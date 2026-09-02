"""WAVE SHOP — тесты автопродления. Самое дорогое место в системе.

Почему этот файл появился: renewals.py был написан, но НИ РАЗУ не выполнен.
В нём было три несовпадения с реальными подписями:

  • record_revenue(amount=..., currency=...) — таких параметров нет
    (нужны amount_rub=..., provider=...)
  • send_message(reply_markup={...}) — параметра нет (нужен keyboard=[[...]])
  • исключение внутри цикла убивало весь прогон

Последствия на живых деньгах: карта клиента СПИСАНА, срок продлён, а дальше
падение — выручка не записана в LEDGER, клиент не получил подтверждения,
и все остальные подписки в пачке не обработаны (люди теряют доступ, хотя
готовы платить). Учёт при этом расходится с банком: деньги пришли, записи нет.

Правило, которое охраняют эти тесты:
    ЕСЛИ ДЕНЬГИ СПИСАНЫ — они обязаны попасть в учёт, клиент обязан узнать,
    и ни один сбой не имеет права остановить остальные продления.

Запуск:  python3 tests/renewals_v1.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Settings        # noqa: E402
from renewals import RenewalEngine  # noqa: E402
from store import Store            # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


def make_settings(tmp: Path, autorenew: bool = True) -> Settings:
    return Settings(
        bot_token="t", admin_ids={1}, shop_name="WAVE", support_contact="@s",
        payment_order=["stars"], yookassa_shop_id="x", yookassa_secret_key="y",
        crypto_pay_token="", crypto_asset="USDT", crypto_rub_per_unit=100.0,
        manual_pay_details="", currency="RUB", ref_reward_percent=10,
        autorenew_enabled=autorenew, renew_notice_days=3,
        data_dir=tmp, runtime_dir=tmp,
    )


class FakeAPI:
    """Телеграм без сети. Ловим и текст, и клавиатуру — чтобы поймать
    несовпадение подписи, а не только факт отправки."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []

    def send_message(self, chat_id, text, keyboard=None, parse_mode="HTML"):
        self.sent.append((chat_id, text, keyboard))
        return {}

    def texts(self) -> str:
        return "\n".join(t for _, t, _ in self.sent)


class Charge:
    def __init__(self, ok: bool, external_id: str = "") -> None:
        self.ok = ok
        self.external_id = external_id


class OkProvider:
    configured = True

    def __init__(self) -> None:
        self.charges: list[tuple[str, int]] = []

    def charge_saved_card(self, pmid, amount_rub, description="", idempotency_key=""):
        self.charges.append((pmid, amount_rub))
        return Charge(True, f"pay_{len(self.charges)}")


class DeadProvider:
    configured = True

    def charge_saved_card(self, pmid, amount_rub, description="", idempotency_key=""):
        return Charge(False)


class ExplodingProvider:
    """Падает на первом клиенте, работает на остальных — проверка изоляции сбоя."""
    configured = True

    def __init__(self) -> None:
        self.calls = 0

    def charge_saved_card(self, pmid, amount_rub, description="", idempotency_key=""):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("провайдер вернул мусор")
        return Charge(True, f"pay_{self.calls}")


def due(store: Store, uid: int, pid: str = "sub_5m", amount: int = 7900) -> None:
    """Подписка, которой пора списаться."""
    store.upsert_subscription(uid, pid, 30, amount, payment_method_id="pm", autorenew=True)
    store.mark_sub_field(uid, pid, paid_until=int(time.time()) - 10)


def setup(tmp: Path, autorenew: bool = True):
    s = make_settings(tmp, autorenew)
    store = Store(tmp)
    store.upsert_product({"id": "sub_5m", "title": "5 млн CAPS/мес", "price_rub": 7900,
                          "kind": "subscription", "period_days": 30, "active": True})
    return s, store


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave_renew_test_"))
    try:
        # ═══ Успешное продление: деньги, учёт, письмо ═══
        s, store = setup(tmp)
        due(store, 5)
        api, prov = FakeAPI(), OkProvider()
        r = RenewalEngine(s, store=store, api=api, provider=prov).run_once()

        check(r["charged"] == 1, f"списание прошло (charged={r['charged']})")
        check(r.get("errors", 0) == 0, "прогон без исключений")
        led = store.revenue_total()
        check(led["orders"] == 1 and led["rub_total"] == 7900,
              f"деньги В УЧЁТЕ: {led['orders']} запись на {led['rub_total']} ₽")
        check(len(api.sent) == 1, "клиент получил подтверждение списания")
        check("продлена" in api.texts(), "в письме сказано, что подписка продлена")
        check("7900" in api.texts() or "7 900" in api.texts(),
              "в письме названа списанная сумма — клиент видит, за что заплатил")
        sub = store.subscription(5, "sub_5m")
        check(int(sub["paid_until"]) > int(time.time()), "срок сдвинут вперёд")
        check(int(sub.get("failed_attempts", 0)) == 0, "счётчик провалов сброшен")

        # Списанное должно совпадать с суммой в учёте — иначе касса не сходится
        check(prov.charges[0][1] == 7900 and led["rub_total"] == 7900,
              "сумма у провайдера и в LEDGER совпадают до рубля")
        shutil.rmtree(tmp, ignore_errors=True)

        # ═══ Пачка: один сбой не убивает остальных ═══
        tmp = Path(tempfile.mkdtemp(prefix="wave_renew_test_"))
        s, store = setup(tmp)
        for uid in (11, 12, 13):
            due(store, uid)
        api = FakeAPI()
        r = RenewalEngine(s, store=store, api=api, provider=ExplodingProvider()).run_once()
        check(r["charged"] == 2 and r["errors"] == 1,
              f"сбой на одном клиенте не остановил пачку "
              f"(продлено {r['charged']}, сбоев {r['errors']})")
        check(store.revenue_total()["orders"] == 2,
              "в учёт попали только реально списанные")
        shutil.rmtree(tmp, ignore_errors=True)

        # ═══ Отказ карты: три попытки, потом пауза ═══
        tmp = Path(tempfile.mkdtemp(prefix="wave_renew_test_"))
        s, store = setup(tmp)
        due(store, 20)
        api = FakeAPI()
        eng = RenewalEngine(s, store=store, api=api, provider=DeadProvider())
        for _ in range(3):
            eng.process_renewals()
        sub = store.subscription(20, "sub_5m")
        check(int(sub.get("failed_attempts", 0)) == 3, "три неудачные попытки посчитаны")
        check(sub.get("autorenew") is False,
              "после 3 отказов автопродление на паузе — карту не долбим бесконечно")
        check(store.revenue_total()["orders"] == 0,
              "неудачное списание НЕ попало в выручку")
        check("вручную" in api.texts(), "клиенту предложен ручной путь продления")
        shutil.rmtree(tmp, ignore_errors=True)

        # ═══ Предупреждение ДО списания ═══
        tmp = Path(tempfile.mkdtemp(prefix="wave_renew_test_"))
        s, store = setup(tmp)
        store.upsert_subscription(30, "sub_5m", 30, 7900, payment_method_id="pm", autorenew=True)
        store.mark_sub_field(30, "sub_5m", paid_until=int(time.time()) + 2 * 86400)
        api = FakeAPI()
        eng = RenewalEngine(s, store=store, api=api, provider=OkProvider())
        sent = eng.send_notices()
        check(sent == 1, "предупреждение о списании отправлено заранее")
        check("Отключите автопродление" in api.texts(),
              "клиенту сказано, как отказаться — иначе это списание втихую")
        check(eng.send_notices() == 0, "повторно о том же списании не пишем")
        shutil.rmtree(tmp, ignore_errors=True)

        # ═══ Рубильник оператора ═══
        tmp = Path(tempfile.mkdtemp(prefix="wave_renew_test_"))
        s, store = setup(tmp, autorenew=False)
        due(store, 40)
        r = RenewalEngine(s, store=store, api=FakeAPI(), provider=OkProvider()).run_once()
        check(r["charged"] == 0 and store.revenue_total()["orders"] == 0,
              "WAVE_AUTORENEW=off полностью останавливает списания")
        shutil.rmtree(tmp, ignore_errors=True)

        # ═══ Отключённое автопродление клиентом ═══
        tmp = Path(tempfile.mkdtemp(prefix="wave_renew_test_"))
        s, store = setup(tmp)
        due(store, 50)
        store.set_autorenew(50, "sub_5m", False)
        r = RenewalEngine(s, store=store, api=FakeAPI(), provider=OkProvider()).run_once()
        check(r["charged"] == 0,
              "клиент отключил автопродление — списания НЕТ (закон подписки)")
        sub = store.subscription(50, "sub_5m")
        check(int(sub["paid_until"]) > 0,
              "оплаченный срок при отключении сохраняется, доступ не отбирают")
        shutil.rmtree(tmp, ignore_errors=True)

        # ═══ Продление НЕ стирает цену ключа шлюза (кабинет клиента) ═══
        # Регресс, который тут ловится: _renew_one звал extend() без price_rub,
        # extend для подписки записывал price_rub=0 → кабинет показывал «0 ₽ из
        # 0» на весь оплаченный месяц. Обещание «сколько РЕАЛЬНО потрачено —
        # отображается» молча ломалось сразу ПОСЛЕ успешного списания денег.
        # Цена ключа при выдаче (990) намеренно НЕ равна списанию (7900): так
        # видно, что продление ставит цену НОВОГО периода, а не 0 и не старую.
        tmp = Path(tempfile.mkdtemp(prefix="wave_renew_test_"))
        s, store = setup(tmp)
        from gateway.quota import QuotaStore  # noqa: E402
        gq = QuotaStore(tmp)
        gwkey = gq.issue_key(user_id=60, plan_id="sub_5m", order_id="o60",
                             price_rub=990)
        gq.consume(gwkey["token"], int(gwkey["tokens_limit"]) // 2, "claude-opus-5")
        due(store, 60, amount=7900)
        RenewalEngine(s, store=store, api=FakeAPI(), provider=OkProvider()).run_once()
        st = gq.status(gwkey["token"])
        check(int(st["price_rub"]) == 7900,
              f"автопродление записало в ключ уплаченную сумму, а не 0 "
              f"({st['price_rub']} ₽ — ждём 7900)")
        check(float(st["spent_rub"]) == 0.0,
              "новый оплаченный месяц: расход в ₽ обнулён, кабинет честен")

        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        print(f"\n{'=' * 58}\nИТОГ: {passed}/{total} проверок пройдено")
        if passed == total:
            print("🔄 АВТОПРОДЛЕНИЕ: деньги доходят до учёта, клиент знает, сбой изолирован.")
            return 0
        print("Есть красные проверки — смотрите выше.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

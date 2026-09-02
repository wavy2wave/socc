"""WAVE — тесты удержания: автоподключение + продление на том же ключе.

Зачем этот файл. Разведка кода показала, что цепочка удержания была разорвана
в пяти местах, и каждый разрыв стоил денег:

  1. save_payment_method НЕ уходил в ЮKassa → карта не сохранялась → любая
     «подписка» была разовой покупкой. Автопродление физически не могло сработать.
  2. payment_method_id никуда не записывался → движок продлений не видел карту.
  3. Ни один товар каталога не создавал запись подписки → subs_due_for_renewal()
     всегда пуст → движок крутился вхолостую.
  4. Продление ВЫДАВАЛО НОВЫЙ КЛЮЧ вместо продления старого → клиент, оплатив
     месяц, должен был заново настраивать Cursor. Продление превращалось в
     работу, а не в тишину.
  5. Успешное списание не продлевало ключ шлюза → деньги взяли, доступ умер.

Правила, которые охраняют эти тесты:
    • Ключ клиента НЕ МЕНЯЕТСЯ при продлении. Настроил один раз — забыл.
    • Если деньги списаны — доступ продлён на том же токене.
    • Автопродление включается только если карта реально привязана.
    • Конфиг, выданный клиенту, работает: модель в нём разрешена его тарифом.

Запуск:  python3 tests/retention_v1.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import ShopCore                                  # noqa: E402
from config import Settings                               # noqa: E402
from renewals import RenewalEngine                        # noqa: E402
from store import Store                                   # noqa: E402
from gateway.quota import QuotaStore, model_allowed        # noqa: E402
from gateway.setup_kit import (                           # noqa: E402
    model_for_key, public_gateway, setup_payload,
)

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


def make_settings(tmp: Path) -> Settings:
    return Settings(
        bot_token="t", admin_ids={1}, shop_name="WAVE", support_contact="@s",
        payment_order=["stars"], yookassa_shop_id="x", yookassa_secret_key="y",
        crypto_pay_token="", crypto_asset="USDT", crypto_rub_per_unit=100.0,
        manual_pay_details="", currency="RUB", ref_reward_percent=10,
        autorenew_enabled=True, renew_notice_days=3, data_dir=tmp, runtime_dir=tmp,
    )


SUB = {"id": "sub_5m", "plan_id": "sub_5m", "title": "5 млн CAPS/мес",
       "price_rub": 7900, "kind": "gateway", "period_days": 30, "active": True}
HOUR = {"id": "hour_1", "plan_id": "hour_1", "title": "1 час",
        "price_rub": 550, "kind": "gateway", "active": True}
DEMO = {"id": "demo", "plan_id": "demo", "title": "Демо", "price_rub": 0,
        "kind": "gateway", "active": True}


class FakeAPI:
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

    def charge_saved_card(self, pmid, amount_rub, description="", idempotency_key=""):
        return Charge(True, "pay_next")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave_ret_test_"))
    os.environ["WAVE_PUBLIC_GATEWAY"] = "https://api.example.com"
    try:
        s = make_settings(tmp)
        store = Store(tmp)
        core = ShopCore(store, s)
        for p in (SUB, HOUR, DEMO):
            store.upsert_product(p)
        gq = QuotaStore(tmp)

        # ═══ ГЛАВНОЕ: продление НЕ меняет ключ ═══
        o1 = store.create_order(1, "sub_5m", "yookassa", 7900)
        store.update_order(o1["order_id"], payment_method_id="pm_card")
        ok1, pay1 = core.deliver(o1["order_id"])
        check(ok1, "подписка куплена, ключ выдан")
        first = gq.keys_of_user(1)[0]["token"]

        o2 = store.create_order(1, "sub_5m", "yookassa", 7900)
        store.update_order(o2["order_id"], payment_method_id="pm_card")
        ok2, pay2 = core.deliver(o2["order_id"])
        keys_now = [k["token"] for k in gq.keys_of_user(1)]
        check(ok2 and len(keys_now) == 1,
              f"повторная покупка НЕ создала второй ключ (ключей: {len(keys_now)})")
        check(keys_now[0] == first,
              "токен тот же — клиенту нечего перенастраивать после продления")
        check("продлён" in pay2 and "тот же" in pay2,
              "клиенту прямо сказано, что ключ не изменился")

        st = gq.status(first)
        check(int(st["tokens_left"]) == 5_000_000,
              f"квота обновлена на новый период ({st['tokens_left']:,} CAPS)")

        # ═══ Почасовой — всегда новый ключ ═══
        for _ in range(2):
            o = store.create_order(2, "hour_1", "stars", 550)
            core.deliver(o["order_id"])
        check(len(gq.keys_of_user(2)) == 2,
              "почасовой тариф выдаёт НОВЫЙ ключ каждый раз (час нельзя продлевать)")

        # ═══ Подписка зарегистрирована для движка продлений ═══
        sub = store.subscription(1, "sub_5m")
        check(sub is not None, "запись подписки создана — движок её увидит")
        check(sub.get("autorenew") is True,
              "автопродление включено: карта привязана")
        check(sub.get("payment_method_id") == "pm_card",
              "id карты доехал от оплаты до подписки")

        # ═══ Без карты автопродления НЕ обещаем ═══
        o3 = store.create_order(3, "sub_5m", "stars", 7900)   # Stars карту не даёт
        core.deliver(o3["order_id"])
        sub3 = store.subscription(3, "sub_5m")
        check(sub3 is not None and sub3.get("autorenew") is False,
              "без привязанной карты автопродление выключено — не обещаем невозможное")
        # Горизонт 70 дней: первая покупка дала 30 дней, повторная ПРОДЛИЛА
        # до 60 (клиент не теряет оплаченные дни) — значит очередь продлений
        # должна увидеть подписку только после этого срока.
        check(len(store.subs_due_for_renewal(int(time.time()) + 70 * 86400)) >= 1,
              "подписки с картой попадают в очередь продлений")
        check(len(store.subs_due_for_renewal(int(time.time()) + 10 * 86400)) == 0,
              "до конца оплаченного срока НИКОГО не списываем")

        # ═══ Списание продлевает ТОТ ЖЕ ключ шлюза ═══
        store.mark_sub_field(1, "sub_5m", paid_until=int(time.time()) - 10)
        gq.consume(first, 4_000_000, "claude-opus-5")
        before = gq.status(first)["tokens_left"]
        api = FakeAPI()
        r = RenewalEngine(s, store=store, api=api, provider=OkProvider()).run_once()
        check(r["charged"] == 1, "автосписание прошло")
        after_keys = [k["token"] for k in gq.keys_of_user(1)]
        check(len(after_keys) == 1 and after_keys[0] == first,
              "после автопродления ключ ВСЁ ЕЩЁ тот же")
        after = gq.status(first)
        check(after["tokens_left"] > before,
              f"квота на ключе восстановлена ({before:,} → {after['tokens_left']:,})")
        check(int(after["seconds_left"]) > 0, "срок ключа сдвинут вперёд")
        check("перенастраивать не нужно" in api.texts(),
              "в письме о продлении клиента успокаивают насчёт настроек")

        # ═══ АВТОУСТАНОВЩИК ═══
        rec = gq.get_key(first)
        kit = setup_payload(rec)

        check(kit["base_url"] == "https://api.example.com/v1",
              f"адрес шлюза берётся из окружения и заканчивается на /v1 "
              f"({kit['base_url']})")
        check(kit["token"] == first and first in kit["curl"],
              "в готовой команде стоит реальный ключ клиента")
        check("Bearer " + first in kit["curl"],
              "заголовок авторизации собран правильно")

        # Конфиг обязан быть валидным — иначе клиент вставит и получит ошибку
        import json as _json
        cont = _json.loads(kit["continue_json"])
        check(cont["models"][0]["apiKey"] == first
              and cont["models"][0]["apiBase"] == kit["base_url"],
              "конфиг Continue — валидный JSON с ключом и адресом")
        cline = _json.loads(kit["cline_json"])
        check(cline["openAiApiKey"] == first, "конфиг Cline — валидный JSON")

        check("OPENAI_API_KEY=" + first in kit["env"],
              ".env содержит ключ в правильной переменной")
        check("export OPENAI_BASE_URL=" in kit["shell"],
              "shell-экспорты готовы к вставке в ~/.zshrc")
        check("~/.continue/config.json" in kit["install_continue"]
              and first in kit["install_continue"],
              "одна команда сама кладёт конфиг Continue на место")
        check("curl" not in kit["install_continue"].split("\n")[0].lower(),
              "установка НЕ качает скрипт с сервера — клиент видит, что применяет")

        # ═══ Модель в конфиге должна быть РАЗРЕШЕНА тарифом ═══
        o4 = store.create_order(9, "demo", "free", 0)
        core.deliver(o4["order_id"])
        demo_rec = gq.keys_of_user(9)[0]
        demo_kit = setup_payload(demo_rec)
        check(demo_kit["model"] == "claude-sonnet-5",
              f"демо получает конфиг с Sonnet, а не Opus ({demo_kit['model']})")
        check(model_allowed(demo_kit["model"], demo_rec.get("model_key", "")),
              "модель из конфига проходит проверку шлюза — файл рабочий")
        check(model_for_key({}) == "claude-opus-5",
              "ключ без потолка получает флагманскую модель")
        paid_kit = setup_payload(gq.get_key(first))
        check(model_allowed(paid_kit["model"], gq.get_key(first).get("model_key", "")),
              "конфиг платного тарифа тоже проходит шлюз")

        # ═══ Конфиг не содержит срока — иначе после продления он врёт ═══
        blob = (kit["continue_json"] + kit["env"] + kit["shell"] + kit["cline_json"])
        check("expires" not in blob and "tokens_left" not in blob,
              "в конфиге нет срока и остатка: файл остаётся верным после продления")

        # ═══ Изоляция: чужой ключ по хвосту не достать ═══
        mine = {k["token"][-6:] for k in gq.keys_of_user(1)}
        others = {k["token"][-6:] for k in gq.keys_of_user(2)}
        check(not (mine & others), "хвосты токенов разных клиентов не пересекаются")

        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        print(f"\n{'=' * 60}\nИТОГ: {passed}/{total} проверок пройдено")
        if passed == total:
            print("🔗 УДЕРЖАНИЕ: ключ не меняется, продление тихое, конфиг рабочий.")
            return 0
        print("Есть красные проверки — смотрите выше.")
        return 1
    finally:
        os.environ.pop("WAVE_PUBLIC_GATEWAY", None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

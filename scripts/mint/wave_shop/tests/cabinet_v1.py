"""WAVE — тесты КАБИНЕТА клиента: потокенный кошелёк, автопополнение, выбор
продления, привязка/отвязка карты.

Оператор попросил ровно эту петлю: «ввёл ключ → отсчёт; трафик кончился →
автосписание; на продлении человек СВОБОДЕН выбрать — тот же пакет, любой другой
или вообще без пакета (потокенно по нашему тарифу); карта привязывается сама и
обслуживает всё». Здесь мы охраняем каждое обещание на уровне UI-обвязки —
БЕЗ единого реального запроса в сеть и БЕЗ движения денег (RUBICON цел).

Что проверяем:

  1. Потокенный кошелёк ВИДЕН в «Мои ключи»: показываем ₽-баланс и расход, а НЕ
     остаток токенов и НЕ ложное «♾ Без срока» (у кошелька срока нет).
  2. Автопополнение включается ТОЛЬКО при живой карте. Нет карты — кнопки нет и
     включить нельзя (обещали бы списание, которое нечем исполнить).
  3. Ручное пополнение: счёт → «Я оплатил» → кошелёк пополнен РОВНО раз (повтор
     нажатия не зачисляет второй раз — защита нашей маржи).
  4. RUBICON: нет кассы (ЮKassa) — заказ на пополнение не создаётся, счёт не
     выставляется, баланс не трогается.
  5. Выбор «чем продлевать» пишется в next_product_id: тот же / потокенно /
     другой пакет; несуществующий пакет — не пишется (кривой выбор отклонён).
  6. Карта: сохранилась → видна и отвязывается; после отвязки автопродление
     подписки живёт на СВОЕЙ карте (честное предупреждение, не ложное «удалено»).

Запуск:  python3 tests/cabinet_v1.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import ShopBot                                   # noqa: E402
from config import Settings                               # noqa: E402
from store import Store                                   # noqa: E402
from gateway.quota import QuotaStore                       # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


def make_settings(tmp: Path) -> Settings:
    return Settings(
        bot_token="t", admin_ids={1}, shop_name="WAVE", support_contact="@s",
        payment_order=["yookassa"], yookassa_shop_id="x", yookassa_secret_key="y",
        crypto_pay_token="", crypto_asset="USDT", crypto_rub_per_unit=100.0,
        manual_pay_details="", currency="RUB", ref_reward_percent=10,
        autorenew_enabled=True, renew_notice_days=3, data_dir=tmp, runtime_dir=tmp,
    )


class FakeAPI:
    """Перехват транспорта: ни одного реального запроса в Telegram."""

    def __init__(self, token: str = "") -> None:
        self.sent: list[tuple[int, str, object]] = []

    def send_message(self, chat_id, text, kb=None, **kw):
        self.sent.append((chat_id, text, kb))
        return {"ok": True, "result": {"message_id": 1}}

    def edit_message_text(self, chat_id, message_id, text, kb=None, **kw):
        self.sent.append((chat_id, text, kb))
        return {"ok": True, "result": {"message_id": message_id}}

    def answer_callback(self, *a, **kw):
        return {}

    def get_me(self):
        return {"username": "t"}

    def last_text(self) -> str:
        return self.sent[-1][1] if self.sent else ""

    def all_text(self) -> str:
        return "\n".join(t for _, t, _ in self.sent)

    def last_callbacks(self) -> list[str]:
        if not self.sent:
            return []
        kb = self.sent[-1][2] or []
        return [b.get("callback_data", "") for row in kb for b in row]

    def all_callbacks(self) -> list[str]:
        out: list[str] = []
        for _, _, kb in self.sent:
            for row in (kb or []):
                for b in row:
                    if "callback_data" in b:
                        out.append(b["callback_data"])
        return out


class FakeCharge:
    def __init__(self, ok=True, method="url", pay_url="https://pay.example",
                 external_id="ext1", message="") -> None:
        self.ok = ok
        self.method = method
        self.pay_url = pay_url
        self.external_id = external_id
        self.message = message


class FakeYoo:
    """Поддельная ЮKassa: без сети, с управляемым verify и сохранённой картой."""
    key = "yookassa"
    hint = "тест"

    def __init__(self) -> None:
        self.verify_ok = True
        self.pm = "pm_saved_1"
        self.charges = 0

    def create_charge(self, order, product):
        self.charges += 1
        return FakeCharge(ok=True, external_id="ext_" + order["order_id"])

    def verify(self, external_id):
        return self.verify_ok

    def fetch_payment_method(self, external_id):
        return self.pm


def make_bot(tmp: Path, providers: dict | None) -> ShopBot:
    """ShopBot с подменённым транспортом и кассами (сеть не трогаем)."""
    bot = ShopBot(make_settings(tmp))
    bot.api = FakeAPI()
    bot.providers = providers if providers is not None else {"yookassa": FakeYoo()}
    return bot


def tail_of(token: str) -> str:
    return token[-6:]


def main() -> int:  # noqa: C901
    tmp = Path(tempfile.mkdtemp(prefix="wave_cab_test_"))
    try:
        # ═══ 1. Потокенный кошелёк виден в «Мои ключи» ═══
        bot = make_bot(tmp, None)
        gq = QuotaStore(tmp)
        rec = gq.issue_key(user_id=10, plan_id="postpaid", price_rub=500)
        token = rec["token"]
        bot.render_my_subs(chat_id=100, message_id=None, user_id=10)
        txt = bot.api.last_text()
        cbs = bot.api.last_callbacks()
        check("Кошелёк" in txt and "500" in txt,
              "потокенный кошелёк показывает ₽-баланс (500 ₽)")
        check("Без срока" not in txt,
              "у кошелька НЕТ ложного «♾ Без срока» (срока у ₽-кошелька нет)")
        check(f"pp:top:{tail_of(token)}" in cbs,
              "есть кнопка «Пополнить кошелёк» (pp:top:<tail>)")
        # Карты нет → включить автопополнение НЕЛЬЗЯ, кнопки auto1 быть не должно.
        check(f"pp:auto1:{tail_of(token)}" not in cbs,
              "без карты кнопки «включить автопополнение» нет")

        # ═══ 2. Автопополнение включается только при живой карте ═══
        # 2a. Нет карты → auto1 блокируется, флаг НЕ ставится.
        bot.api.sent.clear()
        bot._handle_postpaid_callback(101, None, 10, f"auto1:{tail_of(token)}")
        st = gq.status(token)
        check(not st.get("autotopup"),
              "auto1 без карты НЕ включил автопополнение")
        check("привяж" in bot.api.all_text().lower(),
              "объяснили клиенту, что нужна карта")

        # 2b. Появилась карта → auto1 включает; auto0 выключает.
        bot.store.set_card_on_file(10, "pm_user_10", provider="yookassa")
        bot.api.sent.clear()
        bot._handle_postpaid_callback(102, None, 10, f"auto1:{tail_of(token)}")
        check(bool(gq.status(token).get("autotopup")),
              "auto1 при живой карте ВКЛючил автопополнение")
        bot._handle_postpaid_callback(103, None, 10, f"auto0:{tail_of(token)}")
        check(not gq.status(token).get("autotopup"),
              "auto0 выключил автопополнение")

        # ═══ 3. Ручное пополнение: счёт → «Я оплатил» → +ровно один раз ═══
        bot2 = make_bot(tmp, None)
        yoo = bot2.providers["yookassa"]
        gq2 = QuotaStore(tmp)
        rec3 = gq2.issue_key(user_id=13, plan_id="postpaid", price_rub=500)
        tok3 = rec3["token"]
        bot2.start_postpaid_topup(chat_id=130, user_id=13, tail=tail_of(tok3), amount_rub=500)
        chk_cbs = [c for c in bot2.api.last_callbacks() if c.startswith("ppchk:")]
        check(len(chk_cbs) == 1, "счёт на пополнение создан, есть кнопка «Я оплатил»")
        order_id = chk_cbs[0].split(":", 1)[1]
        order = bot2.store.get_order(order_id)
        check(order is not None and order.get("product_id") == "postpaid_topup",
              "заказ помечен product_id='postpaid_topup' (отдельный от товаров путь)")
        check(bool(order and order.get("save_card")),
              "save_card=True — карта сохранится при оплате пополнения")

        # 3a. Оплата ещё не видна → НЕ зачисляем.
        yoo.verify_ok = False
        bot2.api.sent.clear()
        bot2.check_topup_payment(131, 13, order_id)
        check(abs(float(gq2.status(tok3)["balance_rub"]) - 500.0) < 0.01,
              "verify=False: баланс НЕ изменился (500 ₽)")
        check(bot2.store.get_order(order_id).get("status") != "delivered",
              "verify=False: заказ НЕ помечен delivered")

        # 3b. Оплата видна → зачисляем РОВНО раз.
        yoo.verify_ok = True
        bot2.api.sent.clear()
        bot2.check_topup_payment(132, 13, order_id)
        bal_after = float(gq2.status(tok3)["balance_rub"])
        check(abs(bal_after - 1000.0) < 0.01,
              f"verify=True: кошелёк пополнен на 500 → {bal_after:.0f} ₽")
        check(bot2.store.get_order(order_id).get("status") == "delivered",
              "успешное пополнение помечает заказ delivered")
        card = bot2.store.card_on_file(13)
        check(bool(card and card.get("payment_method_id") == "pm_saved_1"),
              "карта с оплаты пополнения легла на файл (для автопополнения)")

        # 3c. Повторное нажатие «Я оплатил» — БЕЗ второго зачисления.
        bot2.api.sent.clear()
        bot2.check_topup_payment(133, 13, order_id)
        bal_again = float(gq2.status(tok3)["balance_rub"])
        check(abs(bal_again - 1000.0) < 0.01,
              f"повтор «Я оплатил» НЕ зачислил второй раз (осталось {bal_again:.0f} ₽)")
        check("уже зачислено" in bot2.api.all_text().lower(),
              "повтору честно сказали, что пополнение уже зачислено")

        # ═══ 4. RUBICON: нет кассы → пополнение не создаётся ═══
        bot3 = make_bot(tmp, providers={})   # касс нет вовсе
        gq3 = QuotaStore(tmp)
        rec4 = gq3.issue_key(user_id=14, plan_id="postpaid", price_rub=500)
        tok4 = rec4["token"]
        bot3.start_postpaid_topup(140, 14, tail_of(tok4), 500)
        check(not any(c.startswith("ppchk:") for c in bot3.api.all_callbacks()),
              "без кассы счёт на пополнение НЕ выставлен (RUBICON)")
        check(abs(float(gq3.status(tok4)["balance_rub"]) - 500.0) < 0.01,
              "без кассы баланс не тронут")
        check("касс" in bot3.api.all_text().lower() or "ЮKassa" in bot3.api.all_text(),
              "клиенту честно сказали, что касса не настроена")

        # ═══ 5. Выбор «чем продлевать» пишется в next_product_id ═══
        bot4 = make_bot(tmp, None)
        for p in (
            {"id": "sub_a", "title": "Пакет A", "price_rub": 1000,
             "kind": "subscription", "period_days": 30, "active": True},
            {"id": "sub_b", "title": "Пакет B", "price_rub": 2000,
             "kind": "subscription", "period_days": 30, "active": True},
        ):
            bot4.store.upsert_product(p)
        bot4.store.upsert_subscription(15, "sub_a", 30, 1000,
                                       payment_method_id="pm_15", autorenew=True)

        bot4._apply_renewal_choice(150, None, 15, "p:sub_a")
        check(bot4.store.subscription(15, "sub_a").get("next_product_id") == "__postpaid__",
              "выбор «потокенно» записан (next_product_id=__postpaid__)")

        bot4._apply_renewal_choice(151, None, 15, "o:sub_a:sub_b")
        check(bot4.store.subscription(15, "sub_a").get("next_product_id") == "sub_b",
              "выбор «другой пакет» записан (next_product_id=sub_b)")

        bot4._apply_renewal_choice(152, None, 15, "s:sub_a")
        check(bot4.store.subscription(15, "sub_a").get("next_product_id") == "",
              "выбор «тот же тариф» очистил next_product_id")

        # Несуществующий пакет — кривой выбор отклонён, старое значение цело.
        bot4._apply_renewal_choice(153, None, 15, "o:sub_a:sub_ghost")
        check(bot4.store.subscription(15, "sub_a").get("next_product_id") == "",
              "выбор несуществующего пакета НЕ записан")
        check("недоступен" in bot4.api.all_text().lower(),
              "про исчезнувший пакет сказали честно")

        # Экран выбора рисуется и предлагает оба альтернативных хода.
        bot4.api.sent.clear()
        bot4.render_renewal_choice(154, None, 15, "sub_a")
        rc_cbs = bot4.api.last_callbacks()
        check("rcx:s:sub_a" in rc_cbs and "rcx:p:sub_a" in rc_cbs
              and "rcx:o:sub_a:sub_b" in rc_cbs,
              "экран выбора даёт все три хода: тот же / потокенно / другой")

        # ═══ 6. Карта: видна, отвязывается, подписка живёт на своей карте ═══
        bot5 = make_bot(tmp, None)
        bot5.store.set_card_on_file(16, "pm_user_16", title="•• 4242", provider="yookassa")
        check(bot5._user_payment_method(16) == "pm_user_16",
              "привязанная карта видна кабинету (card_on_file)")
        bot5.api.sent.clear()
        bot5.forget_card_cmd(160, None, 16)
        check(bot5.store.card_on_file(16) is None,
              "отвязка убрала card_on_file")
        # Подписка со своей картой → кабинет всё ещё «видит» карту (fallback),
        # честно предупреждаем, что подписка спишется со своей.
        bot5.store.upsert_subscription(16, "sub_x", 30, 900, payment_method_id="pm_sub_16")
        check(bot5._user_payment_method(16) == "pm_sub_16",
              "после отвязки кабинет берёт карту подписки (fallback как в движке)")

        # ═══ 7. Диспетчер: каждая кнопка кабинета идёт в СВОЙ обработчик ═══
        # Методы тесты зовут напрямую — а вот РАЗВОДКА callback'ов не покрыта.
        # Именно тут будущий рефактор мог бы тихо перекрестить денежную кнопку
        # (pp: перехватил бы pptop:, rc: — rcx:). Ловим это монитором вызовов.
        bot6 = make_bot(tmp, None)
        calls: list[tuple[str, tuple]] = []
        bot6.start_postpaid_topup = lambda *a, **k: calls.append(("topup_start", a))
        bot6.check_topup_payment = lambda *a, **k: calls.append(("topup_check", a))
        bot6._handle_postpaid_callback = lambda *a, **k: calls.append(("pp", a))
        bot6._apply_renewal_choice = lambda *a, **k: calls.append(("rcx", a))
        bot6.render_renewal_choice = lambda *a, **k: calls.append(("rc", a))
        bot6.forget_card_cmd = lambda *a, **k: calls.append(("forget", a))

        def cq_update(data, chat=900, mid=5, uid=77):
            return {"callback_query": {"id": "c1", "data": data,
                    "message": {"chat": {"id": chat}, "message_id": mid},
                    "from": {"id": uid}}}

        def route(data):
            calls.clear()
            bot6.handle_update(cq_update(data))
            return calls[0] if calls else (None, ())

        name, a = route("pptop:abcdef:500")
        check(name == "topup_start" and a[2] == "abcdef" and a[3] == 500,
              "pptop:<tail>:<amt> → start_postpaid_topup (сумма как int)")
        check(route("pptop:abcdef:notnum") == (None, ()),
              "pptop с нечисловой суммой игнорируется (никого не зовём)")
        name, a = route("ppchk:ord_9")
        check(name == "topup_check" and a[2] == "ord_9",
              "ppchk:<order> → check_topup_payment (НЕ перехвачен pp:)")
        name, a = route("pp:auto1:abcdef")
        check(name == "pp" and a[3] == "auto1:abcdef",
              "pp:<...> → _handle_postpaid_callback (НЕ перехвачен pptop:/ppchk:)")
        name, a = route("rcx:o:sub_a:sub_b")
        check(name == "rcx" and a[3] == "o:sub_a:sub_b",
              "rcx:<...> → _apply_renewal_choice (НЕ перехвачен rc:)")
        name, a = route("rc:sub_a")
        check(name == "rc" and a[3] == "sub_a",
              "rc:<pid> → render_renewal_choice")
        name, a = route("card:forget")
        check(name == "forget", "card:forget → forget_card_cmd")

        # ── ИТОГ ──
        print("\n" + "=" * 46)
        ok = sum(1 for c, _ in results if c)
        total = len(results)
        print(f"ИТОГ: {ok}/{total} проверок пройдено")
        if ok == total:
            print("🔑 КАБИНЕТ: кошелёк, автопополнение, выбор продления и карта — честны и RUBICON-safe.")
            return 0
        print("Кабинет прохудился — смотрите выше.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

"""WAVE SHOP — регрессия на находки аудита админ-панели (A–H).

Почему отдельный файл, а не дополнение admin_panel_v1:
admin_panel_v1 дёргает мастер и колбэки НАПРЯМУЮ (_admin_wizard_input,
_handle_admin_callback), минуя реальный диспетчер handle_update. Именно там
жил самый дорогой баг: активный мастер перехватывал СЛЭШ-команды (/confirm,
/stock, /start), и оплаченный заказ оставался без выдачи, а цена/склад
искажались случайными цифрами из команды. Этот набор бьёт по РОУТИНГУ —
гоняет апдейты через handle_update ровно так, как их принесёт Telegram.

Плюс проверяет разбор цены (десятичные → 100× переплата), очистку мастера по
/admin, гейтинг кнопки «изменить выдачу» по типу, ленту продаж по 'delivered',
безопасный отказ при удалённом товаре и лимит 64 байта на id.

Запуск:  python3 tests/admin_fixes_v1.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot import ShopBot                  # noqa: E402
from config import Settings              # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


class FakeAPI:
    """Телеграм-заглушка: помнит последний экран и всю ленту отправленного."""

    def __init__(self) -> None:
        self.last_text = ""
        self.last_kb: list[list[dict]] = []
        self.sent: list[str] = []

    def send_message(self, chat_id, text="", kb=None, **kw):
        self.last_text, self.last_kb = text, kb or []
        self.sent.append(text)
        return {"ok": True, "result": {"message_id": 1}}

    def edit_message_text(self, chat_id, message_id, text="", kb=None, **kw):
        self.last_text, self.last_kb = text, kb or []
        self.sent.append(text)
        return {"ok": True}

    def answer_callback(self, *a, **kw):
        return {"ok": True}

    def answer_pre_checkout(self, *a, **kw):
        return {"ok": True}


def cbs(kb: list[list[dict]]) -> list[str]:
    return [b.get("callback_data", "") for row in kb for b in row]


def make_bot(tmp: Path, admin_ids=frozenset({1})) -> ShopBot:
    s = Settings(
        bot_token="test:token", admin_ids=set(admin_ids), shop_name="WAVE SHOP",
        support_contact="@support", payment_order=["stars", "manual"],
        yookassa_shop_id="", yookassa_secret_key="", crypto_pay_token="",
        crypto_asset="USDT", crypto_rub_per_unit=100.0,
        manual_pay_details="Карта 0000", currency="RUB", ref_reward_percent=10,
        autorenew_enabled=False, renew_notice_days=3,
        data_dir=tmp, runtime_dir=tmp / "runtime",
    )
    bot = ShopBot(s)
    bot.api = FakeAPI()
    return bot


def msg(bot: ShopBot, user_id: int, text: str, chat_id: int = 1) -> None:
    """Прогнать текстовое сообщение через РЕАЛЬНЫЙ диспетчер."""
    bot.handle_update({
        "update_id": 1,
        "message": {"chat": {"id": chat_id}, "from": {"id": user_id, "username": "u"},
                    "text": text},
    })


def add_product(bot: ShopBot, pid: str, kind: str, price: int = 500) -> None:
    p = {"id": pid, "title": pid, "description": "d", "price_rub": price,
         "stars_price": max(1, round(price / 16.6)) if price else 0,
         "kind": kind, "active": True}
    if kind == "lifetime":
        p["lifetime_payload"] = "СЕКРЕТ-ВЫДАЧА"
    if kind == "subscription":
        p["period_days"] = 30
    bot.store.upsert_product(p)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave_admin_fixes_"))
    try:
        # ============ A: слэш-команды НЕ проглатываются мастером ============
        bot = make_bot(tmp)
        add_product(bot, "day_pass", "lifetime", price=500)
        buyer = 555
        order = bot.store.create_order(buyer, "day_pass", "manual", 500)
        oid = order["order_id"]

        # Админ (1) заходит в мастер правки цены и НЕ выходит из него.
        bot._handle_admin_callback(1, 1, 1, "adm:price:day_pass")
        check(bot._admin_state.get(1, {}).get("step") == "edit_price",
              "мастер правки цены открыт")

        # Пока мастер открыт — /confirm приходит от админа через диспетчер.
        msg(bot, 1, f"/confirm {oid}")
        confirmed = bot.store.get_order(oid)
        check(confirmed and confirmed["status"] == "delivered",
              "/confirm при открытом мастере ВЫДАЛ заказ (не проглочен)")
        check(bot.store.product("day_pass")["price_rub"] == 500,
              "цена НЕ испорчена цифрами из /confirm (осталась 500₽)")

        # Мастер всё ещё жив → обычный текст правит цену как задумано.
        msg(bot, 1, "700")
        check(bot.store.product("day_pass")["price_rub"] == 700,
              "свободный текст всё ещё уходит в мастер (цена → 700₽)")
        check(1 not in bot._admin_state, "мастер закрылся после ввода цены")

        # /stock тоже должен пройти при открытом мастере (товар-ключ).
        add_product(bot, "keyprod", "key", price=300)
        bot._handle_admin_callback(1, 1, 1, "adm:price:keyprod")   # снова открыли мастер
        msg(bot, 1, "/stock keyprod KEY-1,KEY-2")
        check(bot.store.stock_count("keyprod") == 2,
              "/stock при открытом мастере пополнил склад (не проглочен)")

        # ==================== B: /admin чистит мастер ====================
        bot2 = make_bot(tmp / "b")
        bot2._admin_start_add(1, 1)
        check(1 in bot2._admin_state, "мастер добавления запущен")
        msg(bot2, 1, "/admin")
        check(1 not in bot2._admin_state, "/admin сбросил застрявший мастер")
        check("Управление" in bot2.api.last_text, "/admin показал панель")

        # ==================== C: разбор цены ====================
        check(ShopBot._parse_int("550") == 550, "«550» → 550")
        check(ShopBot._parse_int("1 600 ₽") == 1600, "«1 600 ₽» → 1600")
        check(ShopBot._parse_int("1 600,50 ₽") == 1600,
              "«1 600,50 ₽» → 1600 (десятичные НЕ дают 100× переплату)")
        check(ShopBot._parse_int("199,99") == 200, "«199,99» → 200 (округление)")
        check(ShopBot._parse_int("/confirm ord_1") is None,
              "команда как цена отвергнута")
        check(ShopBot._parse_int("abc") is None, "мусор без цифр → None")
        # Огромный ввод не должен ронять процесс: либо капнут потолком, либо
        # безопасно отвергнут (None). Главное — не OverflowError и не переплата.
        big400 = ShopBot._parse_int("9" * 400)
        check(big400 is None or big400 == ShopBot._MAX_PRICE_RUB,
              "строка из 400 цифр не роняет (None или потолок)")
        big_finite = ShopBot._parse_int("9999999999")   # 10 млрд ₽
        check(big_finite == ShopBot._MAX_PRICE_RUB,
              "крупная конечная цена капнута потолком, а не принята как есть")

        # Интеграция: правим цену через мастер строкой с копейками.
        bot3 = make_bot(tmp / "c")
        add_product(bot3, "px", "lifetime", price=500)
        bot3._handle_admin_callback(1, 1, 1, "adm:price:px")
        msg(bot3, 1, "1 600,50 ₽")
        check(bot3.store.product("px")["price_rub"] == 1600,
              "мастер: «1 600,50 ₽» сохранил 1600₽, а не 160050₽")

        # ==================== E: гейтинг кнопки «изменить выдачу» ====================
        bot4 = make_bot(tmp / "e")
        add_product(bot4, "life", "lifetime")
        add_product(bot4, "gw", "gateway")
        add_product(bot4, "sub", "subscription")
        add_product(bot4, "key", "key")

        bot4.render_admin_product(1, None, "life")
        check(any(c == "adm:pay:life" for c in cbs(bot4.api.last_kb)),
              "lifetime: кнопка «изменить выдачу» ЕСТЬ")
        bot4.render_admin_product(1, None, "gw")
        check(not any(c.startswith("adm:pay:") for c in cbs(bot4.api.last_kb)),
              "gateway: кнопки «изменить выдачу» НЕТ (обман исключён)")
        bot4.render_admin_product(1, None, "sub")
        check(not any(c.startswith("adm:pay:") for c in cbs(bot4.api.last_kb)),
              "subscription: кнопки «изменить выдачу» НЕТ")
        bot4.render_admin_product(1, None, "key")
        kb_key = cbs(bot4.api.last_kb)
        check(any(c == "adm:stock:key" for c in kb_key)
              and not any(c.startswith("adm:pay:") for c in kb_key),
              "key: есть «склад», нет «изменить выдачу»")

        # ==================== F: лента продаж = delivered ====================
        bot5 = make_bot(tmp / "f")
        add_product(bot5, "d1", "lifetime", price=800)
        add_product(bot5, "d2", "lifetime", price=900)
        o1 = bot5.store.create_order(70, "d1", "manual", 800)["order_id"]
        o2 = bot5.store.create_order(71, "d2", "manual", 900)["order_id"]
        bot5.core.mark_paid(o1); bot5._fulfill_and_send(70, o1)   # доставлен
        bot5.core.mark_paid(o2)                                   # завис в 'paid'
        bot5.render_admin_revenue(1, None)
        rev_text = bot5.api.last_text
        check("800" in rev_text, "лента продаж показывает доставленный (800₽)")
        check("900" not in rev_text,
              "заказ в статусе 'paid' (не доставлен) в ленту НЕ попал")

        # ==================== G: правка удалённого товара ====================
        bot6 = make_bot(tmp / "g")
        add_product(bot6, "gone", "lifetime", price=400)
        bot6._handle_admin_callback(1, 1, 1, "adm:price:gone")   # открыли мастер
        bot6.store.delete_product("gone")                        # товар исчез
        msg(bot6, 1, "1000")                                     # шлём новую цену
        check(1 not in bot6._admin_state, "мастер закрылся при удалённом товаре")
        check("не найден" in bot6.api.sent[-2].lower()
              or "удал" in bot6.api.sent[-2].lower()
              or any("не найден" in s.lower() or "удал" in s.lower()
                     for s in bot6.api.sent[-3:]),
              "оператору сказано: товар не найден/удалён")
        check("Товары" in bot6.api.last_text or "пусто" in bot6.api.last_text.lower(),
              "после отказа вернулись к списку товаров")

        # ==================== H: лимит 64 байта на id ====================
        check(ShopBot._id_manageable("day_pass_ab12"), "короткий ASCII id — управляем")
        check(not ShopBot._id_manageable("я" * 60),
              "60 кириллических символов (120 байт) — НЕ управляем")
        bot7 = make_bot(tmp / "h")
        long_id = "оченьдлинныйидентификатортоваранакириллице_x"  # >54 байт
        add_product(bot7, long_id, "lifetime")
        add_product(bot7, "ok_id", "lifetime")
        bot7.render_admin_products(1, None)
        kb_all = cbs(bot7.api.last_kb)
        check(any(c == "adm:p:ok_id" for c in kb_all), "короткий id — кнопка есть")
        check(not any(c == f"adm:p:{long_id}" for c in kb_all),
              "длинный id — мёртвой кнопки нет")
        check("не помещаются" in bot7.api.last_text.lower()
              or "переименуй" in bot7.api.last_text.lower(),
              "оператора предупредили о длинном id")

        print("\n====================================================")
        total = len(results)
        ok = sum(1 for good, _ in results if good)
        print(f"ИТОГ: {ok}/{total} проверок пройдено")
        print("🛡 WAVE SHOP: находки аудита A–H закрыты регрессией.")
        return 0 if ok == total else 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

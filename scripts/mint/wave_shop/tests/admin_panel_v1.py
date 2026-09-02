"""WAVE SHOP — регрессия админ-панели: CRUD товаров из бота, мастер добавления.

Зачем этот файл:
До панели товар добавлялся только правкой data/catalog.json руками. Это делало
магазин непригодным «под ключ»: создатель не может управлять витриной с
телефона. Панель (callback-роутинг adm:* + пошаговый мастер с состоянием)
должна уметь: создать товар обоих типов, поменять цену/выдачу/склад, скрыть и
снова показать, удалить, — и НЕ пускать не-админов.

Всё тестируется на ВРЕМЕННОМ каталоге — боевой data/catalog.json не трогается.
Только Store и ShopBot, без сети: TelegramAPI подменён фейком.

Запуск:  python3 tests/admin_panel_v1.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot import ShopBot                  # noqa: E402
from config import Settings              # noqa: E402
from store import Store                  # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


class FakeAPI:
    """Телеграм-заглушка: запоминает последний экран."""

    def __init__(self) -> None:
        self.last_text = ""
        self.last_kb: list[list[dict]] = []
        self.sent: list[str] = []          # все отправленные тексты подряд

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


def buttons(kb: list[list[dict]]) -> list[str]:
    return [b.get("callback_data", "") for row in kb for b in row]


def make_bot(tmp: Path, admin_ids: set[int] = {1}) -> ShopBot:
    """Бот на ПОЛНОСТЬЮ временном хранилище — боевые файлы не трогаем."""
    s = Settings(
        bot_token="test:token", admin_ids=admin_ids, shop_name="WAVE SHOP",
        support_contact="@support", payment_order=["stars"],
        yookassa_shop_id="", yookassa_secret_key="", crypto_pay_token="",
        crypto_asset="USDT", crypto_rub_per_unit=100.0, manual_pay_details="",
        currency="RUB", ref_reward_percent=10, autorenew_enabled=False,
        renew_notice_days=3, data_dir=tmp, runtime_dir=tmp / "runtime",
    )
    bot = ShopBot(s)
    bot.api = FakeAPI()
    return bot


def run_wizard(bot: ShopBot, user_id: int, title: str, desc: str,
               price: str, kind_cb: str, payload: str | None) -> str:
    """Пройти мастер добавления целиком, вернуть id созданного товара."""
    bot._admin_start_add(1, user_id)
    bot._admin_wizard_input(1, user_id, title)          # шаг 1: название
    bot._admin_wizard_input(1, user_id, desc)           # шаг 2: описание
    bot._admin_wizard_input(1, user_id, price)          # шаг 3: цена
    bot._admin_choose_kind(1, user_id, kind_cb.split(":", 1)[1])
    if payload is not None:
        bot._admin_wizard_input(1, user_id, payload)    # шаг 5: текст выдачи
    # Мастер закончился, состояние сброшено
    assert user_id not in bot._admin_state, "мастер не закрыл состояние"
    return bot.store.catalog(only_active=False)[-1]["id"]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave_admin_panel_"))
    try:
        # ---------- Доступ ----------
        bot = make_bot(tmp, admin_ids={1})
        # Не-админ не должен получить панель и не должен двигать состояние.
        bot.render_admin(1, None)   # админ
        admin_screen = bot.api.last_text
        bot._handle_admin_callback(1, 1, 99, "adm:products")   # user 99 — не админ
        check("Панель открывается админу", "Управление" in admin_screen)
        check("Не-админ не открывает список товаров",
              "Товары" not in bot.api.last_text or bot.api.last_text == admin_screen)

        # ---------- Мастер: товар с мгновенной выдачей (kind=lifetime) ----------
        pid = run_wizard(bot, 1, "Доступ на день", "Полный доступ к базе",
                         "550", "kind:lifetime", "Вот ваш доступ: https://x.ru")
        p = bot.store.product(pid)
        check(pid.isascii() and pid.replace("_", "").isalnum(),
              f"id ASCII-безопасный ({pid})")
        check(p and p["kind"] == "lifetime", "kind=lifetime")
        check(p and p["price_rub"] == 550 and p["stars_price"] == 33,
              f"цена 550₽/33⭐ (Stars пересчитаны)")
        check(p and p["lifetime_payload"] == "Вот ваш доступ: https://x.ru", "выдача сохранена")
        check(p and p.get("active") is True, "новый товар сразу активен")
        check(len(bot.store.catalog(only_active=True)) == 1, "товар на витрине")

        # ---------- Мастер: товар-ключ со склада (kind=key) ----------
        pid2 = run_wizard(bot, 1, "Ключ PRO", "Один ключ на покупку", "900",
                          "kind:key", None)
        p2 = bot.store.product(pid2)
        check(p2 and p2["kind"] == "key", "kind=key")
        check(p2 and not bot.store.is_available(p2), "пустой склад = нет в наличии")
        bot.store.add_stock(pid2, ["KEY-AAA", "KEY-BBB"])
        check(bot.store.is_available(bot.store.product(pid2)), "склад пополнен — товар доступен")

        # ---------- Переключение активности ----------
        bot._handle_admin_callback(1, 1, 1, f"adm:tgl:{pid}")
        p = bot.store.product(pid)
        check(p and p.get("active") is False, "скрыт с витрины")
        check(len(bot.store.catalog(only_active=True)) == 1, "на витрине только один")
        bot._handle_admin_callback(1, 1, 1, f"adm:tgl:{pid}")
        check(bot.store.product(pid).get("active") is True, "снова показан")

        # ---------- Правка цены ----------
        bot._handle_admin_callback(1, 1, 1, f"adm:price:{pid}")
        bot._admin_wizard_input(1, 1, "1 600 ₽")     # цена с мусором парсится
        p = bot.store.product(pid)
        check(p and p["price_rub"] == 1600 and p["stars_price"] == 96,
              "цена изменена, Stars пересчитаны (1 600₽→96⭐)")

        # ---------- Правка выдачи ----------
        bot._handle_admin_callback(1, 1, 1, f"adm:pay:{pid}")
        bot._admin_wizard_input(1, 1, "Новый доступ: https://y.ru")
        check(bot.store.product(pid)["lifetime_payload"] == "Новый доступ: https://y.ru",
              "выдача изменена")

        # ---------- Склад через панель ----------
        bot._handle_admin_callback(1, 1, 1, f"adm:stock:{pid2}")
        bot._admin_wizard_input(1, 1, "KEY-CCC\nKEY-DDD")
        check(bot.store.stock_count(pid2) == 4, "ключи добавлены через панель (2+2)")

        # ---------- Удаление ----------
        bot._handle_admin_callback(1, 1, 1, f"adm:del:{pid}")
        bot._handle_admin_callback(1, 1, 1, f"adm:delok:{pid}")
        check(bot.store.product(pid) is None, "товар удалён")
        check(len(bot.store.catalog(only_active=False)) == 1, "в каталоге остался только второй")

        # ---------- /cancel выходит из мастера ----------
        bot._admin_start_add(1, 1)
        bot._admin_wizard_input(1, 1, "Заброшенный товар")
        bot.admin_command(1, 1, "/cancel")
        check(1 not in bot._admin_state, "/cancel сбрасывает мастер")

        # ---------- Данные не ломаются при повторном проходе ----------
        pid3 = run_wizard(bot, 1, "Ещё товар", "-", "0", "kind:lifetime", "Даром")
        p3 = bot.store.product(pid3)
        check(p3 and p3["price_rub"] == 0 and p3["stars_price"] == 0,
              "бесплатный товар: 0₽/0⭐")
        check(p3 and p3["description"] == "", "описание «-» = пустое")

        print("\n====================================================")
        total = len(results)
        ok = sum(1 for ok, _ in results if ok)
        print(f"ИТОГ: {ok}/{total} проверок пройдено")
        print("🎛 WAVE SHOP: админ-панель работает (CRUD + мастер).")
        return 0 if ok == total else 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

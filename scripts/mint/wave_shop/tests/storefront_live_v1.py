"""WAVE SHOP — регрессия витрины на НАСТОЯЩЕМ каталоге.

Зачем этот файл существует отдельно от smoke_v1.py:

Магазин был мёртв на 100% — ни у одного из 9 товаров не появлялась кнопка
«Купить», — и при этом ВСЕ 153 теста были зелёными. Причина: остальные тесты
собирают свой временный каталог с kind='key', а боевой data/catalog.json
состоит целиком из kind='gateway'. Проверка наличия считала склад для товаров,
у которых склада нет по устройству, и гасила витрину полностью.

Вывод, ради которого написан тест: витрину нужно проверять на тех данных,
которые увидит покупатель, а не на удобных тестовых. Здесь НИЧЕГО не
подменяется — берётся ровно data/catalog.json из рабочей папки.

Запуск:  python3 tests/storefront_live_v1.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot import ShopBot             # noqa: E402
from config import Settings         # noqa: E402
from store import Store             # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


class FakeAPI:
    """Телеграм-заглушка: запоминает последний показанный экран."""

    def __init__(self) -> None:
        self.last_text = ""
        self.last_kb: list[list[dict]] = []

    def send_message(self, chat_id, text="", kb=None, **kw):
        self.last_text, self.last_kb = text, kb or []
        return {"ok": True, "result": {"message_id": 1}}

    def edit_message_text(self, chat_id, message_id, text="", kb=None, **kw):
        self.last_text, self.last_kb = text, kb or []
        return {"ok": True}

    def answer_callback(self, *a, **kw):
        return {"ok": True}


def buttons(kb: list[list[dict]]) -> list[str]:
    return [b.get("callback_data", "") for row in kb for b in row]


def make_bot(runtime: Path, providers: list[str]) -> ShopBot:
    """Бот на БОЕВОМ каталоге. data_dir = рабочая папка магазина.

    Склад и заказы при этом уводим в temp — тест не должен писать в боевые файлы.
    """
    s = Settings(
        bot_token="test:token", admin_ids={1}, shop_name="WAVE SHOP",
        support_contact="@support", payment_order=providers,
        yookassa_shop_id="", yookassa_secret_key="", crypto_pay_token="",
        crypto_asset="USDT", crypto_rub_per_unit=100.0, manual_pay_details="",
        currency="RUB", ref_reward_percent=10, autorenew_enabled=False,
        renew_notice_days=3, data_dir=ROOT / "data", runtime_dir=runtime,
    )
    bot = ShopBot(s)
    bot.api = FakeAPI()
    # Каталог — боевой (на чтение), всё изменяемое — во временную папку.
    bot.store.orders_path = runtime / "orders.json"
    bot.store.users_path = runtime / "users.json"
    bot.store.ledger_path = runtime / "ledger.json"
    bot.store.subs_path = runtime / "subscriptions.json"
    return bot


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave_storefront_"))
    try:
        # Единственная касса — Stars: она работает на одном токене бота,
        # без ИП, реквизитов и ЮKassa. Это состояние «оператор только запустился».
        bot = make_bot(tmp, ["stars"])
        catalog = bot.store.catalog(only_active=True)

        check(len(catalog) > 0, f"боевой каталог не пуст ({len(catalog)} товаров)")

        # --- ГЛАВНОЕ: у каждого активного товара есть кнопка «Купить» ---
        dead = []
        for p in catalog:
            bot.render_product(chat_id=1, message_id=1, product_id=p["id"])
            if f"buy:{p['id']}" not in buttons(bot.api.last_kb):
                dead.append(p["id"])
        check(not dead, f"кнопка «Купить» есть у всех товаров (мёртвых: {dead or 'нет'})")

        # --- Витрина не помечает живой товар как отсутствующий ---
        bot.render_shop(chat_id=1, message_id=1)
        check("нет в наличии" not in bot.api.last_text.lower(),
              "в списке витрины нет ложной пометки «нет в наличии»")

        # --- Платный товар доводит до кассы (есть хоть одна кнопка оплаты) ---
        paid = [p for p in catalog if int(p.get("price_rub", 0)) > 0]
        no_checkout = []
        for p in paid:
            bot.render_buy(chat_id=1, message_id=1, product_id=p["id"], user_id=1)
            if not any(b.startswith("pay:") for b in buttons(bot.api.last_kb)):
                no_checkout.append(p["id"])
        check(not no_checkout,
              f"платные товары доходят до кассы на одном токене бота "
              f"(без кассы: {no_checkout or 'нет'})")

        # --- Бесплатный товар не идёт через кассу ---
        free = [p for p in catalog if int(p.get("price_rub", 0)) <= 0]
        leaked = []
        for p in free:
            bot.render_buy(chat_id=1, message_id=1, product_id=p["id"], user_id=777001)
            if any(b.startswith("pay:") for b in buttons(bot.api.last_kb)):
                leaked.append(p["id"])
        check(not leaked, f"бесплатный тариф не уходит в кассу (утекло: {leaked or 'нет'})")

        # --- Каталог обещает только те тарифы, которые шлюз умеет выдать ---
        # Иначе клиент платит, а выдача молча возвращает «не удалось выдать ключ».
        try:
            from gateway.quota import get_plan
        except ImportError:
            check(False, "модуль gateway.quota импортируется")
        else:
            broken = [p["id"] for p in catalog
                      if p.get("kind") == "gateway"
                      and not get_plan(p.get("plan_id", p["id"]))]
            check(not broken,
                  f"у каждого тарифа шлюза есть план выдачи (битых: {broken or 'нет'})")

        # --- Контроль от обратной ошибки: «в наличии» не должно стать всегда ---
        # Товар со складом при пустом складе обязан остаться недоступным,
        # иначе починка превратилась бы в продажу воздуха.
        store = Store(tmp)
        store.upsert_product({"id": "phys", "title": "Со складом", "description": "",
                              "price_rub": 100, "stars_price": 6, "kind": "key",
                              "active": True})
        check(not store.is_available(store.product("phys")),
              "товар kind='key' при пустом складе остаётся недоступен")
        store.add_stock("phys", ["KEY-1"])
        check(store.is_available(store.product("phys")),
              "тот же товар становится доступен после пополнения склада")

        # --- Итог ---
        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        print(f"\n{'='*46}\nИТОГ: {passed}/{total} проверок пройдено")
        if passed == total:
            print("🛍 ВИТРИНА: боевой каталог покупаем целиком.")
            return 0
        print("Витрина мертва или частично мертва — смотрите выше.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

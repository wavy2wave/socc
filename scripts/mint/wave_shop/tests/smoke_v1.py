"""WAVE SHOP — smoke-тест: весь путь покупки БЕЗ сети и без Telegram.

Проверяет то, что реально ломается: выдачу со склада, идемпотентность,
пустой склад, вечный доступ, реф-начисление с реальной покупки, LEDGER.

Запуск:  python3 tests/smoke_v1.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import ShopCore          # noqa: E402
from config import Settings       # noqa: E402
from store import Store           # noqa: E402
from payments.providers import build_providers, StarsProvider  # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


def make_settings(tmp: Path) -> Settings:
    return Settings(
        bot_token="test:token", admin_ids={1}, shop_name="WAVE SHOP",
        support_contact="@support", payment_order=["stars"],
        yookassa_shop_id="", yookassa_secret_key="", crypto_pay_token="",
        crypto_asset="USDT", crypto_rub_per_unit=100.0, manual_pay_details="",
        currency="RUB", ref_reward_percent=10, autorenew_enabled=False,
        renew_notice_days=3, data_dir=tmp, runtime_dir=tmp,
    )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave_shop_test_"))
    try:
        s = make_settings(tmp)
        store = Store(tmp)
        core = ShopCore(store, s)

        # --- Каталог и склад ---
        store.upsert_product({"id": "k1", "title": "Ключ", "description": "тест",
                              "price_rub": 500, "stars_price": 30, "kind": "key", "active": True})
        store.upsert_product({"id": "life", "title": "Вечный", "description": "тест",
                              "price_rub": 2500, "stars_price": 150, "kind": "lifetime",
                              "lifetime_payload": "ВЕЧНЫЙ-ДОСТУП-ОК", "active": True})
        check(len(store.catalog()) == 2, "каталог: 2 товара активны")

        store.add_stock("k1", ["KEY-A", "KEY-B"])
        check(store.stock_count("k1") == 2, "склад: 2 ключа загружено")

        # --- Пользователи и рефералы ---
        inviter = store.get_or_create_user(100, "inviter")
        ref_code = inviter["ref_code"]
        buyer = store.get_or_create_user(200, "buyer", ref_by=ref_code)
        check(buyer["ref_by"] == ref_code, "реферал: покупатель привязан к пригласившему")
        check(store.ref_stats(ref_code)["invited"] == 1, "реферал: счётчик приглашённых = 1")

        # --- Покупка ключа + выдача ---
        order = store.create_order(200, "k1", "stars", 500, ref_by=ref_code)
        core.mark_paid(order["order_id"])
        ok, payload = core.deliver(order["order_id"])
        check(ok and payload == "KEY-A", f"выдача: получен первый ключ со склада ({payload})")
        check(store.stock_count("k1") == 1, "склад: списан 1 ключ (осталось 1)")

        # --- Идемпотентность: повторная выдача не списывает второй ключ ---
        ok2, payload2 = core.deliver(order["order_id"])
        check(ok2 and payload2 == "KEY-A", "идемпотентность: повторная выдача = тот же ключ")
        check(store.stock_count("k1") == 1, "идемпотентность: склад НЕ списан повторно")

        # --- Повторный mark_paid НЕ откатывает выданный заказ ---
        # Telegram может прислать successful_payment дважды, /confirm — нажаться
        # повторно. mark_paid обязан НЕ затирать 'delivered', иначе страж
        # идемпотентности слепнет и заказ выдаётся второй раз.
        core.mark_paid(order["order_id"])
        check(store.get_order(order["order_id"])["status"] == "delivered",
              "повторный mark_paid не сбросил статус выданного заказа")
        ok_re, payload_re = core.deliver(order["order_id"])
        check(ok_re and payload_re == "KEY-A" and store.stock_count("k1") == 1,
              "после повторной оплаты склад НЕ списан в третий раз")
        rev_after = store.revenue_total()
        check(rev_after["orders"] == 1,
              f"повторная оплата не задвоила выручку (продаж {rev_after['orders']})")

        # --- Реферальная награда с реальной покупки (10% от 500 = 50) ---
        stats = store.ref_stats(ref_code)
        check(stats["balance"] == 50, f"реферал: начислено 10% = 50 ₽ (факт {stats['balance']})")

        # --- LEDGER ---
        rev = store.revenue_total()
        check(rev["orders"] == 1 and rev["rub_total"] == 500,
              f"LEDGER: 1 продажа на 500 ₽ (факт {rev})")

        # --- Вечный доступ (склад не нужен) ---
        o2 = store.create_order(200, "life", "stars", 2500, ref_by=ref_code)
        core.mark_paid(o2["order_id"])
        ok3, payload3 = core.deliver(o2["order_id"])
        check(ok3 and payload3 == "ВЕЧНЫЙ-ДОСТУП-ОК", "lifetime: выдан вечный доступ без склада")

        # --- Пустой склад: честный отказ, а не выдача пустоты ---
        store.pop_stock("k1")  # опустошаем
        o3 = store.create_order(300, "k1", "stars", 500)
        core.mark_paid(o3["order_id"])
        ok4, msg4 = core.deliver(o3["order_id"])
        check(not ok4 and "закончился" in msg4, "пустой склад: честный отказ, деньги не съедены")

        # --- Провайдеры: только сконфигурированные ---
        provs = build_providers(s)
        check(list(provs) == ["stars"], f"кассы: включён только stars (факт {list(provs)})")
        charge = StarsProvider().create_charge({"amount_rub": 500}, {"stars_price": 30})
        check(charge.ok and charge.stars_amount == 30, "Stars: инвойс на 30 ⭐ готов")

        # --- Итог ---
        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        print(f"\n{'='*46}\nИТОГ: {passed}/{total} проверок пройдено")
        if passed == total:
            print("🌊 WAVE SHOP: путь покупки работает end-to-end.")
            return 0
        print("Есть красные проверки — смотрите выше.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

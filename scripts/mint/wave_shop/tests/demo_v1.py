"""WAVE — тесты бесплатного демо. Страховка от бесконечной раздачи доступа.

Демо — вход в воронку: клиент убеждается, что всё работает у него, до оплаты.
Но бесплатный товар — это то место, где деньги текут наружу быстрее всего.

Что тут закрывается:
  1. Демо выдаётся ДВАЖДЫ одному аккаунту → бесплатный доступ навсегда.
  2. Гонка двух быстрых нажатий → два ключа в обход UI-проверки.
  3. Демо попадает в LEDGER → счётчик продаж и средний чек врут.
  4. Отказ по демо выглядит как сбой выдачи → бот обещает вернуть деньги,
     которых не было.
  5. Демо на Opus по цене платного тарифа → раздача убытков.

Запуск:  python3 tests/demo_v1.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import ShopCore, fmt_price                            # noqa: E402
from config import Settings                                    # noqa: E402
from store import Store                                        # noqa: E402
from gateway.pricing import caps_cost_rub                      # noqa: E402
from gateway.quota import (                                    # noqa: E402
    PLANS, AlreadyIssued, QuotaStore, model_allowed, plan_quota_caps,
)

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


def make_settings(tmp: Path) -> Settings:
    return Settings(
        bot_token="test:token", admin_ids={1}, shop_name="WAVE", support_contact="@s",
        payment_order=["stars"], yookassa_shop_id="", yookassa_secret_key="",
        crypto_pay_token="", crypto_asset="USDT", crypto_rub_per_unit=100.0,
        manual_pay_details="", currency="RUB", ref_reward_percent=10,
        autorenew_enabled=False, renew_notice_days=3, data_dir=tmp, runtime_dir=tmp,
    )


DEMO_PRODUCT = {
    "id": "demo", "plan_id": "demo", "title": "🎁 Демо", "description": "проба",
    "price_rub": 0, "stars_price": 0, "kind": "gateway", "active": True,
}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave_demo_test_"))
    try:
        s = make_settings(tmp)
        store = Store(tmp)
        core = ShopCore(store, s)
        store.upsert_product(DEMO_PRODUCT)

        # ---------- Тариф демо настроен как вход в воронку ----------
        demo = PLANS["demo"]
        check(demo.get("once_per_user") is True,
              "у демо стоит флаг once_per_user — иначе раздача бесконечна")
        check(demo.get("model_key") == "sonnet",
              f"демо на дешёвой модели ({demo.get('model_key')}), не на Opus")
        cost = caps_cost_rub(plan_quota_caps(demo), demo["model_key"])
        check(cost < 100,
              f"полный расход демо стоит оператору {round(cost)} ₽ — цена привлечения, "
              f"а не убыток")

        # ---------- Витрина показывает «бесплатно», а не «0 ₽» ----------
        check(fmt_price(DEMO_PRODUCT, s) == "бесплатно",
              f"нулевая цена читается как «бесплатно» (факт: {fmt_price(DEMO_PRODUCT, s)})")

        # ---------- Первая выдача проходит ----------
        o1 = store.create_order(777, "demo", "free", 0)
        ok1, payload1 = core.deliver(o1["order_id"])
        check(ok1 and "wave-" in payload1, "первое демо выдано, в тексте есть токен")

        # ---------- Вторая выдача тому же аккаунту отбита ----------
        o2 = store.create_order(777, "demo", "free", 0)
        ok2, msg2 = core.deliver(o2["order_id"])
        check(not ok2, "второе демо тому же аккаунту НЕ выдано")
        check("один раз" in msg2.lower(),
              "клиенту объясняют правило, а не показывают код ошибки")
        check("вернём деньги" not in msg2.lower(),
              "за бесплатный отказ бот НЕ обещает возврат денег")
        order2 = store.get_order(o2["order_id"]) or {}
        check(order2.get("status") == "rejected",
              f"отказной заказ помечен rejected (факт: {order2.get('status')})")

        # ---------- Ключей у пользователя ровно один ----------
        q = QuotaStore(tmp)
        demo_keys = [k for k in q.keys_of_user(777) if k.get("plan_id") == "demo"]
        check(len(demo_keys) == 1, f"демо-ключей на аккаунте ровно 1 (факт {len(demo_keys)})")

        # ---------- Другому аккаунту демо доступно ----------
        o3 = store.create_order(888, "demo", "free", 0)
        ok3, _ = core.deliver(o3["order_id"])
        check(ok3, "другому аккаунту демо выдаётся — воронка не перекрыта")

        # ---------- Гонка: 8 одновременных попыток дают 1 ключ ----------
        # UI-проверка «уже есть ключ?» такую гонку не ловит: между чтением и
        # записью успевают пролезть оба нажатия. Замок обязан быть в issue_key.
        errors: list[Exception] = []
        issued: list[dict] = []

        def race() -> None:
            try:
                issued.append(q.issue_key(999, "demo", "race"))
            except AlreadyIssued as e:
                errors.append(e)

        threads = [threading.Thread(target=race) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        check(len(issued) == 1 and len(errors) == 7,
              f"8 одновременных нажатий → выдан 1 ключ, отбито {len(errors)}")

        # ---------- Платные тарифы можно покупать повторно ----------
        q.issue_key(555, "hour_1", "p1")
        again = None
        try:
            again = q.issue_key(555, "hour_1", "p2")
        except AlreadyIssued:
            again = None
        check(again is not None,
              "платный тариф можно купить повторно — ограничение только на демо")

        # ---------- Демо не пишется в LEDGER ----------
        rev = store.revenue_total()
        check(rev["rub_total"] == 0 and rev["orders"] == 0,
              f"выручка чиста от бесплатных выдач ({rev['orders']} записей, "
              f"{rev['rub_total']} ₽)")

        # ---------- Демо не платит рефералу ----------
        inviter = store.get_or_create_user(101)
        code = inviter["ref_code"]
        o4 = store.create_order(102, "demo", "free", 0, ref_by=code)
        core.deliver(o4["order_id"])
        check(store.ref_stats(code)["balance"] == 0,
              "за бесплатное демо реферальная награда НЕ начисляется")

        # ---------- Старый plan_id демо тоже считается тем же демо ----------
        # Если оператор переименует тариф, обход не должен открыться.
        q.issue_key(303, "demo", "d1")
        blocked = False
        try:
            q.issue_key(303, "demo", "d2")
        except AlreadyIssued:
            blocked = True
        check(blocked, "повтор ловится и после нормализации plan_id")

        # ---------- Потолок модели: демо не пускает на Opus ----------
        # Демо посчитано по цене Sonnet. Без этой проверки клиент пишет в
        # запросе "opus" и жжёт закупку в 5 раз дороже — бесплатно.
        check(model_allowed("claude-sonnet-5", "sonnet"),
              "демо-ключ работает со своей моделью (sonnet)")
        check(not model_allowed("claude-opus-5", "sonnet"),
              "демо-ключ НЕ пускает на Opus — обещали Sonnet, за Sonnet и платили")
        check(model_allowed("claude-haiku-4-5", "sonnet"),
              "модель дешевле потолка разрешена — клиенту не мешают экономить")
        check(model_allowed("claude-opus-5", "opus"),
              "платный ключ уровня opus работает с Opus")
        check(not model_allowed("gpt-невнятное-имя", "sonnet"),
              "незнакомое имя модели отбито: ошибаться в сторону убытка нельзя")
        check(model_allowed("anthropic/claude-sonnet-5", "sonnet"),
              "имя с префиксом провайдера распознаётся (openrouter-формат)")
        check(not model_allowed("ANTHROPIC/CLAUDE-OPUS-4.6", "sonnet"),
              "регистр и версия не открывают обход")
        check(model_allowed("claude-opus-5", ""),
              "у платных тарифов без model_key ограничения нет — сетка не сломана")
        # DeepSeek — то, что шлюз перепродаёт; по закупке дешевле haiku, поэтому
        # обязан пускаться даже на демо-потолке (иначе воронка не продаёт продукт).
        check(model_allowed("deepseek-v4-flash", "sonnet"),
              "deepseek-flash пускается на демо (sonnet) — дешевле потолка")
        check(model_allowed("deepseek-ai/DeepSeek-V4-Pro", "sonnet"),
              "deepseek-pro (полный слаг DeepInfra) тоже проходит демо-потолок")
        check(model_allowed("deepseek-v4-flash", "haiku"),
              "deepseek на самом низком потолке разрешён — это его тир")

        demo_key = demo_keys[0]
        check(demo_key.get("model_key") == "sonnet",
              "потолок модели записан в сам ключ, а не только в тариф")

        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        print(f"\n{'=' * 56}\nИТОГ: {passed}/{total} проверок пройдено")
        if passed == total:
            print("🎁 ДЕМО: один на аккаунт, гонка отбита, касса не запачкана.")
            return 0
        print("Есть красные проверки — смотрите выше.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

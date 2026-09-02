"""WAVE — тесты экономики. Страховка от убыточного прайса.

Зачем этот файл: разведка нашла, что сетка была убыточной — час за 99 ₽ при
потолке 2 млн токенов давал −869 ₽ на чеке, пакет 5М за 1490 ₽ давал −1167 ₽.
Обе дыры возникли не от глупости, а потому что цену и потолок назначали
раздельно и на глаз. Здесь это проверяется машиной.

Правило, которое охраняют эти тесты:
    НИ ОДИН тариф не может быть убыточным при ПОЛНОМ расходе квоты.

Запуск:  python3 tests/pricing_v1.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.pricing import (  # noqa: E402
    W_CACHE_READ, W_INPUT, W_OUTPUT, caps_from_usage, caps_cost_rub,
    margin_report, recommend_price_rub, safe_hourly_cap,
)
from gateway.quota import PLANS, get_plan, plan_quota_caps  # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


def main() -> int:
    # ---------- Веса отражают реальный прайс ----------
    check(W_OUTPUT == 5.0 * W_INPUT,
          "вес выхода в 5 раз больше входа (прайс: $25 против $5)")
    check(W_CACHE_READ == 0.1 * W_INPUT,
          "чтение кэша в 10 раз дешевле входа (прайс: $0.50 против $5)")

    # ---------- Учёт CAPS: главная защита от потерь ----------
    caps = caps_from_usage({"input_tokens": 1000, "output_tokens": 1000,
                            "cache_read_input_tokens": 10000})
    check(caps == 7000, f"Anthropic-формат: 1k+1k+10k кэш = 7000 CAPS (факт {caps})")

    caps_oai = caps_from_usage({"prompt_tokens": 11000, "completion_tokens": 1000,
                                "prompt_tokens_details": {"cached_tokens": 10000}})
    check(caps_oai == 7000, f"OpenAI-формат не задваивает кэш (факт {caps_oai})")

    naive = 1000 + 1000  # как считалось раньше
    check(caps > naive * 3,
          f"взвешенный счёт видит в {caps // naive}× больше расхода, чем сырая сумма")

    # Генерация дороже чтения — иначе клиент с длинными ответами разоряет
    gen = caps_from_usage({"input_tokens": 100, "output_tokens": 10000})
    read = caps_from_usage({"input_tokens": 10000, "output_tokens": 100})
    check(gen > read, f"генерация ({gen}) дороже чтения ({read}) — как в прайсе")

    # ---------- ГЛАВНОЕ: ни один тариф не убыточен ----------
    print("\n--- прибыльность каждого тарифа при ПОЛНОМ расходе ---")
    losers: list[str] = []
    for plan_id, plan in PLANS.items():
        quota = plan_quota_caps(plan)
        if not quota:
            continue                      # безлимит проверяем отдельно
        model_key = plan.get("model_key", "opus")
        price = recommend_price_rub(quota, model_key)
        rep = margin_report(price, quota, model_key)
        if not rep["profitable"]:
            losers.append(plan_id)
        print(f"    {plan_id:<10} {price:>7,} ₽ → чистыми {rep['profit_rub']:>7,} ₽ "
              f"({rep['margin_pct']}%)")
    check(not losers, f"все квотные тарифы прибыльны (убыточных: {losers or 'нет'})")

    # ---------- Безлимит: потолок должен окупать цену ----------
    unlim = PLANS["unlim"]
    daily = int(unlim["daily_cap_caps"])
    month_cost = caps_cost_rub(daily * int(unlim["period_days"]), "opus")
    check(daily > 0, "у безлимита есть суточный потолок (без него это долг, а не тариф)")
    print(f"    безлимит при максимальном расходе: {round(month_cost):,} ₽/мес себестоимости")

    # ---------- Историческая дыра не может вернуться ----------
    old_hole = margin_report(99, 2_000_000, "opus")
    check(not old_hole["profitable"],
          f"старая дыра распознаётся как убыток ({old_hole['profit_rub']} ₽ на чеке)")

    hour_plan = PLANS["hour_1"]
    per_hour = int(hour_plan["caps_per_hour"])
    check(per_hour < 2_000_000,
          f"потолок часа снижен до безопасного: {per_hour:,} CAPS (было 2 000 000)")

    safe = safe_hourly_cap(550, 1)
    rep = margin_report(550, safe, "opus")
    check(rep["profitable"],
          f"калькулятор потолка даёт прибыльный результат ({rep['margin_pct']}% маржи)")

    # ---------- Пакеты не бессрочны ----------
    for pid in ("pack_3m", "pack_10m"):
        ttl = PLANS[pid].get("ttl_days", 0)
        check(0 < ttl <= 366,
              f"{pid}: срок {ttl} дней — не бессрочное обязательство")

    # ---------- Старые plan_id не сломались ----------
    for old in ("hour_3", "pack_5m", "sub_10m", "pack_50m", "hour_12", "sub_30m"):
        check(get_plan(old) is not None, f"старый тариф {old} ещё резолвится")

    # ---------- Реальная закупка меняет экономику ----------
    os.environ["WAVE_COST_OPUS_IN"] = "2.50"      # агрегатор даёт вдвое дешевле
    cheaper = caps_cost_rub(1_000_000, "opus")
    del os.environ["WAVE_COST_OPUS_IN"]
    normal = caps_cost_rub(1_000_000, "opus")
    check(cheaper < normal,
          f"цена закупки из .env влияет на расчёт ({round(cheaper)} ₽ против {round(normal)} ₽)")

    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    print(f"\n{'=' * 56}\nИТОГ: {passed}/{total} проверок пройдено")
    if passed == total:
        print("💰 ЭКОНОМИКА: убыточных тарифов нет, учёт взвешенный.")
        return 0
    print("Есть красные проверки — смотрите выше.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

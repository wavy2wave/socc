#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА ЯНДЕКС — РОЛЬ КАТЕГОРИЙЩИК (YM_CATEGORIST).

Фальсифицируемо: каждый тест ловит конкретное нарушение закона роли.
  • Если роль возьмёт донорскую «Цену» как цену продажи (а не закупку) → FAIL (C1).
  • Если предложит цену «из файла» вместо cost×наценки → FAIL (C2).
  • Если выдумает габариты, которых нет → FAIL (C3).
  • Если пропустит закупку дороже порога → FAIL (C4).
  • Если оставит в шорт-листе позицию, где ни одна наценка не бьёт пол маржи → FAIL (C5).

ЧИСТАЯ ЛОГИКА: тест НЕ трогает донор-читатель (openpyxl) — только score/rank/propose/reconcile.
Поэтому идёт зелёным под любым интерпретатором регрессии (3.13 без openpyxl).

Запуск: python3 tests/run_yandex_categorist.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_role_categorist_v1 as cat            # noqa: E402
import ymarket_role_pricer_v1 as pricer             # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))


# Реалистичная позиция короба: настоящие габариты посылки (см) + вес, дешёвая закупка.
def box(cost=50.0, sku="B1", name="Короб для переезда", cat_id=76346336):
    return {
        "sku": sku, "name": name, "cost": cost,
        "length": 33.0, "width": 23.0, "height": 23.0, "weight": 0.276,
        "category_id": cat_id, "slug": "korob", "stock_source": "donor:в наличии",
        "pictures": ["https://cdn.example/box.jpg"],
    }


print("ПРИЁМКА ЯНДЕКС — КАТЕГОРИЙЩИК\n")

# ============================================================================
# C1 — донорская «Цена» = НАША закупка, не цена продажи
# ============================================================================
print("C1 · донорская цена трактуется как закупка (дропшип)")

r = cat.score_item(box(cost=60.0), city="москва")
check("C1: cost прошёл в разбор как закупка", r["cost"] == 60.0, str(r["cost"]))
check("C1: предложенная цена продажи = закупка×наценка, НЕ равна закупке",
      r["proposed_low"] == 60.0 * cat.DEFAULT_MARKUP_LO, str(r["proposed_low"]))
check("C1: без закупки → needs_data (нечего предлагать)",
      cat.score_item({"sku": "X", "name": "нечто"}, city="москва")["verdict"] == "needs_data")

# ============================================================================
# C2 — цену продажи ПРЕДЛАГАЕМ (×наценка), не читаем из файла
# ============================================================================
print("\nC2 · цена продажи — предложение, помечена как таковая")

lo, hi = cat.propose_prices(100.0, 5.0, 10.0)
check("C2: propose_prices(100, ×5–10) = (500, 1000)", (lo, hi) == (500.0, 1000.0), f"{lo},{hi}")
check("C2: нет закупки → (None,None), цену не выдумываем", cat.propose_prices(0) == (None, None))
check("C2: разбор помечает price_is_proposal=True", r["price_is_proposal"] is True)
check("C2: proposed_high = закупка×верхняя наценка",
      r["proposed_high"] == 60.0 * cat.DEFAULT_MARKUP_HI, str(r["proposed_high"]))

# ============================================================================
# C3 — нет габаритов/веса → needs_data, размеры не выдумываем
# ============================================================================
print("\nC3 · без габаритов — needs_data, не выдумываем")

no_dims = box(cost=60.0)
for k in ("length", "width", "height"):
    no_dims.pop(k, None)
rd = cat.score_item(no_dims, city="москва")
check("C3: короб без габаритов → не select", rd["verdict"] != "select", rd["verdict"])
check("C3: причина ссылается на данные (T5/габарит)",
      any(("T5" in x) or ("габарит" in x.lower()) for x in rd["reasons"]),
      "; ".join(rd["reasons"]))

# вес: реконсиляция единиц (живой урок — «Вес, кг»=276 это граммы)
wkg, src = cat.resolve_weight_kg(None, 276)
check("C3/вес: 276 в «кг» неправдоподобно → трактуем как граммы 0.276кг",
      wkg == 0.276 and src == "kg_col_reconciled_grams", f"{wkg},{src}")
wkg2, src2 = cat.resolve_weight_kg(276, None)
check("C3/вес: явная колонка «г»=276 → 0.276кг, source=grams_col",
      wkg2 == 0.276 and src2 == "grams_col", f"{wkg2},{src2}")
wkg3, src3 = cat.resolve_weight_kg(None, 1.5)
check("C3/вес: правдоподобные 1.5кг остаются как есть", wkg3 == 1.5 and src3 == "kg_col")
wkg4, src4 = cat.resolve_weight_kg(None, None)
check("C3/вес: нет чисел → (None, unknown), не выдумываем", wkg4 is None and src4 == "unknown")

# ============================================================================
# C4 — закупка дороже порога → отбой
# ============================================================================
print("\nC4 · закупка выше порога — отбой (врываемся дёшево)")

expensive = cat.score_item(box(cost=900.0), city="москва", max_cost=700.0)
check("C4: закупка 900 > порога 700 → reject", expensive["verdict"] == "reject", expensive["verdict"])
check("C4: причина называет порог", any("C4" in x for x in expensive["reasons"]))
cheap = cat.score_item(box(cost=699.0), city="москва", max_cost=700.0)
check("C4: закупка 699 ≤ порога 700 → не отсекается по C4",
      not any("C4" in x for x in cheap["reasons"]))

# ============================================================================
# C5 — ни одна наценка не бьёт пол маржи → отбой
# ============================================================================
print("\nC5 · наценка ниже пола маржи — отбой")

# Пол маржи ЦЕНОВИКА проверяется на КОНСЕРВАТИВНОМ конце (×markup_lo).
# markup_lo=1.0 при закупке 60 → цена=60, но пол = 60+сборы+30 > 60 → reject.
tight = cat.score_item(box(cost=60.0), city="москва", markup_lo=1.0, markup_hi=1.2)
check("C5: наценка ×1.0 (цена=закупке) не бьёт пол → не select", tight["verdict"] != "select", tight["verdict"])

be = cat.breakeven_markup(cost=100.0, fee=50.0, min_profit=30.0)
check("C5: breakeven_markup(100, fee 50, min 30) = (100+50+30)/100 = 1.8", be == 1.8, str(be))
check("C5: без закупки breakeven=None", cat.breakeven_markup(0, 50) is None)
check("C5: без сборов breakeven=None (не считаем на выдуманном)", cat.breakeven_markup(100, None) is None)

# ============================================================================
# select — прибыльный короб проходит целиком
# ============================================================================
print("\nselect · прибыльный короб проходит и попадает в шорт-лист")

good = cat.score_item(box(cost=50.0), city="москва", markup_lo=5.0, markup_hi=10.0)
check("select: дешёвый короб с габаритами и категорией → select", good["verdict"] == "select", good["verdict"])
check("select: есть экономика с прибылью", isinstance((good.get("economics") or {}).get("profit"), (int, float)))
check("select: why человекочитаемо (купить→продать)", "купить" in good["why"] and "продать" in good["why"])

# ============================================================================
# rank — сортировка по прибыли, только select
# ============================================================================
print("\nrank · ранжирование по прибыли, tiebreak меньшая закупка")

scored = [
    cat.score_item(box(cost=50.0, sku="A"), city="москва"),
    cat.score_item(box(cost=100.0, sku="B"), city="москва"),
    cat.score_item(box(cost=900.0, sku="C"), city="москва", max_cost=700.0),  # reject
    cat.score_item({"sku": "D", "name": "нет данных"}, city="москва"),         # needs_data
]
ranked = cat.rank(scored)
check("rank: в ранжирование попали только select", all(r["verdict"] == "select" for r in ranked))
check("rank: reject/needs_data отфильтрованы", len(ranked) == 2, str(len(ranked)))
profits = [(r["economics"] or {}).get("profit", 0) for r in ranked]
check("rank: отсортировано по убыванию прибыли", profits == sorted(profits, reverse=True), str(profits))

# ============================================================================
# КАНОН — роль соответствует шаблону SOCC (8 полей)
# ============================================================================
print("\nКАНОН · КАТЕГОРИЙЩИК соответствует шаблону SOCC")

C = cat.CHARTER
check("КАНОН: id = YM_CATEGORIST", C.get("id") == "YM_CATEGORIST")
check("КАНОН: name_ru присутствует", bool(C.get("name_ru")))
check("КАНОН: mandate присутствует", bool(C.get("mandate")))
check("КАНОН: owns — непустой список", isinstance(C.get("owns"), list) and bool(C["owns"]))
check("КАНОН: laws — непустой список (C1..C5)", isinstance(C.get("laws"), list) and len(C["laws"]) >= 5)
check("КАНОН: kpi — список", isinstance(C.get("kpi"), list) and bool(C["kpi"]))
check("КАНОН: proves_by — строка", isinstance(C.get("proves_by"), str) and bool(C["proves_by"]))
for k in C["kpi"]:
    check(f"КАНОН KPI '{k.get('metric')}': source_of_truth есть", bool(k.get("source_of_truth")))

# ============================================================================
# ИТОГ
# ============================================================================
print("\n" + "=" * 70)
print(f"ЯНДЕКС КАТЕГОРИЙЩИК: {len(PASS)}/{len(PASS) + len(FAIL)} зелёных")
if FAIL:
    print("КРАСНЫЕ:")
    for f in FAIL:
        print(f"  ❌ {f}")
    sys.exit(1)
print("✅ КАТЕГОРИЙЩИК честен: закупка≠продажа, цена предложена, данные не выдуманы, пол маржи держится")

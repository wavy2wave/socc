#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — ЦЕНОВИК·ПЛАН (ymarket_pricing_plan_v1). Сухо, 0₽, чистая математика над price_rules.

Проверяем ЗАКОНЫ формы плана переценки, а не «запустилось»: разбор ПО КАРТОЧКЕ (offer_id +
закупка + действующая + что поставить + якорь), provisional-честность (не подтверждённые
доставка/комиссия = совет, не приказ), сортировка «что чинить сначала», якорь всегда выше
рекомендованной. Эталон вердиктов — живая плёночная партия 2026-09-02 (закупка = скан донора,
витрина = чтение). Никакой сети и записи.

  PP1  empty_plan             — plan_cards([]) → [] без падения
  PP2  ok_card_in_zone        — цена в зоне → OK, рекомендую == цена, gap == 0
  PP3  raise_below_floor      — цена ниже пола КПИ → RAISE, рекомендую ≥ пола
  PP4  sweet_below_zone       — прибыльно, но ниже сладкой зоны → SWEET, рекомендую в зоне
  PP5  no_cost_honest         — без закупки → NO_COST, рекомендации НЕТ (не выдумываем)
  PP6  provisional_flag       — без явных delivery/fee → provisional=True; с явными → False
  PP7  crossed_above_recommended — якорь ВСЕГДА > рекомендованной (нет фальшивой скидки)
  PP8  urgent_first           — сортировка: RAISE перед SWEET перед OK
  PP9  real_film_2026-09-02   — живая партия 4 ARB → ровно те вердикты, что видел оператор
  PP10 summary_counts         — сводка считает строки/вердикты/provisional
  PP11 render_human           — таблица содержит offer_id+вердикт и баннер provisional; пусто → []
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_pricing_plan_v1 as P   # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


# Живая партия 2026-09-02 16:40 (закупка = живой скан донора, витрина = чтение campaign_offers).
_FILM = [
    {"offer_id": "ARB-87309612", "cost": 700.0, "price": 5600},   # 700×8, в зоне
    {"offer_id": "ARB-29846713", "cost": 600.0, "price": 4800},   # 600×8, в зоне
    {"offer_id": "ARB-53416854", "cost": 170.0, "price": 1360},   # ×8, чуть ниже зоны → SWEET
    {"offer_id": "ARB-87931769", "cost": 65.0, "price": 520},     # net 177 < КПИ → RAISE
]


def _row(cards, oid):
    return next(x for x in P.plan_cards(cards) if x["offer_id"] == oid)


def pp1_empty_plan():
    rows = P.plan_cards([])
    ok = rows == [] and P.summary(rows)["rows"] == 0
    return ok, "plan_cards([]) → [] · summary.rows=0"


def pp2_ok_card_in_zone():
    x = _row(_FILM, "ARB-87309612")
    ok = (x["verdict"] == "OK" and x["recommended"] == 5600 and x["gap"] == 0.0
          and x["net"] is not None and x["net"] > 0)
    return ok, f"verdict={x['verdict']} рекомендую={x['recommended']} gap={x['gap']} net={x['net']}"


def pp3_raise_below_floor():
    x = _row(_FILM, "ARB-87931769")
    ok = (x["verdict"] == "RAISE" and x["recommended"] is not None
          and x["recommended"] >= x["floor"] and x["gap"] > 0)
    return ok, (f"verdict={x['verdict']} пол={x['floor']} рекомендую={x['recommended']} "
                f"gap=+{x['gap']} net={x['net']} (net<КПИ → честный подъём до пола)")


def pp4_sweet_below_zone():
    x = _row(_FILM, "ARB-53416854")
    z = x["zone"]
    ok = (x["verdict"] == "SWEET" and z.get("low") is not None
          and z["low"] <= x["recommended"] <= z["high"] and x["gap"] > 0)
    return ok, (f"verdict={x['verdict']} зона={z.get('low')}–{z.get('high')} "
                f"рекомендую={x['recommended']} (подъём в сладкую зону)")


def pp5_no_cost_honest():
    rows = P.plan_cards([{"offer_id": "ARB-X", "price": 1000}])
    ok = (len(rows) == 1 and rows[0]["verdict"] == "NO_COST"
          and rows[0]["recommended"] is None)
    return ok, f"без закупки → {rows[0]['verdict']}, рекомендации нет (PP4: не выдумываем)"


def pp6_provisional_flag():
    r1 = P.plan_cards(_FILM)
    r2 = P.plan_cards(_FILM, delivery=200.0, fee=0.15)
    ok = (all(x["provisional"] for x in r1)
          and all(not x["provisional"] for x in r2))
    return ok, (f"без параметров: provisional={r1[0]['provisional']}; "
                f"с явными delivery/fee: provisional={r2[0]['provisional']}")


def pp7_crossed_above_recommended():
    rows = P.plan_cards(_FILM)
    ok = all(x.get("crossed") is not None and x["crossed"] > x["recommended"] for x in rows)
    return ok, f"якорь > рекомендованной на всех {len(rows)} (нет фальшивой скидки, PP6)"


def pp8_urgent_first():
    rows = P.plan_cards(_FILM)
    order = [x["verdict"] for x in rows]
    ok = order[0] == "RAISE" and order[1] == "SWEET" and order[2:] == ["OK", "OK"]
    return ok, f"порядок главности: {order} (чинить → держать)"


def pp9_real_film_2026_09_02():
    rows = P.plan_cards(_FILM)
    got = {x["offer_id"]: x["verdict"] for x in rows}
    want = {"ARB-87309612": "OK", "ARB-29846713": "OK",
            "ARB-53416854": "SWEET", "ARB-87931769": "RAISE"}
    ok = got == want
    return ok, f"живая партия → {got} (совпадает с леджером 16:40: RAISE+SWEET, 2/4 в зоне)"


def pp10_summary_counts():
    s = P.summary(P.plan_cards(_FILM))
    ok = (s["rows"] == 4 and s["by_verdict"] == {"OK": 2, "SWEET": 1, "RAISE": 1}
          and s["urgent"] == {"RAISE": 1, "SWEET": 1} and s["provisional"] is True)
    return ok, f"summary={s} (2 держим, 2 чинить, всё provisional)"


def pp11_render_human():
    lines = P.render_plan(P.plan_cards(_FILM))
    txt = "\n".join(lines)
    ok = (any("ARB-87931769" in l for l in lines)
          and any("RAISE" in l for l in lines)
          and "ПРОЕКТ" in txt and "не приказ" in txt
          and P.render_plan([]) == [])
    return ok, f"таблица {len(lines)} строк · баннер ПРОЕКТ есть · пустой план → []"


# ── СЛОЙ «АКЦИИ» (PR12–PR17): решение {sku, value, discount_base}, ничего не пишет ──

def pr12_promo_ok_payload():
    """PR1/PR3: акция со снижением с реальной витринной → OK + готовый payload для trade."""
    card = next(c for c in _FILM if c["offer_id"] == "ARB-29846713")
    r = P.promo_card(card, sell=4200)          # regular умолч. = действующая витринная 4800 (PR2)
    ok = (r["ok"] and r["verdict"] == "OK" and r["discount_pct"] == 12.5
          and r["payload"] == {"sku": "ARB-29846713", "value": 4200.0,
                               "discount_base": 4800.0})
    return ok, (f"verdict={r['verdict']} скидка {r['discount_pct']}% payload="
                f"{r['payload'] and list(r['payload'])}")


def pr13_no_sell_no_invent():
    """PR4: без цены распродажи → NO_SELL, не выдумываем (цена акции решает оператор)."""
    card = next(c for c in _FILM if c["offer_id"] == "ARB-87309612")
    r = P.promo_card(card, sell=None)
    ok = (not r["ok"] and r["verdict"] == "NO_SELL" and r["payload"] is None)
    return ok, f"verdict={r['verdict']} (sell не задан — payload нет)"


def pr14_fake_anchor_refused():
    """PR2: якорь ≤ продажи = «подъём под видом акции» → NOT_SALE (не рисуем скидку)."""
    card = {"offer_id": "ARB-87931769", "cost": 65.0, "price": 520}
    r = P.promo_card(card, sell=1200, regular=520)
    ok = (not r["ok"] and r["verdict"] == "NOT_SALE" and "не скидка" in r["note"])
    return ok, f"verdict={r['verdict']} · {r['note']}"


def pr15_below_floor_refused():
    """PR4: продажа ниже пола ЦЕНОВИКА → отказ (убыток запрещён, P1)."""
    card = {"offer_id": "ARB-87931769", "cost": 65.0, "price": 520}
    r = P.promo_card(card, sell=700, regular=900)     # пол 900 (net 330 < КПИ 500)
    ok = (not r["ok"] and r["verdict"] == "BELOW_FLOOR"
          and r["floor"] == 900 and "пола" in r["note"])
    return ok, f"verdict={r['verdict']} пол={r['floor']} · {r['note']}"


def pr16_range_gate():
    """PR3: скидка вне 5–99% по правилу Маркета → DISCOUNT_RANGE. discount_pct в 2 знаках
    (решение по ТОМУ ЖЕ округлению, что и наружу): отказная 2.13% никогда не выглядит «в зоне»."""
    card = {"offer_id": "ARB-87309612", "cost": 700.0, "price": 5600}
    r = P.promo_card(card, sell=4600, regular=4700)   # (4700−4600)/4700 ≈ 2.13% < 5%
    ok = (not r["ok"] and r["verdict"] == "DISCOUNT_RANGE" and r["discount_pct"] == 2.13)
    return ok, f"verdict={r['verdict']} скидка {r['discount_pct']}% (вне 5–99%)"


def pr17_provisional_honest():
    """PR6: пол/решение provisional без явных delivery/fee; с явными — confirmed."""
    card = next(c for c in _FILM if c["offer_id"] == "ARB-53416854")
    r_prov = P.promo_card(card, sell=1200)
    r_cnf = P.promo_card(card, sell=1200, delivery=200, fee=0.15)
    ok = (r_prov["ok"] and r_prov["provisional"] and "PROVISIONAL" in r_prov["note"]
          and r_cnf["ok"] and not r_cnf["provisional"])
    return ok, f"provisional без явных={r_prov['provisional']} · с явными={r_cnf['provisional']}"


# ── #14-фиксы ревью (баги проводки #13, подтверждены адверсариалом): крэш/происхождение/граница ──

def pr18_cost_zero_no_invent():
    """#14: cost=0 (и строка-не-число) раньше проскакивал NO_COST-гейт → crash `f'{None:g}'`
    на отказной строке floor_hit(NA). Теперь → честный NO_COST, без исключения."""
    bad_costs = [0, 0.0, "abc", "0"]
    ok_all, detail = True, []
    for cost in bad_costs:
        r = P.promo_card({"offer_id": "ARB-X", "cost": cost, "price": 500}, sell=400)
        good = not r["ok"] and r["verdict"] == "NO_COST" and r["payload"] is None
        ok_all &= bool(good)
        detail.append(f"cost={cost!r}→{r['verdict']}")
    return ok_all, " · ".join(detail) + " (без крэша, PR5: закупки нет → акция нечестна)"


def pr19_bad_params_no_blowup():
    """#14: битые параметры (fee=1.0/доставка<0) при валидной закупке → floor_hit BAD_PARAMS
    БЕЗ net → раньше TypeError `f'{None:g}'`. Теперь — BAD_PARAMS с честной причиной, не крэш."""
    card = {"offer_id": "ARB-87931769", "cost": 65.0, "price": 520}
    r_fee = P.promo_card(card, sell=470, regular=520, fee=1.0)
    r_del = P.promo_card(card, sell=470, regular=520, delivery=-5)
    ok = (not r_fee["ok"] and r_fee["verdict"] == "BAD_PARAMS"
          and "пол не посчитан" in r_fee["note"]
          and not r_del["ok"] and r_del["verdict"] == "BAD_PARAMS")
    return ok, (f"fee=1.0→{r_fee['verdict']} ({r_fee['note'][:40]}…) "
                f"delivery<0→{r_del['verdict']} (без крэша партии)")


def pr20_basis_provenance():
    """#14: basis честно отражает ПРОИСХОЖДЕНИЕ якоря: явный regular=held (выдержанная),
    regular по умолчанию с витрины=current_vitrine; OK-строка не перетирает held."""
    card = next(c for c in _FILM if c["offer_id"] == "ARB-29846713")   # price 4800 (витрина)
    r_default = P.promo_card(card, sell=4200)                    # regular по умолч. = 4800
    r_explicit = P.promo_card(card, sell=4200, regular=6000)     # явно выдержанная 6000
    r_same = P.promo_card(card, sell=4600, regular=4800)         # явно == витринной
    r_refused = P.promo_card(card, sell=1200, regular=520)       # отказ NOT_SALE, явный held
    ok = (r_default["basis"] == "current_vitrine"
          and r_explicit["basis"] == "held" and r_explicit["ok"]
          and r_explicit["payload"]["discount_base"] == 6000.0
          and r_same["basis"] == "held"          # явно задан даже == витрине — held, не витрина
          and r_refused["basis"] == "held" and not r_refused["ok"])
    return ok, (f"default={r_default['basis']} explicit={r_explicit['basis']} "
                f"explicit==cur={r_same['basis']} refused={r_refused['basis']}")


def pr21_boundary_consistent():
    """#14: вердикт и discount_pct решаются на ОДНОМ округлении (2 знака) — отказная строка
    никогда не печатает число, похожее на «в диапазоне». DISCOUNT_RANGE ⇒ pct вне [5,99]."""
    card = next(c for c in _FILM if c["offer_id"] == "ARB-87309612")
    sells = [4600, 2000, 4560.6]      # 2.13%, ~58%, ~4.99% (граница снизу)
    ok_all, detail = True, []
    for sell in sells:
        r = P.promo_card(card, sell=sell, regular=4700)
        pct = r["discount_pct"]
        consistent = (r["verdict"] != "DISCOUNT_RANGE") or not (5.00 <= pct <= 99.00)
        ok_all &= bool(consistent and r["discount_pct"] is not None)
        detail.append(f"{sell}→{r['verdict']} {pct}%")
    return ok_all, " · ".join(detail) + " (pct и вердикт не спорят)"



def pp22_batch_nan_cost_no_crash():
    # #16: ОДНА карточка с cost=nan (json 'NaN'/1e400 из донора) раньше роняла ВЕСЬ батч
    # promo_cards сырым ValueError (int(math.ceil(nan)) внутри пола). Теперь нан-закупка —
    # честный NO_COST, соседние карточки живы.
    cards = [
        {"offer_id": "ARB-PP-A", "cost": 65.0, "price": 520},
        {"offer_id": "ARB-PP-B", "cost": float("nan"), "price": 500},
        {"offer_id": "ARB-PP-C", "cost": "NaN", "price": 500},
        {"offer_id": "ARB-PP-D", "cost": 700.0, "price": 5600},
    ]
    sells = {"ARB-PP-A": 470, "ARB-PP-B": 400, "ARB-PP-C": 400, "ARB-PP-D": 4400}
    rows = P.promo_cards(cards, sells=sells)
    got = {r["sku"]: (r["verdict"], r["ok"]) for r in rows}
    ok = (len(rows) == 4
          and got["ARB-PP-A"] == ("BELOW_FLOOR", False)
          and got["ARB-PP-B"] == ("NO_COST", False)
          and got["ARB-PP-C"] == ("NO_COST", False)
          and got["ARB-PP-D"] == ("OK", True))
    detail = ", ".join(f"{k}={v[0]}" for k, v in got.items())
    return ok, f"вердикты {detail} (нан-закупки NO_COST, батч жив)"


def pp23_bad_price_no_crash():
    # #16-residual: цена карточки НЕ числом ('abc') / nan / inf / '1e400' роняла ВЕСЬ plan_cards
    # сырым float(price) в gap-строке (или давала gap=-inf → '+−inf₽'). Грязная цена → вердикт от
    # recommend (SET/OK по норме), gap честно 0, партия жива.
    cards = [
        {"offer_id": "ARB-PP-E", "cost": 300.0, "price": "abc"},        # строка-не-число
        {"offer_id": "ARB-PP-F", "cost": 300.0, "price": float("nan")}, # nan витрина
        {"offer_id": "ARB-PP-G", "cost": 300.0, "price": "1e400"},      # inf-строка
        {"offer_id": "ARB-PP-H", "cost": 300.0, "price": 2900},         # контроль в зоне
        {"offer_id": "ARB-PP-I", "cost": int("1" + "0" * 400), "price": 500},  # огромная закупка (JSON-int)
    ]
    rows = P.plan_cards(cards)
    got = {x["offer_id"]: x for x in rows}
    ok = (len(rows) == 5
          and got["ARB-PP-H"]["verdict"] == "OK" and got["ARB-PP-H"]["gap"] == 0.0
          and all(x["gap"] == 0.0 for x in (got["ARB-PP-E"], got["ARB-PP-F"], got["ARB-PP-G"]))
          and got["ARB-PP-E"]["verdict"] in ("OK", "SET")   # цена не распознана → честный SET-путь
          and got["ARB-PP-I"]["verdict"] == "NO_COST"        # огромная закупка → честный отказ
          and P.render_plan(rows) is not None)               # рендер переживает 10**400 в cost
    detail = ", ".join(f"{k}→{x['verdict']} gap={x['gap']}" for k, x in got.items())
    return ok, f"грязные цены/кости живы: {detail} (нет +−inf₽, нет OverflowError рендера)"


TESTS = [
    ("PP1  empty_plan", pp1_empty_plan),
    ("PP2  ok_card_in_zone", pp2_ok_card_in_zone),
    ("PP3  raise_below_floor", pp3_raise_below_floor),
    ("PP4  sweet_below_zone", pp4_sweet_below_zone),
    ("PP5  no_cost_honest", pp5_no_cost_honest),
    ("PP6  provisional_flag", pp6_provisional_flag),
    ("PP7  crossed_above_recommended", pp7_crossed_above_recommended),
    ("PP8  urgent_first", pp8_urgent_first),
    ("PP9  real_film_2026_09_02", pp9_real_film_2026_09_02),
    ("PP10 summary_counts", pp10_summary_counts),
    ("PP11 render_human", pp11_render_human),
    ("PR12 promo_ok_payload", pr12_promo_ok_payload),
    ("PR13 no_sell_no_invent", pr13_no_sell_no_invent),
    ("PR14 fake_anchor_refused", pr14_fake_anchor_refused),
    ("PR15 below_floor_refused", pr15_below_floor_refused),
    ("PR16 range_gate", pr16_range_gate),
    ("PR17 provisional_honest", pr17_provisional_honest),
    ("PR18 cost_zero_no_invent", pr18_cost_zero_no_invent),
    ("PR19 bad_params_no_blowup", pr19_bad_params_no_blowup),
    ("PR20 basis_provenance", pr20_basis_provenance),
    ("PR21 boundary_consistent", pr21_boundary_consistent),
    ("PP22 batch_nan_cost_no_crash", pp22_batch_nan_cost_no_crash),
    ("PP23 bad_price_no_crash", pp23_bad_price_no_crash),
]


def main():
    print("🎯 ПРИЁМКА · ЦЕНОВИК·ПЛАН (форма переценки для утверждения, 0₽, без сети)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<30} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ План честен: вердикты делегированы price_rules (одна правда), цифры "
              "provisional до слова оператора, якорь всегда выше рекомендованной, RUBICON цел.")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

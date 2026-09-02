#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — ЦЕНОВИК·ПРАВИЛА (ymarket_price_rules_v1). Сухо, 0₽, чистая математика.

Проверяем ПРАВИЛА ценовой политики на реальных числах оператора (2026-09-02):
«каждый заказ ≥500₽ чистого после доставки», «закупка ~300₽ должна уходить за 2600–3000,
а не 1300», «зачёркнутая цена поверх». Никакой сети и записи — только формулы и честные вердикты.

  PR1  net_profit_formula        — net = price·(1−fee) − cost − delivery (КПИ после доставки, P1)
  PR2  net_none_on_bad_input     — цена/закупка ≤0 или None → None (не выдумываем, P8)
  PR3  floor_formula             — пол = (cost+delivery+КПИ)/(1−fee) вверх до 50₽ (P3)
  PR4  floor_no_invent           — закупки нет → пол не считаем (P8)
  PR5  floor_hit_ok              — цена 1300 при закупке 300 даёт net≥500 → OK
  PR6  floor_hit_below           — цена 1000 при закупке 300 → net<500 → BELOW_FLOOR, gap честный (P4)
  PR7  sweet_band_operator_case  — закупка 300 → сладкая зона 2400–3000 (ARB-53416854: «2600–3000»)
  PR8  floor_lift_no_invert      — малая закупка (доставка фиксирована) → зона не инвертируется, пол держит
  PR9  recommend_sweet_raise     — 1300₽ прибыльна, но ниже сладкой зоны → SWEET, рекомендует ~2700₽
  PR10 recommend_floor_raise     — 1000₽ ниже пола → RAISE до пола 1200₽ (честно, P4)
  PR11 recommend_set_no_current  — цены нет → SET в середину зоны (2700₽)
  PR12 recommend_ok_hold         — цена в зоне → OK, держим (КПИ и дизайн-профит есть)
  PR13 crossed_price_gap         — якорь всегда выше цены на ≥ min_gap (P5)
  PR14 kpi_honest                — КПИ по факту net: попал/недобрал — с короткой, не «красивой» цифрой
  PR15 no_cost_honest_refusal    — recommend(0/None) → NO_COST, ok=False (не выдумываем цену)
  PR16 crossed_above_on_hold     — вердикт OK (держим цену) → якорь от ИТОГОВОЙ цены, всегда выше (P5)
  PR17 provisional_flag          — delivery/fee не даны → provisional=True (совет, НЕ приговор)
  PR18 bad_fee_no_blowup         — fee вне (0,1) → None/BAD_PARAMS, не деление на ноль/врёт (P7/P8)
  PR19 net_decimal_exact         — копеечная арифметика 1 округлением = десятичной истине (не ±1 коп.)
  PR20 sweet_band_real_mult      — множитель зоны ФАКТИЧЕСКИЙ (после подъёма полом), не константа ×8
  PR21 above_zone_honest         — цена выше зоны (но прибыльна) → OK «держим», флаги above_zone/over_ceiling,
                                   НЕ врём «в зоне» и НЕ авто-снижаем (решение оператора, #14)
  PR22 net_3decimal_exact        — цена с 3-м десятичным знаком цела: net 430.01, не 430.02 (1 округление, #14)
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

import ymarket_price_rules_v1 as pr      # noqa: E402

_D, _F, _T = 200.0, 0.15, 500.0           # доставка/комиссия/цель — как в демо модуля


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def pr1_net_profit_formula():
    net = pr.net_profit(700, 87.5, delivery=_D, fee=_F)
    return net == 307.5, f"net(700,87.5)= {net} (ждём 307.5 = 700·0.85−87.5−200)"


def pr2_net_none_on_bad_input():
    bad = (pr.net_profit(0, 87.5), pr.net_profit(700, -1), pr.net_profit(-5, 87.5),
           pr.net_profit(None, 87.5), pr.net_profit(700, None))
    return all(v is None for v in bad), f"нечестные входы → все None: {bad}"


def pr3_floor_formula():
    fl = pr.floor_price(300, target_profit=_T, delivery=_D, fee=_F)
    return fl == 1200, f"пол(300, КПИ500)= {fl} (ждём 1200 = ⌈(300+200+500)/0.85⌉50)"


def pr4_floor_no_invent():
    return pr.floor_price(0) is None and pr.floor_price(None) is None, "пол без закупки → None"


def pr5_floor_hit_ok():
    v = pr.floor_hit(1300, 300, target_profit=_T, delivery=_D, fee=_F)
    return v["ok"] and v["net"] == 605.0, f"net(1300)= {v['net']} (ждём 605≥500)"


def pr6_floor_hit_below():
    v = pr.floor_hit(1000, 300, target_profit=_T, delivery=_D, fee=_F)
    return (not v["ok"] and v["verdict"] == "BELOW_FLOOR" and v["floor"] == 1200
            and v["gap"] == 200.0), f"net(1000)= {v['net']} gap={v.get('gap')} (ждём 350, BELOW_FLOOR)"


def pr7_sweet_band_operator_case():
    z = pr.sweet_band(300)
    return (z["low"] == 2400 and z["high"] == 3000), (
        f"зона(300)= {z['low']}–{z['high']} (оператор: закупка ~300 → 2600–3000, НЕ 1300)")


def pr8_floor_lift_no_invert():
    fl = pr.floor_price(50, target_profit=_T, delivery=_D, fee=_F)
    z = pr.sweet_band(50, floor=fl)
    ok = (z["low"] <= z["high"] and z["low"] >= fl)
    return ok, f"зона(50, пол={fl})= {z['low']}–{z['high']} — не инвертирована, пол держит"


def pr9_recommend_sweet_raise():
    r = pr.recommend(300, current_price=1300)
    # 1300 прибыльна (net 605 ≥ пола), НО ниже сладкой зоны фирменного товара — вердикт SWEET, не OK
    ok = r["verdict"] == "SWEET" and 2400 <= r["recommended"] <= 3000 and r["crossed"] > r["recommended"]
    return ok, f"verdict={r['verdict']} рекомендуем {r['recommended']}₽ (в зоне 2400–3000) якорь {r['crossed']}₽"


def pr10_recommend_floor_raise():
    r = pr.recommend(300, current_price=1000)
    return r["verdict"] == "RAISE" and r["recommended"] == 1200, (
        f"verdict={r['verdict']} рекомендуем {r['recommended']} (ждём RAISE→1200 пол)")


def pr11_recommend_set_no_current():
    r = pr.recommend(300)
    return r["verdict"] == "SET" and r["recommended"] == 2700, (
        f"verdict={r['verdict']} рекомендуем {r['recommended']} (ждём SET→2700 середина зоны)")


def pr12_recommend_ok_hold():
    r = pr.recommend(300, current_price=2900)
    return r["verdict"] == "OK" and r["recommended"] == 2900, (
        f"verdict={r['verdict']} (цена в зоне — держим {r['recommended']})")


def pr13_crossed_price_gap():
    c = pr.crossed_price(700, min_gap=600)
    return c >= 1300 and c - 700 >= 600, f"якорь(700)= {c} (ждём ≥1300, т.е. +600 минимум)"


def pr14_kpi_honest():
    hi, lo = pr.kpi(605.0, target=_T), pr.kpi(350.0, target=_T)
    return (hi["ok"] and lo["ok"] is False and lo["shortfall"] == 150.0), (
        f"net605→ok={hi['ok']} net350→ok={lo['ok']} shortfall={lo['shortfall']} (ждём 150)")


def pr15_no_cost_honest_refusal():
    for c in (0, None, -1):
        r = pr.recommend(c)
        if r["verdict"] != "NO_COST" or r["ok"]:
            return False, f"закупка {c} → verdict={r.get('verdict')} (ждём NO_COST, честно)"
    return True, "закупки нет → честный отказ, цену не выдумываем (P8)"


def pr16_crossed_above_on_hold():
    # OK на удержании цены: якорь строится от ИТОГОВОЙ (recommended=current), НЕ от середины зоны —
    # иначе зачёркнутая могла бы быть ≤ продажной (фальшивая «скидка»). Проверяем на трёх удержаниях.
    ok_all = True
    detail = []
    for cur in (2600, 3500, 5000):
        r = pr.recommend(300, current_price=cur, delivery=_D, fee=_F)
        good = r["verdict"] == "OK" and r["recommended"] == cur and r["crossed"] > cur
        ok_all &= bool(good)
        detail.append(f"{cur}→{r['crossed']}")
    return ok_all, f"вердикты OK, якорь всегда выше продажной: " + ", ".join(detail)


def pr17_provisional_flag():
    # delivery/fee НЕ подтверждены оператором → дефолты, provisional=True (вердикт = совет).
    a = pr.recommend(300, current_price=2900)                       # без явных delivery/fee
    b = pr.recommend(300, current_price=2900, delivery=_D, fee=_F)  # явные → подтверждено
    h = pr.floor_hit(1300, 300)                                     # и в floor_hit тоже
    ok = (a["provisional"] and a["params"]["confirmed"] is False
          and b["provisional"] is False and b["params"]["confirmed"]
          and h["provisional"])
    return ok, (f"дефолт→provisional={a['provisional']} подтверждено={b['params']['confirmed']} "
                f"floor_hit→provisional={h['provisional']}")


def pr18_bad_fee_no_blowup():
    # fee=1.0 / вне (0,1) — честно None/BAD_PARAMS, не ZeroDivision и не фейковая цена (P7/P8).
    fl = pr.floor_price(300, fee=1.0)
    fl_neg = pr.floor_price(300, fee=-0.5)
    net = pr.net_profit(1300, 300, fee=1.0)
    v = pr.floor_hit(1300, 300, delivery=_D, fee=1.0)
    r = pr.recommend(300, current_price=1300, delivery=_D, fee=1.0)
    ok = (fl is None and fl_neg is None and net is None
          and v["verdict"] == "BAD_PARAMS" and r["verdict"] == "BAD_PARAMS" and not r["ok"])
    return ok, f"floor={fl} net={net} floor_hit={v.get('verdict')} recommend={r.get('verdict')} (честно)"



def pr19_net_decimal_exact():
    # Двойное округление (комиссия отдельно, потом net) давало −121.71 против десятичной истины −121.70.
    # Одно округление всего выражения в копейках обязано совпасть с Decimal half-even (PR1 не сломан).
    import decimal
    price, cost, d, f = 100.10, 6.79, 200.0, 0.15
    got = pr.net_profit(price, cost, delivery=d, fee=f)
    truth = decimal.Decimal("100.10") * (decimal.Decimal("1") - decimal.Decimal("0.15")) \
        - decimal.Decimal("6.79") - decimal.Decimal("200.00")
    truth = float(truth.quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_EVEN))
    ok = got == truth and got == -121.7
    return ok, f"net({price},{cost})= {got} — десятичная истина {truth} (1 округление, ±0.01 исключён)"


def pr20_sweet_band_real_mult():
    # Зона поднята полом/потолком → множитель ФАКТИЧЕСКОЙ зоны, а не констант ×8/×10:
    # малый товар с фиксированной доставкой иначе писал бы ×8 при реальной цене ×18 (врёт СТРАТЕГУ).
    z = pr.sweet_band(50, floor=900)
    ok = z["low"] == 900 and z["high"] == 900 and z["from_mult"] == 18.0 and z["to_mult"] == 18.0
    return ok, f"зона(50, пол=900)= {z['low']}–{z['high']} множитель {z['from_mult']}–{z['to_mult']} (реальный ×18)"


def pr21_above_zone_honest():
    # #14-фикс ревью: цена ВЫШЕ сладкой зоны (но прибыльна) → вердикт OK (держим, НЕ авто-снижаем —
    # это решение оператора), но НЕ врём «в зоне»: флаги above_zone/over_ceiling + честная заметка.
    ok_all, detail = True, []
    for cur in (5000, 3100):                    # cost 300, зона 2400–3000; 5000>потолок 3000
        r = pr.recommend(300, current_price=cur, delivery=_D, fee=_F)
        above = cur > 3000
        good = (r["verdict"] == "OK" and r["recommended"] == cur
                and r.get("above_zone") is above
                and r.get("over_ceiling") == (cur > 3000)
                and "в зоне 2400–3000₽" not in r["note"]
                and "ВЫШЕ зоны" in r["note"] and "держим" in r["note"])
        ok_all &= bool(good)
        detail.append(f"{cur}→{r['verdict']} above={r.get('above_zone')} "
                      f"over_ceil={r.get('over_ceiling')} · {r['note']}")
    return ok_all, " | ".join(detail)


def pr22_net_3decimal_exact():
    # #14-фикс ревью: цена с 3-м десятичным знаком не теряет его (старое пред-округление цены
    # до копейки round(price*100) роняло полкопейки → net 430.02 вместо десятичной 430.01).
    got = pr.net_profit(800.015, 50, delivery=200.0, fee=0.15)
    truth = round(800.015 * 0.85 - 50 - 200.0, 2)     # 430.01 (десятичная истина)
    return got == 430.01 and got != 430.02, (
        f"net(800.015, 50)= {got} — десятичная истина 430.01 (3-й знак цены цел, ±1 коп. исключён)")


TESTS = [
    ("PR1  net_profit_formula", pr1_net_profit_formula),
    ("PR2  net_none_on_bad_input", pr2_net_none_on_bad_input),
    ("PR3  floor_formula", pr3_floor_formula),
    ("PR4  floor_no_invent", pr4_floor_no_invent),
    ("PR5  floor_hit_ok", pr5_floor_hit_ok),
    ("PR6  floor_hit_below", pr6_floor_hit_below),
    ("PR7  sweet_band_operator_case", pr7_sweet_band_operator_case),
    ("PR8  floor_lift_no_invert", pr8_floor_lift_no_invert),
    ("PR9  recommend_sweet_raise", pr9_recommend_sweet_raise),
    ("PR10 recommend_floor_raise", pr10_recommend_floor_raise),
    ("PR11 recommend_set_no_current", pr11_recommend_set_no_current),
    ("PR12 recommend_ok_hold", pr12_recommend_ok_hold),
    ("PR13 crossed_price_gap", pr13_crossed_price_gap),
    ("PR14 kpi_honest", pr14_kpi_honest),
    ("PR15 no_cost_honest_refusal", pr15_no_cost_honest_refusal),
    ("PR16 crossed_above_on_hold", pr16_crossed_above_on_hold),
    ("PR17 provisional_flag", pr17_provisional_flag),
    ("PR18 bad_fee_no_blowup", pr18_bad_fee_no_blowup),
    ("PR19 net_decimal_exact", pr19_net_decimal_exact),
    ("PR20 sweet_band_real_mult", pr20_sweet_band_real_mult),
    ("PR21 above_zone_honest", pr21_above_zone_honest),
    ("PR22 net_3decimal_exact", pr22_net_3decimal_exact),
]


def main():
    print("🎯 ПРИЁМКА · ЦЕНОВИК·ПРАВИЛА (чистая математика, 0₽, без сети)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<28} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Ценовик честен: КПИ после доставки, пол не выдумывает, сладкая зона по оператору "
              "(300→2400–3000, не 1300), якорь-зачёркнутая выше, нечестная закупка → отказ.")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

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


def pr23_nan_inf_net_none():
    # #16-фикс: нан/inf в цене/закупке/доставке — честный None, НЕ nan (раньше nan утекал в
    # Decimal-арифметику и floor_hit врал «net nan < пола» / BELOW_FLOOR на нан-цене).
    for bad in (float("nan"), float("inf"), float("-inf"), "nan", "1e400"):
        vals = [pr.net_profit(bad, 300, delivery=_D, fee=_F),
                pr.net_profit(1300, bad, delivery=_D, fee=_F),
                pr.net_profit(1300, 300, delivery=bad, fee=_F)]
        if any(v is not None for v in vals):
            return False, f"net с {bad!r} не всё None: {vals}"
    return True, "nan/inf цена/закупка/доставка → None (не nan, не врём floor_hit'у)"


def pr24_floor_nan_none():
    # #16-фикс: нан/inf/огромная cost крэшили int(math.ceil()) сырым OverflowError — теперь честно
    # None, без исключения. 10**400 (json-integer) → OverflowError float(); 1.7e308 → raw = inf.
    for v in (float("nan"), float("inf"), float("-inf"), "nan", "1e400",
              int("1" + "0" * 400), 1.7e308):
        try:
            got = pr.floor_price(v, delivery=_D, fee=_F)
            if got is not None:
                return False, f"floor_price({str(v)[:20]}…)= {got} (ждём None)"
        except Exception as e:
            return False, f"floor_price({str(v)[:20]}…) → {type(e).__name__}: {e} (ждём None)"
    return True, "nan/inf/огромная cost → пол None (без сырого крэша)"


def pr25_recommend_string_and_nan_cost():
    # #16-фикс: cost строкой из JSON донора ломала ноту над-зоны (cost*CEIL → TypeError);
    # нан-закупка (nan<=0 ложно) давала BAD_PARAMS вместо честного NO_COST.
    r_str = pr.recommend("300", current_price=5000, delivery=_D, fee=_F)
    ok_str = (r_str["verdict"] == "OK" and r_str["cost"] == 300.0
              and r_str.get("over_ceiling") is True)
    r_nan = pr.recommend(float("nan"), delivery=_D, fee=_F)
    ok_nan = r_nan["verdict"] == "NO_COST" and not r_nan["ok"]
    return ok_str and ok_nan, (f"строка '300' над потолком → {r_str['verdict']} "
                               f"over={r_str.get('over_ceiling')} · нан-закупка → {r_nan['verdict']}")


def pr26_sweet_band_nan_none():
    # #16-фикс: нан/inf-закупка крэшила _round_up(int(math.ceil(nan))) — теперь честно None.
    try:
        z = pr.sweet_band(float("nan"))
        if z is not None:
            return False, f"sweet_band(nan)= {z} (ждём None)"
    except Exception as e:
        return False, f"sweet_band(nan) → {type(e).__name__}: {e}"
    return True, "нан-закупка → зоны нет (None), не сырой крэш"


def pr27_floor_hit_nan_honest():
    # #16-фикс: floor_hit(нан-цена) раньше врал BELOW_FLOOR «net nan < пола» — теперь честный NA
    # (net_profit вернул None); нан-закупка тоже честно NA, а НЕ числовое враньё.
    v = pr.floor_hit(float("nan"), 300, delivery=_D, fee=_F)
    v2 = pr.floor_hit(1300, float("nan"), delivery=_D, fee=_F)
    ok = (v["verdict"] == "NA" and v.get("net") is None
          and v2["verdict"] == "NA" and v2.get("net") is None
          and v["ok"] is False and v2["ok"] is False)
    return ok, (f"floor_hit(нан цена)={v.get('verdict')} · floor_hit(нан закупка)="
                f"{v2.get('verdict')} — честно NA, не BELOW_FLOOR")


def pr28_ceiling_masked_by_shelf():
    # #16-фикс (остаток V4): sweet_band округляет верх зоны к «полке» (5333→5400), и цена 5390
    # (>×10 потолка 5333) пряталась «в зоне». Потолок теперь проверяется НЕЗАВИСИМО от зоны.
    r = pr.recommend(533.33, current_price=5390, delivery=_D, fee=_F)
    ok = (r["verdict"] == "OK" and r["recommended"] == 5390
          and r.get("over_ceiling") is True
          and "в зоне" not in r["note"] and "ПРОБИТ" in r["note"] and "держим" in r["note"])
    # контроль: ниже потолка (5300 < 5333) — чистое OK в зоне без флагов
    r2 = pr.recommend(533.33, current_price=5300, delivery=_D, fee=_F)
    ok &= (r2["verdict"] == "OK" and r2.get("over_ceiling") in (None, False)
           and "в зоне" in r2["note"])
    return ok, (f"5390 (в полке 5400, но >×10 потолок 5333) → over_ceiling="
                f"{r.get('over_ceiling')} above_zone={r.get('above_zone')} · 5300 → в зоне без флагов")


def pr29_floor_hit_string_huge():
    # #19-residual: floor_hit был ЕДИНСТВЕННЫМ звеном канала cost/price без нормализации входов —
    # строка-цена '1300' (JSON чтения) доходила до gap `fl - price` → TypeError (1200 - '1300'),
    # float(10**400) (JSON-int) падал СЫРЫМ OverflowError (except ловил только TypeError/ValueError),
    # строка-цель '500' сравнивалась с net СЫРОЙ (net 605 ≥ '500' → TypeError). Теперь всё парсится
    # как net_profit: строка-число работает, битое/огромное/не-число с любой стороны → честный NA.
    v = pr.floor_hit('1300', 300, delivery=_D, fee=_F)
    if not (v['ok'] and v['verdict'] == 'OK' and v['net'] == 605.0 and v['floor'] == 1200):
        return False, f"floor_hit('1300',300)= {v} (ждём OK, net 605, пол 1200)"
    v2 = pr.floor_hit('1300', '300', target_profit='500', delivery=_D, fee=_F)  # цель строкой-числом
    if v2['verdict'] != 'OK':
        return False, f"floor_hit строками и целью-'500' = {v2} (ждём OK)"
    huge = int('1' + '0' * 400)
    bad_pairs = [(huge, 300), ('1300', huge), ('abc', 300), ('1300', 'abc'),
                 ('1e400', 300), ('1300', '1e400'), (huge, huge)]
    for price, cost in bad_pairs:
        try:
            w = pr.floor_hit(price, cost, delivery=_D, fee=_F)
            good = (not w['ok'] and w['verdict'] == 'NA' and w.get('net') is None)
            if not good:
                return False, f"floor_hit({str(price)[:12]}…,{str(cost)[:12]}…)= {w} (ждём NA, net None)"
        except Exception as e:
            return False, f"floor_hit({str(price)[:12]}…) → {type(e).__name__}: {e} (ждём NA)"
    return True, "'1300'/'300'/цель-'500' → OK·605; 10**400/'abc'/'1e400' с любой стороны → честный NA (net None)"


def pr30_sweet_band_huge_finite_none():
    # #19-residual: cost КОНЕЧНА, но cost×hi переполняет float (→ inf) → _round_up(int(math.ceil(inf)))
    # падал сырым OverflowError и валил ВЕСЬ recommend (F9 — партия с одной такой закупкой не
    # собиралась). Зоны при таком масштабе честно НЕТ → None (P8), не крэш. Контроль 300 цел.
    zc = pr.sweet_band(300)
    if not (zc and zc['low'] == 2400 and zc['high'] == 3000):
        return False, f"sweet_band(300)= {zc} (ждём 2400–3000)"
    for v in (1.7e308, 1e308, 2e307, 1.8e307):     # cost×8 или ×10 → inf (переполнение float)
        try:
            z = pr.sweet_band(v)
            if z is not None:
                return False, f"sweet_band({v:g})= {z} (ждём None — зона переполняет float)"
        except Exception as e:
            return False, f"sweet_band({v:g}) → {type(e).__name__}: {e} (ждём None)"
    return True, "огромные конечные cost (1.7e308/1e308/2e307/1.8e307) → зоны НЕТ (None), контроль 300→2400–3000"


def pr31_crossed_price_huge_none():
    # #19-residual: sell конечна, но sell×1.25 переполняет float (→ inf) → _round_up(ceil(inf)) падал
    # сырым OverflowError. Якоря при таком масштабе честно нет → None (P8). Контроль 700→1300 цел.
    c = pr.crossed_price(700, min_gap=600)
    if c is None or c < 1300:
        return False, f"crossed_price(700)= {c} (ждём ≥1300)"
    for v in (1.7e308, 1.6e308, '1.7e308', 10**400, '1e400'):
        try:
            g = pr.crossed_price(v)
            if g is not None:
                return False, f"crossed_price({str(v)[:14]}…)= {g} (ждём None)"
        except Exception as e:
            return False, f"crossed_price({str(v)[:14]}…) → {type(e).__name__}: {e} (ждём None)"
    return True, "огромный sell (1.7e308/1.6e308/10**400/'1e400') → якоря НЕТ (None), контроль 700→1300"


def pr32_recommend_huge_finite_no_crash():
    # #19-residual: закупка КОНЕЧНА, но за пределами честной ценовой зоны (cost×hi переполняет ИЛИ
    # сумма границ зоны > floatmax) раньше падала сырым OverflowError посреди партии донора (F9).
    # Одна такая строка роняла ВЕСЬ recommend-прогон. Теперь → честный NO_COST-отказ (P8), партия жива.
    for v in (2e307, 1e307, 1.8e307, '2e307', '1e307', 1e308, 1.7e308):
        try:
            r = pr.recommend(v, delivery=_D, fee=_F)
            if r['verdict'] != 'NO_COST' or r['ok']:
                return False, f"recommend({str(v)[:12]}…) → verdict={r.get('verdict')} ok={r.get('ok')} (ждём NO_COST)"
        except Exception as e:
            return False, f"recommend({str(v)[:12]}…) → {type(e).__name__}: {e} (ждём NO_COST)"
    rc = pr.recommend(300, current_price=2900, delivery=_D, fee=_F)
    if rc['verdict'] != 'OK':
        return False, f"контроль recommend(300)= {rc.get('verdict')} (ждём OK)"
    return True, "огромные конечные закупки (1e307…1.7e308, и строкой) → честный NO_COST, не крэш; контроль 300→OK"


def pr33_floor_price_bad_siblings():
    # #19-residual: sibling-параметры floor_price (target_profit/step) НЕ валидировались — цель '500'
    # → TypeError (cost + '500'), None → float+NoneType, step=0 → ZeroDivision, step=inf → НАН утекал
    # наружу (враньё), step=nan → ceil(nan). Цель и шаг обязаны быть конечными >0 — иначе пол честно
    # None (P8). None-цель = модульный дефолт, строка-число работает.
    base = dict(delivery=_D, fee=_F)
    if pr.floor_price(300, **base) != 1200:
        return False, f"контроль floor_price(300)= {pr.floor_price(300, **base)} (ждём 1200)"
    if pr.floor_price(300, target_profit='500', **base) != 1200:
        return False, f"цель-'500' → {pr.floor_price(300, target_profit='500', **base)} (ждём 1200)"
    for tp in ('abc', float('nan'), float('inf'), -1, 0):
        got = pr.floor_price(300, target_profit=tp, **base)
        if got is not None:
            return False, f"target_profit={tp!r} → {got} (ждём None)"
    for st in (0, -5, float('nan'), float('inf')):
        got = pr.floor_price(300, step=st, **base)
        if got is not None:
            return False, f"step={st!r} → {got} (ждём None)"
    return True, "битые цель/шаг ('abc'/0/-1/nan/inf) → пол None, None-цель и '500' → 1200 (контроль)"


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
    ("PR23 nan_inf_net_none", pr23_nan_inf_net_none),
    ("PR24 floor_nan_none", pr24_floor_nan_none),
    ("PR25 recommend_string_and_nan_cost", pr25_recommend_string_and_nan_cost),
    ("PR26 sweet_band_nan_none", pr26_sweet_band_nan_none),
    ("PR27 floor_hit_nan_honest", pr27_floor_hit_nan_honest),
    ("PR28 ceiling_masked_by_shelf", pr28_ceiling_masked_by_shelf),
    ("PR29 floor_hit_string_huge", pr29_floor_hit_string_huge),
    ("PR30 sweet_band_huge_finite_none", pr30_sweet_band_huge_finite_none),
    ("PR31 crossed_price_huge_none", pr31_crossed_price_huge_none),
    ("PR32 recommend_huge_finite_no_crash", pr32_recommend_huge_finite_no_crash),
    ("PR33 floor_price_bad_siblings", pr33_floor_price_bad_siblings),
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

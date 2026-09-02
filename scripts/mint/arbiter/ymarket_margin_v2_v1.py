#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""МАРЖА v2 — пол цены ЯМ с ОЖИДАЕМОЙ экономикой дропшипа (труд выкупа L + возвраты r). 0₽, чистая функция.

ЗАЧЕМ (мандат оператора — «усиль математику успешного ЯМ»): пол v1 (`ymarket_role_pricer_v1`)
считал `пол = закупка + сборы + мин.прибыль` и гейт маржи 5%. Он СЛЕП к двум реальным издержкам
дропшипа, из-за которых «прибыльная» сделка уходит в минус:

  L — ТРУД ВЫКУПА. На КАЖДЫЙ оплаченный заказ оператор руками оформляет выкуп у донора (cargo-avto).
      Это реальный ₽ на заказ (внимание + переключение + риск ошибки), а не ноль.
  r — ВОЗВРАТЫ. Доля заказов возвращается. На возврате Маркет возвращает клиенту цену (и обычно сборы),
      но закупку C мы УЖЕ понесли (выкуп — ПОСЛЕ оплаты), труд L потрачен, плюс логистика возврата Rlog.
      Значит закупка+труд ТОНУТ независимо от возврата → это налог на каждую сделку.

МОДЕЛЬ (ожидание на ОДИН размещённый заказ; выкуп происходит всегда, возврат — с вероятностью r):
    ветка «оставил» (1−r):  π_keep   = P − F − C − L
    ветка «вернул»   (r):   π_return = −(C + L + Rlog)          # цена/сборы возвращены, C+L утоплены
    E[π] = (1−r)·(P − F − C − L) − r·(C + L + Rlog)
         = (1−r)·P − (1−r)·F − (C + L) − r·Rlog                 # C+L платим ВСЕГДА, сборы/цена — лишь на (1−r)

Проверка вырождения: r=0, L=0, Rlog=0  →  E[π] = P − F − C  →  ровно прибыль v1. v2 ⊃ v1.

ПОЛ (два жёстких условия, берём МАКС — оба должны держаться):
  • абсолютный (никогда не в ожидаемый убыток):  E[π] ≥ min_profit
        P ≥ [min_profit + (1−r)·F + (C+L) + r·Rlog] / (1−r)
  • относительный (пол маржи 15–20%, не 5%):      E[π]/P·100 ≥ min_margin_pct
        P ≥ [(1−r)·F + (C+L) + r·Rlog] / [(1−r) − min_margin_pct/100]

ЧЕСТНОСТЬ (закон линии, как в v1/econ):
  • нет закупки или нет сборов → пол = None (НЕ ноль: ноль = «продавай за копейку», дороже всех ложь).
  • r→1 (почти верный возврат) → знаменатель (1−r)→0 → пол неисчислим → None, basis='returns_too_high'.
  • (1−r) ≤ min_margin_pct/100 → такую маржу не взять ни за какую цену → None, basis='margin_unreachable'.
  • L и r по умолчанию — ОЦЕНКИ, не замер. Пока не откалибровано на живом заказе, решение несёт
    calibrated=False (пол ЗАВЫШАЕМ на оценку — лучше перебдеть, чем продать в минус). После первого
    заказа оператор задаёт реальные L и r явно → calibrated=True.

Граница: файл НЕ двигает деньги и НЕ рисует доход. Считает пол и ОЖИДАЕМУЮ прибыль до публикации.
Реальный ₽ — только verified в леджере по факту. stdlib-only, fail-soft.
"""
from __future__ import annotations

import json
import sys

# Абсолютный ориентир прибыли — тот же, что в v1 (единый язык пола).
MIN_PROFIT_RUB = 30.0
# Пол маржи v2: 15–20% вместо 5%. Экспрессу цена терпит (срочность), а риск дропшипа (выкуп+возврат) — нет.
MIN_MARGIN_PCT_V2 = 18.0

# ── ОЦЕНКИ (НЕ измерено; калибровать на ПЕРВОМ живом заказе — до тех пор calibrated=False) ──────────
DEFAULT_BUYOUT_LABOR_RUB = 50.0      # труд выкупа у донора на 1 оплаченный заказ (~мин внимания + переключение)
DEFAULT_RETURNS_RATE = 0.05          # доля возвратов (плёнка/короб/скотч — непошив/непарфюм → низкая; оценка)
DEFAULT_RETURN_LOGISTICS_RUB = 0.0   # логистика возврата СВЕРХ утопленной закупки (оценка; C+L и так тонут)


def _num(v):
    """Мягкое число: 99 / '99' / '1,2' → float; None/мусор → None (не выдумываем 0)."""
    if v is None:
        return None
    if isinstance(v, bool):            # bool — не число цены
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _clamp_rate(r):
    """Доля возвратов в [0,1). 1.0 и выше отсекаем как неисчислимое (обрабатывается выше)."""
    r = _num(r)
    if r is None:
        return None
    return max(0.0, r)


def expected_profit(price_sell, cost_buy, market_fees,
                    labor=DEFAULT_BUYOUT_LABOR_RUB, returns_rate=DEFAULT_RETURNS_RATE,
                    return_logistics=DEFAULT_RETURN_LOGISTICS_RUB):
    """Ожидаемая прибыль на один размещённый заказ (см. модель в docstring файла). Честные None.

    Возврат: {e_profit, e_margin_pct, keep_prob, pi_keep, pi_return, cost_buy, market_fees,
              labor, returns_rate, return_logistics, in_plus, basis}.
    """
    P = _num(price_sell)
    C = _num(cost_buy)
    F = _num(market_fees)
    L = _num(labor) or 0.0
    Rlog = _num(return_logistics) or 0.0
    r = _clamp_rate(returns_rate)
    r = 0.0 if r is None else r

    base = {"cost_buy": C, "market_fees": F, "labor": round(L, 2),
            "returns_rate": round(r, 4), "return_logistics": round(Rlog, 2)}
    if P is None:
        return {**base, "e_profit": None, "e_margin_pct": None, "keep_prob": None,
                "pi_keep": None, "pi_return": None, "in_plus": None, "basis": "no_price"}
    if C is None:
        return {**base, "e_profit": None, "e_margin_pct": None, "keep_prob": round(1 - r, 4),
                "pi_keep": None, "pi_return": None, "in_plus": None, "basis": "cost_only"}
    if F is None:
        return {**base, "e_profit": None, "e_margin_pct": None, "keep_prob": round(1 - r, 4),
                "pi_keep": None, "pi_return": None, "in_plus": None, "basis": "no_fees"}
    if r >= 1.0:                       # почти верный возврат — ожидание не окупается ничем
        pi_return = round(-(C + L + Rlog), 2)
        return {**base, "e_profit": pi_return, "e_margin_pct": None, "keep_prob": 0.0,
                "pi_keep": round(P - F - C - L, 2), "pi_return": pi_return,
                "in_plus": False, "basis": "returns_too_high"}

    pi_keep = P - F - C - L
    pi_return = -(C + L + Rlog)
    e_profit = round((1.0 - r) * pi_keep + r * pi_return, 2)
    e_margin_pct = round(e_profit / P * 100.0, 1) if P > 0 else None
    return {**base, "e_profit": e_profit, "e_margin_pct": e_margin_pct,
            "keep_prob": round(1 - r, 4), "pi_keep": round(pi_keep, 2),
            "pi_return": round(pi_return, 2), "in_plus": e_profit > 0, "basis": "full"}


def margin_floor_v2(cost_buy, market_fees,
                    labor=DEFAULT_BUYOUT_LABOR_RUB, returns_rate=DEFAULT_RETURNS_RATE,
                    return_logistics=DEFAULT_RETURN_LOGISTICS_RUB,
                    min_profit=MIN_PROFIT_RUB, min_margin_pct=MIN_MARGIN_PCT_V2):
    """ПОЛ ЦЕНЫ v2 = макс(абсолютный, относительный). None, если посчитать честно нельзя.

    Возврат: {floor, absolute_floor, relative_floor, binding, feasible, cost_buy, market_fees,
              labor, returns_rate, return_logistics, min_profit, min_margin_pct, why}.
    binding ∈ {'absolute','relative'} — какое условие задаёт пол (что «жмёт»).
    """
    C = _num(cost_buy)
    F = _num(market_fees)
    L = _num(labor) or 0.0
    Rlog = _num(return_logistics) or 0.0
    r = _clamp_rate(returns_rate)
    r = 0.0 if r is None else r
    mp = _num(min_profit) or 0.0
    m = (_num(min_margin_pct) or 0.0) / 100.0

    base = {"cost_buy": C, "market_fees": F, "labor": round(L, 2),
            "returns_rate": round(r, 4), "return_logistics": round(Rlog, 2),
            "min_profit": round(mp, 2), "min_margin_pct": round(m * 100, 1)}

    if C is None or F is None:
        why = ("закупка неизвестна → пол не посчитать (P2)" if C is None
               else "сборы Маркета неизвестны → пол не посчитать; сначала калькулятор тарифов")
        return {**base, "floor": None, "absolute_floor": None, "relative_floor": None,
                "binding": None, "feasible": False, "why": why}
    if r >= 1.0:
        return {**base, "floor": None, "absolute_floor": None, "relative_floor": None,
                "binding": None, "feasible": False,
                "why": f"возвраты r={r} ≥ 1 — почти верный возврат, пол неисчислим (не выдумываем)"}

    keep = 1.0 - r
    fixed = keep * F + (C + L) + r * Rlog     # числитель обоих условий (издержки, амортизированные по r)

    # абсолютный: E[π] ≥ min_profit
    absolute_floor = round((mp + fixed) / keep, 2)

    # относительный: E[π]/P·100 ≥ min_margin_pct  →  P·(keep − m) ≥ fixed
    denom = keep - m
    if denom <= 0:
        return {**base, "floor": None, "absolute_floor": absolute_floor, "relative_floor": None,
                "binding": None, "feasible": False,
                "why": f"маржа {m*100:.0f}% недостижима: доля-удержания (1−r)={keep:.2f} ≤ маржи — "
                       f"такую маржу не взять ни за какую цену"}
    relative_floor = round(fixed / denom, 2)

    if relative_floor >= absolute_floor:
        floor, binding = relative_floor, "relative"
        why = (f"пол {floor}₽ держит маржу {m*100:.0f}% (жмёт относительное условие; "
               f"абсолютный был бы {absolute_floor}₽)")
    else:
        floor, binding = absolute_floor, "absolute"
        why = (f"пол {floor}₽ держит прибыль ≥{mp:.0f}₽ (жмёт абсолютное условие; "
               f"маржинальный был бы {relative_floor}₽)")
    return {**base, "floor": floor, "absolute_floor": absolute_floor,
            "relative_floor": relative_floor, "binding": binding, "feasible": True, "why": why}


def decide_v2(price_sell, cost_buy, market_fees,
              labor=None, returns_rate=None, return_logistics=None,
              min_profit=MIN_PROFIT_RUB, min_margin_pct=MIN_MARGIN_PCT_V2):
    """Полное решение по цене v2 из СЫРЫХ чисел (адаптер prod→числа — забота роли ЦЕНОВИК).

    labor/returns_rate=None → берём ОЦЕНКИ по умолчанию и метим calibrated=False (пол на оценке).
    Явно заданные L и r (после первого живого заказа) → calibrated=True.

    Возврат совместим по духу с v1 price_decision + поля v2:
      {allowed, price, floor, cost_buy, market_fees, labor, returns_rate, e_profit, e_margin_pct,
       binding, basis, calibrated, model, why}.
    """
    calibrated = labor is not None and returns_rate is not None
    L = DEFAULT_BUYOUT_LABOR_RUB if labor is None else labor
    r = DEFAULT_RETURNS_RATE if returns_rate is None else returns_rate
    Rlog = DEFAULT_RETURN_LOGISTICS_RUB if return_logistics is None else return_logistics

    P = _num(price_sell)
    ep = expected_profit(P, cost_buy, market_fees, L, r, Rlog)
    fl = margin_floor_v2(cost_buy, market_fees, L, r, Rlog, min_profit, min_margin_pct)
    floor = fl["floor"]

    def _out(allowed, basis, why):
        return {"allowed": allowed, "price": P, "floor": floor,
                "cost_buy": ep["cost_buy"], "market_fees": ep["market_fees"],
                "labor": ep["labor"], "returns_rate": ep["returns_rate"],
                "e_profit": ep["e_profit"], "e_margin_pct": ep["e_margin_pct"],
                "binding": fl["binding"], "basis": basis, "calibrated": calibrated,
                "model": "v2", "why": why}

    if P is None:
        return _out(False, "no_price", "цена не задана — выставлять нечего (не выдумываем)")
    if ep["basis"] == "cost_only":
        return _out(False, "cost_only",
                    "закупка неизвестна → пол маржи не посчитать (P2): цену не выставляем автоматически")
    if ep["basis"] == "no_fees":
        return _out(False, "no_fees", "сборы Маркета неизвестны → пол не посчитать; сначала калькулятор")
    if not fl["feasible"] or floor is None:
        return _out(False, "infeasible", fl["why"])

    tag = "" if calibrated else " ⚠️L,r=оценка (калибровать на 1-м заказе)"
    if P < floor:
        return _out(False, "full",
                    f"цена {P} НИЖЕ пола {floor} (P1) — ожидаемый убыток запрещён{tag}")
    return _out(True, "full",
                f"цена {P} ≥ пола {floor}, ожид. прибыль {ep['e_profit']}₽ "
                f"({ep['e_margin_pct']}%){tag}")


def render_floor(fl):
    """Человеческая строка пола для сводки БРИГАДИРУ."""
    if not fl.get("feasible"):
        return f"⛔ пол v2 неисчислим: {fl.get('why')}"
    return (f"пол v2 {fl['floor']}₽ (жмёт {fl['binding']}) · "
            f"закуп {fl['cost_buy']} + сборы {fl['market_fees']} + труд {fl['labor']} · "
            f"возвраты {fl['returns_rate']*100:.0f}% · маржа ≥{fl['min_margin_pct']:.0f}%")


if __name__ == "__main__":
    if "--json" in sys.argv:
        demo = {
            "floor_v1_parity(r0,L0,m5)": margin_floor_v2(180, 50, labor=0, returns_rate=0, min_margin_pct=5),
            "floor_v2(L50,r5%,m18)": margin_floor_v2(180, 50),
            "decide_ok": decide_v2(1500, 180, 50),
            "decide_below": decide_v2(300, 180, 50),
            "returns_100%": margin_floor_v2(180, 50, returns_rate=1.0),
        }
        print(json.dumps(demo, ensure_ascii=False, indent=2))
        sys.exit(0)

    print("💰 МАРЖА v2 — пол цены с трудом выкупа L + возвраты r (сухо, 0₽)\n")
    print("  Вырождение v2⊃v1 (L=0,r=0,маржа=5%): пол должен = закупка+сборы+30")
    f0 = margin_floor_v2(180, 50, labor=0, returns_rate=0, min_margin_pct=5)
    print(f"    {render_floor(f0)}  → floor={f0['floor']} (v1 дал бы 260)\n")
    print("  Боевая v2 (L=50, r=5%, маржа=18%) на закуп 180 + сборы 50:")
    f = margin_floor_v2(180, 50)
    print(f"    {render_floor(f)}")
    for P in (300, 600, 1200):
        d = decide_v2(P, 180, 50)
        print(f"    {'✅' if d['allowed'] else '⛔'} цена {P}: {d['why']}")

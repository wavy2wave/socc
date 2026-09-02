#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЦЕНОВИК·ПРАВИЛА (ymarket_price_rules_v1) — решающий слой ценовой политики ЦИКЛА-1.

ЗАЧЕМ. Оператор (2026-09-02): «каждый заказ должен давать ≥500₽ чистого профита ПОСЛЕ доставки»,
«закупка ~300₽ должна уходить за 2600–3000, а не за 1300», «зачёркнутая цена 600–1000₽ поверх».
Роли-ценовики (role_pricer/glasses) считают ПОЛ цены; этот модуль — ВЕРХНИЙ решающий слой:
по закупке и цели чистого профита решает, по какой цене карточка обязана продаваться, честно ли
текущая цена даёт КПИ, и где витринная цена-якорь. Никого не импортирует, ничего не пишет — чистая
математика (0₽, RUBCON цел). Владелец ценовой политики (L9): manifest MARKUP у движка советуется
с этим слоем.

МОДЕЛЬ издержек (параметры, TUNABLE — оператор подтверждает цифры):
  fee_rate   — комиссия платформы + приёма платежа, ДОЛЯ от цены продажи (default 0.15)
  delivery   — доставка/логистика посылки в ₽ (default 200; ВЕРИФИЦИРУЕТ ОВХ-слой, L10)
  net = price·(1−fee) − cost − delivery      ← КПИ ПОСЛЕ ДОСТАВКИ (P1)

ПРАВИЛА (механические, покрыты приёмкой run_price_rules):
  P1  КПИ = чистый профит после доставки/издержек (net), НЕ наценка по цене.
  P2  каждый оплаченный заказ: net ≥ NET_FLOOR (default 500₽, TUNABLE).
  P3  цена не ниже пола: price ≥ (cost + delivery + NET_FLOOR) / (1 − fee)  (P5-пол).
  P4  если при действующей цене net < пола — честно СКАЗАТЬ «цена ниже пола», не выдумывать.
  P5  витринный якорь (зачёркнутая цена): cross = round_up(price·1.25, 100), но не ниже price+min_gap.
  P6  сладкая зона: товар с фирменным фото-профитом живёт в ×8–10 от закупки (дизайн-профит),
      обычный товар — в ×5–8 (не спускаемся к ×4 без слова оператора).
  P7  потолок справедливости: цена не растёт без связи с закупкой (×CEIL, default 10) —
      защита от «красивости», тормозящей конверсию.
  P8  ничего не выдумываем: cost ≤ 0 / без offerId → честный вердикт, не цифра из воздуха.
"""
from __future__ import annotations

# Параметры политики (TUNABLE — оператор подтверждает на живых цифрах кабинета).
NET_FLOOR = 500.0          # P2: минимальный чистый профит заказа после издержек, ₽
DELIVERY_DEFAULT = 200.0   # доставка/логистика посылки, ₽ (уточняет ОВХ/СТРАТЕГ)
FEE_DEFAULT = 0.15         # комиссия платформы + эквайринг, доля от цены продажи
CEIL_MULT = 10.0           # P7: потолок цены = закупка × CEIL
SWEET_LO, SWEET_HI = 8.0, 10.0   # P6: сладкая зона (фирменный фото-профит)
NORM_LO, NORM_HI = 5.0, 8.0      # P6: обычная зона


# ── КПИ: чистый профит после доставки (P1) ─────────────────────────────────────

def _resolve_io(delivery, fee):
    """Дефолты доставки/комиссии ТОЛЬКО если не переданы явно (None-sentinel). Возвращает
    (delivery, fee, provisional): provisional=True значит «считано на НЕподтверждённых
    оператором TUNABLE-дефолтах» — такой вердикт совет, а не приговор (см. recommend)."""
    d = DELIVERY_DEFAULT if delivery is None else delivery
    f = FEE_DEFAULT if fee is None else fee
    return float(d), float(f), (delivery is None) or (fee is None)


def net_profit(price, cost, *, delivery=None, fee=None):
    """Чистый профит заказа ПОСЛЕ издержек: price·(1−fee) − cost − delivery (P1).

    ОДНО округление до копейки десятичной арифметикой (Decimal, half-even): без пред-
    округления цены и без двойного округления комиссии. 3-й десятичный знак цены не
    теряется (price 800.015 → net 430.01, а НЕ 430.02 — старое пред-округление цены
    до копейки роняло полкопейки и сдвигало net). Честно: цена/закупка ≤0, NaN/inf или
    fee вне (0,1) → None (не выдумываем, P8)."""
    try:
        price, cost = float(price), float(cost)
        if price <= 0 or cost <= 0:
            return None
        d, f, _ = _resolve_io(delivery, fee)
        if not (0 < f < 1) or d < 0:
            return None
        from decimal import Decimal, ROUND_HALF_EVEN
        net = Decimal(str(price)) * (Decimal("1") - Decimal(str(f))) \
            - Decimal(str(cost)) - Decimal(str(d))
        return float(net.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))
    except (TypeError, ValueError, ArithmeticError):
        return None


def floor_price(cost, *, target_profit=NET_FLOOR, delivery=None, fee=None,
                step=50):
    """P3: минимальная цена, дающая target_profit чистыми: (cost + delivery + target)/(1−fee), вверх до step."""
    try:
        cost = float(cost)
        if cost <= 0:
            return None
    except (TypeError, ValueError):
        return None
    d, f, _ = _resolve_io(delivery, fee)
    if not (0 < f < 1) or d < 0:
        return None                            # fee вне (0,1) → деление на ноль/отрицательное
    raw = (cost + d + target_profit) / (1 - f)
    # вверх к «круглому» шагу (50₽) — торговая полка, не дробный копеечный минимум
    import math
    return int(math.ceil(raw / step)) * step


def floor_hit(price, cost, *, target_profit=NET_FLOOR, delivery=None, fee=None):
    """P4: честный вердикт по действующей цене. Возвращает dict с net, полом и вердиктом.
    provisional=True, если delivery/fee не заданы явно (счёт на неподтверждённых дефолтах)."""
    d, f, prov = _resolve_io(delivery, fee)
    # Параметры биты (fee вне (0,1) / доставка <0) при ВАЛИДНОЙ закупке → BAD_PARAMS с честной
    # причиной, а НЕ NA. net_profit на fee=1.0 вернул бы None по ПРИЧИНЕ параметров, и нижний
    # `if net is None` соврал бы «цена/закупка не даны» (P8-причина, которой нет). Тот же вердикт,
    # что у recommend(): пол не считаем, но закупка есть — это BAD_PARAMS, не незнание цены.
    try:
        cost_bad = float(price) <= 0 or float(cost) <= 0
    except (TypeError, ValueError):
        cost_bad = True
    if not cost_bad and (not (0 < f < 1) or d < 0):
        return {"ok": False, "verdict": "BAD_PARAMS", "provisional": prov,
                "note": "комиссия вне (0,1) или доставка <0 — не считаем пол (P7/P8)"}
    net = net_profit(price, cost, delivery=d, fee=f)
    if net is None:
        return {"ok": False, "verdict": "NA", "provisional": prov,
                "note": "цена/закупка не даны честно (P8)"}
    fl = floor_price(cost, target_profit=target_profit, delivery=d, fee=f)
    if fl is None:
        return {"ok": False, "verdict": "BAD_PARAMS", "provisional": prov,
                "note": "комиссия вне (0,1) или доставка <0 — не считаем пол (P7/P8)",
                "net": net}
    gap = max(0.0, round(fl - price, 2))
    if net >= target_profit:
        return {"ok": True, "verdict": "OK", "provisional": prov,
                "note": f"net {net:g}₽ ≥ пола {target_profit:g}₽", "net": net,
                "floor": fl, "gap": 0.0}
    return {"ok": False, "verdict": "BELOW_FLOOR", "provisional": prov,
            "note": f"net {net:g}₽ < пола {target_profit:g}₽ — цена {price:g}₽ ниже {fl:g}₽",
            "net": net, "floor": fl, "gap": gap}


# ── сладкая зона / витринный якорь (P5/P6/P7) ─────────────────────────────────

def _round_up(x, step=100):
    import math
    return int(math.ceil(x / step)) * step


def sweet_band(cost, *, lo=SWEET_LO, hi=SWEET_HI, floor=None, ceil_mult=CEIL_MULT):
    """P6: зона продажи: cost·lo … cost·hi (фирменный фото-слой несёт цену).

    Зона НЕ спускается ниже пола (floor): пол — закон прибыли (P3), он важнее «красивой» наценки.
    Потолок ×ceil_mult ограничивает только сверху и ТОЛЬКО когда не ломает пол (иначе маленький
    товар с фиксированной доставкой просто не смог бы быть прибыльным). Битый cost → None (P8).
    """
    try:
        cost = float(cost)
        if cost <= 0 or lo <= 0 or hi < lo:
            return None
    except (TypeError, ValueError):
        return None
    fl = float(floor) if floor else 0.0
    low_raw = max(cost * lo, fl)
    high_raw = max(cost * hi, low_raw)            # не инвертируем: high ≥ low всегда
    cap = cost * ceil_mult if ceil_mult else float("inf")
    if high_raw > cap:
        high_raw = max(cap, low_raw)              # потолок не рвёт пол
    return {"low": _round_up(low_raw, 50), "high": _round_up(high_raw, 100),
            # множители от ФАКТИЧЕСКОЙ зоны (после подъёма полом/потолка), а не от констант:
            # иначе малый товар с большой доставкой писал бы ×8 при реальной цене ×18.
            "from_mult": round(low_raw / cost, 1) if cost else lo,
            "to_mult": round(high_raw / cost, 1) if cost else hi}


def crossed_price(sell_price, *, min_gap=600, mult=1.25, step=100):
    """P5: зачёркнутая цена-якорь на витрине. Всегда выше sell: sell·mult, но не менее sell+min_gap."""
    try:
        sell_price = float(sell_price)
        if sell_price <= 0:
            return None
    except (TypeError, ValueError):
        return None
    return _round_up(max(sell_price * mult, sell_price + min_gap), step)


def _mid(a, b):
    """Середина зоны до 100₽ — «одно число» рекомендации без псевдо-точности."""
    return int(round((a + b) / 2.0 / 100.0)) * 100


def recommend(cost, *, current_price=None, target_profit=NET_FLOOR, delivery=None,
              fee=None, branded=True, min_gap=600):
    """Одно решающее слово по товару: пол, зона, якорь и вердикт действующей цены.

    branded=True (фирменные фото/инфографика) → сладкая зона ×8–10 от закупки (P6);
    иначе обычная ×5–8. Вердикты:
      NO_COST      — закупки нет, цену не выдумываем (P8)
      BAD_PARAMS   — закупка есть, но комиссия вне (0,1) / доставка <0 (не считаем, P7)
      SET          — цены ещё нет: ставим середину зоны
      RAISE        — действующая ниже ПОЛА (КПИ после издержек не достигается) — ставим пол (P4)
      SWEET        — действующая прибыльна, но ниже сладкой зоны фирменного товара — поднимаем в зону
      OK           — действующая внутри/выше зоны: держим (КПИ есть, дизайн-профит есть)
    provisional=True, если delivery/fee НЕ подтверждены оператором и взяты дефолтами:
    вердикт тогда совет, НЕ приговор — гейтом/исполнителем не используется как PASS/FAIL.
    Зачёркнутый якорь строится от ИТОГОВОЙ цены (recommended/текущей в OK), а не от
    середины зоны — иначе на удержании якорь мог быть ≤ продажной (фальшивая «скидка», P5)."""
    d, f, prov = _resolve_io(delivery, fee)
    fl = floor_price(cost, target_profit=target_profit, delivery=d, fee=f)
    if fl is None:
        try:
            has_cost = float(cost) > 0
        except (TypeError, ValueError):
            has_cost = False
        if has_cost:
            return {"ok": False, "verdict": "BAD_PARAMS", "cost": cost, "provisional": prov,
                    "note": "закупка есть, но комиссия вне (0,1) или доставка <0 — пол не считаем (P7)"}
        return {"ok": False, "verdict": "NO_COST", "cost": cost, "provisional": prov,
                "note": "нет закупки — цену не выдумываем (P8)"}
    zone = sweet_band(cost, lo=SWEET_LO if branded else NORM_LO,
                      hi=SWEET_HI if branded else NORM_HI, floor=fl)
    zlow, zhigh = zone["low"], zone["high"]
    out = {
        "ok": True, "cost": cost, "floor": fl, "provisional": prov,
        "params": {"delivery": d, "fee": f, "confirmed": not prov},
        "zone": {"low": zlow, "high": zhigh, "from_mult": zone["from_mult"],
                 "to_mult": zone["to_mult"]},
        "decision": "SWEET" if branded else "NORM",
    }
    if current_price is None or float(current_price) <= 0:
        rec = _mid(zlow, zhigh)
        out.update(recommended=rec, verdict="SET", crossed=crossed_price(rec, min_gap=min_gap))
        out["note"] = (f"цены нет: зона {zlow}–{zhigh}₽, рекомендую {rec}₽ "
                       f"(КПИ {target_profit:g}₽ после издержек)")
        return out
    v = floor_hit(current_price, cost, target_profit=target_profit, delivery=d, fee=f)
    out["current"] = {"price": current_price, **v}
    if not v["ok"]:
        rec = fl
        out.update(recommended=rec, verdict="RAISE", crossed=crossed_price(rec, min_gap=min_gap))
        out["note"] = (f"текущая {current_price:g}₽ ниже пола {fl}₽ (net {v['net']:g}₽ < "
                       f"{target_profit:g}₽) — поднять минимум до {fl}₽")
    elif current_price < zlow:
        rec = _mid(zlow, zhigh)
        out.update(recommended=rec, verdict="SWEET" if branded else "ZONE_RAISE",
                   crossed=crossed_price(rec, min_gap=min_gap))
        out["note"] = (f"текущая {current_price:g}₽ даёт КПИ, но ниже зоны {zlow}–{zhigh}₽ "
                       f"{'сладкой зоны фирменного товара' if branded else 'нормальной наценки'} — "
                       f"поднять до {rec}₽ (дизайн-профит)" if branded
                       else f"текущая {current_price:g}₽ даёт КПИ, но ниже зоны {zlow}–{zhigh}₽ — "
                       f"поднять до {rec}₽")
    else:
        rec = int(current_price)
        out.update(recommended=rec, verdict="OK", crossed=crossed_price(rec, min_gap=min_gap))
        if current_price <= zhigh:
            out["note"] = f"текущая {current_price:g}₽ в зоне {zlow}–{zhigh}₽: КПИ есть, держим"
        else:
            # #14-честность (P7): цена ВЫШЕ зоны — не врём «в зоне». Авто-снижения НЕТ:
            # это решение оператора (ЦЕНОВИК-fork), а не гейт. Но даём флаги/честную заметку,
            # чтобы над-потолочная цена не выглядела «как все» для того, кто считает сигнал.
            over_ceiling = current_price > cost * CEIL_MULT
            out["above_zone"] = True
            out["over_ceiling"] = bool(over_ceiling)
            cap = (f"P7-потолок ×{CEIL_MULT:g} ({cost * CEIL_MULT:g}₽) ПРОБИТ — решение за оператором"
                   if over_ceiling else f"в пределах потолка ×{CEIL_MULT:g}")
            out["note"] = (f"текущая {current_price:g}₽ ВЫШЕ зоны {zlow}–{zhigh}₽ "
                           f"(×{current_price / cost:g} от закупки) — КПИ есть, держим; {cap}")
    return out


def kpi(net, *, target=NET_FLOOR):
    """КПИ заказа: по факту net (после доставки) — попал ли в цель. Пусто → None."""
    if net is None:
        return None
    return {"ok": net >= target, "net": round(net, 2), "target": target,
            "shortfall": max(0.0, round(target - net, 2))}


if __name__ == "__main__":
    # Сухая демонстрация (0₽): пример оператора ARB-53416854 (закупка ~300₽).
    for cost in (87.5, 300.0, 150.0):
        r = recommend(cost, current_price=cost * 4)      # «×4 — как было у ARB-53416854 (1300₽)»
        print(f"закупка {cost:g}₽ · действующая ×4={cost * 4:g}₽ → {r['verdict']}: {r['note']}")
        print(f"   пол {r['floor']}₽ · зона {r['zone']['low']}–{r['zone']['high']}₽ · "
              f"рекомендую {r['recommended']}₽ · зачёркнуто {r['crossed']}₽")

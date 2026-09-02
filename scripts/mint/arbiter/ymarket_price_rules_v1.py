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

import math

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
    try:
        return float(d), float(f), (delivery is None) or (fee is None)
    except (TypeError, ValueError, OverflowError):
        # #16: битые доставка/комиссия (10**400 → OverflowError, 'abc' → ValueError) не должны
        # крэшить формулу — nan провалит гейты `0 < f < 1` / `d < 0` / isfinite у вызывающих.
        return float("nan"), float("nan"), (delivery is None) or (fee is None)


def net_profit(price, cost, *, delivery=None, fee=None):
    """Чистый профит заказа ПОСЛЕ издержек: price·(1−fee) − cost − delivery (P1).

    ОДНО округление до копейки десятичной арифметикой (Decimal, half-even): без пред-
    округления цены и без двойного округления комиссии. 3-й десятичный знак цены не
    теряется (price 800.015 → net 430.01, а НЕ 430.02 — старое пред-округление цены
    до копейки роняло полкопейки и сдвигало net). Честно: цена/закупка ≤0, NaN/inf или
    fee вне (0,1) → None (не выдумываем, P8)."""
    try:
        price, cost = float(price), float(cost)
        # #16: nan/inf ЛОЖНО проходят `<= 0` (nan<=0 == False) и утекали в Decimal-арифметику
        # как nan → floor_hit врал «net nan < пола». Только КОНЕЧНОЕ положительное — честный net.
        if not math.isfinite(price) or not math.isfinite(cost) or price <= 0 or cost <= 0:
            return None
        d, f, _ = _resolve_io(delivery, fee)
        if (not (0 < f < 1) or d < 0
                or not math.isfinite(d) or not math.isfinite(f)):
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
        # #16: нан/inf (nan<=0 ложно) или огромная cost крэшили int(math.ceil()) сырым
        # OverflowError. Пол обязан быть КОНЕЧНЫМ числом — иначе честно None.
        if not math.isfinite(cost) or cost <= 0:
            return None
    except (TypeError, ValueError, OverflowError):   # float(10**400) → OverflowError, не ValueError
        return None
    d, f, _ = _resolve_io(delivery, fee)
    if (not (0 < f < 1) or d < 0
            or not math.isfinite(d) or not math.isfinite(f)):
        return None                            # fee вне (0,1) → деление на ноль/отрицательное
    # #16-residual: sibling-параметры (target_profit/step) НЕ валидировались и падали каждый
    # по-своему: цель '500' → TypeError (cost + '500'), цель None → float+NoneType, step=0 →
    # ZeroDivision, step=inf → 0·inf = НАН утекал наружу (враньё), step=nan → ceil(nan). Цель КПИ
    # и шаг полки обязаны быть конечными >0 — иначе пол честно не посчитан (None, P8).
    # None-цель = модульный дефолт (как `or`-идиома у recommend).
    try:
        tp = float(NET_FLOOR if target_profit is None else target_profit)
        st = float(step)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(tp) or tp <= 0 or not math.isfinite(st) or st <= 0:
        return None
    raw = (cost + d + tp) / (1 - f)
    if not math.isfinite(raw):
        return None                            # пол переполнил float (cost ~1e308) → честно нет пола
    q = raw / st                               # #16-residual: крошечный step (1e-300) → q = inf
    if not math.isfinite(q):
        return None                            # → int(ceil(inf)) падал сырым OverflowError; честно None
    # вверх к «круглому» шагу (50₽) — торговая полка, не дробный копеечный минимум
    return int(math.ceil(q)) * st


def floor_hit(price, cost, *, target_profit=NET_FLOOR, delivery=None, fee=None):
    """P4: честный вердикт по действующей цене. Возвращает dict с net, полом и вердиктом.
    provisional=True, если delivery/fee не заданы явно (счёт на неподтверждённых дефолтах)."""
    d, f, prov = _resolve_io(delivery, fee)
    # #16-residual: floor_hit был ЕДИНСТВЕННОЙ функцией канала без нормализации входов —
    # float(10**400) (JSON-int) падал СЫРЫМ OverflowError (в except только (TypeError, ValueError)),
    # строка-цена '1300' доходила до gap `fl - price` → TypeError (1200 - '1300'), а строка-цель
    # '500' чинилась ТОЛЬКО внутри floor_price, но сравнение net шло с СЫРОЙ целью. Всё парсим
    # КАК net_profit (float + isfinite + >0): строка-число работает, битое/огромное → честный вердикт.
    try:
        price_f, cost_f = float(price), float(cost)
        tp = float(NET_FLOOR if target_profit is None else target_profit)
    except (TypeError, ValueError, OverflowError):
        price_f = cost_f = tp = float("nan")
    if not (math.isfinite(price_f) and price_f > 0
            and math.isfinite(cost_f) and cost_f > 0):
        return {"ok": False, "verdict": "NA", "provisional": prov,
                "note": "цена/закупка не даны честно (P8)"}
    # Параметры биты (fee вне (0,1) / доставка <0) при ВАЛИДНОЙ закупке → BAD_PARAMS с честной
    # причиной, а НЕ NA. net_profit на fee=1.0 вернул бы None по ПРИЧИНЕ параметров, и нижний
    # `if net is None` соврал бы «цена/закупка не даны» (P8-причина, которой нет). Тот же вердикт,
    # что у recommend(): пол не считаем, но закупка есть — это BAD_PARAMS, не незнание цены.
    if (not (0 < f < 1) or d < 0
            or not math.isfinite(d) or not math.isfinite(f)):
        return {"ok": False, "verdict": "BAD_PARAMS", "provisional": prov,
                "note": "комиссия вне (0,1) или доставка <0 — не считаем пол (P7/P8)"}
    net = net_profit(price_f, cost_f, delivery=d, fee=f)
    if net is None:
        return {"ok": False, "verdict": "NA", "provisional": prov,
                "note": "цена/закупка не даны честно (P8)"}
    fl = floor_price(cost_f, target_profit=tp, delivery=d, fee=f)
    if fl is None:
        return {"ok": False, "verdict": "BAD_PARAMS", "provisional": prov,
                "note": "цель КПИ/параметры биты — пол не считаем (P7/P8)",
                "net": net}
    gap = max(0.0, round(fl - price_f, 2))
    if net >= tp:
        return {"ok": True, "verdict": "OK", "provisional": prov,
                "note": f"net {net:g}₽ ≥ пола {tp:g}₽", "net": net,
                "floor": fl, "gap": 0.0}
    return {"ok": False, "verdict": "BELOW_FLOOR", "provisional": prov,
            "note": f"net {net:g}₽ < пола {tp:g}₽ — цена {price_f:g}₽ ниже {fl:g}₽",
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
        # #16: нан/inf (nan<=0 ложно) крэшили _round_up(int(math.ceil(nan))) → честно None (P8).
        if not math.isfinite(cost) or cost <= 0 or lo <= 0 or hi < lo:
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    fl = float(floor) if floor else 0.0
    if not math.isfinite(fl):
        return None
    low_raw = max(cost * lo, fl)
    high_raw = max(cost * hi, low_raw)            # не инвертируем: high ≥ low всегда
    cap = cost * ceil_mult if ceil_mult else float("inf")
    # #16-residual: cost КОНЕЧНА, но так велика, что cost×lo/hi переполняет float (→ inf):
    # _round_up(int(math.ceil(inf))) падал сырым OverflowError и валил ВЕСЬ recommend (F9 — партия
    # донора с одной такой закупкой не собиралась). Сладкой зоны при таком масштабе честно нет →
    # None (P8), не крэш партии.
    if not math.isfinite(low_raw) or not math.isfinite(high_raw):
        return None
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
        if not math.isfinite(sell_price) or sell_price <= 0:
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    anchor = max(sell_price * mult, sell_price + min_gap)
    # #16-residual: sell конечна, но sell×1.25 переполняет float (→ inf) для sell ≳ 1.4e308 →
    # _round_up(ceil(inf)) падал сырым OverflowError. Якоря при таком масштабе честно нет → None.
    if not math.isfinite(anchor):
        return None
    return _round_up(anchor, step)


def _mid(a, b):
    """Середина зоны до 100₽ — «одно число» рекомендации без псевдо-точности."""
    # #16-residual: зона настолько велика, что (a+b)/2.0 переполняет float (сумма int-ов > floatmax
    # → int/float-деление кидает OverflowError, не inf). Середины честно нет → None (рекомендую
    # не выдумываем). Recommend выше отказывает таким зонам до _mid — тут страховка прямых вызовов.
    try:
        mid = (float(a) + float(b)) / 200.0
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(mid):
        return None
    return int(round(mid)) * 100


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
    # #16: закупку нормализуем в float ОДИН раз. Раньше нан/inf/строка-"300"/огромный int доходили
    # до формулы цены: нан ложно проходил `<= 0`, строка роняла ноту (cost*CEIL → TypeError),
    # 10**400 → сырой OverflowError. Конечная положительная — иначе честный NO_COST (P8).
    try:
        cost_f = float(cost)
    except (TypeError, ValueError, OverflowError):
        cost_f = float("nan")
    if not math.isfinite(cost_f) or cost_f <= 0:
        return {"ok": False, "verdict": "NO_COST", "cost": cost_f, "provisional": prov,
                "note": "нет честной закупки (пусто/не-число/не конечна) — цену не выдумываем (P8)"}
    # #19-residual: fl=None у floor_price бывает по ДВУМ причинам — битые параметры (fee вне (0,1)/
    # delivery<0) ИЛИ пол переполнил float (закупка ≳1.5e308, raw → inf). Раньше обе сливались в
    # BAD_PARAMS «комиссия вне (0,1)» — оператору врало про ЕГО конфиг, когда виновата мусорная
    # закупка. Битые параметры → BAD_PARAMS (P7); переполнение пола → честный NO_COST (P8).
    if (not (0 < f < 1) or d < 0
            or not math.isfinite(d) or not math.isfinite(f)):
        return {"ok": False, "verdict": "BAD_PARAMS", "cost": cost_f, "provisional": prov,
                "note": "закупка есть, но комиссия вне (0,1) или доставка <0 — пол не считаем (P7)"}
    fl = floor_price(cost_f, target_profit=target_profit, delivery=d, fee=f)
    if fl is None:
        return {"ok": False, "verdict": "NO_COST", "cost": cost_f, "provisional": prov,
                "note": f"закупка {cost_f:g}₽ за пределами честной ценовой зоны — пол переполняет "
                        "float, цену не выдумываем (P8)"}
    zone = sweet_band(cost_f, lo=SWEET_LO if branded else NORM_LO,
                      hi=SWEET_HI if branded else NORM_HI, floor=fl)
    # #16-residual: закупка конечна, но за пределами честной ценовой зоны — cost×hi переполняет
    # float (зона → None) ИЛИ сумма границ зоны > floatmax (соврал бы/крэшил _mid ниже). Такая
    # закупка — коррупция/опечатка масштаба (реальные ≤ ~1e5), НЕ товар: честный NO_COST-отказ,
    # а не сырой OverflowError посреди партии донора (F9). Границы зоны уже int-ы (после полки):
    # сравниваем их float-сумму, где переполнение даёт inf, а не исключение.
    if zone is None:
        return {"ok": False, "verdict": "NO_COST", "cost": cost_f, "provisional": prov,
                "note": f"закупка {cost_f:g}₽ за пределами честной ценовой зоны (×{SWEET_HI if branded else NORM_HI:g} переполняет float) — цену не выдумываем (P8)"}
    zlow, zhigh = zone["low"], zone["high"]
    if not math.isfinite(float(zlow) + float(zhigh)):
        return {"ok": False, "verdict": "NO_COST", "cost": cost_f, "provisional": prov,
                "note": f"закупка {cost_f:g}₽ за пределами честной ценовой зоны — цену не выдумываем (P8)"}
    out = {
        "ok": True, "cost": cost_f, "floor": fl, "provisional": prov,
        "params": {"delivery": d, "fee": f, "confirmed": not prov},
        "zone": {"low": zlow, "high": zhigh, "from_mult": zone["from_mult"],
                 "to_mult": zone["to_mult"]},
        "decision": "SWEET" if branded else "NORM",
    }
    # Действующую цену тоже нормализуем (#16): nan/inf/≤0 = «цены ещё нет» → честный SET, а НЕ
    # ложный RAISE «net nan < пола» (floor_hit на nan-цене врал BELOW_FLOOR/NA).
    cur = None
    if current_price is not None:
        try:
            cf = float(current_price)
            if math.isfinite(cf) and cf > 0:
                cur = cf
        except (TypeError, ValueError, OverflowError):
            pass
    if cur is None:
        rec = _mid(zlow, zhigh)
        out.update(recommended=rec, verdict="SET", crossed=crossed_price(rec, min_gap=min_gap))
        out["note"] = (f"цены нет: зона {zlow}–{zhigh}₽, рекомендую {rec}₽ "
                       f"(КПИ {target_profit:g}₽ после издержек)")
        return out
    v = floor_hit(cur, cost_f, target_profit=target_profit, delivery=d, fee=f)
    out["current"] = {"price": cur, **v}
    if not v["ok"]:
        rec = fl
        out.update(recommended=rec, verdict="RAISE", crossed=crossed_price(rec, min_gap=min_gap))
        net_txt = f"{v['net']:g}₽" if v.get("net") is not None else "net не посчитан"
        out["note"] = (f"текущая {cur:g}₽ ниже пола {fl}₽ ({net_txt} < "
                       f"{target_profit:g}₽) — поднять минимум до {fl}₽")
    elif cur < zlow:
        rec = _mid(zlow, zhigh)
        out.update(recommended=rec, verdict="SWEET" if branded else "ZONE_RAISE",
                   crossed=crossed_price(rec, min_gap=min_gap))
        if branded:
            out["note"] = (f"текущая {cur:g}₽ даёт КПИ, но ниже зоны {zlow}–{zhigh}₽ "
                           f"сладкой зоны фирменного товара — поднять до {rec}₽ (дизайн-профит)")
        else:
            out["note"] = (f"текущая {cur:g}₽ даёт КПИ, но ниже зоны {zlow}–{zhigh}₽ — "
                           f"поднять до {rec}₽")
    else:
        # держим (OK-удержание — решение оператора, авто-снижения НЕТ) — но НЕ врём:
        # #14 ставил флаги только для cur > zhigh, а округление зоны к «полке» МАСКИРОВАЛО
        # над-потолочные цены (cost 533 → зона до 5400, а cur 5390 > ×10 потолок 5333 пряталась
        # «в зоне»). Потолок ×CEIL проверяем НЕЗАВИСИМО от распечатанной зоны.
        rec = int(cur)
        out.update(recommended=rec, verdict="OK", crossed=crossed_price(rec, min_gap=min_gap))
        over_ceiling = cur > cost_f * CEIL_MULT
        if (cur <= zhigh) and not over_ceiling:
            out["note"] = f"текущая {cur:g}₽ в зоне {zlow}–{zhigh}₽: КПИ есть, держим"
        else:
            above = cur > zhigh
            out["above_zone"] = above
            out["over_ceiling"] = bool(over_ceiling)
            parts = []
            if above:
                parts.append(f"ВЫШЕ зоны {zlow}–{zhigh}₽ (×{cur / cost_f:g} от закупки)")
            if over_ceiling:
                parts.append(f"потолок ×{CEIL_MULT:g} ({cost_f * CEIL_MULT:g}₽) ПРОБИТ")
            tail = (f"в пределах потолка ×{CEIL_MULT:g}"
                    if not over_ceiling else "решение за оператором")
            out["note"] = (f"текущая {cur:g}₽ — " + "; ".join(parts) +
                           f" — КПИ есть, держим; {tail}")
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

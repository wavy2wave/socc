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

def _f(x):
    """Один чок-поинт числа ценового канала (#21): bool (JSON true/false) — НЕ число, а подкласс
    int: float(True)=1.0 ложно проходил isfinite>0 и строил цену/пол/зону/акцию от выдуманной
    «закупки 1₽». Битое/огромное (10**400 → OverflowError, 'abc' → ValueError) и bool → nan:
    существующие isfinite-гейты честно откажут. СТРОКИ-ЧИСЛА ('0.15','1300','500') ПАРСЯТСЯ —
    контракт #16: мусор ≠ число, но число строкой валидно (канал из JSON/донора)."""
    if isinstance(x, bool):
        return float("nan")
    try:
        return float(x)
    except (TypeError, ValueError, OverflowError):
        return float("nan")


def _resolve_io(delivery, fee):
    """Дефолты доставки/комиссии ТОЛЬКО если не переданы явно (None-sentinel). Возвращает
    (delivery, fee, provisional): provisional=True значит «считано на НЕподтверждённых
    оператором TUNABLE-дефолтах» — такой вердикт совет, а не приговор (см. recommend)."""
    d = DELIVERY_DEFAULT if delivery is None else delivery
    f = FEE_DEFAULT if fee is None else fee
    # #16/#21: битые доставка/комиссия (10**400 → OverflowError, 'abc' → ValueError, bool → 1.0)
    # не должны крэшить формулу или «давать комиссию 1.0»: _f → nan провалит гейты `0 < f < 1` /
    # `d < 0` / isfinite у вызывающих.
    return _f(d), _f(f), (delivery is None) or (fee is None)


def net_profit(price, cost, *, delivery=None, fee=None):
    """Чистый профит заказа ПОСЛЕ издержек: price·(1−fee) − cost − delivery (P1).

    ОДНО округление до копейки десятичной арифметикой (Decimal, half-even): без пред-
    округления цены и без двойного округления комиссии. 3-й десятичный знак цены не
    теряется (price 800.015 → net 430.01, а НЕ 430.02 — старое пред-округление цены
    до копейки роняло полкопейки и сдвигало net). Честно: цена/закупка ≤0, NaN/inf или
    fee вне (0,1) → None (не выдумываем, P8)."""
    price, cost = _f(price), _f(cost)
    # #16: nan/inf ЛОЖНО проходят `<= 0` (nan<=0 == False) и утекали в Decimal-арифметику
    # как nan → floor_hit врал «net nan < пола». #21: bool — не число (float(True)=1.0 ложно
    # давал «закупку 1₽»). Только КОНЕЧНОЕ положительное — честный net.
    if not math.isfinite(price) or not math.isfinite(cost) or price <= 0 or cost <= 0:
        return None
    d, f, _ = _resolve_io(delivery, fee)
    if (not (0 < f < 1) or d < 0
            or not math.isfinite(d) or not math.isfinite(f)):
        return None
    try:
        from decimal import Decimal, ROUND_HALF_EVEN
        net = Decimal(str(price)) * (Decimal("1") - Decimal(str(f))) \
            - Decimal(str(cost)) - Decimal(str(d))
        try:
            return float(net.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))
        except (ArithmeticError, ValueError):
            # #21 (F9/F10): копеечное округление ОГРОМНОГО конечного net требует коэффициент
            # >28 знаков → quantize кидает InvalidOperation (ArithmeticError) и весь net_profit
            # возвращал None → floor_hit/promo_card/recommend ВРАЛИ (RAISE/NA/BAD_PARAMS «закупка
            # не дана» при честно огромном net). На таком масштабе копейки бессмысленны — честен
            # сам конечный net. Не конечен при float() (переполнение) → честно None.
            q = float(net)
            return q if math.isfinite(q) else None
    except (TypeError, ValueError, ArithmeticError):
        return None


def floor_price(cost, *, target_profit=NET_FLOOR, delivery=None, fee=None,
                step=50):
    """P3: минимальная цена, дающая target_profit чистыми: (cost + delivery + target)/(1−fee), вверх до step."""
    cost = _f(cost)
    # #16: нан/inf (nan<=0 ложно) или огромная cost крэшили int(math.ceil()) сырым
    # OverflowError. #21: bool-cost (JSON true) — не число (float(True)=1.0 строил пол от
    # «закупки 1₽»). Пол обязан быть КОНЕЧНЫМ числом — иначе честно None.
    if not math.isfinite(cost) or cost <= 0:
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
    tp = _f(NET_FLOOR if target_profit is None else target_profit)
    st = _f(step)
    # #21: bool-цель/шаг (JSON true → 1.0) — не число политики; битое/огромное _f сводит к nan.
    if not math.isfinite(tp) or tp <= 0 or not math.isfinite(st) or st <= 0:
        return None
    raw = (cost + d + tp) / (1 - f)
    if not math.isfinite(raw):
        return None                            # пол переполнил float (cost ~1e308) → честно нет пола
    q = raw / st                               # #16-residual: крошечный step (1e-300) → q = inf
    if not math.isfinite(q):
        return None                            # → int(ceil(inf)) падал сырым OverflowError; честно None
    # вверх к «круглому» шагу (50₽) — торговая полка, не дробный копеечный минимум
    res = int(math.ceil(q)) * st
    # #21 (F2): огромная конечная cost + float-step: int·float переполняла float → inf утекал
    # после всех гейтов как НЕКОНЕЧНЫЙ пол (враньё/крэш у сравнений). Пол обязан быть конечным.
    return None if not math.isfinite(res) else res


def floor_hit(price, cost, *, target_profit=NET_FLOOR, delivery=None, fee=None):
    """P4: честный вердикт по действующей цене. Возвращает dict с net, полом и вердиктом.
    provisional=True, если delivery/fee не заданы явно (счёт на неподтверждённых дефолтах)."""
    d, f, prov = _resolve_io(delivery, fee)
    # #16-residual: floor_hit был ЕДИНСТВЕННОЙ функцией канала без нормализации входов —
    # float(10**400) (JSON-int) падал СЫРЫМ OverflowError (в except только (TypeError, ValueError)),
    # строка-цена '1300' доходила до gap `fl - price` → TypeError (1200 - '1300'), а строка-цель
    # '500' чинилась ТОЛЬКО внутри floor_price, но сравнение net шло с СЫРОЙ целью. Всё парсим
    # КАК net_profit (float + isfinite + >0): строка-число работает, битое/огромное → честный вердикт.
    price_f, cost_f = _f(price), _f(cost)
    tp = _f(NET_FLOOR if target_profit is None else target_profit)
    if not (math.isfinite(price_f) and price_f > 0
            and math.isfinite(cost_f) and cost_f > 0):
        return {"ok": False, "verdict": "NA", "provisional": prov,
                "note": "цена/закупка не даны честно (P8)"}
    if not (math.isfinite(tp) and tp > 0):
        # #21: цель КПИ бита (bool/строка-не-число/≤0/не конечна) — параметр политики, а не данные
        # цены: пол не считаем по ПРИЧИНЕ цели (P7), НЕ «закупка не дана» (иначе врало бы про P8).
        return {"ok": False, "verdict": "BAD_PARAMS", "provisional": prov,
                "note": "цель КПИ не дана честно (≤0/не конечна/не число) — пол не считаем (P7)"}
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
        # Цель/параметры уже гейтнуты выше → fl=None здесь значит: закупка так велика, что пол
        # переполнил float (#21 F10). Это НЕ BAD_PARAMS про конфиг оператора (его параметры целы) —
        # честно: на этой шкале пол не посчитать (P8). net несём как есть (конечен после #21).
        return {"ok": False, "verdict": "NA", "provisional": prov,
                "note": "закупка за пределами честной ценовой шкалы — пол переполняет float (P8)",
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
    cost = _f(cost)
    # #16: нан/inf крэшили _round_up; #21: bool-cost (JSON true) — не число (float(True)=1.0 давал
    # «зону ×8 от закупки 1₽» — враньё). Битый/неконечный/неположительный cost → None (P8).
    if not math.isfinite(cost) or cost <= 0:
        return None
    # #23: sibling-параметры lo/hi/floor/ceil_mult — последние сырые float()-слоты канала цены.
    # Раньше lo/hi чистились float()+сравнением, но bool lo=True (JSON true) читался как «×1.0»
    # и давал «сладкую зону» от закупки 1:1 (враньё P6), floor=True → «пол 1₽»; ceil_mult НЕ
    # чистился ВООБЩЕ: 'abc'/10**400 → сырой TypeError/OverflowError (крэш партии), True/−5 → зона
    # схлопывалась в точку (низ==верх), nan тихо снимал потолок. _f (bool→nan, не-число→nan) +
    # конечность: битый параметр политики → честно None (P8), не крэш и не враньё.
    lo, hi = _f(lo), _f(hi)
    if not (math.isfinite(lo) and math.isfinite(hi) and lo > 0 and hi >= lo):
        return None
    fl = 0.0 if floor is None else _f(floor)
    if not math.isfinite(fl):
        return None
    cm = 0.0 if ceil_mult is None else _f(ceil_mult)   # None = «без потолка» (как 0/0.0, прежний falsy)
    if not (math.isfinite(cm) and cm >= 0):
        return None
    low_raw = max(cost * lo, fl)
    high_raw = max(cost * hi, low_raw)            # не инвертируем: high ≥ low всегда
    cap = cost * cm if cm else float("inf")
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
    sell_price = _f(sell_price)
    # #21: bool-цена — не число (float(True)=1.0 строил якорь от «цены 1₽»). Честно None (P8).
    if not math.isfinite(sell_price) or sell_price <= 0:
        return None
    # #22: sibling-параметры (min_gap/mult/step) НЕ чистились — тот же канал, что step/delivery/fee
    # в floor_price (PR33) и цель в recommend/floor_hit (#21 F5). min_gap/mult 'abc'/None роняли
    # СЫРЫМ TypeError, step 0 → ZeroDivisionError, step nan → ValueError, а min_gap nan/True/0 и
    # mult True/1.0 ТИХО глотались (якорь «как без разрыва»). _f(bool)→nan закрывает bool-слоты.
    # Параметр политики бит → якоря честно НЕТ (None), не враньё и не крэш.
    min_gap = _f(min_gap)
    mult = _f(mult)
    step = _f(step)
    if not (math.isfinite(min_gap) and math.isfinite(mult) and math.isfinite(step)
            and min_gap >= 0 and mult > 0 and step > 0):
        return None
    anchor = max(sell_price * mult, sell_price + min_gap)
    # #16-residual: sell конечна, но sell×1.25 переполняет float (→ inf) для sell ≳ 1.4e308 →
    # _round_up(ceil(inf)) падал сырым OverflowError. Якоря при таком масштабе честно нет → None.
    # #22: якорь ОБЯЗАН быть СТРОГО выше продажи (P5): mult≤1 и/или разрыв ≤0 съедают наценку →
    # anchor ≤ sell → discount_base ≤ value на витрине (фальшивая «скидка»). Такой не-якорь — None.
    if not math.isfinite(anchor) or not anchor > sell_price:
        return None
    return _round_up(anchor, step)


def _mid(a, b):
    """Середина зоны до 100₽ — «одно число» рекомендации без псевдо-точности."""
    # #16-residual: зона настолько велика, что (a+b)/2.0 переполняет float (сумма int-ов > floatmax
    # → int/float-деление кидает OverflowError, не inf). Середины честно нет → None (рекомендую
    # не выдумываем). Recommend выше отказывает таким зонам до _mid — тут страховка прямых вызовов.
    # #21: bool/битые границы → _f(nan) → mid nan → None ниже (гейт isfinite).
    mid = (_f(a) + _f(b)) / 200.0
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
    cost_f = _f(cost)
    # #21: bool-cost (JSON true) — не число (float(True)=1.0 строил пол/зону от «закупки 1₽»).
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
    # #21 (F5): цель КПИ нормализуем ОДИН раз ДО floor_price/нот. Раньше цель строкой ('abc'/'500')/
    # bool (true→1.0) шла СЫРОЙ в формулу и ноты {target_profit:g}: не-число роняло ноту TypeError
    # (а '500' в SET-ноте печаталось криво), bool-1.0 ложно «давал КПИ 1₽», битая цель падала в
    # fl=None и ВРАЛА NO_COST про закупку. Цель — параметр политики: битая → BAD_PARAMS (P7).
    tp = _f(NET_FLOOR if target_profit is None else target_profit)
    if not math.isfinite(tp) or tp <= 0:
        return {"ok": False, "verdict": "BAD_PARAMS", "cost": cost_f, "provisional": prov,
                "note": "закупка есть, но цель КПИ не дана честно (≤0/не конечна/не число) — пол не считаем (P7)"}
    fl = floor_price(cost_f, target_profit=tp, delivery=d, fee=f)
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
        cf = _f(current_price)   # #21: bool/битое → nan → «цены ещё нет» (SET), НЕ цена 1.0
        if math.isfinite(cf) and cf > 0:
            cur = cf
    if cur is None:
        rec = _mid(zlow, zhigh)
        out.update(recommended=rec, verdict="SET", crossed=crossed_price(rec, min_gap=min_gap))
        out["note"] = (f"цены нет: зона {zlow}–{zhigh}₽, рекомендую {rec}₽ "
                       f"(КПИ {tp:g}₽ после издержек)")
        return out
    v = floor_hit(cur, cost_f, target_profit=tp, delivery=d, fee=f)
    out["current"] = {"price": cur, **v}
    if not v["ok"]:
        rec = fl
        out.update(recommended=rec, verdict="RAISE", crossed=crossed_price(rec, min_gap=min_gap))
        net_txt = f"{v['net']:g}₽" if v.get("net") is not None else "net не посчитан"
        out["note"] = (f"текущая {cur:g}₽ ниже пола {fl}₽ ({net_txt} < "
                       f"{tp:g}₽) — поднять минимум до {fl}₽")
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
    """КПИ заказа: по факту net (после доставки) — попал ли в цель. Пусто/бито → None.

    #22: цель КПИ и сам net — тот же канал, что цель floor_price/floor_hit/recommend (#21 F5):
    net 'abc' ронял СЫРЫМ TypeError (net >= target), target 'abc' → TypeError, target nan давал
    ok=False «не достигнут» при битой цели (враньё про результат). Битый вход → честно None
    (КПИ не знаем), как net is None. Число-строка работает (net '605' / target '500')."""
    if net is None:
        return None
    net = _f(net)
    target = _f(NET_FLOOR if target is None else target)
    if not (math.isfinite(net) and math.isfinite(target) and target > 0):
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

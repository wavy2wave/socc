#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЦЕНОВИК·ПЛАН (ymarket_pricing_plan_v1) — сухой план переценки партии для утверждения оператором.

ЗАЧЕМ. ЦЕНОВИК·ПРАВИЛА (price_rules_v1) умеет решать по одной цене: пол КПИ (P3), сладкая зона
(P6), якорь зачёркивания (P5). Но движок до сих пор печатал только СЧЁТЧИКИ вердиктов в note СБОРКИ
(«2/4 в зоне, вне зоны {...}»), а оператору для слова «да/нет» нужен РАЗБОР ПО КАРТОЧКЕ: какая
цена сейчас, до какого числа поднять, что поставить якорем, почему. Этот модуль — форма этого
разбора: чистая математика НАД price_rules_v1 (ничего не пишет, наружу не ходит — 0₽, RUBICON цел).

МЕСТО В РЯДУ (не дублируем):
  role_pricer  — пол МАРЖИ по ЖИВЫМ тарифам Маркета (калькулятор, сеть READ) + allowed/refused.
  price_rules  — решающий слой политики: КПИ после доставки, пол, зона ×8–10, якорь (чистая).
  pricing_plan — ЭТОТ: рендер плана партии из price_rules для утверждения оператором/движком.
  Роль не подменяет apply_prices: показывает, что ПОСТАВИТЬ; само выставление — отдельный шаг
  с явным словом оператора (RUBICON: никакой записи здесь).

ВХОД — карточки партии {offer_id, cost, price}: cost = ЗАКУПКА (живой скан донора), price =
действующая ВИТРИННАЯ цена (чтение campaign_offers / леджер). Подаёт движок на СБОРКЕ или
оператор из чтения. Цены НЕ трогаем — только план (все числа помечены provisional, если
доставка/комиссия не подтверждены оператором явно).

ЗАКОНЫ (механические, покрыты приёмкой run_pricing_plan):
  PP1 ничего не пишем и наружу не ходим: чистая математика над price_rules_v1.
  PP2 план — по КАРТОЧКЕ (offer_id + закупка + действующая цена + что поставить), а не счётчики.
  PP3 вердикт и числа делегированы price_rules_v1.recommend (одна правда, не вторая копия).
  PP4 честность: нет закупки → NO_COST (рекомендации нет, не выдумываем); цена не дана → SET
      (рекомендуем середину зоны); provisional=True пока delivery/fee НЕ подтверждены явно.
  PP5 сортировка по ГЛАВНОМУ для оператора: RAISE (не даёт КПИ) → SWEET/ZONE_RAISE (в зону) →
      SET → OK (держим) — что чинить сначала.
  PP6 якорь зачёркивания ВСЕГДА выше рекомендованной (нет фальшивой «скидки», P5 price_rules).
  PP7 gap = сколько ₽ поднять до рекомендованного (0 при OK) — оператору на утверждение.
"""
from __future__ import annotations

import math

import ymarket_price_rules_v1 as R

# Порядок главности для оператора (PP5): что чинить сначала.
_URGENCY = {"RAISE": 0, "SWEET": 1, "ZONE_RAISE": 1, "SET": 2, "OK": 3}


def _net_at(price, cost, delivery, fee):
    """net по действующей цене (для колонки «что даёт сейчас»). Нет данных → None (PP4)."""
    try:
        return R.net_profit(price, cost, delivery=delivery, fee=fee)
    except Exception:
        return None


def plan_cards(cards, *, delivery=None, fee=None, branded=True):
    """План переценки партии. cards = [{offer_id, cost, price?}] → список строк (PP2/PP3).

    Каждая строка = решающий разбор price_rules_v1.recommend + offer_id + net по действующей
    цене + gap (до рекомендованного). provisional=True, пока delivery/fee не переданы явно (PP4).
    Сортировка: RAISE → SWEET/ZONE_RAISE → SET → OK, внутри — исходный порядок (PP5).
    Пусто → []. Битые строки не роняют партию: честный разбор вместо исключения.
    """
    d, f, prov = R._resolve_io(delivery, fee)
    rows = []
    for i, c in enumerate(cards or []):
        c = c or {}
        oid = c.get("offer_id") or c.get("sku")
        cost, price = c.get("cost"), c.get("price")
        # СЫРЫЕ delivery/fee (None-sentinel), НЕ резолвленные дефолты: recommend сам взводит
        # provisional=True, пока оператор не подтвердил TUNABLE (PP4). Резолвленные d/f —
        # только для net по действующей цене ниже.
        r = R.recommend(cost, current_price=price, delivery=delivery, fee=fee, branded=branded)
        cur = r.get("current") or {}
        net = _net_at(price, cost, d, f)
        rec = r.get("recommended")
        # #16: цена карточки из чтения может прийти НЕ числом ('abc') или nan/inf (json '1e400').
        # float('abc') → ValueError ронял ВЕСЬ план; rec − inf давал gap=-inf → '+−inf₽' в рендере.
        # Грязная цена → честный gap 0 (раз план не знает, сколько поднимать), партия жива.
        gap = 0.0
        if rec is not None and price:
            try:
                price_f = float(price)
                if math.isfinite(price_f):
                    gap = round(rec - price_f, 2)
            except (TypeError, ValueError, OverflowError):
                pass
        rows.append({
            "offer_id": oid,
            "cost": cost,
            "price": price,
            "verdict": r.get("verdict"),
            "provisional": r.get("provisional", prov),
            "floor": r.get("floor"),
            "zone": r.get("zone", {}),
            "recommended": rec,
            "crossed": r.get("crossed"),
            "net": net,
            "current_ok": cur.get("ok"),
            "gap": gap,
            "note": r.get("note"),
            "_i": i,                      # исходный индекс: стабильная сортировка (PP5)
        })
    # Главность вердикта → внутри — исходный порядок партии.
    rows.sort(key=lambda x: (_URGENCY.get(x["verdict"], 9), x["_i"]))
    for x in rows:
        x.pop("_i", None)
    return rows


def summary(rows):
    """Сжатая сводка для пульса: сколько чинить, сколько держим, provisional ли всё."""
    cnt = {}
    for x in rows:
        cnt[x["verdict"]] = cnt.get(x["verdict"], 0) + 1
    prov = any(x.get("provisional") for x in rows)
    urgent = {v: cnt.get(v, 0) for v in ("RAISE", "SWEET", "ZONE_RAISE") if cnt.get(v)}
    return {"rows": len(rows), "by_verdict": cnt, "urgent": urgent, "provisional": prov}


def _num(v, unit="₽"):
    if v is None:
        return "—"
    try:
        return f"{float(v):g}{unit}"
    except (TypeError, ValueError, OverflowError):   # #16: float(10**400) → OverflowError, не только ValueError
        return "—"


def render_plan(rows, *, delivery=None, fee=None):
    """Человеческая таблица для утверждения. Ничего не пишет — строки для вывода.

    Каждая карточка = строка: offer_id · закупка → действующая · вердикт · пол · зона ·
    рекомендую · якорь · net. Баннер provisional, если доставка/комиссия не подтверждены (PP4).
    Пустой план → []: нулю карточек нечего подтверждать, ПРОЕКТ-баннер не печатаем (PP11).
    """
    rows = list(rows or [])
    if not rows:
        return []
    d, f, prov = R._resolve_io(delivery, fee)
    out = []
    head = (f"ЦЕНОВИК·ПЛАН переценки ({len(rows)} карточек)"
            + (f" · ПРОЕКТ: доставка {d:g}₽/комиссия {f:.0%} НЕ подтверждены оператором" if prov
               else f" · доставка {d:g}₽/комиссия {f:.0%} подтверждены"))
    out.append(head)
    out.append("-" * len(head))
    for x in rows:
        z = x.get("zone") or {}
        out.append(
            f"{x['offer_id']:<14} закуп {_num(x['cost'])} → витрина {_num(x['price'])} · "
            f"{x['verdict']:<10} пол {_num(x['floor'])} · зона {_num(z.get('low'))}–"
            f"{_num(z.get('high'))} · рекомендую {_num(x['recommended'])} · якорь "
            f"{_num(x['crossed'])} · net {_num(x['net'])}" + (f" · +{x['gap']:g}₽" if x["gap"] else ""))
        if x.get("note"):
            out.append(f"    ↳ {x['note']}")
    if prov:
        out.append("ВНИМАНИЕ: цифры provisional (TUNABLE доставка/комиссия по умолчанию) — "
                   "это СОВЕТ для утверждения, не приказ. Гейтом движка не является.")
    return out


def print_plan(rows, *, delivery=None, fee=None):
    """Вывод плана в консоль (для CLI/движка). Никакой записи наружу."""
    for line in render_plan(rows, delivery=delivery, fee=fee):
        print(line)


# ─────────────────────────────────────────────────────────────────────────────
#  СЛОЙ «АКЦИИ» (зачёркнутая цена на витрине) — решение, НЕ запись
#
#  L9 движка ЦИКЛ-1: «товар НИ В КАКИХ акциях в цикл-1». Акция — ОТДЕЛЬНАЯ витринная
#  операция ЦЕНОВИКА: снизить цену под распродажу, поставив discountBase (зачёркнутую)
#  реальной обычной цены. Этот слой СЧИТАЕТ и проверяет payload для trade.update_prices,
#  ничего не пишет и наружу не ходит (0₽, RUBICON цел — запись только по слову оператора).
#
#  Законы (покрыты приёмкой run_pricing_plan, PR12–PR16):
#    PR1  акция ≠ цикл-1: модуль считает решение, запись — отдельный шаг (L9/PP1).
#    PR2  якорь реальный: regular (зачёркнутая) — обычная цена, что реально стоит на витрине/
#         выдержана; regular ≤ sell → «не скидка» → отказ (не рисуем фальшивый якорь, P4).
#    PR3  скидка по правилу Маркета 5–99%: вне диапазона → отказ (P4).
#    PR4  sell ≥ пол ЦЕНОВИКА (нет убытка, P1): ниже пола → отказ; пол из cost+издержек.
#    PR5  нет закупки → пол не посчитать → акция невозможна честно (P2): NO_COST.
#    PR6  provisional честно в решении, пока delivery/fee не подтверждены (как PP4).
# ─────────────────────────────────────────────────────────────────────────────

# Вердикты акции (короткие, для рендера/отказной строки).
PROMO_OK = "OK"            # payload готов {sku, value: sell, discount_base: regular}
PROMO_VERDICTS = ("OK", "NO_COST", "NO_PRICE", "NO_SELL", "NOT_SALE",
                  "DISCOUNT_RANGE", "BELOW_FLOOR", "BAD_PARAMS")


def promo_card(card, *, sell, regular=None, delivery=None, fee=None, target_profit=None):
    """Акция ОДНОЙ карточки: валидный ли payload {sku, value, discount_base} и почему.

    card = {offer_id|sku, cost, price?} — price = действующая витринная цена (по умолчанию
    regular-якорь: реальная цена, что стоит на витрине сейчас, PR2). sell = цена распродажи
    (решает оператор, не выдумываем). regular, если задан явно, — выдержанная обычная цена.
    Пол считаем из cost сырыми delivery/fee → provisional (PR6). Чистая, ничего не пишет.
    """
    sku = (card or {}).get("offer_id") or (card or {}).get("sku")
    cost = (card or {}).get("cost")
    cur = (card or {}).get("price")
    # #21: bool (JSON true/false) — тип-коррупция как bool-cost (#16/#19): float(True)=1.0 ложно
    # «давал закупку/цену» и строил акцию cost=1/якорь=1 (враньё). bool → None: гейты ниже честно
    # откажут (NO_COST/NO_PRICE).
    cost = None if isinstance(cost, bool) else cost
    cur = None if isinstance(cur, bool) else cur
    try:
        cost = float(cost) if cost is not None else None
    except (TypeError, ValueError, OverflowError):    # #16: float(10**400) → OverflowError
        cost = None
    sell = None if isinstance(sell, bool) else sell    # #21: bool-sell — не цена распродажи
    try:
        sell = float(sell)
    except (TypeError, ValueError, OverflowError):
        sell = None
    explicit_regular = regular is not None            # якорь задан ЯВНО (выдержанная цена)
    if explicit_regular:
        regular = None if isinstance(regular, bool) else regular   # #21: bool-якорь не цена
        try:
            regular = float(regular)
        except (TypeError, ValueError, OverflowError):
            regular = None
    elif cur is not None:
        try:
            regular = float(cur)                      # по умолчанию = действующая витринная (PR2)
        except (TypeError, ValueError, OverflowError):
            regular = None
    else:
        regular = None

    d, f, prov = R._resolve_io(delivery, fee)
    # Происхождение якоря (basis) — НЕ врём: held = выдержанная (задали явно); current_vitrine =
    # подтянута с витрины по умолчанию. Раньше non-explicit regular помечался held, а OK-строка
    # перетирала в current_vitrine даже явный held — происхождение терялось.
    basis = None if regular is None else ("held" if explicit_regular else "current_vitrine")
    base = {"sku": sku, "cost": cost, "sell": sell, "regular": regular, "provisional": prov,
            "discount_pct": None, "floor": None, "net_at_sell": None, "payload": None,
            "basis": basis, "note": ""}

    # #16: нан/inf-закупка (json 'NaN'→nan) ЛОЖНО проходила `cost <= 0` (nan<=0 == False) и роняла
    # потом floor_hit/net враньём «ниже пола»; одна nan-карточка валила ВЕСЬ батч promo_cards.
    if cost is None or not math.isfinite(cost) or cost <= 0:
        return {**base, "ok": False, "verdict": "NO_COST",
                "note": "закупка неизвестна/≤0 → пол не посчитать, акция невозможна честно (P2/PR5)"}
    # #21 (F10): закупка конечна, но за пределами честной ценовой ШКАЛЫ акции — ТА же грань, где
    # recommend (#19) отказывает (зона cost×hi переполняет float / сумма границ > floatmax): это
    # НЕ «продажа ниже пола» (пола на этой шкале нет) и НЕ «конфиг оператора бит» (параметры целы)
    # — мусорная закупка масштаба → честный NO_COST (P8). Реальная закупка ≤ ~1e5 — вне зоны риска.
    _band = R.sweet_band(cost)
    if _band is None or not math.isfinite(float(_band["low"]) + float(_band["high"])):
        return {**base, "ok": False, "verdict": "NO_COST",
                "note": "закупка за пределами честной ценовой шкалы (переполняет float) — акцию не выдумываем (P8)"}
    if sell is None or not math.isfinite(sell) or sell <= 0:
        return {**base, "ok": False, "verdict": "NO_SELL",
                "note": "цена распродажи не задана/не конечна/≤0 — не выдумываем (PR4)"}
    if regular is None or not math.isfinite(regular) or regular <= 0:
        return {**base, "ok": False, "verdict": "NO_PRICE",
                "note": "нет реальной обычной цены-якоря (не конечна/≤0/нет витринной или выдержанной) — акция нечестна (PR2)"}
    if regular <= sell:
        return {**base, "ok": False, "verdict": "NOT_SALE",
                "note": f"якорь {regular:g}₽ ≤ продажи {sell:g}₽ — это не скидка, а подъём под видом акции (PR2)"}
    disc = (regular - sell) / regular
    # Решение по СКИДКЕ на том ЖЕ округлении, что и discount_pct наружу: вердикт и число
    # никогда не спорят. (Пограничная 4.995% раньше писала 5.0% в отказной строке — враньё.)
    pct = round(disc * 100, 2)
    base["discount_pct"] = pct
    if not (5.00 <= pct <= 99.00):
        return {**base, "ok": False, "verdict": "DISCOUNT_RANGE",
                "note": f"скидка {pct:g}% вне 5–99% по правилу Маркета (P4/PR3)"}
    h = R.floor_hit(sell, cost, delivery=d, fee=f,
                    **({} if target_profit is None else {"target_profit": target_profit}))
    base["floor"] = h.get("floor")
    base["net_at_sell"] = h.get("net")
    if not h.get("ok"):
        if h.get("verdict") == "BELOW_FLOOR":
            # Пол и net посчитаны честно (provisional на TUNABLE) — обычная отказная строка.
            base["note"] = (f"продажа {sell:g}₽ ниже пола {h['floor']}₽ (net {h['net']:g}₽) — "
                            f"убыток запрещён (P1/PR4)" + ("" if not prov else " · provisional"))
            return {**base, "ok": False, "verdict": "BELOW_FLOOR"}
        # Пол НЕ посчитан (BAD_PARAMS: комиссия вне (0,1)/доставка <0) — раньше тут был
        # f"{h.get('net'):g}" на None → TypeError (крэш партии). Не «ниже пола», а причина.
        base["note"] = (f"продажа {sell:g}₽: пол не посчитан — {h.get('note') or 'параметры биты'}"
                        + ("" if not prov else " · provisional"))
        return {**base, "ok": False,
                "verdict": h.get("verdict") if h.get("verdict") in PROMO_VERDICTS else "BAD_PARAMS"}
    base["payload"] = {"sku": sku, "value": sell, "discount_base": regular}
    base["note"] = (f"скидка {pct:g}% ({regular:g}₽ → {sell:g}₽), net {h['net']:g}₽ ≥ пола"
                    + ("" if not prov else " · PROVISIONAL (TUNABLE не подтверждены, PR6)"))
    return {**base, "ok": True, "verdict": "OK"}


def promo_cards(cards, *, sells=None, regulars=None, delivery=None, fee=None):
    """Пачка решений акции: cards + sells (одна цена распродажи на карточку, как для плана).

    sells — dict sku/offer_id→sell или список цен в порядке cards; regulars (опц.) —
    dict/список выдержанных обычных цен (иначе regular = действующая витринная, PR2).
    Возвращает список вердиктов promo_card (сорт: готовые → отказы). Пусто → [].
    """
    rows = []
    for i, c in enumerate(cards or []):
        sku = (c or {}).get("offer_id") or (c or {}).get("sku")
        sell = None
        if isinstance(sells, dict):
            sell = sells.get(sku)
        elif isinstance(sells, (list, tuple)) and i < len(sells):
            sell = sells[i]
        regular = None
        if isinstance(regulars, dict):
            regular = regulars.get(sku)
        elif isinstance(regulars, (list, tuple)) and i < len(regulars):
            regular = regulars[i]
        rows.append(promo_card(c, sell=sell, regular=regular, delivery=delivery, fee=fee))
    rows.sort(key=lambda x: 0 if x["ok"] else 1)
    return rows


def render_promo(rows):
    """Человеческая карточка решения акции (для утверждения). Строки, запись — отдельно."""
    rows = list(rows or [])
    if not rows:
        return []
    ok_n = sum(1 for x in rows if x["ok"])
    out = [f"АКЦИЯ · решение ({len(rows)} карточек, готово {ok_n}) — слой решения, запись по слову"]
    out.append("-" * 60)
    for x in rows:
        sku = x.get("sku") or "?"
        mark = "✅" if x["ok"] else "⛔"
        disc = f"{x['discount_pct']}%" if x.get("discount_pct") is not None else "—"
        out.append(f"{mark} {sku:<14} {x['verdict']:<14} {_num(x['regular'])} → {_num(x['sell'])} "
                   f"(−{disc}) · пол {_num(x.get('floor'))} · {x.get('note') or ''}")
        if x["ok"]:
            p = x["payload"]
            out.append(f"      payload → trade.update_prices: sku={p['sku']} value={p['value']:g}₽ "
                       f"discount_base={p['discount_base']:g}₽")
    if any(x.get("provisional") for x in rows):
        out.append("ВНИМАНИЕ: пол на provisional TUNABLE (доставка/комиссия не подтверждены) — "
                   "совет, не приказ (PR6).")
    return out


def print_promo(rows):
    for line in render_promo(rows):
        print(line)


if __name__ == "__main__":
    # Сухая демонстрация (0₽): живая плёночная партия из леджера 2026-09-02 16:40
    # (закупка = живой скан донора, витрина = чтение) — РОВНО те числа, что видит оператор.
    film = [
        {"offer_id": "ARB-87309612", "cost": 700.0, "price": 5600},
        {"offer_id": "ARB-29846713", "cost": 600.0, "price": 4800},
        {"offer_id": "ARB-53416854", "cost": 170.0, "price": 1360},
        {"offer_id": "ARB-87931769", "cost": 65.0, "price": 520},
    ]
    plan_rows = plan_cards(film)
    print_plan(plan_rows)
    s = summary(plan_rows)
    print("\nСводка:", s)

    # Слой АКЦИИ (решение, 0₽): примеры на той же партии — что реально на витрине.
    print("\n── АКЦИЯ · примеры решений (запись — только по слову оператора) ──")
    sell_map = {"ARB-29846713": 4200, "ARB-53416854": 1200}   # цены распродажи решает оператор
    print_promo(promo_cards(film, sells=sell_map))
    # отказ: «акция» с якорем ниже продажи — фальшь (PR2)
    fake = {"offer_id": "ARB-87931769", "cost": 65.0, "price": 520}
    print_promo([promo_card(fake, sell=1200, regular=520)])

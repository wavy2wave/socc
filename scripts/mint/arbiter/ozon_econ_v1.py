#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON ECON V1 — выгода-взвешивание для ОЗОН-МЕНЕДЖЕРА (чистая функция, 0₽).

«Цель — доход и его РОСТ.» Менеджеру мало знать ЧТО можно сделать — он должен знать, что ВЫГОДНЕЕ
прямо сейчас, и какая карточка тянет магазин вниз (красный индекс = невидимость). Этот слой даёт
честную арифметику приоритета поверх ФАКТА кабинета.

ЕДИНЫЙ ИСТОЧНИК КОНСТАНТ: socc_mint_prospect_v1 (NET_COEFF=0.298, DELIVERY_NET=₽325). Здесь их не
переопределяем — импортируем, чтобы два числа не разошлись (закон одного источника, ozon_truth_v1).

ИНДЕКС ЦЕН ОЗОНА — 3-й по силе рычаг: красный/жёлтый индекс = алгоритм перестаёт показывать карточку
= де-факто невидимость. Цвет важнее числа для решения «показывается или нет».

ЗАКОН (SOCC/MINT): stdlib-only, без сети, без денег, честные None (нет данных → не выдумываем число).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MINT = HERE.parent                       # scripts/mint
for _p in (str(HERE), str(MINT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import socc_mint_prospect_v1 as prospect   # noqa: E402  — единый источник экономики Озона

# Реэкспорт ФАКТА кабинета (не переопределяем — ссылаемся):
NET_COEFF = prospect.NET_COEFF            # 0.298 — доля цены до продавца после комиссии 53%
DELIVERY_NET = prospect.DELIVERY_NET      # ₽325 — доставка нетто

# Индекс цен Озона: цвет решает видимость. RED = карточку прячут из органики (де-факто мёртвая).
INDEX_GREEN, INDEX_YELLOW, INDEX_RED = "GREEN", "YELLOW", "RED"
_INDEX_GAP = {INDEX_GREEN: 0.0, INDEX_YELLOW: 0.5, INDEX_RED: 1.0}
# Синонимы, которые Ozon Seller API отдаёт в разных версиях (нормализуем к цвету):
_INDEX_ALIASES = {
    "green": INDEX_GREEN, "profit": INDEX_GREEN, "profitable": INDEX_GREEN,
    "super_profit": INDEX_GREEN, "без_риска": INDEX_GREEN,
    "yellow": INDEX_YELLOW, "avg_profit": INDEX_YELLOW, "moderate": INDEX_YELLOW,
    "red": INDEX_RED, "non_profit": INDEX_RED, "unprofitable": INDEX_RED,
    "without_index": None, "no_index": None, "": None,
}
DEFAULT_LABOR_RUB = 5.0   # условная «стоимость» тик-действия (чтобы отсекать бессмысленные шаги)


def _num(v):
    """Мягкое число: '99'/'1,2'/99 → float; None/мусор → None (не выдумываем 0)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def net_receipt(price):
    """Сколько дойдёт до продавца с цены после комиссии Озон (price × NET_COEFF). None-безопасно."""
    p = _num(price)
    return round(p * NET_COEFF, 2) if p is not None else None


def profit_net(price, cost, delivery=None):
    """Честная чистая прибыль: receipt − cost − доставка. delivery=None ⇒ факт кабинета ₽325.

    Любой None во входе → None (не выдумываем прибыль там, где нечем считать).
    """
    p, c = _num(price), _num(cost)
    if p is None or c is None:
        return None
    dlv = DELIVERY_NET if delivery is None else (_num(delivery) or 0.0)
    return round(p * NET_COEFF - c - dlv, 2)


def sku_margin(card, price=None, cost=None, delivery=None):
    """Маржа карточки — ЧЕСТНО, с пометкой basis (на чём посчитана).

    card — dict карточки (может нести price/cost). Нет цены → basis='no_price'; есть цена без
    закупки → basis='cost_only' (profit_net=None); обе есть → basis='full'. Никогда не врёт числом.
    """
    sell = _num(price)
    if sell is None and isinstance(card, dict):
        sell = _num(card.get("price"))
    buy = _num(cost)
    if buy is None and isinstance(card, dict):
        buy = _num(card.get("cost"))
    if sell is None:
        return {"price_sell": None, "cost_buy": buy, "receipt": None,
                "profit_net": None, "margin_pct": None, "basis": "no_price"}
    receipt = round(sell * NET_COEFF, 2)
    if buy is None:
        return {"price_sell": round(sell, 2), "cost_buy": None, "receipt": receipt,
                "profit_net": None, "margin_pct": None, "basis": "cost_only"}
    pn = profit_net(sell, buy, delivery)
    margin_pct = round((pn / sell) * 100, 1) if (pn is not None and sell > 0) else None
    return {"price_sell": round(sell, 2), "cost_buy": round(buy, 2), "receipt": receipt,
            "profit_net": pn, "margin_pct": margin_pct, "basis": "full"}


def index_color(price_index):
    """Нормализовать индекс цен (цвет/энум/строку) к GREEN|YELLOW|RED|None. None = индекса ещё нет.

    Число тоже принимаем: ≤1.0 → GREEN (мы не дороже рынка), ≤1.1 → YELLOW, иначе RED.
    """
    n = _num(price_index)
    if n is not None:
        if n <= 1.0:
            return INDEX_GREEN
        if n <= 1.1:
            return INDEX_YELLOW
        return INDEX_RED
    if isinstance(price_index, str):
        return _INDEX_ALIASES.get(price_index.strip().lower(), None)
    return None


def index_gap(price_index):
    """Разрыв индекса 0..1: GREEN→0, YELLOW→0.5, RED→1.0, нет данных→1.0 (неизвестное = стоит заняться)."""
    color = index_color(price_index)
    if color is None:
        return 1.0
    return _INDEX_GAP.get(color, 1.0)


def is_hidden_by_index(price_index):
    """КРАСНЫЙ индекс = карточку прячут из органики. True ⇒ карточка де-факто невидима, чинить срочно."""
    return index_color(price_index) == INDEX_RED


def priority_weight(margin, gap):
    """Вес «сделать первым» = выгода × (1 + разрыв_индекса). Больше маржа и хуже индекс → выше приоритет.

    margin — dict из sku_margin (profit_net может быть None → нейтраль 1.0). gap — из index_gap (0..1).
    Убыточная карточка (profit_net<0) → base 0.0 (вверх по выгоде не двигаем).
    """
    pn = margin.get("profit_net") if isinstance(margin, dict) else _num(margin)
    base = pn if isinstance(pn, (int, float)) else None
    if base is None:
        base = 1.0
    elif base < 0:
        base = 0.0
    g = _num(gap)
    g = 0.0 if g is None else max(0.0, min(1.0, g))
    return round(base * (1.0 + g), 4)


def action_pays(gain_estimate, labor_rub=DEFAULT_LABOR_RUB):
    """Окупается ли действие: прирост ₽ ≥ труд. gain=None → sound=True с assumed=True (не блокируем)."""
    labor = _num(labor_rub)
    labor = DEFAULT_LABOR_RUB if labor is None else labor
    gain = _num(gain_estimate)
    if gain is None:
        return {"sound": True, "assumed": True, "gain_estimate": None,
                "labor_rub": round(labor, 2), "net": None}
    net = round(gain - labor, 2)
    return {"sound": gain >= labor, "assumed": False, "gain_estimate": round(gain, 2),
            "labor_rub": round(labor, 2), "net": net}


if __name__ == "__main__":
    import json
    demo = {
        "net_coeff": NET_COEFF, "delivery_net": DELIVERY_NET,
        "receipt_990": net_receipt(990),
        "profit_990_cost400": profit_net(990, 400),
        "margin_full": sku_margin({"price": 990, "cost": 400}),
        "margin_cost_only": sku_margin({"price": 990}),
        "index_red_num": index_color(1.25), "index_green_word": index_color("PROFIT"),
        "hidden_when_red": is_hidden_by_index("NON_PROFIT"),
        "gap_red": index_gap("RED"), "gap_none": index_gap(None),
        "weight": priority_weight(sku_margin({"price": 990, "cost": 400}), index_gap("YELLOW")),
    }
    print(json.dumps(demo, ensure_ascii=False, indent=2))

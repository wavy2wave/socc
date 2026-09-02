#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОКНО НАЦЕНКИ по 20 плёнкам на подтверждённых сборах Маркета (офлайн, 0 ₽, сеть не нужна).

СБОРЫ ЭКСПРЕССА, категория 76346336 — сняты с калькулятора Маркета 2026-08-11
(POST /v2/tariffs/calculate, поле parameters[value], valueType=relative):
    FEE                 44.50 % от цены   ← ставка размещения, категорийная
    PAYMENT_TRANSFER     3.30 % от цены   ← перевод платежа
    AGENCY_COMMISSION    0.12 ₽           ← абсолютная копейка
    EXPRESS_DELIVERY     8.00 % от цены, минимум 100 ₽, максимум 1500 ₽
ТАРИФНЫЙ ОБРЫВ: вес ≥ 20 кг ИЛИ сумма трёх сторон ≥ 210 см → доставка плоские 1500 ₽/шт.

Итого Маркет забирает 55.8 % цены + доставку. Значит продавцу доходит 47.8 % цены
(до вычета доставки), и закупка должна уместиться в этот остаток.

ЧЕСТНОСТЬ: калькулятор Маркета сам помечен как ПРИМЕРНЫЙ — факт приезжает в отчётах.
Это оценка до первой реальной продажи, а не доказанный ₽.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_from_xlsx_v1 as fx  # noqa: E402

XLSX = "/Users/wavysexy/parsers/parsed_data/cargo-avto_MASTER_2026-08-03_03-06-11.xlsx"

FEE_PCT = 0.4450
PAYMENT_PCT = 0.0330
AGENCY_ABS = 0.12
DELIVERY_PCT = 0.0800
DELIVERY_MIN = 100.0
DELIVERY_MAX = 1500.0
CLIFF_WEIGHT_KG = 20.0
CLIFF_SUM_CM = 210.0
FLAT_HEAVY = 1500.0

# Доля цены, остающаяся продавцу ДО доставки
KEEP = 1.0 - FEE_PCT - PAYMENT_PCT          # 0.522

LIVE = {"9600154", "9600155", "9600239", "9600879", "9601440", "9601512", "9601513",
        "9601515", "9601516", "9602037", "9602468", "9602489", "9603273", "9604033",
        "9604035", "9604036", "9604815", "9604816", "9605336", "9605392"}


def over_cliff(p):
    dims = [p.get("length"), p.get("width"), p.get("height")]
    if not all(isinstance(d, (int, float)) and d > 0 for d in dims):
        return None
    w = p.get("weight")
    if not isinstance(w, (int, float)) or w <= 0:
        return None
    return (w >= CLIFF_WEIGHT_KG) or (sum(dims) >= CLIFF_SUM_CM)


def delivery_for(price, heavy):
    if heavy:
        return FLAT_HEAVY
    return min(max(price * DELIVERY_PCT, DELIVERY_MIN), DELIVERY_MAX)


def profit_at(price, cost, heavy):
    dlv = delivery_for(price, heavy)
    return price * KEEP - AGENCY_ABS - dlv - cost, dlv


def breakeven(cost, heavy):
    """Минимальная цена, при которой профит = 0. Аналитически, с учётом полки доставки."""
    if heavy:
        return (cost + FLAT_HEAVY + AGENCY_ABS) / KEEP
    # ветка минимальной доставки 100 ₽ (пока 8 % цены < 100, т.е. цена < 1250)
    p_min = (cost + DELIVERY_MIN + AGENCY_ABS) / KEEP
    if p_min < DELIVERY_MIN / DELIVERY_PCT:
        return p_min
    # ветка процентной доставки
    return (cost + AGENCY_ABS) / (KEEP - DELIVERY_PCT)


def min_markup_for_margin(cost, heavy, target=0.15, hi=40.0):
    """Наименьшая наценка, при которой профит ≥ target·цена. Бинарный поиск."""
    lo = 1.0
    if profit_at(cost * hi, cost, heavy)[0] < target * cost * hi:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        pr, _d = profit_at(cost * mid, cost, heavy)
        if pr >= target * cost * mid:
            hi = mid
        else:
            lo = mid
    return hi


def main():
    films = [p for p in fx.load_category(XLSX, slug="puzyrkovaya-plenka")["products"]
             if p["sku"].split("-")[0] in LIVE]
    films.sort(key=lambda p: -(p.get("cost") or 0))

    print("Маркет удерживает %.1f %% цены (FEE %.2f + перевод %.2f) + доставку сверху."
          % ((FEE_PCT + PAYMENT_PCT) * 100, FEE_PCT * 100, PAYMENT_PCT * 100))
    print("Продавцу доходит %.1f %% цены до вычета доставки и закупки.\n" % (KEEP * 100))

    print("%-12s%-12s%7s%6s%9s%8s%8s%8s%8s"
          % ("SKU", "размер", "закуп", "Σсм", "безуб.", "×3", "×4", "×5", "мин×15%"))
    print("-" * 86)

    dead, heavy_list = [], []
    for p in films:
        cost = p.get("cost") or 0
        heavy = over_cliff(p)
        sp = p.get("_spec", {})
        size = "%sx%s" % (sp.get("ширина_м"), sp.get("длина_м"))
        dim_sum = sum(x for x in (p.get("length"), p.get("width"), p.get("height")) if x) or 0
        be = breakeven(cost, heavy)
        cells = []
        for k in (3, 4, 5):
            pr, _ = profit_at(cost * k, cost, heavy)
            cells.append("%+8.0f" % pr)
        need = min_markup_for_margin(cost, heavy)
        if heavy:
            heavy_list.append(p["sku"])
        if need is None or need > 10:
            dead.append(p["sku"])
        print("%-12s%-12s%7.0f%6.0f%9.0f%s%s%s%8s"
              % (p["sku"], size, cost, dim_sum, be, cells[0], cells[1], cells[2],
                 ("×%.1f" % need) if need else "нет"))

    print("-" * 86)
    print("за тарифным обрывом (доставка 1500 ₽): %s" % (", ".join(heavy_list) or "нет"))
    print("не выходят в 15 %% маржи разумной наценкой: %s" % (", ".join(dead) or "нет"))


if __name__ == "__main__":
    main()

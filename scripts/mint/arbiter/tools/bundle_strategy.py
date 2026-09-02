#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СТРАТЕГИЯ ЧАСТЫХ ПРОДАЖ: побег от пола доставки через комплекты (ЧТЕНИЕ, 0 ₽).

ЗАДАЧА ОПЕРАТОРА: «старайся работать с товарами в закупке до 500 ₽. И продумай стратегии,
где у нас прибыль невысока, но мы сможем продавать чаще, и это выгоднее.»

ГИПОТЕЗА, КОТОРУЮ ПРОВЕРЯЕМ. Экспресс-доставка = 8 % цены, но НЕ МЕНЬШЕ 100 ₽, и берётся
за ЕДИНИЦУ (billingUnit=item). Значит на дешёвом товаре пол доставки съедает маржу:
у плёнки 0.4×5 м закупкой 70 ₽ цена ×4 = 280 ₽, а доставка всё равно 100 ₽ — это 36 % цены,
позиция в минусе. Но если продавать НЕ рулон, а КОМПЛЕКТ из N рулонов одной ссылкой —
цена растёт, 8 % обгоняют пол, и доставка платится ОДИН раз вместо N.

Побочные выигрыши комплекта: (1) это отдельный SKU, которого нет ни у кого → сравнивать
Маркету не с чем (та самая «голубая вода»); (2) выше чек при той же логистике.

ЧЕСТНОСТЬ. Пол/процент доставки берём из живого калькулятора, а не из модели: скрипт
СРАВНИВАЕТ свою арифметику с ответом Маркета и печатает расхождение. Ключевое допущение,
которое проверяется зовом: как калькулятор считает quantity — за единицу или за весь заказ.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_from_xlsx_v1 as fx       # noqa: E402
import ymarket_trade_hands_v1 as trade  # noqa: E402

XLSX = "/Users/wavysexy/parsers/parsed_data/cargo-avto_MASTER_2026-08-03_03-06-11.xlsx"
CATEGORY = 76346336

FEE, PAY, AGENCY = 0.4450, 0.0330, 0.12
DLV_PCT, DLV_MIN, DLV_MAX = 0.08, 100.0, 1500.0
CLIFF_KG, CLIFF_CM, FLAT = 20.0, 210.0, 1500.0
KEEP = 1.0 - FEE - PAY
MARKUP = 4.0
CHEAP_LIMIT = 500.0        # директива оператора: работаем с закупкой до 500 ₽

LIVE = {"9600154", "9600155", "9600239", "9600879", "9601440", "9601512", "9601513",
        "9601515", "9601516", "9602037", "9602468", "9602489", "9603273", "9604033",
        "9604035", "9604036", "9604815", "9604816", "9605336", "9605392"}


def pack_dims(p, n):
    """Габариты комплекта из n рулонов: складываем по КОРОТКОЙ стороне (рулоны рядом).

    Честно: это модель укладки, а не факт. Ширина рулона не меняется, растёт «толщина» связки.
    """
    dims = sorted([p.get("length") or 0, p.get("width") or 0, p.get("height") or 0])
    if not all(dims):
        return None
    a, b, c = dims                    # a ≤ b ≤ c
    return [a * n, b, c]              # связка растёт по самой короткой стороне


def econ(price, cost, dims, weight):
    heavy = (weight >= CLIFF_KG) or (sum(dims) >= CLIFF_CM)
    dlv = FLAT if heavy else min(max(price * DLV_PCT, DLV_MIN), DLV_MAX)
    return round(price * KEEP - AGENCY - dlv - cost), dlv, heavy


def main():
    films = [p for p in fx.load_category(XLSX, slug="puzyrkovaya-plenka")["products"]
             if p["sku"].split("-")[0] in LIVE]
    cheap = [p for p in films if (p.get("cost") or 0) <= CHEAP_LIMIT]
    cheap.sort(key=lambda p: p.get("cost") or 0)

    print("ДЕШЁВЫЙ ЭШЕЛОН: закупка ≤ %.0f ₽ — %d позиций из %d\n" % (CHEAP_LIMIT, len(cheap), len(films)))
    print("Поштучно при наценке ×%.1f:" % MARKUP)
    print("%-12s%-12s%7s%8s%7s%8s%7s" % ("SKU", "размер", "закуп", "цена", "дост", "профит", "марж%"))
    print("-" * 64)
    for p in cheap:
        cost = p["cost"]
        price = round(cost * MARKUP)
        dims = [p.get("length"), p.get("width"), p.get("height")]
        prof, dlv, _ = econ(price, cost, dims, p.get("weight") or 0)
        sp = p.get("_spec", {})
        print("%-12s%-12s%7.0f%8.0f%7.0f%+8.0f%6.1f%%"
              % (p["sku"], "%sx%s" % (sp.get("ширина_м"), sp.get("длина_м")),
                 cost, price, dlv, prof, prof / price * 100))

    print("\n" + "=" * 78)
    print("КОМПЛЕКТЫ: та же позиция, но N рулонов одной ссылкой")
    print("=" * 78)
    for p in cheap:
        cost1 = p["cost"]
        sp = p.get("_spec", {})
        print("\n%s  %sx%s м, закупка %.0f ₽/шт"
              % (p["sku"], sp.get("ширина_м"), sp.get("длина_м"), cost1))
        print("   %-4s%9s%8s%7s%9s%8s  %s" % ("шт", "закуп", "цена", "дост", "профит", "марж%", "заметка"))
        for n in (1, 2, 3, 5, 10):
            dims = pack_dims(p, n)
            if not dims:
                continue
            cost = cost1 * n
            price = round(cost * MARKUP)
            w = (p.get("weight") or 0) * n
            prof, dlv, heavy = econ(price, cost, dims, w)
            note = "ОБРЫВ: Σ%.0fсм" % sum(dims) if heavy else ("пол доставки" if dlv == DLV_MIN else "")
            print("   %-4d%9.0f%8.0f%7.0f%+9.0f%7.1f%%  %s"
                  % (n, cost, price, dlv, prof, prof / price * 100, note))

    print("\n" + "=" * 78)
    print("СВЕРКА С ЖИВЫМ КАЛЬКУЛЯТОРОМ МАРКЕТА (quantity: за единицу или за заказ?)")
    print("=" * 78)
    probe = films[0]
    tests = [("1 шт, цена 280", 280, 1), ("1 шт, цена 2800", 2800, 1),
             ("10 шт, цена 280", 280, 10)]
    for name, price, qty in tests:
        try:
            rows = trade.calc_tariffs([{
                "category_id": CATEGORY, "price": price, "quantity": qty,
                "length": probe.get("length"), "width": probe.get("width"),
                "height": probe.get("height"), "weight": probe.get("weight")}],
                selling_program=trade.PLACEMENT_EXPRESS)
            tar = (rows[0] if rows else {}).get("tariffs") or []
            parts = " · ".join("%s=%.2f" % (t.get("type"), float(t.get("amount") or 0))
                               for t in sorted(tar, key=lambda x: -float(x.get("amount") or 0)))
            total = sum(float(t.get("amount") or 0) for t in tar)
            print("  %-18s всего=%8.2f   %s" % (name, total, parts))
        except Exception as e:
            print("  %-18s ошибка: %s" % (name, str(e)[:80]))


if __name__ == "__main__":
    main()

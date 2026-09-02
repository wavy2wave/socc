#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СПИСОК НА ВЫКУП И СЪЁМКУ: что выкупаем первым (офлайн, 0 ₽).

Решение оператора 2026-08-11 (уточнено в тот же день): берём ВЕСЬ товар с закупом ≤ 700 ₽,
комплектов НЕТ — каждый рулон отдельной карточкой. Логика: не топить капитал в дорогой
Биг бабл (×10 = 44 000 ₽, спрос недоказан), а накрыть МНОГО дешёвых SKU по правдоподобным
ценникам (×5–10 держит рулон в 350…3700 ₽ — такое реально покупают). Больше карточек =
больше выстрелов, меньше риск на позицию. Путь №3 по фото: у донора ВСЕ снимки идут через
/watermark/ (чужой водяной знак), чистого близнеца по 13 типовым путям нет (404) — снимаем сами.

Сборы Экспресса, категория 76346336 (сняты с калькулятора Маркета 2026-08-11):
    FEE 44.50 % + PAYMENT_TRANSFER 3.30 % от цены, AGENCY_COMMISSION 0.12 ₽,
    EXPRESS_DELIVERY 8.00 % (мин 100, макс 1500);
    обрыв: вес ≥ 20 кг ИЛИ Σ сторон ≥ 210 см → доставка плоские 1500 ₽.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_from_xlsx_v1 as fx  # noqa: E402
import donor_stock_v1 as DS        # noqa: E402

XLSX = "/Users/wavysexy/parsers/parsed_data/cargo-avto_MASTER_2026-08-03_03-06-11.xlsx"

FEE, PAY, AGENCY = 0.4450, 0.0330, 0.12
DLV_PCT, DLV_MIN, DLV_MAX = 0.08, 100.0, 1500.0
CLIFF_KG, CLIFF_CM, FLAT = 20.0, 210.0, 1500.0
KEEP = 1.0 - FEE - PAY

# НАЦЕНКА — решение оператора 2026-08-11: политика ×5–10 на УНИКАЛЬНЫХ карточках
# Яндекса. Обоснование: свой EAN-13 рвёт склейку → «голубая вода», цену задаём мы,
# ценовой конкуренции с перекупами нет. НЕ путать с Озоном (pricing_v1.py): там индекс
# цен убивает высокую наценку, здесь — наоборот. Диапазон, а не точка: пол ×5 даёт маржу
# с большим запасом над порогом живой категории ×3.4; потолок ×10 ограничен только
# спросом («купят ли») — проверяется листингом, не расчётом.
MARKUP_FLOOR = 5.0
MARKUP_CEIL = 10.0
MARKUP = MARKUP_FLOOR   # дефолт для econ() = пол окна

# ЧТО ВЫКУПАЕМ (решение оператора 2026-08-11): весь товар с закупом ≤ 700 ₽, комплектов НЕТ.
# Не топим капитал в дорогой Биг бабл — накрываем много дешёвых SKU, у каждого своя карточка.
BUY_MAX_COST = 700.0

LIVE = {"9600154", "9600155", "9600239", "9600879", "9601440", "9601512", "9601513",
        "9601515", "9601516", "9602037", "9602468", "9602489", "9603273", "9604033",
        "9604035", "9604036", "9604815", "9604816", "9605336", "9605392"}


def heavy_of(p):
    dims = [p.get("length"), p.get("width"), p.get("height")]
    if not all(isinstance(d, (int, float)) and d > 0 for d in dims):
        return None
    w = p.get("weight")
    return (w >= CLIFF_KG) or (sum(dims) >= CLIFF_CM) if isinstance(w, (int, float)) else None


def econ(cost, heavy, markup=MARKUP):
    price = round(cost * markup)
    dlv = FLAT if heavy else min(max(price * DLV_PCT, DLV_MIN), DLV_MAX)
    profit = price * KEEP - AGENCY - dlv - cost
    return price, dlv, round(profit), round(profit / price * 100, 1) if price else 0


def main():
    films = [p for p in fx.load_category(XLSX, slug="puzyrkovaya-plenka")["products"]
             if p["sku"].split("-")[0] in LIVE]
    print("читаю живое наличие у донора...")
    DS.apply_to(films, DS.stock_for(sorted({p["sku"].split("-")[0] for p in films})))

    rows = []
    for p in films:
        cost = p.get("cost") or 0
        heavy = heavy_of(p)
        pf = econ(cost, heavy, MARKUP_FLOOR)   # (цена, дост, профит, марж%) на полу ×5
        pc = econ(cost, heavy, MARKUP_CEIL)    # на потолке ×10
        sp = p.get("_spec", {})
        rows.append({
            "sku": p["sku"], "cost": cost, "heavy": heavy,
            "price_f": pf[0], "profit_f": pf[2], "marg_f": pf[3],
            "price_c": pc[0], "profit_c": pc[2], "marg_c": pc[3],
            "size": "%sx%s" % (sp.get("ширина_м"), sp.get("длина_м")),
            "dens": sp.get("плотность_г_м2"),
            "stock": p.get("donor_stock"),
            "pics": len(p.get("pictures") or []),
        })
    rows.sort(key=lambda r: -r["profit_f"])

    print("\nОКНО НАЦЕНКИ ×%.0f–%.0f (решение оператора) · уникальная карточка, цену задаём мы\n"
          % (MARKUP_FLOOR, MARKUP_CEIL))
    print("%-11s%-11s%5s%7s │%8s%8s%6s │%8s%8s%6s │%9s"
          % ("SKU", "размер", "г/м²", "закуп",
             "цена×5", "проф×5", "м%×5", "цена×10", "проф×10", "м%×10", "донор"))
    print("-" * 96)
    for r in rows:
        print("%-11s%-11s%5s%7.0f │%8.0f%+8.0f%5.0f%% │%8.0f%+8.0f%5.0f%% │%9s"
              % (r["sku"], r["size"], r["dens"] or "?", r["cost"],
                 r["price_f"], r["profit_f"], r["marg_f"],
                 r["price_c"], r["profit_c"], r["marg_c"],
                 "в наличии" if r["stock"] == "in_stock" else "под заказ"))

    buy = [r for r in rows if r["cost"] <= BUY_MAX_COST]   # уже отсортированы по профиту ×5
    print("\n" + "=" * 96)
    print("СПИСОК НА ВЫКУП И СЪЁМКУ — весь товар закуп ≤ %.0f ₽ (комплектов нет, каждый рулон = карточка)"
          % BUY_MAX_COST)
    print("=" * 96)
    total = 0
    for i, r in enumerate(buy, 1):
        total += r["cost"]
        note = "" if r["stock"] == "in_stock" else "  ← под заказ, брать с задержкой"
        print("%2d. %-11s %-11s %s г/м²  закуп %4.0f ₽  цена %5.0f…%-5.0f ₽  профит %+5.0f…%+5.0f ₽%s"
              % (i, r["sku"], r["size"], r["dens"] or "?", r["cost"],
                 r["price_f"], r["price_c"], r["profit_f"], r["profit_c"], note))
    print("-" * 96)
    pf_sum = sum(r["profit_f"] for r in buy)
    pc_sum = sum(r["profit_c"] for r in buy)
    print("ИТОГО %d карточек · закупка %.0f ₽ · профит с одной продажи каждой: %+.0f ₽ (×5) … %+.0f ₽ (×10)"
          % (len(buy), total, pf_sum, pc_sum))
    print("одна продажа с каждой карточки окупает закуп в %.1f× (×5) … %.1f× (×10)"
          % (pf_sum / total if total else 0, pc_sum / total if total else 0))


if __name__ == "__main__":
    main()

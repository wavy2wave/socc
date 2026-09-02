#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""НАСТОЯЩИЕ СБОРЫ МАРКЕТА по одобренным позициям (ЧТЕНИЕ, 0 ₽).

ЗАЧЕМ. В воронке колонка «сборы» содержала ТОЛЬКО доставку по модели органа (8 % / плоские 1500).
Комиссия Маркета туда не входила — значит профит был завышен. Здесь зовём калькулятор самого
Маркета (/v2/tariffs/calculate) и раскладываем сбор по типам: размещение, агентская комиссия,
эквайринг, экспресс-доставка.

ЧЕСТНОСТЬ. Документация Маркета прямо предупреждает: расчёт ПРИМЕРНЫЙ, факт приезжает в отчётах.
Поэтому результат — оценка, а не доказанный ₽. Цена берётся как закупка × наценка (см. MARKUP).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_from_xlsx_v1 as fx           # noqa: E402
import ymarket_role_merchandiser_v1 as M    # noqa: E402
import ymarket_card_v1 as C                 # noqa: E402
import ymarket_trade_hands_v1 as trade      # noqa: E402
import donor_stock_v1 as DS                 # noqa: E402

XLSX = "/Users/wavysexy/parsers/parsed_data/cargo-avto_MASTER_2026-08-03_03-06-11.xlsx"
CATEGORY_ID = 76346336          # подтверждена боем: 4 живые карточки
MARKUP = 3.0                    # проверяем гипотезу ×3 (решение по наценке за оператором)

LIVE = {"9600154", "9600155", "9600239", "9600879", "9601440", "9601512", "9601513",
        "9601515", "9601516", "9602037", "9602468", "9602489", "9603273", "9604033",
        "9604035", "9604036", "9604815", "9604816", "9605336", "9605392"}


def main():
    films = [p for p in fx.load_category(XLSX, slug="puzyrkovaya-plenka")["products"]
             if p["sku"].split("-")[0] in LIVE]
    DS.apply_to(films, DS.stock_for(sorted({p["sku"].split("-")[0] for p in films})))
    res = M.screen(films, city="Москва", cats=C.load_cats())
    approved = res["approved"]
    by_sku = {p["sku"]: p for p in films}
    print("одобрено воронкой: %d · наценка гипотезы ×%.1f\n" % (len(approved), MARKUP))

    offers = []
    for a in approved:
        p = by_sku[a["sku"]]
        offers.append({"category_id": CATEGORY_ID, "price": round((p["cost"] or 0) * MARKUP),
                       "length": p.get("length"), "width": p.get("width"),
                       "height": p.get("height"), "weight": p.get("weight"), "quantity": 1})

    rows = trade.calc_tariffs(offers, selling_program=trade.PLACEMENT_EXPRESS)
    print("калькулятор вернул строк: %d\n" % len(rows))

    print("%-12s%8s%8s%9s%9s%9s%9s" % ("SKU", "закуп", "цена", "сборы", "из них", "профит", "марж%"))
    print("%-12s%8s%8s%9s%9s%9s%9s" % ("", "", "", "всего", "доставка", "", ""))
    print("-" * 66)
    kinds = {}
    tot_p = tot_f = 0.0
    for a, o, row in zip(approved, offers, rows):
        p = by_sku[a["sku"]]
        tar = (row or {}).get("tariffs") or []
        fees = 0.0
        dlv = 0.0
        for t in tar:
            amt = float(t.get("amount") or 0)
            kind = t.get("type") or "?"
            kinds[kind] = kinds.get(kind, 0.0) + amt
            fees += amt
            if "DELIVERY" in kind.upper():
                dlv += amt
        price = o["price"]
        profit = round(price - (p["cost"] or 0) - fees, 2)
        marg = round(profit / price * 100, 1) if price else 0
        tot_p += profit
        tot_f += fees
        print("%-12s%8.0f%8.0f%9.0f%9.0f%9.0f%8.1f%%"
              % (a["sku"], p["cost"], price, fees, dlv, profit, marg))

    print("-" * 66)
    print("ИТОГО профит: %.0f ₽ · сборов: %.0f ₽ · средний профит: %.0f ₽"
          % (tot_p, tot_f, tot_p / len(approved) if approved else 0))
    print("\nСБОРЫ ПО ТИПАМ (сумма по всем позициям):")
    for k, v in sorted(kinds.items(), key=lambda x: -x[1]):
        print("   %-26s %9.0f ₽" % (k, v))


if __name__ == "__main__":
    main()

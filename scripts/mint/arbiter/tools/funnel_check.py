#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Прогон плёнок через воронку ТОВАРОВЕДА (сухо, 0 ₽, наружу не ходит).

Проверяет стык загрузчик → роли после двух правок 2026-08-08/09:
плоские габариты (length/width/height/weight) и закупка (cost).
"""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_from_xlsx_v1 as fx           # noqa: E402
import ymarket_role_merchandiser_v1 as M    # noqa: E402
import ymarket_card_v1 as C                 # noqa: E402
import donor_stock_v1 as DS                 # noqa: E402

XLSX = "/Users/wavysexy/parsers/parsed_data/cargo-avto_MASTER_2026-08-03_03-06-11.xlsx"

# Артикулы, реально живущие в категории донора (сверено с живым сайтом 2026-08-08).
# Фильтр по слову «пузырьк» терял «Биг бабл» — берём по списку, а не по имени.
LIVE = {"9600154", "9600155", "9600239", "9600879", "9601440", "9601512", "9601513",
        "9601515", "9601516", "9602037", "9602468", "9602489", "9603273", "9604033",
        "9604035", "9604036", "9604815", "9604816", "9605336", "9605392"}


def main():
    prods = fx.load_category(XLSX, slug="puzyrkovaya-plenka")["products"]
    films = [p for p in prods if p["sku"].split("-")[0] in LIVE]
    print("позиций: %d | с закупкой: %d | с габаритами: %d"
          % (len(films),
             sum(1 for p in films if p.get("cost")),
             sum(1 for p in films if p.get("weight"))))

    # Наличие берём ЖИВЬЁМ с сайта донора: колонка XLSX пуста у половины позиций и стареет.
    print("читаю живое наличие у донора...")
    stock = DS.stock_for(sorted({p["sku"].split("-")[0] for p in films}))
    marked = DS.apply_to(films, stock)
    n_on = sum(1 for v in stock.values() if v["status"] == "on_order")
    print("живое наличие: в наличии %d · под заказ %d · неизвестно %d"
          % (marked, n_on, len(stock) - marked - n_on))

    res = M.screen(films, city="Москва", cats=C.load_cats())
    agg = res["agg"]
    print("\nИТОГ: одобрено %s · отбито %s · нужны данные %s | средний профит %s ₽ | у обрыва %s"
          % (agg["approved"], agg["rejected"], agg["needs_data"],
             agg["avg_profit"], agg["near_cliff"]))
    print("лимиты города:", agg["city_limits"], "\n")

    print("%-12s%-11s%9s%9s%9s%9s  %s"
          % ("SKU", "вердикт", "пол", "закуп", "сборы", "профит", "причина"))
    print("-" * 100)
    for bucket, tag in (("approved", "БЕРЁМ"), ("needs_data", "нет данных"), ("rejected", "ОТБОЙ")):
        for d in res[bucket]:
            e = d.get("economics") or {}
            why = d["reasons"][0][:44] if d.get("reasons") else "чисто"
            print("%-12s%-11s%9s%9s%9s%9s  %s"
                  % (d["sku"], tag, e.get("floor"), e.get("cost_buy"),
                     e.get("market_fees"), e.get("profit"), why))


if __name__ == "__main__":
    main()

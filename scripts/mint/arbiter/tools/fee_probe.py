#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРОВЕРКА СБОРА FEE: программа vs наш магазин (ЧТЕНИЕ, 0 ₽).

Калькулятор вернул FEE ≈ 46 % от цены — это неправдоподобно много для размещения.
Гипотеза: зов по sellingProgram даёт обобщённый максимум, а по campaignId — тарифы НАШЕГО
магазина. Документация запрещает передавать их вместе, значит сравниваем двумя зовами.
Заодно смотрим, зависит ли FEE от цены (процент) или от габаритов.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_trade_hands_v1 as trade  # noqa: E402

CATEGORY_ID = 76346336
CAMPAIGN_ID = int(os.environ.get("YANDEX_CAMPAIGN_ID") or 0)

# один товар, три цены — видно, процент это или floor
PROBES = [
    {"category_id": CATEGORY_ID, "price": 210, "length": 50, "width": 30, "height": 30, "weight": 0.5},
    {"category_id": CATEGORY_ID, "price": 1380, "length": 55, "width": 32, "height": 32, "weight": 1.4},
    {"category_id": CATEGORY_ID, "price": 9600, "length": 120, "width": 74, "height": 74, "weight": 5.4},
]


def show(title, rows, probes):
    print("\n=== %s ===" % title)
    if not rows:
        print("   (пусто)")
        return
    for o, row in zip(probes, rows):
        tar = (row or {}).get("tariffs") or []
        total = sum(float(t.get("amount") or 0) for t in tar)
        print("  цена %6.0f → сборы %7.0f (%.1f%%)" % (o["price"], total, total / o["price"] * 100))
        for t in sorted(tar, key=lambda x: -float(x.get("amount") or 0)):
            amt = float(t.get("amount") or 0)
            pct = t.get("percent")
            print("        %-22s %8.0f ₽   percent=%s" % (t.get("type"), amt, pct))


by_prog = trade.calc_tariffs(PROBES, selling_program=trade.PLACEMENT_EXPRESS)
show("по ПРОГРАММЕ (EXPRESS)", by_prog, PROBES)

if CAMPAIGN_ID:
    by_camp = trade.calc_tariffs(PROBES, campaign_id=CAMPAIGN_ID)
    show("по НАШЕМУ МАГАЗИНУ (campaignId=%d)" % CAMPAIGN_ID, by_camp, PROBES)
else:
    print("\nYANDEX_CAMPAIGN_ID не задан — второй зов пропущен")

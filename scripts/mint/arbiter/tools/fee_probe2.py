#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЧТО ТАКОЕ FEE 44.5 %: сырой ответ + зависимость от категории и программы (ЧТЕНИЕ, 0 ₽).

FEE вышел ровно 44.5 % от цены и одинаков по программе и по магазину. Проверяем три вещи:
  1) сырой JSON строки тарифа — есть ли поля, объясняющие ставку;
  2) меняется ли FEE% при СМЕНЕ КАТЕГОРИИ (если нет — это заглушка/максимум, а не наш тариф);
  3) меняется ли FEE% при СМЕНЕ ПРОГРАММЫ (FBS/DBS против EXPRESS).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_trade_hands_v1 as trade  # noqa: E402

FILM = 76346336        # наша категория (подтверждена боем)
BOX = {"length": 55, "width": 32, "height": 32, "weight": 1.4}
PRICE = 1380


def fee_pct(rows, i=0):
    tar = ((rows or [{}])[i] or {}).get("tariffs") or []
    out = {}
    for t in tar:
        out[t.get("type")] = float(t.get("amount") or 0)
    return out


print("=== 1. СЫРОЙ JSON строки тарифа (наша категория, EXPRESS) ===")
raw = trade.calc_tariffs([dict(category_id=FILM, price=PRICE, **BOX)],
                         selling_program=trade.PLACEMENT_EXPRESS)
print(json.dumps(raw[0] if raw else {}, ensure_ascii=False, indent=2)[:2200])

print("\n=== 2. FEE ПРИ СМЕНЕ КАТЕГОРИИ (цена/габариты одни и те же) ===")
CATS = [
    (FILM, "наша: упаковочные плёнки"),
    (90764, "бытовая техника (верхний узел)"),
    (91491, "одежда/обувь (верхний узел)"),
    (16440530, "продукты питания (верхний узел)"),
]
for cid, name in CATS:
    try:
        r = trade.calc_tariffs([dict(category_id=cid, price=PRICE, **BOX)],
                               selling_program=trade.PLACEMENT_EXPRESS)
        f = fee_pct(r)
        tot = sum(f.values())
        print("  %-34s FEE=%7.0f (%.1f%%)  всего=%7.0f (%.1f%%)"
              % (name, f.get("FEE", 0), f.get("FEE", 0) / PRICE * 100, tot, tot / PRICE * 100))
    except Exception as e:
        print("  %-34s ошибка: %s" % (name, str(e)[:90]))

print("\n=== 3. FEE ПРИ СМЕНЕ ПРОГРАММЫ (наша категория) ===")
for prog in (trade.PLACEMENT_EXPRESS, trade.PLACEMENT_FBS, trade.PLACEMENT_DBS):
    try:
        r = trade.calc_tariffs([dict(category_id=FILM, price=PRICE, **BOX)], selling_program=prog)
        f = fee_pct(r)
        tot = sum(f.values())
        parts = " · ".join("%s=%.0f" % (k, v) for k, v in sorted(f.items(), key=lambda x: -x[1]))
        print("  %-9s всего=%7.0f (%.1f%%)   %s" % (prog, tot, tot / PRICE * 100, parts))
    except Exception as e:
        print("  %-9s ошибка: %s" % (prog, str(e)[:90]))

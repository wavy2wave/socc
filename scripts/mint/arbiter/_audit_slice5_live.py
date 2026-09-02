#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СРЕЗ-5 LIVE READ probe. ТОЛЬКО чтение: калькулятор тарифов + GET-зонды доставки.
Ни одного write. Ни одного commit."""
import json
from ymarket_hands_v1 import _request, resolve_ids, YMarketHTTPError, creds_present
import ymarket_trade_hands_v1 as trade

bid, cid, _ = resolve_ids()
print("creds:", creds_present(), "| bid:", bid, "| cid:", cid)

# --- 1. Калькулятор тарифов (READ) на двух рулонах: крупный vs средний ---
# categoryId — плёнка стрейч; берём id из прежних экспериментов органа.
CAT = 76346336
offers = [
    {"category_id": CAT, "price": 1000, "length": 120, "width": 68, "height": 68,
     "weight": 4.15, "quantity": 1},   # 1.2x100 (сумма 256) — за обрывом
    {"category_id": CAT, "price": 1000, "length": 50, "width": 68, "height": 68,
     "weight": 2.0, "quantity": 1},    # 0.5x100 (сумма 186) — до обрыва
    {"category_id": CAT, "price": 1000, "length": 30, "width": 26, "height": 26,
     "weight": 0.5, "quantity": 1},    # мелкий
]
print("\n### 1) /v2/tariffs/calculate sellingProgram=EXPRESS (READ) ###")
try:
    rows = trade.calc_tariffs(offers, selling_program="EXPRESS")
    for o, r in zip(offers, rows):
        tar = r.get("tariffs") or []
        brief = [(t.get("type"), t.get("amount"), t.get("percent")) for t in tar]
        print(f"  L{o['length']} sum={o['length']+o['width']+o['height']} w={o['weight']}: {brief}")
except Exception as e:
    print("  EXPRESS calc error:", str(e)[:300])

print("\n### 1b) sellingProgram=FBS (READ) ###")
try:
    rows = trade.calc_tariffs(offers, selling_program="FBS")
    for o, r in zip(offers, rows):
        tar = r.get("tariffs") or []
        brief = [(t.get("type"), t.get("amount")) for t in tar]
        print(f"  L{o['length']} sum={o['length']+o['width']+o['height']}: {brief}")
except Exception as e:
    print("  FBS calc error:", str(e)[:300])

# --- 2. Зонд GET-эндпоинтов доставки/условий (READ only) ---
print("\n### 2) GET-зонды доставки/условий продаж (READ only) ###")
probes = [
    ("GET", f"/businesses/{bid}/settings"),
    ("GET", f"/campaigns/{cid}/settings"),
    ("GET", f"/campaigns/{cid}/delivery/services"),
    ("GET", f"/campaigns/{cid}/settings/delivery"),
    ("GET", f"/businesses/{bid}/delivery/conditions"),
    ("GET", f"/campaigns/{cid}"),
]
for method, path in probes:
    try:
        data = _request(method, path, timeout=15)
        s = json.dumps(data, ensure_ascii=False)
        print(f"  {method} {path:<42} 200 :: {s[:220]}")
    except YMarketHTTPError as e:
        codes = [x.get("code") for x in (e.body or {}).get("errors", [])] if isinstance(e.body, dict) else []
        print(f"  {method} {path:<42} {e.status} {codes}")
    except Exception as e:
        print(f"  {method} {path:<42} ERR {str(e)[:90]}")

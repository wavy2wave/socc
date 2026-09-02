#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""READ-ONLY audit probe. Loads donor xlsx, filters bubble-wrap, inspects dialect gaps.
Does NOT touch Market. No commit, no dry=False."""
import sys, json, re
sys.path.insert(0, ".")

import ymarket_from_xlsx_v1 as bridge
import ymarket_role_merchandiser_v1 as merch
import ymarket_role_pricer_v1 as pricer
import ymarket_card_v1 as card

XLSX = "/Users/wavysexy/parsers/parsed_data/cargo-avto_MASTER_2026-08-03_03-06-11.xlsx"
SLUG = "puzyrkovaya-plenka"

loaded = bridge.load_category(XLSX, slug=SLUG, vendor=None)
prods = loaded["products"]
print(f"LOADED products: {len(prods)}  skipped: {loaded.get('skipped')}")
print(f"colmap: {json.dumps(loaded.get('colmap'), ensure_ascii=False)}")

def is_bubble(name):
    n = (name or "").lower()
    return ("пузырьк" in n or "пузырк" in n) and ("клещ" not in n)

bubble = [p for p in prods if is_bubble(p.get("name"))]
print(f"\nBUBBLE-WRAP matches (пузырьк/пузырк, no клещ): {len(bubble)}")

cats = card.load_cats()

# Probe first N in detail
FLAT_KEYS = ("length", "width", "height", "weight")
print("\n=== PER-PRODUCT DIALECT PROBE (first 18) ===")
for i, p in enumerate(bubble[:18], 1):
    sku = p.get("sku")
    name = (p.get("name") or "")[:55]
    has_wd = isinstance(p.get("weightDimensions"), dict)
    wd = p.get("weightDimensions") if has_wd else None
    flat_present = {k: p.get(k) for k in FLAT_KEYS}
    # merch view
    dims = merch._dims(p)
    weight_flat = p.get("weight")
    cost = p.get("cost")
    cat_id = p.get("category_id") or p.get("marketCategoryId")
    stock_ok = bool(p.get("stock_source") or p.get("in_stock") is True or isinstance(p.get("count"), (int, float)))
    print(f"\n[{i}] sku={sku}  {name}")
    print(f"    price={p.get('price')}  cost={cost}")
    print(f"    weightDimensions(nested)={wd}")
    print(f"    flat length/width/height/weight = {flat_present}")
    print(f"    MERCH._dims()={dims}  MERCH weight={weight_flat}  -> fits_city.ok={merch.fits_city(p).get('ok')}")
    print(f"    MERCH cat_id={cat_id}  stock_ok={stock_ok}")

print("\n=== MERCHANDISER SCREEN (all 18) ===")
scr = merch.screen(bubble[:18], cats=cats)
print(json.dumps(scr["agg"], ensure_ascii=False, indent=2))
# reasons histogram
from collections import Counter
reason_hist = Counter()
for bucket in ("approved","rejected","needs_data"):
    for r in scr[bucket]:
        for rs in r.get("reasons", []):
            reason_hist[rs.split(" —")[0][:60]] += 1
print("REASONS:")
for k,v in reason_hist.most_common():
    print(f"   {v}x  {k}")

print("\n=== CARD.to_offer + parameter_values (first 5) ===")
for p in bubble[:5]:
    try:
        res = card.to_offer(p, slug=SLUG, cats=cats)
        offer = res["offer"]; meta = res["meta"]
        has_wd = "weightDimensions" in offer
        pv = card.parameter_values(p, category_params=None, profile=(cats.get('categories',{}).get(SLUG)))
        print(f"sku={offer.get('offerId')} price_ok={offer['basicPrice']['value']} cat_id={meta.get('category_id')} "
              f"wd_in_offer={has_wd} pics={len(offer.get('pictures',[]))} "
              f"param_missing_required={pv.get('missing_required')} n_params={len(pv.get('parameterValues',[]))}")
    except Exception as e:
        print(f"sku={p.get('sku')} CARD ERROR: {type(e).__name__}: {e}")

# Dump one full prod keys to see what dialect the loader actually emits
print("\n=== FULL KEY DUMP of bubble[0] ===")
if bubble:
    p0 = bubble[0]
    for k in sorted(p0.keys()):
        v = p0[k]
        vs = json.dumps(v, ensure_ascii=False) if not isinstance(v,str) else v
        print(f"   {k} = {vs[:120]}")

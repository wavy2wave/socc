#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Живой READ-срез витрины (0₽): оффер → имя/цена/остаток. Вывод в файл (не в tty),
чтобы не терять при долгих паузах API. Скотч vs плёнка vs наборы — по имени.
"""
import json
import sys

sys.path.insert(0, "/Users/wavysexy/SOCC/scripts/mint/arbiter")
import ymarket_hands_v1 as h
import ymarket_trade_hands_v1 as T
import ymarket_library_v1 as L

BID, CID, WH = 216949599, 149215943, 2390811
OUT = "/Users/wavysexy/SOCC/scripts/mint/arbiter/_live_vitrine_now.json"

def log(*a):
    print(*a, flush=True)

offers = h.campaign_offers(CID, limit=200)
entries = (offers.get("offers") if isinstance(offers, dict) else offers) or []
log("CAMPAIGN total:", len(entries))
ids = [str(o.get("offerId")) for o in entries]

def names_for(ids):
    out = {}
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        m = h._request("POST", f"/businesses/{BID}/offer-mappings",
                       body={"offerIds": chunk}, params={"limit": 50})
        ent = m.get("result", m) if isinstance(m, dict) else m
        ent = ent.get("offerMappings") if isinstance(ent, dict) else ent
        for row in (ent or []):
            o = row.get("offer") or row or {}
            out[str(o.get("offerId"))] = o.get("name")
    log("  mapped", len(out))
    return out

nm = names_for(ids)
log("reading stocks...")
stocks = {r["sku"]: r["count"] for r in T.read_stocks(BID, WH, offer_ids=ids)
          if r.get("type") == "FIT"}
log("  stocks", len(stocks))

rows = []
for o in entries:
    oid = str(o.get("offerId"))
    bp = o.get("basicPrice")
    price = (bp.get("value") if isinstance(bp, dict) else bp) or None
    rows.append({"sku": oid, "status": o.get("status"), "available": o.get("available"),
                 "price": price, "name": nm.get(oid), "stock": stocks.get(oid)})

lib = L.load().get("goods") or {}
for k in rows:
    k["in_lib"] = k["sku"] in lib
    if k["in_lib"]:
        k["lib_verdict"] = (lib[k["sku"]].get("last_verified") or {}).get("verdict")

def is_set(r):
    return r["name"] and "—" in r["name"] and "шт" in r["name"]

def is_tape_single(r):
    n = (r["name"] or "").lower()
    return n.startswith(("скотч", "лента клейкая", "klejkaya")) and not is_set(r)

def tag(r):
    if is_set(r):
        return "набор"
    if is_tape_single(r):
        return "одиночка"
    if "плёнка" in (r["name"] or "").lower() or "пленка" in (r["name"] or "").lower() \
            or "пузырч" in (r["name"] or "").lower():
        return "плёнка"
    return "прочее"

for r in rows:
    r["tag"] = tag(r)

with open(OUT, "w") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)
log("saved", OUT)

from collections import Counter
log("by tag:", dict(Counter(r["tag"] for r in rows)))

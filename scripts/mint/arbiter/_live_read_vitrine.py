#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Живой READ-срез витрины кабинета (0₽, наружу ничего не шлёт).

Перед живым write-актом (репрайс комплектов +800, остатки) — точный ground truth:
  какие SKU НА витрине, их status/available, имя и текущая цена (basicPrice).
Зеркалит поля движка ЦИКЛ-1 (node_verify): placement = campaign_offers,
content = offer-mappings. Скотч и плёнка живут в ОДНОМ кабинете (мать-наследование).
"""
import json
import re
import sys

sys.path.insert(0, "/Users/wavysexy/SOCC/scripts/mint/arbiter")
import ymarket_hands_v1 as h

BID, CID, WH = 216949599, 149215943, 2390811


def offer_name(oid):
    """Имя товара из offer-mappings (там живёт name; campaign/offers его не эхо)."""
    try:
        m = h._request("POST", f"/businesses/{BID}/offer-mappings",
                       body={"offerIds": [str(oid)]}, params={"limit": 50})
        ent = m.get("result", m) if isinstance(m, dict) else m
        ent = ent.get("offerMappings") if isinstance(ent, dict) else ent
        row = (ent or [{}])[0]
        o = row.get("offer") or row or {}
        bp = o.get("basicPrice")
        price = (bp.get("value") if isinstance(bp, dict) else bp) or None
        return (o.get("name"), price)
    except Exception as e:
        return (f"<ERR {e}>", None)


def main():
    offers = h.campaign_offers(CID, limit=200)
    entries = (offers.get("offers") if isinstance(offers, dict) else offers) or []
    print(f"Всего офферов в кампании {CID}: {len(entries)}\n")
    sets, singles, film, other = [], [], [], []
    for o in sorted(entries, key=lambda x: str(x.get("offerId"))):
        oid = str(o.get("offerId"))
        bp = o.get("basicPrice")
        price = (bp.get("value") if isinstance(bp, dict) else bp) or None
        st = (o.get("status"), o.get("available"))
        row = {"sku": oid, "place_status": o.get("status"),
               "available": o.get("available"), "place_price": price}
        name, mprice = offer_name(oid)
        row["name"] = name
        row["price"] = mprice
        nm = (name or "").lower()
        # Классификация: скотч ARB2/ARB, плёнка ARB-*, легаси
        if re.search(r"—\s*(\d+)\s*шт", name or ""):
            sets.append(row)
        elif nm.startswith("скотч") or "klejkaya" in nm or "лента клейкая" in nm:
            singles.append(row)
        elif "плёнка" in nm or "пленка" in nm or "пузырч" in nm:
            film.append(row)
        else:
            other.append(row)
    print("=" * 100)
    print(f"КОМПЛЕКТЫ (— N шт): {len(sets)}")
    for r in sorted(sets, key=lambda x: x["price"] or 0):
        print(f"  {r['sku']:<16} st={r['place_status']:<14} av={r['available']!s:<5} "
              f"{r['price']!s:>7}₽  {r['name']}")
    print("=" * 100)
    print(f"ОДИНОЧКИ СКОТЧА (скотч, без '— N шт'): {len(singles)}")
    for r in sorted(singles, key=lambda x: x["price"] or 0):
        print(f"  {r['sku']:<16} st={r['place_status']:<14} av={r['available']!s:<5} "
              f"{r['price']!s:>7}₽  {(r['name'] or '')[:70]}")
    print("=" * 100)
    print(f"ПЛЁНКА (пузырч/плёнка): {len(film)}")
    for r in sorted(film, key=lambda x: x["price"] or 0):
        print(f"  {r['sku']:<16} st={r['place_status']:<14} av={r['available']!s:<5} "
              f"{r['price']!s:>7}₽  {(r['name'] or '')[:70]}")
    print("=" * 100)
    print(f"ПРОЧЕЕ: {len(other)}")
    for r in sorted(other, key=lambda x: x["sku"]):
        print(f"  {r['sku']:<16} st={r['place_status']:<14} av={r['available']!s:<5} "
              f"{r['price']!s:>7}₽  {(r['name'] or '')[:70]}")


if __name__ == "__main__":
    main()

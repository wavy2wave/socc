#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Эксперимент 9: устойчивость листингов + существуют ли «пропавшие» карточки (явный offerIds)."""
import json
from ymarket_hands_v1 import _request, resolve_ids

bid, cid, _ = resolve_ids()

KNOWN = ["7627283ввв", "9600068-1", "9600130-1", "9600154-1", "9600155-1",
         "9601515-1", "9602037-1", "9603273-1", "9604816-1"]


def ids_of_cards(res):
    return [c.get("offerId") for c in res.get("offerCards", [])]


def ids_of_maps(res):
    return [m.get("offer", {}).get("offerId") for m in res.get("offerMappings", [])]


print("### A) offer-cards, body={}, разные limit ###")
for lim in (5, 10, 50, 200):
    data = _request("POST", f"/businesses/{bid}/offer-cards", body={}, params={"limit": lim})
    res = data.get("result", {})
    got = ids_of_cards(res)
    tok = (res.get("paging") or {}).get("nextPageToken")
    print(f"  limit={lim:<4} n={len(got):<3} token={'да' if tok else 'нет':<4} ids={got}")

print("\n### B) offer-mappings, body={}, разные limit ###")
for lim in (5, 10, 50, 200):
    data = _request("POST", f"/businesses/{bid}/offer-mappings", body={}, params={"limit": lim})
    res = data.get("result", {})
    got = ids_of_maps(res)
    tok = (res.get("paging") or {}).get("nextPageToken")
    print(f"  limit={lim:<4} n={len(got):<3} token={'да' if tok else 'нет':<4} ids={got}")

print("\n### C) offer-mappings с ЯВНЫМ offerIds (существуют ли «пропавшие»?) ###")
data = _request("POST", f"/businesses/{bid}/offer-mappings",
                body={"offerIds": KNOWN}, params={"limit": 200})
res = data.get("result", {})
found = ids_of_maps(res)
print(f"  запросил {len(KNOWN)}, вернулось {len(found)}: {found}")
print(f"  НЕ найдены: {[k for k in KNOWN if k not in found]}")

print("\n### D) offer-cards с ЯВНЫМ offerIds (рейтинг у каждого) ###")
data = _request("POST", f"/businesses/{bid}/offer-cards",
                body={"offerIds": KNOWN}, params={"limit": 200})
res = data.get("result", {})
cards = res.get("offerCards", [])
print(f"  запросил {len(KNOWN)}, вернулось {len(cards)}")
for c in cards:
    print(f"    {str(c.get('offerId')):<14} rating={str(c.get('contentRating')):<6} "
          f"status={str(c.get('contentRatingStatus')):<10} "
          f"#params={len(c.get('parameterValues') or []):<3} "
          f"#err={len(c.get('errors') or [])} "
          f"cardStatus={c.get('cardStatus')}")
print(f"  НЕ вернулись: {[k for k in KNOWN if k not in [c.get('offerId') for c in cards]]}")

print("\n### E) offer-mappings с archived=true ###")
for flag in (False, True):
    try:
        data = _request("POST", f"/businesses/{bid}/offer-mappings",
                        body={"archived": flag}, params={"limit": 200})
        res = data.get("result", {})
        got = ids_of_maps(res)
        print(f"  archived={flag}: n={len(got)} ids={got}")
    except Exception as e:
        print(f"  archived={flag}: ошибка {e}")

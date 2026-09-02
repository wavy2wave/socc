#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Эксперимент 8: истинный состав каталога через offer-mappings + повторный offer-cards без пагинации."""
import json
from collections import Counter
from ymarket_hands_v1 import _request, resolve_ids

bid, cid, _ = resolve_ids()

# 1) Полный каталог через offer-mappings (пагинация page_token)
all_maps = []
token = None
pages = 0
while True:
    params = {"limit": 200}
    if token:
        params["page_token"] = token
    data = _request("POST", f"/businesses/{bid}/offer-mappings", body={}, params=params)
    res = data.get("result", {})
    batch = res.get("offerMappings", [])
    all_maps.extend(batch)
    pages += 1
    token = (res.get("paging") or {}).get("nextPageToken")
    print(f"  offer-mappings стр.{pages}: +{len(batch)} (token={'да' if token else 'нет'})")
    if not token or pages > 20:
        break

print(f"\nВСЕГО в каталоге (offer-mappings): {len(all_maps)}")
ids = [m.get("offer", {}).get("offerId") for m in all_maps]
print("offerIds:", ids)

# 2) offer-cards ОДНИМ запросом БЕЗ пагинации, limit=200
data = _request("POST", f"/businesses/{bid}/offer-cards", body={}, params={"limit": 200})
res = data.get("result", {})
cards1 = res.get("offerCards", [])
print(f"\noffer-cards без offerIds, limit=200 → {len(cards1)} карточек")
print("paging:", res.get("paging"))
for c in cards1:
    print(f"  {c.get('offerId'):<20} rating={c.get('contentRating')} status={c.get('contentRatingStatus')}")

# 3) offer-cards С ЯВНЫМ списком ВСЕХ offerIds из каталога
print(f"\noffer-cards С явным offerIds ({len(ids)} шт):")
cards2 = []
CHUNK = 200
for i in range(0, len(ids), CHUNK):
    chunk = [x for x in ids[i:i + CHUNK] if x]
    data = _request("POST", f"/businesses/{bid}/offer-cards", body={"offerIds": chunk}, params={"limit": 200})
    cards2.extend(data.get("result", {}).get("offerCards", []))

print(f"→ {len(cards2)} карточек")
cnt = Counter(c.get("contentRatingStatus") for c in cards2)
print("contentRatingStatus:", dict(cnt))
print()
print(f"{'offerId':<20} {'rating':<8} {'ratingStatus':<14} {'#params':<9} {'#err'}")
print("-" * 70)
for c in sorted(cards2, key=lambda x: str(x.get("offerId"))):
    print(f"{str(c.get('offerId')):<20} "
          f"{str(c.get('contentRating')):<8} "
          f"{str(c.get('contentRatingStatus')):<14} "
          f"{len(c.get('parameterValues') or []):<9} "
          f"{len(c.get('errors') or [])}")

with open("/tmp/mappings_dump.json", "w") as f:
    json.dump(all_maps, f, ensure_ascii=False, indent=2)
with open("/tmp/cards_by_ids.json", "w") as f:
    json.dump(cards2, f, ensure_ascii=False, indent=2)
print("\nДампы: /tmp/mappings_dump.json /tmp/cards_by_ids.json")

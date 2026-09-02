#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Эксперимент 10: полный дамп 4 живых офферов (что реально заполнено) + карточки рядом."""
import json
from ymarket_hands_v1 import _request, resolve_ids

bid, cid, _ = resolve_ids()

data = _request("POST", f"/businesses/{bid}/offer-mappings", body={}, params={"limit": 200})
maps = data.get("result", {}).get("offerMappings", [])

data = _request("POST", f"/businesses/{bid}/offer-cards", body={}, params={"limit": 200})
cards = {c.get("offerId"): c for c in data.get("result", {}).get("offerCards", [])}

for m in maps:
    off = m.get("offer", {})
    oid = off.get("offerId")
    card = cards.get(oid, {})
    print("=" * 78)
    print(f"offerId: {oid}")
    print(f"  name:            {'ДА (' + str(len(off.get('name') or '')) + ' симв)' if off.get('name') else 'НЕТ'}")
    print(f"  description:     {'ДА (' + str(len(off.get('description') or '')) + ' симв)' if off.get('description') else 'НЕТ'}")
    print(f"  pictures:        {len(off.get('pictures') or [])}")
    print(f"  videos:          {len(off.get('videos') or [])}")
    print(f"  vendor:          {off.get('vendor')!r}")
    print(f"  barcodes:        {off.get('barcodes')}")
    print(f"  manufCountries:  {off.get('manufacturerCountries')}")
    print(f"  weightDimensions:{off.get('weightDimensions')}")
    print(f"  boxCount:        {off.get('boxCount')}")
    print(f"  type:            {off.get('type')}")
    print(f"  cardStatus:      {off.get('cardStatus')}")
    print(f"  campaigns:       {off.get('campaigns')}")
    print(f"  basicPrice:      {off.get('basicPrice')}")
    print(f"  mapping:         marketSku={m.get('mapping', {}).get('marketSku')} "
          f"cat={m.get('mapping', {}).get('marketCategoryId')} "
          f"({m.get('mapping', {}).get('marketCategoryName')})")
    print(f"  --- offer-cards ---")
    print(f"  contentRating:       {card.get('contentRating')}")
    print(f"  contentRatingStatus: {card.get('contentRatingStatus')}")
    print(f"  parameterValues:     {len(card.get('parameterValues') or [])}")
    print(f"  errors:              {card.get('errors')}")
    print(f"  recommendations:     {card.get('recommendations')}")
    # какие ключи вообще есть у оффера
    print(f"  ключи offer: {sorted(off.keys())}")

with open("/tmp/live4_maps.json", "w") as f:
    json.dump(maps, f, ensure_ascii=False, indent=2)
with open("/tmp/live4_cards.json", "w") as f:
    json.dump(list(cards.values()), f, ensure_ascii=False, indent=2)
print("\nДампы: /tmp/live4_maps.json /tmp/live4_cards.json")

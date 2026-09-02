#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Эксперимент 7: полный дамп contentRating + contentRatingStatus по ВСЕМ карточкам каталога."""
import json
from collections import Counter
from ymarket_hands_v1 import _request, resolve_ids

bid, cid, _ = resolve_ids()

# Полная пагинация offer-cards
all_cards = []
page_token = None
while True:
    params = {"limit": 200}
    if page_token:
        params["page_token"] = page_token
    data = _request("POST", f"/businesses/{bid}/offer-cards", body={}, params=params)
    res = data.get("result", {})
    cards = res.get("offerCards", [])
    all_cards.extend(cards)
    page_token = (res.get("paging") or {}).get("nextPageToken")
    if not page_token:
        break

print(f"ВСЕГО карточек в каталоге: {len(all_cards)}\n")

# Распределение по статусам
status_counter = Counter(c.get("contentRatingStatus") for c in all_cards)
card_status_counter = Counter(c.get("cardStatus") for c in all_cards)
print("contentRatingStatus:", dict(status_counter))
print("cardStatus:", dict(card_status_counter))
print()

# Таблица: offerId | contentRating | contentRatingStatus | cardStatus | есть ли errors/recommendations
print(f"{'offerId':<20} {'rating':<8} {'ratingStatus':<14} {'cardStatus':<24} {'err':<5} {'recs'}")
print("-" * 90)
for c in sorted(all_cards, key=lambda x: str(x.get("offerId"))):
    rating = c.get("contentRating")
    print(f"{str(c.get('offerId')):<20} "
          f"{str(rating):<8} "
          f"{str(c.get('contentRatingStatus')):<14} "
          f"{str(c.get('cardStatus')):<24} "
          f"{len(c.get('errors') or []):<5} "
          f"{len(c.get('recommendations') or [])}")

# Ключи, встречающиеся в ответах
all_keys = Counter()
for c in all_cards:
    for k in c.keys():
        all_keys[k] += 1
print("\nВстречаемость ключей в offerCards:", dict(all_keys))

# Сохранить сырьё для последующего сравнения
with open("/tmp/offer_cards_dump.json", "w") as f:
    json.dump(all_cards, f, ensure_ascii=False, indent=2)
print("\nСырой дамп: /tmp/offer_cards_dump.json")

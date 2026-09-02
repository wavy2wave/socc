#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Эксперимент 11: фильтры offer-cards + поиск endpoint пересчёта (POST-варианты). Только READ/зонд."""
import json
from ymarket_hands_v1 import _request, resolve_ids, YMarketHTTPError

bid, cid, _ = resolve_ids()
IDS = ["9601515-1", "9602037-1", "9603273-1", "9604816-1"]


def show(tag, body, params=None):
    try:
        data = _request("POST", f"/businesses/{bid}/offer-cards", body=body,
                        params=params or {"limit": 200})
        cards = data.get("result", {}).get("offerCards", [])
        line = ", ".join(f"{c.get('offerId')}={c.get('contentRating')}/{c.get('contentRatingStatus')}"
                         for c in cards)
        print(f"  {tag:<52} n={len(cards)} :: {line}")
    except Exception as e:
        print(f"  {tag:<52} ОШИБКА: {str(e)[:160]}")


print("### A) Варианты фильтров offer-cards ###")
show("body={}", {})
show("offerIds=все4", {"offerIds": IDS})
show("cardStatuses=[HAS_CARD_CAN_UPDATE]", {"cardStatuses": ["HAS_CARD_CAN_UPDATE"]})
show("cardStatuses=[HAS_CARD_CAN_NOT_UPDATE]", {"cardStatuses": ["HAS_CARD_CAN_NOT_UPDATE"]})
show("cardStatuses=[NO_CARD_NEED_CONTENT]", {"cardStatuses": ["NO_CARD_NEED_CONTENT"]})
show("categoryIds=[76346336]", {"categoryIds": [76346336]})
show("categoryIds=[61019139]", {"categoryIds": [61019139]})
show("archived=false", {"archived": False})
show("archived=true", {"archived": True})
show("limit=1", {}, {"limit": 1})

print("\n### B) Зонд: существует ли endpoint пересчёта рейтинга ###")
probes = [
    ("POST", f"/businesses/{bid}/offer-cards/recalculate", {}),
    ("POST", f"/businesses/{bid}/offer-cards/rating/refresh", {}),
    ("POST", f"/businesses/{bid}/offer-cards/content-rating", {}),
    ("POST", f"/businesses/{bid}/content-rating", {}),
    ("POST", f"/businesses/{bid}/offer-cards/refresh", {}),
    ("POST", f"/businesses/{bid}/offer-cards/update", None),   # существует (не зовём с телом)
    ("GET", f"/businesses/{bid}/ratings", None),
    ("GET", f"/campaigns/{cid}/ratings", None),
    ("GET", f"/businesses/{bid}/settings", None),
    ("GET", f"/campaigns/{cid}/settings", None),
]
for method, path, body in probes:
    if path.endswith("/offer-cards/update"):
        print(f"  {method} {path:<58} ПРОПУСК (запись, не зондируем)")
        continue
    try:
        data = _request(method, path, body=body, timeout=15)
        print(f"  {method} {path:<58} 200 OK -> {json.dumps(data, ensure_ascii=False)[:200]}")
    except YMarketHTTPError as e:
        codes = [x.get("code") for x in (e.body or {}).get("errors", [])] if isinstance(e.body, dict) else []
        print(f"  {method} {path:<58} {e.status} {codes}")
    except Exception as e:
        print(f"  {method} {path:<58} {str(e)[:100]}")

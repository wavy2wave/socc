#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Эксперимент 12: ПОЛЛИНГ contentRating во времени — доказать асинхронный расчёт.

Каждые 45 с снимаем rating/status/#params для 4 живых офферов. Только READ.
"""
import time
import datetime
from ymarket_hands_v1 import _request, resolve_ids

bid, cid, _ = resolve_ids()
ROUNDS = 14
SLEEP = 45

hist = {}
for i in range(ROUNDS):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    try:
        data = _request("POST", f"/businesses/{bid}/offer-cards", body={}, params={"limit": 200})
        cards = data.get("result", {}).get("offerCards", [])
    except Exception as e:
        print(f"[{ts}] ошибка: {str(e)[:120]}")
        time.sleep(SLEEP)
        continue

    parts = []
    for c in sorted(cards, key=lambda x: str(x.get("offerId"))):
        oid = c.get("offerId")
        r = c.get("contentRating")
        st = c.get("contentRatingStatus")
        np = len(c.get("parameterValues") or [])
        nrec = len(c.get("recommendations") or [])
        cur = (r, st, np, nrec)
        prev = hist.get(oid)
        mark = "" if prev == cur else "  <== ИЗМЕНИЛОСЬ"
        hist[oid] = cur
        parts.append(f"{oid}: r={str(r):<5} st={str(st):<9} p={np:<3} rec={nrec}{mark}")
    print(f"[{ts}] round {i+1}/{ROUNDS}")
    for p in parts:
        print(f"    {p}")
    if i + 1 < ROUNDS:
        time.sleep(SLEEP)

print("\n=== ИТОГОВОЕ СОСТОЯНИЕ ===")
for oid, (r, st, np, nrec) in sorted(hist.items()):
    print(f"  {oid}: contentRating={r} status={st} params={np} recommendations={nrec}")

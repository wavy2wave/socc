#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Живая СВЕРКА после write-акта (0₽): статус витрины, цена, остаток по 50 SKU.

Читает ТОЧНО как node_verify движка: campaign_offers → placement(status/available/basicPrice),
read_stocks → count/type. Скотч-комплекты должны стать PUBLISHED/FIT по новой цене (+800),
плёнка ARB-* остаться PUBLISHED с FIT=100.
"""
import sys

sys.path.insert(0, "/Users/wavysexy/SOCC/scripts/mint/arbiter")
import ymarket_hands_v1 as h
import ymarket_trade_hands_v1 as T

BID, CID, WH = 216949599, 149215943, 2390811

SET_REPRICE_NEW = {  # ожидаемые новые цены
    "ARB2-83168862": 2040, "ARB2-84993096": 2040, "ARB2-38101050": 2640,
    "ARB2-36421253": 2910, "ARB2-41601467": 3080, "ARB2-74205687": 3480,
    "ARB2-73223557": 3710, "ARB2-88513538": 3140, "ARB2-02256839": 3140,
    "ARB2-21295888": 3140, "ARB2-40634030": 3140,
}
KEEP_PRICE = {  # N=5/N=10 комплекты — НЕ трогали, должны остаться 1530
    "ARB2-12960513": 1530, "ARB2-76781511": 1530,
}

# остатки: 13 комплектов ×13 + 37 плёнки ARB-* ×100
SET_STOCK = {"ARB2-83168862", "ARB2-84993096", "ARB2-12960513", "ARB2-76781511",
             "ARB2-38101050", "ARB2-36421253", "ARB2-41601467", "ARB2-02256839",
             "ARB2-21295888", "ARB2-40634030", "ARB2-88513538", "ARB2-74205687",
             "ARB2-73223557"}
FILM = ["ARB-56925082", "ARB-87931769", "ARB-53416854", "ARB-20503734", "ARB-49285152",
        "ARB-71632066", "ARB-08729795", "ARB-07058684", "ARB-33849601", "ARB-56738137",
        "ARB-26247053", "ARB-29846713", "ARB-72549324", "ARB-73557155", "ARB-51627659",
        "ARB-87309612", "ARB-70813041", "ARB-16214506", "ARB-47555504", "ARB-04235344",
        "ARB-57807179", "ARB-94366517", "ARB-15723146", "ARB-54145852", "ARB-63513197",
        "ARB-12034838", "ARB-96812616", "ARB-17739462", "ARB-86551711", "ARB-37280156",
        "ARB-09219228", "ARB-26558215", "ARB-36274733", "ARB-47726061", "ARB-20980160",
        "ARB-63700297", "ARB-54288181"]

ids = list(SET_STOCK) + FILM
print(f"СВЕРКА {len(ids)} SKU кабинета {CID}\n")

rows = {}
offers = h.campaign_offers(CID, offer_ids=ids, limit=50)
for o in (offers.get("offers") if isinstance(offers, dict) else offers) or []:
    bp = o.get("basicPrice")
    price = (bp.get("value") if isinstance(bp, dict) else bp) or None
    rows.setdefault(o.get("offerId"), {})["pl"] = {"status": o.get("status"),
                                                    "av": o.get("available"), "price": price}
for r in T.read_stocks(BID, WH, offer_ids=ids):
    if r.get("type") == "FIT":
        rows.setdefault(r["sku"], {})["stock"] = r["count"]
    else:
        rows.setdefault(r.get("sku"), {})["stock_raw"] = r

def line(sku):
    pl = rows.get(sku, {}).get("pl") or {}
    st = rows.get(sku, {}).get("stock")
    return f"{sku:<16} st={str(pl.get('status')):<13} av={str(pl.get('av'))!s:<5} " \
           f"price={str(pl.get('price')):>8}  stock={st}"

print("── КОМПЛЕКТЫ 2/3шт (ждали +800 к старой) ──")
bad = 0
for sku, want in sorted(SET_REPRICE_NEW.items()):
    pl = rows.get(sku, {}).get("pl") or {}
    got = pl.get("price")
    ok = got == want
    bad += 0 if ok else 1
    print(f"  {'✓' if ok else '✗ ' + str(got) + '≠' + str(want):<4} {line(sku)}")
print("\n── N=5/N=10 (НЕ трогали: цена 1530, остаток 13) ──")
for sku, want in KEEP_PRICE.items():
    pl = rows.get(sku, {}).get("pl") or {}
    ok = pl.get("price") == want
    bad += 0 if ok else 1
    print(f"  {'✓' if ok else '✗':<4} {line(sku)}")
print("\n── ПЛЁНКА ARB-* ×100 (37) ──")
n_ok = 0
for sku in FILM:
    st = rows.get(sku, {}).get("stock")
    pl = rows.get(sku, {}).get("pl") or {}
    ok = st == 100 and pl.get("status") == "PUBLISHED"
    n_ok += 1 if ok else 0
    if not ok:
        bad += 1
        print(f"  ✗  {line(sku)}")
print(f"  ✓ {n_ok}/37 плёнки PUBLISHED с FIT=100")
print(f"\nИТОГ: {'ВСЁ ЧИСТО' if bad == 0 else f'{bad} НЕСОВПАДЕНИЙ'}")

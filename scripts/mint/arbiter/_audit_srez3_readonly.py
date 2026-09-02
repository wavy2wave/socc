#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СРЕЗ 3 — read-only снимок живого кабинета. Ни одного вызова с /update. Только чтение."""
import json
import os
import sys

# грузим .env явно из этой папки (source .env в шелле тоже сделает, но подстрахуемся)
HERE = os.path.dirname(os.path.abspath(__file__))
envf = os.path.join(HERE, ".env")
if os.path.exists(envf):
    for line in open(envf, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import ymarket_hands_v1 as h
import ymarket_trade_hands_v1 as th

BID = os.getenv("YANDEX_BUSINESS_ID")
CID = os.getenv("YANDEX_CAMPAIGN_ID")
OFFERS = ["9601515-1", "9602037-1", "9603273-1", "9604816-1"]

def dump(title, obj):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)
    print(json.dumps(obj, ensure_ascii=False, indent=2))

def safe(label, fn):
    try:
        return fn()
    except Exception as e:
        import traceback
        print(f"\n!!! ОШИБКА в [{label}]: {e}")
        traceback.print_exc()
        return {"__error__": str(e)}

def main():
    print(f"creds_present={h.creds_present()} business_id={BID} campaign_id={CID}")

    # 1) offer-cards (POST-фильтр = чтение): contentRating + parameterValues + recommendations
    cards = safe("offer-cards", lambda: h.offer_cards_status(BID, offer_ids=OFFERS, limit=50))
    dump("1) offer-cards (RAW, всё что отдаёт API)", cards)

    # 1b) offer-mappings (POST без /update = чтение): описание, картинки, штрихкоды, vendor, габариты
    def read_mappings():
        return h._request("POST", f"/businesses/{BID}/offer-mappings",
                          body={"offerIds": OFFERS}, params={"limit": 50})
    mappings = safe("offer-mappings", read_mappings)
    dump("1b) offer-mappings (RAW: offer object — описание/картинки/штрихкоды/vendor/габариты)", mappings)

    # 3) размещение в магазине: PUBLISHED? + цены в offers
    camp = safe("campaign_offers", lambda: h.campaign_offers(CID, offer_ids=OFFERS, limit=50))
    dump("3a) campaigns/{cid}/offers (RAW: статус размещения)", camp)

    # 3b) остатки — попробуем несколько складов; сначала узнаем склады
    whs = safe("warehouses", lambda: th.warehouses(BID))
    dump("4a) warehouses (нормализованный)", whs)

    # 4a-raw: сырой ответ warehouses чтобы увидеть ВСЕ поля (адрес/расписание/id/комментарий)
    def raw_warehouses():
        return h._request("POST", f"/v3/businesses/{BID}/warehouses",
                          body={"components": ["ADDRESS", "SCHEDULE", "GROUP"]})
    whs_raw = safe("warehouses_raw", raw_warehouses)
    dump("4b) warehouses RAW (все поля: адрес/расписание/комментарий/id)", whs_raw)

    exp = safe("express_warehouses", lambda: th.express_warehouses(BID))
    dump("4c) express_warehouses (только EXPRESS)", exp)

    # 3b) остатки по каждому express-складу
    wh_ids = []
    if isinstance(whs, list):
        wh_ids = [w.get("id") for w in whs if w.get("id") is not None]
    for wid in wh_ids:
        st = safe(f"read_stocks[{wid}]", lambda wid=wid: th.read_stocks(BID, wid, offer_ids=OFFERS))
        dump(f"3b) остатки на складе {wid}", st)

    # 3c) рекомендации по ценам
    pr = safe("price_recommendations", lambda: th.price_recommendations(BID, offer_ids=OFFERS))
    dump("3c) price_recommendations", pr)

    # 5) качество магазина
    q = safe("quality_rating", lambda: th.quality_rating(BID, [CID]))
    dump("5a) quality_rating", q)

    # 5b) регион Санкт-Петербург
    spb = safe("find_region", lambda: th.find_region("Санкт-Петербург"))
    dump("5b) find_region('Санкт-Петербург')", spb)

    print("\n\nГОТОВО. Всё выше — только чтение (0 вызовов с /update).")

if __name__ == "__main__":
    sys.exit(main() or 0)

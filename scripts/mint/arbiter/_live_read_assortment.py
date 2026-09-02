"""LIVE READ-ONLY — what's actually in the cabinet right now (assortment + stock).
RUBICON: GET/list only. No writes. Key never printed."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ymarket_hands_v1 as H
import ymarket_trade_hands_v1 as T

def show(title, obj, n=1200):
    print(f"\n== {title} ==", flush=True)
    try:
        s = json.dumps(obj, ensure_ascii=False)
        print("  " + (s if len(s) <= n else s[:n] + f" …(+{len(s)-n} chars)"))
    except Exception:
        print("  " + repr(obj)[:n])

H._ensure_env()
bid = H.business_id_env()
cid = H.campaign_id_env()
WH = 2390811  # Atlas (Москва)

# how many SKUs live in the shop
try:
    co = H.campaign_offers(int(cid), limit=50)
    offers = (co.get("offers") if isinstance(co, dict) else None) or (co if isinstance(co, list) else [])
    ids = []
    for o in offers:
        ids.append(o.get("offerId") or o.get("offer_id") or o.get("id"))
    print(f"\n== campaign_offers: {len(offers)} offer(s) in shop {cid} ==")
    for o in offers[:30]:
        print(f"   • offerId={o.get('offerId')}  "
              f"avail={o.get('available')}  "
              f"quantum={o.get('quantum')}  "
              f"status={o.get('campaignStatus') or o.get('status')}")
    if not offers:
        show("campaign_offers raw", co)
except Exception as e:
    print(f"\n== campaign_offers ==\n  ERR {type(e).__name__}: {e}")
    ids = []

# card fill / moderation status (business catalog)
try:
    cs = H.offer_cards_status(bid, limit=50)
    show("offer_cards_status (catalog fill/moderation)", cs)
except Exception as e:
    print(f"\n== offer_cards_status ==\n  ERR {type(e).__name__}: {e}")

# stock on the Moscow warehouse
try:
    st = T.read_stocks(bid, WH)
    show(f"read_stocks @ warehouse {WH} (Москва)", st)
except Exception as e:
    print(f"\n== read_stocks ==\n  ERR {type(e).__name__}: {e}")

print("\n== done (read-only; nothing written) ==")

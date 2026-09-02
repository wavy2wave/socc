"""LIVE READ-ONLY — assortment of ALL shops + DBS shop settings (fulfillment model).
RUBICON: GET/list only. No writes, no prices, no publish. Key never printed.
Purpose: before any боевой write, prove which shop is a HONEST DBS (no Express 60-min
timer) and whether any shop already has покупаемые offers hanging (a passive risk).
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ymarket_hands_v1 as H

H._ensure_env()
bid = H.business_id_env()

SHOPS = [
    (135962876, "express go",           "FBS"),
    (148611270, "express go 2",         "DBS"),   # doctrine target
    (148619267, "Express Molodezhnaya", "FBS"),   # current env
]

def offers_of(cid):
    try:
        offers = H.campaign_offers(int(cid), limit=50)
        return offers if isinstance(offers, list) else []
    except Exception as e:
        return f"ERR {type(e).__name__}: {e}"

print(f"business_id = {bid}\n")
for cid, name, kind in SHOPS:
    print(f"== shop {cid}  «{name}»  [{kind}] ==")
    offers = offers_of(cid)
    if isinstance(offers, str):
        print(f"   {offers}")
    else:
        print(f"   offers in shop: {len(offers)}")
        for o in offers[:40]:
            oid = o.get("offerId") or o.get("offer_id") or o.get("id")
            # campaignStatus / status tells us if it is PUBLISHED / buyable
            st = o.get("campaignStatus") or o.get("status") or (o.get("statusInfo") or {})
            avail = o.get("available")
            print(f"     • {oid!r}  available={avail}  status={st}")
    print()

# DBS shop settings — confirm honest DBS vs Express-mode
print("== settings of DBS shop 148611270 (fulfillment model truth) ==")
try:
    s = H._request("GET", "/campaigns/148611270/settings")
    res = s.get("result", s) if isinstance(s, dict) else s
    settings = res.get("settings", res) if isinstance(res, dict) else res
    # print only model-relevant fields, not the whole blob
    if isinstance(settings, dict):
        keys = ("countryRegion", "shopName", "showInContext", "showInPremium",
                "localRegion", "isOnline", "showInSnippets")
        slim = {k: settings.get(k) for k in keys if k in settings}
        # localRegion carries delivery type (express flags live here)
        print("  " + json.dumps(slim, ensure_ascii=False))
        lr = settings.get("localRegion") or {}
        if lr:
            print("  localRegion.delivery = " + json.dumps(lr.get("delivery"), ensure_ascii=False))
    else:
        print("  " + json.dumps(settings, ensure_ascii=False)[:800])
except Exception as e:
    print(f"  ERR {type(e).__name__}: {e}")

print("\n== done (read-only; nothing written) ==")

"""LIVE READ-ONLY probe — proves the test token can SEE the cabinet.

RUBICON: only GET calls (campaigns / warehouses / ratings / price-recs). No writes,
no prices, no publish, no orders. Values of the key are never printed.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ymarket_hands_v1 as H
import ymarket_trade_hands_v1 as T

def line(t): print(t, flush=True)

# 1. creds visible to the organ (via its own gitignored .env loader)
H._ensure_env()
line("== creds ==")
line(f"  api-key present : {H.creds_present()}")
line(f"  business_id env : {H.business_id_env()}")
line(f"  campaign_id env : {H.campaign_id_env()}")

# 2. LIVE GET /campaigns — the real auth handshake
line("\n== GET /campaigns (live auth) ==")
try:
    r = H.campaigns()
    camps = r.get("campaigns") if isinstance(r, dict) else None
    if camps is not None:
        line(f"  ✅ authenticated — {len(camps)} campaign(s) visible:")
        for c in camps:
            line(f"     • campaignId={c.get('id')}  domain={c.get('domain')}  "
                 f"clientId={c.get('clientId')}  placement={c.get('placementType')}")
    else:
        line(f"  raw: {json.dumps(r, ensure_ascii=False)[:600]}")
except Exception as e:
    line(f"  ❌ {type(e).__name__}: {e}")

# 3. resolve business<->campaign the way the organ does
line("\n== resolve_ids ==")
try:
    line(f"  {H.resolve_ids()}")
except Exception as e:
    line(f"  ❌ {type(e).__name__}: {e}")

# 4. express warehouses (the cities: MSK/SPB/Krd/Rostov) — READ ONLY
line("\n== express warehouses (cities) ==")
try:
    bid = H.business_id_env()
    w = T.express_warehouses(bid) if bid else {"_": "no business id"}
    line(f"  {json.dumps(w, ensure_ascii=False)[:900]}")
except Exception as e:
    line(f"  ❌ {type(e).__name__}: {e}")

# 5. quality / index rating — READ ONLY ("200≠success" law lives here)
line("\n== quality rating ==")
try:
    bid = H.business_id_env(); cid = H.campaign_id_env()
    if bid and cid:
        q = T.quality_rating(bid, [int(cid)])
        line(f"  {json.dumps(q, ensure_ascii=False)[:700]}")
    else:
        line("  skipped (need business+campaign id)")
except Exception as e:
    line(f"  ❌ {type(e).__name__}: {e}")

line("\n== done (read-only; nothing written) ==")

#!/usr/bin/env python3
"""
SCOUT Live Source V1 — the hunter sources REAL clinics by itself, any district, automatically.

This is the live source adapter SCOUT-SPEC-1 left gated. It uses OpenStreetMap Overpass — OPEN data
(ODbL), free, no key, worldwide — so the команда finds real clinics in ANY район without the operator
lifting a finger. It returns ONLY objective public facts; it invents no pain.

HONEST PAIN MAPPING (no fabrication — Φ(h1) downstream depends on it):
  - no_online_booking: TRUE pain only when the OSM listing genuinely has NO website/booking link.
    This is a real, checkable structural gap (a patient can't self-book → writes/calls → waits).
  - slow_dm_reply / reviews: OSM cannot measure these, so this source NEVER asserts them. The live
    domain's icp_signals are restricted to what OSM can evidence. Unknown is never claimed as pain.

LAWFUL: read-only query of an open public dataset (business listings, not personal data). No contact,
nothing sent. Attribution: data © OpenStreetMap contributors (ODbL).

Usage:
  python3 scout_live_osm_v1.py "Казань" 30
  (importable: find_clinics(place, limit) -> SCOUT feed dict)
"""
import json, sys, time, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
UA = "SOCC-ANNA-komanda/1.0 (lawful B2B prospecting; OSM ODbL)"
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
NOMINATIM = "https://nominatim.openstreetmap.org/search"


def _http(url, data=None, timeout=40):
    req = urllib.request.Request(url, data=data, method=("POST" if data else "GET"))
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _overpass(query, tries_per_host=2):
    """Resilient Overpass call: rotate mirrors, retry with backoff. Returns elements or raises."""
    last = None
    data = urllib.parse.urlencode({"data": query}).encode()
    for host in OVERPASS:
        for attempt in range(tries_per_host):
            try:
                raw = _http(host, data=data, timeout=50)
                return json.loads(raw).get("elements", [])
            except Exception as e:
                last = f"{host}: {e}"
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"all overpass mirrors failed: {last}")


def _bbox(place):
    """Fallback geocode via Nominatim → (south,west,north,east) bbox string for Overpass."""
    q = urllib.parse.urlencode({"q": place, "format": "json", "limit": 1})
    arr = json.loads(_http(f"{NOMINATIM}?{q}", timeout=30))
    if not arr:
        return None
    bb = arr[0]["boundingbox"]  # [south, north, west, east]
    return f'{bb[0]},{bb[2]},{bb[1]},{bb[3]}'


def _query_area(place):
    return (f'[out:json][timeout:40];area["name"="{place}"]->.a;'
            '(node["amenity"="dentist"](area.a);way["amenity"="dentist"](area.a);'
            'node["healthcare"="dentist"](area.a);way["healthcare"="dentist"](area.a););'
            'out center tags 200;')


def _query_bbox(bbox):
    return (f'[out:json][timeout:40];'
            f'(node["amenity"="dentist"]({bbox});way["amenity"="dentist"]({bbox});'
            f'node["healthcare"="dentist"]({bbox});way["healthcare"="dentist"]({bbox}););'
            'out center tags 200;')


# contact extraction: canonical channel → OSM tag candidates
_CONTACT_TAGS = [
    ("instagram", ["contact:instagram", "instagram"]),
    ("telegram",  ["contact:telegram", "telegram"]),
    ("vk",        ["contact:vk", "vk"]),
    ("whatsapp",  ["contact:whatsapp", "whatsapp"]),
    ("email",     ["email", "contact:email"]),
    ("phone",     ["phone", "contact:phone", "contact:mobile"]),
    ("website",   ["website", "contact:website", "url"]),
]
# outreach preference for cold B2B to a clinic owner: DM-able first, then email, then phone/site
_REACH_PRIORITY = ["instagram", "telegram", "vk", "whatsapp", "email", "phone", "website"]


def _to_clinic(el):
    t = el.get("tags", {})
    name = (t.get("name") or "").strip()
    if not name:
        return None
    contacts = {}
    for canon, keys in _CONTACT_TAGS:
        for k in keys:
            if t.get(k):
                contacts[canon] = t[k]; break
    website = contacts.get("website")
    booking = bool(website) or bool(t.get("contact:booking") or t.get("booking"))
    best = next((c for c in _REACH_PRIORITY if c in contacts), None)   # how the команда would reach them
    osm_url = f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}"
    return {
        "name": name,
        "channel": best or "unknown",
        "channels": list(contacts.keys()) or ["unknown"],
        "contact_value": contacts.get(best, "") if best else "",
        "contacts": contacts,
        "reachable": best is not None,             # can the команда actually deliver to them?
        "has_online_booking": booking,
        "reviews": [],                             # OSM cannot evidence reviews → never asserted as pain
        "source_url": website or osm_url, "osm": osm_url,
        "lat": el.get("lat") or (el.get("center") or {}).get("lat"),
        "lon": el.get("lon") or (el.get("center") or {}).get("lon"),
    }


def find_clinics(place, limit=40):
    """Return a SCOUT feed of REAL clinics in `place` (any district), from OSM open data."""
    try:
        els = _overpass(_query_area(place))
    except Exception:
        els = []
    if not els:                                  # area name miss → geocode → bbox
        bb = _bbox(place)
        if bb:
            els = _overpass(_query_bbox(bb))
    clinics = [c for c in (_to_clinic(e) for e in els) if c][:limit]
    ts = datetime.now(timezone.utc)
    return {
        "source": f"OSM Overpass LIVE · {place} · © OpenStreetMap contributors (ODbL)",
        "place": place, "fetched_at_utc": ts.isoformat(),
        "raw_count": len(els), "clinics": clinics,
    }


def main():
    if len(sys.argv) < 2:
        print('usage: scout_live_osm_v1.py "<район/город>" [limit]'); raise SystemExit(2)
    place = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 40
    feed = find_clinics(place, limit)
    no_book = sum(1 for c in feed["clinics"] if not c["has_online_booking"])
    print(f"OSM LIVE · {place}: нашёл {len(feed['clinics'])} реальных клиник "
          f"(из {feed['raw_count']} в OSM) · без онлайн-записи: {no_book}")
    for c in feed["clinics"][:15]:
        gap = "НЕТ онлайн-записи" if not c["has_online_booking"] else "запись есть"
        print(f"  - {c['name'][:38]:<38} [{c['channel']:<9}] {gap}")
    out = ROOT / "entity_substrate/domains/_komanda_live_feed.json"
    out.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"feed → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

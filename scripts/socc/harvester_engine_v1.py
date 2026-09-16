#!/usr/bin/env python3
"""
HARVESTER Engine V1 — the команда's data-acquisition agent (the role that gets the BASE).

Born on the SOCC base as the UPSTREAM role before SCOUT. The pain it closes: a район has ~100 real
clinics with TG/MAX/WhatsApp/phone, but no single free source has all of it. HARVESTER is the agent
that acquires it — multi-source, source-pluggable, validated, degrading gracefully:

  BASE    : OSM Overpass (free, always on) + a 2GIS/Yandex provider that ACTIVATES when a key exists
            (.secrets/komanda_sources.env → KOMANDA_2GIS_KEY=...). The full ~100 base + phones.
  ENRICH  : each clinic's OWN public website → validated messenger/phone (komanda_enrich, href-based).
  VERIFY  : only validated contacts count as reachable → "доказано написать им", no junk.

Lawful: open data (ODbL) + public business websites + a licensed maps API when keyed. No login, no
personal data, nothing sent. The agent can run deep (fetch every site) — not seconds, but provable.

Usage:      python3 harvester_engine_v1.py "<район>" [limit]
Importable: acquire(place, limit) -> verified feed (drop-in for komanda_pipeline_v1).
"""
import os, sys, json, time, urllib.request, urllib.parse, importlib.util as _ilu
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(p, n):
    s = _ilu.spec_from_file_location(n, p); m = _ilu.module_from_spec(s); s.loader.exec_module(m); return m


OSM = _load(ROOT / "scripts/socc/scout_live_osm_v1.py", "scout_live_osm_v1")
ENR = _load(ROOT / "scripts/socc/komanda_enrich_v1.py", "komanda_enrich_v1")
SOURCES_ENV = ROOT / ".secrets/komanda_sources.env"


def _key(name):
    if SOURCES_ENV.exists():
        for ln in SOURCES_ENV.read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith(name + "="):
                return ln.split("=", 1)[1].strip()
    return os.environ.get(name)


_2GIS_HOST = "https://catalog.api.2gis.ru/3.0/items"   # .com times out from RU-blocked egress; .ru works
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124"   # 2GIS.ru needs a UA or SSL times out


def _from_2gis(place, limit, key):
    """Base (+ contacts/website when the key's plan allows) from 2GIS Catalog API. Paginated. All RF."""
    out, page, got, PS = [], 1, 0, 10          # 2GIS caps page_size ~10 for this key → paginate
    while got < limit and page <= 12:
        q = urllib.parse.urlencode({"q": f"стоматология, {place}", "key": key, "page": page, "page_size": PS,
                                    "fields": "items.contact_groups,items.address_name,items.point"})
        d = None
        for attempt in range(3):                # RU host is flaky from some egress → retry with backoff
            try:
                req = urllib.request.Request(f"{_2GIS_HOST}?{q}", headers={"User-Agent": _UA})
                with urllib.request.urlopen(req, timeout=20) as r:
                    d = json.loads(r.read()); break
            except Exception:
                time.sleep(1.2 * (attempt + 1))
        if d is None:
            break
        items = (d.get("result", {}) or {}).get("items", [])
        if not items:
            break
        for it in items:
            name = (it.get("name") or "")
            if not any(k in name.lower() for k in ("стоматолог", "дент", "dental", "зуб")):
                continue                                      # keep dentistry, drop 2GIS fuzzy noise
            contacts = {}
            for g in it.get("contact_groups", []):
                for c in g.get("contacts", []):
                    typ, val = c.get("type"), (c.get("url") or c.get("value") or c.get("text"))
                    if not val:
                        continue
                    if typ == "phone":
                        contacts.setdefault("phone", ENR._valid_phone(val) or val)
                    elif typ in ("telegram", "whatsapp", "vk", "instagram", "website"):
                        contacts.setdefault(typ, val)
            best = next((c for c in ENR._REACH if c in contacts), None)
            out.append({"name": name.split(",")[0].strip(), "address": it.get("address_name", ""),
                        "channels": list(contacts.keys()) or ["unknown"],
                        "channel": best or "unknown", "contact_value": contacts.get(best, "") if best else "",
                        "contacts": contacts, "reachable": best is not None,
                        "website": contacts.get("website", ""),
                        "has_online_booking": bool(contacts.get("website")),
                        "reviews": [], "source_url": contacts.get("website") or "2gis", "osm": ""})
            got += 1
        page += 1
    return out


def acquire(place, limit=80, enrich=True):
    """Acquire the район's real clinic base + verified contacts, from every available source."""
    feed = OSM.find_clinics(place, limit)                       # free clean base
    sources = ["osm"]
    key2gis = _key("KOMANDA_2GIS_KEY")
    if key2gis:                                                 # licensed full base + phones
        have = {c["name"] for c in feed["clinics"]}
        for c in _from_2gis(place, limit, key2gis):
            if c["name"] and c["name"] not in have:
                feed["clinics"].append(c); have.add(c["name"])
        sources.append("2gis")
    if enrich:                                                  # each clinic's own site → verified messengers/phone
        ENR.enrich_feed(feed, limit_fetch=min(limit, 60))
        sources.append("website-enrich")
    feed["place"] = place
    feed["acquired"] = len(feed["clinics"])
    feed["reachable"] = sum(1 for c in feed["clinics"] if c.get("reachable"))
    feed["sources_used"] = sources
    feed["source"] = f"HARVESTER · {place} · sources={sources}"
    return feed


def main():
    place = sys.argv[1] if len(sys.argv) > 1 else "Казань"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 60
    f = acquire(place, limit)
    print(f"HARVESTER · {place}: добыто {f['acquired']} · достижимо {f['reachable']} · источники {f['sources_used']}")
    for c in f["clinics"][:25]:
        tag = ("📨 " + c["channel"] + " " + str(c.get("contact_value", ""))) if c.get("reachable") else "🚫 канал не найден"
        print(f"  - {c['name'][:34]:<34} {tag}")
    out = ROOT / "entity_substrate/domains/_komanda_harvest_feed.json"
    out.write_text(json.dumps(f, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nfeed → {out.relative_to(ROOT)}")
    if "2gis" not in f["sources_used"]:
        print("ⓘ для полной базы (~100 клиник + телефоны): .secrets/komanda_sources.env → KOMANDA_2GIS_KEY=<free key>")


if __name__ == "__main__":
    main()

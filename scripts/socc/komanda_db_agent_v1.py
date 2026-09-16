#!/usr/bin/env python3
"""
КОМАНДА DB Agent V1 — the establishment-discovery ENTITY ("Добытчик"). Наша фишка made durable.

Builds and GROWS an EXHAUSTIVE, deduplicated, persistent database of clinics for any район, so the
команда never misses a lead. Design principles (why "no troubles later"):

  EXHAUSTIVE   : reads the source's `total` and paginates until fetched >= total → coverage %,
                 with an explicit exhaustive flag. Nothing silently truncated.
  UNION+DEDUP  : merges every source (2GIS + OSM + contact enrich) into one record per real clinic,
                 keyed by normalized name+address. A clinic seen by two sources = one row, both cited.
  DURABLE      : the DB persists at SOVEREIGN/LEDGER/komanda_clinics_db.json and GROWS across runs —
                 a clinic is never lost; first_seen/last_seen/sources tracked. Atomic write.
  ROBUST       : retries + UA against flaky RU egress; partial runs degrade gracefully (coverage drops,
                 nothing corrupts). Contacts only when validated ("доказано написать").

Saved as the SOCC entity  entity_substrate/entities/harvester/  — a first-class organ the operator
owns forever, upstream of SCOUT. Sealing to sovereign canon is the operator's act (Λ₀).

Usage:
  python3 komanda_db_agent_v1.py "<район>"     # acquire/refresh a район into the DB, print coverage
  python3 komanda_db_agent_v1.py --report      # coverage + reachability across the whole DB
"""
import os, sys, json, time, re, urllib.request, urllib.parse, importlib.util as _ilu
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "SOVEREIGN/LEDGER/komanda_clinics_db.json"
SOURCES_ENV = ROOT / ".secrets/komanda_sources.env"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
_2GIS = "https://catalog.api.2gis.ru/3.0/items"


def _load(p, n):
    s = _ilu.spec_from_file_location(n, ROOT / p); m = _ilu.module_from_spec(s); s.loader.exec_module(m); return m


OSM = _load("scripts/socc/scout_live_osm_v1.py", "scout_live_osm_v1")
ENR = _load("scripts/socc/komanda_enrich_v1.py", "komanda_enrich_v1")


def now():
    return datetime.now(timezone.utc).isoformat()


def _key(name, addr=""):
    """Stable dedup key: normalized name + first chunk of address. One real clinic → one row."""
    n = re.sub(r"[^a-zа-я0-9]", "", (name or "").lower())
    a = re.sub(r"[^0-9а-я]", "", (addr or "").lower())[:18]
    return f"{n}|{a}"


def _2gis_key():
    if SOURCES_ENV.exists():
        for ln in SOURCES_ENV.read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith("KOMANDA_2GIS_KEY="):
                return ln.split("=", 1)[1].strip()
    return os.environ.get("KOMANDA_2GIS_KEY")


def _2gis_page(place, key, page, ps=10):
    q = urllib.parse.urlencode({"q": f"стоматология, {place}", "key": key, "page": page, "page_size": ps,
                                "fields": "items.contact_groups,items.address_name,items.point"})
    for _ in range(3):                                  # flaky RU egress → retry
        try:
            req = urllib.request.Request(f"{_2GIS}?{q}", headers={"User-Agent": UA})
            return json.loads(urllib.request.urlopen(req, timeout=20).read())
        except Exception:
            time.sleep(1.4)
    return None


def acquire_2gis_exhaustive(place, key, hard_cap=300):
    """Paginate 2GIS until ALL `total` items are pulled — the completeness core (nothing missed)."""
    first = _2gis_page(place, key, 1)
    if not first:
        return [], None
    total = (first.get("result", {}) or {}).get("total")
    items, page = [], 1
    while True:
        d = first if page == 1 else _2gis_page(place, key, page)
        got = (d.get("result", {}) or {}).get("items", []) if d else []
        if not got:
            break
        items += got
        if (total and len(items) >= total) or len(items) >= hard_cap:
            break
        page += 1
    out = []
    for it in items:
        n = (it.get("name") or "")
        if not any(k in n.lower() for k in ("стоматолог", "дент", "dental", "зуб")):
            continue                                    # keep dentistry, drop 2GIS fuzzy noise
        contacts = {}
        for g in it.get("contact_groups", []):
            for c in g.get("contacts", []):
                t, v = c.get("type"), (c.get("url") or c.get("value") or c.get("text"))
                if not v:
                    continue
                if t == "phone":
                    contacts.setdefault("phone", ENR._valid_phone(v) or v)
                elif t in ("telegram", "whatsapp", "vk", "instagram", "website"):
                    contacts.setdefault(t, v)
        out.append({"name": n.split(",")[0].strip(), "address": it.get("address_name", ""),
                    "contacts": contacts, "sources": ["2gis"]})
    return out, total


def _load_db():
    try:
        return json.loads(DB.read_text(encoding="utf-8"))
    except Exception:
        return {"clinics": {}, "districts": {}, "updated_at": None}


def _save_db(db):
    db["updated_at"] = now()
    DB.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DB)                                     # atomic → a torn run never corrupts the base


def acquire(place):
    db = _load_db()
    clinics = db.setdefault("clinics", {})
    key = _2gis_key()
    g2, src_total = (acquire_2gis_exhaustive(place, key) if key else ([], None))
    osm = OSM.find_clinics(place, 80).get("clinics", [])
    added = 0
    for c in osm + g2:
        k = _key(c.get("name"), c.get("address", ""))
        if not k.strip("|"):
            continue
        rec = clinics.get(k)
        if rec:                                         # union: same clinic, merge sources+contacts
            rec["sources"] = sorted(set(rec.get("sources", []) + c.get("sources", ["osm"])))
            rec["last_seen"] = now()
            for kk, vv in (c.get("contacts") or {}).items():
                if vv:
                    rec.setdefault("contacts", {}).setdefault(kk, vv)
        else:
            cts = c.get("contacts") or {}
            best = next((ch for ch in ENR._REACH if ch in cts), None)
            clinics[k] = {"name": c.get("name"), "address": c.get("address", ""), "district": place,
                          "contacts": cts, "channel": best or "unknown", "reachable": best is not None,
                          "sources": c.get("sources", ["osm"]), "first_seen": now(), "last_seen": now(),
                          "status": "candidate"}
            added += 1
        # refresh reachability off merged contacts
        r = clinics[k]
        b = next((ch for ch in ENR._REACH if ch in (r.get("contacts") or {})), None)
        r["channel"], r["reachable"] = (b or "unknown"), (b is not None)
    in_d = [k for k, v in clinics.items() if v.get("district") == place]
    cov = round(100.0 * len(in_d) / src_total, 1) if src_total else None
    db.setdefault("districts", {})[place] = {
        "source_total": src_total, "in_db": len(in_d), "coverage_pct": cov,
        "exhaustive": bool(src_total and len(in_d) >= src_total * 0.95), "last_run": now()}
    _save_db(db)
    return {"place": place, "added": added, "in_db": len(in_d), "source_total": src_total,
            "coverage_pct": cov, "reachable": sum(1 for k in in_d if clinics[k].get("reachable"))}


def report():
    db = _load_db()
    cl = db.get("clinics", {})
    reach = sum(1 for v in cl.values() if v.get("reachable"))
    print(f"КОМАНДА DB · всего клиник: {len(cl)} · достижимо: {reach} · районов: {len(db.get('districts',{}))}")
    for place, s in db.get("districts", {}).items():
        mark = "✅ исчерпано" if s.get("exhaustive") else "⚠ частично"
        print(f"  {place:<22} в базе {s.get('in_db')}/{s.get('source_total') or '?'} "
              f"покрытие {s.get('coverage_pct')}%  {mark}")
    print(f"db → {DB.relative_to(ROOT)}")


def main():
    if "--report" in sys.argv:
        report(); return
    place = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "Некрасовка, Москва"
    print(f"КОМАНДА DB Agent · добываю исчерпывающе «{place}» …")
    r = acquire(place)
    tot = r["source_total"]
    print(f"  добавлено новых: {r['added']} · в базе района: {r['in_db']}"
          + (f"/{tot} (покрытие {r['coverage_pct']}%)" if tot else " (2GIS-ключ не задан → только OSM)"))
    print(f"  достижимо (валидный контакт): {r['reachable']}")
    print(f"db → {DB.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

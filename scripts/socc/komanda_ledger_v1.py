#!/usr/bin/env python3
"""
КОМАНДА Ledger V1 — the team's memory of WHO it has already touched (no duplicates, ever).

This is the LEDGER role applied to outreach: a durable registry keyed by a stable clinic identity,
so a re-run NEVER re-drafts or re-contacts a clinic the команда already handled. This is the
operator's original ask ("исключить дубли") on the sales side.

Status lifecycle:  candidate → drafted → approved → sent → (replied / won / lost / skip)
Dedup rule: a clinic at status `drafted` or beyond is KNOWN — SCOUT/HERMES skip it on later runs.

Pure file state, atomic writes, no network. Registry: SOVEREIGN/LEDGER/komanda_contacts.json
"""
import json, re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "SOVEREIGN/LEDGER/komanda_contacts.json"
# statuses that mean "already handled" → never draft again
HANDLED = {"drafted", "approved", "sent", "replied", "won", "lost", "skip"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def key(clinic):
    """Stable identity: OSM url if present (immutable), else normalized name+channel."""
    osm = clinic.get("osm") or clinic.get("source_url") or ""
    if "openstreetmap.org" in osm:
        return osm.rsplit("/", 2)[-2] + "/" + osm.rsplit("/", 1)[-1]   # type/id
    nm = re.sub(r"\s+", " ", (clinic.get("name") or "").strip().lower())
    return "name:" + nm + "|" + (clinic.get("channel") or "")


def load():
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {"id": "KOMANDA_CONTACTS_V1", "contacts": {}, "updated_at": None}


def save(d):
    d["updated_at"] = _now()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(LEDGER)                                   # atomic → never a half-written ledger


def is_handled(d, clinic):
    rec = d["contacts"].get(key(clinic))
    return bool(rec and rec.get("status") in HANDLED)


def partition(d, clinics, place):
    """Split a fresh SCOUT list into (new, already_known) by the ledger — the dedup gate."""
    new, known = [], []
    for c in clinics:
        (known if is_handled(d, c) else new).append(c)
    return new, known


def record(d, clinic, place, status="drafted", extra=None):
    k = key(clinic)
    rec = d["contacts"].get(k) or {"first_seen": _now(), "place": place}
    rec.update({"name": clinic.get("name"), "channel": clinic.get("channel"),
                "contact": clinic.get("contact_value", ""), "place": place,
                "status": status, "last_run": _now(), "key": k})
    if extra:
        rec.update(extra)
    d["contacts"][k] = rec
    return rec


def mark(d, k, status):
    if k in d["contacts"]:
        d["contacts"][k]["status"] = status
        d["contacts"][k]["last_run"] = _now()
        return True
    return False


def counts(d):
    out = {}
    for r in d["contacts"].values():
        out[r.get("status", "?")] = out.get(r.get("status", "?"), 0) + 1
    return out


if __name__ == "__main__":
    d = load()
    print(f"KOMANDA Ledger · {len(d['contacts'])} контактов · {counts(d)}")
    print(f"file → {LEDGER.relative_to(ROOT)}")

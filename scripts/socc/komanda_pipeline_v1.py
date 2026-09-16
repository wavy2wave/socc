#!/usr/bin/env python3
"""
КОМАНДА Pipeline V1 — the sales team running as ONE machine (not two disconnected scripts).

Wires the real role engines end-to-end per PXS-1's DAG:
    SCOUT (find + PROVE pain, fail-closed)  →  HERMES (draft a touch on that evidence, PENDING_APPROVE)
and points every draft at the REAL, now-safe demo bot @anna_dent_bot (R1 safe-mode), not a placeholder.

LAWFUL BOUNDARY (unchanged, inherited from both engines):
  - SCOUT here runs on a FEED FILE. Live scraping (2GIS/Instagram/Dikidi adapters) stays the operator's
    fire. But a REAL run needs only a real feed file — so this adds `from_export()`: turn a legal public
    business export (2GIS/Yandex/Prodoctorov CSV-or-JSON the operator can lawfully pull) into a feed.
  - HERMES NEVER sends. Every draft is sent=False, status=PENDING_APPROVE. Sending each = operator approve.
  - Drafts cite ONLY real SCOUT evidence — no invented claims.

So: this script makes the команда operate as a unit and be ONE real feed away from a real run. Nothing
is scraped, nothing is sent, nothing touches a clinic. Fully reversible.

Usage:
  python3 komanda_pipeline_v1.py --starter                         # self-contained machine proof (writes a feed, runs end-to-end)
  python3 komanda_pipeline_v1.py --feed real_clinics.json          # REAL run on the operator's feed
  python3 komanda_pipeline_v1.py --export 2gis_dump.json --export-kind 2gis   # real export -> feed -> run
  (optional: --demo @anna_dent_bot   --domain entity_substrate/domains/dental.json)
"""
import json, sys, hashlib, importlib.util as _ilu
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[2]  # SOCC/
SCOUT_SRC = ROOT / "scripts/socc/scout_engine_v1.py"
HERMES_SRC = ROOT / "scripts/socc/hermes_engine_v1.py"
WORK = ROOT / "entity_substrate/domains"
PROOF = ROOT / "proofs/socc/komanda_pipeline_v1.proof.json"
MSK = timezone(timedelta(hours=3), name="MSK")
DEMO_BOT = "@anna_dent_bot"   # the REAL bot, made safe in R1 — patients verify ANNA themselves here


def _load(path, name):
    spec = _ilu.spec_from_file_location(name, path)
    m = _ilu.module_from_spec(spec); spec.loader.exec_module(m)
    return m


SCOUT = _load(SCOUT_SRC, "scout_engine_v1")
HERMES = _load(HERMES_SRC, "hermes_engine_v1")
OSM = _load(ROOT / "scripts/socc/scout_live_osm_v1.py", "scout_live_osm_v1")   # live source (open data)
LED = _load(ROOT / "scripts/socc/komanda_ledger_v1.py", "komanda_ledger_v1")   # contact registry (no-dup)
HARVEST = _load(ROOT / "scripts/socc/harvester_engine_v1.py", "harvester_engine_v1")   # acquisition agent (base+contacts)
APPROVE_Q = ROOT / "SOVEREIGN/LEDGER/komanda_approve_queue.json"


def _now():
    return datetime.now(timezone.utc)


DENTAL_DOMAIN = {
    "id": "dental_cis_v1",
    "vertical": "стоматология",
    "channels": ["telegram", "instagram", "whatsapp"],
    # the pain signals SCOUT looks for (domain-as-parameter — TFS-1 functor; barbershop would swap these)
    "icp_signals": ["no_online_booking", "slow_dm_reply", "reviews_mention_не_дозвониться"],
}

# Live domain: OSM can only EVIDENCE the absence of online booking — so the LIVE команда targets ONLY
# that signal. No fabricated slow-reply/review claims. Honest by construction (drafts cite a real gap).
DENTAL_DOMAIN_LIVE = {**DENTAL_DOMAIN, "id": "dental_cis_live", "icp_signals": ["no_online_booking"]}

# A realistic dental feed in the EXACT shape SCOUT consumes. This is a MACHINE-PROOF feed (shape-real,
# clinics illustrative) — swap for a real export/feed for a real run. Fields are the objective signals
# a legal public export carries: online-booking present?, last DM reply latency, public review text.
STARTER_FEED = {
    "source": "STARTER (machine proof — replace with --feed or --export for a real run)",
    "clinics": [
        {"name": "Клиника А", "channel": "telegram", "channels": ["telegram"],
         "has_online_booking": False, "dm_reply_minutes": None,
         "reviews": ["второй день не могу дозвониться, никто не берёт трубку"],
         "source_url": "example://listing/a"},
        {"name": "Клиника Б", "channel": "instagram", "channels": ["instagram"],
         "has_online_booking": False, "dm_reply_minutes": 240,
         "reviews": ["хороший врач, всё понравилось"],
         "source_url": "example://listing/b"},
        {"name": "Клиника В", "channel": "telegram", "channels": ["telegram"],
         "has_online_booking": True, "dm_reply_minutes": 5,
         "reviews": ["записалась онлайн за минуту, удобно"],
         "source_url": "example://listing/c"},   # healthy → SCOUT must SKIP (fail-closed, no pain)
    ],
}


def from_export(rows, kind="generic"):
    """Adapter: a legal public business export (list of dicts) -> SCOUT feed format.
    Maps the objective, public fields only. Unknown latency -> None (SCOUT treats as 'no timely reply').
    The operator pulls the export lawfully (public business data); this just reshapes it. No network."""
    clinics = []
    for r in rows:
        name = r.get("name") or r.get("title") or r.get("org") or "—"
        booking = r.get("has_online_booking")
        if booking is None:
            booking = bool(r.get("booking_url") or r.get("online_booking") or r.get("widget"))
        reviews = r.get("reviews") or ([r["review"]] if r.get("review") else [])
        ch = r.get("channel") or (r.get("channels") or ["telegram"])[0]
        clinics.append({
            "name": name, "channel": ch, "channels": r.get("channels") or [ch],
            "has_online_booking": booking,
            "dm_reply_minutes": r.get("dm_reply_minutes"),
            "reviews": reviews, "source_url": r.get("url") or r.get("source_url") or "",
        })
    return {"source": f"REAL EXPORT ({kind})", "clinics": clinics}


def run(domain, feed, demo):
    WORK.mkdir(parents=True, exist_ok=True)
    dom_p = WORK / "_komanda_domain.json"
    feed_p = WORK / "_komanda_feed.json"
    targets_p = WORK / "_komanda_scout_targets.json"
    new_targets_p = WORK / "_komanda_new_targets.json"
    queue_p = WORK / "_komanda_hermes_queue.json"
    dom_p.write_text(json.dumps(domain, ensure_ascii=False, indent=2), encoding="utf-8")
    feed_p.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    place = feed.get("place") or domain.get("id")

    print("\n╔══════════════════════════════════════════╗")
    print("║  КОМАНДА — единая машина  SCOUT → HERMES  ║")
    print(f"║  демо-бот: {demo:<30} ║")
    print("╚══════════════════════════════════════════╝")

    scout_out = SCOUT.run(str(dom_p), str(feed_p), str(targets_p))   # s1..s5: find + PROVE pain

    # enrich SCOUT targets with contact/reachability from the feed (SCOUT output stays pure)
    by_name = {c.get("name"): c for c in feed.get("clinics", [])}
    for tg in scout_out["targets"]:
        c = by_name.get(tg["name"], {})
        tg["reachable"] = c.get("reachable", False)
        tg["contact_value"] = c.get("contact_value", "")
        tg["contacts"] = c.get("contacts", {})
        tg["osm"] = c.get("osm", "")
        if c.get("channel"):
            tg["channel"] = c["channel"]

    # LEDGER dedup: only clinics NOT already handled get drafted (no duplicates, ever)
    led = LED.load()
    new_targets, known = LED.partition(led, scout_out["targets"], place)
    new_obj = {**{k: scout_out[k] for k in scout_out if k != "targets"}, "targets": new_targets}
    new_targets_p.write_text(json.dumps(new_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    hermes_out = HERMES.run(str(new_targets_p), demo, str(queue_p))   # drafts NEW targets only (H1: nothing sent)

    # build approve-queue + record new contacts to the ledger
    draft_by_name = {d["clinic"]: d for d in hermes_out["queue"]}
    items, reachable_n = [], 0
    for tg in new_targets:
        d = draft_by_name.get(tg["name"])
        if not d:
            continue
        reach = bool(tg.get("reachable"))
        reachable_n += int(reach)
        items.append({"key": LED.key(tg), "clinic": tg["name"], "channel": tg.get("channel"),
                      "contact": tg.get("contact_value", ""), "reachable": reach,
                      "signals": tg.get("signals", []), "message": d["message"], "status": "PENDING_APPROVE"})
        LED.record(led, tg, place, status="drafted")
    items.sort(key=lambda x: not x["reachable"])         # reachable first
    for i, it in enumerate(items, 1):
        it["n"] = i
    LED.save(led)
    aq = {"id": "KOMANDA_APPROVE_QUEUE_V1", "place": place, "demo_bot": demo,
          "created_at_utc": _now().isoformat(), "items": items,
          "counts": {"pending": len(items), "reachable": reachable_n, "unreachable": len(items) - reachable_n}}
    APPROVE_Q.parent.mkdir(parents=True, exist_ok=True)
    APPROVE_Q.write_text(json.dumps(aq, ensure_ascii=False, indent=2), encoding="utf-8")

    chain_ok = (scout_out["all_have_pain_evidence"] and hermes_out["all_pending_approve"]
                and hermes_out["all_cite_evidence"])
    body = {
        "id": "KOMANDA_PIPELINE_V1_PROOF",
        "komanda_runs_end_to_end": chain_ok,
        "place": place, "feed_source": feed.get("source"), "demo_bot": demo,
        "found": len(feed.get("clinics", [])),
        "scout": {"painful": scout_out["counts"]["in_list"], "skipped_no_pain": scout_out["counts"]["skipped"],
                  "all_targets_have_evidence": scout_out["all_have_pain_evidence"]},
        "ledger": {"new_drafted": len(new_targets), "already_known_deduped": len(known),
                   "reachable": reachable_n, "unreachable": len(items) - reachable_n},
        "hermes": {"drafts": hermes_out["count"], "all_pending_approve": hermes_out["all_pending_approve"],
                   "all_cite_evidence": hermes_out["all_cite_evidence"], "sent": 0},
        "law": "SCOUT fail-closed · LEDGER no-dup · HERMES sends nothing (H1) · drafts cite only real evidence",
        "truth_boundary": ("Autonomous discovery + dedup + draft, all reversible. Sending each draft is the "
                           "operator's one approve (lawful gate, ФЗ-38). Nothing sent, no clinic touched."),
        "status": "PASS" if chain_ok else "FAIL",
        "real_next": "operator reviews approve-queue (komanda_approve_v1.py --list) → approves reachable touches one by one",
    }
    digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]
    body["proof_hash"] = digest
    body["created_at_utc"] = _now().isoformat()
    PROOF.parent.mkdir(parents=True, exist_ok=True)
    PROOF.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n┌─ ЦЕПЬ КОМАНДЫ (proof) ─────────────────────")
    print(f"│ найдено {body['found']}  ·  с болью {body['scout']['painful']}  ·  отсеяно без боли {body['scout']['skipped_no_pain']} (fail-closed)")
    print(f"│ LEDGER: новых {body['ledger']['new_drafted']}  ·  дублей отсеяно {body['ledger']['already_known_deduped']}  ·  достижимы {body['ledger']['reachable']}/{len(items)}")
    print(f"│ HERMES: черновиков {body['hermes']['drafts']}  ·  ВСЕ PENDING_APPROVE  ·  отправлено 0")
    print(f"│ статус цепи: {'🟢 PASS' if chain_ok else '🔴 FAIL'}   hash {body['proof_hash']}")
    print(f"└─ proof → {PROOF.relative_to(ROOT)}")
    print(f"\n▶ очередь на approve → python3 scripts/socc/komanda_approve_v1.py --list   ({len(items)} писем, {reachable_n} достижимых)")
    print("⛔ Ничего не отправлено. Каждое письмо ждёт твоего approve = твой огонь (закон ФЗ-38).")
    return body


def main():
    args = sys.argv[1:]
    demo = args[args.index("--demo") + 1] if "--demo" in args else DEMO_BOT
    domain = DENTAL_DOMAIN
    if "--harvest" in args:                               # HARVESTER agent: base + verified contacts (any район)
        place = args[args.index("--harvest") + 1]
        limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 80
        print(f"… HARVESTER (агент-добытчик команды): база + контакты по «{place}» …")
        feed = HARVEST.acquire(place, limit)
        print(f"… добыто {feed.get('acquired', 0)} клиник · достижимо {feed.get('reachable', 0)} · источники {feed.get('sources_used')}")
        domain = DENTAL_DOMAIN_LIVE
    elif "--live" in args:                                # raw OSM (no enrichment) — sources clinics ITSELF
        place = args[args.index("--live") + 1]
        limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 40
        print(f"… SCOUT live (OSM open data): ищу реальные клиники в «{place}» …")
        feed = OSM.find_clinics(place, limit)
        print(f"… найдено {len(feed.get('clinics', []))} реальных клиник (из {feed.get('raw_count', 0)} в OSM)")
        domain = DENTAL_DOMAIN_LIVE
    elif "--export" in args:
        rows = json.loads(Path(args[args.index("--export") + 1]).read_text(encoding="utf-8"))
        rows = rows.get("items", rows) if isinstance(rows, dict) else rows
        kind = args[args.index("--export-kind") + 1] if "--export-kind" in args else "generic"
        feed = from_export(rows, kind)
    elif "--feed" in args:
        feed = json.loads(Path(args[args.index("--feed") + 1]).read_text(encoding="utf-8"))
    else:
        feed = STARTER_FEED
    if "--domain" in args:
        domain = json.loads(Path(args[args.index("--domain") + 1]).read_text(encoding="utf-8"))
    run(domain, feed, demo)


if __name__ == "__main__":
    main()

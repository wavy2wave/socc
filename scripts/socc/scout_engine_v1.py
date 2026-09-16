#!/usr/bin/env python3
"""
SCOUT Engine V1 — the hunter, made real (not a spec).

Implements SCOUT-SPEC-1 sub-DAG s1..s5 on a clinic feed: extract → detect_pain → score →
rank → emit list. Fail-closed (SC1): a clinic with NO pain evidence does NOT enter the list.
Domain-invariant: pain signals come from the domain file's icp_signals (dental or barbershop).

LAWFUL BOUNDARY (PXS-1): this proves the SCOUT LOGIC on a sample feed. It does NOT scrape live
sources — the live source adapters (2GIS/Instagram/Dikidi) are a separate GATED step (operator's
fire), because live scraping touches network + legal limits (SCOUT Λ L1/L2). Engine build = internal
and reversible; live operation = fire. No network here.

Usage:
  python3 scout_engine_v1.py <domain.json> <feed.json> [--out targets.json]
"""
import json, sys, re
from pathlib import Path
from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3), name="MSK")
SLOW_DM_MINUTES = 60            # порог «медленный ответ в директ»
NEG_REVIEW = re.compile(r"дозвон|не отвеч|не беру|никто не|games|игнор|перезвон", re.I)


def detect_pain(clinic, icp_signals):
    """Return list of {signal, evidence} actually present (real fields), per domain icp_signals."""
    found = []
    sig = set(icp_signals)
    if "no_online_booking" in sig and clinic.get("has_online_booking") is False:
        found.append({"signal": "no_online_booking", "evidence": "карточка: онлайн-записи нет"})
    if "slow_dm_reply" in sig:
        m = clinic.get("dm_reply_minutes")
        if m is None or (isinstance(m, (int, float)) and m > SLOW_DM_MINUTES):
            found.append({"signal": "slow_dm_reply",
                          "evidence": f"ответ в директ: {'нет ответа' if m is None else str(m)+' мин'} (порог {SLOW_DM_MINUTES})"})
    if any(s.startswith("reviews_mention") for s in sig):
        for rv in clinic.get("reviews", []):
            if NEG_REVIEW.search(rv):
                found.append({"signal": "reviews_mention_не_дозвониться", "evidence": f"отзыв: «{rv[:60]}»"})
                break
    return found


def score(clinic, pain, channels):
    icp_fit = 1 if set(clinic.get("channels", [clinic.get("channel")])) & set(channels) else 0
    pain_strength = len(pain)
    return round(pain_strength * 1.0 + icp_fit * 0.5, 2)


def run(domain_path, feed_path, out_path):
    domain = json.loads(Path(domain_path).read_text(encoding="utf-8"))
    feed = json.loads(Path(feed_path).read_text(encoding="utf-8"))
    icp = domain.get("icp_signals", [])
    channels = domain.get("channels", [])

    targets, skipped = [], []
    for c in feed.get("clinics", []):
        pain = detect_pain(c, icp)
        if not pain:                                   # SC1 fail-closed: нет боли → не в список
            skipped.append({"name": c.get("name"), "reason": "no_pain_evidence"})
            continue
        targets.append({
            "name": c.get("name"), "channel": c.get("channel"),
            "source_url": c.get("source_url"),
            "signals": [p["signal"] for p in pain],
            "evidence": pain,                          # каждая цель — с доказательством (Φ(s2))
            "score": score(c, pain, channels),
        })
    targets.sort(key=lambda t: t["score"], reverse=True)   # s4 rank

    ts = datetime.now(timezone.utc)
    out = {
        "id": "SCOUT_TARGETS_V1", "domain": domain.get("id"),
        "created_at_utc": ts.isoformat(), "created_at_msk": ts.astimezone(MSK).isoformat(timespec="seconds"),
        "source": "SAMPLE FEED (not live scrape — live adapters are a gated fire step)",
        "all_have_pain_evidence": all(t["evidence"] for t in targets),
        "targets": targets, "skipped_no_pain": skipped,
        "counts": {"in_list": len(targets), "skipped": len(skipped)},
        "next_after_pass": "HERMES.touch",
        "truth_boundary": "SCOUT logic proven on sample feed. No live scrape, no network. "
                          "Each listed clinic carries pain evidence (SC1). Live sourcing = operator fire.",
    }
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("SCOUT ENGINE V1 — охотник (на образце)")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"домен::{domain.get('id')}  feed::{len(feed.get('clinics',[]))} клиник")
    print(f"в список::{len(targets)}   отсеяно без боли::{len(skipped)} (fail-closed SC1)")
    print("— ранжированные цели (с доказательством боли) —")
    for i, t in enumerate(targets, 1):
        print(f"  {i}. {t['name']:<22} score {t['score']}  ::  {', '.join(t['signals'])}")
        for e in t["evidence"]:
            print(f"        ↳ {e['evidence']}")
    if skipped:
        print("— отсеяны (нет боли = не беспокоим) —")
        for s in skipped:
            print(f"  ✗ {s['name']}")
    print(f"targets::{out_path}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: scout_engine_v1.py <domain.json> <feed.json> [out.json]"); raise SystemExit(2)
    out = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else "entity_substrate/domains/_scout_targets.json"
    run(sys.argv[1], sys.argv[2], out)

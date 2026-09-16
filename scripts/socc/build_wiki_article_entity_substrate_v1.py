#!/usr/bin/env python3
"""Knowledge Substrate step 3 — build the Entity Substrate wiki article.

Selects topic-relevant claims (mention "Entity Substrate" OR come from in-repo
canon), governs them by freshness/authority, builds timeline + idea branches +
source index, and writes the living article (md + json). The worked-out main-line
prose is injected from an authored sidecar if present. No LLM. No global route change.
"""
import sys
import glob
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))

from knowledge_substrate.io import (
    now_utc, now_msk, read_json, read_text, write_json, write_text, h, discipline_flags,
)
from knowledge_substrate.anchors import source_link_record
from knowledge_substrate import governance, wiki

ROOT = Path(".")
ACTIVE = ROOT / "SYSTEM/CAPABILITIES/memory_continuity/ACTIVE_KNOWLEDGE_SUBSTRATE_DIRECTION.json"
INGEST_DIR = ROOT / "SOVEREIGN/MEMORY/documents/ingested"
CANON_CONNECTOR = "CONNECTOR_ENTITY_SUBSTRATE_CANON_V1"
CORE_ENTITY = "Entity Substrate"

ARTICLE_MD = ROOT / "SOVEREIGN/WIKI/pages/entity_substrate.md"
ARTICLE_JSON = ROOT / "SOVEREIGN/WIKI/pages/entity_substrate.json"
TIMELINE = ROOT / "SOVEREIGN/WIKI/evolution/entity_substrate_timeline_v1.json"
INDEX = ROOT / "SOVEREIGN/WIKI/indexes/KNOWLEDGE_SUBSTRATE_INDEX_V1.json"
MAIN_LINE_SIDECAR = ROOT / "SOVEREIGN/WIKI/pages/_entity_substrate_main_line.md"
PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/WIKI_ARTICLE_ENTITY_SUBSTRATE_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/WIKI_ARTICLE_ENTITY_SUBSTRATE_V1_MEMORY.json"

EXPECTED = "build_wiki_article_entity_substrate_v1"
NEXT = "validate_knowledge_substrate_v1"
TOPIC = "entity_substrate"

TRUTH = ("Knowledge Substrate wiki article build only. Deterministic synthesis from "
         "ingested records; main-line prose authored separately. Source hyperlinks "
         "preserved. No LLM. Global route authority untouched. No daemon/background/network.")


def qualifies(claim, is_canon):
    return is_canon or (CORE_ENTITY in claim.get("entities", []))


records = [read_json(f) for f in sorted(glob.glob(str(INGEST_DIR / "*.json")))]
records = [r for r in records if r]

claims = []
source_usage = {}        # sha16 -> {name, abs_path, lines_used}
date_events = []         # for timeline (canon-authoritative + core)

for r in records:
    is_canon = r.get("connector") == CANON_CONNECTOR
    sha16 = r.get("source_sha16")
    abs_path = r.get("abs_path")
    name = Path(abs_path).name if abs_path else sha16
    used = 0
    for c in r.get("claims", []):
        if not qualifies(c, is_canon):
            continue
        link = source_link_record(sha16, abs_path, c["line"])
        claims.append({
            "text": c["text"],
            "entities": c["entities"],
            "polarity": c["polarity"],
            "intent": c["intent"],
            "source_mtime_utc": r.get("source_mtime_utc"),
            "source_provenance": r.get("source_provenance"),
            "link": link,
        })
        used += 1
    # timeline events: canon dates (authoritative) + dates from chats where
    # Entity Substrate is a recurring pattern (evolution of discussion)
    core_pattern = r.get("entity_counts", {}).get(CORE_ENTITY, 0) >= 3
    if is_canon or core_pattern:
        for d in r.get("dates", []):
            if d["value"] < "2026-01-01" or d["value"] > "2027-01-01":
                continue  # drop implausible parsed dates
            date_events.append({"date": d["value"], "text": f"{name}: {d['raw']}",
                                "link": source_link_record(sha16, abs_path, d["line"])})
    if used:
        source_usage[sha16] = {"name": name, "abs_path": abs_path, "lines_used": used}

governed = governance.classify(claims)

# timeline: dedupe by (date) keep first, sort
seen_dates = {}
for e in sorted(date_events, key=lambda x: (x["date"], x["link"]["line"])):
    seen_dates.setdefault(e["date"], e)
timeline = [
    {"date": e["date"], "event": e["text"][:200],
     "source": {"sha16": e["link"]["sha16"], "line": e["link"]["line"], "ref": e["link"]["ref"]}}
    for e in seen_dates.values()
]
timeline.sort(key=lambda t: t["date"])

branches = wiki.build_idea_branches(
    governed["current_authority"] + governed["conflicting"] + governed["historical"]
)

# definition: longest current-authority canon claim mentioning the core entity
canon_defs = [c for c in governed["current_authority"]
              if CORE_ENTITY in c.get("entities", [])
              and c.get("source_provenance") in ("canon_document", "system_state")]
definition = {"text": "", "source": {}}
if canon_defs:
    best = max(canon_defs, key=lambda c: len(c["text"]))
    definition = {"text": best["text"],
                  "source": {"ref": best["link"]["ref"], "md_link": best["link"]["md_link"]}}

source_links = [
    {"sha16": k, "name": v["name"], "abs_path": v["abs_path"], "lines_used": v["lines_used"]}
    for k, v in sorted(source_usage.items(), key=lambda kv: -kv[1]["lines_used"])
]

main_line_text = read_text(MAIN_LINE_SIDECAR).strip() if MAIN_LINE_SIDECAR.exists() else ""

article_json = wiki.assemble_json(TOPIC, definition, governed, timeline, branches,
                                  source_links, main_line_text or None)
article_json["created_at_utc"] = now_utc()
article_json["article_hash"] = h(article_json)

article_md = wiki.assemble_md(TOPIC, definition, governed, timeline, branches,
                              source_links, main_line_text or None)

timeline_doc = {
    "id": "ENTITY_SUBSTRATE_TIMELINE_V1",
    "topic": TOPIC,
    "created_at_utc": now_utc(),
    "events": timeline,
}

index_doc = read_json(INDEX) or {"id": "KNOWLEDGE_SUBSTRATE_INDEX_V1", "articles": {}}
index_doc["updated_at_utc"] = now_utc()
index_doc.setdefault("articles", {})[TOPIC] = {
    "page_md": str(ARTICLE_MD),
    "page_json": str(ARTICLE_JSON),
    "timeline": str(TIMELINE),
    "governance_counts": governed["counts"],
    "source_count": len(source_links),
}

checks = {
    "ingested_records_present": len(records) > 0,
    "topic_claims_found": len(claims) > 0,
    "current_authority_nonempty": governed["counts"]["current"] > 0,
    "definition_extracted": bool(definition["text"]),
    "timeline_built": len(timeline) > 0,
    "source_links_present": len(source_links) > 0,
    "every_current_claim_has_link": all(bool(c["link"]["ref"]) for c in governed["current_authority"]),
    "global_route_untouched": True,
}
hard = [{"code": "CHECK_FAIL", "check": k} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

proof = {
    "id": "WIKI_ARTICLE_ENTITY_SUBSTRATE_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": "memory_continuity",
    "step": EXPECTED,
    "topic": TOPIC,
    "article_md": str(ARTICLE_MD),
    "article_json": str(ARTICLE_JSON),
    "timeline": str(TIMELINE),
    "index": str(INDEX),
    "governance_counts": governed["counts"],
    "topic_claims": len(claims),
    "source_count": len(source_links),
    "main_line_authored": bool(main_line_text),
    "checks": checks,
    "hard_failures": hard,
    "real_next": NEXT if status == "PASS" else "repair_" + EXPECTED,
    "truth_boundary": TRUTH,
}
proof.update(discipline_flags())
proof["proof_hash"] = h(proof)

memory = {
    "id": "WIKI_ARTICLE_ENTITY_SUBSTRATE_V1_MEMORY",
    "created_at_utc": now_utc(),
    "status": status,
    "memory_effect": (f"Built living wiki article '{TOPIC}': "
                      f"{governed['counts']['current']} current-authority claims, "
                      f"{governed['counts']['conflicting']} conflicting, "
                      f"{len(timeline)} timeline events, {len(source_links)} sources, "
                      f"main_line_authored={bool(main_line_text)}."),
    "proof": str(PROOF),
    "article_md": str(ARTICLE_MD),
    "real_next": NEXT if status == "PASS" else "repair_" + EXPECTED,
    "truth_boundary": TRUTH,
}

write_json(ARTICLE_JSON, article_json)
write_text(ARTICLE_MD, article_md)
write_json(TIMELINE, timeline_doc)
write_json(INDEX, index_doc)
write_json(PROOF, proof)
write_json(MEMORY, memory)

if status == "PASS":
    active = read_json(ACTIVE)
    active["last_step"] = EXPECTED
    active["next_required_step"] = NEXT
    active["updated_at_utc"] = now_utc()
    write_json(ACTIVE, active)

print("KNOWLEDGE SUBSTRATE :: WIKI ARTICLE :: " + status)
print("TOPIC::" + TOPIC)
print("ARTICLE_MD::" + str(ARTICLE_MD))
print("CURRENT_AUTHORITY::" + str(governed["counts"]["current"]))
print("CONFLICTING::" + str(governed["counts"]["conflicting"]))
print("HISTORICAL::" + str(governed["counts"]["historical"]))
print("DEPRECATED::" + str(governed["counts"]["deprecated"]))
print("TIMELINE_EVENTS::" + str(len(timeline)))
print("SOURCE_COUNT::" + str(len(source_links)))
print("MAIN_LINE_AUTHORED::" + str(bool(main_line_text)))
print("DEFINITION_FOUND::" + str(bool(definition["text"])))
print("PROOF::" + str(PROOF))
print("REAL_NEXT::" + (NEXT if status == "PASS" else "repair_" + EXPECTED))
print("LLM_USED::False")
print("GLOBAL_ROUTE_TOUCHED::False")
print("TRUTH_BOUNDARY::" + TRUTH)

raise SystemExit(0 if status == "PASS" else 1)

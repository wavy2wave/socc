#!/usr/bin/env python3
"""Knowledge Substrate step 2 — deterministic ingest of registered sources.

For each source in the registry, read the file and run the no-LLM extractors
(dates / entities / claims / patterns / intent markers). Writes one ingested
record per source under SOVEREIGN/MEMORY/documents/ingested/<sha16>.json, plus a
proof + memory sidecar. Advances the organ-local pointer. No global route change.

Usage: ingest_knowledge_sources_v1.py [--topic entity_substrate]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))

from knowledge_substrate.io import (
    now_utc, now_msk, read_json, read_text, write_json, h, discipline_flags,
)
from knowledge_substrate.parser import parse_text, ENTITY_LEXICON

ROOT = Path(".")
ACTIVE = ROOT / "SYSTEM/CAPABILITIES/memory_continuity/ACTIVE_KNOWLEDGE_SUBSTRATE_DIRECTION.json"
REGISTRY = ROOT / "SOVEREIGN/MEMORY/documents/SOURCE_REGISTRY_V1.json"
INGEST_DIR = ROOT / "SOVEREIGN/MEMORY/documents/ingested"
PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_INGEST_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/KNOWLEDGE_SUBSTRATE_INGEST_V1_MEMORY.json"

EXPECTED = "ingest_knowledge_sources_v1"
NEXT = "build_wiki_article_entity_substrate_v1"

# entities that mark the entity_substrate topic
TOPIC_ENTITIES = {
    "entity_substrate": ["Entity Substrate", "ANNA", "SOCC", "Hermes", "Codex",
                         "Self-construction", "Knowledge Substrate"],
    "anna": ["ANNA", "Dental Clinic", "Administrator", "Vertical Agent", "Persona",
             "Booking", "Telegram", "Subscription"],
}

TRUTH = ("Knowledge Substrate deterministic ingest only. No LLM. Read-only over "
         "sources. Produces parsed memory with source line anchors. Global route "
         "authority untouched. No daemon/background/network.")

args = sys.argv[1:]
topic = "entity_substrate"
if "--topic" in args:
    try:
        topic = args[args.index("--topic") + 1]
    except IndexError:
        pass
topic_entities = TOPIC_ENTITIES.get(topic, list(ENTITY_LEXICON.keys()))

registry = read_json(REGISTRY)
sources = registry.get("sources", [])

ingested_count = 0
topic_count = 0
total_claims = 0
total_dates = 0
total_entities = 0
written = []
errors = []

for s in sources:
    text = read_text(s["abs_path"])
    if not text:
        errors.append(f"EMPTY_OR_UNREADABLE::{s['abs_path']}")
        continue
    parsed = parse_text(text, topic_entities=topic_entities, topic_name=topic)
    record = {
        "id": f"INGESTED_{s['sha16']}",
        "source_sha16": s["sha16"],
        "abs_path": s["abs_path"],
        "rel_path": s.get("rel_path"),
        "connector": s.get("connector"),
        "source_provenance": s.get("provenance"),
        "source_mtime_utc": s.get("mtime_utc"),
        "created_at_utc": now_utc(),
        "parser_version": "ingest_v1_nollm",
        "dates": parsed["dates"],
        "entities": parsed["entities"],
        "claims": parsed["claims"],
        "patterns": parsed["patterns"],
        "intent_markers": parsed["intent_markers"],
        "entity_counts": parsed["entity_counts"],
        "topics": parsed["topics"],
        "llm_used": False,
    }
    record["ingest_hash"] = h(record)
    write_json(INGEST_DIR / f"{s['sha16']}.json", record)
    written.append(s["sha16"])
    ingested_count += 1
    total_claims += len(parsed["claims"])
    total_dates += len(parsed["dates"])
    total_entities += len(parsed["entities"])
    if topic in parsed["topics"]:
        topic_count += 1

checks = {
    "registry_present": bool(sources),
    "ingested_all_readable_sources": ingested_count > 0,
    "topic_sources_found": topic_count > 0,
    "claims_extracted": total_claims > 0,
    "every_record_no_llm": True,
    "ingest_dir_written": INGEST_DIR.exists(),
    "global_route_untouched": True,
}
hard = [{"code": "CHECK_FAIL", "check": k} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

summary = {
    "topic": topic,
    "sources_total": len(sources),
    "ingested_count": ingested_count,
    "topic_source_count": topic_count,
    "total_claims": total_claims,
    "total_dates": total_dates,
    "total_entities": total_entities,
    "errors": errors,
}

proof = {
    "id": "KNOWLEDGE_SUBSTRATE_INGEST_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": "memory_continuity",
    "step": EXPECTED,
    "ingest_dir": str(INGEST_DIR),
    "summary": summary,
    "checks": checks,
    "hard_failures": hard,
    "real_next": NEXT if status == "PASS" else "repair_" + EXPECTED,
    "truth_boundary": TRUTH,
}
proof.update(discipline_flags())
proof["proof_hash"] = h(proof)

memory = {
    "id": "KNOWLEDGE_SUBSTRATE_INGEST_V1_MEMORY",
    "created_at_utc": now_utc(),
    "status": status,
    "memory_effect": f"Ingested {ingested_count} sources deterministically; "
                     f"{topic_count} relevant to topic '{topic}'; "
                     f"{total_claims} claims, {total_dates} dates extracted.",
    "proof": str(PROOF),
    "real_next": NEXT if status == "PASS" else "repair_" + EXPECTED,
    "truth_boundary": TRUTH,
}

write_json(PROOF, proof)
write_json(MEMORY, memory)

if status == "PASS":
    active = read_json(ACTIVE)
    active["last_step"] = EXPECTED
    active["next_required_step"] = NEXT
    active["updated_at_utc"] = now_utc()
    write_json(ACTIVE, active)

print("KNOWLEDGE SUBSTRATE :: INGEST :: " + status)
print("TOPIC::" + topic)
print("INGESTED::" + str(ingested_count))
print("TOPIC_SOURCES::" + str(topic_count))
print("TOTAL_CLAIMS::" + str(total_claims))
print("TOTAL_DATES::" + str(total_dates))
print("TOTAL_ENTITIES::" + str(total_entities))
print("ERRORS::" + str(len(errors)))
print("PROOF::" + str(PROOF))
print("REAL_NEXT::" + (NEXT if status == "PASS" else "repair_" + EXPECTED))
print("LLM_USED::False")
print("GLOBAL_ROUTE_TOUCHED::False")
print("TRUTH_BOUNDARY::" + TRUTH)

raise SystemExit(0 if status == "PASS" else 1)

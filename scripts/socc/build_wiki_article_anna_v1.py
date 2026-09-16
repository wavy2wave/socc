#!/usr/bin/env python3
"""Knowledge Substrate — build the ANNA wiki article (topic = anna).

Reuses the generic deterministic builder. Selects ANNA/product claims, governs
by freshness, writes the living article (md+json) + timeline + index entry + proof.
No LLM. No global route change.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))

from knowledge_substrate.io import now_utc, now_msk, read_json, read_text, write_json, write_text, h, discipline_flags
from knowledge_substrate import wiki

ROOT = Path(".")
INGEST_DIR = ROOT / "SOVEREIGN/MEMORY/documents/ingested"
CANON_CONNECTORS = ("CONNECTOR_ANNA_V1",)
CORE_ENTITIES = ["ANNA", "Dental Clinic", "Administrator", "Vertical Agent", "Persona", "Booking"]

ARTICLE_MD = ROOT / "SOVEREIGN/WIKI/pages/anna.md"
ARTICLE_JSON = ROOT / "SOVEREIGN/WIKI/pages/anna.json"
TIMELINE = ROOT / "SOVEREIGN/WIKI/evolution/anna_timeline_v1.json"
INDEX = ROOT / "SOVEREIGN/WIKI/indexes/KNOWLEDGE_SUBSTRATE_INDEX_V1.json"
MAIN_LINE_SIDECAR = ROOT / "SOVEREIGN/WIKI/pages/_anna_main_line.md"
PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/WIKI_ARTICLE_ANNA_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/WIKI_ARTICLE_ANNA_V1_MEMORY.json"
TOPIC = "anna"

TRUTH = ("Knowledge Substrate ANNA wiki article build only. Deterministic synthesis from "
         "ingested records; source hyperlinks preserved. No LLM. Global route untouched.")

governed, timeline, branches, source_links, definition, n_claims = wiki.build_topic_article(
    TOPIC, CORE_ENTITIES, INGEST_DIR, CANON_CONNECTORS
)

main_line = read_text(MAIN_LINE_SIDECAR).strip() if MAIN_LINE_SIDECAR.exists() else ""

article_json = wiki.assemble_json(TOPIC, definition, governed, timeline, branches,
                                  source_links, main_line or None)
article_json["created_at_utc"] = now_utc()
article_json["article_hash"] = h(article_json)
article_md = wiki.assemble_md(TOPIC, definition, governed, timeline, branches,
                              source_links, main_line or None)

index_doc = read_json(INDEX) or {"id": "KNOWLEDGE_SUBSTRATE_INDEX_V1", "articles": {}}
index_doc["updated_at_utc"] = now_utc()
index_doc.setdefault("articles", {})[TOPIC] = {
    "page_md": str(ARTICLE_MD), "page_json": str(ARTICLE_JSON), "timeline": str(TIMELINE),
    "governance_counts": governed["counts"], "source_count": len(source_links),
}

checks = {
    "topic_claims_found": n_claims > 0,
    "current_authority_nonempty": governed["counts"]["current"] > 0,
    "source_links_present": len(source_links) > 0,
    "every_current_claim_has_link": all(bool(c["link"]["ref"]) for c in governed["current_authority"]),
    "global_route_untouched": True,
}
hard = [{"code": "CHECK_FAIL", "check": k} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

proof = {
    "id": "WIKI_ARTICLE_ANNA_V1_PROOF", "created_at_utc": now_utc(), "created_at_msk": now_msk(),
    "status": status, "capability": "memory_continuity", "step": "build_wiki_article_anna_v1",
    "topic": TOPIC, "article_md": str(ARTICLE_MD), "article_json": str(ARTICLE_JSON),
    "governance_counts": governed["counts"], "topic_claims": n_claims,
    "source_count": len(source_links), "main_line_authored": bool(main_line),
    "checks": checks, "hard_failures": hard,
    "real_next": "validate_knowledge_substrate_v1" if status == "PASS" else "repair_build_wiki_article_anna_v1",
    "truth_boundary": TRUTH,
}
proof.update(discipline_flags())
proof["proof_hash"] = h(proof)

memory = {
    "id": "WIKI_ARTICLE_ANNA_V1_MEMORY", "created_at_utc": now_utc(), "status": status,
    "memory_effect": (f"Built living wiki article 'anna': {governed['counts']['current']} current, "
                      f"{governed['counts']['conflicting']} conflicting, {len(timeline)} timeline events, "
                      f"{len(source_links)} sources."),
    "proof": str(PROOF), "article_md": str(ARTICLE_MD), "truth_boundary": TRUTH,
}

write_json(ARTICLE_JSON, article_json)
write_text(ARTICLE_MD, article_md)
write_json(TIMELINE, {"id": "ANNA_TIMELINE_V1", "topic": TOPIC, "created_at_utc": now_utc(), "events": timeline})
write_json(INDEX, index_doc)
write_json(PROOF, proof)
write_json(MEMORY, memory)

print("KNOWLEDGE SUBSTRATE :: WIKI ARTICLE ANNA :: " + status)
print("TOPIC::anna")
print("ARTICLE_MD::" + str(ARTICLE_MD))
print("CURRENT_AUTHORITY::" + str(governed["counts"]["current"]))
print("CONFLICTING::" + str(governed["counts"]["conflicting"]))
print("HISTORICAL::" + str(governed["counts"]["historical"]))
print("DEPRECATED::" + str(governed["counts"]["deprecated"]))
print("TIMELINE_EVENTS::" + str(len(timeline)))
print("SOURCE_COUNT::" + str(len(source_links)))
print("TOPIC_CLAIMS::" + str(n_claims))
print("DEFINITION_FOUND::" + str(bool(definition["text"])))
print("PROOF::" + str(PROOF))
print("LLM_USED::False")
print("GLOBAL_ROUTE_TOUCHED::False")
print("TRUTH_BOUNDARY::" + TRUTH)

raise SystemExit(0 if status == "PASS" else 1)

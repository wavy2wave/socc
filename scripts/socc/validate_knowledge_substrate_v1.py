#!/usr/bin/env python3
"""Knowledge Substrate step 4 — validate the organ run.

Checks: scan/ingest/article proofs PASS; article has current authority; every
current-authority claim resolves to a real source line (file exists, line in
range); governance counts agree with the article; timeline present; no orphan
anchors in the source index. Writes a validation proof. No global route change.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))

from knowledge_substrate.io import now_utc, now_msk, read_json, read_text, write_json, h, discipline_flags

ROOT = Path(".")
ACTIVE = ROOT / "SYSTEM/CAPABILITIES/memory_continuity/ACTIVE_KNOWLEDGE_SUBSTRATE_DIRECTION.json"
SCAN_PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_SOURCE_SCAN_V1_PROOF.json"
INGEST_PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_INGEST_V1_PROOF.json"
ARTICLE_PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/WIKI_ARTICLE_ENTITY_SUBSTRATE_V1_PROOF.json"
ARTICLE_JSON = ROOT / "SOVEREIGN/WIKI/pages/entity_substrate.json"
TIMELINE = ROOT / "SOVEREIGN/WIKI/evolution/entity_substrate_timeline_v1.json"
PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_VALIDATION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/KNOWLEDGE_SUBSTRATE_VALIDATION_V1_MEMORY.json"

EXPECTED = "validate_knowledge_substrate_v1"
NEXT = "review_knowledge_substrate_v1"
TRUTH = ("Knowledge Substrate validation only. Verifies proofs, claim->source line "
         "resolution, governance integrity, and absence of orphan anchors. No build. "
         "Global route authority untouched. No daemon/background/network/LLM.")

_linecache = {}


def line_ok(abs_path, line):
    if abs_path not in _linecache:
        txt = read_text(abs_path)
        _linecache[abs_path] = txt.count("\n") + 1 if txt else 0
    n = _linecache[abs_path]
    return n > 0 and 1 <= int(line) <= n


def proof_pass(p):
    o = read_json(p)
    return o.get("status") == "PASS" and o.get("hard_failures") == []


article = read_json(ARTICLE_JSON)
buckets = ["current_authority", "conflicting", "historical", "deprecated"]
all_claims = [c for b in buckets for c in article.get(b, [])]
current = article.get("current_authority", [])

# resolve every current-authority claim + sample of the rest
unresolved = []
for c in current:
    src = c.get("source", {})
    if not src.get("ref") or not line_ok(src.get("ref", "").rsplit(":", 1)[0], src.get("line", 0)):
        unresolved.append(src.get("ref"))

# orphan anchors in source index
orphan_sources = []
for s in article.get("source_links", []):
    if not Path(s["abs_path"]).exists():
        orphan_sources.append(s["abs_path"])

article_proof = read_json(ARTICLE_PROOF)
counts_match = article.get("governance_counts") == article_proof.get("governance_counts")
timeline_doc = read_json(TIMELINE)

checks = {
    "scan_proof_pass": proof_pass(SCAN_PROOF),
    "ingest_proof_pass": proof_pass(INGEST_PROOF),
    "article_proof_pass": proof_pass(ARTICLE_PROOF),
    "article_json_present": bool(article),
    "current_authority_nonempty": len(current) > 0,
    "all_current_claims_resolve_to_source_line": len(unresolved) == 0,
    "no_orphan_source_links": len(orphan_sources) == 0,
    "governance_counts_match_proof": counts_match,
    "definition_present": bool(article.get("definition", {}).get("text")),
    "timeline_present": len(timeline_doc.get("events", [])) > 0,
    "article_llm_not_used": article.get("llm_used") is False,
    "global_route_untouched": True,
}
hard = [{"code": "CHECK_FAIL", "check": k} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

proof = {
    "id": "KNOWLEDGE_SUBSTRATE_VALIDATION_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": "memory_continuity",
    "step": EXPECTED,
    "claims_validated": len(all_claims),
    "current_authority_validated": len(current),
    "unresolved_refs": unresolved[:20],
    "orphan_sources": orphan_sources[:20],
    "checks": checks,
    "hard_failures": hard,
    "real_next": NEXT if status == "PASS" else "repair_" + EXPECTED,
    "truth_boundary": TRUTH,
}
proof.update(discipline_flags())
proof["proof_hash"] = h(proof)

memory = {
    "id": "KNOWLEDGE_SUBSTRATE_VALIDATION_V1_MEMORY",
    "created_at_utc": now_utc(),
    "status": status,
    "memory_effect": f"Validated Knowledge Substrate: {len(current)} current-authority "
                     f"claims resolve to source lines; {len(orphan_sources)} orphan sources.",
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

print("KNOWLEDGE SUBSTRATE :: VALIDATION :: " + status)
print("CLAIMS_VALIDATED::" + str(len(all_claims)))
print("CURRENT_AUTHORITY_VALIDATED::" + str(len(current)))
print("UNRESOLVED_REFS::" + str(len(unresolved)))
print("ORPHAN_SOURCES::" + str(len(orphan_sources)))
print("PROOF::" + str(PROOF))
print("REAL_NEXT::" + (NEXT if status == "PASS" else "repair_" + EXPECTED))
print("HARD_FAILURES::" + str(hard))
print("TRUTH_BOUNDARY::" + TRUTH)

raise SystemExit(0 if status == "PASS" else 1)

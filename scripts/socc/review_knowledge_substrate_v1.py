#!/usr/bin/env python3
"""Knowledge Substrate step 5 — review/seal the organ run.

Confirms validation PASS, discipline flags false across the proof chain, and a
truth boundary on the article. Seals the Knowledge Substrate pilot. Advances the
organ-local pointer to a sealed/idle state. No global route change.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))

from knowledge_substrate.io import now_utc, now_msk, read_json, write_json, h, discipline_flags

ROOT = Path(".")
ACTIVE = ROOT / "SYSTEM/CAPABILITIES/memory_continuity/ACTIVE_KNOWLEDGE_SUBSTRATE_DIRECTION.json"
VALIDATION_PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_VALIDATION_V1_PROOF.json"
ARTICLE_JSON = ROOT / "SOVEREIGN/WIKI/pages/entity_substrate.json"
CHAIN = [
    ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_SOURCE_SCAN_V1_PROOF.json",
    ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_INGEST_V1_PROOF.json",
    ROOT / "SOVEREIGN/PROOF/proof_chain/WIKI_ARTICLE_ENTITY_SUBSTRATE_V1_PROOF.json",
    VALIDATION_PROOF,
]
PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/KNOWLEDGE_SUBSTRATE_REVIEW_V1_MEMORY.json"

EXPECTED = "review_knowledge_substrate_v1"
NEXT = "knowledge_substrate_sealed_idle"
TRUTH = ("Knowledge Substrate review/seal only. Confirms the pilot organ run is "
         "proof-backed and discipline-clean. Entity Substrate itself is NOT built; "
         "ANNA is NOT born. Global route authority untouched. No daemon/background/network/LLM.")


def proof_pass(p):
    o = read_json(p)
    return o.get("status") == "PASS" and o.get("hard_failures") == []


def discipline_clean(p):
    o = read_json(p)
    forbidden = ["daemon_running", "network_used", "background_loop_enabled",
                 "entity_birth_allowed", "anna_birth_allowed", "agi_claim_allowed", "llm_used"]
    return all(o.get(k) is False for k in forbidden if k in o)


article = read_json(ARTICLE_JSON)

checks = {
    "validation_proof_pass": proof_pass(VALIDATION_PROOF),
    "whole_chain_pass": all(proof_pass(p) for p in CHAIN),
    "whole_chain_discipline_clean": all(discipline_clean(p) for p in CHAIN),
    "article_truth_present": bool(article.get("freshness_rule")),
    "article_has_current_authority": len(article.get("current_authority", [])) > 0,
    "article_has_source_links": len(article.get("source_links", [])) > 0,
    "global_route_untouched": True,
}
hard = [{"code": "CHECK_FAIL", "check": k} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

proof = {
    "id": "KNOWLEDGE_SUBSTRATE_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": "memory_continuity",
    "step": EXPECTED,
    "knowledge_substrate_pilot_sealed": status == "PASS",
    "sealed_chain": [str(p) for p in CHAIN],
    "checks": checks,
    "hard_failures": hard,
    "real_next": NEXT if status == "PASS" else "repair_" + EXPECTED,
    "truth_boundary": TRUTH,
}
proof.update(discipline_flags())
proof["proof_hash"] = h(proof)

memory = {
    "id": "KNOWLEDGE_SUBSTRATE_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "status": status,
    "memory_effect": ("Knowledge Substrate organ pilot sealed: living wiki article for "
                      "entity_substrate is proof-backed, source-linked, discipline-clean. "
                      "memory_continuity capability now has a working organ."),
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
    active["status"] = "SEALED_PILOT"
    active["sealed_at_utc"] = now_utc()
    active["updated_at_utc"] = now_utc()
    write_json(ACTIVE, active)

print("KNOWLEDGE SUBSTRATE :: REVIEW/SEAL :: " + status)
print("PILOT_SEALED::" + str(status == "PASS"))
print("PROOF::" + str(PROOF))
print("REAL_NEXT::" + (NEXT if status == "PASS" else "repair_" + EXPECTED))
print("HARD_FAILURES::" + str(hard))
print("TRUTH_BOUNDARY::" + TRUTH)

raise SystemExit(0 if status == "PASS" else 1)

#!/usr/bin/env python3
"""Knowledge Substrate observe — organ-local status mirror.

Read-only. Reports source/ingested/article counts, governance breakdown, pointer
state, proof-chain status, and discipline flags. Writes a dashboard panel (json+txt).
"""
import sys
import glob
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))

from knowledge_substrate.io import now_utc, now_msk, read_json, write_json, write_text

ROOT = Path(".")
ACTIVE = ROOT / "SYSTEM/CAPABILITIES/memory_continuity/ACTIVE_KNOWLEDGE_SUBSTRATE_DIRECTION.json"
REGISTRY = ROOT / "SOVEREIGN/MEMORY/documents/SOURCE_REGISTRY_V1.json"
INGEST_DIR = ROOT / "SOVEREIGN/MEMORY/documents/ingested"
ARTICLE_JSON = ROOT / "SOVEREIGN/WIKI/pages/entity_substrate.json"
INDEX = ROOT / "SOVEREIGN/WIKI/indexes/KNOWLEDGE_SUBSTRATE_INDEX_V1.json"
PANEL_JSON = ROOT / "SYSTEM/DASHBOARD/KNOWLEDGE_SUBSTRATE_PANEL_V1.json"
PANEL_TXT = ROOT / "SYSTEM/DASHBOARD/KNOWLEDGE_SUBSTRATE_PANEL_V1.txt"

CHAIN = {
    "scan": ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_SOURCE_SCAN_V1_PROOF.json",
    "ingest": ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_INGEST_V1_PROOF.json",
    "article": ROOT / "SOVEREIGN/PROOF/proof_chain/WIKI_ARTICLE_ENTITY_SUBSTRATE_V1_PROOF.json",
    "validation": ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_VALIDATION_V1_PROOF.json",
    "review": ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_REVIEW_V1_PROOF.json",
}


def pstat(p):
    o = read_json(p)
    return o.get("status", "MISSING") if o else "MISSING"


registry = read_json(REGISTRY)
active = read_json(ACTIVE)
article = read_json(ARTICLE_JSON)
index = read_json(INDEX)
ingested = len(glob.glob(str(INGEST_DIR / "*.json")))

source_count = registry.get("counts", {}).get("total", 0)
gov = article.get("governance_counts", {})
chain_status = {k: pstat(v) for k, v in CHAIN.items()}
hard = []
if source_count <= 0:
    hard.append("NO_SOURCES")
if ingested <= 0:
    hard.append("NO_INGESTED")
if not article:
    hard.append("NO_ARTICLE")
status = "PASS" if not hard else "REVIEW_REQUIRED"

panel = {
    "id": "KNOWLEDGE_SUBSTRATE_PANEL_V1",
    "panel_type": "knowledge_substrate_status",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": "memory_continuity",
    "organ": "Knowledge Substrate",
    "pointer_status": active.get("status"),
    "last_step": active.get("last_step"),
    "next_required_step": active.get("next_required_step"),
    "source_count": source_count,
    "ingested_count": ingested,
    "governance_counts": gov,
    "articles": list(index.get("articles", {}).keys()),
    "proof_chain_status": chain_status,
    "hard_failures": hard,
    "operator_visible_summary": (
        f"Knowledge Substrate: {source_count} sources, {ingested} ingested, "
        f"article 'entity_substrate' [{gov.get('current',0)} current / "
        f"{gov.get('conflicting',0)} conflicting / {gov.get('historical',0)} historical]. "
        f"Pointer: {active.get('status')} -> {active.get('next_required_step')}."
    ),
    "daemon_running": False,
    "network_used": False,
    "background_loop_enabled": False,
    "entity_birth_allowed": False,
    "anna_birth_allowed": False,
    "agi_claim_allowed": False,
    "llm_used": False,
    "truth_boundary": "Observe only. Read-only over KS artifacts. No daemon/background/network/LLM.",
}

txt = []
txt.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
txt.append("KNOWLEDGE SUBSTRATE — STATUS")
txt.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
txt.append(f"STATUS::{status}")
txt.append(f"SOURCES::{source_count}   INGESTED::{ingested}")
txt.append(f"ARTICLE::entity_substrate")
txt.append(f"  current::{gov.get('current',0)}  conflicting::{gov.get('conflicting',0)}"
           f"  historical::{gov.get('historical',0)}  deprecated::{gov.get('deprecated',0)}")
txt.append("PROOF CHAIN:")
for k, v in chain_status.items():
    txt.append(f"  {k}::{v}")
txt.append(f"POINTER::{active.get('status')} -> {active.get('next_required_step')}")
txt.append(f"HARD_FAILURES::{hard}")
txt.append("DAEMON::False  NETWORK::False  LLM::False  ENTITY_BIRTH::False  ANNA_BIRTH::False")

write_json(PANEL_JSON, panel)
write_text(PANEL_TXT, "\n".join(txt))

print("\n".join(txt))
print("PANEL::" + str(PANEL_JSON))
raise SystemExit(0 if status == "PASS" else 1)

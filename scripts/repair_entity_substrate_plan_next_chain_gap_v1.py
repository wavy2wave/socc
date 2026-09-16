#!/usr/bin/env python3
"""
Repair: ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1.next_chain gap.

The construction plan's next_chain jumps build_surface -> run_session, omitting
review_entity_substrate_bounded_execution_surface_v1 and
accept_entity_substrate_bounded_execution_surface_v1. That violates the mandatory
gate review_accept_before_execution. The authoritative ordering is the
direction.future_frontiers. This repair inserts the two missing steps into the
plan's next_chain so the canon is self-consistent.

Data hygiene only: it does NOT touch route authority, run a session, execute, or
birth anything. Backs up the plan and writes a proof (no fake pass).
"""
import json, hashlib, shutil
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(".")
PLAN = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1.json"
DIRECTION = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.json"
PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/SOCC_REPAIR_ENTITY_SUBSTRATE_PLAN_NEXT_CHAIN_GAP_V1_PROOF.json"
BACKUP = ROOT / "SYSTEM/ENTITY_SUBSTRATE/plan_next_chain_backups"

BUILD = "build_entity_substrate_bounded_execution_surface_v1"
REVIEW = "review_entity_substrate_bounded_execution_surface_v1"
ACCEPT = "accept_entity_substrate_bounded_execution_surface_v1"
RUN = "run_entity_substrate_bounded_execution_session_v1"


def now(): return datetime.now(timezone.utc).isoformat()
def rj(p): return json.loads(p.read_text(encoding="utf-8"))
def wj(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
def h16(o): return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]

plan = rj(PLAN)
direction = rj(DIRECTION)
chain = list(plan.get("next_chain", []))
dir_ff = direction.get("future_frontiers", [])
before = list(chain)

checks = {
    "plan_exists": PLAN.exists(),
    "direction_has_review_then_accept": (
        REVIEW in dir_ff and ACCEPT in dir_ff
        and dir_ff.index(REVIEW) < dir_ff.index(ACCEPT)),
    "review_accept_before_execution_mandated":
        direction.get("mandatory_gates", {}).get("review_accept_before_execution") is True,
    "build_in_chain": BUILD in chain,
}
hard = [k for k, v in checks.items() if v is not True]

changed = False
if not hard and BUILD in chain:
    i = chain.index(BUILD)
    # idempotent: only insert the ones that are missing, in correct order
    insert = [s for s in (REVIEW, ACCEPT) if s not in chain]
    if insert:
        chain[i + 1:i + 1] = insert
        changed = True

checks["chain_now_has_review"] = REVIEW in chain
checks["chain_now_has_accept"] = ACCEPT in chain
checks["order_build_review_accept_run"] = (
    all(s in chain for s in (BUILD, REVIEW, ACCEPT, RUN))
    and chain.index(BUILD) < chain.index(REVIEW) < chain.index(ACCEPT) < chain.index(RUN)
)
hard = [k for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

backup_path = None
if status == "PASS" and changed:
    snap = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    BACKUP.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP / f"{snap}_ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1.json"
    shutil.copy2(PLAN, backup_path)
    plan["next_chain"] = chain
    plan["next_chain_repaired_utc"] = now()
    plan["next_chain_repair_note"] = (
        "Inserted review/accept of bounded execution surface to satisfy mandatory "
        "gate review_accept_before_execution, per direction.future_frontiers.")
    wj(PLAN, plan)

proof = {
    "id": "SOCC_REPAIR_ENTITY_SUBSTRATE_PLAN_NEXT_CHAIN_GAP_V1_PROOF",
    "created_at_utc": now(), "status": status,
    "capability": ("SOCC_REPAIRED_ENTITY_SUBSTRATE_PLAN_NEXT_CHAIN_REVIEW_ACCEPT_BEFORE_EXECUTION"
                   if status == "PASS" else "ENTITY_SUBSTRATE_PLAN_NEXT_CHAIN_REPAIR_BLOCKED"),
    "changed": changed,
    "next_chain_before": before,
    "next_chain_after": chain,
    "authoritative_source": "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.json#future_frontiers",
    "checks": checks, "hard_failures": hard,
    "backup": str(backup_path) if backup_path else None,
    "route_authority_touched": False, "no_execution": True, "no_session_run": True,
    "no_entity_birth": True, "no_daemon": True, "no_background": True, "no_network": True,
    "truth_boundary": "Plan next_chain data-hygiene repair only. No route change, no execution, no birth.",
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)

print("REPAIR_PLAN_NEXT_CHAIN_GAP::" + status)
print("CHANGED::" + str(changed))
print("ORDER::" + " -> ".join(s for s in chain if s in (BUILD, REVIEW, ACCEPT, RUN)))
print("PROOF::" + str(PROOF))
if hard: raise SystemExit(1)

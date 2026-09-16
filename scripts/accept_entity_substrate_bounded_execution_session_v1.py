#!/usr/bin/env python3
"""
Entity/Substrate — Accept Bounded Execution Session V1.

Lawful chain position:
    ... review_entity_substrate_bounded_execution_session_v1
        -> accept_entity_substrate_bounded_execution_session_v1   (here)
        -> seal_entity_substrate_v1 ...

Accepts the reviewed+validated bounded session and AUTHORIZES the seal step as the next
lawful action. It does NOT seal, does NOT birth Entity/Anna, runs nothing. Seal remains a
separate, explicit step (it is the milestone that later unlocks the ANNA MVP line).

No fake pass: checks from real file state. Transition (accept -> seal) via the ENFORCED
atomic-commit helper, then observe mirrors synced.
"""
import json, hashlib, shutil, importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
CURRENT = "accept_entity_substrate_bounded_execution_session_v1"
NEXT = "seal_entity_substrate_v1"

PC = ROOT / "SOVEREIGN/PROOF/proof_chain"
ES = ROOT / "SYSTEM/ENTITY_SUBSTRATE"
RUN_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json"
VALIDATE_PROOF = PC / "SOCC_VALIDATE_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json"
REVIEW_PROOF = PC / "SOCC_REVIEW_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json"
DIRECTION = ES / "ENTITY_SUBSTRATE_DIRECTION_V1.json"

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"

ACCEPT_DOC = ES / "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_ACCEPTANCE_V1.json"
ACTIVE = ES / "ACTIVE_ACCEPTED_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION.json"
PROOF = PC / "SOCC_ACCEPT_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_SESSION_ACCEPTANCE_MEMORY_V1.json"
PANEL_OUT = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_SESSION_ACCEPTED_PANEL_V1.json"
BACKUP_ROOT = ROOT / "core/socc/route_authority/self_construction_autonomy/session_accept_backups"

TRUTH_BOUNDARY = (
    "Entity/Substrate bounded execution session acceptance only. Accepts the reviewed+"
    "validated session and authorizes the seal step as the next lawful action. Does NOT "
    "seal, does NOT birth Entity/Anna, runs nothing, no daemon/background/network, no "
    "AGI/L3 claim. Seal stays a separate explicit step.")


def now_utc(): return datetime.now(timezone.utc).isoformat()
def now_msk(): return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")
def rj(p):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}
def wj(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
def h16(o): return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
def load_enforcer():
    spec = importlib.util.spec_from_file_location("socc_self_building_atomic_commit_enforcer_v1", ENFORCER)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def get_next(o):
    if not isinstance(o, dict): return None
    for k in ["current_lawful_next", "lawful_next", "next", "route_next", "current_next"]:
        if isinstance(o.get(k), str): return o[k]
    return None
def proof_next(o):
    for k in ["next_after_pass", "next_lawful_step", "next_required_step"]:
        if isinstance(o.get(k), str): return o[k]
    return None


run = rj(RUN_PROOF); val = rj(VALIDATE_PROOF); rev = rj(REVIEW_PROOF); direction = rj(DIRECTION)
dir_frontiers = direction.get("future_frontiers", []) or []
authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})
ts = now_utc()

presence = {
    "run_proof_exists": RUN_PROOF.exists(), "validate_proof_exists": VALIDATE_PROOF.exists(),
    "review_proof_exists": REVIEW_PROOF.exists(), "direction_exists": DIRECTION.exists(),
    "enforcer_exists": ENFORCER.exists(),
}
accept_checks = {
    "run_proof_pass": run.get("status") == "PASS",
    "validate_proof_pass": val.get("status") == "PASS",
    "review_proof_pass": rev.get("status") == "PASS",
    "review_next_matches_current": proof_next(rev) == CURRENT,
    "run_one_tick": run.get("ticks_run") == 1,
    "authority_at_current": authority_nexts == [CURRENT],
    "seal_is_next_in_direction": (
        dir_frontiers[dir_frontiers.index(CURRENT) + 1] == NEXT
        if CURRENT in dir_frontiers and dir_frontiers.index(CURRENT) + 1 < len(dir_frontiers) else False),
    "authorizes_seal_only_not_seal_itself": True,
}
safety = {"no_seal_now": True, "no_entity_birth": True, "no_anna_birth": True, "no_daemon": True,
          "no_background": True, "no_network": True, "no_old_route_resume": True, "no_mw_route": True,
          "no_agi_claim": True, "no_l3_claim": True, "no_build_execution": True, "no_session_run": True}
checks = {**presence, **accept_checks, **safety, "accept_checks_all_true": all(accept_checks.values())}
hard = [k for k, v in checks.items() if v is not True]
commit_result = None; backup_dir = None
status = "PASS" if not hard else "FAIL"

wj(ACCEPT_DOC, {
    "id": "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_ACCEPTANCE_V1", "created_at_utc": ts, "status": status,
    "verdict": ("ENTITY_SUBSTRATE_BOUNDED_SESSION_ACCEPTED_AUTHORIZES_SEAL"
                if status == "PASS" else "ENTITY_SUBSTRATE_BOUNDED_SESSION_ACCEPTANCE_BLOCKED"),
    "run_proof": str(RUN_PROOF), "validate_proof": str(VALIDATE_PROOF), "review_proof": str(REVIEW_PROOF),
    "authorizes_next": NEXT, "checks": checks, "hard_failures": hard,
    "entity_born": False, "anna_born": False, "truth_boundary": TRUTH_BOUNDARY,
})
if status == "PASS":
    wj(ACTIVE, {
        "id": "ACTIVE_ACCEPTED_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION", "created_at_utc": ts,
        "acceptance": str(ACCEPT_DOC), "authorizes_next": NEXT,
        "authorization_scope": "authorizes_seal_step_only_no_birth", "truth_boundary": TRUTH_BOUNDARY,
    })

if status == "PASS":
    snap = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = BACKUP_ROOT / snap; backup_dir.mkdir(parents=True, exist_ok=True)
    for p in AUTHORITY_FILES:
        if p.exists(): shutil.copy2(p, backup_dir / p.name)
    enforcer = load_enforcer()
    commit_result = enforcer.enforce_atomic_commit_transition(
        lawful_next=NEXT, upstream_proof=str(PROOF), truth_boundary=TRUTH_BOUNDARY,
        route_updates={"current_lawful_next": NEXT,
                       "current_lawful_next_source": "entity_substrate_session_acceptance_pass",
                       "recommended_next_target": NEXT, "entity_substrate_session_accepted": True},
        reason="entity_substrate_session_acceptance_pass_authorizes_seal")
    if not (isinstance(commit_result, dict) and commit_result.get("status") == "PASS"):
        hard.append("ATOMIC_COMMIT_NOT_PASS"); status = "FAIL"

if status == "PASS":
    route_hash = rj(ROUTE).get("route_hash")
    guard = {"daemon_running": False, "continuous_loop_enabled": False, "background_loop_enabled": False,
             "scheduler_installed": False, "network_used": False, "queue_widening_allowed": False,
             "entity_birth_allowed": False, "anna_birth_allowed": False, "agi_claim_allowed": False}
    pulse = rj(AUTONOMY_PULSE)
    pulse.update({"updated_at_utc": now_utc(), "status": "PASS", "current_lawful_next": NEXT,
                  "lawful_next": NEXT, "real_next": NEXT,
                  "current_lawful_next_source": "entity_substrate_session_acceptance_pass",
                  "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY", "route_hash_ref": route_hash,
                  "entity_substrate_session_accepted": True}); pulse.update(guard)
    wj(AUTONOMY_PULSE, pulse)
    control = rj(CONTROL_PANEL)
    control.update({"updated_at_utc": now_utc(), "status": "PASS", "current_lawful_next": NEXT,
                    "lawful_next": NEXT, "real_next": NEXT, "CONTROL_NEXT": NEXT,
                    "route_hash_ref": route_hash, "entity_substrate_session_accepted": True})
    if isinstance(control.get("operator_view"), dict):
        control["operator_view"]["current_lawful_next"] = NEXT
    control.update(guard); wj(CONTROL_PANEL, control)

proof = {
    "id": "SOCC_ACCEPT_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF",
    "created_at_utc": ts, "created_at_msk": now_msk(), "status": status,
    "capability": ("SOCC_HAS_ACCEPTED_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_AUTHORIZES_SEAL"
                   if status == "PASS" else "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_ACCEPTANCE_BLOCKED"),
    "current_expected": CURRENT,
    "next_after_pass": NEXT if status == "PASS" else None,
    "next_lawful_step": NEXT if status == "PASS" else "manual_session_acceptance_repair_required",
    "acceptance": str(ACCEPT_DOC), "active_accepted": str(ACTIVE) if status == "PASS" else None,
    "run_proof": str(RUN_PROOF), "validate_proof": str(VALIDATE_PROOF), "review_proof": str(REVIEW_PROOF),
    "checks": checks, "accept_checks": accept_checks, "hard_failures": hard, "warnings": [],
    "atomic_commit_result": commit_result, "backup_dir": str(backup_dir) if backup_dir else None,
    "stopped_after_step": True, "sealed": False, "entity_born": False, "anna_born": False,
    "no_seal_now": True, "no_entity_birth": True, "no_anna_birth": True, "no_daemon": True,
    "no_background": True, "no_network": True, "no_old_route_resume": True, "no_mw_route": True,
    "no_agi_claim": True, "no_l3_claim": True, "final_canon_approval_allowed": False,
    "truth_boundary": TRUTH_BOUNDARY,
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)

wj(MEMORY, {
    "id": "ENTITY_SUBSTRATE_SESSION_ACCEPTANCE_MEMORY_V1", "created_at_utc": ts, "status": "RECORDED",
    "event": ("Bounded session accepted; seal authorized as the next lawful step; no birth, not sealed."
              if status == "PASS" else "Session acceptance blocked; hard failures recorded."),
    "acceptance_status": status, "hard_failures": hard, "proof": str(PROOF),
    "next": NEXT if status == "PASS" else "manual_session_acceptance_repair_required",
    "stopped_after_step": True, "truth_boundary": TRUTH_BOUNDARY,
})
wj(PANEL_OUT, {
    "id": "ENTITY_SUBSTRATE_SESSION_ACCEPTED_PANEL_V1", "created_at_utc": ts, "status": status,
    "stage": "entity_substrate_session_accepted", "current": CURRENT,
    "next": NEXT if status == "PASS" else "manual_session_acceptance_repair_required",
    "sealed": False, "proof": str(PROOF), "hard_failures": hard,
    "entity_born": False, "anna_born": False, "truth_boundary": TRUTH_BOUNDARY,
})

print("ENTITY/SUBSTRATE SESSION ACCEPTANCE V1")
print("STATUS::" + status)
print("NEXT::" + (NEXT if status == "PASS" else "manual_session_acceptance_repair_required"))
print("SEALED::False   ENTITY_BORN::False   ANNA_BORN::False")
print("HARD_FAILURES::" + str(hard))
print("PROOF::" + str(PROOF))
if hard:
    raise SystemExit(1)

#!/usr/bin/env python3
"""
Entity/Substrate — Review Bounded Execution Session V1.

Lawful chain position:
    ... validate_entity_substrate_bounded_execution_session_v1
        -> review_entity_substrate_bounded_execution_session_v1   (here)
        -> accept_entity_substrate_bounded_execution_session_v1 ...

Reviews the validated bounded session and confirms it is ready for acceptance:
run proof PASS, validation proof PASS, ten surfaces + panel present and non-empty,
no birth, one tick. Reviews only — runs nothing, builds nothing, births nothing.

No fake pass: checks from real file state. Transition (review -> accept) via the
ENFORCED atomic-commit helper, then observe mirrors synced.
"""
import json, hashlib, shutil, importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
CURRENT = "review_entity_substrate_bounded_execution_session_v1"
NEXT = "accept_entity_substrate_bounded_execution_session_v1"

PC = ROOT / "SOVEREIGN/PROOF/proof_chain"
ES = ROOT / "SYSTEM/ENTITY_SUBSTRATE"
RUNTIME = ES / "runtime"
RUN_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json"
VALIDATE_PROOF = PC / "SOCC_VALIDATE_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json"
DIRECTION = ES / "ENTITY_SUBSTRATE_DIRECTION_V1.json"
SURFACE_FILES = [RUNTIME / f for f in [
    "ENTITY_IDENTITY_SURFACE_V1.json", "ENTITY_STATE_SURFACE_V1.json", "ENTITY_MEMORY_SURFACE_V1.json",
    "ENTITY_LINEAGE_SURFACE_V1.json", "ENTITY_CAPABILITY_BINDING_SURFACE_V1.json",
    "ENTITY_LAWFUL_ACTION_SURFACE_V1.json", "ENTITY_DASHBOARD_SURFACE_V1.json",
    "ENTITY_PROOF_CHAIN_SURFACE_V1.json", "ENTITY_FREEZE_REVIEW_STOP_SURFACE_V1.json",
    "ENTITY_PRODUCT_BINDING_SURFACE_FOR_ANNA_MVP_V1.json"]]

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"

REVIEW_DOC = ES / "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_REVIEW_V1.json"
PROOF = PC / "SOCC_REVIEW_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_SESSION_REVIEW_MEMORY_V1.json"
PANEL_OUT = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_SESSION_REVIEWED_PANEL_V1.json"
BACKUP_ROOT = ROOT / "core/socc/route_authority/self_construction_autonomy/session_review_backups"

TRUTH_BOUNDARY = (
    "Entity/Substrate bounded execution session review only. Confirms the validated "
    "session is ready for acceptance. Reviews only: runs nothing, builds nothing, "
    "births no Entity/Anna, no daemon/background/network, no AGI/L3 claim.")


def now_utc(): return datetime.now(timezone.utc).isoformat()
def now_msk(): return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")
def rj(p):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}
def nonempty(p):
    d = rj(p); return isinstance(d, dict) and len(d) > 0
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


run = rj(RUN_PROOF); val = rj(VALIDATE_PROOF); direction = rj(DIRECTION)
dir_frontiers = direction.get("future_frontiers", []) or []
authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})
ts = now_utc()

presence = {
    "run_proof_exists": RUN_PROOF.exists(), "validate_proof_exists": VALIDATE_PROOF.exists(),
    "direction_exists": DIRECTION.exists(), "enforcer_exists": ENFORCER.exists(),
    "all_ten_surfaces_exist": all(p.exists() for p in SURFACE_FILES),
}
review_checks = {
    "run_proof_pass": run.get("status") == "PASS",
    "validate_proof_pass": val.get("status") == "PASS",
    "validate_next_matches_current": proof_next(val) == CURRENT,
    "run_one_tick": run.get("ticks_run") == 1,
    "ten_surfaces_nonempty": all(nonempty(p) for p in SURFACE_FILES),
    "all_surfaces_declare_no_birth": all(
        rj(p).get("entity_born") is False and rj(p).get("anna_born") is False for p in SURFACE_FILES),
    "authority_at_current": authority_nexts == [CURRENT],
    "accept_is_next_in_direction": (
        dir_frontiers[dir_frontiers.index(CURRENT) + 1] == NEXT
        if CURRENT in dir_frontiers and dir_frontiers.index(CURRENT) + 1 < len(dir_frontiers) else False),
}
safety = {"no_entity_birth": True, "no_anna_birth": True, "no_daemon": True, "no_background": True,
          "no_network": True, "no_old_route_resume": True, "no_mw_route": True,
          "no_agi_claim": True, "no_l3_claim": True, "no_build_execution": True, "no_session_run": True}
checks = {**presence, **review_checks, **safety, "review_checks_all_true": all(review_checks.values())}
hard = [k for k, v in checks.items() if v is not True]
commit_result = None; backup_dir = None
status = "PASS" if not hard else "FAIL"

wj(REVIEW_DOC, {
    "id": "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_REVIEW_V1", "created_at_utc": ts, "status": status,
    "verdict": ("ENTITY_SUBSTRATE_BOUNDED_SESSION_REVIEWED_READY_FOR_ACCEPTANCE"
                if status == "PASS" else "ENTITY_SUBSTRATE_BOUNDED_SESSION_REVIEW_BLOCKED"),
    "run_proof": str(RUN_PROOF), "validate_proof": str(VALIDATE_PROOF),
    "checks": checks, "hard_failures": hard,
    "entity_born": False, "anna_born": False, "truth_boundary": TRUTH_BOUNDARY,
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
                       "current_lawful_next_source": "entity_substrate_session_review_pass",
                       "recommended_next_target": NEXT, "entity_substrate_session_reviewed": True},
        reason="entity_substrate_session_review_pass_advance_to_accept")
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
                  "current_lawful_next_source": "entity_substrate_session_review_pass",
                  "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY", "route_hash_ref": route_hash,
                  "entity_substrate_session_reviewed": True}); pulse.update(guard)
    wj(AUTONOMY_PULSE, pulse)
    control = rj(CONTROL_PANEL)
    control.update({"updated_at_utc": now_utc(), "status": "PASS", "current_lawful_next": NEXT,
                    "lawful_next": NEXT, "real_next": NEXT, "CONTROL_NEXT": NEXT,
                    "route_hash_ref": route_hash, "entity_substrate_session_reviewed": True})
    if isinstance(control.get("operator_view"), dict):
        control["operator_view"]["current_lawful_next"] = NEXT
    control.update(guard); wj(CONTROL_PANEL, control)

proof = {
    "id": "SOCC_REVIEW_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF",
    "created_at_utc": ts, "created_at_msk": now_msk(), "status": status,
    "capability": ("SOCC_HAS_REVIEWED_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_READY_FOR_ACCEPTANCE"
                   if status == "PASS" else "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_REVIEW_BLOCKED"),
    "current_expected": CURRENT,
    "next_after_pass": NEXT if status == "PASS" else None,
    "next_lawful_step": NEXT if status == "PASS" else "manual_session_review_repair_required",
    "review": str(REVIEW_DOC), "run_proof": str(RUN_PROOF), "validate_proof": str(VALIDATE_PROOF),
    "checks": checks, "review_checks": review_checks, "hard_failures": hard, "warnings": [],
    "atomic_commit_result": commit_result, "backup_dir": str(backup_dir) if backup_dir else None,
    "stopped_after_step": True, "entity_born": False, "anna_born": False,
    "no_entity_birth": True, "no_anna_birth": True, "no_daemon": True, "no_background": True,
    "no_network": True, "no_old_route_resume": True, "no_mw_route": True,
    "no_agi_claim": True, "no_l3_claim": True, "no_build_execution": True, "no_session_run": True,
    "final_canon_approval_allowed": False, "truth_boundary": TRUTH_BOUNDARY,
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)

wj(MEMORY, {
    "id": "ENTITY_SUBSTRATE_SESSION_REVIEW_MEMORY_V1", "created_at_utc": ts, "status": "RECORDED",
    "event": ("Bounded session reviewed: validated session confirmed ready for acceptance; "
              "no birth; advanced to accept." if status == "PASS"
              else "Session review blocked; hard failures recorded."),
    "review_status": status, "hard_failures": hard, "proof": str(PROOF),
    "next": NEXT if status == "PASS" else "manual_session_review_repair_required",
    "stopped_after_step": True, "truth_boundary": TRUTH_BOUNDARY,
})
wj(PANEL_OUT, {
    "id": "ENTITY_SUBSTRATE_SESSION_REVIEWED_PANEL_V1", "created_at_utc": ts, "status": status,
    "stage": "entity_substrate_session_reviewed", "current": CURRENT,
    "next": NEXT if status == "PASS" else "manual_session_review_repair_required",
    "proof": str(PROOF), "hard_failures": hard,
    "entity_born": False, "anna_born": False, "truth_boundary": TRUTH_BOUNDARY,
})

print("ENTITY/SUBSTRATE SESSION REVIEW V1")
print("STATUS::" + status)
print("NEXT::" + (NEXT if status == "PASS" else "manual_session_review_repair_required"))
print("HARD_FAILURES::" + str(hard))
print("PROOF::" + str(PROOF))
if hard:
    raise SystemExit(1)

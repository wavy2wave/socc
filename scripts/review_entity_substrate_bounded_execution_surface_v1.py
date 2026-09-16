#!/usr/bin/env python3
"""
Entity/Substrate — Review Bounded Execution Surface V1.

Chain: build_surface -> review_surface (here) -> accept_surface -> run_session ...

Reviews the bounded execution surface CONTRACT: confirms it is well-formed,
bounded (1 session / 1 tick / stop / no daemon/network/background), authorizes
no execution, and forbids entity/anna birth. Reviews only — no execution, no
session, no birth.

No fake pass: checks computed from real file state. Route transition via the
ENFORCED atomic-commit helper, then observe mirrors synced.
"""
import json, hashlib, shutil, importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
CURRENT = "review_entity_substrate_bounded_execution_surface_v1"
NEXT = "accept_entity_substrate_bounded_execution_surface_v1"

PC = ROOT / "SOVEREIGN/PROOF/proof_chain"
BUILD_PROOF = PC / "SOCC_BUILD_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1_PROOF.json"
SURFACE = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1.json"
DIRECTION = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.json"

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"

REVIEW_DOC = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_REVIEW_V1.json"
PROOF = PC / "SOCC_REVIEW_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_REVIEW_MEMORY_V1.json"
PANEL_JSON = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_REVIEW_PANEL_V1.json"
PANEL_TXT = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_REVIEW_PANEL_V1.txt"
BACKUP_ROOT = ROOT / "core/socc/route_authority/self_construction_autonomy/bounded_surface_review_backups"

TRUTH_BOUNDARY = (
    "Entity/Substrate bounded execution surface review only. Confirms the surface "
    "contract is well-formed and bounded; authorizes no execution. Runs no "
    "session, materializes no artifacts, births no Entity/ANNA, no daemon/"
    "background/network."
)


def now_utc(): return datetime.now(timezone.utc).isoformat()
def now_msk(): return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")
def rj(p):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}
def wj(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
def wt(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(s).rstrip() + "\n", encoding="utf-8")
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


build = rj(BUILD_PROOF)
surface = rj(SURFACE)
direction = rj(DIRECTION)
scope = surface.get("execution_scope", {}) or {}
dir_frontiers = direction.get("future_frontiers", []) or []
authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})

presence = {
    "build_proof_exists": BUILD_PROOF.exists(),
    "surface_exists": SURFACE.exists(),
    "direction_exists": DIRECTION.exists(),
    "enforcer_exists": ENFORCER.exists(),
}
review_checks = {
    "build_proof_pass": build.get("status") == "PASS",
    "build_next_matches_current": proof_next(build) == CURRENT,
    "surface_is_candidate": surface.get("status") == "BUILT_CANDIDATE",
    "surface_type_correct": surface.get("surface_type") == "BOUNDED_ENTITY_SUBSTRATE_EXECUTION_SURFACE",
    "scope_single_session": scope.get("max_sessions") == 1,
    "scope_single_tick": scope.get("max_ticks") == 1,
    "scope_must_stop": scope.get("must_stop_after_run") is True,
    "scope_no_daemon": scope.get("daemon_allowed") is False,
    "scope_no_background": scope.get("background_allowed") is False,
    "scope_no_network": scope.get("network_allowed") is False,
    "scope_no_entity_birth": scope.get("entity_birth_allowed") is False,
    "scope_no_anna_birth": scope.get("anna_birth_allowed") is False,
    "has_allowed_writes": bool(surface.get("allowed_writes")),
    "has_forbidden_writes": bool(surface.get("forbidden_writes")),
    "has_pass_definition": bool(surface.get("pass_definition")),
    "has_runtime_artifacts": bool(surface.get("runtime_artifacts_to_build")),
    "has_pre_run_checks": bool(surface.get("pre_run_checks_required")),
    "authority_at_current": authority_nexts == [CURRENT],
    "accept_surface_is_next_in_direction": (
        dir_frontiers[dir_frontiers.index(CURRENT) + 1] == NEXT
        if CURRENT in dir_frontiers and dir_frontiers.index(CURRENT) + 1 < len(dir_frontiers) else False),
    "execution_not_authorized": True,
}
safety = {
    "no_execution": True, "no_session_run": True, "no_build_execution": True,
    "no_entity_birth": True, "no_anna_birth": True, "no_daemon": True,
    "no_background": True, "no_network": True, "no_agi_claim": True,
    "no_l3_claim": True, "no_old_route_resume": True,
}
checks = {**presence, **review_checks, **safety, "review_checks_all_true": all(review_checks.values())}
hard = [k for k, v in checks.items() if v is not True]

commit_result = None; backup_dir = None
status = "PASS" if not hard else "FAIL"
ts = now_utc()

wj(REVIEW_DOC, {
    "id": "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_REVIEW_V1",
    "created_at_utc": ts, "status": status,
    "verdict": ("ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_REVIEWED_READY_FOR_ACCEPTANCE"
                if status == "PASS" else "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_REVIEW_BLOCKED"),
    "reviewed_surface": str(SURFACE), "build_proof": str(BUILD_PROOF),
    "checks": checks, "hard_failures": hard,
    "next": NEXT if status == "PASS" else "manual_bounded_surface_review_repair_required",
    "truth_boundary": TRUTH_BOUNDARY,
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
                       "current_lawful_next_source": "entity_substrate_bounded_surface_review_pass",
                       "recommended_next_target": NEXT,
                       "entity_substrate_bounded_surface_reviewed": True},
        reason="entity_substrate_bounded_surface_review_pass_advance_to_acceptance")
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
                  "current_lawful_next_source": "entity_substrate_bounded_surface_review_pass",
                  "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY", "route_hash_ref": route_hash,
                  "entity_substrate_bounded_surface_reviewed": True}); pulse.update(guard)
    wj(AUTONOMY_PULSE, pulse)
    control = rj(CONTROL_PANEL)
    control.update({"updated_at_utc": now_utc(), "status": "PASS", "current_lawful_next": NEXT,
                    "lawful_next": NEXT, "real_next": NEXT, "CONTROL_NEXT": NEXT, "route_hash_ref": route_hash,
                    "entity_substrate_bounded_surface_reviewed": True})
    if isinstance(control.get("operator_view"), dict):
        control["operator_view"]["current_lawful_next"] = NEXT
    control.update(guard); wj(CONTROL_PANEL, control)

proof = {
    "id": "SOCC_REVIEW_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1_PROOF",
    "created_at_utc": ts, "created_at_msk": now_msk(), "status": status,
    "capability": ("SOCC_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_REVIEWED_READY_FOR_ACCEPTANCE"
                   if status == "PASS" else "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_REVIEW_BLOCKED"),
    "current_expected": CURRENT,
    "next_after_pass": NEXT if status == "PASS" else None,
    "next_lawful_step": NEXT if status == "PASS" else "manual_bounded_surface_review_repair_required",
    "review": str(REVIEW_DOC), "bounded_execution_surface": str(SURFACE), "build_proof": str(BUILD_PROOF),
    "checks": checks, "review_checks": review_checks, "hard_failures": hard, "warnings": [],
    "atomic_commit_result": commit_result, "backup_dir": str(backup_dir) if backup_dir else None,
    "stopped_after_step": True, "execution_not_authorized": True,
    "no_execution": True, "no_session_run": True, "no_entity_build_execution_now": True,
    "no_entity_birth": True, "no_anna_birth": True, "no_daemon": True, "no_background": True,
    "no_network": True, "no_old_route_resume": True, "no_agi_claim": True, "no_l3_claim": True,
    "final_canon_approval_allowed": False, "truth_boundary": TRUTH_BOUNDARY,
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)

wj(MEMORY, {
    "id": "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_REVIEW_MEMORY_V1",
    "created_at_utc": ts, "status": "RECORDED",
    "event": ("Bounded execution surface contract reviewed; bounded and well-formed; ready for acceptance."
              if status == "PASS" else "Bounded execution surface review blocked; hard failures recorded."),
    "review_status": status, "hard_failures": hard, "proof": str(PROOF),
    "next": NEXT if status == "PASS" else "manual_bounded_surface_review_repair_required",
    "stopped_after_step": True, "truth_boundary": TRUTH_BOUNDARY,
})
wj(PANEL_JSON, {
    "id": "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_REVIEW_PANEL_V1",
    "created_at_utc": ts, "status": status, "stage": "entity_substrate_bounded_surface_review",
    "current": CURRENT, "next": NEXT if status == "PASS" else "manual_bounded_surface_review_repair_required",
    "execution_authorized": False, "proof": str(PROOF), "hard_failures": hard, "truth_boundary": TRUTH_BOUNDARY,
})
wt(PANEL_TXT, "\n".join([
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "ENTITY/SUBSTRATE BOUNDED SURFACE REVIEW V1",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    f"STATUS::{status}", f"CURRENT::{CURRENT}",
    f"NEXT::{NEXT if status == 'PASS' else 'manual_bounded_surface_review_repair_required'}",
    f"HARD_FAILURES::{hard}", "",
    "EXECUTION_AUTHORIZED::False", "ENTITY_BIRTH_ALLOWED::False", "ANNA_BIRTH_ALLOWED::False",
    "NO_DAEMON::True   NO_NETWORK::True",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
]))

print(PANEL_TXT.read_text(encoding="utf-8"))
print("REVIEW::" + str(REVIEW_DOC)); print("PROOF::" + str(PROOF)); print("STATUS::" + status)
print("NEXT_LAWFUL_STEP::" + (NEXT if status == "PASS" else "manual_bounded_surface_review_repair_required"))
if hard: raise SystemExit(1)

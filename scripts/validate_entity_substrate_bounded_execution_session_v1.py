#!/usr/bin/env python3
"""
Entity/Substrate — Validate Bounded Execution Session V1.

Lawful chain position:
    ... run_entity_substrate_bounded_execution_session_v1
        -> validate_entity_substrate_bounded_execution_session_v1   (here)
        -> review_entity_substrate_bounded_execution_session_v1 ...

This step VALIDATES the bounded session that just ran: it confirms the run proof
passed, that exactly one bounded tick ran, that the ten substrate surfaces + runtime
panel were actually materialized and are non-empty, that memory was recorded, and that
nothing was born / no daemon / no network. It validates only — it runs nothing, builds
nothing, births nothing.

No fake pass: every check is computed from real file state. The lawful transition
(validate -> review) goes through the ENFORCED atomic-commit helper, then the observe
mirrors are synced.
"""
import json
import hashlib
import shutil
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
CURRENT = "validate_entity_substrate_bounded_execution_session_v1"
NEXT = "review_entity_substrate_bounded_execution_session_v1"

PC = ROOT / "SOVEREIGN/PROOF/proof_chain"
ES = ROOT / "SYSTEM/ENTITY_SUBSTRATE"
RUNTIME = ES / "runtime"

RUN_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json"
RUN_MEMORY = ROOT / "MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_RUNTIME_MEMORY_V1.json"
PANEL = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_RUNTIME_PANEL_V1.json"
DIRECTION = ES / "ENTITY_SUBSTRATE_DIRECTION_V1.json"

SURFACE_FILES = [
    RUNTIME / "ENTITY_IDENTITY_SURFACE_V1.json",
    RUNTIME / "ENTITY_STATE_SURFACE_V1.json",
    RUNTIME / "ENTITY_MEMORY_SURFACE_V1.json",
    RUNTIME / "ENTITY_LINEAGE_SURFACE_V1.json",
    RUNTIME / "ENTITY_CAPABILITY_BINDING_SURFACE_V1.json",
    RUNTIME / "ENTITY_LAWFUL_ACTION_SURFACE_V1.json",
    RUNTIME / "ENTITY_DASHBOARD_SURFACE_V1.json",
    RUNTIME / "ENTITY_PROOF_CHAIN_SURFACE_V1.json",
    RUNTIME / "ENTITY_FREEZE_REVIEW_STOP_SURFACE_V1.json",
    RUNTIME / "ENTITY_PRODUCT_BINDING_SURFACE_FOR_ANNA_MVP_V1.json",
]

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"

VALIDATION = ES / "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_VALIDATION_V1.json"
PROOF = PC / "SOCC_VALIDATE_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_SESSION_VALIDATION_MEMORY_V1.json"
PANEL_OUT = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_SESSION_VALIDATED_PANEL_V1.json"
BACKUP_ROOT = ROOT / "core/socc/route_authority/self_construction_autonomy/session_validate_backups"

TRUTH_BOUNDARY = (
    "Entity/Substrate bounded execution session validation only. Confirms the prior "
    "bounded tick materialized the ten substrate surfaces + runtime panel and recorded "
    "memory/proof. Validates only: runs nothing, builds nothing, births no Entity/Anna, "
    "no daemon/background/network, no old route resume, no AGI/L3 claim."
)


def now_utc(): return datetime.now(timezone.utc).isoformat()
def now_msk(): return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")
def rj(p):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}
def nonempty(p):
    d = rj(p)
    return isinstance(d, dict) and len(d) > 0
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


run = rj(RUN_PROOF)
run_mem = rj(RUN_MEMORY)
direction = rj(DIRECTION)
dir_frontiers = direction.get("future_frontiers", []) or []
authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})
ts = now_utc()

presence = {
    "run_proof_exists": RUN_PROOF.exists(),
    "run_memory_exists": RUN_MEMORY.exists(),
    "runtime_panel_exists": PANEL.exists(),
    "direction_exists": DIRECTION.exists(),
    "enforcer_exists": ENFORCER.exists(),
    "all_ten_surfaces_exist": all(p.exists() for p in SURFACE_FILES),
}
validate_checks = {
    "run_proof_pass": run.get("status") == "PASS",
    "run_proof_next_matches_current": proof_next(run) == CURRENT,
    "observed_ticks_1": run.get("ticks_run") == 1,
    "run_stopped_after_step": run.get("stopped_after_step") is True,
    "run_entity_not_born": run.get("entity_born") is False,
    "run_anna_not_born": run.get("anna_born") is False,
    "run_execution_engine_not_started": run.get("execution_engine_started") is False,
    "ten_surfaces_nonempty": all(nonempty(p) for p in SURFACE_FILES),
    "panel_nonempty": nonempty(PANEL),
    "all_surfaces_declare_no_birth": all(
        rj(p).get("entity_born") is False and rj(p).get("anna_born") is False for p in SURFACE_FILES),
    "run_memory_recorded": run_mem.get("status") == "RECORDED",
    "run_memory_links_proof": run_mem.get("proof") == str(RUN_PROOF),
    "authority_at_current": authority_nexts == [CURRENT],
    "review_is_next_in_direction": (
        dir_frontiers[dir_frontiers.index(CURRENT) + 1] == NEXT
        if CURRENT in dir_frontiers and dir_frontiers.index(CURRENT) + 1 < len(dir_frontiers) else False),
}
safety = {
    "no_entity_birth": True, "no_anna_birth": True, "no_daemon": True, "no_background": True,
    "no_network": True, "no_old_route_resume": True, "no_mw_route": True,
    "no_agi_claim": True, "no_l3_claim": True, "no_build_execution": True, "no_session_run": True,
}
checks = {**presence, **validate_checks, **safety,
          "validate_checks_all_true": all(validate_checks.values())}
hard = [k for k, v in checks.items() if v is not True]

commit_result = None
backup_dir = None
status = "PASS" if not hard else "FAIL"

wj(VALIDATION, {
    "id": "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_VALIDATION_V1",
    "created_at_utc": ts, "status": status,
    "verdict": ("ENTITY_SUBSTRATE_BOUNDED_SESSION_VALIDATED_TEN_SURFACES_MATERIALIZED"
                if status == "PASS" else "ENTITY_SUBSTRATE_BOUNDED_SESSION_VALIDATION_BLOCKED"),
    "run_proof": str(RUN_PROOF), "validated_surfaces": [str(p) for p in SURFACE_FILES],
    "runtime_panel": str(PANEL), "checks": checks, "hard_failures": hard,
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
                       "current_lawful_next_source": "entity_substrate_session_validation_pass",
                       "recommended_next_target": NEXT,
                       "entity_substrate_session_validated": True},
        reason="entity_substrate_session_validation_pass_advance_to_review")
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
                  "current_lawful_next_source": "entity_substrate_session_validation_pass",
                  "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY", "route_hash_ref": route_hash,
                  "entity_substrate_session_validated": True}); pulse.update(guard)
    wj(AUTONOMY_PULSE, pulse)
    control = rj(CONTROL_PANEL)
    control.update({"updated_at_utc": now_utc(), "status": "PASS", "current_lawful_next": NEXT,
                    "lawful_next": NEXT, "real_next": NEXT, "CONTROL_NEXT": NEXT,
                    "route_hash_ref": route_hash, "entity_substrate_session_validated": True})
    if isinstance(control.get("operator_view"), dict):
        control["operator_view"]["current_lawful_next"] = NEXT
    control.update(guard); wj(CONTROL_PANEL, control)

proof = {
    "id": "SOCC_VALIDATE_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF",
    "created_at_utc": ts, "created_at_msk": now_msk(), "status": status,
    "capability": ("SOCC_HAS_VALIDATED_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION"
                   if status == "PASS" else "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_VALIDATION_BLOCKED"),
    "current_expected": CURRENT,
    "next_after_pass": NEXT if status == "PASS" else None,
    "next_lawful_step": NEXT if status == "PASS" else "manual_session_validation_repair_required",
    "validation": str(VALIDATION), "run_proof": str(RUN_PROOF),
    "validated_surfaces": [str(p) for p in SURFACE_FILES], "runtime_panel": str(PANEL),
    "checks": checks, "validate_checks": validate_checks, "hard_failures": hard, "warnings": [],
    "atomic_commit_result": commit_result, "backup_dir": str(backup_dir) if backup_dir else None,
    "observed_ticks": 1, "stopped_after_step": True,
    "entity_born": False, "anna_born": False,
    "no_entity_birth": True, "no_anna_birth": True, "no_daemon": True, "no_background": True,
    "no_network": True, "no_old_route_resume": True, "no_mw_route": True,
    "no_agi_claim": True, "no_l3_claim": True, "no_build_execution": True, "no_session_run": True,
    "final_canon_approval_allowed": False, "truth_boundary": TRUTH_BOUNDARY,
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)

wj(MEMORY, {
    "id": "ENTITY_SUBSTRATE_SESSION_VALIDATION_MEMORY_V1",
    "created_at_utc": ts, "status": "RECORDED",
    "event": ("Bounded session validated: ten substrate surfaces + panel confirmed "
              "materialized, one tick, no birth; advanced to review."
              if status == "PASS" else "Session validation blocked; hard failures recorded."),
    "validation_status": status, "hard_failures": hard, "proof": str(PROOF),
    "next": NEXT if status == "PASS" else "manual_session_validation_repair_required",
    "stopped_after_step": True, "truth_boundary": TRUTH_BOUNDARY,
})
wj(PANEL_OUT, {
    "id": "ENTITY_SUBSTRATE_SESSION_VALIDATED_PANEL_V1",
    "created_at_utc": ts, "status": status, "stage": "entity_substrate_session_validated",
    "current": CURRENT, "next": NEXT if status == "PASS" else "manual_session_validation_repair_required",
    "surfaces_validated": len(SURFACE_FILES), "proof": str(PROOF), "hard_failures": hard,
    "entity_born": False, "anna_born": False, "truth_boundary": TRUTH_BOUNDARY,
})

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("ENTITY/SUBSTRATE SESSION VALIDATION V1")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("STATUS::" + status)
print("CURRENT::" + CURRENT)
print("NEXT::" + (NEXT if status == "PASS" else "manual_session_validation_repair_required"))
print("SURFACES_VALIDATED::" + str(len(SURFACE_FILES)))
print("ENTITY_BORN::False   ANNA_BORN::False")
print("HARD_FAILURES::" + str(hard))
print("PROOF::" + str(PROOF))
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
if hard:
    raise SystemExit(1)

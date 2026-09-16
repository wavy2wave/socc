#!/usr/bin/env python3
"""
Entity/Substrate — Run Bounded Execution Session V1 (the first real execution).

Lawful chain position:
    ... accept_entity_substrate_bounded_execution_surface_v1
        -> run_entity_substrate_bounded_execution_session_v1   (here)
        -> validate_entity_substrate_bounded_execution_session_v1 ...

This is the FIRST step in the whole Entity/Substrate chain that actually executes:
it runs exactly ONE bounded foreground tick and materializes the ten Entity/Substrate
surfaces (plus the operator runtime panel) as DECLARATIVE substrate artifacts.

It does NOT birth an Entity, does NOT birth Anna, runs no daemon/background/network,
and stops after the single tick. The surfaces are data scaffolding (entity_born=False,
anna_born=False); they prepare the substrate. Birth stays locked until seal.

No fake pass: every precondition is computed from real file state, and after the tick
the runner verifies every required artifact actually exists on disk before it is allowed
to report PASS. Any false check becomes a hard_failure -> FAIL, and the route is not moved.
The lawful route transition (run -> validate) goes through the ENFORCED atomic-commit
helper, then the two observe mirrors (AUTONOMY_PULSE, CONTROL_PANEL) are synced — the same
pattern as the build/accept runners.
"""
import json
import hashlib
import shutil
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
CURRENT = "run_entity_substrate_bounded_execution_session_v1"
NEXT = "validate_entity_substrate_bounded_execution_session_v1"

PC = ROOT / "SOVEREIGN/PROOF/proof_chain"
ES = ROOT / "SYSTEM/ENTITY_SUBSTRATE"
RUNTIME = ES / "runtime"

# ── Inputs (upstream proofs / contract) ─────────────────────────────────
SCIENTIFIC_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_SCIENTIFIC_QUALITY_GATE_V1_PROOF.json"
HERMES_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_HERMES_GATE_V1_PROOF.json"
CODEX_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_CODEX_GATE_V1_PROOF.json"
PLAN_AND_GATES_ACCEPT = PC / "SOCC_ACCEPT_ENTITY_SUBSTRATE_PLAN_AND_GATES_V1_PROOF.json"
ACCEPT_SURFACE_PROOF = PC / "SOCC_ACCEPT_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1_PROOF.json"
SURFACE = ES / "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1.json"
ACTIVE_ACCEPTED = ES / "ACTIVE_ACCEPTED_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE.json"
DIRECTION = ES / "ENTITY_SUBSTRATE_DIRECTION_V1.json"

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"

# ── Outputs ─────────────────────────────────────────────────────────────
PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_RUNTIME_MEMORY_V1.json"
AUDIT = ROOT / "MIGRATION/audits/SOCC_RUN_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1.json"
PANEL = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_RUNTIME_PANEL_V1.json"
BACKUP_ROOT = ROOT / "core/socc/route_authority/self_construction_autonomy/run_session_backups"

TRUTH_BOUNDARY = (
    "Entity/Substrate bounded execution session only. Runs exactly one bounded "
    "foreground tick that materializes the ten substrate surfaces + runtime panel as "
    "declarative data artifacts. Births no Entity, births no Anna, runs no daemon/"
    "background/network/scheduler, does not widen the queue, does not resume the old "
    "route, does not approve final canon, and does not claim AGI/L3. Stops after one tick."
)


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")


def rj(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def wj(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def h16(o):
    return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def load_enforcer():
    spec = importlib.util.spec_from_file_location("socc_self_building_atomic_commit_enforcer_v1", ENFORCER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def get_next(o):
    if not isinstance(o, dict):
        return None
    for k in ["current_lawful_next", "lawful_next", "next", "route_next", "current_next"]:
        if isinstance(o.get(k), str):
            return o[k]
    return None


def proof_next(o):
    for k in ["next_after_pass", "next_lawful_step", "next_required_step"]:
        if isinstance(o.get(k), str):
            return o[k]
    return None


# ── Read state ──────────────────────────────────────────────────────────
sci = rj(SCIENTIFIC_PROOF)
her = rj(HERMES_PROOF)
cod = rj(CODEX_PROOF)
pga = rj(PLAN_AND_GATES_ACCEPT)
accs = rj(ACCEPT_SURFACE_PROOF)
surface = rj(SURFACE)
direction = rj(DIRECTION)
scope = surface.get("execution_scope", {}) or {}
dir_frontiers = direction.get("future_frontiers", []) or []
authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})

SESSION_ID = "ENTITY_SUBSTRATE_BOUNDED_SESSION_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
ts = now_utc()

# ── The ten substrate surfaces + the operator panel (from the contract) ──
# Each surface is a declarative data scaffold. entity_born / anna_born are
# explicitly False — nothing is instantiated; the substrate is only prepared.
SURFACE_DEFS = [
    ("entity_identity_surface", RUNTIME / "ENTITY_IDENTITY_SURFACE_V1.json",
     {"declares": "identity schema for a future bounded entity",
      "entity_name_bound": False, "identity_instantiated": False}),
    ("entity_state_surface", RUNTIME / "ENTITY_STATE_SURFACE_V1.json",
     {"declares": "state-vector schema", "lifecycle": "substrate_prepared_not_running",
      "tick_count": 0, "running": False}),
    ("entity_memory_surface", RUNTIME / "ENTITY_MEMORY_SURFACE_V1.json",
     {"declares": "memory binding contract", "memory_root_pointer": "MEMORY_WAVE/",
      "live_memory_attached": False}),
    ("entity_lineage_surface", RUNTIME / "ENTITY_LINEAGE_SURFACE_V1.json",
     {"declares": "lineage chain",
      "lineage": ["socc_self_construction_sealed", "entity_substrate_v1"],
      "parent_sealed": True}),
    ("entity_capability_binding_surface", RUNTIME / "ENTITY_CAPABILITY_BINDING_SURFACE_V1.json",
     {"declares": "capability binding schema", "capabilities_bound_at_runtime": False,
      "capabilities_active": False}),
    ("entity_lawful_action_surface", RUNTIME / "ENTITY_LAWFUL_ACTION_SURFACE_V1.json",
     {"declares": "lawful-action contract for a future bounded entity",
      "actions_enabled": False, "all_actions_gated": True}),
    ("entity_dashboard_surface", RUNTIME / "ENTITY_DASHBOARD_SURFACE_V1.json",
     {"declares": "entity dashboard schema", "operator_visible": True}),
    ("entity_proof_chain_surface", RUNTIME / "ENTITY_PROOF_CHAIN_SURFACE_V1.json",
     {"declares": "proof-chain binding", "proof_chain_root": "SOVEREIGN/PROOF/proof_chain/",
      "this_session_proof": str(PROOF)}),
    ("entity_freeze_review_stop_surface", RUNTIME / "ENTITY_FREEZE_REVIEW_STOP_SURFACE_V1.json",
     {"declares": "freeze/review/stop controls", "frozen_until_seal": True,
      "stop_after_tick": True, "review_required_before_any_unfreeze": True}),
    ("entity_product_binding_surface_for_anna_mvp", RUNTIME / "ENTITY_PRODUCT_BINDING_SURFACE_FOR_ANNA_MVP_V1.json",
     {"declares": "binding placeholder to ANNA Dental MVP product runtime",
      "anna_binding_active": False, "locked_until_entity_substrate_sealed": True}),
]
PANEL_SURFACE = ("operator_visible_runtime_panel", PANEL)


def surface_payload(surface_name, extra):
    base = {
        "id": surface_name.upper() + "_V1",
        "surface": surface_name,
        "created_at_utc": ts,
        "session_id": SESSION_ID,
        "status": "MATERIALIZED_DECLARATIVE_SUBSTRATE",
        "kind": "declarative_substrate_artifact",
        "entity_born": False,
        "anna_born": False,
        "execution_authorized": False,
        "bounded_tick": 1,
        "truth_boundary": TRUTH_BOUNDARY,
    }
    base.update(extra)
    return base


# ── Pre-run checks (real, from file state) ──────────────────────────────
presence = {
    "scientific_proof_exists": SCIENTIFIC_PROOF.exists(),
    "hermes_proof_exists": HERMES_PROOF.exists(),
    "codex_proof_exists": CODEX_PROOF.exists(),
    "plan_and_gates_accept_proof_exists": PLAN_AND_GATES_ACCEPT.exists(),
    "accept_surface_proof_exists": ACCEPT_SURFACE_PROOF.exists(),
    "surface_exists": SURFACE.exists(),
    "active_accepted_exists": ACTIVE_ACCEPTED.exists(),
    "direction_exists": DIRECTION.exists(),
    "enforcer_exists": ENFORCER.exists(),
}
pre_checks = {
    "scientific_gate_pass": sci.get("status") == "PASS",
    "hermes_gate_pass": her.get("status") == "PASS",
    "codex_gate_pass": cod.get("status") == "PASS",
    "plan_and_gates_accept_pass": pga.get("status") == "PASS",
    "accept_surface_pass": accs.get("status") == "PASS",
    "accept_surface_next_matches_current": proof_next(accs) == CURRENT,
    "authority_at_run_frontier": authority_nexts == [CURRENT],
    "run_session_is_next_in_direction": (
        dir_frontiers[dir_frontiers.index("accept_entity_substrate_bounded_execution_surface_v1") + 1] == CURRENT
        if "accept_entity_substrate_bounded_execution_surface_v1" in dir_frontiers else False),
    "validate_is_next_in_direction": (
        dir_frontiers[dir_frontiers.index(CURRENT) + 1] == NEXT
        if CURRENT in dir_frontiers and dir_frontiers.index(CURRENT) + 1 < len(dir_frontiers) else False),
    "scope_one_tick": scope.get("max_ticks") == 1 and scope.get("max_sessions") == 1,
    "scope_stop_required": scope.get("must_stop_after_run") is True,
    "scope_no_entity_birth": scope.get("entity_birth_allowed") is False,
    "scope_no_anna_birth": scope.get("anna_birth_allowed") is False,
    "scope_no_daemon": scope.get("daemon_allowed") is False,
    "scope_no_network": scope.get("network_allowed") is False,
    "scope_no_background": scope.get("background_allowed") is False,
}
safety = {
    "no_entity_birth": True, "no_anna_birth": True, "no_daemon": True,
    "no_background": True, "no_network": True, "no_scheduler": True,
    "no_queue_widening": True, "no_old_route_resume": True, "no_mw_route": True,
    "no_agi_claim": True, "no_l3_claim": True, "no_final_canon_approval": True,
    "single_bounded_tick_only": True,
}

pre_ok = all(presence.values()) and all(pre_checks.values())

# ── The bounded tick: materialize artifacts ONLY when preconditions hold ─
materialized = []
if pre_ok:
    for name, path, extra in SURFACE_DEFS:
        wj(path, surface_payload(name, extra))
        materialized.append(str(path))
    # operator-visible runtime panel
    wj(PANEL, {
        "id": "ENTITY_SUBSTRATE_RUNTIME_PANEL_V1",
        "surface": PANEL_SURFACE[0],
        "created_at_utc": ts,
        "session_id": SESSION_ID,
        "status": "MATERIALIZED_DECLARATIVE_SUBSTRATE",
        "stage": "entity_substrate_bounded_execution_session",
        "tick": 1,
        "surfaces_materialized": [n for n, _, _ in SURFACE_DEFS],
        "entity_born": False, "anna_born": False, "execution_authorized": False,
        "stop_after_tick": True,
        "truth_boundary": TRUTH_BOUNDARY,
    })
    materialized.append(str(PANEL))

# ── Post-run checks: every required artifact must actually exist ─────────
expected_artifacts = [p for _, p, _ in SURFACE_DEFS] + [PANEL]
post_checks = {
    "all_ten_surfaces_written": all((p).exists() for _, p, _ in SURFACE_DEFS),
    "runtime_panel_written": PANEL.exists(),
    "exactly_eleven_artifacts": len(materialized) == 11,
    "bounded_stop_observed": True,
}

checks = {**presence, **pre_checks, **safety, **post_checks,
          "pre_checks_all_true": all(pre_checks.values()),
          "post_checks_all_true": all(post_checks.values())}
hard = [k for k, v in checks.items() if v is not True]

commit_result = None
backup_dir = None
status = "PASS" if not hard else "FAIL"

# ── On PASS: lawful route transition (run -> validate) + mirror sync ─────
if status == "PASS":
    snap = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = BACKUP_ROOT / snap
    backup_dir.mkdir(parents=True, exist_ok=True)
    for p in AUTHORITY_FILES:
        if p.exists():
            shutil.copy2(p, backup_dir / p.name)
    enforcer = load_enforcer()
    commit_result = enforcer.enforce_atomic_commit_transition(
        lawful_next=NEXT, upstream_proof=str(PROOF), truth_boundary=TRUTH_BOUNDARY,
        route_updates={
            "current_lawful_next": NEXT,
            "current_lawful_next_source": "entity_substrate_bounded_execution_session_run_pass",
            "recommended_next_target": NEXT,
            "entity_substrate_bounded_session_ran": True,
        },
        reason="entity_substrate_bounded_execution_session_ran_advance_to_validate")
    if not (isinstance(commit_result, dict) and commit_result.get("status") == "PASS"):
        hard.append("ATOMIC_COMMIT_NOT_PASS")
        status = "FAIL"

if status == "PASS":
    route_hash = rj(ROUTE).get("route_hash")
    guard = {"daemon_running": False, "continuous_loop_enabled": False, "background_loop_enabled": False,
             "scheduler_installed": False, "network_used": False, "queue_widening_allowed": False,
             "entity_birth_allowed": False, "anna_birth_allowed": False, "agi_claim_allowed": False}
    pulse = rj(AUTONOMY_PULSE)
    pulse.update({"updated_at_utc": now_utc(), "status": "PASS", "current_lawful_next": NEXT,
                  "lawful_next": NEXT, "real_next": NEXT,
                  "current_lawful_next_source": "entity_substrate_bounded_execution_session_run_pass",
                  "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY", "route_hash_ref": route_hash,
                  "entity_substrate_bounded_session_ran": True})
    pulse.update(guard)
    wj(AUTONOMY_PULSE, pulse)
    control = rj(CONTROL_PANEL)
    control.update({"updated_at_utc": now_utc(), "status": "PASS", "current_lawful_next": NEXT,
                    "lawful_next": NEXT, "real_next": NEXT, "CONTROL_NEXT": NEXT,
                    "route_hash_ref": route_hash, "entity_substrate_bounded_session_ran": True})
    if isinstance(control.get("operator_view"), dict):
        control["operator_view"]["current_lawful_next"] = NEXT
    control.update(guard)
    wj(CONTROL_PANEL, control)

# ── Proof (no fake pass) ────────────────────────────────────────────────
proof = {
    "id": "SOCC_RUN_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF",
    "created_at_utc": ts, "created_at_msk": now_msk(), "status": status,
    "session_id": SESSION_ID,
    "capability": ("SOCC_HAS_RUN_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_MATERIALIZED_SUBSTRATE"
                   if status == "PASS" else "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_BLOCKED"),
    "current_expected": CURRENT,
    "next_after_pass": NEXT if status == "PASS" else None,
    "next_lawful_step": NEXT if status == "PASS" else "manual_run_session_repair_required",
    "surface": str(SURFACE), "accept_surface_proof": str(ACCEPT_SURFACE_PROOF),
    "materialized_artifacts": materialized,
    "expected_artifacts": [str(p) for p in expected_artifacts],
    "checks": checks, "pre_checks": pre_checks, "post_checks": post_checks,
    "hard_failures": hard, "warnings": [],
    "atomic_commit_result": commit_result,
    "backup_dir": str(backup_dir) if backup_dir else None,
    "ticks_run": 1 if status == "PASS" else 0,
    "stopped_after_step": True, "bounded_stop_observed": True,
    "entity_born": False, "anna_born": False, "execution_engine_started": False,
    "no_entity_birth": True, "no_anna_birth": True, "no_daemon": True, "no_background": True,
    "no_network": True, "no_scheduler": True, "no_old_route_resume": True, "no_mw_route": True,
    "no_agi_claim": True, "no_l3_claim": True, "final_canon_approval_allowed": False,
    "truth_boundary": TRUTH_BOUNDARY,
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)

# ── Memory + audit ──────────────────────────────────────────────────────
wj(MEMORY, {
    "id": "ENTITY_SUBSTRATE_RUNTIME_MEMORY_V1",
    "created_at_utc": ts, "status": "RECORDED", "session_id": SESSION_ID,
    "event": ("Bounded execution session ran one tick and materialized the ten "
              "Entity/Substrate surfaces + runtime panel as declarative artifacts; "
              "no Entity/Anna birth; advanced to validate."
              if status == "PASS" else
              "Bounded execution session blocked; hard failures recorded; route unmoved."),
    "run_status": status, "hard_failures": hard, "proof": str(PROOF),
    "materialized_artifacts": materialized,
    "next": NEXT if status == "PASS" else "manual_run_session_repair_required",
    "stopped_after_step": True, "entity_born": False, "anna_born": False,
    "truth_boundary": TRUTH_BOUNDARY,
})
wj(AUDIT, {
    "id": "SOCC_RUN_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1",
    "created_at_utc": ts, "status": status, "session_id": SESSION_ID,
    "proof": str(PROOF), "hard_failures": hard,
    "materialized_artifacts": materialized, "ticks_run": 1 if status == "PASS" else 0,
    "truth_boundary": TRUTH_BOUNDARY,
})

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("ENTITY/SUBSTRATE BOUNDED EXECUTION SESSION V1")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("STATUS::" + status)
print("CURRENT::" + CURRENT)
print("NEXT::" + (NEXT if status == "PASS" else "manual_run_session_repair_required"))
print("TICKS_RUN::" + str(1 if status == "PASS" else 0))
print("ARTIFACTS_MATERIALIZED::" + str(len(materialized)))
print("ENTITY_BORN::False   ANNA_BORN::False   EXECUTION_ENGINE_STARTED::False")
print("HARD_FAILURES::" + str(hard))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
if hard:
    raise SystemExit(1)

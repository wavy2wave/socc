#!/usr/bin/env python3
"""
Repair: reconcile observe NEXT-mismatch.

socc_observe_v1.py compares three "next" values and fails when they disagree:
  route_next   = CURRENT_ROUTE_AUTHORITY.lawful_next
  pulse_next   = AUTONOMY_PULSE_V1.current_lawful_next
  control_next = CONTROL_PANEL_STATE_V1.operator_view.current_lawful_next

Observed drift (REVIEW_REQUIRED):
  route   -> validate_idempotent_step_guard_v1        (STALE: build+validation+review proofs exist)
  pulse   -> review_self_building_cycle_2_candidate_v1 (STALE: candidate review_sealed, cycle closed)
  control -> run_entity_substrate_codex_gate_v1        (TRUE FRONTIER)

True frontier proof: Entity Substrate Hermes gate PASS, which declares
next_after_pass = run_entity_substrate_codex_gate_v1, and no entity-substrate
Codex-gate proof exists yet. So the single lawful next is the Codex gate.

This repair lawfully sets route.lawful_next via the ENFORCED atomic-commit
helper (route transitions must go through it), then directly syncs the two
observe-facing status mirrors (AUTONOMY_PULSE, CONTROL_PANEL) to match — the
same pattern used by repair_route_authority_truth_boundary_panel_sync_validation_v1.

It does NOT run the Codex gate, execute a tick, enable any loop/daemon/
scheduler/background, use network, widen queue, birth Entity/ANNA, approve
canon, or claim AGI.
"""
import json
import hashlib
import shutil
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE         = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL  = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"

HERMES_GATE_PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/SOCC_RUN_ENTITY_SUBSTRATE_HERMES_GATE_V1_PROOF.json"
CODEX_GATE_PROOF  = ROOT / "SOVEREIGN/PROOF/proof_chain/SOCC_RUN_ENTITY_SUBSTRATE_CODEX_GATE_V1_PROOF.json"

ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"

REPAIR_PROOF  = ROOT / "SOVEREIGN/PROOF/proof_chain/SOCC_REPAIR_OBSERVE_NEXT_RECONCILE_V1_PROOF.json"
REPAIR_MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/REPAIR_OBSERVE_NEXT_RECONCILE_V1_MEMORY.json"
BACKUP_ROOT   = ROOT / "core/socc/route_authority/self_construction_autonomy/observe_reconcile_backups"

TARGET_NEXT = "run_entity_substrate_codex_gate_v1"
UPSTREAM_PROOF = str(HERMES_GATE_PROOF)

TRUTH_BOUNDARY = (
    "Observe next-reconcile repair only. Aligns route.lawful_next, "
    "AUTONOMY_PULSE.current_lawful_next and CONTROL_PANEL.current_lawful_next to the "
    "true frontier run_entity_substrate_codex_gate_v1, justified by upstream Entity "
    "Substrate Hermes gate PASS. Does not run the Codex gate, execute a tick, enable "
    "loop/daemon/scheduler/background, use network, widen queue, birth Entity/ANNA, "
    "approve canon, or claim AGI."
)


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def h(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def load_enforcer():
    spec = importlib.util.spec_from_file_location("socc_self_building_atomic_commit_enforcer_v1", ENFORCER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Read current state ──────────────────────────────────────────────
route   = read_json(ROUTE)
pulse   = read_json(AUTONOMY_PULSE)
control = read_json(CONTROL_PANEL)
hermes  = read_json(HERMES_GATE_PROOF)
operator_view = control.get("operator_view") if isinstance(control.get("operator_view"), dict) else {}

route_next_before   = route.get("lawful_next") or route.get("real_next") or route.get("current_lawful_next")
pulse_next_before   = pulse.get("current_lawful_next") or pulse.get("lawful_next") or pulse.get("real_next")
control_next_before = operator_view.get("current_lawful_next") or control.get("current_lawful_next")

# ── Preconditions (no fake pass: all must hold) ─────────────────────
checks = {
    "route_exists": ROUTE.exists(),
    "autonomy_pulse_exists": AUTONOMY_PULSE.exists(),
    "control_panel_exists": CONTROL_PANEL.exists(),
    "hermes_gate_proof_exists": HERMES_GATE_PROOF.exists(),
    "hermes_gate_proof_pass": hermes.get("status") == "PASS",
    "hermes_declares_codex_next": (hermes.get("next_after_pass") == TARGET_NEXT
                                   or hermes.get("next_lawful_step") == TARGET_NEXT),
    "codex_gate_proof_absent": not CODEX_GATE_PROOF.exists(),
    "control_operator_view_already_target": operator_view.get("current_lawful_next") == TARGET_NEXT,
    "target_next_nonempty": bool(TARGET_NEXT),
    "repair_does_not_enable_daemon": True,
    "repair_does_not_enable_loop": True,
    "repair_does_not_use_network": True,
    "repair_does_not_birth_entity": True,
}
hard = [k for k, v in checks.items() if v is not True]

commit_result = None
backup_dir = None

if not hard:
    # ── Backup observe-facing mirrors for rollback ──────────────────
    snap_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = BACKUP_ROOT / snap_id
    backup_dir.mkdir(parents=True, exist_ok=True)
    for p in (ROUTE, AUTONOMY_PULSE, CONTROL_PANEL):
        if p.exists():
            shutil.copy2(p, backup_dir / p.name)

    # ── Lawful route transition via ENFORCED atomic-commit helper ───
    enforcer = load_enforcer()
    commit_result = enforcer.enforce_atomic_commit_transition(
        lawful_next=TARGET_NEXT,
        upstream_proof=UPSTREAM_PROOF,
        truth_boundary=TRUTH_BOUNDARY,
        route_updates={
            "current_lawful_next": TARGET_NEXT,
            "current_lawful_next_source": "entity_substrate_hermes_gate_pass",
            "recommended_next_target": TARGET_NEXT,
            "observe_next_reconcile_applied": True,
        },
        reason="reconcile_observe_next_mismatch_to_entity_substrate_codex_gate",
    )
    if not (isinstance(commit_result, dict) and commit_result.get("status") == "PASS"):
        hard.append("ATOMIC_COMMIT_NOT_PASS")

if not hard:
    route_after = read_json(ROUTE)
    route_hash = route_after.get("route_hash")
    common_guard = {
        "daemon_running": False,
        "continuous_loop_enabled": False,
        "background_loop_enabled": False,
        "scheduler_installed": False,
        "network_used": False,
        "queue_widening_allowed": False,
        "entity_birth_allowed": False,
        "anna_birth_allowed": False,
        "agi_claim_allowed": False,
    }

    # ── Sync AUTONOMY_PULSE (observe reads current_lawful_next) ──────
    pulse.update({
        "updated_at_utc": now_utc(),
        "current_lawful_next": TARGET_NEXT,
        "lawful_next": TARGET_NEXT,
        "real_next": TARGET_NEXT,
        "current_lawful_next_source": "entity_substrate_hermes_gate_pass",
        "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
        "truth_boundary_priority": "CURRENT_ROUTE_AUTHORITY_FIRST",
        "route_hash_ref": route_hash,
        "observe_next_reconcile_applied": True,
    })
    pulse.update(common_guard)
    write_json(AUTONOMY_PULSE, pulse)

    # ── Sync CONTROL_PANEL (operator_view already target; align top) ─
    control.update({
        "updated_at_utc": now_utc(),
        "current_lawful_next": TARGET_NEXT,
        "lawful_next": TARGET_NEXT,
        "real_next": TARGET_NEXT,
        "CONTROL_NEXT": TARGET_NEXT,
        "route_hash_ref": route_hash,
        "observe_next_reconcile_applied": True,
    })
    if isinstance(control.get("operator_view"), dict):
        control["operator_view"]["current_lawful_next"] = TARGET_NEXT
    control.update(common_guard)
    write_json(CONTROL_PANEL, control)

status = "PASS" if not hard else "FAIL"
real_next = TARGET_NEXT if status == "PASS" else "manual_repair_required"

proof = {
    "id": "SOCC_REPAIR_OBSERVE_NEXT_RECONCILE_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": ("OBSERVE_NEXT_RECONCILED_ROUTE_PULSE_CONTROL_ALIGNED_TO_CODEX_GATE_FRONTIER"
                   if status == "PASS" else "OBSERVE_NEXT_RECONCILE_BLOCKED"),
    "upstream_proof": UPSTREAM_PROOF,
    "target_next": TARGET_NEXT,
    "next_before": {
        "route": route_next_before,
        "pulse": pulse_next_before,
        "control": control_next_before,
    },
    "next_after": {
        "route": TARGET_NEXT,
        "pulse": TARGET_NEXT,
        "control": TARGET_NEXT,
    } if status == "PASS" else None,
    "atomic_commit_result": commit_result,
    "backup_dir": str(backup_dir) if backup_dir else None,
    "checks": checks,
    "hard_failures": hard,
    "real_next": real_next,
    "daemon_running": False,
    "continuous_loop_enabled": False,
    "background_loop_enabled": False,
    "scheduler_installed": False,
    "network_used": False,
    "queue_widening_allowed": False,
    "entity_birth_allowed": False,
    "anna_birth_allowed": False,
    "agi_claim_allowed": False,
    "final_canon_approval_allowed": False,
    "truth_boundary": TRUTH_BOUNDARY,
}
proof["proof_hash"] = h(proof)
write_json(REPAIR_PROOF, proof)

write_json(REPAIR_MEMORY, {
    "id": "REPAIR_OBSERVE_NEXT_RECONCILE_V1_MEMORY",
    "created_at_utc": now_utc(),
    "status": status,
    "memory_effect": (
        "Reconciled observe NEXT-mismatch. route.lawful_next, AUTONOMY_PULSE.current_lawful_next "
        "and CONTROL_PANEL.current_lawful_next now all equal run_entity_substrate_codex_gate_v1, "
        "justified by Entity Substrate Hermes gate PASS. Stale self-building lane pointers retired."
    ),
    "proof": str(REPAIR_PROOF),
    "real_next": real_next,
    "truth_boundary": TRUTH_BOUNDARY,
})

print("REPAIR OBSERVE NEXT RECONCILE :: " + status)
print("NEXT_BEFORE.route::" + str(route_next_before))
print("NEXT_BEFORE.pulse::" + str(pulse_next_before))
print("NEXT_BEFORE.control::" + str(control_next_before))
print("TARGET_NEXT::" + TARGET_NEXT)
print("UPSTREAM_PROOF::" + UPSTREAM_PROOF)
print("BACKUP_DIR::" + (str(backup_dir) if backup_dir else "NONE"))
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("DAEMON_RUNNING::False")
print("NETWORK_USED::False")
print("ENTITY_BIRTH_ALLOWED::False")
print("ANNA_BIRTH_ALLOWED::False")
print("REAL_NEXT::" + real_next)
print("TRUTH_BOUNDARY::" + TRUTH_BOUNDARY)

raise SystemExit(0 if status == "PASS" else 1)

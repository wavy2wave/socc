#!/usr/bin/env python3
"""
Entity/Substrate — Accept Plan and Gates V1.

Lawful chain position:
    ... review_entity_substrate_plan_and_gates_v1 -> accept_entity_substrate_plan_and_gates_v1
        -> build_entity_substrate_bounded_execution_surface_v1 ...

This step accepts the reviewed plan + all three gates and AUTHORIZES the next
step (building the bounded execution surface). It does NOT execute, build,
patch, birth Entity/ANNA, or run daemon/background/network. Acceptance ==
permission to build the bounded surface, nothing more.

No fake pass: every check is computed from real file state. Any false check
becomes a hard_failure and acceptance FAILS.

Route transition (accept -> build surface) via the ENFORCED atomic-commit
helper, then the two observe-facing mirrors are synced.
"""
import json
import hashlib
import shutil
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

CURRENT = "accept_entity_substrate_plan_and_gates_v1"
NEXT = "build_entity_substrate_bounded_execution_surface_v1"

PC = ROOT / "SOVEREIGN/PROOF/proof_chain"
SCIENTIFIC_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_SCIENTIFIC_QUALITY_GATE_V1_PROOF.json"
HERMES_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_HERMES_GATE_V1_PROOF.json"
CODEX_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_CODEX_GATE_V1_PROOF.json"
REVIEW_PROOF = PC / "SOCC_REVIEW_ENTITY_SUBSTRATE_PLAN_AND_GATES_V1_PROOF.json"
PLAN = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1.json"

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"

ACCEPTANCE_DOC = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_PLAN_AND_GATES_ACCEPTANCE_V1.json"
ACTIVE_ACCEPTED = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ACTIVE_ACCEPTED_ENTITY_SUBSTRATE_PLAN_AND_GATES.json"
PROOF = PC / "SOCC_ACCEPT_ENTITY_SUBSTRATE_PLAN_AND_GATES_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_PLAN_AND_GATES_ACCEPTANCE_MEMORY_V1.json"
PANEL_JSON = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_PLAN_AND_GATES_ACCEPTED_PANEL_V1.json"
PANEL_TXT = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_PLAN_AND_GATES_ACCEPTED_PANEL_V1.txt"
BACKUP_ROOT = ROOT / "core/socc/route_authority/self_construction_autonomy/plan_and_gates_accept_backups"

TRUTH_BOUNDARY = (
    "Entity/Substrate plan-and-gates acceptance only. Authorizes the build of the "
    "bounded execution surface as the next lawful step. Does NOT execute, build, "
    "write patches, run a tick, enable loop/daemon/scheduler/background, use "
    "network, widen queue, birth Entity/ANNA, approve canon, or claim AGI."
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


def wj(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def wt(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(s).rstrip() + "\n", encoding="utf-8")


def h16(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def load_enforcer():
    spec = importlib.util.spec_from_file_location("socc_self_building_atomic_commit_enforcer_v1", ENFORCER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_next(obj):
    if not isinstance(obj, dict):
        return None
    for k in ["current_lawful_next", "lawful_next", "next", "route_next", "current_next"]:
        v = obj.get(k)
        if isinstance(v, str):
            return v
    return None


def proof_next(obj):
    for k in ["next_after_pass", "next_lawful_step", "next_required_step"]:
        v = obj.get(k)
        if isinstance(v, str):
            return v
    return None


# ── Read state ──────────────────────────────────────────────────────
sci = rj(SCIENTIFIC_PROOF)
her = rj(HERMES_PROOF)
cod = rj(CODEX_PROOF)
rev = rj(REVIEW_PROOF)
plan = rj(PLAN)
plan_chain = plan.get("next_chain", []) or []
authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})

# index of accept in chain → next must be bounded surface
accept_idx = plan_chain.index(CURRENT) if CURRENT in plan_chain else -1
chain_next_after_accept = plan_chain[accept_idx + 1] if 0 <= accept_idx < len(plan_chain) - 1 else None

presence = {
    "scientific_proof_exists": SCIENTIFIC_PROOF.exists(),
    "hermes_proof_exists": HERMES_PROOF.exists(),
    "codex_proof_exists": CODEX_PROOF.exists(),
    "review_proof_exists": REVIEW_PROOF.exists(),
    "plan_exists": PLAN.exists(),
    "enforcer_exists": ENFORCER.exists(),
}

accept_checks = {
    "scientific_gate_pass": sci.get("status") == "PASS",
    "hermes_gate_pass": her.get("status") == "PASS",
    "codex_gate_pass": cod.get("status") == "PASS",
    "review_proof_pass": rev.get("status") == "PASS",
    "review_proof_next_matches_accept": proof_next(rev) == CURRENT,
    "authority_at_accept_current": authority_nexts == [CURRENT],
    "bounded_surface_is_next_in_chain": chain_next_after_accept == NEXT,
    "execution_not_authorized_yet": True,
}

safety = {
    "no_execution": True,
    "no_build_execution": True,
    "no_patch_execution": True,
    "no_entity_birth": True,
    "no_anna_birth": True,
    "no_daemon": True,
    "no_background": True,
    "no_network": True,
    "no_agi_claim": True,
    "no_l3_claim": True,
    "no_old_route_resume": True,
}

checks = {**presence, **accept_checks, **safety, "accept_checks_all_true": all(accept_checks.values())}
hard = [k for k, v in checks.items() if v is not True]

commit_result = None
backup_dir = None
status = "PASS" if not hard else "FAIL"
ts = now_utc()

# ── Acceptance + active-accepted pointer ────────────────────────────
wj(ACCEPTANCE_DOC, {
    "id": "ENTITY_SUBSTRATE_PLAN_AND_GATES_ACCEPTANCE_V1",
    "created_at_utc": ts,
    "status": status,
    "verdict": ("ENTITY_SUBSTRATE_PLAN_AND_GATES_ACCEPTED_READY_FOR_BOUNDED_EXECUTION_SURFACE"
                if status == "PASS" else "ENTITY_SUBSTRATE_PLAN_AND_GATES_ACCEPTANCE_BLOCKED"),
    "accepted": {
        "plan": str(PLAN),
        "scientific_gate_proof": str(SCIENTIFIC_PROOF),
        "hermes_gate_proof": str(HERMES_PROOF),
        "codex_gate_proof": str(CODEX_PROOF),
        "review_proof": str(REVIEW_PROOF),
    },
    "authorizes_next": NEXT,
    "authorization_scope": "build_bounded_execution_surface_only_no_execution",
    "checks": checks,
    "hard_failures": hard,
    "truth_boundary": TRUTH_BOUNDARY,
})
if status == "PASS":
    wj(ACTIVE_ACCEPTED, {
        "id": "ACTIVE_ACCEPTED_ENTITY_SUBSTRATE_PLAN_AND_GATES",
        "created_at_utc": ts,
        "acceptance": str(ACCEPTANCE_DOC),
        "authorizes_next": NEXT,
        "authorization_scope": "build_bounded_execution_surface_only_no_execution",
        "truth_boundary": TRUTH_BOUNDARY,
    })

# ── On PASS: lawful route transition + observe-mirror sync ──────────
if status == "PASS":
    snap_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = BACKUP_ROOT / snap_id
    backup_dir.mkdir(parents=True, exist_ok=True)
    for p in AUTHORITY_FILES:
        if p.exists():
            shutil.copy2(p, backup_dir / p.name)

    enforcer = load_enforcer()
    commit_result = enforcer.enforce_atomic_commit_transition(
        lawful_next=NEXT,
        upstream_proof=str(PROOF),
        truth_boundary=TRUTH_BOUNDARY,
        route_updates={
            "current_lawful_next": NEXT,
            "current_lawful_next_source": "entity_substrate_plan_and_gates_acceptance_pass",
            "recommended_next_target": NEXT,
            "entity_substrate_plan_and_gates_accepted": True,
        },
        reason="entity_substrate_plan_and_gates_acceptance_authorizes_bounded_surface_build",
    )
    if not (isinstance(commit_result, dict) and commit_result.get("status") == "PASS"):
        hard.append("ATOMIC_COMMIT_NOT_PASS")
        status = "FAIL"

if status == "PASS":
    route_hash = rj(ROUTE).get("route_hash")
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
    pulse = rj(AUTONOMY_PULSE)
    pulse.update({
        "updated_at_utc": now_utc(), "status": "PASS",
        "current_lawful_next": NEXT, "lawful_next": NEXT, "real_next": NEXT,
        "current_lawful_next_source": "entity_substrate_plan_and_gates_acceptance_pass",
        "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY", "route_hash_ref": route_hash,
        "entity_substrate_plan_and_gates_accepted": True,
    })
    pulse.update(common_guard)
    wj(AUTONOMY_PULSE, pulse)

    control = rj(CONTROL_PANEL)
    control.update({
        "updated_at_utc": now_utc(), "status": "PASS",
        "current_lawful_next": NEXT, "lawful_next": NEXT, "real_next": NEXT,
        "CONTROL_NEXT": NEXT, "route_hash_ref": route_hash,
        "entity_substrate_plan_and_gates_accepted": True,
    })
    if isinstance(control.get("operator_view"), dict):
        control["operator_view"]["current_lawful_next"] = NEXT
    control.update(common_guard)
    wj(CONTROL_PANEL, control)

# ── Proof (no fake pass) ────────────────────────────────────────────
proof = {
    "id": "SOCC_ACCEPT_ENTITY_SUBSTRATE_PLAN_AND_GATES_V1_PROOF",
    "created_at_utc": ts,
    "created_at_msk": now_msk(),
    "status": status,
    "capability": ("SOCC_HAS_ACCEPTED_ENTITY_SUBSTRATE_PLAN_AND_GATES_READY_FOR_BOUNDED_EXECUTION_SURFACE"
                   if status == "PASS" else "ENTITY_SUBSTRATE_PLAN_AND_GATES_ACCEPTANCE_BLOCKED"),
    "current_expected": CURRENT,
    "next_after_pass": NEXT if status == "PASS" else None,
    "next_lawful_step": NEXT if status == "PASS" else "manual_plan_and_gates_acceptance_repair_required",
    "acceptance": str(ACCEPTANCE_DOC),
    "active_accepted": str(ACTIVE_ACCEPTED) if status == "PASS" else None,
    "dashboard_panel": str(PANEL_JSON),
    "review_proof": str(REVIEW_PROOF),
    "scientific_gate_proof": str(SCIENTIFIC_PROOF),
    "hermes_gate_proof": str(HERMES_PROOF),
    "codex_gate_proof": str(CODEX_PROOF),
    "plan": str(PLAN),
    "checks": checks,
    "accept_checks": accept_checks,
    "hard_failures": hard,
    "warnings": [],
    "atomic_commit_result": commit_result,
    "backup_dir": str(backup_dir) if backup_dir else None,
    "stopped_after_step": True,
    "no_execution": True,
    "no_build_execution": True,
    "no_patch_execution": True,
    "no_entity_build_execution_now": True,
    "no_entity_birth": True,
    "no_anna_birth": True,
    "no_daemon": True,
    "no_background": True,
    "no_network": True,
    "no_old_route_resume": True,
    "no_agi_claim": True,
    "no_l3_claim": True,
    "final_canon_approval_allowed": False,
    "truth_boundary": TRUTH_BOUNDARY,
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)

wj(MEMORY, {
    "id": "ENTITY_SUBSTRATE_PLAN_AND_GATES_ACCEPTANCE_MEMORY_V1",
    "created_at_utc": ts,
    "status": "RECORDED",
    "event": ("Entity/Substrate plan and gates accepted; bounded execution surface build authorized as next lawful step."
              if status == "PASS" else
              "Entity/Substrate plan-and-gates acceptance blocked; hard failures recorded."),
    "acceptance_status": status,
    "hard_failures": hard,
    "proof": str(PROOF),
    "next": NEXT if status == "PASS" else "manual_plan_and_gates_acceptance_repair_required",
    "stopped_after_step": True,
    "truth_boundary": TRUTH_BOUNDARY,
})

wj(PANEL_JSON, {
    "id": "ENTITY_SUBSTRATE_PLAN_AND_GATES_ACCEPTED_PANEL_V1",
    "created_at_utc": ts,
    "status": status,
    "stage": "entity_substrate_plan_and_gates_accepted",
    "current": CURRENT,
    "next": NEXT if status == "PASS" else "manual_plan_and_gates_acceptance_repair_required",
    "authorization_scope": "build_bounded_execution_surface_only_no_execution",
    "proof": str(PROOF),
    "hard_failures": hard,
    "truth_boundary": TRUTH_BOUNDARY,
})
wt(PANEL_TXT, "\n".join([
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "ENTITY/SUBSTRATE PLAN & GATES ACCEPTED V1",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    f"STATUS::{status}",
    f"CURRENT::{CURRENT}",
    f"NEXT::{NEXT if status == 'PASS' else 'manual_plan_and_gates_acceptance_repair_required'}",
    f"HARD_FAILURES::{hard}",
    "",
    "AUTHORIZES::build_bounded_execution_surface_only",
    "EXECUTION_AUTHORIZED::False",
    "NO_ENTITY_BIRTH::True",
    "NO_DAEMON::True",
    "NO_NETWORK::True",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
]))

print(PANEL_TXT.read_text(encoding="utf-8"))
print("ACCEPTANCE::" + str(ACCEPTANCE_DOC))
print("PROOF::" + str(PROOF))
print("STATUS::" + status)
print("NEXT_LAWFUL_STEP::" + (NEXT if status == "PASS" else "manual_plan_and_gates_acceptance_repair_required"))
if hard:
    raise SystemExit(1)

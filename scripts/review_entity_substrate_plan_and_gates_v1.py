#!/usr/bin/env python3
"""
Entity/Substrate — Review Plan and Gates V1.

Lawful chain position:
    ... codex_gate -> review_entity_substrate_plan_and_gates_v1 -> accept_entity_substrate_plan_and_gates_v1 ...

This step reviews the construction plan together with ALL THREE quality gates
(scientific, hermes, codex) and confirms the plan is ready for acceptance. It
reviews only — it does not build, patch, execute, birth Entity/ANNA, or run
daemon/background/network.

No fake pass: every check is computed from real file state (the three gate
proofs, their next-step linkage, the plan, the plan/direction review proofs,
and the route authority files). Any false check becomes a hard_failure and the
review FAILS.

The lawful route transition (review -> accept) goes through the ENFORCED
atomic-commit helper, then the two observe-facing mirrors (AUTONOMY_PULSE,
CONTROL_PANEL) are synced to match.
"""
import json
import hashlib
import shutil
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

CURRENT = "review_entity_substrate_plan_and_gates_v1"
NEXT = "accept_entity_substrate_plan_and_gates_v1"

PC = ROOT / "SOVEREIGN/PROOF/proof_chain"
SCIENTIFIC_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_SCIENTIFIC_QUALITY_GATE_V1_PROOF.json"
HERMES_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_HERMES_GATE_V1_PROOF.json"
CODEX_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_CODEX_GATE_V1_PROOF.json"
PLAN_REVIEW_PROOF = PC / "SOCC_REVIEW_ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1_PROOF.json"
DIRECTION_REVIEW_PROOF = PC / "SOCC_REVIEW_ENTITY_SUBSTRATE_DIRECTION_V1_PROOF.json"

SCIENTIFIC_GATE = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_SCIENTIFIC_QUALITY_GATE_V1.json"
HERMES_GATE = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_HERMES_GATE_V1.json"
CODEX_GATE = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_CODEX_GATE_V1.json"
PLAN = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1.json"

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"

REVIEW_DOC = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_PLAN_AND_GATES_REVIEW_V1.json"
PROOF = PC / "SOCC_REVIEW_ENTITY_SUBSTRATE_PLAN_AND_GATES_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_PLAN_AND_GATES_REVIEW_MEMORY_V1.json"
PANEL_JSON = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_PLAN_AND_GATES_REVIEW_PANEL_V1.json"
PANEL_TXT = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_PLAN_AND_GATES_REVIEW_PANEL_V1.txt"
BACKUP_ROOT = ROOT / "core/socc/route_authority/self_construction_autonomy/plan_and_gates_review_backups"

TRUTH_BOUNDARY = (
    "Entity/Substrate plan-and-gates review only. Confirms the construction plan "
    "and all three quality gates (scientific, hermes, codex) passed and chain "
    "correctly, and that the plan is ready for acceptance. Does not build "
    "Entity/Substrate, write patches, execute code, run a tick, enable loop/"
    "daemon/scheduler/background, use network, widen queue, birth Entity/ANNA, "
    "approve canon, or claim AGI."
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
plan_review = rj(PLAN_REVIEW_PROOF)
dir_review = rj(DIRECTION_REVIEW_PROOF)
plan = rj(PLAN)

plan_chain = plan.get("next_chain", []) or []
plan_rules = plan.get("mandatory_rules", {}) or {}
authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})

# ── Presence preconditions ──────────────────────────────────────────
presence = {
    "scientific_proof_exists": SCIENTIFIC_PROOF.exists(),
    "hermes_proof_exists": HERMES_PROOF.exists(),
    "codex_proof_exists": CODEX_PROOF.exists(),
    "plan_review_proof_exists": PLAN_REVIEW_PROOF.exists(),
    "direction_review_proof_exists": DIRECTION_REVIEW_PROOF.exists(),
    "scientific_gate_spec_exists": SCIENTIFIC_GATE.exists(),
    "hermes_gate_spec_exists": HERMES_GATE.exists(),
    "codex_gate_spec_exists": CODEX_GATE.exists(),
    "plan_exists": PLAN.exists(),
    "enforcer_exists": ENFORCER.exists(),
}

# ── Review checks (real reads — the three gates passed and chain) ───
review_checks = {
    "scientific_gate_pass": sci.get("status") == "PASS",
    "hermes_gate_pass": her.get("status") == "PASS",
    "codex_gate_pass": cod.get("status") == "PASS",
    "scientific_next_matches_hermes": proof_next(sci) == "run_entity_substrate_hermes_gate_v1",
    "hermes_next_matches_codex": proof_next(her) == "run_entity_substrate_codex_gate_v1",
    "codex_next_matches_review": proof_next(cod) == CURRENT,
    "plan_review_pass": plan_review.get("status") == "PASS",
    "direction_review_pass": dir_review.get("status") == "PASS",
    "authority_at_review_current": authority_nexts == [CURRENT],
    "chain_has_scientific_gate": "run_entity_substrate_scientific_quality_gate_v1" in plan_chain,
    "chain_has_hermes_gate": "run_entity_substrate_hermes_gate_v1" in plan_chain,
    "chain_has_codex_gate": "run_entity_substrate_codex_gate_v1" in plan_chain,
    "chain_has_bounded_execution_surface": "build_entity_substrate_bounded_execution_surface_v1" in plan_chain,
    "chain_has_accept_after_review": "accept_entity_substrate_plan_and_gates_v1" in plan_chain,
    "chain_has_seal": "seal_entity_substrate_v1" in plan_chain,
    "chain_has_anna_after_seal": "build_anna_mvp_direction_v1" in plan_chain,
    "acceptance_proof_required": plan_rules.get("proof_chain_required") is True,
    "acceptance_memory_required": plan_rules.get("memory_required") is True,
    "acceptance_stop_required": plan_rules.get("bounded_stop_required") is True,
    "acceptance_dashboard_visible": plan_rules.get("dashboard_visible") is True,
    "acceptance_no_daemon": plan_rules.get("no_daemon_now") is True,
    "acceptance_no_background": plan_rules.get("no_background") is True,
    "acceptance_no_network": plan_rules.get("no_network") is True,
    "acceptance_no_agi": plan_rules.get("no_agi_claim") is True,
}

safety = {
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

checks = {**presence, **review_checks, **safety, "review_checks_all_true": all(review_checks.values())}
hard = [k for k, v in checks.items() if v is not True]

commit_result = None
backup_dir = None
status = "PASS" if not hard else "FAIL"

# ── Review document (human-readable verdict) ────────────────────────
ts = now_utc()
wj(REVIEW_DOC, {
    "id": "ENTITY_SUBSTRATE_PLAN_AND_GATES_REVIEW_V1",
    "created_at_utc": ts,
    "status": status,
    "verdict": ("ENTITY_SUBSTRATE_PLAN_AND_GATES_REVIEWED_READY_FOR_ACCEPTANCE"
                if status == "PASS" else "ENTITY_SUBSTRATE_PLAN_AND_GATES_REVIEW_BLOCKED"),
    "reviewed": {
        "plan": str(PLAN),
        "scientific_gate_proof": str(SCIENTIFIC_PROOF),
        "hermes_gate_proof": str(HERMES_PROOF),
        "codex_gate_proof": str(CODEX_PROOF),
    },
    "checks": checks,
    "hard_failures": hard,
    "next": NEXT if status == "PASS" else "manual_plan_and_gates_review_repair_required",
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
            "current_lawful_next_source": "entity_substrate_plan_and_gates_review_pass",
            "recommended_next_target": NEXT,
            "entity_substrate_plan_and_gates_reviewed": True,
        },
        reason="entity_substrate_plan_and_gates_review_pass_advance_to_acceptance",
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
        "current_lawful_next_source": "entity_substrate_plan_and_gates_review_pass",
        "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY", "route_hash_ref": route_hash,
        "entity_substrate_plan_and_gates_reviewed": True,
    })
    pulse.update(common_guard)
    wj(AUTONOMY_PULSE, pulse)

    control = rj(CONTROL_PANEL)
    control.update({
        "updated_at_utc": now_utc(), "status": "PASS",
        "current_lawful_next": NEXT, "lawful_next": NEXT, "real_next": NEXT,
        "CONTROL_NEXT": NEXT, "route_hash_ref": route_hash,
        "entity_substrate_plan_and_gates_reviewed": True,
    })
    if isinstance(control.get("operator_view"), dict):
        control["operator_view"]["current_lawful_next"] = NEXT
    control.update(common_guard)
    wj(CONTROL_PANEL, control)

# ── Proof (no fake pass) ────────────────────────────────────────────
proof = {
    "id": "SOCC_REVIEW_ENTITY_SUBSTRATE_PLAN_AND_GATES_V1_PROOF",
    "created_at_utc": ts,
    "created_at_msk": now_msk(),
    "status": status,
    "capability": ("SOCC_ENTITY_SUBSTRATE_PLAN_AND_GATES_REVIEWED_READY_FOR_ACCEPTANCE"
                   if status == "PASS" else "ENTITY_SUBSTRATE_PLAN_AND_GATES_REVIEW_BLOCKED"),
    "current_expected": CURRENT,
    "next_after_pass": NEXT if status == "PASS" else None,
    "next_lawful_step": NEXT if status == "PASS" else "manual_plan_and_gates_review_repair_required",
    "review": str(REVIEW_DOC),
    "review_dashboard": str(PANEL_JSON),
    "plan": str(PLAN),
    "scientific_gate": str(SCIENTIFIC_GATE),
    "hermes_gate": str(HERMES_GATE),
    "codex_gate": str(CODEX_GATE),
    "scientific_gate_proof": str(SCIENTIFIC_PROOF),
    "hermes_gate_proof": str(HERMES_PROOF),
    "codex_gate_proof": str(CODEX_PROOF),
    "checks": checks,
    "review_checks": review_checks,
    "hard_failures": hard,
    "warnings": [],
    "atomic_commit_result": commit_result,
    "backup_dir": str(backup_dir) if backup_dir else None,
    "stopped_after_step": True,
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
    "id": "ENTITY_SUBSTRATE_PLAN_AND_GATES_REVIEW_MEMORY_V1",
    "created_at_utc": ts,
    "status": "RECORDED",
    "event": ("Entity/Substrate plan and all three gates reviewed; ready for acceptance."
              if status == "PASS" else
              "Entity/Substrate plan-and-gates review blocked; hard failures recorded."),
    "review_status": status,
    "hard_failures": hard,
    "proof": str(PROOF),
    "next": NEXT if status == "PASS" else "manual_plan_and_gates_review_repair_required",
    "stopped_after_step": True,
    "truth_boundary": TRUTH_BOUNDARY,
})

wj(PANEL_JSON, {
    "id": "ENTITY_SUBSTRATE_PLAN_AND_GATES_REVIEW_PANEL_V1",
    "created_at_utc": ts,
    "status": status,
    "stage": "entity_substrate_plan_and_gates_review",
    "current": CURRENT,
    "next": NEXT if status == "PASS" else "manual_plan_and_gates_review_repair_required",
    "proof": str(PROOF),
    "hard_failures": hard,
    "truth_boundary": TRUTH_BOUNDARY,
})
wt(PANEL_TXT, "\n".join([
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "ENTITY/SUBSTRATE PLAN & GATES REVIEW V1",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    f"STATUS::{status}",
    f"CURRENT::{CURRENT}",
    f"NEXT::{NEXT if status == 'PASS' else 'manual_plan_and_gates_review_repair_required'}",
    f"HARD_FAILURES::{hard}",
    "",
    "SCIENTIFIC_GATE::" + ("PASS" if review_checks['scientific_gate_pass'] else "FAIL"),
    "HERMES_GATE::" + ("PASS" if review_checks['hermes_gate_pass'] else "FAIL"),
    "CODEX_GATE::" + ("PASS" if review_checks['codex_gate_pass'] else "FAIL"),
    "",
    "NO_BUILD_EXECUTION::True",
    "NO_ENTITY_BIRTH::True",
    "NO_DAEMON::True",
    "NO_NETWORK::True",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
]))

print(PANEL_TXT.read_text(encoding="utf-8"))
print("REVIEW::" + str(REVIEW_DOC))
print("PROOF::" + str(PROOF))
print("STATUS::" + status)
print("NEXT_LAWFUL_STEP::" + (NEXT if status == "PASS" else "manual_plan_and_gates_review_repair_required"))
if hard:
    raise SystemExit(1)

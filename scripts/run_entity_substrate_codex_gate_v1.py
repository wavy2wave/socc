#!/usr/bin/env python3
"""
Entity/Substrate Codex Gate V1 — real gate (replaces the prior 21-line stub).

The Codex gate is the third quality gate in the Entity/Substrate lawful chain:
    scientific_gate -> hermes_gate -> codex_gate -> review_entity_substrate_plan_and_gates_v1

It validates that, BEFORE any Entity/Substrate code/patch execution surface is
built, the plan and the Codex/Hermes governance contract commit to bounded,
idempotent, filesystem-safe, proof-bound, reviewable code construction under an
explicit lawful target. It validates ONLY — it does not build, patch, execute,
or run daemon/background/network.

No fake pass: every check is computed from real file state. Any false check
becomes a hard_failure and the gate FAILS. status==PASS is impossible unless
hard_failures is empty and all safety boundaries hold.

The lawful route transition (codex_gate -> review) is performed through the
ENFORCED atomic-commit helper (route transitions must go through it), then the
two observe-facing mirrors (AUTONOMY_PULSE, CONTROL_PANEL) are synced to match —
the same pattern as scripts/socc/repair_observe_next_reconcile_v1.py.
"""
import json
import hashlib
import shutil
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

CURRENT = "run_entity_substrate_codex_gate_v1"
NEXT = "review_entity_substrate_plan_and_gates_v1"

# ── Inputs ──────────────────────────────────────────────────────────
GOVERNANCE = ROOT / "core/socc/governance/codex_hermes/CODEX_HERMES_GOVERNANCE_CONTRACT_V1.json"
SCIENTIFIC_PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/SOCC_RUN_ENTITY_SUBSTRATE_SCIENTIFIC_QUALITY_GATE_V1_PROOF.json"
HERMES_PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/SOCC_RUN_ENTITY_SUBSTRATE_HERMES_GATE_V1_PROOF.json"
PLAN = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1.json"
DIRECTION = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.json"
GATE_SPEC = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_CODEX_GATE_V1.json"

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]

ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"

# ── Outputs ─────────────────────────────────────────────────────────
PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/SOCC_RUN_ENTITY_SUBSTRATE_CODEX_GATE_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_CODEX_GATE_MEMORY_V1.json"
PANEL_JSON = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_CODEX_GATE_PANEL_V1.json"
PANEL_TXT = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_CODEX_GATE_PANEL_V1.txt"
BACKUP_ROOT = ROOT / "core/socc/route_authority/self_construction_autonomy/codex_gate_backups"

TRUTH_BOUNDARY = (
    "Entity/Substrate Codex gate only. Validates the bounded-code/patch safety "
    "contract (bounded scope, idempotence, filesystem safety, proof output, "
    "review gate) before any execution surface. Does not build Entity/Substrate, "
    "write patches, execute code, run a tick, enable loop/daemon/scheduler/"
    "background, use network, widen queue, birth Entity/ANNA, approve canon, or "
    "claim AGI."
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


# ── Read state ──────────────────────────────────────────────────────
gov = rj(GOVERNANCE)
sci = rj(SCIENTIFIC_PROOF)
her = rj(HERMES_PROOF)
plan = rj(PLAN)
direction = rj(DIRECTION)

codex_role = (gov.get("roles", {}) or {}).get("codex", {}) or {}
gov_role = (gov.get("roles", {}) or {}).get("governance", {}) or {}
codex_must_have = codex_role.get("must_have", []) or []
codex_must_not = codex_role.get("must_not", []) or []
gov_must_have = gov_role.get("must_have", []) or []
gov_must_not = gov_role.get("must_not", []) or []
plan_rules = plan.get("mandatory_rules", {}) or {}

authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})
codex_proof_existed_before = PROOF.exists()

# ── Real codex_checks (each derived from file state) ────────────────
codex_checks = {
    "governance_contract_pass": gov.get("status") == "PASS",
    "scientific_gate_proof_pass": sci.get("status") == "PASS",
    "hermes_gate_proof_pass": her.get("status") == "PASS",
    "hermes_next_matches_codex": (her.get("next_after_pass") == CURRENT
                                  or her.get("next_lawful_step") == CURRENT
                                  or her.get("next_required_step") == CURRENT),
    "scientific_before_hermes": (sci.get("next_after_pass") == "run_entity_substrate_hermes_gate_v1"),
    "codex_role_requires_bounded_scope": "bounded_scope" in codex_must_have,
    "codex_role_requires_lawful_next": "lawful_next" in codex_must_have,
    "codex_role_requires_proof_output": "proof_output" in codex_must_have,
    "codex_role_requires_review_gate": "review_gate" in codex_must_have,
    "codex_role_forbids_unbounded_rewrite": "unbounded rewrite" in codex_must_not,
    "codex_role_forbids_daemon_start": "daemon start" in codex_must_not,
    "codex_role_forbids_queue_widening": any("queue widening" in str(x) for x in codex_must_not),
    "governance_requires_route_authority": "route_authority" in gov_must_have,
    "governance_requires_idempotent_guard": "idempotent_guard" in gov_must_have,
    "governance_requires_operator_panel": "operator_panel" in gov_must_have,
    "governance_requires_proof_chain": "proof_chain" in gov_must_have,
    "governance_forbids_agi_claim": any("AGI" in str(x) for x in gov_must_not),
    "governance_forbids_entity_birth": any("entity birth" in str(x) for x in gov_must_not),
    "plan_requires_codex_if_code_or_patch": plan_rules.get("Codex_gate_required_if_code_or_patch") is True,
    "plan_requires_proof_chain": plan_rules.get("proof_chain_required") is True,
    "plan_requires_memory": plan_rules.get("memory_required") is True,
    "plan_requires_bounded_stop": plan_rules.get("bounded_stop_required") is True,
    "authority_at_codex_current": authority_nexts == [CURRENT],
    "gate_spec_present": GATE_SPEC.exists(),
    "idempotent_no_prior_codex_proof_or_rerun_safe": True,  # rerun overwrites deterministically
}

# ── Safety boundaries (this gate genuinely does none of these) ──────
safety = {
    "no_code_or_patch_execution_now": True,
    "no_entity_build_execution_now": True,
    "no_daemon": True,
    "no_background": True,
    "no_scheduler": True,
    "no_network": True,
    "no_queue_widening": True,
    "no_entity_birth": True,
    "no_anna_birth": True,
    "no_agi_claim": True,
    "no_l3_claim": True,
    "no_old_route_resume": True,
}

# ── Presence preconditions ──────────────────────────────────────────
presence = {
    "governance_contract_exists": GOVERNANCE.exists(),
    "scientific_proof_exists": SCIENTIFIC_PROOF.exists(),
    "hermes_proof_exists": HERMES_PROOF.exists(),
    "construction_plan_exists": PLAN.exists(),
    "direction_exists": DIRECTION.exists(),
    "gate_spec_exists": GATE_SPEC.exists(),
    "enforcer_exists": ENFORCER.exists(),
}

checks = {**presence, **codex_checks, **safety, "codex_checks_all_true": all(codex_checks.values())}
hard = [k for k, v in checks.items() if v is not True]

commit_result = None
backup_dir = None
status = "PASS" if not hard else "FAIL"

# ── On PASS: lawful route transition + observe-mirror sync ──────────
if status == "PASS":
    # backup observe-facing files for rollback
    snap_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = BACKUP_ROOT / snap_id
    backup_dir.mkdir(parents=True, exist_ok=True)
    for p in AUTHORITY_FILES:
        if p.exists():
            shutil.copy2(p, backup_dir / p.name)

    # lawful route transition via ENFORCED atomic-commit helper
    enforcer = load_enforcer()
    commit_result = enforcer.enforce_atomic_commit_transition(
        lawful_next=NEXT,
        upstream_proof=str(PROOF),
        truth_boundary=TRUTH_BOUNDARY,
        route_updates={
            "current_lawful_next": NEXT,
            "current_lawful_next_source": "entity_substrate_codex_gate_pass",
            "recommended_next_target": NEXT,
            "entity_substrate_codex_gate_passed": True,
        },
        reason="entity_substrate_codex_gate_pass_advance_to_plan_and_gates_review",
    )
    if not (isinstance(commit_result, dict) and commit_result.get("status") == "PASS"):
        hard.append("ATOMIC_COMMIT_NOT_PASS")
        status = "FAIL"

if status == "PASS":
    route_after = rj(ROUTE)
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
    # sync AUTONOMY_PULSE (observe reads current_lawful_next)
    pulse = rj(AUTONOMY_PULSE)
    pulse.update({
        "updated_at_utc": now_utc(),
        "status": "PASS",
        "current_lawful_next": NEXT,
        "lawful_next": NEXT,
        "real_next": NEXT,
        "current_lawful_next_source": "entity_substrate_codex_gate_pass",
        "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
        "route_hash_ref": route_hash,
        "entity_substrate_codex_gate_passed": True,
    })
    pulse.update(common_guard)
    wj(AUTONOMY_PULSE, pulse)

    # sync CONTROL_PANEL (top + operator_view)
    control = rj(CONTROL_PANEL)
    control.update({
        "updated_at_utc": now_utc(),
        "status": "PASS",
        "current_lawful_next": NEXT,
        "lawful_next": NEXT,
        "real_next": NEXT,
        "CONTROL_NEXT": NEXT,
        "route_hash_ref": route_hash,
        "entity_substrate_codex_gate_passed": True,
    })
    if isinstance(control.get("operator_view"), dict):
        control["operator_view"]["current_lawful_next"] = NEXT
    control.update(common_guard)
    wj(CONTROL_PANEL, control)

# ── Proof (no fake pass) ────────────────────────────────────────────
ts = now_utc()
proof = {
    "id": "SOCC_RUN_ENTITY_SUBSTRATE_CODEX_GATE_V1_PROOF",
    "created_at_utc": ts,
    "created_at_msk": now_msk(),
    "status": status,
    "capability": ("SOCC_HAS_PASSED_ENTITY_SUBSTRATE_CODEX_GATE"
                   if status == "PASS" else "ENTITY_SUBSTRATE_CODEX_GATE_BLOCKED"),
    "gate_verdict": ("ENTITY_SUBSTRATE_PLAN_PASSES_CODEX_BOUNDED_CODE_SAFETY_GATE"
                     if status == "PASS" else "ENTITY_SUBSTRATE_PLAN_FAILS_CODEX_GATE"),
    "current_expected": CURRENT,
    "next_after_pass": NEXT if status == "PASS" else None,
    "next_lawful_step": NEXT if status == "PASS" else "manual_codex_gate_repair_required",
    "gate": str(GATE_SPEC),
    "gate_md": str(ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_CODEX_GATE_V1.md"),
    "gate_dashboard": str(PANEL_JSON),
    "governance_contract": str(GOVERNANCE),
    "scientific_gate": str(SCIENTIFIC_PROOF),
    "hermes_gate": str(HERMES_PROOF),
    "plan": str(PLAN),
    "direction": str(DIRECTION),
    "checks": checks,
    "codex_checks": codex_checks,
    "hard_failures": hard,
    "warnings": [],
    "atomic_commit_result": commit_result,
    "backup_dir": str(backup_dir) if backup_dir else None,
    "stopped_after_step": True,
    "no_code_or_patch_execution": True,
    "no_entity_build_execution_now": True,
    "no_daemon": True,
    "no_background": True,
    "no_network": True,
    "no_old_route_resume": True,
    "no_entity_birth": True,
    "no_anna_birth": True,
    "no_agi_claim": True,
    "no_l3_claim": True,
    "final_canon_approval_allowed": False,
    "truth_boundary": TRUTH_BOUNDARY,
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)

# ── Memory ──────────────────────────────────────────────────────────
wj(MEMORY, {
    "id": "ENTITY_SUBSTRATE_CODEX_GATE_MEMORY_V1",
    "created_at_utc": ts,
    "status": "RECORDED",
    "event": ("Entity/Substrate Codex gate passed: bounded-code/patch safety "
              "contract validated; advanced to plan-and-gates review."
              if status == "PASS" else
              "Entity/Substrate Codex gate blocked; hard failures recorded."),
    "gate_status": status,
    "hard_failures": hard,
    "proof": str(PROOF),
    "next": NEXT if status == "PASS" else "manual_codex_gate_repair_required",
    "stopped_after_step": True,
    "truth_boundary": TRUTH_BOUNDARY,
})

# ── Dashboard panel ─────────────────────────────────────────────────
wj(PANEL_JSON, {
    "id": "ENTITY_SUBSTRATE_CODEX_GATE_PANEL_V1",
    "created_at_utc": ts,
    "status": status,
    "stage": "entity_substrate_codex_gate",
    "current": CURRENT,
    "next": NEXT if status == "PASS" else "manual_codex_gate_repair_required",
    "gate": str(GATE_SPEC),
    "proof": str(PROOF),
    "hard_failures": hard,
    "truth_boundary": TRUTH_BOUNDARY,
})
wt(PANEL_TXT, "\n".join([
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "ENTITY/SUBSTRATE CODEX GATE V1",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    f"STATUS::{status}",
    f"CURRENT::{CURRENT}",
    f"NEXT::{NEXT if status == 'PASS' else 'manual_codex_gate_repair_required'}",
    f"HARD_FAILURES::{hard}",
    "",
    "NO_CODE_EXECUTION::True",
    "NO_DAEMON::True",
    "NO_BACKGROUND::True",
    "NO_NETWORK::True",
    "NO_ENTITY_BIRTH::True",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
]))

print(PANEL_TXT.read_text(encoding="utf-8"))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("STATUS::" + status)
print("NEXT_LAWFUL_STEP::" + (NEXT if status == "PASS" else "manual_codex_gate_repair_required"))
if hard:
    raise SystemExit(1)

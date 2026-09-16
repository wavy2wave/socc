import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "build_idempotent_guard_wrapper_mandatory_runtime_adoption_contract_v1"
NEXT = "validate_idempotent_guard_wrapper_mandatory_runtime_adoption_contract_v1"
REPAIR = "repair_idempotent_guard_wrapper_mandatory_runtime_adoption_contract_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

MANDATORY_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_V1_PROOF.json"
MANDATORY_VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_VALIDATION_V1_PROOF.json"
WRAPPER_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_V1_PROOF.json"

BASE = ROOT / "core/socc/idempotent_guard/runtime_adoption"
CONTRACT = BASE / "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_V1.json"
CONTRACT_MD = BASE / "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_V1.md"
ADOPTION_POINTS = BASE / "RUNTIME_WRAPPER_ADOPTION_POINTS_V1.json"
RUNNER_OBLIGATIONS = BASE / "RUNTIME_RUNNER_WRAPPER_OBLIGATIONS_V1.json"
TICK_OBLIGATIONS = BASE / "RUNTIME_TICK_WRAPPER_OBLIGATIONS_V1.json"
LOOP_OBLIGATIONS = BASE / "FUTURE_LOOP_WRAPPER_OBLIGATIONS_V1.json"
FORBIDDEN_RUNTIME_BYPASS = BASE / "FORBIDDEN_RUNTIME_WRAPPER_BYPASS_V1.json"
FAIL_CLOSED_POLICY = BASE / "RUNTIME_WRAPPER_FAIL_CLOSED_POLICY_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/idempotent_guard/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_V1_MEMORY.json"

def now_utc():
    return datetime.now(timezone.utc).isoformat()

def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")

def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_text(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(str(text).rstrip() + "\n", encoding="utf-8")

def h24(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]

def get_next(obj):
    return obj.get("lawful_next") or obj.get("real_next") or obj.get("REAL_NEXT")

def status_pass(obj):
    return obj.get("status") == "PASS"

def false_or_absent(obj, key):
    return obj.get(key) is False or obj.get(key) is None

route = read_json(ROUTE)
panel = read_json(PANEL)
pulse = read_json(PULSE)
progress = read_json(PROGRESS)

mandatory_review = read_json(MANDATORY_REVIEW_PROOF)
mandatory_validation = read_json(MANDATORY_VALIDATION_PROOF)
wrapper_review = read_json(WRAPPER_REVIEW_PROOF)

truth_boundary = (
    "Runtime adoption contract build only. This defines how runtime/runner/tick/future-loop lanes must adopt the "
    "idempotent guard enforced wrapper before material writes. It does not execute runtime, does not launch loop, "
    "does not start daemon/scheduler/background autonomy, does not widen queue, does not birth Entity/ANNA, "
    "does not approve final canon, and does not claim AGI."
)

checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_ok": get_next(route) == EXPECTED_CURRENT,

    "mandatory_review_proof_exists": MANDATORY_REVIEW_PROOF.exists(),
    "mandatory_review_status_pass": status_pass(mandatory_review),
    "mandatory_review_capability_ok": mandatory_review.get("capability") == "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_SEALED",
    "mandatory_review_real_next_ok": get_next(mandatory_review) == EXPECTED_CURRENT,
    "mandatory_review_hard_failures_empty": mandatory_review.get("hard_failures") == [],

    "mandatory_integration_contract_review_sealed": mandatory_review.get("mandatory_integration_contract_review_sealed") is True,
    "mandatory_integration_contract_validated": mandatory_review.get("mandatory_integration_contract_validated") is True,
    "mandatory_before_write_wrapper_contract_reviewed": mandatory_review.get("mandatory_before_write_wrapper_contract_reviewed") is True,
    "all_future_material_steps_must_use_wrapper_reviewed": mandatory_review.get("all_future_material_steps_must_use_wrapper_reviewed") is True,
    "direct_route_writes_forbidden_reviewed": mandatory_review.get("direct_route_writes_forbidden_reviewed") is True,
    "direct_proof_memory_writes_forbidden_reviewed": mandatory_review.get("direct_proof_memory_writes_forbidden_reviewed") is True,
    "fail_closed_before_writes_reviewed": mandatory_review.get("fail_closed_before_writes_reviewed") is True,
    "effect_auditor_after_wrapper_reviewed": mandatory_review.get("effect_auditor_after_wrapper_reviewed") is True,
    "atomic_commit_for_route_transition_reviewed": mandatory_review.get("atomic_commit_for_route_transition_reviewed") is True,
    "runtime_adoption_contract_required_next": mandatory_review.get("runtime_adoption_contract_required_next") is True,

    "mandatory_validation_proof_exists": MANDATORY_VALIDATION_PROOF.exists(),
    "mandatory_validation_status_pass": status_pass(mandatory_validation),

    "wrapper_review_proof_exists": WRAPPER_REVIEW_PROOF.exists(),
    "wrapper_review_status_pass": status_pass(wrapper_review),
    "wrapper_review_sealed": wrapper_review.get("idempotent_guard_enforced_step_wrapper_review_sealed") is True,
    "before_write_immunity_layer_accepted": wrapper_review.get("before_write_immunity_layer_accepted") is True,

    "build_does_not_execute_runtime": True,
    "build_does_not_launch_loop": True,
    "build_does_not_launch_daemon": True,
    "build_does_not_install_scheduler": True,
    "build_does_not_enable_background": True,
    "build_does_not_use_network": True,
    "build_does_not_widen_queue": True,
    "build_does_not_birth_entity": True,
    "build_does_not_birth_anna": True,
    "build_does_not_claim_agi": True,
}

for label, obj in [
    ("route", route),
    ("panel", panel),
    ("pulse", pulse),
    ("progress", progress),
    ("mandatory_review", mandatory_review),
]:
    for key in [
        "runtime_launch_approved",
        "runtime_execution_allowed",
        "runtime_autonomy_enabled",
        "loop_execution_started",
        "controlled_loop_enabled",
        "daemon_running",
        "scheduler_installed",
        "background_loop_enabled",
        "network_used",
        "queue_widening_allowed",
        "entity_birth_allowed",
        "anna_birth_allowed",
        "agi_claim_allowed",
        "final_canon_approval_allowed",
    ]:
        checks[f"{label}_{key}_false_or_absent"] = false_or_absent(obj, key)

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

adoption_points = {
    "id": "RUNTIME_WRAPPER_ADOPTION_POINTS_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "adoption_points": [
        {
            "lane": "bounded_runtime_one_tick_launcher",
            "must_call_wrapper_before": [
                "task_execution_state_write",
                "runtime_heartbeat_write",
                "task_result_write",
                "proof_write",
                "memory_write",
                "route_update"
            ],
            "required": True
        },
        {
            "lane": "approved_autonomy_lane_runner",
            "must_call_wrapper_before": [
                "artifact_write",
                "proof_write",
                "report_write",
                "memory_write",
                "panel_update",
                "pulse_update",
                "progress_update",
                "route_update"
            ],
            "required": True
        },
        {
            "lane": "future_controlled_loop_candidate",
            "must_call_wrapper_before": [
                "iteration_state_write",
                "iteration_proof_write",
                "iteration_memory_write",
                "loop_route_transition",
                "stop_condition_commit"
            ],
            "required": True
        },
        {
            "lane": "future_self_building_tick",
            "must_call_wrapper_before": [
                "quest_artifact_write",
                "delta_report_write",
                "self_improvement_proof_write",
                "memory_write",
                "route_update"
            ],
            "required": True
        },
        {
            "lane": "repair_lane",
            "must_call_wrapper_before": [
                "repair_artifact_write",
                "repair_proof_write",
                "repair_memory_write",
                "route_repair_commit"
            ],
            "required": True
        }
    ],
    "truth_boundary": truth_boundary
}

runner_obligations = {
    "id": "RUNTIME_RUNNER_WRAPPER_OBLIGATIONS_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "runner_must": [
        "load_CURRENT_ROUTE_AUTHORITY_before_execution",
        "verify_lawful_next_matches_runner_step",
        "call_idempotent_guard_enforced_wrapper_before_material_writes",
        "deny_direct_route_proof_memory_panel_pulse_progress_writes",
        "fail_closed_on_wrapper_rejection",
        "emit_wrapper_decision_in_proof",
        "call_effect_auditor_after_material_delta",
        "call_atomic_commit_for_route_transition"
    ],
    "runner_must_not": [
        "write_proof_without_wrapper",
        "write_memory_without_wrapper",
        "update_route_without_atomic_commit",
        "ignore_already_committed_noop",
        "continue_after_out_of_phase_block",
        "start_daemon",
        "install_scheduler",
        "enable_background_loop"
    ],
    "truth_boundary": truth_boundary
}

tick_obligations = {
    "id": "RUNTIME_TICK_WRAPPER_OBLIGATIONS_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "one_tick_must": [
        "declare_tick_scope",
        "declare_expected_current_lawful_next",
        "declare_allowed_task",
        "invoke_wrapper_before_task_result_writes",
        "record_guard_decision",
        "record_noop_if_already_committed",
        "block_out_of_phase_before_writes",
        "record_truth_boundary_flags_false"
    ],
    "one_tick_must_not": [
        "silently_widen_queue",
        "chain_unapproved_second_tick",
        "launch_background_continuation",
        "convert_one_tick_to_loop",
        "claim_daemon_or_24_7"
    ],
    "truth_boundary": truth_boundary
}

loop_obligations = {
    "id": "FUTURE_LOOP_WRAPPER_OBLIGATIONS_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "future_loop_must": [
        "be_defined_by_candidate_contract_first",
        "limit_max_iterations",
        "invoke_wrapper_before_each_iteration_write",
        "commit_each_iteration_through_atomic_commit",
        "record_iteration_proof_memory",
        "stop_fail_closed_on_wrapper_rejection",
        "not_mutate_route_directly",
        "not_run_as_daemon"
    ],
    "future_loop_must_not": [
        "start_without_contract_validation_review",
        "skip_wrapper_on_iterations",
        "become_infinite_loop",
        "become_scheduler",
        "become_background_daemon",
        "enable_network_autonomy_without_contract"
    ],
    "truth_boundary": truth_boundary
}

forbidden_runtime_bypass = {
    "id": "FORBIDDEN_RUNTIME_WRAPPER_BYPASS_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "forbidden": [
        "runtime_write_without_wrapper",
        "runner_write_without_wrapper",
        "tick_result_write_without_wrapper",
        "loop_iteration_write_without_wrapper",
        "repair_commit_without_wrapper",
        "direct_route_mutation_from_runtime",
        "direct_proof_memory_mutation_from_runtime",
        "atomic_commit_acceptance_without_material_route_effect",
        "effect_audit_acceptance_without_material_delta"
    ],
    "violation_result": "FAIL_CLOSED_BEFORE_WRITES",
    "truth_boundary": truth_boundary
}

fail_closed_policy = {
    "id": "RUNTIME_WRAPPER_FAIL_CLOSED_POLICY_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "fail_closed_when": [
        "current_lawful_next_mismatch",
        "upstream_proof_mismatch",
        "step_already_committed_and_not_noop_safe",
        "out_of_phase_rerun_detected",
        "missing_wrapper_decision",
        "direct_write_attempt_detected",
        "truth_boundary_flag_true",
        "effect_audit_material_delta_missing",
        "atomic_commit_material_route_effect_missing"
    ],
    "allowed_repair_classes": [
        "route_transition_repair_after_proof_pass",
        "commit_effect_repair_after_auditor_and_atomic_acceptance",
        "schema_bridge_repair_with_artifact_evidence",
        "canonical_route_path_repair_with_upstream_proof"
    ],
    "truth_boundary": truth_boundary
}

capability = (
    "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_BUILT"
    if status == "PASS"
    else "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_BLOCKED"
)

contract = {
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "source_mandatory_integration_review_proof": str(MANDATORY_REVIEW_PROOF),
    "source_mandatory_integration_validation_proof": str(MANDATORY_VALIDATION_PROOF),
    "source_wrapper_review_proof": str(WRAPPER_REVIEW_PROOF),
    "adoption_points": str(ADOPTION_POINTS),
    "runner_obligations": str(RUNNER_OBLIGATIONS),
    "tick_obligations": str(TICK_OBLIGATIONS),
    "future_loop_obligations": str(LOOP_OBLIGATIONS),
    "forbidden_runtime_bypass": str(FORBIDDEN_RUNTIME_BYPASS),
    "fail_closed_policy": str(FAIL_CLOSED_POLICY),

    "runtime_adoption_contract_built": status == "PASS",
    "runtime_lanes_must_adopt_wrapper": status == "PASS",
    "runtime_direct_writes_forbidden": status == "PASS",
    "runner_wrapper_invocation_required": status == "PASS",
    "tick_wrapper_invocation_required": status == "PASS",
    "future_loop_wrapper_invocation_required": status == "PASS",
    "runtime_fail_closed_policy_built": status == "PASS",

    "runtime_launch_approved": False,
    "runtime_execution_allowed": False,
    "runtime_autonomy_enabled": False,
    "loop_execution_started": False,
    "controlled_loop_enabled": False,
    "daemon_running": False,
    "scheduler_installed": False,
    "background_loop_enabled": False,
    "network_used": False,
    "queue_widening_allowed": False,
    "entity_birth_allowed": False,
    "anna_birth_allowed": False,
    "agi_claim_allowed": False,
    "final_canon_approval_allowed": False,

    "checks": checks,
    "hard_failures": hard,
    "real_next": NEXT if status == "PASS" else REPAIR,
    "truth_boundary": truth_boundary
}
contract["contract_hash"] = h24(contract)

proof = {
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "contract": str(CONTRACT),
    "contract_md": str(CONTRACT_MD),
    "adoption_points": str(ADOPTION_POINTS),
    "runner_obligations": str(RUNNER_OBLIGATIONS),
    "tick_obligations": str(TICK_OBLIGATIONS),
    "future_loop_obligations": str(LOOP_OBLIGATIONS),
    "forbidden_runtime_bypass": str(FORBIDDEN_RUNTIME_BYPASS),
    "fail_closed_policy": str(FAIL_CLOSED_POLICY),
    "memory": str(MEMORY),

    "runtime_adoption_contract_built": status == "PASS",
    "runtime_lanes_must_adopt_wrapper": status == "PASS",
    "runtime_direct_writes_forbidden": status == "PASS",
    "runner_wrapper_invocation_required": status == "PASS",
    "tick_wrapper_invocation_required": status == "PASS",
    "future_loop_wrapper_invocation_required": status == "PASS",
    "runtime_fail_closed_policy_built": status == "PASS",

    "runtime_launch_approved": False,
    "runtime_execution_allowed": False,
    "runtime_autonomy_enabled": False,
    "loop_execution_started": False,
    "controlled_loop_enabled": False,
    "daemon_running": False,
    "scheduler_installed": False,
    "background_loop_enabled": False,
    "network_used": False,
    "queue_widening_allowed": False,
    "entity_birth_allowed": False,
    "anna_birth_allowed": False,
    "agi_claim_allowed": False,
    "final_canon_approval_allowed": False,

    "checks": checks,
    "hard_failures": hard,
    "real_next": NEXT if status == "PASS" else REPAIR,
    "final_socc_status": (
        "SOCC_IDEMPOTENT_WRAPPER_RUNTIME_ADOPTION_CONTRACT_PASS_NOT_RUNTIME_NOT_LOOP_NOT_DAEMON"
        if status == "PASS"
        else "SOCC_IDEMPOTENT_WRAPPER_RUNTIME_ADOPTION_CONTRACT_FAIL"
    ),
    "truth_boundary": truth_boundary
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built runtime adoption contract for mandatory idempotent guard wrapper use in runner/tick/future-loop lanes. "
        "This defines runtime adoption obligations without launching runtime/loop/daemon."
        if status == "PASS"
        else "Runtime adoption contract build blocked."
    ),
    "contract": str(CONTRACT),
    "proof": str(PROOF),
    "real_next": NEXT if status == "PASS" else REPAIR,
    "truth_boundary": truth_boundary
}

md = "# IDEMPOTENT GUARD WRAPPER MANDATORY RUNTIME ADOPTION CONTRACT V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\n"
md += "Mandatory integration contract was review-sealed. Future material steps must use wrapper before writes.\n\n"
md += "## ДЕЙСТВИЕ\n\n"
md += "Built runtime adoption contract for runner/tick/future-loop lanes.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Runtime adoption contract is built. Runtime lanes now have defined wrapper adoption obligations, but runtime is not launched.\n\n"
else:
    md += "Runtime adoption contract build is blocked. Repair required.\n\n"
md += "## Runtime adoption points\n\n"
for ap in adoption_points["adoption_points"]:
    md += "- " + ap["lane"] + ": wrapper required before " + ", ".join(ap["must_call_wrapper_before"]) + "\n"
md += "\n## Explicitly NOT done\n\n"
for x in [
    "runtime not launched",
    "loop not executed",
    "controlled loop not enabled",
    "daemon not launched",
    "scheduler not installed",
    "background autonomy not enabled",
    "queue not widened",
    "Entity not born",
    "ANNA not born",
    "AGI not claimed",
    "final canon not approved",
]:
    md += "- " + x + "\n"
md += "\n## lawful_next\n\n"
md += (NEXT if status == "PASS" else REPAIR) + "\n\n"
md += "## Truth boundary\n\n"
md += truth_boundary + "\n"

write_json(ADOPTION_POINTS, adoption_points)
write_json(RUNNER_OBLIGATIONS, runner_obligations)
write_json(TICK_OBLIGATIONS, tick_obligations)
write_json(LOOP_OBLIGATIONS, loop_obligations)
write_json(FORBIDDEN_RUNTIME_BYPASS, forbidden_runtime_bypass)
write_json(FAIL_CLOSED_POLICY, fail_closed_policy)
write_json(CONTRACT, contract)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(CONTRACT_MD, md)

print("IDEMPOTENT GUARD WRAPPER MANDATORY RUNTIME ADOPTION CONTRACT BUILD :: " + status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + capability)
print("CONTRACT::" + str(CONTRACT))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("RUNTIME_ADOPTION_CONTRACT_BUILT::" + str(status == "PASS"))
print("RUNTIME_LANES_MUST_ADOPT_WRAPPER::" + str(status == "PASS"))
print("RUNTIME_DIRECT_WRITES_FORBIDDEN::" + str(status == "PASS"))
print("RUNNER_WRAPPER_INVOCATION_REQUIRED::" + str(status == "PASS"))
print("TICK_WRAPPER_INVOCATION_REQUIRED::" + str(status == "PASS"))
print("FUTURE_LOOP_WRAPPER_INVOCATION_REQUIRED::" + str(status == "PASS"))
print("RUNTIME_FAIL_CLOSED_POLICY_BUILT::" + str(status == "PASS"))
print("RUNTIME_LAUNCH_APPROVED::False")
print("RUNTIME_EXECUTION_ALLOWED::False")
print("RUNTIME_AUTONOMY_ENABLED::False")
print("LOOP_EXECUTION_STARTED::False")
print("CONTROLLED_LOOP_ENABLED::False")
print("DAEMON_RUNNING::False")
print("SCHEDULER_INSTALLED::False")
print("BACKGROUND_LOOP_ENABLED::False")
print("NETWORK_USED::False")
print("QUEUE_WIDENING_ALLOWED::False")
print("ENTITY_BIRTH_ALLOWED::False")
print("ANNA_BIRTH_ALLOWED::False")
print("AGI_CLAIM_ALLOWED::False")
print("FINAL_CANON_APPROVAL_ALLOWED::False")
print("REAL_NEXT::" + (NEXT if status == "PASS" else REPAIR))
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if status == "PASS" else 1)

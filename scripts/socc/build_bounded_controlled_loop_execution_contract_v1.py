import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "build_bounded_controlled_loop_execution_contract_v1"
NEXT = "validate_bounded_controlled_loop_execution_contract_v1"
REPAIR = "repair_bounded_controlled_loop_execution_contract_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

CANDIDATE_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_V1_PROOF.json"
CANDIDATE_REVIEW_ROUTE_REPAIR_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CONTROLLED_LOOP_CANDIDATE_REVIEW_ROUTE_TRANSITION_REPAIR_V1_PROOF.json"
CANDIDATE_VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CONTROLLED_LOOP_CANDIDATE_CONTRACT_VALIDATION_V1_PROOF.json"
ENFORCEMENT_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_V1_PROOF.json"

CANDIDATE_BASE = ROOT / "core/socc/controlled_loop/candidate_contract"
CANDIDATE_CONTRACT = CANDIDATE_BASE / "CONTROLLED_LOOP_CANDIDATE_CONTRACT_V1.json"
CANDIDATE_BOUNDARIES = CANDIDATE_BASE / "CONTROLLED_LOOP_CANDIDATE_BOUNDARIES_V1.json"
CANDIDATE_ITERATION_RULES = CANDIDATE_BASE / "CONTROLLED_LOOP_CANDIDATE_ITERATION_RULES_V1.json"
CANDIDATE_OBSERVABILITY = CANDIDATE_BASE / "CONTROLLED_LOOP_CANDIDATE_OBSERVABILITY_V1.json"
CANDIDATE_STOP_CONDITIONS = CANDIDATE_BASE / "CONTROLLED_LOOP_CANDIDATE_STOP_CONDITIONS_V1.json"
CANDIDATE_REPAIR_CONDITIONS = CANDIDATE_BASE / "CONTROLLED_LOOP_CANDIDATE_REPAIR_CONDITIONS_V1.json"
CANDIDATE_FORBIDDEN_CLAIMS = CANDIDATE_BASE / "CONTROLLED_LOOP_CANDIDATE_FORBIDDEN_CLAIMS_V1.json"

BASE = ROOT / "core/socc/controlled_loop/bounded_execution_contract"
CONTRACT = BASE / "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_V1.json"
CONTRACT_MD = BASE / "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_V1.md"
EXECUTION_BOUNDARIES = BASE / "BOUNDED_CONTROLLED_LOOP_EXECUTION_BOUNDARIES_V1.json"
ITERATION_PROTOCOL = BASE / "BOUNDED_CONTROLLED_LOOP_ITERATION_PROTOCOL_V1.json"
EXECUTION_OBSERVABILITY = BASE / "BOUNDED_CONTROLLED_LOOP_EXECUTION_OBSERVABILITY_V1.json"
EXECUTION_STOP_POLICY = BASE / "BOUNDED_CONTROLLED_LOOP_EXECUTION_STOP_POLICY_V1.json"
EXECUTION_REPAIR_POLICY = BASE / "BOUNDED_CONTROLLED_LOOP_EXECUTION_REPAIR_POLICY_V1.json"
NO_DAEMON_GUARD = BASE / "BOUNDED_CONTROLLED_LOOP_NO_DAEMON_GUARD_V1.json"
EXECUTION_TRUTH_BOUNDARY = BASE / "BOUNDED_CONTROLLED_LOOP_EXECUTION_TRUTH_BOUNDARY_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/controlled_loop/BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_V1_MEMORY.json"

FORBIDDEN_FLAGS = [
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
]

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

candidate_review = read_json(CANDIDATE_REVIEW_PROOF)
candidate_review_repair = read_json(CANDIDATE_REVIEW_ROUTE_REPAIR_PROOF)
candidate_validation = read_json(CANDIDATE_VALIDATION_PROOF)
enforcement_review = read_json(ENFORCEMENT_REVIEW_PROOF)

candidate_contract = read_json(CANDIDATE_CONTRACT)
candidate_boundaries = read_json(CANDIDATE_BOUNDARIES)
candidate_iteration_rules = read_json(CANDIDATE_ITERATION_RULES)
candidate_observability = read_json(CANDIDATE_OBSERVABILITY)
candidate_stop = read_json(CANDIDATE_STOP_CONDITIONS)
candidate_repair = read_json(CANDIDATE_REPAIR_CONDITIONS)
candidate_forbidden = read_json(CANDIDATE_FORBIDDEN_CLAIMS)

truth_boundary = (
    "Execution contract build only. This builds a bounded controlled loop execution contract, but does not execute "
    "the loop, does not launch runtime, does not enable controlled loop, does not start daemon/scheduler/background "
    "autonomy, does not widen queue, does not birth Entity/ANNA, does not approve final canon, and does not claim AGI."
)

checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_ok": get_next(route) == EXPECTED_CURRENT,
    "route_upstream_points_to_candidate_review_proof": route.get("upstream_proof") == str(CANDIDATE_REVIEW_PROOF),

    "candidate_review_proof_exists": CANDIDATE_REVIEW_PROOF.exists(),
    "candidate_review_status_pass": status_pass(candidate_review),
    "candidate_review_capability_ok": candidate_review.get("capability") == "CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_SEALED",
    "candidate_review_real_next_ok": get_next(candidate_review) == EXPECTED_CURRENT,
    "candidate_review_hard_failures_empty": candidate_review.get("hard_failures") == [],

    "candidate_contract_review_sealed": candidate_review.get("controlled_loop_candidate_contract_review_sealed") is True,
    "candidate_contract_validated": candidate_review.get("controlled_loop_candidate_contract_validated") is True,
    "bounded_loop_candidate_reviewed": candidate_review.get("bounded_loop_candidate_reviewed") is True,
    "max_iterations_reviewed": candidate_review.get("max_iterations_reviewed") is True,
    "per_iteration_wrapper_required_reviewed": candidate_review.get("per_iteration_wrapper_required_reviewed") is True,
    "per_iteration_compliance_proof_required_reviewed": candidate_review.get("per_iteration_compliance_proof_required_reviewed") is True,
    "per_iteration_effect_audit_required_reviewed": candidate_review.get("per_iteration_effect_audit_required_reviewed") is True,
    "per_iteration_atomic_commit_required_if_route_transition_reviewed": candidate_review.get("per_iteration_atomic_commit_required_if_route_transition_reviewed") is True,
    "stop_conditions_reviewed": candidate_review.get("stop_conditions_reviewed") is True,
    "repair_conditions_reviewed": candidate_review.get("repair_conditions_reviewed") is True,
    "truth_boundary_reviewed": candidate_review.get("truth_boundary_reviewed") is True,
    "bounded_loop_execution_contract_required_next": candidate_review.get("bounded_loop_execution_contract_required_next") is True,

    "candidate_review_route_repair_proof_exists": CANDIDATE_REVIEW_ROUTE_REPAIR_PROOF.exists(),
    "candidate_review_route_repair_status_pass": status_pass(candidate_review_repair),
    "candidate_review_route_repair_updated_to_build": candidate_review_repair.get("route_lawful_next_updated_to_bounded_execution_contract_build") is True,
    "candidate_review_route_repair_upstream_ok": candidate_review_repair.get("route_upstream_points_to_review_proof") is True,

    "candidate_validation_proof_exists": CANDIDATE_VALIDATION_PROOF.exists(),
    "candidate_validation_status_pass": status_pass(candidate_validation),
    "candidate_validation_ready_for_review": candidate_validation.get("ready_for_review") is True,

    "enforcement_review_proof_exists": ENFORCEMENT_REVIEW_PROOF.exists(),
    "enforcement_review_status_pass": status_pass(enforcement_review),
    "enforcement_review_sealed": enforcement_review.get("guarded_runtime_adoption_enforcement_lane_review_sealed") is True,

    "candidate_contract_exists": CANDIDATE_CONTRACT.exists(),
    "candidate_boundaries_exists": CANDIDATE_BOUNDARIES.exists(),
    "candidate_iteration_rules_exists": CANDIDATE_ITERATION_RULES.exists(),
    "candidate_observability_exists": CANDIDATE_OBSERVABILITY.exists(),
    "candidate_stop_conditions_exists": CANDIDATE_STOP_CONDITIONS.exists(),
    "candidate_repair_conditions_exists": CANDIDATE_REPAIR_CONDITIONS.exists(),
    "candidate_forbidden_claims_exists": CANDIDATE_FORBIDDEN_CLAIMS.exists(),

    "candidate_contract_status_built": candidate_contract.get("status") == "BUILT",
    "candidate_max_iterations_3": candidate_boundaries.get("max_iterations_candidate") == 3,
    "candidate_allowed_mode_bounded_candidate_only": candidate_boundaries.get("allowed_execution_mode") == "bounded_candidate_only",
    "candidate_stop_mode_fail_closed": candidate_stop.get("stop_mode") == "fail_closed",

    "build_does_not_execute_loop": True,
    "build_does_not_execute_tick": True,
    "build_does_not_launch_runtime": True,
    "build_does_not_launch_daemon": True,
    "build_does_not_install_scheduler": True,
    "build_does_not_enable_background": True,
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
    ("candidate_review", candidate_review),
    ("candidate_contract", candidate_contract),
]:
    for key in FORBIDDEN_FLAGS:
        checks[f"{label}_{key}_false_or_absent"] = false_or_absent(obj, key)

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

execution_boundaries = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_BOUNDARIES_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "execution_mode": "bounded_contract_only",
    "max_iterations": 3,
    "iteration_indices_allowed": [1, 2, 3],
    "required_stop_after_max_iterations": True,
    "no_background_continuation": True,
    "no_self_scheduling": True,
    "no_daemonization": True,
    "no_unbounded_recursion": True,
    "truth_boundary": truth_boundary,
}

iteration_protocol = {
    "id": "BOUNDED_CONTROLLED_LOOP_ITERATION_PROTOCOL_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "each_iteration_must": [
        "declare_iteration_index",
        "declare_loop_contract_id",
        "load_current_route_authority",
        "verify_lawful_next_matches_declared_iteration_step",
        "verify_upstream_proof",
        "invoke_idempotent_guard_wrapper_before_material_writes",
        "produce_runtime_adoption_compliance_proof",
        "run_bypass_detector",
        "record_effect_audit_result",
        "record_atomic_commit_result_if_route_transition",
        "verify_material_route_effect_if_route_transition",
        "write_iteration_memory",
        "update_panel_pulse_progress",
        "evaluate_stop_conditions",
        "emit_iteration_proof"
    ],
    "each_iteration_must_not": [
        "write_without_wrapper",
        "skip_compliance_proof",
        "skip_effect_audit",
        "skip_atomic_commit_on_route_transition",
        "continue_after_stop_condition",
        "spawn_background_process",
        "install_scheduler",
        "widen_queue",
        "claim_runtime_autonomy",
        "claim_agi"
    ],
    "truth_boundary": truth_boundary,
}

execution_observability = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_OBSERVABILITY_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "loop_execution_later_must_emit": [
        "bounded_loop_execution_contract_id",
        "iteration_count",
        "iteration_index",
        "current_lawful_next_before_iteration",
        "current_lawful_next_after_iteration",
        "wrapper_decision",
        "bypass_detector_result",
        "compliance_proof",
        "effect_audit_result",
        "atomic_commit_result",
        "material_route_effect_result",
        "stop_condition_result",
        "repair_condition_result",
        "truth_boundary_flags",
        "hard_failures"
    ],
    "contract_build_emits_execution": False,
    "truth_boundary": truth_boundary,
}

execution_stop_policy = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_STOP_POLICY_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "stop_on": [
        "iteration_count_reaches_3",
        "lawful_next_mismatch",
        "upstream_proof_mismatch",
        "wrapper_rejection",
        "bypass_detected",
        "missing_compliance_proof",
        "effect_audit_failure",
        "atomic_commit_failure",
        "missing_material_route_effect",
        "panel_pulse_progress_incoherence",
        "truth_boundary_violation",
        "unknown_iteration_task",
        "unapproved_queue_widening_attempt"
    ],
    "stop_result": "fail_closed_no_background_continuation",
    "truth_boundary": truth_boundary,
}

execution_repair_policy = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_REPAIR_POLICY_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "repair_allowed_only_for": [
        "proof_pass_but_route_transition_missing",
        "atomic_commit_accepted_but_material_route_effect_missing",
        "schema_drift_against_newer_reviewed_contract",
        "panel_pulse_progress_incoherence_with_valid_route_and_proof"
    ],
    "repair_forbidden_for": [
        "truth_boundary_violation",
        "daemon_started",
        "scheduler_installed",
        "background_loop_enabled",
        "loop_executed_without_execution_contract_review",
        "direct_write_without_wrapper",
        "missing_effect_audit",
        "Entity_or_ANNA_birth_claim",
        "AGI_claim"
    ],
    "truth_boundary": truth_boundary,
}

no_daemon_guard = {
    "id": "BOUNDED_CONTROLLED_LOOP_NO_DAEMON_GUARD_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "forbidden": [
        "daemon_process",
        "scheduler_registration",
        "background_loop",
        "watchdog_autorun",
        "self_rescheduling",
        "infinite_loop",
        "network_autonomy",
        "queue_widening_without_contract"
    ],
    "enforcement": "hard_fail_before_execution",
    "truth_boundary": truth_boundary,
}

execution_truth_boundary = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_TRUTH_BOUNDARY_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "explicit_false_claims": {
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
        "final_canon_approval_allowed": False
    },
    "allowed_claim": "bounded_controlled_loop_execution_contract_built_only_if_proof_pass",
    "truth_boundary": truth_boundary,
}

capability = (
    "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_BUILT"
    if status == "PASS"
    else "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_BLOCKED"
)

contract = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,

    "source_candidate_review_proof": str(CANDIDATE_REVIEW_PROOF),
    "source_candidate_review_route_repair_proof": str(CANDIDATE_REVIEW_ROUTE_REPAIR_PROOF),
    "source_candidate_validation_proof": str(CANDIDATE_VALIDATION_PROOF),
    "source_enforcement_review_proof": str(ENFORCEMENT_REVIEW_PROOF),

    "execution_boundaries": str(EXECUTION_BOUNDARIES),
    "iteration_protocol": str(ITERATION_PROTOCOL),
    "execution_observability": str(EXECUTION_OBSERVABILITY),
    "execution_stop_policy": str(EXECUTION_STOP_POLICY),
    "execution_repair_policy": str(EXECUTION_REPAIR_POLICY),
    "no_daemon_guard": str(NO_DAEMON_GUARD),
    "execution_truth_boundary": str(EXECUTION_TRUTH_BOUNDARY),

    "bounded_controlled_loop_execution_contract_built": status == "PASS",
    "bounded_execution_protocol_defined": status == "PASS",
    "max_iterations_3_defined": status == "PASS",
    "iteration_protocol_defined": status == "PASS",
    "per_iteration_wrapper_required": status == "PASS",
    "per_iteration_compliance_proof_required": status == "PASS",
    "per_iteration_effect_audit_required": status == "PASS",
    "per_iteration_atomic_commit_required_if_route_transition": status == "PASS",
    "stop_after_3_required": status == "PASS",
    "no_daemon_guard_built": status == "PASS",
    "execution_truth_boundary_built": status == "PASS",

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
    "truth_boundary": truth_boundary,
}
contract["contract_hash"] = h24(contract)

proof = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "contract": str(CONTRACT),
    "contract_md": str(CONTRACT_MD),
    "execution_boundaries": str(EXECUTION_BOUNDARIES),
    "iteration_protocol": str(ITERATION_PROTOCOL),
    "execution_observability": str(EXECUTION_OBSERVABILITY),
    "execution_stop_policy": str(EXECUTION_STOP_POLICY),
    "execution_repair_policy": str(EXECUTION_REPAIR_POLICY),
    "no_daemon_guard": str(NO_DAEMON_GUARD),
    "execution_truth_boundary": str(EXECUTION_TRUTH_BOUNDARY),
    "memory": str(MEMORY),

    "bounded_controlled_loop_execution_contract_built": status == "PASS",
    "bounded_execution_protocol_defined": status == "PASS",
    "max_iterations_3_defined": status == "PASS",
    "iteration_protocol_defined": status == "PASS",
    "per_iteration_wrapper_required": status == "PASS",
    "per_iteration_compliance_proof_required": status == "PASS",
    "per_iteration_effect_audit_required": status == "PASS",
    "per_iteration_atomic_commit_required_if_route_transition": status == "PASS",
    "stop_after_3_required": status == "PASS",
    "no_daemon_guard_built": status == "PASS",
    "execution_truth_boundary_built": status == "PASS",

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
        "SOCC_BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_BUILD_PASS_NOT_LOOP_EXECUTION_NOT_DAEMON"
        if status == "PASS"
        else "SOCC_BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_BUILD_FAIL"
    ),
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built bounded controlled loop execution contract. This is contract only: no loop execution, no runtime launch, no daemon."
        if status == "PASS"
        else "Bounded controlled loop execution contract build blocked."
    ),
    "contract": str(CONTRACT),
    "proof": str(PROOF),
    "real_next": NEXT if status == "PASS" else REPAIR,
    "truth_boundary": truth_boundary,
}

md = "# BOUNDED CONTROLLED LOOP EXECUTION CONTRACT V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nControlled loop candidate contract was review-sealed and route was repaired to bounded execution contract build.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt bounded controlled loop execution contract. This is not loop execution.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Bounded controlled loop execution contract is built. Next step: validate the execution contract.\n\n"
else:
    md += "Bounded controlled loop execution contract build is blocked. Repair required.\n\n"
md += "## Explicitly NOT done\n\n"
for x in [
    "runtime not launched",
    "tick not executed",
    "loop not executed",
    "controlled loop not enabled",
    "daemon not launched",
    "scheduler not installed",
    "background autonomy not enabled",
    "network not used",
    "queue not widened",
    "Entity not born",
    "ANNA not born",
    "AGI not claimed",
    "final canon not approved",
]:
    md += "- " + x + "\n"
md += "\n## lawful_next\n\n" + (NEXT if status == "PASS" else REPAIR) + "\n\n"
md += "## Truth boundary\n\n" + truth_boundary + "\n"

write_json(EXECUTION_BOUNDARIES, execution_boundaries)
write_json(ITERATION_PROTOCOL, iteration_protocol)
write_json(EXECUTION_OBSERVABILITY, execution_observability)
write_json(EXECUTION_STOP_POLICY, execution_stop_policy)
write_json(EXECUTION_REPAIR_POLICY, execution_repair_policy)
write_json(NO_DAEMON_GUARD, no_daemon_guard)
write_json(EXECUTION_TRUTH_BOUNDARY, execution_truth_boundary)
write_json(CONTRACT, contract)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(CONTRACT_MD, md)

print("BOUNDED CONTROLLED LOOP EXECUTION CONTRACT BUILD :: " + status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + capability)
print("CONTRACT::" + str(CONTRACT))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_BUILT::" + str(status == "PASS"))
print("BOUNDED_EXECUTION_PROTOCOL_DEFINED::" + str(status == "PASS"))
print("MAX_ITERATIONS_3_DEFINED::" + str(status == "PASS"))
print("ITERATION_PROTOCOL_DEFINED::" + str(status == "PASS"))
print("PER_ITERATION_WRAPPER_REQUIRED::" + str(status == "PASS"))
print("PER_ITERATION_COMPLIANCE_PROOF_REQUIRED::" + str(status == "PASS"))
print("PER_ITERATION_EFFECT_AUDIT_REQUIRED::" + str(status == "PASS"))
print("PER_ITERATION_ATOMIC_COMMIT_REQUIRED_IF_ROUTE_TRANSITION::" + str(status == "PASS"))
print("STOP_AFTER_3_REQUIRED::" + str(status == "PASS"))
print("NO_DAEMON_GUARD_BUILT::" + str(status == "PASS"))
print("EXECUTION_TRUTH_BOUNDARY_BUILT::" + str(status == "PASS"))
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

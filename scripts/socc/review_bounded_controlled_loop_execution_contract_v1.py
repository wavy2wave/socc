import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "review_bounded_controlled_loop_execution_contract_v1"
NEXT = "build_bounded_controlled_loop_execution_step_v1"
REPAIR = "repair_review_bounded_controlled_loop_execution_contract_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_VALIDATION_V1_PROOF.json"
VALIDATION_ROUTE_REPAIR_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_ROUTE_TRANSITION_REPAIR_V1_PROOF.json"
BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_V1_PROOF.json"
CANDIDATE_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_V1_PROOF.json"

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

REVIEW_DIR = BASE / "review"
REVIEW = REVIEW_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_V1.json"
REVIEW_MD = REVIEW_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/controlled_loop/BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_V1_MEMORY.json"

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

validation = read_json(VALIDATION_PROOF)
validation_repair = read_json(VALIDATION_ROUTE_REPAIR_PROOF)
build = read_json(BUILD_PROOF)
candidate_review = read_json(CANDIDATE_REVIEW_PROOF)
contract = read_json(CONTRACT)

boundaries = read_json(EXECUTION_BOUNDARIES)
iteration_protocol = read_json(ITERATION_PROTOCOL)
observability = read_json(EXECUTION_OBSERVABILITY)
stop_policy = read_json(EXECUTION_STOP_POLICY)
repair_policy = read_json(EXECUTION_REPAIR_POLICY)
no_daemon_guard = read_json(NO_DAEMON_GUARD)
execution_truth = read_json(EXECUTION_TRUTH_BOUNDARY)

truth_boundary = (
    "Review-seal only. This review-seals bounded controlled loop execution contract. "
    "It does not execute loop, does not execute tick, does not launch runtime, does not enable controlled loop, "
    "does not start daemon/scheduler/background autonomy, does not widen queue, does not birth Entity/ANNA, "
    "does not approve final canon, and does not claim AGI. "
    "After this review-seal, lawful next is build bounded controlled loop execution step only."
)

checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_ok": get_next(route) == EXPECTED_CURRENT,
    "route_upstream_points_to_validation_proof": route.get("upstream_proof") == str(VALIDATION_PROOF),

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": status_pass(validation),
    "validation_capability_ok": validation.get("capability") == "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_VALIDATED",
    "validation_real_next_ok": get_next(validation) == EXPECTED_CURRENT,
    "validation_hard_failures_empty": validation.get("hard_failures") == [],
    "validation_ready_for_review": validation.get("ready_for_review") is True,

    "bounded_controlled_loop_execution_contract_validated": validation.get("bounded_controlled_loop_execution_contract_validated") is True,
    "bounded_execution_protocol_validated": validation.get("bounded_execution_protocol_validated") is True,
    "max_iterations_3_validated": validation.get("max_iterations_3_validated") is True,
    "iteration_protocol_validated": validation.get("iteration_protocol_validated") is True,
    "per_iteration_wrapper_required_validated": validation.get("per_iteration_wrapper_required_validated") is True,
    "per_iteration_compliance_proof_required_validated": validation.get("per_iteration_compliance_proof_required_validated") is True,
    "per_iteration_effect_audit_required_validated": validation.get("per_iteration_effect_audit_required_validated") is True,
    "per_iteration_atomic_commit_required_if_route_transition_validated": validation.get("per_iteration_atomic_commit_required_if_route_transition_validated") is True,
    "stop_after_3_validated": validation.get("stop_after_3_validated") is True,
    "no_daemon_guard_validated": validation.get("no_daemon_guard_validated") is True,
    "execution_truth_boundary_validated": validation.get("execution_truth_boundary_validated") is True,

    "validation_route_repair_proof_exists": VALIDATION_ROUTE_REPAIR_PROOF.exists(),
    "validation_route_repair_status_pass": status_pass(validation_repair),
    "validation_route_repair_updated_to_review": validation_repair.get("route_lawful_next_updated_to_review") is True,
    "validation_route_repair_upstream_ok": validation_repair.get("route_upstream_points_to_validation_proof") is True,

    "build_proof_exists": BUILD_PROOF.exists(),
    "build_status_pass": status_pass(build),
    "build_contract_built": build.get("bounded_controlled_loop_execution_contract_built") is True,

    "candidate_review_proof_exists": CANDIDATE_REVIEW_PROOF.exists(),
    "candidate_review_status_pass": status_pass(candidate_review),
    "candidate_review_sealed": candidate_review.get("controlled_loop_candidate_contract_review_sealed") is True,

    "contract_exists": CONTRACT.exists(),
    "contract_md_exists": CONTRACT_MD.exists(),
    "execution_boundaries_exists": EXECUTION_BOUNDARIES.exists(),
    "iteration_protocol_exists": ITERATION_PROTOCOL.exists(),
    "execution_observability_exists": EXECUTION_OBSERVABILITY.exists(),
    "execution_stop_policy_exists": EXECUTION_STOP_POLICY.exists(),
    "execution_repair_policy_exists": EXECUTION_REPAIR_POLICY.exists(),
    "no_daemon_guard_exists": NO_DAEMON_GUARD.exists(),
    "execution_truth_boundary_exists": EXECUTION_TRUTH_BOUNDARY.exists(),

    "contract_status_built": contract.get("status") == "BUILT",
    "contract_built": contract.get("bounded_controlled_loop_execution_contract_built") is True,
    "bounded_execution_protocol_defined": contract.get("bounded_execution_protocol_defined") is True,
    "max_iterations_3_defined": contract.get("max_iterations_3_defined") is True,
    "iteration_protocol_defined": contract.get("iteration_protocol_defined") is True,
    "per_iteration_wrapper_required": contract.get("per_iteration_wrapper_required") is True,
    "per_iteration_compliance_proof_required": contract.get("per_iteration_compliance_proof_required") is True,
    "per_iteration_effect_audit_required": contract.get("per_iteration_effect_audit_required") is True,
    "per_iteration_atomic_commit_required_if_route_transition": contract.get("per_iteration_atomic_commit_required_if_route_transition") is True,
    "stop_after_3_required": contract.get("stop_after_3_required") is True,
    "no_daemon_guard_built": contract.get("no_daemon_guard_built") is True,
    "execution_truth_boundary_built": contract.get("execution_truth_boundary_built") is True,

    "boundaries_execution_mode_contract_only": boundaries.get("execution_mode") == "bounded_contract_only",
    "boundaries_max_iterations_3": boundaries.get("max_iterations") == 3,
    "boundaries_stop_after_max": boundaries.get("required_stop_after_max_iterations") is True,
    "boundaries_no_background": boundaries.get("no_background_continuation") is True,
    "boundaries_no_self_scheduling": boundaries.get("no_self_scheduling") is True,
    "boundaries_no_daemonization": boundaries.get("no_daemonization") is True,
    "boundaries_no_unbounded_recursion": boundaries.get("no_unbounded_recursion") is True,

    "stop_result_fail_closed": stop_policy.get("stop_result") == "fail_closed_no_background_continuation",
    "no_daemon_enforcement_hard_fail": no_daemon_guard.get("enforcement") == "hard_fail_before_execution",
    "execution_truth_allowed_claim": execution_truth.get("allowed_claim") == "bounded_controlled_loop_execution_contract_built_only_if_proof_pass",

    "review_does_not_execute_loop": True,
    "review_does_not_execute_tick": True,
    "review_does_not_launch_runtime": True,
    "review_does_not_enable_controlled_loop": True,
    "review_does_not_launch_daemon": True,
    "review_does_not_install_scheduler": True,
    "review_does_not_enable_background": True,
    "review_does_not_widen_queue": True,
    "review_does_not_birth_entity": True,
    "review_does_not_birth_anna": True,
    "review_does_not_claim_agi": True,
}

for label, obj in [
    ("route", route),
    ("panel", panel),
    ("pulse", pulse),
    ("progress", progress),
    ("validation", validation),
    ("contract", contract),
]:
    for key in FORBIDDEN_FLAGS:
        checks[f"{label}_{key}_false_or_absent"] = false_or_absent(obj, key)

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

capability = (
    "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_SEALED"
    if status == "PASS"
    else "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_BLOCKED"
)

real_next = NEXT if status == "PASS" else REPAIR

review = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "REVIEW_SEALED" if status == "PASS" else "BLOCKED",
    "capability": capability,

    "source_validation_proof": str(VALIDATION_PROOF),
    "source_validation_route_repair_proof": str(VALIDATION_ROUTE_REPAIR_PROOF),
    "source_build_proof": str(BUILD_PROOF),
    "source_candidate_review_proof": str(CANDIDATE_REVIEW_PROOF),
    "source_contract": str(CONTRACT),

    "bounded_controlled_loop_execution_contract_review_sealed": status == "PASS",
    "bounded_controlled_loop_execution_contract_validated": status == "PASS",
    "bounded_execution_protocol_reviewed": status == "PASS",
    "max_iterations_3_reviewed": status == "PASS",
    "iteration_protocol_reviewed": status == "PASS",
    "per_iteration_wrapper_required_reviewed": status == "PASS",
    "per_iteration_compliance_proof_required_reviewed": status == "PASS",
    "per_iteration_effect_audit_required_reviewed": status == "PASS",
    "per_iteration_atomic_commit_required_if_route_transition_reviewed": status == "PASS",
    "stop_after_3_reviewed": status == "PASS",
    "no_daemon_guard_reviewed": status == "PASS",
    "execution_truth_boundary_reviewed": status == "PASS",

    "bounded_loop_execution_step_required_next": status == "PASS",

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
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}
review["review_hash"] = h24(review)

proof = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "bounded_controlled_loop_execution_contract_review_sealed": status == "PASS",
    "bounded_controlled_loop_execution_contract_validated": status == "PASS",
    "bounded_execution_protocol_reviewed": status == "PASS",
    "max_iterations_3_reviewed": status == "PASS",
    "iteration_protocol_reviewed": status == "PASS",
    "per_iteration_wrapper_required_reviewed": status == "PASS",
    "per_iteration_compliance_proof_required_reviewed": status == "PASS",
    "per_iteration_effect_audit_required_reviewed": status == "PASS",
    "per_iteration_atomic_commit_required_if_route_transition_reviewed": status == "PASS",
    "stop_after_3_reviewed": status == "PASS",
    "no_daemon_guard_reviewed": status == "PASS",
    "execution_truth_boundary_reviewed": status == "PASS",

    "bounded_loop_execution_step_required_next": status == "PASS",

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
    "real_next": real_next,
    "final_socc_status": (
        "SOCC_BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_PASS_EXECUTION_STEP_NEXT_NOT_LOOP_NOT_DAEMON"
        if status == "PASS"
        else "SOCC_BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_FAIL"
    ),
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed bounded controlled loop execution contract. Next is bounded loop execution step build only. "
        "No loop execution, no runtime launch, no daemon."
        if status == "PASS"
        else "Bounded controlled loop execution contract review blocked."
    ),
    "review": str(REVIEW),
    "proof": str(PROOF),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

md = "# BOUNDED CONTROLLED LOOP EXECUTION CONTRACT REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nBounded controlled loop execution contract was built and validated.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed bounded controlled loop execution contract. This is not loop execution.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Bounded controlled loop execution contract is review-sealed. Next lawful layer: bounded loop execution step build.\n\n"
else:
    md += "Bounded controlled loop execution contract review is blocked. Repair required.\n\n"
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
md += "\n## lawful_next\n\n" + real_next + "\n\n"
md += "## Truth boundary\n\n" + truth_boundary + "\n"

write_json(REVIEW, review)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(REVIEW_MD, md)

print("BOUNDED CONTROLLED LOOP EXECUTION CONTRACT REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_SEALED::" + str(status == "PASS"))
print("BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_VALIDATED::" + str(status == "PASS"))
print("BOUNDED_EXECUTION_PROTOCOL_REVIEWED::" + str(status == "PASS"))
print("MAX_ITERATIONS_3_REVIEWED::" + str(status == "PASS"))
print("ITERATION_PROTOCOL_REVIEWED::" + str(status == "PASS"))
print("PER_ITERATION_WRAPPER_REQUIRED_REVIEWED::" + str(status == "PASS"))
print("PER_ITERATION_COMPLIANCE_PROOF_REQUIRED_REVIEWED::" + str(status == "PASS"))
print("PER_ITERATION_EFFECT_AUDIT_REQUIRED_REVIEWED::" + str(status == "PASS"))
print("PER_ITERATION_ATOMIC_COMMIT_REQUIRED_IF_ROUTE_TRANSITION_REVIEWED::" + str(status == "PASS"))
print("STOP_AFTER_3_REVIEWED::" + str(status == "PASS"))
print("NO_DAEMON_GUARD_REVIEWED::" + str(status == "PASS"))
print("EXECUTION_TRUTH_BOUNDARY_REVIEWED::" + str(status == "PASS"))
print("BOUNDED_LOOP_EXECUTION_STEP_REQUIRED_NEXT::" + str(status == "PASS"))
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
print("REAL_NEXT::" + real_next)
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if status == "PASS" else 1)

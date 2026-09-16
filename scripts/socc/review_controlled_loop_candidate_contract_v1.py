import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "review_controlled_loop_candidate_contract_v1"
NEXT = "build_bounded_controlled_loop_execution_contract_v1"
REPAIR = "repair_review_controlled_loop_candidate_contract_schema_or_route_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CONTROLLED_LOOP_CANDIDATE_CONTRACT_VALIDATION_V1_PROOF.json"
VALIDATION_ROUTE_REPAIR_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CONTROLLED_LOOP_CANDIDATE_VALIDATION_ROUTE_TRANSITION_REPAIR_V1_PROOF.json"
BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CONTROLLED_LOOP_CANDIDATE_CONTRACT_V1_PROOF.json"
ENFORCEMENT_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_V1_PROOF.json"

BASE = ROOT / "core/socc/controlled_loop/candidate_contract"
CONTRACT = BASE / "CONTROLLED_LOOP_CANDIDATE_CONTRACT_V1.json"
CONTRACT_MD = BASE / "CONTROLLED_LOOP_CANDIDATE_CONTRACT_V1.md"
BOUNDARIES = BASE / "CONTROLLED_LOOP_CANDIDATE_BOUNDARIES_V1.json"
ITERATION_RULES = BASE / "CONTROLLED_LOOP_CANDIDATE_ITERATION_RULES_V1.json"
OBSERVABILITY = BASE / "CONTROLLED_LOOP_CANDIDATE_OBSERVABILITY_V1.json"
STOP_CONDITIONS = BASE / "CONTROLLED_LOOP_CANDIDATE_STOP_CONDITIONS_V1.json"
REPAIR_CONDITIONS = BASE / "CONTROLLED_LOOP_CANDIDATE_REPAIR_CONDITIONS_V1.json"
FORBIDDEN_CLAIMS = BASE / "CONTROLLED_LOOP_CANDIDATE_FORBIDDEN_CLAIMS_V1.json"

REVIEW_DIR = BASE / "review"
REVIEW = REVIEW_DIR / "CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_V1.json"
REVIEW_MD = REVIEW_DIR / "CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/controlled_loop/CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_V1_MEMORY.json"

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
enforcement_review = read_json(ENFORCEMENT_REVIEW_PROOF)

contract = read_json(CONTRACT)
boundaries = read_json(BOUNDARIES)
iteration_rules = read_json(ITERATION_RULES)
observability = read_json(OBSERVABILITY)
stop_conditions = read_json(STOP_CONDITIONS)
repair_conditions = read_json(REPAIR_CONDITIONS)
forbidden_claims = read_json(FORBIDDEN_CLAIMS)

truth_boundary = (
    "Review-seal only. This review-seals the validated controlled loop candidate contract. "
    "It does not execute a loop, does not execute a tick, does not launch runtime, does not start daemon/scheduler/"
    "background autonomy, does not widen queue, does not birth Entity/ANNA, does not approve final canon, and does not claim AGI. "
    "After this review-seal, the lawful next architectural layer is bounded controlled loop execution contract build only."
)

checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_ok": get_next(route) == EXPECTED_CURRENT,
    "route_upstream_points_to_validation_proof": route.get("upstream_proof") == str(VALIDATION_PROOF),

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": status_pass(validation),
    "validation_capability_ok": validation.get("capability") == "CONTROLLED_LOOP_CANDIDATE_CONTRACT_VALIDATED",
    "validation_real_next_ok": get_next(validation) == EXPECTED_CURRENT,
    "validation_hard_failures_empty": validation.get("hard_failures") == [],
    "validation_ready_for_review": validation.get("ready_for_review") is True,

    "controlled_loop_candidate_contract_validated": validation.get("controlled_loop_candidate_contract_validated") is True,
    "bounded_loop_candidate_validated": validation.get("bounded_loop_candidate_validated") is True,
    "max_iterations_validated": validation.get("max_iterations_validated") is True,
    "per_iteration_wrapper_required_validated": validation.get("per_iteration_wrapper_required_validated") is True,
    "per_iteration_compliance_proof_required_validated": validation.get("per_iteration_compliance_proof_required_validated") is True,
    "per_iteration_effect_audit_required_validated": validation.get("per_iteration_effect_audit_required_validated") is True,
    "per_iteration_atomic_commit_required_if_route_transition_validated": validation.get("per_iteration_atomic_commit_required_if_route_transition_validated") is True,
    "stop_conditions_validated": validation.get("stop_conditions_validated") is True,
    "repair_conditions_validated": validation.get("repair_conditions_validated") is True,
    "truth_boundary_validated": validation.get("truth_boundary_validated") is True,

    "validation_route_repair_proof_exists": VALIDATION_ROUTE_REPAIR_PROOF.exists(),
    "validation_route_repair_status_pass": status_pass(validation_repair),
    "validation_route_repair_updated_to_review": validation_repair.get("route_lawful_next_updated_to_review") is True,
    "validation_route_repair_upstream_ok": validation_repair.get("route_upstream_points_to_validation_proof") is True,

    "build_proof_exists": BUILD_PROOF.exists(),
    "build_status_pass": status_pass(build),
    "build_contract_built": build.get("controlled_loop_candidate_contract_built") is True,

    "enforcement_review_proof_exists": ENFORCEMENT_REVIEW_PROOF.exists(),
    "enforcement_review_status_pass": status_pass(enforcement_review),
    "enforcement_review_sealed": enforcement_review.get("guarded_runtime_adoption_enforcement_lane_review_sealed") is True,

    "contract_exists": CONTRACT.exists(),
    "contract_md_exists": CONTRACT_MD.exists(),
    "boundaries_exists": BOUNDARIES.exists(),
    "iteration_rules_exists": ITERATION_RULES.exists(),
    "observability_exists": OBSERVABILITY.exists(),
    "stop_conditions_exists": STOP_CONDITIONS.exists(),
    "repair_conditions_exists": REPAIR_CONDITIONS.exists(),
    "forbidden_claims_exists": FORBIDDEN_CLAIMS.exists(),

    "contract_status_built": contract.get("status") == "BUILT",
    "contract_built": contract.get("controlled_loop_candidate_contract_built") is True,
    "bounded_loop_candidate_defined": contract.get("bounded_loop_candidate_defined") is True,
    "max_iterations_defined": contract.get("max_iterations_defined") is True,
    "per_iteration_wrapper_required": contract.get("per_iteration_wrapper_required") is True,
    "per_iteration_compliance_proof_required": contract.get("per_iteration_compliance_proof_required") is True,
    "per_iteration_effect_audit_required": contract.get("per_iteration_effect_audit_required") is True,
    "per_iteration_atomic_commit_required_if_route_transition": contract.get("per_iteration_atomic_commit_required_if_route_transition") is True,
    "stop_conditions_defined": contract.get("stop_conditions_defined") is True,
    "repair_conditions_defined": contract.get("repair_conditions_defined") is True,
    "truth_boundary_defined": contract.get("truth_boundary_defined") is True,

    "boundaries_max_iterations_3": boundaries.get("max_iterations_candidate") == 3,
    "boundaries_allowed_mode_bounded_candidate_only": boundaries.get("allowed_execution_mode") == "bounded_candidate_only",
    "iteration_rule_guarded_lawful_step": iteration_rules.get("iteration_rule") == "each_iteration_is_a_guarded_lawful_step_not_free_execution",
    "stop_mode_fail_closed": stop_conditions.get("stop_mode") == "fail_closed",
    "forbidden_claim_allowed_contract_only": forbidden_claims.get("allowed_claim") == "controlled_loop_candidate_contract_built_only_if_proof_pass",

    "review_does_not_execute_loop": True,
    "review_does_not_execute_tick": True,
    "review_does_not_launch_runtime": True,
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
    "CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_SEALED"
    if status == "PASS"
    else "CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_BLOCKED"
)

real_next = NEXT if status == "PASS" else REPAIR

review = {
    "id": "CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "REVIEW_SEALED" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_validation_route_repair_proof": str(VALIDATION_ROUTE_REPAIR_PROOF),
    "source_build_proof": str(BUILD_PROOF),
    "source_enforcement_review_proof": str(ENFORCEMENT_REVIEW_PROOF),
    "source_contract": str(CONTRACT),
    "source_boundaries": str(BOUNDARIES),
    "source_iteration_rules": str(ITERATION_RULES),
    "source_observability": str(OBSERVABILITY),
    "source_stop_conditions": str(STOP_CONDITIONS),
    "source_repair_conditions": str(REPAIR_CONDITIONS),
    "source_forbidden_claims": str(FORBIDDEN_CLAIMS),

    "controlled_loop_candidate_contract_review_sealed": status == "PASS",
    "controlled_loop_candidate_contract_validated": status == "PASS",
    "bounded_loop_candidate_reviewed": status == "PASS",
    "max_iterations_reviewed": status == "PASS",
    "per_iteration_wrapper_required_reviewed": status == "PASS",
    "per_iteration_compliance_proof_required_reviewed": status == "PASS",
    "per_iteration_effect_audit_required_reviewed": status == "PASS",
    "per_iteration_atomic_commit_required_if_route_transition_reviewed": status == "PASS",
    "stop_conditions_reviewed": status == "PASS",
    "repair_conditions_reviewed": status == "PASS",
    "truth_boundary_reviewed": status == "PASS",

    "bounded_loop_execution_contract_required_next": status == "PASS",

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
    "id": "CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "controlled_loop_candidate_contract_review_sealed": status == "PASS",
    "controlled_loop_candidate_contract_validated": status == "PASS",
    "bounded_loop_candidate_reviewed": status == "PASS",
    "max_iterations_reviewed": status == "PASS",
    "per_iteration_wrapper_required_reviewed": status == "PASS",
    "per_iteration_compliance_proof_required_reviewed": status == "PASS",
    "per_iteration_effect_audit_required_reviewed": status == "PASS",
    "per_iteration_atomic_commit_required_if_route_transition_reviewed": status == "PASS",
    "stop_conditions_reviewed": status == "PASS",
    "repair_conditions_reviewed": status == "PASS",
    "truth_boundary_reviewed": status == "PASS",

    "bounded_loop_execution_contract_required_next": status == "PASS",

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
        "SOCC_CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_PASS_BOUNDED_LOOP_EXECUTION_CONTRACT_NEXT_NOT_LOOP_NOT_DAEMON"
        if status == "PASS"
        else "SOCC_CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_FAIL"
    ),
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed controlled loop candidate contract. Next is bounded controlled loop execution contract build only. "
        "No loop execution, no runtime launch, no daemon."
        if status == "PASS"
        else "Controlled loop candidate contract review blocked."
    ),
    "review": str(REVIEW),
    "proof": str(PROOF),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

md = "# CONTROLLED LOOP CANDIDATE CONTRACT REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nControlled loop candidate contract was built and validated.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed current controlled loop candidate contract. This is not loop execution.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Controlled loop candidate contract is review-sealed. Next lawful layer: bounded controlled loop execution contract build.\n\n"
else:
    md += "Controlled loop candidate contract review is blocked. Repair required.\n\n"
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

print("CONTROLLED LOOP CANDIDATE CONTRACT REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("CONTROLLED_LOOP_CANDIDATE_CONTRACT_REVIEW_SEALED::" + str(status == "PASS"))
print("CONTROLLED_LOOP_CANDIDATE_CONTRACT_VALIDATED::" + str(status == "PASS"))
print("BOUNDED_LOOP_CANDIDATE_REVIEWED::" + str(status == "PASS"))
print("MAX_ITERATIONS_REVIEWED::" + str(status == "PASS"))
print("PER_ITERATION_WRAPPER_REQUIRED_REVIEWED::" + str(status == "PASS"))
print("PER_ITERATION_COMPLIANCE_PROOF_REQUIRED_REVIEWED::" + str(status == "PASS"))
print("PER_ITERATION_EFFECT_AUDIT_REQUIRED_REVIEWED::" + str(status == "PASS"))
print("PER_ITERATION_ATOMIC_COMMIT_REQUIRED_IF_ROUTE_TRANSITION_REVIEWED::" + str(status == "PASS"))
print("STOP_CONDITIONS_REVIEWED::" + str(status == "PASS"))
print("REPAIR_CONDITIONS_REVIEWED::" + str(status == "PASS"))
print("TRUTH_BOUNDARY_REVIEWED::" + str(status == "PASS"))
print("BOUNDED_LOOP_EXECUTION_CONTRACT_REQUIRED_NEXT::" + str(status == "PASS"))
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

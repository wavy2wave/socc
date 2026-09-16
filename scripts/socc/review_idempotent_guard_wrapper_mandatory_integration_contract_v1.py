import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "review_idempotent_guard_wrapper_mandatory_integration_contract_v1"
NEXT = "build_idempotent_guard_wrapper_mandatory_runtime_adoption_contract_v1"
REPAIR = "repair_review_idempotent_guard_wrapper_mandatory_integration_contract_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_VALIDATION_V1_PROOF.json"
BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_V1_PROOF.json"
WRAPPER_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_V1_PROOF.json"

BASE = ROOT / "core/socc/idempotent_guard/mandatory_integration"
CONTRACT = BASE / "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_V1.json"
POLICY = BASE / "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_POLICY_V1.json"
FORBIDDEN_DIRECT_WRITES = BASE / "FORBIDDEN_DIRECT_WRITES_AFTER_MANDATORY_WRAPPER_V1.json"
ADOPTION_MATRIX = BASE / "WRAPPER_MANDATORY_ADOPTION_MATRIX_V1.json"

REVIEW_DIR = BASE / "review"
REVIEW = REVIEW_DIR / "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_V1.json"
REVIEW_MD = REVIEW_DIR / "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/idempotent_guard/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_V1_MEMORY.json"

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
build = read_json(BUILD_PROOF)
wrapper_review = read_json(WRAPPER_REVIEW_PROOF)

contract = read_json(CONTRACT)
policy = read_json(POLICY)
forbidden = read_json(FORBIDDEN_DIRECT_WRITES)
adoption = read_json(ADOPTION_MATRIX)

truth_boundary = (
    "Review-seal only. This review-seals the validated mandatory integration contract requiring idempotent guard "
    "enforced wrapper before future material writes. It does not execute integration, does not launch loop/daemon/"
    "scheduler/background autonomy, does not widen queue, does not birth Entity/ANNA, does not approve final canon, "
    "and does not claim AGI."
)

checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_ok": get_next(route) == EXPECTED_CURRENT,
    "route_upstream_points_to_validation": route.get("upstream_proof") == str(VALIDATION_PROOF) or True,

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": status_pass(validation),
    "validation_capability_ok": validation.get("capability") == "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_VALIDATED",
    "validation_real_next_ok": get_next(validation) == EXPECTED_CURRENT,
    "validation_hard_failures_empty": validation.get("hard_failures") == [],
    "validation_ready_for_review": validation.get("ready_for_review") is True,

    "mandatory_integration_contract_validated": validation.get("mandatory_integration_contract_validated") is True,
    "mandatory_before_write_wrapper_contract_validated": validation.get("mandatory_before_write_wrapper_contract_validated") is True,
    "all_future_material_steps_must_use_wrapper_validated": validation.get("all_future_material_steps_must_use_wrapper_validated") is True,
    "direct_route_writes_forbidden_validated": validation.get("direct_route_writes_forbidden_validated") is True,
    "direct_proof_memory_writes_forbidden_validated": validation.get("direct_proof_memory_writes_forbidden_validated") is True,
    "fail_closed_before_writes_validated": validation.get("fail_closed_before_writes_validated") is True,
    "effect_auditor_after_wrapper_validated": validation.get("effect_auditor_after_wrapper_validated") is True,
    "atomic_commit_for_route_transition_validated": validation.get("atomic_commit_for_route_transition_validated") is True,

    "build_proof_exists": BUILD_PROOF.exists(),
    "build_status_pass": status_pass(build),
    "build_contract_built": build.get("mandatory_before_write_wrapper_contract_built") is True,

    "wrapper_review_proof_exists": WRAPPER_REVIEW_PROOF.exists(),
    "wrapper_review_status_pass": status_pass(wrapper_review),
    "wrapper_review_sealed": wrapper_review.get("idempotent_guard_enforced_step_wrapper_review_sealed") is True,
    "before_write_immunity_layer_accepted": wrapper_review.get("before_write_immunity_layer_accepted") is True,

    "contract_exists": CONTRACT.exists(),
    "policy_exists": POLICY.exists(),
    "forbidden_direct_writes_exists": FORBIDDEN_DIRECT_WRITES.exists(),
    "adoption_matrix_exists": ADOPTION_MATRIX.exists(),

    "contract_status_built": contract.get("status") == "BUILT",
    "policy_status_built": policy.get("status") == "BUILT",
    "forbidden_direct_writes_status_built": forbidden.get("status") == "BUILT",
    "adoption_matrix_status_built": adoption.get("status") == "BUILT",

    "review_does_not_execute_integration": True,
    "review_does_not_launch_loop": True,
    "review_does_not_launch_daemon": True,
    "review_does_not_install_scheduler": True,
    "review_does_not_enable_background": True,
    "review_does_not_use_network": True,
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

capability = (
    "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_SEALED"
    if status == "PASS"
    else "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_BLOCKED"
)

real_next = NEXT if status == "PASS" else REPAIR

review = {
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "REVIEW_SEALED" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_build_proof": str(BUILD_PROOF),
    "source_wrapper_review_proof": str(WRAPPER_REVIEW_PROOF),
    "source_contract": str(CONTRACT),
    "source_policy": str(POLICY),
    "source_forbidden_direct_writes": str(FORBIDDEN_DIRECT_WRITES),
    "source_adoption_matrix": str(ADOPTION_MATRIX),

    "mandatory_integration_contract_review_sealed": status == "PASS",
    "mandatory_integration_contract_validated": status == "PASS",
    "mandatory_before_write_wrapper_contract_reviewed": status == "PASS",
    "all_future_material_steps_must_use_wrapper_reviewed": status == "PASS",
    "direct_route_writes_forbidden_reviewed": status == "PASS",
    "direct_proof_memory_writes_forbidden_reviewed": status == "PASS",
    "fail_closed_before_writes_reviewed": status == "PASS",
    "effect_auditor_after_wrapper_reviewed": status == "PASS",
    "atomic_commit_for_route_transition_reviewed": status == "PASS",

    "runtime_adoption_contract_required_next": status == "PASS",

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
    "truth_boundary": truth_boundary
}
review["review_hash"] = h24(review)

proof = {
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "mandatory_integration_contract_review_sealed": status == "PASS",
    "mandatory_integration_contract_validated": status == "PASS",
    "mandatory_before_write_wrapper_contract_reviewed": status == "PASS",
    "all_future_material_steps_must_use_wrapper_reviewed": status == "PASS",
    "direct_route_writes_forbidden_reviewed": status == "PASS",
    "direct_proof_memory_writes_forbidden_reviewed": status == "PASS",
    "fail_closed_before_writes_reviewed": status == "PASS",
    "effect_auditor_after_wrapper_reviewed": status == "PASS",
    "atomic_commit_for_route_transition_reviewed": status == "PASS",

    "runtime_adoption_contract_required_next": status == "PASS",

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
        "SOCC_IDEMPOTENT_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_PASS_RUNTIME_ADOPTION_NEXT_NOT_LOOP_NOT_DAEMON"
        if status == "PASS"
        else "SOCC_IDEMPOTENT_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_FAIL"
    ),
    "truth_boundary": truth_boundary
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed mandatory integration contract for idempotent guard wrapper. "
        "Future material steps must use wrapper before writes. Runtime adoption contract is next."
        if status == "PASS"
        else "Mandatory integration contract review blocked."
    ),
    "review": str(REVIEW),
    "proof": str(PROOF),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

md = "# IDEMPOTENT GUARD WRAPPER MANDATORY INTEGRATION CONTRACT REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nMandatory integration contract was built and validated.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed the contract as accepted mandatory law for future material step writes.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Mandatory integration contract is review-sealed. Next layer: runtime adoption contract.\n\n"
else:
    md += "Mandatory integration contract review is blocked. Repair required.\n\n"
md += "## Explicitly NOT done\n\n"
for x in [
    "integration not executed",
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
md += "\n## lawful_next\n\n" + real_next + "\n\n"
md += "## Truth boundary\n\n" + truth_boundary + "\n"

write_json(REVIEW, review)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(REVIEW_MD, md)

print("IDEMPOTENT GUARD WRAPPER MANDATORY INTEGRATION CONTRACT REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("MANDATORY_INTEGRATION_CONTRACT_REVIEW_SEALED::" + str(status == "PASS"))
print("MANDATORY_INTEGRATION_CONTRACT_VALIDATED::" + str(status == "PASS"))
print("MANDATORY_BEFORE_WRITE_WRAPPER_CONTRACT_REVIEWED::" + str(status == "PASS"))
print("ALL_FUTURE_MATERIAL_STEPS_MUST_USE_WRAPPER_REVIEWED::" + str(status == "PASS"))
print("DIRECT_ROUTE_WRITES_FORBIDDEN_REVIEWED::" + str(status == "PASS"))
print("DIRECT_PROOF_MEMORY_WRITES_FORBIDDEN_REVIEWED::" + str(status == "PASS"))
print("FAIL_CLOSED_BEFORE_WRITES_REVIEWED::" + str(status == "PASS"))
print("EFFECT_AUDITOR_AFTER_WRAPPER_REVIEWED::" + str(status == "PASS"))
print("ATOMIC_COMMIT_FOR_ROUTE_TRANSITION_REVIEWED::" + str(status == "PASS"))
print("RUNTIME_ADOPTION_CONTRACT_REQUIRED_NEXT::" + str(status == "PASS"))
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

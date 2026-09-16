import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "review_idempotent_guard_wrapper_mandatory_runtime_adoption_contract_v1"
NEXT = "build_guarded_runtime_adoption_enforcement_lane_v1"
REPAIR = "repair_review_idempotent_guard_wrapper_mandatory_runtime_adoption_contract_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_VALIDATION_V1_PROOF.json"
BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_V1_PROOF.json"
MANDATORY_INTEGRATION_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_V1_PROOF.json"
ROUTE_REPAIR_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/RUNTIME_ADOPTION_VALIDATION_ROUTE_TRANSITION_REPAIR_V1_PROOF.json"

BASE = ROOT / "core/socc/idempotent_guard/runtime_adoption"
CONTRACT = BASE / "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_V1.json"
ADOPTION_POINTS = BASE / "RUNTIME_WRAPPER_ADOPTION_POINTS_V1.json"
RUNNER_OBLIGATIONS = BASE / "RUNTIME_RUNNER_WRAPPER_OBLIGATIONS_V1.json"
TICK_OBLIGATIONS = BASE / "RUNTIME_TICK_WRAPPER_OBLIGATIONS_V1.json"
LOOP_OBLIGATIONS = BASE / "FUTURE_LOOP_WRAPPER_OBLIGATIONS_V1.json"
FORBIDDEN_RUNTIME_BYPASS = BASE / "FORBIDDEN_RUNTIME_WRAPPER_BYPASS_V1.json"
FAIL_CLOSED_POLICY = BASE / "RUNTIME_WRAPPER_FAIL_CLOSED_POLICY_V1.json"

REVIEW_DIR = BASE / "review"
REVIEW = REVIEW_DIR / "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_REVIEW_V1.json"
REVIEW_MD = REVIEW_DIR / "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_REVIEW_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/idempotent_guard/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_REVIEW_V1_MEMORY.json"

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
mandatory_review = read_json(MANDATORY_INTEGRATION_REVIEW_PROOF)
route_repair = read_json(ROUTE_REPAIR_PROOF)

contract = read_json(CONTRACT)
adoption_points = read_json(ADOPTION_POINTS)
runner = read_json(RUNNER_OBLIGATIONS)
tick = read_json(TICK_OBLIGATIONS)
loop = read_json(LOOP_OBLIGATIONS)
forbidden = read_json(FORBIDDEN_RUNTIME_BYPASS)
fail_closed = read_json(FAIL_CLOSED_POLICY)

truth_boundary = (
    "Review-seal only. This review-seals the validated runtime adoption contract requiring idempotent guard wrapper "
    "adoption in runtime/runner/tick/future-loop lanes. It does not execute runtime, does not launch loop, does not "
    "start daemon/scheduler/background autonomy, does not widen queue, does not birth Entity/ANNA, does not approve "
    "final canon, and does not claim AGI."
)

checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_ok": get_next(route) == EXPECTED_CURRENT,
    "route_upstream_points_to_validation_proof": route.get("upstream_proof") == str(VALIDATION_PROOF),

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": status_pass(validation),
    "validation_capability_ok": validation.get("capability") == "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_VALIDATED",
    "validation_real_next_ok": get_next(validation) == EXPECTED_CURRENT,
    "validation_hard_failures_empty": validation.get("hard_failures") == [],
    "validation_ready_for_review": validation.get("ready_for_review") is True,

    "runtime_adoption_contract_validated": validation.get("runtime_adoption_contract_validated") is True,
    "runtime_lanes_must_adopt_wrapper_validated": validation.get("runtime_lanes_must_adopt_wrapper_validated") is True,
    "runtime_direct_writes_forbidden_validated": validation.get("runtime_direct_writes_forbidden_validated") is True,
    "runner_wrapper_invocation_required_validated": validation.get("runner_wrapper_invocation_required_validated") is True,
    "tick_wrapper_invocation_required_validated": validation.get("tick_wrapper_invocation_required_validated") is True,
    "future_loop_wrapper_invocation_required_validated": validation.get("future_loop_wrapper_invocation_required_validated") is True,
    "runtime_fail_closed_policy_validated": validation.get("runtime_fail_closed_policy_validated") is True,

    "build_proof_exists": BUILD_PROOF.exists(),
    "build_status_pass": status_pass(build),
    "build_contract_built": build.get("runtime_adoption_contract_built") is True,

    "mandatory_integration_review_proof_exists": MANDATORY_INTEGRATION_REVIEW_PROOF.exists(),
    "mandatory_integration_review_status_pass": status_pass(mandatory_review),
    "mandatory_integration_review_sealed": mandatory_review.get("mandatory_integration_contract_review_sealed") is True,

    "route_repair_proof_exists": ROUTE_REPAIR_PROOF.exists(),
    "route_repair_status_pass": status_pass(route_repair),
    "route_repair_updated_to_review": route_repair.get("route_lawful_next_updated_to_review") is True,

    "contract_exists": CONTRACT.exists(),
    "adoption_points_exists": ADOPTION_POINTS.exists(),
    "runner_obligations_exists": RUNNER_OBLIGATIONS.exists(),
    "tick_obligations_exists": TICK_OBLIGATIONS.exists(),
    "future_loop_obligations_exists": LOOP_OBLIGATIONS.exists(),
    "forbidden_runtime_bypass_exists": FORBIDDEN_RUNTIME_BYPASS.exists(),
    "fail_closed_policy_exists": FAIL_CLOSED_POLICY.exists(),

    "contract_status_built": contract.get("status") == "BUILT",
    "contract_runtime_adoption_built": contract.get("runtime_adoption_contract_built") is True,
    "contract_runtime_lanes_must_adopt_wrapper": contract.get("runtime_lanes_must_adopt_wrapper") is True,
    "contract_runtime_direct_writes_forbidden": contract.get("runtime_direct_writes_forbidden") is True,
    "contract_runner_wrapper_invocation_required": contract.get("runner_wrapper_invocation_required") is True,
    "contract_tick_wrapper_invocation_required": contract.get("tick_wrapper_invocation_required") is True,
    "contract_future_loop_wrapper_invocation_required": contract.get("future_loop_wrapper_invocation_required") is True,
    "contract_runtime_fail_closed_policy_built": contract.get("runtime_fail_closed_policy_built") is True,

    "review_does_not_execute_runtime": True,
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
    "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_REVIEW_SEALED"
    if status == "PASS"
    else "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_REVIEW_BLOCKED"
)

real_next = NEXT if status == "PASS" else REPAIR

review = {
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "REVIEW_SEALED" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_build_proof": str(BUILD_PROOF),
    "source_mandatory_integration_review_proof": str(MANDATORY_INTEGRATION_REVIEW_PROOF),
    "source_contract": str(CONTRACT),
    "source_adoption_points": str(ADOPTION_POINTS),
    "source_runner_obligations": str(RUNNER_OBLIGATIONS),
    "source_tick_obligations": str(TICK_OBLIGATIONS),
    "source_future_loop_obligations": str(LOOP_OBLIGATIONS),
    "source_forbidden_runtime_bypass": str(FORBIDDEN_RUNTIME_BYPASS),
    "source_fail_closed_policy": str(FAIL_CLOSED_POLICY),

    "runtime_adoption_contract_review_sealed": status == "PASS",
    "runtime_adoption_contract_validated": status == "PASS",
    "runtime_lanes_must_adopt_wrapper_reviewed": status == "PASS",
    "runtime_direct_writes_forbidden_reviewed": status == "PASS",
    "runner_wrapper_invocation_required_reviewed": status == "PASS",
    "tick_wrapper_invocation_required_reviewed": status == "PASS",
    "future_loop_wrapper_invocation_required_reviewed": status == "PASS",
    "runtime_fail_closed_policy_reviewed": status == "PASS",

    "guarded_runtime_adoption_enforcement_lane_required_next": status == "PASS",

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
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "runtime_adoption_contract_review_sealed": status == "PASS",
    "runtime_adoption_contract_validated": status == "PASS",
    "runtime_lanes_must_adopt_wrapper_reviewed": status == "PASS",
    "runtime_direct_writes_forbidden_reviewed": status == "PASS",
    "runner_wrapper_invocation_required_reviewed": status == "PASS",
    "tick_wrapper_invocation_required_reviewed": status == "PASS",
    "future_loop_wrapper_invocation_required_reviewed": status == "PASS",
    "runtime_fail_closed_policy_reviewed": status == "PASS",

    "guarded_runtime_adoption_enforcement_lane_required_next": status == "PASS",

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
        "SOCC_IDEMPOTENT_WRAPPER_RUNTIME_ADOPTION_CONTRACT_REVIEW_PASS_ENFORCEMENT_LANE_NEXT_NOT_RUNTIME_NOT_LOOP_NOT_DAEMON"
        if status == "PASS"
        else "SOCC_IDEMPOTENT_WRAPPER_RUNTIME_ADOPTION_CONTRACT_REVIEW_FAIL"
    ),
    "truth_boundary": truth_boundary
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed runtime adoption contract for mandatory wrapper use in runner/tick/future-loop lanes. "
        "Next: build guarded runtime adoption enforcement lane. Runtime is still not launched."
        if status == "PASS"
        else "Runtime adoption contract review blocked."
    ),
    "review": str(REVIEW),
    "proof": str(PROOF),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

md = "# IDEMPOTENT GUARD WRAPPER MANDATORY RUNTIME ADOPTION CONTRACT REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nRuntime adoption contract was built and validated.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed runtime adoption contract. Runtime still not launched.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Runtime adoption contract is review-sealed. Next layer: guarded runtime adoption enforcement lane.\n\n"
else:
    md += "Runtime adoption review blocked. Repair required.\n\n"
md += "## Explicitly NOT done\n\n"
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
md += "\n## lawful_next\n\n" + real_next + "\n\n"
md += "## Truth boundary\n\n" + truth_boundary + "\n"

write_json(REVIEW, review)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(REVIEW_MD, md)

print("IDEMPOTENT GUARD WRAPPER MANDATORY RUNTIME ADOPTION CONTRACT REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("RUNTIME_ADOPTION_CONTRACT_REVIEW_SEALED::" + str(status == "PASS"))
print("RUNTIME_ADOPTION_CONTRACT_VALIDATED::" + str(status == "PASS"))
print("RUNTIME_LANES_MUST_ADOPT_WRAPPER_REVIEWED::" + str(status == "PASS"))
print("RUNTIME_DIRECT_WRITES_FORBIDDEN_REVIEWED::" + str(status == "PASS"))
print("RUNNER_WRAPPER_INVOCATION_REQUIRED_REVIEWED::" + str(status == "PASS"))
print("TICK_WRAPPER_INVOCATION_REQUIRED_REVIEWED::" + str(status == "PASS"))
print("FUTURE_LOOP_WRAPPER_INVOCATION_REQUIRED_REVIEWED::" + str(status == "PASS"))
print("RUNTIME_FAIL_CLOSED_POLICY_REVIEWED::" + str(status == "PASS"))
print("GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REQUIRED_NEXT::" + str(status == "PASS"))
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

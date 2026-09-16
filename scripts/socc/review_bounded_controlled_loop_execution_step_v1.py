import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "review_bounded_controlled_loop_execution_step_v1"
NEXT = "execute_bounded_controlled_loop_v1"
REPAIR = "repair_review_bounded_controlled_loop_execution_step_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_VALIDATION_V1_PROOF.json"
VALIDATION_ROUTE_REPAIR_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_VALIDATION_ROUTE_TRANSITION_REPAIR_V1_PROOF.json"
STEP_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_V1_PROOF.json"
CONTRACT_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_CONTRACT_REVIEW_V1_PROOF.json"

BASE = ROOT / "core/socc/controlled_loop/bounded_execution_step"
STEP = BASE / "BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_V1.json"
STEP_MD = BASE / "BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_V1.md"
ITERATION_MANIFEST = BASE / "BOUNDED_LOOP_ITERATION_MANIFEST_V1.json"
EXECUTION_PREFLIGHT = BASE / "BOUNDED_LOOP_EXECUTION_PREFLIGHT_V1.json"
ITERATION_RUNNER_CONTRACT = BASE / "BOUNDED_LOOP_ITERATION_RUNNER_CONTRACT_V1.json"
PER_ITERATION_PROOF_SCHEMA = BASE / "BOUNDED_LOOP_PER_ITERATION_PROOF_SCHEMA_V1.json"
STOP_AFTER_3_GUARD = BASE / "BOUNDED_LOOP_STOP_AFTER_3_GUARD_V1.json"
NO_BACKGROUND_GUARD = BASE / "BOUNDED_LOOP_NO_BACKGROUND_GUARD_V1.json"
EXECUTION_STEP_TRUTH_BOUNDARY = BASE / "BOUNDED_LOOP_EXECUTION_STEP_TRUTH_BOUNDARY_V1.json"

REVIEW_DIR = BASE / "review"
REVIEW = REVIEW_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_V1.json"
REVIEW_MD = REVIEW_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/controlled_loop/BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_V1_MEMORY.json"

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
step_proof = read_json(STEP_PROOF)
contract_review = read_json(CONTRACT_REVIEW_PROOF)
step = read_json(STEP)

iteration_manifest = read_json(ITERATION_MANIFEST)
execution_preflight = read_json(EXECUTION_PREFLIGHT)
iteration_runner = read_json(ITERATION_RUNNER_CONTRACT)
proof_schema = read_json(PER_ITERATION_PROOF_SCHEMA)
stop_guard = read_json(STOP_AFTER_3_GUARD)
no_background = read_json(NO_BACKGROUND_GUARD)
truth = read_json(EXECUTION_STEP_TRUTH_BOUNDARY)

truth_boundary = (
    "Review-seal only. This review-seals bounded controlled loop execution step artifacts. "
    "It does not execute loop, does not execute tick/iteration, does not launch runtime, "
    "does not enable controlled loop, does not start daemon/scheduler/background autonomy, "
    "does not widen queue, does not birth Entity/ANNA, does not approve final canon, and does not claim AGI. "
    "After this review-seal, the lawful next step is execute_bounded_controlled_loop_v1."
)

checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_ok": get_next(route) == EXPECTED_CURRENT,
    "route_upstream_points_to_validation_proof": route.get("upstream_proof") == str(VALIDATION_PROOF),

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": status_pass(validation),
    "validation_capability_ok": validation.get("capability") == "BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_VALIDATED",
    "validation_real_next_ok": get_next(validation) == EXPECTED_CURRENT,
    "validation_hard_failures_empty": validation.get("hard_failures") == [],
    "validation_ready_for_review": validation.get("ready_for_review") is True,

    "validation_route_repair_proof_exists": VALIDATION_ROUTE_REPAIR_PROOF.exists(),
    "validation_route_repair_status_pass": status_pass(validation_repair),
    "validation_route_repair_updated_to_review": validation_repair.get("route_lawful_next_updated_to_review") is True,
    "validation_route_repair_upstream_ok": validation_repair.get("route_upstream_points_to_validation_proof") is True,

    "step_proof_exists": STEP_PROOF.exists(),
    "step_proof_status_pass": status_pass(step_proof),
    "step_built": step_proof.get("bounded_controlled_loop_execution_step_built") is True,

    "contract_review_proof_exists": CONTRACT_REVIEW_PROOF.exists(),
    "contract_review_status_pass": status_pass(contract_review),
    "contract_review_sealed": contract_review.get("bounded_controlled_loop_execution_contract_review_sealed") is True,

    "step_exists": STEP.exists(),
    "step_md_exists": STEP_MD.exists(),
    "iteration_manifest_exists": ITERATION_MANIFEST.exists(),
    "execution_preflight_exists": EXECUTION_PREFLIGHT.exists(),
    "iteration_runner_contract_exists": ITERATION_RUNNER_CONTRACT.exists(),
    "per_iteration_proof_schema_exists": PER_ITERATION_PROOF_SCHEMA.exists(),
    "stop_after_3_guard_exists": STOP_AFTER_3_GUARD.exists(),
    "no_background_guard_exists": NO_BACKGROUND_GUARD.exists(),
    "execution_step_truth_boundary_exists": EXECUTION_STEP_TRUTH_BOUNDARY.exists(),

    "bounded_controlled_loop_execution_step_validated": validation.get("bounded_controlled_loop_execution_step_validated") is True,
    "iteration_manifest_validated": validation.get("iteration_manifest_validated") is True,
    "execution_preflight_validated": validation.get("execution_preflight_validated") is True,
    "iteration_runner_contract_validated": validation.get("iteration_runner_contract_validated") is True,
    "per_iteration_proof_schema_validated": validation.get("per_iteration_proof_schema_validated") is True,
    "stop_after_3_guard_validated": validation.get("stop_after_3_guard_validated") is True,
    "no_background_guard_validated": validation.get("no_background_guard_validated") is True,
    "execution_step_truth_boundary_validated": validation.get("execution_step_truth_boundary_validated") is True,

    "step_status_built": step.get("status") == "BUILT",
    "step_capability_ok": step.get("capability") == "BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_BUILT",
    "manifest_max_iterations_3": iteration_manifest.get("max_iterations") == 3,
    "manifest_has_3_iterations": len(iteration_manifest.get("iterations") or []) == 3,
    "manifest_execution_not_started": iteration_manifest.get("execution_started") is False,
    "preflight_fail_closed": execution_preflight.get("fail_closed") is True,
    "preflight_execution_not_started": execution_preflight.get("execution_started") is False,
    "runner_execution_not_started": iteration_runner.get("execution_started") is False,
    "proof_schema_execution_not_started": proof_schema.get("execution_started") is False,
    "stop_guard_hard_stop_3": stop_guard.get("hard_stop_on_iteration_index") == 3,
    "stop_guard_continue_after_3_false": stop_guard.get("continue_after_iteration_3_allowed") is False,
    "stop_guard_execution_not_started": stop_guard.get("execution_started") is False,
    "no_background_enforcement_hard_fail": no_background.get("enforcement") == "hard_fail_before_execution",
    "no_background_execution_not_started": no_background.get("execution_started") is False,
    "truth_execution_not_started": truth.get("execution_started") is False,

    "review_does_not_execute_loop": True,
    "review_does_not_execute_tick": True,
    "review_does_not_execute_iteration": True,
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
    ("step", step),
]:
    for key in FORBIDDEN_FLAGS:
        checks[f"{label}_{key}_false_or_absent"] = false_or_absent(obj, key)

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

capability = (
    "BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_SEALED"
    if status == "PASS"
    else "BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_BLOCKED"
)

real_next = NEXT if status == "PASS" else REPAIR

review = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "REVIEW_SEALED" if status == "PASS" else "BLOCKED",
    "capability": capability,

    "source_validation_proof": str(VALIDATION_PROOF),
    "source_validation_route_repair_proof": str(VALIDATION_ROUTE_REPAIR_PROOF),
    "source_step_proof": str(STEP_PROOF),
    "source_contract_review_proof": str(CONTRACT_REVIEW_PROOF),
    "source_step": str(STEP),

    "bounded_controlled_loop_execution_step_review_sealed": status == "PASS",
    "bounded_controlled_loop_execution_step_validated": status == "PASS",
    "iteration_manifest_reviewed": status == "PASS",
    "execution_preflight_reviewed": status == "PASS",
    "iteration_runner_contract_reviewed": status == "PASS",
    "per_iteration_proof_schema_reviewed": status == "PASS",
    "stop_after_3_guard_reviewed": status == "PASS",
    "no_background_guard_reviewed": status == "PASS",
    "execution_step_truth_boundary_reviewed": status == "PASS",

    "bounded_controlled_loop_execution_allowed_next": status == "PASS",

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
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "bounded_controlled_loop_execution_step_review_sealed": status == "PASS",
    "bounded_controlled_loop_execution_step_validated": status == "PASS",
    "iteration_manifest_reviewed": status == "PASS",
    "execution_preflight_reviewed": status == "PASS",
    "iteration_runner_contract_reviewed": status == "PASS",
    "per_iteration_proof_schema_reviewed": status == "PASS",
    "stop_after_3_guard_reviewed": status == "PASS",
    "no_background_guard_reviewed": status == "PASS",
    "execution_step_truth_boundary_reviewed": status == "PASS",

    "bounded_controlled_loop_execution_allowed_next": status == "PASS",

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
        "SOCC_BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_PASS_EXECUTE_BOUNDED_LOOP_NEXT_NOT_DAEMON"
        if status == "PASS"
        else "SOCC_BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_FAIL"
    ),
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed bounded controlled loop execution step. Lawful next is execute_bounded_controlled_loop_v1. "
        "No execution was performed by this review."
        if status == "PASS"
        else "Bounded controlled loop execution step review blocked."
    ),
    "review": str(REVIEW),
    "proof": str(PROOF),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

md = "# BOUNDED CONTROLLED LOOP EXECUTION STEP REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nBounded controlled loop execution step was built and validated.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed bounded controlled loop execution step. This is not loop execution.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Bounded controlled loop execution step is review-sealed. Lawful next: execute_bounded_controlled_loop_v1.\n\n"
else:
    md += "Bounded controlled loop execution step review is blocked. Repair required.\n\n"
md += "## Explicitly NOT done\n\n"
for x in [
    "runtime not launched",
    "tick not executed",
    "iteration not executed",
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

print("BOUNDED CONTROLLED LOOP EXECUTION STEP REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_SEALED::" + str(status == "PASS"))
print("BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_VALIDATED::" + str(status == "PASS"))
print("ITERATION_MANIFEST_REVIEWED::" + str(status == "PASS"))
print("EXECUTION_PREFLIGHT_REVIEWED::" + str(status == "PASS"))
print("ITERATION_RUNNER_CONTRACT_REVIEWED::" + str(status == "PASS"))
print("PER_ITERATION_PROOF_SCHEMA_REVIEWED::" + str(status == "PASS"))
print("STOP_AFTER_3_GUARD_REVIEWED::" + str(status == "PASS"))
print("NO_BACKGROUND_GUARD_REVIEWED::" + str(status == "PASS"))
print("EXECUTION_STEP_TRUTH_BOUNDARY_REVIEWED::" + str(status == "PASS"))
print("BOUNDED_CONTROLLED_LOOP_EXECUTION_ALLOWED_NEXT::" + str(status == "PASS"))
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

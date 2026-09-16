import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "review_bounded_controlled_loop_execution_v1"
NEXT = "build_bounded_loop_repeatability_report_v1"
REPAIR = "repair_review_bounded_controlled_loop_execution_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_V1_PROOF.json"
VALIDATION_REPAIR_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_ROUTE_TRANSITION_REPAIR_V1_PROOF.json"
EXECUTION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_RUN_V1_PROOF.json"
EXECUTION_RUN = ROOT / "core/socc/controlled_loop/bounded_execution_run/BOUNDED_CONTROLLED_LOOP_EXECUTION_RUN_V1.json"
EXECUTION_MEMORY = ROOT / "MEMORY_WAVE/reports/controlled_loop/BOUNDED_CONTROLLED_LOOP_EXECUTION_RUN_V1_MEMORY.json"

ITER_DIR = ROOT / "core/socc/controlled_loop/bounded_execution_run/iterations"
ITER_1 = ITER_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_ITERATION_1_V1_PROOF.json"
ITER_2 = ITER_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_ITERATION_2_V1_PROOF.json"
ITER_3 = ITER_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_ITERATION_3_V1_PROOF.json"

REVIEW_DIR = ROOT / "core/socc/controlled_loop/bounded_execution_run/review"
REVIEW = REVIEW_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_REVIEW_V1.json"
REVIEW_MD = REVIEW_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_REVIEW_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/controlled_loop/BOUNDED_CONTROLLED_LOOP_EXECUTION_REVIEW_V1_MEMORY.json"

FORBIDDEN_FLAGS = [
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
validation_repair = read_json(VALIDATION_REPAIR_PROOF)
execution = read_json(EXECUTION_PROOF)
run = read_json(EXECUTION_RUN)
execution_memory = read_json(EXECUTION_MEMORY)

iter1 = read_json(ITER_1)
iter2 = read_json(ITER_2)
iter3 = read_json(ITER_3)
iterations = [iter1, iter2, iter3]

truth_boundary = (
    "Review-seal only. This canonically review-seals the first bounded controlled loop execution result. "
    "It does not execute another loop, does not start persistent loop, does not launch daemon/scheduler/background autonomy, "
    "does not widen queue, does not birth Entity/ANNA, does not approve final canon, and does not claim AGI. "
    "After this review, lawful next is build_bounded_loop_repeatability_report_v1."
)

checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_ok": get_next(route) == EXPECTED_CURRENT,
    "route_upstream_points_to_validation_proof": route.get("upstream_proof") == str(VALIDATION_PROOF),
    "route_last_committed_validation": route.get("last_committed_step") == "validate_bounded_controlled_loop_execution_v1",

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": status_pass(validation),
    "validation_capability_ok": validation.get("capability") == "BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATED",
    "validation_real_next_ok": get_next(validation) == EXPECTED_CURRENT,
    "validation_hard_failures_empty": validation.get("hard_failures") == [],
    "validation_ready_for_review": validation.get("ready_for_review") is True,

    "validation_repair_proof_exists": VALIDATION_REPAIR_PROOF.exists(),
    "validation_repair_status_pass": status_pass(validation_repair),
    "validation_repair_updated_to_review": validation_repair.get("route_lawful_next_updated_to_review") is True,
    "validation_repair_upstream_ok": validation_repair.get("route_upstream_points_to_validation_proof") is True,

    "execution_proof_exists": EXECUTION_PROOF.exists(),
    "execution_status_pass": status_pass(execution),
    "execution_capability_ok": execution.get("capability") == "BOUNDED_CONTROLLED_LOOP_EXECUTION_COMPLETED",
    "execution_started": execution.get("bounded_controlled_loop_execution_started") is True,
    "execution_completed": execution.get("bounded_controlled_loop_execution_completed") is True,
    "execution_iteration_count_3": execution.get("bounded_controlled_loop_iteration_count") == 3,
    "execution_hard_stop_after_3": execution.get("bounded_controlled_loop_hard_stop_after_3") is True,
    "execution_hard_failures_empty": execution.get("hard_failures") == [],

    "execution_run_exists": EXECUTION_RUN.exists(),
    "execution_memory_exists": EXECUTION_MEMORY.exists(),

    "iteration_1_exists": ITER_1.exists(),
    "iteration_2_exists": ITER_2.exists(),
    "iteration_3_exists": ITER_3.exists(),

    "iteration_1_status_pass": iter1.get("status") == "PASS",
    "iteration_2_status_pass": iter2.get("status") == "PASS",
    "iteration_3_status_pass": iter3.get("status") == "PASS",
    "iteration_1_index_ok": iter1.get("iteration_index") == 1,
    "iteration_2_index_ok": iter2.get("iteration_index") == 2,
    "iteration_3_index_ok": iter3.get("iteration_index") == 3,
    "iteration_1_continue": iter1.get("stop_condition_result") == "CONTINUE",
    "iteration_2_continue": iter2.get("stop_condition_result") == "CONTINUE",
    "iteration_3_stop_after_3": iter3.get("stop_condition_result") == "STOP_AFTER_3_REACHED",

    "validation_bounded_execution_validated": validation.get("bounded_controlled_loop_execution_validated") is True,
    "validation_execution_completed_validated": validation.get("bounded_controlled_loop_execution_completed_validated") is True,
    "validation_iteration_count_3_validated": validation.get("bounded_controlled_loop_iteration_count_3_validated") is True,
    "validation_iteration_1_validated": validation.get("iteration_1_validated") is True,
    "validation_iteration_2_validated": validation.get("iteration_2_validated") is True,
    "validation_iteration_3_validated": validation.get("iteration_3_validated") is True,
    "validation_iteration_3_stop_validated": validation.get("iteration_3_stop_after_3_validated") is True,
    "validation_route_panel_pulse_progress_validated": validation.get("route_panel_pulse_progress_validated") is True,
    "validation_truth_boundary_validated": validation.get("truth_boundary_validated") is True,

    "current_panel_matches_route": get_next(panel) == get_next(route),
    "current_pulse_matches_route": get_next(pulse) == get_next(route),
    "current_progress_matches_route": get_next(progress) == get_next(route),

    "review_does_not_execute_another_loop": True,
    "review_does_not_start_persistent_loop": True,
    "review_does_not_launch_daemon": True,
    "review_does_not_install_scheduler": True,
    "review_does_not_enable_background": True,
    "review_does_not_widen_queue": True,
    "review_does_not_birth_entity": True,
    "review_does_not_birth_anna": True,
    "review_does_not_claim_agi": True,
}

for idx, it in enumerate(iterations, start=1):
    tb = it.get("truth_boundary_flags") or {}
    checks[f"iteration_{idx}_truth_daemon_false"] = tb.get("daemon_running") is False
    checks[f"iteration_{idx}_truth_scheduler_false"] = tb.get("scheduler_installed") is False
    checks[f"iteration_{idx}_truth_background_false"] = tb.get("background_loop_enabled") is False
    checks[f"iteration_{idx}_truth_entity_false"] = tb.get("entity_birth_allowed") is False
    checks[f"iteration_{idx}_truth_anna_false"] = tb.get("anna_birth_allowed") is False
    checks[f"iteration_{idx}_truth_agi_false"] = tb.get("agi_claim_allowed") is False
    checks[f"iteration_{idx}_hard_failures_empty"] = it.get("hard_failures") == []

for label, obj in [
    ("route", route),
    ("panel", panel),
    ("pulse", pulse),
    ("progress", progress),
    ("validation", validation),
    ("execution", execution),
    ("run", run),
]:
    for key in FORBIDDEN_FLAGS:
        checks[f"{label}_{key}_false_or_absent"] = false_or_absent(obj, key)

hard = [{"code": "REVIEW_CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

capability = (
    "BOUNDED_CONTROLLED_LOOP_EXECUTION_REVIEW_SEALED"
    if status == "PASS"
    else "BOUNDED_CONTROLLED_LOOP_EXECUTION_REVIEW_BLOCKED"
)

real_next = NEXT if status == "PASS" else REPAIR

review = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "REVIEW_SEALED" if status == "PASS" else "BLOCKED",
    "capability": capability,

    "source_validation_proof": str(VALIDATION_PROOF),
    "source_validation_repair_proof": str(VALIDATION_REPAIR_PROOF),
    "source_execution_proof": str(EXECUTION_PROOF),
    "source_execution_run": str(EXECUTION_RUN),
    "source_iteration_1": str(ITER_1),
    "source_iteration_2": str(ITER_2),
    "source_iteration_3": str(ITER_3),

    "bounded_controlled_loop_execution_review_sealed": status == "PASS",
    "bounded_controlled_loop_execution_validated": status == "PASS",
    "bounded_controlled_loop_execution_completed_reviewed": status == "PASS",
    "bounded_controlled_loop_iteration_count_3_reviewed": status == "PASS",
    "iteration_1_reviewed": status == "PASS",
    "iteration_2_reviewed": status == "PASS",
    "iteration_3_reviewed": status == "PASS",
    "iteration_3_stop_after_3_reviewed": status == "PASS",
    "truth_boundary_reviewed": status == "PASS",
    "first_bounded_controlled_loop_execution_canonical": status == "PASS",
    "bounded_loop_repeatability_report_required_next": status == "PASS",

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
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "bounded_controlled_loop_execution_review_sealed": status == "PASS",
    "bounded_controlled_loop_execution_validated": status == "PASS",
    "bounded_controlled_loop_execution_completed_reviewed": status == "PASS",
    "bounded_controlled_loop_iteration_count_3_reviewed": status == "PASS",
    "iteration_1_reviewed": status == "PASS",
    "iteration_2_reviewed": status == "PASS",
    "iteration_3_reviewed": status == "PASS",
    "iteration_3_stop_after_3_reviewed": status == "PASS",
    "truth_boundary_reviewed": status == "PASS",
    "first_bounded_controlled_loop_execution_canonical": status == "PASS",
    "bounded_loop_repeatability_report_required_next": status == "PASS",

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
        "SOCC_FIRST_BOUNDED_CONTROLLED_LOOP_EXECUTION_REVIEW_PASS_CANONICAL_NOT_DAEMON"
        if status == "PASS"
        else "SOCC_BOUNDED_CONTROLLED_LOOP_EXECUTION_REVIEW_FAIL"
    ),
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed first bounded controlled loop execution result: 3 iterations, hard stop, no daemon. "
        "Next lawful layer is bounded loop repeatability report, not persistent autonomy."
        if status == "PASS"
        else "Bounded controlled loop execution review blocked."
    ),
    "review": str(REVIEW),
    "proof": str(PROOF),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

md = "# BOUNDED CONTROLLED LOOP EXECUTION REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nFirst bounded controlled loop execution was completed and validated.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed the first bounded execution result. This is not another execution.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "First bounded controlled loop execution is canonical. Next lawful layer: bounded loop repeatability report.\n\n"
else:
    md += "Bounded controlled loop execution review is blocked. Repair required.\n\n"
md += "## Explicitly NOT done\n\n"
for x in [
    "no new loop execution",
    "persistent loop not started",
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

print("BOUNDED CONTROLLED LOOP EXECUTION REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("BOUNDED_CONTROLLED_LOOP_EXECUTION_REVIEW_SEALED::" + str(status == "PASS"))
print("BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATED::" + str(status == "PASS"))
print("BOUNDED_CONTROLLED_LOOP_EXECUTION_COMPLETED_REVIEWED::" + str(status == "PASS"))
print("BOUNDED_CONTROLLED_LOOP_ITERATION_COUNT_3_REVIEWED::" + str(status == "PASS"))
print("ITERATION_1_REVIEWED::" + str(status == "PASS"))
print("ITERATION_2_REVIEWED::" + str(status == "PASS"))
print("ITERATION_3_REVIEWED::" + str(status == "PASS"))
print("ITERATION_3_STOP_AFTER_3_REVIEWED::" + str(status == "PASS"))
print("TRUTH_BOUNDARY_REVIEWED::" + str(status == "PASS"))
print("FIRST_BOUNDED_CONTROLLED_LOOP_EXECUTION_CANONICAL::" + str(status == "PASS"))
print("BOUNDED_LOOP_REPEATABILITY_REPORT_REQUIRED_NEXT::" + str(status == "PASS"))
print("DAEMON_RUNNING::False")
print("SCHEDULER_INSTALLED::False")
print("BACKGROUND_LOOP_ENABLED::False")
print("NETWORK_USED::False")
print("QUEUE_WIDENING_ALLOWED::False")
print("ENTITY_BIRTH_ALLOWED::False")
print("ANNA_BIRTH_ALLOWED::False")
print("AGI_CLAIM_ALLOWED::False")
print("REAL_NEXT::" + real_next)
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if status == "PASS" else 1)

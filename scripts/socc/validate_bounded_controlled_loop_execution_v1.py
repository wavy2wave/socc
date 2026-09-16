import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "validate_bounded_controlled_loop_execution_v1"
NEXT = "review_bounded_controlled_loop_execution_v1"
REPAIR = "repair_validate_bounded_controlled_loop_execution_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

EXECUTION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_RUN_V1_PROOF.json"
EXECUTION_RUN = ROOT / "core/socc/controlled_loop/bounded_execution_run/BOUNDED_CONTROLLED_LOOP_EXECUTION_RUN_V1.json"
EXECUTION_RUN_MD = ROOT / "core/socc/controlled_loop/bounded_execution_run/BOUNDED_CONTROLLED_LOOP_EXECUTION_RUN_V1.md"
EXECUTION_MEMORY = ROOT / "MEMORY_WAVE/reports/controlled_loop/BOUNDED_CONTROLLED_LOOP_EXECUTION_RUN_V1_MEMORY.json"

STEP_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_V1_PROOF.json"
STEP_REVIEW_REPAIR_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_STEP_REVIEW_ROUTE_TRANSITION_REPAIR_V1_PROOF.json"

ITER_DIR = ROOT / "core/socc/controlled_loop/bounded_execution_run/iterations"
ITER_1 = ITER_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_ITERATION_1_V1_PROOF.json"
ITER_2 = ITER_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_ITERATION_2_V1_PROOF.json"
ITER_3 = ITER_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_ITERATION_3_V1_PROOF.json"

VALIDATION_DIR = ROOT / "core/socc/controlled_loop/bounded_execution_run/validation"
VALIDATION = VALIDATION_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_V1.json"
VALIDATION_MD = VALIDATION_DIR / "BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/controlled_loop/BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_V1_MEMORY.json"

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

execution_proof = read_json(EXECUTION_PROOF)
execution_run = read_json(EXECUTION_RUN)
execution_memory = read_json(EXECUTION_MEMORY)

step_review = read_json(STEP_REVIEW_PROOF)
step_review_repair = read_json(STEP_REVIEW_REPAIR_PROOF)

iter1 = read_json(ITER_1)
iter2 = read_json(ITER_2)
iter3 = read_json(ITER_3)
iterations = [iter1, iter2, iter3]

truth_boundary = (
    "Validation only. This validates the first bounded controlled loop execution run. "
    "It does not execute another loop, does not launch daemon/scheduler/background autonomy, does not widen queue, "
    "does not birth Entity/ANNA, does not approve final canon, and does not claim AGI."
)

checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_ok": get_next(route) == EXPECTED_CURRENT,
    "route_upstream_points_to_execution_proof": route.get("upstream_proof") == str(EXECUTION_PROOF),
    "route_last_committed_execute": route.get("last_committed_step") == "execute_bounded_controlled_loop_v1",
    "route_execution_completed": route.get("bounded_controlled_loop_execution_completed") is True,
    "route_iteration_count_3": route.get("bounded_controlled_loop_iteration_count") == 3,
    "route_hard_stop_after_3": route.get("bounded_controlled_loop_hard_stop_after_3") is True,

    "execution_proof_exists": EXECUTION_PROOF.exists(),
    "execution_proof_status_pass": status_pass(execution_proof),
    "execution_proof_capability_ok": execution_proof.get("capability") == "BOUNDED_CONTROLLED_LOOP_EXECUTION_COMPLETED",
    "execution_proof_real_next_ok": get_next(execution_proof) == EXPECTED_CURRENT,
    "execution_proof_hard_failures_empty": execution_proof.get("hard_failures") == [],

    "execution_run_exists": EXECUTION_RUN.exists(),
    "execution_run_md_exists": EXECUTION_RUN_MD.exists(),
    "execution_memory_exists": EXECUTION_MEMORY.exists(),

    "execution_started_true": execution_proof.get("bounded_controlled_loop_execution_started") is True,
    "execution_completed_true": execution_proof.get("bounded_controlled_loop_execution_completed") is True,
    "execution_iteration_count_3": execution_proof.get("bounded_controlled_loop_iteration_count") == 3,
    "execution_hard_stop_after_3": execution_proof.get("bounded_controlled_loop_hard_stop_after_3") is True,

    "iteration_files_count_3": len(execution_proof.get("iteration_files") or []) == 3,
    "iteration_1_file_exists": ITER_1.exists(),
    "iteration_2_file_exists": ITER_2.exists(),
    "iteration_3_file_exists": ITER_3.exists(),

    "iteration_1_pass_flag": execution_proof.get("iteration_1_pass") is True,
    "iteration_2_pass_flag": execution_proof.get("iteration_2_pass") is True,
    "iteration_3_pass_flag": execution_proof.get("iteration_3_pass") is True,
    "iteration_3_stop_after_3_flag": execution_proof.get("iteration_3_stop_after_3") is True,

    "iteration_1_status_pass": iter1.get("status") == "PASS",
    "iteration_2_status_pass": iter2.get("status") == "PASS",
    "iteration_3_status_pass": iter3.get("status") == "PASS",

    "iteration_1_index_ok": iter1.get("iteration_index") == 1,
    "iteration_2_index_ok": iter2.get("iteration_index") == 2,
    "iteration_3_index_ok": iter3.get("iteration_index") == 3,

    "iteration_1_continue": iter1.get("stop_condition_result") == "CONTINUE",
    "iteration_2_continue": iter2.get("stop_condition_result") == "CONTINUE",
    "iteration_3_stop": iter3.get("stop_condition_result") == "STOP_AFTER_3_REACHED",

    "iteration_1_no_bypass": iter1.get("bypass_detector_result") == "NO_BYPASS_DETECTED",
    "iteration_2_no_bypass": iter2.get("bypass_detector_result") == "NO_BYPASS_DETECTED",
    "iteration_3_no_bypass": iter3.get("bypass_detector_result") == "NO_BYPASS_DETECTED",

    "iteration_1_effect_pass": str(iter1.get("effect_audit_result", "")).startswith("PASS"),
    "iteration_2_effect_pass": str(iter2.get("effect_audit_result", "")).startswith("PASS"),
    "iteration_3_effect_pass": str(iter3.get("effect_audit_result", "")).startswith("PASS"),

    "route_updated_to_validate_execution": execution_proof.get("route_lawful_next_updated_to_validate_execution") is True,
    "panel_matches_route": execution_proof.get("panel_lawful_next_matches_route") is True,
    "pulse_matches_route": execution_proof.get("pulse_lawful_next_matches_route") is True,
    "progress_matches_route": execution_proof.get("progress_lawful_next_matches_route") is True,
    "route_upstream_points_to_execution_proof_claim": execution_proof.get("route_upstream_points_to_execution_proof") is True,

    "current_panel_matches_route": get_next(panel) == get_next(route),
    "current_pulse_matches_route": get_next(pulse) == get_next(route),
    "current_progress_matches_route": get_next(progress) == get_next(route),

    "step_review_proof_exists": STEP_REVIEW_PROOF.exists(),
    "step_review_status_pass": status_pass(step_review),
    "step_review_sealed": step_review.get("bounded_controlled_loop_execution_step_review_sealed") is True,
    "step_review_repair_exists": STEP_REVIEW_REPAIR_PROOF.exists(),
    "step_review_repair_status_pass": status_pass(step_review_repair),
    "step_review_repair_updated_to_execute": step_review_repair.get("route_lawful_next_updated_to_execute") is True,

    "daemon_false": execution_proof.get("daemon_running") is False,
    "scheduler_false": execution_proof.get("scheduler_installed") is False,
    "background_false": execution_proof.get("background_loop_enabled") is False,
    "network_false": execution_proof.get("network_used") is False,
    "queue_false": execution_proof.get("queue_widening_allowed") is False,
    "entity_false": execution_proof.get("entity_birth_allowed") is False,
    "anna_false": execution_proof.get("anna_birth_allowed") is False,
    "agi_false": execution_proof.get("agi_claim_allowed") is False,

    "validation_does_not_execute_another_loop": True,
    "validation_does_not_launch_daemon": True,
    "validation_does_not_install_scheduler": True,
    "validation_does_not_enable_background": True,
    "validation_does_not_widen_queue": True,
    "validation_does_not_birth_entity": True,
    "validation_does_not_birth_anna": True,
    "validation_does_not_claim_agi": True,
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
    ("execution_proof", execution_proof),
    ("execution_run", execution_run),
]:
    for key in FORBIDDEN_FLAGS:
        checks[f"{label}_{key}_false_or_absent"] = false_or_absent(obj, key)

hard = [{"code": "VALIDATION_CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

capability = (
    "BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATED"
    if status == "PASS"
    else "BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_BLOCKED"
)

real_next = NEXT if status == "PASS" else REPAIR

validation = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "VALIDATED" if status == "PASS" else "BLOCKED",
    "capability": capability,

    "source_execution_proof": str(EXECUTION_PROOF),
    "source_execution_run": str(EXECUTION_RUN),
    "source_iteration_1": str(ITER_1),
    "source_iteration_2": str(ITER_2),
    "source_iteration_3": str(ITER_3),
    "source_step_review_proof": str(STEP_REVIEW_PROOF),

    "bounded_controlled_loop_execution_validated": status == "PASS",
    "bounded_controlled_loop_execution_completed_validated": status == "PASS",
    "bounded_controlled_loop_iteration_count_3_validated": status == "PASS",
    "iteration_1_validated": status == "PASS",
    "iteration_2_validated": status == "PASS",
    "iteration_3_validated": status == "PASS",
    "iteration_3_stop_after_3_validated": status == "PASS",
    "route_panel_pulse_progress_validated": status == "PASS",
    "truth_boundary_validated": status == "PASS",
    "ready_for_review": status == "PASS",

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
validation["validation_hash"] = h24(validation)

proof = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "validation": str(VALIDATION),
    "validation_md": str(VALIDATION_MD),
    "memory": str(MEMORY),

    "bounded_controlled_loop_execution_validated": status == "PASS",
    "bounded_controlled_loop_execution_completed_validated": status == "PASS",
    "bounded_controlled_loop_iteration_count_3_validated": status == "PASS",
    "iteration_1_validated": status == "PASS",
    "iteration_2_validated": status == "PASS",
    "iteration_3_validated": status == "PASS",
    "iteration_3_stop_after_3_validated": status == "PASS",
    "route_panel_pulse_progress_validated": status == "PASS",
    "truth_boundary_validated": status == "PASS",
    "ready_for_review": status == "PASS",

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
        "SOCC_BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_PASS_READY_FOR_REVIEW_NOT_DAEMON"
        if status == "PASS"
        else "SOCC_BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_FAIL"
    ),
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATION_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC validated first bounded controlled loop execution: 3 iterations, hard stop after 3, no daemon/scheduler/background."
        if status == "PASS"
        else "Bounded controlled loop execution validation blocked."
    ),
    "validation": str(VALIDATION),
    "proof": str(PROOF),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

md = "# BOUNDED CONTROLLED LOOP EXECUTION VALIDATION V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nBounded controlled loop execution was completed with 3 iterations and hard stop.\n\n"
md += "## ДЕЙСТВИЕ\n\nValidated execution proof, iteration proofs, route coherence and truth boundary.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Bounded controlled loop execution is validated and ready for review.\n\n"
else:
    md += "Bounded controlled loop execution validation is blocked. Repair required.\n\n"
md += "## Explicitly NOT done\n\n"
for x in [
    "no new loop execution",
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

write_json(VALIDATION, validation)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(VALIDATION_MD, md)

print("BOUNDED CONTROLLED LOOP EXECUTION VALIDATION :: " + status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + capability)
print("VALIDATION::" + str(VALIDATION))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("BOUNDED_CONTROLLED_LOOP_EXECUTION_VALIDATED::" + str(status == "PASS"))
print("BOUNDED_CONTROLLED_LOOP_EXECUTION_COMPLETED_VALIDATED::" + str(status == "PASS"))
print("BOUNDED_CONTROLLED_LOOP_ITERATION_COUNT_3_VALIDATED::" + str(status == "PASS"))
print("ITERATION_1_VALIDATED::" + str(status == "PASS"))
print("ITERATION_2_VALIDATED::" + str(status == "PASS"))
print("ITERATION_3_VALIDATED::" + str(status == "PASS"))
print("ITERATION_3_STOP_AFTER_3_VALIDATED::" + str(status == "PASS"))
print("ROUTE_PANEL_PULSE_PROGRESS_VALIDATED::" + str(status == "PASS"))
print("TRUTH_BOUNDARY_VALIDATED::" + str(status == "PASS"))
print("READY_FOR_REVIEW::" + str(status == "PASS"))
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

import json
import hashlib
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
PROOF_DIR = ROOT / "core/socc/approved_autonomy_lane_runner/proof"

MATERIALIZATION_PROOF = PROOF_DIR / "SELF_BUILDING_TICK_EXECUTABLE_MATERIALIZATION_V1_PROOF.json"
CONTRACT_PROOF = PROOF_DIR / "SELF_BUILDING_TICK_TASK_CONTRACT_V1_PROOF.json"
APPROVAL_PROOF = PROOF_DIR / "ONE_BOUNDED_SELF_BUILDING_TICK_OPERATOR_APPROVAL_V1_PROOF.json"

TARGET_SCRIPT = ROOT / "scripts/socc/build_self_building_tick_execution_plan_v1.py"
TASK_PROOF = PROOF_DIR / "SELF_BUILDING_TICK_EXECUTION_PLAN_V1_PROOF.json"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/tick_run"
RUN = OUT_DIR / "ONE_BOUNDED_SELF_BUILDING_TICK_RUN_V1.json"
RUN_MD = OUT_DIR / "ONE_BOUNDED_SELF_BUILDING_TICK_RUN_V1.md"

PROOF = PROOF_DIR / "ONE_BOUNDED_SELF_BUILDING_TICK_RUN_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/ONE_BOUNDED_SELF_BUILDING_TICK_RUN_V1_MEMORY.json"

EXPECTED_MATERIALIZATION_CAPABILITY = "SELF_BUILDING_TICK_EXECUTABLE_MATERIALIZED_READY_FOR_ONE_BOUNDED_TICK"
EXPECTED_NEXT = "run_one_bounded_self_building_tick_v1"
TARGET_SCRIPT_STR = "scripts/socc/build_self_building_tick_execution_plan_v1.py"

def now_utc():
    return datetime.now(timezone.utc).isoformat()

def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text).rstrip() + "\n", encoding="utf-8")

def h24(obj):
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]

materialization = read_json(MATERIALIZATION_PROOF)
contract = read_json(CONTRACT_PROOF)
approval = read_json(APPROVAL_PROOF)

pre_checks = {
    "materialization_proof_exists": MATERIALIZATION_PROOF.exists(),
    "materialization_status_pass": materialization.get("status") == "PASS",
    "materialization_capability_ok": materialization.get("capability") == EXPECTED_MATERIALIZATION_CAPABILITY,
    "materialization_real_next_ok": materialization.get("real_next") == EXPECTED_NEXT,
    "materialized_executable_ok": materialization.get("materialized_executable") == TARGET_SCRIPT_STR,
    "ready_for_one_bounded_self_building_tick": materialization.get("ready_for_one_bounded_self_building_tick") is True,
    "materialization_task_not_executed_now": materialization.get("task_executed_now") is False,

    "contract_proof_exists": CONTRACT_PROOF.exists(),
    "contract_status_pass": contract.get("status") == "PASS",
    "contract_ready_for_executable_materialization": contract.get("ready_for_executable_materialization") is True,

    "approval_proof_exists": APPROVAL_PROOF.exists(),
    "approval_status_pass": approval.get("status") == "PASS",
    "approval_one_tick_only": approval.get("one_tick_only") is True,
    "approval_tick_approved": approval.get("bounded_self_building_tick_approved") is True,
    "approval_tick_not_executed": approval.get("bounded_self_building_tick_executed") is False,

    "target_script_exists": TARGET_SCRIPT.exists(),

    "run_is_one_tick_only": True,
    "run_does_not_start_daemon": True,
    "run_does_not_install_scheduler": True,
    "run_does_not_enable_background_loop": True,
    "run_does_not_use_network": True,
    "run_does_not_widen_queue": True,
    "run_does_not_birth_entity": True,
    "run_does_not_birth_anna": True,
    "run_does_not_claim_agi": True,
    "run_does_not_approve_final_canon": True,
}

for key in [
    "runtime_launch_approved",
    "runtime_execution_allowed",
    "runtime_autonomy_enabled",
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
    pre_checks[f"materialization_{key}_false"] = materialization.get(key) is False

pre_hard = [{"code": "PRECHECK_FAIL", "check": k, "actual": v} for k, v in pre_checks.items() if v is not True]

worker_returncode = None
worker_stdout = ""
worker_stderr = ""
task_proof_after = {}

if not pre_hard:
    proc = subprocess.run(
        [sys.executable, str(TARGET_SCRIPT)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=60,
    )
    worker_returncode = proc.returncode
    worker_stdout = proc.stdout[-12000:]
    worker_stderr = proc.stderr[-12000:]
    task_proof_after = read_json(TASK_PROOF)

post_checks = {
    "worker_returncode_zero": worker_returncode == 0,
    "task_proof_exists": TASK_PROOF.exists(),
    "task_proof_status_pass": task_proof_after.get("status") == "PASS",
    "execution_plan_built": task_proof_after.get("self_building_tick_execution_plan_built") is True,
    "bounded_self_building_tick_executed_by_task": task_proof_after.get("bounded_self_building_tick_executed") is True,
    "selected_improvement_target_ok": task_proof_after.get("selected_improvement_target") == "build_self_building_runtime_status_panel_v1",
    "task_real_next_ok": task_proof_after.get("real_next") == "validate_self_building_tick_execution_plan_v1",
    "task_hard_failures_empty": task_proof_after.get("hard_failures") == [],
    "task_self_building_mode_enabled_false": task_proof_after.get("self_building_mode_enabled") is False,
    "task_daemon_false": task_proof_after.get("daemon_running") is False,
    "task_scheduler_false": task_proof_after.get("scheduler_installed") is False,
    "task_background_false": task_proof_after.get("background_loop_enabled") is False,
    "task_network_false": task_proof_after.get("network_used") is False,
    "task_queue_false": task_proof_after.get("queue_widening_allowed") is False,
    "task_entity_birth_false": task_proof_after.get("entity_birth_allowed") is False,
    "task_anna_birth_false": task_proof_after.get("anna_birth_allowed") is False,
    "task_agi_false": task_proof_after.get("agi_claim_allowed") is False,
}

post_hard = [{"code": "POSTCHECK_FAIL", "check": k, "actual": v} for k, v in post_checks.items() if v is not True]
hard = pre_hard + post_hard
status = "PASS" if not hard else "FAIL"

if status == "PASS":
    capability = "ONE_BOUNDED_SELF_BUILDING_TICK_EXECUTED_EXECUTION_PLAN_BUILT"
    real_next = "validate_self_building_tick_execution_plan_v1"
    final_socc_status = "SOCC_ONE_BOUNDED_SELF_BUILDING_TICK_PASS_EXECUTION_PLAN_READY_FOR_VALIDATION_NOT_DAEMON_NOT_AGI"
else:
    capability = "ONE_BOUNDED_SELF_BUILDING_TICK_RUN_BLOCKED_OR_FAILED"
    real_next = "repair_one_bounded_self_building_tick_run_v1"
    final_socc_status = "SOCC_ONE_BOUNDED_SELF_BUILDING_TICK_RUN_FAIL"

truth_boundary = (
    "One bounded self-building tick run only. This runs exactly one approved executable task: "
    "build_self_building_tick_execution_plan_v1.py. It does not enable persistent self-building mode, launch daemon, "
    "install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

run = {
    "id": "ONE_BOUNDED_SELF_BUILDING_TICK_RUN_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "source_materialization_proof": str(MATERIALIZATION_PROOF),
    "source_contract_proof": str(CONTRACT_PROOF),
    "source_approval_proof": str(APPROVAL_PROOF),
    "target_script": str(TARGET_SCRIPT),
    "task_proof": str(TASK_PROOF),
    "worker_returncode": worker_returncode,
    "worker_stdout_tail": worker_stdout,
    "worker_stderr_tail": worker_stderr,

    "one_bounded_self_building_tick_executed": status == "PASS",
    "bounded_self_building_tick_executed": status == "PASS",
    "task_executed": status == "PASS",
    "selected_improvement_target": task_proof_after.get("selected_improvement_target") if status == "PASS" else None,

    "self_building_mode_enabled": False,
    "runtime_launch_approved": False,
    "runtime_execution_allowed": False,
    "runtime_autonomy_enabled": False,
    "daemon_running": False,
    "scheduler_installed": False,
    "background_loop_enabled": False,
    "network_used": False,
    "queue_widening_allowed": False,
    "entity_birth_allowed": False,
    "anna_birth_allowed": False,
    "agi_claim_allowed": False,
    "final_canon_approval_allowed": False,

    "pre_checks": pre_checks,
    "post_checks": post_checks,
    "hard_failures": hard,
    "real_next": real_next,
    "truth_boundary": truth_boundary
}
run["run_hash"] = h24(run)

proof = {
    "id": "ONE_BOUNDED_SELF_BUILDING_TICK_RUN_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "run": str(RUN),
    "run_md": str(RUN_MD),
    "memory": str(MEMORY),
    "target_script": str(TARGET_SCRIPT),
    "task_proof": str(TASK_PROOF),
    "worker_returncode": worker_returncode,

    "one_bounded_self_building_tick_executed": status == "PASS",
    "bounded_self_building_tick_executed": status == "PASS",
    "task_executed": status == "PASS",
    "selected_improvement_target": task_proof_after.get("selected_improvement_target") if status == "PASS" else None,

    "self_building_mode_enabled": False,
    "runtime_launch_approved": False,
    "runtime_execution_allowed": False,
    "runtime_autonomy_enabled": False,
    "daemon_running": False,
    "scheduler_installed": False,
    "background_loop_enabled": False,
    "network_used": False,
    "queue_widening_allowed": False,
    "entity_birth_allowed": False,
    "anna_birth_allowed": False,
    "agi_claim_allowed": False,
    "final_canon_approval_allowed": False,

    "pre_checks": pre_checks,
    "post_checks": post_checks,
    "hard_failures": hard,
    "real_next": real_next,
    "final_socc_status": final_socc_status,
    "truth_boundary": truth_boundary
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "ONE_BOUNDED_SELF_BUILDING_TICK_RUN_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC executed exactly one bounded self-building tick. The tick produced an execution plan selecting "
        "runtime status panel / observability as next autonomy improvement target."
    ),
    "proof": str(PROOF),
    "run": str(RUN),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

md = "# ONE BOUNDED SELF-BUILDING TICK RUN V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nSelf-building executable was materialized and ready for one bounded tick.\n\n"
md += "## ДЕЙСТВИЕ\n\nRan exactly one bounded self-building task executable.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in pre_checks.items():
    md += "- " + k + ": " + str(v) + "\n"
for k, v in post_checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "One bounded self-building tick executed. It built an execution plan for improving autonomy observability/status panel.\n\n"
else:
    md += "One bounded self-building tick failed or was blocked. Repair required.\n\n"
md += "## Selected improvement target\n\n" + str(task_proof_after.get("selected_improvement_target")) + "\n\n"
md += "## Explicitly NOT done\n\n"
for x in [
    "persistent self-building mode not enabled",
    "runtime not launched",
    "daemon not started",
    "scheduler not installed",
    "background loop not enabled",
    "network not used",
    "queue not widened",
    "Entity not born",
    "ANNA not born",
    "AGI not claimed",
]:
    md += "- " + x + "\n"
md += "\n## lawful_next\n\n" + real_next + "\n\n"
md += "## Truth boundary\n\n" + truth_boundary + "\n"

write_json(RUN, run)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(RUN_MD, md)

print("ONE BOUNDED SELF-BUILDING TICK RUN :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("RUN::" + str(RUN))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("TARGET_SCRIPT::" + str(TARGET_SCRIPT))
print("WORKER_RETURNCODE::" + str(worker_returncode))
print("ONE_BOUNDED_SELF_BUILDING_TICK_EXECUTED::" + str(status == "PASS"))
print("BOUNDED_SELF_BUILDING_TICK_EXECUTED::" + str(status == "PASS"))
print("TASK_EXECUTED::" + str(status == "PASS"))
print("SELECTED_IMPROVEMENT_TARGET::" + str(task_proof_after.get("selected_improvement_target") if status == "PASS" else "NONE"))
print("SELF_BUILDING_MODE_ENABLED::False")
print("RUNTIME_LAUNCH_APPROVED::False")
print("RUNTIME_EXECUTION_ALLOWED::False")
print("RUNTIME_AUTONOMY_ENABLED::False")
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

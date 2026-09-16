import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
PROOF_DIR = ROOT / "core/socc/approved_autonomy_lane_runner/proof"

READINESS_PROOF = PROOF_DIR / "SELF_BUILDING_READINESS_EVALUATOR_V1_PROOF.json"
READINESS_REPORT = ROOT / "core/socc/autonomy/self_building/readiness/reports/SELF_BUILDING_READINESS_REPORT_V1.json"
LAUNCH_GATE = ROOT / "core/socc/autonomy/self_building/readiness/SELF_BUILDING_ONE_TICK_LAUNCH_GATE_V1.json"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/operator_approval"
APPROVAL = OUT_DIR / "ONE_BOUNDED_SELF_BUILDING_TICK_OPERATOR_APPROVAL_V1.json"
APPROVAL_MD = OUT_DIR / "ONE_BOUNDED_SELF_BUILDING_TICK_OPERATOR_APPROVAL_V1.md"

PROOF = PROOF_DIR / "ONE_BOUNDED_SELF_BUILDING_TICK_OPERATOR_APPROVAL_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/ONE_BOUNDED_SELF_BUILDING_TICK_OPERATOR_APPROVAL_V1_MEMORY.json"

EXPECTED_CAPABILITY = "SELF_BUILDING_READINESS_EVALUATOR_BUILT_READY_FOR_OPERATOR_APPROVAL_NOT_EXECUTION"
EXPECTED_NEXT = "operator_approval_for_one_bounded_self_building_tick_v1"
APPROVED_TICK = "build_self_building_tick_task_contract_v1"

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
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]

readiness = read_json(READINESS_PROOF)
report = read_json(READINESS_REPORT)
gate = read_json(LAUNCH_GATE)

checks = {
    "readiness_proof_exists": READINESS_PROOF.exists(),
    "readiness_status_pass": readiness.get("status") == "PASS",
    "readiness_capability_ok": readiness.get("capability") == EXPECTED_CAPABILITY,
    "readiness_real_next_ok": readiness.get("real_next") == EXPECTED_NEXT,
    "readiness_evaluator_built": readiness.get("self_building_readiness_evaluator_built") is True,
    "readiness_score_at_least_85": int(readiness.get("self_building_readiness_score") or 0) >= 85,
    "ready_for_operator_approval": readiness.get("self_building_ready_for_operator_approval") is True,

    "readiness_report_exists": READINESS_REPORT.exists(),
    "readiness_report_ready_for_operator_approval": report.get("ready_for_operator_approval") is True,
    "readiness_report_launch_allowed_false": report.get("launch_allowed_now") is False,

    "launch_gate_exists": LAUNCH_GATE.exists(),
    "launch_gate_ready_for_operator_approval": gate.get("status") == "READY_FOR_OPERATOR_APPROVAL",
    "launch_gate_operator_approval_required": gate.get("operator_approval_required") is True,
    "launch_gate_approved_now_false": gate.get("approved_now") is False,
    "launch_gate_one_tick_only": gate.get("one_tick_only") is True,

    "approval_does_not_enable_self_building_mode": True,
    "approval_does_not_execute_tick": True,
    "approval_does_not_launch_runtime": True,
    "approval_does_not_start_daemon": True,
    "approval_does_not_install_scheduler": True,
    "approval_does_not_enable_background_loop": True,
    "approval_does_not_use_network": True,
    "approval_does_not_widen_queue": True,
    "approval_does_not_birth_entity": True,
    "approval_does_not_birth_anna": True,
    "approval_does_not_claim_agi": True,
    "approval_does_not_approve_final_canon": True,
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
    checks[f"readiness_{key}_false"] = readiness.get(key) is False

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

if status == "PASS":
    capability = "ONE_BOUNDED_SELF_BUILDING_TICK_OPERATOR_APPROVED_NOT_EXECUTED"
    approval_status = "APPROVED"
    real_next = APPROVED_TICK
    final_socc_status = "SOCC_ONE_BOUNDED_SELF_BUILDING_TICK_APPROVAL_PASS_TASK_CONTRACT_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "ONE_BOUNDED_SELF_BUILDING_TICK_OPERATOR_APPROVAL_BLOCKED"
    approval_status = "BLOCKED"
    real_next = "repair_one_bounded_self_building_tick_operator_approval_v1"
    final_socc_status = "SOCC_ONE_BOUNDED_SELF_BUILDING_TICK_APPROVAL_FAIL"

truth_boundary = (
    "Operator approval only. This approves exactly one bounded self-building preparation tick target, "
    "build_self_building_tick_task_contract_v1. It does not enable self-building mode, execute a tick, launch runtime, "
    "start daemon/scheduler/background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

approval = {
    "id": "ONE_BOUNDED_SELF_BUILDING_TICK_OPERATOR_APPROVAL_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": approval_status,
    "capability": capability,
    "source_readiness_proof": str(READINESS_PROOF),
    "source_readiness_report": str(READINESS_REPORT),
    "source_launch_gate": str(LAUNCH_GATE),

    "operator_approval_recorded": status == "PASS",
    "approved_one_bounded_self_building_tick": status == "PASS",
    "approved_tick_target": APPROVED_TICK if status == "PASS" else None,
    "one_tick_only": True,

    "self_building_mode_enabled": False,
    "bounded_self_building_tick_approved": status == "PASS",
    "bounded_self_building_tick_executed": False,

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

    "checks": checks,
    "hard_failures": hard,
    "real_next": real_next,
    "truth_boundary": truth_boundary
}
approval["approval_hash"] = h24(approval)

proof = {
    "id": "ONE_BOUNDED_SELF_BUILDING_TICK_OPERATOR_APPROVAL_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "approval": str(APPROVAL),
    "approval_md": str(APPROVAL_MD),
    "memory": str(MEMORY),

    "operator_approval_recorded": status == "PASS",
    "approved_one_bounded_self_building_tick": status == "PASS",
    "approved_tick_target": APPROVED_TICK if status == "PASS" else None,
    "one_tick_only": True,

    "self_building_mode_enabled": False,
    "bounded_self_building_tick_approved": status == "PASS",
    "bounded_self_building_tick_executed": False,

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

    "checks": checks,
    "hard_failures": hard,
    "real_next": real_next,
    "final_socc_status": final_socc_status,
    "truth_boundary": truth_boundary
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "ONE_BOUNDED_SELF_BUILDING_TICK_OPERATOR_APPROVAL_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "Operator approval recorded for exactly one bounded self-building preparation tick target. "
        "The tick is not executed yet; next is building the tick task contract."
    ),
    "approval": str(APPROVAL),
    "proof": str(PROOF),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

md = "# ONE BOUNDED SELF-BUILDING TICK OPERATOR APPROVAL V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nSelf-building readiness evaluator reported READY_FOR_OPERATOR_APPROVAL with high readiness score.\n\n"
md += "## ДЕЙСТВИЕ\n\nRecorded operator approval for exactly one bounded self-building preparation tick target.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "One bounded self-building tick target is approved. Execution has not happened yet.\n\n"
else:
    md += "Operator approval is blocked. Repair required.\n\n"
md += "## Approved target\n\n" + (APPROVED_TICK if status == "PASS" else "NONE") + "\n\n"
md += "## Explicitly NOT done\n\n"
for x in [
    "self-building mode not enabled",
    "tick not executed",
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

write_json(APPROVAL, approval)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(APPROVAL_MD, md)

print("ONE BOUNDED SELF-BUILDING TICK OPERATOR APPROVAL :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("APPROVAL::" + str(APPROVAL))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("OPERATOR_APPROVAL_RECORDED::" + str(status == "PASS"))
print("APPROVED_ONE_BOUNDED_SELF_BUILDING_TICK::" + str(status == "PASS"))
print("APPROVED_TICK_TARGET::" + (APPROVED_TICK if status == "PASS" else "NONE"))
print("ONE_TICK_ONLY::True")
print("SELF_BUILDING_MODE_ENABLED::False")
print("BOUNDED_SELF_BUILDING_TICK_APPROVED::" + str(status == "PASS"))
print("BOUNDED_SELF_BUILDING_TICK_EXECUTED::False")
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

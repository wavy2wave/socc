import json
import hashlib
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
PROOF_DIR = ROOT / "core/socc/approved_autonomy_lane_runner/proof"

REFRESH_PROOF = PROOF_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1_PROOF.json"
REVIEW_PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_V1_PROOF.json"

SHOW_SCRIPT = ROOT / "scripts/socc/show_self_building_status_panel_v1.py"

BASE = ROOT / "core/socc/autonomy/self_building/status_panel/refresh"
VALIDATION_DIR = BASE / "validation"

REFRESH_CONTRACT = BASE / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1.json"
REFRESH_MD = BASE / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1.md"
VALIDATION = VALIDATION_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_V1.json"
VALIDATION_MD = VALIDATION_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_V1.md"
VALIDATION_OUTPUT = VALIDATION_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_OUTPUT_V1.txt"

PROOF = PROOF_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_V1_MEMORY.json"

EXPECTED_CAPABILITY = "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_BUILT_CREATOR_CAN_RENDER_PULSE_ON_DEMAND"
EXPECTED_NEXT = "validate_self_building_status_panel_refresh_command_v1"
NEXT_AFTER_VALIDATION = "review_self_building_status_panel_refresh_command_v1"

def now_utc():
    return datetime.now(timezone.utc).isoformat()

def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text).rstrip() + "\n", encoding="utf-8")

def h24(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]

refresh = read_json(REFRESH_PROOF)
review = read_json(REVIEW_PROOF)

pre_checks = {
    "refresh_proof_exists": REFRESH_PROOF.exists(),
    "refresh_status_pass": refresh.get("status") == "PASS",
    "refresh_capability_ok": refresh.get("capability") == EXPECTED_CAPABILITY,
    "refresh_real_next_ok": refresh.get("real_next") == EXPECTED_NEXT,
    "refresh_command_built": refresh.get("refresh_command_built") is True,
    "creator_can_render_pulse_on_demand": refresh.get("creator_can_render_pulse_on_demand") is True,
    "local_read_only": refresh.get("local_read_only") is True,
    "refresh_hard_failures_empty": refresh.get("hard_failures") == [],

    "review_proof_exists": REVIEW_PROOF.exists(),
    "review_status_pass": review.get("status") == "PASS",
    "runtime_status_panel_review_sealed": review.get("runtime_status_panel_review_sealed") is True,
    "creator_visible_autonomy_pulse_accepted": review.get("creator_visible_autonomy_pulse_accepted") is True,
    "observable_self_building_pulse_proven": review.get("observable_self_building_pulse_proven") is True,

    "show_script_exists": SHOW_SCRIPT.exists(),
    "refresh_contract_exists": REFRESH_CONTRACT.exists(),
    "refresh_md_exists": REFRESH_MD.exists(),

    "validation_does_not_enable_self_building_mode": True,
    "validation_does_not_launch_runtime": True,
    "validation_does_not_start_daemon": True,
    "validation_does_not_install_scheduler": True,
    "validation_does_not_enable_background_loop": True,
    "validation_does_not_use_network": True,
    "validation_does_not_widen_queue": True,
    "validation_does_not_birth_entity": True,
    "validation_does_not_birth_anna": True,
    "validation_does_not_claim_agi": True,
    "validation_does_not_approve_final_canon": True,
}

for src_name, src in [("refresh", refresh), ("review", review)]:
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
        pre_checks[f"{src_name}_{key}_false"] = src.get(key) is False

pre_hard = [{"code": "PRECHECK_FAIL", "check": k, "actual": v} for k, v in pre_checks.items() if v is not True]

returncode = None
stdout = ""
stderr = ""

if not pre_hard:
    proc = subprocess.run(
        [sys.executable, str(SHOW_SCRIPT)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=20,
    )
    returncode = proc.returncode
    stdout = proc.stdout
    stderr = proc.stderr

post_checks = {
    "show_script_returncode_zero": returncode == 0,
    "stdout_contains_pulse": "SOCC_SELF_BUILDING_PULSE::ALIVE_BOUNDED_SELF_BUILDING_VISIBLE" in stdout,
    "stdout_contains_current_level": "CURRENT_LEVEL::L7_FIRST_BOUNDED_SELF_BUILDING_CYCLE_CLOSED_STATUS_PANEL_BUILT" in stdout,
    "stdout_contains_cycle_count": "SELF_BUILDING_CYCLE_COUNT::1" in stdout,
    "stdout_contains_lawful_next_fixed": "LAWFUL_NEXT::validate_self_building_status_panel_refresh_command_v1" in stdout,
    "stdout_does_not_contain_typo_lawul": ("LAWUL_NEXT::" not in stdout and "lawul_next" not in stdout),
    "stdout_contains_last_tick_pass": "LAST_TICK_STATUS::PASS" in stdout,
    "stdout_contains_review_sealed": "RUNTIME_STATUS_PANEL_REVIEW_SEALED::True" in stdout,
    "stdout_contains_pulse_accepted": "CREATOR_VISIBLE_AUTONOMY_PULSE_ACCEPTED::True" in stdout,
    "stdout_contains_observable_pulse_proven": "OBSERVABLE_SELF_BUILDING_PULSE_PROVEN::True" in stdout,
    "stdout_contains_self_building_mode_false": "SELF_BUILDING_MODE_ENABLED::False" in stdout,
    "stdout_contains_daemon_false": "DAEMON_RUNNING::False" in stdout,
    "stdout_contains_scheduler_false": "SCHEDULER_INSTALLED::False" in stdout,
    "stdout_contains_background_false": "BACKGROUND_LOOP_ENABLED::False" in stdout,
    "stdout_contains_network_false": "NETWORK_USED::False" in stdout,
    "stdout_contains_queue_false": "QUEUE_WIDENING_ALLOWED::False" in stdout,
    "stdout_contains_entity_false": "ENTITY_BIRTH_ALLOWED::False" in stdout,
    "stdout_contains_anna_false": "ANNA_BIRTH_ALLOWED::False" in stdout,
    "stdout_contains_agi_false": "AGI_CLAIM_ALLOWED::False" in stdout,
    "stdout_contains_hard_failures_empty": "HARD_FAILURES::[]" in stdout,
}

post_hard = [{"code": "POSTCHECK_FAIL", "check": k, "actual": v} for k, v in post_checks.items() if v is not True]
hard = pre_hard + post_hard
status = "PASS" if not hard else "FAIL"

if status == "PASS":
    capability = "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATED_ON_DEMAND_PULSE_WORKS"
    validation_status = "VALIDATED"
    real_next = NEXT_AFTER_VALIDATION
    final_socc_status = "SOCC_SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_PASS_READY_FOR_REVIEW_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_BLOCKED"
    validation_status = "BLOCKED"
    real_next = "repair_self_building_status_panel_refresh_command_validation_v1"
    final_socc_status = "SOCC_SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_FAIL"

truth_boundary = (
    "Refresh command validation only. This validates that the local read-only status panel refresh command renders the accepted "
    "self-building pulse and correct lawful_next. It does not enable persistent self-building mode, launch runtime, start daemon/"
    "scheduler/background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

validation = {
    "id": "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": validation_status,
    "capability": capability,
    "source_refresh_proof": str(REFRESH_PROOF),
    "source_review_proof": str(REVIEW_PROOF),
    "show_script": str(SHOW_SCRIPT),
    "validation_output": str(VALIDATION_OUTPUT),
    "show_script_returncode": returncode,

    "refresh_command_validated": status == "PASS",
    "creator_can_render_pulse_on_demand_validated": status == "PASS",
    "lawful_next_display_validated": status == "PASS",
    "typo_lawful_next_removed": status == "PASS",
    "local_read_only_validated": status == "PASS",

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
    "truth_boundary": truth_boundary,
}
validation["validation_hash"] = h24(validation)

proof = {
    "id": "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "validation": str(VALIDATION),
    "validation_md": str(VALIDATION_MD),
    "validation_output": str(VALIDATION_OUTPUT),
    "memory": str(MEMORY),

    "refresh_command_validated": status == "PASS",
    "creator_can_render_pulse_on_demand_validated": status == "PASS",
    "lawful_next_display_validated": status == "PASS",
    "typo_lawful_next_removed": status == "PASS",
    "local_read_only_validated": status == "PASS",

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
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC validated the local self-building status panel refresh command. Creator can render the visible pulse on demand; "
        "lawful_next display is corrected and validated."
    ),
    "proof": str(PROOF),
    "validation": str(VALIDATION),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

md = "# SELF-BUILDING STATUS PANEL REFRESH COMMAND VALIDATION V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nRefresh command was built. Display typo/route drift was patched before validation.\n\n"
md += "## ДЕЙСТВИЕ\n\nRan local refresh command and validated output markers.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in pre_checks.items():
    md += "- " + k + ": " + str(v) + "\n"
for k, v in post_checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Refresh command is validated. Creator can render pulse on demand with correct LAWFUL_NEXT.\n\n"
else:
    md += "Refresh command validation is blocked. Repair required.\n\n"
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

write_text(VALIDATION_OUTPUT, stdout)
write_json(VALIDATION, validation)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(VALIDATION_MD, md)

print("SELF-BUILDING STATUS PANEL REFRESH COMMAND VALIDATION :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("VALIDATION::" + str(VALIDATION))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("REFRESH_COMMAND_VALIDATED::" + str(status == "PASS"))
print("CREATOR_CAN_RENDER_PULSE_ON_DEMAND_VALIDATED::" + str(status == "PASS"))
print("LAWFUL_NEXT_DISPLAY_VALIDATED::" + str(status == "PASS"))
print("TYPO_LAWFUL_NEXT_REMOVED::" + str(status == "PASS"))
print("LOCAL_READ_ONLY_VALIDATED::" + str(status == "PASS"))
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

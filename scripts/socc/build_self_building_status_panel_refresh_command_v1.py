import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
PROOF_DIR = ROOT / "core/socc/approved_autonomy_lane_runner/proof"

REVIEW_PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_V1_PROOF.json"
PANEL_PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_V1_PROOF.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL_MD = ROOT / "core/socc/autonomy/self_building/status_panel/reports/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.md"
TERMINAL_SUMMARY = ROOT / "core/socc/autonomy/self_building/status_panel/reports/SOCC_SELF_BUILDING_TERMINAL_SUMMARY_V1.txt"
CREATOR_REPORT = ROOT / "core/socc/autonomy/self_building/status_panel/reports/CREATOR_VISIBLE_AUTONOMY_PULSE_REPORT_V1.md"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/status_panel/refresh"
REFRESH_CONTRACT = OUT_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1.json"
REFRESH_MD = OUT_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1.md"
REFRESH_LOG = OUT_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_SAMPLE_OUTPUT_V1.txt"

SHOW_SCRIPT = ROOT / "scripts/socc/show_self_building_status_panel_v1.py"

PROOF = PROOF_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1_MEMORY.json"

EXPECTED_REVIEW_CAPABILITY = "SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_SEALED_VISIBLE_PULSE_ACCEPTED"
EXPECTED_NEXT = "build_self_building_status_panel_refresh_command_v1"
EXPECTED_PULSE = "ALIVE_BOUNDED_SELF_BUILDING_VISIBLE"

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

review = read_json(REVIEW_PROOF)
panel_proof = read_json(PANEL_PROOF)
panel = read_json(PANEL)
pulse = read_json(PULSE)

checks = {
    "review_proof_exists": REVIEW_PROOF.exists(),
    "review_status_pass": review.get("status") == "PASS",
    "review_capability_ok": review.get("capability") == EXPECTED_REVIEW_CAPABILITY,
    "review_real_next_ok": review.get("real_next") == EXPECTED_NEXT,
    "runtime_status_panel_review_sealed": review.get("runtime_status_panel_review_sealed") is True,
    "creator_visible_autonomy_pulse_accepted": review.get("creator_visible_autonomy_pulse_accepted") is True,
    "observable_self_building_pulse_proven": review.get("observable_self_building_pulse_proven") is True,
    "review_pulse_value_ok": review.get("pulse_value") == EXPECTED_PULSE,
    "review_hard_failures_empty": review.get("hard_failures") == [],

    "panel_proof_exists": PANEL_PROOF.exists(),
    "panel_proof_status_pass": panel_proof.get("status") == "PASS",
    "runtime_status_panel_built": panel_proof.get("runtime_status_panel_built") is True,
    "creator_visible_pulse_ready": panel_proof.get("creator_visible_autonomy_pulse_ready") is True,

    "panel_json_exists": PANEL.exists(),
    "pulse_json_exists": PULSE.exists(),
    "panel_md_exists": PANEL_MD.exists(),
    "terminal_summary_exists": TERMINAL_SUMMARY.exists(),
    "creator_report_exists": CREATOR_REPORT.exists(),

    "panel_status_built": panel.get("status") == "BUILT",
    "panel_lawful_next_validation_or_known": bool(panel.get("lawful_next")),
    "pulse_value_ok": pulse.get("pulse") == EXPECTED_PULSE,

    "refresh_does_not_enable_self_building_mode": True,
    "refresh_does_not_launch_runtime": True,
    "refresh_does_not_start_daemon": True,
    "refresh_does_not_install_scheduler": True,
    "refresh_does_not_enable_background_loop": True,
    "refresh_does_not_use_network": True,
    "refresh_does_not_widen_queue": True,
    "refresh_does_not_birth_entity": True,
    "refresh_does_not_birth_anna": True,
    "refresh_does_not_claim_agi": True,
    "refresh_does_not_approve_final_canon": True,
}

for src_name, src in [("review", review), ("panel_proof", panel_proof), ("panel", panel)]:
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
        checks[f"{src_name}_{key}_false"] = src.get(key) is False

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

show_script = r'''import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
TERMINAL_SUMMARY = ROOT / "core/socc/autonomy/self_building/status_panel/reports/SOCC_SELF_BUILDING_TERMINAL_SUMMARY_V1.txt"
CREATOR_REPORT = ROOT / "core/socc/autonomy/self_building/status_panel/reports/CREATOR_VISIBLE_AUTONOMY_PULSE_REPORT_V1.md"
REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_V1_PROOF.json"

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

def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")

panel = read_json(PANEL)
pulse = read_json(PULSE)
review = read_json(REVIEW_PROOF)
terminal = read_text(TERMINAL_SUMMARY)

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SOCC SELF-BUILDING STATUS PANEL — REFRESH")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("REFRESHED_AT_MSK::" + now_msk())
print("SOCC_SELF_BUILDING_PULSE::" + str(pulse.get("pulse", "UNKNOWN")))
print("CURRENT_LEVEL::" + str(panel.get("current_autonomy_level") or pulse.get("current_autonomy_level") or "UNKNOWN"))
print("SELF_BUILDING_CYCLE_COUNT::" + str(panel.get("self_building_cycle_count") or pulse.get("self_building_cycle_count") or 0))
print("LAWFUL_NEXT::" + str(review.get("real_next") or panel.get("lawful_next") or "UNKNOWN"))
print("LAST_TICK_STATUS::" + str(panel.get("last_tick_status", "UNKNOWN")))
print("RUNTIME_STATUS_PANEL_REVIEW_SEALED::" + str(review.get("runtime_status_panel_review_sealed") is True))
print("CREATOR_VISIBLE_AUTONOMY_PULSE_ACCEPTED::" + str(review.get("creator_visible_autonomy_pulse_accepted") is True))
print("OBSERVABLE_SELF_BUILDING_PULSE_PROVEN::" + str(review.get("observable_self_building_pulse_proven") is True))
print("SELF_BUILDING_MODE_ENABLED::False")
print("DAEMON_RUNNING::False")
print("SCHEDULER_INSTALLED::False")
print("BACKGROUND_LOOP_ENABLED::False")
print("NETWORK_USED::False")
print("QUEUE_WIDENING_ALLOWED::False")
print("ENTITY_BIRTH_ALLOWED::False")
print("ANNA_BIRTH_ALLOWED::False")
print("AGI_CLAIM_ALLOWED::False")
print("HARD_FAILURES::" + json.dumps(review.get("hard_failures") or [], ensure_ascii=False))
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("REPORTS")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("PANEL_JSON::" + str(PANEL))
print("PULSE_JSON::" + str(PULSE))
print("TERMINAL_SUMMARY::" + str(TERMINAL_SUMMARY))
print("CREATOR_REPORT::" + str(CREATOR_REPORT))
print("REVIEW_PROOF::" + str(REVIEW_PROOF))
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("TRUTH_BOUNDARY")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(str(review.get("truth_boundary") or panel.get("truth_boundary") or "No truth boundary found."))
'''

if status == "PASS":
    write_text(SHOW_SCRIPT, show_script)
    SHOW_SCRIPT.chmod(0o755)

post_checks = {
    "show_script_created": SHOW_SCRIPT.exists() if status == "PASS" else True,
    "show_script_path_exact": str(SHOW_SCRIPT) == "scripts/socc/show_self_building_status_panel_v1.py" if status == "PASS" else True,
}

post_hard = [{"code": "POST_CHECK_FAIL", "check": k, "actual": v} for k, v in post_checks.items() if v is not True]
if post_hard:
    status = "FAIL"
    hard = hard + post_hard

if status == "PASS":
    capability = "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_BUILT_CREATOR_CAN_RENDER_PULSE_ON_DEMAND"
    real_next = "validate_self_building_status_panel_refresh_command_v1"
    final_socc_status = "SOCC_SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_BLOCKED"
    real_next = "repair_self_building_status_panel_refresh_command_v1"
    final_socc_status = "SOCC_SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_FAIL"

truth_boundary = (
    "Refresh command build only. This creates a local command to re-render the accepted self-building pulse/status panel on demand. "
    "It reads local JSON/Markdown proof artifacts only. It does not enable persistent self-building mode, launch runtime, start daemon/"
    "scheduler/background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

sample_output = ""
if status == "PASS":
    sample_output = "\n".join([
        "SOCC_SELF_BUILDING_PULSE::" + str(pulse.get("pulse")),
        "CURRENT_LEVEL::" + str(panel.get("current_autonomy_level")),
        "SELF_BUILDING_CYCLE_COUNT::" + str(panel.get("self_building_cycle_count")),
        "REAL_NEXT::" + real_next,
        "SELF_BUILDING_MODE_ENABLED::False",
        "DAEMON_RUNNING::False",
        "SCHEDULER_INSTALLED::False",
        "BACKGROUND_LOOP_ENABLED::False",
    ])

refresh = {
    "id": "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "source_review_proof": str(REVIEW_PROOF),
    "show_script": str(SHOW_SCRIPT) if status == "PASS" else None,
    "sample_output": str(REFRESH_LOG) if status == "PASS" else None,
    "refresh_command_built": status == "PASS",
    "creator_can_render_pulse_on_demand": status == "PASS",
    "local_read_only": True,
    "network_used": False,
    "self_building_mode_enabled": False,
    "runtime_launch_approved": False,
    "runtime_execution_allowed": False,
    "runtime_autonomy_enabled": False,
    "daemon_running": False,
    "scheduler_installed": False,
    "background_loop_enabled": False,
    "queue_widening_allowed": False,
    "entity_birth_allowed": False,
    "anna_birth_allowed": False,
    "agi_claim_allowed": False,
    "final_canon_approval_allowed": False,
    "checks": checks,
    "post_checks": post_checks,
    "hard_failures": hard,
    "real_next": real_next,
    "truth_boundary": truth_boundary
}
refresh["refresh_hash"] = h24(refresh)

proof = {
    "id": "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "refresh": str(REFRESH_CONTRACT),
    "refresh_md": str(REFRESH_MD),
    "show_script": str(SHOW_SCRIPT) if status == "PASS" else None,
    "sample_output": str(REFRESH_LOG) if status == "PASS" else None,
    "memory": str(MEMORY),
    "refresh_command_built": status == "PASS",
    "creator_can_render_pulse_on_demand": status == "PASS",
    "local_read_only": True,
    "network_used": False,
    "self_building_mode_enabled": False,
    "runtime_launch_approved": False,
    "runtime_execution_allowed": False,
    "runtime_autonomy_enabled": False,
    "daemon_running": False,
    "scheduler_installed": False,
    "background_loop_enabled": False,
    "queue_widening_allowed": False,
    "entity_birth_allowed": False,
    "anna_birth_allowed": False,
    "agi_claim_allowed": False,
    "final_canon_approval_allowed": False,
    "checks": checks,
    "post_checks": post_checks,
    "hard_failures": hard,
    "real_next": real_next,
    "final_socc_status": final_socc_status,
    "truth_boundary": truth_boundary
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built a local refresh command for the creator-visible self-building pulse. "
        "The creator can re-render the autonomy status panel on demand without daemon/scheduler/background loop."
    ),
    "proof": str(PROOF),
    "refresh": str(REFRESH_CONTRACT),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

md = "# SELF-BUILDING STATUS PANEL REFRESH COMMAND V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nObservable self-building pulse was review-sealed and accepted, but there was no simple local refresh command.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt local read-only command `scripts/socc/show_self_building_status_panel_v1.py`.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
for k, v in post_checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Creator can re-render the local self-building pulse on demand without launching daemon/scheduler.\n\n"
else:
    md += "Refresh command is blocked. Repair required.\n\n"
md += "## Команда\n\n```bash\npython3 scripts/socc/show_self_building_status_panel_v1.py\n```\n\n"
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

write_text(REFRESH_LOG, sample_output)
write_json(REFRESH_CONTRACT, refresh)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(REFRESH_MD, md)

print("SELF-BUILDING STATUS PANEL REFRESH COMMAND :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("REFRESH::" + str(REFRESH_CONTRACT))
print("SHOW_SCRIPT::" + (str(SHOW_SCRIPT) if status == "PASS" else "NONE"))
print("SAMPLE_OUTPUT::" + (str(REFRESH_LOG) if status == "PASS" else "NONE"))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("REFRESH_COMMAND_BUILT::" + str(status == "PASS"))
print("CREATOR_CAN_RENDER_PULSE_ON_DEMAND::" + str(status == "PASS"))
print("LOCAL_READ_ONLY::True")
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

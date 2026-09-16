import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
PROOF_DIR = ROOT / "core/socc/approved_autonomy_lane_runner/proof"

VALIDATION_PROOF = PROOF_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_V1_PROOF.json"
REFRESH_PROOF = PROOF_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1_PROOF.json"
PANEL_REVIEW_PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_V1_PROOF.json"

BASE = ROOT / "core/socc/autonomy/self_building/status_panel/refresh"
REVIEW_DIR = BASE / "review"

VALIDATION_JSON = BASE / "validation/SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_V1.json"
VALIDATION_MD = BASE / "validation/SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_V1.md"
VALIDATION_OUTPUT = BASE / "validation/SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATION_OUTPUT_V1.txt"

REFRESH_CONTRACT = BASE / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1.json"
REFRESH_MD = BASE / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_V1.md"
SHOW_SCRIPT = ROOT / "scripts/socc/show_self_building_status_panel_v1.py"

REVIEW = REVIEW_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_REVIEW_V1.json"
REVIEW_MD = REVIEW_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_REVIEW_V1.md"

PROOF = PROOF_DIR / "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_REVIEW_V1_MEMORY.json"

EXPECTED_VALIDATION_CAPABILITY = "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_VALIDATED_ON_DEMAND_PULSE_WORKS"
EXPECTED_REFRESH_CAPABILITY = "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_BUILT_CREATOR_CAN_RENDER_PULSE_ON_DEMAND"
EXPECTED_NEXT = "review_self_building_status_panel_refresh_command_v1"

NEXT_AFTER_REVIEW = "build_self_building_cycle_2_candidate_v1"

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
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]

validation = read_json(VALIDATION_PROOF)
refresh = read_json(REFRESH_PROOF)
panel_review = read_json(PANEL_REVIEW_PROOF)
validation_output = read_text(VALIDATION_OUTPUT)

checks = {
    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": validation.get("status") == "PASS",
    "validation_capability_ok": validation.get("capability") == EXPECTED_VALIDATION_CAPABILITY,
    "validation_real_next_ok": validation.get("real_next") == EXPECTED_NEXT,
    "refresh_command_validated": validation.get("refresh_command_validated") is True,
    "creator_can_render_pulse_on_demand_validated": validation.get("creator_can_render_pulse_on_demand_validated") is True,
    "lawful_next_display_validated": validation.get("lawful_next_display_validated") is True,
    "typo_lawful_next_removed": validation.get("typo_lawful_next_removed") is True,
    "local_read_only_validated": validation.get("local_read_only_validated") is True,
    "validation_hard_failures_empty": validation.get("hard_failures") == [],

    "refresh_proof_exists": REFRESH_PROOF.exists(),
    "refresh_status_pass": refresh.get("status") == "PASS",
    "refresh_capability_ok": refresh.get("capability") == EXPECTED_REFRESH_CAPABILITY,
    "refresh_command_built": refresh.get("refresh_command_built") is True,
    "creator_can_render_pulse_on_demand": refresh.get("creator_can_render_pulse_on_demand") is True,
    "refresh_local_read_only": refresh.get("local_read_only") is True,

    "panel_review_proof_exists": PANEL_REVIEW_PROOF.exists(),
    "panel_review_status_pass": panel_review.get("status") == "PASS",
    "runtime_status_panel_review_sealed": panel_review.get("runtime_status_panel_review_sealed") is True,
    "observable_self_building_pulse_proven": panel_review.get("observable_self_building_pulse_proven") is True,

    "validation_json_exists": VALIDATION_JSON.exists(),
    "validation_md_exists": VALIDATION_MD.exists(),
    "validation_output_exists": VALIDATION_OUTPUT.exists(),
    "refresh_contract_exists": REFRESH_CONTRACT.exists(),
    "refresh_md_exists": REFRESH_MD.exists(),
    "show_script_exists": SHOW_SCRIPT.exists(),

    "validation_output_contains_pulse": "SOCC_SELF_BUILDING_PULSE::ALIVE_BOUNDED_SELF_BUILDING_VISIBLE" in validation_output,
    "validation_output_contains_lawful_next": "LAWFUL_NEXT::validate_self_building_status_panel_refresh_command_v1" in validation_output,
    "validation_output_no_lawul_typo": ("LAWUL_NEXT::" not in validation_output and "lawul_next" not in validation_output),
    "validation_output_hard_failures_empty": "HARD_FAILURES::[]" in validation_output,

    "review_does_not_enable_self_building_mode": True,
    "review_does_not_launch_runtime": True,
    "review_does_not_start_daemon": True,
    "review_does_not_install_scheduler": True,
    "review_does_not_enable_background_loop": True,
    "review_does_not_use_network": True,
    "review_does_not_widen_queue": True,
    "review_does_not_birth_entity": True,
    "review_does_not_birth_anna": True,
    "review_does_not_claim_agi": True,
    "review_does_not_approve_final_canon": True,
}

for src_name, src in [("validation", validation), ("refresh", refresh), ("panel_review", panel_review)]:
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

if status == "PASS":
    capability = "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_REVIEW_SEALED_ON_DEMAND_PULSE_ACCEPTED"
    review_status = "REVIEW_SEALED"
    real_next = NEXT_AFTER_REVIEW
    final_socc_status = "SOCC_SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_REVIEW_PASS_CYCLE_2_CANDIDATE_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_REVIEW_BLOCKED"
    review_status = "BLOCKED"
    real_next = "repair_self_building_status_panel_refresh_command_review_v1"
    final_socc_status = "SOCC_SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_REVIEW_FAIL"

truth_boundary = (
    "Review-seal only. This accepts the validated local read-only refresh command for on-demand creator-visible self-building pulse. "
    "It does not enable persistent self-building mode, launch runtime, start daemon/scheduler/background loop, use network, "
    "widen queue, birth Entity/ANNA, approve final canon, or claim AGI. Next route prepares a second bounded self-building cycle candidate."
)

review = {
    "id": "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": review_status,
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_refresh_proof": str(REFRESH_PROOF),
    "source_panel_review_proof": str(PANEL_REVIEW_PROOF),
    "show_script": str(SHOW_SCRIPT),

    "refresh_command_review_sealed": status == "PASS",
    "on_demand_pulse_refresh_accepted": status == "PASS",
    "creator_can_render_pulse_on_demand_review_sealed": status == "PASS",
    "local_read_only_review_sealed": status == "PASS",
    "lawful_next_display_review_sealed": status == "PASS",

    "self_building_cycle_count": 1,
    "next_route_class": "second_bounded_self_building_cycle_candidate" if status == "PASS" else None,
    "next_improvement_target": NEXT_AFTER_REVIEW if status == "PASS" else None,

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

    "checks": checks,
    "hard_failures": hard,
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}
review["review_hash"] = h24(review)

proof = {
    "id": "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "refresh_command_review_sealed": status == "PASS",
    "on_demand_pulse_refresh_accepted": status == "PASS",
    "creator_can_render_pulse_on_demand_review_sealed": status == "PASS",
    "local_read_only_review_sealed": status == "PASS",
    "lawful_next_display_review_sealed": status == "PASS",

    "self_building_cycle_count": 1,
    "next_route_class": "second_bounded_self_building_cycle_candidate" if status == "PASS" else None,

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

    "checks": checks,
    "hard_failures": hard,
    "real_next": real_next,
    "final_socc_status": final_socc_status,
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed the local on-demand self-building pulse refresh command. "
        "Creator can now render the autonomy pulse without daemon/scheduler. Next is preparing a second bounded self-building cycle candidate."
    ),
    "proof": str(PROOF),
    "review": str(REVIEW),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

md = "# SELF-BUILDING STATUS PANEL REFRESH COMMAND REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nRefresh command was built and validated. Creator could render local pulse on demand with correct LAWFUL_NEXT.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed the validated local read-only refresh command.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "On-demand pulse refresh is accepted. Next route prepares second bounded self-building cycle candidate.\n\n"
else:
    md += "Refresh command review is blocked. Repair required.\n\n"
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

write_json(REVIEW, review)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(REVIEW_MD, md)

print("SELF-BUILDING STATUS PANEL REFRESH COMMAND REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("REFRESH_COMMAND_REVIEW_SEALED::" + str(status == "PASS"))
print("ON_DEMAND_PULSE_REFRESH_ACCEPTED::" + str(status == "PASS"))
print("CREATOR_CAN_RENDER_PULSE_ON_DEMAND_REVIEW_SEALED::" + str(status == "PASS"))
print("LOCAL_READ_ONLY_REVIEW_SEALED::" + str(status == "PASS"))
print("LAWFUL_NEXT_DISPLAY_REVIEW_SEALED::" + str(status == "PASS"))
print("SELF_BUILDING_CYCLE_COUNT::1")
print("NEXT_ROUTE_CLASS::" + ("second_bounded_self_building_cycle_candidate" if status == "PASS" else "NONE"))
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

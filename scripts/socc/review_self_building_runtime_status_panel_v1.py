import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
PROOF_DIR = ROOT / "core/socc/approved_autonomy_lane_runner/proof"

VALIDATION_PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATION_V1_PROOF.json"
PANEL_PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_V1_PROOF.json"
CONTRACT_PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_V1_PROOF.json"
TICK_REVIEW_PROOF = PROOF_DIR / "SELF_BUILDING_TICK_EXECUTION_PLAN_REVIEW_V1_PROOF.json"

BASE = ROOT / "core/socc/autonomy/self_building/status_panel"
REVIEW_DIR = BASE / "review"

PANEL = BASE / "runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PULSE = BASE / "runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL_MD = BASE / "reports/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.md"
TERMINAL_SUMMARY = BASE / "reports/SOCC_SELF_BUILDING_TERMINAL_SUMMARY_V1.txt"
CREATOR_REPORT = BASE / "reports/CREATOR_VISIBLE_AUTONOMY_PULSE_REPORT_V1.md"
VALIDATION_JSON = BASE / "validation/SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATION_V1.json"

REVIEW = REVIEW_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_V1.json"
REVIEW_MD = REVIEW_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_V1.md"

PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_V1_MEMORY.json"

EXPECTED_VALIDATION_CAPABILITY = "SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATED_CREATOR_VISIBLE_PULSE_ACCEPTED"
EXPECTED_PANEL_CAPABILITY = "SELF_BUILDING_RUNTIME_STATUS_PANEL_BUILT_CREATOR_VISIBLE_PULSE_READY"
EXPECTED_NEXT = "review_self_building_runtime_status_panel_v1"
EXPECTED_PULSE = "ALIVE_BOUNDED_SELF_BUILDING_VISIBLE"
EXPECTED_LEVEL = "L7_FIRST_BOUNDED_SELF_BUILDING_CYCLE_CLOSED_STATUS_PANEL_BUILT"

NEXT_AFTER_REVIEW = "build_self_building_status_panel_refresh_command_v1"

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

validation = read_json(VALIDATION_PROOF)
panel_proof = read_json(PANEL_PROOF)
contract = read_json(CONTRACT_PROOF)
tick_review = read_json(TICK_REVIEW_PROOF)
panel = read_json(PANEL)
pulse = read_json(PULSE)

checks = {
    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": validation.get("status") == "PASS",
    "validation_capability_ok": validation.get("capability") == EXPECTED_VALIDATION_CAPABILITY,
    "validation_real_next_ok": validation.get("real_next") == EXPECTED_NEXT,
    "runtime_status_panel_validated": validation.get("runtime_status_panel_validated") is True,
    "creator_visible_pulse_validated": validation.get("creator_visible_autonomy_pulse_validated") is True,
    "validation_pulse_value_ok": validation.get("pulse_value") == EXPECTED_PULSE,
    "validation_current_level_ok": validation.get("current_autonomy_level") == EXPECTED_LEVEL,
    "validation_cycle_count_one": int(validation.get("self_building_cycle_count") or 0) == 1,
    "validation_ready_for_review": validation.get("ready_for_review") is True,
    "validation_hard_failures_empty": validation.get("hard_failures") == [],

    "panel_proof_exists": PANEL_PROOF.exists(),
    "panel_proof_status_pass": panel_proof.get("status") == "PASS",
    "panel_capability_ok": panel_proof.get("capability") == EXPECTED_PANEL_CAPABILITY,
    "panel_built": panel_proof.get("runtime_status_panel_built") is True,
    "creator_visible_pulse_ready": panel_proof.get("creator_visible_autonomy_pulse_ready") is True,

    "contract_proof_exists": CONTRACT_PROOF.exists(),
    "contract_status_pass": contract.get("status") == "PASS",
    "contract_built": contract.get("runtime_status_panel_contract_built") is True,

    "tick_review_proof_exists": TICK_REVIEW_PROOF.exists(),
    "tick_review_status_pass": tick_review.get("status") == "PASS",
    "first_self_building_cycle_closed": tick_review.get("one_bounded_self_building_tick_cycle_closed") is True,

    "panel_json_exists": PANEL.exists(),
    "pulse_json_exists": PULSE.exists(),
    "panel_md_exists": PANEL_MD.exists(),
    "terminal_summary_exists": TERMINAL_SUMMARY.exists(),
    "creator_report_exists": CREATOR_REPORT.exists(),
    "validation_json_exists": VALIDATION_JSON.exists(),

    "panel_json_status_built": panel.get("status") == "BUILT",
    "panel_current_level_ok": panel.get("current_autonomy_level") == EXPECTED_LEVEL,
    "panel_lawful_next_validation": panel.get("lawful_next") == "validate_self_building_runtime_status_panel_v1",
    "panel_cycle_count_one": int(panel.get("self_building_cycle_count") or 0) == 1,
    "pulse_value_ok": pulse.get("pulse") == EXPECTED_PULSE,
    "pulse_level_ok": pulse.get("current_autonomy_level") == EXPECTED_LEVEL,

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

for src_name, src in [
    ("validation", validation),
    ("panel_proof", panel_proof),
    ("contract", contract),
    ("tick_review", tick_review),
    ("panel", panel),
]:
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
    capability = "SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_SEALED_VISIBLE_PULSE_ACCEPTED"
    review_status = "REVIEW_SEALED"
    real_next = NEXT_AFTER_REVIEW
    final_socc_status = "SOCC_SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_PASS_REFRESH_COMMAND_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_BLOCKED"
    review_status = "BLOCKED"
    real_next = "repair_self_building_runtime_status_panel_review_v1"
    final_socc_status = "SOCC_SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_FAIL"

truth_boundary = (
    "Review-seal only. This accepts the validated creator-visible self-building runtime/status panel and routes next to "
    "a refresh command so the creator can re-render the local autonomy pulse on demand. It does not enable persistent "
    "self-building mode, launch runtime, start daemon/scheduler/background loop, use network, widen queue, birth Entity/ANNA, "
    "approve final canon, or claim AGI."
)

review = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": review_status,
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_panel_proof": str(PANEL_PROOF),
    "source_contract_proof": str(CONTRACT_PROOF),
    "source_tick_review_proof": str(TICK_REVIEW_PROOF),

    "runtime_status_panel_review_sealed": status == "PASS",
    "creator_visible_autonomy_pulse_accepted": status == "PASS",
    "observable_self_building_pulse_proven": status == "PASS",
    "self_building_cycle_count": 1 if status == "PASS" else 0,
    "current_autonomy_level": EXPECTED_LEVEL if status == "PASS" else None,
    "pulse_value": EXPECTED_PULSE if status == "PASS" else None,

    "next_improvement_target": NEXT_AFTER_REVIEW if status == "PASS" else None,
    "why_next": (
        "A refresh command lets the creator re-render the local self-building pulse at any time without starting daemon/scheduler."
        if status == "PASS" else None
    ),

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
    "truth_boundary": truth_boundary
}
review["review_hash"] = h24(review)

proof = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "runtime_status_panel_review_sealed": status == "PASS",
    "creator_visible_autonomy_pulse_accepted": status == "PASS",
    "observable_self_building_pulse_proven": status == "PASS",
    "self_building_cycle_count": 1 if status == "PASS" else 0,
    "current_autonomy_level": EXPECTED_LEVEL if status == "PASS" else None,
    "pulse_value": EXPECTED_PULSE if status == "PASS" else None,

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
    "truth_boundary": truth_boundary
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed the creator-visible self-building runtime/status panel. "
        "Observable bounded self-building pulse is now accepted. Next is a local refresh command."
    ),
    "proof": str(PROOF),
    "review": str(REVIEW),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

md = "# SELF-BUILDING RUNTIME STATUS PANEL REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nRuntime/status panel was built and validated. Creator-visible autonomy pulse was ready for review.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed the creator-visible self-building pulse/status panel.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Observable self-building pulse is review-sealed and accepted. Next: build local status panel refresh command.\n\n"
else:
    md += "Runtime/status panel review is blocked. Repair required.\n\n"
md += "## Pulse accepted\n\n"
md += "- pulse: " + (EXPECTED_PULSE if status == "PASS" else "BLOCKED") + "\n"
md += "- current_level: " + (EXPECTED_LEVEL if status == "PASS" else "BLOCKED") + "\n"
md += "- self_building_cycle_count: " + str(1 if status == "PASS" else 0) + "\n\n"
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

print("SELF-BUILDING RUNTIME STATUS PANEL REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("RUNTIME_STATUS_PANEL_REVIEW_SEALED::" + str(status == "PASS"))
print("CREATOR_VISIBLE_AUTONOMY_PULSE_ACCEPTED::" + str(status == "PASS"))
print("OBSERVABLE_SELF_BUILDING_PULSE_PROVEN::" + str(status == "PASS"))
print("SOCC_SELF_BUILDING_PULSE::" + (EXPECTED_PULSE if status == "PASS" else "BLOCKED"))
print("CURRENT_LEVEL::" + (EXPECTED_LEVEL if status == "PASS" else "BLOCKED"))
print("SELF_BUILDING_CYCLE_COUNT::" + str(1 if status == "PASS" else 0))
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

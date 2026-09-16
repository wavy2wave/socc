import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
PROOF_DIR = ROOT / "core/socc/approved_autonomy_lane_runner/proof"

PANEL_PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_V1_PROOF.json"
PANEL_CONTRACT_PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_V1_PROOF.json"
TICK_REVIEW_PROOF = PROOF_DIR / "SELF_BUILDING_TICK_EXECUTION_PLAN_REVIEW_V1_PROOF.json"

BASE = ROOT / "core/socc/autonomy/self_building/status_panel"
RUNTIME_DIR = BASE / "runtime"
REPORTS_DIR = BASE / "reports"
VALIDATION_DIR = BASE / "validation"

PANEL = RUNTIME_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PULSE = RUNTIME_DIR / "SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL_MD = REPORTS_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.md"
TERMINAL_SUMMARY = REPORTS_DIR / "SOCC_SELF_BUILDING_TERMINAL_SUMMARY_V1.txt"
CREATOR_REPORT = REPORTS_DIR / "CREATOR_VISIBLE_AUTONOMY_PULSE_REPORT_V1.md"

CONTRACT_SCHEMA = BASE / "contract/SELF_BUILDING_RUNTIME_STATUS_PANEL_SCHEMA_V1.json"
CONTRACT_DATA_SOURCES = BASE / "contract/SELF_BUILDING_RUNTIME_STATUS_PANEL_DATA_SOURCES_V1.json"
CONTRACT_RENDER_SPEC = BASE / "contract/SELF_BUILDING_RUNTIME_STATUS_PANEL_RENDER_SPEC_V1.json"
CONTRACT_VALIDATOR = BASE / "contract/SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATOR_CONTRACT_V1.json"

VALIDATION = VALIDATION_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATION_V1.json"
VALIDATION_MD = VALIDATION_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATION_V1.md"

PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATION_V1_MEMORY.json"

EXPECTED_PANEL_CAPABILITY = "SELF_BUILDING_RUNTIME_STATUS_PANEL_BUILT_CREATOR_VISIBLE_PULSE_READY"
EXPECTED_CONTRACT_CAPABILITY = "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_BUILT_READY_FOR_IMPLEMENTATION"
EXPECTED_NEXT = "validate_self_building_runtime_status_panel_v1"
EXPECTED_PULSE = "ALIVE_BOUNDED_SELF_BUILDING_VISIBLE"
EXPECTED_LEVEL = "L7_FIRST_BOUNDED_SELF_BUILDING_CYCLE_CLOSED_STATUS_PANEL_BUILT"
NEXT_AFTER_VALIDATION = "review_self_building_runtime_status_panel_v1"

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

panel_proof = read_json(PANEL_PROOF)
contract_proof = read_json(PANEL_CONTRACT_PROOF)
tick_review = read_json(TICK_REVIEW_PROOF)
panel = read_json(PANEL)
pulse = read_json(PULSE)
schema = read_json(CONTRACT_SCHEMA)
data_sources = read_json(CONTRACT_DATA_SOURCES)
render_spec = read_json(CONTRACT_RENDER_SPEC)
validator = read_json(CONTRACT_VALIDATOR)

panel_md = read_text(PANEL_MD)
terminal = read_text(TERMINAL_SUMMARY)
creator_report = read_text(CREATOR_REPORT)

required_fields = set(schema.get("required_fields") or [])
panel_keys = set(panel.keys())
proven = panel.get("proven_capabilities") or []
locked = panel.get("locked_capabilities") or []
must_validate = set(validator.get("must_validate") or [])

checks = {
    "panel_proof_exists": PANEL_PROOF.exists(),
    "panel_proof_status_pass": panel_proof.get("status") == "PASS",
    "panel_capability_ok": panel_proof.get("capability") == EXPECTED_PANEL_CAPABILITY,
    "panel_real_next_ok": panel_proof.get("real_next") == EXPECTED_NEXT,
    "runtime_status_panel_built_true": panel_proof.get("runtime_status_panel_built") is True,
    "creator_visible_pulse_ready_true": panel_proof.get("creator_visible_autonomy_pulse_ready") is True,
    "panel_self_building_cycle_count_one": int(panel_proof.get("self_building_cycle_count") or 0) == 1,
    "panel_current_level_ok": panel_proof.get("current_autonomy_level") == EXPECTED_LEVEL,
    "panel_hard_failures_empty": panel_proof.get("hard_failures") == [],

    "contract_proof_exists": PANEL_CONTRACT_PROOF.exists(),
    "contract_status_pass": contract_proof.get("status") == "PASS",
    "contract_capability_ok": contract_proof.get("capability") == EXPECTED_CONTRACT_CAPABILITY,
    "contract_panel_built_false_before": contract_proof.get("runtime_status_panel_built") is False,

    "tick_review_proof_exists": TICK_REVIEW_PROOF.exists(),
    "tick_review_status_pass": tick_review.get("status") == "PASS",
    "tick_cycle_closed": tick_review.get("one_bounded_self_building_tick_cycle_closed") is True,

    "panel_json_exists": PANEL.exists(),
    "pulse_json_exists": PULSE.exists(),
    "panel_md_exists": PANEL_MD.exists(),
    "terminal_summary_exists": TERMINAL_SUMMARY.exists(),
    "creator_report_exists": CREATOR_REPORT.exists(),

    "contract_schema_exists": CONTRACT_SCHEMA.exists(),
    "contract_data_sources_exists": CONTRACT_DATA_SOURCES.exists(),
    "contract_render_spec_exists": CONTRACT_RENDER_SPEC.exists(),
    "contract_validator_exists": CONTRACT_VALIDATOR.exists(),

    "panel_has_all_required_fields": required_fields.issubset(panel_keys),
    "panel_status_built": panel.get("status") == "BUILT",
    "panel_capability_ok_json": panel.get("capability") == EXPECTED_PANEL_CAPABILITY,
    "panel_current_level_ok_json": panel.get("current_autonomy_level") == EXPECTED_LEVEL,
    "panel_lawful_next_ok": panel.get("lawful_next") == EXPECTED_NEXT,
    "panel_last_tick_status_pass": panel.get("last_tick_status") == "PASS",
    "panel_self_building_cycle_count_one_json": int(panel.get("self_building_cycle_count") or 0) == 1,
    "panel_has_proven_capabilities": len(proven) >= 8,
    "panel_has_locked_capabilities": len(locked) >= 6,
    "panel_truth_boundary_exists": bool(panel.get("truth_boundary")),

    "pulse_value_ok": pulse.get("pulse") == EXPECTED_PULSE,
    "pulse_current_level_ok": pulse.get("current_autonomy_level") == EXPECTED_LEVEL,
    "pulse_lawful_next_ok": pulse.get("lawful_next") == EXPECTED_NEXT,
    "pulse_cycle_count_one": int(pulse.get("self_building_cycle_count") or 0) == 1,

    "terminal_contains_pulse": "SOCC_SELF_BUILDING_PULSE::ALIVE_BOUNDED_SELF_BUILDING_VISIBLE" in terminal,
    "terminal_contains_level": "CURRENT_LEVEL::L7_FIRST_BOUNDED_SELF_BUILDING_CYCLE_CLOSED_STATUS_PANEL_BUILT" in terminal,
    "terminal_contains_lawful_next": "REAL_NEXT::validate_self_building_runtime_status_panel_v1" in terminal,
    "terminal_hard_failures_empty": "HARD_FAILURES::[]" in terminal,

    "panel_md_contains_pulse": "## Пульс" in panel_md,
    "panel_md_contains_proven": "## Что доказано" in panel_md,
    "panel_md_contains_locked": "## Что locked" in panel_md,
    "panel_md_contains_lawful_next": "validate_self_building_runtime_status_panel_v1" in panel_md,

    "creator_report_contains_visible_pulse": "пульс self-building автономии" in creator_report,
    "creator_report_contains_next": "validate_self_building_runtime_status_panel_v1" in creator_report,

    "validator_must_validate_schema": "panel schema exists" in must_validate,
    "validator_must_validate_local_sources": "data sources are local proof/memory only" in must_validate,
    "validator_must_validate_current_level": "panel includes current level" in must_validate,
    "validator_must_validate_lawful_next": "panel includes lawful_next" in must_validate,
    "validator_must_validate_last_tick": "panel includes last tick" in must_validate,
    "validator_must_validate_no_daemon": "panel does not start daemon" in must_validate,
    "validator_must_validate_no_scheduler": "panel does not install scheduler" in must_validate,
    "validator_must_validate_no_network": "panel does not use network" in must_validate,

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

for src_name, src in [("panel_proof", panel_proof), ("panel", panel), ("contract", contract_proof), ("tick_review", tick_review)]:
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
    capability = "SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATED_CREATOR_VISIBLE_PULSE_ACCEPTED"
    validation_status = "VALIDATED"
    real_next = NEXT_AFTER_VALIDATION
    final_socc_status = "SOCC_SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATION_PASS_READY_FOR_REVIEW_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATION_BLOCKED"
    validation_status = "BLOCKED"
    real_next = "repair_self_building_runtime_status_panel_validation_v1"
    final_socc_status = "SOCC_SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATION_FAIL"

truth_boundary = (
    "Runtime/status panel validation only. This validates local creator-visible pulse/status reports and proof-state. "
    "It does not enable persistent self-building mode, launch runtime, start daemon/scheduler/background loop, use network, "
    "widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

validation = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATION_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": validation_status,
    "capability": capability,
    "source_panel_proof": str(PANEL_PROOF),
    "source_contract_proof": str(PANEL_CONTRACT_PROOF),
    "source_tick_review_proof": str(TICK_REVIEW_PROOF),
    "panel": str(PANEL),
    "pulse": str(PULSE),
    "panel_md": str(PANEL_MD),
    "terminal_summary": str(TERMINAL_SUMMARY),
    "creator_report": str(CREATOR_REPORT),

    "runtime_status_panel_validated": status == "PASS",
    "creator_visible_autonomy_pulse_validated": status == "PASS",
    "pulse_value": EXPECTED_PULSE if status == "PASS" else None,
    "current_autonomy_level": EXPECTED_LEVEL if status == "PASS" else None,
    "self_building_cycle_count": 1 if status == "PASS" else 0,
    "ready_for_review": status == "PASS",

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
validation["validation_hash"] = h24(validation)

proof = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATION_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "validation": str(VALIDATION),
    "validation_md": str(VALIDATION_MD),
    "memory": str(MEMORY),

    "runtime_status_panel_validated": status == "PASS",
    "creator_visible_autonomy_pulse_validated": status == "PASS",
    "pulse_value": EXPECTED_PULSE if status == "PASS" else None,
    "current_autonomy_level": EXPECTED_LEVEL if status == "PASS" else None,
    "self_building_cycle_count": 1 if status == "PASS" else 0,
    "ready_for_review": status == "PASS",

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
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATION_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC validated the creator-visible self-building pulse/status panel. The local pulse report is accepted for review."
    ),
    "proof": str(PROOF),
    "validation": str(VALIDATION),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

md = "# SELF-BUILDING RUNTIME STATUS PANEL VALIDATION V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nRuntime/status panel was built with creator-visible self-building pulse.\n\n"
md += "## ДЕЙСТВИЕ\n\nValidated pulse, current level, lawful_next, last tick, local reports, proven/locked capabilities, validator contract, and truth boundary.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Runtime/status panel is validated. Creator-visible autonomy pulse is accepted for review.\n\n"
else:
    md += "Runtime/status panel validation is blocked. Repair required.\n\n"
md += "## Pulse\n\n"
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

write_json(VALIDATION, validation)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(VALIDATION_MD, md)

print("SELF-BUILDING RUNTIME STATUS PANEL VALIDATION :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("VALIDATION::" + str(VALIDATION))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("RUNTIME_STATUS_PANEL_VALIDATED::" + str(status == "PASS"))
print("CREATOR_VISIBLE_AUTONOMY_PULSE_VALIDATED::" + str(status == "PASS"))
print("SOCC_SELF_BUILDING_PULSE::" + (EXPECTED_PULSE if status == "PASS" else "BLOCKED"))
print("CURRENT_LEVEL::" + (EXPECTED_LEVEL if status == "PASS" else "BLOCKED"))
print("SELF_BUILDING_CYCLE_COUNT::" + str(1 if status == "PASS" else 0))
print("READY_FOR_REVIEW::" + str(status == "PASS"))
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

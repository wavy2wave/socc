import json
import hashlib
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
SYNC_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_V1_PROOF.json"
CYCLE2_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_V1_PROOF.json"

PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
SHOW_SCRIPT = ROOT / "scripts/socc/show_self_building_status_panel_v1.py"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/truth_boundary_panel_sync/validation"
VALIDATION = OUT_DIR / "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1.json"
VALIDATION_MD = OUT_DIR / "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1.md"
SHOW_OUTPUT = OUT_DIR / "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_SHOW_OUTPUT_V1.txt"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1_MEMORY.json"

EXPECTED_SYNC_CAPABILITY = "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_BUILT_ROUTE_TRUTH_FIRST"
EXPECTED_NEXT = "validate_route_authority_truth_boundary_panel_sync_v1"
NEXT = "review_route_authority_truth_boundary_panel_sync_v1"

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

def h(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]

route = read_json(ROUTE)
sync = read_json(SYNC_PROOF)
cycle2_review = read_json(CYCLE2_REVIEW_PROOF)
pulse = read_json(PULSE)
panel = read_json(PANEL)
show_script = read_text(SHOW_SCRIPT)

route_next = route.get("lawful_next") or route.get("real_next")
route_truth = route.get("truth_boundary")
route_hash = route.get("route_hash")
route_upstream = route.get("upstream_proof")

pre_checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_validation": route_next == EXPECTED_NEXT,
    "route_upstream_sync_proof_ok": route_upstream == str(SYNC_PROOF),
    "route_truth_boundary_exists": bool(route_truth),
    "route_truth_boundary_panel_sync_enabled": route.get("truth_boundary_panel_sync_enabled") is True,
    "route_truth_boundary_priority_ok": route.get("truth_boundary_priority") == "CURRENT_ROUTE_AUTHORITY_FIRST",
    "route_truth_boundary_display_drift_resolved": route.get("truth_boundary_display_drift_resolved") is True,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "sync_proof_exists": SYNC_PROOF.exists(),
    "sync_status_pass": sync.get("status") == "PASS",
    "sync_capability_ok": sync.get("capability") == EXPECTED_SYNC_CAPABILITY,
    "sync_real_next_ok": sync.get("real_next") == EXPECTED_NEXT,
    "sync_built": sync.get("route_authority_truth_boundary_panel_sync_built") is True,
    "sync_truth_boundary_priority_ok": sync.get("truth_boundary_priority") == "CURRENT_ROUTE_AUTHORITY_FIRST",
    "sync_pulse_truth_synced": sync.get("pulse_truth_boundary_synced_to_route") is True,
    "sync_panel_truth_synced": sync.get("panel_truth_boundary_synced_to_route") is True,
    "sync_show_command_route_first": sync.get("show_command_truth_boundary_route_first") is True,
    "sync_hard_failures_empty": sync.get("hard_failures") == [],

    "cycle2_review_proof_exists": CYCLE2_REVIEW_PROOF.exists(),
    "cycle2_review_status_pass": cycle2_review.get("status") == "PASS",
    "cycle2_review_ready_to_build": cycle2_review.get("ready_to_build_selected_target") is True,

    "pulse_exists": PULSE.exists(),
    "pulse_lawful_next_matches_route": pulse.get("lawful_next") == route_next,
    "pulse_truth_boundary_matches_route": pulse.get("truth_boundary") == route_truth,
    "pulse_truth_boundary_source_route": pulse.get("truth_boundary_source") == "CURRENT_ROUTE_AUTHORITY",
    "pulse_truth_boundary_priority_ok": pulse.get("truth_boundary_priority") == "CURRENT_ROUTE_AUTHORITY_FIRST",

    "panel_exists": PANEL.exists(),
    "panel_lawful_next_matches_route": panel.get("lawful_next") == route_next,
    "panel_truth_boundary_matches_route": panel.get("truth_boundary") == route_truth,
    "panel_truth_boundary_source_route": panel.get("truth_boundary_source") == "CURRENT_ROUTE_AUTHORITY",
    "panel_truth_boundary_priority_ok": panel.get("truth_boundary_priority") == "CURRENT_ROUTE_AUTHORITY_FIRST",

    "show_script_exists": SHOW_SCRIPT.exists(),
    "show_script_reads_route": "route = read_json(ROUTE)" in show_script,
    "show_script_truth_boundary_route_first": 'route.get("truth_boundary")' in show_script,
    "show_script_lawful_next_route_first": 'route.get("lawful_next")' in show_script,

    "validation_does_not_execute_tick": True,
    "validation_does_not_enable_continuous_loop": True,
    "validation_does_not_launch_daemon": True,
    "validation_does_not_install_scheduler": True,
    "validation_does_not_enable_background_loop": True,
    "validation_does_not_use_network": True,
    "validation_does_not_widen_queue": True,
    "validation_does_not_birth_entity": True,
    "validation_does_not_birth_anna": True,
    "validation_does_not_claim_agi": True,
    "validation_does_not_approve_final_canon": True,
}

for name, src in [("route", route), ("sync", sync), ("cycle2_review", cycle2_review), ("pulse", pulse), ("panel", panel)]:
    for key in [
        "continuous_loop_enabled",
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
        if key in src:
            pre_checks[f"{name}_{key}_false"] = src.get(key) is False

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
    "show_returncode_zero": returncode == 0,
    "show_outputs_lawful_next": f"LAWFUL_NEXT::{EXPECTED_NEXT}" in stdout,
    "show_outputs_truth_boundary_source": "TRUTH_BOUNDARY_SOURCE::CURRENT_ROUTE_AUTHORITY" in stdout,
    "show_outputs_route_hash": "ROUTE_HASH::" in stdout and str(route_hash) in stdout,
    "show_outputs_route_upstream_sync_proof": f"ROUTE_UPSTREAM_PROOF::{SYNC_PROOF}" in stdout,
    "show_outputs_current_route_authority_path": "CURRENT_ROUTE_AUTHORITY::core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json" in stdout,
    "show_truth_boundary_contains_route_truth": bool(route_truth) and route_truth in stdout,
    "show_does_not_use_old_runtime_panel_truth": "Review-seal only. This accepts the validated creator-visible self-building runtime/status panel" not in stdout,
    "show_outputs_self_building_mode_true": "SELF_BUILDING_MODE_ENABLED::True" in stdout,
    "show_outputs_daemon_false": "DAEMON_RUNNING::False" in stdout,
    "show_outputs_scheduler_false": "SCHEDULER_INSTALLED::False" in stdout,
    "show_outputs_background_false": "BACKGROUND_LOOP_ENABLED::False" in stdout,
    "show_outputs_network_false": "NETWORK_USED::False" in stdout,
    "show_outputs_queue_false": "QUEUE_WIDENING_ALLOWED::False" in stdout,
    "show_outputs_hard_failures_empty": "HARD_FAILURES::[]" in stdout,
}

post_hard = [{"code": "POSTCHECK_FAIL", "check": k, "actual": v} for k, v in post_checks.items() if v is not True]
hard = pre_hard + post_hard
status = "PASS" if not hard else "FAIL"

if status == "PASS":
    capability = "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATED_NO_TRUTH_DRIFT"
    validation_status = "VALIDATED"
    real_next = NEXT
    final_socc_status = "SOCC_ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_PASS_READY_FOR_REVIEW_NOT_DAEMON_NOT_AGI"
else:
    capability = "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_BLOCKED"
    validation_status = "BLOCKED"
    real_next = "repair_route_authority_truth_boundary_panel_sync_validation_v1"
    final_socc_status = "SOCC_ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_FAIL"

truth_boundary = (
    "Route-authority truth-boundary/status-panel sync validation only. This validates that CURRENT_ROUTE_AUTHORITY, pulse, panel, "
    "and terminal refresh agree on truth_boundary and lawful_next. It does not execute a tick, enable continuous loop, launch daemon, "
    "install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

validation = {
    "id": "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": validation_status,
    "capability": capability,
    "source_route_authority": str(ROUTE),
    "source_sync_proof": str(SYNC_PROOF),
    "source_cycle2_review_proof": str(CYCLE2_REVIEW_PROOF),
    "show_output": str(SHOW_OUTPUT),
    "show_returncode": returncode,

    "route_authority_truth_boundary_panel_sync_validated": status == "PASS",
    "no_truth_boundary_display_drift": status == "PASS",
    "truth_boundary_priority_current_route_first_validated": status == "PASS",
    "pulse_truth_boundary_synced_to_route_validated": status == "PASS",
    "panel_truth_boundary_synced_to_route_validated": status == "PASS",
    "show_command_truth_boundary_route_first_validated": status == "PASS",

    "tick_executed_now": False,
    "continuous_loop_enabled": False,
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
validation["validation_hash"] = h(validation)

proof = {
    "id": "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "validation": str(VALIDATION),
    "validation_md": str(VALIDATION_MD),
    "show_output": str(SHOW_OUTPUT),
    "memory": str(MEMORY),

    "route_authority_truth_boundary_panel_sync_validated": status == "PASS",
    "no_truth_boundary_display_drift": status == "PASS",
    "truth_boundary_priority_current_route_first_validated": status == "PASS",
    "pulse_truth_boundary_synced_to_route_validated": status == "PASS",
    "panel_truth_boundary_synced_to_route_validated": status == "PASS",
    "show_command_truth_boundary_route_first_validated": status == "PASS",

    "tick_executed_now": False,
    "continuous_loop_enabled": False,
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
proof["proof_hash"] = h(proof)

memory = {
    "id": "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC validated route-authority truth-boundary/status-panel sync. Terminal refresh now displays CURRENT_ROUTE_AUTHORITY.truth_boundary."
    ),
    "proof": str(PROOF),
    "validation": str(VALIDATION),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

if status == "PASS":
    route.update({
        "updated_at_utc": now_utc(),
        "updated_at_msk": now_msk(),
        "lawful_next": real_next,
        "real_next": real_next,
        "upstream_proof": str(PROOF),
        "truth_boundary_panel_sync_validated": True,
        "no_truth_boundary_display_drift": True,
        "truth_boundary_priority": "CURRENT_ROUTE_AUTHORITY_FIRST",
        "self_building_mode_enabled": True,
        "visible_bounded_mode_ready": True,
        "continuous_loop_enabled": False,
        "daemon_running": False,
        "scheduler_installed": False,
        "background_loop_enabled": False,
        "network_used": False,
        "queue_widening_allowed": False,
        "entity_birth_allowed": False,
        "anna_birth_allowed": False,
        "agi_claim_allowed": False,
        "final_canon_approval_allowed": False,
        "truth_boundary": truth_boundary
    })
    route["route_hash"] = h(route)
    write_json(ROUTE, route)

md = "# ROUTE AUTHORITY TRUTH BOUNDARY PANEL SYNC VALIDATION V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nTruth-boundary display sync was built.\n\n"
md += "## ДЕЙСТВИЕ\n\nValidated route/pulse/panel/show truth_boundary agreement and terminal output.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in pre_checks.items():
    md += "- " + k + ": " + str(v) + "\n"
for k, v in post_checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Truth-boundary display sync is validated. No truth-boundary drift detected.\n\n"
else:
    md += "Truth-boundary display sync validation is blocked. Repair required.\n\n"
md += "## Explicitly NOT done\n\n"
for x in [
    "tick not executed now",
    "continuous loop not enabled",
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

write_text(SHOW_OUTPUT, stdout)
write_json(VALIDATION, validation)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(VALIDATION_MD, md)

print("ROUTE AUTHORITY TRUTH BOUNDARY PANEL SYNC VALIDATION :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("VALIDATION::" + str(VALIDATION))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATED::" + str(status == "PASS"))
print("NO_TRUTH_BOUNDARY_DISPLAY_DRIFT::" + str(status == "PASS"))
print("TRUTH_BOUNDARY_PRIORITY_CURRENT_ROUTE_FIRST_VALIDATED::" + str(status == "PASS"))
print("PULSE_TRUTH_BOUNDARY_SYNCED_TO_ROUTE_VALIDATED::" + str(status == "PASS"))
print("PANEL_TRUTH_BOUNDARY_SYNCED_TO_ROUTE_VALIDATED::" + str(status == "PASS"))
print("SHOW_COMMAND_TRUTH_BOUNDARY_ROUTE_FIRST_VALIDATED::" + str(status == "PASS"))
print("TICK_EXECUTED_NOW::False")
print("CONTINUOUS_LOOP_ENABLED::False")
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

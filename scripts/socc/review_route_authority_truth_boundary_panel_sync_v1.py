import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1_PROOF.json"
SYNC_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_V1_PROOF.json"
CYCLE2_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_V1_PROOF.json"

VALIDATION_JSON = ROOT / "core/socc/autonomy/self_building/truth_boundary_panel_sync/validation/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1.json"
SHOW_OUTPUT = ROOT / "core/socc/autonomy/self_building/truth_boundary_panel_sync/validation/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_SHOW_OUTPUT_V1.txt"

PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
SHOW_SCRIPT = ROOT / "scripts/socc/show_self_building_status_panel_v1.py"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/truth_boundary_panel_sync/review"
REVIEW = OUT_DIR / "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_V1.json"
REVIEW_MD = OUT_DIR / "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_V1_MEMORY.json"

EXPECTED_VALIDATION_CAPABILITY = "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATED_NO_TRUTH_DRIFT"
EXPECTED_SYNC_CAPABILITY = "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_BUILT_ROUTE_TRUTH_FIRST"
EXPECTED_NEXT = "review_route_authority_truth_boundary_panel_sync_v1"

# После review второго цикла идём к следующему безопасному шагу:
# построить закрывающий отчёт/метрику Cycle 2, а не daemon/scheduler.
NEXT = "build_self_building_cycle_2_closure_report_v1"

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
validation = read_json(VALIDATION_PROOF)
sync = read_json(SYNC_PROOF)
cycle2_review = read_json(CYCLE2_REVIEW_PROOF)
validation_json = read_json(VALIDATION_JSON)
pulse = read_json(PULSE)
panel = read_json(PANEL)
show_output = read_text(SHOW_OUTPUT)
show_script = read_text(SHOW_SCRIPT)

route_next = route.get("lawful_next") or route.get("real_next")
route_truth = route.get("truth_boundary")

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_review": route_next == EXPECTED_NEXT,
    "route_upstream_validation_proof_ok": route.get("upstream_proof") == str(VALIDATION_PROOF),
    "route_truth_boundary_panel_sync_validated": route.get("truth_boundary_panel_sync_validated") is True,
    "route_no_truth_boundary_display_drift": route.get("no_truth_boundary_display_drift") is True,
    "route_truth_boundary_priority_ok": route.get("truth_boundary_priority") == "CURRENT_ROUTE_AUTHORITY_FIRST",
    "route_truth_boundary_exists": bool(route_truth),
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": validation.get("status") == "PASS",
    "validation_capability_ok": validation.get("capability") == EXPECTED_VALIDATION_CAPABILITY,
    "validation_real_next_ok": validation.get("real_next") == EXPECTED_NEXT,
    "validation_sync_validated": validation.get("route_authority_truth_boundary_panel_sync_validated") is True,
    "validation_no_truth_drift": validation.get("no_truth_boundary_display_drift") is True,
    "validation_truth_priority_validated": validation.get("truth_boundary_priority_current_route_first_validated") is True,
    "validation_pulse_truth_validated": validation.get("pulse_truth_boundary_synced_to_route_validated") is True,
    "validation_panel_truth_validated": validation.get("panel_truth_boundary_synced_to_route_validated") is True,
    "validation_show_truth_route_first": validation.get("show_command_truth_boundary_route_first_validated") is True,
    "validation_hard_failures_empty": validation.get("hard_failures") == [],

    "sync_proof_exists": SYNC_PROOF.exists(),
    "sync_status_pass": sync.get("status") == "PASS",
    "sync_capability_ok": sync.get("capability") == EXPECTED_SYNC_CAPABILITY,
    "sync_built": sync.get("route_authority_truth_boundary_panel_sync_built") is True,
    "sync_truth_priority_ok": sync.get("truth_boundary_priority") == "CURRENT_ROUTE_AUTHORITY_FIRST",

    "cycle2_review_proof_exists": CYCLE2_REVIEW_PROOF.exists(),
    "cycle2_review_status_pass": cycle2_review.get("status") == "PASS",
    "cycle2_review_ready_to_build": cycle2_review.get("ready_to_build_selected_target") is True,

    "validation_json_exists": VALIDATION_JSON.exists(),
    "show_output_exists": SHOW_OUTPUT.exists(),
    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),
    "show_script_exists": SHOW_SCRIPT.exists(),

    "pulse_lawful_next_matches_route": pulse.get("lawful_next") == route_next,
    "panel_lawful_next_matches_route": panel.get("lawful_next") == route_next,
    "pulse_truth_boundary_matches_route": pulse.get("truth_boundary") == route_truth,
    "panel_truth_boundary_matches_route": panel.get("truth_boundary") == route_truth,
    "pulse_truth_boundary_source_route": pulse.get("truth_boundary_source") == "CURRENT_ROUTE_AUTHORITY",
    "panel_truth_boundary_source_route": panel.get("truth_boundary_source") == "CURRENT_ROUTE_AUTHORITY",

    "show_script_truth_boundary_route_first": 'route.get("truth_boundary")' in show_script,
    "show_script_lawful_next_route_first": 'route.get("lawful_next")' in show_script,
    "show_output_has_truth_source_route": "TRUTH_BOUNDARY_SOURCE::CURRENT_ROUTE_AUTHORITY" in show_output,
    "show_output_has_lawful_next": "LAWFUL_NEXT::review_route_authority_truth_boundary_panel_sync_v1" in show_output or "LAWFUL_NEXT::validate_route_authority_truth_boundary_panel_sync_v1" in show_output,
    "show_output_has_no_old_runtime_truth": "Review-seal only. This accepts the validated creator-visible self-building runtime/status panel" not in show_output,

    "review_does_not_execute_tick": True,
    "review_does_not_enable_continuous_loop": True,
    "review_does_not_launch_daemon": True,
    "review_does_not_install_scheduler": True,
    "review_does_not_enable_background_loop": True,
    "review_does_not_use_network": True,
    "review_does_not_widen_queue": True,
    "review_does_not_birth_entity": True,
    "review_does_not_birth_anna": True,
    "review_does_not_claim_agi": True,
    "review_does_not_approve_final_canon": True,
}

for name, src in [
    ("route", route),
    ("validation", validation),
    ("sync", sync),
    ("cycle2_review", cycle2_review),
    ("pulse", pulse),
    ("panel", panel),
]:
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
            checks[f"{name}_{key}_false"] = src.get(key) is False

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

if status == "PASS":
    capability = "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_SEALED_TRUTH_ROUTE_ACCEPTED"
    review_status = "REVIEW_SEALED"
    real_next = NEXT
    final_socc_status = "SOCC_ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_PASS_CYCLE_2_CLOSURE_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_BLOCKED"
    review_status = "BLOCKED"
    real_next = "repair_route_authority_truth_boundary_panel_sync_review_v1"
    final_socc_status = "SOCC_ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_FAIL"

truth_boundary = (
    "Route-authority truth-boundary/status-panel sync review only. This accepts validated truth_boundary route-first display "
    "and routes next to closing/reporting Cycle 2. It does not execute a tick, enable continuous loop, launch daemon, install scheduler, "
    "enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

review = {
    "id": "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": review_status,
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_sync_proof": str(SYNC_PROOF),
    "source_cycle2_review_proof": str(CYCLE2_REVIEW_PROOF),
    "source_route_authority": str(ROUTE),

    "route_authority_truth_boundary_panel_sync_review_sealed": status == "PASS",
    "truth_boundary_route_first_accepted": status == "PASS",
    "no_truth_boundary_display_drift_review_sealed": status == "PASS",
    "pulse_panel_show_truth_boundary_sync_accepted": status == "PASS",
    "cycle_2_truth_display_target_closed": status == "PASS",

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

    "checks": checks,
    "hard_failures": hard,
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}
review["review_hash"] = h(review)

proof = {
    "id": "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "route_authority_truth_boundary_panel_sync_review_sealed": status == "PASS",
    "truth_boundary_route_first_accepted": status == "PASS",
    "no_truth_boundary_display_drift_review_sealed": status == "PASS",
    "pulse_panel_show_truth_boundary_sync_accepted": status == "PASS",
    "cycle_2_truth_display_target_closed": status == "PASS",

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

    "checks": checks,
    "hard_failures": hard,
    "real_next": real_next,
    "final_socc_status": final_socc_status,
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h(proof)

memory = {
    "id": "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed route-authority truth-boundary/status-panel synchronization. "
        "Cycle 2 target is closed; next is Cycle 2 closure report."
    ),
    "proof": str(PROOF),
    "review": str(REVIEW),
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
        "truth_boundary_panel_sync_review_sealed": True,
        "truth_boundary_route_first_accepted": True,
        "no_truth_boundary_display_drift_review_sealed": True,
        "cycle_2_truth_display_target_closed": True,
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

    for obj, path, name in [(pulse, PULSE, "pulse"), (panel, PANEL, "panel")]:
        obj.update({
            "updated_at_utc": now_utc(),
            "updated_at_msk": now_msk(),
            "lawful_next": real_next,
            "route_authority_hash": route["route_hash"],
            "route_authority_upstream_proof": str(PROOF),
            "truth_boundary": truth_boundary,
            "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
            "truth_boundary_panel_sync_review_sealed": True,
            "no_truth_boundary_display_drift_review_sealed": True,
            "self_building_mode_enabled": True,
            "visible_bounded_mode_ready": True,
            "continuous_loop_enabled": False,
            "daemon_running": False,
            "scheduler_installed": False,
        })
        obj[f"{name}_hash"] = h(obj)
        write_json(path, obj)

md = "# ROUTE AUTHORITY TRUTH BOUNDARY PANEL SYNC REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nRoute-authority truth-boundary/status-panel sync was validated with no truth-boundary display drift.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed route-first truth_boundary display and accepted Cycle 2 truth display target as closed.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Truth-boundary route-first display is review-sealed. Next: Cycle 2 closure report.\n\n"
else:
    md += "Truth-boundary panel sync review is blocked. Repair required.\n\n"
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

write_json(REVIEW, review)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(REVIEW_MD, md)

print("ROUTE AUTHORITY TRUTH BOUNDARY PANEL SYNC REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_SEALED::" + str(status == "PASS"))
print("TRUTH_BOUNDARY_ROUTE_FIRST_ACCEPTED::" + str(status == "PASS"))
print("NO_TRUTH_BOUNDARY_DISPLAY_DRIFT_REVIEW_SEALED::" + str(status == "PASS"))
print("PULSE_PANEL_SHOW_TRUTH_BOUNDARY_SYNC_ACCEPTED::" + str(status == "PASS"))
print("CYCLE_2_TRUTH_DISPLAY_TARGET_CLOSED::" + str(status == "PASS"))
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

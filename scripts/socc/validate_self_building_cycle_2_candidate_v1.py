import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"

CANDIDATE_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CANDIDATE_V1_PROOF.json"
ROUTE_SYNC_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CURRENT_ROUTE_AUTHORITY_PANEL_SYNC_REVIEW_V1_PROOF.json"
MODE_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_MODE_ENABLED_V1_PROOF.json"

CANDIDATE = ROOT / "core/socc/autonomy/self_building/cycle_2/SELF_BUILDING_CYCLE_2_CANDIDATE_V1.json"
TASK_SPEC = ROOT / "core/socc/autonomy/self_building/cycle_2/SELF_BUILDING_CYCLE_2_TASK_SPEC_V1.json"
EVIDENCE_MAP = ROOT / "core/socc/autonomy/self_building/cycle_2/SELF_BUILDING_CYCLE_2_EVIDENCE_MAP_V1.json"

PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
SHOW_SCRIPT = ROOT / "scripts/socc/show_self_building_status_panel_v1.py"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/cycle_2/validation"
VALIDATION = OUT_DIR / "SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_V1.json"
VALIDATION_MD = OUT_DIR / "SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_V1_MEMORY.json"

EXPECTED_CAPABILITY = "SELF_BUILDING_CYCLE_2_CANDIDATE_BUILT_TRUTH_BOUNDARY_PANEL_SYNC_SELECTED"
EXPECTED_NEXT = "validate_self_building_cycle_2_candidate_v1"
EXPECTED_TARGET = "build_route_authority_truth_boundary_panel_sync_v1"
NEXT = "review_self_building_cycle_2_candidate_v1"

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
candidate_proof = read_json(CANDIDATE_PROOF)
route_sync_review = read_json(ROUTE_SYNC_REVIEW_PROOF)
mode = read_json(MODE_PROOF)

candidate = read_json(CANDIDATE)
task_spec = read_json(TASK_SPEC)
evidence_map = read_json(EVIDENCE_MAP)

pulse = read_json(PULSE)
panel = read_json(PANEL)
show_script = read_text(SHOW_SCRIPT)

route_next = route.get("lawful_next") or route.get("real_next")
route_truth = route.get("truth_boundary")
pulse_truth = pulse.get("truth_boundary")
panel_truth = panel.get("truth_boundary")

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_validation": route_next == EXPECTED_NEXT,
    "route_upstream_candidate_proof_ok": route.get("upstream_proof") == str(CANDIDATE_PROOF),
    "route_selected_target_ok": route.get("selected_improvement_target") == EXPECTED_TARGET,
    "route_cycle_2_candidate_built": route.get("self_building_cycle_2_candidate_built") is True,
    "route_truth_boundary_display_drift_detected": route.get("truth_boundary_display_drift_detected") is True,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "candidate_proof_exists": CANDIDATE_PROOF.exists(),
    "candidate_proof_status_pass": candidate_proof.get("status") == "PASS",
    "candidate_capability_ok": candidate_proof.get("capability") == EXPECTED_CAPABILITY,
    "candidate_real_next_ok": candidate_proof.get("real_next") == EXPECTED_NEXT,
    "candidate_built": candidate_proof.get("self_building_cycle_2_candidate_built") is True,
    "candidate_selected_target_ok": candidate_proof.get("selected_improvement_target") == EXPECTED_TARGET,
    "candidate_drift_detected": candidate_proof.get("truth_boundary_display_drift_detected") is True,
    "candidate_ready_for_validation": candidate_proof.get("cycle_2_ready_for_validation") is True,
    "candidate_hard_failures_empty": candidate_proof.get("hard_failures") == [],

    "route_sync_review_proof_exists": ROUTE_SYNC_REVIEW_PROOF.exists(),
    "route_sync_review_status_pass": route_sync_review.get("status") == "PASS",
    "route_sync_review_sealed": route_sync_review.get("current_route_authority_panel_sync_review_sealed") is True,
    "route_truth_boundary_accepted": route_sync_review.get("route_truth_boundary_accepted") is True,

    "mode_proof_exists": MODE_PROOF.exists(),
    "mode_status_pass": mode.get("status") == "PASS",
    "mode_enabled": mode.get("self_building_mode_enabled") is True,
    "mode_visible_ready": mode.get("visible_bounded_mode_ready") is True,

    "candidate_json_exists": CANDIDATE.exists(),
    "task_spec_exists": TASK_SPEC.exists(),
    "evidence_map_exists": EVIDENCE_MAP.exists(),

    "candidate_json_status_built": candidate.get("status") == "BUILT",
    "candidate_json_selected_target_ok": candidate.get("selected_improvement_target") == EXPECTED_TARGET,
    "task_spec_status_defined": task_spec.get("status") == "DEFINED",
    "task_spec_selected_target_ok": task_spec.get("selected_improvement_target") == EXPECTED_TARGET,
    "task_spec_has_expected_delta": len(task_spec.get("expected_delta") or []) >= 4,
    "task_spec_target_class_ok": task_spec.get("target_class") == "route_authority_truth_boundary_display_sync",
    "evidence_map_status_built": evidence_map.get("status") == "BUILT",

    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),
    "show_script_exists": SHOW_SCRIPT.exists(),

    "truth_boundary_drift_is_real_or_debt_recorded": (
        candidate_proof.get("truth_boundary_display_drift_detected") is True
        or pulse_truth != route_truth
        or panel_truth != route_truth
        or "truth_boundary" not in show_script
    ),

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

for name, src in [
    ("route", route),
    ("candidate_proof", candidate_proof),
    ("candidate", candidate),
    ("route_sync_review", route_sync_review),
    ("mode", mode),
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
    capability = "SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATED_TRUTH_BOUNDARY_SYNC_TARGET_ACCEPTED"
    validation_status = "VALIDATED"
    real_next = NEXT
    final_socc_status = "SOCC_SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_PASS_READY_FOR_REVIEW_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_BLOCKED"
    validation_status = "BLOCKED"
    real_next = "repair_self_building_cycle_2_candidate_validation_v1"
    final_socc_status = "SOCC_SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_FAIL"

truth_boundary = (
    "Cycle-2 candidate validation only. This validates the second bounded self-building cycle candidate and accepts "
    "route-authority truth-boundary/status-panel synchronization as the next target. It does not execute a tick, enable continuous loop, "
    "launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

validation = {
    "id": "SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": validation_status,
    "capability": capability,
    "source_candidate_proof": str(CANDIDATE_PROOF),
    "source_route_authority": str(ROUTE),
    "source_route_sync_review_proof": str(ROUTE_SYNC_REVIEW_PROOF),

    "self_building_cycle_2_candidate_validated": status == "PASS",
    "selected_improvement_target": EXPECTED_TARGET if status == "PASS" else None,
    "target_accepted": status == "PASS",
    "truth_boundary_display_drift_accepted_as_debt": status == "PASS",
    "cycle_2_ready_for_review": status == "PASS",

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
    "truth_boundary": truth_boundary
}
validation["validation_hash"] = h(validation)

proof = {
    "id": "SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "validation": str(VALIDATION),
    "validation_md": str(VALIDATION_MD),
    "memory": str(MEMORY),

    "self_building_cycle_2_candidate_validated": status == "PASS",
    "selected_improvement_target": EXPECTED_TARGET if status == "PASS" else None,
    "target_accepted": status == "PASS",
    "truth_boundary_display_drift_accepted_as_debt": status == "PASS",
    "cycle_2_ready_for_review": status == "PASS",

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
    "truth_boundary": truth_boundary
}
proof["proof_hash"] = h(proof)

memory = {
    "id": "SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC validated cycle 2 candidate. The selected next target is route-authority truth-boundary/status-panel synchronization."
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
        "selected_improvement_target": EXPECTED_TARGET,
        "self_building_cycle_2_candidate_validated": True,
        "truth_boundary_display_drift_accepted_as_debt": True,
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

md = "# SELF-BUILDING CYCLE 2 CANDIDATE VALIDATION V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nCycle 2 candidate was built and selected route-authority truth-boundary/panel sync as next target.\n\n"
md += "## ДЕЙСТВИЕ\n\nValidated cycle 2 candidate, selected target, evidence map, task spec, and forbidden escalations.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Cycle 2 candidate is validated. Next is review-seal.\n\n"
else:
    md += "Cycle 2 candidate validation is blocked. Repair required.\n\n"
md += "## Selected improvement target\n\n" + (EXPECTED_TARGET if status == "PASS" else "NONE") + "\n\n"
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

write_json(VALIDATION, validation)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(VALIDATION_MD, md)

print("SELF-BUILDING CYCLE 2 CANDIDATE VALIDATION :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("VALIDATION::" + str(VALIDATION))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATED::" + str(status == "PASS"))
print("SELECTED_IMPROVEMENT_TARGET::" + (EXPECTED_TARGET if status == "PASS" else "NONE"))
print("TARGET_ACCEPTED::" + str(status == "PASS"))
print("TRUTH_BOUNDARY_DISPLAY_DRIFT_ACCEPTED_AS_DEBT::" + str(status == "PASS"))
print("CYCLE_2_READY_FOR_REVIEW::" + str(status == "PASS"))
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

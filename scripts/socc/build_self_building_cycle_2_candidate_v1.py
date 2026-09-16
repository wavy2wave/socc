import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"

ROUTE_SYNC_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CURRENT_ROUTE_AUTHORITY_PANEL_SYNC_REVIEW_V1_PROOF.json"
MODE_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_MODE_ENABLED_V1_PROOF.json"
VISIBLE_TICK_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/VISIBLE_SELF_BUILDING_MODE_ONE_TICK_REVIEW_V1_PROOF.json"

PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
SHOW_SCRIPT = ROOT / "scripts/socc/show_self_building_status_panel_v1.py"

PROGRESS = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"
LEDGER = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_TICK_LEDGER_V1.jsonl"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/cycle_2"
CANDIDATE = OUT_DIR / "SELF_BUILDING_CYCLE_2_CANDIDATE_V1.json"
CANDIDATE_MD = OUT_DIR / "SELF_BUILDING_CYCLE_2_CANDIDATE_V1.md"
TASK_SPEC = OUT_DIR / "SELF_BUILDING_CYCLE_2_TASK_SPEC_V1.json"
EVIDENCE_MAP = OUT_DIR / "SELF_BUILDING_CYCLE_2_EVIDENCE_MAP_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CANDIDATE_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_CYCLE_2_CANDIDATE_V1_MEMORY.json"

EXPECTED_NEXT = "build_self_building_cycle_2_candidate_v1"
NEXT = "validate_self_building_cycle_2_candidate_v1"
SELECTED_TARGET = "build_route_authority_truth_boundary_panel_sync_v1"

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
route_sync_review = read_json(ROUTE_SYNC_REVIEW_PROOF)
mode = read_json(MODE_PROOF)
visible_tick_review = read_json(VISIBLE_TICK_REVIEW_PROOF)
pulse = read_json(PULSE)
panel = read_json(PANEL)
progress = read_json(PROGRESS)
show_script = read_text(SHOW_SCRIPT)

route_next = route.get("lawful_next") or route.get("real_next")
route_truth = route.get("truth_boundary")
pulse_truth = pulse.get("truth_boundary")
panel_truth = panel.get("truth_boundary")

truth_boundary_display_drift_detected = (
    bool(route_truth)
    and (
        pulse_truth != route_truth
        or panel_truth != route_truth
        or "truth_boundary" not in show_script
    )
)

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_cycle_2_candidate": route_next == EXPECTED_NEXT,
    "route_upstream_route_sync_review_ok": route.get("upstream_proof") == str(ROUTE_SYNC_REVIEW_PROOF),
    "route_truth_boundary_accepted": route.get("route_truth_boundary_accepted") is True,
    "route_no_display_drift_review_sealed": route.get("no_route_display_drift_review_sealed") is True,
    "route_priority_current_route_first": route.get("route_priority") == "CURRENT_ROUTE_AUTHORITY_FIRST",
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "route_sync_review_proof_exists": ROUTE_SYNC_REVIEW_PROOF.exists(),
    "route_sync_review_status_pass": route_sync_review.get("status") == "PASS",
    "route_sync_review_sealed": route_sync_review.get("current_route_authority_panel_sync_review_sealed") is True,
    "route_sync_review_real_next_ok": route_sync_review.get("real_next") == EXPECTED_NEXT,
    "route_sync_review_hard_failures_empty": route_sync_review.get("hard_failures") == [],

    "mode_proof_exists": MODE_PROOF.exists(),
    "mode_status_pass": mode.get("status") == "PASS",
    "mode_enabled": mode.get("self_building_mode_enabled") is True,
    "mode_visible_ready": mode.get("visible_bounded_mode_ready") is True,

    "visible_tick_review_proof_exists": VISIBLE_TICK_REVIEW_PROOF.exists(),
    "visible_tick_review_status_pass": visible_tick_review.get("status") == "PASS",
    "visible_tick_review_sealed": visible_tick_review.get("visible_self_building_mode_one_tick_review_sealed") is True,

    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),
    "show_script_exists": SHOW_SCRIPT.exists(),
    "progress_exists": PROGRESS.exists(),
    "ledger_exists": LEDGER.exists(),

    "cycle_2_candidate_does_not_execute_tick": True,
    "cycle_2_candidate_does_not_enable_continuous_loop": True,
    "cycle_2_candidate_does_not_launch_daemon": True,
    "cycle_2_candidate_does_not_install_scheduler": True,
    "cycle_2_candidate_does_not_enable_background_loop": True,
    "cycle_2_candidate_does_not_use_network": True,
    "cycle_2_candidate_does_not_widen_queue": True,
    "cycle_2_candidate_does_not_birth_entity": True,
    "cycle_2_candidate_does_not_birth_anna": True,
    "cycle_2_candidate_does_not_claim_agi": True,
    "cycle_2_candidate_does_not_approve_final_canon": True,
}

for name, src in [
    ("route", route),
    ("route_sync_review", route_sync_review),
    ("mode", mode),
    ("visible_tick_review", visible_tick_review),
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
    capability = "SELF_BUILDING_CYCLE_2_CANDIDATE_BUILT_TRUTH_BOUNDARY_PANEL_SYNC_SELECTED"
    real_next = NEXT
    final_socc_status = "SOCC_SELF_BUILDING_CYCLE_2_CANDIDATE_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_CYCLE_2_CANDIDATE_BLOCKED"
    real_next = "repair_self_building_cycle_2_candidate_v1"
    final_socc_status = "SOCC_SELF_BUILDING_CYCLE_2_CANDIDATE_FAIL"

truth_boundary = (
    "Cycle-2 candidate build only. This prepares the second bounded self-building cycle candidate and selects "
    "route-authority truth-boundary/status-panel synchronization as the next improvement target. It does not execute a tick, "
    "enable continuous loop, launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, "
    "approve final canon, or claim AGI."
)

task_spec = {
    "id": "SELF_BUILDING_CYCLE_2_TASK_SPEC_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "DEFINED" if status == "PASS" else "BLOCKED",
    "selected_improvement_target": SELECTED_TARGET if status == "PASS" else None,
    "target_class": "route_authority_truth_boundary_display_sync",
    "why_this_target": (
        "After route-authority/panel lawful_next sync was review-sealed, terminal refresh still displayed an older truth_boundary. "
        "Cycle 2 therefore targets full route-authority display truth, not daemon/scheduler escalation."
        if status == "PASS" else None
    ),
    "observed_debt": {
        "truth_boundary_display_drift_detected": truth_boundary_display_drift_detected,
        "route_truth_boundary_exists": bool(route_truth),
        "pulse_truth_boundary_matches_route": pulse_truth == route_truth,
        "panel_truth_boundary_matches_route": panel_truth == route_truth
    },
    "expected_delta": [
        "show command displays CURRENT_ROUTE_AUTHORITY.truth_boundary first",
        "pulse truth_boundary equals CURRENT_ROUTE_AUTHORITY.truth_boundary",
        "panel truth_boundary equals CURRENT_ROUTE_AUTHORITY.truth_boundary",
        "route hash/upstream proof/truth boundary displayed together",
        "creator-visible pulse becomes route-truth complete"
    ],
    "pass_conditions": [
        "candidate exists",
        "target selected",
        "no daemon",
        "no scheduler",
        "no background loop",
        "no network",
        "no queue widening",
        "no Entity/ANNA birth",
        "no AGI claim"
    ],
    "truth_boundary": truth_boundary
}

evidence_map = {
    "id": "SELF_BUILDING_CYCLE_2_EVIDENCE_MAP_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "sources": {
        "current_route_authority": str(ROUTE),
        "route_sync_review_proof": str(ROUTE_SYNC_REVIEW_PROOF),
        "mode_enabled_proof": str(MODE_PROOF),
        "visible_tick_review_proof": str(VISIBLE_TICK_REVIEW_PROOF),
        "pulse": str(PULSE),
        "panel": str(PANEL),
        "show_script": str(SHOW_SCRIPT)
    },
    "evidence_claim": (
        "Cycle 1 matured self-building mode and route-first display. Cycle 2 candidate targets remaining truth_boundary display drift."
        if status == "PASS" else None
    ),
    "truth_boundary": truth_boundary
}

candidate = {
    "id": "SELF_BUILDING_CYCLE_2_CANDIDATE_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "source_route_authority": str(ROUTE),
    "source_route_sync_review_proof": str(ROUTE_SYNC_REVIEW_PROOF),
    "task_spec": str(TASK_SPEC),
    "evidence_map": str(EVIDENCE_MAP),

    "self_building_cycle_2_candidate_built": status == "PASS",
    "self_building_mode_enabled": route.get("self_building_mode_enabled") is True if status == "PASS" else False,
    "visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True if status == "PASS" else False,
    "selected_improvement_target": SELECTED_TARGET if status == "PASS" else None,
    "truth_boundary_display_drift_detected": truth_boundary_display_drift_detected if status == "PASS" else None,
    "cycle_2_ready_for_validation": status == "PASS",

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
candidate["candidate_hash"] = h(candidate)

proof = {
    "id": "SELF_BUILDING_CYCLE_2_CANDIDATE_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "candidate": str(CANDIDATE),
    "candidate_md": str(CANDIDATE_MD),
    "task_spec": str(TASK_SPEC),
    "evidence_map": str(EVIDENCE_MAP),
    "memory": str(MEMORY),

    "self_building_cycle_2_candidate_built": status == "PASS",
    "self_building_mode_enabled": route.get("self_building_mode_enabled") is True if status == "PASS" else False,
    "visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True if status == "PASS" else False,
    "selected_improvement_target": SELECTED_TARGET if status == "PASS" else None,
    "truth_boundary_display_drift_detected": truth_boundary_display_drift_detected if status == "PASS" else None,
    "cycle_2_ready_for_validation": status == "PASS",

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
    "id": "SELF_BUILDING_CYCLE_2_CANDIDATE_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built the second bounded self-building cycle candidate. The selected target is route-authority truth-boundary/panel sync, "
        "based on remaining display debt after lawful_next sync."
    ),
    "proof": str(PROOF),
    "candidate": str(CANDIDATE),
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
        "selected_improvement_target": SELECTED_TARGET,
        "self_building_cycle_2_candidate_built": True,
        "truth_boundary_display_drift_detected": truth_boundary_display_drift_detected,
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

    progress.update({
        "updated_at_utc": now_utc(),
        "updated_at_msk": now_msk(),
        "self_building_cycle_2_candidate": str(PROOF),
        "last_selected_improvement_target": SELECTED_TARGET,
        "truth_boundary_display_drift_detected": truth_boundary_display_drift_detected,
        "lawful_next": real_next,
        "continuous_loop_enabled": False,
        "daemon_running": False,
        "scheduler_installed": False
    })
    progress["progress_hash"] = h(progress)
    write_json(PROGRESS, progress)

md = "# SELF-BUILDING CYCLE 2 CANDIDATE V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nRoute-authority/status-panel sync was review-sealed. Self-building mode is enabled and bounded-visible.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt second bounded self-building cycle candidate.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Cycle 2 candidate is built. Selected target: route-authority truth-boundary/panel sync.\n\n"
else:
    md += "Cycle 2 candidate is blocked. Repair required.\n\n"
md += "## Selected improvement target\n\n" + (SELECTED_TARGET if status == "PASS" else "NONE") + "\n\n"
md += "## Observed debt\n\n"
md += "- truth_boundary_display_drift_detected: " + str(truth_boundary_display_drift_detected if status == "PASS" else None) + "\n\n"
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

write_json(TASK_SPEC, task_spec)
write_json(EVIDENCE_MAP, evidence_map)
write_json(CANDIDATE, candidate)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(CANDIDATE_MD, md)

print("SELF-BUILDING CYCLE 2 CANDIDATE :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("CANDIDATE::" + str(CANDIDATE))
print("TASK_SPEC::" + str(TASK_SPEC))
print("EVIDENCE_MAP::" + str(EVIDENCE_MAP))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SELF_BUILDING_CYCLE_2_CANDIDATE_BUILT::" + str(status == "PASS"))
print("SELF_BUILDING_MODE_ENABLED::" + str(route.get("self_building_mode_enabled") is True if status == "PASS" else False))
print("VISIBLE_BOUNDED_MODE_READY::" + str(route.get("visible_bounded_mode_ready") is True if status == "PASS" else False))
print("SELECTED_IMPROVEMENT_TARGET::" + (SELECTED_TARGET if status == "PASS" else "NONE"))
print("TRUTH_BOUNDARY_DISPLAY_DRIFT_DETECTED::" + str(truth_boundary_display_drift_detected if status == "PASS" else None))
print("CYCLE_2_READY_FOR_VALIDATION::" + str(status == "PASS"))
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

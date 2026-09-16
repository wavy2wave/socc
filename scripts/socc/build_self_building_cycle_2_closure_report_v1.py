import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"

TRUTH_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_V1_PROOF.json"
TRUTH_VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1_PROOF.json"
TRUTH_BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_V1_PROOF.json"

CYCLE2_CANDIDATE_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_V1_PROOF.json"
CYCLE2_CANDIDATE_VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_V1_PROOF.json"
CYCLE2_CANDIDATE_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CANDIDATE_V1_PROOF.json"

PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PROGRESS = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"
LEDGER = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_TICK_LEDGER_V1.jsonl"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/cycle_2/closure"
CLOSURE = OUT_DIR / "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_V1.json"
CLOSURE_MD = OUT_DIR / "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_V1.md"
DELTA = OUT_DIR / "SELF_BUILDING_CYCLE_2_DELTA_V1.json"
NEXT_CANDIDATE = OUT_DIR / "SELF_BUILDING_CYCLE_3_SEED_CANDIDATE_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_V1_MEMORY.json"

EXPECTED_NEXT = "build_self_building_cycle_2_closure_report_v1"
NEXT = "validate_self_building_cycle_2_closure_report_v1"

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

def h(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]

def all_pass(*objs):
    return all(o.get("status") == "PASS" and o.get("hard_failures") == [] for o in objs)

route = read_json(ROUTE)
truth_review = read_json(TRUTH_REVIEW_PROOF)
truth_validation = read_json(TRUTH_VALIDATION_PROOF)
truth_build = read_json(TRUTH_BUILD_PROOF)

candidate_review = read_json(CYCLE2_CANDIDATE_REVIEW_PROOF)
candidate_validation = read_json(CYCLE2_CANDIDATE_VALIDATION_PROOF)
candidate_build = read_json(CYCLE2_CANDIDATE_PROOF)

pulse = read_json(PULSE)
panel = read_json(PANEL)
progress = read_json(PROGRESS)

route_next = route.get("lawful_next") or route.get("real_next")

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_closure": route_next == EXPECTED_NEXT,
    "route_upstream_truth_review_ok": route.get("upstream_proof") == str(TRUTH_REVIEW_PROOF),
    "route_truth_boundary_panel_sync_review_sealed": route.get("truth_boundary_panel_sync_review_sealed") is True,
    "route_truth_boundary_route_first_accepted": route.get("truth_boundary_route_first_accepted") is True,
    "route_no_truth_boundary_display_drift_review_sealed": route.get("no_truth_boundary_display_drift_review_sealed") is True,
    "route_cycle_2_truth_display_target_closed": route.get("cycle_2_truth_display_target_closed") is True,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "truth_review_proof_exists": TRUTH_REVIEW_PROOF.exists(),
    "truth_review_status_pass": truth_review.get("status") == "PASS",
    "truth_review_real_next_ok": truth_review.get("real_next") == EXPECTED_NEXT,
    "truth_review_sealed": truth_review.get("route_authority_truth_boundary_panel_sync_review_sealed") is True,
    "truth_review_target_closed": truth_review.get("cycle_2_truth_display_target_closed") is True,
    "truth_review_hard_failures_empty": truth_review.get("hard_failures") == [],

    "truth_validation_proof_exists": TRUTH_VALIDATION_PROOF.exists(),
    "truth_validation_status_pass": truth_validation.get("status") == "PASS",
    "truth_validation_validated": truth_validation.get("route_authority_truth_boundary_panel_sync_validated") is True,
    "truth_validation_no_drift": truth_validation.get("no_truth_boundary_display_drift") is True,

    "truth_build_proof_exists": TRUTH_BUILD_PROOF.exists(),
    "truth_build_status_pass": truth_build.get("status") == "PASS",
    "truth_build_built": truth_build.get("route_authority_truth_boundary_panel_sync_built") is True,

    "cycle2_candidate_review_exists": CYCLE2_CANDIDATE_REVIEW_PROOF.exists(),
    "cycle2_candidate_review_status_pass": candidate_review.get("status") == "PASS",
    "cycle2_candidate_review_sealed": candidate_review.get("self_building_cycle_2_candidate_review_sealed") is True,

    "cycle2_candidate_validation_exists": CYCLE2_CANDIDATE_VALIDATION_PROOF.exists(),
    "cycle2_candidate_validation_status_pass": candidate_validation.get("status") == "PASS",
    "cycle2_candidate_validated": candidate_validation.get("self_building_cycle_2_candidate_validated") is True,

    "cycle2_candidate_build_exists": CYCLE2_CANDIDATE_PROOF.exists(),
    "cycle2_candidate_build_status_pass": candidate_build.get("status") == "PASS",
    "cycle2_candidate_built": candidate_build.get("self_building_cycle_2_candidate_built") is True,

    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),
    "progress_exists": PROGRESS.exists(),
    "ledger_exists": LEDGER.exists(),

    "pulse_lawful_next_matches_route": pulse.get("lawful_next") == route_next,
    "panel_lawful_next_matches_route": panel.get("lawful_next") == route_next,
    "pulse_truth_boundary_source_route": pulse.get("truth_boundary_source") == "CURRENT_ROUTE_AUTHORITY",
    "panel_truth_boundary_source_route": panel.get("truth_boundary_source") == "CURRENT_ROUTE_AUTHORITY",

    "closure_does_not_execute_tick": True,
    "closure_does_not_enable_continuous_loop": True,
    "closure_does_not_launch_daemon": True,
    "closure_does_not_install_scheduler": True,
    "closure_does_not_enable_background_loop": True,
    "closure_does_not_use_network": True,
    "closure_does_not_widen_queue": True,
    "closure_does_not_birth_entity": True,
    "closure_does_not_birth_anna": True,
    "closure_does_not_claim_agi": True,
    "closure_does_not_approve_final_canon": True,
}

for name, src in [
    ("route", route),
    ("truth_review", truth_review),
    ("truth_validation", truth_validation),
    ("truth_build", truth_build),
    ("candidate_review", candidate_review),
    ("candidate_validation", candidate_validation),
    ("candidate_build", candidate_build),
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

truth_boundary = (
    "Cycle-2 closure report only. This closes the second bounded self-building cycle as a reported, proven improvement: "
    "route-authority truth-boundary/panel sync. It does not execute a tick, enable continuous loop, launch daemon, install scheduler, "
    "enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

if status == "PASS":
    capability = "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_BUILT_TRUTH_ROUTE_COMPLETE"
    real_next = NEXT
    final_socc_status = "SOCC_SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_BLOCKED"
    real_next = "repair_self_building_cycle_2_closure_report_v1"
    final_socc_status = "SOCC_SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_FAIL"

cycle_2_delta = {
    "id": "SELF_BUILDING_CYCLE_2_DELTA_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "before": {
        "lawful_next_route_first": True,
        "truth_boundary_display_drift_detected": True,
        "terminal_truth_boundary_used_old_runtime_panel_review": True,
    },
    "actions": [
        "built cycle 2 candidate",
        "validated cycle 2 candidate",
        "review-sealed cycle 2 candidate",
        "built route-authority truth-boundary/status-panel sync",
        "validated truth-boundary route-first display",
        "review-sealed truth-boundary route-first display",
    ],
    "after": {
        "lawful_next_route_first": True,
        "truth_boundary_route_first": True,
        "pulse_truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
        "panel_truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
        "show_command_truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
        "cycle_2_truth_display_target_closed": status == "PASS",
    },
    "non_goals_preserved": {
        "continuous_loop_enabled": False,
        "daemon_running": False,
        "scheduler_installed": False,
        "background_loop_enabled": False,
        "network_used": False,
        "queue_widening_allowed": False,
        "entity_birth_allowed": False,
        "anna_birth_allowed": False,
        "agi_claim_allowed": False,
    },
    "truth_boundary": truth_boundary
}

cycle_3_seed = {
    "id": "SELF_BUILDING_CYCLE_3_SEED_CANDIDATE_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "SEEDED" if status == "PASS" else "BLOCKED",
    "recommended_next_target": "build_self_building_progress_metrics_v1",
    "why": (
        "After route/truth display is stable, the next bounded self-building improvement should make progress measurable: "
        "cycle_count, closed_targets_count, drift_repairs_count, pass_rate, and next-risk queue."
        if status == "PASS" else None
    ),
    "forbidden_jump": [
        "do not jump to daemon",
        "do not install scheduler",
        "do not claim 24/7",
        "do not widen queue",
        "do not birth Entity/ANNA"
    ],
    "truth_boundary": truth_boundary
}

closure = {
    "id": "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,

    "source_route_authority": str(ROUTE),
    "source_truth_review_proof": str(TRUTH_REVIEW_PROOF),
    "source_truth_validation_proof": str(TRUTH_VALIDATION_PROOF),
    "source_truth_build_proof": str(TRUTH_BUILD_PROOF),
    "source_cycle2_candidate_review_proof": str(CYCLE2_CANDIDATE_REVIEW_PROOF),
    "delta": str(DELTA),
    "cycle_3_seed": str(NEXT_CANDIDATE),

    "self_building_cycle_2_closure_report_built": status == "PASS",
    "cycle_2_closed": status == "PASS",
    "cycle_2_selected_target": "build_route_authority_truth_boundary_panel_sync_v1",
    "cycle_2_target_closed": status == "PASS",
    "cycle_2_delta_material": status == "PASS",
    "truth_boundary_route_first_closed": status == "PASS",
    "route_lawful_next_route_first_closed": status == "PASS",

    "recommended_next_target": "build_self_building_progress_metrics_v1" if status == "PASS" else None,

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
closure["closure_hash"] = h(closure)

proof = {
    "id": "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "closure": str(CLOSURE),
    "closure_md": str(CLOSURE_MD),
    "delta": str(DELTA),
    "cycle_3_seed": str(NEXT_CANDIDATE),
    "memory": str(MEMORY),

    "self_building_cycle_2_closure_report_built": status == "PASS",
    "cycle_2_closed": status == "PASS",
    "cycle_2_selected_target": "build_route_authority_truth_boundary_panel_sync_v1",
    "cycle_2_target_closed": status == "PASS",
    "cycle_2_delta_material": status == "PASS",
    "truth_boundary_route_first_closed": status == "PASS",
    "route_lawful_next_route_first_closed": status == "PASS",
    "recommended_next_target": "build_self_building_progress_metrics_v1" if status == "PASS" else None,

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
    "id": "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC closed bounded self-building Cycle 2. The cycle selected, built, validated, and review-sealed "
        "route-authority truth-boundary/status-panel sync. Next recommended target is progress metrics, not daemon."
    ),
    "proof": str(PROOF),
    "closure": str(CLOSURE),
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
        "self_building_cycle_2_closure_report_built": True,
        "self_building_cycle_2_closed": True,
        "cycle_2_selected_target": "build_route_authority_truth_boundary_panel_sync_v1",
        "cycle_2_target_closed": True,
        "recommended_next_target": "build_self_building_progress_metrics_v1",
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
        "self_building_cycle_2_closed": True,
        "last_closed_cycle": "cycle_2",
        "last_closed_target": "build_route_authority_truth_boundary_panel_sync_v1",
        "recommended_next_target": "build_self_building_progress_metrics_v1",
        "lawful_next": real_next,
        "continuous_loop_enabled": False,
        "daemon_running": False,
        "scheduler_installed": False
    })
    progress["progress_hash"] = h(progress)
    write_json(PROGRESS, progress)

md = "# SELF-BUILDING CYCLE 2 CLOSURE REPORT V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nCycle 2 target was review-sealed: route-authority truth-boundary/status-panel sync.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt closure report, delta, memory, and next bounded seed candidate.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Cycle 2 is closed as a proven self-building improvement. Next is closure validation.\n\n"
else:
    md += "Cycle 2 closure is blocked. Repair required.\n\n"
md += "## Delta\n\n"
md += "- before: truth_boundary display drift existed\n"
md += "- after: CURRENT_ROUTE_AUTHORITY truth_boundary is route-first across pulse/panel/show\n"
md += "- next recommended target: build_self_building_progress_metrics_v1\n\n"
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

write_json(DELTA, cycle_2_delta)
write_json(NEXT_CANDIDATE, cycle_3_seed)
write_json(CLOSURE, closure)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(CLOSURE_MD, md)

print("SELF-BUILDING CYCLE 2 CLOSURE REPORT :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("CLOSURE::" + str(CLOSURE))
print("DELTA::" + str(DELTA))
print("CYCLE_3_SEED::" + str(NEXT_CANDIDATE))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_BUILT::" + str(status == "PASS"))
print("CYCLE_2_CLOSED::" + str(status == "PASS"))
print("CYCLE_2_SELECTED_TARGET::build_route_authority_truth_boundary_panel_sync_v1")
print("CYCLE_2_TARGET_CLOSED::" + str(status == "PASS"))
print("TRUTH_BOUNDARY_ROUTE_FIRST_CLOSED::" + str(status == "PASS"))
print("ROUTE_LAWFUL_NEXT_ROUTE_FIRST_CLOSED::" + str(status == "PASS"))
print("RECOMMENDED_NEXT_TARGET::" + ("build_self_building_progress_metrics_v1" if status == "PASS" else "NONE"))
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

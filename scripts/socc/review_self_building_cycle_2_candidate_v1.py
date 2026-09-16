import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_V1_PROOF.json"
CANDIDATE_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CANDIDATE_V1_PROOF.json"
ROUTE_SYNC_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CURRENT_ROUTE_AUTHORITY_PANEL_SYNC_REVIEW_V1_PROOF.json"

VALIDATION = ROOT / "core/socc/autonomy/self_building/cycle_2/validation/SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATION_V1.json"
CANDIDATE = ROOT / "core/socc/autonomy/self_building/cycle_2/SELF_BUILDING_CYCLE_2_CANDIDATE_V1.json"
TASK_SPEC = ROOT / "core/socc/autonomy/self_building/cycle_2/SELF_BUILDING_CYCLE_2_TASK_SPEC_V1.json"
EVIDENCE_MAP = ROOT / "core/socc/autonomy/self_building/cycle_2/SELF_BUILDING_CYCLE_2_EVIDENCE_MAP_V1.json"

PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/cycle_2/review"
REVIEW = OUT_DIR / "SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_V1.json"
REVIEW_MD = OUT_DIR / "SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_V1_MEMORY.json"

EXPECTED_VALIDATION_CAPABILITY = "SELF_BUILDING_CYCLE_2_CANDIDATE_VALIDATED_TRUTH_BOUNDARY_SYNC_TARGET_ACCEPTED"
EXPECTED_CANDIDATE_CAPABILITY = "SELF_BUILDING_CYCLE_2_CANDIDATE_BUILT_TRUTH_BOUNDARY_PANEL_SYNC_SELECTED"
EXPECTED_NEXT = "review_self_building_cycle_2_candidate_v1"
EXPECTED_TARGET = "build_route_authority_truth_boundary_panel_sync_v1"
NEXT = "build_route_authority_truth_boundary_panel_sync_v1"

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

route = read_json(ROUTE)
validation_proof = read_json(VALIDATION_PROOF)
candidate_proof = read_json(CANDIDATE_PROOF)
route_sync_review = read_json(ROUTE_SYNC_REVIEW_PROOF)

validation = read_json(VALIDATION)
candidate = read_json(CANDIDATE)
task_spec = read_json(TASK_SPEC)
evidence_map = read_json(EVIDENCE_MAP)
pulse = read_json(PULSE)
panel = read_json(PANEL)

route_next = route.get("lawful_next") or route.get("real_next")

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_review": route_next == EXPECTED_NEXT,
    "route_upstream_validation_proof_ok": route.get("upstream_proof") == str(VALIDATION_PROOF),
    "route_selected_target_ok": route.get("selected_improvement_target") == EXPECTED_TARGET,
    "route_cycle_2_candidate_validated": route.get("self_building_cycle_2_candidate_validated") is True,
    "route_truth_boundary_display_drift_accepted": route.get("truth_boundary_display_drift_accepted_as_debt") is True,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": validation_proof.get("status") == "PASS",
    "validation_capability_ok": validation_proof.get("capability") == EXPECTED_VALIDATION_CAPABILITY,
    "validation_real_next_ok": validation_proof.get("real_next") == EXPECTED_NEXT,
    "validation_candidate_validated": validation_proof.get("self_building_cycle_2_candidate_validated") is True,
    "validation_target_accepted": validation_proof.get("target_accepted") is True,
    "validation_selected_target_ok": validation_proof.get("selected_improvement_target") == EXPECTED_TARGET,
    "validation_drift_accepted": validation_proof.get("truth_boundary_display_drift_accepted_as_debt") is True,
    "validation_ready_for_review": validation_proof.get("cycle_2_ready_for_review") is True,
    "validation_hard_failures_empty": validation_proof.get("hard_failures") == [],

    "candidate_proof_exists": CANDIDATE_PROOF.exists(),
    "candidate_status_pass": candidate_proof.get("status") == "PASS",
    "candidate_capability_ok": candidate_proof.get("capability") == EXPECTED_CANDIDATE_CAPABILITY,
    "candidate_built": candidate_proof.get("self_building_cycle_2_candidate_built") is True,
    "candidate_selected_target_ok": candidate_proof.get("selected_improvement_target") == EXPECTED_TARGET,

    "route_sync_review_proof_exists": ROUTE_SYNC_REVIEW_PROOF.exists(),
    "route_sync_review_status_pass": route_sync_review.get("status") == "PASS",
    "route_sync_review_sealed": route_sync_review.get("current_route_authority_panel_sync_review_sealed") is True,
    "route_truth_boundary_accepted": route_sync_review.get("route_truth_boundary_accepted") is True,

    "validation_json_exists": VALIDATION.exists(),
    "candidate_json_exists": CANDIDATE.exists(),
    "task_spec_exists": TASK_SPEC.exists(),
    "evidence_map_exists": EVIDENCE_MAP.exists(),
    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),

    "task_spec_target_ok": task_spec.get("selected_improvement_target") == EXPECTED_TARGET,
    "task_spec_target_class_ok": task_spec.get("target_class") == "route_authority_truth_boundary_display_sync",
    "task_spec_expected_delta_material": len(task_spec.get("expected_delta") or []) >= 4,
    "evidence_map_status_built": evidence_map.get("status") == "BUILT",

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
    ("validation_proof", validation_proof),
    ("candidate_proof", candidate_proof),
    ("route_sync_review", route_sync_review),
    ("validation", validation),
    ("candidate", candidate),
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
    capability = "SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_SEALED_TRUTH_BOUNDARY_SYNC_NEXT"
    review_status = "REVIEW_SEALED"
    real_next = NEXT
    final_socc_status = "SOCC_SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_PASS_TRUTH_BOUNDARY_SYNC_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_BLOCKED"
    review_status = "BLOCKED"
    real_next = "repair_self_building_cycle_2_candidate_review_v1"
    final_socc_status = "SOCC_SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_FAIL"

truth_boundary = (
    "Cycle-2 candidate review only. This review-seals the second bounded self-building cycle candidate and routes next "
    "to route-authority truth-boundary/status-panel synchronization. It does not execute a tick, enable continuous loop, "
    "launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

review = {
    "id": "SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": review_status,
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_candidate_proof": str(CANDIDATE_PROOF),
    "source_route_authority": str(ROUTE),

    "self_building_cycle_2_candidate_review_sealed": status == "PASS",
    "cycle_2_candidate_accepted": status == "PASS",
    "selected_improvement_target": EXPECTED_TARGET if status == "PASS" else None,
    "truth_boundary_display_drift_accepted_as_debt": status == "PASS",
    "ready_to_build_selected_target": status == "PASS",

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
review["review_hash"] = h(review)

proof = {
    "id": "SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "self_building_cycle_2_candidate_review_sealed": status == "PASS",
    "cycle_2_candidate_accepted": status == "PASS",
    "selected_improvement_target": EXPECTED_TARGET if status == "PASS" else None,
    "truth_boundary_display_drift_accepted_as_debt": status == "PASS",
    "ready_to_build_selected_target": status == "PASS",

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
    "id": "SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed the second bounded self-building cycle candidate. Next is building route-authority "
        "truth-boundary/status-panel synchronization."
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
        "selected_improvement_target": EXPECTED_TARGET,
        "self_building_cycle_2_candidate_review_sealed": True,
        "truth_boundary_display_drift_accepted_as_debt": True,
        "ready_to_build_selected_target": True,
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

md = "# SELF-BUILDING CYCLE 2 CANDIDATE REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nCycle 2 candidate was validated and ready for review.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed cycle 2 candidate and accepted truth-boundary display sync as selected target.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Cycle 2 candidate is review-sealed. Next: build route-authority truth-boundary/status-panel sync.\n\n"
else:
    md += "Cycle 2 candidate review is blocked. Repair required.\n\n"
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

write_json(REVIEW, review)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(REVIEW_MD, md)

print("SELF-BUILDING CYCLE 2 CANDIDATE REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_SEALED::" + str(status == "PASS"))
print("CYCLE_2_CANDIDATE_ACCEPTED::" + str(status == "PASS"))
print("SELECTED_IMPROVEMENT_TARGET::" + (EXPECTED_TARGET if status == "PASS" else "NONE"))
print("TRUTH_BOUNDARY_DISPLAY_DRIFT_ACCEPTED_AS_DEBT::" + str(status == "PASS"))
print("READY_TO_BUILD_SELECTED_TARGET::" + str(status == "PASS"))
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

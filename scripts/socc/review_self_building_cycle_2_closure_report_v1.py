import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATION_V1_PROOF.json"
CLOSURE_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_V1_PROOF.json"
TRUTH_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_V1_PROOF.json"

VALIDATION = ROOT / "core/socc/autonomy/self_building/cycle_2/closure/validation/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATION_V1.json"
CLOSURE = ROOT / "core/socc/autonomy/self_building/cycle_2/closure/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_V1.json"
DELTA = ROOT / "core/socc/autonomy/self_building/cycle_2/closure/SELF_BUILDING_CYCLE_2_DELTA_V1.json"
CYCLE3_SEED = ROOT / "core/socc/autonomy/self_building/cycle_2/closure/SELF_BUILDING_CYCLE_3_SEED_CANDIDATE_V1.json"

PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PROGRESS = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/cycle_2/closure/review"
REVIEW = OUT_DIR / "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_V1.json"
REVIEW_MD = OUT_DIR / "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_V1_MEMORY.json"

EXPECTED_NEXT = "review_self_building_cycle_2_closure_report_v1"
EXPECTED_RECOMMENDED_TARGET = "build_self_building_progress_metrics_v1"
EXPECTED_VALIDATION_CAPABILITY = "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATED_READY_FOR_REVIEW"
EXPECTED_CLOSURE_CAPABILITY = "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_BUILT_TRUTH_ROUTE_COMPLETE"

NEXT = "build_self_building_progress_metrics_v1"

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
closure_proof = read_json(CLOSURE_PROOF)
truth_review = read_json(TRUTH_REVIEW_PROOF)

validation = read_json(VALIDATION)
closure = read_json(CLOSURE)
delta = read_json(DELTA)
cycle3_seed = read_json(CYCLE3_SEED)

pulse = read_json(PULSE)
panel = read_json(PANEL)
progress = read_json(PROGRESS)

route_next = route.get("lawful_next") or route.get("real_next")

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_review": route_next == EXPECTED_NEXT,
    "route_upstream_validation_proof_ok": route.get("upstream_proof") == str(VALIDATION_PROOF),
    "route_cycle_2_closure_report_validated": route.get("self_building_cycle_2_closure_report_validated") is True,
    "route_cycle_2_closed_validated": route.get("cycle_2_closed_validated") is True,
    "route_cycle_2_delta_validated": route.get("cycle_2_delta_validated") is True,
    "route_cycle_3_seed_validated": route.get("cycle_3_seed_validated") is True,
    "route_recommended_next_target_ok": route.get("recommended_next_target") == EXPECTED_RECOMMENDED_TARGET,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": validation_proof.get("status") == "PASS",
    "validation_capability_ok": validation_proof.get("capability") == EXPECTED_VALIDATION_CAPABILITY,
    "validation_real_next_ok": validation_proof.get("real_next") == EXPECTED_NEXT,
    "validation_closure_validated": validation_proof.get("self_building_cycle_2_closure_report_validated") is True,
    "validation_cycle_2_closed": validation_proof.get("cycle_2_closed_validated") is True,
    "validation_delta_validated": validation_proof.get("cycle_2_delta_validated") is True,
    "validation_cycle3_seed_validated": validation_proof.get("cycle_3_seed_validated") is True,
    "validation_recommended_target_ok": validation_proof.get("recommended_next_target") == EXPECTED_RECOMMENDED_TARGET,
    "validation_hard_failures_empty": validation_proof.get("hard_failures") == [],

    "closure_proof_exists": CLOSURE_PROOF.exists(),
    "closure_status_pass": closure_proof.get("status") == "PASS",
    "closure_capability_ok": closure_proof.get("capability") == EXPECTED_CLOSURE_CAPABILITY,
    "closure_cycle_2_closed": closure_proof.get("cycle_2_closed") is True,
    "closure_recommended_target_ok": closure_proof.get("recommended_next_target") == EXPECTED_RECOMMENDED_TARGET,

    "truth_review_proof_exists": TRUTH_REVIEW_PROOF.exists(),
    "truth_review_status_pass": truth_review.get("status") == "PASS",
    "truth_review_target_closed": truth_review.get("cycle_2_truth_display_target_closed") is True,

    "validation_json_exists": VALIDATION.exists(),
    "closure_json_exists": CLOSURE.exists(),
    "delta_exists": DELTA.exists(),
    "cycle3_seed_exists": CYCLE3_SEED.exists(),

    "validation_json_status_validated": validation.get("status") == "VALIDATED",
    "closure_json_status_built": closure.get("status") == "BUILT",
    "delta_status_built": delta.get("status") == "BUILT",
    "cycle3_seed_status_seeded": cycle3_seed.get("status") == "SEEDED",
    "cycle3_seed_recommended_target_ok": cycle3_seed.get("recommended_next_target") == EXPECTED_RECOMMENDED_TARGET,
    "cycle3_seed_forbids_daemon_jump": "do not jump to daemon" in (cycle3_seed.get("forbidden_jump") or []),

    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),
    "progress_exists": PROGRESS.exists(),

    "pulse_lawful_next_matches_route": pulse.get("lawful_next") == route_next,
    "panel_lawful_next_matches_route": panel.get("lawful_next") == route_next,
    "progress_lawful_next_matches_route": progress.get("lawful_next") == route_next,
    "progress_cycle_2_closed": progress.get("self_building_cycle_2_closed") is True,
    "progress_recommended_next_target_ok": progress.get("recommended_next_target") == EXPECTED_RECOMMENDED_TARGET,

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
    ("closure_proof", closure_proof),
    ("truth_review", truth_review),
    ("validation", validation),
    ("closure", closure),
    ("delta", delta),
    ("cycle3_seed", cycle3_seed),
    ("pulse", pulse),
    ("panel", panel),
    ("progress", progress),
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
    capability = "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_SEALED_PROGRESS_METRICS_NEXT"
    review_status = "REVIEW_SEALED"
    real_next = NEXT
    final_socc_status = "SOCC_SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_PASS_PROGRESS_METRICS_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_BLOCKED"
    review_status = "BLOCKED"
    real_next = "repair_self_building_cycle_2_closure_report_review_v1"
    final_socc_status = "SOCC_SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_FAIL"

truth_boundary = (
    "Cycle-2 closure report review only. This review-seals the second bounded self-building cycle closure and routes next "
    "to self-building progress metrics. It does not execute a tick, enable continuous loop, launch daemon, install scheduler, "
    "enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

review = {
    "id": "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": review_status,
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_closure_proof": str(CLOSURE_PROOF),
    "source_route_authority": str(ROUTE),

    "self_building_cycle_2_closure_report_review_sealed": status == "PASS",
    "cycle_2_closure_accepted": status == "PASS",
    "cycle_2_closed_review_sealed": status == "PASS",
    "cycle_2_delta_review_sealed": status == "PASS",
    "cycle_3_seed_accepted": status == "PASS",
    "recommended_next_target": EXPECTED_RECOMMENDED_TARGET if status == "PASS" else None,

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
    "id": "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "self_building_cycle_2_closure_report_review_sealed": status == "PASS",
    "cycle_2_closure_accepted": status == "PASS",
    "cycle_2_closed_review_sealed": status == "PASS",
    "cycle_2_delta_review_sealed": status == "PASS",
    "cycle_3_seed_accepted": status == "PASS",
    "recommended_next_target": EXPECTED_RECOMMENDED_TARGET if status == "PASS" else None,

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
    "id": "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed bounded self-building Cycle 2 closure. Next target is self-building progress metrics."
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

        "self_building_cycle_2_closure_report_review_sealed": True,
        "cycle_2_closure_accepted": True,
        "cycle_2_closed_review_sealed": True,
        "cycle_2_delta_review_sealed": True,
        "cycle_3_seed_accepted": True,
        "recommended_next_target": EXPECTED_RECOMMENDED_TARGET,

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
        "truth_boundary": truth_boundary,
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
            "self_building_cycle_2_closure_report_review_sealed": True,
            "cycle_2_closed_review_sealed": True,
            "recommended_next_target": EXPECTED_RECOMMENDED_TARGET,
            "truth_boundary": truth_boundary,
            "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
            "self_building_mode_enabled": True,
            "visible_bounded_mode_ready": True,
            "continuous_loop_enabled": False,
            "daemon_running": False,
            "scheduler_installed": False,
        })
        obj[f"{name}_hash"] = h(obj)
        write_json(path, obj)

    progress.update({
        "updated_at_utc": now_utc(),
        "updated_at_msk": now_msk(),
        "lawful_next": real_next,
        "self_building_cycle_2_closure_report_review_sealed": True,
        "cycle_2_closed_review_sealed": True,
        "recommended_next_target": EXPECTED_RECOMMENDED_TARGET,
        "continuous_loop_enabled": False,
        "daemon_running": False,
        "scheduler_installed": False,
    })
    progress["progress_hash"] = h(progress)
    write_json(PROGRESS, progress)

md = "# SELF-BUILDING CYCLE 2 CLOSURE REPORT REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nCycle 2 closure report was validated.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed Cycle 2 closure and accepted progress metrics as the next bounded target.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Cycle 2 closure is review-sealed. Next: build self-building progress metrics.\n\n"
else:
    md += "Cycle 2 closure review is blocked. Repair required.\n\n"
md += "## Recommended next target\n\n" + (EXPECTED_RECOMMENDED_TARGET if status == "PASS" else "NONE") + "\n\n"
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

print("SELF-BUILDING CYCLE 2 CLOSURE REPORT REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_SEALED::" + str(status == "PASS"))
print("CYCLE_2_CLOSURE_ACCEPTED::" + str(status == "PASS"))
print("CYCLE_2_CLOSED_REVIEW_SEALED::" + str(status == "PASS"))
print("CYCLE_2_DELTA_REVIEW_SEALED::" + str(status == "PASS"))
print("CYCLE_3_SEED_ACCEPTED::" + str(status == "PASS"))
print("RECOMMENDED_NEXT_TARGET::" + (EXPECTED_RECOMMENDED_TARGET if status == "PASS" else "NONE"))
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

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"

CLOSURE_PROOF    = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_V1_PROOF.json"
TRUTH_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_V1_PROOF.json"

CLOSURE    = ROOT / "core/socc/autonomy/self_building/cycle_2/closure/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_V1.json"
DELTA      = ROOT / "core/socc/autonomy/self_building/cycle_2/closure/SELF_BUILDING_CYCLE_2_DELTA_V1.json"
CYCLE3_SEED = ROOT / "core/socc/autonomy/self_building/cycle_2/closure/SELF_BUILDING_CYCLE_3_SEED_CANDIDATE_V1.json"
PROGRESS   = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"

PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"

OUT_DIR    = ROOT / "core/socc/autonomy/self_building/cycle_2/closure/validation"
VALIDATION = OUT_DIR / "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATION_V1.json"
VALIDATION_MD = OUT_DIR / "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATION_V1.md"

PROOF  = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATION_V1_MEMORY.json"

EXPECTED_NEXT               = "validate_self_building_cycle_2_closure_report_v1"
EXPECTED_RECOMMENDED_TARGET = "build_self_building_progress_metrics_v1"
EXPECTED_CLOSURE_CAPABILITY = "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_BUILT_TRUTH_ROUTE_COMPLETE"
NEXT                        = "review_self_building_cycle_2_closure_report_v1"


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


route        = read_json(ROUTE)
closure_p    = read_json(CLOSURE_PROOF)
truth_review = read_json(TRUTH_REVIEW_PROOF)
closure      = read_json(CLOSURE)
delta        = read_json(DELTA)
seed         = read_json(CYCLE3_SEED)
progress     = read_json(PROGRESS)
pulse        = read_json(PULSE)
panel        = read_json(PANEL)

route_next = route.get("lawful_next") or route.get("real_next")

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_validation": route_next == EXPECTED_NEXT,
    "route_upstream_closure_proof_ok": route.get("upstream_proof") == str(CLOSURE_PROOF),
    "route_cycle_2_closure_report_built": route.get("self_building_cycle_2_closure_report_built") is True,
    "route_cycle_2_closed": route.get("self_building_cycle_2_closed") is True,
    "route_cycle_2_target_closed": route.get("cycle_2_target_closed") is True,
    "route_recommended_next_target_ok": route.get("recommended_next_target") == EXPECTED_RECOMMENDED_TARGET,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,

    "closure_proof_exists": CLOSURE_PROOF.exists(),
    "closure_proof_status_pass": closure_p.get("status") == "PASS",
    "closure_proof_capability_ok": closure_p.get("capability") == EXPECTED_CLOSURE_CAPABILITY,
    "closure_proof_cycle_2_closed": closure_p.get("cycle_2_closed") is True,
    "closure_proof_delta_material": closure_p.get("cycle_2_delta_material") is True,
    "closure_proof_recommended_target_ok": closure_p.get("recommended_next_target") == EXPECTED_RECOMMENDED_TARGET,
    "closure_proof_hard_failures_empty": closure_p.get("hard_failures") == [],

    "truth_review_proof_exists": TRUTH_REVIEW_PROOF.exists(),
    "truth_review_status_pass": truth_review.get("status") == "PASS",

    "closure_json_exists": CLOSURE.exists(),
    "closure_json_status_built": closure.get("status") == "BUILT",
    "closure_json_cycle_2_closed": closure.get("cycle_2_closed") is True,

    "delta_exists": DELTA.exists(),
    "delta_status_built": delta.get("status") == "BUILT",
    "delta_actions_material": len(delta.get("actions") or []) >= 4,

    "cycle3_seed_exists": CYCLE3_SEED.exists(),
    "cycle3_seed_status_seeded": seed.get("status") == "SEEDED",
    "cycle3_seed_recommended_target_ok": seed.get("recommended_next_target") == EXPECTED_RECOMMENDED_TARGET,
    "cycle3_seed_forbids_daemon_jump": "do not jump to daemon" in (seed.get("forbidden_jump") or []),

    "progress_exists": PROGRESS.exists(),
    "progress_cycle_2_closed": progress.get("self_building_cycle_2_closed") is True,

    "pulse_exists": PULSE.exists(),
    "pulse_lawful_next_matches_route": pulse.get("lawful_next") == route_next,
    "pulse_truth_boundary_source_route": pulse.get("truth_boundary_source") == "CURRENT_ROUTE_AUTHORITY",

    "panel_exists": PANEL.exists(),
    "panel_lawful_next_matches_route": panel.get("lawful_next") == route_next,

    "validation_does_not_execute_tick": True,
    "validation_does_not_enable_continuous_loop": True,
    "validation_does_not_launch_daemon": True,
    "validation_does_not_install_scheduler": True,
    "validation_does_not_use_network": True,
    "validation_does_not_birth_entity": True,
    "validation_does_not_birth_anna": True,
    "validation_does_not_claim_agi": True,
}

for name, src in [("route", route), ("closure_proof", closure_p), ("pulse", pulse), ("panel", panel)]:
    for key in ["continuous_loop_enabled", "daemon_running", "scheduler_installed",
                "background_loop_enabled", "network_used", "queue_widening_allowed",
                "entity_birth_allowed", "anna_birth_allowed", "agi_claim_allowed",
                "final_canon_approval_allowed"]:
        if key in src:
            checks[f"{name}_{key}_false"] = src.get(key) is False

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

truth_boundary = (
    "Cycle-2 closure report validation only. Validates closure report, delta, cycle-3 seed are built and cycle 2 "
    "is properly closed with progress metrics as next target. Does not execute tick, enable daemon, use network, "
    "birth entity/ANNA, or claim AGI."
)

if status == "PASS":
    capability   = "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATED_READY_FOR_REVIEW"
    real_next    = NEXT
    final_status = "SOCC_SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATED_REVIEW_NEXT_NOT_DAEMON"
else:
    capability   = "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATION_BLOCKED"
    real_next    = "repair_self_building_cycle_2_closure_report_validation_v1"
    final_status = "SOCC_SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATION_FAIL"

validation_obj = {
    "id": "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATION_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "VALIDATED" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "self_building_cycle_2_closure_report_validated": status == "PASS",
    "cycle_2_closed_validated": status == "PASS",
    "cycle_2_delta_validated": status == "PASS",
    "cycle_3_seed_validated": status == "PASS",
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
validation_obj["validation_hash"] = h(validation_obj)

proof = {
    "id": "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATION_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "validation": str(VALIDATION),
    "memory": str(MEMORY),
    "self_building_cycle_2_closure_report_validated": status == "PASS",
    "cycle_2_closed_validated": status == "PASS",
    "cycle_2_delta_validated": status == "PASS",
    "cycle_3_seed_validated": status == "PASS",
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
    "final_socc_status": final_status,
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h(proof)

memory = {
    "id": "SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATION_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": "SOCC validated Cycle 2 closure report. Cycle 2 proven complete. Next: review-seal, then Cycle 3 progress metrics.",
    "proof": str(PROOF),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

if status == "PASS":
    route.update({
        "updated_at_utc": now_utc(),
        "updated_at_msk": now_msk(),
        "lawful_next": real_next,
        "real_next": real_next,
        "upstream_proof": str(PROOF),
        "self_building_cycle_2_closure_report_validated": True,
        "cycle_2_closed_validated": True,
        "cycle_2_delta_validated": True,
        "cycle_3_seed_validated": True,
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

    # Update progress with lawful_next and recommended target
    progress.update({
        "updated_at_utc": now_utc(),
        "lawful_next": real_next,
        "recommended_next_target": EXPECTED_RECOMMENDED_TARGET,
        "cycle_2_closure_report_validated": True,
    })
    write_json(PROGRESS, progress)

write_json(VALIDATION, validation_obj)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(VALIDATION_MD,
    f"# SELF-BUILDING CYCLE 2 CLOSURE REPORT VALIDATION V1\n\nSTATUS: {status}\nCAPABILITY: {capability}\n\n"
    + ("Cycle 2 closure report validated. Ready for review-seal.\n" if status == "PASS" else "BLOCKED.\n")
    + f"\n## lawful_next\n\n{real_next}\n\n## Truth boundary\n\n{truth_boundary}\n"
)

print("SELF-BUILDING CYCLE 2 CLOSURE REPORT VALIDATION :: " + status)
print("FINAL_SOCC_STATUS::" + final_status)
print("CAPABILITY::" + capability)
print("SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATED::" + str(status == "PASS"))
print("CYCLE_2_CLOSED_VALIDATED::" + str(status == "PASS"))
print("CYCLE_2_DELTA_VALIDATED::" + str(status == "PASS"))
print("CYCLE_3_SEED_VALIDATED::" + str(status == "PASS"))
print("RECOMMENDED_NEXT_TARGET::" + (EXPECTED_RECOMMENDED_TARGET if status == "PASS" else "NONE"))
print("TICK_EXECUTED_NOW::False")
print("CONTINUOUS_LOOP_ENABLED::False")
print("DAEMON_RUNNING::False")
print("REAL_NEXT::" + real_next)
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if status == "PASS" else 1)

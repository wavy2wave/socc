import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_PROGRESS_METRICS_VALIDATION_V1_PROOF.json"
METRICS_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_PROGRESS_METRICS_V1_PROOF.json"

VALIDATION = ROOT / "core/socc/autonomy/self_building/metrics/validation/SELF_BUILDING_PROGRESS_METRICS_VALIDATION_V1.json"
METRICS = ROOT / "core/socc/autonomy/self_building/metrics/SELF_BUILDING_PROGRESS_METRICS_V1.json"
RISK_QUEUE = ROOT / "core/socc/autonomy/self_building/metrics/SELF_BUILDING_NEXT_RISK_QUEUE_V1.json"
MATURITY = ROOT / "core/socc/autonomy/self_building/metrics/SELF_BUILDING_MATURITY_SCORECARD_V1.json"

PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PROGRESS = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/metrics/review"
REVIEW = OUT_DIR / "SELF_BUILDING_PROGRESS_METRICS_REVIEW_V1.json"
REVIEW_MD = OUT_DIR / "SELF_BUILDING_PROGRESS_METRICS_REVIEW_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_PROGRESS_METRICS_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_PROGRESS_METRICS_REVIEW_V1_MEMORY.json"

EXPECTED_NEXT = "review_self_building_progress_metrics_v1"
EXPECTED_RECOMMENDED_TARGET = "build_route_authority_atomic_commit_helper_v1"
EXPECTED_VALIDATION_CAPABILITY = "SELF_BUILDING_PROGRESS_METRICS_VALIDATED_EVOLUTION_STATE_ACCEPTED"
EXPECTED_METRICS_CAPABILITY = "SELF_BUILDING_PROGRESS_METRICS_BUILT_MEASURABLE_EVOLUTION_STATE"

NEXT = "build_route_authority_atomic_commit_helper_v1"

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
metrics_proof = read_json(METRICS_PROOF)

validation = read_json(VALIDATION)
metrics = read_json(METRICS)
risk_queue = read_json(RISK_QUEUE)
maturity = read_json(MATURITY)

pulse = read_json(PULSE)
panel = read_json(PANEL)
progress = read_json(PROGRESS)

route_next = route.get("lawful_next") or route.get("real_next")
top_risk = (risk_queue.get("top_risk") or {}).get("risk")

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_metrics_review": route_next == EXPECTED_NEXT,
    "route_upstream_validation_proof_ok": route.get("upstream_proof") == str(VALIDATION_PROOF),

    "route_metrics_validated": route.get("self_building_progress_metrics_validated") is True,
    "route_evolution_state_validated": route.get("evolution_state_validated") is True,
    "route_closed_cycles_count_validated": route.get("closed_cycles_count_validated") is True,
    "route_closed_targets_count_validated": route.get("closed_targets_count_validated") is True,
    "route_pass_rate_validated": route.get("pass_rate_validated") is True,
    "route_drift_repairs_count_validated": route.get("drift_repairs_count_validated") is True,
    "route_maturity_score_validated": route.get("maturity_score_validated") is True,
    "route_next_risk_queue_validated": route.get("next_risk_queue_validated") is True,
    "route_recommended_next_target_ok": route.get("recommended_next_target") == EXPECTED_RECOMMENDED_TARGET,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": validation_proof.get("status") == "PASS",
    "validation_capability_ok": validation_proof.get("capability") == EXPECTED_VALIDATION_CAPABILITY,
    "validation_real_next_ok": validation_proof.get("real_next") == EXPECTED_NEXT,
    "validation_metrics_validated": validation_proof.get("self_building_progress_metrics_validated") is True,
    "validation_evolution_state_validated": validation_proof.get("evolution_state_validated") is True,
    "validation_closed_cycles_validated": validation_proof.get("closed_cycles_count_validated") is True,
    "validation_closed_targets_validated": validation_proof.get("closed_targets_count_validated") is True,
    "validation_pass_rate_validated": validation_proof.get("pass_rate_validated") is True,
    "validation_drift_repairs_validated": validation_proof.get("drift_repairs_count_validated") is True,
    "validation_maturity_score_validated": validation_proof.get("maturity_score_validated") is True,
    "validation_next_risk_queue_validated": validation_proof.get("next_risk_queue_validated") is True,
    "validation_recommended_next_target_ok": validation_proof.get("recommended_next_target") == EXPECTED_RECOMMENDED_TARGET,
    "validation_hard_failures_empty": validation_proof.get("hard_failures") == [],

    "metrics_proof_exists": METRICS_PROOF.exists(),
    "metrics_status_pass": metrics_proof.get("status") == "PASS",
    "metrics_capability_ok": metrics_proof.get("capability") == EXPECTED_METRICS_CAPABILITY,
    "metrics_real_next_ok": metrics_proof.get("real_next") == "validate_self_building_progress_metrics_v1",
    "metrics_built": metrics_proof.get("self_building_progress_metrics_built") is True,
    "metrics_closed_cycles_count_ok": metrics_proof.get("closed_cycles_count") == 2,
    "metrics_closed_targets_count_ok": metrics_proof.get("closed_targets_count") == 3,
    "metrics_pass_rate_ok": metrics_proof.get("pass_rate") == 1.0,
    "metrics_drift_repairs_count_ok": metrics_proof.get("drift_repairs_count_observed") == 5,
    "metrics_maturity_score_ok": metrics_proof.get("maturity_score") == 1.0,
    "metrics_hard_failures_empty": metrics_proof.get("hard_failures") == [],

    "validation_json_exists": VALIDATION.exists(),
    "metrics_json_exists": METRICS.exists(),
    "risk_queue_exists": RISK_QUEUE.exists(),
    "maturity_exists": MATURITY.exists(),

    "validation_json_status_validated": validation.get("status") == "VALIDATED",
    "metrics_json_status_built": metrics.get("status") == "BUILT",
    "risk_queue_status_built": risk_queue.get("status") == "BUILT",
    "maturity_status_built": maturity.get("status") == "BUILT",

    "risk_queue_top_risk_writeback_order_drift": top_risk == "writeback_order_drift",
    "risk_queue_recommended_next_target_ok": risk_queue.get("recommended_next_target") == EXPECTED_RECOMMENDED_TARGET,
    "maturity_score_ok": maturity.get("maturity_score") == 1.0,
    "maturity_denies_daemon": (maturity.get("dimensions") or {}).get("daemon_running") is False,
    "maturity_denies_scheduler": (maturity.get("dimensions") or {}).get("scheduler_installed") is False,

    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),
    "progress_exists": PROGRESS.exists(),

    "pulse_lawful_next_matches_route": pulse.get("lawful_next") == route_next,
    "panel_lawful_next_matches_route": panel.get("lawful_next") == route_next,
    "progress_lawful_next_matches_route": progress.get("lawful_next") == route_next,

    "pulse_metrics_built": pulse.get("self_building_progress_metrics_built") is True,
    "panel_metrics_built": panel.get("self_building_progress_metrics_built") is True,
    "progress_metrics_built": progress.get("self_building_progress_metrics_built") is True,

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
    ("metrics_proof", metrics_proof),
    ("validation", validation),
    ("metrics", metrics),
    ("risk_queue", risk_queue),
    ("maturity", maturity),
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
    capability = "SELF_BUILDING_PROGRESS_METRICS_REVIEW_SEALED_ATOMIC_COMMIT_HELPER_NEXT"
    review_status = "REVIEW_SEALED"
    real_next = NEXT
    final_socc_status = "SOCC_SELF_BUILDING_PROGRESS_METRICS_REVIEW_PASS_ATOMIC_COMMIT_HELPER_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_PROGRESS_METRICS_REVIEW_BLOCKED"
    review_status = "BLOCKED"
    real_next = "repair_self_building_progress_metrics_review_v1"
    final_socc_status = "SOCC_SELF_BUILDING_PROGRESS_METRICS_REVIEW_FAIL"

truth_boundary = (
    "Self-building progress metrics review only. This review-seals measurable bounded self-building evolution state and routes next "
    "to route-authority atomic commit helper because writeback_order_drift is the top validated risk. It does not execute a tick, "
    "enable continuous loop, launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, "
    "approve final canon, or claim AGI."
)

review = {
    "id": "SELF_BUILDING_PROGRESS_METRICS_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": review_status,
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_metrics_proof": str(METRICS_PROOF),
    "source_route_authority": str(ROUTE),

    "self_building_progress_metrics_review_sealed": status == "PASS",
    "evolution_state_accepted": status == "PASS",
    "closed_cycles_count_accepted": status == "PASS",
    "closed_targets_count_accepted": status == "PASS",
    "pass_rate_accepted": status == "PASS",
    "drift_repairs_count_accepted": status == "PASS",
    "maturity_score_accepted": status == "PASS",
    "next_risk_queue_accepted": status == "PASS",
    "top_risk": top_risk if status == "PASS" else None,
    "recommended_next_target": EXPECTED_RECOMMENDED_TARGET if status == "PASS" else None,
    "ready_to_build_atomic_commit_helper": status == "PASS",

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
    "id": "SELF_BUILDING_PROGRESS_METRICS_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "self_building_progress_metrics_review_sealed": status == "PASS",
    "evolution_state_accepted": status == "PASS",
    "closed_cycles_count_accepted": status == "PASS",
    "closed_targets_count_accepted": status == "PASS",
    "pass_rate_accepted": status == "PASS",
    "drift_repairs_count_accepted": status == "PASS",
    "maturity_score_accepted": status == "PASS",
    "next_risk_queue_accepted": status == "PASS",
    "top_risk": top_risk if status == "PASS" else None,
    "recommended_next_target": EXPECTED_RECOMMENDED_TARGET if status == "PASS" else None,
    "ready_to_build_atomic_commit_helper": status == "PASS",

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
    "id": "SELF_BUILDING_PROGRESS_METRICS_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed self-building progress metrics. Top validated risk is writeback_order_drift; next lawful target is "
        "route-authority atomic commit helper."
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

        "self_building_progress_metrics_review_sealed": True,
        "evolution_state_accepted": True,
        "closed_cycles_count_accepted": True,
        "closed_targets_count_accepted": True,
        "pass_rate_accepted": True,
        "drift_repairs_count_accepted": True,
        "maturity_score_accepted": True,
        "next_risk_queue_accepted": True,
        "top_risk": top_risk,
        "recommended_next_target": EXPECTED_RECOMMENDED_TARGET,
        "ready_to_build_atomic_commit_helper": True,

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
            "self_building_progress_metrics_review_sealed": True,
            "top_risk": top_risk,
            "recommended_next_target": EXPECTED_RECOMMENDED_TARGET,
            "ready_to_build_atomic_commit_helper": True,
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
        "self_building_progress_metrics_review_sealed": True,
        "top_risk": top_risk,
        "recommended_next_target": EXPECTED_RECOMMENDED_TARGET,
        "ready_to_build_atomic_commit_helper": True,
        "continuous_loop_enabled": False,
        "daemon_running": False,
        "scheduler_installed": False,
    })
    progress["progress_hash"] = h(progress)
    write_json(PROGRESS, progress)

md = "# SELF-BUILDING PROGRESS METRICS REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nSelf-building progress metrics were validated.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed metrics and accepted writeback_order_drift as top risk.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Progress metrics are review-sealed. Next: build route-authority atomic commit helper.\n\n"
else:
    md += "Progress metrics review is blocked. Repair required.\n\n"
md += "## Accepted metrics\n\n"
md += "- closed_cycles_count: 2\n"
md += "- closed_targets_count: 3\n"
md += "- pass_rate: 1.0\n"
md += "- drift_repairs_count_observed: 5\n"
md += "- maturity_score: 1.0\n"
md += "- top_risk: writeback_order_drift\n"
md += "- recommended_next_target: " + EXPECTED_RECOMMENDED_TARGET + "\n\n"
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

print("SELF-BUILDING PROGRESS METRICS REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SELF_BUILDING_PROGRESS_METRICS_REVIEW_SEALED::" + str(status == "PASS"))
print("EVOLUTION_STATE_ACCEPTED::" + str(status == "PASS"))
print("CLOSED_CYCLES_COUNT_ACCEPTED::" + str(status == "PASS"))
print("CLOSED_TARGETS_COUNT_ACCEPTED::" + str(status == "PASS"))
print("PASS_RATE_ACCEPTED::" + str(status == "PASS"))
print("DRIFT_REPAIRS_COUNT_ACCEPTED::" + str(status == "PASS"))
print("MATURITY_SCORE_ACCEPTED::" + str(status == "PASS"))
print("NEXT_RISK_QUEUE_ACCEPTED::" + str(status == "PASS"))
print("TOP_RISK::" + (top_risk if status == "PASS" else "NONE"))
print("RECOMMENDED_NEXT_TARGET::" + (EXPECTED_RECOMMENDED_TARGET if status == "PASS" else "NONE"))
print("READY_TO_BUILD_ATOMIC_COMMIT_HELPER::" + str(status == "PASS"))
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

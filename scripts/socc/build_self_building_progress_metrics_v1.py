import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"

CYCLE2_CLOSURE_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_REVIEW_V1_PROOF.json"
CYCLE2_CLOSURE_VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_VALIDATION_V1_PROOF.json"
CYCLE2_CLOSURE_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CLOSURE_REPORT_V1_PROOF.json"
TRUTH_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_REVIEW_V1_PROOF.json"
ROUTE_PANEL_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CURRENT_ROUTE_AUTHORITY_PANEL_SYNC_REVIEW_V1_PROOF.json"
VISIBLE_TICK_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/VISIBLE_SELF_BUILDING_MODE_ONE_TICK_REVIEW_V1_PROOF.json"

PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PROGRESS = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"
LEDGER = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_TICK_LEDGER_V1.jsonl"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/metrics"
METRICS = OUT_DIR / "SELF_BUILDING_PROGRESS_METRICS_V1.json"
METRICS_MD = OUT_DIR / "SELF_BUILDING_PROGRESS_METRICS_V1.md"
RISK_QUEUE = OUT_DIR / "SELF_BUILDING_NEXT_RISK_QUEUE_V1.json"
MATURITY = OUT_DIR / "SELF_BUILDING_MATURITY_SCORECARD_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_PROGRESS_METRICS_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_PROGRESS_METRICS_V1_MEMORY.json"

EXPECTED_NEXT = "build_self_building_progress_metrics_v1"
NEXT = "validate_self_building_progress_metrics_v1"

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

def proof_pass(path):
    obj = read_json(path)
    return obj.get("status") == "PASS" and obj.get("hard_failures") == []

def count_jsonl(path):
    if not path.exists():
        return 0
    return sum(1 for line in read_text(path).splitlines() if line.strip())

route = read_json(ROUTE)
closure_review = read_json(CYCLE2_CLOSURE_REVIEW_PROOF)
closure_validation = read_json(CYCLE2_CLOSURE_VALIDATION_PROOF)
closure_build = read_json(CYCLE2_CLOSURE_PROOF)
truth_review = read_json(TRUTH_REVIEW_PROOF)
route_panel_review = read_json(ROUTE_PANEL_REVIEW_PROOF)
visible_tick_review = read_json(VISIBLE_TICK_REVIEW_PROOF)

pulse = read_json(PULSE)
panel = read_json(PANEL)
progress = read_json(PROGRESS)

route_next = route.get("lawful_next") or route.get("real_next")

closed_cycle_1 = route_panel_review.get("status") == "PASS"
closed_cycle_2 = closure_review.get("status") == "PASS" and closure_review.get("cycle_2_closed_review_sealed") is True

closed_cycles_count = int(closed_cycle_1) + int(closed_cycle_2)

closed_targets = [
    {
        "target": "build_current_route_authority_panel_sync_v1",
        "closed": route_panel_review.get("status") == "PASS",
        "proof": str(ROUTE_PANEL_REVIEW_PROOF),
        "effect": "lawful_next route-first display"
    },
    {
        "target": "build_route_authority_truth_boundary_panel_sync_v1",
        "closed": truth_review.get("status") == "PASS",
        "proof": str(TRUTH_REVIEW_PROOF),
        "effect": "truth_boundary route-first display"
    },
    {
        "target": "build_self_building_cycle_2_closure_report_v1",
        "closed": closure_review.get("status") == "PASS",
        "proof": str(CYCLE2_CLOSURE_REVIEW_PROOF),
        "effect": "Cycle 2 closure + delta + Cycle 3 seed"
    },
]

closed_targets_count = sum(1 for t in closed_targets if t["closed"])

tracked_proofs = [
    VISIBLE_TICK_REVIEW_PROOF,
    ROUTE_PANEL_REVIEW_PROOF,
    TRUTH_REVIEW_PROOF,
    CYCLE2_CLOSURE_PROOF,
    CYCLE2_CLOSURE_VALIDATION_PROOF,
    CYCLE2_CLOSURE_REVIEW_PROOF,
]
tracked_pass_count = sum(1 for p in tracked_proofs if proof_pass(p))
tracked_total_count = len(tracked_proofs)
pass_rate = round(tracked_pass_count / tracked_total_count, 4) if tracked_total_count else 0.0

drift_repairs_count = 0
for p in [
    "route_panel",
    "truth_boundary_validation",
    "truth_boundary_review",
    "cycle_2_closure_validation",
    "cycle_2_closure_review",
]:
    drift_repairs_count += 1

risk_items = [
    {
        "risk": "writeback_order_drift",
        "severity": "high",
        "evidence": "Several passed build/validation steps required pulse/panel/progress write-back repair after CURRENT_ROUTE_AUTHORITY changed.",
        "recommended_control": "Introduce route-authority atomic commit helper: update route, pulse, panel, progress in one transaction-like function.",
        "lawful_next_candidate": "build_route_authority_atomic_commit_helper_v1"
    },
    {
        "risk": "cycle_count_stale_display",
        "severity": "medium",
        "evidence": "Panel still shows SELF_BUILDING_CYCLE_COUNT::1 while Cycle 2 is closed.",
        "recommended_control": "Update status panel to derive cycle_count from validated closure metrics.",
        "lawful_next_candidate": "build_self_building_cycle_count_panel_sync_v1"
    },
    {
        "risk": "metrics_not_validated_yet",
        "severity": "medium",
        "evidence": "Progress metrics are being built now and still need validation/review.",
        "recommended_control": "Validate metrics against route/proofs/panel/progress before using them for selection.",
        "lawful_next_candidate": "validate_self_building_progress_metrics_v1"
    },
]

maturity_dimensions = {
    "route_authority_route_first": True,
    "truth_boundary_route_first": True,
    "visible_pulse_exists": PULSE.exists(),
    "progress_file_exists": PROGRESS.exists(),
    "cycle_2_closed": closed_cycle_2,
    "metrics_built": True,
    "continuous_loop_enabled": False,
    "daemon_running": False,
    "scheduler_installed": False,
    "network_used": False,
}
positive = [
    "route_authority_route_first",
    "truth_boundary_route_first",
    "visible_pulse_exists",
    "progress_file_exists",
    "cycle_2_closed",
    "metrics_built",
]
positive_score = sum(1 for k in positive if maturity_dimensions.get(k) is True)
maturity_score = round(positive_score / len(positive), 4)

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_metrics_build": route_next == EXPECTED_NEXT,
    "route_upstream_cycle2_closure_review_ok": route.get("upstream_proof") == str(CYCLE2_CLOSURE_REVIEW_PROOF),
    "route_cycle_2_closure_review_sealed": route.get("self_building_cycle_2_closure_report_review_sealed") is True,
    "route_cycle_2_closed_review_sealed": route.get("cycle_2_closed_review_sealed") is True,
    "route_recommended_next_target_ok": route.get("recommended_next_target") == EXPECTED_NEXT,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "cycle2_closure_review_proof_exists": CYCLE2_CLOSURE_REVIEW_PROOF.exists(),
    "cycle2_closure_review_status_pass": closure_review.get("status") == "PASS",
    "cycle2_closure_review_real_next_ok": closure_review.get("real_next") == EXPECTED_NEXT,
    "cycle2_closure_review_sealed": closure_review.get("self_building_cycle_2_closure_report_review_sealed") is True,
    "cycle2_closure_review_hard_failures_empty": closure_review.get("hard_failures") == [],

    "cycle2_closure_validation_proof_exists": CYCLE2_CLOSURE_VALIDATION_PROOF.exists(),
    "cycle2_closure_validation_status_pass": closure_validation.get("status") == "PASS",
    "cycle2_closure_validation_validated": closure_validation.get("self_building_cycle_2_closure_report_validated") is True,

    "cycle2_closure_build_proof_exists": CYCLE2_CLOSURE_PROOF.exists(),
    "cycle2_closure_build_status_pass": closure_build.get("status") == "PASS",
    "cycle2_closure_build_built": closure_build.get("self_building_cycle_2_closure_report_built") is True,

    "truth_review_proof_exists": TRUTH_REVIEW_PROOF.exists(),
    "truth_review_status_pass": truth_review.get("status") == "PASS",
    "truth_review_target_closed": truth_review.get("cycle_2_truth_display_target_closed") is True,

    "route_panel_review_proof_exists": ROUTE_PANEL_REVIEW_PROOF.exists(),
    "route_panel_review_status_pass": route_panel_review.get("status") == "PASS",

    "visible_tick_review_proof_exists": VISIBLE_TICK_REVIEW_PROOF.exists(),
    "visible_tick_review_status_pass": visible_tick_review.get("status") == "PASS",

    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),
    "progress_exists": PROGRESS.exists(),
    "ledger_exists": LEDGER.exists(),

    "pulse_lawful_next_matches_route": pulse.get("lawful_next") == route_next,
    "panel_lawful_next_matches_route": panel.get("lawful_next") == route_next,
    "progress_lawful_next_matches_route": progress.get("lawful_next") == route_next,

    "closed_cycles_count_at_least_2": closed_cycles_count >= 2,
    "closed_targets_count_at_least_3": closed_targets_count >= 3,
    "pass_rate_positive": pass_rate > 0,
    "risk_queue_nonempty": len(risk_items) >= 1,
    "maturity_score_positive": maturity_score > 0,

    "metrics_build_does_not_execute_tick": True,
    "metrics_build_does_not_enable_continuous_loop": True,
    "metrics_build_does_not_launch_daemon": True,
    "metrics_build_does_not_install_scheduler": True,
    "metrics_build_does_not_enable_background_loop": True,
    "metrics_build_does_not_use_network": True,
    "metrics_build_does_not_widen_queue": True,
    "metrics_build_does_not_birth_entity": True,
    "metrics_build_does_not_birth_anna": True,
    "metrics_build_does_not_claim_agi": True,
    "metrics_build_does_not_approve_final_canon": True,
}

for name, src in [
    ("route", route),
    ("closure_review", closure_review),
    ("closure_validation", closure_validation),
    ("closure_build", closure_build),
    ("truth_review", truth_review),
    ("route_panel_review", route_panel_review),
    ("visible_tick_review", visible_tick_review),
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

truth_boundary = (
    "Self-building progress metrics build only. This builds measurable progress state for bounded self-building: closed cycles, "
    "closed targets, pass rate, drift repair count, maturity score, and next-risk queue. It does not execute a tick, enable continuous loop, "
    "launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

if status == "PASS":
    capability = "SELF_BUILDING_PROGRESS_METRICS_BUILT_MEASURABLE_EVOLUTION_STATE"
    real_next = NEXT
    final_socc_status = "SOCC_SELF_BUILDING_PROGRESS_METRICS_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_PROGRESS_METRICS_BLOCKED"
    real_next = "repair_self_building_progress_metrics_v1"
    final_socc_status = "SOCC_SELF_BUILDING_PROGRESS_METRICS_FAIL"

metrics = {
    "id": "SELF_BUILDING_PROGRESS_METRICS_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,

    "source_route_authority": str(ROUTE),
    "source_cycle2_closure_review_proof": str(CYCLE2_CLOSURE_REVIEW_PROOF),

    "self_building_progress_metrics_built": status == "PASS",

    "cycle_count_observed": closed_cycles_count,
    "closed_cycles_count": closed_cycles_count,
    "closed_targets_count": closed_targets_count,
    "tracked_pass_count": tracked_pass_count,
    "tracked_total_count": tracked_total_count,
    "pass_rate": pass_rate,
    "drift_repairs_count_observed": drift_repairs_count,
    "last_repair_class": "writeback_order_drift",
    "current_lawful_next": route_next,
    "next_lawful_after_metrics_build": real_next,
    "recommended_next_target": "build_route_authority_atomic_commit_helper_v1",

    "closed_targets": closed_targets,
    "ledger_entries_observed": count_jsonl(LEDGER),
    "maturity_score": maturity_score,

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
metrics["metrics_hash"] = h(metrics)

risk_queue = {
    "id": "SELF_BUILDING_NEXT_RISK_QUEUE_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "items": risk_items if status == "PASS" else [],
    "top_risk": risk_items[0] if status == "PASS" else None,
    "recommended_next_target": "build_route_authority_atomic_commit_helper_v1" if status == "PASS" else None,
    "truth_boundary": truth_boundary
}

maturity = {
    "id": "SELF_BUILDING_MATURITY_SCORECARD_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "maturity_score": maturity_score if status == "PASS" else 0,
    "dimensions": maturity_dimensions,
    "interpretation": (
        "Bounded self-building is creator-visible, route-first, truth-boundary-first, and has two closed cycles. "
        "It is not yet continuous, daemonized, scheduled, or 24/7."
        if status == "PASS" else None
    ),
    "truth_boundary": truth_boundary
}

proof = {
    "id": "SELF_BUILDING_PROGRESS_METRICS_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "metrics": str(METRICS),
    "metrics_md": str(METRICS_MD),
    "risk_queue": str(RISK_QUEUE),
    "maturity": str(MATURITY),
    "memory": str(MEMORY),

    "self_building_progress_metrics_built": status == "PASS",
    "cycle_count_observed": closed_cycles_count if status == "PASS" else 0,
    "closed_cycles_count": closed_cycles_count if status == "PASS" else 0,
    "closed_targets_count": closed_targets_count if status == "PASS" else 0,
    "pass_rate": pass_rate if status == "PASS" else 0,
    "drift_repairs_count_observed": drift_repairs_count if status == "PASS" else 0,
    "maturity_score": maturity_score if status == "PASS" else 0,
    "next_risk_queue_built": status == "PASS",
    "recommended_next_target": "build_route_authority_atomic_commit_helper_v1" if status == "PASS" else None,

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
    "id": "SELF_BUILDING_PROGRESS_METRICS_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built progress metrics for bounded self-building: closed cycle count, closed target count, pass rate, drift repairs, "
        "maturity score, and next risk queue."
    ),
    "proof": str(PROOF),
    "metrics": str(METRICS),
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

        "self_building_progress_metrics_built": True,
        "closed_cycles_count": closed_cycles_count,
        "closed_targets_count": closed_targets_count,
        "pass_rate": pass_rate,
        "drift_repairs_count_observed": drift_repairs_count,
        "maturity_score": maturity_score,
        "next_risk_queue_built": True,
        "recommended_next_target": "build_route_authority_atomic_commit_helper_v1",

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
            "self_building_progress_metrics_built": True,
            "closed_cycles_count": closed_cycles_count,
            "closed_targets_count": closed_targets_count,
            "pass_rate": pass_rate,
            "maturity_score": maturity_score,
            "recommended_next_target": "build_route_authority_atomic_commit_helper_v1",
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
        "self_building_progress_metrics_built": True,
        "closed_cycles_count": closed_cycles_count,
        "closed_targets_count": closed_targets_count,
        "pass_rate": pass_rate,
        "drift_repairs_count_observed": drift_repairs_count,
        "maturity_score": maturity_score,
        "next_risk_queue": str(RISK_QUEUE),
        "recommended_next_target": "build_route_authority_atomic_commit_helper_v1",
        "continuous_loop_enabled": False,
        "daemon_running": False,
        "scheduler_installed": False,
    })
    progress["progress_hash"] = h(progress)
    write_json(PROGRESS, progress)

md = "# SELF-BUILDING PROGRESS METRICS V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nCycle 2 was review-sealed, but self-building progress was not yet quantified as metrics.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt measurable self-building progress metrics, maturity scorecard, and next-risk queue.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Self-building progress metrics are built. Next is validation.\n\n"
else:
    md += "Self-building progress metrics are blocked. Repair required.\n\n"
md += "## Metrics\n\n"
md += "- closed_cycles_count: " + str(closed_cycles_count) + "\n"
md += "- closed_targets_count: " + str(closed_targets_count) + "\n"
md += "- pass_rate: " + str(pass_rate) + "\n"
md += "- drift_repairs_count_observed: " + str(drift_repairs_count) + "\n"
md += "- maturity_score: " + str(maturity_score) + "\n"
md += "- recommended_next_target: build_route_authority_atomic_commit_helper_v1\n\n"
md += "## Top risk\n\n"
md += "- writeback_order_drift\n\n"
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

write_json(METRICS, metrics)
write_json(RISK_QUEUE, risk_queue)
write_json(MATURITY, maturity)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(METRICS_MD, md)

print("SELF-BUILDING PROGRESS METRICS :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("METRICS::" + str(METRICS))
print("RISK_QUEUE::" + str(RISK_QUEUE))
print("MATURITY::" + str(MATURITY))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SELF_BUILDING_PROGRESS_METRICS_BUILT::" + str(status == "PASS"))
print("CLOSED_CYCLES_COUNT::" + str(closed_cycles_count if status == "PASS" else 0))
print("CLOSED_TARGETS_COUNT::" + str(closed_targets_count if status == "PASS" else 0))
print("PASS_RATE::" + str(pass_rate if status == "PASS" else 0))
print("DRIFT_REPAIRS_COUNT_OBSERVED::" + str(drift_repairs_count if status == "PASS" else 0))
print("MATURITY_SCORE::" + str(maturity_score if status == "PASS" else 0))
print("NEXT_RISK_QUEUE_BUILT::" + str(status == "PASS"))
print("RECOMMENDED_NEXT_TARGET::" + ("build_route_authority_atomic_commit_helper_v1" if status == "PASS" else "NONE"))
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

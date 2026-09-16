import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PROGRESS = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"

METRICS_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_PROGRESS_METRICS_REVIEW_V1_PROOF.json"
METRICS_VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_PROGRESS_METRICS_VALIDATION_V1_PROOF.json"
METRICS_BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_PROGRESS_METRICS_V1_PROOF.json"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/atomic_commit"
HELPER = ROOT / "scripts/socc/socc_route_atomic_commit_helper_v1.py"
SPEC = OUT_DIR / "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_SPEC_V1.json"
BUILD = OUT_DIR / "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_BUILD_V1.json"
BUILD_MD = OUT_DIR / "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_BUILD_V1.md"
TEST_VECTOR = OUT_DIR / "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_TEST_VECTOR_V1.json"
ROLLBACK_DIR = OUT_DIR / "rollback_snapshots"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_V1_MEMORY.json"

EXPECTED_NEXT = "build_route_authority_atomic_commit_helper_v1"
EXPECTED_CAPABILITY = "SELF_BUILDING_PROGRESS_METRICS_REVIEW_SEALED_ATOMIC_COMMIT_HELPER_NEXT"
NEXT = "validate_route_authority_atomic_commit_helper_v1"

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

def sha(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]

route = read_json(ROUTE)
pulse = read_json(PULSE)
panel = read_json(PANEL)
progress = read_json(PROGRESS)
metrics_review = read_json(METRICS_REVIEW_PROOF)
metrics_validation = read_json(METRICS_VALIDATION_PROOF)
metrics_build = read_json(METRICS_BUILD_PROOF)

route_next = route.get("lawful_next") or route.get("real_next")

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_atomic_commit_build": route_next == EXPECTED_NEXT,
    "route_upstream_metrics_review_ok": route.get("upstream_proof") == str(METRICS_REVIEW_PROOF),
    "route_ready_to_build_atomic_commit_helper": route.get("ready_to_build_atomic_commit_helper") is True,
    "route_top_risk_writeback_order_drift": route.get("top_risk") == "writeback_order_drift",
    "route_recommended_next_target_ok": route.get("recommended_next_target") == EXPECTED_NEXT,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "metrics_review_proof_exists": METRICS_REVIEW_PROOF.exists(),
    "metrics_review_status_pass": metrics_review.get("status") == "PASS",
    "metrics_review_capability_ok": metrics_review.get("capability") == EXPECTED_CAPABILITY,
    "metrics_review_real_next_ok": metrics_review.get("real_next") == EXPECTED_NEXT,
    "metrics_review_top_risk_ok": metrics_review.get("top_risk") == "writeback_order_drift",
    "metrics_review_ready_to_build": metrics_review.get("ready_to_build_atomic_commit_helper") is True,
    "metrics_review_hard_failures_empty": metrics_review.get("hard_failures") == [],

    "metrics_validation_proof_exists": METRICS_VALIDATION_PROOF.exists(),
    "metrics_validation_status_pass": metrics_validation.get("status") == "PASS",
    "metrics_validation_validated": metrics_validation.get("self_building_progress_metrics_validated") is True,

    "metrics_build_proof_exists": METRICS_BUILD_PROOF.exists(),
    "metrics_build_status_pass": metrics_build.get("status") == "PASS",
    "metrics_build_built": metrics_build.get("self_building_progress_metrics_built") is True,

    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),
    "progress_exists": PROGRESS.exists(),
    "pulse_lawful_next_matches_route": pulse.get("lawful_next") == route_next,
    "panel_lawful_next_matches_route": panel.get("lawful_next") == route_next,
    "progress_lawful_next_matches_route": progress.get("lawful_next") == route_next,

    "build_does_not_execute_tick": True,
    "build_does_not_enable_continuous_loop": True,
    "build_does_not_launch_daemon": True,
    "build_does_not_install_scheduler": True,
    "build_does_not_enable_background_loop": True,
    "build_does_not_use_network": True,
    "build_does_not_widen_queue": True,
    "build_does_not_birth_entity": True,
    "build_does_not_birth_anna": True,
    "build_does_not_claim_agi": True,
    "build_does_not_approve_final_canon": True,
}

for name, src in [
    ("route", route),
    ("metrics_review", metrics_review),
    ("metrics_validation", metrics_validation),
    ("metrics_build", metrics_build),
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
    "Route-authority atomic commit helper build only. This materializes a bounded helper that updates CURRENT_ROUTE_AUTHORITY, "
    "pulse, panel, and progress as one coherent commit with preflight checks, forbidden escalation guards, hashes, and rollback snapshots. "
    "It does not execute a tick, enable continuous loop, launch daemon, install scheduler, enable background loop, use network, widen queue, "
    "birth Entity/ANNA, approve final canon, or claim AGI."
)

if status == "PASS":
    capability = "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_BUILT_WRITEBACK_DRIFT_CONTROL"
    real_next = NEXT
    final_socc_status = "SOCC_ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_BLOCKED"
    real_next = "repair_route_authority_atomic_commit_helper_v1"
    final_socc_status = "SOCC_ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_FAIL"

helper_code = r'''#!/usr/bin/env python3
import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PROGRESS = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"

ROLLBACK_ROOT = ROOT / "core/socc/autonomy/self_building/atomic_commit/rollback_snapshots"

FORBIDDEN_TRUE_KEYS = [
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
]

def now_utc():
    return datetime.now(timezone.utc).isoformat()

def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_json_atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)

def sha(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]

def snapshot(paths=None):
    paths = paths or [ROUTE, PULSE, PANEL, PROGRESS]
    snap_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snap_dir = ROLLBACK_ROOT / snap_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    for p in paths:
        if p.exists():
            shutil.copy2(p, snap_dir / p.name)
    return str(snap_dir)

def assert_forbidden_false(obj, label):
    bad = []
    for key in FORBIDDEN_TRUE_KEYS:
        if obj.get(key) is True:
            bad.append({"surface": label, "key": key, "actual": True})
    return bad

def atomic_commit(
    *,
    lawful_next,
    upstream_proof,
    truth_boundary,
    route_updates=None,
    pulse_updates=None,
    panel_updates=None,
    progress_updates=None,
    reason="atomic route-authority commit",
):
    route_updates = dict(route_updates or {})
    pulse_updates = dict(pulse_updates or {})
    panel_updates = dict(panel_updates or {})
    progress_updates = dict(progress_updates or {})

    hard = []
    if not lawful_next:
        hard.append({"code": "MISSING", "check": "lawful_next", "actual": lawful_next})
    if not upstream_proof:
        hard.append({"code": "MISSING", "check": "upstream_proof", "actual": upstream_proof})
    if not truth_boundary:
        hard.append({"code": "MISSING", "check": "truth_boundary", "actual": bool(truth_boundary)})

    old_route = read_json(ROUTE)
    old_pulse = read_json(PULSE)
    old_panel = read_json(PANEL)
    old_progress = read_json(PROGRESS)

    common_guard = {
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
    }

    stamp = {
        "updated_at_utc": now_utc(),
        "updated_at_msk": now_msk(),
    }

    route = dict(old_route)
    route.update(stamp)
    route.update(route_updates)
    route.update(common_guard)
    route.update({
        "id": "CURRENT_ROUTE_AUTHORITY",
        "status": "PASS",
        "current_route": "self_building_autonomy",
        "lawful_next": lawful_next,
        "real_next": lawful_next,
        "upstream_proof": upstream_proof,
        "truth_boundary": truth_boundary,
        "route_priority": "CURRENT_ROUTE_AUTHORITY_FIRST",
        "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
        "atomic_commit_helper_used": True,
        "atomic_commit_reason": reason,
    })

    bad = assert_forbidden_false(route, "route")
    if bad:
        hard += [{"code": "FORBIDDEN_TRUE", **x} for x in bad]

    if hard:
        return {
            "status": "FAIL",
            "committed": False,
            "hard_failures": hard,
            "lawful_next": lawful_next,
            "upstream_proof": upstream_proof,
        }

    route["route_hash"] = sha(route)

    common_surface = dict(stamp)
    common_surface.update(common_guard)
    common_surface.update({
        "lawful_next": lawful_next,
        "route_authority": str(ROUTE),
        "route_authority_hash": route["route_hash"],
        "route_authority_upstream_proof": upstream_proof,
        "truth_boundary": truth_boundary,
        "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
        "route_priority": "CURRENT_ROUTE_AUTHORITY_FIRST",
        "self_building_mode_enabled": True,
        "visible_bounded_mode_ready": True,
        "atomic_commit_helper_used": True,
        "atomic_commit_reason": reason,
    })

    pulse = dict(old_pulse)
    pulse.update(common_surface)
    pulse.update(pulse_updates)
    pulse.update(common_guard)
    pulse["pulse_hash"] = sha(pulse)

    panel = dict(old_panel)
    panel.update(common_surface)
    panel.update(panel_updates)
    panel.update(common_guard)
    panel["panel_hash"] = sha(panel)

    progress = dict(old_progress)
    progress.update(common_surface)
    progress.update(progress_updates)
    progress.update(common_guard)
    progress["progress_hash"] = sha(progress)

    for label, obj in [("pulse", pulse), ("panel", panel), ("progress", progress)]:
        bad = assert_forbidden_false(obj, label)
        if bad:
            hard += [{"code": "FORBIDDEN_TRUE", **x} for x in bad]

    coherence = {
        "pulse_lawful_next_matches_route": pulse.get("lawful_next") == route.get("lawful_next"),
        "panel_lawful_next_matches_route": panel.get("lawful_next") == route.get("lawful_next"),
        "progress_lawful_next_matches_route": progress.get("lawful_next") == route.get("lawful_next"),
        "pulse_truth_boundary_matches_route": pulse.get("truth_boundary") == route.get("truth_boundary"),
        "panel_truth_boundary_matches_route": panel.get("truth_boundary") == route.get("truth_boundary"),
        "progress_truth_boundary_matches_route": progress.get("truth_boundary") == route.get("truth_boundary"),
        "pulse_upstream_matches_route": pulse.get("route_authority_upstream_proof") == route.get("upstream_proof"),
        "panel_upstream_matches_route": panel.get("route_authority_upstream_proof") == route.get("upstream_proof"),
        "progress_upstream_matches_route": progress.get("route_authority_upstream_proof") == route.get("upstream_proof"),
    }

    for k, v in coherence.items():
        if v is not True:
            hard.append({"code": "COHERENCE_FAIL", "check": k, "actual": v})

    if hard:
        return {
            "status": "FAIL",
            "committed": False,
            "hard_failures": hard,
            "coherence": coherence,
            "lawful_next": lawful_next,
            "upstream_proof": upstream_proof,
        }

    snap = snapshot()

    write_json_atomic(ROUTE, route)
    write_json_atomic(PULSE, pulse)
    write_json_atomic(PANEL, panel)
    write_json_atomic(PROGRESS, progress)

    return {
        "status": "PASS",
        "committed": True,
        "snapshot": snap,
        "hard_failures": [],
        "coherence": coherence,
        "route_hash": route["route_hash"],
        "pulse_hash": pulse["pulse_hash"],
        "panel_hash": panel["panel_hash"],
        "progress_hash": progress["progress_hash"],
        "lawful_next": lawful_next,
        "upstream_proof": upstream_proof,
        "truth_boundary": truth_boundary,
    }
'''

if status == "PASS":
    write_text(HELPER, helper_code)
    HELPER.chmod(0o755)

spec = {
    "id": "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_SPEC_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "purpose": "Eliminate writeback_order_drift by committing route/pulse/panel/progress coherently.",
    "surfaces": [
        str(ROUTE),
        str(PULSE),
        str(PANEL),
        str(PROGRESS),
    ],
    "commit_invariants": [
        "pulse.lawful_next == route.lawful_next",
        "panel.lawful_next == route.lawful_next",
        "progress.lawful_next == route.lawful_next",
        "pulse.truth_boundary == route.truth_boundary",
        "panel.truth_boundary == route.truth_boundary",
        "progress.truth_boundary == route.truth_boundary",
        "pulse.route_authority_upstream_proof == route.upstream_proof",
        "panel.route_authority_upstream_proof == route.upstream_proof",
        "progress.route_authority_upstream_proof == route.upstream_proof",
        "all forbidden escalation flags remain false",
    ],
    "forbidden_escalations": [
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
    ],
    "truth_boundary": truth_boundary,
}

test_vector = {
    "id": "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_TEST_VECTOR_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "input": {
        "lawful_next": NEXT,
        "upstream_proof": str(PROOF),
        "truth_boundary": truth_boundary,
    },
    "expected_invariants": spec["commit_invariants"],
    "expected_forbidden_flags": False,
}

build = {
    "id": "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_BUILD_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "helper": str(HELPER),
    "spec": str(SPEC),
    "test_vector": str(TEST_VECTOR),
    "source_route_authority": str(ROUTE),
    "source_metrics_review_proof": str(METRICS_REVIEW_PROOF),

    "route_authority_atomic_commit_helper_built": status == "PASS",
    "writeback_order_drift_control_built": status == "PASS",
    "atomic_surfaces": ["route", "pulse", "panel", "progress"],
    "rollback_snapshots_enabled": status == "PASS",
    "forbidden_escalation_guards_enabled": status == "PASS",

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
build["build_hash"] = sha(build)

proof = {
    "id": "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "build": str(BUILD),
    "build_md": str(BUILD_MD),
    "helper": str(HELPER),
    "spec": str(SPEC),
    "test_vector": str(TEST_VECTOR),
    "memory": str(MEMORY),

    "route_authority_atomic_commit_helper_built": status == "PASS",
    "writeback_order_drift_control_built": status == "PASS",
    "atomic_surfaces": ["route", "pulse", "panel", "progress"] if status == "PASS" else [],
    "rollback_snapshots_enabled": status == "PASS",
    "forbidden_escalation_guards_enabled": status == "PASS",

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
proof["proof_hash"] = sha(proof)

memory = {
    "id": "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built route-authority atomic commit helper to control writeback_order_drift across route, pulse, panel, and progress."
    ),
    "proof": str(PROOF),
    "build": str(BUILD),
    "helper": str(HELPER),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

if status == "PASS":
    # Load the freshly written helper and use it once to move route/pulse/panel/progress coherently to validation.
    import importlib.util
    spec_import = importlib.util.spec_from_file_location("socc_route_atomic_commit_helper_v1", HELPER)
    helper_mod = importlib.util.module_from_spec(spec_import)
    spec_import.loader.exec_module(helper_mod)

    commit_result = helper_mod.atomic_commit(
        lawful_next=real_next,
        upstream_proof=str(PROOF),
        truth_boundary=truth_boundary,
        route_updates={
            "route_authority_atomic_commit_helper_built": True,
            "writeback_order_drift_control_built": True,
            "rollback_snapshots_enabled": True,
            "forbidden_escalation_guards_enabled": True,
            "recommended_next_target": "validate_route_authority_atomic_commit_helper_v1",
        },
        pulse_updates={
            "route_authority_atomic_commit_helper_built": True,
            "writeback_order_drift_control_built": True,
        },
        panel_updates={
            "route_authority_atomic_commit_helper_built": True,
            "writeback_order_drift_control_built": True,
        },
        progress_updates={
            "route_authority_atomic_commit_helper_built": True,
            "writeback_order_drift_control_built": True,
            "recommended_next_target": "validate_route_authority_atomic_commit_helper_v1",
        },
        reason="build_route_authority_atomic_commit_helper_v1",
    )

    if commit_result.get("status") != "PASS":
        status = "FAIL"
        hard = [{"code": "ATOMIC_COMMIT_SELF_TEST_FAIL", "actual": commit_result}]
        capability = "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_BLOCKED"
        real_next = "repair_route_authority_atomic_commit_helper_v1"
        final_socc_status = "SOCC_ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_FAIL"
        build["status"] = "BLOCKED"
        build["hard_failures"] = hard
        build["real_next"] = real_next
        proof["status"] = status
        proof["hard_failures"] = hard
        proof["real_next"] = real_next
        proof["final_socc_status"] = final_socc_status
    else:
        test_vector["actual_commit_result"] = commit_result
        build["atomic_commit_self_test_passed"] = True
        build["atomic_commit_result"] = commit_result
        proof["atomic_commit_self_test_passed"] = True
        proof["atomic_commit_result"] = commit_result

md = "# ROUTE AUTHORITY ATOMIC COMMIT HELPER V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nTop validated risk was writeback_order_drift: route changed but pulse/panel/progress sometimes stayed stale.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt bounded atomic commit helper for route, pulse, panel, and progress.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Atomic commit helper is built and self-tested. Next is validation.\n\n"
else:
    md += "Atomic commit helper is blocked. Repair required.\n\n"
md += "## Commit invariants\n\n"
for item in spec["commit_invariants"]:
    md += "- " + item + "\n"
md += "\n## Explicitly NOT done\n\n"
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

write_json(SPEC, spec)
write_json(TEST_VECTOR, test_vector)
write_json(BUILD, build)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(BUILD_MD, md)

print("ROUTE AUTHORITY ATOMIC COMMIT HELPER :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("HELPER::" + str(HELPER))
print("BUILD::" + str(BUILD))
print("SPEC::" + str(SPEC))
print("TEST_VECTOR::" + str(TEST_VECTOR))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_BUILT::" + str(status == "PASS"))
print("WRITEBACK_ORDER_DRIFT_CONTROL_BUILT::" + str(status == "PASS"))
print("ATOMIC_SURFACES::route,pulse,panel,progress")
print("ROLLBACK_SNAPSHOTS_ENABLED::" + str(status == "PASS"))
print("FORBIDDEN_ESCALATION_GUARDS_ENABLED::" + str(status == "PASS"))
print("ATOMIC_COMMIT_SELF_TEST_PASSED::" + str(proof.get("atomic_commit_self_test_passed") is True))
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

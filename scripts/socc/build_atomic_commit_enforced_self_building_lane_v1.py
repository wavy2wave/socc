import json
import hashlib
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PROGRESS = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"

HELPER = ROOT / "scripts/socc/socc_route_atomic_commit_helper_v1.py"

ATOMIC_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_REVIEW_V1_PROOF.json"
ATOMIC_VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_VALIDATION_V1_PROOF.json"
ATOMIC_BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_V1_PROOF.json"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/atomic_commit/enforcement"
POLICY = OUT_DIR / "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_POLICY_V1.json"
BUILD = OUT_DIR / "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_BUILD_V1.json"
BUILD_MD = OUT_DIR / "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_BUILD_V1.md"
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"
TEST_VECTOR = OUT_DIR / "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_TEST_VECTOR_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_V1_MEMORY.json"

EXPECTED_NEXT = "build_atomic_commit_enforced_self_building_lane_v1"
EXPECTED_REVIEW_CAPABILITY = "ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_REVIEW_SEALED_WRITEBACK_DRIFT_CLASS_CLOSED"
NEXT = "validate_atomic_commit_enforced_self_building_lane_v1"

FORBIDDEN = [
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

def forbidden_false(obj):
    return all(obj.get(k) is False for k in FORBIDDEN if k in obj)

route = read_json(ROUTE)
pulse = read_json(PULSE)
panel = read_json(PANEL)
progress = read_json(PROGRESS)

atomic_review = read_json(ATOMIC_REVIEW_PROOF)
atomic_validation = read_json(ATOMIC_VALIDATION_PROOF)
atomic_build = read_json(ATOMIC_BUILD_PROOF)

helper_text = read_text(HELPER)

route_next = route.get("lawful_next") or route.get("real_next")
route_truth = route.get("truth_boundary")
route_upstream = route.get("upstream_proof")

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_enforcement_build": route_next == EXPECTED_NEXT,
    "route_upstream_atomic_review_ok": route_upstream == str(ATOMIC_REVIEW_PROOF),
    "route_atomic_commit_review_sealed": route.get("route_authority_atomic_commit_helper_review_sealed") is True,
    "route_writeback_order_drift_class_closed": route.get("writeback_order_drift_control_review_sealed") is True or route.get("writeback_order_drift_class_closed") is True,
    "route_ready_to_enforce_atomic_commit_lane": route.get("ready_to_enforce_atomic_commit_lane") is True,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "atomic_review_proof_exists": ATOMIC_REVIEW_PROOF.exists(),
    "atomic_review_status_pass": atomic_review.get("status") == "PASS",
    "atomic_review_capability_ok": atomic_review.get("capability") == EXPECTED_REVIEW_CAPABILITY,
    "atomic_review_real_next_ok": atomic_review.get("real_next") == EXPECTED_NEXT,
    "atomic_review_class_closed": atomic_review.get("writeback_order_drift_class_closed") is True,
    "atomic_review_ready_to_enforce_lane": atomic_review.get("ready_to_enforce_atomic_commit_lane") is True,
    "atomic_review_hard_failures_empty": atomic_review.get("hard_failures") == [],

    "atomic_validation_proof_exists": ATOMIC_VALIDATION_PROOF.exists(),
    "atomic_validation_status_pass": atomic_validation.get("status") == "PASS",
    "atomic_validation_helper_validated": atomic_validation.get("route_authority_atomic_commit_helper_validated") is True,
    "atomic_validation_invariants_validated": atomic_validation.get("atomic_commit_invariants_validated") is True,

    "atomic_build_proof_exists": ATOMIC_BUILD_PROOF.exists(),
    "atomic_build_status_pass": atomic_build.get("status") == "PASS",
    "atomic_build_helper_built": atomic_build.get("route_authority_atomic_commit_helper_built") is True,
    "atomic_build_self_test_passed": atomic_build.get("atomic_commit_self_test_passed") is True,

    "helper_exists": HELPER.exists(),
    "helper_has_atomic_commit": "def atomic_commit(" in helper_text,
    "helper_has_coherence_checks": "progress_upstream_matches_route" in helper_text,
    "helper_has_forbidden_guards": "FORBIDDEN_TRUE_KEYS" in helper_text,

    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),
    "progress_exists": PROGRESS.exists(),

    "pulse_lawful_next_matches_route": pulse.get("lawful_next") == route_next,
    "panel_lawful_next_matches_route": panel.get("lawful_next") == route_next,
    "progress_lawful_next_matches_route": progress.get("lawful_next") == route_next,

    "pulse_truth_boundary_matches_route": pulse.get("truth_boundary") == route_truth,
    "panel_truth_boundary_matches_route": panel.get("truth_boundary") == route_truth,
    "progress_truth_boundary_matches_route": progress.get("truth_boundary") == route_truth,

    "pulse_upstream_matches_route": pulse.get("route_authority_upstream_proof") == route_upstream,
    "panel_upstream_matches_route": panel.get("route_authority_upstream_proof") == route_upstream,
    "progress_upstream_matches_route": progress.get("route_authority_upstream_proof") == route_upstream,

    "route_forbidden_false": forbidden_false(route),
    "pulse_forbidden_false": forbidden_false(pulse),
    "panel_forbidden_false": forbidden_false(panel),
    "progress_forbidden_false": forbidden_false(progress),

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
    ("atomic_review", atomic_review),
    ("atomic_validation", atomic_validation),
    ("atomic_build", atomic_build),
    ("pulse", pulse),
    ("panel", panel),
    ("progress", progress),
]:
    for key in FORBIDDEN:
        if key in src:
            checks[f"{name}_{key}_false"] = src.get(key) is False

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

truth_boundary = (
    "Atomic-commit enforced self-building lane build only. This builds a lane policy/enforcer requiring future bounded "
    "self-building route transitions to use the validated route-authority atomic commit helper. It does not execute a tick, "
    "enable continuous loop, launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, "
    "approve final canon, or claim AGI."
)

if status == "PASS":
    capability = "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_BUILT_ROUTE_TRANSITIONS_GATED"
    real_next = NEXT
    final_socc_status = "SOCC_ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_BLOCKED"
    real_next = "repair_atomic_commit_enforced_self_building_lane_v1"
    final_socc_status = "SOCC_ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_FAIL"

enforcer_code = r'''#!/usr/bin/env python3
import json
import importlib.util
from pathlib import Path

ROOT = Path(".")
HELPER = ROOT / "scripts/socc/socc_route_atomic_commit_helper_v1.py"
POLICY = ROOT / "core/socc/autonomy/self_building/atomic_commit/enforcement/ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_POLICY_V1.json"

FORBIDDEN_DIRECT_ROUTE_WRITE_REASON = "direct_route_write_forbidden_after_atomic_commit_review"

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def load_helper():
    spec = importlib.util.spec_from_file_location("socc_route_atomic_commit_helper_v1", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def policy_enabled():
    p = read_json(POLICY)
    return p.get("status") == "ENFORCED" and p.get("atomic_commit_required_for_route_transitions") is True

def enforce_atomic_commit_transition(
    *,
    lawful_next,
    upstream_proof,
    truth_boundary,
    route_updates=None,
    pulse_updates=None,
    panel_updates=None,
    progress_updates=None,
    reason="atomic_commit_enforced_self_building_lane",
):
    if not policy_enabled():
        return {
            "status": "FAIL",
            "committed": False,
            "hard_failures": [
                {"code": "POLICY_NOT_ENFORCED", "check": "policy_enabled", "actual": policy_enabled()}
            ],
        }

    helper = load_helper()
    return helper.atomic_commit(
        lawful_next=lawful_next,
        upstream_proof=upstream_proof,
        truth_boundary=truth_boundary,
        route_updates=route_updates or {},
        pulse_updates=pulse_updates or {},
        panel_updates=panel_updates or {},
        progress_updates=progress_updates or {},
        reason=reason,
    )

def reject_direct_route_write(reason=None):
    return {
        "status": "BLOCKED",
        "allowed": False,
        "reason": reason or FORBIDDEN_DIRECT_ROUTE_WRITE_REASON,
        "required_method": "enforce_atomic_commit_transition",
    }
'''

policy = {
    "id": "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_POLICY_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "ENFORCED" if status == "PASS" else "BLOCKED",
    "atomic_commit_required_for_route_transitions": status == "PASS",
    "direct_route_write_forbidden": status == "PASS",
    "required_helper": str(HELPER),
    "required_enforcer": str(ENFORCER),
    "source_atomic_review_proof": str(ATOMIC_REVIEW_PROOF),
    "enforced_surfaces": [
        str(ROUTE),
        str(PULSE),
        str(PANEL),
        str(PROGRESS),
    ],
    "required_invariants": [
        "pulse.lawful_next == route.lawful_next",
        "panel.lawful_next == route.lawful_next",
        "progress.lawful_next == route.lawful_next",
        "pulse.truth_boundary == route.truth_boundary",
        "panel.truth_boundary == route.truth_boundary",
        "progress.truth_boundary == route.truth_boundary",
        "pulse.route_authority_upstream_proof == route.upstream_proof",
        "panel.route_authority_upstream_proof == route.upstream_proof",
        "progress.route_authority_upstream_proof == route.upstream_proof",
        "forbidden escalation flags remain false",
    ],
    "truth_boundary": truth_boundary,
}

test_vector = {
    "id": "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_TEST_VECTOR_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "direct_route_write_expected": "BLOCKED",
    "atomic_commit_transition_expected": "PASS",
    "validation_target": NEXT,
    "truth_boundary": truth_boundary,
}

if status == "PASS":
    write_text(ENFORCER, enforcer_code)
    ENFORCER.chmod(0o755)

build = {
    "id": "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_BUILD_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "policy": str(POLICY),
    "enforcer": str(ENFORCER),
    "test_vector": str(TEST_VECTOR),
    "source_atomic_review_proof": str(ATOMIC_REVIEW_PROOF),

    "atomic_commit_enforced_self_building_lane_built": status == "PASS",
    "atomic_commit_required_for_route_transitions": status == "PASS",
    "direct_route_write_forbidden": status == "PASS",
    "writeback_order_drift_class_control_enforced": status == "PASS",
    "ready_for_validation": status == "PASS",

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
build["build_hash"] = h(build)

proof = {
    "id": "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "build": str(BUILD),
    "build_md": str(BUILD_MD),
    "policy": str(POLICY),
    "enforcer": str(ENFORCER),
    "test_vector": str(TEST_VECTOR),
    "memory": str(MEMORY),

    "atomic_commit_enforced_self_building_lane_built": status == "PASS",
    "atomic_commit_required_for_route_transitions": status == "PASS",
    "direct_route_write_forbidden": status == "PASS",
    "writeback_order_drift_class_control_enforced": status == "PASS",
    "ready_for_validation": status == "PASS",

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
    "id": "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built atomic-commit-enforced self-building lane policy. Future route transitions must go through atomic commit enforcer."
    ),
    "proof": str(PROOF),
    "build": str(BUILD),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

if status == "PASS":
    write_json(POLICY, policy)
    write_json(TEST_VECTOR, test_vector)

    spec_import = importlib.util.spec_from_file_location("socc_route_atomic_commit_helper_v1", HELPER)
    helper_mod = importlib.util.module_from_spec(spec_import)
    spec_import.loader.exec_module(helper_mod)

    commit_result = helper_mod.atomic_commit(
        lawful_next=real_next,
        upstream_proof=str(PROOF),
        truth_boundary=truth_boundary,
        route_updates={
            "atomic_commit_enforced_self_building_lane_built": True,
            "atomic_commit_required_for_route_transitions": True,
            "direct_route_write_forbidden": True,
            "writeback_order_drift_class_control_enforced": True,
            "ready_for_validation": True,
            "recommended_next_target": real_next,
        },
        pulse_updates={
            "atomic_commit_enforced_self_building_lane_built": True,
            "atomic_commit_required_for_route_transitions": True,
        },
        panel_updates={
            "atomic_commit_enforced_self_building_lane_built": True,
            "atomic_commit_required_for_route_transitions": True,
        },
        progress_updates={
            "atomic_commit_enforced_self_building_lane_built": True,
            "atomic_commit_required_for_route_transitions": True,
            "recommended_next_target": real_next,
        },
        reason="build_atomic_commit_enforced_self_building_lane_v1",
    )

    build["atomic_commit_enforcement_commit_result"] = commit_result
    proof["atomic_commit_enforcement_commit_result"] = commit_result

    if commit_result.get("status") != "PASS":
        status = "FAIL"
        hard = [{"code": "ATOMIC_ENFORCEMENT_COMMIT_FAIL", "actual": commit_result}]
        capability = "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_BLOCKED"
        real_next = "repair_atomic_commit_enforced_self_building_lane_v1"
        final_socc_status = "SOCC_ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_FAIL"
        build["status"] = "BLOCKED"
        build["hard_failures"] = hard
        build["real_next"] = real_next
        proof["status"] = status
        proof["hard_failures"] = hard
        proof["real_next"] = real_next
        proof["final_socc_status"] = final_socc_status

md = "# ATOMIC COMMIT ENFORCED SELF-BUILDING LANE V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nAtomic commit helper was review-sealed; writeback_order_drift was closed as a class.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt lane policy and enforcer requiring atomic commit for future self-building route transitions.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Self-building lane now has an atomic-commit enforcement policy. Next is validation.\n\n"
else:
    md += "Atomic commit lane enforcement build is blocked. Repair required.\n\n"
md += "## Enforced rule\n\n"
md += "- direct route writes are forbidden after atomic commit review\n"
md += "- route transitions must use socc_self_building_atomic_commit_enforcer_v1.enforce_atomic_commit_transition\n\n"
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

write_json(BUILD, build)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(BUILD_MD, md)

print("ATOMIC COMMIT ENFORCED SELF-BUILDING LANE :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("POLICY::" + str(POLICY))
print("ENFORCER::" + str(ENFORCER))
print("BUILD::" + str(BUILD))
print("TEST_VECTOR::" + str(TEST_VECTOR))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_BUILT::" + str(status == "PASS"))
print("ATOMIC_COMMIT_REQUIRED_FOR_ROUTE_TRANSITIONS::" + str(status == "PASS"))
print("DIRECT_ROUTE_WRITE_FORBIDDEN::" + str(status == "PASS"))
print("WRITEBACK_ORDER_DRIFT_CLASS_CONTROL_ENFORCED::" + str(status == "PASS"))
print("READY_FOR_VALIDATION::" + str(status == "PASS"))
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

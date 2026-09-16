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

ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"
EFFECT_LANE = ROOT / "scripts/socc/socc_self_building_effect_auditor_enforced_lane_v1.py"

CYCLE_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_REVIEW_V1_PROOF.json"
LANE_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_V1_PROOF.json"

OUT = ROOT / "core/socc/autonomy/self_building/idempotent_step_guard"
GUARD = ROOT / "scripts/socc/socc_idempotent_step_guard_v1.py"
SPEC = OUT / "IDEMPOTENT_STEP_GUARD_SPEC_V1.json"
BUILD = OUT / "IDEMPOTENT_STEP_GUARD_BUILD_V1.json"
BUILD_MD = OUT / "IDEMPOTENT_STEP_GUARD_BUILD_V1.md"
TEST_VECTOR = OUT / "IDEMPOTENT_STEP_GUARD_TEST_VECTOR_V1.json"
REPLAY = OUT / "IDEMPOTENT_STEP_GUARD_BUILD_REPLAY_V1.json"
EFFECT_AUDIT = OUT / "IDEMPOTENT_STEP_GUARD_BUILD_EFFECT_AUDIT_V1.json"
COMMIT_RESULT = OUT / "IDEMPOTENT_STEP_GUARD_BUILD_COMMIT_RESULT_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_STEP_GUARD_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/IDEMPOTENT_STEP_GUARD_V1_MEMORY.json"

EXPECTED_NEXT = "build_idempotent_step_guard_v1"
NEXT = "validate_idempotent_step_guard_v1"

FORBIDDEN_FLAGS = [
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

def import_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def forbidden_false(obj):
    return all(obj.get(k) is False for k in FORBIDDEN_FLAGS if k in obj)

route_before = read_json(ROUTE)
pulse = read_json(PULSE)
panel = read_json(PANEL)
progress = read_json(PROGRESS)

cycle_review = read_json(CYCLE_REVIEW_PROOF)
lane_review = read_json(LANE_REVIEW_PROOF)

enforcer_text = read_text(ENFORCER)
effect_lane_text = read_text(EFFECT_LANE)

route_next = route_before.get("lawful_next") or route_before.get("real_next")
route_truth = route_before.get("truth_boundary")
route_upstream = route_before.get("upstream_proof")

checks = {
    "route_exists": ROUTE.exists(),
    "route_status_pass": route_before.get("status") == "PASS",
    "route_points_to_idempotent_guard_build": route_next == EXPECTED_NEXT,
    "route_upstream_cycle_review": route_upstream == str(CYCLE_REVIEW_PROOF),
    "route_ready_to_build_idempotent_step_guard": route_before.get("ready_to_build_idempotent_step_guard") is True,
    "route_idempotent_guard_next_review_sealed": route_before.get("idempotent_step_guard_next_review_sealed") is True,
    "route_selected_target_review_sealed": route_before.get("selected_next_target_review_sealed") == EXPECTED_NEXT,
    "route_self_building_mode_enabled": route_before.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route_before.get("visible_bounded_mode_ready") is True,

    "cycle_review_proof_exists": CYCLE_REVIEW_PROOF.exists(),
    "cycle_review_status_pass": cycle_review.get("status") == "PASS",
    "cycle_review_real_next_ok": cycle_review.get("real_next") == EXPECTED_NEXT,
    "cycle_review_ready_to_build_guard": cycle_review.get("ready_to_build_idempotent_step_guard") is True,
    "cycle_review_hard_failures_empty": cycle_review.get("hard_failures") == [],

    "lane_review_proof_exists": LANE_REVIEW_PROOF.exists(),
    "lane_review_status_pass": lane_review.get("status") == "PASS",
    "lane_law_active": lane_review.get("effect_auditor_lane_law_review_sealed") is True,
    "lane_future_pass_requires_material_effect": lane_review.get("future_bounded_pass_requires_material_effect") is True,
    "lane_semantic_null_rejected": lane_review.get("semantic_null_pass_rejected_by_lane_law") is True,

    "enforcer_exists": ENFORCER.exists(),
    "enforcer_has_enforce_transition": "def enforce_atomic_commit_transition(" in enforcer_text,
    "effect_lane_exists": EFFECT_LANE.exists(),
    "effect_lane_has_enforce_function": "def enforce_effect_auditor_lane(" in effect_lane_text,

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

    "route_forbidden_false": forbidden_false(route_before),
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

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]

truth_boundary = (
    "Idempotent step guard build only. This builds a bounded guard that detects already-committed or out-of-phase reruns and prevents destructive "
    "proof overwrite. It returns ALREADY_COMMITTED_NOOP for safe reruns and blocks backward reruns that would corrupt proof state. It does not execute "
    "a tick, enable continuous loop, launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

guard_code = r'''#!/usr/bin/env python3
from pathlib import Path
import json

def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}

def route_next(route):
    return route.get("lawful_next") or route.get("real_next")

def guard_step_execution(
    *,
    step_name,
    expected_current_next,
    success_next,
    proof_path,
    route,
    existing_proof=None,
    allow_recovery=False,
):
    """
    Idempotent guard for SOCC bounded construction steps.

    Cases:
    1. NORMAL_EXECUTION_ALLOWED:
       route.lawful_next == expected_current_next

    2. ALREADY_COMMITTED_NOOP:
       route.lawful_next == success_next
       route.upstream_proof == proof_path
       existing proof is PASS or allow_recovery=True

    3. OUT_OF_PHASE_RERUN_BLOCKED:
       route has advanced beyond expected_current_next, but proof/upstream does not match safe already-committed state.

    This prevents rerunning stale validation/build/review scripts from rewriting valid artifacts to FAIL after route has already advanced.
    """
    current_next = route_next(route)
    upstream = route.get("upstream_proof")
    existing = existing_proof or {}

    if current_next == expected_current_next:
        return {
            "status": "PASS",
            "decision": "NORMAL_EXECUTION_ALLOWED",
            "step_name": step_name,
            "current_next": current_next,
            "expected_current_next": expected_current_next,
            "success_next": success_next,
            "proof_path": proof_path,
            "hard_failures": [],
        }

    proof_ok = existing.get("status") == "PASS" or allow_recovery is True

    if current_next == success_next and upstream == proof_path and proof_ok:
        return {
            "status": "PASS",
            "decision": "ALREADY_COMMITTED_NOOP",
            "step_name": step_name,
            "current_next": current_next,
            "expected_current_next": expected_current_next,
            "success_next": success_next,
            "proof_path": proof_path,
            "already_committed": True,
            "write_allowed": False,
            "hard_failures": [],
        }

    return {
        "status": "FAIL",
        "decision": "OUT_OF_PHASE_RERUN_BLOCKED",
        "step_name": step_name,
        "current_next": current_next,
        "expected_current_next": expected_current_next,
        "success_next": success_next,
        "route_upstream_proof": upstream,
        "expected_proof_path": proof_path,
        "write_allowed": False,
        "hard_failures": [
            {
                "code": "OUT_OF_PHASE_RERUN_BLOCKED",
                "current_next": current_next,
                "expected_current_next": expected_current_next,
                "success_next": success_next,
                "route_upstream_proof": upstream,
                "expected_proof_path": proof_path,
            }
        ],
    }
'''

status = "PASS" if not hard else "FAIL"
capability = "IDEMPOTENT_STEP_GUARD_BUILT_OUT_OF_PHASE_RERUN_CONTROL" if status == "PASS" else "IDEMPOTENT_STEP_GUARD_BUILD_BLOCKED"
real_next = NEXT if status == "PASS" else "repair_idempotent_step_guard_v1"
final_socc_status = "SOCC_IDEMPOTENT_STEP_GUARD_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI" if status == "PASS" else "SOCC_IDEMPOTENT_STEP_GUARD_FAIL"

replay = {}
effect_audit = {}
commit = {}

if status == "PASS":
    write_text(GUARD, guard_code)
    GUARD.chmod(0o755)

    spec = {
        "id": "IDEMPOTENT_STEP_GUARD_SPEC_V1",
        "created_at_utc": now_utc(),
        "created_at_msk": now_msk(),
        "status": "BUILT",
        "purpose": "Prevent destructive reruns from overwriting valid committed proof artifacts with FAIL after route has advanced.",
        "decisions": [
            "NORMAL_EXECUTION_ALLOWED",
            "ALREADY_COMMITTED_NOOP",
            "OUT_OF_PHASE_RERUN_BLOCKED",
        ],
        "truth_boundary": truth_boundary,
    }
    write_json(SPEC, spec)

    test_vector = {
        "id": "IDEMPOTENT_STEP_GUARD_TEST_VECTOR_V1",
        "created_at_utc": now_utc(),
        "created_at_msk": now_msk(),
        "status": "BUILT",
        "normal_case": {
            "route": {"lawful_next": "validate_x", "upstream_proof": "build_x_proof.json"},
            "expected_current_next": "validate_x",
            "success_next": "review_x",
            "proof_path": "validation_x_proof.json",
        },
        "already_committed_case": {
            "route": {"lawful_next": "review_x", "upstream_proof": "validation_x_proof.json"},
            "existing_proof": {"status": "PASS"},
            "expected_current_next": "validate_x",
            "success_next": "review_x",
            "proof_path": "validation_x_proof.json",
        },
        "out_of_phase_block_case": {
            "route": {"lawful_next": "review_x", "upstream_proof": "other_proof.json"},
            "existing_proof": {"status": "FAIL"},
            "expected_current_next": "validate_x",
            "success_next": "review_x",
            "proof_path": "validation_x_proof.json",
        },
    }
    write_json(TEST_VECTOR, test_vector)

    guard = import_module(GUARD, "idempotent_step_guard")

    normal = guard.guard_step_execution(
        step_name="validate_x",
        expected_current_next="validate_x",
        success_next="review_x",
        proof_path="validation_x_proof.json",
        route=test_vector["normal_case"]["route"],
        existing_proof={},
    )

    already = guard.guard_step_execution(
        step_name="validate_x",
        expected_current_next="validate_x",
        success_next="review_x",
        proof_path="validation_x_proof.json",
        route=test_vector["already_committed_case"]["route"],
        existing_proof=test_vector["already_committed_case"]["existing_proof"],
    )

    blocked = guard.guard_step_execution(
        step_name="validate_x",
        expected_current_next="validate_x",
        success_next="review_x",
        proof_path="validation_x_proof.json",
        route=test_vector["out_of_phase_block_case"]["route"],
        existing_proof=test_vector["out_of_phase_block_case"]["existing_proof"],
    )

    replay = {
        "id": "IDEMPOTENT_STEP_GUARD_BUILD_REPLAY_V1",
        "created_at_utc": now_utc(),
        "created_at_msk": now_msk(),
        "status": "PASS" if (
            normal.get("decision") == "NORMAL_EXECUTION_ALLOWED"
            and already.get("decision") == "ALREADY_COMMITTED_NOOP"
            and blocked.get("decision") == "OUT_OF_PHASE_RERUN_BLOCKED"
            and normal.get("status") == "PASS"
            and already.get("status") == "PASS"
            and blocked.get("status") == "FAIL"
        ) else "FAIL",
        "normal_case": normal,
        "already_committed_case": already,
        "out_of_phase_block_case": blocked,
    }
    write_json(REPLAY, replay)

    if replay["status"] != "PASS":
        status = "FAIL"
        hard = [{"code": "IDEMPOTENT_GUARD_REPLAY_FAIL", "actual": replay}]
        capability = "IDEMPOTENT_STEP_GUARD_BUILD_BLOCKED"
        real_next = "repair_idempotent_step_guard_v1"
        final_socc_status = "SOCC_IDEMPOTENT_STEP_GUARD_FAIL"

if status == "PASS":
    lane = import_module(EFFECT_LANE, "effect_lane")
    effect_audit = lane.enforce_effect_auditor_lane(
        {"route_before": route_before},
        {
            "route_after": {
                **route_before,
                "lawful_next": real_next,
                "real_next": real_next,
                "upstream_proof": str(PROOF),
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
            },
            "expected_lawful_next_before": EXPECTED_NEXT,
            "expected_lawful_next_after": real_next,
            "expected_upstream_proof_after": str(PROOF),
            "expected_memory": str(CYCLE_REVIEW_PROOF),
            "required_artifacts": [str(GUARD), str(SPEC), str(TEST_VECTOR), str(REPLAY), str(CYCLE_REVIEW_PROOF)],
            "changed_artifacts": [str(GUARD), str(SPEC), str(TEST_VECTOR), str(REPLAY)],
            "material_claims": [
                "idempotent step guard script created",
                "idempotent guard spec created",
                "normal execution allowed case proven",
                "already committed noop case proven",
                "out-of-phase rerun blocked case proven",
                "route transition prepared under effect-auditor lane law",
            ],
        }
    )
    write_json(EFFECT_AUDIT, effect_audit)

    if effect_audit.get("status") != "PASS":
        status = "FAIL"
        hard = [{"code": "EFFECT_AUDIT_FAIL", "actual": effect_audit}]
        capability = "IDEMPOTENT_STEP_GUARD_BUILD_BLOCKED"
        real_next = "repair_idempotent_step_guard_v1"
        final_socc_status = "SOCC_IDEMPOTENT_STEP_GUARD_FAIL"

build = {
    "id": "IDEMPOTENT_STEP_GUARD_BUILD_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "guard": str(GUARD),
    "spec": str(SPEC),
    "test_vector": str(TEST_VECTOR),
    "replay": str(REPLAY),
    "effect_audit": str(EFFECT_AUDIT),
    "source_cycle_review_proof": str(CYCLE_REVIEW_PROOF),

    "idempotent_step_guard_built": status == "PASS",
    "normal_execution_allowed_case_passed": replay.get("normal_case", {}).get("decision") == "NORMAL_EXECUTION_ALLOWED" if status == "PASS" else False,
    "already_committed_noop_case_passed": replay.get("already_committed_case", {}).get("decision") == "ALREADY_COMMITTED_NOOP" if status == "PASS" else False,
    "out_of_phase_rerun_blocked_case_passed": replay.get("out_of_phase_block_case", {}).get("decision") == "OUT_OF_PHASE_RERUN_BLOCKED" if status == "PASS" else False,
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
    "id": "IDEMPOTENT_STEP_GUARD_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "build": str(BUILD),
    "build_md": str(BUILD_MD),
    "guard": str(GUARD),
    "spec": str(SPEC),
    "test_vector": str(TEST_VECTOR),
    "replay": str(REPLAY),
    "effect_audit": str(EFFECT_AUDIT),
    "memory": str(MEMORY),

    "idempotent_step_guard_built": status == "PASS",
    "normal_execution_allowed_case_passed": replay.get("normal_case", {}).get("decision") == "NORMAL_EXECUTION_ALLOWED" if status == "PASS" else False,
    "already_committed_noop_case_passed": replay.get("already_committed_case", {}).get("decision") == "ALREADY_COMMITTED_NOOP" if status == "PASS" else False,
    "out_of_phase_rerun_blocked_case_passed": replay.get("out_of_phase_block_case", {}).get("decision") == "OUT_OF_PHASE_RERUN_BLOCKED" if status == "PASS" else False,
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
    "id": "IDEMPOTENT_STEP_GUARD_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": "Built idempotent step guard to prevent out-of-phase reruns from corrupting already committed proof state.",
    "proof": str(PROOF),
    "build": str(BUILD),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

if status == "PASS":
    enforcer = import_module(ENFORCER, "enforcer")
    commit = enforcer.enforce_atomic_commit_transition(
        lawful_next=real_next,
        upstream_proof=str(PROOF),
        truth_boundary=truth_boundary,
        route_updates={
            "idempotent_step_guard_built": True,
            "normal_execution_allowed_case_passed": True,
            "already_committed_noop_case_passed": True,
            "out_of_phase_rerun_blocked_case_passed": True,
            "ready_for_validation": True,
            "recommended_next_target": real_next,
        },
        pulse_updates={
            "idempotent_step_guard_built": True,
            "already_committed_noop_case_passed": True,
        },
        panel_updates={
            "idempotent_step_guard_built": True,
            "already_committed_noop_case_passed": True,
        },
        progress_updates={
            "idempotent_step_guard_built": True,
            "already_committed_noop_case_passed": True,
            "recommended_next_target": real_next,
        },
        reason="build_idempotent_step_guard_v1",
    )
    write_json(COMMIT_RESULT, commit)
    build["atomic_commit_result"] = commit
    proof["atomic_commit_result"] = commit
    if commit.get("status") != "PASS":
        status = "FAIL"
        hard = [{"code": "ATOMIC_COMMIT_FAIL", "actual": commit}]
        build["status"] = "BLOCKED"
        build["hard_failures"] = hard
        build["real_next"] = "repair_idempotent_step_guard_v1"
        proof["status"] = "FAIL"
        proof["hard_failures"] = hard
        proof["real_next"] = "repair_idempotent_step_guard_v1"

write_json(BUILD, build)
write_json(PROOF, proof)
write_json(MEMORY, memory)

md = "# IDEMPOTENT STEP GUARD V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nNext cycle review selected build_idempotent_step_guard_v1 after out-of-phase rerun corrupted validation artifacts.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt idempotent guard that distinguishes normal execution, already committed noop, and out-of-phase destructive rerun.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Idempotent step guard is built. Next is validation.\n\n"
else:
    md += "Idempotent step guard build is blocked. Repair required.\n\n"
md += "## Guard decisions\n\n"
md += "- NORMAL_EXECUTION_ALLOWED\n"
md += "- ALREADY_COMMITTED_NOOP\n"
md += "- OUT_OF_PHASE_RERUN_BLOCKED\n\n"
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
md += "\n## lawful_next\n\n" + proof.get("real_next", real_next) + "\n\n"
md += "## Truth boundary\n\n" + truth_boundary + "\n"
write_text(BUILD_MD, md)

print("IDEMPOTENT STEP GUARD :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("GUARD::" + str(GUARD))
print("SPEC::" + str(SPEC))
print("TEST_VECTOR::" + str(TEST_VECTOR))
print("REPLAY::" + str(REPLAY))
print("EFFECT_AUDIT::" + str(EFFECT_AUDIT))
print("COMMIT_RESULT::" + str(COMMIT_RESULT))
print("BUILD::" + str(BUILD))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("IDEMPOTENT_STEP_GUARD_BUILT::" + str(status == "PASS"))
print("NORMAL_EXECUTION_ALLOWED_CASE_PASSED::" + str(replay.get("normal_case", {}).get("decision") == "NORMAL_EXECUTION_ALLOWED" if status == "PASS" else False))
print("ALREADY_COMMITTED_NOOP_CASE_PASSED::" + str(replay.get("already_committed_case", {}).get("decision") == "ALREADY_COMMITTED_NOOP" if status == "PASS" else False))
print("OUT_OF_PHASE_RERUN_BLOCKED_CASE_PASSED::" + str(replay.get("out_of_phase_block_case", {}).get("decision") == "OUT_OF_PHASE_RERUN_BLOCKED" if status == "PASS" else False))
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
print("REAL_NEXT::" + proof.get("real_next", real_next))
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if status == "PASS" else 1)

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
GUARD = ROOT / "scripts/socc/socc_idempotent_step_guard_v1.py"

GUARD_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_STEP_GUARD_REVIEW_V1_PROOF.json"
GUARD_VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_STEP_GUARD_VALIDATION_V1_PROOF.json"

OUT = ROOT / "core/socc/autonomy/self_building/idempotent_guard_enforced_step_wrapper"
WRAPPER = ROOT / "scripts/socc/socc_idempotent_guard_enforced_step_wrapper_v1.py"
SPEC = OUT / "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_SPEC_V1.json"
BUILD = OUT / "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_BUILD_V1.json"
BUILD_MD = OUT / "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_BUILD_V1.md"
REPLAY = OUT / "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REPLAY_V1.json"
EFFECT_AUDIT = OUT / "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_EFFECT_AUDIT_V1.json"
COMMIT_RESULT = OUT / "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_COMMIT_RESULT_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_V1_MEMORY.json"

EXPECTED_NEXT = "build_idempotent_guard_enforced_step_wrapper_v1"
NEXT = "validate_idempotent_guard_enforced_step_wrapper_v1"

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

guard_review = read_json(GUARD_REVIEW_PROOF)
guard_validation = read_json(GUARD_VALIDATION_PROOF)

guard_text = read_text(GUARD)
enforcer_text = read_text(ENFORCER)
effect_lane_text = read_text(EFFECT_LANE)

route_next = route_before.get("lawful_next") or route_before.get("real_next")
route_truth = route_before.get("truth_boundary")
route_upstream = route_before.get("upstream_proof")

checks = {
    "route_exists": ROUTE.exists(),
    "route_status_pass": route_before.get("status") == "PASS",
    "route_points_to_wrapper_build": route_next == EXPECTED_NEXT,
    "route_upstream_guard_review": route_upstream == str(GUARD_REVIEW_PROOF),
    "route_guard_review_sealed": route_before.get("idempotent_step_guard_review_sealed") is True,
    "route_already_committed_noop_review_sealed": route_before.get("already_committed_noop_review_sealed") is True,
    "route_out_of_phase_blocked_review_sealed": route_before.get("out_of_phase_rerun_blocked_review_sealed") is True,
    "route_recovery_explicit_only_review_sealed": route_before.get("recovery_allowed_explicit_only_review_sealed") is True,
    "route_ready_to_build_wrapper": route_before.get("ready_to_build_idempotent_guard_enforced_step_wrapper") is True,
    "route_self_building_mode_enabled": route_before.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route_before.get("visible_bounded_mode_ready") is True,

    "guard_review_proof_exists": GUARD_REVIEW_PROOF.exists(),
    "guard_review_status_pass": guard_review.get("status") == "PASS",
    "guard_review_real_next_ok": guard_review.get("real_next") == EXPECTED_NEXT,
    "guard_review_sealed": guard_review.get("idempotent_step_guard_review_sealed") is True,
    "guard_review_ready_to_build_wrapper": guard_review.get("ready_to_build_idempotent_guard_enforced_step_wrapper") is True,
    "guard_review_hard_failures_empty": guard_review.get("hard_failures") == [],

    "guard_validation_proof_exists": GUARD_VALIDATION_PROOF.exists(),
    "guard_validation_status_pass": guard_validation.get("status") == "PASS",
    "guard_validation_guard_validated": guard_validation.get("idempotent_step_guard_validated") is True,

    "guard_script_exists": GUARD.exists(),
    "guard_has_function": "def guard_step_execution(" in guard_text,
    "guard_has_noop_decision": "ALREADY_COMMITTED_NOOP" in guard_text,
    "guard_has_block_decision": "OUT_OF_PHASE_RERUN_BLOCKED" in guard_text,

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
    "Idempotent guard enforced step wrapper build only. This builds a bounded wrapper that applies the review-sealed idempotent guard before future "
    "bounded steps write proof/report/memory artifacts. It supports normal execution, already-committed noop, and out-of-phase rerun block. It does not "
    "execute a tick, enable continuous loop, launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

wrapper_code = r'''#!/usr/bin/env python3
import json
import importlib.util
from pathlib import Path

ROOT = Path(".")
GUARD = ROOT / "scripts/socc/socc_idempotent_step_guard_v1.py"

def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}

def import_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def enforce_step_before_writes(
    *,
    step_name,
    expected_current_next,
    success_next,
    proof_path,
    route_path="core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json",
    existing_proof_path=None,
    allow_recovery=False,
):
    """
    Enforced wrapper around the idempotent guard.

    This function must run before any bounded construction step writes
    proof/report/memory artifacts.

    Returns:
    - NORMAL_EXECUTION_ALLOWED -> caller may write artifacts
    - ALREADY_COMMITTED_NOOP -> caller must not rewrite artifacts; return safe noop
    - OUT_OF_PHASE_RERUN_BLOCKED -> caller must fail before writes
    """
    route = read_json(route_path)
    existing_proof = read_json(existing_proof_path) if existing_proof_path else {}

    guard = import_module(GUARD, "idempotent_step_guard")
    decision = guard.guard_step_execution(
        step_name=step_name,
        expected_current_next=expected_current_next,
        success_next=success_next,
        proof_path=proof_path,
        route=route,
        existing_proof=existing_proof,
        allow_recovery=allow_recovery,
    )

    decision["wrapper_enforced"] = True
    decision["writes_allowed"] = decision.get("decision") == "NORMAL_EXECUTION_ALLOWED"
    decision["noop_required"] = decision.get("decision") == "ALREADY_COMMITTED_NOOP"
    decision["blocked_before_writes"] = decision.get("decision") == "OUT_OF_PHASE_RERUN_BLOCKED"
    return decision
'''

status = "PASS" if not hard else "FAIL"
capability = "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_BUILT_BEFORE_PROOF_WRITES" if status == "PASS" else "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_BUILD_BLOCKED"
real_next = NEXT if status == "PASS" else "repair_idempotent_guard_enforced_step_wrapper_v1"
final_socc_status = "SOCC_IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI" if status == "PASS" else "SOCC_IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_FAIL"

replay = {}
effect_audit = {}
commit = {}

if status == "PASS":
    write_text(WRAPPER, wrapper_code)
    WRAPPER.chmod(0o755)

    spec = {
        "id": "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_SPEC_V1",
        "created_at_utc": now_utc(),
        "created_at_msk": now_msk(),
        "status": "BUILT",
        "purpose": "Apply idempotent step guard before future bounded step artifact writes.",
        "decisions": [
            "NORMAL_EXECUTION_ALLOWED -> writes_allowed=True",
            "ALREADY_COMMITTED_NOOP -> noop_required=True and writes_allowed=False",
            "OUT_OF_PHASE_RERUN_BLOCKED -> blocked_before_writes=True and writes_allowed=False",
        ],
        "truth_boundary": truth_boundary,
    }
    write_json(SPEC, spec)

    tmp = OUT / "wrapper_replay_tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    normal_route = tmp / "normal_route.json"
    normal_proof = tmp / "normal_proof.json"
    already_route = tmp / "already_route.json"
    already_proof = tmp / "already_proof.json"
    blocked_route = tmp / "blocked_route.json"
    blocked_proof = tmp / "blocked_proof.json"

    write_json(normal_route, {"lawful_next": "validate_demo", "upstream_proof": "build_demo_proof.json"})
    write_json(normal_proof, {})
    write_json(already_route, {"lawful_next": "review_demo", "upstream_proof": "demo_validation_proof.json"})
    write_json(already_proof, {"status": "PASS"})
    write_json(blocked_route, {"lawful_next": "review_demo", "upstream_proof": "other_proof.json"})
    write_json(blocked_proof, {"status": "FAIL"})

    wrapper = import_module(WRAPPER, "wrapper")
    normal = wrapper.enforce_step_before_writes(
        step_name="validate_demo",
        expected_current_next="validate_demo",
        success_next="review_demo",
        proof_path="demo_validation_proof.json",
        route_path=str(normal_route),
        existing_proof_path=str(normal_proof),
    )
    already = wrapper.enforce_step_before_writes(
        step_name="validate_demo",
        expected_current_next="validate_demo",
        success_next="review_demo",
        proof_path="demo_validation_proof.json",
        route_path=str(already_route),
        existing_proof_path=str(already_proof),
    )
    blocked = wrapper.enforce_step_before_writes(
        step_name="validate_demo",
        expected_current_next="validate_demo",
        success_next="review_demo",
        proof_path="demo_validation_proof.json",
        route_path=str(blocked_route),
        existing_proof_path=str(blocked_proof),
    )

    replay = {
        "id": "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REPLAY_V1",
        "created_at_utc": now_utc(),
        "created_at_msk": now_msk(),
        "status": "PASS" if (
            normal.get("decision") == "NORMAL_EXECUTION_ALLOWED"
            and normal.get("writes_allowed") is True
            and already.get("decision") == "ALREADY_COMMITTED_NOOP"
            and already.get("writes_allowed") is False
            and already.get("noop_required") is True
            and blocked.get("decision") == "OUT_OF_PHASE_RERUN_BLOCKED"
            and blocked.get("writes_allowed") is False
            and blocked.get("blocked_before_writes") is True
        ) else "FAIL",
        "normal_execution": normal,
        "already_committed_noop": already,
        "out_of_phase_block": blocked,
    }
    write_json(REPLAY, replay)

    if replay["status"] != "PASS":
        status = "FAIL"
        hard = [{"code": "WRAPPER_REPLAY_FAIL", "actual": replay}]
        capability = "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_BUILD_BLOCKED"
        real_next = "repair_idempotent_guard_enforced_step_wrapper_v1"
        final_socc_status = "SOCC_IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_FAIL"

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
            "expected_memory": str(GUARD_REVIEW_PROOF),
            "required_artifacts": [str(WRAPPER), str(GUARD), str(SPEC), str(REPLAY), str(GUARD_REVIEW_PROOF)],
            "changed_artifacts": [str(WRAPPER), str(SPEC), str(REPLAY)],
            "material_claims": [
                "enforced wrapper script created",
                "wrapper spec created",
                "normal execution allows writes",
                "already committed rerun requires noop and blocks writes",
                "out-of-phase rerun blocks before writes",
                "route transition prepared under effect-auditor lane law",
            ],
        }
    )
    write_json(EFFECT_AUDIT, effect_audit)

    if effect_audit.get("status") != "PASS":
        status = "FAIL"
        hard = [{"code": "EFFECT_AUDIT_FAIL", "actual": effect_audit}]
        capability = "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_BUILD_BLOCKED"
        real_next = "repair_idempotent_guard_enforced_step_wrapper_v1"
        final_socc_status = "SOCC_IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_FAIL"

build = {
    "id": "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_BUILD_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "wrapper": str(WRAPPER),
    "guard": str(GUARD),
    "spec": str(SPEC),
    "replay": str(REPLAY),
    "effect_audit": str(EFFECT_AUDIT),
    "source_guard_review_proof": str(GUARD_REVIEW_PROOF),

    "idempotent_guard_enforced_step_wrapper_built": status == "PASS",
    "wrapper_applies_guard_before_writes": status == "PASS",
    "normal_execution_writes_allowed": status == "PASS",
    "already_committed_noop_writes_blocked": status == "PASS",
    "out_of_phase_rerun_blocked_before_writes": status == "PASS",
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
    "id": "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "build": str(BUILD),
    "build_md": str(BUILD_MD),
    "wrapper": str(WRAPPER),
    "guard": str(GUARD),
    "spec": str(SPEC),
    "replay": str(REPLAY),
    "effect_audit": str(EFFECT_AUDIT),
    "memory": str(MEMORY),

    "idempotent_guard_enforced_step_wrapper_built": status == "PASS",
    "wrapper_applies_guard_before_writes": status == "PASS",
    "normal_execution_writes_allowed": status == "PASS",
    "already_committed_noop_writes_blocked": status == "PASS",
    "out_of_phase_rerun_blocked_before_writes": status == "PASS",
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
    "id": "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": "Built enforced wrapper so future bounded steps can run the idempotent guard before writing proof/report/memory artifacts.",
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
            "idempotent_guard_enforced_step_wrapper_built": True,
            "wrapper_applies_guard_before_writes": True,
            "normal_execution_writes_allowed": True,
            "already_committed_noop_writes_blocked": True,
            "out_of_phase_rerun_blocked_before_writes": True,
            "ready_for_validation": True,
            "recommended_next_target": real_next,
        },
        pulse_updates={
            "idempotent_guard_enforced_step_wrapper_built": True,
            "wrapper_applies_guard_before_writes": True,
        },
        panel_updates={
            "idempotent_guard_enforced_step_wrapper_built": True,
            "wrapper_applies_guard_before_writes": True,
        },
        progress_updates={
            "idempotent_guard_enforced_step_wrapper_built": True,
            "wrapper_applies_guard_before_writes": True,
            "recommended_next_target": real_next,
        },
        reason="build_idempotent_guard_enforced_step_wrapper_v1",
    )
    write_json(COMMIT_RESULT, commit)
    build["atomic_commit_result"] = commit
    proof["atomic_commit_result"] = commit

    if commit.get("status") != "PASS":
        status = "FAIL"
        hard = [{"code": "ATOMIC_COMMIT_FAIL", "actual": commit}]
        build["status"] = "BLOCKED"
        build["hard_failures"] = hard
        build["real_next"] = "repair_idempotent_guard_enforced_step_wrapper_v1"
        proof["status"] = "FAIL"
        proof["hard_failures"] = hard
        proof["real_next"] = "repair_idempotent_guard_enforced_step_wrapper_v1"
        real_next = proof["real_next"]

write_json(BUILD, build)
write_json(PROOF, proof)
write_json(MEMORY, memory)

md = "# IDEMPOTENT GUARD ENFORCED STEP WRAPPER V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nIdempotent step guard was review-sealed, but future scripts still needed a reusable before-write enforcement wrapper.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt wrapper that applies idempotent guard before proof/report/memory writes.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Enforced wrapper is built. Next is validation.\n\n"
else:
    md += "Wrapper build is blocked. Repair required.\n\n"
md += "## Wrapper decisions\n\n"
md += "- NORMAL_EXECUTION_ALLOWED -> writes_allowed=True\n"
md += "- ALREADY_COMMITTED_NOOP -> noop_required=True, writes_allowed=False\n"
md += "- OUT_OF_PHASE_RERUN_BLOCKED -> blocked_before_writes=True, writes_allowed=False\n\n"
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

print("IDEMPOTENT GUARD ENFORCED STEP WRAPPER :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("WRAPPER::" + str(WRAPPER))
print("SPEC::" + str(SPEC))
print("REPLAY::" + str(REPLAY))
print("EFFECT_AUDIT::" + str(EFFECT_AUDIT))
print("COMMIT_RESULT::" + str(COMMIT_RESULT))
print("BUILD::" + str(BUILD))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_BUILT::" + str(status == "PASS"))
print("WRAPPER_APPLIES_GUARD_BEFORE_WRITES::" + str(status == "PASS"))
print("NORMAL_EXECUTION_WRITES_ALLOWED::" + str(status == "PASS"))
print("ALREADY_COMMITTED_NOOP_WRITES_BLOCKED::" + str(status == "PASS"))
print("OUT_OF_PHASE_RERUN_BLOCKED_BEFORE_WRITES::" + str(status == "PASS"))
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

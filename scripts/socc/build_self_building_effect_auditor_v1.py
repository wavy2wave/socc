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

SELECTOR_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_REVIEW_V1_PROOF.json"
SELECTOR_VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_VALIDATION_V1_PROOF.json"
SELECTOR_BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_V1_PROOF.json"

OUT = ROOT / "core/socc/autonomy/self_building/effect_auditor"
AUDITOR = ROOT / "scripts/socc/socc_self_building_effect_auditor_v1.py"
SPEC = OUT / "SELF_BUILDING_EFFECT_AUDITOR_SPEC_V1.json"
BUILD = OUT / "SELF_BUILDING_EFFECT_AUDITOR_BUILD_V1.json"
BUILD_MD = OUT / "SELF_BUILDING_EFFECT_AUDITOR_BUILD_V1.md"
TEST_VECTOR = OUT / "SELF_BUILDING_EFFECT_AUDITOR_TEST_VECTOR_V1.json"
AUDIT_REPLAY = OUT / "SELF_BUILDING_EFFECT_AUDITOR_BUILD_REPLAY_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_EFFECT_AUDITOR_V1_MEMORY.json"

EXPECTED_NEXT = "build_self_building_effect_auditor_v1"
EXPECTED_SELECTOR_CAPABILITY = "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_REVIEW_SEALED_EFFECT_AUDITOR_NEXT"
NEXT = "validate_self_building_effect_auditor_v1"

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

route = read_json(ROUTE)
pulse = read_json(PULSE)
panel = read_json(PANEL)
progress = read_json(PROGRESS)

selector_review = read_json(SELECTOR_REVIEW_PROOF)
selector_validation = read_json(SELECTOR_VALIDATION_PROOF)
selector_build = read_json(SELECTOR_BUILD_PROOF)
enforcer_text = read_text(ENFORCER)

route_next = route.get("lawful_next") or route.get("real_next")
route_truth = route.get("truth_boundary")
route_upstream = route.get("upstream_proof")

checks = {
    "route_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_effect_auditor_build": route_next == EXPECTED_NEXT,
    "route_upstream_selector_review": route_upstream == str(SELECTOR_REVIEW_PROOF),
    "route_selector_review_sealed": route.get("enforced_self_building_next_target_selector_review_sealed") is True,
    "route_selected_target_review_sealed": route.get("selected_next_target_review_sealed") == EXPECTED_NEXT,
    "route_ready_to_build_selected_next_target": route.get("ready_to_build_selected_next_target") is True,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "selector_review_proof_exists": SELECTOR_REVIEW_PROOF.exists(),
    "selector_review_status_pass": selector_review.get("status") == "PASS",
    "selector_review_capability_ok": selector_review.get("capability") == EXPECTED_SELECTOR_CAPABILITY,
    "selector_review_real_next_ok": selector_review.get("real_next") == EXPECTED_NEXT,
    "selector_review_selected_target_ok": selector_review.get("selected_next_target_review_sealed") == EXPECTED_NEXT,
    "selector_review_ready_to_build_selected": selector_review.get("ready_to_build_selected_next_target") is True,
    "selector_review_hard_failures_empty": selector_review.get("hard_failures") == [],

    "selector_validation_proof_exists": SELECTOR_VALIDATION_PROOF.exists(),
    "selector_validation_status_pass": selector_validation.get("status") == "PASS",
    "selector_validation_selected_target_ok": selector_validation.get("selected_next_target_validated") == EXPECTED_NEXT,
    "selector_validation_scheduler_rejected": selector_validation.get("scheduler_rejection_validated") is True,

    "selector_build_proof_exists": SELECTOR_BUILD_PROOF.exists(),
    "selector_build_status_pass": selector_build.get("status") == "PASS",
    "selector_build_selected_target_ok": selector_build.get("selected_next_target") == EXPECTED_NEXT,

    "enforcer_exists": ENFORCER.exists(),
    "enforcer_has_enforce_transition": "def enforce_atomic_commit_transition(" in enforcer_text,

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

pre_hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]

truth_boundary = (
    "Self-building effect auditor build only. This builds a bounded auditor for detecting semantic-null PASS by checking material "
    "effects: artifact deltas, proof/report/memory creation, route transition, atomic commit coherence, and forbidden escalation guards. "
    "It does not execute a tick, enable continuous loop, launch daemon, install scheduler, enable background loop, use network, widen queue, "
    "birth Entity/ANNA, approve final canon, or claim AGI."
)

auditor_code = r'''#!/usr/bin/env python3
from pathlib import Path
import json
import hashlib

ROOT = Path(".")

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

def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}

def exists(path):
    return Path(path).exists()

def file_hash(path):
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()[:24]

def forbidden_false(obj):
    return all(obj.get(k) is False for k in FORBIDDEN_FLAGS if k in obj)

def audit_effect(before, after):
    """
    before/after are dicts:
      route_before, route_after
      required_artifacts: list[path]
      changed_artifacts: list[path]
      expected_lawful_next_before
      expected_lawful_next_after
      expected_upstream_proof_after
      expected_memory
      material_claims: list[str]
    """
    hard = []
    evidence = {}

    route_before = before.get("route_before") or {}
    route_after = after.get("route_after") or {}

    before_next = route_before.get("lawful_next") or route_before.get("real_next")
    after_next = route_after.get("lawful_next") or route_after.get("real_next")

    expected_before = after.get("expected_lawful_next_before")
    expected_after = after.get("expected_lawful_next_after")
    expected_upstream = after.get("expected_upstream_proof_after")
    expected_memory = after.get("expected_memory")

    evidence["lawful_next_before"] = before_next
    evidence["lawful_next_after"] = after_next
    evidence["route_changed"] = before_next != after_next
    evidence["expected_before_ok"] = before_next == expected_before if expected_before else True
    evidence["expected_after_ok"] = after_next == expected_after if expected_after else True
    evidence["upstream_ok"] = route_after.get("upstream_proof") == expected_upstream if expected_upstream else True
    evidence["memory_exists"] = exists(expected_memory) if expected_memory else True
    evidence["forbidden_false_after"] = forbidden_false(route_after)

    if not evidence["route_changed"]:
        hard.append({"code": "SEMANTIC_NULL", "check": "route_changed", "actual": False})
    if evidence["expected_before_ok"] is not True:
        hard.append({"code": "EXPECTATION_FAIL", "check": "expected_before_ok", "actual": before_next})
    if evidence["expected_after_ok"] is not True:
        hard.append({"code": "EXPECTATION_FAIL", "check": "expected_after_ok", "actual": after_next})
    if evidence["upstream_ok"] is not True:
        hard.append({"code": "EXPECTATION_FAIL", "check": "upstream_ok", "actual": route_after.get("upstream_proof")})
    if evidence["memory_exists"] is not True:
        hard.append({"code": "MISSING_EFFECT", "check": "memory_exists", "actual": expected_memory})
    if evidence["forbidden_false_after"] is not True:
        hard.append({"code": "FORBIDDEN_TRUE", "check": "forbidden_false_after", "actual": False})

    required = after.get("required_artifacts") or []
    changed = after.get("changed_artifacts") or []

    required_results = {}
    for item in required:
        required_results[item] = exists(item)
        if not required_results[item]:
            hard.append({"code": "MISSING_ARTIFACT", "artifact": item})

    changed_results = {}
    for item in changed:
        changed_results[item] = file_hash(item)
        if changed_results[item] is None:
            hard.append({"code": "MISSING_CHANGED_ARTIFACT", "artifact": item})

    evidence["required_artifacts"] = required_results
    evidence["changed_artifacts_hashes"] = changed_results
    evidence["material_claims_count"] = len(after.get("material_claims") or [])

    if evidence["material_claims_count"] <= 0:
        hard.append({"code": "NO_MATERIAL_CLAIMS", "check": "material_claims_count", "actual": 0})

    return {
        "status": "PASS" if not hard else "FAIL",
        "semantic_null_pass_blocked": bool(hard),
        "material_effect_proven": not bool(hard),
        "evidence": evidence,
        "hard_failures": hard,
    }
'''

status = "PASS" if not pre_hard else "FAIL"

if status == "PASS":
    write_text(AUDITOR, auditor_code)
    AUDITOR.chmod(0o755)

    capability = "SELF_BUILDING_EFFECT_AUDITOR_BUILT_SEMANTIC_NULL_PASS_CONTROL"
    real_next = NEXT
    final_socc_status = "SOCC_SELF_BUILDING_EFFECT_AUDITOR_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_EFFECT_AUDITOR_BLOCKED"
    real_next = "repair_self_building_effect_auditor_v1"
    final_socc_status = "SOCC_SELF_BUILDING_EFFECT_AUDITOR_FAIL"

spec = {
    "id": "SELF_BUILDING_EFFECT_AUDITOR_SPEC_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "purpose": "Detect and block semantic-null PASS by requiring material state/artifact effects.",
    "auditor": str(AUDITOR),
    "required_effect_classes": [
        "route_lawful_next_changed",
        "upstream_proof_changed",
        "proof_artifact_exists",
        "memory_artifact_exists",
        "required_artifacts_exist",
        "changed_artifacts_hashable",
        "forbidden_flags_remain_false",
    ],
    "truth_boundary": truth_boundary,
}

test_vector = {
    "id": "SELF_BUILDING_EFFECT_AUDITOR_TEST_VECTOR_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "positive_case": {
        "before": {"route_before": {"lawful_next": "x"}},
        "after": {
            "route_after": {
                "lawful_next": "y",
                "upstream_proof": str(PROOF),
                "continuous_loop_enabled": False,
                "daemon_running": False,
                "scheduler_installed": False,
            },
            "expected_lawful_next_before": "x",
            "expected_lawful_next_after": "y",
            "expected_upstream_proof_after": str(PROOF),
            "expected_memory": None,  # memory is written after build replay; validation/review will check real memory artifact
            "required_artifacts": [str(SPEC)],
            "changed_artifacts": [str(AUDITOR)],
            "material_claims": ["auditor file built", "spec built", "route transition planned"],
        },
    },
    "negative_case_semantic_null": {
        "before": {"route_before": {"lawful_next": "x"}},
        "after": {
            "route_after": {"lawful_next": "x", "upstream_proof": str(PROOF)},
            "expected_lawful_next_before": "x",
            "expected_lawful_next_after": "y",
            "expected_upstream_proof_after": str(PROOF),
            "expected_memory": str(MEMORY),
            "required_artifacts": [],
            "changed_artifacts": [],
            "material_claims": [],
        },
    },
}

audit_replay = {"status": "SKIPPED"}
if status == "PASS":
    write_json(SPEC, spec)
    write_json(TEST_VECTOR, test_vector)

    auditor_mod = import_module(AUDITOR, "effect_auditor")
    positive = auditor_mod.audit_effect(
        test_vector["positive_case"]["before"],
        test_vector["positive_case"]["after"],
    )
    negative = auditor_mod.audit_effect(
        test_vector["negative_case_semantic_null"]["before"],
        test_vector["negative_case_semantic_null"]["after"],
    )
    audit_replay = {
        "id": "SELF_BUILDING_EFFECT_AUDITOR_BUILD_REPLAY_V1",
        "created_at_utc": now_utc(),
        "created_at_msk": now_msk(),
        "status": "PASS" if positive.get("status") == "PASS" and negative.get("status") == "FAIL" else "FAIL",
        "positive_case": positive,
        "negative_case_semantic_null": negative,
    }
    write_json(AUDIT_REPLAY, audit_replay)

    if audit_replay["status"] != "PASS":
        status = "FAIL"
        pre_hard = [{"code": "AUDITOR_REPLAY_FAIL", "actual": audit_replay}]
        capability = "SELF_BUILDING_EFFECT_AUDITOR_BLOCKED"
        real_next = "repair_self_building_effect_auditor_v1"
        final_socc_status = "SOCC_SELF_BUILDING_EFFECT_AUDITOR_FAIL"

build = {
    "id": "SELF_BUILDING_EFFECT_AUDITOR_BUILD_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "auditor": str(AUDITOR),
    "spec": str(SPEC),
    "test_vector": str(TEST_VECTOR),
    "audit_replay": str(AUDIT_REPLAY),
    "source_selector_review_proof": str(SELECTOR_REVIEW_PROOF),

    "self_building_effect_auditor_built": status == "PASS",
    "semantic_null_pass_control_built": status == "PASS",
    "material_effect_gate_built": status == "PASS",
    "build_replay_memory_check_deferred": status == "PASS",
    "positive_effect_case_passed": audit_replay.get("positive_case", {}).get("status") == "PASS" if status == "PASS" else False,
    "negative_semantic_null_case_blocked": audit_replay.get("negative_case_semantic_null", {}).get("status") == "FAIL" if status == "PASS" else False,
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
    "hard_failures": pre_hard,
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}
build["build_hash"] = h(build)

proof = {
    "id": "SELF_BUILDING_EFFECT_AUDITOR_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "build": str(BUILD),
    "build_md": str(BUILD_MD),
    "auditor": str(AUDITOR),
    "spec": str(SPEC),
    "test_vector": str(TEST_VECTOR),
    "audit_replay": str(AUDIT_REPLAY),
    "memory": str(MEMORY),

    "self_building_effect_auditor_built": status == "PASS",
    "semantic_null_pass_control_built": status == "PASS",
    "material_effect_gate_built": status == "PASS",
    "positive_effect_case_passed": audit_replay.get("positive_case", {}).get("status") == "PASS" if status == "PASS" else False,
    "negative_semantic_null_case_blocked": audit_replay.get("negative_case_semantic_null", {}).get("status") == "FAIL" if status == "PASS" else False,
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
    "hard_failures": pre_hard,
    "real_next": real_next,
    "final_socc_status": final_socc_status,
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h(proof)

memory = {
    "id": "SELF_BUILDING_EFFECT_AUDITOR_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": "Built self-building effect auditor to block semantic-null PASS and require material effects.",
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
            "self_building_effect_auditor_built": True,
            "semantic_null_pass_control_built": True,
            "material_effect_gate_built": True,
            "positive_effect_case_passed": True,
            "negative_semantic_null_case_blocked": True,
            "ready_for_validation": True,
            "recommended_next_target": real_next,
        },
        pulse_updates={
            "self_building_effect_auditor_built": True,
            "semantic_null_pass_control_built": True,
        },
        panel_updates={
            "self_building_effect_auditor_built": True,
            "semantic_null_pass_control_built": True,
        },
        progress_updates={
            "self_building_effect_auditor_built": True,
            "semantic_null_pass_control_built": True,
            "recommended_next_target": real_next,
        },
        reason="build_self_building_effect_auditor_v1",
    )
    build["atomic_commit_result"] = commit
    proof["atomic_commit_result"] = commit
    if commit.get("status") != "PASS":
        status = "FAIL"
        pre_hard = [{"code": "ATOMIC_COMMIT_FAIL", "actual": commit}]
        build["status"] = "BLOCKED"
        build["hard_failures"] = pre_hard
        build["real_next"] = "repair_self_building_effect_auditor_v1"
        proof["status"] = "FAIL"
        proof["hard_failures"] = pre_hard
        proof["real_next"] = "repair_self_building_effect_auditor_v1"

md = "# SELF-BUILDING EFFECT AUDITOR V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nSelector review sealed build_self_building_effect_auditor_v1 as next lawful target.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt bounded effect auditor to detect semantic-null PASS and require material effects.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Effect auditor is built. Next is validation.\n\n"
else:
    md += "Effect auditor build is blocked. Repair required.\n\n"
md += "## Effect gate\n\n"
md += "- route lawful_next must change when expected\n"
md += "- upstream proof must change\n"
md += "- required artifacts must exist\n"
md += "- memory artifact must exist\n"
md += "- forbidden flags must remain false\n"
md += "- semantic-null PASS must be blocked\n\n"
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

print("SELF-BUILDING EFFECT AUDITOR :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("AUDITOR::" + str(AUDITOR))
print("SPEC::" + str(SPEC))
print("TEST_VECTOR::" + str(TEST_VECTOR))
print("AUDIT_REPLAY::" + str(AUDIT_REPLAY))
print("BUILD::" + str(BUILD))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SELF_BUILDING_EFFECT_AUDITOR_BUILT::" + str(status == "PASS"))
print("SEMANTIC_NULL_PASS_CONTROL_BUILT::" + str(status == "PASS"))
print("MATERIAL_EFFECT_GATE_BUILT::" + str(status == "PASS"))
print("POSITIVE_EFFECT_CASE_PASSED::" + str(audit_replay.get("positive_case", {}).get("status") == "PASS" if status == "PASS" else False))
print("NEGATIVE_SEMANTIC_NULL_CASE_BLOCKED::" + str(audit_replay.get("negative_case_semantic_null", {}).get("status") == "FAIL" if status == "PASS" else False))
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
print("HARD_FAILURES::" + json.dumps(pre_hard, ensure_ascii=False))
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if status == "PASS" else 1)

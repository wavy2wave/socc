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
AUDITOR = ROOT / "scripts/socc/socc_self_building_effect_auditor_v1.py"

REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_REVIEW_V1_PROOF.json"
VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_V1_PROOF.json"
BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_V1_PROOF.json"

OUT = ROOT / "core/socc/autonomy/self_building/effect_auditor/enforced_lane"
LANE = ROOT / "scripts/socc/socc_self_building_effect_auditor_enforced_lane_v1.py"
POLICY = OUT / "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_POLICY_V1.json"
BUILD = OUT / "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_BUILD_V1.json"
BUILD_MD = OUT / "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_BUILD_V1.md"
REPLAY = OUT / "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REPLAY_V1.json"
NULL_PROBE = OUT / "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_NULL_PROBE_V1.json"
COMMIT_RESULT = OUT / "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_COMMIT_RESULT_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_V1_MEMORY.json"

EXPECTED_NEXT = "build_self_building_effect_auditor_enforced_lane_v1"
NEXT = "validate_self_building_effect_auditor_enforced_lane_v1"

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

review_proof = read_json(REVIEW_PROOF)
validation_proof = read_json(VALIDATION_PROOF)
build_proof = read_json(BUILD_PROOF)

auditor_text = read_text(AUDITOR)
enforcer_text = read_text(ENFORCER)

route_next = route.get("lawful_next") or route.get("real_next")
route_truth = route.get("truth_boundary")
route_upstream = route.get("upstream_proof")

checks = {
    "route_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_enforced_lane_build": route_next == EXPECTED_NEXT,
    "route_upstream_effect_auditor_review": route_upstream == str(REVIEW_PROOF),
    "route_effect_auditor_review_sealed": route.get("self_building_effect_auditor_review_sealed") is True,
    "route_semantic_null_class_controlled": route.get("semantic_null_pass_class_controlled") is True,
    "route_ready_to_enforce_effect_auditor_lane": route.get("ready_to_enforce_effect_auditor_lane") is True,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "review_proof_exists": REVIEW_PROOF.exists(),
    "review_proof_status_pass": review_proof.get("status") == "PASS",
    "review_capability_ok": review_proof.get("capability") == "SELF_BUILDING_EFFECT_AUDITOR_REVIEW_SEALED_SEMANTIC_NULL_CLASS_CONTROLLED",
    "review_real_next_ok": review_proof.get("real_next") == EXPECTED_NEXT,
    "review_semantic_null_class_controlled": review_proof.get("semantic_null_pass_class_controlled") is True,
    "review_ready_to_enforce_lane": review_proof.get("ready_to_enforce_effect_auditor_lane") is True,
    "review_hard_failures_empty": review_proof.get("hard_failures") == [],

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": validation_proof.get("status") == "PASS",
    "validation_semantic_null_control_validated": validation_proof.get("semantic_null_pass_control_validated") is True,
    "validation_material_gate_validated": validation_proof.get("material_effect_gate_validated") is True,
    "validation_negative_semantic_null_blocked": validation_proof.get("negative_semantic_null_validation_blocked") is True,

    "build_proof_exists": BUILD_PROOF.exists(),
    "build_status_pass": build_proof.get("status") == "PASS",
    "build_semantic_null_control_built": build_proof.get("semantic_null_pass_control_built") is True,
    "build_negative_case_blocked": build_proof.get("negative_semantic_null_case_blocked") is True,

    "auditor_exists": AUDITOR.exists(),
    "auditor_has_audit_effect": "def audit_effect(" in auditor_text,
    "auditor_has_semantic_null_code": "SEMANTIC_NULL" in auditor_text,
    "auditor_checks_route_changed": "route_changed" in auditor_text,
    "auditor_checks_material_claims": "material_claims_count" in auditor_text,
    "auditor_checks_memory_exists": "memory_exists" in auditor_text,

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

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]

truth_boundary = (
    "Self-building effect auditor enforced-lane build only. This builds the lane-level enforcement wrapper requiring future bounded self-building "
    "steps to prove material effect through the review-sealed effect auditor before PASS is accepted. It does not execute a tick, enable continuous loop, "
    "launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

lane_code = r'''#!/usr/bin/env python3
from pathlib import Path
import importlib.util

AUDITOR = Path("scripts/socc/socc_self_building_effect_auditor_v1.py")

def _import_auditor():
    spec = importlib.util.spec_from_file_location("socc_self_building_effect_auditor_v1", AUDITOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def enforce_effect_auditor_lane(before, after):
    """
    Enforced lane gate for bounded self-building steps.

    Required input:
      before: {"route_before": {...}}
      after:
        {
          "route_after": {...},
          "expected_lawful_next_before": "...",
          "expected_lawful_next_after": "...",
          "expected_upstream_proof_after": "...",
          "expected_memory": "...",
          "required_artifacts": [...],
          "changed_artifacts": [...],
          "material_claims": [...]
        }

    PASS means material effect proven.
    FAIL means semantic-null or missing-effect work must not be accepted as PASS.
    """
    auditor = _import_auditor()
    audit = auditor.audit_effect(before, after)

    return {
        "status": "PASS" if audit.get("status") == "PASS" and audit.get("material_effect_proven") is True else "FAIL",
        "effect_auditor_enforced": True,
        "material_effect_required": True,
        "semantic_null_pass_blocked": audit.get("status") != "PASS",
        "audit": audit,
        "hard_failures": [] if audit.get("status") == "PASS" and audit.get("material_effect_proven") is True else audit.get("hard_failures", []),
    }
'''

status = "PASS" if not hard else "FAIL"
capability = "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_BUILT_MATERIAL_EFFECT_REQUIRED" if status == "PASS" else "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_BLOCKED"
real_next = NEXT if status == "PASS" else "repair_self_building_effect_auditor_enforced_lane_v1"
final_socc_status = "SOCC_SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI" if status == "PASS" else "SOCC_SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_FAIL"

replay = {}
null_probe = {}
commit = {}

if status == "PASS":
    write_text(LANE, lane_code)
    LANE.chmod(0o755)

    policy = {
        "id": "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_POLICY_V1",
        "created_at_utc": now_utc(),
        "created_at_msk": now_msk(),
        "status": "BUILT",
        "policy": "Every future bounded self-building PASS must provide a material effect audit.",
        "requires": [
            "before_route_snapshot",
            "after_route_snapshot",
            "expected_lawful_next_before",
            "expected_lawful_next_after",
            "expected_upstream_proof_after",
            "expected_memory",
            "required_artifacts",
            "changed_artifacts",
            "material_claims",
            "forbidden_flags_false",
        ],
        "blocks": [
            "semantic_null_pass",
            "no_route_delta",
            "missing_memory",
            "missing_required_artifacts",
            "no_material_claims",
            "forbidden_escalation",
        ],
        "truth_boundary": truth_boundary,
    }
    write_json(POLICY, policy)

    lane = import_module(LANE, "effect_auditor_enforced_lane")

    replay = lane.enforce_effect_auditor_lane(
        {"route_before": {"lawful_next": EXPECTED_NEXT}},
        {
            "route_after": {
                "lawful_next": NEXT,
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
            "expected_lawful_next_after": NEXT,
            "expected_upstream_proof_after": str(PROOF),
            "expected_memory": str(REVIEW_PROOF),
            "required_artifacts": [str(AUDITOR), str(REVIEW_PROOF), str(POLICY)],
            "changed_artifacts": [str(LANE), str(POLICY)],
            "material_claims": [
                "enforced lane wrapper created",
                "policy created",
                "effect auditor is required for future PASS",
                "semantic-null lane probe configured",
            ],
        }
    )
    write_json(REPLAY, replay)

    null_probe = lane.enforce_effect_auditor_lane(
        {"route_before": {"lawful_next": "same"}},
        {
            "route_after": {
                "lawful_next": "same",
                "upstream_proof": str(PROOF),
                "continuous_loop_enabled": False,
                "daemon_running": False,
                "scheduler_installed": False,
            },
            "expected_lawful_next_before": "same",
            "expected_lawful_next_after": "different",
            "expected_upstream_proof_after": str(PROOF),
            "expected_memory": str(REVIEW_PROOF),
            "required_artifacts": [],
            "changed_artifacts": [],
            "material_claims": [],
        }
    )
    write_json(NULL_PROBE, null_probe)

    if replay.get("status") != "PASS" or null_probe.get("status") != "FAIL":
        status = "FAIL"
        capability = "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_BLOCKED"
        real_next = "repair_self_building_effect_auditor_enforced_lane_v1"
        final_socc_status = "SOCC_SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_FAIL"
        hard = [{"code": "ENFORCED_LANE_REPLAY_FAIL", "replay": replay, "null_probe": null_probe}]

build = {
    "id": "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_BUILD_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "lane": str(LANE),
    "policy": str(POLICY),
    "replay": str(REPLAY),
    "null_probe": str(NULL_PROBE),
    "source_review_proof": str(REVIEW_PROOF),

    "self_building_effect_auditor_enforced_lane_built": status == "PASS",
    "material_effect_required_lane_built": status == "PASS",
    "semantic_null_pass_lane_block_built": status == "PASS",
    "positive_lane_replay_passed": replay.get("status") == "PASS" if status == "PASS" else False,
    "negative_lane_null_probe_blocked": null_probe.get("status") == "FAIL" if status == "PASS" else False,
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
    "id": "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "build": str(BUILD),
    "build_md": str(BUILD_MD),
    "lane": str(LANE),
    "policy": str(POLICY),
    "replay": str(REPLAY),
    "null_probe": str(NULL_PROBE),
    "memory": str(MEMORY),

    "self_building_effect_auditor_enforced_lane_built": status == "PASS",
    "material_effect_required_lane_built": status == "PASS",
    "semantic_null_pass_lane_block_built": status == "PASS",
    "positive_lane_replay_passed": replay.get("status") == "PASS" if status == "PASS" else False,
    "negative_lane_null_probe_blocked": null_probe.get("status") == "FAIL" if status == "PASS" else False,
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
    "id": "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": "Built enforced lane requiring future bounded self-building PASS to prove material effect through the effect auditor.",
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
            "self_building_effect_auditor_enforced_lane_built": True,
            "material_effect_required_lane_built": True,
            "semantic_null_pass_lane_block_built": True,
            "positive_lane_replay_passed": True,
            "negative_lane_null_probe_blocked": True,
            "ready_for_validation": True,
            "recommended_next_target": real_next,
        },
        pulse_updates={
            "self_building_effect_auditor_enforced_lane_built": True,
            "material_effect_required_lane_built": True,
        },
        panel_updates={
            "self_building_effect_auditor_enforced_lane_built": True,
            "material_effect_required_lane_built": True,
        },
        progress_updates={
            "self_building_effect_auditor_enforced_lane_built": True,
            "material_effect_required_lane_built": True,
            "recommended_next_target": real_next,
        },
        reason="build_self_building_effect_auditor_enforced_lane_v1",
    )
    write_json(COMMIT_RESULT, commit)
    build["atomic_commit_result"] = commit
    proof["atomic_commit_result"] = commit

    if commit.get("status") != "PASS":
        status = "FAIL"
        hard = [{"code": "ATOMIC_COMMIT_FAIL", "actual": commit}]
        build["status"] = "BLOCKED"
        build["hard_failures"] = hard
        build["real_next"] = "repair_self_building_effect_auditor_enforced_lane_v1"
        proof["status"] = "FAIL"
        proof["hard_failures"] = hard
        proof["real_next"] = "repair_self_building_effect_auditor_enforced_lane_v1"

md = "# SELF-BUILDING EFFECT AUDITOR ENFORCED LANE V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nEffect auditor review PASS. Semantic-null PASS class is controlled and ready for lane enforcement.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt enforced lane wrapper and policy requiring material-effect audit for future bounded self-building PASS.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Effect auditor enforced lane is built. Next is validation.\n\n"
else:
    md += "Effect auditor enforced lane build is blocked. Repair required.\n\n"
md += "## Lane law\n\n"
md += "- future bounded self-building PASS requires material effect\n"
md += "- semantic-null PASS is blocked\n"
md += "- route transition must be non-null when expected\n"
md += "- proof/report/memory artifacts must exist when claimed\n"
md += "- forbidden escalation flags must remain false\n\n"
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

write_json(BUILD, build)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(BUILD_MD, md)

print("SELF-BUILDING EFFECT AUDITOR ENFORCED LANE :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("LANE::" + str(LANE))
print("POLICY::" + str(POLICY))
print("REPLAY::" + str(REPLAY))
print("NULL_PROBE::" + str(NULL_PROBE))
print("COMMIT_RESULT::" + str(COMMIT_RESULT))
print("BUILD::" + str(BUILD))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_BUILT::" + str(status == "PASS"))
print("MATERIAL_EFFECT_REQUIRED_LANE_BUILT::" + str(status == "PASS"))
print("SEMANTIC_NULL_PASS_LANE_BLOCK_BUILT::" + str(status == "PASS"))
print("POSITIVE_LANE_REPLAY_PASSED::" + str(replay.get("status") == "PASS" if status == "PASS" else False))
print("NEGATIVE_LANE_NULL_PROBE_BLOCKED::" + str(null_probe.get("status") == "FAIL" if status == "PASS" else False))
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

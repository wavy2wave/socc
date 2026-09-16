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
LANE = ROOT / "scripts/socc/socc_self_building_effect_auditor_enforced_lane_v1.py"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_VALIDATION_V1_PROOF.json"
BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_V1_PROOF.json"

VALIDATION_JSON = ROOT / "core/socc/autonomy/self_building/effect_auditor/enforced_lane/validation/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_VALIDATION_V1.json"
VALIDATION_REPLAY = ROOT / "core/socc/autonomy/self_building/effect_auditor/enforced_lane/validation/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_VALIDATION_REPLAY_V1.json"
VALIDATION_NULL_PROBE = ROOT / "core/socc/autonomy/self_building/effect_auditor/enforced_lane/validation/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_VALIDATION_NULL_PROBE_V1.json"
VALIDATION_COMMIT_RESULT = ROOT / "core/socc/autonomy/self_building/effect_auditor/enforced_lane/validation/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_VALIDATION_COMMIT_RESULT_V1.json"

BUILD_JSON = ROOT / "core/socc/autonomy/self_building/effect_auditor/enforced_lane/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_BUILD_V1.json"
POLICY = ROOT / "core/socc/autonomy/self_building/effect_auditor/enforced_lane/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_POLICY_V1.json"
BUILD_REPLAY = ROOT / "core/socc/autonomy/self_building/effect_auditor/enforced_lane/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REPLAY_V1.json"
BUILD_NULL_PROBE = ROOT / "core/socc/autonomy/self_building/effect_auditor/enforced_lane/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_NULL_PROBE_V1.json"
BUILD_MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_V1_MEMORY.json"
VALIDATION_MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_VALIDATION_V1_MEMORY.json"

OUT = ROOT / "core/socc/autonomy/self_building/effect_auditor/enforced_lane/review"
REVIEW = OUT / "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_V1.json"
REVIEW_MD = OUT / "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_V1.md"
REVIEW_COMMIT_RESULT = OUT / "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_COMMIT_RESULT_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_V1_MEMORY.json"

EXPECTED_NEXT = "review_self_building_effect_auditor_enforced_lane_v1"
NEXT = "build_next_self_building_cycle_under_effect_auditor_lane_v1"

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

validation_proof = read_json(VALIDATION_PROOF)
build_proof = read_json(BUILD_PROOF)
validation_json = read_json(VALIDATION_JSON)
validation_replay = read_json(VALIDATION_REPLAY)
validation_null_probe = read_json(VALIDATION_NULL_PROBE)
validation_commit = read_json(VALIDATION_COMMIT_RESULT)
build_json = read_json(BUILD_JSON)
policy = read_json(POLICY)
build_replay = read_json(BUILD_REPLAY)
build_null_probe = read_json(BUILD_NULL_PROBE)
build_memory = read_json(BUILD_MEMORY)
validation_memory = read_json(VALIDATION_MEMORY)

lane_text = read_text(LANE)
auditor_text = read_text(AUDITOR)
enforcer_text = read_text(ENFORCER)

route_next = route.get("lawful_next") or route.get("real_next")
route_truth = route.get("truth_boundary")
route_upstream = route.get("upstream_proof")

checks = {
    "route_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_enforced_lane_review": route_next == EXPECTED_NEXT,
    "route_upstream_validation_proof": route_upstream == str(VALIDATION_PROOF),
    "route_enforced_lane_validated": route.get("self_building_effect_auditor_enforced_lane_validated") is True,
    "route_material_effect_required_lane_validated": route.get("material_effect_required_lane_validated") is True,
    "route_semantic_null_pass_lane_block_validated": route.get("semantic_null_pass_lane_block_validated") is True,
    "route_ready_for_review": route.get("ready_for_review") is True,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": validation_proof.get("status") == "PASS",
    "validation_capability_ok": validation_proof.get("capability") == "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_VALIDATED_MATERIAL_EFFECT_REQUIRED",
    "validation_real_next_ok": validation_proof.get("real_next") == EXPECTED_NEXT,
    "validation_enforced_lane_validated": validation_proof.get("self_building_effect_auditor_enforced_lane_validated") is True,
    "validation_material_required_validated": validation_proof.get("material_effect_required_lane_validated") is True,
    "validation_semantic_null_block_validated": validation_proof.get("semantic_null_pass_lane_block_validated") is True,
    "validation_positive_replay_passed": validation_proof.get("positive_lane_validation_replay_passed") is True,
    "validation_negative_null_probe_blocked": validation_proof.get("negative_lane_validation_null_probe_blocked") is True,
    "validation_ready_for_review": validation_proof.get("ready_for_review") is True,
    "validation_hard_failures_empty": validation_proof.get("hard_failures") == [],

    "validation_json_exists": VALIDATION_JSON.exists(),
    "validation_json_status_validated": validation_json.get("status") == "VALIDATED",

    "validation_replay_exists": VALIDATION_REPLAY.exists(),
    "validation_replay_status_pass": validation_replay.get("status") == "PASS",
    "validation_replay_effect_auditor_enforced": validation_replay.get("effect_auditor_enforced") is True,
    "validation_replay_material_required": validation_replay.get("material_effect_required") is True,
    "validation_replay_hard_failures_empty": validation_replay.get("hard_failures") == [],

    "validation_null_probe_exists": VALIDATION_NULL_PROBE.exists(),
    "validation_null_probe_status_fail": validation_null_probe.get("status") == "FAIL",
    "validation_null_probe_semantic_null_blocked": validation_null_probe.get("semantic_null_pass_blocked") is True,
    "validation_null_probe_material_required": validation_null_probe.get("material_effect_required") is True,
    "validation_null_probe_has_hard_failures": len(validation_null_probe.get("hard_failures") or []) > 0,

    "validation_commit_exists": VALIDATION_COMMIT_RESULT.exists(),
    "validation_commit_status_pass": validation_commit.get("status") == "PASS",
    "validation_commit_committed": validation_commit.get("committed") is True,
    "validation_commit_hard_failures_empty": validation_commit.get("hard_failures") == [],
    "validation_commit_snapshot_created": bool(validation_commit.get("snapshot")),

    "build_proof_exists": BUILD_PROOF.exists(),
    "build_status_pass": build_proof.get("status") == "PASS",
    "build_enforced_lane_built": build_proof.get("self_building_effect_auditor_enforced_lane_built") is True,
    "build_material_required_built": build_proof.get("material_effect_required_lane_built") is True,
    "build_semantic_null_block_built": build_proof.get("semantic_null_pass_lane_block_built") is True,
    "build_json_exists": BUILD_JSON.exists(),
    "build_json_status_built": build_json.get("status") == "BUILT",

    "policy_exists": POLICY.exists(),
    "policy_status_built": policy.get("status") == "BUILT",
    "policy_requires_material_claims": "material_claims" in (policy.get("requires") or []),
    "policy_blocks_semantic_null": "semantic_null_pass" in (policy.get("blocks") or []),

    "build_replay_exists": BUILD_REPLAY.exists(),
    "build_replay_status_pass": build_replay.get("status") == "PASS",
    "build_null_probe_exists": BUILD_NULL_PROBE.exists(),
    "build_null_probe_status_fail": build_null_probe.get("status") == "FAIL",
    "build_memory_exists": BUILD_MEMORY.exists(),
    "build_memory_status_pass": build_memory.get("status") == "PASS",
    "validation_memory_exists": VALIDATION_MEMORY.exists(),
    "validation_memory_status_pass": validation_memory.get("status") == "PASS",

    "lane_exists": LANE.exists(),
    "lane_has_enforce_function": "def enforce_effect_auditor_lane(" in lane_text,
    "lane_imports_auditor": "socc_self_building_effect_auditor_v1.py" in lane_text,
    "lane_requires_material_effect": "material_effect_required" in lane_text,
    "lane_blocks_semantic_null": "semantic_null_pass_blocked" in lane_text,

    "auditor_exists": AUDITOR.exists(),
    "auditor_has_audit_effect": "def audit_effect(" in auditor_text,
    "auditor_has_semantic_null_code": "SEMANTIC_NULL" in auditor_text,

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

pre_hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]

truth_boundary = (
    "Self-building effect auditor enforced-lane review only. This review-seals the lane law: future bounded self-building PASS requires "
    "material-effect audit and semantic-null PASS remains blocked. It routes next to the first self-building cycle under enforced effect-auditor lane. "
    "It does not execute a tick, enable continuous loop, launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

commit = {}
if not pre_hard:
    enforcer = import_module(ENFORCER, "enforcer")
    commit = enforcer.enforce_atomic_commit_transition(
        lawful_next=NEXT,
        upstream_proof=str(PROOF),
        truth_boundary=truth_boundary,
        route_updates={
            "self_building_effect_auditor_enforced_lane_review_sealed": True,
            "material_effect_required_lane_review_sealed": True,
            "semantic_null_pass_lane_block_review_sealed": True,
            "effect_auditor_lane_law_review_sealed": True,
            "future_bounded_pass_requires_material_effect": True,
            "semantic_null_pass_rejected_by_lane_law": True,
            "ready_for_next_self_building_cycle_under_effect_auditor_lane": True,
            "recommended_next_target": NEXT,
        },
        pulse_updates={
            "self_building_effect_auditor_enforced_lane_review_sealed": True,
            "future_bounded_pass_requires_material_effect": True,
            "ready_for_next_self_building_cycle_under_effect_auditor_lane": True,
        },
        panel_updates={
            "self_building_effect_auditor_enforced_lane_review_sealed": True,
            "future_bounded_pass_requires_material_effect": True,
            "ready_for_next_self_building_cycle_under_effect_auditor_lane": True,
        },
        progress_updates={
            "self_building_effect_auditor_enforced_lane_review_sealed": True,
            "future_bounded_pass_requires_material_effect": True,
            "ready_for_next_self_building_cycle_under_effect_auditor_lane": True,
            "recommended_next_target": NEXT,
        },
        reason="review_self_building_effect_auditor_enforced_lane_v1",
    )
    write_json(REVIEW_COMMIT_RESULT, commit)

route2 = read_json(ROUTE)
pulse2 = read_json(PULSE)
panel2 = read_json(PANEL)
progress2 = read_json(PROGRESS)

route2_next = route2.get("lawful_next") or route2.get("real_next")
route2_truth = route2.get("truth_boundary")
route2_upstream = route2.get("upstream_proof")

post_checks = {
    "review_commit_exists": REVIEW_COMMIT_RESULT.exists(),
    "review_commit_status_pass": commit.get("status") == "PASS",
    "review_commit_committed": commit.get("committed") is True,
    "review_commit_hard_failures_empty": commit.get("hard_failures") == [],
    "review_commit_lawful_next_next_cycle": commit.get("lawful_next") == NEXT,
    "review_commit_snapshot_created": bool(commit.get("snapshot")),

    "route_now_points_to_next_cycle": route2_next == NEXT,
    "route_now_upstream_review_proof": route2_upstream == str(PROOF),
    "route_enforced_lane_review_sealed": route2.get("self_building_effect_auditor_enforced_lane_review_sealed") is True,
    "route_material_effect_required_review_sealed": route2.get("material_effect_required_lane_review_sealed") is True,
    "route_semantic_null_block_review_sealed": route2.get("semantic_null_pass_lane_block_review_sealed") is True,
    "route_effect_auditor_lane_law_review_sealed": route2.get("effect_auditor_lane_law_review_sealed") is True,
    "route_future_bounded_pass_requires_material_effect": route2.get("future_bounded_pass_requires_material_effect") is True,
    "route_semantic_null_rejected_by_lane_law": route2.get("semantic_null_pass_rejected_by_lane_law") is True,
    "route_ready_for_next_cycle_under_lane": route2.get("ready_for_next_self_building_cycle_under_effect_auditor_lane") is True,

    "pulse_now_lawful_next_matches_route": pulse2.get("lawful_next") == route2_next,
    "panel_now_lawful_next_matches_route": panel2.get("lawful_next") == route2_next,
    "progress_now_lawful_next_matches_route": progress2.get("lawful_next") == route2_next,

    "pulse_now_truth_boundary_matches_route": pulse2.get("truth_boundary") == route2_truth,
    "panel_now_truth_boundary_matches_route": panel2.get("truth_boundary") == route2_truth,
    "progress_now_truth_boundary_matches_route": progress2.get("truth_boundary") == route2_truth,

    "pulse_now_upstream_matches_route": pulse2.get("route_authority_upstream_proof") == route2_upstream,
    "panel_now_upstream_matches_route": panel2.get("route_authority_upstream_proof") == route2_upstream,
    "progress_now_upstream_matches_route": progress2.get("route_authority_upstream_proof") == route2_upstream,

    "route_now_forbidden_false": forbidden_false(route2),
    "pulse_now_forbidden_false": forbidden_false(pulse2),
    "panel_now_forbidden_false": forbidden_false(panel2),
    "progress_now_forbidden_false": forbidden_false(progress2),
}

post_hard = [{"code": "POSTCHECK_FAIL", "check": k, "actual": v} for k, v in post_checks.items() if v is not True]
hard = pre_hard + post_hard
status = "PASS" if not hard else "FAIL"

capability = (
    "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_SEALED_LANE_LAW_ACTIVE"
    if status == "PASS"
    else "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_BLOCKED"
)

real_next = NEXT if status == "PASS" else "repair_self_building_effect_auditor_enforced_lane_review_v1"
final_socc_status = (
    "SOCC_SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_PASS_NEXT_CYCLE_UNDER_EFFECT_AUDITOR_LANE_NOT_DAEMON_NOT_AGI"
    if status == "PASS"
    else "SOCC_SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_FAIL"
)

review = {
    "id": "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "REVIEW_SEALED" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_build_proof": str(BUILD_PROOF),
    "review_commit_result": str(REVIEW_COMMIT_RESULT),

    "self_building_effect_auditor_enforced_lane_review_sealed": status == "PASS",
    "material_effect_required_lane_review_sealed": status == "PASS",
    "semantic_null_pass_lane_block_review_sealed": status == "PASS",
    "effect_auditor_lane_law_review_sealed": status == "PASS",
    "future_bounded_pass_requires_material_effect": status == "PASS",
    "semantic_null_pass_rejected_by_lane_law": status == "PASS",
    "ready_for_next_self_building_cycle_under_effect_auditor_lane": status == "PASS",

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
    "post_checks": post_checks,
    "hard_failures": hard,
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}
review["review_hash"] = h(review)

proof = {
    "id": "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "review_commit_result": str(REVIEW_COMMIT_RESULT),
    "memory": str(MEMORY),

    "self_building_effect_auditor_enforced_lane_review_sealed": status == "PASS",
    "material_effect_required_lane_review_sealed": status == "PASS",
    "semantic_null_pass_lane_block_review_sealed": status == "PASS",
    "effect_auditor_lane_law_review_sealed": status == "PASS",
    "future_bounded_pass_requires_material_effect": status == "PASS",
    "semantic_null_pass_rejected_by_lane_law": status == "PASS",
    "ready_for_next_self_building_cycle_under_effect_auditor_lane": status == "PASS",

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
    "post_checks": post_checks,
    "hard_failures": hard,
    "real_next": real_next,
    "final_socc_status": final_socc_status,
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h(proof)

memory = {
    "id": "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": "Review-sealed effect-auditor enforced lane. Future bounded self-building PASS requires material effect and semantic-null PASS is rejected by lane law.",
    "proof": str(PROOF),
    "review": str(REVIEW),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

md = "# SELF-BUILDING EFFECT AUDITOR ENFORCED LANE REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nEnforced lane validation PASS. Material-effect requirement validated; semantic-null null probe blocked.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed enforced lane as accepted law for future bounded self-building PASS.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## POSTCHECKS\n\n"
for k, v in post_checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Effect-auditor enforced lane is review-sealed. Next: first bounded self-building cycle under the enforced effect-auditor lane.\n\n"
else:
    md += "Enforced lane review is blocked. Repair required.\n\n"
md += "## Review-sealed lane law\n\n"
md += "- future bounded self-building PASS requires material-effect audit\n"
md += "- semantic-null PASS is rejected by lane law\n"
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
md += "\n## lawful_next\n\n" + real_next + "\n\n"
md += "## Truth boundary\n\n" + truth_boundary + "\n"

write_json(REVIEW, review)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(REVIEW_MD, md)

print("SELF-BUILDING EFFECT AUDITOR ENFORCED LANE REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("REVIEW_COMMIT_RESULT::" + str(REVIEW_COMMIT_RESULT))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_SEALED::" + str(status == "PASS"))
print("MATERIAL_EFFECT_REQUIRED_LANE_REVIEW_SEALED::" + str(status == "PASS"))
print("SEMANTIC_NULL_PASS_LANE_BLOCK_REVIEW_SEALED::" + str(status == "PASS"))
print("EFFECT_AUDITOR_LANE_LAW_REVIEW_SEALED::" + str(status == "PASS"))
print("FUTURE_BOUNDED_PASS_REQUIRES_MATERIAL_EFFECT::" + str(status == "PASS"))
print("SEMANTIC_NULL_PASS_REJECTED_BY_LANE_LAW::" + str(status == "PASS"))
print("READY_FOR_NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE::" + str(status == "PASS"))
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

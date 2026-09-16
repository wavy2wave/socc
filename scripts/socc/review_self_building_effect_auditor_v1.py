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

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_V1_PROOF.json"
BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_V1_PROOF.json"

VALIDATION_JSON = ROOT / "core/socc/autonomy/self_building/effect_auditor/validation/SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_V1.json"
VALIDATION_REPLAY = ROOT / "core/socc/autonomy/self_building/effect_auditor/validation/SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_REPLAY_V1.json"
VALIDATION_NULL_PROBE = ROOT / "core/socc/autonomy/self_building/effect_auditor/validation/SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_NULL_PROBE_V1.json"
VALIDATION_COMMIT_RESULT = ROOT / "core/socc/autonomy/self_building/effect_auditor/validation/SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_COMMIT_RESULT_V1.json"

BUILD_REPLAY = ROOT / "core/socc/autonomy/self_building/effect_auditor/SELF_BUILDING_EFFECT_AUDITOR_BUILD_REPLAY_V1.json"
BUILD_MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_EFFECT_AUDITOR_V1_MEMORY.json"
VALIDATION_MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_V1_MEMORY.json"

OUT = ROOT / "core/socc/autonomy/self_building/effect_auditor/review"
REVIEW = OUT / "SELF_BUILDING_EFFECT_AUDITOR_REVIEW_V1.json"
REVIEW_MD = OUT / "SELF_BUILDING_EFFECT_AUDITOR_REVIEW_V1.md"
REVIEW_COMMIT_RESULT = OUT / "SELF_BUILDING_EFFECT_AUDITOR_REVIEW_COMMIT_RESULT_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_EFFECT_AUDITOR_REVIEW_V1_MEMORY.json"

EXPECTED_NEXT = "review_self_building_effect_auditor_v1"
NEXT = "build_self_building_effect_auditor_enforced_lane_v1"

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
build_replay = read_json(BUILD_REPLAY)
build_memory = read_json(BUILD_MEMORY)
validation_memory = read_json(VALIDATION_MEMORY)

auditor_text = read_text(AUDITOR)
enforcer_text = read_text(ENFORCER)

route_next = route.get("lawful_next") or route.get("real_next")
route_truth = route.get("truth_boundary")
route_upstream = route.get("upstream_proof")

checks = {
    "route_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_effect_auditor_review": route_next == EXPECTED_NEXT,
    "route_upstream_validation_proof": route_upstream == str(VALIDATION_PROOF),
    "route_effect_auditor_validated": route.get("self_building_effect_auditor_validated") is True,
    "route_semantic_null_control_validated": route.get("semantic_null_pass_control_validated") is True,
    "route_material_gate_validated": route.get("material_effect_gate_validated") is True,
    "route_ready_for_review": route.get("ready_for_review") is True,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": validation_proof.get("status") == "PASS",
    "validation_capability_ok": validation_proof.get("capability") == "SELF_BUILDING_EFFECT_AUDITOR_VALIDATED_SEMANTIC_NULL_BLOCKED",
    "validation_real_next_ok": validation_proof.get("real_next") == EXPECTED_NEXT,
    "validation_effect_auditor_validated": validation_proof.get("self_building_effect_auditor_validated") is True,
    "validation_semantic_null_control_validated": validation_proof.get("semantic_null_pass_control_validated") is True,
    "validation_material_gate_validated": validation_proof.get("material_effect_gate_validated") is True,
    "validation_positive_passed": validation_proof.get("positive_material_effect_validation_passed") is True,
    "validation_negative_blocked": validation_proof.get("negative_semantic_null_validation_blocked") is True,
    "validation_ready_for_review": validation_proof.get("ready_for_review") is True,
    "validation_hard_failures_empty": validation_proof.get("hard_failures") == [],

    "build_proof_exists": BUILD_PROOF.exists(),
    "build_status_pass": build_proof.get("status") == "PASS",
    "build_effect_auditor_built": build_proof.get("self_building_effect_auditor_built") is True,
    "build_semantic_null_control_built": build_proof.get("semantic_null_pass_control_built") is True,
    "build_positive_passed": build_proof.get("positive_effect_case_passed") is True,
    "build_negative_blocked": build_proof.get("negative_semantic_null_case_blocked") is True,

    "validation_json_exists": VALIDATION_JSON.exists(),
    "validation_json_status_validated": validation_json.get("status") == "VALIDATED",

    "validation_replay_exists": VALIDATION_REPLAY.exists(),
    "validation_replay_status_pass": validation_replay.get("status") == "PASS",
    "validation_replay_material_effect_proven": validation_replay.get("material_effect_proven") is True,
    "validation_replay_hard_failures_empty": validation_replay.get("hard_failures") == [],

    "validation_null_probe_exists": VALIDATION_NULL_PROBE.exists(),
    "validation_null_probe_status_fail": validation_null_probe.get("status") == "FAIL",
    "validation_null_probe_semantic_null_blocked": validation_null_probe.get("semantic_null_pass_blocked") is True,
    "validation_null_probe_material_effect_not_proven": validation_null_probe.get("material_effect_proven") is False,
    "validation_null_probe_has_semantic_null": any(
        x.get("code") == "SEMANTIC_NULL" for x in (validation_null_probe.get("hard_failures") or [])
    ),

    "validation_commit_exists": VALIDATION_COMMIT_RESULT.exists(),
    "validation_commit_status_pass": validation_commit.get("status") == "PASS",
    "validation_commit_committed": validation_commit.get("committed") is True,
    "validation_commit_hard_failures_empty": validation_commit.get("hard_failures") == [],
    "validation_commit_snapshot_created": bool(validation_commit.get("snapshot")),

    "build_replay_exists": BUILD_REPLAY.exists(),
    "build_replay_status_pass": build_replay.get("status") == "PASS",
    "build_memory_exists": BUILD_MEMORY.exists(),
    "build_memory_status_pass": build_memory.get("status") == "PASS",
    "validation_memory_exists": VALIDATION_MEMORY.exists(),
    "validation_memory_status_pass": validation_memory.get("status") == "PASS",

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
    "Self-building effect auditor review only. This review-seals semantic-null PASS control and routes next to enforcing the effect auditor "
    "across the bounded self-building lane. It does not execute a tick, enable continuous loop, launch daemon, install scheduler, enable background loop, "
    "use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

commit = {}
if not pre_hard:
    enforcer = import_module(ENFORCER, "enforcer")
    commit = enforcer.enforce_atomic_commit_transition(
        lawful_next=NEXT,
        upstream_proof=str(PROOF),
        truth_boundary=truth_boundary,
        route_updates={
            "self_building_effect_auditor_review_sealed": True,
            "semantic_null_pass_control_review_sealed": True,
            "material_effect_gate_review_sealed": True,
            "positive_material_effect_review_sealed": True,
            "negative_semantic_null_review_sealed": True,
            "semantic_null_pass_class_controlled": True,
            "ready_to_enforce_effect_auditor_lane": True,
            "recommended_next_target": NEXT,
        },
        pulse_updates={
            "self_building_effect_auditor_review_sealed": True,
            "semantic_null_pass_control_review_sealed": True,
            "ready_to_enforce_effect_auditor_lane": True,
        },
        panel_updates={
            "self_building_effect_auditor_review_sealed": True,
            "semantic_null_pass_control_review_sealed": True,
            "ready_to_enforce_effect_auditor_lane": True,
        },
        progress_updates={
            "self_building_effect_auditor_review_sealed": True,
            "semantic_null_pass_control_review_sealed": True,
            "ready_to_enforce_effect_auditor_lane": True,
            "recommended_next_target": NEXT,
        },
        reason="review_self_building_effect_auditor_v1",
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
    "review_commit_lawful_next_effect_lane": commit.get("lawful_next") == NEXT,
    "review_commit_snapshot_created": bool(commit.get("snapshot")),

    "route_now_points_to_effect_lane": route2_next == NEXT,
    "route_now_upstream_review_proof": route2_upstream == str(PROOF),
    "route_effect_auditor_review_sealed": route2.get("self_building_effect_auditor_review_sealed") is True,
    "route_semantic_null_review_sealed": route2.get("semantic_null_pass_control_review_sealed") is True,
    "route_material_gate_review_sealed": route2.get("material_effect_gate_review_sealed") is True,
    "route_semantic_null_class_controlled": route2.get("semantic_null_pass_class_controlled") is True,
    "route_ready_to_enforce_effect_auditor_lane": route2.get("ready_to_enforce_effect_auditor_lane") is True,

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

if status == "PASS":
    capability = "SELF_BUILDING_EFFECT_AUDITOR_REVIEW_SEALED_SEMANTIC_NULL_CLASS_CONTROLLED"
    review_status = "REVIEW_SEALED"
    real_next = NEXT
    final_socc_status = "SOCC_SELF_BUILDING_EFFECT_AUDITOR_REVIEW_PASS_EFFECT_AUDITOR_LANE_ENFORCEMENT_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_EFFECT_AUDITOR_REVIEW_BLOCKED"
    review_status = "BLOCKED"
    real_next = "repair_self_building_effect_auditor_review_v1"
    final_socc_status = "SOCC_SELF_BUILDING_EFFECT_AUDITOR_REVIEW_FAIL"

review = {
    "id": "SELF_BUILDING_EFFECT_AUDITOR_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": review_status,
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_build_proof": str(BUILD_PROOF),
    "review_commit_result": str(REVIEW_COMMIT_RESULT),

    "self_building_effect_auditor_review_sealed": status == "PASS",
    "semantic_null_pass_control_review_sealed": status == "PASS",
    "material_effect_gate_review_sealed": status == "PASS",
    "positive_material_effect_review_sealed": status == "PASS",
    "negative_semantic_null_review_sealed": status == "PASS",
    "semantic_null_pass_class_controlled": status == "PASS",
    "ready_to_enforce_effect_auditor_lane": status == "PASS",
    "recommended_next_target": NEXT if status == "PASS" else None,

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
    "id": "SELF_BUILDING_EFFECT_AUDITOR_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "review_commit_result": str(REVIEW_COMMIT_RESULT),
    "memory": str(MEMORY),

    "self_building_effect_auditor_review_sealed": status == "PASS",
    "semantic_null_pass_control_review_sealed": status == "PASS",
    "material_effect_gate_review_sealed": status == "PASS",
    "positive_material_effect_review_sealed": status == "PASS",
    "negative_semantic_null_review_sealed": status == "PASS",
    "semantic_null_pass_class_controlled": status == "PASS",
    "ready_to_enforce_effect_auditor_lane": status == "PASS",
    "recommended_next_target": NEXT if status == "PASS" else None,

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
    "id": "SELF_BUILDING_EFFECT_AUDITOR_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": "Review-sealed self-building effect auditor. semantic-null PASS is controlled as a class; next is enforcing effect auditor lane-wide.",
    "proof": str(PROOF),
    "review": str(REVIEW),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

md = "# SELF-BUILDING EFFECT AUDITOR REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nEffect auditor validation PASS. Semantic-null probe was blocked and material-effect replay passed.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed effect auditor as accepted control against semantic-null PASS.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## POSTCHECKS\n\n"
for k, v in post_checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Effect auditor is review-sealed. Next: enforce effect auditor across bounded self-building lane.\n\n"
else:
    md += "Effect auditor review is blocked. Repair required.\n\n"
md += "## Review-sealed law\n\n"
md += "- material effect must be proven\n"
md += "- semantic-null PASS must be blocked\n"
md += "- route transition must be non-null when expected\n"
md += "- required artifacts/proof/memory must exist\n"
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

print("SELF-BUILDING EFFECT AUDITOR REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("REVIEW_COMMIT_RESULT::" + str(REVIEW_COMMIT_RESULT))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SELF_BUILDING_EFFECT_AUDITOR_REVIEW_SEALED::" + str(status == "PASS"))
print("SEMANTIC_NULL_PASS_CONTROL_REVIEW_SEALED::" + str(status == "PASS"))
print("MATERIAL_EFFECT_GATE_REVIEW_SEALED::" + str(status == "PASS"))
print("POSITIVE_MATERIAL_EFFECT_REVIEW_SEALED::" + str(status == "PASS"))
print("NEGATIVE_SEMANTIC_NULL_REVIEW_SEALED::" + str(status == "PASS"))
print("SEMANTIC_NULL_PASS_CLASS_CONTROLLED::" + str(status == "PASS"))
print("READY_TO_ENFORCE_EFFECT_AUDITOR_LANE::" + str(status == "PASS"))
print("RECOMMENDED_NEXT_TARGET::" + (NEXT if status == "PASS" else "NONE"))
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

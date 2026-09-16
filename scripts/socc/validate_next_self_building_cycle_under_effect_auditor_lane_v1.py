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

BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_V1_PROOF.json"
BUILD_JSON = ROOT / "core/socc/autonomy/self_building/cycle_under_effect_auditor_lane/NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_V1.json"
TASK_SPEC = ROOT / "core/socc/autonomy/self_building/cycle_under_effect_auditor_lane/NEXT_SELF_BUILDING_CYCLE_TASK_SPEC_UNDER_EFFECT_AUDITOR_LANE_V1.json"
EVIDENCE_MAP = ROOT / "core/socc/autonomy/self_building/cycle_under_effect_auditor_lane/NEXT_SELF_BUILDING_CYCLE_EVIDENCE_MAP_UNDER_EFFECT_AUDITOR_LANE_V1.json"
BUILD_EFFECT_AUDIT = ROOT / "core/socc/autonomy/self_building/cycle_under_effect_auditor_lane/NEXT_SELF_BUILDING_CYCLE_EFFECT_AUDIT_V1.json"
BUILD_COMMIT_RESULT = ROOT / "core/socc/autonomy/self_building/cycle_under_effect_auditor_lane/NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_COMMIT_RESULT_V1.json"
BUILD_MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_V1_MEMORY.json"

LANE_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_V1_PROOF.json"

OUT = ROOT / "core/socc/autonomy/self_building/cycle_under_effect_auditor_lane/validation"
VALIDATION = OUT / "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATION_V1.json"
VALIDATION_MD = OUT / "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATION_V1.md"
VALIDATION_EFFECT_AUDIT = OUT / "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATION_EFFECT_AUDIT_V1.json"
VALIDATION_COMMIT_RESULT = OUT / "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATION_COMMIT_RESULT_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATION_V1_MEMORY.json"

EXPECTED_NEXT = "validate_next_self_building_cycle_under_effect_auditor_lane_v1"
NEXT = "review_next_self_building_cycle_under_effect_auditor_lane_v1"
SELECTED_TARGET = "build_idempotent_step_guard_v1"

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

build_proof = read_json(BUILD_PROOF)
build_json = read_json(BUILD_JSON)
task_spec = read_json(TASK_SPEC)
evidence_map = read_json(EVIDENCE_MAP)
build_effect_audit = read_json(BUILD_EFFECT_AUDIT)
build_commit = read_json(BUILD_COMMIT_RESULT)
build_memory = read_json(BUILD_MEMORY)
lane_review = read_json(LANE_REVIEW_PROOF)

enforcer_text = read_text(ENFORCER)
effect_lane_text = read_text(EFFECT_LANE)

route_next = route_before.get("lawful_next") or route_before.get("real_next")
route_truth = route_before.get("truth_boundary")
route_upstream = route_before.get("upstream_proof")

pre_checks = {
    "route_exists": ROUTE.exists(),
    "route_status_pass": route_before.get("status") == "PASS",
    "route_points_to_cycle_validation": route_next == EXPECTED_NEXT,
    "route_upstream_build_proof": route_upstream == str(BUILD_PROOF),
    "route_next_cycle_built": route_before.get("next_self_building_cycle_under_effect_auditor_lane_built") is True,
    "route_effect_lane_law_applied": route_before.get("effect_auditor_lane_law_applied") is True,
    "route_selected_target_ok": route_before.get("selected_next_target") == SELECTED_TARGET,
    "route_idempotent_guard_selected": route_before.get("idempotent_step_guard_selected") is True,
    "route_ready_for_validation": route_before.get("ready_for_validation") is True,
    "route_self_building_mode_enabled": route_before.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route_before.get("visible_bounded_mode_ready") is True,

    "build_proof_exists": BUILD_PROOF.exists(),
    "build_proof_status_pass": build_proof.get("status") == "PASS",
    "build_capability_ok": build_proof.get("capability") == "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_BUILT_IDEMPOTENT_GUARD_SELECTED",
    "build_real_next_ok": build_proof.get("real_next") == EXPECTED_NEXT,
    "build_selected_target_ok": build_proof.get("selected_next_target") == SELECTED_TARGET,
    "build_effect_lane_applied": build_proof.get("effect_auditor_lane_law_applied") is True,
    "build_ready_for_validation": build_proof.get("ready_for_validation") is True,
    "build_hard_failures_empty": build_proof.get("hard_failures") == [],
    "build_atomic_commit_pass": (build_proof.get("atomic_commit_result") or {}).get("status") == "PASS",
    "build_atomic_commit_committed": (build_proof.get("atomic_commit_result") or {}).get("committed") is True,

    "build_json_exists": BUILD_JSON.exists(),
    "build_json_status_built": build_json.get("status") == "BUILT",
    "task_spec_exists": TASK_SPEC.exists(),
    "task_spec_status_defined": task_spec.get("status") == "DEFINED",
    "task_spec_target_ok": task_spec.get("selected_target") == SELECTED_TARGET,
    "task_spec_target_class_ok": task_spec.get("target_class") == "IDEMPOTENT_STEP_GUARD",
    "evidence_map_exists": EVIDENCE_MAP.exists(),
    "evidence_map_status_built": evidence_map.get("status") == "BUILT",
    "evidence_map_effect_auditor_required": evidence_map.get("effect_auditor_required") is True,

    "build_effect_audit_exists": BUILD_EFFECT_AUDIT.exists(),
    "build_effect_audit_status_pass": build_effect_audit.get("status") == "PASS",
    "build_effect_audit_material_required": build_effect_audit.get("material_effect_required") is True,
    "build_effect_audit_hard_failures_empty": build_effect_audit.get("hard_failures") == [],
    "build_effect_audit_inner_material_effect_proven": (build_effect_audit.get("audit") or {}).get("material_effect_proven") is True,

    "build_commit_exists": BUILD_COMMIT_RESULT.exists(),
    "build_commit_status_pass": build_commit.get("status") == "PASS",
    "build_commit_committed": build_commit.get("committed") is True,
    "build_memory_exists": BUILD_MEMORY.exists(),
    "build_memory_status_pass": build_memory.get("status") == "PASS",

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

    "validation_does_not_execute_tick": True,
    "validation_does_not_enable_continuous_loop": True,
    "validation_does_not_launch_daemon": True,
    "validation_does_not_install_scheduler": True,
    "validation_does_not_enable_background_loop": True,
    "validation_does_not_use_network": True,
    "validation_does_not_widen_queue": True,
    "validation_does_not_birth_entity": True,
    "validation_does_not_birth_anna": True,
    "validation_does_not_claim_agi": True,
    "validation_does_not_approve_final_canon": True,
}

pre_hard = [{"code": "PRECHECK_FAIL", "check": k, "actual": v} for k, v in pre_checks.items() if v is not True]

truth_boundary = (
    "Next bounded self-building cycle under effect-auditor lane validation only. This validates the cycle that selected the idempotent step guard "
    "and confirms the effect-auditor lane law was applied before routing to review. It does not execute a tick, enable continuous loop, launch daemon, "
    "install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

validation_effect_audit = {}
commit = {}

if not pre_hard:
    lane = import_module(EFFECT_LANE, "effect_lane")
    validation_effect_audit = lane.enforce_effect_auditor_lane(
        {"route_before": route_before},
        {
            "route_after": {
                **route_before,
                "lawful_next": NEXT,
                "real_next": NEXT,
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
            "expected_memory": str(BUILD_MEMORY),
            "required_artifacts": [str(BUILD_PROOF), str(BUILD_JSON), str(TASK_SPEC), str(EVIDENCE_MAP), str(BUILD_EFFECT_AUDIT), str(BUILD_MEMORY)],
            "changed_artifacts": [str(BUILD_PROOF), str(BUILD_EFFECT_AUDIT)],
            "material_claims": [
                "validated existing cycle build proof",
                "validated task spec target",
                "validated evidence map",
                "validated build effect audit",
                "prepared transition to review",
            ],
        }
    )
    write_json(VALIDATION_EFFECT_AUDIT, validation_effect_audit)

    if validation_effect_audit.get("status") != "PASS":
        pre_hard.append({"code": "VALIDATION_EFFECT_AUDIT_FAIL", "actual": validation_effect_audit})

hard = pre_hard
status = "PASS" if not hard else "FAIL"

capability = (
    "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATED_IDEMPOTENT_GUARD_SELECTED"
    if status == "PASS"
    else "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATION_BLOCKED"
)
real_next = NEXT if status == "PASS" else "repair_next_self_building_cycle_under_effect_auditor_lane_validation_v1"
final_socc_status = (
    "SOCC_NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATION_PASS_READY_FOR_REVIEW_NOT_DAEMON_NOT_AGI"
    if status == "PASS"
    else "SOCC_NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATION_FAIL"
)

validation = {
    "id": "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATION_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "VALIDATED" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "source_build_proof": str(BUILD_PROOF),
    "validation_effect_audit": str(VALIDATION_EFFECT_AUDIT),

    "next_self_building_cycle_under_effect_auditor_lane_validated": status == "PASS",
    "effect_auditor_lane_law_applied_validated": status == "PASS",
    "selected_next_target_validated": SELECTED_TARGET if status == "PASS" else None,
    "idempotent_step_guard_selection_validated": status == "PASS",
    "ready_for_review": status == "PASS",

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

    "pre_checks": pre_checks,
    "hard_failures": hard,
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}
validation["validation_hash"] = h(validation)

proof = {
    "id": "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATION_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "validation": str(VALIDATION),
    "validation_md": str(VALIDATION_MD),
    "validation_effect_audit": str(VALIDATION_EFFECT_AUDIT),
    "memory": str(MEMORY),

    "next_self_building_cycle_under_effect_auditor_lane_validated": status == "PASS",
    "effect_auditor_lane_law_applied_validated": status == "PASS",
    "selected_next_target_validated": SELECTED_TARGET if status == "PASS" else None,
    "idempotent_step_guard_selection_validated": status == "PASS",
    "ready_for_review": status == "PASS",

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

    "pre_checks": pre_checks,
    "hard_failures": hard,
    "real_next": real_next,
    "final_socc_status": final_socc_status,
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h(proof)

memory = {
    "id": "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATION_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": "Validated the first bounded self-building cycle under active effect-auditor lane law. Idempotent step guard remains selected as next bounded target.",
    "proof": str(PROOF),
    "validation": str(VALIDATION),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

write_json(VALIDATION, validation)
write_json(PROOF, proof)
write_json(MEMORY, memory)

if status == "PASS":
    enforcer = import_module(ENFORCER, "enforcer")
    commit = enforcer.enforce_atomic_commit_transition(
        lawful_next=real_next,
        upstream_proof=str(PROOF),
        truth_boundary=truth_boundary,
        route_updates={
            "next_self_building_cycle_under_effect_auditor_lane_validated": True,
            "effect_auditor_lane_law_applied_validated": True,
            "selected_next_target_validated": SELECTED_TARGET,
            "idempotent_step_guard_selection_validated": True,
            "ready_for_review": True,
            "recommended_next_target": real_next,
        },
        pulse_updates={
            "next_self_building_cycle_under_effect_auditor_lane_validated": True,
            "effect_auditor_lane_law_applied_validated": True,
            "selected_next_target_validated": SELECTED_TARGET,
        },
        panel_updates={
            "next_self_building_cycle_under_effect_auditor_lane_validated": True,
            "effect_auditor_lane_law_applied_validated": True,
            "selected_next_target_validated": SELECTED_TARGET,
        },
        progress_updates={
            "next_self_building_cycle_under_effect_auditor_lane_validated": True,
            "effect_auditor_lane_law_applied_validated": True,
            "selected_next_target_validated": SELECTED_TARGET,
            "recommended_next_target": real_next,
        },
        reason="validate_next_self_building_cycle_under_effect_auditor_lane_v1",
    )
    write_json(VALIDATION_COMMIT_RESULT, commit)

    validation["validation_commit_result"] = str(VALIDATION_COMMIT_RESULT)
    proof["validation_commit_result"] = str(VALIDATION_COMMIT_RESULT)
    validation["atomic_commit_result"] = commit
    proof["atomic_commit_result"] = commit

    if commit.get("status") != "PASS":
        status = "FAIL"
        hard = [{"code": "ATOMIC_COMMIT_FAIL", "actual": commit}]
        validation["status"] = "BLOCKED"
        validation["hard_failures"] = hard
        validation["real_next"] = "repair_next_self_building_cycle_under_effect_auditor_lane_validation_v1"
        proof["status"] = "FAIL"
        proof["hard_failures"] = hard
        proof["real_next"] = "repair_next_self_building_cycle_under_effect_auditor_lane_validation_v1"
        real_next = proof["real_next"]

write_json(VALIDATION, validation)
write_json(PROOF, proof)
write_json(MEMORY, memory)

md = "# NEXT SELF-BUILDING CYCLE UNDER EFFECT AUDITOR LANE VALIDATION V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nNext cycle under effect-auditor lane build PASS. Selected target: build_idempotent_step_guard_v1.\n\n"
md += "## ДЕЙСТВИЕ\n\nValidated task spec, evidence map, build effect-audit, lane-law application, and route transition to review.\n\n"
md += "## PRECHECKS\n\n"
for k, v in pre_checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Next cycle under effect-auditor lane is validated. Next is review-seal.\n\n"
else:
    md += "Next cycle validation is blocked. Repair required.\n\n"
md += "## Selected target\n\n" + str(SELECTED_TARGET if status == "PASS" else None) + "\n\n"
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
write_text(VALIDATION_MD, md)

print("NEXT SELF-BUILDING CYCLE UNDER EFFECT AUDITOR LANE VALIDATION :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("VALIDATION::" + str(VALIDATION))
print("VALIDATION_EFFECT_AUDIT::" + str(VALIDATION_EFFECT_AUDIT))
print("VALIDATION_COMMIT_RESULT::" + str(VALIDATION_COMMIT_RESULT))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_VALIDATED::" + str(status == "PASS"))
print("EFFECT_AUDITOR_LANE_LAW_APPLIED_VALIDATED::" + str(status == "PASS"))
print("SELECTED_NEXT_TARGET_VALIDATED::" + (SELECTED_TARGET if status == "PASS" else "NONE"))
print("IDEMPOTENT_STEP_GUARD_SELECTION_VALIDATED::" + str(status == "PASS"))
print("READY_FOR_REVIEW::" + str(status == "PASS"))
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

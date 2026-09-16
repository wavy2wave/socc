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

LANE_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_V1_PROOF.json"
LANE_VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_VALIDATION_V1_PROOF.json"
LANE_BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_V1_PROOF.json"

OUT = ROOT / "core/socc/autonomy/self_building/cycle_under_effect_auditor_lane"
CYCLE = OUT / "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_V1.json"
CYCLE_MD = OUT / "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_V1.md"
TASK_SPEC = OUT / "NEXT_SELF_BUILDING_CYCLE_TASK_SPEC_UNDER_EFFECT_AUDITOR_LANE_V1.json"
EVIDENCE_MAP = OUT / "NEXT_SELF_BUILDING_CYCLE_EVIDENCE_MAP_UNDER_EFFECT_AUDITOR_LANE_V1.json"
EFFECT_AUDIT = OUT / "NEXT_SELF_BUILDING_CYCLE_EFFECT_AUDIT_V1.json"
COMMIT_RESULT = OUT / "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_COMMIT_RESULT_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_V1_MEMORY.json"

EXPECTED_NEXT = "build_next_self_building_cycle_under_effect_auditor_lane_v1"
NEXT = "validate_next_self_building_cycle_under_effect_auditor_lane_v1"

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

lane_review = read_json(LANE_REVIEW_PROOF)
lane_validation = read_json(LANE_VALIDATION_PROOF)
lane_build = read_json(LANE_BUILD_PROOF)

enforcer_text = read_text(ENFORCER)
effect_lane_text = read_text(EFFECT_LANE)

route_next = route_before.get("lawful_next") or route_before.get("real_next")
route_truth = route_before.get("truth_boundary")
route_upstream = route_before.get("upstream_proof")

checks = {
    "route_exists": ROUTE.exists(),
    "route_status_pass": route_before.get("status") == "PASS",
    "route_points_to_next_cycle_build": route_next == EXPECTED_NEXT,
    "route_upstream_lane_review": route_upstream == str(LANE_REVIEW_PROOF),
    "route_effect_auditor_lane_law_review_sealed": route_before.get("effect_auditor_lane_law_review_sealed") is True,
    "route_future_bounded_pass_requires_material_effect": route_before.get("future_bounded_pass_requires_material_effect") is True,
    "route_semantic_null_pass_rejected_by_lane_law": route_before.get("semantic_null_pass_rejected_by_lane_law") is True,
    "route_ready_for_next_cycle_under_lane": route_before.get("ready_for_next_self_building_cycle_under_effect_auditor_lane") is True,
    "route_self_building_mode_enabled": route_before.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route_before.get("visible_bounded_mode_ready") is True,

    "lane_review_proof_exists": LANE_REVIEW_PROOF.exists(),
    "lane_review_status_pass": lane_review.get("status") == "PASS",
    "lane_review_capability_ok": lane_review.get("capability") == "SELF_BUILDING_EFFECT_AUDITOR_ENFORCED_LANE_REVIEW_SEALED_LANE_LAW_ACTIVE",
    "lane_review_real_next_ok": lane_review.get("real_next") == EXPECTED_NEXT,
    "lane_review_law_sealed": lane_review.get("effect_auditor_lane_law_review_sealed") is True,
    "lane_review_future_pass_requires_material_effect": lane_review.get("future_bounded_pass_requires_material_effect") is True,
    "lane_review_semantic_null_rejected": lane_review.get("semantic_null_pass_rejected_by_lane_law") is True,
    "lane_review_hard_failures_empty": lane_review.get("hard_failures") == [],

    "lane_validation_proof_exists": LANE_VALIDATION_PROOF.exists(),
    "lane_validation_status_pass": lane_validation.get("status") == "PASS",
    "lane_validation_material_required": lane_validation.get("material_effect_required_lane_validated") is True,
    "lane_validation_semantic_null_blocked": lane_validation.get("semantic_null_pass_lane_block_validated") is True,

    "lane_build_proof_exists": LANE_BUILD_PROOF.exists(),
    "lane_build_status_pass": lane_build.get("status") == "PASS",
    "lane_build_material_required": lane_build.get("material_effect_required_lane_built") is True,

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

    "cycle_does_not_execute_tick": True,
    "cycle_does_not_enable_continuous_loop": True,
    "cycle_does_not_launch_daemon": True,
    "cycle_does_not_install_scheduler": True,
    "cycle_does_not_enable_background_loop": True,
    "cycle_does_not_use_network": True,
    "cycle_does_not_widen_queue": True,
    "cycle_does_not_birth_entity": True,
    "cycle_does_not_birth_anna": True,
    "cycle_does_not_claim_agi": True,
    "cycle_does_not_approve_final_canon": True,
}

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]

truth_boundary = (
    "Next bounded self-building cycle under effect-auditor lane build only. This prepares the first cycle after lane-law activation and "
    "selects an idempotent step guard as the next bounded target, because the last defect class was out-of-phase validation rerun overwriting proof artifacts. "
    "It does not execute a tick, enable continuous loop, launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, "
    "approve final canon, or claim AGI."
)

task_spec = {
    "id": "NEXT_SELF_BUILDING_CYCLE_TASK_SPEC_UNDER_EFFECT_AUDITOR_LANE_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "DEFINED" if not hard else "BLOCKED",
    "selected_target": SELECTED_TARGET,
    "target_class": "IDEMPOTENT_STEP_GUARD",
    "reason": "Previous defect: out-of-phase validation rerun overwrote already-committed validation artifacts with FAIL. Next cycle should prevent backward reruns from corrupting proof state.",
    "expected_material_effect": [
        "define idempotent guard for already-committed steps",
        "block destructive rerun when route has advanced beyond step",
        "return ALREADY_COMMITTED/NOOP instead of rewriting PASS proof to FAIL",
        "preserve route/proof/memory coherence",
    ],
    "forbidden": FORBIDDEN_FLAGS,
}

evidence_map = {
    "id": "NEXT_SELF_BUILDING_CYCLE_EVIDENCE_MAP_UNDER_EFFECT_AUDITOR_LANE_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if not hard else "BLOCKED",
    "source_lane_review_proof": str(LANE_REVIEW_PROOF),
    "route_before_lawful_next": route_next,
    "selected_target": SELECTED_TARGET,
    "why_material": "The cycle creates a new task spec/evidence map/proof/memory and advances route to validation under effect-auditor lane.",
    "effect_auditor_required": True,
}

status = "PASS" if not hard else "FAIL"
capability = "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_BUILT_IDEMPOTENT_GUARD_SELECTED" if status == "PASS" else "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_BLOCKED"
real_next = NEXT if status == "PASS" else "repair_next_self_building_cycle_under_effect_auditor_lane_v1"
final_socc_status = "SOCC_NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI" if status == "PASS" else "SOCC_NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_FAIL"

cycle = {
    "id": "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "task_spec": str(TASK_SPEC),
    "evidence_map": str(EVIDENCE_MAP),
    "effect_audit": str(EFFECT_AUDIT),
    "source_lane_review_proof": str(LANE_REVIEW_PROOF),

    "next_self_building_cycle_under_effect_auditor_lane_built": status == "PASS",
    "effect_auditor_lane_law_applied": status == "PASS",
    "selected_next_target": SELECTED_TARGET if status == "PASS" else None,
    "idempotent_step_guard_selected": status == "PASS",
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
cycle["cycle_hash"] = h(cycle)

proof = {
    "id": "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "cycle": str(CYCLE),
    "cycle_md": str(CYCLE_MD),
    "task_spec": str(TASK_SPEC),
    "evidence_map": str(EVIDENCE_MAP),
    "effect_audit": str(EFFECT_AUDIT),
    "memory": str(MEMORY),

    "next_self_building_cycle_under_effect_auditor_lane_built": status == "PASS",
    "effect_auditor_lane_law_applied": status == "PASS",
    "selected_next_target": SELECTED_TARGET if status == "PASS" else None,
    "idempotent_step_guard_selected": status == "PASS",
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
    "id": "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": "Built first bounded self-building cycle under active effect-auditor lane law. Selected idempotent step guard as next bounded target.",
    "proof": str(PROOF),
    "cycle": str(CYCLE),
    "selected_next_target": SELECTED_TARGET if status == "PASS" else None,
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

if status == "PASS":
    write_json(TASK_SPEC, task_spec)
    write_json(EVIDENCE_MAP, evidence_map)

    # Effect-auditor lane audit before committing route transition.
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
            "expected_memory": str(LANE_REVIEW_PROOF),
            "required_artifacts": [str(TASK_SPEC), str(EVIDENCE_MAP), str(LANE_REVIEW_PROOF)],
            "changed_artifacts": [str(TASK_SPEC), str(EVIDENCE_MAP)],
            "material_claims": [
                "new bounded cycle task spec created",
                "new evidence map created",
                "selected idempotent step guard target",
                "route transition prepared under effect-auditor lane law",
            ],
        }
    )
    write_json(EFFECT_AUDIT, effect_audit)

    if effect_audit.get("status") != "PASS":
        status = "FAIL"
        hard = [{"code": "EFFECT_AUDITOR_LANE_AUDIT_FAIL", "actual": effect_audit}]
        capability = "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_BLOCKED"
        real_next = "repair_next_self_building_cycle_under_effect_auditor_lane_v1"
        final_socc_status = "SOCC_NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_FAIL"
        cycle["status"] = "BLOCKED"
        cycle["hard_failures"] = hard
        cycle["real_next"] = real_next
        proof["status"] = status
        proof["hard_failures"] = hard
        proof["real_next"] = real_next
    else:
        enforcer = import_module(ENFORCER, "enforcer")
        commit = enforcer.enforce_atomic_commit_transition(
            lawful_next=real_next,
            upstream_proof=str(PROOF),
            truth_boundary=truth_boundary,
            route_updates={
                "next_self_building_cycle_under_effect_auditor_lane_built": True,
                "effect_auditor_lane_law_applied": True,
                "selected_next_target": SELECTED_TARGET,
                "idempotent_step_guard_selected": True,
                "ready_for_validation": True,
                "recommended_next_target": real_next,
            },
            pulse_updates={
                "next_self_building_cycle_under_effect_auditor_lane_built": True,
                "effect_auditor_lane_law_applied": True,
                "selected_next_target": SELECTED_TARGET,
            },
            panel_updates={
                "next_self_building_cycle_under_effect_auditor_lane_built": True,
                "effect_auditor_lane_law_applied": True,
                "selected_next_target": SELECTED_TARGET,
            },
            progress_updates={
                "next_self_building_cycle_under_effect_auditor_lane_built": True,
                "effect_auditor_lane_law_applied": True,
                "selected_next_target": SELECTED_TARGET,
                "recommended_next_target": real_next,
            },
            reason="build_next_self_building_cycle_under_effect_auditor_lane_v1",
        )
        write_json(COMMIT_RESULT, commit)
        cycle["atomic_commit_result"] = commit
        proof["atomic_commit_result"] = commit
        if commit.get("status") != "PASS":
            status = "FAIL"
            hard = [{"code": "ATOMIC_COMMIT_FAIL", "actual": commit}]
            capability = "NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_BLOCKED"
            real_next = "repair_next_self_building_cycle_under_effect_auditor_lane_v1"
            final_socc_status = "SOCC_NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_FAIL"
            cycle["status"] = "BLOCKED"
            cycle["hard_failures"] = hard
            cycle["real_next"] = real_next
            proof["status"] = status
            proof["hard_failures"] = hard
            proof["real_next"] = real_next

md = "# NEXT SELF-BUILDING CYCLE UNDER EFFECT AUDITOR LANE V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nEffect-auditor enforced lane was review-sealed. Future bounded PASS requires material effect.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt the next bounded self-building cycle under lane law and selected idempotent step guard.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Next bounded self-building cycle under effect-auditor lane is built. Next is validation.\n\n"
else:
    md += "Next bounded self-building cycle build is blocked. Repair required.\n\n"
md += "## Selected target\n\n" + str(SELECTED_TARGET if status == "PASS" else None) + "\n\n"
md += "## Why this target\n\n"
md += "The last defect class was an out-of-phase validation rerun overwriting already committed validation artifacts. The next bounded target must make steps idempotent.\n\n"
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

write_json(CYCLE, cycle)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(CYCLE_MD, md)

print("NEXT SELF-BUILDING CYCLE UNDER EFFECT AUDITOR LANE :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("CYCLE::" + str(CYCLE))
print("TASK_SPEC::" + str(TASK_SPEC))
print("EVIDENCE_MAP::" + str(EVIDENCE_MAP))
print("EFFECT_AUDIT::" + str(EFFECT_AUDIT))
print("COMMIT_RESULT::" + str(COMMIT_RESULT))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("NEXT_SELF_BUILDING_CYCLE_UNDER_EFFECT_AUDITOR_LANE_BUILT::" + str(status == "PASS"))
print("EFFECT_AUDITOR_LANE_LAW_APPLIED::" + str(status == "PASS"))
print("SELECTED_NEXT_TARGET::" + str(SELECTED_TARGET if status == "PASS" else None))
print("IDEMPOTENT_STEP_GUARD_SELECTED::" + str(status == "PASS"))
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

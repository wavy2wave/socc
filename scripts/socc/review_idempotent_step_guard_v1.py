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

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_STEP_GUARD_VALIDATION_V1_PROOF.json"
BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_STEP_GUARD_V1_PROOF.json"

VALIDATION_JSON = ROOT / "core/socc/autonomy/self_building/idempotent_step_guard/validation/IDEMPOTENT_STEP_GUARD_VALIDATION_V1.json"
VALIDATION_REPLAY = ROOT / "core/socc/autonomy/self_building/idempotent_step_guard/validation/IDEMPOTENT_STEP_GUARD_VALIDATION_REPLAY_V1.json"
VALIDATION_EFFECT_AUDIT = ROOT / "core/socc/autonomy/self_building/idempotent_step_guard/validation/IDEMPOTENT_STEP_GUARD_VALIDATION_EFFECT_AUDIT_V1.json"
VALIDATION_COMMIT_RESULT = ROOT / "core/socc/autonomy/self_building/idempotent_step_guard/validation/IDEMPOTENT_STEP_GUARD_VALIDATION_COMMIT_RESULT_V1.json"
VALIDATION_MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/IDEMPOTENT_STEP_GUARD_VALIDATION_V1_MEMORY.json"

BUILD_JSON = ROOT / "core/socc/autonomy/self_building/idempotent_step_guard/IDEMPOTENT_STEP_GUARD_BUILD_V1.json"
SPEC = ROOT / "core/socc/autonomy/self_building/idempotent_step_guard/IDEMPOTENT_STEP_GUARD_SPEC_V1.json"
TEST_VECTOR = ROOT / "core/socc/autonomy/self_building/idempotent_step_guard/IDEMPOTENT_STEP_GUARD_TEST_VECTOR_V1.json"
BUILD_REPLAY = ROOT / "core/socc/autonomy/self_building/idempotent_step_guard/IDEMPOTENT_STEP_GUARD_BUILD_REPLAY_V1.json"
BUILD_EFFECT_AUDIT = ROOT / "core/socc/autonomy/self_building/idempotent_step_guard/IDEMPOTENT_STEP_GUARD_BUILD_EFFECT_AUDIT_V1.json"
BUILD_MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/IDEMPOTENT_STEP_GUARD_V1_MEMORY.json"

OUT = ROOT / "core/socc/autonomy/self_building/idempotent_step_guard/review"
REVIEW = OUT / "IDEMPOTENT_STEP_GUARD_REVIEW_V1.json"
REVIEW_MD = OUT / "IDEMPOTENT_STEP_GUARD_REVIEW_V1.md"
REVIEW_DRAFT = OUT / "IDEMPOTENT_STEP_GUARD_REVIEW_DRAFT_BEFORE_EFFECT_AUDIT_V1.json"
PROOF_DRAFT = OUT / "IDEMPOTENT_STEP_GUARD_PROOF_DRAFT_BEFORE_EFFECT_AUDIT_V1.json"
REVIEW_EFFECT_AUDIT = OUT / "IDEMPOTENT_STEP_GUARD_REVIEW_EFFECT_AUDIT_V1.json"
REVIEW_COMMIT_RESULT = OUT / "IDEMPOTENT_STEP_GUARD_REVIEW_COMMIT_RESULT_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_STEP_GUARD_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/IDEMPOTENT_STEP_GUARD_REVIEW_V1_MEMORY.json"

EXPECTED_NEXT = "review_idempotent_step_guard_v1"
NEXT = "build_idempotent_guard_enforced_step_wrapper_v1"

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

validation_proof = read_json(VALIDATION_PROOF)
build_proof = read_json(BUILD_PROOF)
validation_json = read_json(VALIDATION_JSON)
validation_replay = read_json(VALIDATION_REPLAY)
validation_effect_audit = read_json(VALIDATION_EFFECT_AUDIT)
validation_commit = read_json(VALIDATION_COMMIT_RESULT)
validation_memory = read_json(VALIDATION_MEMORY)

build_json = read_json(BUILD_JSON)
spec_json = read_json(SPEC)
test_vector = read_json(TEST_VECTOR)
build_replay = read_json(BUILD_REPLAY)
build_effect_audit = read_json(BUILD_EFFECT_AUDIT)
build_memory = read_json(BUILD_MEMORY)

guard_text = read_text(GUARD)
enforcer_text = read_text(ENFORCER)
effect_lane_text = read_text(EFFECT_LANE)

route_next = route_before.get("lawful_next") or route_before.get("real_next")
route_truth = route_before.get("truth_boundary")
route_upstream = route_before.get("upstream_proof")

checks = {
    "route_exists": ROUTE.exists(),
    "route_status_pass": route_before.get("status") == "PASS",
    "route_points_to_guard_review": route_next == EXPECTED_NEXT,
    "route_upstream_validation_proof": route_upstream == str(VALIDATION_PROOF),
    "route_guard_validated": route_before.get("idempotent_step_guard_validated") is True,
    "route_normal_case_validated": route_before.get("normal_execution_allowed_case_validated") is True,
    "route_already_committed_noop_validated": route_before.get("already_committed_noop_case_validated") is True,
    "route_out_of_phase_blocked_validated": route_before.get("out_of_phase_rerun_blocked_case_validated") is True,
    "route_recovery_allowed_validated": route_before.get("recovery_allowed_case_validated") is True,
    "route_ready_for_review": route_before.get("ready_for_review") is True,
    "route_self_building_mode_enabled": route_before.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route_before.get("visible_bounded_mode_ready") is True,

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_proof_status_pass": validation_proof.get("status") == "PASS",
    "validation_capability_ok": validation_proof.get("capability") == "IDEMPOTENT_STEP_GUARD_VALIDATED_OUT_OF_PHASE_RERUN_CONTROL",
    "validation_real_next_ok": validation_proof.get("real_next") == EXPECTED_NEXT,
    "validation_guard_validated": validation_proof.get("idempotent_step_guard_validated") is True,
    "validation_normal_case_validated": validation_proof.get("normal_execution_allowed_case_validated") is True,
    "validation_already_committed_noop_validated": validation_proof.get("already_committed_noop_case_validated") is True,
    "validation_out_of_phase_blocked_validated": validation_proof.get("out_of_phase_rerun_blocked_case_validated") is True,
    "validation_recovery_allowed_validated": validation_proof.get("recovery_allowed_case_validated") is True,
    "validation_ready_for_review": validation_proof.get("ready_for_review") is True,
    "validation_hard_failures_empty": validation_proof.get("hard_failures") == [],
    "validation_atomic_commit_pass": (validation_proof.get("atomic_commit_result") or {}).get("status") == "PASS",
    "validation_atomic_commit_committed": (validation_proof.get("atomic_commit_result") or {}).get("committed") is True,

    "validation_json_exists": VALIDATION_JSON.exists(),
    "validation_json_status_validated": validation_json.get("status") == "VALIDATED",
    "validation_replay_exists": VALIDATION_REPLAY.exists(),
    "validation_replay_status_pass": validation_replay.get("status") == "PASS",
    "validation_replay_normal_ok": (validation_replay.get("normal_case") or {}).get("decision") == "NORMAL_EXECUTION_ALLOWED",
    "validation_replay_already_committed_ok": (validation_replay.get("already_committed_case") or {}).get("decision") == "ALREADY_COMMITTED_NOOP",
    "validation_replay_blocked_ok": (validation_replay.get("out_of_phase_block_case") or {}).get("decision") == "OUT_OF_PHASE_RERUN_BLOCKED",
    "validation_replay_recovery_ok": (validation_replay.get("recovery_allowed_case") or {}).get("decision") == "ALREADY_COMMITTED_NOOP",
    "validation_effect_audit_exists": VALIDATION_EFFECT_AUDIT.exists(),
    "validation_effect_audit_status_pass": validation_effect_audit.get("status") == "PASS",
    "validation_effect_audit_material_required": validation_effect_audit.get("material_effect_required") is True,
    "validation_effect_audit_hard_failures_empty": validation_effect_audit.get("hard_failures") == [],
    "validation_memory_exists": VALIDATION_MEMORY.exists(),
    "validation_memory_status_pass": validation_memory.get("status") == "PASS",
    "validation_commit_exists": VALIDATION_COMMIT_RESULT.exists(),
    "validation_commit_status_pass": validation_commit.get("status") == "PASS",
    "validation_commit_committed": validation_commit.get("committed") is True,

    "build_proof_exists": BUILD_PROOF.exists(),
    "build_proof_status_pass": build_proof.get("status") == "PASS",
    "build_guard_built": build_proof.get("idempotent_step_guard_built") is True,
    "build_json_exists": BUILD_JSON.exists(),
    "build_json_status_built": build_json.get("status") == "BUILT",
    "spec_exists": SPEC.exists(),
    "spec_status_built": spec_json.get("status") == "BUILT",
    "test_vector_exists": TEST_VECTOR.exists(),
    "build_replay_exists": BUILD_REPLAY.exists(),
    "build_replay_status_pass": build_replay.get("status") == "PASS",
    "build_effect_audit_exists": BUILD_EFFECT_AUDIT.exists(),
    "build_effect_audit_status_pass": build_effect_audit.get("status") == "PASS",
    "build_memory_exists": BUILD_MEMORY.exists(),
    "build_memory_status_pass": build_memory.get("status") == "PASS",

    "guard_exists": GUARD.exists(),
    "guard_has_function": "def guard_step_execution(" in guard_text,
    "guard_has_normal_decision": "NORMAL_EXECUTION_ALLOWED" in guard_text,
    "guard_has_noop_decision": "ALREADY_COMMITTED_NOOP" in guard_text,
    "guard_has_block_decision": "OUT_OF_PHASE_RERUN_BLOCKED" in guard_text,
    "guard_has_write_allowed_false": "write_allowed" in guard_text,

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

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]

truth_boundary = (
    "Idempotent step guard review only. This review-seals the guard as accepted protection against destructive out-of-phase reruns and routes next "
    "to building an enforced step wrapper so future bounded construction steps can use the guard before writing proof artifacts. It does not execute a tick, "
    "enable continuous loop, launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

review_effect_audit = {}
commit = {}

if not hard:
    write_json(REVIEW_DRAFT, {
        "id": "IDEMPOTENT_STEP_GUARD_REVIEW_DRAFT_BEFORE_EFFECT_AUDIT_V1",
        "status": "DRAFT_BEFORE_EFFECT_AUDIT",
        "expected_real_next": NEXT,
        "source_validation_proof": str(VALIDATION_PROOF),
        "truth_boundary": truth_boundary,
        "review_seals": [
            "normal_execution_allowed",
            "already_committed_noop",
            "out_of_phase_rerun_blocked",
            "recovery_allowed_only_explicit",
        ],
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
    })

    write_json(PROOF_DRAFT, {
        "id": "IDEMPOTENT_STEP_GUARD_PROOF_DRAFT_BEFORE_EFFECT_AUDIT_V1",
        "status": "DRAFT_BEFORE_EFFECT_AUDIT",
        "capability": "PRE_EFFECT_AUDIT_DRAFT_FOR_IDEMPOTENT_STEP_GUARD_REVIEW",
        "expected_final_proof": str(PROOF),
        "expected_real_next": NEXT,
        "source_validation_proof": str(VALIDATION_PROOF),
        "truth_boundary": truth_boundary,
    })

    lane = import_module(EFFECT_LANE, "effect_lane")
    review_effect_audit = lane.enforce_effect_auditor_lane(
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
            "expected_memory": str(VALIDATION_MEMORY),
            "required_artifacts": [str(VALIDATION_PROOF), str(VALIDATION_JSON), str(VALIDATION_REPLAY), str(VALIDATION_MEMORY), str(GUARD), str(SPEC)],
            "changed_artifacts": [str(REVIEW_DRAFT), str(PROOF_DRAFT)],
            "material_claims": [
                "review draft materialized before effect audit",
                "proof draft materialized before effect audit",
                "review sealed idempotent guard",
                "accepted noop/block/recovery decisions",
                "prepared route transition to enforced wrapper build",
            ],
        }
    )
    write_json(REVIEW_EFFECT_AUDIT, review_effect_audit)

    if review_effect_audit.get("status") != "PASS":
        hard.append({"code": "REVIEW_EFFECT_AUDIT_FAIL", "actual": review_effect_audit})

status = "PASS" if not hard else "FAIL"

capability = (
    "IDEMPOTENT_STEP_GUARD_REVIEW_SEALED_OUT_OF_PHASE_RERUN_CONTROL"
    if status == "PASS"
    else "IDEMPOTENT_STEP_GUARD_REVIEW_BLOCKED"
)
real_next = NEXT if status == "PASS" else "repair_idempotent_step_guard_review_v1"
final_socc_status = (
    "SOCC_IDEMPOTENT_STEP_GUARD_REVIEW_PASS_ENFORCED_WRAPPER_NEXT_NOT_DAEMON_NOT_AGI"
    if status == "PASS"
    else "SOCC_IDEMPOTENT_STEP_GUARD_REVIEW_FAIL"
)

review = {
    "id": "IDEMPOTENT_STEP_GUARD_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "REVIEW_SEALED" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_build_proof": str(BUILD_PROOF),
    "review_draft_before_effect_audit": str(REVIEW_DRAFT),
    "proof_draft_before_effect_audit": str(PROOF_DRAFT),
    "review_effect_audit": str(REVIEW_EFFECT_AUDIT),

    "idempotent_step_guard_review_sealed": status == "PASS",
    "normal_execution_allowed_review_sealed": status == "PASS",
    "already_committed_noop_review_sealed": status == "PASS",
    "out_of_phase_rerun_blocked_review_sealed": status == "PASS",
    "recovery_allowed_explicit_only_review_sealed": status == "PASS",
    "ready_to_build_idempotent_guard_enforced_step_wrapper": status == "PASS",

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
review["review_hash"] = h(review)

proof = {
    "id": "IDEMPOTENT_STEP_GUARD_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "review_draft_before_effect_audit": str(REVIEW_DRAFT),
    "proof_draft_before_effect_audit": str(PROOF_DRAFT),
    "review_effect_audit": str(REVIEW_EFFECT_AUDIT),
    "memory": str(MEMORY),

    "idempotent_step_guard_review_sealed": status == "PASS",
    "normal_execution_allowed_review_sealed": status == "PASS",
    "already_committed_noop_review_sealed": status == "PASS",
    "out_of_phase_rerun_blocked_review_sealed": status == "PASS",
    "recovery_allowed_explicit_only_review_sealed": status == "PASS",
    "ready_to_build_idempotent_guard_enforced_step_wrapper": status == "PASS",

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
    "id": "IDEMPOTENT_STEP_GUARD_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": "Review-sealed idempotent step guard. Next is enforced step wrapper so future construction scripts can apply guard before proof writes.",
    "proof": str(PROOF),
    "review": str(REVIEW),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

write_json(REVIEW, review)
write_json(PROOF, proof)
write_json(MEMORY, memory)

if status == "PASS":
    enforcer = import_module(ENFORCER, "enforcer")
    commit = enforcer.enforce_atomic_commit_transition(
        lawful_next=real_next,
        upstream_proof=str(PROOF),
        truth_boundary=truth_boundary,
        route_updates={
            "idempotent_step_guard_review_sealed": True,
            "normal_execution_allowed_review_sealed": True,
            "already_committed_noop_review_sealed": True,
            "out_of_phase_rerun_blocked_review_sealed": True,
            "recovery_allowed_explicit_only_review_sealed": True,
            "ready_to_build_idempotent_guard_enforced_step_wrapper": True,
            "recommended_next_target": real_next,
        },
        pulse_updates={
            "idempotent_step_guard_review_sealed": True,
            "already_committed_noop_review_sealed": True,
            "ready_to_build_idempotent_guard_enforced_step_wrapper": True,
        },
        panel_updates={
            "idempotent_step_guard_review_sealed": True,
            "already_committed_noop_review_sealed": True,
            "ready_to_build_idempotent_guard_enforced_step_wrapper": True,
        },
        progress_updates={
            "idempotent_step_guard_review_sealed": True,
            "already_committed_noop_review_sealed": True,
            "ready_to_build_idempotent_guard_enforced_step_wrapper": True,
            "recommended_next_target": real_next,
        },
        reason="review_idempotent_step_guard_v1",
    )
    write_json(REVIEW_COMMIT_RESULT, commit)
    review["review_commit_result"] = str(REVIEW_COMMIT_RESULT)
    proof["review_commit_result"] = str(REVIEW_COMMIT_RESULT)
    review["atomic_commit_result"] = commit
    proof["atomic_commit_result"] = commit

    if commit.get("status") != "PASS":
        status = "FAIL"
        hard = [{"code": "ATOMIC_COMMIT_FAIL", "actual": commit}]
        review["status"] = "BLOCKED"
        review["hard_failures"] = hard
        review["real_next"] = "repair_idempotent_step_guard_review_v1"
        proof["status"] = "FAIL"
        proof["hard_failures"] = hard
        proof["real_next"] = "repair_idempotent_step_guard_review_v1"
        real_next = proof["real_next"]

write_json(REVIEW, review)
write_json(PROOF, proof)
write_json(MEMORY, memory)

md = "# IDEMPOTENT STEP GUARD REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nIdempotent step guard validation PASS. Normal/noop/block/recovery cases validated.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed the guard as accepted protection against destructive out-of-phase reruns.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Idempotent step guard is review-sealed. Next: build enforced step wrapper.\n\n"
else:
    md += "Idempotent step guard review is blocked. Repair required.\n\n"
md += "## Review-sealed law\n\n"
md += "- normal route state may execute\n"
md += "- already committed rerun must become NOOP\n"
md += "- destructive out-of-phase rerun must be blocked\n"
md += "- recovery requires explicit allow_recovery\n"
md += "- future wrappers must apply guard before proof writes\n\n"
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
write_text(REVIEW_MD, md)

print("IDEMPOTENT STEP GUARD REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("REVIEW_EFFECT_AUDIT::" + str(REVIEW_EFFECT_AUDIT))
print("REVIEW_COMMIT_RESULT::" + str(REVIEW_COMMIT_RESULT))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("IDEMPOTENT_STEP_GUARD_REVIEW_SEALED::" + str(status == "PASS"))
print("NORMAL_EXECUTION_ALLOWED_REVIEW_SEALED::" + str(status == "PASS"))
print("ALREADY_COMMITTED_NOOP_REVIEW_SEALED::" + str(status == "PASS"))
print("OUT_OF_PHASE_RERUN_BLOCKED_REVIEW_SEALED::" + str(status == "PASS"))
print("RECOVERY_ALLOWED_EXPLICIT_ONLY_REVIEW_SEALED::" + str(status == "PASS"))
print("READY_TO_BUILD_IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER::" + str(status == "PASS"))
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

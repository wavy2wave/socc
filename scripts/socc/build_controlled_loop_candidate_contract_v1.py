import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "build_controlled_loop_candidate_contract_v1"
NEXT = "validate_controlled_loop_candidate_contract_v1"
REPAIR = "repair_controlled_loop_candidate_contract_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

ENFORCEMENT_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_V1_PROOF.json"
ENFORCEMENT_ROUTE_REPAIR_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_REVIEW_ROUTE_TRANSITION_REPAIR_V1_PROOF.json"
RUNTIME_ADOPTION_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_REVIEW_V1_PROOF.json"
MANDATORY_INTEGRATION_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_REVIEW_V1_PROOF.json"
WRAPPER_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_V1_PROOF.json"

BASE = ROOT / "core/socc/controlled_loop/candidate_contract"
CONTRACT = BASE / "CONTROLLED_LOOP_CANDIDATE_CONTRACT_V1.json"
CONTRACT_MD = BASE / "CONTROLLED_LOOP_CANDIDATE_CONTRACT_V1.md"
BOUNDARIES = BASE / "CONTROLLED_LOOP_CANDIDATE_BOUNDARIES_V1.json"
ITERATION_RULES = BASE / "CONTROLLED_LOOP_CANDIDATE_ITERATION_RULES_V1.json"
OBSERVABILITY = BASE / "CONTROLLED_LOOP_CANDIDATE_OBSERVABILITY_V1.json"
STOP_CONDITIONS = BASE / "CONTROLLED_LOOP_CANDIDATE_STOP_CONDITIONS_V1.json"
REPAIR_CONDITIONS = BASE / "CONTROLLED_LOOP_CANDIDATE_REPAIR_CONDITIONS_V1.json"
FORBIDDEN_CLAIMS = BASE / "CONTROLLED_LOOP_CANDIDATE_FORBIDDEN_CLAIMS_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/CONTROLLED_LOOP_CANDIDATE_CONTRACT_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/controlled_loop/CONTROLLED_LOOP_CANDIDATE_CONTRACT_V1_MEMORY.json"

FORBIDDEN_FLAGS = [
    "runtime_launch_approved",
    "runtime_execution_allowed",
    "runtime_autonomy_enabled",
    "loop_execution_started",
    "controlled_loop_enabled",
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
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_text(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(str(text).rstrip() + "\n", encoding="utf-8")

def h24(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]

def get_next(obj):
    return obj.get("lawful_next") or obj.get("real_next") or obj.get("REAL_NEXT")

def status_pass(obj):
    return obj.get("status") == "PASS"

def false_or_absent(obj, key):
    return obj.get(key) is False or obj.get(key) is None

route = read_json(ROUTE)
panel = read_json(PANEL)
pulse = read_json(PULSE)
progress = read_json(PROGRESS)

enforcement_review = read_json(ENFORCEMENT_REVIEW_PROOF)
enforcement_repair = read_json(ENFORCEMENT_ROUTE_REPAIR_PROOF)
runtime_adoption_review = read_json(RUNTIME_ADOPTION_REVIEW_PROOF)
mandatory_review = read_json(MANDATORY_INTEGRATION_REVIEW_PROOF)
wrapper_review = read_json(WRAPPER_REVIEW_PROOF)

truth_boundary = (
    "Candidate contract build only. This builds the controlled loop candidate contract. "
    "It does not execute a loop, does not approve runtime launch, does not start daemon/scheduler/background autonomy, "
    "does not widen queue, does not birth Entity/ANNA, does not approve final canon, and does not claim AGI."
)

checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_ok": get_next(route) == EXPECTED_CURRENT,

    "enforcement_review_proof_exists": ENFORCEMENT_REVIEW_PROOF.exists(),
    "enforcement_review_status_pass": status_pass(enforcement_review),
    "enforcement_review_capability_ok": enforcement_review.get("capability") == "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_SEALED",
    "enforcement_review_real_next_ok": get_next(enforcement_review) == EXPECTED_CURRENT,
    "enforcement_review_hard_failures_empty": enforcement_review.get("hard_failures") == [],

    "enforcement_lane_review_sealed": enforcement_review.get("guarded_runtime_adoption_enforcement_lane_review_sealed") is True,
    "enforcement_lane_validated": enforcement_review.get("guarded_runtime_adoption_enforcement_lane_validated") is True,
    "bypass_detector_reviewed": enforcement_review.get("runtime_wrapper_bypass_detector_reviewed") is True,
    "compliance_proof_spec_reviewed": enforcement_review.get("runtime_adoption_compliance_proof_spec_reviewed") is True,
    "fail_closed_enforcement_reviewed": enforcement_review.get("guarded_runtime_fail_closed_enforcement_reviewed") is True,
    "controlled_loop_candidate_required_next": enforcement_review.get("controlled_loop_candidate_contract_required_next") is True,

    "enforcement_route_repair_proof_exists": ENFORCEMENT_ROUTE_REPAIR_PROOF.exists(),
    "enforcement_route_repair_status_pass": status_pass(enforcement_repair),
    "route_repaired_to_candidate_build": enforcement_repair.get("route_lawful_next_updated_to_controlled_loop_candidate_build") is True,

    "runtime_adoption_review_exists": RUNTIME_ADOPTION_REVIEW_PROOF.exists(),
    "runtime_adoption_review_status_pass": status_pass(runtime_adoption_review),
    "runtime_adoption_review_sealed": runtime_adoption_review.get("runtime_adoption_contract_review_sealed") is True,

    "mandatory_integration_review_exists": MANDATORY_INTEGRATION_REVIEW_PROOF.exists(),
    "mandatory_integration_review_status_pass": status_pass(mandatory_review),
    "mandatory_integration_review_sealed": mandatory_review.get("mandatory_integration_contract_review_sealed") is True,

    "wrapper_review_exists": WRAPPER_REVIEW_PROOF.exists(),
    "wrapper_review_status_pass": status_pass(wrapper_review),
    "wrapper_review_sealed": wrapper_review.get("idempotent_guard_enforced_step_wrapper_review_sealed") is True,
    "before_write_immunity_accepted": wrapper_review.get("before_write_immunity_layer_accepted") is True,

    "build_does_not_execute_loop": True,
    "build_does_not_approve_runtime": True,
    "build_does_not_launch_daemon": True,
    "build_does_not_install_scheduler": True,
    "build_does_not_enable_background": True,
    "build_does_not_widen_queue": True,
    "build_does_not_birth_entity": True,
    "build_does_not_birth_anna": True,
    "build_does_not_claim_agi": True,
}

for label, obj in [
    ("route", route),
    ("panel", panel),
    ("pulse", pulse),
    ("progress", progress),
    ("enforcement_review", enforcement_review),
]:
    for key in FORBIDDEN_FLAGS:
        checks[f"{label}_{key}_false_or_absent"] = false_or_absent(obj, key)

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

boundaries = {
    "id": "CONTROLLED_LOOP_CANDIDATE_BOUNDARIES_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "max_iterations_candidate": 3,
    "allowed_execution_mode": "bounded_candidate_only",
    "not_allowed_modes": [
        "daemon",
        "scheduler",
        "background_loop",
        "infinite_loop",
        "24_7_autonomy",
        "network_autonomy",
        "queue_widening",
        "Entity_birth",
        "ANNA_birth",
        "AGI_claim"
    ],
    "required_per_iteration": [
        "current_route_authority_check",
        "lawful_next_match",
        "wrapper_decision_before_writes",
        "runtime_adoption_compliance_proof",
        "effect_audit",
        "atomic_commit_if_route_transition",
        "material_effect_check",
        "panel_pulse_progress_coherence",
        "memory_write",
        "truth_boundary_false"
    ],
    "truth_boundary": truth_boundary
}

iteration_rules = {
    "id": "CONTROLLED_LOOP_CANDIDATE_ITERATION_RULES_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "iteration_rule": "each_iteration_is_a_guarded_lawful_step_not_free_execution",
    "each_iteration_must": [
        "declare_iteration_index",
        "declare_expected_lawful_next",
        "load_current_route_authority",
        "invoke_idempotent_guard_wrapper_before_material_writes",
        "produce_runtime_adoption_compliance_proof",
        "block_direct_route_proof_memory_writes",
        "fail_closed_on_wrapper_rejection",
        "record_effect_audit_result",
        "record_atomic_commit_result_when_route_changes",
        "verify_material_route_effect",
        "record_memory_wave_report",
        "update_panel_pulse_progress_coherently"
    ],
    "each_iteration_must_not": [
        "execute_unbounded_tasks",
        "spawn_background_continuation",
        "self_schedule_next_run",
        "widen_queue",
        "skip_review_or_validation",
        "claim_autonomy_level_increase_without_proof"
    ],
    "truth_boundary": truth_boundary
}

observability = {
    "id": "CONTROLLED_LOOP_CANDIDATE_OBSERVABILITY_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "must_emit": [
        "loop_candidate_contract_proof",
        "iteration_index",
        "iteration_start_state",
        "iteration_end_state",
        "wrapper_decision",
        "bypass_detector_result",
        "compliance_proof",
        "effect_audit_result",
        "atomic_commit_result",
        "route_material_effect_result",
        "stop_condition_result",
        "repair_condition_result",
        "truth_boundary_flags"
    ],
    "must_update_if_executed_later": [
        "panel",
        "pulse",
        "progress",
        "memory_wave",
        "proof_ledger"
    ],
    "truth_boundary": truth_boundary
}

stop_conditions = {
    "id": "CONTROLLED_LOOP_CANDIDATE_STOP_CONDITIONS_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "stop_on": [
        "max_iterations_reached",
        "lawful_next_mismatch",
        "upstream_proof_mismatch",
        "wrapper_rejection",
        "direct_write_attempt_detected",
        "effect_audit_failure",
        "atomic_commit_failure",
        "missing_material_route_effect",
        "panel_pulse_progress_incoherence",
        "truth_boundary_violation",
        "unknown_task",
        "unapproved_queue_widening_attempt"
    ],
    "stop_mode": "fail_closed",
    "truth_boundary": truth_boundary
}

repair_conditions = {
    "id": "CONTROLLED_LOOP_CANDIDATE_REPAIR_CONDITIONS_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "repairable_only_if": [
        "proof_pass_exists_but_route_transition_missing",
        "effect_auditor_and_atomic_commit_accepted_but_material_route_effect_missing",
        "canonical_route_missing_but_upstream_proof_points_to_lawful_next",
        "schema_bridge_needed_with_existing_artifact_evidence"
    ],
    "not_repairable_if": [
        "truth_boundary_violation",
        "daemon_started",
        "scheduler_installed",
        "background_loop_enabled",
        "runtime_execution_without_contract",
        "direct_write_without_wrapper",
        "AGI_claim_written",
        "Entity_or_ANNA_birth_claim_written"
    ],
    "truth_boundary": truth_boundary
}

forbidden_claims = {
    "id": "CONTROLLED_LOOP_CANDIDATE_FORBIDDEN_CLAIMS_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "forbidden_claims": [
        "SOCC_full_autonomy",
        "SOCC_AGI",
        "daemon_running",
        "scheduler_installed",
        "background_24_7_autonomy",
        "controlled_loop_executed",
        "runtime_launched",
        "Entity_born",
        "ANNA_born"
    ],
    "allowed_claim": "controlled_loop_candidate_contract_built_only_if_proof_pass",
    "truth_boundary": truth_boundary
}

capability = (
    "CONTROLLED_LOOP_CANDIDATE_CONTRACT_BUILT"
    if status == "PASS"
    else "CONTROLLED_LOOP_CANDIDATE_CONTRACT_BLOCKED"
)

contract = {
    "id": "CONTROLLED_LOOP_CANDIDATE_CONTRACT_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,

    "source_enforcement_review_proof": str(ENFORCEMENT_REVIEW_PROOF),
    "source_enforcement_route_repair_proof": str(ENFORCEMENT_ROUTE_REPAIR_PROOF),
    "source_runtime_adoption_review_proof": str(RUNTIME_ADOPTION_REVIEW_PROOF),
    "source_mandatory_integration_review_proof": str(MANDATORY_INTEGRATION_REVIEW_PROOF),
    "source_wrapper_review_proof": str(WRAPPER_REVIEW_PROOF),

    "boundaries": str(BOUNDARIES),
    "iteration_rules": str(ITERATION_RULES),
    "observability": str(OBSERVABILITY),
    "stop_conditions": str(STOP_CONDITIONS),
    "repair_conditions": str(REPAIR_CONDITIONS),
    "forbidden_claims": str(FORBIDDEN_CLAIMS),

    "controlled_loop_candidate_contract_built": status == "PASS",
    "bounded_loop_candidate_defined": status == "PASS",
    "max_iterations_defined": status == "PASS",
    "per_iteration_wrapper_required": status == "PASS",
    "per_iteration_compliance_proof_required": status == "PASS",
    "per_iteration_effect_audit_required": status == "PASS",
    "per_iteration_atomic_commit_required_if_route_transition": status == "PASS",
    "stop_conditions_defined": status == "PASS",
    "repair_conditions_defined": status == "PASS",
    "truth_boundary_defined": status == "PASS",

    "runtime_launch_approved": False,
    "runtime_execution_allowed": False,
    "runtime_autonomy_enabled": False,
    "loop_execution_started": False,
    "controlled_loop_enabled": False,
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
    "real_next": NEXT if status == "PASS" else REPAIR,
    "truth_boundary": truth_boundary
}
contract["contract_hash"] = h24(contract)

proof = {
    "id": "CONTROLLED_LOOP_CANDIDATE_CONTRACT_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "contract": str(CONTRACT),
    "contract_md": str(CONTRACT_MD),
    "boundaries": str(BOUNDARIES),
    "iteration_rules": str(ITERATION_RULES),
    "observability": str(OBSERVABILITY),
    "stop_conditions": str(STOP_CONDITIONS),
    "repair_conditions": str(REPAIR_CONDITIONS),
    "forbidden_claims": str(FORBIDDEN_CLAIMS),
    "memory": str(MEMORY),

    "controlled_loop_candidate_contract_built": status == "PASS",
    "bounded_loop_candidate_defined": status == "PASS",
    "max_iterations_defined": status == "PASS",
    "per_iteration_wrapper_required": status == "PASS",
    "per_iteration_compliance_proof_required": status == "PASS",
    "per_iteration_effect_audit_required": status == "PASS",
    "per_iteration_atomic_commit_required_if_route_transition": status == "PASS",
    "stop_conditions_defined": status == "PASS",
    "repair_conditions_defined": status == "PASS",
    "truth_boundary_defined": status == "PASS",

    "runtime_launch_approved": False,
    "runtime_execution_allowed": False,
    "runtime_autonomy_enabled": False,
    "loop_execution_started": False,
    "controlled_loop_enabled": False,
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
    "real_next": NEXT if status == "PASS" else REPAIR,
    "final_socc_status": (
        "SOCC_CONTROLLED_LOOP_CANDIDATE_CONTRACT_BUILD_PASS_NOT_LOOP_EXECUTION_NOT_DAEMON"
        if status == "PASS"
        else "SOCC_CONTROLLED_LOOP_CANDIDATE_CONTRACT_BUILD_FAIL"
    ),
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "CONTROLLED_LOOP_CANDIDATE_CONTRACT_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built controlled loop candidate contract after guarded runtime adoption enforcement review-seal. "
        "This is contract only: no loop execution, no runtime launch, no daemon."
        if status == "PASS"
        else "Controlled loop candidate contract build blocked."
    ),
    "contract": str(CONTRACT),
    "proof": str(PROOF),
    "real_next": NEXT if status == "PASS" else REPAIR,
    "truth_boundary": truth_boundary,
}

md = "# CONTROLLED LOOP CANDIDATE CONTRACT V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\n"
md += "Guarded runtime adoption enforcement lane was review-sealed. Wrapper bypass detection and compliance proof discipline are accepted.\n\n"
md += "## ДЕЙСТВИЕ\n\n"
md += "Built controlled loop candidate contract. This is not loop execution.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Controlled loop candidate contract is built. Next step: validate the candidate contract.\n\n"
else:
    md += "Controlled loop candidate contract build is blocked. Repair required.\n\n"
md += "## Explicitly NOT done\n\n"
for x in [
    "runtime not launched",
    "loop not executed",
    "controlled loop not enabled",
    "daemon not launched",
    "scheduler not installed",
    "background autonomy not enabled",
    "network not used",
    "queue not widened",
    "Entity not born",
    "ANNA not born",
    "AGI not claimed",
    "final canon not approved",
]:
    md += "- " + x + "\n"
md += "\n## lawful_next\n\n" + (NEXT if status == "PASS" else REPAIR) + "\n\n"
md += "## Truth boundary\n\n" + truth_boundary + "\n"

write_json(BOUNDARIES, boundaries)
write_json(ITERATION_RULES, iteration_rules)
write_json(OBSERVABILITY, observability)
write_json(STOP_CONDITIONS, stop_conditions)
write_json(REPAIR_CONDITIONS, repair_conditions)
write_json(FORBIDDEN_CLAIMS, forbidden_claims)
write_json(CONTRACT, contract)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(CONTRACT_MD, md)

print("CONTROLLED LOOP CANDIDATE CONTRACT BUILD :: " + status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + capability)
print("CONTRACT::" + str(CONTRACT))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("CONTROLLED_LOOP_CANDIDATE_CONTRACT_BUILT::" + str(status == "PASS"))
print("BOUNDED_LOOP_CANDIDATE_DEFINED::" + str(status == "PASS"))
print("MAX_ITERATIONS_DEFINED::" + str(status == "PASS"))
print("PER_ITERATION_WRAPPER_REQUIRED::" + str(status == "PASS"))
print("PER_ITERATION_COMPLIANCE_PROOF_REQUIRED::" + str(status == "PASS"))
print("PER_ITERATION_EFFECT_AUDIT_REQUIRED::" + str(status == "PASS"))
print("PER_ITERATION_ATOMIC_COMMIT_REQUIRED_IF_ROUTE_TRANSITION::" + str(status == "PASS"))
print("STOP_CONDITIONS_DEFINED::" + str(status == "PASS"))
print("REPAIR_CONDITIONS_DEFINED::" + str(status == "PASS"))
print("TRUTH_BOUNDARY_DEFINED::" + str(status == "PASS"))
print("RUNTIME_LAUNCH_APPROVED::False")
print("RUNTIME_EXECUTION_ALLOWED::False")
print("RUNTIME_AUTONOMY_ENABLED::False")
print("LOOP_EXECUTION_STARTED::False")
print("CONTROLLED_LOOP_ENABLED::False")
print("DAEMON_RUNNING::False")
print("SCHEDULER_INSTALLED::False")
print("BACKGROUND_LOOP_ENABLED::False")
print("NETWORK_USED::False")
print("QUEUE_WIDENING_ALLOWED::False")
print("ENTITY_BIRTH_ALLOWED::False")
print("ANNA_BIRTH_ALLOWED::False")
print("AGI_CLAIM_ALLOWED::False")
print("FINAL_CANON_APPROVAL_ALLOWED::False")
print("REAL_NEXT::" + (NEXT if status == "PASS" else REPAIR))
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if status == "PASS" else 1)

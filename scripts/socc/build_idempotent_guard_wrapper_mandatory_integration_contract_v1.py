import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "build_idempotent_guard_wrapper_mandatory_integration_contract_v1"
NEXT = "validate_idempotent_guard_wrapper_mandatory_integration_contract_v1"
REPAIR = "repair_idempotent_guard_wrapper_mandatory_integration_contract_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

WRAPPER_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_V1_PROOF.json"
COMMIT_EFFECT_REPAIR_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_WRAPPER_REVIEW_ATOMIC_COMMIT_EFFECT_REPAIR_V1_PROOF.json"

OUT_DIR = ROOT / "core/socc/idempotent_guard/mandatory_integration"
CONTRACT = OUT_DIR / "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_V1.json"
CONTRACT_MD = OUT_DIR / "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_V1.md"
POLICY = OUT_DIR / "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_POLICY_V1.json"
FORBIDDEN_DIRECT_WRITES = OUT_DIR / "FORBIDDEN_DIRECT_WRITES_AFTER_MANDATORY_WRAPPER_V1.json"
ADOPTION_MATRIX = OUT_DIR / "WRAPPER_MANDATORY_ADOPTION_MATRIX_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/idempotent_guard/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_V1_MEMORY.json"

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
review = read_json(WRAPPER_REVIEW_PROOF)
repair = read_json(COMMIT_EFFECT_REPAIR_PROOF)

truth_boundary = (
    "Mandatory integration contract build only. This defines that future bounded construction steps must use the "
    "idempotent guard enforced wrapper before proof/report/memory/route writes. It does not execute integration, "
    "does not launch loop/daemon/scheduler/background autonomy, does not widen queue, does not birth Entity/ANNA, "
    "does not approve final canon, and does not claim AGI."
)

checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_ok": get_next(route) == EXPECTED_CURRENT,

    "wrapper_review_proof_exists": WRAPPER_REVIEW_PROOF.exists(),
    "wrapper_review_status_pass": status_pass(review),
    "wrapper_review_sealed": review.get("idempotent_guard_enforced_step_wrapper_review_sealed") is True,
    "before_write_immunity_layer_accepted": review.get("before_write_immunity_layer_accepted") is True,
    "effect_auditor_enforced": review.get("effect_auditor_enforced") is True,
    "atomic_commit_committed": review.get("atomic_commit_committed") is True,
    "route_lawful_next_updated": review.get("route_lawful_next_updated") is True,
    "panel_lawful_next_matches_route": review.get("panel_lawful_next_matches_route") is True,
    "pulse_lawful_next_matches_route": review.get("pulse_lawful_next_matches_route") is True,
    "progress_lawful_next_matches_route": review.get("progress_lawful_next_matches_route") is True,
    "review_real_next_ok": get_next(review) == EXPECTED_CURRENT,

    "commit_effect_repair_proof_exists": COMMIT_EFFECT_REPAIR_PROOF.exists(),
    "commit_effect_repair_status_pass": status_pass(repair),
    "commit_effect_repair_route_coherent": repair.get("route_lawful_next_updated") is True,
    "commit_effect_repair_wrapper_finalized": repair.get("wrapper_review_finalized") is True,

    "route_upstream_points_to_review": route.get("upstream_proof") == str(WRAPPER_REVIEW_PROOF),
    "route_wrapper_review_sealed": route.get("idempotent_guard_enforced_step_wrapper_review_sealed") is True,
    "route_before_write_immunity_accepted": route.get("before_write_immunity_layer_accepted") is True,
    "route_mandatory_integration_required": route.get("mandatory_integration_required_next") is True,

    "build_does_not_execute_wrapper": True,
    "build_does_not_launch_loop": True,
    "build_does_not_launch_daemon": True,
    "build_does_not_install_scheduler": True,
    "build_does_not_enable_background": True,
    "build_does_not_use_network": True,
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
    ("review", review),
]:
    for key in [
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
    ]:
        checks[f"{label}_{key}_false_or_absent"] = false_or_absent(obj, key)

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

policy = {
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_POLICY_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "policy": {
        "mandatory_before_write_wrapper": status == "PASS",
        "scope": [
            "build_steps",
            "validate_steps",
            "review_steps",
            "repair_steps",
            "runtime_one_tick_steps",
            "future_controlled_loop_iterations",
            "future_self_building_ticks"
        ],
        "must_wrap_before": [
            "artifact_write",
            "proof_write",
            "memory_write",
            "report_write",
            "route_update",
            "panel_update",
            "pulse_update",
            "progress_update"
        ],
        "required_pre_write_checks": [
            "current_lawful_next_matches_step",
            "upstream_proof_matches_route",
            "step_not_already_committed",
            "out_of_phase_rerun_blocked",
            "already_committed_rerun_noop",
            "forbidden_truth_boundary_flags_false"
        ],
        "required_post_write_checks": [
            "material_artifact_exists",
            "proof_exists",
            "memory_exists",
            "route_lawful_next_updated_if_transition",
            "panel_pulse_progress_coherent",
            "hard_failures_empty"
        ],
        "fail_closed": True
    },
    "truth_boundary": truth_boundary
}

forbidden_direct_writes = {
    "id": "FORBIDDEN_DIRECT_WRITES_AFTER_MANDATORY_WRAPPER_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "forbidden_direct_write_targets": [
        "CURRENT_ROUTE_AUTHORITY.json",
        "SELF_BUILDING_STATUS_PANEL_V1.json",
        "SELF_BUILDING_PULSE_V1.json",
        "SELF_BUILDING_PROGRESS_LEDGER_V1.json",
        "core/socc/approved_autonomy_lane_runner/proof/*.json",
        "MEMORY_WAVE/reports/**/*.json",
        "runtime/state/**/*.json",
        "future_loop_state/**/*.json"
    ],
    "allowed_only_through": [
        "idempotent_guard_enforced_step_wrapper",
        "effect_auditor_enforced_lane",
        "atomic_commit_enforcer"
    ],
    "violation_result": "FAIL_CLOSED_BEFORE_WRITES",
    "truth_boundary": truth_boundary
}

adoption_matrix = {
    "id": "WRAPPER_MANDATORY_ADOPTION_MATRIX_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "adoption_targets": [
        {
            "target": "future_build_steps",
            "required": True,
            "before_write_wrapper_required": True
        },
        {
            "target": "future_validation_steps",
            "required": True,
            "before_write_wrapper_required": True
        },
        {
            "target": "future_review_steps",
            "required": True,
            "before_write_wrapper_required": True
        },
        {
            "target": "future_repair_steps",
            "required": True,
            "before_write_wrapper_required": True
        },
        {
            "target": "controlled_loop_candidate_contract",
            "required": True,
            "before_write_wrapper_required": True
        },
        {
            "target": "bounded_controlled_loop_execution",
            "required": True,
            "before_write_wrapper_required": True
        },
        {
            "target": "self_building_mode_ticks",
            "required": True,
            "before_write_wrapper_required": True
        }
    ],
    "truth_boundary": truth_boundary
}

contract = {
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": (
        "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_BUILT"
        if status == "PASS"
        else "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_BLOCKED"
    ),
    "source_wrapper_review_proof": str(WRAPPER_REVIEW_PROOF),
    "source_commit_effect_repair_proof": str(COMMIT_EFFECT_REPAIR_PROOF),
    "policy": str(POLICY),
    "forbidden_direct_writes": str(FORBIDDEN_DIRECT_WRITES),
    "adoption_matrix": str(ADOPTION_MATRIX),

    "mandatory_before_write_wrapper_contract_built": status == "PASS",
    "all_future_material_steps_must_use_wrapper": status == "PASS",
    "direct_route_writes_forbidden": status == "PASS",
    "direct_proof_memory_writes_forbidden": status == "PASS",
    "fail_closed_before_writes_required": status == "PASS",
    "effect_auditor_required_after_wrapper": status == "PASS",
    "atomic_commit_required_for_route_transition": status == "PASS",

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
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": contract["capability"],
    "contract": str(CONTRACT),
    "contract_md": str(CONTRACT_MD),
    "policy": str(POLICY),
    "forbidden_direct_writes": str(FORBIDDEN_DIRECT_WRITES),
    "adoption_matrix": str(ADOPTION_MATRIX),
    "memory": str(MEMORY),

    "mandatory_before_write_wrapper_contract_built": status == "PASS",
    "all_future_material_steps_must_use_wrapper": status == "PASS",
    "direct_route_writes_forbidden": status == "PASS",
    "direct_proof_memory_writes_forbidden": status == "PASS",
    "fail_closed_before_writes_required": status == "PASS",
    "effect_auditor_required_after_wrapper": status == "PASS",
    "atomic_commit_required_for_route_transition": status == "PASS",

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
        "SOCC_IDEMPOTENT_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_PASS_NOT_LOOP_NOT_DAEMON"
        if status == "PASS"
        else "SOCC_IDEMPOTENT_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_FAIL"
    ),
    "truth_boundary": truth_boundary
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "IDEMPOTENT_GUARD_WRAPPER_MANDATORY_INTEGRATION_CONTRACT_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built a mandatory integration contract requiring the idempotent guard enforced wrapper before future material writes. "
        "This prepares future loop/self-building execution without launching loop/daemon."
        if status == "PASS"
        else "Mandatory wrapper integration contract build blocked."
    ),
    "contract": str(CONTRACT),
    "proof": str(PROOF),
    "real_next": NEXT if status == "PASS" else REPAIR,
    "truth_boundary": truth_boundary
}

md = "# IDEMPOTENT GUARD WRAPPER MANDATORY INTEGRATION CONTRACT V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + contract["capability"] + "\n\n"
md += "## БЫЛО\n\n"
md += "Idempotent guard enforced wrapper was review-sealed with effect audit and atomic commit. Before-write immunity exists as accepted capability.\n\n"
md += "## ДЕЙСТВИЕ\n\n"
md += "Built mandatory integration contract: future material construction steps must invoke wrapper before writes.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Mandatory integration contract is built. Wrapper must be integrated before future build/validate/review/repair/loop/self-building writes.\n\n"
else:
    md += "Mandatory integration contract is blocked. Repair required.\n\n"
md += "## Forbidden direct writes\n\n"
for x in forbidden_direct_writes["forbidden_direct_write_targets"]:
    md += "- " + x + "\n"
md += "\n## Explicitly NOT done\n\n"
for x in [
    "loop not executed",
    "controlled loop not enabled",
    "daemon not launched",
    "scheduler not installed",
    "background autonomy not enabled",
    "network autonomy not enabled",
    "queue not widened",
    "Entity not born",
    "ANNA not born",
    "AGI not claimed",
    "final canon not approved",
]:
    md += "- " + x + "\n"
md += "\n## lawful_next\n\n"
md += (NEXT if status == "PASS" else REPAIR) + "\n\n"
md += "## Truth boundary\n\n"
md += truth_boundary + "\n"

write_json(POLICY, policy)
write_json(FORBIDDEN_DIRECT_WRITES, forbidden_direct_writes)
write_json(ADOPTION_MATRIX, adoption_matrix)
write_json(CONTRACT, contract)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(CONTRACT_MD, md)

print("IDEMPOTENT GUARD WRAPPER MANDATORY INTEGRATION CONTRACT BUILD :: " + status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + contract["capability"])
print("CONTRACT::" + str(CONTRACT))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("MANDATORY_BEFORE_WRITE_WRAPPER_CONTRACT_BUILT::" + str(status == "PASS"))
print("ALL_FUTURE_MATERIAL_STEPS_MUST_USE_WRAPPER::" + str(status == "PASS"))
print("DIRECT_ROUTE_WRITES_FORBIDDEN::" + str(status == "PASS"))
print("DIRECT_PROOF_MEMORY_WRITES_FORBIDDEN::" + str(status == "PASS"))
print("FAIL_CLOSED_BEFORE_WRITES_REQUIRED::" + str(status == "PASS"))
print("EFFECT_AUDITOR_REQUIRED_AFTER_WRAPPER::" + str(status == "PASS"))
print("ATOMIC_COMMIT_REQUIRED_FOR_ROUTE_TRANSITION::" + str(status == "PASS"))
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

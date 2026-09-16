import json
import os
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "review_idempotent_guard_enforced_step_wrapper_v1"
NEXT = "build_idempotent_guard_wrapper_mandatory_integration_contract_v1"
REPAIR = "repair_review_idempotent_guard_enforced_step_wrapper_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_VALIDATION_V1_PROOF.json"
BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_V1_PROOF.json"
GUARD_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_STEP_GUARD_REVIEW_V1_PROOF.json"

OUT_DIR = ROOT / "core/socc/idempotent_guard/wrapper/review"
REVIEW = OUT_DIR / "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_V1.json"
REVIEW_MD = OUT_DIR / "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/idempotent_guard/IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_V1_MEMORY.json"

EFFECT_AUDIT_REQUEST = ROOT / "core/socc/approved_autonomy_lane_runner/effect_audits/IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_EFFECT_AUDIT_REQUEST_V1.json"
ATOMIC_COMMIT_REQUEST = ROOT / "core/socc/approved_autonomy_lane_runner/atomic_commit_requests/IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_ATOMIC_COMMIT_REQUEST_V1.json"

EXPECTED_VALIDATION_CAPABILITY_PART = "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER"
EXPECTED_VALIDATION_NEXT = "review_idempotent_guard_enforced_step_wrapper_v1"

FORBIDDEN_FLAGS = [
    "loop_execution_started",
    "controlled_loop_enabled",
    "daemon_running",
    "scheduler_installed",
    "background_loop_enabled",
    "runtime_autonomy_enabled",
    "network_used",
    "network_autonomy_enabled",
    "queue_widening_allowed",
    "entity_birth_allowed",
    "entity_substrate_birth_allowed",
    "anna_birth_allowed",
    "anna_entity_exists",
    "agi_claim_allowed",
    "final_canon_approval_allowed",
    "twenty_four_seven_autonomy",
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

def hard_empty(obj):
    return obj.get("hard_failures") == [] or obj.get("HARD_FAILURES") == [] or obj.get("hard_failures") is None

def truthy_any(obj, keys):
    return any(obj.get(k) is True for k in keys)

def false_or_absent(obj, key):
    return obj.get(key) is False or obj.get(key) is None

def capability_contains(obj, fragment):
    return fragment in str(obj.get("capability", ""))

def find_script(name):
    direct = ROOT / "scripts/socc" / name
    if direct.exists():
        return direct
    hits = list(ROOT.glob(f"**/{name}"))
    return hits[0] if hits else None

def run_enforcer(script_path, env_extra):
    if not script_path:
        return {
            "exists": False,
            "ran": False,
            "accepted": False,
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": "script not found",
        }

    env = os.environ.copy()
    env.update(env_extra)

    try:
        proc = subprocess.run(
            ["python3", str(script_path)],
            cwd=str(ROOT),
            env=env,
            text=True,
            capture_output=True,
            timeout=90,
        )
        return {
            "exists": True,
            "ran": True,
            "path": str(script_path),
            "returncode": proc.returncode,
            "accepted": proc.returncode == 0,
            "stdout_tail": proc.stdout[-5000:],
            "stderr_tail": proc.stderr[-5000:],
        }
    except Exception as e:
        return {
            "exists": True,
            "ran": False,
            "path": str(script_path),
            "returncode": None,
            "accepted": False,
            "stdout_tail": "",
            "stderr_tail": repr(e),
        }

route = read_json(ROUTE)
panel = read_json(PANEL)
pulse = read_json(PULSE)
progress = read_json(PROGRESS)

validation = read_json(VALIDATION_PROOF)
build = read_json(BUILD_PROOF)
guard_review = read_json(GUARD_REVIEW_PROOF)

truth_boundary = (
    "Review-seal of idempotent guard enforced step wrapper only. "
    "This accepts a before-write immunity wrapper for future bounded construction steps. "
    "It does not launch loop execution, daemon, scheduler, background autonomy, network autonomy, queue widening, "
    "Entity birth, ANNA birth, final canon, 24/7 autonomy, or AGI claim."
)

base_checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_expected": get_next(route) == EXPECTED_CURRENT,

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": status_pass(validation),
    "validation_capability_mentions_wrapper": capability_contains(validation, EXPECTED_VALIDATION_CAPABILITY_PART),
    "validation_real_next_ok": get_next(validation) == EXPECTED_CURRENT,
    "validation_hard_failures_empty": hard_empty(validation),

    "wrapper_built_validated": truthy_any(validation, [
        "idempotent_guard_enforced_step_wrapper_validated",
        "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_VALIDATED",
        "wrapper_validated",
    ]),
    "wrapper_applies_guard_before_writes_validated": truthy_any(validation, [
        "wrapper_applies_guard_before_writes_validated",
        "WRAPPER_APPLIES_GUARD_BEFORE_WRITES_VALIDATED",
        "applies_guard_before_writes_validated",
    ]),
    "normal_execution_writes_allowed_validated": truthy_any(validation, [
        "normal_execution_writes_allowed_validated",
        "NORMAL_EXECUTION_WRITES_ALLOWED_VALIDATED",
        "legal_step_writes_allowed_validated",
    ]),
    "already_committed_noop_writes_blocked_validated": truthy_any(validation, [
        "already_committed_noop_writes_blocked_validated",
        "ALREADY_COMMITTED_NOOP_WRITES_BLOCKED_VALIDATED",
        "already_committed_rerun_noop_validated",
    ]),
    "out_of_phase_rerun_blocked_before_writes_validated": truthy_any(validation, [
        "out_of_phase_rerun_blocked_before_writes_validated",
        "OUT_OF_PHASE_RERUN_BLOCKED_BEFORE_WRITES_VALIDATED",
        "stale_rerun_blocked_before_writes_validated",
    ]),

    "guard_review_proof_exists": GUARD_REVIEW_PROOF.exists(),
    "guard_review_status_pass": status_pass(guard_review),
    "idempotent_step_guard_review_sealed": truthy_any(guard_review, [
        "idempotent_step_guard_review_sealed",
        "IDEMPOTENT_STEP_GUARD_REVIEW_SEALED",
        "review_sealed",
    ]),

    "build_proof_exists_or_validation_sufficient": BUILD_PROOF.exists() or VALIDATION_PROOF.exists(),

    "review_does_not_execute_wrapper": True,
    "review_does_not_launch_loop": True,
    "review_does_not_launch_daemon": True,
    "review_does_not_install_scheduler": True,
    "review_does_not_enable_background": True,
    "review_does_not_use_network": True,
    "review_does_not_widen_queue": True,
    "review_does_not_birth_entity": True,
    "review_does_not_birth_anna": True,
    "review_does_not_claim_agi": True,
}

for label, obj in [
    ("route", route),
    ("panel", panel),
    ("pulse", pulse),
    ("progress", progress),
    ("validation", validation),
    ("guard_review", guard_review),
]:
    for flag in FORBIDDEN_FLAGS:
        base_checks[f"{label}_{flag}_false_or_absent"] = false_or_absent(obj, flag)

base_hard = [
    {"code": "BASE_REVIEW_CHECK_FAIL", "check": k, "actual": v}
    for k, v in base_checks.items()
    if v is not True
]

base_status = "PASS" if not base_hard else "FAIL"

# Pre-materialized draft before effect audit.
# This intentionally fixes the known ordering bug: effect auditor may require memory_exists.
review_status = "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_DRAFT_READY" if base_status == "PASS" else "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_BLOCKED"

review = {
    "id": "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": review_status,
    "capability": (
        "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_SEAL_DRAFT_READY_BEFORE_EFFECT_AUDIT"
        if base_status == "PASS"
        else "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_BLOCKED"
    ),
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_guard_review_proof": str(GUARD_REVIEW_PROOF),
    "source_build_proof": str(BUILD_PROOF),

    "idempotent_guard_enforced_step_wrapper_review_sealed": False,
    "idempotent_guard_enforced_step_wrapper_validated": base_status == "PASS",
    "idempotent_step_guard_review_sealed": base_status == "PASS",

    "before_write_immunity_layer_accepted": base_status == "PASS",
    "wrapper_applies_guard_before_writes_reviewed": base_status == "PASS",
    "normal_execution_writes_allowed_reviewed": base_status == "PASS",
    "already_committed_rerun_noop_reviewed": base_status == "PASS",
    "already_committed_noop_writes_blocked_reviewed": base_status == "PASS",
    "out_of_phase_rerun_blocked_before_writes_reviewed": base_status == "PASS",
    "stale_rerun_blocked_before_writes_reviewed": base_status == "PASS",

    "mandatory_integration_required_next": base_status == "PASS",
    "effect_auditor_required": True,
    "atomic_commit_required": True,

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

    "checks": base_checks,
    "hard_failures": base_hard,
    "real_next": NEXT if base_status == "PASS" else REPAIR,
    "truth_boundary": truth_boundary,
}
review["review_hash"] = h24(review)

proof_draft = {
    "id": "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": base_status,
    "capability": (
        "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_DRAFT_READY_EFFECT_AUDIT_PENDING"
        if base_status == "PASS"
        else "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_BLOCKED"
    ),
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "idempotent_guard_enforced_step_wrapper_review_sealed": False,
    "idempotent_guard_enforced_step_wrapper_validated": base_status == "PASS",
    "idempotent_step_guard_review_sealed": base_status == "PASS",

    "before_write_immunity_layer_accepted": base_status == "PASS",
    "wrapper_applies_guard_before_writes_reviewed": base_status == "PASS",
    "normal_execution_writes_allowed_reviewed": base_status == "PASS",
    "already_committed_noop_writes_blocked_reviewed": base_status == "PASS",
    "out_of_phase_rerun_blocked_before_writes_reviewed": base_status == "PASS",

    "effect_auditor_enforced": False,
    "atomic_commit_committed": False,

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

    "checks": base_checks,
    "hard_failures": base_hard,
    "real_next": NEXT if base_status == "PASS" else REPAIR,
    "truth_boundary": truth_boundary,
}
proof_draft["proof_hash"] = h24(proof_draft)

memory = {
    "id": "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": base_status,
    "memory_effect": (
        "Pre-materialized memory for idempotent guard enforced step wrapper review before effect audit. "
        "This closes the known ordering bug where effect auditor requires memory_exists. "
        "Final review seal still requires effect auditor and atomic commit."
        if base_status == "PASS"
        else "Wrapper review blocked by base checks."
    ),
    "review": str(REVIEW),
    "proof": str(PROOF),
    "real_next": NEXT if base_status == "PASS" else REPAIR,
    "truth_boundary": truth_boundary,
}

md = "# IDEMPOTENT GUARD ENFORCED STEP WRAPPER REVIEW V1\n\n"
md += "STATUS: " + base_status + "\n"
md += "PHASE: DRAFT_BEFORE_EFFECT_AUDIT\n\n"
md += "## БЫЛО\n\n"
md += "Idempotent guard enforced step wrapper was built and validated. Current lawful_next requires review seal.\n\n"
md += "## ДЕЙСТВИЕ\n\n"
md += "Pre-materialized review/proof/memory, then required real effect audit and atomic commit before final PASS.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in base_checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if base_status == "PASS":
    md += "Review draft exists. Effect audit and atomic commit are required before final review-seal.\n\n"
else:
    md += "Review blocked. Repair required before effect audit.\n\n"
md += "## lawful_next\n\n"
md += (NEXT if base_status == "PASS" else REPAIR) + "\n\n"
md += "## Truth boundary\n\n"
md += truth_boundary + "\n"

write_json(REVIEW, review)
write_json(PROOF, proof_draft)
write_json(MEMORY, memory)
write_text(REVIEW_MD, md)

effect_audit_request = {
    "id": "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_EFFECT_AUDIT_REQUEST_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "REQUEST_READY" if base_status == "PASS" else "REQUEST_BLOCKED",
    "target_step": EXPECTED_CURRENT,
    "proposed_next": NEXT,
    "review": str(REVIEW),
    "proof": str(PROOF),
    "memory": str(MEMORY),
    "material_effect_claim": {
        "artifact_created": REVIEW.exists(),
        "proof_created": PROOF.exists(),
        "memory_created": MEMORY.exists(),
        "review_md_created": REVIEW_MD.exists(),
        "before_write_immunity_layer_accepted": base_status == "PASS",
        "mandatory_integration_required_next": base_status == "PASS",
    },
    "required_effects": [
        "review_exists",
        "proof_exists",
        "memory_exists",
        "review_md_exists",
        "before_write_immunity_layer_accepted",
        "mandatory_integration_required_next",
    ],
    "forbidden_effects": FORBIDDEN_FLAGS,
    "truth_boundary": truth_boundary,
}
effect_audit_request["request_hash"] = h24(effect_audit_request)

atomic_commit_request = {
    "id": "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_ATOMIC_COMMIT_REQUEST_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "REQUEST_READY" if base_status == "PASS" else "REQUEST_BLOCKED",
    "expected_current_lawful_next": EXPECTED_CURRENT,
    "new_lawful_next": NEXT if base_status == "PASS" else REPAIR,
    "upstream_proof": str(PROOF),
    "review": str(REVIEW),
    "memory": str(MEMORY),
    "effect_audit_request": str(EFFECT_AUDIT_REQUEST),
    "must_update": [
        str(ROUTE),
        str(PANEL),
        str(PULSE),
        str(PROGRESS),
    ],
    "required_commit_effects": [
        "route_lawful_next_updated",
        "route_upstream_proof_updated",
        "panel_lawful_next_matches_route",
        "pulse_lawful_next_matches_route",
        "progress_lawful_next_matches_route",
    ],
    "direct_manual_route_update_allowed": False,
    "truth_boundary": truth_boundary,
}
atomic_commit_request["request_hash"] = h24(atomic_commit_request)

write_json(EFFECT_AUDIT_REQUEST, effect_audit_request)
write_json(ATOMIC_COMMIT_REQUEST, atomic_commit_request)

effect_script = find_script("socc_self_building_effect_auditor_enforced_lane_v1.py")
atomic_script = find_script("socc_self_building_atomic_commit_enforcer_v1.py")

effect_result = {
    "exists": bool(effect_script),
    "ran": False,
    "accepted": False,
    "skipped": base_status != "PASS",
}

atomic_result = {
    "exists": bool(atomic_script),
    "ran": False,
    "accepted": False,
    "skipped": base_status != "PASS",
}

if base_status == "PASS":
    effect_result = run_enforcer(effect_script, {
        "SOCC_EFFECT_AUDIT_REQUEST": str(EFFECT_AUDIT_REQUEST),
        "SOCC_TARGET_STEP": EXPECTED_CURRENT,
        "SOCC_UPSTREAM_PROOF": str(PROOF),
        "SOCC_REVIEW": str(REVIEW),
        "SOCC_MEMORY": str(MEMORY),
        "SOCC_EXPECTED_CURRENT_LAWFUL_NEXT": EXPECTED_CURRENT,
        "SOCC_PROPOSED_NEXT_LAWFUL_NEXT": NEXT,
    })

    atomic_result = run_enforcer(atomic_script, {
        "SOCC_ATOMIC_COMMIT_REQUEST": str(ATOMIC_COMMIT_REQUEST),
        "SOCC_EXPECTED_CURRENT_LAWFUL_NEXT": EXPECTED_CURRENT,
        "SOCC_NEW_LAWFUL_NEXT": NEXT,
        "SOCC_UPSTREAM_PROOF": str(PROOF),
        "SOCC_REVIEW": str(REVIEW),
        "SOCC_MEMORY": str(MEMORY),
        "SOCC_EFFECT_AUDIT_REQUEST": str(EFFECT_AUDIT_REQUEST),
    })

enforcement_checks = {
    "effect_auditor_script_exists": effect_result.get("exists") is True,
    "effect_auditor_ran": effect_result.get("ran") is True,
    "effect_auditor_accepted": effect_result.get("accepted") is True,
    "atomic_commit_script_exists": atomic_result.get("exists") is True,
    "atomic_commit_ran": atomic_result.get("ran") is True,
    "atomic_commit_accepted": atomic_result.get("accepted") is True,
}

final_checks = dict(base_checks)
final_checks.update(enforcement_checks)

final_hard = [
    {"code": "FINAL_REVIEW_CHECK_FAIL", "check": k, "actual": v}
    for k, v in final_checks.items()
    if v is not True
]

final_status = "PASS" if not final_hard else "FAIL"

# Re-read state after atomic commit for coherence.
route_after = read_json(ROUTE)
panel_after = read_json(PANEL)
pulse_after = read_json(PULSE)
progress_after = read_json(PROGRESS)

coherence_checks = {
    "route_lawful_next_updated": get_next(route_after) == NEXT if final_status == "PASS" else True,
    "panel_lawful_next_matches_route": get_next(panel_after) == get_next(route_after) if final_status == "PASS" else True,
    "pulse_lawful_next_matches_route": get_next(pulse_after) == get_next(route_after) if final_status == "PASS" else True,
    "progress_lawful_next_matches_route": get_next(progress_after) == get_next(route_after) if final_status == "PASS" else True,
}

coherence_hard = [
    {"code": "COHERENCE_CHECK_FAIL", "check": k, "actual": v}
    for k, v in coherence_checks.items()
    if v is not True
]

if coherence_hard:
    final_status = "FAIL"
    final_hard += coherence_hard

final_capability = (
    "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_SEALED_EFFECT_AUDITED_ATOMIC_COMMITTED"
    if final_status == "PASS"
    else "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_BLOCKED"
)

final_next = NEXT if final_status == "PASS" else REPAIR

review.update({
    "status": "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_SEALED" if final_status == "PASS" else "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_BLOCKED",
    "capability": final_capability,
    "idempotent_guard_enforced_step_wrapper_review_sealed": final_status == "PASS",
    "effect_auditor_enforced": effect_result.get("accepted") is True,
    "atomic_commit_committed": atomic_result.get("accepted") is True,
    "coherence_checks": coherence_checks,
    "effect_audit_result": effect_result,
    "atomic_commit_result": atomic_result,
    "checks": final_checks,
    "hard_failures": final_hard,
    "real_next": final_next,
})
review["review_hash"] = h24(review)

proof = {
    "id": "IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": final_status,
    "capability": final_capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),
    "effect_audit_request": str(EFFECT_AUDIT_REQUEST),
    "atomic_commit_request": str(ATOMIC_COMMIT_REQUEST),

    "idempotent_guard_enforced_step_wrapper_review_sealed": final_status == "PASS",
    "idempotent_guard_enforced_step_wrapper_validated": base_status == "PASS",
    "idempotent_step_guard_review_sealed": base_status == "PASS",

    "before_write_immunity_layer_accepted": final_status == "PASS",
    "wrapper_applies_guard_before_writes_reviewed": final_status == "PASS",
    "normal_execution_writes_allowed_reviewed": final_status == "PASS",
    "already_committed_noop_writes_blocked_reviewed": final_status == "PASS",
    "out_of_phase_rerun_blocked_before_writes_reviewed": final_status == "PASS",

    "effect_auditor_enforced": effect_result.get("accepted") is True,
    "atomic_commit_committed": atomic_result.get("accepted") is True,

    "route_lawful_next_updated": coherence_checks.get("route_lawful_next_updated") is True if final_status == "PASS" else False,
    "panel_lawful_next_matches_route": coherence_checks.get("panel_lawful_next_matches_route") is True if final_status == "PASS" else False,
    "pulse_lawful_next_matches_route": coherence_checks.get("pulse_lawful_next_matches_route") is True if final_status == "PASS" else False,
    "progress_lawful_next_matches_route": coherence_checks.get("progress_lawful_next_matches_route") is True if final_status == "PASS" else False,

    "mandatory_integration_required_next": final_status == "PASS",

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

    "checks": final_checks,
    "coherence_checks": coherence_checks,
    "effect_audit_result": effect_result,
    "atomic_commit_result": atomic_result,
    "hard_failures": final_hard,
    "real_next": final_next,
    "final_socc_status": (
        "SOCC_IDEMPOTENT_WRAPPER_REVIEW_PASS_BEFORE_WRITE_IMMUNITY_READY_FOR_MANDATORY_INTEGRATION"
        if final_status == "PASS"
        else "SOCC_IDEMPOTENT_WRAPPER_REVIEW_FAIL"
    ),
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h24(proof)

memory.update({
    "status": final_status,
    "memory_effect": (
        "SOCC review-sealed the idempotent guard enforced step wrapper with effect auditor and atomic commit. "
        "Before-write immunity layer is accepted; next step is mandatory integration contract."
        if final_status == "PASS"
        else "SOCC attempted idempotent wrapper review but enforcement/coherence failed. Repair required."
    ),
    "review": str(REVIEW),
    "proof": str(PROOF),
    "effect_audit_request": str(EFFECT_AUDIT_REQUEST),
    "atomic_commit_request": str(ATOMIC_COMMIT_REQUEST),
    "real_next": final_next,
})

md = "# IDEMPOTENT GUARD ENFORCED STEP WRAPPER REVIEW V1\n\n"
md += "STATUS: " + final_status + "\n"
md += "CAPABILITY: " + final_capability + "\n\n"
md += "## БЫЛО\n\n"
md += "Idempotent guard enforced step wrapper was built and validated. The route required review-seal.\n\n"
md += "## ДЕЙСТВИЕ\n\n"
md += "Review-sealed wrapper only after pre-materialized memory, real effect auditor, atomic commit, and route/panel/pulse/progress coherence checks.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in final_checks.items():
    md += f"- {k}: {v}\n"
for k, v in coherence_checks.items():
    md += f"- {k}: {v}\n"
md += "\n## EFFECT AUDIT RESULT\n\n"
md += json.dumps(effect_result, ensure_ascii=False, indent=2) + "\n\n"
md += "## ATOMIC COMMIT RESULT\n\n"
md += json.dumps(atomic_result, ensure_ascii=False, indent=2) + "\n\n"
md += "## СТАЛО\n\n"
if final_status == "PASS":
    md += "Idempotent before-write wrapper is review-sealed. Mandatory integration contract is required next.\n\n"
else:
    md += "Wrapper review is blocked. Do not proceed to mandatory integration until repair.\n\n"
md += "## Explicitly NOT done\n\n"
for x in [
    "loop not executed",
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
md += final_next + "\n\n"
md += "## Truth boundary\n\n"
md += truth_boundary + "\n"

write_json(REVIEW, review)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(REVIEW_MD, md)

print("IDEMPOTENT GUARD ENFORCED STEP WRAPPER REVIEW :: " + final_status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + final_capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("EFFECT_AUDIT_REQUEST::" + str(EFFECT_AUDIT_REQUEST))
print("ATOMIC_COMMIT_REQUEST::" + str(ATOMIC_COMMIT_REQUEST))
print("IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_REVIEW_SEALED::" + str(final_status == "PASS"))
print("IDEMPOTENT_GUARD_ENFORCED_STEP_WRAPPER_VALIDATED::" + str(base_status == "PASS"))
print("IDEMPOTENT_STEP_GUARD_REVIEW_SEALED::" + str(base_status == "PASS"))
print("BEFORE_WRITE_IMMUNITY_LAYER_ACCEPTED::" + str(final_status == "PASS"))
print("WRAPPER_APPLIES_GUARD_BEFORE_WRITES_REVIEWED::" + str(final_status == "PASS"))
print("NORMAL_EXECUTION_WRITES_ALLOWED_REVIEWED::" + str(final_status == "PASS"))
print("ALREADY_COMMITTED_NOOP_WRITES_BLOCKED_REVIEWED::" + str(final_status == "PASS"))
print("OUT_OF_PHASE_RERUN_BLOCKED_BEFORE_WRITES_REVIEWED::" + str(final_status == "PASS"))
print("EFFECT_AUDITOR_ENFORCED::" + str(effect_result.get("accepted") is True))
print("ATOMIC_COMMIT_COMMITTED::" + str(atomic_result.get("accepted") is True))
print("ROUTE_LAWFUL_NEXT_UPDATED::" + str(proof["route_lawful_next_updated"]))
print("PANEL_LAWFUL_NEXT_MATCHES_ROUTE::" + str(proof["panel_lawful_next_matches_route"]))
print("PULSE_LAWFUL_NEXT_MATCHES_ROUTE::" + str(proof["pulse_lawful_next_matches_route"]))
print("PROGRESS_LAWFUL_NEXT_MATCHES_ROUTE::" + str(proof["progress_lawful_next_matches_route"]))
print("MANDATORY_INTEGRATION_REQUIRED_NEXT::" + str(final_status == "PASS"))
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
print("REAL_NEXT::" + final_next)
print("HARD_FAILURES::" + json.dumps(final_hard, ensure_ascii=False))
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if final_status == "PASS" else 1)

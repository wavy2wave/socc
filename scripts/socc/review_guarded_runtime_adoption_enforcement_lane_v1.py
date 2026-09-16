import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

EXPECTED_CURRENT = "review_guarded_runtime_adoption_enforcement_lane_v1"
NEXT = "build_controlled_loop_candidate_contract_v1"
REPAIR = "repair_review_guarded_runtime_adoption_enforcement_lane_v1"

ROUTE = ROOT / "core/socc/approved_autonomy_lane_runner/CURRENT_ROUTE_AUTHORITY.json"
PANEL = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_STATUS_PANEL_V1.json"
PULSE = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PULSE_V1.json"
PROGRESS = ROOT / "core/socc/approved_autonomy_lane_runner/SELF_BUILDING_PROGRESS_LEDGER_V1.json"

VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_VALIDATION_V1_PROOF.json"
BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_V1_PROOF.json"
ROUTE_REPAIR_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_VALIDATION_ROUTE_TRANSITION_REPAIR_V1_PROOF.json"
RUNTIME_ADOPTION_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/IDEMPOTENT_GUARD_WRAPPER_MANDATORY_RUNTIME_ADOPTION_CONTRACT_REVIEW_V1_PROOF.json"

BASE = ROOT / "core/socc/idempotent_guard/runtime_adoption/enforcement_lane"
LANE = BASE / "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_V1.json"
LANE_SCOPE = BASE / "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_SCOPE_V1.json"
CHECKS_SPEC = BASE / "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_CHECKS_V1.json"
BYPASS_DETECTOR = BASE / "RUNTIME_WRAPPER_BYPASS_DETECTOR_V1.json"
COMPLIANCE_PROOF_SPEC = BASE / "RUNTIME_ADOPTION_COMPLIANCE_PROOF_SPEC_V1.json"
FAIL_CLOSED_ENFORCEMENT = BASE / "GUARDED_RUNTIME_FAIL_CLOSED_ENFORCEMENT_V1.json"

REVIEW_DIR = BASE / "review"
REVIEW = REVIEW_DIR / "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_V1.json"
REVIEW_MD = REVIEW_DIR / "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/idempotent_guard/GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_V1_MEMORY.json"

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

validation = read_json(VALIDATION_PROOF)
build = read_json(BUILD_PROOF)
route_repair = read_json(ROUTE_REPAIR_PROOF)
runtime_adoption_review = read_json(RUNTIME_ADOPTION_REVIEW_PROOF)

lane = read_json(LANE)
lane_scope = read_json(LANE_SCOPE)
checks_spec = read_json(CHECKS_SPEC)
bypass_detector = read_json(BYPASS_DETECTOR)
compliance_spec = read_json(COMPLIANCE_PROOF_SPEC)
fail_closed = read_json(FAIL_CLOSED_ENFORCEMENT)

truth_boundary = (
    "Review-seal only. This review-seals the guarded runtime adoption enforcement lane. "
    "It does not execute runtime, does not launch loop, does not start daemon/scheduler/background autonomy, "
    "does not widen queue, does not birth Entity/ANNA, does not approve final canon, and does not claim AGI. "
    "After this review-seal, the lawful next architectural layer is controlled loop candidate contract build only."
)

checks = {
    "route_exists": ROUTE.exists(),
    "route_lawful_next_ok": get_next(route) == EXPECTED_CURRENT,
    "route_upstream_points_to_validation_proof": route.get("upstream_proof") == str(VALIDATION_PROOF),

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": status_pass(validation),
    "validation_capability_ok": validation.get("capability") == "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_VALIDATED",
    "validation_real_next_ok": get_next(validation) == EXPECTED_CURRENT,
    "validation_hard_failures_empty": validation.get("hard_failures") == [],
    "validation_ready_for_review": validation.get("ready_for_review") is True,

    "guarded_runtime_adoption_enforcement_lane_validated": validation.get("guarded_runtime_adoption_enforcement_lane_validated") is True,
    "runtime_wrapper_bypass_detector_validated": validation.get("runtime_wrapper_bypass_detector_validated") is True,
    "runtime_adoption_compliance_proof_spec_validated": validation.get("runtime_adoption_compliance_proof_spec_validated") is True,
    "guarded_runtime_fail_closed_enforcement_validated": validation.get("guarded_runtime_fail_closed_enforcement_validated") is True,
    "runtime_runner_compliance_enforceable_validated": validation.get("runtime_runner_compliance_enforceable_validated") is True,
    "tick_wrapper_compliance_enforceable_validated": validation.get("tick_wrapper_compliance_enforceable_validated") is True,
    "future_loop_wrapper_compliance_enforceable_validated": validation.get("future_loop_wrapper_compliance_enforceable_validated") is True,

    "build_proof_exists": BUILD_PROOF.exists(),
    "build_status_pass": status_pass(build),
    "build_lane_built": build.get("guarded_runtime_adoption_enforcement_lane_built") is True,

    "route_repair_proof_exists": ROUTE_REPAIR_PROOF.exists(),
    "route_repair_status_pass": status_pass(route_repair),
    "route_repair_updated_to_review": route_repair.get("route_lawful_next_updated_to_review") is True,

    "runtime_adoption_review_proof_exists": RUNTIME_ADOPTION_REVIEW_PROOF.exists(),
    "runtime_adoption_review_status_pass": status_pass(runtime_adoption_review),
    "runtime_adoption_contract_review_sealed": runtime_adoption_review.get("runtime_adoption_contract_review_sealed") is True,

    "lane_exists": LANE.exists(),
    "lane_scope_exists": LANE_SCOPE.exists(),
    "checks_spec_exists": CHECKS_SPEC.exists(),
    "bypass_detector_exists": BYPASS_DETECTOR.exists(),
    "compliance_proof_spec_exists": COMPLIANCE_PROOF_SPEC.exists(),
    "fail_closed_enforcement_exists": FAIL_CLOSED_ENFORCEMENT.exists(),

    "lane_status_built": lane.get("status") == "BUILT",
    "lane_capability_ok": lane.get("capability") == "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_BUILT",
    "lane_built": lane.get("guarded_runtime_adoption_enforcement_lane_built") is True,
    "bypass_detector_built": lane.get("runtime_wrapper_bypass_detector_built") is True,
    "compliance_proof_spec_built": lane.get("runtime_adoption_compliance_proof_spec_built") is True,
    "fail_closed_enforcement_built": lane.get("guarded_runtime_fail_closed_enforcement_built") is True,

    "review_does_not_execute_runtime": True,
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
    ("lane", lane),
]:
    for key in FORBIDDEN_FLAGS:
        checks[f"{label}_{key}_false_or_absent"] = false_or_absent(obj, key)

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

capability = (
    "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_SEALED"
    if status == "PASS"
    else "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_BLOCKED"
)

real_next = NEXT if status == "PASS" else REPAIR

review = {
    "id": "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "REVIEW_SEALED" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "source_validation_proof": str(VALIDATION_PROOF),
    "source_build_proof": str(BUILD_PROOF),
    "source_route_repair_proof": str(ROUTE_REPAIR_PROOF),
    "source_runtime_adoption_review_proof": str(RUNTIME_ADOPTION_REVIEW_PROOF),
    "source_lane": str(LANE),
    "source_checks_spec": str(CHECKS_SPEC),
    "source_bypass_detector": str(BYPASS_DETECTOR),
    "source_compliance_proof_spec": str(COMPLIANCE_PROOF_SPEC),
    "source_fail_closed_enforcement": str(FAIL_CLOSED_ENFORCEMENT),

    "guarded_runtime_adoption_enforcement_lane_review_sealed": status == "PASS",
    "guarded_runtime_adoption_enforcement_lane_validated": status == "PASS",
    "runtime_wrapper_bypass_detector_reviewed": status == "PASS",
    "runtime_adoption_compliance_proof_spec_reviewed": status == "PASS",
    "guarded_runtime_fail_closed_enforcement_reviewed": status == "PASS",
    "runtime_runner_compliance_enforceable_reviewed": status == "PASS",
    "tick_wrapper_compliance_enforceable_reviewed": status == "PASS",
    "future_loop_wrapper_compliance_enforceable_reviewed": status == "PASS",

    "controlled_loop_candidate_contract_required_next": status == "PASS",

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
    "real_next": real_next,
    "truth_boundary": truth_boundary
}
review["review_hash"] = h24(review)

proof = {
    "id": "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "review": str(REVIEW),
    "review_md": str(REVIEW_MD),
    "memory": str(MEMORY),

    "guarded_runtime_adoption_enforcement_lane_review_sealed": status == "PASS",
    "guarded_runtime_adoption_enforcement_lane_validated": status == "PASS",
    "runtime_wrapper_bypass_detector_reviewed": status == "PASS",
    "runtime_adoption_compliance_proof_spec_reviewed": status == "PASS",
    "guarded_runtime_fail_closed_enforcement_reviewed": status == "PASS",
    "runtime_runner_compliance_enforceable_reviewed": status == "PASS",
    "tick_wrapper_compliance_enforceable_reviewed": status == "PASS",
    "future_loop_wrapper_compliance_enforceable_reviewed": status == "PASS",

    "controlled_loop_candidate_contract_required_next": status == "PASS",

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
    "real_next": real_next,
    "final_socc_status": (
        "SOCC_GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_PASS_CONTROLLED_LOOP_CANDIDATE_NEXT_NOT_RUNTIME_NOT_LOOP_NOT_DAEMON"
        if status == "PASS"
        else "SOCC_GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_FAIL"
    ),
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC review-sealed guarded runtime adoption enforcement lane. "
        "Controlled loop candidate contract is now the lawful next architecture layer. Runtime/loop/daemon remain disabled."
        if status == "PASS"
        else "Guarded runtime adoption enforcement lane review blocked."
    ),
    "review": str(REVIEW),
    "proof": str(PROOF),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

md = "# GUARDED RUNTIME ADOPTION ENFORCEMENT LANE REVIEW V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nGuarded runtime adoption enforcement lane was built and validated.\n\n"
md += "## ДЕЙСТВИЕ\n\nReview-sealed enforcement lane. Runtime/loop/daemon remain disabled.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += f"- {k}: {v}\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Guarded runtime adoption enforcement lane is review-sealed. Next lawful layer: controlled loop candidate contract.\n\n"
else:
    md += "Guarded runtime adoption enforcement lane review is blocked. Repair required.\n\n"
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
md += "\n## lawful_next\n\n" + real_next + "\n\n"
md += "## Truth boundary\n\n" + truth_boundary + "\n"

write_json(REVIEW, review)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(REVIEW_MD, md)

print("GUARDED RUNTIME ADOPTION ENFORCEMENT LANE REVIEW :: " + status)
print("FINAL_SOCC_STATUS::" + proof["final_socc_status"])
print("CAPABILITY::" + capability)
print("REVIEW::" + str(REVIEW))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_REVIEW_SEALED::" + str(status == "PASS"))
print("GUARDED_RUNTIME_ADOPTION_ENFORCEMENT_LANE_VALIDATED::" + str(status == "PASS"))
print("RUNTIME_WRAPPER_BYPASS_DETECTOR_REVIEWED::" + str(status == "PASS"))
print("RUNTIME_ADOPTION_COMPLIANCE_PROOF_SPEC_REVIEWED::" + str(status == "PASS"))
print("GUARDED_RUNTIME_FAIL_CLOSED_ENFORCEMENT_REVIEWED::" + str(status == "PASS"))
print("RUNTIME_RUNNER_COMPLIANCE_ENFORCEABLE_REVIEWED::" + str(status == "PASS"))
print("TICK_WRAPPER_COMPLIANCE_ENFORCEABLE_REVIEWED::" + str(status == "PASS"))
print("FUTURE_LOOP_WRAPPER_COMPLIANCE_ENFORCEABLE_REVIEWED::" + str(status == "PASS"))
print("CONTROLLED_LOOP_CANDIDATE_CONTRACT_REQUIRED_NEXT::" + str(status == "PASS"))
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
print("REAL_NEXT::" + real_next)
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if status == "PASS" else 1)

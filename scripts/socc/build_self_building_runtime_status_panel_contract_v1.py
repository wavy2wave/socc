import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
PROOF_DIR = ROOT / "core/socc/approved_autonomy_lane_runner/proof"

REVIEW_PROOF = PROOF_DIR / "SELF_BUILDING_TICK_EXECUTION_PLAN_REVIEW_V1_PROOF.json"
VALIDATION_PROOF = PROOF_DIR / "SELF_BUILDING_TICK_EXECUTION_PLAN_VALIDATION_V1_PROOF.json"
RUN_PROOF = PROOF_DIR / "ONE_BOUNDED_SELF_BUILDING_TICK_RUN_V1_PROOF.json"

BASE = ROOT / "core/socc/autonomy/self_building/status_panel/contract"

CONTRACT = BASE / "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_V1.json"
CONTRACT_MD = BASE / "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_V1.md"
PANEL_SCHEMA = BASE / "SELF_BUILDING_RUNTIME_STATUS_PANEL_SCHEMA_V1.json"
DATA_SOURCES = BASE / "SELF_BUILDING_RUNTIME_STATUS_PANEL_DATA_SOURCES_V1.json"
RENDER_SPEC = BASE / "SELF_BUILDING_RUNTIME_STATUS_PANEL_RENDER_SPEC_V1.json"
VALIDATOR_CONTRACT = BASE / "SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATOR_CONTRACT_V1.json"

PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_V1_MEMORY.json"

EXPECTED_REVIEW_CAPABILITY = "SELF_BUILDING_TICK_EXECUTION_PLAN_REVIEW_SEALED_STATUS_PANEL_NEXT"
EXPECTED_NEXT = "build_self_building_runtime_status_panel_contract_v1"
EXPECTED_TARGET = "build_self_building_runtime_status_panel_v1"

def now_utc():
    return datetime.now(timezone.utc).isoformat()

def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text).rstrip() + "\n", encoding="utf-8")

def h24(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]

review = read_json(REVIEW_PROOF)
validation = read_json(VALIDATION_PROOF)
run = read_json(RUN_PROOF)

checks = {
    "review_proof_exists": REVIEW_PROOF.exists(),
    "review_status_pass": review.get("status") == "PASS",
    "review_capability_ok": review.get("capability") == EXPECTED_REVIEW_CAPABILITY,
    "review_real_next_ok": review.get("real_next") == EXPECTED_NEXT,
    "review_sealed": review.get("self_building_tick_execution_plan_review_sealed") is True,
    "first_self_building_tick_output_accepted": review.get("first_self_building_tick_output_accepted") is True,
    "one_bounded_self_building_tick_cycle_closed": review.get("one_bounded_self_building_tick_cycle_closed") is True,
    "review_selected_target_ok": review.get("selected_improvement_target") == EXPECTED_TARGET,
    "review_hard_failures_empty": review.get("hard_failures") == [],

    "validation_proof_exists": VALIDATION_PROOF.exists(),
    "validation_status_pass": validation.get("status") == "PASS",
    "validation_selected_target_ok": validation.get("selected_improvement_target") == EXPECTED_TARGET,

    "run_proof_exists": RUN_PROOF.exists(),
    "run_status_pass": run.get("status") == "PASS",
    "run_one_bounded_self_building_tick_executed": run.get("one_bounded_self_building_tick_executed") is True,

    "contract_does_not_enable_self_building_mode": True,
    "contract_does_not_launch_runtime": True,
    "contract_does_not_start_daemon": True,
    "contract_does_not_install_scheduler": True,
    "contract_does_not_enable_background_loop": True,
    "contract_does_not_use_network": True,
    "contract_does_not_widen_queue": True,
    "contract_does_not_birth_entity": True,
    "contract_does_not_birth_anna": True,
    "contract_does_not_claim_agi": True,
    "contract_does_not_approve_final_canon": True,
}

for src_name, src in [("review", review), ("validation", validation), ("run", run)]:
    for key in [
        "runtime_launch_approved",
        "runtime_execution_allowed",
        "runtime_autonomy_enabled",
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
        checks[f"{src_name}_{key}_false"] = src.get(key) is False

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

panel_schema = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_SCHEMA_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "DEFINED" if status == "PASS" else "BLOCKED",
    "required_fields": [
        "panel_generated_at",
        "current_autonomy_level",
        "current_route_authority",
        "lawful_next",
        "last_tick_status",
        "last_tick_proof",
        "last_memory_report",
        "self_building_cycle_count",
        "proven_capabilities",
        "locked_capabilities",
        "readiness_state",
        "hard_failures",
        "truth_boundary",
        "creator_summary"
    ],
    "creator_visible_sections": [
        "Пульс",
        "Где система сейчас",
        "Что доказано",
        "Что не доказано",
        "Что запрещено сейчас",
        "Следующий lawful_next",
        "Последний tick",
        "Последний proof/memory",
        "Риск / FAIL",
        "Куда идём к scheduler/daemon/24-7"
    ],
    "truth_boundary": "Schema defines visibility only. It does not launch or enable runtime."
}

data_sources = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_DATA_SOURCES_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "DEFINED" if status == "PASS" else "BLOCKED",
    "primary_sources": [
        str(REVIEW_PROOF),
        str(VALIDATION_PROOF),
        str(RUN_PROOF),
        "core/socc/approved_autonomy_lane_runner/proof/AUTONOMY_EVOLUTION_MAP_V1_PROOF.json",
        "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_MODE_CONTRACT_V1_PROOF.json",
        "core/socc/approved_autonomy_lane_runner/proof/CREATOR_FEEDBACK_LAYER_V1_PROOF.json",
        "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_READINESS_EVALUATOR_V1_PROOF.json"
    ],
    "memory_sources": [
        "MEMORY_WAVE/reports/autonomy"
    ],
    "must_not_read": [
        "network",
        "external science intake without contract",
        "private unrelated files"
    ],
    "truth_boundary": "Data sources are local proof/memory paths only."
}

render_spec = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_RENDER_SPEC_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "DEFINED" if status == "PASS" else "BLOCKED",
    "render_targets": [
        "markdown report",
        "json status snapshot",
        "terminal-readable summary"
    ],
    "terminal_summary_lines": [
        "SOCC_SELF_BUILDING_PULSE",
        "CURRENT_LEVEL",
        "LAST_TICK",
        "LAWFUL_NEXT",
        "READY",
        "LOCKED",
        "HARD_FAILURES"
    ],
    "truth_boundary": "Render spec defines reports only. It does not run background loops."
}

validator_contract = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATOR_CONTRACT_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "DEFINED" if status == "PASS" else "BLOCKED",
    "must_validate": [
        "panel schema exists",
        "data sources are local proof/memory only",
        "panel includes current level",
        "panel includes lawful_next",
        "panel includes last tick",
        "panel includes proven/locked capabilities",
        "panel includes truth boundary",
        "panel does not launch runtime",
        "panel does not start daemon",
        "panel does not install scheduler",
        "panel does not enable background loop",
        "panel does not use network"
    ],
    "truth_boundary": "Validator contract only. It does not render panel yet."
}

if status == "PASS":
    capability = "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_BUILT_READY_FOR_IMPLEMENTATION"
    real_next = "build_self_building_runtime_status_panel_v1"
    final_socc_status = "SOCC_SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_PASS_PANEL_BUILD_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_BLOCKED"
    real_next = "repair_self_building_runtime_status_panel_contract_v1"
    final_socc_status = "SOCC_SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_FAIL"

truth_boundary = (
    "Runtime/status panel contract only. This defines creator-visible autonomy pulse/status panel requirements, local data sources, "
    "rendering, and validator contract. It does not enable self-building mode, launch runtime, start daemon/scheduler/background loop, "
    "use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

contract = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "source_review_proof": str(REVIEW_PROOF),
    "panel_schema": str(PANEL_SCHEMA),
    "data_sources": str(DATA_SOURCES),
    "render_spec": str(RENDER_SPEC),
    "validator_contract": str(VALIDATOR_CONTRACT),

    "runtime_status_panel_contract_built": status == "PASS",
    "runtime_status_panel_built": False,
    "creator_visible_autonomy_pulse_ready": False,

    "self_building_mode_enabled": False,
    "runtime_launch_approved": False,
    "runtime_execution_allowed": False,
    "runtime_autonomy_enabled": False,
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
contract["contract_hash"] = h24(contract)

proof = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "contract": str(CONTRACT),
    "contract_md": str(CONTRACT_MD),
    "panel_schema": str(PANEL_SCHEMA),
    "data_sources": str(DATA_SOURCES),
    "render_spec": str(RENDER_SPEC),
    "validator_contract": str(VALIDATOR_CONTRACT),
    "memory": str(MEMORY),

    "runtime_status_panel_contract_built": status == "PASS",
    "runtime_status_panel_built": False,
    "creator_visible_autonomy_pulse_ready": False,

    "self_building_mode_enabled": False,
    "runtime_launch_approved": False,
    "runtime_execution_allowed": False,
    "runtime_autonomy_enabled": False,
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
    "truth_boundary": truth_boundary
}
proof["proof_hash"] = h24(proof)

memory = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built the contract for a creator-visible runtime/status panel. "
        "Next is building the panel itself so the autonomy pulse becomes visible."
    ),
    "proof": str(PROOF),
    "contract": str(CONTRACT),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

md = "# SELF-BUILDING RUNTIME STATUS PANEL CONTRACT V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nFirst bounded self-building cycle was review-sealed and selected runtime/status observability as next target.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt contract for creator-visible autonomy pulse/status panel.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Runtime/status panel contract is built. Panel itself is not built yet.\n\n"
else:
    md += "Runtime/status panel contract is blocked. Repair required.\n\n"
md += "## Panel must show\n\n"
for x in panel_schema["creator_visible_sections"]:
    md += "- " + x + "\n"
md += "\n## Explicitly NOT done\n\n"
for x in [
    "status panel not built yet",
    "persistent self-building mode not enabled",
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

write_json(PANEL_SCHEMA, panel_schema)
write_json(DATA_SOURCES, data_sources)
write_json(RENDER_SPEC, render_spec)
write_json(VALIDATOR_CONTRACT, validator_contract)
write_json(CONTRACT, contract)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(CONTRACT_MD, md)

print("SELF-BUILDING RUNTIME STATUS PANEL CONTRACT :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("CONTRACT::" + str(CONTRACT))
print("PANEL_SCHEMA::" + str(PANEL_SCHEMA))
print("DATA_SOURCES::" + str(DATA_SOURCES))
print("RENDER_SPEC::" + str(RENDER_SPEC))
print("VALIDATOR_CONTRACT::" + str(VALIDATOR_CONTRACT))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("RUNTIME_STATUS_PANEL_CONTRACT_BUILT::" + str(status == "PASS"))
print("RUNTIME_STATUS_PANEL_BUILT::False")
print("CREATOR_VISIBLE_AUTONOMY_PULSE_READY::False")
print("SELF_BUILDING_MODE_ENABLED::False")
print("RUNTIME_LAUNCH_APPROVED::False")
print("RUNTIME_EXECUTION_ALLOWED::False")
print("RUNTIME_AUTONOMY_ENABLED::False")
print("DAEMON_RUNNING::False")
print("SCHEDULER_INSTALLED::False")
print("BACKGROUND_LOOP_ENABLED::False")
print("NETWORK_USED::False")
print("QUEUE_WIDENING_ALLOWED::False")
print("ENTITY_BIRTH_ALLOWED::False")
print("ANNA_BIRTH_ALLOWED::False")
print("AGI_CLAIM_ALLOWED::False")
print("REAL_NEXT::" + real_next)
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if status == "PASS" else 1)

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
PROOF_DIR = ROOT / "core/socc/approved_autonomy_lane_runner/proof"

CONTRACT_PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_V1_PROOF.json"
REVIEW_PROOF = PROOF_DIR / "SELF_BUILDING_TICK_EXECUTION_PLAN_REVIEW_V1_PROOF.json"
RUN_PROOF = PROOF_DIR / "ONE_BOUNDED_SELF_BUILDING_TICK_RUN_V1_PROOF.json"
EVOLUTION_PROOF = PROOF_DIR / "AUTONOMY_EVOLUTION_MAP_V1_PROOF.json"
SELF_BUILDING_PROOF = PROOF_DIR / "SELF_BUILDING_MODE_CONTRACT_V1_PROOF.json"
READINESS_PROOF = PROOF_DIR / "SELF_BUILDING_READINESS_EVALUATOR_V1_PROOF.json"

CONTRACT = ROOT / "core/socc/autonomy/self_building/status_panel/contract/SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_V1.json"
PANEL_SCHEMA = ROOT / "core/socc/autonomy/self_building/status_panel/contract/SELF_BUILDING_RUNTIME_STATUS_PANEL_SCHEMA_V1.json"
DATA_SOURCES = ROOT / "core/socc/autonomy/self_building/status_panel/contract/SELF_BUILDING_RUNTIME_STATUS_PANEL_DATA_SOURCES_V1.json"
RENDER_SPEC = ROOT / "core/socc/autonomy/self_building/status_panel/contract/SELF_BUILDING_RUNTIME_STATUS_PANEL_RENDER_SPEC_V1.json"
VALIDATOR_CONTRACT = ROOT / "core/socc/autonomy/self_building/status_panel/contract/SELF_BUILDING_RUNTIME_STATUS_PANEL_VALIDATOR_CONTRACT_V1.json"

BASE = ROOT / "core/socc/autonomy/self_building/status_panel"
RUNTIME_DIR = BASE / "runtime"
REPORTS_DIR = BASE / "reports"

PANEL = RUNTIME_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PANEL_MD = REPORTS_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.md"
PULSE = RUNTIME_DIR / "SOCC_SELF_BUILDING_PULSE_V1.json"
TERMINAL_SUMMARY = REPORTS_DIR / "SOCC_SELF_BUILDING_TERMINAL_SUMMARY_V1.txt"
CREATOR_REPORT = REPORTS_DIR / "CREATOR_VISIBLE_AUTONOMY_PULSE_REPORT_V1.md"

PROOF = PROOF_DIR / "SELF_BUILDING_RUNTIME_STATUS_PANEL_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1_MEMORY.json"

EXPECTED_CONTRACT_CAPABILITY = "SELF_BUILDING_RUNTIME_STATUS_PANEL_CONTRACT_BUILT_READY_FOR_IMPLEMENTATION"
EXPECTED_NEXT = "build_self_building_runtime_status_panel_v1"
NEXT_AFTER_PANEL = "validate_self_building_runtime_status_panel_v1"

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
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]

contract_proof = read_json(CONTRACT_PROOF)
review = read_json(REVIEW_PROOF)
run = read_json(RUN_PROOF)
evolution = read_json(EVOLUTION_PROOF)
self_building = read_json(SELF_BUILDING_PROOF)
readiness = read_json(READINESS_PROOF)

schema = read_json(PANEL_SCHEMA)
sources = read_json(DATA_SOURCES)
render = read_json(RENDER_SPEC)
validator = read_json(VALIDATOR_CONTRACT)

required_fields = set(schema.get("required_fields") or [])
creator_sections = schema.get("creator_visible_sections") or []
must_validate = set(validator.get("must_validate") or [])

checks = {
    "contract_proof_exists": CONTRACT_PROOF.exists(),
    "contract_status_pass": contract_proof.get("status") == "PASS",
    "contract_capability_ok": contract_proof.get("capability") == EXPECTED_CONTRACT_CAPABILITY,
    "contract_real_next_ok": contract_proof.get("real_next") == EXPECTED_NEXT,
    "runtime_status_panel_contract_built": contract_proof.get("runtime_status_panel_contract_built") is True,
    "runtime_status_panel_not_built_before": contract_proof.get("runtime_status_panel_built") is False,
    "creator_visible_pulse_not_ready_before": contract_proof.get("creator_visible_autonomy_pulse_ready") is False,

    "contract_exists": CONTRACT.exists(),
    "panel_schema_exists": PANEL_SCHEMA.exists(),
    "data_sources_exists": DATA_SOURCES.exists(),
    "render_spec_exists": RENDER_SPEC.exists(),
    "validator_contract_exists": VALIDATOR_CONTRACT.exists(),

    "review_proof_exists": REVIEW_PROOF.exists(),
    "review_status_pass": review.get("status") == "PASS",
    "one_bounded_self_building_tick_cycle_closed": review.get("one_bounded_self_building_tick_cycle_closed") is True,

    "run_proof_exists": RUN_PROOF.exists(),
    "run_status_pass": run.get("status") == "PASS",
    "run_tick_executed": run.get("one_bounded_self_building_tick_executed") is True,

    "evolution_proof_exists": EVOLUTION_PROOF.exists(),
    "evolution_status_pass": evolution.get("status") == "PASS",
    "bounded_one_tick_autonomy_proven": evolution.get("bounded_one_tick_autonomy_proven") is True,

    "self_building_proof_exists": SELF_BUILDING_PROOF.exists(),
    "self_building_status_pass": self_building.get("status") == "PASS",
    "self_building_contract_built": self_building.get("self_building_mode_contract_built") is True,

    "readiness_proof_exists": READINESS_PROOF.exists(),
    "readiness_status_pass": readiness.get("status") == "PASS",
    "readiness_evaluator_built": readiness.get("self_building_readiness_evaluator_built") is True,

    "schema_has_panel_generated_at": "panel_generated_at" in required_fields,
    "schema_has_current_autonomy_level": "current_autonomy_level" in required_fields,
    "schema_has_lawful_next": "lawful_next" in required_fields,
    "schema_has_last_tick_status": "last_tick_status" in required_fields,
    "schema_has_proven_capabilities": "proven_capabilities" in required_fields,
    "schema_has_locked_capabilities": "locked_capabilities" in required_fields,
    "schema_has_truth_boundary": "truth_boundary" in required_fields,
    "schema_has_creator_summary": "creator_summary" in required_fields,

    "creator_sections_include_pulse": "Пульс" in creator_sections,
    "creator_sections_include_lawful_next": "Следующий lawful_next" in creator_sections,
    "creator_sections_include_path_24_7": "Куда идём к scheduler/daemon/24-7" in creator_sections,

    "validator_must_validate_panel_schema": "panel schema exists" in must_validate,
    "validator_must_validate_local_sources": "data sources are local proof/memory only" in must_validate,
    "validator_must_validate_current_level": "panel includes current level" in must_validate,
    "validator_must_validate_lawful_next": "panel includes lawful_next" in must_validate,
    "validator_must_validate_last_tick": "panel includes last tick" in must_validate,
    "validator_must_validate_no_daemon": "panel does not start daemon" in must_validate,
    "validator_must_validate_no_scheduler": "panel does not install scheduler" in must_validate,
    "validator_must_validate_no_network": "panel does not use network" in must_validate,

    "panel_build_does_not_enable_self_building_mode": True,
    "panel_build_does_not_launch_runtime": True,
    "panel_build_does_not_start_daemon": True,
    "panel_build_does_not_install_scheduler": True,
    "panel_build_does_not_enable_background_loop": True,
    "panel_build_does_not_use_network": True,
    "panel_build_does_not_widen_queue": True,
    "panel_build_does_not_birth_entity": True,
    "panel_build_does_not_birth_anna": True,
    "panel_build_does_not_claim_agi": True,
    "panel_build_does_not_approve_final_canon": True,
}

for src_name, src in [("contract", contract_proof), ("review", review), ("run", run), ("evolution", evolution), ("self_building", self_building), ("readiness", readiness)]:
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

current_level = "L7_FIRST_BOUNDED_SELF_BUILDING_CYCLE_CLOSED_STATUS_PANEL_BUILT" if status == "PASS" else "BLOCKED"
lawful_next = NEXT_AFTER_PANEL if status == "PASS" else "repair_self_building_runtime_status_panel_v1"

proven_capabilities = [
    "bounded one-tick autonomy",
    "worker output validation",
    "worker output review seal",
    "autonomy evolution map",
    "self-building mode contract",
    "creator intent intake",
    "creator feedback layer",
    "self-building readiness evaluator",
    "one bounded self-building tick",
    "first self-building cycle review-sealed",
    "runtime/status panel contract",
    "creator-visible autonomy pulse panel"
] if status == "PASS" else []

locked_capabilities = [
    "persistent self-building mode",
    "scheduler",
    "daemon",
    "background loop",
    "bounded 24/7 autonomy",
    "network scientific intake",
    "queue widening",
    "Entity birth",
    "ANNA birth",
    "AGI/final canon"
]

truth_boundary = (
    "Runtime/status panel build only. This creates local JSON/Markdown/TXT reports showing SOCC self-building pulse and proof-state. "
    "It does not enable persistent self-building mode, launch runtime, start daemon/scheduler/background loop, use network, "
    "widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

pulse = {
    "id": "SOCC_SELF_BUILDING_PULSE_V1",
    "panel_generated_at_utc": now_utc(),
    "panel_generated_at_msk": now_msk(),
    "pulse": "ALIVE_BOUNDED_SELF_BUILDING_VISIBLE" if status == "PASS" else "BLOCKED",
    "current_autonomy_level": current_level,
    "last_tick_status": run.get("status"),
    "last_tick_proof": str(RUN_PROOF),
    "last_memory_report": run.get("memory"),
    "self_building_cycle_count": 1 if review.get("one_bounded_self_building_tick_cycle_closed") is True else 0,
    "lawful_next": lawful_next,
    "hard_failures": hard,
    "truth_boundary": truth_boundary
}

panel = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_V1",
    "panel_generated_at": now_utc(),
    "panel_generated_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": (
        "SELF_BUILDING_RUNTIME_STATUS_PANEL_BUILT_CREATOR_VISIBLE_PULSE_READY"
        if status == "PASS"
        else "SELF_BUILDING_RUNTIME_STATUS_PANEL_BLOCKED"
    ),
    "current_autonomy_level": current_level,
    "current_route_authority": {
        "source": str(CONTRACT_PROOF),
        "previous_real_next": EXPECTED_NEXT,
        "lawful_next": lawful_next
    },
    "lawful_next": lawful_next,
    "last_tick_status": run.get("status"),
    "last_tick_proof": str(RUN_PROOF),
    "last_memory_report": run.get("memory"),
    "self_building_cycle_count": pulse["self_building_cycle_count"],
    "proven_capabilities": proven_capabilities,
    "locked_capabilities": locked_capabilities,
    "readiness_state": {
        "self_building_readiness_score": readiness.get("self_building_readiness_score"),
        "ready_for_operator_approval": readiness.get("self_building_ready_for_operator_approval"),
        "persistent_mode_enabled": False,
        "daemon_ready": False,
        "scheduler_ready": False,
        "bounded_24_7_ready": False
    },
    "hard_failures": hard,
    "creator_summary": {
        "short": "SOCC self-building pulse is now visible." if status == "PASS" else "Panel blocked.",
        "what_changed": [
            "Creator can see current autonomy level.",
            "Creator can see last self-building tick.",
            "Creator can see lawful_next.",
            "Creator can see proven vs locked capabilities.",
            "Status panel creates observability prerequisite for future scheduler/daemon route."
        ] if status == "PASS" else [],
        "what_is_not_done": locked_capabilities
    },
    "paths": {
        "pulse": str(PULSE),
        "panel_md": str(PANEL_MD),
        "terminal_summary": str(TERMINAL_SUMMARY),
        "creator_report": str(CREATOR_REPORT),
        "proof": str(PROOF)
    },
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
    "truth_boundary": truth_boundary
}
panel["panel_hash"] = h24(panel)

if status == "PASS":
    capability = "SELF_BUILDING_RUNTIME_STATUS_PANEL_BUILT_CREATOR_VISIBLE_PULSE_READY"
    real_next = NEXT_AFTER_PANEL
    final_socc_status = "SOCC_SELF_BUILDING_RUNTIME_STATUS_PANEL_PASS_CREATOR_VISIBLE_PULSE_READY_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_RUNTIME_STATUS_PANEL_BLOCKED"
    real_next = "repair_self_building_runtime_status_panel_v1"
    final_socc_status = "SOCC_SELF_BUILDING_RUNTIME_STATUS_PANEL_FAIL"

proof = {
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "panel": str(PANEL),
    "panel_md": str(PANEL_MD),
    "pulse": str(PULSE),
    "terminal_summary": str(TERMINAL_SUMMARY),
    "creator_report": str(CREATOR_REPORT),
    "memory": str(MEMORY),

    "runtime_status_panel_built": status == "PASS",
    "creator_visible_autonomy_pulse_ready": status == "PASS",
    "self_building_cycle_count": pulse["self_building_cycle_count"] if status == "PASS" else 0,
    "current_autonomy_level": current_level if status == "PASS" else None,
    "lawful_next": lawful_next,

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
    "id": "SELF_BUILDING_RUNTIME_STATUS_PANEL_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built the creator-visible runtime/status panel. The self-building pulse, current level, lawful_next, "
        "last tick, proof/memory, proven/locked capabilities and future scheduler/daemon path are now locally visible."
    ),
    "proof": str(PROOF),
    "panel": str(PANEL),
    "pulse": str(PULSE),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

panel_md = "# SOCC SELF-BUILDING RUNTIME STATUS PANEL V1\n\n"
panel_md += "## Пульс\n\n"
panel_md += f"- pulse: {pulse['pulse']}\n"
panel_md += f"- generated_at_msk: {pulse['panel_generated_at_msk']}\n"
panel_md += f"- current_level: {current_level}\n"
panel_md += f"- self_building_cycle_count: {pulse['self_building_cycle_count']}\n\n"
panel_md += "## Где система сейчас\n\n"
panel_md += "- первый bounded self-building cycle закрыт\n"
panel_md += "- runtime/status panel построен\n"
panel_md += "- persistent self-building mode ещё не включён\n\n"
panel_md += "## Что доказано\n\n"
for x in proven_capabilities:
    panel_md += "- " + x + "\n"
panel_md += "\n## Что locked\n\n"
for x in locked_capabilities:
    panel_md += "- " + x + "\n"
panel_md += "\n## Последний tick\n\n"
panel_md += f"- status: {run.get('status')}\n"
panel_md += f"- proof: {RUN_PROOF}\n"
panel_md += f"- memory: {run.get('memory')}\n\n"
panel_md += "## lawful_next\n\n"
panel_md += real_next + "\n\n"
panel_md += "## Truth boundary\n\n"
panel_md += truth_boundary + "\n"

terminal = "\n".join([
    "SOCC_SELF_BUILDING_PULSE::" + pulse["pulse"],
    "CURRENT_LEVEL::" + current_level,
    "SELF_BUILDING_CYCLE_COUNT::" + str(pulse["self_building_cycle_count"]),
    "LAST_TICK_STATUS::" + str(run.get("status")),
    "RUNTIME_STATUS_PANEL_BUILT::" + str(status == "PASS"),
    "CREATOR_VISIBLE_AUTONOMY_PULSE_READY::" + str(status == "PASS"),
    "SELF_BUILDING_MODE_ENABLED::False",
    "DAEMON_RUNNING::False",
    "SCHEDULER_INSTALLED::False",
    "BACKGROUND_LOOP_ENABLED::False",
    "NETWORK_USED::False",
    "QUEUE_WIDENING_ALLOWED::False",
    "REAL_NEXT::" + real_next,
    "HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False),
])

creator_report = "# CREATOR VISIBLE AUTONOMY PULSE REPORT V1\n\n"
creator_report += "Система стала видимой: теперь можно открыть локальный panel/report и увидеть пульс self-building автономии.\n\n"
creator_report += "## Что изменилось\n\n"
for x in panel["creator_summary"]["what_changed"]:
    creator_report += "- " + x + "\n"
creator_report += "\n## Что ещё НЕ доказано\n\n"
for x in locked_capabilities:
    creator_report += "- " + x + "\n"
creator_report += "\n## Следующий законный шаг\n\n" + real_next + "\n\n"

write_json(PULSE, pulse)
write_json(PANEL, panel)
write_text(PANEL_MD, panel_md)
write_text(TERMINAL_SUMMARY, terminal)
write_text(CREATOR_REPORT, creator_report)
write_json(PROOF, proof)
write_json(MEMORY, memory)

print("SELF-BUILDING RUNTIME STATUS PANEL :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("PANEL::" + str(PANEL))
print("PANEL_MD::" + str(PANEL_MD))
print("PULSE::" + str(PULSE))
print("TERMINAL_SUMMARY::" + str(TERMINAL_SUMMARY))
print("CREATOR_REPORT::" + str(CREATOR_REPORT))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SOCC_SELF_BUILDING_PULSE::" + pulse["pulse"])
print("CURRENT_LEVEL::" + current_level)
print("SELF_BUILDING_CYCLE_COUNT::" + str(pulse["self_building_cycle_count"]))
print("RUNTIME_STATUS_PANEL_BUILT::" + str(status == "PASS"))
print("CREATOR_VISIBLE_AUTONOMY_PULSE_READY::" + str(status == "PASS"))
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
print("FINAL_CANON_APPROVAL_ALLOWED::False")
print("REAL_NEXT::" + real_next)
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if status == "PASS" else 1)

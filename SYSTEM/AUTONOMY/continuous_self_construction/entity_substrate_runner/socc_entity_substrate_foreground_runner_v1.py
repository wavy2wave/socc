#!/usr/bin/env python3
import json, hashlib
from pathlib import Path
from datetime import datetime, timezone

CURRENT = "run_continuous_foreground_self_construction_runner_for_entity_substrate_v1"
NEXT = "review_entity_substrate_construction_plan_v1"

AUTHORITY_FILES = [
    Path("core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"),
    Path("core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"),
    Path("core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"),
]

INGEST_MANIFEST = Path("MIGRATION/old_project_ingest/supramental-agent/OLD_PROJECT_FULL_INGEST_MANIFEST_V1.json")
ADOPTION = Path("SYSTEM/AUTONOMY/continuous_self_construction/OLD_PROJECT_FULL_LINEAGE_ADOPTION_V1.json")
DIRECTION = Path("SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.json")
ACCEPTED_DIRECTION = Path("SYSTEM/ENTITY_SUBSTRATE/ACTIVE_ACCEPTED_ENTITY_SUBSTRATE_DIRECTION.json")

PLAN = Path("SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1.json")
PLAN_MD = Path("SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1.md")
PLAN_DASHBOARD = Path("SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_PANEL_V1.json")
MEMORY = Path("MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_FOREGROUND_RUNNER_MEMORY_V1.json")
PANEL_JSON = Path("SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_FOREGROUND_RUNNER_LIVE_PANEL_V1.json")
PANEL_TXT = Path("SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_FOREGROUND_RUNNER_LIVE_PANEL_V1.txt")
PROOF = Path("SOVEREIGN/PROOF/proof_chain/SOCC_RUN_CONTINUOUS_FOREGROUND_SELF_CONSTRUCTION_RUNNER_FOR_ENTITY_SUBSTRATE_V1_PROOF.json")
REPORT = Path("MIGRATION/audits/SOCC_RUN_CONTINUOUS_FOREGROUND_SELF_CONSTRUCTION_RUNNER_FOR_ENTITY_SUBSTRATE_V1.json")

def now():
    return datetime.now(timezone.utc).isoformat()

def rj(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def wj(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def wt(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(s).rstrip() + "\n", encoding="utf-8")

def sha16(p):
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    except Exception:
        return None

def h16(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]

def get_next(obj):
    if not isinstance(obj, dict):
        return None
    for k in ["current_lawful_next", "lawful_next", "next", "route_next", "current_next"]:
        v = obj.get(k)
        if isinstance(v, str):
            return v
    return None

def authority_unique():
    snap = {str(p): get_next(rj(p)) for p in AUTHORITY_FILES}
    return sorted(set(v for v in snap.values() if v)), snap

def set_next(obj, value):
    for k in ["current_lawful_next", "lawful_next", "next", "route_next", "current_next"]:
        if k in obj:
            obj[k] = value
    if "current_lawful_next" not in obj:
        obj["current_lawful_next"] = value
    obj["status"] = "PASS"
    obj["current_lawful_next_source"] = "entity_substrate_foreground_runner_step_closed"
    obj["last_runner_step"] = {
        "id": "SOCC_ENTITY_SUBSTRATE_FOREGROUND_RUNNER_STEP_V1",
        "at_utc": now(),
        "from": CURRENT,
        "to": value,
        "proof": str(PROOF),
        "boundary": "Foreground runner step. No daemon/background/network."
    }

def advance(value):
    for p in AUTHORITY_FILES:
        obj = rj(p)
        set_next(obj, value)
        wj(p, obj)

def panel(stage, status, lifecycle, hard=None):
    data = {
        "id": "ENTITY_SUBSTRATE_FOREGROUND_RUNNER_LIVE_PANEL_V1",
        "created_at_utc": now(),
        "status": status,
        "stage": stage,
        "lifecycle": lifecycle,
        "current": CURRENT,
        "next": NEXT,
        "plan": str(PLAN),
        "hard_failures": hard or [],
        "truth_boundary": "Foreground runner panel. No daemon/background/network."
    }
    wj(PANEL_JSON, data)
    wt(PANEL_TXT, "\n".join([
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "ENTITY/SUBSTRATE FOREGROUND AUTONOMY RUNNER LIVE PANEL V1",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"STATUS::{status}",
        f"STAGE::{stage}",
        "",
        "## LIFECYCLE",
        *[f"- {x}" for x in lifecycle],
        "",
        f"ENTITY_SUBSTRATE_PLAN::{PLAN}",
        f"NEXT::{NEXT}",
        "",
        "NO_DAEMON::True",
        "NO_BACKGROUND::True",
        "NO_NETWORK::True",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]))

lifecycle = []
hard = []

obs, auth = authority_unique()
if obs != [CURRENT]:
    hard.append(f"AUTHORITY_NOT_AT_RUN_FRONTIER::{obs}")

for p in [INGEST_MANIFEST, ADOPTION, DIRECTION, ACCEPTED_DIRECTION]:
    if not p.exists():
        hard.append(f"REQUIRED_FILE_MISSING::{p}")

if hard:
    lifecycle.append("GUARD_STOP")
    panel("GUARD_STOP", "GUARD_STOP", lifecycle, hard)
    print(PANEL_TXT.read_text(encoding="utf-8"))
    raise SystemExit(0)

ts = now()
ingest = rj(INGEST_MANIFEST)
direction = rj(DIRECTION)

lifecycle.append("SELECTED::build_entity_substrate_construction_plan_v1")
panel("SELECTED", "RUNNING", lifecycle)

lifecycle.append("LOCAL_LINEAGE_CHECK::PASS::old_project_ingest_bundle")
panel("LOCAL_LINEAGE_CHECK", "RUNNING", lifecycle)

lifecycle.append("DOING::write_entity_substrate_construction_plan")
panel("DOING", "RUNNING", lifecycle)

plan = {
    "id": "ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1",
    "created_at_utc": ts,
    "status": "BUILT_BY_FOREGROUND_AUTONOMY_RUNNER_PENDING_REVIEW",
    "built_by": "SOCC foreground continuous self-construction autonomy runner",
    "current_runner_frontier": CURRENT,
    "next_required_step": NEXT,
    "source_direction": str(DIRECTION),
    "local_old_project_ingest": str(INGEST_MANIFEST),
    "old_project_dependency_after_ingest": False,
    "mission": "Construct Entity/Substrate as a lawful, proof-bound, dashboard-visible substrate for future entity instances and Anna MVP.",
    "surfaces_to_construct": [
        "entity_identity_surface",
        "entity_state_surface",
        "entity_memory_surface",
        "entity_lineage_surface",
        "entity_capability_binding_surface",
        "entity_lawful_action_surface",
        "entity_dashboard_surface",
        "entity_proof_chain_surface",
        "entity_freeze_review_stop_surface",
        "anna_mvp_product_binding_surface"
    ],
    "next_chain": [
        "review_entity_substrate_construction_plan_v1",
        "run_entity_substrate_scientific_quality_gate_v1",
        "run_entity_substrate_hermes_gate_v1",
        "run_entity_substrate_codex_gate_v1",
        "review_entity_substrate_plan_and_gates_v1",
        "accept_entity_substrate_plan_and_gates_v1",
        "build_entity_substrate_bounded_execution_surface_v1",
        "run_entity_substrate_bounded_execution_session_v1",
        "validate_entity_substrate_bounded_execution_session_v1",
        "review_entity_substrate_bounded_execution_session_v1",
        "accept_entity_substrate_bounded_execution_session_v1",
        "seal_entity_substrate_v1",
        "build_anna_mvp_direction_v1"
    ],
    "mandatory_rules": {
        "use_local_old_project_ingest_bundle": True,
        "do_not_query_old_project_each_step": True,
        "do_not_resume_old_route": True,
        "do_not_launch_old_daemon": True,
        "route_bound_current_lawful_next_only": True,
        "dashboard_visible": True,
        "proof_chain_required": True,
        "memory_required": True,
        "bounded_stop_required": True,
        "scientific_gate_required": True,
        "Hermes_gate_required": True,
        "Codex_gate_required_if_code_or_patch": True,
        "no_daemon_now": True,
        "no_background": True,
        "no_network": True,
        "no_agi_claim": True,
        "no_l3_claim": True
    },
    "old_ingest_summary": {
        "files_indexed": ingest.get("files_indexed"),
        "keyword_hits_count": ingest.get("keyword_hits_count"),
        "daemon_hits_count": ingest.get("daemon_hits_count"),
        "archive": ingest.get("archive")
    },
    "truth_boundary": "Plan was built by foreground autonomy runner. Entity/Substrate is started but not sealed. No daemon/background/network."
}
wj(PLAN, plan)
wt(PLAN_MD, "\n".join([
    "# Entity/Substrate Construction Plan V1",
    "",
    "STATUS::BUILT_BY_FOREGROUND_AUTONOMY_RUNNER_PENDING_REVIEW",
    f"NEXT_REQUIRED_STEP::{NEXT}",
    "",
    "## Built by",
    "SOCC foreground continuous self-construction autonomy runner",
    "",
    "## Mission",
    plan["mission"],
    "",
    "## Surfaces to construct",
    *[f"- {x}" for x in plan["surfaces_to_construct"]],
    "",
    "## Mandatory rules",
    *[f"- {k}: `{v}`" for k, v in plan["mandatory_rules"].items()],
    "",
    "## Boundary",
    plan["truth_boundary"],
]))

dashboard = {
    "id": "ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_PANEL_V1",
    "created_at_utc": ts,
    "status": "ACTIVE_RUNNER_BUILT_PENDING_REVIEW",
    "current_stage": "entity_substrate_construction_plan_built_by_foreground_runner_pending_review",
    "lawful_next": NEXT,
    "plan": str(PLAN),
    "runner_panel": str(PANEL_TXT),
    "operator_visible_summary": "Foreground autonomy runner started Entity/Substrate and built its construction plan. Review is next.",
    "truth_boundary": plan["truth_boundary"]
}
wj(PLAN_DASHBOARD, dashboard)

memory = {
    "id": "ENTITY_SUBSTRATE_FOREGROUND_RUNNER_MEMORY_V1",
    "created_at_utc": ts,
    "status": "RECORDED",
    "event": "SOCC foreground autonomy runner started Entity/Substrate by building the construction plan.",
    "plan": str(PLAN),
    "next": NEXT,
    "stopped_after_step": True,
    "truth_boundary": plan["truth_boundary"]
}
wj(MEMORY, memory)

lifecycle.append("DONE::entity_substrate_construction_plan_written")
panel("DONE", "RUNNING", lifecycle)

proof = {
    "id": "SOCC_RUN_CONTINUOUS_FOREGROUND_SELF_CONSTRUCTION_RUNNER_FOR_ENTITY_SUBSTRATE_V1_PROOF",
    "created_at_utc": ts,
    "status": "PASS",
    "current_expected": CURRENT,
    "next_after_pass": NEXT,
    "capability": "SOCC_FOREGROUND_AUTONOMY_RUNNER_STARTED_ENTITY_SUBSTRATE",
    "lifecycle": lifecycle + ["CLOSED", "NEXT::" + NEXT],
    "plan": str(PLAN),
    "plan_dashboard": str(PLAN_DASHBOARD),
    "runner_panel": str(PANEL_TXT),
    "memory": str(MEMORY),
    "sha16": {
        "plan": sha16(PLAN),
        "dashboard": sha16(PLAN_DASHBOARD),
        "memory": sha16(MEMORY)
    },
    "hard_failures": [],
    "stopped_after_step": True,
    "no_daemon": True,
    "no_background": True,
    "no_network": True,
    "no_old_route_resume": True,
    "no_agi_claim": True,
    "no_l3_claim": True,
    "next_lawful_step": NEXT,
    "truth_boundary": plan["truth_boundary"]
}
proof["proof_hash"] = h16(proof)
wj(PROOF, proof)

lifecycle.append("CLOSED::runner_step_closed")
lifecycle.append("NEXT::" + NEXT)
advance(NEXT)

report = {
    "id": "SOCC_RUN_CONTINUOUS_FOREGROUND_SELF_CONSTRUCTION_RUNNER_FOR_ENTITY_SUBSTRATE_V1_REPORT",
    "created_at_utc": now(),
    "status": "PASS",
    "lifecycle": lifecycle,
    "plan": str(PLAN),
    "proof": str(PROOF),
    "memory": str(MEMORY),
    "next": NEXT,
    "truth_boundary": plan["truth_boundary"]
}
wj(REPORT, report)
panel("CLOSED_NEXT", "PASS", lifecycle)

print(PANEL_TXT.read_text(encoding="utf-8"))
print("PLAN::" + str(PLAN))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("NEXT_LAWFUL_STEP::" + NEXT)

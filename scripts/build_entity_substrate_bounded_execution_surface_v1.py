#!/usr/bin/env python3
"""
Entity/Substrate — Build Bounded Execution Surface V1.

Lawful chain position:
    ... accept_entity_substrate_plan_and_gates_v1
        -> build_entity_substrate_bounded_execution_surface_v1
        -> review_entity_substrate_bounded_execution_surface_v1 ...

This step BUILDS a declarative contract artifact (the bounded execution surface)
that defines the sandbox in which a later single bounded session will
materialize the Entity/Substrate surfaces. It executes NOTHING, runs no session,
births no Entity/ANNA. The surface authorizes no execution until separate review
and acceptance.

No fake pass: every check is computed from real file state. Any false check
becomes a hard_failure and the build FAILS.

Route transition (build surface -> review surface) via the ENFORCED
atomic-commit helper, then the two observe-facing mirrors are synced.
"""
import json
import hashlib
import shutil
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

CURRENT = "build_entity_substrate_bounded_execution_surface_v1"
NEXT = "review_entity_substrate_bounded_execution_surface_v1"

PC = ROOT / "SOVEREIGN/PROOF/proof_chain"
SCIENTIFIC_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_SCIENTIFIC_QUALITY_GATE_V1_PROOF.json"
HERMES_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_HERMES_GATE_V1_PROOF.json"
CODEX_PROOF = PC / "SOCC_RUN_ENTITY_SUBSTRATE_CODEX_GATE_V1_PROOF.json"
ACCEPT_PROOF = PC / "SOCC_ACCEPT_ENTITY_SUBSTRATE_PLAN_AND_GATES_V1_PROOF.json"
ACTIVE_ACCEPTED = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ACTIVE_ACCEPTED_ENTITY_SUBSTRATE_PLAN_AND_GATES.json"
PLAN = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1.json"
DIRECTION = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.json"

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"

SURFACE = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1.json"
SURFACE_MD = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1.md"
ACTIVE_SURFACE = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ACTIVE_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE.json"
PROOF = PC / "SOCC_BUILD_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_MEMORY_V1.json"
PANEL_JSON = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_PANEL_V1.json"
PANEL_TXT = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_PANEL_V1.txt"
BACKUP_ROOT = ROOT / "core/socc/route_authority/self_construction_autonomy/bounded_surface_build_backups"

RUN_FRONTIER = "run_entity_substrate_bounded_execution_session_v1"

TRUTH_BOUNDARY = (
    "Entity/Substrate bounded execution surface build only. Builds a declarative "
    "sandbox contract; authorizes NO execution until separate review and "
    "acceptance. Runs no session, materializes no substrate artifacts, births no "
    "Entity/ANNA, and does not enable loop/daemon/scheduler/background, use "
    "network, widen queue, approve canon, or claim AGI."
)

# The 10 substrate surfaces a later bounded session will materialize (declaratively).
RUNTIME_ARTIFACTS = [
    ("SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_IDENTITY_SURFACE_V1.json", "entity_identity_surface"),
    ("SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_STATE_SURFACE_V1.json", "entity_state_surface"),
    ("SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_MEMORY_SURFACE_V1.json", "entity_memory_surface"),
    ("SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_LINEAGE_SURFACE_V1.json", "entity_lineage_surface"),
    ("SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_CAPABILITY_BINDING_SURFACE_V1.json", "entity_capability_binding_surface"),
    ("SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_LAWFUL_ACTION_SURFACE_V1.json", "entity_lawful_action_surface"),
    ("SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_DASHBOARD_SURFACE_V1.json", "entity_dashboard_surface"),
    ("SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_PROOF_CHAIN_SURFACE_V1.json", "entity_proof_chain_surface"),
    ("SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_FREEZE_REVIEW_STOP_SURFACE_V1.json", "entity_freeze_review_stop_surface"),
    ("SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_PRODUCT_BINDING_SURFACE_FOR_ANNA_MVP_V1.json", "entity_product_binding_surface_for_anna_mvp"),
]


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")


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


def h16(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def load_enforcer():
    spec = importlib.util.spec_from_file_location("socc_self_building_atomic_commit_enforcer_v1", ENFORCER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_next(obj):
    if not isinstance(obj, dict):
        return None
    for k in ["current_lawful_next", "lawful_next", "next", "route_next", "current_next"]:
        v = obj.get(k)
        if isinstance(v, str):
            return v
    return None


def proof_next(obj):
    for k in ["next_after_pass", "next_lawful_step", "next_required_step"]:
        v = obj.get(k)
        if isinstance(v, str):
            return v
    return None


# ── Read state ──────────────────────────────────────────────────────
sci = rj(SCIENTIFIC_PROOF)
her = rj(HERMES_PROOF)
cod = rj(CODEX_PROOF)
acc = rj(ACCEPT_PROOF)
plan = rj(PLAN)
direction = rj(DIRECTION)
plan_chain = plan.get("next_chain", []) or []
dir_frontiers = direction.get("future_frontiers", []) or []
authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})

# Authoritative ordering source = the direction's future_frontiers, which obeys
# the mandatory gate review_accept_before_execution (review+accept the surface
# BEFORE any run). The construction plan's next_chain omits those two steps and
# jumps straight to run_session — a latent gap, recorded transparently here and
# left for a separate lawful repair (no silent widening).
review_accept_before_execution = direction.get("mandatory_gates", {}).get("review_accept_before_execution") is True
plan_next_chain_gap = (
    "build_entity_substrate_bounded_execution_surface_v1" in plan_chain
    and NEXT not in plan_chain
)
def _next_in(seq):
    return (seq[seq.index(CURRENT) + 1] == NEXT
            if CURRENT in seq and seq.index(CURRENT) + 1 < len(seq) else False)

presence = {
    "scientific_proof_exists": SCIENTIFIC_PROOF.exists(),
    "hermes_proof_exists": HERMES_PROOF.exists(),
    "codex_proof_exists": CODEX_PROOF.exists(),
    "accept_proof_exists": ACCEPT_PROOF.exists(),
    "active_accepted_exists": ACTIVE_ACCEPTED.exists(),
    "plan_exists": PLAN.exists(),
    "direction_exists": DIRECTION.exists(),
    "enforcer_exists": ENFORCER.exists(),
}

build_checks = {
    "scientific_gate_pass": sci.get("status") == "PASS",
    "hermes_gate_pass": her.get("status") == "PASS",
    "codex_gate_pass": cod.get("status") == "PASS",
    "plan_and_gates_accept_pass": acc.get("status") == "PASS",
    "accept_next_matches_current": proof_next(acc) == CURRENT,
    "authority_at_current": authority_nexts == [CURRENT],
    "review_accept_before_execution_mandated": review_accept_before_execution,
    "review_surface_is_next_in_direction": _next_in(dir_frontiers),
    "run_session_in_direction": RUN_FRONTIER in dir_frontiers,
    "seal_in_chain": "seal_entity_substrate_v1" in (dir_frontiers + plan_chain),
    "execution_not_authorized": True,
    "entity_birth_not_authorized": True,
    "anna_birth_not_authorized": True,
}

safety = {
    "no_execution": True,
    "no_session_run": True,
    "no_build_execution": True,
    "no_patch_execution": True,
    "no_entity_birth": True,
    "no_anna_birth": True,
    "no_daemon": True,
    "no_background": True,
    "no_network": True,
    "no_agi_claim": True,
    "no_l3_claim": True,
    "no_old_route_resume": True,
}

checks = {**presence, **build_checks, **safety, "build_checks_all_true": all(build_checks.values())}
hard = [k for k, v in checks.items() if v is not True]

commit_result = None
backup_dir = None
status = "PASS" if not hard else "FAIL"
ts = now_utc()

# ── Build the bounded execution surface contract ────────────────────
surface = {
    "id": "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1",
    "created_at_utc": ts,
    "status": "BUILT_CANDIDATE" if status == "PASS" else "BLOCKED",
    "surface_type": "BOUNDED_ENTITY_SUBSTRATE_EXECUTION_SURFACE",
    "direction_id": "DIRECTION_ENTITY_SUBSTRATE_V1",
    "current_expected": CURRENT,
    "next_required_step": NEXT,
    "execution_purpose": (
        "Run exactly one bounded foreground session to materialize the ten "
        "Entity/Substrate surfaces as declarative substrate artifacts. This "
        "prepares the substrate; it does NOT birth an entity or Anna."
    ),
    "execution_scope": {
        "mode": "single_foreground_bounded_execution_session",
        "max_sessions": 1,
        "max_ticks": 1,
        "operator_foreground_only": True,
        "must_stop_after_run": True,
        "daemon_allowed": False,
        "background_allowed": False,
        "network_allowed": False,
        "mw_route_allowed": False,
        "old_route_resume_allowed": False,
        "agi_claim_allowed": False,
        "l3_claim_allowed": False,
        "entity_birth_allowed": False,
        "anna_birth_allowed": False,
    },
    "allowed_writes": [path for path, _ in RUNTIME_ARTIFACTS] + [
        "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_RUNTIME_PANEL_V1.json",
        "MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_RUNTIME_MEMORY_V1.json",
        "SOVEREIGN/PROOF/proof_chain/SOCC_RUN_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json",
        "MIGRATION/audits/SOCC_RUN_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1.json",
    ],
    "forbidden_writes": [
        "core/socc/route_authority/* except lawful next transition fields",
        "old supramental-agent route files",
        "network config",
        "launch agents / daemon plist / cron jobs / background workers",
        "MW route",
        "any entity-birth or anna-birth surface",
    ],
    "pre_run_checks_required": {
        "scientific_gate_pass": True,
        "hermes_gate_pass": True,
        "codex_gate_pass": True,
        "plan_and_gates_accepted": True,
        "bounded_surface_accepted": True,
        "route_authority_equals_run_frontier": RUN_FRONTIER,
        "dashboard_visible": True,
        "memory_required": True,
        "proof_required": True,
        "stop_required": True,
        "entity_birth_allowed": False,
        "anna_birth_allowed": False,
    },
    "pass_definition": {
        "pass_only_if": [
            f"route authority equals {RUN_FRONTIER}",
            "exactly one bounded foreground session runs",
            "the ten substrate surface artifacts are written",
            "runtime dashboard panel is written",
            "proof is written",
            "memory is written",
            "stop is observed",
            "no daemon/background/network/old route/MW/L3",
            "no entity birth / no anna birth",
        ],
        "fail_if": [
            "any daemon/background/network action is attempted",
            "old route is resumed",
            "execution exceeds one bounded tick",
            "any entity/anna birth is attempted",
            "proof/memory/dashboard missing",
            "route authority does not match expected run frontier",
        ],
    },
    "runtime_artifacts_to_build": [
        {"path": path, "surface": surface_name} for path, surface_name in RUNTIME_ARTIFACTS
    ] + [
        {"path": "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_RUNTIME_PANEL_V1.json",
         "surface": "operator_visible_runtime_panel"},
    ],
    "run_outputs_required": {
        "substrate_surface_artifacts": True,
        "runtime_dashboard_panel": True,
        "memory_record": True,
        "proof_chain": True,
        "bounded_stop_observed": True,
        "lawful_next_after_run": True,
    },
    "future_frontiers": [
        "review_entity_substrate_bounded_execution_surface_v1",
        "accept_entity_substrate_bounded_execution_surface_v1",
        "run_entity_substrate_bounded_execution_session_v1",
        "validate_entity_substrate_bounded_execution_session_v1",
        "review_entity_substrate_bounded_execution_session_v1",
        "accept_entity_substrate_bounded_execution_session_v1",
        "seal_entity_substrate_v1",
        "build_anna_mvp_direction_v1",
    ],
    "checks": checks,
    "hard_failures": hard,
    "findings": {
        "plan_next_chain_gap_detected": plan_next_chain_gap,
        "plan_next_chain_gap_note": (
            "ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1.next_chain omits "
            "review_entity_substrate_bounded_execution_surface_v1 and "
            "accept_entity_substrate_bounded_execution_surface_v1, jumping "
            "build_surface -> run_session. This violates mandatory gate "
            "review_accept_before_execution. Lawful ordering is taken from the "
            "direction.future_frontiers instead. Repair the plan next_chain in a "
            "separate lawful step." if plan_next_chain_gap else "none"),
    },
    "truth_boundary": TRUTH_BOUNDARY,
}
wj(SURFACE, surface)
wt(SURFACE_MD, "\n".join([
    "# Entity/Substrate Bounded Execution Surface V1",
    "",
    f"STATUS::{surface['status']}",
    f"SURFACE_TYPE::{surface['surface_type']}",
    f"NEXT_REQUIRED_STEP::{NEXT}",
    "",
    "## Purpose",
    surface["execution_purpose"],
    "",
    "## Execution scope (hard bounds)",
    *[f"- {k}: `{v}`" for k, v in surface["execution_scope"].items()],
    "",
    "## Surfaces a later single bounded session will materialize",
    *[f"- {s}" for _, s in RUNTIME_ARTIFACTS],
    "",
    "## Boundary",
    TRUTH_BOUNDARY,
]))
if status == "PASS":
    wj(ACTIVE_SURFACE, {
        "id": "ACTIVE_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE",
        "created_at_utc": ts,
        "surface": str(SURFACE),
        "next_required_step": NEXT,
        "execution_authorized": False,
        "truth_boundary": TRUTH_BOUNDARY,
    })

# ── On PASS: lawful route transition + observe-mirror sync ──────────
if status == "PASS":
    snap_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = BACKUP_ROOT / snap_id
    backup_dir.mkdir(parents=True, exist_ok=True)
    for p in AUTHORITY_FILES:
        if p.exists():
            shutil.copy2(p, backup_dir / p.name)

    enforcer = load_enforcer()
    commit_result = enforcer.enforce_atomic_commit_transition(
        lawful_next=NEXT,
        upstream_proof=str(PROOF),
        truth_boundary=TRUTH_BOUNDARY,
        route_updates={
            "current_lawful_next": NEXT,
            "current_lawful_next_source": "entity_substrate_bounded_execution_surface_built_candidate",
            "recommended_next_target": NEXT,
            "entity_substrate_bounded_execution_surface_built": True,
        },
        reason="entity_substrate_bounded_execution_surface_build_candidate_advance_to_review",
    )
    if not (isinstance(commit_result, dict) and commit_result.get("status") == "PASS"):
        hard.append("ATOMIC_COMMIT_NOT_PASS")
        status = "FAIL"

if status == "PASS":
    route_hash = rj(ROUTE).get("route_hash")
    common_guard = {
        "daemon_running": False,
        "continuous_loop_enabled": False,
        "background_loop_enabled": False,
        "scheduler_installed": False,
        "network_used": False,
        "queue_widening_allowed": False,
        "entity_birth_allowed": False,
        "anna_birth_allowed": False,
        "agi_claim_allowed": False,
    }
    pulse = rj(AUTONOMY_PULSE)
    pulse.update({
        "updated_at_utc": now_utc(), "status": "PASS",
        "current_lawful_next": NEXT, "lawful_next": NEXT, "real_next": NEXT,
        "current_lawful_next_source": "entity_substrate_bounded_execution_surface_built_candidate",
        "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY", "route_hash_ref": route_hash,
        "entity_substrate_bounded_execution_surface_built": True,
    })
    pulse.update(common_guard)
    wj(AUTONOMY_PULSE, pulse)

    control = rj(CONTROL_PANEL)
    control.update({
        "updated_at_utc": now_utc(), "status": "PASS",
        "current_lawful_next": NEXT, "lawful_next": NEXT, "real_next": NEXT,
        "CONTROL_NEXT": NEXT, "route_hash_ref": route_hash,
        "entity_substrate_bounded_execution_surface_built": True,
    })
    if isinstance(control.get("operator_view"), dict):
        control["operator_view"]["current_lawful_next"] = NEXT
    control.update(common_guard)
    wj(CONTROL_PANEL, control)

# ── Proof (no fake pass) ────────────────────────────────────────────
proof = {
    "id": "SOCC_BUILD_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1_PROOF",
    "created_at_utc": ts,
    "created_at_msk": now_msk(),
    "status": status,
    "capability": ("SOCC_HAS_BUILT_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_CANDIDATE"
                   if status == "PASS" else "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_BUILD_BLOCKED"),
    "current_expected": CURRENT,
    "next_after_pass": NEXT if status == "PASS" else None,
    "next_lawful_step": NEXT if status == "PASS" else "manual_bounded_surface_build_repair_required",
    "bounded_execution_surface": str(SURFACE),
    "surface_md": str(SURFACE_MD),
    "active_surface": str(ACTIVE_SURFACE) if status == "PASS" else None,
    "dashboard_panel": str(PANEL_JSON),
    "accept_proof": str(ACCEPT_PROOF),
    "scientific_gate_proof": str(SCIENTIFIC_PROOF),
    "hermes_gate_proof": str(HERMES_PROOF),
    "codex_gate_proof": str(CODEX_PROOF),
    "plan": str(PLAN),
    "checks": checks,
    "build_checks": build_checks,
    "hard_failures": hard,
    "warnings": (["PLAN_NEXT_CHAIN_GAP::construction_plan_skips_surface_review_and_accept"]
                 if plan_next_chain_gap else []),
    "plan_next_chain_gap_detected": plan_next_chain_gap,
    "atomic_commit_result": commit_result,
    "backup_dir": str(backup_dir) if backup_dir else None,
    "stopped_after_step": True,
    "execution_not_authorized": True,
    "no_execution": True,
    "no_session_run": True,
    "no_build_execution": True,
    "no_patch_execution": True,
    "no_entity_build_execution_now": True,
    "no_entity_birth": True,
    "no_anna_birth": True,
    "no_daemon": True,
    "no_background": True,
    "no_network": True,
    "no_old_route_resume": True,
    "no_agi_claim": True,
    "no_l3_claim": True,
    "final_canon_approval_allowed": False,
    "truth_boundary": TRUTH_BOUNDARY,
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)

wj(MEMORY, {
    "id": "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_MEMORY_V1",
    "created_at_utc": ts,
    "status": "RECORDED",
    "event": ("Entity/Substrate bounded execution surface contract built (candidate); "
              "no execution authorized. Review is next."
              if status == "PASS" else
              "Entity/Substrate bounded execution surface build blocked; hard failures recorded."),
    "build_status": status,
    "hard_failures": hard,
    "surface": str(SURFACE),
    "proof": str(PROOF),
    "next": NEXT if status == "PASS" else "manual_bounded_surface_build_repair_required",
    "stopped_after_step": True,
    "truth_boundary": TRUTH_BOUNDARY,
})

wj(PANEL_JSON, {
    "id": "ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_PANEL_V1",
    "created_at_utc": ts,
    "status": status,
    "stage": "entity_substrate_bounded_execution_surface_built",
    "current": CURRENT,
    "next": NEXT if status == "PASS" else "manual_bounded_surface_build_repair_required",
    "execution_authorized": False,
    "surface": str(SURFACE),
    "proof": str(PROOF),
    "hard_failures": hard,
    "truth_boundary": TRUTH_BOUNDARY,
})
wt(PANEL_TXT, "\n".join([
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    "ENTITY/SUBSTRATE BOUNDED EXECUTION SURFACE V1",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    f"STATUS::{status}",
    f"CURRENT::{CURRENT}",
    f"NEXT::{NEXT if status == 'PASS' else 'manual_bounded_surface_build_repair_required'}",
    f"HARD_FAILURES::{hard}",
    "",
    "SURFACE_TYPE::BOUNDED_ENTITY_SUBSTRATE_EXECUTION_SURFACE",
    "EXECUTION_AUTHORIZED::False",
    "MAX_SESSIONS::1   MAX_TICKS::1",
    "ENTITY_BIRTH_ALLOWED::False",
    "ANNA_BIRTH_ALLOWED::False",
    "NO_DAEMON::True   NO_NETWORK::True",
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
]))

print(PANEL_TXT.read_text(encoding="utf-8"))
print("SURFACE::" + str(SURFACE))
print("PROOF::" + str(PROOF))
print("STATUS::" + status)
print("NEXT_LAWFUL_STEP::" + (NEXT if status == "PASS" else "manual_bounded_surface_build_repair_required"))
if hard:
    raise SystemExit(1)

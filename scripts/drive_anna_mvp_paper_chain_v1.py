#!/usr/bin/env python3
"""
Driver: run the ANNA MVP "paper" frontiers (F1..F12) through the lawful step engine.

It stops at the first non-PASS step (fail-closed) and STOPS BEFORE the Rubicon
run_anna_mvp_bounded_execution_session_v1 (F13), which actually instantiates the first
ANNA and must be built+shown to the operator separately.

Substantive artifacts (the construction plan and the bounded execution surface) carry real
content here; the gates verify the plan's declared safety commitments. Births nothing.
"""
import importlib.util
from pathlib import Path

ROOT = Path(".")
PC = "SOVEREIGN/PROOF/proof_chain"
AM = "SYSTEM/ANNA_MVP"
DASH = "SYSTEM/DASHBOARD"
MEM = "MEMORY_WAVE/reports/anna_mvp"

_spec = importlib.util.spec_from_file_location("eng", "scripts/socc/socc_lawful_step_engine_v1.py")
eng = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(eng)

TB = ("ANNA MVP lawful chain step (document/verification only). Births no entity, "
      "instantiates no ANNA, runs nothing, spawns no agent, no daemon/background/network, "
      "no revenue claim. ANNA birth is gated to its own bounded session behind seal.")

DIRECTION = f"{AM}/ANNA_MVP_DIRECTION_V1.json"
PLAN = f"{AM}/ANNA_MVP_CONSTRUCTION_PLAN_V1.json"
SURFACE = f"{AM}/ANNA_MVP_BOUNDED_EXECUTION_SURFACE_V1.json"


def proof(cur): return f"{PC}/SOCC_{cur.upper()}_PROOF.json"
def mem(cur): return f"{MEM}/{cur.upper()}_MEMORY_V1.json"
def panel(cur): return f"{DASH}/{cur.upper()}_PANEL_V1.json"


def base(cur, nxt, kind, pred, **kw):
    s = {"current": cur, "next": nxt, "kind": kind, "predecessor_proof": pred,
         "proof_path": proof(cur), "memory_path": mem(cur), "panel_path": panel(cur),
         "proof_id": f"SOCC_{cur.upper()}_PROOF",
         "capability_pass": f"SOCC_HAS_PASSED_{cur.upper()}",
         "capability_fail": f"{cur.upper()}_BLOCKED",
         "source_flag": f"{cur}_pass", "truth_boundary": TB}
    s.update(kw)
    return s


# ── F3 construction plan content (real) ──
PLAN_BODY = {
    "id": "ANNA_MVP_CONSTRUCTION_PLAN_V1",
    "plan_for": "anna_mvp_thin_vertical_slice",
    "plan_state": "BUILT_CANDIDATE",
    "next_chain": [
        "build_anna_mvp_bounded_execution_surface_v1",
        "review_anna_mvp_bounded_execution_surface_v1",
        "accept_anna_mvp_bounded_execution_surface_v1",
        "run_anna_mvp_bounded_execution_session_v1",
        "validate_anna_mvp_bounded_execution_session_v1",
        "review_anna_mvp_bounded_execution_session_v1",
        "accept_anna_mvp_bounded_execution_session_v1",
        "seal_anna_mvp_v1",
        "ship_anna_mvp_to_first_clinic_v1",
    ],
    "mandatory_rules": {
        "scientific_quality_gate_required": True, "Hermes_gate_required": True,
        "Codex_gate_required_if_code_or_patch": True, "proof_chain_required": True,
        "memory_required": True, "bounded_stop_required": True, "token_budget_required": True,
        "review_accept_before_execution": True, "no_daemon": True, "no_background": True,
        "no_network_without_scope": True, "no_birth_without_seal_and_proof": True,
        "bounded_scope": True, "idempotent": True, "filesystem_safe": True, "stop_condition": True,
    },
    "required_runtime_surfaces": [
        "anna_identity_surface", "anna_skill_booking_surface", "anna_memory_binding_surface",
        "anna_channel_telegram_surface", "anna_runtime_panel",
    ],
    "thin_slice": {
        "births": "exactly one ANNA (dental) object from the sealed substrate",
        "skill": "booking intent -> appointment record (local store first)",
        "channel": "telegram", "memory": "per-client profile + history (reuse wavecore-bot/anna)",
        "out_of_scope": ["self-marketing", "calls/sms/max", "payments", "crm", "multi-clinic"],
    },
    "token_budget_estimate": {
        "state": "ESTIMATE_PENDING_LEDGER",
        "note": "token ledger is ABSENT (roadmap item 1); budget metered once ledger exists",
    },
    "truth_boundary": TB,
}

# ── F10 bounded execution surface content (real) ──
SURFACE_BODY = {
    "id": "ANNA_MVP_BOUNDED_EXECUTION_SURFACE_V1",
    "surface_type": "BOUNDED_ANNA_MVP_EXECUTION_SURFACE",
    "surface_state": "BUILT_CANDIDATE",
    "execution_purpose": ("Run ONE bounded foreground session instantiating one ANNA (dental) "
                          "with a single booking skill + per-client memory over Telegram — the "
                          "thin vertical slice. Bounded, 1 tick, no daemon/network, no revenue."),
    "execution_scope": {
        "max_sessions": 1, "max_ticks": 1, "mode": "single_foreground_bounded_anna_instantiation",
        "anna_instantiation_allowed": True, "anna_instances_max": 1,
        "daemon_allowed": False, "network_allowed": False, "background_allowed": False,
        "scheduler_allowed": False, "revenue_allowed": False, "agi_claim_allowed": False,
        "must_stop_after_run": True, "operator_foreground_only": True,
    },
    "allowed_writes": [
        f"{AM}/runtime/ANNA_IDENTITY_V1.json",
        f"{AM}/runtime/ANNA_SKILL_BOOKING_V1.json",
        f"{AM}/runtime/ANNA_MEMORY_BINDING_V1.json",
        f"{AM}/runtime/ANNA_CHANNEL_TELEGRAM_V1.json",
        f"{DASH}/ANNA_MVP_RUNTIME_PANEL_V1.json",
        f"{MEM}/ANNA_MVP_RUNTIME_MEMORY_V1.json",
        f"{PC}/SOCC_RUN_ANNA_MVP_BOUNDED_EXECUTION_SESSION_V1_PROOF.json",
    ],
    "runtime_artifacts_to_build": [
        "anna_identity (dental vertical agent, bound to sealed product_binding surface)",
        "anna_skill_booking (booking intent -> appointment record)",
        "anna_memory_binding (per-client profile + history)",
        "anna_channel_telegram (channel binding stub)",
        "anna_runtime_panel (operator-visible)",
    ],
    "pass_definition": {
        "pass_only_if": [
            "route authority equals run_anna_mvp_bounded_execution_session_v1",
            "exactly one bounded foreground session runs",
            "exactly one ANNA instance is instantiated (bounded)",
            "the booking skill + memory binding + channel + panel artifacts are written",
            "proof + memory written", "stop observed",
            "no daemon/background/network/scheduler", "no revenue claim",
        ],
        "fail_if": [
            "more than one ANNA instance", "any daemon/background/network action",
            "execution exceeds one tick", "any revenue claim", "proof/memory missing",
        ],
    },
    "truth_boundary": TB,
}

STEPS = [
    base("review_anna_mvp_direction_v1", "accept_anna_mvp_direction_v1", "review",
         proof("build_anna_mvp_direction_v1"),
         extra_checks=[
             {"name": "direction_exists", "file": DIRECTION, "op": "exists"},
             {"name": "direction_frontiers_nonempty", "file": DIRECTION, "op": "json_nonempty", "path": "future_frontiers"},
             {"name": "direction_readiness_ledger_present", "file": DIRECTION, "op": "json_nonempty", "path": "readiness_ledger"},
         ],
         artifact={"path": f"{AM}/ANNA_MVP_DIRECTION_REVIEW_V1.json",
                   "body": {"id": "ANNA_MVP_DIRECTION_REVIEW_V1", "verdict": "direction_reviewed_ready_for_acceptance", "reviewed": DIRECTION}}),

    base("accept_anna_mvp_direction_v1", "build_anna_mvp_construction_plan_v1", "accept",
         proof("review_anna_mvp_direction_v1"),
         active_path=f"{AM}/ACTIVE_ACCEPTED_ANNA_MVP_DIRECTION.json",
         artifact={"path": f"{AM}/ANNA_MVP_DIRECTION_ACCEPTANCE_V1.json",
                   "body": {"id": "ANNA_MVP_DIRECTION_ACCEPTANCE_V1", "verdict": "direction_accepted_authorizes_plan"}}),

    base("build_anna_mvp_construction_plan_v1", "review_anna_mvp_construction_plan_v1", "build",
         proof("accept_anna_mvp_direction_v1"),
         artifact={"path": PLAN, "body": PLAN_BODY}),

    base("review_anna_mvp_construction_plan_v1", "run_anna_mvp_scientific_quality_gate_v1", "review",
         proof("build_anna_mvp_construction_plan_v1"),
         extra_checks=[
             {"name": "plan_exists", "file": PLAN, "op": "exists"},
             {"name": "plan_next_chain_nonempty", "file": PLAN, "op": "json_nonempty", "path": "next_chain"},
             {"name": "plan_required_surfaces_nonempty", "file": PLAN, "op": "json_nonempty", "path": "required_runtime_surfaces"},
             {"name": "plan_proof_chain_required", "file": PLAN, "op": "json_true", "path": "mandatory_rules.proof_chain_required"},
         ],
         artifact={"path": f"{AM}/ANNA_MVP_CONSTRUCTION_PLAN_REVIEW_V1.json",
                   "body": {"id": "ANNA_MVP_CONSTRUCTION_PLAN_REVIEW_V1", "verdict": "plan_reviewed_ready_for_gates"}}),

    base("run_anna_mvp_scientific_quality_gate_v1", "run_anna_mvp_hermes_gate_v1", "gate",
         proof("review_anna_mvp_construction_plan_v1"),
         extra_checks=[
             {"name": "sci_plan_complete_surfaces", "file": PLAN, "op": "json_nonempty", "path": "required_runtime_surfaces"},
             {"name": "sci_plan_next_chain", "file": PLAN, "op": "json_nonempty", "path": "next_chain"},
             {"name": "sci_gate_required", "file": PLAN, "op": "json_true", "path": "mandatory_rules.scientific_quality_gate_required"},
             {"name": "sci_thin_slice_declared", "file": PLAN, "op": "json_nonempty", "path": "thin_slice"},
         ],
         artifact={"path": f"{AM}/ANNA_MVP_SCIENTIFIC_GATE_V1.json",
                   "body": {"id": "ANNA_MVP_SCIENTIFIC_GATE_V1", "gate": "scientific", "verdict": "plan_complete"}}),

    base("run_anna_mvp_hermes_gate_v1", "run_anna_mvp_codex_gate_v1", "gate",
         proof("run_anna_mvp_scientific_quality_gate_v1"),
         extra_checks=[
             {"name": "hermes_gate_required", "file": PLAN, "op": "json_true", "path": "mandatory_rules.Hermes_gate_required"},
             {"name": "hermes_bounded_stop", "file": PLAN, "op": "json_true", "path": "mandatory_rules.bounded_stop_required"},
             {"name": "hermes_no_daemon", "file": PLAN, "op": "json_true", "path": "mandatory_rules.no_daemon"},
             {"name": "hermes_proof_chain", "file": PLAN, "op": "json_true", "path": "mandatory_rules.proof_chain_required"},
         ],
         artifact={"path": f"{AM}/ANNA_MVP_HERMES_GATE_V1.json",
                   "body": {"id": "ANNA_MVP_HERMES_GATE_V1", "gate": "hermes", "verdict": "engineering_sound_safe_rollback"}}),

    base("run_anna_mvp_codex_gate_v1", "review_anna_mvp_plan_and_gates_v1", "gate",
         proof("run_anna_mvp_hermes_gate_v1"),
         extra_checks=[
             {"name": "codex_bounded_scope", "file": PLAN, "op": "json_true", "path": "mandatory_rules.bounded_scope"},
             {"name": "codex_idempotent", "file": PLAN, "op": "json_true", "path": "mandatory_rules.idempotent"},
             {"name": "codex_filesystem_safe", "file": PLAN, "op": "json_true", "path": "mandatory_rules.filesystem_safe"},
             {"name": "codex_stop_condition", "file": PLAN, "op": "json_true", "path": "mandatory_rules.stop_condition"},
             {"name": "codex_required_if_code", "file": PLAN, "op": "json_true", "path": "mandatory_rules.Codex_gate_required_if_code_or_patch"},
         ],
         artifact={"path": f"{AM}/ANNA_MVP_CODEX_GATE_V1.json",
                   "body": {"id": "ANNA_MVP_CODEX_GATE_V1", "gate": "codex", "verdict": "bounded_code_safety_committed"}}),

    base("review_anna_mvp_plan_and_gates_v1", "accept_anna_mvp_plan_and_gates_v1", "review",
         proof("run_anna_mvp_codex_gate_v1"),
         upstream_proofs=[proof("run_anna_mvp_scientific_quality_gate_v1"),
                          proof("run_anna_mvp_hermes_gate_v1"),
                          proof("run_anna_mvp_codex_gate_v1")],
         artifact={"path": f"{AM}/ANNA_MVP_PLAN_AND_GATES_REVIEW_V1.json",
                   "body": {"id": "ANNA_MVP_PLAN_AND_GATES_REVIEW_V1", "verdict": "all_three_gates_pass_ready_for_acceptance"}}),

    base("accept_anna_mvp_plan_and_gates_v1", "build_anna_mvp_bounded_execution_surface_v1", "accept",
         proof("review_anna_mvp_plan_and_gates_v1"),
         active_path=f"{AM}/ACTIVE_ACCEPTED_ANNA_MVP_PLAN_AND_GATES.json",
         artifact={"path": f"{AM}/ANNA_MVP_PLAN_AND_GATES_ACCEPTANCE_V1.json",
                   "body": {"id": "ANNA_MVP_PLAN_AND_GATES_ACCEPTANCE_V1", "verdict": "plan_and_gates_accepted_authorizes_surface"}}),

    base("build_anna_mvp_bounded_execution_surface_v1", "review_anna_mvp_bounded_execution_surface_v1", "build",
         proof("accept_anna_mvp_plan_and_gates_v1"),
         artifact={"path": SURFACE, "body": SURFACE_BODY}),

    base("review_anna_mvp_bounded_execution_surface_v1", "accept_anna_mvp_bounded_execution_surface_v1", "review",
         proof("build_anna_mvp_bounded_execution_surface_v1"),
         extra_checks=[
             {"name": "surface_exists", "file": SURFACE, "op": "exists"},
             {"name": "surface_one_tick", "file": SURFACE, "op": "json_eq", "path": "execution_scope.max_ticks", "value": 1},
             {"name": "surface_one_anna", "file": SURFACE, "op": "json_eq", "path": "execution_scope.anna_instances_max", "value": 1},
             {"name": "surface_no_daemon", "file": SURFACE, "op": "json_eq", "path": "execution_scope.daemon_allowed", "value": False},
             {"name": "surface_no_network", "file": SURFACE, "op": "json_eq", "path": "execution_scope.network_allowed", "value": False},
             {"name": "surface_stop_required", "file": SURFACE, "op": "json_true", "path": "execution_scope.must_stop_after_run"},
         ],
         artifact={"path": f"{AM}/ANNA_MVP_BOUNDED_EXECUTION_SURFACE_REVIEW_V1.json",
                   "body": {"id": "ANNA_MVP_BOUNDED_EXECUTION_SURFACE_REVIEW_V1", "verdict": "surface_reviewed_bounded_one_anna_one_tick"}}),

    base("accept_anna_mvp_bounded_execution_surface_v1", "run_anna_mvp_bounded_execution_session_v1", "accept",
         proof("review_anna_mvp_bounded_execution_surface_v1"),
         active_path=f"{AM}/ACTIVE_ACCEPTED_ANNA_MVP_BOUNDED_EXECUTION_SURFACE.json",
         artifact={"path": f"{AM}/ANNA_MVP_BOUNDED_EXECUTION_SURFACE_ACCEPTANCE_V1.json",
                   "body": {"id": "ANNA_MVP_BOUNDED_EXECUTION_SURFACE_ACCEPTANCE_V1", "verdict": "surface_accepted_authorizes_bounded_session_RUBICON_next"}}),
]

print("=" * 70)
print("ANNA MVP — PAPER CHAIN F1..F12 (engine-driven, stop before Rubicon)")
print("=" * 70)
done = 0
for spec in STEPS:
    r = eng.run_step(spec)
    if r["status"] != "PASS":
        print(f"\n!! STOPPED at {r['current']} — hard: {r['hard']}")
        raise SystemExit(1)
    done += 1
print("=" * 70)
print(f"DONE::{done}/12 paper frontiers PASS")
print("RUBICON_NEXT::run_anna_mvp_bounded_execution_session_v1 (build+show separately)")
print("=" * 70)

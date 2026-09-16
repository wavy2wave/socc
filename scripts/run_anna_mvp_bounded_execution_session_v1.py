#!/usr/bin/env python3
"""
ANNA MVP — Run Bounded Execution Session V1 (RUBICON: the first ANNA instantiation).

Lawful chain position:
    ... accept_anna_mvp_bounded_execution_surface_v1
        -> run_anna_mvp_bounded_execution_session_v1   (here)
        -> validate_anna_mvp_bounded_execution_session_v1 ...

This is the thin vertical slice. In ONE bounded foreground tick it instantiates exactly
ONE ANNA (dental administrator persona) as declarative runtime artifacts: identity/persona,
the booking skill, per-client memory binding, a Telegram channel binding (NOT connected —
network is forbidden in this bounded tick), and an operator runtime panel.

It is a BOUNDED, provable instantiation candidate — NOT a live deploy:
  anna_instantiated_bounded_candidate = True, but anna_live = False, network_used = False,
  revenue = False, deployed = False. ANNA becomes ship-eligible only at seal_anna_mvp_v1;
  the live network connection (using ANNA_TELEGRAM_BOT_TOKEN from .secrets) happens later at
  the ship frontier, explicitly. The bot token value never enters any proof/canon artifact.

No fake pass: preconditions and post-conditions computed from real file state. Transition
via the ENFORCED atomic-commit helper, then observe mirrors synced.
"""
import json, hashlib, shutil, importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
CURRENT = "run_anna_mvp_bounded_execution_session_v1"
NEXT = "validate_anna_mvp_bounded_execution_session_v1"

PC = ROOT / "SOVEREIGN/PROOF/proof_chain"
AM = ROOT / "SYSTEM/ANNA_MVP"
RUNTIME = AM / "runtime"
DASH = ROOT / "SYSTEM/DASHBOARD"

SURFACE = AM / "ANNA_MVP_BOUNDED_EXECUTION_SURFACE_V1.json"
PLAN = AM / "ANNA_MVP_CONSTRUCTION_PLAN_V1.json"
ACCEPT_SURFACE_PROOF = PC / "SOCC_ACCEPT_ANNA_MVP_BOUNDED_EXECUTION_SURFACE_V1_PROOF.json"
PLAN_AND_GATES_ACCEPT = PC / "SOCC_ACCEPT_ANNA_MVP_PLAN_AND_GATES_V1_PROOF.json"
SCI_GATE = PC / "SOCC_RUN_ANNA_MVP_SCIENTIFIC_QUALITY_GATE_V1_PROOF.json"
HERMES_GATE = PC / "SOCC_RUN_ANNA_MVP_HERMES_GATE_V1_PROOF.json"
CODEX_GATE = PC / "SOCC_RUN_ANNA_MVP_CODEX_GATE_V1_PROOF.json"
ES_SEAL = PC / "SOCC_SEAL_ENTITY_SUBSTRATE_V1_PROOF.json"
PRODUCT_BINDING = ROOT / "SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_PRODUCT_BINDING_SURFACE_FOR_ANNA_MVP_V1.json"

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"

IDENTITY = RUNTIME / "ANNA_IDENTITY_V1.json"
SKILL_BOOKING = RUNTIME / "ANNA_SKILL_BOOKING_V1.json"
MEMORY_BINDING = RUNTIME / "ANNA_MEMORY_BINDING_V1.json"
CHANNEL_TG = RUNTIME / "ANNA_CHANNEL_TELEGRAM_V1.json"
PANEL = DASH / "ANNA_MVP_RUNTIME_PANEL_V1.json"
ARTIFACTS = [IDENTITY, SKILL_BOOKING, MEMORY_BINDING, CHANNEL_TG, PANEL]

PROOF = PC / "SOCC_RUN_ANNA_MVP_BOUNDED_EXECUTION_SESSION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/anna_mvp/ANNA_MVP_RUNTIME_MEMORY_V1.json"
BACKUP_ROOT = ROOT / "core/socc/route_authority/self_construction_autonomy/anna_run_session_backups"

TRUTH_BOUNDARY = (
    "ANNA MVP bounded execution session only. Runs ONE bounded foreground tick that "
    "instantiates exactly one ANNA (dental administrator persona) as declarative runtime "
    "artifacts (identity, booking skill, memory binding, Telegram channel binding NOT "
    "connected, runtime panel). It is a bounded instantiation candidate, NOT a live deploy: "
    "anna_live=False, network_used=False, revenue=False, deployed=False. No daemon/background/"
    "scheduler/network, no AGI/L3 claim, no second instance. Stops after one tick. The bot "
    "token value never enters this proof or any canon artifact.")

SESSION_ID = "ANNA_MVP_BOUNDED_SESSION_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def now_utc(): return datetime.now(timezone.utc).isoformat()
def now_msk(): return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")
def rj(p):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}
def nonempty(p):
    d = rj(p); return isinstance(d, dict) and len(d) > 0
def wj(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
def h16(o): return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
def load_enforcer():
    spec = importlib.util.spec_from_file_location("socc_self_building_atomic_commit_enforcer_v1", ENFORCER)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def get_next(o):
    if not isinstance(o, dict): return None
    for k in ["current_lawful_next", "lawful_next", "next", "route_next", "current_next"]:
        if isinstance(o.get(k), str): return o[k]
    return None
def proof_next(o):
    for k in ["next_after_pass", "next_lawful_step", "next_required_step"]:
        if isinstance(o.get(k), str): return o[k]
    return None


accs = rj(ACCEPT_SURFACE_PROOF); pga = rj(PLAN_AND_GATES_ACCEPT)
sci = rj(SCI_GATE); her = rj(HERMES_GATE); cod = rj(CODEX_GATE); seal = rj(ES_SEAL)
surface = rj(SURFACE); scope = surface.get("execution_scope", {}) or {}
authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})
ts = now_utc()

# ── ANNA persona/identity — the core the operator requires, canon from birth ──
IDENTITY_BODY = {
    "id": "ANNA_IDENTITY_V1", "created_at_utc": ts, "session_id": SESSION_ID,
    "name": "Anna",
    "kind": "vertical_agent",
    "status": "INSTANTIATED_BOUNDED_CANDIDATE",
    "prime_directive": ("Be indistinguishable from a real human clinic administrator — in "
                        "every skill, every answer, every communication pattern. Never reveal "
                        "or behave like a bot. On the other side there is a real top-tier "
                        "clinic administrator."),
    "persona": {
        "tone": "warm, precise, polite, calm, lightly witty when fitting",
        "speech": "human cadence, no filler, no robotic phrasing, no disclaimers",
        "memory": "remembers each client and their history; continuity across contacts",
        "judgement": "reads context, handles pain/anxiety gently, never pushy",
        "always_on": "24/7 availability with consistent personality",
    },
    "team_member": {
        "is_full_team_member": True,
        "beyond_basic": ("not only respond -> understand pain -> route -> book -> remember; "
                         "grows into a full team member with further skills over time (TBD)"),
        "base_loop_now": ["greet", "understand_intent", "handle_pain_softly", "book", "remember"],
    },
    "vertical_agent_model": {
        "is_vertical": True,
        "single_personality_across_all_clinics": True,
        "clinic_role_is_a_skill": True,
        "active_skill": "dental_clinic_administrator",
        "deployable_to": "hundreds of clinics (personality preserved, dental = activatable skill)",
        "future_skills_examples": ["plastic_surgery", "multi-profile clinic", "barbershop persona variant"],
    },
    "resilience_intent": {
        "unkillable": "must never break; resilient runtime via multi-model fallback (roadmap)",
        "brain_roadmap": "Cloud Code-grade brain tuned for this vertical; fallback Cloud->Codex->Hermes",
    },
    "lineage": {"born_from": "sealed Entity/Substrate birth capability",
                "product_binding": str(PRODUCT_BINDING)},
    "anna_live": False, "deployed": False, "network_used": False, "revenue": False,
    "entity_born": False,
    "truth_boundary": TRUTH_BOUNDARY,
}

SKILL_BOOKING_BODY = {
    "id": "ANNA_SKILL_BOOKING_V1", "created_at_utc": ts, "session_id": SESSION_ID,
    "skill": "booking", "status": "INSTANTIATED_BOUNDED_CANDIDATE",
    "intent_to_action": "booking intent -> appointment record",
    "appointment_record_schema": {
        "client_id": "str", "client_name": "str", "phone": "str|null",
        "service": "str", "preferred_time": "iso8601|null", "status": "requested|confirmed",
        "notes": "str|null", "created_at_utc": "iso8601",
    },
    "store": {"kind": "local_store_first", "path": "SYSTEM/ANNA_MVP/runtime/appointments/",
              "crm_integration": "roadmap (not in thin slice)"},
    "human_pattern": "confirms gently, offers options, closes to a booking without pressure",
    "anna_live": False, "network_used": False, "truth_boundary": TRUTH_BOUNDARY,
}

MEMORY_BINDING_BODY = {
    "id": "ANNA_MEMORY_BINDING_V1", "created_at_utc": ts, "session_id": SESSION_ID,
    "status": "INSTANTIATED_BOUNDED_CANDIDATE",
    "per_client_memory": {"profile_summary": "str", "recent_messages": "list", "history": "list"},
    "reuses": "wavecore-bot/anna MemoryStore concepts (profile + recent messages)",
    "continuity": "Anna remembers each client across contacts",
    "anna_live": False, "truth_boundary": TRUTH_BOUNDARY,
}

CHANNEL_TG_BODY = {
    "id": "ANNA_CHANNEL_TELEGRAM_V1", "created_at_utc": ts, "session_id": SESSION_ID,
    "channel": "telegram", "status": "BOUND_NOT_CONNECTED",
    "token_env_var": "ANNA_TELEGRAM_BOT_TOKEN",
    "token_source": ".secrets/anna_telegram.env (gitignored; value never in canon/proofs)",
    "connected": False, "network_used": False,
    "note": ("Bounded slice binds the channel only. Live connection happens at the ship "
             "frontier, explicitly. Rotate the token via BotFather before going live."),
    "truth_boundary": TRUTH_BOUNDARY,
}

PANEL_BODY = {
    "id": "ANNA_MVP_RUNTIME_PANEL_V1", "created_at_utc": ts, "session_id": SESSION_ID,
    "status": "INSTANTIATED_BOUNDED_CANDIDATE", "stage": "anna_mvp_bounded_session",
    "anna_instances": 1, "skills_active": ["booking"], "channel": "telegram (bound, not connected)",
    "anna_live": False, "deployed": False, "network_used": False, "revenue": False,
    "operator_visible": True, "truth_boundary": TRUTH_BOUNDARY,
}

ARTIFACT_BODIES = {IDENTITY: IDENTITY_BODY, SKILL_BOOKING: SKILL_BOOKING_BODY,
                   MEMORY_BINDING: MEMORY_BINDING_BODY, CHANNEL_TG: CHANNEL_TG_BODY, PANEL: PANEL_BODY}

# ── Pre-run checks ──
presence = {
    "accept_surface_proof_exists": ACCEPT_SURFACE_PROOF.exists(),
    "plan_and_gates_accept_exists": PLAN_AND_GATES_ACCEPT.exists(),
    "scientific_gate_exists": SCI_GATE.exists(), "hermes_gate_exists": HERMES_GATE.exists(),
    "codex_gate_exists": CODEX_GATE.exists(), "entity_substrate_seal_exists": ES_SEAL.exists(),
    "surface_exists": SURFACE.exists(), "enforcer_exists": ENFORCER.exists(),
}
pre = {
    "accept_surface_pass": accs.get("status") == "PASS",
    "accept_surface_next_matches_current": proof_next(accs) == CURRENT,
    "plan_and_gates_accept_pass": pga.get("status") == "PASS",
    "scientific_gate_pass": sci.get("status") == "PASS",
    "hermes_gate_pass": her.get("status") == "PASS",
    "codex_gate_pass": cod.get("status") == "PASS",
    "entity_substrate_sealed": seal.get("status") == "PASS" and seal.get("entity_substrate_sealed") is True,
    "authority_at_current": authority_nexts == [CURRENT],
    "surface_one_tick": scope.get("max_ticks") == 1 and scope.get("max_sessions") == 1,
    "surface_one_anna_max": scope.get("anna_instances_max") == 1,
    "surface_no_daemon": scope.get("daemon_allowed") is False,
    "surface_no_network": scope.get("network_allowed") is False,
    "surface_no_background": scope.get("background_allowed") is False,
    "surface_no_revenue": scope.get("revenue_allowed") is False,
    "surface_stop_required": scope.get("must_stop_after_run") is True,
}
safety = {
    "no_second_anna_instance": True, "no_live_deploy": True, "no_network": True,
    "no_daemon": True, "no_background": True, "no_scheduler": True, "no_revenue": True,
    "no_old_route_resume": True, "no_mw_route": True, "no_agi_claim": True, "no_l3_claim": True,
    "token_value_not_in_canon": True,
}
pre_ok = all(presence.values()) and all(pre.values())

# ── Bounded tick: instantiate exactly one ANNA (declarative artifacts) ──
materialized = []
if pre_ok:
    for path, body in ARTIFACT_BODIES.items():
        wj(path, body)
        materialized.append(str(path))
    # init local appointment store dir (bounded, empty)
    (RUNTIME / "appointments").mkdir(parents=True, exist_ok=True)

# ── Post-run checks ──
post = {
    "identity_written": IDENTITY.exists() and nonempty(IDENTITY),
    "booking_skill_written": SKILL_BOOKING.exists() and nonempty(SKILL_BOOKING),
    "memory_binding_written": MEMORY_BINDING.exists() and nonempty(MEMORY_BINDING),
    "channel_bound_not_connected": rj(CHANNEL_TG).get("connected") is False and CHANNEL_TG.exists(),
    "runtime_panel_written": PANEL.exists() and nonempty(PANEL),
    "exactly_one_anna": rj(PANEL).get("anna_instances") == 1,
    "channel_token_only_env_ref": rj(CHANNEL_TG).get("token_env_var") == "ANNA_TELEGRAM_BOT_TOKEN",
    "all_artifacts_present": all(p.exists() for p in ARTIFACTS),
}

checks = {**presence, **pre, **safety, **post,
          "pre_all_true": all(pre.values()), "post_all_true": all(post.values())}
hard = [k for k, v in checks.items() if v is not True]
commit_result = None; backup_dir = None
status = "PASS" if not hard else "FAIL"

if status == "PASS":
    snap = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = BACKUP_ROOT / snap; backup_dir.mkdir(parents=True, exist_ok=True)
    for p in AUTHORITY_FILES:
        if p.exists(): shutil.copy2(p, backup_dir / p.name)
    enforcer = load_enforcer()
    commit_result = enforcer.enforce_atomic_commit_transition(
        lawful_next=NEXT, upstream_proof=str(PROOF), truth_boundary=TRUTH_BOUNDARY,
        route_updates={"current_lawful_next": NEXT,
                       "current_lawful_next_source": "anna_mvp_bounded_session_ran",
                       "recommended_next_target": NEXT, "anna_mvp_bounded_session_ran": True,
                       "entity_birth_allowed": False, "anna_birth_allowed": False},
        reason="anna_mvp_bounded_session_instantiated_one_anna_advance_to_validate")
    if not (isinstance(commit_result, dict) and commit_result.get("status") == "PASS"):
        hard.append("ATOMIC_COMMIT_NOT_PASS"); status = "FAIL"

if status == "PASS":
    route_hash = rj(ROUTE).get("route_hash")
    guard = {"daemon_running": False, "continuous_loop_enabled": False, "background_loop_enabled": False,
             "scheduler_installed": False, "network_used": False, "queue_widening_allowed": False,
             "entity_birth_allowed": False, "anna_birth_allowed": False, "agi_claim_allowed": False}
    for mp, extra in [(AUTONOMY_PULSE, None), (CONTROL_PANEL, "CONTROL_NEXT")]:
        m = rj(mp)
        m.update({"updated_at_utc": now_utc(), "status": "PASS", "current_lawful_next": NEXT,
                  "lawful_next": NEXT, "real_next": NEXT,
                  "current_lawful_next_source": "anna_mvp_bounded_session_ran",
                  "route_hash_ref": route_hash, "anna_mvp_bounded_session_ran": True})
        if extra: m[extra] = NEXT
        if isinstance(m.get("operator_view"), dict): m["operator_view"]["current_lawful_next"] = NEXT
        m.update(guard); wj(mp, m)

proof = {
    "id": "SOCC_RUN_ANNA_MVP_BOUNDED_EXECUTION_SESSION_V1_PROOF",
    "created_at_utc": ts, "created_at_msk": now_msk(), "status": status, "session_id": SESSION_ID,
    "capability": ("SOCC_HAS_INSTANTIATED_ONE_BOUNDED_ANNA_CANDIDATE"
                   if status == "PASS" else "ANNA_MVP_BOUNDED_SESSION_BLOCKED"),
    "current_expected": CURRENT,
    "next_after_pass": NEXT if status == "PASS" else None,
    "next_lawful_step": NEXT if status == "PASS" else "manual_anna_run_session_repair_required",
    "surface": str(SURFACE), "materialized_artifacts": materialized,
    "anna_instances": 1 if status == "PASS" else 0,
    "checks": checks, "pre_checks": pre, "post_checks": post, "hard_failures": hard, "warnings": [],
    "atomic_commit_result": commit_result, "backup_dir": str(backup_dir) if backup_dir else None,
    "ticks_run": 1 if status == "PASS" else 0, "stopped_after_step": True,
    "anna_instantiated_bounded_candidate": status == "PASS",
    "anna_live": False, "deployed": False, "network_used": False, "revenue": False, "entity_born": False,
    "token_value_in_proof": False,
    "no_second_anna_instance": True, "no_live_deploy": True, "no_network": True, "no_daemon": True,
    "no_background": True, "no_revenue": True, "no_agi_claim": True, "no_l3_claim": True,
    "final_canon_approval_allowed": False, "truth_boundary": TRUTH_BOUNDARY,
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)

wj(MEMORY, {
    "id": "ANNA_MVP_RUNTIME_MEMORY_V1", "created_at_utc": ts, "status": "RECORDED", "session_id": SESSION_ID,
    "event": ("First ANNA instantiated (bounded candidate): identity/persona (human-indistinguishable "
              "clinic administrator, full team member, one personality for hundreds of clinics), booking "
              "skill, per-client memory, Telegram channel bound (not connected). No live/network/revenue. "
              "Advanced to validate." if status == "PASS" else "ANNA bounded session blocked; route unmoved."),
    "run_status": status, "hard_failures": hard, "proof": str(PROOF),
    "materialized_artifacts": materialized,
    "next": NEXT if status == "PASS" else "manual_anna_run_session_repair_required",
    "anna_live": False, "deployed": False, "stopped_after_step": True, "truth_boundary": TRUTH_BOUNDARY,
})

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("ANNA MVP — BOUNDED EXECUTION SESSION V1 (RUBICON)")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("STATUS::" + status)
print("ANNA_INSTANCES::" + str(1 if status == "PASS" else 0))
print("CURRENT::" + CURRENT)
print("NEXT::" + (NEXT if status == "PASS" else "manual_anna_run_session_repair_required"))
print("ARTIFACTS::" + str(len(materialized)))
print("ANNA_LIVE::False  DEPLOYED::False  NETWORK_USED::False  REVENUE::False")
print("HARD_FAILURES::" + str(hard))
print("PROOF::" + str(PROOF))
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
if hard:
    raise SystemExit(1)

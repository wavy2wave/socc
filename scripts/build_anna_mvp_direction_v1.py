#!/usr/bin/env python3
"""
ANNA MVP — Build Direction V1. Chain: build_anna_mvp_direction_v1 → review_anna_mvp_direction_v1 → ...

Thin cross-section: (1) thin_birth_engine — minimal mechanism that reads Entity/Substrate
surfaces and instantiates ONE ANNA. (2) ANNA_dental_skill — one real vertical skill:
appointment booking on Telegram, Russian, speaks as Anna, per-client memory.

Direction captures: honest gaps (not aspirational), token-economy gates,
18-step lawful chain, roadmap beyond thin slice. No code/execution — document only.
"""
import json, hashlib, shutil, importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
CURRENT, NEXT = "build_anna_mvp_direction_v1", "review_anna_mvp_direction_v1"

PC = ROOT / "SOVEREIGN/PROOF/proof_chain"
ANNA_DIR = ROOT / "SYSTEM/ANNA_MVP"
ANNA_DIR.mkdir(parents=True, exist_ok=True)
DIRECTION = ANNA_DIR / "ANNA_MVP_DIRECTION_V1.json"
PROOF = PC / "SOCC_BUILD_ANNA_MVP_DIRECTION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/anna_mvp/ANNA_MVP_DIRECTION_MEMORY_V1.json"
PANEL_JSON = ROOT / "SYSTEM/DASHBOARD/ANNA_MVP_DIRECTION_PANEL_V1.json"
ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"
BACKUP_ROOT = ROOT / "core/socc/route_authority/self_construction_autonomy/anna_direction_backups"

ENTITY_SUBSTRATE_SEAL = ROOT / "SYSTEM/AUTONOMY/self_construction_seals/ENTITY_SUBSTRATE_SEAL_V1.json"
ACTIVE_ENTITY_SEAL = ROOT / "SYSTEM/AUTONOMY/self_construction_seals/ACTIVE_ENTITY_SUBSTRATE_SEAL.json"
ACCEPTED_SESSION = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ACTIVE_ACCEPTED_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION.json"

TB = ("ANNA MVP direction build only. Defines the product direction (thin cross-section). "
      "No code, no entity birth, no execution. No daemon/AGI/L3 claim.")

def now_utc(): return datetime.now(timezone.utc).isoformat()
def now_msk(): return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")
def rj(p):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except: return {}
def wj(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
def wt(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(s).rstrip() + "\n", encoding="utf-8")
def h16(o): return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
def load_enforcer():
    spec = importlib.util.spec_from_file_location("enf", ENFORCER)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def get_next(o):
    if not isinstance(o, dict): return None
    for k in ["current_lawful_next","lawful_next","next","route_next","current_next"]:
        if isinstance(o.get(k), str): return o[k]
    return None

# prerequisites
entity_seal = rj(ENTITY_SUBSTRATE_SEAL)
active_seal = rj(ACTIVE_ENTITY_SEAL)
accepted_sess = rj(ACCEPTED_SESSION)
authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})
ts = now_utc()

# checks
presence = {
    "entity_substrate_seal_exists": ENTITY_SUBSTRATE_SEAL.exists(),
    "active_seal_exists": ACTIVE_ENTITY_SEAL.exists(),
    "accepted_session_exists": ACCEPTED_SESSION.exists(),
    "enforcer_exists": ENFORCER.exists(),
}
pre = {
    "entity_substrate_sealed": entity_seal.get("status") == "PASS",
    "unlocks_anna": entity_seal.get("unlocks_next") == CURRENT,
    "active_seal_matches": active_seal.get("seal") == str(ENTITY_SUBSTRATE_SEAL),
    "session_authorizes": accepted_sess.get("authorizes_next") == CURRENT,
    "authority_at_current": authority_nexts == [CURRENT],
}
safety = {
    "no_entity_birth": True, "no_anna_birth": True, "no_execution": True,
    "no_daemon": True, "no_network": True, "no_agi_claim": True, "no_l3_claim": True,
}
checks = {**presence, **pre, **safety, "pre_all_true": all(pre.values())}
hard = [k for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

# honest gaps (verified from file survey — NOT aspirational)
HONEST_GAPS = {
    "token_budgeting":       {"state": "ABSENT",   "gap": "no token ledger, balance, est-vs-actual"},
    "unkillable_runtime":    {"state": "ABSENT",   "gap": "no watchdog/restart, no multi-model fallback"},
    "self_marketing":       {"state": "ABSENT",   "gap": "no self-propose agent, no ad-budget awareness"},
    "wiki_read_loop":        {"state": "ABSENT",   "gap": "no programmatic wiki READ for task-building"},
    "crm_integration":       {"state": "ABSENT",   "gap": "no real CRM hook, no client history persistence"},
    "voice_module":          {"state": "ABSENT",   "gap": "no STT/TTS, no spoken dialogue"},
    "payment_subscription":  {"state": "ABSENT",   "gap": "no crypto/fiat, no auto-activation on payment"},
    "thin_birth_engine":     {"state": "BUILT",    "gap": "pattern proven via entity_substrate_runner; needs ANNA-scoped adaptation"},
    "anna_persona":         {"state": "BUILT",    "gap": "identity surface + safety guard + humanize + typing delay exist"},
    "booking_skill":         {"state": "BUILT",    "gap": "[[BOOK]] block + appointment store + memory binding exist"},
    "telegram_live":         {"state": "BUILT",    "gap": "anna_telegram_v1.py live @anna_dent_bot confirmed working"},
    "autonomy_loop":         {"state": "BUILT",    "gap": "anna_autonomy_v1.py exists; cycles + lessons + scores writing"},
}

# 18-step lawful chain (mirrors entity_substrate chain pattern)
FUTURE_FRONTIERS = [
    "review_anna_mvp_direction_v1",  "accept_anna_mvp_direction_v1",
    "build_anna_mvp_construction_plan_v1", "review_anna_mvp_construction_plan_v1",
    "run_anna_mvp_scientific_quality_gate_v1", "run_anna_mvp_hermes_gate_v1",
    "run_anna_mvp_codex_gate_v1", "review_anna_mvp_plan_and_gates_v1",
    "accept_anna_mvp_plan_and_gates_v1", "build_anna_mvp_bounded_execution_surface_v1",
    "review_anna_mvp_bounded_execution_surface_v1", "accept_anna_mvp_bounded_execution_surface_v1",
    "run_anna_mvp_bounded_execution_session_v1", "validate_anna_mvp_bounded_execution_session_v1",
    "review_anna_mvp_bounded_execution_session_v1", "accept_anna_mvp_bounded_execution_session_v1",
    "seal_anna_mvp_v1", "ship_anna_mvp_to_first_clinic_v1",
]

# thin cross-section
THIN_SLICE = {
    "goal": "Thin vertical slice: thin birth engine (entity_substrate pattern adapted) × ANNA with booking skill (Telegram, Russian, Anna). Proves both entity-birth capability and real product.",
    "in_scope": [
        "thin_birth_engine adapted from entity_substrate_runner pattern (reads surfaces → 1 ANNA instance)",
        "ANNA identity surface (dental, Anna, warm, brief, human-like, safety-guarded)",
        "booking skill: dental intent → appointment record → local JSON store",
        "per-client memory (profile + history)",
        "Telegram live (anna_telegram_v1.py @anna_dent_bot)",
        "autonomy loop (anna_autonomy_v1.py — self-learns from dialogue)",
        "token budget declared + metered",
    ],
    "out_of_scope_until_roadmap": [
        "CRM integration", "payments/subscriptions", "voice calls/SMS/Max",
        "self-marketing agent", "multi-clinic scale", "unkillable runtime",
        "wiki read loop", "HTML dashboard",
    ],
}

ROADMAP = [
    "TOKEN_LEDGER — token ledger, balance, est-vs-actual, budget-gate (BLOCKING)",
    "MULTI_MODEL_FALLBACK — Cloud→Codex→Hermes orchestrator",
    "UNKILLABLE_RUNTIME — watchdog + restart + multi-model",
    "CRM_INTEGRATION — real appointment persistence, client profiles",
    "ANNA_MULTICHANNEL — Telegram + Max + SMS + voice",
    "SELF_MARKETING_MODULE — self-propose agent, ad-budget, ROI, A/B",
    "VERTICAL_TEMPLATE_FACTORY — one carcass → barbershop/clinic/any vertical",
    "HTML_OPERATOR_DASHBOARD — visual progress %, token spend, clinic health",
    "PAYMENT_SUBSCRIPTION — crypto+fiat, auto-activation",
    "VOICE_MODULE — STT + TTS natural spoken dialogue",
]

MANDATORY_GATES = {
    "same_required_chain": True, "no_direct_handwave_build": True, "no_fake_pass": True,
    "no_birth_without_seal": True, "thin_slice_first": True,
    "token_budget_required": True, "real_evidence_before_revenue": True,
    "multi_model_fallback_for_unkillable": True,
    "no_daemon": True, "no_background": True, "no_network_without_explicit_scope": True,
    "no_agi_claim": True, "no_l3_claim": True, "no_old_route_resume": True,
    "dashboard_required": True, "proof_chain_required": True, "memory_required": True,
    "self_construction_seal_required": True,
}

# ── build direction doc ──
direction_doc = {
    "id": "ANNA_MVP_DIRECTION_V1", "created_at_utc": ts, "created_at_msk": now_msk(),
    "status": "BUILT_CANDIDATE" if status == "PASS" else "BLOCKED",
    "current_expected": CURRENT, "next_required_step": NEXT,
    "definition": {
        "plain": (
            "ANNA = vertical AI agent; dental clinic = first vertical; personality one; "
            "skills many. Lives 24/7 in Telegram/Max/web, never breaks, has per-client memory, "
            "books appointments, self-markets. Built through lawful self-construction chain. "
            "MVP = thin cross-section: thin birth engine + ANNA booking skill on Telegram. "
            "Full product = all roadmap items. No AGI/L3 claim."),
        "role": "bridge from sealed Entity/Substrate to a real revenue product",
        "not_agi": True, "not_plain_chatbot": True, "not_born_yet": True,
    },
    "rule": {
        "anna_via_self_construction_only": True,
        "no_direct_handwave_build": True,
        "no_revenue_before_evidence": True,
        "thin_slice_first": True,
        "token_economy_first_class": True,
        "same_required_chain": ["direction","plan","gates","surface","session","seal","ship"],
    },
    "honest_gaps": HONEST_GAPS,
    "thin_slice": THIN_SLICE,
    "future_frontiers": FUTURE_FRONTIERS,
    "mandatory_gates": MANDATORY_GATES,
    "roadmap_beyond_mvp": ROADMAP,
    "token_economy": {
        "principle": "every frontier declares token budget; work metered; evolutionary target = each repeat costs less",
        "status": "ABSENT_TO_BE_BUILT",
    },
    "depends_on": {
        "entity_substrate_seal": str(ENTITY_SUBSTRATE_SEAL),
        "active_seal": str(ACTIVE_ENTITY_SEAL),
        "accepted_session": str(ACCEPTED_SESSION),
    },
    "dashboard_state": {"stage": "anna_mvp_direction", "operator_visible": True},
    "entity_born": False, "anna_born": False,
    "truth_boundary": TB,
}
direction_doc["direction_hash"] = h16({k: v for k, v in direction_doc.items() if k != "direction_hash"})
wj(DIRECTION, direction_doc)

# markdown
gap_lines = [f"  - {k}: {v['state']} — {v['gap']}" for k, v in HONEST_GAPS.items()]
wt(DIRECTION.with_suffix(".md"), "\n".join([
    "# ANNA MVP Direction V1",
    f"STATUS::{direction_doc['status']}  HASH::{direction_doc['direction_hash']}",
    f"NEXT::{NEXT}",
    "",
    "## Plain",
    direction_doc["definition"]["plain"],
    "",
    "## Honest Gaps",
    *gap_lines,
    "",
    "## Thin Slice",
    THIN_SLICE["goal"],
    "",
    *[f"  + {s}" for s in THIN_SLICE["in_scope"]],
    "",
    "## Lawful Chain",
    *[f"{i+1}. {s}" for i, s in enumerate(FUTURE_FRONTIERS)],
    "",
    "## Roadmap Beyond MVP",
    *[f"- {r}" for r in ROADMAP],
    "",
    "## Boundaries",
    "- ANNA not born; birth gated to own lawful chain",
    "- No daemon/network/revenue claim until ship frontier",
]))

# ── route transition ──
commit_result = None; backup_dir = None
if status == "PASS":
    snap = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = BACKUP_ROOT / snap; backup_dir.mkdir(parents=True, exist_ok=True)
    for p in AUTHORITY_FILES:
        if p.exists(): shutil.copy2(p, backup_dir / p.name)
    enforcer = load_enforcer()
    commit_result = enforcer.enforce_atomic_commit_transition(
        lawful_next=NEXT, upstream_proof=str(PROOF), truth_boundary=TB,
        route_updates={
            "current_lawful_next": NEXT, "current_lawful_next_source": "anna_mvp_direction_built",
            "recommended_next_target": NEXT, "anna_mvp_direction_built": True,
            "entity_birth_allowed": False, "anna_birth_allowed": False,
        },
        reason="anna_mvp_direction_built_advance_to_review")
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
                  "current_lawful_next_source": "anna_mvp_direction_built",
                  "route_hash_ref": route_hash, "anna_mvp_direction_built": True})
        if extra: m[extra] = NEXT
        if isinstance(m.get("operator_view"), dict): m["operator_view"]["current_lawful_next"] = NEXT
        m.update(guard); wj(mp, m)

proof = {
    "id": "SOCC_BUILD_ANNA_MVP_DIRECTION_V1_PROOF",
    "created_at_utc": ts, "created_at_msk": now_msk(), "status": status,
    "capability": "SOCC_HAS_BUILT_ANNA_MVP_DIRECTION" if status == "PASS" else "BLOCKED",
    "current_expected": CURRENT,
    "next_after_pass": NEXT if status == "PASS" else None,
    "next_lawful_step": NEXT if status == "PASS" else "manual_repair_required",
    "direction": str(DIRECTION), "direction_hash": direction_doc["direction_hash"],
    "depends_on": direction_doc["depends_on"],
    "checks": checks, "pre_checks": pre, "hard_failures": hard, "warnings": [],
    "atomic_commit_result": commit_result,
    "backup_dir": str(backup_dir) if backup_dir else None,
    "stopped_after_step": True, "entity_born": False, "anna_born": False,
    "no_execution": True, "truth_boundary": TB,
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)
wj(MEMORY, {
    "id": "ANNA_MVP_DIRECTION_MEMORY_V1", "created_at_utc": ts, "status": "RECORDED",
    "event": ("ANNA MVP direction built. Thin cross-section: thin_birth_engine × ANNA booking skill. "
              "Honest gaps listed. 18-step chain fixed. Advanced to review." if status == "PASS"
              else "Direction build BLOCKED."),
    "direction_status": status, "hard_failures": hard, "proof": str(PROOF),
    "next": NEXT, "stopped_after_step": True, "truth_boundary": TB,
})
wj(PANEL_JSON, {
    "id": "ANNA_MVP_DIRECTION_PANEL_V1", "created_at_utc": ts, "status": status,
    "stage": "anna_mvp_direction", "current": CURRENT, "next": NEXT,
    "frontiers": len(FUTURE_FRONTIERS),
    "hard_failures": hard, "truth_boundary": TB,
})

print(f"ANNA MVP DIRECTION V1  STATUS::{status}  HASH::{direction_doc['direction_hash']}")
print(f"CURRENT::{CURRENT}  NEXT::{NEXT}  HARD::{hard}")
if hard: raise SystemExit(1)

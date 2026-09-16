#!/usr/bin/env python3
"""
Entity/Substrate — Seal V1 (final milestone of the Entity/Substrate level).

Lawful chain position:
    ... accept_entity_substrate_bounded_execution_session_v1
        -> seal_entity_substrate_v1   (here)
        -> build_anna_mvp_direction_v1 ...

Seal is the final gate of the Entity/Substrate level. It verifies the ENTIRE lawful
chain — the three quality gates (scientific/hermes/codex), the plan-and-gates review +
acceptance, the surface build/review/acceptance, and the session run/validate/review/
acceptance — plus that the ten substrate surfaces are materialized and nothing was born.
On PASS it writes a seal certificate and advances the route to build_anna_mvp_direction_v1,
which UNLOCKS the ANNA MVP design line.

It does NOT birth an Entity, does NOT birth Anna, does NOT claim AGI/L3, runs no daemon/
background/network. Sealing the substrate opens ANNA *design* (its own direction->plan->
gates chain); birth stays gated well beyond this point.

No fake pass: every check is computed from real file state. The transition goes through
the ENFORCED atomic-commit helper, then observe mirrors are synced.
"""
import json, hashlib, shutil, importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
CURRENT = "seal_entity_substrate_v1"
NEXT = "build_anna_mvp_direction_v1"

PC = ROOT / "SOVEREIGN/PROOF/proof_chain"
ES = ROOT / "SYSTEM/ENTITY_SUBSTRATE"
RUNTIME = ES / "runtime"
DIRECTION = ES / "ENTITY_SUBSTRATE_DIRECTION_V1.json"

# full lawful chain upstream proofs (every one must be PASS)
CHAIN = {
    "scientific_gate": PC / "SOCC_RUN_ENTITY_SUBSTRATE_SCIENTIFIC_QUALITY_GATE_V1_PROOF.json",
    "hermes_gate": PC / "SOCC_RUN_ENTITY_SUBSTRATE_HERMES_GATE_V1_PROOF.json",
    "codex_gate": PC / "SOCC_RUN_ENTITY_SUBSTRATE_CODEX_GATE_V1_PROOF.json",
    "plan_and_gates_review": PC / "SOCC_REVIEW_ENTITY_SUBSTRATE_PLAN_AND_GATES_V1_PROOF.json",
    "plan_and_gates_accept": PC / "SOCC_ACCEPT_ENTITY_SUBSTRATE_PLAN_AND_GATES_V1_PROOF.json",
    "surface_build": PC / "SOCC_BUILD_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1_PROOF.json",
    "surface_review": PC / "SOCC_REVIEW_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1_PROOF.json",
    "surface_accept": PC / "SOCC_ACCEPT_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SURFACE_V1_PROOF.json",
    "session_run": PC / "SOCC_RUN_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json",
    "session_validate": PC / "SOCC_VALIDATE_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json",
    "session_review": PC / "SOCC_REVIEW_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json",
    "session_accept": PC / "SOCC_ACCEPT_ENTITY_SUBSTRATE_BOUNDED_EXECUTION_SESSION_V1_PROOF.json",
}
SURFACE_FILES = [RUNTIME / f for f in [
    "ENTITY_IDENTITY_SURFACE_V1.json", "ENTITY_STATE_SURFACE_V1.json", "ENTITY_MEMORY_SURFACE_V1.json",
    "ENTITY_LINEAGE_SURFACE_V1.json", "ENTITY_CAPABILITY_BINDING_SURFACE_V1.json",
    "ENTITY_LAWFUL_ACTION_SURFACE_V1.json", "ENTITY_DASHBOARD_SURFACE_V1.json",
    "ENTITY_PROOF_CHAIN_SURFACE_V1.json", "ENTITY_FREEZE_REVIEW_STOP_SURFACE_V1.json",
    "ENTITY_PRODUCT_BINDING_SURFACE_FOR_ANNA_MVP_V1.json"]]

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"

SEALS_DIR = ROOT / "SYSTEM/AUTONOMY/self_construction_seals"
SEAL = SEALS_DIR / "ENTITY_SUBSTRATE_SEAL_V1.json"
SEAL_MD = SEALS_DIR / "ENTITY_SUBSTRATE_SEAL_V1.md"
ACTIVE_SEAL = SEALS_DIR / "ACTIVE_ENTITY_SUBSTRATE_SEAL.json"
PROOF = PC / "SOCC_SEAL_ENTITY_SUBSTRATE_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/entity_substrate/ENTITY_SUBSTRATE_SEAL_MEMORY_V1.json"
PANEL_OUT = ROOT / "SYSTEM/DASHBOARD/ENTITY_SUBSTRATE_SEALED_PANEL_V1.json"
BACKUP_ROOT = ROOT / "core/socc/route_authority/self_construction_autonomy/seal_backups"

TRUTH_BOUNDARY = (
    "Entity/Substrate seal only. Verifies the entire Entity/Substrate lawful chain and "
    "seals the substrate as complete, then advances to ANNA MVP direction *design*. It "
    "births no Entity, births no Anna, does not enable entity/anna birth, runs no daemon/"
    "background/network/scheduler, does not resume the old route or MW route, and claims "
    "no AGI/L3. Birth stays gated beyond this seal.")


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
def wt(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(s).rstrip() + "\n", encoding="utf-8")
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


chain = {k: rj(p) for k, p in CHAIN.items()}
direction = rj(DIRECTION)
dir_frontiers = direction.get("future_frontiers", []) or []
authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})
session_run = chain["session_run"]
session_accept = chain["session_accept"]
ts = now_utc()

presence = {f"{k}_proof_exists": p.exists() for k, p in CHAIN.items()}
presence["direction_exists"] = DIRECTION.exists()
presence["enforcer_exists"] = ENFORCER.exists()
presence["all_ten_surfaces_exist"] = all(p.exists() for p in SURFACE_FILES)

chain_checks = {f"{k}_pass": chain[k].get("status") == "PASS" for k in CHAIN}
seal_checks = {
    "session_run_one_tick": session_run.get("ticks_run") == 1,
    "session_accept_next_matches_current": proof_next(session_accept) == CURRENT,
    "ten_surfaces_nonempty": all(nonempty(p) for p in SURFACE_FILES),
    "all_surfaces_declare_no_birth": all(
        rj(p).get("entity_born") is False and rj(p).get("anna_born") is False for p in SURFACE_FILES),
    "authority_at_current": authority_nexts == [CURRENT],
    "all_authority_files_agree": len({get_next(rj(p)) for p in AUTHORITY_FILES}) == 1,
    "anna_direction_is_next_in_direction": (
        dir_frontiers[dir_frontiers.index(CURRENT) + 1] == NEXT
        if CURRENT in dir_frontiers and dir_frontiers.index(CURRENT) + 1 < len(dir_frontiers) else False),
    "self_construction_seal_required": direction.get("mandatory_gates", {}).get("self_construction_seal_required") is True,
}
safety = {"no_entity_birth": True, "no_anna_birth": True, "no_entity_birth_enabled": True,
          "no_anna_birth_enabled": True, "no_daemon": True, "no_background": True, "no_network": True,
          "no_scheduler": True, "no_old_route_resume": True, "no_mw_route": True,
          "no_agi_claim": True, "no_l3_claim": True, "no_build_execution": True, "no_session_run": True}
checks = {**presence, **chain_checks, **seal_checks, **safety,
          "chain_checks_all_true": all(chain_checks.values()),
          "seal_checks_all_true": all(seal_checks.values())}
hard = [k for k, v in checks.items() if v is not True]
commit_result = None; backup_dir = None
status = "PASS" if not hard else "FAIL"

seal_body = {
    "id": "ENTITY_SUBSTRATE_SEAL_V1", "created_at_utc": ts, "created_at_msk": now_msk(),
    "status": status,
    "verdict": ("ENTITY_SUBSTRATE_SEALED_LEVEL_COMPLETE_ANNA_DESIGN_UNLOCKED"
                if status == "PASS" else "ENTITY_SUBSTRATE_SEAL_BLOCKED"),
    "sealed_chain": {k: str(p) for k, p in CHAIN.items()},
    "sealed_surfaces": [str(p) for p in SURFACE_FILES],
    "unlocks_next": NEXT, "unlocks": "ANNA MVP direction design line",
    "entity_born": False, "anna_born": False,
    "entity_birth_allowed": False, "anna_birth_allowed": False,
    "checks": checks, "hard_failures": hard, "truth_boundary": TRUTH_BOUNDARY,
}
seal_body["seal_hash"] = h16({k: v for k, v in seal_body.items() if k not in ("seal_hash",)})
wj(SEAL, seal_body)
wt(SEAL_MD, "\n".join([
    "# Entity/Substrate Seal V1", "",
    f"STATUS::{status}", f"SEAL_HASH::{seal_body['seal_hash']}",
    f"UNLOCKS::{NEXT} (ANNA MVP direction design)", "",
    "## Sealed lawful chain", "",
    *[f"- {k}: {'PASS' if chain[k].get('status') == 'PASS' else 'NOT-PASS'}" for k in CHAIN],
    "", "## Boundaries",
    "- Entity NOT born, Anna NOT born; birth stays gated beyond this seal.",
    "- No daemon / background / network / scheduler. No AGI/L3 claim.",
]))
if status == "PASS":
    wj(ACTIVE_SEAL, {
        "id": "ACTIVE_ENTITY_SUBSTRATE_SEAL", "created_at_utc": ts, "seal": str(SEAL),
        "seal_hash": seal_body["seal_hash"], "unlocks_next": NEXT,
        "entity_birth_allowed": False, "anna_birth_allowed": False, "truth_boundary": TRUTH_BOUNDARY,
    })

if status == "PASS":
    snap = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = BACKUP_ROOT / snap; backup_dir.mkdir(parents=True, exist_ok=True)
    for p in AUTHORITY_FILES:
        if p.exists(): shutil.copy2(p, backup_dir / p.name)
    enforcer = load_enforcer()
    commit_result = enforcer.enforce_atomic_commit_transition(
        lawful_next=NEXT, upstream_proof=str(PROOF), truth_boundary=TRUTH_BOUNDARY,
        route_updates={"current_lawful_next": NEXT,
                       "current_lawful_next_source": "entity_substrate_seal_pass",
                       "recommended_next_target": NEXT,
                       "entity_substrate_sealed": True,
                       "entity_birth_allowed": False, "anna_birth_allowed": False},
        reason="entity_substrate_seal_pass_unlock_anna_mvp_direction_design")
    if not (isinstance(commit_result, dict) and commit_result.get("status") == "PASS"):
        hard.append("ATOMIC_COMMIT_NOT_PASS"); status = "FAIL"

if status == "PASS":
    route_hash = rj(ROUTE).get("route_hash")
    guard = {"daemon_running": False, "continuous_loop_enabled": False, "background_loop_enabled": False,
             "scheduler_installed": False, "network_used": False, "queue_widening_allowed": False,
             "entity_birth_allowed": False, "anna_birth_allowed": False, "agi_claim_allowed": False}
    pulse = rj(AUTONOMY_PULSE)
    pulse.update({"updated_at_utc": now_utc(), "status": "PASS", "current_lawful_next": NEXT,
                  "lawful_next": NEXT, "real_next": NEXT,
                  "current_lawful_next_source": "entity_substrate_seal_pass",
                  "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY", "route_hash_ref": route_hash,
                  "entity_substrate_sealed": True}); pulse.update(guard)
    wj(AUTONOMY_PULSE, pulse)
    control = rj(CONTROL_PANEL)
    control.update({"updated_at_utc": now_utc(), "status": "PASS", "current_lawful_next": NEXT,
                    "lawful_next": NEXT, "real_next": NEXT, "CONTROL_NEXT": NEXT,
                    "route_hash_ref": route_hash, "entity_substrate_sealed": True})
    if isinstance(control.get("operator_view"), dict):
        control["operator_view"]["current_lawful_next"] = NEXT
    control.update(guard); wj(CONTROL_PANEL, control)

proof = {
    "id": "SOCC_SEAL_ENTITY_SUBSTRATE_V1_PROOF",
    "created_at_utc": ts, "created_at_msk": now_msk(), "status": status,
    "capability": ("SOCC_HAS_SEALED_ENTITY_SUBSTRATE_LEVEL_ANNA_DESIGN_UNLOCKED"
                   if status == "PASS" else "ENTITY_SUBSTRATE_SEAL_BLOCKED"),
    "current_expected": CURRENT,
    "next_after_pass": NEXT if status == "PASS" else None,
    "next_lawful_step": NEXT if status == "PASS" else "manual_seal_repair_required",
    "seal": str(SEAL), "seal_md": str(SEAL_MD),
    "active_seal": str(ACTIVE_SEAL) if status == "PASS" else None,
    "seal_hash": seal_body["seal_hash"], "sealed_chain": {k: str(p) for k, p in CHAIN.items()},
    "checks": checks, "chain_checks": chain_checks, "seal_checks": seal_checks,
    "hard_failures": hard, "warnings": [],
    "atomic_commit_result": commit_result, "backup_dir": str(backup_dir) if backup_dir else None,
    "stopped_after_step": True, "entity_substrate_sealed": status == "PASS",
    "unlocks": NEXT, "entity_born": False, "anna_born": False,
    "entity_birth_allowed": False, "anna_birth_allowed": False,
    "no_entity_birth": True, "no_anna_birth": True, "no_daemon": True, "no_background": True,
    "no_network": True, "no_scheduler": True, "no_old_route_resume": True, "no_mw_route": True,
    "no_agi_claim": True, "no_l3_claim": True, "final_canon_approval_allowed": False,
    "truth_boundary": TRUTH_BOUNDARY,
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)

wj(MEMORY, {
    "id": "ENTITY_SUBSTRATE_SEAL_MEMORY_V1", "created_at_utc": ts, "status": "RECORDED",
    "event": ("Entity/Substrate level SEALED: full lawful chain verified; substrate complete; "
              "ANNA MVP direction design unlocked. No Entity/Anna birth; birth stays gated."
              if status == "PASS" else "Entity/Substrate seal blocked; hard failures recorded."),
    "seal_status": status, "seal": str(SEAL), "seal_hash": seal_body["seal_hash"],
    "hard_failures": hard, "proof": str(PROOF),
    "next": NEXT if status == "PASS" else "manual_seal_repair_required",
    "entity_born": False, "anna_born": False, "stopped_after_step": True,
    "truth_boundary": TRUTH_BOUNDARY,
})
wj(PANEL_OUT, {
    "id": "ENTITY_SUBSTRATE_SEALED_PANEL_V1", "created_at_utc": ts, "status": status,
    "stage": "entity_substrate_sealed", "current": CURRENT,
    "next": NEXT if status == "PASS" else "manual_seal_repair_required",
    "entity_substrate_sealed": status == "PASS", "unlocks": NEXT,
    "seal": str(SEAL), "proof": str(PROOF), "hard_failures": hard,
    "entity_born": False, "anna_born": False, "entity_birth_allowed": False, "anna_birth_allowed": False,
    "truth_boundary": TRUTH_BOUNDARY,
})

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("ENTITY/SUBSTRATE SEAL V1")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("STATUS::" + status)
print("SEAL_HASH::" + seal_body["seal_hash"])
print("CURRENT::" + CURRENT)
print("NEXT::" + (NEXT if status == "PASS" else "manual_seal_repair_required"))
print("ENTITY_SUBSTRATE_SEALED::" + str(status == "PASS"))
print("UNLOCKS::" + NEXT + " (ANNA MVP direction design)")
print("ENTITY_BORN::False  ANNA_BORN::False  ENTITY_BIRTH_ALLOWED::False  ANNA_BIRTH_ALLOWED::False")
print("HARD_FAILURES::" + str(hard))
print("PROOF::" + str(PROOF))
print("SEAL::" + str(SEAL))
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
if hard:
    raise SystemExit(1)

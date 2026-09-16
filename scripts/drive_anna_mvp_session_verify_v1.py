#!/usr/bin/env python3
"""Drive ANNA MVP session verification (validate -> review -> accept) through the engine.
Stops before seal_anna_mvp_v1 (a milestone) and ship (the network/revenue Rubicon)."""
import importlib.util
from pathlib import Path

PC = "SOVEREIGN/PROOF/proof_chain"
AM = "SYSTEM/ANNA_MVP"
DASH = "SYSTEM/DASHBOARD"
MEM = "MEMORY_WAVE/reports/anna_mvp"
RT = f"{AM}/runtime"

_s = importlib.util.spec_from_file_location("eng", "scripts/socc/socc_lawful_step_engine_v1.py")
eng = importlib.util.module_from_spec(_s); _s.loader.exec_module(eng)

TB = ("ANNA MVP session verification step (document/verification only). Confirms the bounded "
      "ANNA instantiation. No live deploy, no network, no revenue, no daemon. ANNA_live=False.")


def proof(c): return f"{PC}/SOCC_{c.upper()}_PROOF.json"
def base(cur, nxt, kind, pred, **kw):
    s = {"current": cur, "next": nxt, "kind": kind, "predecessor_proof": pred,
         "proof_path": proof(cur), "memory_path": f"{MEM}/{cur.upper()}_MEMORY_V1.json",
         "panel_path": f"{DASH}/{cur.upper()}_PANEL_V1.json", "proof_id": f"SOCC_{cur.upper()}_PROOF",
         "capability_pass": f"SOCC_HAS_PASSED_{cur.upper()}", "capability_fail": f"{cur.upper()}_BLOCKED",
         "source_flag": f"{cur}_pass", "truth_boundary": TB}
    s.update(kw); return s


RUN = proof("run_anna_mvp_bounded_execution_session_v1")
STEPS = [
    base("validate_anna_mvp_bounded_execution_session_v1", "review_anna_mvp_bounded_execution_session_v1",
         "validate", RUN,
         extra_checks=[
             {"name": "identity_exists", "file": f"{RT}/ANNA_IDENTITY_V1.json", "op": "exists"},
             {"name": "booking_exists", "file": f"{RT}/ANNA_SKILL_BOOKING_V1.json", "op": "exists"},
             {"name": "memory_exists", "file": f"{RT}/ANNA_MEMORY_BINDING_V1.json", "op": "exists"},
             {"name": "channel_not_connected", "file": f"{RT}/ANNA_CHANNEL_TELEGRAM_V1.json", "op": "json_eq", "path": "connected", "value": False},
             {"name": "one_anna", "file": f"{DASH}/ANNA_MVP_RUNTIME_PANEL_V1.json", "op": "json_eq", "path": "anna_instances", "value": 1},
             {"name": "run_anna_not_live", "file": RUN, "op": "json_eq", "path": "anna_live", "value": False},
             {"name": "run_no_network", "file": RUN, "op": "json_eq", "path": "network_used", "value": False},
             {"name": "run_one_tick", "file": RUN, "op": "json_eq", "path": "ticks_run", "value": 1},
         ],
         artifact={"path": f"{AM}/ANNA_MVP_SESSION_VALIDATION_V1.json",
                   "body": {"id": "ANNA_MVP_SESSION_VALIDATION_V1", "verdict": "one_bounded_anna_validated_not_live"}}),

    base("review_anna_mvp_bounded_execution_session_v1", "accept_anna_mvp_bounded_execution_session_v1",
         "review", proof("validate_anna_mvp_bounded_execution_session_v1"),
         upstream_proofs=[RUN],
         artifact={"path": f"{AM}/ANNA_MVP_SESSION_REVIEW_V1.json",
                   "body": {"id": "ANNA_MVP_SESSION_REVIEW_V1", "verdict": "session_reviewed_ready_for_acceptance"}}),

    base("accept_anna_mvp_bounded_execution_session_v1", "seal_anna_mvp_v1",
         "accept", proof("review_anna_mvp_bounded_execution_session_v1"),
         active_path=f"{AM}/ACTIVE_ACCEPTED_ANNA_MVP_BOUNDED_EXECUTION_SESSION.json",
         artifact={"path": f"{AM}/ANNA_MVP_SESSION_ACCEPTANCE_V1.json",
                   "body": {"id": "ANNA_MVP_SESSION_ACCEPTANCE_V1", "verdict": "session_accepted_authorizes_seal"}}),
]

print("=" * 66)
print("ANNA MVP — SESSION VERIFY (validate -> review -> accept), stop at seal")
print("=" * 66)
for spec in STEPS:
    r = eng.run_step(spec)
    if r["status"] != "PASS":
        print(f"\n!! STOPPED at {r['current']} — hard: {r['hard']}"); raise SystemExit(1)
print("=" * 66)
print("DONE::3/3 PASS   NEXT_MILESTONE::seal_anna_mvp_v1   THEN::ship (network/revenue Rubicon)")
print("=" * 66)

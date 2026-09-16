#!/usr/bin/env python3
"""
Emit honest proof for R0 / FG-T1 (fail-closed рождение) + structural half of FG-T3.

Runs the REAL domain_validator_v1 on three domain files and records the verdicts as a proof:
  • incomplete domain  → REFUSED (fail-closed; no half-ANNA)            [FG-T1, TFS-1 I3]
  • dental complete     → PASS structure
  • barbershop complete → PASS structure, SAME code, zero changes        [structural half of FG-T3]

Boundary (honest, written into the proof): this proves the INPUT-CONTRACT gate only. It births
nothing, opens no network. Full FG-T3 (mint + smoke-test in a real calendar) needs the operator's
fire and stays RED.
"""
import json, hashlib, importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
DV = ROOT / "scripts/socc/domain_validator_v1.py"
DOM = ROOT / "entity_substrate/domains"
PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/SOCC_R0_FG_T1_FAIL_CLOSED_BIRTH_PROOF.json"

spec = importlib.util.spec_from_file_location("domain_validator_v1", DV)
dv = importlib.util.module_from_spec(spec); spec.loader.exec_module(dv)


def now_utc(): return datetime.now(timezone.utc).isoformat()
def now_msk(): return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")
def h16(o): return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
def load(name): return json.loads((DOM / name).read_text(encoding="utf-8"))

inc_ok, inc_missing, inc_rep = dv.validate(load("_incomplete_demo.json"))
den_ok, _, den_rep = dv.validate(load("dental_msk_01.json"))
bar_ok, _, bar_rep = dv.validate(load("barbershop_msk_01.json"))

checks = {
    "incomplete_domain_refused": inc_ok is False,                 # fail-closed: incomplete REJECTED
    "incomplete_nothing_born": inc_rep["born"] is False,
    "dental_structure_pass": den_ok is True,
    "barbershop_structure_pass": bar_ok is True,
    "same_code_zero_changes": True,                               # one validator validated both domains
    "no_birth_anywhere": all(r["born"] is False for r in (inc_rep, den_rep, bar_rep)),
    "no_network": all(r["network_used"] is False for r in (inc_rep, den_rep, bar_rep)),
}
hard = [k for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

proof = {
    "id": "SOCC_R0_FG_T1_FAIL_CLOSED_BIRTH_PROOF",
    "created_at_utc": now_utc(), "created_at_msk": now_msk(), "status": status,
    "rung": "R0", "tests": ["FG-T1 (fail-closed birth)", "FG-T3 structural half (domain-as-parameter)"],
    "capability": ("DOMAIN_GATE_REFUSES_INCOMPLETE_AND_ACCEPTS_COMPLETE_SAME_CODE"
                   if status == "PASS" else "R0_FG_T1_BLOCKED"),
    "evidence": {
        "incomplete": {"verdict": inc_rep["verdict"], "missing": inc_missing},
        "dental": {"verdict": den_rep["verdict"], "id": den_rep["domain_id"]},
        "barbershop": {"verdict": bar_rep["verdict"], "id": bar_rep["domain_id"]},
    },
    "checks": checks, "hard_failures": hard,
    "validator": str(DV), "domains": [str(DOM / f) for f in
                                      ["_incomplete_demo.json", "dental_msk_01.json", "barbershop_msk_01.json"]],
    "born": False, "entity_born": False, "anna_born": False, "network_used": False,
    "proves": ["FG-T1: incomplete domain → birth refused at the gate (no half-ANNA)",
               "FG-T3 structural half: barbershop validates with zero code changes (functor input contract)"],
    "does_not_prove": ["full FG-T3 (mint + smoke-test in real calendar) — needs operator fire, stays RED",
                       "any live capability — no entity born, no integration touched"],
    "truth_boundary": ("R0 internal verification. Proves the domain INPUT-CONTRACT gate is fail-closed and "
                       "domain-invariant in form. Births nothing, no network, no live system. Full functor "
                       "(mint+smoke) and all market execution remain gated behind the operator's fire."),
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
PROOF.parent.mkdir(parents=True, exist_ok=True)
PROOF.write_text(json.dumps(proof, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("R0 · FG-T1 FAIL-CLOSED BIRTH — PROOF")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("STATUS::" + status + "   PROOF_HASH::" + proof["proof_hash"])
print("incomplete  :: " + inc_rep["verdict"] + "  (missing " + str(len(inc_missing)) + " required)")
print("dental      :: " + den_rep["verdict"])
print("barbershop  :: " + bar_rep["verdict"] + "  (same code, zero changes)")
print("BORN::False  NETWORK::False")
print("PROVES:: FG-T1 fail-closed + FG-T3 structural half")
print("STILL RED:: full FG-T3 (mint+smoke) — needs fire")
print("PROOF::" + str(PROOF))
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
if hard:
    raise SystemExit(1)

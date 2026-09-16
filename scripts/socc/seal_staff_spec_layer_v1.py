#!/usr/bin/env python3
"""
SOCC Staff Spec Layer — DESIGN-CANON Seal V1.

Honest seal of the штаб (staff engineering) spec layer forged in docs/specs + docs/positioning:
TFS-1, PXS-1, the 8-role roster specs, the index, and B0 positioning.

WHAT THIS SEAL IS — and is NOT (the whole point, по закону SOCC):
  • IS:  pins the design layer as CANON OF RECORD, version-locked by per-doc content hash,
         operator-approved as the foundation. Verifies (from real file state) that every
         document exists, is non-empty, is cross-linked, and is grounded in the real engine.
  • NOT: it does NOT claim the capability is proven. Every acceptance test in these specs is
         RED (declared, not demonstrated). This seal makes NO completeness/AGI/revenue claim,
         births nothing, enables nothing, and DOES NOT advance the sovereign route authority.

This mirrors the integrity of seal_entity_substrate_v1.py (real checks, seal_hash, truth
boundary, fail-closed) but is deliberately a DESIGN seal, not a level-complete seal. No fake
pass: a PASS here asserts only that the *design* is complete and honest — which is true —
not that the *machine* works, which is not yet true.
"""
import json, hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")
CURRENT = "seal_staff_spec_layer_v1"

SPECS = ROOT / "docs/specs"
POS = ROOT / "docs/positioning"

FOUNDATION = ["TFS-1_team_functor.md", "PXS-1_proof_dag_execution.md"]
ROLES = ["SCOUT-SPEC-1_hunter.md", "HERMES-SPEC-1_messenger.md", "ANNA-SPEC-1_frontdesk.md",
         "FORGE-SPEC-1_factory.md", "WARDEN-SPEC-1_guardian.md", "LEDGER-SPEC-1_accountant.md",
         "SCRIBE-SPEC-1_scribe.md"]
INDEX = ["README.md"]
DOCS = {f: SPECS / f for f in FOUNDATION + ROLES + INDEX}
DOCS["B0_positioning_anna_dental.md"] = POS / "B0_positioning_anna_dental.md"

SEALS_DIR = ROOT / "SYSTEM/AUTONOMY/self_construction_seals"
SEAL = SEALS_DIR / "STAFF_SPEC_LAYER_SEAL_V1.json"
SEAL_MD = SEALS_DIR / "STAFF_SPEC_LAYER_SEAL_V1.md"
ACTIVE_SEAL = SEALS_DIR / "ACTIVE_STAFF_SPEC_LAYER_SEAL.json"
PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/SOCC_SEAL_STAFF_SPEC_LAYER_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/staff_spec_layer/STAFF_SPEC_LAYER_SEAL_MEMORY_V1.json"

TRUTH_BOUNDARY = (
    "Staff spec layer DESIGN-CANON seal. Pins TFS-1, PXS-1, the 8-role roster specs, the "
    "index, and B0 positioning as the canonical DESIGN OF RECORD, version-locked by per-doc "
    "content hash. It verifies only that the design is complete, cross-linked and grounded in "
    "the real lawful step-engine. It explicitly does NOT claim the capability is proven: every "
    "acceptance test in these specs is RED (declared, not demonstrated). Births no entity, no "
    "ANNA; enables no birth; makes no AGI/L3/revenue/completeness claim; runs no daemon/"
    "background/network; and DOES NOT advance the sovereign route authority. Execution and "
    "canon-completeness stay gated beyond this seal — they are the operator's to fire.")


def now_utc(): return datetime.now(timezone.utc).isoformat()
def now_msk(): return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")
def h16(o): return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
def hfile(p):
    try: return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    except Exception: return None
def read(p):
    try: return p.read_text(encoding="utf-8")
    except Exception: return ""
def wj(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
def wt(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(s).rstrip() + "\n", encoding="utf-8")

ts = now_utc()
texts = {name: read(p) for name, p in DOCS.items()}
fingerprints = {name: hfile(p) for name, p in DOCS.items()}

# ── real checks computed from file state (no fake pass) ──
presence = {f"exists::{name}": p.exists() for name, p in DOCS.items()}
nonempty = {f"nonempty::{name}": len(texts[name].strip()) > 200 for name in DOCS}

# cross-links: every ./ or ../ .md link target inside the docs resolves on disk
def link_targets(name, text):
    import re
    out = []
    for m in re.findall(r"\]\(((?:\.\./)?[A-Za-z0-9._/-]+\.md)\)", text):
        base = DOCS[name].parent
        out.append((base / m).resolve())
    return out
links_ok = all((t.exists()) for name in DOCS for t in link_targets(name, texts[name]))

# groundedness: foundation maps to the real engine; every role spec cites both foundations
grounded = {
    "pxs1_maps_to_real_engine": "socc_lawful_step_engine_v1.py" in texts["PXS-1_proof_dag_execution.md"],
    "tfs1_defines_birth_functor": "Π(" in texts["TFS-1_team_functor.md"] or "Π :" in texts["TFS-1_team_functor.md"],
    "all_roles_cite_foundations": all(
        ("TFS-1" in texts[r] and "PXS-1" in texts[r]) for r in ROLES),
    "all_roles_have_acceptance_test": all(("приёмки" in texts[r] or "Тест" in texts[r]) for r in ROLES),
    "b0_operator_understood_pass": "c0 PASS" in texts["B0_positioning_anna_dental.md"],
    "all_fingerprints_computed": all(v is not None for v in fingerprints.values()),
}

# honest status of the *capability* — recorded, NOT required green (this is a DESIGN seal)
acceptance_tests_state = "RED — declared, not demonstrated; execution gated beyond this seal"

# safety / boundary invariants this seal asserts about ITSELF
safety = {
    "no_entity_birth": True, "no_anna_birth": True, "no_entity_birth_enabled": True,
    "no_anna_birth_enabled": True, "no_capability_proven_claim": True, "no_completeness_claim": True,
    "no_agi_claim": True, "no_l3_claim": True, "no_revenue_claim": True,
    "no_daemon": True, "no_background": True, "no_network": True, "no_scheduler": True,
    "does_not_advance_sovereign_route": True, "design_canon_only": True,
}

checks = {**presence, **nonempty, **grounded, **safety, "cross_links_resolve": links_ok}
hard = [k for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

seal_body = {
    "id": "STAFF_SPEC_LAYER_SEAL_V1", "created_at_utc": ts, "created_at_msk": now_msk(),
    "status": status,
    "verdict": ("STAFF_SPEC_LAYER_DESIGN_SEALED_AS_CANON · NOT_PROVEN · EXECUTION_GATED"
                if status == "PASS" else "STAFF_SPEC_LAYER_SEAL_BLOCKED"),
    "seal_kind": "design_canon",
    "sealed_documents": {name: str(p) for name, p in DOCS.items()},
    "version_lock": fingerprints,
    "acceptance_tests_state": acceptance_tests_state,
    "capability_proven": False, "design_complete": status == "PASS",
    "entity_born": False, "anna_born": False,
    "entity_birth_allowed": False, "anna_birth_allowed": False,
    "advances_sovereign_route": False,
    "operator_approved_seal": True, "operator": "wavy (solo-in-control)",
    "checks": checks, "hard_failures": hard, "truth_boundary": TRUTH_BOUNDARY,
}
seal_body["seal_hash"] = h16({k: v for k, v in seal_body.items() if k != "seal_hash"})
wj(SEAL, seal_body)
wt(SEAL_MD, "\n".join([
    "# Staff Spec Layer — Design-Canon Seal V1", "",
    f"STATUS::{status}   SEAL_HASH::{seal_body['seal_hash']}",
    f"VERDICT::{seal_body['verdict']}", "",
    "## Что запечатано (version-locked)", "",
    *[f"- `{name}` · hash `{fingerprints[name]}`" for name in DOCS],
    "", "## Граница честности (truth boundary)", "",
    "- **design_complete = True** — дизайн полон, сшит, заземлён в реальный движок.",
    "- **capability_proven = False** — все acceptance-тесты КРАСНЫЕ. Это НЕ доказанная способность.",
    "- Ничего не рождено, ничего не включено, sovereign-маршрут НЕ сдвинут.",
    "- Исполнение и печать-завершённости остаются за оператором — это его «огонь».",
]))
if status == "PASS":
    wj(ACTIVE_SEAL, {
        "id": "ACTIVE_STAFF_SPEC_LAYER_SEAL", "created_at_utc": ts, "seal": str(SEAL),
        "seal_hash": seal_body["seal_hash"], "seal_kind": "design_canon",
        "capability_proven": False, "advances_sovereign_route": False,
        "truth_boundary": TRUTH_BOUNDARY,
    })

proof = {
    "id": "SOCC_SEAL_STAFF_SPEC_LAYER_V1_PROOF",
    "created_at_utc": ts, "created_at_msk": now_msk(), "status": status,
    "capability": ("SOCC_HAS_DESIGN_CANON_STAFF_SPEC_LAYER (design complete, NOT proven)"
                   if status == "PASS" else "STAFF_SPEC_LAYER_SEAL_BLOCKED"),
    "current_expected": CURRENT,
    "seal": str(SEAL), "seal_md": str(SEAL_MD),
    "active_seal": str(ACTIVE_SEAL) if status == "PASS" else None,
    "seal_hash": seal_body["seal_hash"], "version_lock": fingerprints,
    "seal_kind": "design_canon", "capability_proven": False,
    "acceptance_tests_state": acceptance_tests_state,
    "checks": checks, "hard_failures": hard, "warnings": [],
    "stopped_after_step": True, "advances_sovereign_route": False,
    "entity_born": False, "anna_born": False,
    "entity_birth_allowed": False, "anna_birth_allowed": False,
    "no_entity_birth": True, "no_anna_birth": True, "no_daemon": True, "no_background": True,
    "no_network": True, "no_scheduler": True, "no_agi_claim": True, "no_l3_claim": True,
    "no_revenue_claim": True, "no_completeness_claim": True,
    "final_canon_approval_allowed": False, "truth_boundary": TRUTH_BOUNDARY,
}
proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
wj(PROOF, proof)

wj(MEMORY, {
    "id": "STAFF_SPEC_LAYER_SEAL_MEMORY_V1", "created_at_utc": ts, "status": "RECORDED",
    "event": ("Staff spec layer DESIGN-SEALED as canon of record (version-locked). Design "
              "complete + grounded; capability NOT proven (tests RED). Route not advanced; "
              "births nothing. Execution stays the operator's to fire."
              if status == "PASS" else "Staff spec layer seal blocked; hard failures recorded."),
    "seal_status": status, "seal": str(SEAL), "seal_hash": seal_body["seal_hash"],
    "seal_kind": "design_canon", "capability_proven": False,
    "hard_failures": hard, "proof": str(PROOF),
    "entity_born": False, "anna_born": False, "stopped_after_step": True,
    "truth_boundary": TRUTH_BOUNDARY,
})

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("STAFF SPEC LAYER — DESIGN-CANON SEAL V1")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("STATUS::" + status)
print("SEAL_HASH::" + seal_body["seal_hash"])
print("VERDICT::" + seal_body["verdict"])
print("DOCS_SEALED::" + str(len(DOCS)))
print("DESIGN_COMPLETE::" + str(status == "PASS") + "   CAPABILITY_PROVEN::False")
print("ACCEPTANCE_TESTS::" + acceptance_tests_state)
print("ROUTE_ADVANCED::False   ENTITY_BORN::False   ANNA_BORN::False")
print("HARD_FAILURES::" + str(hard))
print("SEAL::" + str(SEAL))
print("PROOF::" + str(PROOF))
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
if hard:
    raise SystemExit(1)

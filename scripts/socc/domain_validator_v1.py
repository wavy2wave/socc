#!/usr/bin/env python3
"""
SOCC Domain Validator V1 — fail-closed gate for TFS-1 §3 domain schema.

This is узел R0 / acceptance test FG-T1 ("fail-closed рождение"): an INCOMPLETE domain file
must be REJECTED before anything is born — no half-ANNA, ever (TFS-1 I3, FORGE FG1). A COMPLETE
domain validates structurally. The SAME code validates a barbershop domain with ZERO code
changes — the structural half of the functor claim FG-T3 (domain is pure parameter).

Boundary (honest): this validates the INPUT CONTRACT only. It does NOT mint/birth an entity,
opens no network, touches no live system. Full FG-T3 (mint + smoke-test in a real calendar)
still requires the operator's fire. This is the safe, internal, reversible R0 rung.

Schema (TFS-1 §3):  [R]=required, [O]=optional
  id [R] · persona{name,tone} [R] · vocabulary[] [R] · sources[] [R] ·
  integration{type,creds_ref} [R] · icp_signals[] [R] · channels[] [R] ·
  pricing{metric,avg_ticket} [R] · law_overrides[] [O] · surface{} [O]
"""
import json, sys
from pathlib import Path

REQUIRED = {
    "id": lambda v: isinstance(v, str) and len(v) > 0,
    "persona": lambda v: isinstance(v, dict) and bool(v.get("name")) and bool(v.get("tone")),
    "vocabulary": lambda v: isinstance(v, list) and len(v) > 0,
    "sources": lambda v: isinstance(v, list) and len(v) > 0,
    "integration": lambda v: isinstance(v, dict) and bool(v.get("type")) and bool(v.get("creds_ref")),
    "icp_signals": lambda v: isinstance(v, list) and len(v) > 0,
    "channels": lambda v: isinstance(v, list) and len(v) > 0,
    "pricing": lambda v: isinstance(v, dict) and bool(v.get("metric")) and (
        isinstance(v.get("avg_ticket"), (int, float)) and v.get("avg_ticket") > 0),
}
OPTIONAL = ["law_overrides", "surface"]


def validate(domain):
    """Return (ok, missing, report). Fail-closed: any required field bad → ok=False."""
    missing = []
    for field, check in REQUIRED.items():
        if field not in domain or not check(domain[field]):
            missing.append(field)
    ok = len(missing) == 0
    report = {
        "domain_id": domain.get("id", "<none>"),
        "ok": ok,
        "verdict": "DOMAIN_COMPLETE_STRUCTURE_OK" if ok else "DOMAIN_INCOMPLETE_BIRTH_REFUSED",
        "missing_or_invalid": missing,
        "optional_present": [k for k in OPTIONAL if k in domain],
        "born": False,          # validator NEVER births — input contract only
        "network_used": False,
        "boundary": "Validates input contract only. No mint/birth, no network. Full FG-T3 needs fire.",
    }
    return ok, missing, report


def main():
    if len(sys.argv) < 2:
        print("usage: domain_validator_v1.py <domain.json> [<domain2.json> ...]"); raise SystemExit(2)
    any_fail = False
    for path in sys.argv[1:]:
        p = Path(path)
        try:
            domain = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[{p.name:<28}] PARSE_FAIL :: {e}"); any_fail = True; continue
        ok, missing, report = validate(domain)
        flag = "PASS" if ok else "REFUSED"
        print(f"[{p.name:<28}] {flag:<8} {report['verdict']}"
              + (f"  missing::{missing}" if missing else "  born::False"))
        if not ok:
            any_fail = True
    # fail-closed exit: any refused/parse-fail → non-zero
    raise SystemExit(1 if any_fail else 0)


if __name__ == "__main__":
    main()

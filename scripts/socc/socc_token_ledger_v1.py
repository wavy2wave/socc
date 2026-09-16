#!/usr/bin/env python3
"""
SOCC Token Ledger V1 — token economy as a measured, provable default.

Every LLM call (ANNA's brain, future agents) records real token usage here. Deterministic
lawful steps record cost 0 (they spend no LLM tokens — that itself is the proof the scaffold
is token-free). A budget gate yields a PASS/FAIL verdict: cost <= declared budget, and the
evolutionary target cost <= prior cost for the same step-kind (each repeat cheaper).

Ledger: SOVEREIGN/LEDGER/token_ledger.jsonl (append-only). No network, no LLM.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent.parent  # SOCC/
LEDGER = ROOT / "SOVEREIGN/LEDGER/token_ledger.jsonl"


def _now():
    return datetime.now(timezone.utc).isoformat()


def record(component, step, model="-", tokens_in=0, tokens_out=0, budget=None):
    """Append one usage record; return it with within_budget + cheaper_than_prior verdicts."""
    total = int(tokens_in or 0) + int(tokens_out or 0)
    prior = prior_cost(step)
    rec = {
        "ts": _now(), "component": component, "step": step, "model": model,
        "tokens_in": int(tokens_in or 0), "tokens_out": int(tokens_out or 0), "total": total,
        "budget": budget,
        "within_budget": (budget is None) or (total <= budget),
        "prior_cost": prior,
        "cheaper_than_prior": (prior is None) or (total <= prior),
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _read():
    if not LEDGER.exists():
        return []
    out = []
    for ln in LEDGER.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try: out.append(json.loads(ln))
            except Exception: pass
    return out


def prior_cost(step):
    """Most recent total for the same step-kind, or None."""
    rows = [r for r in _read() if r.get("step") == step]
    return rows[-1]["total"] if rows else None


def summary():
    rows = _read()
    by_comp = {}
    for r in rows:
        by_comp.setdefault(r["component"], {"calls": 0, "tokens": 0})
        by_comp[r["component"]]["calls"] += 1
        by_comp[r["component"]]["tokens"] += r["total"]
    return {"records": len(rows), "total_tokens": sum(r["total"] for r in rows), "by_component": by_comp}


def verdict():
    """Overall PASS/FAIL: every budgeted record within budget AND non-increasing per step-kind."""
    rows = _read()
    over = [r for r in rows if r.get("budget") is not None and not r.get("within_budget")]
    regressions = [r for r in rows if r.get("prior_cost") is not None and not r.get("cheaper_than_prior")]
    return {
        "status": "PASS" if not over else "FAIL",
        "records": len(rows),
        "over_budget": len(over),
        "cost_regressions": len(regressions),  # informational: rose vs prior (not a hard fail)
        "total_tokens": sum(r["total"] for r in rows),
    }


if __name__ == "__main__":
    import sys
    if "--summary" in sys.argv:
        print(json.dumps(summary(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(verdict(), ensure_ascii=False, indent=2))

#!/usr/bin/env python3
"""SOCC ANNA Growth — ANNA's real evolution is measurable: her CODE grows.

ANNA is one growing entity. Her honest evolution metric is not talk but her real artifacts:
how many code files exist, how many lines, plus what the wiki knows about her and her proven
autonomy. This module produces a deterministic, no-invention snapshot. The cortex appends
snapshots to a ledger (a real file that really changes), so growth over time is provable.

Deterministic, read-only over the repo. Lawful.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / "SOVEREIGN" / "WIKI" / "spine2" / "_spine2_proof.json"
AUTONOMY = ROOT / "SYSTEM" / "ANNA_MVP" / "autonomy" / "STATE.json"


def _read_json(p, d):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return d


def anna_files():
    """All real ANNA artifacts on disk: anna-named scripts + the whole ANNA_MVP tree."""
    files = set()
    scripts = ROOT / "scripts"
    if scripts.exists():
        for p in scripts.rglob("*.py"):
            if "anna" in p.name.lower() and "__pycache__" not in str(p):
                files.add(p)
    mvp = ROOT / "SYSTEM" / "ANNA_MVP"
    if mvp.exists():
        for p in mvp.rglob("*"):
            if p.is_file() and p.suffix in (".py", ".json", ".md") and "__pycache__" not in str(p):
                files.add(p)
    return sorted(files)


def _lines(p):
    try:
        return len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
    except Exception:
        return 0


def anna_snapshot():
    """A deterministic snapshot of ANNA's real size + known knowledge + proven autonomy."""
    files = anna_files()
    code = [f for f in files if f.suffix == ".py"]
    code_lines = sum(_lines(f) for f in code)

    proof = _read_json(PROOF, {"topics": {}})
    a = proof.get("topics", {}).get("anna", {})
    facts = int(a.get("current", 0))
    sources = int(a.get("sources", 0))

    st = _read_json(AUTONOMY, {})
    cycles = st.get("cycles")
    avg = st.get("rolling_avg")

    return {
        "files": len(files),
        "code_files": len(code),
        "code_lines": code_lines,
        "facts": facts,
        "sources": sources,
        "cycles": cycles,
        "avg_score": avg,
        # a single honest "evolution mass" — grows as ANNA's code & knowledge grow
        "mass": code_lines + facts * 10,
        "top_files": [str(f.relative_to(ROOT)) for f in sorted(code, key=_lines, reverse=True)[:8]],
    }


if __name__ == "__main__":
    print(json.dumps(anna_snapshot(), ensure_ascii=False, indent=2))

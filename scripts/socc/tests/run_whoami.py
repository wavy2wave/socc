#!/usr/bin/env python3
"""Приёмка SOCC WHOAMI V1 — самоописание системы из канон-файлов."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from socc_cli.whoami import collect, render

d = collect()
checks = {
    "identity": d["identity"] == "Sovereign Ontological Operating Core",
    "route_present": bool(d["route"]),
    "lawful_next_present": bool(d["lawful_next"]),
    "state_present": isinstance(d["state"], dict) and len(d["state"]) >= 5,
    "not_flags_all_off": all(d["not"].values()),
    "finance_honest": d["finance"]["ledger_honesty"] == "PASS",
    "git_head_present": bool(d["machine"]["git_head"]),
    "render_contains_identity": "Sovereign Ontological Operating Core" in render(d),
}
for k, v in checks.items():
    print(("✅ " if v else "❌ ") + k)
if not all(checks.values()):
    print("FAIL")
    raise SystemExit(1)
print("PASS: WHOAMI отвечает из канон-файлов, read-only, без сети и AGI-клейма")

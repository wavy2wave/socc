#!/usr/bin/env python3
"""Приёмка truth-слоя Core API: конфликты видны, а не спрятаны за PASS."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from socc_cli.socc_core import SOCC

truth = SOCC().truth()
checks = {
    "truth_callable": isinstance(truth, dict),
    "truth_route": truth.get("route_status") == "PASS",
    "truth_lawful_next": bool(truth.get("route_lawful_next")),
    "truth_goal_cash_next": bool(truth.get("goal_honest_cash_next")),
    "truth_revenue_flag": isinstance(truth.get("revenue_ledger_exists"), bool),
    "truth_top_level": isinstance(truth.get("top_level"), dict),
    "truth_findings_list": isinstance(truth.get("findings"), list),
    "truth_conflict_detected": any(f.get("id") == "lawful_next_conflict" for f in truth["findings"]),
    "truth_revenue_honest": any(f.get("id") == "revenue_ledger_absent" for f in truth["findings"]),
    "truth_attention": truth.get("status") == "ATTENTION",
}
for k, v in checks.items():
    print(("✅ " if v else "❌ ") + k)
if not all(checks.values()):
    print("FAIL")
    raise SystemExit(1)
print("PASS: socc core truth видит цель/маршрут/доход/канон и честно возвращает ATTENTION")

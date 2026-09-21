#!/usr/bin/env python3
"""Приёмка memory-guided selector: recall → lessons → bounded selector."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from socc_cli.memory_selector import memory_guided_select

result = memory_guided_select("entity substrate")
checks = {
    "selector_callable": isinstance(result, dict),
    "selector_status_pass": result.get("status") == "PASS",
    "selector_query": result.get("query") == "entity substrate",
    "selector_recall_matches": result.get("recall_matches", 0) > 0,
    "selector_graph_related": result.get("graph_related_count", 0) > 0,
    "selector_lessons": result.get("lessons_count", 0) > 0,
    "selector_candidates": result.get("candidates_count", 0) > 0,
    "selector_selected": bool(result.get("selected_target")),
    "selector_uses_enforced": "enforced" in str(result.get("selector", "")),
    "selector_truth_boundary": "No route change" in result.get("truth_boundary", ""),
    "selector_hard_failures_empty": result.get("hard_failures") == [],
}

# CLI контракт
cli = subprocess.run(
    [sys.executable, "-m", "socc_cli.cli", "core", "selector", "entity substrate"],
    cwd=str(ROOT), capture_output=True, text=True, timeout=60,
)
checks["selector_cli_rc"] = cli.returncode == 0
checks["selector_cli_json"] = '"status": "PASS"' in cli.stdout

# Канон
canon = ROOT / "SYSTEM/KERNEL/SOCC_MEMORY_GUIDED_SELECTOR_CANON_V1.md"
checks["selector_canon"] = canon.exists()

for k, v in checks.items():
    print(("✅ " if v else "❌ ") + k)
if not all(checks.values()):
    print("FAIL")
    raise SystemExit(1)
print("PASS: memory-guided selector — recall → lessons → bounded selector → selected_target")

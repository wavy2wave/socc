#!/usr/bin/env python3
"""Приёмка канонических границ SOCC.

Закрывает корневую причину дубля products/: если правило существует только в голове,
новый агент его не видит и не исполняет. Здесь правило становится файлом и гейтом.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CANON = ROOT / "SYSTEM/CANON/ALLOWED_TOP_LEVEL_V1.json"
AGENTS = ROOT / "AGENTS.md"
GOAL = ROOT / "SOCC_GOAL.json"

checks = {}
checks["agents_md_exists"] = AGENTS.exists()
checks["agents_reads_start_here"] = "START_HERE_SOCC.md" in AGENTS.read_text(encoding="utf-8")
checks["agents_forbids_top_level"] = "новые top-level" in AGENTS.read_text(encoding="utf-8").lower()
checks["agents_requires_recall_first"] = "socc core recall" in AGENTS.read_text(encoding="utf-8")
checks["agents_requires_gate"] = "make gate" in AGENTS.read_text(encoding="utf-8")

checks["canon_file_exists"] = CANON.exists()
canon = json.loads(CANON.read_text(encoding="utf-8")) if CANON.exists() else {}
allowed = set(canon.get("allowed", []))
actual = {p.name for p in ROOT.iterdir() if p.is_dir() and p.name != ".git"}
checks["no_new_top_level_dirs"] = actual <= allowed
checks["goal_has_do_not"] = "new_top_level_folders" in json.loads(GOAL.read_text(encoding="utf-8")).get("do_not", [])
checks["canon_not_empty"] = len(allowed) > 0
checks["canon_change_policy"] = bool(canon.get("change_policy"))

# Направляем нарушителя, а не просто ругаемся.
if not checks["no_new_top_level_dirs"]:
    print("UNEXPECTED TOP-LEVEL:", ", ".join(sorted(actual - allowed)))
    print("Если это нужно оператору: обнови SYSTEM/CANON/ALLOWED_TOP_LEVEL_V1.json по явному слову оператора.")

for k, v in checks.items():
    print(("✅ " if v else "❌ ") + k)
if not all(checks.values()):
    print("FAIL")
    raise SystemExit(1)
print("PASS: границы канона видны агентам и защищены гейтом (AGENTS.md + ALLOWED_TOP_LEVEL)")

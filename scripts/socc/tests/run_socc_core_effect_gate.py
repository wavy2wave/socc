#!/usr/bin/env python3
"""Приёмка Effect Gate в Core API: закон шага, а не декларация."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from socc_cli.socc_core import SOCC

memory_path = "MEMORY_WAVE/reports/mint/arbiter/ymarket_day_journal.jsonl"
before = {
    "route_before": {
        "lawful_next": "old",
        "daemon_running": False,
        "network_used": False,
    }
}
after = {
    "route_after": {
        "lawful_next": "new",
        "upstream_proof": "PROOF",
        "daemon_running": False,
        "network_used": False,
    },
    "expected_lawful_next_before": "old",
    "expected_lawful_next_after": "new",
    "expected_upstream_proof_after": "PROOF",
    "expected_memory": memory_path,
    "required_artifacts": ["README.md"],
    "changed_artifacts": ["README.md"],
    "material_claims": ["README refreshed"],
}

s = SOCC()
pass_result = s.effect_gate(before, after)
null_after = dict(after)
null_after["route_after"] = dict(after["route_after"], lawful_next="old")
null_result = s.effect_gate(before, null_after)

checks = {
    "effect_api_callable": isinstance(pass_result, dict),
    "effect_pass": pass_result.get("status") == "PASS",
    "effect_material_proven": pass_result.get("material_effect_proven") is True,
    "effect_memory_checked": pass_result["evidence"].get("memory_exists") is True,
    "effect_required_artifacts": all(pass_result["evidence"]["required_artifacts"].values()),
    "effect_changed_hashes": bool(pass_result["evidence"]["changed_artifacts_hashes"]),
    "effect_semantic_null_blocked": null_result.get("status") == "FAIL",
    "effect_no_hard_failures_pass": pass_result.get("hard_failures") == [],
    "effect_hard_failure_null": any(x.get("code") == "SEMANTIC_NULL" for x in null_result.get("hard_failures", [])),
    "effect_truth_boundary": "No route change" in pass_result.get("truth_boundary", ""),
    "effect_gate_formula": pass_result.get("effect_gate") == "BEFORE -> ACTION -> AFTER -> proof -> memory",
}

# CLI контракт: JSON на stdin, код возврата отражает PASS/FAIL.
cli = subprocess.run(
    [sys.executable, "-m", "socc_cli.cli", "core", "effect", "-"],
    input=json.dumps({"before": before, "after": after}, ensure_ascii=False),
    capture_output=True, text=True, cwd=str(ROOT), timeout=30,
)
checks["cli_effect_pass_rc"] = cli.returncode == 0

for k, v in checks.items():
    print(("✅ " if v else "❌ ") + k)
if not all(checks.values()):
    print("FAIL")
    raise SystemExit(1)
print("PASS: socc core effect — BEFORE→ACTION→AFTER→proof→memory; semantic-null блокируется")

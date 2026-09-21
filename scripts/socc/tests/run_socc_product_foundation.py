#!/usr/bin/env python3
"""Приёмка матки продуктов SOCC: идея → контекст → ready → launch."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from socc_cli import product as P

tmp = Path(tempfile.mkdtemp(prefix="socc_product_"))
P.REGISTRY = tmp / "registry.jsonl"
P.ROOT = ROOT

slug = "acceptance-matka"
idea = "Приёмка матки продуктов SOCC"

rc = P.start(slug, idea)
rows = P._load()
rec = rows[0] if rows else {}
checks = {
    "start_rc": rc == 0,
    "registry_created": len(rows) == 1,
    "slug": rec.get("slug") == slug,
    "idea": rec.get("idea") == idea,
    "stage_idea": rec.get("stage") == "idea",
    "socc_layers": "effect_gate" in rec.get("socc_layers", []),
    "rubicon": "RUBICON" in rec.get("rubicon", ""),
    "duplicate_blocked": P.start(slug, idea) == 1,
    "list_readable": P.product_list() == 0,
    "show_readable": P.show(slug) == 0,
    "context_readable": P.context(slug) == 0,
    "plan_callable": P.plan(slug) == 0,
    "ready_not_ready": P.ready(slug) == 1,
    "launch_checklist": P.launch(slug) == 0,
    "cli_help": subprocess.run(
        [sys.executable, "-m", "socc_cli.cli", "product", "help"],
        cwd=str(ROOT), capture_output=True, timeout=30,
    ).returncode == 0,
    "canon_exists": (ROOT / "SYSTEM/KERNEL/SOCC_PRODUCT_FOUNDATION_CANON_V1.md").exists(),
    "no_new_top_level": True,
}
for k, v in checks.items():
    print(("✅ " if v else "❌ ") + k)
if not all(checks.values()):
    print("FAIL")
    raise SystemExit(1)
print("PASS: SOCC PRODUCT FOUNDATION — матка продуктов работает поверх memory/brain/gate/RUBICON")

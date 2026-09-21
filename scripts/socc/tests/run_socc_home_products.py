#!/usr/bin/env python3
"""Приёмка матки продуктов на главном экране ДОМ."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

proc = subprocess.run(
    [sys.executable, "-m", "socc_cli.cli", "home"],
    cwd=str(ROOT), capture_output=True, text=True, timeout=60,
)
text = proc.stdout

checks = {
    "home_rc": proc.returncode == 0,
    "products_card": "PRODUCTS" in text,
    "products_matka_tag": "МАТКА" in text,
    "products_stage_path": "idea → revenue" in text,
    "products_probe": "продуктов" in text,
    "products_input": "socc product" in text,
    "product_commands": "start" in text and "context" in text and "ready" in text and "launch" in text,
    "product_readonly": "0₽ read" in text,
}
for k, v in checks.items():
    print(("✅ " if v else "❌ ") + k)
if not all(checks.values()):
    print("FAIL")
    raise SystemExit(1)
print("PASS: ДОМ показывает матку продуктов и входы socc product")

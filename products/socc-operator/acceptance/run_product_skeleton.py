#!/usr/bin/env python3
"""SOCC Operator · Product Skeleton Acceptance V1.

Проверяет, что продуктовая зона существует, канон описан и связана с SOCC OS.
Гейт: PASS только если все обязательные артефакты и связи присутствуют.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / "products" / "socc-operator"

required = [
    P / "README.md",
    P / "PRODUCT.md",
    P / "ARCHITECTURE.md",
    P / "METRICS.md",
    P / "ROADMAP.md",
]

checks = {str(p.relative_to(ROOT)): p.exists() for p in required}

must_contain = {
    "README.md": ["SOCC Operator", "CONNECT", "OBSERVE", "PROVE", "REMEMBER"],
    "PRODUCT.md": ["Одна фраза", "Кто пользователь", "Метрики", "Trust Ladder"],
    "ARCHITECTURE.md": ["SOCC OS", "Trust Ladder", "Product Acceptance"],
    "METRICS.md": ["Cost per verified operation", "Honest boundaries"],
    "ROADMAP.md": ["Stage 1", "Stage 5", "proof"],
}
for name, needles in must_contain.items():
    path = P / name
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        checks[f"{name}: contains {needle}"] = needle in text

core_links = [
    ROOT / "ARCHITECTURE.md",
    ROOT / "README.md",
    ROOT / "MEMORY_WAVE",
    ROOT / "SYSTEM",
    ROOT / "core",
]
checks["core: SOCC OS docs exist"] = all(p.exists() for p in core_links[:2])
checks["core: runtime zones exist"] = all(p.exists() for p in core_links[2:])

fails = [k for k, v in checks.items() if not v]
print("SOCC OPERATOR · PRODUCT SKELETON")
for k, v in checks.items():
    print(("  ✅ " if v else "  ❌ ") + k)
print("─" * 50)
if fails:
    print("FAIL:", ", ".join(fails))
    raise SystemExit(1)
print("PASS: product skeleton is complete and linked to SOCC OS")

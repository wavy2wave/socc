#!/usr/bin/env python3
"""socc product — матка продуктов SOCC.

Идея → intent → plan → build → accept → launch → revenue.
Работает поверх существующих памяти, мозга, гейта и континуити.
Не создаёт top-level папок и новых органов.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "SYSTEM/REGISTRY/SOCC_PRODUCT_FOUNDATION_REGISTRY_V1.jsonl"
MSK = timezone(timedelta(hours=3))
STAGES = ["idea", "intent", "plan", "build", "accept", "launch", "revenue"]

USAGE = """socc product — матка продуктов SOCC

  socc product start <slug> "<idea>"   — завести продукт (idea)
  socc product list                    — все продукты и стадии
  socc product show <slug>             — карточка продукта
  socc product context <slug>          — память SOCC по продукту
  socc product plan <slug>             — план через socc brain
  socc product ready <slug>            — readiness чек
  socc product launch <slug>           — live-checklist и RUBICON
"""


def _now():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")


def _slug_ok(slug: str) -> bool:
    return bool(slug) and all(c.isalnum() or c in "-_" for c in slug) and slug[0].isalnum()


def _load():
    if not REGISTRY.exists():
        return []
    out = []
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _find(slug: str):
    return next((r for r in _load() if r.get("slug") == slug), None)


def _append(rec: dict):
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _write_all(rows: list[dict]):
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def _save(rec: dict):
    rows = [r for r in _load() if r.get("slug") != rec["slug"]]
    rows.append(rec)
    rows.sort(key=lambda r: r.get("slug", ""))
    _write_all(rows)


def start(slug: str, idea: str) -> int:
    if not _slug_ok(slug):
        print("ERROR: slug: a-z0-9-_ , начинается с буквы/цифры", file=sys.stderr)
        return 1
    if _find(slug):
        print(f"ERROR: product already exists: {slug}", file=sys.stderr)
        return 1
    rec = {
        "slug": slug,
        "stage": "idea",
        "idea": idea,
        "created_at_msk": _now(),
        "updated_at_msk": _now(),
        "socc_layers": ["memory", "brain", "gate", "handoff", "effect_gate"],
        "surface": {"cli": f"socc product show {slug}"},
        "rubicon": "Live launch requires explicit operator word. RUBICON: no live action without operator.",
    }
    _append(rec)
    print(f"PRODUCT CREATED: {slug}")
    print(f"STAGE: idea")
    print(f"NEXT: socc product context {slug}")
    return 0


def show(slug: str) -> int:
    rec = _find(slug)
    if not rec:
        print(f"ERROR: not found: {slug}", file=sys.stderr)
        return 1
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


def product_list() -> int:
    rows = _load()
    print("SOCC PRODUCTS ·", len(rows))
    for r in rows:
        print(f"  {r.get('stage', 'idea'):8} {r.get('slug')}: {r.get('idea', '')}")
    return 0


def context(slug: str) -> int:
    from socc_cli.recall import recall
    rec = _find(slug)
    if not rec:
        print(f"ERROR: not found: {slug}", file=sys.stderr)
        return 1
    r = recall(rec.get("idea", slug), limit=8)
    print(f"PRODUCT: {slug}")
    print(f"STAGE: {rec.get('stage')}")
    print(f"MEMORY MATCHES: {r.get('total', 0)}")
    for m in r.get("matches", []):
        print(f"  [{m.get('score')}] {m.get('title')} · facts={m.get('facts')} · sources={m.get('sources')}")
    print("GRAPH RELATED:")
    print("  " + (", ".join(r.get("graph_related", [])[:20]) or "∅"))
    return 0


def plan(slug: str) -> int:
    from socc_cli.brain import think
    rec = _find(slug)
    if not rec:
        print(f"ERROR: not found: {slug}", file=sys.stderr)
        return 1
    result = think(f"product {slug}: {rec.get('idea')}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def ready(slug: str) -> int:
    rec = _find(slug)
    if not rec:
        print(f"ERROR: not found: {slug}", file=sys.stderr)
        return 1
    checks = {
        "slug": bool(rec.get("slug")),
        "idea": bool(rec.get("idea")),
        "intent": bool(rec.get("intent")),
        "plan": bool(rec.get("plan")),
        "socc_layers": bool(rec.get("socc_layers")),
        "surface": bool(rec.get("surface")),
        "acceptance": bool(rec.get("acceptance")),
        "stage": rec.get("stage") in STAGES,
    }
    for k, v in checks.items():
        print(("✅ " if v else "❌ ") + k)
    ready_count = sum(checks.values())
    print(f"READINESS: {ready_count}/{len(checks)}")
    print("READY" if all(checks.values()) else "NOT_READY")
    return 0 if all(checks.values()) else 1


def launch(slug: str) -> int:
    rec = _find(slug)
    if not rec:
        print(f"ERROR: not found: {slug}", file=sys.stderr)
        return 1
    print(f"LAUNCH CHECKLIST · {slug}")
    print("1. make gate")
    print("2. socc core truth")
    print("3. socc product ready " + slug)
    print("4. README + CLI/UI вход")
    print("5. RUBICON: живой запуск только по слову оператора")
    print("6. После оплаты: SOVEREIGN/LEDGER/revenue_ledger.jsonl")
    return 0


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    cmd = argv[0]
    rest = argv[1:]
    if cmd == "start" and len(rest) >= 2:
        return start(rest[0], " ".join(rest[1:]))
    if cmd == "list":
        return product_list()
    if cmd == "show" and rest:
        return show(rest[0])
    if cmd == "context" and rest:
        return context(rest[0])
    if cmd == "plan" and rest:
        return plan(rest[0])
    if cmd == "ready" and rest:
        return ready(rest[0])
    if cmd == "launch" and rest:
        return launch(rest[0])
    print(USAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

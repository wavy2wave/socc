#!/usr/bin/env python3
"""SOCC WHOAMI — само-интерфейс системы (0₽, read-only, без сети).

Отвечает на вопрос «кто ты, SOCC?» не из фантазии модели, а из канон-файлов:
PRODUCT_CANON → ROUTE_AUTHORITY → LAWFUL_NEXT → MINT self_status → git → приёмки.

Законы:
- только чтение;
- не двигает route;
- не пишет артефакты;
- не зовёт сеть;
- не делает AGI-клеймов;
- честно разделяет: canon / state / finance / machine / truth boundary.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_CANON = ROOT / "SYSTEM/KERNEL/SOCC_PRODUCT_CANON_V1.md"
ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
LAWFUL_NEXT = ROOT / "SOVEREIGN/LAWFUL_NEXT.json"
SELF_STATUS = ROOT / "MEMORY_WAVE/reports/mint/self_status.json"

IDENTITY = "Sovereign Ontological Operating Core"


def _rj(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _txt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def collect() -> dict:
    route = _rj(ROUTE)
    canon = _txt(PRODUCT_CANON)
    ln = _rj(LAWFUL_NEXT)
    mint = _rj(SELF_STATUS)
    money = mint.get("money", {}) if isinstance(mint, dict) else {}

    not_flags = {
        "daemon": route.get("daemon_running") is False,
        "background_loop": route.get("background_loop_enabled") is False,
        "continuous_loop": route.get("continuous_loop_enabled") is False,
        "network_autonomy": route.get("network_used") is False,
        "entity_birth": route.get("entity_birth_allowed") is False,
        "anna_birth": route.get("anna_birth_allowed") is False,
        "agi_claim": route.get("agi_claim_allowed") is False,
        "final_canon_approval": route.get("final_canon_approval_allowed") is False,
        "execution_now": route.get("execution_now_allowed") is False,
    }

    return {
        "identity": IDENTITY,
        "root_is_canon": "Old ~/supramental-agent" in canon,
        "route": route.get("current_route"),
        "lawful_next": route.get("current_lawful_next"),
        "lawful_next_source": route.get("current_lawful_next_source"),
        "state": {
            "anna_mvp_sealed": route.get("anna_mvp_sealed") is True,
            "anna_ship_eligible": route.get("anna_ship_eligible") is True,
            "entity_substrate_sealed": route.get("entity_substrate_sealed") is True,
            "closed_cycles": route.get("closed_cycles_count"),
            "closed_targets": route.get("closed_targets_count"),
        },
        "not": not_flags,
        "finance": {
            "real_verified_tx": money.get("real_verified_tx"),
            "real_verified_profit": money.get("real_verified_profit"),
            "simulated_verified_tx": money.get("simulated_verified_tx"),
            "ledger_honesty": money.get("ledger_honesty"),
            "next_lawful_step": mint.get("next_lawful_step"),
        },
        "machine": {
            "git_head": _git_head(),
        },
        "lawful_line": {
            "current": ln.get("current"),
            "next": ln.get("next"),
            "decision": ln.get("decision"),
        },
        "truth_boundary": (
            "WHOAMI читает только канон-файлы и состояние. "
            "Это самоописание, не самозаявление: без AGI-клейма, без денежного клейма, "
            "без маршрута, без сети."
        ),
    }


def render(data: dict) -> str:
    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║  SOCC · WHOAMI                                    read-only  ║",
        "╚══════════════════════════════════════════════════════════════╝",
        "",
        "IDENTITY",
        f"  {data['identity']}",
        f"  canon root: {'this SOCC repo' if data['root_is_canon'] else 'UNKNOWN'}",
        "",
        "CURRENT",
        f"  route: {data['route']}",
        f"  lawful_next: {data['lawful_next']}",
        f"  source: {data['lawful_next_source']}",
        "",
        "STATE",
    ]
    for k, v in data["state"].items():
        lines.append(f"  {k}: {v}")
    lines += ["", "I AM NOT"]
    for k, v in data["not"].items():
        mark = "✓" if v else "!"
        lines.append(f"  {mark} {k}: {v}")
    lines += ["", "FINANCE (honest)"]
    f = data["finance"]
    lines += [
        f"  real_verified_tx: {f['real_verified_tx']}",
        f"  real_verified_profit: {f['real_verified_profit']}",
        f"  simulated_verified_tx: {f['simulated_verified_tx']}",
        f"  ledger_honesty: {f['ledger_honesty']}",
        f"  next: {f['next_lawful_step']}",
        "",
        "MACHINE",
        f"  git HEAD: {data['machine']['git_head']}",
        "",
        "LAWFUL LINE",
    ]
    l = data["lawful_line"]
    lines += [
        f"  current: {l['current']}",
        f"  next: {l['next']}",
        f"  decision: {l['decision']}",
        "",
        "TRUTH BOUNDARY",
        f"  {data['truth_boundary']}",
        "",
        "MAIN ANSWER",
        f"  Я — SOCC: {data['identity']}.",
        f"  Мой законный шаг сейчас: {data['lawful_next']}.",
        "  Я не демон, не AGI, не фоновый цикл и не двигаю деньги без оператора.",
        f"  Реальных денег в моём леджере сейчас: {f['real_verified_profit']}.",
    ]
    return "\n".join(lines)


def main() -> int:
    print(render(collect()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

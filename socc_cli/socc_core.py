#!/usr/bin/env python3
"""SOCC Core API — единый фасад живого ядра.

Не создаёт новые органы: склеивает существующие (state, memory, recall,
brain, observe, handoff, gate) в один программный вход.

Read-only по умолчанию. Никакой сети, демонов, изменений маршрута.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
PROOF = ROOT / "SOVEREIGN/WIKI/spine2/_spine2_proof.json"
GRAPH = ROOT / "SOVEREIGN/WIKI/graph/metrics.json"
PACKS = ROOT / "SOVEREIGN/WIKI/context_packs"


def _rj(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


class SOCC:
    """Unified SOCC core API."""

    root = ROOT

    def __init__(self):
        self._route = _rj(ROUTE)
        self._proof = _rj(PROOF)
        self._graph = _rj(GRAPH)

    # truth
    def truth(self) -> dict:
        """Честная панель ядра: не заменяет гейт, а делает конфликты видимыми."""
        goal = _rj(ROOT / "SOCC_GOAL.json")
        route = self._route
        canon = _rj(ROOT / "SYSTEM/CANON/ALLOWED_TOP_LEVEL_V1.json")
        revenue = _rj(ROOT / "SOVEREIGN/LEDGER/revenue_ledger.jsonl")
        ledger = Path(ROOT / "SOVEREIGN/LEDGER/revenue_ledger.jsonl")
        allowed = set(canon.get("allowed", []))
        actual = {p.name for p in ROOT.iterdir() if p.is_dir() and p.name != ".git"}
        route_next = route.get("lawful_next") or route.get("real_next") or route.get("current_lawful_next")
        goal_next = goal.get("honest_cash_next")
        findings = []
        if goal_next and route_next and goal_next != route_next:
            findings.append({
                "id": "lawful_next_conflict",
                "severity": "high",
                "fact": f"SOCC_GOAL.honest_cash_next={goal_next!r} != route.current_lawful_next={route_next!r}",
                "fix": "Operator must choose one lawful_next; update SOCC_GOAL or route authority atomically."
            })
        if not ledger.exists():
            findings.append({
                "id": "revenue_ledger_absent",
                "severity": "high",
                "fact": "SOVEREIGN/LEDGER/revenue_ledger.jsonl does not exist",
                "fix": "No money claimed yet. First verified sale must create it via scripts/mint/socc_revenue_ledger_v1.py."
            })
        extra = actual - allowed
        if extra:
            findings.append({
                "id": "top_level_boundary_violation",
                "severity": "high",
                "fact": f"New top-level dirs: {sorted(extra)}",
                "fix": "Remove them, or get explicit operator permission and update SYSTEM/CANON/ALLOWED_TOP_LEVEL_V1.json."
            })
        # P0 readiness for the cash path (no secrets, no live calls)
        bot_cfg = _rj(ROOT / "scripts/mint/botfactory/config.demo_prodazha.json")
        botfactory_python = ROOT / "scripts/mint/botfactory/.venv/bin/python"
        aiogram_in_venv = botfactory_python.exists() and any(
            (botfactory_python.parent.parent / "lib").glob("*/site-packages/aiogram")
        )
        owner_chat_id = bot_cfg.get("owner_chat_id") if isinstance(bot_cfg, dict) else None
        p0 = {
            "aiogram_in_botfactory_venv": aiogram_in_venv,
            "aiogram_in_system_python": importlib.util.find_spec("aiogram") is not None,
            "owner_chat_id": owner_chat_id,
            "owner_chat_id_configured": bool(owner_chat_id),
            "npd_status_known": (ROOT / "scripts/mint/botfactory/.npd_ready").exists(),
            "runtime_note": "Bot must be started via scripts/mint/botfactory/.venv/bin/python until aiogram is installed system-wide or in main venv."
        }
        if not owner_chat_id:
            findings.append({
                "id": "owner_chat_id_not_configured",
                "severity": "high",
                "fact": "scripts/mint/botfactory/config.demo_prodazha.json has owner_chat_id=0",
                "fix": "Set owner_chat_id to the operator Telegram chat id before the first live run."
            })
        if not aiogram_in_venv:
            findings.append({
                "id": "aiogram_missing",
                "severity": "high",
                "fact": "aiogram is not available in scripts/mint/botfactory/.venv",
                "fix": "Install dependencies into the botfactory virtual environment."
            })
        if not p0["npd_status_known"]:
            findings.append({
                "id": "npd_status_unknown",
                "severity": "medium",
                "fact": "scripts/mint/botfactory/.npd_ready is absent",
                "fix": "After confirming NPD status, create this local marker (not committed) to turn the monitor green."
            })

        # violations present but not fatal for truth() itself
        return {
            "status": "PASS" if not findings else "ATTENTION",
            "route_status": route.get("status"),
            "route_lawful_next": route_next,
            "goal_honest_cash_next": goal_next,
            "goal_formal_lawful_next": goal.get("formal_lawful_next_anna"),
            "revenue_ledger_exists": ledger.exists(),
            "revenue_records": len(revenue) if isinstance(revenue, list) else 0,
            "top_level": {
                "allowed_count": len(allowed),
                "actual_count": len(actual),
                "extra": sorted(extra),
            },
            "p0_cash_path": p0,
            "findings": findings,
        }

    # effect gate
    def effect_gate(self, before: dict, after: dict) -> dict:
        """Закон шага: BEFORE → ACTION → AFTER → proof → memory.

        Обёртка над существующим socc_self_building_effect_auditor_v1.py.
        Не создаёт новый орган, не двигает маршрут, не пишет в proof-chain.
        """
        import importlib.util
        auditor_path = ROOT / "scripts/socc/socc_self_building_effect_auditor_v1.py"
        spec = importlib.util.spec_from_file_location("socc_self_building_effect_auditor_v1", auditor_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod.audit_effect(before, after)
        result["effect_gate"] = "BEFORE -> ACTION -> AFTER -> proof -> memory"
        result["truth_boundary"] = "Read-only wrapper. No route change, no network, no daemon, no entity birth."
        return result

    # memory-guided selector
    def selector(self, query: str, limit: int = 12) -> dict:
        """recall → lessons → bounded selector → selected_target."""
        from socc_cli.memory_selector import memory_guided_select
        return memory_guided_select(query, limit=limit)

    # state
    def state(self) -> dict:
        route = self._route
        return {
            "status": route.get("status"),
            "route": route.get("current_route"),
            "lawful_next": route.get("lawful_next") or route.get("real_next") or route.get("current_lawful_next"),
            "source": route.get("current_lawful_next_source"),
            "safety": {
                k: route.get(k) for k in (
                    "daemon_running", "background_loop_enabled", "continuous_loop_enabled",
                    "network_used", "entity_birth_allowed", "agi_claim_allowed",
                )
            },
        }

    # memory
    def memory(self) -> dict:
        proof = self._proof
        topics = list((proof.get("topics", {}) or {}).keys()) if isinstance(proof, dict) else []
        packs = sorted(p.name for p in PACKS.glob("*_context_pack_v1.json")) if PACKS.exists() else []
        return {
            "topics": topics,
            "sources_scanned": proof.get("sources_scanned") if isinstance(proof, dict) else None,
            "graph": self._graph,
            "context_packs": packs,
        }

    # recall
    def recall(self, query: str, limit: int = 12) -> dict:
        from socc_cli.recall import recall
        return recall(query, limit=limit)

    # brain
    def think(self, request: str) -> dict:
        from socc_cli.brain import think
        return think(request)

    # observe
    def observe(self) -> dict:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/socc/socc_observe_v1.py")],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT),
        )
        return {"ok": result.returncode == 0, "output": result.stdout}

    # handoff
    def handoff(self) -> dict:
        from socc_cli.handoff import collect
        return collect()

    # gate
    def gate(self) -> dict:
        result = subprocess.run(
            [sys.executable, str(ROOT / "ops/run_all_acceptances.py")],
            capture_output=True, text=True, timeout=600, cwd=str(ROOT),
        )
        return {"ok": result.returncode == 0, "output": result.stdout}

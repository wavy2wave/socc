#!/usr/bin/env python3
"""SOCC Core API — единый фасад живого ядра.

Не создаёт новые органы: склеивает существующие (state, memory, recall,
brain, observe, handoff, gate) в один программный вход.

Read-only по умолчанию. Никакой сети, демонов, изменений маршрута.
"""
from __future__ import annotations

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

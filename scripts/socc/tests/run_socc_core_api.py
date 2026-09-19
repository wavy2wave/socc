#!/usr/bin/env python3
"""Приёмка Core API — единый вход в живое ядро SOCC."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from socc_cli.socc_core import SOCC

s = SOCC()
state = s.state()
memory = s.memory()
recall = s.recall("entity substrate")
handoff = s.handoff()

checks = {
    "state_status": state.get("status") == "PASS",
    "state_lawful_next": bool(state.get("lawful_next")),
    "state_safety_off": all(v is False for v in state["safety"].values()),
    "memory_topics": len(memory["topics"]) > 0,
    "memory_graph": (memory["graph"] or {}).get("nodes", 0) > 0,
    "memory_packs": len(memory["context_packs"]) > 0,
    "recall_matches": recall["total"] > 0,
    "recall_graph": len(recall["graph_related"]) > 0,
    "handoff_route": bool(handoff["route"]["lawful_next"]),
    "handoff_memory": len(handoff["memory"]["topics"]) > 0,
    "core_map": (ROOT / "SYSTEM/KERNEL/LIVING_CORE_MAP_V1.md").exists(),
}
for k, v in checks.items():
    print(("✅ " if v else "❌ ") + k)
if not all(checks.values()):
    print("FAIL")
    raise SystemExit(1)
print("PASS: SOCC Core API — единый вход работает (state+memory+recall+handoff)")

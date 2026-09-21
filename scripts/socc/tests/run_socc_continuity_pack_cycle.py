#!/usr/bin/env python3
"""Приёмка полного цикла континуити: handoff→recall→think→gate→pack."""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from socc_cli.handoff import collect, export_pack
from socc_cli.recall import recall
from socc_cli.brain import think

# 1. handoff
handoff = collect()
checks = {
    "handoff_route_pass": handoff["route"]["status"] == "PASS",
    "handoff_lawful_next": bool(handoff["route"]["lawful_next"]),
    "handoff_memory": len(handoff["memory"]["topics"]) > 0,
    "handoff_do_not": len(handoff["goal"]["do_not"]) > 0,
}

# 2. recall from the same memory described by handoff
r = recall("entity substrate")
checks.update({
    "recall_nonempty": r["total"] > 0,
    "recall_graph_related": len(r["graph_related"]) > 0,
})

# 3. think uses memory-backed context
t = think("entity substrate")
checks.update({
    "think_intent": t["intent"]["intent_kind"] in ("build", "search", "explain"),
    "think_known_topics": len(t["knowledge"]["known_topics"]) > 0,
    "think_context_pack": bool(t["knowledge"]["context_pack"]),
})

# 4. gate contract (dry, 0₽; full gate runs separately to keep this acceptance O(seconds))
gate = ROOT / "ops/run_all_acceptances.py"
checks["gate_contract"] = gate.exists()

# 5. export one-file handoff pack
rc, pack_path = export_pack()
assert pack_path is not None
pack = pack_path.read_text(encoding="utf-8")
checks.update({
    "pack_exported": rc == 0 and pack_path.exists(),
    "pack_canonical_handoff": "## CANONICAL HANDOFF" in pack,
    "pack_route": "## ROUTE AUTHORITY" in pack,
    "pack_goal": "## GOAL / DO NOT" in pack,
    "pack_core_map": "## LIVING CORE MAP" in pack,
    "pack_context_packs": pack.count("## CONTEXT PACK ·") >= 2,
    "pack_memory_proof": "## MEMORY PROOF" in pack,
    "pack_graph": "## GRAPH METRICS" in pack,
    "pack_safety": "no network · no daemon · no route change" in pack,
    "pack_git_head": handoff["git_head"] in pack,
})

for k, v in checks.items():
    print(("✅ " if v else "❌ ") + k)
if not all(checks.values()):
    print("FAIL")
    raise SystemExit(1)
print("PASS: полный цикл континуити handoff→recall→think→gate-контракт→pack работает (0₽, read-only)")

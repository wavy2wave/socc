#!/usr/bin/env python3
"""socc handoff — континуити SOCC (read-only generate/show).

Собирает текущее состояние системы для любого нового агента/сессии:
- git HEAD;
- route authority / lawful_next;
- memory wiki/graph/recall;
- context packs;
- DO NOT из SOCC_GOAL;
- readiness гейта;
- один самодостаточный handoff-пак для внешнего агента (Codex/Claude).

Ничего не пишет в сеть, не двигает маршрут, не создаёт органы.
--generate обновляет canonical HANDOFF файл (per operator request).
--export-pack создаёт FOUNDATION/SOCC_HANDOFF_PACK_V1.md (read-only континуити-пак).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.modules[__name__].__dict__.setdefault('__builtins__', __builtins__)
MSK = timezone(timedelta(hours=3))
ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
GOAL = ROOT / "SOCC_GOAL.json"
PROOF = ROOT / "SOVEREIGN/WIKI/spine2/_spine2_proof.json"
GRAPH = ROOT / "SOVEREIGN/WIKI/graph/metrics.json"
PACKS = ROOT / "SOVEREIGN/WIKI/context_packs"
CANON = ROOT / "FOUNDATION/SOCC_OPERATOR_HANDOFF_START_PROTOCOL_V1.md"
HANDOFF_PACK = ROOT / "FOUNDATION/SOCC_HANDOFF_PACK_V1.md"


def _rj(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _head():
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def collect() -> dict:
    route = _rj(ROUTE)
    goal = _rj(GOAL)
    proof = _rj(PROOF)
    graph = _rj(GRAPH)
    packs = sorted(p.name for p in PACKS.glob("*_context_pack_v1.json")) if PACKS.exists() else []
    topics = list((proof.get("topics", {}) or {}).keys()) if isinstance(proof, dict) else []
    lawful = route.get("lawful_next") or route.get("real_next") or route.get("current_lawful_next")
    return {
        "generated_at_msk": datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds"),
        "root": str(ROOT),
        "git_head": _head(),
        "route": {
            "status": route.get("status"),
            "current_route": route.get("current_route"),
            "lawful_next": lawful,
            "source": route.get("current_lawful_next_source"),
        },
        "memory": {
            "topics": topics,
            "sources_scanned": proof.get("sources_scanned") if isinstance(proof, dict) else None,
            "graph_nodes": graph.get("nodes") if isinstance(graph, dict) else None,
            "graph_communities": graph.get("communities") if isinstance(graph, dict) else None,
            "context_packs": packs,
            "recall": "socc recall \"<запрос>\"",
        },
        "goal": {
            "goal": goal.get("goal"),
            "decision": goal.get("decision"),
            "do_not": goal.get("do_not", []),
        },
        "inputs": [
            "socc home",
            "socc observe",
            "socc recall \"<запрос>\"",
            "socc think \"<запрос>\"",
            "make gate",
        ],
        "truth_boundary": "Handoff read-only. No route change, no network, no daemon, no entity birth.",
    }


def render(d: dict) -> str:
    r = d["route"]; m = d["memory"]; g = d["goal"]
    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║  SOCC · HANDOFF — континуити для нового агента/сессии        ║",
        "╚══════════════════════════════════════════════════════════════╝",
        "",
        f"generated: {d['generated_at_msk']}",
        f"root:      {d['root']}",
        f"git HEAD:  {d['git_head']}",
        "",
        "ROUTE",
        f"  status:     {r['status']}",
        f"  route:      {r['current_route']}",
        f"  lawful_next:{r['lawful_next']}",
        f"  source:     {r['source']}",
        "",
        "MEMORY",
        f"  topics:     {', '.join(m['topics']) or '∅'}",
        f"  sources:    {m['sources_scanned']}",
        f"  graph:      {m['graph_nodes']} nodes · {m['graph_communities']} communities",
        "  packs:      " + (", ".join(m['context_packs']) or "∅"),
        "  recall:     socc recall \"<запрос>\"",
        "",
        "GOAL",
        f"  goal:       {g['goal']}",
        f"  decision:   {g['decision']}",
        "  do_not:",
    ] + [f"    - {x}" for x in g["do_not"]] + [
        "",
        "ВХОДЫ",
    ] + [f"  - {x}" for x in d["inputs"]] + [
        "",
        f"TRUTH BOUNDARY: {d['truth_boundary']}",
    ]
    return "\n".join(lines)


def export_pack() -> tuple[int, Path | None]:
    """Экспорт одного самодостаточного handoff-пака для внешнего агента."""
    d = collect()
    HANDOFF_PACK.parent.mkdir(parents=True, exist_ok=True)
    core_map = ROOT / "SYSTEM/KERNEL/LIVING_CORE_MAP_V1.md"
    goal = _rj(ROOT / "SOCC_GOAL.json")
    route = _rj(ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json")
    proof = ROOT / "SOVEREIGN/WIKI/spine2/_spine2_proof.json"
    graph = ROOT / "SOVEREIGN/WIKI/graph/metrics.json"
    parts = [
        "# SOCC HANDOFF PACK V1",
        "",
        "READ-ONLY · 0₽ · no network · no daemon · no route change · no entity birth",
        f"exported_at_msk: {d['generated_at_msk']}",
        f"root: {d['root']}",
        f"git_head: {d['git_head']}",
        "",
        "## START",
        "```text",
        "cd /Users/wavysexy/SOCC",
        "socc home",
        "socc observe",
        "socc core all",
        "```",
        "",
        "## CANONICAL HANDOFF",
        "```text",
        render(d),
        "```",
        "",
        "## ROUTE AUTHORITY",
        "```json",
        json.dumps(route, ensure_ascii=False, indent=2),
        "```",
        "",
        "## GOAL / DO NOT",
        "```json",
        json.dumps(goal, ensure_ascii=False, indent=2),
        "```",
    ]
    if core_map.exists():
        parts += ["", "## LIVING CORE MAP", "```text", core_map.read_text(encoding="utf-8").strip(), "```"]
    for pack_file in sorted(PACKS.glob("*_context_pack_v1.json")):
        parts += ["", f"## CONTEXT PACK · {pack_file.name}", "```json", pack_file.read_text(encoding="utf-8").strip(), "```"]
    parts += [
        "",
        "## MEMORY PROOF",
        "```json",
        proof.read_text(encoding="utf-8").strip(),
        "```",
        "",
        "## GRAPH METRICS",
        "```json",
        graph.read_text(encoding="utf-8").strip(),
        "```",
        "",
        "## CORE CLI",
        "```text",
        "socc core state       — маршрут, lawful_next, флаги",
        "socc core memory      — wiki/graph/packs",
        'socc core recall "q"  — поиск по памяти',
        'socc core think "q"   — план с памятью',
        "socc core handoff     — континуити (JSON)",
        "socc core observe     — системный аудит",
        "socc core all         — state+memory+handoff одним вызовом",
        "```",
    ]
    HANDOFF_PACK.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return 0, HANDOFF_PACK


def generate_if_pass() -> bool:
    """Авто-handoff: обновить канон только если route PASS. Возвращает True если обновлено."""
    route = _rj(ROUTE)
    if route.get("status") != "PASS":
        return False
    generate()
    return True


def generate() -> int:
    d = collect()
    body = render(d)
    md = [
        "# SOCC OPERATOR HANDOFF START PROTOCOL V1",
        "",
        f"status: PASS",
        f"canonical_root: {d['root']}",
        f"git_head: {d['git_head']}",
        f"generated_at_msk: {d['generated_at_msk']}",
        f"current_lawful_next: {d['route']['lawful_next']}",
        "",
        "START:",
        "  cd /Users/wavysexy/SOCC",
        "  socc home",
        "  socc observe",
        "",
        "MEMORY:",
        f"  topics: {', '.join(d['memory']['topics'])}",
        f"  graph nodes: {d['memory']['graph_nodes']}",
        f"  context packs: {', '.join(d['memory']['context_packs'])}",
        '  recall: socc recall "<запрос>"',
        "",
        "GOAL:",
        f"  {d['goal']['goal']}",
        "DO NOT:",
    ] + [f"  - {x}" for x in d["goal"]["do_not"]] + [
        "",
        "```text",
        body,
        "```",
    ]
    CANON.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(body)
    print(f"\nCANON UPDATED: {CANON}")
    return 0


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if "--generate-if-pass" in argv:
        updated = generate_if_pass()
        print("AUTO-HANDOFF::" + ("UPDATED" if updated else "SKIPPED (route not PASS)"))
        return 0 if updated else 1
    if "--export-pack" in argv:
        rc, path = export_pack()
        if path:
            print(f"HANDOFF PACK EXPORTED: {path}")
        return rc
    if "--generate" in argv:
        return generate()
    print(render(collect()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

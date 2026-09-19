#!/usr/bin/env python3
"""socc recall — поиск по системной памяти SOCC (read-only, 0₽).

Читает proof spine2 (темы/факты/источники) и graph-слой вики.
Возвращает плотный бриф: matched topics + graph related nodes.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "SOVEREIGN/WIKI/spine2/_spine2_proof.json"
GRAPH_NODES = ROOT / "SOVEREIGN/WIKI/graph/nodes.json"


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def recall(query: str, limit: int = 12) -> dict:
    q = query.lower().strip()
    if not q:
        return {"matches": [], "graph_related": [], "total": 0}
    pr = read_json(PROOF)
    terms = [t for t in re.split(r"\s+", q) if len(t) > 1]
    matches = []
    for key, topic in (pr.get("topics", {}) or {}).items():
        title = str(topic.get("title", key))
        hay = (title + " " + key).lower()
        score = sum(1 for t in terms if t in hay)
        if score:
            matches.append({
                "topic": key, "title": title, "score": score,
                "facts": topic.get("current", 0),
                "timeline": topic.get("timeline", 0),
                "sources": topic.get("sources", 0),
            })
    matches.sort(key=lambda m: (-m["score"], -m["facts"], m["topic"]))
    nodes = read_json(GRAPH_NODES)
    graph_related = sorted({
        str(n.get("id", "")) for n in nodes
        if any(t in str(n.get("id", "")).lower() for t in terms)
    })[:40]
    return {"matches": matches[:limit], "graph_related": graph_related, "total": len(matches)}


def run(query: str) -> int:
    r = recall(query)
    print("SOCC RECALL · read-only · 0₽")
    print(f"query: {query}")
    print(f"matched topics: {r['total']}")
    print()
    if not r["matches"]:
        print("  (нет совпадений)")
    for m in r["matches"]:
        print(f"  [{m['score']}] {m['title']}")
        print(f"      topic: {m['topic']} · facts: {m['facts']} · timeline: {m['timeline']} · sources: {m['sources']}")
    print()
    print(f"graph related ({len(r['graph_related'])}):")
    if r["graph_related"]:
        print("  " + ", ".join(r["graph_related"][:20]))
    else:
        print("  (нет)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: socc_cli/recall.py <query>")
        raise SystemExit(1)
    raise SystemExit(run(sys.argv[1]))

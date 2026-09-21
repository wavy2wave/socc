#!/usr/bin/env python3
"""SOCC memory-guided selector: recall → lessons → bounded selector."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from socc_cli.recall import recall

SELECTOR_PATH = ROOT / "scripts/socc/socc_enforced_self_building_next_target_selector_v1.py"


def _import_selector():
    spec = importlib.util.spec_from_file_location("socc_enforced_self_building_next_target_selector_v1", SELECTOR_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _lessons(query: str, recall_result: dict) -> list[dict]:
    """Достаёт lessons из памяти: темы, факты, граф-связи."""
    lessons = []
    for m in recall_result.get("matches", []):
        lessons.append({
            "source": "wiki_topic",
            "topic": m.get("topic"),
            "title": m.get("title"),
            "facts": m.get("facts", 0),
            "sources": m.get("sources", 0),
            "signal": "memory_topic_relevant",
        })
    for node in recall_result.get("graph_related", [])[:10]:
        lessons.append({
            "source": "graph_node",
            "node": node,
            "signal": "graph_relation_relevant",
        })
    return lessons


def _candidates_from_lessons(lessons: list[dict]) -> list[dict]:
    """Строит bounded candidates из lessons. Не обходит enforced selector."""
    candidates = []
    for lesson in lessons:
        if lesson.get("source") == "wiki_topic":
            topic = lesson.get("topic") or "socc"
            score = int(lesson.get("facts", 0) or 0)
            candidates.append({
                "name": f"reuse_{topic}_lesson_v1",
                "priority": min(100, score),
                "evidence_ready": True,
                "bounded": True,
                "requires_network": False,
                "requires_daemon": False,
                "requires_scheduler": False,
                "queue_widening": False,
                "entity_birth": False,
                "anna_birth": False,
                "agi_claim": False,
                "final_canon_approval": False,
            })
    # всегда добавляем канонический honest cash candidate
    candidates.append({
        "name": "mint_verified_ruble_v1",
        "priority": 100,
        "evidence_ready": True,
        "bounded": True,
        "requires_network": False,
        "requires_daemon": False,
        "requires_scheduler": False,
        "queue_widening": False,
        "entity_birth": False,
        "anna_birth": False,
        "agi_claim": False,
        "final_canon_approval": False,
    })
    return candidates


def memory_guided_select(query: str, limit: int = 12) -> dict:
    """recall → lessons → bounded selector → selected_target."""
    r = recall(query, limit=limit)
    lessons = _lessons(query, r)
    candidates = _candidates_from_lessons(lessons)
    selector = _import_selector()
    selection = selector.select_next_target(candidates)

    return {
        "status": selection.get("status"),
        "query": query,
        "recall_matches": r.get("total", 0),
        "graph_related_count": len(r.get("graph_related", [])),
        "lessons": lessons,
        "lessons_count": len(lessons),
        "candidates_count": len(candidates),
        "selected_target": selection.get("selected_target"),
        "selected": selection.get("selected"),
        "rejected": selection.get("rejected", []),
        "hard_failures": selection.get("hard_failures", []),
        "selector": str(SELECTOR_PATH),
        "truth_boundary": "Memory-guided only. No route change, no network, no daemon, no entity birth.",
    }

#!/usr/bin/env python3
"""SOCC Self-Evolution Engine — turns the passive wiki mirror into an active growth loop.

A toy mirror DISPLAYS the system. This engine makes the system LOOK at itself, find what is
missing/conflicting/blocked, and emit the single highest-value LAWFUL next step to close the
gap — then you (or a bounded session) act, re-run, and it points at the next gap. That closed
loop (self-knowledge -> gap detection -> bounded self-set task -> proof -> growth) is the
real self-evolution mechanism described in SOCC's own AGI-direction (Слой 4).

It is NOT a daemon and NOT AGI hype: deterministic, no-LLM, read-only over wiki artifacts,
proposes bounded lawful steps (never executes them, never births, never touches route/proof
chain). Operator stays in control: the engine recommends, you approve. Atomic write of two
files: SELF_EVOLVE.md (human backlog) + _self_evolve.json (machine).

Usage:
  python3 scripts/socc/socc_self_evolve_v1.py     # after socc_memory_spine_v2.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "SOVEREIGN" / "WIKI"
SPINE2 = WIKI / "spine2"
PROOF = SPINE2 / "_spine2_proof.json"
TOPIC_MAP = WIKI / "TOPIC_MAP_V1.json"
ROUTE = ROOT / "core" / "socc" / "route_authority" / "CURRENT_ROUTE_AUTHORITY.json"
OUT_MD = SPINE2 / "SELF_EVOLVE.md"
OUT_JSON = SPINE2 / "_self_evolve.json"

SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SEV_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def detect(proof, tmeta, route):
    """Deterministic gap detectors. Each yields a bounded, lawful candidate step."""
    tasks = []
    topics = proof.get("topics", {})

    # 1) The honest product blocker — highest leverage of all.
    if route.get("anna_mvp_sealed") and not route.get("anna_live", False):
        tasks.append({
            "kind": "REVIVE_BRAIN", "topic": "anna", "severity": "critical", "score": 10_000,
            "why": "Маршрут: anna_mvp_sealed=true, но anna_live=false — автономия встала на мёртвом LLM-мозге (401/402). "
                   "Это блокирует ВСЮ цепочку к деньгам.",
            "action": "Восстановить LLM-мозг (рабочий ключ/гейтвей/кредиты) → перезапустить anna_autonomy + Telegram → подтвердить живые циклы.",
            "lawful": "Внешний ресурс (ключ) + перезапуск runtime. Не церемония маршрута.",
        })

    # 2) Faculties the system cannot yet explain in human terms (no authored main line).
    for tid, st in topics.items():
        if not st.get("main_line_authored"):
            src = st.get("sources", 0)
            sev = "high" if src >= 150 else "medium" if src >= 60 else "low"
            tasks.append({
                "kind": "MISSING_MAIN_LINE", "topic": tid, "severity": sev, "score": src,
                "why": f"Тема «{st.get('title', tid)}» собрана из {src} источников, но НЕ имеет авторской основной линии — "
                       f"система знает факты, но не осмыслила тему по-человечески. Зеркало неполное.",
                "action": f"Написать SOVEREIGN/WIKI/main_lines/{tid}.md (основная линия: что/как/почему + ссылки на сырьё).",
                "lawful": "Авторский слой смысла (operator/Claude). Детерминированный слой не трогается.",
            })

    # 3) Unresolved internal contradictions (real forks) — the system disagrees with itself.
    for tid, st in topics.items():
        forks = st.get("forks", 0)
        if forks >= 8:
            sev = "high" if forks >= 25 else "medium"
            tasks.append({
                "kind": "UNRESOLVED_FORKS", "topic": tid, "severity": sev, "score": forks * 5,
                "why": f"Тема «{st.get('title', tid)}» несёт {forks} нерешённых развилок — система противоречит себе. "
                       f"Без разрешения основная линия не острая.",
                "action": f"Разобрать топ-развилки на странице pages/{tid}.md, зафиксировать решение в main_lines/{tid}.md (newest-wins + обоснование).",
                "lawful": "Авторское решение развилки. Сырьё и хронология сохраняются.",
            })

    # 4) Thin knowledge — a faculty with almost no current truth and no authored cover.
    for tid, st in topics.items():
        cur = st.get("current", 0)
        if cur < 5 and not st.get("main_line_authored"):
            tasks.append({
                "kind": "THIN_KNOWLEDGE", "topic": tid, "severity": "medium", "score": 200 - cur,
                "why": f"Тема «{st.get('title', tid)}» имеет лишь {cur} current-claim'ов и без авторской линии — слепое пятно.",
                "action": f"Влить больше сырья по теме в inbox (или расширить keywords темы в TOPIC_MAP_V1.json), пересобрать.",
                "lawful": "Загрузка источников + пересборка. Без исполнения.",
            })

    # 5) Route honesty — flags ahead of reality.
    if route.get("anna_mvp_sealed") and not route.get("anna_live", False):
        tasks.append({
            "kind": "ROUTE_RECONCILE", "topic": "self_construction", "severity": "medium", "score": 300,
            "why": "Флаги маршрута стоят на 'sealed/ship', но честный фронтир (живой мозг + пилот) не закрыт — риск самообмана.",
            "action": "Зафиксировать в route authority честный lawful_next (revive_brain → relaunch → first_clinic_pilot) через observe→next→reconcile.",
            "lawful": "Reconcile маршрута по закону (atomic commit), без нового execution.",
        })

    tasks.sort(key=lambda t: (SEV_RANK[t["severity"]], -t["score"]))
    return tasks


def main() -> None:
    proof = load(PROOF, {"topics": {}})
    tmap = load(TOPIC_MAP, {"topics": []})
    route = load(ROUTE, {})
    tmeta = {t["id"]: t for t in tmap.get("topics", [])}

    tasks = detect(proof, tmeta, route)
    now = datetime.now(timezone.utc).isoformat()
    top = tasks[0] if tasks else None

    out = [
        "# 🧬 SOCC — Самоэволюция (что система должна сделать, чтобы вырасти)",
        "",
        f"> Авто-собрано {now}. Система **смотрит на себя** и сама выводит следующий законный шаг.",
        "> Deterministic, no-LLM. Движок ПРЕДЛАГАЕТ bounded-шаги — оператор одобряет. Не daemon, не AGI-хайп.",
        "",
        "## ⭐ Следующий законный шаг (самый ценный)",
    ]
    if top:
        out += [
            f"### {SEV_ICON[top['severity']]} {top['kind']} · `{top['topic']}`",
            f"**Почему:** {top['why']}",
            "",
            f"**Что сделать:** {top['action']}",
            "",
            f"**Законно:** {top['lawful']}",
            "",
        ]
    else:
        out += ["_Пробелов не найдено — зеркало полное._", ""]

    out += [f"## Полный бэклог роста ({len(tasks)})", "",
            "| # | Сев. | Тип | Тема | Что сделать |", "|---|---|---|---|---|"]
    for i, t in enumerate(tasks, 1):
        out.append(f"| {i} | {SEV_ICON[t['severity']]} {t['severity']} | {t['kind']} | "
                   f"{t['topic']} | {t['action']} |")
    out += ["",
            "## Как работает петля самоэволюции",
            "```",
            "вики (знание о себе) → этот движок (находит пробел) → ⭐ следующий законный шаг",
            "      ↑                                                          ↓",
            "  пересборка  ←  ты делаешь шаг (proof)  ←  гейты PASS  ←  оператор одобряет",
            "```",
            "Сделал шаг №1 → перезапусти `socc_memory_spine_v2.py` → движок укажет новый №1. Это и есть рост по proof.",
            ""]

    write_atomic(OUT_MD, "\n".join(out) + "\n")
    write_atomic(OUT_JSON, json.dumps({"built_at": now, "next_step": top, "backlog": tasks}, ensure_ascii=False, indent=2))

    print("SOCC SELF-EVOLVE — BUILT (двигатель самоэволюции)")
    print(f"  gaps found : {len(tasks)}")
    if top:
        print(f"  next step  : {SEV_ICON[top['severity']]} {top['kind']} · {top['topic']}")
    print(f"  open       : {OUT_MD}")


if __name__ == "__main__":
    main()

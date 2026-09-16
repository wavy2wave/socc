#!/usr/bin/env python3
"""SOCC Self-Model — the wiki as a mirror of the system's self-awareness.

Reads the living-wiki artifacts (spine2 proof + TOPIC_MAP + route authority) and emits
ONE page, SOVEREIGN/WIKI/spine2/SELF_MODEL.md, that answers, from the system's own
knowledge: WHO am I · WHAT am I made of (faculties/topics) · HOW do I work (loop + law) ·
my CONNECTIONS (goal chain) · WHAT do I need next for self-evolution · honest UNKNOWNS.

This is the "зеркало сознания": run it after the spine and the system can see itself whole
— and from that decide which lawful next step to take. Deterministic, no-LLM, read-only over
artifacts, atomic write of one file. No route authority / proof chain mutation, no network.

Usage:
  python3 scripts/socc/socc_self_model_v1.py     # after socc_memory_spine_v2.py
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
OUT = SPINE2 / "SELF_MODEL.md"

# The system's spine, ordered as a living organism (substrate -> core -> engine -> product).
CHAIN_ORDER = ["memory", "law_proof", "socc", "self_construction", "entity_substrate", "anna", "vision"]


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


def main() -> None:
    proof = load(PROOF, {"topics": {}})
    tmap = load(TOPIC_MAP, {"topics": []})
    route = load(ROUTE, {})
    tmeta = {t["id"]: t for t in tmap.get("topics", [])}
    ptopics = proof.get("topics", {})

    order = [tid for tid in CHAIN_ORDER if tid in tmeta] + \
            [tid for tid in tmeta if tid not in CHAIN_ORDER]

    now = datetime.now(timezone.utc).isoformat()
    socc = tmeta.get("socc", {})
    sc = tmeta.get("self_construction", {})

    out = [
        "# 🧠 SOCC — Модель себя (зеркало сознания)",
        "",
        f"> Авто-собрано из живой вики {now}. Это то, что система **знает о себе** прямо сейчас.",
        "> Deterministic, no-LLM. Каждая способность — кликабельная статья со ссылками на сырьё.",
        "> Перезапусти spine → знание свежее → это зеркало обновляется.",
        "",
        "## Кто я",
        socc.get("summary", "SOCC — Sovereign Cognitive Operating Core."),
        "",
        "**Базовый цикл сознания (как я думаю и расту):**",
        "`memory → understanding → goal → attention → decision → capability → runtime → proof → learning → updated self-model`",
        "Каждый виток ограничен (bounded), оставляет proof и **обновляет эту модель себя**.",
        "",
        "## Из чего я состою — мои способности (темы по смыслу)",
        "",
        "| Способность | Что это | Истина | Развилки | Источников | authored |",
        "|---|---|---|---|---|---|",
    ]
    for tid in order:
        meta = tmeta.get(tid, {})
        st = ptopics.get(tid, {})
        title = meta.get("title", tid)
        summ = (meta.get("summary", "") or "")[:140]
        cur = st.get("current", "—")
        forks = st.get("forks", "—")
        src = st.get("sources", "—")
        auth = "✅" if st.get("main_line_authored") else "—"
        out.append(f"| [{title}](pages/{tid}.md) | {summ} | {cur} | {forks} | {src} | {auth} |")
    out.append("")

    out += [
        "## Как я работаю (закон + цепочка одного шага)",
        sc.get("summary", "Самостройка: один bounded-шаг → гейты PASS → эффект → proof → стоп."),
        "",
        "**Законная цепочка любого шага:** `intake → direction → plan → scientific gate → "
        "Hermes gate → Codex gate → bounded execution → одна foreground-сессия → "
        "dashboard+state+memory+proof → STOP`. Гейт PI Agent ловит фантом-эффект. "
        "Подробно → [Автономное строительство](pages/self_construction.md).",
        "",
        "## Мои связи (цель-цепочка — порядок строг)",
        "",
        "```",
        "Память + Закон  →  SOCC ядро  →  Автономное строительство  →  Entity Substrate  →  ANNA  →  ship клинике",
        " (фундамент)       (кто я)        (двигатель самоэволюции)     (орган рождения)    (продукт)  (деньги)",
        "```",
        "Прыжки через шаги запрещены. Память и Закон — рельсы под всем.",
        "",
    ]

    # What I need next — straight from the route authority + honest blocker.
    nxt = route.get("current_lawful_next") or route.get("lawful_next") or "—"
    cur_route = route.get("current_route", "—")
    sealed = []
    for k in ("entity_substrate_sealed", "anna_mvp_sealed"):
        if route.get(k):
            sealed.append(k.replace("_", " "))
    out += [
        "## Что мне нужно для самоэволюции (следующий шаг)",
        f"- **current_route:** `{cur_route}`",
        f"- **lawful_next (по маршруту):** `{nxt}`",
        f"- **запечатано:** {', '.join(sealed) if sealed else '—'}",
        "- **честный блокер:** автономный цикл встал на мёртвом LLM-мозге (401/402). "
        "Настоящий next — не новая церемония, а: восстановить мозг → перезапустить цикл → "
        "реальный пилот в клинике. См. [ANNA](pages/anna.md).",
        "",
        "## Граница честности (что я ещё НЕ знаю / не закрыто)",
        f"- источников в памяти: **{proof.get('sources_scanned', '—')}** · "
        f"мусора отфильтровано: **{proof.get('junk_dropped', '—')}** строк (код/вывод, не знание).",
        "- тон/эмоции пока не разбираются (экстрактор фактов, не семантика чувств).",
        "- полярность развилок (assert/negate) — грубая; кураторские развилки живут в authored-линиях.",
        "- флаги маршрута могли уйти в «sealed/ship» раньше реального продуктового гейта — "
        "это зафиксировано честно, не замазано.",
        "",
        "---",
        "_Это зеркало — не украшение. Система читает его, чтобы понять, какой законный шаг взять для роста._",
    ]

    write_atomic(OUT, "\n".join(out) + "\n")
    print("SOCC SELF-MODEL — BUILT (зеркало сознания)")
    print(f"  faculties : {len(order)}  ·  sources : {proof.get('sources_scanned', '—')}")
    print(f"  open      : {OUT}")


if __name__ == "__main__":
    main()

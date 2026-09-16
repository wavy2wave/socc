#!/usr/bin/env python3
"""SOCC Atom Reasoning — the cortex's thinking layer.

Decomposes ONE file into atoms (meaningful segments) and, for each, surfaces not just WHAT
was said but WHY it matters, WHICH domain (meaning-topic) it touches, whether it is NEW
knowledge, and WHERE it LEADS (which growth direction it feeds). This is the evolutionary
DNA: every atom becomes a growth vector, so the system can want to grow in directions — not
just store facts.

Atoms = segments (lines / sentences), not only the high-precision parser claims, so the
cortex can show a RICH per-part breakdown of how the file is understood.

Emits one JSON the SOCC Cortex streams as live "reasoning": a thinking-trace, per-atom
decisions, domains touched, growth directions (what the system WANTS next), and an
Obsidian-style graph (domain hubs + file + atoms). Deterministic, no-LLM, read-only. Lawful.

Usage:  python3 scripts/socc/socc_atom_reasoning_v1.py "<path/to/file>"
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "SOVEREIGN" / "WIKI"
TOPIC_MAP = WIKI / "TOPIC_MAP_V1.json"
SPINE2 = WIKI / "spine2"
SELF_EVOLVE = SPINE2 / "_self_evolve.json"

_UI_GLYPHS = "⏺↳⎿❯│├└▌▐◀▶✶✻✽⊹"
_CODE_RE = re.compile(
    r"(\bdef\s+\w+\s*\(|\blambda\b|\bimport\s+\w|\bprint\s*\(|\bfor\s+\w+\s+in\b.*:|"
    r"=\s*max\s*\(|=\s*json\.|os\.\w+\(|self\.\w+|subprocess\.|</?\w+>|::|:=|==|!=|=>|"
    r"\bcurl\b|\bsudo\b|\bpython3\b|#L\d+|\.py\b)")
_PALETTE = ["#5cc8ff", "#46d39a", "#f5c451", "#f5736b", "#b78bff", "#7ee0c8", "#ff9e64"]


def is_junk(text: str) -> bool:
    t = text.strip()
    if len(t) < 14:
        return True
    if any(g in t for g in _UI_GLYPHS):
        return True
    if re.match(r"^\s*\d{1,4}\s+\S", t) and ("=" in t or "(" in t):
        return True
    if _CODE_RE.search(t):
        return True
    letters = sum(ch.isalpha() for ch in t)
    return letters / max(len(t), 1) < 0.45


def norm(t: str) -> str:
    return re.sub(r"[^0-9a-zA-Zа-яёА-ЯЁ]+", " ", t.lower()).strip()


def load_taxonomy():
    data = json.loads(TOPIC_MAP.read_text(encoding="utf-8"))
    rank, meta, matchers = {}, {}, {}
    for i, t in enumerate(data["topics"]):
        tid = t["id"]
        rank[tid] = t.get("rank", 99)
        meta[tid] = {"title": t["title"], "summary": t.get("summary", ""),
                     "goal_chain": t.get("goal_chain", ""), "color": _PALETTE[i % len(_PALETTE)]}
        members = [re.compile(r"\b" + re.escape(m.lower()) + r"\b") for m in t["members"]]
        matchers[tid] = {"members": list(zip(t["members"], members)),
                         "keywords": [k.lower() for k in t.get("keywords", [])]}
    return rank, meta, matchers


def classify(low, rank, matchers):
    """Pick the most specific (lowest-rank) domain whose member/keyword matches the segment."""
    hits = []
    for tid, mx in matchers.items():
        for name, pat in mx["members"]:
            if pat.search(low):
                hits.append((rank[tid], tid, f"упомянут «{name}»"))
                break
        else:
            for kw in mx["keywords"]:
                if kw in low:
                    hits.append((rank[tid], tid, f"по смыслу: «{kw}»"))
                    break
    if not hits:
        return None, "вне смысловой карты"
    hits.sort()
    return hits[0][1], hits[0][2]


def human_intent(low):
    if low.endswith("?") or low.startswith(("как ", "что ", "почему", "зачем", "когда", "нужно ли")):
        return "вопрос"
    if any(w in low for w in ("должн", "нужно", "надо", "сделать", "построить", "запустить")):
        return "задача"
    if any(w in low for w in ("решено", "выбрали", "отказались", "не будем", "вместо")):
        return "решение"
    if any(w in low for w in (" не ", "нельзя", "запрещ", "without", "no daemon")):
        return "ограничение"
    return "идея/факт"


def segments(text):
    out = []
    for ln_no, raw in enumerate(text.splitlines(), 1):
        s = raw.strip().lstrip("#->*•·—– ").strip()
        if not s:
            continue
        parts = re.split(r"(?<=[.!?。])\s+", s) if len(s) > 170 else [s]
        for p in parts:
            p = p.strip()
            if len(p) >= 14:
                out.append((p, ln_no))
    return out


def analyze_file(path: Path):
    rank, meta, matchers = load_taxonomy()
    known_blob = ""
    if (SPINE2 / "pages").exists():
        for p in (SPINE2 / "pages").glob("*.md"):
            known_blob += " " + norm(p.read_text(encoding="utf-8"))
    wanted = set()
    if SELF_EVOLVE.exists():
        try:
            wanted = {b.get("topic") for b in json.loads(SELF_EVOLVE.read_text(encoding="utf-8")).get("backlog", [])}
        except Exception:
            pass

    text = path.read_text(encoding="utf-8", errors="replace")
    segs = segments(text)

    atoms, domains, intents, seen = [], defaultdict(int), defaultdict(int), set()
    raw_n = len(segs)
    new_count = 0
    for i, (seg, line) in enumerate(segs):
        if is_junk(seg):
            continue
        key = norm(seg)[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        low = seg.lower()
        tid, why = classify(low, rank, matchers)
        if not tid:
            continue                                  # cortex shows only atoms it can place in meaning
        intent = human_intent(low)
        novelty = "known" if key[:64] in known_blob else "new"
        if novelty == "new":
            new_count += 1
        domains[tid] += 1
        intents[intent] += 1
        atoms.append({
            "n": len(atoms) + 1, "line": line, "text": seg[:240],
            "domain": tid, "domain_title": meta[tid]["title"], "color": meta[tid]["color"],
            "intent": intent, "novelty": novelty, "why": why,
            "leads_to": meta[tid]["goal_chain"], "wants": tid in wanted,
        })

    growth = [{"topic": tid, "title": meta[tid]["title"], "atoms": n,
               "leads_to": meta[tid]["goal_chain"], "wants": tid in wanted}
              for tid, n in sorted(domains.items(), key=lambda x: -x[1])]

    trace = [
        f"📥 Принял файл «{path.name}» — {len(text.splitlines())} строк",
        f"🔬 Разбил на {raw_n} сегментов, оставил {len(atoms)} осмысленных атомов",
        f"🧭 Разложил по смыслу — {len(domains)} доменов задето",
    ]
    for g in growth[:6]:
        flag = "  ⟵ система ХОЧЕТ сюда расти" if g["wants"] else ""
        trace.append(f"   → «{g['title'].split(' —')[0]}»: {g['atoms']} атомов · ведёт к: {g['leads_to']}{flag}")
    trace.append(f"✨ Новизна: {new_count} новых атомов — рост знания системы")
    wants_here = [g["title"].split(" —")[0] for g in growth if g["wants"]]
    if wants_here:
        trace.append("🧬 Эволюционный вектор: файл питает то, что система уже хочет закрыть — " + ", ".join(wants_here))

    nodes = [{"id": "file", "label": path.name, "group": "file", "size": 16}]
    for tid, n in domains.items():
        nodes.append({"id": tid, "label": meta[tid]["title"].split(" —")[0], "group": "domain",
                      "size": 10 + min(n, 28), "color": meta[tid]["color"], "wants": tid in wanted})
    links = [{"source": "file", "target": tid, "w": n} for tid, n in domains.items()]
    for a in atoms[:30]:
        aid = f"a{a['n']}"
        nodes.append({"id": aid, "label": a["text"][:40], "group": "atom",
                      "color": a["color"], "size": 4, "novelty": a["novelty"]})
        links.append({"source": aid, "target": a["domain"], "w": 1})

    return {
        "file": {"name": path.name, "lines": len(text.splitlines()), "bytes": len(text)},
        "stats": {"atoms": len(atoms), "segments": raw_n, "new": new_count, "domains": len(domains)},
        "atoms": atoms[:140],
        "domains_touched": dict(domains),
        "intents": dict(intents),
        "growth": growth,
        "trace": trace,
        "graph": {"nodes": nodes, "links": links},
    }


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: socc_atom_reasoning_v1.py <file>")
    path = Path(sys.argv[1])
    if not path.exists():
        raise SystemExit(f"no such file: {path}")
    print(json.dumps(analyze_file(path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

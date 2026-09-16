"""SOCC Knowledge Spine — one nerve over the existing knowledge_substrate organs.

Turns dozens of scattered source files into ONE living knowledge base:
scan -> parse -> govern -> per-topic living articles + master index + an
auto-generated CONTEXT_PACK (the single file you used to feed to each new chat,
now assembled from current truth instead of maintained by hand).

Truth boundary (SOCC-lawful):
  Read-only over sources. Writes ONLY under SOVEREIGN/WIKI/spine/. It does NOT
  touch route authority, proof chain, Memory Wave roots, Entity/ANNA birth,
  network, daemon, or autonomy. One bounded foreground step, proof, stop.
  Deterministic: no LLM is used. Re-runnable => "living" (re-run = fresh truth).

Usage:
  python3 scripts/socc/socc_knowledge_spine_v1.py
"""

from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]            # /Users/wavysexy/SOCC
sys.path.insert(0, str(ROOT))

from knowledge_substrate import scanner, parser, governance  # noqa: E402

HOME = Path.home()
OUT_DIR = ROOT / "SOVEREIGN" / "WIKI" / "spine"
MAIN_LINES_DIR = ROOT / "SOVEREIGN" / "WIKI" / "main_lines"   # authored prose, survives rebuilds

# Where your idea actually lives, scattered across the disk. Read-only.
CORPORA = [
    {"root": ROOT / "SOVEREIGN" / "MEMORY" / "inbox", "suffixes": [".txt", ".md", ".eml", ".json"], "recurse": True},
    {"root": HOME / "Downloads" / "MEMORY SOCC", "suffixes": [".txt", ".md", ".eml"], "recurse": True},
    {"root": HOME / "Downloads", "suffixes": [".md", ".txt"], "recurse": False},
    {"root": ROOT / "SYSTEM", "suffixes": [".md"], "recurse": True},
    {"root": ROOT / "FOUNDATION", "suffixes": [".md"], "recurse": True},
]

# Topics always present (canon spine of SOCC), plus auto-discovered hot entities.
ALWAYS_TOPICS = ["SOCC", "Entity Substrate", "ANNA", "Memory Wave", "Knowledge Substrate"]
MAX_TOPICS = 14
MIN_TOPIC_MENTIONS = 25       # an entity becomes a topic if mentioned this often across the corpus
PAGE_CLAIM_CAP = 40           # current-authority claims rendered per page
PACK_CLAIM_CAP = 6            # claims per topic in the compact context pack


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ref(rec, line):
    return f"{rec['abs_path']}:{line}"


def _md_link(rec, line):
    name = Path(rec["abs_path"]).name
    return f"[{name}:{line}]({rec['abs_path']}#L{line})"


def discover_records():
    """Scan every corpus; return source records annotated with parsed memory."""
    records = []
    for c in CORPORA:
        root = c["root"]
        if not root.exists():
            continue
        recs, err = scanner.scan_root(str(root), c["suffixes"], exclude_globs=[], recurse=c["recurse"])
        if err:
            continue
        for r in recs:
            try:
                text = Path(r["abs_path"]).read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            r["parsed"] = parser.parse_text(text)
            records.append(r)
    return records


def pick_topics(records):
    """Canon topics + entities mentioned often enough across the whole corpus."""
    totals = defaultdict(int)
    for r in records:
        for ent, n in r["parsed"]["entity_counts"].items():
            totals[ent] += n
    hot = sorted(totals.items(), key=lambda kv: -kv[1])
    topics = list(ALWAYS_TOPICS)
    for ent, n in hot:
        if ent not in topics and n >= MIN_TOPIC_MENTIONS:
            topics.append(ent)
    return totals, topics[:MAX_TOPICS]


def claims_for_topic(records, topic):
    """Build governance-ready claim dicts (with source links) for one topic."""
    out, dates = [], []
    for r in records:
        parsed = r["parsed"]
        if r["parsed"]["entity_counts"].get(topic, 0) == 0:
            continue
        for cl in parsed["claims"]:
            if topic not in cl["entities"]:
                continue
            out.append({
                "text": cl["text"],
                "entities": cl["entities"],
                "polarity": cl["polarity"],
                "intent": cl["intent"],
                "source_mtime_utc": r.get("mtime_utc"),
                "source_provenance": r.get("provenance"),
                "link": {"ref": _ref(r, cl["line"]), "md_link": _md_link(r, cl["line"]), "line": cl["line"]},
            })
        # timeline events for files that are genuinely "about" this topic
        if r["parsed"]["entity_counts"].get(topic, 0) >= 3:
            for d in parsed["dates"]:
                if "2026-01-01" <= d["value"] <= "2027-12-31":
                    dates.append({"date": d["value"], "ref": _ref(r, d["line"]),
                                  "event": f"{Path(r['abs_path']).name}: {d['raw']}"})
    return out, dates


def load_main_line(slug):
    """Authored main line for a topic, if present. Survives rebuilds."""
    f = MAIN_LINES_DIR / f"{slug}.md"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    return None


def render_page(topic, gov, timeline, n_sources, main_line=None):
    cur = gov["current_authority"]
    definition = max((c for c in cur if len(c["text"]) > 30), key=lambda c: len(c["text"]), default=None)
    out = [f"# {topic} — SOCC Knowledge Spine", "",
           "> Живая статья. Newest source wins; in-repo canon = current authority.",
           "> Каждый пункт ссылается на сырой источник (`path#Lnn`). Deterministic, no-LLM.", ""]
    if main_line:
        out += ["## Основная линия (authored)", main_line, ""]
    out += ["## Определение"]
    out += [definition["text"] + f"  \n↳ `{definition['link']['ref']}`" if definition else "_(не извлечено)_", ""]
    out += [f"## Current Authority ({gov['counts']['current']})"]
    for c in cur[:PAGE_CLAIM_CAP]:
        out.append(f"- {c['text']}  \n  ↳ {c['link']['md_link']}")
    out.append("")
    if gov["conflicting"]:
        out += [f"## Conflicting / Open ({gov['counts']['conflicting']})"]
        for c in gov["conflicting"][:20]:
            out.append(f"- {c['text']}  \n  ↳ {c['link']['md_link']}")
        out.append("")
    if timeline:
        out += [f"## Timeline ({len(timeline)})"]
        for t in timeline[:60]:
            out.append(f"- **{t['date']}** — {t['event']}  \n  ↳ `{t['ref']}`")
        out.append("")
    out += [f"## Источников использовано: {n_sources}", ""]
    return "\n".join(out)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "pages").mkdir(exist_ok=True)

    records = discover_records()
    totals, topics = pick_topics(records)

    proof = {"id": "SOCC_KNOWLEDGE_SPINE_V1", "built_at": _now(),
             "sources_scanned": len(records), "topics": {},
             "truth_boundary": ("Read-only spine build. Writes only under SOVEREIGN/WIKI/spine/. "
                                "No route authority / proof chain / Memory Wave / Entity / ANNA / "
                                "network / daemon / autonomy. Deterministic, no-LLM.")}

    index = ["# SOCC Knowledge Spine — Master Index", "",
             f"_Собрано {proof['built_at']} из {len(records)} источников. Deterministic, no-LLM._", "",
             "| Тема | Current | Conflicting | Timeline | Mentions |", "|---|---|---|---|---|"]
    pack = ["# SOCC — CONTEXT PACK (auto-generated)", "",
            "> Это файл, который раньше ты вскармливал каждому новому чату.",
            "> Теперь он собирается сам из текущей истины твоих файлов. Не редактируй руками — перезапусти spine.",
            f"> Собрано: {proof['built_at']} · источников: {len(records)}", ""]

    for topic in topics:
        claims, raw_dates = claims_for_topic(records, topic)
        if not claims:
            continue
        gov = governance.classify(claims)
        seen, timeline = {}, []
        for d in sorted(raw_dates, key=lambda x: x["date"]):
            seen.setdefault(d["date"], d)
        timeline = list(seen.values())

        slug = topic.lower().replace(" ", "_").replace("/", "_")
        n_src = len({c["link"]["ref"].rsplit(":", 1)[0] for c in claims})
        main_line = load_main_line(slug)
        (OUT_DIR / "pages" / f"{slug}.md").write_text(
            render_page(topic, gov, timeline, n_src, main_line), encoding="utf-8")

        proof["topics"][topic] = {"current": gov["counts"]["current"], "conflicting": gov["counts"]["conflicting"],
                                  "historical": gov["counts"]["historical"], "timeline": len(timeline),
                                  "mentions": totals.get(topic, 0), "sources": n_src,
                                  "main_line_authored": bool(main_line)}
        index.append(f"| [{topic}](pages/{slug}.md) | {gov['counts']['current']} | "
                     f"{gov['counts']['conflicting']} | {len(timeline)} | {totals.get(topic, 0)} |")

        cur = gov["current_authority"]
        definition = max((c for c in cur if len(c["text"]) > 30), key=lambda c: len(c["text"]), default=None)
        pack += [f"## {topic}"]
        if main_line:
            pack += [main_line, ""]          # authored main line is the truth fed to chats
        elif definition:
            pack.append(f"**Определение:** {definition['text']}  ↳ `{definition['link']['ref']}`")
            for c in cur[:PACK_CLAIM_CAP]:
                pack.append(f"- {c['text']}")
        pack.append("")

    (OUT_DIR / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    (OUT_DIR / "CONTEXT_PACK.md").write_text("\n".join(pack) + "\n", encoding="utf-8")
    (OUT_DIR / "_spine_proof.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")

    print("SOCC KNOWLEDGE SPINE — BUILT")
    print(f"  sources scanned : {len(records)}")
    print(f"  topics built    : {len(proof['topics'])}")
    print(f"  output          : {OUT_DIR}")
    print(f"  files           : INDEX.md · CONTEXT_PACK.md · pages/*.md · _spine_proof.json")
    top = sorted(proof["topics"].items(), key=lambda kv: -kv[1]["current"])[:8]
    print("  top topics (current-authority claims):")
    for name, st in top:
        print(f"    {name:24} cur={st['current']:4}  conflict={st['conflicting']:4}  src={st['sources']:3}")


if __name__ == "__main__":
    main()

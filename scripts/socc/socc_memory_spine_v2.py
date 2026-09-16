#!/usr/bin/env python3
"""SOCC Memory Spine v2 — meaning-based, fast, concurrency-safe living wiki.

Why v2 (over socc_knowledge_spine_v1.py):
  v1 made EVERY frequently-mentioned lexicon entity its own topic ("Daemon",
  "Telegram", "Booking" became topics) — topics by MENTION COUNT, not meaning,
  and governance boilerplate ("does not birth ANNA / no daemon / no AGI") flooded
  every page thousands of times. This v2 fixes exactly that:

    1. TOPICS BY MEANING. Reads SOVEREIGN/WIKI/TOPIC_MAP_V1.json — 6 curated human
       themes, each absorbing several lexicon entities. A claim is assigned to ONE
       primary topic (most specific entity wins), not scattered across all.
    2. NOISE COLLAPSE. The repetitive truth-boundary boilerplate is detected and
       collapsed to 1-2 representative samples per topic instead of thousands.
    3. NEAR-DUP DEDUP. Beyond governance's exact-text dedup, near-identical claims
       (same normalized text) collapse to the freshest one.
    4. HUMAN RENDER. Each page leads with the authored main line (main_lines/<id>.md),
       then a tight "current truth", "real forks", a collapsed "historical boundary",
       timeline, and sources. Reads like Wikipedia, not a log.
    5. FAST. Parse results are cached by sha16 (.cache_v2/parsed/<sha16>.json). After
       a warm cache, re-runs are seconds instead of ~145s (only new/changed files
       are parsed).
    6. CONCURRENCY-SAFE. Writes only under SOVEREIGN/WIKI/spine2/ + .cache_v2/, via
       atomic temp+os.replace. Does NOT touch v1 (spine/), route authority, proof
       chain, network, daemon. Read-only over sources & main_lines. Re-runnable.

Usage:
  python3 scripts/socc/socc_memory_spine_v2.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]            # /Users/wavysexy/SOCC
sys.path.insert(0, str(ROOT))

from knowledge_substrate import scanner, parser, governance  # noqa: E402

HOME = Path.home()
WIKI = ROOT / "SOVEREIGN" / "WIKI"
OUT_DIR = WIKI / "spine2"
MAIN_LINES_DIR = WIKI / "main_lines"
TOPIC_MAP = WIKI / "TOPIC_MAP_V1.json"
CACHE_DIR = WIKI / ".cache_v2" / "parsed"

# Same scattered corpus as v1, read-only.
CORPORA = [
    {"root": ROOT / "SOVEREIGN" / "MEMORY" / "inbox", "suffixes": [".txt", ".md", ".eml", ".json"], "recurse": True},
    {"root": HOME / "Downloads" / "MEMORY SOCC", "suffixes": [".txt", ".md", ".eml"], "recurse": True},
    {"root": HOME / "Downloads", "suffixes": [".md", ".txt"], "recurse": False},
    {"root": ROOT / "SYSTEM", "suffixes": [".md"], "recurse": True},
    {"root": ROOT / "FOUNDATION", "suffixes": [".md"], "recurse": True},
]

PAGE_CURRENT_CAP = 18    # current-truth claims rendered per page (after dedup)
PAGE_FORK_CAP = 12       # real forks (conflicting) rendered per page
BOUNDARY_SAMPLE_CAP = 2  # collapsed boilerplate samples kept per topic
PACK_CLAIM_CAP = 5

# Governance / truth-boundary boilerplate tokens. A claim hitting >=3 of these is
# treated as repetitive boundary noise: collapsed, not exploded across the page.
_NOISE_TOKENS = [
    "does not", "do not", "not born", "birth entity", "birth anna", "entity/anna",
    "no daemon", "daemon", "scheduler", "background loop", "24/7", "widen queue",
    "queue runtime", "final canon", "claim agi", " agi", "truth_boundary",
    "не рождает", "не запускает", "не расширяет", "не трогает", "unsupervised",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_atomic(path: Path, text: str) -> None:
    """Atomic write: temp file in same dir + os.replace. Safe under concurrent runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_taxonomy():
    data = json.loads(TOPIC_MAP.read_text(encoding="utf-8"))
    topics = data["topics"]
    ent2topic = {}          # lexicon entity -> topic id
    for t in topics:
        for m in t["members"]:
            ent2topic[m] = t["id"]
    rank = {t["id"]: t.get("rank", 99) for t in topics}
    return topics, ent2topic, rank


def parse_cached(rec):
    """parse_text(rec) with an sha16 cache. Cache hit => no re-parse (the speed win)."""
    cf = CACHE_DIR / f"{rec['sha16']}.json"
    if cf.exists():
        try:
            return json.loads(cf.read_text(encoding="utf-8")), True
        except Exception:
            pass
    try:
        text = Path(rec["abs_path"]).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None, False
    parsed = parser.parse_text(text)
    # store only what the spine needs (keeps cache small, drops bulky entity contexts)
    slim = {
        "claims": parsed["claims"],
        "dates": parsed["dates"],
        "entity_counts": parsed["entity_counts"],
    }
    try:
        write_atomic(cf, json.dumps(slim, ensure_ascii=False))
    except Exception:
        pass
    return slim, False


def is_boundary(text: str) -> bool:
    low = text.lower()
    return sum(tok in low for tok in _NOISE_TOKENS) >= 3


# Claude-CLI / terminal UI glyphs and code/tool-output signatures. The work-history logs
# (ПАМЯТЬ ТЕРМИНАЛ.txt, ИСТОРИЯ РАБОТЫ1.txt) are full of code lines and tool output that the
# parser mistakes for "claims". This is the «мусор vs идея» filter: junk never enters the wiki.
_UI_GLYPHS = "⏺↳⎿❯│├└▌▐◀▶✶✻✽⊹"
_CODE_RE = re.compile(
    r"(\bdef\s+\w+\s*\(|\blambda\b|\bimport\s+\w|\bprint\s*\(|\bfor\s+\w+\s+in\b.*:|"
    r"=\s*max\s*\(|=\s*json\.|os\.\w+\(|self\.\w+|subprocess\.|\)\s*$|^\s*[\[{].*[\]}]\s*,?\s*$|"
    r"</?\w+>|::|:=|==|!=|=>|\+\+|&&|\|\||\bcurl\b|\bsudo\b|\bpython3\b|#L\d+|\.py\b|\.json\b)")


def is_junk(text: str) -> bool:
    """True if the line is code / tool-output / UI chrome, not a genuine knowledge claim."""
    t = text.strip()
    if len(t) < 14:
        return True
    if any(g in t for g in _UI_GLYPHS):
        return True
    # line-number-prefixed code dump, e.g. "137  definition = max(("
    if re.match(r"^\s*\d{1,4}\s+\S", t) and ("=" in t or "(" in t):
        return True
    if _CODE_RE.search(t):
        return True
    # symbol-heavy (JSON fragments, paths, ascii tables) — not prose
    letters = sum(ch.isalpha() for ch in t)
    if letters / max(len(t), 1) < 0.45:
        return True
    return False


def norm(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Zа-яёА-ЯЁ]+", " ", text.lower()).strip()


def _ref(abs_path, line):
    return f"{abs_path}:{line}"


def _md_link(abs_path, line):
    return f"[{Path(abs_path).name}:{line}]({abs_path}#L{line})"


def discover():
    """Scan every corpus once; return records (read-only)."""
    records = []
    for c in CORPORA:
        if not c["root"].exists():
            continue
        recs, err = scanner.scan_root(str(c["root"]), c["suffixes"], exclude_globs=[], recurse=c["recurse"])
        if err:
            continue
        records.extend(recs)
    return records


def collect(records, topics, ent2topic, rank):
    """Assign each claim to ONE primary meaning-topic; collapse boilerplate; gather timelines."""
    by_topic = {t["id"]: {"claims": [], "boundary": [], "dates": [], "src": set()} for t in topics}
    member_sets = {t["id"]: set(t["members"]) for t in topics}
    cache_hits = 0
    junk_dropped = 0

    for r in records:
        parsed, hit = parse_cached(r)
        if parsed is None:
            continue
        cache_hits += hit
        ecounts = parsed.get("entity_counts", {})

        for cl in parsed["claims"]:
            if is_junk(cl["text"]):
                junk_dropped += 1
                continue
            cand = {ent2topic[e] for e in cl["entities"] if e in ent2topic}
            if not cand:
                continue
            primary = min(cand, key=lambda tid: rank[tid])   # most specific topic wins
            item = {
                "text": cl["text"],
                "entities": cl["entities"],
                "polarity": cl["polarity"],
                "intent": cl["intent"],
                "source_mtime_utc": r.get("mtime_utc"),
                "source_provenance": r.get("provenance"),
                "link": {"ref": _ref(r["abs_path"], cl["line"]),
                         "md_link": _md_link(r["abs_path"], cl["line"]), "line": cl["line"]},
            }
            bucket = by_topic[primary]
            if is_boundary(cl["text"]):
                bucket["boundary"].append(item)
            else:
                bucket["claims"].append(item)
            bucket["src"].add(r["abs_path"])

        # timelines: dates from files genuinely "about" a topic (a member entity seen >=3x)
        for t in topics:
            if any(ecounts.get(m, 0) >= 3 for m in member_sets[t["id"]]):
                for d in parsed["dates"]:
                    if "2026-01-01" <= d["value"] <= "2027-12-31":
                        by_topic[t["id"]]["dates"].append(
                            {"date": d["value"], "ref": _ref(r["abs_path"], d["line"]),
                             "event": f"{Path(r['abs_path']).name}: {d['raw']}"})
    return by_topic, cache_hits, junk_dropped


def dedup_near(claims):
    """Collapse near-identical claim texts to the freshest occurrence; preserve order."""
    best = {}
    order = []
    for c in claims:
        k = norm(c["text"])
        if not k:
            continue
        prev = best.get(k)
        if prev is None:
            best[k] = c
            order.append(k)
        elif (c.get("source_mtime_utc") or "") > (prev.get("source_mtime_utc") or ""):
            best[k] = c
    return [best[k] for k in order]


def real_forks(conflicting):
    """Turn governance's raw 'conflicting' bucket into GENUINE forks.

    governance dumps EVERY claim of any mixed-polarity entity-signature group into
    'conflicting' — so the raw count (e.g. 2869) is mentions, not disagreements. Here a
    fork = ONE entity-set genuinely in disagreement: we drop boundary boilerplate, group
    by entity signature, keep only groups that still carry >=2 polarities, and show the
    freshest exemplar per side. Returns forks newest-first, each with its raw mention count.
    """
    groups = {}
    for c in conflicting:
        if is_boundary(c["text"]):
            continue
        sig = frozenset(c.get("entities", []))
        groups.setdefault(sig, []).append(c)
    forks = []
    for sig, items in groups.items():
        per_pol = {}
        for c in items:
            p = c.get("polarity")
            prev = per_pol.get(p)
            if prev is None or (c.get("source_mtime_utc") or "") > (prev.get("source_mtime_utc") or ""):
                per_pol[p] = c
        if len(per_pol) < 2:
            continue  # after boundary filter it's no longer a real disagreement
        exemplars = sorted(per_pol.values(), key=lambda c: c.get("source_mtime_utc") or "", reverse=True)
        fresh = max((c.get("source_mtime_utc") or "") for c in exemplars)
        forks.append({"sig": sig, "exemplars": exemplars, "fresh": fresh, "n_raw": len(items)})
    forks.sort(key=lambda f: f["fresh"], reverse=True)
    return forks


def load_main_line(slug):
    f = MAIN_LINES_DIR / f"{slug}.md"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    return None


def render_page(topic, gov, boundary, timeline, n_src, main_line):
    tid, title = topic["id"], topic["title"]
    cur = dedup_near(gov["current_authority"])
    forks = real_forks(gov["conflicting"])
    out = [f"# {title}", "",
           "> Живая статья · темы по СМЫСЛУ (TOPIC_MAP_V1) · newest source wins · каждый пункт → сырьё `path#Lnn`.",
           f"> Тема собрана из {n_src} источников. Deterministic, no-LLM. main_line — авторский слой смысла.", ""]
    out += ["## Что это", topic["summary"], ""]

    if main_line:
        out += ["## Основная линия (authored — человеческий смысл)", "", main_line, ""]

    if cur:
        out += [f"## Текущая истина ({len(cur)})"]
        for c in cur[:PAGE_CURRENT_CAP]:
            out.append(f"- {c['text']}  \n  ↳ {c['link']['md_link']}")
        if len(cur) > PAGE_CURRENT_CAP:
            out.append(f"- _…ещё {len(cur) - PAGE_CURRENT_CAP} (см. сырьё)_")
        out.append("")

    if forks:
        raw_total = sum(f["n_raw"] for f in forks)
        out += [f"## Реальные развилки / открытое ({len(forks)})",
                f"> Авто-детект: один набор сущностей с противоположной полярностью. "
                f"Сгруппировано в {len(forks)} развилок из {raw_total} спорных упоминаний; показан свежий образец "
                f"каждой стороны. Кураторские развилки — в основной линии выше."]
        for f in forks[:PAGE_FORK_CAP]:
            names = ", ".join(sorted(f["sig"])) or "—"
            out.append(f"- **[{names}]** · {f['n_raw']} упоминаний:")
            for c in f["exemplars"][:2]:
                pol = c.get("polarity") or "?"
                out.append(f"    - _({pol})_ {c['text']}  \n      ↳ {c['link']['md_link']}")
        if len(forks) > PAGE_FORK_CAP:
            out.append(f"- _…ещё {len(forks) - PAGE_FORK_CAP} развилок_")
        out.append("")

    if boundary:
        bsamples = dedup_near(boundary)[:BOUNDARY_SAMPLE_CAP]
        out += [f"## Историческая граница (boilerplate, схлопнуто из {len(boundary)})",
                "> Повторяющийся proof-boundary шаблон («does not birth Entity/ANNA / no daemon / no AGI…»). "
                "Это историческая граница ДО постройки, не сегодняшняя тема. Показаны образцы:"]
        for c in bsamples:
            out.append(f"- {c['text']}  \n  ↳ {c['link']['md_link']}")
        out.append("")

    if timeline:
        seen = {}
        for d in sorted(timeline, key=lambda x: x["date"]):
            seen.setdefault(d["date"], d)
        tl = list(seen.values())
        out += [f"## Хронология ({len(tl)})"]
        for d in tl[:50]:
            out.append(f"- **{d['date']}** — {d['event']}  \n  ↳ `{d['ref']}`")
        out.append("")

    out += [f"## Источников использовано: {n_src}", ""]
    return "\n".join(out)


def main():
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "pages").mkdir(exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    topics, ent2topic, rank = load_taxonomy()
    records = discover()
    by_topic, cache_hits, junk_dropped = collect(records, topics, ent2topic, rank)

    proof = {"id": "SOCC_MEMORY_SPINE_V2", "built_at": _now(),
             "sources_scanned": len(records), "cache_hits": cache_hits,
             "junk_dropped": junk_dropped,
             "topics": {}, "by": "meaning (TOPIC_MAP_V1)",
             "truth_boundary": ("Meaning-based spine build. Writes only under SOVEREIGN/WIKI/spine2/ + .cache_v2/. "
                                "Atomic writes. No v1 spine, route authority, proof chain, network, daemon. no-LLM.")}

    index = ["# SOCC Memory Spine v2 — темы по СМЫСЛУ", "",
             f"_Собрано {proof['built_at']} из {len(records)} источников (cache hits: {cache_hits}). Deterministic, no-LLM._", "",
             "Темы делятся по смыслу (TOPIC_MAP_V1), а не по частоте слов. Boilerplate-границы схлопнуты.", "",
             "| Тема | Текущая истина | Развилки | Граница (схлопнуто) | Хронология | Источников | authored |",
             "|---|---|---|---|---|---|---|"]
    pack = ["# SOCC — CONTEXT PACK v2 (по смыслу, auto-generated)", "",
            "> Собирается из текущей истины твоих файлов по смысловой таксономии. Не редактируй руками — перезапусти spine v2.",
            f"> Собрано: {proof['built_at']} · источников: {len(records)}", ""]

    for t in topics:
        b = by_topic[t["id"]]
        gov = governance.classify(b["claims"])
        n_src = len(b["src"])
        main_line = load_main_line(t.get("main_line") or t["id"])

        page = render_page(t, gov, b["boundary"], b["dates"], n_src, main_line)
        write_atomic(OUT_DIR / "pages" / f"{t['id']}.md", page)

        cur_n = len(dedup_near(gov["current_authority"]))
        fork_n = len(real_forks(gov["conflicting"]))
        seen_dates = {d["date"] for d in b["dates"]}
        proof["topics"][t["id"]] = {"title": t["title"], "current": cur_n, "forks": fork_n,
                                    "boundary_collapsed": len(b["boundary"]), "timeline": len(seen_dates),
                                    "sources": n_src, "main_line_authored": bool(main_line)}
        index.append(f"| [{t['title']}](pages/{t['id']}.md) | {cur_n} | {fork_n} | {len(b['boundary'])} | "
                     f"{len(seen_dates)} | {n_src} | {'✅' if main_line else '—'} |")

        pack += [f"## {t['title']}", t["summary"]]
        if main_line:
            pack += ["", main_line, ""]
        else:
            for c in dedup_near(gov["current_authority"])[:PACK_CLAIM_CAP]:
                pack.append(f"- {c['text']}")
            pack.append("")

    write_atomic(OUT_DIR / "INDEX.md", "\n".join(index) + "\n")
    write_atomic(OUT_DIR / "CONTEXT_PACK.md", "\n".join(pack) + "\n")
    write_atomic(OUT_DIR / "_spine2_proof.json", json.dumps(proof, ensure_ascii=False, indent=2))

    # one command rebuilds everything: self-model mirror + dashboard (best effort)
    import subprocess
    for helper in ("socc_self_model_v1.py", "socc_self_evolve_v1.py", "socc_memory_dashboard_v2.py"):
        hp = ROOT / "scripts" / "socc" / helper
        if hp.exists():
            subprocess.run([sys.executable, str(hp)], capture_output=True, text=True)

    dt = time.time() - t0
    print("SOCC MEMORY SPINE v2 — BUILT (meaning-based)")
    print(f"  sources scanned : {len(records)}  ·  cache hits: {cache_hits}  ·  time: {dt:.1f}s")
    print(f"  junk dropped    : {junk_dropped} (code/tool-output/UI lines, not knowledge)")
    print(f"  topics (by meaning): {len(proof['topics'])}")
    print(f"  output          : {OUT_DIR}")
    print("  topics:")
    for tid, st in proof["topics"].items():
        print(f"    {st['title'][:46]:46} current={st['current']:3}  forks={st['forks']:3}  "
              f"boundary_collapsed={st['boundary_collapsed']:4}  authored={'Y' if st['main_line_authored'] else '-'}")


if __name__ == "__main__":
    main()

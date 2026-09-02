"""Wiki article assembler.

Turns governed claims + timeline + source registry into a per-topic article
(markdown + json). The markdown carries hyperlinks (`path#Lnn`) back to every
source line so a reader can jump to the original context.

The deterministic builder fills: definition candidates, governed claim buckets,
timeline, idea branches, conflicting/open, source index. The worked-out
`main_line` prose is authored separately (by the operator/Claude for the pilot,
by an LLM layer when scaled) and injected via `main_line_md` if present.
"""

from collections import defaultdict


def build_topic_article(topic, core_entities, ingest_dir, canon_connectors=()):
    """Generic deterministic article builder reused across topics (entity_substrate, anna…).

    Selects claims that mention any core entity OR come from a canon connector,
    governs by freshness, builds timeline + branches + source index. Returns
    (article_json_parts, governed, timeline, branches, source_links, definition).
    Pure: no IO side effects beyond reading ingested files via the passed loader.
    """
    import glob
    import json
    from pathlib import Path
    from knowledge_substrate.anchors import source_link_record
    from knowledge_substrate import governance

    def _read(f):
        try:
            return json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            return {}

    core_set = set(core_entities)
    records = [_read(f) for f in sorted(glob.glob(str(Path(ingest_dir) / "*.json")))]
    records = [r for r in records if r]

    claims, source_usage, date_events = [], {}, []
    for r in records:
        is_canon = r.get("connector") in canon_connectors
        sha16, abs_path = r.get("source_sha16"), r.get("abs_path")
        name = Path(abs_path).name if abs_path else sha16
        used = 0
        for c in r.get("claims", []):
            if not (is_canon or core_set & set(c.get("entities", []))):
                continue
            link = source_link_record(sha16, abs_path, c["line"])
            claims.append({
                "text": c["text"], "entities": c["entities"], "polarity": c["polarity"],
                "intent": c["intent"], "source_mtime_utc": r.get("source_mtime_utc"),
                "source_provenance": r.get("source_provenance"), "link": link,
            })
            used += 1
        core_pattern = any(r.get("entity_counts", {}).get(e, 0) >= 3 for e in core_set)
        if is_canon or core_pattern:
            for d in r.get("dates", []):
                if "2026-01-01" <= d["value"] <= "2027-01-01":
                    date_events.append({"date": d["value"], "text": f"{name}: {d['raw']}",
                                        "link": source_link_record(sha16, abs_path, d["line"])})
        if used:
            source_usage[sha16] = {"name": name, "abs_path": abs_path, "lines_used": used}

    governed = governance.classify(claims)

    seen = {}
    for e in sorted(date_events, key=lambda x: (x["date"], x["link"]["line"])):
        seen.setdefault(e["date"], e)
    timeline = [{"date": e["date"], "event": e["text"][:200],
                 "source": {"sha16": e["link"]["sha16"], "line": e["link"]["line"], "ref": e["link"]["ref"]}}
                for e in seen.values()]
    timeline.sort(key=lambda t: t["date"])

    branches = build_idea_branches(governed["current_authority"] + governed["conflicting"] + governed["historical"])

    primary = core_entities[0] if core_entities else None
    defs = [c for c in governed["current_authority"]
            if primary in c.get("entities", []) and len(c["text"]) > 30]
    definition = {"text": "", "source": {}}
    if defs:
        best = max(defs, key=lambda c: len(c["text"]))
        definition = {"text": best["text"],
                      "source": {"ref": best["link"]["ref"], "md_link": best["link"]["md_link"]}}

    source_links = [{"sha16": k, "name": v["name"], "abs_path": v["abs_path"], "lines_used": v["lines_used"]}
                    for k, v in sorted(source_usage.items(), key=lambda kv: -kv[1]["lines_used"])]

    return governed, timeline, branches, source_links, definition, len(claims)


def _claim_line(c):
    return f"- {c['text']}  \n  ↳ {c['link']['md_link']}  ·  `{c['link']['ref']}`"


def build_timeline(claims):
    """Order dated claims chronologically."""
    dated = [c for c in claims if c.get("date")]
    dated.sort(key=lambda c: c["date"])
    return [
        {
            "date": c["date"],
            "event": c["text"][:200],
            "source": {"sha16": c["link"]["sha16"], "line": c["link"]["line"],
                       "ref": c["link"]["ref"]},
        }
        for c in dated
    ]


def build_idea_branches(claims):
    """Group claims by leading entity to surface forks/branches of thinking."""
    by_entity = defaultdict(list)
    for c in claims:
        lead = c["entities"][0] if c.get("entities") else "general"
        by_entity[lead].append(c)
    branches = []
    for entity, group in sorted(by_entity.items()):
        branches.append({
            "branch": entity,
            "claim_count": len(group),
            "claims": [{"text": g["text"], "status": g.get("status"),
                        "ref": g["link"]["ref"]} for g in group[:30]],
        })
    return branches


def assemble_json(topic, definition, governed, timeline, branches, source_links,
                  main_line_text=None):
    return {
        "id": f"WIKI_{topic.upper()}",
        "topic": topic,
        "freshness_rule": "newest_mtime_wins; in-repo canon ranks current",
        "definition": definition,
        "main_line": {"text": main_line_text or "", "authored": bool(main_line_text)},
        "current_authority": [_c(c) for c in governed["current_authority"]],
        "conflicting": [_c(c) for c in governed["conflicting"]],
        "historical": [_c(c) for c in governed["historical"]],
        "deprecated": [_c(c) for c in governed["deprecated"]],
        "timeline": timeline,
        "idea_branches": branches,
        "source_links": source_links,
        "governance_counts": governed["counts"],
        "llm_used": False,
    }


def _c(c):
    return {
        "text": c["text"],
        "status": c.get("status"),
        "entities": c.get("entities", []),
        "polarity": c.get("polarity"),
        "intent": c.get("intent"),
        "source": {"sha16": c["link"]["sha16"], "line": c["link"]["line"],
                   "ref": c["link"]["ref"], "md_link": c["link"]["md_link"]},
    }


def assemble_md(topic, definition, governed, timeline, branches, source_links,
                main_line_md=None):
    title = topic.replace("_", " ").title()
    out = [f"# {title} — SOCC Wiki", ""]
    out.append("> Живая статья Knowledge Substrate. Newest source wins; in-repo canon = current authority.")
    out.append("> Каждый пункт ссылается на сырой источник (`path#Lnn`). LLM не использовался (deterministic ingest).")
    out.append("")

    out.append("## Определение")
    if definition.get("text"):
        out.append(definition["text"])
        if definition.get("source"):
            out.append(f"  \n↳ `{definition['source'].get('ref','')}`")
    else:
        out.append("_(определение не извлечено)_")
    out.append("")

    if main_line_md:
        out.append("## Основная линия (worked-out main line)")
        out.append(main_line_md.strip())
        out.append("")

    out.append(f"## Current Authority ({governed['counts']['current']})")
    for c in governed["current_authority"][:120]:
        out.append(_claim_line(c))
    out.append("")

    if governed["conflicting"]:
        out.append(f"## Conflicting / Open ({governed['counts']['conflicting']})")
        for c in governed["conflicting"][:60]:
            out.append(_claim_line(c))
        out.append("")

    out.append(f"## Timeline / Evolution ({len(timeline)})")
    for t in timeline[:120]:
        out.append(f"- **{t['date']}** — {t['event']}  \n  ↳ `{t['source']['ref']}`")
    out.append("")

    out.append(f"## Idea Branches ({len(branches)})")
    for b in branches:
        out.append(f"### {b['branch']} ({b['claim_count']})")
        for c in b["claims"][:20]:
            out.append(f"- [{c['status']}] {c['text']}  \n  ↳ `{c['ref']}`")
        out.append("")

    if governed["historical"]:
        out.append(f"## Historical ({governed['counts']['historical']})")
        for c in governed["historical"][:80]:
            out.append(_claim_line(c))
        out.append("")

    if governed["deprecated"]:
        out.append(f"## Deprecated ({governed['counts']['deprecated']})")
        for c in governed["deprecated"][:80]:
            out.append(_claim_line(c))
        out.append("")

    out.append(f"## Source Index ({len(source_links)})")
    out.append("| sha16 | source | lines used |")
    out.append("|---|---|---|")
    for s in source_links:
        out.append(f"| `{s['sha16']}` | [{s['name']}]({s['abs_path']}) | {s['lines_used']} |")
    out.append("")
    return "\n".join(out)

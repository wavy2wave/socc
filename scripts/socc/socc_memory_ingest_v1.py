#!/usr/bin/env python3
"""SOCC Memory Ingest — the workhorse. One command, the whole living-memory loop.

Drop files into the inbox (or sync a Google Drive folder to it), run this once:
  1. ensure the inbox connector folder exists (auto-created)
  2. scan every connector, diff vs the registry  -> было/стало (new/changed/unchanged)
  3. ingest ONLY new/changed files (deterministic, no-LLM) -> ingested/<sha16>.json
  4. update the source registry
  5. rebuild the living wiki (all topics) via the spine
  6. report было->стало per topic (the system now knows more)

Truth boundary (SOCC-lawful): read-only over sources; files never moved/copied.
Writes only under SOVEREIGN/MEMORY and SOVEREIGN/WIKI. Does NOT touch global route
authority / proof chain, births no Entity/ANNA, no daemon/background/network/LLM.
One bounded foreground run, then stop. Re-runnable => living.

Usage:
  python3 scripts/socc/socc_memory_ingest_v1.py
"""

from __future__ import annotations

import glob
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from knowledge_substrate import scanner, parser  # noqa: E402
from knowledge_substrate.io import now_utc, read_json, write_json, h  # noqa: E402

CONN_DIR = ROOT / "SYSTEM" / "CAPABILITIES" / "memory_continuity" / "connectors"
INBOX = ROOT / "SOVEREIGN" / "MEMORY" / "inbox"
REGISTRY = ROOT / "SOVEREIGN" / "MEMORY" / "documents" / "SOURCE_REGISTRY_V1.json"
INGEST_DIR = ROOT / "SOVEREIGN" / "MEMORY" / "documents" / "ingested"
SPINE = ROOT / "scripts" / "socc" / "socc_knowledge_spine_v1.py"
SPINE_PROOF = ROOT / "SOVEREIGN" / "WIKI" / "spine" / "_spine_proof.json"
RUN_REPORT = ROOT / "SOVEREIGN" / "WIKI" / "spine" / "_last_ingest_run.md"

TRUTH = ("SOCC memory ingest. Read-only over sources; files never moved/copied. "
         "Rebuilds wiki under SOVEREIGN/WIKI. Global route authority untouched. "
         "No Entity/ANNA birth, no daemon/background/network/LLM. One bounded run.")


def scan_connectors():
    """Walk every connector root; return source records (read-only)."""
    sources = []
    for cpath in sorted(glob.glob(str(CONN_DIR / "*.json"))):
        conn = read_json(cpath)
        if not conn:
            continue
        if conn.get("file_list"):
            recs, _ = scanner.scan_files(conn["file_list"], conn.get("id"))
        else:
            recs, _ = scanner.scan_root(conn.get("source_root", ""), conn.get("include_suffixes", []),
                                        conn.get("exclude_globs", []), recurse=conn.get("recurse", True))
        for r in recs:
            r["connector"] = conn.get("id")
        sources.extend(recs)
    return sources


def ingest_one(rec):
    """Deterministically parse one source into an ingested record."""
    text = Path(rec["abs_path"]).read_text(encoding="utf-8", errors="replace")
    parsed = parser.parse_text(text)
    out = {
        "id": f"INGESTED_{rec['sha16']}", "source_sha16": rec["sha16"], "abs_path": rec["abs_path"],
        "rel_path": rec.get("rel_path"), "connector": rec.get("connector"),
        "source_provenance": rec.get("provenance"), "source_mtime_utc": rec.get("mtime_utc"),
        "created_at_utc": now_utc(), "parser_version": "memory_ingest_v1_nollm",
        "dates": parsed["dates"], "entities": parsed["entities"], "claims": parsed["claims"],
        "patterns": parsed["patterns"], "intent_markers": parsed["intent_markers"],
        "entity_counts": parsed["entity_counts"], "topics": parsed["topics"], "llm_used": False,
    }
    out["ingest_hash"] = h(out)
    write_json(INGEST_DIR / f"{rec['sha16']}.json", out)
    return len(parsed["claims"])


def main():
    INBOX.mkdir(parents=True, exist_ok=True)
    INGEST_DIR.mkdir(parents=True, exist_ok=True)

    prior = read_json(REGISTRY) or {}
    prior_by_path = {s["abs_path"]: s for s in prior.get("sources", [])}

    sources = scanner.diff_status(scan_connectors(), prior_by_path)
    counts = {
        "total": len(sources),
        "new": sum(1 for s in sources if s["status"] == "new"),
        "changed": sum(1 for s in sources if s["status"] == "changed"),
        "unchanged": sum(1 for s in sources if s["status"] == "unchanged"),
    }

    # ingest only было->стало deltas
    claims_added, new_files = 0, []
    for s in sources:
        if s["status"] in ("new", "changed"):
            claims_added += ingest_one(s)
            new_files.append({"file": Path(s["abs_path"]).name, "status": s["status"],
                              "connector": s.get("connector"), "provenance": s.get("provenance")})

    registry = {"id": "SOURCE_REGISTRY_V1", "created_at_utc": prior.get("created_at_utc", now_utc()),
                "updated_at_utc": now_utc(), "connectors": sorted(glob.glob(str(CONN_DIR / "*.json"))),
                "sources": sources, "counts": counts}
    registry["source_scan_hash"] = h(registry["sources"])
    write_json(REGISTRY, registry)

    # было: snapshot prior wiki proof, then rebuild
    before = read_json(SPINE_PROOF) or {}
    before_topics = before.get("topics", {})
    spine = subprocess.run([sys.executable, str(SPINE)], capture_output=True, text=True)
    after = read_json(SPINE_PROOF) or {}
    after_topics = after.get("topics", {})

    # было->стало per topic
    deltas = []
    for topic, st in sorted(after_topics.items(), key=lambda kv: -kv[1]["current"]):
        b = before_topics.get(topic, {})
        dc = st["current"] - b.get("current", 0)
        ds = st["sources"] - b.get("sources", 0)
        deltas.append({"topic": topic, "current": st["current"], "d_current": dc,
                       "sources": st["sources"], "d_sources": ds})

    report = ["# SOCC Memory Ingest — последний прогон", "", f"_{now_utc()}_", "",
              f"## Было / Стало (источники)",
              f"- всего: {counts['total']}  ·  **новых: {counts['new']}**  ·  **изменённых: {counts['changed']}**  ·  без изменений: {counts['unchanged']}",
              f"- разобрано claims из новых/изменённых: {claims_added}", ""]
    if new_files:
        report += ["### Новые/изменённые файлы"]
        report += [f"- [{f['status']}] {f['file']}  ·  `{f['connector']}`  ·  {f['provenance']}" for f in new_files[:50]]
        report.append("")
    report += ["## Было → Стало по темам (знание системы)", "", "| Тема | Current | Δ | Sources | Δ |", "|---|---|---|---|---|"]
    for d in deltas:
        mark = lambda x: (f"+{x}" if x > 0 else str(x))
        report.append(f"| {d['topic']} | {d['current']} | {mark(d['d_current'])} | {d['sources']} | {mark(d['d_sources'])} |")
    report.append("")
    RUN_REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    write_json(RUN_REPORT.with_suffix(".json"),
               {"built_at": now_utc(), "counts": counts, "claims_added": claims_added,
                "new_files": new_files, "deltas": deltas})

    # refresh the static dashboard (no server, no daemon) — best effort
    dash = ROOT / "scripts" / "socc" / "socc_memory_dashboard_v1.py"
    if dash.exists():
        subprocess.run([sys.executable, str(dash)], capture_output=True, text=True)

    # human print
    print("SOCC MEMORY INGEST — DONE")
    print(f"  inbox            : {INBOX}")
    print(f"  было/стало       : total={counts['total']}  NEW={counts['new']}  CHANGED={counts['changed']}  unchanged={counts['unchanged']}")
    print(f"  claims из новых  : {claims_added}")
    print(f"  wiki rebuild     : {'OK' if spine.returncode == 0 else 'FAIL'}")
    grew = [d for d in deltas if d["d_current"] or d["d_sources"]]
    if grew:
        print("  знание выросло (было→стало):")
        for d in grew[:12]:
            print(f"    {d['topic']:24} current {d['current']-d['d_current']:>4}→{d['current']:<4} (Δ{d['d_current']:+})  sources Δ{d['d_sources']:+}")
    else:
        print("  знание без изменений (нет новых файлов с новыми claims)")
    print(f"  отчёт            : {RUN_REPORT}")
    print(f"  TRUTH_BOUNDARY   : {TRUTH}")


if __name__ == "__main__":
    main()

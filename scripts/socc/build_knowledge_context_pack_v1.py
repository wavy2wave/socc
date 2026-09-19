#!/usr/bin/env python3
"""Knowledge Substrate bridge — Build Context Pack.

The connective tissue between the Knowledge Substrate (memory/wiki) and the
continuous self-construction organ. Before SOCC builds anything on a topic, it
reads ONE dense pack instead of re-reading raw sources:

  definition + main_line  -> what to build and why
  current_authority       -> build aligned to the accepted line
  do_not / deprecated     -> never rebuild known-stale ideas ("не строй хуйню")
  open_questions          -> conflicting items that must be resolved first
  next_lawful_step        -> where to move lawfully
  source_anchors          -> drill into raw context only when truly needed

Token-economical by design: caps each section and emits a compact md+json.
Read-only over the article. No global route change. No LLM. No daemon.

Usage: build_knowledge_context_pack_v1.py [--topic entity_substrate] [--max N]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))

from knowledge_substrate.io import now_utc, now_msk, read_json, read_text, write_json, write_text, h, discipline_flags

ROOT = Path(".")
ARTICLE_JSON = ROOT / "SOVEREIGN/WIKI/pages/entity_substrate.json"
MAIN_LINE = ROOT / "SOVEREIGN/WIKI/pages/_entity_substrate_main_line.md"
CANON_ACTIVE = ROOT / "SYSTEM/ENTITY_SUBSTRATE/ACTIVE_ACCEPTED_ENTITY_SUBSTRATE_DIRECTION.json"
PACK_JSON = ROOT / "SOVEREIGN/WIKI/context_packs/entity_substrate_context_pack_v1.json"
PACK_MD = ROOT / "SOVEREIGN/WIKI/context_packs/entity_substrate_context_pack_v1.md"
GRAPH_NODES = ROOT / "SOVEREIGN/WIKI/graph/nodes.json"
GRAPH_EDGES = ROOT / "SOVEREIGN/WIKI/graph/edges.json"
GRAPH_METRICS = ROOT / "SOVEREIGN/WIKI/graph/metrics.json"
PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_CONTEXT_PACK_ENTITY_SUBSTRATE_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/KNOWLEDGE_CONTEXT_PACK_ENTITY_SUBSTRATE_V1_MEMORY.json"

TOPIC = "entity_substrate"
TRUTH = ("Knowledge context pack build only. Compresses the living wiki article into a "
         "token-economical build brief (definition, main line, current authority, do-not, "
         "open questions, next lawful step) for the self-construction organ to consult "
         "before building. Read-only. No global route change. No daemon/network/LLM.")

args = sys.argv[1:]
max_items = 12
if "--max" in args:
    try:
        max_items = int(args[args.index("--max") + 1])
    except (IndexError, ValueError):
        pass


def _dense(claims, n):
    """Dedupe near-identical claims, keep concise distinct lines with one ref each."""
    out, seen = [], set()
    for c in claims:
        text = " ".join(c["text"].split())
        key = text.lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": text[:240], "ref": c.get("source", {}).get("ref", "")})
        if len(out) >= n:
            break
    return out


article = read_json(ARTICLE_JSON)
main_line = read_text(MAIN_LINE).strip()
canon = read_json(CANON_ACTIVE)
next_step = canon.get("next_required_step") or "review_self_building_cycle_2_candidate_v1"

graph_nodes = read_json(GRAPH_NODES) if GRAPH_NODES.exists() else []
graph_edges = read_json(GRAPH_EDGES) if GRAPH_EDGES.exists() else []
graph_metrics = read_json(GRAPH_METRICS) if GRAPH_METRICS.exists() else {}
topic_terms = [TOPIC, "entity", "substrate", "anna", "identity", "memory", "proof"]
graph_related = sorted({
    n.get("id") for n in graph_nodes
    if any(t in str(n.get("id", "")).lower() for t in topic_terms)
})[:40]
graph_context = {
    "source": "SOVEREIGN/WIKI/graph",
    "metrics": graph_metrics,
    "related_nodes": graph_related,
    "note": "graph layer of system memory; use to see connected concepts and avoid duplicate builds",
} if graph_nodes else {
    "source": "SOVEREIGN/WIKI/graph",
    "metrics": {},
    "related_nodes": [],
    "note": "graph layer absent; rebuild from graphify-out before relying on graph context",
}

current = _dense(article.get("current_authority", []), max_items)
deprecated = _dense(article.get("deprecated", []), max_items)
conflicting = _dense(article.get("conflicting", []), max_items)
definition = article.get("definition", {}).get("text", "")

pack = {
    "id": "KNOWLEDGE_CONTEXT_PACK_ENTITY_SUBSTRATE_V1",
    "topic": TOPIC,
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "purpose": "build brief for the self-construction organ; read this instead of raw sources",
    "definition": definition,
    "main_line": main_line,
    "current_authority": current,
    "do_not_rebuild_deprecated": deprecated,
    "open_questions_conflicting": conflicting,
    "next_lawful_step_for_substrate": next_step,
    "drill_down_note": "Open source anchors (article current_authority refs) only when a claim must be verified in raw context.",
    "governance_counts": article.get("governance_counts", {}),
    "token_economy": {
        "raw_sources_bypassed": article.get("governance_counts", {}),
        "pack_caps_per_section": max_items,
        "principle": "read KB of pack, not MB of raw files",
    },
    "graph_context": graph_context,
}
pack["pack_hash"] = h(pack)

checks = {
    "article_present": bool(article),
    "definition_present": bool(definition),
    "main_line_present": bool(main_line),
    "current_authority_present": len(current) > 0,
    "next_step_present": bool(next_step),
    "graph_layer_present": bool(graph_nodes),
    "global_route_untouched": True,
}
hard = [{"code": "CHECK_FAIL", "check": k} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

md = []
md.append("# Build Context Pack — Entity Substrate")
md.append("")
md.append("> Плотный брифинг для органа самостройки. Читай ЭТО вместо сырых файлов.")
md.append("> Цель: строить по принятой линии, не повторять устаревшее, видеть открытые вопросы.")
md.append("")
md.append("## Что строим (definition)")
md.append(definition or "_n/a_")
md.append("")
md.append("## Основная линия")
md.append(main_line or "_n/a_")
md.append("")
md.append(f"## Current Authority — строй по этому ({len(current)})")
for c in current:
    md.append(f"- {c['text']}  \n  ↳ `{c['ref']}`")
md.append("")
md.append(f"## DO NOT — не пересобирай устаревшее ({len(deprecated)})")
for c in deprecated:
    md.append(f"- ⛔ {c['text']}  \n  ↳ `{c['ref']}`")
if not deprecated:
    md.append("- _(пусто)_")
md.append("")
md.append(f"## Открытые вопросы — реши сначала ({len(conflicting)})")
for c in conflicting:
    md.append(f"- ❓ {c['text']}  \n  ↳ `{c['ref']}`")
if not conflicting:
    md.append("- _(пусто)_")
md.append("")
md.append("## Graph Context — системная память")
md.append(f"- граф: `{graph_context['source']}` · узлов: {graph_metrics.get('nodes', 0)} · сообществ: {graph_metrics.get('communities', 0)}")
md.append(f"- связанные узлы ({len(graph_related)}): " + (", ".join(graph_related[:20]) or "—"))
md.append(f"- {graph_context['note']}")
md.append("")
md.append("## Следующий законный шаг для Entity Substrate")
md.append(f"`{next_step}`")
md.append("")

proof = {
    "id": "KNOWLEDGE_CONTEXT_PACK_ENTITY_SUBSTRATE_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": "memory_continuity",
    "step": "build_knowledge_context_pack_v1",
    "pack_json": str(PACK_JSON),
    "pack_md": str(PACK_MD),
    "sections": {"current": len(current), "deprecated": len(deprecated),
                 "conflicting": len(conflicting)},
    "checks": checks,
    "hard_failures": hard,
    "real_next": "consult_pack_before_self_construction_build",
    "truth_boundary": TRUTH,
}
proof.update(discipline_flags())
proof["proof_hash"] = h(proof)

memory = {
    "id": "KNOWLEDGE_CONTEXT_PACK_ENTITY_SUBSTRATE_V1_MEMORY",
    "created_at_utc": now_utc(),
    "status": status,
    "memory_effect": ("Built the Wiki->Builder bridge: a compact context pack the "
                      "self-construction organ reads before building Entity Substrate, "
                      "so it builds the accepted line, skips deprecated, resolves open questions."),
    "proof": str(PROOF),
    "pack_md": str(PACK_MD),
    "truth_boundary": TRUTH,
}

write_json(PACK_JSON, pack)
write_text(PACK_MD, "\n".join(md))
write_json(PROOF, proof)
write_json(MEMORY, memory)

print("KNOWLEDGE CONTEXT PACK :: " + status)
print("PACK_MD::" + str(PACK_MD))
print("CURRENT::" + str(len(current)))
print("DEPRECATED::" + str(len(deprecated)))
print("CONFLICTING::" + str(len(conflicting)))
print("NEXT_LAWFUL_STEP::" + next_step)
print("LLM_USED::False")
print("GLOBAL_ROUTE_TOUCHED::False")
print("TRUTH_BOUNDARY::" + TRUTH)

raise SystemExit(0 if status == "PASS" else 1)

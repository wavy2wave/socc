# Knowledge Substrate Direction V1

STATUS::BUILT_CANDIDATE
DIRECTION_ID::DIRECTION_KNOWLEDGE_SUBSTRATE_V1
CAPABILITY::memory_continuity
NEXT_REQUIRED_STEP::scan_knowledge_sources_v1

## Rule
Knowledge Substrate is the living wiki/memory organ of SOCC. It must be built by bounded
self-construction discipline: read-only ingest, proof per step, dashboard-visible, idempotent,
no daemon/background/network, no LLM at MVP, no entity/ANNA birth, no AGI claim.

## Definition
Knowledge Substrate turns a folder of raw files (dialogues, notes, chat exports) into a living
wiki for the system itself. A connector points at an external source folder. Each file is
registered (hash/mtime/type/provenance), deterministically parsed (dates, named entities,
claims, patterns, intent markers — every hit carries a source line anchor), then synthesized into
per-topic wiki articles that carry: definition, current authority (worked-out main line),
timeline/evolution, all idea branches, conflicting/open items, historical and deprecated claims,
and a source index of hyperlinks back to the raw files. Freshness rule: newest source wins.

This is the SOCC memory organ so that models do not re-read raw files each time — they read the
wiki article and jump to the original line only when needed.

## Required surfaces
- knowledge_source_connector_surface   (points at external source folder, read-only)
- knowledge_source_registry_surface     (all sources: hash, mtime, type, provenance, status)
- knowledge_ingest_surface              (deterministic parsed memory per source)
- knowledge_governance_surface          (CURRENT_AUTHORITY / HISTORICAL / DEPRECATED / CONFLICTING)
- knowledge_wiki_article_surface        (living per-topic article with source hyperlinks)
- knowledge_timeline_surface            (chronology/evolution of a topic)
- knowledge_index_surface               (article index)
- knowledge_dashboard_surface           (operator-visible panel)
- knowledge_proof_chain_surface         (proof per step)
- knowledge_freeze_review_stop_surface  (bounded stop, no daemon)

## Organ-local chain (does NOT touch global CURRENT_ROUTE_AUTHORITY)
- scan_knowledge_sources_v1
- ingest_knowledge_sources_v1
- build_wiki_article_entity_substrate_v1
- validate_knowledge_substrate_v1
- review_knowledge_substrate_v1

## Pilot
Topic = entity_substrate. Produce one reference wiki article that gives the system a complete
representation of Entity Substrate, with the worked-out main line and hyperlinks to every source.

## Boundary
Organ build + pilot article only. Read-only over external sources (files never moved/copied).
Global route authority is not modified by this organ; it advances its own ACTIVE pointer.
No daemon/background/network/LLM/entity-birth/AGI claim.

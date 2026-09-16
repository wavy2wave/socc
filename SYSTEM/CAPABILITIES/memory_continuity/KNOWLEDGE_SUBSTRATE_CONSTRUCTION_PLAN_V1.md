# Knowledge Substrate Construction Plan V1

STATUS::BUILT_PENDING_RUN
NEXT_REQUIRED_STEP::scan_knowledge_sources_v1
CAPABILITY::memory_continuity

## Mission
Construct the Knowledge Substrate organ (living wiki/memory) and prove it on a pilot topic
(Entity Substrate): scan sources → ingest deterministically → build wiki article with source
hyperlinks → validate → review. Read-only over external sources; bounded; proof per step.

## Components to construct
- Package `knowledge_substrate/`: io, scanner, parser, anchors, governance, wiki.
- Connectors under `connectors/`: external source folder + in-repo Entity Substrate canon.
- Route scripts in `scripts/socc/`: scan, ingest, build_wiki_article_entity_substrate,
  validate, review, observe.
- Data homes: `SOVEREIGN/MEMORY/documents/` (registry + ingested), `SOVEREIGN/WIKI/`
  (pages/evolution/indexes), `SOVEREIGN/PROOF/proof_chain/`, `MEMORY_WAVE/reports/autonomy/`,
  `SYSTEM/DASHBOARD/`.

## Mandatory rules
- read_only_source_ingest: True
- no_copy_no_move_of_sources: True
- deterministic_no_llm_at_mvp: True
- source_line_anchors_required: True
- freshness_newest_wins: True
- idempotent_rerun_required: True
- dashboard_visible: True
- proof_chain_required: True
- memory_required: True
- bounded_stop_required: True
- does_not_modify_global_route_authority: True
- no_daemon: True
- no_background: True
- no_network: True
- no_agi_claim: True
- no_entity_birth: True
- no_anna_birth: True

## Boundary
Organ + pilot article only. Entity Substrate itself is NOT built here; ANNA is NOT born here.
Global CURRENT_ROUTE_AUTHORITY is not modified. No daemon/background/network/LLM.

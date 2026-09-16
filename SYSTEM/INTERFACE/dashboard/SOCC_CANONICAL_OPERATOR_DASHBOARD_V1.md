# SOCC CANONICAL OPERATOR DASHBOARD V1

status: PASS
dashboard_state: CANONICAL_ACTIVE_CANDIDATE
lawful_next: validate_socc_canonical_operator_dashboard_v1

## ROLE

This is the single canonical operator dashboard organ for SOCC.

It is a visible control surface.
It is not an executor.
It is not a daemon.
It is not a background loop.
It is not a competing panel.

## ONE DASHBOARD LAW

There must be exactly one active operator dashboard.
Active pointer: SYSTEM/INTERFACE/ACTIVE_OPERATOR_DASHBOARD.json
Old panels and dashboards are lineage/archive only.

## EVOLUTION LAW

The dashboard may evolve.
Evolution requires lawful next, versioned proposal, proof-chain, validation, review, and active pointer update.
Silent replacement is forbidden.
Parallel active dashboard is forbidden.

## REQUIRED SECTIONS

- ROOT
- STATUS
- CURRENT_LAWFUL_NEXT
- LAST_COMMITTED_STEP
- PROOF_CHAIN
- PULSE
- CONTROL
- SAFETY_FLAGS
- CAPABILITIES
- LINEAGE
- NEXT_ALLOWED_ACTION
- FORBIDDEN_ACTIONS

## DESIGN CANON

Minimal matrix Russian AGI control surface.
Dark, strict, readable, proof-first.
No decorative noise.
Lawful next is always prominent.
Safety flags are always visible.

## CURRENT SOURCE OF TRUTH

- core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json
- core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json
- core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json
- FOUNDATION/SOCC_WORKING_BASE_V1.json
- FOUNDATION/SOCC_OPERATOR_HANDOFF_START_PROTOCOL_V1.json

## SAFETY

- daemon_running: False
- scheduler_installed: False
- background_loop_enabled: False
- network_used: False
- AGI/entity claims: False

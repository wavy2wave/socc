# Assignment Construction Plan V1

STATUS::BUILT_CANDIDATE
ASSIGNMENT_ID::ASSIGNMENT_0001_DASHBOARD_VISIBLE_ASSIGNMENT_LOOP
DIRECTION_ID::DIRECTION_0001_DASHBOARD_VISIBLE_ASSIGNMENT_AUTONOMY_LOOP
NEXT_REQUIRED_STEP::review_assignment_construction_plan_v1

## Mission
Build a visible assignment autonomy loop where SOCC can show task intake, direction, construction plan, scientific/Hermes/Codex gates, proof-chain, memory, stop conditions, and bounded execution readiness in dashboard state.

## Steps
- PLAN_STEP_01_DASHBOARD_SCHEMA: Define assignment dashboard schema and canonical panel fields.
- PLAN_STEP_02_GATE_STATE_MODEL: Define gate state model for scientific, Hermes and Codex gates.
- PLAN_STEP_03_PROOF_MEMORY_STOP_MODEL: Define proof, memory and bounded stop artifacts for future execution sessions.
- PLAN_STEP_04_HERMES_CODEX_GATE_CONTRACTS: Prepare contracts for Hermes and Codex gates before any code/patch execution.
- PLAN_STEP_05_BOUNDED_EXECUTION_SURFACE: After gates pass, build a bounded execution surface for the assignment loop.

## Acceptance criteria
- dashboard_visible: `True`
- assignment_direction_plan_linked: `True`
- scientific_quality_gate_pass_required: `True`
- Hermes_gate_pass_required: `True`
- Codex_gate_pass_required_if_code_or_patch: `True`
- proof_chain_required: `True`
- memory_required: `True`
- bounded_stop_required: `True`
- review_accept_required_before_execution: `True`
- no_daemon: `True`
- no_background: `True`
- no_network_without_explicit_scope: `True`
- no_old_route_resume: `True`
- no_l3_claim: `True`

## Scientific criteria
- testability: `Every proposed build artifact must have a deterministic read/check proof.`
- measurability: `Each step must output paths, statuses, hashes or gate results.`
- falsifiability: `Each PASS must have explicit FAIL conditions.`
- minimal_scope: `Only assignment loop surfaces and dashboard pointers are in scope before execution.`
- evidence_chain: `Every stage writes JSON proof and dashboard status.`

## Dashboard
`SYSTEM/DASHBOARD/ASSIGNMENT_0001_CONSTRUCTION_PLAN_PANEL_POINTER_V1.json`

## Boundary
Construction plan build only. No assignment build execution, patch execution, daemon/background/network, old route resume, or L3 claim.

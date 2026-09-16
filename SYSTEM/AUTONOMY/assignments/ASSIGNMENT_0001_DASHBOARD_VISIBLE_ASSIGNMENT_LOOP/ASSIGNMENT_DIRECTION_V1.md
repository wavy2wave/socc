# Assignment Direction V1

STATUS::BUILT_CANDIDATE
ASSIGNMENT_ID::ASSIGNMENT_0001_DASHBOARD_VISIBLE_ASSIGNMENT_LOOP
DIRECTION_ID::DIRECTION_0001_DASHBOARD_VISIBLE_ASSIGNMENT_AUTONOMY_LOOP
NEXT_REQUIRED_STEP::review_assignment_direction_v1

## Direction
Dashboard-visible assignment autonomy loop with scientific, Hermes and Codex gates

## Why
- Operator wants working autonomy on a concrete task, not abstract proof only.
- SOCC must transform task text into a lawful direction and later into construction plan.
- Dashboard visibility is required so operator can inspect assignment, gates, proofs, progress and lawful next.
- Hermes/Codex/scientific quality gates are mandatory before any build execution.

## Contract
- assignment_intake_required: `True`
- construction_plan_required_next: `True`
- scientific_quality_gate_required: `True`
- hermes_gate_required: `True`
- codex_gate_required_if_code_or_patch: `True`
- dashboard_visibility_required: `True`
- proof_chain_required: `True`
- memory_required: `True`
- bounded_stop_required: `True`
- review_accept_required_before_execution: `True`
- no_daemon: `True`
- no_background: `True`
- no_network_without_explicit_lawful_scope: `True`
- no_old_route_resume: `True`
- no_l3_claim: `True`

## Dashboard
`SYSTEM/DASHBOARD/ASSIGNMENT_0001_DIRECTION_PANEL_POINTER_V1.json`

## Boundary
Direction build only. No construction plan execution, no patch execution, no daemon/background/network, no old route resume, no L3 claim.

# Assignment Direction Autonomy Surface V1

STATUS::BUILT_CANDIDATE
NEXT_REQUIRED_STEP::review_assignment_direction_autonomy_surface_v1

## Purpose
Allow SOCC to accept an operator assignment as a lawful object, create a direction, derive a build plan, pass mandatory gates, and expose execution through dashboard-visible state.

## Assignment lifecycle
- assignment_intake: Operator submits a task as a lawful assignment object.
- direction_creation: SOCC creates a direction/research-build lane from the assignment.
- build_plan_generation: SOCC generates a construction plan before any execution.
- scientific_quality_gate: Plan must pass scientific/engineering quality criteria before build.
- hermes_gate: Hermes quality/law/reasoning review must approve the plan where Hermes capability is available.
- codex_gate: Codex/code-quality review must approve patches/scripts where code is involved.
- review_accept_execute: Only after build plan, scientific gate, Hermes gate, Codex gate, review and acceptance may SOCC run a bounded assignment build session.

## Mandatory filters before build
- route_authority_preflight: `True`
- assignment_object_required: `True`
- direction_required: `True`
- build_plan_required: `True`
- scientific_quality_gate_required: `True`
- hermes_gate_required_if_capability_present: `True`
- codex_gate_required_if_code_or_patch_present: `True`
- operator_dashboard_visibility_required: `True`
- proof_chain_required: `True`
- memory_required: `True`
- bounded_stop_required: `True`
- review_accept_required_before_execution: `True`
- no_daemon: `True`
- no_background: `True`
- no_network_without_explicit_lawful_scope: `True`
- no_old_route_resume: `True`
- no_l3_claim: `True`

## Dashboard visibility
- pointer: `SYSTEM/DASHBOARD/ACTIVE_ASSIGNMENT_DIRECTION_PANEL_POINTER_V1.json`
- must show: `assignment_id`
- must show: `direction_id`
- must show: `current_stage`
- must show: `lawful_next`
- must show: `blocked_reason_if_any`
- must show: `gates_status`
- must show: `Hermes status`
- must show: `Codex status`
- must show: `proof artifacts`
- must show: `memory artifacts`
- must show: `what changed`
- must show: `what remains`
- must show: `operator-visible next action`

## Future frontiers
- `review_assignment_direction_autonomy_surface_v1`
- `accept_assignment_direction_autonomy_surface_v1`
- `build_assignment_intake_object_v1`
- `review_assignment_intake_object_v1`
- `accept_assignment_intake_object_v1`
- `build_assignment_direction_v1`
- `review_assignment_direction_v1`
- `accept_assignment_direction_v1`
- `build_assignment_construction_plan_v1`
- `run_assignment_scientific_quality_gate_v1`
- `run_assignment_hermes_gate_v1`
- `run_assignment_codex_gate_v1`
- `review_assignment_build_plan_and_gates_v1`
- `accept_assignment_build_plan_and_gates_v1`
- `build_assignment_bounded_execution_surface_v1`

## Boundary
This surface enables assignment-direction autonomy as a lawful control surface. It does not run an assignment, execute patches, start daemon/background/network, or claim L3.

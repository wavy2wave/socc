# Assignment Intake Object V1

STATUS::BUILT_CANDIDATE
ASSIGNMENT_ID::ASSIGNMENT_0001_DASHBOARD_VISIBLE_ASSIGNMENT_LOOP
NEXT_REQUIRED_STEP::review_assignment_intake_object_v1

## Assignment text
Build a working dashboard-visible assignment autonomy loop. SOCC must take an operator task, create a direction, generate a construction plan, run scientific quality filters, Hermes review gate, Codex code/patch quality gate, collect proof/memory/stop evidence, and expose the task/direction/progress in dashboard state. No daemon/background/network autonomy. No old route resume. No execution before review/accept gates.

## Scope allowed
- create assignment object
- create direction
- create construction plan
- define scientific quality criteria
- prepare Hermes gate contract
- prepare Codex gate contract
- create dashboard-visible pointers
- create proof/memory/stop requirements

## Not allowed yet
- execute build patches
- start daemon
- background loop
- network autonomy
- resume old route
- skip gates
- claim L3/AGI

## Initial gates
- route_authority: `PASS`
- assignment_object: `BUILT_CANDIDATE`
- direction: `not_built_yet`
- construction_plan: `not_built_yet`
- scientific_quality_gate: `required_not_run_yet`
- Hermes_gate: `required_not_run_yet`
- Codex_gate: `required_not_run_yet`
- dashboard_visibility: `candidate_pointer_written`
- proof: `pending_this_build_proof`
- memory: `pending_future_assignment_memory`
- stop: `required_before_execution`

## Dashboard
`SYSTEM/DASHBOARD/ASSIGNMENT_0001_PANEL_POINTER_V1.json`

## Boundary
Assignment intake object only. No assignment build execution, no patch execution, no daemon/background/network, no old route resume, no L3 claim.

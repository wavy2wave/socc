# Assignment Bounded Execution Surface V1

STATUS::BUILT_CANDIDATE
NEXT_REQUIRED_STEP::review_assignment_bounded_execution_surface_v1

## Execution scope
- mode: `single_foreground_bounded_execution_session`
- max_sessions: `1`
- max_ticks: `1`
- must_stop_after_run: `True`
- operator_foreground_only: `True`
- daemon_allowed: `False`
- background_allowed: `False`
- network_allowed: `False`
- old_route_resume_allowed: `False`
- mw_route_allowed: `False`
- agi_claim_allowed: `False`
- l3_claim_allowed: `False`

## Runtime artifacts
- `SYSTEM/DASHBOARD/ASSIGNMENT_0001_RUNTIME_PANEL_V1.json`: Operator-visible runtime panel showing assignment, direction, current stage, gates, proof, memory, stop and next.
- `SYSTEM/AUTONOMY/assignments/ASSIGNMENT_0001_DASHBOARD_VISIBLE_ASSIGNMENT_LOOP/RUNTIME/ASSIGNMENT_RUNTIME_STATE_V1.json`: Machine-readable runtime state for the assignment loop.
- `MEMORY_WAVE/reports/assignments/ASSIGNMENT_0001_RUNTIME_MEMORY_V1.json`: Memory record that bounded execution occurred and stopped.
- `SOVEREIGN/PROOF/proof_chain/SOCC_RUN_ASSIGNMENT_BOUNDED_EXECUTION_SESSION_V1_PROOF.json`: Proof that bounded execution wrote expected artifacts and stopped.

## Pass definition
- route authority equals run_assignment_bounded_execution_session_v1
- exactly one bounded foreground session runs
- runtime dashboard panel is written
- runtime assignment state is written
- proof is written
- memory is written
- stop is observed
- no daemon/background/network/old route/MW/L3

## Boundary
Execution surface build only. It authorizes no execution until separate review and acceptance. No daemon/background/network/old route/MW/L3.

# SOCC CANONICAL DASHBOARD VIEW V1

rendered_at_utc: 2026-06-08T20:06:17.427118+00:00

## ROOT

- active_dashboard: `SYSTEM/INTERFACE/dashboard/SOCC_CANONICAL_OPERATOR_DASHBOARD_V1.json`
- dashboard_state: `ACCEPTED_ACTIVE_CANONICAL_DASHBOARD`

## STATUS

- route_status: `PASS`
- pulse_status: `SOCC_CANONICAL_DASHBOARD_RENDERER_REVIEWED`
- control_status: `SOCC_CANONICAL_DASHBOARD_RENDERER_REVIEWED`

## CURRENT_LAWFUL_NEXT

`accept_socc_canonical_dashboard_renderer_v1`

## LAST_COMMITTED_STEP

- route_last: `review_socc_canonical_dashboard_renderer_v1`
- pulse_last: `review_socc_canonical_dashboard_renderer_v1`
- control_last: `review_socc_canonical_dashboard_renderer_v1`

## PROOF_CHAIN

- route_upstream_proof: `SYSTEM/INTERFACE/dashboard/renderers/SOCC_CANONICAL_DASHBOARD_RENDERER_REVIEW_V1.json`
- pulse_upstream_proof: `SYSTEM/INTERFACE/dashboard/renderers/SOCC_CANONICAL_DASHBOARD_RENDERER_REVIEW_V1.json`
- control_upstream_proof: `SYSTEM/INTERFACE/dashboard/renderers/SOCC_CANONICAL_DASHBOARD_RENDERER_REVIEW_V1.json`

## SAFETY_FLAGS

- daemon_running: `False`
- scheduler_installed: `False`
- background_loop_enabled: `False`
- network_used: `False`
- agi_claim_allowed: `False`
- entity_birth_allowed: `False`
- anna_birth_allowed: `False`

## ACTIVE_OPERATOR_ORGAN

- active_pointer: `SYSTEM/INTERFACE/ACTIVE_OPERATOR_DASHBOARD.json`
- active_dashboard: `SYSTEM/INTERFACE/dashboard/SOCC_CANONICAL_OPERATOR_DASHBOARD_V1.json`
- renderer: `SYSTEM/INTERFACE/dashboard/renderers/render_socc_dashboard_v1.py`

## FORBIDDEN_ACTIONS

- no daemon
- no background loop
- no network autonomy
- no execution from renderer
- no route mutation from renderer
- no parallel active dashboard

## NEXT_ALLOWED_ACTION

Read CURRENT_LAWFUL_NEXT and execute only through lawful proof-chain.

# SOCC CANONICAL DASHBOARD RENDERER V1

status: PASS
lawful_next: validate_socc_canonical_dashboard_renderer_v1

## ROLE

Read-only renderer for the accepted canonical SOCC dashboard.

It reads:
- ACTIVE_OPERATOR_DASHBOARD.json
- SOCC_CANONICAL_OPERATOR_DASHBOARD_V1.json
- CURRENT_ROUTE_AUTHORITY.json
- AUTONOMY_PULSE_V1.json
- CONTROL_PANEL_STATE_V1.json

It writes:
- SYSTEM/INTERFACE/dashboard/SOCC_CANONICAL_DASHBOARD_VIEW_V1.md

## FORBIDDEN

- no execution
- no route mutation
- no daemon
- no background loop
- no network
- no second dashboard

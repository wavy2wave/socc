# SOCC Language Dashboard Binding View V1

STATUS::BUILT_CANDIDATE
MODE::READ_ONLY_CREATOR_DIALOGUE_SURFACE_BINDING
CAPABILITY::SOCC_CAN_SHOW_CANONICAL_LANGUAGE_ORGAN_INSIDE_DASHBOARD_WITHOUT_EXECUTION

## Active Language
- pointer: SYSTEM/INTERFACE/language/ACTIVE_SOVEREIGN_CORE_LANGUAGE_LAYER.json
- language: SYSTEM/INTERFACE/language/SOCC_SOVEREIGN_CORE_LANGUAGE_LAYER_V1.json
- acceptance: SYSTEM/INTERFACE/language/SOCC_SOVEREIGN_CORE_LANGUAGE_LAYER_ACCEPTANCE_V1.json

## Active Dashboard
- pointer: SYSTEM/INTERFACE/ACTIVE_OPERATOR_DASHBOARD.json
- acceptance: SYSTEM/INTERFACE/dashboard/SOCC_CANONICAL_OPERATOR_DASHBOARD_ACCEPTANCE_V1.json
- renderer_acceptance: SYSTEM/INTERFACE/dashboard/renderers/SOCC_CANONICAL_DASHBOARD_RENDERER_ACCEPTANCE_V1.json

## Route
- core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json: build_socc_language_dashboard_binding_v1
- core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json: build_socc_language_dashboard_binding_v1
- core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json: build_socc_language_dashboard_binding_v1

## Allowed
- display language status
- display creator dialogue protocol
- display lawful intent protocol
- display proof-chain pointers
- display current_lawful_next
- write this markdown view

## Forbidden
- no language execution
- no route mutation
- no daemon
- no background
- no network
- no MW route
- no second dashboard

NEXT_REQUIRED_STEP::validate_socc_language_dashboard_binding_v1

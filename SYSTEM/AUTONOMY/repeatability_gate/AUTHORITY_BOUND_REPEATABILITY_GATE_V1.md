# Authority Bound Repeatability Gate V1

STATUS::BUILT_CANDIDATE
NEXT_REQUIRED_STEP::review_authority_bound_repeatability_gate_v1

## Purpose
Define the fresh lawful repeatability gate that can prove continuous foreground autonomy without resuming old route and without daemon/background/network.

## Contract
- minimum_future_sessions_for_gate_pass: `2`
- minimum_ticks_per_session: `1`
- maximum_ticks_per_session_before_later_expansion: `3`
- route_authority_required_before_each_tick: `True`
- proof_required_after_each_tick: `True`
- memory_required_after_each_tick: `True`
- validation_required_after_each_tick_or_session: `True`
- review_accept_required_before_claiming_repeatability: `True`
- must_stop_after_each_session: `True`
- fresh_route_only: `True`
- old_route_resume_allowed: `False`
- daemon_allowed: `False`
- background_allowed: `False`
- network_allowed: `False`
- mw_route_allowed: `False`
- agi_claim_allowed: `False`
- l3_claim_allowed: `False`

## Pass definition
- all authority files agree before run
- every tick/session has PASS proof
- every tick/session has memory
- no daemon/background/network was used
- no old route was resumed
- route advances through validation/review/accept only
- bounded stop is observed

## Not pass if
- PASS appears only as text without proof
- route differs across authority files
- tick/session runs outside accepted gate
- old route is used as current
- daemon/background/network starts
- no stop condition is proven

## Autonomy distance
- first_foreground_tick: `done_pending_validation`
- repeatability_gate: `built_candidate_pending_review`
- continuous_foreground_autonomy: `requires repeatability session plan + bounded sessions + validation/review/accept`
- daemon_or_24_7_autonomy: `not_authorized`

## Boundary
This is a gate contract only. It does not run sessions, does not resume old route, does not start daemon/background/network, and does not claim L3.

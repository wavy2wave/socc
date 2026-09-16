# SOCC Controlled Cycle Visibility Contract Acceptance V1

STATUS::ACCEPTED
CAPABILITY::SOCC_HAS_ACCEPTED_CONTROLLED_CYCLE_VISIBILITY_CONTRACT
CONTRACT::SYSTEM/CYCLE/visibility_contract/SOCC_CONTROLLED_CYCLE_VISIBILITY_CONTRACT_V1.json
ACTIVE_ACCEPTED_CONTRACT::SYSTEM/CYCLE/visibility_contract/ACTIVE_ACCEPTED_CONTROLLED_CYCLE_VISIBILITY_CONTRACT.json
NEXT_REQUIRED_STEP::build_socc_first_controlled_cycle_packet_v1

## Required future cycle visibility chain
- current
- decision
- boundary
- proof
- result
- next

## Autonomy distance
- first controlled cycle packet: next
- first foreground tick: approximately 1-4 lawful steps
- continuous daemon autonomy: not authorized

## Boundary
Accepted visibility contract authorizes building the first controlled cycle packet only. It does not execute cycles or authorize daemon/background/network autonomy.

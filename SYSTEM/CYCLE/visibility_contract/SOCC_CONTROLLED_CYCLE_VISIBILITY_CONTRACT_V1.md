# SOCC Controlled Cycle Visibility Contract V1

STATUS::BUILT_CANDIDATE
TYPE::CONTROLLED_CYCLE_VISIBILITY_ONLY
CAPABILITY::SOCC_CAN_DEFINE_VISIBLE_PROOF_BOUND_CONTROLLED_CYCLE_OUTPUT

## Every future controlled cycle must show
- observed current_lawful_next before cycle
- selected bounded step
- decision reason
- allowed boundary
- forbidden actions
- expected artifact delta
- required proof
- result summary
- hard failures if any
- next_lawful_step after cycle

## Autonomy distance
- controlled cycle packet: near
- first foreground autonomous tick: approximately 4-7 lawful steps
- continuous daemon autonomy: not authorized

## Forbidden
- no cycle execution
- no code execution
- no language execution
- no route mutation outside lawful transition
- no daemon
- no background
- no network
- no MW route
- no AGI/autonomy launch claim

NEXT_REQUIRED_STEP::validate_socc_controlled_cycle_visibility_contract_v1

## Boundary
This contract only defines visible controlled cycle obligations. It does not execute cycles or authorize daemon/background/network autonomy.

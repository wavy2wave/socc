# Entity/Substrate Continuous Autonomy Requirement V1

STATUS::REQUIRED

## Requirement
Entity/Substrate must be built by continuous lawful self-construction autonomy, not by manual decorative patches.

## Allowed now
- continuous_mode: `foreground_route_bound_runner_only`
- daemon: `False`
- background: `False`
- network: `False`

## Runner must
- read current_lawful_next from route authority
- check old project before every step
- choose only lawful next step
- write lifecycle state: SELECTED -> DOING -> DONE -> CLOSED -> NEXT
- write dashboard refresh artifact every step
- write proof-chain artifact every step
- write memory artifact every step
- stop/freeze on guard failure
- never resume old route directly
- never claim live Entity/Substrate before runtime evidence
- continue Entity/Substrate construction until bounded stop or operator stop

## Runner must not
- start daemon
- run in background
- use network
- skip current_lawful_next
- bypass Hermes/Codex/scientific gates
- build Entity/Substrate by handwave patch
- claim AGI/L3

## Boundary
This is a requirement artifact, not execution. It authorizes a future foreground runner surface only after direction acceptance.

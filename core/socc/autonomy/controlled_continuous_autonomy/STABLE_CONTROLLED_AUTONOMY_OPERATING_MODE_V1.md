
# STABLE CONTROLLED AUTONOMY OPERATING MODE V1

status: PASS  
current_step: build_stable_controlled_autonomy_operating_mode_v1  
lawful_next: validate_stable_controlled_autonomy_operating_mode_v1

## SOCC state

Controlled autonomy path is proven.

- first lawful controlled run: executed / validated / reviewed
- continuity contract: built / validated / reviewed
- operator panel: active
- Codex/Hermes governance: active
- proof-chain: required
- route/pulse/control alignment: required

## Operating rule

SOCC may continue only from `current_lawful_next`.

Default operating shape:

- one lawful bounded step
- proof required
- route/pulse/control atomic update required
- operator panel visible
- Codex/Hermes bounded repair on lawful failure
- stop after step

## Forbidden

- no daemon
- no background loop
- no network autonomy
- no duplicate passed step
- no queue widening without route authority
- no AGI/entity claim

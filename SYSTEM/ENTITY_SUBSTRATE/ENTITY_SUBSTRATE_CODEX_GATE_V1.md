# Entity/Substrate Codex Gate V1

STATUS::SPEC
CURRENT_EXPECTED::run_entity_substrate_codex_gate_v1
NEXT_REQUIRED_STEP::review_entity_substrate_plan_and_gates_v1

## Purpose

The Codex gate is the third and last quality gate before Entity/Substrate is
allowed to build any code or patch execution surface. It does **not** build,
patch, or execute anything. It validates that the plan and the Codex/Hermes
governance contract commit to **bounded code construction under an explicit
lawful target**:

- bounded scope (no unbounded rewrite),
- idempotent / filesystem-safe construction,
- proof output + proof chain,
- a review gate after the work,
- no daemon start, no queue widening without route authority.

## Why a separate gate (role split)

| Gate | Validates | Question |
| --- | --- | --- |
| Scientific | plan structure & required surfaces | "Is the blueprint complete?" |
| Hermes | engineering coherence & safe-fail recovery | "Will the structure hold and repair?" |
| **Codex** | bounded-code/patch execution safety | "Are the hands that build it safe?" |

Order is enforced: `scientific -> hermes -> codex -> review`.

## Pass criteria

All `codex_checks` in `ENTITY_SUBSTRATE_CODEX_GATE_V1.json` must hold. The runner
verifies each one against real file state (upstream proofs, the governance
contract roles, the construction plan, and the route authority files). Any false
check becomes a `hard_failure` and the gate **fails** — there is no fake pass.

## Boundary

Codex gate only. It reviews the bounded-code/patch safety contract for
Entity/Substrate; it does not build Entity/Substrate, write patches, execute
code, or run daemon/background/network.

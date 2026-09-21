# SOCC LIVING CORE MAP V1

> Карта живого ядра SOCC по существующим файлам. Не создаёт новые органы — фиксирует, где что живёт.

## Ядро как контур

```text
state → memory → plan → action → proof → continuity
```

## Слои

| слой | файлы/модули | назначение |
|---|---|---|
| state | `core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json` | маршрут, lawful_next, флаги |
| memory | `SOVEREIGN/WIKI/spine2`, `SOVEREIGN/WIKI/graph`, `SOVEREIGN/WIKI/context_packs` | живая вики, граф, брифы |
| recall | `socc_cli/recall.py` | поиск по памяти |
| brain | `socc_cli/brain.py` | intent, knowledge, readiness, plan, ticket |
| observe | `scripts/socc/socc_observe_v1.py` | системный аудит |
| continuity | `socc_cli/handoff.py`, `FOUNDATION/SOCC_OPERATOR_HANDOFF_START_PROTOCOL_V1.md` | передача состояния |
| surface | `socc_cli/cli.py`, `socc_cli/home.py` | единый интерфейс |
| effect gate | `scripts/socc/socc_self_building_effect_auditor_v1.py` | закон шага: материальный эффект обязателен |
| proof | `SOVEREIGN/PROOF/proof_chain`, гейты | верификация |
| safety | route flags, M2/M3/ПДн гейты | RUBICON |

## Core API

`socc_cli/socc_core.py` — фасад над всеми слоями:

```python
from socc_cli.socc_core import SOCC

socc = SOCC()
socc.state()          # маршрут + флаги
socc.memory()         # wiki/graph/packs
socc.recall("anna")   # поиск
socc.think("задача")  # план с памятью
socc.effect_gate(before, after)  # BEFORE → ACTION → AFTER → proof → memory
socc.observe()        # системный аудит
socc.handoff()        # континуити
socc.gate()           # полный гейт
```

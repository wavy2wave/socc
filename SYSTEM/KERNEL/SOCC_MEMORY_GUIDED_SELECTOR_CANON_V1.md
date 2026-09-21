# SOCC MEMORY GUIDED SELECTOR CANON V1

> Ядро не выбирает следующий шаг «из головы». Оно сначала спрашивает память, достаёт уроки, затем передаёт кандидатов в существующий bounded selector.

## Контур

```text
query
  → recall (wiki + graph)
  → lessons (память о том, что сработало/не сработало)
  → candidates (bounded, evidence_ready)
  → socc_enforced_self_building_next_target_selector_v1.py
  → selected_target
```

## Что делает memory-guided selector

- берёт `recall` по теме;
- собирает `lessons` из существующей памяти (`spine2`, `graph`, `context_packs`);
- строит candidates с `priority`, но не обходит границ;
- передаёт их в существующий enforced selector;
- возвращает `selected_target` + evidence, а не «мнение».

## Границы

- не обходит RUBICON;
- не выбирает network/daemon/entity_birth;
- не создаёт новый орган — это слой над существующим selector;
- не двигает route authority сам.

## Где живёт

- канон — `SYSTEM/KERNEL/SOCC_MEMORY_GUIDED_SELECTOR_CANON_V1.md`;
- модуль — `socc_cli/memory_selector.py`;
- приёмка — `scripts/socc/tests/run_socc_memory_selector.py`;
- вызов — `socc core selector "<тема>"`.

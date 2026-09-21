# SOCC PRODUCT FOUNDATION CANON V1

> SOCC — матка продуктов. Не «ещё один орган», а обязательная база, через которую идея становится проверяемым продуктом.

## Назначение

При подключении новой идеи SOCC сразу отвечает на 9 вопросов:

1. **КОНТЕКСТ** — что уже есть в памяти (`socc recall`);
2. **ЦЕЛЬ** — кто пользователь и какой измеримый результат;
3. **ПОЛЬЗА** — 90% скорости/надёжности/понятности достигается готовыми слоями;
4. **ГРАНИЦА** — что НЕ делаем (`SOCC_GOAL.do_not`, top-level, новые органы);
5. **ЛИНИЯ** — существующие продукты: YM, OZON, ANNA, WAVE SHOP;
6. **ПОВЕРХНОСТЬ** — CLI/UI/README как обязательный вход, не потом;
7. **ГОТОВНОСТЬ** — седьмая дорожка: idea → intent → plan → build → accept → launch → revenue;
8. **ПРОВЕРКА** — гейт, приёмка, truth, effect-gate;
9. **ПОДКЛЮЧЕНИЕ** — handoff новому агенту/сессии.

## Матка продуктов

```text
IDEA
  → socc product start <slug> "<идея>"
  → socc product context <slug>
  → socc product ready <slug>
  → socc product launch <slug>
```

Матка живёт в существующих слоях:

- канон — `SYSTEM/KERNEL`;
- реестр — `SYSTEM/REGISTRY`;
- CLI — `socc_cli/product.py`;
- приёмка — `scripts/socc/tests/run_socc_product_foundation.py`.

## Стадии продукта

| стадия | требование | проверка |
|---|---|---|
| `idea` | slug + intent | реестр создан |
| `intent` | user/outcome/why_now | `socc product context` |
| `plan` | задачи, границы, слои SOCC | `socc product plan` |
| `build` | минимальный артефакт | effect-gate |
| `accept` | приёмка в общем гейте | `make gate` |
| `launch` | README/UI/CLI + live-checklist | `socc product launch` |
| `revenue` | verified ₽ | revenue ledger |

## Правила матки

- продукт не создаёт новый top-level;
- продукт не копирует ядро — подключает его;
- каждый продукт обязан использовать `recall → think → effect_gate`;
- каждый продукт обязан иметь README и CLI/UI-вход до живого запуска;
- каждый живой шаг — RUBICON оператора.

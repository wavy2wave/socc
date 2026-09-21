# SOCC PRODUCT FOUNDATION · Матка продуктов

> SOCC — не «ядро для себя». Это матка: новая идея подключает готовую память, мозг, гейты, инструкции и surface. Продукт получает ~90% скорости не потому, что «агент умный», а потому, что база уже построена и проверяема.

## Быстрый старт

```bash
socc product start <slug> "<идея>"
socc product list
socc product context <slug>
socc product plan <slug>
socc product ready <slug>
socc product launch <slug>
```

## Контур матки

```text
IDEA
  → product start      (registry)
  → product context    (socc recall)
  → product plan       (socc brain)
  → build              (effect_gate)
  → accept             (make gate)
  → launch             (README + CLI/UI + RUBICON)
  → revenue            (verified ₽ в revenue_ledger)
```

## Стадии

| стадия | требование | команда |
|---|---|---|
| idea | slug + intent | `socc product start <slug> "<idea>"` |
| intent | user/outcome/why_now | `socc product context <slug>` |
| plan | задачи, границы, слои SOCC | `socc product plan <slug>` |
| build | минимальный артефакт | effect-gate |
| accept | приёмка в общем гейте | `make gate` |
| launch | README + CLI/UI + live-checklist | `socc product launch <slug>` |
| revenue | verified ₽ | revenue ledger |

## Что матка даёт продукту

| слой SOCC | что получает продукт |
|---|---|
| memory | `socc recall` — что уже было |
| brain | `socc think` — план с контекстом |
| effect gate | `socc core effect` — материальность шага |
| gate | `make gate` — приёмки, M2, ПДн |
| handoff | `socc handoff` — континуити |
| truth | `socc core truth` — конфликты и P0 |
| surface | CLI/UI — человек сразу видит продукт |

## Правила

1. Продукт **не создаёт новый top-level**.
2. Продукт **не копирует ядро** — подключает его.
3. Продукт обязан использовать `recall → think → effect_gate`.
4. Продукт обязан иметь README и CLI/UI-вход до живого запуска.
5. Живой шаг — RUBICON оператора.

## Где живут файлы

- канон — `SYSTEM/KERNEL/SOCC_PRODUCT_FOUNDATION_CANON_V1.md`;
- реестр — `SYSTEM/REGISTRY/SOCC_PRODUCT_FOUNDATION_REGISTRY_V1.jsonl`;
- CLI — `socc_cli/product.py`;
- приёмка — `scripts/socc/tests/run_socc_product_foundation.py`.

## Пример

```bash
socc product start wave-shop "Магазин доступа к ИИ"
socc product context wave-shop
socc product plan wave-shop
socc product ready wave-shop
socc product launch wave-shop
```

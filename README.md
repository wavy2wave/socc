# SOCC · Живое суверенное ядро

> **SOCC — система, которая сама себя строит и ведёт дело.**
> Законно. Автономно. С proof, без fake-pass.

Это не набор скриптов и не «ИИ-бот». Это машина с пятью слоями:
**ядро → фабрика сущностей → продукты → поверхности оператора → память.**

Продукты не копируют ядро — они рождаются через **Entity Substrate**
и работают на нём: YM CYCLE, OZON CYCLE, ANNA.

## Быстрый вход

| кто ты | куда |
|---|---|
| человек/оператор | [START_HERE.md](START_HERE.md) |
| агент/ИИ | [START_HERE_SOCC.md](START_HERE_SOCC.md) |
| хочешь понять устройство | [ARCHITECTURE.md](ARCHITECTURE.md) |
| собрать с нуля | [BOOTSTRAP.md](BOOTSTRAP.md) |
| развернуть на VPS | [DEPLOY.md](DEPLOY.md) |
| цель сейчас | [SOCC_GOAL.json](SOCC_GOAL.json) |

## Карта машины

| путь | что это |
|---|---|
| `SYSTEM/`, `SOVEREIGN/` | фундамент: закон, канон, proof-chain, маршрут |
| `core/`, `scripts/socc/` | живое ядро: state, selector, autonomy, lawful_next |
| `entity_substrate/`, `SYSTEM/ENTITY_SUBSTRATE`, `scripts/entity/` | фабрика рождения сущностей |
| `scripts/mint/arbiter/` | продукты: **YM CYCLE · OZON CYCLE** |
| `SYSTEM/ANNA_MVP/`, `scripts/anna_*` | продукт: **ANNA** |
| `socc_cli/`, `SYSTEM/INTERFACE/`, `SYSTEM/DASHBOARD/` | поверхности оператора: пульт, dashboards |
| `MEMORY_WAVE/`, `SOVEREIGN/MEMORY/` | память: леджеры, опыт, решения |

## Принцип «подводная лодка»

Ошибки возможны. **Незаметных ошибок — нет.**

- отсеки: ядро / фабрика / продукты / данные разделены
- двери: RUBICON, `--dry` по умолчанию, `--commit` только оператором
- затопление: FAIL останавливает цепь, не машину
- эволюция: ошибка → proof → memory → selector

## Движок ЦИКЛ-1 (YM)

```
ДОНОР → СБОРКА → ЗАЛИВ → ВИТРИНА → ОСТАТКИ → СВЕРКА → ПЛАНЁРКА
 0₽GET   локально  write   write    write    READ      самоосознание
```

- **L12:** узел N+1 стартует только после `PASS` узла N.
- **RUBICON:** write-узлы идут в сеть только с `--commit`; иначе dry, 0₽.
- **СВЕРКА:** правда в `campaign_offers`/`stocks`, не в `200 OK`.

## Быстрая проверка машины

```bash
make gate        # переносимость + все приёмки + секреты + ПДн
make pult        # CLI-пульт: где мы, что горит, lawful_next
make dry         # сухой ход ЦИКЛ-1 (нужны .env и stores.json)
```

## Законы репо

- **M2:** секреты — только env.
- **M3:** живое/данные/журналы — вне репо.
- **M4:** каждый шаг = вердикт.
- **M5:** машина в git, живое вне git.

## Текущий фокус

1. Порядок репо: один вход, явные слои.
2. **OZON CYCLE** — следующий продуктовый фокус.
3. ANNA — отдельная линия после порядка.

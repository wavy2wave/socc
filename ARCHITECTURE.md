# SOCC · Архитектура машины

> SOCC — **живое суверенное ядро**: система, которая держит закон, память,
> самостройку и рождает работающие продукты. Не «бот» и не «набор скриптов»,
> а организизм с проверяемым циклом: состояние → выбор → действие → proof →
> память → следующий шаг.

## Главный принцип: подводная лодка

Ошибки возможны. Незаметных ошибок — нет.

- **Отсеки.** Ядро, фабрика сущностей, продукты и данные разделены физически.
- **Двери.** Каждый write закрыт RUBICON: `--dry` по умолчанию, `--commit` только оператором.
- **Контроль затопления.** FAIL останавливает цепь, не топит машину. Причина фиксируется в леджере.
- **Эволюция вместо смерти.** Ошибка становится опытом: proof → memory → selector.

Система не обязана быть идеальной. Она обязана быть **проверяемой и ремонтопригодной**.

## Пять слоёв

```
┌──────────────────────────────────────────────┐
│ 5. SURFACES — фронт оператора                 │
│    CLI-пульт · dashboards · design-canon      │
├──────────────────────────────────────────────┤
│ 4. PRODUCTS — рождённые продукты              │
│    YM CYCLE · OZON CYCLE · ANNA               │
├──────────────────────────────────────────────┤
│ 3. ENTITY SUBSTRATE — фабрика рождения        │
│    identity · state · memory · lineage ·      │
│    capability · law · proof · freeze · product│
├──────────────────────────────────────────────┤
│ 2. LIVING CORE — жизненный контур             │
│    state → selector → critic → bounded        │
│    action → validator → proof → memory → next │
├──────────────────────────────────────────────┤
│ 1. FOUNDATION — закон и доказательства        │
│    KERNEL · GOVERNANCE · route authority ·    │
│    proof-chain · RUBICON · Memory Wave        │
└──────────────────────────────────────────────┘
```

## Карта репозитория

| слой | путь | что там |
|---|---|---|
| Foundation | `SYSTEM/KERNEL`, `SYSTEM/GOVERNANCE`, `SOVEREIGN/PROOF`, `route_authority/` | закон, канон, proof-chain, маршрут |
| Living Core | `core/socc/`, `scripts/socc/`, `SYSTEM/AUTONOMY`, `SOVEREIGN/LAWFUL_NEXT.json` | жизненный цикл: state, selector, lane runner, autonomy |
| Entity Substrate | `entity_substrate/`, `SYSTEM/ENTITY_SUBSTRATE`, `scripts/entity/` | фабрика рождения сущностей, 10 поверхностей, ENTITY FORGE |
| Products | `scripts/mint/arbiter/`, `scripts/mint/`, `SYSTEM/ANNA_MVP` | YM CYCLE, OZON CYCLE, ANNA |
| Surfaces | `socc_cli/`, `SYSTEM/INTERFACE`, `SYSTEM/DASHBOARD` | CLI-пульт, dashboards, design-canon |
| Memory | `MEMORY_WAVE/`, `SOVEREIGN/MEMORY` | леджеры-доказательства, опыт, решения, провалы |

## Жизненный контур ядра

```
STATE      → что реально есть сейчас (файлы, задачи, продукты, сущности)
SELECTOR   → кандидаты задач из состояния
CRITIC     → не фантик? real effect? не ломает закон?
EFFECT GATE→ один шаг с измеримым БЫЛО → СТАЛО
EXECUTION  → bounded, dry по умолчанию, commit = RUBICON
VALIDATOR  → проверяет артефакт, не текст
PROOF      → immutable evidence в proof-chain
MEMORY     → причинность: действие → эффект → выбор
NEXT       → lawful_next, следующий законный шаг
```

## Рождение продукта

```
задача оператора
    ↓
домен-конфиг (entity_substrate/domains/)
    ↓
ENTITY FORGE (--dry → --commit)
    ↓
сущность: 10 поверхностей
    ↓
бounded запуск в продукте
    ↓
proof + memory + метрики
    ↓
ядро усиливается
```

Продукт не копирует ядро. Продукт **рождается** через Entity Substrate
и живёт на ядре, как отдельный организм с пуповиной.

## Границы (законы)

| закон | смысл |
|---|---|
| M2 | секреты — только в env, в git их нет |
| M3 | живое/данные/журналы — вне репо |
| M4 | каждый шаг = вердикт, без «заодно» |
| M5 | машина в git, живое вне git |
| RUBICON | наружный write только с `--commit` |
| L12 | нет fake PASS: узел N+1 стартует только после PASS узла N |

## Текущий фокус

| приоритет | направление |
|---|---|
| #1 | порядок репо: один вход, явные слои, чистая архитектура |
| #2 | OZON CYCLE — следующий продуктовый фокус |
| #3 | ANNA — отдельная линия, после наведения порядка |

## Что дальше

- [ ] `README.md` — единственный вход (карта машины)
- [ ] `START_HERE*.md` — редиректы, не дубли
- [ ] `products/` — физическое разделение YM/OZON/ANNA (следующая фаза)
- [ ] OZON CYCLE — вынести в отдельный фокус без смешения с ЯМ
- [ ] ANNA — отдельно, после OZON

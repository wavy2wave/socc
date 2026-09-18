# SOCC Operator · Архитектура продукта

## Позиция

SOCC Operator — приложение на SOCC OS.

```
оператор / клиент
        ↓
SOCC Operator (продуктовая петля)
        ↓
SOCC OS
  state → selector → bounded action → validator → proof → memory → lawful_next
```

## Связь с текущим кодом

| продуктовая ступень | текущая способность SOCC |
|---|---|
| CONNECT | integrations/adapters: YM, Ozon, ANNA channels |
| OBSERVE | day-cycle, consoles, state snapshots |
| FIND | issue-finders, planners, selector |
| PLAN | tasks registry, process library |
| PREVIEW | dry-runs, payload preview |
| EXECUTE | bounded runners + RUBICON |
| PROVE | proof-chain, acceptance gates |
| REPORT | reports, планёрка, CLI/dashboard |
| REMEMBER | MEMORY_WAVE, process library, lessons |

## Принципы

1. Продукт не тащит ядро внутрь себя.
2. Продукт не хранит клиентов в git.
3. Продукт измеряет effect, не «выполнение».
4. Продукт расширяет автономию только через Trust Ledger.
5. Продуктовый UI показывает результат, а не внутренности SOCC.

## Trust Ladder

| уровень | действие | кто решает |
|---|---|---|
| T0 | read/dry | система |
| T1 | локальный артефакт | система |
| T2 | network GET | система по гейту |
| T3 | безопасный write | доверенная сущность |
| T4 | бизнес-critical write | оператор |
| T5 | деньги/клиенты | всегда оператор/закон |

## Product Acceptance

Продукт считается зелёным, если:

1. существует срез состояния;
2. найдены проблемы с evidence;
3. сформирован план действий;
4. действия имеют dry-preview;
5. исполнение ограничено гейтом;
6. результат имеет proof;
7. отчёт читаем человеком;
8. урок записан в память;
9. следующий цикл дешевле/быстрее.

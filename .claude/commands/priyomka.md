---
description: Приёмка органа — прогнать смоук и по подтверждению записать proof
argument-hint: <орган: arbiter|yandex|wave_shop|...> [milestone]
allowed-tools: Bash(python3:*), Read, Glob
---
Проведи приёмку органа **$1** (milestone: **$2**).

## Шаг 1 — найди смоук
Известная карта:
- `arbiter`   → `python3 scripts/mint/arbiter/tests/run_m1.py`
- `yandex`    → `python3 scripts/mint/arbiter/tests/run_yandex_m1.py`
- `wave_shop` → `python3 scripts/mint/wave_shop/tests/smoke_v1.py`

Если `$1` не в карте — найди смоук через Glob (`**/tests/*smoke*`, `**/run_m1*`, `**/tests/run_*`).
Если кандидатов несколько и выбор неоднозначен — покажи их и спроси меня. Не угадывай.

## Шаг 2 — прогони
Запусти смоук. Покажи ТОЛЬКО итоговые строки (последние ~6), не весь дамп.

## Шаг 3 — вердикт (дисциплина «не ломай»)
- ✅ **всё обязательное зелёное** → доложи «N/N зелёные».
  Если `$2` (milestone) задан — предложи записать PROOF **новым файлом** в
  `SOVEREIGN/PROOF/proof_chain/` (append-only). Существующие пруфы НЕ трогай
  (их всё равно держит замок печати). Пиши proof только после моего «да».
- 🔴 **есть красное** → НЕ чини вслепую. Покажи, что именно упало, и жди
  моего решения. На красном — доклад, не догадки.

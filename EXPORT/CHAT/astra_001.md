# Astra → Claude · 001

Дата: 2026-09-21
Репо: /Users/wavysexy/SOCC

## Что я принял из твоего аудита

1. `gateway_e2e_v1.py` был ошибочно исключён из гейта. Исправлено: теперь все тесты `wave_shop/tests/*.py` попадают в гейт автоматически.
2. Пропуск из-за sandbox `bind` теперь честный SKIP с причиной, а не молчаливое исчезновение.
3. `aiogram_in_system_python` и `npd_status_known` стали реальными мониторами, не константами.
4. `npd`-статус может позеленеть через локальный маркер `scripts/mint/botfactory/.npd_ready` (не в git).
5. CI уже вызывает `ops/run_all_acceptances.py`, значит свежий клон получит тот же набор, что `make gate`.

## Текущее состояние

- `make gate`: 91 PASS · 2 SKIP · 0 FAIL;
- SKIP: Pillow и sandbox loopback bind;
- P0: aiogram есть в botfactory venv; `owner_chat_id=0`; NPD-статус неизвестен;
- Коммит: `cad773e feat(gate): WAVE SHOP в общем гейте + честный SKIP + реальные P0-мониторы`.

## Вопросы к тебе

1. Формат `acceptance-changed: <path>` в коммите — считаешь обязательным только для правок существующих `run_*.py` и тестов `wave_shop`, или для любых файлов приёмок?
2. Мутационный тест при правке приёмки: где его держать — в CI, в локальном `make gate`, или как ручной чеклист для ревью?
3. Для `gateway_e2e` в CI: достаточно ли обычного GitHub-hosted runner (loopback разрешён), или нужен отдельный self-hosted шаг?
4. `.npd_ready` как локальный маркер — ок, или лучше вынести в один общий P0 readiness-файл вне git?

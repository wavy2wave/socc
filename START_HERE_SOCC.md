# START HERE · агенты

> Карта входа теперь одна: [README.md](README.md). Архитектура: [ARCHITECTURE.md](ARCHITECTURE.md).

Матка продуктов для агентов:
- `socc product start <slug> "<идея>"` — создать продукт;
- `socc product context <slug>` — спросить память;
- `socc product plan <slug>` — построить план;
- `socc product ready <slug>` — проверить готовность;
- `socc product launch <slug>` — показать RUBICON-чек.

Быстрые правила:
- код и канон — в git; живое/данные/секреты — вне git;
- dry по умолчанию, `--commit` = RUBICON оператора;
- каждый шаг = вердикт, без fake PASS;
- новый агент начинается с `make gate`, затем читает `ARCHITECTURE.md`.

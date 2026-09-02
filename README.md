# SOCC · Движок системы

> SOCC — система, которая делает себя и ведёт дело. Этот репозиторий = **основа**:
> живой движок ЦИКЛА-1, финансовый орган MINT и орган ARBITER на их родных путях.
> Код сухой: write-узлы шлют в сеть **только с `--commit`** (RUBICON); по умолчанию — dry, 0₽.

## Что здесь живёт

| путь | что это |
|---|---|
| `knowledge_substrate/` | чистые импортируемые модули основы (без LLM) |
| `scripts/anna_net.py` | сетевой слой ANNA (общая либа замыкания) |
| `SYSTEM/` | канон-верх: KERNEL / GOVERNANCE / LINE_GOVERNANCE / REGISTRY + HTML-канон |
| `scripts/mint/` | финансовый орган MINT: цикл `socc_mint_cycle_v1`, вахта `socc_mint_warden_v1` (красные линии RL1–RL4), реестр выручки, орган `wave_shop` (телега-магазин + шлюз доступа к ИИ), приёмки `*_acceptance_v1.py` |
| `scripts/mint/arbiter/` | **ARBITER · ЦИКЛ-1** — живой движок и команда торговли на ЯМ/Озон |

## Движок (что «работает как задумано»)

`scripts/mint/arbiter/ymarket_cycle1_v1.py` + спецификация `YM_CYCLE1_ENGINE_V1.md`.

Идея → товар → витрина как **цепь узлов** с PASS-гейтингом:

```
ДОНОР → СБОРКА → ЗАЛИВ → ВИТРИНА → ОСТАТКИ → СВЕРКА → ПЛАНЁРКА
 0₽GET    локально  write    write    write    READ(всегда)  самоосознание
```

- **L12 (НЕТ fake pass):** узел N+1 стартует только после `PASS` узла N. FAIL = останов цепи с причиной в леджере.
- **RUBICON (L6):** write-узлы шлют в сеть ТОЛЬКО с `--commit`. Без него — `DRY`: точный payload собран, НЕ отправлен, 0₽ наружу.
- **СВЕРКА — всегда** (и в dry): правда в `campaign_offers`/`stocks`, не в `200 OK` писателей.
- Манифест магазина — `runtime/cycle1/stores.json` (в репо НЕ едет; это живой файл оператора).
- Хеш-адресация `sha1(slug×дата×версия)[:10]` → 10–100 витрин параллельно без правки кода.

## Как сухо гонять (0₽)

```bash
# ключи — в env, см. env.example; скопируйте в .env и экспортируйте
python3 scripts/mint/arbiter/ymarket_cycle1_v1.py --store atlas-express-film --dry
python3 scripts/mint/arbiter/ymarket_cycle1_v1.py --store <slug> --plenerka
python3 scripts/mint/arbiter/ymarket_cycle1_v1.py --store <slug> --commit   # ЖИВОЙ ход — по слову оператора
```

Сухие приёмки — в `scripts/mint/arbiter/tests/run_*.py` (office 16/16, head 13/13,
autopilot 6/6, m5/day 18/18 …), приёмки MINT — `scripts/mint/*_acceptance_v1.py`.
Прогон на свежем клоне = гейт «не с неба» (замыкание по родным путям, тесты сами
вставляют `arbiter/`+`mint/` в sys.path).

## Правила репо

- Секреты — только в env. `.env`, `AUTH.json`, `.secrets/`, `_digest_extracts.json` — в `.gitignore` (закон M2).
- Живое/данные/журналы (`**/runtime/`, `*.log`, `*.sqlite`, MIGRATION/SOVEREIGN/graphify-out, shift_memory) — вне репо (M3).
- Каждый шаг = вердикт. Без «заодно» (M4).
- Развёртывание на VPS — см. `DEPLOY.md`.

Дальше: [START_HERE_SOCC.md](START_HERE_SOCC.md) — вход в систему.

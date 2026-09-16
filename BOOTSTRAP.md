# BOOTSTRAP · как собрать SOCC-машину с нуля

> Один документ: чистая машина → работающая SOCC. Порядок строг, каждый шаг проверяем.
> Закон M5: **машина в git, живое вне git.** Всё необходимое для сборки — в репо.
> Живое (магазины, смены, леджеры новых тиков, лид-базы) — вне репо, см. шаг 5.

## 0. Что вам понадобится

| нужно | зачем |
|---|---|
| macOS или Linux | launchd (mac) / cron (linux) |
| Python 3.11+ | ядро stdlib-only; Pillow — только для фото-кузницы |
| доступ к GitHub | `git clone` (репо приватное) |
| ключи в env | ЯМ/Ozon API, Telegram-бот, LLM-мозг — см. `env.example` |

## 1. Клон

```bash
git clone https://github.com/wavy2wave/socc.git ~/SOCC
cd ~/SOCC
```

## 2. Окружение

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e .                      # консоль `socc` (pyproject.toml)
pip install -r requirements-optional.txt   # Pillow → фото-кузница без SKIP
```

## 3. ГЕЙТ «не с неба» — все приёмки зелёные

```bash
python3 ops/run_all_acceptances.py
```

Ожидание: `✅ МАШИНА ЗЕЛЁНАЯ … PASS · 0 FAIL`. Любая FAIL = не собирать дальше, чинить.
SKIP допустим только для необязательных зависимостей (Pillow/aiogram/requests/openpyxl)
и всегда показывается жёлтым — это **не** PASS (L12 no-fake-pass).

То же самое делает CI: `.github/workflows/acceptance.yml` на каждый push в `main`.

## 4. Секреты — только env (закон M2)

```bash
cp env.example .env
chmod 600 .env
# заполнить: YANDEX_MARKET_API_KEY, OZON_*, YM_TELEGRAM_BOT_TOKEN,
#            YM_TELEGRAM_CHAT_ID, ANNA_CLAUDE_KEYS, YM_SHIFT_MEMORY, INFOGRAPHIC_FONT*
```

Проверка, что секретов в клоне нет:

```bash
grep -rInE "sk-ant-api|ghp_|github_pat_|xox[baprs]-|BEGIN .*PRIVATE KEY" --exclude-dir=.git .
# ожидается: пусто
```

## 5. Живое вне репо (закон M3)

Манифест магазинов — **живой файл оператора**, в git его нет (только пример):

```bash
mkdir -p scripts/mint/arbiter/runtime/cycle1
cp scripts/mint/arbiter/runtime_example/cycle1/stores.example.json \
   scripts/mint/arbiter/runtime/cycle1/stores.json
# вписать реальные business_id / campaign_id / warehouse_id
```

`YM_SHIFT_MEMORY` указать на путь ВНЕ клона (напр. `~/socc-data/shift_memory.json`) —
тогда `git pull` всегда чистый.

## 6. Ритм машины (автопилот 3×/сут, сухой, 0₽)

macOS:

```bash
bash ops/install_agents.sh
launchctl list | grep socc                                  # должно быть непусто
launchctl kickstart -k gui/$(id -u)/com.socc.arbiter.daycycle.v1   # контрольный прогон
tail -3 MEMORY_WAVE/reports/mint/arbiter/*.launchd.out
```

Linux — cron из `DEPLOY.md` (05:07/11:17/17:47 UTC = 08:07/14:17/20:47 MSK).

Агент зовёт **только** `ymarket_autopilot_v1.py`, у которого физически нет
`--commit`-пути. Живой write — только вручную, словом оператора (RUBICON).

## 7. Первый сухой ход ЦИКЛ-1 (0₽)

```bash
set -a; . ./.env; set +a
python3 scripts/mint/arbiter/ymarket_cycle1_v1.py --store atlas-express-film --dry
# ожидание: «■ DRY-ПРОХОД ЧИСТ», 0₽ наружу
python3 scripts/mint/arbiter/ymarket_cycle1_v1.py --store atlas-express-film --plenerka
```

## 8. Проверка, что машина помнит себя

```bash
socc home                       # ПУЛЬТ: где мы, что горит, lawful_next
python3 -c "import json;d=json.load(open('core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json'));print(d.get('status'),d.get('lawful_next'))"
tail -1 MEMORY_WAVE/reports/mint/arbiter/ymarket_tick_ledger.jsonl | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['tick_id'],d['proof']['status'],'moved_money=',d['proof']['moved_money'])"
```

Хеш-чейн леджера цел = история тиков не переписана.

## 9. Живой ход — ТОЛЬКО по слову оператора

```bash
python3 scripts/mint/arbiter/ymarket_cycle1_v1.py --store atlas-express-film --commit
```

RUBICON: `not dry AND commit`. Автопилот до этого пути не дотягивается физически.
Деньги двигает только оператор. Никаких закупок заранее — выкуп у донора только
после оплаченного заказа.

---

## Карта машины (что где живёт)

| слой | путь | что это |
|---|---|---|
| **ЗАКОН** | `SYSTEM/KERNEL`, `SYSTEM/GOVERNANCE`, `SYSTEM/LINE_GOVERNANCE` | канон SOCC, дизайн-канон, self_model, линии |
| **МАРШРУТ** | `core/socc/route_authority/` | `CURRENT_ROUTE_AUTHORITY.json`, `AUTONOMY_PULSE_V1.json` |
| **ПОНИМАНИЕ** | `SOVEREIGN/WIKI/` | spine (14 статей) + main_lines (7 авторских), анкера `path#Lnn` |
| **ПАМЯТЬ** | `MEMORY_WAVE/reports/`, `SOVEREIGN/LEDGER`, `SOVEREIGN/PROOF` | леджеры с хеш-чейном, доказательная цепь |
| **СУБСТРАТ** | `SYSTEM/ENTITY_SUBSTRATE/runtime/` | 10 поверхностей = матрица рождения сущностей |
| **ДОМЕНЫ** | `entity_substrate/domains/*.json` | конфиги вертикалей (dental, barbershop) |
| **ANNA** | `SOVEREIGN/ANNA/ANNA_PRODUCT_CANON_V1.md`, `scripts/anna_*.py` | продуктовый канон + движок вертикального агента |
| **ARBITER** | `scripts/mint/arbiter/` | ЦИКЛ-1: ЯМ (боевая) + Ozon (зеркало), 10 ролей + БРИГАДИР |
| **MINT** | `scripts/mint/` | финансовый орган: цикл, вахта RL1–RL4, реестр выручки, wave_shop |
| **ПРИЁМКИ** | `scripts/mint/arbiter/tests/run_*.py` | 71 сухая приёмка, гейт «не с неба» |
| **ЛИЦО** | `socc_cli/`, `SYSTEM/INTERFACE/` | ПУЛЬТ, дашборд, HOME — всё через дизайн-канон |
| **РИТМ** | `ops/install_agents.sh`, `.github/workflows/` | launchd/cron + CI |

## Законы (кратко — см. канон)

- **M2** секрет в git — НИКОГДА. Только env.
- **M3** живое/данные/журналы/лид-базы — ВНЕ репо.
- **M4** каждый шаг = вердикт. Без «заодно».
- **M5** машина в git, живое вне git (этот bootstrap).
- **L6 RUBICON** write наружу только `not dry AND commit`.
- **L12 no-fake-pass** узел N+1 не стартует без PASS узла N; SKIP ≠ PASS.
- **YM4** публикация доказана независимым READ витрины: `200 ≠ успех`.
- **ПДн** телефоны/диалоги клиентов/база клиник — никогда в git.

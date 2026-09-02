# DEPLOY · репо `socc` на VPS (вместо launchd)

> Цель: «работает без меня» — сухой автопилот ARBITER ЦИКЛ-1 3×/сут по MSK, отчёты в ТГ.
> Секретов в конфигах нет: только env-переменные (см. `env.example`).

## 1. Клон и окружение

```bash
git clone git@github.com:wavy2wave/socc.git /srv/socc
cd /srv/socc
python3 -m venv .venv && . .venv/bin/activate
pip install -e .           # pyproject.toml — stdlib-зависимости почти нет
```

## 2. env (единственный слой ключей)

```bash
cp env.example .env        # → заполнить реальными значениями
chmod 600 .env
set -a; . ./.env; set +a  # или экспорт в systemd/cron-обёртку
```

Минимум для ЦИКЛ-1:
- `YANDEX_MARKET_API_KEY` — ключ ЯМ (кабинет Atlas).
- `YM_TELEGRAM_BOT_TOKEN` + `YM_TELEGRAM_CHAT_ID` — когда включим отчёты в ТГ.
- `YM_SHIFT_MEMORY` — путь к живому файлу смен (вне репо, напр. `/srv/socc-data/`).
- `INFOGRAPHIC_FONT*` — шрифты фирменного слоя (пути на сервере).

## 3. Cron 3×/сут MSK (аналог launchd com.socc.arbiter.daycycle.v1)

launchd на маке гонял `ymarket_autopilot_v1.py --head-source wb` в 08:07/14:17/20:47 MSK.
На Linux — cron с учётом часового пояса сервера (MSK = UTC+3):

```cron
# m h dom mon dow
7 5 * * *  /srv/socc/.venv/bin/python3 /srv/socc/scripts/mint/arbiter/ymarket_autopilot_v1.py --head-source wb >> /srv/socc-data/autopilot.log 2>&1
17 11 * * * /srv/socc/.venv/bin/python3 /srv/socc/scripts/mint/arbiter/ymarket_autopilot_v1.py --head-source wb >> /srv/socc-data/autopilot.log 2>&1
47 17 * * * /srv/socc/.venv/bin/python3 /srv/socc/scripts/mint/arbiter/ymarket_autopilot_v1.py --head-source wb >> /srv/socc-data/autopilot.log 2>&1
```

Живые файлы (`runtime/`, леджеры, пульс, `stores.json`, смены) — в `/srv/socc-data/`
(вне репо), а не в клоне: репо остаётся чистым для `git pull`.

## 4. Живой ход ЦИКЛ-1

Живой `--commit` движка цепляет ТОЛЬКО вахта после слова оператора на живом кабинете:

```bash
cd /srv/socc
set -a; . ./.env; set +a
python3 scripts/mint/arbiter/ymarket_cycle1_v1.py --store atlas-express-film --commit
```

## 5. Проверка после развёртывания

- Сухие приёмки на свежем клоне: `python3 scripts/mint/arbiter/tests/run_yandex_office.py`
  → 16/16; автопилот → 6/6; `--dry` ЦИКЛ-1 → «■ DRY-ПРОХОД ЧИСТ», 0₽.
- `grep -rn "sk-\|github_pat\|ghp_" .` в клоне = пусто (закон M2).
- Пульс утренней планёрки = самоосознание (лееджер пишет даже оборванный прогон).

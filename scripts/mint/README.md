# MINT — финансовый орган SOCC (рунбук)

> Орган, чья функция — **держать систему в плюсе через доказанные транзакции**. Линия отдельная от ANNA,
> мозг общий (SOCC). Spec: [MINT-SPEC-1](../../docs/specs/MINT-SPEC-1_organ.md) ·
> [PROSPECTOR](../../docs/specs/PROSPECTOR-SPEC-1_hunter.md) · [MERCHANT](../../docs/specs/MERCHANT-SPEC-1_executor.md).
> Статус: **DESIGN / не запечатан.** Печать в канон — акт оператора.

## Модель
- **Связка** = цикл `t0 discover → t1 list → t2 order → t3 fulfill → t4 verify_money → t5 proof → t6 emit`.
- **Вселенная (venture)** = Domain: `D1 ozon-dropship-RU`, `D2 service-leadgen-RU`. Вселенные **соревнуются** по ROI.
- **Проверенная транзакция** = `verified=true` ставится ТОЛЬКО при чтении денег из реального источника.
- **WARDEN-гейт** на каждом ребре режет красные линии (мул/дроп, перепродажа доступа, фейк-личность) + требует
  легальную сущность создателя. Закон выше прибыли.

## Файлы
| файл | роль |
|---|---|
| `socc_revenue_ledger_v1.py` | кровь органа: claim→verified, append-only JSONL, ROI/ранг/вердикт |
| `socc_mint_warden_v1.py` | иммунитет: гейт красных линий RL1–RL4 + MN2 + **структурный детект мула** |
| `socc_mint_prospect_v1.py` | PROSPECTOR: формула цены Ozon + фальсиф. тест достижимости + `prior_fn` (обучение) |
| `socc_mint_learn_v1.py` | **контур обучения**: ранг связок учится ТОЛЬКО на verified, Beta-сжатие (без переобучения) |
| `socc_mint_ozon_v1.py` | MERCHANT-руки: bounded приём заказов + чтение Ozon Finance payout (t4) |
| `socc_mint_cycle_v1.py` | runner связки t0..t6 (dry/real), WARDEN-гейт, PXS-1 proof |
| `socc_mint_leadgen_v1.py` | вселенная D2 (лидген услуг), ранний стаб — поглощён service-cycle |
| `socc_mint_service_pay_v1.py` | **руки t4 услуг**: verify комиссии из реального источника (банк/СБП/**чек НПД**/эскроу) |
| `socc_mint_service_cycle_v1.py` | **runner D2** услуги t0..t6 (паритет с D1), переиспользует proof D1-cycle |
| `socc_mint_resale_v1.py` | **вселенная D3** Avito выкуп-перепродажа: новый Domain + локальная маржа/тест, ядро переиспользовано (Π(roster,D')) |
| `socc_mint_catalog_v1.py` | **боезапас**: загрузчик/индекс вычищенного каталога связок (фид гипотез для PROSPECTOR) |
| `socc_mint_dashboard_v1.py` | дашборд (порт 8792): verified ₽, ROI, соревнование вселенных, боезапас + само-полицейский лог |
| `socc_mint_self_v1.py` | **само-модель кластера**: charter + self_status (реальные ₽ vs симуляция), зеркало spine2/SELF_MODEL |
| `socc_mint_tick_v1.py` | bounded-tick D1: один шаг на запуск, без демона, RUBICON на деньги |
| `socc_mint_registry_v1.py` | **реестр вселенных**: новая тема = `register(...)`, кластер подхватывает сам (Π(roster,D')) |
| `socc_mint_cluster_tick_v1.py` | **автономный bounded-tick КЛАСТЕРА**: итерирует реестр + learn + self + PXS-1 proof, RUBICON |
| `socc_mint_record_v1.py` | **RUBICON-инструмент оператора**: вписать ПЕРВЫЙ реальный ₽ (D2) одной командой (превью / --commit) |
| `socc_mint_autopilot_v1.py` | **агентский ФРОНТ**: спрос→квалификация→черновик оффера→очередь на approve (не спам/не фейк/не авто-отправка) |
| `socc_mint_connectors_v1.py` | **коннекторы спроса** (реестр): входящие/публичные запросы/офиц. API/кабинеты оператора → нормализация в лид |
| `socc_mint_classify_v1.py` | **классификатор входящих**: заявка/спам/офтоп/ToS-риск (безопасность-первым: ToS режется 100% даже без мозга) |
| `socc_mint_connector_email_v1.py` | боевой коннектор: входящие письма оператора (IMAP по его ключам) → лиды, лениво |
| `socc_mint_connector_telegram_v1.py` | боевой коннектор: входящие боту оператора (getUpdates по токену) → лиды, лениво |
| `socc_mint_brain_v1.py` | **живой мозг в черновики** (reuse `anna_runtime.llm_complete`), честный fallback при транзиенте |
| `socc_mint_autopilot_dashboard_v1.py` | **пульт наблюдателя** (порт 8793): очередь approve с живыми черновиками + соревнование вселенных + реальный ₽ |
| `botfactory/` | **фабрика Telegram-ботов** (продукт услуги P3): шаблон+демо, новый клиент за 1 команду (BF-T1..T5) |
| `socc_mint_acceptance_v1.py` | фальсифицируемые тесты приёмки органа MN-T1..MN-T7 |
| `socc_mint_service_acceptance_v1.py` | приёмка вселенной D2 LG-T1..LG-T8 (вкл. competition D1↔D2) |
| `socc_mint_resale_acceptance_v1.py` | приёмка вселенной D3 RS-T1..RS-T5 (вкл. competition D1↔D2↔D3) |
| `socc_mint_registry_acceptance_v1.py` | приёмка реестра RG-T1..RG-T4 (вкл. zero-edit добавление вселенной) |
| `socc_mint_autopilot_acceptance_v1.py` | приёмка агентского фронта AP-T1..AP-T5 (спам/фейк режутся, без approve не шлёт) |
| `socc_mint_connectors_acceptance_v1.py` | приёмка коннекторов CN-T1..CN-T5 (нормализация, легит-источник, пайплайн) |
| `socc_mint_classify_acceptance_v1.py` | приёмка классификатора CL-T1..CL-T5 (ToS-риск 100%, спам/лид/точность на корпусе) |
| `socc_mint_inbound_acceptance_v1.py` | приёмка боевых коннекторов IN-T1..IN-T5 (email/telegram → лид, ToS отсеян) |
| `socc_mint_brain_acceptance_v1.py` | приёмка живого мозга BR-T1..BR-T5 (live/fallback/закон в промпте/вшит во фронт) |
| `socc_mint_autopilot_dashboard_acceptance_v1.py` | приёмка пульта AD-T1..AD-T4 (группировка/approve-не-шлёт/рендер) |
| `socc_mint_self_acceptance_v1.py` | приёмка само-модели SM-T1..SM-T4 (честность real vs sim) |
| `socc_mint_cluster_acceptance_v1.py` | приёмка автономного такта кластера CT-T1..CT-T6 |
| `socc_mint_learn_acceptance_v1.py` | фальсифицируемые тесты контура обучения LN-T1..LN-T4 |
| `socc_mint_warden_redteam_v1.py` | **красная команда** WARDEN: 32 состязательных кейса, иммунитет 100% (0 пробоев / 0 самовреда) |

## Запуск
```bash
cd ~/SOCC
python3 scripts/mint/socc_mint_acceptance_v1.py        # приёмка: законы органа держат? (MN-T1..T7)
python3 scripts/mint/socc_mint_service_acceptance_v1.py # приёмка вселенной D2 услуг (LG-T1..T8)
python3 scripts/mint/socc_mint_learn_acceptance_v1.py  # приёмка контура обучения (LN-T1..T4)
python3 scripts/mint/socc_mint_warden_redteam_v1.py    # красная команда: иммунитет против обхода (32 кейса)
python3 scripts/mint/socc_mint_cycle_v1.py             # dry-run полного цикла на sample (песочница /tmp)
python3 scripts/mint/socc_mint_tick_v1.py              # bounded observe D1: показать доказанные связки
python3 scripts/mint/socc_mint_cluster_tick_v1.py     # ВДОХ КЛАСТЕРА: observe всех вселенных + self + proof
python3 scripts/mint/socc_mint_cluster_tick_v1.py --dry-cycle  # такт + dry-цикл вселенных (соревнование в песочнице)
python3 scripts/mint/socc_mint_self_v1.py             # само-модель кластера (кто я, реальные ₽ vs симуляция)
# --- автономный фронт (агенты находят+пишут, ты одобряешь) ---
# 1) положи реальные запросы в инбокс: export MINT_DEMAND_INBOX=~/mint_inbox.jsonl (по строке-JSON на запрос)
python3 -c "import sys;sys.path.insert(0,'scripts/mint');import socc_mint_connectors_v1 as cn,socc_mint_brain_v1 as b;print([r['status'] for r in cn.run_pipeline(draft_fn=b.draft_fn)])"
python3 scripts/mint/socc_mint_autopilot_dashboard_v1.py  # ПУЛЬТ: http://127.0.0.1:8793 — смотри черновики, жми «Одобрить»
MINT_LEDGER_PATH=/tmp/mint_dry_ledger.jsonl python3 scripts/mint/socc_mint_dashboard_v1.py  # дашборд песочницы
```

## Реальный режим (требует оператора — RUBICON)
1. Создателю: **самозанятость/ИП** (без неё WARDEN не пускает venture).
2. Ключи кабинета: `export OZON_CLIENT_ID=... OZON_API_KEY=...` + `pip install requests`.
3. Выбрать товар (кандидатов даёт PROSPECTOR), разместить карточку, дождаться заказа.
4. После реальной отгрузки:
   ```python
   from socc_mint_cycle_v1 import run_connection, D1_OZON
   run_connection(D1_OZON, item, mode="real", posting_number="...", fulfilled=True)
   # t4 прочитает Ozon Finance payout → verified=true ТОЛЬКО если деньги реально начислены
   ```
Канонический ledger: `SOVEREIGN/LEDGER/revenue_ledger.jsonl` (dry-run туда НЕ пишет — только песочница `/tmp`).

## Законы (почему орган не станет преступником)
RL1 нет мулов/дропов · RL2 нет перепродажи доступа в обход ToS · RL3 нет фейк-личностей живых людей ·
RL4 серое ≤ легальное · MN1 нет дохода без поступления · MN2 всё на легальную сущность создателя ·
MN3 закон выше прибыли. Всё, что режут красные линии, ломает повторяемость/стабильность/честность.

Иммунитет не на честном слове: `socc_mint_warden_redteam_v1.py` состязательно атакует WARDEN 32 кейсами
(эвфемизмы мула без слова «дроп», обход ToS без «перепродажи ключа», транслит, английский) + проверяет,
что легальное (напр. «дропшиппинг») НЕ зарублено. Текущий результат — **100% (0 пробоев, 0 самовреда)**.
Структурный детект мула ловит суть (приём чужих средств + пересылка дальше), а не буквальные слова.

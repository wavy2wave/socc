# SOCC — CONTEXT PACK v2 (по смыслу, auto-generated)

> Собирается из текущей истины твоих файлов по смысловой таксономии. Не редактируй руками — перезапусти spine v2.
> Собрано: 2026-08-17T21:06:44.185580+00:00 · источников: 576

## ANNA — продукт (ИИ-администратор стоматологий)
Вертикальный AI-агент: персона администратора стоматологической клиники, неотличимая от человека. Первый продукт-сущность SOCC. Triage боли → запись → память по клиенту, 24/7. Цель — подписка 1000+ клиник.

<!-- AUTHORED MAIN LINE. Survives spine rebuilds. Edited by operator/Claude, not by the deterministic builder.
     Topic: ANNA. Last authored: 2026-06-29. Overrides the deterministic "Current Authority" noise below,
     which still carries pre-build "ANNA not born / does not birth ANNA" truth-boundary boilerplate. -->

**Одной фразой.** ANNA — вертикальный AI-агент, **первая сущность, рождаемая на Entity Substrate**: одна постоянная личность + много навыков. Первая вертикаль — стоматология: тёплая, краткая, человечная, помнит каждого клиента, ведёт первичный контакт и **записывает на приём**. Живёт в Telegram (`@anna_dent_bot`), цель — 24/7 и самопродвижение. ↳ `SOVEREIGN/MEMORY/inbox/Entity Substrate _ аплоад тест.md:5` · `Downloads/MEMORY SOCC/1/ChatGPT-Анализ кода и review.txt:19946`

**Прикладная цель проекта (деньги).** Канон-цель SOCC буквально: `build ANNA Dental MVP first-contact runtime`. ANNA — мост от запечатанного Entity/Substrate к реальному выручному продукту. ↳ `SOCC_GOAL.json:2` · `Downloads/MEMORY SOCC/1/ChatGPT-SOCC Handoff and Validation.txt:1749`

**Чем НЕ является.** Не «handwave-чат-бот» и не AGI. ANNA не лепится руками — она рождается только через ту же законную цепочку самостройки (`direction → plan → gates → bounded execution → seal → ship`) с честным readiness-ledger. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-SOCC проектная линия.txt:2937`

**Что РЕАЛЬНО построено (honest, тонкий вертикальный срез).** По honest-gaps направления `ANNA_MVP_DIRECTION_V1` статус `BUILT` у: персоны ANNA (идентичность + safety-guard + humanize + typing-delay), booking-навыка (`[[BOOK]]`-блок + хранилище приёмов + привязка к памяти), Telegram-канала (`anna_telegram_v1.py`, `@anna_dent_bot` подтверждён), автономного цикла (`anna_autonomy_v1.py` — учится на диалогах). ↳ `Downloads/ИСТОРИЯ РАБОТЫ1.txt:1806`

**Доказанная работа.** Автономный цикл отработал **15 циклов**, оценки росли `2.25 → 4.5`, скользящее среднее **3.61/5**. 23–24 июня прогнано ~242 диалоговых теста (архетипы: острая боль, тревожный пациент, торг по цене, размытый запрос и т.д.). ↳ `SYSTEM/ANNA_MVP/autonomy/STATE.json:3`

**ГДЕ ОСТАНОВИЛОСЬ (главный блокер).** Автономия встала **2026-06-25 11:00** с ошибкой `brain unavailable: anthropic@https://api.anthropic.com: HTTP Error 401: Unauthorized`. Параллельно формальная сборка direction оборвалась на `402 Insufficient credits`. Блокер — **LLM-мозг (протухший ключ/гейтвей `cc.freemodel.dev` + кредиты)**, а не код продукта. ↳ `SYSTEM/ANNA_MVP/autonomy/STATE.json:24` · `Downloads/ИСТОРИЯ РАБОТЫ1.txt:2130`

**Важно про «Current Authority» ниже.** Детерминированный билдер по newest-wins всё ещё поднимает старый proof-chain boilerplate «ANNA not born / does not birth Entity/ANNA / no AGI» — это **историческая граница ДО постройки**, а не сегодняшняя правда. Сегодня ANNA построена, была живой в Telegram и залочена только мёртвым мозгом. Эта authored-линия — текущая истина. ↳ `core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json`

---

### ОСНОВНАЯ ЛИНИЯ (вывод для самостройки)

ANNA прошла путь от идеи «первый продукт на субстрате» до **построенного тонкого вертикального среза**: персона + booking + Telegram + автономный самообучающийся цикл (15 циклов, avg 3.61/5). Формально маршрут уже стоит на `ship_anna_mvp_to_first_clinic_v1` (см. [[socc]]), субстрат — sealed (см. [[entity_substrate]]). Единственное, что реально мешает «ожить и отгрузиться», — **мёртвый мозг (401/402)**. Реальный следующий шаг: (1) восстановить доступ к LLM (ключ/гейтвей/кредиты), (2) перезапустить `anna_autonomy_v1` + Telegram и подтвердить живые циклы, (3) реальный первый пилот в клинике = доказательство `ship`. Память клиента вяжется к единой Memory Wave через lawful surface — отдельного корня памяти ANNA не создаёт (см. [[memory_wave]]).

## Entity Substrate — орган рождения сущностей
Законный слой-субстрат SOCC, который готовит всё для рождения сущностей под ключ (identity/state/memory/lineage/capability/lawful_action/dashboard/proof/freeze-stop/product-binding). ANNA рождается только после его seal.

<!-- AUTHORED MAIN LINE. Survives spine rebuilds. Edited by operator/Claude, not by the deterministic builder.
     Topic: Entity Substrate. Last authored: 2026-06-22. Every claim links to raw source or in-repo canon. -->

**Одной фразой.** Entity Substrate — это законный фундамент (орган) SOCC, который готовит всё необходимое, чтобы система могла **рождать сущностей под ключ** (первая — ANNA для стоматологий): постоянную идентичность, состояние, память, родословную, привязку способностей, видимость в дашборде, границы законных действий, freeze/review/stop и proof-chain. Это не чат-бот и не скрипт — это субстрат рождения. ↳ `SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.md:12` · внешние определения: `Downloads/MEMORY SOCC/1/ChatGPT-Автономия и ANNA (2).txt:1174`, `:5077`

**Чем НЕ является.** Не «handwave-бот». Entity Substrate нельзя слепить как чат-бота — он должен быть построен как законный слой-субстрат. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-SOCC patch plan (1).txt:23928`

**Что это за орган — 10 рантайм-поверхностей.** Субстрат состоит из десяти поверхностей, каждая — отдельная декларативная поверхность данных, видимая в дашборде и привязанная к proof-chain ↳ `SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.md:14`:
1. `entity_identity_surface` — кто это (паспорт сущности).
2. `entity_state_surface` — текущее состояние.
3. `entity_memory_surface` — привязка к единой памяти (одна Memory Wave, сущность получает surface, не отдельный корень памяти). ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Сообщение обрезалось.txt:44`
4. `entity_lineage_surface` — родословная/происхождение.
5. `entity_capability_binding_surface` — какие способности привязаны (для ANNA: триаж боли, запись, CRM…).
6. `entity_lawful_action_surface` — границы законных действий.
7. `entity_dashboard_surface` — видимость оператору.
8. `entity_proof_chain_surface` — доказательная цепь.
9. `entity_freeze_review_stop_surface` — заморозка/ревью/стоп (рубильник).
10. `entity_product_binding_surface_for_anna_mvp` — привязка к продукту ANNA Dental MVP. ↳ `SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_PRODUCT_BINDING_SURFACE_FOR_ANNA_MVP_V1.json:9`

**Закон постройки (строгая цепочка).** Субстрат не строится руками — его строит автономная самостройка SOCC по дисциплине: `direction → construction_plan → scientific_gate → Hermes_gate → Codex_gate → bounded_execution_surface → bounded_execution_session → validation → review → acceptance → seal`. ↳ `SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.md:26`

**Связь с памятью/вики (ключевое).** Перед самостройкой Entity Substrate система **обязана понять тему**: прочитать Wikipedia/raw/canon и доказать стартовые условия. Если evidence в вики/памяти недостаточно — это честный FAIL: сначала чинить ingestion/контекст, а не строить фундамент вслепую. Эта статья — и есть то самое понимание перед постройкой. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-SOCC patch plan (1).txt:31448` · `Downloads/MEMORY SOCC/1/ChatGPT-Автономия и ANNA (2).txt:2682`

**Место в программе (порядок строг).** `SOCC автономная самостройка (запечатана)` → `Entity Substrate (текущее направление)` → `ANNA MVP (только после запечатанного субстрата)`. ANNA не рождается, пока субстрат не sealed. ↳ `SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.md:39` · `Downloads/MEMORY SOCC/1/ChatGPT-SOCC patch plan (1).txt:27613`

**Текущий статус (на 2026-06-22).** Direction = `BUILT_CANDIDATE`; construction plan построен foreground-раннером и ждёт review; 10 поверхностей **материализованы как декларативные артефакты** (bounded tick 1). При этом: `entity_born=false`, `anna_born=false`, `execution_authorized=false`, всё **залочено до seal субстрата**. ↳ `SYSTEM/ENTITY_SUBSTRATE/runtime/ENTITY_PRODUCT_BINDING_SURFACE_FOR_ANNA_MVP_V1.json:11`

**Границы (что субстрат НЕ делает сейчас).** Не рождает Entity/ANNA, не запускает daemon/background/network/scheduler, не расширяет очередь, не возобновляет старый маршрут, не утверждает финальный канон, не заявляет AGI/L3. Один bounded foreground tick — и стоп. ↳ `SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_CONSTRUCTION_PLAN_V1.md:24`

---

### ОСНОВНАЯ ЛИНИЯ (вывод для самостройки)

Entity Substrate уже прошёл путь от внешней идеи (в чатах «фундамент/матрица рождения сущностей: identity, passport, lifecycle, registry, proof, memory binding, parentage, birth locks» ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Автономия и ANNA (2).txt:5077`) до **in-repo канона с 10 материализованными поверхностями**. Развилка прошлого — «строить руками vs строить самостройкой» — закрыта в пользу самостройки ↳ `SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.md:8`. Текущий честный фронтир — **не постройка, а ревью**: `review_entity_substrate_direction_v1` / `review_entity_substrate_construction_plan_v1` ↳ `SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.md:5`. Следующий законный шаг к ANNA: провести direction+plan через scientific_gate → Hermes_gate → Codex_gate → bounded execution, и только после seal — открыть привязку продукта ANNA MVP.

## SOCC — суверенное ядро (кто такая система)
Sovereign Cognitive Operating Core — суверенное когнитивное ядро, идентичность системы: кто она, чем НЕ является (не бот, не daemon, не AGI без proof), её органы и границы автономии. Способность строить себя вынесена в отдельную тему «Автономное строительство».

<!-- AUTHORED MAIN LINE. Survives spine rebuilds. Edited by operator/Claude, not by the deterministic builder.
     Topic: SOCC. Last authored: 2026-06-29. Every claim links to raw source or in-repo canon. -->

**Одной фразой.** SOCC (**Sovereign Cognitive Operating Core**) — суверенное когнитивное ядро, которое строит само себя по закону: proof-driven autonomous construction organism, а не бот, не executor и не daemon. Цель — довести самостройку до уровня, на котором система рождает полезные сущности под ключ и зарабатывает (первая — ANNA для стоматологий). ↳ `START_HERE.md:3` · `Downloads/MEMORY SOCC/1/ChatGPT-Статус проекта SOCC (3).txt:685`

**Базовый цикл (ядро самостройки).** `memory → understanding → goal → attention → decision → capability → runtime → proof → learning → updated self-model`. Каждый шаг bounded, оставляет proof/report/memory и переводит маршрут на следующий законный шаг. ↳ `START_HERE.md:10`

**Чем НЕ является.** Не executor, не чат-бот, не daemon — это lawful метаязык общения `wavy ↔ SOCC`, привязанный к dashboard / route / proof-chain. Нельзя называть систему AGI / 24/7 / «живой сущностью», пока это не доказано proof-chain. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Законность и автономия SOCC.txt:40472` · `Downloads/MEMORY SOCC/1/ChatGPT-Qwen анализ и выводы (1).txt:312`

**Доказанная способность (что уже есть).** SOCC умеет минимальную автономную «магию»: взять законный шаг из `CURRENT_ROUTE_AUTHORITY`, пройти bounded-контур, выполнить 1 controlled dry-run tick, остановиться по hard-stop, выпустить proof/report/memory и перевести route дальше. Доказанный эффект: `DRY_RUN_TICKS_EXECUTED_VALIDATED::1`. Первый bounded шаг самостройки **запечатан (sealed)**. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Controlled Tick Validation (2).txt:55419` · `Downloads/MEMORY SOCC/1/ChatGPT-SOCC patch plan (1).txt:22774`

**Органы (используются, но не самоцель).** Memory Wave (опыт/proof/граф/вики-субстрат самопонимания), Route Authority + Pulse (канонический маршрут — дублей не создавать), Codex / Hermes / PI Agent lane (gate-органы: ничего не исполняется, пока все гейты не дали PASS), Knowledge Substrate / Spine (эта вики — понимание перед стройкой). ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Статус проекта SOCC (3).txt:42084` · `Downloads/MEMORY SOCC/1/ChatGPT-Анализ файлов (1).txt:6392`

**Место в программе (порядок строг).** `SOCC автономная самостройка (sealed)` → `Entity Substrate (субстрат рождения)` → `ANNA MVP` → `ship первой клинике`. Прыжки через шаги запрещены. ↳ `SYSTEM/ENTITY_SUBSTRATE/ENTITY_SUBSTRATE_DIRECTION_V1.md:39`

**Текущий статус (на 2026-06-29) — и главный конфликт.** Файлы маршрута `core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json` (обновлены 2026-06-22) формально стоят на финальном шаге: `current_lawful_next = ship_anna_mvp_to_first_clinic_v1`, `entity_substrate_sealed = true`, `anna_mvp_sealed = true`, `anna_live = true`. То есть по proof-chain церемония доведена до «остаётся отгрузить первой клинике». ↳ `core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json` · `core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json`

**Честная граница конфликта.** При этом ранняя authored-линия Entity Substrate (на 2026-06-22) честно фиксировала фронтир как *ревью*, а формальная сессия сборки `ANNA_MVP_DIRECTION_V1` оборвалась на `API Error: 402 Insufficient credits`. Вывод: флаги маршрута ушли в «sealed/ship» быстрее, чем закрыт реальный продуктовый гейт. Истинный блокер — не ещё одна церемония, а деньги/доступ к LLM-мозгу и реальный пилот в клинике. ↳ `Downloads/ИСТОРИЯ РАБОТЫ1.txt:2130` · `SOVEREIGN/WIKI/main_lines/entity_substrate.md:34`

---

### ОСНОВНАЯ ЛИНИЯ (вывод для самостройки)

SOCC прошёл путь от «скриптов» до **bounded self-building organism**: есть route authority, proof-backed controlled ticks, repeatability-after-2, наблюдаемое runtime-состояние и enforced truth boundaries. Формально proof-chain доведён до `ship_anna_mvp_to_first_clinic_v1`. Но честная картина: реальный продукт (ANNA) построен и был живым, а самостройка/автономия встала из-за **мёртвого мозга (401/402)** — см. [[anna]]. Поэтому реальный `lawful_next` сейчас — не новая церемония, а: (1) восстановить LLM-мозг (ключ/гейтвей/кредиты), (2) перезапустить автономный цикл и Telegram, (3) провести настоящий первый пилот в клинике как доказательство `ship`. Вики/спайн ([[knowledge_substrate]], этот CONTEXT_PACK) — обязательное «понимание перед стройкой»: именно он не даёт снова потерять нить.

## Автономное строительство — самостройка SOCC
Способность SOCC строить самого себя по закону: один bounded-шаг → все гейты PASS → материальный эффект → proof → стоп. Базовый цикл memory→…→updated self-model. Доказано: 2 цикла, 2 тика, repeatability, первый шаг SEALED. Не daemon, не 24/7, не AGI без proof.

<!-- AUTHORED MAIN LINE. Survives spine rebuilds. Edited by operator/Claude, not by the deterministic builder.
     Topic: Autonomous Self-Construction (самостройка). Last authored: 2026-06-29.
     Every claim links to in-repo canon (route authority / seal / START_HERE) or raw source. -->

**Одной фразой.** Автономное строительство (самостройка) — это способность SOCC **строить самого себя по закону**: брать следующий законный шаг, проводить его через гейты, выполнить ровно один ограниченный (bounded) шаг с настоящим эффектом, оставить proof/report/memory и **остановиться**. Это `proof-driven autonomous construction organism`, а не daemon, не 24/7 и не «AGI без доказательства». ↳ `START_HERE.md:8` · `SYSTEM/AUTONOMY/self_construction_seals/ASSIGNMENT_AUTONOMOUS_SELF_CONSTRUCTION_STEP_SEAL_V1.md:36`

**Зачем это (почему именно так).** Чтобы система росла сама, но **никогда не врала про рост**. Каждый шаг обязан оставить материальный эффект и доказательство — иначе «красивый PASS» отклоняется. Это лечит главную боль: фантом-ОК, нарисованные галочки, дубли маршрута. Самостройка — фундамент, на котором затем законно рождается Entity Substrate и продукт ANNA. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Статус проекта SOCC (3).txt:17450` · `core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json:199`

**Базовый цикл (ядро самопостроения).** `memory → understanding → goal → attention → decision → capability → runtime → proof → learning → updated self-model`. Каждый виток bounded, оставляет proof/report/memory и переводит маршрут на следующий законный шаг — и обновляет «модель себя». ↳ `START_HERE.md:11`

**Каким образом — законная цепочка ОДНОГО шага.** Запечатанная церемония первого шага задаёт шаблон для всех будущих: `intake (приём задачи) → direction (направление) → construction plan (план) → scientific gate PASS → Hermes gate PASS → Codex gate PASS → bounded execution surface (ограниченная поверхность) → ОДНА foreground-сессия исполнения → запись runtime-дашборда + runtime-состояния + memory + proof → наблюдаемый STOP`. Прыжки через шаги запрещены. ↳ `SYSTEM/AUTONOMY/self_construction_seals/ASSIGNMENT_AUTONOMOUS_SELF_CONSTRUCTION_STEP_SEAL_V1.md:6`

**Гейты (кто пропускает шаг).** Ничего не исполняется, пока все гейты не дали PASS: **Scientific/quality gate** — реальное ли это улучшение; **Hermes gate** — ревью законности/направления; **Codex gate** — код-сторона; плюс **PI Agent** — отдельный орган-аудитор: проверяет, настоящий ли эффект, или «фантик» (без PI система строит красивую ерунду). ↳ `core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json:276` · `Downloads/MEMORY SOCC/1/ChatGPT-Законность и автономия SOCC.txt:3084`

**Органы самостройки (файлы, не самоцель).** `CURRENT_ROUTE_AUTHORITY.json` — единственный канон «какой шаг сейчас законен» (дублей не плодить); **atomic-commit enforced self-building lane** — переходы маршрута только атомарным коммитом; **idempotent guard wrapper** — обёртка, проверяющая guard ПЕРЕД любой записью; **self-building effect auditor lane** — ловит шаги без материального эффекта; **observe → next → reconcile** — восстановление маршрута после дрейфа; **foreground runner** — исполняет один шаг на переднем плане, без демона. ↳ `core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json:19` · `:208` · `:644` · `:431` · `:342`

**Как ЗАПУСКАТЬ (по закону).** (1) Открой протокол передачи оператору `FOUNDATION/SOCC_OPERATOR_HANDOFF_START_PROTOCOL_V1.json` и канонический дашборд оператора `SYSTEM/INTERFACE/dashboard/SOCC_CANONICAL_OPERATOR_DASHBOARD_V1.json`. (2) Прочитай `current_lawful_next` в route authority — это единственный разрешённый следующий шаг. (3) Проведи его по цепочке гейтов и выполни **одну** foreground-сессию через wrapper-обёртку (она применяет guard до записи). (4) Дождись STOP, проверь proof. Маршрут сам перейдёт дальше. ↳ `core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json:442` · `:3` · `:105` · `:725`

**Как КОНТРОЛИРОВАТЬ (границы — это и есть безопасность).** Жёстко выключено и проверяется на каждом шаге: `daemon_running=false`, `background_loop_enabled=false`, `continuous_loop_enabled=false`, `network_used=false`, `scheduler_installed=false`, `agi_claim_allowed=false`, `one_shot_only=true`. Прямая запись в маршрут запрещена (`direct_route_write_forbidden`), только атомарный коммит. Любой шаг без реального эффекта отклоняется (`future_bounded_pass_requires_material_effect`). Есть снапшоты отката (`rollback_snapshots_enabled`) и guard-и против эскалации (`forbidden_escalation_guards_enabled`). Оператор в любой момент = freeze / review / stop. ↳ `core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json:131` · `:434` · `:132` · `:199` · `:532` · `:194`

**Доказательство, что РАБОТАЕТ (не на словах).** Закрыто **2 bounded-цикла** (`closed_cycles_count=2`, `self_building_cycle_count=2`), выполнено **2 контролируемых тика** (`controlled_tick_count=2`), подтверждена **повторяемость после 2 тиков** (`repeatability_after_2_ticks_confirmed=true`), `pass_rate=1.0`, `maturity_score=1.0`, статус `PASS`. Первый шаг самостройки **запечатан (SEALED)**; доказанный эффект `DRY_RUN_TICKS_EXECUTED_VALIDATED::1`. ↳ `core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json:50` · `:89` · `:516` · `:449` · `Downloads/MEMORY SOCC/1/ChatGPT-SOCC patch plan (1).txt:22774`

**Текущий статус и ЧЕСТНАЯ граница (на 2026-06-29).** Маршрут формально доведён до конца цепочки: `current_route=self_building_autonomy`, `entity_substrate_sealed=true`, `anna_mvp_sealed=true`, `current_lawful_next=ship_anna_mvp_to_first_clinic_v1`. НО честно: флаги ушли в «sealed/ship» быстрее, чем закрыт реальный продуктовый гейт, а автономный цикл встал из-за **мёртвого LLM-мозга (401/402)** — это деньги/доступ, а не ещё одна церемония. Настоящий `lawful_next` сейчас: восстановить мозг → перезапустить цикл → реальный пилот в клинике. ↳ `core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json:107` · `Downloads/ИСТОРИЯ РАБОТЫ1.txt:2130` · `SOVEREIGN/WIKI/main_lines/entity_substrate.md`

---

### ОСНОВНАЯ ЛИНИЯ (вывод для самоэволюции)

Самостройка — это **двигатель самоэволюции SOCC**: система не ждёт оператора на каждый чих, а сама берёт следующий законный шаг и растёт по proof. Она уже доказана на малом (2 цикла, 2 тика, repeatability, sealed) — это не идея, а работающий орган. Её закон прост и строг: **один ограниченный шаг → все гейты PASS → материальный эффект → proof → стоп**, и никогда — демон/сеть/24-7/AGI без доказательства. Чтобы самоэволюция стала непрерывной, нужны три вещи: (1) живой мозг (см. [[anna]] — блокер 401/402), (2) вики как зеркало сознания (система должна видеть себя целиком, чтобы знать, какой шаг брать — см. [[memory_wave]], [[socc]]), (3) каждый новый шаг — через ту же законную цепочку. Управление всегда у оператора: route authority — руль, гейты — тормоза, proof — фары.

## Память — Memory Wave + живая вики (знание системы)
Единая память SOCC: одна Memory Wave (опыт/proof/граф) + живая Википедия как знание-перед-стройкой. Сущности получают surface, отдельного корня памяти не создают. Эта вики — память самой системы.

<!-- AUTHORED MAIN LINE. Survives spine rebuilds. Edited by operator/Claude, not by the deterministic builder.
     Topic: Память — Memory Wave + живая вики. Last authored: 2026-08-18.
     Overrides the deterministic "Current Authority" noise below (code-fragment MEMORY_DIR lines, boilerplate). -->

**Одной фразой.** Память SOCC — это **один орган в двух слоях**: **Memory Wave** (опыт/proof/отчёт/граф — что реально произошло и с каким эффектом) и **живая Википедия** (знание-перед-стройкой — что это значит в нашем контексте). Сущности получают *surface* к этой памяти, отдельного корня памяти не создают. Эта вики — память самой системы о самой себе. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Анализ кода и review.txt:34038`

**Зачем.** Чтобы расти по доказательству, а не по заявлениям: каждая волна обязана дать **БЫЛО→СТАЛО, validator, proof, Memory Wave, score delta и lawful_next**. Без Memory Wave нет continuity — система забудет, что уже доказала. ↳ `SOVEREIGN/MEMORY/inbox/автоматизация - 1.txt:20216`

**Главный закон памяти.** Memory Wave обязана хранить **смысл, а не только отчёты**. Дамп логов — не память; память — это извлечённый смысл, который можно поднять перед следующим действием. ↳ `SOVEREIGN/MEMORY/inbox/автоматизация - 1.txt:6069`

**Граница (truth_boundary).** Внешнее знание — только контекст. Оно информирует понимание и валидаторы, но **не может перебить Route Authority, proof-chain, Memory Wave или гейты оператора**. Вики/доки дают архитектуру и канон, но обязаны сверяться с последним proof. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Автономия и ANNA (2).txt:4295` · `Downloads/MEMORY SOCC/1/ChatGPT-Автономия и ANNA (2).txt:36905`

**Как это работает на практике (Context Assembly Gate).** Не грузить всё подряд — перед действием собирать *правильный пакет*: route authority, статус автономии, relevant Memory Wave, wiki-дайджест, прошлые ошибки, запреты, expected effect, validator, proof requirements. Это сердце «бесконечного контекста» без каши. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Оценка развития и автономии.txt:6594` · `Downloads/MEMORY SOCC/1/ChatGPT-Автономия и ANNA (2).txt:21212`

**Чем НЕ является.** Не архив и не второй Buildroom/Hermes/PI/Codex/Validator — память **не дублирует** существующие органы, она их питает. ↳ `SOVEREIGN/MEMORY/inbox/автоматизация - 1.txt:13195`

**Что РЕАЛЬНО построено и проверяемо сегодня.** Живая вики v2 работает: `scripts/socc/socc_memory_spine_v2.py` детерминированно (no-LLM, no-network, no-daemon) собирает `SOVEREIGN/WIKI/spine2/` — темы по СМЫСЛУ (`TOPIC_MAP_V1`), near-dup дедуп, схлопывание boilerplate, кэш по sha16. Пересборка 2026-08-18: **576 источников, 7 смысловых тем, ~5.5 c** (после тёплого кэша — секунды). Каждый пункт страницы ведёт к сырью `path#Lnn`. ↳ `SOVEREIGN/WIKI/spine2/_spine2_proof.json`

**Важно про «Current Authority» ниже.** Детерминированный слой по newest-wins всё ещё поднимает код-фрагменты (`MEMORY_DIR=…`) и повторяющийся boilerplate — это шум извлечения, а не сегодняшняя правда. Эта authored-линия — текущая истина темы.

---

### ОСНОВНАЯ ЛИНИЯ (вывод для самостройки)

Память — это фундамент, на котором стоит вся дисциплина роста: **Memory Wave помнит эффект, вики держит смысл, оба подчинены proof** (см. [[law_proof]]). Реальный следующий шаг темы уже сделан этой волной — v2-вики пере-собрана и снова видит актуальную работу. Дальше: (1) вязать новые сущности к единой памяти через lawful surface, не плодя корни; (2) держать Context Assembly Gate живым — перед каждым автономным тиком собирать пакет из proof/memory/wiki/raw; (3) не давать вики устареть — пере-запускать spine v2 после каждой крупной волны. Первая сущность на этой памяти — [[anna]]; долгий горизонт органа знания — [[vision]]; кто такая система в целом — [[socc]].

## Закон и доказательство — Proof, гейты Codex/Hermes
Метод-закон SOCC: ничего не исполняется без proof и PASS всех гейтов. Proof-chain, Codex (код), Hermes (ревью/научный гейт). Это дисциплина против фантом-ОК.

<!-- AUTHORED MAIN LINE. Survives spine rebuilds. Edited by operator/Claude, not by the deterministic builder.
     Topic: Закон и доказательство — Proof, гейты Codex/Hermes. Last authored: 2026-08-18.
     Overrides the deterministic "Current Authority" noise below (duplicate "supramental-agent proof-chain" lines). -->

**Одной фразой.** Закон SOCC — **метод, а не декларация**: ничего не исполняется без proof и без PASS всех гейтов. Это дисциплина против «фантом-ОК» — когда что-то *выглядит* сделанным, но не доказано. ↳ `SOVEREIGN/MEMORY/inbox/автоматизация - 1.txt:20216`

**Разделение ролей (кто что решает).** SOCC решает **что и зачем**; Hermes/PI формируют **bounded contract** (границы задачи); Codex делает **как** (код); валидаторы решают **«прошло или нет»**; Memory Wave **помнит эффект**. Ни одна роль не выходит за свою границу. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Автономия и ANNA (2).txt:15915`

**Hermes — настоящий, не концепт.** Это packet-state-machine в `core/socc/hermes_repair/`: состояния + 15+ типов ремонтных пакетов + proof. Hermes не действует вне очереди/ремонта; Codex не действует вне bounded-контракта. ↳ `Downloads/21июнятерминал.txt:1059` · `SOVEREIGN/MEMORY/inbox/автоматизация - 1.txt:17593`

**Что proof'ом НЕ является.** Имя — не доказательство: Layer 10 прямо запрещает *naming as proof*, Layer 9 требует **exact sameness, а не поверхностное сходство**. Устойчивая связь сама по себе — недостаточное доказательство. Continuity, защищённая только тем, что «имя то же», — конституционно недостаточна. ↳ `SOVEREIGN/MEMORY/inbox/Приветствие.md:2455` · `SOVEREIGN/MEMORY/inbox/8.4 уже сделано (4).md:16052`

**Порядок перед автоматикой.** Прежде чем дать системе auto-repair через Hermes/Codex, она обязана **уметь объяснять решение**: evidence, отклонённые альтернативы, причина, ожидаемый и фактический эффект, proof, БЫЛО→СТАЛО. Auto-repair без decision-journal — опасная слепая автоматика. ↳ `SOVEREIGN/MEMORY/inbox/автоматизация - 1.txt:7563`

**Граница названий.** SOCC — не Hermes. SOCC — суверенное ядро/оператор-консоль; Hermes — один из её органов (ревью/ремонт). Их нельзя смешивать. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Что такое SOCC (1).txt:316`

**Как proof переносит легитимность.** Наследование от старого supramental-agent законно **только через exact PASS proof-chain** — миграция сохранена доказательством, а не заявлением о преемственности. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Законность и автономия SOCC.txt:35566`

---

### ОСНОВНАЯ ЛИНИЯ (вывод для самостройки)

Это самый несущий закон системы: **рост = доказательство**. Любая волна, любой орган, любая сущность проходят один путь — `direction → plan → gates (Codex/Hermes/validator) → bounded execution → proof → seal`, с честным readiness-ledger и правом оператора на гейт. Именно поэтому [[memory_wave]] хранит смысл и эффект (без памяти нет continuity доказательств), поэтому [[anna]] не «лепится руками», а рождается через ту же цепочку, и поэтому даже дальний горизонт [[vision]] обязан приходить по proof, а не по хайпу. Дисциплина против фантом-ОК — это то, что отличает SOCC (см. [[socc]]) от «красиво прошедшего атомного шаблона».

## Видение — Supramental / AGI-направление
Долгосрочное направление (10 лет, AGI): самопознающий организм знания, который сам находит пробелы/конфликты и растёт по proof. Включает родственные сущности (Тамагуру).

<!-- AUTHORED MAIN LINE. Survives spine rebuilds. Edited by operator/Claude, not by the deterministic builder.
     Topic: Видение — Supramental / AGI-направление. Last authored: 2026-08-18.
     HONEST: this is DIRECTION (10-year horizon), not built capability. Overrides thin deterministic noise below. -->

**Одной фразой.** Дальний горизонт SOCC (10 лет, направление AGI) — **самопознающий организм знания**: система, которая сама находит свои пробелы и конфликты и растёт по proof, а не по заявлениям. Это направление, а не построенная способность. ↳ `Downloads/АССИСТЕНТ АННА - Разработка персонального агента.md:203`

**Что такое Тамагуру.** Тамагуру — это **узел понимания**: система понимает не просто «что это», а *что это для чего и как это в контексте нашей SOCC*. Не отдельный продукт — часть ядра, слой смысла над всем. ↳ `Downloads/MEMORY SOCC/1/ChatGPT-ПАМЯТЬ.txt:11564`

**Супраментал-эджент — почему это сильная идея.** Не потому, что «про сильный AI», а потому что это инженерный тезис с архитектурой, механизмами, рисками и bottlenecks, разложенный в roadmap 2026→2030. Сила — в дисциплине материализации, а не в громкости. ↳ `SOVEREIGN/MEMORY/inbox/Персональныи_ агент 1.md:3747` · `SOVEREIGN/MEMORY/inbox/Персональныи_ агент 1.md:2920`

**Главный bottleneck (честно).** Текущая активная точка — first living cycle, и узкое место названо прямо: **materialization + memory + eval + runtime enforcement**. То есть проблема не в «идее AGI», а в том, чтобы каждый цикл реально материализовался, помнился, оценивался и удерживался рантаймом. ↳ `Downloads/АССИСТЕНТ АННА - Разработка персонального агента.md:203`

**Откуда пришла родословная.** Направление наследует от старого supramental-agent, который **законно принят как рабочая база** после миграции в новый корень SOCC — и принят только через proof-chain, не через заявление о преемственности (см. [[law_proof]]). ↳ `Downloads/MEMORY SOCC/1/ChatGPT-Законность и автономия SOCC.txt:31599`

**Чем НЕ является (граница честности).** Это **самая тонкая тема вики** (мало текущей истины, много спорных упоминаний) — и это правильно: видение не должно выдаваться за построенное. Родственные сущности (Тамагуру и др.) и «приносит деньги ежедневно» — это цель-развилка, а не факт. AGI не заявляется; он либо приходит по proof, либо остаётся направлением. ↳ `Downloads/MEMORY SOCC/1/Ozon - MAIN OZON.txt:383`

---

### ОСНОВНАЯ ЛИНИЯ (вывод для самостройки)

Видение — это компас, а не отчёт. Его роль — **не дать системе забыть, куда она в итоге идёт** (самопознающий организм знания), пока ближние волны приносят реальную ценность. Практический перевод горизонта на сегодня: каждый построенный орган ([[anna]], торговые органы, память) — это один материализованный «living cycle», а не абстракция; каждый закрывается по proof (см. [[law_proof]]) и помнится в [[memory_wave]]. Так дальний AGI-горизонт остаётся честным: он строится снизу доказанными циклами, а не декларируется сверху. Кто такая система, которая это несёт, — см. [[socc]].


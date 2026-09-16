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

# ANNA L2 — Реальная запись (Direction V1)

STATUS::DIRECTION_CANDIDATE  NEXT::review_anna_l2_real_booking_direction_v1
LAYER::L2 (карта ANNA_REAL_PRODUCT_ROADMAP_V1)  ·  PRECOND: L1 resilient (ранги 1/2/5 ✅)

> Документ-только. Ничего не исполняет, к внешним системам клиники НЕ подключается без её явных кредов и согласия.
> Это твой гейт review/accept перед стройкой. Написан соло (workflow-ресёрч завис → убит, чтобы не ждать впустую);
> поэтому фактическая интеграционная феасибилити помечена честно UNVERIFIED — no-fake-pass.

## Зачем (боль продукта)
Сейчас «запись» ANNA — это локальный JSON, который не видит ни один реальный календарь клиники. Для клиники
это не запись, а заметка в чужом файле. Без приземления в её рабочий процесс продукт не продаётся (L2 ABSENT в карте).

## Что есть сейчас (правда из кода, `scripts/anna_runtime_v1.py`)
- `_book(data)` → пишет `SYSTEM/ANNA_MVP/runtime/appointments/<client>-<stamp>.json`, поле `status:"requested"`,
  идемпотентность по service+time в окне 10 мин. Данные: `{service, preferred_time, name, phone, notes}`.
- `_notify_admin()` → человекочитаемая карточка `cards/*.md` + событие в `admin_inbox.jsonl` (его читает дашборд)
  + опциональный `ANNA_ADMIN_WEBHOOK` (сети по умолчанию нет).
- `_scrub_booking()` / `_extract_booking()` — анти-галлюцинация: телефон/имя, которых клиент не писал, не попадают в запись.
- **Чего нет:** приземления в реальный календарь/CRM, подтверждения клиенту по факту брони, напоминания,
  переноса/отмены, защиты от двойной записи на стороне клиники.

## Честный ledger готовности
- booking_capture (захват намерения → структура): **HAVE** — `_book`/`_extract_booking`, анти-галлюцинация.
- operator_surface (ресепшн видит лид): **PARTIAL** — `admin_inbox.jsonl` + карточка есть; нет подтверждения обратно клиенту.
- real_calendar_write (запись в систему клиники): **ABSENT**.
- confirmation_loop (клиент узнаёт, что реально записан): **ABSENT**.
- reminder / reschedule / cancel: **ABSENT**.
- yclients_api_feasibility: **UNVERIFIED** — доступ к API, вероятно, за партнёрством/одобрением + токен клиники; не проверял в этой сессии.
- dikidi_api_feasibility: **UNVERIFIED**.
- gcal_api_feasibility: **PARTIAL/UNVERIFIED** — Google Calendar API документирован (OAuth/service-account, создание события), но в коде не интегрирован.

## Тонкий вертикальный срез (что строим первым — честный выбор)
**Manual confirmation loop (backend `manual`)** — единственное, что (а) строится без внешнего партнёрства,
(б) работает у ЛЮБОЙ клиники, (в) stealth-безопасно (запись «от живого админа»). Это и есть реальная запись
с точки зрения клиники: ANNA собрала структуру → ресепшн подтвердил в СВОЕЙ системе → ANNA подтвердила клиенту
по факту + поставила напоминание. Никаких API-кредов чужих систем на старте.
- **Первая API-интеграция (следующий фронтир):** Google Calendar как универсальный (клиника даёт свой календарь).
- **YClients/Dikidi:** заперты за реальным партнёрством/кредами клиники — UNVERIFIED, не на тонком срезе.

## Booking-spine (дизайн абстракции, без кода сейчас)
`_book()` роутит в один из бэкендов по конфигу клиники: `manual` (дефолт, везде) → `gcal` → `yclients`/`dikidi`.
Единый интерфейс: `create(appt) -> {ok, external_id|None, needs_confirmation}`, `confirm()`, `remind()`, `cancel()`.
Текущий локальный JSON остаётся журналом истины под всеми бэкендами.

## Законная под-цепочка L2 (mirror 18-шаговой ANNA MVP)
1. review_anna_l2_real_booking_direction_v1
2. accept_anna_l2_real_booking_direction_v1
3. build_anna_l2_construction_plan_v1  (booking-spine + manual loop)
4. review_anna_l2_construction_plan_v1
5. run_anna_l2_scientific_gate_v1
6. run_anna_l2_hermes_gate_v1
7. run_anna_l2_codex_gate_v1
8. review_anna_l2_plan_and_gates_v1 → 9. accept_…
10. build_anna_l2_bounded_execution_surface_v1 (manual backend + confirmation/reminder)
11. review → 12. accept
13. run_anna_l2_bounded_execution_session_v1 (локальный e2e: лид → подтверждение → напоминание, без сети)
14. validate → 15. review → 16. accept
17. seal_anna_l2_manual_loop_v1
18. ship_to_first_clinic (= вход в L3 — реальная клиника докажет ценность)

## Гейты
- Научный: запись детерминированно идемпотентна, двойной брони нет, телефон/имя не выдуманы.
- Hermes: тон подтверждения/напоминания человеческий, stealth не нарушен.
- Codex: backend-абстракция чистая, локальный journal — единый источник истины, fallback на `manual` всегда жив.

## Границы (no-fake-pass)
- К YClients/Dikidi/Google НЕ подключаемся без явных кредов и согласия клиники. Никакой авто-записи в чужую систему втихую.
- Stealth: подтверждение/напоминание звучат как живой админ; никаких «бот записал вас».
- Никаких заявок про выручку — это докажет L3 (реальная клиника), не L2.
- Реальная неубиваемость рантайма (L1) — на always-on хосте; пока RESILIENT, не unkillable (открытое операторское решение).

# SOCC — с чего начать (порядок, 2026-07-13)

Один файл. Открыл → понял → делаешь.

---

## Решение (зафиксировано)

**14 дней: Mint first ₽.**  
ANNA — только фон (ключ / health). Клиники и 25k/мес — **после** первого verified ₽.

| Приоритет | Что | Зачем |
|---|---|---|
| **#1** | Продать Telegram-бот-автоответчик за **1500 ₽** | Первый реальный ₽ в каноне |
| **#2** | Оживить LLM-ключ ANNA | Чтобы потом был live demo |
| **⏸** | Пилот клиник / ship ANNA | После M1 (₽) + A0 (health 🟢) |

Линия: `ln-cee92000` · узел M1 · main.

---

## Ты здесь

| | |
|---|---|
| real_money (mint) | **0** |
| ANNA brain | 🔴 403 freemodel org disabled |
| botfactory | ✅ BF-T1..T5 pass, демо-конфиг готов |
| Клиники | 55 candidates — **не трогать на этой неделе** |

---

## Что делать тебе (мир, не код)

### Сегодня / завтра

1. **BotFather** → новый бот → скопировать token  
2. Запустить демо:
```bash
cd ~/SOCC/scripts/mint/botfactory
# подставь свой Telegram user id в owner_chat_id в config.demo_prodazha.json
BOT_TOKEN=... .venv/bin/python socc_botfactory_v1.py config.demo_prodazha.json
```
3. **45 мин** спрос: YouDo / Avito «Требуется» / Kwork — посчитать свежие «нужен бот»  
4. **5–15 откликов** текстом ниже + ссылка на демо-бота  

### Текст отклика (copy-paste)

> Настрою Telegram-бота-автоответчика за 1 день — 1500 ₽.  
> Бот отвечает 24/7 (цены/адрес/часы) и собирает заявки вам в Telegram.  
> Покажу демо до оплаты: @ВАШ_ДЕМО_БОТ  
> Самозанятый, чек НПД. Первым клиентам 1500 ₽ за честный отзыв.

### Когда деньги пришли

```bash
cd ~/SOCC
python3 scripts/mint/socc_mint_record_v1.py \
  --service "Telegram-бот автоответчик" --amount 1500 \
  --lead-ref "direct-или-id-заявки" \
  --source moy_nalog_receipt --ref "id-чека" --inn ТВОЙ_ИНН --commit
```

Полный рунбук: `scripts/mint/P3_FIRST_LEAD_RUNBOOK.md` · закрытие: `scripts/mint/M1_CLOSE.md`

---

## Параллельно (≤30 мин, не вместо откликов)

```bash
# когда будет рабочий ключ (не мёртвый freemodel):
# дописать в .secrets/anna_llm.env  OPENAI_API_KEY=... или ANTHROPIC_API_KEY=...
python3 scripts/anna_runtime_v1.py --health   # нужно 🟢
```

---

## Открывать

| Зачем | Путь |
|---|---|
| Этот порядок | `START_HERE.md` |
| First ₽ рунбук | `scripts/mint/P3_FIRST_LEAD_RUNBOOK.md` |
| Демо-конфиг | `scripts/mint/botfactory/config.demo_prodazha.json` |
| Запись ₽ | `scripts/mint/socc_mint_record_v1.py` |
| ANNA (потом) | `SOVEREIGN/ANNA/ANNA_PRODUCT_CANON_V1.md` |

## Склад (не трогать)

`MIGRATION/`, `MEMORY_WAVE/`, self-building ceremony, 55 клиник cold, mint universe expansion, новые proof-цепи.

---

## Правило

Сессия без **отклика или сделки** = сессия в минус.  
Код только если сломалась доставка бота клиенту.

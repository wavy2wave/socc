#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT brain adapter V1 — ЖИВОЙ мозг в черновики AUTOPILOT (шаг 2 автономного фронта).

Переиспользует существующий мозг SOCC: anna_runtime_v1.llm_complete (fast API → free gateway → claude CLI).
Даёт draft_fn(lead, offer) → персональный оффер КАК представитель бизнеса оператора: с раскрытием, без
выдумки конкретной чужой личности, без гарантий дохода, с предложением демо и чека НПД.

Честность к транзиенту (см. auto-retry-transient-blocks): мозг недоступен/пуст/ошибка → детерминированный
fallback (autopilot._stub_draft). Фронт НИКОГДА не падает и НИКОГДА не шлёт без approve (RUBICON).
Логика тестируется без сети: _draft_with(lead, offer, llm) принимает любую llm-функцию.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))  # чтобы найти scripts/anna_runtime_v1.py
import socc_mint_autopilot_v1 as autopilot  # noqa: E402

# Инструкция мозгу — зашивает закон фронта прямо в системный промпт.
SYSTEM = (
    "Ты — представитель бизнеса самозанятого исполнителя услуг ИИ/автоматизации (Telegram-боты, настройка "
    "нейросетей, автоматизация рутины). Пиши короткий персональный честный ответ на запрос клиента. "
    "ОБЯЗАТЕЛЬНО: раскрой, что это предложение услуги; предложи демо/пример ДО оплаты; упомяни, что "
    "работаешь как самозанятый и дашь чек НПД. ЗАПРЕЩЕНО: выдавать себя за конкретного ДРУГОГО живого "
    "человека или за обладателя диплома/лицензии, которых нет; обещать гарантированный доход/результат; "
    "спамить. 4–6 предложений, по-русски, по делу."
)


def _user_prompt(lead, offer):
    return (f"Запрос клиента: услуга «{lead.get('service')}», ориентировочный бюджет ~{offer.get('price')} ₽.\n"
            f"Текст запроса: {lead.get('raw_text', '') or '(без текста)'}\n"
            f"Напиши персональный ответ-оффер по правилам системного промпта.")


def _draft_with(lead, offer, llm):
    """Черновик через ЛЮБУЮ llm-функцию llm(system, messages)->(text, err). Fallback на стаб при проблеме."""
    try:
        text, err = llm(SYSTEM, [{"role": "user", "content": _user_prompt(lead, offer)}])
    except Exception:
        text, err = None, "brain_exception"
    if err or not text or not str(text).strip():
        return autopilot._stub_draft(lead, offer)  # транзиент/нет ключей → детерминированный fallback
    return str(text).strip()


def _real_llm(system, messages):
    import anna_runtime_v1 as brain  # ленивый импорт: dry/тесты работают без сети
    return brain.llm_complete(system, messages)


def draft_fn(lead, offer):
    """Готовый draft_fn для AUTOPILOT/коннекторов: живой мозг с fallback. Не падает, не шлёт."""
    try:
        return _draft_with(lead, offer, _real_llm)
    except Exception:
        return autopilot._stub_draft(lead, offer)


if __name__ == "__main__":
    import json
    lead = {"service": "Telegram-бот автоответчик", "ticket_value": 1500,
            "raw_text": "Нужен бот для записи клиентов в барбершоп", "lead_ref": "demo"}
    offer = {"price": 1500}
    text = draft_fn(lead, offer)
    print(json.dumps({"draft": text, "len": len(text),
                      "note": "живой мозг, если доступен; иначе честный fallback-стаб"}, ensure_ascii=False, indent=2))

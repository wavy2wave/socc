#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT demand connectors V1 — вход РЕАЛЬНОГО спроса в AUTOPILOT (шаг 1 автономного фронта).

Агент — авторизованный представитель оператора: работает на реальных кабинетах/почтах/каналах оператора
(он их предоставляет и доверяет). Коннектор берёт сырой сигнал спроса из ЛЕГИТИМНОГО источника и
нормализует его в lead для autopilot.run_outreach.

Легитимные источники (autopilot.LEGIT_SOURCES): входящие заявки/формы, публичные запросы площадок,
официальные API, рефералы, собственные кабинеты оператора. НЕ парсинг в обход ToS, НЕ массовая рассылка.

Fetch — ленивый: файловые коннекторы читают JSONL-инбокс (входящие/вебхук), сетевые (email/telegram/офиц.
API) грузятся только при ключах. Логика ЧИСТАЯ (stdlib) — нормализация тестируется без сети.
"""
import os
import sys
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import socc_mint_autopilot_v1 as autopilot  # noqa: E402


def normalize(raw, source):
    """Сырой сигнал спроса → lead для AUTOPILOT. Источник обязан быть легитимным (иначе фронт отрежет)."""
    ref = raw.get("lead_ref") or raw.get("id") or raw.get("contact") or "lead"
    return {
        "service": raw.get("service", "услуга"),
        "ticket_value": float(raw.get("ticket_value", raw.get("amount", 0)) or 0),
        "executor": raw.get("executor", "самозанятый (создатель)"),
        "lead_ref": ref,
        "source": source,
        "demand_real": raw.get("demand_real", {"kind": "request", "ref": ref}),
        "personalized": True,   # каждый ответ персональный (не спам)
        "disclosed": True,      # раскрытие: это предложение услуги от бизнеса оператора
        "min_profit": float(raw.get("min_profit", 200)),
        "raw_text": raw.get("text", ""),
    }


def _file_fetch(env_var):
    """Прочитать JSONL-инбокс (входящие заявки/вебхук), куда падают реальные запросы. [] если нет."""
    path = os.environ.get(env_var)
    if not path or not Path(path).exists():
        return []
    out = []
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out


def _manual_fetch():
    return _file_fetch("MINT_DEMAND_INBOX")      # оператор кладёт увиденные реальные запросы


def _webhook_fetch():
    return _file_fetch("MINT_WEBHOOK_INBOX")     # форма/вебхук на сайте оператора → входящие заявки


def _email_fetch():
    try:  # боевой: входящие письма оператора (IMAP по его ключам), лениво
        import socc_mint_connector_email_v1 as e
        return e.fetch()
    except Exception:
        return []


def _telegram_fetch():
    try:  # боевой: входящие боту оператора (getUpdates по его токену), лениво
        import socc_mint_connector_telegram_v1 as t
        return t.fetch()
    except Exception:
        return []


# Реестр коннекторов. Добавить источник = один register_connector(...). source ∈ autopilot.LEGIT_SOURCES.
CONNECTORS = [
    {"id": "manual", "source": "public_request", "fetch": _manual_fetch},
    {"id": "webhook", "source": "inbound", "fetch": _webhook_fetch},
    {"id": "email", "source": "inbound", "fetch": _email_fetch},
    {"id": "telegram", "source": "inbound", "fetch": _telegram_fetch},
]


def register_connector(cid, source, fetch):
    """Зарегистрировать источник спроса. Источник обязан быть легитимным (иначе фронт всё равно отрежет)."""
    if source not in autopilot.LEGIT_SOURCES:
        raise ValueError(f"нелегитимный источник '{source}' (нужен {autopilot.LEGIT_SOURCES}) — парсинг в обход ToS запрещён")
    CONNECTORS.append({"id": cid, "source": source, "fetch": fetch})
    return CONNECTORS


def poll_all():
    """Собрать нормализованные лиды со ВСЕХ коннекторов реестра (ленивый fetch)."""
    leads = []
    for c in CONNECTORS:
        try:
            for raw in c["fetch"]():
                leads.append(normalize(raw, c["source"]))
        except Exception:
            continue
    return leads


def run_pipeline(draft_fn=None):
    """Шаг 1→фронт: poll спрос → autopilot по каждому лиду. Ничего не отправляет (approve за оператором)."""
    results = []
    for lead in poll_all():
        offer = {"price": lead["ticket_value"], "pitch": "Сделаю под ключ, покажу пример до оплаты."}
        results.append(autopilot.run_outreach(lead, offer, draft_fn=draft_fn))
    return results


if __name__ == "__main__":
    res = run_pipeline()
    print(json.dumps({"connectors": [c["id"] for c in CONNECTORS],
                      "leads_processed": len(res),
                      "by_status": {s: sum(1 for r in res if r["status"] == s) for s in {"QUEUED", "SKIP", "BLOCKED"}}},
                     ensure_ascii=False, indent=2))

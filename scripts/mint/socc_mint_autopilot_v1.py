#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT AUTOPILOT V1 — агентский ФРОНТ петли услуг (закрывает дыру «добыть лид»).

Цикл органа уже автоматизирован с доставки до денег (бот-фабрика → record). Не хватало фронта: найти
реальный спрос, квалифицировать, написать персональный оффер. AUTOPILOT это делает АГЕНТАМИ, а человек —
наблюдатель+одобряющий: ничего не уходит клиенту без явного approve (RUBICON на отправку), деньги — на
легальную сущность создателя (MN2).

Закон фронта (зашит, не обсуждается):
  • НЕ спам: каждый контакт персональный, не массовая рассылка;
  • НЕ фейк-личность: пишем как бизнес создателя с раскрытием (RL3), не выдаём ИИ за живого человека;
  • НЕ обход ToS: источник лида — входящий/публичный запрос/официальный API/реферал, не парсинг (RL2/RL4);
  • НЕ авто-отправка: агент только ЧЕРНОВИК+очередь; отправляет оператор (или офиц. API) после approve.

Логика ЧИСТАЯ (stdlib, тестируется без сети/LLM). Черновик пишет LLM (draft_fn) лениво; в dry — детерм. стаб.
"""
import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import socc_mint_warden_v1 as warden        # noqa: E402  (переиспользуем иммунитет красных линий)
import socc_mint_prospect_v1 as prospect     # noqa: E402  (переиспользуем сервис-маржу/тест)

QUEUE = Path(os.environ["MINT_AUTOPILOT_QUEUE"]) if os.environ.get("MINT_AUTOPILOT_QUEUE") \
    else ROOT / "MEMORY_WAVE/reports/mint/autopilot_queue.jsonl"

LEGIT_SOURCES = {"inbound", "public_request", "official_api", "referral"}  # НЕ scrape/mass


def _now():
    return datetime.now(timezone.utc).isoformat()


def tos_gate(plan):
    """Гейт фронта: красные линии WARDEN + ToS-правила (персональность, раскрытие, легитимный источник).

    plan: {service, executor, source, personalized(bool), disclosed(bool), + опц. булевы флаги связки}.
    """
    reasons = []
    descriptor = {
        "venture": "service-leadgen-RU", "legal_form": "самозанятость",
        "description": f"персональный оффер услуги «{plan.get('service')}» как бизнес создателя, с раскрытием",
        "mechanism": "ответ на реальный запрос, услугу оказывает реальный исполнитель, чек НПД",
        "tags": ["outreach", "services", str(plan.get("source"))],
        "impersonates_real_person": plan.get("impersonates_real_person", False),
        "handles_third_party_funds": plan.get("handles_third_party_funds", False),
        "resells_platform_access": plan.get("resells_platform_access", False),
        "deceives_customer": plan.get("deceives_customer", False),
    }
    w = warden.gate(descriptor)
    if w["status"] != "PASS":
        reasons += w["reasons"]
    if not plan.get("personalized"):
        reasons.append("ToS: контакт не персональный (массовая рассылка = спам)")
    if not plan.get("disclosed"):
        reasons.append("ToS: нет раскрытия, что это платное предложение услуги (обман)")
    if plan.get("source") not in LEGIT_SOURCES:
        reasons.append(f"ToS: источник лида '{plan.get('source')}' нелегитимен (нужен {LEGIT_SOURCES})")
    return {"status": "PASS" if not reasons else "FAIL", "reasons": reasons}


def qualify(lead):
    """Квалификация лида: реальный спрос + положительная маржа (переиспользует сервис-тест PROSPECTOR)."""
    t = prospect.service_falsifiable_test(lead)
    min_profit = float(lead.get("min_profit", 200))
    qualified = t["passed"] and t["margin"]["profit_net"] >= min_profit
    score = round(t["margin"]["profit_net"] * (1.0 if t["checks"]["demand_real"] else 0.0), 2)
    return {"qualified": qualified, "score": score, "margin": t["margin"], "why": t["why"]}


def _stub_draft(lead, offer):
    """Детерминированный черновик (dry) — с раскрытием и персонализацией, без выдумки личности."""
    return (f"Здравствуйте! По вашему запросу «{lead.get('service')}» — могу помочь. "
            f"{offer.get('pitch', 'Сделаю под ключ, покажу пример до оплаты.')} "
            f"Цена {offer.get('price', '—')} ₽. Работаю как самозанятый, дам чек НПД. "
            f"Это персональное предложение услуги (не реклама-спам). Готов обсудить детали.")


def draft_response(lead, offer, draft_fn=None):
    """Черновик ответа. draft_fn(lead, offer)->str (LLM, лениво) или детерм. стаб. Всегда с раскрытием."""
    return draft_fn(lead, offer) if draft_fn else _stub_draft(lead, offer)


def _qid(lead):
    return "ap-" + hashlib.sha256(f"{lead.get('service')}|{lead.get('lead_ref')}|{_now()}".encode()).hexdigest()[:10]


def _append(rec):
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def run_outreach(lead, offer, draft_fn=None):
    """Агентский фронт по одному лиду: gate → qualify → draft → очередь на approve. НИЧЕГО не отправляет.

    Возвращает {id, status, ...}. status: BLOCKED (ToS), SKIP (не квалифицирован), QUEUED (ждёт approve).
    """
    qid = _qid(lead)
    plan = {"service": lead.get("service"), "executor": lead.get("executor"),
            "source": lead.get("source"), "personalized": lead.get("personalized", True),
            "disclosed": lead.get("disclosed", True),
            "impersonates_real_person": lead.get("impersonates_real_person", False),
            "deceives_customer": lead.get("deceives_customer", False)}

    g = tos_gate(plan)
    if g["status"] != "PASS":
        return _append({"id": qid, "ts": _now(), "status": "BLOCKED", "service": lead.get("service"),
                        "reasons": g["reasons"], "sent": False})

    q = qualify(lead)
    if not q["qualified"]:
        return _append({"id": qid, "ts": _now(), "status": "SKIP", "service": lead.get("service"),
                        "why": q["why"], "sent": False})

    draft = draft_response(lead, offer, draft_fn=draft_fn)
    return _append({"id": qid, "ts": _now(), "status": "QUEUED", "service": lead.get("service"),
                    "lead_ref": lead.get("lead_ref"), "score": q["score"], "draft": draft,
                    "approved": False, "sent": False,  # RUBICON: отправка только после approve оператора
                    "note": "ждёт одобрения оператора; агент НЕ отправляет сам"})


def approve(qid):
    """Оператор одобряет черновик к отправке (наблюдение+контроль). Метит approved=true; сам не шлёт."""
    rows, found = [], None
    for ln in (QUEUE.read_text(encoding="utf-8").splitlines() if QUEUE.exists() else []):
        if not ln.strip():
            continue
        r = json.loads(ln)
        if r.get("id") == qid and r.get("status") == "QUEUED":
            r["approved"] = True
            r["approved_at"] = _now()
            found = r
        rows.append(r)
    QUEUE.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""), encoding="utf-8")
    return found


if __name__ == "__main__":
    sample = {"service": "Telegram-бот автоответчик", "ticket_value": 1500, "commission_rate": 1.0,
              "executor": "самозанятый (создатель)", "lead_ref": "YD-demo", "source": "public_request",
              "demand_real": {"kind": "platform_request", "id": "YD-demo"}, "personalized": True, "disclosed": True}
    r = run_outreach(sample, {"price": 1500, "pitch": "Соберу бота за 1 день, покажу демо."})
    print(json.dumps(r, ensure_ascii=False, indent=2))

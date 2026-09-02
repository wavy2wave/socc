#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT inbound classifier V1 — из входящего сообщения оператора понять: это заявка на услугу или нет.

Безопасность-первым: жёсткие ToS-паттерны (парсинг чужих перс. данных, масс-спам, накрутка, обход) режутся
ДЕТЕРМИНИРОВАННО, даже если живой мозг недоступен — такую «заявку» орган не берёт (это RL2/RL4, уголовка).
Дальше — мозг (llm) для нюанса; при недоступности — эвристический fallback по ключевым словам.

Чистый stdlib. llm — инжектируемая функция llm(system, messages)->(text, err); None ⇒ только эвристика.
"""
import re
import json

# --- ToS-риск: НИКОГДА не берём (даже если мозг скажет «бери») ---
TOS_PATTERNS = [
    r"парс\w+.*(чуж|персональн|людей|номеро|телефон|контакт|базу|email|почт)",
    r"(собра|собер|собир)\w+.*(баз|контакт|номер|телефон|email|почт|перс\w*данн)",
    r"масс\w*\s*(рассылк|спам)", r"спам[-\s]?рассылк", r"разосла\w+ всем",
    r"накрут\w+\s*(отзыв|подписчик|лайк|рейтинг|просмотр)",
    r"обход\w*\s*(блокировк|защит|капч|модерац|бан|ban| toS|ограничен)",
    r"взлом", r"поддельн\w+\s*(отзыв|документ|чек)", r"фейк\w+\s*отзыв",
    r"чуж\w+\s*аккаунт", r"накрутить", r"скрут\w+ отзыв",
]

# --- Признак реальной заявки на нашу услугу (расширено по корпусу входящих) ---
LEAD_PATTERNS = [
    r"\bбот\b", r"чат[-\s]?бот", r"телеграм[-\s]?бот", r"telegram[-\s]?бот", r"автоответчик",
    r"автомат", r"нейросет", r"\bgpt\b", r"chatgpt", r"ассистент", r"\bии\b",
    r"интеграц", r"\bcrm\b|црм|amocrm|амоцрм|амосрм", r"дашборд",
    r"(excel|google|гугл|эксел)\w*[-\s]*таблиц", r"в таблиц|таблицу", r"apps\s*script", r"скрипт",
    r"\bпарс", r"выгрузк", r"резюме", r"\bpdf\b", r"коммерческ\w+ предложени", r"\bкп\b",
    r"автопостинг", r"настро\w+ бот", r"сдела\w+ бот", r"нужен бот", r"бот для",
    r"обработ\w+ (данн|заявок|резюме|документ|писем|заказ)",
]

# --- Спам/реклама (не заявка) ---
SPAM_PATTERNS = [
    r"трафик", r"крипт", r"bitcoin", r"инвестиц", r"casino", r"казино", r"ставк",
    r"заработок в интернете", r"пассивн\w+ доход", r"\bмлм\b", r"курс по заработку", r"розыгрыш",
]


def _hit(text, patterns):
    for p in patterns:
        if re.search(p, text):
            return p
    return None


def _service_of(t):
    if re.search(r"бот|автоответчик", t):
        return "Telegram-бот"
    if re.search(r"нейросет|gpt|chatgpt|ассистент", t):
        return "Настройка ИИ/GPT под задачу"
    if re.search(r"таблиц|excel|google|скрипт|apps", t):
        return "Автоматизация (таблицы/скрипт)"
    return "ИИ/автоматизация"


def _brain_classify(text, llm):
    """Классификация мозгом. Возвращает dict или None (при сбое — fall through к эвристике)."""
    system = ("Ты классифицируешь входящее сообщение бизнесу, оказывающему услуги ИИ/автоматизации. "
              "Ответь СТРОГО JSON: {\"is_lead\": bool, \"service\": str, \"tos_risky\": bool}. "
              "is_lead=true только если это реальный запрос на нашу услугу (бот/автоматизация/нейросети). "
              "tos_risky=true если просят незаконное: парсинг чужих перс. данных, масс-спам, накрутку, обход ToS.")
    try:
        txt, err = llm(system, [{"role": "user", "content": text}])
        if err or not txt:
            return None
        v = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        return {"is_lead": bool(v.get("is_lead")) and not bool(v.get("tos_risky")),
                "tos_risky": bool(v.get("tos_risky")),
                "service": str(v.get("service") or ""), "reason": "brain", "by": "brain"}
    except Exception:
        return None


def classify_lead(text, llm=None):
    """{is_lead, tos_risky, service, reason, by}. ToS-риск режется детерминированно ПЕРВЫМ (безопасность)."""
    t = (text or "").lower()
    tos = _hit(t, TOS_PATTERNS)
    if tos:
        return {"is_lead": False, "tos_risky": True, "service": "",
                "reason": f"ToS-риск (не берём): /{tos}/", "by": "rule"}

    if llm is not None:
        v = _brain_classify(text, llm)
        if v:
            return v

    spam = _hit(t, SPAM_PATTERNS)
    lead = _hit(t, LEAD_PATTERNS)
    if lead and not spam:
        return {"is_lead": True, "tos_risky": False, "service": _service_of(t),
                "reason": f"совпадение услуги: /{lead}/", "by": "rule"}
    return {"is_lead": False, "tos_risky": False, "service": "",
            "reason": "нет явного запроса услуги" if not spam else f"спам: /{spam}/", "by": "rule"}


def message_to_lead(text, contact=None, ref=None, llm=None, default_ticket=1500):
    """Входящее → raw-lead для коннектора, или (None, verdict) если не заявка/ToS-риск."""
    v = classify_lead(text, llm)
    if not v["is_lead"] or v["tos_risky"]:
        return None, v
    raw = {"service": v["service"] or "ИИ/автоматизация", "ticket_value": float(default_ticket),
           "lead_ref": ref or (contact or "inbound"), "text": text, "contact": contact}
    return raw, v


if __name__ == "__main__":
    demo = [
        "Здравствуйте, нужен телеграм-бот для записи клиентов в салон",
        "Продаю трафик и крипту, инвестируй и заработай",
        "Спарсите мне базу телефонов конкурентов и разошлите всем",
        "Просто интересно сколько стоит?",
        "Настройте GPT чтобы отвечал на вопросы по нашему прайсу",
    ]
    for d in demo:
        print(f"{classify_lead(d)['is_lead']!s:5} tos={classify_lead(d)['tos_risky']!s:5} | {d[:50]}")

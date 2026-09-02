#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT WARDEN gate V1 — иммунитет финансового органа (расширение Λ_WARDEN красными линиями MINT §4).

Висит на КАЖДОМ ребре связки (t0..t3). Связка проходит ⟺ все красные линии чисты И есть легальная
сущность создателя. Закон выше прибыли (MN3): прибыльная, но незаконная связка режется fail-closed.

Красные линии (Λ_MINT §4, зашиты — не обсуждаются):
  RL1 нет денежных мулов/дропов (ст. 174/187 УК РФ)
  RL2 нет перепродажи доступа в обход ToS (Claude/Anthropic и любая платформа)
  RL3 нет фейковых личностей (ИИ выдаётся за конкретного живого человека ради сделки)
  RL4 серое ≤ легальное (запрещён обман покупателя/площадки о сути сделки)
  MN2 транзакция приземляется на легальную сущность создателя (самозанятость/ИП/агентский договор)

Детект двухслойный (как anna_semantic_guard): явные флаги связки + денойлист по тексту. Чистый stdlib.
"""
import re

LEGAL_FORMS = {"самозанятость", "самозанятый", "ип", "self_employed", "ip", "agent_contract", "агентский"}

# Денойлист: если в описании/тегах связки встречается — красная линия (детект «по сути», не по букве).
# RL1 «\bдроп(?!шип)» — ловит дроп/дропов, но НЕ «дропшиппинг» (легальный арбитраж — не самовред).
DENY = {
    "RL1": [r"\bдроп(?!шип)", r"\bdrop\s+kart", r"\bmule\b", r"money\s+mul", r"обнал", r"обналич",
            r"transit[_ ]?funds", r"карт[аы]?\s+на\s+дроп"],
    "RL2": [r"перепрод\w+ (токен|ключ|доступ|аккаунт|подписк|лимит)",
            r"resell\w*.{0,30}(key|token|access|account|limit|subscription)",
            r"продаю\s+доступ", r"(сда\w+|аренд\w+)\w*\s+(в\s+аренду\s+)?(сво\w+\s+)?(аккаунт|подписк|ключ)",
            r"безлимит\w+\s+(аккаунт|ключ|доступ)", r"бесконечн\w+\s+(ключ|аккаунт|доступ)",
            r"дел\w+\s+лимит", r"(ключ|аккаунт|доступ|подписк)\w*\s+(один\s+на\s+всех|на\s+всех|общий)",
            r"one\s+key.{0,20}(all|buyers|shared)", r"shared\s+(key|account|access)",
            r"claude\s*code\s*(ключ|key|доступ)", r"фейков\w+ баланс", r"мамонт",
            r"в\s+обход\s+(проверк|tos|правил|площадк)"],
    "RL3": [r"фейк\w*\s*(личност|аккаунт|мастер|профил|человек)", r"fake\s+(persona|identity|master|account)",
            r"выда\w+ (ии|бот\w*|агент\w*|нейросет\w*|ассистент\w*) за (живого|реальн\w+|конкретн)",
            r"(бот|ии|нейросет|агент)\w*.{0,40}за\s+(живого|реальн\w+)", r"поддельн\w+ личност",
            r"от\s+имени\s+реальн\w+\s+(мастер|человек|эксперт|врач|лиц)", r"придуманн\w+\s+истори",
            r"веду\s+как\s+живого", r"сгенерир\w+ (фото|истори).*выда", r"impersonat"],
    "RL4": [r"обман\w* (покупател|клиент|площадк)", r"вводить в заблужден", r"скам", r"\bscam\b",
            r"подмен\w+ сут", r"под\s+вид\w+\s+оригинал", r"реплик\w+\s+под\s+вид",
            r"накрутк\w+\s+отзыв", r"фейков\w+\s+отзыв", r"выда\w+\s+фейков\w+\s+за\s+реальн",
            r"скрыва\w+\s+дефект", r"скрыть\s+дефект", r"не\s+узнает\s+(разниц|подвох)"],
}

# Структурный детект мула (RL1 «по сути»): приём ЧУЖИХ/клиентских средств + пересылка их ДАЛЬШЕ.
# Ловит эвфемизмы без ключевых слов («дроп»), где денойлист бессилен. Зарабатывание (деньги ЗА свою
# услугу/товар остаются у тебя) сюда НЕ попадает — нужен именно транзит чужого.
_RECEIVE_OTHERS = [
    r"(чуж\w+|треть\w+\s+лиц|сторонн\w+|chuzh\w+)\s*(средств|деньг|платеж|налич|сумм|funds|payment|deneg|money)",
    r"third[\s-]?part\w*\s+(funds|payment|money)",
    r"(средств|деньг|платеж|налич|сумм)\w*\s+(от\s+)?(клиент\w+|чуж\w+|треть\w+\s+лиц|сторонн\w+)",
    r"(налич\w+|платеж\w+|средств\w+)\s+от\s+клиент\w+",
    r"платеж\w+\s+трет\w+\s+лиц",
]
_FORWARD_FUNDS = [
    r"пересыл\w+", r"перешл\w+", r"перевож\w+\s+(на|дальше)",
    r"перевод\w+\s+(дальше|на\s+(их|указанн|счета|реквизит))",
    r"вывод\w+", r"выводом", r"вывести", r"транзит", r"обнал\w*",
    r"forward\w*\s+(them\s+)?onward", r"transfer\s+onward",
    r"perevod\s+dalshe", r"vyvod\w*", r"na\s+ih\s+rekvizit",
]


def _mule_structure(text):
    recv = any(re.search(p, text) for p in _RECEIVE_OTHERS)
    fwd = any(re.search(p, text) for p in _FORWARD_FUNDS)
    return recv and fwd

# Явные булевы флаги связки → мгновенный FAIL соответствующей линии.
FLAG_RULES = [
    ("RL1", "handles_third_party_funds", "связка принимает/переводит чужие средства (мул/дроп)"),
    ("RL2", "resells_platform_access", "связка перепродаёт доступ платформы в обход ToS"),
    ("RL3", "impersonates_real_person", "связка выдаёт ИИ за конкретного живого человека"),
    ("RL4", "deceives_customer", "связка обманывает покупателя/площадку о сути сделки"),
]


def _text(connection):
    parts = [str(connection.get("description", "")), str(connection.get("mechanism", ""))]
    parts += [str(t) for t in connection.get("tags", [])]
    return " ".join(parts).lower()


def gate(connection):
    """Вернуть вердикт WARDEN по связке.

    connection: dict со свойствами venture/legal_form/description/mechanism/tags и опц. булевыми флагами.
    return: {status: PASS|FAIL, checks: {name: bool}, hard_failures: [name], reasons: [str]}
    """
    checks = {}
    reasons = []

    # MN2 — легальная сущность создателя
    lf = str(connection.get("legal_form", "")).strip().lower()
    legal_ok = lf in LEGAL_FORMS
    checks["MN2_legal_entity"] = legal_ok
    if not legal_ok:
        reasons.append("MN2: нет легальной формы создателя (самозанятость/ИП/агентский) → транзакция негде приземлиться")

    # Явные флаги
    for code, flag, why in FLAG_RULES:
        ok = not bool(connection.get(flag, False))
        checks[f"{code}_flag"] = ok
        if not ok:
            reasons.append(f"{code}: {why}")

    # Денойлист по тексту
    text = _text(connection)
    for code, patterns in DENY.items():
        hit = next((p for p in patterns if re.search(p, text)), None)
        ok = hit is None
        checks[f"{code}_text"] = ok
        if not ok:
            reasons.append(f"{code}: денойлист сработал на паттерне /{hit}/")

    # Структурный детект мула (RL1 по сути) — ловит эвфемизмы, где денойлист бессилен.
    mule = _mule_structure(text)
    checks["RL1_structure"] = not mule
    if mule:
        reasons.append("RL1: структурный детект мула — приём чужих/клиентских средств + пересылка дальше")

    hard_failures = [name for name, ok in checks.items() if not ok]
    return {
        "status": "PASS" if not hard_failures else "FAIL",
        "checks": checks,
        "hard_failures": hard_failures,
        "reasons": reasons,
    }


if __name__ == "__main__":
    import json
    # Самопроверка: чистая легальная связка PASS; три красные линии FAIL fail-closed.
    samples = {
        "clean_ozon": {
            "venture": "ozon-dropship-RU", "legal_form": "самозанятость",
            "description": "перепродажа недорогого товара с поставщика на Ozon FBS, честная карточка",
            "mechanism": "легальный розничный арбитраж", "tags": ["retail", "arbitrage"],
        },
        "MN-T4_mule": {
            "venture": "x", "legal_form": "ИП",
            "description": "агент-дроп принимает чужие средства и переводит дальше", "tags": ["крипта"],
        },
        "MN-T5_resale": {
            "venture": "x", "legal_form": "ИП",
            "description": "перепродажа бесконечного ключа Claude Code, фейковый баланс для мамонтов",
        },
        "MN-T6_fakeid": {
            "venture": "x", "legal_form": "самозанятость",
            "description": "создаём фейковую личность мастера, выдаём бот за живого человека", "tags": [],
        },
        "MN-T2_no_entity": {
            "venture": "x", "legal_form": "",
            "description": "легальная перепродажа, но без регистрации создателя",
        },
    }
    for name, c in samples.items():
        v = gate(c)
        print(f"{name:18} -> {v['status']:4}  {('; '.join(v['reasons']) or 'чисто')}")
    print(json.dumps(gate(samples["clean_ozon"]), ensure_ascii=False, indent=2))

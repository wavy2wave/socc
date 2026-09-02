#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT boевые коннекторы acceptance V1 — тесты email/telegram входа (IN-T1..IN-T5). Без сети.

Зелёный ⟺ входящие оператора превращаются в лиды через классификатор: реальная заявка → лид, спам/ToS/офтоп
отсеяны, пустой вход (нет ключей) безопасен. Тестируется чистая to_raws (без IMAP/Bot API).
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import socc_mint_connector_email_v1 as email_c        # noqa: E402
import socc_mint_connector_telegram_v1 as tg_c         # noqa: E402


def check(name, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return passed


BOT_MSG = {"subject": "Нужен бот", "body": "Хочу телеграм-бота для записи клиентов в барбершоп", "from": "client@x.ru", "id": "1"}
SPAM_MSG = {"subject": "Трафик", "body": "Продаём целевой трафик и крипту, заработок на автопилоте", "from": "spam@x.ru", "id": "2"}
TOS_MSG = {"subject": "Заказ", "body": "Спарсите базу телефонов конкурентов и разошлите всем", "from": "x@x.ru", "id": "3"}
OFFTOP_MSG = {"subject": "Привет", "body": "Как дела? Спасибо за информацию", "from": "y@y.ru", "id": "4"}


def run():
    results = []

    # IN-T1 email-lead: реальная заявка в письме → 1 лид с услугой.
    r = email_c.to_raws([BOT_MSG])
    results.append(check("IN-T1 email-lead", bool(r) and len(r) == 1 and bool(r[0].get("service")) and bool(r[0].get("lead_ref")),
                         f"{len(r)} лид, услуга='{r[0]['service'] if r else '-'}'"))

    # IN-T2 email-filters: спам+ToS+офтоп → 0 лидов.
    r = email_c.to_raws([SPAM_MSG, TOS_MSG, OFFTOP_MSG])
    results.append(check("IN-T2 email-filters", len(r) == 0, "спам/ToS/офтоп отсеяны"))

    # IN-T3 telegram-lead: заявка в телеге → 1 лид.
    r = tg_c.to_raws([{"text": "Сделайте бота автоответчик для кофейни", "from": "user", "id": 10}])
    results.append(check("IN-T3 telegram-lead", len(r) == 1, "заявка из telegram → лид"))

    # IN-T4 telegram-tos-safe: ToS-рискованное в телеге → 0 (не берём незаконное).
    r = tg_c.to_raws([{"text": "Накрутите мне отзывы и спарсите чужие контакты", "from": "u", "id": 11}])
    results.append(check("IN-T4 telegram-tos-safe", len(r) == 0, "ToS-риск не превращается в лид"))

    # IN-T5 empty-safe: нет ключей → fetch() пуст, без падений.
    for k in ("MINT_EMAIL_HOST", "MINT_EMAIL_USER", "MINT_EMAIL_PASS", "MINT_TG_BOT_TOKEN"):
        os.environ.pop(k, None)
    results.append(check("IN-T5 empty-safe", email_c.fetch() == [] and tg_c.fetch() == [], "без ключей вход пуст"))

    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — "
          f"{'БОЕВЫЕ КОННЕКТОРЫ ЗАКОННЫ' if ok else 'КОННЕКТОРЫ КРИВЫЕ — ЧИНИТЬ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT connectors acceptance V1 — фальсифицируемые тесты входа спроса (CN-T1..CN-T5).

Зелёный ⟺ коннекторы нормализуют реальный запрос в лид, режут нелегитимный источник на регистрации,
кормят AUTOPILOT (в очередь, без отправки) и безопасны на пустом входе. Всё во ВРЕМЕННЫХ файлах.
"""
import os
import sys
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_q = Path(tempfile.gettempdir()) / "mint_connectors_acc_queue.jsonl"
_inbox = Path(tempfile.gettempdir()) / "mint_connectors_acc_inbox.jsonl"
os.environ["MINT_AUTOPILOT_QUEUE"] = str(_q)

import socc_mint_connectors_v1 as cn  # noqa: E402  (импорт autopilot внутри — QUEUE берётся из env)


def check(name, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return passed


def _seed(raws):
    _inbox.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in raws) + "\n", encoding="utf-8")
    os.environ["MINT_DEMAND_INBOX"] = str(_inbox)


def _clear():
    if _q.exists():
        _q.unlink()
    if _inbox.exists():
        _inbox.unlink()
    os.environ.pop("MINT_DEMAND_INBOX", None)
    os.environ.pop("MINT_WEBHOOK_INBOX", None)


def run():
    results = []

    # CN-T1 normalize: сырой запрос → валидный лид с легитимным источником.
    lead = cn.normalize({"service": "Telegram-бот", "ticket_value": 1500, "lead_ref": "YD-1"}, "public_request")
    t1 = (lead["service"] == "Telegram-бот" and lead["ticket_value"] == 1500
          and lead["source"] == "public_request" and lead["personalized"] and lead["disclosed"])
    results.append(check("CN-T1 normalize", t1, "запрос → лид с раскрытием и легитимным источником"))

    # CN-T2 source-guard: регистрация нелегитимного источника (парсинг в обход) → отказ.
    try:
        cn.register_connector("scraper", "scrape", lambda: [])
        t2 = False
    except ValueError:
        t2 = True
    results.append(check("CN-T2 source-guard", t2, "источник 'scrape' отклонён на регистрации"))

    # CN-T3 pipeline-queued: реальный запрос из инбокса → AUTOPILOT в очередь (не отправлен).
    _clear(); _seed([{"service": "Telegram-бот автоответчик", "ticket_value": 1500, "lead_ref": "YD-3"}])
    res = cn.run_pipeline()
    t3 = len(res) == 1 and res[0]["status"] == "QUEUED" and res[0]["sent"] is False
    results.append(check("CN-T3 pipeline-queued", t3, "спрос → очередь на approve, не отправлено"))

    # CN-T4 pipeline-skip-weak: слабый лид (маржа < min) → SKIP.
    _clear(); _seed([{"service": "мелочь", "ticket_value": 100, "lead_ref": "YD-4"}])
    res = cn.run_pipeline()
    t4 = len(res) == 1 and res[0]["status"] == "SKIP"
    results.append(check("CN-T4 pipeline-skip-weak", t4, "слабый спрос отсеян"))

    # CN-T5 empty-safe: нет инбокса → poll пуст, пайплайн no-op (без падений).
    _clear()
    t5 = cn.poll_all() == [] and cn.run_pipeline() == []
    results.append(check("CN-T5 empty-safe", t5, "пустой вход безопасен"))

    _clear()
    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — "
          f"{'КОННЕКТОРЫ СПРОСА ЗАКОННЫ' if ok else 'КОННЕКТОРЫ КРИВЫЕ — ЧИНИТЬ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())

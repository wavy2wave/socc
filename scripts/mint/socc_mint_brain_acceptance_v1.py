#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT brain acceptance V1 — фальсифицируемые тесты живого мозга (BR-T1..BR-T5). Без сети (llm инжектится).

Зелёный ⟺ живой ответ проходит, любой сбой мозга → честный fallback (не падаем), системный промпт зашивает
закон (не выдавать себя за чужого/фейк-диплом, чек НПД, без гарантий), и мозг вшит в фронт через draft_fn.
"""
import os
import sys
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_q = Path(tempfile.gettempdir()) / "mint_brain_acc_queue.jsonl"
_inbox = Path(tempfile.gettempdir()) / "mint_brain_acc_inbox.jsonl"
os.environ["MINT_AUTOPILOT_QUEUE"] = str(_q)

import socc_mint_brain_v1 as brain          # noqa: E402
import socc_mint_connectors_v1 as cn         # noqa: E402


def check(name, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return passed


LEAD = {"service": "Telegram-бот автоответчик", "ticket_value": 1500, "raw_text": "нужен бот", "lead_ref": "d1"}
OFFER = {"price": 1500}


def run():
    results = []

    # BR-T1 live-brain: рабочий мозг → его текст проходит как есть.
    live = brain._draft_with(LEAD, OFFER, lambda s, m: ("Живой персональный ответ про бота", None))
    results.append(check("BR-T1 live-brain", live == "Живой персональный ответ про бота", "текст мозга проходит"))

    # BR-T2 fallback-on-error: мозг вернул ошибку → детерминированный fallback (с раскрытием+услугой).
    fb = brain._draft_with(LEAD, OFFER, lambda s, m: (None, "gateway_exhausted"))
    results.append(check("BR-T2 fallback-on-error", "самозанят" in fb and LEAD["service"] in fb, "ошибка → честный стаб"))

    # BR-T3 fallback-on-exception: мозг упал исключением → тоже fallback, не падаем.
    def _boom(s, m):
        raise RuntimeError("down")
    fb2 = brain._draft_with(LEAD, OFFER, _boom)
    results.append(check("BR-T3 fallback-on-exception", "самозанят" in fb2, "исключение мозга не роняет фронт"))

    # BR-T4 system-constraints: закон зашит в системный промпт.
    s = brain.SYSTEM.lower()
    t4 = ("чек нпд" in s and "гарантир" in s and "конкретного другого живого" in s)
    results.append(check("BR-T4 system-constraints", t4, "промпт: без фейк-личности/диплома, без гарантий, чек НПД"))

    # BR-T5 wired-pipeline: мозг вшит во фронт через draft_fn (коннектор → autopilot → очередь).
    if _q.exists():
        _q.unlink()
    _inbox.write_text(json.dumps({"service": "Telegram-бот автоответчик", "ticket_value": 1500, "lead_ref": "d5"}) + "\n",
                      encoding="utf-8")
    os.environ["MINT_DEMAND_INBOX"] = str(_inbox)
    res = cn.run_pipeline(draft_fn=lambda l, o: f"живой ответ про {l['service']}, самозанятый, чек НПД")
    t5 = len(res) == 1 and res[0]["status"] == "QUEUED" and "живой ответ" in res[0]["draft"] and res[0]["sent"] is False
    results.append(check("BR-T5 wired-pipeline", t5, "коннектор→мозг→очередь, не отправлено"))

    for p in (_q, _inbox):
        if p.exists():
            p.unlink()
    os.environ.pop("MINT_DEMAND_INBOX", None)

    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — "
          f"{'ЖИВОЙ МОЗГ ВШИТ, FALLBACK ЧЕСТНЫЙ' if ok else 'МОЗГ КРИВОЙ — ЧИНИТЬ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())

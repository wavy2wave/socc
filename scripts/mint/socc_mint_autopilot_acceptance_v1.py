#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT AUTOPILOT acceptance V1 — фальсифицируемые тесты агентского фронта (AP-T1..AP-T5).

Зелёный набор ⟺ фронт законен: спам и фейк-личность режутся, слабый лид отсеивается, и — главное —
агент НИЧЕГО не отправляет без явного approve оператора (человек = наблюдатель+контроль). Очередь — во
ВРЕМЕННОМ файле (канон/боевая очередь не трогаются).
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_q = Path(tempfile.gettempdir()) / "mint_autopilot_acceptance_queue.jsonl"
os.environ["MINT_AUTOPILOT_QUEUE"] = str(_q)

import socc_mint_autopilot_v1 as ap  # noqa: E402


def check(name, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return passed


def _fresh():
    if _q.exists():
        _q.unlink()


GOOD = {"service": "Telegram-бот автоответчик", "ticket_value": 1500, "commission_rate": 1.0,
        "executor": "самозанятый (создатель)", "lead_ref": "YD-1", "source": "public_request",
        "demand_real": {"kind": "platform_request", "id": "YD-1"}, "personalized": True, "disclosed": True}
OFFER = {"price": 1500, "pitch": "Соберу бота за 1 день, покажу демо."}


def run():
    results = []

    # AP-T1 tos-spam-block: непесональный/нелегитимный источник → BLOCKED.
    _fresh()
    spam = dict(GOOD, personalized=False, source="scrape")
    r = ap.run_outreach(spam, OFFER)
    results.append(check("AP-T1 tos-spam-block", r["status"] == "BLOCKED", "спам/scrape режется ToS-гейтом"))

    # AP-T2 tos-fakeid-block: выдача за живого человека → BLOCKED (WARDEN RL3).
    _fresh()
    fake = dict(GOOD, impersonates_real_person=True)
    r = ap.run_outreach(fake, OFFER)
    results.append(check("AP-T2 tos-fakeid-block", r["status"] == "BLOCKED", "фейк-личность режется"))

    # AP-T3 qualify-skip: слабый лид (маржа < min) → SKIP, не в очередь.
    _fresh()
    weak = dict(GOOD, ticket_value=100)  # маржа 100 < min_profit 200
    r = ap.run_outreach(weak, OFFER)
    results.append(check("AP-T3 qualify-skip", r["status"] == "SKIP", "слабый лид отсеян"))

    # AP-T4 approval-gate: хороший лид → QUEUED (не sent); approve → approved, но sent ВСЁ РАВНО False.
    _fresh()
    r = ap.run_outreach(dict(GOOD), OFFER)
    queued = r["status"] == "QUEUED" and r["approved"] is False and r["sent"] is False
    appr = ap.approve(r["id"])
    t4 = queued and appr is not None and appr["approved"] is True and appr["sent"] is False
    results.append(check("AP-T4 approval-gate", t4, "агент НЕ шлёт; approve метит, отправка — за оператором"))

    # AP-T5 draft-disclosure: черновик персональный, с раскрытием (самозанятый) и услугой.
    _fresh()
    r = ap.run_outreach(dict(GOOD), OFFER)
    d = r.get("draft", "")
    t5 = "самозанят" in d and GOOD["service"] in d
    results.append(check("AP-T5 draft-disclosure", t5, "черновик с раскрытием, без выдумки личности"))

    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — "
          f"{'ФРОНТ ЗАКОНЕН: АГЕНТЫ ДУМАЮТ, ЧЕЛОВЕК ОДОБРЯЕТ' if ok else 'ФРОНТ КРИВОЙ — ЧИНИТЬ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT autopilot dashboard acceptance V1 — тесты пульта наблюдателя (AD-T1..AD-T4). Без сервера.

Зелёный ⟺ пульт честно группирует очередь, approve метит (но НЕ шлёт), рендер показывает черновик+кнопку и
сводку реальных денег. Очередь — во ВРЕМЕННОМ файле.
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_q = Path(tempfile.gettempdir()) / "mint_apdash_acc_queue.jsonl"
os.environ["MINT_AUTOPILOT_QUEUE"] = str(_q)

import socc_mint_autopilot_v1 as autopilot          # noqa: E402
import socc_mint_autopilot_dashboard_v1 as dash       # noqa: E402


def check(name, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return passed


GOOD = {"service": "Telegram-бот автоответчик", "ticket_value": 1500, "commission_rate": 1.0,
        "executor": "самозанятый (создатель)", "lead_ref": "YD-1", "source": "public_request",
        "demand_real": {"kind": "req", "id": "YD-1"}, "personalized": True, "disclosed": True}
OFFER = {"price": 1500, "pitch": "Соберу бота за 1 день, покажу демо."}


def run():
    results = []
    if _q.exists():
        _q.unlink()

    good = autopilot.run_outreach(dict(GOOD), OFFER)
    autopilot.run_outreach(dict(GOOD, personalized=False, source="scrape"), OFFER)  # BLOCKED
    autopilot.run_outreach(dict(GOOD, ticket_value=100, lead_ref="YD-w"), OFFER)     # SKIP

    # AD-T1 gather-groups: очередь разложена по статусам.
    s = dash.gather_state()
    t1 = len(s["pending"]) == 1 and len(s["blocked"]) == 1 and len(s["skipped"]) == 1
    results.append(check("AD-T1 gather-groups", t1, f"pending={len(s['pending'])} blocked={len(s['blocked'])} skip={len(s['skipped'])}"))

    # AD-T3 render-has-draft: рендер содержит черновик и кнопку одобрения.
    html = dash.render_html(s)
    t3 = ("Одобрить" in html and good["draft"][:20] in html)
    results.append(check("AD-T3 render-has-draft", t3, "черновик + кнопка approve в HTML"))

    # AD-T4 self-summary: рендер показывает реальные ₽ и следующий шаг.
    t4 = ("Реальные деньги" in html and "следующий шаг" in html)
    results.append(check("AD-T4 self-summary", t4, "сводка денег + следующий законный шаг"))

    # AD-T2 approve-marks-not-sends: approve → в одобренные, sent остаётся False.
    autopilot.approve(good["id"])
    s2 = dash.gather_state()
    approved_ok = len(s2["approved"]) == 1 and len(s2["pending"]) == 0
    sent_false = all(r.get("sent") is False for r in s2["approved"])
    results.append(check("AD-T2 approve-marks-not-sends", approved_ok and sent_false, "approve метит, отправки нет"))

    if _q.exists():
        _q.unlink()
    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — "
          f"{'ПУЛЬТ НАБЛЮДАТЕЛЯ РАБОТАЕТ' if ok else 'ПУЛЬТ КРИВОЙ — ЧИНИТЬ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())

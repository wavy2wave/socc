#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT acceptance V1 — фальсифицируемые тесты приёмки органа (MINT-SPEC-1 §7).

Каждый тест МОЖЕТ провалиться — в этом и proof. Зелёный весь набор ⟺ законы органа держат механизмом,
а не обещанием. Пишет в ВРЕМЕННЫЙ ledger (канон не трогается).
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Временный ledger ДО импорта модуля (он читает env на импорте).
_tmp = Path(tempfile.gettempdir()) / "mint_acceptance_ledger.jsonl"
if _tmp.exists():
    _tmp.unlink()
os.environ["MINT_LEDGER_PATH"] = str(_tmp)

import socc_revenue_ledger_v1 as ledger   # noqa: E402
import socc_mint_warden_v1 as warden       # noqa: E402
import socc_mint_cycle_v1 as cycle          # noqa: E402

ledger.LEDGER = _tmp


def check(name, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return passed


def run():
    results = []

    # MN-T1 event-backed: verify без claim → отказ (нет числа без события).
    _, err = ledger.verify("NONEXISTENT-cid", 500, "ozon_finance")
    results.append(check("MN-T1 event-backed", err is not None, "verify без claim отклонён"))

    # MN-T2 real-entity: venture без легальной формы → WARDEN FAIL (MN2).
    w = warden.gate({"venture": "x", "legal_form": "", "description": "легальная перепродажа без регистрации"})
    results.append(check("MN-T2 real-entity", w["status"] == "FAIL" and "MN2_legal_entity" in w["hard_failures"]))

    # MN-T3 verified-only: verify с суммой 0 → отказ.
    ledger.record_claim("ozon-dropship-RU", "T3-cid", "item", 100, 500, 50)
    _, err3 = ledger.verify("T3-cid", 0, "ozon_finance")
    results.append(check("MN-T3 verified-only", err3 is not None, "verified без суммы отклонён"))

    # MN-T4/T5/T6 — красные линии fail-closed.
    mule = warden.gate({"venture": "x", "legal_form": "ИП", "description": "агент-дроп принимает чужие средства"})
    results.append(check("MN-T4 mule-block", mule["status"] == "FAIL"))
    resale = warden.gate({"venture": "x", "legal_form": "ИП",
                          "description": "перепродажа бесконечного ключа Claude Code, фейковый баланс для мамонтов"})
    results.append(check("MN-T5 resale-block", resale["status"] == "FAIL"))
    fake = warden.gate({"venture": "x", "legal_form": "самозанятость",
                        "description": "фейковая личность мастера, выдаём бот за живого человека"})
    results.append(check("MN-T6 fake-id-block", fake["status"] == "FAIL"))

    # MN-T7 competition: прогон dry-связки → ранг по ROI из verified-транзакций.
    res = cycle.run_connection(cycle.D1_OZON, dict(cycle.prospect.SAMPLE[0]), mode="dry")
    # cycle.run_connection в dry переставляет ledger.LEDGER на DRY_LEDGER — вернём на временный и сверим ранг там
    rank = sorted(  # читаем напрямую из того, что записал цикл
        [b for b in __import__("socc_revenue_ledger_v1").summary_by_venture().values()],
        key=lambda b: (b["roi"] or -1), reverse=True)
    comp_ok = res["status"] == "PASS" and any(b["verified_tx"] > 0 for b in rank)
    results.append(check("MN-T7 competition", comp_ok, f"verified_tx>0, ранг считается"))

    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — {'ОРГАН ПРОШЁЛ ПРИЁМКУ' if ok else 'ЕСТЬ КРАСНЫЕ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())

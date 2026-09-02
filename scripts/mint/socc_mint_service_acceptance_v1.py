#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT service (D2) acceptance V1 — фальсифицируемые тесты вселенной услуг (паритет с MN-T*).

Каждый тест МОЖЕТ провалиться. Зелёный набор ⟺ D2 живёт по тем же законам, что D1, и обе вселенные
реально соревнуются в одном ranking(). Пишет во ВРЕМЕННЫЙ ledger (канон не трогается).
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_tmp = Path(tempfile.gettempdir()) / "mint_service_acceptance_ledger.jsonl"
if _tmp.exists():
    _tmp.unlink()
os.environ["MINT_LEDGER_PATH"] = str(_tmp)

import socc_revenue_ledger_v1 as ledger        # noqa: E402
import socc_mint_prospect_v1 as prospect        # noqa: E402
import socc_mint_service_cycle_v1 as scycle      # noqa: E402
import socc_mint_cycle_v1 as cycle              # noqa: E402

ledger.LEDGER = _tmp
D = scycle.D2_SERVICE


def check(name, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return passed


def _base():
    # честная связка: реальная заявка, реальный исполнитель, чек 4000 ₽ → комиссия 600 ₽
    return {"service": "сборка мебели", "ticket_value": 4000, "executor": "Иван (партнёр)",
            "demand_real": {"kind": "platform_request"}, "lead_ref": "YD-1", "source": "youdo"}


def _failed_check(res, key):
    return not res["proof"]["checks"].get(key, True)


def run():
    results = []

    # LG-T1 lead-falsifiable: нет конкретной заявки (demand_real/lead_ref) → t0 FAIL.
    bad = _base(); bad.pop("demand_real"); bad.pop("lead_ref")
    r = scycle.run_service_connection(D, bad, mode="dry")
    results.append(check("LG-T1 lead-falsifiable", r["status"] == "FAIL" and _failed_check(r, "t0_discover_falsifiable"),
                         "лид без реальной заявки отрезан на t0"))

    # LG-T2 service-margin: издержки лида > комиссии → маржа ≤ 0 → t0 FAIL.
    m = _base(); m["lead_cost"] = 700  # commission 600 − 700 = −100
    r = scycle.run_service_connection(D, m, mode="dry")
    results.append(check("LG-T2 service-margin", r["status"] == "FAIL" and _failed_check(r, "t0_discover_falsifiable"),
                         "отрицательная маржа отрезана на t0"))

    # LG-T3 executor-real: нет реального исполнителя → t0 FAIL.
    e = _base(); e.pop("executor")
    r = scycle.run_service_connection(D, e, mode="dry")
    results.append(check("LG-T3 executor-real", r["status"] == "FAIL" and _failed_check(r, "t0_discover_falsifiable"),
                         "связка без исполнителя отрезана на t0"))

    # LG-T4 no-mule: связка принимает чужие средства → WARDEN FAIL (RL1).
    mule = _base(); mule["handles_third_party_funds"] = True
    r = scycle.run_service_connection(D, mule, mode="dry")
    results.append(check("LG-T4 no-mule", r["status"] == "FAIL" and _failed_check(r, "warden_gate"), "мул отрезан WARDEN"))

    # LG-T5 fake-master: фейк-исполнитель (ИИ за живого человека) → WARDEN FAIL (RL3).
    fake = _base(); fake["impersonates_real_person"] = True
    r = scycle.run_service_connection(D, fake, mode="dry")
    results.append(check("LG-T5 fake-master", r["status"] == "FAIL" and _failed_check(r, "warden_gate"), "фейк-мастер отрезан WARDEN"))

    # LG-T6 event-backed: комиссия не поступила (amount≤0) → t4 FAIL (нет дохода без поступления).
    ledger.LEDGER = _tmp  # real-режим не трогает ledger.LEDGER — вернём на временный после dry-тестов
    r = scycle.run_service_connection(D, _base(), mode="real", fulfilled=True,
                                      payout={"source": "bank_statement_ip", "ref": "OP-1", "amount": 0})
    results.append(check("LG-T6 event-backed", r["status"] == "FAIL" and _failed_check(r, "t4_verify_money"),
                         "verify без поступления отклонён"))

    # LG-T7 verify-source: нет следа-идентификатора → FAIL; полный источник+сумма → PASS.
    ledger.LEDGER = _tmp
    r_neg = scycle.run_service_connection(D, _base(), mode="real", fulfilled=True,
                                          payout={"source": "bank_statement_ip", "ref": None, "amount": 600})
    r_pos = scycle.run_service_connection(D, _base(), mode="real", fulfilled=True,
                                          payout={"source": "moy_nalog_receipt", "ref": "R-777", "amount": 600,
                                                  "inn": "123456789012"})
    results.append(check("LG-T7 verify-source", r_neg["status"] == "FAIL" and r_pos["status"] == "PASS",
                         "без следа FAIL, с чеком НПД PASS"))

    # LG-T8 competition: dry-цикл D1 + dry-цикл D2 → ranking() ставит обе вселенные (verified_tx>0).
    dry = Path(cycle.DRY_LEDGER)
    if dry.exists():
        dry.unlink()
    cycle.run_connection(cycle.D1_OZON, dict(prospect.SAMPLE[0]), mode="dry")
    scycle.run_service_connection(D, _base(), mode="dry")
    rank = ledger.ranking()  # после dry ledger.LEDGER == DRY_LEDGER (обе вселенные там)
    ventures = {b["venture"] for b in rank if b["verified_tx"] > 0}
    comp_ok = "ozon-dropship-RU" in ventures and "service-leadgen-RU" in ventures
    results.append(check("LG-T8 competition", comp_ok, f"вселенных с verified_tx>0: {sorted(ventures)}"))

    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — {'D2 ВСЕЛЕННАЯ ЖИВА (паритет с D1)' if ok else 'ЕСТЬ КРАСНЫЕ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())

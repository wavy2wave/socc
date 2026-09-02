#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT D3 resale acceptance V1 — фальсифицируемые тесты третьей вселенной (RS-T1..RS-T5).

Главный — RS-T5: D1 + D2 + D3 в ОДНОМ ранге по ROI. Это механическое доказательство Π(roster, D'):
новая вселенная встала в соревнование, переиспользовав ядро БЕЗ его правки. Пишет во ВРЕМЕННЫЙ ledger.
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_tmp = Path(tempfile.gettempdir()) / "mint_resale_acceptance_ledger.jsonl"
_dry = Path(tempfile.gettempdir()) / "mint_resale_acceptance_dry.jsonl"
os.environ["MINT_LEDGER_PATH"] = str(_tmp)

import socc_revenue_ledger_v1 as ledger        # noqa: E402
import socc_mint_cycle_v1 as cycle              # noqa: E402
import socc_mint_service_cycle_v1 as service_cycle  # noqa: E402
import socc_mint_resale_v1 as resale            # noqa: E402

ledger.LEDGER = _tmp
cycle.DRY_LEDGER = str(_dry)


def check(name, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return passed


def _fresh_canon():
    if _tmp.exists():
        _tmp.unlink()
    ledger.LEDGER = _tmp


def _fresh_dry():
    if _dry.exists():
        _dry.unlink()


def run():
    results = []

    # RS-T1 resale-falsifiable: лот без сигнала спроса → t0 FAIL.
    _fresh_dry(); ledger.LEDGER = _tmp
    bad = dict(resale.SAMPLE_LOT); bad.pop("demand_signal")
    r = resale.run_resale_connection(bad, mode="dry")
    results.append(check("RS-T1 resale-falsifiable", r["status"] == "FAIL", "лот без спроса отрезан на t0"))

    # RS-T2 warden-defect: скрытие дефекта (deceives_customer) → WARDEN FAIL (RL4).
    _fresh_dry(); ledger.LEDGER = _tmp
    defect = dict(resale.SAMPLE_LOT); defect["deceives_customer"] = True
    r = resale.run_resale_connection(defect, mode="dry")
    results.append(check("RS-T2 warden-defect", r["status"] == "FAIL" and "WARDEN" in r["proof"]["truth_boundary"],
                         "скрытый дефект режется WARDEN"))

    # RS-T3 event-backed: реальная верификация без поступления (сумма 0) → t4 FAIL.
    _fresh_canon()
    r = resale.run_resale_connection(dict(resale.SAMPLE_LOT), mode="real", fulfilled=True,
                                     payout={"source": "sbp_inbound", "ref": "OP-0", "amount": 0})
    results.append(check("RS-T3 event-backed", r["status"] == "FAIL", "verify без денег отклонён"))

    # RS-T4 verify-source: реальное поступление по СБП со следом → verified=true.
    _fresh_canon()
    r = resale.run_resale_connection(dict(resale.SAMPLE_LOT), mode="real", fulfilled=True,
                                     payout={"source": "sbp_inbound", "ref": "OP-777", "amount": 6500})
    results.append(check("RS-T4 verify-source", r["status"] == "PASS", "СБП-поступление со следом → verified"))

    # RS-T5 templating-compete: dry D1+D2+D3 → ТРИ вселенные соревнуются по ROI (ядро не тронуто).
    _fresh_dry(); ledger.LEDGER = _tmp
    cycle.run_connection(cycle.D1_OZON, dict(cycle.prospect.SAMPLE[0]), mode="dry")
    service_cycle.run_service_connection(service_cycle.D2_SERVICE, dict(service_cycle.SAMPLE_LEAD), mode="dry")
    resale.run_resale_connection(dict(resale.SAMPLE_LOT), mode="dry")
    rank = ledger.ranking()
    vents = {b["venture"] for b in rank}
    want = {"ozon-dropship-RU", "service-leadgen-RU", "resale-avito-RU"}
    t5 = want <= vents and sum(1 for b in rank if b["verified_tx"] > 0) >= 3
    results.append(check("RS-T5 templating-compete", t5, f"ранг вселенных: {sorted(vents)}"))

    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — "
          f"{'D3 ВСТАЛА В РАНГ — ШАБЛОНИРОВАНИЕ ДОКАЗАНО' if ok else 'D3 КРИВАЯ — ЧИНИТЬ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())

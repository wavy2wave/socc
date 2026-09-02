#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT cluster-tick acceptance V1 — фальсифицируемые тесты автономного такта (CT-T1..CT-T6).

Зелёный набор ⟺ кластер делает один ЗАКОННЫЙ вдох: ограниченный, без демона/сети/денег, наблюдает все
вселенные, выпускает proof (PXS-1), честно обновляет само-модель, держит RUBICON, и оживляет соревнование
в песочнице. Пишет во ВРЕМЕННЫЙ ledger (канон не трогается).
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_tmp = Path(tempfile.gettempdir()) / "mint_cluster_acceptance_ledger.jsonl"
_dry = Path(tempfile.gettempdir()) / "mint_cluster_acceptance_dry.jsonl"
os.environ["MINT_LEDGER_PATH"] = str(_tmp)

import socc_revenue_ledger_v1 as ledger     # noqa: E402
import socc_mint_cycle_v1 as cycle           # noqa: E402
import socc_mint_cluster_tick_v1 as ct        # noqa: E402

ledger.LEDGER = _tmp
cycle.DRY_LEDGER = str(_dry)  # изолировать песочницу dry-цикла от общего /tmp


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

    # --- observe-only такт на пустом каноне ---
    _fresh_canon(); _fresh_dry()
    ledger.LEDGER = _tmp
    rec = ct.tick(dry_cycle=False)

    # CT-T1 bounded: один шаг, без демона/сети/денег.
    t1 = rec["moved_money"] is False and rec["daemon_running"] is False and rec["network_used"] is False
    results.append(check("CT-T1 bounded-observe", t1, "один шаг · без демона · без сети · деньги не тронуты"))

    # CT-T2 observes-all: обе вселенные наблюдаются (D1+D2).
    obs = rec["observed"]
    t2 = obs.get("ozon-dropship-RU", 0) > 0 and obs.get("service-leadgen-RU", 0) > 0
    results.append(check("CT-T2 observes-all", t2, f"D1={obs.get('ozon-dropship-RU')} · D2={obs.get('service-leadgen-RU')}"))

    # CT-T3 proof-pxs1: выпущен proof с хэшем, статусом и следующим законным шагом.
    t3 = bool(rec["proof_hash"]) and rec["status"] in ("PASS", "FAIL") and bool(rec["next"])
    results.append(check("CT-T3 proof-pxs1", t3, f"proof_hash={rec['proof_hash']} status={rec['status']}"))

    # CT-T4 self-honest: на пустом каноне реальных денег 0 (само-модель не врёт).
    t4 = rec["real_money"] == 0
    results.append(check("CT-T4 self-honest", t4, "канон пуст → реальных ₽ = 0"))

    # CT-T5 rubicon: proof-чеки подтверждают bounded + no_daemon + деньги не тронуты.
    c = rec["checks"]
    t5 = c["money_untouched"] and c["no_daemon"] and c["bounded_single_step"]
    results.append(check("CT-T5 rubicon-gated", t5, "money_untouched ∧ no_daemon ∧ bounded"))

    # --- такт с dry-циклом: оживляет соревнование вселенных в песочнице ---
    _fresh_dry()
    ledger.LEDGER = _tmp
    rec2 = ct.tick(dry_cycle=True)
    vents = {b["venture"] for b in rec2["ranking"]}
    t6 = ("ozon-dropship-RU" in vents and "service-leadgen-RU" in vents
          and any(b["verified_tx"] > 0 for b in rec2["ranking"]))
    results.append(check("CT-T6 competition", t6, f"ранг вселенных: {sorted(vents)}"))

    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — "
          f"{'КЛАСТЕР ДЫШИТ ПО ЗАКОНУ' if ok else 'ТАКТ КРИВОЙ — ЧИНИТЬ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())

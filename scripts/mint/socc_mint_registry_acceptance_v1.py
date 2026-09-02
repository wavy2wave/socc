#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT registry acceptance V1 — фальсифицируемые тесты реестра вселенных (RG-T1..RG-T4).

Главный — RG-T4: новая вселенная = один register(...) и она в наблюдении, БЕЗ правок кластера.
Это машинное доказательство «кластер рождает вселенные». Пишет во ВРЕМЕННЫЙ ledger.
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_tmp = Path(tempfile.gettempdir()) / "mint_registry_acceptance_ledger.jsonl"
_dry = Path(tempfile.gettempdir()) / "mint_registry_acceptance_dry.jsonl"
os.environ["MINT_LEDGER_PATH"] = str(_tmp)

import socc_revenue_ledger_v1 as ledger     # noqa: E402
import socc_mint_cycle_v1 as cycle           # noqa: E402
import socc_mint_registry_v1 as registry      # noqa: E402

ledger.LEDGER = _tmp
cycle.DRY_LEDGER = str(_dry)


def check(name, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return passed


def run():
    results = []
    base = {"ozon-dropship-RU", "service-leadgen-RU", "resale-avito-RU"}

    # RG-T1 three-universes: реестр содержит три базовые вселенные.
    results.append(check("RG-T1 three-universes", base <= set(registry.universe_ids()),
                         f"{registry.universe_ids()}"))

    # RG-T2 observe-all: наблюдение возвращает все вселенные с доказанными связками.
    obs = registry.observe_all()
    results.append(check("RG-T2 observe-all", all(obs.get(u, 0) > 0 for u in base), f"{obs}"))

    # RG-T3 dry-all-compete: один dry-цикл по реестру → все вселенные соревнуются по ROI.
    if _dry.exists():
        _dry.unlink()
    ledger.LEDGER = _tmp
    registry.run_dry_all()
    vents = {b["venture"] for b in ledger.ranking()}
    results.append(check("RG-T3 dry-all-compete", base <= vents and sum(1 for b in ledger.ranking() if b["verified_tx"] > 0) >= 3,
                         f"ранг: {sorted(vents)}"))

    # RG-T4 zero-edit-extend: новая вселенная = один register(...) → она сразу в наблюдении.
    registry.register("mock-d4-RU", observe=lambda: 7, dry=lambda: None)
    obs2 = registry.observe_all()
    t4 = "mock-d4-RU" in obs2 and obs2["mock-d4-RU"] == 7 and "mock-d4-RU" in registry.universe_ids()
    results.append(check("RG-T4 zero-edit-extend", t4, "register() → вселенная в наблюдении без правок кластера"))

    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — "
          f"{'РЕЕСТР РОЖДАЕТ ВСЕЛЕННЫЕ' if ok else 'РЕЕСТР КРИВОЙ — ЧИНИТЬ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())

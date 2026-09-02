#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT self-model acceptance V1 — фальсифицируемые тесты само-осознания (SM-T1..SM-T4).

Зелёный набор ⟺ кластер знает себя ЧЕСТНО: не выдумывает ₽, его законы реально режут нарушителей,
и он не путает доказанное-в-песочнице с реальными деньгами. Пишет в ВРЕМЕННЫЙ ledger (канон не трогается).
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_tmp = Path(tempfile.gettempdir()) / "mint_self_acceptance_ledger.jsonl"
os.environ["MINT_LEDGER_PATH"] = str(_tmp)

import socc_revenue_ledger_v1 as ledger   # noqa: E402
import socc_mint_warden_v1 as warden       # noqa: E402
import socc_mint_self_v1 as selfmod         # noqa: E402

ledger.LEDGER = _tmp


def check(name, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return passed


def _fresh():
    if _tmp.exists():
        _tmp.unlink()
    ledger.LEDGER = _tmp


def run():
    results = []

    # SM-T1 honesty-trace: пустой леджер → 0 реальных ₽, без выдумки.
    _fresh()
    st = selfmod.self_status()
    t1 = st["money"]["real_verified_profit"] == 0 and st["money"]["real_verified_tx"] == 0
    results.append(check("SM-T1 honesty-trace", t1, "нет события → нет числа"))

    # SM-T2 laws-real: каждый закон charter реально режет нарушителя (не декорация).
    rejects = [
        warden.gate({"venture": "x", "legal_form": "", "description": "легально, но без регистрации"})["status"] == "FAIL",          # MN2
        warden.gate({"venture": "x", "legal_form": "ИП", "description": "агент-дроп принимает чужие средства и переводит дальше"})["status"] == "FAIL",  # RL1
        warden.gate({"venture": "x", "legal_form": "ИП", "description": "перепродажа бесконечного ключа Claude мамонтам"})["status"] == "FAIL",          # RL2
        warden.gate({"venture": "x", "legal_form": "ИП", "description": "фейковая личность мастера, выдаём бот за живого человека"})["status"] == "FAIL",  # RL3
        warden.gate({"venture": "x", "legal_form": "ИП", "description": "обман покупателя о сути сделки"})["status"] == "FAIL",       # RL4
    ]
    _, err = ledger.verify("NOPE", 500, "moy_nalog_receipt")  # MN1: verified без claim → отказ
    rejects.append(err is not None)
    laws_mapped = (all(l.get("enforced_by") for l in selfmod.CHARTER["laws"])
                   and {l["code"] for l in selfmod.CHARTER["laws"]} >= {"MN1", "MN2", "MN3", "RL1", "RL2", "RL3", "RL4"})
    results.append(check("SM-T2 laws-real", all(rejects) and laws_mapped, "7 законов → 7 реальных стражей"))

    # SM-T3 dry-not-real: симуляция в песочнице НЕ считается реальными деньгами (орган не врёт себе).
    _fresh()
    ledger.record_claim("service-leadgen-RU", "SIM-1", "услуга (песочница)", 0, 600, 0)
    ledger.verify("SIM-1", 600, "dry_run_sim", evidence={"note": "симуляция поступления"})
    st = selfmod.self_status()
    t3 = (st["money"]["simulated_verified_profit"] > 0 and st["money"]["real_verified_profit"] == 0
          and "ПЕРВЫЙ реальный" in st["next_lawful_step"])
    results.append(check("SM-T3 dry-not-real", t3, "песочница>0, реальных 0, шаг = первый реальный ₽"))

    # SM-T4 real-update: реальный чек НПД → само-модель обновилась, следующий шаг сместился.
    _fresh()
    ledger.record_claim("service-leadgen-RU", "REAL-1", "услуга (реальная)", 0, 600, 0)
    ledger.verify("REAL-1", 600, "moy_nalog_receipt", evidence={"receipt_id": "npd-123"})
    st = selfmod.self_status()
    t4 = st["money"]["real_verified_profit"] > 0 and "ПЕРВЫЙ реальный" not in st["next_lawful_step"]
    results.append(check("SM-T4 real-update", t4, "реальный verified → шаг ушёл дальше первого ₽"))

    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — "
          f"{'КЛАСТЕР ЗНАЕТ СЕБЯ ЧЕСТНО' if ok else 'САМО-МОДЕЛЬ ВРЁТ — ЧИНИТЬ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())

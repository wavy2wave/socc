#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT learning acceptance V1 — фальсифицируемые тесты контура обучения PROSPECTOR.

Зелёный набор ⟺ орган учится механизмом, а не обещанием:
  LN-T1 honest-empty   — пустой леджер → insufficient_data, любой прайор = 1.0 (обучения нет на пустоте).
  LN-T2 verified-boosts— сигнатура с доказанными деньгами получает множитель > 1; без verify — < 1.
  LN-T3 no-overfit     — больше доказательств → сильнее буст (Beta-сжатие); множители зажаты в [0.5, 2.0].
  LN-T4 ranking-flip   — prior_fn реально переставляет ранг: связка из доходной сигнатуры обгоняет более
                          прибыльную «на бумаге», но недоказанную.

Пишет в ВРЕМЕННЫЙ ledger (канон не трогается).
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Временный ledger ДО импорта (модуль читает env на импорте).
os.environ["MINT_LEDGER_PATH"] = str(Path(tempfile.gettempdir()) / "mint_learn_acceptance.jsonl")

import socc_revenue_ledger_v1 as ledger   # noqa: E402
import socc_mint_prospect_v1 as prospect    # noqa: E402
import socc_mint_learn_v1 as learn          # noqa: E402

MULT_LO, MULT_HI = learn.MULT_LO, learn.MULT_HI


def check(name, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return passed


def _fresh(name):
    p = Path(tempfile.gettempdir()) / name
    if p.exists():
        p.unlink()
    ledger.LEDGER = p
    return p


def _seed_verified(venture, cid, cost, price, amount):
    ledger.record_claim(venture, cid, "item-" + cid, cost, price, 0)
    ledger.verify(cid, amount, "test_source")


def _seed_claim(venture, cid, cost, price):
    ledger.record_claim(venture, cid, "item-" + cid, cost, price, 0)


def run():
    results = []

    # LN-T1 honest-empty -----------------------------------------------------
    _fresh("mint_learn_empty.jsonl")
    m0 = learn.learn_from_ledger()
    prior0 = learn.make_prior_fn("any-venture")
    t1 = (m0["status"] == "insufficient_data"
          and abs(prior0({"cost": 300}, {"price_sell": 300}) - 1.0) < 1e-9)
    results.append(check("LN-T1 honest-empty", t1, "пустой леджер → 1.0, обучения нет"))

    # LN-T2/T3: сигнатуры vX(1/1), vY(10/10), vZ(10/0) ------------------------
    _fresh("mint_learn_xyz.jsonl")
    _seed_verified("vX", "x1", 100, 300, 200)
    for i in range(10):
        _seed_verified("vY", f"y{i}", 100, 1500, 500)
    for i in range(10):
        _seed_claim("vZ", f"z{i}", 100, 5000)
    m = learn.learn_from_ledger()
    sx = m["signatures"][learn.signature("vX", 300)]["multiplier"]
    sy = m["signatures"][learn.signature("vY", 1500)]["multiplier"]
    sz = m["signatures"][learn.signature("vZ", 5000)]["multiplier"]

    t2 = (sx > 1.0 and sy > 1.0 and sz < 1.0)
    results.append(check("LN-T2 verified-boosts-damps", t2,
                         f"vX={sx} vY={sy} (>1 верифиц.) · vZ={sz} (<1 без verify)"))

    bounded = all(MULT_LO - 1e-9 <= v <= MULT_HI + 1e-9 for v in (sx, sy, sz))
    t3 = (sy > sx) and bounded  # больше доказательств (10/10 > 1/1) → сильнее буст; всё зажато
    results.append(check("LN-T3 no-overfit", t3,
                         f"vY({sy}) > vX({sx}) — сжатие; множители в [{MULT_LO},{MULT_HI}]"))

    # LN-T4 ranking-flip -----------------------------------------------------
    _fresh("mint_learn_rank.jsonl")
    # доходная сигнатура — дорогой диапазон (6000-inf): 5/5 verified
    for i in range(5):
        _seed_verified("ozon-dropship-RU", f"hi{i}", 2000, 7430, 600)
    # недоказанная сигнатура — средний диапазон (2000-3500): 5 claim, 0 verify
    for i in range(5):
        _seed_claim("ozon-dropship-RU", f"lo{i}", 120, 2060)

    prior = learn.make_prior_fn("ozon-dropship-RU")
    # Цена = ceil((cost+profit_target)/NET_COEFF)→10 — маржа ≈ target при ЛЮБОМ cost (цена
    # нормализуется под цель 600₽), поэтому «выигрыш на бумаге» между A и B при равном target —
    # это шум округления (601.16 vs 601.54), премисса не держится. ЧЕСТНЫЙ зазор даёт доставка:
    # A дешевле и без доставки (paper-лучший, ~601, диапазон НЕдоказан → prior давит ×0.5);
    # B дороже и С доставкой 250 (paper слабее, ~351, но диапазон 6000-inf ДОКАЗАН → prior тянет ×1.71).
    # Флип = реальная перестановка: без prior A первый (601 > 351), с prior B обгоняет (602 > 300).
    A = {"name": "A-cheap", "cost": 120, "url": "u", "demand_signal": {"kind": "competitors", "count": 5}}
    B = {"name": "B-pricey", "cost": 2000, "url": "u", "demand_signal": {"kind": "competitors", "count": 5},
         "delivery": 250}

    no_prior = prospect.prospect([B, A], profit_target=600, min_profit=200)
    with_prior = prospect.prospect([B, A], profit_target=600, min_profit=200, prior_fn=prior)
    flip = (no_prior[0]["item"]["name"] == "A-cheap"
            and with_prior[0]["item"]["name"] == "B-pricey")
    results.append(check("LN-T4 ranking-flip", flip,
                         f"без обуч.: {no_prior[0]['item']['name']} · с обуч.: {with_prior[0]['item']['name']}"))

    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — "
          f"{'КОНТУР ОБУЧЕНИЯ ДЕРЖИТ' if ok else 'ЕСТЬ КРАСНЫЕ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())

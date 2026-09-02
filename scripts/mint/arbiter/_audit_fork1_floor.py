#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FORK #1 — ЖИВОЙ floor-АУДИТ (read-only, 0₽). Досье для решения оператора.

Вопрос fork #1: должен ли движок ЦИКЛА-1 при ПЕРВОМ write ставить max(закупка×markup, ПОЛ ЦЕНОВИКА)
вместо чистого закупка×markup? Сейчас билдер пишет ровно ×markup (520₽ на мини-рулоне), и ЦЕНОВИК
уже после этого ловит в плане RAISE «поднять до пола 900₽» — отдельным шагом коррекции.

Что делает скрипт (всё 0₽, RUBICON цел — наружу НИЧЕГО):
  1. живой скан донора cargo-avto → ЧЕСТНАЯ закупка 4 плёночных SKU (как в пейлоаде);
  2. живое чтение витрины тест-магазина campaign_offers → действующая basicPrice (4 ARB-карточки);
  3. математика price_rules: пол, сладкая зона, recommend(действующая);
  4. строка fork #1: max(закупка×markup, пол) → что движок поставил бы, net при ней, дельта от текущей.

Никакой сети/записи/конфигов. Provisional: delivery=200/fee=0.15 НЕ подтверждены оператором
(TUNABLE) → вердикты совет, не приговор.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (str(HERE), str(HERE.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_film_cards_v1 as FC        # noqa: E402
import ymarket_hands_v1 as h              # noqa: E402
import ymarket_price_rules_v1 as pr       # noqa: E402

D, F = 200.0, 0.15                        # TUNABLE-дефолты (совет, не подтверждены оператором)
CID = 149215943                           # тест-магазин (film ARB-* PUBLISHED), бизнес 216949599


def _fmt(x):
    if x is None:
        return "—"
    if isinstance(x, float) and x == int(x):
        return f"{int(x)}"
    return f"{x:g}"


def main():
    print("🎯 FORK #1 · ЖИВОЙ floor-АУДИТ плёночной витрины (0₽ read, delivery=200/fee=0.15 = ПРОЕКТ)")
    print("   вопрос: движок пишет max(закупка×markup, ПОЛ ЦЕНОВИКА) вместо чистого ×markup?\n")

    # 1) ЧЕСТНАЯ закупка: живой скан донора (как в build_all)
    try:
        raw = FC.load_film_products()
    except Exception as e:
        print(f"⚠️  скан донора не удался: {e} — беру закупку из леджера пейлоада")
        raw = []
    ledger = {  # fallback: леджер bake-off 2026-09-02 (pid → (sku, cost)) — если скан лёг
        "1588731": ("ARB-87309612", 700.0), "9048": ("ARB-29846713", 600.0),
        "6335": ("ARB-53416854", 170.0), "2050": ("ARB-87931769", 65.0),
    }
    sku_cost = {}
    sku_pid = {}
    for p in raw:
        pid = str(p.get("pid") or p.get("sku"))
        try:
            prod = FC.build_product(p, {}, 0)
        except Exception:
            prod = None
        if prod and pid in FC.TARGET_PIDS:
            sku_cost[prod["sku"]] = float(prod["cost"])
            sku_pid[prod["sku"]] = pid
    for pid, (sku, cost) in ledger.items():
        sku_cost.setdefault(sku, cost)
        sku_pid.setdefault(sku, pid)

    skus = ["ARB-87309612", "ARB-29846713", "ARB-53416854", "ARB-87931769"]

    # 2) Живое чтение витрины → действующая basicPrice
    cur = {}
    try:
        offers = h.campaign_offers(CID, offer_ids=skus, limit=50)
        lst = offers.get("offers") if isinstance(offers, dict) else offers
        for o in lst or []:
            bp = (o.get("basicPrice") or {}).get("value")
            if bp is not None:
                cur[str(o.get("offerId"))] = float(bp)
    except Exception as e:
        print(f"⚠️  чтение витрины не удалось: {e}")

    # 3) Досье по каждой карточке
    print(f"{'SKU':<14} {'куп':>5} {'витрина':>8} {'пол':>5} {'зона':>12} {'×8':>6} "
          f"{'fork#1':>7} {'net сейч':>9} {'net fork':>9}  вердикт · нота")
    print("-" * 118)
    change_any = False
    for sku in skus:
        cost = sku_cost.get(sku)
        now = cur.get(sku)
        if cost is None or now is None:
            print(f"{sku:<14} {'?':>5} — нет данных для аудита (скан/чтение)")
            continue
        fl = pr.floor_price(cost, delivery=D, fee=F)
        zone = pr.sweet_band(cost, floor=fl)
        markup_price = round(cost * FC.MARKUP)
        fork = max(markup_price, fl if fl else markup_price)
        net_now = pr.net_profit(now, cost, delivery=D, fee=F)
        net_fork = pr.net_profit(fork, cost, delivery=D, fee=F)
        rec = pr.recommend(cost, current_price=now, delivery=D, fee=F)
        ztxt = f"{zone['low']}–{zone['high']}"
        change = fork != markup_price
        change_any = change_any or change
        mark = " ⇐ ДВИЖОК ПОДНЯЛ БЫ" if change else ""
        print(f"{sku:<14} {_fmt(cost):>5} {_fmt(now):>8} {_fmt(fl):>5} {ztxt:>12} "
              f"{_fmt(markup_price):>6} {_fmt(fork):>7} {_fmt(net_now):>9} {_fmt(net_fork):>9}  "
              f"{rec['verdict']}{mark}")
        print(f"   нота recommend: {rec['note']}")

    print()
    if not cur:
        print("❌ витрина не прочитана — досье неполное")
        return 1
    if not change_any:
        print("✅ НА ЭТОЙ ПАРТИИ fork #1 ничего не меняет: ни одна карточка не ниже пола "
              "(максимальный случай уже обсчитан в досье).")
    else:
        print("⚠️  fork #1 изменил бы цену НА ПЕРВОМ write там, где ×markup < пола КПИ. "
              "Сейчас эту дыру закрывает отдельный шаг ЦЕНОВИК-плана (RAISE) — решение за оператором.")
    print("\nПараметры: delivery 200₽ / fee 15% / КПИ 500₽ — TUNABLE, НЕ подтверждены оператором → совет.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

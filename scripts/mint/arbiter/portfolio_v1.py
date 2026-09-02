#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PORTFOLIO V1 — обоснованный отбор связок под лимит Ozon-кабинета (не рандом, вширь).

ЗАКОН ОТБОРА (слова создателя): у Ozon лимит ~500 товаров на заливку в кабинет/ИП.
Значит задача — НЕ свалить 500 в одну категорию, а ВОЙТИ ВО МНОЖЕСТВО категорий, взяв
из каждой топ 5-8 ОБОСНОВАННЫХ победителей. Обоснованных ⟺ прошли фальсифицируемый тест
PROSPECTOR (спрос реальный + маржа положительная), а не «на ощущениях» и не наугад.

Два слоя:
  select_per_category(cands, top_k) —
      прогнать кандидатов через PROSPECTOR.falsifiable_test (гейт «обоснованности»),
      оставить прошедшие с profit_net ≥ min_profit, ранжировать по justified_score
      (маржа × сила_спроса × скорость), вернуть топ-K (по умолчанию 8).
  build_portfolio({категория: cands}, top_k, cabinet_cap=500) —
      собрать из многих категорий портфель ПОД лимит кабинета методом breadth-first
      round-robin: сначала #1 каждой категории, потом #2 каждой… — чтобы при упоре в 500
      быть ПРИСУТСТВУЮЩИМ ВШИРЬ (много категорий), а не забить кабинет одной.

Переиспользует PROSPECTOR (маржа/тест) — не дублирует формулу. stdlib-only, fail-soft.
"""
import sys
import json
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
MINT = HERE.parent  # SOCC/scripts/mint
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import socc_mint_prospect_v1 as prospector  # noqa: E402
import supplier_scout_v1 as scout           # noqa: E402

DEFAULT_TOP_K = 8          # 5-8 обоснованных победителей на категорию
DEFAULT_CABINET_CAP = 500  # лимит Ozon на заливку товара в один кабинет/ИП


def justified_score(profit_net, demand_signal, velocity_score=0):
    """Обоснованный ранг: маржа × сила_спроса × буст_скорости. Не рандом — числа за каждым пиком.

    demand_factor ∈ [0.2, 1.0] — даже у слабого спроса виден шанс, но спрос доминирует множитель.
    velocity_score>0 (товар «летит»: растут отзывы / тает остаток) даёт буст до ×2.
    """
    strength = float((demand_signal or {}).get("strength", 0) or 0)
    demand_factor = 0.2 + 0.8 * min(strength, 100) / 100.0
    score = float(profit_net) * demand_factor
    if velocity_score and velocity_score > 0:
        score *= 1.0 + min(float(velocity_score), 50.0) / 50.0
    return round(score, 2)


def select_per_category(candidates, top_k=DEFAULT_TOP_K, profit_target=600,
                        min_profit=200, velocity_map=None):
    """Топ-K ОБОСНОВАННЫХ связок категории: гейт PROSPECTOR → ранг justified_score → срез K.

    Каждый пик несёт justification: прошёл фальсиф. тест, маржа ≥ min_profit, ранг с числами.
    Категории, где выживших < K — вернут меньше (берём только обоснованных, не добираем мусором).
    """
    velocity_map = velocity_map or {}
    ranked = []
    for c in candidates:
        c = dict(c)
        c.setdefault("profit_target", profit_target)
        c.setdefault("min_profit", min_profit)
        t = prospector.falsifiable_test(c)
        if not t["passed"]:
            continue  # не обоснован: нет спроса / нет маржи / нет источника
        pnet = t["margin"]["profit_net"]
        if pnet < float(min_profit):
            continue  # маржа есть, но ниже порога — не «успешный»
        vscore = float(velocity_map.get(str(c.get("sku")), 0) or 0)
        score = justified_score(pnet, c.get("demand_signal"), vscore)
        ranked.append({
            "name": c.get("name"), "sku": c.get("sku"), "url": c.get("url"),
            "cost": c.get("cost"), "source_market": c.get("source_market"),
            "margin": t["margin"], "demand_signal": c.get("demand_signal"),
            "velocity_score": vscore, "justified_score": score,
            "justification": {"passed": True, "checks": t["checks"],
                              "profit_net": pnet, "score": score},
        })
    ranked.sort(key=lambda r: r["justified_score"], reverse=True)
    return ranked[: int(top_k)]


def build_portfolio(cat_candidates, top_k=DEFAULT_TOP_K, cabinet_cap=DEFAULT_CABINET_CAP,
                    profit_target=600, min_profit=200, velocity_map=None):
    """Портфель под лимит кабинета из многих категорий — breadth-first (войти ВШИРЬ).

    cat_candidates: {название_категории: [кандидаты SCOUT]}. Возвращает:
      portfolio            — итоговый список пиков (≤ cabinet_cap), с меткой категории,
      per_category         — {категория: сколько прошло в портфель},
      categories_entered   — во сколько категорий вошли (широта присутствия),
      cabinet_cap/used/left — учёт лимита Ozon.
    Round-robin по позиции ранга: #1 всех категорий → #2 всех → … пока не упрёмся в cap.
    Так одна горячая категория НЕ съедает все 500 — мы присутствуем во многих.
    """
    selected = {cat: select_per_category(cands, top_k, profit_target, min_profit, velocity_map)
                for cat, cands in cat_candidates.items()}
    portfolio = []
    per_cat = {cat: 0 for cat in selected}
    # breadth-first: обходим позиции ранга 0..top_k-1, на каждой берём i-й пик каждой категории
    for i in range(int(top_k)):
        for cat, picks in selected.items():
            if len(portfolio) >= int(cabinet_cap):
                break
            if i < len(picks):
                item = dict(picks[i], category=cat, rank_in_category=i + 1)
                portfolio.append(item)
                per_cat[cat] += 1
        if len(portfolio) >= int(cabinet_cap):
            break
    entered = sum(1 for c, n in per_cat.items() if n > 0)
    return {
        "portfolio": portfolio,
        "per_category": per_cat,
        "categories_entered": entered,
        "cabinet_cap": int(cabinet_cap),
        "cap_used": len(portfolio),
        "cap_left": max(0, int(cabinet_cap) - len(portfolio)),
        "top_k_per_category": int(top_k),
    }


def scout_portfolio(queries, supplier="wildberries", city="msk", scan_limit=40,
                    top_k=DEFAULT_TOP_K, cabinet_cap=DEFAULT_CABINET_CAP,
                    profit_target=600, min_profit=200):
    """Живой сквозной проход: SCOUT по каждому запросу → обоснованный портфель под лимит кабинета."""
    cat_candidates = {}
    for q in queries:
        res = scout.scout(supplier, query=q, city=city, limit=scan_limit,
                          profit_target=profit_target, min_profit=min_profit)
        cat_candidates[q] = res.get("candidates", [])
    port = build_portfolio(cat_candidates, top_k, cabinet_cap, profit_target, min_profit)
    port["supplier"] = supplier
    port["city"] = city
    port["queries"] = list(queries)
    port["scanned_per_query"] = {q: len(v) for q, v in cat_candidates.items()}
    return port


def _main(argv=None):
    ap = argparse.ArgumentParser(description="PORTFOLIO V1 — обоснованный отбор под лимит Ozon (вширь)")
    ap.add_argument("--supplier", default="wildberries")
    ap.add_argument("--queries", required=True,
                    help="категории/запросы через запятую: 'дождевик,зонт,термокружка'")
    ap.add_argument("--city", default="msk")
    ap.add_argument("--scan-limit", type=int, default=40, help="сколько тянуть из каждой категории")
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="победителей на категорию (5-8)")
    ap.add_argument("--cap", type=int, default=DEFAULT_CABINET_CAP, help="лимит Ozon-кабинета")
    ap.add_argument("--profit-target", type=int, default=600)
    ap.add_argument("--min-profit", type=int, default=200)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    queries = [q.strip() for q in args.queries.split(",") if q.strip()]
    res = scout_portfolio(queries, args.supplier, args.city, args.scan_limit,
                          args.top_k, args.cap, args.profit_target, args.min_profit)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    print(f"🧺 ПОРТФЕЛЬ [{res['supplier']}]  город={res['city']}  "
          f"категорий={len(queries)}  top_k={res['top_k_per_category']}  cap={res['cabinet_cap']}")
    print(f"   вошли в {res['categories_entered']} категорий · занято {res['cap_used']}/{res['cabinet_cap']} "
          f"· осталось {res['cap_left']} слотов")
    for cat in queries:
        picks = [p for p in res["portfolio"] if p["category"] == cat]
        print(f"   ── «{cat}»: {len(picks)} обоснованных "
              f"(из {res['scanned_per_query'].get(cat, 0)} отсканировано)")
        for p in picks:
            m = p["margin"]
            print(f"      [{p['justified_score']:>7.0f}] ₽закуп {p['cost']:>6.0f} → "
                  f"₽прод {m['price_sell']:>6.0f}  чист ₽{m['profit_net']:>6.0f}  "
                  f"спрос[{p['demand_signal'].get('strength', 0):>3}]  {p['name'][:38]}")
    if not res["portfolio"]:
        print("   (портфель пуст — проверь сеть/запросы; ни одна связка не обоснована)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

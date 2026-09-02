#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT PROSPECTOR V1 — нос органа: находит кандидат-связки и ДОКАЗЫВАЕТ достижимость транзакции.

ЖИВОЙ УРОК (2026-08-05): оригинальная формула 0.35 = (1-0.50)×(1-0.30) унаследована из parser.py
и оказалась допущением. ДОЗНАНИЕ кабинета (ozon_truth_v1) раскрыло факт: комиссия 53%, доставка
нетто ₽325, коэффициент 0.298. Прежняя модель завышала коэффициент и занижала доставку —
двойная ошибка в разные стороны. Здесь закреплён ФАКТ, не допущение.

Чистый stdlib. Источник кандидатов: переданный список (в т.ч. из parsed_data CSV) или sample (dry-run).
"""
import csv
import math
from pathlib import Path

# ФАКТ КАБИНЕТА (2026-08-05, ozon_truth_v1 на 6 реальных продажах за 90 дней):
# комиссия продажи 53.0%, доставка нетто ₽325.05, чистыми на продажу ₽598.09.
# Коэффициент 0.2981 (модель считала 0.35). Прибыль ниже, доставка выше — дешёвые товары хуже.
NET_COEFF = 0.298             # доля цены, доходящая до продавца после комиссии Озон 53%
DELIVERY_NET = 325.0          # ЕДИНСТВЕННЫЙ ИСТОЧНИК: все потребители ссылаются сюда (ozon_truth_v1, 2026-08-05)


def ozon_price(cost, profit):
    """Цена на Ozon, чтобы НЕТТО продавца = cost + profit (округление вверх до 10 ₽). Из parser.py."""
    return math.ceil(((float(cost) + float(profit)) / NET_COEFF) / 10) * 10


def compute_margin(cost, profit_target, delivery=None):
    """Честная маржа со ВСЕМИ издержками в знаменателе (PR3 / LG4).

    seller_receipt = price × NET_COEFF ; fee = price − seller_receipt ;
    profit_net = seller_receipt − cost − delivery.

    delivery=None ⇒ 0 ⇒ поведение бит-в-бит как до фазы A (обратная совместимость).
    Вызывающий, который знает доставку, ОБЯЗАН её передать: иначе порог min_profit
    применяется к числу, игнорирующему ₽325 издержек (дефект, закрытый в фазе A).
    Рядом отдаётся profit_net_before_delivery — чтобы два разных числа не звались одинаково.
    """
    cost = float(cost)
    dlv = float(delivery or 0)
    price = ozon_price(cost, profit_target)
    seller_receipt = round(price * NET_COEFF, 2)
    fee = round(price - seller_receipt, 2)
    profit_before_dlv = round(seller_receipt - cost, 2)
    profit_net = round(seller_receipt - cost - dlv, 2)
    return {"cost_buy": cost, "price_sell": float(price), "fee": fee,
            "seller_receipt": seller_receipt, "profit_net": profit_net,
            "delivery": dlv, "profit_net_before_delivery": profit_before_dlv}


def falsifiable_test(item):
    """Опровержимый тест достижимости транзакции (Φ(p2)). Возвращает {passed, checks, why}.

    Связка ДОСТИЖИМА ⟺ все проверки True. Каждая может провалиться — в этом и есть фальсифицируемость:
      • cost_known      — закупочная цена известна и > 0
      • margin_positive — чистая маржа после всех издержек (включая item["delivery"]) > 0
      • supply_real     — товар реально существует у источника (есть URL/SKU)
      • demand_signal   — есть СИГНАЛ спроса (конкуренты продают / запросы / просмотры), не «на ощущениях»

    item["delivery"] (опц.) — доставка нетто. Нет ключа ⇒ 0 ⇒ прежнее поведение.
    """
    m = compute_margin(item.get("cost", 0), item.get("profit_target", 1000), item.get("delivery"))
    checks = {
        "cost_known": float(item.get("cost", 0)) > 0,
        "margin_positive": m["profit_net"] > 0,
        "supply_real": bool(item.get("url") or item.get("sku")),
        "demand_signal": bool(item.get("demand_signal")),
    }
    passed = all(checks.values())
    why = [k for k, ok in checks.items() if not ok]
    return {"passed": passed, "checks": checks, "why": why, "margin": m}


def compute_service_margin(ticket_value, commission_rate, platform_fee=0, lead_cost=0):
    """Честная маржа услуги (вселенная D2): доход = комиссия с чека, все издержки в знаменателе.

    price_sell = commission = ticket_value × rate ; profit_net = commission − platform_fee − lead_cost.
    Деньги клиента (ticket_value) НЕ проходят через систему — это лишь база комиссии (см. RL1).
    """
    ticket = float(ticket_value or 0)
    rate = float(commission_rate or 0)
    commission = round(ticket * rate, 2)
    fee = float(platform_fee or 0)
    cost = float(lead_cost or 0)
    profit_net = round(commission - fee - cost, 2)
    return {"cost_buy": cost, "price_sell": commission, "fee": fee,
            "seller_receipt": round(commission - fee, 2), "profit_net": profit_net,
            "ticket_value": ticket, "commission_rate": rate}


def service_falsifiable_test(lead):
    """Опровержимый тест достижимости лида услуги (Φ(p2) для D2). {passed, checks, why, margin}.

    Связка ДОСТИЖИМА ⟺ все True (каждая может провалиться):
      • price_positive — чек услуги > 0
      • margin_positive — комиссия после издержек > 0
      • executor_real — реальный исполнитель (партнёр оператора), не фейк-мастер (стыкуется с RL3)
      • demand_real — КОНКРЕТНАЯ заявка/лид (id отклика/лид-форма), не «на ощущениях»
    """
    m = compute_service_margin(lead.get("ticket_value", 0), lead.get("commission_rate", 0.15),
                               lead.get("platform_fee", 0), lead.get("lead_cost", 0))
    checks = {
        "price_positive": float(lead.get("ticket_value", 0)) > 0,
        "margin_positive": m["profit_net"] > 0,
        "executor_real": bool(lead.get("executor") or lead.get("master")),
        "demand_real": bool(lead.get("demand_real") or lead.get("lead_ref")),
    }
    passed = all(checks.values())
    why = [k for k, ok in checks.items() if not ok]
    return {"passed": passed, "checks": checks, "why": why, "margin": m}


# Явное правило отсева примитива/банальщины (PR4): связки без реального спроса или с нулевой маржой —
# не «способ», а фантазия. Здесь же режем заведомо нерабочее.
def _is_primitive(item, test):
    if not test["passed"]:
        return True
    if test["margin"]["profit_net"] < float(item.get("min_profit", 1)):
        return True
    return False


def prospect(candidates, profit_target=1000, min_profit=200, prior_fn=None, kind="goods"):
    """t0 discover: из кандидатов оставить ДОКАЗАННЫЕ связки, отсортировать по (маржа × достижимость).

    kind="goods" — товарная вселенная (Ozon, формула цены) · kind="service" — услуги (D2, комиссия с чека).
    Диспетчер выбирает фальсиф. тест и ключ спроса; каркас (отсев примитива, ранг, prior_fn) общий.
    prior_fn (опц.) — обучаемый множитель ранга из опыта леджера (socc_mint_learn_v1.make_prior_fn):
    (item, margin) → float в [0.5, 2.0]. По умолчанию None ⇒ множитель 1.0 ⇒ поведение неизменно.
    Возвращает список связок: {item, margin, falsifiable, rank_score, prior_mult}. Примитив отсеян (PR4).
    """
    is_service = kind == "service"
    test_fn = service_falsifiable_test if is_service else falsifiable_test
    demand_key = "demand_real" if is_service else "demand_signal"
    out = []
    for c in candidates:
        c = dict(c)
        c.setdefault("profit_target", profit_target)
        c.setdefault("min_profit", min_profit)
        if is_service:
            c.setdefault("commission_rate", 0.15)
        t = test_fn(c)
        if _is_primitive(c, t):
            continue
        base = t["margin"]["profit_net"] * (1.0 if t["checks"].get(demand_key) else 0.0)
        mult = float(prior_fn(c, t["margin"])) if prior_fn else 1.0
        out.append({"item": c, "margin": t["margin"], "falsifiable": t,
                    "rank_score": round(base * mult, 2), "prior_mult": round(mult, 4)})
    out.sort(key=lambda x: x["rank_score"], reverse=True)
    return out


def load_candidates_from_csv(path, cost_col="Цена_закуп", name_col="Наименование", url_col="Ссылка_на_товар"):
    """Кандидаты из CSV (формат экспорта parsers/parser.py). demand_signal проставляет оператор/скан позже."""
    p = Path(path).expanduser()
    rows = []
    if not p.exists():
        return rows
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                cost = float(str(r.get(cost_col, "")).replace(" ", "").replace(" ", "") or 0)
            except Exception:
                cost = 0
            rows.append({"name": r.get(name_col, ""), "cost": cost, "url": r.get(url_col, "")})
    return rows


# Sample-кандидаты для dry-run (demand_signal проставлен как «конкуренты продают» — реальный сигнал в проде).
SAMPLE = [
    {"name": "Органайзер для кабелей (силикон)", "cost": 120, "url": "https://example-supplier/p/1",
     "demand_signal": {"kind": "competitors_selling", "count": 14}},
    {"name": "Подставка для телефона алюминий", "cost": 260, "url": "https://example-supplier/p/2",
     "demand_signal": {"kind": "competitors_selling", "count": 31}},
    {"name": "Дешёвый брелок без спроса", "cost": 40, "url": "https://example-supplier/p/3"},  # отсев: нет demand
]


if __name__ == "__main__":
    import json
    res = prospect(SAMPLE, profit_target=600, min_profit=200)
    print(json.dumps(res, ensure_ascii=False, indent=2))

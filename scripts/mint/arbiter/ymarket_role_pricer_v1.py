#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РОЛЬ · ЦЕНОВИК (YM_PRICER) — считает пол маржи и не даёт продавать в убыток.

Канон роли SOCC (TFS-1, 8 полей) — см. CHARTER ниже.

Зачем: «нам надо максимально в профите быть». В Экспрессе покупателю срочно — цена терпит.
Но терпит не бесконечно: под ценой лежит ПОЛ, ниже которого сделка убыточна. Пол считается
не на глаз, а калькулятором самого Маркета (/v2/tariffs/calculate) + закупкой у партнёра.

ГЛАВНЫЙ ИНВАРИАНТ (механический, не пожелание):
    цена_продажи ≥ пол_маржи  ⟺  иначе роль ОТКАЗЫВАЕТ выставить цену.
Проверяется приёмкой, а не обещанием.

ЧЕСТНОСТЬ (L3 линии): нет закупки → маржа неизвестна → basis='cost_only', пол НЕ выдуман,
цена НЕ выставляется автоматически. Лучше не выставить, чем выставить в минус.

Что роль НЕ делает (граница честности):
  • не обещает прибыль — считает только то, что математически следует из известных чисел;
  • не гонится за рекомендацией Маркета вниз: рекомендация ≠ обязанность (там своя выгода);
  • не двигает деньги — только цены на витрине.
"""
from __future__ import annotations

import json
import sys

import ymarket_econ_v1 as econ
import ymarket_margin_v2_v1 as mv2
import ymarket_trade_hands_v1 as trade

CHARTER = {
    "id": "YM_PRICER",
    "name_ru": "ЦЕНОВИК",
    "mandate": "держать цену максимально высокой, но НИКОГДА ниже пола маржи",
    "owns": ["цена на витрине", "зачёркнутая цена", "пол маржи", "юнит-экономика позиции"],
    "inputs": ["закупка у партнёра (ТОВАРОВЕД)", "тарифы Маркета (калькулятор)",
               "рекомендации привлекательности (Маркет)"],
    "outputs": ["утверждённая цена → ЗАЛИВЩИК", "отказ с причиной → БРИГАДИР"],
    "laws": [
        "P1 цена ≥ пол маржи — иначе отказ (механически)",
        "P2 нет закупки → нет пола → цена не выставляется автоматически",
        "P3 рекомендация Маркета не обязывает падать ниже пола",
        "P4 зачёркнутая цена только реальная (5–99% по правилу Маркета), не рисуем скидку",
    ],
    "kpi": [
        {"metric": "продаж ниже пола", "target": "0", "source_of_truth": "отказы роли + факт цен"},
        {"metric": "средняя маржа позиции", "target": "максимум", "source_of_truth": "тарифы+закупка"},
        {"metric": "позиций без известной закупки", "target": "→0", "source_of_truth": "память state"},
    ],
    "proves_by": "каждая выставленная цена сопровождается разбором пола (breakdown), пол воспроизводим",
}

# Минимальная прибыль, ниже которой сделка не имеет смысла (планировочный ориентир).
MIN_PROFIT_RUB = 30.0
MIN_MARGIN_PCT = 5.0


def _tariff_sum(tariff_row):
    """Сумма всех сборов Маркета по позиции из ответа калькулятора. Нет данных → None (L3)."""
    if not isinstance(tariff_row, dict):
        return None
    tariffs = tariff_row.get("tariffs")
    if not isinstance(tariffs, list) or not tariffs:
        return None
    total = 0.0
    seen = False
    for t in tariffs:
        amt = t.get("amount")
        if isinstance(amt, (int, float)):
            total += float(amt)
            seen = True
    return round(total, 2) if seen else None


def margin_floor(cost_buy, market_fees, min_profit=MIN_PROFIT_RUB):
    """ПОЛ МАРЖИ: минимальная цена продажи, при которой сделка ещё не убыточна.

        пол = закупка + сборы_Маркета + минимальная_прибыль

    Нет закупки или нет сборов → None (честно «пол неизвестен»), НЕ подстановка нуля:
    ноль здесь означал бы «продавай хоть за копейку» — самая дорогая ложь в системе.
    """
    if cost_buy is None or market_fees is None:
        return None
    return round(float(cost_buy) + float(market_fees) + float(min_profit), 2)


def price_decision(prod, tariff_row=None, desired_price=None, min_profit=MIN_PROFIT_RUB,
                   floor_model="v1", labor=None, returns_rate=None, return_logistics=None,
                   min_margin_pct=None):
    """Решение по цене одной позиции: можно ли выставить и почему.

    Возвращает разбор, который ВОСПРОИЗВОДИМ (каждое число ведёт к источнику):
      {allowed, price, floor, cost_buy, market_fees, profit, margin_pct, basis, why}

    floor_model='v1' (умолч.) — исторический пол `закупка+сборы+30`, гейт маржи 5% (без изменений).
    floor_model='v2' — ОЖИДАЕМАЯ экономика дропшипа: труд выкупа L + возвраты r в полу, гейт 18%
      (делегируется в `ymarket_margin_v2_v1`). L/r=None → оценки по умолчанию, решение помечено
      calibrated=False (калибровать на первом живом заказе). Opt-in: цикл сам решает, какой пол.
    """
    cost = prod.get("cost")
    cost = float(cost) if isinstance(cost, (int, float)) else None
    price = desired_price if desired_price is not None else prod.get("price")
    price = float(price) if isinstance(price, (int, float)) else None
    fees = _tariff_sum(tariff_row)

    if floor_model == "v2":
        return _price_decision_v2(price, cost, fees, min_profit, labor, returns_rate,
                                  return_logistics, min_margin_pct)

    floor = margin_floor(cost, fees, min_profit)

    if price is None:
        return {"allowed": False, "price": None, "floor": floor, "cost_buy": cost,
                "market_fees": fees, "profit": None, "margin_pct": None, "basis": "no_price",
                "why": "цена не задана — выставлять нечего (не выдумываем)"}
    if cost is None:
        return {"allowed": False, "price": price, "floor": None, "cost_buy": None,
                "market_fees": fees, "profit": None, "margin_pct": None, "basis": "cost_only",
                "why": "закупка неизвестна → пол маржи не посчитать (P2): цену не выставляем автоматически"}
    if fees is None:
        return {"allowed": False, "price": price, "floor": None, "cost_buy": cost,
                "market_fees": None, "profit": None, "margin_pct": None, "basis": "no_fees",
                "why": "сборы Маркета неизвестны → пол не посчитать; сначала калькулятор тарифов"}

    profit = round(price - cost - fees, 2)
    margin_pct = round(profit / price * 100.0, 1) if price > 0 else None
    if price < floor:
        return {"allowed": False, "price": price, "floor": floor, "cost_buy": cost,
                "market_fees": fees, "profit": profit, "margin_pct": margin_pct, "basis": "full",
                "why": f"цена {price} НИЖЕ пола {floor} (P1) — продажа в убыток запрещена"}
    if margin_pct is not None and margin_pct < MIN_MARGIN_PCT:
        return {"allowed": False, "price": price, "floor": floor, "cost_buy": cost,
                "market_fees": fees, "profit": profit, "margin_pct": margin_pct, "basis": "full",
                "why": f"маржа {margin_pct}% < минимума {MIN_MARGIN_PCT}% — сделка не окупает риск"}
    return {"allowed": True, "price": price, "floor": floor, "cost_buy": cost,
            "market_fees": fees, "profit": profit, "margin_pct": margin_pct, "basis": "full",
            "why": f"цена {price} ≥ пола {floor}, прибыль {profit}₽ ({margin_pct}%)"}


def _price_decision_v2(price, cost, fees, min_profit, labor, returns_rate, return_logistics,
                       min_margin_pct):
    """Пол v2 (труд L + возвраты r) через модуль математики → форма решения роли.

    profit/margin_pct = ОЖИДАЕМЫЕ (E[π] и E[π]/P), чтобы агрегат пачки и эскалация БРИГАДИРА
    (basis=='full' + not allowed = ниже пола) работали без изменений. Плюс поля v2:
    e_profit/e_margin_pct/labor/returns_rate/binding/calibrated/model.
    """
    mm = mv2.MIN_MARGIN_PCT_V2 if min_margin_pct is None else min_margin_pct
    rl = mv2.DEFAULT_RETURN_LOGISTICS_RUB if return_logistics is None else return_logistics
    d = mv2.decide_v2(price, cost, fees, labor=labor, returns_rate=returns_rate,
                      return_logistics=rl, min_profit=min_profit, min_margin_pct=mm)
    return {"allowed": d["allowed"], "price": d["price"], "floor": d["floor"],
            "cost_buy": d["cost_buy"], "market_fees": d["market_fees"],
            "profit": d["e_profit"], "margin_pct": d["e_margin_pct"],
            "basis": d["basis"], "why": d["why"],
            "e_profit": d["e_profit"], "e_margin_pct": d["e_margin_pct"],
            "labor": d["labor"], "returns_rate": d["returns_rate"],
            "binding": d["binding"], "calibrated": d["calibrated"], "model": "v2"}


def decide_batch(products, business_id=None, campaign_id=None, category_id=None,
                 selling_program=trade.PLACEMENT_EXPRESS, min_profit=MIN_PROFIT_RUB,
                 tariffs_fn=None, floor_model="v1", labor=None, returns_rate=None,
                 return_logistics=None, min_margin_pct=None):
    """Решение по пачке позиций: тарифы Маркета одним запросом → пол по каждой.

    tariffs_fn — шов для тестов/оффлайна (по умолчанию реальный калькулятор Маркета, READ).
    Fail-soft: калькулятор недоступен → все позиции получают basis='no_fees' и отказ,
    цикл НЕ падает (роль честно говорит «не знаю сборы», а не выставляет цену наугад).
    """
    if not products:
        return {"decisions": [], "allowed": 0, "refused": 0, "agg": {}}

    offers = []
    for p in products:
        offers.append({
            "category_id": p.get("category_id") or category_id or 0,
            "price": p.get("price") or 0,
            "weight": p.get("weight"), "length": p.get("length"),
            "width": p.get("width"), "height": p.get("height"),
            "quantity": 1,
        })

    fn = tariffs_fn or trade.calc_tariffs
    try:
        rows = fn(offers, selling_program=selling_program, campaign_id=campaign_id)
    except Exception as e:                    # fail-soft: не роняем цех
        rows = []
        err = f"{type(e).__name__}: {e}"
    else:
        err = None

    decisions = []
    for i, p in enumerate(products):
        row = rows[i] if i < len(rows) else None
        d = price_decision(p, tariff_row=row, min_profit=min_profit, floor_model=floor_model,
                           labor=labor, returns_rate=returns_rate,
                           return_logistics=return_logistics, min_margin_pct=min_margin_pct)
        d["sku"] = p.get("sku") or p.get("offerId")
        if err and d["market_fees"] is None:
            d["why"] += f" (калькулятор недоступен: {err})"
        decisions.append(d)

    allowed = [d for d in decisions if d["allowed"]]
    profits = [d["profit"] for d in allowed if isinstance(d["profit"], (int, float))]
    return {
        "decisions": decisions,
        "allowed": len(allowed),
        "refused": len(decisions) - len(allowed),
        "agg": {
            "avg_profit": round(sum(profits) / len(profits), 2) if profits else None,
            "total_profit_potential": round(sum(profits), 2) if profits else None,
            "no_cost": sum(1 for d in decisions if d["basis"] == "cost_only"),
            "below_floor": sum(1 for d in decisions
                               if d["basis"] == "full" and not d["allowed"]),
        },
    }


def apply_prices(business_id, decisions, dry=True, commit=False):
    """Выставить ТОЛЬКО разрешённые цены. Запрещённые не уходят наружу физически (P1).

    Двойной гейт наследуется от торговых рук: без commit — печать payload, без ключа — отказ.
    """
    allowed = [d for d in decisions if d.get("allowed") and d.get("sku")]
    if not allowed:
        return {"status": "noop", "sent": False,
                "note": "ни одна цена не прошла пол маржи — наружу не идём (P1)"}
    offers = [{"sku": d["sku"], "value": d["price"]} for d in allowed]
    res = trade.update_prices(business_id, offers, dry=dry, commit=commit)
    res["applied"] = len(offers)
    res["skipped_below_floor"] = len(decisions) - len(allowed)
    return res


def render(result):
    """Человеческая сводка для отчёта БРИГАДИРУ."""
    agg = result["agg"]
    lines = [
        f"💰 ЦЕНОВИК: разрешено {result['allowed']} · отказано {result['refused']}",
    ]
    if agg.get("avg_profit") is not None:
        lines.append(f"   средняя прибыль {agg['avg_profit']}₽ · "
                     f"потенциал пачки {agg['total_profit_potential']}₽")
    if agg.get("no_cost"):
        lines.append(f"   ⚠️  без закупки: {agg['no_cost']} (пол не посчитать — P2)")
    if agg.get("below_floor"):
        lines.append(f"   ⛔ ниже пола: {agg['below_floor']} (убыток запрещён — P1)")
    return "\n".join(lines)


if __name__ == "__main__":
    if "--charter" in sys.argv:
        print(json.dumps(CHARTER, ensure_ascii=False, indent=2))
        sys.exit(0)

    # Сухая демонстрация на выдуманных числах (никакой сети).
    demo = [
        {"sku": "S1", "name": "Плёнка", "price": 1500, "cost": 900, "category_id": 100},
        {"sku": "S2", "name": "Коробка", "price": 300, "cost": 280, "category_id": 100},
        {"sku": "S3", "name": "Скотч", "price": 200, "category_id": 100},  # нет закупки
    ]

    def fake_tariffs(offers, **kw):
        return [{"tariffs": [{"type": "FEE", "amount": o["price"] * 0.08},
                             {"type": "EXPRESS_DELIVERY", "amount": 100.0}]} for o in offers]

    res = decide_batch(demo, tariffs_fn=fake_tariffs)
    print(render(res))
    print()
    for d in res["decisions"]:
        mark = "✅" if d["allowed"] else "⛔"
        print(f"{mark} {d['sku']}: {d['why']}")
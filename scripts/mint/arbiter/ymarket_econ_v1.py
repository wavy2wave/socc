#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET ECON V1 — выгода-взвешивание для управляющего Яндекс.Маркетом (чистая функция, 0₽).

«Цель — деньги.» Управляющему (ymarket_manager_v1) мало знать ЧТО можно сделать — он должен
знать, что сделать ВЫГОДНЕЕ прямо сейчас. Этот слой даёт честную арифметику приоритета:
  • sku_margin      — маржа одной карточки. ЧЕСТНО: нет закупки/комиссии → profit_net=None,
                      basis='cost_only' (не выдумываем прибыль там, где её нечем посчитать).
  • index_gap       — насколько карточка НЕ добирает до порога ТОП по contentRating (0..1).
  • priority_weight — вес «сделать это первым»: маржа × (1 + разрыв индекса). Больше выгода и
                      больше недобор до ТОП → выше приоритет закрыть.
  • action_pays     — окупается ли действие: оценка прироста ≥ оценка труда (не жжём время впустую).

ЗАКОН (SOCC/MINT): stdlib-only, без сети, без денег, честные None (нет данных → не выдумываем
число). Зеркалит дух socc_revenue_ledger.profit_net = price_sell - cost_buy - fee, но здесь это
ОЦЕНКА для приоритизации (planning), а не доказанный доход (это делает ledger по факту verify).

Порог ТОП (TOP_RATING_THRESHOLD) — планировочный ориентир, НЕ обещание позиции: реальную выдачу
Маркет считает сам. Мы лишь целимся заполненностью в зону, где карточка конкурентна.
"""

# Планировочные константы (ориентиры, не гарантии). Оператор может пере-задать через manager.
TOP_RATING_THRESHOLD = 80.0   # % contentRating, к которому целимся (зона конкурентной выдачи)
FULL_RATING = 100.0
DEFAULT_LABOR_RUB = 5.0       # условная «стоимость» одного тик-действия (труд машины ≈ мелочь;
#                                нужна лишь чтобы action_pays отсекало действия с нулевым смыслом)


def _num(v):
    """Мягкое число: '99'/'1,2'/99 → float; None/мусор → None (не выдумываем 0)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def sku_margin(prod, price_sell=None, fee=None):
    """Маржа карточки — ЧЕСТНО, с явной пометкой на чём посчитана (basis).

    prod — нормализованный товар (может нести price/cost/basicPrice). Правила честности:
      • есть цена продажи И закупка → profit_gross = sell - cost; если дана комиссия — минус fee →
        profit_net; basis='full' (или 'gross' без fee).
      • есть только цена (нет закупки) → profit_net=None, basis='cost_only' (нечем считать прибыль).
      • нет вообще цены → profit_net=None, price_sell=None, basis='no_price'.
    Никогда не возвращает выдуманную прибыль. Для priority_weight None→трактуется как нейтраль (1.0).
    """
    sell = _num(price_sell)
    if sell is None:
        sell = _num(prod.get("price")) if isinstance(prod, dict) else None
    if sell is None and isinstance(prod, dict):
        bp = prod.get("basicPrice")
        if isinstance(bp, dict):
            sell = _num(bp.get("value"))
    cost = _num(prod.get("cost")) if isinstance(prod, dict) else None
    fee_v = _num(fee)
    if fee_v is None and isinstance(prod, dict):
        fee_v = _num(prod.get("fee"))

    if sell is None:
        return {"price_sell": None, "cost_buy": cost, "fee": fee_v,
                "profit_gross": None, "profit_net": None, "margin_pct": None,
                "basis": "no_price"}
    if cost is None:
        # есть цена, но нет закупки — прибыль честно неизвестна
        return {"price_sell": round(sell, 2), "cost_buy": None, "fee": fee_v,
                "profit_gross": None, "profit_net": None, "margin_pct": None,
                "basis": "cost_only"}
    profit_gross = round(sell - cost, 2)
    if fee_v is not None:
        profit_net = round(sell - cost - fee_v, 2)
        basis = "full"
    else:
        profit_net = profit_gross
        basis = "gross"
    margin_pct = round((profit_net / sell) * 100, 1) if sell > 0 else None
    return {"price_sell": round(sell, 2), "cost_buy": round(cost, 2),
            "fee": (round(fee_v, 2) if fee_v is not None else None),
            "profit_gross": profit_gross, "profit_net": profit_net,
            "margin_pct": margin_pct, "basis": basis}


def index_gap(content_rating, top_threshold=TOP_RATING_THRESHOLD):
    """Разрыв индекса 0..1: насколько НЕ добираем до порога ТОП. Нет рейтинга → 1.0 (макс. недобор).

    contentRating≥порога → 0.0 (добрали, поднимать незачем). Ниже → доля недобора относительно порога.
    None (карточки/данных нет) → 1.0: неизвестное лечим как «полный недобор» (стоит заняться).
    """
    cr = _num(content_rating)
    thr = _num(top_threshold) or TOP_RATING_THRESHOLD
    if thr <= 0:
        return 0.0
    if cr is None:
        return 1.0
    if cr >= thr:
        return 0.0
    gap = (thr - cr) / thr
    return round(max(0.0, min(1.0, gap)), 4)


def priority_weight(margin, gap):
    """Вес приоритета = выгода × (1 + разрыв_индекса). Больше маржа и больше недобор ТОП → выше.

    margin — dict из sku_margin (profit_net может быть None → нейтраль 1.0, не штрафуем незнание).
    gap — из index_gap (0..1). Формула: base = max(profit_net, 0.0) или 1.0 если неизвестно;
    вес = base × (1 + gap). Карточка с ошибкой/без индекса (gap=1) весит вдвое против добравшей.
    """
    if isinstance(margin, dict):
        pn = margin.get("profit_net")
    else:
        pn = _num(margin)
    base = pn if isinstance(pn, (int, float)) else None
    if base is None:
        base = 1.0            # выгода неизвестна → нейтральная единица (не 0: действие всё равно имеет смысл)
    elif base < 0:
        base = 0.0            # заведомо убыточную карточку не двигаем вверх по выгоде
    g = _num(gap)
    g = 0.0 if g is None else max(0.0, min(1.0, g))
    return round(base * (1.0 + g), 4)


def action_pays(gain_estimate, labor_rub=DEFAULT_LABOR_RUB):
    """Окупается ли действие: оценка прироста ₽ ≥ оценка труда. Возвращает разбор (sound=bool).

    ЧЕСТНОСТЬ: gain_estimate=None → неизвестно, sound=True с флагом assumed=True (не блокируем
    полезное действие из-за отсутствия оценки, но помечаем что прирост не доказан). Отрицательный
    или нулевой прирост при известной оценке → sound=False (не жжём тик впустую).
    """
    labor = _num(labor_rub)
    labor = DEFAULT_LABOR_RUB if labor is None else labor
    gain = _num(gain_estimate)
    if gain is None:
        return {"sound": True, "assumed": True, "gain_estimate": None,
                "labor_rub": round(labor, 2), "net": None}
    net = round(gain - labor, 2)
    return {"sound": gain >= labor, "assumed": False, "gain_estimate": round(gain, 2),
            "labor_rub": round(labor, 2), "net": net}


def rating_gain_estimate(recommendations):
    """Оценка прироста индекса (в пунктах) от закрытия ЗАКРЫВАЕМЫХ рекомендаций. Сумма remainingRatingPoints.

    recommendations — список {type, remainingRatingPoints} (из card.card_quality). Считаем только
    сумму пунктов (это «сколько поднимем»). Что именно закрываемо — решает writer (CLOSABLE_RECS);
    здесь чистая арифметика прироста. Пусто/нет чисел → None (нечего оценивать).
    """
    if not isinstance(recommendations, list):
        return None
    pts = [_num(r.get("remainingRatingPoints")) for r in recommendations
           if isinstance(r, dict)]
    pts = [p for p in pts if p is not None]
    return round(sum(pts), 2) if pts else None


if __name__ == "__main__":
    import json
    demo = {
        "with_cost": sku_margin({"price": 149, "cost": 90, "fee": 22}),
        "cost_only": sku_margin({"price": 149}),
        "no_price": sku_margin({}),
        "gap_at_60": index_gap(60),
        "gap_full": index_gap(100),
        "gap_none": index_gap(None),
        "weight_good": priority_weight(sku_margin({"price": 149, "cost": 90}), index_gap(60)),
        "weight_unknown": priority_weight(sku_margin({}), index_gap(None)),
        "pays_known": action_pays(30),
        "pays_unknown": action_pays(None),
    }
    print(json.dumps(demo, ensure_ascii=False, indent=2))

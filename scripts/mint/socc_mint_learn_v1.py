#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT PROSPECTOR learning V1 — орган учится ранжировать связки ТОЛЬКО на доказанной реальности.

Контур обучения (MINT §5, расширение соревнования вселенных): связки, дошедшие до verified=true в
леджере, поднимают приоритет похожих будущих связок; связки, застрявшие в claim (деньги не пришли) —
опускают. Это замыкает петлю PROSPECTOR → WARDEN → MERCHANT → LEDGER(proof) → обратно в PROSPECTOR:
орган становится умнее ровно настолько, насколько реально заработал.

Сигнатура связки = (venture, ценовой диапазон) — грубая, чтобы ОБОБЩАТЬ опыт, а не запоминать товар.
Множитель прайора считается байесовским сжатием (Beta-сглаживание): на малой выборке тянется к базовой
конверсии, поэтому одно событие не диктует ранг (это и есть «законно инженерно», без переобучения).

ЗАКОН ЧЕСТНОСТИ ОБУЧЕНИЯ:
  • учимся ТОЛЬКО на stage=='verified' (реальные прочитанные деньги). claim без verify — сигнал провала
    достижимости (не доход);
  • симуляция/песочница в канонический revenue_ledger не попадает (см. socc_revenue_ledger_v1), поэтому
    орган физически не может «выучить» ненастоящую прибыль;
  • нет ни одной verified-записи → status='insufficient_data', все множители = 1.0 (орган не выдумывает
    обучение на пустоте).

Чистый stdlib. Без сети, без LLM.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import socc_revenue_ledger_v1 as ledger  # noqa: E402

# Ценовые диапазоны (₽) для сигнатуры — грубые, чтобы обобщать опыт, а не запоминать конкретный товар.
PRICE_BANDS = [(0, 500), (500, 1000), (1000, 2000), (2000, 3500), (3500, 6000), (6000, float("inf"))]

# Beta-прайор (a0,b0): слабый симметричный — на малой выборке тянет апостериор к базовой конверсии (сжатие).
A0, B0 = 1.0, 1.0
# Множитель прайора зажат: обучение ВЛИЯЕТ на ранг, но не диктует его (≤ 2× вверх / ≥ 0.5× вниз).
MULT_LO, MULT_HI = 0.5, 2.0


def price_band(price):
    """Метка ценового диапазона для цены продажи (часть сигнатуры связки)."""
    p = float(price or 0)
    for lo, hi in PRICE_BANDS:
        if lo <= p < hi:
            return f"{int(lo)}-{'inf' if hi == float('inf') else int(hi)}"
    return "0-500"


def signature(venture, price):
    """Сигнатура связки: (вселенная, ценовой диапазон). Опыт обобщается внутри сигнатуры."""
    return f"{venture}|{price_band(price)}"


def learn_from_ledger():
    """Свести опыт органа из леджера.

    return: {status, base_rate, total_claims, total_verified, signatures: {sig: {...}}}
      • n_claims    — попыток (знаменатель достижимости) в сигнатуре;
      • n_verified  — доказанных денег (числитель), матч claim↔verified по connection_id;
      • conversion  — апостериорная конверсия с Beta-сглаживанием;
      • multiplier  — множитель ранга в [0.5, 2.0] (1.0 = нейтрально).
    status='insufficient_data' пока нет ни одной verified-записи (тогда все множители 1.0).
    """
    rows = ledger._read()
    verified_ids = {r["connection_id"] for r in rows
                    if r.get("stage") == "verified" and r.get("verified")}

    sigs = {}
    for r in rows:
        if r.get("stage") != "claim":
            continue
        sig = signature(r.get("venture", "?"), r.get("price_sell"))
        s = sigs.setdefault(sig, {"signature": sig, "n_claims": 0, "n_verified": 0,
                                  "verified_profit_total": 0.0})
        s["n_claims"] += 1
        if r.get("connection_id") in verified_ids:
            s["n_verified"] += 1

    for r in rows:
        if r.get("stage") == "verified" and r.get("verified"):
            sig = signature(r.get("venture", "?"), r.get("price_sell"))
            if sig in sigs:
                sigs[sig]["verified_profit_total"] = round(
                    sigs[sig]["verified_profit_total"] + float(r.get("profit_net") or 0), 2)

    total_claims = sum(s["n_claims"] for s in sigs.values())
    total_verified = sum(s["n_verified"] for s in sigs.values())
    status = "insufficient_data" if total_verified == 0 else "learning"
    base_rate = (total_verified / total_claims) if total_claims > 0 else 0.0

    for s in sigs.values():
        post = (s["n_verified"] + A0) / (s["n_claims"] + A0 + B0)  # апостериорная конверсия (сжатие)
        s["conversion"] = round(post, 4)
        s["verified_profit_avg"] = round(
            s["verified_profit_total"] / s["n_verified"], 2) if s["n_verified"] > 0 else 0.0
        if status == "insufficient_data" or base_rate <= 0:
            s["multiplier"] = 1.0
        else:
            s["multiplier"] = round(min(MULT_HI, max(MULT_LO, post / base_rate)), 4)

    return {"status": status, "base_rate": round(base_rate, 4),
            "total_claims": total_claims, "total_verified": total_verified, "signatures": sigs}


def make_prior_fn(venture):
    """Прайор-функция для PROSPECTOR.prospect(prior_fn=...): по (item, margin) → множитель ранга [0.5,2.0].

    Снимок опыта берётся один раз на вызов (модель из леджера). На пустом/недостаточном леджере всегда
    1.0 (нейтрально) — орган не выдумывает обучение там, где нет доказанных денег.
    """
    model = learn_from_ledger()
    sigs = model["signatures"]
    insufficient = model["status"] == "insufficient_data"

    def prior(item, margin=None):
        if insufficient:
            return 1.0
        price = (margin or {}).get("price_sell") if margin else None
        if price is None:
            price = item.get("price_sell") or item.get("cost", 0)
        s = sigs.get(signature(venture, price))
        return s["multiplier"] if s else 1.0

    return prior


if __name__ == "__main__":
    import json
    print(json.dumps(learn_from_ledger(), ensure_ascii=False, indent=2))

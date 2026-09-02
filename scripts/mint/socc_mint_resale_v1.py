#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT Venture D3 — Avito выкуп-перепродажа (третья вселенная). ДОКАЗАТЕЛЬСТВО шаблонирования Π(roster, D').

Новая тема = только новый дескриптор + локальная маржа/тест. ВСЁ дорогое переиспользовано БЕЗ правки ядра:
  • ledger.record_claim/verify/ranking  — кровь и соревнование (socc_revenue_ledger_v1) — не тронуто;
  • warden.gate                          — иммунитет красных линий — не тронуто;
  • service_pay.fetch_service_payout     — руки t4 (банк/СБП) — переиспользованы как есть;
  • cycle._cid/_emit_proof/_finish       — proof такта связки — переиспользованы;
  • learn/self                           — обучение и само-модель ВКЛЮЧАЮТ D3 автоматически по venture.

Связка честная (RL4 серое ≤ легальное): выкуп НЕДООЦЕНЁННОГО лота → честная карточка (дефекты раскрыты) →
перепродажа своего товара. Деньги покупателя идут на свой счёт за СВОЙ товар (не мул, не чужие средства).
Чистый stdlib. Верификация денег детерминированная (без LLM).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import socc_revenue_ledger_v1 as ledger            # noqa: E402  (переиспользуем кровь)
import socc_mint_warden_v1 as warden                # noqa: E402  (переиспользуем иммунитет)
import socc_mint_service_pay_v1 as service_pay      # noqa: E402  (переиспользуем руки t4)
import socc_mint_cycle_v1 as cycle                  # noqa: E402  (переиспользуем _cid/_emit_proof/_finish/DRY_LEDGER)

# Domain D3 — третья вселенная (полный дескриптор, MINT-SPEC §1).
D3_RESALE = {
    "id": "resale-avito-RU",
    "market": "Avito",
    "sources": ["avito"],
    "integration": "manual",                 # выкуп/листинг — ручные (массовый парсинг в обход ToS = RL4)
    "legal_form": "самозанятость",
    "profit_target": 1000, "min_profit": 300,
    "verify_sources": ["sbp_inbound", "bank_statement_ip", "avito_delivery"],
    "law_overrides": {"disclose_defects": True, "no_third_party_funds": True},
}


def compute_resale_margin(price_buy, price_sell, fees=0):
    """Маржа перепродажи: profit = цена_продажи − цена_выкупа − издержки (доставка/продвижение)."""
    cost = float(price_buy or 0)
    sell = float(price_sell or 0)
    fee = float(fees or 0)
    profit_net = round(sell - cost - fee, 2)
    return {"cost_buy": cost, "price_sell": sell, "fee": fee,
            "seller_receipt": round(sell - fee, 2), "profit_net": profit_net}


def resale_falsifiable_test(item):
    """Опровержимый тест достижимости перепродажи (Φ(p2) для D3). {passed, checks, why, margin}.

      • buy_known      — цена выкупа известна и > 0
      • margin_positive — маржа после издержек > 0
      • supply_real    — лот реально существует у источника (url/lot id)
      • demand_signal  — есть СИГНАЛ спроса (аналоги проданы / реальный покупатель), не «на ощущениях»
    """
    m = compute_resale_margin(item.get("price_buy", 0), item.get("price_sell", 0), item.get("fees", 0))
    checks = {
        "buy_known": float(item.get("price_buy", 0)) > 0,
        "margin_positive": m["profit_net"] > 0,
        "supply_real": bool(item.get("url") or item.get("lot_id")),
        "demand_signal": bool(item.get("demand_signal")),
    }
    passed = all(checks.values())
    return {"passed": passed, "checks": checks, "why": [k for k, ok in checks.items() if not ok], "margin": m}


def _descriptor(item, margin):
    """Дескриптор связки перепродажи для WARDEN (что именно делаем)."""
    return {
        "venture": D3_RESALE["id"],
        "legal_form": D3_RESALE["legal_form"],
        "description": f"легальная перепродажа недооценённого лота «{item.get('name')}» с Avito, честная карточка",
        "mechanism": "выкупаю свой товар → честная карточка с раскрытыми дефектами → продаю; деньги за СВОЙ товар на свой счёт",
        "tags": ["resale", "arbitrage", "avito"],
        "handles_third_party_funds": item.get("handles_third_party_funds", False),
        "resells_platform_access": item.get("resells_platform_access", False),
        "impersonates_real_person": item.get("impersonates_real_person", False),
        "deceives_customer": item.get("deceives_customer", False),  # скрыть дефект = True → WARDEN режет (RL4)
        "margin": margin,
    }


def run_resale_connection(item, mode="dry", payout=None, fulfilled=False):
    """Прогнать одну связку перепродажи по DAG t0..t6. Переиспользует proof/ledger/warden/руки."""
    if mode == "dry":
        ledger.LEDGER = Path(cycle.DRY_LEDGER)  # общий песочный леджер → соревнование в одном ранге с D1/D2

    steps, checks = [], {}
    connection_id = cycle._cid(D3_RESALE, {"name": item.get("name")})

    # --- t0 discover (тест достижимости перепродажи) ---
    t = resale_falsifiable_test(item)
    t0_ok = t["passed"] and t["margin"]["profit_net"] >= float(item.get("min_profit", D3_RESALE["min_profit"]))
    checks["t0_discover_falsifiable"] = t0_ok
    steps.append({"atom": "t0_discover", "ok": t0_ok, "detail": t["checks"] if t0_ok else t["why"]})
    if not t0_ok:
        return cycle._finish(connection_id, "FAIL", steps, checks, "t0: лот не прошёл фальсиф. тест/примитив")
    margin = t["margin"]

    # --- WARDEN gate ---
    w = warden.gate(_descriptor(item, margin))
    checks["warden_gate"] = (w["status"] == "PASS")
    steps.append({"atom": "warden_gate", "ok": checks["warden_gate"], "detail": w["reasons"] or "красные линии чисты"})
    if w["status"] != "PASS":
        return cycle._finish(connection_id, "FAIL", steps, checks, "WARDEN: " + "; ".join(w["reasons"]))

    # --- t1 list ---
    checks["t1_list_price"] = margin["price_sell"] > 0
    steps.append({"atom": "t1_list", "ok": True, "detail": {"price_sell": margin["price_sell"]}})

    # --- t2 order ---
    if mode == "dry":
        order_ref = item.get("order_ref") or f"DRY-{connection_id}"
        order_ok = True
    else:
        order_ref = item.get("order_ref")
        order_ok = bool(order_ref)
    checks["t2_order_real_source"] = bool(order_ok and order_ref)
    steps.append({"atom": "t2_order", "ok": checks["t2_order_real_source"], "detail": {"order_ref": order_ref}})
    if not checks["t2_order_real_source"]:
        return cycle._finish(connection_id, "FAIL", steps, checks, "t2: нет реального заказа (order_ref)")

    ledger.record_claim(
        venture=D3_RESALE["id"], connection_id=connection_id, item=item.get("name"),
        cost_buy=margin["cost_buy"], price_sell=margin["price_sell"], fee=margin["fee"],
        meta={"mode": mode, "order_ref": order_ref, "note": "доход verified только при поступлении из реального источника"})

    # --- t3 fulfill (товар передан покупателю) ---
    t3_ok = True if mode == "dry" else bool(fulfilled)
    checks["t3_fulfill_real"] = t3_ok
    steps.append({"atom": "t3_fulfill", "ok": t3_ok, "detail": "передан (dry)" if mode == "dry" else ("передан" if fulfilled else "НЕ передан")})
    if not t3_ok:
        return cycle._finish(connection_id, "FAIL", steps, checks, "t3: товар не передан (real требует fulfilled=True)")

    # --- t4 verify_money (переиспользуем руки услуг: банк/СБП/Avito Доставка) ---
    if mode == "dry":
        amount = margin["seller_receipt"]
        _, err = ledger.verify(connection_id, amount, "dry_run_sim",
                               evidence={"mode": "dry", "note": "симуляция поступления — НЕ реальные деньги"})
    else:
        payout = payout or {}
        src = payout.get("source", "sbp_inbound")
        amount, ev = service_pay.fetch_service_payout(connection_id, src, ref=payout.get("ref"),
                                                      amount=payout.get("amount"), inn=payout.get("inn"))
        if amount is None:
            checks["t4_verify_money"] = False
            steps.append({"atom": "t4_verify_money", "ok": False, "detail": ev})
            return cycle._finish(connection_id, "FAIL", steps, checks, f"t4: {ev}")
        _, err = ledger.verify(connection_id, amount, src, evidence=ev)
    checks["t4_verify_money"] = (err is None)
    steps.append({"atom": "t4_verify_money", "ok": err is None, "detail": err or {"verified_amount": amount}})
    if err:
        return cycle._finish(connection_id, "FAIL", steps, checks, f"t4 verify refused: {err}")

    return cycle._finish(connection_id, "PASS", steps, checks,
                         "dry-run: verified из симуляции (песочница)" if mode == "dry"
                         else "real: verified из реального источника (СБП/банк/Avito Доставка)")


# Sample-лот для dry-run: выкуп 3000 → продажа 7000, издержки 500 → маржа 3500 ₽; аналоги проданы.
SAMPLE_LOT = {"name": "Диван б/у (выкуп с Avito)", "price_buy": 3000, "price_sell": 7000, "fees": 500,
              "url": "avito://lot/demo-1", "order_ref": "AV-demo-1",
              "demand_signal": {"kind": "comparable_sold", "count": 8}}


if __name__ == "__main__":
    import json
    mode = "real" if "--real" in sys.argv else "dry"
    res = run_resale_connection(dict(SAMPLE_LOT), mode=mode)
    print(json.dumps({"mode": mode, "connection_id": res["connection_id"], "status": res["status"],
                      "truth": res["proof"]["truth_boundary"], "ranking": ledger.ranking()},
                     ensure_ascii=False, indent=2))

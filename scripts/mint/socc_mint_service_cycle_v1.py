#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT service cycle runner V1 — вселенная D2 (service-leadgen-RU) по DAG t0..t6, proof-gated, fail-closed.

Паритет с D1 (socc_mint_cycle_v1): тот же цикл, но для УСЛУГИ. Переиспользует _emit_proof/_finish/_cid и
общий песочный леджер cycle.DRY_LEDGER (чтобы D1 и D2 соревновались в одном ranking()). Новое — только
сервис-специфика: prospect(kind="service"), сервис-дескриптор для WARDEN, руки t4 socc_mint_service_pay.

  t0 discover (PROSPECTOR/услуга) → w-gate → t1 list(оффер) → t2 order(заявка)
    → t3 fulfill(услуга оказана) → t4 verify_money(комиссия поступила) → t5 proof → t6 emit

Инвариант против мула (RL1): деньги КЛИЕНТА идут напрямую исполнителю/через эскроу; система берёт ТОЛЬКО
свою комиссию на свой счёт. Исполнитель — реальный человек (партнёр оператора), не фейк (RL3).

Режимы: dry — песочница (verified из симуляции, канон не трогаем) · real — t4 из реального источника
(банк/СБП/чек НПД/эскроу через socc_mint_service_pay), verified=true ТОЛЬКО при реальном поступлении.
Чистый stdlib. Без LLM (верификация денег детерминированная).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import socc_revenue_ledger_v1 as ledger        # noqa: E402
import socc_mint_warden_v1 as warden            # noqa: E402
import socc_mint_prospect_v1 as prospect        # noqa: E402
import socc_mint_service_pay_v1 as service_pay  # noqa: E402
import socc_mint_cycle_v1 as cycle              # noqa: E402  (reuse _emit_proof/_finish/_cid/DRY_LEDGER)

# Domain D2 — вторая вселенная (полный дескриптор, MINT-SPEC §1).
D2_SERVICE = {
    "id": "service-leadgen-RU",
    "market": "Profi.ru / YouDo / Avito Услуги",
    "sources": ["profi", "youdo", "avito_services"],
    "integration": "manual",                 # площадки услуг ~без открытого API → RUBICON-захват лида
    "legal_form": "самозанятость",           # MN2 (для крупного — ИП)
    "commission_rate": 0.15,
    "profit_target": 600, "min_profit": 200,
    "verify_sources": ["bank_statement_ip", "sbp_inbound", "moy_nalog_receipt", "youdo_escrow", "profi_escrow"],
    "law_overrides": {"npd_receipt_required": True, "no_third_party_funds": True},
}


def _service_descriptor(domain, lead, margin):
    """Дескриптор связки услуги для WARDEN-гейта (что именно делаем)."""
    executor = lead.get("executor") or lead.get("master") or "?"
    return {
        "venture": domain.get("id"),
        "legal_form": domain.get("legal_form", ""),
        "description": f"свод реального спроса на «{lead.get('service')}» с реальным исполнителем {executor}, комиссия с оказанной услуги",
        "mechanism": "честное посредничество: деньги клиента идут напрямую исполнителю/через эскроу, система берёт только комиссию на свой счёт",
        "tags": ["leadgen", "services", lead.get("source", "manual")],
        # явные флаги красных линий — для честной связки все False:
        "handles_third_party_funds": lead.get("handles_third_party_funds", False),
        "resells_platform_access": lead.get("resells_platform_access", False),
        "impersonates_real_person": lead.get("impersonates_real_person", False),
        "deceives_customer": lead.get("deceives_customer", False),
        "margin": margin,
    }


def run_service_connection(domain, lead, mode="dry", payout=None, fulfilled=False):
    """Прогнать одну связку услуги. Возвращает {connection_id, status, steps, proof, ledger_verdict}."""
    if mode == "dry":
        ledger.LEDGER = Path(cycle.DRY_LEDGER)  # общий песочный леджер с D1 → соревнование в одном ранге

    steps, checks = [], {}
    connection_id = cycle._cid(domain, {"name": lead.get("service")})

    # --- t0 discover (PROSPECTOR / услуга) ---
    found = prospect.prospect([lead], kind="service",
                              profit_target=domain.get("profit_target", 600),
                              min_profit=domain.get("min_profit", 200))
    t0_ok = len(found) > 0
    checks["t0_discover_falsifiable"] = t0_ok
    steps.append({"atom": "t0_discover", "ok": t0_ok,
                  "detail": found[0]["falsifiable"]["checks"] if t0_ok else "лид не прошёл фальсиф. тест/примитив"})
    if not t0_ok:
        return cycle._finish(connection_id, "FAIL", steps, checks, "t0: нет доказанного лида")
    margin = found[0]["margin"]

    # --- WARDEN gate (красные линии до листинга) ---
    w = warden.gate(_service_descriptor(domain, lead, margin))
    checks["warden_gate"] = (w["status"] == "PASS")
    steps.append({"atom": "warden_gate", "ok": checks["warden_gate"],
                  "detail": w["reasons"] or "красные линии чисты"})
    if w["status"] != "PASS":
        return cycle._finish(connection_id, "FAIL", steps, checks, "WARDEN: " + "; ".join(w["reasons"]))

    # --- t1 list (оффер услуги, цена = комиссия) ---
    checks["t1_list_price_from_formula"] = margin["price_sell"] > 0
    steps.append({"atom": "t1_list", "ok": True,
                  "detail": {"commission": margin["price_sell"], "from_formula": True}})

    # --- t2 order (реальная заявка клиента) ---
    if mode == "dry":
        lead_ref = lead.get("lead_ref") or f"DRY-{connection_id}"
        order_ok = True
    else:
        lead_ref = lead.get("lead_ref")
        order_ok = bool(lead_ref)
    checks["t2_order_real_source"] = bool(order_ok and lead_ref)
    steps.append({"atom": "t2_order", "ok": checks["t2_order_real_source"], "detail": {"lead_ref": lead_ref}})
    if not checks["t2_order_real_source"]:
        return cycle._finish(connection_id, "FAIL", steps, checks, "t2: нет реальной заявки (lead_ref)")

    # claim (verified=false) — обязательство ещё не закрыто
    ledger.record_claim(
        venture=domain.get("id"), connection_id=connection_id,
        item=f"{lead.get('service')} → {lead.get('executor') or lead.get('master')}",
        cost_buy=margin["cost_buy"], price_sell=margin["price_sell"], fee=margin["fee"],
        meta={"mode": mode, "lead_ref": lead_ref, "ticket_value": margin.get("ticket_value"),
              "note": "комиссия verified только при поступлении из реального источника"})

    # --- t3 fulfill (услуга оказана исполнителем) ---
    t3_ok = True if mode == "dry" else bool(fulfilled)
    checks["t3_fulfill_real"] = t3_ok
    steps.append({"atom": "t3_fulfill", "ok": t3_ok,
                  "detail": "оказано (dry)" if mode == "dry" else ("оказано" if fulfilled else "НЕ оказано")})
    if not t3_ok:
        return cycle._finish(connection_id, "FAIL", steps, checks,
                             "t3: услуга не оказана (real-режим требует fulfilled=True)")

    # --- t4 verify_money (комиссия поступила — LEDGER + руки услуг) ---
    if mode == "dry":
        amount = margin["seller_receipt"]
        vrec, err = ledger.verify(connection_id, amount, "dry_run_sim",
                                  evidence={"mode": "dry", "note": "симуляция поступления комиссии — НЕ реальные деньги"})
    else:
        payout = payout or {}
        amount, ev = service_pay.fetch_service_payout(
            connection_id, payout.get("source"), ref=payout.get("ref"),
            amount=payout.get("amount"), inn=payout.get("inn"), online_check=payout.get("online_check"))
        if amount is None:
            checks["t4_verify_money"] = False
            steps.append({"atom": "t4_verify_money", "ok": False, "detail": ev})
            return cycle._finish(connection_id, "FAIL", steps, checks, f"t4: {ev}")
        vrec, err = ledger.verify(connection_id, amount, payout.get("source"), evidence=ev)
    checks["t4_verify_money"] = (err is None)
    steps.append({"atom": "t4_verify_money", "ok": err is None,
                  "detail": err or {"verified_amount": vrec["verify_amount"], "source": vrec["verify_source"]}})
    if err:
        return cycle._finish(connection_id, "FAIL", steps, checks, f"t4 verify refused: {err}")

    return cycle._finish(connection_id, "PASS", steps, checks,
                         "dry-run: verified из симуляции (песочница)" if mode == "dry"
                         else "real: verified из реального источника услуги (банк/НПД/эскроу)")


# Sample-лид для dry-run: реальная заявка, реальный исполнитель-партнёр, чек 4000 ₽ → комиссия 600 ₽.
SAMPLE_LEAD = {"service": "сборка мебели", "ticket_value": 4000, "executor": "Иван (партнёр)",
               "demand_real": {"kind": "platform_request", "lead_ref": "YD-demo-1"},
               "lead_ref": "YD-demo-1", "source": "youdo"}


if __name__ == "__main__":
    import json
    mode = "real" if "--real" in sys.argv else "dry"
    res = run_service_connection(D2_SERVICE, dict(SAMPLE_LEAD), mode=mode)
    out = {"mode": mode, "ledger_path": str(ledger.LEDGER),
           "connection_id": res["connection_id"], "status": res["status"],
           "truth": res["proof"]["truth_boundary"],
           "ranking": ledger.ranking()}
    print(json.dumps(out, ensure_ascii=False, indent=2))

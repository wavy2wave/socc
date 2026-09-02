#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT cycle runner V1 — гоняет одну связку по DAG t0..t6 (MINT-SPEC-1 §2), proof-gated, fail-closed.

  t0 discover (PROSPECTOR) → w-gate → t1 list (MERCHANT) → t2 order → t3 fulfill
    → t4 verify_money (LEDGER) → t5 proof → t6 emit_verified_tx

WARDEN-гейт (красные линии RL1–RL4 + MN2) висит перед исполнением: нарушение → стоп до листинга.

Режимы:
  • dry  — песочница: полный цикл t0..t6 на sample, verified из симулированного источника, пишет в
           /tmp леджер (канон НЕ трогается). Доказывает, что механизм замыкается.
  • real — t2 из реального Ozon FBS, t3 — отметка отгрузки оператором, t4 — чтение Ozon Finance payout.
           verified=true ТОЛЬКО при реальном поступлении. Пишет в канонический revenue_ledger.

Чистый stdlib (сетевые вызовы Ozon — ленивые, только в real). Без LLM (верификация денег детерминированная).
"""
import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # SOCC/
sys.path.insert(0, str(HERE))

import socc_revenue_ledger_v1 as ledger      # noqa: E402
import socc_mint_warden_v1 as warden          # noqa: E402
import socc_mint_prospect_v1 as prospect      # noqa: E402
import socc_mint_ozon_v1 as ozon              # noqa: E402

DRY_LEDGER = "/tmp/mint_dry_ledger.jsonl"
PROOF_DIR = ROOT / "MEMORY_WAVE/reports/mint"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _cid(domain, item):
    base = f"{domain.get('id')}|{item.get('name')}|{_now()}"
    return domain.get("id", "v") + "-" + hashlib.sha256(base.encode()).hexdigest()[:10]


def _connection_descriptor(domain, item, margin):
    """Описание связки для WARDEN-гейта (что именно мы собираемся делать)."""
    return {
        "venture": domain.get("id"),
        "legal_form": domain.get("legal_form", ""),
        "description": f"легальный розничный арбитраж: {item.get('name')} → {domain.get('market')}",
        "mechanism": "честная карточка, реальная отгрузка, налог уплачивается",
        "tags": ["retail", "arbitrage"],
        # явные флаги красных линий — все False для честной связки:
        "handles_third_party_funds": item.get("handles_third_party_funds", False),
        "resells_platform_access": item.get("resells_platform_access", False),
        "impersonates_real_person": item.get("impersonates_real_person", False),
        "deceives_customer": item.get("deceives_customer", False),
        "margin": margin,
    }


def _emit_proof(connection_id, status, checks, truth_boundary):
    hard = [k for k, ok in checks.items() if not ok]
    proof = {
        "id": connection_id,
        "ts": _now(),
        "organ": "MINT",
        "status": "PASS" if (status == "PASS" and not hard) else "FAIL",
        "checks": checks,
        "hard_failures": hard,
        "next_after_pass": "t6_emit_verified_tx" if not hard else None,
        "next_lawful_step": "emit" if not hard else f"manual_{connection_id}_repair_required",
        "truth_boundary": truth_boundary,
    }
    proof["proof_hash"] = hashlib.sha256(
        json.dumps(proof, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    (PROOF_DIR / f"connection_{connection_id}.json").write_text(
        json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    return proof


def run_connection(domain, item, mode="dry", posting_number=None, fulfilled=False):
    """Прогнать одну связку. Возвращает {connection_id, status, steps, ledger, proof}."""
    if mode == "dry":
        ledger.LEDGER = Path(DRY_LEDGER)  # песочница: канон не трогаем

    steps = []
    checks = {}
    connection_id = _cid(domain, item)

    # --- t0 discover (PROSPECTOR) ---
    found = prospect.prospect([item], profit_target=domain.get("profit_target", 600),
                              min_profit=domain.get("min_profit", 200))
    t0_ok = len(found) > 0
    checks["t0_discover_falsifiable"] = t0_ok
    steps.append({"atom": "t0_discover", "ok": t0_ok,
                  "detail": found[0]["falsifiable"] if t0_ok else "связка не прошла фальсиф. тест/примитив"})
    if not t0_ok:
        return _finish(connection_id, "FAIL", steps, checks, "t0: нет доказанной связки")
    margin = found[0]["margin"]

    # --- WARDEN gate (красные линии до листинга) ---
    descriptor = _connection_descriptor(domain, item, margin)
    w = warden.gate(descriptor)
    checks["warden_gate"] = (w["status"] == "PASS")
    steps.append({"atom": "warden_gate", "ok": checks["warden_gate"],
                  "detail": w["reasons"] or "красные линии чисты"})
    if w["status"] != "PASS":
        return _finish(connection_id, "FAIL", steps, checks, "WARDEN: " + "; ".join(w["reasons"]))

    # --- t1 list (MERCHANT) ---
    checks["t1_list_price_from_formula"] = margin["price_sell"] > 0
    steps.append({"atom": "t1_list", "ok": True,
                  "detail": {"price_sell": margin["price_sell"], "from_formula": True}})

    # --- t2 order ---
    if mode == "dry":
        posting_number = posting_number or f"DRY-{connection_id}"
        order_ok = True
    else:
        if not posting_number:
            # реальный заказ берётся из кабинета; оператор передаёт posting_number отгружаемого заказа
            orders = ozon.fetch_new_orders()
            order_ok = len(orders) > 0
            posting_number = orders[0].get("posting_number") if order_ok else None
        else:
            order_ok = True
    checks["t2_order_real_source"] = bool(order_ok and posting_number)
    steps.append({"atom": "t2_order", "ok": checks["t2_order_real_source"], "detail": {"posting": posting_number}})
    if not checks["t2_order_real_source"]:
        return _finish(connection_id, "FAIL", steps, checks, "t2: нет реального заказа")

    # claim (verified=false) — обязательство ещё не закрыто
    claim = ledger.record_claim(
        venture=domain.get("id"), connection_id=connection_id, item=item.get("name"),
        cost_buy=margin["cost_buy"], price_sell=margin["price_sell"], fee=margin["fee"],
        meta={"mode": mode, "posting": posting_number})

    # --- t3 fulfill ---
    t3_ok = True if mode == "dry" else bool(fulfilled)
    checks["t3_fulfill_real"] = t3_ok
    steps.append({"atom": "t3_fulfill", "ok": t3_ok,
                  "detail": "отгружено (dry)" if mode == "dry" else ("отгружено" if fulfilled else "НЕ отгружено")})
    if not t3_ok:
        return _finish(connection_id, "FAIL", steps, checks,
                       "t3: обязательство не исполнено (real-режим требует fulfilled=True)")

    # --- t4 verify_money (LEDGER) ---
    if mode == "dry":
        amount = margin["seller_receipt"]
        vrec, err = ledger.verify(connection_id, amount, "dry_run_sim",
                                  evidence={"mode": "dry", "note": "симуляция поступления — НЕ реальные деньги"})
    else:
        amount, ev = ozon.fetch_posting_payout(posting_number)
        if amount is None:
            checks["t4_verify_money"] = False
            steps.append({"atom": "t4_verify_money", "ok": False, "detail": ev})
            return _finish(connection_id, "FAIL", steps, checks, f"t4: {ev}")
        vrec, err = ledger.verify(connection_id, amount, "ozon_finance", evidence=ev)
    checks["t4_verify_money"] = (err is None)
    steps.append({"atom": "t4_verify_money", "ok": err is None,
                  "detail": err or {"verified_amount": vrec["verify_amount"], "source": vrec["verify_source"]}})
    if err:
        return _finish(connection_id, "FAIL", steps, checks, f"t4 verify refused: {err}")

    return _finish(connection_id, "PASS", steps, checks,
                   "dry-run: verified из симуляции (песочница)" if mode == "dry"
                   else "real: verified из Ozon Finance payout")


def _finish(connection_id, status, steps, checks, truth_boundary):
    proof = _emit_proof(connection_id, status, checks, truth_boundary)
    return {"connection_id": connection_id, "status": proof["status"], "steps": steps,
            "proof": proof, "ledger_verdict": ledger.verdict()}


# Domain D1 — первая вселенная.
D1_OZON = {"id": "ozon-dropship-RU", "market": "Ozon", "legal_form": "самозанятость",
           "profit_target": 600, "min_profit": 200}


if __name__ == "__main__":
    mode = "real" if "--real" in sys.argv else "dry"
    # dry-run: гоняем sample-связки через полный цикл
    results = []
    items = prospect.SAMPLE if mode == "dry" else []
    for it in items:
        results.append(run_connection(D1_OZON, it, mode=mode))
    out = {"mode": mode, "ledger_path": str(ledger.LEDGER),
           "results": [{"connection_id": r["connection_id"], "status": r["status"],
                        "truth": r["proof"]["truth_boundary"]} for r in results],
           "summary_by_venture": ledger.summary_by_venture(),
           "ranking": ledger.ranking(),
           "verdict": ledger.verdict()}
    print(json.dumps(out, ensure_ascii=False, indent=2))

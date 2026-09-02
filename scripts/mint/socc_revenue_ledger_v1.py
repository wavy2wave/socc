#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT Revenue Ledger V1 — кровь финансового органа: доход как доказанное событие.

Зеркало socc_token_ledger_v1.py, но мерит НЕ расход мозга, а ПРИХОД в мир. Две стадии (закон LG1/LG2):
  • record_claim(...)  — связка исполнена (отгрузка/услуга), ₽ ЗАЯВЛЕН (verified=false). Это ещё не доход.
  • verify(...)        — деньги ПРОЧИТАНЫ из реального источника (Ozon payout / банк). Только тогда verified=true.

Инвариант честности (MINT §3, Φ(t4)):
  verified=true  ⟺  есть verify_source + сумма > 0  ∧  claim с тем же connection_id существует.
Сомнение → не verified. MINT не умеет рисовать доход — только читать поступление.

Ledger: SOVEREIGN/LEDGER/revenue_ledger.jsonl (append-only). Чистый stdlib. Без сети, без LLM.
"""
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/mint/ -> scripts -> SOCC/
# Канонический леджер органа. Dry-run/тесты перенаправляют в песочницу через MINT_LEDGER_PATH,
# чтобы в SOVEREIGN/LEDGER никогда не попал ненастоящий verified-доход (закон честности канона).
LEDGER = Path(os.environ["MINT_LEDGER_PATH"]) if os.environ.get("MINT_LEDGER_PATH") \
    else ROOT / "SOVEREIGN/LEDGER/revenue_ledger.jsonl"

# Источники-СИМУЛЯЦИИ: verified в песочнице, НЕ реальные деньги (зеркало self_v1.SIM_SOURCE).
# Всё, что НЕ здесь, считается реальным источником (банк/СБП/чек НПД/Ozon payout).
SIM_SOURCES = {"dry_run_sim"}


def is_real_source(verify_source) -> bool:
    """Реальный источник ⟺ не симуляция. Мост тратит ТОЛЬКО реальные (real_only)."""
    return bool(verify_source) and verify_source not in SIM_SOURCES


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def _read():
    if not LEDGER.exists():
        return []
    out = []
    for ln in LEDGER.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out


def _append(rec):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def record_claim(venture, connection_id, item, cost_buy, price_sell, fee=0, meta=None):
    """Стадия 1: обязательство исполнено, ₽ заявлен (verified=false). Возвращает запись claim.

    profit_net = price_sell - cost_buy - fee  (честный знаменатель: все издержки учтены — LG4).
    """
    cost_buy = float(cost_buy or 0)
    price_sell = float(price_sell or 0)
    fee = float(fee or 0)
    profit_net = round(price_sell - cost_buy - fee, 2)
    rec = {
        "ts": _now(),
        "organ": "MINT",
        "stage": "claim",
        "venture": venture,
        "connection_id": connection_id,
        "item": item,
        "cost_buy": cost_buy,
        "price_sell": price_sell,
        "fee": fee,
        "profit_net": profit_net,
        "verified": False,
        "verify_source": None,
        "verify_amount": None,
        "meta": meta or {},
        "proof_hash": _hash("claim", venture, connection_id, item, price_sell),
    }
    return _append(rec)


def verify(connection_id, verify_amount, verify_source, evidence=None):
    """Стадия 2: деньги прочитаны из реального источника. Ставит verified=true — только при доказательстве.

    Возвращает (rec, error). error != None ⟺ верификация ОТКЛОНЕНА (консервативно, закон LG2):
      - нет claim с этим connection_id  → нет числа без события (LG1)
      - verify_source пустой            → нечем подтвердить
      - verify_amount <= 0              → деньги не пришли
    """
    claims = [r for r in _read() if r.get("connection_id") == connection_id and r.get("stage") == "claim"]
    if not claims:
        return None, f"REFUSED: нет claim для connection_id={connection_id} (LG1 нет числа без события)"
    if not verify_source:
        return None, "REFUSED: пустой verify_source (нечем подтвердить поступление)"
    try:
        amt = float(verify_amount)
    except Exception:
        amt = 0.0
    if amt <= 0:
        return None, "REFUSED: verify_amount <= 0 (деньги не пришли → не verified, LG2)"

    claim = claims[-1]
    rec = {
        "ts": _now(),
        "organ": "MINT",
        "stage": "verified",
        "venture": claim.get("venture"),
        "connection_id": connection_id,
        "item": claim.get("item"),
        "cost_buy": claim.get("cost_buy"),
        "price_sell": claim.get("price_sell"),
        "fee": claim.get("fee"),
        "profit_net": claim.get("profit_net"),
        "verified": True,
        "verify_source": verify_source,
        "verify_amount": round(amt, 2),
        "evidence": evidence or {},
        "proof_hash": _hash("verified", connection_id, verify_source, amt),
    }
    return _append(rec), None


def _verified_connection_ids():
    return {r["connection_id"] for r in _read() if r.get("stage") == "verified" and r.get("verified")}


def summary_by_venture():
    """Сводка по вселенным: заявлено vs проверено ₽, стоимость, ROI. ROI считает ТОЛЬКО verified."""
    rows = _read()
    verified_ids = _verified_connection_ids()
    by = {}
    for r in rows:
        v = r.get("venture", "?")
        b = by.setdefault(v, {
            "venture": v, "claims": 0, "verified_tx": 0,
            "claimed_profit": 0.0, "verified_profit": 0.0, "cost": 0.0,
        })
        if r.get("stage") == "claim":
            b["claims"] += 1
            b["claimed_profit"] = round(b["claimed_profit"] + float(r.get("profit_net") or 0), 2)
            b["cost"] = round(b["cost"] + float(r.get("cost_buy") or 0) + float(r.get("fee") or 0), 2)
        elif r.get("stage") == "verified" and r.get("verified"):
            b["verified_tx"] += 1
            b["verified_profit"] = round(b["verified_profit"] + float(r.get("profit_net") or 0), 2)
    for b in by.values():
        b["roi"] = round(b["verified_profit"] / b["cost"], 3) if b["cost"] > 0 else None
    return by


def ranking():
    """Соревнование вселенных (MINT §5): сортировка по f_D = verified_profit / cost (desc)."""
    rows = list(summary_by_venture().values())
    rows.sort(key=lambda b: (b["roi"] if b["roi"] is not None else -1, b["verified_profit"]), reverse=True)
    return rows


def verdict():
    """Честность ledger PASS/FAIL: каждая verified-запись имеет источник+сумму и ведёт к существующему claim."""
    rows = _read()
    claim_ids = {r["connection_id"] for r in rows if r.get("stage") == "claim"}
    bad = []
    for r in rows:
        if r.get("stage") == "verified":
            if not r.get("verify_source") or not (float(r.get("verify_amount") or 0) > 0):
                bad.append({"connection_id": r.get("connection_id"), "why": "verified без источника/суммы"})
            elif r.get("connection_id") not in claim_ids:
                bad.append({"connection_id": r.get("connection_id"), "why": "verified без claim (нет события)"})
    total_verified = sum(
        float(r.get("profit_net") or 0) for r in rows if r.get("stage") == "verified" and r.get("verified")
    )
    return {
        "status": "PASS" if not bad else "FAIL",
        "records": len(rows),
        "verified_violations": bad,
        "verified_profit_total": round(total_verified, 2),
    }


if __name__ == "__main__":
    import sys
    if "--summary" in sys.argv:
        print(json.dumps(summary_by_venture(), ensure_ascii=False, indent=2))
    elif "--rank" in sys.argv:
        print(json.dumps(ranking(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(verdict(), ensure_ascii=False, indent=2))

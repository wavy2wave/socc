#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT Venture D2 — лидген услуг (тонкий стаб второй вселенной).

Связка честная: ловим РЕАЛЬНЫЙ спрос на услугу (Avito-услуги/Profi.ru/YouDo) → сводим с РЕАЛЬНЫМ мастером
(партнёр оператора) → берём комиссию. Транзакция = поступившая комиссия (verified при подтверждении).

ВАЖНО (WARDEN-границы, помечено явно):
  • Avito не даёт открытого API под произвольный парсинг — захват лида здесь это РУЧНОЙ ввод оператором
    или официальная лид-форма. Массовый парсинг в обход ToS = RL4, режется WARDEN. Это стаб, не парсер.
  • Мастер — реальный человек, который реально оказывает услугу. Никаких фейк-личностей (RL3).

Стаб демонстрирует ту же дисциплину, что и Ozon-вселенная: WARDEN-гейт → claim → verified. Полный
парсинг/интеграции — следующий инкремент по «огню» оператора. Чистый stdlib.
"""
import os
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import socc_revenue_ledger_v1 as ledger   # noqa: E402
import socc_mint_warden_v1 as warden       # noqa: E402

DRY_LEDGER = "/tmp/mint_dry_ledger.jsonl"

# Domain D2 — вторая вселенная.
D2_LEADGEN = {"id": "service-leadgen-RU", "market": "Avito/Profi/YouDo",
              "legal_form": "агентский", "commission_rate": 0.15}


def _cid(lead):
    base = f"{D2_LEADGEN['id']}|{lead.get('service')}|{datetime.now(timezone.utc).isoformat()}"
    return D2_LEADGEN["id"] + "-" + hashlib.sha256(base.encode()).hexdigest()[:10]


def capture_lead(service, ticket_value, master, source="manual", mode="dry"):
    """Завести связку лидгена. master — РЕАЛЬНЫЙ исполнитель (имя/контакт партнёра оператора).

    Возвращает {connection_id, status, warden, claim, detail}.
    """
    if mode == "dry":
        ledger.LEDGER = Path(DRY_LEDGER)

    connection_id = _cid({"service": service})
    commission = round(float(ticket_value) * D2_LEADGEN["commission_rate"], 2)

    descriptor = {
        "venture": D2_LEADGEN["id"],
        "legal_form": D2_LEADGEN["legal_form"],
        "description": f"свод реального спроса на «{service}» с реальным мастером {master}, комиссия с оказанной услуги",
        "mechanism": "честное посредничество, услугу оказывает реальный человек",
        "tags": ["leadgen", "services", source],
        # реальный мастер, не фейк; не трогаем чужие средства; не перепродаём доступ:
        "impersonates_real_person": False,
        "handles_third_party_funds": False,
        "resells_platform_access": False,
        "deceives_customer": False,
    }
    w = warden.gate(descriptor)
    if w["status"] != "PASS":
        return {"connection_id": connection_id, "status": "FAIL", "warden": w,
                "detail": "WARDEN отрезал связку до claim: " + "; ".join(w["reasons"])}

    claim = ledger.record_claim(
        venture=D2_LEADGEN["id"], connection_id=connection_id,
        item=f"{service} → {master}",
        cost_buy=0, price_sell=commission, fee=0,
        meta={"mode": mode, "service": service, "master": master, "ticket_value": float(ticket_value),
              "source": source, "note": "комиссия verified только при поступлении (оператор/банк)"})
    return {"connection_id": connection_id, "status": "CLAIMED", "warden": w, "claim": claim,
            "detail": f"claim на комиссию {commission} ₽ заведён (verified=false до поступления)"}


def confirm_commission(connection_id, amount, source="operator_bank_confirm", evidence=None, mode="dry"):
    """t4 для лидгена: комиссия реально поступила (подтверждение оператора/банка). verified=true."""
    if mode == "dry":
        ledger.LEDGER = Path(DRY_LEDGER)
    return ledger.verify(connection_id, amount, source, evidence=evidence or {"mode": mode})


if __name__ == "__main__":
    import json
    mode = "real" if "--real" in sys.argv else "dry"
    if mode == "dry":
        ledger.LEDGER = Path(DRY_LEDGER)
    # dry-демо: реальный мастер «Иван (партнёр)», услуга «сборка мебели», чек 4000 ₽
    r = capture_lead("сборка мебели", ticket_value=4000, master="Иван (партнёр)", mode="dry")
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if r["status"] == "CLAIMED":
        v, err = confirm_commission(r["connection_id"], amount=600,
                                    source="dry_run_sim", evidence={"note": "симуляция поступления комиссии"}, mode="dry")
        print(json.dumps({"verify_error": err, "verified": bool(v)}, ensure_ascii=False, indent=2))

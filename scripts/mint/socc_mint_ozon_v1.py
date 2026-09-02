#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT Ozon client V1 — руки MERCHANT на Ozon Seller API (bounded, без демона).

Рефактор projects/tamaguru-core/marketplace-os/agents/ozon-bridge/bridge.py:
  • было: while True: fetch(); sleep(900)   — фоновой демон (запрещён законом SOCC Λ₀ no_daemon)
  • стало: fetch_new_orders()               — один ограниченный вызов на тик оператора

Добавлено для t4 verify_money: fetch_posting_payout(posting_number) — читает Ozon Finance, возвращает
сумму, реально начисленную продавцу по отправлению (то самое «деньги легли», что верифицирует LEDGER).

requests импортируется ЛЕНИВО: модуль грузится без сети/ключей (dry-run на чистом stdlib).
Ключи — из env OZON_CLIENT_ID / OZON_API_KEY (как в исходном bridge.py).

ФАЗА A: ключи подтягиваются из gitignored .env через общий socc_mint_env_v1 (та же дыра, что
чинили у рук Яндекса: раньше читали только os.getenv → при живых ключах в .env врали «ключей нет»).
"""
import os

API = "https://api-seller.ozon.ru"

_ENV_TRIED = False


def _ensure_env():
    """Один раз подтянуть gitignored .env через общий загрузчик. Fail-soft: без него dry-run живёт."""
    global _ENV_TRIED
    if _ENV_TRIED:
        return
    _ENV_TRIED = True
    try:
        import socc_mint_env_v1 as env
    except Exception:
        try:
            import sys
            from pathlib import Path
            mint = str(Path(__file__).resolve().parent)   # SOCC/scripts/mint
            if mint not in sys.path:
                sys.path.insert(0, mint)
            import socc_mint_env_v1 as env
        except Exception:
            return
    try:
        env.ensure_env()
    except Exception:
        pass


def creds_present():
    _ensure_env()
    return bool(os.getenv("OZON_CLIENT_ID") and os.getenv("OZON_API_KEY"))


def _headers():
    _ensure_env()
    cid, key = os.getenv("OZON_CLIENT_ID"), os.getenv("OZON_API_KEY")
    if not (cid and key):
        raise RuntimeError("OZON_CLIENT_ID / OZON_API_KEY не заданы — реальный режим недоступен (нужны ключи кабинета)")
    return {"Client-Id": cid, "Api-Key": key, "Content-Type": "application/json"}


def _post(path, body, timeout=30):
    try:
        import requests  # ленивый импорт: dry-run работает без него
    except Exception as e:
        raise RuntimeError(f"requests не установлен ({e}); реальный режим Ozon недоступен, используй mode=dry")
    r = requests.post(API + path, headers=_headers(), json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_new_orders(since_days=1, limit=50, status="awaiting_packaging"):
    """Один ограниченный запрос новых FBS-заказов (наследует bridge.py::fetch, но без while/sleep)."""
    from datetime import datetime, timedelta
    since = (datetime.utcnow() - timedelta(days=since_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {"dir": "ASC", "limit": int(limit), "offset": 0,
            "with": {"analytics_data": True, "barcodes": True},
            "filter": {"since": since, "to": to, "status": status}}
    data = _post("/v3/posting/fbs/list", body)
    return data.get("result", {}).get("postings", [])


def fetch_posting_payout(posting_number, since_days=90):
    """t4 verify_money: сумма, реально начисленная продавцу по отправлению (Ozon Finance).

    Возвращает (amount, evidence) или (None, why). amount > 0 ⟺ деньги действительно начислены.
    Это детерминированное чтение реального источника — НЕ оценка, НЕ LLM.
    """
    from datetime import datetime, timedelta
    frm = (datetime.utcnow() - timedelta(days=since_days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    to = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    body = {"filter": {"date": {"from": frm, "to": to},
                       "posting_number": posting_number,
                       "transaction_type": "all"},
            "page": 1, "page_size": 1000}
    data = _post("/v3/finance/transaction/list", body)
    ops = data.get("result", {}).get("operations", [])
    if not ops:
        return None, f"Ozon Finance: операций по {posting_number} нет (деньги ещё не начислены)"
    amount = round(sum(float(o.get("amount") or 0) for o in ops), 2)
    if amount <= 0:
        return None, f"Ozon Finance: суммарное начисление по {posting_number} ≤ 0 (нетто не в плюсе)"
    return amount, {"source": "ozon_finance_transaction_list", "posting_number": posting_number,
                    "operations": len(ops), "amount": amount}


if __name__ == "__main__":
    import json
    print(json.dumps({"creds_present": creds_present(),
                      "note": "реальные вызовы требуют OZON_CLIENT_ID/OZON_API_KEY и requests"},
                     ensure_ascii=False, indent=2))

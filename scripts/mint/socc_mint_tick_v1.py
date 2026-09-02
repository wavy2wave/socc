#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT bounded tick V1 — один ограниченный шаг органа на запуск оператора (зеркало
scripts/socc_autonomous_build_loop_v1.py). БЕЗ демона, БЕЗ авто-сети, БЕЗ фонового цикла.

Логика: observe (discover доказанные связки) → RUBICON-гейт → один шаг → STOP.
RUBICON (требует явного оператора, не авто): всё, что ДВИГАЕТ реальные деньги —
реальный приём заказа, отметка отгрузки, верификация поступления. По умолчанию tick только НАБЛЮДАЕТ.

  python3 socc_mint_tick_v1.py                 # dry observe: показать доказанные связки (ничего не двигает)
  python3 socc_mint_tick_v1.py --dry-cycle      # прогнать ОДНУ связку через полный цикл в песочнице
  python3 socc_mint_tick_v1.py --go --real ...  # RUBICON: реальный шаг — только с ключами и оператором

Тик-леджер: MEMORY_WAVE/reports/mint/tick_ledger.jsonl (append-only).
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import socc_mint_prospect_v1 as prospect   # noqa: E402
import socc_mint_cycle_v1 as cycle          # noqa: E402
import socc_mint_ozon_v1 as ozon            # noqa: E402

TICK_LEDGER = ROOT / "MEMORY_WAVE/reports/mint/tick_ledger.jsonl"
RUBICON = {"real_order_intake", "real_fulfill", "real_verify_money"}  # не авто-запускается по дизайну


def _now():
    return datetime.now(timezone.utc).isoformat()


def _candidates():
    csv_path = os.environ.get("MINT_CANDIDATES_CSV")
    if csv_path:
        rows = prospect.load_candidates_from_csv(csv_path)
        return rows if rows else prospect.SAMPLE
    return prospect.SAMPLE


def observe():
    """Discover: доказанные связки из источника кандидатов. Ничего не двигает (чистое наблюдение)."""
    proven = prospect.prospect(_candidates(), profit_target=cycle.D1_OZON["profit_target"],
                               min_profit=cycle.D1_OZON["min_profit"])
    return proven


def _record(rec):
    TICK_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(TICK_LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def main():
    go = "--go" in sys.argv
    real = "--real" in sys.argv
    dry_cycle = "--dry-cycle" in sys.argv

    proven = observe()
    rec = {"ts": _now(), "organ": "MINT", "step": "observe", "proven_connections": len(proven),
           "daemon_running": False, "network_used": False, "moved_money": False}

    if real and go:
        # RUBICON: реальный шаг разрешён только при ключах И явном операторе. Иначе fail-closed.
        if not ozon.creds_present():
            rec.update({"step": "real_blocked", "reason": "нет OZON_CLIENT_ID/OZON_API_KEY — RUBICON закрыт"})
            _record(rec); print(json.dumps(rec, ensure_ascii=False, indent=2)); return
        rec.update({"step": "real_armed",
                    "reason": "RUBICON: реальное движение денег требует пошаговой команды оператора "
                              "(посмотри socc_mint_cycle_v1.run_connection(..., mode='real', fulfilled=True))"})
        _record(rec); print(json.dumps(rec, ensure_ascii=False, indent=2)); return

    if dry_cycle and proven:
        top = proven[0]["item"]
        res = cycle.run_connection(cycle.D1_OZON, top, mode="dry")
        rec.update({"step": "dry_cycle", "top_item": top.get("name"),
                    "connection_id": res["connection_id"], "cycle_status": res["status"]})
    else:
        rec.update({"step": "observe_only",
                    "top": [{"name": p["item"]["name"], "netto": p["margin"]["profit_net"],
                             "score": p["rank_score"]} for p in proven[:5]]})

    _record(rec)
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    print("\nСвязок доказано:", len(proven), "· RUBICON (движение денег) — только по явной команде оператора.")


if __name__ == "__main__":
    main()

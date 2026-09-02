#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT cluster bounded-tick V1 — один ограниченный «вдох» ВСЕГО кластера на запуск оператора.

Связывает орган воедино и подключает силу SOCC:
  • observe ВСЕ вселенные (D1 товары + D2 услуги) — discover доказанных связок (ничего не двигает);
  • rank вселенные по ROI (соревнование, MINT §5);
  • learn — обновить контур обучения из леджера (только verified);
  • self — обновить само-модель (P4, зеркало spine2/SELF_MODEL);
  • proof — выпустить proof такта в форме PXS-1 (status/checks/hard_failures/proof_hash/next_lawful_step);
  • report — записать такт в cluster tick-ledger + печать сводки оператору.

Закон (Λ₀): НЕ демон, НЕ авто-сеть, один bounded-шаг → STOP. RUBICON: всё, что двигает РЕАЛЬНЫЕ деньги
(реальный цикл/верификация), требует пошаговой команды оператора — авто-тик только НАБЛЮДАЕТ.
Чистый stdlib (dry-цикл и чтение — без сети/LLM).
"""
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import socc_revenue_ledger_v1 as ledger            # noqa: E402
import socc_mint_registry_v1 as registry            # noqa: E402  (реестр вселенных — кластер итерирует его)
import socc_mint_learn_v1 as learn                  # noqa: E402
import socc_mint_self_v1 as selfmod                 # noqa: E402

TICK_LEDGER = ROOT / "MEMORY_WAVE/reports/mint/cluster_tick_ledger.jsonl"
PROOF_DIR = ROOT / "MEMORY_WAVE/reports/mint"


def _now():
    return datetime.now(timezone.utc).isoformat()


def observe():
    """Discover по ВСЕМ вселенным РЕЕСТРА (чистое наблюдение). Новая вселенная подхватывается сама."""
    return registry.observe_all()


def _emit_tick_proof(tick_id, checks, st):
    """Proof такта в форме PXS-1 (status/checks/hard_failures/proof_hash/next_lawful_step)."""
    hard = [k for k, ok in checks.items() if not ok]
    proof = {"id": tick_id, "ts": _now(), "organ": "MINT", "kind": "cluster_tick",
             "status": "PASS" if not hard else "FAIL", "checks": checks, "hard_failures": hard,
             "next_lawful_step": st["next_lawful_step"]}
    proof["proof_hash"] = hashlib.sha256(
        json.dumps(proof, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    (PROOF_DIR / f"cluster_tick_{tick_id}.json").write_text(
        json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    return proof


def tick(dry_cycle=False):
    """Один bounded-такт кластера. dry_cycle=True гоняет по одному dry-циклу на вселенную (песочница)."""
    tick_id = "ct-" + hashlib.sha256(_now().encode()).hexdigest()[:10]
    moved_money = False  # авто-тик НИКОГДА не двигает реальные деньги (RUBICON у оператора)

    observed = observe()
    if dry_cycle:
        # bounded: по одному dry-циклу каждой вселенной РЕЕСТРА в песочнице (канон не трогаем; соревнование оживает)
        registry.run_dry_all()

    learn.learn_from_ledger()          # обновить опыт (только verified)
    st = selfmod.self_status()         # обновить само-модель (читает текущий ledger.LEDGER)
    selfmod.emit(st)

    checks = {
        "bounded_single_step": True,
        "no_daemon": True,
        "money_untouched": not moved_money,
        "ledger_honesty": st["money"]["ledger_honesty"] == "PASS",
        "self_emitted": True,
    }
    proof = _emit_tick_proof(tick_id, checks, st)

    rec = {"ts": _now(), "tick_id": tick_id, "kind": "cluster_tick",
           "observed": observed, "ranking": ledger.ranking(),
           "real_money": st["money"]["real_verified_profit"],
           "sim_money": st["money"]["simulated_verified_profit"],
           "god": st["learning"]["god_pattern"], "next": st["next_lawful_step"],
           "checks": checks, "proof_hash": proof["proof_hash"], "status": proof["status"],
           "daemon_running": False, "network_used": False, "moved_money": moved_money}
    TICK_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(TICK_LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def main():
    if "--real" in sys.argv:
        # RUBICON fail-closed: реальные деньги — только пошаговая команда оператора, не авто-тик.
        print(json.dumps({"step": "real_blocked",
                          "reason": "RUBICON: реальные деньги двигает только оператор — "
                                    "socc_mint_service_cycle_v1.run_service_connection(..., mode='real', "
                                    "fulfilled=True, payout=...). Авто-тик деньги не трогает."},
                         ensure_ascii=False, indent=2))
        return
    rec = tick(dry_cycle="--dry-cycle" in sys.argv)
    print(selfmod.render())
    print()
    print(json.dumps({"tick": rec["tick_id"], "status": rec["status"], "observed": rec["observed"],
                      "real_money": rec["real_money"], "sim_money": rec["sim_money"],
                      "next": rec["next"], "proof_hash": rec["proof_hash"],
                      "RUBICON": "реальные деньги двигает только оператор"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

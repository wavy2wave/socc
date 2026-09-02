#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT self-model V1 — само-осознание кластера (зеркало spine2/SELF_MODEL для финансового органа).

Орган понимает себя: для чего создан, мандат, ответственность, законы (и чем каждый ПРИНУЖДАЕТСЯ),
вселенные и их соревнование по ROI, выученный паттерн-«бог», следующий законный шаг, граница честности.

Главный закон само-модели (как у всего органа): НЕТ ЧИСЛА БЕЗ СОБЫТИЯ. Каждый ₽ в self_status ведёт к
verified-записи в revenue_ledger. И отдельно — орган НЕ обманывает сам себя: verified из песочницы
(`verify_source=="dry_run_sim"`) считается ДОКАЗАННЫМ-В-СИМУЛЯЦИИ, а не реальными деньгами. Реальные ₽ —
только из реального источника (банк/СБП/чек НПД/Ozon payout). Пока реальных 0 — само-модель честно об этом
говорит, как бы хорошо ни выглядела песочница.

Deterministic, без сети, без LLM. Источник правды — ledger.LEDGER (канон или песочница через MINT_LEDGER_PATH).
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import socc_revenue_ledger_v1 as ledger  # noqa: E402
import socc_mint_learn_v1 as learn        # noqa: E402

SELF_PATH = ROOT / "MEMORY_WAVE/reports/mint/self_status.json"
SIM_SOURCE = "dry_run_sim"  # метка симуляции: verified в песочнице, НЕ реальные деньги

# Charter органа — кто он, зачем, по каким законам. Каждый закон мапится на РЕАЛЬНУЮ точку принуждения
# (иначе это декорация — SM-T2 это фальсифицирует).
CHARTER = {
    "id": "MINT",
    "kind": "финансовый орган SOCC — кластер вселенных-venture",
    "mandate": "держать систему в плюсе через ДОКАЗАННЫЕ транзакции; находить, замыкать и тиражировать связки",
    "is_not": ["бот", "демон/24-7", "генератор дохода из воздуха", "АГИ без proof"],
    "responsibilities": [  # Σ — грамматика органа
        "register_venture(D)", "prospect(D)", "run_connection(D)", "verify_transaction(claim)",
        "rank_ventures()", "learn_from_ledger()", "report(operator)",
    ],
    "laws": [  # code → text → чем ПРИНУЖДАЕТСЯ (проверяемая ссылка на функцию-страж)
        {"code": "MN1", "text": "нет дохода без события поступления",
         "enforced_by": "ledger.verify: amount>0 ∧ verify_source ∧ существует claim"},
        {"code": "MN2", "text": "транзакция на легальную сущность создателя",
         "enforced_by": "warden.gate: MN2_legal_entity"},
        {"code": "MN3", "text": "закон выше прибыли",
         "enforced_by": "warden.gate: fail-closed при любой красной линии"},
        {"code": "RL1", "text": "нет денежных мулов/дропов",
         "enforced_by": "warden: RL1 денойлист + _mule_structure (приём чужого + пересылка)"},
        {"code": "RL2", "text": "нет перепродажи доступа в обход ToS",
         "enforced_by": "warden: RL2"},
        {"code": "RL3", "text": "нет фейк-личности живого человека",
         "enforced_by": "warden: RL3"},
        {"code": "RL4", "text": "серое ≤ легальное (без обмана покупателя/площадки)",
         "enforced_by": "warden: RL4"},
    ],
    "success_metric": "суммарный РЕАЛЬНЫЙ verified ₽ / стоимость; вселенные соревнуются по ROI (f_D)",
    "cadence": "bounded-tick (без демона); реальные деньги двигает только оператор (RUBICON)",
    "honesty_boundary": [
        "не двигает чужие/реальные средства автономно (RUBICON)",
        "verified=true только из реального источника",
        "dry-run в канон не пишет; симуляция не считается реальными деньгами",
    ],
    "hierarchy": {
        "вселенная (venture/Domain D)": "тема со своим спросом/площадкой/правилами; соревнуется по ROI",
        "связка": "клетка — proof-gated цикл t0..t6 с доказанным концом (verified)",
        "«бог»": "паттерн-связки, промотированный в геном после k подтверждённых verified (φ_promote)",
        "«полубог»": "способность родить ЛЕГАЛЬНУЮ собственную интернет-личность бренда (не подделка человека)",
    },
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _god_pattern(model):
    """«Бог» = сигнатура с наибольшим числом РЕАЛЬНЫХ verified и множителем (промотированный паттерн)."""
    sigs = [s for s in model["signatures"].values() if s["n_verified"] > 0]
    if not sigs:
        return None
    best = max(sigs, key=lambda s: (s["n_verified"], s["multiplier"]))
    return {"signature": best["signature"], "verified": best["n_verified"],
            "conversion": best["conversion"], "multiplier": best["multiplier"],
            "verified_profit_avg": best["verified_profit_avg"]}


def self_status():
    """Собрать само-модель кластера из леджера (источник правды). Каждое число ведёт к событию."""
    rows = ledger._read()
    verified = [r for r in rows if r.get("stage") == "verified" and r.get("verified")]
    real = [r for r in verified if r.get("verify_source") != SIM_SOURCE]
    sim = [r for r in verified if r.get("verify_source") == SIM_SOURCE]
    real_profit = round(sum(float(r.get("profit_net") or 0) for r in real), 2)
    sim_profit = round(sum(float(r.get("profit_net") or 0) for r in sim), 2)

    verdict = ledger.verdict()
    ranking = ledger.ranking()
    model = learn.learn_from_ledger()
    god = _god_pattern(model)

    # Следующий законный шаг — честно, от реального состояния (не от красивой песочницы).
    if verdict["status"] != "PASS":
        nxt = "почини честность леджера: есть verified без события/claim"
    elif len(real) == 0:
        nxt = ("ПЕРВЫЙ реальный verified ₽: провести связку D2 (услуги) до чека НПД/поступления — RUBICON "
               "оператора (даже если песочница уже зелёная, реальных денег пока 0)")
    elif len({r.get("venture") for r in real}) < 2:
        nxt = "поднять вторую вселенную до РЕАЛЬНОГО verified — включить соревнование на реальных деньгах"
    else:
        nxt = "тиражировать выигравший паттерн-«бог» в новую вселенную: Π(roster, D')"

    return {
        "ts": _now(),
        "organ": CHARTER["id"],
        "charter": CHARTER,
        "universes": [{"venture": b["venture"], "verified_tx": b["verified_tx"],
                       "verified_profit": b["verified_profit"], "roi": b["roi"]} for b in ranking],
        "money": {
            "real_verified_tx": len(real), "real_verified_profit": real_profit,
            "simulated_verified_tx": len(sim), "simulated_verified_profit": sim_profit,
            "ledger_honesty": verdict["status"],
        },
        "learning": {"status": model["status"], "god_pattern": god},
        "next_lawful_step": nxt,
        "self_note": ("каждый ₽ ведёт к verified-событию в revenue_ledger; реальные деньги ≠ симуляция; "
                      "нет события — нет числа"),
    }


def emit(status=None):
    """Записать само-модель на диск (для дашборда/спайна). Возвращает записанный объект."""
    st = status or self_status()
    SELF_PATH.parent.mkdir(parents=True, exist_ok=True)
    SELF_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    return st


def render(st=None):
    st = st or self_status()
    m = st["money"]
    lines = [
        f"🏦 {st['organ']} — {st['charter']['kind']}",
        f"мандат: {st['charter']['mandate']}",
        f"РЕАЛЬНЫЕ деньги: {m['real_verified_profit']:.0f} ₽ ({m['real_verified_tx']} tx) · "
        f"симуляция (песочница): {m['simulated_verified_profit']:.0f} ₽ ({m['simulated_verified_tx']} tx) · "
        f"честность леджера: {m['ledger_honesty']}",
        "вселенные (ранг по ROI):",
    ]
    for u in st["universes"]:
        roi = "—" if u["roi"] is None else f"{u['roi']:.3f}"
        lines.append(f"  • {u['venture']}: verified {u['verified_tx']} · {u['verified_profit']:.0f} ₽ · ROI {roi}")
    god = st["learning"]["god_pattern"]
    lines.append(f"паттерн-«бог»: {god['signature'] if god else 'пока нет (нужны реальные verified)'}")
    lines.append(f"следующий законный шаг: {st['next_lawful_step']}")
    return "\n".join(lines)


if __name__ == "__main__":
    if "--emit" in sys.argv:
        emit()
    print(render())

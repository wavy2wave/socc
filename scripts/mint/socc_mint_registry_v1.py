#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT universe registry V1 — реестр вселенных кластера (это и есть «кластер рождает вселенные»).

Каждая вселенная регистрирует себя: id + observe() (счёт доказанных связок) + dry() (один dry-цикл).
Кластер-тик итерирует РЕЕСТР, а не хардкод — поэтому новая тема = `register(...)` и она сама встаёт в
наблюдение и соревнование, БЕЗ правок кластера. Это машинная форма Π(roster, D') (MINT-SPEC §1).

Чистый stdlib. Никакой сети/LLM — только сведение вселенных в один список.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import socc_mint_prospect_v1 as prospect            # noqa: E402
import socc_mint_cycle_v1 as cycle                  # noqa: E402
import socc_mint_service_cycle_v1 as service_cycle  # noqa: E402
import socc_mint_resale_v1 as resale                # noqa: E402


# --- observe/dry каждой вселенной (тонкие адаптеры к её модулю) ---
def _d1_observe():
    return len(prospect.prospect(prospect.SAMPLE, kind="goods",
                                 profit_target=cycle.D1_OZON["profit_target"], min_profit=cycle.D1_OZON["min_profit"]))


def _d1_dry():
    cycle.run_connection(cycle.D1_OZON, dict(prospect.SAMPLE[0]), mode="dry")


def _d2_observe():
    return len(prospect.prospect([dict(service_cycle.SAMPLE_LEAD)], kind="service",
                                 profit_target=service_cycle.D2_SERVICE["profit_target"],
                                 min_profit=service_cycle.D2_SERVICE["min_profit"]))


def _d2_dry():
    service_cycle.run_service_connection(service_cycle.D2_SERVICE, dict(service_cycle.SAMPLE_LEAD), mode="dry")


def _d3_observe():
    t = resale.resale_falsifiable_test(dict(resale.SAMPLE_LOT))
    return 1 if (t["passed"] and t["margin"]["profit_net"] >= resale.D3_RESALE["min_profit"]) else 0


def _d3_dry():
    resale.run_resale_connection(dict(resale.SAMPLE_LOT), mode="dry")


# Реестр вселенных. Добавить D4+ = один register(...) (или строка тут) — кластер подхватит сам.
REGISTRY = [
    {"id": "ozon-dropship-RU", "observe": _d1_observe, "dry": _d1_dry},
    {"id": "service-leadgen-RU", "observe": _d2_observe, "dry": _d2_dry},
    {"id": "resale-avito-RU", "observe": _d3_observe, "dry": _d3_dry},
]


def register(uid, observe, dry):
    """Зарегистрировать новую вселенную. observe()→int (доказанных связок), dry()→None (один dry-цикл)."""
    REGISTRY.append({"id": uid, "observe": observe, "dry": dry})
    return REGISTRY


def universe_ids():
    return [u["id"] for u in REGISTRY]


def observe_all():
    """Discover по ВСЕМ вселенным реестра → {id: счёт доказанных связок}. Ничего не двигает."""
    return {u["id"]: int(u["observe"]()) for u in REGISTRY}


def run_dry_all():
    """Один dry-цикл по каждой вселенной (песочница) — оживляет соревнование всех вселенных разом."""
    for u in REGISTRY:
        u["dry"]()


if __name__ == "__main__":
    import json
    print(json.dumps({"universes": universe_ids(), "observed": observe_all()}, ensure_ascii=False, indent=2))

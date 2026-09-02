#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON SELF V1 — само-осознание ОЗОН-МЕНЕДЖЕРА (зеркало ymarket_self / MINT self-model).

Менеджер понимает СЕБЯ: кто он, зачем создан, по каким законам, и главное — в каком он СЕЙЧАС
состоянии и какой следующий ЗАКОННЫЙ шаг. Источник правды — ПАМЯТЬ (ozon_state): карточки, их
жизненный этап, цвет индекса, дневные нормы. Каждое число ведёт к реальному наблюдению (READ
витрины), не к фантазии.

Главный закон само-модели: НЕТ ЧИСЛА БЕЗ СОБЫТИЯ. «Карточка на витрине» — только если независимый
READ показал модерацию OK И visible И stock>0 (200≠успех). Пока доказанных публикаций 0 — self
честно об этом говорит, как бы хорошо ни выглядела сухая готовность.

Лестница решений — единый мозг с ozon_manager.decide (§7 плана):
  cards_errored>0 → ПОЧИНИТЬ · need_mapping>0 → ПРИВЯЗАТЬ КАТЕГОРИЮ · tracked==0 → НАБЛЮДЕНИЕ ·
  ready>0 & on_shelf_verified==0 → ПЕРВАЯ ПУБЛИКАЦИЯ (RUBICON) · index_red>0 → ЧИНИТЬ ИНДЕКС · иначе ДЕРЖАТЬ.

ЗАКОН (SOCC): deterministic, без сети, без LLM, без денег. Источник — ozon_state.load()
(канон или песочница через env OZON_STATE_PATH).
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
for p in (str(HERE), str(HERE.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ozon_state_v1 as state    # noqa: E402
import ozon_econ_v1 as econ      # noqa: E402  (цвета индекса — для честной формулировки шага)

ROOT = HERE.parent.parent.parent
SELF_PATH = ROOT / "MEMORY_WAVE/reports/mint/arbiter/ozon_self_status.json"

# Charter менеджера — кто он, зачем, по каким законам. Каждый закон мапится на РЕАЛЬНУЮ точку
# принуждения в коде (иначе декорация — приёмка это фальсифицирует).
CHARTER = {
    "id": "OZON_MANAGER",
    "kind": "живой менеджер магазина Ozon (орган оси ARBITER; паутина узлов, не конвейер)",
    "mandate": ("вести магазин Ozon к успеху «как швейцарские часы»: карточки полностью заполнены и "
                "на витрине, зелёный индекс, быстрая отгрузка; контролировать доход и его РОСТ"),
    "is_not": ["бот-однокнопка", "демон/24-7", "автопубликатор без отмашки",
               "генератор ранга из воздуха"],
    "responsibilities": [   # Σ — грамматика менеджера (ходы)
        "observe(state)", "decide(<=1 action)", "fix_errors", "fix_index", "publish_ready",
        "resolve_mapping(operator)", "keep_norms", "emit_self", "prove_tick", "report(operator)",
    ],
    "laws": [   # code → text → чем ПРИНУЖДАЕТСЯ (проверяемая ссылка на функцию-страж)
        {"code": "OZ1", "text": "ни одна карточка не остаётся с ошибкой (цель #errored → 0); "
                                "200≠успех — читаем errors[], а не HTTP-код",
         "enforced_by": "decide: FIX_ERRORS выше всего; state.kpis.cards_errored из реального READ"},
        {"code": "OZ2", "text": "категорию/обязательные атрибуты не выдумываем — need_mapping не летит",
         "enforced_by": "card без category_id/attrs → write ok=False; decide→RESOLVE_MAPPING"},
        {"code": "OZ3", "text": "карточка DONE только на витрине (модерация OK И visible И stock>0)",
         "enforced_by": "state.advance_lifecycle→ON_SHELF лишь при полном соответствии §4"},
        {"code": "OZ4", "text": "публикация доказана независимым READ витрины (не ответом на запись)",
         "enforced_by": "proof.verify_publish real-source-only; published_verified в state"},
        {"code": "OZ5", "text": "красный/жёлтый индекс = карточку прячут → чинить цену или снять",
         "enforced_by": "decide: index_red>0 → FIX_INDEX; econ.is_hidden_by_index"},
        {"code": "OZ6", "text": "реальная запись/деньги только по отмашке (not dry AND commit); RUBICON",
         "enforced_by": "write двойной гейт; tick dry=True по умолчанию; proof.moved_money=False"},
    ],
    "success_metric": ("0 карточек с ошибкой ∧ индекс в зелёном ∧ доказанно на витрине больше ∧ "
                       "дневные нормы (залито/отгружено/доставлено) растут; при равном — вперёд "
                       "карточка с большей выгодой (econ.priority_weight)"),
    "cadence": "bounded-tick (внешний планировщик зовёт тик; между тиками помнит через state/shift)",
    "honesty_boundary": [
        "не публикует и не двигает деньги автономно (отмашка/RUBICON оператора)",
        "cards_on_shelf только после proof-gate (независимый READ), не по ответу на import",
        "сухая готовность ≠ живая карточка; 200 ≠ успех",
        "нет данных индекса → цвет None, не выдумываем зелёный",
    ],
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _next_lawful_step(k):
    """Следующий законный шаг — честно от реального состояния памяти. Совпадает с decide (единый мозг)."""
    if k["cards_errored"] > 0:
        return (f"ПОЧИНИТЬ ОШИБКИ: {k['cards_errored']} карточек с errors[] (закон OZ1 «#errored→0») — "
                f"{', '.join(k['errored_ids'][:5])}")
    if k["need_mapping"] > 0:
        return (f"ПРИВЯЗАТЬ КАТЕГОРИЮ: {k['need_mapping']} карточек ждут category_id + обязательные "
                f"атрибуты (глаза оператора; id не выдумываем — OZ2)")
    if k["tracked"] == 0:
        return ("НАБЛЮДЕНИЕ: памяти пусто — прогнать отбор/preflight по нише (dry, 0₽), взять "
                "карточки под наблюдение")
    if k["cards_on_shelf"] == 0 and k["ready_to_publish"] > 0:
        return (f"ПЕРВАЯ РЕАЛЬНАЯ ПУБЛИКАЦИЯ: {k['ready_to_publish']} карточек готовы — по отмашке "
                f"оператора (--commit) залить 1 и доказать независимым READ витрины (OZ4/OZ6, RUBICON)")
    if k["index_red"] > 0:
        return (f"ЧИНИТЬ ИНДЕКС: {k['index_red']} карточек в КРАСНОМ индексе — их прячут из органики "
                f"(OZ5); снизить цену в рамках пола маржи или снять — "
                f"{', '.join(k['index_red_ids'][:5])}")
    return "ДЕРЖАТЬ СТРОЙ: ошибок нет, индекс не красный — наблюдать, добирать заполненность и нормы дня"


def self_status(doc=None):
    """Собрать само-модель менеджера из памяти (state). Каждое число ведёт к наблюдению."""
    doc = doc if doc is not None else state.load()
    k = state.kpis(doc)
    return {
        "ts": _now(),
        "organ": CHARTER["id"],
        "charter": CHARTER,
        "kpis": {
            "cards_tracked": k["tracked"],
            "cards_on_shelf": k["cards_on_shelf"],       # доказанные (proof-gate)
            "cards_errored": k["cards_errored"],         # цель = 0 (OZ1)
            "errored_ids": k["errored_ids"],
            "need_mapping": k["need_mapping"],
            "ready_to_publish": k["ready_to_publish"],
            "index_red": k["index_red"],                 # красных индексов (де-факто невидимы, OZ5)
            "index_red_ids": k["index_red_ids"],
            "index_clean": k["index_red"] == 0,
        },
        "daily_today": k["daily_today"],                 # норма дня: залито/отгружено/доставлено
        "counters": k["counters"],
        "next_lawful_step": _next_lawful_step(k),
        "self_note": ("каждое число ведёт к реальному READ витрины; живая карточка ≠ сухая готовность; "
                      "публикация доказана только независимым READ (200≠успех)"),
    }


def emit(status=None):
    """Записать само-модель на диск (для дашборда/спайна). fail-soft. Возвращает объект."""
    st = status or self_status()
    try:
        SELF_PATH.parent.mkdir(parents=True, exist_ok=True)
        SELF_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        st["_file"] = str(SELF_PATH)
    except Exception as e:
        st["_file_error"] = str(e)
    return st


def render(st=None):
    st = st or self_status()
    k = st["kpis"]
    d = st.get("daily_today", {})
    lines = [
        f"🛰  {st['organ']} — {st['charter']['kind']}",
        f"мандат: {st['charter']['mandate']}",
        (f"карточек: ведём {k['cards_tracked']} · НА ВИТРИНЕ {k['cards_on_shelf']} · "
         f"С ОШИБКОЙ {k['cards_errored']} (цель 0) · ждут категорию {k['need_mapping']} · "
         f"готовы к заливу {k['ready_to_publish']}"),
        (f"индекс: красных {k['index_red']} (чисто: {k['index_clean']}) — "
         f"красный = карточку прячут из органики"),
        (f"норма дня: залито {d.get('uploaded', 0)} · отгружено {d.get('shipped', 0)} · "
         f"доставлено {d.get('delivered', 0)}"),
        f"следующий законный шаг: {st['next_lawful_step']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    if "--emit" in sys.argv:
        emit()
    if "--json" in sys.argv:
        print(json.dumps(self_status(), ensure_ascii=False, indent=2))
    else:
        print(render())

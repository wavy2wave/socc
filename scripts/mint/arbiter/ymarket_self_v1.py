#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET SELF V1 — само-осознание управляющего Яндекс.Маркетом (зеркало MINT self-model).

Управляющий понимает СЕБЯ: кто он, зачем создан, по каким законам, и главное — в каком он СЕЙЧАС
состоянии и какой следующий законный шаг. Как MINT-self читает revenue_ledger, этот self читает
ПАМЯТЬ управляющего (ymarket_state) — источник правды о карточках. Каждое число ведёт к реальному
наблюдению (preflight/track), не к фантазии.

Главный закон само-модели (как у MINT): НЕТ ЧИСЛА БЕЗ СОБЫТИЯ. «Карточек живо N» — только если track
реально прочитал их PUBLISHED. «Доказанно живо» (cards_live_verified) — только после proof-gate
(независимый READ витрины). Пока реальных публикаций 0 — self честно об этом говорит, как бы хорошо
ни выглядел dry-preflight.

ЗАКОН (SOCC): deterministic, без сети, без LLM, без денег. Источник — state.load() (канон или
песочница через env YM_STATE_PATH).
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_state_v1 as state    # noqa: E402
import ymarket_econ_v1 as econ      # noqa: E402

ROOT = HERE.parent.parent.parent
SELF_PATH = ROOT / "MEMORY_WAVE/reports/mint/arbiter/ymarket_self_status.json"

# Charter управляющего — кто он, зачем, по каким законам. Каждый закон мапится на РЕАЛЬНУЮ точку
# принуждения в коде органа (иначе это декорация — приёмка это фальсифицирует).
CHARTER = {
    "id": "ARBITER_YM_MANAGER",
    "kind": "живой управляющий витриной Яндекс.Маркета (орган оси ARBITER, веха M6)",
    "mandate": ("держать карточки БЕЗ ошибок и с максимальной заполненностью, чтобы карточки были "
                "конкурентны в выдаче; действовать быстро, точно, с выгодой (деньги — цель)"),
    "is_not": ["бот-однокнопка", "демон/24-7", "автопубликатор без отмашки",
               "генератор ТОПа из воздуха"],
    "responsibilities": [   # Σ — грамматика управляющего (что он умеет как ходы)
        "observe(state)", "decide(<=1 action)", "fix_errors", "raise_index", "publish_ready",
        "resolve_mapping(operator)", "emit_self", "prove_tick", "report(operator)",
    ],
    "laws": [   # code → text → чем ПРИНУЖДАЕТСЯ (проверяемая ссылка на функцию-страж)
        {"code": "YM1", "text": "ни одна карточка не остаётся с ошибкой (цель #errored → 0)",
         "enforced_by": "decide: приоритет FIX_ERRORS выше всего; kpis.cards_errored в self"},
        {"code": "YM2", "text": "marketCategoryId не выдумываем — need_mapping не летит",
         "enforced_by": "card.market_category_id=None → write.create_card ok=False; decide→RESOLVE_MAPPING"},
        {"code": "YM3", "text": "реальная запись только по отмашке (not dry AND commit)",
         "enforced_by": "write._dry двойной гейт; manager.tick dry=True по умолчанию"},
        {"code": "YM4", "text": "публикация доказана независимым READ витрины (200≠успех)",
         "enforced_by": "proof.verify_publish real-source-only; published_verified в state"},
        {"code": "YM5", "text": "без демона — жизнь из ограниченных тиков",
         "enforced_by": "tick() выходит за один проход; proof.no_daemon=True; anchor.daemon_running=False"},
        {"code": "YM6", "text": "деньги управляющий не двигает (RUBICON у оператора)",
         "enforced_by": "нет вызовов оплаты; proof.moved_money=False; anchor.no_money_moved"},
    ],
    "success_metric": ("0 карточек с ошибкой ∧ средний contentRating → зона ТОП ∧ доказанно живых "
                       "карточек больше; при равном — вперёд идёт карточка с большей выгодой (econ)"),
    "cadence": "bounded-tick (внешний планировщик зовёт тик; между тиками помнит через state)",
    "honesty_boundary": [
        "не публикует и не двигает деньги автономно (отмашка/RUBICON оператора)",
        "cards_live только из реального track; cards_live_verified только после proof-gate",
        "dry-preflight в канон побед не пишет; сухая готовность ≠ живая карточка",
        "рекомендации, что API не закрыть (видео/бренд), честно в can_not_fill, не выдумываем",
    ],
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _next_lawful_step(k):
    """Следующий законный шаг — честно, от реального состояния памяти (не от красивой сухой готовности).

    Лестница совпадает с политикой decide (единый мозг): сначала честность/ошибки, потом ТОП,
    потом залив, потом маппинг, потом идл. Это то, что управляющий СКАЖЕТ и СДЕЛАЕТ следующим.
    """
    if k["cards_errored"] > 0:
        return (f"ПОЧИНИТЬ ОШИБКИ: {k['cards_errored']} карточек с ошибкой (закон YM1 «#errored→0») — "
                f"{', '.join(k['errored_ids'][:5])}")
    if k["need_mapping"] > 0:
        return (f"ПОДТВЕРДИТЬ КАТЕГОРИЮ: {k['need_mapping']} карточек ждут marketCategoryId "
                f"(categories_tree + глаза оператора; id не выдумываем — YM2)")
    if k["tracked"] == 0:
        return ("НАБЛЮДЕНИЕ: памяти пусто — прогнать preflight по категории (dry, 0₽), взять "
                "карточки под наблюдение")
    if k["cards_live_verified"] == 0 and k["ready_to_publish"] > 0:
        return (f"ПЕРВАЯ РЕАЛЬНАЯ ПУБЛИКАЦИЯ: {k['ready_to_publish']} карточек готовы — по отмашке "
                f"оператора (--commit) залить 1 и доказать независимым READ витрины (YM3/YM4, RUBICON)")
    if k["avg_content_rating"] is not None and k["avg_content_rating"] < econ.TOP_RATING_THRESHOLD:
        return (f"ПОДНЯТЬ ИНДЕКС: средний contentRating {k['avg_content_rating']}% < цели "
                f"{econ.TOP_RATING_THRESHOLD:.0f}% — закрывать рекомендации по самой выгодной карточке")
    return "ДЕРЖАТЬ СТРОЙ: ошибок нет, индекс в зоне цели — наблюдать и добирать заполненность"


def self_status(doc=None):
    """Собрать само-модель управляющего из памяти (state). Каждое число ведёт к наблюдению."""
    doc = doc if doc is not None else state.load()
    k = state.kpis(doc)
    return {
        "ts": _now(),
        "organ": CHARTER["id"],
        "charter": CHARTER,
        "kpis": {
            "cards_tracked": k["tracked"],
            "cards_live": k["cards_live"],
            "cards_live_verified": k["cards_live_verified"],
            "cards_errored": k["cards_errored"],        # цель = 0 (YM1)
            "errored_ids": k["errored_ids"],
            "need_mapping": k["need_mapping"],
            "ready_to_publish": k["ready_to_publish"],
            "avg_content_rating": k["avg_content_rating"],
            "top_threshold": econ.TOP_RATING_THRESHOLD,
            "in_top_zone": (k["avg_content_rating"] is not None
                            and k["avg_content_rating"] >= econ.TOP_RATING_THRESHOLD),
        },
        "counters": k["counters"],
        "next_lawful_step": _next_lawful_step(k),
        "self_note": ("каждое число ведёт к реальному наблюдению (preflight/track); живая карточка ≠ "
                      "сухая готовность; публикация доказана только независимым READ витрины"),
    }


def emit(status=None):
    """Записать само-модель на диск (для дашборда/спайна). Возвращает записанный объект.

    Использует атомарную запись state.write_atomic-стиля через временный файл? Здесь достаточно
    простой записи (self_status — производный снимок, не источник правды). fail-soft.
    """
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
    avg = "—" if k["avg_content_rating"] is None else f"{k['avg_content_rating']}%"
    lines = [
        f"🛰  {st['organ']} — {st['charter']['kind']}",
        f"мандат: {st['charter']['mandate']}",
        (f"карточек: ведём {k['cards_tracked']} · живых {k['cards_live']} "
         f"(доказанно {k['cards_live_verified']}) · С ОШИБКОЙ {k['cards_errored']} (цель 0) · "
         f"ждут категорию {k['need_mapping']} · готовы к заливу {k['ready_to_publish']}"),
        f"индекс: средний {avg} (цель {k['top_threshold']:.0f}%, в зоне ТОП: {k['in_top_zone']})",
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

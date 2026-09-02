#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РОЛЬ · ТРЕНД-СКАУТ (YM_TRENDSCOUT) — поймать окно спроса ДО насыщения, не после.

Канон роли SOCC (TFS-1, 8 полей) — см. CHARTER ниже.

Зачем: цель оператора — «на хайпе закупить и продать x10». Но х10 бывает только в УЗКОМ окне:
пока спрос растёт, а предложение не догнало. Опоздал на две недели — купил склад неликвида по
пиковой цене. Поэтому роль отвечает не за «найти модный товар», а за ФАЗУ ОКНА: рано / рост /
пик / поздно. И за честный отказ, когда сигнал слаб.

ГЛАВНЫЙ ЗАКОН (T1): тренд без источника — это слух, а не действие. У органа СЕЙЧАС нет
подключённого источника трендов. Роль от этого не выдумывает цифры: она возвращает честное
«нет источника» и говорит, какой адаптер подключить. Как только источник появится (WB-скаут,
выгрузка поставщика, статистика своих продаж) — роль считает по нему, а не по ощущениям.

Что роль НЕ делает (граница честности):
  • не закупает и не тратит деньги (RUBICON у оператора — роль только предлагает);
  • не выдумывает объём спроса, цену и число конкурентов;
  • не называет «трендом» одиночный всплеск без истории;
  • не предлагает вход в фазе «поздно», даже если товар выглядит красиво.
"""
from __future__ import annotations

import json
import sys

CHARTER = {
    "id": "YM_TRENDSCOUT",
    "name_ru": "ТРЕНД-СКАУТ",
    "mandate": "ловить окна растущего спроса до насыщения и честно отсекать опоздавшие",
    "owns": ["фаза окна спроса", "срок годности сигнала", "лимит риска на хайп-закупку"],
    "inputs": ["адаптеры источников (WB-скаут, выгрузки, своя статистика продаж)",
               "маржа кандидата (econ)", "лимит риска оператора"],
    "outputs": ["кандидаты с фазой окна → оператор/ТОВАРОВЕД", "запрос источника → оператор"],
    "laws": [
        "T1 тренд без источника = слух: нет данных → отказ и запрос адаптера, НЕ выдуманное число",
        "T2 у сигнала есть срок годности: старше max_age_days → протух, входить нельзя",
        "T3 фаза окна решает: late/пик → НЕ входим, даже если товар нравится",
        "T4 закупка под хайп ограничена лимитом риска оператора; лимита нет → рекомендуемая сумма 0",
        "T5 одиночный всплеск без истории ≥ min_points — не тренд, а шум",
        "T6 роль не тратит деньги: только предлагает, решает оператор (RUBICON)",
    ],
    "kpi": [
        {"metric": "кандидатов с подтверждённым источником", "target": "100% выданных",
         "source_of_truth": "поле source у каждого сигнала"},
        {"metric": "входов в фазе late", "target": "0", "source_of_truth": "фаза на момент решения"},
        {"metric": "сумма рекомендаций сверх лимита риска", "target": "0₽",
         "source_of_truth": "risk_cap оператора"},
    ],
    "proves_by": "каждый кандидат: источник → ряд точек спроса → фаза окна → сумма в пределах лимита",
}

# Пороги фазы окна. Не «ощущения» — явные правила, которые приёмка может фальсифицировать.
MIN_POINTS = 3          # T5: меньше точек истории — это шум, не тренд
MAX_AGE_DAYS = 14       # T2: сигнал старше — протух
GROWTH_EARLY = 0.15     # рост ≥15% за период при низкой конкуренции → раннее окно
GROWTH_FLAT = 0.03      # рост <3% → плато (пик/поздно)
SATURATED_SELLERS = 30  # продавцов больше → окно закрыто (догнали)


def _growth(points):
    """Относительный рост по ряду точек спроса: (последняя − первая) / первая. Мусор → None."""
    vals = [p for p in points if isinstance(p, (int, float))]
    if len(vals) < MIN_POINTS or vals[0] <= 0:
        return None
    return round((vals[-1] - vals[0]) / vals[0], 4)


def classify_window(points, sellers=None, age_days=None):
    """Фаза окна спроса по явным правилам (T2/T3/T5). Возвращает {phase, action, why}.

    phase: early (входить) / growth (входить) / peak (осторожно) / late (не входить) /
           noise (мало истории) / stale (протух).
    """
    if age_days is not None and age_days > MAX_AGE_DAYS:
        return {"phase": "stale", "action": "SKIP",
                "why": f"сигналу {age_days} дн > {MAX_AGE_DAYS} (T2) — данные протухли, вход вслепую"}
    g = _growth(points)
    if g is None:
        return {"phase": "noise", "action": "SKIP",
                "why": f"истории меньше {MIN_POINTS} точек (T5) — это шум, а не тренд"}
    saturated = isinstance(sellers, int) and sellers >= SATURATED_SELLERS
    if saturated and g < GROWTH_EARLY:
        return {"phase": "late", "action": "SKIP", "growth": g,
                "why": f"продавцов {sellers} ≥{SATURATED_SELLERS} и рост {g:.0%} слабый (T3) — опоздали"}
    if g < GROWTH_FLAT:
        return {"phase": "peak", "action": "WATCH", "growth": g,
                "why": f"рост {g:.0%} — плато; вход только если маржа очень высокая"}
    if g >= GROWTH_EARLY and not saturated:
        return {"phase": "early", "action": "ENTER", "growth": g,
                "why": f"рост {g:.0%} при {sellers if sellers is not None else '?'} продавцах — окно открыто"}
    return {"phase": "growth", "action": "ENTER", "growth": g,
            "why": f"рост {g:.0%} — спрос растёт, окно ещё не закрыто"}


def size_position(candidate, risk_cap_rub=None, max_share=0.25):
    """Сколько рублей можно поставить на кандидата (T4/T6). Без лимита оператора → 0.

    max_share — доля лимита на ОДНОГО кандидата (не кладём все яйца в одну корзину).
    Роль только считает предел; покупает оператор.
    """
    if not risk_cap_rub or risk_cap_rub <= 0:
        return {"amount_rub": 0, "why": "лимит риска оператора не задан (T4) — рекомендуем 0₽",
                "needs_operator": "укажи лимит риска на хайп-закупки (risk_cap_rub)"}
    cost = candidate.get("cost_buy")
    amount = round(risk_cap_rub * max_share, 2)
    units = int(amount // cost) if isinstance(cost, (int, float)) and cost > 0 else None
    return {"amount_rub": amount, "units": units,
            "why": f"≤{max_share:.0%} лимита {risk_cap_rub:.0f}₽ на одного кандидата (T4)",
            "needs_operator": "подтверждение закупки (RUBICON — деньги двигает оператор)"}


def scan(source_fn=None, risk_cap_rub=None, now_days=None):
    """Осмотреть источники трендов. БЕЗ подключённого источника — честный отказ (T1), не выдумка.

    source_fn — шов адаптера: функция без аргументов, возвращающая список сигналов вида
      {"sku"/"name", "points":[...], "sellers":int|None, "age_days":int|None,
       "cost_buy":float|None, "price_sell":float|None, "source":"откуда"}
    Первый реальный адаптер — wb_scout_v1 (нос спроса оси ARBITER); пока не подключён.

    Возвращает {ok, candidates[], skipped[], need_source, agg}.
    """
    if source_fn is None:
        return {
            "ok": False, "role": CHARTER["id"], "reason": "NO_TREND_SOURCE",
            "candidates": [], "skipped": [],
            "need_source": ("источник трендов не подключён (T1): нужен адаптер — WB-скаут "
                            "(wb_scout_v1), выгрузка поставщика или статистика своих продаж"),
            "note": "роль не выдумывает тренды: без источника кандидатов НЕТ (это честный ноль)",
            "agg": {"candidates": 0, "skipped": 0},
        }
    try:
        signals = source_fn() or []
    except Exception as e:
        return {"ok": False, "role": CHARTER["id"], "error": f"{type(e).__name__}: {e}",
                "candidates": [], "skipped": [],
                "note": "источник упал — НЕ считаем, что трендов нет (это разные утверждения)",
                "agg": {"candidates": 0, "skipped": 0}}

    candidates, skipped = [], []
    for s in signals:
        if not isinstance(s, dict):
            continue
        name = s.get("name") or s.get("sku") or "?"
        if not s.get("source"):
            skipped.append({"name": name, "why": "у сигнала нет источника (T1) — слух, не действие"})
            continue
        win = classify_window(s.get("points") or [], sellers=s.get("sellers"),
                              age_days=s.get("age_days", now_days))
        row = {"name": name, "sku": s.get("sku"), "source": s.get("source"),
               "sellers": s.get("sellers"), **win}
        # маржа кандидата — только из данных сигнала, ничего не выдумываем
        cost, sell = s.get("cost_buy"), s.get("price_sell")
        if isinstance(cost, (int, float)) and isinstance(sell, (int, float)) and cost > 0:
            row["margin_rub"] = round(sell - cost, 2)
            row["margin_x"] = round(sell / cost, 2)      # во сколько раз (тот самый «х10»)
        else:
            row["margin_rub"] = None
            row["margin_x"] = None
            row["margin_note"] = "нет закупки/цены в сигнале — множитель не считаем (T1)"
        if win["action"] == "ENTER":
            row["position"] = size_position({"cost_buy": cost}, risk_cap_rub=risk_cap_rub)
            candidates.append(row)
        else:
            skipped.append(row)

    # ранг: сначала множитель (х10 — цель оператора), потом рост
    candidates.sort(key=lambda r: ((r.get("margin_x") or 0), (r.get("growth") or 0)), reverse=True)
    return {"ok": True, "role": CHARTER["id"], "candidates": candidates, "skipped": skipped,
            "need_source": None,
            "agg": {"candidates": len(candidates), "skipped": len(skipped),
                    "best_x": candidates[0].get("margin_x") if candidates else None}}


def render(res):
    """Человеческий доклад ТРЕНД-СКАУТА (для дневного отчёта)."""
    if not res:
        return "ТРЕНД-СКАУТ: нет данных"
    if not res.get("ok"):
        if res.get("reason") == "NO_TREND_SOURCE":
            return ("ТРЕНД-СКАУТ · источник трендов НЕ подключён — кандидатов нет (честный ноль).\n"
                    f"  → {res['need_source']}")
        return f"ТРЕНД-СКАУТ: источник упал — {res.get('error')} (это не «трендов нет»)"
    a = res["agg"]
    lines = [f"ТРЕНД-СКАУТ · кандидатов {a['candidates']}, отсеяно {a['skipped']}"]
    for c in res["candidates"][:5]:
        x = f"x{c['margin_x']}" if c.get("margin_x") else "множитель неизвестен"
        pos = c.get("position", {})
        lines.append(f"  • {c['name']} · фаза {c['phase']} · {x} · {c['why']}")
        lines.append(f"      ставка ≤{pos.get('amount_rub', 0):.0f}₽ · решает оператор (RUBICON)")
    late = [s for s in res["skipped"] if isinstance(s, dict) and s.get("phase") in ("late", "peak")]
    if late:
        lines.append(f"  не входим ({len(late)}): опоздали или плато — это экономия, а не потеря")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ТРЕНД-СКАУТ — окна спроса (0₽, без сети)")
    ap.add_argument("--charter", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.charter:
        print(json.dumps(CHARTER, ensure_ascii=False, indent=2))
        sys.exit(0)
    res = scan()   # без адаптера — честный отказ
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render(res))

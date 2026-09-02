#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РОЛЬ · СТРАТЕГ (YM_STRATEGIST) — ищет, где лежат недобранные деньги, и считает их.

Канон роли SOCC (TFS-1, 8 полей) — см. CHARTER ниже.

Зачем: остальные роли держат СЕГОДНЯ (заказы, остатки, цена, индекс). СТРАТЕГ отвечает за ЗАВТРА —
почему выручка не растёт и какой ход даст больше всего ₽ на единицу усилия. Он не фантазёр:
работает по РЫЧАГАМ, которые орган реально может дёрнуть, и каждый ход считает числом из
ФАКТОВ органа (память карточек, индекс, маржа, доклады ролей), а не из головы.

ГЛАВНЫЙ ЗАКОН (G1): гипотеза без числа — не гипотеза. Если для рычага нет данных, СТРАТЕГ не
придумывает «ну примерно 30%», а честно говорит: нужен источник, вот какой. Это отличает
стратегию от гадания.

Что роль НЕ делает (граница честности):
  • не двигает цены и остатки сама (это ЦЕНОВИК и СКЛАДОВЩИК — у них свои законы);
  • не обещает выручку («заработаем X») — даёт ОЦЕНКУ ПОТОЛКА с явной формулой и допущениями;
  • не предлагает ходы, ломающие пол маржи (P1) или роняющие индекс качества (C-зоны);
  • не выдумывает внешний спрос — это работа ТРЕНД-СКАУТА, и тоже только с источником.
"""
from __future__ import annotations

import json
import sys

import ymarket_econ_v1 as econ

CHARTER = {
    "id": "YM_STRATEGIST",
    "name_ru": "СТРАТЕГ",
    "mandate": "находить недобранные деньги органа и ранжировать ходы роста по ₽ на единицу усилия",
    "owns": ["карта рычагов роста", "оценка потолка по каждому рычагу", "очередь проверок гипотез"],
    "inputs": ["память карточек (state)", "индекс и рекомендации", "маржа (econ)",
               "доклады ролей за смену", "журнал смен (тренд)"],
    "outputs": ["ранжированный список ходов → БРИГАДИР/управляющий",
                "запросы на источник данных → оператор"],
    "laws": [
        "G1 гипотеза без числа = не гипотеза: нет данных → запрос источника, НЕ выдуманная цифра",
        "G2 ход не имеет права ломать пол маржи (P1 ЦЕНОВИКА) — рост в убыток не рост",
        "G3 ход не имеет права ронять индекс качества (C1–C3) — штрафы съедят прибыль",
        "G4 ранг по ₽/усилие, а не по красоте идеи (дешёвые проверки первыми)",
        "G5 ход без следующего действия и владельца = мечта: у каждого next_action + кто делает",
        "G6 оценка — это ПОТОЛОК с формулой и допущениями, а не обещание выручки",
    ],
    "kpi": [
        {"metric": "ходов с посчитанным ₽", "target": "100% выданных",
         "source_of_truth": "поле expected_rub + formula"},
        {"metric": "мёртвых карточек (ошибка/заморозка)", "target": "0",
         "source_of_truth": "память state + статусы Маркета"},
        {"metric": "SKU с неизвестным остатком", "target": "0",
         "source_of_truth": "доклад СКЛАДОВЩИКА"},
    ],
    "proves_by": "каждый ход: рычаг → факты, из которых он выведен → формула оценки → next_action",
}

# Стоимость проверки хода в условных единицах усилия (для ранга ₽/усилие).
# Не деньги — время/риск. Дешёвое проверяем первым (G4).
EFFORT = {"trivial": 1, "low": 2, "medium": 5, "high": 12}


def _rub(v):
    return None if v is None else round(float(v), 2)


def _lever(lever, why, expected_rub, formula, next_action, owner, effort="medium",
           facts=None, needs_source=None, blocked_by=None):
    """Единая форма хода. expected_rub=None + needs_source → честное «нужен источник» (G1)."""
    e = EFFORT.get(effort, 5)
    score = None if expected_rub is None else round(float(expected_rub) / e, 2)
    return {
        "lever": lever,
        "why": why,
        "expected_rub": _rub(expected_rub),      # ПОТОЛОК, не обещание (G6)
        "formula": formula,
        "effort": effort,
        "effort_units": e,
        "score": score,                          # ₽ на единицу усилия — по нему ранг (G4)
        "next_action": next_action,              # G5
        "owner": owner,                          # G5
        "facts": facts or {},
        "needs_source": needs_source,            # G1: чего не хватает, чтобы посчитать
        "blocked_by": blocked_by,
    }


def _dead_cards(state_doc):
    """Рычаг 1: мёртвые карточки — в ошибке/заморозке они не продают ВООБЩЕ.

    Живой урок Маркета №2: карточка в HAS_CARD_CAN_UPDATE_ERRORS заморожена — обновления молча не
    применяются. Это не «недобор», это ноль. Потолок считаем честно: воскрешённая карточка в лучшем
    случае даёт средний по органу чек; среднего нет → нет числа (G1).
    """
    skus = (state_doc or {}).get("skus", {})
    dead = [oid for oid, s in skus.items()
            if s.get("status") in ("NO_CARD_ERRORS", "HAS_CARD_CAN_UPDATE_ERRORS")
            or (s.get("preflight_errors") or [])]
    if not dead:
        return None
    # средний чек по органу — только из карточек с известной ценой (не выдумываем)
    prices = [s.get("margin", {}).get("price_sell") for s in skus.values()
              if isinstance(s.get("margin"), dict)]
    prices = [p for p in prices if isinstance(p, (int, float))]
    avg = round(sum(prices) / len(prices), 2) if prices else None
    if avg is None:
        return _lever(
            "DEAD_CARD_REVIVE",
            f"{len(dead)} карточек в ошибке/заморозке — они не продают вообще (ноль, не недобор)",
            None, "нет средней цены по органу → потолок не считаем (G1)",
            "пере-отправить offer через offer-mappings/update → статус упадёт в CAN_UPDATE, "
            "после чего обновления пройдут (живой урок №2)",
            "УПРАВЛЯЮЩИЙ", effort="low",
            facts={"dead_skus": dead[:20], "count": len(dead)},
            needs_source="цена продажи хотя бы части карточек (для среднего чека)")
    return _lever(
        "DEAD_CARD_REVIVE",
        f"{len(dead)} карточек заморожены/с ошибкой — продают ноль",
        len(dead) * avg,
        f"{len(dead)} мёртвых × средний чек {avg}₽ = потолок одной продажи с каждой (G6: потолок)",
        "пере-отправить offer через offer-mappings/update (снятие заморозки, урок №2), затем verify",
        "УПРАВЛЯЮЩИЙ", effort="low",
        facts={"dead_skus": dead[:20], "count": len(dead), "avg_price": avg})


def _unknown_stock(shift_report):
    """Рычаг 2: SKU с неизвестным остатком стоят с нулём — витрина есть, продаж нет.

    Закон СКЛАДОВЩИКА S1 «лучше ноль, чем ложь» абсолютно верен, но он консервирует проблему:
    пока источник наличия не подключён, товар физически не продаётся. Это самый тупой и самый
    дорогой недобор — поэтому рычаг всегда в списке, пока есть хоть один unknown.
    """
    st = ((shift_report or {}).get("steps") or {}).get("STOCKMAN") or {}
    unknown = st.get("unknown_source")
    if not unknown:
        return None
    return _lever(
        "STOCK_SOURCE_CONNECT",
        f"{unknown} SKU с неизвестным остатком → выставлен 0 (S1) → они не продаются вообще",
        None,
        "потолок = число SKU × их оборот; оборота нет, пока нет источника наличия (G1)",
        "подключить реальный источник наличия партнёра (выгрузка/API) → СКЛАДОВЩИК поднимет остатки",
        "ОПЕРАТОР", effort="medium",
        facts={"unknown_skus": unknown},
        needs_source="источник наличия партнёра (какие SKU реально есть и сколько)")


def _index_lift(state_doc, threshold=None):
    """Рычаг 3: карточки ниже порога заполненности хуже ранжируются → меньше показов.

    Считаем ЧЕСТНО: связь «индекс → выручка» у нас не измерена, поэтому ₽ не выдумываем.
    Даём объём работы и недобор в пунктах — это факт; деньги появятся, когда измерим конверсию.
    """
    thr = threshold if threshold is not None else econ.TOP_RATING_THRESHOLD
    skus = (state_doc or {}).get("skus", {})
    low = {oid: s.get("content_rating") for oid, s in skus.items()
           if isinstance(s.get("content_rating"), (int, float)) and s["content_rating"] < thr}
    if not low:
        return None
    total_gap = round(sum(thr - r for r in low.values()), 1)
    return _lever(
        "INDEX_LIFT",
        f"{len(low)} карточек ниже {thr:.0f}% заполненности — суммарный недобор {total_gap} пунктов",
        None,
        "связь индекс→выручка ещё НЕ измерена на наших данных → ₽ не выдумываем (G1); "
        "измеряется A/B: поднять индекс части карточек и сравнить показы/заказы",
        "закрыть закрываемые рекомендации (фото/описание/характеристики) по самым выгодным карточкам",
        "УПРАВЛЯЮЩИЙ", effort="medium",
        facts={"cards_below": len(low), "total_gap_points": total_gap,
               "worst": sorted(low.items(), key=lambda kv: kv[1])[:10]},
        needs_source="замер конверсии показ→заказ до/после подъёма индекса (A/B на своих карточках)")


def _price_headroom(state_doc):
    """Рычаг 4: где цена ниже потолка рынка, но выше пола маржи — там лежат деньги.

    Требует рекомендаций цены от Маркета (recommended price). Их в памяти нет → честный запрос
    источника, а не «поднимем на 10%».
    """
    skus = (state_doc or {}).get("skus", {})
    with_reco = [oid for oid, s in skus.items() if s.get("recommended_price")]
    if not with_reco:
        if not skus:
            return None
        return _lever(
            "PRICE_HEADROOM",
            "не знаем, где цена ниже рыночного потолка — рекомендации Маркета не читаются",
            None,
            "потолок = Σ(рекомендованная − текущая) по SKU, где результат ≥ пола маржи (G2)",
            "включить чтение price-recommendations Маркета в тик и сложить в память",
            "УПРАВЛЯЮЩИЙ", effort="low",
            facts={"cards_tracked": len(skus)},
            needs_source="рекомендации цены Маркета (offer-recommendations) по нашим SKU")
    gain = 0.0
    for oid in with_reco:
        s = skus[oid]
        cur = (s.get("margin") or {}).get("price_sell")
        rec = s.get("recommended_price")
        if isinstance(cur, (int, float)) and isinstance(rec, (int, float)) and rec > cur:
            gain += rec - cur
    if gain <= 0:
        return None
    return _lever(
        "PRICE_HEADROOM",
        f"{len(with_reco)} карточек имеют рекомендацию цены выше текущей",
        gain,
        "Σ(рекомендованная − текущая); ЦЕНОВИК всё равно проверит пол маржи (G2)",
        "передать список ЦЕНОВИКУ на пере-оценку (он держит P1 — ниже пола не пустит)",
        "ЦЕНОВИК", effort="low",
        facts={"skus": with_reco[:20]})


def _assortment(state_doc, target_sku=None):
    """Рычаг 5: узкий ассортимент — потолок выручки упирается в число карточек.

    target_sku — цель оператора по числу SKU. Нет цели → не выдумываем «надо 500» (G1).
    """
    skus = (state_doc or {}).get("skus", {})
    n = len(skus)
    if target_sku is None:
        return _lever(
            "ASSORTMENT_WIDEN",
            f"в витрине {n} SKU — цель по ассортименту не задана, потолок роста неизвестен",
            None,
            "потолок = (цель_SKU − текущие) × средний чек × конверсия; цели нет → числа нет (G1)",
            "задать цель по числу SKU на квартал (сколько карточек хотим держать)",
            "ОПЕРАТОР", effort="trivial",
            facts={"current_sku": n},
            needs_source="цель оператора по числу SKU")
    if n >= target_sku:
        return None
    prices = [(s.get("margin") or {}).get("price_sell") for s in skus.values()]
    prices = [p for p in prices if isinstance(p, (int, float))]
    avg = round(sum(prices) / len(prices), 2) if prices else None
    missing = target_sku - n
    if avg is None:
        return _lever(
            "ASSORTMENT_WIDEN", f"до цели {target_sku} SKU не хватает {missing}",
            None, "нет средней цены → потолок не считаем (G1)",
            "залить следующую пачку карточек из подтверждённой категории",
            "УПРАВЛЯЮЩИЙ", effort="high", facts={"current_sku": n, "missing": missing},
            needs_source="цена продажи по карточкам")
    return _lever(
        "ASSORTMENT_WIDEN",
        f"до цели {target_sku} SKU не хватает {missing} карточек",
        missing * avg,
        f"{missing} недостающих × средний чек {avg}₽ = потолок одной продажи с каждой (G6)",
        "залить следующую пачку из подтверждённой категории (preflight → commit по отмашке)",
        "УПРАВЛЯЮЩИЙ", effort="high",
        facts={"current_sku": n, "target": target_sku, "missing": missing, "avg_price": avg})


def plan(state_doc=None, shift_report=None, target_sku=None, threshold=None):
    """Собрать ходы роста и отранжировать. Ничего не отправляет и не меняет — чистая аналитика, 0₽.

    Возвращает {ok, moves[], need_sources[], agg}. moves отсортированы по ₽/усилие (G4);
    ходы без числа идут после посчитанных, но НЕ выбрасываются — они и есть очередь на источники.
    """
    builders = [
        _dead_cards(state_doc),
        _unknown_stock(shift_report),
        _index_lift(state_doc, threshold),
        _price_headroom(state_doc),
        _assortment(state_doc, target_sku),
    ]
    moves = [m for m in builders if m]
    scored = [m for m in moves if m.get("score") is not None]
    unscored = [m for m in moves if m.get("score") is None]
    scored.sort(key=lambda m: m["score"], reverse=True)
    unscored.sort(key=lambda m: m["effort_units"])
    ordered = scored + unscored
    need = [{"lever": m["lever"], "needs_source": m["needs_source"], "why": m["why"]}
            for m in moves if m.get("needs_source")]
    return {
        "ok": True,
        "role": CHARTER["id"],
        "moves": ordered,
        "need_sources": need,
        "agg": {
            "moves": len(ordered),
            "with_number": len(scored),
            "need_source": len(need),
            "top_lever": ordered[0]["lever"] if ordered else None,
            "ceiling_rub": _rub(sum(m["expected_rub"] for m in scored)) if scored else None,
        },
    }


def render(res):
    """Человеческий доклад СТРАТЕГА (для дневного отчёта)."""
    if not res or not res.get("ok"):
        return "СТРАТЕГ: не смог собрать картину"
    a = res["agg"]
    lines = [f"СТРАТЕГ · ходов {a['moves']} (с числом {a['with_number']}, ждут источник {a['need_source']})"]
    if a["ceiling_rub"]:
        lines.append(f"  потолок посчитанного: {a['ceiling_rub']:.0f}₽ (это ПОТОЛОК, не обещание)")
    for m in res["moves"][:5]:
        rub = f"{m['expected_rub']:.0f}₽" if m["expected_rub"] is not None else "число: нужен источник"
        lines.append(f"  • {m['lever']}: {m['why']}")
        lines.append(f"      {rub} · усилие {m['effort']} · делает {m['owner']}")
        lines.append(f"      → {m['next_action']}")
    if res["need_sources"]:
        lines.append("  чего не хватает, чтобы считать точнее:")
        for n in res["need_sources"][:4]:
            lines.append(f"      – {n['needs_source']} (для {n['lever']})")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="СТРАТЕГ — ходы роста из фактов органа (0₽, без сети)")
    ap.add_argument("--charter", action="store_true", help="показать канон роли")
    ap.add_argument("--target-sku", type=int, default=None, help="цель по числу SKU")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.charter:
        print(json.dumps(CHARTER, ensure_ascii=False, indent=2))
        sys.exit(0)
    import ymarket_state_v1 as state
    res = plan(state.load(), target_sku=args.target_sku)
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render(res))

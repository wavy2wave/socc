#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PRICING V1 — движок ЧЕСТНОЙ ЦЕНЫ органа ARBITER: индекс цен ДО публикации + гарантия плюса.

ЗАЧЕМ (слова создателя, дословный смысл): «главное — чтобы я гарантированно даже после доставки
и комиссии маркету остался в плюсе. Минимум 3x, и стремимся максимально маржу снимать. На товары,
которых точно нет на других площадках — мы сами решаем цены.»

Три открытия, которые этот файл делает КОДОМ (не на словах):

  1. ИНДЕКС ЦЕН ОЗОН — убийца наивной наценки. Озон сравнивает твою цену с ЭТАЛОНОМ того же товара
     (в т.ч. с твоим же товаром на WB). index = цена_озон / эталон. index > 1.05 → карточка ПРЯЧЕТСЯ
     из органики (страницы 3-5, продаж ~0). Значит на MATCHABLE-товаре высокая наценка = смерть в
     органике. estimate_price_index() считает это ДО публикации — не гадаем постфактум.

  2. ГОЛУБАЯ ВОДА — где эталона НЕТ, индекс не с чем считать → цена НАША. Товара нет на Озон/ЯМ
     (и мы прячем WB-происхождение уникализацией) → бенчмарка нет → index не бьёт. classify_slot()
     честно метит: blue_water | thin | thick | unknown. Только тут работает «мы сами решаем цену».

  3. NET_COEFF ловушка: до продавца доходит лишь 29.8% цены (ФАКТ кабинета 2026-08-05: комиссия
     продажи 53%), а доставка нетто ₽325 — ОТДЕЛЬНАЯ строка сверху, не «в общем котле». Значит
     3x·cost даёт продавцу лишь 0.89·cost — уже минус ДО доставки. «min 3x» — это пол-опровержение,
     а не безопасная цель. guaranteed_profit() считает плюс ПОСЛЕ ВСЕХ издержек (комиссия + закуп +
     доставка) и режет связку, если после доставки уходит в минус. Прежняя модель (0.35 «65% общим
     котлом» + доставка ₽100) ошибалась ДВАЖДЫ в разные стороны — см. ozon_truth_v1.

ГРАНИЦА ЧЕСТНОСТИ (RUBICON): этот файл НЕ двигает деньги и НЕ рисует доход. Он лишь СЧИТАЕТ цену
и ПРЕДСКАЗЫВАЕТ индекс/прибыль до публикации. Реальный ₽ — только verified в revenue_ledger (SETTLE).
Индекс — МОДЕЛЬ (эталон приблизителен), помечен явно; точное значение даёт кабинет Озон после публикации.

Переиспускает PROSPECTOR (формула цены/маржи) — не дублирует. Чистый stdlib, fail-soft.
"""
import sys
import json
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent          # SOCC/scripts/mint/arbiter
MINT = HERE.parent                                # SOCC/scripts/mint
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import socc_mint_prospect_v1 as prospector       # noqa: E402  (формула цены Ozon: NET_COEFF, ozon_price)

# ── Пороги стратегии (все калибруемы — это инженерные числа, не догма) ──────────────
INDEX_CEIL = 1.05        # index > 1.05 → Озон прячет карточку из органики (официальный порог-эффект)
INDEX_TARGET = 1.00      # целимся ≤1.00 с запасом (не на самой грани обрезания)
THIN_CARDS = 10          # < THIN конкурентных карточек на Озон = тонкая ниша (легко в топ-30)
THICK_CARDS = 30         # ≥ THICK = насыщено (индекс бьёт жёстко, нужна уникализация или отказ)
MIN_MULTIPLE = 3.0       # жёсткий пол наценки (слова создателя) — НО движок докажет, хватает ли его
TARGET_MULTIPLE = 5.0    # цель наценки (исторические 5x создателя — здоровая маржа), floor'ится вниз
DEFAULT_NET_COEFF = prospector.NET_COEFF   # 0.298 — ФАКТ кабинета (доля цены, доходящая до продавца)
DEFAULT_DELIVERY = prospector.DELIVERY_NET # ₽325 — ФАКТ кабинета (доставка нетто), единый источник


def guaranteed_profit(price_sell, cost_buy, delivery=0.0, net_coeff=None):
    """Чистая прибыль ПОСЛЕ ВСЕХ издержек: комиссия+буст (net_coeff) + закуп + ДОСТАВКА.

    Именно та гарантия, что просил создатель: seller_receipt = price·net_coeff (то, что реально
    доходит после удержаний Озон); profit = seller_receipt − cost_buy − delivery. delivery —
    последняя миля (Яндекс.Go/ПВЗ), явная строка, а не спрятанная. Возврат {...}.
    """
    net = float(net_coeff if net_coeff is not None else DEFAULT_NET_COEFF)
    price = float(price_sell or 0)
    cost = float(cost_buy or 0)
    dlv = float(delivery or 0)
    seller_receipt = round(price * net, 2)
    profit_net = round(seller_receipt - cost - dlv, 2)
    markup = round(price / cost, 3) if cost > 0 else None
    return {"price_sell": price, "seller_receipt": seller_receipt, "cost_buy": cost,
            "delivery": dlv, "fee": round(price - seller_receipt, 2),
            "profit_net": profit_net, "markup": markup, "net_coeff": net,
            "in_plus": profit_net > 0}


def estimate_price_index(price_sell, benchmark_price):
    """Предсказать индекс цен Озон ДО публикации: index = наша_цена / эталон.

    benchmark_price — цена ТОГО ЖЕ товара, которую Озон видит для сравнения (типично: твоя же
    закупочная цена на WB — ведь Озон матчит карточку к WB-листингу). None/≤0 → эталона НЕТ
    (голубая вода/уникализовано) → index неприменим → возвращаем None (index не бьёт).
    """
    b = float(benchmark_price or 0)
    if b <= 0:
        return None
    return round(float(price_sell or 0) / b, 3)


def index_safe(index):
    """Индекс безопасен для органики? None (нет эталона) = безопасен. Иначе ≤ INDEX_CEIL."""
    return True if index is None else index <= INDEX_CEIL


def classify_slot(coverage):
    """Честно классифицировать слот Озон по покрытию: blue_water | thin | thick | unknown.

    coverage — из gap_v1.ozon_search: {known, cards}. known=False → покрытие неизвестно (Озон
    бот-защищён) → 'unknown' (НЕ выдумываем воду). cards==0 → blue_water (никого нет → цена наша).
    """
    cov = coverage or {}
    if not cov.get("known"):
        return "unknown"
    cards = cov.get("cards")
    if not isinstance(cards, int) or isinstance(cards, bool):
        return "unknown"
    if cards == 0:
        return "blue_water"
    if cards < THIN_CARDS:
        return "thin"
    if cards >= THICK_CARDS:
        return "thick"
    return "thin"     # THIN..THICK — умеренно, ведём как тонкую (индекс всё же проверим)


def recommend_markup(candidate, coverage, min_multiple=MIN_MULTIPLE, target_multiple=TARGET_MULTIPLE,
                     delivery=0.0, net_coeff=None):
    """Рекомендуемый диапазон наценки [min, max] под гарантию плюса + индекс <1.

    Идём от цели (target_multiple) вниз: сперва проверяем, проходит ли целевая наценка индекс <1.05.
    Если да — возвращаем её. Иначе пробуем floor до безопасного индекса. Если и это даёт убыток или
    <min_multiple — связка отклоняется (подойдёт голубая вода/уникализация или отказ).

    benchmark_price — цена ТОГО ЖЕ товара, которую Озон видит для сравнения. Типично: cost_buy на WB
    (Озон матчит карточку → находит WB-эталон → сравнивает). Если бенчмарка нет (голубая вода или
    уникализовано) — берём target_multiple смело (индекс не бьёт).

    Возвращает {'ok', 'recommended_markup', 'price_sell', 'profit_net', 'index', 'slot_class', 'why'}.
    """
    net = float(net_coeff if net_coeff is not None else DEFAULT_NET_COEFF)
    cost = float(candidate.get("cost", 0) or 0)
    if cost <= 0:
        return {"ok": False, "recommended_markup": None, "price_sell": None, "profit_net": None,
                "index": None, "slot_class": None,
                "why": "cost_buy неизвестен или ≤0 — рекомендовать наценку не на чем"}

    slot_class = classify_slot(coverage)
    benchmark = float(candidate.get("benchmark_price", 0) or 0)
    # голубая вода ИЛИ бенчмарка нет → индекс не применим → цель смело
    if slot_class == "blue_water" or benchmark <= 0:
        price = round(cost * target_multiple, 2)
        pf = guaranteed_profit(price, cost, delivery, net)
        if pf["profit_net"] <= 0:
            return {"ok": False, "recommended_markup": None, "price_sell": price, "profit_net": pf["profit_net"],
                    "index": None, "slot_class": slot_class,
                    "why": f"голубая вода, но даже {target_multiple}x даёт убыток после доставки"}
        return {"ok": True, "recommended_markup": target_multiple, "price_sell": price,
                "profit_net": pf["profit_net"], "index": None, "slot_class": slot_class,
                "why": f"голубая вода — индекс не бьёт, цена наша ({target_multiple}x)"}

    # есть benchmark → индекс применим → сперва проверим target_multiple
    price_target = round(cost * target_multiple, 2)
    idx_target = estimate_price_index(price_target, benchmark)
    pf_target = guaranteed_profit(price_target, cost, delivery, net)
    if index_safe(idx_target) and pf_target["profit_net"] > 0:
        return {"ok": True, "recommended_markup": target_multiple, "price_sell": price_target,
                "profit_net": pf_target["profit_net"], "index": idx_target, "slot_class": slot_class,
                "why": f"target {target_multiple}x проходит индекс {idx_target} <{INDEX_CEIL} + плюс"}

    # target_multiple бьёт индекс или в убыток → пробуем floor до безопасного индекса
    safe_price = round(benchmark * INDEX_TARGET, 2)   # INDEX_TARGET=1.00 с запасом
    safe_markup = round(safe_price / cost, 3) if cost > 0 else 0
    pf_safe = guaranteed_profit(safe_price, cost, delivery, net)
    idx_safe = estimate_price_index(safe_price, benchmark)

    if safe_markup < min_multiple:
        return {"ok": False, "recommended_markup": None, "price_sell": safe_price,
                "profit_net": pf_safe["profit_net"], "index": idx_safe, "slot_class": slot_class,
                "why": f"безопасный индекс {idx_safe} даёт наценку {safe_markup}x < floor {min_multiple}x — "
                       f"связка отклоняется (нужна голубая вода/уникализация или отказ)"}
    if pf_safe["profit_net"] <= 0:
        return {"ok": False, "recommended_markup": None, "price_sell": safe_price,
                "profit_net": pf_safe["profit_net"], "index": idx_safe, "slot_class": slot_class,
                "why": f"безопасный индекс {idx_safe} даёт убыток ₽{pf_safe['profit_net']} после доставки — "
                       f"связка отклоняется"}
    return {"ok": True, "recommended_markup": safe_markup, "price_sell": safe_price,
            "profit_net": pf_safe["profit_net"], "index": idx_safe, "slot_class": slot_class,
            "why": f"floor к безопасному индексу {idx_safe}: наценка {safe_markup}x, плюс ₽{pf_safe['profit_net']}"}


def is_blue_water(candidate, ozon_coverage=None, yandex_coverage=None):
    """Голубая вода? — товара нет НИ на Озон, НИ на Яндекс.Маркет (или мы не смогли проверить).

    Возвращает {status, known, note}. status='blue_water' ⟺ оба покрытия known=True И cards==0.
    known=False где-то → честно 'unknown' (не выдумываем воду). Это фильтр «монополия».
    """
    oz = ozon_coverage or {}
    ya = yandex_coverage or {}
    oz_known, oz_cards = oz.get("known"), oz.get("cards")
    ya_known, ya_cards = ya.get("known"), ya.get("cards")

    if not oz_known or not ya_known:
        return {"status": "unknown", "known": False,
                "note": "покрытие Озон/ЯМ неизвестно (бот-защита) — не выдумываем голубую воду"}
    # оба известны
    oz_c = int(oz_cards) if isinstance(oz_cards, int) and not isinstance(oz_cards, bool) else None
    ya_c = int(ya_cards) if isinstance(ya_cards, int) and not isinstance(ya_cards, bool) else None
    if oz_c is None or ya_c is None:
        return {"status": "unknown", "known": False,
                "note": "cards не число где-то — честная деградация в unknown"}
    if oz_c == 0 and ya_c == 0:
        return {"status": "blue_water", "known": True, "ozon_cards": 0, "yandex_cards": 0,
                "note": "нет конкурентов НИ на Озон, НИ на Яндекс → цена наша (монополия)"}
    return {"status": "matchable", "known": True, "ozon_cards": oz_c, "yandex_cards": ya_c,
            "note": f"есть конкуренты ({oz_c} озон, {ya_c} яндекс) — индекс цен применим"}


def price_strategy(candidate, ozon_coverage=None, yandex_coverage=None, min_multiple=MIN_MULTIPLE,
                   target_multiple=TARGET_MULTIPLE, delivery=0.0, net_coeff=None):
    """Полная стратегия цены: голубая вода → target_multiple; matchable → recommend_markup.

    Возвращает {ok, strategy, recommended_markup, price_sell, profit_net, index, slot_class, blue_water, why}.
    Честность: если нет гарантии плюса или индекс бьёт — ok=False (связка отклоняется).
    """
    bw = is_blue_water(candidate, ozon_coverage, yandex_coverage)
    if bw["status"] == "blue_water":
        # голубая вода → recommend_markup честно вернёт target_multiple (индекс не применим)
        rec = recommend_markup(candidate, ozon_coverage, min_multiple, target_multiple, delivery, net_coeff)
        rec = dict(rec, strategy="blue_water", blue_water=bw)
        return rec
    # matchable или unknown → recommend_markup решает (индекс применим, если известен benchmark)
    cand = dict(candidate, benchmark_price=candidate.get("cost", 0))  # benchmark = WB-закуп (то, что Озон матчит)
    rec = recommend_markup(cand, ozon_coverage, min_multiple, target_multiple, delivery, net_coeff)
    rec = dict(rec, strategy="matchable" if bw["status"] == "matchable" else "unknown", blue_water=bw)
    return rec


def decide_price(candidate, ozon_coverage=None, yandex_coverage=None, uniqueize_report=None,
                 min_multiple=MIN_MULTIPLE, target_multiple=TARGET_MULTIPLE, delivery=0.0,
                 net_coeff=None, unlink_risk_ceiling=25):
    """ЕДИНЫЙ вердикт цены, связывающий ТРИ пути создателя в одну честную функцию.

    Три пути обойти индекс цен (>1.05 прячет карточку из органики) + ГАРАНТИЯ ПЛЮСА везде:

      1. ГОЛУБАЯ ВОДА (is_blue_water) — товара нет НИ на Озон, НИ на ЯМ → эталона нет → индекс
         неприменим → цена НАША (target_multiple). strategy='blue_water'.
      2. НЕСВЯЗЫВАЕМЫЙ (uniqueize_report) — карточка уникализована так, что риск склейки с WB-эталоном
         < unlink_risk_ceiling (own_card_likely). Озон не найдёт дешёвый WB-оригинал для сравнения →
         индекс неприменим → цена НАША. strategy='uniqueized_unlinkable'. ЭТО и есть «защита маржи».
      3. ЧЕСТНЫЙ FLOOR (matchable) — Озон СВЯЖЕТ (не уникализовано, есть конкуренты) → индекс бьёт →
         floor цены к безопасному индексу; если floor < min_multiple или в убыток → отклонить.
         strategy='matchable_index_capped'.

    Во ВСЕХ путях guaranteed_profit > 0 (после комиссии+буста+доставки) — ЖЁСТКИЙ гейт. Нет плюса →
    ok=False (никогда не проводим убыточную связку, что бы ни говорил индекс). Возврат — см. price_strategy.
    """
    cost = float(candidate.get("cost", 0) or 0)
    if cost <= 0:
        return {"ok": False, "strategy": "no_cost", "recommended_markup": None, "price_sell": None,
                "profit_net": None, "index": None, "slot_class": None, "unlinkable": False,
                "why": "cost_buy неизвестен или ≤0 — цену считать не на чем"}

    bw = is_blue_water(candidate, ozon_coverage, yandex_coverage)

    # Путь 2: несвязываемость через уникализацию. Риск склейки низкий → Озон не найдёт WB-эталон.
    coll = (uniqueize_report or {}).get("collision") or {}
    unlinkable = (isinstance(coll.get("risk"), (int, float))
                  and coll["risk"] < float(unlink_risk_ceiling)
                  and coll.get("verdict") == "own_card_likely")

    # Путь 1 (голубая вода) ИЛИ Путь 2 (несвязываемо) → эталона для индекса нет → цена наша (target).
    if bw["status"] == "blue_water" or unlinkable:
        price = round(cost * target_multiple, 2)
        pf = guaranteed_profit(price, cost, delivery, net_coeff)
        strategy = "blue_water" if bw["status"] == "blue_water" else "uniqueized_unlinkable"
        if pf["profit_net"] <= 0:
            return {"ok": False, "strategy": strategy, "recommended_markup": target_multiple,
                    "price_sell": price, "profit_net": pf["profit_net"], "index": None,
                    "slot_class": classify_slot(ozon_coverage), "unlinkable": unlinkable, "blue_water": bw,
                    "why": f"{strategy}: даже {target_multiple}x даёт убыток ₽{pf['profit_net']} после доставки"}
        reason = ("нет конкурентов нигде — цена наша" if strategy == "blue_water"
                  else f"уникализовано (риск склейки {coll.get('risk')}<{unlink_risk_ceiling}) — "
                       f"Озон не свяжет с WB-эталоном, индекс не бьёт")
        return {"ok": True, "strategy": strategy, "recommended_markup": target_multiple,
                "price_sell": price, "profit_net": pf["profit_net"], "index": None,
                "slot_class": classify_slot(ozon_coverage), "unlinkable": unlinkable, "blue_water": bw,
                "why": f"{reason} ({target_multiple}x, плюс ₽{pf['profit_net']})"}

    # Путь 3: matchable — Озон свяжет → индекс применим → floor к безопасной цене (benchmark = WB-закуп).
    cand = dict(candidate, benchmark_price=candidate.get("cost", 0))
    rec = recommend_markup(cand, ozon_coverage, min_multiple, target_multiple, delivery, net_coeff)
    rec = dict(rec, strategy="matchable_index_capped", unlinkable=False, blue_water=bw)
    return rec


def _main(argv=None):
    ap = argparse.ArgumentParser(description="PRICING V1 — движок ЧЕСТНОЙ ЦЕНЫ ARBITER (индекс+гарантия плюса)")
    ap.add_argument("--cost", type=float, required=True, help="закупочная цена (WB)")
    ap.add_argument("--markup", type=float, help="наценка для demo guaranteed_profit (дефолт TARGET_MULTIPLE)")
    ap.add_argument("--delivery", type=float, default=DEFAULT_DELIVERY,
                    help=f"доставка последняя миля (по умолчанию факт кабинета ₽{DEFAULT_DELIVERY:.0f})")
    ap.add_argument("--benchmark", type=float, help="эталонная цена того же товара (для index demo)")
    ap.add_argument("--ozon-cards", type=int, help="покрытие Озон (cards) для demo slot/recommend")
    ap.add_argument("--min-multiple", type=float, default=MIN_MULTIPLE)
    ap.add_argument("--target-multiple", type=float, default=TARGET_MULTIPLE)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    markup = args.markup if args.markup else args.target_multiple
    price = round(args.cost * markup, 2)
    pf = guaranteed_profit(price, args.cost, args.delivery)

    # demo: индекс (если задан benchmark)
    idx = None
    if args.benchmark:
        idx = estimate_price_index(price, args.benchmark)
        idx_ok = index_safe(idx)
    else:
        idx_ok = None

    # demo: slot class + recommend_markup (если задан ozon-cards)
    rec = None
    if args.ozon_cards is not None:
        cov = {"known": True, "cards": args.ozon_cards}
        cand = {"cost": args.cost, "benchmark_price": args.benchmark or args.cost}
        rec = recommend_markup(cand, cov, args.min_multiple, args.target_multiple, args.delivery)

    out = {"cost_buy": args.cost, "markup": markup, "price_sell": price,
           "profit_net": pf["profit_net"], "in_plus": pf["in_plus"],
           "delivery": args.delivery, "net_coeff": pf["net_coeff"],
           "index": idx, "index_safe": idx_ok, "recommendation": rec}

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print(f"💰 PRICING ENGINE (честная цена + гарантия плюса)")
    print(f"   закуп ₽{args.cost}  наценка {markup}x  →  цена ₽{price}")
    print(f"   чист ₽{pf['profit_net']}  доставка ₽{args.delivery}  "
          f"→  {'✅ в плюсе' if pf['in_plus'] else '❌ в минусе'}")
    if idx is not None:
        print(f"   индекс {idx}  (benchmark ₽{args.benchmark})  "
              f"→  {'✅ безопасно' if idx_ok else f'⛔ >{ INDEX_CEIL} убьёт органику'}")
    if rec:
        print(f"   RECOMMEND: {'✅' if rec['ok'] else '⛔'}  слот[{rec['slot_class']}]  "
              f"наценка {rec['recommended_markup']}x  →  цена ₽{rec['price_sell']}  чист ₽{rec['profit_net']}")
        print(f"      {rec['why']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""АДАПТЕР ЗДОРОВЬЯ КАБИНЕТА — единственный шов между суточным циклом и живой СВЕРКОЙ карточек.

Зачем отдельный файл (а не строка в day):
  • Провязка «СВЕРКА в цикл». Раньше `cards_errored` в run_day шёл ИЗ ПАМЯТИ (что запомнила
    само-модель по прошлым заливам), а НЕ из живого `errors[]` кабинета. Цикл был СЛЕП к реальным
    ошибкам карточек — планка оператора YM1 «ни одной карточки с ошибкой» не могла быть правдой.
  • Живой классификатор здоровья `classify_card_health` живёт в `ymarket_write_v1.py`, который ведёт
    ПАРАЛЛЕЛЬНАЯ линия Claude (активно правит дефекты). Чтобы её правки НЕ могли уронить суточный
    цикл, ВСЁ связывание с write изолировано здесь и ДВАЖДЫ ограждено (import под try + вызов под try).
    day → этот адаптер (всегда импортируем, stdlib-only) → guarded write. Разрыв в write = честный
    None, НИКОГДА не фейковый 0 (фейковый 0 = ложная зелень — худшее, что можно сделать под YM1).

Определение «карточка с ошибкой» = РОВНО то же, что `reconcile.error_skus` параллельной линии:
  klass ∈ {frozen, error_fixable} — у карточки есть СВОИ `our_errors`. Единый язык двух линий, без
  расхождения. «Магазин отключён» (store_blocked) — вина ВИТРИНЫ, а не карточки → НЕ ошибка (снимает
  оператор в кабинете). needs_placement / processing / unknown — тоже НЕ ошибки: здоровье за факт
  не выдаём (та же ловушка «ложной зелени», которую параллельная линия закрыла в classify_card_health).

RUBICON: 0₽. `card_health(cards)` — чистая, без сети. `read_card_health(...)` делает ОДИН READ
offer-cards (как `_read_cabinet` в day — свободное чтение, денег не двигает, наружу не пишет).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# «Карточка с ошибкой» по планке YM1 = у карточки есть свои errors[].
# Держим кортеж синхронно с ymarket_write_v1.reconcile.error_skus (klass in frozen/error_fixable).
ERRORED_KLASSES = ("frozen", "error_fixable")

_EMPTY = {"classifier": "unavailable", "cards_total": 0, "cards_errored": None,
          "errored": [], "store_blocked": [], "needs_placement": [], "by_klass": {}}


def _classifier():
    """Живой классификатор из параллельной линии — ОГРАЖДЁННО. Разрыв → None (честно, не падаем).

    Импорт write отделён сюда, чтобы правки соседней линии (мид-фикс дефектов) физически не могли
    уронить суточный цикл: худшее, что даёт разрыв, — None-классификатор → cards_errored=None.
    """
    try:
        import ymarket_write_v1 as write
        fn = getattr(write, "classify_card_health", None)
        return fn if callable(fn) else None
    except Exception:
        return None


def card_health(cards, classify_fn=None):
    """ЧИСТО: список карточек из offer_cards_status → сводка здоровья (0₽, без сети).

    Возврат ВСЕГДА одной формы (форма не зависит от достижимости классификатора):
      {classifier:    "live" | "unavailable",
       cards_total:   int,
       cards_errored: int | None,   # None ⇔ классификатор недостижим → честно «не знаю», НЕ 0
       errored:       [{offerId, klass, action, cardStatus, our_errors}],   # klass ∈ ERRORED_KLASSES
       store_blocked: [ …та же форма… ],   # витрина отключена — НЕ наша ошибка, держим отдельно
       needs_placement:[ …та же форма… ],  # контент готов, но не в кампании — НЕ ошибка (разместить)
       by_klass:      {klass: count}}
    """
    classify_fn = classify_fn or _classifier()
    total = len(cards) if isinstance(cards, (list, tuple)) else 0
    if classify_fn is None:
        # НЕТ живого классификатора → не выдаём фейковый 0. cards_errored=None = «честно не знаю».
        out = dict(_EMPTY)
        out["cards_total"] = total
        out["errored"] = []
        out["store_blocked"] = []
        out["needs_placement"] = []
        out["by_klass"] = {}
        return out

    errored, store_blocked, needs_placement, by_klass = [], [], [], {}
    for card in (cards or []):
        try:
            h = classify_fn(card)
        except Exception:
            # одна карточка сломала классификатор → считаем её unknown, сводкой НЕ роняем (fail-soft).
            by_klass["unknown"] = by_klass.get("unknown", 0) + 1
            continue
        if not isinstance(h, dict):
            by_klass["unknown"] = by_klass.get("unknown", 0) + 1
            continue
        klass = h.get("klass")
        by_klass[klass] = by_klass.get(klass, 0) + 1
        row = {"offerId": h.get("offerId"), "klass": klass, "action": h.get("action"),
               "cardStatus": h.get("cardStatus"), "our_errors": h.get("our_errors") or []}
        if klass in ERRORED_KLASSES:
            errored.append(row)
        elif klass == "store_blocked":
            store_blocked.append(row)
        elif klass == "needs_placement":
            needs_placement.append(row)
    return {"classifier": "live", "cards_total": total,
            "cards_errored": len(errored), "errored": errored,
            "store_blocked": store_blocked, "needs_placement": needs_placement,
            "by_klass": by_klass}


def read_card_health(business_id=None, hands=None, limit=100):
    """ЖИВОЙ READ (0₽, RUBICON цел — только чтение): offer-cards кабинета → card_health.

    Для standalone/CLI/ручной сверки. В суточном цикле day уже держит `cards` из `_read_cabinet` и
    зовёт `card_health` на них напрямую (без второго запроса). Fail-soft на каждом шаге: руки
    недоступны / сеть упала / businessId неизвестен → честный `cards_errored=None` + `read_error`.
    """
    if hands is None:
        try:
            import ymarket_hands_v1 as hands
        except Exception as e:
            out = dict(_EMPTY); out["read_error"] = f"{type(e).__name__}: {e}"; return out
    bid = business_id
    if not bid:
        try:
            bid = hands.business_id_env()
        except Exception:
            bid = None
    try:
        cards = hands.offer_cards_status(bid, limit=limit)
    except Exception as e:
        out = dict(_EMPTY); out["read_error"] = f"{type(e).__name__}: {e}"; return out
    return card_health(cards if isinstance(cards, list) else [])


if __name__ == "__main__":
    # Ручная живая сверка здоровья кабинета одной командой (READ, 0₽). Секретов не печатает.
    import argparse
    import json
    ap = argparse.ArgumentParser(description="ЗДОРОВЬЕ КАБИНЕТА — живой READ offer-cards (0₽, без записи)")
    ap.add_argument("--business-id", default=None, help="businessId кабинета (по умолч. из env YANDEX_BUSINESS_ID)")
    ap.add_argument("--json", action="store_true", help="сырой JSON вместо человеческой сводки")
    args = ap.parse_args()
    h = read_card_health(business_id=args.business_id)
    if args.json:
        print(json.dumps(h, ensure_ascii=False, indent=2))
    else:
        src = h["classifier"]
        ce = h["cards_errored"]
        print("🩺 ЗДОРОВЬЕ КАБИНЕТА (READ, 0₽)")
        if "read_error" in h:
            print(f"   ⚠️  чтение не удалось: {h['read_error']}")
        print(f"   классификатор: {'ЖИВОЙ' if src == 'live' else 'НЕДОСТУПЕН (write мид-фикс?)'}")
        print(f"   карточек всего: {h['cards_total']}")
        print(f"   с ошибкой (YM1, цель 0): {'—' if ce is None else ce}"
              + ("" if ce is None else "  " + ", ".join(
                  f"{r['offerId']}[{r['klass']}]" for r in h["errored"]) if h["errored"] else ""))
        if h["store_blocked"]:
            print(f"   магазин отключён (вина витрины, не карточки): {len(h['store_blocked'])} "
                  "→ снимает ОПЕРАТОР в кабинете")
        if h["by_klass"]:
            print(f"   по классам: {h['by_klass']}")

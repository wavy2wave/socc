#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M2-PRICING ПРИЁМКА — ЦЕНОВОЙ ГЕЙТ поверх GAP: три пути создателя + ГАРАНТИЯ ПЛЮСА (dry, 0₽).

Веха: индекс цен Озон (>1.05 прячет карточку из органики) + удержание 65% (NET_COEFF=0.35) делают
наивную наценку смертельной на matchable-товаре. Создатель дал ТРИ пути обойти это, и жёсткое условие:
он ОБЯЗАН остаться в плюсе после комиссии+доставки (минимум 3x, максимизируя маржу). Приёмка доказывает,
что gap.prove(pricing=...) кодирует ровно это — и что БЕЗ pricing поведение 1:1 как в M2 (обратн. совм.).

  P1  none_is_backcompat      — pricing=None → блок цены не исполняется, price=None, verdict как в M2.
  P2  matchable_rejected      — Озон+ЯМ имеют карточки → индекс бьёт → floor даёт <3x → PROVEN→REJECTED.
  P3  bluewater_our_price     — нет НИ на Озон, НИ на ЯМ → эталона нет → цена НАША (5x), плюс → PROVEN.
  P4  uniqueized_unlinkable   — matchable, НО карточка уникализована (риск склейки<25) → индекс неприменим → PROVEN.
  P5  delivery_kills_plus     — даже голубая вода, но доставка съедает плюс → ok=False → REJECTED (гарантия плюса — гейт).
  P6  gate_only_hardens       — REJECTED по WARDEN (красная линия) НИКОГДА не промотится ценой в PROVEN.
  P7  failsoft_bad_pricing    — битый net_coeff → ценовой гейт падает МЯГКО, конвейер жив, PROVEN→REJECTED честно.
  P8  min3x_floor_is_real     — «минимум 3x» — не лозунг: на matchable floor к безопасному индексу <3x → отказ (доказано числом).

Все оффлайн-детерминированы (coverage/uniqueize — фейковые dict, сети нет). НЕ трогает канон и деньги.
Это отдельный файл — run_m2.py (13 зелёных) НЕ модифицируется (директива «не ломай что работает»).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent                    # SOCC/scripts/mint/arbiter
MINT = ARB.parent                    # SOCC/scripts/mint
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import gap_v1 as gap                              # noqa: E402
import uniqueizer_v1 as uniq                      # noqa: E402


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


def mk(name, cost=200, strength=80, sku="s", url="u", **extra):
    """Кандидат в схеме SCOUT (зеркалит run_m2.mk). cost=200 → 0.75·cost=150 покрывает доставку 100."""
    d = {"name": name, "cost": cost, "source_market": "wildberries", "sku": sku, "url": url,
         "demand_signal": {"strength": strength, "kind": "wildberries_public_proxy"}}
    d.update(extra)
    return d


def p1_none_is_backcompat():
    """pricing=None → ценовой блок НЕ исполняется: price=None, verdict как в M2 (обратная совместимость)."""
    cand = mk("Органайзер для кабелей")
    r = gap.prove(cand, profit_target=600, min_profit=200, coverage={"known": True, "cards": 10})
    ok = (r["verdict"] == "PROVEN" and r["price"] is None
          and r["econ"]["passed"] is True and r["slot"]["score"] == 74.4)
    return ok, f"verdict={r['verdict']}, price={r['price']} (блок не тронут), слот={r['slot']['score']}"


def p2_matchable_rejected():
    """Озон+ЯМ имеют карточки → индекс бьёт → floor к безопасной цене даёт <3x → PROVEN→REJECTED."""
    cand = mk("Органайзер для кабелей")
    pricing = {"yandex_coverage": {"known": True, "cards": 5}, "delivery": 100}
    r = gap.prove(cand, coverage={"known": True, "cards": 50}, pricing=pricing)
    ok = (r["verdict"] == "REJECTED" and r["price"]["ok"] is False
          and r["price"]["strategy"] == "matchable_index_capped"
          and any(x.startswith("PRICE:") for x in r["reasons"]))
    return ok, f"verdict={r['verdict']}, strat={r['price']['strategy']}, причина PRICE есть={any(x.startswith('PRICE:') for x in r['reasons'])}"


def p3_bluewater_our_price():
    """Нет НИ на Озон, НИ на ЯМ → эталона нет → индекс неприменим → цена НАША (5x), плюс → PROVEN.

    Закуп ₽400 (не ₽200): после ДОЗНАНИЯ кабинета (2026-08-05) коэффициент = 0.298 вместо
    допущенных 0.35, и 5x на закупе ₽200 даёт −₽2 — честно мёртв. Фикстура отражает реальность.
    """
    cand = mk("Уникальный товар без аналогов", cost=400)
    pricing = {"yandex_coverage": {"known": True, "cards": 0}, "delivery": 100}
    r = gap.prove(cand, coverage={"known": True, "cards": 0}, pricing=pricing)
    p = r["price"]
    ok = (r["verdict"] == "PROVEN" and p["ok"] is True and p["strategy"] == "blue_water"
          and p["index"] is None and p["recommended_markup"] == 5.0 and p["profit_net"] > 0)
    return ok, f"verdict={r['verdict']}, strat={p['strategy']}, {p['recommended_markup']}x, индекс={p['index']}, чист ₽{p['profit_net']}"


def p4_uniqueized_unlinkable():
    """matchable, НО карточка уникализована (риск склейки<25) → Озон не свяжет с WB → индекс неприменим → PROVEN."""
    rep = uniq.uniqueize({"sku": "s", "name": "Органайзер WB", "brand": "NoName", "cost": 400},
                         house_brand="RAINO")
    cand = mk("Органайзер для кабелей", cost=400)
    pricing = {"yandex_coverage": {"known": True, "cards": 5}, "delivery": 100,
               "uniqueize_report": rep["law_report"]}
    r = gap.prove(cand, coverage={"known": True, "cards": 50}, pricing=pricing)
    p = r["price"]
    risk = rep["law_report"]["collision"]["risk"]
    ok = (r["verdict"] == "PROVEN" and p["ok"] is True and p["strategy"] == "uniqueized_unlinkable"
          and p["unlinkable"] is True and p["index"] is None and p["profit_net"] > 0 and risk < 25)
    return ok, f"verdict={r['verdict']}, unlinkable={p['unlinkable']}, риск склейки={risk}<25, {p['recommended_markup']}x, чист ₽{p['profit_net']}"


def p5_delivery_kills_plus():
    """Гарантия плюса — ЖЁСТКИЙ гейт: даже голубая вода, но доставка съедает плюс → ok=False → REJECTED."""
    cand = mk("Уникальный товар без аналогов")
    pricing = {"yandex_coverage": {"known": True, "cards": 0}, "delivery": 100000}  # абсурдная доставка
    r = gap.prove(cand, coverage={"known": True, "cards": 0}, pricing=pricing)
    p = r["price"]
    ok = (r["verdict"] == "REJECTED" and p["ok"] is False and p["profit_net"] < 0
          and p["strategy"] == "blue_water")   # путь голубой воды, но плюса нет → всё равно режем
    return ok, f"verdict={r['verdict']}, ok={p['ok']}, чист ₽{p['profit_net']} (доставка убила плюс)"


def p6_gate_only_hardens():
    """Ценовой гейт МОНОТОНЕН: REJECTED по WARDEN (красная линия) НИКОГДА не промотится ценой в PROVEN."""
    cand = mk("Дроп карта для переводов")                     # RL1 денойлист WARDEN
    pricing = {"yandex_coverage": {"known": True, "cards": 0}, "delivery": 100}  # цена была бы ок (голубая вода)
    r = gap.prove(cand, coverage={"known": True, "cards": 0}, pricing=pricing)
    # verdict остаётся REJECTED из-за WARDEN; ценовой путь мог быть ok, но промоушена НЕТ
    ok = (r["verdict"] == "REJECTED" and r["warden"]["status"] == "FAIL"
          and "RL1_text" in r["warden"]["hard_failures"])
    return ok, f"verdict={r['verdict']} (WARDEN {r['warden']['hard_failures']}), цена не промотит незаконное"


def p7_failsoft_bad_pricing():
    """Битый net_coeff → ценовой гейт падает МЯГКО (не роняет конвейер), PROVEN→REJECTED честно (сомнение→нет)."""
    cand = mk("Органайзер для кабелей")
    pricing = {"yandex_coverage": {"known": True, "cards": 5}, "net_coeff": "abc"}  # float('abc') внутри → ошибка
    r = gap.prove(cand, coverage={"known": True, "cards": 50}, pricing=pricing)
    p = r["price"]
    ok = (r["verdict"] == "REJECTED" and p["ok"] is False
          and p["strategy"] == "price_gate_error" and "why" in p)
    return ok, f"verdict={r['verdict']}, strat={p['strategy']} (упал мягко, конвейер жив)"


def p8_min3x_floor_is_real():
    """«Минимум 3x» — не лозунг: на matchable безопасный индекс даёт наценку <3x → отказ, доказано ЧИСЛОМ.

    Прямой вызов движка цены: benchmark=cost (Озон матчит карточку к WB-эталону = наша закупка),
    безопасная цена = benchmark·1.0 → наценка ровно 1.0x < floor 3.0x. Число, не слова.
    """
    import pricing_v1 as price
    cand = {"cost": 200}
    dec = price.decide_price(cand, ozon_coverage={"known": True, "cards": 50},
                             yandex_coverage={"known": True, "cards": 5},
                             delivery=100, min_multiple=3.0, target_multiple=5.0)
    ok = (dec["ok"] is False and dec["strategy"] == "matchable_index_capped"
          and dec["index"] == 1.0 and "floor 3.0x" in dec["why"])
    return ok, f"ok={dec['ok']}, индекс={dec['index']}, наценка<floor → отказ: «{dec['why'][:52]}…»"


TESTS = [
    ("P1 none_is_backcompat", p1_none_is_backcompat),
    ("P2 matchable_rejected", p2_matchable_rejected),
    ("P3 bluewater_our_price", p3_bluewater_our_price),
    ("P4 uniqueized_unlinkable", p4_uniqueized_unlinkable),
    ("P5 delivery_kills_plus", p5_delivery_kills_plus),
    ("P6 gate_only_hardens", p6_gate_only_hardens),
    ("P7 failsoft_bad_pricing", p7_failsoft_bad_pricing),
    ("P8 min3x_floor_is_real", p8_min3x_floor_is_real),
]


def main():
    print("═" * 68)
    print("  ARBITER · M2-PRICING ПРИЁМКА — ЦЕНОВОЙ ГЕЙТ: три пути + гарантия плюса (dry, 0₽)")
    print("═" * 68)
    total = 0
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        total += 1
        passed += 1 if ok else 0
        print(f"{_passed(ok)}  {name}: {detail}")
    print("─" * 68)
    print(f"ИТОГ M2-PRICING:  {passed}/{total} зелёные")
    print("═" * 68)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

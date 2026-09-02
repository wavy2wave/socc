#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЯНДЕКС ПРИЁМКА — СКАУТ РОСТА (ГОРОДА + МОДЕЛИ). Сухо, 0₽, без сети.

Проверяем ЗАКОНЫ скаута, а не «запустилось». Каждый тест падает при нарушении закона.

  GR1  axes_only_city_model     — каждый ход только на оси ГОРОДА/МОДЕЛИ (ассортимент — у СТРАТЕГА, G4)
  GR2  no_number_no_silence     — ход без ₽ обязан нести needs_source (открытая дверь честно без числа, G1/G2)
  GR3  dormant_shop_seen        — спящий магазин (active=False) → ход ОЖИВИТЬ на оси МОДЕЛИ, владелец ОПЕРАТОР
  GR4  unknown_shop_not_judged  — магазин с active=None НЕ объявляется спящим (не врём про смерть канала, G2)
  GR5  disabled_model_lever     — выключенная модель склада → ход ВКЛЮЧИТЬ (зовёт set_warehouse_model, честно про кабинет)
  GR6  express_city_reach       — города Express в facts = снимку; упор в руки-кабинет помечен (G6)
  GR7  blind_city_in_our_hands  — обслуживаем город не из known → ход ОТКРЫТЬ, blocked_by=None (в наших руках)
  GR8  known_city_not_blind     — город из known НЕ попадает в слепые
  GR9  cheapest_lawful_first    — безчисловые ходы сортируются по усилию возр. (дешёвый законный шаг первым)
  GR10 rubicon_no_live_snapshot — при переданном снимке живой READ НЕ вызывается (0 сети, 0 записи)
  GR11 fail_soft_garbage        — набор битых снимков не роняет plan (G5/L6), ok=True
  GR12 render_smoke             — render на плане и на пустом плане не падает, несёт заголовок роли
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
SCRIPTS = MINT.parent
for p in (str(ARB), str(MINT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_role_growth_v1 as growth   # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


# Снимок кабинета: спящий DBS-магазин + магазин с неизвестной активностью,
# склад Москва (DBS выключен), склад Казань (Express включён, город НЕ в known).
SNAP = {
    "business_id": "216949599",
    "shops": [
        {"id": "149215943", "placements": ["FBS", "EXPRESS"], "active": True},
        {"id": "149215945", "placements": ["DBS"], "active": False},    # спящий канал
        {"id": "149999999", "placements": ["FBS"], "active": None},     # активность не читали
    ],
    "warehouses": [
        {"id": "2390811", "name": "Atlas", "city": "Москва",
         "models": {"FBS": "ENABLED", "EXPRESS": "ENABLED", "DBS": "DISABLED"}},
        {"id": "2390812", "name": "Kazan-1", "city": "Казань",
         "models": {"EXPRESS": "ENABLED"}},
    ],
    "known_cities": ["москва"],
}


def _plan():
    return growth.plan(snapshot=SNAP)


def _find(moves, lever_prefix):
    return [m for m in moves if m["lever"].startswith(lever_prefix)]


def gr1_axes_only_city_model():
    moves = _plan()["moves"]
    ok = bool(moves) and all(m["axis"] in (growth.AXIS_CITY, growth.AXIS_MODEL) for m in moves)
    no_assort = all("АССОРТИМЕНТ" not in m["axis"] for m in moves)
    return ok and no_assort, f"ходов={len(moves)} оси={sorted({m['axis'] for m in moves})}"


def gr2_no_number_no_silence():
    moves = _plan()["moves"]
    offenders = [m["lever"] for m in moves if m["expected_rub"] is None and not m.get("needs_source")]
    return not offenders, f"без числа и без источника: {offenders or 'нет — честно'}"


def gr3_dormant_shop_seen():
    moves = _plan()["moves"]
    m = _find(moves, "ОЖИВИТЬ_МАГАЗИН_149215945")
    ok = (m and m[0]["axis"] == growth.AXIS_MODEL and m[0]["owner"] == "ОПЕРАТОР"
          and "слово оператора" in (m[0]["blocked_by"] or ""))
    return bool(ok), f"ход_оживить={bool(m)} " + (f"ось={m[0]['axis']} владелец={m[0]['owner']}" if m else "нет хода")


def gr4_unknown_shop_not_judged():
    moves = _plan()["moves"]
    # магазин 149999999 (active=None) НЕ должен породить ход «оживить»
    judged = _find(moves, "ОЖИВИТЬ_МАГАЗИН_149999999")
    return not judged, f"неизвестный-по-активности объявлен спящим={bool(judged)} (ждём False)"


def gr5_disabled_model_lever():
    moves = _plan()["moves"]
    m = _find(moves, "ВКЛЮЧИТЬ_DBS_")
    if not m:
        return False, "нет хода ВКЛЮЧИТЬ_DBS для выключенной модели склада"
    mv = m[0]
    calls_write = "set_warehouse_model" in mv["next_action"]
    honest_cabinet = "кабинет" in mv["next_action"]        # если Маркет выключил сам — только кабинет
    gated = "write-гейт" in (mv["blocked_by"] or "")
    return (mv["axis"] == growth.AXIS_MODEL and calls_write and honest_cabinet and gated), \
        f"зовёт_set_warehouse_model={calls_write} честно_про_кабинет={honest_cabinet} write-гейт={gated}"


def gr6_express_city_reach():
    res = _plan()
    m = _find(res["moves"], "РАСШИРИТЬ_ГОРОДА_EXPRESS")
    if not m:
        return False, "нет хода расширения городов Express"
    mv = m[0]
    facts_cities = set(mv["facts"].get("express_cities") or [])
    match = facts_cities == {"москва", "казань"}
    hands_block = "руками" in (mv["blocked_by"] or "") or "кабинет" in (mv["blocked_by"] or "")
    return (mv["axis"] == growth.AXIS_CITY and match and hands_block), \
        f"города_в_facts={sorted(facts_cities)} упор_в_руки={hands_block}"


def gr7_blind_city_in_our_hands():
    res = _plan()
    m = _find(res["moves"], "ОТКРЫТЬ_ГОРОДА_В_МЕРЧАНДАЙЗЕРЕ")
    if not m:
        return False, "нет хода открыть слепой город"
    mv = m[0]
    blind = set(mv["facts"].get("blind_cities") or [])
    in_our_hands = mv["blocked_by"] is None       # не нужен ни кабинет, ни слово оператора
    return ("казань" in blind and mv["axis"] == growth.AXIS_CITY and in_our_hands), \
        f"слепые={sorted(blind)} в_наших_руках(blocked_by is None)={in_our_hands}"


def gr8_known_city_not_blind():
    res = _plan()
    m = _find(res["moves"], "ОТКРЫТЬ_ГОРОДА_В_МЕРЧАНДАЙЗЕРЕ")
    blind = set(m[0]["facts"].get("blind_cities") or []) if m else set()
    # москва в known → не должна быть слепой
    return ("москва" not in blind and res["map"]["blind_cities"] == ["казань"]), \
        f"слепые={sorted(blind)} (москва не слепая, только казань)"


def gr9_cheapest_lawful_first():
    moves = _plan()["moves"]
    scoreless = [m for m in moves if m["score"] is None]
    units = [m["effort_units"] for m in scoreless]
    sorted_asc = units == sorted(units)
    # самый дорогой ход (Express, high) — последний среди безчисловых
    last_is_express = moves[-1]["lever"] == "РАСШИРИТЬ_ГОРОДА_EXPRESS"
    return (sorted_asc and last_is_express), f"усилия={units} по_возр={sorted_asc} последний_Express={last_is_express}"


def gr10_rubicon_no_live_snapshot():
    """При переданном снимке живой READ не должен вызываться вовсе (RUBICON: 0 сети, 0 записи)."""
    orig = growth._gather_live
    tripped = {"hit": False}

    def bomb(*a, **k):
        tripped["hit"] = True
        raise AssertionError("живой READ вызван при переданном снимке — нарушение RUBICON")

    growth._gather_live = bomb
    try:
        res = growth.plan(snapshot=SNAP)
    finally:
        growth._gather_live = orig
    return (res["ok"] and not tripped["hit"]), f"живой_READ_вызван={tripped['hit']} (ждём False)"


def gr11_fail_soft_garbage():
    garbage = [
        42, "x", [1, 2, 3],                                       # снимок вообще не словарь
        {"shops": "nope", "warehouses": 7},                       # поля не тех типов
        {"shops": [1, 2, 3], "warehouses": {"a": 1}},             # элементы не словари
        {"shops": [{"id": 1, "placements": "FBS", "active": False}],
         "warehouses": [{"models": [1, 2], "city": 123}]},        # placements-строка, models-список, city-число
        {"warehouses": [{"city": "Тула", "models": {"EXPRESS": None}}]},  # статус None
        {"known_cities": 5},                                      # known не список
    ]
    for g in garbage:
        try:
            res = growth.plan(snapshot=g)
        except Exception as e:
            return False, f"упал на {str(g)[:44]}: {type(e).__name__}: {e}"
        if not res.get("ok"):
            return False, f"на {str(g)[:44]} ok=False"
    return True, f"{len(garbage)} битых снимков пережиты, plan не упал"


def gr12_render_smoke():
    try:
        full = growth.render(_plan())
        empty = growth.render(growth.plan(snapshot={}))
        none_ = growth.render(None)
    except Exception as e:
        return False, f"render упал: {type(e).__name__}: {e}"
    ok = ("СКАУТ РОСТА" in full and "нет снимка" in empty and "отчёта нет" in none_)
    return ok, f"заголовок_в_плане={'СКАУТ РОСТА' in full} пустой_честен={'нет снимка' in empty}"


TESTS = [
    ("GR1  axes_only_city_model", gr1_axes_only_city_model),
    ("GR2  no_number_no_silence", gr2_no_number_no_silence),
    ("GR3  dormant_shop_seen", gr3_dormant_shop_seen),
    ("GR4  unknown_shop_not_judged", gr4_unknown_shop_not_judged),
    ("GR5  disabled_model_lever", gr5_disabled_model_lever),
    ("GR6  express_city_reach", gr6_express_city_reach),
    ("GR7  blind_city_in_our_hands", gr7_blind_city_in_our_hands),
    ("GR8  known_city_not_blind", gr8_known_city_not_blind),
    ("GR9  cheapest_lawful_first", gr9_cheapest_lawful_first),
    ("GR10 rubicon_no_live_snapshot", gr10_rubicon_no_live_snapshot),
    ("GR11 fail_soft_garbage", gr11_fail_soft_garbage),
    ("GR12 render_smoke", gr12_render_smoke),
]


def main():
    print("🎯 ЯНДЕКС ПРИЁМКА · СКАУТ РОСТА (ГОРОДА + МОДЕЛИ, сухо, 0₽, без сети)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<30} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Двери роста видны на осях ГОРОДА+МОДЕЛИ, число честно (needs_source), RUBICON цел (0 сети/0 записи)")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

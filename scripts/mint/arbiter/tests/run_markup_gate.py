#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — ВОРОТА МАНИФЕСТ-MARKUP (#14-фиксы ревью проводки #13). Сухо, 0₽.

Ревью (13 агентов, адверсариал) подтвердило: `float(markup) if markup else MARKUP` тихо
превращало JSON true в 1.0, а 0/""/отсутствие — в 8.0 (маскировка коррупции), и цена уходила
≤ закупки (гарантированный убыток после издержек, P1) или молча «по дефолту». #14-фиксы:
resolve_markup() громко говорит «это битый манифест»; build_product кидает ValueError;
движок (node_build) гейтит манифест ПОНЯТНЫМ FAIL-ом ДО каких-либо действий.

  MG1 none_default          — markup не задан (None) → модульная MARKUP 8.0 (обратносовместимо)
  MG2 numeric_ok            — число/строка-число >1 → как есть (8.0 / 12.0 / 1.5)
  MG3 boolean_rejected      — true/false → ошибка (было: тихая цена == закупка)
  MG4 falsy_rejected        — 0 / 1 / 0.5 / "" / "abc" → ошибка (было: тихий дефолт 8.0 / убыток)
  MG5 build_bad_raises      — build_product(markup=0.5) → ValueError с «markup» (не тихая цена)
  MG6 build_ok_backcompat   — build_product(markup=None) и (markup=8.0) → ОДНА и та же цена ×8
  MG7 cycle1_fail_bad_markup — node_build битого манифеста → FAIL, имя поля + магазина
  MG8 cycle1_pass_valid     — node_build валидного markup → гейт НЕ мешает (PASS, пустая партия)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_film_cards_v1 as FC      # noqa: E402
import ymarket_cycle1_v1 as C1         # noqa: E402

# Минимальный валидный донор-объект (article/name/cost нужны build_product до resolve_markup).
_DONOR = {"pid": "MG-TEST-PID", "article": "STRETCH-MG-777", "name": "Тестовая плёнка 50см×100м",
          "cost": 100.0}


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def mg1_none_default():
    m, err = FC.resolve_markup(None)
    return m == FC.MARKUP == 8.0 and err is None, (
        f"resolve_markup(None)= {m}, err={err} — модульная MARKUP {FC.MARKUP} (до проводки так же)")


def mg2_numeric_ok():
    ok_all, detail = True, []
    for v, want in ((8.0, 8.0), ("12", 12.0), (1.5, 1.5)):
        m, err = FC.resolve_markup(v)
        ok = m == want and err is None
        ok_all &= bool(ok)
        detail.append(f"{v!r}→{m}")
    return ok_all, " · ".join(detail) + " (>1 число/строка-число — как есть)"


def mg3_boolean_rejected():
    ok_all, detail = True, []
    for v in (True, False):
        m, err = FC.resolve_markup(v)
        ok = m is None and err is not None and "boolean" in err
        ok_all &= bool(ok)
        detail.append(f"{v!r}→err")
    return ok_all, " · ".join(detail) + " (true==1.0 раньше давал цену == закупку — убыток)"


def mg4_falsy_rejected():
    ok_all, detail = True, []
    for v in (0, 1, 0.5, "", "abc", "0"):
        m, err = FC.resolve_markup(v)
        ok = m is None and err is not None and "markup" in err
        ok_all &= bool(ok)
        detail.append(f"{v!r}→err")
    return ok_all, " · ".join(detail) + " (0/1/0.5/пусто/не-число → ошибка, НЕ тихий дефолт 8.0)"


def mg9_nonfinite_rejected():
    # #14-residual: nan/inf ПРОСКАКИВАЛИ `mult <= 1.0` (сравнение с nan ложно) и падали сырым
    # ValueError/OverflowError в round() глубоко в билдере. Реальный манифест это даёт:
    # json.loads("1e400")→inf, строка "nan"→float("nan"). Теперь → чистая markup-ошибка.
    ok_all, detail = True, []
    for v in (float("nan"), float("inf"), float("-inf"), "nan", "1e400", 1e400):
        m, err = FC.resolve_markup(v)
        ok = m is None and err is not None and "markup" in err and "конечн" in err
        ok_all &= bool(ok)
        detail.append(f"{v!r}→err")
    # и build_product не даёт сырого исключения round-а — ValueError с причиной markup
    for v in (float("nan"), float("inf"), 1e400):
        try:
            FC.build_product(_DONOR, {}, 0, markup=v)
            clean = False
        except ValueError as e:
            clean = "markup" in str(e) and "конечн" in str(e)
        except OverflowError:
            clean = False
        ok_all &= bool(clean)
        detail.append(f"build({v!r})→ValueError(markup)" if clean else f"build({v!r})→НЕ чисто!")
    return ok_all, " · ".join(detail) + " (nan/inf → чистый markup-FAIL, не сырой round-крэш)"


def mg5_build_bad_raises():
    ok_all, detail = True, []
    for v in (0.5, True, 0, ""):
        try:
            FC.build_product(_DONOR, {}, 0, markup=v)
            raised = False
        except ValueError as e:
            raised = "markup" in str(e)
        ok_all &= bool(raised)
        detail.append(f"{v!r}→ValueError" if raised else f"{v!r}→НЕ кинул!")
    return ok_all, " · ".join(detail) + " (битый markup — громко, не тихая цена ≤ закупки)"


def mg6_build_ok_backcompat():
    p_none = FC.build_product(_DONOR, {}, 0, markup=None)
    p_num = FC.build_product(_DONOR, {}, 0, markup=8.0)
    ok = (p_none is not None and p_num is not None
          and p_none["price"] == p_num["price"] == round(100.0 * 8.0, 0)
          and p_none["cost"] == 100.0)
    return ok, f"markup=None → {p_none['price']}₽ · markup=8.0 → {p_num['price']}₽ (идентично, ×8)"


def mg7_cycle1_fail_bad_markup():
    ctx = {"profile": {"slug": "test-store", "markup": "abc"}, "raw_donor": []}
    r = C1.node_build(ctx, dry=True, commit=False)
    ok = (r.get("verdict") == "FAIL" and "test-store" in r.get("note", "")
          and "markup" in (r.get("note", "") or "").lower()
          and r.get("evidence", {}).get("field") == "markup")
    return ok, f"verdict={r.get('verdict')} · {r.get('note')} (манифест «test-store»: марка бита → FAIL ДО действий)"


def mg8_cycle1_pass_valid():
    # markup НЕ задан / валиден → гейт не мешает: node_build идёт дальше и на пустой партии
    # честно возвращает PASS (0 собрано), не FAIL из-за гейта. (Путь: гейт = `if merr: return FAIL`.)
    ctx = {"profile": {"slug": "test-store", "markup": 8.0}, "raw_donor": []}
    r = C1.node_build(ctx, dry=True, commit=False)
    ok = r.get("verdict") == "PASS" and "0" in str(r.get("evidence", {}).get("n"))
    return ok, f"verdict={r.get('verdict')} · {r.get('note')} (валидный markup → гейт молчит, партия идёт)"


def mg10_huge_jsonint_overflow():
    # #16-residual: json.loads('1'+'0'*400) даёт ОГРОМНЫЙ Python-int (валидный JSON-integer);
    # float() такого int кидает OverflowError (НЕ ValueError) → раньше сырой крэш resolve_markup
    # и build_product. Теперь → чистая markup-ошибка (битый манифест, а не авария).
    ok_all, detail = True, []
    for v in (int("1" + "0" * 400), int("9" * 400), 10**400):
        m, err = FC.resolve_markup(v)
        good = m is None and err is not None and "markup" in err
        ok_all &= bool(good)
        detail.append(f"{str(v)[:9]}…→err")
    for v in (int("1" + "0" * 400),):
        try:
            FC.build_product(_DONOR, {}, 0, markup=v)
            clean = False
        except ValueError as e:
            clean = "markup" in str(e)
        except OverflowError:
            clean = False
        ok_all &= bool(clean)
        detail.append(f"build({str(v)[:9]}…)→ValueError(markup)" if clean else "build→НЕ чисто!")
    return ok_all, " · ".join(detail) + " (огромный int-markup → чистый FAIL, не OverflowError)"


def mg11_build_cost_nonfinite_skipped():
    # #16: #14 закрыл канал markup, но та же коррупция (nan/inf) бьёт по ЗАКУПКЕ донора: nan<=0
    # ложно → сырой round-крэш в билдере. Теперь строка с не-конечной/нечестной закупкой честно
    # ПРОПУСКАЕТСЯ (None), как строка без article/name, — партия «не собрана», не сломана.
    ok_all, detail = True, []
    for c in (float("nan"), float("inf"), "nan", "1e400", 1e400, "abc"):
        don = {"pid": "MG-X", "article": "STRETCH-MG-88", "name": "Тестовая плёнка",
               "cost": c}
        try:
            p = FC.build_product(don, {}, 0)
            good = p is None
        except Exception as e:
            good = False
            detail.append(f"cost={c!r}→{type(e).__name__}: {e}")
        ok_all &= bool(good)
        if good:
            detail.append(f"cost={c!r}→skip")
    # контроль: валидная закупка по-прежнему собирается
    try:
        p = FC.build_product(_DONOR, {}, 0)
        ok_all &= p is not None and p["price"] == 800
        detail.append("cost=100→OK ×8")
    except Exception as e:
        ok_all = False
        detail.append(f"cost=100 → {type(e).__name__}: {e}")
    return ok_all, " · ".join(detail) + " (битая закупка → честный пропуск строки, не крэш)"


def mg12_build_subruble_margin_skipped():
    # #16-residual: markup чуть >1 (1.0000001) ВАЛИДЕН по гейту `>1`, но копеечная маржа теряется
    # в round() → цена продажи == закупке (заведомый убыток после издержек, P1). Раньше такой
    # продукт СТРОИЛСЯ с ценой == закупке. Теперь строка честно пропускается, как для битой закупки.
    don = {"pid": "X", "article": "STRETCH-MG-90", "name": "Тестовая плёнка", "cost": 100.0}
    ok_all, detail = True, []
    for mk in (1.0000001, 1.0000005, 1.0005):          # маржа < 0.5₽ → round съедает
        p = FC.build_product(don, {}, 0, markup=mk)
        good = p is None
        ok_all &= bool(good)
        detail.append(f"markup={mk}→skip" if good else f"markup={mk}→price={p['price']}==cost!")
    # контроль: маржа с запасом (×8) по-прежнему строится, и цена СТРОГО выше закупки
    p = FC.build_product(don, {}, 0, markup=8.0)
    ok_all &= p is not None and p["price"] == 800 and p["price"] > p["cost"]
    detail.append("markup=8→price=800>100")
    return ok_all, " · ".join(detail) + " (цена ≤ закупки не выпускается, P1)"


def mg13_build_bool_cost_skipped():
    # #19-residual: bool-закупка (JSON-поле cost=true/false) — тип-коррупция как bool-markup (#16):
    # float(True)=1.0 проходил `isfinite>0` и СТРОИЛ карточку cost=1.0 price=8 (ложная закупка:
    # true — НЕ число, а карточка «есть за 1₽» уезжала в партию). False/0/'' и так уходили в skip;
    # True теперь тоже битая закупка → честный ПРОПУСК строки (None), как для nan/inf (mg11).
    ok_all, detail = True, []
    for c in (True, False):
        don = {"pid": "X", "article": "STRETCH-MG-91", "name": "Тест", "cost": c}
        try:
            p = FC.build_product(don, {}, 0)
            good = p is None
            detail.append(f"cost={c!r}→skip" if good else f"cost={c!r}→СТРОИТ (cost={p and p.get('cost')})")
        except Exception as e:
            good = False
            detail.append(f"cost={c!r}→{type(e).__name__}: {e}")
        ok_all &= bool(good)
    try:
        p = FC.build_product(_DONOR, {}, 0)
        ok_all &= p is not None and p["price"] == 800
        detail.append("cost=100→OK ×8")
    except Exception as e:
        ok_all = False
        detail.append(f"cost=100 → {type(e).__name__}: {e}")
    return ok_all, " · ".join(detail) + " (bool-закупка → честный пропуск, не карточка cost=1)"


def mg14_dims_garbage_no_weight_dimensions():
    # #21 (F7): габариты (length/width/height/weight из донора) шли в weightDimensions через сырой
    # float()/фильтры — одно bool/nan/inf/10**400/≤0/None в ЛЮБОМ поле делало карточку с ЛОЖНЫМИ
    # габаритами (JSON height=true → «высота 1.0» вместо честного отказа; вес донора НЕ выдумываем).
    # Теперь: НЕ все 4 габарита честные конечные >0 → weightDimensions просто НЕ кладётся (продукт
    # собирается без ложных размеров, партия жива). Валидные 4 → точный dict.
    valid = {"length": 100.0, "width": 10.0, "height": 10.0, "weight": 1.0}
    p = FC.build_product(dict(_DONOR, **valid), {}, 0)
    if not (p is not None and p.get("weightDimensions") == valid):
        return False, f"валидные габариты → {p and p.get('weightDimensions')} (ждём {valid})"
    for k, bad in (("length", True), ("width", "abc"), ("height", float("nan")),
                   ("weight", 0), ("length", 10 ** 400), ("width", float("inf")),
                   ("height", None), ("weight", -3)):
        d = dict(_DONOR, **valid)
        d[k] = bad
        try:
            q = FC.build_product(d, {}, 0)
        except Exception as e:
            return False, f"dims[{k}]={bad!r} → {type(e).__name__}: {e} (ждём продукт БЕЗ габаритов)"
        if q is None or "weightDimensions" in q:
            return False, f"dims[{k}]={bad!r} → продукт={q is not None}, weightDimensions ЕСТЬ (ждём без)"
    # контроль: габаритов вовсе нет → продукт как раньше, без ключа
    q = FC.build_product(_DONOR, {}, 0)
    if q is None or "weightDimensions" in q or q["price"] != 800:
        return False, f"без габаритов → продукт {q is not None}, ключ есть? (ждём 800 без weightDimensions)"
    return True, "валидные 4 → точные габариты; любое битое поле / их отсутствие → продукт жив БЕЗ ложных размеров"


def mg15_build_nonstr_name_skipped():
    # #23: имя донора — только ТЕКСТ. str()-коэрсия лепила в ЗАГОЛОВОК карточки bool True → 'True',
    # nan → 'nan', 10**400 → 401-значное число, [1,2] → '[1, 2]': тип-мусор (как bool-cost #19) уезжал
    # в ПУБЛИЧНОЕ имя 1-в-1 витрины. Не-str имя → НЕ имя → честный пропуск строки, как строка без
    # article/name (не собранная, а НЕ сломанная партия). Строка (вкл. числоподобную «123») — текст,
    # собирается 1-в-1 как раньше.
    ok_all, detail = True, []
    for bad in (True, False, float("nan"), float("inf"), 10 ** 400, [1, 2], 123, -7, 0.0):
        don = {"pid": "X", "article": "STRETCH-MG-92", "name": bad, "cost": 100.0}
        try:
            p = FC.build_product(don, {}, 0)
            good = p is None
            detail.append(f"name={bad!r}→skip" if good else f"name={bad!r}→СТРОИТ (name={p and p['name']!r})")
        except Exception as e:
            good = False
            detail.append(f"name={bad!r}→{type(e).__name__}: {e}")
        ok_all &= bool(good)
    # контроль: настоящее строковое имя (вкл. числоподобное «123») собирается 1-в-1, цена прежняя
    p = FC.build_product(_DONOR, {}, 0)
    q = FC.build_product(dict(_DONOR, name="123"), {}, 0)
    if not (p is not None and p["price"] == 800 and q is not None and q["name"] == "123"):
        ok_all = False
        detail.append(f"контроль: str-name → {p is not None} price={p and p.get('price')}, "
                      f"'123' → {q and q.get('name')!r}")
    else:
        detail.append("контроль: текст-имя собирается 1-в-1")
    return ok_all, " · ".join(detail) + " (не-str имя → честный пропуск, мусор в заголовок не идёт)"


TESTS = [
    ("MG1 none_default", mg1_none_default),
    ("MG2 numeric_ok", mg2_numeric_ok),
    ("MG3 boolean_rejected", mg3_boolean_rejected),
    ("MG4 falsy_rejected", mg4_falsy_rejected),
    ("MG5 build_bad_raises", mg5_build_bad_raises),
    ("MG6 build_ok_backcompat", mg6_build_ok_backcompat),
    ("MG7 cycle1_fail_bad_markup", mg7_cycle1_fail_bad_markup),
    ("MG8 cycle1_pass_valid", mg8_cycle1_pass_valid),
    ("MG9 nonfinite_rejected", mg9_nonfinite_rejected),
    ("MG10 huge_jsonint_overflow", mg10_huge_jsonint_overflow),
    ("MG11 build_cost_nonfinite_skipped", mg11_build_cost_nonfinite_skipped),
    ("MG12 build_subruble_margin_skipped", mg12_build_subruble_margin_skipped),
    ("MG13 build_bool_cost_skipped", mg13_build_bool_cost_skipped),
    ("MG14 dims_garbage_no_weight_dimensions", mg14_dims_garbage_no_weight_dimensions),
    ("MG15 build_nonstr_name_skipped", mg15_build_nonstr_name_skipped),
]


def main():
    print("🎯 ПРИЁМКА · ВОРОТА МАНИФЕСТ-MARKUP (#14: битый markup → громко, не тихая цена; 0₽)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<24} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Ворота целы: коррупция markup манифеста ловится громко ДО сборки, "
              "валидное (вкл. None-дефолт) — обратносовместимо, RUBICON цел.")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

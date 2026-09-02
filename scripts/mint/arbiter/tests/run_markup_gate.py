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


TESTS = [
    ("MG1 none_default", mg1_none_default),
    ("MG2 numeric_ok", mg2_numeric_ok),
    ("MG3 boolean_rejected", mg3_boolean_rejected),
    ("MG4 falsy_rejected", mg4_falsy_rejected),
    ("MG5 build_bad_raises", mg5_build_bad_raises),
    ("MG6 build_ok_backcompat", mg6_build_ok_backcompat),
    ("MG7 cycle1_fail_bad_markup", mg7_cycle1_fail_bad_markup),
    ("MG8 cycle1_pass_valid", mg8_cycle1_pass_valid),
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

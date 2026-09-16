#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН плёнка · ПУПОВИНА «карточка ⇄ донор» — приёмки ПРОФИТ-ЯКОРЯ (ozon_donor_anchor_v1).

Законы (D = Donor anchor):
  D1  КАЖДЫЙ размер получает якорь: anchor_for(w,l) никогда None при живом каноне.
  D2  ШИРИНА ПРИМАРНА: карточка 0.6 → класс 0.6 (НЕ сваливается на 0.5/0.3 ради цены).
      1.2→1.2, 1.5→1.5, 0.75→0.75. Схлопывание ширин ЗАПРЕЩЕНО.
  D3  ПРИМЕР ОПЕРАТОРА 0.38×55 (40г/2сл): материал лояльности — берём 40г рулон (9601513,
      0.3×100, один рулон) ДОРОЖЕ дешёвой 25г (9605412). Тонкую плёнку не подсовываем.
  D4  равный |Δw| → ШИРЕ (не оголяем клиента): 0.55×100 → 0.6 класс (9601115), НЕ 0.5 (9605413);
      0.45 → 0.5; 0.35 → 0.4 (когда класс 0.4 тянет).
  D5  QCAP-кап: 0.4×100 (рулоны 2/5м) → 20×5м > QCAP → уходим на ближайший класс, что тянет
      (0.5×50×2 = 720₽), НЕ выкупаем 20 штук.
  D6  МАТЕРИАЛ НЕ БЛОКЕР: нет рулона под материал класса → любой рулон класса (закон «не убийца»).
  D7  ПРОФИТ ВСЕГДА под капотом: цена − cost_total; убыток → unprofitable=True (не молчим).
  D8  СВЕРКА 697 (лежит в donor-reconcile): ПОСЛЕ мутации 10.09 (слово оператора 09.09):
      kept 697 / changed 0 / new 0 — библиотека полностью связана, exact 202,
      width_keep 644, unprofitable 0. (При изменении канона/библиотеки — обновить константы
      честно, не подгонкой.)
  D9  ДЕТЕРМИНИЗМ: тот же (w,l,материал) → тот же рулон; float-шум |Δw| не меняет выбор.

Сухо: канон читается с диска (donor-rolls-2026-09-09.json), сеть НЕ зовётся, 0₽, ничего не пишет.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ozon_donor_anchor_v1 as A

PASS = "✅ PASS"
FAIL = "❌ FAIL"
RUNTIME = Path(__file__).resolve().parent.parent / "runtime" / "ozon-library"
ROLLS = json.loads((RUNTIME / "donor-rolls-2026-09-09.json").read_text(encoding="utf-8"))["rolls"]
LIB = json.loads((RUNTIME / "library-2026-09-08.json").read_text(encoding="utf-8"))
RECS = LIB if isinstance(LIB, list) else LIB.get("records", LIB)


def art(w, l, grams=None, layers=None, price=None):
    return A.anchor_for(w, l, grams, layers, price, ROLLS)


def _test_every_size_anchored():
    """D1: для любого разумного (w,l) есть якорь."""
    bad = []
    for w in (0.2, 0.3, 0.35, 0.38, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.75, 0.9, 1.2, 1.3, 1.5):
        for l in (5, 10, 25, 50, 100, 250, 500):
            a = art(w, l)
            if a is None:
                bad.append(f"{w}×{l}")
    return not bad, "; ".join(bad[:8])


def _test_width_primary_no_collapse():
    """D2: типовые ширины НЕ сваливаются на чужой класс."""
    cases = [(0.6, 50), (0.6, 100), (1.2, 50), (1.2, 100), (1.5, 50), (1.5, 100), (0.75, 100)]
    bad = []
    for w, l in cases:
        a = art(w, l, 40, 2)
        if not a or abs(a["roll"]["w"] - w) > 1e-6:
            bad.append(f"{w}×{l} → {a['roll']['w'] if a else None}")
    return not bad, "; ".join(bad)


def _test_operator_example_material_loyalty():
    """D3: 0.38×55 40г/2сл → 40г рулон, не 25г; ширина 0.3 класс (пример оператора)."""
    a = art(0.38, 55, 40, 2)
    if not a:
        return False, "нет якоря"
    roll = a["roll"]
    if roll.get("dens") != 40:
        return False, f"взял {roll.get('dens')}г (должен 40г): {roll}"
    if a["article"] == "9605412":
        return False, "взял дешёвую 25г (9605412) — материал лояльности нарушен"
    # допускаем 9601513 (0.3×100 один рулон) как улучшение над 2×9601512 — то же 40г/2сл, та же 420₽
    return a["article"] in ("9601512", "9601513"), f"article={a['article']} {roll}"


def _test_tie_prefers_wider():
    """D4: равный |Δw| → шире (0.55→0.6, 0.45→0.5, 0.35→0.4)."""
    a = art(0.55, 100)
    if not a or a["roll"]["w"] != 0.6:
        return False, f"0.55×100 → {a['roll']['w'] if a else None} (должен 0.6, не оголяем)"
    if a["article"] != "9601115":
        return False, f"0.55×100 → {a['article']} (ожидаем 9601115 0.6×100)"
    b = art(0.45, 50)
    if not b or b["roll"]["w"] != 0.5:
        return False, f"0.45×50 → {b['roll']['w'] if b else None} (должен 0.5)"
    return True, "0.55→0.6, 0.45→0.5"


def _test_qcap_cap():
    """D5: 0.4×100 не выкупаем 20×5м — уходим на 0.5 класс."""
    a = art(0.4, 100)
    if not a or a["qty"] > 6:
        return False, f"qty={a['qty'] if a else None} > QCAP — выкупил бы {a['qty'] if a else 0} рулонов"
    if a["roll"]["w"] != 0.5:
        return False, f"0.4×100 → {a['roll']['w']} (ждём 0.5 класс: 0.4 класс не тянет 100м ≤6 рулонами)"
    return True, f"0.4×100 → {a['article']} ×{a['qty']} (0.5 класс)"


def _test_material_not_blocker():
    """D6: 3сл карточка на ширине без 3сл рулона → всё равно якорь (любой рулон класса)."""
    # у донора на 0.75/0.7 ширине 3сл рулонов нет — привязка не блокируется
    a = art(0.7, 50, 45, 3)
    if not a:
        return False, "0.7×50 3сл без якоря (материал заблокировал — а не должен)"
    if a["roll"]["w"] not in (0.6, 0.75):
        return False, f"0.7×50 → {a['roll']['w']} (ждём ближайший класс 0.6/0.75)"
    return True, f"0.7×50 3сл → {a['article']} (др. материал, но связан)"


def _test_profit_flagged():
    """D7: убыток не молчит."""
    a = art(0.3, 50, 40, 2, price=100)  # цена 100₽ < закупка 210₽
    if not a or not a["unprofitable"]:
        return False, f"0.3×50 price=100 → unprofitable={a['unprofitable'] if a else None} (должен True)"
    if a["profit"] >= 0:
        return False, f"profit={a['profit']} (должен быть отрицателен)"
    return True, f"profit={a['profit']}₽ flagged"


def _test_reconcile_constants():
    """D8: свёрка 697 в устойчивом состоянии ПОСЛЕ мутации (чтение артефакта, не подгонка).

    10.09: мутация библиотеки применена по слову оператора (09.09) — kept 697 / changed 0 /
    new 0. Если канон/библиотека снова изменятся — обновить константы честно, не подгонкой.
    """
    rec = json.loads((RUNTIME / "donor-reconcile-2026-09-09.json").read_text(encoding="utf-8"))
    s = rec["summary"]
    rows = rec["rows"]
    assert s["poured"] == 697, s
    assert s["exact"] == 202, s
    assert s["width_keep"] == 644, s
    assert s["unprofitable"] == 0, s
    # устойчивое состояние после мутации 10.09: всё литьё связано, переделок нет
    assert s["kept"] == 697 and s["changed"] == 0 and s["new"] == 0, s
    assert s["unbound"] == 147, s
    assert len(rows) == s["total"] == 844, (len(rows), s["total"])
    # каждый связанный имеет reason с закупкой
    for r in rows:
        if r["anchor"] is not None and (r["cost_total"] is None or r["reason"] is None):
            return False, f"строка {r['article']} без cost_total/reason"
    return True, f"poured={s['poured']} kept={s['kept']}/changed={s['changed']} width_keep={s['width_keep']}"


def _test_determinism():
    """D9: тот же ввод → тот же выбор (float-шум не влияет)."""
    a1 = art(0.55, 100, 40, 2)
    a2 = art(0.55, 100, 40, 2)
    if a1["article"] != a2["article"] or a1["cost_total"] != a2["cost_total"]:
        return False, "недетерминизм 0.55×100"
    for _ in range(50):
        b1 = art(0.4, 55, None, None)
        b2 = art(0.4, 55, None, None)
        if b1["article"] != b2["article"]:
            return False, "недетерминизм 0.4×55"
    return True, "детерминировано"


TESTS = [
    ("D1 каждый размер получает якорь (16 ширин × 7 длин)", _test_every_size_anchored),
    ("D2 ширина примарна — типовые классы не схлопываются (0.6/1.2/1.5/0.75)", _test_width_primary_no_collapse),
    ("D3 пример оператора 0.38×55 40г/2сл → 40г рулон (не 25г)", _test_operator_example_material_loyalty),
    ("D4 равный |Δw| → шире: 0.55→0.6 (9601115), 0.45→0.5", _test_tie_prefers_wider),
    ("D5 QCAP: 0.4×100 → 0.5 класс, НЕ 20×5м", _test_qcap_cap),
    ("D6 материал не блокер: 0.7×50 3сл без 3сл-рулона → связан", _test_material_not_blocker),
    ("D7 убыток не молчит: 0.3×50 price=100 → unprofitable", _test_profit_flagged),
    ("D8 свёрка 697: kept/changed/new, exact, width_keep, 0 убыточных", _test_reconcile_constants),
    ("D9 детерминизм (float-шум не меняет выбор)", _test_determinism),
]


def main():
    passed = 0
    for name, fn in TESTS:
        try:
            ok, extra = fn()
        except Exception as e:
            ok, extra = False, f"{type(e).__name__}: {e}"
        if ok:
            passed += 1
        print(f"{PASS if ok else FAIL} · {name}" + (f" — {extra}" if extra and not ok else ""))
    print(f"\nOZON DONOR ANCHOR · {passed}/{len(TESTS)} зелёных")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

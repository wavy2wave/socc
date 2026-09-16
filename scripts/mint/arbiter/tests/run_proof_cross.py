#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — КРОСС-СВЕРКА «ДОКАЗАННО ЖИВЫХ» (ymarket_proof_cross_v1). Сухо, 0₽, герметично.

Оператор («сделай чтобы система законно не врала»): панели печатали «доказанно живых: 0» из пустой
само-модели суточного, хотя леджер ЦИКЛ-1 доказывает живые карточки (last_verified PASS) в кабинете
atlas-express-film. Приёмка проверяет, что новый орган ЧЕСТНО сводит это:

  PC1 pass_goods/by_store   — считает ТОЛЬКО СВЕРКА-PASS (не считает FAIL/без-записи/не-PASS).
  PC2 store-подпись          — известный slug получает имя (тест «Атлас»), строки остаются у своего
        кабинета; кабинеты не сливаются в одно число.
  PC3 журнал≠леджер          — суточный журнал «0» + леджер «4» → блок показывает ОБА, честно
        разграничивая («это его кабинет», числа не складываются) — «0» больше не читается как
        общесистемная правда.
  PC4 деградад честен        — леджер не читается → «НЕИЗВЕСТНО (не читается)», нули не выдумываем;
        леджер пуст (журнал молчит) → честное «0: леджер ЦИКЛ-1 пуст» — это правда, не ложь,
        render() всегда возвращает правдивую строку (None не нужен: «0» при пустом леджере = правда).
  PC5 журнал сам себя не прячет — леджер 0, журнал рисует «0» → блок помечает, что 0 — суточный,
        и числа не складываются.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
for p in (str(ARB),):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_proof_cross_v1 as X    # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _goods(oid, slug, verdict="PASS", ts=None):
    g = {"offer_id": oid, "article": oid, "store_slug": slug}
    if verdict is not None:
        g["last_verified"] = {"verdict": verdict, "ts": ts or "2026-09-03T13:27:40+00:00"}
    return g


def _journal(last_v):
    """Одна строка журнала суточного с cards_live_verified=last_v (или без него)."""
    k = {"cards_tracked": 7, "cards_live": 7, "cards_errored": 7}
    if last_v is not None:
        k["cards_live_verified"] = last_v
    return [{"ts": "2026-09-03T18:32:04+00:00", "date": "2026-09-03", "kpis": k}]


def pc1_only_svverka_pass():
    lib = {"goods": {
        "a": _goods("ARB-1", "atlas-express-film", "PASS", "2026-09-03T13:27:40+00:00"),
        "b": _goods("ARB-2", "atlas-express-film", "FAIL", "2026-09-03T13:28:00+00:00"),
        "c": _goods("ARB-3", "atlas-express-film", None),            # вообще без last_verified
        "d": _goods("ARB-4", "boevoj-slug", "PASS", "2026-09-03T14:00:00+00:00"),
        "e": {"offer_id": "ARB-5"},                                  # не goods-структура
    }}
    by, _ = X.by_store(lib)
    ok = (by.get("atlas-express-film", {}).get("n") == 1
          and by.get("boevoj-slug", {}).get("n") == 1 and len(by) == 2)
    return ok, f"atlas={by.get('atlas-express-film',{}).get('n')} boevoj={by.get('boevoj-slug',{}).get('n')} (FAIL/без-записи НЕ считаются)"


def pc2_store_labels():
    lib = {"goods": {
        "a": _goods("ARB-1", "atlas-express-film", "PASS"),
        "b": _goods("ARB-2", "unknown-store", "PASS"),
    }}
    by, _ = X.by_store(lib)
    txt = X.render(journal_rows=[], library_doc=lib)
    ok = (X.store_label("atlas-express-film") == "тест «Атлас»"
          and "тест «Атлас» (atlas-express-film): 1" in txt
          and "unknown-store: 1" in txt
          # обе строки несут свою кабинетную подпись (не сливаются в одно безымянное число):
          and "• тест «Атлас» (atlas-express-film): 1" in txt
          and "• unknown-store: 1" in txt)
    return ok, f"txt={txt!r}"


def pc3_journal_zero_vs_ledger_four():
    lib = {"goods": {f"ARB-{i}": _goods(f"ARB-{i}", "atlas-express-film", "PASS",
                                          f"2026-09-03T13:27:{40+i}+00:00") for i in range(4)}}
    txt = X.render(journal_rows=_journal(0), library_doc=lib)
    need = ["4", "тест «Атлас» (atlas-express-film)", "0", "не складываются"]
    missing = [n for n in need if n not in txt]
    return (not missing), f"недостаёт: {missing or '—'} · txt={txt!r}"


def pc4_no_fake_zero():
    # (а) леджер не читается (doc с load_error как возвращает load_library) → честно «не читается»,
    #     нулей не выдумываем, НО журнал 0 помечаем как суточный (не леджер).
    err = {"load_error": "FileNotFoundError: нет файла"}
    by, doc = X.by_store(err)
    txt_a = X.render(journal_rows=_journal(0), library_doc=err)
    ok_a = (len(by) == 0 and doc.get("load_error") and "не читается" in txt_a
            and "суточный журнал рисует 0" in txt_a)
    # (б) леджер пуст И журнал «0» не рисует (журнала нет) → честное «0: леджер пуст» —
    #     правда (ни одной СВЕРКА PASS), render не молчит и не возвращает None.
    txt_b = X.render(journal_rows=[], library_doc={"goods": {}})
    ok_b = (txt_b is not None and "леджер ЦИКЛ-1 пуст" in txt_b and "0" in txt_b)
    # (в) леджер пуст + журнал 0 → «0 — леджер пуст» + помечаем, что рисует 0 суточный журнал.
    txt_c = X.render(journal_rows=_journal(0), library_doc={"goods": {}})
    ok_c = (txt_c is not None and "леджер ЦИКЛ-1 пуст" in txt_c
            and "суточный журнал рисует 0" in txt_c)
    return (ok_a and ok_b and ok_c), f"нечитаем={ok_a} пуст-без-журнала={ok_b} пуст+0={ok_c}"


def pc5_journal_cabinet_label():
    # Суточный журнал «0», леджер пуст → блок обязан сказать, что «0 рисует» журнал СВОЕГО кабинета
    # (само-модель), и числа леджера с журналом не складываются — «0» не общесистемное доказательство.
    txt = X.render(journal_rows=_journal(0), library_doc={"goods": {}})
    ok = ("0" in txt and "суточный журнал рисует 0" in txt and "не складываются" in txt)
    return ok, f"txt={txt!r}"


def _run():
    tests = [("PC1 only_svverka_pass", pc1_only_svverka_pass),
             ("PC2 store_labels", pc2_store_labels),
             ("PC3 journal0_vs_ledger4", pc3_journal_zero_vs_ledger_four),
             ("PC4 no_fake_zero", pc4_no_fake_zero),
             ("PC5 journal_cabinet_label", pc5_journal_cabinet_label)]
    fails = 0
    for name, fn in tests:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(f"  {_passed(ok)} {name:<22} {detail}")
        fails += 0 if ok else 1
    print(f"\nКРОСС-СВЕРКА «доказанно живых»: {len(tests) - fails}/{len(tests)} зелёных")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run())

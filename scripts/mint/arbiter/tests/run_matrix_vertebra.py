#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — ПОЗВОНОК-МАТРИЦА (движок ЦИКЛ-1 ПИШЕТ матрицу). Сухо, 0₽, без сети, герметично.

Оператор 03.09 («оживи позвонок-матрицу»): движок ЦИКЛ-1 начинает ПИСАТЬ матрицу —
узел цепочки = ensure+set_status(собран/залит/на-витрине) с offer_id; живые ARB-карточки
становятся позвонками «на-витрине». Это шов ЯМ-ЦИКЛа: ОДИН товар идёт через все циклы,
матрица — «позвонок» этой крови (кандидат→собран→залит→сверен→на-витрине→продан).

Пишем ТОЛЬКО во временный стор (env YM_MATRIX_PATH / YM_LIBRARY_PATH) — канон отчётов
не трогаем. Ключевое: матрица растёт ТОЛЬКО из реальных событий (LB1: dry пишет НИЧЕГО),
поэтому _sync_matrix зовётся движком только под `not dry AND commit`.

  MX1 auto_sync_full_to_vitrine — полный живой ход (СБОРКА+ЗАЛИВ+СВЕРКА PASS) → строка
        поднимается до «на-витрине» + offer_id + ean + рыночная категория.
  MX2 partial_fill_stops_at_zalit — цепь остановлена после ЗАЛИВ (ВИТРИНА FAIL) → «залит»
        + offer_id (НЕ «на-витрине»: живое не подтверждено).
  MX3 never_downgrade            — карточка уже «на-витрине», частичный новый ход (ЗАЛИВ
        FAIL) → НЕ разжалуется вниз (M4), без исключения.
  MX4 gate_live_only             — _sync_matrix/_sync_library в движке живут ТОЛЬКО под
        `if not dry and commit:` (текстовый закон, как A2); нет PASS-узлов → не пишем.
  MX5 catchup_from_library       — карточки, прожившие цикл ДО хука, поднимает matrix_catchup
        из библиотеки (last_verified=PASS — реальное чтение витрины); FAIL-товар не трогаем.
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
for p in (str(ARB),):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_cycle1_v1 as C1      # noqa: E402
import ymarket_matrix_v1 as mx      # noqa: E402
import ymarket_library_v1 as lib    # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


class _Sandbox:
    """Песочница: временный каталог, env YM_MATRIX_PATH+YM_LIBRARY_PATH → туда. Выход — вернули."""
    def __init__(self):
        self._tmp = tempfile.mkdtemp(prefix="mx_")
        self._saved = {}
        self.dir = self._tmp

    def __enter__(self):
        for var in ("YM_MATRIX_PATH", "YM_LIBRARY_PATH"):
            self._saved[var] = os.environ.get(var)
        os.environ["YM_MATRIX_PATH"] = str(Path(self._tmp) / "matrix.json")
        os.environ["YM_LIBRARY_PATH"] = str(Path(self._tmp) / "library.json")
        return self

    def __exit__(self, *exc):
        for var, val in self._saved.items():
            if val is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = val
        return False


def _ctx(prod):
    return {"profile": {"slug": "atlas-express-film", "builder_slug": "puzyrkovaya-plenka",
                        "donor_category": "vozdushno-puzyrkovaya-plenka"},
            "prods": [prod], "provider": None}


def _prod(sku="ARB-77700001", article="9607777", ean="4607777777777", name=None):
    return {"sku": sku, "name": name or f"Плёнка ВПП 0,3×100 м, двухслойная (арт {article})",
            "article": article, "barcode": ean, "pid": "777",
            "cost": 150.0, "price": 1200.0, "vendor": "Без бренда",
            "pictures": [], "_spec": {"толщина": "2 слоя"}}

# чтобы _sync_matrix в MX1/MX2 реально что-то поднял, надо чтобы ensure дал ключ:
# имя с цифрами → норм-ключ строится, плюс article задан — дедуп по статье.


def mx1_auto_sync_full_to_vitrine():
    with _Sandbox() as sb:
        prod = _prod()
        results = [{"node": "СБОРКА", "verdict": "PASS"}, {"node": "ЗАЛИВ", "verdict": "PASS"},
                   {"node": "ВИТРИНА", "verdict": "PASS"}, {"node": "СВЕРКА", "verdict": "PASS"}]
        r = C1._sync_matrix(_ctx(prod), results, "mx1")
        doc = mx.load()
        rows = list((doc.get("rows") or {}).values())
        row = rows[0] if rows else {}
        ok = (r.get("ok") and r.get("n") == 1 and len(rows) == 1
              and row.get("status") == "на-витрине" and row.get("offer_id") == prod["sku"]
              and row.get("ean") == prod["barcode"] and row.get("article") == prod["article"]
              and row.get("category") == "puzyrkovaya-plenka")
        return ok, f"{r} · status={row.get('status')} offer={row.get('offer_id')} ean={row.get('ean')}"


def mx2_partial_fill_stops_at_zalit():
    with _Sandbox() as sb:
        prod = _prod()
        results = [{"node": "СБОРКА", "verdict": "PASS"}, {"node": "ЗАЛИВ", "verdict": "PASS"},
                   {"node": "ВИТРИНА", "verdict": "FAIL"}]     # цепь остановлена — СВЕРКА не шла
        r = C1._sync_matrix(_ctx(prod), results, "mx2")
        row = next(iter((mx.load().get("rows") or {}).values()), {})
        ok = (r.get("ok") and row.get("status") == "залит" and row.get("offer_id") == prod["sku"])
        return ok, f"{r} · status={row.get('status')} offer={row.get('offer_id')} (живое НЕ подтверждено)"


def mx3_never_downgrade():
    with _Sandbox() as sb:
        prod = _prod()
        full = [{"node": "СБОРКА", "verdict": "PASS"}, {"node": "ЗАЛИВ", "verdict": "PASS"},
                {"node": "СВЕРКА", "verdict": "PASS"}]
        C1._sync_matrix(_ctx(prod), full, "mx3a")               # → на-витрине
        partial = [{"node": "СБОРКА", "verdict": "PASS"}, {"node": "ЗАЛИВ", "verdict": "FAIL"}]
        try:
            r = C1._sync_matrix(_ctx(prod), partial, "mx3b")    # вниз НЕ пойдёт (M4)
            exc = None
        except Exception as e:
            exc, r = e, {}
        row = next(iter((mx.load().get("rows") or {}).values()), {})
        ok = (exc is None and r.get("ok") and row.get("status") == "на-витрине")
        return ok, f"exc={exc and type(exc).__name__} · status={row.get('status')} (не разжалован)"


def mx4_gate_live_only():
    # (а) текстовый закон: вызовы хуков в run_cycle — только под `if not dry and commit:`
    src = (ARB / "ymarket_cycle1_v1.py").read_text(encoding="utf-8")
    i_syn = src.find("        syn = _sync_library(ctx, results, hsh)")
    i_mtx = src.find("        mtx = _sync_matrix(ctx, results, hsh)")
    window = src[max(0, i_syn - 80):i_mtx]
    gate = ("if not dry and commit:" in window) and i_syn != -1 and i_mtx != -1
    # (б) без PASS-узлов — не пишем и не падаем
    with _Sandbox() as sb:
        prod = _prod()
        results = [{"node": "ДОНОР", "verdict": "PASS"}, {"node": "СВЕРКА", "verdict": "FAIL"}]
        r = C1._sync_matrix(_ctx(prod), results, "mx4")         # СБОРКА/ЗАЛИВ не PASS
        wrote = Path(os.environ["YM_MATRIX_PATH"]).exists()
        ok = gate and r.get("ok") and not wrote
        return ok, f"gate_под_dry-commit={gate} · r={r} · файл={wrote}"


def _seed_library_and_matrix(pass_ids, fail_ids):
    """Песочница: библиотека с PASS/FAIL-товарами + матрица с теми же строками на «собран»."""
    lib_doc = lib.load()
    mx_doc = mx.load()
    all_ids = pass_ids + fail_ids
    for i, oid in enumerate(all_ids):
        art = f"9607{100 + i}"
        ean = f"460{7000000 + i}"
        name = f"Плёнка ВПП 0,3×{100 + i} м, двухслойная"
        lib.upsert_card(lib_doc, oid, name=name, article=art, barcode=ean,
                        vendor="Без бренда", cost=150.0, price=1200.0,
                        category_slug="puzyrkovaya-plenka", store_slug="atlas-express-film",
                        cycle_hash="seed", donor_pid=str(100 + i))
        lib.mark_verified(lib_doc, oid, verdict="PASS" if oid in pass_ids else "FAIL",
                          store_slug="atlas-express-film", cycle_hash="seed",
                          note="СВЕРКА: витрина PUBLISHED + остатки FIT" if oid in pass_ids
                              else "цепь остановлена — не подтверждено")
        mx.ensure(mx_doc, name=name, article=art)               # позвонок на «собран»
        key = mx._find_dup(mx_doc, article=art)[0]
        mx.set_status(mx_doc, key, "собран", note="сухо собрана (посев)")
    lib.write_atomic(lib_doc)
    mx.write_atomic(mx_doc)


def mx5_catchup_from_library():
    with _Sandbox() as sb:
        pass_ids, fail_ids = ["ARB-77700001", "ARB-77700002"], ["ARB-77700003"]
        _seed_library_and_matrix(pass_ids, fail_ids)
        r = C1.matrix_catchup()
        doc = mx.load()
        rows = {(x.get("article")): x for x in (doc.get("rows") or {}).values()}
        ok = (r.get("ok") and r.get("n") == 2
              and rows["9607100"].get("status") == "на-витрине"
              and rows["9607100"].get("offer_id") == "ARB-77700001"
              and rows["9607101"].get("status") == "на-витрине"
              and rows["9607102"].get("status") == "собран")     # FAIL-товар не трогаем
        return ok, (f"{r} · PASS→на-витрине 2, FAIL-товар остался "
                    f"{rows['9607102'].get('status')} (idempotent, FAIL не ведёт вверх)")


def _run():
    tests = [("MX1 auto_sync_full_to_vitrine", mx1_auto_sync_full_to_vitrine),
             ("MX2 partial_fill_stops_at_zalit", mx2_partial_fill_stops_at_zalit),
             ("MX3 never_downgrade", mx3_never_downgrade),
             ("MX4 gate_live_only", mx4_gate_live_only),
             ("MX5 catchup_from_library", mx5_catchup_from_library)]
    fails = 0
    for name, fn in tests:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(f"  {_passed(ok)} {name:<28} {detail}")
        fails += 0 if ok else 1
    print(f"\nПОЗВОНОК-МАТРИЦА: {len(tests) - fails}/{len(tests)} зелёных")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run())

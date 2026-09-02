#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — БИБЛИОТЕКА ТОВАРОВ/КАТЕГОРИЙ (ymarket_library_v1). Сухо, 0₽, без сети.

Проверяем ЗАКОНЫ библиотеки, а не «запустилось». Каждый тест ловит конкретную ложь, которую
библиотека могла бы сказать. Пишем ТОЛЬКО во временный стор (env YM_LIBRARY_PATH) — канон отчётов
не трогаем. Ключевое: dry (live=False) пишет НИЧЕГО — библиотека растёт ТОЛЬКО из реальных событий.

  LB1  empty_store_is_empty   — нет файла → load() чистый бланк, срезы пусты (не падаем)
  LB2  dry_records_nothing    — record_cards/stock/verified(live=False) → None, файл не создан (LB1)
  LB3  upsert_needs_offerid   — upsert_card без offerId → ValueError (не выдумываем ключ)
  LB4  card_roundtrip_live    — record_cards(live=True) → запись с полями, переживает файл (LB6)
  LB5  markup_derived         — цена+закупка → markup=price/cost, не выдумываем сверх данного
  LB6  stock_event_appends    — record_stock копит события, не затирает карточку (LB7)
  LB7  merge_none_safe        — частичное обновление не затирает известные поля
  LB8  pid_from_registry      — donor_pid авто-мостится через реестр (LB3), ARB-sku pid не выдумывает
  LB9  slices_empty_on_blank  — by_category/by_cycle/by_store на пустом сторе → []
  LB10 by_cycle_cross_stock   — по хешу цикла видны и карточки, и остатки того цикла
  LB11 categories_rollup      — categories()/stats() сводят по категориям/магазинам/циклам
  LB12 failsoft_corrupt       — битый/чужой JSON → чистый бланк, спасаем goods из чужой схемы (LB5)
  LB13 dims_none_preserves    — обновление без dims НЕ стирает сохранённые габариты (LB2/LB4)
  LB14 record_cards_no_mutate — record_cards копирует entries: caller-словарь не выпиливается (LB2)
  LB15 corrupt_backup_preserves — битый канон при живой записи спасается в .corrupt-*.bak, не сожжён (LB6)
  LB16 junk_schema_read_safe  — чужой/мусорный стор → load() чистит, read-органы не падают (LB5)
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_library_v1 as lib       # noqa: E402
import ymarket_registry_v1 as reg      # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


class _Store:
    """Контекст: временный стор через env YM_LIBRARY_PATH (канон отчётов не трогаем)."""
    def __enter__(self):
        self._save = os.environ.get("YM_LIBRARY_PATH")
        self._dir = tempfile.TemporaryDirectory()
        os.environ["YM_LIBRARY_PATH"] = str(Path(self._dir.name) / "lib.json")
        return self

    def __exit__(self, *exc):
        if self._save is None:
            os.environ.pop("YM_LIBRARY_PATH", None)
        else:
            os.environ["YM_LIBRARY_PATH"] = self._save
        self._dir.cleanup()
        return False


def _p(*parts):
    return Path(os.environ["YM_LIBRARY_PATH"], *parts)


def lb1_empty_store_is_empty():
    with _Store():
        doc = lib.load()
        ok = (doc["schema"] == lib.SCHEMA and lib.all_goods(doc) == {}
              and lib.get(doc, "ARB-1") is None
              and lib.by_category(doc, "x") == [] and lib.by_cycle(doc, "h") == []
              and lib.by_store(doc, "s") == [] and lib.categories(doc) == {})
    return ok, f"бланк schema={doc['schema']} goods={lib.all_goods(doc)}"


def lb2_dry_records_nothing():
    with _Store():
        n = lib.record_cards(False, [{"offer_id": "ARB-1", "name": "Плёнка", "cost": 10, "price": 80}])
        s = lib.record_stock(False, "ARB-1", count=100, warehouse_id=2390811)
        v = lib.record_verified(False, "ARB-1", verdict="PASS")
        nofile = not _p().exists()
        ok = (n is None and s is None and v is None and nofile
              and lib.all_goods(lib.load()) == {})
    return ok, f"dry записало: card={n} stock={s} verified={v} файл_создан={not nofile}"


def lb3_upsert_needs_offerid():
    doc = lib._blank()
    bad = 0
    for empty in ("", None):
        try:
            lib.upsert_card(doc, empty, name="x")
        except ValueError:
            bad += 1
    return bad == 2, f"отказов на пустом offerId={bad}/2"


def lb4_card_roundtrip_live():
    with _Store():
        entry = {"offer_id": "ARB-12345678", "donor_pid": "1588731",
                 "name": "Плёнка 100×0,75 м", "store_slug": "atlas-express-film",
                 "cycle_hash": "abcdef1234", "builder": "film", "vendor": "Без бренда",
                 "barcode": "4607000000000", "cost": 87.5, "price": 700,
                 "category_slug": "vozdushno-puzyrkovaya-plenka", "n_photos": 4,
                 "dims": {"length": 30, "width": 25, "height": 25}}
        n = lib.record_cards(True, [entry])
        rec = lib.lookup("ARB-12345678")
        ok = (n == 1 and rec and rec["name"].startswith("Плёнка")
              and rec["price"] == 700 and rec["dims"]["length"] == 30
              and rec["events"] and rec["events"][0]["kind"] == "card")
    return ok, f"записано={n} markup={rec and rec.get('markup')} events={rec and len(rec['events'])}"


def lb5_markup_derived():
    with _Store():
        lib.record_cards(True, [{"offer_id": "ARB-1", "cost": 87.5, "price": 700}])
        lib.record_cards(True, [{"offer_id": "ARB-2", "cost": 50, "price": 50}])   # markup не считается (cost=price)
        a, b = lib.lookup("ARB-1"), lib.lookup("ARB-2")
        ok = (a["markup"] == 8.0 and b.get("markup") == 1.0)
    return ok, f"ARB-1 markup={a and a.get('markup')} (ждём 8.0)"


def lb6_stock_event_appends():
    with _Store():
        lib.record_cards(True, [{"offer_id": "ARB-1", "name": "Плёнка", "cost": 10, "price": 80}])
        lib.record_stock(True, "ARB-1", count=100, warehouse_id=2390811,
                         store_slug="atlas-express-film", cycle_hash="abcdef1234")
        lib.record_stock(True, "ARB-1", count=60, warehouse_id=2390811,
                         store_slug="atlas-express-film", cycle_hash="abcdef1234")
        rec = lib.lookup("ARB-1")
        kinds = [e["kind"] for e in rec["events"]]
        counts = [e["count"] for e in rec["events"] if e["kind"] == "stock"]
        ok = (rec["name"] == "Плёнка"            # карточка не затерта событием (LB7)
              and kinds == ["card", "stock", "stock"]
              and counts == [100, 60] and rec["updated_at"])
    return ok, f"events={kinds} counts={counts}"


def lb7_merge_none_safe():
    with _Store():
        lib.record_cards(True, [{"offer_id": "ARB-1", "name": "Плёнка", "cost": 10, "price": 80,
                                 "vendor": "Без бренда", "category_slug": "vozdushno-puzyrkovaya-plenka"}])
        # частичное обновление (только stock_count) НЕ должно затереть name/vendor/cost
        lib.record_cards(True, [{"offer_id": "ARB-1", "stock_count": 100}])
        rec = lib.lookup("ARB-1")
        ok = (rec["name"] == "Плёнка" and rec["vendor"] == "Без бренда"
              and rec["cost"] == 10 and rec["stock_count"] == 100
              and rec["category_slug"] == "vozdushno-puzyrkovaya-plenka")
    return ok, f"name={rec and rec.get('name')} vendor={rec and rec.get('vendor')} stock={rec and rec.get('stock_count')}"


def lb8_pid_from_registry():
    with _Store():
        # канон-реестр: '9603273-1' несёт pid в offerId → библиотека мостит его через реестр
        lib.record_cards(True, [{"offer_id": "9603273-1", "name": "Донор-товар"}])
        a = lib.lookup("9603273-1")
        # ARB-sku (наш, Ozon-путь) pid НЕ выдумывает (LB3): остаётся None, если не передан
        lib.record_cards(True, [{"offer_id": "ARB-777", "name": "Плёнка"}])
        b = lib.lookup("ARB-777")
        ok = (a["donor_pid"] == "9603273" and b.get("donor_pid") is None)
    return ok, f"9603273-1→pid={a and a.get('donor_pid')} ARB-777→{b and b.get('donor_pid')} (ждём None)"


def lb9_slices_empty_on_blank():
    doc = lib._blank()
    ok = (lib.by_category(doc, "x") == [] and lib.by_cycle(doc, "h") == []
          and lib.by_store(doc, "s") == [] and lib.categories(doc) == {}
          and lib.stats(doc)["articles"] == 0)
    return ok, f"срезы: by_cat={lib.by_category(doc, 'x')} stats={lib.stats(doc)}"


def lb10_by_cycle_cross_stock():
    with _Store():
        # цикл h1: карточка ARB-1 + остаток; цикл h2: только остаток по ARB-2 (карточка другая/иная)
        lib.record_cards(True, [{"offer_id": "ARB-1", "name": "Плёнка",
                                 "cycle_hash": "h1", "store_slug": "s1"}])
        lib.record_stock(True, "ARB-1", count=100, warehouse_id=1, cycle_hash="h1", store_slug="s1")
        lib.record_stock(True, "ARB-2", count=50, warehouse_id=1, cycle_hash="h2", store_slug="s1")
        doc = lib.load()
        ok = (lib.by_cycle(doc, "h1") == ["ARB-1"]
              and lib.by_cycle(doc, "h2") == ["ARB-2"]      # остаток цикла виден
              and lib.by_store(doc, "s1") == ["ARB-1", "ARB-2"])
        h1 = lib.by_cycle(doc, "h1")
        h2 = lib.by_cycle(doc, "h2")
    return ok, f"h1={h1} h2={h2}"


def lb11_categories_rollup():
    with _Store():
        lib.record_cards(True, [
            {"offer_id": "ARB-1", "name": "А", "store_slug": "s1", "cycle_hash": "h1",
             "category_slug": "cat-a"},
            {"offer_id": "ARB-2", "name": "Б", "store_slug": "s1", "cycle_hash": "h1",
             "category_slug": "cat-a"},
            {"offer_id": "ARB-3", "name": "В", "store_slug": "s2", "cycle_hash": "h2",
             "category_slug": "cat-b"},
        ])
        st = lib.stats(lib.load())
        cats = lib.categories(lib.load())
        ok = (st["articles"] == 3 and cats["cat-a"]["articles"] == 2
              and cats["cat-b"]["articles"] == 1
              and st["stores"]["s1"]["articles"] == 2 and st["stores"]["s2"]["articles"] == 1
              and st["cycles"]["h1"]["articles"] == 2 and st["cycles"]["h2"]["articles"] == 1)
    return ok, (f"articles={st['articles']} cat-a={cats.get('cat-a')} "
                f"stores={st['stores']} cycles={st['cycles']}")


def lb12_failsoft_corrupt():
    with _Store():
        p = _p()
        p.parent.mkdir(parents=True, exist_ok=True)
        # чужая схема, но с goods — спасаем содержимое, не роняемся (LB5)
        p.write_text(json.dumps({"schema": "someone.else", "goods":
                     {"ARB-1": {"offerId": "ARB-1", "donor_pid": "1", "events": []}}}),
                     encoding="utf-8")
        doc = lib.load()
        rescued = lib.get(doc, "ARB-1")
        # полностью битый JSON → чистый бланк
        p.write_text("}{ не json", encoding="utf-8")
        blank = lib.load()
        ok = (doc["schema"] == lib.SCHEMA and rescued and rescued["donor_pid"] == "1"
              and lib.all_goods(blank) == {})
    return ok, f"спасено={bool(rescued)} битый→бланк={lib.all_goods(blank) == {}}"


def lb13_dims_none_preserves():
    with _Store():
        lib.record_cards(True, [{"offer_id": "ARB-5", "name": "Плёнка",
                                 "dims": {"length": 30, "width": 25, "height": 25}}])
        # живой цикл без ОВХ у донора: карточку обновляем БЕЗ dims → габариты не стираются
        lib.record_cards(True, [{"offer_id": "ARB-5", "price": 700}])
        rec = lib.lookup("ARB-5")
        ok = rec and rec["dims"] == {"length": 30, "width": 25, "height": 25} and rec["price"] == 700
    return ok, f"dims после обновления без dims={rec and rec.get('dims')} (сохранены, LB2/LB4)"


def lb14_record_cards_no_mutate():
    with _Store():
        entry = {"offer_id": "ARB-9", "name": "Не мутируй", "cost": 10, "price": 80}
        snapshot = dict(entry)
        n = lib.record_cards(True, [entry])
        ok = (n == 1 and entry == snapshot and entry.get("offer_id") == "ARB-9"
              and lib.lookup("ARB-9") is not None)
    return ok, f"записано={n} caller.offerId после вызова={entry.get('offer_id')} (не выпилен)"


def lb15_corrupt_backup_preserves():
    with _Store():
        p = _p()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{ не json вообще", encoding="utf-8")
        n = lib.record_cards(True, [{"offer_id": "ARB-7", "name": "Плёнка", "cost": 10, "price": 80}])
        baks = sorted(p.parent.glob(p.name + ".corrupt-*.bak"))
        doc = lib.load()
        ok = (n == 1 and len(baks) == 1
              and baks[0].read_text(encoding="utf-8") == "{ не json вообще"   # битый спасён, не сожжён (LB6)
              and doc["schema"] == lib.SCHEMA and lib.get(doc, "ARB-7") is not None)
    return ok, f"записано={n} бэкап={[b.name for b in baks]} (битый канон восстановим человеком)"


def lb16_junk_schema_read_safe():
    with _Store():
        p = _p()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"schema": "someone.else", "goods": {
            "junk-1": "не-dict", "junk-2": None, "junk-3": {"events": "строка, не список"},
            "ok-1": {"offerId": "ok-1", "events": [42, "x", {"kind": "card"}],
                     "category_slug": "cat", "store_slug": "s1", "cycle_hash": "h1"},
        }}), encoding="utf-8")
        doc = lib.load()
        goods = lib.all_goods(doc)
        ok = (set(goods) == {"ok-1", "junk-3"}                     # мусор без dict-формы выброшен (LB5)
              and goods["ok-1"]["events"] == [{"kind": "card"}]    # не-dict события отфильтрованы
              and goods["junk-3"]["events"] == []
              and lib.by_category(doc, "cat") == ["ok-1"] and lib.by_store(doc, "s1") == ["ok-1"]
              and lib.by_cycle(doc, "h1") == ["ok-1"] and lib.stats(doc)["articles"] == 2)
    return ok, f"goods={set(goods)} (читатели не падают, агрегаты целы)"


TESTS = [
    ("LB1  empty_store_is_empty", lb1_empty_store_is_empty),
    ("LB2  dry_records_nothing", lb2_dry_records_nothing),
    ("LB3  upsert_needs_offerid", lb3_upsert_needs_offerid),
    ("LB4  card_roundtrip_live", lb4_card_roundtrip_live),
    ("LB5  markup_derived", lb5_markup_derived),
    ("LB6  stock_event_appends", lb6_stock_event_appends),
    ("LB7  merge_none_safe", lb7_merge_none_safe),
    ("LB8  pid_from_registry", lb8_pid_from_registry),
    ("LB9  slices_empty_on_blank", lb9_slices_empty_on_blank),
    ("LB10 by_cycle_cross_stock", lb10_by_cycle_cross_stock),
    ("LB11 categories_rollup", lb11_categories_rollup),
    ("LB12 failsoft_corrupt", lb12_failsoft_corrupt),
    ("LB13 dims_none_preserves", lb13_dims_none_preserves),
    ("LB14 record_cards_no_mutate", lb14_record_cards_no_mutate),
    ("LB15 corrupt_backup_preserves", lb15_corrupt_backup_preserves),
    ("LB16 junk_schema_read_safe", lb16_junk_schema_read_safe),
]


def main():
    print("🎯 ПРИЁМКА · БИБЛИОТЕКА ТОВАРОВ/КАТЕГОРИЙ (сухо, 0₽, без сети)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<28} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Библиотека честна: dry не пишет, не выдумывает ключ/pid, события копятся, "
              "срезы/агрегаты полны, fail-soft, RUBICON цел (0 сети/локальная запись).")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

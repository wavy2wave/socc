#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · ЗАЛИВ ИЗ ФАЙЛА (ozon_film_file_v1) — герметичные приёмки (dry, сети к Ozon НЕТ).

Законы (отражение Z-законов линии плёнки под файловый источник):
  L1  источник: канон-строки файла читаются (fail-soft → честная _error).
  L2  волна = ТОЛЬКО рулоны-в-м с размером; порядок (ширина↑, длина↑, артикул).
  L3  select_wave режет по N; N>=всех → вся партия.
  L4  карточка: can_build=True, dci=17027937/tid=97503, цена СТРОКОЙ, vat='0', EAN-13 валиден.
  L5  ЧЕСТНОСТЬ бренда: ExpressGo ПО ЗНАЧЕНИЮ (attr 85 БЕЗ dictionary_value_id — в словаре нет, не выдумываем).
  L6  материал=полиэтилен (dvid 62043 есть); цвет ТОЛЬКО из имени (чёрный→61574) — файловую колонку не копируем.
  L7  фото/габариты/аннотация из файла в карточку (1-в-1, без выдумок).
  L8  старая цена строго больше новой; old<=price / old=None → атрибут НЕ шлём.
  L9  не-рулоны (пакеты/м-одиночные) в кандидаты НЕ попадают (библиотека-только).
  L10 РУБИКОН dry: fill(dry=True) НЕ открывает сеть (create_product с dry=True commit=False).
  L11 подвязка donor из матрицы попадает в prod (донор_url/артикул), но НЕ в карточку-атрибут.
  L12 имя файла НЕ калечим (verbatim); offer_id = СИСТЕМНЫЙ код (ozon_article_v1), уник.
  L13 EAN уникален в волне (разный SKU → разный код), детерминирован, от КОДА (не от tdt).
  L14 ЧАНКИ-залив: волна >100 режется на пакеты ≤100 (кап /v3/product/import = 100/вызов), агрегат.
  L15 СИСТЕМНЫЙ АРТИКУЛ (артикул — ключ): tdt в карточку НЕ идёт — карточка несёт код VPP-… (он же
      EAN/модель); файловый артикул живёт в prod.file_article → журнал и матрица ключуются tdt, матрица не сбивается.
  L16 ЧАНКИ-остатки: stocks() режет ≤100 на вызов /v2/products/stocks (кап Ozon), агрегат.

Сухо: env-песочница (канон-строки и матрица — фикстуры tmp), сети нет, канон репо не пишется.
"""
import io
import json
import os
import sys
import tempfile
import unittest.mock as mock
from contextlib import redirect_stdout
from pathlib import Path

ARB = Path(__file__).resolve().parent.parent
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

import ozon_library_v1 as LIB
import ozon_film_file_v1 as F

PASS = "✅ PASS"
FAIL = "❌ FAIL"

# ── Фикстура: канон-строки (это ВЫХОД convert: HTML аннотации уже снят, размер честно распарсен) ──
FIX_ROWS = [
    {"article": "tdt_fix_105", "name": "Пупырчатая пленка трехслойная 0.2x5 м", "type": "рулон-в-м",
     "size": {"w_m": 0.2, "l_m": 5.0}, "price": 4590, "old_price": 5140, "vat": "0",
     "images": ["https://cdn1.ozone.ru/s3/1.jpg", "https://cdn1.ozone.ru/s3/2.jpg"],
     "pkg_mm": {"width": 440, "height": 246, "depth": 292}, "weight_g": 550,
     "annotation": "Надёжная упаковка от ExpressGo для хрупких вещей."},
    {"article": "tdt_fix_139", "name": "Пупырка для упаковки 0.4*5 м", "type": "рулон-в-м",
     "size": {"w_m": 0.4, "l_m": 5.0}, "price": 4680, "old_price": 5230, "vat": "0",
     "images": ["https://cdn1.ozone.ru/s3/3.jpg"],
     "pkg_mm": {"width": 470, "height": 249, "depth": 295}, "weight_g": 880,
     "annotation": "Двухслойная пузырчатая плёнка."},
    {"article": "tdt_fix_140", "name": "Пупырка для упаковки 0.4*10 м", "type": "рулон-в-м",
     "size": {"w_m": 0.4, "l_m": 10.0}, "price": 6900, "old_price": 7400, "vat": "0",
     "images": ["https://cdn1.ozone.ru/s3/4.jpg"],
     "pkg_mm": {"width": 500, "height": 250, "depth": 300}, "weight_g": 1200,
     "annotation": "Длинный рулон для переезда."},
    {"article": "tdt_fix_300", "name": "Пленка воздушно-пузырьковая чёрная 0.5x10 м, 2 слоя", "type": "рулон-в-м",
     "size": {"w_m": 0.5, "l_m": 10.0}, "price": 7200, "old_price": 7700, "vat": "0",
     "images": ["https://cdn1.ozone.ru/s3/5.jpg"],
     "pkg_mm": {"width": 520, "height": 260, "depth": 320}, "weight_g": 1300,
     "annotation": "Чёрная плёнка — скрывает содержимое."},
    {"article": "tdt_fix_055", "name": "Плёнка пузырьковая 0.55x10 м", "type": "рулон-в-м",
     "size": {"w_m": 0.55, "l_m": 10.0}, "price": 8100, "old_price": 8600, "vat": "0",
     "images": ["https://cdn1.ozone.ru/s3/6.jpg"],
     "pkg_mm": {"width": 540, "height": 270, "depth": 340}, "weight_g": 1400,
     "annotation": "Широкая плёнка."},
    {"article": "tdt_fix_900", "name": "Воздушно-пузырьковая плёнка 1.2x50 м", "type": "рулон-в-м",
     "size": {"w_m": 1.2, "l_m": 50.0}, "price": 14250, "old_price": None, "vat": "0",  # край: нет старой
     "images": ["https://cdn1.ozone.ru/s3/7.jpg"],
     "pkg_mm": {"width": 600, "height": 300, "depth": 400}, "weight_g": 3000,
     "annotation": "Максимальная ширина."},
    {"article": "tdt_fix_pak", "name": "Пакет пупырчатый 20x30 см, 50 шт", "type": "пакеты-пупырка",
     "size": None, "price": 1500, "old_price": 2000, "vat": "0",
     "images": ["https://cdn1.ozone.ru/s3/8.jpg"], "pkg_mm": None, "weight_g": None, "annotation": ""},
    {"article": "tdt_fix_nos", "name": "Пленка пузырьковая надувная лист", "type": "м-одиночное",
     "size": None, "price": 900, "old_price": 1200, "vat": "0",
     "images": ["https://cdn1.ozone.ru/s3/9.jpg"], "pkg_mm": None, "weight_g": None, "annotation": ""},
]
# край old_price <= price: старая цена не выше новой → old не шлём
FIX_ROWS.append({"article": "tdt_fix_old", "name": "Плёнка 0.3x3 м", "type": "рулон-в-м",
                 "size": {"w_m": 0.3, "l_m": 3.0}, "price": 5000, "old_price": 4800, "vat": "0",
                 "images": ["https://cdn1.ozone.ru/s3/10.jpg"],
                 "pkg_mm": {"width": 440, "height": 246, "depth": 292}, "weight_g": 500,
                 "annotation": ""})
# донор-карта для подвязки (канон-пример оператора: Ш0.4×Д5 → артикул 9600155)
FIX_DONOR = {"0.4|5.0": {"article": "9600155", "url": "https://shop.cargo-avto.ru/catalog/9600155/",
                          "source": "scan"}}

# Системные коды фикстуры (грамматика ozon_article_v1: VPP-{Ш-см}x{Д-м}-{слои}{k}).
# НОВЫЙ канон: карточка несёт СВОЙ артикул-код; файловый tdt — внутренний (file_article).
CODE = {
    "tdt_fix_105": "VPP-20x5-3",     # «трехслойная 0.2x5 м» → 3 слоя
    "tdt_fix_139": "VPP-40x5-1",     # «0.4*5 м» (слоёв в имени нет → 1) — канон донора 9600155
    "tdt_fix_140": "VPP-40x10-1",    # «0.4*10 м»
    "tdt_fix_300": "VPP-50x10-2k",   # «…чёрная 0.5x10 м, 2 слоя» → 2 слоя + чёрная k
    "tdt_fix_055": "VPP-55x10-1",    # «0.55x10 м»
    "tdt_fix_900": "VPP-120x50-1",   # «1.2x50 м» → Ш120×Д50
    "tdt_fix_old": "VPP-30x3-1",     # «0.3x3 м»
}

PASS_N = 0


def check(name, cond, extra=""):
    global PASS_N
    if cond:
        PASS_N += 1
        print(f"{PASS} {name}" + (f" — {extra}" if extra else ""))
    else:
        print(f"{FAIL} {name}" + (f" — {extra}" if extra else ""))


def _ean_ok(code):
    if len(code) != 13 or not code.isdigit():
        return False
    s = sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(code[:12]))
    return (10 - s % 10) % 10 == int(code[12])


def _setup_fixtures():
    """tmp-канон строк + матрица с donor-картой; env на tmp (репо не пишем)."""
    td = tempfile.mkdtemp(prefix="ozfilm_fix_")
    rows_p = Path(td) / "rows.json"
    lib_p = Path(td) / "lib.json"
    rows_p.write_text(json.dumps(FIX_ROWS, ensure_ascii=False), encoding="utf-8")
    lib = {"records": [{"article": r["article"], "donor_link":
                        FIX_DONOR.get(f"{r.get('size', {}).get('w_m')}|{r.get('size', {}).get('l_m')}")
                        if r.get("size") else None} for r in FIX_ROWS]}
    lib_p.write_text(json.dumps(lib, ensure_ascii=False), encoding="utf-8")
    os.environ["OZON_FILM_ROWS_PATH"] = str(rows_p)
    os.environ["OZON_LIBRARY_PATH"] = str(lib_p)
    os.environ["OZON_FILM_FILE_LIBRARY_PATH"] = str(Path(td) / "pour.json")
    return rows_p, lib_p


def main():
    rows_p, lib_p = _setup_fixtures()

    # L1 источник (канон-строки + donor-карта из матрицы)
    src = F.load_source()
    check("L1 источник читается (fail-soft ok)", src["_error"] is None and len(src["rows"]) == len(FIX_ROWS))
    d139 = src["donor"].get("tdt_fix_139")
    check("L1 донор-карта из матрицы подхвачена", (d139 or {}).get("article") == "9600155")

    # L9/L2/L3 волна
    cands = F.pour_candidates(src["rows"])
    arts = [r["article"] for r in cands]
    check("L9 не-рулоны исключены (библиотека-только)",
          "tdt_fix_pak" not in arts and "tdt_fix_nos" not in arts)
    expect_order = ["tdt_fix_105", "tdt_fix_old", "tdt_fix_139", "tdt_fix_140",
                    "tdt_fix_300", "tdt_fix_055", "tdt_fix_900"]
    check("L2 порядок волны (ширина↑,длина↑,артикул)", arts == expect_order, str(arts))
    w3 = F.select_wave(src["rows"], wave=3)
    check("L3 волна режет N=3", [r["article"] for r in w3] == arts[:3])
    wall = F.select_wave(src["rows"], wave=999)
    check("L3 волна >=всех = вся партия", len(wall) == len(cands))

    # L4-L13 сборка карточек (фикстура: 7 рулонов → 7 готово, 0 блок)
    built = F.build_cards(cands, donor=src["donor"])
    by = {b["meta"]["offer_id"]: b for b in built}
    check("L4 все кандидаты собраны (0 блок)", all(b["item"] is not None for b in built) and len(built) == 7)
    c139, c300, c105 = CODE["tdt_fix_139"], CODE["tdt_fix_300"], CODE["tdt_fix_105"]
    it = by[c139]["item"]
    m = by[c139]["meta"]
    check("L15 НОВЫЙ артикул: offer_id = системный код (в карточке НЕТ tdt)",
          c139 in by and all("tdt_" not in str(b["item"]["offer_id"]) for b in built))
    check("L4 категория/цена-строкой/vat", m["can_build"] and m["description_category_id"] == 17027937
          and m["type_id"] == 97503 and it["price"] == "4680" and it["vat"] == "0")
    check("L4 EAN-13 валиден", _ean_ok(it["barcode"]))
    attrs = {a["id"]: a for a in it.get("attributes", [])}
    b85 = attrs[85]["values"][0]
    check("L5 бренд ExpressGo ПО ЗНАЧЕНИЮ (без dvid)", b85.get("value") == "ExpressGo"
          and "dictionary_value_id" not in b85)
    m_attr = attrs.get(6383, {}).get("values", [{}])[0]
    check("L6 материал=полиэтилен+dvid 62043", m_attr.get("value") == "полиэтилен"
          and m_attr.get("dictionary_value_id") == 62043)
    check("L6 цвет из имени: прозрачный НЕ задан без слова в имени", attrs.get(10096) is None)
    c300_a = {a["id"]: a for a in by[c300]["item"].get("attributes", [])}.get(10096, {}).get("values", [{}])[0]
    check("L6 чёрный в имени → цвет черный 61574", c300_a.get("dictionary_value_id") == 61574)
    check("L7 фото из файла 1-в-1", len(it.get("images", [])) == 1
          and it.get("primary_image") == it["images"][0])
    check("L7 габариты из файла (мм/г)", it.get("depth") == 295 and it.get("weight") == 880)
    a4191 = attrs.get(4191, {}).get("values", [{}])[0].get("value", "")
    check("L7 аннотация 1-в-1 (уже plain на конверте)", a4191 == "Двухслойная пузырчатая плёнка.")
    check("L12 имя 1-в-1 verbatim (НЕ калечим)", by[c105]["item"]["name"] == FIX_ROWS[0]["name"])
    check("L12 offer_id = системный код (канон 0.4×5)", by[c139]["item"]["offer_id"] == "VPP-40x5-1")
    check("L15 коды = ожидания грамматики (все рулоны фикстуры)",
          all(CODE[r["article"]] == by[CODE[r["article"]]]["item"]["offer_id"]
              for r in FIX_ROWS if r["type"] == "рулон-в-м"))
    check("L15 файловый артикул живёт в prod (журнал/матрица), НЕ в карточке",
          by[c139]["prod"].get("file_article") == "tdt_fix_139"
          and "tdt_fix_139" not in json.dumps(by[c139]["item"], ensure_ascii=False))
    check("L8 old строго больше → шлём", it.get("old_price") == "5230")
    check("L8 old<=price → НЕ шлём", "old_price" not in by[CODE["tdt_fix_old"]]["item"])
    check("L8 old=None → НЕ шлём", "old_price" not in by[CODE["tdt_fix_900"]]["item"])
    oids = [b["item"]["offer_id"] for b in built]
    check("L12 offer_id уник в волне", len(set(oids)) == len(oids))
    eans = [b["item"]["barcode"] for b in built]
    check("L13 EAN уник в волне (анти-склейка)", len(set(eans)) == len(eans))
    check("L13 EAN детерминирован и от кода (не от tdt)",
          F.prod_of(FIX_ROWS[1], code=c139)["barcode"] == F.prod_of(FIX_ROWS[1], code=c139)["barcode"]
          and F.prod_of(FIX_ROWS[1], code=c139)["barcode"] == by[c139]["item"]["barcode"]
          and F.prod_of(FIX_ROWS[1], code=c139)["barcode"] == F.prod_of(FIX_ROWS[1], code="VPP-40x5-1")["barcode"])
    # L11 подвязка в prod (журнал), НЕ в карточку
    p139 = by[c139]["prod"]
    check("L11 донор в prod-метаданных (журнал)", p139.get("donor_article") == "9600155"
          and str(p139.get("donor_url")).endswith("/9600155/"))
    check("L11 донор НЕ в карточке (нет лишних полей)", "donor_url" not in by[c139]["item"]
          and "donor_article" not in by[c139]["item"])
    # L10 РУБИКОН dry: fill(dry=True) без сети → ok, честная метка
    buf = io.StringIO()
    with redirect_stdout(buf):
        r = F.fill(built, dry=True, commit=False)
    check("L10 dry fill не открывает сеть (ok dry)", r.get("dry") is True and r.get("ok") is True)
    out = buf.getvalue()
    check("L10 dry честно помечен «СУХО»", "СУХО" in out)

    # L14 ЧАНКИ: кап Ozon /v3/product/import = 100 item на вызов. fill живой режет волну >100
    # на пакеты ≤100 (свой task_id на пакет), агрегирует imported по пакетам.
    big = built * 37  # 7×37 = 259 > 100 → должно быть 3 пакета (100/100/59)
    calls, last_batch = [], []

    def fake_create(items, dry=True, commit=False):
        calls.append(len(items))
        last_batch[:] = items
        return {"status": "sent", "response": {"result": {"task_id": len(calls)}}}

    def fake_import_info(task_id):
        return [{"offer_id": it["offer_id"], "product_id": 10_000_000 + i,
                 "status": "imported", "errors": []} for i, it in enumerate(last_batch)]

    buf2 = io.StringIO()
    with redirect_stdout(buf2), mock.patch.object(F.W, "create_product", fake_create), \
            mock.patch.object(F.W, "import_info", fake_import_info):
        r14 = F.fill(big, dry=False, commit=True)
    check("L14 волна 259 режется на пакеты ≤100 (3 вызова: 100/100/59)",
          len(calls) == 3 and calls == [100, 100, 59], str(calls))
    check("L14 агрегат импортированных по пакетам (ок, 259, 0 fail)",
          r14.get("ok") is True and len(r14["imported"]) == 259 and not r14["failures"])

    # L16 ЧАНКИ-остатки: кап /v2/products/stocks = 100 за вызов. stocks() (фикс 2026-09-09) режет волну.
    scalls = []

    def fake_stock(payload, dry=True, commit=False):
        scalls.append(len(payload))
        return {"status": "sent", "response": {"result": []}}

    buf3 = io.StringIO()
    with redirect_stdout(buf3), mock.patch.object(F, "first_warehouse_id", lambda: (90210, "Тест.Склад")), \
            mock.patch.object(F.W, "set_stock", fake_stock):
        r16 = F.stocks(big, count=50, dry=False, commit=True)
    check("L16 остатки 259 режутся на пакеты ≤100 (3 вызова: 100/100/59)",
          len(scalls) == 3 and scalls == [100, 100, 59], str(scalls))
    check("L16 агрегат стоков ok (все пакеты ушли)", r16.get("ok") is True and r16.get("n_batches") == 3)

    N_EXPECT = 35
    print(f"\nИТОГ · pass {PASS_N}/{N_EXPECT}")
    return 0 if PASS_N == N_EXPECT else 1


if __name__ == "__main__":
    sys.exit(main())

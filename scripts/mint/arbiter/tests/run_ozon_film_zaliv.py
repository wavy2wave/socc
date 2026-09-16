#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · ЗАЛИВ ПЛЁНКИ (ozon_film_zaliv_v1) — герметичные приёмки зеркала сегодняшнего набора ЯМ.

Законы (F = Film):
  F1  источник: FILM_DONOR_PATH-фикстура читается (fail-soft → честная _error).
  F2  битая строка донора (нет честной закупки) → ПРОПУСК (не собрана, не крэш).
  F3  карточка собрана: dci=17027937/type=97503 (живьё 08.09), цена строкой, EAN-13, dims см→мм/кг→г
      (1500×485×485 мм / 2250 г), can_build=True, need_mapping=False.
  F4  «Название модели» 9048 = ARB-sku (анти-склейка карточек) — НО offer_id (SKU на Ozon) = артикул
      донора (реальный товар на сайте, связка при заказе); arb ≠ art.
  F5  ЧЕСТНОСТЬ бренда: ExpressGo ПО ЗНАЧЕНИЮ — в attribute НЕТ dictionary_value_id (в словаре бренда
      нет, не выдумываем; бренд оператора зарегистрирован). Вид плёнки (11011) и ТН ВЭД (22232) — со
      словарными dvid; код маркировки 23536 = false; страна 4389 = Россия dvid 90295.
  F6  enum-атрибуты из фактов: материал полиэтилен→62043, цвет прозрачный→61572/черный→61574;
      НЕизвестное значение словаря → атрибут НЕ шлём (мягкий проход, не выдумка dvid).
  F7  фото журнала (по ARB-sku) перекрывают → images есть (не «НЕТ»).
  F8  детерминизм: та же строка → тот же sku/цена/old_price; цена = build_product ЯМ-линии (тот же
      билдер → «цены держим одинаково что там что там»).
  F9  EAN-13 валиден (контрольная цифра) и детерминирован (тот же артикул → тот же код).
  F10 OZ2 жёсткий блок: справочник категорий пуст → item=None + need_mapping=True (не исключение).
  F11 РУБИКОН dry: fill(dry=True) — create_product зовётся с dry=True commit=False (сеть не открыта).
  F12 живой залив: task_id → poll import_info → imported/errors; успех = status=='imported' AND pid>0
      AND errors==[].
  F13 200≠успех: import_info вернул failed+errors → честный failure, ok=False.
  F14 результат НЕ известен честно: import_info пуст за все попытки → «неизвестен», не фантом-успех.
  F15 остаток не выдумываем: count не задан → блок.
  F16 склад не выдумываем: склада нет → блок «склад не создан».
  F17 остатки dry: склад есть + count → payload собран, ТОЛЬКО «В наличии» донора (in_stock).
  F18 остатки живые: set_stock зовётся с dry=False commit=True; наличие честно (только in_stock=True).
  F19 poured_pids честно: набор pids несёт ТОЛЬКО живой ДОНОР (не ЗАЛИВ/ВИТРИНА, не dry); пустой
      журнал → [] (отсутствие артефакта ≠ «ноль»).
  F20 photo_urls_by_sku: журнал ARB→http-URL; не-http отсеяны; пусто → {}.
  F21 SKU на Ozon = артикул донора (offer_id=article, реальный товар; arb=ARB-… ≠ article).
  F22 две цены: зачёркнутая old_price = цена продажи + OLD_PRICE_STEP (500₽) — «мы скидку сделали».
  F23 полная карточка из фактов (внедрённые ym.FILM_FACTS, как живой assemble_new_rows): аннотация
      4191 = НАШЕ описание plain-текстом (ExpressGo, БЕЗ «ATLAS EDGE», без HTML), страна 4389 dvid
      90295, длина 6468=«50» (м), ширина 8416=«150» (см), единиц 8962=«1».
  F24 МАТРИЦА-БИБЛИОТЕКА залитого (директива SKU=реальный товар донора): после ЖИВОГО --fill --commit
      пишутся связки offer_id↔donor_url↔цена/old_price↔ARB-sku↔product_id + shelf «Продаётся» (сверка
      витрины); --library читает; пустой imported → файл НЕ создаётся (нет результата — нечего писать).
  F25 витрина «Продаётся» ЧЕСТНО (цикл-1 ОЗОН): «Продаётся» ТОЛЬКО при живом visible=True; модерация/
      ошибки/скрыта/нет — иные статусы; product_id=0 вне сверки; pour_mark_shelf проставляет shelf в
      матрицу, новых записей не плодит.
  F26 ГЕЙТ ПОЛНОТЫ (живой скан донора транзиентно частичен — 15/33): залив/остатки зеркального набора
      НЕ лиются по недо-скану. scan_donor_complete догоняет полный набор ретраями (мёржа по pid);
      не догнал → main --fill/--stocks --only-poured (живой донор) АБОРТ rc=1, НИ ОДНОГО write; полный
      скан гейт пропускает (stocks уходит). Богатая карточка требует FILM_FACTS из того же процесса →
      гейт в main(), а не снапшотом.

Сухо: env-песочница (FILM_DONOR_PATH→фикстура, журналы→временные файлы, OZON_FILM_LIBRARY_PATH→в
песок), сеть к Ozon/донору НЕ открывается, W.* замоканы, 0₽, канон не пишется.
"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ARB = Path(__file__).resolve().parent.parent
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

import ozon_film_zaliv_v1 as F
import ozon_card_v1 as card
import ymarket_film_cards_v1 as ym

PASS = "✅ PASS"
FAIL = "❌ FAIL"

# ФАКТЫ богатой карточки для pid "10143" (row0 фикстуры: 50×1.5 м, 30 г/м², 2 слоя) — схема статики
# FILM_FACTS (ключи _build_name/_build_description/_build_spec): длина_м/ширина_м → Озон 6468/8416.
RICH_FACTS = {
    "ширина_м": 1.5, "длина_м": 50.0, "площадь_м2": 75.0,
    "слои": 2, "пузырёк_мм": 10, "плотность_г_м2": 30.0, "толщина_мм": 4.0,
    "вес_кг": 2.25, "цвет": "прозрачный", "материал": "полиэтилен", "страна": "Россия",
    "применение": ["обёртывание товаров при переезде", "защита хрупких предметов"],
    "особость": "рулона хватает на десятки коробок — один запас закрывает сезон отправок",
}

# Строки в схеме assemble_new_rows (донор-скан ЯМ-линии): pid/sku+article+name+cost+dims+_stock.
FILM_ROWS = [
    {"sku": "10143",
     "name": "Воздушно пузырьковая пленка, 50*1.5 м «Бизнес», 30 г/м², двухслойная",
     "cost": "770.0", "article": "9602472", "_stock": "in_stock",
     "length": "150.0", "width": "48.5", "height": "48.5", "weight": "2.25"},
    {"sku": "10144",
     "name": "Воздушно пузырьковая пленка, 1.2*100 м «Компакт», 45 г/м², трёхслойная",
     "cost": "2420.0", "article": "9602473", "_stock": "in_stock",
     "length": "35.0", "width": "35.0", "height": "90.0", "weight": "4.7"},
    {"sku": "10145",
     "name": "Воздушно пузырьковая пленка, 5*0.4 м, 55 г/м²",
     "cost": "655.0", "article": "9602474", "_stock": "on_order",
     "length": "10.0", "width": "10.0", "height": "10.0", "weight": "0.12"},
]
# Битые строки донора (нет честной закупки/артикула) — пропуск, не крэш.
BROKEN_ROW = {"sku": "10199", "name": "Воздушно пузырьковая пленка сломанная",
              "cost": "", "article": "", "_stock": "in_stock"}

# Исходные объекты W (вернуть после каждого теста — не оставлять мок следующему).
_ORIG = (F.W.create_product, F.W.import_info, F.W.set_stock, F.W.read_shelf, F.first_warehouse_id)


def _restore_mocks():
    (F.W.create_product, F.W.import_info, F.W.set_stock, F.W.read_shelf,
     F.first_warehouse_id) = _ORIG


def _sandbox(rows=None):
    rows = FILM_ROWS if rows is None else rows
    d = Path(tempfile.mkdtemp(prefix="ozon_film_zaliv_test_"))
    fx = d / "fixture.json"
    fx.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    old = os.environ.get("FILM_DONOR_PATH")
    os.environ["FILM_DONOR_PATH"] = str(fx)
    return d, old, fx


def _restore(old):
    if old is None:
        os.environ.pop("FILM_DONOR_PATH", None)
    else:
        os.environ["FILM_DONOR_PATH"] = old
    _restore_mocks()


def _silent(fn):
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn()
    return buf.getvalue()


def _attr(built, idx, aid):
    """Достать attribute по id из item."""
    item = built[idx]["item"]
    for a in (item.get("attributes") or []):
        if a.get("id") == aid:
            return a
    return None


def _attr_of(item, aid):
    return next((a for a in (item.get("attributes") or []) if a.get("id") == aid), None)


def _t01_fixture_ok():
    d, old, fx = _sandbox()
    try:
        m = F.load_donor_rows()
        return m["ok"] and len(m["rows"]) == 3 and m["path"] == str(fx), f"rows={len(m.get('rows', []))}"
    finally:
        _restore(old)


def _t02_broken_skip():
    d, old, fx = _sandbox(rows=FILM_ROWS + [BROKEN_ROW])
    try:
        built = F.build_cards(F.load_donor_rows()["rows"])
        # битая строка пропущена: карточек 3, а не 4; без крэша
        return len(built) == 3, f"cards={len(built)}"
    finally:
        _restore(old)


def _t03_card_built():
    d, old, fx = _sandbox()
    try:
        built = F.build_cards(F.load_donor_rows()["rows"])
        b = built[0]
        item, m = b["item"], b["meta"]
        dims_ok = (item.get("depth") == 1500 and item.get("width") == 485
                   and item.get("height") == 485 and item.get("weight") == 2250
                   and item.get("dimension_unit") == "mm" and item.get("weight_unit") == "g")
        ok = (item is not None
              and item.get("description_category_id") == F.VPP_DCI
              and item.get("type_id") == F.VPP_TID
              and item.get("price") == str(b["prod"]["price"])     # цена строкой, зеркало ЯМ
              and item.get("vat") == "0"
              and item.get("barcode") and len(item["barcode"]) == 13
              and dims_ok
              and m["can_build"] is True and m["need_mapping"] is False
              and m["price"] == str(b["prod"]["price"]))
        return ok, (f"dci={item.get('description_category_id')} price={item.get('price')} "
                    f"dims={item.get('depth')}/{item.get('width')}/{item.get('height')}/{item.get('weight')}")
    finally:
        _restore(old)


def _t04_model_9048_injected():
    """«Название модели» 9048 = ARB-sku (анти-склейка); offer_id (SKU Ozon) = АРТИКУЛ донора."""
    d, old, fx = _sandbox()
    try:
        built = F.build_cards(F.load_donor_rows()["rows"])
        b = built[0]
        mod = _attr(built, 0, 9048)              # Название модели (категория ТРЕБУЕТ)
        mv = (mod.get("values") or [{}])[0].get("value") if mod else None
        arb = str(b["prod"]["sku"])               # ARB-… — ключ фото/журнала, анти-склейка
        art = str(b["row"]["article"])            # реальный товар донора
        return mv == arb and b["item"]["offer_id"] == art and arb != art, \
               f"model={mv!r} arb={arb!r} offer_id={b['item'].get('offer_id')!r}"
    finally:
        _restore(old)


def _t05_brand_po_znacheniyu():
    """Бренд = 'ExpressGo' (бренд оператора) ПО ЗНАЧЕНИЮ; вид+ТН ВЭД словарём; маркировка false."""
    d, old, fx = _sandbox()
    try:
        built = F.build_cards(F.load_donor_rows()["rows"])
        brand = _attr(built, 0, 85)              # Бренд — по значению (в словаре его НЕТ)
        vid = _attr(built, 0, 11011)             # Вид упаковочной пленки — словарный
        tn = _attr(built, 0, 22232)              # ТН ВЭД — словарный
        mark = _attr(built, 0, 23536)            # Нужен код маркировки — boolean false
        country = _attr(built, 0, 4389)          # Страна-изготовитель — словарный
        bv = (brand.get("values") or [{}])[0]
        vv = (vid.get("values") or [{}])[0]
        tv = (tn.get("values") or [{}])[0]
        mv = (mark.get("values") or [{}])[0]
        cv = (country.get("values") or [{}])[0]
        brand_honest = bv.get("value") == "ExpressGo" and bv.get("dictionary_value_id") is None
        vid_honest = vv.get("dictionary_value_id") == F.VPP_VID_DVID
        tn_honest = tv.get("dictionary_value_id") == F.VPP_TN_VED_DVID and "3920108909" in str(tv.get("value"))
        mark_honest = mv.get("value") == "false"
        country_honest = country is not None and cv.get("dictionary_value_id") == 90295
        return brand_honest and vid_honest and tn_honest and mark_honest and country_honest, \
               f"brand={bv} vid={vv} tn={tv} mark={mv} country={cv}"
    finally:
        _restore(old)


def _t06_enums_facts():
    """enum-атрибуты материала/цвета из фактов; неизвестное слово → атрибут НЕ шлём (не выдумка)."""
    d, old, fx = _sandbox()
    try:
        def it(spec):
            prod = {"offer_id": "ARB-00000001", "price": 500,
                    "name": "Плёнка воздушно-пузырьковая 1.5×50 м. 2 слоя, плотность 30 г/м²",
                    "_spec": {"_model": "ARB-00000001", **spec}}
            r = card.to_item(prod, cats=F.CATS, unique_name=False, house_brand=F.HOUSE_BRAND)
            return r["item"]
        i1 = it({"материал": "полиэтилен", "цвет": "прозрачный"})
        i2 = it({"материал": "полиэтилен", "цвет": "черный"})
        i3 = it({"материал": "бумага", "цвет": "синий"})       # в словаре категории нет
        a_mat = _attr_of(i1, 6383); a_col = _attr_of(i1, 10096)
        a_mat_black = _attr_of(i2, 6383); a_col_black = _attr_of(i2, 10096)
        hit = (a_mat is not None and (a_mat["values"][0].get("dictionary_value_id") == 62043)
               and a_col is not None and (a_col["values"][0].get("dictionary_value_id") == 61572)
               and a_col_black is not None and (a_col_black["values"][0].get("dictionary_value_id") == 61574))
        skip = a_mat_black is not None and _attr_of(i3, 6383) is None and _attr_of(i3, 10096) is None
        return hit and skip, f"материал={a_mat and a_mat['values']} цвет={a_col and a_col['values']} i3_attr6383={_attr_of(i3,6383) is None}"
    finally:
        _restore(old)


def _t07_photos_override():
    d, old, fx = _sandbox()
    try:
        from uniqueizer_v1 import gen_ean13
        rows = F.load_donor_rows()["rows"]
        art = str(rows[0]["article"])
        arb_sku = f"ARB-{gen_ean13(art)[-8:]}"
        photos = {arb_sku: ["https://img.ozon.example/film_1.jpg", "https://img.ozon.example/film_2.jpg"]}
        built = F.build_cards(rows, photos=photos)
        b = built[0]
        imgs = b["item"].get("images") or []
        return (not b["meta"]["missing_images"] and b["item"].get("primary_image") == photos[arb_sku][0]
                and imgs == photos[arb_sku]), f"images={imgs}"
    finally:
        _restore(old)


def _t08_determinism():
    """Детерминизм + зеркальная цена: два прохода сборки идентичны, цена = build_product ЯМ-линии.
    offer_id = АРТИКУЛ донора (SKU=реальный товар), а не ARB-sku билдера."""
    d, old, fx = _sandbox()
    try:
        rows = F.load_donor_rows()["rows"]
        a = F.build_cards(rows)
        b = F.build_cards(rows)
        same = ([(x["item"]["offer_id"], x["item"]["price"], x["item"].get("old_price")) for x in a]
                == [(x["item"]["offer_id"], x["item"]["price"], x["item"].get("old_price")) for x in b])
        from ymarket_film_cards_v1 import build_product as ym_build
        ym = ym_build(rows[0], {}, 0)
        mirror_price = a[0]["item"]["price"] == str(ym["price"])
        mirror_sku = a[0]["item"]["offer_id"] == str(rows[0]["article"])   # товар донора, не ARB
        return same and mirror_price and mirror_sku, \
               f"offer_id={a[0]['item']['offer_id']} price={a[0]['item']['price']} ym_price={ym['price']} ym_sku={ym['sku']}"
    finally:
        _restore(old)


def _t09_ean_valid():
    d, old, fx = _sandbox()
    try:
        from uniqueizer_v1 import gen_ean13
        e = gen_ean13("9602472")
        s = sum((1 if i % 2 == 0 else 3) * int(ch) for i, ch in enumerate(e[:12]))
        check = (10 - (s % 10)) % 10
        return len(e) == 13 and e[0] == "2" and int(e[12]) == check and e == gen_ean13("9602472"), f"ean={e}"
    finally:
        _restore(old)


def _t10_oz2_block():
    d, old, fx = _sandbox()
    try:
        prod = {"offer_id": "NO-CAT-1", "name": "Странный товар без категории", "price": 500}
        r = card.to_item(prod, cats={})     # справочник пуст → категории нет → жёсткий блок
        m = r["meta"]
        return r["item"] is None and m["need_mapping"] is True and m["can_build"] is False \
            and m.get("block_reason") and "авто-категории" in m["block_reason"], \
            f"item={r['item']} need_mapping={m['need_mapping']}"
    finally:
        _restore(old)


def _t11_rubicon_dry():
    d, old, fx = _sandbox()
    try:
        calls = {}
        def fake_cp(items, dry=True, commit=False, timeout=60):
            calls["dry"], calls["commit"] = dry, commit
            return {"status": "dry", "would_send": items}
        F.W.create_product = fake_cp
        built = F.build_cards(F.load_donor_rows()["rows"])
        out = _silent(lambda: F.fill(built, dry=True, commit=False))
        return calls.get("dry") is True and calls.get("commit") is False and "СУХО" in out, \
               f"calls={calls} out_has_dry={'СУХО' in out}"
    finally:
        _restore(old)


def _t12_live_imported():
    """Живой залив: task_id → poll import_info → imported (по АРТИКУЛУ донора = offer_id на Ozon)."""
    d, old, fx = _sandbox()
    try:
        F.W.create_product = lambda items, dry=True, commit=False, timeout=60: \
            {"status": "sent", "response": {"result": {"task_id": 123456}}}
        F.W.import_info = lambda task_id, timeout=30: [
            {"offer_id": "9602472", "status": "imported", "product_id": 777001, "errors": []},
            {"offer_id": "9602473", "status": "imported", "product_id": 777002, "errors": []},
        ]
        built = F.build_cards(F.load_donor_rows()["rows"])
        out = _silent(lambda: F.fill(built, dry=False, commit=True))
        ok = "product_id=777001" in out and "ошибок 0" in out
        return ok, out.strip().splitlines()[0]
    finally:
        _restore(old)


def _t13_200_ne_uspeh():
    d, old, fx = _sandbox()
    try:
        F.W.create_product = lambda items, dry=True, commit=False, timeout=60: \
            {"status": "sent", "response": {"result": {"task_id": 1}}}
        F.W.import_info = lambda task_id, timeout=30: [
            {"offer_id": "9602472", "status": "failed", "product_id": 0,
             "errors": ["ТН ВЭД не совпадает", "Название модели обязательно"]},
        ]
        built = F.build_cards(F.load_donor_rows()["rows"])
        out = _silent(lambda: F.fill(built, dry=False, commit=True))
        ok = "ошибок 1" in out and "ТН ВЭД не совпадает" in out
        return ok, out.strip().splitlines()[0]
    finally:
        _restore(old)


def _t14_unknown_honest():
    d, old, fx = _sandbox()
    try:
        F.W.create_product = lambda items, dry=True, commit=False, timeout=60: \
            {"status": "sent", "response": {"result": {"task_id": 9}}}
        F.W.import_info = lambda task_id, timeout=30: []     # вечно пусто
        built = F.build_cards(F.load_donor_rows()["rows"])
        out = _silent(lambda: F.fill(built, dry=False, commit=True, poll_attempts=2, poll_delay=0))
        ok = "НЕ известен" in out and "imported" not in out
        return ok, out.strip()[:90]
    finally:
        _restore(old)


def _t15_count_obyazaten():
    d, old, fx = _sandbox()
    try:
        built = F.build_cards(F.load_donor_rows()["rows"])
        out = _silent(lambda: F.stocks(built, count=None, dry=True, commit=False))
        return "count не задан" in out, out.strip()[:80]
    finally:
        _restore(old)


def _t16_sklad_ne_vyiduman():
    d, old, fx = _sandbox()
    try:
        F.first_warehouse_id = lambda: (None, None)     # склада в кабинете нет
        built = F.build_cards(F.load_donor_rows()["rows"])
        out = _silent(lambda: F.stocks(built, count=5, dry=True, commit=False))
        return "склад не создан" in out, out.strip().splitlines()[0]
    finally:
        _restore(old)


def _t17_stocks_dry():
    d, old, fx = _sandbox()
    try:
        F.first_warehouse_id = lambda: (1020005029808130, "Карго.Вавилова")
        F.W.set_stock = lambda stocks, dry=True, commit=False, timeout=60: {"status": "dry"}
        built = F.build_cards(F.load_donor_rows()["rows"])
        out = _silent(lambda: F.stocks(built, count=7, dry=True, commit=False))
        # только in_stock строки донора (2 из 3; on_order — НЕ наличие); SKU = артикул донора
        ok = ("1020005029808130" in out) and ("9602472 → 7" in out) and ("9602473 → 7" in out)
        # on_order-артикул (9602474) в payload отсутствует
        sku_out = [b["meta"]["offer_id"] for b in built if b["row"]["_stock"] == "on_order"][0]
        return ok and (sku_out not in out), out.strip().splitlines()[0]
    finally:
        _restore(old)


def _t18_stocks_live_nalechie():
    d, old, fx = _sandbox()
    try:
        calls = {}
        F.first_warehouse_id = lambda: (1020005029808130, "Карго.Вавилова")
        F.W.set_stock = lambda stocks, dry=True, commit=False, timeout=60: \
            (calls.__setitem__("dry", dry), calls.__setitem__("commit", commit), {"status": "sent"})[2]
        built = F.build_cards(F.load_donor_rows()["rows"])
        out = _silent(lambda: F.stocks(built, count=3, dry=False, commit=True))
        # наличие честно: только _stock=="in_stock" → True; on_order/нет/None → False
        nal = (F._in_stock({"sku": "a", "_stock": "in_stock"}) is True
               and F._in_stock({"sku": "a", "_stock": "on_order"}) is False
               and F._in_stock({"sku": "a", "_stock": None}) is False
               and F._in_stock({"sku": "a", "_stock": ""}) is False
               and F._in_stock({"sku": "a", "stock": {"in_stock": True}}) is True
               and F._in_stock({"sku": "a", "stock": {"in_stock": False}}) is False)
        return calls.get("dry") is False and calls.get("commit") is True and "ЖИВОЙ" in out and nal, \
               f"calls={calls} out_has_live={'ЖИВОЙ' in out} nal={nal}"
    finally:
        _restore(old)


def _t19_poured_honest():
    """pids несёт ТОЛЬКО последний ЖИВОЙ ДОНОР; ЗАЛИВ/ВИТРИНА/dry-события игнорируются; пусто→[]."""
    d = Path(tempfile.mkdtemp(prefix="ozon_film_zaliv_journal_"))
    try:
        j = d / "2026-09-08.jsonl"
        j.write_text("\n".join([
            json.dumps({"node": "ЗАЛИВ", "dry": False, "evidence": {"pids": ["1", "2"]}}),
            json.dumps({"node": "ДОНОР", "dry": True, "evidence": {"pids": ["3", "4"]}}),
            json.dumps({"node": "ДОНОР", "dry": False, "evidence": {"pids": ["10143", "10144"]}}),
            json.dumps({"node": "ДОНОР", "dry": False, "evidence": {"pids": ["10145"]}}),  # последний живьё
        ]), encoding="utf-8")
        got = F.poured_pids(journal=str(j))
        empty = F.poured_pids(journal=str(d / "empty.jsonl"))  # файла нет → []
        return got == ["10145"] and empty == [], f"got={got} empty={empty}"
    finally:
        pass


def _t20_photo_journal():
    d = Path(tempfile.mkdtemp(prefix="ozon_film_zaliv_photo_"))
    try:
        j = d / "photos.jsonl"
        j.write_text("\n".join([
            json.dumps({"offer_id": "ARB-16214506", "pictures_current": ["https://img/1.jpg"]}),
            json.dumps({"offer_id": "ARB-16214506", "pictures_current": ["https://img/2.jpg", "ftp://no"]}),
            json.dumps({"offer_id": "", "pictures_current": ["https://no-sku.jpg"]}),
        ]), encoding="utf-8")
        got = F.photo_urls_by_sku(journal=str(j))
        ok = (got.get("ARB-16214506") == ["https://img/2.jpg"]   # последняя по SKU, не-http отсеян
              and F.photo_urls_by_sku(journal=str(d / "empty.jsonl")) == {})
        return ok, f"got={got}"
    finally:
        pass


def _t21_offer_is_article():
    """F21 SKU-на-Ozon = РЕАЛЬНЫЙ товар донора: item.offer_id == article (не ARB-sku)."""
    d, old, fx = _sandbox()
    try:
        rows = F.load_donor_rows()["rows"]
        built = F.build_cards(rows)
        for b in built:
            art = str(b["row"]["article"])
            arb = str(b["prod"]["sku"])
            it, m = b["item"], b["meta"]
            if not (it["offer_id"] == art and arb.startswith("ARB-") and arb != art
                    and m["offer_id"] == art):
                return False, f"offer_id={it['offer_id']!r} article={art!r} arb={arb!r}"
        # связка заказа: донор-URL реального товара строится от артикула
        return F.DONOR_BASE + "9602472" + "/" == "https://sp.cargo-avto.ru/catalog/9602472/", "url ok"
    finally:
        _restore(old)


def _t22_two_prices():
    """F22 две цены: old_price (зачёркнутая) = цена продажи + OLD_PRICE_STEP (500₽)."""
    d, old, fx = _sandbox()
    try:
        rows = F.load_donor_rows()["rows"]
        built = F.build_cards(rows)
        for b in built:
            price = b["prod"]["price"]
            old_price = int(round(price)) + F.OLD_PRICE_STEP
            if not (b["item"]["price"] == str(price)
                    and b["item"].get("old_price") == str(old_price)
                    and int(b["item"].get("old_price", 0)) > int(b["item"]["price"])):
                return False, (f"price={b['item']['price']} old={b['item'].get('old_price')} "
                               f"want_old={old_price}")
        return True, f"step={F.OLD_PRICE_STEP}"
    finally:
        _restore(old)


def _t23_full_card_rich():
    """F23 полная карточка из фактов (внедряем ym.FILM_FACTS[pid], как делает живой assemble_new_rows):
    аннотация 4191 = НАШЕ описание plain-текстом (ExpressGo, БЕЗ 'ATLAS EDGE' и БЕЗ HTML-тегов);
    страна 4389 = Россия dvid 90295; длина 6468="50"; ширина 8416="150"; единиц 8962="1"."""
    d, old, fx = _sandbox()
    ym.FILM_FACTS["10143"] = RICH_FACTS
    try:
        rows = F.load_donor_rows()["rows"]
        built = F.build_cards(rows)
        b = built[0]
        ann = _attr(built, 0, 4191)
        av = (ann.get("values") or [{}])[0].get("value") if ann else None
        c = _attr(built, 0, 4389)
        cv = (c.get("values") or [{}])[0] if c else None
        ln = _attr(built, 0, 6468)
        wd = _attr(built, 0, 8416)
        un = _attr(built, 0, 8962)
        val = lambda a: (a.get("values") or [{}])[0].get("value") if a else None
        ann_ok = (av is not None and "ExpressGo" in av and "ATLAS EDGE" not in av
                  and "<" not in av and ">" not in av)
        ok = (ann_ok and c is not None and cv.get("dictionary_value_id") == 90295
              and cv.get("value") == "Россия"
              and val(ln) == "50" and val(wd) == "150" and val(un) == "1")
        return ok, (f"ann={'нет' if av is None else av[:70]!r} c={cv} "
                    f"len={val(ln)} wid={val(wd)} units={val(un)}")
    finally:
        ym.FILM_FACTS.pop("10143", None)
        _restore(old)


def _t24_library_cycle():
    """F24 МАТРИЦА-БИБЛИОТЕКА: CLI --fill --commit пишет связки offer_id↔донор + авто-сверка витрины
    (shelf='Продаётся'); --library читает; пустой imported → файл НЕ создаётся."""
    d, old, fx = _sandbox()
    lib_dir = Path(tempfile.mkdtemp(prefix="ozon_film_lib_"))
    lib_p = lib_dir / "pour-library.json"
    old_lib = os.environ.get("OZON_FILM_LIBRARY_PATH")
    os.environ["OZON_FILM_LIBRARY_PATH"] = str(lib_p)
    try:
        F.W.create_product = lambda items, dry=True, commit=False, timeout=60: \
            {"status": "sent", "response": {"result": {"task_id": 123456}}}
        F.W.import_info = lambda task_id, timeout=30: [
            {"offer_id": "9602472", "status": "imported", "product_id": 777001, "errors": []},
            {"offer_id": "9602473", "status": "imported", "product_id": 777002, "errors": []},
            {"offer_id": "9602474", "status": "imported", "product_id": 777003, "errors": []},
        ]
        F.W.read_shelf = lambda offer_ids, timeout=30: {"ok": True, "cards": [
            {"offer_id": str(o), "visible": True, "moderation": "approved",
             "errors": [], "product_id": 777000 + i + 1}
            for i, o in enumerate(offer_ids)]}
        rc = F.main(["--fill", "--commit"])
        lib = F.read_pour_library()
        rec = lib.get("9602472") or {}
        # связка заказа: донор-URL реального товара, цена зеркала, зачёркнутая, статус витрины
        ok = (rc == 0 and len(lib) == 3
              and rec.get("donor_url") == "https://sp.cargo-avto.ru/catalog/9602472/"
              and rec.get("product_id") == 777001
              and rec.get("price") and rec.get("old_price")
              and rec.get("old_price") > rec.get("price")
              and rec.get("shelf") == "Продаётся"
              and rec.get("arb_sku", "").startswith("ARB-"))
        # пустой imported → файл НЕ пишется (нет результата залива — нечего записывать)
        os.environ["OZON_FILM_LIBRARY_PATH"] = str(lib_dir / "empty.json")
        r2 = F.record_pour([], [])
        empty_ok = (not r2.get("ok") and not (lib_dir / "empty.json").exists())
        return ok and empty_ok, f"rc={rc} lib={len(lib)} shelf={rec.get('shelf')} r2={r2}"
    finally:
        if old_lib is None:
            os.environ.pop("OZON_FILM_LIBRARY_PATH", None)
        else:
            os.environ["OZON_FILM_LIBRARY_PATH"] = old_lib
        _restore(old)


def _t25_shelf_status_honest():
    """F25 витрина-гейт цикл-1: «Продаётся» ТОЛЬКО при живом visible=True; модерация/ошибки/нет —
    честно иные. verify_shelf не шлёт без product_id; pour_mark_shelf проставляет в библиотеку."""
    d, old, fx = _sandbox()
    lib_dir = Path(tempfile.mkdtemp(prefix="ozon_film_shelf_"))
    lib_p = lib_dir / "pour-library.json"
    old_lib = os.environ.get("OZON_FILM_LIBRARY_PATH")
    os.environ["OZON_FILM_LIBRARY_PATH"] = str(lib_p)
    try:
        # Классификатор: честно разводит состояния
        cl = (F.shelf_status_of({"visible": True}) == "Продаётся"
              and F.shelf_status_of({"visible": False, "moderation": "in_progress"}) == "на модерации"
              and F.shelf_status_of({"visible": False, "moderation": None, "errors": ["Нет цены"]})
              .startswith("ошибки")
              and F.shelf_status_of({"visible": False, "moderation": "approved"}) == "одобрена, но скрыта"
              and F.shelf_status_of(None) == "не найдена"
              and F.shelf_status_of({"_error": "таймаут"}) == "сверка недоступна: таймаут")
        # verify_shelf: product_id==0 → НЕ шлём на витрину; мок живой витрины visible
        F.W.read_shelf = lambda offer_ids, timeout=30: {"ok": True, "cards": [
            {"offer_id": "9602472", "visible": True, "moderation": "approved", "errors": []},
            {"offer_id": "9602473", "visible": False, "moderation": "in_progress", "errors": []},
        ]}
        res = F.verify_shelf([
            {"offer_id": "9602472", "product_id": 777001},
            {"offer_id": "9602473", "product_id": 777002},
            {"offer_id": "9602499", "product_id": 0},        # нет product_id — вне сверки
        ])
        rpt = res.get("report", {})
        ver = (res.get("ok") is True and len(rpt) == 2
               and rpt.get("9602472") == "Продаётся"
               and rpt.get("9602473") == "на модерации")
        # pour_mark_shelf: записи в матрице получают поле shelf; новых не добавляет
        F._write_pour_library({
            "9602472": {"offer_id": "9602472", "price": 6160},
            "9602473": {"offer_id": "9602473", "price": 19360},
        })
        pm = F.pour_mark_shelf(rpt)
        lib = F.read_pour_library()
        mark = (pm.get("ok") is True and pm.get("updated") == 2
                and lib.get("9602472", {}).get("shelf") == "Продаётся"
                and lib.get("9602473", {}).get("shelf") == "на модерации"
                and "9602499" not in lib)
        return cl and ver and mark, f"cl={cl} ver={rpt} mark={pm}"
    finally:
        if old_lib is None:
            os.environ.pop("OZON_FILM_LIBRARY_PATH", None)
        else:
            os.environ["OZON_FILM_LIBRARY_PATH"] = old_lib
        _restore(old)


def _mkrow(pid):
    """Строка донора (схема assemble_new_rows) для гейт-тестов: всё «В наличии», честные закупка/артикул."""
    return {"sku": str(pid), "name": f"Воздушно пузырьковая пленка тест {pid}", "cost": "770.0",
            "article": "96" + str(pid).zfill(6), "_stock": "in_stock",
            "length": "150.0", "width": "48.5", "height": "48.5", "weight": "2.25"}


def _t26a_scan_donor_complete_merges():
    """F26a донабор: первый живой скан частичен (1 из 3), второй — полный → scan_donor_complete
    догоняет (мёрж по pid), missing пуст, число попыток честное."""
    pids = {"10143", "10144", "10145"}
    order = [["10143"], ["10144", "10145"]]
    calls = []

    def fake_load():
        calls.append(1)
        batch = order[min(len(calls) - 1, len(order) - 1)]
        return {"ok": True, "rows": [_mkrow(p) for p in batch]}

    old_load, old_sleep = F.load_donor_rows, F.time.sleep
    F.load_donor_rows, F.time.sleep = fake_load, (lambda s: None)
    try:
        rows, missing = F.scan_donor_complete(pids, retries=3, delay=0)
        ok = len(rows) == 3 and not missing and len(calls) == 2
        return ok, f"rows={len(rows)} missing={missing} calls={len(calls)}"
    finally:
        F.load_donor_rows, F.time.sleep = old_load, old_sleep


def _t26b_gate_abort_partial():
    """F26b гейт полноты: живой скан вечно частичен (1 из 3) → --stocks --commit --only-poured
    АБОРТ (rc=1, 'ГЕЙТ ПОЛНОТЫ', перечислены недостающие), W.set_stock НЕ вызван — ни одного write."""
    pids = {"10143", "10144", "10145"}

    def fake_load():
        return {"ok": True, "rows": [_mkrow("10143")]}   # недо-скан из раза в раз

    seen, rc = [], None
    old_env = os.environ.get("FILM_DONOR_PATH")
    os.environ.pop("FILM_DONOR_PATH", None)              # живой донор (не фикстура) → гейт активен
    old_load, old_poured, old_sleep = F.load_donor_rows, F.poured_pids, F.time.sleep
    F.load_donor_rows, F.poured_pids = fake_load, (lambda: list(pids))
    F.time.sleep = lambda s: None
    F.W.set_stock = lambda stocks, dry=True, commit=False, timeout=60: \
        (seen.append(len(stocks)), {"status": "sent"})[1]
    F.first_warehouse_id = lambda: (1020005024209370, "T")
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = F.main(["--stocks", "--count", "5", "--commit", "--only-poured"])
        out = buf.getvalue()
        ok = (rc == 1 and "ГЕЙТ ПОЛНОТЫ" in out and "10144" in out and "10145" in out
              and not seen and "3/3" not in out)
        return ok, f"rc={rc} has_gate={'ГЕЙТ ПОЛНОТЫ' in out} calls={len(seen)}"
    finally:
        F.load_donor_rows, F.poured_pids, F.time.sleep = old_load, old_poured, old_sleep
        if old_env is None:
            os.environ.pop("FILM_DONOR_PATH", None)
        else:
            os.environ["FILM_DONOR_PATH"] = old_env
        _restore_mocks()


def _t26c_gate_passes_full():
    """F26c гейт пропускает ПОЛНЫЙ скан: 3/3 на месте → --stocks --commit --only-poured уходит
    (set_stock вызван один раз, payload на все 3 «В наличии»), rc=0."""
    pids = {"10143", "10144", "10145"}

    def fake_load():
        return {"ok": True, "rows": [_mkrow(p) for p in sorted(pids)]}

    sent, rc = [], None
    old_env = os.environ.get("FILM_DONOR_PATH")
    os.environ.pop("FILM_DONOR_PATH", None)
    old_load, old_poured, old_sleep = F.load_donor_rows, F.poured_pids, F.time.sleep
    F.load_donor_rows, F.poured_pids = fake_load, (lambda: list(pids))
    F.time.sleep = lambda s: None
    F.W.set_stock = lambda stocks, dry=True, commit=False, timeout=60: \
        (sent.append(stocks), {"status": "sent"})[1]
    F.first_warehouse_id = lambda: (1020005024209370, "T")
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = F.main(["--stocks", "--count", "5", "--commit", "--only-poured"])
        ok = rc == 0 and len(sent) == 1 and len(sent[0]) == 3
        return ok, f"rc={rc} calls={len(sent)} payload={len(sent[0]) if sent else 0}"
    finally:
        F.load_donor_rows, F.poured_pids, F.time.sleep = old_load, old_poured, old_sleep
        if old_env is None:
            os.environ.pop("FILM_DONOR_PATH", None)
        else:
            os.environ["FILM_DONOR_PATH"] = old_env
        _restore_mocks()


def _t27_stocks_payload_offer_id():
    """F27 форма set_stock на проводе: item.offer_id (артикул донора), НЕ sku.

    Регресс живого бага 08.09: payload шёл {"sku": article} → Ozon /v2/products/stocks
    поле sku не знает → HTTP 200 'sent', а остаток НЕ лег (has_stock=false «Нет на складе»).
    """
    d, old, fx = _sandbox()
    sent = []

    def fake_set(stocks, dry=True, commit=False, timeout=60):
        sent.append(list(stocks))
        return {"status": "sent"}

    try:
        F.first_warehouse_id = lambda: (1020005029808130, "Карго.Вавилова")
        F.W.set_stock = fake_set
        built = F.build_cards(F.load_donor_rows()["rows"])
        out = _silent(lambda: F.stocks(built, count=100, dry=False, commit=True))
        if not sent:
            return False, "set_stock не вызван"
        items = sent[0]
        ok = (all("offer_id" in it and "sku" not in it for it in items)
              and len(items) == 2)  # только 2 in_stock из 3 строк фикстуры
        return ok, f"payload_first={items[0] if items else None} n={len(items)}"
    finally:
        _restore(old)


TESTS = [
    ("F1 источник читается (фикстура)", _t01_fixture_ok),
    ("F2 битая строка донора → честный пропуск", _t02_broken_skip),
    ("F3 карточка собрана: dci/tid/цена-строкой/EAN/габариты мм·г", _t03_card_built),
    ("F4 модель 9048 инжектится = ARB-sku", _t04_model_9048_injected),
    ("F5 бренд по значению (нет dict id) / вид+ТНВЭД словарём / маркировка false", _t05_brand_po_znacheniyu),
    ("F6 enum материал/цвет из фактов; неизвестное → не шлём", _t06_enums_facts),
    ("F7 фото журнала (по ARB-sku) перекрывают", _t07_photos_override),
    ("F8 детерминизм + зеркальная цена = build_product ЯМ", _t08_determinism),
    ("F9 EAN-13 валиден и детерминирован", _t09_ean_valid),
    ("F10 OZ2 жёсткий блок без категории", _t10_oz2_block),
    ("F11 РУБИКОН dry — сеть не открыта", _t11_rubicon_dry),
    ("F12 живой залив: task_id→imported", _t12_live_imported),
    ("F13 200≠успех: failed+errors → честный failure", _t13_200_ne_uspeh),
    ("F14 результат неизвестен честно (не фантом-успех)", _t14_unknown_honest),
    ("F15 остаток не выдумываем (count обязателен)", _t15_count_obyazaten),
    ("F16 склад не выдумываем (нет склада → блок)", _t16_sklad_ne_vyiduman),
    ("F17 остатки dry: только in_stock донора", _t17_stocks_dry),
    ("F18 остатки живые + наличие честно (только in_stock)", _t18_stocks_live_nalechie),
    ("F19 poured_pids честно (живой ДОНОР; пусто → [])", _t19_poured_honest),
    ("F20 photo_urls_by_sku (ARB→http; пусто → {})", _t20_photo_journal),
    ("F21 SKU на Ozon = артикул донора (offer_id=article, реальный товар)", _t21_offer_is_article),
    ("F22 две цены: зачёркнутая old_price = цена + 500₽", _t22_two_prices),
    ("F23 полная карточка из фактов: аннотация/страна/длина/ширина/единиц", _t23_full_card_rich),
    ("F24 МАТРИЦА-БИБЛИОТЕКА: связка SKU↔донор + shelf; пусто → не пишем", _t24_library_cycle),
    ("F25 витрина «Продаётся» честно (visible True) + pour_mark_shelf", _t25_shelf_status_honest),
    ("F26a scan_donor_complete: донабор полного набора ретраями (мёрж по pid)", _t26a_scan_donor_complete_merges),
    ("F26b ГЕЙТ ПОЛНОТЫ: недо-скан → АБОРТ, ни одного write (set_stock не зван)", _t26b_gate_abort_partial),
    ("F26c ГЕЙТ ПОЛНОТЫ: полный скан → гейт пропускает (stocks уходит)", _t26c_gate_passes_full),
    ("F27 форма set_stock: offer_id артикула (НЕ sku) — регресс 08.09 'sent но не лёг'", _t27_stocks_payload_offer_id),
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
    print(f"\nOZON FILM ZALIV · {passed}/{len(TESTS)} зелёных")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

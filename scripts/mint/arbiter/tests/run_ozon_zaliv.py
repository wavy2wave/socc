#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · ЗАЛИВ (ozon_zaliv_v1) — герметичные приёмки цикла залива.

Законы:
  Z1  источник: master-файл читается (fail-soft → честная _error).
  Z2  распределение категорий считает верно.
  Z3  select_category фильтрует ТОЛЬКО ленту.
  Z4  карточка ленты собрана: dci/tid/цена-строкой/EAN; meta.can_build=True, need_mapping=False.
  Z5  ЧЕСТНОСТЬ бренда: ExpressGo шлём ПО ЗНАЧЕНИЮ — в attribute НЕТ dictionary_value_id (в словаре его нет,
      не выдумываем id). Тип/ТН ВЭД — со словарными id (они в словаре есть, проверено живьём).
  Z6  EAN-13 валиден (контрольная цифра), детерминирован (тот же sku → тот же код).
  Z7  OZ2 жёсткий блок: категории нет → item=None + need_mapping=True (не исключение, законное состояние).
  Z8  РУБИКОН dry: fill(dry=True) НЕ открывает сеть — create_product зовётся с dry=True commit=False.
  Z9  живой залив: task_id → poll import_info → imported/errors; успех = status=='imported' AND pid>0 AND errors==[].
  Z10 200≠успех: import_info вернул failed+errors → честный failure, ok=False (не «всё хорошо»).
  Z11 результат НЕ известен честно: import_info пуст за все попытки → _error «неизвестен», не фантом-успех.
  Z12 остаток не выдумываем: count не задан → блок.
  Z13 склад не выдумываем: склада нет → блок «склад не создан» (не 0, не «нет данных»).
  Z14 остатки dry: склад есть + count → payload собран, ok dry.
  Z15 остатки живые: set_stock зовётся с dry=False commit=True.
  Z16 «Наличие (shop)» честно: только 'В наличии' = True; 'Нет в наличии'/None = False.

Сухо: env-песочница (CARGO_MASTER_PATH→фикстура), сети нет, канон не пишется.
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

import ozon_zaliv_v1 as Z

PASS = "✅ PASS"
FAIL = "❌ FAIL"

TAPE_ROWS = [
    {"Артикул": "9600055-1",
     "Наименование (Ozon)": "Упаковочная, для коробок и отправлений: Клейкая лента (скотч), 48 мм × 66 м, 45 мкм, кристально-прозрачный",
     "Категории": "Клейкая лента", "Цена продажи, ₽": 1740, "Наличие (shop)": "В наличии",
     "Фото без вотермарка": "https://sp.cargo-avto.ru/upload/1.jpg", "Вес, кг": "0.153"},
    {"Артикул": "9600071-1",
     "Наименование (Ozon)": "Клейкая лента (скотч), 48 мм × 66 м (упаковочная), 45 мкм, прозрачный",
     "Категории": "Клейкая лента", "Цена продажи, ₽": 1650, "Наличие (shop)": "В наличии",
     "Фото без вотермарка": "https://sp.cargo-avto.ru/upload/2.jpg", "Вес, кг": "0.163"},
    {"Артикул": "9605968-1",
     "Наименование (Ozon)": "Клейкая лента (скотч) 48 мм × 33 м, 45 мкм, прозрачный",
     "Категории": "Клейкая лента", "Цена продажи, ₽": 1570, "Наличие (shop)": "Нет в наличии",
     "Фото без вотермарка": "https://sp.cargo-avto.ru/upload/3.jpg", "Вес, кг": "0.089"},
]
OTHER_ROWS = [
    {"Артикул": "9610000-1", "Наименование (Ozon)": "Пузырчатая плёнка 1,2 м × 100 м",
     "Категории": "Воздушно-пузырьковая плёнка", "Цена продажи, ₽": 3400,
     "Наличие (shop)": "В наличии", "Фото без вотермарка": "https://sp.cargo-avto.ru/upload/4.jpg"},
]


def _sandbox():
    d = Path(tempfile.mkdtemp(prefix="ozon_zaliv_test_"))
    fx = d / "fixture.json"
    fx.write_text(json.dumps(TAPE_ROWS + OTHER_ROWS, ensure_ascii=False), encoding="utf-8")
    env = {"CARGO_MASTER_PATH": str(fx)}
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    return d, old, fx


def _restore(old):
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


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


def _t01_master_ok():
    d, old, fx = _sandbox()
    try:
        m = Z.load_master()
        return m["ok"] and len(m["rows"]) == 4 and m["path"] == str(fx), f"rows={len(m.get('rows', []))}"
    finally:
        _restore(old)


def _t02_distribution():
    d, old, fx = _sandbox()
    try:
        dist = Z.category_distribution(Z.load_master()["rows"])
        return dist.get("Клейкая лента") == 3 and dist.get("Воздушно-пузырьковая плёнка") == 1, str(dist)
    finally:
        _restore(old)


def _t03_select_tape():
    d, old, fx = _sandbox()
    try:
        sel = Z.select_category(Z.load_master()["rows"])
        return len(sel) == 3 and all("лент" in str(r["Категории"]).lower() for r in sel), f"sel={len(sel)}"
    finally:
        _restore(old)


def _t04_card_built():
    d, old, fx = _sandbox()
    try:
        built = Z.build_cards(Z.select_category(Z.load_master()["rows"]))
        b = built[0]
        item, m = b["item"], b["meta"]
        ok = (item is not None and item.get("description_category_id") == Z.TAPE_DCI
              and item.get("type_id") == Z.TAPE_TID
              and item.get("price") == "1740" and item.get("vat") == "0"
              and item.get("barcode") and len(item["barcode"]) == 13
              and m["can_build"] is True and m["need_mapping"] is False
              and "ExpressGo" in item.get("name", ""))
        return ok, f"dci={item.get('description_category_id')} price={item.get('price')} name_has_brand={'ExpressGo' in (item.get('name') or '')}"
    finally:
        _restore(old)


def _t05_brand_po_znacheniyu():
    d, old, fx = _sandbox()
    try:
        built = Z.build_cards(Z.select_category(Z.load_master()["rows"]))
        brand = _attr(built, 0, 85)          # Бренд
        tip = _attr(built, 0, 8229)          # Тип
        tn = _attr(built, 0, 22232)          # ТН ВЭД
        bv = (brand.get("values") or [{}])[0]
        tv = (tip.get("values") or [{}])[0]
        tnv = (tn.get("values") or [{}])[0]
        brand_honest = bv.get("value") == "ExpressGo" and bv.get("dictionary_value_id") is None
        tip_honest = tv.get("dictionary_value_id") == Z.TAPE_TID and tv.get("value") == "Клейкая лента"
        tn_honest = tnv.get("dictionary_value_id") == Z.TN_VED_DVID and "3919900000" in str(tnv.get("value"))
        return brand_honest and tip_honest and tn_honest, \
               f"brand={bv} tip={tv} tn={tnv}"
    finally:
        _restore(old)


def _t06_ean_valid():
    d, old, fx = _sandbox()
    try:
        from uniqueizer_v1 import gen_ean13
        e = gen_ean13("9600055-1")
        s = sum((1 if i % 2 == 0 else 3) * int(ch) for i, ch in enumerate(e[:12]))
        check = (10 - (s % 10)) % 10
        return len(e) == 13 and e[0] == "2" and int(e[12]) == check and e == gen_ean13("9600055-1"), f"ean={e}"
    finally:
        _restore(old)


def _t07_oz2_block():
    d, old, fx = _sandbox()
    try:
        import ozon_card_v1 as card
        prod = {"offer_id": "NO-CAT-1", "name": "Странный товар без категории", "price": 500}
        r = card.to_item(prod, cats={})     # справочник пуст → категории нет → жёсткий блок
        m = r["meta"]
        return r["item"] is None and m["need_mapping"] is True and m["can_build"] is False \
            and m.get("block_reason") and "авто-категории" in m["block_reason"], \
            f"item={r['item']} need_mapping={m['need_mapping']}"
    finally:
        _restore(old)


def _t08_rubicon_dry():
    d, old, fx = _sandbox()
    try:
        calls = {}
        def fake_cp(items, dry=True, commit=False, timeout=60):
            calls["dry"], calls["commit"] = dry, commit
            return {"status": "dry", "would_send": items}
        Z.W.create_product = fake_cp
        built = Z.build_cards(Z.select_category(Z.load_master()["rows"]))
        out = _silent(lambda: Z.fill(built, dry=True, commit=False))
        return calls.get("dry") is True and calls.get("commit") is False and "СУХО" in out, \
               f"calls={calls} out_has_dry={'СУХО' in out}"
    finally:
        _restore(old)


def _t09_live_imported():
    d, old, fx = _sandbox()
    try:
        Z.W.create_product = lambda items, dry=True, commit=False, timeout=60: \
            {"status": "sent", "response": {"result": {"task_id": 123456}}}
        Z.W.import_info = lambda task_id, timeout=30: [
            {"offer_id": "9600055-1", "status": "imported", "product_id": 777001, "errors": []},
            {"offer_id": "9600071-1", "status": "imported", "product_id": 777002, "errors": []},
        ]
        built = Z.build_cards(Z.select_category(Z.load_master()["rows"]))
        out = _silent(lambda: Z.fill(built, dry=False, commit=True))
        res = {"out": out}
        ok = "product_id=777001" in out and "ошибок 0" in out
        return ok, out.strip().splitlines()[0]
    finally:
        _restore(old)


def _t10_200_ne_uspeh():
    d, old, fx = _sandbox()
    try:
        Z.W.create_product = lambda items, dry=True, commit=False, timeout=60: \
            {"status": "sent", "response": {"result": {"task_id": 1}}}
        Z.W.import_info = lambda task_id, timeout=30: [
            {"offer_id": "9600055-1", "status": "failed", "product_id": 0,
             "errors": ["ТН ВЭД не совпадает", "Название модели обязательно"]},
        ]
        built = Z.build_cards(Z.select_category(Z.load_master()["rows"]))
        out = _silent(lambda: Z.fill(built, dry=False, commit=True))
        ok = "ошибок 1" in out and "ТН ВЭД не совпадает" in out
        return ok, out.strip().splitlines()[0]
    finally:
        _restore(old)


def _t11_unknown_honest():
    d, old, fx = _sandbox()
    try:
        Z.W.create_product = lambda items, dry=True, commit=False, timeout=60: \
            {"status": "sent", "response": {"result": {"task_id": 9}}}
        Z.W.import_info = lambda task_id, timeout=30: []     # вечно пусто
        built = Z.build_cards(Z.select_category(Z.load_master()["rows"]))
        out = _silent(lambda: Z.fill(built, dry=False, commit=True, poll_attempts=2, poll_delay=0))
        ok = "НЕ известен" in out and "imported" not in out
        return ok, out.strip()[:90]
    finally:
        _restore(old)


def _t12_count_obyazaten():
    d, old, fx = _sandbox()
    try:
        built = Z.build_cards(Z.select_category(Z.load_master()["rows"]))
        out = _silent(lambda: Z.stocks(built, count=None, dry=True, commit=False))
        return "count не задан" in out, out.strip()[:80]
    finally:
        _restore(old)


def _t13_sklad_ne_vyiduman():
    d, old, fx = _sandbox()
    try:
        Z.first_warehouse_id = lambda: (None, None)     # склада в кабинете нет
        built = Z.build_cards(Z.select_category(Z.load_master()["rows"]))
        out = _silent(lambda: Z.stocks(built, count=5, dry=True, commit=False))
        return "склад не создан" in out and "0" in out, out.strip().splitlines()[0]
    finally:
        _restore(old)


def _t14_stocks_dry():
    d, old, fx = _sandbox()
    try:
        Z.first_warehouse_id = lambda: (1020005024209370, "MSK EXPRESS")
        Z.W.set_stock = lambda stocks, dry=True, commit=False, timeout=60: {"status": "dry"}
        built = Z.build_cards(Z.select_category(Z.load_master()["rows"]))
        out = _silent(lambda: Z.stocks(built, count=7, dry=True, commit=False))
        # только 2 позиции «В наличии» из 3
        ok = ("1020005024209370" in out) and ("9600055-1 → 7" in out) and ("9605968-1" not in out)
        return ok, out.strip().splitlines()[0]
    finally:
        _restore(old)


def _t15_stocks_live():
    d, old, fx = _sandbox()
    try:
        calls = {}
        Z.first_warehouse_id = lambda: (1020005024209370, "MSK EXPRESS")
        Z.W.set_stock = lambda stocks, dry=True, commit=False, timeout=60: \
            (calls.__setitem__("dry", dry), calls.__setitem__("commit", commit), {"status": "sent"})[2]
        built = Z.build_cards(Z.select_category(Z.load_master()["rows"]))
        out = _silent(lambda: Z.stocks(built, count=3, dry=False, commit=True))
        return calls.get("dry") is False and calls.get("commit") is True and "ЖИВОЙ" in out, f"calls={calls}"
    finally:
        _restore(old)


def _t16_nalechie_chestno():
    d, old, fx = _sandbox()
    try:
        return (Z._in_stock({"Наличие (shop)": "В наличии"}) is True
                and Z._in_stock({"Наличие (shop)": "Нет в наличии"}) is False
                and Z._in_stock({"Наличие (shop)": None}) is False
                and Z._in_stock({"Наличие (shop)": "нет"}) is False), "ok"
    finally:
        _restore(old)


TESTS = [
    ("Z1 источник читается", _t01_master_ok),
    ("Z2 распределение категорий", _t02_distribution),
    ("Z3 фильтр только лента", _t03_select_tape),
    ("Z4 карточка ленты собрана", _t04_card_built),
    ("Z5 бренд по значению (нет dict id) / тип+ТНВЭД со словарём", _t05_brand_po_znacheniyu),
    ("Z6 EAN-13 валиден и детерминирован", _t06_ean_valid),
    ("Z7 OZ2 жёсткий блок без категории", _t07_oz2_block),
    ("Z8 РУБИКОН dry — сеть не открыта", _t08_rubicon_dry),
    ("Z9 живой залив: task_id→imported", _t09_live_imported),
    ("Z10 200≠успех: failed+errors → честный failure", _t10_200_ne_uspeh),
    ("Z11 результат неизвестен честно (не фантом-успех)", _t11_unknown_honest),
    ("Z12 остаток не выдумываем (count обязателен)", _t12_count_obyazaten),
    ("Z13 склад не выдумываем (нет склада → блок)", _t13_sklad_ne_vyiduman),
    ("Z14 остатки dry: payload собран", _t14_stocks_dry),
    ("Z15 остатки живые: гейт открыт", _t15_stocks_live),
    ("Z16 наличие честно ('В наличии' только)", _t16_nalechie_chestno),
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
    print(f"\nOZON ЗАЛИВ · {passed}/{len(TESTS)} зелёных")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

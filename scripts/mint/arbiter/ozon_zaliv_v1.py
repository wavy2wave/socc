#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON ZALIV V1 — цикл залива товаров на кабинет Ozon (зеркало ymarket_zaliv_source_v1).

ИСТОЧНИК — НЕ живой скан донора (у ЯМ — CargoAvtoAdapter.scan), а ГОТОВЫЙ файл
  ~/parsers/parsed_data/CARGO_COLLECTION_2026-09-07/cargo_master_products.json
  (205 Ozon-ready товаров: имя/цена/фото/вес уже посчитаны), env CARGO_MASTER_PATH.

ЦИКЛ (дословно оператора): заливай товары на кабинет → склад → обнови остатки туда.
  • Фаза FILL    — POST /v3/product/import + опрос import_info (склад НЕ нужен).
  • Фаза STOCKS  — POST /v2/products/stocks на warehouse_id склада (склад ОБЯЗАТЕЛЕН; id НЕ выдумываем —
                   только из /v2/warehouse/list живого кабинета, закон OZ2 «склад не выдумываем»).

ЗАКОНЫ ЧЕСТНОСТИ (проверено живьём 2026-09-08, кабинет 5473485):
  • RUBICON: реальная сеть ТОЛЬКО при not dry AND commit. По умолчанию dry — 0 запросов, 0₽.
  • 200 ≠ успех: читаем errors[]/warnings[] из тела, а не HTTP-код (закон OZ-уроков).
  • Категорию НЕ выдумываем (OZ2): description_category_id+type_id из живого дерева (ниже — живьём).
  • dictionary_value_id НЕ выдумываем: бренд ExpressGo в словаре брендов категории ОТСУТСТВУЕТ
    (просканировано 20 375 значений, есть 'Express' — не 'ExpressGo') → шлём ПО ЗНАЧЕНИЮ
    (value='ExpressGo', без id). Ozon сам сматчит существующий бренд или заведёт новый.
  • EAN-13 — СВОЙ (uniqueizer_v1.gen_ean13, префикс 2 = внутреннее/ограниченное обращение, не
    сталкивается с заводскими GTIN). Это НЕ выдумка чужого штрихкода: товар НАШ (бренд ExpressGo),
    код присваиваем сами — легальный рычаг (урок ЯМ «штрихкод = рычаг»).
  • Габариты: у ленты есть только вес (коробочных Д*Ш*В нет) → габаритный блок НЕ шлём (честный None),
    Ozon зафиксирует реальные при отгрузке. Не выдумываем размер коробки.
  • Имя: 1-в-1 от донора + суффикс 'ExpressGo' (без потерь размера/единиц — урок кард-нейма ЯМ).
  • Цена: «Цена продажи, ₽» из файла как есть (уже считана с комиссией 40% + логистикой).
  • Остаток (STOCKS): count НЕ выдумываем — обязательный параметр --count (или явный --stock N).
  • Склад: в магазине 5473485 складов 0 (живая проверка) — создание только в кабинете (API 404 на все
    версии create). До появления склада STOCKS честно блокируется.

Entrypoints (все dry по умолчанию; живьё-по-слову --commit):
  python3 ozon_zaliv_v1.py --categories            # распределение категорий в мастере (0₽)
  python3 ozon_zaliv_v1.py --check-warehouse       # /v2/warehouse/list живьём (0₽ GET)
  python3 ozon_zaliv_v1.py --fill                  # СУХОЙ залив: карточки собраны, ничего не летит
  python3 ozon_zaliv_v1.py --fill --commit         # ЖИВОЙ залив (RUBICON: слово оператора)
  python3 ozon_zaliv_v1.py --stocks --count N      # СУХИЕ остатки на склад (показать payload)
  python3 ozon_zaliv_v1.py --stocks --count N --commit   # ЖИВЫЕ остатки (склад обязан существовать)
  python3 ozon_zaliv_v1.py --warehouse             # печать warehouse_id из живого кабинета
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ozon_card_v1 as card
import ozon_hands_write_v1 as W
from uniqueizer_v1 import gen_ean13

MASTER_DEFAULT = Path.home() / "parsers/parsed_data/CARGO_COLLECTION_2026-09-07/cargo_master_products.json"

HOUSE_BRAND = "ExpressGo"   # бренд оператора везде (дословно)

# ── Категория «Клейкая лента» (ОТЛОВЛЕНА живьём 2026-09-08, /v1/description-category/tree + /attribute) ──
TAPE_DCI = 86727623     # description_category_id
TAPE_TID = 94550        # type_id «Клейкая лента» (в словаре id совпадает со значением, проверено)
# ТН ВЭД 3919900000 (id 971397921): «лента из пластмасс, самоклеящаяся, в рулонах или нет» — фит для скотча
TN_VED_DVID = 971397921

TAPE_PROFILE = {
    "attr_constants": {
        # Бренд — ПО ЗНАЧЕНИЮ: в словаре категории ExpressGo НЕТ (проверено 20 375 значений) → без id
        "бренд":          {"id": 85,    "value": HOUSE_BRAND},
        # Тип — словарный: 94550 «Клейкая лента»
        "тип":            {"id": 8229,  "dictionary_value_id": TAPE_TID, "value": "Клейкая лента"},
        # ТН ВЭД — словарный: 3919900000
        "тн_вэд":         {"id": 22232, "dictionary_value_id": TN_VED_DVID, "value": "3919900000"},
        # Нужен код маркировки — Boolean: скотч не маркируется (честный false)
        "код_маркировки": {"id": 23536, "value": "false"},
    },
    "attr_specs": {
        # Название модели — свободная строка, своя на каждый SKU (анти-склейка карточек)
        "модель": {"id": 9048, "from": "_model"},
    },
}

CATS = {
    "klejkaya-lenta": {
        "description_category_id": TAPE_DCI,
        "type_id": TAPE_TID,
        "keywords": ["клейкая лента", "скотч"],
        "profile": TAPE_PROFILE,
    },
}

CATEGORY_KEYWORDS = ("лент",)   # сегмент «Категории» начинается с «Клейкая лента»


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ИСТОЧНИК (файл мастера)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def master_path():
    return Path(__import__("os").environ.get("CARGO_MASTER_PATH", MASTER_DEFAULT))


def load_master(path=None):
    """Читать cargo_master_products.json → список строк. fail-soft → [] + _error."""
    p = Path(path) if path else master_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "rows": [], "_error": f"{type(e).__name__}: {e}"}
    rows = data if isinstance(data, list) else data.get("products", [])
    if isinstance(rows, dict):
        rows = list(rows.values())
    return {"ok": True, "rows": [r for r in rows if isinstance(r, dict)], "path": str(p)}


def category_distribution(rows):
    """Распределение по первой категории (для выбора следующей волны, 0₽)."""
    out = {}
    for r in rows:
        c = str(r.get("Категории") or "—").split(" / ")[0].strip()
        out[c] = out.get(c, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def select_category(rows, keywords=CATEGORY_KEYWORDS):
    """Отобрать строки по ключевым словам в категории. Честный пустой список если ничего нет."""
    sel = []
    for r in rows:
        cat = str(r.get("Категории") or "").lower()
        if any(k in cat for k in keywords):
            sel.append(r)
    return sel


def _in_stock(row):
    """«Наличие (shop)»: True только если строка 'В наличии'. Всё остальное — НЕ считаем наличием."""
    return (str(row.get("Наличие (shop)") or "").strip() == "В наличии")


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  СБОРКА КАРТОЧКИ (донор-строка → prod → item через ozon_card_v1.to_item)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _to_prod(row, house_brand=HOUSE_BRAND):
    """Строка мастера → prod-диктат для ozon_card_v1.to_item (поля Ozon)."""
    art = str(row.get("Артикул") or "").strip()
    name = str(row.get("Наименование (Ozon)") or row.get("Наименование") or "").strip()
    price = row.get("Цена продажи, ₽")
    img = str(row.get("Фото без вотермарка") or row.get("Фото (вотермарк, fallback)") or "").strip()
    prod = {
        "offer_id": art,
        "name": name,
        "price": price,
        "images": [img] if img else [],
        "barcode": gen_ean13(art),                     # СВОЙ EAN-13 (префикс 2), не выдумка чужого
        "house_brand": house_brand,
        "_spec": {"_model": art},                       # модель = наш артикул (анти-склейка)
    }
    return prod


def build_cards(rows, cats=None, house_brand=HOUSE_BRAND, unique_name=True):
    """Строки → список {'row','prod','item','meta'}. item=None — честный блок (need_mapping, OZ2)."""
    cats = cats if cats is not None else CATS
    out = []
    for row in rows:
        prod = _to_prod(row, house_brand=house_brand)
        r = card.to_item(prod, cats=cats, unique_name=unique_name, house_brand=house_brand)
        out.append({"row": row, "prod": prod, "item": r["item"], "meta": r["meta"]})
    return out


def items_of(built):
    """Готовые item (не None) — то, что реально полетит в /v3/product/import."""
    return [b["item"] for b in built if b["item"] is not None]


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ОТЧЁТЫ
# ══════════════════════════════════════════════════════════════════════════════════════════════

def render_build(built):
    """Человеко-отчёт сборки карточек. Ничего не пишет наружу (0₽)."""
    n = len(built)
    ok = [b for b in built if b["item"] is not None]
    blocked = [b for b in built if b["item"] is None]
    lines = []
    lines.append(f"КАРТОЧКИ · всего {n} · готово {len(ok)} · блок(OZ2, нет категории) {len(blocked)}")
    for b in ok:
        m = b["meta"]
        lines.append(
            f"  🟢 {m['offer_id']} · {m['price']}₽ · фото={'есть' if not m['missing_images'] else 'НЕТ'} · "
            f"EAN={m.get('has_barcode') and 'есть' or 'нет'} · аттрибутов {m['attrs_built']} · "
            f"имя '{b['item'].get('name', '')[:60]}'")
    for b in blocked:
        m = b["meta"]
        lines.append(f"  🔴 {m['offer_id']} · блок: {m.get('block_reason')}")
    return "\n".join(lines)


def render_fill_report(imported, failures, dry):
    """Итог залива: по каждому offer_id — imported/errors. 200≠успех — читаем errors[] (не HTTP-код)."""
    lines = []
    lines.append(f"ЗАЛИВ · {'СУХО (payload собран, 0₽)' if dry else 'ЖИВОЙ'}"
                 f" · импортировано {len(imported)} · ошибок {len(failures)}")
    for it in imported:
        lines.append(f"  ✅ {it.get('offer_id')} → product_id={it.get('product_id')}")
    for f in failures:
        lines.append(f"  ❌ {f.get('offer_id')} · status={f.get('status')} · errors={f.get('errors')}")
    return "\n".join(lines)


def render_stocks(stocks, warehouse_id, dry):
    n = len(stocks)
    return (f"ОСТАТКИ · {'СУХО (payload собран, 0₽)' if dry else 'ЖИВОЙ'} · склад {warehouse_id} · SKU {n}\n"
            + "\n".join(f"  {s.get('sku')} → {s.get('stock')}" for s in stocks))


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ФАЗЫ ЦИКЛА
# ══════════════════════════════════════════════════════════════════════════════════════════════

def check_warehouse():
    """Живое чтение складов (0₽ GET). Честно: пусто = склада нет, не «нет данных»."""
    wl = W.warehouse_list(timeout=20)
    whs = wl.get("warehouses", [])
    print(f"СКЛАДЫ (живое чтение) · ok={wl.get('ok')} · складов: {len(whs)}")
    for wh in whs:
        a = wh.get("address_info") or {}
        print(f"  id={wh.get('warehouse_id')} name={wh.get('name')!r} status={wh.get('status')} "
              f"type={wh.get('warehouse_type')} addr={a.get('address')!r}")
    if wl.get("_error"):
        print(f"  _error: {wl['_error']}")
    return whs


def first_warehouse_id():
    """Первый склад кабинета — ЕДИНСТВЕННЫЙ законный источник warehouse_id (не выдумываем)."""
    whs = W.warehouse_list(timeout=20).get("warehouses", [])
    for wh in whs:
        wid = wh.get("warehouse_id")
        if wid is not None:
            return wid, wh.get("name")
    return None, None


def fill(built, dry=True, commit=False, poll_attempts=24, poll_delay=8):
    """Фаза FILL: собрать item → /v3/product/import → опрос import_info.

    dry=True  — собрать и показать payload, 0 запросов (РУБИКОН).
    commit    — реальный залив + опрос; успех item = status=='imported' AND product_id>0 AND errors==[].
    """
    items = items_of(built)
    if not items:
        return {"ok": False, "imported": [], "failures": [], "_error": "нет готовых карточек (всё блок)"}
    res = W.create_product(items, dry=dry, commit=commit)
    if dry:
        print(render_fill_report([], [], dry=True))
        return {"ok": True, "dry": True, "items_ready": len(items)}
    if res.get("status") != "sent":
        print(render_fill_report([], [{"offer_id": "?", "status": "transport",
                                       "errors": [str(res.get("_error"))]}], dry=False))
        return {"ok": False, "imported": [], "failures": [], "_error": res.get("_error")}
    # ЖИВОЙ: получен task_id — это квитанция, НЕ карточка (OZ3: истина только в import_info).
    resp = res.get("response") or {}
    task_id = (resp.get("result") or {}).get("task_id") or resp.get("task_id")
    if task_id is None:
        msg = "task_id не получен — карточка НЕ создана (не выдаём желаемое за факт)"
        print(render_fill_report([], [{"offer_id": "?", "status": "no-task-id", "errors": [msg]}], dry=False))
        return {"ok": False, "imported": [], "failures": [], "_error": msg}
    items_info = []
    for _ in range(poll_attempts):
        items_info = W.import_info(task_id)
        if not items_info:
            time.sleep(poll_delay)
            continue
        if all(str(i.get("status")) != "pending" for i in items_info):
            break
        time.sleep(poll_delay)
    imported, failures = [], []
    for it in items_info:
        status = str(it.get("status"))
        pid = it.get("product_id") or 0
        errs = [str(e) for e in (it.get("errors") or [])]
        if status == "imported" and pid and not errs:
            imported.append(it)
        else:
            failures.append({"offer_id": it.get("offer_id"), "status": status,
                             "errors": errs, "product_id": pid})
    if not items_info:
        msg = f"import_info пуст за {poll_attempts} попыток — результат НЕ известен (честно)"
        print(msg)
        return {"ok": False, "imported": [], "failures": [], "_error": msg}
    print(render_fill_report(imported, failures, dry=False))
    return {"ok": not failures, "imported": imported, "failures": failures, "task_id": task_id}


def stocks(cards, count=None, dry=True, commit=False):
    """Фаза STOCKS: остатки «В наличии» на склад. count обязателен (не выдумываем остаток).

    Склад: warehouse_id из живого /v2/warehouse/list. Склада нет → честный блок (не 0, не «нет данных»).
    """
    if count is None:
        print("ОСТАТКИ · блок: count не задан — остаток НЕ выдумываем (--count N)")
        return {"ok": False, "_error": "count не задан"}
    try:
        cnt = int(count)
    except (TypeError, ValueError):
        print("ОСТАТКИ · блок: count не число")
        return {"ok": False, "_error": "count не число"}
    if cnt <= 0:
        print("ОСТАТКИ · блок: count должен быть > 0")
        return {"ok": False, "_error": "count ≤ 0"}
    wid, wname = first_warehouse_id()
    if wid is None:
        print("ОСТАТКИ · блок: склад не создан — складов в кабинете 0 (создать в seller.ozon.ru → "
              "Логистика). warehouse_id не выдумываем.")
        return {"ok": False, "_error": "склад не создан"}
    payload = [{"sku": c["meta"]["offer_id"], "warehouse_id": wid, "stock": cnt}
               for c in cards if _in_stock(c["row"])]
    if not payload:
        print("ОСТАТКИ · блок: среди карточек нет позиций «В наличии» — остаток ставить не на что")
        return {"ok": False, "_error": "нет позиций в наличии"}
    res = W.set_stock(payload, dry=dry, commit=commit)
    print(render_stocks(payload, wid, dry=dry))
    if dry:
        return {"ok": True, "dry": True, "payload": payload}
    if res.get("status") != "sent":
        print(f"  transport: {res.get('_error')}")
        return {"ok": False, "_error": res.get("_error")}
    return {"ok": True, "response": res.get("response")}


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════════════════════

def main(argv=None):
    ap = argparse.ArgumentParser(description="OZON ZALIV V1 — цикл залива (dry по умолчанию)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--categories", action="store_true", help="распределение категорий в мастере")
    g.add_argument("--check-warehouse", action="store_true", help="склады кабинета живьём (0₽)")
    g.add_argument("--warehouse", action="store_true", help="печать warehouse_id первого склада")
    g.add_argument("--fill", action="store_true", help="залив карточек (dry; --commit — живой)")
    g.add_argument("--stocks", action="store_true", help="остатки (dry; --commit — живой)")
    ap.add_argument("--commit", action="store_true", help="ЖИВОЙ режим (РУБИКОН: слово оператора)")
    ap.add_argument("--count", type=int, default=None, help="остаток на каждый SKU (не выдумываем)")
    ap.add_argument("--cat", default="klejkaya-lenta", help="slug категории (по умолчанию лента)")
    ap.add_argument("--limit", type=int, default=None, help="ограничить число карточек (для проверки)")
    args = ap.parse_args(argv)

    if args.categories:
        m = load_master()
        if not m["ok"]:
            print(f"master ERR: {m['_error']}"); return 1
        for c, n in category_distribution(m["rows"]).items():
            print(f"  {n:3d}  {c}")
        return 0

    if args.check_warehouse:
        check_warehouse()
        return 0

    if args.warehouse:
        wid, name = first_warehouse_id()
        if wid is None:
            print("склад НЕ создан (в кабинете 0 складов) — создайте в seller.ozon.ru → Логистика")
            return 1
        print(f"warehouse_id={wid} name={name}")
        return 0

    # FILL / STOCKS требуют мастер
    m = load_master()
    if not m["ok"]:
        print(f"master ERR: {m['_error']}"); return 1
    rows = select_category(m["rows"])
    if args.limit is not None:
        rows = rows[:args.limit]

    if args.fill:
        if not rows:
            print("ЗАЛИВ · нет строк категории — блок"); return 1
        built = build_cards(rows)
        print(render_build(built))
        res = fill(built, dry=not args.commit, commit=args.commit)
        return 0 if (res.get("ok") or res.get("dry")) else 1

    if args.stocks:
        if not rows:
            print("ОСТАТКИ · нет строк категории — блок"); return 1
        built = build_cards(rows)
        res = stocks(built, count=args.count, dry=not args.commit, commit=args.commit)
        return 0 if (res.get("ok") or res.get("dry")) else 1

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

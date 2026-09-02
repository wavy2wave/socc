#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА ЖИВОГО НАЛИЧИЯ ДОНОРА (donor_stock_v1) — статья → статус склада. 0₽, без сети, чистые функции.

ЗАЧЕМ ЭТА ПРИЁМКА. Присоска cargo_avto кладёт в normalized() и sku (bx-id листинга, 9048), и article
(артикул донора, 9602037). Живая карточка — ТОЛЬКО по article: /catalog/9602037/ отдаёт 655КБ с
маркером «Интернет-магазин:», а /catalog/9048/ — HTTP 404 (проверено живьём 2026-09-01 на обоих
хостах). Пока apply_to брал sku, stock_for кормился мёртвыми URL, все карточки рождались без
stock_source (закон СКЛАДОВЩИКА «лучше ноль, чем ложь»), и присоска была слепа в сток. Законы ниже
держат ровно этот способ соврать и его соседей: precedence, обратную совместимость с донорами без
article, и то, что только 'in_stock' даёт источник наличия.

  DS1 article_beats_sku   — товар с article берёт его, НЕ sku (bx-id мёртв; живая страница по article)
  DS2 no_article_fallback — article нет (детмир/wb) → как раньше sku (обратная совместимость)
  DS3 in_stock_only       — только 'in_stock' даёт stock_source + in_stock=True (закон L3)
  DS4 on_order_is_false   — 'on_order' → in_stock=False, stock_source НЕ выдаётся (не выдумываем)
  DS5 unknown_is_none     — None → in_stock=None, stock_source НЕ выдаётся (незнание ≠ «нет»)
  DS6 parse_status_anchor — маркер «Интернет-магазин:» читается 1-в-1: в наличии → in_stock
  DS7 parse_on_order      — «под заказ» за маркером → on_order (не путаем с пунктами самовывоза)
  DS8 parse_unknown       — нет маркера / нет статуса → честный None (не «нет в наличии»)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

import donor_stock_v1 as ds        # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _item(sku="9048", article=None):
    """Синтетический normalized()-товар, как отдаёт присоска: sku=bx-id, article=артикул."""
    return {"sku": sku, "name": "Плёнка ВПП", "cost": 600.0,
            "article": article, "url": "", "stock": 0}


def ds1_article_beats_sku():
    """article есть → stock_for ищет по нему (9602037), а не по мёртвому bx-id (9048)."""
    called = {}
    def fake_fetch(pid):
        called["pid"] = pid
        return "<html>Интернет-магазин: в наличии</html>"
    save = ds.fetch
    ds.fetch = fake_fetch
    try:
        p = _item(article="9602037")
        stock_map = ds.stock_for([p["article"]], pause=0)   # применяем наличие по article
        ds.apply_to([p], stock_map)
    finally:
        ds.fetch = save
    ok = p.get("stock_source") == "донор:живой сайт" and p.get("in_stock") is True
    return ok, f"stock_source={p.get('stock_source')!r} in_stock={p.get('in_stock')}"


def ds2_no_article_fallback():
    """article нет (детмир/wb не кладут) → как раньше по sku. Обратная совместимость."""
    p = _item(article=None)
    ds.apply_to([p], {"9048": {"status": "in_stock", "human": "в наличии"}})
    ok = p.get("in_stock") is True
    return ok, f"in_stock={p.get('in_stock')} (по sku 9048, как до правки)"


def ds3_in_stock_only():
    """Только 'in_stock' даёт источник наличия. Это ядро закона L3."""
    p = _item()
    ds.apply_to([p], {"9048": {"status": "in_stock", "human": "в наличии"}})
    ok = p.get("stock_source") == "донор:живой сайт" and p.get("in_stock") is True
    return ok, f"stock_source={p.get('stock_source')!r} in_stock={p.get('in_stock')}"


def ds4_on_order_is_false():
    """'on_order' → in_stock=False (на Экспрессе под заказ = отмена по нашей вине), источник не даём."""
    p = _item()
    ds.apply_to([p], {"9048": {"status": "on_order", "human": "под заказ"}})
    ok = p.get("in_stock") is False and "stock_source" not in p
    return ok, f"in_stock={p.get('in_stock')} stock_source={p.get('stock_source', '<нет>')}"


def ds5_unknown_is_none():
    """None → in_stock=None, источник не даём. Незнание ≠ «нет в наличии» (это чинится повтором)."""
    p = _item()
    ds.apply_to([p], {"9048": {"status": None, "human": "страница не прочитана"}})
    ok = p.get("in_stock") is None and "stock_source" not in p
    return ok, f"in_stock={p.get('in_stock')} stock_source={p.get('stock_source', '<нет>')}"


def _page(after_marker):
    """Карточка донора: маркер + искомый статус сразу после (как на живом сайте)."""
    return f'<div class="shop-status">Интернет-магазин:<span> {after_marker} </span></div>'


def ds6_parse_status_anchor():
    """Разметка живого сайта 1-в-1: «Интернет-магазин: в наличии» → in_stock."""
    r = ds.parse_stock(_page("в наличии"))
    ok = r["status"] == "in_stock"
    return ok, f"status={r['status']} · {r['human']}"


def ds7_parse_on_order():
    """«под заказ» за маркером → on_order, не путаем со статусами пунктов самовывоза."""
    r = ds.parse_stock(_page("под заказ"))
    ok = r["status"] == "on_order"
    return ok, f"status={r['status']} · {r['human']}"


def ds8_parse_unknown():
    """Маркера нет → None (незнание), а не «нет в наличии». Маркер есть, статуса нет → None."""
    r1 = ds.parse_stock("<html>страница без маркера</html>")
    r2 = ds.parse_stock("<html>Интернет-магазин:<span> скидка 50% </span></html>")
    ok = r1["status"] is None and r2["status"] is None
    return ok, f"без маркера={r1['status']} · статус не распознан={r2['status']}"


ALL = [
    ("DS1", "article_beats_sku", ds1_article_beats_sku),
    ("DS2", "no_article_fallback", ds2_no_article_fallback),
    ("DS3", "in_stock_only", ds3_in_stock_only),
    ("DS4", "on_order_is_false", ds4_on_order_is_false),
    ("DS5", "unknown_is_none", ds5_unknown_is_none),
    ("DS6", "parse_status_anchor", ds6_parse_status_anchor),
    ("DS7", "parse_on_order", ds7_parse_on_order),
    ("DS8", "parse_unknown", ds8_parse_unknown),
]


def main():
    print("🎯 ЖИВОЕ НАЛИЧИЕ ДОНОРА · статья → статус склада (герметично, 0₽, без сети)")
    passed = 0
    for code, name, fn in ALL:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        passed += 1 if ok else 0
        print(f"   {_passed(ok)} {code:<4} {name:<20} {detail}")
    total = len(ALL)
    print(f"\n   {'✅' if passed == total else '❌'} {passed}/{total} законов держатся")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

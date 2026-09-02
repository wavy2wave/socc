#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА ПРИСОСКИ К ДОНОРУ (suppliers/cargo_avto_v1) — листинг сайта → normalized(). 0₽, без сети.

ЗАЧЕМ ЭТА ПРИЁМКА ВООБЩЕ ПОЯВИЛАСЬ. Адаптер стоял с меткой proven=True и «70 товаров» в шапке, а
живьём 2026-08-31 отдавал 11 — и ни одного товара категории: одни кросс-селл-виджеты. Причина была
в одной цифре: `seg = seg[:8000]`. Сайт растолстел разметкой картинок, <meta itemprop="price"> уехал
на смещение ~9300 внутри блока ~16,6 КБ, цена не находилась, а `if cost <= 0: continue` выбрасывал
товар МОЛЧА. Потом голосование «доминирующий tid = категория» выигрывал виджет — и присоска честно
докладывала об успехе, присосавшись не туда. Отсюда законы ниже: каждый ловит ровно тот способ
соврать, который уже случился. Всё герметично — фикстура HTML, ни одного GET.

  РАЗБОР БЛОКА (parse_catalog)
    CA1  price_beyond_window   — цена на смещении >8000 в блоке НЕ теряется (замок против seg[:8000])
    CA2  cost_is_tier_from_one — cost = ступень «от 1», НЕ оптовая (железный закон поштучного выкупа)
    CA3  tiers_ladder_whole    — лестница разобрана целиком, порядок по min, data-max="" → None
    CA4  url_is_article        — url = /catalog/{АРТИКУЛ}/ с сайта (pid-URL мёртв, проверено живьём)
    CA5  no_link_no_lie        — ссылки нет в разметке → url пустой, синтетическую НЕ выдумываем
    CA6  article_parsed        — артикул донора вынут (ключ карточки, URL и сверки с реестром)
    CA7  stock_always_zero     — stock=0 всегда (закон СКЛАДОВЩИКА «лучше ноль чем ложь»)
    CA8  dims_raw_as_written   — dims_raw как в названии (рулон, НЕ посылка — блокер T5)
    CA9  no_price_skipped      — блок без цены пропущен (не выдумываем 0₽ = «бесплатно»)
    CA10 no_pid_skipped        — промо-плитка без bx-id пропущена
    CA11 tags_between_price    — ₽-фолбэк видит цену, когда между числом и ₽ стоят теги

  СКАН КАТЕГОРИИ (scan)
    CA12 grid_main_dominant    — доминирующий tid = категория (main), прочие = related, main первыми
    CA13 dupes_dont_page       — страница без НОВЫХ товаров категории останавливает пагинацию
    CA14 no_slug_no_scan       — без slug присоска молчит (категорийный донор), сеть не трогает
    CA15 window_guard_sane     — BLOCK_WINDOW ≥ 2× живого блока (предохранитель, а не удавка)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
for p in (str(ARB), str(ARB / "suppliers")):
    if p not in sys.path:
        sys.path.insert(0, p)

import cargo_avto_v1 as ca      # noqa: E402

TID_MAIN = "3966226736"         # template-хеш сетки категории (как на живом сайте)
TID_WIDGET = "1155442200"       # template-хеш виджета «сопутствующие»
FAT = "x" * 9000                # тот самый разметочный жир (data-img-config), из-за которого всё легло


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _tier_html(mn, mx, price):
    """Ступень лестницы — разметка 1-в-1 как на сайте (число и ₽ разделены тегами)."""
    return (f'<div class="price__range"><span>от {mn}{" до " + str(mx) if mx != "" else ""} </span></div>'
            f'<div class="price__row"><div class="price__new">'
            f'<span data-min="{mn}" data-max="{mx}" class="price__new-val">   {price:.0f} ₽'
            f'<meta itemprop="price" content="{price:.0f}">'
            f'<meta itemprop="priceCurrency" content="RUB"></span></div></div>')


def _block(pid="9048", tid=TID_MAIN, name="Воздушно пузырьковая пленка, 50*0.3 м «БаблБокс», 60 г/м²",
           tiers=((1, 14, 600), (15, 24, 580), (25, "", 540)), href="/catalog/9602037/",
           art="9602037", fat=FAT, ru_price_only=False, with_id=True):
    """Один блок каталога. Порядок элементов как в живом HTML: жир картинок → цена → имя → артикул."""
    head = f'class="catalog-block__item bordered" id="bx_{tid}_{pid}">' if with_id \
        else 'class="catalog-block__item promo-tile">'
    parts = [head, f"<div class=\"img\" data-img-config='{fat}'></div>"]
    if href:
        parts.append(f'<a href="{href}" class="catalog-block__link">')
    if ru_price_only:                       # цена есть, но БЕЗ meta и БЕЗ лестницы: 600</span> … ₽
        parts.append('<div class="price"><span class="price__new-val">600</span><span>&nbsp;₽</span></div>')
    else:
        parts.append('<div class="prices__table">')
        parts.extend(_tier_html(mn, mx, pr) for mn, mx, pr in tiers)
        parts.append("</div>")
    parts.append(f'<meta itemprop="name" content="{name}">')
    parts.append(f'<meta itemprop="description" content="{name}">')
    if art:
        parts.append(f'<span class="art">Арт.&nbsp;</span> <span data-value="{art}">{art}</span>')
    parts.append("</a></div>")
    return "".join(parts)


def _page(*blocks, pagen="PAGEN_4=1"):
    """Страница листинга: шапка + блоки. pagen=None → компонента пагинации в разметке нет."""
    return ("<html><body>" + (f'<div class="pagination" data-url="?{pagen}"></div>' if pagen else "")
            + "<div>" + "".join(blocks) + "</div></body></html>")


def _one(**kw):
    rows = ca.parse_catalog(_page(_block(**kw)), limit=40)
    return rows[0] if rows else None


# ─────────────────────────── РАЗБОР БЛОКА ───────────────────────────

def ca1_price_beyond_window():
    """Цена лежит за 8000-м символом блока (как на живом сайте) — товар обязан дойти живым."""
    html = _page(_block())
    seg = html.split('class="catalog-block__item ')[1]
    off = seg.find('itemprop="price"')
    p = _one()
    ok = off > 8000 and p is not None and p["cost"] == 600.0
    return ok, f"цена на смещении {off} (>8000) → {'товар есть, ' + str(p['cost']) + '₽' if p else 'ПОТЕРЯН'}"


def ca2_cost_is_tier_from_one():
    """cost = 600 (ступень «от 1»), а НЕ 540 (от 25 шт): заранее не закупаем, выкуп поштучный."""
    p = _one()
    ok = p["cost"] == 600.0
    return ok, f"cost={p['cost']} (ждём 600 «от 1», не 540 оптовую)"


def ca3_tiers_ladder_whole():
    """Лестница едет рядом целиком: 3 ступени, по возрастанию min, «от 25 и выше» → max=None."""
    t = _one()["price_tiers"]
    ok = (len(t) == 3 and [x["min"] for x in t] == [1, 15, 25]
          and t[2]["max"] is None and t[2]["price"] == 540.0)
    return ok, f"ступеней={len(t)} mins={[x['min'] for x in t]} последняя_max={t[2]['max'] if len(t) > 2 else '—'}"


def ca4_url_is_article():
    """URL берём с сайта: /catalog/9602037/ (артикул). Синтетический /catalog/9048/ (pid) — мёртв."""
    p = _one()
    ok = p["url"] == ca.HOST + "/catalog/9602037/" and "9048" not in p["url"]
    return ok, f"url={p['url']}"


def ca5_no_link_no_lie():
    """Ссылки в разметке нет → url пустой. Мёртвую /catalog/{pid}/ не выдумываем (было именно так)."""
    p = _one(href="", art="9602037")
    ok = p["url"] == ""
    return ok, f"url={p['url']!r} (ждём пусто, не синтетику)"


def ca6_article_parsed():
    """Артикул донора вынут из блока — им живёт URL карточки и сверка с реестром offerId↔донор."""
    p = _one()
    ok = p["article"] == "9602037" and p["sku"] == "9048"
    return ok, f"article={p['article']} · sku(bx-id)={p['sku']} — разные сущности, обе на месте"


def ca7_stock_always_zero():
    """stock=0 всегда: в листинге наличие пунктов самовывоза, путать с нашим складом нельзя."""
    p = _one()
    ok = p["stock"] == 0
    return ok, f"stock={p['stock']} (живое наличие — дело donor_stock, не листинга)"


def ca8_dims_raw_as_written():
    """dims_raw = «50*0.3 м» как в названии: это РУЛОН. ОВХ посылки считает отдельный слой (T5)."""
    p = _one()
    ok = p["dims_raw"] == "50*0.3 м"
    return ok, f"dims_raw={p['dims_raw']!r} (сырьё, не подстановка в карточку)"


def ca9_no_price_skipped():
    """Цены нет вообще → товара нет. Молча ставить 0₽ = обещать бесплатную закупку."""
    rows = ca.parse_catalog(_page(_block(tiers=())), limit=40)
    return rows == [], f"строк={len(rows)} (ждём 0)"


def ca10_no_pid_skipped():
    """Промо-плитка без id=\"bx_..\" — не товар. Пропускаем, а не заводим пустышку."""
    rows = ca.parse_catalog(_page(_block(with_id=False)), limit=40)
    return rows == [], f"строк={len(rows)} (ждём 0)"


def ca11_tags_between_price():
    """Фолбэк: цена без meta и без лестницы, между числом и ₽ теги → 600₽ всё равно прочитан."""
    p = _one(ru_price_only=True)
    ok = p is not None and p["cost"] == 600.0 and p["price_tiers"] == []
    return ok, f"cost={p['cost'] if p else None} tiers={p['price_tiers'] if p else None}"


# ─────────────────────────── СКАН КАТЕГОРИИ ───────────────────────────

class _Net:
    """Шов сети: считает GET-ы и отдаёт заранее сложенные страницы. Ни одного реального запроса."""
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def __call__(self, url, timeout=20):
        self.calls.append(url)
        return self.pages[min(len(self.calls) - 1, len(self.pages) - 1)]


def _scan_with(pages, **kw):
    net = _Net(pages)
    orig = ca._get_html
    ca._get_html = net
    try:
        return ca.CargoAvtoAdapter().scan(category="plenka", limit=500, **kw), net
    finally:
        ca._get_html = orig


def ca12_grid_main_dominant():
    """3 блока сетки + 1 виджет → main=3 (доминирующий tid), related=1, main идут первыми."""
    page = _page(_block(pid="1", href="/catalog/101/", art="101"),
                 _block(pid="2", href="/catalog/102/", art="102"),
                 _block(pid="3", href="/catalog/103/", art="103"),
                 _block(pid="9", tid=TID_WIDGET, href="/catalog/109/", art="109"), pagen=None)
    rows, net = _scan_with([page])
    main = [p for p in rows if p["grid"] == "main"]
    rel = [p for p in rows if p["grid"] == "related"]
    ok = (len(main) == 3 and len(rel) == 1 and rows[0]["grid"] == "main"
          and len(net.calls) == 1)          # без PAGEN в разметке не листаем
    return ok, f"main={len(main)} related={len(rel)} GET-ов={len(net.calls)}"


def ca13_dupes_dont_page():
    """Стр.2 дала новый товар, стр.3 — только дубли → пагинация встала. Виджеты не наматывают страницы."""
    p1 = _page(_block(pid="1", href="/catalog/101/", art="101"),
               _block(pid="9", tid=TID_WIDGET, href="/catalog/109/", art="109"))
    p2 = _page(_block(pid="2", href="/catalog/102/", art="102"),
               _block(pid="9", tid=TID_WIDGET, href="/catalog/109/", art="109"))
    p3 = _page(_block(pid="9", tid=TID_WIDGET, href="/catalog/109/", art="109"))
    rows, net = _scan_with([p1, p2, p3, p3])
    main = [p["sku"] for p in rows if p["grid"] == "main"]
    ok = main == ["1", "2"] and len(net.calls) == 3 and "PAGEN_4=2" in net.calls[1]
    return ok, f"main={main} GET-ов={len(net.calls)} (ждём 3: база, стр2, стр3-сухая)"


def ca14_no_slug_no_scan():
    """Без slug сканить нечего (донор категорийный) — и в сеть за этим не ходим."""
    net = _Net([_page(_block())])
    orig = ca._get_html
    ca._get_html = net
    try:
        rows = ca.CargoAvtoAdapter().scan(limit=10)
    finally:
        ca._get_html = orig
    ok = rows == [] and net.calls == []
    return ok, f"строк={len(rows)} GET-ов={len(net.calls)} (ждём 0/0)"


def ca15_window_guard_sane():
    """Окно блока — предохранитель от патологии, а не удавка: ≥2× живого блока (16,6 КБ)."""
    ok = ca.BLOCK_WINDOW >= 33_000
    return ok, f"BLOCK_WINDOW={ca.BLOCK_WINDOW} (живой блок ~16 600 Б)"


ALL = [
    ("CA1", "price_beyond_window", ca1_price_beyond_window),
    ("CA2", "cost_is_tier_from_one", ca2_cost_is_tier_from_one),
    ("CA3", "tiers_ladder_whole", ca3_tiers_ladder_whole),
    ("CA4", "url_is_article", ca4_url_is_article),
    ("CA5", "no_link_no_lie", ca5_no_link_no_lie),
    ("CA6", "article_parsed", ca6_article_parsed),
    ("CA7", "stock_always_zero", ca7_stock_always_zero),
    ("CA8", "dims_raw_as_written", ca8_dims_raw_as_written),
    ("CA9", "no_price_skipped", ca9_no_price_skipped),
    ("CA10", "no_pid_skipped", ca10_no_pid_skipped),
    ("CA11", "tags_between_price", ca11_tags_between_price),
    ("CA12", "grid_main_dominant", ca12_grid_main_dominant),
    ("CA13", "dupes_dont_page", ca13_dupes_dont_page),
    ("CA14", "no_slug_no_scan", ca14_no_slug_no_scan),
    ("CA15", "window_guard_sane", ca15_window_guard_sane),
]


def main():
    print("🎯 ПРИЁМКА ПРИСОСКИ К ДОНОРУ · cargo-avto: листинг → normalized() (герметично, 0₽, без сети)")
    passed = 0
    for code, name, fn in ALL:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        passed += 1 if ok else 0
        print(f"   {_passed(ok)} {code:<4} {name:<22} {detail}")
    total = len(ALL)
    print(f"\n   {'✅' if passed == total else '❌'} {passed}/{total} законов держатся")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

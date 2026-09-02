#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CARGO-AVTO ADAPTER — поставщик-адаптер органа ARBITER (донор Express, shop.cargo-avto.ru).

ЗАЧЕМ. Оператор торгует по Express с донора cargo-avto. Раньше данные заходили Excel-выгрузкой
(категорийщик ест XLSX) — оператор потребовал: НИКАКИХ файлов, система сама «присасывается» к
сайту по URL категории и тянет товары. Это тот самый универсальный парсер под капотом: тот же
контракт scan()→normalized(), что у detmir/wb — ядро не трогаем, новый магазин = новый файл.

ЧЕМ БЬЁМ. Каталог на 1С-Битрикс: карточка = <div class="catalog-block__item" id="bx_NN_{pid}">,
внутри микроразметка schema.org/Product (itemprop name/url/price + <meta description> с ГАБАРИТАМИ
в названии). Это железобетонный якорь — парсим по schema.org, CSS-классы вторичны (fail-soft).

ЧЕСТНОСТЬ (законы органа):
  * cost = РОЗНИЦА cargo-avto = НАША ЗАКУПКА (см. categorist L: цену продажи предлагаем ×N сами,
    НЕ берём из файла). Цена в листинге — не одно число, а ЛЕСТНИЦА объёма: «от 1 до 14 → 600 ₽»,
    «от 15 до 24 → 580 ₽», «от 25 → 540 ₽» (data-min/data-max + <meta itemprop="price">).
    БЕРЁМ СТУПЕНЬ «от 1», потому что ЖЕЛЕЗНЫЙ ЗАКОН органа: заранее не закупаем НИКОГДА, выкуп у
    донора — ПОШТУЧНО и только под уже оплаченный заказ. Оптовая ступень в расчёт маржи не идёт
    (это была бы ложь в нашу пользу), но лестница едет рядом в price_tiers — как виден потолок.
  * stock из листинга НЕ читаем (там наличие пунктов самовывоза, путать нельзя) → stock=0,
    живое наличие берёт donor_stock_v1 по карточке (закон СКЛАДОВЩИКА «лучше ноль чем ложь»).
  * dims_raw — габариты как написаны в названии (для плёнки это размер РУЛОНА, НЕ посылки;
    ОВХ упаковки для ЯМ считает отдельный слой — не выдаём рулон за посылку). См. блокер T5.
  * 0 ₽ наружу: только GET. RUBICON цел по построению.
"""
import re
import urllib.request
from html import unescape

try:                                    # работаем и как пакетный модуль, и как отдельный CLI
    from .base_v1 import SupplierAdapter, register, normalized
except ImportError:                     # pragma: no cover
    from base_v1 import SupplierAdapter, register, normalized

HOST = "https://shop.cargo-avto.ru"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")

# Габариты в названии: «50*0.3 м», «600*400*400 мм», «150*210+40 мм» и т.п.
_DIMS_RE = re.compile(r"(\d[\d.,]*\s*(?:[*x×х/]\s*\d[\d.,+]*\s*)+(?:мм|см|м|мкм|л|кг|г/м²|г)?)", re.I)
_PRICE_RE = re.compile(r'itemprop="price"[^>]*content="([\d.]+)"')
_DESC_RE = re.compile(r'itemprop="description"\s+content="([^"]*)"')
_NAME_RE = re.compile(r'itemprop="name"[^>]*content="([^"]*)"')
_URL_RE = re.compile(r'itemprop="url"[^>]*content="([^"]*)"')
_HREF_RE = re.compile(r'href="(/catalog/\d+/)"')
_PID_RE = re.compile(r'id="bx_\d+_(\d+)"')
_TID_RE = re.compile(r'id="bx_(\d+)_\d+"')          # template-хеш блока: сетка vs виджет
_PAGEN_RE = re.compile(r'PAGEN_(\d+)=')             # номер Bitrix-компонента листинга
_FALLBACK_PRICE_RE = re.compile(r'([0-9][0-9\s ]{0,7})\s*(?:₽|&#8381)')
_ART_RE = re.compile(r'Арт\.[^<]*</span>\s*<span[^>]*>\s*([\w-]+)')   # артикул донора = ключ URL
# Ступень лестницы: <span data-min="1" data-max="14" …>600 ₽<meta itemprop="price" content="600">
_TIER_RE = re.compile(r'data-min="(\d+)"\s+data-max="(\d*)"[^>]*>.{0,400}?'
                      r'itemprop="price"\s+content="([\d.]+)"', re.S)

# ОКНО БЛОКА. Раньше стояло 8000 — и это МОЛЧА съедало каталог: сайт растолстел разметкой картинок,
# и <meta itemprop="price"> уехал на смещение ~9300 внутри блока ~16,6 КБ. Живой замер 2026-08-31 по
# vozdushno-puzyrkovaya-plenka: 31 блок → цену видно у 11, ТЕРЯЕМ 20 (всю плёнку). Дальше срабатывал
# `if cost <= 0: continue` — товары исчезали БЕЗ следа, а голосование за доминирующий tid выигрывал
# кросс-селл-виджет: скан отдавал 11 «сопутствующих» вместо ~20 товаров категории. Отсюда закон:
# окно режем ТОЛЬКО как предохранитель от патологии, с запасом ×2 от живого размера блока.
BLOCK_WINDOW = 40_000


def parse_dims(name):
    """Достаём габаритный токен из названия (сырьё для ОВХ-слоя, не подстановка)."""
    m = _DIMS_RE.search(name or "")
    return m.group(1).strip() if m else ""


def _get_html(url, timeout=20):
    """Сырой HTML (base.get даёт JSON — тут нужен текст страницы). fail-soft ''."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
    except Exception:
        return ""


def parse_price_tiers(seg):
    """Лестница объёма из блока: [{'min':1,'max':14,'price':600.0}, …] по возрастанию min.

    max=None означает «и выше» (в разметке data-max=""). Пусто → лестницы нет (fail-soft).
    """
    tiers = []
    for mn, mx, pr in _TIER_RE.findall(seg):
        try:
            tiers.append({"min": int(mn), "max": (int(mx) if mx else None), "price": float(pr)})
        except ValueError:
            continue
    tiers.sort(key=lambda t: t["min"])
    return tiers


def _cost_from(seg):
    """НАША ЗАКУПКА за 1 шт. Порядок: ступень «от 1» → первая meta-цена → ₽-число по тексту.

    Возвращает (cost, tiers). Ступень «от 1» — единственная законная: выкуп поштучный (см. шапку).
    ₽-фолбэк считаем по тексту БЕЗ тегов и БЕЗ html-сущностей: в разметке между числом и знаком ₽
    стоят и теги (</span><meta…>), и неразрывный пробел (&nbsp;) — регексп по сырому HTML не
    переступит ни то, ни другое и молча вернёт 0₽, то есть выбросит товар (уже случалось).
    """
    tiers = parse_price_tiers(seg)
    for t in tiers:
        if t["min"] <= 1:
            return t["price"], tiers
    pm = _PRICE_RE.search(seg)
    if not pm:
        pm = _FALLBACK_PRICE_RE.search(unescape(re.sub(r"<[^>]+>", " ", seg)))
    if pm:
        try:
            return float(re.sub(r"[^\d.]", "", pm.group(1))), tiers
        except ValueError:
            pass
    return 0.0, tiers


def parse_catalog(html, limit=40):
    """HTML категории → список normalized(). Якорь — блоки catalog-block__item + schema.org."""
    html = re.sub(r"<svg.*?</svg>", "", html, flags=re.S)   # режем SVG-шум, поля не съезжают
    blocks = re.split(r'class="catalog-block__item ', html)[1:]
    out = []
    for seg in blocks[: int(limit) * 2]:                    # с запасом: часть блоков — промо-плитки
        seg = seg[:BLOCK_WINDOW]
        pid = _PID_RE.search(seg)
        if not pid:
            continue
        # имя: сначала schema name, потом meta description (в ней габариты)
        desc = _DESC_RE.search(seg)
        name = (_NAME_RE.search(seg) or desc)
        name = name.group(1).strip() if name else ""
        cost, tiers = _cost_from(seg)
        if cost <= 0 or not name:
            continue
        # URL карточки — ТОЛЬКО как написан на сайте: /catalog/{АРТИКУЛ}/, а не /catalog/{pid}/.
        # Проверено живьём: pid=9048 (bx-id) даёт пустой ответ, артикул 9602037 — живую страницу.
        # Ссылки нет в разметке → отдаём пустую строку, синтетическую мёртвую НЕ выдумываем.
        um = _URL_RE.search(seg) or _HREF_RE.search(seg)
        url = um.group(1) if um else ""
        if url.startswith("/"):
            url = HOST + url
        prod = normalized(sku=pid.group(1), name=name, cost=cost, url=url, stock=0)
        prod["dims_raw"] = parse_dims(desc.group(1) if desc else name)  # ОВХ-сырьё, честно
        prod["price_tiers"] = tiers                     # лестница объёма (потолок виден, в маржу НЕ идёт)
        am = _ART_RE.search(seg)
        art = am.group(1) if am else ""
        if not art and url:                             # артикул = хвост живой ссылки
            hm = re.search(r"/catalog/(\d+)/", url)
            art = hm.group(1) if hm else ""
        prod["article"] = art                           # артикул донора: ключ карточки и URL
        tm = _TID_RE.search(seg)                        # template-хеш: делит сетку и виджеты
        prod["_tid"] = tm.group(1) if tm else ""
        out.append(prod)
        if len(out) >= int(limit):
            break
    return out


@register
class CargoAvtoAdapter(SupplierAdapter):
    key = "cargo_avto"
    title = "Cargo-Avto (донор Express)"
    secret = True                       # секретный донор — не светить в публичных логах
    proven = True                       # живой скан подтверждён 2026-08-26 (70 товаров, 4 стр)
    default_city = "msk"                # склад Express — Москва
    city_map = {"msk": "", "spb": ""}
    MAX_PAGES = 12                      # предохранитель от бесконечной пагинации

    def scan(self, *, query=None, category=None, city="msk", limit=200, page=1):
        """Скан ВСЕЙ категории по slug → normalized() со всех страниц.

        Каталог на 1С-Битрикс листается ?PAGEN_{N}={стр}. Основная сетка категории и
        виджет «сопутствующие» — РАЗНЫЕ template-хеши (id="bx_{tid}_{pid}"): доминирующий
        tid = сама категория (grid='main'), прочие = магазинный кросс-селл (grid='related').
        НЕ выбрасываем related (охват всего магазина, закон «жадный оператор») — помечаем и
        отдаём отдельно, main первыми. Дедуп по sku (виджеты повторяются на каждой странице).
        """
        if not category:
            return []                   # cargo-avto — категорийный донор, без slug сканить нечего
        base = f"{HOST}/catalog/{category.strip('/')}/"
        html1 = _get_html(base)
        if not html1:
            return []                   # fail-soft: сеть легла — конвейер живёт
        first = parse_catalog(html1, limit=10000)
        if not first:
            return []
        # доминирующий template = основная сетка категории (универсально, без хардкода слова)
        from collections import Counter
        dominant = Counter(p["_tid"] for p in first).most_common(1)[0][0]
        pm = _PAGEN_RE.search(html1)
        comp = pm.group(1) if pm else None

        seen, main, related = set(), [], []

        def _absorb(prods):
            new_main = 0
            for p in prods:
                if p["sku"] in seen:
                    continue
                seen.add(p["sku"])
                is_main = p.pop("_tid") == dominant
                p["grid"] = "main" if is_main else "related"
                if is_main:
                    main.append(p)
                    new_main += 1
                else:
                    related.append(p)
            return new_main

        _absorb(first)
        n = 2
        while comp and len(main) < int(limit) and n <= self.MAX_PAGES:
            html = _get_html(f"{base}?PAGEN_{comp}={n}")
            got = _absorb(parse_catalog(html, limit=10000)) if html else 0
            if got == 0:                # страница не дала новых товаров категории → конец
                break
            n += 1

        out = main[: int(limit)] + related      # main первыми, related сверх лимита не режем
        if query:                                # опционально сузить по слову в названии
            q = query.lower()
            out = [p for p in out if q in p["name"].lower()]
        return out


if __name__ == "__main__":              # быстрый живой зонд: python3 cargo_avto_v1.py <slug>
    import json
    import sys
    slug = sys.argv[1] if len(sys.argv) > 1 else "vozdushno-puzyrkovaya-plenka"
    rows = CargoAvtoAdapter().scan(category=slug, limit=500)
    m = [p for p in rows if p.get("grid") == "main"]
    r = [p for p in rows if p.get("grid") == "related"]
    print(f"CARGO-AVTO scan '{slug}': {len(rows)} товаров  (категория={len(m)}, сопутствующие={len(r)})")
    for p in rows:
        tag = "•" if p.get("grid") == "main" else "~"
        print(f"  {tag}[{p['sku']:>8}] {p['cost']:>7.0f}₽  {p['name'][:50]:50}  ОВХ:{p['dims_raw']}")
    print(json.dumps(rows[:2], ensure_ascii=False, indent=2))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WILDBERRIES ADAPTER — поставщик-адаптер №1 органа ARBITER (МОЙ СЕКРЕТ).

Публичные endpoints WB (БЕЗ ключей, БЕЗ авторизации) → нормализованные товары.
Это доказанный живой источник (10 реальных «дождевиков» по МСК: cost/url/feedbacks).
secret=True — не светить как источник в публичных логах/витрине.

Границы модели (честность): у публичного WB нет поля «продано N штук». Цена берётся из
product-level salePriceU/priceU (копейки) либо sizes[].price (новый формат). Остаток по
поисковому endpoint часто пуст — это ОЖИДАЕМО (точный остаток — отдельный card.wb.ru).
Поэтому сигнал спроса опирается на feedbacks (сильный прокси), остаток — бонус.
"""
import time
import urllib.parse

from .base_v1 import SupplierAdapter, register, normalized, filter_relevant

CATALOG_HOST = "https://catalog.wb.ru"
SEARCH_HOST = "https://search.wb.ru"

# Публичный поиск WB иногда отдаёт HTTP-200 с ПУСТЫМ списком товаров (edge-кэш промахнулся /
# лёгкий rate-limit) — при этом товары есть. Для вечной машины пусто ≠ «товара нет»: ограниченно
# ретраим на пустой валидный ответ с нарастающей паузой (не демон, жёсткий потолок попыток).
EMPTY_RETRIES = 3
EMPTY_BACKOFF = 0.7

# Регион → dest-код WB. dest влияет на остатки/цену/позицию; -1 = общероссийская выдача.
CITY_DEST = {
    "msk": -1257786,   # Москва и МО
    "spb": -1123300,   # Санкт-Петербург
    "ekb": -5510930,   # Екатеринбург
    "nsk": -364763,    # Новосибирск
    "kdr": -2133463,   # Краснодар
    "ru": -1,          # общероссийская выдача
}


def _price_rub(prod):
    """Цена в ₽ (копейки → рубли). Новый формат sizes[].price.total, старый salePriceU/priceU."""
    try:
        for sz in prod.get("sizes", []) or []:
            pr = (sz.get("price") or {})
            val = pr.get("total") or pr.get("product")
            if val:
                return round(val / 100.0, 2)
    except Exception:
        pass
    val = prod.get("salePriceU") or prod.get("priceU") or 0
    return round((val or 0) / 100.0, 2)


def _total_stock(prod):
    """Суммарный остаток по складам/размерам (прокси предложения; дельта = скорость ухода)."""
    total = 0
    try:
        for sz in prod.get("sizes", []) or []:
            for st in sz.get("stocks", []) or []:
                total += int(st.get("qty") or 0)
    except Exception:
        return 0
    return total


def _wb_url(nm_id):
    return f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"


def _parse_products(payload):
    """Из ответа WB достать товары (форматы catalog/search немного разнятся)."""
    if not payload:
        return []
    data = payload.get("data") or {}
    return data.get("products") or payload.get("products") or []


@register
class WildberriesAdapter(SupplierAdapter):
    key = "wildberries"
    title = "Wildberries"
    secret = True           # мой секретный источник — не светить в публичных логах/витрине
    proven = True           # доказан живой скан (10 реальных дождевиков, МСК)
    default_city = "msk"
    city_map = CITY_DEST

    def _scan_nonempty(self, url):
        """GET с ретраем на ПУСТОЙ валидный ответ WB (edge-кэш/rate-limit моргнул, а товары есть).

        Возвращает список сырых товаров. Пусто после всех попыток → [] (fail-soft, машина живёт).
        Сам http_get_json уже ретраит сетевые сбои; здесь ретраим именно «HTTP-200, но products=[]».
        """
        for attempt in range(EMPTY_RETRIES + 1):
            prods = _parse_products(self.get(url))
            if prods:
                return prods
            if attempt < EMPTY_RETRIES:
                time.sleep(EMPTY_BACKOFF * (attempt + 1))
        return []

    def scan(self, *, query=None, category=None, city="msk", limit=40, page=1):
        dest = self.city_code(city)
        if dest is None:
            dest = -1
        common = {
            "appType": 1, "curr": "rub", "dest": dest, "spp": 30,
            "sort": "popular", "page": int(page), "lang": "ru", "locale": "ru",
        }
        if query:
            q = dict(common, query=query, resultset="catalog")
            url = f"{SEARCH_HOST}/exactmatch/ru/common/v5/search?" + urllib.parse.urlencode(q)
        elif category:
            # v2-каталог WB требует shard/cat через отдельный роут; на публичном без shard
            # надёжнее subject-фильтр в поиске. Держим cat как «subject» hint в общем catalog.
            q = dict(common, subject=int(category))
            url = f"{CATALOG_HOST}/catalog/ext/v2/catalog?" + urllib.parse.urlencode(q)
        else:
            return []

        prods = self._scan_nonempty(url)
        if query:
            # Гард релевантности: под троттлингом WB отдаёт fallback-рекомендации (левые товары).
            # Режем ДО среза по limit, чтобы вернуть до limit НАСТОЯЩИХ совпадений, а не фантомы.
            prods = filter_relevant(prods, query)
        prods = prods[: int(limit)]
        out = []
        for prod in prods:
            nm = prod.get("id") or prod.get("nmId")
            if not nm:
                continue
            cost = _price_rub(prod)
            if cost <= 0:
                continue
            out.append(normalized(
                sku=nm,
                name=prod.get("name") or f"WB {nm}",
                cost=cost,
                url=_wb_url(nm),
                brand=prod.get("brand") or "",
                stock=_total_stock(prod),
                feedbacks=int(prod.get("feedbacks") or prod.get("nmFeedbacks") or 0),
                rating=float(prod.get("reviewRating") or prod.get("rating") or 0),
            ))
        return out

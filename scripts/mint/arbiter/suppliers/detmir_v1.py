#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ДЕТСКИЙ МИР ADAPTER — поставщик-адаптер органа ARBITER (не секретный, публичный магазин).

Детский мир отдаёт публичный поисковый JSON. Тот же контракт, что у WB: scan → normalized().
Ядро НЕ менялось ни на строку — вот доказательство «мощи»: новый магазин = новый файл.

proven=False: живой скан ещё не подтверждён руками (endpoint/поля Детмира надо сверить с сетью,
как мы сверяли WB). Пока схема не подтверждена — адаптер честно падает мягко в [] (fail-soft),
конвейер живёт и берёт кандидатов у WB. Подтвердим руками → ставим proven=True.
"""
import urllib.parse

from .base_v1 import SupplierAdapter, register, normalized

# Публичный поисковый хост Детского мира (сверить актуальность как делали с WB).
API_HOST = "https://api.detmir.ru/v2"


def _price_rub(item):
    """Цена из price.normal_price / price.retail_price (Детмир отдаёт рубли, не копейки)."""
    pr = (item.get("price") or {})
    val = pr.get("normal_price") or pr.get("retail_price") or item.get("price_normal") or 0
    try:
        return round(float(val or 0), 2)
    except Exception:
        return 0.0


def _dm_url(item_id, alias=""):
    slug = alias or "product"
    return f"https://www.detmir.ru/product/index/id/{item_id}/"


@register
class DetmirAdapter(SupplierAdapter):
    key = "detmir"
    title = "Детский мир"
    secret = False          # публичный магазин, не секрет
    proven = False          # живой скан ещё не подтверждён руками — сверить endpoint/поля с сетью
    default_city = "msk"
    # Детмир таргетирует по региону/магазину; коды сверяются отдельно (как dest у WB).
    city_map = {"msk": "RU-MOW", "spb": "RU-SPE", "ru": ""}

    def scan(self, *, query=None, category=None, city="msk", limit=40, page=1):
        region = self.city_code(city) or ""
        params = {
            "filter": f"categories[].alias:{category}" if category else "",
            "q": query or "",
            "limit": int(limit),
            "offset": int(max(0, page - 1) * limit),
            "sort": "popularity:desc",
            "expand": "meta",
        }
        if region:
            params["region"] = region
        params = {k: v for k, v in params.items() if v != ""}
        url = f"{API_HOST}/products?" + urllib.parse.urlencode(params)

        payload = self.get(url) or {}
        items = payload.get("items") or payload.get("products") or []
        out = []
        for it in items[: int(limit)]:
            pid = it.get("id") or it.get("code")
            if not pid:
                continue
            cost = _price_rub(it)
            if cost <= 0:
                continue
            rating = ((it.get("rating") or {}).get("rate")
                      if isinstance(it.get("rating"), dict) else it.get("rating")) or 0
            reviews = ((it.get("rating") or {}).get("count")
                       if isinstance(it.get("rating"), dict) else it.get("reviews_count")) or 0
            out.append(normalized(
                sku=pid,
                name=it.get("title") or it.get("name") or f"ДМ {pid}",
                cost=cost,
                url=_dm_url(pid, it.get("alias") or ""),
                brand=(it.get("brand") or {}).get("title") if isinstance(it.get("brand"), dict)
                      else (it.get("brand") or ""),
                stock=int(it.get("available_quantity") or 0),
                feedbacks=int(reviews or 0),
                rating=float(rating or 0),
            ))
        return out

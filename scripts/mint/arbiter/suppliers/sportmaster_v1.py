#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
СПОРТМАСТЕР ADAPTER — поставщик-адаптер органа ARBITER (не секретный, публичный магазин).

Тот же контракт scan → normalized(). Ядро не менялось — третий магазин, тот же приём.

proven=False: у Спортмастера публичный каталог строже (часто требует региональной сессии/
заголовков). Схему и endpoint надо сверить с сетью руками (как WB). Пока не подтверждено —
fail-soft в [] (конвейер живёт на WB). Подтвердим руками → proven=True. Это НЕ заглушка-обман:
контракт настоящий, парс реальных полей написан; недостаёт только сетевого подтверждения.
"""
import urllib.parse

from .base_v1 import SupplierAdapter, register, normalized

API_HOST = "https://www.sportmaster.ru/api"


def _price_rub(item):
    pr = (item.get("price") or {})
    val = (pr.get("salePrice") or pr.get("value") or item.get("salePrice")
           or item.get("price_value") or 0)
    try:
        return round(float(val or 0), 2)
    except Exception:
        return 0.0


def _sm_url(item_id):
    return f"https://www.sportmaster.ru/product/{item_id}/"


@register
class SportmasterAdapter(SupplierAdapter):
    key = "sportmaster"
    title = "Спортмастер"
    secret = False
    proven = False          # сверить endpoint/региональные заголовки с сетью, затем proven=True
    default_city = "msk"
    city_map = {"msk": "1", "spb": "2", "ru": ""}

    def scan(self, *, query=None, category=None, city="msk", limit=40, page=1):
        region = self.city_code(city) or ""
        params = {
            "query": query or "",
            "categoryId": category or "",
            "pageSize": int(limit),
            "page": int(max(1, page)),
            "sort": "popular",
        }
        if region:
            params["regionId"] = region
        params = {k: v for k, v in params.items() if v != ""}
        url = f"{API_HOST}/catalog/products?" + urllib.parse.urlencode(params)

        payload = self.get(url, headers={"X-Requested-With": "XMLHttpRequest"}) or {}
        items = (payload.get("products") or payload.get("items")
                 or (payload.get("data") or {}).get("products") or [])
        out = []
        for it in items[: int(limit)]:
            pid = it.get("id") or it.get("productId") or it.get("code")
            if not pid:
                continue
            cost = _price_rub(it)
            if cost <= 0:
                continue
            out.append(normalized(
                sku=pid,
                name=it.get("name") or it.get("title") or f"СМ {pid}",
                cost=cost,
                url=_sm_url(pid),
                brand=it.get("brand") or "",
                stock=int(it.get("stock") or it.get("available") or 0),
                feedbacks=int(it.get("reviewsCount") or it.get("reviews") or 0),
                rating=float(it.get("rating") or 0),
            ))
        return out

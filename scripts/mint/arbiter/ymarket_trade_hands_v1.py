#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ТОРГОВЫЕ РУКИ Яндекс.Маркета — то, чего органу М6 не хватало для денег.

Существующий ymarket_hands_v1 умеет СЕРЕДИНУ (каталог, карточка, витрина, индекс).
Здесь — НАЧАЛО и КОНЕЦ торгового контура:
  склады · остатки · цены · заказы · тарифы(маржа) · регионы(города) · качество.

Почему отдельный модуль, а не правка hands: закон линии «НЕ ЛОМАЙ что работает».
Тут только ДОБАВЛЕНИЕ; сетевой шов, ретраи и разбор ошибок переиспользуются из hands.

ЗАКОНЫ (механические, не пожелания):
  L1 двойной гейт: любая ЗАПИСЬ наружу требует not dry AND commit. Иначе печатаем payload.
  L2 200 ≠ успех: у Маркета ошибка приезжает в теле — всегда читаем body errors.
  L3 не выдумываем: нет данных → None/отказ, НЕ подстановка «на глаз».
  L4 батч-потолки Маркета зашиты числом: остатки 2000, цены 500, тарифы 200, sku-фильтр 500.
  L5 создать склад через API НЕЛЬЗЯ (в Partner API метода нет) — честный отказ, не имитация.

Версии путей: hands.API без префикса, поэтому здесь пути пишем с /v1 /v2 /v3 явно.
"""
from __future__ import annotations

import json
import os

import ymarket_hands_v1 as hands

# --- потолки Маркета (L4): превышение = наша ошибка, ловим ДО сети -----------
MAX_STOCKS_BATCH = 2000      # POST /v3/.../offers/stocks/update  (maxItems 2000)
MAX_PRICES_BATCH = 500       # POST /v2/businesses/.../offer-prices/updates (maxItems 500)
MAX_TARIFF_OFFERS = 200      # POST /v2/tariffs/calculate (до 200 товаров)
MAX_SKU_FILTER = 500         # фильтр offerIds при чтении остатков
MAX_CARD_FILTER = 200        # offerIds при чтении заполненности карточек

# Модели размещения склада (enum Маркета). Экспресс — наш клин.
PLACEMENT_FBS = "FBS"
PLACEMENT_DBS = "DBS"
PLACEMENT_EXPRESS = "EXPRESS"
PLACEMENTS = (PLACEMENT_FBS, PLACEMENT_DBS, PLACEMENT_EXPRESS)


class WriteRefused(RuntimeError):
    """Запись наружу отклонена законом (нет commit / нет ключа / нет id) — не сетевая ошибка."""


def _gate(what, dry, commit):
    """L1 двойной гейт записи. Возвращает True, если РЕАЛЬНО можно писать наружу."""
    if dry or not commit:
        return False
    if not hands.creds_present():
        raise WriteRefused(
            f"{what}: нет YANDEX_MARKET_API_KEY — реальная запись невозможна (не выдумываем успех)")
    return True


def _dry_echo(what, method, path, body):
    """Сухой прогон: печатаем ТОЧНЫЙ payload, который полетел бы. Ничего не шлём."""
    print(f"  [dry] {what}: {method} {path}")
    print("  [dry] payload: " + json.dumps(body, ensure_ascii=False)[:900])
    return {"status": "dry", "sent": False, "method": method, "path": path, "payload": body}


def _errors_of(node):
    """L2: собрать errors/warnings из узла ответа Маркета (их формат — список объектов)."""
    errs, warns = [], []
    if isinstance(node, dict):
        for e in node.get("errors") or []:
            errs.append(e.get("message") or e.get("code") or str(e))
        for w in node.get("warnings") or []:
            warns.append(w.get("message") or w.get("code") or str(w))
    return errs, warns


# ============================================================================
# СКЛАДЫ — вход в модель. Читать можно, СОЗДАТЬ через API нельзя (L5).
# ============================================================================

def warehouses(business_id, warehouse_ids=None, with_address=True, timeout=30):
    """Склады партнёра: POST /v3/businesses/{id}/warehouses (кабинеты БЕЗ групп складов).

    Возвращает нормализованный список:
      [{id, name, models: {EXPRESS: 'ENABLED', ...}, city, address, gps}]
    Лимит Маркета: 100 запросов/час.
    """
    if not business_id:
        raise WriteRefused("склады: businessId неизвестен (не шлём на /businesses/None/)")
    body = {}
    if warehouse_ids:
        body["warehouseIds"] = [int(w) for w in warehouse_ids]
    if with_address:
        body["components"] = ["ADDRESS"]
    data = hands._request("POST", f"/v3/businesses/{business_id}/warehouses",
                          body=body, timeout=timeout)
    res = (data or {}).get("result") or {}
    out = []
    for w in res.get("warehouses") or []:
        models = {}
        for m in w.get("models") or []:
            pt = m.get("placementType")
            if pt:
                models[pt] = m.get("apiAvailability") or m.get("status") or "UNKNOWN"
        addr = w.get("address") or {}
        gps = addr.get("gps") or {}
        out.append({
            "id": w.get("id"),
            "name": w.get("name"),
            "models": models,
            "express": PLACEMENT_EXPRESS in models,
            "city": addr.get("city"),
            "address": " ".join(str(addr.get(k)) for k in ("street", "number", "building")
                                if addr.get(k)) or None,
            "gps": {"lat": gps.get("latitude"), "lon": gps.get("longitude")} if gps else None,
        })
    return out


def express_warehouses(business_id, timeout=30):
    """Только склады с включённым ЭКСПРЕССОМ — рабочая площадка органа."""
    return [w for w in warehouses(business_id, timeout=timeout) if w["express"]]


def set_warehouse_model(business_id, partner_warehouse_id, model, enabled,
                        dry=True, commit=False, timeout=30):
    """Включить/выключить модель (FBS/DBS/EXPRESS) на складе.

    POST /v3/businesses/{id}/warehouse/models/status
    Эффект Маркета: товары скрываются/возвращаются ~15 мин (или 4 ч, если модель спала ≥30 дней).
    Модель, отключённую САМИМ Маркетом, через API включить нельзя — вернётся ошибка в теле.
    """
    if model not in PLACEMENTS:
        raise WriteRefused(f"модель склада '{model}' неизвестна (ожидаем {PLACEMENTS})")
    if not business_id:
        raise WriteRefused("модель склада: businessId неизвестен")
    path = f"/v3/businesses/{business_id}/warehouse/models/status"
    body = {"partnerWarehouseId": int(partner_warehouse_id),
            "model": model, "enabled": bool(enabled)}
    what = f"склад {partner_warehouse_id} · {model} · {'ON' if enabled else 'OFF'}"
    if not _gate(what, dry, commit):
        return _dry_echo(what, "POST", path, body)
    data = hands._request("POST", path, body=body, timeout=timeout)
    errs, warns = _errors_of((data or {}).get("result") or data)
    return {"status": "sent", "sent": True, "ok": not errs,
            "errors": errs, "warnings": warns, "raw": data}


def create_warehouse_refused():
    """L5: честный отказ. В Partner API метода создания склада НЕТ.

    Склад создаётся руками: кабинет → Настройки → API и модули → Склады
    (для Экспресса Маркет ещё проводит проверку склада: обычно 6–8 часов, максимум сутки).
    Роль СКЛАДОВЩИК обязана вернуть ЭТО, а не имитировать создание.
    """
    return {
        "ok": False,
        "reason": "API_METHOD_ABSENT",
        "human": ("Создать склад через API нельзя — в Partner API такого метода нет. "
                  "Заводится руками в кабинете (Настройки → API и модули → Склады), "
                  "для Экспресса Маркет проверяет склад 6–8 часов."),
        "operator_action_required": True,
    }


# ============================================================================
# ОСТАТКИ — самое денежное. Протухли → заказ на то, чего нет → штраф + индекс вниз.
# ============================================================================

def update_stocks(business_id, items, dry=True, commit=False, timeout=60):
    """Обновить остатки на складе партнёра: POST /v3/businesses/{id}/offers/stocks/update.

    items — [{sku, warehouse_id, count, updated_at?}]. Потолок батча 2000 (L4), 50 запросов/мин.
    count=0 — ЛЕГАЛЬНО и важно: так товар честно снимается с продажи (лучше нуля, чем штраф).
    updated_at не выдумываем: не передали — Маркет ставит время получения запроса сам (L3).
    """
    if not business_id:
        raise WriteRefused("остатки: businessId неизвестен")
    if not items:
        return {"status": "noop", "sent": False, "note": "нечего обновлять (пустой список)"}
    if len(items) > MAX_STOCKS_BATCH:
        raise WriteRefused(
            f"остатки: {len(items)} SKU > потолка Маркета {MAX_STOCKS_BATCH} — режь на батчи")

    sku_items = []
    for it in items:
        sku = it.get("sku") or it.get("offerId")
        wid = it.get("warehouse_id") or it.get("partnerWarehouseId")
        cnt = it.get("count")
        if not sku or wid is None or cnt is None:
            raise WriteRefused(
                f"остатки: неполная позиция {it!r} — нужны sku, warehouse_id, count (не выдумываем)")
        row = {"sku": str(sku), "partnerWarehouseId": int(wid), "count": int(cnt)}
        if it.get("updated_at"):
            row["updatedAt"] = it["updated_at"]
        sku_items.append(row)

    path = f"/v3/businesses/{business_id}/offers/stocks/update"
    body = {"skuItems": sku_items}
    what = f"остатки {len(sku_items)} SKU"
    if not _gate(what, dry, commit):
        return _dry_echo(what, "POST", path, body)
    data = hands._request("POST", path, body=body, timeout=timeout)
    errs, warns = _errors_of((data or {}).get("result") or data)
    return {"status": "sent", "sent": True, "ok": not errs, "count": len(sku_items),
            "errors": errs, "warnings": warns, "raw": data}


def read_stocks(business_id, warehouse_id, offer_ids=None, timeout=30):
    """Прочитать текущие остатки: POST /v3/businesses/{id}/offers/stocks. READ, 500 запросов/мин.

    Возвращает [{sku, count, updatedAt}] — источник правды для проверки «остатки живые».
    """
    if not business_id:
        raise WriteRefused("чтение остатков: businessId неизвестен")
    if warehouse_id is None:
        raise WriteRefused("чтение остатков: partnerWarehouseId обязателен")
    body = {"partnerWarehouseId": int(warehouse_id)}
    if offer_ids:
        ids = list(offer_ids)
        if len(ids) > MAX_SKU_FILTER:
            raise WriteRefused(f"чтение остатков: фильтр {len(ids)} > {MAX_SKU_FILTER}")
        body["offerIds"] = [str(i) for i in ids]
    data = hands._request("POST", f"/v3/businesses/{business_id}/offers/stocks",
                          body=body, timeout=timeout)
    res = (data or {}).get("result") or {}
    out = []
    # ЖИВОЙ КАБИНЕТ: ответ приходит как offers[{offerId, stocks:[{count, updatedAt}]}].
    # Пустой stocks[] = остаток НЕ задан (позиция в каталоге, но на складе её нет) — это не то же
    # самое, что count=0 (явный ноль). Различаем честно: count=None означает «не задан».
    for row in res.get("offers") or []:
        stocks = row.get("stocks") or []
        if stocks:
            for st in stocks:
                out.append({"sku": row.get("offerId"), "count": st.get("count"),
                            "updatedAt": st.get("updatedAt"), "type": st.get("type")})
        else:
            out.append({"sku": row.get("offerId"), "count": None, "updatedAt": None,
                        "type": None})
    # Совместимость со схемой из документации (skuItems / skus), если Маркет вернёт к ней.
    for row in res.get("skuItems") or res.get("skus") or []:
        cnt = row.get("count")
        if cnt is None:
            items = row.get("items") or []
            cnt = items[0].get("count") if items else None
            upd = items[0].get("updatedAt") if items else None
        else:
            upd = row.get("updatedAt")
        out.append({"sku": row.get("sku") or row.get("offerId"),
                    "count": cnt, "updatedAt": upd})
    return out


# ============================================================================
# ЦЕНЫ — «максимально в профите». discountBase = зачёркнутая цена.
# ============================================================================

def update_prices(business_id, offers, dry=True, commit=False, timeout=60):
    """Единые цены кабинета: POST /v2/businesses/{id}/offer-prices/updates. Потолок 500 (L4).

    offers — [{sku, value, discount_base?, vat?}]. discountBase Маркет требует передавать
    ПРИ КАЖДОМ обновлении, иначе зачёркнутая цена сбрасывается; скидка должна быть 5–99 %.
    Резкий скачок цены → товар попадает в карантин цен (подтверждается отдельно).
    """
    if not business_id:
        raise WriteRefused("цены: businessId неизвестен")
    if not offers:
        return {"status": "noop", "sent": False, "note": "нечего обновлять"}
    if len(offers) > MAX_PRICES_BATCH:
        raise WriteRefused(
            f"цены: {len(offers)} offers > потолка {MAX_PRICES_BATCH} — режь на батчи")

    rows = []
    for o in offers:
        sku = o.get("sku") or o.get("offerId")
        val = o.get("value") or o.get("price")
        if not sku or val is None:
            raise WriteRefused(f"цены: неполная позиция {o!r} — нужны sku и value")
        val = float(val)
        if val <= 0:
            raise WriteRefused(f"цены: {sku} value={val} — цену ≤0 не отправляем")
        price = {"value": val, "currencyId": "RUR"}
        db = o.get("discount_base") or o.get("discountBase")
        if db is not None:
            db = int(round(float(db)))
            # Маркет: скидка 5–99 % от зачёркнутой; иначе отклонит — ловим ДО сети (L2/L3).
            if db <= val:
                raise WriteRefused(
                    f"цены: {sku} discountBase={db} должен быть БОЛЬШЕ цены {val}")
            disc_pct = (db - val) / db * 100.0
            if not (5.0 <= disc_pct <= 99.0):
                raise WriteRefused(
                    f"цены: {sku} скидка {disc_pct:.1f}% вне 5–99% (Маркет отклонит)")
            price["discountBase"] = db
        if o.get("vat"):
            price["vat"] = o["vat"]
        rows.append({"offerId": str(sku), "price": price})

    path = f"/v2/businesses/{business_id}/offer-prices/updates"
    body = {"offers": rows}
    what = f"цены {len(rows)} offers"
    if not _gate(what, dry, commit):
        return _dry_echo(what, "POST", path, body)
    data = hands._request("POST", path, body=body, timeout=timeout)
    errs, warns = _errors_of((data or {}).get("result") or data)
    return {"status": "sent", "sent": True, "ok": not errs, "count": len(rows),
            "errors": errs, "warnings": warns, "raw": data}


def price_recommendations(business_id, offer_ids=None, limit=200, timeout=30):
    """Рекомендации Маркета по привлекательности цены: POST /v2/businesses/{id}/offers/recommendations.

    Это НЕ цены конкурентов (их API не даёт) — это порог привлекательной цены и оценка витрины.
    Ценовик обязан отличать: рекомендация Маркета ≠ обязанность падать в цене.
    """
    if not business_id:
        raise WriteRefused("рекомендации цен: businessId неизвестен")
    body = {}
    if offer_ids:
        ids = list(offer_ids)[:MAX_CARD_FILTER]
        body["offerIds"] = [str(i) for i in ids]
    data = hands._request("POST", f"/v2/businesses/{business_id}/offers/recommendations",
                          body=body, params={"limit": int(limit)}, timeout=timeout)
    res = (data or {}).get("result") or {}
    return res.get("offers") or res.get("offerRecommendations") or []


# ============================================================================
# ТАРИФЫ — считать маржу ДО залива. Калькулятор самого Маркета.
# ============================================================================

def calc_tariffs(offers, selling_program=PLACEMENT_EXPRESS, campaign_id=None,
                 frequency="DAILY", currency="RUR", timeout=30):
    """POST /v2/tariffs/calculate — сколько Маркет возьмёт за товар. До 200 позиций, 100 зап/мин.

    offers — [{category_id, price, length, width, height, weight, quantity?}] (см. габариты).
    campaignId и sellingProgram ВМЕСТЕ передавать нельзя — Маркет вернёт ошибку.
    Ответ: список тарифов по позиции; типы — FEE (размещение), AGENCY_COMMISSION,
    PAYMENT_TRANSFER, EXPRESS_DELIVERY и др. Документация честно предупреждает: расчёт
    ПРИМЕРНЫЙ, факт приезжает в отчётах. Поэтому ценовик кладёт это в оценку, не в доказанный ₽.
    """
    if not offers:
        return []
    if len(offers) > MAX_TARIFF_OFFERS:
        raise WriteRefused(f"тарифы: {len(offers)} > потолка {MAX_TARIFF_OFFERS}")
    # Боевой урок: campaignId нельзя слать вместе НЕ ТОЛЬКО с sellingProgram, но и с currency.
    params = {"frequency": frequency}
    if campaign_id:
        params["campaignId"] = int(campaign_id)
    else:
        params["sellingProgram"] = selling_program
        params["currency"] = currency
    rows = []
    for o in offers:
        row = {"categoryId": int(o.get("category_id") or o.get("categoryId") or 0),
               "price": float(o.get("price") or 0)}
        for src, dst in (("length", "length"), ("width", "width"), ("height", "height"),
                         ("weight", "weight")):
            if o.get(src) is not None:
                row[dst] = float(o[src])
        row["quantity"] = int(o.get("quantity") or 1)
        rows.append(row)
    data = hands._request("POST", "/v2/tariffs/calculate",
                          body={"parameters": params, "offers": rows}, timeout=timeout)
    res = (data or {}).get("result") or {}
    return res.get("offers") or []


# ============================================================================
# ЗАКАЗЫ — конец контура. В Экспрессе таймер 60 минут решает деньги.
# ============================================================================

ORDER_PROCESSING = "PROCESSING"
SUB_STARTED = "STARTED"
SUB_READY_TO_SHIP = "READY_TO_SHIP"
ORDER_CANCELLED = "CANCELLED"
SUB_SHOP_FAILED = "SHOP_FAILED"


def orders(business_id, statuses=None, program_types=(PLACEMENT_EXPRESS,),
           campaign_ids=None, limit=50, page_token=None, timeout=30):
    """Заказы кабинета: POST /v1/businesses/{id}/orders. 10 000 запросов/час.

    Маркет рекомендует опрашивать ЭКСПРЕСС каждые 10–15 минут (FBS/DBS — раз в час).
    Диапазон дат за один запрос — максимум 30 дней; без дат вернёт последние 30 дней.
    """
    if not business_id:
        raise WriteRefused("заказы: businessId неизвестен")
    body = {}
    if statuses:
        body["statuses"] = list(statuses)
    if program_types:
        body["programTypes"] = list(program_types)
    if campaign_ids:
        body["campaignIds"] = [int(c) for c in campaign_ids]
    params = {"limit": int(limit)}
    if page_token:
        params["pageToken"] = page_token
    data = hands._request("POST", f"/v1/businesses/{business_id}/orders",
                          body=body, params=params, timeout=timeout)
    res = (data or {}).get("result") or {}
    return {"orders": res.get("orders") or [],
            "nextPageToken": (res.get("paging") or {}).get("nextPageToken")}


def new_express_orders(business_id, timeout=30):
    """Свежие экспресс-заказы, ждущие сборки (PROCESSING). Их и караулит роль ДИСПЕТЧЕР."""
    got = orders(business_id, statuses=[ORDER_PROCESSING],
                 program_types=[PLACEMENT_EXPRESS], timeout=timeout)
    return got["orders"]


def set_order_status(campaign_id, order_id, status, substatus=None,
                     dry=True, commit=False, timeout=30):
    """Сменить статус заказа: PUT /v2/campaigns/{cid}/orders/{oid}/status.

    Разрешённые продавцу переходы (Маркет требует именно этого порядка):
      PROCESSING/STARTED       → PROCESSING/READY_TO_SHIP   (собрал, готов к отгрузке)
      PROCESSING/STARTED       → CANCELLED/SHOP_FAILED      (не могу выполнить)
      PROCESSING/READY_TO_SHIP → CANCELLED/SHOP_FAILED      (брак последнего товара)
    Отмена по вине магазина бьёт по индексу качества И по деньгам — роль обязана считать это
    последним средством, а не удобным выходом.
    """
    if not campaign_id or not order_id:
        raise WriteRefused("статус заказа: нужны campaignId и orderId")
    path = f"/v2/campaigns/{campaign_id}/orders/{order_id}/status"
    order = {"status": status}
    if substatus:
        order["substatus"] = substatus
    body = {"order": order}
    what = f"заказ {order_id} → {status}/{substatus or '—'}"
    if not _gate(what, dry, commit):
        return _dry_echo(what, "PUT", path, body)
    data = hands._request("PUT", path, body=body, timeout=timeout)
    errs, warns = _errors_of((data or {}).get("result") or data)
    return {"status": "sent", "sent": True, "ok": not errs,
            "errors": errs, "warnings": warns, "raw": data}


def mark_ready_to_ship(campaign_id, order_id, dry=True, commit=False, timeout=30):
    """Главное действие Экспресса: «Готов к отгрузке» ДО истечения таймера.

    Просрочка +60 минут после shipmentTime → Маркет отменяет заказ САМ и роняет индекс.
    """
    return set_order_status(campaign_id, order_id, ORDER_PROCESSING, SUB_READY_TO_SHIP,
                            dry=dry, commit=commit, timeout=timeout)


def verify_eac(campaign_id, order_id, code, dry=True, commit=False, timeout=30):
    """Код подтверждения курьеру (ЭАПП): PUT /v2/campaigns/{cid}/orders/{oid}/verifyEac.

    Метод существует ТОЛЬКО для Экспресса. В ответе attemptsLeft — попытки не бесконечны,
    поэтому код не «подбираем»: нет кода → отказ (L3).
    """
    if not code:
        raise WriteRefused("verifyEac: пустой код — не подбираем (attemptsLeft ограничен)")
    path = f"/v2/campaigns/{campaign_id}/orders/{order_id}/verifyEac"
    body = {"code": str(code)}
    what = f"verifyEac заказ {order_id}"
    if not _gate(what, dry, commit):
        return _dry_echo(what, "PUT", path, body)
    data = hands._request("PUT", path, body=body, timeout=timeout)
    res = (data or {}).get("result") or {}
    return {"status": "sent", "sent": True,
            "verification": res.get("verificationResult"),
            "attempts_left": res.get("attemptsLeft"), "raw": data}


# ============================================================================
# РЕГИОНЫ — рост по городам.
# ============================================================================

def find_region(name, limit=20, timeout=30):
    """Найти город: GET /v2/regions?name=... Лимит группы методов — 50 000 регионов/час.

    Возвращает [{id, name, type, parent_path}]. type=CITY — то, что нужно для нового города.
    """
    if not name:
        return []
    data = hands._request("GET", "/v2/regions",
                          params={"name": str(name), "limit": int(limit)}, timeout=timeout)
    # ЖИВОЙ КАБИНЕТ: regions лежат в КОРНЕ ответа, не в result (документация вводит в заблуждение).
    # Поддерживаем оба варианта — если Маркет вернёт к схеме, ничего не сломается.
    res = (data or {}).get("result") or data or {}
    out = []
    for r in res.get("regions") or []:
        chain, node = [], r.get("parent")
        while isinstance(node, dict):
            if node.get("name"):
                chain.append(node["name"])
            node = node.get("parent")
        out.append({"id": r.get("id"), "name": r.get("name"), "type": r.get("type"),
                    "parent_path": " / ".join(reversed(chain)) or None})
    return out


def quality_rating(business_id, campaign_ids, timeout=30):
    """Индекс качества магазина: POST /v2/businesses/{id}/ratings/quality. 500 запросов/час.

    В Экспрессе от индекса ПРЯМО зависят деньги: <98 → платим % за отмены/опоздания,
    <40 → магазин отключают и товары скрывают на 7 дней. Роль КОНТРОЛЁР следит за этим числом.
    """
    if not business_id or not campaign_ids:
        raise WriteRefused("индекс качества: нужны businessId и campaignIds")
    data = hands._request("POST", f"/v2/businesses/{business_id}/ratings/quality",
                          body={"campaignIds": [int(c) for c in campaign_ids]}, timeout=timeout)
    res = (data or {}).get("result") or {}
    # ЖИВОЙ КАБИНЕТ: приходит campaignRatings[{campaignId, ratings:[...]}]. Пустой ratings[]
    # означает, что Маркет ЕЩЁ НЕ рассчитал индекс (новый магазин без истории заказов) —
    # это НЕ «индекс ноль». Отдаём rating=None, чтобы КОНТРОЛЁР честно сказал «неизвестен» (C5).
    out = []
    for row in res.get("campaignRatings") or []:
        ratings = row.get("ratings") or []
        value = None
        for r in ratings:
            v = r.get("value") if isinstance(r, dict) else None
            if isinstance(v, (int, float)):
                value = float(v)
                break
        out.append({"campaignId": row.get("campaignId"), "total": value,
                    "components": ratings, "not_calculated": not ratings})
    if out:
        return out
    return res.get("campaignsRatings") or res.get("ratings") or []


if __name__ == "__main__":
    bid = hands.business_id_env()
    print("ТОРГОВЫЕ РУКИ М6 — сухая самопроверка (0₽, наружу ничего)")
    print(f"  ключ: {'есть' if hands.creds_present() else 'НЕТ'} · businessId: {bid or 'НЕ ЗАДАН'}")
    print(f"  потолки: остатки {MAX_STOCKS_BATCH} · цены {MAX_PRICES_BATCH} · тарифы {MAX_TARIFF_OFFERS}")
    print("\n· склад: включить ЭКСПРЕСС (dry)")
    print(json.dumps(set_warehouse_model(bid or "B1", 123, PLACEMENT_EXPRESS, True,
                                         dry=True)["payload"], ensure_ascii=False))
    print("\n· остатки (dry)")
    print(json.dumps(update_stocks(bid or "B1", [{"sku": "S1", "warehouse_id": 123, "count": 7}],
                                   dry=True)["payload"], ensure_ascii=False))
    print("\n· цена со зачёркнутой (dry)")
    print(json.dumps(update_prices(bid or "B1", [{"sku": "S1", "value": 1500,
                                                  "discount_base": 2000}],
                                   dry=True)["payload"], ensure_ascii=False))
    print("\n· готов к отгрузке (dry)")
    print(json.dumps(mark_ready_to_ship("C1", 42, dry=True)["payload"], ensure_ascii=False))
    print("\n· создать склад:")
    print("  " + create_warehouse_refused()["human"])

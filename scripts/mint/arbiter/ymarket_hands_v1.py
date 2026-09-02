#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET HANDS V1 — руки MERCHANT на Яндекс.Маркет Partner API (bounded, без демона).

Близнец socc_mint_ozon_v1 (руки Ozon), но для второго маркетплейса — Яндекс.Маркета, и с
УПОРОМ НА ЗАПИСЬ КАРТОЧЕК (у Ozon-рук главным был READ заказов; здесь — WRITE карточек +
READ индекса заполненности). Веха M6 оси ARBITER: «Яндекс.Маркет-витрина (клон ozon_write)».

ЧТО ЭТО (карта API, дословно из справки partner-api):
  • Авторизация — заголовок `Api-Key: <токен 48 знаков>` (OAuth Bearer устарел). Нет ключа → 401.
  • Два уровня id: businessId (кабинет, общий каталог+контент) ↔ campaignId (магазин FBS/DBS/FBY).
    Оба узнаём из GET campaigns. Товар живёт в каталоге кабинета, продаётся в магазине.
  • 4-шаг публикации карточки:
      1) POST businesses/{businessId}/offer-mappings/update — товар в каталог кабинета.
      2) POST businesses/{businessId}/offer-cards/update      — категорийные характеристики.
      3) POST campaigns/{campaignId}/offers/update            — размещение (available/quantum/vat).
      4) POST campaigns/{campaignId}/offers                   — проверка витрины (статус PUBLISHED).
  • Индекс/ТОП: POST businesses/{businessId}/offer-cards — contentRating + recommendations.
  • Справочники: POST categories/tree, POST category/{id}/parameters (у параметра флаг required).

ЗАКОН (как у Ozon-рук и всего ARBITER): requests ЛЕНИВЫЙ (модуль грузится без сети/ключей —
чистый stdlib dry-run), ключи ТОЛЬКО из env, устойчивый слой (401=ключи-не-код, 429/5xx=ограниченный
ретрай, НЕ демон), fail-soft. 200 ≠ успех: разбор results.errors/warnings — забота вызывающего
(writer), эти руки лишь честно доносят тело ответа и http-исход. Деньги эти руки НЕ трогают.

Env:
  YANDEX_MARKET_API_KEY   — Api-Key токен кабинета (обязателен для реального режима).
  YANDEX_BUSINESS_ID      — id кабинета (можно не задавать: возьмём из campaigns()).
  YANDEX_CAMPAIGN_ID      — id магазина (можно не задавать: возьмём из campaigns()).
"""
import os

API = "https://api.partner.market.yandex.ru"

# Транзиторные http-коды: моргнули → ограниченный ретрай (не демон). 401/403 — НЕ транзиторные (ключи).
_TRANSIENT = (420, 429, 500, 502, 503, 504)
_MAX_RETRIES = 3

_ENV_TRIED = False


def _ensure_env():
    """Один раз подтянуть gitignored .env (фаза A: руки не видели ЖИВЫХ ключей — читали только env).

    Fail-soft вдвойне: сначала обычный импорт, потом с достройкой sys.path, и любая неудача —
    молчаливый выход. Загрузчик секретов НЕ ИМЕЕТ ПРАВА уронить руки: без него dry-run обязан жить.
    """
    global _ENV_TRIED
    if _ENV_TRIED:
        return
    _ENV_TRIED = True
    env = None
    try:
        import socc_mint_env_v1 as env          # noqa: F811
    except Exception:
        try:
            import sys
            from pathlib import Path
            mint = str(Path(__file__).resolve().parent.parent)   # SOCC/scripts/mint
            if mint not in sys.path:
                sys.path.insert(0, mint)
            import socc_mint_env_v1 as env      # noqa: F811
        except Exception:
            return
    try:
        env.ensure_env()
    except Exception:
        pass


def creds_present():
    """Есть ли Api-Key в env (включая gitignored .env). Без него реальный режим недоступен."""
    _ensure_env()
    return bool(os.getenv("YANDEX_MARKET_API_KEY"))


def business_id_env():
    _ensure_env()
    return os.getenv("YANDEX_BUSINESS_ID") or None


def campaign_id_env():
    _ensure_env()
    return os.getenv("YANDEX_CAMPAIGN_ID") or None


def _headers():
    _ensure_env()
    key = os.getenv("YANDEX_MARKET_API_KEY")
    if not key:
        raise RuntimeError(
            "YANDEX_MARKET_API_KEY не задан — реальный режим недоступен (нужен Api-Key кабинета "
            "Яндекс.Маркета; впиши в wavecore-bot/.env, он gitignored)")
    # Партнёрский API авторизуется ЗАГОЛОВКОМ Api-Key (OAuth Bearer устарел).
    return {"Api-Key": key, "Content-Type": "application/json", "Accept": "application/json"}


class YMarketHTTPError(RuntimeError):
    """HTTP-ошибка Яндекс.Маркета с сохранённым кодом и телом — чтобы writer честно разобрал."""
    def __init__(self, status, body, url):
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"Яндекс.Маркет {status} {url}: {str(body)[:300]}")


class _Resp:
    """Лёгкий носитель http-исхода (status_code + json/text) — чтобы _http_call и тесты не тянули requests."""
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("не JSON")
        return self._payload


def _http_call(method, url, headers, body, params, timeout):
    """Единственное место реальной сети (шов для тестов): один вызов → _Resp.

    Тесты подменяют ИМЕННО этот шов (а не _request), чтобы проверялась ретрай-петля _request.
    Транспорт выбирается по наличию: requests, если установлен (исторический путь), иначе
    stdlib urllib — организм остаётся ЖИВЫМ на голом Python, без внешних зависимостей
    (закон вечной машины: ни dry-run, ни боевой режим не должны требовать pip install).

    Не-2xx здесь НЕ роняем — возвращаем _Resp со статусом, чтобы петля _request сама решила
    (401/403 — сразу ошибка, 429/5xx — ретрай). Роняем только НАСТОЯЩИЙ сетевой сбой/timeout,
    и тогда _request сочтёт это транзиторным и ретайнет.
    """
    try:
        import requests  # исторический путь, если доступен
    except Exception:
        requests = None
    if requests is not None:
        r = requests.request(method, url, headers=headers, json=body, params=params, timeout=timeout)
        payload = None
        try:
            payload = r.json()
        except Exception:
            payload = None
        return _Resp(r.status_code, payload, getattr(r, "text", ""))

    # ── stdlib-транспорт (urllib): requests нет → живём на голом Python ──
    import json as _json
    import urllib.request, urllib.parse, urllib.error
    full = url
    if params:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
        if qs:
            full = url + ("&" if "?" in url else "?") + qs
    data = _json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(full, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.getcode()
    except urllib.error.HTTPError as e:      # не-2xx: вернуть статус+тело, НЕ ронять
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
        status = e.code
    # URLError/timeout НЕ ловим — пусть _request сочтёт транзиторным и ретайнет
    payload = None
    try:
        payload = _json.loads(raw) if raw else None
    except Exception:
        payload = None
    return _Resp(status, payload, raw)


def _request(method, path, body=None, params=None, timeout=30):
    """Один устойчивый вызов к Partner API. Возвращает распарсенный JSON (dict).

    Устойчивость (закон вечной машины, как у bridge_v1.read_orders):
      • 401/403 → YMarketHTTPError сразу (это КЛЮЧИ/права, не код — ретрай бессмыслен).
      • 429/5xx/timeout → до _MAX_RETRIES ретраев с jitter-бэкоффом (моргнуло — не «мост мёртв»).
      • иной не-2xx → YMarketHTTPError (writer прочитает body.results.errors — 200≠успех работает
        и наоборот: не-2xx тоже несёт машиночитаемую причину).
    Реальная сеть изолирована в _http_call (шов для тестов).
    """
    url = API + path
    retries = 0
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            r = _http_call(method, url, _headers(), body, params, timeout)
        except Exception as e:  # сетевой сбой/timeout — транзиторный
            last_exc = e
            if attempt + 1 < _MAX_RETRIES:
                import time, random
                time.sleep(0.5 + random.random() * 1.0)
                retries += 1
                continue
            raise RuntimeError(f"сеть к Яндекс.Маркету упала после {retries} ретраев: {e}")
        if r.status_code in (401, 403):
            raise YMarketHTTPError(r.status_code, _safe_json(r), url)  # ключи/права, не код
        if r.status_code in _TRANSIENT and attempt + 1 < _MAX_RETRIES:
            import time, random
            time.sleep(0.5 + random.random() * 1.0)
            retries += 1
            continue
        if not (200 <= r.status_code < 300):
            raise YMarketHTTPError(r.status_code, _safe_json(r), url)
        return _safe_json(r)
    # исчерпали ретраи на транзиторном коде
    raise RuntimeError(f"исчерпаны ретраи к {url} (последняя ошибка: {last_exc})")


def _safe_json(r):
    """Тело ответа как JSON; если не JSON — вернуть {'raw': text} (не роняем разбор)."""
    try:
        return r.json()
    except Exception:
        return {"raw": getattr(r, "text", "")}


# ── Справочники: кабинет/магазин и категории (READ, 0₽) ──

def campaigns(timeout=30):
    """GET campaigns → список магазинов кабинета. Отсюда узнаём businessId и campaignId.

    Каждый элемент несёт business.id (кабинет) и id (магазин) + placementType (FBS/DBS/FBY).
    """
    data = _request("GET", "/campaigns", timeout=timeout)
    return data.get("campaigns", []) if isinstance(data, dict) else []


def resolve_ids(timeout=30):
    """Разрешить (business_id, campaign_id): сперва env, иначе из первого магазина campaigns().

    Возвращает (business_id, campaign_id, source) — source честно говорит откуда взяли.
    """
    bid, cid = business_id_env(), campaign_id_env()
    if bid and cid:
        return bid, cid, "env"
    camps = campaigns(timeout=timeout)
    if not camps:
        return bid, cid, "env_partial_no_campaigns"
    first = camps[0]
    bid = bid or str((first.get("business") or {}).get("id") or "") or None
    cid = cid or str(first.get("id") or "") or None
    return bid, cid, "campaigns"


def categories_tree(timeout=30):
    """POST categories/tree → дерево категорий Маркета (для поиска листовой marketCategoryId)."""
    data = _request("POST", "/categories/tree", body={}, timeout=timeout)
    return data.get("result", data) if isinstance(data, dict) else data


def category_parameters(category_id, timeout=30):
    """POST category/{id}/parameters → характеристики листовой категории (у параметра флаг required).

    Это ИСТОЧНИК ИСТИНЫ для «карточки без ошибок»: какие поля обязательны и какие valueId допустимы.
    """
    data = _request("POST", f"/category/{int(category_id)}/parameters", body={}, timeout=timeout)
    res = data.get("result", data) if isinstance(data, dict) else data
    if isinstance(res, dict):
        return res.get("parameters", res)
    return res


# ── Запись карточки: 4 шага (реальные вызовы; writer зовёт их только по отмашке) ──

def update_offer_mappings(business_id, offer_mappings, timeout=60):
    """Шаг 1: POST businesses/{businessId}/offer-mappings/update — товары в каталог кабинета.

    offer_mappings — список {'offer': {...}, 'mapping'?: {'marketSku': ...}}. Возвращает тело ответа
    целиком (writer обязан прочитать result.offerMappings[].errors/warnings — 200≠успех)."""
    body = {"offerMappings": list(offer_mappings)}
    return _request("POST", f"/businesses/{business_id}/offer-mappings/update", body=body, timeout=timeout)


def update_offer_cards(business_id, offers_content, timeout=60):
    """Шаг 2: POST businesses/{businessId}/offer-cards/update — категорийные характеристики.

    offers_content — список {'offerId','categoryId','parameterValues':[{parameterId,unitId,valueId,value}]}.
    """
    body = {"offersContent": list(offers_content)}
    return _request("POST", f"/businesses/{business_id}/offer-cards/update", body=body, timeout=timeout)


def update_campaign_offers(campaign_id, offers, timeout=60):
    """Шаг 3: POST campaigns/{campaignId}/offers/update — размещение в магазине (available/quantum/vat)."""
    body = {"offers": list(offers)}
    return _request("POST", f"/campaigns/{campaign_id}/offers/update", body=body, timeout=timeout)


# ── Удаление из каталога (DESTRUCTIVE — товар исчезает из кабинета И из всех магазинов) ──

def delete_offer_mappings(business_id, offer_ids, timeout=60):
    """POST businesses/{businessId}/offer-mappings/delete — удалить товары из каталога кабинета.

    ЭТО НЕОБРАТИМО в один вызов: товар исчезает из общего каталога, значит и из всех магазинов
    (Express/DBS/FBS сразу). Возвращает тело ответа целиком; вызывающий ОБЯЗАН прочитать
    result.notDeletedOfferIds — Маркет НЕ удаляет offer с активными остатками/заказами и честно
    вернёт его в этом списке (status может быть OK, но товар остался — 200≠успех работает и тут).
    Руки только доносят исход; решение «жать» принимает драйвер по отмашке оператора (RUBICON).
    """
    body = {"offerIds": list(offer_ids)}
    return _request("POST", f"/businesses/{business_id}/offer-mappings/delete", body=body, timeout=timeout)


# ── Чтение витрины и индекса заполненности (READ, 0₽) ──

def campaign_offers(campaign_id, offer_ids=None, limit=50, timeout=30):
    """Шаг 4: POST campaigns/{campaignId}/offers — товары магазина + статус размещения (PUBLISHED?)."""
    body = {}
    if offer_ids:
        body["offerIds"] = list(offer_ids)
    data = _request("POST", f"/campaigns/{campaign_id}/offers", body=body,
                    params={"limit": int(limit)}, timeout=timeout)
    res = data.get("result", data) if isinstance(data, dict) else data
    if isinstance(res, dict):
        return res.get("offers", res)
    return res


def offer_cards_status(business_id, offer_ids=None, limit=50, timeout=30):
    """POST businesses/{businessId}/offer-cards — заполненность карточек (contentRating + recommendations).

    Это рычаг ТОП: contentRating (%), averageContentRating (по категории), recommendations[] с
    remainingRatingPoints. READ, 0₽. Нет offer_ids → вернёт по всему каталогу (пагинация limit).
    """
    body = {}
    if offer_ids:
        body["offerIds"] = list(offer_ids)
    data = _request("POST", f"/businesses/{business_id}/offer-cards", body=body,
                    params={"limit": int(limit)}, timeout=timeout)
    res = data.get("result", data) if isinstance(data, dict) else data
    if isinstance(res, dict):
        return res.get("offerCards", res)
    return res


if __name__ == "__main__":
    import json
    print(json.dumps({
        "creds_present": creds_present(),
        "business_id_env": business_id_env(),
        "campaign_id_env": campaign_id_env(),
        "note": "реальные вызовы требуют YANDEX_MARKET_API_KEY и requests; без ключа — только dry",
    }, ensure_ascii=False, indent=2))

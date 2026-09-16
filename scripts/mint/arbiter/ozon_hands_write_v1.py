#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON HANDS WRITE V1 — руки MERCHANT на Ozon Seller API (bounded, без демона, ЧИСТЫЙ stdlib).

Веха M1 оси ОЗОН: письменно-читающая плоскость. Зеркалит доказанный образец
ymarket_hands_v1 (шов _http_call → петля _request), но под Ozon: заголовки Client-Id/Api-Key
(как socc_mint_ozon_v1._headers), транспорт — тот же urllib, что у ozon_truth_v1._post_stdlib
(в этой среде requests НЕТ — организм обязан жить на голом Python).

ЧТО ЭТО (карта Seller API, дословно из закреплённого контракта; ВСЁ — POST с JSON-телом):
  ЗАПИСЬ (двойной гейт РУБИКОНА — реальный вызов ТОЛЬКО при not dry AND commit):
    • create_product  POST /v3/product/import          — залить карточку(и). Ответ = task_id
                                                          (АСИНХРОННАЯ квитанция, НЕ созданная карточка!)
    • set_price       POST /v1/product/import/prices    — цены (все суммы СТРОКАМИ)
    • set_stock       POST /v2/products/stocks          — остатки (warehouse_id ОБЯЗАТЕЛЕН для FBS)
    • ship_posting    POST /v2/posting/fbs/ship         — отгрузка отправления (M4, деньги/логистика)
  ЧТЕНИЕ (0₽, гейта нет, но fail-soft; 200≠успех — разбираем errors[] уровня item):
    • import_info     POST /v1/product/import/info      — ОПРОС задачи create_product (async → poll)
    • read_shelf / product_visible  POST /v3/product/info/list  — витрина (контракт proof-gate)
    • read_price_index POST /v5/product/info/prices      — цена + индекс цен (RED = скрыт из выдачи)
    • warehouse_list  POST /v1/warehouse/list           — склады FBS (источник warehouse_id, НЕ выдумываем)
    • package_label   POST /v2/posting/fbs/package-label — PDF-этикетка (БИНАРНЫЙ ответ)
  СПРАВОЧНИКИ КАТЕГОРИЙ (0₽; истина для сборки карточки — у Ozon нет авто-категории):
    • category_tree        POST /v1/description-category/tree
    • category_attributes  POST /v1/description-category/attribute        (is_required = истина полноты)
    • attribute_values     POST /v1/description-category/attribute/values  (dictionary_value_id, курсор)

ЗАКОН (как весь ARBITER):
  • requests ЛЕНИВЫЙ → нет его → urllib. Модуль грузится без сети/ключей (чистый dry).
  • Ключи ТОЛЬКО из env/gitignored .env. Нет ключа → честная ошибка, НЕ ретрай.
  • Устойчивость: 401/403 → сразу ошибка (ключи/права, не код); 429/5xx/timeout → ≤3 ретрая
    с jitter; иной не-2xx → ошибка с телом (writer прочитает причину). Не демон.
  • 200 ≠ успех: тело несёт errors[]/warnings[] на уровне item — читает вызывающий/proof-gate.
  • ДЕНЬГИ/КАРТОЧКИ наружу — только по слову оператора (РУБИКОН). dry=True/commit=False по умолчанию.

⚠ ВЕРСИИ ПУТЕЙ вынесены в КОНСТАНТЫ (Ozon versioned, ломает старые пути). Самый рискованный на
  живой сверке — чтение витрины: PRODUCT_INFO_LIST_PATH по умолчанию /v3 (у /v1 велик риск 404).

Env: OZON_CLIENT_ID + OZON_API_KEY (в SOCC/scripts/mint/.env, chmod 600, gitignored).
АККАУНТ: env OZON_ACCOUNT выбирает слот ключей:
  • не задан / "main" → OZON_CLIENT_ID + OZON_API_KEY   (основной кабинет — плёнка/ARB)
  • "box"            → OZON_BOX_CLIENT_ID + OZON_BOX_API_KEY  (кабинет Express Box — коробки)
Отдельные кабинеты = отдельные витрины/лимиты: коробки льются в свой (не забивают плёнку).
"""
import os
import json

API = "https://api-seller.ozon.ru"

# Транзиторные http-коды: моргнуло → ограниченный ретрай (НЕ демон). 401/403 — НЕ транзиторные (ключи).
_TRANSIENT = (420, 429, 500, 502, 503, 504)
_MAX_RETRIES = 3

# ── ВЕРСИИ ПУТЕЙ (overridable — Ozon ломает версии; правится одной строкой без правки логики) ──
PRODUCT_INFO_LIST_PATH = "/v3/product/info/list"      # ⚠ ЖИВАЯ СВЕРКА: /v1 может отдать 404 → /v3|/v4
PRODUCT_INFO_PRICES_PATH = "/v5/product/info/prices"  # v1 устарел → v5 (чтение цены+color_index)
PRODUCT_RATING_PATH = "/v1/product/rating-by-sku"     # контент-рейтинг карточки 0..100 (только по Ozon sku)

_ENV_TRIED = False


def _ensure_env():
    """Один раз подтянуть gitignored .env через общий загрузчик. Fail-soft: без него dry живёт.

    Загрузчик секретов НЕ ИМЕЕТ ПРАВА уронить руки: любая неудача — молчаливый выход, dry обязан жить.
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


def _account_creds():
    """Ключи активного аккаунта по OZON_ACCOUNT (main|box). Никогда не падает — только читает env."""
    _ensure_env()
    if os.getenv("OZON_ACCOUNT", "main").strip().lower() == "box":
        return os.getenv("OZON_BOX_CLIENT_ID"), os.getenv("OZON_BOX_API_KEY")
    return os.getenv("OZON_CLIENT_ID"), os.getenv("OZON_API_KEY")


def creds_present():
    """Есть ли ОБА ключа Ozon (Client-Id + Api-Key) активного аккаунта в env (включая gitignored .env)."""
    _ensure_env()
    cid, key = _account_creds()
    return bool(cid and key)


def _headers():
    """Заголовки Seller API (единый источник ключей активного аккаунта). Нет ключа → RuntimeError."""
    _ensure_env()
    cid, key = _account_creds()
    label = ("OZON_BOX_CLIENT_ID / OZON_BOX_API_KEY" if os.getenv("OZON_ACCOUNT", "main").strip().lower() == "box"
             else "OZON_CLIENT_ID / OZON_API_KEY")
    if not (cid and key):
        raise RuntimeError(
            f"{label} не заданы — реальный режим аккаунта 'box' недоступен (нужны ключи "
            "кабинета Ozon; впиши в SOCC/scripts/mint/.env, он gitignored)")
    return {"Client-Id": cid, "Api-Key": key,
            "Content-Type": "application/json", "Accept": "application/json"}


class OzonHTTPError(RuntimeError):
    """HTTP-ошибка Ozon с сохранённым кодом и телом — чтобы writer/proof честно разобрали причину."""
    def __init__(self, status, body, url):
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"Ozon {status} {url}: {str(body)[:300]}")


class _Resp:
    """Лёгкий носитель http-исхода (status + json/text/БАЙТЫ/тип) — чтобы шов и тесты не тянули requests."""
    def __init__(self, status_code, payload=None, text="", content=b"", content_type=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.content = content              # сырые байты (для БИНАРНОГО PDF этикетки)
        self.content_type = content_type

    def json(self):
        if self._payload is None:
            raise ValueError("не JSON")
        return self._payload


def _http_call(method, url, headers, body, params, timeout):
    """Единственное место реальной сети (ШОВ ДЛЯ ТЕСТОВ): один вызов → _Resp.

    Тесты подменяют ИМЕННО этот шов (а не _request), чтобы проверялась ретрай-петля _request.
    Транспорт по наличию: requests (исторический путь), иначе stdlib urllib — организм жив на
    голом Python (в этой среде requests нет; закон вечной машины: ни dry, ни бой не требуют pip).

    Не-2xx здесь НЕ роняем — возвращаем _Resp со статусом, чтобы петля _request решила
    (401/403 — сразу ошибка, 429/5xx — ретрай). Роняем только НАСТОЯЩИЙ сетевой сбой/timeout.
    """
    try:
        import requests
    except Exception:
        requests = None
    if requests is not None:
        r = requests.request(method, url, headers=headers, json=body, params=params, timeout=timeout)
        content = getattr(r, "content", b"") or b""
        try:
            ct = r.headers.get("Content-Type", "") or ""
        except Exception:
            ct = ""
        payload = None
        try:
            payload = r.json()
        except Exception:
            payload = None
        return _Resp(r.status_code, payload, getattr(r, "text", ""), content, ct)

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
    ct, raw_bytes = "", b""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_bytes = resp.read()
            status = resp.getcode()
            try:
                ct = resp.headers.get_content_type()
            except Exception:
                ct = (resp.headers.get("Content-Type", "") if resp.headers else "")
    except urllib.error.HTTPError as e:      # не-2xx: вернуть статус+тело, НЕ ронять
        try:
            raw_bytes = e.read()
        except Exception:
            raw_bytes = b""
        status = e.code
        try:
            ct = e.headers.get_content_type() if e.headers else ""
        except Exception:
            ct = ""
    # URLError/timeout НЕ ловим — пусть _request сочтёт транзиторным и ретайнет
    text = raw_bytes.decode("utf-8", "replace") if raw_bytes else ""
    payload = None
    if "json" in (ct or "").lower() or text[:1] in ("{", "["):  # PDF (%PDF) не парсим как json
        try:
            payload = _json.loads(text) if text else None
        except Exception:
            payload = None
    return _Resp(status, payload, text, raw_bytes, ct)


def _safe_json(r):
    """Тело как JSON; не JSON → {'raw': text} (не роняем разбор)."""
    try:
        return r.json()
    except Exception:
        return {"raw": getattr(r, "text", "")}


def _request(method, path, body=None, params=None, timeout=30, binary=False):
    """Один устойчивый вызов к Seller API. Возвращает распарсенный JSON (или _Resp при binary).

    Устойчивость (закон вечной машины):
      • ключа нет → _headers() роняет RuntimeError СРАЗУ (до петли — это не транзиторно).
      • 401/403 → OzonHTTPError сразу (ключи/права, не код — ретрай бессмыслен).
      • 429/5xx/timeout → до _MAX_RETRIES ретраев с jitter-бэкоффом.
      • иной не-2xx → OzonHTTPError (writer прочитает тело — 200≠успех работает и наоборот).
    Реальная сеть изолирована в _http_call (шов для тестов).
    """
    url = API + path
    headers = _headers()                 # ОДИН РАЗ до петли: нет ключа → RuntimeError, не ретрай
    retries = 0
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            r = _http_call(method, url, headers, body, params, timeout)
        except Exception as e:           # сетевой сбой/timeout — транзиторный
            last_exc = e
            if attempt + 1 < _MAX_RETRIES:
                import time, random
                time.sleep(0.5 + random.random() * 1.0)
                retries += 1
                continue
            raise RuntimeError(f"сеть к Ozon упала после {retries} ретраев: {e}")
        if r.status_code in (401, 403):
            raise OzonHTTPError(r.status_code, _safe_json(r), url)      # ключи/права, не код
        if r.status_code in _TRANSIENT and attempt + 1 < _MAX_RETRIES:
            import time, random
            time.sleep(0.5 + random.random() * 1.0)
            retries += 1
            continue
        if not (200 <= r.status_code < 300):
            raise OzonHTTPError(r.status_code, _safe_json(r), url)
        return r if binary else _safe_json(r)
    raise RuntimeError(f"исчерпаны ретраи к {url} (последняя ошибка: {last_exc})")


def _dry(dry, commit, label, call, payload):
    """ДВОЙНОЙ ГЕЙТ РУБИКОНА: реальный вызов ТОЛЬКО при (not dry AND commit).

    Иначе печатает ТОЧНЫЙ payload (что ушло бы) и возвращает муляж {'status':'dry'} — наружу
    ничего не летит. Гейт открыт → зовёт call(); fail-soft ловит транспортный сбой →
    {'status':'error'} (организм не падает — писатель/менеджер честно увидит ошибку).

    ВАЖНО про create_product: 'sent' = запрос ПРИНЯТ (получен task_id), а НЕ карточка создана.
    Создание асинхронно — истину даёт только import_info + read_shelf (закон OZ3: DONE=на витрине).
    """
    gate_open = (not dry) and commit
    if not gate_open:
        try:
            preview = json.dumps(payload, ensure_ascii=False)
        except Exception:
            preview = str(payload)
        print(f"  [DRY] {label}: {preview[:600]}")
        return {"status": "dry", "label": label, "would_send": payload,
                "gate": {"dry": bool(dry), "commit": bool(commit)}}
    try:
        res = call()
        return {"status": "sent", "label": label, "response": res}
    except Exception as e:
        return {"status": "error", "label": label, "_error": f"{type(e).__name__}: {e}"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  СПРАВОЧНИКИ КАТЕГОРИЙ (READ, 0₽) — у Ozon НЕТ авто-категории, это истина для сборки карточки
# ══════════════════════════════════════════════════════════════════════════════════════════════

def category_tree(language="DEFAULT", timeout=60):
    """POST /v1/description-category/tree → полное дерево категорий (ищем ЛИСТ: description_category_id+type_id).

    Пропускаем узлы с disabled==true. Это единственный законный источник id категории (OZ2: не выдумываем).
    """
    data = _request("POST", "/v1/description-category/tree", body={"language": language}, timeout=timeout)
    return data.get("result", data) if isinstance(data, dict) else data


def category_attributes(description_category_id, type_id, language="DEFAULT", timeout=60):
    """POST /v1/description-category/attribute → характеристики (пары category_id+type_id).

    is_required — ИСТИНА полноты карточки; dictionary_id>0 → значения тянуть через attribute_values.
    """
    body = {"description_category_id": int(description_category_id),
            "type_id": int(type_id), "language": language}
    data = _request("POST", "/v1/description-category/attribute", body=body, timeout=timeout)
    return data.get("result", data) if isinstance(data, dict) else data


def attribute_values(description_category_id, type_id, attribute_id,
                     limit=5000, last_value_id=0, language="DEFAULT", timeout=60):
    """POST /v1/description-category/attribute/values → словарь значений (dictionary_value_id).

    Курсор через last_value_id; has_next=true → тянуть дальше. id значения = dictionary_value_id в payload.
    Возвращает {'values':[...], 'has_next':bool}.
    """
    body = {"description_category_id": int(description_category_id), "type_id": int(type_id),
            "attribute_id": int(attribute_id), "limit": int(limit),
            "last_value_id": int(last_value_id), "language": language}
    data = _request("POST", "/v1/description-category/attribute/values", body=body, timeout=timeout)
    if isinstance(data, dict):
        return {"values": data.get("result", []), "has_next": bool(data.get("has_next"))}
    return {"values": data or [], "has_next": False}


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ЗАПИСЬ (двойной гейт РУБИКОНА — по умолчанию dry=True/commit=False, наружу НИЧЕГО)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def create_product(items, dry=True, commit=False, timeout=60):
    """POST /v3/product/import → залить карточку(и), ≤100 item за вызов.

    Ответ (при открытом гейте) = {"result":{"task_id":<int64>}} — АСИНХРОННАЯ КВИТАНЦИЯ, НЕ карточка.
    Обязательно опросить import_info(task_id), потом подтвердить read_shelf (OZ3: DONE = на витрине).
    """
    body = {"items": list(items)}
    return _dry(dry, commit, "create_product /v3/product/import",
                lambda: _request("POST", "/v3/product/import", body=body, timeout=timeout), body)


def set_price(prices, dry=True, commit=False, timeout=60):
    """POST /v1/product/import/prices → цены, ≤1000. Все суммы (price/old_price/min_price) СТРОКАМИ.

    old_price должен превышать price (иначе бессмыслен/отвергнут). Лимит ≤10 правок/час/товар.
    """
    body = {"prices": list(prices)}
    return _dry(dry, commit, "set_price /v1/product/import/prices",
                lambda: _request("POST", "/v1/product/import/prices", body=body, timeout=timeout), body)


def set_stock(stocks, dry=True, commit=False, timeout=60):
    """POST /v2/products/stocks → остатки, ≤100. warehouse_id ОБЯЗАТЕЛЕН для FBS (из warehouse_list).

    Лимит ≤1 правка/30мин/SKU. Доктрина: stock>0 = реальное обязательство продать → РУБИКОН.
    """
    body = {"stocks": list(stocks)}
    return _dry(dry, commit, "set_stock /v2/products/stocks",
                lambda: _request("POST", "/v2/products/stocks", body=body, timeout=timeout), body)


def archive_products(product_ids, dry=True, commit=False, timeout=60):
    """POST /v1/product/archive → снять карточку(и) в архив, ≤100 id за вызов.

    Архив = карточка скрывается с витрины/маркета (обратимо: unarchive). Остатки/цены остаются.
    Доктрина: дубль НЕ продаём — жив близнец; архив парка = снять дубль по слову оператора (РУБИКОН).
    """
    body = {"product_id": [int(pid) for pid in product_ids]}
    return _dry(dry, commit, "archive_products /v1/product/archive",
                lambda: _request("POST", "/v1/product/archive", body=body, timeout=timeout), body)


def ship_posting(posting_number, packages, additional_data=True, dry=True, commit=False, timeout=60):
    """POST /v2/posting/fbs/ship → отгрузка отправления (M4: логистика тронута).

    posting_number — ОДНА строка. packages=[{"products":[{"product_id":int,"quantity":int}]}]
    (внутренний ключ products, НЕ items; product_id — наименее надёжное поле, живьём часто нужен маппинг).
    """
    body = {"posting_number": str(posting_number), "packages": list(packages),
            "with": {"additional_data": bool(additional_data)}}
    return _dry(dry, commit, "ship_posting /v2/posting/fbs/ship",
                lambda: _request("POST", "/v2/posting/fbs/ship", body=body, timeout=timeout), body)


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ЧТЕНИЕ ИТОГА / ВИТРИНЫ / СКЛАДОВ / ЭТИКЕТКИ (READ, 0₽; fail-soft; 200≠успех)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def import_info(task_id, timeout=30):
    """POST /v1/product/import/info → ОПРОС задачи create_product. АСИНХРОННО → опрашивать до итога.

    result.items[]: offer_id, product_id(0 пока нет успеха), status(pending|imported|failed), errors[].
    Успех item = status=='imported' AND product_id>0 AND errors==[]. Возвращает список items.
    """
    data = _request("POST", "/v1/product/import/info", body={"task_id": int(task_id)}, timeout=timeout)
    res = data.get("result", data) if isinstance(data, dict) else data
    if isinstance(res, dict):
        return res.get("items", [])
    return res if isinstance(res, list) else []


def _extract_present_stock(stocks):
    """Достать present-остаток из разных форм stocks (dict {present}, {stocks:[...]}, list)."""
    def _int(x):
        try:
            return int(x or 0)
        except (TypeError, ValueError):
            return 0
    if isinstance(stocks, dict):
        if "present" in stocks:
            return _int(stocks.get("present"))
        inner = stocks.get("stocks")
        if isinstance(inner, list):
            return sum(_int(s.get("present")) for s in inner if isinstance(s, dict))
    if isinstance(stocks, list):
        return sum(_int(s.get("present")) for s in stocks if isinstance(s, dict))
    return 0


def _parse_shelf_item(it):
    """Один item витрины → форма контракта ozon_state.ingest_shelf_read / proof-gate.

    Защита от версий: v3+ статус-блок = 'statuses', v2 = 'status'; видимость — visible|visibility_details.
    """
    if not isinstance(it, dict):
        return {"offer_id": None, "product_id": 0, "moderation": None, "visible": False,
                "stock": 0, "price": None, "price_index": None, "sku": None,
                "errors": ["item не dict"], "missing_required_attrs": []}
    offer_id = it.get("offer_id") or it.get("offerId")
    product_id = it.get("id") or it.get("product_id") or 0
    sku = it.get("sku")                       # Ozon sku (int64) — нужен для rating-by-sku (НЕ product_id!)
    sb = it.get("statuses") if isinstance(it.get("statuses"), dict) else \
        (it.get("status") if isinstance(it.get("status"), dict) else {})
    moderation = sb.get("moderate_status") or sb.get("moderation_status") or it.get("moderate_status")
    visible = it.get("visible")
    if visible is None:
        vd = it.get("visibility_details") if isinstance(it.get("visibility_details"), dict) else {}
        if "active_product" in vd:                      # v2-схема
            visible = bool(vd.get("active_product"))
        else:                                           # v3-схема: витрина = цена И остаток
            visible = bool(vd.get("has_price") and vd.get("has_stock"))
    visible = bool(visible)
    stock = _extract_present_stock(it.get("stocks"))
    errors = []
    for k in ("item_errors", "errors"):
        v = sb.get(k) if isinstance(sb, dict) else None
        v = v or it.get(k)
        if isinstance(v, list):
            errors.extend(v)
    decl = (sb.get("decline_reasons") if isinstance(sb, dict) else None) or it.get("decline_reasons")
    if isinstance(decl, list):
        errors.extend(decl)
    return {"offer_id": offer_id, "product_id": product_id, "moderation": moderation,
            "visible": visible, "stock": stock, "price": it.get("price"),
            "price_index": it.get("price_index") or it.get("price_indexes"),
            "sku": it.get("sku"),
            "errors": errors, "missing_required_attrs": []}


def read_shelf(offer_ids, timeout=30):
    """POST /v3/product/info/list → витрина в форме ozon_state.ingest_shelf_read.

    Возвращает {'ok':bool, 'cards':[{offer_id,product_id,moderation,visible,stock,price,price_index,
    errors,missing_required_attrs}], '_error'?}. Fail-soft: нет ключа/сеть/HTTP → ok=False + причина.
    ⚠ Путь версионирован (PRODUCT_INFO_LIST_PATH, по умолч. /v3): на живой сверке /v1 может дать 404.
    """
    if not creds_present():
        return {"ok": False, "cards": [], "_error": "нет ключей Ozon (OZON_CLIENT_ID/OZON_API_KEY)"}
    body = {"offer_id": [str(o) for o in offer_ids], "product_id": [], "sku": []}
    try:
        data = _request("POST", PRODUCT_INFO_LIST_PATH, body=body, timeout=timeout)
    except Exception as e:
        return {"ok": False, "cards": [], "_error": f"{type(e).__name__}: {e}"}
    items = data.get("items") if isinstance(data, dict) else None
    if items is None and isinstance(data, dict):
        res = data.get("result")
        items = res.get("items", []) if isinstance(res, dict) else []
    return {"ok": True, "cards": [_parse_shelf_item(it) for it in (items or [])]}


def product_visible(offer_id, timeout=30):
    """Один товар с витрины (КОНТРАКТ proof-gate ozon_proof.verify_publish):
    {moderation, visible, stock, errors, price_index} (+ offer_id/product_id/price). Fail-soft.
    """
    res = read_shelf([offer_id], timeout=timeout)
    if not res.get("ok"):
        return {"moderation": None, "visible": False, "stock": 0, "errors": [res.get("_error")],
                "price_index": None, "offer_id": str(offer_id), "product_id": 0,
                "_error": res.get("_error")}
    for c in res.get("cards", []):
        if str(c.get("offer_id")) == str(offer_id):
            return c
    return {"moderation": None, "visible": False, "stock": 0,
            "errors": [f"offer_id {offer_id} не найден на витрине"],
            "price_index": None, "offer_id": str(offer_id), "product_id": 0}


def read_price_index(offer_ids, limit=1000, timeout=30):
    """POST /v5/product/info/prices → цена + индекс цен. Fail-soft.

    color_index: WITHOUT_INDEX|GREEN|YELLOW|RED. RED = карточка скрыта из органической выдачи (OZ5).
    Читаем ЧИСЛА (запись — строки). Возвращает {'ok':bool,'items':[...],'cursor':str,'_error'?}.
    """
    if not creds_present():
        return {"ok": False, "items": [], "_error": "нет ключей Ozon"}
    body = {"filter": {"offer_id": [str(o) for o in offer_ids], "product_id": [], "visibility": "ALL"},
            "cursor": "", "limit": int(limit)}
    try:
        data = _request("POST", PRODUCT_INFO_PRICES_PATH, body=body, timeout=timeout)
    except Exception as e:
        return {"ok": False, "items": [], "_error": f"{type(e).__name__}: {e}"}
    items = data.get("items") if isinstance(data, dict) else None
    if items is None and isinstance(data, dict):
        res = data.get("result")
        items = res.get("items", []) if isinstance(res, dict) else []
    out = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        price = it.get("price") if isinstance(it.get("price"), dict) else {}
        pidx = it.get("price_indexes") if isinstance(it.get("price_indexes"), dict) else {}
        color = pidx.get("color_index")
        out.append({"offer_id": it.get("offer_id"),
                    "product_id": it.get("product_id") or it.get("id"),
                    "price": price.get("price"), "old_price": price.get("old_price"),
                    "min_price": price.get("min_price"), "color_index": color})
    return {"ok": True, "items": out, "cursor": (data.get("cursor", "") if isinstance(data, dict) else "")}


def read_content_rating(offer_ids, limit=100, timeout=30):
    """POST /v1/product/rating-by-sku → контент-рейтинг карточек 0..100 (аналог contentRating ЯМ).

    Ozon отдаёт рейтинг ТОЛЬКО по своему sku (int64), НЕ по offer_id/product_id → два шага:
      шаг 1: read_shelf() → item.sku (аддитивное поле в _parse_shelf_item);
      шаг 2: батчами ≤100 POST {"skus":[int…]}.
    rating=None у карточки = ещё НЕ оценена (Ozon считает ~1 сутки) — это НЕ ошибка и НЕ ретрай.
    groups[].improve_attributes — конкретные атрибуты, что поднимут рейтинг (actionable).
    Fail-soft: {'ok':bool,'ratings':[{offer_id,sku,rating,groups}],'not_rated':[{offer_id,sku}],'_error'?}.
    """
    if not creds_present():
        return {"ok": False, "ratings": [], "_error": "нет ключей Ozon"}
    oids = [str(o) for o in offer_ids]
    shelf = read_shelf(oids, timeout=timeout)
    sku_of = {}
    for c in (shelf.get("cards") or []):
        sk = c.get("sku")
        if sk is not None:
            try:
                n = int(sk)
            except (TypeError, ValueError):
                n = 0
            if n > 0:                       # sku≤0 = припаркованная (SPU-дубль, не продаётся) — рейтинга нет
                sku_of[str(c.get("offer_id"))] = n
    if not sku_of:
        return {"ok": bool(shelf.get("ok")), "ratings": [],
                "_error": None if shelf.get("ok") else shelf.get("_error"),
                "not_rated": [{"offer_id": o, "sku": None} for o in oids]}
    try:
        data = _request("POST", PRODUCT_RATING_PATH,
                        body={"skus": [str(s) for s in sku_of.values()]}, timeout=timeout)
    except Exception as e:
        return {"ok": False, "ratings": [], "_error": f"{type(e).__name__}: {e}"}
    by_sku = {}
    for p in ((data.get("products") if isinstance(data, dict) else (data or [])) or []):
        if isinstance(p, dict) and p.get("sku") is not None:
            by_sku[int(p["sku"])] = p
    ratings, not_rated = [], []
    for off in oids:
        sk = sku_of.get(off)
        p = by_sku.get(sk) if sk is not None else None
        if p is not None:
            ratings.append({"offer_id": off, "sku": sk, "rating": p.get("rating"),
                            "groups": p.get("groups")})
        else:
            not_rated.append({"offer_id": off, "sku": sk})
    return {"ok": True, "ratings": ratings, "not_rated": not_rated}


def warehouse_list(timeout=30):
    """POST /v2/warehouse/list → склады FBS. ИСТОЧНИК warehouse_id для set_stock (не выдумываем!).

    /v1/warehouse/list → 400 code 9 (obsolete, нельзя использовать) — ЛИВЫМ проверено 2026-09-08;
    /v2/warehouse/list отвечает на верхнем уровне {'warehouses':[...]} (НЕ в result).
    Возвращает {'ok':bool,'warehouses':[...],'_error'?}. Fail-soft.
    """
    if not creds_present():
        return {"ok": False, "warehouses": [], "_error": "нет ключей Ozon"}
    try:
        data = _request("POST", "/v2/warehouse/list", body={}, timeout=timeout)
    except Exception as e:
        return {"ok": False, "warehouses": [], "_error": f"{type(e).__name__}: {e}"}
    res = data.get("warehouses", []) if isinstance(data, dict) else (data or [])
    return {"ok": True, "warehouses": res if isinstance(res, list) else []}


def package_label(posting_numbers, timeout=60):
    """POST /v2/posting/fbs/package-label → PDF-этикетка(и). Тело: {"posting_number":[...]} (ЗНАЧЕНИЕ — МАССИВ).

    Ответ БИНАРНЫЙ (PDF). Если Content-Type == application/json → это КОНВЕРТ ОШИБКИ (провал), не этикетка.
    Возвращает {'ok':bool,'content_type':str,'pdf_bytes':int,'_pdf':bytes} или {'ok':False,'error':...}.
    Fail-soft. Гейта нет: чтение PDF ничего не меняет и не двигает деньги (сама отгрузка — ship_posting).
    """
    if not creds_present():
        return {"ok": False, "_error": "нет ключей Ozon"}
    body = {"posting_number": list(posting_numbers)}
    try:
        resp = _request("POST", "/v2/posting/fbs/package-label", body=body, timeout=timeout, binary=True)
    except Exception as e:
        return {"ok": False, "_error": f"{type(e).__name__}: {e}"}
    ct = (resp.content_type or "").lower()
    content = resp.content or b""
    if "application/pdf" in ct or content[:4] == b"%PDF":
        return {"ok": True, "content_type": ct, "pdf_bytes": len(content), "_pdf": content}
    # JSON или иное → конверт ошибки
    return {"ok": False, "content_type": ct,
            "error": (resp._payload if resp._payload is not None else (resp.text or "")[:300])}


if __name__ == "__main__":
    print(json.dumps({
        "creds_present": creds_present(),
        "api": API,
        "product_info_list_path": PRODUCT_INFO_LIST_PATH,
        "product_info_prices_path": PRODUCT_INFO_PRICES_PATH,
        "note": ("реальные вызовы требуют OZON_CLIENT_ID/OZON_API_KEY; запись под двойным гейтом "
                 "(dry=True/commit=False по умолчанию — наружу ничего). ⚠ путь витрины версионирован: "
                 "на живой сверке /v1 может дать 404 → правь PRODUCT_INFO_LIST_PATH."),
    }, ensure_ascii=False, indent=2))

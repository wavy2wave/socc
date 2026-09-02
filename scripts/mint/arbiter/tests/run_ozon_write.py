#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON WRITE ПРИЁМКА — сухая плоскость записи/чтения ОЗОН-МЕНЕДЖЕРА (0₽, без сети, без ключа).

Веха M1 оси ОЗОН: доказывает ozon_card_v1 (сборщик item /v3/product/import) + ozon_hands_write_v1
(руки на Seller API). Все тесты ОФФЛАЙН-детерминированы: НИКАКОЙ сети, НИКАКОГО реального ключа,
НИКАКИХ денег. Сеть изолирована в шве _http_call — тесты подменяют ИМЕННО его (не _request), чтобы
проверялась устойчивая петля ретраев. Реальные ключи в процесс НЕ загружаются: _ENV_TRIED=True глушит
загрузчик .env, ключи подставляем фейковые. Реальный залив/деньги — только по отмашке (RUBICON).

СБОРЩИК КАРТОЧКИ (ozon_card_v1):
  W1  card_explicit_built      — явная категория → item собран, price СТРОКОЙ, vat '0.2', RUB, габариты/фото/штрихкод.
  W2  card_need_mapping_block  — нет категории → item=None, need_mapping, can_build=False (у Ozon НЕТ авто-категории, OZ2).
  W3  card_vat_normalization   — '20'→'0.2', '0,2'→'0.2', проценты/доля/запятая; None/мусор/вне-энум → '0'+defaulted.
  W4  card_attributes_nesting  — {complex_id,id,values:[{dictionary_value_id,value}]}; enum без соответствия НЕ шлём (не выдумываем dvid).
  W5  card_dimensions          — родные мм/г как есть; см/кг конверт ×10/×1000; неполный набор → None (не выдумываем).
  W6  card_name_verbatim       — имя 1-в-1 («0,3×100 м» цело); квалификатор суффиксом только при unique_name.
  W7  card_carderror_guards    — нет offer_id / нет имени / цена≤0 → CardError (непоправимое).
  W8  card_import_body_filters — import_body отсеивает item=None и принимает сырые item.
  W9  card_old_price_gt_only   — old_price только если СТРОГО > price.
  W10 card_honest_flags        — нет фото/габаритов/штрихкода → честные флаги + поля не шлём.
  W11 card_price_rounding       — дробь округляется в СТРОКУ целых ₽; 0<цена<0.5 → 0₽ → CardError (гейт по выходу).
  W31 card_offer_id_truncated   — offer_id>50 → обрезан + ЧЕСТНЫЙ флаг offer_id_truncated/offer_id_full (риск коллизии id).

РУКИ ЗАПИСИ/ЧТЕНИЯ (ozon_hands_write_v1):
  W12 gate_dry_no_send         — dry / dry+commit / not-dry+not-commit → 'dry', сеть НЕ дёрнута, would_send точен.
  W13 gate_open_sends          — not dry AND commit → 'sent', тело точное, сеть вызвана ровно раз.
  W14 gate_failsoft_error      — открытый гейт + сбой транспорта → 'error' (организм не падает).
  W15 request_401_no_retry     — 401 → сразу ошибка, БЕЗ ретраев (ключи/права, не код).
  W16 request_transient_then_ok— 429 → ретрай → 200 (моргнуло — не «мост мёртв»).
  W17 request_transient_exhaust— всегда 503 → исчерпал _MAX_RETRIES → ошибка.
  W18 request_network_retry    — сетевой сбой → ретрай → успех.
  W19 request_non2xx_body      — 400 → OzonHTTPError с телом (writer прочитает причину).
  W20 shelf_v3_parse           — /v3 statuses+visible+stocks{present} → контракт витрины.
  W21 shelf_v2_errors          — /v2 status+visibility_details+stocks[] с errors на 200 (200≠успех).
  W22 product_visible_contract — форма proof-gate {moderation,visible,stock,errors,price_index}; не найдено → visible=False.
  W23 shelf_failsoft_no_creds  — нет ключей → ok=False (нет данных ≠ ноль).
  W24 extract_stock_variants   — present-остаток из dict/{stocks:[]}/list/мусора.
  W25 price_index_parse        — цена+color_index (RED=скрыт из выдачи).
  W26 package_label_pdf        — бинарный PDF → ok + %PDF.
  W27 package_label_json_err   — JSON вместо PDF → ok=False (конверт ошибки, не этикетка).
  W28 write_body_shapes        — set_stock/ship_posting шлют точную форму тела.
  W29 import_info_parse        — опрос async-задачи → items[].
  W30 warehouse_list           — склады + fail-soft без ключей.
"""
import io
import os
import sys
import contextlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ozon_card_v1 as card              # noqa: E402
import ozon_hands_write_v1 as hands      # noqa: E402

# ── Глушим загрузчик .env (реальный КОМПРОМЕТИРОВАННЫЙ ключ в процесс НЕ попадает) + фейк-ключи ──
hands._ENV_TRIED = True
os.environ["OZON_CLIENT_ID"] = "test-cid"
os.environ["OZON_API_KEY"] = "test-key"

# Ретраи без реального ожидания: глушим time.sleep на время приёмки (_request делает import time).
import time as _time                     # noqa: E402
_ORIG_SLEEP = _time.sleep
_time.sleep = lambda *a, **k: None


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


def _quiet(fn, *a, **kw):
    """Прогнать шумную функцию молча (dry-ветка _dry печатает [DRY]) — держим чистый вывод."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*a, **kw)


def _resp(status, payload=None, text="", content=b"", content_type=""):
    return hands._Resp(status, payload, text, content, content_type)


def _script(*responses):
    """Фейковый _http_call: выдаёт responses по порядку (Exception → бросает). Держит счётчик .state."""
    seq = list(responses)
    st = {"n": 0}

    def fake(method, url, headers, body, params, timeout):
        i = st["n"]
        st["n"] += 1
        r = seq[i] if i < len(seq) else seq[-1]
        if isinstance(r, BaseException):
            raise r
        return r
    fake.state = st
    return fake


def _capture(resp):
    """Фейковый _http_call: пишет отправленные тела в .rec['bodies'], всегда возвращает resp."""
    rec = {"bodies": [], "n": 0}

    def fake(method, url, headers, body, params, timeout):
        rec["bodies"].append(body)
        rec["n"] += 1
        return resp
    fake.rec = rec
    return fake


# ══════════════════════════════════════════════ СБОРЩИК КАРТОЧКИ ══════════════════════════════

def t1_card_explicit_built():
    prod = {"offer_id": "OZ-1", "name": "Органайзер настольный", "price": 499.0,
            "description_category_id": 17028922, "type_id": 971082156, "vat": "20",
            "dimensions": {"depth": 120, "width": 80, "height": 40, "weight": 150},
            "images": ["https://img/x.jpg"], "barcode": "4600000000001"}
    r = card.to_item(prod)
    it, m = r["item"], r["meta"]
    cond = (it is not None and m["can_build"] and not m["need_mapping"]
            and it["price"] == "499" and isinstance(it["price"], str)
            and it["vat"] == "0.2" and it["currency_code"] == "RUB"
            and it["description_category_id"] == 17028922 and it["type_id"] == 971082156
            and it["depth"] == 120 and it["weight"] == 150
            and it["dimension_unit"] == "mm" and it["weight_unit"] == "g"
            and it["primary_image"] == "https://img/x.jpg" and it["barcode"] == "4600000000001")
    return cond, f"can_build={m['can_build']} price='{it['price']}'(str) vat='{it['vat']}' cat={it['description_category_id']}"


def t2_card_need_mapping_block():
    r = card.to_item({"offer_id": "OZ-2", "name": "Товар без категории", "price": 100})
    m = r["meta"]
    cond = (r["item"] is None and m["need_mapping"] and not m["can_build"]
            and m["block_reason"] and "OZ2" in m["block_reason"] and m["category_source"] == "none")
    return cond, f"item={r['item']} need_mapping={m['need_mapping']} block='{(m['block_reason'] or '')[:28]}'"


def t3_card_vat_normalization():
    exact = {"20": "0.2", "0,2": "0.2", "0.2": "0.2", "10": "0.1", "7": "0.07", "5": "0.05", "0": "0"}
    good = all(card._normalize_vat(k) == (v, False) for k, v in exact.items())
    # float-проценты и десятичные строки (str(20.0)=='20.0') — числовой фолбэк, НЕ тихий 0% НДС
    numeric = (card._normalize_vat(20.0) == ("0.2", False)
               and card._normalize_vat("20.0") == ("0.2", False)
               and card._normalize_vat(10.0) == ("0.1", False)
               and card._normalize_vat(0.2) == ("0.2", False))
    defs = (card._normalize_vat(None) == ("0", True)
            and card._normalize_vat("abc") == ("0", True)
            and card._normalize_vat("0.15") == ("0", True))   # вне энума → дефолт
    return good and numeric and defs, f"энум-ок={good} float-проценты={numeric} дефолты(None/мусор/вне-энум)={defs}"


def t4_card_attributes_nesting():
    profile = {
        "attr_constants": {"Бренд": {"id": 85, "dictionary_value_id": 971082156, "value": "ATLAS EDGE"}},
        "attr_specs": {"Ширина": {"id": 4180, "from": "width_mm"}},
        "attr_enums": {
            "Материал": {"id": 4191, "values": {"пвд": 61575, "пнд": 61576}},
            "Цвет": {"id": 10096, "values": {"красный": 61111}},   # не совпадёт → НЕ шлём
        },
    }
    prod = {"offer_id": "OZ-4", "name": "Плёнка", "price": 300,
            "description_category_id": 17028922, "type_id": 971082156, "_profile": profile,
            "_spec": {"width_mm": 100, "Материал": "ПВД (полиэтилен высокого давления)", "Цвет": "неоновый"}}
    r = card.to_item(prod)
    attrs = {a["id"]: a for a in r["item"].get("attributes", [])}
    brand, width, mat = attrs.get(85), attrs.get(4180), attrs.get(4191)
    cond = (brand and brand["complex_id"] == 0
            and brand["values"][0]["dictionary_value_id"] == 971082156
            and brand["values"][0]["value"] == "ATLAS EDGE"
            and width and width["values"][0] == {"value": "100"}
            and "dictionary_value_id" not in width["values"][0]        # свободная форма — без dvid
            and mat and mat["values"][0]["dictionary_value_id"] == 61575  # мягкое совпадение «пвд»
            and 10096 not in attrs                                       # НЕ выдумали dvid для «неоновый»
            and r["meta"]["attrs_built"] == 3)
    return cond, f"attrs_built={r['meta']['attrs_built']} (бренд+спека+enum), Цвет-без-совпадения отброшен={10096 not in attrs}"


def t5_card_dimensions():
    native = card._ozon_dimensions({"dimensions": {"depth": 120, "width": 80, "height": 40, "weight": 150}})
    conv = card._ozon_dimensions({"weightDimensions": {"length": 12, "width": 8, "height": 4, "weight": 0.15}})
    incomplete = card._ozon_dimensions({"dimensions": {"depth": 120}})
    submm = card._ozon_dimensions({"dimensions": {"depth": 0.3, "width": 8, "height": 4, "weight": 150}})
    want = {"depth": 120, "width": 80, "height": 40, "weight": 150, "dimension_unit": "mm", "weight_unit": "g"}
    cond = native == want and conv == want and incomplete is None and submm is None
    return cond, f"родные={native == want} конверт(см/кг→мм/г)={conv == want} неполный→None={incomplete is None} суб-мм→None={submm is None}"


def t6_card_name_verbatim():
    base = "Плёнка ПВД 0,3×100 м"
    r1 = card.to_item({"offer_id": "OZ-6", "name": base, "price": 100,
                       "description_category_id": 1, "type_id": 1})
    verbatim = r1["item"]["name"] == base and r1["meta"]["name_source"] == "verbatim"
    r2 = card.to_item({"offer_id": "OZ-6b", "name": base, "price": 100,
                       "description_category_id": 1, "type_id": 1,
                       "unique_name": True, "house_brand": "ATLAS EDGE"})
    nm = r2["item"]["name"]
    uniq = ("0,3×100 м" in nm and "ATLAS EDGE" in nm and nm.startswith(base)
            and r2["meta"]["name_source"] == "unique")
    return verbatim and uniq, f"verbatim='{r1['item']['name']}' · unique='{nm}'"


def t7_card_carderror_guards():
    def _raises(prod):
        try:
            card.to_item(prod)
            return False
        except card.CardError:
            return True
    no_sku = _raises({"name": "x", "price": 1})
    no_name = _raises({"offer_id": "OZ", "price": 1})
    bad_price = _raises({"offer_id": "OZ", "name": "x", "price": 0})
    zero_round = _raises({"offer_id": "OZ", "name": "x", "price": 0.4})   # 0<цена<0.5 → округляется в 0₽
    return (no_sku and no_name and bad_price and zero_round,
            f"нет-sku={no_sku} нет-имени={no_name} цена≤0={bad_price} 0.4→0₽={zero_round}")


def t8_card_import_body_filters():
    good = card.to_item({"offer_id": "OZ-8", "name": "x", "price": 100,
                         "description_category_id": 1, "type_id": 1})
    blocked = card.to_item({"offer_id": "OZ-8b", "name": "y", "price": 100})   # нет категории → item=None
    body = card.import_body([good, blocked, {"offer_id": "raw", "name": "z"}])
    cond = (len(body["items"]) == 2 and body["items"][0]["offer_id"] == "OZ-8"
            and any(i.get("offer_id") == "raw" for i in body["items"]))
    return cond, f"items={len(body['items'])} (None-item отсеян, сырой принят)"


def t9_card_old_price_gt_only():
    hi = card.to_item({"offer_id": "OZ-9", "name": "x", "price": 100, "old_price": 150,
                       "description_category_id": 1, "type_id": 1})
    lo = card.to_item({"offer_id": "OZ-9b", "name": "x", "price": 100, "old_price": 80,
                       "description_category_id": 1, "type_id": 1})
    cond = hi["item"].get("old_price") == "150" and "old_price" not in lo["item"]
    return cond, f"old>price→'{hi['item'].get('old_price')}' · old<price→нет={'old_price' not in lo['item']}"


def t10_card_honest_flags():
    r = card.to_item({"offer_id": "OZ-10", "name": "x", "price": 100,
                      "description_category_id": 1, "type_id": 1})
    m, it = r["meta"], r["item"]
    cond = (m["missing_images"] and m["missing_dimensions"] and not m["has_barcode"]
            and "barcode" not in it and "images" not in it)
    return cond, f"missing_images={m['missing_images']} missing_dims={m['missing_dimensions']} has_barcode={m['has_barcode']}"


def t11_card_price_rounding():
    r = card.to_item({"offer_id": "OZ-11", "name": "x", "price": 499.6,
                      "description_category_id": 1, "type_id": 1})
    cond = r["item"]["price"] == "500" and isinstance(r["item"]["price"], str) and r["meta"]["price"] == "500"
    return cond, f"499.6 → '{r['item']['price']}' (строка целых ₽)"


# ══════════════════════════════════════════════ РУКИ ЗАПИСИ/ЧТЕНИЯ ═════════════════════════════

def t12_gate_dry_no_send():
    fake = _capture(_resp(200, {"result": {"task_id": 1}}))
    hands._http_call = fake
    dry = _quiet(hands.create_product, [{"offer_id": "X"}], dry=True, commit=False)
    dc = _quiet(hands.create_product, [{"offer_id": "X"}], dry=True, commit=True)
    nc = _quiet(hands.create_product, [{"offer_id": "X"}], dry=False, commit=False)
    cond = (dry["status"] == "dry" and dc["status"] == "dry" and nc["status"] == "dry"
            and fake.rec["n"] == 0
            and dry["would_send"] == {"items": [{"offer_id": "X"}]}
            and dry["gate"] == {"dry": True, "commit": False})
    return cond, f"3 попытки → dry, сеть вызвана {fake.rec['n']} раз (ждём 0)"


def t13_gate_open_sends():
    fake = _capture(_resp(200, {"result": {"task_id": 777}}))
    hands._http_call = fake
    res = hands.create_product([{"offer_id": "X"}], dry=False, commit=True)
    cond = (res["status"] == "sent" and res["response"] == {"result": {"task_id": 777}}
            and fake.rec["n"] == 1 and fake.rec["bodies"][0] == {"items": [{"offer_id": "X"}]})
    return cond, f"status={res['status']} task_id получен, тело={fake.rec['bodies'][0]}"


def t14_gate_failsoft_error():
    hands._http_call = _script(_resp(400, {"error": "bad"}))   # не-2xx не-транзиторный → raise → _dry ловит
    res = hands.set_price([{"offer_id": "X", "price": "1"}], dry=False, commit=True)
    cond = res["status"] == "error" and "OzonHTTPError" in res["_error"]
    return cond, f"status={res['status']} _error='{res['_error'][:40]}'"


def t15_request_401_no_retry():
    f = _script(_resp(401, {"error": "invalid key"}))
    hands._http_call = f
    raised = False
    try:
        hands._request("POST", "/x", body={})
    except hands.OzonHTTPError as e:
        raised = (e.status == 401)
    return raised and f.state["n"] == 1, f"401→ошибка сразу, вызовов={f.state['n']} (ждём 1, без ретрая)"


def t16_request_transient_then_ok():
    f = _script(_resp(429, {}), _resp(200, {"ok": 1}))
    hands._http_call = f
    out = hands._request("POST", "/x", body={})
    return out == {"ok": 1} and f.state["n"] == 2, f"429→ретрай→200, вызовов={f.state['n']}"


def t17_request_transient_exhaust():
    f = _script(_resp(503, {"e": 1}))
    hands._http_call = f
    raised = False
    try:
        hands._request("POST", "/x", body={})
    except hands.OzonHTTPError as e:
        raised = (e.status == 503)
    return raised and f.state["n"] == hands._MAX_RETRIES, f"503×∞→ошибка, вызовов={f.state['n']}=_MAX_RETRIES"


def t18_request_network_retry():
    f = _script(ConnectionError("boom"), _resp(200, {"ok": 2}))
    hands._http_call = f
    out = hands._request("POST", "/x", body={})
    return out == {"ok": 2} and f.state["n"] == 2, f"сеть-сбой→ретрай→успех, вызовов={f.state['n']}"


def t19_request_non2xx_body():
    f = _script(_resp(400, {"code": 9, "message": "bad payload"}))
    hands._http_call = f
    err = None
    try:
        hands._request("POST", "/x", body={})
    except hands.OzonHTTPError as e:
        err = e
    cond = err is not None and err.status == 400 and err.body.get("code") == 9 and f.state["n"] == 1
    return cond, f"400→OzonHTTPError, тело.code={getattr(err, 'body', {}) and err.body.get('code')}"


def t20_shelf_v3_parse():
    data = {"items": [{"offer_id": "OZ-A", "id": 555,
                       "statuses": {"moderate_status": "approved", "item_errors": []},
                       "visible": True, "stocks": {"present": 7}, "price": "499", "price_index": "0.9"}]}
    hands._http_call = _script(_resp(200, data))
    res = hands.read_shelf(["OZ-A"])
    c = res["cards"][0]
    cond = (res["ok"] and c["offer_id"] == "OZ-A" and c["product_id"] == 555
            and c["moderation"] == "approved" and c["visible"] is True and c["stock"] == 7
            and c["errors"] == [] and c["price_index"] == "0.9")
    return cond, f"v3: mod={c['moderation']} visible={c['visible']} stock={c['stock']}"


def t21_shelf_v2_errors():
    data = {"result": {"items": [{"offer_id": "OZ-B", "product_id": 556,
            "status": {"moderation_status": "processed", "errors": ["нет фото"]},
            "visibility_details": {"active_product": False},
            "stocks": {"stocks": [{"present": 3}, {"present": 2}]}}]}}
    hands._http_call = _script(_resp(200, data))
    res = hands.read_shelf(["OZ-B"])
    c = res["cards"][0]
    cond = (res["ok"] and c["moderation"] == "processed" and c["visible"] is False
            and c["stock"] == 5 and c["errors"] == ["нет фото"] and c["product_id"] == 556)
    return cond, f"v2: mod={c['moderation']} visible={c['visible']} stock={c['stock']} errors={c['errors']} (200≠успех)"


def t22_product_visible_contract():
    data = {"items": [{"offer_id": "OZ-V", "id": 1, "statuses": {"moderate_status": "ok"},
                       "visible": True, "stocks": {"present": 2}, "price_index": "1.0"}]}
    hands._http_call = _script(_resp(200, data))
    c = hands.product_visible("OZ-V")
    keys = {"moderation", "visible", "stock", "errors", "price_index"}
    hit = keys <= set(c.keys()) and c["visible"] is True and c["stock"] == 2 and c["moderation"] == "ok"
    hands._http_call = _script(_resp(200, {"items": []}))
    nf = hands.product_visible("OZ-MISSING")
    miss = nf["visible"] is False and nf["stock"] == 0 and bool(nf["errors"])
    return hit and miss, f"контракт-ключи={keys <= set(c.keys())} · не-найдено→visible=False,stock=0={miss}"


def t23_shelf_failsoft_no_creds():
    orig = hands.creds_present
    hands.creds_present = lambda: False
    try:
        res = hands.read_shelf(["X"])
    finally:
        hands.creds_present = orig
    cond = (not res["ok"]) and res["cards"] == [] and bool(res["_error"])
    return cond, f"нет ключей → ok={res['ok']} _error='{res['_error'][:30]}'"


def t24_extract_stock_variants():
    E = hands._extract_present_stock
    cond = (E({"present": 7}) == 7 and E({"stocks": [{"present": 3}, {"present": 2}]}) == 5
            and E([{"present": 4}, {"present": 1}]) == 5 and E(None) == 0 and E("junk") == 0)
    return cond, f"present={E({'present': 7})} stocks[]={E({'stocks': [{'present': 3}, {'present': 2}]})} list={E([{'present': 4}, {'present': 1}])} мусор={E('junk')}"


def t25_price_index_parse():
    data = {"items": [{"offer_id": "OZ-P", "product_id": 9,
                       "price": {"price": "499", "old_price": "599", "min_price": "450"},
                       "price_indexes": {"color_index": "RED"}}], "cursor": "NEXT"}
    hands._http_call = _script(_resp(200, data))
    res = hands.read_price_index(["OZ-P"])
    it = res["items"][0]
    cond = (res["ok"] and it["offer_id"] == "OZ-P" and it["price"] == "499"
            and it["old_price"] == "599" and it["min_price"] == "450"
            and it["color_index"] == "RED" and res["cursor"] == "NEXT")
    return cond, f"price={it['price']} color_index={it['color_index']} (RED=скрыт) cursor={res['cursor']}"


def t26_package_label_pdf():
    hands._http_call = _script(_resp(200, None, "", b"%PDF-1.4\n stub", "application/pdf"))
    res = hands.package_label(["POST-1"])
    cond = res["ok"] and res["content_type"] == "application/pdf" and res["pdf_bytes"] > 0 and res["_pdf"][:4] == b"%PDF"
    return cond, f"ok={res['ok']} ct={res['content_type']} pdf_bytes={res['pdf_bytes']}"


def t27_package_label_json_err():
    hands._http_call = _script(_resp(200, {"code": 404, "message": "not found"},
                                     '{"code":404}', b'{"code":404}', "application/json"))
    res = hands.package_label(["POST-X"])
    cond = (not res["ok"]) and res["content_type"] == "application/json" and res["error"].get("code") == 404
    return cond, f"ok={res['ok']} (JSON вместо PDF = конверт ошибки) error.code={res['error'].get('code')}"


def t28_write_body_shapes():
    sink = _capture(_resp(200, {"result": True}))
    hands._http_call = sink
    hands.set_stock([{"offer_id": "S", "stock": 5, "warehouse_id": 2390811}], dry=False, commit=True)
    hands.ship_posting("POST-9", [{"products": [{"product_id": 1, "quantity": 1}]}], dry=False, commit=True)
    b_stock, b_ship = sink.rec["bodies"][0], sink.rec["bodies"][1]
    cond = (b_stock == {"stocks": [{"offer_id": "S", "stock": 5, "warehouse_id": 2390811}]}
            and b_ship["posting_number"] == "POST-9"
            and b_ship["packages"] == [{"products": [{"product_id": 1, "quantity": 1}]}]
            and b_ship["with"] == {"additional_data": True})
    return cond, f"set_stock={list(b_stock)} · ship.with={b_ship['with']}"


def t29_import_info_parse():
    hands._http_call = _script(_resp(200, {"result": {"items": [
        {"offer_id": "OZ-I", "product_id": 0, "status": "pending", "errors": []}]}}))
    items = hands.import_info(12345)
    cond = len(items) == 1 and items[0]["offer_id"] == "OZ-I" and items[0]["status"] == "pending"
    return cond, f"items={len(items)} status={items[0]['status']} (async-квитанция, не витрина)"


def t30_warehouse_list():
    hands._http_call = _script(_resp(200, {"result": [{"warehouse_id": 2390811, "name": "FBS"}]}))
    res = hands.warehouse_list()
    ok1 = res["ok"] and res["warehouses"][0]["warehouse_id"] == 2390811
    orig = hands.creds_present
    hands.creds_present = lambda: False
    try:
        res2 = hands.warehouse_list()
    finally:
        hands.creds_present = orig
    cond = ok1 and (not res2["ok"]) and res2["warehouses"] == []
    return cond, f"склад={res['warehouses'][0]['warehouse_id']} · без ключей→ok={res2['ok']}"


def t31_card_offer_id_truncated():
    long_id = "SUP-" + "A" * 60                     # > 50 символов
    r = card.to_item({"offer_id": long_id, "name": "x", "price": 100,
                      "description_category_id": 1, "type_id": 1})
    m, it = r["meta"], r["item"]
    short = card.to_item({"offer_id": "OZ-SHORT", "name": "x", "price": 100,
                          "description_category_id": 1, "type_id": 1})["meta"]
    cond = (m["offer_id_truncated"] and len(it["offer_id"]) == card.MAX_OFFER_ID
            and m["offer_id_full"] == long_id and it["offer_id"] == long_id[:card.MAX_OFFER_ID]
            and not short["offer_id_truncated"] and short["offer_id_full"] is None)
    return cond, (f"обрезан={m['offer_id_truncated']} len={len(it['offer_id'])} "
                  f"full-сохранён={m['offer_id_full'] == long_id} · короткий-флаг={short['offer_id_truncated']}")


TESTS = [
    ("W1  card_explicit_built", t1_card_explicit_built),
    ("W2  card_need_mapping_block", t2_card_need_mapping_block),
    ("W3  card_vat_normalization", t3_card_vat_normalization),
    ("W4  card_attributes_nesting", t4_card_attributes_nesting),
    ("W5  card_dimensions", t5_card_dimensions),
    ("W6  card_name_verbatim", t6_card_name_verbatim),
    ("W7  card_carderror_guards", t7_card_carderror_guards),
    ("W8  card_import_body_filters", t8_card_import_body_filters),
    ("W9  card_old_price_gt_only", t9_card_old_price_gt_only),
    ("W10 card_honest_flags", t10_card_honest_flags),
    ("W11 card_price_rounding", t11_card_price_rounding),
    ("W12 gate_dry_no_send", t12_gate_dry_no_send),
    ("W13 gate_open_sends", t13_gate_open_sends),
    ("W14 gate_failsoft_error", t14_gate_failsoft_error),
    ("W15 request_401_no_retry", t15_request_401_no_retry),
    ("W16 request_transient_then_ok", t16_request_transient_then_ok),
    ("W17 request_transient_exhaust", t17_request_transient_exhaust),
    ("W18 request_network_retry", t18_request_network_retry),
    ("W19 request_non2xx_body", t19_request_non2xx_body),
    ("W20 shelf_v3_parse", t20_shelf_v3_parse),
    ("W21 shelf_v2_errors", t21_shelf_v2_errors),
    ("W22 product_visible_contract", t22_product_visible_contract),
    ("W23 shelf_failsoft_no_creds", t23_shelf_failsoft_no_creds),
    ("W24 extract_stock_variants", t24_extract_stock_variants),
    ("W25 price_index_parse", t25_price_index_parse),
    ("W26 package_label_pdf", t26_package_label_pdf),
    ("W27 package_label_json_err", t27_package_label_json_err),
    ("W28 write_body_shapes", t28_write_body_shapes),
    ("W29 import_info_parse", t29_import_info_parse),
    ("W30 warehouse_list", t30_warehouse_list),
    ("W31 card_offer_id_truncated", t31_card_offer_id_truncated),
]


def main():
    print("🎯 OZON WRITE ПРИЁМКА · сборщик карточки + руки записи/чтения (сухо, 0₽, без сети/реального ключа)")
    passed = 0
    try:
        for name, fn in TESTS:
            try:
                ok, detail = fn()
            except Exception as e:
                ok, detail = False, f"исключение: {type(e).__name__}: {e}"
            print(f"   {_passed(ok)} {name:<30} {detail}")
            passed += 1 if ok else 0
    finally:
        _time.sleep = _ORIG_SLEEP     # вернуть настоящий sleep
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET M1 ПРИЁМКА — МОСТ ЯНДЕКС: руки + карточка + писатель (сухо, 0₽, БЕЗ ключей/сети).

Веха M6 оси ARBITER (Яндекс.Маркет-витрина) — СУХАЯ read-плоскость до записи наружу. Все тесты
оффлайн-детерминированы: сеть к Яндекс.Маркету подменяется monkeypatch (hands._http_call — шов
сети под ретрай-петлёй _request), реальные ключи НЕ нужны и НЕ используются. НИЧЕГО не
отправляется наружу (0₽, dry по умолчанию).

  Y1  no_creds_honest      — ключей нет → creds_present=False, честно, без падения.
  Y2  auth_401_is_keys     — 401 от API → YMarketHTTPError (ключи, не код), без ретрай-шторма.
  Y3  transient_retry      — 429 дважды → ретрай и добивается успеха (устойчивость, не демон).
  Y4  campaigns_resolve    — campaigns() → businessId/campaignId из env и из первого магазина.
  Y5  categories_tree      — categories_tree()/category_parameters() отдают справочники.
  Y6  offer_required       — to_offer собирает offer с обязательными полями (offerId/name/price).
  Y7  offer_honest_gaps    — нет vendor/barcode/pictures → поля НЕ выдумываются, честные флаги.
  Y8  need_mapping_block   — не подтверждённая категория → need_mapping=True, ok=False (не летит).
  Y9  card_quality_parse   — offer_cards_status → contentRating+рекомендации+can_not_fill.
  Y10 4step_dry_payload    — publish_card(dry) печатает точный payload, НЕ шлёт, ok по need_mapping.
  Y11 errors_warnings_read — 200≠успех: ошибки/предупреждения из ответа читаются честно.
  Y12 quality_report_dry   — quality_report(dry=True) честно отказывает (README, 0₽).
  Y13 price_invalid        — цена ≤0 → CardError (не выдумываем цену).
  Y14 parameter_values     — параметры категории: заполняем только известные, missing_required.
  Y15 place_and_check      — place_in_campaign/check_visibility сухие (payload, статус dry).

Приёмка не пишет в реальный канон и не зовёт сеть. Реальный залив — только по отмашке оператора.
"""
import os
import sys
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_hands_v1 as hands     # noqa: E402
import ymarket_card_v1 as card       # noqa: E402
import ymarket_write_v1 as write     # noqa: E402


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


def _resp(status_code, payload=None, text=""):
    """Мини-ответ = реальный hands._Resp (status_code/json()/text) — для подмены hands._http_call."""
    return hands._Resp(status_code, payload, text)


# Мини-monkeypatch: подменяем hands._http_call (шов сети) / creds_present, откат гарантирован.
class _Patch:
    # id-переменные кабинета/магазина: в http-тестах их надо убрать, иначе resolve_ids() возьмёт
    # их из ЖИВОГО .env (src=env) вместо пути через campaigns() (src=campaigns), и Y4 покраснеет.
    _ID_VARS = ("YANDEX_BUSINESS_ID", "YANDEX_CAMPAIGN_ID")

    def __init__(self, http_call=None, creds=None, no_env=False):
        self._http = http_call
        self._creds = creds
        self._no_env = no_env
        self._save = {}

    def _pop_env(self, var):
        self._save.setdefault("env:" + var, os.environ.get(var))
        os.environ.pop(var, None)

    def __enter__(self):
        # Полная нейтрализация среды: тест сам держит мир, gitignored .env не должен влиять.
        # Замораживаем _ENV_TRIED=True → _ensure_env() становится no-op и не дозагрузит живой ключ.
        if self._no_env:
            self._save["_ENV_TRIED"] = hands._ENV_TRIED
            hands._ENV_TRIED = True
            self._pop_env("YANDEX_MARKET_API_KEY")
            for var in self._ID_VARS:
                self._pop_env(var)
        # Сетевым тестам нужен фиктивный ключ: реальный _request зовёт _headers() ДО _http_call,
        # а фейковая сеть его игнорирует. Y1 (без ключа) не патчит сеть — остаётся честным.
        if self._http is not None:
            self._save["key"] = os.environ.get("YANDEX_MARKET_API_KEY")
            os.environ["YANDEX_MARKET_API_KEY"] = "TEST-KEY"
            for var in self._ID_VARS:                 # resolve_ids должен идти через campaigns()
                self._pop_env(var)
            self._save["_http_call"] = hands._http_call
            hands._http_call = self._http
        if self._creds is not None:
            self._save["creds_present"] = hands.creds_present
            hands.creds_present = self._creds
        return self

    def __exit__(self, *exc):
        for name, val in self._save.items():
            if name == "key":
                if val is None:
                    os.environ.pop("YANDEX_MARKET_API_KEY", None)
                else:
                    os.environ["YANDEX_MARKET_API_KEY"] = val
            elif name.startswith("env:"):
                var = name[4:]
                if val is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = val
            elif name == "_ENV_TRIED":
                hands._ENV_TRIED = val
            else:
                setattr(hands, name, val)
        return False


# ── Y1: ключей нет → честно, без падения ──
def t1_no_creds_honest():
    with _Patch(no_env=True):
        got = hands.creds_present()
    return got is False, f"creds_present={got} (без YANDEX_MARKET_API_KEY)"


# ── Y2: 401 → YMarketHTTPError (ключи, не код), без ретрай-шторма ──
def t2_auth_401_is_keys():
    calls = []

    def _http(method, url, headers, body, params, timeout):
        calls.append(url)
        return _resp(401, {"message": "unauthorized"})

    with _Patch(http_call=_http):
        try:
            hands.campaigns()
            return False, "401 не поднял YMarketHTTPError"
        except hands.YMarketHTTPError as e:
            ok = e.status == 401 and len(calls) == 1  # 401 не ретраим
            return ok, f"YMarketHTTPError 401, вызовов={len(calls)}"


# ── Y3: 429 дважды → ретрай и успех (устойчивость) ──
def t3_transient_retry():
    calls = []

    def _http(method, url, headers, body, params, timeout):
        calls.append(url)
        if len(calls) < 3:
            return _resp(429, {"message": "too many"})  # транзиторно → _request ретраит
        return _resp(200, {"campaigns": [{"id": "C1", "business": {"id": "B1"}}]})

    with _Patch(http_call=_http):
        camps = hands.campaigns()
        return len(calls) == 3 and camps[0]["id"] == "C1", f"ретраев={len(calls)-1}, успех"


# ── Y4: campaigns → businessId/campaignId ──
def t4_campaigns_resolve():
    def _http(method, url, headers, body, params, timeout):
        return _resp(200, {"campaigns": [
            {"id": "C42", "placementType": "FBS", "business": {"id": "B7"}}]})
    with _Patch(http_call=_http):
        camps = hands.campaigns()
        bid, cid, src = hands.resolve_ids()
        return (len(camps) == 1 and camps[0]["placementType"] == "FBS"
                and bid == "B7" and cid == "C42" and src == "campaigns"), \
            f"business={bid} campaign={cid} src={src}"


# ── Y5: справочники категорий ──
def t5_categories_tree():
    def _http(method, url, headers, body, params, timeout):
        if url.endswith("/categories/tree"):
            return _resp(200, {"result": {"categories": [{"id": 123, "name": "Упаковка пищевая"}]}})
        if url.endswith("/category/123/parameters"):
            return _resp(200, {"result": {"parameters": [
                {"id": 1, "name": "материал", "required": True}]}})
        raise AssertionError(f"не ждали {url}")
    with _Patch(http_call=_http):
        tree = hands.categories_tree()
        params = hands.category_parameters(123)
        ok = (isinstance(tree, dict) and params and params[0]["required"] is True)
        return ok, f"tree категорий, параметров={len(params)}, required={params[0]['required']}"


# ── Y6: to_offer собирает offer с обязательными полями ──
def t6_offer_required():
    prod = {"sku": "S1", "name": "Пакет фасовочный 24х15", "cost": 99.0}
    r = card.to_offer(prod, slug="pishevaya-upakovka")
    o = r["offer"]
    need = all(k in o for k in ("offerId", "name", "type", "basicPrice"))
    price_ok = o["basicPrice"]["value"] == 99.0 and o["basicPrice"]["currencyId"] == "RUR"
    return need and price_ok, f"offerId={o['offerId']}, price={o['basicPrice']['value']}"


# ── Y7: нет vendor/barcode/pictures → НЕ выдумываем, честные флаги ──
def t7_offer_honest_gaps():
    prod = {"sku": "S2", "name": "Контейнер пищевой", "cost": 50.0}
    r = card.to_offer(prod, slug="pishevaya-upakovka")
    o, m = r["offer"], r["meta"]
    no_fake = ("vendor" not in o and "barcodes" not in o and "pictures" not in o
               and "description" not in o and "weightDimensions" not in o)
    honest = m["missing_pictures"] is True and m["has_vendor"] is False
    return no_fake and honest, f"missing_pictures={m['missing_pictures']} has_vendor={m['has_vendor']}"


# ── Y8: id НЕ ВЫДУМЫВАЕТСЯ; нет id → законная авто-категория (закон обновлён 2026-08-06) ──
def t8_need_mapping_block():
    """ЗАКОН (действующий): свой marketCategoryId не выдумываем. Если ни ручной справочник, ни мост
    по живому дереву не дали id — это ЗАКОННОЕ состояние: карточка уходит со строкой-подсказкой
    `category`, и категорию определяет авто-классификатор Маркета. Раньше это блокировало залив;
    блокировка снята сознательно (см. to_offer docstring), поэтому тест проверяет НЕ блокировку,
    а честность: выдуманного id нет, флаг правдив, вход авто-классификатора на месте.
    """
    # bridge=False — детерминизм: отключаем лексический мост, чтобы проверить именно «молчание» резолва
    prod = {"sku": "S3", "name": "Нечто неведомое зурбаганское", "cost": 10.0}
    r = card.to_offer(prod, slug="pishevaya-upakovka", bridge=False)
    o, m = r["offer"], r["meta"]
    honest = m["need_mapping"] is True and m["category_id"] is None
    no_fake_id = "marketCategoryId" not in o          # выдуманного id НЕТ
    auto_input = o.get("category") == "pishevaya-upakovka"  # вход авто-классификатора на месте
    return honest and no_fake_id and auto_input, \
        f"need_mapping={m['need_mapping']} id={m['category_id']} marketCategoryId в offer={'есть' if not no_fake_id else 'НЕТ (честно)'} category='{o.get('category')}'"


# ── Y9: card_quality парсит contentRating/рекомендации ──
def t9_card_quality_parse():
    statuses = [
        {"offerId": "S1", "contentRating": 80, "averageContentRating": 60,
         "cardStatus": "HAS_CARD_CAN_UPDATE",
         "recommendations": [{"type": "HAS_VIDEO", "remainingRatingPoints": 5},
                             {"type": "PICTURE_COUNT", "remainingRatingPoints": 10}]}
    ]
    cards = card.card_quality(statuses)
    c = cards[0]
    return (c["contentRating"] == 80 and c["averageContentRating"] == 60
            and len(c["recommendations"]) == 2 and "HAS_VIDEO" in c["can_not_fill"]), \
        f"rating={c['contentRating']}, recs={len(c['recommendations'])}, can_not={c['can_not_fill']}"


# ── Y10: publish_card(dry) печатает точный payload и НИЧЕГО не шлёт (сухой гейт) ──
def t10_4step_dry_payload():
    """ЗАКОН YM3 (двойной гейт): в dry наружу не уходит ничего, но payload собран точно.

    Проверяем сам гейт, а не судьбу категории: карточка с резолвнутой категорией проходит все
    4 шага СУХО (status='dry'), реальных вызовов нет. Мост включён — это боевой путь.
    """
    prod = {"sku": "S4", "name": "Курьер-пакет 50х70", "cost": 30.0,
            "vendor": "SOCC", "pictures": ["https://img.example/p.jpg"]}
    res = write.publish_card(prod, slug="upakovka-dlya-marketplejsov", dry=True, commit=False)
    cc = res.get("create_card", res)
    dry_held = res.get("dry") is True                       # гейт закрыт
    nothing_sent = res.get("status") in ("dry", None) or res.get("published") is None
    payload_built = bool(cc.get("payloads", {}).get("step1"))  # точный payload собран
    return dry_held and nothing_sent and payload_built, \
        f"dry={res.get('dry')} status={res.get('status')} payload_step1={'собран' if payload_built else 'НЕТ'}"


# ── Y11: 200≠успех — errors/warnings читаются ──
def t11_errors_warnings_read():
    # _collect_issues: ответ 200 с result.offerMappings[].errors/warnings
    resp = {"result": {"offerMappings": [
        {"offerId": "S1", "errors": [{"message": "нет категории"}],
         "warnings": [{"message": "нет описания"}]}
    ]}}
    errs, warns = write._collect_issues(resp, "offerMappings")
    return len(errs) == 1 and len(warns) == 1, f"errors={len(errs)} warnings={len(warns)}"


# ── Y12: quality_report(dry) честно отказывает ──
def t12_quality_report_dry():
    res = write.quality_report(dry=True)
    return res["ok"] is False and res["dry"] is True, f"ok={res['ok']} dry={res['dry']} note={res.get('note')}"


# ── Y13: цена ≤0 → CardError (не выдумываем) ──
def t13_price_invalid():
    try:
        card.to_offer({"sku": "S5", "name": "X", "cost": 0}, slug="pishevaya-upakovka")
        return False, "цена 0 не вызвала CardError"
    except card.CardError:
        return True, "CardError на цене 0"


# ── Y14: parameter_values заполняет только известные + missing_required ──
def t14_parameter_values():
    params = [
        {"id": 1, "name": "материал", "required": True, "unitId": 100},
        {"id": 2, "name": "объём", "required": True},
        {"id": 3, "name": "цвет", "required": False},
    ]
    prod = {"материал": "полиэтилен"}
    pv = card.parameter_values(prod, params)
    filled = pv["parameterValues"]
    ok = (len(filled) == 1 and filled[0]["parameterId"] == 1
          and filled[0]["value"] == "полиэтилен" and filled[0]["unitId"] == 100
          and pv["missing_required"] == 1)  # объём обязателен, нет → честный счётчик
    return ok, f"заполнено={len(filled)} missing_required={pv['missing_required']}"


# ── Y15: place/check сухие ──
def t15_place_and_check():
    r2 = write.place_in_campaign("S1", dry=True)
    r3 = write.check_visibility("S1", dry=True)
    return r2["dry"] is True and r3["dry"] is True and r3["status"] == "dry", \
        f"place dry={r2['dry']} check dry={r3['dry']} status={r3['status']}"


TESTS = [
    ("Y1  no_creds_honest", t1_no_creds_honest),
    ("Y2  auth_401_is_keys", t2_auth_401_is_keys),
    ("Y3  transient_retry", t3_transient_retry),
    ("Y4  campaigns_resolve", t4_campaigns_resolve),
    ("Y5  categories_tree", t5_categories_tree),
    ("Y6  offer_required", t6_offer_required),
    ("Y7  offer_honest_gaps", t7_offer_honest_gaps),
    ("Y8  need_mapping_block", t8_need_mapping_block),
    ("Y9  card_quality_parse", t9_card_quality_parse),
    ("Y10 4step_dry_payload", t10_4step_dry_payload),
    ("Y11 errors_warnings_read", t11_errors_warnings_read),
    ("Y12 quality_report_dry", t12_quality_report_dry),
    ("Y13 price_invalid", t13_price_invalid),
    ("Y14 parameter_values", t14_parameter_values),
    ("Y15 place_and_check", t15_place_and_check),
]


def main():
    print("🎯 YMARKET M1 ПРИЁМКА · МОСТ ЯНДЕКС (сухо, 0₽, без ключей/сети)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<24} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

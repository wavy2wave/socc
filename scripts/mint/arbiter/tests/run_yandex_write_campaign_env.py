#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET WRITE · РЕГРЕССИЯ campaignId-резолва (0₽, без сети) — ловит боевой баг первого RUBICON-fire.

ЖИВОЙ ИНЦИДЕНТ (2026-08-21, первый реальный залив 5 карточек): шаги 1+2 (offer-mappings +
offer-cards) прошли — карточки легли в каталог 184481130. Шаг 3 (place_in_campaign) упал 5/5:
  POST https://api.partner.market.yandex.ru/campaigns/None/offers/update
  → 400 BAD_REQUEST 'Incorrect campaignId: None'.
Корень: place_in_campaign/check_visibility (в отличие от create_card) НЕ брали YANDEX_CAMPAIGN_ID
из env, а publish_card пробрасывал сырой campaign_id=None насквозь. env ИМЕЛ верный 148619267 —
шаг 3/4 его просто не читали. Оператор: «ни один товар не должен быть с ошибкой». Этот баг = 5/5
ошибок. Тесты ниже фиксируют починку и стоят на страже, чтобы он не воскрес.

  W1 place_env_fallback     — place_in_campaign(campaign_id=None) РЕАЛЬНО берёт cid из env (не None).
  W2 visibility_env_fallback— check_visibility(campaign_id=None) РЕАЛЬНО берёт cid из env (не None).
  W3 place_guard_no_env     — env пуст → ЧЕСТНЫЙ отказ, НИ ОДНОГО POST на /campaigns/None/ (guard).
  W4 visibility_guard_no_env— env пуст → честный отказ, сеть НЕ тронута.
  W5 explicit_cid_wins      — явный campaign_id бьёт env (обратная совместимость старых вызовов).
  W6 dry_untouched          — dry=True: ни env, ни сеть не нужны (двойной гейт цел).
  W7 publish_card_e2e       — ВЕСЬ 4-шаг с campaign_id=None+env: шаг 3 получает env cid, НЕ None
                              (точная репродукция боевого падения — теперь зелёная).

Детерминизм: .env НЕ грузим (hands._ENV_TRIED=True), YANDEX_CAMPAIGN_ID/BUSINESS_ID задаём руками,
руки hands.* стабятся целиком и ловят, с каким cid их позвали. Реальные ключи НЕ нужны, 0₽.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_hands_v1 as hands       # noqa: E402
import ymarket_write_v1 as write       # noqa: E402


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


def _isolate_env(campaign_value, business_value="184481130"):
    """Полностью детерминировать env: .env НЕ грузим, значения задаём/снимаем руками."""
    hands._ENV_TRIED = True   # блокируем загрузку gitignored .env — тест владеет окружением
    if campaign_value is None:
        os.environ.pop("YANDEX_CAMPAIGN_ID", None)
    else:
        os.environ["YANDEX_CAMPAIGN_ID"] = campaign_value
    if business_value is None:
        os.environ.pop("YANDEX_BUSINESS_ID", None)
    else:
        os.environ["YANDEX_BUSINESS_ID"] = business_value


def _clean_offers_resp(offer_id="X", key="offers"):
    """Ответ руки без ошибок (200 «без errors») — чтобы _collect_issues нашёл 0 проблем."""
    return {"status": "OK", "result": {key: [{"offerId": offer_id, "errors": [], "warnings": []}]}}


# ── W1: place_in_campaign(campaign_id=None) РЕАЛЬНО резолвит env ──
def w1_place_env_fallback():
    _isolate_env("148619267")
    captured = {}
    save = hands.update_campaign_offers
    try:
        hands.update_campaign_offers = lambda cid, offers: (captured.__setitem__("cid", cid),
                                                            _clean_offers_resp("SKU1"))[1]
        r = write.place_in_campaign("SKU1", available=False, dry=False, commit=True, campaign_id=None)
        ok = captured.get("cid") == "148619267" and r.get("ok") and not r.get("errors")
        return ok, f"captured_cid={captured.get('cid')!r}, ok={r.get('ok')}, errors={r.get('errors')}"
    finally:
        hands.update_campaign_offers = save


# ── W2: check_visibility(campaign_id=None) РЕАЛЬНО резолвит env ──
def w2_visibility_env_fallback():
    _isolate_env("148619267")
    captured = {}
    save = hands.campaign_offers
    try:
        hands.campaign_offers = lambda cid, offer_ids=None: (captured.__setitem__("cid", cid),
                                                             [{"offerId": "SKU1", "status": "PUBLISHED"}])[1]
        r = write.check_visibility("SKU1", dry=False, commit=True, campaign_id=None)
        ok = captured.get("cid") == "148619267" and r.get("status") == "PUBLISHED"
        return ok, f"captured_cid={captured.get('cid')!r}, status={r.get('status')}"
    finally:
        hands.campaign_offers = save


# ── W3: env пуст → честный отказ, НИ ОДНОГО POST на /campaigns/None/ ──
def w3_place_guard_no_env():
    _isolate_env(None)
    called = {"n": 0}
    save = hands.update_campaign_offers
    try:
        hands.update_campaign_offers = lambda cid, offers: (called.__setitem__("n", called["n"] + 1),
                                                            _clean_offers_resp("SKU1"))[1]
        r = write.place_in_campaign("SKU1", available=False, dry=False, commit=True, campaign_id=None)
        # НЕ отправили ничего наружу (guard сработал ДО сети) и честно вернули ошибку про campaignId
        ok = (called["n"] == 0 and not r.get("ok")
              and any("campaignId" in e for e in (r.get("errors") or [])))
        return ok, f"network_calls={called['n']}, ok={r.get('ok')}, errors={r.get('errors')}"
    finally:
        hands.update_campaign_offers = save


# ── W4: check_visibility при пустом env → честный отказ, сеть не тронута ──
def w4_visibility_guard_no_env():
    _isolate_env(None)
    called = {"n": 0}
    save = hands.campaign_offers
    try:
        hands.campaign_offers = lambda cid, offer_ids=None: (called.__setitem__("n", called["n"] + 1), [])[1]
        r = write.check_visibility("SKU1", dry=False, commit=True, campaign_id=None)
        ok = called["n"] == 0 and not r.get("ok") and "campaignId" in (r.get("error") or "")
        return ok, f"network_calls={called['n']}, ok={r.get('ok')}, error={r.get('error')}"
    finally:
        hands.campaign_offers = save


# ── W5: явный campaign_id бьёт env (обратная совместимость) ──
def w5_explicit_cid_wins():
    _isolate_env("ENV-1")
    captured = {}
    save = hands.update_campaign_offers
    try:
        hands.update_campaign_offers = lambda cid, offers: (captured.__setitem__("cid", cid),
                                                            _clean_offers_resp("SKU1"))[1]
        r = write.place_in_campaign("SKU1", available=False, dry=False, commit=True,
                                    campaign_id="EXPLICIT-9")
        ok = captured.get("cid") == "EXPLICIT-9" and r.get("ok")
        return ok, f"captured_cid={captured.get('cid')!r} (env был ENV-1)"
    finally:
        hands.update_campaign_offers = save


# ── W6: dry=True — ни env, ни сеть не нужны (двойной гейт цел) ──
def w6_dry_untouched():
    _isolate_env(None)
    called = {"n": 0}
    save = hands.update_campaign_offers
    try:
        hands.update_campaign_offers = lambda cid, offers: (called.__setitem__("n", called["n"] + 1),
                                                            _clean_offers_resp("SKU1"))[1]
        r = write.place_in_campaign("SKU1", available=False, dry=True, commit=False, campaign_id=None)
        # dry: сеть не тронута, ok=True (готовый payload напечатан), никакого отказа-guard
        ok = called["n"] == 0 and r.get("ok") and r.get("dry")
        return ok, f"network_calls={called['n']}, ok={r.get('ok')}, dry={r.get('dry')}"
    finally:
        hands.update_campaign_offers = save


# ── W7: ВЕСЬ 4-шаг с campaign_id=None+env — точная репродукция боевого падения ──
def w7_publish_card_e2e():
    _isolate_env("148619267")
    captured = {}
    save_map = hands.update_offer_mappings
    save_card = hands.update_offer_cards
    save_place = hands.update_campaign_offers
    save_vis = hands.campaign_offers
    try:
        # шаги 1+2: чисто (как в бою — они и тогда прошли)
        hands.update_offer_mappings = lambda bid, offers: _clean_offers_resp(
            (offers[0]["offer"].get("offerId") or "OID"), "offerMappings")
        hands.update_offer_cards = lambda bid, content: _clean_offers_resp(
            content[0].get("offerId", "OID"), "offerCards")
        # шаг 3: ловим, с каким campaignId нас позвали (в бою тут было None)
        hands.update_campaign_offers = lambda cid, offers: (captured.__setitem__("place_cid", cid),
                                                            _clean_offers_resp(offers[0]["offerId"]))[1]
        # шаг 4: витрина
        hands.campaign_offers = lambda cid, offer_ids=None: (captured.__setitem__("vis_cid", cid),
                                                             [{"offerId": (offer_ids or ["OID"])[0],
                                                               "status": "PUBLISHED"}])[1]
        prod = {"sku": "REGR-CAMP-1", "name": "Короб картонный регресс-тест 60×40×40",
                "cost": 120, "vendor": "SOCC", "pictures": ["https://img.example/box.jpg"]}
        r = write.publish_card(prod, slug="kartonnye-koroba", dry=False, commit=True,
                               available=False, campaign_id=None)
        # Гвоздь: шаг 3 получил env cid, НЕ None (иначе — тот самый /campaigns/None/)
        ok = (captured.get("place_cid") == "148619267"
              and captured.get("vis_cid") == "148619267"
              and r.get("ok"))
        return ok, (f"place_cid={captured.get('place_cid')!r}, vis_cid={captured.get('vis_cid')!r}, "
                    f"ok={r.get('ok')}, published={r.get('published')}, step={r.get('step')}")
    finally:
        hands.update_offer_mappings = save_map
        hands.update_offer_cards = save_card
        hands.update_campaign_offers = save_place
        hands.campaign_offers = save_vis


TESTS = [
    ("W1 place_env_fallback", w1_place_env_fallback),
    ("W2 visibility_env_fallback", w2_visibility_env_fallback),
    ("W3 place_guard_no_env", w3_place_guard_no_env),
    ("W4 visibility_guard_no_env", w4_visibility_guard_no_env),
    ("W5 explicit_cid_wins", w5_explicit_cid_wins),
    ("W6 dry_untouched", w6_dry_untouched),
    ("W7 publish_card_e2e", w7_publish_card_e2e),
]


def main():
    passed = 0
    for name, fn in TESTS:
        try:
            ok, msg = fn()
            print(f"{_passed(ok)}  {name}: {msg}")
            if ok:
                passed += 1
        except Exception as e:
            print(f"❌ FAIL  {name}: EXCEPTION {type(e).__name__}: {e}")
    print("─" * 68)
    print(f"ИТОГ WRITE·campaignId-регресс:  {passed}/{len(TESTS)} зелёные")
    print("═" * 68)
    return passed == len(TESTS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)

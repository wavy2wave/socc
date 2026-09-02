#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET WRITE V1 — писатель карточек Яндекс.Маркета (клон ozon_write-логики, dry по умолчанию).

Веха M6 оси ARBITER: «Яндекс.Маркет-витрина». ЦЕЛЬ ОПЕРАТОРА: «создавать карточки на Маркете
быстро без ошибок, заполняя всевозможные данные, чтобы вылететь в ТОП. Индекс важен. И сама
карточка важна.» Здесь — сердце этого: карточка проходит 4 шага API, читается index, закрываются
рекомендации (top_fill). РЕАЛЬНЫЙ залив — ТОЛЬКО по отмашке (dry=True по умолчанию).

4 шага публикации (карта API, yandex-market-api-map):
  1) update_offer_mappings  — товар в каталог кабинета (businessId).
  2) update_offer_cards     — категорийные характеристики (parameterValues).
  3) update_campaign_offers — размещение в магазине (available/quantum/vat).
  4) campaign_offers        — проверка витрины (статус PUBLISHED).
Индекс/ТОП: offer_cards_status → contentRating + recommendations; top_fill() честно раскладывает
их на closable (поднимаемые данными карточки) vs can_not_fill (видео/бренд — API не закрыть).

ЗАКОНЫ SOCC: stdlib, fail-soft, без демона (bounded tick), ключи из env, dry по умолчанию.
200 ≠ успех: ВСЕГДА читаем result.offerMappings[].errors/warnings (и offerCards[]), не доверяем
коду. `can_not_fill` рекомендации (видео и т.п.) честно логируются, не выдумываются.

ЗАКОН КАТЕГОРИИ (переписан 2026-08-06 по живому опыту, отменяет прежний запрет):
  ВЫДУМАННАЯ категория — ошибка. ОТСУТСТВИЕ категории — НЕ ошибка и НЕ повод не лить.
  Доказано в кабинете Atlas Edge: TEST-AUTOCAT-1 без marketCategoryId и без parameterValues
  залился и получил категорию от Маркета сам (76346336 «Упаковочные плёнки»); TEST-BARECAT-1
  с ГОЛОЙ marketCategoryId (без parameterValues) принят и не встал в ERRORS.
  Поэтому need_mapping=True больше НЕ блокирует залив — это лишь честный флаг «своего id нет».
  Следствие для шага 2: при category_id=None или пустых parameterValues шаг ПРОПУСКАЕТСЯ —
  слать categoryId:None в update_offer_cards нельзя, а пустые параметры бессмысленны.
"""
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_hands_v1 as hands        # noqa: E402
import ymarket_card_v1 as card          # noqa: E402

REPORTS = Path(__file__).resolve().parent.parent.parent.parent / "MEMORY_WAVE/reports/mint/arbiter"

# Статусы, при которых товар «на витрине» / «нужен контент» / «ошибка» (для честного разбора).
PUBLISHED = "PUBLISHED"
NEED_CONTENT = ("NO_CARD_NEED_CONTENT", "HAS_CARD_CAN_UPDATE_PROCESSING")
ERROR_STATUSES = ("NO_CARD_ERRORS", "HAS_CARD_CAN_UPDATE_ERRORS")
# Карточка ЖИВА и редактируема / в обработке (для сверки здоровья, classify_card_health).
READY_STATUSES = ("PUBLISHED", "HAS_CARD_CAN_UPDATE", "HAS_CARD_CAN_NOT_UPDATE")
PROCESSING_STATUSES = ("NO_CARD_PROCESSING", "HAS_CARD_CAN_UPDATE_PROCESSING")
# «Магазин отключён по результатам проверки» — вердикт СЛУЖБЫ КАЧЕСТВА ВИТРИНЫ, снимается ТОЛЬКО в
# кабинете (живой урок 2026-08-25). Это НЕ вина карточки → держим ОТДЕЛЬНО от наших ошибок.
STORE_DISABLED_MARKERS = ("магазин отключ",)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _result_offers(resp, key="offerMappings"):
    """Достать массив результатов из ответа API (fail-soft: не то → [])."""
    if not isinstance(resp, dict):
        return []
    return resp.get("result", {}).get(key, []) if isinstance(resp.get("result"), dict) else []


def _collect_issues(resp, key="offerMappings"):
    """Собрать все errors/warnings из ответа (200≠успех — это и есть «без ошибок»)."""
    errors, warnings = [], []
    for row in _result_offers(resp, key):
        if not isinstance(row, dict):
            continue
        for e in (row.get("errors") or []):
            if isinstance(e, dict):
                errors.append(e.get("message") or str(e))
        for w in (row.get("warnings") or []):
            if isinstance(w, dict):
                warnings.append(w.get("message") or str(w))
    return errors, warnings


def _status_of(resp, offer_id):
    """Статус карточки offer_id из ответа (fail-soft: '' если нет)."""
    for row in _result_offers(resp, "offerCards") or _result_offers(resp, "offers"):
        if isinstance(row, dict) and (row.get("offerId") or row.get("offer_id")) == offer_id:
            return row.get("status") or row.get("cardStatus") or ""
    return ""


def _err_text(e):
    """Нормализовать элемент errors[] в СТРОКУ. Живьём видели ОБА формата: dict-с-message И голую
    строку — парсер «по одному формату» молча потерял бы половину вердиктов (200≠успех врёт тихо).

    ГАРАНТИЯ: всегда возвращаем str. Если message/text сами оказались НЕ строкой (вложенный dict,
    число) — не отдаём их сырыми (иначе .lower() ниже по потоку падает AttributeError и роняет
    всю сверку), а честно сериализуем в JSON. Так «кривой вердикт» превращается в видимый текст,
    а не в тихий обвал."""
    if isinstance(e, str):
        return e.strip()
    if isinstance(e, dict):
        for k in ("message", "text", "value", "comment", "description"):
            val = e.get(k)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return json.dumps(e, ensure_ascii=False)
    return str(e)


def _norm_text(text):
    """Нормализация вердикта для сравнения: не-строку → str, NBSP и любые пробелы схлопнуть, lower.
    Живьём Яндекс сыплет NBSP (\\xa0) внутри фраз (доказано: own-error в R4). Без этого
    «Магазин\\xa0отключён» не совпал бы с маркером — и мы приняли бы блок ВИТРИНЫ за СВОЮ ошибку
    (бессмысленный ре-билд чистой карточки). str.split() без аргумента бьёт по Unicode-пробелам,
    включая NBSP, поэтому " ".join(split()) нормализует без regex."""
    s = text if isinstance(text, str) else ("" if text is None else str(text))
    return " ".join(s.split()).lower()


def _is_store_verdict(text):
    """True, если строка — операторский «Магазин отключён…» (вина витрины, НЕ карточки).
    Сверяем по НОРМАЛИЗОВАННОМУ тексту (nbsp/регистр/лишние пробелы не должны прятать блок).
    Расширять на «вставленное слово» — ТОЛЬКО по реально увиденному образцу (форм не выдумываем)."""
    t = _norm_text(text)
    return any(m in t for m in STORE_DISABLED_MARKERS)


# ── 4 шага публикации (dry по умолчанию) ──

def _dry(dry, commit, label, call, payload):
    """Двойной гейт безопасности: реальный call() уходит наружу ТОЛЬКО когда `not dry AND commit`.

    dry=True ИЛИ commit=False → печатает точный payload (что ПОЛЕТЕЛО БЫ) и возвращает fake-ответ
    status='dry'. Это и есть «сухая плоскость до записи наружу»: тренируемся на точном JSON, ничего
    не отправляя. Так контракт «ничего без --commit» держится НА ГРАНИЦЕ ФУНКЦИИ, а не только в CLI.

    Fail-soft (закон вечной машины): если реальный вызов упал (ключи/сеть) — НЕ роняем писателя,
    несём ошибку в теле {status:'error', _error:...}, вызывающий свернётся честно (ok=False).
    """
    if dry or not commit:
        tag = "dry" if dry else "no-commit"
        print(f"  · {label}: ({tag}) точный payload, НЕ отправлен:")
        print(f"      {json.dumps(payload, ensure_ascii=False)[:500]}")
        return {"status": "dry", "result": {key: [] for key in ("offerMappings", "offerCards", "offers")}}
    try:
        return call()
    except (hands.YMarketHTTPError, RuntimeError) as e:
        return {"status": "error", "_error": str(e),
                "result": {key: [] for key in ("offerMappings", "offerCards", "offers")}}


def _merge_pictures(existing, photo_urls, cap=30):
    """Слить фото товара с НАШИМИ выкованными URL, дедуп с сохранением порядка, потолок cap.

    Кладём ТОЛЬКО непустые строки-URL. Наши кадры идут ПЕРВЫМИ (главное фото = наш стиль),
    затем прежние. photo_urls приходит из photo_publish.pictures_from_forge (уже прошёл
    провенанс-гейт «свои пиксели»); тут мы фильтры не дублируем, только сшиваем.
    """
    seen, out = set(), []
    for src in ((photo_urls or []), (existing or [])):
        for u in src:
            if isinstance(u, str) and u.strip() and u not in seen:
                seen.add(u)
                out.append(u)
            if len(out) >= cap:
                return out
    return out


def create_card(prod, slug=None, dry=True, commit=False, cats=None, business_id=None,
                campaign_id=None, category_params=None, photo_urls=None, unique_name=None,
                house_brand=None):
    """Шаг 1+2: собрать карточку и (если не dry) отправить offer-mappings + offer-cards.

    Возвращает {'ok', 'need_mapping', 'errors', 'warnings', 'dry', 'offer_id', 'mapping', ...}.
    КАТЕГОРИЯ (закон 2026-08-06): need_mapping=True НЕ отказ — карточка уходит БЕЗ marketCategoryId,
    Маркет назначает категорию сам (доказано живьём). Выдуманный id по-прежнему запрещён.
    commit=False → только dry-подготовка (не шлём). price/поле проверены.
    photo_urls — ПУБЛИЧНЫЕ https-ссылки наших выкованных кадров (из photo_publish); если заданы,
    встают ПЕРВЫМИ в pictures[] (наш стиль = главное фото). Только строки-URL, дедуп, потолок 30.
    Локальные пути/base64 сюда не кладём — их отсекает провенанс-гейт публикатора.
    unique_name — анти-склейка рычаг НАИМЕНОВАНИЯ (см. card.to_offer). None → уважаем флаг в prod
    (prod['unique_name']); True/False — явно включить/выключить. ВЫКЛ по умолчанию → имя дословно.
    """
    if photo_urls and isinstance(prod, dict):
        prod = {**prod, "pictures": _merge_pictures(prod.get("pictures"), photo_urls)}
    try:
        built = card.to_offer(prod, slug=slug, cats=cats, unique_name=unique_name,
                              house_brand=house_brand)
    except card.CardError as e:
        return {"ok": False, "error": f"CardError: {e}", "dry": dry, "commit": commit}
    offer, meta = built["offer"], built["meta"]
    oid = meta["offerId"]

    if meta.get("need_mapping"):
        # НЕ отказ: честно говорим, что льём в авто-категорию Маркета.
        print(f"  ℹ️  {oid}: своего marketCategoryId нет — АВТО-категория Маркета")
    if meta.get("missing_pictures"):
        # карточка без изображений = заниженный index; не «молча»: честно предупредим
        print(f"  ⚠️  {oid}: нет изображений (карточка уйдёт с низким index)")

    bid = business_id or hands.business_id_env()
    cid = campaign_id or hands.campaign_id_env()
    # ID-резолв: реально шлём (not dry and commit), но businessId неизвестен → узнаём из campaigns()
    # (в dry сеть НЕ трогаем). Всё ещё None → честный отказ, НЕ POST на /businesses/None/...
    if (not dry) and commit and not bid:
        try:
            bid2, cid2, _src = hands.resolve_ids()
            bid = bid or bid2
            cid = cid or cid2
        except (hands.YMarketHTTPError, RuntimeError) as e:
            return {"ok": False, "error": f"не удалось узнать businessId ({e}); задай YANDEX_BUSINESS_ID",
                    "offer_id": oid, "dry": dry, "commit": commit}
    if (not dry) and commit and not bid:
        return {"ok": False, "error": "businessId неизвестен (нет YANDEX_BUSINESS_ID и campaigns() пуст) — "
                "реальный залив невозможен, не шлём на /businesses/None/", "offer_id": oid,
                "dry": dry, "commit": commit}

    # Шаг 1: товар в каталог кабинета
    payload1 = {"offerMappings": [{"offer": offer}]}
    resp1 = _dry(dry, commit, "step1 offer-mappings",
                 lambda: hands.update_offer_mappings(bid, [{"offer": offer}]), payload1)
    errors1, warns1 = _collect_issues(resp1, "offerMappings")
    if resp1.get("_error"):
        errors1.append(f"transport: {resp1['_error']}")
    # F7: шаг 1 ГЕЙТИТ шаг 2 — при ошибках offer-mappings (в т.ч. 200-с-ошибками) НЕ шлём offer-cards.
    if errors1:
        return {"ok": False, "offer_id": oid, "slug": meta.get("slug"),
                "need_mapping": meta.get("need_mapping"), "missing_pictures": meta.get("missing_pictures"),
                "errors": errors1, "warnings": warns1, "dry": dry, "commit": commit,
                "step": "step1_offer_mappings", "category_id": meta.get("category_id"),
                "payloads": {"step1": payload1}}

    # Шаг 2: категорийные характеристики (профиль категории даёт точные unitId/valueId, если подтверждён)
    # ЗАКОН ШАГА 2: он ИМЕЕТ СМЫСЛ только когда известны И categoryId, И непустые parameterValues.
    # categoryId=None API не примет, а пустые параметры — пустой запрос. Тогда шаг ПРОПУСКАЕМ:
    # карточка уже в каталоге после шага 1, категорию Маркет назначит сам (закон авто-категории).
    profile = card.load_profile(meta.get("slug"), cats)
    pv = card.parameter_values(prod, category_params, profile=profile)
    # ВРАТАРЬ: сверяем с живыми ограничениями категории ДО отправки (иначе испортим живую карточку).
    pv_clean, pv_dropped = card.validate_against_live(pv["parameterValues"], category_params)
    if pv_dropped:
        for d in pv_dropped:
            print(f"  ⚠️  {oid}: «{d.get('name')}» = {d.get('value')} НЕ отправлено — {d.get('why')}")
    pv["parameterValues"] = pv_clean
    pv["dropped"] = pv_dropped

    step2_skipped = None
    if meta.get("category_id") is None:
        step2_skipped = "нет categoryId — авто-категория Маркета"
    elif not pv_clean:
        step2_skipped = "нет параметров для отправки"
    if step2_skipped:
        errors2, warns2, payload2 = [], [], None
        print(f"  ↷ {oid}: шаг 2 (offer-cards) пропущен — {step2_skipped}")
    else:
        offers_content = [{"offerId": oid,
                           "categoryId": meta.get("category_id"),
                           "parameterValues": pv["parameterValues"]}]
        payload2 = {"offersContent": offers_content}
        resp2 = _dry(dry, commit, "step2 offer-cards",
                     lambda: hands.update_offer_cards(bid, offers_content), payload2)
        errors2, warns2 = _collect_issues(resp2, "offerCards")
        if resp2.get("_error"):
            errors2.append(f"transport: {resp2['_error']}")

    errors = errors1 + errors2
    warnings = warns1 + warns2
    # ok = «залив прошёл без ошибок». Отсутствие своего id категории — НЕ ошибка (закон авто-категории).
    ok = not errors
    return {
        "ok": ok,
        "offer_id": oid,
        "slug": meta.get("slug"),
        "need_mapping": meta.get("need_mapping"),
        "category_source": meta.get("category_source"),
        "category_leaf": meta.get("category_leaf"),
        "step2_skipped": step2_skipped,
        "missing_pictures": meta.get("missing_pictures"),
        # tri-state: None = «параметры категории не грузили» (не путать с «0 пропущено»)
        "missing_required_params": pv["missing_required"],
        "params_known": pv["missing_required"] is not None,
        "errors": errors,
        "warnings": warnings,
        "dry": dry,
        "commit": commit,
        "category_id": meta.get("category_id"),
        "payloads": {"step1": payload1, "step2": payload2},
    }


def place_in_campaign(offer_id, available=True, min_q=1, step_q=1, vat=None, dry=True,
                      campaign_id=None, commit=False):
    """Шаг 3: разместить товар в магазине (updateCampaignOffers) — доступность/кванты/НДС.

    vat — СТРОКА-энум API (VAT_20/VAT_10/VAT_0/NO_VAT), НЕ число: `vat:0` API отклоняет.

    ЖИВОЙ УРОК (2026-08-05, кабинет Atlas Edge): УСН/без-НДС кабинет (settings.taxation.vat=NO_VAT)
    отклоняет ЛЮБОЕ значение vat в offers/update → 400 'Illegal input at offers[0].vat' (в том числе
    сам NO_VAT). Поэтому дефолт None = не передавать поле; НДС берётся из настроек магазина.
    Оператор на ОСНО передаёт vat явно.
    """
    # ID-резолв (симметрично create_card): None → берём YANDEX_CAMPAIGN_ID из env. НЕ авто-resolve_ids()
    # для кампании — там первый попавшийся магазин (мог быть чужой/забаненный); env = канон витрины.
    campaign_id = campaign_id or hands.campaign_id_env()
    off = {"offerId": offer_id, "available": available,
           "quantum": {"minQuantity": min_q, "stepQuantity": step_q}}
    if vat:
        off["vat"] = vat
    payload = {"offers": [off]}
    # Честный гейт: реально шлём (not dry and commit), но campaignId неизвестен → НЕ POST на /campaigns/None/
    if (not dry) and commit and not campaign_id:
        return {"ok": False, "offer_id": offer_id, "dry": dry, "commit": commit, "payload": payload,
                "errors": ["campaignId неизвестен (нет YANDEX_CAMPAIGN_ID) — не шлём на "
                           "/campaigns/None/offers/update; задай YANDEX_CAMPAIGN_ID или --campaign-id"],
                "warnings": []}
    resp = _dry(dry, commit, "step3 campaign-offers",
                lambda: hands.update_campaign_offers(campaign_id, payload["offers"]), payload)
    errors, warnings = _collect_issues(resp, "offers")
    if resp.get("_error"):
        errors.append(f"transport: {resp['_error']}")
    return {"ok": (dry or not errors), "offer_id": offer_id, "errors": errors,
            "warnings": warnings, "dry": dry, "commit": commit, "payload": payload}


def check_visibility(offer_id, dry=True, campaign_id=None, commit=False):
    """Шаг 4: проверить витрину — вернуть статус карточки (PUBLISHED?) и весь статус.

    READ, 0₽, но всё равно под двойным гейтом (not dry AND commit): «ничего наружу без --commit».
    Fail-soft: сеть/ключи упали → {ok:False, error}, без traceback.
    """
    if dry or not commit:
        print(f"  · step4: (dry) проверил бы витрину для {offer_id}")
        return {"ok": True, "offer_id": offer_id, "status": "dry", "dry": True, "placements": []}
    campaign_id = campaign_id or hands.campaign_id_env()
    if not campaign_id:
        return {"ok": False, "offer_id": offer_id, "status": "", "dry": False, "placements": [],
                "error": "campaignId неизвестен (нет YANDEX_CAMPAIGN_ID) — витрину проверить не на чём"}
    try:
        resp = hands.campaign_offers(campaign_id, offer_ids=[offer_id])
    except (hands.YMarketHTTPError, RuntimeError) as e:
        return {"ok": False, "offer_id": offer_id, "status": "", "error": str(e),
                "placements": [], "dry": False}
    placements = resp if isinstance(resp, list) else []
    status = ""
    for p in placements:
        if isinstance(p, dict) and (p.get("offerId") or p.get("offer_id")) == offer_id:
            status = p.get("status") or p.get("placementStatus") or ""
    return {"ok": status == PUBLISHED, "offer_id": offer_id, "status": status,
            "placements": placements, "dry": False}


def publish_card(prod, slug=None, dry=True, commit=False, cats=None, business_id=None,
                 campaign_id=None, category_params=None, available=True, min_q=1, step_q=1,
                 vat=None, photo_urls=None):
    """Полный 4-шаг: create_card → place → check. Возвращает единый сводный dict.

    ВАЖНО: если любой шаг дал ошибки → ok=False и дальше НЕ идём (не писать вслепую).
    need_mapping (нет своего id категории) НЕ останавливает публикацию — Маркет назначит категорию
    сам (закон авто-категории 2026-08-06); флаг лишь попадает в сводку.
    В реальном режиме (dry=False, commit=True) шаги идут СТРОГО по очереди, каждый только при ok.
    vat — строка-энум API; дефолт None = не слать (УСН-кабинет отклоняет vat; см. place_in_campaign).
    photo_urls — публичные ссылки наших выкованных кадров (см. create_card); проброс насквозь.
    """
    r1 = create_card(prod, slug=slug, dry=dry, commit=commit, cats=cats,
                     business_id=business_id, campaign_id=campaign_id,
                     category_params=category_params, photo_urls=photo_urls)
    if not r1.get("ok"):
        r1["step"] = "create_card"
        r1["published"] = False
        return r1
    oid = r1["offer_id"]
    r2 = place_in_campaign(oid, available=available, min_q=min_q, step_q=step_q, vat=vat,
                           dry=dry, campaign_id=campaign_id, commit=commit)
    if not r2.get("ok"):
        r2["step"] = "place_in_campaign"
        r2["published"] = False
        return r2
    r3 = check_visibility(oid, dry=dry, campaign_id=campaign_id, commit=commit)
    return {
        "ok": r1.get("ok") and r2.get("ok"),
        "offer_id": oid,
        "slug": slug,
        "step": "publish_card",
        "dry": dry,
        "published": r3.get("status") == PUBLISHED if not dry else None,
        "status": r3.get("status"),
        "create_card": r1,
        "place_in_campaign": r2,
        "check_visibility": r3,
    }


def quality_report(offer_ids=None, business_id=None, dry=True, limit=50, commit=False):
    """Индекс: contentRating карточек + рекомендации + can_not_fill. READ, 0₽.

    Это и есть «индекс важен» — замер заполненности, из которого растёт ТОП. Двойной гейт
    (not dry AND commit): даже READ не уходит наружу без --commit («ничего наружу без отмашки»).
    Fail-soft: сеть/ключи/пустой businessId → {ok:False, error}, без traceback.
    """
    if dry or not commit:
        tag = "dry" if dry else "no-commit"
        return {"ok": False, "dry": dry, "commit": commit,
                "note": f"READ индекса не выполнен ({tag}): нужен реальный режим (dry=False) и --commit"}
    bid = business_id or hands.business_id_env()
    if not bid:
        # businessId не задан — узнаём из campaigns() (0₽ read), иначе честный отказ (не /businesses/None/)
        try:
            bid, _cid, _src = hands.resolve_ids()
        except (hands.YMarketHTTPError, RuntimeError) as e:
            return {"ok": False, "dry": False, "error": f"не удалось узнать businessId ({e})"}
    if not bid:
        return {"ok": False, "dry": False, "error": "businessId неизвестен — READ индекса невозможен"}
    try:
        statuses = hands.offer_cards_status(bid, offer_ids=offer_ids, limit=limit)
    except (hands.YMarketHTTPError, RuntimeError) as e:
        return {"ok": False, "dry": False, "error": str(e)}
    cards = card.card_quality(statuses, offer_id=None)
    return {"ok": True, "dry": False, "cards": cards, "count": len(cards),
            "avg_content_rating": _avg_rating(cards)}


def _avg_rating(cards):
    vals = [c.get("contentRating") for c in cards if isinstance(c.get("contentRating"), (int, float))]
    return round(sum(vals) / len(vals), 1) if vals else None


def top_fill(offer_ids=None, business_id=None, dry=True, limit=50, commit=False):
    """Диагностика ТОП (bounded, не демон): читать рекомендации index → честно разложить.

    ЧЕСТНОСТЬ (закон): реального «закрытия» рекомендаций здесь НЕ делаем — закрыть = повторный
    create_card с недостающими данными (фото/описание/vendorCode), которых у диагностики нет.
    Поэтому возвращаем ПЛАН, а не выдуманный счётчик «закрыто N»:
      • closable      — рекомендации, которые поднимет данными карточки (CLOSABLE_RECS: фото/описание/карточка).
      • can_not_fill  — которые API закрыть не может (UNFILLABLE_RECS: видео/узнаваемый бренд) — честно.
      • unknown       — незнакомый тип рекомендации: НЕ обещаем закрыть.
    READ, 0₽ (тот же двойной гейт, что и quality_report).
    """
    rep = quality_report(offer_ids=offer_ids, business_id=business_id, dry=dry, limit=limit, commit=commit)
    if not rep.get("ok"):
        return {"ok": False, "dry": dry, "note": rep.get("note") or rep.get("error") or "нет данных"}
    cards = rep.get("cards", [])
    closable, can_not_fill = [], []
    for c in cards:
        oid = c.get("offerId")
        for r in c.get("recommendations", []):
            t = r.get("type")
            if not t:
                continue
            row = {"offerId": oid, "type": t, "remainingRatingPoints": r.get("remainingRatingPoints")}
            if t in card.CLOSABLE_RECS:
                closable.append(row)
            elif t in card.UNFILLABLE_RECS:
                can_not_fill.append(row)
            else:
                row["unknown"] = True
                can_not_fill.append(row)
    return {"ok": True, "dry": rep.get("dry", False), "cards": cards,
            "closable": closable, "closable_count": len(closable),
            "can_not_fill": can_not_fill, "can_not_fill_count": len(can_not_fill),
            "avg_content_rating": rep.get("avg_content_rating")}


# ── СВЕРКА статусов после залива (планка оператора: «ни один товар с ошибкой; надёжно как часы») ──

def classify_card_health(card):
    """ЧИСТЫЙ классификатор здоровья ОДНОЙ карточки из offer_cards_status (0₽, без сети).

    Закрывает доказанное живьём слепое пятно: `card.card_quality` РОНЯЕТ массив errors[], поэтому
    весь путь track/quality_report/verify_publish БЫЛ СЛЕП к вердиктам ошибок карточки. Здесь читаем
    И `cardStatus`, И `errors[]` и честно разделяем два разных мира:
      • our_errors     — ошибки САМОЙ карточки. Это и есть «товар с ошибкой» по планке оператора.
      • store_verdicts — «Магазин отключён по результатам проверки»: вина ВИТРИНЫ, а не карточки;
                         снимается ТОЛЬКО в кабинете (живой урок 2026-08-25). Держим ОТДЕЛЬНО, иначе
                         объявили бы чистую карточку сломанной и гоняли бы бессмысленный ре-билд.

    klass  ∈ {clean, error_fixable, frozen, store_blocked, processing, unknown}
    action ∈ {none, rebuild, wait, operator_cabinet}

    ЗАМОРОЖЕННАЯ карточка (ERROR_STATUSES + свои ошибки) = ловушка тихого проглатывания патча
    (offer-mappings отвечает 200 OK, но поле НЕ применяет) → ЛЕЧИТСЯ ПОЛНЫМ ре-билдом `publish_card`,
    а не патчем одного поля (живой урок «замороженная карточка»). Поэтому action=rebuild, не wait.
    """
    if not isinstance(card, dict):
        card = {}
    oid = card.get("offerId") or card.get("offer_id")
    status = card.get("cardStatus") or card.get("status") or ""
    rating = card.get("contentRating")
    raw = [t for t in (_err_text(e) for e in (card.get("errors") or [])) if t]
    warnings = [t for t in (_err_text(w) for w in (card.get("warnings") or [])) if t]
    store_verdicts = [t for t in raw if _is_store_verdict(t)]
    our_errors = [t for t in raw if not _is_store_verdict(t)]
    store_blocked = bool(store_verdicts)

    # Приоритет: НАШИ ошибки важнее операторского store-block (нам есть что чинить).
    # Заморозка (свои ошибки + ERROR-статус) выделена отдельно — у неё особое лечение (ре-билд).
    if our_errors and status in ERROR_STATUSES:
        klass, action = "frozen", "rebuild"
    elif our_errors:
        klass, action = "error_fixable", "rebuild"
    elif store_blocked:
        klass, action = "store_blocked", "operator_cabinet"
    elif status in ERROR_STATUSES:
        # ERROR-статус БЕЗ видимых errors[] (read отдал статус, но не список): карточка НЕ чиста.
        # Раньше падала в unknown/wait и молча шла за ✅ — ЛОЖНАЯ ЗЕЛЕНЬ. Теперь честно: ре-билд.
        klass, action = "frozen", "rebuild"
    elif status == "NO_CARD_ADD_TO_CAMPAIGN":
        # Контент готов, но оффер не помещён в кампанию → лечится РАЗМЕЩЕНИЕМ (шаг 3), не ре-билдом.
        klass, action = "needs_placement", "place"
    elif status in READY_STATUSES:
        klass, action = "clean", "none"
    elif status in PROCESSING_STATUSES or status in NEED_CONTENT:
        klass, action = "processing", "wait"
    else:
        klass, action = "unknown", "wait"

    reason = {
        "frozen": "заморожена / ERROR-статус: патч одного поля молча гибнет → полный ре-билд",
        "error_fixable": "свои ошибки при не-замороженном статусе → повторный полный залив",
        "store_blocked": "карточка чиста; «Магазин отключён» снимает ТОЛЬКО оператор в кабинете",
        "needs_placement": "контент готов, но оффер не в кампании → разместить (campaign-offers), не ре-билд",
        "clean": "без своих ошибок, статус готов",
        "processing": "в обработке/ждёт контент — возможен асинхрон (перечитать после паузы)",
        "unknown": f"незнакомый статус {status!r} — здоровье за факт не выдаём",
    }[klass]

    return {
        "offerId": oid, "cardStatus": status, "contentRating": rating,
        "klass": klass, "action": action,
        "our_errors": our_errors, "store_verdicts": store_verdicts,
        "store_blocked": store_blocked, "all_errors": raw, "warnings": warnings, "reason": reason,
    }


def reconcile(offer_ids, business_id=None, settle_wait=90, reread=True, dry=True, commit=False,
              limit=50, cards_fn=None, sleep_fn=None):
    """Пост-заливочная СВЕРКА по каждому SKU: читаем offer-cards, КЛАССИФИЦИРУЕМ здоровье, различаем
    асинхрон-лаг от заморозки, отделяем операторский «магазин отключён» от НАШИХ ошибок.

    Кодифицированный ответ на планку оператора: «инструмент не просто заливает, а ОТСЛЕЖИВАЕТ статусы;
    ни один товар не должен быть с ошибкой; быстро и надёжно как швейцарские часы».

    Асинхрон vs заморозка (живые уроки): offer-mappings пишет АСИНХРОННО ~50–110с, немедленное чтение
    стухшее. Поэтому при reread читаем ДВАЖДЫ с паузой settle_wait: если ошибки/обработка ушли на 2-м
    чтении — это был асинхрон-лаг (settled_change=True, был→стал); если карточка так и заморожена —
    это НАСТОЯЩАЯ заморозка, лечится ре-билдом. Так «200 OK врёт» не путается с «поле ещё не осело».

    READ, 0₽. На ЖИВОМ пути под тем же двойным гейтом (not dry AND commit): даже чтение не идёт наружу
    без --commit. cards_fn/sleep_fn инъектируемы → сухие тесты гоняют классификацию без сети и без сна
    (settle_wait=0). Наружу НИЧЕГО не пишет — только читает; RUBICON не при чём (нет commit-пути записи).
    """
    ids = list(offer_ids or [])
    # Живой ридер под гейтом; инъекция cards_fn (тесты/кастом) обходит и сеть, и гейт — чисто.
    if cards_fn is None:
        if dry or not commit:
            tag = "dry" if dry else "no-commit"
            return {"ok": False, "dry": dry, "commit": commit,
                    "note": f"СВЕРКА не выполнена ({tag}): нужен реальный режим (dry=False) и --commit"}
        bid = business_id or hands.business_id_env()
        if not bid:
            try:
                bid, _cid, _src = hands.resolve_ids()
            except (hands.YMarketHTTPError, RuntimeError) as e:
                return {"ok": False, "dry": False, "error": f"не удалось узнать businessId ({e})"}
        if not bid:
            return {"ok": False, "dry": False, "error": "businessId неизвестен — СВЕРКА невозможна"}
        reader = lambda _ids: hands.offer_cards_status(bid, offer_ids=_ids or None, limit=limit)
    else:
        reader = cards_fn
    sleep_fn = sleep_fn or time.sleep

    def _read_and_classify(_ids):
        try:
            rows = reader(_ids)
        except (hands.YMarketHTTPError, RuntimeError) as e:
            return None, str(e)
        by = {}
        for r in (rows if isinstance(rows, list) else []):
            v = classify_card_health(r)
            if v["offerId"] is not None:
                by[v["offerId"]] = v
        return by, None

    first, err = _read_and_classify(ids)
    if err:
        return {"ok": False, "dry": False, "error": err}

    settled, verdicts_by = False, first
    disappeared = []      # битые в 1-м чтении и ПРОПАВШИЕ из 2-го среза — не теряем (иначе ложная зелень)
    if reread and settle_wait and settle_wait > 0:
        sleep_fn(settle_wait)
        second, err2 = _read_and_classify(ids)
        if err2:
            return {"ok": False, "dry": False, "error": err2, "first_pass": list(first.values())}
        # Финал = 2-е чтение (после оседания). Отмечаем, где здоровье УЛУЧШИЛОСЬ — это был асинхрон-лаг,
        # а НЕ заморозка (заморозка на 2-м чтении осталась бы frozen).
        for oid, v2 in second.items():
            v1 = first.get(oid)
            v2["was"] = v1["klass"] if v1 else None
            v2["settled_change"] = bool(v1 and v1["klass"] in ("frozen", "error_fixable", "processing")
                                        and v2["klass"] in ("clean", "store_blocked", "processing")
                                        and v2["klass"] != v1["klass"])
        # Пропавшие из 2-го чтения, но БИТЫЕ в 1-м: перечитанный срез (limit/пагинация) мог их не отдать —
        # засчитать за «исцелились» НЕЛЬЗЯ. Переносим вердикт 1-го чтения вперёд, помечаем disappeared.
        for oid, v1 in first.items():
            if oid not in second and v1["klass"] in ("frozen", "error_fixable"):
                v1["disappeared"] = True
                second[oid] = v1
                disappeared.append(oid)
        settled, verdicts_by = True, second

    verdicts = list(verdicts_by.values())
    # Запрошенные, но не вернувшиеся SKU — честно НЕ выдаём за clean (могли ещё не проступить/не существуют).
    missing = [oid for oid in ids if oid not in verdicts_by]
    our_error_skus = [v["offerId"] for v in verdicts if v["our_errors"]]      # есть ТЕКСТ своей ошибки
    # «Товар с ошибкой» по планке оператора = требует НАШЕГО ре-билда (frozen/error_fixable),
    # ВКЛЮЧАЯ ERROR-статус без видимых errors[] (иначе пустой errors[] под *_ERRORS = ложная зелень).
    error_skus = [v["offerId"] for v in verdicts if v["klass"] in ("frozen", "error_fixable")]
    frozen_skus = [v["offerId"] for v in verdicts if v["klass"] == "frozen"]
    store_blocked_skus = [v["offerId"] for v in verdicts if v["store_blocked"]]
    needs_rebuild = [v["offerId"] for v in verdicts if v["action"] == "rebuild"]
    needs_placement = [v["offerId"] for v in verdicts if v["action"] == "place"]
    clean_skus = [v["offerId"] for v in verdicts if v["klass"] == "clean"]

    return {
        "ok": True, "dry": False, "settled": settled, "settle_wait": settle_wait,
        "verdicts": verdicts, "count": len(verdicts), "missing": missing,
        "our_error_skus": our_error_skus, "error_skus": error_skus,
        # Планка «ни один товар с ошибкой» — по НАШИМ ошибкам (вина витрины сюда НЕ входит).
        "all_clean_of_our_errors": len(error_skus) == 0,
        # Строгий вердикт «швейцарские часы»: КАЖДАЯ карточка реально clean, все запрошенные видны,
        # никто не пропал. store_blocked/needs_placement/processing сюда НЕ проходят — это не «готово как часы».
        "all_verified_clean": (bool(verdicts) and all(v["klass"] == "clean" for v in verdicts)
                               and not missing and not disappeared),
        "frozen_skus": frozen_skus, "needs_rebuild": needs_rebuild, "needs_placement": needs_placement,
        "store_blocked_skus": store_blocked_skus, "clean_skus": clean_skus, "disappeared": disappeared,
        # Витрина отключена целиком (все вернувшиеся карточки несут store-вердикт) — доминирующий блокер.
        "store_blocked_all": bool(verdicts) and len(store_blocked_skus) == len(verdicts),
        # Модерация/включение ВИТРИНЫ через offer-cards API НЕ видны (apiAvailability врёт AVAILABLE) —
        # подтверждается ТОЛЬКО в кабинете. Отсутствие store-вердикта ≠ «витрина жива».
        "storefront_moderation_unknown": not bool(store_blocked_skus),
        "storefront_caveat": ("состояние модерации/включения витрины через offer-cards API не видно; "
                              "подтверждается ТОЛЬКО в кабинете (apiAvailability врёт AVAILABLE)"),
    }


def _print_reconcile(rep):
    """Человеческая сводка СВЕРКИ (как друг с цифрами): что чисто, что чинить, что — к оператору."""
    if not rep.get("ok"):
        print(f"🩺 СВЕРКА не выполнена: {rep.get('note') or rep.get('error') or '?'}")
        return
    print(f"🩺 СВЕРКА · карточек={rep.get('count')}  осело={rep.get('settled')}  "
          f"свои ошибки={'НЕТ ✅' if rep.get('all_clean_of_our_errors') else 'ЕСТЬ ❌'}")
    for v in rep.get("verdicts", []):
        mark = {"clean": "✅", "store_blocked": "🏪", "frozen": "🧊", "needs_placement": "🧩",
                "error_fixable": "🔧", "processing": "⏳", "unknown": "❓"}.get(v["klass"], "·")
        chg = "  (осело: был " + str(v.get("was")) + ")" if v.get("settled_change") else ""
        gone = "  ⚠️пропал из 2-го чтения" if v.get("disappeared") else ""
        print(f"   {mark} {v['offerId']}: {v['klass']} → {v['action']} · {v['cardStatus']}{chg}{gone}")
        if v["our_errors"]:
            print(f"        свои ошибки: {'; '.join(v['our_errors'])}")
        if v["store_verdicts"]:
            print(f"        витрина (оператор): {'; '.join(v['store_verdicts'])}")
        if v.get("warnings"):
            print(f"        предупреждения: {'; '.join(v['warnings'])}")
    if rep.get("missing"):
        print(f"   ❓ не вернулись (не проступили/не существуют): {', '.join(map(str, rep['missing']))}")
    if rep.get("needs_rebuild"):
        print(f"   🔧 нужен ре-билд: {', '.join(map(str, rep['needs_rebuild']))}")
    if rep.get("needs_placement"):
        print(f"   🧩 нужно разместить в кампании: {', '.join(map(str, rep['needs_placement']))}")
    if rep.get("store_blocked_all"):
        print("   🏪 ВСЯ витрина отключена по проверке — доминирующий блокер снимает ТОЛЬКО оператор в кабинете.")
    if rep.get("storefront_moderation_unknown"):
        print("   ⚠️ витрина: модерация/включение через API не видны — подтвердить в кабинете.")


def _main(argv=None):
    ap = argparse.ArgumentParser(description="YMARKET WRITE V1 — писатель карточек Яндекс.Маркета (dry по умолчанию)")
    ap.add_argument("--sku", default="TEST-001")
    ap.add_argument("--name", default="Пакет фасовочный пищевой 24х15 см, 100 шт")
    ap.add_argument("--price", type=float, default=99.0)
    ap.add_argument("--slug", default="pishevaya-upakovka")
    ap.add_argument("--commit", action="store_true", help="РЕАЛЬНЫЙ залив (по отмашке; иначе dry)")
    ap.add_argument("--quality", action="store_true", help="замерить индекс (contentRating)")
    ap.add_argument("--reconcile", action="store_true",
                    help="СВЕРКА статусов после залива: классификация здоровья каждого SKU (READ, 0₽)")
    ap.add_argument("--offers", default="", help="SKU для --reconcile через запятую (пусто = весь каталог)")
    ap.add_argument("--settle-wait", type=int, default=90,
                    help="пауза (сек) между двумя чтениями СВЕРКИ — различить асинхрон-лаг от заморозки")
    ap.add_argument("--no-reread", action="store_true", help="СВЕРКА в одно чтение (без ожидания оседания)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.reconcile:
        offers = [s.strip() for s in args.offers.split(",") if s.strip()]
        res = reconcile(offers, settle_wait=args.settle_wait, reread=not args.no_reread,
                        dry=not args.commit, commit=args.commit)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            _print_reconcile(res)
        return 0 if res.get("ok") else 1

    if args.quality:
        res = quality_report(dry=not args.commit, commit=args.commit)
    else:
        prod = {"sku": args.sku, "name": args.name, "cost": args.price,
                "vendor": "SOCC", "pictures": ["https://img.example/socc.jpg"]}
        res = publish_card(prod, slug=args.slug, dry=not args.commit, commit=args.commit)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    if args.quality:
        if not res.get("ok"):
            print(f"📊 quality: {res.get('note', res.get('error', '?'))}")
            return 0
        print(f"📊 INDEX · карточек={res.get('count')}  средний contentRating={res.get('avg_content_rating')}%")
        for c in res.get("cards", []):
            print(f"   {c.get('offerId')}: {c.get('contentRating')}% "
                  f"(средн.категории {c.get('averageContentRating')}) · {c.get('cardStatus')}")
            for r in c.get("recommendations", []):
                print(f"       рекомендация {r.get('type')} +{r.get('remainingRatingPoints')}pt")
            if c.get("can_not_fill"):
                print(f"       ⚠️ не закрыть API: {', '.join(c['can_not_fill'])}")
        return 0

    print(f"🛰  YMARKET WRITE · карточка {res.get('offer_id')}  slug={res.get('slug')}  "
          f"dry={res.get('dry')}  commit={res.get('commit')}")
    if res.get("need_mapping"):
        print(f"   ⛔ карточка НЕ публикуется: категория «{res.get('slug')}» без подтверждённого "
              f"marketCategoryId (не выдумываем id).")
        print(f"      → подтверди маппинг в ymarket_cats_v1.json через categories_tree(), затем повтори.")
        if res.get("dry"):
            print("      (dry: точный payload шагов 1–2 напечатан выше, НИЧЕГО не отправлено.)")
        return 1
    if not res.get("ok"):
        print(f"   ⛔ не прошло на шаге «{res.get('step') or '?'}»: {res.get('error') or ''}")
        print(f"   ошибки: {res.get('errors') or '—'}")
        return 1
    print(f"   статус: {res.get('status')}  опубликовано={res.get('published')}")
    print(f"   ошибки={len(res.get('create_card', {}).get('errors', []))} "
          f"предупреждения={len(res.get('create_card', {}).get('warnings', []))}")
    if res.get("dry"):
        print("   (dry: точный payload напечатан выше, НИЧЕГО не отправлено. Для реального залива "
              "сначала подтверди маппинг категорий, потом --commit по отмашке.)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

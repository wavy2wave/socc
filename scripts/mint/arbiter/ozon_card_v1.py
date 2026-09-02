#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON CARD V1 — сборщик товара для Ozon Seller API /v3/product/import (чистая модель данных, 0₽).

Зеркалит ymarket_card_v1.to_offer (доказанный образец), меняет ТРИ вещи под Озон:
  1) ФОРМА payload — не offer-mappings Маркета, а item для POST /v3/product/import (плоские поля
     depth/width/height/weight + единицы, price СТРОКОЙ, vat строкой-энумом, attributes[] со своей
     вложенностью {complex_id,id,values:[{dictionary_value_id,value}]}).
  2) ЗАКОН КАТЕГОРИИ — ПЕРЕВЁРНУТ относительно Маркета (см. ниже, критично).
  3) ЕДИНИЦЫ/энумы Озона (vat как доля «0.2», размер в мм, вес в г).

════════════════════════════════════════════════════════════════════════════════════════════════
ЗАКОН КАТЕГОРИИ (ГЛАВНОЕ ОТЛИЧИЕ ОТ ЯНДЕКСА — не перепутать!):
  У Маркета есть АВТО-категория: нет marketCategoryId → Маркет решает сам, карточка всё равно летит.
  У Ozon авто-категории НЕТ. /v3/product/import ТРЕБУЕТ description_category_id И type_id (оба, int64,
  лист дерева). Значит need_mapping у Озона = карточку ФИЗИЧЕСКИ НЕЛЬЗЯ создать (честный ЖЁСТКИЙ блок).
  Поэтому здесь: can_build = bool(description_category_id AND type_id). can_build=False →
  item=None + need_mapping=True (НЕ исключение — это законное состояние, менеджер идёт в RESOLVE_MAPPING;
  закон OZ2 «категорию не выдумываем»). id категории НИКОГДА не сочиняем — только из живого дерева
  (POST /v1/description-category/tree) через справочник ozon_cats_v1.json.
════════════════════════════════════════════════════════════════════════════════════════════════

ЗАКОН (SOCC): stdlib-only, fail-soft, честные флаги. 200≠успех — это забота писателя/proof; здесь
только ФОРМА. Не выдумываем: dictionary_value_id, категорию, цену, габариты — нет данных → не шлём/None.

CardError — только для непоправимого: нет offer_id, нет имени, цена ≤ 0. Отсутствие категории/атрибутов/
габаритов/фото — НЕ CardError, а честные флаги в meta (менеджер решит, что чинить).

Контракт item (/v3/product/import, из закреплённого контракта):
  offer_id(str≤50), name(str≤500), description_category_id(int64), type_id(int64),
  price(СТРОКА целых ₽), vat(СТРОКА-энум), currency_code('RUB'),
  dimension_unit('mm')+depth/width/height(int), weight_unit('g')+weight(int),
  attributes[]={complex_id:0,id,values:[{dictionary_value_id,value}]}, images[]≤15+primary_image,
  barcode(опц. EAN-13), old_price(опц. СТРОКА, >price).
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATS_PATH = HERE / "ozon_cats_v1.json"

# Санитизация текста: убрать непечатные управляющие (кроме таба), схлопнуть пробелы.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RE = re.compile(r"\s+")

MAX_NAME = 500        # Ozon: name ≤ 500 (у Маркета было 150 — НЕ путать)
MAX_OFFER_ID = 50     # Ozon: offer_id ≤ 50 символов, уникален в кабинете
MAX_IMAGES = 15       # Ozon: images ≤ 15 (первый = primary_image)
MAX_DESC = 3000       # разумный предел (описание в Ozon — через attributes, но лимит держим)

# НДС Ozon — СТРОКА-ДОЛЯ, НЕ проценты. Живой урок Яндекса/Озона: '0.2', НЕ '20'. УСН → '0'.
OZON_VAT_ENUM = ("0", "0.05", "0.07", "0.1", "0.2")
# Валюты Ozon (currency_code). По умолчанию рубли.
OZON_CURRENCIES = ("RUB", "BYN", "KZT", "EUR", "USD", "CNY")


class CardError(ValueError):
    """Непоправимо невалидный товар (нет offer_id/имени/цены) — собирать нечего."""
    pass


def _clean_text(v, max_len=None):
    """Почистить текст: убрать управляющие, схлопнуть пробелы, обрезать. '' если пусто."""
    if v is None:
        return ""
    s = _CONTROL_RE.sub("", str(v)).strip()
    s = _WS_RE.sub(" ", s)
    if max_len and len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def load_cats(path=None):
    """Загрузить справочник маппинга категорий (ozon_cats_v1.json). fail-soft → {}."""
    p = Path(path) if path else CATS_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("categories", {})
    except Exception:
        return {}


def category_for(prod, cats=None):
    """Найти категорию товара в справочнике (по ключевым словам в названии). Честный None если нет."""
    cats = cats if cats is not None else load_cats()
    name = _clean_text(prod.get("name", "")).lower()
    if isinstance(cats, dict):
        for slug, meta in cats.items():
            kws = (meta or {}).get("keywords", []) if isinstance(meta, dict) else []
            if any(str(k).lower() in name for k in kws):
                return slug, meta
    return None, None


def _resolve_category(prod, slug=None, cats=None):
    """Определить (description_category_id, type_id, profile, source). НИЧЕГО не выдумываем (OZ2).

    Приоритет (первый давший ОБА id побеждает):
      1) explicit — явные поля товара prod['description_category_id']+prod['type_id'] (прямой ввод/тест).
      2) cats     — справочник ozon_cats_v1.json по slug или ключевым словам (несёт profile атрибутов).
      3) none     — категории нет. У Ozon это ЖЁСТКИЙ блок (авто-категории не существует).
    """
    # 1) явные поля (инъекция в тесте / прямой ввод оператором по живому дереву)
    dci, tid = prod.get("description_category_id"), prod.get("type_id")
    if dci is not None and tid is not None:
        prof = prod.get("_profile") if isinstance(prod.get("_profile"), dict) else None
        try:
            return int(dci), int(tid), prof, "explicit"
        except (TypeError, ValueError):
            pass  # мусор в явных полях → падаем в справочник
    # 2) справочник категорий
    cats = cats if cats is not None else load_cats()
    meta = cats.get(slug) if (slug and isinstance(cats, dict)) else None
    if meta is None:
        slug, meta = category_for(prod, cats)
    if isinstance(meta, dict) and not meta.get("need_mapping"):
        cdci, ctid = meta.get("description_category_id"), meta.get("type_id")
        if cdci is not None and ctid is not None:
            try:
                prof = meta.get("profile") if isinstance(meta.get("profile"), dict) else None
                return int(cdci), int(ctid), prof, "cats"
            except (TypeError, ValueError):
                pass
    # 3) нет категории — у Ozon это ЖЁСТКИЙ блок (OZ2). Честно говорим «none».
    return None, None, None, "none"


def _normalize_vat(raw):
    """Ставка НДС Ozon → СТРОКА-ДОЛЯ из энума. Возвращает (vat, defaulted).

    Живой урок: Ozon ждёт долю ('0.2'), НЕ проценты ('20'). УСН → '0'. Принимаем и проценты
    ('20'→'0.2'), и долю ('0.2'), и запятую ('0,2'). Не распознали / нет входа → '0' + defaulted=True
    (честно: применили дефолт, а не подтверждённую ставку).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return "0", True
    s = str(raw).replace(",", ".").strip()
    aliases = {
        "20": "0.2", "10": "0.1", "7": "0.07", "5": "0.05", "0": "0",
        "0.20": "0.2", "0.10": "0.1", "0.070": "0.07", "0.050": "0.05", "0.0": "0",
        "0.2": "0.2", "0.1": "0.1", "0.07": "0.07", "0.05": "0.05",
    }
    v = aliases.get(s, s)
    if v in OZON_VAT_ENUM:
        return v, False
    # Числовой фолбэк: float-проценты и десятичные строки ('20.0', 20.0, '10.00') таблица алиасов
    # не ловит (str(20.0)=='20.0'). Проценты (≥1) → доля (÷100); доля — как есть. Сопоставляем с
    # энумом по близости, иначе честный дефолт. Закрывает «20.0 → тихо 0% НДС».
    try:
        f = float(s)
    except (TypeError, ValueError):
        return "0", True
    if f >= 1:
        f = f / 100.0
    for cand in OZON_VAT_ENUM:
        if abs(f - float(cand)) < 1e-9:
            return cand, False
    return "0", True


def _num_str(v):
    """Число → строка ('0.3', '50'). Не число → None. (Ozon свободные текст-атрибуты — строкой.)"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return str(int(f)) if f.is_integer() else str(f)


def _barcode(prod):
    """Штрихкод товара (barcode|barcodes[0]). Нет → None (не выдумываем)."""
    raw = prod.get("barcode") or prod.get("barcodes")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None:
        return None
    b = _clean_text(raw)
    return b if b else None


def _ozon_dimensions(prod):
    """Габариты для Ozon /v3/product/import — ПЛОСКИЕ поля + единицы. Всё-или-ничего.

    Ozon шлёт габариты не объектом, а отдельными полями: depth/width/height (целые) + dimension_unit,
    weight (целое) + weight_unit. Неполный/невалидный набор Ozon отклоняет → отдаём None (не выдумываем).

    Два источника:
      • prod['dimensions'] = {depth,width,height,weight} — Ozon-РОДНЫЕ мм/г, берём как есть (округляя).
      • prod['weightDimensions'] = {length,width,height,weight} — см/кг (шейп Маркета), КОНВЕРТИРУЕМ:
        length→depth, ×10 (см→мм), вес ×1000 (кг→г). Единицы фиксируем явно, чтобы не соврать масштабом.
    """
    d = prod.get("dimensions")
    if isinstance(d, dict):
        vals = {}
        for k in ("depth", "width", "height", "weight"):
            try:
                x = float(d.get(k))
            except (TypeError, ValueError):
                return None
            if not (x > 0):
                return None
            iv = int(round(x))
            if iv <= 0:          # 0.3 мм/г → round=0: Ozon отвергнет, мусор не шлём (гейт по ВЫХОДУ)
                return None
            vals[k] = iv
        return {"depth": vals["depth"], "width": vals["width"], "height": vals["height"],
                "weight": vals["weight"], "dimension_unit": "mm", "weight_unit": "g"}
    wd = prod.get("weightDimensions")
    if isinstance(wd, dict):
        try:
            length = float(wd.get("length")); width = float(wd.get("width"))
            height = float(wd.get("height")); weight = float(wd.get("weight"))
        except (TypeError, ValueError):
            return None
        if not all(x > 0 for x in (length, width, height, weight)):
            return None
        conv = {"depth": int(round(length * 10)), "width": int(round(width * 10)),
                "height": int(round(height * 10)), "weight": int(round(weight * 1000))}
        if any(v <= 0 for v in conv.values()):   # суб-мм/суб-г после конверсии → 0: не шлём
            return None
        return {**conv, "dimension_unit": "mm", "weight_unit": "g"}
    return None


def _title_words(s):
    """Слова названия в нижнем регистре (для проверки «квалификатор уже в имени?»)."""
    return {t.lower() for t in "".join(c if (c.isalnum() or c.isspace()) else " "
                                       for c in (s or "")).split()}


def _append_qualifiers(source_name, house_brand="", extra_kw=None, max_len=MAX_NAME):
    """Уникальное НАИМЕНОВАНИЕ БЕЗ ПОТЕРЬ: имя товара 1-в-1 + свой квалификатор суффиксом.

    Имя товара НЕПРИКОСНОВЕННО — никаких перестановок/срезов/чистки. Размер и единицы часто живут в
    одиночных символах и дробях («0,3×100 м», «40 г/м²»); любой рерайт их искажает — это враньё о сути.
    house_brand/extra_kw добавляем В КОНЕЦ, только если такого слова ещё нет в имени (сравнение по словам,
    регистронезависимо) и результат влезает в max_len. extra_kw — ОДИН ключ (не итерируем по буквам).
    """
    base = (source_name or "").strip()
    if not base:
        return ""
    have = _title_words(base)
    additions = []
    if extra_kw:
        kws = [extra_kw] if isinstance(extra_kw, str) else list(extra_kw)
        for kw in kws:
            kw = str(kw).strip()
            kw_words = _title_words(kw)
            if kw_words and not kw_words <= have:
                additions.append(kw)
                have |= kw_words
    if house_brand:
        hb = str(house_brand).strip()
        hb_words = _title_words(hb)
        if hb_words and not hb_words <= have:
            additions.append(hb)
            have |= hb_words
    out = base
    for add in additions:
        cand = f"{out} {add}"
        if len(cand) <= max_len:
            out = cand
    return out[:max_len].strip()


def _build_attributes(prod, profile):
    """ПОДТВЕРЖДЁННЫЙ профиль категории Ozon → attributes[] для /v3/product/import.

    Каждый атрибут: {complex_id:0, id:<из /v1/description-category/attribute>,
                     values:[{dictionary_value_id:<из /attribute/values>, value:"метка|свободный текст"}]}
    Профиль наполняется ТОЛЬКО из живого пула (attribute + attribute/values) — см. МЕТОД в ozon_cats_v1.json.

    Секции профиля (зеркало profile_parameter_values Яндекса под форму Озона):
      • attr_constants — категорийные константы (верны для всей категории): {label:{id,dictionary_value_id,value}}
      • attr_specs     — числовые/текстовые спеки (свободная форма, dictionary_id=0): {key:{id, from?}}
      • attr_enums     — словарные: {key:{id, values:{lookup: dictionary_value_id}}}
    ЧЕСТНОСТЬ: dictionary_value_id НЕ выдумываем — нет соответствия в словаре → атрибут НЕ шлём.
    """
    if not isinstance(profile, dict):
        return []
    spec = dict(prod["_spec"]) if isinstance(prod.get("_spec"), dict) else {}
    out, seen = [], set()

    # 1) Категорийные константы — по определению верны для всей категории.
    for _label, c in (profile.get("attr_constants") or {}).items():
        if not isinstance(c, dict):
            continue
        aid = c.get("id")
        if aid is None:
            continue
        try:
            aid = int(aid)
        except (TypeError, ValueError):
            continue
        if aid in seen:
            continue
        val = {"value": c.get("value")}
        if c.get("dictionary_value_id") is not None:
            try:
                val["dictionary_value_id"] = int(c["dictionary_value_id"])
            except (TypeError, ValueError):
                pass
        out.append({"complex_id": 0, "id": aid, "values": [val]})
        seen.add(aid)

    # 2) Числовые/текстовые спеки — свободная форма (dictionary_id=0), значение строкой.
    for key, u in (profile.get("attr_specs") or {}).items():
        if key.startswith("_") or not isinstance(u, dict):
            continue
        aid = u.get("id")
        if aid is None:
            continue
        try:
            aid = int(aid)
        except (TypeError, ValueError):
            continue
        if aid in seen:
            continue
        raw = spec.get(u.get("from", key))
        if raw is None:
            continue
        s = _num_str(raw) if isinstance(raw, (int, float)) else _clean_text(raw)
        if not s:
            continue
        out.append({"complex_id": 0, "id": aid, "values": [{"value": str(s)}]})
        seen.add(aid)

    # 3) Словарные (ENUM): значение товара → dictionary_value_id справочника Озона.
    for key, m in (profile.get("attr_enums") or {}).items():
        if key.startswith("_") or not isinstance(m, dict):
            continue
        aid = m.get("id")
        if aid is None:
            continue
        try:
            aid = int(aid)
        except (TypeError, ValueError):
            continue
        if aid in seen:
            continue
        raw = spec.get(key)
        if raw is None:
            continue
        vals = m.get("values") or {}
        if isinstance(raw, (int, float)) and float(raw).is_integer():
            lookup = str(int(raw))
        else:
            lookup = _clean_text(raw).lower().replace("ё", "е")
        dvid = vals.get(lookup)
        if dvid is None:  # мягкий проход: «ПВД (полиэтилен высокого давления)» содержит ключ словаря
            for k2, v2 in vals.items():
                if k2 and not str(k2).startswith("_") and str(k2) in lookup:
                    dvid = v2
                    break
        if dvid is None:
            continue  # не подтверждено — dictionary_value_id НЕ выдумываем
        try:
            dvid = int(dvid)
        except (TypeError, ValueError):
            continue
        out.append({"complex_id": 0, "id": aid,
                    "values": [{"dictionary_value_id": dvid, "value": lookup}]})
        seen.add(aid)

    return out


def to_item(prod, slug=None, cats=None, unique_name=None, house_brand=None, extra_kw=None):
    """Нормализованный товар → item для POST /v3/product/import (+ флаги честности в meta).

    Возвращает {'item': {...}|None, 'meta': {...}}.
      • item != None  — можно слать в /v3/product/import (категория есть, форма собрана).
      • item is None  — need_mapping=True: у Озона НЕТ авто-категории, без description_category_id+type_id
                        карточку физически НЕ создать (закон OZ2). Это НЕ ошибка — менеджер идёт в
                        RESOLVE_MAPPING (глаза оператора привяжут категорию по живому дереву).

    CardError — только непоправимое: нет offer_id, нет имени, цена ≤ 0.

    УНИКАЛЬНОЕ ИМЯ (unique_name) — вторичный анти-склейка рычаг (главный — ШТРИХКОД). Имя НЕ рерайтим
    (теряет размер: «0,3×100 м»→«3x100»); свой квалификатор (house_brand/extra_kw) добавляем суффиксом.
    name_source='unique' ТОЛЬКО когда реально добавили квалификатор; иначе 'verbatim'/'verbatim_fallback'.
    """
    if not isinstance(prod, dict):
        raise CardError("товар не dict")
    sku = _clean_text(prod.get("offer_id") or prod.get("sku") or prod.get("offerId"))
    if not sku:
        raise CardError("нет offer_id (sku) — карточку не собрать")
    offer_id_full = sku
    offer_id_truncated = len(sku) > MAX_OFFER_ID
    if offer_id_truncated:
        sku = sku[:MAX_OFFER_ID]   # Ozon: offer_id ≤ 50 — режем, но ЧЕСТНО помечаем (риск коллизии id)
    name = _clean_text(prod.get("name"), MAX_NAME)
    if not name:
        raise CardError(f"нет названия у {sku} — карточку не собрать")

    # ── Уникальное имя (опц., анти-склейка; имя 1-в-1 + квалификатор суффиксом) ──
    original_name = name
    want_unique = prod.get("unique_name") if unique_name is None else unique_name
    name_source = "verbatim"                       # verbatim | unique | verbatim_fallback
    if want_unique:
        hb = house_brand if house_brand is not None else (prod.get("house_brand") or "")
        kw = extra_kw if extra_kw is not None else prod.get("extra_kw")
        cand = _append_qualifiers(original_name, house_brand=hb, extra_kw=kw, max_len=MAX_NAME)
        if cand and cand != original_name:
            name, name_source = cand, "unique"
        else:
            name_source = "verbatim_fallback"

    # ── Цена — СТРОКА целых рублей (Ozon: price is string; дробь → warning NUMBER_FORMAT) ──
    price_raw = prod.get("price") or prod.get("basicPrice") or prod.get("cost") or 0
    try:
        price_f = float(price_raw)
    except Exception:
        price_f = 0.0
    if not (price_f > 0):
        raise CardError(f"цена {sku} ≤ 0 — не выдумываем цену")
    price_int = int(round(price_f))
    if price_int <= 0:            # 0<price<0.5 округляется в 0₽ — продавать за 0 нельзя (гейт по ВЫХОДУ)
        raise CardError(f"цена {sku} округляется в 0₽ — не выдумываем цену")
    price = str(price_int)

    # ── Категория: explicit → cats → none. У Ozon НЕТ авто-категории → отсутствие = ЖЁСТКИЙ блок ──
    dci, type_id, profile, csource = _resolve_category(prod, slug, cats)
    can_build = dci is not None and type_id is not None
    need_mapping = not can_build

    # ── Прочие поля формы ──
    vat, vat_defaulted = _normalize_vat(prod.get("vat"))
    dims = _ozon_dimensions(prod)
    attrs = _build_attributes(prod, profile) if can_build else []
    imgs = prod.get("images") or prod.get("pictures")
    if isinstance(imgs, list):
        imgs = [_clean_text(p) for p in imgs if _clean_text(p)][:MAX_IMAGES]
    else:
        imgs = []
    barcode = _barcode(prod)

    meta = {
        "offer_id": sku,
        "offer_id_truncated": offer_id_truncated,   # True = обрезан до 50 (риск коллизии уникального id)
        "offer_id_full": (offer_id_full if offer_id_truncated else None),
        "slug": slug,
        "description_category_id": dci,
        "type_id": type_id,
        "category_source": csource,            # explicit | cats | none
        "need_mapping": need_mapping,          # честный флаг «своей категории нет»
        "can_build": can_build,                # ЖЁСТКИЙ гейт: без категории карточку не создать
        "block_reason": (None if can_build else
                         "нет description_category_id/type_id — у Ozon нет авто-категории (OZ2)"),
        "price": price,                        # строка целых ₽ (как уйдёт в payload)
        "vat": vat,
        "vat_defaulted": vat_defaulted,        # True = применили дефолт '0', не подтверждённую ставку
        "missing_images": not imgs,
        "missing_dimensions": dims is None,
        "attrs_built": len(attrs),
        "has_barcode": barcode is not None,
        "name_source": name_source,            # verbatim | unique | verbatim_fallback
        "original_name": (original_name if name != original_name else None),
    }

    # ЖЁСТКИЙ БЛОК Ozon: без категории карточку физически не создать. item=None (законно, не исключение).
    if not can_build:
        return {"item": None, "meta": meta}

    item = {
        "offer_id": sku,
        "name": name,
        "description_category_id": int(dci),
        "type_id": int(type_id),
        "price": price,                        # СТРОКА (Ozon требует price строкой)
        "vat": vat,                            # СТРОКА-энум ('0'|'0.05'|'0.07'|'0.1'|'0.2')
        "currency_code": "RUB",
    }
    if dims:
        item.update(dims)                      # depth/width/height/weight + dimension_unit/weight_unit
    if attrs:
        item["attributes"] = attrs
    if imgs:
        item["images"] = imgs
        item["primary_image"] = imgs[0]        # первое фото — главное
    if barcode:
        item["barcode"] = barcode
    # old_price (опц.): только если СТРОГО больше price (иначе Ozon ругается / бессмысленно)
    old_raw = prod.get("old_price")
    if old_raw is not None:
        try:
            old_f = float(old_raw)
            if old_f > price_f:
                item["old_price"] = str(int(round(old_f)))
        except Exception:
            pass

    return {"item": item, "meta": meta}


def import_body(items):
    """Обернуть список item в тело POST /v3/product/import: {"items":[...]}. None-item отсеиваем.

    Удобство для писателя/тестов: принимает как «сырые» item, так и результаты to_item ({'item','meta'}).
    """
    out = []
    for it in (items or []):
        if isinstance(it, dict) and "item" in it and "meta" in it:
            it = it.get("item")
        if isinstance(it, dict) and it:
            out.append(it)
    return {"items": out}


def schema():
    """Документационная сводка полей item (для писателя/тестов/кокпита)."""
    return {
        "required_item": ["offer_id", "name", "description_category_id", "type_id",
                          "price", "vat", "dimension_unit", "depth", "width", "height",
                          "weight_unit", "weight"],
        "optional_item": ["currency_code", "old_price", "primary_image", "images",
                          "attributes", "barcode", "color_image", "images360"],
        "price_is": "СТРОКА целых рублей (дробь → warning NUMBER_FORMAT)",
        "vat_enum": list(OZON_VAT_ENUM),
        "currency_enum": list(OZON_CURRENCIES),
        "category_law": "description_category_id И type_id ОБЯЗАТЕЛЬНЫ (авто-категории у Ozon НЕТ)",
        "attribute_shape": {"complex_id": 0, "id": "<attr id>",
                            "values": [{"dictionary_value_id": "<int64>", "value": "<label|free text>"}]},
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="OZON CARD V1 — сборщик item /v3/product/import (0₽)")
    ap.add_argument("--sku", default="OZ-TEST-001")
    ap.add_argument("--name", default="Органайзер для кабелей настольный, 6 отсеков")
    ap.add_argument("--price", type=float, default=499.0)
    ap.add_argument("--cat", type=int, default=None, help="description_category_id (живьём из дерева)")
    ap.add_argument("--type", dest="type_id", type=int, default=None, help="type_id (живьём из дерева)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    prod = {"offer_id": args.sku, "name": args.name, "price": args.price,
            "dimensions": {"depth": 120, "width": 80, "height": 40, "weight": 150},
            "images": ["https://img.example/ozon.jpg"], "barcode": "4600000000000"}
    if args.cat is not None:
        prod["description_category_id"] = args.cat
    if args.type_id is not None:
        prod["type_id"] = args.type_id
    try:
        r = to_item(prod)
        m = r["meta"]
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            state = "СОБРАНА" if r["item"] else "БЛОК (нет категории)"
            print(f"🧾 {m['offer_id']} — {state}  can_build={m['can_build']} "
                  f"need_mapping={m['need_mapping']} cat={m['description_category_id']} "
                  f"type={m['type_id']} price='{m['price']}' vat='{m['vat']}' "
                  f"фото={'нет' if m['missing_images'] else 'есть'} габариты="
                  f"{'нет' if m['missing_dimensions'] else 'есть'}")
            if r["item"]:
                print(json.dumps(r["item"], ensure_ascii=False, indent=2))
    except CardError as e:
        print(f"⛔ CardError: {e}")
        raise SystemExit(1)

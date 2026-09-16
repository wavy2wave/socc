#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET CARD V1 — сборщик карточки товара для Яндекс.Маркета (модель данных).

«Карточка важна. И индекс важен.» Здесь — ЧИСТАЯ МОДЕЛЬ: из нормализованного товара (схема
ARBITER base_v1.normalized) собираем offer для offer-mappings + parameterValues для offer-cards,
+ читаем contentRating/recommendations. Никакой сети и никаких денег: это чистая функция.
Держится на выученной карте API (см. yandex-market-api-map): обязательные поля offer,
content-поля (vendor/barcodes/description/weightDimensions/manufacturerCountries/videos/manuals),
маппинг категорий (ymarket_cats_v1.json, marketCategoryId не выдумываем).

ЗАКОН (SOCC): stdlib-only, fail-soft, честные флаги. 200≠успех — писатель читает errors/warnings;
здесь только форма. Цены валидируем (basicPrice>0), текст чистим.

КАТЕГОРИЯ — ТРИ ИСТОЧНИКА (сверху вниз, первый давший id побеждает):
  1) cats     — ручной справочник ymarket_cats_v1.json (несёт profile с точными unitId/valueId).
  2) мост     — ymarket_category_map_v1: правила/лексика по ЖИВОМУ дереву Маркета (8774 листа).
  3) авто     — id нет. Шлём БЕЗ marketCategoryId и БЕЗ parameterValues, Маркет решает сам.

ЗАКОН КАТЕГОРИИ (переписан 2026-08-06 по живому опыту, отменяет прежний запрет):
  ВЫДУМАННАЯ категория — ошибка. ОТСУТСТВИЕ категории — НЕ ошибка и НЕ повод не лить.
  Доказано в кабинете Atlas Edge: TEST-AUTOCAT-1 без marketCategoryId и без parameterValues
  залился и получил категорию от Маркета; TEST-BARECAT-1 с ГОЛОЙ marketCategoryId (без
  parameterValues) принят и не встал в ERRORS. Прежний закон «нет id → карточка не летит»
  держался на догадке и стоил 4.5% каталога — снят.
  need_mapping остаётся честным флагом «своего id нет» (источник = auto), но больше НЕ блокирует.

Поля offer-mappings (обязательные + влияющие на ТОП):
  offerId (наш SKU, уникален), name, marketCategoryId|category, pictures[], vendor, vendorCode,
  barcodes[], description, manufacturerCountries[], weightDimensions{length,width,height,weight},
  videos[], manuals[], basicPrice{value,currencyId:RUR}, params[]/parameterValues[],
  boxCount, type:'DEFAULT'. ВАЖНО: поле pictures — ОБЯЗАТЕЛЬНО для карточки (рекомендация
  PICTURE_COUNT → ТОП); карточка без изображений не должна уйти в залив (honest_flag).
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATS_PATH = HERE / "ymarket_cats_v1.json"

# Санитизация текста: избавляемся от непечатных/«особых» управляющих (запрещены API, кроме таба).
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RE = re.compile(r"\s+")
MAX_NAME = 150          # разумный предел длины названия (Маркет рекомендует ≤150)
MAX_DESC = 3000         # описания — не вываливаемся за здравые лимиты
MAX_PICTURES = 30       # не больше N изображений (разумный верх; лимит API соблюдаем запасом)

# Рекомендации индекса: закрываемые данными карточки vs физически не закрыть API (честный флаг).
CLOSABLE_RECS = frozenset({"PICTURE_COUNT", "HAS_DESCRIPTION", "HAS_CARD"})
UNFILLABLE_RECS = frozenset({"HAS_VIDEO", "RECOGNIZED_VENDOR"})


class CardError(ValueError):
    """Невалидная карточка (нет offerId/имени/категории/цены) — собирать нечего."""
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
    """Загрузить справочник маппинга категорий (ymarket_cats_v1.json). fail-soft → {}."""
    p = Path(path) if path else CATS_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("categories", {})
    except Exception:
        return {}


def category_for(prod, cats=None):
    """Найти категорию товара в справочнике (по ключевым словам в названии). Честный None если нет."""
    cats = cats if cats is not None else load_cats()
    name = _clean_text(prod.get("name", "")).lower()
    for slug, meta in cats.items():
        kws = meta.get("keywords", [])
        if any(k.lower() in name for k in kws):
            return slug, meta
    return None, None


def market_category_id(slug, cats=None):
    """marketCategoryId из РУЧНОГО справочника — только подтверждённый. None если не подтверждён.

    ЗАКОН: не выдумываем id. need_mapping в справочнике → None, и слово переходит к мосту (рубеж 2),
    а если и он молчит — к авто-категории Маркета. Отсутствие id больше не блокирует залив.
    """
    cats = cats if cats is not None else load_cats()
    meta = cats.get(slug) if isinstance(cats, dict) else None
    if not meta or meta.get("need_mapping"):
        return None
    cid = meta.get("market_category_id")
    return int(cid) if isinstance(cid, (int, str)) and str(cid).isdigit() else None


# РУБЕЖ 2 — КАТЕГОРИЙНЫЙ МОСТ. Работает, когда ручной справочник молчит (товар с ЛЮБОГО сайта).
USE_BRIDGE = True   # выключатель для тестов/детерминизма: to_offer(..., bridge=False)


def bridge_category(name):
    """Имя товара → (category_id, leaf, source) через ymarket_category_map_v1.

    fail-soft ДО КОНЦА: нет модуля, нет дерева, любая беда → (None, None, 'auto').
    Мост НИКОГДА не роняет сборку карточки и никогда не блокирует залив — это его закон.
    """
    if not name:
        return None, None, "auto"
    try:
        from ymarket_category_map_v1 import match
        r = match(name) or {}
        cid = r.get("category_id")
        return (int(cid) if cid else None), r.get("leaf"), (r.get("source") or "auto")
    except Exception:
        return None, None, "auto"


def load_profile(slug, cats=None):
    """Подтверждённый профиль категории (точные unitId/valueId/константы) или None.

    Профиль наполняется ТОЛЬКО из живого category_parameters() — см. МЕТОД в ymarket_cats_v1.json.
    Нет профиля → parameter_values работает по-старому (матч по имени), ничего не ломается.
    """
    cats = cats if cats is not None else load_cats()
    meta = cats.get(slug) if isinstance(cats, dict) else None
    prof = meta.get("profile") if isinstance(meta, dict) else None
    return prof if isinstance(prof, dict) else None


def _barcode(prod):
    """Штрихкод из товара: если есть barcode — берём (карточка точнее). None → честный None."""
    raw = prod.get("barcode") or prod.get("barcodes")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None:
        return None
    b = _clean_text(raw)
    return b if b else None


def _weight_dimensions(prod):
    """Вес/габариты из товара: {length,width,height,weight} в СМ/КГ (единицы Маркета). Честность:

    объект отдаём ТОЛЬКО когда известны ВСЕ четыре (частичный weightDimensions API отклоняет и
    не закрывает рекомендацию). Точность НЕ теряем (без int()-усечения). weight_g → кг явным делением.
    Нет полного набора → None (не выдумываем; пусть рекомендация weightDimensions честно всплывёт).
    """
    wd = prod.get("weightDimensions")
    if isinstance(wd, dict):
        keys = ("length", "width", "height", "weight")
        vals = {}
        for k in keys:
            v = wd.get(k)
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = 0
            if not (v > 0):
                return None  # неполный/невалидный набор — честно ничего не шлём
            vals[k] = int(v) if float(v).is_integer() else round(float(v), 3)
        return vals
    return None


def _title_words(s):
    """Слова названия в нижнем регистре (для проверки «квалификатор уже в имени?»)."""
    return {t.lower() for t in "".join(c if (c.isalnum() or c.isspace()) else " "
                                       for c in (s or "")).split()}


def _append_qualifiers(source_name, house_brand="", extra_kw=None, max_len=MAX_NAME):
    """Уникальное НАИМЕНОВАНИЕ БЕЗ ПОТЕРЬ: имя товара 1-в-1 + свой квалификатор суффиксом.

    Имя товара НЕПРИКОСНОВЕННО — никаких перестановок/срезов/чистки. Размер и единицы часто живут
    в одиночных символах и дробях («0,3×100 м», «40 г/м²»); любой рерайт их искажает или теряет,
    а это враньё о сути (уже другой товар). Поэтому source_name копируется как есть.

    house_brand и extra_kw добавляем В КОНЕЦ, только если такого слова ещё нет в имени (сравнение
    по словам, регистронезависимо — «атлас» в имени гасит суффикс «Атлас», без дубля) и только если
    результат влезает в max_len (иначе суффикс молча пропускаем — имя товара важнее квалификатора).
    Строку extra_kw трактуем как ОДИН ключ (не итерируем по буквам — это была ловушка). Пустое имя
    → '' (решение отдаём верхнему уровню).
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
            if kw_words and not kw_words <= have:      # не полностью покрыт именем → добавляем
                additions.append(kw)
                have |= kw_words
    if house_brand:
        hb = str(house_brand).strip()
        hb_words = _title_words(hb)
        if hb_words and not hb_words <= have:          # бренда ещё нет в имени (в любом регистре)
            additions.append(hb)
            have |= hb_words
    out = base
    for add in additions:
        cand = f"{out} {add}"
        if len(cand) <= max_len:                       # не влезает → пропускаем, суть не теряем
            out = cand
    return out[:max_len].strip()


def to_offer(prod, slug=None, cats=None, bridge=None, unique_name=None,
             house_brand=None, extra_kw=None):
    """Нормализованный товар ARBITER → offer для offer-mappings (+ набор флагов честности).

    Возвращает {'offer': {...}, 'meta': {...}} — writer кладёт offer в offerMappings, а meta несёт
    флаги (need_mapping, missing_pictures, price_ok, category_id, category_source), чтобы НЕ уронить
    валидность.

    Обязательные/сильные поля: offerId (sku), name, basicPrice>0, marketCategoryId (если известна),
    pictures. Не выдумываем: vendor/barcodes/description/weightDimensions берём только если есть.
    bridge=None → USE_BRIDGE; bridge=False → в точности прежнее поведение (обратная совместимость).

    УНИКАЛЬНОЕ НАИМЕНОВАНИЕ (unique_name) — опциональный анти-склейка рычаг. Маркет склеивает наш
    оффер с чужой готовой карточкой (тогда наш контент на витрину не попадает, а contentRating
    считается по чужому). Своё уникальное имя ломает точное текстовое совпадение карточек. ЭТО
    ВТОРИЧНЫЙ рычаг: главный ключ склейки — ШТРИХКОД (свой EAN-13, живёт в own_card_fields/_barcode).
    Приоритет: аргумент unique_name → иначе prod['unique_name']. ВЫКЛ по умолчанию (None и нет флага
    в prod) → имя берётся дословно, прежнее поведение 1-в-1.
    КАК делаем уникальным: имя товара НЕ рерайтим (перестановка/срез/чистка теряют размер, напр.
    «0,3×100 м»→«3x100» — враньё о сути). Имя копируется 1-в-1, а свой квалификатор (house_brand и/или
    extra_kw) добавляется СУФФИКСОМ и только если такого слова ещё нет в имени и результат влезает в
    лимит (см. _append_qualifiers). house_brand/extra_kw — из аргумента, иначе из prod-полей.
    ЗАКОН ЧЕСТНОСТИ: name_source='unique' ТОЛЬКО когда реально добавили квалификатор (суть-имя цела как
    префикс). Нечего добавить / квалификатор уже в имени / не влез → meta['name_source']=
    'verbatim_fallback', имя дословное (не выдаём за уникальное).
    """
    if not isinstance(prod, dict):
        raise CardError("товар не dict")
    sku = _clean_text(prod.get("sku") or prod.get("offerId"))
    if not sku:
        raise CardError("нет offerId (sku) — карточку не собрать")
    name = _clean_text(prod.get("name"), MAX_NAME)
    if not name:
        raise CardError(f"нет названия у {sku} — карточку не собрать")

    # ── Уникальное НАИМЕНОВАНИЕ (опц., анти-склейка вторичным рычагом) ──
    # НЕ рерайтим имя (это теряло размер: «0,3×100 м»→«3x100»). Имя 1-в-1 + свой квалификатор в конец.
    original_name = name
    want_unique = prod.get("unique_name") if unique_name is None else unique_name
    name_source = "verbatim"                         # verbatim | unique | verbatim_fallback
    if want_unique:
        hb = house_brand if house_brand is not None else (prod.get("house_brand") or "")
        kw = extra_kw if extra_kw is not None else prod.get("extra_kw")
        cand = _append_qualifiers(original_name, house_brand=hb, extra_kw=kw, max_len=MAX_NAME)
        if cand and cand != original_name:
            # добавили реальный квалификатор → имя уникально, но суть (имя товара) на месте как префикс
            name, name_source = cand, "unique"
        else:
            # квалификатора нет / уже в имени / не влез → честно НЕ выдаём за уникальное
            name_source = "verbatim_fallback"
    price = prod.get("price") or prod.get("basicPrice") or prod.get("cost") or 0
    try:
        price = float(price)
    except Exception:
        price = 0.0
    if not (price > 0):
        raise CardError(f"цена {sku} ≤ 0 — не выдумываем цену")

    # Категория: ручной справочник → мост → авто. Пустой результат — законное состояние, не отказ.
    if slug is None:
        slug, meta = category_for(prod, cats)
    else:
        meta = (cats or load_cats()).get(slug) if isinstance((cats or load_cats()), dict) else None
    cid = market_category_id(slug, cats) if slug else None
    # Имя листа для журнала/глаз оператора: у подтверждённой категории это имя ЛИСТА Маркета
    # (leaf_title = последний сегмент market_category_path), НЕ донорский ярлык (title_ru — by design
    # имя донора). leaf_title добавлен 04.09 на все confirmed; title_ru остаётся фолбэком. Мост и
    # авто-ветка переопределяют leaf ниже (свой путь/None).
    leaf = ((meta or {}).get("leaf_title") or (meta or {}).get("title_ru")) if cid is not None else None
    csource = "cats"
    if cid is None:
        if USE_BRIDGE if bridge is None else bridge:
            cid, leaf, csource = bridge_category(name)
        else:
            csource = "auto"
    need_mapping = cid is None   # честный флаг «своего id нет»; НЕ блокирует залив (см. ЗАКОН)

    offer = {
        "offerId": sku,
        "name": name,
        "type": "DEFAULT",
        "boxCount": 1,
        # ЖИВОЙ УРОК Маркета: warning NUMBER_FORMAT — «Price field must not contain digits after
        # the point». Цена принимается только ЦЕЛОЙ (в рублях), копейки — предупреждение.
        "basicPrice": {"value": int(round(price)), "currencyId": "RUR"},
    }
    if cid is not None:
        offer["marketCategoryId"] = cid
    elif slug:
        # ЗАКОН АВТО-КАТЕГОРИИ (спека PartnerMarketCategoryId): без marketCategoryId и без
        # parameterValues Маркет читает устаревшие params/category и определяет категорию САМ.
        # Значит строка-подсказка тут не «заглушка», а рабочий вход авто-классификатора.
        offer["category"] = slug
    # БРЕНД (решение оператора 2026-08-05): по умолчанию НЕ шлём. Дропшип — vendor связывает наши
    # карточки с карточками поставщика/других перекупов (Маркет склеивает по бренду+модели), это
    # раскрывает канал и втягивает в ценовое сравнение. Нужен бренд — prod['send_vendor']=True.
    vendor = _clean_text(prod.get("vendor") or prod.get("brand"))
    if vendor and prod.get("send_vendor"):
        offer["vendor"] = vendor
    else:
        vendor = ""
    vcode = _clean_text(prod.get("vendorCode"))
    if vcode:
        offer["vendorCode"] = vcode
    b = _barcode(prod)
    if b:
        offer["barcodes"] = [b]
    desc = _clean_text(prod.get("description"), MAX_DESC)
    if desc:
        offer["description"] = desc
    pics = prod.get("pictures")
    if isinstance(pics, list):
        pics = [_clean_text(p) for p in pics if _clean_text(p)]
        pics = pics[:MAX_PICTURES]
    else:
        pics = []
    if pics:
        offer["pictures"] = pics
    wd = _weight_dimensions(prod)
    if wd:
        offer["weightDimensions"] = wd
    countries = prod.get("manufacturerCountries")
    if isinstance(countries, list) and countries:
        offer["manufacturerCountries"] = [_clean_text(c) for c in countries if _clean_text(c)]
    videos = prod.get("videos")
    if isinstance(videos, list) and videos:
        offer["videos"] = [_clean_text(v) for v in videos if _clean_text(v)]
    manuals = prod.get("manuals")
    if isinstance(manuals, list) and manuals:
        offer["manuals"] = [_clean_text(m) for m in manuals if _clean_text(m)]

    meta = {
        "offerId": sku,
        "slug": slug,
        "category_id": cid,
        "category_source": csource,   # cats | rule | lexical | auto — откуда взялся id
        "category_leaf": leaf,        # человеческое имя листа (для журнала и глаз оператора)
        "need_mapping": need_mapping,
        "missing_pictures": not pics,
        "price_ok": True,
        "has_vendor": bool(vendor),
        "has_barcode": b is not None,
        "has_description": bool(desc),
        "weight_dimensions": wd is not None,
        "name_source": name_source,                        # verbatim | unique | verbatim_fallback
        "original_name": (original_name if name != original_name else None),  # что было до рерайта
        "platform_residue": prod.get("_platform_residue"),  # чужой МП в имени (04.09; FLAG, имя НЕ тронуто)
    }
    return {"offer": offer, "meta": meta}


def _enum_value_id(param, wanted):
    """Найти valueId словарного значения в живом описании параметра. None → не подтверждено.

    ЖИВОЙ УРОК (2026-08-05): в ответе category_parameters вариант несёт ключ `id` (НЕ `valueId`),
    а сравнение обязано быть регистронезависимым и ё-нечувствительным: справочник Маркета хранит
    «полиэтилен» строчными, выгрузка донора даёт «Полиэтилен». Точное сравнение молча теряло
    ВСЕ словарные характеристики (8 из 15 долетали) → contentRating падал вдвое.
    """
    if not isinstance(param, dict) or wanted is None:
        return None
    w = _clean_text(wanted).lower().replace("ё", "е")
    if not w:
        return None
    opts = param.get("values") if isinstance(param.get("values"), list) else []
    for v in opts:
        if not isinstance(v, dict):
            continue
        label = _clean_text(v.get("value") or v.get("name")).lower().replace("ё", "е")
        vid = v.get("id", v.get("valueId"))
        if label and vid is not None and label == w:
            return int(vid)
    # мягкий проход: «ПВД (полиэтилен высокого давления)» содержит «полиэтилен»
    for v in opts:
        if not isinstance(v, dict):
            continue
        label = _clean_text(v.get("value") or v.get("name")).lower().replace("ё", "е")
        vid = v.get("id", v.get("valueId"))
        if label and vid is not None and (label in w or w in label):
            return int(vid)
    return None


def validate_against_live(parameter_values, category_params):
    """ВРАТАРЬ: сверить собранные parameterValues с ЖИВЫМИ ограничениями категории.

    ЖИВОЙ УРОК (2026-08-05): мы послали «Толщина пленки = 4» (мм, высота пузырька), а у поля
    максимум 230 (микроны, калибр плёнки) → Маркет вернул warning и карточка встала
    HAS_CARD_CAN_UPDATE_ERRORS. Отправить значение вне диапазона = испортить живую карточку.
    Поэтому ни одно числовое значение не уходит, не пройдя min/max из category_parameters.

    Возвращает (clean, dropped): clean — что можно слать, dropped — что отбраковано и ПОЧЕМУ
    (честно, для отчёта; не молчим о потере — это и есть «ни единого проёба»).
    """
    by_id = {}
    for p in (category_params or []):
        if isinstance(p, dict):
            pid = p.get("id") or p.get("parameterId")
            if pid is not None:
                by_id[int(pid)] = p
    clean, dropped = [], []
    for item in (parameter_values or []):
        pid = item.get("parameterId")
        p = by_id.get(int(pid)) if pid is not None else None
        if p is None:
            clean.append(item)  # параметра нет в описании категории — решает Маркет, не выдумываем
            continue
        name = _clean_text(p.get("name")) or str(pid)
        cons = p.get("constraints") if isinstance(p.get("constraints"), dict) else {}
        if "value" in item and p.get("type") == "NUMERIC":
            try:
                x = float(item["value"])
            except (TypeError, ValueError):
                dropped.append({"parameterId": pid, "name": name, "why": "не число"})
                continue
            lo, hi = cons.get("minValue"), cons.get("maxValue")
            if hi is not None and x > float(hi):
                dropped.append({"parameterId": pid, "name": name, "value": item["value"],
                                "why": f"больше максимума {hi} (проверь единицы измерения)"})
                continue
            if lo is not None and x < float(lo):
                dropped.append({"parameterId": pid, "name": name, "value": item["value"],
                                "why": f"меньше минимума {lo}"})
                continue
        if "value" in item and p.get("type") in ("TEXT", "ENUM"):
            ml = cons.get("maxLength")
            if ml and len(str(item["value"])) > int(ml):
                item = dict(item)
                item["value"] = str(item["value"])[:int(ml)]
        clean.append(item)
    return clean, dropped


def _num_str(v):
    """Число → строка для parameterValue ('0.3', '50'). Не число → None. (API ждёт value строкой.)"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return str(int(f)) if f.is_integer() else str(f)


# Человеческие ярлыки спек-ключей — для честной укладки в свободный текст, когда своего параметра нет.
_SPEC_LABELS = {
    "диаметр_пузырька_мм": "Диаметр пузырька, мм",
    "площадь_м2": "Площадь рулона, м²",
    "толщина_мм": "Толщина, мм",
}


def profile_parameter_values(prod, profile):
    """ПОДТВЕРЖДЁННЫЙ профиль категории → parameterValues с ТОЧНЫМИ unitId/valueId.

    Профиль живёт в ymarket_cats_v1.json (categories[slug].profile) и заполняется ТОЛЬКО из живого
    category_parameters() — это и есть МЕТОД переноса на новую категорию/новый сайт.

    Почему это отдельно от матча-по-имени:
      • unitId. У «Ширины» дефолтная единица категории — СМ. Послать 0.3 без unitId=6 значит сказать
        Маркету «0.3 см» вместо «0.3 м» — карточка будет врать. Профиль знает точную единицу.
      • ENUM. «слои: 3» надо превратить в valueId метки «трехслойная», иначе значение не примет.
      • Константы категории (Тип плёнки = воздушно-пузырьковая) верны для ВСЕХ товаров категории.
    ЧЕСТНОСТЬ: не нашли значение/соответствие в словаре — НЕ шлём (не выдумываем valueId).
    """
    if not isinstance(profile, dict):
        return []
    spec = dict(prod["_spec"]) if isinstance(prod.get("_spec"), dict) else {}

    # ЕДИНЫЙ ИСТОЧНИК ГАБАРИТОВ (иначе тихий дрейф step1↔step2). Категорийные Длина/Ширина/Высота/Вес
    # (видимая карточка, step2) и weightDimensions (логистика, step1) описывают ОДНУ коробку — расходиться
    # не имеют права. Берём ровно то, что уйдёт в логистику (_weight_dimensions: та же нормировка), и
    # добираем в spec ТОЛЬКО отсутствующее. Если товар отдал габариты лишь для логистики (нет _spec) —
    # карточка всё равно заполнится, а не уедет пустой (планка «ни один товар без ошибки»).
    # Для ПЛЁНКИ инертно: её spec_units читают ключи ширина_м/длина_м/вес_кг, а не English length/width —
    # ловушка «длина рулона только в Длину намотки» цела.
    if any(not spec.get(k) for k in ("length", "width", "height", "weight")):
        wd = _weight_dimensions(prod)
        if isinstance(wd, dict):
            for k in ("length", "width", "height", "weight"):
                if spec.get(k) is None and wd.get(k) is not None:
                    spec[k] = wd[k]

    out, seen = [], set()

    # 1) Категорийные константы — по определению верны для всей категории.
    for _label, c in (profile.get("param_constants") or {}).items():
        if not isinstance(c, dict):
            continue
        pid, vid = c.get("parameterId"), c.get("valueId")
        if pid is None or vid is None or int(pid) in seen:
            continue
        # ЖИВОЙ УРОК (2026-08-05): Яндекс принимает ENUM только когда valueId И value идут вместе.
        # По отдельности — молча отбрасывается (ни ошибки, ни предупреждения). Нигде не задокументировано.
        out.append({"parameterId": int(pid), "valueId": int(vid), "value": c.get("label"), "_label": c.get("label")})
        seen.add(int(pid))

    # 2) Числовые спеки с ТОЧНОЙ единицей измерения.
    for key, u in (profile.get("spec_units") or {}).items():
        if key.startswith("_") or not isinstance(u, dict):
            continue
        pid = u.get("parameterId")
        if pid is None or int(pid) in seen:
            continue
        raw = spec.get(u.get("from", key))
        if raw is None:
            continue
        s = _num_str(raw)
        if s is None:
            continue
        item = {"parameterId": int(pid), "value": s}
        if u.get("unitId") is not None:
            item["unitId"] = int(u["unitId"])
        out.append(item)
        seen.add(int(pid))

    # 3) Словарные (ENUM): значение товара → valueId справочника Маркета.
    for key, m in (profile.get("enum_maps") or {}).items():
        if key.startswith("_") or not isinstance(m, dict):
            continue
        pid = m.get("parameterId")
        if pid is None or int(pid) in seen:
            continue
        raw = spec.get(key)
        if raw is None:
            continue
        vals = m.get("values") or {}
        # число (слои=3) ищем как "3"; текст — в нижнем регистре
        if isinstance(raw, (int, float)) and float(raw).is_integer():
            lookup = str(int(raw))
        else:
            lookup = _clean_text(raw).lower().replace("ё", "е")
        vid = vals.get(lookup)
        if vid is None:  # мягко: «ПВД (полиэтилен высокого давления)» → содержит ключ словаря
            for k2, v2 in vals.items():
                if k2 and not k2.startswith("_") and k2 in lookup:
                    vid = v2
                    break
        if vid is None:
            continue  # не подтверждено — не шлём
        out.append({"parameterId": int(pid), "valueId": int(vid), "value": lookup, "_label": lookup})
        seen.add(int(pid))

    # 4) Свободный текст: спеки, под которые у категории НЕТ своего параметра (данные не теряем).
    extra = []
    for skey in (profile.get("no_param_for") or {}):
        if skey.startswith("_"):
            continue
        v = spec.get(skey)
        if v is None:
            continue
        label = _SPEC_LABELS.get(skey, skey.replace("_", " "))
        extra.append(f"{label}: {_num_str(v) or _clean_text(v)}")
    if extra:
        ft = profile.get("free_text_params") or {}
        pid = ft.get("Прочие характеристики") or ft.get("Дополнительная информация")
        if pid is not None and int(pid) not in seen:
            out.append({"parameterId": int(pid), "value": "; ".join(extra)[:500]})
            seen.add(int(pid))

    return out


def parameter_values(prod, category_params=None, profile=None):
    """Карточка категорийных характеристик: parameterValues из товара по СПИСКУ параметров категории.

    category_params — результат category_parameters() (список параметров: id/required/values[]/unitId).
    profile — подтверждённый профиль категории (ymarket_cats_v1.json). Если задан, его значения
    АВТОРИТЕТНЫ (точные unitId/valueId), а матч-по-имени добирает остальное. profile=None →
    поведение в точности прежнее (обратная совместимость).
    Честность:
      • Заполняем ТОЛЬКО те параметры, для которых у товара есть значение; не выдумываем.
      • Словарный/select-параметр (values[]): резолвим значение товара в valueId варианта из
        справочника; неподтверждённое значение НЕ шлём текстом (select без valueId отклоняется).
      • Обязательный параметр без значения → missing_required += 1.
      • Списка параметров нет (None/[]) → missing_required = None: «не знаем», НЕ путаем с «0 пропущено».
    """
    params = category_params if isinstance(category_params, list) else []
    out = profile_parameter_values(prod, profile) if profile else []
    covered = {i["parameterId"] for i in out}
    missing_required = 0 if params else None

    # ЖИВОЙ СПРАВОЧНИК АВТОРИТЕТНЕЕ ПРОФИЛЯ: если у параметра есть словарь значений, valueId берём
    # из него (регистронезависимо). Профиль может устареть — Маркет меняет id значений.
    by_id = {}
    for p in params:
        if isinstance(p, dict):
            pid = p.get("id") or p.get("parameterId")
            if pid is not None:
                by_id[int(pid)] = p
    for item in out:
        p = by_id.get(int(item["parameterId"]))
        if not p or p.get("type") != "ENUM":
            continue
        opts = p.get("values") if isinstance(p.get("values"), list) else []
        if not opts:
            continue
        known = {int(v.get("id", v.get("valueId"))) for v in opts
                 if isinstance(v, dict) and v.get("id", v.get("valueId")) is not None}
        vid = item.get("valueId")
        if vid is not None and int(vid) in known:
            # ENUM требует ОБА поля (valueId+value) — добираем ярлык из живого справочника
            if not item.get("value"):
                for v in opts:
                    if isinstance(v, dict) and int(v.get("id", v.get("valueId", -1))) == int(vid):
                        item["value"] = _clean_text(v.get("value") or v.get("name"))
                        break
            continue  # профиль совпал с живым справочником
        # профиль промахнулся → перерезолвим по ярлыку из профиля/значения товара
        label = item.get("_label") or item.get("value")
        fixed = _enum_value_id(p, label) if label else None
        if fixed is not None:
            item["valueId"] = fixed
            for v in opts:
                if isinstance(v, dict) and int(v.get("id", v.get("valueId", -1))) == int(fixed):
                    item["value"] = _clean_text(v.get("value") or v.get("name"))
                    break
    for item in out:
        item.pop("_label", None)

    for p in params:
        if not isinstance(p, dict):
            continue
        pid = p.get("id") or p.get("parameterId")
        pname = _clean_text(p.get("name"))
        if pid is None or int(pid) in covered:
            continue  # профиль уже закрыл этот параметр точным значением
        val = _clean_text(prod.get(pname)) if pname else ""
        if not val:
            if p.get("required"):
                missing_required = (missing_required or 0) + 1
            continue
        item = {"parameterId": int(pid)}
        # Словарный параметр: у вариантов values[] свои valueId — берём ТОЛЬКО подтверждённый.
        opts = p.get("values") if isinstance(p.get("values"), list) else None
        if opts:
            for v in opts:
                if not isinstance(v, dict):
                    continue
                label = _clean_text(v.get("value") or v.get("name"))
                if label and label.lower() == val.lower():
                    vid = v.get("valueId")
                    if vid is not None:
                        item["valueId"] = int(vid)
                    break
            if "valueId" not in item:
                continue  # не подтверждённое значение словаря НЕ шлём (select без valueId отклонят)
        else:
            item["value"] = val  # свободное текстовое поле — только для genuinely free-text
        if p.get("unitId") is not None:
            item["unitId"] = int(p["unitId"])
        out.append(item)
        covered.add(int(pid))
    return {"parameterValues": out, "missing_required": missing_required}


def card_quality(statuses, offer_id=None):
    """Из offer_cards_status() → качество карточек: contentRating + рекомендации.

    statuses — результат ymarket_hands.offer_cards_status() (список offerCards). Возвращает
    список {offerId, contentRating, averageContentRating, status, recommendations, can_not_fill}
    — can_not_fill = рекомендации, которые нельзя выполнить API (честно, не выдумываем).
    """
    if not isinstance(statuses, list):
        return []
    out = []
    for c in statuses:
        if not isinstance(c, dict):
            continue
        recs = c.get("recommendations") if isinstance(c.get("recommendations"), list) else []
        oid = c.get("offerId") or c.get("offer_id") or offer_id
        out.append({
            "offerId": oid,
            "contentRating": c.get("contentRating"),
            "averageContentRating": c.get("averageContentRating"),
            "cardStatus": c.get("cardStatus"),
            "mapping": c.get("mapping"),
            "recommendations": [
                {"type": r.get("type"), "remainingRatingPoints": r.get("remainingRatingPoints")}
                for r in recs if isinstance(r, dict)
            ],
            "can_not_fill": [r.get("type") for r in recs
                             if isinstance(r, dict) and r.get("type") in UNFILLABLE_RECS],
        })
    return out


def schema():
    """Документационная сводка полей offer (для writer/тестов/кокпита) — «что есть в карточке»."""
    return {
        "required_offer": ["offerId", "name", "basicPrice", "marketCategoryId|category", "pictures"],
        "content_for_top": ["vendor", "vendorCode", "barcodes", "description", "manufacturerCountries",
                            "weightDimensions", "videos", "manuals", "params"],
        "pricing": {"basicPrice": {"value": "number>0", "currencyId": "RUR"}},
        "card_status_enum": ["PUBLISHED", "NO_CARD_NEED_CONTENT", "NO_CARD_ADD_TO_CAMPAIGN",
                             "NO_CARD_ERRORS", "NO_CARD_PROCESSING", "HAS_CARD_CAN_UPDATE",
                             "HAS_CARD_CAN_NOT_UPDATE"],
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="YMARKET CARD V1 — сборщик карточки (чистая функция, 0₽)")
    ap.add_argument("--sku", default="TEST-001")
    ap.add_argument("--name", default="Пакет фасовочный пищевой 24х15 см, 100 шт")
    ap.add_argument("--price", type=float, default=99.0)
    ap.add_argument("--slug", default="pishevaya-upakovka")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    prod = {"sku": args.sku, "name": args.name, "cost": args.price,
            "vendor": "SOCC", "pictures": ["https://img.example/socc.jpg"],
            "weightDimensions": {"weight": 200}, "barcode": "4600000000000"}
    try:
        r = to_offer(prod, slug=args.slug)
        if args.json:
            import json
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print(f"🧾 offer: {r['meta']['offerId']}  категория={r['meta']['slug']} "
                  f"id={r['meta']['category_id']} need_mapping={r['meta']['need_mapping']} "
                  f"картинок={'есть' if not r['meta']['missing_pictures'] else 'НЕТ'}")
            import json
            print(json.dumps(r["offer"], ensure_ascii=False, indent=2))
    except CardError as e:
        print(f"⛔ CardError: {e}")
        raise SystemExit(1)

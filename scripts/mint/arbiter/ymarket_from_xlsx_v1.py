#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET FROM XLSX V1 — мост «выгрузка-парсер → нормализованный товар Яндекс.Маркета».

Веха M6 оси ARBITER, звено «рабочая лошадка»: оператор даёт XLSX категории (сейчас — выгрузка
cargo-avto из /Users/wavysexy/parsers), мост превращает КАЖДУЮ строку в нормализованный товар,
который принимают ymarket_card_v1.to_offer + ymarket_write_v1.publish_card. Цель оператора:
«карточка реально охуенно заполнена → в ТОП». Значит мост не просто копирует поля, а ОБОГАЩАЕТ
их характеристиками, которые важны в категории (разведка конкурентов Яндекс.Маркета).

ЗАКОН SOCC (как весь ARBITER):
  • stdlib + openpyxl (та же зависимость, что у парсера); БЕЗ сети и БЕЗ денег — чистое чтение файла.
  • ЧЕСТНОСТЬ (без фейк-пасс): извлекаем ТОЛЬКО то, что реально есть в имени/описании/характеристиках
    строки. Не нашли плотность — поле пустое, НЕ выдумываем «40 г/м²». Разобранное — из текста товара.
  • ГЕНЕРИЧНОСТЬ: колонки матчатся по СМЫСЛУ (нечёткое имя заголовка), а не по точной строке —
    чтобы тот же мост принял выгрузку с другого сайта с минимальной правкой (будущее: «дал сайт → в Яндекс»).
  • НЕ ЛОМАЕТ орган: это новый модуль, ничего в hands/card/write не трогает.

Разведка категории «воздушно-пузырьковая плёнка» (что важно в карточке, по конкурентам Маркета):
  плотность г/м² · ширина рулона м · длина намотки м · диаметр пузырька мм · число слоёв · материал.
Эти же поля кладём в prod под человекочитаемыми именами — как только category_parameters() подтвердит
реальные parameterId, ymarket_card_v1.parameter_values() сматчит их по имени и карточка получит
категорийные характеристики (рост contentRating). До подтверждения они честно живут в описании/спеке.
"""
import re
import sys
import json
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (str(HERE), str(HERE.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ── Нечёткий матч колонок по смыслу (генерично; заголовки разных выгрузок отличаются пунктуацией) ──
# Каждый логический ключ → список подстрок-признаков (все в нижнем регистре). Первый заголовок,
# содержащий ЛЮБОЙ признак (и не попавший в exclude), выигрывает.
# Приоритет: основные правила → fallback (если основные не сработали).
COLUMN_MATCHERS = {
    "sku":          {"any": ["артикул", "sku"], "not": []},
    "name":         {"any": ["наименование", "название"], "not": ["ориг", "исход"]},
    "price":        {"any": ["цена продажи", "цена, ₽", "цена ₽", "розничная", "цена_ozon", "цена ozon"], "not": ["закуп", "сайт", "₽/шт"]},
    # ЗАКУПКА (живой урок 2026-08-08): себестоимость ЕСТЬ в выгрузке донора («Закупка SKU, ₽»), но
    # логического ключа под неё не было — колонка отбрасывалась как ценовой шум (она и правда не
    # характеристика товара). Итог: ЦЕНОВИК на КАЖДОЙ позиции говорил «закупка неизвестна → пол маржи
    # не посчитать» (P2) и цена не выставлялась. Ключ ровно тот, что читает pricer.price_decision: cost.
    "cost":         {"any": ["закупка", "закуп", "себестоим"], "not": ["логистик", "комисси"]},
    "description":  {"any": ["описание"], "not": []},
    "pictures":     {"any": ["фото без", "фото без вотермарка", "изображен"], "not": ["вотермарк fallback", "источник"]},
    "pictures_alt": {"any": ["вотермарк", "watermark", "fallback"], "not": ["источник"]},
    "availability": {"any": ["наличие"], "not": ["ручек", "кармана", "крышк"]},  # исключить характеристики товара
    "link":         {"any": ["ссылка", "url"], "not": ["фото"]},
    "photo_source": {"any": ["источник фото"], "not": []},
    "categories":   {"any": ["категории", "категория"], "not": []},
}
# Фаллбэк для артикула: если не найдено, ищем первую колонку с "наименование ориг" (исходное название поставщика)
COLUMN_MATCHERS_FALLBACK_SKU = {"any": ["наименование ориг", "название ориг"], "not": []}
# Служебные (ценовые/расчётные) колонки — НЕ считаем их «характеристиками» товара.
_NON_SPEC = {"sku", "name", "price", "cost", "description", "pictures", "pictures_alt",
             "availability", "link", "photo_source", "categories"}
_PRICE_NOISE = ["закупка", "логистика", "комиссия", "профит", "маржа", "цена на сайте",
                "себестоимость", "наценка", "цена, ₽/шт", "цена ₽/шт"]

_URL_RE = re.compile(r"https?://[^\s,;|]+")


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _lc(s):
    return _norm(s).lower().replace("ё", "е")


def map_columns(header):
    """header (list заголовков) → {логический_ключ: индекс}. Генерично, по смыслу. Неточно найдено → нет ключа."""
    idx = {}
    used = set()
    lchdr = [_lc(h) for h in header]
    for key, rule in COLUMN_MATCHERS.items():
        for i, h in enumerate(lchdr):
            if i in used or not h:
                continue
            if any(a in h for a in rule["any"]) and not any(b in h for b in rule["not"]):
                idx[key] = i
                used.add(i)
                break
    return idx


def spec_columns(header, colmap):
    """Все прочие колонки = характеристики: {индекс: человекочитаемое_имя}. Ценовой шум отбрасываем."""
    taken = set(colmap.values())
    out = {}
    for i, h in enumerate(header):
        if i in taken:
            continue
        lc = _lc(h)
        if not lc or any(n in lc for n in _PRICE_NOISE):
            continue
        out[i] = _norm(h)
    return out


# ── Извлечение характеристик пузырьковой плёнки из текста (честно: только что реально в тексте) ──

def _num(s):
    """'1,2' → 1.2 ; '50' → 50.0 ; мусор → None."""
    if s is None:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", str(s))
    return float(m.group(0).replace(",", ".")) if m else None


def extract_specs(text):
    """Из текста товара (имя+описание+характеристики) → {ширина_м,длина_м,плотность,слои,пузырёк_мм,материал}.

    ЧЕСТНОСТЬ: возвращаем только реально найденное. Единицы приводим к метрам/г-м²/мм/шт-слоёв.
    Никакой выдумки: нет паттерна — ключа нет.
    """
    t = " " + _norm(text).lower().replace("ё", "е") + " "
    spec = {}

    # ширина × длина: "1,2*50", "1.5×100", "0,4 x 25", допускаем 'м'/'метр' рядом
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[*x×хX]\s*(\d+(?:[.,]\d+)?)", t)
    if m:
        a, b = _num(m.group(1)), _num(m.group(2))
        # меньшее из двух — ширина рулона (обычно ≤1.6 м), большее — длина намотки (25/50/100)
        if a is not None and b is not None:
            w, l = (a, b) if a <= b else (b, a)
            spec["ширина_м"], spec["длина_м"] = w, l
    if "ширина_м" not in spec:
        mw = re.search(r"ширин\w*\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*(м|метр|см|mm|мм)?", t)
        if mw:
            val, unit = _num(mw.group(1)), (mw.group(2) or "м")
            if val is not None:
                spec["ширина_м"] = val / 100 if unit in ("см",) else val
    if "длина_м" not in spec:
        ml = re.search(r"(?:длин\w*|намотк\w*)\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*(м|метр)", t)
        if ml:
            v = _num(ml.group(1))
            if v is not None:
                spec["длина_м"] = v

    # плотность г/м²
    md = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:г\s*/?\s*м\s*[²2]|гр?\s*/?\s*м2|g/?m2)", t)
    if not md:
        md = re.search(r"плотност\w*\s*[:\-]?\s*(\d+(?:[.,]\d+)?)", t)
    if md:
        v = _num(md.group(1))
        if v is not None:
            spec["плотность_г_м2"] = v

    # слои: словоформа («двухслойный/трёхслойный/пятислойный») ИЛИ цифра («2 слоя», «3-слойная»).
    # ЧЕСТНОСТЬ: диапазон-совет «упаковать в 1–2 слоя» — НЕ спека товара, его игнорируем.
    _word_layers = {"одно": 1, "двух": 2, "дву": 2, "трех": 3, "четырех": 4, "пяти": 5, "шести": 6}
    mw = re.search(r"(одно|двух|дву|трех|четырех|пяти|шести)\s*сло", t)
    if mw:
        spec["слои"] = _word_layers[mw.group(1)]
    elif not re.search(r"\d\s*[–—-]\s*\d\s*сло", t):  # нет диапазона-совета → можно брать цифру
        mdgt = re.search(r"(\d)\s*[-]?\s*слой?[йяе]?", t)
        if mdgt:
            spec["слои"] = int(mdgt.group(1))

    # диаметр пузырька мм
    mb = re.search(r"пузыр\w*[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*мм", t)
    if not mb:
        mb = re.search(r"диаметр\w*\s*пузыр\w*\s*[:\-]?\s*(\d+(?:[.,]\d+)?)", t)
    if mb:
        v = _num(mb.group(1))
        if v is not None:
            spec["диаметр_пузырька_мм"] = v

    # материал
    if re.search(r"\bпвд\b", t):
        spec["материал"] = "ПВД (полиэтилен высокого давления)"
    elif re.search(r"\bпнд\b", t):
        spec["материал"] = "ПНД (полиэтилен низкого давления)"
    elif "полиэтилен" in t:
        spec["материал"] = "полиэтилен"

    return spec


# ── Названия параметров карточки (человекочитаемые ключи, которые сматчит parameter_values по имени) ──
# Кладём спеку в prod под НЕСКОЛЬКИМИ вероятными именами параметра Маркета — parameter_values()
# матчит по имени параметра из category_parameters(); лишние ключи безвредны, совпавшие — поднимают index.
_SPEC_TO_PARAM_NAMES = {
    "ширина_м":            ["Ширина рулона", "Ширина", "Ширина, м"],
    "длина_м":             ["Длина намотки", "Длина", "Длина рулона", "Длина, м"],
    "плотность_г_м2":      ["Плотность", "Плотность, г/м²", "Плотность плёнки"],
    "слои":                ["Количество слоёв", "Число слоёв", "Слои"],
    "диаметр_пузырька_мм": ["Диаметр пузырька", "Размер пузырька", "Диаметр пузырьков"],
    "материал":            ["Материал", "Материал изделия", "Состав"],
}
_SPEC_HUMAN = {
    "ширина_м": ("Ширина рулона", "м"),
    "длина_м": ("Длина намотки", "м"),
    "плотность_г_м2": ("Плотность", "г/м²"),
    "слои": ("Количество слоёв", ""),
    "диаметр_пузырька_мм": ("Диаметр пузырька", "мм"),
    "материал": ("Материал", ""),
}


def _fmt_spec_line(spec):
    """Человеческий спек-блок для дописывания в описание (заполненность = ТОП)."""
    parts = []
    for k, (label, unit) in _SPEC_HUMAN.items():
        if k in spec:
            v = spec[k]
            v = (int(v) if isinstance(v, float) and v.is_integer() else v)
            parts.append(f"{label}: {v}{(' ' + unit) if unit else ''}".strip())
    return " · ".join(parts)


def _spec_from_chars(chars):
    """Вытянуть спеку из готовых structured-колонок XLSX (надёжнее regex). Возвращает {ключ: значение}."""
    spec = {}
    for cname, cval in chars.items():
        cn = _lc(cname)
        v = _norm(cval)
        # ширина: ловушка единиц — «Ширина, мм» (курьер-пакет/скотч/коробка) НЕ метры.
        # Приводим к метрам по подписи колонки, иначе 230 мм станет 230 м и габариты улетят в мусор.
        if "ширин" in cn and "мм" in cn:
            w = _num(v)
            if w is not None:
                spec["ширина_м"] = w / 1000.0
        elif "ширин" in cn and "см" in cn:
            w = _num(v)
            if w is not None:
                spec["ширина_м"] = w / 100.0
        elif any(k in cn for k in ["ширина рулон", "ширина, м", "ширина"]):
            w = _num(v)
            if w is not None:
                spec["ширина_м"] = w
        # длина / намотка
        elif any(k in cn for k in ["намотк", "длина", "длина рулон"]):
            l = _num(v)
            if l is not None:
                spec["длина_м"] = l
        # плотность г/м²
        elif "плотност" in cn and ("г" in cn or "g" in cn):
            d = _num(v)
            if d is not None:
                spec["плотность_г_м2"] = d
        # диаметр пузырька
        elif "пузырьк" in cn or "пузырч" in cn:
            p = _num(v)
            if p is not None:
                spec["диаметр_пузырька_мм"] = p
        # кол-во слоёв
        elif "слой" in cn or "слоев" in cn:
            s = _num(v)
            if s is not None and 1 <= s <= 9:
                spec["слои"] = int(s)
        # материал
        elif "материал" in cn:
            if v:
                spec["материал"] = v
        # диаметр рулона/бобины (для расчёта габаритов упаковки): мм → м
        elif any(k in cn for k in ["диаметр рулон", "диаметр бобин"]):
            d = _num(v)
            if d is not None:
                if "мм" in cn:
                    spec["диаметр_рулона_м"] = d / 1000.0
                elif "см" in cn:
                    spec["диаметр_рулона_м"] = d / 100.0
                else:
                    spec["диаметр_рулона_м"] = d
    return spec


def _dims_from_chars(chars):
    """Габариты упаковки из строки вида '50*35*50' / '50х35х50 см' → [Д, Ш, В] в СМ. Иначе None.

    ГЕНЕРИЧНО: ищем колонку про размер/габарит УПАКОВКИ (не самого рулона) и три числа в ней.
    Честность: ровно три числа — иначе None (неполный weightDimensions API отклоняет).
    """
    for cname, cval in chars.items():
        cn = _lc(cname)
        if not any(k in cn for k in ["размер упаковки", "габарит", "д*ш*в", "дxшxв", "д х ш х в"]):
            continue
        nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", str(cval))]
        if len(nums) == 3 and all(n > 0 for n in nums):
            # если колонка в мм — приводим к см (Маркет ждёт см)
            if "мм" in cn and "см" not in cn:
                nums = [n / 10 for n in nums]
            return nums
    return None


def _derive_dims(spec):
    """Габариты упаковки (см) ВЫВЕДЕННЫЕ из физики рулона, когда готовой колонки нет.

    ЖИВОЙ УРОК (2026-08-05): Маркет требует длину/ширину/высоту + вес, иначе карточка встаёт
    NO_CARD_ERRORS («Не указаны габариты товара»). В выгрузке донора готовая колонка размеров
    была лишь у 1 товара из 24 — остальные 23 не публиковались.

    ЧЕСТНОСТЬ: это не выдумка, а расчёт из РЕАЛЬНЫХ размеров товара. Рулон едет как цилиндр:
      • длина коробки = ширина рулона (намотан по ширине), см = м×100
      • ширина = высота = диаметр рулона, см
    Диаметр берём из колонки, если есть; иначе — из транспортировочного объёма (V = Ш×Д×В),
    иначе из площади намотки и толщины (геометрия свёрнутого полотна). Нет ни одного источника
    → возвращаем None (карточка честно останется без габаритов, не врём).
    """
    w_m = spec.get("ширина_м")
    if not w_m or w_m <= 0:
        return None
    d_m = spec.get("диаметр_рулона_м")
    if not d_m or d_m <= 0:
        vol = spec.get("транспортный_объем_м3")
        if vol and vol > 0:
            # V = ширина × диаметр² → диаметр = sqrt(V / ширина)
            d_m = (vol / w_m) ** 0.5
    if not d_m or d_m <= 0:
        # свёрнутое полотно: V_плёнки = площадь × толщина; рулон занимает ~V/0.75 (рыхлость)
        area, th_mm = spec.get("площадь_м2"), spec.get("толщина_мм")
        if area and th_mm and area > 0 and th_mm > 0:
            v_film = area * (th_mm / 1000.0)          # м³ плёнки
            d_m = ((v_film / 0.75) / w_m * 4 / 3.14159) ** 0.5
    if not d_m or d_m <= 0:
        return None
    L = round(w_m * 100, 1)          # длина коробки = ширина рулона
    D = round(d_m * 100, 1)          # ширина = высота = диаметр
    if not (0 < L <= 300 and 0 < D <= 300):
        return None                  # неправдоподобно — лучше ничего, чем ложь
    return [L, D, D]


def _generic_from_chars(chars):
    """ОБЩЕТОВАРНЫЕ поля из structured-колонок (работают на ЛЮБОМ сайте, не только cargo-avto).

    Это часть МЕТОДА: бренд/страна/вес/габариты/цвет/толщина/штук-в-упаковке нужны почти каждой
    категории Маркета и сильно двигают contentRating. Честность прежняя: нет колонки — нет ключа.
    """
    g = {}
    for cname, cval in chars.items():
        cn = _lc(cname)
        v = _norm(cval)
        if not v:
            continue
        if "вес_кг" not in g and re.match(r"^вес\b", cn) and "кг" in cn:
            x = _num(v)
            if x is not None:
                g["вес_кг"] = x
        elif "вес_кг" not in g and re.match(r"^вес\b", cn) and ("гр" in cn or cn.endswith(", г")):
            x = _num(v)
            if x is not None:
                g["вес_кг"] = x / 1000
        elif "толщина_мм" not in g and "толщин" in cn:
            x = _num(v)
            if x is not None:
                g["толщина_мм"] = x / 1000 if "мкм" in cn else x
        elif "цвет" not in g and "цвет" in cn:
            g["цвет"] = v
        elif "бренд" not in g and any(k in cn for k in ["торговая марка", "бренд", "brand", "производитель"]) and "страна" not in cn:
            g["бренд"] = v
        elif "страна" not in g and "стран" in cn:
            g["страна"] = v
        elif "штук_в_упаковке" not in g and any(k in cn for k in ["кол-во в sku", "штук в упаковк", "единиц в упаковк", "кол-во в упаковк"]):
            x = _num(v)
            if x is not None and x >= 1:
                g["штук_в_упаковке"] = int(x)
        elif "площадь_м2" not in g and "площад" in cn:
            x = _num(v)
            if x is not None:
                g["площадь_м2"] = x
        elif "транспортный_объем_м3" not in g and "объем" in cn:
            x = _num(v)
            if x is not None:
                g["транспортный_объем_м3"] = x
    dims = _dims_from_chars(chars)
    if dims:
        g["габариты_упаковки_см"] = dims
    return g


def _merge_specs(primary, fallback):
    """Объединить две спеки: primary (из колонок) имеет приоритет над fallback (regex из текста)."""
    merged = dict(fallback)
    merged.update(primary)
    return merged


def own_card_fields(prod, house_brand="", platform="yandex_market"):
    """ОТВЯЗКА ОТ ЧУЖОЙ КАРТОЧКИ (путь А, решение оператора 2026-08-05).

    ЖИВОЙ УРОК: залитый оффер приклеился к готовой карточке Маркета (mapping.marketSku 6080814325).
    Пока действует склейка, покупателю показывают контент ТОЙ карточки — наши фото/описание/
    характеристики на витрину не попадают, а contentRating считается по чужому контенту. Отсюда
    «описание есть, но баллов нет».

    Главный ключ склейки у маркетплейсов — ШТРИХКОД. Свой валидный EAN-13 (префикс 2 = внутреннее
    обращение, не конфликтует с заводскими GTIN) + уникальное название разрывают привязку.
    Переиспользуем уже построенный орган uniqueizer_v1 (его приёмка T9/T10 зелёная), не дублируем.

    БРЕНД (эталон 99 баллов из живого кабинета): у карточки с рейтингом 99 стоит vendor="Без бренда"
    — это ЛЕГАЛЬНОЕ значение Маркета для товаров без торговой марки. Оно закрывает обязательное поле
    «Бренд» (без него NO_CARD_ERRORS) и при этом НЕ раскрывает поставщика и не склеивает карточки
    по бренду. Ровно то, что нужно дропшипу.

    ЗАКОН ЕДИНОГО ИСТОЧНИКА (2026-08-12): имя генерируем НЕ здесь. Ставим флаг unique_name=True — и
    уникальное НАИМЕНОВАНИЕ соберёт card.to_offer (вторичный рычаг склейки; главный — свой штрихкод
    ниже). Формулировка имени живёт в ОДНОМ месте (to_offer), не дублируется здесь. Способ to_offer —
    БЕЗ ПОТЕРЬ: имя товара 1-в-1 + house_brand суффиксом (размер/единицы не искажаются). Поэтому флаг
    безопасен и без бренда: house_brand не задан → добавлять нечего → имя остаётся дословным
    (name_source='verbatim_fallback'). «Без бренда» в имя НЕ пихаем — это квалификатор поля vendor,
    не заголовка; house_brand для заголовка кладём только если задан реальный бренд-дом.

    Возвращает поля-добавки к товару; пустой dict если орган недоступен (fail-soft).
    """
    try:
        import uniqueizer_v1 as uq
    except Exception:
        return {}
    sku = prod.get("sku") or prod.get("name")
    if not sku:
        return {}
    out = {"barcode": uq.gen_ean13(sku)}
    # Бренд обязателен для Маркета. Свой бренд-дом — если оператор задал; иначе «Без бренда».
    out["vendor"] = house_brand or "Без бренда"
    out["send_vendor"] = True
    # Уникальное имя разорвёт склейку по заголовку — но собирает его to_offer (единый источник).
    out["unique_name"] = True
    if house_brand:                       # реальный бренд-дом → отдаём его в квалификатор заголовка
        out["house_brand"] = house_brand
    return out


def verify_pictures(pictures, sku, name="", source_ok=False):
    """ВРАТАРЬ ФОТО: пропустить только те URL, что ДОКАЗАННО принадлежат этому товару.

    ЖИВОЙ УРОК (2026-08-05): 8 товаров из 24 получили один файл `1.webp` — заглушку парсера.
    Оставшиеся могли быть взяты с WB/Ozon, где артикул зашит в путь (`/vol8411/part841143/841143054/`),
    а не в имя файла — такие фото ВАЛИДНЫ, если номенклатура записана в «Источник фото».

    ДОКАЗАТЕЛЬСТВО принадлежности = хотя бы одна идентифицирующая цифра товара в URL:
      • SKU cargo-avto (9602037) — главный артикул;
      • номенклатура маркетплейса из колонки «Источник фото» (841143054 для WB).

    Нет ни одного доказательства → фото НЕ шлём. Лучше карточка без фото, чем с чужим.

    Возвращает (verified, rejected) — оба списка, чтобы вызывающий честно отчитался о потере.
    """
    base = str(sku or "").split("-")[0].strip()
    verified, rejected = [], []
    # ЖИВОЙ УРОК-2 (2026-08-05): фото донора с WB/Ozon имеют порядковые имена (1.webp, 2.webp),
    # но это НАСТОЯЩИЕ фото товара — если подпись «Источник фото» описывает ТОТ ЖЕ товар.
    # Формальный запрет по имени файла отбраковывал годные снимки (8 товаров остались без фото).
    # Поэтому: имя файла — не приговор; приговор выносит сверка размеров (photo_source_matches),
    # которую вызывает row_to_prod вторым рубежом.
    for u in (pictures or []):
        if base and base in str(u):
            verified.append(u)          # родное фото поставщика — сильнейшее доказательство
            continue
        if source_ok:
            verified.append(u)          # фото донора, размеры товара сверены и совпали
            continue
        rejected.append({"url": u, "why": "нет доказательства принадлежности (ни артикул, ни сверка источника)"})
    return verified, rejected


def _dims_fingerprint(text):
    """Отпечаток товара по размерам из названия: {0.3, 100} для «Плёнка 0.3×100 м».

    Нужен, чтобы поймать промах подбора фото по названию: парсер брал с WB карточку с ПОХОЖИМ
    названием, но другими размерами (товар «Плёнка 0.3×100 м» получил фото «Пакет 0,15*21 см»).
    Размеры — самый надёжный различитель в упаковке.
    """
    t = _norm(text).lower().replace(",", ".")
    nums = set()
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*[*x×х]\s*(\d+(?:\.\d+)?)", t):
        nums.add(float(m.group(1)))
        nums.add(float(m.group(2)))
    return nums


def photo_source_matches(product_name, photo_source):
    """Совпадает ли товар с тем, что реально на фото (по подписи «Источник фото»)?

    Возвращает (ok, why). Пустой источник → (True, 'родное фото') — проверять нечего.
    Разные размеры → (False, ...) = фото ЧУЖОГО товара, не шлём.
    """
    src = _norm(photo_source)
    if not src:
        return True, "родное фото (источник не указан)"
    if ":" not in src:
        return True, "источник без названия — не проверить"
    donor_title = src.split(":", 1)[1]
    a, b = _dims_fingerprint(product_name), _dims_fingerprint(donor_title)
    if not a or not b:
        return True, "размеры не сравнить (нет габаритов в названии)"
    if a & b:
        return True, f"размеры совпали {sorted(a & b)}"
    return False, f"ЧУЖОЙ товар: у нас {sorted(a)}, на фото {sorted(b)} — «{donor_title[:45]}»"


def resolve_sku(sku_cell, link):
    """Артикул строки: заявленный в выгрузке, иначе выведенный из ссылки. '' если не выводится.

    ВАЖНО: чужой сайт может дать id, совпадающий с артикулом другого поставщика, а offerId
    обязан быть уникален по всему бизнесу — иначе заливка МОЛЧА перезапишет чужой товар.
    Поэтому выведенный (не заявленный в выгрузке) артикул всегда привязываем к домену источника.
    """
    sku = _norm(sku_cell)
    if sku:
        return sku
    link = _norm(link)
    if not link:
        return ""
    m = re.search(r"[?&]id=(\d+)", link)
    raw_id = m.group(1) if m else None
    if not raw_id:
        parts = re.findall(r"/(\d+)", link)
        raw_id = parts[-1] if parts else None
    if not raw_id:
        return ""
    host = re.sub(r"^https?://(www\.)?", "", link).split("/")[0]
    label = re.sub(r"[^a-z0-9]+", "", host.split(".")[0].lower())
    return f"{label}-{raw_id}" if label else raw_id


def diagnose_row(row, colmap):
    """Почему строка НЕ стала товаром. None если строка валидна. Для честного отчёта оператору.

    ЗАКОН: молчаливый ноль — худший отказ. Новый сайт должен падать с ИМЕНЕМ причины,
    а не с пустым результатом.
    """
    def cell(key):
        i = colmap.get(key)
        return row[i] if (i is not None and i < len(row)) else None

    if not any(_norm(c) for c in row):
        return "пустая строка"
    name = _norm(cell("name"))
    price = _num(cell("price"))
    sku = resolve_sku(cell("sku"), cell("link"))
    missing = []
    if not sku:
        missing.append("артикул (нет колонки и не выводится из ссылки)")
    if not name:
        missing.append("наименование")
    if price is None:
        missing.append("цена продажи")
    elif price <= 0:
        missing.append(f"цена продажи ({price} ≤ 0)")
    return "нет: " + ", ".join(missing) if missing else None


def row_to_prod(row, colmap, speccols, slug=None, vendor=None):
    """Одна строка XLSX → нормализованный товар для ymarket_card_v1. None если нет sku/имени/цены.

    Обогащение: парсим спеку из имени+описания+всех характеристик → кладём в prod под именами
    параметров (для offer-cards) и дописываем спек-блок в описание (для contentRating).
    """
    def cell(key):
        i = colmap.get(key)
        return row[i] if (i is not None and i < len(row)) else None

    name = _norm(cell("name"))
    price = _num(cell("price"))
    link = _norm(cell("link"))
    sku = resolve_sku(cell("sku"), link)

    if not sku or not name or not price or price <= 0:
        return None

    desc = _norm(cell("description"))
    pics_raw = "{} {}".format(_norm(cell("pictures")), _norm(cell("pictures_alt")) if not _norm(cell("pictures")) else "")
    pictures = _URL_RE.findall(pics_raw)
    # характеристики строки (как есть) — и для спек-парсинга, и как отдельные поля товара
    chars = {}
    for i, hname in speccols.items():
        v = _norm(row[i]) if i < len(row) else ""
        if v:
            chars[hname] = v

    # текст для извлечения спеки = имя + описание + все характеристики
    blob = " | ".join([name, desc] + [f"{k}: {v}" for k, v in chars.items()])
    spec = _merge_specs(_spec_from_chars(chars), extract_specs(blob))
    # общетоварные поля (бренд/страна/вес/габариты/цвет/толщина) — ключи не пересекаются с категорийными
    spec.update(_generic_from_chars(chars))

    prod = {
        "sku": sku,
        "name": name,
        "price": price,
        "description": desc,
        "slug": slug,
        "availability": _norm(cell("availability")),
        "link": _norm(cell("link")),
        "photo_source": _norm(cell("photo_source")),
        "_chars": chars,
        "_spec": spec,
    }
    # ЗАКУПКА → ключ cost (его читает ЦЕНОВИК: pricer.price_decision → margin_floor).
    # Честность: колонки нет или значение не число → ключ НЕ ставим. Роль тогда честно скажет
    # «закупка неизвестна», а не посчитает пол маржи от выдуманного нуля.
    _cost = _num(cell("cost"))
    if _cost is not None and _cost > 0:
        prod["cost"] = _cost
    # ФОТО: сначала сверяем ИСТОЧНИК (тот ли это товар по размерам), потом пропускаем URL.
    src_ok, src_why = photo_source_matches(name, _norm(cell("photo_source")))
    verified, rejected = verify_pictures(pictures, sku, name, source_ok=src_ok)
    if not src_ok and verified:
        rejected += [{"url": u, "why": src_why} for u in verified]
        verified = []
    prod["pictures"] = verified
    if rejected:
        prod["_photos_rejected"] = rejected  # вызывающий решит, доложить ли оператору
    if vendor:
        prod["vendor"] = vendor
    # ПУТЬ А (решение оператора 2026-08-05): бренд ПОСТАВЩИКА из выгрузки НЕ подставляем —
    # он склеивает нашу карточку с чужой (mapping.marketSku) и отдаёт витрину чужому контенту.
    # Бренд-дом оператора, если он есть, приходит параметром vendor выше.
    # ОТВЯЗКА: свой EAN-13 — главный ключ, разрывающий склейку.
    prod.update(own_card_fields(prod, house_brand=vendor or ""))
    if spec.get("страна"):
        prod["manufacturerCountries"] = [spec["страна"]]
    # weightDimensions: Маркет требует ВСЕ четыре (см/кг) — шлём только полный набор (закон честности)
    _dims, _wkg = spec.get("габариты_упаковки_см"), spec.get("вес_кг")
    if not _dims:
        _dims = _derive_dims(spec)   # готовой колонки нет → считаем из физики рулона
        if _dims:
            spec["габариты_упаковки_см"] = _dims
    if _dims and _wkg:
        prod["weightDimensions"] = {"length": _dims[0], "width": _dims[1],
                                    "height": _dims[2], "weight": _wkg}
        # ЕДИНЫЙ ДИАЛЕКТ ГАБАРИТОВ (живой урок 2026-08-07). Карточка (ymarket_card._weight_dimensions)
        # читает ВЛОЖЕННЫЙ weightDimensions, а роли цеха — ПЛОСКИЕ ключи: ТОВАРОВЕД (_dims/fits_city/
        # delivery_cost) и ЦЕНОВИК (decide_batch → calc_tariffs). Раньше загрузчик клал только вложенный
        # вид → роли видели None → отбивали ВЕСЬ каталог как needs_data при полных данных.
        # Кладём ОБА вида. Безопасно: наружу уходит белый список to_offer (плоские ключи не текут в API),
        # а категорийные параметры матчатся по РУССКИМ именам — с length/width/height/weight не столкнутся.
        prod["length"], prod["width"], prod["height"] = _dims[0], _dims[1], _dims[2]
        prod["weight"] = _wkg
    # спеку — под вероятными именами параметров (parameter_values сматчит по имени с реальной категорией)
    for skey, val in spec.items():
        for pname in _SPEC_TO_PARAM_NAMES.get(skey, []):
            prod.setdefault(pname, val if not isinstance(val, float) or not val.is_integer() else int(val))
    # пробрасываем исходные характеристики тоже (вдруг имя параметра Маркета совпадёт напрямую)
    for k, v in chars.items():
        prod.setdefault(k, v)

    # ОПИСАНИЕ по эталону 99 баллов: развёрнутый HTML вместо короткого текста (баллы за описание).
    rich = build_rich_description(name, desc, spec, chars)
    if rich and len(rich) > len(desc or ""):
        prod["description"] = rich[:3000]
    else:
        specline = _fmt_spec_line(spec)
        if specline and specline.split(" · ")[0].split(":")[0] not in desc:
            prod["description"] = (desc + ("\n\nХарактеристики: " if desc else "Характеристики: ") + specline).strip()

    return prod


def build_rich_description(name, base_desc, spec, chars):
    """Развёрнутое HTML-описание по ЭТАЛОНУ 99 баллов из живого кабинета.

    ЖИВОЙ УРОК (2026-08-05): карточка с contentRating=99 имеет описание 1466 символов В HTML
    (<p>-абзацы), а наше было 469 символов простым текстом → баллы за описание не начислялись.
    Формула эталона: вводный абзац «что это и для чего» → абзац с размерами/материалом →
    абзац применения → список характеристик.

    ЧЕСТНОСТЬ: ни одного придуманного факта. Все числа берутся из spec/chars (реальные колонки
    выгрузки). Нет данных — предложение просто не пишется.
    """
    sp = spec or {}
    parts = []

    w, l = sp.get("ширина_м"), sp.get("длина_м")
    dens, layers = sp.get("плотность_г_м2"), sp.get("слои")
    bubble, mat = sp.get("диаметр_пузырька_мм"), sp.get("материал")
    area, weight = sp.get("площадь_м2"), sp.get("вес_кг")

    def _n(x):
        return int(x) if isinstance(x, float) and x.is_integer() else x

    # 1) вводный абзац — суть товара
    # ВАЖНО: режем по «. » (точка+пробел), а не по точке — иначе «0.3 м» рвётся на «0.»
    lead = ""
    if base_desc:
        bd = _norm(base_desc)
        m = re.search(r"\.\s", bd)
        lead = bd[:m.start()] if m else bd
    intro = lead if lead else _norm(name)
    if w and l:
        intro += f". Размер полотна — {_n(w)} м в ширину и {_n(l)} м в длину"
        if area:
            intro += f", общая площадь {_n(area)} м²"
    parts.append(f"<p>{intro}.</p>")

    # 2) конструкция и материал
    tech = []
    if layers:
        tech.append(f"{_n(layers)}-слойная структура")
    if bubble:
        tech.append(f"воздушные пузырьки диаметром {_n(bubble)} мм")
    if dens:
        tech.append(f"плотность {_n(dens)} г/м²")
    if mat:
        tech.append(f"материал — {str(mat).lower()}")
    if tech:
        parts.append("<p>Характеристики материала: " + ", ".join(tech) +
                     ". Пузырьки гасят удары и вибрацию при транспортировке, "
                     "защищая содержимое от повреждений.</p>")

    # 3) применение
    parts.append("<p>Подходит для упаковки товаров при отправке в маркетплейсы, "
                 "почтовых пересылок, переездов и хранения. Используется для обёртывания "
                 "хрупких предметов, заполнения пустот в коробках и защиты поверхностей "
                 "от царапин.</p>")

    # 4) список фактов
    facts = []
    if w:
        facts.append(f"<li>Ширина рулона: {_n(w)} м</li>")
    if l:
        facts.append(f"<li>Длина намотки: {_n(l)} м</li>")
    if dens:
        facts.append(f"<li>Плотность: {_n(dens)} г/м²</li>")
    if layers:
        facts.append(f"<li>Количество слоёв: {_n(layers)}</li>")
    if bubble:
        facts.append(f"<li>Диаметр пузырька: {_n(bubble)} мм</li>")
    if mat:
        facts.append(f"<li>Материал: {mat}</li>")
    if area:
        facts.append(f"<li>Площадь рулона: {_n(area)} м²</li>")
    if weight:
        facts.append(f"<li>Вес: {_n(weight)} кг</li>")
    if sp.get("цвет"):
        facts.append(f"<li>Цвет: {sp['цвет']}</li>")
    if sp.get("страна"):
        facts.append(f"<li>Страна производства: {sp['страна']}</li>")
    if facts:
        parts.append("<p>Технические характеристики:</p><ul>" + "".join(facts) + "</ul>")

    return "".join(parts)


def load_category(xlsx_path, slug=None, vendor=None, sheet=None):
    """XLSX категории → список нормализованных товаров (+ отчёт о разборе). Fail-soft.

    Возвращает {'products':[...], 'colmap':..., 'spec_columns':[...], 'skipped':N, 'file':...}.
    """
    try:
        import openpyxl
    except Exception as e:
        raise RuntimeError(f"openpyxl не установлен ({e}); мост XLSX недоступен")
    wb = openpyxl.load_workbook(str(xlsx_path), read_only=True, data_only=True)
    ws = None
    if sheet:
        ws = wb[sheet] if sheet in wb.sheetnames else None
    if ws is None:
        # предпочитаем лист с «товар»/«sku» в имени, иначе первый
        for name in wb.sheetnames:
            if "товар" in _lc(name) or "sku" in _lc(name):
                ws = wb[name]
                break
        ws = ws or wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {"products": [], "colmap": {}, "spec_columns": [], "skipped": 0,
                "file": str(xlsx_path), "sheet": ws.title, "header": []}
    header = [_norm(h) for h in rows[0]]
    colmap = map_columns(header)
    speccols = spec_columns(header, colmap)
    prods, skipped = [], 0
    skip_reasons = {}
    for rn, r in enumerate(rows[1:], start=2):
        p = row_to_prod(r, colmap, speccols, slug=slug, vendor=vendor)
        if p:
            prods.append(p)
        else:
            skipped += 1
            why = diagnose_row(r, colmap) or "неизвестно"
            slot = skip_reasons.setdefault(why, {"строк": 0, "примеры": []})
            slot["строк"] += 1
            if len(slot["примеры"]) < 3:
                slot["примеры"].append(rn)
    # ЗАКОН ЧЕСТНОСТИ: если не разобрано НИ ОДНОЙ строки — это отказ с именем, а не пустой результат
    blocker = None
    if not prods:
        need = [k for k in ("sku", "name", "price") if k not in colmap]
        if need:
            human = {"sku": "артикул", "name": "наименование", "price": "цена продажи"}
            blocker = ("НЕ РАСПОЗНАНЫ ОБЯЗАТЕЛЬНЫЕ КОЛОНКИ: "
                       + ", ".join(human[k] for k in need)
                       + f". Заголовок листа «{ws.title}»: {header}")
        elif skip_reasons:
            blocker = "ВСЕ строки отбракованы: " + "; ".join(
                f"{w} ({d['строк']} стр.)" for w, d in skip_reasons.items())
        else:
            blocker = f"Лист «{ws.title}» не содержит строк данных"
    return {
        "products": prods,
        "colmap": {k: header[v] for k, v in colmap.items()},
        "spec_columns": [header[i] for i in speccols],
        "skipped": skipped,
        "skip_reasons": skip_reasons,
        "blocker": blocker,
        "file": str(xlsx_path),
        "sheet": ws.title,
        "header": header,
    }


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Мост XLSX-выгрузка → товары Яндекс.Маркета (чистое чтение, 0₽)")
    ap.add_argument("xlsx", help="путь к XLSX категории (выгрузка парсера)")
    ap.add_argument("--slug", default=None, help="slug категории (для маппинга marketCategoryId)")
    ap.add_argument("--vendor", default=None, help="бренд/производитель (если у оператора есть — заполнит vendor)")
    ap.add_argument("--limit", type=int, default=5, help="сколько товаров показать")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    rep = load_category(args.xlsx, slug=args.slug, vendor=args.vendor)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0
    print(f"📄 {Path(rep['file']).name}  лист='{rep['sheet']}'")
    print(f"   колонки-смысл: {rep['colmap']}")
    print(f"   характеристик-колонок: {len(rep['spec_columns'])}")
    print(f"   товаров разобрано: {len(rep['products'])}  (пропущено строк: {rep['skipped']})")
    for p in rep["products"][:args.limit]:
        specs = p.get("_spec", {})
        print(f"\n   • {p['sku']}  {p['name'][:70]}")
        print(f"     цена={p['price']}  фото={len(p['pictures'])}  спека={specs}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

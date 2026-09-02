#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОВХ-СЛОЙ ГАБАРИТОВ ПОСЫЛКИ (ymarket_ovh_dims_v1) — карточка донора → габариты упаковки для ЯМ.

ЗАЧЕМ. Живой листинг cargo-avto несёт только dims_raw РУЛОНА («50*0.3 м» — ширина×намотка), а Экспрессу
нужны ГАБАРИТЫ ПОСЫЛКИ (Д×Ш×В, см) + вес — иначе ТОВАРОВЕД честно роняет позицию в needs_data (T5) и
партия не собирается (живой замер 2026-09-01: 24 кандидата ждут данных, 0 собрано). Этот слой закрывает
ровно этот разрыв: тянет карточку донора (1 GET, 0₽) и читает оттуда готовый блок характеристик —
«Размер упаковки Д*Ш*В, см», «Вес, кг», спеку (ширина/намотка/плотность/слои/материал/толщина/площадь).

ИЕРАРХИЯ ЧЕСТНОСТИ (не выдумываем, закон L3):
  1. card.dims   — готовый «Размер упаковки Д*Ш*В, см» → [Д,Ш,В] СМ напрямую (лучший источник; живой
     пример 9602037: «50*35*50» = коробка-диспенсер, НЕ рулон).
  2. card.weight — «Вес, кг» → вес. Вес НЕ оцениваем: нет колонки → нет веса (честно останется T5).
  3. physics     — «Размер упаковки» нет → оценка коробки рулона как цилиндра: длина = ширина рулона,
     ширина = высота = диаметр. Диаметр: транспортный объём (V = Ш×Д²) → площадь×толщина (геометрия
     полотна; та же математика, что _derive_dims в [[ymarket_from_xlsx_v1]]). Ни одного источника →
     None (карточка честно останется без габаритов, не врём).
Провенанс: dims_source='card'|'physics', weight_source='донор:карточка'. Всё насквозь (row → сводка →
отчёт): карточка никогда не уедет в залив на «наверное влезет».

ГЕРМЕТИЧНОСТЬ: stdlib-only (re/time/urllib). parse/dims-функции — чистые; сеть только в fetch_card
(fail-soft: любая беда → '' → свойств нет → позиция честно остаётся needs_data, не краш). Бюджет
enrich_products: обогащаем, пока не выйдет budget секунд — не успевшие честно ждут следующего дня
(донор не держит сутки). Свой слой: source-файлы донора (cargo_avto/donor_stock) НЕ редактируем.
"""
import re
import time
import urllib.request

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126 Safari/537.36")

# Блок характеристик карточки донора (Bitrix): имя закрыто </span>, значение — в соседнем <div>.
# Живой пример 9602037 дал все 15 свойств этим регексом (2026-09-01).
_PROP_RE = re.compile(
    r'properties-group__name">(.*?)</span>.*?properties-group__value[^>]*>(.*?)</div>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _clean(frag):
    """HTML-фрагмент → плоский текст (теги в пробелы, схлопнутые пробелы, без хвостовой пунктуации)."""
    txt = _TAG_RE.sub(" ", frag or "")
    return re.sub(r"\s+", " ", txt).strip(" :\t")


def _nums(s):
    """Все положительные числа из строки (до 3 первых), ',' → '.'. Пусто → []."""
    out = []
    for m in _NUM_RE.findall(str(s or "")):
        try:
            f = float(m.replace(",", "."))
        except ValueError:
            continue
        if f > 0:
            out.append(f)
    return out[:3]


def _find(props, *needles):
    """Первое свойство, в имени которого есть хоть одна игла (нижний регистр). (name, value) | (None, None)."""
    if not props:
        return None, None
    for n, v in props.items():
        ln = n.lower()
        if any(x in ln for x in needles):
            return n, v
    return None, None


def parse_card_properties(html):
    """Блок характеристик карточки → {Имя: Значение}. Пустой HTML → {} (fail-soft, не краш).

    Дубли по имени отбрасываем (первое вхождение). Имена без хвостового ':' — для чистого матча.
    """
    if not html:
        return {}
    out = {}
    for name, val in _PROP_RE.findall(html):
        n = _clean(name)
        v = _clean(val)
        if n and v and n not in out:
            out[n] = v
    return out


def dims_from_card(props):
    """Готовый «Размер упаковки Д*Ш*В, см» → [Д,Ш,В] СМ или None (нет колонки / не числа).

    Порядок — как написано у донора (Д×Ш×В). Колонка в мм → см (Маркет ждёт см).
    """
    name, val = _find(props, "размер упаковки", "д*ш*в", "габариты упаковки", "габарит")
    if not val:
        return None
    nums = _nums(val)
    if len(nums) != 3:
        return None
    if "мм" in (name or "").lower() and "см" not in (name or "").lower():
        nums = [round(n / 10, 1) for n in nums]
    return nums


def weight_from_card(props):
    """«Вес, кг» → (кг, 'донор:карточка'). Нет колонки → (None, None): вес НЕ оцениваем (T5 честно)."""
    name, val = _find(props, "вес")
    if not val:
        return None, None
    nums = _nums(val)
    if not nums:
        return None, None
    kg = nums[0]
    if "г" in (name or "").lower() and "кг" not in (name or "").lower():
        kg = kg / 1000.0
    return round(kg, 4), "донор:карточка"


def spec_from_card(props):
    """Карточка → _spec ключами ТОГО ЖЕ словаря, что from_xlsx (_SPEC_TO_PARAM_NAMES / _derive_dims):

    ширина_м / длина_м / плотность_г_м2 / слои / диаметр_пузырька_мм / материал — под parameter_values;
    толщина_мм / площадь_м2 / транспортный_объем_м3 / вес_кг — под оценку физики и свободный текст.
    Нет свойства → нет ключа (не выдумываем).
    """
    if not props:
        return {}
    spec = {}

    def n1(*needles):
        _, val = _find(props, *needles)
        nums = _nums(val)
        return nums[0] if nums else None

    w = n1("ширина рулона")
    if w:
        spec["ширина_м"] = round(w, 3)
    l = n1("намотка", "длина намотки")
    if l:
        spec["длина_м"] = round(l, 3)
    d = n1("плотность")
    if d:
        spec["плотность_г_м2"] = round(d, 2)
    layers = n1("кол-во слоев", "кол-во слоёв", "число слоёв", "число слоев", "слоев", "слоёв")
    if layers:
        spec["слои"] = int(layers)
    bub = n1("диаметр пузырька")
    if bub:
        spec["диаметр_пузырька_мм"] = round(bub, 1)
    _, material = _find(props, "материал")
    if material:
        spec["материал"] = material
    th_name, th_val = _find(props, "толщина")
    if th_val:
        th = _nums(th_val)[0]
        # Донор пишет «Общая толщина пленки, мм» (живой пример 9602037), но бывают «мкм» —
        # не выдаём микроны за миллиметры (иначе оценка диаметра станет ложью в опасную сторону).
        if "мкм" in (th_name or "").lower() and "мм" not in (th_name or "").lower():
            th = th / 1000.0
        spec["толщина_мм"] = round(th, 4)
    area = n1("площадь рулона")
    if area:
        spec["площадь_м2"] = round(area, 3)
    vol = n1("транспортировочный объем", "транспортный объем")
    if vol:
        spec["транспортный_объем_м3"] = round(vol, 4)
    kg, _ = weight_from_card(props)
    if kg:
        spec["вес_кг"] = kg
    return spec


def dims_from_physics(spec):
    """Оценка коробки рулона из физики, когда готового «Размер упаковки» нет. Зеркало _derive_dims.

    Длина коробки = ширина рулона (см); ширина = высота = диаметр. Диаметр: транспортный объём
    (V = Ш×Д²) → площадь×толщина (полотно, рыхлость 0.75). Нет ни одного источника → None (не выдумываем).
    Провенанс dims_source='physics' — оператор видит, что это ОЦЕНКА, а не факт карточки.
    """
    w_m = spec.get("ширина_м")
    if not w_m or w_m <= 0:
        return None
    d_m = spec.get("диаметр_рулона_м")
    if not d_m or d_m <= 0:
        vol = spec.get("транспортный_объем_м3")
        if vol and vol > 0:
            d_m = (vol / w_m) ** 0.5
    if not d_m or d_m <= 0:
        area, th_mm = spec.get("площадь_м2"), spec.get("толщина_мм")
        if area and th_mm and area > 0 and th_mm > 0:
            v_film = area * (th_mm / 1000.0)
            d_m = ((v_film / 0.75) / w_m * 4 / 3.14159) ** 0.5
    if not d_m or d_m <= 0:
        return None
    L = round(w_m * 100, 1)
    D = round(d_m * 100, 1)
    if not (0 < L <= 300 and 0 < D <= 300):
        return None                     # неправдоподобно — лучше ничего, чем ложь
    return [L, D, D]


def enrich(product, props):
    """Проставить продукту flat-габариты/вес/_spec из карточки. Меняет product, возвращает его.

    Правило честности: карточка не выдумывает. Нет свойства → нет ключа → ТОВАРОВЕД честно оставит
    needs_data (T5), а не «наверное влезет». dims_source говорит, ФАКТ или ОЦЕНКА.
    """
    dims = dims_from_card(props)
    source = "card" if dims else None
    if dims is None:
        spec = spec_from_card(props)
        dims = dims_from_physics(spec)
        source = "physics" if dims else None
    if dims:
        product["length"], product["width"], product["height"] = dims
        product["dims_source"] = source
    kg, ws = weight_from_card(props)
    if kg:
        product["weight"] = kg
        product["weight_source"] = ws
    spec = spec_from_card(props)
    if spec:
        product["_spec"] = spec
    return product


def fetch_card(url, timeout=20):
    """HTML карточки донора. fail-soft: любая беда → '' (→ свойств нет → позиция честно без габаритов)."""
    if not url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
    except Exception:                    # noqa: BLE001 — сеть/донор легли: не крашим сутки
        return ""


def enrich_products(products, budget=120, fetch=None, only_where=None):
    """Обогатить партию карточками донора: габариты посылки/вес/_spec (GET, 0₽, бюджет seconds).

    fetch   — шов для тестов (по умолчанию fetch_card, fail-soft).
    only_where — предикат «обогащать ли продукт» (по умолчанию: есть живой url и dims_raw).
    Бюджет — ВРЕМЯ, а не штуки: медленный донор не держит сутки; не успевшие остаются как есть
    (честно ждут следующего дня). Никогда не бросает исключение (беду не проглатываем: сеть сама
    fail-soft, остальное честно всплывёт в _safe суточного цикла).
    """
    fetch = fetch if fetch is not None else fetch_card
    pred = only_where or (lambda p: bool(p.get("url") and p.get("dims_raw")))
    t0 = time.monotonic()
    for p in products:
        if not pred(p):
            continue
        if time.monotonic() - t0 > budget:
            break
        enrich(p, parse_card_properties(fetch(p["url"])))
    return products


if __name__ == "__main__":               # быстрый живой зонд: python3 ymarket_ovh_dims_v1.py <article-url>
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://shop.cargo-avto.ru/catalog/9602037/"
    html = fetch_card(url)
    props = parse_card_properties(html)
    print(f"ОВХ-карточка {url}: {len(props)} свойств")
    for k, v in props.items():
        print(f"  {k} = {v}")
    spec = spec_from_card(props)
    print(f"\n_dims card = {dims_from_card(props)}  (dims_source='card')")
    print(f"weight      = {weight_from_card(props)}")
    print(f"_spec       = {spec}")
    print(f"_dims physics = {dims_from_physics(spec)}  (dims_source='physics', если 'Размер упаковки' нет)")

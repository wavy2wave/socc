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
  2. card.weight — «Вес, кг» карточки → вес. Нет колонки → вес ИЗ НАЗВАНИЯ товара («…, 2 кг, …» — донор
     сам пишет вес рулона в названии; провенанс 'донор:название'). Ни там, ни там → вес НЕ оцениваем
     (честно останется T5).
  3. physics     — «Размер упаковки» нет → посылка БЕЗ КОРОБКИ (решение оператора 04.09: рулон в
     сложенном виде = сам цилиндр, не коробка): длина = ширина рулона, ширина = высота = ДИАМЕТР
     цилиндра. Ширина — из карточки «Ширина, мм» (единица-осознанно) ИЛИ ИЗ НАЗВАНИЯ («…, 500 мм, …» —
     директива оператора «ширина в названии»). Диаметр = √(4V/(πL)) из «Транспортировочный объем, м³»
     (объём САМОГО рулона); нет объёма → площадь×толщина полотна (рыхлость 0.75), круг та же формула.
     Ни одного источника → None (карточка честно останется без габаритов, не врём).
  4. cache       — СБОЙНЫЙ GET (сеть/донор легли, '' вместо HTML) → последние-известные габариты ТОЙ ЖЕ
     карточки (реальные, прочитаны ранее с донора, runtime/ovh_dims_cache.json). Это НЕ выдумка — ровно
     то, что донор сам отдавал; провенанс dims_source сохранён, продукт помечен dims_cached+ts (видно
     «кэш», а не свежий факт). TTL 14 суток → не вечный сталь: первый успешный живой GET перезаписывает.
     Живой пример-флап 2026-09-03: у atlas-express-film СБОРКА сухо упала на ARB-53416854 («карточки
     БЕЗ ОВХ-габаритов») из-за одноразового пустого ответа донора, следующий прогон через 3 мин — PASS.
     Кэш закрывает ровно это: сухой цикл не умирает на транзиентном чтении донора (решение оператора:
     «чтобы карточка прошла, запомним, потом поменяет» — TTL и есть «потом»).
Провенанс: dims_source='card'|'physics', weight_source='донор:карточка'|'донор:название'; dims_cached=True — значение из
кэша. Всё насквозь (row → сводка → отчёт): карточка никогда не уедет в залив на «наверное влезет».

ГЕРМЕТИЧНОСТЬ: stdlib-only (re/time/urllib). parse/dims-функции — чистые; сеть только в fetch_card
(fail-soft: любая беда → '' → свойств нет → позиция честно остаётся needs_data, не краш). Бюджет
enrich_products: обогащаем, пока не выйдет budget секунд — не успевшие честно ждут следующего дня
(донор не держит сутки). Кэш пишем атомарно (tmp→replace), любой сбой чтения/записи кэша fail-soft
(слой не падает из-за файла). Свой слой: source-файлы донора (cargo_avto/donor_stock) НЕ редактируем.
"""
import json
import pathlib
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


# ── Ширина и вес ИЗ НАЗВАНИЯ товара (директива оператора 04.09 «ширина в названии») ────────────────
# У плёночных рулонов донор пишет в названии «…, 500 мм, 20 мкм, 2 кг, 1 сорт»: первый токен «N мм» —
# ШИРИНА рулона, «N кг» — вес рулона. Это официальные данные донора (второй источник после карточки,
# НЕ выдумка; провенанс помечается 'донор:название'). «мкм» не ловится (там нет подстроки «мм»), толщину
# вроде «0.02 мм» lookbehind/разрядность не пускают, «кг/м²»-плотность — lookahead.
_NAME_W_MM_RE = re.compile(r"(?<![\d.,])(\d{2,4}(?:[.,]\d+)?)\s*мм")       # «500 мм»
_NAME_KG_RE = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*кг(?![\/\w])")    # «2 кг» (не «2 кг/м²»)
_NAME_W_MIN_MM, _NAME_W_MAX_MM = 50, 3000          # правдоподобная ширина рулона, иначе не рулон


def width_m_from_name(name):
    """Ширина рулона ИЗ НАЗВАНИЯ («…, 500 мм, …») → метры | None."""
    if not name:
        return None
    m = _NAME_W_MM_RE.search(name)
    if not m:
        return None
    mm = float(m.group(1).replace(",", "."))
    if not (_NAME_W_MIN_MM <= mm <= _NAME_W_MAX_MM):
        return None
    return round(mm / 1000.0, 4)


def weight_kg_from_name(name):
    """Вес ИЗ НАЗВАНИЯ («…, 2 кг, …») → кг | None. Фолбэк к «Вес, кг» карточки."""
    if not name:
        return None
    m = _NAME_KG_RE.search(name)
    if not m:
        return None
    return round(float(m.group(1).replace(",", ".")), 4)


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

    # Ширина рулона. Донор пишет «Ширина, мм = 500» (живой стрейч 9600231/9602475/9603835) — единица В
    # ИМЕНИ свойства (изредка в значении «500 мм»). Многозначные свойства («Д 500 × Ш 300») пропускаем:
    # это не одиночная ширина. Нет «мм»/«см» в контексте → число как есть (м — прежнее поведение).
    w_name, w_val = _find(props, "ширина")
    if w_val and not re.search(r"[×xх*/]", w_val):
        w_nums = _nums(w_val)
        if w_nums:
            w_m = w_nums[0]
            w_ctx = f"{w_name} {w_val}".lower()
            if "мм" in w_ctx and "см" not in w_ctx:
                w_m = w_m / 1000.0             # «500 мм» → 0.5 м (иначе 500 м — ложь ×1000)
            elif "см" in w_ctx and "мм" not in w_ctx:
                w_m = w_m / 100.0              # «50 см» → 0.5 м
            spec["ширина_м"] = round(w_m, 4)
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
        # 4 знаков МАЛО: донор пишет «0.001066» → round(…,4)=0.0011 (+3% к объёму → ~1.5% к диаметру).
        spec["транспортный_объем_м3"] = round(vol, 6)
    kg, _ = weight_from_card(props)
    if kg:
        spec["вес_кг"] = kg
    return spec


def dims_from_physics(spec):
    """Посылка рулона БЕЗ КОРОБКИ — сам рулон-цилиндр (решение оператора 04.09: «коробки нет, там в
    сложенном виде другие размеры»). Длина = ширина рулона (см); ширина = высота = ДИАМЕТР цилиндра.

    Диаметр: «Транспортировочный объем, м³» карточки — это объём САМОГО рулона: V = π·(D/2)²·L →
    D = √(4V/(πL)) (проверено на живых карточках: стрейч 500 мм V=0.004253 → 50×10.4×10.4 см / 2 кг).
    Нет объёма → геометрия полотна площадь×толщина (рыхлость намотки 0.75), круг та же формула.
    Ни одного источника → None (не выдумываем).
    Провенанс dims_source='physics' — оператор видит, что это ОЦЕНКА формы товара, а не факт карточки.
    """
    w_m = spec.get("ширина_м")
    if not w_m or w_m <= 0:
        return None
    d_m = None
    vol = spec.get("транспортный_объем_м3")
    if vol and vol > 0:
        d_m = (4.0 * vol / (3.14159 * w_m)) ** 0.5       # круговой цилиндр, коробки НЕТ
    if not d_m or d_m <= 0:
        area, th_mm = spec.get("площадь_м2"), spec.get("толщина_мм")
        if area and th_mm and area > 0 and th_mm > 0:
            v_film = area * (th_mm / 1000.0)             # полотно, рыхлость 0.75
            d_m = (4.0 * (v_film / 0.75) / (3.14159 * w_m)) ** 0.5
    if not d_m or d_m <= 0:
        return None
    L = round(w_m * 100, 1)
    D = round(d_m * 100, 1)
    if not (0 < L <= 300 and 0 < D <= 300):
        return None                     # неправдоподобно — лучше ничего, чем ложь
    return [L, D, D]


def enrich(product, props):
    """Проставить продукту flat-габариты/вес/_spec из карточки. Меняет product, возвращает его.

    Правило честности: источник не выдумывает. Карточка → факт; ширина/вес в НАЗВАНИИ товара — тоже
    данные донора (провенанс 'донор:название'), берём как ФОЛБЭК, когда карточка молчит. Нет источника
    → нет ключа → ТОВАРОВЕД честно оставит needs_data (T5), а не «наверное влезет». dims_source говорит,
    ФАКТ или ОЦЕНКА.
    """
    dims = dims_from_card(props)
    source = "card" if dims else None
    if dims is None:
        spec = spec_from_card(props)
        if not spec.get("ширина_м"):                # карточка без ширины → ширина В НАЗВАНИИ (04.09)
            wm = width_m_from_name(product.get("name"))
            if wm:
                spec["ширина_м"] = wm
        dims = dims_from_physics(spec)
        source = "physics" if dims else None
    if dims:
        product["length"], product["width"], product["height"] = dims
        product["dims_source"] = source
    kg, ws = weight_from_card(props)
    if not kg:                                       # карточка без «Вес» → донор пишет вес в названии
        kg, ws = weight_kg_from_name(product.get("name")), "донор:название"
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


# ── Last-known-good кэш габаритов (реальные, читаны с донора ранее; НЕ выдумываем) ──────────────
_ARB_DIR = pathlib.Path(__file__).resolve().parent
DIMS_CACHE_DEFAULT = _ARB_DIR / "runtime" / "ovh_dims_cache.json"
_DIMS_CACHE_TTL = 14 * 86400               # 14 суток: кэш — пластырь на транзиентный флап, не вечный сталь
_DIM_FLAT = ("length", "width", "height")


def _cache_load(path):
    """Кэш → dict {url: snapshot}. Любой сбой файла → {} (fail-soft: слой не падает из-за кэша)."""
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:                    # noqa: BLE001
        return {}


def _cache_save(path, cache):
    """dict → файл атомарно (tmp→replace). Любой сбой → молча (fail-soft)."""
    try:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
    except Exception:                    # noqa: BLE001
        pass


def _dims_snapshot(p):
    """Продукт после ЖИВОГО чтения карточки → снапшот для кэша | None (нет реальных габаритов).

    Кэшируем только проверенное: все 4 габарита на месте + dims_source факт/оценка (card|physics).
    Пусто/мусор → None — в кэш не пишем, что не читали (не выдумываем даже в кэше).
    """
    if not all(p.get(k) for k in _DIM_FLAT) or p.get("dims_source") not in ("card", "physics"):
        return None
    snap = {k: p[k] for k in _DIM_FLAT}
    snap["dims_source"] = p.get("dims_source")
    snap["ts"] = time.time()
    if p.get("weight"):
        snap["weight"] = p["weight"]
        snap["weight_source"] = p.get("weight_source")
    return snap


def _cache_put(cache, p, url):
    snap = _dims_snapshot(p)
    if snap and url:
        cache[str(url)] = snap


def _cache_apply(cache, p, url):
    """Продукту БЕЗ габаритов → последние-известные ТОЙ ЖЕ карточки (реальные, TTL-свежие).

    Прозрачность: провенанс dims_source сохранён, продукт помечен dims_cached=True + ts — оператор
    видит «кэш», а не свежий факт. Неизвестный url / протух / пусто → продукт как был (честно без
    габаритов — ничего не сочиняем про карточку, которую ни разу не читали).
    """
    if not url:
        return p
    ent = cache.get(str(url))
    if not ent:
        return p
    age = time.time() - ent.get("ts", 0)
    if not (0 <= age <= _DIMS_CACHE_TTL):
        return p
    for k in _DIM_FLAT:
        p[k] = ent[k]
    p["dims_source"] = ent.get("dims_source", "card")
    if ent.get("weight"):
        p["weight"] = ent["weight"]
        p["weight_source"] = ent.get("weight_source", "донор:карточка")
    p["dims_cached"] = True
    p["dims_cached_ts"] = ent.get("ts")
    return p


def enrich_products(products, budget=120, fetch=None, only_where=None, cache_path=DIMS_CACHE_DEFAULT):
    """Обогатить партию карточками донора: габариты посылки/вес/_spec (GET, 0₽, бюджет seconds).

    fetch   — шов для тестов (по умолчанию fetch_card, fail-soft).
    only_where — предикат «обогащать ли продукт» (по умолчанию: есть живой url; dims_raw НЕ нужен —
    у стрейча имя «500 мм, 20 мкм…» регексом «50*0.3 м» не даёт dims_raw, а габариты даёт карточка).
    бюджет сам режет.
    cache_path — куда кэш (None = кэш выключен, для герметичных тестов; по умолчанию runtime).
    Бюджет — ВРЕМЯ, а не штуки: медленный донор не держит сутки; не успевшие остаются как есть.
    Кэш (last-known-good): каждый УСПЕШНЫЙ живой GET записывает реальные габариты карточки в
    runtime/ovh_dims_cache.json; продукты, оставшиеся БЕЗ габаритов (сбойный GET-флап донора →
    '', бюджет вытек, строки не по предикату) → честно берут последние-известные ТОЙ ЖЕ карточки
    (dims_cached=True). Это закрывает живой флап 2026-09-03: СБОРКА не умирает на одноразовом
    пустом ответе донора. Первый раз / неизвестный url → честно без габаритов (не выдумываем).
    Никогда не бросает исключение (беду не проглатываем: сеть сама fail-soft, кэш fail-soft,
    остальное честно всплывёт в _safe суточного цикла).
    """
    fetch = fetch if fetch is not None else fetch_card
    pred = only_where or (lambda p: bool(p.get("url")))
    cache = _cache_load(cache_path) if cache_path else {}
    t0 = time.monotonic()
    dirty = False
    for p in products:
        if not pred(p):
            continue
        if time.monotonic() - t0 > budget:
            break
        enrich(p, parse_card_properties(fetch(p["url"])))
        if _dims_snapshot(p):
            _cache_put(cache, p, p.get("url"))
            dirty = True
    # Фолбэк: сбойный/не успевший GET → последние-известные реальные габариты (не выдумываем).
    for p in products:
        if not all(p.get(k) for k in _DIM_FLAT):
            _cache_apply(cache, p, p.get("url"))
    if dirty:
        _cache_save(cache_path, cache)
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

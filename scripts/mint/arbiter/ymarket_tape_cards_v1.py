#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЛЕНТОЧНЫЙ ОРГАН · klejkaya-lenta (ЯМ 90741) — зеркало плёночного сборщика.

Источник фактов: XLSX cargo shop (runtime/cargo_matrix_2026-09-08/tape_xlsx_facts.json, снят
08.09) — имя / закупка / ФОТО БЕЗ ВОТЕРМАРКИ (прямое слово оператора: «по названию определить
и взять фото») / намотка / ширина / толщина / цвет / тип / вес / объём. Живой GET карточки дона
(0₽): ОВХ-габариты посылки (OVH.enrich) + наличие склада (STOCK.parse_stock, закон СКЛАДОВЩИКА:
лучше ноль, чем ложь) + og:image фолбэк.

ФИРМЕННОЕ имя — НЕ копия донора (жалоба оператора «названия как в карго почти один в один»):
«Скотч упаковочный 48 мм × 66 м, 45 мкм, прозрачный». Манифест 09.09 #2: суффикс «Для надёжной
упаковки и переезда» ИЗ ИМЁН УБРАН; у карточки-НАБОРА к имени добавляется «— N шт».
Свой EAN-13/артикул ARB-*, бренд ATLAS EDGE, все характеристики в параметры категории
(профиль 90741: длина/ширина/вид_скотча/вид_ленты/цвет/штук_в_упаковке/упаковок_в_товаре).

ПОЛКА v5 (СЛОВО ОПЕРАТОРА 09.09, детали в PACK_V5 ниже): не продаём ниже 900 ₽; якорь-одиночка =
закуп×9 (round10); набор = N рулонов (закуп набора честно N×закуп) ценой round10(N×закуп×7.65);
у кого одиночка ×9 < 900 — только комплектом. Набор = СВОЙ article/EAN/SKU, артикул набора
не уходит в offer-поля (только след), pid=рулон → общие фото/категория.

TWIN-гард движка (предохранитель): физ-отпечаток = ширина_мм|длина_м|штук_в_упаковке (читаемо и в
_spec, и живьём: параметр 14805583). Рулон(шт=1) и набор(шт=N) одной физ-группы — РАЗНЫЕ ключи →
сосуществуют (полка v5), а не близнецы. Вариант = (цвет-семья, толщина_мкм); толщина_мкм —
СЛУЖЕБНЫЙ ключ _spec (параметра толщины в 90741 НЕТ), живьём не виден → twin_variant_live даёт
(цвет, None) — консервативно. ГЛАВНАЯ защита от дублей — ДЕДУП в loader: одна физ-группа
(ширина|длина|мкм|цвет-семья) → самая дешёвая IN_STOCK (закон ЦЕНОВИК: лучшая маржа).

RUBICON: скрипт сам НИЧЕГО не пишет. `--commit` поднимает реальный залив — только по слову
оператора после снятия вердикта сухого прогона.
"""
import json, math, pathlib, re, sys

ARB = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ARB))

from uniqueizer_v1 import gen_ean13
import ymarket_role_categorist_v1 as C
import ymarket_ovh_dims_v1 as OVH
import ymarket_write_v1 as W
import donor_stock_v1 as STOCK

SLUG = "klejkaya-lenta"               # ключ ymarket_cats_v1.json → market_category_id 90741
DONOR_SLUG = "klejkaya-lenta"         # категория дона shop.cargo-avto.ru (скотч)
TARGET_PIDS = set()                   # партия = весь лист лент из XLSX (после фильтров/дедупа)
HOUSE_BRAND = "ATLAS EDGE"
MARKUP = 8.0                          # цена продажи = закупка ×8 (манифест магазина)
MAX_COST = 700.0                      # потолок закупки: промышленная 9600591 (2385₽) — не наш формат
SKU_PREFIX = "ARB2"                   # поколение SKU offerId: бамп при перезаливе партии. КАРАНТИН ЯМ
                                      # «Цена сильно снизилась» живёт на offerId (история цен) и НЕ лечится
                                      # ни пересозданием того же offerId, ни поднятием цены — только НОВЫМ
                                      # offerId (доказано Q1-экспериментом 09.09). Новый префикс = цена ×8
                                      # становится ПЕРВОЙ ценой offerId, карантина нет.

# ── ПОЛКА v5 (СЛОВО ОПЕРАТОРА 09.09) ─────────────────────────────────────────
# «набор подороже икс 9 −15» + «не продаём по ценам до 900 ₽; где дешёвый товар — делай
# комплект». Якорь-одиночка = закуп_рулона ×9 (округляем к десяткам); цена НАБОРА =
# round10(N × закуп_рулона × 9 × 0.85) = round10(N × закуп × 7.65). ЦЕНОВОЙ ПОЛ 900 ₽ на КАЖДУЮ
# карточку гоняет движок (манифест price_floor=900, floor-guard). Одиночка живёт ТОЛЬКО когда
# цена(×9) ≥ 900 — иначе товар только комплектом. Канон-числа:
# runtime/cargo_matrix_2026-09-08/tape_pack_v5_proposal.json (22 карточки = 9 одиночек + 13 наборов).
# Проводка: манифест-markup (эталон витрины ×8) НЕ трогаем до живого репрайса одиночек; ряды полки
# несут СВОЙ множитель _sale_mult (одиночка 9.0 / набор 7.65 при cost = N×закуп). См. _expand_packs.
SALE_MULT_SINGLE = 9.0        # якорь-одиночка: закуп ×9 (на дорогих группах закрывает пол 900)
SALE_MULT_SET_NET = 7.65      # набор: 9.0 × 0.85 — скидка объёма 15% от якоря-одиночки
# Премия комплектам 2/3 шт (СЛОВО ОПЕРАТОРА 10.09 «цена на комплект скотч 2 шт и 3 шт поднять по
# 600-800 руб. выше цены в целом» → выбор оператора: шаг +800₽). Классётся НА НАБОР поверх базового
# round10(N×закуп×7.65): итог = база + премия (800 кратно 10 — округление не дрейфует). Только 2 и 3
# шт: N=5 (48×33) и N=10 (канц) оператор не называл — не трогаем. Живой репрайс 10.09: 11/11 ✓.
SET_PREMIUM_QTY = {2: 800, 3: 800}
# pid (артикул донора, base) → роль на полке. single=False = одиночка ×9 < 900 → в продаже
# ТОЛЬКО комплектом (канц 180₽ / 48×33 360₽ / прозр-66 730₽ / кор-66 730₽ — ниже пола оператора).
PACK_V5 = {
    "9603018": {"single": False, "set": 10},   # канц 15×33 38 · 20₽/рулон → комплект 10 · 1530₽ (N∉{2,3}, без премии)
    "9605968": {"single": False, "set": 5},    # прозр 48×33 45 · 40₽ → комплект 5 · 1530₽ (N∉{2,3}, без премии)
    "9604226": {"single": False, "set": 2},    # прозр 48×66 45 ФЛАГМАН · 81₽ → комплект 2 · 1240+800=2040₽ (магнит-вход)
    "9604330": {"single": False, "set": 2},    # кор 48×66 45 · 81₽ → комплект 2 · 2040₽
    "9600095": {"single": True,  "set": 3},    # маркир красный 48×66 · 102₽ → одиночка 920₽ + набор 2340+800=3140₽
    "9600108": {"single": True,  "set": 3},    # маркир синий → 920₽ + 3140₽
    "9600109": {"single": True,  "set": 3},    # маркир оранжевый → 920₽ + 3140₽
    "9600072": {"single": True,  "set": 3},    # маркир зелёный → 920₽ + 3140₽
    "9604250": {"single": True,  "set": 2},    # прозр 72×66 · 120₽ → одиночка 1080₽ + набор 1840+800=2640₽
    "9604264": {"single": True,  "set": 2},    # прозр 48×132 40 · 138₽ → 1240₽ + 2110+800=2910₽
    "9604227": {"single": True,  "set": 2},    # прозр 48×132 45 · 149₽ → 1340₽ + 2280+800=3080₽
    "9604596": {"single": True,  "set": 2},    # прозр 48×150 40 · 175₽ → 1580₽ + 2680+800=3480₽
    "9604581": {"single": True,  "set": 2},    # прозр 48×150 45 · 190₽ → 1710₽ + 2910+800=3710₽
}

FACT_PATH = ARB / "runtime/cargo_matrix_2026-09-08/tape_xlsx_facts.json"

_OG_RE = re.compile(r'property="og:image"\s+content="([^"]+)"')
_ТИП_СЛОВО = {"упаковочная": "упаковочный", "канцелярская": "канцелярский",
              "маркировочная": "маркировочный"}
_ПРОЗР = {"прозрачный", "прозрачная", "прозрачные", "кристально-прозрачный",
          "кристально-прозрачная", "бесцветный", "бесцветная", "кристальный"}


def _num(f, key):
    """Факт → float; None если пусто/не-число (честно: источник молчит, не выдумываем)."""
    v = f.get(key)
    if v is None:
        return None
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _fmt_ru(x):
    """0.153→'0,153', 66→'66' — русская десятичная запятая для описания."""
    return f"{float(x):g}".replace(".", ",")


def _цвет_семья(raw):
    """'Кристально-прозрачный'/'бесцветный' → 'прозрачный'; цветные — свои (lower). None если пусто."""
    s = str(raw or "").strip().lower()
    if not s:
        return None
    return "прозрачный" if s in _ПРОЗР else s


def _наличие(f, html):
    """Живой статус склада (STOCK.parse_stock, авторитетен) → фолбэк на XLSX 'наличие_shop'.
    Только 'in_stock' даёт источник наличия (закон СКЛАДОВЩИКА: лучше ноль, чем ложь)."""
    st = STOCK.parse_stock(html).get("status") if html else None
    if st:
        return st
    return "in_stock" if str(f.get("наличие_shop") or "").strip() == "В наличии" else None


def _load_facts():
    """tape_xlsx_facts.json → list[dict]; сбой/отсутствие → [] (fail-soft, сутки не крашим)."""
    if not FACT_PATH.exists():
        return []
    try:
        data = json.loads(FACT_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def _og_from_html(html):
    m = _OG_RE.search(html or "")
    return m.group(1) if m else ""


def _dedup(rows):
    """На одну физ-группу (ширина|длина|мкм|цвет-семья) — самая дешёвая IN_STOCK.
    ЦЕНОВИК: лучшая маржа (та же цена продажи ×8 при меньшей закупке) + анти-дубль (один
    физический рулон — одна карточка на полке). Проигравшие помечаются _twin_dropped."""
    best = {}
    for p in rows:
        k = (str(p.get("ширина_мм")).strip(), str(p.get("намотка_м")).strip(),
             str(p.get("толщина_мкм") or "").strip(), _цвет_семья(p.get("цвет")))
        cost = _num(p, "cost") or math.inf
        prev = best.get(k)
        if prev is None or cost < (prev.get("_cost") or math.inf):
            p["_cost"] = cost
            if prev is not None:
                prev["_twin_dropped"] = True
                prev["_dropped_by"] = str(p.get("article"))
            best[k] = p
    return [p for p in best.values() if not p.get("_twin_dropped")]


def _tape_dims_physics(p):
    """ОВХ-фолбэк ленты: посылка = сам рулон-цилиндр (решение оператора 04.09 для рулонов:
    «коробки нет»). ЕДИНСТВЕННАЯ ветка ленты (унификация 08.09, адверсариал-аудит #80):
    диаметр из ГЕОМЕТРИИ намотки — полотно длиной L и толщиной t намотано на втулку радиусом r →
    кольцо сечения π(R²−r²) = L·t/ρ (ρ=0.9, рыхлость намотки, ср. плёночный dims_from_physics
    ρ=0.75) → D = 2·√(L·t/(ρπ) + r²). «Транспортировочный объём» дона для рулона НЕ используем:
    он включает упаковку/воздух и даёт НЕПРАВДОПОДОБНЫЕ диаметры (40мкм-рулон 13.2см против
    45мкм-близнеца 11.9см, аудит HIGH) — любая physics-оценка объёмом (dims_source='physics')
    ПЕРЕЗАПИСЫВАЕТСЯ честной геометрией. НЕ выдумка: все 4 ингредиента (намотка/ширина/толщина/
    втулка) прочитаны с дона честно; провенанс 'physics' — оператор видит «оценка формы», не факт.
    Реальные размеры с дона (dims_source='card', dims_from_card) — ФАКТ карточки, их не трогаем."""
    if p.get("dims_source") == "card":
        return p                              # факт дона, не перезаписываем
    L = _num(p, "намотка_м")
    w = _num(p, "ширина_мм")
    t = _num(p, "толщина_мкм")
    r = _num(p, "втулка_мм")
    if not (L and w and t and r and L > 0 and w > 0 and t > 0 and r > 0):
        return p
    r_m, t_m = r / 2000.0, t / 1e6            # радиус втулки (м), толщина полотна (м)
    D_m = 2.0 * (L * t_m / (0.9 * 3.14159) + r_m * r_m) ** 0.5
    L_cm, D_cm = round(w / 10.0, 1), round(D_m * 100, 1)
    if not (0 < L_cm <= 300 and 0 < D_cm <= 300):
        return p                              # неправдоподобно — лучше ничего, чем ложь
    p["length"], p["width"], p["height"] = L_cm, D_cm, D_cm
    p["dims_source"] = "physics"
    return p


def _round10(x):
    """Цена к десяткам ₽ (решение оператора 09.09: 816 «не красиво» → ровные десятки)."""
    return int(round(x, -1))


def _expand_packs(rows):
    """Полка v5: после дедупа строка физ-группы → карточки полки.
    Дорогая группа (одиночка ×9 ≥ 900) → одиночка + НАБОР; дешёвая (одиночка ×9 < 900, пол
    оператора) → ТОЛЬКО НАБОР. Набор: СВОЙ EAN/SKU от артикула-набора f"{article}-{N}x"
    (_ean_article; pid = рулона → фото/категория общие), cost = N × закуп_рулона (честная
    себестоимость единицы «набор»), _sale_mult=7.65, штук_в_упаковке=N; ОВХ: вес ×N всегда,
    длина ×N только для physics (N рулонов стопкой вдоль оси) — card-факт дона не трогаем."""
    out = []
    for p in rows:
        cfg = PACK_V5.get(str(p.get("pid") or ""))
        if cfg is None:                       # не-полка → как было (одиночка, манифест-markup)
            out.append(p)
            continue
        roll_cost = _num(p, "cost")
        N = cfg.get("set")
        if N and roll_cost and roll_cost > 0:
            q = dict(p)
            q["_ean_article"] = f"{p['article']}-{N}x"    # СВОЙ EAN/SKU набора (pid тот же)
            q["_is_pack"] = True
            q["_pack_size"] = int(N)
            q["_sale_mult"] = SALE_MULT_SET_NET
            q["cost"] = round(roll_cost * N, 2)           # единица «набор» = N рулонов
            for _k in ("weight",) + (("length",) if p.get("dims_source") == "physics" else ()):
                _v = p.get(_k)
                if isinstance(_v, bool) or _v is None:
                    continue
                try:
                    _x = float(_v)
                except (TypeError, ValueError, OverflowError):
                    continue
                if math.isfinite(_x) and _x > 0:
                    q[_k] = _x * N
            out.append(q)
        if cfg.get("single"):                 # одиночка полки: свой множитель-якорь ×9
            s = dict(p)
            s["_sale_mult"] = SALE_MULT_SINGLE
            out.append(s)
    return out


def load_products(scope=None):
    """XLSX-факты → фильтры (настоящая лента + цена) → живой GET каждой (ОВХ/наличие/og) → дедуп.

    Строки несут _facts/_stock/_og: движок мёржит _og в pub (фото-слой), N1 читает _stock
    (закон СКЛАДОВЩИКА: строки не-in_stock в партию не входят вообще — N1 не FAIL-ит по ним).
    scope из манифеста ('new-rolls') — партия всегда весь лист лент (TARGET_PIDS пуст).
    """
    out = []
    for f in _load_facts():
        # Фильтр «настоящая лента»: есть И намотка, И ширина (исключает коробку 9600068,
        # курьер-пакет 9605484, ВПП 9600155, бумагу 9600130). Цена ≤ потолка (9600591 — мимо).
        if not _num(f, "намотка_м") or not _num(f, "ширина_мм"):
            continue
        cost = _num(f, "cost")
        if cost is None or cost <= 0 or cost > MAX_COST:
            continue
        url = str(f.get("ссылка") or "").strip()
        html = OVH.fetch_card(url) if url else ""
        p = dict(f)
        p["pid"] = str(f.get("article") or "").split("-")[0]
        p["sku"] = str(f.get("article") or "")
        p["article"] = str(f.get("article") or "")
        p["_facts"] = True
        # ФОТО: прямое слово оператора — колонка XLSX «Фото без вотермарки» (фото_чистое);
        # og:image дона — честный фолбэк, если чистое фото в файле отсутствует.
        p["_og"] = str(f.get("фото_чистое") or "").strip() or _og_from_html(html)
        p["_stock"] = _наличие(f, html)
        if p["_stock"] != "in_stock":
            continue
        OVH.enrich(p, OVH.parse_card_properties(html))   # 0₽ GET по карточкам дона, fail-soft
        _tape_dims_physics(p)                            # карточка без объёма → геометрия намотки
        # ВЕС-ФОЛБЭК: живой html молчит (флап дона / карточка без «Вес») → вес РУЛОНА из донор-файла
        # XLSX (вес_кг — колонка cargo-шопа, та же семья правды, что шириной/намоткой правят геометрию;
        # провенанс 'xlsx' — оператор видит «файл дона», не факт карточки). Живой факт карточки
        # (weight_source='донор:…') НЕ перезаписывается — фолбэк только на тишину. Набор умножит вес
        # ×N сам в _expand_packs — здесь всегда вес ОДНОГО рулона.
        if not p.get("weight"):
            _wkg = _num(f, "вес_кг")
            if _wkg and _wkg > 0:
                p["weight"] = _wkg
                p["weight_source"] = "xlsx"
        out.append(p)
    # Полка v5: дедуп по физ-группе → разворот в одиночки/наборы (PACK_V5). Дедуп ПОСЛЕ разворота
    # не гоняем: набор того же w|l с N≠1 не близнец одиночки (twin-отпечаток +штук), а повторный
    # дедуп схлопнул бы набор с рулоном.
    return _expand_packs(_dedup(out))


def load_film_products(scope=None):
    """Алиас интерфейс-контракта (движок диспатчит getattr 'load_products')."""
    return load_products(scope)


def resolve_markup(markup):
    """Множитель цены из манифеста магазина → (число>1, ошибка_или_None). Зеркало film_cards:
    None → модульная MARKUP (8.0); boolean/не-число/≤1/nan/inf — БИТЫЙ манифест, не тихая цена."""
    if markup is None:
        return MARKUP, None
    if isinstance(markup, bool):
        return None, f"markup манифеста — boolean {markup!r}, не число (цена была бы ≤ закупки)"
    if isinstance(markup, str):
        s = markup.strip()
        if not s:
            return None, "markup манифеста — пустая строка (битый манифест)"
        try:
            markup = float(s)
        except ValueError:
            return None, f"markup манифеста «{markup}» — не число (битый манифест)"
    try:
        mult = float(markup)
    except (TypeError, ValueError, OverflowError):
        return None, f"markup манифеста «{markup!r}» — не число (битый манифест)"
    if not math.isfinite(mult):
        return None, (f"markup манифеста «{markup!r}» — не конечное число (nan/inf); "
                      "поставь > 1 (для ленты ×8)")
    if mult <= 1.0:
        return None, (f"markup {mult:g} ≤ 1 — цена продажи {mult:g}× закупки ≤ закупки, "
                      "гарантированный убыток после издержек (P1); поставь > 1 (для ленты ×8)")
    return mult, None


def _build_name(f, donor_name=""):
    """ФИРМЕННОЕ имя — стиль эталона (рейтинг 87), НЕ копия донора. Марка дона (Unibob/Nova
    Roll/Лентапром) НЕ переносится; размеры с «×», толщина/цвет словом; поисковые ключи сохранены.
    Не собралось → донорское имя 1-в-1 (без потерь)."""
    try:
        w = f"{_num(f, 'ширина_мм'):g}"
        l = f"{_num(f, 'намотка_м'):g}"
        мкм = f"{_num(f, 'толщина_мкм'):g}"
        цвет = str(f.get("цвет") or "").strip().lower()
        if not цвет:
            return donor_name
        тип = _ТИП_СЛОВО.get(str(f.get("тип_ленты") or "").strip().lower(), "упаковочный")
        # Манифест 09.09 #2: суффикс «Для надёжной упаковки и переезда» из имён убран; количество
        # рулонов в имя набора добавляет build_product («— N шт»).
        return f"Скотч {тип} {w} мм × {l} м, {мкм} мкм, {цвет}."
    except Exception:
        return donor_name


def _рул(n):
    """Числительное для лида набора: 1→«рулон», 2/3/4→«рулона», 5+→«рулонов»."""
    n100, n10 = n % 100, n % 10
    if 11 <= n100 <= 14:
        return "рулонов"
    if n10 == 1:
        return "рулон"
    if 2 <= n10 <= 4:
        return "рулона"
    return "рулонов"


# Родительный падеж основы для герой-абзаца «лента на основе …» (в фактах дона — именительный).
_ОСНОВА_РОД = {"Двуосноориентированный полипропилен": "двуосноориентированного полипропилена"}


def _build_description(f):
    """НАШЕ описание (создано на основе донора, НЕ копия): герой-абзац → применение → спеки.
    Каждый факт из tape_xlsx_facts; клеевой/основа/втулка/вес/страна — только когда донор их дал."""
    тип = str(f.get("тип_ленты") or "упаковочная").strip().lower()
    вширь = f"{_num(f, 'ширина_мм'):g}"
    вдлину = f"{_num(f, 'намотка_м'):g}"
    мкм = f"{_num(f, 'толщина_мкм'):g}"
    цвет = str(f.get("цвет") or "").strip().lower()
    клей = str(f.get("клеевой") or "").strip()
    основа = str(f.get("основа") or "").strip()
    N = int(f.get("_pack_size") or 1)                  # 1 = одиночка; N>1 = набор (полка v5)
    вес = _fmt_ru(f["вес_кг"]) if _num(f, "вес_кг") else None
    втулка = f"{_num(f, 'втулка_мм'):g}" if _num(f, "втулка_мм") else None
    страна = str(f.get("страна") or "").strip()
    осн = f" на основе {_ОСНОВА_РОД.get(основа, основа)}" if основа else ""
    кл = f" Клеевой слой: {клей}." if клей else ""
    абзац1 = (f"<p>Скотч ATLAS EDGE — {тип} лента{осн} шириной {вширь} мм и намоткой {вдлину} м. "
              f"Толщина полотна {мкм} мкм, цвет {цвет}.{кл} Лента разматывается ровно, "
              "клеевой слой схватывается сразу и держит коробку при транспортировке и хранении.</p>")
    абзац2 = ("<p>Скотч покупают интернет-магазины для сборки заказов, семьи при переезде и "
              "владельцы складов — для заклейки коробок, посылок и картонных упаковок. "
              + (f"Диаметр втулки {втулка} мм." if втулка else "")
              + "</p>")
    спеки = [f"Ширина: {вширь} мм", f"Длина намотки: {вдлину} м", f"Толщина полотна: {мкм} мкм",
             f"Тип: {тип}", f"Цвет: {цвет}"]
    if N > 1:
        спеки.insert(0, f"Количество рулонов в наборе: {N} шт")
    if вес:
        спеки.append(f"Вес одного рулона: {вес} кг" if N > 1 else f"Вес: {вес} кг")
    if основа:
        спеки.append(f"Материал основы: {основа[:1].lower() + основа[1:]}")
    if клей:
        спеки.append(f"Клеевой слой: {клей}")
    if втулка:
        спеки.append(f"Диаметр втулки: {втулка} мм")
    if страна:
        спеки.append(f"Страна производства: {страна}")
    li = "".join(f"<li>{s}</li>" for s in спеки)
    лид = f"<p>В наборе: <b>{N} {_рул(N)}</b> скотча ATLAS EDGE.</p>" if N > 1 else ""
    return (лид + абзац1 + абзац2 +
            "<p><b>Технические характеристики:</b></p><ul>" + li + "</ul>")


def _build_spec(f):
    """Факты → prod['_spec']: ключи, которые профиль 90741 читает в parameterValues.
    толщина_мкм — СЛУЖЕБНЫЙ ключ (параметра толщины в 90741 НЕТ): в parameterValues не уходит,
    читает его ТОЛЬКО twin-гард (вариант цвета/толщины разводит законные варианты на полке)."""
    spec = {
        "длина_м": f.get("намотка_м"),                 # 23674610, unitId 6 м
        "ширина_мм": f.get("ширина_мм"),               # 34439430, unitId 6145200 мм
        "вид_скотча": "односторонний",                 # 37188370 → 38421390 (все выбранные одностор.)
        "цвет": str(f.get("цвет") or "").strip().lower(),  # 13887626 → valueId словаря
        "толщина_мкм": str(f.get("толщина_мкм") or "").strip(),  # СЛУЖЕБНЫЙ (twin)
        "штук_в_упаковке": int(f.get("_pack_size") or 1),  # 14805583; набор = N (полка v5)
        "упаковок_в_товаре": 1,                        # 33663230, unitId 6145205
    }
    # вид_ленты (37141050) — только прозрачные: честно «прозрачная»; цветные ленты вида не несут.
    if _цвет_семья(f.get("цвет")) == "прозрачный":
        spec["вид_ленты"] = "прозрачная"               # 37141050 → 45477530
    return spec


def _pub_urls_by_pid():
    """У ленты нет published_urls: фото-слой = _og строки (фото_чистое из XLSX), движок мёржит сам."""
    return {}


def build_product(p, pub_urls, index, *, markup=None):
    """XLSX-строка → product-словарь ARBITER (схема ymarket_card.to_offer). Зеркало film_cards:
    гейты bool-cost/не-число/≤0/не-финит×mult, price≤cost, weightDimensions всеми 4, свой EAN-13,
    sku ARB2-{ean[-8:]} (префикс-поколение SKU_PREFIX), vendor ATLAS EDGE, unique_name, фото из pub_urls (движок заложил _og)."""
    pid = str(p.get("pid") or p.get("sku"))
    donor_article = str(p.get("article") or "")
    # НАБОР несёт СВОЙ артикул-ключ = _ean_article (f"{артикул}-{N}x") — ровно тот, что кормит EAN.
    # Иначе набор и одиночка одной физ-группы уходят в мир с ОДНИМ article донора, и дедуп матрицы
    # (_find_dup, article — ПЕРВЫЙ ключ M2, ymarket_matrix_v1:141) схлопывает их в одну строку:
    # набор теряет offer_id и статус. Артикул донора НЕ теряется — живёт в donor_article (связь
    # с донором, директива оператора 10.09). В offer ЯМ article не уходит вовсе (ymarket_card.to_offer).
    article = str(p.get("_ean_article") or donor_article)
    _raw_name = p.get("name")
    name = _raw_name.strip() if isinstance(_raw_name, str) else ""
    mult, merr = resolve_markup(markup)
    if merr:
        raise ValueError(merr)                # битый markup манифеста → громко, не тихая цена
    if isinstance(p.get("cost"), bool):
        return None                           # bool-закупка = тип-коррупция → честный пропуск
    try:
        cost = float(p.get("cost") or 0)
    except (TypeError, ValueError, OverflowError):
        cost = float("nan")
    if not article or not name or not math.isfinite(cost) or cost <= 0:
        return None
    ean = gen_ean13(p.get("_ean_article") or article)  # набор → СВОЙ EAN от «артикул-Nx» (полка v5)
    sm = p.get("_sale_mult")                          # множитель полки v5: одиночка 9.0 / набор 7.65
    if not isinstance(sm, bool):
        try:
            sm = float(sm) if sm is not None else None
        except (TypeError, ValueError, OverflowError):
            sm = None
    else:
        sm = None
    if sm is not None and not (math.isfinite(sm) and sm > 1.0):
        sm = None                                     # битый множитель → обычный путь ×markup
    if sm is not None:
        price = _round10(cost * sm)                   # полка v5: round10(N×закуп×7.65 / закуп×9)
        # Премия оператора 10.09: комплект 2/3 шт дороже базового round10(N×закуп×7.65) на +800₽
        # (шаг кратен 10 — цена остаётся ровным десятком). Живой репрайс 11/11 сделан тем же
        # числом — ЦИКЛ-1 воспроизводит витрину, СВЕРКА дрейф цены не поймает.
        _pk = int(p.get("_pack_size") or 0)
        if p.get("_is_pack") and _pk in SET_PREMIUM_QTY:
            price += SET_PREMIUM_QTY[_pk]
    else:
        lo, _hi = C.propose_prices(cost, mult, mult)
        price = round(lo)
    if price <= cost:
        return None                           # копеечная маржа потеряна в round → честный пропуск
    if p.get("_facts"):
        name = _build_name(p, name)           # ФИРМЕННОЕ имя, НЕ копия
        _pn = int(p.get("_pack_size") or 0)
        if _pn > 1:
            name = f"{name} — {_pn} шт"       # набор: число рулонов в имени (Манифест 09.09 #2)
    prod = {
        "sku": f"{SKU_PREFIX}-{ean[-8:]}",  # СВОЙ артикул продавца; префикс-поколение (см. SKU_PREFIX)
        "name": name,
        "barcode": ean,                       # СВОЙ EAN-13 — главный рычаг анти-склейки
        "cost": cost,                         # закупка у донора (₽); набор = N×закуп (честно)
        "price": price,                       # полка v5: round10(закуп×9) одиночка / round10(N×закуп×7.65) набор
        "article": article,                   # ключ строки: донорский, у набора свой f"{артикул}-{N}x"
        "donor_article": donor_article,       # артикул донора 1-в-1 (связь с донором; в offer не уходит)
        "house_brand": HOUSE_BRAND,           # суффикс уникальности имени
        "vendor": HOUSE_BRAND,                # своя марка + свой EAN-13 → анти-склейка с донором
        "send_vendor": True,
        "unique_name": True,
        "extra_kw": None,
        "pictures": pub_urls.get(pid, []),    # фото_чистое (XLSX) — движок мёржит _og в pub
        "dims_source": p.get("dims_source"),
        "pid": pid,
    }
    if p.get("_facts"):
        prod["_spec"] = _build_spec(p)
        prod["description"] = _build_description(p)
        prod["manufacturerCountries"] = ["RU"]
    # weightDimensions: ВСЕ четыре честно (есть, число-не-bool, конечны, >0) — иначе НЕ выдумываем.
    keys = ("length", "width", "height", "weight")
    dims = {}
    for k in keys:
        v = p.get(k)
        if isinstance(v, bool) or v is None:
            break
        try:
            x = float(v)
        except (TypeError, ValueError, OverflowError):
            break
        if not math.isfinite(x) or x <= 0:
            break
        dims[k] = x
    if len(dims) == len(keys):
        prod["weightDimensions"] = dims
    return prod


# ── TWIN-HOOKS (движок диспатчит через builder, плёночный путь байт-в-байт без них) ──────────
# Физ-отпечаток ленты = ширина_мм|длина_м|штук_в_упаковке; вариант = (цвет-семья, мкм).
# parameterId живого offer-cards: 34439430 ширина (unitId 6145200 мм) · 23674610 длина (unitId 6 м)
# · 13887626 цвет · 14805583 штук_в_упаковке (полка v5: рулон=1 vs набор=N — РАЗНЫЕ ключи,
# рулон и набор одной физ-группы сосуществуют, НЕ схлопываются в близнеца).
_TAPE_LIVE_PID = {34439430: "w", 23674610: "l", 13887626: "цвет", 14805583: "шт"}


def twin_spec_key(pr):
    """Задумка (_spec) → 'ширина|длина|шт'; нечем/бито → None."""
    sp = pr.get("_spec") or {}
    if not sp:
        return None
    try:
        w = float(sp.get("ширина_мм"))
        l = float(sp.get("длина_м"))
        шт = int(sp.get("штук_в_упаковке") or 1) or 1
    except (TypeError, ValueError):
        return None
    if not (w > 0 and l > 0):
        return None
    return f"{w:g}|{l:g}|{шт}"


def twin_variant(pr):
    """Задумка (_spec) → (цвет-семья, толщина_мкм); неизвестно → None (не разводит)."""
    sp = pr.get("_spec") or {}
    col = _цвет_семья(sp.get("цвет"))
    мкм = str(sp.get("толщина_мкм") or "").strip() or None
    return (col, мкм)


def twin_live_key(pv_list):
    """Живой offer-cards (parameterValues) → тот же физ-ключ; параметров нет → None."""
    got = {}
    for pv in pv_list or []:
        k = _TAPE_LIVE_PID.get(pv.get("parameterId"))
        if k:
            got[k] = pv.get("value")
    if not ({"w", "l"} <= set(got)):
        return None
    try:
        w, l = float(got["w"]), float(got["l"])
        шт = int(float(got.get("шт") or 1)) or 1   # штук_в_упаковке; живьём может не быть → 1
    except (TypeError, ValueError):
        return None
    if not (w > 0 and l > 0):
        return None
    return f"{w:g}|{l:g}|{шт}"


def twin_variant_live(pv_list):
    """Живой offer-cards → (цвет-семья, None): толщины в параметрах 90741 НЕТ → консервативно."""
    got = {}
    for pv in pv_list or []:
        if pv.get("parameterId") == 13887626:
            got["цвет"] = pv.get("value")
    return (_цвет_семья(got.get("цвет")), None)


def build_all(dry=True, commit=False):
    """Полный сухой/реальный ход: XLSX+живой скан → продукты → publish_card ×N. Сводка."""
    raw = load_products()
    pub = _pub_urls_by_pid()
    for p in raw:                       # движок делает то же (N2); тут — для автономного прогона
        _og = p.get("_og")
        if _og:
            pub.setdefault(p["pid"], [])
            if _og not in pub[p["pid"]]:
                pub[p["pid"]].append(_og)
    products = [build_product(p, pub, i) for i, p in enumerate(raw)]
    products = [pr for pr in products if pr]
    out = []
    for pr in products:
        r = W.publish_card(pr, slug=SLUG, dry=dry, commit=commit, photo_urls=pr["pictures"])
        out.append({"pid": pr["pid"], "sku": pr["sku"], "ok": r.get("ok"),
                    "price": pr["price"], "cost": pr["cost"], "dims": pr.get("weightDimensions"),
                    "photos": len(pr["pictures"]), "name": pr["name"][:52],
                    "errors": (r.get("errors") or r.get("error") or None),
                    "need_mapping": r.get("need_mapping"), "category_id": r.get("category_id")})
    return {"dry": dry, "products": out}


def render(res):
    L = [f"📦  ЛЕНТОЧНЫЙ ОРГАН · {SLUG} (market_category_id 90741) · "
         f"{'DRY (0₽, наружу НИЧЕГО)' if res['dry'] else 'LIVE'}", ""]
    ok_all = True
    for r in res["products"]:
        tag = "🟢" if r["ok"] else "🔴"
        ok_all = ok_all and bool(r["ok"])
        L.append(f"{tag} pid={r['pid']}  {r['name']}")
        L.append(f"     купить {r['cost']:g}₽ → продать {r['price']}₽ · фото {r['photos']} · "
                 f"габариты {r['dims'] or 'НЕТ'}")
        if r["errors"]:
            L.append(f"     ошибки: {r['errors']}")
        if r["need_mapping"]:
            L.append(f"     need_mapping={r['need_mapping']} category_id={r['category_id']}")
    L.append("")
    L.append("ИТОГ: " + ("ПАРТИЯ ЧИСТАЯ — готова к сухому ЦИКЛ-1 и слову оператора на --commit"
                         if ok_all else "есть ошибки — смотрим выше"))
    return "\n".join(L)


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Ленточный орган (klejkaya-lenta 90741)")
    ap.add_argument("--commit", action="store_true",
                    help="РЕАЛЬНЫЙ залив (dry=False, commit=True) — по слову оператора")
    args = ap.parse_args(argv)
    dry = not args.commit
    res = build_all(dry=dry, commit=args.commit)
    print(render(res))
    return 0 if all(r["ok"] for r in res["products"]) else 1


if __name__ == "__main__":
    sys.exit(_main())

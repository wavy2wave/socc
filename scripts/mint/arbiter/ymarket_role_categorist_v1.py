#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РОЛЬ · КАТЕГОРИЙЩИК (YM_CATEGORIST) — «шарит за категорию, врывается с двух ног».

Веха методологии главной линии (ЯМ Экспресс, 2026-08-18): оператор дал донорскую выгрузку
(shop.cargo-avto.ru) и мандат — взять ОДНУ категорию, покупать дёшево (закупка ≤ порога),
продавать ×5–10 там, где у Экспресса нет конкуренции, влезать в габариты курьера. КАТЕГОРИЙЩИК —
это тот сотрудник, что читает донорскую выгрузку глазами профи и выдаёт РАНЖИРОВАННЫЙ ШОРТ-ЛИСТ:
«вот на чём Экспресс реально зарабатывает, вот сколько купить/продать, вот почему».

ЗАКОН SOCC (как весь ARBITER):
  • stdlib + openpyxl (ленивый импорт, только в читателе донора); БЕЗ сети и БЕЗ денег — чистое чтение.
  • ЧЕСТНОСТЬ (L3, без фейк-пасс): предлагаем только то, что следует из реальных чисел строки.
    Нет габаритов/веса → Экспресс-подгонку не проверить → позиция в needs_data, НЕ в шорт-лист.
  • НЕ ЛОМАЕТ орган: новый модуль. Физику/экономику НЕ дублируем — делегируем ТОВАРОВЕДУ
    (merchandiser.screen_one: габариты города, тариф, обрыв) и ЦЕНОВИКУ (pricer: пол маржи).

ГЛАВНАЯ ТОНКОСТЬ ДРОПШИПА (живой урок с реальной выгрузки 2026-08-19):
  На выгрузке shop.cargo-avto.ru колонка «Цена» = РОЗНИЦА cargo-avto = НАША ЗАКУПКА (мы у них берём).
  «Цена поставщика» = ИХ входная цена — для нас шум. ЦЕНЫ ПРОДАЖИ в файле НЕТ — её не существует,
  пока мы её не назначим. Поэтому КАТЕГОРИЙЩИК цену продажи НЕ читает, а ПРЕДЛАГАЕТ (×наценка),
  честно помечая как предложение. Это противоположно допущению общего загрузчика from_xlsx
  (там price = наша цена продажи), поэтому у роли СВОЙ донор-читатель — общий load_category не трогаем.

ЗАКОНЫ РОЛИ (механические, проверяются приёмкой):
  C1  донорская «Цена» → наша ЗАКУПКА (cost), не цена продажи. Не путаем колонки.
  C2  цену продажи не берём из файла — ПРЕДЛАГАЕМ cost×наценку; помечаем price_is_proposal=True.
  C3  нет габаритов/веса → Экспресс-подгонку не проверить → needs_data, не выдумываем размеры.
  C4  закупка > порога (max_cost) → отбой: мандат «врываться дёшево».
  C5  ни одна наценка из диапазона не проходит пол маржи ЦЕНОВИКА → отбой (сделка бессмысленна).
"""
from __future__ import annotations

import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ymarket_role_merchandiser_v1 as merch   # noqa: E402  габариты города, тариф, обрыв, экономика
import ymarket_role_pricer_v1 as pricer        # noqa: E402  пол маржи (через merch.screen_one)
import ymarket_card_v1 as card                 # noqa: E402  карта категорий (marketCategoryId)

CHARTER = {
    "id": "YM_CATEGORIST",
    "name_ru": "КАТЕГОРИЙЩИК",
    "mandate": "из донорской выгрузки выбрать позиции, на которых Экспресс реально зарабатывает: "
               "дёшево купить (≤ порога), продать ×5–10 без конкуренции, влезть в габариты курьера",
    "owns": ["чтение донорской выгрузки", "предложение цены продажи (наценка)",
             "шорт-лист под Экспресс", "ранжирование по прибыли"],
    "inputs": ["донорский XLSX (cargo-avto и совместимые)", "лимиты города (ТОВАРОВЕД)",
               "порог закупки и диапазон наценки (оператор)", "карта категорий (подтверждён ли id)"],
    "outputs": ["ранжированный шорт-лист → вышка/суточный цикл", "needs_data и rejected с причинами"],
    "laws": [
        "C1 донорская «Цена» = НАША закупка (дропшип), не цена продажи",
        "C2 цену продажи не читаем из файла — ПРЕДЛАГАЕМ cost×наценку (price_is_proposal)",
        "C3 нет габаритов/веса → Экспресс-подгонку не проверить → needs_data (не выдумываем)",
        "C4 закупка > порога → отбой (врываемся дёшево)",
        "C5 ни одна наценка диапазона не проходит пол маржи → отбой",
    ],
    "kpi": [
        {"metric": "позиций в шорт-листе", "target": "максимум прибыльных", "source_of_truth": "экономика merch/pricer"},
        {"metric": "средняя предложенная маржа", "target": "максимум", "source_of_truth": "pricer.price_decision"},
        {"metric": "позиций с выдуманными данными", "target": "0", "source_of_truth": "needs_data честно отделён"},
    ],
    "proves_by": "каждая позиция шорт-листа воспроизводима: закупка/габариты/наценка/why ведут к строке донора",
}

# Диапазон наценки по умолчанию (мандат оператора 2026-08-18: ×5–10 там, где нет конкуренции).
DEFAULT_MARKUP_LO = 5.0
DEFAULT_MARKUP_HI = 10.0
# Порог закупки по умолчанию (мандат: «врываемся дёшево», ≤700 ₽ за позицию).
DEFAULT_MAX_COST_RUB = 700.0
# Физически невозможный вес для упаковочной позиции (короб/лента/рулон плёнки): выше — колонка
# «Вес, кг» на деле содержит ГРАММЫ (частая ошибка выгрузки). Не выдумка — реконсиляция единиц с флагом.
_IMPLAUSIBLE_KG = 50.0

_URL_RE = re.compile(r"https?://[^\s,;|]+")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _lc(s):
    return _norm(s).lower().replace("ё", "е")


def _num(s):
    """'1,2'→1.2 ; '52'→52.0 ; '276 г'→276.0 ; мусор→None."""
    if s is None:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", str(s))
    return float(m.group(0).replace(",", ".")) if m else None


# ── Чистая логика (без openpyxl; тестируется в регрессии под любым Python) ──────────────────

def resolve_weight_kg(grams_cell, kg_cell):
    """Честный вес в кг из двух колонок донора («Вес, г» и «Вес, кг»).

    ЖИВОЙ УРОК (реальная выгрузка cargo-avto 2026-08-19): у коробов колонка «Вес, кг» содержит 276,
    что для картонной коробки физически невозможно в килограммах — это ГРАММЫ (276 г). Колонка
    «Вес, г» — однозначная. Правило (с флагом, не втихую):
      • есть «Вес, г» число → кг = г/1000, source='grams_col';
      • иначе «Вес, кг»: правдоподобно (≤ порога) → как есть; неправдоподобно → трактуем как граммы
        (÷1000) c source='kg_col_reconciled_grams';
      • ничего числового → (None, 'unknown'): C3 честно скажет «вес неизвестен».
    Возвращает (weight_kg | None, source_str).
    """
    g = _num(grams_cell)
    if g is not None and g > 0:
        return round(g / 1000.0, 3), "grams_col"
    kg = _num(kg_cell)
    if kg is not None and kg > 0:
        if kg > _IMPLAUSIBLE_KG:
            return round(kg / 1000.0, 3), "kg_col_reconciled_grams"
        return round(kg, 3), "kg_col"
    return None, "unknown"


# ── Спека короба → _spec для профиля категории (ТОП-заполнение) ────────────────────────────
# Движок card.profile_parameter_values читает prod['_spec'] по ключам профиля kartonnye-koroba:
#   NUMERIC: length/width/height/weight/штук_в_упаковке ; ENUM: материал/слои_картона.
# ЗАКОН ЧЕСТНОСТИ: кладём ТОЛЬКО то, что подтверждено донором/физикой; не выдумываем valueId
# (несопоставленное значение движок сам молча отбросит — «лучше пусто, чем ложь»).

def derive_material(tip_kartona, material_col=None):
    """Материал короба для ENUM Маркета — из КОНСТРУКЦИИ (донорский «Тип картона»), не из волокна.

    ФАКТ, не выдумка: трёх-/пяти-/семислойный и микрогофрокартон = ГОФРОКАРТОН по определению
    (слои = лайнер+гофра+лайнер). Хром-эрзац = плотный коробочный КАРТОН (не гофро). Донорская
    колонка «Материал» (Целлюлоза/Макулатура) — это ВОЛОКНО (virgin/вторичка), а не то, что
    спрашивает ENUM Маркета; используем её лишь как запасной сигнал для целлюлозы.
    Не распознали конструкцию → None (честно; движок не пошлёт неподтверждённое)."""
    t = _lc(tip_kartona)
    if "гофро" in t or "слойн" in t:
        return "гофрокартон"
    if "хром" in t or "эрзац" in t:
        return "картон"
    m = _lc(material_col)
    if "целлюлоз" in m:
        return "целлюлоза"
    return None


def derive_layers(tip_kartona):
    """Слои картона — ТОЛЬКО из явного слова слойности («Трехслойный»/«Пятислойный»/…).

    Возвращаем донорское значение как есть — карта профиля (трехслойный→valueId и т.д.) резолвит
    его сама. Микрогофрокартон/Хром-эрзац число слоёв НЕ декларируют → None (не выдумываем слои)."""
    return tip_kartona if "слойн" in _lc(tip_kartona) else None


def build_box_spec(length=None, width=None, height=None, weight=None,
                   tip_kartona=None, material_col=None, kolvo=None):
    """Собрать _spec короба для профиля категории. Кладём только присутствующие/подтверждённые поля.

    Габариты приходят уже в СМ (÷10 сделал read_donor) и КОМПЛЕКТОМ (T5: без полного набора —
    read_donor их не кладёт, значит и сюда не попадут). Вес в КГ (реконсиляция единиц уже сделана)."""
    spec = {}
    if isinstance(length, (int, float)):
        spec["length"] = length
    if isinstance(width, (int, float)):
        spec["width"] = width
    if isinstance(height, (int, float)):
        spec["height"] = height
    if isinstance(weight, (int, float)):
        spec["weight"] = weight
    mat = derive_material(tip_kartona, material_col)
    if mat:
        spec["материал"] = mat
    lay = derive_layers(tip_kartona)
    if lay:
        spec["слои_картона"] = lay
    k = _num(kolvo)
    if k is not None and k > 0:
        spec["штук_в_упаковке"] = int(k)
    return spec


def enrich_description(base_desc, marka=None, forma=None, obem=None, ruchki=None, kolvo=None):
    """Донорское описание + БЛОК характеристик из РЕАЛЬНЫХ значений донора (всевозможные данные → ТОП).

    Только непустые/правдивые факты, для которых у категории НЕТ отдельного параметра (форма короба,
    марка гофры, объём, ручки). Ничего не выдумываем; форму короба сюда, а НЕ в ENUM «форма выпуска»
    (тот справочник — лист/рулон/бобина плёнки, чужая семантика для короба)."""
    base = _norm(base_desc)
    facts = []
    if _norm(forma):
        facts.append(f"Форма: {_norm(forma)}")
    if _norm(marka):
        facts.append(f"Марка картона: {_norm(marka)}")
    ob = _num(obem)
    if ob is not None and ob > 0:
        facts.append(f"Полезный объём: {ob:g} л")
    if _lc(ruchki).startswith("да"):
        facts.append("С ручками для переноски")
    k = _num(kolvo)
    if k is not None and k > 0:
        facts.append(f"В упаковке: {int(k)} шт.")
    if not facts:
        return base
    block = "Характеристики — " + "; ".join(facts) + "."
    return (base + "\n\n" + block).strip() if base else block


def breakeven_markup(cost, fee, min_profit=pricer.MIN_PROFIT_RUB):
    """Минимальная наценка к закупке, при которой сделка выходит за пол маржи ЦЕНОВИКА.

        пол = закупка + сборы + min_profit ;  breakeven_markup = пол / закупка
    Нет закупки/сборов → None (не считаем на выдуманных числах, L3)."""
    if not isinstance(cost, (int, float)) or cost <= 0:
        return None
    if not isinstance(fee, (int, float)) or fee < 0:
        return None
    floor = cost + fee + min_profit
    return round(floor / cost, 2)


def propose_prices(cost, markup_lo=DEFAULT_MARKUP_LO, markup_hi=DEFAULT_MARKUP_HI):
    """Предложение цены продажи (её нет в файле — C2). Возвращает (цена_lo, цена_hi).

    Консервативный конец (×markup_lo) идёт в экономику: если прибыльно на нём — прибыльно и выше.
    Нет закупки → (None, None)."""
    if not isinstance(cost, (int, float)) or cost <= 0:
        return None, None
    return round(cost * markup_lo, 2), round(cost * markup_hi, 2)


def score_item(item, city=None, cats=None, max_cost=DEFAULT_MAX_COST_RUB,
               markup_lo=DEFAULT_MARKUP_LO, markup_hi=DEFAULT_MARKUP_HI,
               min_profit=pricer.MIN_PROFIT_RUB):
    """Вердикт по одной нормализованной донорской позиции. Воспроизводимый разбор.

    item — {sku,name,cost,length,width,height(см),weight(кг),category_id|slug,stock_source,pictures}.
    Возвращает {sku,name,cost,verdict,proposed_low,proposed_high,markup_used,breakeven_markup,
                economics,fit,delivery,reasons,why,price_is_proposal}.
    verdict ∈ {'select','needs_data','reject'}.
    """
    sku = item.get("sku")
    name = item.get("name")
    cost = item.get("cost")
    cost = float(cost) if isinstance(cost, (int, float)) else None
    out = {
        "sku": sku, "name": name, "cost": cost, "verdict": None,
        "proposed_low": None, "proposed_high": None, "markup_used": None,
        "breakeven_markup": None, "economics": None, "fit": None, "delivery": None,
        "reasons": [], "why": "", "price_is_proposal": True,
    }
    # Идентичность/категория/габариты — переносим из нормализованной позиции, чтобы шорт-лист
    # был правдивым и годным для RUBICON-write (раннеру нужен category_id, чтобы карточка встала).
    for k in ("category", "slug", "category_id", "in_stock", "stock_source",
              "length", "width", "height", "weight", "weight_source", "pictures", "link",
              "description", "_spec"):
        if k in item:
            out[k] = item[k]

    # C1: закупка обязательна и положительна
    if cost is None or cost <= 0:
        out["verdict"] = "needs_data"
        out["reasons"].append("C1: нет донорской цены (нашей закупки) — предлагать нечего")
        out["why"] = "закупка неизвестна"
        return out

    # C4: порог закупки — врываемся дёшево
    if cost > max_cost:
        out["verdict"] = "reject"
        out["reasons"].append(f"C4: закупка {cost}₽ > порога {max_cost}₽ — дорого для входа")
        out["why"] = f"закупка {cost}₽ выше порога {max_cost}₽"
        return out

    lo, hi = propose_prices(cost, markup_lo, markup_hi)
    out["proposed_low"], out["proposed_high"] = lo, hi

    # Габариты/тариф/экономика — делегируем ТОВАРОВЕДУ (C3 живёт внутри: нет размеров → fit.ok=None).
    # Экономику меряем на КОНСЕРВАТИВНОМ конце (×markup_lo): пройдёт тут — пройдёт и выше.
    prod_lo = dict(item)
    prod_lo["price"] = lo
    verdict = merch.screen_one(prod_lo, city=city, cats=cats, min_profit=min_profit)
    out["fit"] = verdict.get("fit")
    out["delivery"] = verdict.get("delivery")
    out["economics"] = verdict.get("economics")
    out["reasons"].extend(verdict.get("reasons", []))

    # Порог безубыточной наценки — сколько минимум надо накинуть (для глаз оператора)
    fee = (verdict.get("delivery") or {}).get("cost")
    out["breakeven_markup"] = breakeven_markup(cost, fee, min_profit)
    out["markup_used"] = markup_lo

    mv = verdict.get("verdict")
    if mv == "approve":
        out["verdict"] = "select"
        econ = out["economics"] or {}
        out["why"] = (f"купить {cost}₽ → продать {lo}–{hi}₽ (×{markup_lo:g}–{markup_hi:g}), "
                      f"прибыль от {econ.get('profit')}₽ ({econ.get('margin_pct')}%)")
    elif mv == "needs_data":
        out["verdict"] = "needs_data"
        out["why"] = "нужны данные: " + "; ".join(out["reasons"][:3])
    else:
        # C5: даже при консервативной наценке экономика не сходится → отбой
        out["verdict"] = "reject"
        out["why"] = "; ".join(out["reasons"][:3]) or "экономика не сходится"
    return out


def rank(scored):
    """Ранжируем ТОЛЬКО отобранные (select) по прибыли (мандат «максимально в профите»),
    tiebreak — меньшая закупка (меньше связанного капитала). Возвращает новый отсортированный список."""
    def key(r):
        econ = r.get("economics") or {}
        profit = econ.get("profit")
        profit = profit if isinstance(profit, (int, float)) else -1e9
        cost = r.get("cost") if isinstance(r.get("cost"), (int, float)) else 1e9
        return (-profit, cost)
    return sorted([r for r in scored if r.get("verdict") == "select"], key=key)


# ── Донор-читатель (openpyxl; запускать под интерпретатором с openpyxl) ──────────────────────

# Донор-осознанный матч колонок: НАЗВАНИЯ реальной выгрузки shop.cargo-avto.ru.
def _donor_colmap(header_lc):
    """header_lc — список нижне-регистровых заголовков → {ключ: индекс}. Донор-осознанно."""
    idx = {}

    def find(pred, used):
        for i, h in enumerate(header_lc):
            if i in used or not h:
                continue
            if pred(h):
                return i
        return None

    used = set()
    # cost = донорская розница = НАША закупка. Точное «цена», НЕ «цена поставщика»/«валюта».
    ci = find(lambda h: h == "цена", used) or find(
        lambda h: h.startswith("цена") and "поставщик" not in h and "валют" not in h, used)
    if ci is not None:
        idx["cost"] = ci; used.add(ci)
    for key, pred in [
        ("sku",          lambda h: "артикул" in h or h == "sku"),
        ("name",         lambda h: "заголовок" in h or "наименование" in h or "название" in h),
        ("cat2",         lambda h: h == "категория 2"),
        ("cat1",         lambda h: h == "категория 1"),
        ("availability", lambda h: "наличие" in h and "ручек" not in h),
        ("length_mm",    lambda h: h.startswith("длина")),
        ("width_mm",     lambda h: h.startswith("ширина")),
        ("height_mm",    lambda h: h.startswith("высота")),
        ("weight_g",     lambda h: h == "вес, г" or h == "вес,г"),
        ("weight_kg",    lambda h: h == "вес, кг" or h == "вес,кг"),
        ("pictures",     lambda h: "изображен" in h),
        ("link",         lambda h: "ссылка" in h),
        ("description",  lambda h: "описание" in h),
        # ── Спец-колонки короба (всё опционально; профиль kartonnye-koroba → ТОП-заполнение) ──
        ("tip_kartona",  lambda h: "тип" in h and "картон" in h),   # Трехслойный/Микрогофрокартон → материал+слои
        ("material_col", lambda h: h == "материал"),                 # Целлюлоза/Макулатура (волокно, запасной сигнал)
        ("marka",        lambda h: "марка" in h and "картон" in h),  # Т-23 В — в описание
        ("forma",        lambda h: "форма" in h),                    # Плоская/Прямоугольная — в описание (НЕ ENUM выпуска!)
        ("kolvo",        lambda h: ("кол-во" in h or "количеств" in h) and "упаковк" in h),
        ("obem",         lambda h: "полезн" in h and "объ" in h),    # Полезный объём, л — в описание
        ("ruchki",       lambda h: "наличие" in h and "ручек" in h), # Наличие ручек — в описание
    ]:
        i = find(pred, used)
        if i is not None:
            idx[key] = i; used.add(i)
    return idx


def read_donor(xlsx_path, slug=None, cats=None):
    """Донорский XLSX → нормализованные позиции с дропшип-семантикой (C1). Fail-soft, 0₽, чистое чтение.

    Возвращает {'items':[...], 'colmap':{имя-колонки}, 'skipped':N, 'blocker':str|None, 'file','sheet'}.
    Каждая позиция: {sku,name,cost,length,width,height(см),weight(кг),weight_source,category,
                     slug,category_id,stock_source,in_stock,pictures,link,description}.
    ЧЕСТНОСТЬ: ни одной строки → блокер с ИМЕНЕМ (какой обязательной колонки нет), не пустой молчок.
    """
    try:
        import openpyxl
    except Exception as e:
        raise RuntimeError(f"openpyxl не установлен ({e}); донор-читатель недоступен")
    wb = openpyxl.load_workbook(str(xlsx_path), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    # ЖИВОЙ УРОК: read_only иногда кеширует размерность в 1 колонку — сбрасываем, иначе теряем данные.
    try:
        ws.reset_dimensions()
    except Exception:
        pass
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {"items": [], "colmap": {}, "skipped": 0, "file": str(xlsx_path),
                "sheet": ws.title, "blocker": f"Лист «{ws.title}» пуст", "header": []}
    header = [_norm(h) for h in rows[0]]
    header_lc = [_lc(h) for h in header]
    cm = _donor_colmap(header_lc)

    cats = cats if cats is not None else _safe_load_cats()
    items, skipped = [], 0

    def cell(r, key):
        i = cm.get(key)
        return r[i] if (i is not None and i < len(r)) else None

    for r in rows[1:]:
        sku = _norm(cell(r, "sku"))
        name = _norm(cell(r, "name"))
        cost = _num(cell(r, "cost"))
        if not sku or not name or cost is None or cost <= 0:
            skipped += 1
            continue
        L = _num(cell(r, "length_mm"))
        W = _num(cell(r, "width_mm"))
        H = _num(cell(r, "height_mm"))
        wkg, wsrc = resolve_weight_kg(cell(r, "weight_g"), cell(r, "weight_kg"))
        avail = _lc(cell(r, "availability"))
        in_stock = ("налич" in avail) if avail else None
        cat = _norm(cell(r, "cat2")) or _norm(cell(r, "cat1"))
        item_slug = slug or _slug_for_category(cat, cats)
        cat_id = card.market_category_id(item_slug, cats) if item_slug else None
        pics_raw = _norm(cell(r, "pictures"))
        pictures = _URL_RE.findall(pics_raw)
        item = {
            "sku": sku, "name": name, "cost": cost,
            "category": cat, "slug": item_slug, "category_id": cat_id,
            "in_stock": in_stock,
            "pictures": pictures, "link": _norm(cell(r, "link")),
            "description": _norm(cell(r, "description")),
            "weight_source": wsrc,
        }
        # Габариты в СМ (донор в мм). Кладём только полный набор (T5: без одного числа — не выдумываем).
        if L and W and H:
            item["length"], item["width"], item["height"] = round(L / 10.0, 2), round(W / 10.0, 2), round(H / 10.0, 2)
        if wkg is not None:
            item["weight"] = wkg
        # Источник наличия — «есть» только если донор прямо говорит «в наличии» (S1: лучше ноль, чем ложь).
        if in_stock is True:
            item["stock_source"] = "donor:в наличии"
        # ── ТОП-заполнение: _spec для профиля категории + факты в описание (всевозможные данные → ТОП) ──
        tip = _norm(cell(r, "tip_kartona"))
        forma = _norm(cell(r, "forma"))
        marka = _norm(cell(r, "marka"))
        obem = cell(r, "obem")
        ruchki = _norm(cell(r, "ruchki"))
        kolvo = cell(r, "kolvo")
        spec = build_box_spec(
            length=item.get("length"), width=item.get("width"), height=item.get("height"),
            weight=item.get("weight"), tip_kartona=tip,
            material_col=_norm(cell(r, "material_col")), kolvo=kolvo)
        if spec:
            item["_spec"] = spec
        item["description"] = enrich_description(
            item.get("description"), marka=marka, forma=forma, obem=obem, ruchki=ruchki, kolvo=kolvo)
        items.append(item)

    blocker = None
    if not items:
        need = [human for key, human in (("sku", "Артикул"), ("name", "Заголовок/Наименование"),
                                          ("cost", "Цена")) if key not in cm]
        if need:
            blocker = ("НЕ РАСПОЗНАНЫ ОБЯЗАТЕЛЬНЫЕ КОЛОНКИ: " + ", ".join(need)
                       + f". Заголовок листа «{ws.title}»: {header}")
        else:
            blocker = f"Все {skipped} строк отбракованы (нет sku/имени/цены)"
    return {"items": items, "colmap": {k: header[v] for k, v in cm.items()},
            "skipped": skipped, "blocker": blocker,
            "file": str(xlsx_path), "sheet": ws.title, "header": header}


def _safe_load_cats():
    try:
        return card.load_cats()
    except Exception:
        return {}


def _slug_for_category(cat_ru, cats):
    """Русское имя категории донора → slug из карты (по keywords). Не нашли → None (честно, need_mapping)."""
    if not cat_ru or not cats:
        return None
    # card.load_cats() отдаёт УЖЕ развёрнутый словарь categories (slug→entry).
    # На случай внешнего конверта {"categories": {...}} — разворачиваем ещё раз.
    inner = cats.get("categories") if isinstance(cats.get("categories"), dict) else cats
    low = _lc(cat_ru)
    for slug, entry in inner.items():
        if not isinstance(entry, dict):
            continue
        for kw in (entry.get("keywords") or []):
            if _lc(kw) in low or low in _lc(kw):
                return slug
    return None


# ── Оркестрация ─────────────────────────────────────────────────────────────────────────────

def shortlist(xlsx_path, city=None, max_cost=DEFAULT_MAX_COST_RUB,
              markup_lo=DEFAULT_MARKUP_LO, markup_hi=DEFAULT_MARKUP_HI, limit=20, slug=None):
    """Полный ход КАТЕГОРИЙЩИКА: донор → нормализация → оценка → ранжирование → отчёт. 0₽, без сети."""
    cats = _safe_load_cats()
    loaded = read_donor(xlsx_path, slug=slug, cats=cats)
    items = loaded["items"]
    scored = [score_item(it, city=city, cats=cats, max_cost=max_cost,
                          markup_lo=markup_lo, markup_hi=markup_hi) for it in items]
    selected = rank(scored)
    needs = [r for r in scored if r["verdict"] == "needs_data"]
    rejected = [r for r in scored if r["verdict"] == "reject"]

    profits = [(r["economics"] or {}).get("profit") for r in selected]
    profits = [p for p in profits if isinstance(p, (int, float))]
    agg = {
        "rows_read": len(items), "rows_skipped": loaded["skipped"],
        "selected": len(selected), "needs_data": len(needs), "rejected": len(rejected),
        "avg_profit_low_end": round(sum(profits) / len(profits), 2) if profits else None,
        "total_profit_low_end": round(sum(profits), 2) if profits else None,
    }
    return {
        "schema": "ymarket.categorist.shortlist.v1", "ts": _now_iso(), "role": CHARTER["id"],
        "file": loaded["file"], "sheet": loaded["sheet"], "colmap": loaded["colmap"],
        "blocker": loaded["blocker"], "city": city, "max_cost": max_cost,
        "markup_range": [markup_lo, markup_hi], "agg": agg,
        "shortlist": selected[:limit], "needs_data": needs[:limit], "rejected": rejected[:limit],
    }


def render(rep):
    """Человекочитаемый разбор шорт-листа (для CLI и ТГ-подводки)."""
    L = []
    L.append(f"📦 КАТЕГОРИЙЩИК · {Path(rep['file']).name}  лист='{rep['sheet']}'")
    if rep.get("blocker"):
        L.append(f"   ⛔ {rep['blocker']}")
        return "\n".join(L)
    a = rep["agg"]
    L.append(f"   колонки: {rep['colmap']}")
    L.append(f"   прочитано {a['rows_read']} (пропущено {a['rows_skipped']}) → "
             f"в шорт-лист {a['selected']}, нужны данные {a['needs_data']}, отбой {a['rejected']}")
    lo, hi = rep["markup_range"]
    L.append(f"   порог закупки ≤{rep['max_cost']:g}₽ · наценка ×{lo:g}–{hi:g} · город={rep['city'] or 'default'}")
    if a["total_profit_low_end"] is not None:
        L.append(f"   потенциал прибыли (консерв. конец): ~{a['total_profit_low_end']:g}₽ на партию, "
                 f"средняя {a['avg_profit_low_end']:g}₽/позиция")
    L.append("   — ТОП шорт-листа —")
    for r in rep["shortlist"][:12]:
        be = r.get("breakeven_markup")
        L.append(f"   • {r['sku']}  {str(r['name'])[:52]}")
        L.append(f"     купить {r['cost']:g}₽ → продать {r['proposed_low']:g}–{r['proposed_high']:g}₽ · {r['why']}"
                 + (f" · безубыток от ×{be:g}" if be else ""))
    if not rep["shortlist"] and rep["needs_data"]:
        L.append("   (шорт-лист пуст — но есть кандидаты, которым не хватает данных:)")
        for r in rep["needs_data"][:8]:
            L.append(f"   ~ {r['sku']} {str(r['name'])[:46]} — {r['why']}")
    return "\n".join(L)


def _main(argv=None):
    ap = argparse.ArgumentParser(description="КАТЕГОРИЙЩИК: донорский XLSX → шорт-лист под Экспресс (0₽, без сети)")
    ap.add_argument("xlsx", help="путь к донорской выгрузке (shop.cargo-avto.ru и совместимые)")
    ap.add_argument("--city", default=None, help="город доставки (москва даёт больше габаритов)")
    ap.add_argument("--max-cost", type=float, default=DEFAULT_MAX_COST_RUB, help="порог закупки, ₽")
    ap.add_argument("--markup-lo", type=float, default=DEFAULT_MARKUP_LO, help="нижняя наценка")
    ap.add_argument("--markup-hi", type=float, default=DEFAULT_MARKUP_HI, help="верхняя наценка")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--slug", default=None, help="принудительный slug категории (иначе — по keywords карты)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rep = shortlist(args.xlsx, city=args.city, max_cost=args.max_cost,
                    markup_lo=args.markup_lo, markup_hi=args.markup_hi,
                    limit=args.limit, slug=args.slug)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else render(rep))
    return 0


if __name__ == "__main__":
    sys.exit(_main())

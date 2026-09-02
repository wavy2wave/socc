#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОТДЕЛЫ ОЗОНА (ozon_departments_v1) — автономные отделы магазина, каждый со своим KPI и ДОКАЗАТЕЛЬСТВОМ.

Оператор дословно: «Цикл … знает все ОТДЕЛЫ ОЗОНА в контексте моего бизнеса — работают автономно.
Есть ответственный ежедневно, имеющий KPI, и его работа не просто добавить, а вся система видит,
что он УГАДАЛ, не просто с неба взял».

Вот эти отделы. Шесть штук — паутина, не конвейер (каждый читает СВОЙ срез памяти/кабинета и отвечает
за своё число). Отдел НЕ печатает цифру «с неба»: он раскладывает её в ЦЕПЬ доказательства
(ozon_evidence_v1) — [отдел]→[вход]→[формула]→[число] из замороженного снимка. Цикл дня реплеит цепь
по зарегистрированному рецепту и ставит grounded=True/False. А ЦЕНОВИК-ИНДЕКС вдобавок ЗАЯВЛЯЕТ ПРОГНОЗ
(«индекс будет GREEN») — позже реальное чтение кабинета сверит его как hit/miss. Так «угадал» — число, а
не слова.

ОТДЕЛЫ:
  ТОВАРОВЕД      (OZ_MERCH)      — что завести в ассортимент (маржа под econ; берём только 🟢).
  ЦЕНОВИК-ИНДЕКС (OZ_PRICER) ★   — цена + ИНДЕКС ЦЕН Озона (видимость) + ПРОГНОЗ цвета. Флагман «угадал».
  ЗАЛИВЩИК       (OZ_ZALIV)      — карточка DOWNLOADED→ON_SHELF: атрибуты/категория/фото; 200≠успех.
  СНАБЖЕНЕЦ      (OZ_SUPPLY)     — такт заказа Озона (SLA сборки/передачи): что горит.
  ОТГРУЗЧИК      (OZ_SHIPPER)    — этикетка/маркировка/передача в доставку в срок.
  КОНТРОЛЁР      (OZ_CONTROLLER) — индекс качества, errored→0, красный индекс = невидимость (ребро роста).

ЗАКОН ЧЕСТНОСТИ: нет данных для отдела (сухой прогон, кабинет не читали) → source='none', цепи нет,
человеку честно «нет данных: …». НЕ выдумываем занятость. Отдел, который только СЧИТАЕТ факт
(КОНТРОЛЁР/ЗАЛИВЩИК), прогнозов НЕ делает — прогнозирует лишь тот, кто вправе угадывать (ЦЕНОВИК-ИНДЕКС;
СНАБЖЕНЕЦ — риск срыва SLA). Прогноз без числовой опоры помечается weak (E3), чтобы KPI отделил
мастерство от везения.

stdlib-only, 0₽, без сети (данные приходят готовым срезом от памяти/кабинета). RUBICON цел: отделы
РАССУЖДАЮТ и ПРЕДЛАГАЮТ, наружу ничего не пишут.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ozon_evidence_v1 as evidence   # noqa: E402  — движок «не с неба взял» (цепь + прогноз)
import ozon_econ_v1 as econ           # noqa: E402  — маржа/индекс/вес (единый источник констант)
import ozon_state_v1 as state         # noqa: E402  — память + форма KPI (kpis/skus/lifecycle)

ASSESS_SCHEMA = "ozon.departments.assessment.v1"

# Порог маржи «зелёного» — совпадает с ЦЕНОВИКОМ ЯМ (MIN_MARGIN_PCT) и очками (min_margin_pct).
MIN_MARGIN_PCT = 5.0
# Порог «горит» по такту заказа Озона: минут до дедлайна ≤ этого → срочно (TUNABLE, оператор крутит).
SLA_URGENT_MIN = 30.0


# ── общие помощники чтения среза (отдел читает СВОЁ, чужого не трогает) ─────────────────────────
def _card_cost(rec):
    """Закупка карточки: явное поле cost, иначе cost_buy из сохранённой маржи, иначе None (не врём)."""
    if not isinstance(rec, dict):
        return None
    c = econ._num(rec.get("cost"))
    if c is not None:
        return c
    m = rec.get("margin")
    return econ._num(m.get("cost_buy")) if isinstance(m, dict) else None


def _project_index(item):
    """Спроецировать цвет индекса при цене продажи (текущей или предложенной). Чистая функция.

    Возврат (color, idx_num|None, quantified): quantified=True — проекция ОПИРАЕТСЯ на число
    (индекс задан числом, либо цена не меняется). quantified=False — цену меняем, а индекс дан лишь
    цветом → сдвиг посчитать нечем → прогноз будет weak (E3, честно «угадал без опоры»).

    Модель: price_index ≈ наша_цена / рынок. Тогда при новой цене P1: index1 = index0 · P1/P0.
    """
    i0 = item.get("price_index")
    n0 = econ._num(i0)
    p0 = econ._num(item.get("price"))
    p1 = econ._num(item.get("proposed_price"))
    changed = p1 is not None and p0 is not None and p1 != p0
    if n0 is not None and p0 and p0 > 0 and p1 is not None and p1 > 0:
        i1 = n0 * (p1 / p0)
        return econ.index_color(i1), round(i1, 4), True
    return econ.index_color(i0), (round(n0, 4) if n0 is not None else None), (not changed)


# ── РЕЦЕПТЫ (чистые compute(snapshot)->steps; регистрируются при импорте → журнал реплеим) ───────
@evidence.recipe("ozon.merch.assortment")
def _recipe_merch(snap):
    """ТОВАРОВЕД: кандидаты с закупкой → маржа каждого (econ) → сколько берём (🟢)."""
    items = snap.get("items") or []
    mm = snap.get("min_margin_pct")
    margins, take, profitable = [], 0, 0
    for it in items:
        m = econ.sku_margin({}, price=it.get("price"), cost=it.get("cost"))
        mp, pn = m.get("margin_pct"), m.get("profit_net")
        if mp is not None:
            margins.append(mp)
        if pn is not None and pn > 0:
            profitable += 1
            if mm is None or (mp is not None and mp >= mm):
                take += 1
    avg = round(sum(margins) / len(margins), 1) if margins else None
    return [
        evidence.make_step("ТОВАРОВЕД", "кандидаты с закупкой",
                           "n = |карточки, где известна закупка|", {"candidates": len(items)}),
        evidence.make_step("ЭКОНОМ", "маржа каждого",
                           "margin% = profit_net/price·100  (econ.sku_margin, receipt=price·0.298−cost−₽325)",
                           {"avg_margin_pct": avg, "profitable": profitable}),
        evidence.make_step("ТОВАРОВЕД", "вердикт ассортимента",
                           f"берём ⟺ profit_net>0 И margin ≥ {mm}%",
                           {"candidates": len(items), "take": take, "avg_margin_pct": avg}),
    ]


@evidence.recipe("ozon.pricer.index")
def _recipe_pricer(snap):
    """ЦЕНОВИК-ИНДЕКС ★: маржа пачки + проекция ЦВЕТА индекса (видимость) на каждой позиции."""
    items = snap.get("items") or []
    margins = []
    dist = {"green": 0, "yellow": 0, "red": 0, "unknown": 0}
    for it in items:
        m = econ.sku_margin({}, price=it.get("price"), cost=it.get("cost"))
        if m.get("margin_pct") is not None:
            margins.append(m["margin_pct"])
        color, _idx, _q = _project_index(it)
        key = {econ.INDEX_GREEN: "green", econ.INDEX_YELLOW: "yellow",
               econ.INDEX_RED: "red"}.get(color, "unknown")
        dist[key] += 1
    avg = round(sum(margins) / len(margins), 1) if margins else None
    return [
        evidence.make_step("ЦЕНОВИК", "позиции с ценой",
                           "n = |карточки с ценой|", {"tracked": len(items)}),
        evidence.make_step("ЭКОНОМ", "средняя маржа",
                           "margin% = profit_net/price·100 (econ)", {"avg_margin_pct": avg}),
        evidence.make_step("ИНДЕКС", "проекция цвета",
                           "index1 = index0·P1/P0 → цвет: ≤1.0 GREEN · ≤1.1 YELLOW · иначе RED",
                           {"green": dist["green"], "yellow": dist["yellow"],
                            "red": dist["red"], "unknown": dist["unknown"]}),
        evidence.make_step("ЦЕНОВИК", "вердикт",
                           "красный индекс = карточку прячут из органики (чинить/снимать)",
                           {"tracked": len(items), "red": dist["red"],
                            "green": dist["green"], "avg_margin_pct": avg}),
    ]


@evidence.recipe("ozon.zaliv.readiness")
def _recipe_zaliv(snap):
    """ЗАЛИВЩИК: распределение карточек по жизненному циклу → сколько ГОТОВО лететь на витрину."""
    items = snap.get("items") or []
    total = len(items)
    on_shelf = need_mapping = blocked_errors = ready = 0
    for it in items:
        lc = it.get("lifecycle")
        has_err = bool(it.get("has_errors"))
        nm = bool(it.get("need_mapping"))
        verified = bool(it.get("published_verified"))
        if lc == state.LC_ON_SHELF and verified:
            on_shelf += 1
        if has_err:
            blocked_errors += 1
        if nm:
            need_mapping += 1
        if lc in (state.LC_FILLED, state.LC_IMPORTED) and not has_err and not nm and not verified:
            ready += 1
    done = on_shelf + ready
    completeness = round(100.0 * done / total, 1) if total else None
    return [
        evidence.make_step("ЗАЛИВЩИК", "карточки под наблюдением",
                           "n = |skus|", {"total": total}),
        evidence.make_step("ЗАЛИВЩИК", "распределение по циклу",
                           "DOWNLOADED→IMPORTED→FILLED→ON_SHELF; ошибка/нужна привязка = стоп",
                           {"on_shelf": on_shelf, "need_mapping": need_mapping,
                            "blocked_errors": blocked_errors}),
        evidence.make_step("ЗАЛИВЩИК", "готовность к витрине",
                           "ready ⟺ (FILLED|IMPORTED) И без ошибок И без привязки И не на витрине; 200≠успех",
                           {"total": total, "ready": ready, "on_shelf": on_shelf,
                            "need_mapping": need_mapping, "blocked_errors": blocked_errors,
                            "completeness_pct": completeness}),
    ]


@evidence.recipe("ozon.supply.sla")
def _recipe_supply(snap):
    """СНАБЖЕНЕЦ-ДИСПЕТЧЕР: по такту заказа Озона — сколько горит и сколько уже просрочено."""
    orders = snap.get("orders") or []
    thr = econ._num(snap.get("urgent_threshold_min"))
    thr = SLA_URGENT_MIN if thr is None else thr
    urgent = breached = 0
    min_left = None
    for o in orders:
        sla = econ._num(o.get("sla_minutes"))
        el = econ._num(o.get("minutes_elapsed"))
        if sla is None or el is None:
            continue
        left = sla - el
        min_left = left if min_left is None else min(min_left, left)
        if left < 0:
            breached += 1
        elif left <= thr:
            urgent += 1
    return [
        evidence.make_step("ДИСПЕТЧЕР", "заказы в работе",
                           "n = |заказы с тактом|", {"orders": len(orders)}),
        evidence.make_step("ДИСПЕТЧЕР", "остаток такта",
                           "time_left = sla_minutes − minutes_elapsed", {"min_left": min_left}),
        evidence.make_step("ДИСПЕТЧЕР", "вердикт срочности",
                           f"горит ⟺ 0 ≤ time_left ≤ {thr:g} · просрочено ⟺ time_left < 0",
                           {"orders": len(orders), "urgent": urgent, "breached": breached}),
    ]


@evidence.recipe("ozon.shipper.dispatch")
def _recipe_shipper(snap):
    """ОТГРУЗЧИК: отправления → готово к передаче / уже отгружено / ждёт этикетку."""
    postings = snap.get("postings") or []
    ready = shipped = pending = 0
    for p in postings:
        if p.get("shipped"):
            shipped += 1
        elif p.get("label_ready"):
            ready += 1
        else:
            pending += 1
    return [
        evidence.make_step("ОТГРУЗЧИК", "отправления",
                           "n = |postings|", {"postings": len(postings)}),
        evidence.make_step("ОТГРУЗЧИК", "распределение",
                           "shipped | label_ready&¬shipped | ¬label_ready&¬shipped",
                           {"shipped": shipped, "ready": ready, "pending": pending}),
        evidence.make_step("ОТГРУЗЧИК", "вердикт",
                           "готово к передаче = этикетка есть И ещё не отгружено",
                           {"postings": len(postings), "ready": ready,
                            "shipped": shipped, "pending": pending}),
    ]


@evidence.recipe("ozon.controller.quality")
def _recipe_controller(snap):
    """КОНТРОЛЁР: дефекты (ошибки+красный индекс) → индекс качества → пускать ли рост."""
    tracked = int(econ._num(snap.get("tracked")) or 0)
    errored = int(econ._num(snap.get("errored")) or 0)
    index_red = int(econ._num(snap.get("index_red")) or 0)
    need_mapping = int(econ._num(snap.get("need_mapping")) or 0)
    defects = errored + index_red
    clean = max(0, tracked - errored - index_red)
    quality_index = round(100.0 * clean / tracked, 1) if tracked else None
    allow_growth = (errored == 0 and index_red == 0)
    return [
        evidence.make_step("КОНТРОЛЁР", "дефекты",
                           "defects = errored + index_red (красный = невидимость)",
                           {"errored": errored, "index_red": index_red,
                            "need_mapping": need_mapping, "defects": defects}),
        evidence.make_step("КОНТРОЛЁР", "индекс качества",
                           "quality = 100·(tracked − errored − index_red)/tracked",
                           {"quality_index": quality_index}),
        evidence.make_step("КОНТРОЛЁР", "вердикт ребра",
                           "рост разрешён ⟺ errored=0 И index_red=0 (сначала чистим, потом масштаб)",
                           {"quality_index": quality_index, "defects": defects,
                            "allow_growth": allow_growth}),
    ]


# ── CHARTERS (канон роли SOCC: 8 полей + kpi[source_of_truth] + proves_by) ──────────────────────
CHARTERS = {
    "OZ_MERCH": {
        "id": "OZ_MERCH", "name_ru": "ТОВАРОВЕД", "emoji": "🛒",
        "mandate": "заводить в ассортимент только то, что даёт наш профит по вменяемой цене",
        "owns": ["список кандидатов", "закупка донора", "маржа позиции"],
        "is_not": ["не выставляет цену (это ЦЕНОВИК)", "не двигает деньги"],
        "inputs": ["карточки с известной закупкой", "econ.sku_margin", "тренд/спрос (позже)"],
        "outputs": ["шорт-лист «взять» → ЦЕНОВИК/ЗАЛИВЩИК"],
        "laws": [
            "M1 нет закупки → не считаем маржу (честный пропуск, не выдумка)",
            f"M2 берём ⟺ profit_net>0 И маржа ≥ {MIN_MARGIN_PCT}%",
            "M3 число ассортимента заземляется цепью (ozon_evidence)",
        ],
        "kpi": [{"metric": "средняя маржа взятого", "target": "максимум",
                 "source_of_truth": "grounded-цепь ozon.merch.assortment"},
                {"metric": "кандидатов без закупки", "target": "→0",
                 "source_of_truth": "память state (cost/margin.cost_buy)"}],
        "proves_by": "каждое число выведено econ из закупки; реплей воспроизводит (не с неба)",
    },
    "OZ_PRICER": {
        "id": "OZ_PRICER", "name_ru": "ЦЕНОВИК-ИНДЕКС", "emoji": "💰",
        "mandate": "держать цену выше пола маржи И зелёный индекс цен (видимость в органике)",
        "owns": ["цена на витрине", "проекция цвета индекса", "прогноз индекса"],
        "is_not": ["не публикует карточку", "не выкупает у донора"],
        "inputs": ["цена/закупка/индекс карточки", "econ (маржа+цвет индекса)"],
        "outputs": ["решение по цене → ЗАЛИВЩИК", "ПРОГНОЗ цвета → КОНТРОЛЁР/цикл"],
        "laws": [
            "P1 красный индекс = карточку прячут → чинить или снимать",
            "P2 проекция цвета: index1 = index0·P1/P0 (числовой индекс) — иначе прогноз weak",
            "P3 прогноз индекса сверяется РЕАЛЬНЫМ чтением (hit/miss), а не словами",
        ],
        "kpi": [{"metric": "красных индексов", "target": "0",
                 "source_of_truth": "grounded-цепь ozon.pricer.index + реальный READ"},
                {"metric": "точность прогноза индекса", "target": "→100%",
                 "source_of_truth": "accuracy прогнозов (predict→score фактом)"}],
        "proves_by": "заявляет цвет ДО факта; чтение кабинета ставит hit/miss — система видит, угадал ли",
    },
    "OZ_ZALIV": {
        "id": "OZ_ZALIV", "name_ru": "ЗАЛИВЩИК", "emoji": "📦",
        "mandate": "довести карточку до витрины по-настоящему: DOWNLOADED→IMPORTED→FILLED→ON_SHELF",
        "owns": ["атрибуты карточки", "категория/привязка", "жизненный этап"],
        "is_not": ["не считает DONE по HTTP-коду (200≠успех)", "не придумывает категорию/атрибуты"],
        "inputs": ["skus памяти (lifecycle/errors/need_mapping/attrs)"],
        "outputs": ["готовые к витрине → публикация (по слову)"],
        "laws": [
            "Z1 DONE только ON_SHELF (модерация OK И visible И stock>0)",
            "Z2 нужна привязка/есть ошибка → карточка НЕ готова (не летит)",
            "Z3 готовность заземляется цепью из фактических этапов",
        ],
        "kpi": [{"metric": "готовность (completeness%)", "target": "→100%",
                 "source_of_truth": "grounded-цепь ozon.zaliv.readiness"},
                {"metric": "карточек с ошибкой", "target": "0",
                 "source_of_truth": "errors[] реального READ"}],
        "proves_by": "готовность = счёт фактических этапов; реплей воспроизводит распределение",
    },
    "OZ_SUPPLY": {
        "id": "OZ_SUPPLY", "name_ru": "СНАБЖЕНЕЦ-ДИСПЕТЧЕР", "emoji": "🚚",
        "mandate": "не проспать такт заказа Озона; выкуп у донора ТОЛЬКО после оплаченного заказа",
        "owns": ["таймер такта заказа", "риск срыва SLA"],
        "is_not": ["не закупает заранее (доктрина: не рискуем деньгами)", "не отгружает сам"],
        "inputs": ["заказы кабинета (sla_minutes/minutes_elapsed)"],
        "outputs": ["что горит → ОТГРУЗЧИК/оператор", "прогноз срыва SLA"],
        "laws": [
            "S1 горит ⟺ остаток такта мал; просрочено ⟺ такт вышел",
            "S2 нет заказов (сухой прогон) → source='none', ничего не выдумываем",
            "S3 прогноз срыва сверяется фактом (успел/не успел)",
        ],
        "kpi": [{"metric": "просроченных тактов", "target": "0",
                 "source_of_truth": "grounded-цепь ozon.supply.sla"},
                {"metric": "точность прогноза срыва", "target": "→100%",
                 "source_of_truth": "accuracy прогнозов SLA"}],
        "proves_by": "остаток такта = sla−elapsed из снимка; реплей воспроизводит; прогноз сверяется",
    },
    "OZ_SHIPPER": {
        "id": "OZ_SHIPPER", "name_ru": "ОТГРУЗЧИК", "emoji": "🏷",
        "mandate": "этикетка/маркировка и передача в доставку в срок, без потери отправлений",
        "owns": ["этикетки", "статус передачи в доставку"],
        "is_not": ["не двигает цены/деньги", "не считает доставленным то, что не передано"],
        "inputs": ["отправления кабинета (label_ready/shipped)"],
        "outputs": ["готовые к передаче", "факт отгрузки → норма дня"],
        "laws": [
            "SH1 готово к передаче = этикетка есть И ещё не отгружено",
            "SH2 нет отправлений → source='none' (честно, не выдумываем занятость)",
            "SH3 счёт отгрузки заземляется цепью",
        ],
        "kpi": [{"metric": "ждут этикетку (pending)", "target": "→0",
                 "source_of_truth": "grounded-цепь ozon.shipper.dispatch"},
                {"metric": "отгружено за день", "target": "= заказам",
                 "source_of_truth": "state.daily (shipped)"}],
        "proves_by": "счёт отправлений выведен из их статусов; реплей воспроизводит",
    },
    "OZ_CONTROLLER": {
        "id": "OZ_CONTROLLER", "name_ru": "КОНТРОЛЁР", "emoji": "🛡",
        "mandate": "держать магазин чистым: errored→0, красный индекс = невидимость; пускать рост только с чистого ребра",
        "owns": ["индекс качества магазина", "гейт роста"],
        "is_not": ["не угадывает — только СЧИТАЕТ факт (лучше ноль чем ложь)", "не публикует"],
        "inputs": ["kpis памяти (errored/index_red/need_mapping/tracked)"],
        "outputs": ["разрешение на рост / стоп → цикл"],
        "laws": [
            "C1 дефект = ошибка ИЛИ красный индекс",
            "C2 рост разрешён ⟺ errored=0 И index_red=0 (сначала чистим)",
            "C3 КОНТРОЛЁР не прогнозирует — считает факт (честность важнее эффектности)",
        ],
        "kpi": [{"metric": "индекс качества", "target": "→100",
                 "source_of_truth": "grounded-цепь ozon.controller.quality"},
                {"metric": "дефектов (errored+red)", "target": "0",
                 "source_of_truth": "kpis реального READ"}],
        "proves_by": "индекс качества выведен из счётчиков дефектов; реплей воспроизводит",
    },
}

# Порядок паутины (для смены/фида): что брать → за сколько → залить → заказ → отгрузка → контроль.
DEPARTMENT_ORDER = ["OZ_MERCH", "OZ_PRICER", "OZ_ZALIV", "OZ_SUPPLY", "OZ_SHIPPER", "OZ_CONTROLLER"]


# ── упаковка результата отдела ──────────────────────────────────────────────────────────────────
def _charter(dept):
    return CHARTERS[dept]


def _result(dept, source, chain=None, predictions=None, human="", verdict=None):
    ch = _charter(dept)
    return {
        "dept": dept, "name_ru": ch["name_ru"], "emoji": ch["emoji"],
        "source": source,                                  # "memory" | "live" | "none"
        "chain": chain,
        "grounded": (chain.get("grounded") if isinstance(chain, dict) else None),
        "predictions": predictions or [],
        "verdict": (verdict if verdict is not None
                    else (chain.get("verdict") if isinstance(chain, dict) else {})),
        "human": human,
        "ok": True,
    }


def _emit(dept, question, snapshot, recipe_key):
    """Построить цепь отдела и сразу заземлить её реплеем (grounded=True/False)."""
    ch = evidence.build(dept, question, snapshot, recipe_key)
    evidence.ground(ch)
    return ch


# ── ОТДЕЛЫ · assess(ctx) → {chain(grounded), predictions?, verdict, human, source} ───────────────
def assess_merch(ctx):
    cards = ctx.get("cards") or []
    items = [{"oid": r.get("offer_id"), "price": econ._num(r.get("price")), "cost": _card_cost(r)}
             for r in cards if _card_cost(r) is not None and econ._num(r.get("price")) is not None]
    if not items:
        return _result("OZ_MERCH", "none",
                       human="нет кандидатов с известной закупкой — считать маржу не из чего (M1).")
    ch = _emit("OZ_MERCH", "что стоит завести в ассортимент",
               {"items": items, "min_margin_pct": MIN_MARGIN_PCT}, "ozon.merch.assortment")
    v = ch["verdict"]
    human = (f"кандидатов {v.get('candidates')} · берём {v.get('take')} "
             f"(маржа ≥ {MIN_MARGIN_PCT:g}%) · средняя маржа {v.get('avg_margin_pct')}%")
    return _result("OZ_MERCH", "memory", chain=ch, human=human)


def assess_pricer(ctx):
    """★ ФЛАГМАН: маржа+индекс пачки (заземлено) + ПРОГНОЗ цвета индекса по каждой позиции."""
    cards = ctx.get("cards") or []
    items = [{"oid": r.get("offer_id"), "price": econ._num(r.get("price")),
              "cost": _card_cost(r), "price_index": r.get("price_index"),
              "proposed_price": econ._num(r.get("proposed_price"))}
             for r in cards if econ._num(r.get("price")) is not None]
    if not items:
        return _result("OZ_PRICER", "none",
                       human="нет карточек с ценой — индекс проецировать не на чем.")
    ch = _emit("OZ_PRICER", "какой индекс/маржу даёт цена", {"items": items}, "ozon.pricer.index")

    # ПРОГНОЗ на каждую позицию: заявляем цвет индекса ДО факта (сверит реальный READ).
    preds = []
    for it in items:
        color, _idx, quantified = _project_index(it)
        if color is None:
            continue                       # индекса нет → не выдумываем прогноз
        at_price = it.get("proposed_price") if it.get("proposed_price") is not None else it.get("price")
        preds.append(evidence.predict(
            "OZ_PRICER", "index_color", color,
            basis=(f"ozon.pricer.index/{it.get('oid')}" if quantified else None),  # не число → weak (E3)
            horizon="next_read", ctx={"sku": it.get("oid"), "at_price": at_price}))
    v = ch["verdict"]
    human = (f"позиций {v.get('tracked')} · 🔴 индекс {v.get('red')} · 🟢 {v.get('green')} · "
             f"средняя маржа {v.get('avg_margin_pct')}% · прогнозов {len(preds)} "
             f"(сверю чтением)")
    return _result("OZ_PRICER", "memory", chain=ch, predictions=preds, human=human)


def assess_zaliv(ctx):
    cards = ctx.get("cards") or []
    if not cards:
        return _result("OZ_ZALIV", "none", human="карточек под наблюдением нет — заливать нечего.")
    items = [{"oid": r.get("offer_id"), "lifecycle": r.get("lifecycle"),
              "has_errors": bool(r.get("errors")), "need_mapping": bool(r.get("need_mapping")),
              "published_verified": bool(r.get("published_verified"))} for r in cards]
    ch = _emit("OZ_ZALIV", "сколько карточек готово на витрину",
               {"items": items}, "ozon.zaliv.readiness")
    v = ch["verdict"]
    human = (f"всего {v.get('total')} · готово лететь {v.get('ready')} · на витрине {v.get('on_shelf')} · "
             f"нужна привязка {v.get('need_mapping')} · с ошибкой {v.get('blocked_errors')} "
             f"(заполненность {v.get('completeness_pct')}%)")
    return _result("OZ_ZALIV", "memory", chain=ch, human=human)


def assess_supply(ctx):
    orders = ctx.get("orders") or []
    shaped = [{"order_id": o.get("order_id") or o.get("posting_number"),
               "sla_minutes": econ._num(o.get("sla_minutes")),
               "minutes_elapsed": econ._num(o.get("minutes_elapsed"))}
              for o in orders
              if econ._num(o.get("sla_minutes")) is not None
              and econ._num(o.get("minutes_elapsed")) is not None]
    if not shaped:
        return _result("OZ_SUPPLY", "none",
                       human="заказов с тактом нет (сухой прогон/кабинет не читали) — такт не горит (S2).")
    ch = _emit("OZ_SUPPLY", "что горит по такту заказа",
               {"orders": shaped, "urgent_threshold_min": SLA_URGENT_MIN}, "ozon.supply.sla")
    # ПРОГНОЗ срыва SLA: заявляем «сорвётся» тем, у кого такт уже почти вышел (сверит факт отгрузки).
    preds = []
    for o in shaped:
        left = o["sla_minutes"] - o["minutes_elapsed"]
        preds.append(evidence.predict(
            "OZ_SUPPLY", "will_breach_sla", bool(left <= 0),
            basis=f"ozon.supply.sla/{o.get('order_id')}",
            horizon="day", ctx={"order_id": o.get("order_id"), "left_min": round(left, 1)}))
    v = ch["verdict"]
    human = (f"заказов {v.get('orders')} · 🔥 горит {v.get('urgent')} · просрочено {v.get('breached')} "
             f"· прогнозов срыва {len(preds)}")
    return _result("OZ_SUPPLY", "live", chain=ch, predictions=preds, human=human)


def assess_shipper(ctx):
    postings = ctx.get("postings") or []
    if not postings:
        return _result("OZ_SHIPPER", "none",
                       human="отправлений нет (сухой прогон/кабинет не читали) — отгружать нечего (SH2).")
    shaped = [{"posting_id": p.get("posting_id") or p.get("posting_number"),
               "label_ready": bool(p.get("label_ready")), "shipped": bool(p.get("shipped"))}
              for p in postings]
    ch = _emit("OZ_SHIPPER", "что готово к передаче в доставку",
               {"postings": shaped}, "ozon.shipper.dispatch")
    v = ch["verdict"]
    human = (f"отправлений {v.get('postings')} · готово {v.get('ready')} · "
             f"отгружено {v.get('shipped')} · ждут этикетку {v.get('pending')}")
    return _result("OZ_SHIPPER", "live", chain=ch, human=human)


def assess_controller(ctx):
    k = ctx.get("kpis") or {}
    snap = {"tracked": k.get("tracked"), "errored": k.get("cards_errored"),
            "index_red": k.get("index_red"), "need_mapping": k.get("need_mapping")}
    if not k.get("tracked"):
        return _result("OZ_CONTROLLER", "none",
                       human="карточек нет — контролировать нечего (пусто остаётся пустым).")
    ch = _emit("OZ_CONTROLLER", "чист ли магазин, пускать ли рост",
               snap, "ozon.controller.quality")
    v = ch["verdict"]
    gate = "рост РАЗРЕШЁН" if v.get("allow_growth") else "рост СТОП — сначала чистим"
    human = (f"индекс качества {v.get('quality_index')} · дефектов {v.get('defects')} "
             f"(ошибок {snap['errored']} · красных {snap['index_red']}) → {gate}")
    return _result("OZ_CONTROLLER", "memory", chain=ch, human=human)


_ASSESSORS = {
    "OZ_MERCH": assess_merch, "OZ_PRICER": assess_pricer, "OZ_ZALIV": assess_zaliv,
    "OZ_SUPPLY": assess_supply, "OZ_SHIPPER": assess_shipper, "OZ_CONTROLLER": assess_controller,
}


# ── смена всех отделов ──────────────────────────────────────────────────────────────────────────
def assess_all(doc=None, cabinet=None, orders=None, postings=None):
    """Прогнать ВСЕ отделы по текущему срезу памяти/кабинета. Fail-soft: падение одного ≠ смерть смены.

    doc — память (state.load() по умолчанию). cabinet/orders/postings — живой READ кабинета (сухой
    прогон → пусто, отделы честно скажут source='none'). Возврат — сводка смены + все цепи и прогнозы,
    заземлённость и (пока пустая до сверки) точность прогнозов для KPI-свёртки.
    """
    doc = state.load() if doc is None else doc
    kpis = state.kpis(doc)
    ctx = {"doc": doc, "kpis": kpis, "skus": doc.get("skus", {}),
           "cards": list(doc.get("skus", {}).values()),
           "cabinet": cabinet or {}, "orders": orders or [], "postings": postings or []}

    results, chains, predictions = [], [], []
    for dept in DEPARTMENT_ORDER:
        try:
            r = _ASSESSORS[dept](ctx)
        except Exception as e:                     # fail-soft (закон B2): отдел упал — его строка «не смог»
            ch = _charter(dept)
            r = {"dept": dept, "name_ru": ch["name_ru"], "emoji": ch["emoji"], "source": "none",
                 "chain": None, "grounded": None, "predictions": [], "verdict": {},
                 "ok": False, "error": f"{type(e).__name__}: {e}",
                 "human": f"не смог отработать: {type(e).__name__}"}
        results.append(r)
        if isinstance(r.get("chain"), dict):
            chains.append(r["chain"])
        predictions.extend(r.get("predictions") or [])

    return {
        "schema": ASSESS_SCHEMA,
        "ts": evidence._now(),
        "live": bool(cabinet or orders or postings),
        "departments": results,
        "chains": chains,
        "predictions": predictions,
        "groundedness": evidence.groundedness(chains),
        "accuracy": evidence.accuracy(predictions),     # до сверки фактом — pending
    }


def resolve_predictions(predictions, actual_cards):
    """Пришёл реальный READ → сверить прогнозы отделов с фактом (ставит hit/miss).

    actual_cards — список карточек или {oid: card} с фактическим price_index (цвет/число). Сверяем
    прогнозы index_color по совпадению SKU. Это и есть «система видит, что угадал»: заявленный ДО
    факта цвет сравнивается с реально прочитанным. Нераспознанные метрики/без факта → остаются pending.
    """
    if isinstance(actual_cards, dict):
        by_oid = dict(actual_cards)
    else:
        by_oid = {}
        for c in (actual_cards or []):
            oid = c.get("offer_id") or c.get("offerId") or c.get("oid")
            if oid:
                by_oid[oid] = c
    out = []
    for p in predictions:
        if p.get("hit") is not None:                 # уже сверено — не трогаем
            out.append(p)
            continue
        oid = (p.get("ctx") or {}).get("sku")
        card = by_oid.get(oid) if oid else None
        if p.get("metric") == "index_color" and isinstance(card, dict):
            actual = econ.index_color(card.get("price_index"))
            if actual is not None:
                out.append(evidence.score(p, actual))
                continue
        out.append(p)                                 # факта нет → остаётся pending
    return out


def render(assessment):
    """Человеческая смена: строка на отдел (кто что увидел + заземлено ли + сколько прогнозов)."""
    g = assessment.get("groundedness") or {}
    lines = [f"🏢 ОТДЕЛЫ ОЗОНА · смена {assessment.get('ts','')[:19]} · "
             f"{'ЖИВОЙ кабинет' if assessment.get('live') else 'СУХО (память, 0₽)'}",
             f"   заземлено {g.get('grounded')}/{g.get('checked')} цепей "
             f"({g.get('grounded_pct')}%) · прогнозов {len((assessment.get('predictions') or []))}"]
    mark = {True: "✅", False: "❌", None: "…"}
    for r in assessment.get("departments", []):
        gm = mark.get(r.get("grounded"), "…") if r.get("source") != "none" else "·"
        preds = f" · 🔮{len(r['predictions'])}" if r.get("predictions") else ""
        lines.append(f"   {gm} {r.get('emoji','')} {r.get('name_ru',''):<18} {r.get('human','')}{preds}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ОТДЕЛЫ ОЗОНА — автономная смена (цепь+прогноз, 0₽)")
    ap.add_argument("--charter", metavar="DEPT", nargs="?", const="ALL",
                    help="показать CHARTER отдела (или ALL)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.charter:
        out = CHARTERS if args.charter == "ALL" else CHARTERS.get(args.charter.upper())
        print(json.dumps(out, ensure_ascii=False, indent=2))
        sys.exit(0)

    # Сухая демонстрация на выдуманной памяти (0 сети, 0₽): смена + «угадал» + ловля подделки.
    demo_doc = {
        "schema": state.SCHEMA, "working_set": [], "daily": {}, "counters": {},
        "skus": {
            "OZ-1": {"offer_id": "OZ-1", "price": 990, "cost": 400, "price_index": "GREEN",
                     "lifecycle": state.LC_ON_SHELF, "published_verified": True, "errors": []},
            "OZ-2": {"offer_id": "OZ-2", "price": 1490, "cost": 500, "price_index": 1.25,
                     "lifecycle": state.LC_FILLED, "errors": []},                       # красный индекс
            "OZ-3": {"offer_id": "OZ-3", "price": 600, "cost": 550, "price_index": None,
                     "lifecycle": state.LC_IMPORTED, "need_mapping": True, "errors": []},
            "OZ-4": {"offer_id": "OZ-4", "price": 350, "lifecycle": state.LC_DOWNLOADED,
                     "errors": ["attr:brand required"]},                                # ошибка
        },
    }
    a = assess_all(doc=demo_doc)
    print(render(a))
    print()
    pricer = next(r for r in a["departments"] if r["dept"] == "OZ_PRICER")
    print(evidence.render_chain(pricer["chain"]))

    # «Угадал?»: сверяем прогнозы ЦЕНОВИКА с ФАКТОМ чтения (OZ-2 остался красным, OZ-1 позеленел).
    actual = {"OZ-1": {"price_index": "GREEN"}, "OZ-2": {"price_index": "RED"}}
    resolved = resolve_predictions(a["predictions"], actual)
    acc = evidence.accuracy(resolved)
    print(f"\nпрогнозы индекса сверены с фактом → точность: {acc}")

    # «Не с неба»: руками портим число в цепи мимо формулы → реплей ловит (grounded=False).
    faked = json.loads(json.dumps(pricer["chain"]))
    faked["steps"][-1]["out"]["red"] = 0
    evidence.ground(faked)
    print("подделка red=0 в цепи ЦЕНОВИКА:", "заземлено" if faked["grounded"] else "❌ поймано (не с неба)")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЯНДЕКС — ПРИЁМКА «ВЫБОР→ЗАЛИВ в цикл»: сухая сборка партии → ready_to_publish (0₽, без сети).

Провязка рунга 1→3 (ВЫБОР→ЗАЛИВ): ГОЛОВА/КАТЕГОРИЙЩИК предлагают, но цикл не знал, «сколько реально
полетит». Источник ЗАЛИВА сухо собирает партию из донора (runner.preflight → publish_card dry) и даёт
готовность. ready_to_publish обязан браться из РЕАЛЬНОГО «полетит», а не из памяти. Проверяем ЗАКОНЫ
(каждый можно провалить), а не «оно запустилось». Всё герметично: фейки швов, ни xlsx, ни параллельной
линии, ни сети. RUBICON цел (dry, 0₽).

  АДАПТЕР readiness (изоляция шва к runner.preflight — чистая функция)
    ZR1  ready_from_agg_ok        — ready = agg.ok (собралось и категория подтверждена = «полетит»)
    ZR2  none_ready_not_zero      — агрегата нет → ready=None, НИКОГДА 0 (анти-ложь: 0 = «ничего не полетело»)
    ZR3  error_skus_match_errors  — len(error_skus) == agg.build_error (не соврать «0 ошибок» при непустом)
    ZR4  donor_blocker_as_data    — пустой лист/не тот файл → donor_blocker (ДАННЫЕ), не исключение
    ZR5  topfill_min_synced       — TOPFILL_MIN == 6 (контракт с runner.preflight; порогам расходиться нельзя)

  build_preflight_fn (thunk: ленивый, чистый, швы для тестов)
    ZB1  thunk_lazy               — сборка thunk НЕ трогает швы; вызов thunk → готовность (ленивость)
    ZB2  cats_injected_not_loaded — cats поданы швом → load_cats НЕ зовётся, preflight получил их
    ZB3  cats_loaded_when_none    — cats=None → load_cats зовётся, его результат уходит в preflight
    ZB4  chain_wired              — цепь shortlist→to_prod→preflight, slug прокинут в preflight

  collect_kpis (перекрытие памяти живой готовностью)
    KZ1  no_zaliv_uses_memory     — без сводки залива ready_to_publish берётся из памяти (обратная совм.)
    KZ2  live_overrides_memory    — сводка есть → live ready перекрывает память
    KZ3  none_ready_keeps_memory  — сводка есть, но ready=None → память сохраняется (не врём «live»)

  run_day (мёртвый сокет preflight_fn оживлён; B2 + RUBICON)
    WZ1  socket_stores_and_source — inject thunk → day.zaliv заполнен, ready_to_publish_source=zaliv_live
    WZ2  no_preflight_keeps_memory— без thunk → zaliv=None, source=memory, поведение как раньше (совм.)
    WZ3  none_ready_source_memory — thunk дал ready=None → source=memory (не фейковый zaliv_live)
    WZ4  failure_survived         — thunk упал → день выжил (B2), провал назван ZALIV, source=memory
    WZ5  batch_errors_burn        — thunk дал ошибки сборки → «что горит» называет SKU (планка YM1 до залива)
    WZ6  dry_rubicon              — цикл остаётся dry=True/commit=False; наружу ничего (0₽)
    WZ7  live_socket_zaliv_live   — ЖИВОЙ thunk в день → zaliv.ready, ready_to_publish_source=zaliv_live

  ЖИВОЙ ДОНОР (cargo-avto slug, без файлов) — ветка решается на диске при вызове thunk (F6: два слага!)
    ZB5  live_rows_priority       — live_rows поданы швом → приоритет над сканом (scan НЕ зовётся), ready живой
    ZB6  scan_adapter_called      — нет live_rows → scan_adapter зовётся: category=URL-путь, limit прокинут
    ZB7  live_cats_injected       — cats поданы → load_cats НЕ зовётся, preflight получил именно их
    ZB8  is_live_source_discr     — дисковая ветка: kebab-slug→live, файл/путь/None/''→xlsx (не угадать)
    ZB9  dual_slug_contract       — scan ест URL-путь (vozdushno-…), preflight — JSON-ключ (puzyrkovaya-…)
    ZB10 live_build_lazy          — сборка живого thunk ничего не вызывает; вызов → live_shortlist/to_prod/preflight

  МАППЕР ЖИВОГО СКАНА (честность: чего нет — того нет; C3/T5)
    ZM1  map_live_row_honest      — cost/происхождение едут, габаритов посылки НЕТ (не выдумываем), in_stock=None
    ZM2  map_live_row_drops_muck  — без sku/имени/цены → None (мусор), cost≤0 → None

  ЖИВОЙ ДОНОР в цикл (блокер ≠ live; герметичность; реальная цепь)
    ZR6  live_empty_scan_blocker  — скан пуст → donor_blocker «скан вернул пусто», ready=None, preflight НЕ зовётся
    ZR7  readiness_source_deriv   — source: 'live' из file='live:…', 'xlsx' из файла, иначе 'memory'
    ZR8  needs_data_surfaced      — честный T5: needs_data/rejected/grid из шорт-листа доходят в сводку
    ZH1  hermetic_live            — сборка+вызов живого thunk (со швами) НЕ импортируют runner/write/categorist/card
    ZM3  real_chain_offline       — РЕАЛЬНАЯ цепь без швов (scan фейк): нет габаритов → needs_data → selected=0
                                    → preflight([]) → ready=0 честно; donor_blocker=None, source='live'

  ОВХ-СЛОЙ + НАЛИЧИЕ (закрываем T5 И T4 ВМЕСТЕ — закон находки 2026-09-01)
    OH1  enrich_before_shortlist  — enrich_fn зовётся ровно раз с СЫРЫМ сканом (sku/url), ДО маппинга и шорт-листа
    OH2  dims_weight_survive_map  — ОВХ-габариты/вес (flat + dims_source/weight_source) маппер НЕ теряет
    OH3  stock_survives_map       — наличие (in_stock/stock_source) маппер НЕ теряет
    OH4  dims_stock_leave_needs   — РЕАЛЬНАЯ цепь: ОВХ-габариты посылки + живое наличие → selected=2,
                                    needs_data=0, ready=2, errors=0, parcel_dims=2 (ср. ZM3: 0/2)
    OH5  dims_only_keeps_needs    — ЗАКОН НАХОДКИ T4: габариты БЕЗ наличия НЕ выносят из needs_data (2/0)
    OH6  stock_only_keeps_needs   — зеркало OH5: наличие БЕЗ габаритов тоже держит needs_data (T5)
    OH7  stock_gate_hermetic      — _live_stock с article='' → 0 marked, donor_stock НЕ импортируется (сеть не тронута)
    OH8  parcel_dims_surfaced     — габариты посылки (parcel_dims) доходят из агрегата в сводку (0₽ GET)
    OH9  render_ovh_line          — отчёт оператору: строка «габариты посылки из карточки донора: N (ОВХ-слой, 0₽)»
    OH10 max_cost_mirror          — потолок закупки 700₽ зеркалит КАТЕГОРИЙЩИК (C4 не тратит патроны донора)
    OH11 ovh_module_stdlib        — ОВХ-слой в свежем питоне тянет только stdlib (не уронит сутки чужими импортами)
    OH12 enrich_pred_weight_honest— только url+dims_raw обогащаются; веса без «Вес» НЕ выдумываем (закон L3)
    OH13 defaults_exposed         — dims/stock_deadline по умолч. ==360/300 (ЖИВОЙ ЗАМЕР 2026-09-01: 45 карточек
                                   ≈296с, 18 наличие ≈168с; бюджет ниже реальности = гонка → нечестный selected=0),
                                   enrich_fn=None (default = ОВХ+наличие)
    OH14 stock_only_for_dims      — живое наличие спрашиваем ТОЛЬКО у позиций с габаритами (без габаритов T5 —
                                   к донору за наличием НЕ ходим, экономим патроны)

  ФОТО-СЛОЙ (паутина 🟢 ИМЯ→ФОТО→КАРТОЧКА; третий шов build_preflight_fn: products → products с pictures[])
    PH1  default_off_layer_silent — без YM_ZALIV_PHOTOS слой НЕ зовут вовсе: сводка photos=None («не звали»),
                                    photo_pipeline_v1 НЕ импортирован, кузница (~$0.02/кадр) не тратит ни ₽;
                                    no_pictures честно стоит (фото не было — бренд-замок отсечёт)
    PH2  dry_never_lies           — ЗАКОН ЧЕСТНОСТИ: mode='dry' → acquire зовётся с dry=True (это и есть механизм
                                    правды — реальный acquire_photos в сухом режиме вернёт urls=[]); кадров нет →
                                    pictures пусты, no_pictures НЕ снят. Сухое НЕ похоже на живое, не врём себе
    PH3  real_urls_fell_the_wall  — как только у prod СВОИ https-URL (слой дал кадры) → no_pictures=0: партия
                                    проходит бренд-замок. Пруф, что паутина держится на пикселях
    PH4  cap_bounds_spend         — потолок кадров за прогон: арг > env YM_ZALIV_PHOTOS_MAX > 4; отрицательный → 0
                                    (опечатка оператора не сожжёт деньги: каждый кадр живьём = ₽)
    PH5  fail_soft_day_survives   — сбой производителя ПО ПОЗИЦИИ → провенанс _photo.error, остальные обслужены;
                                    крах ВСЕГО слоя → _safe цикла (B2): день выживает, провал назван ZALIV
                                    (фото не может уронить сутки — деградация, а не остановка)
    PH6  lazy_import_boundary     — build thunk и путь со швом НЕ импортируют photo_pipeline_v1 (импорт только
                                    когда реальный слой пойдёт добывать кадры). Дефолтный цикл не тянет фото-цепь
    PH7  deadline_guards_the_day  — бюджет ОДНОГО фото-производства (PHOTO_DEADLINE): медленный/виснущий
                                    искатель (vision-гейт до 180с/кадр) НЕ держит сутки — позиция честно
                                    пропускается с _photo.why про бюджет, остальные обслужены, no_pictures не врёт
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
SCRIPTS = MINT.parent
for p in (str(ARB), str(MINT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_zaliv_source_v1 as zaliv_source     # noqa: E402
import ymarket_day_v1 as day_mod                   # noqa: E402

# Герметичность: журнал дня уводим на несуществующий путь (день не пишем на диск), состояние не трогаем.
os.environ["YM_DAY_JOURNAL"] = os.path.join(tempfile.gettempdir(), "ymzaliv_hermetic_journal.jsonl")
try:
    os.remove(os.environ["YM_DAY_JOURNAL"])
except OSError:
    pass


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _mem_st(ready_to_publish):
    """Само-модель со значением ready_to_publish В ПАМЯТИ (для проверки перекрытия)."""
    return {"kpis": {"cards_tracked": 9, "cards_live": 1, "cards_errored": 0,
                     "ready_to_publish": ready_to_publish, "avg_content_rating": 40}}


def _run_day(preflight_fn=None):
    """Герметичный день: без смены/тика/сети/env/журнала. Только сокет ИСТОЧНИКА ЗАЛИВА живой."""
    return day_mod.run_day(shift_fn=False, tick_fn=False, use_env=False, remember=False,
                           business_id="TESTBIZ", preflight_fn=preflight_fn)


# ─────────────────────────── АДАПТЕР readiness ───────────────────────────

def zr1_ready_from_agg_ok():
    """ready = agg.ok: собралось без ошибки И категория подтверждена = «полетит» (единый язык с preflight)."""
    pre = {"agg": {"ok": 4, "build_error": 0, "topfill": 3, "total": 5,
                   "need_mapping": 1, "no_pictures": 0}, "rows": []}
    z = zaliv_source.readiness(pre, slug="plenka")
    ok = z["ready"] == 4 and z["errors"] == 0 and z["topfill"] == 3 and z["total"] == 5 and z["configured"]
    return ok, f"ready={z['ready']} errors={z['errors']} topfill={z['topfill']} total={z['total']}"


def zr2_none_ready_not_zero():
    """Анти-ложь: сборка не дала агрегата → ready=None (честно «не собирал»), НИКОГДА фейковый 0."""
    z_empty = zaliv_source.readiness({}, slug="plenka")
    z_none = zaliv_source.readiness(None)
    ok = z_empty["ready"] is None and z_none["ready"] is None
    return ok, f"ready(empty)={z_empty['ready']} ready(None)={z_none['ready']} (оба None, не 0)"


def zr3_error_skus_match_errors():
    """len(error_skus) == agg.build_error: непустой errors[] ИЛИ exception → SKU в списке (не соврать «0»)."""
    pre = {"agg": {"ok": 1, "build_error": 2, "total": 3},
           "rows": [{"sku": "A", "errors": ["cat"]}, {"sku": "B", "stage": "exception"},
                    {"sku": "C", "errors": []}]}
    z = zaliv_source.readiness(pre)
    ok = z["error_skus"] == ["A", "B"] and len(z["error_skus"]) == z["errors"]
    return ok, f"error_skus={z['error_skus']} == build_error={z['errors']}"


def zr4_donor_blocker_as_data():
    """Блокер донора (пустой лист/не тот файл) течёт как ДАННЫЕ через donor_blocker, а не как краш."""
    sh = {"blocker": "лист пуст", "file": "cargo.xlsx", "sheet": "Sheet1", "shortlist": [], "agg": {"selected": 0}}
    z = zaliv_source.readiness({}, shortlist_rep=sh, slug="plenka")
    ok = z["donor_blocker"] == "лист пуст" and z["file"] == "cargo.xlsx" and z["ready"] is None
    return ok, f"donor_blocker={z['donor_blocker']!r} file={z['file']!r} ready={z['ready']}"


def zr5_topfill_min_synced():
    """Контракт: TOPFILL_MIN источника == 6 (порог runner.preflight). Расходиться двум порогам нельзя."""
    ok = zaliv_source.TOPFILL_MIN == 6
    return ok, f"TOPFILL_MIN={zaliv_source.TOPFILL_MIN} (ждём 6, синхр. с runner.preflight)"


# ─────────────────────────── build_preflight_fn ───────────────────────────

class _Spy:
    """Счётчики вызовов швов — доказываем ленивость и провязку цепи без xlsx/сети/параллельной линии."""
    def __init__(self, agg=None, rows=None, cats_loaded=("CATS",)):
        self.calls = {"shortlist": 0, "to_prod": 0, "preflight": 0, "load_cats": 0}
        self.seen = {}
        self._agg = agg if agg is not None else {"ok": 2, "build_error": 0, "topfill": 1, "total": 2}
        self._rows = rows if rows is not None else []
        self._cats_loaded = list(cats_loaded)

    def shortlist(self, donor, **kw):
        self.calls["shortlist"] += 1
        self.seen["donor"] = donor
        self.seen["kw"] = kw
        return {"shortlist": [{"r": 1}, {"r": 2}], "file": donor, "sheet": "S",
                "blocker": None, "agg": {"selected": 2}}

    def to_prod(self, row):
        self.calls["to_prod"] += 1
        return {"prod_of": row}

    def preflight(self, products, slug, cats=None):
        self.calls["preflight"] += 1
        self.seen["products"] = products
        self.seen["slug"] = slug
        self.seen["cats"] = cats
        return {"agg": self._agg, "rows": self._rows}

    def load_cats(self):
        self.calls["load_cats"] += 1
        return self._cats_loaded


def zb1_thunk_lazy():
    """Ленивость: построить thunk — швы НЕ трогаются; вызвать thunk — цепь пошла, вернулась готовность."""
    sp = _Spy()
    fn = zaliv_source.build_preflight_fn("cargo.xlsx", "plenka", shortlist_fn=sp.shortlist,
                                         to_prod_fn=sp.to_prod, preflight_fn=sp.preflight,
                                         load_cats_fn=sp.load_cats)
    built_clean = sum(sp.calls.values()) == 0          # сборка thunk ничего не вызвала
    z = fn()
    ran = sp.calls["shortlist"] == 1 and sp.calls["preflight"] == 1 and z.get("configured") is True
    return built_clean and ran, f"после build={built_clean} (0 вызовов), после вызова ready={z.get('ready')} calls={sp.calls}"


def zb2_cats_injected_not_loaded():
    """cats поданы явно → load_cats НЕ зовётся (файл не читаем), preflight получил именно их."""
    sp = _Spy()
    fn = zaliv_source.build_preflight_fn("cargo.xlsx", "plenka", cats=["MYCATS"],
                                         shortlist_fn=sp.shortlist, to_prod_fn=sp.to_prod,
                                         preflight_fn=sp.preflight, load_cats_fn=sp.load_cats)
    fn()
    ok = sp.calls["load_cats"] == 0 and sp.seen["cats"] == ["MYCATS"]
    return ok, f"load_cats вызван {sp.calls['load_cats']} раз (ждём 0), preflight.cats={sp.seen['cats']}"


def zb3_cats_loaded_when_none():
    """cats=None → load_cats зовётся (runner сам cats не грузит), его результат уходит в preflight."""
    sp = _Spy(cats_loaded=("LOADED",))
    fn = zaliv_source.build_preflight_fn("cargo.xlsx", "plenka", cats=None,
                                         shortlist_fn=sp.shortlist, to_prod_fn=sp.to_prod,
                                         preflight_fn=sp.preflight, load_cats_fn=sp.load_cats)
    fn()
    ok = sp.calls["load_cats"] == 1 and sp.seen["cats"] == ["LOADED"]
    return ok, f"load_cats вызван {sp.calls['load_cats']} раз (ждём 1), preflight.cats={sp.seen['cats']}"


def zb4_chain_wired():
    """Цепь: shortlist(донор)→to_prod(каждая строка)→preflight(prods, slug). slug прокинут насквозь."""
    sp = _Spy()
    fn = zaliv_source.build_preflight_fn("cargo.xlsx", "plenka", limit=7,
                                         shortlist_fn=sp.shortlist, to_prod_fn=sp.to_prod,
                                         preflight_fn=sp.preflight, load_cats_fn=sp.load_cats)
    fn()
    ok = (sp.calls["to_prod"] == 2 and sp.seen["slug"] == "plenka"
          and sp.seen["kw"].get("limit") == 7 and sp.seen["kw"].get("slug") == "plenka"
          and len(sp.seen["products"]) == 2)
    return ok, f"to_prod×{sp.calls['to_prod']} slug={sp.seen['slug']} limit={sp.seen['kw'].get('limit')} prods={len(sp.seen['products'])}"


# ─────────────────────────── ЖИВОЙ ДОНОР (cargo-avto slug) ───────────────────────────

# Карта категорий для живого thunk (совпадает с ymarket_cats_v1.json по ключу puzyrkovaya-plenka).
MY_CATS = {"puzyrkovaya-plenka": {"market_category_id": 76346336, "need_mapping": False}}


def _live_row(sku, name, cost=600.0, article="", url="", grid="main"):
    """normalized()-товар как отдаёт живой скан CargoAvtoAdapter: sku/name/cost/article/url/
    dims_raw/price_tiers/grid. Габаритов посылки и веса НЕТ (честно — их нет в листинге, T5)."""
    return {"sku": sku, "name": name, "cost": cost, "article": article, "url": url,
            "grid": grid, "dims_raw": "0.3*100 м",
            "price_tiers": [{"min": 1, "max": 14, "price": 600.0}], "stock": 0}


class _FakeScan:
    """Живой скан категории: шов для тестов, вместо CargoAvtoAdapter (герметично, без сети)."""
    def __init__(self, rows=None):
        self.calls = {"scan": 0}
        self.seen = {}
        self._rows = rows if rows is not None else []

    def scan(self, *, category=None, limit=200):
        self.calls["scan"] += 1
        self.seen["category"] = category
        self.seen["limit"] = limit
        return list(self._rows)


class _LiveSpy:
    """Швы живого thunk: live_shortlist/to_prod/preflight/load_cats. Блокер эхом уходит в шорт-лист
    (ровно как делает _live_shortlist_default), file='live:{source_key}' — иначе source определится ложно."""
    def __init__(self):
        self.calls = {"live_shortlist": 0, "to_prod": 0, "preflight": 0, "load_cats": 0}
        self.seen = {}

    def live_shortlist(self, items, **kw):
        self.calls["live_shortlist"] += 1
        self.seen["items"] = items
        self.seen["kw"] = kw
        if kw.get("blocker"):
            return {"blocker": kw["blocker"], "file": f"live:{kw.get('source_key')}",
                    "shortlist": [], "agg": {"selected": 0}}
        return {"blocker": None, "file": f"live:{kw.get('source_key')}",
                "shortlist": [{"r": 1}, {"r": 2}], "agg": {"selected": 2}}

    def to_prod(self, row):
        self.calls["to_prod"] += 1
        return {"prod_of": row}

    def preflight(self, products, slug, cats=None):
        self.calls["preflight"] += 1
        self.seen["products"] = products
        self.seen["slug"] = slug
        self.seen["cats"] = cats
        return {"agg": {"ok": 2, "build_error": 0, "topfill": 1, "total": 2, "need_mapping": 0}, "rows": []}

    def load_cats(self):
        self.calls["load_cats"] += 1
        return list(MY_CATS)


def _live_build(donor, slug, *, live_rows=None, scan_adapter=None, live_shortlist_fn=None,
                to_prod_fn=None, preflight_fn=None, load_cats_fn=None, cats=MY_CATS, limit=20,
                enrich_fn=None, photo_fn=None):
    """Короткая сборка живого thunk с фейками — единый хелпер для законов ниже."""
    return zaliv_source.build_preflight_fn(donor, slug, cats=cats, limit=limit,
                                           live_rows=live_rows, scan_adapter=scan_adapter,
                                           live_shortlist_fn=live_shortlist_fn,
                                           to_prod_fn=to_prod_fn, preflight_fn=preflight_fn,
                                           load_cats_fn=load_cats_fn, enrich_fn=enrich_fn,
                                           photo_fn=photo_fn)


def zb5_live_rows_priority():
    """live_rows поданы швом → ПРИОРИТЕТ над сканом: scan НЕ зовётся, ready живой (2), source='live'."""
    fs = _FakeScan()
    sp = _LiveSpy()
    rows = [_live_row("1", "Плёнка", cost=600.0), _live_row("2", "Стрейч", cost=320.0)]
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     live_rows=rows, scan_adapter=fs, live_shortlist_fn=sp.live_shortlist,
                     to_prod_fn=sp.to_prod, preflight_fn=sp.preflight, load_cats_fn=sp.load_cats)
    z = fn()
    ok = fs.calls["scan"] == 0 and z.get("ready") == 2 and z.get("source") == "live" \
        and z.get("selected") == 2
    return ok, f"scan вызван {fs.calls['scan']} раз (ждём 0 — приоритет live_rows), ready={z.get('ready')} source={z.get('source')}"


def zb6_scan_adapter_called():
    """Нет live_rows → scan_adapter зовётся ровно раз: category=URL-путь категории, limit прокинут."""
    fs = _FakeScan(rows=[_live_row("1", "Плёнка", cost=600.0)])
    sp = _LiveSpy()
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     scan_adapter=fs, live_shortlist_fn=sp.live_shortlist,
                     to_prod_fn=sp.to_prod, preflight_fn=sp.preflight, load_cats_fn=sp.load_cats,
                     limit=13)
    z = fn()
    ok = fs.calls["scan"] == 1 and fs.seen.get("category") == "vozdushno-puzyrkovaya-plenka" \
        and fs.seen.get("limit") == 13 and z.get("ready") == 2
    return ok, f"scan×{fs.calls['scan']} category={fs.seen.get('category')!r} limit={fs.seen.get('limit')} ready={z.get('ready')}"


def zb7_live_cats_injected():
    """cats поданы явно → load_cats НЕ зовётся (файл карты не читаем), preflight получил именно их."""
    fs = _FakeScan(rows=[_live_row("1", "Плёнка", cost=600.0)])
    sp = _LiveSpy()
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     scan_adapter=fs, live_shortlist_fn=sp.live_shortlist,
                     to_prod_fn=sp.to_prod, preflight_fn=sp.preflight, load_cats_fn=sp.load_cats)
    fn()
    ok = sp.calls["load_cats"] == 0 and sp.seen.get("cats") is MY_CATS \
        and sp.seen.get("kw", {}).get("cats") is MY_CATS
    return ok, f"load_cats×{sp.calls['load_cats']} (ждём 0) preflight.cats is MY_CATS={sp.seen.get('cats') is MY_CATS}"


def zb8_is_live_source_discriminates():
    """Дисковая ветка решается честно: kebab-slug→live; путь/файл на диске/None/''→xlsx. Не угадать."""
    fd, tmp = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    try:
        cases = [("vozdushno-puzyrkovaya-plenka", True), ("cargo.xlsx", False),
                 ("/abs/путь/cargo.xlsx", False), ("donor.xls", False),
                 (tmp, False), (None, False), ("", False)]
        res = {repr(d): zaliv_source._is_live_source(d) for d, _ in cases}
        ok = all(zaliv_source._is_live_source(d) is expect for d, expect in cases)
        return ok, " ".join(f"{k}->{v}" for k, v in res.items())
    finally:
        os.remove(tmp)


def zb9_dual_slug_contract():
    """Два слага НЕ путаем (F6): scan ест URL-путь категории, preflight — JSON-ключ карты."""
    fs = _FakeScan(rows=[_live_row("1", "Плёнка", cost=600.0)])
    sp = _LiveSpy()
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     scan_adapter=fs, live_shortlist_fn=sp.live_shortlist,
                     to_prod_fn=sp.to_prod, preflight_fn=sp.preflight, load_cats_fn=sp.load_cats)
    fn()
    ok = (fs.seen.get("category") == "vozdushno-puzyrkovaya-plenka"
          and sp.seen.get("slug") == "puzyrkovaya-plenka"
          and sp.seen.get("kw", {}).get("slug") == "puzyrkovaya-plenka")
    return ok, f"scan.category={fs.seen.get('category')!r} preflight.slug={sp.seen.get('slug')!r}"


def zb10_live_build_lazy():
    """Ленивость живого thunk: сборка НЕ трогает швы; вызов → live_shortlist×1, to_prod×2, preflight×1."""
    fs = _FakeScan()
    sp = _LiveSpy()
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     live_rows=[_live_row("1", "Плёнка", cost=600.0)], scan_adapter=fs,
                     live_shortlist_fn=sp.live_shortlist, to_prod_fn=sp.to_prod,
                     preflight_fn=sp.preflight, load_cats_fn=sp.load_cats)
    built_clean = sum(sp.calls.values()) == 0 and fs.calls["scan"] == 0
    z = fn()
    ran = (fs.calls["scan"] == 0 and sp.calls["live_shortlist"] == 1
           and sp.calls["to_prod"] == 2 and sp.calls["preflight"] == 1 and z.get("configured"))
    return built_clean and ran, f"build={built_clean} (0 вызовов) → live_shortlist×{sp.calls['live_shortlist']} to_prod×{sp.calls['to_prod']} preflight×{sp.calls['preflight']}"


def zm1_map_live_row_honest():
    """Маппер честен: cost/происхождение (article/url/dims_raw/grid) едут, габаритов посылки НЕТ
    (не выдумываем — C3/T5), in_stock=None, фото пусто, категория подтверждена (76346336)."""
    p = _live_row("9048", "Плёнка ВПП 0.3*100 м", cost=600.0, article="9602037",
                  url="https://shop.cargo-avto.ru/catalog/9602037/")
    r = zaliv_source._map_live_row(p, "puzyrkovaya-plenka", 76346336)
    ok = (r["cost"] == 600.0 and "dims" not in r and "weight" not in r
          and r["category_id"] == 76346336 and r["in_stock"] is None
          and r["pictures"] == [] and r["description"] == ""
          and r["link"] == p["url"] and r["article"] == "9602037"
          and r["dims_raw"] == "0.3*100 м" and r["grid"] == "main"
          and r["slug"] == "puzyrkovaya-plenka")
    return ok, f"cost={r['cost']} dims={'dims' in r} cid={r['category_id']} in_stock={r['in_stock']} link=url={r['link'] == p['url']}"


def zm2_map_live_row_drops_muck():
    """Мусор → None: без sku/имени, цена ≤0/отсутствует. Ничего из мусора не доходит до КАТЕГОРИЙЩИКА."""
    bad = [_live_row("1", "Нет цены", cost=0.0), _live_row("2", "", cost=600.0),
           None, {"sku": "3", "name": "X", "cost": -5.0}, {"name": "Y", "cost": 600.0}]
    got = [zaliv_source._map_live_row(b, "slug", 1) for b in bad]
    ok = all(g is None for g in got)
    return ok, f"отброшено {sum(1 for g in got if g is None)}/{len(bad)} (все — мусор → None)"


def zr6_live_empty_scan_blocker():
    """Скан вернул пусто → ЧЕСТНЫЙ блокер (донор недостижим/категория пуста), ready=None (не 0),
    preflight НЕ зовётся. Блокер ≠ «live»: день удержит память (KZ3/WZ3)."""
    fs = _FakeScan(rows=[])
    sp = _LiveSpy()
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     live_rows=[], scan_adapter=fs, live_shortlist_fn=sp.live_shortlist,
                     to_prod_fn=sp.to_prod, preflight_fn=sp.preflight, load_cats_fn=sp.load_cats)
    z = fn()
    ok = ("скан вернул пусто" in (z.get("donor_blocker") or "")
          and z.get("ready") is None
          and z.get("file") == "live:vozdushno-puzyrkovaya-plenka"
          and z.get("source") == "live"
          and sp.calls["preflight"] == 0)
    return ok, f"blocker={z.get('donor_blocker')!r} ready={z.get('ready')} file={z.get('file')!r} preflight×{sp.calls['preflight']}"


def zr7_readiness_source_derivation():
    """Провенанс источника: 'live' из file='live:…', 'xlsx' из файла, иначе 'memory'. source ≠ «как пошло»."""
    live = zaliv_source.readiness({}, shortlist_rep={"file": "live:vozdushno-puzyrkovaya-plenka"}, slug="s")
    xlsx = zaliv_source.readiness({}, shortlist_rep={"file": "cargo.xlsx"}, slug="s")
    mem = zaliv_source.readiness({})
    mem2 = zaliv_source.readiness({}, shortlist_rep={})
    ok = live["source"] == "live" and xlsx["source"] == "xlsx" \
        and mem["source"] == "memory" and mem2["source"] == "memory"
    return ok, f"live={live['source']} xlsx={xlsx['source']} none={mem['source']} empty-sh={mem2['source']}"


def zr8_needs_data_surfaced():
    """Честный T5: кандидаты без габаритов/веса (needs_data) и происхождение скана (grid) доходят
    из шорт-листа в сводку — ОВХ-слой позже заполнит габариты и они полетят БЕЗ правки моста."""
    sh = {"file": "live:vozdushno-puzyrkovaya-plenka", "blocker": None,
          "agg": {"selected": 0, "needs_data": 7, "rejected": 2, "grid_main": 9, "grid_related": 4}}
    z = zaliv_source.readiness({}, shortlist_rep=sh, slug="plenka")
    ok = z["needs_data"] == 7 and z["rejected"] == 2 and z["grid_main"] == 9 and z["grid_related"] == 4
    return ok, f"needs_data={z['needs_data']} rejected={z['rejected']} grid={z['grid_main']}main/{z['grid_related']}related"


def zh1_hermetic_live():
    """ГЕРМЕТИЧНОСТЬ: сборка живого thunk (без швов) и ВЫЗОВ (со всеми швами) НЕ импортируют
    guarded-модули параллельной линии (runner/write/categorist/card). День не тянет чужих правок."""
    def _guarded():
        return {m for m in sys.modules
                if m.startswith(("ymarket_runner_v1", "ymarket_write_v1",
                                 "ymarket_role_categorist_v1", "ymarket_card_v1"))}

    clean0 = _guarded()
    # (1) сборка живого thunk БЕЗ швов — ленивость на этапе build (сам thunk не вызываем: был бы сеть)
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka")
    clean_build = _guarded() - clean0
    # (2) ВЫЗОВ thunk со ВСЕМИ фейками — ни одному guarded-модулю не нужно встревать
    sp = _LiveSpy()
    fn2 = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                      live_rows=[_live_row("1", "Плёнка", cost=600.0)],
                      live_shortlist_fn=sp.live_shortlist, to_prod_fn=sp.to_prod,
                      preflight_fn=sp.preflight, load_cats_fn=sp.load_cats)
    clean_before_call = _guarded()
    z = fn2()
    clean_call = _guarded() - clean_before_call
    ok = not clean_build and not clean_call and z.get("configured")
    return ok, f"build+call импортировали guarded: {sorted(clean_build | clean_call)} (ждём пусто)"


def zm3_real_chain_offline():
    """РЕАЛЬНАЯ цепь без швов (только скан фейк): categorist→runner→card импортируются ЛЕНИВО,
    товар без габаритов посылки → needs_data → selected=0 → preflight([]) → ready=0 ЧЕСТНО.
    Донор жив (blocker=None), source='live' — «полетит 0» это правда, а не «не знаю»."""
    fs = _FakeScan(rows=[_live_row("1", "Плёнка ВПП 0.3x100", cost=600.0),
                         _live_row("2", "Стрейч 500м", cost=320.0)])
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka", scan_adapter=fs)
    z = fn()
    ok = (z.get("source") == "live" and z.get("donor_blocker") is None
          and z.get("selected") == 0 and z.get("needs_data") == 2
          and z.get("ready") == 0 and z.get("errors") == 0
          and z.get("total") == 0)
    return ok, f"source={z.get('source')} blocker={z.get('donor_blocker')} selected={z.get('selected')} needs_data={z.get('needs_data')} ready={z.get('ready')} errors={z.get('errors')} total={z.get('total')}"


# ─────────────────────────── ОВХ-СЛОЙ + НАЛИЧИЕ (T5+T4 закрываем вместе) ───────────────────────────

def oh1_enrich_before_shortlist():
    """Провязка: enrich_fn зовётся ровно раз, ПОЛУЧАЯ СЫРЫЕ позиции скана (sku/url) — ДО маппинга и
    шорт-листа. ОВХ обязан заполнить поля до score_item, иначе T5/T4 до него не долетят."""
    fs = _FakeScan(rows=[_live_row("1", "Плёнка", cost=600.0, article="9602037",
                                   url="https://shop.cargo-avto.ru/catalog/9602037/")])
    sp = _LiveSpy()
    order = []
    def enrich(products):
        order.append(([p.get("sku") for p in products], [p.get("url") for p in products]))
        return products
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     scan_adapter=fs, enrich_fn=enrich, live_shortlist_fn=sp.live_shortlist,
                     to_prod_fn=sp.to_prod, preflight_fn=sp.preflight, load_cats_fn=sp.load_cats)
    z = fn()
    ok = (len(order) == 1 and order[0][0] == ["1"]
          and order[0][1] == ["https://shop.cargo-avto.ru/catalog/9602037/"]
          and sp.calls["live_shortlist"] == 1 and z.get("configured"))
    return ok, f"enrich×{len(order)} sku={order[0][0] if order else '—'} shortlist×{sp.calls['live_shortlist']}"


def oh2_dims_weight_survive_map():
    """Маппер НЕ теряет ОВХ-габариты/вес: enrich проставил flat length/width/height + dims_source +
    weight/weight_source на сырую позицию → строка КАТЕГОРИЙЩИКА несёт их (score_item увидит, T5 закрыт)."""
    p = _live_row("9048", "Плёнка ВПП 0.3*100 м", cost=600.0, article="9602037",
                  url="https://shop.cargo-avto.ru/catalog/9602037/")
    p["length"], p["width"], p["height"] = 50.0, 35.0, 50.0
    p["dims_source"] = "card"
    p["weight"], p["weight_source"] = 1.438, "донор:карточка"
    r = zaliv_source._map_live_row(p, "puzyrkovaya-plenka", 76346336)
    ok = (r["length"] == 50.0 and r["width"] == 35.0 and r["height"] == 50.0
          and r["dims_source"] == "card" and r["weight"] == 1.438
          and r["weight_source"] == "донор:карточка")
    return ok, f"len/w/h={r.get('length')}/{r.get('width')}/{r.get('height')} src={r.get('dims_source')} w={r.get('weight')}"


def oh3_stock_survives_map():
    """Маппер НЕ теряет наличие: in_stock/stock_source, проставленные donor_stock на сырую позицию,
    доезжают в строку КАТЕГОРИЙЩИКА (T4 закрыт)."""
    p = _live_row("9048", "Плёнка", cost=600.0, article="9602037")
    p["in_stock"] = True
    p["stock_source"] = "донор:живой сайт"
    r = zaliv_source._map_live_row(p, "puzyrkovaya-plenka", 76346336)
    ok = r["in_stock"] is True and r["stock_source"] == "донор:живой сайт"
    return ok, f"in_stock={r.get('in_stock')} stock_source={r.get('stock_source')!r}"


def oh4_dims_stock_leave_needs_data():
    """СВОДНЫЙ ПРУФ СРЕЗА (реальная цепь, герметично, 0₽): сырая позиция + ОВХ-габариты посылки +
    живое наличие → КАТЕГОРИЙЩИК ОТБИРАЕТ (selected=2), needs_data=0, партия СУХО собралась (ready=2,
    errors=0, RUBICON dry). Это ПРОТИВОПОЛОЖНОСТЬ ZM3 (selected=0, needs_data=2 без обоих слоёв):
    оператор видит срез ДО/ПОСЛЕ и ДОКАЗАННЫЙ закон — нужны ОБА слоя (см. OH5/OH6)."""
    fs = _FakeScan(rows=[_live_row("1", "Плёнка ВПП 0.3x100", cost=600.0, article="9602037",
                                   url="https://shop.cargo-avto.ru/catalog/9602037/"),
                         _live_row("2", "Стрейч 500м", cost=320.0, article="9600154",
                                   url="https://shop.cargo-avto.ru/catalog/9600154/")])
    def enrich(products):
        for p in products:
            p["length"], p["width"], p["height"] = 50.0, 35.0, 50.0
            p["dims_source"] = "card"
            p["weight"], p["weight_source"] = 1.438, "донор:карточка"
            p["in_stock"], p["stock_source"] = True, "донор:живой сайт"
        return products
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     scan_adapter=fs, enrich_fn=enrich)
    z = fn()
    ok = (z.get("source") == "live" and z.get("donor_blocker") is None
          and z.get("selected") == 2 and z.get("needs_data") == 0 and z.get("rejected") == 0
          and z.get("ready") == 2 and z.get("errors") == 0 and z.get("total") == 2
          and z.get("parcel_dims") == 2)
    return ok, f"selected={z.get('selected')} needs_data={z.get('needs_data')} ready={z.get('ready')} errors={z.get('errors')} parcel_dims={z.get('parcel_dims')} (ср. ZM3: selected=0, needs_data=2)"


def oh5_dims_only_keeps_needs_data():
    """ЗАКОН НАХОДКИ T4: ОВХ-габариты БЕЗ наличия НЕ выносят кандидата из needs_data. Живой замер дал
    «С ОВХ: verdict=needs_data reasons=['T4: нет источника наличия']». Должно остаться needs_data=2,
    selected=0 — и это ЧЕСТНО (карточку «наверное есть» не строим). ОВХ ОДИН — НЕДОСТАТОЧЕН."""
    fs = _FakeScan(rows=[_live_row("1", "Плёнка ВПП 0.3x100", cost=600.0, article="9602037",
                                   url="https://shop.cargo-avto.ru/catalog/9602037/"),
                         _live_row("2", "Стрейч 500м", cost=320.0, article="9600154",
                                   url="https://shop.cargo-avto.ru/catalog/9600154/")])
    def enrich(products):
        for p in products:
            p["length"], p["width"], p["height"] = 50.0, 35.0, 50.0
            p["dims_source"] = "card"
            p["weight"], p["weight_source"] = 1.438, "донор:карточка"
        return products
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     scan_adapter=fs, enrich_fn=enrich)
    z = fn()
    ok = z.get("needs_data") == 2 and z.get("selected") == 0 and z.get("ready") == 0
    return ok, f"needs_data={z.get('needs_data')} selected={z.get('selected')} ready={z.get('ready')} (T4 держится: наличие не выдумываем)"


def oh6_stock_only_keeps_needs_data():
    """Обратная половина: наличие БЕЗ габаритов посылки тоже не спасает — needs_data=2 (T5 держится).
    Два закона (OH5/OH6) — зеркало: партию собирают ОБА слоя, а не «хоть что-то»."""
    fs = _FakeScan(rows=[_live_row("1", "Плёнка", cost=600.0, article="9602037"),
                         _live_row("2", "Стрейч", cost=320.0, article="9600154")])
    def enrich(products):
        for p in products:
            p["in_stock"], p["stock_source"] = True, "донор:живой сайт"
        return products
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     scan_adapter=fs, enrich_fn=enrich)
    z = fn()
    ok = z.get("needs_data") == 2 and z.get("selected") == 0 and z.get("ready") == 0
    return ok, f"needs_data={z.get('needs_data')} selected={z.get('selected')} (T5: габаритов посылки нет)"


def oh7_stock_gate_hermetic():
    """ГЕРМЕТИЧНОСТЬ _live_stock: позиции БЕЗ артикула (фейки тестов, article='') → 0 marked,
    donor_stock НЕ импортируется и сеть не трогается (по умолч. prep в герметичных тестах — пустышка)."""
    before = {m for m in sys.modules if m.startswith("donor_stock_v1")}
    rows = [_live_row("1", "Плёнка", cost=600.0)]       # article="" по умолч.
    got = zaliv_source._live_stock(rows)
    after = {m for m in sys.modules if m.startswith("donor_stock_v1")}
    ok = got == 0 and not (after - before) and rows[0].get("stock_source") is None
    return ok, f"marked={got} donor_stock импортирован: {sorted(after - before)} (ждём пусто)"


def oh8_parcel_dims_surfaced():
    """Провенанс ОВХ: габариты посылки из карточки донора (parcel_dims) доходят из агрегата шорт-листа
    в сводку — оператор и отчёт видят, СКОЛЬКО позиций ОВХ-слой обогатил (0₽ GET)."""
    sh = {"file": "live:vozdushno-puzyrkovaya-plenka", "blocker": None,
          "agg": {"selected": 2, "needs_data": 0, "parcel_dims": 2}}
    z = zaliv_source.readiness({}, shortlist_rep=sh, slug="plenka")
    ok = z["parcel_dims"] == 2 and z["needs_data"] == 0
    return ok, f"parcel_dims={z['parcel_dims']} (видят и оператор, и отчёт)"


def oh9_render_ovh_line():
    """Отчёт оператору: при parcel_dims>0 строка «габариты посылки из карточки донора: N (ОВХ-слой, 0₽)»
    появляется в render — человекочитаемый след слоя."""
    z = {"configured": True, "ready": 2, "errors": 0, "topfill": 1, "total": 2,
         "parcel_dims": 2, "needs_data": 0}
    s = zaliv_source.render(z)
    ok = "габариты посылки из карточки донора: 2" in s and "ОВХ-слой" in s and "0₽" in s
    return ok, s.splitlines()[0][:52] + " …"


def oh10_max_cost_mirror():
    """Экономика GET: потолок закупки источника (700₽) зеркалит правило КАТЕГОРИЙЩИКА — позиции дороже
    потолка отбились бы C4, значит ОВХ/наличие на них НЕ тратят патроны донора (бюджет бережём)."""
    import ymarket_role_categorist_v1 as categorist   # noqa: E402
    ok = (zaliv_source.DEFAULT_MAX_COST_RUB == categorist.DEFAULT_MAX_COST_RUB == 700.0)
    return ok, f"zaliv={zaliv_source.DEFAULT_MAX_COST_RUB} categorist={categorist.DEFAULT_MAX_COST_RUB}"


def oh11_ovh_module_stdlib():
    """ГЕРМЕТИЧНОСТЬ нового ОВХ-слоя в свежем интерпретаторе: ymarket_ovh_dims_v1 тянет ТОЛЬКО stdlib
    (re/time/urllib) — не может уронить суточный цикл чужими импортами параллельной линии."""
    import json
    import subprocess
    code = ("import sys, json; import ymarket_ovh_dims_v1; "
            "print(json.dumps(sorted(m for m in sys.modules if m.startswith('ymarket_'))))")
    out = subprocess.check_output([sys.executable, "-c", code], cwd=str(ARB), text=True)
    loaded = json.loads(out)
    guarded = [m for m in loaded if m.startswith(("ymarket_runner_v1", "ymarket_write_v1",
                                                  "ymarket_role_categorist_v1", "ymarket_card_v1"))]
    ok = not guarded
    return ok, f"ОВХ-импорты в свежем питоне: {loaded if loaded else 'только stdlib'} guarded={guarded}"


def oh12_enrich_pred_and_weight_honest():
    """ОВХ на модульном уровне: (а) позиция БЕЗ url ИЛИ dims_raw не трогается (pred — патроны не тратим);
    (б) НЕТ колонки «Вес» → вес НЕ выдумывается (закон L3): карточка честно останется без веса (T5),
    а не «1 кг на глаз»."""
    import ymarket_ovh_dims_v1 as ovh                    # noqa: E402
    rows = [{"url": "", "dims_raw": "0.3*100 м"},         # нет url → не трогаем
            {"url": "x"},                                  # нет dims_raw → не трогаем
            {"url": "y", "dims_raw": "0.3*100 м"}]         # есть оба → обогащаем
    seen = []
    def fake_fetch(url):
        seen.append(url)
        return ""
    ovh.enrich_products(rows, budget=5, fetch=fake_fetch)
    ok = seen == ["y"] and "dims_source" not in rows[0] and "dims_source" not in rows[1]
    prod = {"url": "z"}
    ovh.enrich(prod, {"Размер упаковки Д*Ш*В, см": "50*35*50"})
    ok = ok and "weight" not in prod and "weight_source" not in prod and prod["dims_source"] == "card"
    return ok, f"fetch×{len(seen)} url={seen} (тронута только 'y'); weight при отсутствии «Вес»: {'weight' in prod} (ждём False)"


def oh13_defaults_exposed():
    """Согласованные умолчания: dims_deadline/stock_deadline по умолчанию == константы модуля
    (360/300 — ЖИВОЙ ЗАМЕР 2026-09-01: 45 карточек ≈296с, 18 наличие ≈168с; бюджет ниже реальности =
    гонка daemon-потока → НЕЧЕСТНЫЙ selected=0), enrich_fn по умолчанию None (default = ОВХ+наличие)."""
    import inspect
    sig = inspect.signature(zaliv_source.build_preflight_fn)
    ok = (sig.parameters["dims_deadline"].default == zaliv_source.DIMS_DEADLINE == 360
          and sig.parameters["stock_deadline"].default == zaliv_source.STOCK_DEADLINE == 300
          and sig.parameters["enrich_fn"].default is None)
    return ok, f"dims={sig.parameters['dims_deadline'].default} stock={sig.parameters['stock_deadline'].default} enrich=None={sig.parameters['enrich_fn'].default is None}"


def oh14_stock_only_for_dims():
    """Патроны донора экономим СТРОГО: РЕАЛЬНЫЙ _default_prep (enrich_fn=None, не кастом) спрашивает
    живое наличие ТОЛЬКО у позиций, которым ОВХ дал габариты посылки; без габаритов (всё равно T5) к
    донору за наличием НЕ ходим. Сеть не тронута: enrich_products и _live_stock — швы."""
    import ymarket_ovh_dims_v1 as ovh_mod
    fs = _FakeScan(rows=[_live_row("1", "Плёнка", cost=600.0, article="9602037",
                                   url="https://shop.cargo-avto.ru/catalog/9602037/"),
                         _live_row("2", "Стрейч", cost=320.0, article="9600154",
                                   url="https://shop.cargo-avto.ru/catalog/9600154/")])
    sp = _LiveSpy()
    seen = []
    def fake_enrich(products, budget=120, fetch=None, only_where=None):
        for p in products:
            if p["sku"] != "2":                 # ОВХ дал габариты только «1»; «2» без них (честно T5)
                p["length"], p["width"], p["height"] = 50.0, 35.0, 50.0
                p["dims_source"] = "card"
        return products
    def stock_spy(products):
        seen.append([p.get("sku") for p in products])
        return len(products)
    orig_enrich, orig_stock = ovh_mod.enrich_products, zaliv_source._live_stock
    ovh_mod.enrich_products, zaliv_source._live_stock = fake_enrich, stock_spy
    try:
        fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                         scan_adapter=fs, live_shortlist_fn=sp.live_shortlist,
                         to_prod_fn=sp.to_prod, preflight_fn=sp.preflight, load_cats_fn=sp.load_cats)
        fn()
    finally:
        ovh_mod.enrich_products, zaliv_source._live_stock = orig_enrich, orig_stock
    ok = seen and seen[0] == ["1"]          # к донору сходили ТОЛЬКО за dims-позицией «1»
    return ok, f"наличие спрошено для sku={seen[0] if seen else None} (ждём ['1'] — «2» без габаритов не трогали)"


def wz7_live_socket_zaliv_live():
    """ЖИВОЙ thunk в суточный цикл: день кладёт его сводку в day.zaliv,
    ready_to_publish_source=zaliv_live, RUBICON цел (dry/commit). Без файлов, без сети —
    источник живой, но наружу ничего."""
    sp = _LiveSpy()
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     live_rows=[_live_row("1", "Плёнка", cost=600.0)],
                     live_shortlist_fn=sp.live_shortlist, to_prod_fn=sp.to_prod,
                     preflight_fn=sp.preflight, load_cats_fn=sp.load_cats)
    day = _run_day(preflight_fn=fn)
    z = day.get("zaliv") or {}
    ok = z.get("ready") == 2 and day.get("ready_to_publish_source") == "zaliv_live" \
        and day.get("dry") is True and day.get("commit") is False
    return ok, f"zaliv.ready={z.get('ready')} source={day.get('ready_to_publish_source')} dry={day.get('dry')} commit={day.get('commit')}"


# ─────────────────────────── ФОТО-СЛОЙ (паутина 🟢 ИМЯ→ФОТО→КАРТОЧКА) ───────────────────────────

def _ph_rows_and_enrich():
    """Две позиции с ОВХ-габаритами + живым наличием (паттерн OH4) — КАТЕГОРИЙЩИК их ОТБЕРЁТ, а фото-слой
    потом наполняет пиксели. Герметично: фейк-скан, без сети, 0₽."""
    fs = _FakeScan(rows=[_live_row("1", "Плёнка ВПП 0.3x100", cost=600.0, article="9602037",
                                   url="https://shop.cargo-avto.ru/catalog/9602037/"),
                         _live_row("2", "Стрейч 500м", cost=320.0, article="9600154",
                                   url="https://shop.cargo-avto.ru/catalog/9600154/")])
    def enrich(products):
        for p in products:
            p["length"], p["width"], p["height"] = 50.0, 35.0, 50.0
            p["dims_source"] = "card"
            p["weight"], p["weight_source"] = 1.438, "донор:карточка"
            p["in_stock"], p["stock_source"] = True, "донор:живой сайт"
        return products
    return fs, enrich


def ph1_default_off_layer_silent():
    """УМОЛЧАНИЕ = БЕЗОПАСНОСТЬ ДЕНЕГ: без YM_ZALIV_PHOTOS слой НЕ зовётся вообще — сводка photos=None
    (честно «не звали»), photo_pipeline_v1 НЕ импортирован, кузница (живьём ~$0.02/кадр) не тратит ни ₽.
    no_pictures=2 при этом ЧЕСТНЫЙ: кадров не было — бренд-замок бы отсечь (живой срез 2026-09-01: no_pictures=4)."""
    fs, enrich = _ph_rows_and_enrich()
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     scan_adapter=fs, enrich_fn=enrich)
    z = fn()
    ok = (z.get("photos") is None
          and "photo_pipeline_v1" not in sys.modules
          and z.get("no_pictures") == 2)
    return ok, f"photos={z.get('photos')} (None=не звали) photo_pipeline импортирован: {'photo_pipeline_v1' in sys.modules} no_pictures={z.get('no_pictures')}"


def ph2_dry_never_lies():
    """ЗАКОН ЧЕСТНОСТИ СУХОГО ПРОГОНА (0₽): (а) _default_photos в mode='dry' зовёт производителя с dry=True
    (это И ЕСТЬ механизм правды — реальный acquire_photos в сухом режиме вернёт urls=[], photo_publish не врёт)
    и, когда кадров нет, pictures ОСТАЮТСЯ пустыми (no_pictures НЕ снимается). (б) На уровне thunk: слой
    отработал, кадров не дал → сводка честна (with_pictures=0) и no_pictures=2 стоит как стоял.
    Сухое НЕ похоже на живое — иначе мы соврём себе о готовности партии."""
    seen = {}
    def fake_acquire(p, dry=True, **kw):
        seen["dry"] = dry
        return {"photo_urls": [], "source": "fake", "find": {"discovered": False}, "proposals": []}
    prod = {"name": "Плёнка", "sku": "1"}
    out = zaliv_source._default_photos([prod], mode="dry", acquire_fn=fake_acquire)
    ok_a = (seen.get("dry") is True and out[0].get("pictures") is None
            and out[0]["_photo"]["blocked"] is True and out[0]["_photo"]["urls"] == 0)
    # (б) слой вернул пусто (как сухой acquire) → сводка честна, no_pictures НЕ снят
    fs, enrich = _ph_rows_and_enrich()
    def photo_dry(prods):
        for p in prods:
            p["_photo"] = {"mode": "dry", "source": "fake", "urls": 0, "blocked": True,
                           "found": False, "proposals": 0, "why": None}
        return prods
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     scan_adapter=fs, enrich_fn=enrich, photo_fn=photo_dry)
    z = fn()
    ok_b = (z.get("photos", {}).get("with_pictures") == 0
            and z.get("photos", {}).get("asked") == 2
            and z.get("no_pictures") == 2)
    return ok_a and ok_b, f"dry=True до производителя={seen.get('dry')} pictures={out[0].get('pictures')} blocked={out[0]['_photo']['blocked']} | thunk: no_pictures={z.get('no_pictures')} (не снят) with_pictures={z.get('photos',{}).get('with_pictures')}"


def ph3_real_urls_fell_the_wall():
    """ПАДЕНИЕ СТЕНЫ: как только у prod появятся СВОИ https-URL (слой дал кадры) — no_pictures падает до 0,
    партия проходит бренд-замок. Живой срез сегодня no_pictures=4 (кадров нет); код-стена №1 закрывается
    этим слоем, а РЕАЛЬНЫЕ ссылки даст хостер (YC_*). Пруф, что вся паутина 🟢 держится на пикселях."""
    fs, enrich = _ph_rows_and_enrich()
    def photo_live(prods):
        for p in prods:
            p["pictures"] = [f"https://img.example/socc-{p.get('sku')}.jpg"]
            p["_photo"] = {"mode": "live", "source": "fake", "urls": 1, "blocked": False,
                           "found": True, "proposals": 0, "why": None}
        return prods
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     scan_adapter=fs, enrich_fn=enrich, photo_fn=photo_live)
    z = fn()
    ok = (z.get("no_pictures") == 0
          and z.get("photos", {}).get("with_pictures") == 2
          and z.get("photos", {}).get("asked") == 2
          and z.get("ready") == 2 and z.get("errors") == 0)
    return ok, f"no_pictures={z.get('no_pictures')} (стена пала) with_pictures={z.get('photos',{}).get('with_pictures')} ready={z.get('ready')} errors={z.get('errors')}"


def ph4_cap_bounds_spend():
    """ПОТОЛОК РАСХОДА: за прогон слой обслуживает не больше PHOTOS_MAX позиций (арг > env YM_ZALIV_PHOTOS_MAX
    > 4), отрицательный потолок → 0 вызовов (опечатка не сожжёт деньги). Каждый кадр живьём = ₽, лимит — закон."""
    calls = []
    def fake_acquire(p, dry=True, **kw):
        calls.append(p.get("sku"))
        return {"photo_urls": [], "source": "fake"}
    prods = [{"name": f"П{n}", "sku": str(n)} for n in range(6)]
    zaliv_source._default_photos(list(prods), mode="dry", cap=2, acquire_fn=fake_acquire)
    n_cap = len(calls); calls.clear()
    os.environ["YM_ZALIV_PHOTOS_MAX"] = "3"
    try:
        zaliv_source._default_photos(list(prods), mode="dry", acquire_fn=fake_acquire)
    finally:
        os.environ.pop("YM_ZALIV_PHOTOS_MAX", None)
    n_env = len(calls); calls.clear()
    zaliv_source._default_photos(list(prods), mode="dry", cap=-1, acquire_fn=fake_acquire)
    n_neg = len(calls)
    ok = n_cap == 2 and n_env == 3 and n_neg == 0 and zaliv_source._photos_cap(None) == zaliv_source.PHOTOS_MAX
    return ok, f"cap=2→{n_cap} env=3→{n_env} cap=-1→{n_neg} дефолт→{zaliv_source._photos_cap(None)}"


def ph5_fail_soft_day_survives():
    """FAIL-SOFT, ДЕНЬ ЖИВ: (а) производитель фото упал НА ПОЗИЦИИ → не крах: у неё провенанс _photo.error,
    остальные обслужены, сводка честно покажет сбои; (б) если упал ВЕСЬ слой — беду видит _safe цикла (B2),
    день выживает, провал назван ZALIV. Фото НЕ может уронить сутки (закон: деградация, а не остановка)."""
    calls = []
    def flaky(p, dry=True, **kw):
        if p.get("sku") == "2":
            raise RuntimeError("кузница 500")
        calls.append(p.get("sku"))
        return {"photo_urls": [f"https://img.example/{p['sku']}.jpg"], "source": "fake"}
    prods = [{"name": "П1", "sku": "1"}, {"name": "П2", "sku": "2"}, {"name": "П3", "sku": "3"}]
    out = zaliv_source._default_photos(list(prods), mode="live", acquire_fn=flaky)
    bad = out[1]["_photo"]; good = out[2]["_photo"]
    ok_a = ("кузница 500" in bad.get("why", "")) and bad.get("urls") == 0 and bad.get("blocked") \
        and good.get("urls") == 1 and calls == ["1", "3"]
    # (б) весь слой упал → день пережил, провал назван
    def boom_photo(prods):
        raise RuntimeError("фото-цепь умерла")
    fs, enrich = _ph_rows_and_enrich()
    fn = _live_build("vozdushno-puzyrkovaya-plenka", "puzyrkovaya-plenka",
                     scan_adapter=fs, enrich_fn=enrich, photo_fn=boom_photo)
    day = _run_day(preflight_fn=fn)
    named = any("сборка партии к заливу упала" in f for f in day.get("failures", []))
    ok_b = named and day.get("zaliv") is None and day.get("ready_to_publish_source") == "memory"
    return ok_a and ok_b, f"позиция-сбой: urls={bad.get('urls')} why={bad.get('why')!r}; обслужены={calls} | слой-крах назван={named}"


def ph6_lazy_import_boundary():
    """ГЕРМЕТИЧНОСТЬ ФОТО-СЛОЯ: build thunk и путь СО ШВОМ не импортируют photo_pipeline_v1 — импорт
    происходит ТОЛЬКО когда реальный слой пойдёт добывать кадры. Дефолтный цикл (env off) не тянет
    фото-цепь и не жжёт её ₽ (тот же закон, что ZH1 — чужих импортов в сборке нет)."""
    import json
    import subprocess
    code = ("import sys, json\n"
            "import ymarket_zaliv_source_v1 as z\n"
            "probe = lambda: 'photo_pipeline_v1' in sys.modules\n"
            "fn = z.build_preflight_fn('vozdushno-puzyrkovaya-plenka', 'puzyrkovaya-plenka')\n"
            "built = probe()\n"
            "z._default_photos([{'name':'x','sku':'1'}], mode='dry', "
            "acquire_fn=lambda p, dry=True: {'photo_urls': []})\n"
            "seam = probe()\n"
            "print(json.dumps({'built': built, 'seam': seam}))")
    out = subprocess.check_output([sys.executable, "-c", code], cwd=str(ARB), text=True)
    r = json.loads(out)
    ok = not r["built"] and not r["seam"]
    return ok, f"build импортировал photo_pipeline_v1: {r['built']} (ждём False) | seam: {r['seam']} (ждём False)"


def ph7_deadline_guards_the_day():
    """БЮДЖЕТ ФОТО-ПРОИЗВОДСТВА (PHOTO_DEADLINE): медленный/виснущий искатель (vision-гейт до 180с/кадр) НЕ
    держит сутки — позиция, не успевшая за deadline, честно пропускается с _photo.why про бюджет (urls=0,
    blocked), остальные обслужены, день не глохнет. Зеркало DIMS_DEADLINE/STOCK_DEADLINE; без бюджета живой
    прогон завис бы на искателе (замер: 24 мин wall при ~2с CPU)."""
    import time
    t0 = time.monotonic()
    calls = []
    def slow_flaky(p, dry=True, **kw):
        if p.get("sku") == "1":
            time.sleep(2)                       # виснущий искатель
            return {"photo_urls": []}
        calls.append(p.get("sku"))
        return {"photo_urls": [f"https://img.example/{p['sku']}.jpg"], "source": "fake"}
    prods = [{"name": "П1", "sku": "1"}, {"name": "П2", "sku": "2"}, {"name": "П3", "sku": "3"}]
    out = zaliv_source._default_photos(list(prods), mode="dry", acquire_fn=slow_flaky, deadline=0.3)
    elapsed = time.monotonic() - t0
    skipped = out[0]["_photo"]; served = out[2]["_photo"]
    ok = ("бюджет" in skipped.get("why", "")) and skipped.get("urls") == 0 and skipped.get("blocked") \
        and served.get("urls") == 1 and calls == ["2", "3"] and elapsed < 3.0
    return ok, (f"виснущий скип: why={skipped.get('why')!r} urls={skipped.get('urls')} blocked={skipped.get('blocked')} "
                f"| обслужены={calls} | прогон за {elapsed:.1f}с (день не глохнет)")


# ─────────────────────────── collect_kpis ───────────────────────────

def kz1_no_zaliv_uses_memory():
    """Без сводки залива ready_to_publish берётся из памяти само-модели (обратная совместимость)."""
    out = day_mod.collect_kpis(_mem_st(7), {}, zaliv=None)
    return out["ready_to_publish"] == 7, f"ready_to_publish={out['ready_to_publish']} (из памяти 7)"


def kz2_live_overrides_memory():
    """Сводка залива есть (ready=5) → живая готовность перекрывает память (7)."""
    out = day_mod.collect_kpis(_mem_st(7), {}, zaliv={"ready": 5, "errors": 0})
    return out["ready_to_publish"] == 5, f"ready_to_publish={out['ready_to_publish']} (live 5 поверх памяти 7)"


def kz3_none_ready_keeps_memory():
    """Сводка есть, но ready=None (донора нет/сборка не прошла) → память сохраняется, не врём «live»."""
    out = day_mod.collect_kpis(_mem_st(7), {}, zaliv={"ready": None, "donor_blocker": "лист пуст"})
    return out["ready_to_publish"] == 7, f"ready_to_publish={out['ready_to_publish']} (память 7 сохранена)"


# ─────────────────────────── run_day (сокет) ───────────────────────────

def wz1_socket_stores_and_source():
    """inject thunk → day.zaliv заполнен сводкой, провенанс ready_to_publish_source=zaliv_live."""
    z = {"configured": True, "ready": 6, "errors": 0, "topfill": 4, "total": 8, "error_skus": []}
    day = _run_day(preflight_fn=lambda: z)
    ok = day.get("zaliv") == z and day.get("ready_to_publish_source") == "zaliv_live" \
        and day["kpis"]["ready_to_publish"] == 6
    return ok, f"zaliv.ready={day.get('zaliv',{}).get('ready')} source={day.get('ready_to_publish_source')} kpi={day['kpis']['ready_to_publish']}"


def wz2_no_preflight_keeps_memory():
    """Без thunk → zaliv=None, source=memory: день ведёт себя ровно как раньше (обратная совместимость)."""
    day = _run_day(preflight_fn=None)
    ok = day.get("zaliv") is None and day.get("ready_to_publish_source") == "memory" \
        and "ready_to_publish" in day["kpis"]
    return ok, f"zaliv={day.get('zaliv')} source={day.get('ready_to_publish_source')}"


def wz3_none_ready_source_memory():
    """thunk дал ready=None (блокер донора) → source=memory, а НЕ фейковый zaliv_live."""
    z = {"configured": True, "ready": None, "donor_blocker": "лист пуст", "errors": None}
    day = _run_day(preflight_fn=lambda: z)
    ok = day.get("zaliv") == z and day.get("ready_to_publish_source") == "memory"
    return ok, f"ready=None → source={day.get('ready_to_publish_source')} (не zaliv_live)"


def wz4_failure_survived():
    """B2: thunk упал → день выжил, провал назван (ZALIV), zaliv=None, source=memory (не соврём «готова»)."""
    def boom():
        raise RuntimeError("битый xlsx")
    day = _run_day(preflight_fn=boom)
    named = any("сборка партии к заливу упала" in f for f in day.get("failures", []))
    ok = named and day.get("zaliv") is None and day.get("ready_to_publish_source") == "memory" \
        and isinstance(day.get("kpis"), dict)
    return ok, f"провал_назван={named} zaliv={day.get('zaliv')} source={day.get('ready_to_publish_source')}"


def wz5_batch_errors_burn():
    """Ошибки сухой сборки → «что горит» называет SKU (планка YM1 «0 ошибок» ловится ДО залива)."""
    z = {"configured": True, "ready": 3, "errors": 2, "total": 5, "error_skus": ["SKU-A", "SKU-B"]}
    day = _run_day(preflight_fn=lambda: z)
    items = day["burning"]["items"]
    hit = [b for b in items if b.get("zaliv_ref") == "day.zaliv.error_skus"]
    ok = len(hit) == 1 and "SKU-A" in hit[0]["what"] and "2" in hit[0]["what"]
    return ok, f"горящих zaliv-строк={len(hit)} what={hit[0]['what'] if hit else '—'}"


def wz6_dry_rubicon():
    """RUBICON: цикл с источником залива остаётся dry=True/commit=False; наружу ничего (0₽)."""
    z = {"configured": True, "ready": 2, "errors": 0, "total": 2, "error_skus": []}
    day = _run_day(preflight_fn=lambda: z)
    ok = day.get("dry") is True and day.get("commit") is False
    return ok, f"dry={day.get('dry')} commit={day.get('commit')} (наружу ничего)"


ALL = [
    ("ZR1", "ready_from_agg_ok", zr1_ready_from_agg_ok),
    ("ZR2", "none_ready_not_zero", zr2_none_ready_not_zero),
    ("ZR3", "error_skus_match_errors", zr3_error_skus_match_errors),
    ("ZR4", "donor_blocker_as_data", zr4_donor_blocker_as_data),
    ("ZR5", "topfill_min_synced", zr5_topfill_min_synced),
    ("ZB1", "thunk_lazy", zb1_thunk_lazy),
    ("ZB2", "cats_injected_not_loaded", zb2_cats_injected_not_loaded),
    ("ZB3", "cats_loaded_when_none", zb3_cats_loaded_when_none),
    ("ZB4", "chain_wired", zb4_chain_wired),
    ("ZB5", "live_rows_priority", zb5_live_rows_priority),
    ("ZB6", "scan_adapter_called", zb6_scan_adapter_called),
    ("ZB7", "live_cats_injected", zb7_live_cats_injected),
    ("ZB8", "is_live_source_discriminates", zb8_is_live_source_discriminates),
    ("ZB9", "dual_slug_contract", zb9_dual_slug_contract),
    ("ZB10", "live_build_lazy", zb10_live_build_lazy),
    ("ZM1", "map_live_row_honest", zm1_map_live_row_honest),
    ("ZM2", "map_live_row_drops_muck", zm2_map_live_row_drops_muck),
    ("ZR6", "live_empty_scan_blocker", zr6_live_empty_scan_blocker),
    ("ZR7", "readiness_source_derivation", zr7_readiness_source_derivation),
    ("ZR8", "needs_data_surfaced", zr8_needs_data_surfaced),
    ("ZH1", "hermetic_live", zh1_hermetic_live),
    ("ZM3", "real_chain_offline", zm3_real_chain_offline),
    ("OH1", "enrich_before_shortlist", oh1_enrich_before_shortlist),
    ("OH2", "dims_weight_survive_map", oh2_dims_weight_survive_map),
    ("OH3", "stock_survives_map", oh3_stock_survives_map),
    ("OH4", "dims_stock_leave_needs_data", oh4_dims_stock_leave_needs_data),
    ("OH5", "dims_only_keeps_needs_data", oh5_dims_only_keeps_needs_data),
    ("OH6", "stock_only_keeps_needs_data", oh6_stock_only_keeps_needs_data),
    ("OH7", "stock_gate_hermetic", oh7_stock_gate_hermetic),
    ("OH8", "parcel_dims_surfaced", oh8_parcel_dims_surfaced),
    ("OH9", "render_ovh_line", oh9_render_ovh_line),
    ("OH10", "max_cost_mirror", oh10_max_cost_mirror),
    ("OH11", "ovh_module_stdlib", oh11_ovh_module_stdlib),
    ("OH12", "enrich_pred_and_weight_honest", oh12_enrich_pred_and_weight_honest),
    ("OH13", "defaults_exposed", oh13_defaults_exposed),
    ("OH14", "stock_only_for_dims", oh14_stock_only_for_dims),
    ("PH1", "default_off_layer_silent", ph1_default_off_layer_silent),
    ("PH2", "dry_never_lies", ph2_dry_never_lies),
    ("PH3", "real_urls_fell_the_wall", ph3_real_urls_fell_the_wall),
    ("PH4", "cap_bounds_spend", ph4_cap_bounds_spend),
    ("PH5", "fail_soft_day_survives", ph5_fail_soft_day_survives),
    ("PH6", "lazy_import_boundary", ph6_lazy_import_boundary),
    ("PH7", "deadline_guards_the_day", ph7_deadline_guards_the_day),
    ("KZ1", "no_zaliv_uses_memory", kz1_no_zaliv_uses_memory),
    ("KZ2", "live_overrides_memory", kz2_live_overrides_memory),
    ("KZ3", "none_ready_keeps_memory", kz3_none_ready_keeps_memory),
    ("WZ1", "socket_stores_and_source", wz1_socket_stores_and_source),
    ("WZ2", "no_preflight_keeps_memory", wz2_no_preflight_keeps_memory),
    ("WZ3", "none_ready_source_memory", wz3_none_ready_source_memory),
    ("WZ4", "failure_survived", wz4_failure_survived),
    ("WZ5", "batch_errors_burn", wz5_batch_errors_burn),
    ("WZ6", "dry_rubicon", wz6_dry_rubicon),
    ("WZ7", "live_socket_zaliv_live", wz7_live_socket_zaliv_live),
]


def main():
    print("🎯 ЯНДЕКС ПРИЁМКА · ВЫБОР→ЗАЛИВ — сухая сборка партии → ready_to_publish (сухо, 0₽, без сети)")
    passed = 0
    for code, name, fn in ALL:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        passed += 1 if ok else 0
        print(f"   {_passed(ok)} {code}  {name:<26} {detail}")
    total = len(ALL)
    print(f"\n   {'✅' if passed == total else '❌'} {passed}/{total} законов держатся")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ИСТОЧНИК ЗАЛИВА (ymarket_zaliv_source_v1) — единственный шов «готовность партии к заливу» в цикл.

Зачем отдельный файл (а не строка в day):
  • Провязка ВЫБОР→ЗАЛИВ. ГОЛОВА уже ПРЕДЛАГАЕТ суточный шорт-лист категорий (спрос WB), но цикл
    НЕ прогонял предложенное через сборку карточки. Планка оператора — «партия готова к заливу:
    N чистых, 0 ошибок, K охуенно-заполнены» — не могла быть правдой: никто сухо не собирал карточки
    и не считал, сколько взлетит без ошибки. Этот адаптер закрывает разрыв: донорский xlsx →
    КАТЕГОРИЙЩИК → prod → runner.preflight (сухая сборка каждой карточки) → сводка готовности.
  • ЖИВОЙ донор без файлов. Оператор потребовал: «ассортимент перестаёт зависеть от твоих рук» —
    категорию сосёт сам автопилот по slug из env (YM_ZALIV_DONOR = cargo-avto slug). Тот же донор,
    но читается ЖИВЫМ сканом категории (0₽ GET) вместо локальной выгрузки. Два источника различаются
    лексикой донора (см. «ЖИВОЙ ДОНОР» ниже), день и автопилот НЕ меняются.
  • preflight/сборка живут в ПАРАЛЛЕЛЬНОЙ линии (`ymarket_runner_v1` / `ymarket_write_v1`, её активно
    правят). Чтобы её правки НЕ могли уронить суточный цикл, ВСЁ связывание с ней изолировано здесь и
    ленивое: импорт runner/card/categorist происходит ТОЛЬКО в момент вызова thunk, не при сборке.
    day → этот адаптер (stdlib-only на импорте) → guarded runner. Тот же приём, что у
    [[ymarket_cabinet_health_v1]] (СВЕРКА) и [[ymarket_head_source_v1]] (ГОЛОВА).

ГРАНИЦА (RUBICON цел): 0₽ наружу. `readiness(...)` — чистая, без сети. `build_preflight_fn(...)` строит
thunk, который гоняет `runner.preflight` — а он зовёт `write.publish_card(dry=True, commit=False)`:
НИЧЕГО наружу не пишет, денег не двигает (тройной сухой гейт). Сеть по донору: xlsx-источник читается
ЛОКАЛЬНО (0 GET); cargo-avto slug — ЖИВОЕ ЧТЕНИЕ листинга (GET, 0₽, fail-soft: сеть легла → честный
блокер, не краш, не молчание). Поэтому источник по умолчанию НЕ подключён к циклу (как trend/head):
оператор задаёт донор+slug, когда готов. Без донора day ведёт себя ровно как раньше.

ЖИВОЙ ДОНОР (cargo-avto slug, без файлов): оператор потребовал, чтобы ассортимент перестал зависеть
от его рук — автопилот сосёт категорию по slug из env (YM_ZALIV_DONOR) и собирает партию сам. ДВА
слага-контракта не путать (слова обожгли на F6):
  * `donor_xlsx` (первый аргумент) в живой ветке = URL-путь категории на shop.cargo-avto.ru
    (vozdushno-puzyrkovaya-plenka) — им сканим каталог (CargoAvtoAdapter.scan(category=...)).
  * `slug` остаётся JSON-ключом ymarket_cats_v1.json (puzyrkovaya-plenka → market_category_id 76346336) —
    им preflight подтверждает категорию карточки.
  У демо-категории они РАЗНЫЕ. Кинуть URL-путь в `slug` → категория не резолвится (честный
  need_mapping, не «ошибка»); кинуть JSON-ключ в `donor_xlsx` → присоска 404-нёт (честный блокер).
  Оба случая день не ломают: источник молчит и остаётся памятью. Живой товар листинга честно несёт
  {sku, name, cost, article, url, dims_raw, price_tiers, grid} и НЕ несёт габаритов посылки/веса/фото →
  score_item отдаёт needs_data (C3/T5), пока ОВХ-слой не заполнит их. Это НЕ баг моста: он доставляет
  их в сводку честно (needs_data=N), а не врёт «наверное влезет». Живой скан ограничен бюджетом
  scan_deadline (по умолч. 60с) — медленный/висит донор не держит сутки (daemon-поток + deadline).

ОВХ+НАЛИЧИЕ — закрываем T5 И T4 (живой замер 2026-09-01 доказал: ОВХ ОДИН НЕДОСТАТОЧЕН).
Листинг cargo-avto несёт габариты РУЛОНА (dims_raw), а Экспрессу нужны габариты ПОСЫЛКИ + вес — без них
ТОВАРОВЕД честно роняет позицию в needs_data (T5). Но даже заполненные габариты НЕ выносят кандидата из
needs_data: у листинга нет НАЛИЧИЯ, и мерч отбивает T4 («нет источника наличия — карточка родится
мёртвой»). Поэтому перед шорт-листом живой thunk обогащает сырые позиции ДВУМЯ слоями (бюджеты
dims_deadline/stock_deadline, оба 0₽ GET, оба fail-soft):
  1. ОВХ-слой (ymarket_ovh_dims_v1): карточка донора (1 GET) → «Размер упаковки Д*Ш*В, см»+«Вес, кг» →
     flat length/width/height/weight (dims_source='card'); нет колонки → оценка цилиндра по физике
     (dims_source='physics', зеркало _derive_dims). Закрывает T5.
  2. Живое наличие (donor_stock_v1, по АРТИКУЛУ карточки — не по bx-id): ТОЛЬКО 'in_stock' даёт
     stock_source/in_stock (закон СКЛАДОВЩИКА). Закрывает T4.
Провенанс едет насквозь (parcel_dims в сводке: «габариты посылки из карточки донора: N»). Позиция без
карточки (сеть легла) / без наличия (под заказ/неизвестно) ЧЕСТНО остаётся needs_data — карточку
«наверное влезет / наверное есть» не строим. См. [[ymarket_ovh_dims_v1]] и [[donor_stock_v1]].

ФОТО-СЛОЙ — третья стена паутины 🟢 ИМЯ→ФОТО→КАРТОЧКА (живой замер 2026-09-01: собрано 4, ошибок 0,
но no_pictures=4). У листинга донора СВОИХ пикселей нет, а чужой кадр класть нельзя (МП склеит нашу
карточку с донорской по pHash) — значит карточка либо получает НАШ кадр, либо честно едет без фото
(низкий index; при РЕАЛЬНОМ заливе бренд-замок её отсечёт). Слой стоит между `shortlist_to_prod` и
`runner.preflight` — там, где prod уже собран, а шорт-лист уже отранжирован: платим только за те
позиции, что реально поедут (4 отобранных, не 41 сканированных). Зовёт photo_pipeline_v1.acquire_photos
(ИСКАТЕЛЬ-ПЕРВЫМ → КУЗНИЦА-фолбэк) и кладёт в pictures[] ТОЛЬКО настоящие https-URL своих пикселей
(own_pixels+verified+живой хостинг) — сухой прогон оставляет pictures ПУСТЫМИ и no_pictures НЕ снимает
(pictures_from_forge при dry отдаёт urls=[]+would_url; подменить сухое на «как будто залито» = соврать
себе о готовности партии). Дефолт 'off': кузница живьём тратит ₽ — цикл не жжёт деньги без слова
оператора. См. PHOTOS_ENV ниже, [[photo_pipeline_v1]] и [[photo_publish_v1]].

ЧЕСТНОСТЬ ИСТОЧНИКА: «партия готова» и «донора нет» — РАЗНЫЕ вещи и не путаются. Блокер донора
(пустой лист / не тот файл) течёт как ДАННЫЕ через `donor_blocker`, а не как исключение. Любая
НЕОЖИДАННАЯ беда (сломанный импорт параллельной линии, битый xlsx) поднимается наверх — её ловит
`_safe` суточного цикла и честно пишет в failures (день не врёт «партия готова», если сборка упала).

Определение чисел (единый язык с runner.preflight.agg, без расхождения):
  ready   = agg.ok         — собралась без ошибки И категория подтверждена (не need_mapping) = «полетит»
  errors  = agg.build_error — сборка отбила ошибку (= len(error_skus)); планка YM1 «0 ошибок»
  topfill = agg.topfill    — «охуенно заполнена» (n_emitted ≥ TOPFILL_MIN)
  total   = agg.total      — сколько карточек собрано в партии
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Порог «охуенно заполнена». Держим синхронно с runner.preflight (там TOPFILL_MIN=6):
# const + 3 габарита + вес + материал для 0-обязательных коробов. Расходиться двум порогам нельзя.
TOPFILL_MIN = 6

# Правило КАТЕГОРИЙЩИКА (зеркало DEFAULT_MAX_COST_RUB): дороже потолка позиция отобьётся C4 — значит,
# GET-бюджет ОВХ/наличия на неё НЕ тратим (экономим патроны донора и время суток).
DEFAULT_MAX_COST_RUB = 700.0

# Бюджеты обогащения живого донора (секунды). Карточки ОВХ (T5) и живое наличие (T4) — 0₽ GET, каждый
# под своим бюджетом: медленный донор не держит сутки, не успевшие ЧЕСТНО остаются needs_data (ждут дня).
# ЖИВОЙ ЗАМЕР 2026-09-01 (45 позиций ≤700₽, категория плёнки): ОВХ-чтение 45 карточек = 296с (18 с
# габаритами, ~16с/карточка), stock-чтение 18 из них = 168с (8 в наличии, ~9с/карточка). Бюджет НИЖЕ
# реального времени = гонка: daemon-поток наличия не успевает, шорт-лист видит 0 стоков → selected=0
# (НЕЧЕСТНЫЙ недосчёт). Поэтому бюджеты — с запасом под реальный темп донора, а не «красивое» число.
DIMS_DEADLINE = 360
STOCK_DEADLINE = 300

# ФОТО-СЛОЙ (паутина 🟢 ИМЯ→ФОТО→КАРТОЧКА). У живого листинга СВОИХ пикселей нет → карточка уходит
# missing_pictures: низкий index, а при РЕАЛЬНОМ заливе бренд-замок её отсечёт. Слой зовёт
# photo_pipeline_v1.acquire_photos (ИСКАТЕЛЬ-ПЕРВЫМ → КУЗНИЦА-фолбэк) и кладёт в prod['pictures']
# ТОЛЬКО свои пиксели (own_pixels + verified + живой хостинг), иначе НИЧЕГО.
# РЕЖИМЫ (env YM_ZALIV_PHOTOS), неизвестное значение → 'off' (fail-safe, случайно живьём не уйдём):
#   off  — умолчание: слой не зовут вовсе. Кузница живьём ТРАТИТ ₽ (~$0.02/кадр) — суточный цикл не
#          жжёт деньги без слова оператора (зеркало доктрины «не рискуем деньгами заранее»).
#   dry  — сухой прогон (0₽): ИСКАТЕЛЬ читает (GET), кузница/заливка сухие → pictures ОСТАЮТСЯ
#          ПУСТЫМИ, no_pictures НЕ снимается. Это честность, а не поломка: pictures_from_forge при
#          dry отдаёт urls=[] + would_url, и подменять «как будто залито» мы не имеем права.
#   live — оператор дал отмашку: живой форж + заливка на хостинг → в pictures настоящие https-URL.
# Потолок кадров за прогон (env YM_ZALIV_PHOTOS_MAX) — граница расхода: слой обслуживает только
# первые PHOTOS_MAX позиций шорт-листа (он уже отранжирован КАТЕГОРИЙЩИКОМ, сверху — лучшие).
PHOTOS_ENV = "YM_ZALIV_PHOTOS"
PHOTOS_MAX_ENV = "YM_ZALIV_PHOTOS_MAX"
PHOTOS_MODES = ("off", "dry", "live")
PHOTOS_MAX = 4
# Бюджет ОДНОГО фото-производства (искатель+зрение на позицию), секунд. Искатель медленный/виснущий
# (vision-гейт ollama до 180с/кадр, DDG/WB-зонды сериями) НЕ держит сутки: позиция честно пропускается
# с why про бюджет, остальные обслужены — зеркало DIMS_DEADLINE/STOCK_DEADLINE.
PHOTO_DEADLINE = 240


def _error_skus(rows):
    """SKU, которые придётся ПЕРЕСОБРАТЬ: у строки непустой errors[] ЛИБО сборка упала (exception).

    Ровно те же два условия, по которым runner.preflight растит agg.build_error (строки 148 и 172-173):
    держим len(error_skus) == errors, чтобы оператору не соврать «0 ошибок» при непустом списке.
    """
    out = []
    for r in rows if isinstance(rows, (list, tuple)) else []:
        if not isinstance(r, dict):
            continue
        if (r.get("errors") or r.get("stage") == "exception") and r.get("sku"):
            out.append(r["sku"])
    return out


def readiness(pre, shortlist_rep=None, slug=None, photos=None):
    """ЧИСТО: агрегат runner.preflight + отчёт КАТЕГОРИЙЩИКА → сводка готовности партии к заливу (0₽).

    Форма ВСЕГДА одна (не зависит от того, был донор или упал сбор): day кладёт её в day["zaliv"],
    отчёт/лента рендерят из неё. `ready is None` ⇔ агрегата нет (сборку не удалось провести) —
    честное «не знаю», НЕ фейковый 0 (тот же анти-ложь, что в СВЕРКЕ: 0 ≠ «не считал»).

    photos — сводка ФОТО-СЛОЯ (что он реально сделал) как ДАННЫЕ; None ⇔ слой не звали.
    """
    agg = (pre or {}).get("agg") or {}
    rows = (pre or {}).get("rows") or []
    sh = shortlist_rep or {}
    sh_agg = sh.get("agg") or {}
    return {
        "configured": True,
        "slug": slug or sh.get("slug"),
        "file": sh.get("file"),
        "sheet": sh.get("sheet"),
        "donor_blocker": sh.get("blocker"),          # пустой лист / не тот файл — как ДАННЫЕ, не как краш
        "selected": sh_agg.get("selected"),          # сколько КАТЕГОРИЙЩИК отобрал в шорт-лист
        "needs_data": sh_agg.get("needs_data"),      # кандидаты без габаритов/веса (T5) — честно, ждут ОВХ-слой
        "parcel_dims": sh_agg.get("parcel_dims"),    # ОВХ-слой: габариты ПОСЫЛКИ из карточки донора (0₽ GET)
        "rejected": sh_agg.get("rejected"),          # отбой (дорого/маржа не сходится) — причина видна в отчёте
        "grid_main": sh_agg.get("grid_main"),        # происхождение живого скана: основная сетка категории
        "grid_related": sh_agg.get("grid_related"),  # …и сопутствующий кросс-селл (охват, не подмена)
        "total": agg.get("total"),                   # собрано карточек в партию
        "ready": agg.get("ok"),                      # «полетит»: без ошибки И категория подтверждена
        "errors": agg.get("build_error"),            # YM1: сборка отбила ошибку (= len(error_skus))
        "topfill": agg.get("topfill"),               # «охуенно заполнена» (n_emitted ≥ TOPFILL_MIN)
        "need_mapping": agg.get("need_mapping"),     # категория не подтверждена (не «ошибка», но не полетит)
        "no_pictures": agg.get("no_pictures"),       # нет своих пикселей (бренд-замок отсечёт при заливе)
        "photos": photos,                            # ФОТО-СЛОЙ: что сделал производитель (None = не звали)
        "with_specs": agg.get("with_specs"),         # у скольких обогащённый _spec (ТОП-заполнение)
        "avg_emitted": agg.get("avg_emitted"),       # средняя заполненность параметров
        "min_emitted": agg.get("min_emitted"),       # худшая карточка партии
        "source": ("live" if str(sh.get("file") or "").startswith("live:")   # живой скан vs файл
                   else ("xlsx" if sh.get("file") else "memory")),
        "error_skus": _error_skus(rows),             # точечно кого пересобирать (для «что горит»)
        "agg": agg,                                  # сырой агрегат — на случай если рендер захочет больше
        "rows": rows,                                # per-SKU карта готовности (диагностика)
    }


# ── ЖИВОЙ ДОНОР (cargo-avto slug, без файлов) ──────────────────────────────────────────────────

def _is_live_source(donor):
    """Лексика донора в момент ВЫЗОВА thunk: файл на диске или slug категории?

    Файл: существует на диске ИЛИ пахнет путём ('.' или '/') → xlsx-ветка (0 GET, локально).
    Всё прочее (kebab-slug без точки/слеша) → живой скан. Проверяем на ДИСКЕ при вызове, а не
    намертво при сборке: оператор положит файл — и ветка переключится сама, без правки цикла.
    """
    s = str(donor or "")
    if not s or Path(s).is_file():
        return False
    return not ("." in s or "/" in s)


def _market_cid(slug, cats):
    """Локальное зеркало card.market_category_id (6 строк) — живой thunk НЕ импортирует card
    (герметичность). Категория не смаплена/нет в карте → None (честно, не ошибка)."""
    meta = (cats or {}).get(slug)
    if not meta or meta.get("need_mapping"):
        return None
    cid = meta.get("market_category_id")
    return int(cid) if isinstance(cid, (int, str)) and str(cid).isdigit() else None


def _map_live_row(p, slug, category_id):
    """normalized()-товар живого скана → строка КАТЕГОРИЙЩИКА (тот же словарь, что из xlsx).

    Честный перенос: cost = ступень «от 1» (закон поштучного выкупа); article/url/dims_raw/
    price_tiers/grid едут как ПРОИСХОЖДЕНИЕ — мерч/ОВХ решают по правде, а не по пустым полям.
    Габаритов посылки, веса, фото у листинга НЕТ → их просто нет в ключах (score_item через .get()
    честно отдаст needs_data, C3/T5). Позиция без sku/имени/цены — мусор → None.
    """
    if not p or not p.get("sku") or not p.get("name"):
        return None
    cost = p.get("cost") or 0.0
    if cost <= 0:
        return None
    row = {
        "sku": str(p.get("sku")),
        "name": str(p.get("name")),
        "cost": float(cost),
        "slug": slug,                       # JSON-ключ категории (НЕ URL-путь — не путать!)
        "category_id": category_id,         # зеркало карты (честно: None, если категория не смаплена)
        "article": p.get("article") or "",
        "url": p.get("url") or "",
        "link": p.get("url") or "",
        "in_stock": p.get("in_stock"),      # None: живое наличие — дело donor_stock, не листинга
        "stock_source": p.get("stock_source"),
        "pictures": [],
        "description": "",
        "dims_raw": p.get("dims_raw") or "",
        "price_tiers": p.get("price_tiers") or [],
        "grid": p.get("grid"),
    }
    # Габариты/вес/штрихкод, если адаптер их всё же дал (будущие ОВХ-слои) — не теряем.
    # length/width/height/dims_source — это ОВХ-слой (габариты ПОСЫЛКИ, T5): пришёл на raw-позицию
    # из карточки донора (или оценки физики) → доезжает в строку КАТЕГОРИЙЩИКА до score_item.
    for k in ("dims", "length", "width", "height", "dims_source",
              "weight", "weight_source", "barcode", "_spec"):
        if p.get(k) is not None:
            row[k] = p[k]
    return row


def _scan_blocker(raw, items, skipped):
    """Честный блокер живого скана: «пусто» ≠ «всё мусор». raw — число позиций со скана."""
    if not raw:
        return "скан вернул пусто (донор недостижим или категория пустая)"
    if skipped and not items:
        return f"скан вернул {raw} позиций, маппер отбросил все {skipped} (нет sku/имени/цены)"
    return None


def _run_with_deadline(fn, seconds):
    """Гоняет fn в daemon-потоке с бюджетом seconds. None, если не успел (донор медленный/висит).

    ТОЛЬКО для живого адаптера. Инъекционный scan_adapter зовём напрямую — без потоков (герметичность).
    Исключение fn честно всплывает — его ловит `_safe` суточного цикла, день не соврёт «готово».
    """
    import threading
    box = {}

    def _target():
        try:
            box["v"] = fn()
        except Exception as e:              # noqa: BLE001 — беду видит _safe цикла
            box["e"] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        return None                         # не уложился — честное «не знаю», не таймаут-краш
    if "e" in box:
        raise box["e"]
    return box.get("v")


def _real_adapter():
    """Живой CargoAvtoAdapter — импорт лениво (suppliers/ в sys.path только в момент вызова thunk)."""
    if str(HERE / "suppliers") not in sys.path:
        sys.path.insert(0, str(HERE / "suppliers"))
    import cargo_avto_v1 as cargo           # noqa: E402
    return cargo.CargoAvtoAdapter()


def _live_stock(products):
    """Живое наличие у донора (donor_stock_v1) по АРТИКУЛАМ — закрывает T4. Возвращает сколько marked.

    ТОЛЬКО 'in_stock' даёт stock_source/in_stock (закон СКЛАДОВЩИКА: «под заказ» и «неизвестно» — НЕ
    источник; карточка на «под заказ» у Экспресса = отмена по нашей вине). Ключ страницы — article
    (/catalog/{article}/), НЕ sku (bx-id 404-ит — проверено живьём 2026-09-01).

    ГЕРМЕТИЧНОСТЬ: статьи нет (фейки тестов article="") → возвращаем сразу, donor_stock НЕ импортируем
    и сеть не трогаем (ZH1). Реальный вызов — только когда есть живые артикулы (и импорт, и GET).
    """
    real = [p for p in products if str(p.get("article") or "")]
    if not real:
        return 0
    import donor_stock_v1 as stock            # noqa: E402 — лениво, только на реальных артикулах
    pids = []
    for p in real:
        pid = str(p.get("article") or p.get("sku", "")).split("-")[0]
        if pid not in pids:
            pids.append(pid)
    return stock.apply_to(real, stock.stock_for(pids))


def _live_shortlist_default(items, *, city, max_cost, markup_lo, markup_hi, limit,
                            slug, cats, skipped, blocker, source_key):
    """Шорт-лист живого скана: score_item+rank КАТЕГОРИЙЩИКА по строкам _map_live_row.

    Отдаёт ТОТ ЖЕ словарь, что categorist.shortlist (schema/agg/shortlist/needs_data/rejected) —
    readiness()/render/отчёт/лента работают независимо от источника. file='live:{source_key}',
    sheet=None, colmap={}. Габаритов у живого листинга нет → score_item честно роняет в needs_data
    (C3/T5): число уходит в сводку, а не выдумывается. Плюс сетка main/related (происхождение скана).
    """
    import ymarket_role_categorist_v1 as categorist     # noqa: E402 — лениво, только на живом доноре
    mc = max_cost if max_cost is not None else categorist.DEFAULT_MAX_COST_RUB
    mlo = markup_lo if markup_lo is not None else categorist.DEFAULT_MARKUP_LO
    mhi = markup_hi if markup_hi is not None else categorist.DEFAULT_MARKUP_HI
    scored = [categorist.score_item(r, city=city, cats=cats,
                                    max_cost=mc, markup_lo=mlo, markup_hi=mhi)
              for r in items]
    selected = categorist.rank(scored)
    needs = [r for r in scored if r["verdict"] == "needs_data"]
    rejected = [r for r in scored if r["verdict"] == "reject"]
    profits = [(r["economics"] or {}).get("profit") for r in selected]
    profits = [p for p in profits if isinstance(p, (int, float))]
    grid = {}
    for r in items:
        g = r.get("grid") or "?"
        grid[g] = grid.get(g, 0) + 1
    _charter = getattr(categorist, "CHARTER", None)
    role = _charter.get("id") if isinstance(_charter, dict) else "categorist"
    agg = {
        "rows_read": len(items) + skipped, "rows_skipped": skipped,
        "selected": len(selected), "needs_data": len(needs), "rejected": len(rejected),
        "parcel_dims": sum(1 for r in items if r.get("dims_source")),  # ОВХ-слой: габариты посылки
        "grid_main": grid.get("main", 0), "grid_related": grid.get("related", 0),
        "avg_profit_low_end": round(sum(profits) / len(profits), 2) if profits else None,
        "total_profit_low_end": round(sum(profits), 2) if profits else None,
    }
    return {
        "schema": "ymarket.categorist.shortlist.live.v1", "role": role,
        "file": f"live:{source_key}", "sheet": None, "colmap": {},
        "blocker": blocker, "city": city, "max_cost": mc, "markup_range": [mlo, mhi],
        "agg": agg, "shortlist": selected[:limit], "needs_data": needs[:limit],
        "rejected": rejected[:limit],
    }


# ── ФОТО-СЛОЙ: отобранным позициям — СВОИ пиксели в pictures[] ─────────────────────────────────

def _photos_mode(mode=None):
    """Режим фото-слоя: явный аргумент > env YM_ZALIV_PHOTOS > 'off'. Мусор в env → 'off'.

    Fail-safe НАМЕРЕННО односторонний: непонятное значение НИКОГДА не поднимается до 'live'
    (живой форж тратит ₽). Опечатка оператора должна стоить «слой не работал», а не денег.
    """
    import os
    m = mode if mode is not None else os.environ.get(PHOTOS_ENV, "")
    m = str(m or "off").strip().lower()
    return m if m in PHOTOS_MODES else "off"


def _photos_cap(cap=None):
    """Потолок кадров за прогон: явный аргумент > env YM_ZALIV_PHOTOS_MAX > PHOTOS_MAX. <0 → 0."""
    import os
    v = cap if cap is not None else os.environ.get(PHOTOS_MAX_ENV, "")
    try:
        n = int(str(v).strip() or PHOTOS_MAX)
    except (TypeError, ValueError):
        n = PHOTOS_MAX
    return max(0, n)


def _default_photos(products, mode=None, cap=None, acquire_fn=None, deadline=PHOTO_DEADLINE):
    """Товар → СВОИ пиксели в prod['pictures'] через photo_pipeline.acquire_photos. Fail-soft, 0 лжи.

    ЗАЧЕМ ЗДЕСЬ (а не в _map_live_row): фото — самый дорогой шаг паутины, и платить за него имеет смысл
    ТОЛЬКО за те позиции, что реально поедут в карточку. На этой точке шорт-лист уже отобран и
    отранжирован КАТЕГОРИЙЩИКОМ, а prod уже собран — значит слой обслуживает 4 отобранных, а не 41
    сканированных, и ровно тот словарь, что через миг читает runner.preflight (n_pictures).

    ДВА ЗАКОНА ГРАНИЦЫ (душа искателя/публикатора здесь НЕ обходится, только повторно охраняется):
      • В pictures[] попадает ТОЛЬКО настоящий https-URL. Локальный путь/base64/would_url — никогда:
        сухой прогон оставляет pictures ПУСТЫМИ, и сводка честно держит no_pictures. Подменить сухое
        на «как будто залито» = соврать себе о готовности партии (тот же анти-ложь, что ready is None).
      • Слой НИЧЕГО не публикует и не двигает деньги Маркета (RUBICON цел): он лишь ПРОИЗВОДИТ URL для
        prod['pictures']. Расход возможен один — кузница при mode='live' (~$0.02/кадр), и только по
        явной отмашке оператора.

    Бедá провайдера/сети/импорта — НЕ краш суток: пишем провенанс в prod['_photo'] и едем дальше
    (карточка просто останется без своих фото — честная деградация). acquire_fn — шов для тестов.
    ТРЕТИЙ ЗАКОН (бюджет): одно фото-производство — под deadline (по умолч. PHOTO_DEADLINE, daemon-поток
    зеркало DIMS_DEADLINE/STOCK_DEADLINE). Искатель виснущий/медленный (vision-гейт до 180с/кадр) НЕ
    держит сутки: позиция пропускается с _photo.why про бюджет, остальные обслужены. Бюджет-ноль → 0 кадров.
    """
    prods = [p for p in (products or []) if isinstance(p, dict)]
    m = _photos_mode(mode)
    if m == "off" or not prods:
        return list(products or [])

    _acquire = acquire_fn
    if _acquire is None:
        try:
            import photo_pipeline_v1 as photos              # noqa: E402 — свой орган, ленивый импорт
        except Exception as e:                              # noqa: BLE001 — фото ≠ причина уронить сутки
            for p in prods:
                p["_photo"] = {"mode": m, "urls": 0, "blocked": True, "error": type(e).__name__,
                               "why": "фото-цепь недоступна (импорт photo_pipeline_v1 не удался)"}
            return list(products or [])
        _acquire = photos.acquire_photos

    for p in prods[:_photos_cap(cap)]:
        try:
            res = _run_with_deadline(lambda: _acquire(p, dry=(m != "live"),
                                                      infographic=(m == "live")), deadline)
        except Exception as e:                              # noqa: BLE001 — fail-soft по позиции
            p["_photo"] = {"mode": m, "urls": 0, "blocked": True, "error": type(e).__name__,
                           "why": "производитель фото отбил ошибку на этой позиции: %s" % (e,)}
            continue
        if res is None:
            p["_photo"] = {"mode": m, "urls": 0, "blocked": True,
                           "why": ("фото-производитель превысил бюджет %ss (искатель/зрение медленные) — "
                                   "пропустили, день жив" % deadline)}
            continue
        res = res or {}
        urls = [u for u in (res.get("photo_urls") or [])
                if isinstance(u, str) and u.strip().lower().startswith("https://")]
        if urls:
            p["pictures"] = list(urls)                      # свои пиксели ПЕРВЫМИ и единственными
        why = None
        if not urls:
            fw = ((res.get("forged") or {}).get("why") or res.get("note"))
            why = fw if isinstance(fw, str) else None
        p["_photo"] = {"mode": m, "source": res.get("source"), "urls": len(urls),
                       "blocked": not bool(urls),
                       "found": (res.get("find") or {}).get("discovered"),
                       "proposals": len(res.get("proposals") or []),
                       "why": why}
    return list(products or [])


def _photos_summary(products, mode=None):
    """Что фото-слой РЕАЛЬНО сделал → в сводку как данные (оператор видит, а не догадывается)."""
    prods = [p for p in (products or []) if isinstance(p, dict)]
    notes = [p["_photo"] for p in prods if isinstance(p.get("_photo"), dict)]
    return {
        "mode": _photos_mode(mode),
        "asked": len(notes),                                        # у скольких слой отработал
        "with_pictures": sum(1 for p in prods if p.get("pictures")),  # у скольких СВОИ пиксели в карточке
        "errors": sum(1 for n in notes if n.get("error")),
        "proposals": sum(int(n.get("proposals") or 0) for n in notes),  # кадры «на взгляд оператора»
        "why": next((n.get("why") for n in notes if n.get("why")), None),
    }


def _with_photos(products, photo_fn, mode=None, photo_deadline=PHOTO_DEADLINE):
    """Общий шаг обоих thunk: (products, шов) → (products, сводка). Слой не звали ⇔ photos=None."""
    _photos = photo_fn if photo_fn is not None else _default_photos
    if photo_fn is None and _photos_mode(mode) == "off":
        return products, None                       # слоя не было — не сочиняем сводку
    if photo_fn is not None:
        out = _photos(products) or products         # шов тестов сам рулит таймингом — бюджет не навязываем
    else:
        out = _photos(products, deadline=photo_deadline) or products
    return out, _photos_summary(out, mode=mode)


def _xlsx_thunk(donor_xlsx, slug, *, city, limit, max_cost, markup_lo, markup_hi, cats,
                shortlist_fn, to_prod_fn, preflight_fn, load_cats_fn, photo_fn=None,
                photo_deadline=PHOTO_DEADLINE):
    """Файловый донор: xlsx → categorist.shortlist → prod → preflight. Поведение 1-в-1 с прежним."""
    _shortlist = shortlist_fn
    _to_prod = to_prod_fn
    _preflight = preflight_fn
    _load_cats = load_cats_fn
    if _shortlist is None or _to_prod is None or _preflight is None or _load_cats is None:
        # Ленивый ОГРАЖДЁННЫЙ импорт параллельной линии — только когда thunk реально вызван.
        import ymarket_role_categorist_v1 as categorist   # noqa: E402
        import ymarket_runner_v1 as runner                # noqa: E402
        import ymarket_card_v1 as card                    # noqa: E402
        if _shortlist is None:
            _shortlist = categorist.shortlist
        if _to_prod is None:
            _to_prod = runner.shortlist_to_prod
        if _preflight is None:
            _preflight = runner.preflight
        if _load_cats is None:
            _load_cats = card.load_cats

    kw = {"city": city, "limit": limit, "slug": slug}
    if max_cost is not None:
        kw["max_cost"] = max_cost
    if markup_lo is not None:
        kw["markup_lo"] = markup_lo
    if markup_hi is not None:
        kw["markup_hi"] = markup_hi

    sh = _shortlist(donor_xlsx, **kw)
    if sh and sh.get("blocker"):
        # Донор не читается (пустой лист/не тот файл) → «НЕ ЗНАЮ, сколько полетит», а не фейковый 0.
        # День увидит donor_blocker и оставит ready_to_publish из памяти (KZ3/WZ3: блокер ≠ «live»).
        return readiness({}, shortlist_rep=sh, slug=slug)
    selected = (sh or {}).get("shortlist") or []
    products = [_to_prod(r) for r in selected]
    # runner.preflight сам cats НЕ грузит (при None шлёт cats=None в publish_card → карточка
    # деградирует). Его собственный поток делает cats=card.load_cats() перед preflight — повторяем,
    # иначе соврём заниженной готовностью. cats можно подать швом (тесты), тогда файл не читаем.
    _cats = cats if cats is not None else _load_cats()
    products, ph = _with_photos(products, photo_fn, photo_deadline=photo_deadline)  # ФОТО-СЛОЙ до preflight
    pre = _preflight(products, slug, cats=_cats)
    return readiness(pre, shortlist_rep=sh, slug=slug, photos=ph)


def _live_thunk(donor, slug, *, city, limit, max_cost, markup_lo, markup_hi, cats,
                live_rows, scan_adapter, live_shortlist_fn, to_prod_fn, preflight_fn,
                load_cats_fn, scan_deadline, enrich_fn=None,
                dims_deadline=DIMS_DEADLINE, stock_deadline=STOCK_DEADLINE, photo_fn=None,
                photo_deadline=PHOTO_DEADLINE):
    """Живой донор: cargo-avto slug → скан категории → ОВХ+НАЛИЧИЕ → КАТЕГОРИЙЩИК → prod → preflight.

    source priority: live_rows (шов тестов/памяти) > scan_adapter (шов тестов) > живой адаптер
    с бюджетом scan_deadline (daemon-поток). Все импорты параллельной линии — ЛЕНИВО внутри,
    при вызове thunk. Два слага НЕ путаем: `donor` = URL-путь для скана (vozdushno-…),
    `slug` = JSON-ключ для категории (puzyrkovaya-plenka).

    После скана, ДО шорт-листа — шаг обогащения (см. «ОВХ+НАЛИЧИЕ» в шапке): сырые позиции получают
    габариты ПОСЫЛКИ/вес из карточки донора (ОВХ-слой, T5) и живое наличие (donor_stock, T4). Только
    после этого score_item видит заполненные поля и НЕ роняет кандидата в needs_data. enrich_fn — шов
    для тестов (по умолч. _default_prep: cost-фильтр ≤ DEFAULT_MAX_COST_RUB, чтобы GET-бюджет не тратить
    на заведомо-отбитых C4, потом ОВХ под dims_deadline и наличие под stock_deadline).
    """
    _to_prod = to_prod_fn
    _preflight = preflight_fn
    _load_cats = load_cats_fn
    if _to_prod is None or _preflight is None or _load_cats is None:
        import ymarket_runner_v1 as runner                # noqa: E402
        import ymarket_card_v1 as card                    # noqa: E402
        if _to_prod is None:
            _to_prod = runner.shortlist_to_prod
        if _preflight is None:
            _preflight = runner.preflight
        if _load_cats is None:
            _load_cats = card.load_cats

    _cats = cats if cats is not None else _load_cats()

    def _default_prep(products):
        """ОВХ-габариты (карточка донора, T5) + живое наличие (donor_stock, T4). Оба 0₽ GET, fail-soft.

        Сначала cost-фильтр ≤ DEFAULT_MAX_COST_RUB (зеркало C4 КАТЕГОРИЙЩИКА): позицию, которую score_item
        отобьёт «дорого», не кормим патронами донора. Потом ОВХ под бюджетом dims_deadline. Наличие — ПОД
        БЮДЖЕТОМ stock_deadline (daemon-поток; если не успел — частичный урожай ЧЕСТЕН: не успевшие
        остаются needs_data на этот прогон и ждут следующего дня). ВАЖНО: наличие спрашиваем ТОЛЬКО у тех,
        у кого ОВХ уже дал габариты посылки — без габаритов позиция всё равно T5 (патроны донора не тратим);
        а чтобы daemon-поток успел до шорт-листа, бюджет обязан быть ≥ реального времени чтения (замер выше).
        """
        import ymarket_ovh_dims_v1 as ovh                    # noqa: E402 — свой слой, не ограждён
        mc = max_cost if max_cost is not None else DEFAULT_MAX_COST_RUB
        want = [p for p in products if (p.get("cost") or 0.0) <= mc]
        ovh.enrich_products(want, budget=dims_deadline)                 # T5: габариты/вес, 0₽ GET
        dims_ok = [p for p in want if p.get("dims_source")]             # T4: наличие ТОЛЬКО с габаритами
        if dims_ok:
            _run_with_deadline(lambda: _live_stock(dims_ok), stock_deadline)
        return products

    # 1) скан категории (0₽ GET). live_rows > scan_adapter > живой адаптер под бюджетом.
    if live_rows is not None:
        raw = list(live_rows)
    elif scan_adapter is not None:
        raw = scan_adapter.scan(category=donor, limit=limit)
    else:
        raw = _run_with_deadline(lambda: _real_adapter().scan(category=donor, limit=limit),
                                 scan_deadline)

    # 1.5) ОВХ-слой + живое наличие ДО шорт-листа. Без этого даже заполненные габариты НЕ выносят
    #      кандидата из needs_data (живой замер: «С ОВХ: verdict=needs_data reasons=['T4: нет источника
    #      наличия']»). enrich_fn — шов тестов; по умолч. _default_prep (оба слоя, оба под бюджетами).
    if raw is not None:
        _prep = enrich_fn if enrich_fn is not None else _default_prep
        raw = _prep(list(raw))

    # 2) маппинг в строки КАТЕГОРИЙЩИКА. Таймаут скана ≠ «пусто» — отдельный честный блокер.
    cid = _market_cid(slug, _cats)
    if raw is None:
        blocker = f"скан категории не успел за бюджетом {scan_deadline}с (донор медленный/висит)"
        items, skipped = [], 0
    else:
        items, skipped = [], 0
        for p in raw:
            r = _map_live_row(p, slug, cid)
            if r is None:
                skipped += 1
            else:
                items.append(r)
        blocker = _scan_blocker(len(raw), items, skipped)

    # 3) шорт-лист → prod → preflight (готовность).
    _shortlist_live = live_shortlist_fn if live_shortlist_fn is not None else _live_shortlist_default
    sh = _shortlist_live(items, city=city, max_cost=max_cost, markup_lo=markup_lo,
                         markup_hi=markup_hi, limit=limit, slug=slug, cats=_cats,
                         skipped=skipped, blocker=blocker, source_key=donor)
    if sh and sh.get("blocker"):
        # Скан пуст / всё мусор / таймаут → «НЕ ЗНАЮ, сколько полетит» (не фейковый 0). День держит память.
        return readiness({}, shortlist_rep=sh, slug=slug)
    selected = (sh or {}).get("shortlist") or []
    products = [_to_prod(r) for r in selected]
    products, ph = _with_photos(products, photo_fn, photo_deadline=photo_deadline)  # ФОТО-СЛОЙ до preflight
    pre = _preflight(products, slug, cats=_cats)
    return readiness(pre, shortlist_rep=sh, slug=slug, photos=ph)


def build_preflight_fn(donor_xlsx, slug, city=None, limit=20, max_cost=None,
                       markup_lo=None, markup_hi=None, cats=None,
                       shortlist_fn=None, to_prod_fn=None, preflight_fn=None, load_cats_fn=None,
                       *, live_rows=None, scan_adapter=None, live_shortlist_fn=None,
                       scan_deadline=60, enrich_fn=None,
                       dims_deadline=DIMS_DEADLINE, stock_deadline=STOCK_DEADLINE,
                       photo_fn=None, photo_deadline=PHOTO_DEADLINE):
    """Собрать preflight_fn — thunk без аргументов, который суточный цикл дёрнет один раз за сутки.

    Замыкаем донор+slug+параметры отбора. day.run_day(preflight_fn=build_preflight_fn(...)) → внутри
    дня цикл дёрнет thunk и получит сводку готовности партии. Сборка карточек (и её импорты параллельной
    линии) происходит ТОЛЬКО в момент вызова thunk (лениво) — так тесты/сухие сборки не тянут runner,
    пока thunk не вызван.

    ДОНОР — ДВА РЕЖИМА, ветка решается на ДИСКЕ при вызове (см. «ЖИВОЙ ДОНОР» в шапке):
      * файл (XLSX-путь) → `_xlsx_thunk`: categorist.shortlist(донор) → runner.shortlist_to_prod →
        runner.preflight(prods, slug, cats). 0 GET.
      * cargo-avto slug (без точки/слеша) → `_live_thunk`: CargoAvtoAdapter.scan(category=донор) →
        _map_live_row → _live_shortlist_default → prod → preflight. Живой GET, 0₽, бюджет scan_deadline.
      Параметр `slug` в ОБОИХ режимах — JSON-ключ ymarket_cats_v1.json (puzyrkovaya-plenka), НЕ URL-путь.

    Швы — для тестов: shortlist_fn (xlsx) / live_rows, scan_adapter, live_shortlist_fn (live) /
    enrich_fn (live-обогащение: по умолч. ОВХ+наличие, тесты подставляют фейк БЕЗ сети) /
    photo_fn (ФОТО-СЛОЙ: products → products с pictures[]; по умолч. _default_photos, а он молчит,
    пока YM_ZALIV_PHOTOS не задан — суточный цикл не жжёт ₽ кузницы без слова оператора) /
    to_prod_fn, preflight_fn, load_cats_fn (оба). Подставляем фейки и не трогаем ни сеть, ни файлы,
    ни параллельную линию. scan_adapter зовём НАПРЯМУЮ (без потока) — герметичность тестов.

    НЕ ставим тут широкий try/except: блокер донора уже течёт данными (sh["blocker"]), а НЕОЖИДАННУЮ
    беду обязан увидеть `_safe` суточного цикла и записать в failures — иначе цикл соврёт «партия
    готова», проглотив падение сборки. Честность важнее «не упасть любой ценой».
    """
    def _thunk():
        if _is_live_source(donor_xlsx):
            return _live_thunk(donor_xlsx, slug, city=city, limit=limit,
                               max_cost=max_cost, markup_lo=markup_lo, markup_hi=markup_hi,
                               cats=cats, live_rows=live_rows, scan_adapter=scan_adapter,
                               live_shortlist_fn=live_shortlist_fn, to_prod_fn=to_prod_fn,
                               preflight_fn=preflight_fn, load_cats_fn=load_cats_fn,
                               scan_deadline=scan_deadline, enrich_fn=enrich_fn,
                               dims_deadline=dims_deadline, stock_deadline=stock_deadline,
                               photo_fn=photo_fn, photo_deadline=photo_deadline)
        return _xlsx_thunk(donor_xlsx, slug, city=city, limit=limit,
                           max_cost=max_cost, markup_lo=markup_lo, markup_hi=markup_hi,
                           cats=cats, shortlist_fn=shortlist_fn, to_prod_fn=to_prod_fn,
                           preflight_fn=preflight_fn, load_cats_fn=load_cats_fn,
                           photo_fn=photo_fn, photo_deadline=photo_deadline)

    return _thunk


def render(z):
    """Человекочитаемая строка готовности партии (для CLI и подводок). None-числа → честный «—»."""
    if not z:
        return "партия к заливу: источник не подключён (нет донора/slug)."
    def n(v):
        return "—" if v is None else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))
    if z.get("donor_blocker"):
        where = z.get("file") if z.get("source") == "live" else f"файл {z.get('file')}"
        return f"партия к заливу: донор не читается — {z['donor_blocker']} ({where})"
    mark = "✅" if z.get("errors") == 0 else ("❗" if z.get("errors") else "")
    L = [f"партия к заливу: {n(z.get('ready'))} чистых · {n(z.get('errors'))} с ошибкой {mark}(цель 0)"
         f" · {n(z.get('topfill'))} охуенно-заполнены — из {n(z.get('total'))} собранных"]
    if z.get("need_mapping"):
        L.append(f"  категория не подтверждена: {n(z.get('need_mapping'))} (не полетят, пока не смаплены)")
    if z.get("no_pictures"):
        L.append(f"  без своих фото: {n(z.get('no_pictures'))} (бренд-замок отсечёт при заливе)")
    ph = z.get("photos") or None
    if ph:
        tail = ""
        if ph.get("errors"):
            tail = f" · сбоев {n(ph.get('errors'))}"
        elif ph.get("why"):
            tail = f" · {ph['why']}"
        L.append(f"  фото-слой [{ph.get('mode')}]: своих кадров у {n(ph.get('with_pictures'))}"
                 f" из {n(ph.get('asked'))} обслуженных{tail}")
        if ph.get("proposals"):
            L.append(f"  кадров на взгляд оператора: {n(ph.get('proposals'))} (proposals искателя)")
    if z.get("needs_data"):
        L.append(f"  ждут данных (нет габаритов/веса — T5, честно): {n(z.get('needs_data'))}"
                 f" (ОВХ-слой заполнит габариты посылки — и они полетят)")
    if z.get("parcel_dims") is not None:
        L.append(f"  габариты посылки из карточки донора: {n(z.get('parcel_dims'))} (ОВХ-слой, 0₽)")
    if z.get("error_skus"):
        shown = z["error_skus"][:8]
        more = "" if len(z["error_skus"]) <= 8 else f" (+{len(z['error_skus']) - 8})"
        L.append(f"  пересобрать: {', '.join(str(s) for s in shown)}{more}")
    return "\n".join(L)


if __name__ == "__main__":
    import argparse
    import json
    import os
    ap = argparse.ArgumentParser(
        description="ИСТОЧНИК ЗАЛИВА — сухо собрать партию из донора и показать готовность "
                    "(0₽; xlsx — без сети, cargo-avto slug — живой GET)")
    ap.add_argument("donor", help="донор: XLSX-путь (файл на диске, 0 GET) ЛИБО cargo-avto slug "
                                  "категории (vozdushno-puzyrkovaya-plenka) — живой скан, 0₽ GET")
    ap.add_argument("--slug", required=True, help="slug категории (ключ ymarket_cats_v1.json, НЕ URL-путь)")
    ap.add_argument("--city", default=None)
    ap.add_argument("--limit", type=int, default=20, help="сколько строк донора собрать в партию")
    ap.add_argument("--max-cost", type=float, default=None, help="потолок закупки (по умолч. правило КАТЕГОРИЙЩИКА)")
    ap.add_argument("--markup-lo", type=float, default=None)
    ap.add_argument("--markup-hi", type=float, default=None)
    ap.add_argument("--scan-deadline", type=float, default=60,
                    help="бюджет живого скана категории, секунд (медленный донор не держит сутки)")
    ap.add_argument("--dims-deadline", type=float, default=DIMS_DEADLINE,
                    help="бюджет ОВХ-обогащения (габариты посылки из карточек донора), секунд")
    ap.add_argument("--stock-deadline", type=float, default=STOCK_DEADLINE,
                    help="бюджет живого наличия (donor_stock по артикулам), секунд")
    ap.add_argument("--photo-deadline", type=float, default=PHOTO_DEADLINE,
                    help="бюджет ОДНОГО фото-производства (искатель+зрение), секунд; медленный искатель "
                         "не держит сутки — позиция пропускается с why про бюджет")
    ap.add_argument("--photos", default=None, choices=PHOTOS_MODES,
                    help="ФОТО-СЛОЙ off|dry|live (0₽ сухо / живой форж ~$0.02/кадр). То же, что env "
                         "YM_ZALIV_PHOTOS — дефолт env или off; на ручном прогоне флаг пишет env, "
                         "чтобы слой и сводка жили по ОДНОМУ режиму, а не разошлись")
    ap.add_argument("--json", action="store_true", help="сырая сводка готовности вместо человеческой строки")
    args = ap.parse_args()

    if args.photos is not None:
        os.environ[PHOTOS_ENV] = args.photos

    fn = build_preflight_fn(args.donor, args.slug, city=args.city, limit=args.limit,
                            max_cost=args.max_cost, markup_lo=args.markup_lo, markup_hi=args.markup_hi,
                            scan_deadline=args.scan_deadline,
                            dims_deadline=args.dims_deadline, stock_deadline=args.stock_deadline,
                            photo_deadline=args.photo_deadline)
    z = fn()
    if args.json:
        # rows/agg объёмны — в JSON отдаём сводку без сырого per-SKU дампа (диагностика — в --json rows отдельно)
        slim = {k: v for k, v in z.items() if k not in ("rows",)}
        print(json.dumps(slim, ensure_ascii=False, indent=2))
    else:
        print("📦 ГОТОВНОСТЬ ПАРТИИ К ЗАЛИВУ (СУХО, 0₽ — карточки собраны в памяти, наружу ничего)")
        print("   " + render(z).replace("\n", "\n   "))

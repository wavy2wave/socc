#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET RUNNER V1 — диспетчерская МОСТА ЯНДЕКС: залить КАТЕГОРИЮ и держать контроль.

Цель оператора дословно: «заливаешь через API категорию, заполняя всевозможные данные, чтобы
карточка была реально охуенно заполнена → в ТОП; инструмент не просто заливает, а отслеживает
статусы; ни один товар не должен быть с ошибкой; быстро и надёжно как швейцарские часы».

Это и есть вышка над органом (hands+card+write) и мостом (from_xlsx):
  1) preflight (dry, 0₽, БЕЗ ключа) — прогнать КАЖДЫЙ товар через publish_card(dry) и составить
     честную карту готовности: ok / need_mapping / нет фото / ошибки сборки. Оператор видит ДО залива,
     что полетит без ошибок, а что надо чинить. Ничего наружу.
  2) resolve_category (READ, нужен ключ) — categories_tree()/подтверждение marketCategoryId
     листовой категории (без выдумки id; закон «без фейк-пасс»).
  3) commit (реальный залив, ТОЛЬКО --commit + ключ) — publish_card по каждому товару строго
     по очереди с fail-soft; собрать per-SKU статус (PUBLISHED / errors / need_content).
  4) track (READ) — по offerId опросить витрину (campaign_offers) и индекс (offer_cards_status →
     contentRating + рекомендации). Это «отслеживание результата»: где ошибка, где недобор index.
  5) отчёт — JSON + человекочитаемая сводка: сколько ok, сколько с ошибкой (цель = 0), средний index,
     что чинить. Пишется в MEMORY_WAVE/reports/mint/arbiter (канон отчётов ARBITER).

ЗАКОНЫ SOCC: двойной гейт наследуется из write (_dry: наружу только not dry AND commit); stdlib+openpyxl;
fail-soft (один товар упал — вышка не падает, несёт ошибку в отчёт); 200≠успех (write уже читает
errors/warnings); не ломает орган (новый модуль-оркестратор поверх существующих функций).
"""
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_hands_v1 as hands          # noqa: E402
import ymarket_card_v1 as card            # noqa: E402
import ymarket_write_v1 as write          # noqa: E402
import ymarket_from_xlsx_v1 as bridge     # noqa: E402
import ymarket_role_categorist_v1 as categorist  # noqa: E402  (донор-осознанный читатель + дропшип-семантика)

# РЕЕСТР АРТИКУЛОВ — канон связи offerId↔donor. Мягкий импорт: вышка обязана работать и без него.
# Пишем в реестр ТОЛЬКО на реальном заливе (commit_category), а не в сухом preflight — иначе десяток
# read-only аудит-утилит, гоняющих preflight, засоряли бы канон отчётов. Запись локальная, 0₽,
# fail-soft: падение реестра НЕ роняет цикл залива (RUBICON цел, запись наружу тут не при чём).
try:
    import ymarket_registry_v1 as registry
except Exception:                                  # pragma: no cover — модуль рядом, но не роняемся
    registry = None

REPORTS = HERE.parent.parent.parent / "MEMORY_WAVE/reports/mint/arbiter"


def _record_registry(prod, offer_id):
    """Записать связь offerId↔donor в реестр (провенанс). Fail-soft, локально, 0₽.

    Пишем ФАКТ происхождения товара (source_url = откуда взяли, supplier если известен); donor_pid и
    donor_url реестр достраивает сам из offerId по канон-конвенции. Никогда не роняет вызывающий цикл.
    """
    if registry is None or not offer_id:
        return
    try:
        registry.record(offer_id,
                         source_url=prod.get("link") or None,
                         supplier=prod.get("supplier") or None)
    except Exception:
        pass                                       # реестр — вспомогательный канон, не критичный путь


def _absorb_marketsku(rep):
    """Впитать marketSku из отчёта индекса (track) в реестр. Fail-soft, локально, 0₽.

    marketSku присваивает МАРКЕТ после залива и отдаёт в mapping ответа offer-cards; до сих пор он
    читался транзитно в card_quality и ТЕРЯЛСЯ каждый тик (ровно та дыра, ради которой заведён реестр).
    Здесь ловим его на реальном READ индекса (rep.ok=True — сеть уже прошла гейт) и вшиваем в канон
    по offerId. Пишем ПАЧКОЙ (один load→write, не N файловых записей). Никогда не роняет track.
    Возвращает число вшитых marketSku (для наблюдаемости; вызывающему не обязателен).
    """
    if registry is None or not isinstance(rep, dict) or not rep.get("ok"):
        return 0
    pairs = []
    for c in rep.get("cards") or []:
        if not isinstance(c, dict):
            continue
        oid = c.get("offerId")
        mapping = c.get("mapping") if isinstance(c.get("mapping"), dict) else {}
        msku = mapping.get("marketSku")
        if oid and msku:
            pairs.append((str(oid), str(msku)))
    if not pairs:
        return 0
    try:
        doc = registry.load()
        for oid, msku in pairs:
            registry.upsert(doc, oid, marketSku=msku)   # None-safe merge не затрёт известное
        registry.write_atomic(doc)
    except Exception:
        return 0                                    # реестр упал — track всё равно вернул индекс
    return len(pairs)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _stamp():
    # без Math.random/Date.now-запретов: тут обычный datetime разрешён (это не workflow-скрипт)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")


# ── Шаг 1: PREFLIGHT (dry, 0₽) — карта готовности категории ──

def _emitted_param_values(cc):
    """Извлечь РЕАЛЬНО ОТПРАВЛЯЕМЫЕ parameterValues из dry-payload шага 2 (offer-cards).

    Это ИСТИННАЯ метрика «охуенно заполнена»: не сколько характеристик на входе (_spec),
    а сколько движок профиля подтверждённо эмитит в карточку (const + габариты + вес + ENUM).
    Пусто/пропущен шаг 2 → []. Никогда не роняет preflight.
    """
    try:
        oc = ((cc.get("payloads") or {}).get("step2") or {}).get("offersContent") or []
        return oc[0].get("parameterValues") or [] if oc else []
    except Exception:
        return []


def preflight(products, slug, cats=None, category_params=None):
    """Прогнать каждый товар через publish_card(dry). Вернуть per-SKU карту готовности + агрегат.

    Ничего наружу (dry=True). Ошибка сборки одного товара НЕ роняет остальные (fail-soft).
    """
    rows = []
    agg = {"total": len(products), "ok": 0, "need_mapping": 0, "no_pictures": 0,
           "build_error": 0, "with_specs": 0, "topfill": 0, "min_emitted": None,
           "sum_emitted": 0}
    TOPFILL_MIN = 6   # порог «охуенно заполнена» для 0-обязательных коробов: const+3габарита+вес+материал
    for prod in products:
        try:
            res = write.publish_card(prod, slug=slug, dry=True, commit=False, cats=cats,
                                     category_params=category_params)
        except Exception as e:  # никогда не должно, но вышка непадуча
            rows.append({"sku": prod.get("sku"), "ok": False, "stage": "exception",
                         "error": f"{type(e).__name__}: {e}"})
            agg["build_error"] += 1
            continue
        cc = res.get("create_card", res)
        spec = prod.get("_spec") or {}
        emitted = _emitted_param_values(cc)
        row = {
            "sku": res.get("offer_id") or prod.get("sku"),
            "name": prod.get("name"),
            "ok": bool(res.get("ok")),
            "need_mapping": bool(res.get("need_mapping") or cc.get("need_mapping")),
            "missing_pictures": bool(cc.get("missing_pictures")),
            "n_pictures": len(prod.get("pictures") or []),
            "n_specs": len(spec),
            "n_emitted": len(emitted),
            "emitted": [p.get("_label") or p.get("value") for p in emitted],
            "specs": spec,
            "errors": res.get("errors") or cc.get("errors") or [],
            "stage": res.get("step"),
        }
        rows.append(row)
        if row["need_mapping"]:
            agg["need_mapping"] += 1
        if row["missing_pictures"]:
            agg["no_pictures"] += 1
        if row.get("errors"):
            agg["build_error"] += 1
        if row["n_specs"] > 0:
            agg["with_specs"] += 1
        agg["sum_emitted"] += row["n_emitted"]
        if agg["min_emitted"] is None or row["n_emitted"] < agg["min_emitted"]:
            agg["min_emitted"] = row["n_emitted"]
        if row["n_emitted"] >= TOPFILL_MIN:
            agg["topfill"] += 1
        # «готов лететь» = сборка без ошибок И есть подтверждённая категория (не need_mapping)
        if row["ok"] and not row["need_mapping"]:
            agg["ok"] += 1
    agg["avg_emitted"] = round(agg["sum_emitted"] / agg["total"], 1) if agg["total"] else 0
    return {"rows": rows, "agg": agg}


# ── Шаг 2: RESOLVE CATEGORY (READ, нужен ключ) — подтвердить marketCategoryId ──

def resolve_category(query, dry=True, commit=False, limit_show=40):
    """Найти листовую категорию Маркета по подстроке названия (для подтверждения marketCategoryId).

    READ, 0₽, но под тем же гейтом: реально ходит в сеть только при not dry AND commit (нужен ключ).
    Возвращает список кандидатов {id,name,path} — оператор глазами подтверждает и вписывает в
    ymarket_cats_v1.json. НЕ выдумываем id (закон «без фейк-пасс»).
    """
    if dry or not commit:
        return {"ok": False, "dry": dry, "commit": commit,
                "note": "поиск категории требует реального режима (--commit) и ключа YANDEX_MARKET_API_KEY"}
    try:
        tree = hands.categories_tree()
    except (hands.YMarketHTTPError, RuntimeError) as e:
        return {"ok": False, "error": str(e)}
    q = query.lower().replace("ё", "е")
    hits = []

    def walk(node, path):
        if isinstance(node, dict):
            name = str(node.get("name") or "")
            cid = node.get("id")
            npath = path + [name] if name else path
            if q in name.lower().replace("ё", "е") and cid is not None:
                children = node.get("children") or []
                hits.append({"id": cid, "name": name, "leaf": not children,
                             "path": " / ".join(npath)})
            for ch in (node.get("children") or []):
                walk(ch, npath)
        elif isinstance(node, list):
            for ch in node:
                walk(ch, path)

    walk(tree, [])
    hits.sort(key=lambda h: (not h["leaf"], len(h["path"])))
    return {"ok": True, "query": query, "candidates": hits[:limit_show],
            "note": "leaf=true — листовая (в неё и грузим); подтверди id глазами и впиши в ymarket_cats_v1.json"}


# ── Шаг 3: COMMIT (реальный залив; ТОЛЬКО --commit + ключ) ──

def commit_category(products, slug, cats=None, category_params=None, business_id=None,
                    campaign_id=None, vat=None, available=True, pace=0.4):
    """Залить каждый товар (publish_card, реальный). Fail-soft: один упал → в отчёт, идём дальше.

    pace — пауза между товарами (сек), щадим лимит 100 req/час. Реально шлёт: dry=False, commit=True.
    """
    rows = []
    agg = {"total": len(products), "published": 0, "need_content": 0, "errors": 0, "need_mapping": 0}
    for prod in products:
        try:
            res = write.publish_card(prod, slug=slug, dry=False, commit=True, cats=cats,
                                     category_params=category_params, business_id=business_id,
                                     campaign_id=campaign_id, vat=vat, available=available)
        except Exception as e:
            rows.append({"sku": prod.get("sku"), "ok": False, "published": False,
                         "stage": "exception", "errors": [f"{type(e).__name__}: {e}"]})
            agg["errors"] += 1
            continue
        cc = res.get("create_card", res)
        status = res.get("status") or ""
        row = {
            "sku": res.get("offer_id") or prod.get("sku"),
            "ok": bool(res.get("ok")),
            "published": res.get("published") is True or status == write.PUBLISHED,
            "status": status,
            "need_mapping": bool(res.get("need_mapping") or cc.get("need_mapping")),
            "errors": res.get("errors") or cc.get("errors") or [],
            "warnings": cc.get("warnings") or [],
            "stage": res.get("step"),
        }
        rows.append(row)
        if row["published"]:
            agg["published"] += 1
        elif row["need_mapping"]:
            agg["need_mapping"] += 1
        elif status in write.NEED_CONTENT:
            agg["need_content"] += 1
        if row["errors"]:
            agg["errors"] += 1
        # ПРОВЕНАНС: связь наш offerId ↔ донор в канон-реестр (локально, fail-soft, 0₽). Пишем на
        # любом реальном заливе без ошибок сборки — даже если Маркету ещё нужен контент: связь с
        # донором уже реальна и нужна петле исполнения (express_loop.offer_to_cargo резолвит по ней).
        if row.get("sku") and not row["errors"]:
            _record_registry(prod, row["sku"])
        if pace:
            time.sleep(pace)
    return {"rows": rows, "agg": agg}


# ── Шаг 4: TRACK (READ) — витрина + индекс заполненности ──

def track(offer_ids, business_id=None, dry=True, commit=False):
    """Опросить индекс (contentRating + рекомендации) по offerId. READ, но под гейтом (нужен ключ)."""
    rep = write.quality_report(offer_ids=offer_ids, business_id=business_id, dry=dry, commit=commit)
    # ПРОВЕНАНС: словить marketSku (Маркет присвоил после залива) в канон-реестр. Только на реальном
    # READ (rep.ok=True → сеть прошла гейт); в dry rep.ok=False и это no-op. Fail-soft, 0₽, локально.
    _absorb_marketsku(rep)
    return rep


def reconcile(offer_ids, business_id=None, settle_wait=90, reread=True, dry=True, commit=False):
    """СВЕРКА здоровья карточек после залива (делегирует write.reconcile). READ, 0₽, под гейтом.

    Кодифицированный ответ на планку «отслеживает статусы; ни один товар с ошибкой; надёжно как часы».
    Тонкая обёртка рядом с track: track меряет ИНДЕКС (ТОП), reconcile меряет ЗДОРОВЬЕ (ошибки/заморозка/
    операторский store-block) — track к вердиктам ошибок слеп (card_quality роняет errors[]), reconcile нет.
    """
    return write.reconcile(offer_ids, business_id=business_id, settle_wait=settle_wait,
                           reread=reread, dry=dry, commit=commit)


# ── Оркестрация + отчёт ──

def shortlist_to_prod(row):
    """Строка шорт-листа КАТЕГОРИЙЩИКА → prod для write.publish_card. Ничего не выдумываем.

    C2 (дропшип): в карточку идёт ПРЕДЛОЖЕННАЯ цена продажи (proposed_low, консерв. конец ×markup_lo),
    НИКОГДА не донорская закупка (cost) — иначе продадим себе в убыток. weightDimensions собираем
    только при полном наборе (честность card._weight_dimensions отсечёт частичный). _spec и описание
    (уже обогащённое фактами) — насквозь: их читает движок профиля и выдаёт ТОП-заполнение.
    Наличие/остаток СЮДА не кладём — карточка ≠ склад (железный закон: не закупаем заранее; остаток
    ставит отдельный складской путь ТОЛЬКО после оплаченного заказа, DBS).

    БРЕНД+ОТВЯЗКА: как штатный row_to_prod, штампуем vendor="Без бренда" (легальный дефолт Маркета,
    закрывает обязательное поле «Бренд» — без него NO_CARD_ERRORS «Заполните поле Бренд») + свой
    EAN-13/unique_name (отвязка от чужой карточки). Тот же эталон-99, единый источник own_card_fields —
    формулу не дублируем.
    """
    prod = {
        "sku": row.get("sku"),
        "name": row.get("name"),
        "price": row.get("proposed_low"),        # C2: предложение (×markup_lo), НЕ закупка
        "slug": row.get("slug"),
        "pictures": row.get("pictures") or [],
        "description": row.get("description") or "",
        "link": row.get("link"),                 # провенанс (реестр), в карточку не идёт
    }
    if isinstance(row.get("_spec"), dict) and row["_spec"]:
        prod["_spec"] = row["_spec"]
    L, W, H, wt = row.get("length"), row.get("width"), row.get("height"), row.get("weight")
    if all(isinstance(x, (int, float)) and x > 0 for x in (L, W, H, wt)):
        prod["weightDimensions"] = {"length": L, "width": W, "height": H, "weight": wt}
    if row.get("barcode"):
        prod["barcode"] = row["barcode"]   # провенанс-fallback; ниже перекрывается своим EAN-13 (отвязка)
    # БРЕНД-ЭТАЖ + ОТВЯЗКА ОТ ЧУЖОЙ КАРТОЧКИ — тот же доктринальный приём, что и штатный путь
    # row_to_prod (эталон 99 баллов, единый источник own_card_fields — без дубля формулы). Живой
    # инцидент первого залива: донорский путь НЕ ставил vendor → Маркет отбивал карточку
    # (NO_CARD_ERRORS «Заполните поле Бренд»). Ставим ГАРАНТИРОВАННО легальное «Без бренда» (канал не
    # раскрывает, по бренду не склеивает), затем обогащаем своим EAN-13 + unique_name. fail-soft:
    # нет uniqueizer → own_card_fields вернёт {}, но бренд-этаж уже закрыл обязательное поле.
    prod["vendor"] = "Без бренда"
    prod["send_vendor"] = True
    prod.update(bridge.own_card_fields(prod))
    return prod


def run_donor(xlsx, slug, city=None, max_cost=categorist.DEFAULT_MAX_COST_RUB,
              markup_lo=categorist.DEFAULT_MARKUP_LO, markup_hi=categorist.DEFAULT_MARKUP_HI,
              limit=None, skus=None, commit=False, business_id=None, campaign_id=None, vat=None,
              pace=0.4, write_report=True, available=True):
    """Полный цикл вышки на ДОНОРСКОМ читателе (КАТЕГОРИЙЩИК): дропшип-семантика + ТОП-заполнение.

    Отличие от run(): источник товаров — categorist.shortlist (донорская «Цена»=закупка, цену продажи
    ПРЕДЛАГАЕТ, _spec обогащён), а не мост load_category (тот требует колонку цены продажи и слепнет
    на сыром доноре). preflight/commit/track — те же (RUBICON цел). Требует openpyxl (читатель донора).
    """
    t0 = time.time()
    cats = card.load_cats()
    # ТОЧЕЧНЫЙ РЕМОНТ живых карточек: если заданы skus — тянем ПОЛНЫЙ шорт-лист и берём ровно эти
    # SKU, ИГНОРИРУЯ limit. Причина — живой инцидент 2026-08-25: при повторной сборке топ-N «плавал»
    # (тай-брейк ранга), 9600167 выпал из топ-5 → повтор с --limit 5 залил бы ДУБЛЬ (новый 9600132) и
    # ОСИРОТИЛ бы ошибочную 9600167. Пиннинг по SKU обновляет ровно те карточки, что уже в каталоге:
    # без сирот, без дублей — «ни один товар не должен быть с ошибкой» держится буквально.
    want = {str(s).strip() for s in (skus or []) if str(s).strip()}
    pull_limit = 10 ** 6 if want else (limit or 10 ** 6)
    sh = categorist.shortlist(xlsx, city=city, max_cost=max_cost, markup_lo=markup_lo,
                              markup_hi=markup_hi, limit=pull_limit, slug=slug)
    selected = sh["shortlist"]
    skus_missing = []
    if want:
        selected = [r for r in selected if str(r.get("sku")) in want]
        skus_missing = sorted(want - {str(r.get("sku")) for r in selected})
    products = [shortlist_to_prod(r) for r in selected]

    category_params = None
    cid = card.market_category_id(slug, cats)
    if commit and cid is not None and hands.creds_present():
        try:
            category_params = hands.category_parameters(cid)
        except (hands.YMarketHTTPError, RuntimeError):
            category_params = None

    pre = preflight(products, slug, cats=cats, category_params=category_params)

    report = {
        "schema": "ymarket.runner.report.v1",
        "source": "donor",
        "ts": _now_iso(),
        "xlsx": sh["file"],
        "sheet": sh["sheet"],
        "slug": slug,
        "category_id": cid,
        "need_mapping_category": cid is None,
        "colmap": sh["colmap"],
        "donor_blocker": sh.get("blocker"),
        "dropship": {"max_cost": max_cost, "markup_range": [markup_lo, markup_hi],
                     "note": "донорская «Цена»=закупка; цена продажи предложена (×наценка), не из файла"},
        "categorist_agg": sh["agg"],
        "counts": {"rows_selected": len(selected),
                   "needs_data": sh["agg"].get("needs_data"),
                   "rejected": sh["agg"].get("rejected")},
        "skus_requested": sorted(want) if want else None,
        "skus_missing": skus_missing,
        "preflight": pre["agg"],
        "preflight_rows": pre["rows"],
        "creds_present": hands.creds_present(),
        "committed": False,
    }

    if commit:
        if not products:
            report["commit_blocked"] = (
                f"нет товаров под залив: skus {sorted(want)} не совпали с шорт-листом "
                f"(отсутствуют {skus_missing})" if want else "шорт-лист пуст — заливать нечего.")
        elif cid is None:
            report["commit_blocked"] = ("категория не подтверждена (marketCategoryId=null). "
                                        "resolve_category + впиши id.")
        elif not hands.creds_present():
            report["commit_blocked"] = "нет YANDEX_MARKET_API_KEY в env — реальный залив невозможен."
        else:
            com = commit_category(products, slug, cats=cats, category_params=category_params,
                                  business_id=business_id, campaign_id=campaign_id, vat=vat,
                                  available=available, pace=pace)
            report["committed"] = True
            report["commit"] = com["agg"]
            report["commit_rows"] = com["rows"]
            ids = [r["sku"] for r in com["rows"] if r.get("sku")]
            report["track"] = track(ids, business_id=business_id, dry=False, commit=True)

    report["elapsed_sec"] = round(time.time() - t0, 2)

    if write_report:
        try:
            REPORTS.mkdir(parents=True, exist_ok=True)
            out = REPORTS / f"ymarket_runner_donor_{slug}_{_stamp()}.json"
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["_report_file"] = str(out)
        except Exception as e:
            report["_report_file_error"] = str(e)
    return report


def run(xlsx, slug, vendor=None, commit=False, business_id=None, campaign_id=None,
        vat=None, pace=0.4, write_report=True):
    """Полный цикл вышки. По умолчанию — preflight (dry). --commit → + реальный залив и трекинг."""
    t0 = time.time()
    cats = card.load_cats()
    loaded = bridge.load_category(xlsx, slug=slug, vendor=vendor)
    products = loaded["products"]

    # категорийные параметры (для offer-cards) — только реальные, из API (нужен ключ+подтв. id)
    category_params = None
    cid = card.market_category_id(slug, cats)
    if commit and cid is not None and hands.creds_present():
        try:
            category_params = hands.category_parameters(cid)
        except (hands.YMarketHTTPError, RuntimeError):
            category_params = None  # честно: не смогли — параметры не грузим (не выдумываем)

    pre = preflight(products, slug, cats=cats, category_params=category_params)

    report = {
        "schema": "ymarket.runner.report.v1",
        "ts": _now_iso(),
        "xlsx": loaded["file"],
        "sheet": loaded["sheet"],
        "slug": slug,
        "category_id": cid,
        "need_mapping_category": cid is None,
        "colmap": loaded["colmap"],
        "spec_columns": loaded["spec_columns"],
        "counts": {"rows_parsed": len(products), "rows_skipped": loaded["skipped"]},
        "preflight": pre["agg"],
        "preflight_rows": pre["rows"],
        "creds_present": hands.creds_present(),
        "committed": False,
    }

    if commit:
        if cid is None:
            report["commit_blocked"] = ("категория не подтверждена (marketCategoryId=null в "
                                        "ymarket_cats_v1.json). Сначала resolve_category + впиши id.")
        elif not hands.creds_present():
            report["commit_blocked"] = ("нет YANDEX_MARKET_API_KEY в env — реальный залив невозможен "
                                        "(закон: не шлём вслепую).")
        else:
            com = commit_category(products, slug, cats=cats, category_params=category_params,
                                  business_id=business_id, campaign_id=campaign_id, vat=vat, pace=pace)
            report["committed"] = True
            report["commit"] = com["agg"]
            report["commit_rows"] = com["rows"]
            ids = [r["sku"] for r in com["rows"] if r.get("sku")]
            report["track"] = track(ids, business_id=business_id, dry=False, commit=True)

    report["elapsed_sec"] = round(time.time() - t0, 2)

    if write_report:
        try:
            REPORTS.mkdir(parents=True, exist_ok=True)
            out = REPORTS / f"ymarket_runner_{slug}_{_stamp()}.json"
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["_report_file"] = str(out)
        except Exception as e:
            report["_report_file_error"] = str(e)
    return report


def _print_summary(rep):
    pre = rep["preflight"]
    print(f"🛰  YMARKET RUNNER · {Path(rep['xlsx']).name}  slug={rep['slug']}")
    print(f"   колонки-смысл: {rep['colmap']}")
    print(f"   характеристик-колонок: {len(rep['spec_columns'])}  ({', '.join(rep['spec_columns'][:8])}{'…' if len(rep['spec_columns'])>8 else ''})")
    print(f"   товаров разобрано: {rep['counts']['rows_parsed']}  (пропущено: {rep['counts']['rows_skipped']})")
    cidnote = rep["category_id"] if rep["category_id"] is not None else "НЕ ПОДТВЕРЖДЁН (need_mapping)"
    print(f"   marketCategoryId: {cidnote}")
    print(f"\n   PREFLIGHT (сухо, 0₽):")
    print(f"     готовы лететь без ошибок: {pre['ok']}/{pre['total']}")
    print(f"     ждут подтверждения категории (need_mapping): {pre['need_mapping']}")
    print(f"     без фото: {pre['no_pictures']}")
    print(f"     с ошибками сборки: {pre['build_error']}")
    print(f"     с извлечёнными характеристиками: {pre['with_specs']}/{pre['total']}")
    # топ примеры спеки
    withspec = [r for r in rep["preflight_rows"] if r.get("n_specs")]
    for r in withspec[:5]:
        print(f"       · {r['sku']}: фото={r['n_pictures']} спека={r['specs']}")
    print(f"     creds (ключ Яндекса) есть: {rep['creds_present']}")
    if rep.get("commit_blocked"):
        print(f"\n   ⛔ РЕАЛЬНЫЙ ЗАЛИВ ЗАБЛОКИРОВАН: {rep['commit_blocked']}")
    if rep.get("committed"):
        c = rep["commit"]
        print(f"\n   COMMIT (реальный залив):")
        print(f"     опубликовано: {c['published']}/{c['total']}")
        print(f"     нужен контент: {c['need_content']}  ошибок: {c['errors']}  need_mapping: {c['need_mapping']}")
        tr = rep.get("track", {})
        if tr.get("ok"):
            print(f"     средний contentRating (index): {tr.get('avg_content_rating')}%")
    if rep.get("_report_file"):
        print(f"\n   📄 отчёт: {rep['_report_file']}")


def _print_summary_donor(rep):
    pre = rep["preflight"]
    ca = rep["categorist_agg"]
    dz = rep["dropship"]
    print(f"🛰  YMARKET RUNNER · ДОНОР · {Path(rep['xlsx']).name}  slug={rep['slug']}")
    print(f"   колонки-смысл: {rep['colmap']}")
    if rep.get("donor_blocker"):
        print(f"   ⛔ донор: {rep['donor_blocker']}")
    lo, hi = dz["markup_range"]
    print(f"   дропшип: закупка ≤{dz['max_cost']:g}₽ · цена продажи ПРЕДЛОЖЕНА ×{lo:g}–{hi:g} (не из файла)")
    print(f"   КАТЕГОРИЙЩИК: прочитано {ca.get('rows_read')} → шорт-лист {ca.get('selected')}, "
          f"нужны данные {ca.get('needs_data')}, отбой {ca.get('rejected')}")
    if rep.get("skus_requested"):
        line = f"   🎯 точечный ремонт SKU: {', '.join(rep['skus_requested'])}"
        if rep.get("skus_missing"):
            line += f"  ⚠️ НЕ найдены в шорт-листе: {', '.join(rep['skus_missing'])}"
        print(line)
    cidnote = rep["category_id"] if rep["category_id"] is not None else "НЕ ПОДТВЕРЖДЁН (авто-категория)"
    print(f"   marketCategoryId: {cidnote}")
    print(f"\n   PREFLIGHT (сухо, 0₽) по {pre['total']} товарам шорт-листа:")
    print(f"     готовы лететь без ошибок: {pre['ok']}/{pre['total']}")
    print(f"     с ошибками сборки: {pre['build_error']}  (цель = 0)")
    print(f"     без фото: {pre['no_pictures']}")
    print(f"     ТОП-заполнение (≥6 характеристик в карточке): {pre['topfill']}/{pre['total']}")
    print(f"     эмитится характеристик: среднее {pre.get('avg_emitted')}, минимум {pre.get('min_emitted')}")
    top = sorted([r for r in rep["preflight_rows"] if r.get("n_emitted")],
                 key=lambda r: -r["n_emitted"])
    for r in top[:6]:
        print(f"       · {r['sku']}: {r['n_emitted']} хар-к → {', '.join(str(x) for x in r['emitted'])}")
    print(f"     creds (ключ Яндекса) есть: {rep['creds_present']}")
    if rep.get("commit_blocked"):
        print(f"\n   ⛔ РЕАЛЬНЫЙ ЗАЛИВ ЗАБЛОКИРОВАН: {rep['commit_blocked']}")
    if rep.get("committed"):
        c = rep["commit"]
        print(f"\n   COMMIT (реальный залив): опубликовано {c['published']}/{c['total']}, "
              f"нужен контент {c['need_content']}, ошибок {c['errors']}")
        tr = rep.get("track", {})
        if tr.get("ok"):
            print(f"     средний contentRating (index): {tr.get('avg_content_rating')}%")
    if rep.get("_report_file"):
        print(f"\n   📄 отчёт: {rep['_report_file']}")


def _main(argv=None):
    ap = argparse.ArgumentParser(description="YMARKET RUNNER — залить категорию на Яндекс.Маркет с контролем (dry по умолчанию)")
    ap.add_argument("xlsx", help="XLSX категории (выгрузка парсера или ДОНОРСКАЯ выгрузка с --donor)")
    ap.add_argument("--slug", required=True, help="slug категории (ключ в ymarket_cats_v1.json)")
    ap.add_argument("--vendor", default=None, help="бренд (если есть)")
    ap.add_argument("--donor", action="store_true",
                    help="ДОНОРСКИЙ путь: читать сырую выгрузку поставщика (cargo-avto) КАТЕГОРИЙЩИКОМ "
                         "(дропшип: «Цена»=закупка, цену продажи предлагаем ×5–10, _spec → ТОП-заполнение)")
    ap.add_argument("--city", default=None, help="город для тарифа/экономики (донорский путь)")
    ap.add_argument("--max-cost", type=float, default=categorist.DEFAULT_MAX_COST_RUB,
                    help="потолок закупки ₽ (донорский путь; врываемся дёшево)")
    ap.add_argument("--markup-lo", type=float, default=categorist.DEFAULT_MARKUP_LO)
    ap.add_argument("--markup-hi", type=float, default=categorist.DEFAULT_MARKUP_HI)
    ap.add_argument("--limit", type=int, default=None, help="ограничить число товаров шорт-листа")
    ap.add_argument("--skus", default=None,
                    help="ТОЧЕЧНЫЙ РЕМОНТ: точные SKU через запятую. Тянем полный шорт-лист и берём "
                         "ровно эти SKU, ИГНОРИРУЯ --limit — чтобы обновить именно живые карточки, "
                         "не осиротив ошибочную и не создав дубль. Пример: --skus 9600167,9601478")
    ap.add_argument("--commit", action="store_true", help="РЕАЛЬНЫЙ залив (нужен ключ+подтв. категория)")
    ap.add_argument("--find-category", default=None, help="искать листовую marketCategoryId по подстроке (READ, нужен ключ)")
    ap.add_argument("--business-id", default=None)
    ap.add_argument("--campaign-id", default=None)
    ap.add_argument("--vat", default=None)
    ap.add_argument("--not-available", action="store_true",
                    help="КАРТОЧКИ-ТОЛЬКО: залить контент, но НЕ делать товар заказуемым "
                         "(available=false). Безопасный первый RUBICON под железным законом исполнения: "
                         "карточка индексируется и растёт к ТОП, но купить нельзя, пока DBS-петля "
                         "«выкуп у донора после оплаты» не поставлена. По умолчанию товар заказуем.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.find_category:
        res = resolve_category(args.find_category, dry=not args.commit, commit=args.commit)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    if args.donor:
        skus = [s for s in (args.skus.split(",") if args.skus else []) if s.strip()]
        rep = run_donor(args.xlsx, slug=args.slug, city=args.city, max_cost=args.max_cost,
                        markup_lo=args.markup_lo, markup_hi=args.markup_hi, limit=args.limit,
                        skus=skus or None, commit=args.commit, business_id=args.business_id,
                        campaign_id=args.campaign_id, vat=args.vat,
                        available=not args.not_available)
        if args.json:
            print(json.dumps(rep, ensure_ascii=False, indent=2))
        else:
            _print_summary_donor(rep)
        return 0

    rep = run(args.xlsx, slug=args.slug, vendor=args.vendor, commit=args.commit,
              business_id=args.business_id, campaign_id=args.campaign_id, vat=args.vat)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_summary(rep)
    return 0


if __name__ == "__main__":
    sys.exit(_main())

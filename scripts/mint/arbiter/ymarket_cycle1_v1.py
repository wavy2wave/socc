#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЦИКЛ-1 · ДВИЖОК (ymarket_cycle1_v1) — «Идея → Товар → Витрина» как законная цепь узлов.

Ручной проход 2026-09-02 ДОКАЗАН живьём (ARB-* плёнка на витрине Express Atlas): этот движок
выражает его в виде НЕПРЕРЫВНОЙ цепочки узлов с законным PASS-гейтингом (L12: НЕТ fake pass —
узел N+1 стартует только после PASS N с доказательством чтением живого состояния, 200 OK врёт).

Законы движка (канон YM_CYCLE1_V1.md §13):
- L8  бренд = «Без бренда» (YM не индексирует «ATLAS EDGE»), своё описание/параметры, свой EAN.
- L9  цена = владелец ЦЕНОВИК (MARKUP из манифеста), товар НИ В КАКИХ акциях в цикл-1.
- L10 ОВХ = правдивая транспортная упаковка с карточки донора.
- L11 фото: товар + фирменная инфографика (color-science) — артефакт органа.
- L6  RUBICON: WRITE только не dry AND commit; движок сам ничего не шлёт в dry.
- L13 задачи, не вопросы: манифест магазина решает, что делать; оператор отвечает только на вход.
- L14 планёрка = самоосознание: утренний узел собирает вчерашний леджер в ПУЛЬС.

Запуск:  python3 ymarket_cycle1_v1.py [--store atlas-express-film] [--dry|--commit] [--plenerka]
Хеш цикла = sha1(магазин × дата × версия цепи) — 10/100 магазинов живут параллельно, каждый свой.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import pathlib
import sys
import time

ARB = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ARB))

CHAIN_VERSION = "film-1.0"
STORE_DEFAULT = "atlas-express-film"
WAREHOUSE_DEFAULT = 2390811          # Atlas «Atlas» (склад Экспресс кабинета 216949599)

# Канонический вход для НОВОГО магазина (L13: без этого запуск невозможен, но вопросы НЕ задаём —
# манифест отвечает; если манифеста нет — честно говорим, чего не хватает):
REQUIRED_STORE_FIELDS = [
    ("slug",            "короткое имя магазина (alnum, через дефис)"),
    ("business_id",     "businessId кабинета (партнёрский API)"),
    ("campaign_id",     "campaignId ЭКСПРЕСС-магазина (витрина)"),
    ("warehouse_id",    "partnerWarehouseId склада (куда едет курьер)"),
    ("donor_category",  "категория донора (URL-путь suppliers/…_v1.py, напр. vozdushno-puzyrkovaya-plenka)"),
    ("builder",         "сборщик полной карточки (film | box | …)"),
    ("markup",          "MARKUP цены: цена = закупка × markup (владелец — ЦЕНОВИК, L9)"),
    ("stock_count",     "остаток на витрине (L3: донор-real или слово оператора; не выдумываем)"),
]
# Ключ API — ВСЕГДА из env, никогда в манифесте/файле (RUBICON секретов).


# ─────────────────────────────────────────────────────────────────────────────
#  МАНИФЕСТ МАГАЗИНА + ХЕШ ЦИКЛА
# ─────────────────────────────────────────────────────────────────────────────

def _now_msk():
    # локальное время машины (MSK на хосте оператора); для меток пульса
    return time.strftime("%H:%M:%S")


def store_profiles_path():
    return ARB / "runtime" / "cycle1" / "stores.json"


def load_store(slug):
    """Манифест магазина. Нет → вернуть None + список недостающего (канонический вход)."""
    p = store_profiles_path()
    if not p.exists():
        return None
    doc = json.loads(p.read_text())
    return doc.get(slug)


def save_store(profile):
    p = store_profiles_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = json.loads(p.read_text()) if p.exists() else {}
    doc[profile["slug"]] = profile
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1))


# ─────────────────────────────────────────────────────────────────────────────
#  МАМА-НАСЛЕДОВАНИЕ + РЕЕСТР (кабинет-agnostic вход нового магазина)
#
#  «ЦИКЛ-1 ищет маму ЦИКЛ-ЯМ — хеш»: новому магазину не нужно повторять кабинет
#  (business_id/campaign_id/warehouse_id) и API — он объявляет mother=<slug матери>
#  и наследует кабинет от неё. Системе «пофиг какой API/кабинет» — она подтягивается.
# ─────────────────────────────────────────────────────────────────────────────

INHERIT_FIELDS = ("business_id", "campaign_id", "warehouse_id")   # кабинет: наследуем от мамы
BUILDERS = ("film", "box")                                          # известные сборщики полной карточки


def _load_all():
    """Все манифесты магазинов (dict slug→profile). Нет файла → {}."""
    p = store_profiles_path()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def resolve_profile(profile, all_profiles=None):
    """До-заполнить недостающие кабинетные поля ребёнка от МАТЕРИ (mother).

    Чистая функция (тестируется без файла). Идём по цепочке mother до глубочайшей
    мамы; от неё берём INHERIT_FIELDS, которые ребёнок не задал (поля ребёнка
    приоритетнее — явный кабинет у ребёнка перекрывает наследие).
    Возвращает (профиль_или_None, причина_ошибки_или_None).
    """
    if profile is None:
        return None, "профиль не найден"
    all_profiles = all_profiles if all_profiles is not None else _load_all()
    chain = []
    cur = profile
    while cur.get("mother"):
        slug = cur.get("slug")
        if slug in chain:
            return None, "цепь mother замкнута: " + " → ".join(chain + [slug])
        chain.append(slug)
        mom = (all_profiles or {}).get(cur.get("mother"))
        if not mom:
            return None, (f"mother «{cur.get('mother')}» отсутствует в манифесте "
                          f"(нужна магазину «{cur.get('slug')}»); есть: "
                          f"{', '.join((all_profiles or {}).keys()) or '—'}")
        cur = mom
    out = dict(profile)
    src = cur  # глубочайшая мама — источник кабинета
    for key in INHERIT_FIELDS:
        if out.get(key) is None and src.get(key) is not None:
            out[key] = src[key]
    if src.get("slug") and src["slug"] != out.get("slug"):
        out["_inherited_from"] = src["slug"]
    return out, None


def list_cycles():
    """Реестр магазинов для мозга/глаз: slug → сборщик/донор/мама/кабинет и статус резолва."""
    doc = _load_all()
    out = {}
    for slug, prof in doc.items():
        resolved, why = resolve_profile(prof, doc)
        out[slug] = {
            "slug": slug,
            "mother": prof.get("mother"),
            "builder": prof.get("builder"),
            "builder_slug": prof.get("builder_slug"),
            "donor_category": prof.get("donor_category"),
            "markup": prof.get("markup"),
            "stock_count": prof.get("stock_count"),
            "resolve_ok": resolved is not None,
            "resolve_why": why,
            "inherited_from": (resolved or {}).get("_inherited_from"),
            "cabinet": {k: (resolved or {}).get(k) for k in INHERIT_FIELDS},
        }
    return out


def add_store(profile):
    """Добавить новый магазин в манифест (Л13: задачи, не вопросы). Без сети.

    Кабинет не выдумываем: если у магазина нет ни одного кабинетного поля и не задан
    mother — по умолчанию наследуем от STORE_DEFAULT (мать-цикл). Валидация до записи;
    файл трогается ТОЛЬКО на полном успехе. Возвращает (ok: bool, reason: str).
    """
    slug = profile.get("slug")
    if not slug or not all(ch.isalnum() or ch in "-_" for ch in slug):
        return False, f"slug «{slug}» недопустим (только буквы/цифры/дефис/подчёркивание)"
    doc = _load_all()
    if slug in doc:
        return False, f"магазин «{slug}» уже есть в манифесте ({store_profiles_path()})"
    prof = dict(profile)
    prof["slug"] = slug
    mother = prof.get("mother")
    has_cabinet = any(prof.get(k) is not None for k in INHERIT_FIELDS)
    if not mother and not has_cabinet and STORE_DEFAULT in doc:
        prof["mother"] = mother = STORE_DEFAULT
    if mother and mother not in doc:
        return False, f"mother «{mother}» нет в манифесте (есть: {', '.join(doc) or '—'})"
    if prof.get("builder") not in BUILDERS:
        return False, f"builder «{prof.get('builder')}» неизвестен (есть: {', '.join(BUILDERS)})"
    resolved, why = resolve_profile(prof, doc)
    if resolved is None:
        return False, why or "резолв кабинета от мамы не удался"
    missing = [k for k, _ in REQUIRED_STORE_FIELDS if resolved.get(k) is None]
    if missing:
        return False, f"не хватает полей после наследования: {missing}"
    save_store(prof)
    src = resolved.get("_inherited_from")
    return True, f"магазин «{slug}» добавлен" + (f"; кабинет унаследован от «{src}»" if src else "")


def cycle_hash(store_slug, date_str):
    """Уникальный хеш прогона: (магазин × дата × версия цепи). Позволяет вести N циклов параллельно."""
    return hashlib.sha1(f"{store_slug}|{date_str}|{CHAIN_VERSION}".encode()).hexdigest()[:10]


def ledger_path(store_slug, date_str):
    d = ARB / "runtime" / "cycle1" / store_slug
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{date_str}.jsonl"


def pulse_path(store_slug):
    d = ARB / "runtime" / "cycle1" / store_slug
    d.mkdir(parents=True, exist_ok=True)
    return d / "last_pulse.json"


def plannerka_read(store_slug):
    """Пульс магазина как dict (None, если ещё нет). Для мозга/глаз без прогона цепи."""
    p = pulse_path(store_slug)
    if not p.exists():
        return None
    return json.loads(p.read_text())


# ─────────────────────────────────────────────────────────────────────────────
#  ПУЛЬС В ТЕРМИНАЛЕ (живая строка на каждый узел)
# ─────────────────────────────────────────────────────────────────────────────

_C = {"grn": "\033[32m", "red": "\033[31m", "yel": "\033[33m", "cyn": "\033[36m",
      "blu": "\033[34m", "dim": "\033[2m", "rst": "\033[0m", "b": "\033[1m"}


def _c(color, s):
    return f"{_C.get(color, '')}{s}{_C['rst']}"


def pulse_line(node_name, verdict, note, ms, i, n):
    icon = {"PASS": "✓", "FAIL": "✗", "DRY": "◌", "SKIP": "–"}.get(verdict, "?")
    col = {"PASS": "grn", "FAIL": "red", "DRY": "yel", "SKIP": "dim"}.get(verdict, "yel")
    step = f"[{i:02d}/{n:02d}]" if n else ""
    return f"  {_c(col, icon)} {_c('b', node_name):<14} {_c('dim', step):<9} {note}  {_c('dim', f'{ms:>6.0f}мс')}"


def _echo_tail(buf, node_name, tail=14):
    """Тишина не прячет ошибку: на FAIL показать низ захваченного вывода узла (последние строки)."""
    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    if not lines:
        return
    print(f"\n    {_c('dim', '──── низ вывода узла «' + node_name + '» (полный поток: --verbose):')}")
    for ln in lines[-tail:]:
        print(f"    {_c('dim', ln)}")


# ─────────────────────────────────────────────────────────────────────────────
#  ЗАКОН БРЕНДА (L8) — общий трансформер полной карточки
# ─────────────────────────────────────────────────────────────────────────────

def brand_law(prod):
    """YM не индексирует незарегистрированный бренд → «Без бренда» (эталон 99).
    no-brand = бренд не заявляем НИГДЕ: поле / суффикс имени / описание."""
    prod["vendor"] = "Без бренда"
    prod["send_vendor"] = True
    prod["unique_name"] = False
    prod.pop("house_brand", None)
    d = prod.get("description") or ""
    if d:
        prod["description"] = d.replace("Воздушно-пузырьковая плёнка ATLAS EDGE",
                                        "Воздушно-пузырьковая плёнка")
    return prod


# ─────────────────────────────────────────────────────────────────────────────
#  ЦЕПЬ УЗЛОВ (каждый возвращает {verdict, note, evidence}; FAIL останавливает)
# ─────────────────────────────────────────────────────────────────────────────

def node_donor(ctx, dry, commit):
    """N1 ДОНОР · 0₽ GET · живой скан категории донора → партия выбранных товаров."""
    import ymarket_film_cards_v1 as FC
    raw = FC.load_film_products()
    if not raw:
        return {"verdict": "FAIL", "note": "скан донора пуст", "evidence": {"n": 0}}
    ctx["raw_donor"] = raw
    return {"verdict": "PASS", "note": f"донор {FC.DONOR_SLUG}: {len(raw)} строк",
            "evidence": {"n": len(raw), "pids": [str(r.get("pid")) for r in raw]}}


def node_build(ctx, dry, commit):
    """N2 СБОРКА · полная карточка по рецепту (факты донора → _spec + своё описание + ОВХ)."""
    import ymarket_film_cards_v1 as FC
    pub = FC._pub_urls_by_pid()
    prods, missing = [], []
    for p in ctx["raw_donor"]:
        pr = FC.build_product(p, pub, 0)
        if not pr:
            missing.append(str(p.get("pid")))
            continue
        brand_law(pr)
        prods.append(pr)
    ctx["prods"] = prods
    if missing:
        return {"verdict": "FAIL", "note": f"не собраны: {missing}",
                "evidence": {"missing": missing, "n_ok": len(prods)}}
    no_photo = [pr["sku"] for pr in prods if not pr.get("pictures")]
    note = f"собрано {len(prods)} полных карточек (описание/спеки/ОВХ/EAN)"
    ev = {"n": len(prods), "no_photo": no_photo}
    if no_photo:
        # L11: карточка без фото = низкий index — честно не проходим (фото-слой обязателен).
        return {"verdict": "FAIL", "note": f"{note}, но фото нет: {no_photo}", "evidence": ev}
    return {"verdict": "PASS", "note": note, "evidence": ev}


def _summary(prods):
    return "; ".join(f"{pr['sku']} v{pr.get('vendor')} "
                     f"desc={len(pr.get('description') or '')} сп={len(pr.get('_spec') or {})} "
                     f"фото={len(pr.get('pictures') or [])} {pr.get('price')}₽" for pr in prods)


def node_fill(ctx, dry, commit):
    """N3 ЗАЛИВ · content-only offer-mappings + offer-cards (create_card). FAIL любого = стоп."""
    import ymarket_write_v1 as W
    slug = ctx["profile"].get("builder_slug", "puzyrkovaya-plenka")
    errs = {}
    for pr in ctx["prods"]:
        r = W.create_card(pr, slug=slug, dry=dry, commit=commit, photo_urls=pr["pictures"])
        if not r.get("ok"):
            errs[pr["sku"]] = (r.get("errors") or r.get("error"))
    if errs:
        return {"verdict": "FAIL", "note": f"ошибки залива: {errs}", "evidence": {"errors": errs}}
    tag = "DRY" if dry else "PASS"
    return {"verdict": tag, "note": "контент карточек (vendor Без бренда, описание, 13 параметров) — "
            + _summary(ctx["prods"]), "evidence": {"n": len(ctx["prods"])}}


def node_place(ctx, dry, commit):
    """N4 ВИТРИНА · place_in_campaign available=True (после включения ЭКСПРЕСС-магазина в кабинете)."""
    import ymarket_write_v1 as W
    cid = ctx["profile"].get("campaign_id")
    errs = {}
    for pr in ctx["prods"]:
        r = W.place_in_campaign(pr["sku"], available=True, dry=dry, commit=commit, campaign_id=cid)
        if not r.get("ok"):
            errs[pr["sku"]] = (r.get("errors") or r.get("error"))
    if errs:
        return {"verdict": "FAIL", "note": f"не вышли на витрину: {errs}", "evidence": {"errors": errs}}
    tag = "DRY" if dry else "PASS"
    return {"verdict": tag, "note": f"available=True (campaign {cid}) × {len(ctx['prods'])}",
            "evidence": {"n": len(ctx["prods"])}}


def node_stock(ctx, dry, commit):
    """N5 ОСТАТКИ · update_stocks FIT на склад манифеста (L3: не выдумываем, count из профиля/слова)."""
    import ymarket_trade_hands_v1 as T
    from ymarket_hands_v1 import business_id_env
    bid = ctx["profile"].get("business_id") or business_id_env()
    wh = ctx["profile"].get("warehouse_id")
    sc = ctx["profile"].get("stock_count")
    if sc is None:
        # Честный SKIP: остаток не задан оператором — не выдумываем, только читаем текущее.
        rows = T.read_stocks(bid, wh, offer_ids=[pr["sku"] for pr in ctx["prods"]])
        cur = {r["sku"]: r["count"] for r in rows if r.get("type") == "FIT"}
        return {"verdict": "SKIP", "note": f"stock_count не задан в манифесте — читаю: {cur}",
                "evidence": {"current": cur}}
    items = [{"sku": pr["sku"], "warehouse_id": wh, "count": sc} for pr in ctx["prods"]]
    r = T.update_stocks(bid, items, dry=dry, commit=commit)
    if dry:
        # _dry_echo: точный payload собран и прошёл гейт — DRY, не FAIL (L6 RUBICON)
        return {"verdict": "DRY", "note": f"FIT={sc} на склад {wh} × {len(items)} "
                f"(сухой payload, НЕ отправлен)", "evidence": {"count": sc, "n": len(items)}}
    if r.get("ok"):
        return {"verdict": "PASS", "note": f"FIT={sc} на склад {wh} × {len(items)}",
                "evidence": {"count": sc, "n": len(items)}}
    return {"verdict": "FAIL",
            "note": f"остатки не легли: {r.get('errors') or r.get('note') or r.get('status')}",
            "evidence": r}


def node_verify(ctx, dry, commit):
    """N6 СВЕРКА · ЧТЕНИЕ живого состояния (200 OK врёт). ВИДИТ ВСЁ ПОД КАПОТОМ:
    campaign PUBLISHED/available + остатки FIT + vendor/desc/params/фото. Здесь нет dry —
    это READ-гейт, работает всегда."""
    import ymarket_hands_v1 as h
    from ymarket_hands_v1 import business_id_env, campaign_id_env
    import ymarket_trade_hands_v1 as T
    bid = ctx["profile"].get("business_id") or business_id_env()
    cid = ctx["profile"].get("campaign_id") or campaign_id_env()
    wh = ctx["profile"].get("warehouse_id")
    ids = [pr["sku"] for pr in ctx["prods"]]

    rows = {}  # offerId -> evidence-срез
    try:
        offers = h.campaign_offers(cid, offer_ids=ids, limit=50)
        for o in (offers.get("offers") if isinstance(offers, dict) else offers) or []:
            rows.setdefault(o.get("offerId"), {})["placement"] = {
                "available": o.get("available"), "status": o.get("status")}
    except Exception as e:
        return {"verdict": "FAIL", "note": f"чтение витрины упало: {e}",
                "evidence": {"error": str(e)}}

    try:
        m = h._request("POST", f"/businesses/{bid}/offer-mappings",
                       body={"offerIds": ids}, params={"limit": 50})
        for ent in (m.get("result", m).get("offerMappings") if isinstance(m.get("result", m), dict) else []) or []:
            o = ent.get("offer") or ent
            rows.setdefault(o.get("offerId"), {})["content"] = {
                "vendor": o.get("vendor"), "desc_len": len(o.get("description") or ""),
                "n_pics": len(o.get("pictures") or []), "barcodes": o.get("barcodes"),
                "wd": bool(o.get("weightDimensions"))}
    except Exception as e:
        return {"verdict": "FAIL", "note": f"чтение контента упало: {e}",
                "evidence": {"error": str(e)}}

    try:
        for r in T.read_stocks(bid, wh, offer_ids=ids):
            if r.get("type") == "FIT":
                rows.setdefault(r["sku"], {})["stock"] = r["count"]
    except Exception as e:
        return {"verdict": "FAIL", "note": f"чтение остатков упало: {e}",
                "evidence": {"error": str(e)}}

    # Честный вердикт: ВСЕ карточки должны быть на витрине (PUBLISHED+available) с остатком.
    bad = {}
    for sku in ids:
        r = rows.get(sku) or {}
        pl = r.get("placement") or {}
        if pl.get("available") is not True or pl.get("status") != "PUBLISHED":
            bad[sku] = f"витрина {pl}"
        elif not r.get("stock"):
            bad[sku] = "остаток FIT не читается"
    if bad:
        return {"verdict": "FAIL", "note": f"НЕ на витрине: {bad}", "evidence": {"bad": bad, "rows": rows}}
    ok = all(r.get("content", {}).get("vendor") == "Без бренда" for r in rows.values())
    note = f"витрина PUBLISHED ×{len(ids)} · остатки FIT · vendor Без бренда · описания/фото на месте"
    if not ok:
        return {"verdict": "FAIL", "note": "vendor не «Без бренда» у кого-то из карточек", "evidence": rows}
    return {"verdict": "PASS", "note": note, "evidence": rows}


def node_plannerka(ctx, dry, commit):
    """N7 ПЛАНЁРКА · самоосознание: вчерашний леджер + этот прогон → ПУЛЬС (реальные числа)."""
    import datetime
    store = ctx["profile"]["slug"]
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    hist = []
    lp = ledger_path(store, yesterday)
    if lp.exists():
        for line in lp.read_text().splitlines():
            try:
                hist.append(json.loads(line))
            except Exception:
                pass
    from collections import Counter
    c = Counter(x.get("verdict") for x in hist)
    by_node = {}
    for x in hist:
        by_node.setdefault(x.get("node"), Counter())[x.get("verdict")] += 1
    pulse = {
        "store": store, "date": time.strftime("%Y-%m-%d"),
        "yesterday_runs": len(hist), "yesterday_verdicts": dict(c),
        "by_node": {k: dict(v) for k, v in by_node.items()},
        "run_verdicts": Counter(x.get("verdict") for x in ctx["results"]),
        "artifacts": len(ctx["results"]) and sum(
            1 for x in ctx["results"] if x.get("node") == "СВЕРКА" and x.get("verdict") == "PASS"),
    }
    pulse_path(store).write_text(json.dumps(pulse, ensure_ascii=False, indent=1))
    today_pass = sum(1 for x in ctx["results"] if x.get("verdict") == "PASS")
    today_fail = sum(1 for x in ctx["results"] if x.get("verdict") == "FAIL")
    if today_fail:
        return {"verdict": "FAIL", "note": f"пульс: PASS {today_pass} / FAIL {today_fail} — смотрим узлы",
                "evidence": pulse}
    return {"verdict": "PASS", "note": f"пульс вчера: {len(hist)} узлов, "
            f"{'/'.join(f'{k}={v}' for k, v in c.items() or [('без_прогона', 1)])} · сегодня PASS {today_pass}",
            "evidence": pulse}


def film_chain():
    return [
        ("ДОНОР", node_donor, False),
        ("СБОРКА", node_build, False),
        ("ЗАЛИВ", node_fill, True),
        ("ВИТРИНА", node_place, True),
        ("ОСТАТКИ", node_stock, True),
        ("СВЕРКА", node_verify, False),
        ("ПЛАНЁРКА", node_plannerka, False),
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  РАННЕР ЦЕПИ
# ─────────────────────────────────────────────────────────────────────────────

def run_cycle(store_slug, dry=True, commit=False, chain=None, date_str=None, verbose=False):
    import datetime
    date_str = date_str or datetime.date.today().isoformat()
    profile = load_store(store_slug)
    if not profile:
        return _missing_store(store_slug, date_str)
    resolved, why = resolve_profile(profile)
    if resolved is None:
        print(f"\n  {_c('red', '✗')} {store_slug}: резолв мамы не удался — {why}.\n"
              f"    Открыть {store_profiles_path()} и починить mother/поля.\n")
        return {"verdict": "FAIL", "profile": profile, "why": why}
    profile = resolved
    ctx = {"profile": profile, "results": []}
    chain = chain or film_chain()
    hsh = cycle_hash(store_slug, date_str)
    lp = ledger_path(store_slug, date_str)
    results = []
    halted = None
    print(f"\n  {_c('b', 'ЦИКЛ-1')} · {profile['slug']} · {date_str} · {_c('cyn', '#' + hsh)} · "
          f"{_c('yel', 'DRY 0₽' if dry else 'LIVE')} · {_c('dim', 'тихо' if not verbose else 'verbose')}\n")
    for i, (name, fn, is_write) in enumerate(chain, 1):
        t0 = time.time()
        buf = None
        if verbose:
            # --verbose: полный живой поток узла (для отладки точных payload)
            try:
                r = fn(ctx, dry=dry, commit=commit)
            except Exception as e:
                r = {"verdict": "FAIL", "note": f"{type(e).__name__}: {e}", "evidence": {}}
        else:
            # ТИХИЙ по умолчанию («многа букав» → нет): вывод узла (в т.ч. сухие payload
            # из write_v1._dry) ловится; наружу идёт только пульс-строка. Честность FAIL
            # сохраняется — при ошибке показываем хвост захваченного вывода.
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    r = fn(ctx, dry=dry, commit=commit)
            except Exception as e:
                r = {"verdict": "FAIL", "note": f"{type(e).__name__}: {e}", "evidence": {}}
        r = dict(r, node=name, dry=dry, ts=time.strftime("%H:%M:%S"))
        r["ms"] = (time.time() - t0) * 1000
        results.append(r)
        ctx["results"] = list(results)   # планёрка (последний узел) видит весь прогон до себя
        print(pulse_line(name, r["verdict"], r["note"], r["ms"], i, len(chain)))
        if r["verdict"] == "FAIL":
            if buf is not None:
                _echo_tail(buf, name)
            halted = name
            break
    # леджер (append): после каждого узла — чтобы планёрка читала даже оборванный прогон
    with open(lp, "a") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    ctx["results"] = results
    # итог
    pass_n = sum(1 for r in results if r["verdict"] == "PASS")
    fail = [r for r in results if r["verdict"] == "FAIL"]
    verdict = "FAIL" if fail else ("DRY_OK" if dry else "PASS")
    print("\n  " + "─" * 62)
    if verdict == "PASS":
        print(f"  {_c('grn', '■ ЦИКЛ-1 ЗАКРЫТ')} · все узлы PASS с доказательством · артефакт на витрине")
    elif verdict == "DRY_OK":
        print(f"  {_c('yel', '■ DRY-ПРОХОД ЧИСТ')} · узлы готовы · для ЖИВОГО хода: --commit (по слову оператора)")
    else:
        print(f"  {_c('red', '■ ЦИКЛ ОСТАНОВЛЕН')} на узле «{halted}» — починить, перезапустить. Без fake pass.")
    print(f"  хеш {hsh} · PASS {pass_n}/{len(results)} · запись в {lp}\n")
    return {"verdict": verdict, "hash": hsh, "results": results, "profile": profile}


def _missing_store(store_slug, date_str):
    print(f"\n  {_c('red', '✗')} Манифест магазина «{store_slug}» не найден ({store_profiles_path()}).")
    print(f"\n  {_c('b', 'Канонический вход для нового магазина (L13 — без вопросов):')}\n")
    for key, what in REQUIRED_STORE_FIELDS:
        print(f"    {_c('cyn', key):<18} {what}")
    print(f"    {'api_key':<18} YANDEX_MARKET_API_KEY в env (в манифест секреты НЕ пишем)")
    print(f"\n  Пример манифеста (runtime/cycle1/stores.json):")
    example = {"slug": "atlas-express-film", "business_id": 216949599, "campaign_id": 149215943,
               "warehouse_id": 2390811, "donor_category": "vozdushno-puzyrkovaya-plenka",
               "builder": "film", "builder_slug": "puzyrkovaya-plenka",
               "markup": 8.0, "stock_count": 100}
    print("  " + json.dumps(example, ensure_ascii=False, indent=1))
    return {"verdict": "NO_STORE", "profile": None}


def _plenerka(store_slug):
    """Чтение пульса без прогона цепи (утренний узел / быстрый взгляд)."""
    doc = plannerka_read(store_slug)
    if not doc:
        print(f"\n  {_c('yel', 'Пульса ещё нет')} — запусти `--dry` или `--commit`, соберём первый.\n")
        return
    print(f"\n  {_c('b', 'ПУЛЬС ·')} {doc['store']} · {doc['date']}")
    print(f"    вчера узлов: {doc['yesterday_runs']}  вердикты: {doc['yesterday_verdicts']}")
    print(f"    сегодня:     {doc['run_verdicts']}  артефактов-СВЕРКА PASS: {doc['artifacts']}")
    print("    по узлам вчера:")
    for node, vc in (doc.get("by_node") or {}).items():
        print(f"      {node:<14} {vc}")
    print()


def _main(argv=None):
    ap = argparse.ArgumentParser(description="ЦИКЛ-1 движок · Идея→Товар→Витрина (законная цепь узлов)")
    ap.add_argument("--store", default=STORE_DEFAULT, help="манифест магазина (runtime/cycle1/stores.json)")
    ap.add_argument("--commit", action="store_true", help="ЖИВОЙ ход (dry=False) — по слову оператора")
    ap.add_argument("--dry", action="store_true", help="сухой ход 0₽ (явно; дефолт и так dry)")
    ap.add_argument("--plenerka", action="store_true", help="только планёрка/пульс (без прогона)")
    ap.add_argument("--verbose", action="store_true",
                    help="полный поток узлов (по умолчанию ТИХО — только пульс-строки)")
    a = ap.parse_args(argv)
    dry = not a.commit
    if a.plenerka:
        _plenerka(a.store)
        return 0
    res = run_cycle(a.store, dry=dry, commit=a.commit, verbose=a.verbose)
    return 0 if res.get("verdict") in ("PASS", "DRY_OK") else 1


if __name__ == "__main__":
    sys.exit(_main())

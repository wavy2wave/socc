#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WB SCOUT V1 — нос органа ARBITER со стороны СПРОСА (то, чего каталогу MINT не хватало).

Сканирует публичные endpoints Wildberries (БЕЗ ключей, БЕЗ авторизации) и превращает
живой каталог в кандидат-связки в ТОЧНО той схеме, что ждёт PROSPECTOR.falsifiable_test:

    {"name", "cost", "url", "sku", "demand_signal": {...}}

Слово о честности сигнала спроса (граница модели, не факта):
  У публичного WB нет поля «продано N штук». Мы НЕ рисуем объём. Мы читаем НАБЛЮДАЕМЫЕ
  прокси — цена, число отзывов (rating count), суммарный остаток по складам, позиция в
  выдаче — и собираем из них demand_signal с ЯВНЫМ kind. Точный объём даёт платная
  аналитика (MPStats и т.п.) — она вставляется как СМЕННЫЙ адаптер (DEMAND_SOURCES),
  не переписывая скаут. velocity() меряет ИЗМЕНЕНИЕ во времени (дельта отзывов/остатков
  между снимками) — вот это уже настоящая «скорость», а не мгновенный снимок.

Закон ARBITER: stdlib-only (urllib, без requests — 0 зависимостей навсегда), ленивая сеть,
fail-soft (любая стадия падает мягко в пустой/None результат, конвейер живёт), без демона
(один ограниченный проход на вызов; вечный цикл — снаружи, через arbiter_scout_loop).

CLI:
  python3 wb_scout_v1.py --category 9101 --city msk --limit 40
  python3 wb_scout_v1.py --snapshot  --category 9101      # снять снимок для velocity
  python3 wb_scout_v1.py --velocity  --category 9101      # дельта против прошлого снимка
"""
import os
import sys
import json
import gzip
import argparse
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent  # SOCC/
SNAP_DIR = ROOT / "MEMORY_WAVE/reports/mint/arbiter/snapshots"

# Публичные хосты WB (без ключей). dest — регион выдачи (влияет на остатки/цену/позицию).
CATALOG_HOST = "https://catalog.wb.ru"
SEARCH_HOST = "https://search.wb.ru"
CARD_HOST = "https://card.wb.ru"

# Регион → dest-код WB (крупнейшие города, как в задаче: МСК/СПб/крупные).
# dest — приблизительные региональные коды публичного WB; при -1 отдаётся общероссийская выдача.
CITY_DEST = {
    "msk": -1257786,   # Москва и МО
    "spb": -1123300,   # Санкт-Петербург
    "ekb": -5510930,   # Екатеринбург
    "nsk": -364763,    # Новосибирск
    "kdr": -2133463,   # Краснодар
    "ru": -1,          # общероссийская выдача
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Гард релевантности — единый с адаптерным слоем (suppliers/base_v1). fail-open: если пакет
# suppliers недоступен, НЕ фильтруем (старое поведение), скаут никогда не падает из-за импорта.
try:
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    from suppliers.base_v1 import filter_relevant as _filter_relevant
except Exception:
    def _filter_relevant(products, query, name_key="name"):
        return list(products or [])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get(url, timeout=20):
    """Один ленивый GET публичного WB. fail-soft: сеть/парс упали → None (конвейер живёт)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip",
        "Origin": "https://www.wildberries.ru",
        "Referer": "https://www.wildberries.ru/",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return None


def _price_rub(prod):
    """Цена товара в ₽ из карточки WB (копейки → рубли; берём итоговую sale-цену)."""
    # Новый формат: sizes[].price.total (копейки). Старый: salePriceU/priceU (копейки).
    try:
        for sz in prod.get("sizes", []) or []:
            pr = (sz.get("price") or {})
            val = pr.get("total") or pr.get("product")
            if val:
                return round(val / 100.0, 2)
    except Exception:
        pass
    val = prod.get("salePriceU") or prod.get("priceU") or 0
    return round((val or 0) / 100.0, 2)


def _total_stock(prod):
    """Суммарный остаток по всем складам/размерам (прокси предложения; дельта = скорость ухода)."""
    total = 0
    try:
        for sz in prod.get("sizes", []) or []:
            for st in sz.get("stocks", []) or []:
                total += int(st.get("qty") or 0)
    except Exception:
        return 0
    return total


def _wb_url(nm_id):
    return f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"


def _demand_signal(prod, position):
    """Собрать demand_signal с ЯВНЫМ kind из наблюдаемых прокси (не выдумываем объём).

    kind='wb_public_proxy' честно маркирует: это модель спроса из публичных полей, не факт продаж.
    Поля: feedbacks (кол-во отзывов ≈ накопленные покупки), rating, position (место в выдаче),
    stock (текущее предложение). Чем больше отзывов и выше позиция — тем сильнее сигнал.
    """
    feedbacks = int(prod.get("feedbacks") or prod.get("nmFeedbacks") or 0)
    rating = float(prod.get("reviewRating") or prod.get("rating") or 0)
    stock = _total_stock(prod)
    # Грубый скор силы сигнала (0..100): отзывы — главный наблюдаемый прокси спроса.
    strength = min(100, int(feedbacks ** 0.5 * 3) + (10 if position <= 20 else 0) + int(rating * 4))
    return {
        "kind": "wb_public_proxy",
        "source": "wildberries_public",
        "feedbacks": feedbacks,
        "rating": rating,
        "stock_now": stock,
        "position": position,
        "strength": strength,
        "note": "прокси спроса из публичных полей WB — не факт продаж; точный объём даёт платный адаптер",
        "captured_at": _now(),
    }


def _parse_products(payload):
    """Из ответа WB достать список товаров (форматы catalog/search немного разнятся)."""
    if not payload:
        return []
    data = payload.get("data") or {}
    return data.get("products") or payload.get("products") or []


def scan_category(category=None, query=None, city="msk", limit=40, page=1):
    """Один ограниченный скан категории ИЛИ поискового запроса WB → сырые товары (fail-soft []).

    category — id раздела WB (catalog endpoint). query — текстовый запрос (search endpoint).
    Хотя бы одно должно быть задано. Возвращает список dict-товаров WB как есть.
    """
    dest = CITY_DEST.get(city, -1)
    common = {
        "appType": 1, "curr": "rub", "dest": dest, "spp": 30,
        "sort": "popular", "page": int(page),
        "lang": "ru", "locale": "ru",
    }
    if query:
        q = dict(common, query=query, resultset="catalog")
        url = f"{SEARCH_HOST}/exactmatch/ru/common/v5/search?" + urllib.parse.urlencode(q)
    elif category:
        q = dict(common, cat=int(category))
        url = f"{CATALOG_HOST}/catalog/ext/v2/catalog?" + urllib.parse.urlencode(q)
    else:
        return []
    payload = _get(url)
    prods = _parse_products(payload)
    if query:
        # Троттлинг WB → HTTP-200 с fallback-рекомендациями; режем нерелевантное до среза по limit.
        prods = _filter_relevant(prods, query)
    return prods[: int(limit)]


def to_candidates(products, profit_target=600, min_profit=200):
    """Сырые товары WB → кандидат-связки в схеме PROSPECTOR (name/cost/url/sku/demand_signal).

    cost = цена закупки на WB (то, за сколько МЫ купим у поставщика). demand_signal — из прокси.
    Это ещё НЕ доказанная связка: PROSPECTOR.falsifiable_test решит достижимость, GAP — есть ли
    место на Озоне. Скаут только честно поставляет вход.
    """
    out = []
    for pos, prod in enumerate(products, start=1):
        nm = prod.get("id") or prod.get("nmId")
        if not nm:
            continue
        cost = _price_rub(prod)
        if cost <= 0:
            continue
        out.append({
            "name": (prod.get("name") or "").strip() or f"WB {nm}",
            "brand": (prod.get("brand") or "").strip(),
            "cost": cost,
            "sku": str(nm),
            "url": _wb_url(nm),
            "profit_target": profit_target,
            "min_profit": min_profit,
            "demand_signal": _demand_signal(prod, pos),
            "source_market": "wildberries",
        })
    return out


# ── VELOCITY: скорость = ИЗМЕНЕНИЕ между снимками (настоящая динамика, не мгновенный снимок) ──
def _snap_path(key):
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in str(key))
    return SNAP_DIR / f"snap_{safe}.json"


def snapshot(category=None, query=None, city="msk", limit=60):
    """Снять снимок {sku → feedbacks, stock, price, ts} для будущего расчёта velocity."""
    prods = scan_category(category, query, city, limit)
    key = query or f"cat{category}"
    snap = {"key": key, "city": city, "ts": _now(), "items": {}}
    for prod in prods:
        nm = prod.get("id") or prod.get("nmId")
        if not nm:
            continue
        snap["items"][str(nm)] = {
            "feedbacks": int(prod.get("feedbacks") or 0),
            "stock": _total_stock(prod),
            "price": _price_rub(prod),
        }
    p = _snap_path(key)
    p.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": str(p), "count": len(snap["items"]), "ts": snap["ts"]}


def velocity(category=None, query=None, city="msk", limit=60):
    """Дельта против прошлого снимка → настоящая скорость. fail-soft: нет снимка → status='need_snapshot'.

    Для каждого sku: Δfeedbacks (новые отзывы ≈ новые покупки), Δstock (ушло со склада).
    velocity_score = приоритет тем, у кого растут отзывы И тает остаток (товар реально «летит»).
    """
    key = query or f"cat{category}"
    p = _snap_path(key)
    if not p.exists():
        return {"status": "need_snapshot",
                "hint": f"сначала: python3 wb_scout_v1.py --snapshot "
                        f"{'--query ' + query if query else '--category ' + str(category)}"}
    try:
        prev = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "need_snapshot", "hint": "снимок повреждён — сними заново"}

    now_prods = scan_category(category, query, city, limit)
    prev_items = prev.get("items", {})
    rows = []
    for prod in now_prods:
        nm = str(prod.get("id") or prod.get("nmId") or "")
        old = prev_items.get(nm)
        if not old:
            continue
        d_fb = int(prod.get("feedbacks") or 0) - int(old.get("feedbacks") or 0)
        d_stock = _total_stock(prod) - int(old.get("stock") or 0)
        # летит ⟺ отзывы растут и/или остаток тает (продают быстрее, чем пополняют)
        score = max(0, d_fb) * 5 + max(0, -d_stock)
        rows.append({"sku": nm, "name": (prod.get("name") or "").strip(),
                     "d_feedbacks": d_fb, "d_stock": d_stock, "velocity_score": score,
                     "url": _wb_url(nm)})
    rows.sort(key=lambda r: r["velocity_score"], reverse=True)
    return {"status": "ok", "key": key, "since": prev.get("ts"), "now": _now(),
            "measured": len(rows), "rows": rows}


def scout(category=None, query=None, city="msk", limit=40, profit_target=600, min_profit=200):
    """Полный шаг SCOUT: скан → кандидаты. Один ограниченный проход (без демона)."""
    prods = scan_category(category, query, city, limit)
    cands = to_candidates(prods, profit_target, min_profit)
    return {"ts": _now(), "city": city, "category": category, "query": query,
            "scanned": len(prods), "candidates": cands}


def _main(argv=None):
    ap = argparse.ArgumentParser(description="WB SCOUT V1 — нос спроса ARBITER (публичный WB, stdlib)")
    ap.add_argument("--category", type=int, default=None, help="id раздела WB")
    ap.add_argument("--query", type=str, default=None, help="текстовый запрос WB (альтернатива категории)")
    ap.add_argument("--city", type=str, default="msk", choices=sorted(CITY_DEST), help="регион выдачи")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--profit-target", type=int, default=600)
    ap.add_argument("--min-profit", type=int, default=200)
    ap.add_argument("--snapshot", action="store_true", help="снять снимок для velocity")
    ap.add_argument("--velocity", action="store_true", help="дельта против прошлого снимка")
    ap.add_argument("--json", action="store_true", help="сырой JSON вместо человекочитаемого")
    args = ap.parse_args(argv)

    if not args.category and not args.query:
        ap.error("нужен --category ИЛИ --query")

    if args.snapshot:
        res = snapshot(args.category, args.query, args.city, max(args.limit, 60))
    elif args.velocity:
        res = velocity(args.category, args.query, args.city, max(args.limit, 60))
    else:
        res = scout(args.category, args.query, args.city, args.limit,
                    args.profit_target, args.min_profit)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    # человекочитаемо
    if args.snapshot:
        print(f"📸 снимок: {res['count']} товаров → {res['saved']}")
    elif args.velocity:
        if res.get("status") != "ok":
            print(f"⚠️  {res.get('status')}: {res.get('hint','')}")
            return 0
        print(f"🚀 VELOCITY «{res['key']}»  ({res['measured']} товаров, с {res['since']})")
        for r in res["rows"][:15]:
            print(f"   [{r['velocity_score']:>4}] Δотз {r['d_feedbacks']:+d}  Δост {r['d_stock']:+d}  "
                  f"{r['name'][:48]}")
    else:
        c = res["candidates"]
        print(f"🧭 SCOUT  город={res['city']}  "
              f"{'cat=' + str(res['category']) if res['category'] else 'q=' + str(res['query'])}  "
              f"→ отсканировано {res['scanned']}, кандидатов {len(c)}")
        for it in c[:15]:
            ds = it["demand_signal"]
            print(f"   ₽{it['cost']:>7.0f}  спрос[{ds['strength']:>3}] отз={ds['feedbacks']:<5} "
                  f"ост={ds['stock_now']:<5} {it['name'][:46]}")
        if not c:
            print("   (пусто — проверь --category/--query или сеть; скаут падает мягко)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

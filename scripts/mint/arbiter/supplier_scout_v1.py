#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SUPPLIER SCOUT V1 — поставщик-АГНОСТИЧНЫЙ нос спроса ARBITER (мощь: любой магазин).

То же, что wb_scout_v1, но НЕ прибито к WB. Берёт любого зарегистрированного поставщика
(--supplier wildberries|detmir|sportmaster) и гонит один и тот же конвейер:
    scan(adapter) → normalized товары → demand_signal → кандидаты в схеме PROSPECTOR.

Кандидат — ровно то, чего ждёт socc_mint_prospect_v1.falsifiable_test:
    {name, brand, cost, sku, url, profit_target, min_profit, demand_signal, source_market}

Закон: stdlib-only, ленивая сеть, fail-soft, без демона (один проход на вызов).
velocity() меряет ИЗМЕНЕНИЕ между снимками — настоящая скорость, не мгновенный снимок.

CLI:
  python3 supplier_scout_v1.py --list-suppliers
  python3 supplier_scout_v1.py --supplier wildberries --query дождевик --city msk --limit 10
  python3 supplier_scout_v1.py --supplier detmir --query коляска --limit 20
  python3 supplier_scout_v1.py --supplier wildberries --query дождевик --snapshot
  python3 supplier_scout_v1.py --supplier wildberries --query дождевик --velocity
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Импорт как пакет (относительный) при вызове из ядра; как файл — через sys.path (CLI).
try:
    from .suppliers import get_adapter, all_suppliers, build_demand_signal
except Exception:  # запуск как обычный скрипт: python3 supplier_scout_v1.py ...
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from suppliers import get_adapter, all_suppliers, build_demand_signal  # type: ignore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent  # SOCC/
SNAP_DIR = ROOT / "MEMORY_WAVE/reports/mint/arbiter/snapshots"


def _now():
    return datetime.now(timezone.utc).isoformat()


def to_candidates(products, supplier_key, profit_target=600, min_profit=200):
    """Нормализованные товары поставщика → кандидат-связки в схеме PROSPECTOR.

    Это ещё НЕ доказанная связка: PROSPECTOR.falsifiable_test решит достижимость, GAP — есть ли
    место на Озоне. Скаут только честно поставляет вход (реальные cost/url/sku/demand_signal).
    """
    out = []
    for pos, prod in enumerate(products, start=1):
        cost = float(prod.get("cost") or 0)
        if cost <= 0 or not prod.get("sku"):
            continue
        out.append({
            "name": prod["name"],
            "brand": prod.get("brand", ""),
            "cost": cost,
            "sku": prod["sku"],
            "url": prod.get("url", ""),
            "profit_target": profit_target,
            "min_profit": min_profit,
            "demand_signal": build_demand_signal(prod, pos, supplier_key),
            "source_market": supplier_key,
        })
    return out


def scout(supplier="wildberries", query=None, category=None, city="msk",
          limit=40, profit_target=600, min_profit=200):
    """Полный шаг SCOUT для указанного поставщика. fail-soft: нет адаптера → пустой результат."""
    ad = get_adapter(supplier)
    if ad is None:
        return {"ts": _now(), "supplier": supplier, "error": "unknown_supplier",
                "known": sorted(all_suppliers()), "scanned": 0, "candidates": []}
    prods = ad.scan(query=query, category=category, city=city, limit=limit)
    cands = to_candidates(prods, supplier, profit_target, min_profit)
    return {"ts": _now(), "supplier": supplier, "secret": ad.secret, "proven": ad.proven,
            "city": city, "category": category, "query": query,
            "scanned": len(prods), "candidates": cands}


# ── VELOCITY: скорость = ИЗМЕНЕНИЕ между снимками ──
def _snap_path(supplier, key):
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in f"{supplier}_{key}")
    return SNAP_DIR / f"snap_{safe}.json"


def snapshot(supplier="wildberries", query=None, category=None, city="msk", limit=60):
    """Снять снимок {sku → feedbacks, stock, price, ts} для будущего расчёта velocity."""
    ad = get_adapter(supplier)
    if ad is None:
        return {"error": "unknown_supplier", "known": sorted(all_suppliers())}
    prods = ad.scan(query=query, category=category, city=city, limit=limit)
    key = query or f"cat{category}"
    snap = {"supplier": supplier, "key": key, "city": city, "ts": _now(), "items": {}}
    for prod in prods:
        snap["items"][str(prod["sku"])] = {
            "feedbacks": int(prod.get("feedbacks") or 0),
            "stock": int(prod.get("stock") or 0),
            "price": float(prod.get("cost") or 0),
        }
    p = _snap_path(supplier, key)
    p.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": str(p), "count": len(snap["items"]), "ts": snap["ts"]}


def velocity(supplier="wildberries", query=None, category=None, city="msk", limit=60):
    """Дельта против прошлого снимка → настоящая скорость. fail-soft: нет снимка → need_snapshot."""
    ad = get_adapter(supplier)
    if ad is None:
        return {"status": "unknown_supplier", "known": sorted(all_suppliers())}
    key = query or f"cat{category}"
    p = _snap_path(supplier, key)
    if not p.exists():
        arg = f"--query {query}" if query else f"--category {category}"
        return {"status": "need_snapshot",
                "hint": f"сначала: python3 supplier_scout_v1.py --supplier {supplier} {arg} --snapshot"}
    try:
        prev = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "need_snapshot", "hint": "снимок повреждён — сними заново"}

    now_prods = ad.scan(query=query, category=category, city=city, limit=limit)
    prev_items = prev.get("items", {})
    rows = []
    for prod in now_prods:
        nm = str(prod["sku"])
        old = prev_items.get(nm)
        if not old:
            continue
        d_fb = int(prod.get("feedbacks") or 0) - int(old.get("feedbacks") or 0)
        d_stock = int(prod.get("stock") or 0) - int(old.get("stock") or 0)
        score = max(0, d_fb) * 5 + max(0, -d_stock)
        rows.append({"sku": nm, "name": prod["name"], "d_feedbacks": d_fb,
                     "d_stock": d_stock, "velocity_score": score, "url": prod.get("url", "")})
    rows.sort(key=lambda r: r["velocity_score"], reverse=True)
    return {"status": "ok", "supplier": supplier, "key": key, "since": prev.get("ts"),
            "now": _now(), "measured": len(rows), "rows": rows}


def _main(argv=None):
    ap = argparse.ArgumentParser(description="SUPPLIER SCOUT V1 — агностичный нос спроса ARBITER")
    ap.add_argument("--supplier", type=str, default="wildberries",
                    help="ключ поставщика (см. --list-suppliers)")
    ap.add_argument("--list-suppliers", action="store_true", help="показать зарегистрированных поставщиков")
    ap.add_argument("--category", type=str, default=None, help="id/alias раздела поставщика")
    ap.add_argument("--query", type=str, default=None, help="текстовый запрос")
    ap.add_argument("--city", type=str, default="msk", help="регион выдачи (msk/spb/…)")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--profit-target", type=int, default=600)
    ap.add_argument("--min-profit", type=int, default=200)
    ap.add_argument("--snapshot", action="store_true", help="снять снимок для velocity")
    ap.add_argument("--velocity", action="store_true", help="дельта против прошлого снимка")
    ap.add_argument("--json", action="store_true", help="сырой JSON вместо человекочитаемого")
    args = ap.parse_args(argv)

    if args.list_suppliers:
        sup = all_suppliers()
        if args.json:
            print(json.dumps({k: a.info() for k, a in sup.items()}, ensure_ascii=False, indent=2))
            return 0
        print("🏬 поставщики ARBITER (магазин = новый файл, ядро не трогаем):")
        for k, a in sup.items():
            tag = "🔒секрет" if a.secret else "открытый"
            pr = "✅ живой" if a.proven else "⏳ сверить сеть"
            print(f"   {k:<12} {a.title:<16} {tag:<9} {pr}  города={','.join(a.cities())}")
        return 0

    if not args.category and not args.query:
        ap.error("нужен --category ИЛИ --query (или --list-suppliers)")

    if args.snapshot:
        res = snapshot(args.supplier, args.query, args.category, args.city, max(args.limit, 60))
    elif args.velocity:
        res = velocity(args.supplier, args.query, args.category, args.city, max(args.limit, 60))
    else:
        res = scout(args.supplier, args.query, args.category, args.city, args.limit,
                    args.profit_target, args.min_profit)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    if args.snapshot:
        if res.get("error"):
            print(f"⚠️  {res['error']}: {res.get('known')}")
            return 0
        print(f"📸 снимок: {res['count']} товаров → {res['saved']}")
    elif args.velocity:
        if res.get("status") != "ok":
            print(f"⚠️  {res.get('status')}: {res.get('hint', res.get('known',''))}")
            return 0
        print(f"🚀 VELOCITY [{res['supplier']}] «{res['key']}»  ({res['measured']} тов., с {res['since']})")
        for r in res["rows"][:15]:
            print(f"   [{r['velocity_score']:>4}] Δотз {r['d_feedbacks']:+d}  Δост {r['d_stock']:+d}  "
                  f"{r['name'][:48]}")
    else:
        if res.get("error"):
            print(f"⚠️  {res['error']}: известные = {res.get('known')}")
            return 0
        c = res["candidates"]
        lock = "🔒" if res.get("secret") else ""
        prov = "✅" if res.get("proven") else "⏳"
        print(f"🧭 SCOUT [{res['supplier']}{lock}{prov}]  город={res['city']}  "
              f"{'q=' + str(res['query']) if res['query'] else 'cat=' + str(res['category'])}  "
              f"→ отсканировано {res['scanned']}, кандидатов {len(c)}")
        for it in c[:15]:
            ds = it["demand_signal"]
            print(f"   ₽{it['cost']:>7.0f}  спрос[{ds['strength']:>3}] отз={ds['feedbacks']:<5} "
                  f"ост={ds['stock_now']:<5} {it['name'][:46]}")
        if not c:
            print("   (пусто — проверь --supplier/--query или сеть; скаут падает мягко)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

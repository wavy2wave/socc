#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПОРТФЕЛЬ (ymarket_portfolio_v1) — орган «управления пониманием»: read-only матрица того, что залито на ЯМ.

ЗАЧЕМ. Библиотека (ymarket_goods_library.json, схема ymarket.goods.library.v1) копит каждую карточку,
остатки и вердикты СВЕРКИ — но «что организм РЕАЛЬНО поставил на витрину» одним взглядом из неё не
читается. ПОРТФЕЛЬ — сводная read-only матрица понимания: объём, деньги, качество, остатки, история.
Опция --live добавляет СТАТУС НА РЫНКЕ живьём (0₽ GET): PUBLISHED/available + n_pics с витрины кабинета,
join по offerId с библиотекой. Пульс для ЦЕНОВИКА, СТРАТЕГА, планёрки и совета.

ЧТО СЧИТАЕМ (поля карточки библиотеки: name, offerId, article, barcode, cost, price, markup,
stock_count, n_photos, vendor, store_slug, category_slug, donor_pid, cycle_hash, first_seen,
last_verified, description_len, spec_n, dims):
  объём   — карточек всего; по store_slug; по category_slug; по vendor.
  деньги  — Σ cost (вложено), Σ price (потенциальная выручка при продаже всего),
            min/max/средняя цена, топ-10 самых дорогих карточек.
  качество— с фото (n_photos≥1) / без; средн. description_len и spec_n; dims есть/нет;
            полнота по критериям (см. _CRITERIA).
  остатки — Σ stock_count по магазину и по складу (последнее stock-событие на offerId).
  история — карточек на залив (cycle_hash); по датам first_seen.
  статус  — (--live) с витрины кабинета: PUBLISHED?, available?, n_pics живьём.

ПИШЕТ локальный артефакт: MEMORY_WAVE/reports/mint/arbiter/ymarket_portfolio_matrix_<дата>.md + .json
(атомарно, tmp+os.replace). --json → JSON в stdout для пайпа. --no-artifact → только stdout.

ЗАКОНЫ (механические):
  PP1 read-only на маркет: максимум 0₽ GET; НИ ОДНОГО write-вызова к ЯМ — RUBICON цел по построению.
  PP2 наружу — только локальный артефакт (md+json) в REPORTS.
  PP3 fail-soft: битая/пустая библиотека → нули и «—», без падения; --live без ключей → честно None.
  PP4 не выдумываем: отсутствующее поле не заполняем (None → «—»); карточка без cost/price в суммы НЕ идёт.
  PP5 числа и только числа: матрица-факт, без прогнозов/мнений.
"""
from __future__ import annotations

import os
import re
import json
import argparse
import tempfile
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
SCHEMA = "ymarket.goods.library.v1"


def _reports_root():
    """Якорь канона: корень SOCC по маркеру MEMORY_WAVE (как в библиотеке — сирота не затеняет)."""
    here = HERE
    for anc in (here, *here.parents):
        if (anc / ".git").is_dir() and (anc / "MEMORY_WAVE").is_dir():
            return anc
    for anc in (here, *here.parents):
        if (anc / "MEMORY_WAVE").is_dir():
            return anc
    return here.parent.parent.parent            # фолбэк: arbiter -> mint -> scripts -> SOCC


REPORTS = _reports_root() / "MEMORY_WAVE/reports/mint/arbiter"


def library_path():
    """Путь к стору библиотеки. env YM_LIBRARY_PATH перекрывает (песочница/тесты)."""
    p = os.environ.get("YM_LIBRARY_PATH")
    return Path(p) if p else (REPORTS / "ymarket_goods_library.json")


def _load_library_doc():
    """Загрузить библиотеку fail-soft (PP3): канонный модуль → прямой чтение JSON → бланк."""
    try:
        import ymarket_library_v1 as lib
        return lib.load()
    except Exception:
        pass
    try:
        doc = json.loads(library_path().read_text(encoding="utf-8"))
        if isinstance(doc, dict) and doc.get("schema") == SCHEMA and isinstance(doc.get("goods"), dict):
            return doc
    except Exception:
        pass
    return {"schema": SCHEMA, "goods": {}}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def rows(doc):
    """Плоские строки матрицы из сторовых записей (примитивы, всё None-safe). Пусто → []."""
    out = []
    for oid, rec in (doc.get("goods") or {}).items():
        rec = rec or {}
        r = {
            "offer_id": str(rec.get("offerId") or oid),
            "name": rec.get("name") or "",
            "article": rec.get("article"),
            "barcode": rec.get("barcode"),
            "vendor": rec.get("vendor"),
            "store_slug": rec.get("store_slug"),
            "category_slug": rec.get("category_slug"),
            "donor_pid": rec.get("donor_pid"),
            "cycle_hash": rec.get("cycle_hash"),
            "first_seen": rec.get("first_seen"),
            "cost": _num(rec.get("cost")),
            "price": _num(rec.get("price")),
            "markup": _num(rec.get("markup")),
            "stock_count": _int(rec.get("stock_count")),
            "n_photos": _int(rec.get("n_photos")),
            "description_len": _int(rec.get("description_len")),
            "spec_n": _int(rec.get("spec_n")),
            "dims": rec.get("dims") if isinstance(rec.get("dims"), dict) else None,
            "last_verified": rec.get("last_verified"),
        }
        # склад: последнее stock-событие (warehouse_id + count) — история, а не выдумка (PP4)
        wh, cnt = None, None
        for ev in (rec.get("events") or []):
            if isinstance(ev, dict) and ev.get("kind") == "stock":
                wh = ev.get("warehouse_id")
                cnt = _int(ev.get("count"))
        r["warehouse_id"] = wh
        r["stock_event_count"] = cnt
        out.append(r)
    return out


# ── срезы ─────────────────────────────────────────────────────────────────────

def volume(rows):
    """Объём: всего карточек; по магазинам; по категориям; по вендорам."""
    total = len(rows)
    return {
        "total": total,
        "by_store": _counter(rows, "store_slug"),
        "by_category": _counter(rows, "category_slug"),
        "by_vendor": _counter(rows, "vendor"),
    }


def _counter(rows, key):
    c = Counter(r[key] for r in rows if r.get(key))
    return {k: v for k, v in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))}


def money(rows):
    """Деньги: вложено (Σ cost), потенциал (Σ price), min/max/средняя цена, топ-10 дорогих."""
    costs = [r["cost"] for r in rows if r["cost"] is not None]
    prices = [r["price"] for r in rows if r["price"] is not None]
    top = sorted((r for r in rows if r["price"] is not None),
                 key=lambda r: r["price"], reverse=True)[:10]
    return {
        "sum_cost": round(sum(costs), 2) if costs else 0,
        "sum_price": round(sum(prices), 2) if prices else 0,
        "price_count": len(prices),
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "price_avg": round(sum(prices) / len(prices), 2) if prices else None,
        "top10": [{"offer_id": r["offer_id"], "name": r["name"], "price": r["price"],
                   "cost": r["cost"], "store_slug": r["store_slug"], "markup": r["markup"]}
                  for r in top],
    }


# Критерии полноты карточки: имя, идентификаторы, цена/закупка, остаток, фото,
# описание, характеристики, габариты, СВЕРКА. Один язык с гейтами органа.
_CRITERIA = (
    ("name", lambda r: bool((r["name"] or "").strip())),
    ("article", lambda r: bool(r["article"])),
    ("barcode", lambda r: bool(r["barcode"]) and re.fullmatch(r"\d{8,14}", str(r["barcode"])) is not None),
    ("vendor", lambda r: bool(r["vendor"])),
    ("price", lambda r: r["price"] is not None and r["price"] > 0),
    ("cost", lambda r: r["cost"] is not None and r["cost"] > 0),
    ("stock", lambda r: r["stock_count"] is not None),
    ("photos", lambda r: (r["n_photos"] or 0) >= 1),
    ("description", lambda r: (r["description_len"] or 0) >= 50),
    ("spec", lambda r: (r["spec_n"] or 0) >= 1),
    ("dims", lambda r: bool(r["dims"] and r["dims"].get("length") and r["dims"].get("width"))),
    ("verified", lambda r: (r["last_verified"] or {}).get("verdict") == "PASS"),
)


def quality(rows):
    """Качество: фото есть/нет, средн. description_len/spec_n, dims, полнота по критериям."""
    with_photo = sum(1 for r in rows if (r["n_photos"] or 0) >= 1)
    desc_lens = [r["description_len"] for r in rows if r["description_len"] is not None]
    spec_ns = [r["spec_n"] for r in rows if r["spec_n"] is not None]
    crit = []
    for cname, fn in _CRITERIA:
        passed = sum(1 for r in rows if fn(r))
        crit.append({"name": cname, "passed": passed, "total": len(rows),
                     "share": round(passed / len(rows), 3) if rows else None})
    complete = [sum(1 for _n, fn in _CRITERIA if fn(r)) for r in rows]
    return {
        "with_photo": with_photo,
        "without_photo": sum(1 for r in rows if (r["n_photos"] or 0) == 0),
        "photo_share": round(with_photo / len(rows), 3) if rows else None,
        "avg_description_len": round(sum(desc_lens) / len(desc_lens), 1) if desc_lens else None,
        "avg_spec_n": round(sum(spec_ns) / len(spec_ns), 2) if spec_ns else None,
        "with_dims": sum(1 for r in rows if r["dims"]),
        "without_dims": sum(1 for r in rows if not r["dims"]),
        "criteria": crit,
        "avg_completeness": round(sum(complete) / len(rows), 2) if rows else None,
        "max_completeness": len(_CRITERIA),
        "full_complete": sum(1 for c in complete if c == len(_CRITERIA)),
    }


def stock(rows):
    """Остатки: Σ stock_count по магазинам и по складам (последнее stock-событие на offerId)."""
    by_store = Counter()
    for r in rows:
        if r["store_slug"] and r["stock_count"] is not None:
            by_store[r["store_slug"]] += r["stock_count"]
    by_warehouse = Counter()
    for r in rows:
        cnt = r["stock_event_count"] if r["stock_event_count"] is not None else r["stock_count"]
        if r["warehouse_id"] is not None and cnt is not None:
            by_warehouse[str(r["warehouse_id"])] += cnt
    return {
        "total_stock": sum(r["stock_count"] for r in rows if r["stock_count"] is not None),
        "by_store": {k: v for k, v in sorted(by_store.items(), key=lambda kv: (-kv[1], kv[0]))},
        "by_warehouse": {k: v for k, v in sorted(by_warehouse.items(), key=lambda kv: (-kv[1], kv[0]))},
    }


def history(rows):
    """История: карточек на залив (cycle_hash) и по датам first_seen."""
    by_cycle = _counter(rows, "cycle_hash")
    by_date = Counter((r["first_seen"] or "")[:10] for r in rows if r["first_seen"])
    return {
        "by_cycle": by_cycle,
        "by_date": {k: v for k, v in sorted(by_date.items())},
    }


# ── статус на рынке: живая витрина (0₽ GET, PP1) ──────────────────────────────

def _offer_status(o):
    return o.get("status") or o.get("campaignStatus") or o.get("placementStatus")


def _offer_n_pics(o):
    """Фото живьём: список картинок считаем по длине; иначе число-поле. Не знаем → None (PP4)."""
    for key in ("pictures", "pics", "photos"):
        v = o.get(key)
        if isinstance(v, list):
            return len(v)
    for key in ("n_pics", "picturesCount", "photoCount"):
        v = o.get(key)
        try:
            if v is not None:
                return int(v)
        except (TypeError, ValueError):
            pass
    return None


def _live_summary(live_map):
    """Сводка join-карты витрины: PUBLISHED/available/n_pics. Пусто → нули (не фейк)."""
    if not live_map:
        return {"matched": 0, "published": 0, "not_published": 0, "unknown": 0,
                "available": 0, "unavailable": 0, "with_pics": 0, "avg_n_pics": None}
    st = Counter((v.get("status") or "UNKNOWN") for v in live_map.values())
    np = [v["n_pics"] for v in live_map.values() if v.get("n_pics") is not None]
    return {
        "matched": len(live_map),
        "published": st.get("PUBLISHED", 0),
        "not_published": sum(n for k, n in st.items() if k != "PUBLISHED"),
        "unknown": st.get("UNKNOWN", 0),
        "available": sum(1 for v in live_map.values() if v.get("available") is True),
        "unavailable": sum(1 for v in live_map.values() if v.get("available") is False),
        "with_pics": sum(1 for v in live_map.values() if (v.get("n_pics") or 0) >= 1),
        "avg_n_pics": round(sum(np) / len(np), 2) if np else None,
    }


def read_live(rows, campaign_id=None, hands=None, limit=200):
    """ЖИВОЙ READ витрины кабинета (0₽ GET): campaign_offers по offer_ids библиотеки → join-карта.

    Fail-soft на каждом шаге (PP3): нет ключей / сеть упала / campaignId неизвестен → {ok:False,
    error}, НЕ падаем. Ничего не пишет (PP1). Возвращает {ok, error?, campaign_id?, live_map,
    summary}. live_map: {offer_id: {status, available, n_pics}}.
    """
    if hands is None:
        try:
            import ymarket_hands_v1 as hands
        except Exception as e:
            return {"ok": False, "error": f"нет ymarket_hands_v1: {e}", "live_map": {}, "summary": {}}
    if campaign_id is None:
        try:
            campaign_id = hands.campaign_id_env()
        except Exception:
            campaign_id = None
        if not campaign_id:
            try:
                _b, campaign_id, _src = hands.resolve_ids()
            except Exception:
                campaign_id = None
    if not campaign_id:
        return {"ok": False, "error": "campaignId неизвестен (нет YANDEX_CAMPAIGN_ID / кабинет пуст)",
                "live_map": {}, "summary": {}}
    ids = [r["offer_id"] for r in rows]
    try:
        offers = hands.campaign_offers(campaign_id, offer_ids=ids, limit=limit)
    except Exception as e:
        return {"ok": False, "error": f"чтение витрины не удалось: {type(e).__name__}: {e}",
                "live_map": {}, "summary": {}}
    if not isinstance(offers, list):
        offers = []
    live_map = {}
    for o in offers:
        if not isinstance(o, dict):
            continue
        oid = o.get("offerId") or o.get("offer_id")
        if not oid:
            continue
        live_map[str(oid)] = {"status": _offer_status(o), "available": o.get("available"),
                              "n_pics": _offer_n_pics(o)}
    return {"ok": True, "campaign_id": str(campaign_id), "live_map": live_map,
            "summary": _live_summary(live_map)}


# ── сборка матрицы ────────────────────────────────────────────────────────────

def build_matrix(doc=None, live=False, campaign_id=None):
    """Полная матрица портфеля: все срезы + (опция) живой статус витрины и join в rows."""
    doc = doc if doc is not None else _load_library_doc()
    rs = rows(doc)
    out = {
        "schema": "ymarket.portfolio.matrix.v1",
        "source": {"library": str(library_path()), "library_schema": SCHEMA,
                   "cards": len(rs),
                   "library_updated_at": doc.get("updated_at") or doc.get("created_at")},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "volume": volume(rs),
        "money": money(rs),
        "quality": quality(rs),
        "stock": stock(rs),
        "history": history(rs),
    }
    if live:
        live_res = read_live(rs, campaign_id=campaign_id)
        out["live"] = live_res
        lm = live_res.get("live_map") or {}
        for r in rs:
            v = lm.get(r["offer_id"])
            r["live_status"] = (v or {}).get("status")
            r["live_available"] = (v or {}).get("available")
            r["live_n_pics"] = (v or {}).get("n_pics")
    out["rows"] = rs
    return out


# ── рендер md-артефакта ──────────────────────────────────────────────────────

def _fmt_rub(v):
    if v is None:
        return "—"
    return f"{v:,.0f}".replace(",", " ")


def _fmt_num(v, digits=0):
    if v is None:
        return "—"
    return f"{v:,.{digits}f}".replace(",", " ")


def _md_counter(lines, title, counter):
    if not counter:
        lines.append(f"{title}: пусто")
        return
    lines.append(f"### {title}")
    lines.append("| значение | карточек |")
    lines.append("|---|---|")
    for k, n in counter.items():
        lines.append(f"| {k} | {n} |")


def render_md(mx):
    """Матрица → markdown (таблицы). Чистая: ничего не читает/не пишет."""
    L = []
    L.append(f"# ПОРТФЕЛЬ · матрица понимания · {mx['generated_at'][:10]}")
    L.append("")
    src = mx["source"]
    L.append(f"источник: `{src['library']}` · схема `{src['library_schema']}` · "
             f"карточек **{src['cards']}** · библиотека обновлена `{src['library_updated_at']}`")
    L.append("read-only (0₽ GET максимум) — наружу НИЧЕГО не писалось.")
    L.append("")

    v = mx["volume"]
    L.append("## Объём")
    L.append(f"карточек всего: **{v['total']}**")
    _md_counter(L, "по магазинам", v["by_store"])
    _md_counter(L, "по категориям", v["by_category"])
    _md_counter(L, "по вендорам", v["by_vendor"])
    L.append("")

    m = mx["money"]
    L.append("## Деньги")
    L.append(f"- вложено (Σ cost): **{_fmt_rub(m['sum_cost'])} ₽**")
    L.append(f"- потенциал при продаже всего (Σ price): **{_fmt_rub(m['sum_price'])} ₽**")
    L.append(f"- цена: min **{_fmt_rub(m['price_min'])} ₽** · max **{_fmt_rub(m['price_max'])} ₽** · "
             f"средняя **{_fmt_rub(m['price_avg'])} ₽** (по {m['price_count']} карточкам с ценой)")
    L.append("")
    L.append("### Топ-10 самых дорогих карточек")
    L.append("| # | offerId | название | цена, ₽ | закуп, ₽ | магазин |")
    L.append("|---|---|---|---|---|---|")
    for i, t in enumerate(m["top10"], 1):
        name = (t["name"] or "")[:44].replace("|", "\\|")
        L.append(f"| {i} | {t['offer_id']} | {name} | {_fmt_rub(t['price'])} | "
                 f"{_fmt_rub(t['cost'])} | {t['store_slug'] or '—'} |")
    L.append("")

    q = mx["quality"]
    L.append("## Качество")
    L.append(f"- с фото (n_photos≥1): **{q['with_photo']}** · без фото: **{q['without_photo']}**")
    L.append(f"- средн. длина описания: **{_fmt_num(q['avg_description_len'], 1)}** · "
             f"средн. число характеристик (spec): **{_fmt_num(q['avg_spec_n'], 1)}**")
    L.append(f"- с габаритами (dims): **{q['with_dims']}** · без: **{q['without_dims']}**")
    L.append(f"- полнота: в среднем **{_fmt_num(q['avg_completeness'], 1)}** из **{q['max_completeness']}** "
             f"критериев · полностью укомплектовано **{q['full_complete']}**")
    L.append("")
    L.append("### Полнота по критериям")
    L.append("| критерий | прошли | доля |")
    L.append("|---|---|---|")
    for c in q["criteria"]:
        share = f"{c['share'] * 100:.0f}%" if c["share"] is not None else "—"
        L.append(f"| {c['name']} | {c['passed']}/{c['total']} | {share} |")
    L.append("")

    s = mx["stock"]
    L.append("## Остатки")
    L.append(f"- Σ stock_count: **{_fmt_num(s['total_stock'], 0)}** единиц")
    _md_counter(L, "по магазинам", s["by_store"])
    _md_counter(L, "по складам", s["by_warehouse"])
    L.append("")

    h = mx["history"]
    L.append("## История")
    _md_counter(L, "карточек по заливам (cycle_hash)", h["by_cycle"])
    _md_counter(L, "по датам first_seen", h["by_date"])
    L.append("")

    lv = mx.get("live")
    if lv:
        L.append("## Статус на рынке (живая витрина, 0₽ GET)")
        if not lv.get("ok"):
            L.append(f"⚠️ {lv.get('error')}")
        else:
            sm = lv["summary"]
            L.append(f"- сопоставлено с витриной (campaign {lv.get('campaign_id')}): **{sm['matched']}**")
            L.append(f"- PUBLISHED: **{sm['published']}** · не-PUBLISHED: **{sm['not_published']}** · "
                     f"нет статуса: **{sm['unknown']}**")
            L.append(f"- available=true: **{sm['available']}** · false: **{sm['unavailable']}**")
            L.append(f"- с фото на витрине: **{sm['with_pics']}** · средн. n_pics: "
                     f"**{_fmt_num(sm['avg_n_pics'], 1)}**")
            L.append("")
            L.append("### join библиотека ↔ витрина")
            L.append("| offerId | статус | available | n_pics живьём | n_photos (библ.) | цена, ₽ | магазин |")
            L.append("|---|---|---|---|---|---|---|")
            for r in mx["rows"]:
                avail = "да" if r["live_available"] is True else ("нет" if r["live_available"] is False else "—")
                np_ = r["live_n_pics"] if r["live_n_pics"] is not None else "—"
                npb = r["n_photos"] if r["n_photos"] is not None else "—"
                L.append(f"| {r['offer_id']} | {r['live_status'] or '—'} | {avail} | {np_} | {npb} | "
                         f"{_fmt_rub(r['price'])} | {r['store_slug'] or '—'} |")
        L.append("")

    L.append("## RUBICON")
    L.append("Цел: read-only, 0₽ (GET максимум), наружу — только локальный артефакт.")
    L.append("")
    return "\n".join(L)


# ── запись артефакта (PP2, атомарно) ─────────────────────────────────────────

def artifact_paths(date_str=None):
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    return (REPORTS / f"ymarket_portfolio_matrix_{date_str}.md",
            REPORTS / f"ymarket_portfolio_matrix_{date_str}.json")


def write_artifacts(mx, md_text, json_text, date_str=None):
    """md+json в REPORTS атомарно (tmp + os.replace, без полу-файла). Возвращает (md_path, json_path)."""
    md_path, json_path = artifact_paths(date_str)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    for p, data in ((md_path, md_text), (json_path, json_text)):
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".portfolio_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    return md_path, json_path


# ── сухая демонстрация (0₽, файлы не трогает) ────────────────────────────────

def _demo_doc():
    ts = datetime.now(timezone.utc).isoformat()
    doc = {"schema": SCHEMA, "created_at": ts, "updated_at": ts, "goods": {}}

    def card(oid, **kw):
        base = {"offerId": oid, "first_seen": ts, "events": [],
                "name": "Плёнка пузырьковая 100×0,75 м", "vendor": "Без бренда",
                "barcode": "2276329846713", "article": "9602037", "cost": 600.0,
                "price": 4800, "markup": 8.0, "stock_count": 100, "n_photos": 1,
                "store_slug": "atlas-express-film", "category_slug": "vozdushno-puzyrkovaya-plenka",
                "cycle_hash": "91781dfe33", "description_len": 1200, "spec_n": 8,
                "dims": {"length": 50, "width": 35, "height": 50, "weight": 1.4},
                "last_verified": {"verdict": "PASS", "note": "СВЕРКА: витрина PUBLISHED + остатки FIT"}}
        base.update(kw)
        doc["goods"][oid] = base
        return doc

    card("ARB-1")
    card("ARB-2", price=520, cost=65.0, n_photos=0, dims=None, spec_n=0, description_len=40)
    card("ARB-3", vendor="Другой бренд", cycle_hash="abcd1234", n_photos=4)
    return doc


def _main(argv=None):
    ap = argparse.ArgumentParser(description="ПОРТФЕЛЬ — read-only матрица того, что залито на ЯМ (0₽)")
    ap.add_argument("--live", action="store_true",
                    help="добавить СТАТУС НА РЫНКЕ: живой READ витрины кабинета (0₽ GET)")
    ap.add_argument("--campaign-id", default=None, help="campaignId магазина (по умолч. YANDEX_CAMPAIGN_ID)")
    ap.add_argument("--json", action="store_true", help="JSON в stdout для пайпа (артефакты всё равно пишутся)")
    ap.add_argument("--no-artifact", action="store_true", help="не писать md/json артефакты (только stdout)")
    ap.add_argument("--demo", action="store_true", help="сухая демонстрация на выдуманных карточках (0₽)")
    args = ap.parse_args(argv)

    doc = _demo_doc() if args.demo else None
    mx = build_matrix(doc=doc, live=args.live, campaign_id=args.campaign_id)
    md_text = render_md(mx)
    json_text = json.dumps(mx, ensure_ascii=False, indent=2, default=str)

    written = None
    if not args.no_artifact and not args.demo:
        written = write_artifacts(mx, md_text, json_text)

    if args.json:
        print(json_text)
    else:
        print(md_text)
    if written:
        print(f"артефакты:\n  {written[0]}\n  {written[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

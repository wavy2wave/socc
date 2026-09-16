#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · КОРОБКИ · ЧЕСТНАЯ СШИВКА С ДОНОРОМ cargo.shop (артикул + ссылка).

Оператор: «донор — это сайт cargo.shop, где при заказе мы купим (система под капотом).
Сшиваем матрицу БЕЗ ОБМАНА». Правило: колонка «Донор» несёт РЕАЛЬНЫЙ товар cargo.shop
(pid + ссылка https://shop.cargo-avto.ru/catalog/<pid>/), который система купит на заказ.

Установлено (read-only, факты):
  • master-каталог (96XXXXX-N, 205 товаров «наша линейка») коробок НЕ содержит (0).
  • Живой каталог магазина = shop.cargo-avto.ru (Москва, base из summary.json 2026-09-08;
    НЕ sp=СПб). Коробки = категории boxes/* в pid_cats: 413 pid, из них 210 «В наличии»,
    203 «Под заказ», у всех есть цена (cats_cache) и у 393 размер в названии (мм).
  • Габариты ОВХ/пачки НЕ использовать как ключ — это размер СЛОЖЕННОЙ пачки, не короба.
    Честный ключ = размер ОДНОГО КОРОБА, распарсенный из ИМЕНИ товара (см→мм×10).

Честность для имён БЕЗ единицы (напр. «60х40х40», «600х400х400»):
  одиночная трактовка (мм как есть ИЛИ см×10) сама по себе НЕ доказуема. Единственный
  честный арбитр — реальный донор:
    • ровно одна трактовка даёт донора-совпадение  → берём её, помечаем «см/мм не указаны,
      по совпадению донора» (факт покупки реальный).
    • ОБЕ трактовки дают донора (40х40х20: и 40-мм короб, и 40-см короб существуют)
      → НЕ угадываем: статус «размер без единицы — неоднозначно» (честно, без выдумки).
    • ни одна → «донор по размеру не найден».
  Точное совпадение размеров — только по коробам одного размера (sorted-тройка, допуск ±5 мм);
  «близко» (≤30 мм на ось) — отдельная честная пометка, НЕ выдаётся за точное.

Статус донора («В наличии»/«Под заказ») всегда в строке — фулфилмент-риск виден оператору.

Read-only: ни одного записи в Ozon, только файлы. Артефакты:
  runtime/ozon_boxes/korobki_DONOR_STITCH_<DATE>.{json,md}
  runtime/ozon_boxes/korobki_simple_matrix_<DATE>.csv   (простая таблица оператора)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime" / "ozon_boxes"
DATE = "2026-09-10"

FROZEN = RUNTIME / "korobki_CARD_LIVE_2026-09-09.items.json"
DONOR_DIR = Path("/Users/wavysexy/parsers/parsed_data/CARGO_MATRIX_LIVE_2026-09-08")
DONOR_AVA = DONOR_DIR / "availability.json"
DONOR_CATS = DONOR_DIR / "cats_cache.json"
DONOR_MD = DONOR_DIR / "matrix_data.json"
BASE = "https://shop.cargo-avto.ru"

OUT_JSON = RUNTIME / f"korobki_DONOR_STITCH_{DATE}.json"
OUT_MD = RUNTIME / f"korobki_DONOR_STITCH_{DATE}.md"
OUT_CSV = RUNTIME / f"korobki_simple_matrix_{DATE}.csv"

# тип-контекст нашего имени → предпочитаемые подкатегории/ключи донора
TYPE_HINT = [
    ("самосбор", ("samosbornie", "самосбор", "е-2", "е-22", "е-2")) ,
    ("переезд", ("chetyrehklapannye", "archivnie", "переезд", "4-х", "4х")),
    ("почтов", ("korobki-dlya-butilok",)),  # перекрытие редкое — оставляем пустым смысл ниже
]
TYPE_SCORE = {
    "samosbornie": ["самосбор"],
    "chetyrehklapannye": ["переезд", "архив", "упаковоч", "ручк", "откидн"],
    "archivnie": ["переезд", "архив", "хранен"],
    "garderobnie": ["гардероб", "хранен"],
    "kartonnie-lotki": ["лоток"],
    "korobki-dlya-butilok": ["бутыл"],
    "korobki-dlya-kartin": ["картин"],
    "korobki-dlya-knig-i-posudi": ["книг", "посуд"],
}
OUR_TYPE_KEYS = ["переезд", "архив", "почтов", "самосбор", "откидн", "ручк", "бутыл",
                 "гардероб", "лоток", "хранен", "подароч", "крафт", "складн"]


# ── размер из имени (см → мм; мм как есть; без единицы → кандидаты) ────────────

_DIM_RE = re.compile(
    r"(\d{2,4})(?:[.,](\d))?\s*[*хxXХ×]\s*(\d{2,4})(?:[.,](\d))?\s*[*хxXХ×]\s*(\d{2,4})"
    r"(?:[.,](\d))?\s*(мм|см)?", re.IGNORECASE)


def _triple(name):
    """Первая тройка размеров из имени: (dims_mm_or_none, unit|None, decimals_were_used)."""
    n = str(name).lower()
    m = _DIM_RE.search(n)
    if not m:
        return None, None
    a = float(m.group(1))
    if m.group(2):
        a += float("0." + m.group(2))
    b = float(m.group(3))
    if m.group(4):
        b += float("0." + m.group(4))
    c = float(m.group(5))
    if m.group(6):
        c += float("0." + m.group(6))
    unit = m.group(7).lower() if m.group(7) else None
    if unit == "см":
        return tuple(sorted(int(round(x * 10)) for x in (a, b, c))), "см"
    if unit == "мм":
        return tuple(sorted(int(round(x)) for x in (a, b, c))), "мм"
    # без единицы: кандидаты-мм = как есть и ×10 (округление)
    mm1 = tuple(sorted(int(round(x)) for x in (a, b, c)))
    mm2 = tuple(sorted(int(round(x * 10)) for x in (a, b, c)))
    return (mm1, mm2), None


def _qty(name):
    m = re.search(r"(\d+)\s*(?:шт|штук)", str(name).lower())
    return int(m.group(1)) if m else None


def _type_keys(name):
    n = str(name).lower()
    return [k for k in OUR_TYPE_KEYS if k in n]


# ── донорский каталог коробов ───────────────────────────────────────────────

def load_donor():
    av = json.loads(DONOR_AVA.read_text(encoding="utf-8"))
    cats = json.loads(DONOR_CATS.read_text(encoding="utf-8"))
    mdata = json.loads(DONOR_MD.read_text(encoding="utf-8"))
    pid_cats = mdata.get("pid_cats", {})
    box_pids = sorted(p for p, cs in pid_cats.items()
                      if any(str(c).startswith("boxes") for c in cs))
    price = {}
    for pid in box_pids:
        for cat in pid_cats[pid]:
            entry = cats.get(str(cat), {}).get(pid)
            if entry and entry.get("price") is not None:
                price[pid] = float(entry["price"])
                break
    donor = {}
    for pid in box_pids:
        a = av.get(pid)
        if not isinstance(a, dict):
            continue
        title = str(a.get("title") or "").strip()
        status = str(a.get("status") or "")
        dims, unit = _triple(title)
        if not dims:
            continue
        # донорский каталог в мм: если в названии нет «см/мм», берём числовую тройку как мм
        if unit is None:
            dims = dims[0]
        donor[pid] = {
            "pid": pid, "title": title, "status": status,
            "price": price.get(pid), "price_note": ("нет цены" if pid not in price else None),
            "subcats": [str(c) for c in pid_cats.get(pid, [])],
            "dims": tuple(sorted(dims)),
        }
    return donor, box_pids


def donor_score(donor, our_keys):
    """0..1 — насколько подкатегория/имя донора отвечает типу нашего имени."""
    if not our_keys:
        return 0.0
    name = donor["title"].lower()
    sub = " ".join(donor["subcats"])
    score = 0.0
    for key in our_keys:
        if key in name:
            score += 1.0
        for sc, sc_keys in TYPE_SCORE.items():
            if key in sc_keys and sc in sub:
                score += 0.7
    return score


def near(a, b, tol=5):
    return all(abs(x - y) <= tol for x, y in zip(sorted(a), sorted(b)))


def best_donor(donor, dims_mm, our_keys, tolerance_accept=False):
    """Выбор донора по размеру. Точное → (pid, 'точное'); ближнее ≤30 → ('близко') если разрешено."""
    exact = [d for d in donor.values() if tuple(sorted(d["dims"])) == tuple(sorted(dims_mm))]
    if exact:
        exact.sort(key=lambda d: (-donor_score(d, our_keys), d["status"] != "В наличии", d["price"] or 9e9))
        return exact[0], "точное"
    if tolerance_accept:
        near_ok = [d for d in donor.values()
                   if near(d["dims"], dims_mm, tol=30) and max(abs(x - y) for x, y in zip(sorted(d["dims"]), sorted(dims_mm))) >= 6]
        if near_ok:
            near_ok.sort(key=lambda d: (-donor_score(d, our_keys), d["status"] != "В наличии",
                                        sum(abs(x - y) for x, y in zip(sorted(d["dims"]), sorted(dims_mm)))))
            return near_ok[0], "близко"
    return None, None


# ── основная логика ─────────────────────────────────────────────────────────

def resolve_and_stitch(items, donor):
    rows = []
    for it in items:
        name = str(it.get("name") or "")
        art = str(it.get("offer_id") or "")
        price = float(it.get("price") or 0)
        res, unit = _triple(name)
        our_keys = _type_keys(name)
        qty = _qty(name)
        if res is None:
            rows.append({"art": art, "name": name, "price": price, "qty": qty,
                         "bucket": "нет-размера-в-имени", "reason": "размера короба в имени нет",
                         "donor": None})
            continue
        # с явной единицей
        if unit in ("см", "мм"):
            d, how = best_donor(donor, res, our_keys, tolerance_accept=True)
            bucket = "сшито-точно" if how == "точное" else ("сшито-близко" if how == "близко" else "нет-донора")
            reason = (f"размер {res} ({unit}), донор {'±30мм близко' if how=='близко' else 'точно'}"
                      if d else f"размер {res} ({unit}), донора нет в каталоге")
            rows.append({"art": art, "name": name, "price": price, "qty": qty, "unit": unit,
                         "dims_mm": res, "bucket": bucket, "reason": reason, "donor": d})
            continue
        # без единицы: пробуем обе трактовки
        mm_as_is, mm_cm = res
        hit1, how1 = best_donor(donor, mm_as_is, our_keys)
        hit2, how2 = best_donor(donor, mm_cm, our_keys)
        # физическая правдоподобность: 40-мм «переездная» — чепуха; отсекаем абсурд по ключам/величине
        def plausible(dims, keys):
            if max(dims) >= 2500:
                return False
            if min(dims) < 25 and ("переезд" in keys or "архив" in keys or "ручк" in keys):
                return False
            return True
        p1 = hit1 is not None and plausible(mm_as_is, our_keys)
        p2 = hit2 is not None and plausible(mm_cm, our_keys)
        if p1 and p2:
            rows.append({"art": art, "name": name, "price": price, "qty": qty,
                         "dims_mm": None, "bucket": "размер-без-единицы-неоднозначно",
                         "reason": f"см/мм не указаны: донор есть и на {mm_as_is} мм и на {mm_cm} мм",
                         "cand": [hit1["pid"], hit2["pid"]], "donor": None})
            continue
        chosen, how, dims_used = (hit1, how1, mm_as_is) if p1 else ((hit2, how2, mm_cm) if p2 else (None, None, None))
        if chosen:
            rows.append({"art": art, "name": name, "price": price, "qty": qty,
                         "dims_mm": dims_used, "bucket": "сшито-точно",
                         "reason": f"см/мм не указаны → по единственному совпадению донора на {dims_used} мм",
                         "donor": chosen})
            continue
        rows.append({"art": art, "name": name, "price": price, "qty": qty,
                     "dims_mm": None, "bucket": "размер-без-единицы-нет-донора",
                     "reason": f"см/мм не указаны, донора нет ни на {mm_as_is} ни на {mm_cm}",
                     "donor": None})
    return rows


def donor_url(pid):
    return f"{BASE}/catalog/{pid}/"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Честная сшивка коробок с донором cargo.shop (read-only).")
    ap.add_argument("--date", default="2026-09-10")
    args = ap.parse_args(argv)
    DATE = args.date

    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    items = frozen["items"]
    print(f"заморожено: {len(items)} коробок")

    donor, box_pids = load_donor()
    print(f"донор-короба: {len(donor)} из {len(box_pids)} pid (с размером)")
    st = Counter(d["status"] for d in donor.values())
    print(f"  статусы: {dict(st)}")

    rows = resolve_and_stitch(items, donor)
    buckets = Counter(r["bucket"] for r in rows)
    print(f"\nСШИВКА: {dict(buckets)}")

    stitched = [r for r in rows if r.get("donor")]
    print(f"со сшитым донором: {len(stitched)}/{len(rows)}")
    instock = sum(1 for r in stitched if r["donor"]["status"] == "В наличии")
    print(f"  из них донор В НАЛИЧИИ: {instock}")

    # артефакты
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "date": DATE, "scope": "988 коробок → донор cargo.shop (shop.cargo-avto.ru, Москва)",
        "rule": "без обмана: донор=реальный pid покупки; см/мм без единицы решается только донором; "
                "неоднозначно/нет донора = честный статус, ссылка НЕ выдумывается",
        "frozen": FROZEN.name, "items_total": len(rows),
        "donor_boxes": len(donor), "donor_status": dict(st),
        "buckets": dict(buckets),
        "stitched_total": len(stitched), "stitched_instock": instock,
        "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))

    _write_csv(rows, OUT_CSV)
    _write_md(manifest, OUT_MD)
    print(f"\nартефакты:\n  {OUT_JSON.name}\n  {OUT_MD.name}\n  {OUT_CSV.name}")
    return 0


def _write_csv(rows, path):
    import csv
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["№", "Наименование", "Цена, ₽", "Кол-во в упак.",
                    "Донор (cargo.shop pid)", "Донор товар", "Статус донора",
                    "Ссылка донора", "Сшивка"])
        for i, r in enumerate(rows, 1):
            d = r.get("donor")
            w.writerow([
                i, r["name"], f'{r["price"]:.0f}', r["qty"] or "",
                d["pid"] if d else "", d["title"][:80] if d else "",
                d["status"] if d else "", donor_url(d["pid"]) if d else "",
                r["bucket"] + (" · " + r["reason"][:40] if not d else ""),
            ])


def _write_md(m, path):
    L = [f"# КОРОБКИ · ЧЕСТНАЯ СШИВКА С ДОНОРОМ CARGO.SHOP · {m['date']}",
         "",
         f"- заморожено коробок: **{m['items_total']}** · донор-коробов в каталоге: **{m['donor_boxes']}**",
         f"- статусы донора: {m['donor_status']}",
         f"- правило: донор = реальный pid покупки на shop.cargo-avto.ru; см/мм без единицы решаются "
         f"ТОЛЬКО совпадением донора; неоднозначно/нет донора = честный статус без выдуманной ссылки",
         "",
         "## Итог сшивки",
         ""]
    for b, c in m["buckets"].items():
        L.append(f"- **{b}**: {c}")
    L += ["", f"- **со сшитым донором: {m['stitched_total']}** (из них В наличии: {m['stitched_instock']})",
          "",
          "## Легенда статусов",
          "- `сшито-точно` — донор того же размера короба (точное совпадение или ±30мм «близко» при явной единице)",
          "- `сшито-точно` (без единицы) — размер в имени без см/мм, донор найден по единственной трактовке",
          "- `размер-без-единицы-неоднозначно` — обе трактовки имеют донора → НЕ угадываем (уточнить)",
          "- `нет-донора` — размера нет в имени, или донор такого размера в каталоге отсутствует",
          "",
          "## Первые 30 строк (простая таблица оператора: Наименование · Цена · Донор)",
          ""]
    import csv
    for r in m["rows"][:30]:
        d = r.get("donor")
        donor_cell = f"{d['pid']} · {d['title'][:52]} · {d['status']} · {donor_url(d['pid'])}" if d else "—"
        L.append(f"- `{r['art']}` **{r['name'][:70]}** · {r['price']:.0f}₽ · {donor_cell}")
    L += ["", "Полный список: JSON-артефакт (строки `rows[]`) + CSV-таблица рядом."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

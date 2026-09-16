#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН КОРОБКИ · ЛЕКСИКОН ЧЕСТНОГО ВЕСА ДОНА + МАТЧ ЭШЕЛОНОВ (0₽, только чтение файлов).

Закрывает ГЕЙТ ВЕСА (#22): файл коробок ИП даёт в «Вес в упаковке» только ИИ-филлер
(200-мм короб «весит» как 600-мм — физневозможно; колонка «Вес товара, г» пуста везде).
ЧЕСТНЫЙ вес берём у ДОНА cargo.shop — реальные коробки с реальными кг:
  источник А: CARGO_COLLECTION_2026-09-07/cargo_master_products.json («Вес, кг» на коробочных
              SKU, категория «Упаковка для маркетплейсов» и др.) — канон-снапшот 07.09;
  источник Б: parsers/parsed_data/cargo-avto_boxes_*.xlsx (живые сканы категории «Коробки»,
              колонки Длина/Ширина/Высота мм + Марка картона + Вес кг) — дополняет типы,
              которых нет в мастере.
Совпадение по ТОЧНОМУ размеру (сортированная тройка мм — коробка одна и та же физ.,
порядок осей в имени дона не важен). Вес дона в кг → г.

Выход (артефакты):
  runtime/ozon_boxes/korobki_weight_lexicon_<DATE>.json   — лексикон: размер → дон-факт
  runtime/ozon_boxes/korobki_weight_resolution_<DATE>.md  — матч Echelon-1 (17 замороженных)
    и Echelon-2 (20 малых поштучных L<500): per-арт файл-вес ⚠ vs дон-вес ✓/НЕТ-близнеца.

Ничего наружу не пишет. Веса дон = факт чтения файла (не выдумка). Ключи не трогает.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from datetime import date
from pathlib import Path

import openpyxl  # noqa: E402  (/usr/bin/python3, 3.9.6)

HERE = Path(__file__).resolve().parent
DATE = date.today().isoformat()
BASE = HERE / "runtime" / "ozon_boxes" / "ozon_korobki_base_2026-09-08.json"
E1_ITEMS = HERE / "runtime" / "ozon_boxes" / "korobki_echelon1_DRY_2026-09-09.items.json"
MASTER = Path.home() / "parsers/parsed_data/CARGO_COLLECTION_2026-09-07/cargo_master_products.json"
DONOR_XLSX = sorted(glob.glob(str(Path.home() / "parsers/parsed_data/cargo-avto_boxes_*.xlsx")))
OUT_LEX = HERE / "runtime" / "ozon_boxes" / f"korobki_weight_lexicon_{DATE}.json"
OUT_MD = HERE / "runtime" / "ozon_boxes" / f"korobki_weight_resolution_{DATE}.md"

SRC = "ИП Анна/ya new/карго/Коробка для переезда Готов Озон.xlsx"
_DIM_RE = re.compile(r"(\d{3,4})\s*[×xх*]\s*(\d{3,4})\s*[×xх*]\s*(\d{3,4})")
_BOX = re.compile(r"короб|гофрокороб|кофр", re.I)
# категории-исключения (скотч/плёнка/наполнитель живут в той же «Упаковка для МП», но не коробки)
_BOX_CAT = re.compile(r"маркетплейс|коробк|упаковк", re.I)


def _sorted3(d, w, h):
    return tuple(sorted(int(x) for x in (d, w, h)))


def _donor_from_master():
    """Источник А: мастер-снапшот — коробочные SKU с честным «Вес, кг». Возвращает dict key→факт."""
    lex = {}
    if not MASTER.exists():
        return lex
    rows = json.loads(MASTER.read_text(encoding="utf-8"))
    for p in rows:
        nm = str(p.get("Наименование (Ozon)") or p.get("Наименование") or "")
        cat = str(p.get("Категории") or "")
        if not _BOX.search(nm) or not _BOX_CAT.search(cat):
            continue
        m = _DIM_RE.search(nm)
        if not m:
            continue
        w = p.get("Вес, кг")
        if w in (None, ""):
            continue
        try:
            wg = round(float(w) * 1000)
        except (TypeError, ValueError):
            continue
        if wg <= 0:
            continue
        key = _sorted3(*m.groups())
        lex.setdefault(key, {"source": "master", "art": str(p.get("Артикул")),
                             "weight_g": wg, "note": nm[:70]})
    return lex


def _donor_from_xlsx():
    """Источник Б: живые сканы «Коробки» — физ-коробки с отдельными колонками мм + марка + кг.

    Порядок файлов: СВЕЖИЙ ПЕРВЫМ (дата в имени), setdefault берёт первый валидный поштучный
    факт. Артикул дона = только строка вида 96XXXXX-N; строки, где col0 не артикул (в старых
    сканах 07-23 в col0 лежало имя) — пропускаем. Размеры-мусор ('150+40', составные) — мимо.
    """
    ART_RE = re.compile(r"^96\d{5}-\d+$")
    lex = {}
    for f in sorted(DONOR_XLSX, reverse=True):
        wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        hdr = {str(x) if x is not None else "": i for i, x in enumerate(rows[0])}
        iD, iW, iH, iKG = (hdr.get("Длина, мм"), hdr.get("Ширина, мм"),
                           hdr.get("Высота, мм"), hdr.get("Вес, кг"))
        iQ = hdr.get("Кол-во в комплекте, шт")
        iMark = hdr.get("Марка картона")
        if None in (iD, iW, iH, iKG):
            continue
        for r in rows[1:]:
            if r[0] is None or not ART_RE.match(str(r[0])):
                continue
            if r[iD] is None or r[iW] is None or r[iH] is None:
                continue
            qty = r[iQ] if (iQ is not None and r[iQ] is not None) else 1
            if str(qty).strip() not in ("1", "1.0", "1,0"):   # только поштучный физ-тип
                continue
            try:
                key = _sorted3(int(r[iD]), int(r[iW]), int(r[iH]))
            except (TypeError, ValueError):
                continue
            kg = r[iKG]
            if kg in (None, ""):
                continue
            try:
                wg = round(float(kg) * 1000)
            except (TypeError, ValueError):
                continue
            if wg <= 0:
                continue
            mark = str(r[iMark]) if (iMark is not None and r[iMark] is not None) else ""
            lex.setdefault(key, {"source": Path(f).name[:22], "art": str(r[0]),
                                 "weight_g": wg, "mark": mark,
                                 "note": str(r[1] or "")[:70]})
    return lex


def _donor_lexicon():
    """Слить мастер+сканы в key → СПИСОК дон-фактов.

    Один размер может нести НЕСКОЛЬКО реальных коробок дона с РАЗНЫМ весом (600×400×400:
    «№10-Ц Бизнес Т-24» 663 г из скана коробок vs «П-32 ВС прочный» 846 г из мастера — это
    две разные физ. коробки одного габарита). list len=1 → вес бесспорен; len>1 → развилка
    (какую коробку дона считаем близнецом — решает оператор, не выдумываем).
    """
    m = _donor_from_master()
    x = _donor_from_xlsx()
    keys = set(m) | set(x)
    lex = {}
    for k in keys:
        facts = []
        if k in m:
            facts.append(m[k])
        if k in x and not any(f["weight_g"] == x[k]["weight_g"] and f["source"] == "master"
                              for f in facts):
            facts.append(x[k])
        # схлопнуть идентичные по весу+арту (мастер и скан одного и того же товара)
        seen, uniq = set(), []
        for f in facts:
            sig = (f["weight_g"], f["art"])
            if sig in seen:
                continue
            seen.add(sig)
            uniq.append(f)
        lex[k] = uniq
    return lex


def _singles_from_base(src, maxL):
    """Поштучные коробки из базы: ГОТОВО, без «шт», размер из имени, длинная ≤ maxL."""
    data = json.loads(BASE.read_text(encoding="utf-8"))
    out = []
    for p in data["products"]:
        if p.get("source") != src:
            continue
        if "ГОТОВО" not in (p.get("readiness") or []):
            continue
        name = str(p.get("name") or "")
        if "шт" in name:
            continue
        m = _DIM_RE.search(name)
        if not m:
            continue
        dims = tuple(int(g) for g in m.groups())
        if max(dims) > maxL:
            continue
        if not (p.get("photos") and p.get("price")):
            continue
        out.append({"art": str(p["art"]), "name": name, "price": float(p["price"]),
                    "dims": dims, "weight_file_g": (p.get("ovh") or {}).get("weight_g")})
    out.sort(key=lambda x: x["art"])
    return out


def _resolve(dims, lex):
    """Список дон-фактов для размера: [] = нет близнеца, 1 = бесспорен, >1 = развилка."""
    key = tuple(sorted(dims))
    return lex.get(key, [])


def main():
    lex = _donor_lexicon()
    n_master = sum(1 for facts in lex.values() for f in facts if f["source"] == "master")
    n_xlsx = sum(len(facts) for facts in lex.values()) - n_master
    print(f"дон-лексикон честного веса: {len(lex)} размеров, "
          f"{sum(len(f) for f in lex.values())} дон-фактов ({n_master} мастер, {n_xlsx} сканы xlsx)")

    # ── Echelon-1: замороженные 17 (меты несут собранный размер) ──
    e1 = json.loads(E1_ITEMS.read_text(encoding="utf-8"))["metas"]
    e1_rows = []
    for m in e1:
        res = _resolve(m["dims_mm_assembled"], lex)
        e1_rows.append({"art": m["art"], "dims": tuple(m["dims_mm_assembled"]),
                        "price": m["price"], "file_g": m["weight_file_g"],
                        "facts": res, "unique": len(res) == 1})
    # ── Echelon-2: поштучные L<500 из базы ──
    e2_rows = []
    for c in _singles_from_base(SRC, maxL=499):
        res = _resolve(c["dims"], lex)
        e2_rows.append({"art": c["art"], "dims": c["dims"], "price": c["price"],
                        "name": c["name"][:58],
                        "file_g": int(c["weight_file_g"]) if c["weight_file_g"] else None,
                        "facts": res, "unique": len(res) == 1})

    def stats(rows):
        got = [r for r in rows if r["facts"]]
        amb = [r["art"] for r in got if not r["unique"]]
        no_twin = [r["art"] for r in rows if not r["facts"]]
        return {"n": len(rows), "donor_matched": len(got),
                "unique": len(got) - len(amb), "ambiguous": amb, "no_twin": no_twin}

    s1, s2 = stats(e1_rows), stats(e2_rows)
    print(f"Echelon-1 (17): дон {s1['donor_matched']}/{s1['n']} (однознач {s1['unique']}, "
          f"развилка {len(s1['ambiguous'])}: {s1['ambiguous']}) · нет: {s1['no_twin']}")
    print(f"Echelon-2 ({s2['n']}): дон {s2['donor_matched']}/{s2['n']} (однознач {s2['unique']}, "
          f"развилка {len(s2['ambiguous'])}: {s2['ambiguous']}) · нет: {s2['no_twin']}")

    OUT_LEX.parent.mkdir(parents=True, exist_ok=True)
    OUT_LEX.write_text(json.dumps({"date": DATE,
                                   "note": "честный вес коробок = дон cargo (мастер 07.09 + сканы "
                                           "cargo-avto_boxes). ключ = сортированная тройка мм; "
                                           "список = реальные коробки дона этого размера (1 бесспорен, "
                                           ">1 = разные физ. коробки одного габарита)",
                                   "lexicon": {f"{k[0]}x{k[1]}x{k[2]}": v for k, v in lex.items()}},
                                  ensure_ascii=False, indent=1))
    _write_md(e1_rows, e2_rows, s1, s2, lex)
    print(f"\nартефакты: {OUT_LEX.name}\n           {OUT_MD.name}")
    return 0


def _fmt_facts(facts):
    if not facts:
        return "—"
    parts = [f"{f['weight_g']} г ({f['art']}, {f['source'][:14]})" for f in facts]
    return "; ".join(parts)


def _write_md(e1, e2, s1, s2, lex):
    L = [f"# КОРОБКИ · ЧЕСТНЫЙ ВЕС = ДОН · РЕЗОЛЮЦИЯ ЭШЕЛОНОВ · {DATE} · 0₽",
         "",
         "Источник веса в файле ИП — ИИ-филлер «Вес в упаковке» (200-мм короб «весит» как 600-мм);",
         "колонка «Вес товара, г» пуста во всех строках. ЧЕСТНЫЙ вес = дон cargo.shop: реальные",
         "коробки, реальные кг (мастер CARGO_COLLECTION 07.09 + живые сканы cargo-avto_boxes).",
         f"Совпадение по точному размеру. Лексикон ({len(lex)} размеров) в korobki_weight_lexicon_{DATE}.json.",
         "",
         f"- **Echelon-1**: дон **{s1['donor_matched']}/{s1['n']}** · однознач {s1['unique']} · "
         f"развилка {len(s1['ambiguous'])} {s1['ambiguous']} · нет близнеца: {s1['no_twin']}",
         f"- **Echelon-2**: дон **{s2['donor_matched']}/{s2['n']}** · однознач {s2['unique']} · "
         f"развилка {len(s2['ambiguous'])} {s2['ambiguous']} · нет близнеца: {s2['no_twin']}",
         "",
         "## Echelon-1 · файл-вес ⚠ → дон-вес ✓",
         "",
         "| арт | цена | размер, мм | файл ⚠ | ДОН ✓ |",
         "|---|---|---|---|---|",
         ]
    for r in sorted(e1, key=lambda x: x["art"]):
        L.append(f"| {r['art']} | {r['price']:.0f}₽ | {'×'.join(map(str, r['dims']))} | "
                 f"{r['file_g']} г | {_fmt_facts(r['facts'])} |")
    L.append("")
    L.append("## Echelon-2 (малые поштучные L<500) · резолюция веса")
    L.append("")
    L.append("| арт | цена | размер, мм | файл ⚠ | ДОН ✓ | имя |")
    L.append("|---|---|---|---|---|---|")
    for r in sorted(e2, key=lambda x: x["art"]):
        L.append(f"| {r['art']} | {r['price']:.0f}₽ | {'×'.join(map(str, r['dims']))} | "
                 f"{r['file_g']} г | {_fmt_facts(r['facts'])} | {r['name']} |")
    L.append("")
    L.append("## Честный вердикт для оператора")
    L.append("- Однозначных дон-фактов веса: вес карточки = дон (кг → г), НЕ файл.")
    L.append("- Развилка (>1 реальная коробка дона того же размера, напр. 600×400×400 "
             "«№10-Ц Бизнес Т-24» 663 г vs «П-32 ВС прочный» 846 г): выбирает оператор по линии "
             "карточки (премиум/Бизнес → 663, пятислойный/прочный → 846).")
    L.append("- Нет дон-близнеца: вес не выдумываем → взвесить образец ИЛИ открытый вопрос.")
    OUT_MD.write_text("\n".join(L))
    return True


if __name__ == "__main__":
    raise SystemExit(main())

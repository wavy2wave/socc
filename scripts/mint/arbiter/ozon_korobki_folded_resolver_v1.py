#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · КОРОБКИ · РЕЗОЛВЕР «СКЛАД ИЗ ДОНА» → СУХОЙ МАНИФЕСТ ЧЕСТНЫХ ГАБАРИТОВ (0₽).

Решение оператора 09-10 («склад из дона»): в карточку идут НЕ ИИ-филлер base.ovh и НЕ
собранные габариты, а СЛОЖЕННАЯ упаковка + честный вес дона cargo.shop:
  • основание = две БОЛЬШИЕ оси собранного короба (Д×Ш×В с живой карточки дона);
  • толщина   = «Транспортировочный объём, м³» × 1e9 / (большая × средняя), мм;
  • вес       = «Вес, кг» дона × кол-во в карточке (карточка «N шт» = стопка N сложенных).
Факт дона берётся ИЗ ЕГО ЖИВОЙ КАРТОЧКИ (ozon_korobki_donor_phys_v1), не выдумывается.
Нет дон-физики (нет веса/объёма) → HELD: карточка НЕ льётся, вес/габарит не выдумываем.

Сухо: наружу ничего не пишет. Артефакты:
  korobki_FOLDED_<DATE>.items.json   — payload'ы с честными габаритами (для показа/залива)
  korobki_FOLDED_<DATE>.{json,md}    — отчёт + покрытие + old→new + HELD
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime" / "ozon_boxes"
DATE = date.today().isoformat()

STITCHED = RUNTIME / "korobki_STITCHED_2026-09-10.items.json"
PHYS = RUNTIME / f"korobki_donor_phys_{DATE}.json"
STITCH = RUNTIME / "korobki_DONOR_STITCH_2026-09-10.json"


def _latest(pattern, skip=()):
    """Свежий артефакт по маске. Вход ищем ПО НАЛИЧИЮ, а не по календарю: день меняется,
    данные остаются — орган не должен падать от того, что вчерашний сбор ещё актуален.
    skip — подстроки-двойники (напр. подмножество _EXACT той же сшивки)."""
    hits = [p for p in sorted(RUNTIME.glob(pattern)) if not any(s in p.name for s in skip)]
    return hits[-1] if hits else None

OUT_ITEMS = RUNTIME / f"korobki_FOLDED_{DATE}.items.json"
OUT_JSON = RUNTIME / f"korobki_FOLDED_{DATE}.json"
OUT_MD = RUNTIME / f"korobki_FOLDED_{DATE}.md"

# честный допуск «приближения»: толщина склада округляется вверх до мм
_QTY_RE = re.compile(r"(\d+)\s*(?:шт|штук)", re.IGNORECASE)

# ПРЕДЕЛ ПРАВДОПОДОБИЯ СКЛАДА. Сложенная коробка физически не может занимать больше
# ~трети объёма собранной (толщина склада ≈ площадь развёртки × толщина картона / основание;
# для типовых гофрокоробов это 5–25% меньшей оси). Эмпирика по 102 донорам с честным
# трансп.объёмом: медиана 0.10, p90 0.31. Выше 0.35 — донор отдал объём СОБРАННОГО короба
# (проверено: PS.503/PS.505 = 0.997), и «склад» из него не выводится. Тогда HELD, не гадаем.
FOLD_MAX_RATIO = 0.35

# Ограничение перебора связки (см. pack_bundle): 60×60 вариантов достаточно для любой реальной
# партии, дальше только дороже без выигрыша.
_PACK_CAP = 60
_DIM_RE = re.compile(r"(\d{2,4})\s*[×xх*]\s*(\d{2,4})\s*[×xх*]\s*(\d{2,4})")


def _qty(name):
    m = _QTY_RE.search(str(name))
    return int(m.group(1)) if m else 1


def _dims_from_name(name):
    m = _DIM_RE.search(str(name))
    if not m:
        return None
    vals = [int(g) for g in m.groups()]
    # имя «20х10х10 см» — единица в хвосте; «500*300*300 мм» — мм. См определяем по величине:
    # если все ≤ 60 → почти наверняка см (короб 20 см), иначе мм.
    if all(v <= 60 for v in vals):
        vals = [v * 10 for v in vals]
    return tuple(sorted(vals))


def folded_from_phys(rec):
    """дон-физика → (L,W,t_mm) склада ОДНОЙ коробки или (None, причина).

    Дон-вес/объём даны на УПАКОВКУ («Кол-во в упаковке, шт.») → берём *_single.
    Валидация (без неё физика дона бессмысленна): доля склада в собранном объёме обязана быть
    ≤ FOLD_MAX_RATIO. Иначе донор опубликовал объём СОБРАННОГО короба под видом транспортного —
    «склад» из него не выводится (источник 3.9-метровых «башен»).
    """
    if not rec:
        return None, "нет дон-физики"
    w = rec.get("weight_kg_single") if rec.get("weight_kg_single") is not None else rec.get("weight_kg")
    tv = rec.get("transport_m3_single") if rec.get("transport_m3_single") is not None else rec.get("transport_m3")
    dims = rec.get("dims_mm")
    if not (w and tv and dims):
        return None, "у дона нет веса/трансп.объёма"
    sd = sorted(dims)
    L, W = sd[-1], sd[-2]                              # две большие оси — основание
    assembled_m3 = (sd[0] * sd[1] * sd[2]) / 1e9
    ratio = (tv / assembled_m3) if assembled_m3 else 9.9
    if ratio > FOLD_MAX_RATIO:
        return None, (f"донор отдал объём СОБРАННОГО короба, а не склада "
                      f"(трансп/собранного = {round(ratio, 3)} > {FOLD_MAX_RATIO}) — склад недоказуем")
    t_mm = tv * 1e9 / (L * W)
    t_mm = max(1, int(round(t_mm)))
    return {"L": int(L), "W": int(W), "t_mm": t_mm,
            "weight_single_g": int(round(w * 1000)),
            "transport_m3": tv, "weight_kg": w, "dims_assembled": sorted(dims),
            "pack_qty": rec.get("pack_qty", 1)}, None


def pack_bundle(qty, L, W, t):
    """N сложенных коробов → связка (a,b,c) минимальной САМОЙ ДЛИННОЙ стороны.

    Наивная стопка (1,1,N) даёт 3-метровые «башни» (100 шт × 21 мм = 2100 мм), которые
    курьер не возьмёт. Реально такую партию укладывают аккуратной связкой: несколько
    столбиков рядом. Перебираем a×b×c ≥ qty и берём вариант с наименьшей длинной стороной
    (тай-брейк — по объёму). Это геометрия укладки, а не выдумка: число коробов то же.
    Возвращает (depth, width, height, "a×b×c").
    """
    if qty <= 1:
        return L, W, t, "1×1×1"
    cap = min(qty, _PACK_CAP)
    best = None
    for a in range(1, cap + 1):
        for b in range(1, cap + 1):
            c = -(-qty // (a * b))                     # ceil(qty / (a*b))
            d = (a * L, b * W, c * t)
            key = (max(d), d[0] * d[1] * d[2])
            if best is None or key < best[0]:
                best = (key, d, f"{a}×{b}×{c}")
    _, d, layout = best
    return d[0], d[1], max(1, int(d[2])), layout


def build_card(item, meta, phys):
    """Одна сшитая карточка → (item', meta', status). Габариты/вес = склад дона × кол-во."""
    name = str(item.get("name") or meta.get("name") or "")
    pid = str(meta.get("donor_pid") or "")
    rec = phys.get(pid)
    fold, why = folded_from_phys(rec)
    qty = _qty(name)
    if fold is None:
        return None, {"art": item.get("offer_id"), "name": name[:64], "donor_pid": pid,
                      "reason": why, "qty": qty}, "held"
    # габарит упаковки: N сложенных коробов аккуратной связкой (не башней)
    L, W, t = fold["L"], fold["W"], fold["t_mm"]
    dep, wid, hgt, layout = pack_bundle(qty, L, W, t)
    dims = {"depth": dep, "width": wid, "height": hgt}
    weight_g = fold["weight_single_g"] * qty
    out = json.loads(json.dumps(item))                  # глубокое копирование payload
    out["depth"] = dims["depth"]
    out["width"] = dims["width"]
    out["height"] = dims["height"]
    out["weight"] = int(weight_g)
    out["dimension_unit"] = "mm"
    out["weight_unit"] = "g"
    m = {
        "art": out.get("offer_id"), "name": name[:64], "qty": qty,
        "donor_pid": pid, "donor_status": meta.get("donor_status"),
        "donor_url": meta.get("donor_url"), "stitch": meta.get("stitch"),
        "assembled_dims": fold["dims_assembled"], "mark": (rec or {}).get("mark"),
        "donor_pack_qty": fold["pack_qty"], "donor_weight_single_g": fold["weight_single_g"],
        "filler_old": {"depth": item.get("depth"), "width": item.get("width"),
                       "height": item.get("height"), "weight": item.get("weight")},
        "folded": {"depth": dims["depth"], "width": dims["width"], "height": dims["height"],
                   "weight": int(weight_g), "single_t_mm": t,
                   "single_weight_g": fold["weight_single_g"], "transport_m3": fold["transport_m3"]},
        "rule": f"склад дона: основание {L}×{W} мм, толщина {t} мм/шт; связка {layout} → "
                f"{dims['depth']}×{dims['width']}×{dims['height']} мм; "
                f"вес {fold['weight_single_g']} г/шт × {qty} = {weight_g} г",
        "approx_note": "габарит упаковки — приближение по трансп. объёму дона (сайт публикует "
                       "объём и вес, не тройку склада); вес = вес товара без внешней упаковки",
    }
    return out, m, "ok"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Резолвер «склад из дона» → сухой манифест (0₽).")
    ap.add_argument("--phys", default=None, help="путь к dон-физике (по умолч. свежая)")
    ap.add_argument("--stitched", default=None)
    args = ap.parse_args(argv)

    phys_path = Path(args.phys).resolve() if args.phys else _latest("korobki_donor_phys_*.json")
    stitched_path = (Path(args.stitched).resolve() if args.stitched
                     else _latest("korobki_STITCHED_*.items.json", skip=("_EXACT",)))
    if not phys_path or not phys_path.exists():
        print("нет дон-физики — сначала ozon_korobki_donor_phys_v1.py (0₽)"); return 2
    if not stitched_path or not stitched_path.exists():
        print("нет сшитых карточек — сначала сшивка (0₽)"); return 2
    print(f"вход: {stitched_path.name} + {phys_path.name}")
    phys = json.loads(phys_path.read_text(encoding="utf-8"))["phys"]
    st = json.loads(stitched_path.read_text(encoding="utf-8"))
    items, metas = st["items"], st.get("metas", [])
    by_art = {(m.get("art") or m.get("offer_id")): m for m in metas}
    print(f"сшитых карточек: {len(items)} · дон-физика: {len(phys)} pid")

    out_items, out_metas, held = [], [], []
    for it in items:
        art = it.get("offer_id")
        meta = by_art.get(art, {})
        new_it, m, status = build_card(it, meta, phys)
        if status == "ok":
            out_items.append(new_it)
            out_metas.append(m)
        else:
            held.append(m)

    # сводка покрытия
    instock = sum(1 for m in out_metas if m.get("donor_status") == "В наличии")
    print(f"\nСКЛАД ИЗ ДОНА: готово {len(out_items)} / {len(items)} · HELD {len(held)}")
    print(f"  из готовых донор «В наличии»: {instock}")

    # ── перекрёстная сверка дон-веса (1 шт) с независимым фактом лексикона по геометрии ──
    lex = {}
    lex_path = RUNTIME / "korobki_weight_lexicon_2026-09-09.json"
    if lex_path.exists():
        lex = json.loads(lex_path.read_text(encoding="utf-8")).get("lexicon", {})
    xcheck = {"agree": 0, "differ": 0, "no_fact": 0}
    for m in out_metas:
        key = "x".join(str(x) for x in sorted(m["assembled_dims"]))
        facts = lex.get(key)
        f = facts[0] if isinstance(facts, list) and facts else (facts if isinstance(facts, dict) else None)
        if not f:
            xcheck["no_fact"] += 1
            m["weight_xcheck"] = None
            continue
        lg = f.get("weight_g")
        ratio = round(m["donor_weight_single_g"] / lg, 2) if lg else None
        m["weight_xcheck"] = {"lexicon_g": lg, "lexicon_art": f.get("art"), "ratio": ratio}
        if ratio and 0.6 <= ratio <= 1.6:
            xcheck["agree"] += 1
        else:
            xcheck["differ"] += 1
    print(f"  сверка веса с лексиконом: сходится {xcheck['agree']} · расходится {xcheck['differ']} · "
          f"нет независимого факта {xcheck['no_fact']}")

    OUT_ITEMS.parent.mkdir(parents=True, exist_ok=True)
    OUT_ITEMS.write_text(json.dumps({"date": DATE, "scope": "493 сшитых · склад из дона",
                                     "items": out_items, "metas": out_metas},
                                    ensure_ascii=False, indent=1), encoding="utf-8")

    manifest = {
        "date": DATE, "scope": "коробки · габариты упаковки = склад дона + честный вес",
        "policy": "оператор 09-10: склад из дона (основание = 2 большие оси; толщина = трансп.объём/(L·W); "
                  "вес = дон кг × кол-во). Приближение по трансп. объёму — помечено.",
        "source_frozen": stitched_path.name, "donor_phys": phys_path.name,
        "cards_total": len(items), "ready": len(out_items), "held": len(held),
        "ready_instock": instock,
        "held_list": held, "metas": out_metas,
    }
    OUT_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    L = [f"# КОРОБКИ · СКЛАД ИЗ ДОНА (честные габариты+вес) · СУХО 0₽ · {DATE}", "",
         f"- сшитых карточек: **{len(items)}** · готово к заливу/правке: **{len(out_items)}** · "
         f"HELD (нет дон-физики): **{len(held)}**",
         f"- политика: {manifest['policy']}",
         "", "## Пример old→new (ИИ-филлер → склад дона)", "",
         "| арт | кол-во | БЫЛО (филлер) | СТАЛО (склад дона) | дон-вес/шт | правило |",
         "|---|---|---|---|---|---|"]
    for m in out_metas[:20]:
        o, f = m["filler_old"], m["folded"]
        L.append(f"| {m['art']} | {m['qty']} шт | {o['depth']}×{o['width']}×{o['height']} / {o['weight']}г | "
                 f"{f['depth']}×{f['width']}×{f['height']} / {f['weight']}г | {f['single_weight_g']} г | "
                 f"{f['single_t_mm']} мм |")
    # честная сводка по посылкам: что реально получит курьер
    mx = max(out_metas, key=lambda m: m["folded"]["height"]) if out_metas else None
    big = [m for m in out_metas if m["folded"]["height"] > 1000]
    L += ["", "## Посылки (то, что реально повезёт курьер)",
          f"- самая высокая: {mx['art']} {mx['folded']['depth']}×{mx['folded']['width']}×"
          f"{mx['folded']['height']} мм / {mx['folded']['weight']} г" if mx else "",
          f"- выше 1000 мм: {len(big)}",
          f"- вес > 25 кг: {sum(1 for m in out_metas if m['folded']['weight'] > 25000)}",
          ""]
    L += ["", "## HELD (нет честной дон-физики — не льём, не выдумываем)"]
    for h in held:
        L.append(f"- `{h['art']}` {h['name']} — {h['reason']} (дон pid {h['donor_pid']})")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"\nартефакты:\n  {OUT_ITEMS.name}\n  {OUT_JSON.name}\n  {OUT_MD.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

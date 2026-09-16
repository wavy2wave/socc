#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OZON плёнка: ПУПОВИНА «карточка ⇄ донор» (ЗАКОН СИСТЕМЫ по слову оператора 09.09).

Директива оператора (дословно):
  «Главное нам размер. … Смотри по размерам — и каждую позицию вяжи с размерами в
   доноре. … там есть размеры, которых именно таких нет на доноре, поэтому берёшь
   что ближе по смыслу, логике. … у нас карточка, поступил заказ на 0.38×55 м —
   точно такого нет на доноре, но есть Арт. 9601512 — именно его и заказываем.
   То есть на сайте не может быть размеров, которые бы не нашли привязки к донору.
   Привязка — сделаем это инструментом ОЗОН и ЯМ циклов, ВСЕГДА. … чтобы это
   НИКОГДА НЕ НАПРЯГАЛО при заказе. Система в мгновение видит, уже даже по артикулу.»

Правило привязки (слово оператора 09.09, ПРОФИТ-ЗАКОН):
  «Смотрю что выгоднее, что дешевле по похожим размерам. Стараюсь сделать клиенту
   то же метраж, или ширину, не себе в убыток. При привязке ты обязан знать цену
   донора-закупка и ту, что у нас. Под капотом всё считаешь и видишь профит по
   конкретному товару сразу.»
  • ЕДИНИЦА = размер (w,l) + ЦЕНА + материал (г/м², слои). Плотность/слои — НЕ гейт
    («не убийца»), НО ярус-2 выбора: оператор для 0.38×55 берёт 9601512 (0.3×50, 40г/2сл,
    cost_total 420₽) ДОРОЖЕ 9605412 (0.3×100, 25г/2сл, 300₽) — материал лояльности,
    тонкую плёнку клиенту не подсовываем ради рубля.
  • ЯРУС-1 ПРИМАРНО «ТА ЖЕ ШИРИНА» (ширина клиента первична, дешевизна — ВНУТРИ класса):
    идём по классам ширины донора от ближайшего к w (по |Δw|); первый класс, что тянет
    метраж qty=ceil(l/длина_рулона) ≤ QCAP штуками, — побеждает. Класс НЕ прыгает на чужой
    ради цены: 0.6→0.6, 1.2→1.2, 1.5→1.5, 0.75→0.75. Схлопывания ширин (0.6→0.5, 1.2→0.75,
    1.5→1.2) ЗАПРЕЩЕНЫ. Свой класс не тянет (нужно > QCAP рулонов: 0.4×55 на 2/5м рулонах)
    → ближайший класс, что тянет (пример оператора: 0.38×55 → класс 0.3 → 9601512).
  • ЯРУС-2 внутри выигравшего класса: сначала совпадение материала карточки (г/м² ±0.5,
    слои =). Материал НЕ блокирует привязку: нет рулона под материал → берём любой.
  • ЯРУС-3 внутри яруса-2: МИНИМУМ закупки cost_total=cost×qty (макс. профит).
    Среди равных: меньше рулонов → ближе ширина → меньше артикул.
  • ПРОФИТ всегда считается: цена_карточки − cost_total. cost_total > цены → рулон
    помечается unprofitable=True (красным) — не молчим, карточку нельзя лить как есть.
  • Каждая карточка ВСЕГДА получает donor_article (никаких «без донора» для размера).
  • Канон рулонов = ЖИВОЙ скан категории (только реально в продаже на
    shop.cargo-avto.ru, с cost). Вне-стока/спящих карточек в каноне НЕТ.

Канон: runtime/ozon-library/donor-rolls-{date}.json (env OZON_DONOR_ROLLS_PATH).
Артефакт dry-привязки: donor-anchor-{date}.json.

CLI:
  python ozon_donor_anchor_v1.py --scan            # живой скан (0₽) → канон рулонов на дату
  python ozon_donor_anchor_v1.py --anchor          # dry-привязка library → донор (артефакт, НЕ мутирует)
  python ozon_donor_anchor_v1.py --rolls           # показать канон
"""
import argparse
import collections
import datetime as _dt
import json
import math
import re
import sys
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent / "runtime" / "ozon-library"
DONOR_HOST = "https://shop.cargo-avto.ru"
DONOR_SLUG = "vozdushno-puzyrkovaya-plenka"

_BUBBLE = ("пузыр", "пупырчат", "бабл", "bubble", "воздушно", "воздушно-пузырьк")
_NONROLL = ("пакет", "лист", "упаковк", "рулончик", "штук", "стреппинг", "гофрокартон",
            "уценк", "лента", "мешок", "скотч", "бумаг")
_WORD_LAY = {"одно": 1, "двух": 2, "двухслойн": 2, "трех": 3, "трёх": 3,
             "трёхслойн": 3, "четырёх": 4, "пяти": 5}


def _num(x):
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None


# ПРИМАРНО «ТА ЖЕ ШИРИНА» (ПРОФИТ-ЗАКОН): карточка считается попадающей в донорский
# класс ширины, если |Δw| ≤ NOM метров. Тогда берём ТОЛЬКО этот класс (не прыгаем на
# дешёвую 0.5, когда карточка 0.6). QCAP — максимум рулонов донора на метраж карточки
# (0.4×100 не выкупаем 20 штуками по 5 м — уходим на ближайшие ширины).
NOM = 0.026
QCAP = 6


def parse_roll_size(name):
    """'50*0.3 м …' → (w, l) метры, где w<l. Мм-ловушку (12*0.5 мм) НЕ ловим."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[*хx×]\s*(\d+(?:[.,]\d+)?)\s*м\b", (name or "").lower())
    if not m:
        return None
    a, b = _num(m.group(1)), _num(m.group(2))
    if a is None or b is None:
        return None
    return (min(a, b), max(a, b))


def dens_of(name):
    m = re.search(r"(\d{2,3})\s*г/м", (name or "").lower())
    return int(m.group(1)) if m else None


def lay_of(name):
    n = (name or "").lower().replace("ё", "е")
    for k, v in _WORD_LAY.items():
        if k in n:
            return v
    return None


def is_bubble_roll(prod):
    name = (prod.get("name") or "").lower().replace("ё", "е")
    if not any(k in name for k in _BUBBLE):
        return False
    if any(k in name for k in _NONROLL):
        return False
    sz = parse_roll_size(name)
    if not sz:
        return False
    w, l = sz
    if not (0.15 <= w <= 2.5 and 1 <= l <= 300) or not w < l:
        return False
    return True


def donor_rolls_path():
    return Path(__import__("os").environ.get(
        "OZON_DONOR_ROLLS_PATH", RUNTIME / f"donor-rolls-{_dt.date.today():%Y-%m-%d}.json"))


def scan_donor_rolls(limit=300):
    """Живой скан категории плёнки (0₽ GET) → список рулонов-канона с cost."""
    from suppliers.cargo_avto_v1 import CargoAvtoAdapter  # локальный импорт
    res = CargoAvtoAdapter().scan(category=DONOR_SLUG, limit=limit)
    prods = res if isinstance(res, list) else res.get("products", [])
    out, seen = [], set()
    for p in prods:
        art = str(p.get("article", "")).strip()
        name = p.get("name", "")
        if not art or not is_bubble_roll(p) or art in seen:
            continue
        seen.add(art)
        w, l = parse_roll_size(name)
        out.append({
            "article": art,
            "url": f"{DONOR_HOST}/catalog/{art}/",
            "w": w, "l": l,
            "dens": dens_of(name),
            "lay": lay_of(name),
            "cost": p.get("cost"),
            "name": (name or "")[:120],
        })
    out.sort(key=lambda r: (r["w"], r["l"], r["article"]))
    return out


def write_donor_rolls(rolls, path=None):
    path = Path(path or donor_rolls_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"generated": f"{_dt.date.today():%Y-%m-%d}", "host": DONOR_HOST,
           "count": len(rolls), "rolls": rolls}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(path)


def load_donor_rolls(path=None):
    p = Path(path or donor_rolls_path())
    if not p.exists():
        return []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    rolls = doc.get("rolls") if isinstance(doc, dict) else doc
    return [r for r in rolls if isinstance(r, dict)]


def load_latest_donor_rolls():
    """Последний доступный канон рулонов на диске (дата катится вперёд; ищем max дату)."""
    p = Path(donor_rolls_path())
    if p.exists():
        return load_donor_rolls(p)
    candidates = sorted(RUNTIME.glob("donor-rolls-*.json"))
    if not candidates:
        return []
    return load_donor_rolls(candidates[-1])


def anchor_for(w, l, grams=None, layers=None, price=None, rolls=None):
    """ПРОФИТ-ЯКОРЬ по слову оператора 09.09 (всегда есть ответ для размера).

    Три яруса (ширина первична, материал, потом цена):
      ЯРУС-1 «ТА ЖЕ ШИРИНА»: идём по классам ширины донора от ближайшего к w (по |Δw|);
        первый класс, что тянет метраж qty=ceil(l/длина) ≤ QCAP рулонов, — побеждает.
        Чужой дешёвый класс НЕ выигрывает: 0.6 не сваливается на 0.5.
      ЯРУС-2 внутри класса: сначала совпадение материала карточки (г/м² ±0.5, слои =).
        Оператор для 0.38×55 берёт 9601512 (40г/2сл) дороже 9605412 (25г/2сл).
      ЯРУС-3 внутри яруса-2: минимум cost_total=cost×qty (макс. профит).
      ФОЛБЭК: ни один класс не тянет ≤ QCAP → ближайший класс, честная нарезка своей
        ширины (0.4×500 → 0.4×5×100, а не прыжок на 1.2).
    Профит всегда под капотом: цена_карточки − cost_total. Убыточный выбор не молчит
    → unprofitable. → dict {article,url,roll,tag,qty,cost_total,card_price,
    profit,unprofitable,reason,mode} | None если rolls пуст / нет size.
    """
    rolls = [r for r in (rolls or load_donor_rolls())
             if _num(r.get("w")) is not None and _num(r.get("l")) is not None
             and r.get("cost") is not None]
    if not rolls or w is None or l is None:
        return None
    widths = sorted({_num(r.get("w")) for r in rolls})
    # строго ближайшая ширина; при РАВНОМ |Δw| — шире (не оголяем клиента: 0.35→0.4,
    # 0.45→0.5, 0.55→0.6). float-safe через round, иначе 0.099…98 vs 0.100…03 решает шум.
    ranked = sorted(widths, key=lambda rw: (round(abs(rw - w), 6), -rw))

    def build(rw):
        """все рулоны класса ширины rw, покрывающие метраж; qty-сводка."""
        out = []
        for r in rolls:
            if abs(_num(r.get("w")) - rw) > 1e-9:
                continue
            rl = _num(r.get("l"))
            cost = r.get("cost")
            if rl is None or cost is None or rl <= 0:
                continue
            qty = max(1, math.ceil(l / rl))
            out.append({"roll": r, "dw": abs(rw - w), "qty": qty,
                        "cost_total": round(float(cost) * qty, 2)})
        return out

    def spec(t):
        s = 0
        d, la = t["roll"].get("dens"), t["roll"].get("lay")
        if grams is not None and d is not None:
            s += int(abs(float(d) - grams) <= 0.5)
        if layers is not None and la is not None:
            s += int(int(la) == int(layers))
        return s

    def pick(cands, mode):
        if not cands:
            return None
        top = max(spec(c) for c in cands)
        pool = [c for c in cands if spec(c) == top]
        best = min(pool, key=lambda t: (t["cost_total"], t["qty"],
                                        t["dw"], str(t["roll"]["article"])))
        return _answer(best, w, l, grams, layers, price, mode)

    # ЯРУС-1: первый класс ширины, что тянет метраж в ≤ QCAP рулонов
    for rw in ranked:
        ok = [c for c in build(rw) if c["qty"] <= QCAP]
        if ok:
            mode = "same-width" if abs(rw - w) <= NOM else "nearest-width"
            return pick(ok, mode)
    # фолбэк: ни один класс не тянет ≤ QCAP → ближайший класс без капа (честная нарезка)
    return pick(build(ranked[0]), "unbounded")


def _answer(sel, w, l, grams, layers, price, mode="same-width"):
    roll, qty, cost_total = sel["roll"], sel["qty"], sel["cost_total"]
    rw, rl = roll["w"], roll["l"]
    card_price = None if price is None else round(float(price), 2)
    profit = None if card_price is None else round(card_price - cost_total, 2)
    exact = abs(rw - w) < 1e-6 and abs(rl - l) < 1e-6 and qty == 1
    tag = "exact" if exact else "near"
    unprof = card_price is not None and profit < 0
    parts = []
    if mode == "same-width":
        parts.append(f"та же ширина {w}м")
    elif mode == "nearest-width":
        parts.append(f"нет класса ширины {w}м → ближайшая ширина {rw}м")
    else:
        parts.append(f"ни один класс не тянет ≤{QCAP} рулонов → честная нарезка {rw}м")
    if exact:
        parts.append(f"точный {w}×{l}м → {roll['article']}")
    else:
        parts.append(f"ближайший похожий {roll['article']} "
                     f"({rw}×{rl}м, {roll.get('dens') or '?'}г/{roll.get('lay') or '?'}сл)")
    if qty > 1:
        parts.append(f"{qty}× рулона на метраж {l}м")
    parts.append(f"закупка {cost_total}₽")
    if card_price is not None:
        parts.append(f"цена {card_price}₽, профит {profit}₽")
    if unprof:
        parts.append("⚠ УБЫТОК")
    return {
        "article": roll["article"],
        "url": roll["url"],
        "roll": {"w": rw, "l": rl, "dens": roll.get("dens"), "lay": roll.get("lay"), "cost": roll.get("cost")},
        "tag": tag,
        "mode": mode,
        "qty": qty,
        "cost_total": cost_total,
        "card_price": card_price,
        "profit": profit,
        "unprofitable": bool(unprof),
        "reason": "; ".join(parts),
    }


def bind_library(records, rolls=None):
    """dry: записи → {'ok': {article: anchor}, 'blocks': [...], 'stats': {...}}."""
    rolls = list(rolls or load_donor_rolls())
    ok, blocks = {}, []
    stat = collections.Counter()
    for rec in records:
        sz = rec.get("size") or {}
        w, l = _num(sz.get("w_m")), _num(sz.get("l_m"))
        if w is None or l is None:
            blocks.append({"article": rec.get("article"), "reason": "нет size"})
            continue
        a = anchor_for(w, l, rec.get("grams"), rec.get("layers"), rec.get("price"), rolls)
        if not a:
            blocks.append({"article": rec.get("article"), "reason": "канон пуст / нет цены донора"})
            continue
        ok[str(rec.get("article"))] = a
        stat[a["tag"]] += 1
        if a["unprofitable"]:
            stat["unprofitable"] += 1
    return {"ok": ok, "blocks": blocks, "stats": dict(stat), "rolls_count": len(rolls)}


def _load_library():
    lib_path = Path(__import__("os").environ.get(
        "OZON_FILM_LIBRARY_PATH", RUNTIME / "library-2026-09-08.json"))
    doc = json.loads(Path(lib_path).read_text(encoding="utf-8"))
    recs = doc if isinstance(doc, list) else doc.get("records", doc)
    return recs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--anchor", action="store_true")
    ap.add_argument("--rolls", action="store_true")
    args = ap.parse_args(argv)
    if args.scan:
        rolls = scan_donor_rolls()
        path = write_donor_rolls(rolls)
        print(f"сканировано рулонов: {len(rolls)} → {path}")
        for r in rolls:
            print(f"  {r['article']}  {r['w']}×{r['l']}м  {r['dens']}г/{r['lay']}сл  cost={r['cost']}")
        return 0
    if args.rolls:
        rolls = load_donor_rolls()
        print(f"канон рулонов: {len(rolls)}")
        for r in rolls:
            print(f"  {r['article']}  {r['w']}×{r['l']}м  {r['dens']}г/{r['lay']}сл  cost={r['cost']}")
        return 0
    if args.anchor:
        recs = _load_library()
        res = bind_library(recs)
        out = f"{RUNTIME}/donor-anchor-{_dt.date.today():%Y-%m-%d}.json"
        Path(out).write_text(json.dumps({**res, "total": len(recs)}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"dry-привязка: {res['rolls_count']} рулонов канона, {len(res['ok'])} связаны, {len(res['blocks'])} без size")
        print("stats:", res["stats"])
        print("artifact:", out)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

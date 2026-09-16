#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · КОРОБКИ · СПИСКИ НА ПРАВКУ (read-only, 0₽): габариты «не по рынку» · донор неясен · комплекты.

Оператор 09-15: «будь готов редактировать товары. Дай список артикулов, которые имеют размеры
не по рынку, либо донор неясен… также список, где продаём комплекты от 5 шт».

Отвечает тремя списками на ЖИВОМ факте кабинета (кабинет пиннится на Express Box …8715):
  1) ГАБАРИТ НЕ ПО РЫНКУ — живые карточки, у которых depth×width×height ≠ честный склад дона.
     Живой габарит читается /v4/product/info/attributes (манифест — это что ОТПРАВИЛИ, кабинет —
     что СТОИТ; сверять надо кабинет). Делится на:
       1a. ПРАВКА ВОЗМОЖНА — дон-физика есть, честный склад выводится;
       1b. ПРАВКИ НЕТ — донор отдал объём СОБРАННОГО короба либо у его карточки нет веса/объёма.
  2) ДОНОР НЕЯСЕН — HELD (физики нет) + «сшито-близко» (донор совпал с допуском ±30 мм, не точно).
  3) КОМПЛЕКТЫ ≥ 5 шт — что продаём партией (от неё зависит и связка посылки, и выкуп).

Ничего наружу не пишет. Артефакты: korobki_EDIT_LISTS_<DATE>.{json,md} + три .txt-списка.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
RUNTIME = HERE / "runtime" / "ozon_boxes"
DATE = date.today().isoformat()

LIB = RUNTIME / "pour-library-korobki.json"
BOX_ACCOUNT, BOX_CLIENT_TAIL = "box", "8715"
ATTRS_PATH = "/v4/product/info/attributes"

# Кол-во в партии. «N шт» — не единственная форма: донорские имена пишут «Комплект N»,
# «набор N», «- 50ш», «(30 шт)». Берём МАКСИМУМ по всем формам: имя «70х70х60 100 штук» даёт 100,
# а не 70 из габарита. Ложных срабатываний не боимся — рядом печатаем имя для глаза оператора.
_QTY_PATTERNS = (
    re.compile(r"(\d+)\s*(?:шт|штук|ш\.)", re.IGNORECASE),
    re.compile(r"комплект\s*(\d+)", re.IGNORECASE),
    re.compile(r"набор\s*(\d+)", re.IGNORECASE),
)


def qty_of(name):
    """"… 100 штук" / "Комплект 2" / "набор 5" → N. Ничего не нашлось → 1 (одна коробка)."""
    s = str(name)
    found = [int(m.group(1)) for p in _QTY_PATTERNS for m in p.finditer(s)]
    return max(found) if found else 1


def _latest(pattern):
    hits = sorted(RUNTIME.glob(pattern))
    return hits[-1] if hits else None


def read_live(offer_ids):
    """Живые габариты/вес кабинета → {oid: {...}}. Кабинет пинится; чужой Client-Id → отказ."""
    import ozon_hands_write_v1 as W
    os.environ["OZON_ACCOUNT"] = BOX_ACCOUNT
    W._ensure_env()
    cid, _ = W._account_creds()
    tail = str(cid or "").strip()[-4:] or None
    if tail != BOX_CLIENT_TAIL:
        raise RuntimeError(f"кабинет …{tail} ≠ Express Box …{BOX_CLIENT_TAIL} — чтение/правка отменены")
    out = {}
    for i in range(0, len(offer_ids), 100):
        d = W._request("POST", ATTRS_PATH,
                       body={"filter": {"offer_id": offer_ids[i:i + 100], "visibility": "ALL"},
                             "limit": 1000}, timeout=60)
        for it in (d.get("result") or []):
            out[str(it["offer_id"])] = {
                "depth": it.get("depth"), "width": it.get("width"), "height": it.get("height"),
                "weight": it.get("weight"), "name": it.get("name"), "product_id": it.get("id"),
                "sku": it.get("sku"), "dci": it.get("description_category_id"),
                "type_id": it.get("type_id"),
            }
    return out, tail


def build():
    lib = json.loads(LIB.read_text(encoding="utf-8"))
    live_ids = list(lib)
    fold_path = _latest("korobki_FOLDED_*.items.json")
    rep_path = _latest("korobki_FOLDED_*.json")
    fold = json.loads(fold_path.read_text(encoding="utf-8"))
    rep = json.loads(rep_path.read_text(encoding="utf-8"))
    items = {i["offer_id"]: i for i in fold["items"]}
    metas = {m["art"]: m for m in fold["metas"]}
    held = {h["art"]: h for h in rep["held_list"]}

    live, tail = read_live(live_ids)
    missing = [o for o in live_ids if o not in live]

    edit, nofix = [], []
    for oid in sorted(live):
        v, m = live[oid], metas.get(oid)
        cur = (v["depth"], v["width"], v["height"])
        if m:                                            # честный склад дона есть
            new = (m["folded"]["depth"], m["folded"]["width"], m["folded"]["height"])
            if cur != new:
                edit.append({"art": oid, "name": v["name"], "qty": qty_of(v["name"]),
                             "was": {"d": cur[0], "w": cur[1], "h": cur[2], "weight": v["weight"]},
                             "now": {"d": new[0], "w": new[1], "h": new[2],
                                     "weight": m["folded"]["weight"]},
                             "weight_was_g": v["weight"], "weight_now_g": m["folded"]["weight"],
                             "donor_pid": m.get("donor_pid"), "donor_status": m.get("donor_status"),
                             "single_t_mm": m["folded"]["single_t_mm"],
                             "single_weight_g": m["folded"]["single_weight_g"],
                             "product_id": v.get("product_id")})
        else:
            h = held.get(oid)
            nofix.append({"art": oid, "name": v["name"], "qty": qty_of(v["name"]),
                          "was": {"d": cur[0], "w": cur[1], "h": cur[2], "weight": v["weight"]},
                          "reason": (h or {}).get("reason", "нет в HELD-списке"),
                          "donor_pid": (h or {}).get("donor_pid"),
                          "product_id": v.get("product_id")})

    # 2) донор неясен: HELD (нет физики) + «сшито-близко» (±30 мм, не точное совпадение)
    near = [{"art": r["art"], "name": r["name"], "qty": r.get("qty"),
             "donor_pid": (r.get("donor") or {}).get("pid"),
             "donor_dims": (r.get("donor") or {}).get("dims"),
             "donor_status": (r.get("donor") or {}).get("status"),
             "reason": r.get("reason"), "live": r["art"] in live}
            for r in json.loads((RUNTIME / "korobki_DONOR_STITCH_2026-09-10.json")
                                .read_text(encoding="utf-8"))["rows"]
            if r.get("donor") and "близко" in str(r.get("reason", ""))]
    held_list = [{"art": a, "name": h["name"], "qty": h.get("qty"), "donor_pid": h.get("donor_pid"),
                  "reason": h["reason"], "live": a in live} for a, h in sorted(held.items())]

    # 3) комплекты ≥ 5 шт
    bundles = [{"art": a, "name": m["name"], "qty": m["qty"], "live": a in live,
                "dims": (items[a]["depth"], items[a]["width"], items[a]["height"]),
                "weight_g": items[a]["weight"]}
               for a, m in metas.items() if m["qty"] >= 5]
    bundles.sort(key=lambda b: (-b["qty"], b["art"]))

    return {"live": live, "live_tail": tail, "missing": missing, "edit": edit, "nofix": nofix,
            "held": held_list, "near": near, "bundles": bundles,
            "src": {"folded": fold_path.name, "report": rep_path.name},
            "qty_suspect": [{"art": a, "name": m["name"]} for a, m in metas.items()
                            if m["qty"] == 1 and re.search(r"\d+\s*(?:шт|штук|комплект|набор)",
                                                           str(m["name"]), re.IGNORECASE)]}


def _write_txt(path, title, rows, fmt):
    L = [f"# {title}", f"# коробки · {DATE} · кабинет Express Box …8715", ""]
    L += [fmt(r) for r in rows]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Списки коробок на правку (read-only, 0₽).")
    ap.add_argument("--live-only", action="store_true", help="перечитать габариты из кабинета (0₽)")
    ap.parse_args(argv)

    d = build()
    e, nf, hl, nr, bn = d["edit"], d["nofix"], d["held"], d["near"], d["bundles"]
    print(f"[кабинет] Client-Id …{d['live_tail']} · живых прочитано {len(d['live'])}"
          + (f" · НЕ вернулось {len(d['missing'])}" if d["missing"] else ""))
    print(f"[вход] {d['src']['folded']}")
    print(f"\n1) ГАБАРИТ НЕ ПО РЫНКУ · всего {len(e) + len(nf)} живых карточек")
    print(f"   1a. правка возможна (честный склад дона есть): {len(e)}")
    print(f"   1b. правки нет (донор неясен):                 {len(nf)}")
    print(f"\n2) ДОНОР НЕЯСЕН · нет физики {len(hl)} · «близко» ±30мм {len(nr)}")
    c = Counter("объём собранного" if "СОБРАННОГО" in h["reason"] else "нет веса/объёма" for h in hl)
    print(f"   нет физики по причине: {dict(c)}")
    print(f"\n3) КОМПЛЕКТЫ ≥ 5 шт: {len(bn)} (живых {sum(1 for b in bn if b['live'])}) · "
          f"макс партия {bn[0]['qty'] if bn else 0} шт")
    print(f"   подозрительные (в имени есть «шт», а распозналось 1): {len(d['qty_suspect'])}")

    out = {"date": DATE, "account": "box", "client_tail": d["live_tail"], "src": d["src"],
           "counts": {"live": len(d["live"]), "edit": len(e), "nofix": len(nf),
                      "held": len(hl), "near": len(nr), "bundles": len(bn)},
           "edit": e, "nofix": nf, "held": hl, "near": nr, "bundles": bn,
           "qty_suspect": d["qty_suspect"]}
    (RUNTIME / f"korobki_EDIT_LISTS_{DATE}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    _write_txt(RUNTIME / f"korobki_EDIT_{DATE}.txt",
               f"НА ПРАВКУ: габарит ≠ честный склад дона · {len(e)}",
               e, lambda r: f"{r['art']}\t{r['qty']} шт\t{r['was']['d']}×{r['was']['w']}×{r['was']['h']}"
                            f"\t→ {r['now']['d']}×{r['now']['w']}×{r['now']['h']}"
                            f"\tвес {r['weight_was_g']}→{r['weight_now_g']} г\tдон {r['donor_pid']}\t{r['name']}")
    _write_txt(RUNTIME / f"korobki_NOFIX_{DATE}.txt",
               f"ЖИВЫЕ БЕЗ ПРАВКИ: донор неясен · {len(nf)}",
               nf, lambda r: f"{r['art']}\t{r['was']['d']}×{r['was']['w']}×{r['was']['h']}"
                             f"\tдон {r.get('donor_pid') or '—'}\t{r['reason']}\t{r['name']}")
    _write_txt(RUNTIME / f"korobki_DONOR_UNCLEAR_{DATE}.txt",
               f"ДОНОР НЕЯСЕН: нет физики {len(hl)} + близко ±30мм {len(nr)}",
               hl + nr, lambda r: f"{r['art']}\t{'ЖИВ' if r['live'] else 'новый'}"
                                  f"\tдон {r.get('donor_pid') or '—'}\t{r['reason']}\t{r['name']}")
    _write_txt(RUNTIME / f"korobki_BUNDLES_{DATE}.txt",
               f"КОМПЛЕКТЫ ≥ 5 шт · {len(bn)}",
               bn, lambda r: f"{r['art']}\t×{r['qty']}\t{'ЖИВ' if r['live'] else 'новый'}"
                             f"\t{r['dims'][0]}×{r['dims'][1]}×{r['dims'][2]} мм / {r['weight_g']} г\t{r['name']}")
    print(f"\nартефакты: korobki_EDIT_LISTS_{DATE}.json + EDIT / NOFIX / DONOR_UNCLEAR / BUNDLES .txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

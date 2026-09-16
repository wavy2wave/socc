#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OZON плёнка: СВЕРКА «библиотека ⇄ донор» на движке ПРОФИТ-ЯКОРЯ (width-primary).

Dry (0₽). НИЧЕГО не мутирует. Для каждой записи library (pour_flag или нет) считает
anchor_for() новым движком (озон_donor_anchor_v1) и сравнивает с тем, что СЕЙЧАС лежит
в donor_link у записи:
  kept   — якорь совпал с текущим donor_link.article (нечего менять)
  changed — якорь другой (движок ширины-первой заменяет старое решение)
  new    — у записи не было donor_link, якорь назначен
  unbound — якоря нет (канон пуст / нет size / нет цены донора)

Сверка ширины и материала в каждой строке (что меняем и ПОЧЕМУ):
  w_jump  — класс ширины донора ≠ ширины карточки (|Δw|>NOM) → reason говорит «ближайшая»
  w_keep  — класс ширины совпал (|Δw|≤NOM)
  mat_same — граммы/слои совпали (ярус-2), mat_drift — донор другой плотности/слоёв,
            mat_unknown — в карточке нет граммов/слоёв (ярус-2 нечего сверять)

ПРОФИТ всегда под капотом (профит-закон оператора): card_price − cost_total; убыточный
выбор не молчит → unprofitable=True в строке и в summary.

Артефакт: runtime/ozon-library/donor-reconcile-{date}.json
CLI: python3 ozon_donor_reconcile_v1.py [--date YYYY-MM-DD]
"""
import argparse
import collections
import datetime as _dt
import json
import sys
from pathlib import Path

import ozon_donor_anchor_v1 as A

RUNTIME = Path(__file__).resolve().parent / "runtime" / "ozon-library"


def _num(x):
    return A._num(x)


def reconcile(records, rolls=None, date=None):
    """→ dict(канон, summary, rows) — rows это сверка по каждой записи."""
    date = date or f"{_dt.date.today():%Y-%m-%d}"
    rolls = list(rolls or A.load_donor_rolls())
    res = A.bind_library(records, rolls)
    anchors = res["ok"]
    blocks = {b["article"]: b["reason"] for b in res["blocks"]}

    sum_k = collections.Counter()          # kept/changed/new/unbound
    tag_k = collections.Counter()          # exact/near по якорям
    jump_k = collections.Counter()         # same-width/nearest-width/unbounded
    mat_k = collections.Counter()          # mat_same/mat_drift/mat_unknown
    sum_cost = collections.Counter()       # закупка kept vs changed
    rows = []

    for rec in records:
        art = str(rec.get("article"))
        sz = rec.get("size") or {}
        w, l = _num(sz.get("w_m")), _num(sz.get("l_m"))
        grams, layers, price = rec.get("grams"), rec.get("layers"), rec.get("price")
        dl = rec.get("donor_link") or {}
        old = str(dl.get("article")) if dl.get("article") else None

        a = anchors.get(art)
        if not a:
            sum_k["unbound"] += 1
            rows.append(dict(article=art, w=w, l=l, grams=grams, layers=layers,
                             price=price, old_article=old, anchor=None,
                             tag=None, mode=None, qty=None, cost_total=None,
                             card_price=price, profit=None, unprofitable=False,
                             keep=None, w_keep=None, mat=mat_unk(grams, layers),
                             reason=blocks.get(art)))
            continue

        keep = (old == a["article"]) if old else False
        kind = "kept" if keep else ("changed" if old else "new")
        sum_k[kind] += 1
        tag_k[a["tag"]] += 1
        jump_k[a["mode"]] += 1
        if a["mode"] == "same-width":
            wkeep = True
        elif a["mode"] == "nearest-width":
            wkeep = False
        else:
            wkeep = False
        mat = mat_of(rec, a["roll"])
        mat_k[mat] += 1
        sum_cost["all"] += a["cost_total"]
        sum_cost[kind] += a["cost_total"]
        if a["unprofitable"]:
            sum_k["unprofitable"] += 1

        rows.append(dict(
            article=art, w=w, l=l, grams=grams, layers=layers, price=price,
            old_article=old, anchor=a["article"], tag=a["tag"], mode=a["mode"],
            qty=a["qty"], cost_total=a["cost_total"], card_price=a["card_price"],
            profit=a["profit"], unprofitable=a["unprofitable"], keep=keep,
            w_keep=wkeep, mat=mat, reason=a["reason"],
        ))

    summary = dict(
        poured=len(anchors),
        total=len(records),
        kept=sum_k["kept"], changed=sum_k["changed"], new=sum_k["new"],
        unbound=sum_k["unbound"], unprofitable=sum_k["unprofitable"],
        exact=tag_k["exact"], near=tag_k["near"],
        modes=dict(jump_k), width_keep=sum(r.get("w_keep") for r in rows if r.get("w_keep") is not None),
        mat=dict(mat_k),
        cost_total=dict(sum_cost),   # kept/changed/new/all — где меняем, столько закупки
    )
    return dict(generated=date, dry=True,
                canon=dict(rolls=len(rolls), file=f"donor-rolls-{date}.json"),
                summary=summary, rows=rows)


def mat_unk(grams, layers):
    if grams is None and layers is None:
        return "mat_unknown"
    return "mat_maybe"


def mat_of(rec, roll):
    grams, layers = rec.get("grams"), rec.get("layers")
    if grams is None and layers is None:
        return "mat_unknown"
    d, la = roll.get("dens"), roll.get("lay")
    same = True
    if grams is not None and d is not None:
        same = same and abs(float(d) - float(grams)) <= 0.5
    if layers is not None and la is not None:
        same = same and int(la) == int(layers)
    return "mat_same" if same else "mat_drift"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=f"{_dt.date.today():%Y-%m-%d}")
    ap.add_argument("--rolls", default=None, help="путь к канону рулонов (дефолт donor-rolls-{date}.json)")
    args = ap.parse_args(argv)
    lib_path = RUNTIME / "library-2026-09-08.json"
    doc = json.loads(lib_path.read_text(encoding="utf-8"))
    recs = doc if isinstance(doc, list) else doc.get("records", doc)
    rolls = A.load_donor_rolls(args.rolls or (RUNTIME / f"donor-rolls-{args.date}.json"))
    out = reconcile(recs, rolls=rolls, date=args.date)
    path = RUNTIME / f"donor-reconcile-{args.date}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    s = out["summary"]
    print(f"сверка {s['total']} записей, канон {out['canon']['rolls']} рулонов")
    print(f"  связаны: {s['poured']} | kept {s['kept']} / changed {s['changed']} / new {s['new']} / unbound {s['unbound']}")
    print(f"  exact {s['exact']} near {s['near']} | width_keep {s['width_keep']} | unprofitable {s['unprofitable']}")
    print("  modes:", s["modes"], "| mat:", s["mat"])
    print("  cost_total по видам:", s["cost_total"])
    print("artifact:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН плёнка: ПУПОВИНА-мутация библиотеки (donor_article + точный donor_link).

ВЫПОЛНЯЕТСЯ ТОЛЬКО ПО СЛОВУ ОПЕРАТОРА (09.09: «да» на доктрину ширины + 9601513-один-рулон
+ мутацию). Мутирует runtime/ozon-library/library-2026-09-08.json IN-PLACE:

  • для каждой записи, у которой есть якорь (движок ПРОФИТ-ЯКОРЯ), проставляет
    donor_article = article якоря и ПЕРЕписывает donor_link = {article,url,near,source}
    + мета ПРОФИТА (w,l,qty,cost_total,card_price,profit,unprofitable) — «видишь профит
    по конкретному товару сразу».
  • pour_flag/pour_state/price/name/size — НЕ трогаем (только связку донора).
  • записи без size (147) — не литьё, оставляем как есть.
  • АТОМАРНО: пишем во временный файл → rename. Бэкап .bak-{ts} рядом.

Dry по умолчанию (--dry печатает план: сколько kept/changed/new). Живой — только --commit
(не dry) — это и есть слово оператора, второй гейт файл не имеет.
Вердикт: нечётный исход → rc=1, файл НЕ тронут (мы ничего не мутируем, пока план не сошёлся).
"""
import argparse
import datetime as _dt
import json
import shutil
import sys
from pathlib import Path

import ozon_donor_anchor_v1 as A

RUNTIME = Path(__file__).resolve().parent / "runtime" / "ozon-library"
LIB_PATH = RUNTIME / "library-2026-09-08.json"
ROLLS_PATH = RUNTIME / "donor-rolls-2026-09-09.json"
DATE = "2026-09-09"
SRC = "anchor-v1"


def mutate(records, rolls, dry=True):
    """→ {'ok': bool, 'summary': {...}, 'rows': [...]} — печатает план, мутирует только если not dry."""
    anchors = A.bind_library(records, rolls)["ok"]
    stat = {"kept": 0, "changed": 0, "new": 0, "unbound": 0, "no_size": 0,
            "unprofitable": 0}
    rows = []
    for rec in records:
        art = str(rec.get("article"))
        a = anchors.get(art)
        if not a:
            stat["no_size" if not ((rec.get("size") or {}).get("w_m")) else "unbound"] += 1
            rows.append({"article": art, "action": "unchanged",
                         "why": "нет якоря (нет size или канон пуст)"})
            continue
        old = (rec.get("donor_link") or {}).get("article")
        if old == a["article"]:
            action, stat_k = "kept", "kept"
        elif old:
            action, stat_k = "changed", "changed"
        else:
            action, stat_k = "new", "new"
        stat[stat_k] += 1
        if a["unprofitable"]:
            stat["unprofitable"] += 1
        rows.append({
            "article": art, "action": action,
            "old_article": old, "anchor": a["article"],
            "w": a["roll"]["w"], "l": a["roll"]["l"],
            "qty": a["qty"], "cost_total": a["cost_total"],
            "card_price": a["card_price"], "profit": a["profit"],
            "unprofitable": a["unprofitable"], "mode": a["mode"],
        })
        if dry:
            continue
        dl = {
            "article": a["article"],
            "url": f"https://shop.cargo-avto.ru/catalog/{a['article']}/",
            "near": a["tag"] != "exact",
            "source": SRC,
            "w": a["roll"]["w"], "l": a["roll"]["l"],
            "qty": a["qty"], "cost_total": a["cost_total"],
            "card_price": a["card_price"], "profit": a["profit"],
            "unprofitable": a["unprofitable"],
            "mode": a["mode"],
        }
        rec["donor_article"] = a["article"]
        rec["donor_link"] = dl
    stat["bound"] = stat["kept"] + stat["changed"] + stat["new"]
    return {"ok": not stat["unprofitable"], "summary": stat, "rows": rows}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", default=False,
                    help="печать плана (kept/changed/new), НЕ мутирует")
    ap.add_argument("--commit", action="store_true", default=False,
                    help="ЖИВЬЁ: применить мутацию (второй гейт — слово оператора вне файла)")
    args = ap.parse_args(argv)

    doc = json.loads(LIB_PATH.read_text(encoding="utf-8"))
    recs = doc if isinstance(doc, list) else doc.get("records", doc)
    rolls = A.load_donor_rolls(ROLLS_PATH)
    dry = not args.commit

    plan = mutate(recs, rolls, dry=dry)
    s = plan["summary"]
    print(f"ПУПОВИНА-мутация {LIB_PATH} · {'DRY план' if dry else 'ЖИВЬЁ (слово дано)'}")
    print(f"  связаны {s['bound']} · kept {s['kept']} / changed {s['changed']} / new {s['new']}"
          f" · без якоря {s['no_size'] + s['unbound']} · убыточных {s['unprofitable']}")
    if s["unprofitable"]:
        print("  ⚠ ЕСТЬ УБЫТОЧНЫЕ — мутация НЕ применяется (профит-закон), проверь план")
        for r in plan["rows"]:
            if r.get("unprofitable"):
                print(f"    {r['article']} → {r['anchor']} cost {r['cost_total']} > price {r['card_price']}")
        return 1
    if dry:
        print("  (сухо — файл не тронут; --commit применяет)")
        return 0

    # ЖИВЬЁ: бэкап + атомарная запись
    bak = LIB_PATH.with_name(LIB_PATH.name + f".bak-{_dt.datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(LIB_PATH, bak)
    tmp = LIB_PATH.with_name(LIB_PATH.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(LIB_PATH)
    print(f"  бэкап: {bak.name}")
    print(f"  записано атомарно: {LIB_PATH}")
    # проверка чтением
    chk = json.loads(LIB_PATH.read_text(encoding="utf-8"))
    chk_recs = chk if isinstance(chk, list) else chk.get("records", chk)
    ok_link = sum(1 for r in chk_recs if (r.get("donor_link") or {}).get("article"))
    ok_art = sum(1 for r in chk_recs if r.get("donor_article"))
    print(f"  проверка чтением: donor_link у {ok_link}, donor_article у {ok_art}")
    if ok_link != s["bound"] or ok_art != s["bound"]:
        print("  ⚠ РАСХОЖДЕНИЕ после записи — читай файл, не молчи")
        return 1
    print("  ОК")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OZON плёнка: ЧЕСТНЫЙ вердикт связки «файловая строка 844 → живой донор».

Dry (0₽). НИЧЕГО не мутирует: строит донор-канон (48 живьём-проверенных рулонов
shop.cargo-avto.ru), резолвит каждую запись library-2026-09-08.json и пишет вердикт
в runtime/ozon-library/donor-linkage-verdict-2026-09-09.json. Сверяет текущие
donor_link (685) против честного.

Честная модель (решение #38): семейство донора = (ширина w, плотность г/м², слои).
Файловая строка связывается ТОЛЬКО если её длина ≤ max-длины рулона семейства.
  exact  = у донора есть рулон ровно file-длины, семейство совпало.
  recut  = у донора рулон длиннее file-длины (нарезка), семейство совпало.
  too-long = семейство есть, но file-длина больше самого длинного рулона донора.
  ambig  = ≥2 семейства на ширине, а плотность/слои записи не различают.
  no-family = ширина есть у донора, но (dens,lay) такого семейства нет.
  no-width  = ширины file вообще нет у донора (напр. 0.2/0.45/0.55/1.3).
  no-size  = в записи нет size.w_m/l_m.
"""
import collections, json, re, sys

DONOR_HOST = "https://shop.cargo-avto.ru"
LIB_PATH = "runtime/ozon-library/library-2026-09-08.json"
OUT_PATH = "runtime/ozon-library/donor-linkage-verdict-2026-09-09.json"

# (article, w_м, l_м, dens г/м², layers)  — ЖИВЬЁМ проверено (grid + card-live master extras)
LIVE = [
    ("9602037", 0.3, 50, 60, 3), ("9601512", 0.3, 50, 40, 2), ("9601516", 0.3, 100, 60, 3),
    ("9601513", 0.3, 100, 40, 2), ("9605412", 0.3, 100, 25, 2), ("9602694", 0.4, 2, 55, 2),
    ("9600155", 0.4, 5, 55, 2), ("9604685", 0.5, 50, 40, 2), ("9604686", 0.5, 50, 60, 3),
    ("9605413", 0.5, 100, 25, 2), ("9601114", 0.6, 50, 40, 2), ("9601120", 0.6, 50, 60, 3),
    ("9603855", 0.6, 50, 40, 2), ("9604903", 0.6, 50, 60, 3), ("9601115", 0.6, 100, 40, 2),
    ("9601121", 0.6, 100, 60, 3), ("9605392", 0.75, 100, 25, 2), ("9603273", 1.2, 5, 55, 2),
    ("9600094", 1.2, 10, 55, 2), ("9604816", 1.2, 20, 40, 2), ("9601395", 1.2, 25, 90, 2),
    ("9600233", 1.2, 25, 130, 3), ("9600513", 1.2, 50, 40, 2), ("9602489", 1.2, 50, 30, 2),
    ("9600879", 1.2, 50, 60, 3), ("9600239", 1.2, 100, 40, 2), ("9602490", 1.2, 100, 30, 2),
    ("9600892", 1.2, 100, 60, 3), ("9600318", 1.5, 25, 90, 2), ("9600911", 1.5, 25, 130, 3),
    ("9602472", 1.5, 50, 30, 2), ("9600073", 1.5, 50, 40, 2), ("9600940", 1.5, 50, 60, 3),
    ("9602473", 1.5, 100, 30, 2), ("9600092", 1.5, 100, 40, 2), ("9604687", 1.5, 100, 40, 2),
    ("9604688", 1.5, 100, 60, 3), ("9605414", 1.5, 100, 25, 2), ("9600899", 1.5, 100, 60, 3),
]
# мастер-экстры, проверены карточкой живьём на shop-хосте (sp-хост глючит: 9600094)
EXTRAS = [
    ("9601515", 0.3, 50, 60, 3), ("9604815", 0.3, 20, 40, 2), ("9605336", 0.5, 20, 40, 2),
    ("9604033", 0.5, 50, 40, 2), ("9604035", 0.5, 50, 60, 3), ("9604036", 0.5, 100, 60, 3),
    ("9602468", 0.5, 100, 40, 2), ("9601440", 1.2, 50, 90, 2), ("9600154", 1.2, 50, 130, 3),
]

BUCKETS = "exact recut too-long ambig no-width no-family no-size".split()
_WORD_LAY = {"одно": 1, "двух": 2, "трех": 3, "трёх": 3, "четырёх": 4, "пяти": 5}


def g_layers(name):
    m = re.search(r"(одно|двух|трех|трёх|четырёх|пяти)-?слой", (name or "").lower())
    return _WORD_LAY[m.group(1)] if m else None


def g_dens(name):
    m = re.search(r"(\d{2,3})\s*г/м", (name or "").lower())
    return int(m.group(1)) if m else None


def g_num(x):
    try:
        return round(float(str(x).replace(",", ".")), 2)
    except Exception:
        return None


def build_supply():
    fam = collections.defaultdict(list)
    grid_arts = {a for a, *_ in LIVE}
    byw = collections.defaultdict(list)
    for art, w, l, d, la in LIVE + EXTRAS:
        v = dict(article=art, url=f"{DONOR_HOST}/catalog/{art}/", w=w, l=float(l), dens=d, lay=la,
                 src="grid" if art in grid_arts else "card-live")
        fam[(w, d, la)].append(v)
    for k in fam:
        byw[k[0]].append(k)
    maxlen = {k: max(v["l"] for v in vals) for k, vals in fam.items()}
    return fam, byw, maxlen


def resolve(rec, byw, maxlen, fam):
    """→ (bucket, honest_article|None, reason|None)"""
    sz = rec.get("size") or {}
    w, l = g_num(sz.get("w_m")), g_num(sz.get("l_m"))
    dn = rec.get("grams")
    if dn is None:
        dn = g_dens(rec.get("name", ""))
    la = rec.get("layers")
    if la is None:
        la = g_layers(rec.get("name", ""))
    if w is None or l is None:
        return "no-size", None, "нет size.w_m/l_m в записи"
    cw = [k for k in byw if abs(k - w) <= 0.025]
    if not cw:
        return "no-width", None, f"нет ширины {w} у донора (есть {sorted(byw.keys())})"
    cfam = []
    for k in cw:
        for f in byw[k]:
            if dn is not None and abs(f[1] - dn) > 0.5:
                continue
            if la is not None and int(f[2]) != int(la):
                continue
            cfam.append(f)
    uniq = set(cfam)
    if len(uniq) > 1:
        desc = "; ".join(f"ш{w}м {dens}г/{sl}сл" for w, dens, sl in uniq)
        return "ambig", None, f"{len(uniq)} семейства ш{w} ({desc}) — запись не различает"
    if not uniq:
        return "no-family", None, f"нет семейства ш{w} с dens={dn} lay={la}"
    f = uniq.pop()
    mx = maxlen[f]
    if l > mx:
        return "too-long", None, f"файл {l}м > донор {f[1]}г/{f[2]}сл ш{w} макс {mx}м"
    cand = [v for v in fam[f] if v["l"] >= l]
    roll = min(cand, key=lambda v: v["l"])
    if roll["l"] == l:
        return "exact", roll["article"], None
    return "recut", roll["article"], None


def main():
    fam, byw, maxlen = build_supply()
    lib = json.load(open(LIB_PATH))
    recs = lib if isinstance(lib, list) else lib.get("records", lib)

    stats = collections.Counter()
    stats_p = collections.Counter()
    cur = collections.Counter()
    rows = []
    for i, rec in enumerate(recs):
        bucket, article, reason = resolve(rec, byw, maxlen, fam)
        stats[bucket] += 1
        if rec.get("pour_flag"):
            stats_p[bucket] += 1
        curdl = rec.get("donor_link")
        if curdl:
            if article and str(curdl.get("article")) == str(article):
                cur["ok"] += 1
            elif article:
                cur["wrong_link"] += 1
            else:
                cur["impossible"] += 1
        else:
            cur["absent"] += 1
        rows.append(dict(i=i, article=rec.get("article"), name=(rec.get("name", "") or "")[:70],
                         w=g_num((rec.get("size") or {}).get("w_m")), l=g_num((rec.get("size") or {}).get("l_m")),
                         dens=rec.get("grams"), lay=rec.get("layers"), pour=bool(rec.get("pour_flag")),
                         bucket=bucket, honest_article=article, reason=reason,
                         cur_article=str(curdl.get("article")) if curdl else None))

    assert sum(stats[b] for b in BUCKETS) == len(recs) == 844, dict(stats)
    assert sum(stats_p[b] for b in BUCKETS) == 697, dict(stats_p)
    hon_all = stats["exact"] + stats["recut"]
    hon_pour = stats_p["exact"] + stats_p["recut"]

    out = dict(
        generated="2026-09-09", dry=True, host=DONOR_HOST,
        supply=dict(count=len(LIVE) + len(EXTRAS), widths=sorted(byw.keys()),
                    families={f"{k[0]}x{maxlen[k]}м@{k[1]}г/{k[2]}сл": sorted(v["article"] for v in fam[k])
                              for k in sorted(fam)}),
        verdict=dict(total=len(recs), poured=697,
                     buckets={b: dict(all=stats[b], poured=stats_p[b]) for b in BUCKETS},
                     honest_bindable=dict(all=hon_all, poured=hon_pour),
                     current_donor_link_health=dict(cur)),
        rows=rows,
    )
    json.dump(out, open(OUT_PATH, "w"), ensure_ascii=False, indent=1)
    print("supply families:", len(fam), "rolls:", len(LIVE) + len(EXTRAS))
    print("widths у донора:", sorted(byw.keys()))
    for b in BUCKETS:
        print(f"  {b:9s} all={stats[b]:4d} poured={stats_p[b]:4d}")
    print(f"honest-bindable: all={hon_all} poured={hon_pour}")
    print("current donor_link health:", dict(cur))
    print("artifact:", OUT_PATH)


if __name__ == "__main__":
    sys.exit(main())

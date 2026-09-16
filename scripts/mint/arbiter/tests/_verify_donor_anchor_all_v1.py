#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adversarial verify: EVERY donor-anchored record in the (mutated) library points at the
SAME donor roll the anchor engine (ozon_donor_anchor_v1.anchor_for) would choose RIGHT NOW.

Checks per record (all 844):
  * HAS donor_article (697):  re-run anchor_for(size.w_m, size.l_m, grams, layers, price, rolls)
    assert donor_link.article == anchor.article,
           donor_link.w/l     == anchor.roll.w/l,
           donor_link.qty     == anchor.qty,
           donor_link.url     == f"https://shop.cargo-avto.ru/catalog/{article}/",
           donor_link.near    == (anchor.tag != 'exact').
  * NO donor_article (147):   anchor must be None (no size path) — unbound stays unbound.

Counts everything. Reports each concrete violation.
"""
import json
import sys
import math
from pathlib import Path

ROOT = Path("/Users/wavysexy/SOCC/scripts/mint/arbiter")
sys.path.insert(0, str(ROOT))

import ozon_donor_anchor_v1 as anchor_v1  # noqa: E402

LIB = ROOT / "runtime" / "ozon-library" / "library-2026-09-08.json"
ROLLS = ROOT / "runtime" / "ozon-library" / "donor-rolls-2026-09-09.json"

lib = json.loads(LIB.read_text(encoding="utf-8"))
recs = lib["records"] if isinstance(lib, dict) else lib
rolls_doc = json.loads(ROLLS.read_text(encoding="utf-8"))
rolls = rolls_doc["rolls"] if isinstance(rolls_doc, dict) else rolls_doc
print(f"records={len(recs)}  rolls={len(rolls)}")

URL_PREFIX = "https://shop.cargo-avto.ru/catalog/"
BURL_PREFIX = "https://shop.cargo-avto.ru/catalog/"


def num(x):
    try:
        return float(x)
    except Exception:
        return None


violations = []
checked = {"total": 0, "bound": 0, "unbound": 0,
           "chk_article": 0, "chk_w": 0, "chk_l": 0, "chk_qty": 0,
           "chk_url": 0, "chk_near": 0, "chk_unbound_none": 0}
tag_exact = 0
tag_near = 0

for idx, rec in enumerate(recs):
    checked["total"] += 1
    art = rec.get("article")
    sz = rec.get("size") or {}
    w, l = num(sz.get("w_m")), num(sz.get("l_m"))
    grams = rec.get("grams")
    layers = rec.get("layers")
    price = rec.get("price")
    dl = rec.get("donor_link")
    has_da = bool(rec.get("donor_article"))

    anchor = anchor_v1.anchor_for(w, l, grams, layers, price, rolls)
    where = f"#{idx} article={art} size=({w}×{l}) g={grams} lay={layers} price={price}"

    if has_da:
        checked["bound"] += 1
        if anchor is None:
            violations.append(f"BOUND-BUT-NO-ANCHOR {where} donor_article={rec.get('donor_article')} donor_link={json.dumps(dl, ensure_ascii=False)}")
            continue
        if not dl:
            violations.append(f"BOUND-BUT-NO-DONOR_LINK {where}")
            continue
        # article
        checked["chk_article"] += 1
        if str(dl.get("article")) != str(anchor["article"]):
            violations.append(f"ARTICLE-MISMATCH {where} stored={dl.get('article')} recomputed={anchor['article']}")
        # roll w/l
        aw, al = anchor["roll"]["w"], anchor["roll"]["l"]
        checked["chk_w"] += 1
        if dl.get("w") is None or num(dl.get("w")) != num(aw):
            violations.append(f"W-MISMATCH {where} stored_w={dl.get('w')} recomputed_roll_w={aw}")
        checked["chk_l"] += 1
        if dl.get("l") is None or num(dl.get("l")) != num(al):
            violations.append(f"L-MISMATCH {where} stored_l={dl.get('l')} recomputed_roll_l={al}")
        # qty
        checked["chk_qty"] += 1
        if dl.get("qty") is None or int(dl.get("qty")) != int(anchor["qty"]):
            violations.append(f"QTY-MISMATCH {where} stored_qty={dl.get('qty')} recomputed_qty={anchor['qty']}")
        # url
        checked["chk_url"] += 1
        expect_url = f"{BURL_PREFIX}{anchor['article']}/"
        if str(dl.get("url")) != expect_url:
            violations.append(f"URL-MISMATCH {where} stored_url={dl.get('url')} expected={expect_url}")
        if str(dl.get("url")) != str(anchor.get("url")):
            violations.append(f"URL-VS-ANCHOR {where} stored_url={dl.get('url')} anchor_url={anchor.get('url')}")
        # near semantics
        checked["chk_near"] += 1
        want_near = (anchor["tag"] != "exact")
        if bool(dl.get("near")) != bool(want_near):
            violations.append(f"NEAR-MISMATCH {where} stored_near={dl.get('near')} recomputed_tag={anchor['tag']} expect_near={want_near}")
        if anchor["tag"] == "exact":
            tag_exact += 1
        else:
            tag_near += 1
        # extra: mode string consistency (informational)
        if dl.get("mode") != anchor["mode"]:
            violations.append(f"MODE-MISMATCH {where} stored_mode={dl.get('mode')} recomputed_mode={anchor['mode']}")
    else:
        checked["unbound"] += 1
        checked["chk_unbound_none"] += 1
        if anchor is not None:
            violations.append(f"UNBOUND-BUT-ANCHORABLE {where} recomputed_anchor={json.dumps({k: anchor[k] for k in ('article','tag','qty','mode')}, ensure_ascii=False)}")
        if dl:
            violations.append(f"UNBOUND-BUT-HAS-DONOR_LINK {where} donor_link={json.dumps(dl, ensure_ascii=False)}")
        if rec.get("donor_article") is None and rec.get("donor_article") != "":
            pass  # donor_article falsy/absent is the definition of unbound here

print("\n===== COUNTS =====")
for k, v in checked.items():
    print(f"  {k}: {v}")
print(f"  tag_exact: {tag_exact}  tag_near: {tag_near}  (sum {tag_exact + tag_near})")
print(f"\n===== VIOLATIONS: {len(violations)} =====")
for v in violations:
    print("  " + v)
if not violations:
    print("  NONE — все {checked['bound']} привязок совпадают с тем, что выбрал бы движок сейчас; "
          f"{checked['unbound']} непривязанных остаются непривязанными.")

#!/usr/bin/env python3
"""Adversarial verification: 147 records WITHOUT donor anchor must NOT have been touched.

Pre-mutation backup: library-2026-09-08.json.bak-20260910-021012
Post-mutation live:   library-2026-09-08.json
"""
import json
import sys

ROOT = "/Users/wavysexy/SOCC/scripts/mint/arbiter/runtime/ozon-library"
BACKUP = f"{ROOT}/library-2026-09-08.json.bak-20260910-021012"
LIVE = f"{ROOT}/library-2026-09-08.json"

def load(p):
    with open(p) as fh:
        return json.load(fh)

def canon(v):
    """Deterministic canonical serialization for byte-compare."""
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

backup = load(BACKUP)
live = load(LIVE)

violations = []

# ---- Check 4: total record counts ----
assert isinstance(backup, dict) and isinstance(live, dict)
b_recs = backup["records"]
l_recs = live["records"]
if len(b_recs) != 844:
    violations.append(f"[COUNT] backup total records = {len(b_recs)}, expected 844")
if len(l_recs) != 844:
    violations.append(f"[COUNT] live total records = {len(l_recs)}, expected 844")

# Index both by article. Must be unique.
def index(recs):
    d = {}
    for r in recs:
        a = r.get("article")
        if a in d:
            violations.append(f"[DUP] duplicate article {a!r} in this library")
        d[a] = r
    return d

b_idx = index(b_recs)
l_idx = index(l_recs)

if set(b_idx) != set(l_idx):
    only_b = set(b_idx) - set(l_idx)
    only_l = set(l_idx) - set(b_idx)
    for a in sorted(only_b):
        violations.append(f"[KEYSET] article {a!r} present in backup, MISSING in live")
    for a in sorted(only_l):
        violations.append(f"[KEYSET] article {a!r} present in live, MISSING in backup")

# ---- Helper: does a live record count as UNBOUND? ----
def unbound(r):
    dl = r.get("donor_link")
    da = r.get("donor_article")
    # absent donor_link
    if dl is None:
        return True
    # absent donor_article (top-level) OR empty
    if da is None or da == "":
        return True
    # donor_link present but has no article / empty article
    if isinstance(dl, dict):
        a = dl.get("article")
        if a is None or a == "":
            return True
    return False

# ---- Check 1: count unbound ----
unbound_articles = [r["article"] for r in l_recs if unbound(r)]
unbound_articles_sorted = sorted(unbound_articles)
print(f"unbound (no donor_article / no donor_link / no nested article) = {len(unbound_articles_sorted)}")
if len(unbound_articles_sorted) != 147:
    violations.append(f"[COUNT] live unbound records = {len(unbound_articles_sorted)}, expected 147")

# ---- Check 2: unbound donor_link + donor_article identical to backup ----
for a in unbound_articles_sorted:
    lr = l_idx.get(a)
    br = b_idx.get(a)
    if br is None:
        continue  # already flagged as keyset violation
    ldl = lr.get("donor_link")
    bdl = br.get("donor_link")
    lda = lr.get("donor_article")
    bda = br.get("donor_article")
    if canon(ldl) != canon(bdl):
        violations.append(
            f"[UNBOUND-DONOR_LINK] article {a!r}: donor_link drifted\n"
            f"    backup: {canon(bdl)}\n"
            f"    live:   {canon(ldl)}"
        )
    if lda not in (None, "") or bda not in (None, ""):
        violations.append(
            f"[UNBOUND-DONOR_ARTICLE] article {a!r}: donor_article differs "
            f"backup={bda!r} live={lda!r}"
        )

# ---- Check 3: pour_flag/pour_state/price/size/name byte-identical for ALL 844 ----
FIELDS = ["pour_flag", "pour_state", "price", "size", "name"]
for a in l_recs:
    lr = a
    br = b_idx.get(lr["article"])
    if br is None:
        continue
    for f in FIELDS:
        lv = lr.get(f)
        bv = br.get(f)
        if canon(lv) != canon(bv):
            violations.append(
                f"[FIELD] article {lr['article']!r} field {f!r} drifted\n"
                f"    backup: {canon(bv)}\n"
                f"    live:   {canon(lv)}"
            )

# ---- Additional adversarial sweeps ----

# A) Any field outside donor_link/donor_article that differs at all (whole-record diff)?
for lr in l_recs:
    br = b_idx.get(lr["article"])
    if br is None:
        continue
    l_keys = set(lr.keys())
    b_keys = set(br.keys())
    # Allowed key diffs: donor_article added in live; nothing else expected.
    added = l_keys - b_keys
    removed = b_keys - l_keys
    for k in sorted(added - {"donor_article"}):
        violations.append(f"[KEY-ADDED] article {lr['article']!r} live has new key {k!r} (not donor_article)")
    for k in sorted(removed):
        violations.append(f"[KEY-REMOVED] article {lr['article']!r} live DROPPED key {k!r}")
    for k in b_keys & l_keys:
        if k in ("donor_link", "donor_article"):
            continue
        if canon(lr[k]) != canon(br[k]):
            violations.append(
                f"[FIELD] article {lr['article']!r} field {k!r} drifted\n"
                f"    backup: {canon(br[k])}\n"
                f"    live:   {canon(lr[k])}"
            )

# B) For BOUND records (697): donor fields should differ ONLY by anchor additions.
#    Verify donor_article == donor_link.article and no bound record was accidentally unbound-ish.
bound = [r for r in l_recs if not unbound(r)]
print(f"bound (with donor_article) = {len(bound)}")
if len(bound) != 697:
    violations.append(f"[COUNT] live bound records = {len(bound)}, expected 697")
for lr in bound:
    ldl = lr.get("donor_link")
    lda = lr.get("donor_article")
    if isinstance(ldl, dict) and lda is not None:
        if str(lda) != str(ldl.get("article")):
            violations.append(
                f"[BOUND-MISMATCH] article {lr['article']!r}: donor_article={lda!r} "
                f"!= donor_link.article={ldl.get('article')!r}"
            )
    # Bound records' backup donor_link must exist (should have scan) OR be newly anchored.
    # Not a violation if absent before — anchor is the mutation. But other fields inside
    # donor_link beyond anchor keys should match backup where present.

# C) Backup had 685 donor_link present; live has 697. The 12 extra are new anchors.
#    All 685 that existed in backup: which of them are now UNBOUND in live? Should be none
#    (unbound means untouched, so backup donor_link still present → still 'bound' by donor_article?
#    Wait — unbound definition uses donor_article presence. A backup record with donor_link (scan)
#    but no donor_article in live IS one of the 147 if it was never anchored.
#    Verify every live record that has donor_article also has donor_link and vice versa.)
for lr in l_recs:
    has_da = lr.get("donor_article") not in (None, "")
    has_dl = isinstance(lr.get("donor_link"), dict) and lr["donor_link"].get("article")
    if has_da and not has_dl:
        violations.append(f"[INCONSISTENT] article {lr['article']!r} has donor_article but no donor_link.article")

# D) Check live donor_link nested keys for unbound records with a dict donor_link — full equality already covers.
# E) Check donor_article is a scalar string, not a dict/list.
for lr in l_recs:
    lda = lr.get("donor_article")
    if lda is not None and not isinstance(lda, str):
        violations.append(f"[TYPE] article {lr['article']!r} donor_article is {type(lda).__name__} not str")

# ---- Report ----
print()
if violations:
    print(f"VIOLATIONS FOUND: {len(violations)}")
    for v in violations:
        print("  -", v.replace("\n", "\n    "))
else:
    print("NO VIOLATIONS")

print()
print(f"checked: live={len(l_recs)} backup={len(b_recs)} unbound={len(unbound_articles_sorted)} bound={len(bound)}")

sys.exit(1 if violations else 0)

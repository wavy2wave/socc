"""Freshness/authority governance.

Resolves each extracted claim into one of four statuses:
  CURRENT_AUTHORITY — the worked-out current line (newest external + in-repo canon)
  HISTORICAL        — older, consistent, kept for lineage
  DEPRECATED        — explicitly marked stale/superseded
  CONFLICTING       — current claims about the same entity-set that disagree

Rule: newest source wins; in-repo canon (canon_document / system_state) always
ranks as current authority because it is the authoritative present-day claim.
"""

CANON_PROVENANCE = {"canon_document", "system_state"}


def _rank(claim, fresh_cutoff):
    prov = claim.get("source_provenance")
    if prov in CANON_PROVENANCE:
        return 3  # in-repo canon = current authority
    mt = claim.get("source_mtime_utc") or ""
    return 2 if mt >= fresh_cutoff else 1


def _signature(claim):
    return frozenset(claim.get("entities", []))


def classify(claims):
    """claims: list of dicts with text, entities, polarity, intent,
    source_mtime_utc, source_provenance, link. Returns buckets + per-claim status."""
    if not claims:
        return {"current_authority": [], "historical": [], "deprecated": [],
                "conflicting": [], "counts": {"current": 0, "historical": 0,
                "deprecated": 0, "conflicting": 0}}

    # dedupe identical claim text, keep the freshest occurrence
    by_text = {}
    for c in claims:
        key = c["text"].strip().lower()
        prev = by_text.get(key)
        if prev is None or (c.get("source_mtime_utc") or "") > (prev.get("source_mtime_utc") or ""):
            by_text[key] = c
    uniq = list(by_text.values())

    mtimes = sorted([c.get("source_mtime_utc") or "" for c in uniq])
    # freshness cutoff = top quartile of mtimes (external "newest wins")
    cutoff = mtimes[int(len(mtimes) * 0.75)] if mtimes else ""

    current, historical, deprecated = [], [], []
    for c in uniq:
        if c.get("intent") == "deprecation":
            c["status"] = "DEPRECATED"
            deprecated.append(c)
            continue
        r = _rank(c, cutoff)
        if r >= 2:
            c["status"] = "CURRENT_AUTHORITY"
            current.append(c)
        else:
            c["status"] = "HISTORICAL"
            historical.append(c)

    # conflict: same entity signature, opposite polarity, both current
    conflicting = []
    sig_map = {}
    for c in current:
        sig_map.setdefault(_signature(c), []).append(c)
    keep_current = []
    for sig, group in sig_map.items():
        polarities = {g.get("polarity") for g in group}
        if len(group) > 1 and len(polarities) > 1:
            for g in group:
                g["status"] = "CONFLICTING"
            conflicting.extend(group)
        else:
            keep_current.extend(group)
    current = keep_current

    return {
        "current_authority": current,
        "historical": historical,
        "deprecated": deprecated,
        "conflicting": conflicting,
        "counts": {
            "current": len(current),
            "historical": len(historical),
            "deprecated": len(deprecated),
            "conflicting": len(conflicting),
        },
    }

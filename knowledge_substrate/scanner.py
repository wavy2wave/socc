"""Connector + source scanner.

Read-only walk of a connector's source_root. For each file: sha16(content),
size, mtime(utc iso), suffix, type, provenance class. Never copies or moves a
source. new/changed/unchanged is decided by comparing sha16 vs a prior registry.
"""

from pathlib import Path
from datetime import datetime, timezone

from knowledge_substrate.io import sha16_text


def _provenance(rel_name: str, first_line: str) -> str:
    name = rel_name.lower()
    fl = first_line.strip().lower()
    if name.endswith(".eml") or fl.startswith("from:") or fl.startswith("delivered-to:"):
        return "email"
    if name.startswith("chatgpt-") or "chatgpt" in name or fl.startswith("**you:**") or "## prompt:" in fl:
        return "chatgpt_export"
    if "протокол" in name or "protocol" in name or "cycle_l3" in name:
        return "raw_protocol"
    if name.endswith(".json"):
        return "system_state"
    if name.endswith(".md"):
        return "canon_document"
    return "note"


def _kind(suffix: str) -> str:
    return {
        ".txt": "text",
        ".md": "markdown",
        ".json": "json",
        ".eml": "email",
    }.get(suffix.lower(), "other")


def scan_root(source_root: str, include_suffixes, exclude_globs, recurse=True):
    """Yield source records for one connector root. Read-only."""
    root = Path(source_root)
    records = []
    if not root.exists():
        return records, f"SOURCE_ROOT_MISSING::{source_root}"

    excl = set(exclude_globs or [])
    suffixes = {s.lower() for s in include_suffixes}
    walker = root.rglob("*") if recurse else root.glob("*")

    for p in sorted(walker):
        if not p.is_file():
            continue
        if p.suffix.lower() not in suffixes:
            continue
        if any(p.match(g) for g in excl):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        first_line = content.split("\n", 1)[0] if content else ""
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
            size = p.stat().st_size
        except Exception:
            mtime = None
            size = 0
        records.append({
            "sha16": sha16_text(content),
            "abs_path": str(p.resolve()),
            "rel_path": str(p.relative_to(root)),
            "size": size,
            "mtime_utc": mtime,
            "suffix": p.suffix.lower(),
            "type": _kind(p.suffix),
            "provenance": _provenance(p.name, first_line),
            "line_count": content.count("\n") + 1,
        })
    return records, None


def scan_files(file_list, connector_id=None):
    """Scan an explicit list of files (scattered across the disk). Read-only."""
    records = []
    for fp in file_list:
        p = Path(fp).expanduser()
        if not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        first_line = content.split("\n", 1)[0] if content else ""
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
            size = p.stat().st_size
        except Exception:
            mtime, size = None, 0
        records.append({
            "sha16": sha16_text(content),
            "abs_path": str(p.resolve()),
            "rel_path": p.name,
            "size": size,
            "mtime_utc": mtime,
            "suffix": p.suffix.lower(),
            "type": _kind(p.suffix),
            "provenance": _provenance(p.name, first_line),
            "line_count": content.count("\n") + 1,
        })
    return records, None


def diff_status(records, prior_by_path):
    """Annotate each record with new/changed/unchanged vs prior registry (by abs_path)."""
    for r in records:
        prev = prior_by_path.get(r["abs_path"])
        if prev is None:
            r["status"] = "new"
        elif prev.get("sha16") != r["sha16"]:
            r["status"] = "changed"
        else:
            r["status"] = "unchanged"
    return records

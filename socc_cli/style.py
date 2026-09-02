#!/usr/bin/env python3
"""SOCC brand style — single source, reads SOCC_DESIGN_CANON_V1.json.

Every CLI surface imports colors/badges from here so the brand stays one style.
Falls back to hardcoded ANSI if the canon file is missing (never crash).
"""
import json
import sys
from pathlib import Path

SOCC_ROOT = Path(__file__).parent.parent
CANON = SOCC_ROOT / "SYSTEM/KERNEL/SOCC_DESIGN_CANON_V1.json"

# Base ANSI (brand palette — mirrors the canon's terminal_palette_ansi)
R, B, DIM = "\033[0m", "\033[1m", "\033[2m"
CY, GR, YE, RE, MA, BL, W = ("\033[36m", "\033[32m", "\033[33m", "\033[31m",
                             "\033[35m", "\033[34m", "\033[37m")


def _tty():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def c(col, t):
    return f"{col}{t}{R}" if _tty() else t


def canon():
    try:
        return json.loads(CANON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def canon_loaded():
    return CANON.exists()


_SEM = {"primary": CY, "success": GR, "warning": YE, "danger": RE, "event": MA, "muted": DIM}


def sem(name):
    return _SEM.get(name, R)


def header(title):
    return "\n".join([
        c(B + CY, "╔══════════════════════════════════════════════════════════════╗"),
        c(B + CY, "║  " + title.ljust(60) + "║"),
        c(B + CY, "╚══════════════════════════════════════════════════════════════╝"),
    ])


def divider(label=""):
    return c(DIM, f"── {label} " + "─" * max(0, 56 - len(label))) if label else c(DIM, "─" * 60)


def badge(status):
    s = (status or "?").upper()
    col = GR if s in ("PASS", "OK", "ACTIVE", "VALIDATED") else (
        RE if s in ("FAIL", "BLOCKED", "ERROR") else (
            YE if s in ("PENDING", "REVIEW_REQUIRED", "DRAFT", "QUEUED") else DIM))
    return c(col, f"[{s}]")


def dot(on):
    return c(GR, "●") if on else c(YE, "○")


def flag(val):
    return c(GR, "OFF") if val is False else (c(RE, "ON !") if val is True else c(DIM, str(val)))

#!/usr/bin/env python3
"""
SOCC Creator Control Panel — socc watch
Live terminal dashboard. Read-only. Refreshes every N seconds.
Press Ctrl+C to exit.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SOCC_ROOT = Path(__file__).parent.parent

ROUTE   = SOCC_ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
PULSE   = SOCC_ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL = SOCC_ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
LEDGER  = SOCC_ROOT / "MEMORY_WAVE/reports/autonomy/continuous_runner_tick_ledger.jsonl"
STOP    = SOCC_ROOT / "SOCC_RUNNER_STOP"

# ANSI colours
R  = "\033[0m"       # reset
B  = "\033[1m"       # bold
DIM = "\033[2m"
GR = "\033[32m"      # green
YE = "\033[33m"      # yellow
RE = "\033[31m"      # red
CY = "\033[36m"      # cyan
MA = "\033[35m"      # magenta
BL = "\033[34m"      # blue
W  = "\033[37m"      # white


def _ansi_supported() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


USE_COLOUR = _ansi_supported()


def c(colour: str, text: str) -> str:
    return f"{colour}{text}{R}" if USE_COLOUR else text


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_ledger_tail(n: int = 8) -> list[dict]:
    if not LEDGER.exists():
        return []
    lines = LEDGER.read_text(encoding="utf-8").strip().splitlines()
    rows = []
    for line in reversed(lines[-n:]):
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return list(reversed(rows))


def _flag(val) -> str:
    if val is False or val == "False" or val == false:
        return c(GR, "OFF")
    if val is True or val == "True":
        return c(RE, "ON !")
    return c(DIM, str(val))


def _flag(val) -> str:  # noqa: F811 — redefine without the bug above
    if val is False:
        return c(GR, "OFF")
    if val is True:
        return c(RE, "ON !")
    return c(DIM, str(val))


def _status_badge(s: str | None) -> str:
    s = (s or "").upper()
    if s in ("PASS", "VALIDATED", "ACTIVE"):
        return c(GR, f"[{s}]")
    if s in ("FAIL", "BLOCKED", "ERROR"):
        return c(RE, f"[{s}]")
    if s in ("PENDING", "QUEUED", "REVIEW_REQUIRED"):
        return c(YE, f"[{s}]")
    return c(DIM, f"[{s or '?'}]")


def _workload_badge(s: str) -> str:
    s = s.upper()
    if "ACTIVE" in s:
        return c(GR, s)
    if "BLOCKED" in s:
        return c(RE, s)
    if "QUEUED" in s or "DOWNSTREAM" in s:
        return c(YE, s)
    return c(DIM, s)


def _short(text: str, n: int = 72) -> str:
    text = str(text or "")
    return text[:n] + "…" if len(text) > n else text


def _ts_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _width() -> int:
    try:
        return os.get_terminal_size().columns
    except Exception:
        return 100


def _divider(ch: str = "─", label: str = "") -> str:
    w = _width()
    if label:
        pad = max(0, w - len(label) - 4)
        return c(DIM, f"── {label} " + ch * pad)
    return c(DIM, ch * w)


def render() -> str:
    route   = _read(ROUTE)
    pulse   = _read(PULSE)
    control = _read(CONTROL)
    ledger  = _read_ledger_tail(8)

    operator_view = control.get("operator_view") or control
    queued        = operator_view.get("queued_workloads") or []

    lawful_next  = route.get("lawful_next") or route.get("real_next") or route.get("current_lawful_next") or "UNKNOWN"
    route_status = route.get("status") or "?"
    last_step    = route.get("last_committed_step") or route.get("last_step") or "—"
    upstream     = route.get("upstream_proof") or "—"
    truth_b      = _short(route.get("truth_boundary") or "—", 90)
    route_hash   = route.get("route_hash") or "—"

    pulse_next   = pulse.get("current_lawful_next") or pulse.get("lawful_next") or "—"
    pulse_status = pulse.get("status") or "?"

    runner_active = STOP.exists()

    lines = []
    lines.append("")
    lines.append(c(B + CY, "╔══════════════════════════════════════════════════════════════╗"))
    lines.append(c(B + CY, "║          SOCC — CREATOR CONTROL PANEL                        ║"))
    lines.append(c(B + CY, "╚══════════════════════════════════════════════════════════════╝"))
    lines.append(c(DIM, f"  {_ts_now()}   root: {SOCC_ROOT}"))
    lines.append("")

    # ── Route Authority ─────────────────────────────────────────────
    lines.append(_divider(label="ROUTE AUTHORITY"))
    lines.append(f"  Status         {_status_badge(route_status)}")
    lines.append(f"  Lawful next    {c(B+CY, lawful_next)}")
    lines.append(f"  Last step      {c(W, _short(last_step, 70))}")
    lines.append(f"  Upstream proof {c(DIM, _short(upstream, 70))}")
    lines.append(f"  Route hash     {c(DIM, route_hash[:24] if route_hash != '—' else '—')}")
    lines.append(f"  Truth boundary {c(DIM, truth_b)}")
    lines.append("")

    # ── Runner Status ────────────────────────────────────────────────
    lines.append(_divider(label="RUNNER"))
    if runner_active:
        lines.append(f"  State          {c(GR+B, '● RUNNING')}   (delete SOCC_RUNNER_STOP to halt)")
    else:
        lines.append(f"  State          {c(YE, '○ IDLE')}      (run: socc run)")
    lines.append(f"  Pulse status   {_status_badge(pulse_status)}")
    lines.append(f"  Pulse next     {c(DIM, _short(pulse_next, 60))}")
    lines.append("")

    # ── Safety Flags ─────────────────────────────────────────────────
    lines.append(_divider(label="SAFETY FLAGS"))
    flags = [
        ("daemon_running",          route.get("daemon_running", False)),
        ("background_loop_enabled", route.get("background_loop_enabled", False)),
        ("scheduler_installed",     route.get("scheduler_installed", False)),
        ("network_used",            route.get("network_used", False)),
        ("entity_birth_allowed",    route.get("entity_birth_allowed", False)),
        ("anna_birth_allowed",      route.get("anna_birth_allowed", False)),
        ("agi_claim_allowed",       route.get("agi_claim_allowed", False)),
    ]
    for name, val in flags:
        lines.append(f"  {name:<28}  {_flag(val)}")
    lines.append("")

    # ── Workload Queue ────────────────────────────────────────────────
    lines.append(_divider(label="WORKLOAD QUEUE"))
    if queued:
        for wl in queued:
            wid     = wl.get("id", "?")
            wstatus = wl.get("status", "?")
            wsummary = _short(wl.get("summary") or wl.get("description") or "", 50)
            lines.append(f"  {wid:<40}  {_workload_badge(wstatus)}")
            if wsummary:
                lines.append(f"  {'':<40}  {c(DIM, wsummary)}")
    else:
        lines.append(f"  {c(DIM, 'No workloads in control panel state')}")
    lines.append("")

    # ── Recent Ticks ─────────────────────────────────────────────────
    lines.append(_divider(label="RECENT SELF-BUILD TICKS"))
    if ledger:
        for row in ledger:
            event  = row.get("event")
            ts     = (row.get("ts") or "")[:19].replace("T", " ")
            script = row.get("script") or row.get("lawful_next") or ""
            status = row.get("status") or "?"
            tick_n = row.get("tick") or "—"
            if event:
                lines.append(f"  {c(MA, event)}")
            else:
                badge = c(GR, "✓") if status == "PASS" else c(RE, "✗")
                lines.append(f"  {badge} #{str(tick_n):>3}  {ts}  {c(W, _short(script, 52))}  {_status_badge(status)}")
    else:
        lines.append(f"  {c(DIM, 'No ticks yet — run: socc run')}")
    lines.append("")

    # ── Commands ─────────────────────────────────────────────────────
    lines.append(_divider())
    lines.append(c(DIM, "  socc run          continuous self-build   |   socc step   single step"))
    lines.append(c(DIM, "  socc observe      full system report      |   socc status quick status"))
    lines.append(c(DIM, "  Ctrl+C            exit watch panel"))
    lines.append("")

    return "\n".join(lines)


def watch(interval: float = 3.0) -> None:
    try:
        while True:
            os.system("clear" if os.name != "nt" else "cls")
            print(render())
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nExiting watch panel.")

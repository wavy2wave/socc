#!/usr/bin/env python3
"""SOCC canonical HTML renderer — the web analogue of socc_cli/style.py.

LAW: every OPERATOR surface (dashboard, any line/frontier, any console/chat view
meant for the creator) MUST render through this module, so the whole system
shows ONE style — SOCC_DESIGN_CANON_V1, matrix-minimalism. Never invent a
bespoke operator style. (Customer/product surfaces use the product brand, not
this — see SOCC_SURFACE_LAW.)

Depth (canon.technologicalness): dark-first elevation ladder (layering + luminous
hairline, not drop-shadow), a restrained cyberpunk grid backdrop, a matrix
translation of Apple Liquid Glass (.glass, degrades under Reduced Transparency),
functional motion (reduced-motion-safe) and focus-visible rings — all in css().
Atoms: badge, dot, header_box, divider, row, line, panel, kpi, grid, kbd.

Usage from any line:
    import sys; sys.path.insert(0, "<SOCC>/SYSTEM/INTERFACE/dashboard")
    from socc_canon_html import palette, page, divider, badge, dot, row, panel, kpi, grid
    P = palette()
    body = divider("STATE") + panel(row("status", badge("PASS", P), P), "cell")
    html = page("MY VIEW", body, P=P)
"""
import json
from pathlib import Path

_CANON = Path(__file__).resolve().parents[3] / "SYSTEM/KERNEL/SOCC_DESIGN_CANON_V1.json"

DEFAULT_PAL = {"bg": "#0B0F14", "surface": "#121821", "primary": "#22D3EE",
               "success": "#22C55E", "warning": "#EAB308", "danger": "#EF4444",
               "event": "#A855F7", "text": "#E6EDF3", "muted": "#7D8893"}


def palette():
    """Read the brand palette from the real canon; fall back to its known values."""
    try:
        p = json.loads(_CANON.read_text(encoding="utf-8")).get("web_palette_hex", {})
    except Exception:
        p = {}
    return {k: p.get(k, v) for k, v in DEFAULT_PAL.items()}


def badge(status, P=None):
    P = P or palette()
    s = (status or "?").upper()
    if "SEAL" in s:
        col = P["primary"]
    elif any(x in s for x in ("ACCEPT", "PASS", "OK", "VALIDAT", "HARDEN", "DONE", "ACTIVE")):
        col = P["success"]
    elif any(x in s for x in ("REVIEW", "PENDING", "DRAFT", "QUEUED", "PROOF", "LIVE")):
        col = P["warning"]
    elif any(x in s for x in ("FAIL", "BLOCK", "ERROR")):
        col = P["danger"]
    else:
        col = P["muted"]
    label = s.split("(")[0].strip() or "?"
    return f'<span style="color:{col};font-weight:700">[{label}]</span>'


def dot(on, P=None):
    P = P or palette()
    return (f'<span style="color:{P["success"]}">●</span>' if on
            else f'<span style="color:{P["muted"]}">○</span>')


def header_box(title):
    inner = title.ljust(56)
    top = "╔" + "═" * 60 + "╗"
    mid = "║  " + inner[:56] + "║"
    bot = "╚" + "═" * 60 + "╝"
    return f'<div class="box">{top}\n{mid}\n{bot}</div>'


def divider(label=""):
    if not label:
        return '<div class="div">' + "─" * 50 + "</div>"
    return f'<div class="div">── {label} ' + "─" * max(0, 46 - len(label)) + "</div>"


def row(k, v, P=None):
    return f'<div class="r"><span class="k">{k}</span><span class="v">{v}</span></div>'


def line(text):
    return f'<div class="ln">{text}</div>'


def panel(inner, label=""):
    """Elevated operator surface. Depth = layering + luminous hairline, not heavy shadow."""
    head = f'<div class="p-h">{label}</div>' if label else ""
    return f'<div class="panel">{head}{inner}</div>'


def kpi(value, title):
    return (f'<div class="kpi"><div class="kpi-val">{value}</div>'
            f'<div class="kpi-title">{title}</div></div>')


def grid(items, cols=3):
    return (f'<div class="grid" style="grid-template-columns:repeat({cols},1fr)">'
            + "".join(items) + "</div>")


def kbd(k):
    return f'<span class="kbd">{k}</span>'


def css(P=None):
    P = P or palette()
    return f"""<style>
 :root{{
  --bg:{P['bg']};--surface:{P['surface']};--primary:{P['primary']};--success:{P['success']};
  --warning:{P['warning']};--danger:{P['danger']};--event:{P['event']};--text:{P['text']};--muted:{P['muted']};
  /* elevation ladder — refined dark: depth by layering + luminous hairline, not heavy shadow */
  --s0:{P['bg']};--s1:#0e141d;--s2:{P['surface']};--s3:#18212e;
  --line:#1d2733;--line-lum:color-mix(in srgb,var(--primary) 24%,transparent);
  --hair:rgba(255,255,255,.045);
  --glow:0 0 0 1px color-mix(in srgb,var(--primary) 15%,transparent),0 10px 34px -14px rgba(0,0,0,.72);
  --radius:12px;--radius-sm:7px;
  --mono:ui-monospace,'SF Mono',Menlo,Monaco,monospace;
 }}
 *{{box-sizing:border-box}}
 /* technical grid backdrop — cyberpunk motif, restrained: low-opacity fixed grid + one cyan glow */
 body::before{{content:"";position:fixed;inset:0;z-index:-2;pointer-events:none;
  background:
   radial-gradient(120% 68% at 50% -12%,color-mix(in srgb,var(--primary) 8%,transparent) 0%,transparent 56%),
   linear-gradient(transparent 95%,var(--hair) 0),linear-gradient(90deg,transparent 95%,var(--hair) 0);
  background-size:100% 100%,42px 42px,42px 42px}}
 body{{margin:0;background:var(--s0);color:var(--text);
  font-family:var(--mono);font-size:13px;line-height:1.6;-webkit-font-smoothing:antialiased;
  font-variant-numeric:tabular-nums}}
 .wrap{{max-width:960px;margin:0 auto;padding:34px 22px 92px}}
 /* header box — ascii frame inside a luminous panel (glass-adjacent) */
 .box{{color:var(--primary);font-weight:700;white-space:pre;line-height:1.25;font-size:12px;
  margin:0 0 8px;padding:16px 18px;border-radius:var(--radius);
  background:linear-gradient(180deg,color-mix(in srgb,var(--primary) 6%,var(--s1)),var(--s1));
  border:1px solid var(--line);box-shadow:var(--glow);
  text-shadow:0 0 20px color-mix(in srgb,var(--primary) 42%,transparent)}}
 .sub{{color:var(--muted);margin:0 0 20px;letter-spacing:.02em}}
 .div{{color:var(--muted);margin:26px 0 10px;white-space:pre;letter-spacing:.09em;
  text-transform:uppercase;font-size:11px}}
 .r{{display:flex;gap:12px;align-items:baseline;padding:3px 0}}
 .k{{color:var(--muted);min-width:154px}} .v{{color:var(--text)}}
 .ln{{padding:2px 0}} .muted{{color:var(--muted)}}
 a{{color:var(--primary);text-decoration:none;
  border-bottom:1px solid color-mix(in srgb,var(--primary) 32%,transparent);
  transition:border-color .15s ease,color .15s ease}}
 a:hover{{border-bottom-color:var(--primary)}}
 .no{{color:var(--danger)}} .ok{{color:var(--success)}}
 /* panel — elevated operator card. depth = layering + inset hairline highlight */
 .panel{{background:var(--s2);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px 18px;margin:12px 0;position:relative;
  box-shadow:0 1px 0 var(--hair) inset,0 12px 32px -20px rgba(0,0,0,.85)}}
 .p-h{{color:var(--muted);text-transform:uppercase;letter-spacing:.09em;font-size:11px;margin:0 0 10px}}
 /* glass — matrix translation of Apple Liquid Glass: blur + translucency + luminous edge, used sparingly */
 .glass{{background:color-mix(in srgb,var(--s2) 70%,transparent);
  backdrop-filter:blur(14px) saturate(1.2);-webkit-backdrop-filter:blur(14px) saturate(1.2);
  border:1px solid var(--line-lum);border-radius:var(--radius);box-shadow:var(--glow)}}
 /* kpi bento — density with clarity */
 .grid{{display:grid;gap:12px;margin:12px 0}}
 .kpi{{background:var(--s2);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px}}
 .kpi-val{{font-size:27px;font-weight:700;color:var(--text);line-height:1;letter-spacing:-.01em}}
 .kpi-title{{color:var(--muted);font-size:11px;margin-top:7px;text-transform:uppercase;letter-spacing:.05em}}
 .kbd{{font-family:var(--mono);font-size:11px;color:var(--text);background:var(--s3);
  border:1px solid var(--line);border-bottom-width:2px;border-radius:5px;padding:1px 6px}}
 :where(a,button,[tabindex]):focus-visible{{outline:2px solid var(--primary);outline-offset:2px;border-radius:3px}}
 .foot{{margin-top:34px;color:var(--muted);font-size:11px;line-height:1.8;
  border-top:1px solid var(--line);padding-top:14px}}
 @media (prefers-reduced-motion:no-preference){{
  .panel{{transition:border-color .18s ease,box-shadow .18s ease,transform .18s ease}}
  .panel:hover{{border-color:var(--line-lum);
   box-shadow:0 0 0 1px var(--line-lum),0 20px 46px -24px rgba(0,0,0,.9);transform:translateY(-1px)}}
 }}
 @media (prefers-reduced-transparency:reduce){{.glass{{background:var(--s2);backdrop-filter:none;-webkit-backdrop-filter:none}}}}
</style>"""


def page(title, body, subtitle="", P=None):
    P = P or palette()
    sub = f'<p class="sub">{subtitle}</p>' if subtitle else ""
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{title}</title>{css(P)}</head><body><div class="wrap">'
            f'{header_box(title)}{sub}{body}</div></body></html>')

#!/usr/bin/env python3
"""SOCC — unified operator console (общий пульт).

Reads EVERY panel in SYSTEM/DASHBOARD/*.json plus the Brand Forge state and
renders ONE operator surface through the SOCC canon (via socc_canon_html).
Brand Forge is a SECTION here, not a separate file. Re-run to refresh:

    python3 SYSTEM/INTERFACE/dashboard/socc_console.py
"""
import json
from pathlib import Path
from socc_canon_html import palette, page, divider, badge, row, line

SOCC = Path(__file__).resolve().parents[3]
DASH = SOCC / "SYSTEM/DASHBOARD"
OUT = DASH / "SOCC_CONSOLE.html"

# group order + how to detect membership from a panel id/filename
GROUPS = [
    ("BRAND FORGE", "BRAND_FORGE"),
    ("ANNA MVP", "ANNA_MVP"),
    ("ENTITY SUBSTRATE", "ENTITY_SUBSTRATE"),
    ("KNOWLEDGE SUBSTRATE", "KNOWLEDGE_SUBSTRATE"),
    ("ASSIGNMENT 0001", "ASSIGNMENT_0001"),
    ("AUTONOMY / OPERATOR", "AUTONOMY"),
    ("STAFF", "STAFF"),
]


def load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def short(name):
    return (name.replace("_PANEL_V1", "").replace("_V1", "")
            .replace("BRAND_FORGE_", "").replace("ANNA_MVP_", "")
            .replace("ENTITY_SUBSTRATE_", "").replace("KNOWLEDGE_SUBSTRATE_", "")
            .replace("ASSIGNMENT_0001_", "").replace("_PANEL_POINTER", ""))


def main():
    P = palette()
    panels = []
    for f in sorted(DASH.glob("*.json")):
        d = load(f)
        panels.append((f.stem, d))

    def group_of(stem, d):
        hay = (stem + " " + str(d.get("id", ""))).upper()
        for label, key in GROUPS:
            if key in hay:
                return label
        return "OTHER"

    # bucket
    buckets = {label: [] for label, _ in GROUPS}
    buckets["OTHER"] = []
    for stem, d in panels:
        buckets[group_of(stem, d)].append((stem, d))

    # counts / health
    total = len(panels)
    fails = sum(1 for _, d in panels if d.get("hard_failures"))

    body = []
    body.append(divider("SYSTEM"))
    body.append(row("panels", f"{total} · groups {len([b for b in buckets if buckets[b]])}", P))
    body.append(row("hard_failures", (badge("FAIL", P) if fails else badge("OK", P)) + f" {fails}", P))
    body.append(row("brand forge", f'<a href="../BRAND_FORGE/runtime/BRAND_FORGE_CONTROL_ROOM.html">open control room →</a>', P))

    order = [g[0] for g in GROUPS] + ["OTHER"]
    for label in order:
        items = buckets.get(label) or []
        if not items:
            continue
        extra = ""
        if label == "BRAND FORGE":
            extra = '  <a href="../BRAND_FORGE/runtime/BRAND_FORGE_CONTROL_ROOM.html">[control room]</a>'
        body.append(divider(label) )
        if extra:
            body.append(line(extra))
        for stem, d in sorted(items, key=lambda x: x[0]):
            st = d.get("status", "")
            nxt = d.get("next", "")
            nxt_s = f' <span class="muted">→ {nxt}</span>' if nxt else ""
            body.append(line(f'{badge(st, P)} {short(stem)}{nxt_s}'))

    body.append(divider("SURFACE LAW"))
    body.append(line('<span class="ok">✓</span> operator surfaces render through SOCC canon (this pult) — one style'))
    body.append(line('<span class="no">⛔</span> customer/product surfaces use the product brand — matrix never reaches a buyer'))
    body.append('<p class="foot">regenerate: <span style="color:%s">python3 SYSTEM/INTERFACE/dashboard/socc_console.py</span> · '
                'voice: calm, precise, honest — no hype, no fake PASS.</p>' % P["text"])

    html = page("SOCC — OPERATOR CONSOLE", "".join(body),
                subtitle="единый пульт · rendered through SOCC_DESIGN_CANON_V1 · all panels, one style", P=P)
    OUT.write_text(html, encoding="utf-8")
    print(f"console rendered -> {OUT.relative_to(SOCC)}")
    print(f"  panels: {total} · groups rendered: {len([b for b in buckets if buckets[b]])} · hard_failures: {fails}")


if __name__ == "__main__":
    main()

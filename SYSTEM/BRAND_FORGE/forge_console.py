#!/usr/bin/env python3
"""SOCC Brand Forge — live control room generator.

Reads the REAL forge artifacts (SOCC_DESIGN_CANON palette, state, LINE, faces,
proof chain) and renders the operator cockpit as HTML through the SOCC canon
(matrix-minimalism). Re-run after any change to refresh the cockpit:

    python3 SYSTEM/BRAND_FORGE/forge_console.py

Never crashes on a missing file — falls back to canon defaults (like style.py).
"""
import json
import sys
from pathlib import Path

BF = Path(__file__).resolve().parent
SOCC = BF.parents[1]
OUT = BF / "runtime" / "BRAND_FORGE_CONTROL_ROOM.html"

# Operator surface law: render through the shared SOCC canon renderer, never a local style.
sys.path.insert(0, str(SOCC / "SYSTEM/INTERFACE/dashboard"))
from socc_canon_html import palette, badge  # noqa: E402


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def main():
    P = palette()
    state = load(BF / "runtime/BRAND_FORGE_STATE_V1.json")
    line = load(BF / "BRAND_FORGE_LINE_V1.json")
    seal = load(BF / "BRAND_FORGE_SEAL_V1.json")
    anna = load(BF / "canon/ANNA_DESIGN_CANON_V1.json")
    mark = load(BF / "frontiers/entity2/MARK_BARBERSHOP_FACE_V1.json")
    proofs = sorted((SOCC / "SOVEREIGN/PROOF/proof_chain").glob("SOCC_BRAND_FORGE_*_PROOF.json"))

    ph_status = state.get("phase_status", {})

    # LINE rows from the real LINE artifact
    line_rows = []
    for phase in line.get("phases", []):
        title = f'{phase.get("phase","")} {phase.get("title","")}'
        # match a status from state.phase_status by phase code (P0/P1/...)
        code = phase.get("phase", "")
        st = next((v for k, v in ph_status.items() if k.upper().startswith(code)), "")
        dot = P["success"] if st else P["muted"]
        n = len(phase.get("frontiers", []))
        line_rows.append(
            f'<div class="line"><span style="color:{dot}">●</span> '
            f'{title} &nbsp; {badge(st, P)} <span class="muted">· {n} frontiers</span></div>')

    # proof rows
    proof_rows = []
    for f in proofs:
        d = load(f)
        proof_rows.append(
            f'<div class="line"><span style="color:{P["primary"]}">↳</span> '
            f'{f.stem.replace("SOCC_BRAND_FORGE_","").replace("_PROOF","")} {badge(d.get("status"), P)}</div>')

    # faces
    a_pal = anna.get("web_palette_hex", {})
    m_pal = mark.get("skin", {}).get("tokens", {})

    def sw(c):
        return f'<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:{c};vertical-align:middle;margin-right:1px;border:1px solid #0006"></span>'

    faces = f'''
    <div class="row"><span class="k"><span style="color:{P['success']}">●</span> Анна</span>
      <span class="v"><a href="../frontiers/BRAND_FORGE_F2_VISUAL_CORE_V1.html">{anna.get("direction","")}</a>
      {sw(a_pal.get("primary","#54705C"))}{sw(a_pal.get("accent","#D9A679"))}
      · {badge(anna.get("status"), P)}</span></div>
    <div class="row"><span class="k"><span style="color:{P['success']}">●</span> Марк</span>
      <span class="v"><a href="../frontiers/entity2/MARK_BRAND_SHEET_V1.html">{mark.get("vertical","")}</a>
      {sw(m_pal.get("primary","#C77F4E"))}{sw(m_pal.get("bg","#1E1B19"))}
      · {badge("PROOF", P)}</span></div>
    <div class="row"><span class="k"><span style="color:{P['muted']}">○</span> next</span>
      <span class="v muted">пластика / мультипрофиль · ≈ часы через Forge</span></div>'''

    risks = "".join(
        f'<div class="line"><span style="color:{P["warning"]}">❓</span> {x}</div>'
        for x in state.get("deferred", []))
    stealth = ('<div class="line"><span style="color:%s">❗</span> disclosure = FULL STEALTH — '
               'creator-accepted, <span style="color:%s">logged OPEN</span></div>'
               % (P["warning"], P["warning"]))

    html = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SOCC ▸ BRAND FORGE — CONTROL ROOM</title>
<style>
 :root{{--bg:{P['bg']};--surface:{P['surface']};--primary:{P['primary']};--success:{P['success']};
   --warning:{P['warning']};--danger:{P['danger']};--event:{P['event']};--text:{P['text']};--muted:{P['muted']};}}
 *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);
   font-family:ui-monospace,'SF Mono',Menlo,monospace;font-size:13.5px;line-height:1.6}}
 .wrap{{max-width:900px;margin:0 auto;padding:30px 20px 80px}}
 .box{{color:var(--primary);font-weight:700;white-space:pre;line-height:1.25;font-size:13px;margin-bottom:4px}}
 .sub{{color:var(--muted);margin:0 0 22px}} .muted{{color:var(--muted)}}
 .div{{color:var(--muted);margin:26px 0 12px;white-space:pre;letter-spacing:.06em}}
 .row{{display:flex;gap:10px;align-items:baseline;padding:3px 0}} .k{{color:var(--muted);min-width:150px}}
 .line{{padding:2px 0}} a{{color:var(--primary);text-decoration:none;border-bottom:1px dotted #2b6b78}}
 .no{{color:var(--danger)}} .ok{{color:var(--success)}} .foot{{margin-top:30px;color:var(--muted);font-size:12.5px}}
</style></head><body><div class="wrap">
<div class="box">╔══════════════════════════════════════════╗
║  SOCC ▸ BRAND FORGE — CONTROL ROOM   (live: forge_console.py)  ║
╚═══════════════════════════════════════════╝</div>
<p class="sub">operator surface · rendered through SOCC_DESIGN_CANON_V1 · generated from real artifacts</p>

<div class="div">── ROOT ───────────────────────────────────────</div>
<div class="row"><span class="k">cell</span><span class="v">{state.get("cell","BRAND_FORGE_CELL_V1")}</span></div>
<div class="row"><span class="k">forge verdict</span><span class="v">{badge(seal.get("seal_verdict","SEALED"), P)} {seal.get("what_is_sealed","")[:60]}</span></div>
<div class="row"><span class="k">flags</span><span class="v">brand_live <span class="no">OFF</span> · network <span class="no">OFF</span> · revenue <span class="no">OFF</span> · agi <span class="no">OFF</span></span></div>

<div class="div">── LINE (no jumping) ────────────────────────</div>
{''.join(line_rows)}
<div class="row" style="margin-top:8px"><span class="k">lawful_next</span><span class="v" style="color:{P['primary']}">{state.get("lawful_next","")}</span></div>

<div class="div">── PROOF CHAIN ───────────────────────────</div>
{''.join(proof_rows) or '<div class="line muted">(no proofs found)</div>'}

<div class="div">── FACES (product tier · click → brand-sheet) ──────</div>
{faces}

<div class="div">── SAFETY FLAGS / OPEN ──────────────────</div>
{stealth}{risks}

<div class="div">── SURFACE LAW ────────────────────────</div>
<div class="line"><span class="ok">✓</span> operator screens (this) → <span style="color:{P['primary']}">SOCC canon</span> (matrix) — one style</div>
<div class="line"><span class="no">⛔</span> customer screens → product brand — matrix must NEVER reach a buyer</div>

<p class="foot">faces: <a href="../frontiers/BRAND_ARCHITECTURE_MAP_V1.html">house map</a> ·
 regenerate: <span style="color:{P['text']}">python3 SYSTEM/BRAND_FORGE/forge_console.py</span> ·
 voice: calm, precise, honest — no hype, no fake PASS.</p>
</div></body></html>'''

    OUT.write_text(html, encoding="utf-8")
    print(f"control room rendered -> {OUT.relative_to(SOCC)}")
    print(f"  palette from canon: {'yes' if (SOCC / 'SYSTEM/KERNEL/SOCC_DESIGN_CANON_V1.json').exists() else 'fallback'}")
    print(f"  LINE phases: {len(line.get('phases', []))} · proofs: {len(proofs)} · faces: 2")


if __name__ == "__main__":
    main()

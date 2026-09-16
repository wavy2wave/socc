#!/usr/bin/env python3
"""ANNA canonical HTML renderer + component library — the PRODUCT twin of socc_canon_html.py.

LAW (SOCC_SURFACE_LAW): every CUSTOMER / PRODUCT surface for ANNA (owner cabinet,
landing, patient-facing views) MUST render through this module, so the whole
product shows ONE warm style — ANNA_DESIGN_CANON_V1, D3 "Спокойная забота".
The operator matrix (socc_canon_html.py) must NEVER reach a buyer, and this warm
style must never be used for operator/proof surfaces.

Product analogue of SYSTEM/INTERFACE/dashboard/socc_canon_html.py: same shape
(palette/css/page + component fns), different canon. Components consume tokens,
never hardcode. Source of truth: canon/ANNA_DESIGN_CANON_V1.json + anna-tokens.css.

This is the living component library: foundations + button/badge/pill/card/kpi/
avatar/bubble/field/dialog_row/thread/booking_row/banner/tabs/topbar/toast. Any
ANNA surface composes these instead of re-inlining CSS.

Usage:
    import sys; sys.path.insert(0, "<SOCC>/SYSTEM/BRAND_FORGE/canon")
    import anna_canon_html as A
    P = A.palette()
    html = A.page("кабинет", A.card(A.kpi("48","Обращений")), P=P)
"""
import json
from pathlib import Path

_CANON = Path(__file__).resolve().parent / "ANNA_DESIGN_CANON_V1.json"

DEFAULT_PAL = {
    "bg": "#F5F3EE", "surface": "#FFFFFF", "surface_2": "#EDEAE3", "ink": "#2E3D34",
    "muted": "#6E7B71", "primary": "#54705C", "primary_soft": "#8AA897",
    "accent": "#D9A679", "accent_deep": "#B5824F", "success": "#4F8A5B",
    "warning": "#C8923E", "danger": "#C0533B",
}


def palette():
    """Read the product palette from the real canon; fall back to known D3 values."""
    try:
        p = json.loads(_CANON.read_text(encoding="utf-8")).get("web_palette_hex", {})
    except Exception:
        p = {}
    return {k: p.get(k, v) for k, v in DEFAULT_PAL.items()}


_SKINS = Path(__file__).resolve().parent / "BRAND_SKINS_V1.json"


def skin(name="anna"):
    """Load a brand palette from the skin registry (factory data layer). Fallback: ANNA/default."""
    try:
        s = json.loads(_SKINS.read_text(encoding="utf-8"))["skins"][name]["palette"]
        return {k: s.get(k, v) for k, v in DEFAULT_PAL.items()}
    except Exception:
        return palette()


def skins():
    """All registered brand skins {name: {label, palette, ...}}."""
    try:
        return json.loads(_SKINS.read_text(encoding="utf-8"))["skins"]
    except Exception:
        return {}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ── atoms ─────────────────────────────────────────────────────────────────────
def h(label):
    return f'<div class="h">{esc(label)}</div>'


def button(label, kind="primary", onclick=""):
    """kind: primary | accent | ghost"""
    oc = f' onclick="{onclick}"' if onclick else ""
    return f'<button class="btn btn--{kind}"{oc}>{esc(label)}</button>'


def badge(text, kind="ok"):
    """kind: ok | wait | mute | danger"""
    return f'<span class="chip chip--{kind}">{esc(text)}</span>'


chip = badge  # alias


def pill(text, state="on"):
    """status pill with colored dot. state: on | off | unknown"""
    return f'<span class="pill"><span class="dot dot--{state}"></span>{esc(text)}</span>'


def card(inner, title=""):
    head = h(title) if title else ""
    return f'<div class="card">{head}{inner}</div>'


def kpi(value, title, tag=""):
    t = f'<div class="kpi-tag">{esc(tag)}</div>' if tag else ""
    return (f'<div class="card kpi">{t}<div class="kpi-val">{esc(value)}</div>'
            f'<div class="kpi-title">{esc(title)}</div></div>')


def avatar(initial):
    return f'<div class="ava">{esc(initial)}</div>'


def bubble(text, who="a", flag=False):
    """who: a (ANNA, sage) | p (patient). flag=True adds an 'mark error' control on ANNA bubbles."""
    inner = esc(text)
    if who == "a" and flag:
        inner += ('<button class="flag" title="разметить ошибку" '
                  'onclick="annaFlag(this);event.stopPropagation()">⚑</button>')
    return f'<div class="brow brow--{who}"><div class="b b--{who}">{inner}</div></div>'


def field(placeholder="", _id=""):
    idattr = f' id="{_id}"' if _id else ""
    return f'<input class="input"{idattr} placeholder="{esc(placeholder)}">'


# ── composites ────────────────────────────────────────────────────────────────
def grid(cards, cols=4):
    return f'<div class="grid" style="grid-template-columns:repeat({cols},1fr)">{"".join(cards)}</div>'


def cols(left, right):
    return f'<div class="cols"><div>{left}</div><div>{right}</div></div>'


def arch_mark(size=26):
    """The nested-arch shelter mark (the ANNA logomark), inline SVG. Repeats the brand motif."""
    h = round(size * 22 / 26)
    return (f'<svg class="arch-mark" width="{size}" height="{h}" viewBox="0 0 26 22" fill="none" aria-hidden="true">'
            f'<path d="M2 21V12a11 11 0 0 1 22 0v9" stroke="var(--primary)" stroke-width="2" stroke-linecap="round"/>'
            f'<path d="M7 21v-9a6 6 0 0 1 12 0v9" stroke="var(--primary-soft)" stroke-width="1.7" stroke-linecap="round"/></svg>')


def warm_divider():
    """The single tasteful sand hairline with a centered arch. Use ONCE (twice max)."""
    return ('<div class="warm-divider" aria-hidden="true">'
            '<svg width="30" height="15" viewBox="0 0 30 15" fill="none">'
            '<path d="M2 15V8a13 13 0 0 1 26 0v7" stroke="var(--accent)" stroke-width="1.6" stroke-linecap="round"/>'
            '</svg></div>')


def topbar(brand, clinic="", right_html=""):
    cl = f'<span class="clinic">{clinic}</span>' if clinic else ""
    return (f'<div class="bar"><span class="brand-lockup">{arch_mark(26)}<span class="brand">{esc(brand)}</span></span>{cl}'
            f'<span class="spacer"></span>{right_html}</div>')


def tabs(items, active=0):
    out = []
    for i, t in enumerate(items):
        on = " on" if i == active else ""
        out.append(f'<span class="tab{on}" onclick="annaTab(this)">{esc(t)}</span>')
    return f'<span class="chips">{"".join(out)}</span>'


def banner(inner_html):
    return f'<div class="note">⚖️<div>{inner_html}</div></div>'


def dialog_row(rid, initial, name, time, preview, badge_html, active=False):
    a = " is-active" if active else ""
    return (f'<div class="dlg{a}" id="row-{rid}" onclick="annaPick(\'{rid}\')">'
            f'{avatar(initial)}<div class="dlg-body">'
            f'<div class="dlg-top"><span class="dlg-name">{esc(name)}</span>'
            f'<span class="dlg-time">{esc(time)}</span></div>'
            f'<div class="dlg-prev">{esc(preview)}</div></div><div>{badge_html}</div></div>')


def thread(rid, bubbles_html, header="", hidden=False, actions_html=""):
    hd = f'<div class="h" style="margin-bottom:8px">{esc(header)}</div>' if header else ""
    act = f'<div class="actions">{actions_html}</div>' if actions_html else ""
    hide = " hidden" if hidden else ""
    return f'<div class="thread" id="th-{rid}"{hide}>{hd}{bubbles_html}{act}</div>'


def booking_row(svc, who, when, state="booked"):
    color = "var(--success)" if state == "booked" else "var(--accent-deep)"
    sym = "●" if state == "booked" else "○"
    return (f'<div class="bk"><div class="bk-dot" style="color:{color}">{sym}</div>'
            f'<div class="bk-body"><div class="bk-svc">{esc(svc)}</div>'
            f'<div class="bk-meta">{esc(who)} · {esc(when)}</div></div></div>')


def subnote(inner_html):
    return f'<div class="subnote">{inner_html}</div>'


def tg_profile(name, handle, bio, status="онлайн"):
    """Patient-facing Telegram profile header (touchpoint). Product canon, stealth."""
    ini = esc(name[:1].upper()) if name else "•"
    return (f'<div class="card tg-prof"><div class="ava ava--lg">{ini}</div>'
            f'<div class="tg-meta"><div class="tg-name">{esc(name)} <span class="tg-h">{esc(handle)}</span></div>'
            f'<div class="tg-status"><span class="dot dot--on dot--breathe"></span>{esc(status)}</div>'
            f'<div class="tg-bio">{esc(bio)}</div></div></div>')


def pinned(text):
    """A pinned-message block (hours / how to book)."""
    return f'<div class="pinned"><span class="pinned-k">📌 закреплено</span><div class="pinned-x">{esc(text)}</div></div>'


# ── landing patterns (P4.2) ───────────────────────────────────────────────────
def hero(eyebrow, title_html, sub_html, cta_html="", aside_html=""):
    """title_html/sub_html are raw HTML (allow <em> accent, <br>). eyebrow is escaped."""
    eb = f'<div class="hero-eyebrow">{esc(eyebrow)}</div>' if eyebrow else ""
    aside = f'<div class="hero-aside">{aside_html}</div>' if aside_html else ""
    return (f'<div class="hero-stage"><div class="hero"><div class="hero-text">{eb}'
            f'<h1 class="hero-title">{title_html}</h1>'
            f'<p class="hero-sub">{sub_html}</p>'
            f'<div class="hero-cta">{cta_html}</div></div>{aside}</div></div>')


def chat_frame(name, channel, turns):
    """A messenger-style proof frame. turns: list of (who 'a'|'p', text, time)."""
    rows = ""
    for who, text, t in turns:
        tm = f'<span class="cf-t">{esc(t)}</span>' if t else ""
        rows += f'<div class="cf-row cf-row--{who}"><div class="b b--{who}">{esc(text)}</div>{tm}</div>'
    ini = esc(name[:1].upper()) if name else "•"
    return (f'<div class="cf"><div class="cf-head"><div class="ava ava--sm">{ini}</div>'
            f'<div class="cf-id"><b>{esc(name)}</b>'
            f'<span class="cf-status"><span class="dot dot--on dot--breathe"></span>{esc(channel)}</span></div></div>'
            f'<div class="cf-body">{rows}</div></div>')


def device(inner):
    """Wrap a chat_frame (or any product shot) in a premium floating device shell."""
    return f'<div class="cf-device">{inner}</div>'


# line-icon set (inline SVG, stroke=currentColor -> colored via CSS). Replaces emoji.
_ICONS = {
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>',
    "calendar": '<rect x="3" y="4.5" width="18" height="17" rx="2.5"/><path d="M16 2.5v4M8 2.5v4M3 9.5h18M8.5 15l2.2 2.2L15 13"/>',
    "chat": '<path d="M21 15a2 2 0 0 1-2 2H8l-4 4V5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z"/>',
    "shield": '<path d="M12 3l7 3v5c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8.2 12.2l2.6 2.6L16 9.5"/>',
    "leaf": '<path d="M11 20A7 7 0 0 1 4 13C4 8 9 4 20 4c0 8-4 13-9 13z"/><path d="M11 20c0-4 2-7 5-9"/>',
    "phone": '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3-8.6A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8.1 9.6a16 16 0 0 0 6 6l1.1-1.1a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
}


def icon(name, size=20):
    body = _ICONS.get(name, _ICONS["check"])
    return (f'<svg class="ic" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def features(items):
    """items: list of (icon, title, text)"""
    cards = [f'<div class="card feat"><div class="feat-icon">{ic}</div>'
             f'<div class="feat-title">{esc(t)}</div><div class="feat-text">{esc(x)}</div></div>'
             for ic, t, x in items]
    return f'<div class="grid" style="grid-template-columns:repeat({len(items)},1fr)">{"".join(cards)}</div>'


def steps(items):
    """items: list of (title, text)"""
    out = [f'<div class="step"><div class="step-num">{i}</div><div>'
           f'<div class="step-title">{esc(t)}</div><div class="step-text">{esc(x)}</div></div></div>'
           for i, (t, x) in enumerate(items, 1)]
    return f'<div class="steps">{"".join(out)}</div>'


def faq(items):
    """items: list of (question, answer)"""
    return "".join(f'<details class="faq"><summary>{esc(q)}</summary>'
                   f'<div class="faq-a">{esc(a)}</div></details>' for q, a in items)


def lead_form(fields, button_label="Оставить заявку", note="", success="Спасибо! Свяжемся в течение часа."):
    """fields: list of {id,label,placeholder,type?,required?}. Real client-side validation + states."""
    rows = ""
    for f in fields:
        star = ' <span style="color:var(--danger)">*</span>' if f.get("required") else ""
        req = f' data-req="1" data-label="{esc(f["label"])}"' if f.get("required") else ""
        rows += (f'<label class="lf-row"><span class="lf-label">{esc(f["label"])}{star}</span>'
                 f'<input class="input" id="lf-{f["id"]}" type="{f.get("type", "text")}" '
                 f'placeholder="{esc(f.get("placeholder", ""))}"{req}></label>')
    nt = subnote(note) if note else ""
    return (f'<form class="lf" id="leadform" onsubmit="return annaLeadSubmit(event)" novalidate>{rows}'
            f'<div class="lf-err" id="lf-err" role="alert" aria-live="polite"></div>'
            f'<button class="btn btn--primary" type="submit">{esc(button_label)}</button>{nt}</form>'
            f'<div class="lf-ok" id="lf-ok" hidden>✓ {esc(success)}</div>')


def cta_band(title, sub, button_html):
    return (f'<div class="cta-band"><div class="cta-title">{esc(title)}</div>'
            f'<div class="cta-sub">{esc(sub)}</div><div>{button_html}</div></div>')


def trust_strip(items):
    """items: list of short strings -> a thin ✓ strip"""
    return '<div class="trust">' + "".join(f'<span class="trust-i">{esc(t)}</span>' for t in items) + '</div>'


def section(eyebrow, title, inner, tint=False):
    eb = f'<div class="sec-eyebrow">{esc(eyebrow)}</div>' if eyebrow else ""
    ti = f'<h2 class="sec-title">{esc(title)}</h2>' if title else ""
    if tint:
        inner = f'<div class="zone">{inner}</div>'
    return f'<section class="lp-sec reveal">{eb}{ti}{inner}</section>'


def callout(icon, title, text):
    """Accent-bordered reassurance block — used to answer the #1 objection early."""
    return (f'<div class="callout"><div class="callout-ic">{icon}</div><div>'
            f'<div class="callout-t">{esc(title)}</div>'
            f'<div class="callout-x">{esc(text)}</div></div></div>')


def link_button(label, href, kind="ghost"):
    return f'<a class="btn btn--{kind}" href="{esc(href)}">{esc(label)}</a>'


# ── interactions (standard glue; surfaces opt-in) ─────────────────────────────
def scripts():
    return """<script>
function annaPick(id){
  document.querySelectorAll('.dlg').forEach(function(r){r.classList.remove('is-active')});
  var row=document.getElementById('row-'+id); if(row)row.classList.add('is-active');
  document.querySelectorAll('.thread').forEach(function(t){t.hidden=true});
  var th=document.getElementById('th-'+id); if(th)th.hidden=false;
}
function annaTab(el){
  el.parentNode.querySelectorAll('.tab').forEach(function(t){t.classList.remove('on')});
  el.classList.add('on'); annaToast('Период: '+el.textContent+' — демо. Реальные срезы из LEDGER.');
}
function annaFlag(btn){
  var b=btn.closest('.b'); b.classList.toggle('flagged');
  annaToast(b.classList.contains('flagged')
    ? 'Ответ помечен как ошибочный. ANNA учтёт (демо — сохранение с бэкендом).' : 'Метка снята.');
}
function annaTeach(){
  var i=document.getElementById('teach'); var v=(i&&i.value||'').trim();
  annaToast(v ? 'Принято: «'+v+'». ANNA учтёт (демо — сохранение с бэкендом L1).'
              : 'Напишите правило — ANNA запомнит ваш стиль.');
  if(v&&i)i.value='';
}
function annaHandoff(){ annaToast('Диалог передан администратору (демо). С бэкендом — реальная эстафета человеку.'); }
function annaLead(){ var f=document.getElementById('leadform'); if(!f)return;
  f.scrollIntoView({behavior:'smooth'}); var i=f.querySelector('input'); if(i)setTimeout(function(){i.focus()},420); }
function annaLeadSubmit(e){ e.preventDefault();
  var f=document.getElementById('leadform'), bad=[];
  f.querySelectorAll('input[data-req]').forEach(function(i){
    if(!i.value.trim()){ i.classList.add('invalid'); bad.push(i); } else i.classList.remove('invalid'); });
  var err=document.getElementById('lf-err');
  if(bad.length){ err.textContent='Заполните, пожалуйста: '+bad.map(function(i){return i.getAttribute('data-label')}).join(', ')+'.';
    bad[0].focus(); return false; }
  err.textContent=''; f.hidden=true;
  var ok=document.getElementById('lf-ok'); if(ok)ok.hidden=false;
  annaToast('Заявка принята (демо — бэкенд формы L2). Спасибо!'); return false; }
var _annaT;
function annaToast(msg){
  var el=document.getElementById('toast'); if(!el)return;
  el.textContent=msg; el.classList.add('show');
  clearTimeout(_annaT); _annaT=setTimeout(function(){el.classList.remove('show')},3200);
}
(function(){  /* chat comes alive: reveal turns in sequence (reduced-motion: all visible) */
  if(!window.matchMedia||!matchMedia('(prefers-reduced-motion: no-preference)').matches)return;
  document.addEventListener('DOMContentLoaded',function(){
    var rows=document.querySelectorAll('.cf-body .cf-row');
    rows.forEach(function(r,i){
      r.style.opacity=0; r.style.transform='translateY(7px)';
      r.style.transition='opacity .45s ease, transform .45s ease';
      setTimeout(function(){ r.style.opacity=1; r.style.transform='none'; }, 350+i*430);
    });
  });
})();
(function(){  /* section scroll-reveal: default visible; JS opts in only when safe */
  if(!('IntersectionObserver' in window))return;
  if(!matchMedia('(prefers-reduced-motion: no-preference)').matches)return;
  document.documentElement.classList.add('reveal-ready');
  var io=new IntersectionObserver(function(es){
    es.forEach(function(e){ if(!e.isIntersecting)return; e.target.classList.add('in'); io.unobserve(e.target); });
  },{rootMargin:'0px 0px -12% 0px',threshold:.12});
  document.querySelectorAll('.reveal').forEach(function(el){io.observe(el);});
})();
</script>"""


def css(P=None):
    P = P or palette()
    return f"""<style>
 :root{{
  --bg:{P['bg']};--surface:{P['surface']};--surface2:{P['surface_2']};--ink:{P['ink']};
  --muted:{P['muted']};--primary:{P['primary']};--primary-soft:{P['primary_soft']};
  --accent:{P['accent']};--accent-deep:{P['accent_deep']};--success:{P['success']};
  --warning:{P['warning']};--danger:{P['danger']};
  --radius:12px;--radius-lg:20px;--r-xl:28px;
  --sh-1:0 1px 2px rgba(46,61,52,.05),0 6px 16px -6px rgba(46,61,52,.10);
  --sh-2:0 4px 12px rgba(46,61,52,.07),0 16px 34px -10px rgba(46,61,52,.13);
  --sh-3:0 24px 60px -18px rgba(46,61,52,.22);
  --shadow:var(--sh-1);
  --font:Inter,system-ui,-apple-system,sans-serif;--serif:Lora,Georgia,serif;
 }}
 body::before{{content:"";position:fixed;inset:0;z-index:-2;pointer-events:none;opacity:.022;mix-blend-mode:multiply;
  background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}}
 *{{box-sizing:border-box}}
 body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);
  font-size:16px;line-height:1.5;-webkit-font-smoothing:antialiased}}
 .wrap{{max-width:1080px;margin:0 auto;padding:24px 22px 80px}}
 a{{color:var(--primary);text-decoration:none}}
 /* bar */
 .bar{{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:8px}}
 .brand{{font-family:var(--serif);font-size:26px;font-weight:700;color:var(--primary);letter-spacing:-.01em}}
 .clinic{{color:var(--muted);font-size:14px}} .spacer{{flex:1}}
 .sub{{color:var(--muted);margin:2px 0 18px;font-size:14px}}
 .h{{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:2px 0 12px}}
 .chips{{display:flex;gap:6px}}
 .tab{{border:1px solid rgba(46,61,52,.10);background:var(--surface);border-radius:999px;
  padding:6px 14px;font-size:13px;color:var(--muted);cursor:pointer;user-select:none}}
 .tab.on{{background:var(--primary);color:#fff;border-color:var(--primary)}}
 .note{{display:flex;gap:10px;align-items:flex-start;background:color-mix(in srgb,var(--accent) 24%,var(--surface));
  border:1px solid color-mix(in srgb,var(--accent) 42%,var(--surface));
  color:color-mix(in srgb,var(--accent-deep) 80%,#000);border-radius:var(--radius);padding:12px 15px;font-size:13.5px;margin:14px 0 20px}}
 .note b{{color:color-mix(in srgb,var(--accent-deep) 88%,#000)}}
 /* layout */
 .grid{{display:grid;gap:14px;margin-bottom:18px}}
 .cols{{display:grid;grid-template-columns:1.3fr 1fr;gap:18px;align-items:start}}
 .card{{background:var(--surface);border:1px solid rgba(46,61,52,.08);border-radius:var(--radius-lg);
  padding:22px 24px;box-shadow:var(--sh-1);margin-bottom:14px}}
 @media(prefers-reduced-motion:no-preference){{.card{{transition:box-shadow .16s ease}}.card:hover{{box-shadow:var(--sh-2)}}}}
 /* kpi */
 .kpi{{position:relative}}
 .kpi-tag{{position:absolute;top:14px;right:16px;font-size:11px;font-weight:600;text-transform:uppercase;
  letter-spacing:.04em;color:var(--accent-deep)}}
 .kpi-val{{font-family:var(--serif);font-size:39px;font-weight:700;color:var(--ink);line-height:1}}
 .kpi-title{{color:var(--muted);font-size:13.5px;margin-top:8px}}
 /* button */
 .btn{{border:none;border-radius:var(--radius);padding:13px 22px;font:600 15px var(--font);
  cursor:pointer;margin:0 6px 6px 0;letter-spacing:.005em}}
 .btn--primary{{background:var(--primary);color:#fff;box-shadow:0 6px 16px -6px rgba(84,112,92,.55)}} .btn--accent{{background:var(--accent);color:var(--ink)}}
 .btn--ghost{{background:transparent;color:var(--primary);border:1.5px solid var(--primary)}}
 @media(prefers-reduced-motion:no-preference){{.btn--primary{{transition:box-shadow .16s,transform .16s}}.btn--primary:hover{{box-shadow:0 10px 22px -6px rgba(84,112,92,.6);transform:translateY(-1px)}}}}
 .btn:focus-visible{{outline:3px solid var(--primary-soft);outline-offset:2px}}
 /* chip */
 .chip{{font-size:12px;font-weight:600;border-radius:999px;padding:3px 9px;white-space:nowrap;margin-right:6px}}
 .chip--ok{{color:#2c4a37;background:#dcebe0}} .chip--wait{{color:var(--accent-deep);background:color-mix(in srgb,var(--accent) 28%,var(--surface))}}
 .chip--mute{{color:var(--muted);background:var(--surface2)}} .chip--danger{{color:#fff;background:var(--danger)}}
 /* pill */
 .pill{{display:inline-flex;align-items:center;gap:8px;background:var(--surface);
  border:1px solid rgba(46,61,52,.08);border-radius:999px;padding:7px 14px;font-size:14px;
  font-weight:500;box-shadow:var(--shadow)}}
 .dot{{width:9px;height:9px;border-radius:50%;display:inline-block}}
 .dot--on{{background:var(--success)}} .dot--off{{background:var(--danger)}} .dot--unknown{{background:var(--muted)}}
 /* avatar */
 .ava{{width:38px;height:38px;border-radius:50%;background:var(--primary);color:#fff;
  display:inline-flex;align-items:center;justify-content:center;font-weight:600;flex:0 0 38px}}
 /* dialog list */
 .dlg{{display:flex;align-items:center;gap:12px;padding:11px 8px;border-radius:12px;
  border-bottom:1px solid rgba(46,61,52,.06);cursor:pointer;transition:background .12s}}
 .dlg:last-child{{border-bottom:none}} .dlg:hover{{background:var(--bg)}}
 .dlg.is-active{{background:#eef3ee;border-bottom-color:transparent}}
 .dlg-body{{flex:1;min-width:0}} .dlg-top{{display:flex;justify-content:space-between;gap:8px}}
 .dlg-name{{font-weight:600}} .dlg-time{{color:var(--muted);font-size:13px}}
 .dlg-prev{{color:var(--muted);font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
 /* thread + bubbles */
 .thread{{margin-top:16px;padding-top:16px;border-top:1px dashed rgba(46,61,52,.12)}}
 .brow{{display:flex;justify-content:flex-start}} .brow--p{{justify-content:flex-end}}
 .b{{position:relative;max-width:80%;padding:11px 15px;margin:7px 0;font-size:14.5px;border-radius:16px}}
 .b--a{{background:var(--primary-soft);color:#1f2c24;border-bottom-left-radius:5px}}
 .b--p{{background:var(--surface2);color:var(--ink);border-bottom-right-radius:5px}}
 .flag{{position:absolute;top:-9px;right:-9px;width:22px;height:22px;border-radius:50%;
  border:1px solid rgba(46,61,52,.12);background:var(--surface);color:var(--muted);font-size:11px;
  cursor:pointer;line-height:1;opacity:0;transition:opacity .12s}}
 .brow:hover .flag{{opacity:1}}
 .b.flagged{{box-shadow:0 0 0 2px var(--warning) inset}}
 .b.flagged .flag{{opacity:1;background:var(--warning);color:#fff;border-color:var(--warning)}}
 .actions{{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}}
 /* bookings */
 .bk{{display:flex;gap:12px;align-items:center;padding:11px 4px;border-bottom:1px solid rgba(46,61,52,.06)}}
 .bk:last-child{{border-bottom:none}} .bk-dot{{font-size:13px}}
 .bk-svc{{font-weight:600;font-size:15px}} .bk-meta{{color:var(--muted);font-size:13.5px}}
 .subnote{{color:var(--muted);font-size:12.5px;margin-top:12px;padding-top:12px;border-top:1px dashed rgba(46,61,52,.12)}}
 /* field */
 .input{{width:100%;border:1.5px solid var(--surface2);border-radius:var(--radius);padding:12px 14px;
  font:16px var(--font);color:var(--ink);background:var(--surface)}}
 .input:focus-visible{{outline:none;border-color:var(--primary-soft);box-shadow:0 0 0 3px rgba(138,168,151,.35)}}
 /* toast */
 .toast{{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(20px);
  background:var(--ink);color:#fff;padding:13px 20px;border-radius:12px;font-size:14px;opacity:0;
  pointer-events:none;transition:all .25s;box-shadow:0 10px 40px rgba(0,0,0,.2);max-width:90%}}
 .toast.show{{transform:translateX(-50%) translateY(0);opacity:1}}
 .foot{{margin-top:32px;color:var(--muted);font-size:12.5px;line-height:1.7}}
 /* landing patterns */
 .hero-stage{{position:relative;isolation:isolate;margin-top:6px;overflow:hidden;padding-bottom:1px}}
 .hero-stage::before{{content:"";position:absolute;z-index:-1;top:-34px;left:50%;transform:translateX(-50%);
  width:min(1180px,112%);height:540px;border-radius:0 0 46% 46%/0 0 20% 20%;
  background:radial-gradient(120% 90% at 50% 0%,color-mix(in srgb,var(--primary) 12%,var(--bg)) 0%,color-mix(in srgb,var(--accent) 8%,var(--bg)) 44%,var(--bg) 74%);opacity:.95}}
 .hero-stage::after{{content:"";position:absolute;z-index:-1;top:2px;left:50%;transform:translateX(-50%);
  width:min(1040px,101%);height:470px;border-radius:0 0 46% 46%/0 0 20% 20%;
  border:1.5px solid var(--primary-soft);border-top:none;opacity:.20}}
 .hero{{display:grid;grid-template-columns:1.12fr .88fr;gap:38px;align-items:center;padding:clamp(26px,5vw,58px) 0 22px}}
 .hero-eyebrow{{display:inline-flex;align-items:center;gap:7px;color:var(--accent-deep);background:color-mix(in srgb,var(--accent) 30%,var(--surface));font-size:12px;
  font-weight:600;text-transform:uppercase;letter-spacing:.09em;padding:6px 13px;border-radius:999px;margin-bottom:18px}}
 .hero-title{{font-family:var(--serif);font-size:clamp(38px,5.2vw,60px);line-height:1.04;font-weight:600;color:var(--ink);
  margin:0 0 18px;text-wrap:balance;letter-spacing:-.02em}}
 .hero-title em{{color:var(--primary);font-style:italic}}
 .hero-sub{{font-size:18px;color:color-mix(in srgb,var(--ink) 84%,var(--bg));line-height:1.6;margin:0 0 24px;max-width:31em}}
 .hero-cta{{display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
 .hero-note{{flex-basis:100%;font-size:12.5px;color:var(--muted);margin-top:12px}}
 .hero-note::before{{content:'✓ ';color:var(--primary);font-weight:700}}
 .hero-aside{{align-self:center;position:relative}}
 .hero-aside::after{{content:"";position:absolute;z-index:-1;right:-4%;bottom:-6%;width:66%;height:66%;
  background:radial-gradient(closest-side,rgba(217,166,121,.20),transparent);filter:blur(4px)}}
 .cf-device{{max-width:360px;margin:0 auto;padding:10px;border-radius:56px 56px var(--r-xl) var(--r-xl);
  background:linear-gradient(160deg,#fff,#F3F1EB);border:1px solid rgba(46,61,52,.10);box-shadow:var(--sh-3);
  transform:rotate(-1.4deg)}}
 .cf-device .cf{{border-radius:48px 48px 18px 18px}}
 .cf-device .cf-head{{padding-top:16px;justify-content:center;text-align:left}}
 @media(prefers-reduced-motion:no-preference){{.cf-device{{transition:transform .4s ease}}
  .cf-device:hover{{transform:rotate(0) translateY(-4px)}}}}
 .cf{{background:var(--surface);border:1px solid rgba(46,61,52,.07);border-radius:18px;overflow:hidden}}
 .cf-head{{display:flex;align-items:center;gap:10px;padding:11px 15px;border-bottom:1px solid rgba(46,61,52,.06)}}
 .ava--sm{{width:32px;height:32px;font-size:13px;flex:0 0 32px}}
 .cf-id b{{font-size:14px;display:block;line-height:1.1}}
 .cf-status{{display:inline-flex;align-items:center;gap:6px;color:var(--muted);font-size:12px;margin-top:1px}}
 .cf-body{{padding:12px 15px 16px}}
 .cf-row{{display:flex;flex-direction:column;margin:7px 0}}
 .cf-row--p{{align-items:flex-end}} .cf-row--a{{align-items:flex-start}}
 .cf-row .b{{max-width:86%;margin:0}}
 .cf-row .b--a{{box-shadow:inset 0 1px 0 rgba(255,255,255,.35)}}
 .cf-t{{font-size:11px;color:var(--muted);margin:3px 7px 0}}
 @keyframes breathe{{0%,100%{{opacity:.5;transform:scale(.82)}}50%{{opacity:1;transform:scale(1)}}}}
 @media(prefers-reduced-motion:no-preference){{.dot--breathe{{animation:breathe 3s ease-in-out infinite}}}}
 .ic{{vertical-align:middle;flex:0 0 auto}}
 .zone{{background:color-mix(in srgb,var(--primary) 8%,var(--surface));border:1px solid color-mix(in srgb,var(--primary) 16%,var(--surface));border-radius:var(--radius-lg);padding:26px 28px;box-shadow:var(--sh-1)}}
 .tg-prof{{display:flex;gap:16px;align-items:flex-start}}
 .ava--lg{{width:64px;height:64px;font-size:26px;flex:0 0 64px}}
 .tg-name{{font-weight:700;font-size:18px}}
 .tg-h{{color:var(--muted);font-weight:400;font-size:14px}}
 .tg-status{{display:inline-flex;align-items:center;gap:6px;color:var(--muted);font-size:13px;margin:3px 0 8px}}
 .tg-bio{{color:#3d4c43;font-size:14.5px;line-height:1.55;max-width:40em}}
 .pinned{{border-left:3px solid var(--primary-soft);background:#f3f6f2;border-radius:0 var(--radius) var(--radius) 0;padding:12px 16px}}
 .pinned-k{{color:var(--primary);font-size:12px;font-weight:600}}
 .pinned-x{{color:var(--ink);font-size:14.5px;line-height:1.55;margin-top:4px}}
 .feat{{margin-bottom:0}} .feat-icon{{font-size:26px;margin-bottom:10px}}
 .feat-title{{font-weight:700;font-size:18px;margin-bottom:6px}} .feat-text{{color:var(--muted);font-size:14.5px}}
 .steps{{display:flex;flex-direction:column;gap:14px}} .step{{display:flex;gap:14px;align-items:flex-start}}
 .step-num{{flex:0 0 32px;width:32px;height:32px;border-radius:50%;background:var(--primary);color:#fff;
  display:flex;align-items:center;justify-content:center;font-weight:700;font-family:var(--serif)}}
 .step-title{{font-weight:600}} .step-text{{color:var(--muted);font-size:14.5px}}
 details.faq{{border-bottom:1px solid rgba(46,61,52,.08);padding:14px 2px}}
 details.faq summary{{cursor:pointer;font-weight:600;list-style:none}}
 details.faq summary::-webkit-details-marker{{display:none}}
 details.faq summary::before{{content:'+ ';color:var(--primary);font-weight:700}}
 details.faq[open] summary::before{{content:'– '}}
 .faq-a{{color:var(--muted);font-size:14.5px;margin-top:8px}}
 .lead{{display:flex;gap:8px;flex-wrap:wrap}} .lead .input{{flex:1;min-width:150px}}
 .cta-band{{background:linear-gradient(135deg,var(--primary),color-mix(in srgb,var(--primary) 76%,#000));color:#fff;border-radius:var(--r-xl);
  padding:clamp(34px,5vw,52px) 30px;text-align:center;margin-top:12px;box-shadow:var(--sh-2)}}
 .cta-title{{font-family:var(--serif);font-size:clamp(26px,3.4vw,34px);font-weight:600;margin-bottom:10px;letter-spacing:-.01em}}
 .cta-sub{{opacity:.9;margin-bottom:20px}} .cta-band .btn--primary{{background:#fff;color:var(--primary);box-shadow:0 8px 20px -6px rgba(0,0,0,.3)}}
 .callout{{display:flex;gap:14px;align-items:flex-start;background:color-mix(in srgb,var(--primary) 8%,var(--surface));
  border:1px solid color-mix(in srgb,var(--primary) 20%,var(--surface));
  border-left:4px solid var(--primary);border-radius:var(--radius-lg);padding:20px 22px;box-shadow:var(--sh-1)}}
 .callout-ic{{flex:0 0 auto;color:var(--primary);display:flex;align-items:flex-start;line-height:1}}
 .callout-ic .ic{{margin-top:1px}}
 .callout-t{{font-weight:700;margin-bottom:4px}}
 .callout-x{{color:var(--muted);font-size:14.5px;line-height:1.55}}
 a.btn{{display:inline-block;text-decoration:none;text-align:center}}
 .lp-sec{{margin:clamp(52px,8vw,88px) 0}}
 .lp-sec>.card:last-child,.lp-sec>.card:only-child{{margin-bottom:0}}
 .hero-cta .btn,.actions .btn,.cta-band .btn,.lf .btn{{margin:0}}
 .sec-eyebrow{{position:relative;padding-top:20px;color:var(--accent-deep);font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px}}
 .sec-eyebrow::before{{content:"";position:absolute;top:0;left:0;width:22px;height:11px;opacity:.85;background:var(--primary);
  -webkit-mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='22' height='11'%3E%3Cpath d='M1 11V6a10 10 0 0 1 20 0v5' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round'/%3E%3C/svg%3E") no-repeat center/22px 11px;
  mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='22' height='11'%3E%3Cpath d='M1 11V6a10 10 0 0 1 20 0v5' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round'/%3E%3C/svg%3E") no-repeat center/22px 11px}}
 .sec-title{{font-family:var(--serif);font-size:clamp(26px,3vw,32px);font-weight:600;color:var(--ink);margin:0 0 20px;letter-spacing:-.015em}}
 .trust{{display:flex;flex-wrap:wrap;gap:10px;margin:4px 0}}
 .trust-i{{display:inline-flex;align-items:center;background:color-mix(in srgb,var(--primary) 8%,var(--surface));
  border:1px solid color-mix(in srgb,var(--primary) 18%,var(--surface));border-radius:999px;
  padding:8px 15px 8px 9px;font-size:13.5px;font-weight:600;color:color-mix(in srgb,var(--ink) 82%,var(--bg))}}
 .trust-i::before{{content:'✓';display:inline-flex;align-items:center;justify-content:center;margin-right:8px;
  color:#fff;background:var(--primary);width:17px;height:17px;line-height:17px;flex:0 0 17px;border-radius:50%;font-size:10px;font-weight:800}}
 .brand-lockup{{display:inline-flex;align-items:center;gap:9px}}
 .arch-mark{{flex:0 0 auto;transform:translateY(1px)}}
 @media(prefers-reduced-motion:no-preference){{.bar .arch-mark path:first-child{{stroke-dasharray:60;stroke-dashoffset:60;animation:archDraw 1.1s .25s ease forwards}}}}
 @keyframes archDraw{{to{{stroke-dashoffset:0}}}}
 .warm-divider{{display:flex;align-items:center;justify-content:center;margin:clamp(40px,6vw,64px) 0}}
 .warm-divider::before,.warm-divider::after{{content:"";height:1px;flex:1;max-width:220px}}
 .warm-divider::before{{background:linear-gradient(90deg,transparent,rgba(217,166,121,.55))}}
 .warm-divider::after{{background:linear-gradient(90deg,rgba(217,166,121,.55),transparent)}}
 .warm-divider svg{{margin:0 16px;opacity:.9}}
 .step-num{{box-shadow:0 0 0 4px #EDF1EB,0 4px 10px -3px rgba(84,112,92,.4)}}
 .steps .step:not(:last-child)::before{{background:linear-gradient(var(--primary-soft),rgba(138,168,151,.15))}}
 .foot{{margin-top:56px;padding-top:22px;border-top:1px solid rgba(46,61,52,.08);display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
 .foot .arch-mark{{opacity:.5}}
 .foot-tag{{margin-left:auto;font-family:var(--serif);font-style:italic;color:var(--primary-soft)}}
 .reveal-ready .reveal{{opacity:0;transform:translateY(18px)}}
 .reveal-ready .reveal.in{{opacity:1;transform:none;transition:opacity .6s cubic-bezier(.22,.61,.36,1),transform .6s cubic-bezier(.22,.61,.36,1)}}
 @media(prefers-reduced-motion:reduce){{.reveal-ready .reveal{{opacity:1!important;transform:none!important;transition:none}}}}
 .lf{{display:flex;flex-direction:column;gap:13px}}
 .lf-row{{display:flex;flex-direction:column;gap:6px}}
 .lf-label{{font-size:13px;color:var(--muted);font-weight:500}}
 .input.invalid{{border-color:var(--danger);box-shadow:0 0 0 3px rgba(192,83,59,.15)}}
 .lf-err{{color:var(--danger);font-size:13.5px}} .lf-err:empty{{display:none}}
 .lf-ok{{background:#dcebe0;border:1px solid #bcdcc6;color:#2c4a37;border-radius:var(--radius);padding:16px 18px;font-weight:500}}
 .lf .btn{{align-self:flex-start}}
 .step{{position:relative}}
 .steps .step:not(:last-child)::before{{content:'';position:absolute;left:15px;top:36px;bottom:-14px;width:2px;background:var(--surface2)}}
 .feat{{transition:box-shadow .15s ease, transform .15s ease}}
 @media(prefers-reduced-motion:no-preference){{.feat:hover{{box-shadow:0 12px 32px rgba(46,61,52,.10);transform:translateY(-2px)}}}}
 @media(prefers-reduced-motion:no-preference){{.btn{{transition:transform .08s ease}}.btn:active{{transform:translateY(1px)}}
  .feat,.card{{transition:box-shadow .15s ease}}}}
 @media(max-width:860px){{.kpis,.grid{{grid-template-columns:repeat(2,1fr)!important}}.cols{{grid-template-columns:1fr}}
  .hero{{grid-template-columns:1fr;gap:24px}}.hero-title{{font-size:clamp(32px,8vw,42px)}}.sec-title{{font-size:24px}}
  .hero-br{{display:none}}.cf-device{{transform:none}}}}
</style>"""


def page(title, body, subtitle="", P=None, top_html=None, with_scripts=False):
    """top_html overrides the default brand header (e.g. a full topbar()).
    with_scripts injects the standard interaction glue + a toast container."""
    P = P or palette()
    head = top_html if top_html is not None else f'<div class="brand">{esc(title)}</div>'
    sub = f'<p class="sub">{esc(subtitle)}</p>' if subtitle else ""
    toast = '<div class="toast" id="toast"></div>' if with_scripts else ""
    js = scripts() if with_scripts else ""
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{esc(title)}</title>{css(P)}</head><body><div class="wrap">'
            f'{head}{sub}{body}</div>{toast}{js}</body></html>')


# ── self-test: component preview proving the renderer works ───────────────────
def _preview():
    P = palette()
    body = []
    body.append(card(grid([kpi("48", "Обращений", "пример"), kpi("31", "Записей", "пример"),
                           kpi("12", "Возвращено*", "пример"), kpi("—", "Выручка ₽", "из LEDGER")], 4), "KPI"))
    body.append(card(button("Записать") + button("Подтвердить", "accent") + button("Передать", "ghost"), "Кнопки"))
    body.append(card(badge("записан", "ok") + badge("ждёт", "wait") + badge("отвечено", "mute") + badge("ошибка", "danger"), "Бейджи"))
    body.append(card(pill("ANNA на связи · 18:06", "on"), "Статус"))
    body.append(card(thread("demo",
                            bubble("Болит зуб справа сверху, можно сегодня?", "p")
                            + bubble("Ирина, здравствуйте. Сегодня есть окно в 16:30. Записать вас?", "a", flag=True),
                            header="Диалог (наведи на ответ ANNA → разметить)"), "Диалог"))
    body.append(card(booking_row("Лечение кариеса", "Ирина К.", "сегодня 16:30") + booking_row("Консультация", "Алексей П.", "ждёт", "pending"), "Записи"))
    body.append(card(field("Напр.: о рассрочке — предлагать консультацию", "teach") + button("Научить", onclick="annaTeach()"), "Обучение ANNA"))
    body.append('<p class="foot">продуктовый рендерер · ANNA_DESIGN_CANON_V1 (D3) · твин socc_canon_html.py · НЕ матрица<br>'
                'preview: <span style="color:var(--ink)">python3 SYSTEM/BRAND_FORGE/canon/anna_canon_html.py</span></p>')
    return page("анна · компоненты", "".join(body),
                subtitle="живой превью-лист · всё через anna_canon_html (один источник стиля)",
                P=P, with_scripts=True)


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "runtime" / "ANNA_CANON_PREVIEW.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_preview(), encoding="utf-8")
    print(f"[anna_canon_html] preview -> {out}")

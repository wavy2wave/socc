#!/usr/bin/env python3
"""
ATELIER — living styleguide / design-system gallery generator.

Renders the WHOLE design system, each canon in its OWN skin (SOCC_SURFACE_LAW):
  - DESIGN_SYSTEM_ANNA.html  — product canon D3 "Спокойная забота" (via anna_canon_html)
  - DESIGN_SYSTEM_SOCC.html  — operator matrix canon (via socc_canon_html, reused not rebuilt)
  - DESIGN_SYSTEM_INDEX.html — operator overview + surface law + links

This is the single source of truth a designer/engineer looks at. Deterministic,
no network, no daemon. Re-run after touching either renderer:

    python3 SYSTEM/ATELIER/socc_design_system.py
"""
import sys
from pathlib import Path
from datetime import datetime

SOCC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOCC / "SYSTEM" / "BRAND_FORGE" / "canon"))
sys.path.insert(0, str(SOCC / "SYSTEM" / "INTERFACE" / "dashboard"))
import anna_canon_html as A          # product renderer (D3)
import socc_canon_html as S          # operator renderer (matrix) — reused

OUT = SOCC / "SYSTEM" / "ATELIER" / "runtime"
GEN = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


# ── ANNA (product D3) gallery ─────────────────────────────────────────────────
def anna_swatches(P):
    order = [("primary", "primary · sage"), ("primary_soft", "primary-soft"),
             ("accent", "accent · sand"), ("accent_deep", "accent-deep"),
             ("ink", "ink · text"), ("muted", "muted"), ("bg", "bg"),
             ("surface_2", "surface-2"), ("success", "success"),
             ("warning", "warning"), ("danger", "danger")]
    chips = []
    for key, label in order:
        hexv = P[key]
        txt = "#fff" if key in ("primary", "accent_deep", "ink", "success", "danger") else "var(--ink)"
        chips.append(
            f'<div style="border-radius:14px;overflow:hidden;border:1px solid rgba(46,61,52,.08)">'
            f'<div style="height:54px;background:{hexv}"></div>'
            f'<div style="padding:8px 10px;font-size:12px;background:var(--surface)">'
            f'<div style="font-weight:600">{label}</div>'
            f'<div style="color:var(--muted)">{hexv}</div></div></div>')
    return f'<div class="grid" style="grid-template-columns:repeat(4,1fr)">{"".join(chips)}</div>'


def anna_typescale():
    rows = [("4xl 49", "49px", "Спокойная забота"), ("2xl 31", "31px", "Тёплый администратор клиники"),
            ("xl 25", "25px", "Каждый пациент — как самый важный"), ("lg 20", "20px", "Запишу на удобное время"),
            ("base 16", "16px", "Здравствуйте! Чем могу помочь?"), ("sm 14", "14px", "вспомогательный текст")]
    out = []
    for name, size, sample in rows:
        serif = "font-family:var(--serif)" if size in ("49px", "31px") else ""
        out.append(f'<div style="display:flex;gap:16px;align-items:baseline;padding:8px 0;border-bottom:1px solid rgba(46,61,52,.06)">'
                   f'<span style="color:var(--muted);font-size:12px;min-width:64px">{name}</span>'
                   f'<span style="font-size:{size};{serif}">{sample}</span></div>')
    return "".join(out)


def product_gallery(P, title, subtitle, voice):
    """SAME components, ANY skin. Given a palette P -> the whole styleguide reskins."""
    b = []
    b.append(A.card(anna_swatches(P), "Цвет · палитра"))
    b.append(A.card(anna_typescale(), "Типографика · Inter + Lora"))
    b.append(A.card(A.button("Записать") + A.button("Подтвердить", "accent") + A.button("Передать", "ghost"),
                    "Кнопки · primary / accent / ghost"))
    b.append(A.card(A.badge("записан", "ok") + A.badge("ждёт", "wait") + A.badge("отвечено", "mute") + A.badge("ошибка", "danger")
                    + '&nbsp;&nbsp;' + A.pill("на связи", "on"), "Бейджи · статус-пилюля"))
    b.append(A.card(A.grid([A.kpi("48", "Обращений", "пример"), A.kpi("31", "Записей", "пример"),
                            A.kpi("12", "Возвращено*", "пример"), A.kpi("—", "Выручка ₽", "из LEDGER")], 4),
                    "KPI · метрики (ROI только из LEDGER)"))
    b.append(A.card(
        A.dialog_row("g1", "И", "Ирина", "14:32", "Здравствуйте, можно записаться?", A.badge("записан", "ok"), active=True)
        + A.thread("g1", A.bubble("Здравствуйте, можно записаться?", "p")
                   + A.bubble("Здравствуйте! Есть окно в 16:30. Записать вас?", "a", flag=True),
                   header="наведи на ответ → разметить ошибку"),
        "Диалог · список + ветка + разметка"))
    b.append(A.card(A.booking_row("Услуга", "Ирина К.", "сегодня 16:30")
                    + A.booking_row("Консультация", "Алексей П.", "ждёт", "pending")
                    + A.subnote("Реальная синхронизация календаря — L2, в разработке."), "Записи"))
    b.append(A.card(A.field("Напр.: правило для ответа", "teach") + A.button("Научить", onclick="annaTeach()"),
                    "Поле ввода · обучение"))
    b.append(A.banner(voice))
    b.append('<p class="foot">' + A.arch_mark(20) + ' продуктовая дизайн-система · palette-driven · '
             f'всё через один рендерер · НЕ матрица · {GEN}</p>')
    return A.page(title, "".join(b), subtitle=subtitle, P=P, with_scripts=True)


# ── SOCC (operator matrix) gallery ────────────────────────────────────────────
def socc_swatch_row(P):
    order = [("primary", "primary"), ("success", "success"), ("warning", "warning"),
             ("danger", "danger"), ("event", "event"), ("text", "text"), ("muted", "muted"), ("surface", "surface")]
    chips = []
    for key, label in order:
        hexv = P[key]
        chips.append(f'<span style="display:inline-block;margin:0 10px 10px 0;text-align:center">'
                     f'<span style="display:block;width:54px;height:34px;border-radius:6px;background:{hexv};border:1px solid #2b3340"></span>'
                     f'<span style="font-size:11px;color:{P["muted"]}">{label}<br>{hexv}</span></span>')
    return "".join(chips)


def socc_gallery():
    P = S.palette()
    b = []
    b.append(S.divider("COLOR · matrix palette"))
    b.append(S.line(socc_swatch_row(P)))
    b.append(S.divider("STATUS BADGES"))
    b.append(S.line(S.badge("PASS", P) + " " + S.badge("REVIEW", P) + " " + S.badge("FAIL", P)
                    + " " + S.badge("SEALED", P) + " " + S.badge("PENDING", P)))
    b.append(S.divider("STATE DOTS · MARKERS"))
    b.append(S.line(S.dot(True, P) + " running &nbsp; " + S.dot(False, P) + " idle &nbsp;&nbsp; "
                    + '<span class="ok">✓</span> ok · <span class="no">✗</span> fail · ⛔ do-not · ❓ open · ↳ source'))
    b.append(S.divider("ROWS"))
    b.append(S.row("cell", "ATELIER_CELL_V1", P))
    b.append(S.row("status", S.badge("GENESIS", P), P))
    b.append(S.row("lawful_next", '<span class="muted">F2.3 operator component parity</span>', P))
    b.append(S.divider("DEPTH · ELEVATION (technologicalness)"))
    b.append(S.grid([S.kpi("s0", "base #0B0F14"), S.kpi("s1", "recessed"),
                     S.kpi("s2", "surface"), S.kpi("s3", "raised")], 4))
    b.append(S.panel(S.row("panel", "elevated operator card — layering + luminous hairline, no drop-shadow", P)
                     + S.row("hover", '<span class="muted">edge brightens + lifts 1px (reduced-motion-safe)</span>', P),
                     "PANEL · depth by layering"))
    b.append('<div class="glass" style="padding:16px 18px;margin:12px 0">'
             + S.line('<b style="color:var(--primary)">GLASS</b> — matrix translation of Apple Liquid Glass: '
                      'blur + translucency + luminous edge. Functional only, sparingly. '
                      '<span class="muted">degrades to solid under Reduced Transparency.</span>') + '</div>')
    b.append(S.line('press ' + S.kbd("g") + ' ' + S.kbd("d") + ' — keycaps · '
                    '<span class="muted">grid backdrop is the faint 42px cyberpunk lattice behind this page.</span>'))
    b.append(S.divider("VOICE"))
    b.append(S.line('calm, precise, honest — no hype, no fake PASS. русский оператору, english для canon-ключей.'))
    b.append(f'<p class="foot">операторская дизайн-система · SOCC_DESIGN_CANON_V1 (matrix) · всё через socc_canon_html · '
             f'НЕ продуктовый канон · сгенерировано {GEN}</p>')
    return S.page("SOCC — DESIGN SYSTEM (OPERATOR)", "".join(b),
                  subtitle="операторский styleguide · matrix-minimalism · reused renderer, не дубль", P=P)


# ── INDEX (operator canon) ────────────────────────────────────────────────────
def index():
    P = S.palette()
    b = []
    b.append(S.divider("ATELIER · design-system studio"))
    b.append(S.row("organ", "ATELIER_CELL_V1 " + S.badge("GENESIS", P), P))
    b.append(S.row("principle", '<span class="muted">one living system · two canons · zero bespoke CSS</span>', P))
    b.append(S.row("renderers", '<span class="muted">anna_canon_html (D3) · socc_canon_html (matrix, reused)</span>', P))
    b.append(S.divider("STYLEGUIDES (click)"))
    b.append(S.line('↳ <a href="DESIGN_SYSTEM_SOCC.html">SOCC — оператор (matrix)</a> '
                    '<span class="muted">тёмный, для создателя</span>'))
    b.append(S.divider("BRAND FACTORY — one engine · N skins"))
    for name, sk in A.skins().items():
        pal = sk.get("palette", {})
        sw = "".join(f'<span style="display:inline-block;width:12px;height:12px;border-radius:3px;'
                     f'background:{pal.get(k, "#000")};margin-right:2px;border:1px solid #0005;vertical-align:middle"></span>'
                     for k in ("primary", "accent", "bg"))
        land = sk.get("landing", "")
        land_a = f' · <a href="../../BRAND_FORGE/{land}">лендинг</a>' if land else ""
        b.append(S.line(f'{sw} <b>{sk.get("label", name)}</b> — '
                        f'<a href="DESIGN_SYSTEM_{name.upper()}.html">styleguide</a>{land_a} '
                        f'<span class="muted">{sk.get("direction", "")}</span>'))
    b.append(S.line('<span class="muted">новый бренд = добавить палитру в BRAND_SKINS_V1.json (0 строк кода)</span>'))
    b.append(S.divider("SURFACE LAW"))
    b.append(S.line('<span class="ok">✓</span> operator surfaces → SOCC matrix canon (one style)'))
    b.append(S.line('<span class="no">⛔</span> customer/product surfaces → ANNA product canon — matrix NEVER reaches a buyer'))
    b.append(S.divider("BUILT (proven by this line)"))
    for t in ["anna_canon_html.py — product renderer twin", "owner cabinet refactored onto the system (210→123 lines)",
              "component library: atoms + molecules", "this living styleguide"]:
        b.append(S.line(f'<span class="ok">✓</span> {t}'))
    b.append(S.divider("LOCKED (gated)"))
    for t in ["landing hero pattern", "motion system", "WCAG a11y report", "full adoption", "SEAL"]:
        b.append(S.line(f'❓ {t}'))
    b.append(f'<p class="foot">regenerate: <span style="color:{P["text"]}">python3 SYSTEM/ATELIER/socc_design_system.py</span> · '
             f'voice: calm, precise, honest. · {GEN}</p>')
    return S.page("SOCC — ATELIER DESIGN SYSTEM", "".join(b),
                  subtitle="единая дизайн-система · две шкуры по закону поверхности · all one source", P=P)


VOICE = {
    "anna": '<b>Голос Анны:</b> тепло, по-человечески, имя пациента, мягкость к боли. Стелс — человек-администратор, никогда «бот».',
    "mark": '<b>Голос Марка:</b> по-свойски, как твой админ, коротко и по делу. Стелс — свой человек, никогда «бот».',
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for name, sk in A.skins().items():   # one engine, every registered skin
        P = A.skin(name)
        voice = VOICE.get(name, '<b>Голос бренда:</b> по-человечески, честно, стелс.')
        html = product_gallery(P, f'{sk.get("label", name)} · дизайн-система',
                               f'живой styleguide · скин «{name}» · тот же движок, своя палитра', voice)
        f = f"DESIGN_SYSTEM_{name.upper()}.html"
        (OUT / f).write_text(html, encoding="utf-8")
        written.append(f)
    (OUT / "DESIGN_SYSTEM_SOCC.html").write_text(socc_gallery(), encoding="utf-8")
    (OUT / "DESIGN_SYSTEM_INDEX.html").write_text(index(), encoding="utf-8")
    print("[atelier] design system rendered ->")
    for f in ["DESIGN_SYSTEM_INDEX.html", "DESIGN_SYSTEM_SOCC.html"] + written:
        print(f"  {OUT.relative_to(SOCC)}/{f}")


if __name__ == "__main__":
    main()

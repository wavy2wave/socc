#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARBITER — живой пульт (vitals monitor органа торговли на Яндекс.Маркете).

Читает РЕАЛЬНЫЕ артефакты на диске (память смен, дневной журнал, tick-ledger со
СЕЛФ, матрицу-рассуждение ОЧКОВ, лог автопилота, состояние фото-кузницы) и
рендерит пульт оператора в ОДИН HTML через канон SOCC (matrix-minimalism),
расширенный слоем «организм как тело»: роли-органы с пульсом, приборные шкалы и
раскрываемый след рассуждения. Перезапусти, чтобы обновить:

    python3 SOCC/scripts/mint/arbiter/arbiter_console_v1.py

RUBICON: ЧИСТОЕ ЧТЕНИЕ. Никогда не исполняет код организма, не ходит в сеть, не
пишет ничего, кроме этого одного HTML. Все записи самого организма остаются за
гейтом (not dry AND commit) — пульт лишь зеркалит то, что УЖЕ легло на диск.
Никогда не падает на отсутствующем/битом файле — деградирует в честное
«источник не подключён», а не в фейковый ноль.
"""
import os
import sys
import html
import json
import math
from pathlib import Path
from datetime import datetime
from collections import Counter

HERE = Path(__file__).resolve().parent          # .../SOCC/scripts/mint/arbiter
SOCC = HERE.parents[2]                           # .../SOCC
REPORTS = SOCC / "MEMORY_WAVE/reports/mint/arbiter"

# artefact paths (env overrides mirror the organism's own env contract)
SHIFT_PATH   = Path(os.environ.get("YM_SHIFT_MEMORY", HERE / "ymarket_shift_memory.json"))
JOURNAL_PATH = Path(os.environ.get("YM_DAY_JOURNAL", REPORTS / "ymarket_day_journal.jsonl"))
MATRIX_PATH  = Path(os.environ.get("YM_MATRIX_PATH", REPORTS / "ymarket_glasses_matrix.json"))
TICKS_PATH   = REPORTS / "ymarket_tick_ledger.jsonl"
APLOG_PATH   = REPORTS / "ymarket_autopilot.log"
LAUNCHD_ERR  = REPORTS / "ymarket_autopilot.launchd.err"
PHOTO_VERD   = HERE / "state/photo_verdicts.json"
PHOTO_LEDGER = HERE / "state/photoforge_ledger.json"
OUT = HERE / "runtime" / "ARBITER_CONTROL_ROOM.html"

# Operator surface law: render through the shared SOCC canon renderer, never a local style.
sys.path.insert(0, str(SOCC / "SYSTEM/INTERFACE/dashboard"))
from socc_canon_html import palette, css, badge  # noqa: E402

TOP_RATING = 80.0        # econ.TOP_RATING_THRESHOLD — зона ТОП
ZONE_CRIT  = 40.0        # контролёр: индекс < 40 → магазин ОТКЛЮЧАЮТ
SLOTS_MSK  = ["08:07", "14:17", "20:47"]   # launchd StartCalendarInterval (local=MSK)

# ── ролевой реестр (статичное зеркало CHARTER-ов; источник: SOCC/scripts/mint/arbiter/
#    ymarket_role_*_v1.py + ymarket_brigade_v1.py — законы механические, меняются редко) ──
ROLES = [
    # id            name_ru          emoji cluster   mandate                                  law
    ("BRIGADE",     "БРИГАДИР",      "👷", "master",  "ведёт смену — порядок ходов",            "ДИСП→СКЛАД→ТОВ→ЦЕН→КОНТР · молчания нет"),
    ("DISPATCHER",  "ДИСПЕТЧЕР",     "🚚", "core",    "заказы в срок, не сгореть по таймеру",   "такт 60 мин · WARN 40 · CRIT 15"),
    ("STOCKMAN",    "СКЛАДОВЩИК",    "📦", "core",    "честный остаток на витрине",             "не уверен → count=0 (лучше ноль, чем ложь)"),
    ("MERCHANDISER","ТОВАРОВЕД",     "🛒", "core",    "отгружаемо ли — физика посылки",         "тариф-обрыв 20кг / 210см → +1500₽"),
    ("PRICER",      "ЦЕНОВИК",       "💰", "core",    "пол цены — не продать в минус",          "floor = закупка+сборы+30₽ · маржа ≥18%"),
    ("CONTROLLER",  "КОНТРОЛЁР",     "🛡", "core",    "индекс качества карточки",               "<40 ОТКЛ · <80 warn · <98 штраф · ≥98 чисто"),
    ("STRATEGIST",  "СТРАТЕГ",       "📈", "propose", "ранг ходов по ₽/усилие",                 "предлагает, не публикует (RUBICON)"),
    ("TRENDSCOUT",  "ТРЕНД-СКАУТ",   "🔭", "propose", "фаза окна спроса",                       "≥3 точки · ≤14 дн · рост > 15%"),
    ("GROWTH",      "СКАУТ РОСТА",   "🌱", "propose", "оси роста ГОРОДА + МОДЕЛИ",              "read-only · ₽ только при источнике"),
    ("HEAD",        "ГОЛОВА",        "🧠", "propose", "суточный шорт-лист «предложено»",        "1 список / дата · ранг делегирован"),
    ("CATEGORIST",  "КАТЕГОРИЙЩИК",  "🗂", "propose", "донор → ранжир. шорт-лист",             "закупка ≤700₽ · наценка ×5–10"),
]
CLUSTER_RU = {"master": "ведёт смену", "core": "ядро · каждую смену", "propose": "предлагают · RUBICON"}


# ───────────────────────────── helpers (never throw) ─────────────────────────────
def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def load_jsonl(path):
    rows = []
    try:
        for ln in Path(path).read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    except Exception:
        pass
    return rows


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def num(v, dash="—", pct=False):
    if v is None:
        return dash
    try:
        f = float(v)
    except Exception:
        return esc(v)
    tail = "%" if pct else ""
    if f == int(f):
        return "%d%s" % (int(f), tail)
    return "%.1f%s" % (f, tail)


def rub(v, dash="—"):
    if v is None:
        return dash
    try:
        return "%d₽" % round(float(v))
    except Exception:
        return dash


def arrow(cur, prev, good_dir=1):
    """Δ-стрелка vs предыдущего дня, окрашенная по смыслу (good_dir=-1 → меньше = лучше)."""
    if cur is None or prev is None:
        return '<span class="mut">—</span>'
    try:
        d = float(cur) - float(prev)
    except Exception:
        return '<span class="mut">—</span>'
    if abs(d) < 1e-9:
        return '<span class="mut">=</span>'
    up = d > 0
    good = (up and good_dir > 0) or ((not up) and good_dir < 0)
    col = "var(--success)" if good else "var(--danger)"
    tri = "▲" if up else "▼"
    dv = "%d" % abs(d) if abs(d) == int(abs(d)) else "%.1f" % abs(d)
    return '<span style="color:%s">%s%s</span>' % (col, tri, dv)


def spark(vals, w=132, h=30, col="var(--primary)"):
    pts = [float(v) for v in vals if v is not None]
    if len(pts) < 2:
        return '<span class="mut">— мало точек</span>'
    lo, hi = min(pts), max(pts)
    rng = (hi - lo) or 1.0
    step = w / (len(pts) - 1)
    coords = []
    for i, v in enumerate(pts):
        x = i * step
        y = h - (v - lo) / rng * (h - 5) - 2.5
        coords.append("%.1f,%.1f" % (x, y))
    lx, ly = coords[-1].split(",")
    return ('<svg class="spark" width="%d" height="%d" viewBox="0 0 %d %d" aria-hidden="true">'
            '<polyline points="%s" fill="none" stroke="%s" stroke-width="1.6" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
            '<circle cx="%s" cy="%s" r="2.3" fill="%s"/></svg>'
            % (w, h, w, h, " ".join(coords), col, lx, ly, col))


def gauge(value, label, scale=100.0, unit="%", target=None, danger_below=None, warn_below=None):
    """Приборная шкала-полукруг. value=None → штриховка «НЕ ПРОЧИТАН» (честнее нуля)."""
    r, cx, cy = 54.0, 64.0, 66.0
    L = math.pi * r
    arc = "M %.0f,%.0f A %.0f,%.0f 0 0 1 %.0f,%.0f" % (cx - r, cy, r, r, cx + r, cy)
    bg = '<path d="%s" fill="none" stroke="var(--line)" stroke-width="9"/>' % arc
    if value is None:
        dashed = ('<path d="%s" fill="none" stroke="var(--muted)" stroke-width="9" '
                  'stroke-dasharray="4 6" opacity=".7"/>' % arc)
        return ('<div class="gauge"><svg width="128" height="80" viewBox="0 0 128 80" aria-hidden="true">'
                '%s%s</svg><div class="gv"><b class="mut">—</b></div>'
                '<div class="glabel">%s</div>'
                '<div class="glabel no">НЕ ПРОЧИТАН · источник не подключён</div></div>'
                % (bg, dashed, esc(label)))
    frac = max(0.0, min(1.0, float(value) / scale))
    dash = frac * L
    if danger_below is not None and value < danger_below:
        col = "var(--danger)"
    elif warn_below is not None and value < warn_below:
        col = "var(--warning)"
    else:
        col = "var(--success)"
    val = ('<path class="gval" d="%s" fill="none" stroke="%s" stroke-width="9" '
           'stroke-linecap="round" stroke-dasharray="%.1f %.1f" style="--d:%.1f"/>'
           % (arc, col, dash, L, dash))
    tick = ""
    if target is not None:
        ang = math.pi * (1.0 - min(1.0, target / scale))
        x1 = cx + (r - 7) * math.cos(ang)
        y1 = cy - (r - 7) * math.sin(ang)
        x2 = cx + (r + 7) * math.cos(ang)
        y2 = cy - (r + 7) * math.sin(ang)
        tick = ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--text)" '
                'stroke-width="1.5" opacity=".8"/>' % (x1, y1, x2, y2))
    tgt = '<div class="glabel">цель %s%s</div>' % (num(target), esc(unit)) if target is not None else ""
    return ('<div class="gauge"><svg width="128" height="80" viewBox="0 0 128 80" aria-hidden="true">'
            '%s%s%s</svg><div class="gv"><b style="color:%s">%s</b><i>%s</i></div>'
            '<div class="glabel">%s</div>%s</div>'
            % (bg, val, tick, col, num(value), esc(unit), esc(label), tgt))


def mtime_str(path):
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"


# ───────────────────────────── data prep ─────────────────────────────
def prep_journal(rows):
    """dedup: один календарный день = одна точка (побеждает поздний ts). Возвращает по-дневный ряд."""
    by_date = {}
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        prev = by_date.get(d)
        if prev is None or str(r.get("ts", "")) >= str(prev.get("ts", "")):
            by_date[d] = r
    days = [by_date[d] for d in sorted(by_date)]
    return days


def window(days, anchor_date, span):
    try:
        a = datetime.strptime(anchor_date, "%Y-%m-%d").date()
    except Exception:
        return days[-span:] if span > 1 else days[-1:]
    out = []
    for r in days:
        try:
            dd = datetime.strptime(r.get("date", ""), "%Y-%m-%d").date()
        except Exception:
            continue
        if 0 <= (a - dd).days < span:
            out.append(r)
    return out


def prep_shifts(env):
    shifts = env.get("shifts", []) if isinstance(env, dict) else []
    role_esc = Counter()
    kind_esc = Counter()
    quality = []
    ok_n = dry_n = commit_n = 0
    for s in shifts:
        if s.get("ok"):
            ok_n += 1
        if s.get("dry"):
            dry_n += 1
        if s.get("commit"):
            commit_n += 1
        q = s.get("quality_rating")
        if q is not None:
            quality.append((s.get("at", ""), q))
        for e in (s.get("escalations") or []):
            role = e.get("role", "?")
            kind = e.get("kind", "?")
            role_esc[role] += 1
            kind_esc["%s:%s" % (role, kind)] += 1
    quality.sort(key=lambda x: x[0])
    return {
        "n": len(shifts), "ok": ok_n, "dry": dry_n, "commit": commit_n,
        "role_esc": role_esc, "kind_esc": kind_esc, "quality": quality,
        "trimmed": env.get("trimmed", 0) if isinstance(env, dict) else 0,
        "rubicon": (len(shifts) > 0 and commit_n == 0 and dry_n == len(shifts)),
    }


def prep_self(tick_rows):
    """СЕЛФ живёт в последней строке tick-ledger: proof.self_status. + агрегат RUBICON-пруфов."""
    self_status, last_tick = None, None
    money = net = 0
    for r in tick_rows:
        proof = r.get("proof") or {}
        if proof.get("moved_money"):
            money += 1
        if proof.get("network_used"):
            net += 1
        ss = proof.get("self_status")
        if ss:
            self_status = ss
        last_tick = r
    recent = tick_rows[-6:]
    return {"self": self_status, "last": last_tick, "recent": recent,
            "moved_money": money, "network_used": net, "n": len(tick_rows)}


def prep_photo(verd, ledger):
    counts = Counter()
    if isinstance(verd, dict):
        for v in verd.values():
            if isinstance(v, dict):
                counts[v.get("verdict", "?")] += 1
    cost = 0.0
    tiers = Counter()
    n = 0
    if isinstance(ledger, list):
        for row in ledger:
            if not isinstance(row, dict):
                continue
            n += 1
            try:
                cost += float(row.get("cost_usd") or 0)
            except Exception:
                pass
            tiers[row.get("tier", "?")] += 1
    return {"verdicts": counts, "cost": cost, "tiers": tiers, "gens": n}


def prep_autopilot(err_size):
    tg = None
    try:
        for ln in reversed(APLOG_PATH.read_text(encoding="utf-8").splitlines()):
            if "ЛЕНТА в Telegram" in ln:
                tg = ln.strip()
                break
    except Exception:
        pass
    return {"tg": tg, "clean": (err_size == 0)}


# ───────────────────────────── section builders ─────────────────────────────
def sec_vitals(latest, shifts, selfd, ap):
    rubicon = shifts["rubicon"] and selfd["moved_money"] == 0 and selfd["network_used"] == 0
    lamp = "ok" if rubicon else "bad"
    lamp_txt = ("ЗАКРЫТ · dry=true · commit=false" if rubicon
                else "ВНИМАНИЕ · обнаружена запись")
    date = esc(latest.get("date", "—"))
    ts = esc(str(latest.get("ts", "—")))[:19].replace("T", " ")
    burning = latest.get("burning", 0) or 0
    top_move = esc(latest.get("top_move", "—"))
    # какой слот отработал последним (по часу ts, MSK=local)
    hh = ts[11:13]
    slots = []
    for s in SLOTS_MSK:
        live = " live" if s[:2] == hh else ""
        slots.append('<span class="hbslot%s">%s</span>' % (live, s))
    burn_col = "var(--danger)" if burning else "var(--success)"
    burn_txt = ("🔥 %d горит" % burning) if burning else "спокойно"
    tg = esc(ap["tg"]) if ap["tg"] else '<span class="mut">нет данных о доставке</span>'
    clean = ('<span class="ok">чисто</span>' if ap["clean"]
             else '<span class="no">есть stderr</span>')
    return ("""<div class="vitals">
  <div class="vcell rubicon">
    <div class="vk">RUBICON — сейф</div>
    <div class="vlamp"><span class="lamp %s"></span><b>%s</b></div>
    <div class="vsub">пульт = ЧТЕНИЕ · организм не двигает деньги без отмашки (YM3/YM6)</div>
  </div>
  <div class="vcell">
    <div class="vk">автопилот · launchd 3×/сут MSK</div>
    <div class="hbwrap"><span class="hb"></span>%s</div>
    <div class="vsub">последний прогон · %s · <span class="mut">%s</span></div>
  </div>
  <div class="vcell">
    <div class="vk">пульс смены</div>
    <div class="vlamp"><b style="color:%s;font-size:18px">%s</b></div>
    <div class="vsub">ход дня → <span style="color:var(--primary)">%s</span></div>
  </div>
  <div class="vcell">
    <div class="vk">лента команды · telegram</div>
    <div class="vsub2">%s</div>
    <div class="vsub">stderr launchd: %s</div>
  </div>
</div>""" % (lamp, lamp_txt, "".join(slots), ts, date, burn_col, burn_txt, top_move, tg, clean))


def sec_gauges(latest):
    k = latest
    rating = k.get("avg_content_rating")
    qidx = k.get("quality_index")
    tracked = k.get("cards_tracked") or 0
    live_v = k.get("cards_live_verified") or 0
    live_pct = (100.0 * live_v / tracked) if tracked else 0.0
    g1 = gauge(rating, "средний contentRating", target=TOP_RATING, danger_below=ZONE_CRIT, warn_below=TOP_RATING)
    g2 = gauge(qidx, "индекс качества")   # None → НЕ ПРОЧИТАН
    g3 = gauge(round(live_pct, 1), "доказано живых", target=100.0, danger_below=50.0, warn_below=100.0)
    cap = ('<div class="glabel" style="text-align:center">%d из %d карточек прошли независимый READ витрины</div>'
           % (live_v, tracked))
    return ('<div class="p-h">приборы · заполненность / качество / доля живых</div>'
            '<div class="gauges">%s%s%s</div>%s' % (g1, g2, g3, cap))


def sec_kpi(latest, prev):
    def tile(label, key, good_dir=1, pct=False):
        cur = latest.get(key)
        pv = prev.get(key) if prev else None
        return ('<div class="kpi"><div class="kpi-val">%s <span class="delta">%s</span></div>'
                '<div class="kpi-title">%s</div></div>'
                % (num(cur, pct=pct), arrow(cur, pv, good_dir), esc(label)))
    tiles = [
        tile("веду карточек", "cards_tracked", 1),
        tile("живых", "cards_live", 1),
        tile("доказано живых", "cards_live_verified", 1),
        tile("с ошибкой (цель 0)", "cards_errored", -1),
        tile("готовы к заливу", "ready_to_publish", 1),
        tile("витрина отключена", "showcase_disabled", -1),
        tile("магазинов", "shops_total", 0),
        tile("горящих заказов", "urgent_orders", -1),
    ]
    return ('<div class="p-h">KPI последнего дня · Δ ко вчера</div>'
            '<div class="grid g4">%s</div>' % "".join(tiles))


def sec_trends(days, anchor):
    rating = [d.get("kpis", {}).get("avg_content_rating") for d in days]
    tracked = [d.get("kpis", {}).get("cards_tracked") for d in days]
    burning = [d.get("burning") for d in days]

    def wline(name, span):
        w = window(days, anchor, span)
        rr = [d.get("kpis", {}).get("avg_content_rating") for d in w if d.get("kpis", {}).get("avg_content_rating") is not None]
        avg = (sum(rr) / len(rr)) if rr else None
        tr = arrow(rr[-1], rr[0]) if len(rr) >= 2 else '<span class="mut">—</span>'
        return ('<div class="r"><span class="k">%s</span><span class="v">дней %d · ср. рейтинг %s · тренд %s</span></div>'
                % (name, len(w), num(avg, pct=True), tr))
    return ('<div class="p-h">тренды по дневному журналу · %d дней</div>'
            '<div class="sparks">'
            '<div class="sp"><span class="spk">contentRating</span>%s</div>'
            '<div class="sp"><span class="spk">веду карточек</span>%s</div>'
            '<div class="sp"><span class="spk">🔥 горит</span>%s</div>'
            '</div>%s%s%s'
            % (len(days),
               spark(rating), spark(tracked, col="var(--text)"), spark(burning, col="var(--danger)"),
               wline("НЕДЕЛЯ", 7), wline("МЕСЯЦ", 30), wline("ВСЁ ОКНО", 3650)))


def sec_organs(role_esc):
    top_role = role_esc.most_common(1)[0][0] if role_esc else None
    cards = []
    for rid, name_ru, emoji, cluster, mandate, law in ROLES:
        cnt = role_esc.get(rid, 0)
        if cnt == 0:
            pc, state = "var(--success)", "спокоен"
        elif rid == top_role:
            pc, state = "var(--danger)", "хронически эскалирует"
        else:
            pc, state = "var(--warning)", "эскалирует"
        cnt_badge = ('<span class="ocnt" style="color:%s">%d ⚑</span>' % (pc, cnt)) if cnt else '<span class="ocnt mut">0</span>'
        cards.append(
            '<div class="organ %s">'
            '<div class="ohead"><span class="pulse" style="--pc:%s"></span>'
            '<span class="oemoji">%s</span><b>%s</b>%s</div>'
            '<div class="omand">%s</div>'
            '<div class="olaw">%s</div>'
            '<div class="ostate" style="color:%s">%s</div>'
            '</div>'
            % (cluster, pc, emoji, esc(name_ru), cnt_badge, esc(mandate), esc(law), pc, state))
    legend = ('<div class="p-h">органы · 11 ролей смены '
              '<span class="mut">(пульс = частота эскалаций в памяти смен · '
              '<span class="ok">●</span> ядро · <span style="color:var(--success)">●</span> ведёт · '
              '<span class="mut">●</span> предлагают)</span></div>')
    return legend + '<div class="organs">%s</div>' % "".join(cards)


def sec_self(selfd):
    ss = selfd["self"]
    if not ss:
        return ('<div class="p-h">СЕЛФ управляющего</div>'
                '<div class="ln mut">источник не подключён — СЕЛФ живёт в proof.self_status последнего тика,'
                ' а tick-ledger пуст/битый.</div>')
    ch = ss.get("charter", {})
    mandate = esc(ch.get("mandate", "—"))
    step = esc(ss.get("next_lawful_step", "—"))
    laws = []
    for lw in ch.get("laws", []):
        laws.append('<div class="lawchip"><b>%s</b> %s<i>%s</i></div>'
                    % (esc(lw.get("code", "?")), esc(lw.get("text", "")), esc(lw.get("enforced_by", ""))))
    isnot = "".join('<span class="tag mut">не %s</span>' % esc(x) for x in ch.get("is_not", []))
    c = ss.get("counters", {}) or {}
    counters = ('тиков %s · заявлено публикаций %s · доказано %s · починено ошибок %s'
                % (num(c.get("ticks")), num(c.get("publishes_claimed")),
                   num(c.get("publishes_verified")), num(c.get("errors_fixed"))))
    return ("""<div class="p-h">СЕЛФ · %s — само-осознание управляющего</div>
<div class="mandate">%s</div>
<div class="cta"><span class="ctak">следующий законный шаг</span><b>%s</b></div>
<div class="p-h" style="margin-top:16px">законы · каждый принуждается кодом</div>
<div class="lawchips">%s</div>
<div class="isnot">%s</div>
<div class="r" style="margin-top:12px"><span class="k">счётчики</span><span class="v mut">%s</span></div>"""
            % (esc(ch.get("id", "ARBITER_YM_MANAGER")), mandate, step, "".join(laws), isnot, counters))


def _fmt_out(out):
    if not isinstance(out, dict):
        return ""
    parts = []
    for k, v in out.items():
        if isinstance(v, bool):
            vv = "да" if v else "нет"
        elif isinstance(v, (int, float)):
            vv = num(v)
        else:
            vv = esc(v)
        cls = ' class="no"' if k == "stop" else ""
        parts.append('<span%s>%s=<b>%s</b></span>' % (cls, esc(k), vv))
    return " · ".join(parts)


def sec_reasoning(m):
    if not isinstance(m, dict) or not m.get("rows"):
        return ('<div class="p-h">ОЧКИ · след рассуждения</div>'
                '<div class="ln mut">матрица не подключена — прогнать '
                '<span style="color:var(--text)">ymarket_glasses_v1.py &lt;slug&gt; --matrix</span>.</div>')
    summ = m.get("summary", {})
    cfg = m.get("config_snapshot", {})
    updated = esc(str(m.get("updated_at", "")))[:10] or mtime_str(MATRIX_PATH)[:10]
    tiles = ('<div class="grid g4">'
             '<div class="kpi"><div class="kpi-val ok">%s</div><div class="kpi-title">🟢 годны</div></div>'
             '<div class="kpi"><div class="kpi-val no">%s</div><div class="kpi-title">🔴 нет</div></div>'
             '<div class="kpi"><div class="kpi-val">%s</div><div class="kpi-title">ср. прибыль 🟢</div></div>'
             '<div class="kpi"><div class="kpi-val">%s</div><div class="kpi-title">на 10 заказов</div></div>'
             '</div>'
             % (num(summ.get("green")), num(summ.get("red")),
                rub(summ.get("avg_green_profit")), rub(summ.get("profit_10_orders"))))
    # knobs strip (defensive — render whatever keys exist)
    knob_labels = [("commission_pct", "комиссия", "×100%"), ("payment_pct", "эквайринг", "×100%"),
                   ("delivery_rub", "доставка", "₽"), ("overhead_rub", "буфер", "₽"),
                   ("overhead_pct", "буфер%", "×100%"), ("max_sell_mult", "потолок цены", "×"),
                   ("min_margin_pct", "мин. маржа", "%"), ("round_to", "шаг цены", "₽")]
    knobs = []
    for key, lab, unit in knob_labels:
        if key in cfg and cfg[key] is not None:
            val = cfg[key]
            if unit == "×100%":
                disp = "%g%%" % (float(val) * 100)
            elif unit == "×":
                disp = "×%g" % float(val)
            elif unit == "%":
                disp = "%g%%" % float(val)
            else:
                disp = "%g%s" % (float(val), unit)
            knobs.append('<span class="knob"><i>%s</i> %s</span>' % (esc(lab), esc(disp)))
    tiers = cfg.get("tiers")
    if isinstance(tiers, list):
        tparts = []
        for t in tiers:
            if isinstance(t, list) and len(t) == 2:
                up = "∞" if t[0] is None else num(t[0])
                tparts.append("≤%s→+%s₽" % (up, num(t[1])))
        if tparts:
            knobs.append('<span class="knob"><i>тиры profit</i> %s</span>' % esc(" · ".join(tparts)))
    knobstrip = '<div class="knobs">%s</div>' % "".join(knobs) if knobs else ""
    # green pipeline
    pipe = m.get("green_pipeline") or []
    if pipe:
        nodes = []
        for i, node in enumerate(pipe):
            if i:
                nodes.append('<span class="parrow">→</span>')
            nodes.append('<span class="pnode"><b>%s</b><i>%s</i></span>'
                         % (esc(node.get("organ", "")), esc(node.get("does", ""))))
        pipeline = '<div class="p-h" style="margin-top:14px">🟢 куда течёт годная карточка</div><div class="pipe">%s</div>' % "".join(nodes)
    else:
        pipeline = ""
    # rows → expandable chain steppers
    rows = list(m.get("rows", []))

    def _pk(r):
        p = r.get("profit")
        p = p if isinstance(p, (int, float)) else -1e9
        return (0 if r.get("green") else 1, -p)
    rows.sort(key=_pk)
    LIMIT = 18
    shown = rows[:LIMIT]
    items = []
    for r in shown:
        gd = bool(r.get("green"))
        dotc = "var(--success)" if gd else "var(--danger)"
        vd = "🟢" if gd else "🔴"
        head = ('%s <span class="rsku">%s</span> · %s→%s <span class="mut">×%s</span> · '
                '<b style="color:%s">+%s</b> · %s%% <span class="rname">%s</span>'
                % (vd, esc(r.get("sku", "?")), rub(r.get("cost")), rub(r.get("sell")),
                   num(r.get("mult")), dotc, rub(r.get("profit")), num(r.get("margin_pct")),
                   esc(r.get("name", ""))))
        steps = []
        for st in (r.get("chain") or []):
            steps.append(
                '<div class="step"><div class="step-h"><span class="stepn">%s</span>'
                '<span class="org">%s</span> %s</div>'
                '<div class="formula">%s</div><div class="out">%s</div></div>'
                % (esc(st.get("n", "")), esc(st.get("organ", "")), esc(st.get("name", "")),
                   esc(st.get("formula", "")), _fmt_out(st.get("out"))))
        why = '<div class="rwhy">%s</div>' % esc(r.get("why", "")) if r.get("why") else ""
        items.append('<details class="chain"><summary>%s</summary>%s<div class="steps">%s</div></details>'
                     % (head, why, "".join(steps)))
    more = ('<div class="ln mut" style="margin-top:8px">показаны %d из %d строк · '
            'полный реестр цепей в ymarket_glasses_matrix.json</div>' % (len(shown), len(rows))) if len(rows) > LIMIT else ""
    note = ('<div class="ln mut">снимок %s · донор %s · <span class="warnc">знобы могли измениться в коде — '
            'смотри как СТРУКТУРУ рассуждения, числа перепроверяй свежим прогоном</span></div>'
            % (esc(updated), esc(m.get("donor", "—"))))
    return ('<div class="p-h">ОЧКИ · след рассуждения · закупка→цена→сборы→прибыль→вердикт '
            '<span class="mut">(клик по строке — раскрыть 6 шагов)</span></div>'
            + tiles + knobstrip + note + pipeline
            + '<div class="p-h" style="margin-top:14px">карточки-вердикты</div>'
            + "".join(items) + more)


def sec_signals(shifts, selfd):
    kind_esc = shifts["kind_esc"]
    top = kind_esc.most_common(8)
    mx = top[0][1] if top else 1
    rows = []
    for kind, cnt in top:
        w = int(60.0 * cnt / mx)
        rows.append('<div class="sig"><span class="sigk">%s</span>'
                    '<span class="bar" style="width:%dpx"></span><span class="sign">%d</span></div>'
                    % (esc(kind), max(6, w), cnt))
    freq = ('<div class="p-h">нервная система · частота эскалаций (память %d смен)</div>%s'
            % (shifts["n"], "".join(rows) or '<div class="ln mut">эскалаций нет</div>'))
    # recent ticks
    tks = []
    for r in selfd["recent"]:
        proof = r.get("proof") or {}
        st = proof.get("status", "?")
        note = (r.get("result") or {}).get("note", "")
        money = proof.get("moved_money", False)
        net = proof.get("network_used", False)
        chip = ('<span class="tchip"><span class="ok">0₽</span></span>' if not money
                else '<span class="tchip no">₽!</span>')
        nchip = ('<span class="tchip mut">net·off</span>' if not net
                 else '<span class="tchip no">net!</span>')
        tks.append('<div class="tick"><span class="tact">%s</span> %s %s %s'
                   '<div class="tnote mut">%s</div></div>'
                   % (esc(r.get("action", "?")), badge(st), chip, nchip, esc(note)))
    ticks = ('<div class="p-h" style="margin-top:16px">последние тики · пруф RUBICON '
             '<span class="mut">(денег двигали: %d · сеть: %d за %d тиков)</span></div>%s'
             % (selfd["moved_money"], selfd["network_used"], selfd["n"],
                "".join(tks) or '<div class="ln mut">тиков нет</div>'))
    return freq + ticks


def sec_photo(ph):
    v = ph["verdicts"]
    good, unknown, bad = v.get("good", 0), v.get("unknown", 0), v.get("bad", 0)
    tot = good + unknown + bad
    donut = ('<div class="donut">'
             '<span class="dseg ok">🟢 годно %d</span>'
             '<span class="dseg warnc">◐ спорно %d</span>'
             '<span class="dseg no">🔴 брак %d</span></div>' % (good, unknown, bad))
    tiers = " · ".join("%s %d" % (esc(k), c) for k, c in ph["tiers"].most_common())
    return ('<div class="p-h">фото-кузница · тройной гейт (железо/буквы/зрение)</div>'
            '%s<div class="r"><span class="k">вердиктов всего</span><span class="v">%d</span></div>'
            '<div class="r"><span class="k">генераций (ledger)</span><span class="v">%d · $%.2f</span></div>'
            '<div class="r"><span class="k">тиры</span><span class="v mut">%s</span></div>'
            % (donut, tot, ph["gens"], ph["cost"], tiers or "—"))


def sec_footer(sources):
    rows = []
    for label, path, present in sources:
        mark = '<span class="ok">✓</span>' if present else '<span class="no">⚠</span>'
        rows.append('%s %s <span class="mut">· %s · %s</span>'
                    % (mark, esc(label), mtime_str(path), esc(str(path).replace(str(SOCC), "…"))))
    return ('<div class="p-h">источники · всё прочитано, ничего не записано</div>'
            + "".join('<div class="ln">%s</div>' % r for r in rows)
            + '<p class="foot">пульт оператора · рендер через SOCC_DESIGN_CANON_V1 (matrix) из реальных артефактов · '
              'обновить: <span style="color:var(--text)">python3 SOCC/scripts/mint/arbiter/arbiter_console_v1.py</span><br>'
              'голос: спокойно, точно, честно — не выдумываем ₽ и живые карточки; НЕ ПРОЧИТАН честнее нуля. '
              'клиент этот экран не видит — matrix только для оператора.</p>')


def _sect(fn, *a):
    try:
        return '<div class="panel">%s</div>' % fn(*a)
    except Exception as e:
        return ('<div class="panel"><div class="p-h no">секция недоступна</div>'
                '<div class="ln no">⚠ %s: %s</div></div>' % (esc(type(e).__name__), esc(str(e))))


# ───────────────────────────── extended canon css (additive) ─────────────────────────────
def extra_css():
    return """<style>
 .wrap{max-width:1080px}
 .box .t2{color:var(--muted);font-weight:400}
 .mut{color:var(--muted)} .no{color:var(--danger)} .ok{color:var(--success)}
 .warnc{color:var(--warning)}
 /* vital-signs strip */
 .vitals{display:grid;grid-template-columns:repeat(auto-fit,minmax(228px,1fr));gap:12px;margin:14px 0 6px}
 .vcell{background:var(--s2);border:1px solid var(--line);border-radius:var(--radius);padding:13px 15px;
   box-shadow:0 1px 0 var(--hair) inset}
 .vcell.rubicon{border-color:color-mix(in srgb,var(--success) 34%,var(--line))}
 .vk{color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-size:10.5px;margin-bottom:9px}
 .vlamp{display:flex;align-items:center;gap:9px;font-size:12.5px;font-weight:700}
 .vsub{color:var(--muted);font-size:11px;margin-top:8px;line-height:1.5}
 .vsub2{font-size:11.5px;line-height:1.5}
 .lamp{width:12px;height:12px;border-radius:50%;flex:0 0 auto;position:relative}
 .lamp.ok{background:var(--success);box-shadow:0 0 0 3px color-mix(in srgb,var(--success) 22%,transparent),0 0 14px var(--success)}
 .lamp.bad{background:var(--danger);box-shadow:0 0 0 3px color-mix(in srgb,var(--danger) 22%,transparent),0 0 14px var(--danger)}
 .hbwrap{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
 .hb{width:9px;height:9px;border-radius:50%;background:var(--success);flex:0 0 auto;
   box-shadow:0 0 0 0 color-mix(in srgb,var(--success) 60%,transparent)}
 .hbslot{font-size:11px;color:var(--muted);background:var(--s3);border:1px solid var(--line);
   border-radius:5px;padding:1px 7px;letter-spacing:.03em}
 .hbslot.live{color:var(--bg);background:var(--primary);border-color:var(--primary);font-weight:700}
 /* gauges */
 .gauges{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;justify-items:center;margin:6px 0 4px}
 .gauge{position:relative;width:150px;text-align:center}
 .gv{position:absolute;top:34px;left:0;right:0;display:flex;flex-direction:column;align-items:center;line-height:1}
 .gv b{font-size:26px;font-weight:700;letter-spacing:-.02em}
 .gv i{font-style:normal;color:var(--muted);font-size:10px;margin-top:2px}
 .glabel{color:var(--muted);font-size:10.5px;margin-top:2px;letter-spacing:.03em}
 .gval{stroke-dashoffset:0}
 /* kpi grid variants */
 .g4{grid-template-columns:repeat(4,1fr)} .g3{grid-template-columns:repeat(3,1fr)} .g2{grid-template-columns:repeat(2,1fr)}
 .kpi-val{display:flex;align-items:baseline;gap:8px} .delta{font-size:12px;font-weight:400}
 /* trend sparks */
 .sparks{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:4px 0 14px}
 .sp{background:var(--s1);border:1px solid var(--line);border-radius:var(--radius-sm);padding:9px 12px}
 .spk{display:block;color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}
 .spark{display:block}
 /* organ mesh */
 .organs{display:grid;grid-template-columns:repeat(auto-fill,minmax(196px,1fr));gap:11px}
 .organ{background:var(--s2);border:1px solid var(--line);border-left:3px solid var(--muted);
   border-radius:var(--radius-sm);padding:11px 13px}
 .organ.core{border-left-color:var(--primary)} .organ.master{border-left-color:var(--success)}
 .organ.propose{border-left-color:var(--muted);opacity:.92}
 .ohead{display:flex;align-items:center;gap:7px;font-size:13px}
 .ohead b{letter-spacing:.02em} .oemoji{font-size:14px}
 .ocnt{margin-left:auto;font-size:11px;font-weight:700}
 .omand{color:var(--text);font-size:11px;margin:7px 0 3px;line-height:1.45}
 .olaw{color:var(--muted);font-size:10.5px;line-height:1.4}
 .ostate{font-size:10px;margin-top:6px;text-transform:uppercase;letter-spacing:.05em}
 .pulse{width:9px;height:9px;border-radius:50%;background:var(--pc);flex:0 0 auto;
   box-shadow:0 0 0 0 color-mix(in srgb,var(--pc) 55%,transparent)}
 /* self */
 .mandate{font-size:14px;line-height:1.55;color:var(--text);margin:4px 0 14px;
   border-left:2px solid var(--line-lum);padding-left:13px}
 .cta{background:linear-gradient(180deg,color-mix(in srgb,var(--primary) 9%,var(--s2)),var(--s2));
   border:1px solid var(--line-lum);border-radius:var(--radius-sm);padding:12px 15px}
 .ctak{display:block;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-size:10px;margin-bottom:5px}
 .cta b{font-size:13.5px;line-height:1.5;color:var(--primary)}
 .lawchips{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:9px}
 .lawchip{background:var(--s1);border:1px solid var(--line);border-radius:var(--radius-sm);padding:9px 12px;font-size:11.5px;line-height:1.45}
 .lawchip b{color:var(--primary);margin-right:6px} .lawchip i{display:block;color:var(--muted);font-style:normal;font-size:10px;margin-top:5px}
 .isnot{margin-top:11px;display:flex;flex-wrap:wrap;gap:6px}
 .tag{font-size:10.5px;background:var(--s3);border:1px solid var(--line);border-radius:5px;padding:1px 8px}
 /* reasoning chain */
 .knobs{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}
 .knob{font-size:11px;background:var(--s1);border:1px solid var(--line);border-radius:5px;padding:2px 9px}
 .knob i{font-style:normal;color:var(--muted);margin-right:4px}
 .pipe{display:flex;align-items:stretch;gap:8px;flex-wrap:wrap;margin-top:8px}
 .pnode{background:var(--s1);border:1px solid var(--line-lum);border-radius:var(--radius-sm);padding:9px 12px;flex:1;min-width:180px}
 .pnode b{display:block;font-size:11.5px} .pnode i{font-style:normal;color:var(--muted);font-size:10.5px;display:block;margin-top:4px;line-height:1.4}
 .parrow{align-self:center;color:var(--primary);font-weight:700}
 details.chain{background:var(--s1);border:1px solid var(--line);border-radius:var(--radius-sm);margin:7px 0;overflow:hidden}
 details.chain>summary{cursor:pointer;padding:10px 13px;list-style:none;font-size:12px;line-height:1.5}
 details.chain>summary::-webkit-details-marker{display:none}
 details.chain>summary:hover{background:var(--s2)}
 details.chain[open]>summary{border-bottom:1px solid var(--line);background:var(--s2)}
 .rsku{color:var(--muted)} .rname{color:var(--muted);margin-left:4px}
 .rwhy{padding:9px 13px 0;color:var(--text);font-size:11.5px}
 .steps{padding:11px 13px 13px;display:grid;gap:8px}
 .step{border-left:2px solid var(--line-lum);padding:2px 0 2px 12px;position:relative}
 .step-h{font-size:11.5px}
 .stepn{display:inline-block;min-width:16px;color:var(--bg);background:var(--primary);border-radius:4px;
   text-align:center;font-weight:700;font-size:10px;margin-right:6px;padding:0 2px}
 .org{color:var(--primary)} .formula{font-size:11px;color:var(--muted);margin:3px 0}
 .out{font-size:11.5px} .out b{color:var(--text)} .out span{margin-right:2px}
 /* signals */
 .sig{display:flex;align-items:center;gap:10px;padding:3px 0;font-size:11.5px}
 .sigk{min-width:250px;color:var(--text)} .sign{color:var(--muted);min-width:34px;text-align:right}
 .bar{height:9px;border-radius:3px;background:linear-gradient(90deg,var(--warning),var(--danger));flex:0 0 auto}
 .tick{background:var(--s1);border:1px solid var(--line);border-radius:var(--radius-sm);padding:8px 12px;margin:6px 0;font-size:11.5px}
 .tact{color:var(--primary);font-weight:700;margin-right:6px}
 .tchip{font-size:10px;border:1px solid var(--line);border-radius:5px;padding:0 6px;margin-left:5px}
 .tnote{margin-top:4px}
 .donut{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
 .dseg{font-size:12px;background:var(--s1);border:1px solid var(--line);border-radius:6px;padding:4px 11px;font-weight:700}
 @media (prefers-reduced-motion:no-preference){
  .gval{animation:draw .9s cubic-bezier(.2,.6,.2,1) forwards}
  @keyframes draw{from{stroke-dashoffset:var(--d)}to{stroke-dashoffset:0}}
  .lamp.ok,.hb{animation:beat 2.1s ease-in-out infinite}
  .pulse{animation:beat 2.4s ease-in-out infinite}
  @keyframes beat{0%,100%{box-shadow:0 0 0 0 color-mix(in srgb,var(--pc,var(--success)) 55%,transparent)}
   50%{box-shadow:0 0 0 6px transparent}}
  .panel{animation:rise .5s cubic-bezier(.2,.6,.2,1) both}
 }
 @keyframes rise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
 .panel:nth-child(2){animation-delay:.04s}.panel:nth-child(3){animation-delay:.08s}
 .panel:nth-child(4){animation-delay:.12s}.panel:nth-child(5){animation-delay:.16s}
 .panel:nth-child(6){animation-delay:.2s}.panel:nth-child(7){animation-delay:.24s}
</style>"""


def main():
    P = palette()
    env = load_json(SHIFT_PATH, {})
    jrows = load_jsonl(JOURNAL_PATH)
    ticks = load_jsonl(TICKS_PATH)
    matrix = load_json(MATRIX_PATH, {})
    verd = load_json(PHOTO_VERD, {})
    ledger = load_json(PHOTO_LEDGER, [])
    try:
        err_size = LAUNCHD_ERR.stat().st_size
    except Exception:
        err_size = -1

    days = prep_journal(jrows)
    latest = days[-1] if days else {"kpis": {}, "burning": 0, "top_move": "—", "date": "—"}
    prev = days[-2] if len(days) >= 2 else {}
    latest_k = latest.get("kpis", {}) if isinstance(latest.get("kpis"), dict) else {}
    prev_k = prev.get("kpis", {}) if isinstance(prev.get("kpis"), dict) else {}
    shifts = prep_shifts(env)
    selfd = prep_self(ticks)
    ph = prep_photo(verd, ledger)
    ap = prep_autopilot(err_size)
    anchor = latest.get("date", "")

    sources = [
        ("дневной журнал (KPI)", JOURNAL_PATH, bool(days)),
        ("память смен", SHIFT_PATH, shifts["n"] > 0),
        ("tick-ledger (СЕЛФ)", TICKS_PATH, selfd["self"] is not None),
        ("матрица ОЧКОВ", MATRIX_PATH, bool(matrix.get("rows"))),
        ("лог автопилота", APLOG_PATH, ap["tg"] is not None),
        ("фото-вердикты", PHOTO_VERD, sum(ph["verdicts"].values()) > 0),
    ]

    body = "".join([
        _sect(sec_vitals, latest, shifts, selfd, ap),
        _sect(sec_gauges, latest_k),
        _sect(sec_kpi, latest_k, prev_k),
        _sect(sec_trends, days, anchor),
        _sect(sec_self, selfd),
        _sect(sec_reasoning, matrix),
        _sect(sec_organs, shifts["role_esc"]),
        _sect(sec_signals, shifts, selfd),
        _sect(sec_photo, ph),
        _sect(sec_footer, sources),
    ])

    header = ("""<div class="box">╔═══════════════════════════════════════════════════════╗
║  ARBITER ▸ ПУЛЬТ ОРГАНИЗМА   <span class="t2">— как думает торговый организм ЯМ</span>  ║
╚═══════════════════════════════════════════════════════╝</div>
<p class="sub">operator surface · живой рендер из реальных артефактов · %s · RUBICON: чистое чтение (0₽)</p>"""
              % esc(mtime_str(JOURNAL_PATH)))

    doc = ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width, initial-scale=1">'
           '<title>ARBITER ▸ ПУЛЬТ ОРГАНИЗМА</title>%s%s</head><body><div class="wrap">%s%s</div></body></html>'
           % (css(P), extra_css(), header, body))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")

    print("ARBITER control room -> %s" % OUT.relative_to(SOCC))
    print("  journal days: %d · shifts: %d (RUBICON %s) · ticks: %d · matrix rows: %d"
          % (len(days), shifts["n"], "OK" if shifts["rubicon"] else "?",
             selfd["n"], len(matrix.get("rows", []))))
    print("  self: %s · escalations: %d kinds · photo verdicts: %d"
          % ("loaded" if selfd["self"] else "MISSING",
             len(shifts["kind_esc"]), sum(ph["verdicts"].values())))


if __name__ == "__main__":
    main()

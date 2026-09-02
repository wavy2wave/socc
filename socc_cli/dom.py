#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ — ИНТЕРАКТИВ (socc_cli/dom.py).

Живой дом вместо «кирпича»: меню-навигация по органам/магазинам/заданиям.
Оператор («всё сырое — серьёзнее; процессы не стоят камнем, а идут и я вижу»):

    socc home  (tty)  → меню 5 органов; выбор ЯМ → меню магазинов
    socc ym    (tty)  → «магазинов: N» → выбрать витрину → её АКТИВНЫЕ задания
                         + пульс цикла СЕГОДНЯ (леджер растёт — живой след)
    socc ym <витрина> → сразу экран магазина (tty — меню, иначе текст)
    [R] ЖИВОЙ ЭКРАН   → автообновление каждые 2с: пульс/леджер/таймер автопилота

Высшая наука CLI: стрелки ↑↓ / j k + Enter — выбрать; цифра — сразу; q — назад.
Read 0₽ (DH6): НИЧЕГО не пишет, сеть не зовёт, шелла нет. RUBICON цел.
В пайпе / StringIO / `--text` — прежний один-экран текст (CC8/HH2, не ломаем).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

from socc_cli import style as S
from socc_cli import home as H

# ── пути (read-only источники, как консоль) ───────────────────────────────────
ARB = H.SOCC_ROOT / "scripts" / "mint" / "arbiter"
RUNTIME = ARB / "runtime" / "cycle1"
STORES_JSON = RUNTIME / "stores.json"
DAY_JOURNAL = H.REPORTS / "ymarket_day_journal.jsonl"
MATRIX_JSON = H.REPORTS / "ymarket_product_matrix.json"
TASKS_JSON = H.REPORTS / "ymarket_tasks.json"
AUTOPILOT_LOG = H.REPORTS / "ymarket_autopilot.log"
PLISTS = [
    Path.home() / "Library/LaunchAgents/com.socc.arbiter.daycycle.v1.plist",
    Path.home() / "Library/LaunchAgents/com.socc.arbiter.autopilot.v1.plist",
]
_SCHED_FALLBACK = ["08:07", "14:17", "20:47"]  # автопилот 3×/сут MSK (launchd)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
R, B, DIM = "\033[0m", "\033[1m", "\033[2m"
GR, CY, YE, RE = "\033[32m", "\033[36m", "\033[33m", "\033[31m"

# ── мелкие помощники (переиспользуем канон дома) ──────────────────────────────
_tty, _col, _width, _band, _seal = H._tty, H._col, H._width, H._band, H._seal
_now_msk, _j, _snip, _ansi_strip = H._now_msk, H._j, H._snip, H._ansi_strip


def _st(t):
    return _ANSI.sub("", str(t))


def _state_word(state):
    return {"live": "ЖИВО", "idle": "ДЕРЖИТ", "off": "ТИХО"}.get(state, state.upper())


def _state_dot(out, state):
    col = {"live": "GR", "idle": "CY", "off": "DIM"}.get(state, "DIM")
    return _col(out, col, "●")


# ── автопилот: расписание + отсчёт (живой таймер) ─────────────────────────────
def _schedule():
    """Времена автопилота (HH:MM MSK) из launchd plist, иначе запасные."""
    for p in PLISTS:
        if not p.exists():
            continue
        try:
            import plistlib
            with p.open("rb") as f:
                d = plistlib.load(f)
            cal = d.get("StartCalendarInterval") or []
            if not isinstance(cal, list):
                cal = [cal]
            times = sorted({f"{int(c['Hour']):02d}:{int(c.get('Minute', 0)):02d}"
                            for c in cal if isinstance(c, dict) and "Hour" in c})
            if times:
                return times
        except Exception:
            continue
    return _SCHED_FALLBACK


def _next_run(now=None, times=None):
    """Ближайший тик автопилота → (datetime MSK, секунд_до)."""
    now = now or _now_msk()
    times = times or _schedule()
    base = now.replace(second=0, microsecond=0)
    for hm in times:
        try:
            h, m = (int(x) for x in hm.split(":"))
        except Exception:
            continue
        cand = base.replace(hour=h, minute=m)
        if cand > now:
            return cand, int((cand - now).total_seconds())
    for hm in sorted(times):
        try:
            h, m = (int(x) for x in hm.split(":"))
        except Exception:
            continue
        cand = (now + _dt.timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
        return cand, int((cand - now).total_seconds())


def _until_txt(sec):
    if sec is None:
        return "—"
    sec = int(sec)
    if sec < 60:
        return f"{sec}с"
    h, m = divmod(sec // 60, 60)
    if h:
        return f"{h}ч {m:02d}м"
    return f"{m}м"


# ── сторы магазинов / пульс / леджер ──────────────────────────────────────────
def _stores_map():
    d = _j(STORES_JSON)
    return d if isinstance(d, dict) else {}


def _store_info(store):
    return (_stores_map().get(store) or {}) if store else {}


def _pulse(store):
    return _j(RUNTIME / store / "last_pulse.json") if store else None


def _ledger_rows(store, date=None):
    """Строки леджера магазина за день (живой след цикла). read.

    ts в файле — только время («12:22:50»); дописываем дату файла, чтобы
    «когда это было»/возраст считались честно.
    """
    date = date or _now_msk().strftime("%Y-%m-%d")
    p = RUNTIME / store / f"{date}.jsonl"
    rows = []
    try:
        for ln in p.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            r = json.loads(ln)
            if isinstance(r.get("ts"), str) and re.match(r"^\d{2}:\d{2}:\d{2}$", r["ts"]):
                r["ts"] = f"{date}T{r['ts']}"
            rows.append(r)
    except Exception:
        pass
    return rows


def _collapsed_runs(ledger):
    """Леджер → прогоны (каждый стартует на узле ДОНОР)."""
    runs, cur = [], None
    for r in ledger or []:
        node = r.get("node")
        if not node:
            continue
        if cur is None or node == "ДОНОР":
            cur = {"ts": r.get("ts", ""), "nodes": []}
            runs.append(cur)
        cur["nodes"].append((node, r.get("verdict"), str(r.get("note", ""))))
    return runs


def _vmark(v):
    v = str(v or "?").upper()
    return {"PASS": ("GR", "✓"), "FAIL": ("RE", "✗"), "DRY": ("CY", "◌")}.get(v, ("DIM", "·"))


def _age_txt(ts, now=None):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})", str(ts or ""))
    if not m:
        return "—"
    try:
        parts = [int(x) for x in m.groups()]
        d = _dt.datetime(*parts)
        now = now or _now_msk()
        if now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        sec = max(0, int((now - d).total_seconds()))
        return _until_txt(sec) + " назад"
    except Exception:
        return "—"


# ── очередь магазина (наблюдения → задания; реестра durable может не быть) ─────
def _project_queue(store, info, ledger, pulse, today=None, matrix=None):
    """Честная ОЧЕРЕДЬ витрины из живых сторов (0₽). Реестр не трогает.

    Леджер СВЕРКА-PASS сегодня = карточки УЖЕ на витрине → «залить» не зовём
    (матрица может отставать в offer_id — не ложимся на её устарелость).
    matrix=None → читается с диска; фикстура инъекции для герметичных тестов.
    """
    today = today or _now_msk().strftime("%Y-%m-%d")
    q = []

    def _published_now(ledger):
        for r in ledger or []:
            if r.get("node") == "СВЕРКА" and r.get("verdict") == "PASS":
                ev = r.get("evidence")
                if isinstance(ev, dict):
                    for a in ev.values():
                        if isinstance(a, dict) and isinstance(a.get("placement"), dict) \
                                and a["placement"].get("status") == "PUBLISHED":
                            return True
        return False

    # 1. готовые карточки (собран) не долетели до витрины (offer/ean пуст)
    mat = _j(MATRIX_JSON) if matrix is None else matrix
    rows = mat.get("rows", mat) if isinstance(mat, dict) else mat
    items = list(rows.values()) if isinstance(rows, dict) else (rows if isinstance(rows, list) else [])
    cats = {c for c in (info.get("donor_category"), info.get("builder_slug"),
                        info.get("builder"), info.get("category")) if c}
    ready = [r for r in items if isinstance(r, dict) and r.get("status") == "собран"
             and not r.get("offer_id") and (not cats or (r.get("category") or "") in cats)]
    if ready and not _published_now(ledger):
        q.append(dict(
            tag="ЗАЛИВ", urgency="high", owner="MERCHANDISER",
            what=f"Залить {len(ready)} готовых карточек на витрину (собран → offer/ean)",
            evidence=f"матрица: {len(ready)} строк собран, offer/ean пуст · категория "
                     f"{info.get('donor_category') or '—'}; леджер ещё не подтвердил PUBLISHED"))
    elif ready and _published_now(ledger):
        q.append(dict(
            tag="СВЕРКА", urgency="low", owner="CONTROLLER",
            what="Матрица отстала от витрины: карточки PUBLISHED, offer_id в матрице пуст",
            evidence="леджер СВЕРКА-PASS (PUBLISHED), матрица всё ещё «собран/offer пуст»"))
    # 2. последний ход леджера FAIL → чинить узел (без фейк-пасс, якорь на последнем)
    if ledger:
        last = ledger[-1]
        if last.get("verdict") == "FAIL":
            q.append(dict(
                tag="ЧИНИТЬ", urgency="high", owner="CONTROLLER",
                what=f"Узел «{last.get('node')}» упал последним ходом",
                evidence=f"леджер {today}: {str(last.get('ts', ''))[:19]} FAIL · "
                         f"{_snip(last.get('note'), 88)}"))
    # 3. пульс нет / устарел
    if not pulse:
        q.append(dict(
            tag="ПУЛЬС", urgency="normal", owner="DISPATCHER",
            what="Собрать первый пульс магазина (сухой прогон ЦИКЛА-1, 0₽)",
            evidence=f"манифест {store}: last_pulse.json ещё нет"))
    elif str(pulse.get("date")) != today:
        q.append(dict(
            tag="ПУЛЬС", urgency="normal", owner="DISPATCHER",
            what=f"Пульс устарел ({pulse.get('date')}) — прогнать сухо сегодня",
            evidence=f"пульс {pulse.get('date')} ≠ сегодня {today}"))
    return q


def _registry_active(store=None):
    """Durable-реестр заданий: (status, active_tasks). status ∈ absent/ok/error."""
    if not TASKS_JSON.exists():
        return "absent", []
    d = _j(TASKS_JSON)
    ts = (d or {}).get("tasks")
    if ts is None:
        return "error", []
    tasks = list(ts.values()) if isinstance(ts, dict) else (ts if isinstance(ts, list) else [])
    out = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        if t.get("state") in ("done", "archived"):
            continue
        steps = t.get("steps") or []
        if not steps or all(s.get("state") == "done" for s in steps if isinstance(s, dict)):
            continue
        if store and t.get("store") not in ("", store):
            continue
        out.append(t)
    return "ok", out


# ── данные экрана магазина (с инъекцией для герметичных тестов) ───────────────
def store_payload(store, *, info=None, pulse=None, ledger=None, queue=None, registry=None):
    info = info if info is not None else _store_info(store)
    pulse = pulse if pulse is not None else _pulse(store)
    ledger = ledger if ledger is not None else _ledger_rows(store)
    queue = queue if queue is not None else _project_queue(store, info, ledger, pulse)
    registry = registry if registry is not None else _registry_active(store)
    return {"store": store, "info": info, "pulse": pulse, "ledger": ledger,
            "queue": queue, "registry": registry}


def _clock(out=None):
    return _now_msk().strftime("%H:%M MSK")


# ── рендер текста экрана магазина (out-aware) ─────────────────────────────────
def store_text(out, store, pl=None, now=None):
    """Блок витрины: идентичность · пульс · цикл сегодня · активные задания."""
    out = out or sys.stdout
    pl = pl if pl is not None else store_payload(store)
    now = now or _now_msk()
    L = []
    info = pl["info"]
    pulse = pl["pulse"]
    ledger = pl["ledger"]
    today = now.strftime("%Y-%m-%d")

    bid = info.get("business_id") or "?"
    cmp = info.get("campaign_id") or "?"
    wh = info.get("warehouse_id") or "?"
    L.append(_col(out, "DIM", f"  биз {bid} · кампания {cmp} · склад {wh}"))
    bits = []
    if info.get("donor_category"):
        bits.append(f"донор {info['donor_category']}")
    if info.get("builder"):
        bits.append(f"builder {info['builder']}")
    if info.get("markup") is not None:
        bits.append(f"маржа ×{info['markup']}")
    if info.get("stock_count") is not None:
        bits.append(f"остаток {info['stock_count']}")
    if bits:
        L.append(_col(out, "DIM", "  " + " · ".join(bits)))
    if info.get("note"):
        L.append(_col(out, "DIM", f"  {_snip(info['note'], 90)}"))

    # ПУЛЬС
    L.append(_seal(out, "ПУЛЬС"))
    if not pulse:
        L.append(f"  {_col(out, 'YE', '○ пульса нет')} — первый сухой прогон соберёт")
    else:
        pdate = str(pulse.get("date", "?"))
        vd = pulse.get("run_verdicts") or {}
        age = _age_txt(_last_ts(ledger) or pulse.get("date"), now)
        vbits = " · ".join(f"{k} {v}" for k, v in vd.items()) or "—"
        col = "GR" if pdate == today else "YE"
        L.append(f"  {_col(out, col, '●')} пульс {pdate} · вердикты {vbits}"
                 f" · артефактов {pulse.get('artifacts', 0)}"
                 + (f" · активность {age}" if age != "—" else ""))
        if pdate != today:
            L.append(_col(out, "DIM", "     устарел — цикл сегодня ещё не гонялся сухо"))

    # ЦИКЛ СЕГОДНЯ (леджер — живой след)
    L.append(_seal(out, "ЦИКЛ СЕГОДНЯ"))
    runs = _collapsed_runs(ledger)
    if not runs:
        L.append(_col(out, "DIM", "  хода нет — витрина ждёт первого сухого прогона"))
    else:
        nrow = len(ledger)
        last = ledger[-1].get("ts", "")
        age = _age_txt(last, now)
        L.append(_col(out, "DIM",
                      f"  прогонов {len(runs)} · строк {nrow} · последний ход "
                      f"{str(last)[11:19]} · {age}"))
        for run in runs[-5:]:
            marks = []
            for node, v, _note in run["nodes"]:
                if node == "ДОНОР":
                    continue
                tcol, ch = _vmark(v)
                marks.append(node + _col(out, tcol, ch))
            marks = marks or ["—"]
            ts = run.get("ts", "")
            line = f"  {str(ts)[11:16]}  " + "  ".join(marks)
            L.append(_st(line)[: _width(out)] if not _tty(out) else line)

    # АКТИВНЫЕ ЗАДАНИЯ
    L.append(_seal(out, "АКТИВНЫЕ ЗАДАНИЯ"))
    reg_status, reg_tasks = pl["registry"]
    if reg_status == "ok" and reg_tasks:
        for t in sorted(reg_tasks, key=lambda x: (x.get("priority", 50),
                                                  str(x.get("updated_at", "")))):
            st = t.get("state", "open")
            col = "CY" if st == "in_progress" else "W"
            ndone = sum(1 for s in (t.get("steps") or []) if isinstance(s, dict) and s.get("state") == "done")
            ntot = len(t.get("steps") or [])
            icon = "◐" if st == "in_progress" else "○"
            L.append(f"  {_col(out, col, icon)} {_col(out, 'B', t.get('what', ''))} "
                     f"[{t.get('owner')}] · пункты {ndone}/{ntot} · {t.get('id')}")
    elif reg_status == "error":
        L.append(_col(out, "RE", "  реестр заданий битый — читаю очередь из живых сторов"))
    # очередь (наблюдения) — если durable пуст/нет
    queue = pl["queue"]
    if not queue:
        if not (reg_status == "ok" and reg_tasks):
            L.append(_col(out, "GR", "  ◉ витрина чиста: открытых заданий и наблюдений нет"))
    else:
        for qq in queue:
            urg = "!!" if qq.get("urgency") == "high" else ("!" if qq.get("urgency") == "critical" else "")
            tag = _col(out, {"ЗАЛИВ": "CY", "ЧИНИТЬ": "RE", "ПУЛЬС": "YE"}.get(qq.get("tag"), "W"), qq.get("tag", "?"))
            L.append(f"  ○ {tag} {urg} {_col(out, 'B', qq.get('what', ''))} [{qq.get('owner')}]")
            L.append(_col(out, "DIM", f"      · {_snip(qq.get('evidence'), _width(out) - 12)}"))
    if reg_status == "absent" and queue:
        L.append(_col(out, "DIM", "     (реестр durable ещё не создан — это живая очередь наблюдений)"))
    return "\n".join(L)


def _last_ts(ledger):
    for r in reversed(ledger or []):
        if r.get("ts"):
            return r["ts"]
    return None


# ── экранные строки меню (pure: строки; цвет накладывает рендер) ───────────────
def _item(action, label, sub=None, col=None):
    return {"kind": "item", "action": action, "label": label, "sub": sub, "col": col}


def _sep(text):
    return {"kind": "sep", "text": text}


def _text(line):
    return {"kind": "text", "line": line}


def home_rows(probes):
    """Строки меню ДОМА. probes: {key: (state, note)} — свежие зонды."""
    rows = [_sep("ОРГАНЫ")]
    order = [("kernel", "🧭 SOCC · КЕРНЕЛЬ"), ("ym", "🛍️ ЯМ-ЦИКЛ"), ("ozon", "🚚 OZON"),
             ("substrate", "🧬 ENTITY SUBSTRATE"), ("anna", "🩺 ANNA")]
    for key, label in order:
        state, note = probes.get(key, ("off", "зонд недоступен"))
        rows.append(_item(f"go:{key}", f"{label}  · {_state_word(state)}",
                          sub=_snip(note, 84)))
    rows.append(_sep("ЖИВОЕ"))
    rows.append(_item("live:home", "▶ ЖИВОЙ ЭКРАН — вся система дышит",
                      sub="автообновление: пульс органов · таймер автопилота · часы"))
    rows.append(_sep(""))
    rows.append(_item("quit", "Выйти из ДОМА"))
    return rows


def _home_probes():
    orgs = H._ORGANS
    out = {}
    for o in orgs:
        try:
            state, note, _hint = o["probe"]()
        except Exception:
            state, note = "off", "зонд упал"
        out[o["key"]] = (state, note)
    return out


def ym_rows(stores, *, pulse_of=None, now=None):
    """Строки меню ЯМ: витрины (пульс) + действия цикла."""
    rows = []
    stores = stores or {}
    now = now or _now_msk()
    today = now.strftime("%Y-%m-%d")
    if not stores:
        rows.append(_text(_col_not("манифест пуст — магазинов ещё нет (0₽)")))
        rows.append(_text(""))
    else:
        rows.append(_sep(f"МАГАЗИНЫ · в манифесте {len(stores)}"))
        for slug in sorted(stores):
            pulse = (pulse_of or _pulse)(slug) or {}
            pdate = str(pulse.get("date", ""))
            fresh = pdate == today
            vd = pulse.get("run_verdicts") or {}
            vtxt = " · ".join(f"{k} {v}" for k, v in vd.items()) or "хода нет"
            if fresh:
                brief = f"пульс {pdate} · {vtxt} · арт {pulse.get('artifacts', 0)}"
                col = "GR"
            elif pdate:
                brief = f"пульс {pdate} (устарел) · {vtxt}"
                col = "YE"
            else:
                brief = "пульса нет — сухой прогон соберёт"
                col = "DIM"
            sub = f"  · {brief}"
            rows.append(_item(f"store:{slug}", slug, sub=sub, col=col))
    rows.append(_sep("ЦИКЛ-ЯМ · экраны (read)"))
    for act, label in (("view:все", "ВСЁ · штаб+магазины+дело+задания"),
                       ("view:штаб", "ШТАБ · 13 ролей"),
                       ("view:дело", "ДЕЛО · журнал+KPI+задания"),
                       ("view:задания", "ЗАДАНИЯ · весь реестр"),
                       ("view:планёрка", "ПЛАНЁРКА · пульсы+задания"),
                       ("view:авто", "АВТОПИЛОТ · хвост прогонов")):
        rows.append(_item(act, label))
    rows.append(_sep("ЖИВОЕ / ГЛУБЖЕ"))
    rows.append(_item("live:ym", "▶ ЖИВОЙ ЭКРАН ЯМ", sub="витрины · леджеры · таймер автопилота"))
    rows.append(_item("view:мозг", "МОЗГ · чат-навигатор ЯМ"))
    rows.append(_item("quit", "Назад в ДОМ"))
    return rows


def _col_not(t):
    """plain fallback для _text строк (цвет добавит рендер tty)."""
    return t


def _store_action_rows():
    return [_item("live:store", "▶ ЖИВОЙ ЭКРАН магазина",
                  sub="леджер цикла растёт на глазах · таймер автопилота"),
            _item("view:авто", "АВТОПИЛОТ · хвост прогонов"),
            _item("view:задания", "ЗАДАНИЯ · весь реестр"),
            _item("quit", "Назад к магазинам")]


# ── рендер меню + выбор ────────────────────────────────────────────────────────
def _menu_items(rows):
    return [r for r in rows if r.get("kind") == "item"]


def menu_text(out, title, sub, rows, prompt, sel=None):
    """Полный кадр меню (строки; item-строки нумеруются, sel → инверсия)."""
    L = [_band(out, title, right=_clock(), sub=sub), ""]
    items = _menu_items(rows)
    idx = 0
    for r in rows:
        k = r.get("kind")
        if k == "sep":
            L.append(_seal(out, r.get("text", "")))
        elif k == "text":
            L.append("  " + str(r.get("line", "")))
        elif k == "item":
            idx += 1
            num = f"{idx}."
            sel_on = sel is not None and idx - 1 == sel
            label = str(r.get("label", ""))
            col = r.get("col")
            if col and _tty(out):
                label = _col(out, col, label)
            line = f"  {num} {label}" if not sel_on else f"  {_col(out, 'GR', num)} {label}"
            if sel_on:
                line = f"\033[7m {line} \033[0m" if _tty(out) else f"> {line.strip()}"
            L.append(line)
            if r.get("sub"):
                L.append(_col(out, "DIM", "     " + str(r["sub"])) if _tty(out) else "     " + str(r["sub"]))
    L.append("")
    L.append(_col(out, "DIM", "  " + prompt) if _tty(out) else "  " + prompt)
    return "\n".join(L)


def _line_choice(out, inp, items):
    """Не-tty (тесты/пайп): читаем строку из inp; номер/точное вхождение/q."""
    while True:
        raw = inp.readline()
        if raw == "":
            return None
        s = raw.strip().lower()
        if not s:
            continue
        if s in ("q", "0", "exit", "выход", "назад", ".."):
            return None
        if s.isdigit():
            n = int(s)
            if 1 <= n <= len(items):
                return items[n - 1]
            out.write(f"  нет пункта {n} — выбери 1..{len(items)}\n")
            continue
        hits = [it for it in items if s in str(it.get("label", "")).lower()]
        if len(hits) == 1:
            return hits[0]
        out.write(f"  «{s}» не однозначно — выбери цифрой\n")
        continue


def pick(out, inp, *, title, sub, rows, prompt=None):
    """Выбор строки меню. tty+raw: стрелки/jk/цифра/Enter/q. Иначе — строка из inp."""
    out = out or sys.stdout
    inp = inp or sys.stdin
    prompt = prompt or "↑↓ / j k — выбрать · Enter — открыть · цифра — сразу · q — назад"
    if _tty(out) and _tty(inp):
        return _pick_tty(out, inp, title, sub, rows, prompt)
    items = _menu_items(rows)
    out.write(menu_text(out, title, sub, rows, prompt) + "\n")
    return _line_choice(out, inp, items)


def _pick_tty(out, inp, title, sub, rows, prompt):
    """Живой выбор стрелками (raw-режим; терминал восстанавливается в finally)."""
    import select
    import termios
    import tty as _ttymod

    items = _menu_items(rows)
    sel = 0
    fd = inp.fileno()
    old = None
    try:
        old = termios.tcgetattr(fd)
        _ttymod.setraw(fd)
        out.write("\x1b[?25l")
        out.write("\x1b[2J\x1b[H")
        while True:
            out.write(menu_text(out, title, sub, rows, prompt, sel=sel))
            out.flush()
            key = _read_key(inp, fd)
            if key == "up":
                sel = (sel - 1) % len(items) if items else 0
            elif key == "down":
                sel = (sel + 1) % len(items) if items else 0
            elif key == "enter":
                return items[sel] if items else None
            elif key in ("q", "esc"):
                return None
            elif key == "j":
                sel = (sel + 1) % len(items) if items else 0
            elif key == "k":
                sel = (sel - 1) % len(items) if items else 0
            elif key.isdigit():
                n = int(key)
                if 1 <= n <= len(items):
                    return items[n - 1]
            out.write("\x1b[2J\x1b[H")
    finally:
        try:
            out.write("\x1b[?25h")
            if old is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass


def _read_key(inp, fd):
    """Один клавишный ввод: Enter, стрелки (ESC [ A/B), буквы/цифры, ESC=q."""
    import select
    try:
        b0 = os.read(fd, 1)
    except Exception:
        return "q"
    if b0 == b"\x1b":
        seq = b""
        for _ in range(2):
            r, _, _ = select.select([inp], [], [], 0.03)
            if not r:
                break
            try:
                seq += os.read(fd, 1)
            except Exception:
                break
        if seq == b"[A" or seq in (b"OA", b"[1;2A"):
            return "up"
        if seq == b"[B" or seq in (b"OB", b"[1;2B"):
            return "down"
        if seq == b"[C" or seq == b"[D":
            return "right" if seq == b"[C" else "left"
        return "esc"
    if b0 in (b"\r", b"\n"):
        return "enter"
    try:
        ch = b0.decode("utf-8", "replace")
    except Exception:
        return "q"
    if ch in "123456789":
        return ch
    if ch in "jkJK":
        return ch.lower()
    if ch in ("q", "Q"):
        return "q"
    return "enter"  # любая другая — как Enter (быстрое «дальше»)


def _show_pause(out, inp, title, content, footer="— нажми любую клавишу —"):
    """Полный экран с контентом; Enter/любая/пробел — вернуться."""
    if _tty(out) and _tty(inp):
        try:
            import termios
            import tty as _ttymod
            fd = inp.fileno()
            old = termios.tcgetattr(fd)
            _ttymod.setraw(fd)
            try:
                out.write("\x1b[2J\x1b[H")
                out.write(_band(out, title, right=_clock()) + "\n")
                out.write(content + "\n\n")
                out.write(_col(out, "DIM", "  " + footer) if _tty(out) else footer)
                out.flush()
                while True:
                    key = _read_key(inp, fd)
                    if key in ("q", "esc"):
                        return "quit"
                    return "back"
            finally:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
                except Exception:
                    pass
        except Exception:
            return "back"
    else:
        out.write(_band(out, title, right=_clock()) + "\n")
        out.write(content + "\n")
        return "back"


# ── ЖИВОЙ ЭКРАН (автообновление) ──────────────────────────────────────────────
def live_frame(out, scope, store=None, now=None):
    """Кадр живого экрана. scope ∈ home|ym|store:<slug>. Чистый, 0₽."""
    out = out or sys.stdout
    now = now or _now_msk()
    nxt, secs = _next_run(now)
    L = []
    if scope == "home":
        L.append(_band(out, "SOCC · ДОМ · ЖИВОЙ", right=_clock(),
                       sub="автообновление · read 0₽"))
        L.append("")
        for o in H._ORGANS:
            try:
                state, note, _hint = o["probe"]()
            except Exception:
                state, note = "off", "зонд упал"
            word = _state_word(state)
            L.append(f"  {o['icon']} {o['title']:<26} {_state_dot(out, state)} {word:<7} · {_snip(note, 64)}")
    elif scope == "ym":
        L.append(_band(out, "ЯМ-ЦИКЛ · ЖИВОЙ", right=_clock(),
                       sub="витрины · пульсы · леджеры · read 0₽"))
        L.append("")
        stores = _stores_map()
        if not stores:
            L.append("  манифест пуст")
        for slug in sorted(stores):
            pulse = _pulse(slug) or {}
            pdate = str(pulse.get("date", ""))
            vd = pulse.get("run_verdicts") or {}
            vtxt = " ".join(f"{k}{v}" for k, v in vd.items()) or "—"
            ledger = _ledger_rows(slug)
            age = _age_txt(_last_ts(ledger) or "", now)
            col = "GR" if pdate == now.strftime("%Y-%m-%d") else "YE"
            L.append(f"  {_col(out, col, '●')} {slug:<24} пульс {pdate} · {vtxt}"
                     f" · прогонов {len(_collapsed_runs(ledger))} · {age}")
    elif scope and scope.startswith("store:"):
        store = store or scope[6:]
        pl = store_payload(store)
        L.append(_band(out, f"ЯМ · {store} · ЖИВОЙ", right=_clock(),
                       sub="леджер цикла растёт на глазах · read 0₽"))
        L.append("")
        L.append(store_text(out, store, pl, now=now))
        L.append("")
        L.append(_seal(out, "ХВОСТ ЛЕДЖЕРА (свежие ходы)"))
        tail = pl["ledger"][-6:]
        if tail:
            for r in tail:
                tcol, ch = _vmark(r.get("verdict"))
                L.append(f"  {_col(out, 'DIM', str(r.get('ts', ''))[11:19])}"
                         f"  {_col(out, tcol, ch)} {r.get('node', '?')}"
                         f"  {_col(out, 'DIM', _snip(r.get('note'), _width(out) - 30))}")
        else:
            L.append(_col(out, "DIM", "  хода ещё нет"))
    # низ: таймер автопилота + подсказка
    L.append("")
    L.append(_seal(out, "АВТОПИЛОТ"))
    nxt_txt = nxt.strftime("%H:%M") if nxt else "—"
    L.append(f"  следующий тик {nxt_txt} MSK · через {_until_txt(secs)}"
             + (_col(out, "RE", "  · ИДЁТ (в окне)" if secs and secs < 240 else "")))
    L.append(_col(out, "DIM", "  q / любая клавиша — назад в меню"))
    return "\n".join(L)


def _live(out, inp, scope, store=None, interval=2.0):
    """Цикл живости: кадр → пауза interval → клавиша выходит."""
    import select
    import termios
    import tty as _ttymod
    fd = inp.fileno()
    old = None
    try:
        old = termios.tcgetattr(fd)
        _ttymod.setraw(fd)
        out.write("\x1b[?25l")
        while True:
            out.write("\x1b[2J\x1b[H")
            out.write(live_frame(out, scope, store=store))
            out.flush()
            r, _, _ = select.select([inp], [], [], interval)
            if r:
                try:
                    os.read(fd, 64)
                except Exception:
                    pass
                return
    finally:
        try:
            out.write("\x1b[?25h")
            if old is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass


# ── экраны-экраны (сводки цикла через консоль-канон) ──────────────────────────
def _ym_subview(out, subv):
    """Один read-экран ЯМ через канон консоли (как socc ym <под>)."""
    try:
        return H._ym_face(out, subv, [])
    except Exception as e:
        return _col(out, "RE", f"экран «{subv}» не поднялся: {e}")


def _organ_face(out, org):
    fn = {"kernel": H._kernel_face, "ozon": H._ozon_face,
          "substrate": H._substrate_face, "anna": H._anna_face}.get(org)
    if fn is None:
        return ""
    try:
        return fn(out, [])
    except Exception as e:
        return _col(out, "RE", f"{org}: {e}")


def _run_brain(out, inp):
    """МОЗГ сдаёт контроль своему REPL (read); возврат — назад в меню."""
    # мозг живёт в арбитре; запускаем В ПРОЦЕССЕ (read-REPL, как socc ym мозг)
    out.write("\x1b[2J\x1b[H")
    out.flush()
    try:
        sys.path.insert(0, str(ARB))
        import ymarket_brain_v1 as brain  # noqa: WPS433
        fn = getattr(brain, "_main", None) or getattr(brain, "main", None)
        if fn:
            fn([])
    except Exception as e:
        out.write(f"мозг не поднялся: {e}\n")


# ── верхнеуровневые циклы экранов ─────────────────────────────────────────────
def run_store(out, inp, store):
    while True:
        pl = store_payload(store)
        content = store_text(out, store, pl)
        rows = [_text(l) for l in content.split("\n")]
        rows.append(_sep("ДЕЙСТВИЯ"))
        rows.extend(_store_action_rows())
        ch = pick(out, inp, title=f"ЯМ · {store}", sub="витрина Экспресс · read 0₽",
                  rows=rows, prompt="цифра / Enter — действие · q — к магазинам")
        if ch is None:
            return -1
        act = ch["action"]
        if act == "quit":
            return -1
        if act == "live:store":
            _live(out, inp, "store:" + store)
        elif act.startswith("view:"):
            code = _show_pause(out, inp, f"ЯМ · {store}", _ym_subview(out, act[5:]))
            if code == "quit":
                return -1


def run_ym(out, inp):
    stores = _stores_map()
    while True:
        rows = ym_rows(stores)
        ch = pick(out, inp, title="ЯМ-ЦИКЛ", sub=f"магазинов в манифесте: {len(stores)}",
                  rows=rows, prompt="выбери витрину / экран · q — назад в ДОМ")
        if ch is None:
            return -1
        act = ch["action"]
        if act == "quit":
            return -1
        if act.startswith("store:"):
            code = run_store(out, inp, act[6:])
            if code == 0:
                return 0
            stores = _stores_map()  # свежесть после возврата
            continue
        if act == "live:ym":
            _live(out, inp, "ym")
            continue
        if act.startswith("view:"):
            subv = act[5:]
            if subv == "мозг":
                _run_brain(out, inp)
                continue
            code = _show_pause(out, inp, "ЯМ-ЦИКЛ", _ym_subview(out, subv))
            if code == "quit":
                return -1


def run_home(out, inp):
    while True:
        rows = home_rows(_home_probes())
        ch = pick(out, inp, title="SOCC · ДОМ", sub="живой хаб · 0₽ read",
                  rows=rows, prompt="цифра / Enter — орган · q — выйти")
        if ch is None:
            return 0
        act = ch["action"]
        if act == "quit":
            return 0
        if act == "live:home":
            _live(out, inp, "home")
            continue
        if act.startswith("go:"):
            org = act[3:]
            if org == "ym":
                code = run_ym(out, inp)
                if code == 0:
                    return 0
                continue
            code = _show_pause(out, inp, f"SOCC · {org.upper()}", _organ_face(out, org))
            if code == "quit":
                return 0
            continue


def store_screen_text(out, store):
    """Один-экран витрины (не-tty / пайп / --text)."""
    return store_text(out, store, store_payload(store))


if __name__ == "__main__":
    sys.exit(run_home(sys.stdout, sys.stdin))

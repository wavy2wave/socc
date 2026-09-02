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
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from socc_cli import style as S
from socc_cli import home as H
from socc_cli import view as V

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
# Зеркала движка ЦИКЛ-1 (ymarket_cycle1_v1): хеш прогона и цепь узлов.
# Нужны, чтобы ДОМ честно называл тот же хеш/тот же «конец прогона», что движок.
_CHAIN_VERSION = "film-1.0"            # L34 движка
_REQUIRED_STORE_FIELDS = [             # L40 движка (8 полей манифеста)
    "slug", "business_id", "campaign_id", "warehouse_id",
    "donor_category", "builder", "markup", "stock_count",
]
_TERMINAL_NODE = "ПЛАНЁРКА"            # узел N7 — прогон дошёл до конца

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
R, B, DIM = "\033[0m", "\033[1m", "\033[2m"
GR, CY, YE, RE = "\033[32m", "\033[36m", "\033[33m", "\033[31m"

# ── мелкие помощники (переиспользуем канон дома) ──────────────────────────────
_tty, _col, _width, _band, _seal = H._tty, H._col, H._width, H._band, H._seal
_now_msk, _j, _snip, _ansi_strip = H._now_msk, H._j, H._snip, H._ansi_strip

# ── viewport-движок: стабильный кадр вместо «плывущих» ─────────────────────────
# Геометрия ПОСТОЯННА на всех режимах (NAV/READ/LIVE): шапка 4 + воздух 1 = 5,
# низ ровно 3 строки → тело всегда rows-8. Низ пишется последним → подсказка,
# счётчик и действия физически не могут уехать за кадр. Ни одного `\n` внутри
# кадра (raw LF≠CR «плывёт»), автоперенос выключен на весь кадр, каждый ряд —
# абсолютный CUP. Модуль view.py (socc_cli/view.py) владеет ANSI-набором.
_HEAD = 5      # шапка 4 строки + 1 воздух
_FOOT = 3      # низ ровно 3 строки (инфо · подробность/таймер · подсказка)
_MARK_LIVE = " · ЖИВОЙ"


def _geom():
    """(rows, cols, ширина контента) живого экрана — никогда не падает."""
    rows, cols = V.geom()
    return rows, cols, max(10, cols - 2)


def _viable_tty(out, inp):
    """Фиксированный кадр — только живой tty с достаточной геометрией."""
    if not (_tty(out) and _tty(inp)):
        return False
    rows, cols = V.geom()
    return V._viable(cols, rows)


def _head4(out, title, sub, right=None):
    """Шапка-лента РОВНО 4 строки (константа геометрии кадра)."""
    right = right or _clock()
    lines = _band(out, title, right=right, sub=sub).split("\n")
    w = _width(out)
    while len(lines) < 4:
        pad = "║" + " " * max(2, w - 2) + "║"
        lines = lines[:1] + [pad] + lines[1:]
    return lines[:4]


def _frame(out, title, sub, body, foot):
    """Кадр ровно ROWS клеток: шапка 4 · воздух · тело (rows-8) · низ 3 (прижат).

    body — окно уже нужной высоты; низ дописывается последним, поэтому действия
    и подсказка никогда не уезжают. paint() сам добьёт до rows.
    """
    rows, _c, _w = _geom()
    cells = _head4(out, title, sub)
    cells.append("")
    body_h = rows - _HEAD - _FOOT
    cells += (list(body) + [""] * body_h)[:body_h]
    cells += (list(foot) + [""] * _FOOT)[:_FOOT]
    return cells[:rows]


def _nav_cells(out, title, sub, rows, sel, prompt):
    """Клетки меню-кадра: нумерованные пункты (ГЛОБАЛЬНО 1..M) + низ 3 строки.

    Номера действительны и за границей окна: стрелками листаем, цифрой попадаем
    сразу. Подробность выбранного пункта — ВТОРАЯ строка низа (не плывёт, не
    теряется); в тело sub-строки не вставляем → меньше прокрутки.
    """
    items = _menu_items(rows)
    n = len(items)
    wid = len(str(max(n, 1)))
    body, item_pos, idx = [], [], 0
    for r in rows:
        k = r.get("kind")
        if k == "sep":
            body.append(_seal(out, r.get("text", "")))
        elif k == "text":
            body.append("  " + str(r.get("line", "")))
        elif k == "item":
            item_pos.append(len(body))
            label = str(r.get("label", ""))
            col = r.get("col")
            if col:
                label = _col(out, col, label)
            body.append(f"  {idx + 1:>{wid}}  {label}")
            idx += 1
    rows_, _c, _w = _geom()
    body_h = rows_ - _HEAD - _FOOT
    L = len(body)
    top = 0
    if L > body_h:
        t = item_pos[sel] if 0 <= sel < len(item_pos) else 0
        top = min(max(0, t - body_h // 2), max(0, L - body_h))
    win = (list(body[top:top + body_h]) + [""] * body_h)[:body_h]
    if 0 <= sel < len(item_pos):
        li = item_pos[sel] - top
        if 0 <= li < len(win):
            win[li] = "\x1b[7m " + win[li].strip() + " \x1b[0m"
    detail = items[sel].get("sub") if 0 <= sel < n else ""
    foot = [
        (f"пункт {sel + 1} из {n}" if n else "пунктов нет")
        + (" · листай ↑↓ / j k" if L > body_h else ""),
        str(detail) if detail else "",
        prompt,
    ]
    return _frame(out, title, sub, win, [_col(out, "DIM", t) for t in foot])


def _read(out, inp, *, title, sub, body, buttons=None, summary=None, hint=None):
    """READ-экран стабильного кадра: длинное тело листается, низ 3 прижат.

    Возвращает токен кнопки (цифра) либо None (q/esc; Enter-на-коротком-экране).
    Клавиши: ↑↓ / j k / Enter — листать · цифра — действие · q / esc — назад.
    """
    buttons = buttons or []
    body = list(body) if isinstance(body, list) else str(body).split("\n")
    fd, old = V.enter(out, inp)
    rows_, _c, _w = _geom()
    body_h = rows_ - _HEAD - _FOOT
    act_lines = []
    if buttons:
        act_lines = ["", _seal(out, "ДЕЙСТВИЯ")]
        acts = "   " + "   ".join(f"[{i}] {lab}" for i, (_t, lab) in enumerate(buttons, 1))
        act_lines.append(acts)
    avail = body_h - len(act_lines)
    maxoff = max(0, len(body) - avail)
    off = 0
    hint = hint or "↑↓ / j k — листать · q — назад"
    try:
        while True:
            p = min(off, maxoff)
            win = (list(body[p:p + avail]) + [""] * avail)[:avail]
            win = win + act_lines
            if maxoff:
                page = f"стр {p + 1}–{p + avail} из {len(body)}"
                top = f"{summary or ''} · {page}" if summary else page
            else:
                top = summary or ""
            scr = "↑↓ — листать" if maxoff else ""
            act_hint = " · цифра — действие" if buttons else ""
            foot = [top, (scr + act_hint) or "read 0₽", hint]
            V.paint(out, _frame(out, title, sub, win, [_col(out, "DIM", t) for t in foot]))
            key = _read_key(inp, fd)
            if key in ("up", "k"):
                off = max(0, off - 1)
            elif key in ("down", "j", "enter"):
                if maxoff:
                    off = min(maxoff, off + 1)
                elif not buttons:
                    return None
            elif key.isdigit():
                d = int(key)
                if 1 <= d <= len(buttons):
                    return buttons[d - 1][0]
            elif key in ("q", "esc"):
                return None
    finally:
        V.leave(out, fd, old)


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


# ── данные ПУЛЬТА: день · деньги · тик-факт · правило хода (read 0₽) ────────────
# Канон отчётов ARBITER — ТОЛЬКО repo-root MEMORY_WAVE/reports/mint/arbiter (как
# console/day/tasks_reg). Вложенная сирота scripts/MEMORY_WAVE НЕ читается и НЕ
# выводится: она не затеняет канон (тот же закон, что в ymarket_tasks_v1 L87).
def _tail_jsonl(path, kb=64):
    """Хвост JSONL/лога (последние ~kb КБ) → объекты по порядку. read.
    Лог автопилота большой — полный файл не тянем, хвоста хватает для факта тика.
    Строка может начинаться текстом («…JSON {…}») — ищем первый «{» и парсим с него.
    """
    try:
        size = path.stat().st_size
    except Exception:
        return []
    if size <= 0:
        return []
    start = max(0, size - kb * 1024)
    rows = []
    try:
        with path.open("rb") as f:
            if start:
                f.seek(start)
                f.readline()  # отбросить рваную первую строку хвоста
            data = f.read().decode("utf-8", "replace")
    except Exception:
        return []
    for ln in data.splitlines():
        s = ln.strip()
        if not s:
            continue
        try:
            r = json.loads(s)
        except Exception:
            i = s.find("{")
            if i < 0:
                continue
            try:
                r = json.loads(s[i:])
            except Exception:
                continue
        if isinstance(r, dict):
            rows.append(r)
    return rows


def _day_stats(ledger):
    """Честный агрегат дня витрины ПО СТРОКАМ леджера (не run_verdicts пульса):
    вердикты PASS/DRY/FAIL · закрыто/в работе · последний ход · FAIL-хвост."""
    ledger = list(ledger or [])
    verdicts = {}
    for r in ledger:
        v = str(r.get("verdict", "")).upper()
        if v:
            verdicts[v] = verdicts.get(v, 0) + 1
    closed, open_ = _open_runs(ledger)
    last = ledger[-1] if ledger else None
    fails = [r for r in ledger if str(r.get("verdict", "")).upper() == "FAIL"]
    return dict(rows=len(ledger), verdicts=verdicts, closed=len(closed),
                open=len(open_), last=last, last_fail=(fails[-1] if fails else None))


def _store_money(store, pl=None):
    """Деньги витрины ЧЕСТНО: закуп (карта затрат) · витрина = закуп×маржа ·
    PUBLISHED-артикулов (СВЕРКА) · 0₽ выручки, пока нет живой строки с деньгами.
    Сумм продаж в сторах НЕТ → подпись «ПОТЕНЦИАЛ ×N», не «заработано N₽»."""
    pl = pl if pl is not None else store_payload(store)
    costs = _card_costs_map()
    buy = sum(v for v in costs.values() if isinstance(v, (int, float)))
    markup = pl["info"].get("markup")
    pub = _published_evidence(pl["ledger"])
    sell = round(buy * float(markup)) if buy and markup else 0
    return dict(buy=round(buy), sell=sell, pub=len(pub),
                markup=(float(markup) if markup else 0),
                live_rows=sum(1 for r in pl["ledger"] if r.get("dry") is False))


def _fleet_money(stores):
    """Итог по манифесту: закуп · потенциал витрины ×маржа · PUBLISHED арт."""
    buy = sell = pub = 0
    for slug in sorted(stores or {}):
        m = _store_money(slug)
        buy += m["buy"]
        sell += m["sell"]
        pub += m["pub"]
    return dict(buy=buy, sell=sell, pub=pub)


def _last_tick_fact():
    """Факт последнего тика автопилота (канонный autopilot.log): последняя
    JSON-строка → {ts, ok, dry, commit, burning} · None — тика ещё не было."""
    for r in reversed(_tail_jsonl(AUTOPILOT_LOG)):
        if r.get("ts") or r.get("date"):
            return dict(ts=r.get("ts") or r.get("date"),
                        ok=bool(r.get("ok")), dry=r.get("dry", True),
                        commit=bool(r.get("commit")), burning=r.get("burning"))
    return None


def _next_step(store, pl=None, now=None):
    """Правило хода витрины (КОМАНДИР ДНЯ): ЧТО сейчас делать — честно из сторов.
    R1 FAIL-хвост → чинить узел · R2 нет пульса → первый сухой · R3 пульс устарел →
    сухой сегодня · R4 durable-задача открыта → её владелец · R5 очередь (ЗАЛИВ/
    СВЕРКА/…) не покрыта → действие · R6 PUBLISHED и всё чисто → день чист ·
    R7 иначе → ждать тик по расписанию. Возвращает (heat, title, line):
    heat 2=чинить · 1=внимание · 0=спокойно."""
    now = now or _now_msk()
    pl = pl if pl is not None else store_payload(store)
    today = now.strftime("%Y-%m-%d")
    info, pulse, ledger = pl["info"], pl["pulse"], pl["ledger"]
    reg_status, reg_tasks = pl["registry"]
    queue = pl["queue"]
    last = ledger[-1] if ledger else None

    if last and str(last.get("verdict", "")).upper() == "FAIL":
        node = last.get("node", "?")
        return (2, "ЧИНИТЬ",
                f"узел «{node}» упал последним ходом {str(last.get('ts', ''))[11:19]} "
                f"· {_snip(_clean_note(last.get('note')), 44)}")
    if not pulse:
        return (1, "ПУЛЬС", "первый пульс магазина — сухой прогон ЦИКЛ-1 (0₽)")
    if str(pulse.get("date", "")) != today:
        return (1, "ПУЛЬС",
                f"пульс {pulse.get('date')} устарел — прогнать сухо сегодня (0₽)")
    if reg_status == "ok" and reg_tasks:
        t = sorted(reg_tasks, key=lambda x: (x.get("priority", 50),
                                             str(x.get("updated_at", ""))))[0]
        heat = 1 if t.get("urgency") != "high" else 2
        return (heat, "ЗАДАЧА",
                f"{_snip(t.get('what', ''), 52)} [{t.get('owner')}] · {t.get('id')}")
    if queue:
        qq = queue[0]
        return (1 if qq.get("urgency") != "high" else 2, qq.get("tag", "ШАГ"),
                f"{_snip(qq.get('what', ''), 58)} [{qq.get('owner')}]")
    if _published_evidence(ledger):
        return (0, "ДЕНЬ ЧИСТ", "витрина PUBLISHED · открытых заданий нет — цикл идёт сам")
    return (0, "ЖДАТЬ", f"нет действий — след. тик по расписанию · {_ticks_brief()}")


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


# ── ДОМ кампании <хеш>: read-сводка по живым сторам (0₽) ──────────────────────
def _cycle_hash(store, date=None):
    """Тот же хеш прогона, что движок: sha1(магазин×дата×версия цепи)[:10]."""
    date = date or _now_msk().strftime("%Y-%m-%d")
    return hashlib.sha1(f"{store}|{date}|{_CHAIN_VERSION}".encode()).hexdigest()[:10]


def _open_runs(ledger):
    """(закрытые, в_работе): прогоны леджера; в работе — не дошли до ПЛАНЁРКА."""
    runs = _collapsed_runs(ledger)
    closed, open_ = [], []
    for r in runs:
        if r["nodes"] and r["nodes"][-1][0] == _TERMINAL_NODE:
            closed.append(r)
        else:
            open_.append(r)
    return closed, open_


def _published_evidence(ledger):
    """Карточки, чей PUBLISHED доказан чтением СВЕРКА: {артикул: остаток}."""
    out = {}
    for r in ledger or []:
        if r.get("node") == "СВЕРКА" and r.get("verdict") == "PASS":
            ev = r.get("evidence")
            if isinstance(ev, dict):
                for art, a in ev.items():
                    if isinstance(a, dict) and isinstance(a.get("placement"), dict) \
                            and a["placement"].get("status") == "PUBLISHED":
                        st = a.get("stock")
                        if art not in out:
                            out[art] = st
    return out


def _card_costs_map():
    """Закуп донора по артикулам из _card_costs.json (fail-soft)."""
    p = RUNTIME / "_card_costs.json"
    d = _j(p) if p.exists() else {}
    cards = (d or {}).get("cards")
    if isinstance(cards, dict):
        out = {}
        for k, v in cards.items():
            if isinstance(v, dict) and v.get("cost") is not None:
                out[k] = v["cost"]
        return out
    return {}


def _ticks_txt():
    """Автопилот/цикл-дня: расписание + ближ. тик («идёт сам по расписанию»)."""
    sched = _schedule()
    nxt, secs = _next_run()
    nxt_txt = nxt.strftime("%H:%M") if nxt else "—"
    body = f"{len(sched)} тик(а)/сут {', '.join(sched)} MSK"
    if nxt_txt != "—":
        body += f" · ближ. {nxt_txt} через {_until_txt(secs)}"
    return body


def _ticks_brief():
    """Короткое расписание для сводных строк: «3×/сут … MSK» + ближ. тик, если влезает.
    Сводки кадра живут в 80 колонок — длинный хвост режется краем, теряя смысл."""
    sched = _schedule()
    base = f"{len(sched)}×/сут {', '.join(sched)} MSK"
    nxt, secs = _next_run()
    if nxt:
        full = base + f" · след. {nxt.strftime('%H:%M')} через {_until_txt(secs)}"
        if len(full) <= 46:
            return full
    return base


def _clean_note(n):
    """Сырая приписка леджера → чистая; «ok»/«None»/«-» не показываем как мусор."""
    n = str(n or "").strip()
    return "" if n.lower() in ("ok", "none", "—", "-", "есть") else n


def _camp_home_text(out, store, pl=None, now=None):
    """ДОМ ЯМ-ЦИКЛ <хеш> — один сводный кадр кампании. Всё честно из сторов:
    пульс · цикл дня (идёт сам) · циклы в работе · задания · гейт ЦИКЛ-1 ·
    результат дня. read 0₽ — сеть не зовём, движок не запускаем (RUBICON цел)."""
    out = out or sys.stdout
    pl = pl if pl is not None else store_payload(store)
    now = now or _now_msk()
    today = now.strftime("%Y-%m-%d")
    info, pulse, ledger = pl["info"], pl["pulse"], pl["ledger"]
    L = []

    # паспорт витрины (адрес биз/кампания/склад — в шапке кадра под хешем)
    extra = []
    if info.get("donor_category"):
        extra.append(f"донор {info['donor_category']}")
    if info.get("builder"):
        extra.append(f"builder {info['builder']}")
    if info.get("markup") is not None:
        extra.append(f"маржа ×{info['markup']}")
    if info.get("stock_count") is not None:
        extra.append(f"остаток {info['stock_count']}")
    if extra:
        L.append(_col(out, "DIM", "  " + " · ".join(extra)))
    if info.get("note"):
        L.append(_col(out, "DIM", "  " + _snip(info["note"], 66)))

    # ПУЛЬС
    L.append(_seal(out, "ПУЛЬС"))
    if not pulse:
        L.append(f"  {_col(out, 'YE', '○ пульса нет')} — первый сухой прогон соберёт")
    else:
        pdate = str(pulse.get("date", "?"))
        vd = pulse.get("run_verdicts") or {}
        vbits = " ".join(f"{k}{v}" for k, v in vd.items()) or "—"
        col = "GR" if pdate == today else "YE"
        line = f"  {_col(out, col, '●')} пульс {pdate} · вердикты {vbits} · арт {pulse.get('artifacts', 0)}"
        L.append(line[: _width(out)] if not _tty(out) else line)
        if pdate != today:
            L.append(_col(out, "YE", "     день ещё не гонялся сухо — прогнать (0₽)"))

    # ЦИКЛ СЕГОДНЯ — день живёт сам (автопилот/расписание), витрина не ждёт тебя
    L.append(_seal(out, "ЦИКЛ СЕГОДНЯ"))
    runs = _collapsed_runs(ledger)
    last_ts = _last_ts(ledger)
    if not runs:
        L.append(_col(out, "DIM", "  хода нет — витрина ждёт первого сухого прогона"))
    else:
        age = _age_txt(last_ts, now)
        L.append(_col(out, "DIM",
                      f"  прогонов {len(runs)} · строк {len(ledger)} · в работе "
                      f"{len(_open_runs(ledger)[1])} · последний ход "
                      f"{str(last_ts)[11:19] or '—'} · {age}"))
        run = runs[-1]
        marks = [(node + _col(out, _vmark(v)[0], _vmark(v)[1]))
                 for node, v, _n in run["nodes"] if node != "ДОНОР"]
        if marks:
            L.append("  след: " + "  ".join(marks))
    # день идёт по расписанию сам — витрина живая, независимо от смотра
    L.append(_col(out, "CY", "  ◌ цикл дня идёт сам: " + _ticks_brief()))

    # ЦИКЛЫ В РАБОТЕ — незакрытые прогоны (стартовали, до ПЛАНЁРКА не дошли)
    L.append(_seal(out, "ЦИКЛЫ В РАБОТЕ"))
    closed, open_ = _open_runs(ledger)
    if not open_:
        L.append(_col(out, "GR", "  ◉ чисто · незакрытых прогонов нет"
                                 + (f" · закрыто сегодня {len(closed)}" if closed else "")))
    else:
        for r in open_[-3:]:
            nodes = r["nodes"]
            last = nodes[-1]
            tcol, tch = _vmark(last[1])
            start_txt = str(r.get("ts", ""))[11:16]
            if len(nodes) == 1 and last[0] == "ДОНОР":
                L.append(f"  {_col(out, 'DIM', start_txt)}  прогон оборван на старте"
                         f" (узел ДОНОР {_col(out, tcol, tch)})"
                         + (f"  {_snip(_clean_note(last[2]), 28)}" if _clean_note(last[2]) else ""))
            else:
                L.append(f"  {_col(out, 'DIM', start_txt)}  старт {nodes[0][0]}"
                         f" → стоп на «{last[0]}» {_col(out, tcol, tch)}"
                         + (f"  {_snip(_clean_note(last[2]), 28)}" if _clean_note(last[2]) else ""))

    # АКТИВНЫЕ ЗАДАНИЯ — durable-реестр или живая очередь наблюдений
    L.append(_seal(out, "АКТИВНЫЕ ЗАДАНИЯ"))
    reg_status, reg_tasks = pl["registry"]
    queue = pl["queue"]
    if reg_status == "ok" and reg_tasks:
        for t in sorted(reg_tasks, key=lambda x: (x.get("priority", 50),
                                                  str(x.get("updated_at", ""))))[:4]:
            st = t.get("state", "open")
            icon = "◐" if st == "in_progress" else "○"
            col = "CY" if st == "in_progress" else "W"
            ndone = sum(1 for s in (t.get("steps") or [])
                        if isinstance(s, dict) and s.get("state") == "done")
            L.append(f"  {_col(out, col, icon)} {_col(out, 'B', _snip(t.get('what', ''), 60))}"
                     f" [{t.get('owner')}] · {ndone}/{len(t.get('steps') or [])}")
    elif reg_status == "error":
        L.append(_col(out, "RE", "  реестр заданий битый — читаю очередь из живых сторов"))
    if queue:
        for qq in queue[:3]:
            tag = _col(out, {"ЗАЛИВ": "CY", "ЧИНИТЬ": "RE", "ПУЛЬС": "YE"}.get(qq.get("tag"), "W"),
                       qq.get("tag", "?"))
            urg = "!!" if qq.get("urgency") == "high" else ""
            L.append(f"  ○ {tag} {urg} {_col(out, 'B', _snip(qq.get('what', ''), 44))}"
                     f" [{qq.get('owner')}]")
    if not ((reg_status == "ok" and reg_tasks) or queue):
        L.append(_col(out, "GR", "  ◉ витрина чиста: открытых заданий и наблюдений нет"))

    # ГЕЙТ ЦИКЛ-1 — честная статика; живое (ключ/остатки/сеть) — сухим прогоном
    L.append(_seal(out, "ГЕЙТ ЦИКЛ-1"))
    _gate_rows_append(L, out, info, ledger)

    # РЕЗУЛЬТАТ ДНЯ — что уже на витрине, доказано чтением
    L.append(_seal(out, "РЕЗУЛЬТАТ ДНЯ"))
    _result_rows_append(L, out, pulse, ledger)
    return "\n".join(L)


def _gate_rows_append(L, out, info, ledger):
    """Чек-лист гейта (read): статика с диска · «живое» помечаем сухим прогоном."""
    have = [f for f in _REQUIRED_STORE_FIELDS if info.get(f) not in (None, "")]
    pub = _published_evidence(ledger)
    cat = info.get("donor_category")
    L.append(_col(out, "GR", f"  ✓ манифест полон {len(have)}/{len(_REQUIRED_STORE_FIELDS)}"
                             f" · кампания {info.get('campaign_id') or '?'}"
                             f" · склад {info.get('warehouse_id') or '?'}"))
    L.append(_col(out, "GR", f"  ✓ донор «{_snip(cat or '—', 26)}» · builder {info.get('builder') or '—'}"
                             f" · маржа ×{info.get('markup') or '—'}"))
    if pub:
        st = next((v for v in pub.values() if v is not None), "?")
        L.append(_col(out, "GR", f"  ✓ витрина PUBLISHED ({len(pub)} арт, чтение СВЕРКА)"
                                 f" · остатки {st}"))
    else:
        L.append(_col(out, "YE", "  ○ витрина/остатки — докажет сухой прогон (0₽)"))
    L.append(_col(out, "DIM",
                  "  запуск новой партии → БРИГАДИР: ymarket_cycle1_v1 --dry (0₽)"))
    L.append(_col(out, "DIM", "  --commit — только по слову оператора (RUBICON)"))


def _result_rows_append(L, out, pulse, ledger):
    pub = _published_evidence(ledger)
    costs = _card_costs_map()
    total = sum(v for v in costs.values() if isinstance(v, (int, float)))
    if pub:
        st = next((v for v in pub.values() if v is not None), None)
        L.append(f"  {_col(out, 'GR', '●')} на витрине {len(pub)} арт PUBLISHED"
                 + (f" · остаток {st}" if st is not None else "")
                 + (f" · закуп донора ≈ {int(total)}₽ ({len(costs)} арт)"
                    if costs else ""))
    else:
        L.append(_col(out, "DIM", "  карточек на витрине ещё не доказано чтением"))
    if pulse and pulse.get("artifacts"):
        L.append(_col(out, "DIM", f"  артефакт цикла: {pulse.get('artifacts')}"))


def _gate_full_text(out, store, pl=None, now=None):
    """Под-экран ГЕЙТ ЦИКЛ-1 (по кнопке): честный полный чек-лист условий.
    Движок из ДОМА не запускается — только read-сводка и подсказка исполнителя."""
    out = out or sys.stdout
    pl = pl if pl is not None else store_payload(store)
    now = now or _now_msk()
    today = now.strftime("%Y-%m-%d")
    info, ledger = pl["info"], pl["ledger"]
    pub = _published_evidence(ledger)
    L = [f"  ДОМ показывает условия по закону ЦИКЛА-1 (ymarket_cycle1_v1).",
         f"  {_col(out, 'DIM', 'read 0₽: статика читается с диска; живое (ключ · остатки · сеть)')}",
         f"  {_col(out, 'DIM', '— доказывается СУХИМ прогоном, который ДОМ не запускает.')}",
         ""]
    L.append(_seal(out, "УСЛОВИЯ"))
    have = [f for f in _REQUIRED_STORE_FIELDS if info.get(f) not in (None, "")]
    checks = [
        ("манифест: 8 полей канона заполнены",
         len(have) == len(_REQUIRED_STORE_FIELDS)),
        (f"категория донора задана: «{info.get('donor_category') or '—'}»",
         bool(info.get("donor_category"))),
        (f"адрес витрины: биз {info.get('business_id') or '?'} · кампания "
         f"{info.get('campaign_id') or '?'} · склад {info.get('warehouse_id') or '?'}",
         all(info.get(k) for k in ("business_id", "campaign_id", "warehouse_id"))),
        (f"builder {info.get('builder') or '—'} · маржа ×{info.get('markup') or '—'} · "
         f"остаток {info.get('stock_count') or '—'}", True),
        ("витрина жива: карточки PUBLISHED (чтение СВЕРКА)",
         bool(pub)),
        ("остатки не выдуманы: читаются из СВЕРКА/стока",
         bool(pub) or bool(ledger)),
        ("ключ кабинета и доступы — только из env, здесь НЕ читаются",
         False),
        ("цепь сухая, без «мёртвых» узлов — доказывается сухим прогоном",
         False),
    ]
    for txt, ok in checks:
        mark = ("✓" if ok else "○")
        col = "GR" if ok else "DIM"
        L.append(f"  {_col(out, col, mark)} {txt}")
    L.append("")
    L.append(_seal(out, "КТО И КАК ЗАПУСКАЕТ"))
    L.append("  БРИГАДИР (орган-исполнитель, вне ДОМА):")
    L.append("    python3 ymarket_cycle1_v1.py --dry        # 0₽, сухой прогон")
    L.append("    python3 ymarket_cycle1_v1.py --commit     # по слову оператора (RUBICON)")
    L.append(_col(out, "DIM", "  ДОМ только смотрит и зовёт исполнителя — сам в сеть не ходит."))
    return "\n".join(L)


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
    """Строки меню ДОМ ЯМ-ЦИКЛА: что это · кампании (хеш) · действия цикла."""
    rows = []
    stores = stores or {}
    now = now or _now_msk()
    today = now.strftime("%Y-%m-%d")
    # пролог — один короткий ряд, сам себя объясняет
    rows.append(_text("ЯМ-ЦИКЛ: донор → сборка → залив → витрина → учёт → сверка —"))
    rows.append(_text("каждая кампания живёт сама по расписанию; здесь смотреть/управлять."))
    rows.append(_text("цикл дня идёт сам · " + _ticks_brief()))
    rows.append(_text(""))
    if not stores:
        rows.append(_text(_col_not("манифест пуст — магазинов ещё нет (0₽)")))
    else:
        rows.append(_sep(f"КАМПАНИИ · {len(stores)} в манифесте · цифра → ДОМ <хеш>"))
        for slug in sorted(stores):
            pulse = (pulse_of or _pulse)(slug) or {}
            pdate = str(pulse.get("date", ""))
            fresh = pdate == today
            h = _cycle_hash(slug, today)
            vd = pulse.get("run_verdicts") or {}
            vtxt = " ".join(f"{k}{v}" for k, v in vd.items()) or "хода нет"
            if fresh:
                brief = f"пульс {pdate} · {vtxt} · арт {pulse.get('artifacts', 0)}"
                col = "GR"
            elif pdate:
                brief = f"пульс {pdate} (устарел) · {vtxt}"
                col = "YE"
            else:
                brief = "пульса нет — сухой прогон соберёт"
                col = "DIM"
            rows.append(_item(f"store:{slug}", f"{slug} · {h}",
                              sub=f"  · {brief}", col=col))
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
    rows.append(_item("pult:fleet", "ПУЛЬТ · ШТАБ ЯМ-ЦИКЛА",
                      sub="живой пульт: КОМАНДИР ДНЯ · d сухо 0₽ · c живой (RUBICON · слово)",
                      col="GR"))
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
    if _viable_tty(out, inp):
        return _pick_tty(out, inp, title, sub, rows, prompt)
    items = _menu_items(rows)
    out.write(menu_text(out, title, sub, rows, prompt) + "\n")
    return _line_choice(out, inp, items)


def _pick_tty(out, inp, title, sub, rows, prompt):
    """Живой выбор стрелками на СТАБИЛЬНОМ кадре (V.enter/V.paint).

    Каждый ход — полная перерисовка фиксированного кадра через V.paint: никакого
    clear-кода в цикле и никаких переводов строки внутри кадра → терминал
    физически не скроллит и не «плывёт».
    alt-screen входит/выходит на виджет: мозг (свой REPL на input()) после
    возврата работает в обычном кухонном терминале.
    """
    items = _menu_items(rows)
    n = len(items)
    sel = 0
    fd, old = V.enter(out, inp)
    try:
        while True:
            V.paint(out, _nav_cells(out, title, sub, rows, sel, prompt))
            key = _read_key(inp, fd)
            if n == 0:
                if key in ("q", "esc"):
                    return None
                continue
            if key in ("up", "k"):
                sel = (sel - 1) % n
            elif key in ("down", "j"):
                sel = (sel + 1) % n
            elif key == "enter":
                return items[sel]
            elif key in ("q", "esc"):
                return None
            elif key.isdigit():
                d = int(key)
                if 1 <= d <= n:
                    return items[d - 1]
    finally:
        V.leave(out, fd, old)


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
    """Полный экран с контентом; любой клавишей/q — назад (одна ступень)."""
    if _viable_tty(out, inp):
        _read(out, inp, title=title, sub="read 0₽ · листай и возвращайся",
              body=str(content).split("\n"),
              hint=(footer or "↑↓ — листать · q — назад"))
        return "back"
    out.write(_band(out, title, right=_clock()) + "\n")
    out.write(content + "\n")
    return "back"


# ── ЖИВОЙ ЭКРАН (автообновление) ──────────────────────────────────────────────
def _live_body(out, scope, store=None, now=None):
    """Тело живого экрана (без шапки/таймера — их накладывает кадр). Единый
    источник: plain-кадр live_frame и tty-кадр _live_cells зовут его."""
    now = now or _now_msk()
    L = []
    if scope == "home":
        for o in H._ORGANS:
            try:
                state, note, _hint = o["probe"]()
            except Exception:
                state, note = "off", "зонд упал"
            L.append(f"  {o['icon']} {o['title']:<26} {_state_dot(out, state)} "
                     f"{_state_word(state):<7} · {_snip(note, 60)}")
    elif scope == "ym":
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
        L += store_text(out, store, pl, now=now).split("\n")
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
    return L


def live_frame(out, scope, store=None, now=None):
    """Полный ПЛОСКИЙ кадр живого экрана (StringIO/пайп). scope ∈ home|ym|store:."""
    out = out or sys.stdout
    now = now or _now_msk()
    nxt, secs = _next_run(now)
    if scope == "home":
        L = [_band(out, "SOCC · ДОМ · ЖИВОЙ", right=_clock(),
                   sub="автообновление · read 0₽")]
    elif scope == "ym":
        L = [_band(out, "ЯМ-ЦИКЛ · ЖИВОЙ", right=_clock(),
                   sub="витрины · пульсы · леджеры · read 0₽")]
    else:
        store = store or scope[6:]
        L = [_band(out, f"ЯМ · {store} · ЖИВОЙ", right=_clock(),
                   sub="леджер цикла растёт на глазах · read 0₽")]
    L.append("")
    L += _live_body(out, scope, store=store, now=now)
    L.append("")
    L.append(_seal(out, "АВТОПИЛОТ"))
    nxt_txt = nxt.strftime("%H:%M") if nxt else "—"
    L.append(f"  следующий тик {nxt_txt} MSK · через {_until_txt(secs)}"
             + (_col(out, "RE", "  · ИДЁТ (в окне)" if secs and secs < 240 else "")))
    L.append(_col(out, "DIM", "  q / любая клавиша — назад в меню"))
    return "\n".join(L)


def _live_cells(out, scope, store=None, now=None):
    """Клетки ЖИВОГО кадра (tty): тело якорено К НИЗУ (свежий ход на последней
    строке тела), низ 3 прижат — таймер автопилота и подсказка всегда видны."""
    now = now or _now_msk()
    rows_, _c, _w = _geom()
    body_h = rows_ - _HEAD - _FOOT
    full = _live_body(out, scope, store=store, now=now)
    win = full if len(full) <= body_h else full[-body_h:]
    if scope == "home":
        title, sub = "SOCC · ДОМ" + _MARK_LIVE, "автообновление · read 0₽"
    elif scope == "ym":
        title, sub = "ЯМ-ЦИКЛ" + _MARK_LIVE, "витрины · пульсы · леджеры · read 0₽"
    else:
        st = store or (scope[6:] if scope and scope.startswith("store:") else scope)
        title, sub = f"ЯМ · {st}" + _MARK_LIVE, "леджер цикла растёт на глазах · read 0₽"
    nxt, secs = _next_run(now)
    nxt_txt = nxt.strftime("%H:%M") if nxt else "—"
    go = _col(out, "RE", "  · ИДЁТ (в окне)") if secs and secs < 240 else ""
    foot = [
        "read 0₽ · авто-кадр каждые 2с · пульс органов дышит на диске",
        f"АВТОПИЛОТ · следующий тик {nxt_txt} MSK · через {_until_txt(secs)}{go}",
        "q / любая клавиша — назад в меню",
    ]
    return _frame(out, title, sub, win, [_col(out, "DIM", t) for t in foot])


def _live(out, inp, scope, store=None, interval=2.0):
    """Живой экран на стабильном кадре: полный кадр каждые interval, клавиша —
    выход. Вне tty/маленького экрана — один плоский кадр (не ломаемся)."""
    import select
    if not _viable_tty(out, inp):
        out.write(live_frame(out, scope, store=store) + "\n")
        return
    fd, old = V.enter(out, inp)
    try:
        while True:
            V.paint(out, _live_cells(out, scope, store=store))
            r, _, _ = select.select([inp], [], [], interval)
            if not r:
                continue
            try:  # слить накопленное без блокировки и выйти
                while True:
                    rr, _, _ = select.select([inp], [], [], 0)
                    if not rr:
                        break
                    os.read(fd, 64)
            except Exception:
                pass
            return
    finally:
        V.leave(out, fd, old)


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
    # мозг живёт в арбитре; запускаем В ПРОЦЕССЕ (read-REPL, как socc ym мозг).
    # Alt-screen уже покинут (V.leave в pick) — отделяемся пустой строкой, не 2J.
    out.write("\n")
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
def _brief_tasks(pl):
    """Короткая подпись активных заданий. Всегда в нижней строке READ витрины —
    задания видны даже когда тело экрана ушло под сгиб (оператор видит их сразу)."""
    reg_status, reg_tasks = pl["registry"]
    if reg_status == "ok" and reg_tasks:
        owners = []
        for t in reg_tasks:
            o = str(t.get("owner", ""))
            if o and o not in owners:
                owners.append(o)
        who = " · ".join(owners[:3]) or "разные роли"
        return f"АКТИВНЫЕ ЗАДАНИЯ · {len(reg_tasks)} · {who}"
    q = pl["queue"]
    if q:
        return f"АКТИВНЫЕ ЗАДАНИЯ · наблюдений {len(q)} · живая очередь"
    return "АКТИВНЫЕ ЗАДАНИЯ · 0 · витрина чиста"


def _run_pult_store(out, inp, store):
    """КОМАНДИР ДНЯ витрины в ПУЛЬТЕ: правило хода + деньги + d/c рельсы.

    Ленивый импорт: pult.py — единственный исполнитель ДОМА (запуск движка —
    только там, тем же argv). dom.py остаётся DH8-чистым (без write-токенов)."""
    import socc_cli.pult as Pult
    Pult.run_store_pult(out, inp, store)
    return "back"


def _run_store_tty(out, inp, store):
    """ДОМ кампании на живом tty: ДОМ ЯМ-ЦИКЛ <хеш> — сводный кадр читается,
    ДЕЙСТВИЯ прижаты книзу (ЖИВОЙ · ПУЛЬТ · ГЕЙТ · АВТО · ЗАДАНИЯ · НАЗАД), тело
    листается. Движок не запускается: ГЕЙТ — честная read-сводка; ПУЛЬТ —
    единственный исполнитель (КОМАНДИР ДНЯ, запуск движка по слову оператора)."""
    info = _store_info(store)
    h = _cycle_hash(store)
    sub = (f"хеш {h} · витрина Экспресс · биз {info.get('business_id') or '?'} · "
           f"кампания {info.get('campaign_id') or '?'} · склад {info.get('warehouse_id') or '?'}")
    while True:
        pl = store_payload(store)
        content = _camp_home_text(out, store, pl)
        buttons = [("live:store", "ЖИВОЙ"),
                   ("pult:store", "ПУЛЬТ"),
                   ("gate", "ГЕЙТ"),
                   ("view:авто", "АВТО"),
                   ("view:задания", "ЗАДАНИЯ"),
                   ("quit", "НАЗАД")]
        act = _read(out, inp, title=f"ДОМ ЯМ-ЦИКЛ · {store}", sub=_snip(sub, 70),
                    body=content.split("\n"), buttons=buttons,
                    summary=_brief_tasks(pl),
                    hint="ПУЛЬТ = КОМАНДИР ДНЯ: правило хода + d/c · цифра · ↑↓ · q — к кампаниям")
        if act is None or act == "quit":
            return -1
        if act == "live:store":
            _live(out, inp, "store:" + store)
            continue
        if act == "pult:store":
            _run_pult_store(out, inp, store)
            continue
        if act == "gate":
            _show_pause(out, inp, f"ДОМ ЯМ-ЦИКЛ · {store} · ГЕЙТ",
                        _gate_full_text(out, store),
                        footer="↑↓ — листать · q — назад в ДОМ кампании")
            continue
        if act.startswith("view:"):
            _show_pause(out, inp, f"ЯМ · {store}", _ym_subview(out, act[5:]),
                        footer="↑↓ — листать · q — назад в витрину")
            continue


def run_store(out, inp, store):
    if _viable_tty(out, inp):
        return _run_store_tty(out, inp, store)
    # не-tty (тесты/пайп) — прежний выбор строками, ничего не ломаем
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
            _show_pause(out, inp, f"ЯМ · {store}", _ym_subview(out, act[5:]))


def run_ym(out, inp):
    stores = _stores_map()
    while True:
        rows = ym_rows(stores)
        ch = pick(out, inp, title="ДОМ ЯМ-ЦИКЛА",
                  sub=f"магазинов в манифесте: {len(stores)} · цифра → ДОМ кампании <хеш>",
                  rows=rows, prompt="выбери кампанию / экран · q — назад в ДОМ")
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
        if act == "pult:fleet":
            # ПУЛЬТ · ШТАБ ЯМ — единственный исполнитель ДОМА. Ленивый импорт:
            # dom.py остаётся DH8-чистым (исполнитель-код только в pult.py).
            import socc_cli.pult as Pult
            Pult.run_fleet(out, inp)
            continue
        if act.startswith("view:"):
            subv = act[5:]
            if subv == "мозг":
                _run_brain(out, inp)
            else:
                _show_pause(out, inp, "ЯМ-ЦИКЛ", _ym_subview(out, subv))
            continue


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
            _show_pause(out, inp, f"SOCC · {org.upper()}", _organ_face(out, org))
            continue


def store_screen_text(out, store):
    """Один-экран витрины (не-tty / пайп / --text)."""
    return store_text(out, store, store_payload(store))


if __name__ == "__main__":
    sys.exit(run_home(sys.stdout, sys.stdin))

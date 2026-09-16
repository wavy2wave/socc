#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · ЭКОСИСТЕМА магазина — read-навигатор (socc_cli/eco.py).

Оператор: «строим именно CLI-интерфейс, который И ЕСТЬ наша система. Не просто
обёртка, а ЖИВОЙ ПУЛЬТ управления» + видение магазина как эко-системы со своими
разделами, в порядке: ЗАДАНИЯ → ЦИКЛЫ → (дневной пул по ролям) → СОТРУДНИКИ →
ДОНОР → АРТЕФАКТЫ; каждое нажатие проваливает в раздел со своим интерфейсом;
в ЦИКЛЫ провал в прогон = его отчёт/логи. Вилка «Только read 0₽»: слой-чтение,
writes не трогаем; «Все секции разом»: навигатор сразу со всеми секциями, где
данных нет — честно «не материализовано», футер-резерв «ЗАКАЗЫ — проектируется».

Закон разделения (как pult.py): eco — чистый read-слой поверх dom (импортирует
dom как D, всё читает через D-хелперы на момент вызова — мононе-патчабельно).
Сам файлы НЕ пишет, движок НЕ запускает, сети нет, шелла нет. dom.py зовёт eco
ЛЕНИВЫМ импортом в рантайме (как pult) и остаётся DH8-чистым. RUBICON цел.
"""
from __future__ import annotations

import re
import sys

from socc_cli import dom as D

# ── порядок секций (видение оператора: ЗАДАНИЯ первые, цикл второе) ────────────
_SECTIONS = [
    ("задания",    "ЗАДАНИЯ"),
    ("циклы",      "ЦИКЛЫ"),
    ("сотрудники", "СОТРУДНИКИ"),
    ("донор",      "ДОНОР"),
    ("артефакты",  "АРТЕФАКТЫ"),
]
# 3-й пункт видения «дневной пул по ролям» живёт ВНУТРИ СОТРУДНИКИ (см. _emp_lines)

# Цвета тегов живой очереди (токены канона style)
_TAG_COL = {"ЗАЛИВ": "CY", "ЧИНИТЬ": "RE", "ПУЛЬС": "YE", "СВЕРКА": "GR"}

# Офис-роли ДОМА ЯМ: owner-ключ → имя_ru (фолбэк, если офис не импортировался)
_FALLBACK = {
    "BRIGADE": "БРИГАДИР", "DISPATCHER": "ДИСПЕТЧЕР", "STOCKMAN": "СКЛАДОВЩИК",
    "MERCHANDISER": "ТОВАРОВЕД", "PRICER": "ЦЕНОВИК", "CONTROLLER": "КОНТРОЛЁР",
    "MANAGER": "УПРАВЛЯЮЩИЙ", "STRATEGIST": "СТРАТЕГ", "TRENDSCOUT": "ТРЕНД-СКАУТ",
    "HEAD": "ГОЛОВА", "CATEGORIST": "КАТЕГОРИЙЩИК", "GROWTH": "СКАУТ РОСТА",
    "ZALIV": "СБОРЩИК",
}
_NAMES = None  # кэш офис-роста (ленивый, fail-soft)


def _names():
    """owner-ключ → имя_ru. Офис читаем fail-soft; не смогли — фолбэк-словарь."""
    global _NAMES
    if _NAMES is not None:
        return _NAMES
    try:
        if str(D.ARB) not in sys.path:
            sys.path.insert(0, str(D.ARB))
        import ymarket_office_v1 as _off  # noqa: E402
        rost = getattr(_off, "ROSTER", None) or {}
        if isinstance(rost, dict) and rost:
            out = {}
            for k, v in rost.items():
                if isinstance(v, dict):
                    out[str(k).upper()] = str(v.get("name_ru") or k)
                else:
                    out[str(k).upper()] = str(v or k)
            _NAMES = out
            return _NAMES
    except Exception:
        pass
    _NAMES = dict(_FALLBACK)
    return _NAMES


# ── мелкие помощники (ширина 78 — закон EC10) ──────────────────────────────────
def _fit(out, line, n=78):
    """Одна строка ≤n клеток (plain). Цвет не разрезается; длинное режется «…»."""
    s = str(line)
    plain = D._ansi_strip(s)
    if len(plain) <= n:
        return s
    if D._tty(out):
        import socc_cli.view as V
        return V.clip_ansi(s, n)
    return plain[: n - 1] + "…"


def _ts_hm(ts):
    """ts (iso или HH:MM:SS) → 'HH:MM' для строк отчёта."""
    s = str(ts or "")
    m = re.search(r"(?:T|\s)(\d{2}):(\d{2})", s)
    if m:
        return m.group(1) + ":" + m.group(2)
    m = re.match(r"(\d{1,2}):(\d{2})", s)
    return (m.group(1).zfill(2) + ":" + m.group(2)) if m else "—"


def _runs_rows(ledger):
    """Леджер → прогоны (каждый стартует на узле ДОНОР), полные строки сохранены."""
    runs, cur = [], None
    for r in ledger or []:
        node = r.get("node")
        if not node:
            continue
        if cur is None or node == "ДОНОР":
            cur = []
            runs.append(cur)
        cur.append(r)
    return runs


def _run_meta(run):
    """Прогон → {start, n, closed, verdict, node, dry, live} — честно из строк."""
    first, last = (run[0] if run else None), (run[-1] if run else None)
    closed = bool(last and last.get("node") == D._TERMINAL_NODE)
    return dict(
        start=_ts_hm(first.get("ts") if first else None),
        n=len(run),
        closed=closed,
        verdict=str((last or {}).get("verdict", "?")),
        node=str((last or {}).get("node", "?")),
        dry=sum(1 for r in run if r.get("dry") is not False),
        live=sum(1 for r in run if r.get("dry") is False),
    )


def _donor_artifacts(info):
    """Артефакты разведки донора (канон отчётов) по категориям манифеста."""
    cands = {info.get("donor_category"), info.get("builder_slug"),
             info.get("builder"), info.get("category")}
    out, seen = [], set()
    for c in cands:
        if not c:
            continue
        try:
            for p in sorted(D.H.REPORTS.glob(f"ymarket_runner_donor_{c}_*.json")):
                if p.name in seen:
                    continue
                seen.add(p.name)
                obj = D._j(p)
                ts = str((obj or {}).get("ts", "") or "")[:19]
                out.append({"name": p.name, "ts": ts})
        except Exception:
            continue
    out.sort(key=lambda a: a["ts"], reverse=True)
    return out


def _matrix_ready_count(store, info):
    """Карточки матрицы «собран» (offer пуст) этой категории — ждут залива."""
    d = D._j(D.MATRIX_JSON)
    rows = d.get("rows", d) if isinstance(d, dict) else d
    items = list(rows.values()) if isinstance(rows, dict) \
        else (rows if isinstance(rows, list) else [])
    cats = {c for c in (info.get("donor_category"), info.get("builder_slug"),
                        info.get("builder"), info.get("category")) if c}
    return sum(1 for r in items if isinstance(r, dict) and r.get("status") == "собран"
               and not r.get("offer_id")
               and (not cats or (r.get("category") or "") in cats))


def _employees(pl):
    """Активные владельцы (реестр-задачи + живая очередь) этого магазина."""
    reg_status, reg_tasks = pl.get("registry", ("absent", []))
    tasks = reg_tasks if reg_status == "ok" else []
    queue = pl.get("queue", [])
    names = _names()
    idx = {}
    for t in tasks:
        o = str(t.get("owner") or "?")
        idx.setdefault(o, {"owner": o, "name": names.get(o, o),
                           "tasks": [], "obs": []})["tasks"].append(t)
    for qq in queue:
        o = str(qq.get("owner") or "?")
        idx.setdefault(o, {"owner": o, "name": names.get(o, o),
                           "tasks": [], "obs": []})["obs"].append(qq)
    return list(idx.values())


def _run_counts(pl):
    """(закрыто, в_работе) по леджеру — конец ПЛАНЁРКА (DH-честно)."""
    runs = _runs_rows(pl.get("ledger", []))
    closed = sum(1 for r in runs if _run_meta(r)["closed"])
    return closed, len(runs) - closed


# ── маркеры секций (одна функция-источник, честно) ─────────────────────────────
def _section_markers(out, pl, store):
    markers = {}
    reg_status, reg_tasks = pl.get("registry", ("absent", []))
    queue = pl.get("queue", [])
    if reg_status == "absent":
        markers["задания"] = "реестр не материализован"
    elif reg_status == "ok":
        markers["задания"] = f"задач открыто {len(reg_tasks)}"
    else:
        markers["задания"] = "реестр битый"
    if queue:
        markers["задания"] += f" · наблюдений {len(queue)}"

    closed, open_ = _run_counts(pl)
    runs = _runs_rows(pl.get("ledger", []))
    markers["циклы"] = (f"прогонов {len(runs)} · закрыто {closed} · в работе {open_}"
                        if runs else "прогонов нет — ждём первый сухой")

    emps = _employees(pl)
    markers["сотрудники"] = (f"в работе ролей {len(emps)}"
                             if emps else "никто в работе — очередь пуста")

    info = pl.get("info") or {}
    arts = _donor_artifacts(info)
    markers["донор"] = f"{info.get('donor_category') or 'донор не задан'} · артефактов {len(arts)}"

    pub = len(D._published_evidence(pl.get("ledger", [])))
    got = _matrix_ready_count(store, info)
    markers["артефакты"] = f"PUBLISHED {pub} · собрано {got} · закрытых {closed}"
    return markers


# ── строки секций (для паузы и плоского текста) ────────────────────────────────
def _task_short(out, t):
    who = _names().get(str(t.get("owner") or ""), t.get("owner") or "—")
    what = D._snip(t.get("what", ""), 34)
    steps = [s for s in (t.get("steps") or []) if isinstance(s, dict)]
    if steps:
        done = sum(1 for s in steps if s.get("state") == "done")
        return f"{t.get('id') or 'T-?'} · {who}: {what} · пунктов {done}/{len(steps)}"
    return f"{t.get('id') or 'T-?'} · {who}: {what}"


def _obs_short(out, qq):
    who = _names().get(str(qq.get("owner") or ""), qq.get("owner") or "—")
    what = D._snip(qq.get("what", ""), 40)
    return f"[{qq.get('tag') or 'ШАГ'}] {who}: {what}"


def _obs_line(out, qq):
    """Строка наблюдения живой очереди (тег цветом на tty)."""
    head = f"[{qq.get('tag') or 'ШАГ'}]"
    if D._tty(out):
        head = D._col(out, _TAG_COL.get(qq.get("tag"), "DIM"), head)
    who = _names().get(str(qq.get("owner") or ""), qq.get("owner") or "—")
    what = D._snip(qq.get("what", ""), 44)
    ex = "!" if qq.get("urgency") == "high" else ""
    return f"  ○ {head}{ex} {who}: {what}"


def _task_line(out, t):
    """Строка durable-задачи реестра."""
    who = _names().get(str(t.get("owner") or ""), t.get("owner") or "—")
    what = D._snip(t.get("what", ""), 36)
    L = f"  {t.get('id') or 'T-?'} · {who}: {what}"
    steps = [s for s in (t.get("steps") or []) if isinstance(s, dict)]
    if steps:
        done = sum(1 for s in steps if s.get("state") == "done")
        L += f" · пунктов {done}/{len(steps)}"
    urg = t.get("urgency")
    if urg:
        L += f" · {urg}"
    return L


def _emp_lines(out, e):
    """Блок одного сотрудника: имя + его задачи/наблюдения (дневной пул роли)."""
    L = [D._col(out, "CY", f"  {e['name']} ({e['owner']})")]
    if not e["tasks"] and not e["obs"]:
        L.append(D._col(out, "DIM", "     свободен — задач и наблюдений нет"))
        return L
    for t in e["tasks"]:
        L.append("     · " + _task_short(out, t))
    for qq in e["obs"]:
        L.append("     · " + _obs_short(out, qq))
    return L


def _run_lines(out, store, run, pl, idx=None):
    """Отчёт одного прогона (= отчёты/логи ЦИКЛ ДНЯ): узлы сухо/живой + evidence."""
    meta = _run_meta(run)
    L = []
    head = f"  ПРОГОН {idx}" if idx else "  ПРОГОН"
    head += f" · старт {meta['start']} · узлов {meta['n']}"
    head += (f" · закрыт {D._TERMINAL_NODE} {meta['verdict']}"
             if meta["closed"] else f" · в работе — стоп «{meta['node']}»")
    L.append(D._col(out, "GR" if meta["closed"] else "YE", head))
    L.append(D._col(out, "DIM",
                    f"  хеш дня {D._cycle_hash(store)} · сухих {meta['dry']} · "
                    f"живых {meta['live']}"))
    for r in run:
        node = r.get("node", "?")
        col, mark = D._vmark(r.get("verdict"))
        tshm = _ts_hm(r.get("ts"))
        drytag = "сухо" if r.get("dry") is not False else "ЖИВОЙ"
        note = D._snip(D._clean_note(r.get("note")), 40)
        L.append(f"  {tshm} {D._col(out, col, mark)} {node:<9} {drytag:<5} {note}")
        ev = r.get("evidence")
        if isinstance(ev, dict):
            for art, a in ev.items():
                if isinstance(a, dict) and isinstance(a.get("placement"), dict) \
                        and a["placement"].get("status") == "PUBLISHED":
                    st = a.get("stock")
                    L.append(D._col(out, "GR", f"      → {art} PUBLISHED · остаток {st}"))
    if meta["closed"]:
        L.append(D._col(out, "GR",
                        f"  ✓ прогон закрыт {D._TERMINAL_NODE} — цепь прошла до конца"))
    else:
        L.append(D._col(out, "YE", f"  ◌ прогон не закрыт — ждём {D._TERMINAL_NODE}"))
    return L


# ── полные тела секций (используются и для паузы-дрилла, и для плоского) ───────
def _tasks_lines(out, pl):
    L = []
    reg_status, reg_tasks = pl.get("registry", ("absent", []))
    queue = pl.get("queue", [])
    L.append(D._col(out, "CY", "  РЕЕСТР · DURABLE (ymarket_tasks.json)"))
    if reg_status == "absent":
        L.append(D._col(out, "DIM",
                        "  реестр не материализован — появится, когда ЦИКЛ-ДЕНЬ "
                        "запишет журнал заданий"))
    elif reg_status == "error":
        L.append(D._col(out, "RE",
                        "  реестр битый — файл есть, но задач в нём не читается"))
    elif not reg_tasks:
        L.append(D._col(out, "GR", "  открытых задач нет — всё закрыто/архивировано"))
    else:
        for t in reg_tasks:
            L.append(_task_line(out, t))
    L.append("")
    L.append(D._col(out, "CY", "  НАБЛЮДЕНИЯ · ЖИВАЯ ОЧЕРЕДЬ (из сторов)"))
    if not queue:
        L.append(D._col(out, "GR", "  наблюдений нет — витрина чиста"))
    else:
        for qq in queue:
            L.append(_obs_line(out, qq))
    return L


def _cycles_lines(out, store, pl):
    L = []
    runs = _runs_rows(pl.get("ledger", []))
    if not runs:
        L.append(D._col(out, "DIM", "  прогонов нет — витрина ждёт первого сухого (0₽)"))
        L.append(D._col(out, "CY", "  ◌ цикл дня идёт по расписанию — след появится в леджере"))
        return L
    L.append(D._col(out, "CY",
                    f"  прогонов {len(runs)} · каждый — свой отчёт (провал → логи)"))
    for i, run in enumerate(runs, 1):
        L.append("")
        L += _run_lines(out, store, run, pl, idx=i)
    return L


def _employees_lines(out, pl):
    L = []
    emps = _employees(pl)
    if not emps:
        L.append(D._col(out, "DIM",
                        "  активных в магазине нет — очередь пуста, реестр спит"))
        return L
    L.append(D._col(out, "CY",
                    f"  в работе ролей {len(emps)} · занятость — по задачам и наблюдениям"))
    for e in emps:
        L += _emp_lines(out, e)
    return L


def _donor_lines(out, pl):
    info = pl.get("info") or {}
    L = []
    cat = info.get("donor_category") or info.get("builder_slug") or "донор не задан"
    L.append(D._col(out, "CY", f"  ДОНОР · РАЗВЕДКА ЗЕМЕЛЬ · {cat}"))
    bits = []
    if info.get("builder"):
        bits.append(f"builder {info['builder']}")
    if info.get("markup") is not None:
        bits.append(f"маржа ×{info['markup']}")
    if info.get("stock_count") is not None:
        bits.append(f"остаток {info['stock_count']}")
    if bits:
        L.append("  " + " · ".join(bits))
    note = info.get("note")
    if note:
        L.append(D._col(out, "DIM", "  " + D._snip(str(note), 70)))
    L.append("")
    L.append(D._col(out, "CY", "  АРТЕФАКТЫ ОРГАНА (разведка · файлы канона)"))
    arts = _donor_artifacts(info)
    if not arts:
        L.append(D._col(out, "DIM",
                        "  артефактов донора нет — разведка ещё не гонялась (0₽)"))
    else:
        L.append(D._col(out, "DIM", f"  файлов {len(arts)} · свежие сверху"))
        for a in arts[:6]:
            L.append(f"  · {D._snip(a['name'], 58)}")
            if a["ts"]:
                L.append(D._col(out, "DIM", "      " + a["ts"]))
        if len(arts) > 6:
            L.append(D._col(out, "DIM", f"      … ещё {len(arts) - 6} файлов"))
    return L


def _art_lines(out, store, pl):
    ledger = pl.get("ledger", [])
    info = pl.get("info") or {}
    L = []
    L.append(D._col(out, "CY", "  ВИТРИНА · PUBLISHED (доказано СВЕРКА)"))
    pub = D._published_evidence(ledger)
    if not pub:
        L.append(D._col(out, "DIM",
                        "  на витрине 0 — PUBLISHED докажет СВЕРКА после живого залива"))
    else:
        for art, st in pub.items():
            L.append(D._col(out, "GR", f"  ✓ {art} · остаток {st}"))
    L.append("")
    L.append(D._col(out, "CY", "  СБОРКА · МАТРИЦА"))
    got = _matrix_ready_count(store, info)
    if got:
        L.append(D._col(out, "GR",
                        f"  собрано карточек {got} · ждут залива (собран → offer/ean пуст)"))
    else:
        L.append(D._col(out, "DIM",
                        "  собранных карточек нет — сборка ещё не дала готовых"))
    L.append("")
    L.append(D._col(out, "CY", "  ЗАТРАТЫ · КАРТЫ ЗАКУПА"))
    costs = D._card_costs_map()
    if costs:
        total = sum(int(v or 0) for v in costs.values())
        L.append(D._col(out, "GR", f"  карт закупа {len(costs)} · сумма {total}₽"))
    else:
        L.append(D._col(out, "DIM", "  карт закупа нет"))
    L.append("")
    L.append(D._col(out, "CY", "  ПРОГОНЫ"))
    closed, open_ = _run_counts(pl)
    L.append(f"  закрыто {closed} · в работе {open_}")
    L.append(D._col(out, "DIM",
                    "  процент выполнения задания — когда появится реестр с пунктами "
                    "(ЦИКЛ-ДЕНЬ)"))
    return L


def _section_lines(out, key, store, pl):
    if key == "задания":
        return _tasks_lines(out, pl)
    if key == "циклы":
        return _cycles_lines(out, store, pl)
    if key == "сотрудники":
        return _employees_lines(out, pl)
    if key == "донор":
        return _donor_lines(out, pl)
    if key == "артефакты":
        return _art_lines(out, store, pl)
    return []


# ── навигатор (плоский текст + интерактив) ─────────────────────────────────────
def eco_store_text(out, store, pl=None):
    """Плоский ЭКО-лист магазина (не-tty/пайп/--text): навигатор + все разделы."""
    out = out or sys.stdout
    pl = pl if pl is not None else D.store_payload(store)
    info = pl.get("info") or {}
    h = D._cycle_hash(store)
    L = []
    sub = (f"хеш {h} · лицо магазина · разделы на живых данных (read 0₽) · "
           f"биз {info.get('business_id') or '?'} · кампания "
           f"{info.get('campaign_id') or '?'} · склад {info.get('warehouse_id') or '?'}")
    L.append(D._band(out, f"ЭКОСИСТЕМА · {store}", right=D._clock(out),
                     sub=D._snip(sub, 70)))
    L.append("")
    L.append(D._seal(out, "РАЗДЕЛЫ · НАВИГАТОР"))
    markers = _section_markers(out, pl, store)
    for n, (key, label) in enumerate(_SECTIONS, 1):
        L.append(f"  {n}. {label} — {markers.get(key, '')}")
    L.append(D._col(out, "DIM", "  — ЗАКАЗЫ и другие разделы — проектируются (резерв)"))
    L.append("")
    for key, label in _SECTIONS:
        L.append(D._seal(out, label))
        L += _section_lines(out, key, store, pl)
        L.append("")
    L.append(D._col(out, "DIM",
                    "read 0₽ · движок не запускается · данные: манифест/леджер/пульс/"
                    "матрица/артефакты/офис"))
    # _band/_seal могут вернуть многострочные блоки — распластываем ПО-строково,
    # иначе _fit обрежет весь блок как одну «строку» >78 (EC1/EC2/EC10).
    flat = []
    for ln in L:
        flat.extend(str(ln).split("\n"))
    return "\n".join(_fit(out, sub) for sub in flat)


def _nav_rows(out, store, pl):
    """Строки навигатора для pick: секции (с маркерами) + назад."""
    markers = _section_markers(out, pl, store)
    rows = [D._item("sec:" + key, label, sub=markers.get(key, ""))
            for key, label in _SECTIONS]
    rows.append(D._item("quit", "Назад к ДОМУ ЯМ-ЦИКЛ"))
    return rows


def _show_section(out, inp, store, key):
    """Провал в раздел: ЗАДАНИЯ/ДОНОР/АРТЕФАКТЫ — пауза; ЦИКЛЫ/СОТРУДНИКИ — свой pick."""
    label = dict(_SECTIONS)[key]
    title = f"ЭКОСИСТЕМА · {store} · {label}"
    pl = D.store_payload(store)
    if key == "циклы":
        _drill_cycles(out, inp, store)
        return
    if key == "сотрудники":
        _drill_staff(out, inp, store)
        return
    body = "\n".join(_fit(out, ln) for ln in _section_lines(out, key, store, pl))
    D._show_pause(out, inp, title, body,
                  footer="↑↓ — листать · q — назад в ЭКО-навигатор")


def _drill_cycles(out, inp, store):
    """ЦИКЛЫ: выбрать прогон → его отчёт/логи; q — назад в навигатор."""
    while True:
        pl = D.store_payload(store)
        runs = _runs_rows(pl.get("ledger", []))
        if not runs:
            D._show_pause(out, inp, f"ЭКОСИСТЕМА · {store} · ЦИКЛЫ",
                          "  прогонов нет — витрина ждёт первого сухого (0₽)\n\n"
                          "  ◌ цикл дня идёт по расписанию — след появится в леджере",
                          footer="q — назад в ЭКО-навигатор")
            return
        rows = []
        for i, run in enumerate(runs, 1):
            m = _run_meta(run)
            label = f"прогон {i} · старт {m['start']} · узлов {m['n']}"
            if m["closed"]:
                label += f" · закрыт {D._TERMINAL_NODE}"
            else:
                label += f" · в работе"
            sub = (f"конец «{m['node']}» {m['verdict']} · сухих {m['dry']} · "
                   f"живых {m['live']} · хеш {D._cycle_hash(store)}")
            rows.append(D._item(f"run:{i}", label, sub=sub))
        rows.append(D._item("quit", "Назад к разделу ЦИКЛЫ"))
        ch = D.pick(out, inp,
                    title=f"ЭКОСИСТЕМА · {store} · ЦИКЛЫ",
                    sub="провал в прогон = его отчёт/логи (ЦИКЛ ДНЯ, read 0₽)",
                    rows=rows,
                    prompt="цифра / Enter — отчёт прогона · q — назад в навигатор")
        if ch is None or ch["action"] == "quit":
            return
        i = int(ch["action"][4:]) - 1
        if 0 <= i < len(runs):
            run = runs[i]
            body = "\n".join(_fit(out, ln)
                             for ln in _run_lines(out, store, run, pl, idx=i + 1))
            D._show_pause(out, inp,
                          f"ЦИКЛ · отчёт прогона · {store}",
                          body, footer="↑↓ — листать · q — назад к ЦИКЛАМ")


def _drill_staff(out, inp, store):
    """СОТРУДНИКИ: выбрать роль → её задачи/наблюдения; q — назад."""
    while True:
        pl = D.store_payload(store)
        emps = _employees(pl)
        if not emps:
            D._show_pause(out, inp, f"ЭКОСИСТЕМА · {store} · СОТРУДНИКИ",
                          "  активных в магазине нет — очередь пуста, реестр спит",
                          footer="q — назад в ЭКО-навигатор")
            return
        rows = []
        for e in emps:
            nt, no = len(e["tasks"]), len(e["obs"])
            busy = " · ".join(filter(None, [
                f"задач {nt}" if nt else "", f"наблюдений {no}" if no else ""]))
            sub = f"занят: {D._snip((e['obs'][0] if e['obs'] else e['tasks'][0] if e['tasks'] else {}).get('what', ''), 46)}"
            rows.append(D._item(f"emp:{e['owner']}", f"{e['name']} ({e['owner']})",
                                sub=f"{busy} · {sub}" if busy else sub))
        rows.append(D._item("quit", "Назад к разделу СОТРУДНИКИ"))
        ch = D.pick(out, inp,
                    title=f"ЭКОСИСТЕМА · {store} · СОТРУДНИКИ",
                    sub="дневной пул по ролям: кто в работе и чем занят",
                    rows=rows,
                    prompt="цифра / Enter — роль · q — назад в навигатор")
        if ch is None or ch["action"] == "quit":
            return
        owner = ch["action"][4:]
        e = next((x for x in _employees(pl) if x["owner"] == owner), None)
        if e is None:
            continue
        body = "\n".join(_fit(out, ln) for ln in _emp_lines(out, e))
        body += (f"\n  контекст: магазин {store} · хеш {D._cycle_hash(store)}")
        D._show_pause(out, inp, f"ЭКОСИСТЕМА · {store} · СОТРУДНИКИ · {e['name']}",
                      body, footer="↑↓ — листать · q — назад к СОТРУДНИКАМ")


def run_eco_store(out, inp, store):
    """ЭКОСИСТЕМА магазина. tty: навигатор-провалы; не-tty: плоский лист + 'back'."""
    out = out or sys.stdout
    inp = inp or sys.stdin
    if not D._viable_tty(out, inp):
        out.write(eco_store_text(out, store) + "\n")
        return "back"
    info = D.store_payload(store).get("info") or {}
    h = D._cycle_hash(store)
    sub = (f"хеш {h} · биз {info.get('business_id') or '?'} · кампания "
           f"{info.get('campaign_id') or '?'} · склад {info.get('warehouse_id') or '?'}")
    while True:
        pl = D.store_payload(store)
        rows = _nav_rows(out, store, pl)
        ch = D.pick(out, inp,
                    title=f"ЭКОСИСТЕМА · {store}",
                    sub=D._snip(sub, 70),
                    rows=rows,
                    prompt="цифра / Enter — в раздел · ↑↓ — листать · q — назад в ДОМ")
        if ch is None or ch["action"] == "quit":
            return "back"
        if ch["action"].startswith("sec:"):
            _show_section(out, inp, store, ch["action"][4:])

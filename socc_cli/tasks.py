#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · ЗАДАНИЯ — реестр всей системы (socc_cli/tasks.py).

Оператор: «ЗАДАНИЯ — топливо для системы» + «строим CLI … сразу внутри моего кли
дома реализовано». Это ПЕРВОЕ-класс лицо ДОМА на уровне home: `socc задания` в
пайпе = плоская планёрка всех открытых; на живом терминале = меню-реестр (строки
по магазинам, нумерация глобальная, окно листает) → провал в строку = КАРТОЧКА
задания (пункты ●/○ + evidence, render_task органа). До этого реестр был виден
только внутри ЯМ (`socc ym задания` / экран магазина) — теперь это лицо ДОМА.

Данные — ОДНА правда: читаем СТОР реестра и сортируем/фильтруем/считаем функциями
органа ymarket_tasks_v1 (task_path/load/open_only/sort_tasks/stats/derive/
render_task) — ничего из логики не пере-реализуем. Модуль органа тянем ЛЕНИВО,
fail-soft: не импортировался/реестра нет/стор битый — честная строка (TX2), не
фейк-пусто. env YM_TASKS_PATH уважается органом → тесты герметичны (tmp), канон
не трогаем.

Закон разделения (как eco.py/pult.py): tasks — чистый read-слой поверх dom
(импортирует dom как D). Сам файлы НЕ пишет, движок НЕ запускает, сети нет,
шелла нет. dom.py зовёт tasks ЛЕНИВЫМ импортом в рантайме и остаётся DH8-чистым.
RUBICON цел (живые записи реестра — только form/seed/движок по слову оператора).

Законы TX (дом-приёмка socc_dom_tasks_acceptance_v1):
  TX1  лицо_плоское — tasks_text на StringIO: без ANSI (CC8), банд ЗАДАНИЯ · ДОМ,
       секции-магазины с «открыто N», строки с id · владельцем · пунктами X/Y
  TX2  честный_tri_state — модуль-нет / стора-нет / битый → строка, не фейк-пусто
  TX3  открыто_топливо — header: записей · закрыто % · в работе · ждут · срочных;
       закрытые в строки НЕ попадают (гейт derive органа), но в сводке честны
  TX4  важное_выше — порядок строк = sort_tasks органа (priority → срочность →
       created_at): P10 над P20, срочное над normal, ровно как планёрка цикла
  TX5  карточка_пункты — render_task: что [state·id] · пункты ●/○ с evidence у ●;
       длинное обрезано по ≤78 (ширина, закон ДОМА)
  TX6  строка_≤78 — весь плоский текст и карточки: каждая строка ≤78 (80×24
       ничего не клипается), id/хвост не теряются
  TX7  лицо_не_пишет — исходник tasks.py без записи/сети/исполнителя; dom.py без
       шелл-исполнителя (DH8 сохранён после врезки ЗАДАНИЯ)
  TX8  вход_в_доме — `socc задания` (cli._HOME_KEYS + home.dispatch), пункт
       ЗАДАНИЯ в home_rows (меню ДОМА) + ветка dispatch + home_text ВХОДЫ/HELP
"""
from __future__ import annotations

import sys

from socc_cli import dom as D

# Реестр-орган (scripts/mint/arbiter/ymarket_tasks_v1) — кэш ленивого импорта.
_T = None        # None-до импорта
_T_MISSING = object()
_T_ATTR = _T_MISSING


def _reg():
    """ymarket_tasks_v1 (fail-soft): не смогли импортировать → None (честная деградация)."""
    global _T_ATTR, _T
    if _T_ATTR is not _T_MISSING:
        return _T_ATTR
    _T_ATTR = None
    try:
        if str(D.ARB) not in sys.path:
            sys.path.insert(0, str(D.ARB))
        import ymarket_tasks_v1 as T  # noqa: E402
        _T_ATTR = T
    except Exception:
        _T_ATTR = None
    return _T_ATTR


# ── ширина (закон ДОМА: строка целиком ≤78, как eco._fit) ──────────────────────
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


# ── данные (одна правда: орган реестра) ─────────────────────────────────────────
def _data():
    """(status, msg, path, tasks, open_list, stats) для лица.

    status ∈ "ok" | "absent" (стор/орган ещё нет) | "error" (битый).
    msg — честная причина для absent/error. open_list = sort_tasks(open_only(все)).
    stats — орган-сводка по ВСЕМ записям (закрытые в ней честны, в строки не идут).
    """
    T = _reg()
    if T is None:
        return ("absent", "реестр-орган недоступен (ymarket_tasks_v1 не импортировался)",
                "", [], [], None)
    p = T.task_path()
    if not p.exists():
        return ("absent", "реестра ещё нет — первый form/seed (0₽) создаст",
                str(p), [], [], None)
    tasks, err = T.load(path=p)
    if err:
        return ("error", f"реестр битый: {err.get('load_error')}", str(p), [], [], None)
    return ("ok", "", str(p), list(tasks),
            T.sort_tasks(T.open_only(tasks)), T.stats(tasks))


def tasks_probe():
    """(открыто | None, подпись) — sub-строка пункта ЗАДАНИЯ в меню ДОМА."""
    status, msg, _p, _t, open_list, _st = _data()
    if status == "ok":
        return (len(open_list), "топливо ДОМА · 0₽ read")
    return (None, msg)


def _stats_line(out, st):
    """Сводка органа: записей · закрыто % · в работе · ждут · срочных открыто."""
    parts = [f"записей {st['total']}",
             f"закрыто {st['pct_done']}%" if st["pct_done"] is not None else "закрыто —",
             f"в работе {st['by_state']['in_progress']}",
             f"ждут {st['by_state']['waiting']}"]
    if st.get("critical_high_open"):
        parts.append(f"срочных открыто {st['critical_high_open']}")
    return " · ".join(parts)


def _groups(open_list):
    """Открытые → группы (market, store) в порядке встречи; внутри уже sort_tasks."""
    groups, order, by = [], [], {}
    for t in open_list:
        key = (str(t.get("market") or "—"), str(t.get("store") or ""))
        if key not in by:
            by[key] = []
            order.append(key)
        by[key].append(t)
    for key in order:
        mk, store = key
        groups.append((mk, store, by[key]))
    return groups


def _group_head(mk, store, n):
    if store:
        return f"МАГАЗИН · {mk} · {store} · открыто {n}"
    return f"МАРКЕТ {mk} · общесистемные · открыто {n}"


# ── плоский рендер (не-tty/пайп/--text и экран планёрки) ────────────────────────
def tasks_text(out, tasks=None):
    """Плоский лист ЗАДАНИЯ · весь реестр систем. tasks — опц. инъекция (герметика)."""
    out = out or sys.stdout
    L = [D._band(out, "ЗАДАНИЯ · ДОМ", right=D._clock(),
                 sub="весь реестр систем · топливо · read 0₽")]
    L.append("")
    if tasks is not None:
        status, msg = "ok", ""
        _T_reg = _reg()
        open_list = _groups(_T_reg.sort_tasks(_T_reg.open_only(tasks)))
        st = _T_reg.stats(tasks)
        path = "инъекция"
    else:
        status, msg, path, _all, open_list, st = _data()
        open_list = _groups(open_list)
    if status != "ok":
        L.append(D._seal(out, "РЕЕСТР"))
        L.append(f"  {status == 'absent' and '·' or '⚠'} {msg}")
        if path:
            L.append(D._col(out, "DIM", f"  стор: {path}"))
        L.append(D._col(out, "DIM", "  задания появятся, как только реестр сформируется"
                                     " (0₽) — ЦИКЛ-1/ЦИКЛ-ДЕНЬ их подхватывают"))
    else:
        L.append(D._seal(out, "ПЛАНЁРКА · ОТКРЫТЫЕ"))
        L.append("  " + _stats_line(out, st))
        if not open_list:
            L.append(D._col(out, "DIM", "  открытых нет — система чиста (все пункты ●)"))
        for mk, store, tasks_g in open_list:
            L.append(D._seal(out, _group_head(mk, store, len(tasks_g))))
            for t in tasks_g:
                L.append(D._task_row(out, t, with_id=True))
    L.append(D._col(out, "DIM",
                    "read 0₽ · движок не запускается · сортировка/фильтр — орган "
                    "ymarket_tasks_v1 (одна правда)"))
    flat = []
    for ln in L:
        flat.extend(str(ln).split("\n"))
    return "\n".join(_fit(out, ln) for ln in flat)


# ── карточка задания (дрилл, render_task органа) ────────────────────────────────
def _card(out, t):
    """Полная карточка одной задачи: пункты ●/○ + evidence (читабельно, ≤78)."""
    T = _reg()
    lines = []
    if T is not None and hasattr(T, "render_task"):
        lines = list(T.render_task(t))
    else:
        # фолбэк (орган жив, но render отсутствует — не должно): честная карточка
        st = str(t.get("state") or "open")
        lines = [f"{t.get('what')}  [{st} · {t.get('id')}]",
                 f"  магазин {t.get('store') or '—'} · категория {t.get('category')} · "
                 f"владелец {t.get('owner')} · {t.get('cycle')} · срочность {t.get('urgency')}"]
        for s in t.get("steps") or []:
            mark = "●" if s.get("state") == "done" else "○"
            lines.append(f"  {mark} {s.get('title')}")
    return "\n".join(_fit(out, ln) for ln in lines)


# ── интерактив (tty) ────────────────────────────────────────────────────────────
def _pick_rows(out, open_list):
    """Строки меню-реестра: сводка текстом · группы-магазины · задания (глоб. №).

    Метка КОРОТКАЯ (`○ what`, меню-кадр метки не режет), подробность — в sub: на
    выбранной строке 2-я строка низа показывает ПОЛНЫЙ ряд (владелец · пункты · id,
    как live:home/eco — дом-паттерн). Так хвост/id не теряются ни в меню, ни в дрилле.
    """
    rows = [_text_line("ЗАДАНИЯ — топливо: строки по важности (sort_tasks органа)."),
            _text_line("Провал в строку = карточка: пункты ●/○ + evidence (0₽ read)."),
            _text_line("")]
    for mk, store, tasks_g in _groups(open_list):
        rows.append(D._sep(_group_head(mk, store, len(tasks_g))))
        for t in tasks_g:
            icon = "◐" if t.get("state") == "in_progress" else "○"
            rows.append(D._item(f"task:{t.get('id')}",
                                f"{icon} {D._snip(t.get('what', ''), 58)}",
                                sub=D._task_row(out, t, with_id=True)))
    rows.append(D._sep(""))
    rows.append(D._item("quit", "Назад в ДОМ"))
    return rows


def _text_line(line):
    return D._text(line)


def run_tasks(out, inp):
    """ЗАДАНИЯ · лицо ДОМА. tty: меню-реестр → карточка; не-tty: плоский лист.

    Выход-код: run_tasks — корневое лицо dispatch (как run_home/run_ym): когда
    оператор выходит из корневого меню ЗАДАНИЯ (q / «Назад в ДОМ») возвращаем 0
    (dispatch _rc0 → чистый exit 0 на `socc задания`). Внутри run_home return
    игнорируется (врезка tasks:home → continue) — там 0 лишь «закончил лицо».
    """
    out = out or sys.stdout
    inp = inp or sys.stdin
    if not D._viable_tty(out, inp):
        out.write(tasks_text(out) + "\n")
        return 0
    while True:
        status, msg, _p, _all, open_list, st = _data()
        if status != "ok":
            title = "ЗАДАНИЯ · ДОМ"
            body = f"{'·' if status == 'absent' else '⚠'} {msg}"
            D._show_pause(out, inp, title, body,
                          footer="q — назад в ДОМ")
            return 0
        rows = _pick_rows(out, open_list)
        ch = D.pick(out, inp,
                    title="ЗАДАНИЯ · ДОМ",
                    sub=_stats_line(out, st),
                    rows=rows,
                    prompt="цифра / Enter — карточка · ↑↓ — листать · q — назад в ДОМ")
        if ch is None or ch["action"] == "quit":
            return 0
        if ch["action"].startswith("task:"):
            tid = ch["action"][5:]
            t = next((x for x in open_list if x.get("id") == tid), None)
            if t is None:
                continue
            D._show_pause(out, inp,
                          title=f"ЗАДАНИЕ · {tid}",
                          content=_card(out, t) + "\n\n  read 0₽ · движок не запускается · "
                                                 "статус по пунктам — гейт органа",
                          footer="↑↓ — листать · q — к реестру")
            continue


if __name__ == "__main__":
    import io
    sys.exit(run_tasks(io.StringIO(), io.StringIO()))

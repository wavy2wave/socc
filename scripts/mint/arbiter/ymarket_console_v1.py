#!/usr/bin/env python3
"""ymarket_console_v1.py — КОНСОЛЬ-ЯМ · read-кабинет SOCC-ЯМ (ШТАБ-дайв + ДЕЛО).

Pure-read орган: НИЧЕГО не пишет на диск, сеть не зовёт. Собирает текст из сторов:
табель/смены/тики (office), журнал суточного цикла (kpi), матрицу товаров, библиотеку,
торговые точки, хвост автопилота. Это «смотреть работу органа», не влиять на неё.

Функции чистые, с инъекцией строк (tabel_rows/journal_rows/charters/ev/doc=None) —
герметичные тесты не трогают диск (законы CC1–CC8 в tests/run_yandex_console.py).
Цвета SOCC, out-aware: ANSI только на живом tty, в StringIO/пайпе — plain (CC8).

One-shot CLI (по полной-команде-конвенции):
    python3 ymarket_console_v1.py --штаб
    python3 ymarket_console_v1.py --роль ТОВАРОВЕД
    python3 ymarket_console_v1.py --табель [--роль X] [--все]
    python3 ymarket_console_v1.py --день | --kpi | --артефакты | --задания | --план | --совет | --споры
          | --авто | --дело
    python3 ymarket_console_v1.py --доказано          — честная СВЕРКА-ЖИВЫХ (леждер ЦИКЛ-1)

ДЕНЬ/KPI на реальном пути дописывают блок СВЕРКА-ЖИВЫХ: «сверено 0» суточного журнала —
это само-модель СВОЕГО кабинета, а «доказанно живых» (леждер ЦИКЛ-1, СВЕРКА PASS) —
кабинетное число; панель не врёт «0 доказанно живых», когда леджер уже доказывает.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import sys
from pathlib import Path

# ── пути (канон органа: рядом с мозгом, сторы в MEMORY_WAVE/reports/mint/arbiter) ──
HERE = Path(__file__).resolve().parent
SOCC_ROOT = HERE.parents[2] if len(HERE.parents) > 2 else HERE.parents[-1]
if str(SOCC_ROOT) not in sys.path:
    sys.path.insert(0, str(SOCC_ROOT))
REPORTS = SOCC_ROOT / "MEMORY_WAVE/reports/mint/arbiter"

# ── переиспользуемые read-органы (fail-soft: упал — честный деградированный текст) ──
try:
    import ymarket_office_v1 as office      # роли/уставы/табель/совесть
except Exception:
    office = None
try:
    import ymarket_kpi_v1 as kpi            # журнал дня + свёртки DAY/WEEK/MONTH
except Exception:
    kpi = None
try:
    import ymarket_matrix_v1 as matrix      # матрица товаров (лесенка статусов)
except Exception:
    matrix = None
try:
    import ymarket_library_v1 as library    # библиотека артикулов
except Exception:
    library = None
try:
    import ymarket_points_v1 as points      # торговые точки
except Exception:
    points = None
try:
    import ymarket_tasks_v1 as tasks_reg    # реестр заданий ЯМ-ЦИКЛА (открыто/важность/владельцы)
except Exception:
    tasks_reg = None
try:
    import ymarket_proof_cross_v1 as cross  # честный блок «доказанно живых» (леждер ЦИКЛ-1)
except Exception:
    cross = None
try:
    import ymarket_plannerka_v1 as _plannerka  # durable ПЛАН ДНЯ (утро), read 0₽
except Exception:
    _plannerka = None
try:
    import ymarket_sovet_v1 as _sovet_mod      # СОВЕТ (лицо ПЛАНА ДНЯ), read 0₽
except Exception:
    _sovet_mod = None
try:
    import ymarket_sovet_spory_v1 as _spory_mod   # СПОРЫ ОРГАНОВ (слой 2 СОВЕТА), read 0₽
except Exception:
    _spory_mod = None

# ── цвета (SOCC-канон через socc_cli.style, out-aware) ────────────────────────
try:
    from socc_cli import style as S
except Exception:
    S = None

AUTOPILOT_LOG = Path(os.environ.get("YM_AUTOPILOT_LOG", REPORTS / "ymarket_autopilot.log"))

# ТАБЕЛЬ пишет роль дневным ключом MANAGER_TICK, офис знает MANAGER — сводим мост.
_TABEL_KEY = {"MANAGER": "MANAGER_TICK"}
_TABEL_REV = {"MANAGER_TICK": "MANAGER"}


def _tty(out):
    f = getattr(out, "isatty", None)
    if f is None:
        return False
    try:
        return bool(f())
    except Exception:
        return False


def _col(out, token, text):
    if not (S and _tty(out)):
        return text
    code = getattr(S, token, "")
    return f"{code}{text}{S.R}" if code else text


def _dim(out, text):
    return _col(out, "DIM", text)


def _b(out, text):
    return _col(out, "B", text)


def _gr(out, text):
    return _col(out, "GR", text)


def _ye(out, text):
    return _col(out, "YE", text)


def _re(out, text):
    return _col(out, "RE", text)


def _snip(text, n=90):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


# ── служебное: дата «сегодня», строки табели ──────────────────────────────────
def _iso_now(now):
    if now is None:
        return _dt.date.today().isoformat()
    if isinstance(now, str):
        return now[:10]
    return str(now.isoformat())[:10] if hasattr(now, "isoformat") else str(now)[:10]


def _tabel_rows(rows):
    if rows is None:
        try:
            return office.load_tabel() if office else []
        except Exception:
            return []
    return rows or []


def _tabel_key(rid):
    return _TABEL_KEY.get(rid, rid)


def _office_key(tabel_role):
    return _TABEL_REV.get(tabel_role, tabel_role)


# ── роли (реестр office, без чтения диска) ────────────────────────────────────
def roles_index():
    """13 ролей: {key,name_ru,emoji,cluster}. Статика реестра, fs не трогаем."""
    if not office:
        return []
    return [{"key": r["key"], "name_ru": r["name_ru"], "emoji": r["emoji"],
             "cluster": r["cluster"]} for r in office.ROLES]


def role_key(name):
    """key | русское имя (регистр/пробелы-не важно) → ключ роли. Не знаем → None."""
    if not office or not name:
        return None
    n = "".join(str(name).upper().split())
    for r in office.ROLES:
        if r["key"] == n:
            return r["key"]
        if "".join(r["name_ru"].split()) == n:
            return r["key"]
    for ru, key in office.NAME_TO_KEY:
        if ru and "".join(ru.split()) == n:
            return key
    return None


# ── job-строка роли («кто она») — первая строка docstring модуля, read, НЕ импорт ──
_JOB_CACHE = {}


def _module_doc_job(source):
    try:
        p = HERE / source
        if not p.exists():
            return None
        txt = p.read_text(encoding="utf-8")
        m = re.search(r'"""(.+?)"""', txt, re.S)
        if not m:
            m = re.search(r"'''(.+?)'''", txt, re.S)
        if not m:
            return None
        first = next((ln.strip() for ln in m.group(1).splitlines() if ln.strip()), None)
        if not first:
            return None
        if "—" in first:
            first = first.rsplit("—", 1)[1]
        return " ".join(first.split()).rstrip(".")
    except Exception:
        return None


def role_job(key):
    """Одна строка «кто она» (кэш). source=None (СБОРЩИК-призрак) → None."""
    if key in _JOB_CACHE:
        return _JOB_CACHE[key]
    job = None
    if office:
        r = office.ROSTER.get(key)
        if r and r.get("source"):
            job = _module_doc_job(r["source"])
    _JOB_CACHE[key] = job
    return job


def _roles(charters=None):
    """13 записей + устав (role_with_charter) + job-строка. charters инъекция — для тестов."""
    if not office:
        return []
    chs = office.load_charters() if charters is None else charters
    out = []
    for r in office.ROLES:
        rr = office.role_with_charter(r, chs)
        rr["job"] = role_job(r["key"])
        out.append(rr)
    return out


def _ev_for(ev_map, key):
    """Эвиденс роли, до-нормализованный нулями (частичная инъекция в тесте — не падаем)."""
    zero = {"has_channel": False, "channel_desc": None, "samples": 0, "last_real": None,
            "fresh": False, "ok_shifts": 0, "errors": 0, "escalations": 0}
    zero.update((ev_map or {}).get(key) or {})
    return zero


def evidence(charters=None):
    """(ev, summary) живых смен/тиков/журнала (office.gather_evidence). Только чтение."""
    if not office:
        return {}, {}
    chs = office.load_charters() if charters is None else charters
    try:
        return office.gather_evidence(chs)
    except Exception:
        return {}, {}


def _emp_col(out, emp):
    return {"В ШТАТЕ": _gr(out, emp), "СТАЖЁР": _ye(out, emp),
            "ЧИСЛИТСЯ": _dim(out, emp), "ВАКАНСИЯ": _re(out, emp)}.get(emp, emp)


def _status_col(out, st):
    return {"ok": _gr(out, "ok"), "skip": _dim(out, "skip"),
            "fail": _re(out, "fail"), "err": _re(out, "err")}.get(st, st)


# ── ШТАБ-дайв ─────────────────────────────────────────────────────────────────
def staff_summary(*, out=None, tabel_rows=None, now=None, charters=None, ev=None):
    """13 ролей одним листом: имя · кластер · занятость · совесть · сегодня ok/skip/fail/—."""
    out = out or sys.stdout
    today = _iso_now(now)
    if not office:
        return "ШТАБ недоступен: ymarket_office_v1 не импортировался (деградация честная)."
    ev_map = ev if ev is not None else office.gather_evidence(office.load_charters())[0]
    rows = _tabel_rows(tabel_rows)
    today_rows = {}
    for x in rows:
        if (x.get("date") or "").startswith(today):
            today_rows.setdefault(x.get("role"), x)
    lines = []
    counts = {}
    for r in _roles(charters):
        e = _ev_for(ev_map, r["key"])
        emp = office.employment(r, e)
        score, _ = office.conscience_score(r, e)
        counts[emp] = counts.get(emp, 0) + 1
        tk = _tabel_key(r["key"])
        tr = today_rows.get(tk)
        if tr:
            st = tr.get("status")
            today_txt = _status_col(out, st) if st in ("ok", "skip", "fail") else str(st or "—")
        else:
            today_txt = _dim(out, "—")
        line = "%s %s  %s · %s · совесть %s/5 · сегодня %s" % (
            r["emoji"], r["name_ru"].ljust(11), r["cluster"].ljust(8),
            _emp_col(out, emp), score, today_txt)
        lines.append("  " + line)
    head = "%s · %s ролей · %s" % (
        _b(out, "ШТАБ"), len(_roles(charters)),
        " · ".join("%s %d" % (k, v) for k, v in sorted(counts.items())))
    if not rows:
        head += " · " + _dim(out, "табели нет — день ещё не провели")
    return head + "\n" + "\n".join(lines)


def _charter_phrase(r):
    job = r.get("job")
    if job:
        return job
    ch = r.get("charter")
    if isinstance(ch, dict) and ch.get("mandate"):
        return str(ch["mandate"])
    return "вакансия — модуля и устава нет" if not r.get("source") else None


def role_card(key, *, out=None, tabel_rows=None, now=None, charters=None, ev=None):
    """Карточка роли: кто она, занятость, совесть, сегодня/всё время/последняя работа."""
    out = out or sys.stdout
    today = _iso_now(now)
    if not office:
        return "Роль недоступна: ymarket_office_v1 не импортировался (честная деградация)."
    rid = role_key(key)
    if rid is None:
        known = ", ".join(r["name_ru"] for r in office.ROLES)
        return "%s НЕ ЗНАЮ роль «%s». Знаю: %s." % (_re(out, "ШТАБ"), key, known)
    rr = next((x for x in _roles(charters) if x["key"] == rid), None)
    if rr is None:
        return "%s Роли %s нет в реестре." % (_re(out, "ШТАБ"), key)
    ev_map = ev if ev is not None else office.gather_evidence(office.load_charters())[0]
    e = _ev_for(ev_map, rid)
    emp = office.employment(rr, e)
    score, _ = office.conscience_score(rr, e)
    src = rr.get("source")
    mod = Path(src).name if src else None
    wired = rr.get("wired") or "none"
    phrase = _charter_phrase(rr)
    head = "%s · %s %s" % (_b(out, "РОЛЬ"), rr["name_ru"], rr["emoji"])
    info = "кластер %s · модуль %s · проводка %s" % (
        rr["cluster"], mod if mod else "—", wired)
    lines = [head, info]
    if phrase:
        lines.append("  «%s»" % phrase)
    lines.append("занятость: %s · совесть %s/5" % (_emp_col(out, emp), score))

    rows = _tabel_rows(tabel_rows)
    tk = _tabel_key(rid)
    role_rows = [x for x in rows if x.get("role") == tk]
    role_rows.sort(key=lambda x: (x.get("date") or "", x.get("ts") or ""))

    # сегодня
    tod = [x for x in role_rows if (x.get("date") or "").startswith(today)]
    if tod:
        seg = []
        for x in tod:
            st = x.get("status")
            seg.append("%s — %s" % (_status_col(out, st), _dim(out, _snip(x.get("evidence"))))
                       if x.get("evidence") else _status_col(out, st))
        lines.append("сегодня (%s): %s" % (today, " · ".join(seg)))
    elif not rows:
        lines.append("сегодня (%s): %s" % (today, _dim(out, "табели нет — суточный цикл ещё не провели")))
    else:
        lines.append("сегодня (%s): %s" % (today, _dim(out, "не звалась в цикл")))

    # за всё время
    if role_rows:
        days = sorted({x.get("date") for x in role_rows})
        st = {}
        for x in role_rows:
            s = x.get("status")
            st[s] = st.get(s, 0) + 1
        lines.append("за всё время: %d дн · ок %d · skip %d · fail %d · с %s" % (
            len(days), st.get("ok", 0), st.get("skip", 0), st.get("fail", 0), days[0]))
        last = role_rows[-1]
        ev_txt = _snip(last.get("evidence"))
        lines.append("последняя работа: %s · %s%s" % (
            last.get("date"), _status_col(out, last.get("status")),
            (" — " + ev_txt) if ev_txt else ""))
    else:
        lines.append("за всё время: %s" % _dim(out, "в табели нет — день за роль не записывался"))

    return "\n".join(lines)


def tabel_text(*, out=None, role=None, window="today", tabel_rows=None, now=None):
    """Строки ТАБЕЛИ. window: today (по умолчанию) | all. role: office-key/русское имя."""
    out = out or sys.stdout
    today = _iso_now(now)
    rows = _tabel_rows(tabel_rows)
    rid = role_key(role) if role else None
    tk = _tabel_key(rid) if rid else None
    sel = rows
    if window == "today":
        sel = [x for x in sel if (x.get("date") or "").startswith(today)]
    if tk:
        sel = [x for x in sel if x.get("role") == tk]
    sel = sorted(sel, key=lambda x: (x.get("date") or "", x.get("ts") or ""), reverse=True)
    if not sel:
        role_txt = (" · роль " + rid) if rid else ""
        if not rows:
            return "%s · %s%s — %s" % (_b(out, "ТАБЕЛЬ"), window, role_txt,
                                       _dim(out, "табели нет — суточный цикл ещё не провели"))
        return "%s · %s%s — %s" % (_b(out, "ТАБЕЛЬ"), window, role_txt,
                                   _dim(out, "ни одной записи за окно"))
    lines = []
    for x in sel:
        rname = x.get("role")
        ok = _office_key(rname)
        name_ru = office.ROSTER.get(ok, {}).get("name_ru") if office else rname
        st = x.get("status")
        ev_txt = _snip(x.get("evidence"))
        lines.append("  %s  %s  %s%s" % (
            (x.get("date") or "")[:10], name_ru.ljust(11), _status_col(out, st),
            (" — " + ev_txt) if ev_txt else ""))
    role_txt = (" · роль %s" % (rid or "")) if rid else ""
    head = "%s · %s%s · %d строк" % (_b(out, "ТАБЕЛЬ"), window, role_txt, len(sel))
    return head + "\n" + "\n".join(lines)


def tabel_today_text(*, out=None, tabel_rows=None, now=None):
    """Кто реально записался сегодня (сводно), кого сегодня в цикле не было."""
    out = out or sys.stdout
    today = _iso_now(now)
    rows = _tabel_rows(tabel_rows)
    tod = [x for x in rows if (x.get("date") or "").startswith(today)]
    if not tod:
        return "%s · %s — %s" % (_b(out, "ТАБЕЛЬ"), today,
                                 _dim(out, "никто не записан — суточный цикл ещё не провели"))
    present = []
    for x in tod:
        ok = _office_key(x.get("role"))
        name_ru = office.ROSTER.get(ok, {}).get("name_ru") if office else x.get("role")
        present.append("%s %s" % (name_ru, _status_col(out, x.get("status"))))
    head = "%s · %s · записались %d" % (_b(out, "ТАБЕЛЬ"), today, len(present))
    return head + "\n  " + " · ".join(present)


# ── ДЕЛО ──────────────────────────────────────────────────────────────────────
def live_cross_text(*, out=None, journal_rows=None, library_doc=None):
    """Честный блок «доказанно живых»: леджер ЦИКЛ-1 по кабинетам (только СВЕРКА PASS) +,
    когда суточный журнал рисует «0», разграничитель (это само-модель СВОЕГО кабинета,
    не леджер; числа не складываются). Реальный путь (None) читает диск; инъекция —
    герметично. Закон оператора «сделай чтобы система законно не врала»: панель не должна
    показывать «0 доказанно живых» как общесистемную правду, когда леджер уже доказывает."""
    out = out or sys.stdout
    if cross is None:
        return "%s · %s" % (_b(out, "СВЕРКА-ЖИВЫХ"),
                            _dim(out, "ymarket_proof_cross_v1 не импортировался"))
    try:
        txt = cross.render(journal_rows=journal_rows, library_doc=library_doc)
    except Exception as e:
        return "%s · %s" % (_b(out, "СВЕРКА-ЖИВЫХ"), _dim(out, "рендер упал: %s" % e))
    if not txt:
        return None
    head = "%s · %s" % (_b(out, "СВЕРКА-ЖИВЫХ"),
                        _dim(out, "леджер ЦИКЛ-1 (СВЕРКА PASS) vs суточный журнал"))
    return head + "\n" + "\n".join("  " + ln for ln in txt.splitlines())


def day_card(*, out=None, journal_rows=None):
    """Последний снимок дня из журнала суточного цикла: дата/горящее/топ-ход/kpi.
    На реальном пути (journal_rows is None) дописывает честный блок «доказанно живых»
    по леджеру ЦИКЛ-1 — «сверено 0» суточного больше не читается как общесистемная правда."""
    out = out or sys.stdout
    rows = journal_rows if journal_rows is not None else (
        kpi._read_rows() if kpi else [])
    if not rows:
        return "%s · %s" % (_b(out, "ДЕЛО · ДЕНЬ"),
                            _dim(out, "журнала нет — ни одного суточного цикла ещё не провели"))
    last = rows[-1] if isinstance(rows[-1], dict) else {}
    date = last.get("date") or (last.get("ts") or "")[:10]
    kp = last.get("kpis") or {}
    ru = {"cards_tracked": "в работе", "cards_live": "live",
          "cards_live_verified": "сверено", "cards_errored": "ошибок",
          "ready_to_publish": "готово к публикации", "avg_content_rating": "контент",
          "quality_index": "качество", "urgent_orders": "горящие заказы"}
    seg = []
    for f in kp:
        v = kp[f]
        if v is None:
            continue
        lab = ru.get(f, f)
        seg.append("%s %s" % (lab, v))
    lines = ["%s · день %s" % (_b(out, "ДЕЛО"), date)]
    if seg:
        lines.append("  " + " · ".join(seg[:8]))
    if last.get("burning"):
        lines.append("  горит: %s" % _dim(out, _snip(last.get("burning"), 120)))
    if last.get("top_move"):
        lines.append("  топ-ход: %s" % _dim(out, _snip(last.get("top_move"), 120)))
    if journal_rows is None:                      # реальный путь (CLI/ДОМ) → честная СВЕРКА-ЖИВЫХ
        xl = live_cross_text(out=out)
        if xl:
            lines.append(xl)
    return "\n".join(lines)


def kpi_text(*, out=None, journal_rows=None, today=None):
    """Свёртки KPI DAY/WEEK/MONTH (kpi.render_all, injectable rows). На реальном пути
    (journal_rows is None) дописывает честный блок «доказанно живых» по леджеру ЦИКЛ-1."""
    out = out or sys.stdout
    if not kpi:
        return "%s недоступен: ymarket_kpi_v1 не импортировался." % _b(out, "KPI")
    rows = journal_rows if journal_rows is not None else None
    try:
        txt = kpi.render_all(rows=rows, today=today)
    except Exception as e:
        return "%s · рендер упал: %s" % (_b(out, "KPI"), e)
    if journal_rows is None:                      # реальный путь (CLI/ДОМ) → честная СВЕРКА-ЖИВЫХ
        xl = live_cross_text(out=out)
        if xl:
            txt = txt.rstrip("\n") + "\n" + xl
    return txt


def artifacts_text(*, out=None, matrix_doc=None, library_doc=None, points_doc=None):
    """Артефакты: матрица (лесенка статусов) · библиотека артикулов · торговые точки."""
    out = out or sys.stdout
    lines = []
    # матрица товаров
    if matrix_doc is None:
        snap = {}
        if matrix:
            try:
                snap = matrix.snapshot()
            except Exception:
                snap = {}
    else:
        ladder = matrix._STATUS_LADDER if matrix else ()
        rows = (matrix_doc.get("rows") or {})
        snap = {"всего": len(rows)}
        for s in ladder:
            snap[s] = sum(1 for r in rows.values()
                          if isinstance(r, dict) and r.get("status") == s)
    mseg = []
    if snap.get("всего") is None:
        mseg.append("матрицы нет")
    else:
        mseg.append("всего %d" % snap.get("всего", 0))
        for s in ("кандидат", "собран", "залит", "сверен", "на-витрине", "продан"):
            if snap.get(s):
                mseg.append("%s %d" % (s, snap[s]))
    lines.append("%s · %s" % (_b(out, "АРТЕФАКТЫ · матрица"), " · ".join(mseg)))
    # библиотека
    st = None
    if library:
        try:
            doc = library.load() if library_doc is None else library_doc
            st = library.stats(doc)
        except Exception:
            st = None
    if st and st.get("articles"):
        cat_txt = " · ".join("%s %d" % (c, d.get("articles", 0))
                             for c, d in list(st.get("categories", {}).items())[:4]) or "—"
        lines.append("%s · артикулов %d · stock-событий %d · категории: %s" % (
            _b(out, "АРТЕФАКТЫ · библиотека"), st["articles"], st["stock_events"], cat_txt))
    else:
        lines.append("%s · %s" % (_b(out, "АРТЕФАКТЫ · библиотека"),
                                  _dim(out, "артикулов нет")))
    # торговые точки
    if points_doc is None and points:
        try:
            points_doc = points.load()
        except Exception:
            points_doc = None
    npts = len((points_doc or {}).get("points") or {}) if isinstance(points_doc, dict) else 0
    nbind = len((points_doc or {}).get("bindings") or {}) if isinstance(points_doc, dict) else 0
    if npts:
        lines.append("%s · точек %d · привязок %d" % (_b(out, "АРТЕФАКТЫ · точки"), npts, nbind))
    else:
        lines.append("%s · %s" % (_b(out, "АРТЕФАКТЫ · точки"),
                                  _dim(out, "точек нет")))
    return "\n".join(lines)


def autopilot_tail(*, out=None, path=None, n=14):
    """Хвост ymarket_autopilot.log (последние n строк) — только чтение."""
    out = out or sys.stdout
    p = Path(path) if path else AUTOPILOT_LOG
    try:
        if not p.exists():
            return "%s · %s" % (_b(out, "АВТОПИЛОТ"), _dim(out, "лога нет"))
        lines = [ln.rstrip("\n") for ln in p.read_text(encoding="utf-8").splitlines()]
        tail = lines[-n:]
        return "%s · %s\n%s" % (_b(out, "АВТОПИЛОТ"), _dim(out, "хвост %d" % len(tail)),
                                "\n".join("  " + ln for ln in tail))
    except Exception as e:
        return "%s · чтение упало: %s" % (_b(out, "АВТОПИЛОТ"), e)


def deal_text(*, out=None, tabel_rows=None, journal_rows=None, today=None, path=None):
    """ДЕЛО одним листом: кто сегодня · последний день · KPI-сводка · артефакты · задания · автопилот."""
    out = out or sys.stdout
    rows = tabel_rows if tabel_rows is not None else (_tabel_rows(None))
    jrows = journal_rows if journal_rows is not None else (kpi._read_rows() if kpi else [])
    blocks = [tabel_today_text(out=out, tabel_rows=rows, now=today),
              day_card(out=out, journal_rows=jrows),
              kpi_text(out=out, journal_rows=jrows if journal_rows is not None else None,
                       today=today),
              artifacts_text(out=out),
              tasks_text(out=out, now=today),
              plan_day_text(out=out, date_str=_iso_now(today)),
              sovet_text(out=out, date_str=_iso_now(today)),
              spory_text(out=out, date_str=_iso_now(today)),
              autopilot_tail(out=out, path=path, n=6)]
    return "\n".join(blocks)


# ── ЗАДАНИЯ (read-блок: реестр-пульс + открытые по важности) ───────────────────
def tasks_text(*, out=None, tasks=None, now=None):
    """Реестр ЗАДАНИЙ одним блоком: пульс (открыто/в работе/срочных) + открытые по важности.

    tasks инъекция — герметичный тест не трогает диск (CC-паттерн). Без инъекции читает
    реестр (tasks_reg.load, task_path/env). Чистый read: НИЧЕГО не пишет. Различает
    «реестра ещё нет» / «реестр битый» / «открыто N» (CD1-честность на чужом стору)."""
    out = out or sys.stdout
    today = _iso_now(now)
    if tasks_reg is None:
        return "%s · %s" % (_b(out, "ЗАДАНИЯ"),
                            _dim(out, "ymarket_tasks_v1 не импортировался (деградация честная)"))
    if tasks is None:
        status, serr = _registry_status()
        if status != "ok":
            lines = ["%s · %s" % (_b(out, "ЗАДАНИЯ"),
                                  _dim(out, serr if serr else "реестра ещё нет — первая form "
                                       "(--commit) сформирует из живых наблюдений"))]
            if tasks_reg and tasks_reg.task_path().exists():
                lines.append("  стор: %s" % _dim(out, tasks_reg.task_path()))
            return "\n".join(lines)
        tasks, _ = tasks_reg.load()
    tasks = tasks or []
    st = tasks_reg.stats(tasks)
    open_ = tasks_reg.open_only(tasks)
    done_n = st["by_state"]["done"]
    head = "%s · %s · записей %d · открыто %d" % (
        _b(out, "ЗАДАНИЯ"), today, len(tasks), len(open_))
    if st["critical_high_open"]:
        head += " · " + _re(out, "срочных %d" % st["critical_high_open"])
    if done_n:
        head += " · " + _dim(out, "закрыто %d" % done_n)
    lines = [head]
    if not open_:
        lines.append("  " + _dim(out, "открытых нет — все дела закрыты или реестр пуст."))
        return "\n".join(lines)
    for t in tasks_reg.sort_tasks(open_):
        stt = tasks_reg.derive(t)
        tag = "◐" if stt == "in_progress" else ("⏳" if stt == "waiting" else "○")
        urg = ("!" if t.get("urgency") in ("critical", "high") else " ")
        store = "[%s] " % t.get("store") if t.get("store") else ""
        lines.append("  %s P%s%s %s%s · %s · %s · %s" % (
            tag, str(t.get("priority", 50)).ljust(2), urg, _ye(out, store) if store else "",
            _snip(t.get("what"), 70), _gr(out, t.get("owner")), t.get("category"),
            _dim(out, t.get("id"))))
    return "\n".join(lines)


def _registry_status():
    """Состояние реестра: ('absent'|'ok'|'error', текст). «Реестра нет» ≠ «реестр битый»."""
    if tasks_reg is None:
        return "absent", "реестр недоступен (import)"
    try:
        exists = tasks_reg.task_path().exists()
    except Exception:
        exists = False
    if not exists:
        return "absent", None
    _, err = tasks_reg.load()
    if err:
        return "error", "реестр битый: %s" % (err.get("load_error") or err)
    return "ok", None


# ── ПЛАН ДНЯ (read-блок: durable планёрки (утро)) ─────────────────────────────
def _reconcile_esc_plan(plan, dossier_rows):
    """Снять со «ждёт слова» esc-map-{slug}, чьё досье УЖЕ подтверждено ОРГАНОМ (display-only).

    ПЛАН ДНЯ — утренний снимок (М3); досье за день законно уезжают: маппинг подтверждается
    КАТЕГОРИЙЩИКОМ (need_mapping→false + id дан; 04.09 живьём так ушло 8 из 12). Read-лица,
    читающие durable план, показывали бы устаревшее «нужно слово N» против досье в тот же миг.
    Зеркало _reconcile_waiting споров (тот же предикат): esc-map-{slug}, чьё досье уже
    подтверждено → слово оператора больше не нужно → из эскалаций убираем; всё ещё need_mapping
    / досье в списке нет → остаётся (ничего не выдумываем и не теряем). НЕ-esc-map эскалации
    не трогаем. Возвращает (kept, resolved_slugs, total_esc_map); план-док НЕ мутирует."""
    by_slug = {r.get("slug"): r for r in dossier_rows or [] if r.get("slug")}
    kept, resolved, total_esc = [], [], 0
    for x in plan.get("decisions", []):
        rid = x.get("id")
        if x.get("kind") == "escalation" and isinstance(rid, str) and rid.startswith("esc-map-"):
            total_esc += 1
            rec = by_slug.get(rid[len("esc-map-"):])
            if rec is not None and not rec.get("need_mapping") \
                    and rec.get("market_category_id") is not None:
                resolved.append(rid[len("esc-map-"):])   # маппинг подтверждён — слово не нужно
                continue
        kept.append(x)
    return kept, resolved, total_esc


def plan_day_text(*, out=None, plan=None, dossiers=None, date_str=None):
    """ПЛАН ДНЯ (утро) одним блоком: контекст дня + решения (планёрка, durable стор).

    plan/dossiers инъекция — герметичный тест не трогает диск (CC-паттерн). Без инъекции
    читает планёрку (load_plan по date_str/сегодня) И досье в тот же миг (read_dossiers):
    esc-map эскалации, чьё досье за день уже подтверждено органом, снимаются со «ждёт слова»
    (display-only реконсилят — план-файл/реестр/совет-заморозку НЕ трогаем; рендер сверяет с
    текущим досье, нота называет слоги). План инъекцией БЕЗ досье → рендер как есть (истины
    нет). Чистый read: НИЧЕГО не пишет. Различает «движок не импортировался» / «план битый»
    / «плана нет» (стиль _registry_status): «плана нет» ≠ «план пуст» — планёрка (утро)
    собирает durable ПЛАН ДНЯ ПРЕЖДЕ работ дня."""
    out = out or sys.stdout
    today = _iso_now(date_str)
    if _plannerka is None:
        return "%s · %s" % (_b(out, "ПЛАН ДНЯ"),
                            _dim(out, "ymarket_plannerka_v1 не импортировался (деградация честная)"))
    injected = plan is not None
    if plan is None:
        doc, lerr = _plannerka.load_plan(today)
        if lerr:
            return "%s · %s" % (_b(out, "ПЛАН ДНЯ"),
                                _dim(out, "план битый: %s" % (lerr.get("load_error") or lerr)))
        if doc is None:
            return "%s · %s" % (_b(out, "ПЛАН ДНЯ"),
                                _dim(out, "плана нет — планёрка (утро) ещё не собрала"))
        plan = doc
    render_doc, note = plan, ""
    if dossiers is not None or not injected:        # досье даны ИЛИ план пришёл с реального диска
        dr = dossiers
        if dr is None:
            try:
                dr = _plannerka.read_dossiers(None)[0]
            except Exception:
                dr = None
        if dr is not None:
            kept, resolved, total_esc = _reconcile_esc_plan(plan, dr)
            if resolved:
                render_doc = dict(plan)
                render_doc["decisions"] = kept
                note = ("план-файл числил esc-map %d; %d уже подтверждены КАТЕГОРИЙЩИКОМ по "
                        "досье — сняты со «ждёт слова»: %s"
                        % (total_esc, len(resolved), ", ".join(sorted(resolved))))
    lines = ["%s · %s" % (_b(out, "ПЛАН ДНЯ"), _dim(out, "%s · планёрка (утро)" % today))]
    for ln in _plannerka.render_plan(render_doc)[1:]:   # первую строку рендера не дублируем
        lines.append("  " + ln)
    if note:
        lines.append("  " + _dim(out, note))
    return "\n".join(lines)


# ── СОВЕТ ДИРЕКТОРОВ (read-блок: лицо ПЛАНА ДНЯ, 0₽, ничего не пишет) ──────────
def sovet_text(*, out=None, date_str=None):
    """СОВЕТ одним блоком: протокол даты (голоса из сторов + пропиздоны + зеркало решений плана).

    Чистый read: только load_protocol/render_sovet из ymarket_sovet_v1 (0₽, VL4-гейт). По
    отсутствию файла даты честно «совет не собирался» (VL5), а не пустой лист. СОВЕТ сам новых
    заданий не создаёт (VL7) — лицо поэтому строго read-only и ничего не пишет на диск."""
    out = out or sys.stdout
    today = _iso_now(date_str)
    if _sovet_mod is None:
        return "%s · %s" % (_b(out, "СОВЕТ"),
                            _dim(out, "ymarket_sovet_v1 не импортировался (деградация честная)"))
    proto, lerr = _sovet_mod.load_protocol(today)
    if lerr:
        return "%s · %s" % (_b(out, "СОВЕТ"),
                            _dim(out, "протокол битый: %s" % (lerr.get("load_error") or lerr)))
    lines = _sovet_mod.render_sovet(proto, today)
    return "\n".join(lines)


# ── СПОРЫ ОРГАНОВ (read-блок: слой 2 СОВЕТА «Голоса-споры», 0₽, ничего не пишет) ─
def spory_text(*, out=None, date_str=None):
    """ПРЕНИЯ органов одним блоком: позиции + споры по данным даты.

    Чистый read: снимок даты (VL6, с живой озвучкой если была) уже сохранён → рендерит его;
    иначе собирает детерминированный doc в памяти (compose_spory gate="off": 0 LLM, 0₽, без сети)
    и рендерит. Лицо строго ничего не пишет (VL10); по отсутствию повода честно «прений не было»
    (VL5), а не пустой лист. Движок не импортировался → честно (стиль CC9/CC10/CC11)."""
    out = out or sys.stdout
    today = _iso_now(date_str)
    if _spory_mod is None:
        return "%s · %s" % (_b(out, "СПОРЫ"),
                            _dim(out, "ymarket_sovet_spory_v1 не импортировался (деградация честная)"))
    doc, lerr = _spory_mod.load_spory(today)
    if lerr:
        return "%s · %s" % (_b(out, "СПОРЫ"),
                            _dim(out, "стор споров битый: %s" % (lerr.get("load_error") or lerr)))
    if doc is None:
        # снимка даты нет (автопилот споры по умолчанию не пишет) — производная сейчас, 0₽
        try:
            doc = _spory_mod.compose_spory(date_str=today, gate="off")
        except Exception as e:
            return "%s · %s" % (_b(out, "СПОРЫ"),
                                _dim(out, "сбор споров упал: %s" % e))
    if not (doc.get("positions") or doc.get("disputes")):
        # собрано, но противопоставить нечего — честное «прений не было» (VL5), как resolve-слой
        lines = _spory_mod.render_spory(None, today)
    else:
        lines = _spory_mod.render_spory(doc, today)
    return "\n".join(lines)


# ── One-shot CLI (чистая печать, ничего не пишет) ─────────────────────────────
def _usage():
    return (
        "КОНСОЛЬ-ЯМ · read-кабинет SOCC-ЯМ (0₽, ничего не пишет)\n"
        "  python3 ymarket_console_v1.py --штаб               — 13 ролей одним листом\n"
        "  python3 ymarket_console_v1.py --роль ТОВАРОВЕД     — карточка роли (key или имя)\n"
        "  python3 ymarket_console_v1.py --табель [--роль X] [--все]  — табель (сегодня/всё)\n"
        "  python3 ymarket_console_v1.py --день               — последний снимок дня\n"
        "  python3 ymarket_console_v1.py --kpi                — свёртки DAY/WEEK/MONTH\n"
        "  python3 ymarket_console_v1.py --доказано            — честная СВЕРКА-ЖИВЫХ: леджер ЦИКЛ-1\n"
        "        по кабинетам (СВЕРКА PASS) + журнал суточного (само-модель своего кабинета)\n"
        "  python3 ymarket_console_v1.py --артефакты          — матрица · библиотека · точки\n"
        "  python3 ymarket_console_v1.py --задания             — реестр ЗАДАНИЙ (открытые по важности)\n"
        "  python3 ymarket_console_v1.py --план                — ПЛАН ДНЯ (durable планёрки, утро)\n"
        "  python3 ymarket_console_v1.py --совет               — СОВЕТ ДИРЕКТОРОВ (протокол даты)\n"
        "  python3 ymarket_console_v1.py --споры               — СПОРЫ ОРГАНОВ (позиции + прения)\n"
        "  python3 ymarket_console_v1.py --авто               — хвост автопилота\n"
        "  python3 ymarket_console_v1.py --дело               — всё ДЕЛО одним листом")


def _main(argv=None):
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    out = sys.stdout
    if not argv or argv[0] in ("-h", "--help", "help", "--справка"):
        print(_usage())
        return 0
    i = 0
    role = None
    window = "today"
    cmd = None
    while i < len(argv):
        a = argv[i]
        if a in ("--штаб", "--shtab"):
            cmd = cmd or "staff"
        elif a in ("--табель", "--tabel"):
            cmd = cmd or "tabel"
        elif a in ("--день", "--den", "--day"):
            cmd = cmd or "day"
        elif a in ("--kpi", "--kpis"):
            cmd = cmd or "kpi"
        elif a in ("--артефакты", "--artefakty", "--artifacts"):
            cmd = cmd or "artifacts"
        elif a in ("--задания", "--zadaniya", "--tasks"):
            cmd = cmd or "tasks"
        elif a in ("--план", "--plannerka", "--plan"):
            cmd = cmd or "plan"
        elif a in ("--совет", "--sovet", "--sovet_direktorov"):
            cmd = cmd or "sovet"
        elif a in ("--споры", "--spory", "--preniya", "--prenia"):
            cmd = cmd or "spory"
        elif a in ("--авто", "--avto", "--autopilot"):
            cmd = cmd or "autopilot"
        elif a in ("--доказано", "--cross", "--zhivykh"):
            cmd = cmd or "cross"
        elif a in ("--дело", "--delo", "--deal"):
            cmd = cmd or "deal"
        elif a in ("--роль", "--rol", "--role"):
            cmd = cmd or "role"
            if i + 1 < len(argv):
                role = argv[i + 1]
                i += 1
        elif a == "--все":
            window = "all"
        i += 1
    if cmd is None:
        print(_usage())
        return 1
    if cmd == "staff":
        print(staff_summary(out=out))
    elif cmd == "role":
        print(role_card(role or "", out=out))
    elif cmd == "tabel":
        print(tabel_text(out=out, role=role, window=window))
    elif cmd == "day":
        print(day_card(out=out))
    elif cmd == "kpi":
        print(kpi_text(out=out))
    elif cmd == "artifacts":
        print(artifacts_text(out=out))
    elif cmd == "tasks":
        print(tasks_text(out=out))
    elif cmd == "plan":
        print(plan_day_text(out=out))
    elif cmd == "sovet":
        print(sovet_text(out=out))
    elif cmd == "spory":
        print(spory_text(out=out))
    elif cmd == "autopilot":
        print(autopilot_tail(out=out))
    elif cmd == "deal":
        print(deal_text(out=out))
    elif cmd == "cross":
        print(live_cross_text(out=out))
    return 0


if __name__ == "__main__":
    sys.exit(_main())

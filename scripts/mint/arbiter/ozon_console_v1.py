#!/usr/bin/env python3
"""ozon_console_v1.py — КОНСОЛЬ-ОЗОН · read-кабинет линии ОЗОН (ШТАБ-дайв + ДЕЛО).

Pure-read орган: НИЧЕГО не пишет на диск, сеть не зовёт. Собирает текст из сторов:
память карточек (state), последний ход УПРАВЛЯЮЩЕГО (tick-report), 6 ОТДЕЛОВ (assess_all —
цепь/grounded/прогноз на текущем срезе памяти, 0₽), журнал суточного дня (ozon_day_journal),
общий реестр ЗАДАНИЙ (маркет ozon), слепок ДОЗНАНИЯ (ozon_truth_*.json), хвост автопилота.
Это «смотреть работу органа», не влиять на неё.

Функции чистые, с инъекцией строк (doc/ass/journal_rows/tasks/snapshot/path=None) — герметичные
тесты не трогают диск (законы CC1–CC8). Цвета SOCC, out-aware: ANSI только на живом tty,
в StringIO/пайпе — plain.

One-shot CLI (по полной-команде-конвенции):
    python3 ozon_console_v1.py --штаб                — ШТАБ: УПРАВЛЯЮЩИЙ + KPI + ОТДЕЛЫ(6)
    python3 ozon_console_v1.py --день                — последний снимок дня (журнал)
    python3 ozon_console_v1.py --kpi                 — карточка KPI (память сейчас) + дельта ко вчера
    python3 ozon_console_v1.py --отделы [--роль X]   — ОТДЕЛЫ(6); --роль X — карточка одного отдела
    python3 ozon_console_v1.py --задания             — реестр ЗАДАНИЙ маркета ozon (открытые по важности)
    python3 ozon_console_v1.py --дознание            — последний слепок фактов кабинета (0₽ READ)
    python3 ozon_console_v1.py --авто                — хвост ozon_autopilot.log
    python3 ozon_console_v1.py --дело                — всё ДЕЛО одним листом

Законы (зеркало CC1–CC8): чистое чтение без побочных эффектов (CC1); инъекция вместо диска (CC2);
fail-soft деградация текстом, не падением (CC3); «нет стора» честно ≠ 0 (CC4); отдел упал — его
строка с ошибкой, остальные живут (CC5); ANSI только на живом tty (CC8).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

# ── пути (канон органа: сторы в MEMORY_WAVE/reports/mint/arbiter) ──
HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    import ozon_day_v1 as day            # журнал дней + REPORTS (только чтение)
except Exception:
    day = None
try:
    import ozon_state_v1 as state        # память карточек (только чтение)
except Exception:
    state = None
try:
    import ozon_manager_v1 as manager    # последний ход УПРАВЛЯЮЩЕГО (tick-report, только чтение)
except Exception:
    manager = None
try:
    import ozon_self_v1 as self_mod      # само-модель + следующий законный шаг
except Exception:
    self_mod = None
try:
    import ozon_departments_v1 as depts  # 6 отделов: assess_all + render (0₽, сети нет)
except Exception:
    depts = None
try:
    import ymarket_tasks_v1 as tasks_reg # ОБЩИЙ реестр заданий ЯМ+ОЗОН (маркет ozon фильтруем)
except Exception:
    tasks_reg = None

REPORTS = (day.REPORTS if day is not None else HERE.parent.parent.parent
           / "MEMORY_WAVE/reports/mint/arbiter")

# ── цвета (SOCC-канон через socc_cli.style, out-aware) ────────────────────────
try:
    from socc_cli import style as S
except Exception:
    S = None

AUTOPILOT_LOG = Path(os.environ.get("OZON_AUTOPILOT_LOG", REPORTS / "ozon_autopilot.log"))


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


def _iso_now(now):
    if now is None:
        now = _dt.date.today()
    return now.strftime("%Y-%m-%d") if hasattr(now, "strftime") else str(now)


# ── чтение сторов (только READ; env-перекрытия дают герметичность) ────────────

def _read_last_day(rows=None):
    """Последняя строка журнала дня (инъекция rows перекрывает диск). None — журнала нет."""
    if rows is not None:
        return rows[-1] if rows else None
    if day is None:
        return None
    p = day.journal_path()
    if not p.exists():
        return None
    last = None
    try:
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                last = json.loads(ln)
            except json.JSONDecodeError:
                continue
    except OSError:
        return None
    return last


def _read_doc(doc=None):
    """Док памяти (инъекция doc перекрывает диск). Всегда валидный словарь."""
    if doc is not None:
        return doc
    if state is None:
        return {}
    try:
        return state.load()
    except Exception:
        return {}


def _read_assessment(doc=None, ass=None):
    """Срез ОТДЕЛОВ (инъекция ass перекрывает живой assess_all на доке памяти)."""
    if ass is not None:
        return ass
    if depts is None:
        return None
    try:
        return depts.assess_all(doc=_read_doc(doc))
    except Exception:
        return None


def _read_tick(tick_doc=None):
    """Последний tick-report УПРАВЛЯЮЩЕГО (инъекция tick_doc перекрывает диск). None — нет."""
    if tick_doc is not None:
        return tick_doc
    if manager is None:
        return None
    try:
        p = manager.TICK_REPORT
        if not Path(p).exists():
            return None
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_truth_snapshot():
    """Последний слепок ДОЗНАНИЯ ozon_truth_*.json (макс mtime). None — слепка нет."""
    try:
        snaps = sorted(REPORTS.glob("ozon_truth_*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    if not snaps:
        return None
    try:
        return json.loads(snaps[0].read_text(encoding="utf-8"))
    except Exception:
        return None


# ── ШТАБ: УПРАВЛЯЮЩИЙ + KPI + ОТДЕЛЫ(6) ───────────────────────────────────────

def cabinet_summary(*, out=None, doc=None, ass=None, tick_doc=None):
    """ШТАБ одним листом: последний ход УПРАВЛЯЮЩЕГО → само-модель/след.шаг → KPI+норма → ОТДЕЛЫ(6)."""
    out = out or sys.stdout
    doc = _read_doc(doc)
    lines = [_b(out, "ШТАБ-ОЗОН") + " · " + _dim(out, "read-кабинет линии (0₽, ничего не пишет)")]
    # УПРАВЛЯЮЩИЙ (последний тик)
    tk = _read_tick(tick_doc)
    if tk:
        lines.append("%s · %s · тик %s" % (_b(out, "УПРАВЛЯЮЩИЙ"),
                                           _gr(out, str(tk.get("action"))),
                                           _dim(out, tk.get("tick_id") or (tk.get("ts") or "")[:19])))
    else:
        lines.append("%s · %s" % (_b(out, "УПРАВЛЯЮЩИЙ"), _dim(out, "тиков ещё не было")))
    # само-модель: следующий законный шаг
    nxt = None
    if self_mod is not None:
        try:
            nxt = (self_mod.self_status(doc) or {}).get("next_lawful_step")
        except Exception:
            nxt = None
    if nxt:
        lines.append("  растём: %s" % _dim(out, _snip(nxt, 130)))
    lines.append(kpi_text(out=out, doc=doc))
    lines.append(dept_text(out=out, doc=doc, ass=ass))
    return "\n".join(l for l in lines if l)


def kpi_text(*, out=None, doc=None, yesterday_kpis=None):
    """Карточка KPI: память СЕЙЧАС + норма дня + дельта ко вчера (последний журнал, если менялась)."""
    out = out or sys.stdout
    doc = _read_doc(doc)
    if state is None:
        return "%s · %s" % (_b(out, "KPI"), _dim(out, "озон_state_v1 не импортировался"))
    k = {}
    try:
        raw = state.kpis(doc)
        k = {"tracked": raw.get("tracked"), "cards_on_shelf": raw.get("cards_on_shelf"),
             "cards_errored": raw.get("cards_errored"), "need_mapping": raw.get("need_mapping"),
             "ready_to_publish": raw.get("ready_to_publish"), "index_red": raw.get("index_red")}
        dly = state.daily_norm(doc)
        for kk, v in dly.items():
            k[f"daily_{kk}"] = v
    except Exception as e:
        return "%s · рендер упал: %s" % (_b(out, "KPI"), e)
    ru = {"tracked": "ведём", "cards_on_shelf": "витрина", "cards_errored": "ошибки",
          "need_mapping": "ждут-category", "ready_to_publish": "готовы", "index_red": "красных",
          "daily_uploaded": "залито", "daily_shipped": "отгружено",
          "daily_delivered": "доставлено", "daily_fixed": "починено"}
    seg = []
    for f in ("tracked", "cards_on_shelf", "cards_errored", "need_mapping", "ready_to_publish",
              "index_red", "daily_uploaded", "daily_shipped", "daily_delivered", "daily_fixed"):
        v = k.get(f)
        if v is None:
            continue
        if f == "cards_errored":
            seg.append(_re(out, "%s %s" % (ru.get(f, f), v)))
        else:
            seg.append("%s %s" % (ru.get(f, f), v))
    lines = ["%s · %s" % (_b(out, "KPI"), " · ".join(seg))]
    # дельта ко вчера: если в последнем журнале kpis есть и числа менялись — показать разницу
    if yesterday_kpis is None:
        last = _read_last_day()
        yesterday_kpis = (last or {}).get("kpis") if last else None
    if isinstance(yesterday_kpis, dict):
        dif = []
        for kk, v in k.items():
            if not isinstance(v, (int, float)):
                continue
            yv = yesterday_kpis.get(kk)
            if isinstance(yv, (int, float)) and yv != v:
                dif.append("%s %s→%s(%+d)" % (ru.get(kk, kk), yv, v, v - yv))
        if dif:
            lines.append("  " + _dim(out, "дельта ко вчера: " + " · ".join(dif)))
    return "\n".join(lines)


# ── ОТДЕЛЫ (6): render или карточка одного отдела ──────────────────────────────

def dept_text(*, out=None, doc=None, ass=None, role=None):
    """ОТДЕЛЫ(6): сводная строка grounded/прогнозов + человеческий render. --роль X — карточка отдела."""
    out = out or sys.stdout
    a = _read_assessment(doc, ass)
    if a is None:
        return "%s · %s" % (_b(out, "ОТДЕЛЫ"), _dim(out, "озон_departments_v1 не импортировался"))
    rows = a.get("departments") or []
    if role:
        key = (role or "").strip().upper()
        hit = None
        for r in rows:
            if key == (r.get("dept") or "").upper() or key in (r.get("name_ru") or "").upper() \
                    or key in (r.get("emoji") or ""):
                hit = r
                break
        if not hit:
            return "%s · %s" % (_b(out, "ОТДЕЛЫ"), _dim(out,
                                                      f"роли «{role}» не нашёл (ключи: "
                                                      + ", ".join("%s/%s" % (r.get("dept"), r.get("name_ru"))
                                                                  for r in rows or [])))
        g = _ground_col(out, hit.get("grounded"))
        lines = ["%s · %s %s · заземлено %s · прогнозов %d" % (
            _b(out, "ОТДЕЛ"), hit.get("emoji"), _ye(out, hit.get("name_ru")), g,
            len(hit.get("predictions") or []))]
        lines.append("  " + (hit.get("human") or (hit.get("error") or "—")))
        return "\n".join(lines)
    g = a.get("groundedness") or {}
    head = "%s · %s · заземлено %d/%d (%s) · прогнозов %d · live=%s" % (
        _b(out, "ОТДЕЛЫ"), _dim(out, a.get("ts", "")[:19]),
        g.get("grounded", 0), g.get("checked", 0), _pct(g.get("grounded_pct")),
        len(a.get("predictions") or []), a.get("live"))
    txt = head
    try:
        human = depts.render(a)
        txt += "\n" + "\n".join("  " + ln for ln in human.splitlines()[1:])
    except Exception as e:
        txt += "\n  " + _dim(out, "рендер отделов упал: %s" % e)
    return txt


def _ground_col(out, g):
    if g is True:
        return _gr(out, "ДА")
    if g is False:
        return _re(out, "НЕТ")
    return _dim(out, "н/п")


def _pct(v):
    if v is None:
        return "н/п"
    return "%g%%" % v


# ── ДЕНЬ (последний снимок журнала) ────────────────────────────────────────────

def day_card(*, out=None, journal_rows=None):
    """Последний снимок дня из журнала: дата/ок/действие/горящее/KPI + дельта-сводка."""
    out = out or sys.stdout
    last = _read_last_day(journal_rows)
    if not last:
        return "%s · %s" % (_b(out, "ДЕНЬ"), _dim(out, "журнала дня нет — ни одного дня ещё не провели "
                                                     "(первый: ozon_day_v1 --dry)"))
    date = last.get("date") or (last.get("ts") or "")[:10]
    kp = last.get("kpis") or {}
    ru = {"cards_tracked": "ведём", "cards_on_shelf": "витрина", "cards_errored": "ошибки",
          "need_mapping": "ждут-category", "ready_to_publish": "готовы", "index_red": "красных"}
    seg = []
    for f, lab in ru.items():
        v = kp.get(f)
        if v is None:
            continue
        seg.append("%s %s" % (lab, v))
    ok = last.get("ok")
    ok_txt = _gr(out, "ok") if ok else _re(out, "ok=False")
    lines = ["%s · день %s · %s" % (_b(out, "ДЕНЬ"), date, ok_txt)]
    if last.get("action"):
        lines.append("  упр: %s" % _dim(out, str(last.get("action"))))
    if seg:
        lines.append("  " + " · ".join(seg))
    if last.get("burning") is not None:
        lines.append("  горит: %s" % _dim(out, "%d" % last.get("burning")))
    if last.get("failures"):
        lines.append("  провалов: %s" % _re(out, "%d" % last.get("failures")))
    if last.get("compared_to"):
        lines.append("  сравнивали со вчера: %s" % _dim(out, last.get("compared_to")))
    if last.get("truth"):
        t = last.get("truth") or {}
        if t.get("ok"):
            lines.append("  дознание: %s продаж за %sd · нетто %s₽" % (
                t.get("sales_count"), t.get("days"), t.get("total_net")))
        elif t.get("error"):
            lines.append("  дознание: %s" % _dim(out, "ошибка: " + str(t["error"])[:60]))
    return "\n".join(lines)


# ── ЗАДАНИЯ (реестр, маркет ozon) ──────────────────────────────────────────────

def _registry_status():
    """Состояние общего реестра: ('absent'|'ok'|'error', текст). «Нет реестра» ≠ «битый»."""
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


def tasks_text(*, out=None, tasks=None, now=None):
    """Реестр ЗАДАНИЙ маркета ozon: пульс (открыто/срочных) + открытые по важности.

    tasks инъекция — герметичный тест не трогает диск. Чистый read. Различает «реестра ещё нет» /
    «битый» / «0 открытых» (честность на чужом стору)."""
    out = out or sys.stdout
    today = _iso_now(now)
    if tasks_reg is None:
        return "%s · %s" % (_b(out, "ЗАДАНИЯ"), _dim(out, "ymarket_tasks_v1 не импортировался"))
    if tasks is None:
        status, serr = _registry_status()
        if status != "ok":
            lines = ["%s · %s" % (_b(out, "ЗАДАНИЯ ОЗОН"),
                                  _dim(out, serr if serr else "реестра ещё нет — первая form "
                                       "(--commit) сформирует из живых наблюдений"))]
            if tasks_reg and tasks_reg.task_path().exists():
                lines.append("  стор: %s" % _dim(out, tasks_reg.task_path()))
            return "\n".join(lines)
        tasks, _ = tasks_reg.load()
    oz = tasks_reg.by_market(tasks or [], "ozon")
    st = tasks_reg.stats(oz)
    open_ = tasks_reg.open_only(oz)
    head = "%s · %s · записей ОЗОН %d · открыто %d" % (_b(out, "ЗАДАНИЯ ОЗОН"), today, len(oz), len(open_))
    if st["critical_high_open"]:
        head += " · " + _re(out, "срочных %d" % st["critical_high_open"])
    if st["by_state"]["done"]:
        head += " · " + _dim(out, "закрыто %d" % st["by_state"]["done"])
    lines = [head]
    if not open_:
        lines.append("  " + _dim(out, "открытых нет — все дела закрыты или реестр по ОЗОН пуст."))
        return "\n".join(lines)
    for t in tasks_reg.sort_tasks(open_):
        stt = tasks_reg.derive(t)
        tag = "◐" if stt == "in_progress" else ("⏳" if stt == "waiting" else "○")
        urg = ("!" if t.get("urgency") in ("critical", "high") else " ")
        lines.append("  %s P%s%s %s · %s · %s · %s" % (
            tag, str(t.get("priority", 50)).ljust(2), urg,
            _snip(t.get("what"), 70), _gr(out, t.get("owner")), t.get("category"),
            _dim(out, t.get("id"))))
    return "\n".join(lines)


# ── ДОЗНАНИЕ (последний слепок фактов кабинета) ────────────────────────────────

def truth_text(*, out=None, snapshot=None):
    """Последний слепок ДОЗНАНИЯ (0₽ READ): факт продаж/нетто/доставки из кабинета. None — слепка нет."""
    out = out or sys.stdout
    snap = snapshot if snapshot is not None else _read_truth_snapshot()
    if not snap:
        return "%s · %s" % (_b(out, "ДОЗНАНИЕ"), _dim(out, "слепка ещё нет — первый живой READ "
                                                          "(ozon_truth / день --live-read)"))
    if snap.get("error"):
        return "%s · %s" % (_b(out, "ДОЗНАНИЕ"), _re(out, "ошибка: " + str(snap["error"])))
    lines = ["%s · %s" % (_b(out, "ДОЗНАНИЕ"), _dim(out, "факт кабинета, 0₽ READ"))]
    for ln in _truth_facts(snap):
        lines.append("  " + ln)
    return "\n".join(lines)


def _truth_facts(s):
    """Человечные факты слепка (допускает и analyze_cabinet, и записанный слепок дня)."""
    out = []
    if s.get("sales_count") is not None:
        out.append(f"продаж {s['sales_count']} за {s.get('days') or '?'}д")
    if s.get("total_revenue") is not None:
        out.append(f"выручка {s['total_revenue']}₽")
    if s.get("total_net") is not None:
        out.append(f"чистыми {s['total_net']}₽")
    if s.get("net_coeff") is not None:
        out.append(f"нетто-коэфф {s['net_coeff']}")
    if s.get("commission_pct") is not None:
        out.append(f"комиссия {s['commission_pct']}%")
    if s.get("delivery_net") is not None:
        out.append(f"доставка-нетто {s['delivery_net']}₽")
    if s.get("per_sale_avg") is not None:
        out.append(f"средний чек {s['per_sale_avg']}₽")
    if not out:
        out.append(str(s)[:120])
    return out


# ── АВТО (хвост лога) ───────────────────────────────────────────────────────────

def autopilot_tail(*, out=None, path=None, n=14):
    """Хвост ozon_autopilot.log (последние n строк) — только чтение."""
    out = out or sys.stdout
    p = Path(path) if path else AUTOPILOT_LOG
    try:
        if not p.exists():
            return "%s · %s" % (_b(out, "АВТОПИЛОТ ОЗОН"), _dim(out, "лога нет"))
        lines = [ln.rstrip("\n") for ln in p.read_text(encoding="utf-8").splitlines()]
        tail = lines[-n:]
        return "%s · %s\n%s" % (_b(out, "АВТОПИЛОТ ОЗОН"), _dim(out, "хвост %d" % len(tail)),
                                "\n".join("  " + ln for ln in tail))
    except Exception as e:
        return "%s · чтение упало: %s" % (_b(out, "АВТОПИЛОТ ОЗОН"), e)


# ── ДЕЛО (всё одним листом) ─────────────────────────────────────────────────────

def deal_text(*, out=None):
    """ДЕЛО одним листом: ШТАБ · ДЕНЬ · KPI · ОТДЕЛЫ · ЗАДАНИЯ · ДОЗНАНИЕ · АВТО."""
    out = out or sys.stdout
    blocks = [cabinet_summary(out=out),
              day_card(out=out),
              dept_text(out=out),
              tasks_text(out=out),
              truth_text(out=out),
              autopilot_tail(out=out, n=6)]
    return "\n".join(blocks)


# ── CLI ─────────────────────────────────────────────────────────────────────────

def _usage():
    return (
        "КОНСОЛЬ-ОЗОН · read-кабинет линии ОЗОН (0₽, ничего не пишет)\n"
        "  python3 ozon_console_v1.py --штаб               — ШТАБ: УПРАВЛЯЮЩИЙ + KPI + ОТДЕЛЫ(6)\n"
        "  python3 ozon_console_v1.py --день               — последний снимок дня (журнал)\n"
        "  python3 ozon_console_v1.py --kpi                — карточка KPI (память) + дельта ко вчера\n"
        "  python3 ozon_console_v1.py --отделы [--роль X]  — ОТДЕЛЫ(6); --роль X — карточка отдела\n"
        "  python3 ozon_console_v1.py --задания             — реестр ЗАДАНИЙ маркета ozon\n"
        "  python3 ozon_console_v1.py --дознание            — последний слепок фактов кабинета\n"
        "  python3 ozon_console_v1.py --авто               — хвост ozon_autopilot.log\n"
        "  python3 ozon_console_v1.py --дело               — всё ДЕЛО одним листом")


def _main(argv=None):
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    out = sys.stdout
    if not argv or argv[0] in ("-h", "--help", "help", "--справка"):
        print(_usage())
        return 0
    i = 0
    role = None
    cmd = None
    while i < len(argv):
        a = argv[i]
        if a in ("--штаб", "--shtab", "--staff"):
            cmd = cmd or "staff"
        elif a in ("--день", "--den", "--day"):
            cmd = cmd or "day"
        elif a in ("--kpi", "--kpis"):
            cmd = cmd or "kpi"
        elif a in ("--отделы", "--otdely", "--departments", "--depts"):
            cmd = cmd or "depts"
        elif a in ("--задания", "--zadaniya", "--tasks"):
            cmd = cmd or "tasks"
        elif a in ("--дознание", "--doznanie", "--truth"):
            cmd = cmd or "truth"
        elif a in ("--авто", "--avto", "--autopilot"):
            cmd = cmd or "autopilot"
        elif a in ("--дело", "--delo", "--deal"):
            cmd = cmd or "deal"
        elif a in ("--роль", "--rol", "--role"):
            cmd = cmd or "role"
            if i + 1 < len(argv):
                role = argv[i + 1]
                i += 1
        i += 1
    if cmd is None:
        print(_usage())
        return 1
    if cmd == "staff":
        print(cabinet_summary(out=out))
    elif cmd == "day":
        print(day_card(out=out))
    elif cmd == "kpi":
        print(kpi_text(out=out))
    elif cmd == "depts":
        print(dept_text(out=out, role=role))
    elif cmd == "role":
        print(dept_text(out=out, role=role or ""))
    elif cmd == "tasks":
        print(tasks_text(out=out))
    elif cmd == "truth":
        print(truth_text(out=out))
    elif cmd == "autopilot":
        print(autopilot_tail(out=out))
    elif cmd == "deal":
        print(deal_text(out=out))
    return 0


if __name__ == "__main__":
    sys.exit(_main())

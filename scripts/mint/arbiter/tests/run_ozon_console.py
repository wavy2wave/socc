#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · КОНСОЛЬ (ozon_console_v1) — герметичные приёмки read-кабинета.

Законы (зеркало ЯМ CC1-CC8, ОЗОН-правки):
  CC1  чистые функции с инъекцией: doc/ass/tick_doc/journal_rows/tasks/snapshot/path — всё
       подкладывается, диск не зовётся (герметика).
  CC2  инъекция перекрывает диск: подложенный doc/rows побеждает реальный стор.
  CC3  честность пустоты: «журнала дня нет» ≠ «слепка ещё нет» ≠ «реестра ещё нет» — не выдумываем.
  CC4  fail-soft: битый реестр/битый слепок/незнакомый отдел — текст, а не падение.
  CC5  отделы живы на подложенном доке: assess_all(0₽) на замороженной памяти → 6 отделов.
  CC8  ANSI только на живом tty: пайп/StringIO = plain; псевдо-tty = цвета (если socc_cli.style есть).
  CC10 one-shot CLI: --штаб/--день/--отделы/--задания/--дознание/--авто/--дело — exit 0; без
       команды/незнакомой — usage exit 1.
  CC11 ничего не пишет: ни один чистый рендер не создаёт файлов в песочнице.

Сухо: env-песочница, сети нет (assess_all — 0₽ на памяти), канон не пишется.
"""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ARB = Path(__file__).resolve().parent.parent
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

import ozon_console_v1 as con
import ozon_state_v1 as S
import ozon_departments_v1 as depts
import ymarket_tasks_v1 as T

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def _passed(cond):
    return bool(cond)


def _sandbox():
    d = Path(tempfile.mkdtemp(prefix="ozon_console_test_"))
    env = {
        "OZON_STATE_PATH": str(d / "state.json"),
        "OZON_SHIFT_MEMORY": str(d / "shift.json"),
        "OZON_DAY_JOURNAL": str(d / "day_journal.jsonl"),
        "OZON_TICK_LEDGER": str(d / "tick_ledger.json"),
        "YM_TASKS_PATH": str(d / "tasks.json"),
    }
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    return d, old, env


def _restore(old):
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _doc(**skus):
    return {"schema": S.SCHEMA, "skus": skus, "working_set": [],
            "daily": {}, "counters": {}}


def _ass(departments):
    return {"schema": "ozon.departments", "ts": "2026-09-08T00:00:00Z", "live": False,
            "departments": departments, "chains": [], "predictions": [], "groundedness": {},
            "accuracy": None}


def _t01_chistye_s_injektciy():
    d, old, env = _sandbox()
    try:
        doc = _doc(A={"lifecycle": S.LC_ON_SHELF, "published_verified": True, "errors": None})
        ass = _ass([{"dept": "A1", "name_ru": "ЦЕЛИ", "emoji": "🎯", "ok": True,
                     "human": "цели в норме", "grounded": True, "source": "none",
                     "predictions": []}])
        tick = {"tick_id": "OZTICK_TEST", "action": "HEALTHCHECK"}
        rows = [{"schema": "ozon.day.v1", "date": "2026-09-08", "ok": True, "kpis": {}}]
        tasks = []
        snap = {"sales_count": 27, "days": 30, "total_net": 22871.59, "ok": True}
        out = io.StringIO()
        s1 = con.cabinet_summary(out=out, doc=doc, ass=ass, tick_doc=tick)
        s2 = con.kpi_text(out=out, doc=doc, yesterday_kpis=None)
        s3 = con.dept_text(out=out, doc=doc, ass=ass, role="ЦЕЛИ")
        s4 = con.day_card(out=out, journal_rows=rows)
        s5 = con.tasks_text(out=out, tasks=tasks)
        s6 = con.truth_text(out=out, snapshot=snap)
        s7 = con.autopilot_tail(out=out, path=d / "нет_такого_лога.log")
        all_str = all(isinstance(x, str) and x for x in (s1, s2, s3, s4, s5, s6, s7))
        return _passed(all_str), f"ok={all_str}"
    finally:
        _restore(old)


def _t02_injektciya_pere_kyvaet_disk():
    d, old, env = _sandbox()
    try:
        # на диск кладём ОДИН день, а инъекция даёт ДРУГОЙ — побеждает инъекция
        Path(env["OZON_DAY_JOURNAL"]).write_text(
            json.dumps({"schema": "ozon.day.v1", "date": "2026-09-01", "ok": True,
                        "kpis": {"cards_tracked": 1}}) + "\n", encoding="utf-8")
        rows = [{"schema": "ozon.day.v1", "date": "2026-09-08", "ok": True,
                 "kpis": {"cards_tracked": 7}}]
        out = io.StringIO()
        s = con.day_card(out=out, journal_rows=rows)
        return _passed("2026-09-08" in s and "7" in s), s[:100]
    finally:
        _restore(old)


def _t03_chestnost_pustoty():
    d, old, env = _sandbox()
    try:
        out = io.StringIO()
        s_day = con.day_card(out=out, journal_rows=[])
        s_truth = con.truth_text(out=out, snapshot={})
        s_tasks = con.tasks_text(out=out, tasks=[])
        return _passed("журнала дня нет" in s_day
                       and "слепка ещё нет" in s_truth
                       and "записей ОЗОН 0" in s_tasks), \
               f"day={s_day[:40]} truth={s_truth[:40]} tasks={s_tasks[:40]}"
    finally:
        _restore(old)


def _t04_fail_soft():
    d, old, env = _sandbox()
    try:
        out = io.StringIO()
        s_reg = con.tasks_text(out=out, tasks=None)   # реестра в песочнице нет → честно
        s_broken = con.truth_text(out=out, snapshot={"error": "ключ истёк"})
        s_role = con.dept_text(out=out, doc=_doc(), role="НЕСУЩЕСТВУЮЩИЙ")
        s_autopilot = con.autopilot_tail(out=out, path=d / "пусто.log")
        s_day = con.day_card(out=out, journal_rows=None)  # диска нет — не падение
        return _passed("реестра" in s_reg and "ошибка" in s_broken
                       and s_role and s_autopilot and s_day), \
               f"reg={s_reg[:40]} broken={s_broken[:40]}"
    finally:
        _restore(old)


def _t05_otdely_na_doke():
    d, old, env = _sandbox()
    try:
        doc = _doc(A={"lifecycle": S.LC_ON_SHELF, "published_verified": True, "errors": None})
        ass = depts.assess_all(doc=doc)
        out = io.StringIO()
        s = con.dept_text(out=out, doc=doc, ass=ass)
        n = len(ass.get("departments") or [])
        return _passed(n == 6 and s), f"n={n}"
    finally:
        _restore(old)


def _t08_ansi_tolko_tty():
    d, old, env = _sandbox()
    try:
        from ozon_console_v1 import S as style
        class _FakeTty:
            def isatty(self):
                return True
        plain_out = io.StringIO()
        tty_out = _FakeTty()
        p = con._col(plain_out, "GR", "зелено")
        t = con._col(tty_out, "GR", "зелено")
        if style is None:
            # стиль недоступен — честно plain везде
            return _passed(p == "зелено" and t == "зелено"), "style нет → plain"
        return _passed(p == "зелено" and t.startswith(style.GR) and t.endswith(style.R)), \
               f"plain={p!r} tty={t[:20]!r}"
    finally:
        _restore(old)


def _t10_cli_one_shot():
    d, old, env = _sandbox()
    try:
        import io as _io
        for args, expect0 in ((["--штаб"], 0), (["--день"], 0), (["--отделы"], 0),
                              (["--задания"], 0), (["--дознание"], 0), (["--авто"], 0),
                              (["--дело"], 0)):
            buf = _io.StringIO()
            out_old, sys.stdout = sys.stdout, buf
            try:
                rc = con._main(args)
            finally:
                sys.stdout = out_old
            if rc != expect0:
                return _passed(False), f"{args}: rc={rc}"
        # без команды → usage-справка, rc=0 (как --help); незнакомая команда → usage, rc=1
        buf = _io.StringIO()
        out_old, sys.stdout = sys.stdout, buf
        try:
            rc_empty = con._main([])
            rc_unknown = con._main(["--wat"])
        finally:
            sys.stdout = out_old
        return _passed(rc_empty == 0 and rc_unknown == 1
                       and "КОНСОЛЬ-ОЗОН" in buf.getvalue()), \
               f"empty={rc_empty} unknown={rc_unknown}"
    finally:
        _restore(old)


def _t11_nichego_ne_pishet():
    d, old, env = _sandbox()
    try:
        doc = _doc(A={"lifecycle": S.LC_ON_SHELF, "published_verified": True, "errors": None})
        ass = _ass([{"dept": "A1", "name_ru": "ЦЕЛИ", "emoji": "🎯", "ok": True,
                     "human": "х", "grounded": True, "source": "none", "predictions": []}])
        out = io.StringIO()
        con.cabinet_summary(out=out, doc=doc, ass=ass, tick_doc={"action": "HEALTHCHECK"})
        con.day_card(out=out, journal_rows=[{"date": "2026-09-08", "ok": True}])
        con.dept_text(out=out, doc=doc, ass=ass)
        con.tasks_text(out=out, tasks=[])
        con.truth_text(out=out, snapshot={"ok": True})
        con.autopilot_tail(out=out, path=d / "нет_лога.log")
        created = [p for p in d.iterdir()]
        return _passed(not created), f"создано файлов: {len(created)}"
    finally:
        _restore(old)


TESTS = [
    ("CC1 чистые функции с инъекцией (всё подложено)", _t01_chistye_s_injektciy),
    ("CC2 инъекция перекрывает диск", _t02_injektciya_pere_kyvaet_disk),
    ("CC3 честность пустоты (нет≠нет≠нет)", _t03_chestnost_pustoty),
    ("CC4 fail-soft (битое/незнакомое — текст, не падение)", _t04_fail_soft),
    ("CC5 отделы живы на подложенном доке (6 отделов)", _t05_otdely_na_doke),
    ("CC8 ANSI только на живом tty", _t08_ansi_tolko_tty),
    ("CC10 one-shot CLI: команды exit 0 / usage exit 1", _t10_cli_one_shot),
    ("CC11 ни один чистый рендер не пишет файлы", _t11_nichego_ne_pishet),
]


def main():
    passed = 0
    for name, fn in TESTS:
        try:
            ok, extra = fn()
        except Exception as e:
            ok, extra = False, f"{type(e).__name__}: {e}"
        if ok:
            passed += 1
        print(f"{PASS if ok else FAIL} · {name}" + (f" — {extra}" if extra and not ok else ""))
    print(f"\nOZON КОНСОЛЬ · {passed}/{len(TESTS)} зелёных")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

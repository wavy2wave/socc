#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · ЦИКЛ-ДЕНЯ (ozon_cycle_day_v1) — герметичные приёмки диспетчера заданий.

Законы (CD1-CD6 зеркалим, маркет = "ozon"):
  C1  сухо по умолчанию: форма без --commit ничего не пишет (реестра в песочнице нет и не появится).
  C2  форма идемпотентна (TZ1-дедуп): второй --commit не плодит дубль, чужих (ym) не трогает.
  C3  наблюдение с evidence: без артефакта (пустое evidence) кандидат не формируется (CD2).
  C4  сканеры из живых источников: память с errors→OZ_CONTROLLER/cards; журнала нет→DISPATCHER/health;
      пустая память → кандидатов нет (не выдумываем).
  C5  планёрка различает: «реестра ещё нет» ≠ «0 открытых» ≠ список (CD4).
  C6  диспетчер без фейк-пасс: без --cycle-dry день не подхватывается; с --cycle-dry — сухо (CD5).
  C7  диспетчер никогда не mark_step: после разбора задание всё ещё open (CD5).
  C8  RUBICON: единственный write формы — локальный реестр (CD6); в реестре нет ничего кроме задач.

Сухо: env-песочница (OZON_STATE_PATH/OZON_SHIFT_MEMORY/OZON_DAY_JOURNAL/YM_TASKS_PATH), сети нет.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ARB = Path(__file__).resolve().parent.parent
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

import ozon_cycle_day_v1 as C
import ozon_day_v1 as day_mod
import ozon_state_v1 as S
import ymarket_tasks_v1 as T

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def _passed(cond):
    return bool(cond)


def _sandbox():
    d = Path(tempfile.mkdtemp(prefix="ozon_cycle_test_"))
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


def _write_state(d, skus):
    doc = {"schema": S.SCHEMA, "created_at": "2026-09-08T00:00:00Z", "updated_at": "2026-09-08T00:00:00Z",
           "working_set": [], "skus": skus, "daily": {}, "counters": {}}
    p = S.state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _t01_sukho_po_umolchaniyu():
    d, old, env = _sandbox()
    try:
        summary, _ = C.form(commit=False)
        tp = T.task_path()
        return _passed(not tp.exists()), f"реестр_создан={tp.exists()} summary={summary}"
    finally:
        _restore(old)


def _t02_forma_idempotentna():
    d, old, env = _sandbox()
    try:
        _write_state(d, {"E1": {"lifecycle": S.LC_IMPORTED, "errors": ["x"]}})
        s1, _ = C.form(commit=True)
        n1 = len(T.load()[0])
        s2, _ = C.form(commit=True)     # второй прогон — дубль не создаётся
        n2 = len(T.load()[0])
        all_ozon = all(t.get("market") == "ozon" for t in T.load()[0])
        # 2 задания: OZ_CONTROLLER (errors) + DISPATCHER (журнала дня ещё нет) — оба с evidence
        return _passed(n1 == 2 and n2 == 2 and s2.get("new") == 0
                       and all_ozon), f"n1={n1} n2={n2} all_ozon={all_ozon}"
    finally:
        _restore(old)


def _t03_evidence_ne_pusto():
    d, old, env = _sandbox()
    try:
        obs = C._obs_task("что-то", "OPERATOR", "categories", priority=1, evidence="")
        obs_ok = C._obs_task("что-то", "OPERATOR", "categories", priority=1,
                             evidence="ozon_state:/x: 2 sku")
        return _passed(obs is None and obs_ok is not None
                       and obs_ok["refs"]["evidence"]), "голое без evidence не формируется"
    finally:
        _restore(old)


def _t04_skanery_zhivye():
    d, old, env = _sandbox()
    try:
        # память с errors → OZ_CONTROLLER; пусто → кандидатов нет
        _write_state(d, {"E1": {"lifecycle": S.LC_IMPORTED, "errors": ["x"]}})
        st = C.scan_state()
        owners = {o.get("owner") for o in st}
        ev = all(o.get("refs", {}).get("evidence") for o in st)
        _write_state(d, {})
        empty = C.scan_state()
        # журнала дня нет → DISPATCHER/health
        sd = C.scan_day()
        sd_owners = {o.get("owner") for o in sd}
        sd_ev = all(o.get("refs", {}).get("evidence") for o in sd)
        return _passed("OZ_CONTROLLER" in owners and ev and not empty
                       and "DISPATCHER" in sd_owners and sd_ev and sd), \
               f"owners={owners} empty={len(empty)} sd={[o.get('owner') for o in sd]}"
    finally:
        _restore(old)


def _t05_planerka_razlichaet():
    d, old, env = _sandbox()
    try:
        # 1. реестра ещё нет
        t1 = "\n".join(C.plannerka_text())
        absent = "ещё нет" in t1
        # 2. реестр есть, 0 записей ОЗОН
        T.save([], path=T.task_path())
        t2 = "\n".join(C.plannerka_text())
        zero = "0" in t2 and "записей ОЗОН: 0" in t2
        # 3. есть открытые — список
        _write_state(d, {"E1": {"lifecycle": S.LC_IMPORTED, "errors": ["x"]}})
        C.form(commit=True)
        t3 = "\n".join(C.plannerka_text())
        listed = "открыто 1" in t3 and "OZ_CONTROLLER" in t3
        # 4. битый реестр — честная ошибка
        Path(T.task_path()).write_text("{garbage", encoding="utf-8")
        t4 = "\n".join(C.plannerka_text())
        broken = "битый" in t4
        return _passed(absent and zero and listed and broken), \
               f"absent={absent} zero={zero} listed={listed} broken={broken}"
    finally:
        _restore(old)


def _t06_dispatch_bez_feyk():
    d, old, env = _sandbox()
    try:
        calls = []

        def fake_day(dry=True):
            calls.append({"dry": dry})
            return {"ok": True, "roles": {"MANAGER_TICK": {"action": "HEALTHCHECK"}}}

        # без --cycle-dry день не зовётся (read-разбор)
        _write_state(d, {"E1": {"lifecycle": S.LC_IMPORTED, "errors": ["x"]}})
        C.form(commit=True)
        s0, _ = C.dispatch(day_fn=fake_day, cycle_dry=False)
        no_run = len(calls) == 0
        # с --cycle-dry сухой день подхватывается
        s1, _ = C.dispatch(day_fn=fake_day, cycle_dry=True)
        ran = len(calls) == 1 and calls[0]["dry"] is True
        return _passed(no_run and ran), f"no_run={no_run} calls={calls}"
    finally:
        _restore(old)


def _t07_dispatch_ne_mark_step():
    d, old, env = _sandbox()
    try:
        _write_state(d, {"E1": {"lifecycle": S.LC_IMPORTED, "errors": ["x"]}})
        C.form(commit=True)
        s0, _ = C.dispatch(cycle_dry=True)
        tasks, _ = T.load()
        open_count = len(T.open_only(tasks))
        return _passed(open_count == 2), f"open_count={open_count} (не тронуто, 2 открытых)"
    finally:
        _restore(old)


def _t08_rubicon_write_tolko_registry():
    d, old, env = _sandbox()
    try:
        _write_state(d, {"E1": {"lifecycle": S.LC_IMPORTED, "errors": ["x"]}})
        C.form(commit=True)
        # в песочнице появился ТОЛЬКО реестр задач (не журнал дня, не тик-репорт)
        created = [str(p) for p in Path(env["OZON_DAY_JOURNAL"]).parent.iterdir()]
        has_tasks = any("tasks.json" in str(p) for p in created)
        no_journal = not any("day_journal" in str(p) for p in created)
        return _passed(has_tasks and no_journal), f"создано: {created}"
    finally:
        _restore(old)


TESTS = [
    ("C1 сухо по умолчанию (форма без commit не пишет)", _t01_sukho_po_umolchaniyu),
    ("C2 форма идемпотентна (TZ1-дедуп)", _t02_forma_idempotentna),
    ("C3 evidence не пусто (CD2)", _t03_evidence_ne_pusto),
    ("C4 сканеры из живых источников", _t04_skanery_zhivye),
    ("C5 планёрка: нет реестра ≠ 0 ≠ список (CD4)", _t05_planerka_razlichaet),
    ("C6 диспетчер без фейк-пасс (CD5)", _t06_dispatch_bez_feyk),
    ("C7 диспетчер никогда не mark_step (CD5)", _t07_dispatch_ne_mark_step),
    ("C8 RUBICON: единственный write — локальный реестр (CD6)", _t08_rubicon_write_tolko_registry),
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
    print(f"\nOZON ЦИКЛ-ДЕНЬ · {passed}/{len(TESTS)} зелёных")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

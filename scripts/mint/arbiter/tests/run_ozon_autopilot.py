#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · АВТОПИЛОТ (ozon_autopilot_v1) — герметичные приёмки руки под расписание.

Законы (зеркало ymarket_autopilot, RUBICON физически):
  A1  у run() НЕТ параметра commit и НЕТ пути к живому дню: день зовётся строго dry=True,
      результат всегда commit=False.
  A2  день подкладывается через шов day_fn (герметика не трогает канонический TICK_REPORT);
      live_read по умолчанию True (автопилот в проде видит реальные цифры 0₽ GET).
  A3  env-гейт дознания: OZON_AUTOPILOT_LIVE_READ=0/off выключает живое; отсутствие env → True;
      явный флаг приоритетнее env.
  A4  fail-soft exit 0: _main() ловит беду, пишет в лог, возвращает 0 (расписание живёт,
      рестарт-шторма нет).
  A5  повтор идемпотентен: два прогона подряд оба ok, дублей-слома нет.
  A6  лог пишется в песочницу (OZON_AUTOPILOT_LOG), человеко-отчёт + JSON; канон не трогается.

Сухо: env-песочница, сети нет, канон не пишется (день — шов).
"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ARB = Path(__file__).resolve().parent.parent
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

import ozon_autopilot_v1 as A

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def _passed(cond):
    return bool(cond)


def _sandbox():
    d = Path(tempfile.mkdtemp(prefix="ozon_autopilot_test_"))
    env = {
        "OZON_STATE_PATH": str(d / "state.json"),
        "OZON_SHIFT_MEMORY": str(d / "shift.json"),
        "OZON_DAY_JOURNAL": str(d / "day_journal.jsonl"),
        "OZON_TICK_LEDGER": str(d / "tick_ledger.json"),
        "OZON_AUTOPILOT_LOG": str(d / "autopilot.log"),
        "OZON_AUTOPILOT_LIVE_READ": "0",   # герметика: дознание не зовёт сеть
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


def _mk_day(live):
    calls = []

    def day_fn(*, dry=True, live_read=False):
        calls.append({"dry": dry, "live_read": live_read})
        return {"ts": "2026-09-08T00:00:00Z", "date": "2026-09-08", "ok": True,
                "dry": dry, "live_read": bool(live_read), "client_id_known": False,
                "roles": {"MANAGER_TICK": {"action": "HEALTHCHECK"}},
                "failures": [], "burning": {"count": 0, "items": []},
                "kpis": {"cards_tracked": 3, "cards_on_shelf": 1}}

    return day_fn, calls


def _t01_net_commit_param():
    d, old, env = _sandbox()
    try:
        import inspect
        sig = inspect.signature(A.run)
        src = Path(A.__file__).read_text(encoding="utf-8")
        day_fn, calls = _mk_day(False)
        r = A.run(day_fn=day_fn)
        return _passed("commit" not in sig.parameters
                       and r.get("commit") is False
                       and calls[0]["dry"] is True
                       and "commit=True" not in src), \
               f"params={list(sig.parameters)} commit={r.get('commit')}"
    finally:
        _restore(old)


def _t02_seam_i_live_default():
    d, old, env = _sandbox()
    try:
        del os.environ["OZON_AUTOPILOT_LIVE_READ"]
        day_fn, calls = _mk_day(True)
        r = A.run(day_fn=day_fn)
        return _passed(calls and calls[0]["live_read"] is True
                       and r.get("ok") is True), f"calls={calls}"
    finally:
        _restore(old)


def _t03_env_gate():
    d, old, env = _sandbox()
    try:
        # env=0 → False
        day_fn, c1 = _mk_day(False)
        A.run(day_fn=day_fn)
        off = not c1[0]["live_read"]
        # env=off → False
        os.environ["OZON_AUTOPILOT_LIVE_READ"] = "off"
        day_fn, c2 = _mk_day(False)
        A.run(day_fn=day_fn)
        off2 = not c2[0]["live_read"]
        # env=0, но флаг явный True → True (флаг приоритетнее)
        os.environ["OZON_AUTOPILOT_LIVE_READ"] = "0"
        day_fn, c3 = _mk_day(True)
        A.run(live_read=True, day_fn=day_fn)
        flag = c3[0]["live_read"] is True
        # отсутствие env → True
        os.environ.pop("OZON_AUTOPILOT_LIVE_READ", None)
        day_fn, c4 = _mk_day(True)
        A.run(day_fn=day_fn)
        absent = c4[0]["live_read"] is True
        return _passed(off and off2 and flag and absent), \
               f"off={off} off2={off2} flag={flag} absent={absent}"
    finally:
        _restore(old)


def _t04_fail_soft_exit0():
    d, old, env = _sandbox()
    try:
        def boom(*a, **kw):
            raise RuntimeError("день упал в тесте")

        A.run = boom     # monkeypatch run → _main должен поймать и вернуть 0
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = A._main(["--json"])
        log = Path(env["OZON_AUTOPILOT_LOG"])
        ok = code == 0 and "упал" in log.read_text(encoding="utf-8")
        A.run = A.__original_run
        return _passed(ok), f"code={code} json={buf.getvalue()[:80]}"
    finally:
        _restore(old)


def _t05_povtor_idempotenten():
    d, old, env = _sandbox()
    try:
        day_fn, calls = _mk_day(False)
        r1 = A.run(day_fn=day_fn)
        r2 = A.run(day_fn=day_fn)
        return _passed(r1.get("ok") is True and r2.get("ok") is True
                       and r1.get("kpis") == r2.get("kpis")), \
               f"r1={r1.get('ok')} r2={r2.get('ok')}"
    finally:
        _restore(old)


def _t06_log_v_pesok():
    d, old, env = _sandbox()
    try:
        day_fn, calls = _mk_day(False)
        A.run(day_fn=day_fn)
        lp = Path(A.log_path())
        txt = lp.read_text(encoding="utf-8") if lp.exists() else ""
        return _passed(str(lp) == env["OZON_AUTOPILOT_LOG"]
                       and "АВТОПИЛОТ ОЗОН" in txt
                       and '"ok": true' in txt), \
               f"log_exists={lp.exists()}"
    finally:
        _restore(old)


# сохранить оригинал run для restore (test _t04 подменяет)
A.__original_run = A.run

TESTS = [
    ("A1 RUBICON: нет commit-параметра, день строго сухо", _t01_net_commit_param),
    ("A2 шов дня + live_read по умолчанию True", _t02_seam_i_live_default),
    ("A3 env-гейт дознания (0/off/флаг/env)", _t03_env_gate),
    ("A4 fail-soft: _main ловит беду, exit 0, лог", _t04_fail_soft_exit0),
    ("A5 повтор идемпотентен", _t05_povtor_idempotenten),
    ("A6 лог только в песочницу", _t06_log_v_pesok),
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
    print(f"\nOZON АВТОПИЛОТ · {passed}/{len(TESTS)} зелёных")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

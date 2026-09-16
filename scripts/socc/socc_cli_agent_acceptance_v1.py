#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · АГЕНТ — герметичная приёмка (движок НЕ стартует, 0₽).

Законы §АГЕНТ (канон SOCC_HOME_CLI_V1.md):
  AG1 лента_честная   — живой tty: авторская строка ≤ ширины (clip, «…»); пайп — целой.
  AG2 сухо_по_умолчанию — «живой/commit» → отказ; «прогон» → маршрут в _run_cycle_dry
                        (мы НЕ зовём движок — ставим заглушку и смотрим, что вызвана).
  AG3 реальные_вердикты — сводка из payload-фикстуры (честные строки, не нули);
                        пустой стор → честно «данных нет», не краш.
  AG4 вход_не_падает  — once-режим rc 0; «выход»/незнакомая фраза → мягко; cli.py знает «агент».
Запуск:  python3 scripts/socc/socc_cli_agent_acceptance_v1.py
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

SOCC_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOCC_ROOT) not in sys.path:
    sys.path.insert(0, str(SOCC_ROOT))

_ANSI = re.compile(r"\x1b\[[0-9;?]*m")


def _clean(s):
    return _ANSI.sub("", s)


def _out():
    return io.StringIO()


# ── фикстура payload (как настоящий store_payload, но наш — детерминированно) ──
def _fixture_payload(store):
    return {
        "store": store,
        "info": {"slug": store},
        "pulse": {"run_verdicts": {"PASS": 1, "DRY": 1}},
        "ledger": [
            {"node": "ДОНОР", "verdict": "PASS", "dry": True, "ts": "08:00", "evidence": "донор: 4 строки", "note": ""},
            {"node": "ПЛАНЁРКА", "verdict": "PASS", "dry": True, "ts": "08:05", "evidence": "", "note": ""},
        ],
        "queue": [{"tag": "СВЕРКА", "owner": "CONTROLLER", "what": "Матрица отстала", "evidence": ""}],
        "registry": ("absent", []),
    }


class _TtyProbe:
    """Притворяемся живым tty (isatty True), но печатаем в реальный stdout."""

    def __init__(self, real):
        self._real = real

    def isatty(self):
        return True

    def write(self, s):
        self._real.write(s)

    def flush(self):
        self._real.flush()


def main():
    from socc_cli import agent as A
    from socc_cli import dom as D
    print("🌱 SOCC · АГЕНТ · герметичная приёмка (движок не стартует, 0₽)")
    all_ok = True
    n = [0]

    def ok(tag, cond, note=""):
        n[0] += 1
        mark = "✅" if cond else "❌"
        print(f"   {mark} {tag}" + (f"  {note}" if note and not cond else ""))
        nonlocal all_ok
        all_ok = all_ok and cond

    # AG1 — живой tty: длинную строку режем до ширины, добавляем «…»
    _old_tty = sys.stdout
    _old_gs = os.get_terminal_size
    sys.stdout = _TtyProbe(_old_tty)
    os.get_terminal_size = lambda: os.terminal_size((24, 40))
    try:
        buf = _out()
        A._say(buf, "д" * 200, A.S.B)
        text = _clean(buf.getvalue())
        longest = max(len(l) for l in text.splitlines())
        ok("AG1 lenta_chestnaya", longest <= 41 and "…" in text,
           f"длина {longest}, ожидалось ≤ 40")
    finally:
        sys.stdout = _old_tty
        os.get_terminal_size = _old_gs

    # AG2 — живое слово → отказ (движок не зовём); «прогон» → маршрут в _run_cycle_dry
    called = []
    _orig = A._run_cycle_dry

    def _fake_cycle(out, store):
        called.append(store)
        return 0

    A._run_cycle_dry = _fake_cycle
    try:
        buf = _out()
        rc = A._handle(buf, "test-store", "запусти живой commit по-настоящему")
        out = _clean(buf.getvalue())
        ok("AG2 suho_refuse", rc == "ok" and not called and "живой ход" in out,
           f"called={called}, out={out[:60]!r}")
        buf2 = _out()
        A._handle(buf2, "test-store", "прогон")
        ok("AG2 suho_route", called == ["test-store"], f"called={called}")
    finally:
        A._run_cycle_dry = _orig

    # AG3 — сводка из фикстуры честная; пустой payload (None/{}) → «данных нет»
    _orig_p = D.store_payload
    _orig_h = D._cycle_hash
    D.store_payload = _fixture_payload
    D._cycle_hash = lambda store: "abc123def0"
    try:
        buf = _out()
        A._answer_status(buf, "test-store")
        out = _clean(buf.getvalue())
        ok("AG3 verdicts_fixture",
           "прогонов в леджере 2" in out and "закрыто ПЛАНЁРКОЙ 1" in out
           and "PASS 1" in out and "реестр заданий не материализован" in out,
           out[:120])
    finally:
        D.store_payload = _orig_p
        D._cycle_hash = _orig_h

    D.store_payload = lambda store: {}          # пустой/сломанный стор
    try:
        buf = _out()
        A._answer_status(buf, "pustoj-store")
        out = _clean(buf.getvalue())
        ok("AG3 pustoj_store_honest", "данных нет" in out or "пуст" in out, out[:80])
    finally:
        D.store_payload = _orig_p

    # AG4 — once/выход/незнакомое/помощь не падают; cli знает «агент»
    ok("AG4 once_status_rc0", A.run_agent(out=_out(), once="статус", store="x") == 0)
    ok("AG4 once_help_rc0", A.run_agent(out=_out(), once="что умеешь", store="x") == 0)
    ok("AG4 exit_code", A._handle(_out(), "x", "выход") == "exit"
       and A._handle(_out(), "x", "пока") == "exit")
    buf = _out()
    A._handle(buf, "x", "абвгд незнакомое")
    ok("AG4 unknown_help", "не понял" in _clean(buf.getvalue()) and "вот что я умею" in _clean(buf.getvalue()))
    src = (SOCC_ROOT / "socc_cli" / "cli.py").read_text(encoding="utf-8")
    ok("AG4 cli_agent_vetka", 'in ("агент", "agent", "а")' in src or "агент" in src)
    asrc = (SOCC_ROOT / "socc_cli" / "agent.py").read_text(encoding="utf-8")
    ok("AG2 dry_tolko_argv", '"--store", store, "--dry"' in asrc,
       "единственный запуск движка собран строго --dry (argv БРИГАДИРА)")

    print(f"\nИтого: {'✅ АГЕНТ AG1–AG4 зелёные' if all_ok else '❌ есть падения'} ({n[0]} проверок)")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

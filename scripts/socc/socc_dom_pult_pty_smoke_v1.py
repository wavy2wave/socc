#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · ПУЛЬТ ЯМ-ЦИКЛА — ЖИВОЙ ДЫМ НА PTY (raw-клавиатура, реальный `socc`).

Зачем: PU-приёмка гоняет пульт строками (StringIO + runner-инъекция), но живой
путь пульта — raw-клавиши на настоящем tty поверх реального `socc` (движок view,
один alt-screen, рельсы d/c). Здесь дравер сам делает pty.fork() и шлёт клавиши
как человек. Цифра ПУЛЬТ-ШТАБ считается динамически из ym_rows (сейчас 9), чтобы
дым не ломался при росте меню.

Сценарии (0₽, движок НЕ стартует НИ РАЗУ — на рельсах Enter не жмём, отменяем q):
  P1 пульт_штаб_вход — socc ym → цифра=ПУЛЬТ-ШТАБ → кадр «ПУЛЬТ · ШТАБ ЯМ-ЦИКЛА»
                      → q → меню ЯМ → q → выход rc 0
  P2 команд_день+рельс_сухо — в штабе Enter=КОМАНДИР ДНЯ витрины → d → кадр
                      «РЕЛЬС · СУХОЙ 0₽» (подтверждение сухого) → q (отмена) →
                      назад по ступеням до rc 0; движок не звался (нет PASS/DRY_OK)
  P3 руб_слово_80×24 — на РОВНО 80×24: c → слово-магазин → ЧУЖОЕ слово+Enter →
                      назад к КОМАНДИРУ (отказ честный) → c → СВОЁ слово+Enter →
                      кадр «слово принято» (commit) → q отмена → назад → rc 0;
                      кадр стабилен: низ на \x1b[24;1H, внутри кадра нет `\n`.

Запуск:  python3 scripts/socc/socc_dom_pult_pty_smoke_v1.py
"""
from __future__ import annotations

import os
import re
import select
import shutil
import signal
import sys
import time
from pathlib import Path

SOCC_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOCC_ROOT) not in sys.path:
    sys.path.insert(0, str(SOCC_ROOT))

_ANSI = re.compile(rb"\x1b\[[0-9;]*m|[\x01-\x08\x0b\x0c\x0e-\x1f]")


class Pty:
    """Ребёнок на настоящем pty; клавиши шлём как человек."""

    def __init__(self, argv, cols=120, rows=40):
        import pty
        import struct
        import termios
        import fcntl
        pid, master = pty.fork()
        if pid == 0:  # ребёнок: stdin/stdout/stderr уже на slave
            os.execv(argv[0], argv)
            os._exit(127)
        fcntl.ioctl(master, termios.TIOCSWINSZ,
                    struct.pack("HHHH", rows, cols, 0, 0))
        self.pid, self.master = pid, master
        self.buf = b""
        self.cursor = 0
        self.done = False

    def _fill(self, timeout=0.2):
        deadline = time.time() + timeout
        while time.time() < deadline:
            r, _, _ = select.select([self.master], [], [], 0.05)
            if not r:
                return
            try:
                chunk = os.read(self.master, 65536)
            except OSError:
                self.done = True
                return
            if not chunk:
                self.done = True
                return
            self.buf += chunk

    def send(self, data):
        os.write(self.master, data)

    def wait_for(self, text, timeout=15.0):
        needle = text if isinstance(text, bytes) else text.encode()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if needle in self.buf[self.cursor:]:
                idx = self.buf.find(needle, self.cursor)
                self.cursor = idx + len(needle)
                return True
            self._fill(0.3)
            if self.done:
                break
        return False

    def frames(self):
        return self.buf.count(b"\x1b[1;1H")

    def last_frame(self):
        idx = self.buf.rfind(b"\x1b[1;1H")
        return self.buf[idx:] if idx >= 0 else b""

    def close(self):
        try:
            os.kill(self.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            os.close(self.master)
        except OSError:
            pass

    def exitcode(self, timeout=8.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:
                return None
            if pid != 0:
                return os.waitstatus_to_exitcode(status)
            self._fill(0.3)
        return None


def _socc(argv):
    """Команда ребёнка: канонический `socc`, иначе python-модуль дома."""
    exe = shutil.which("socc")
    if exe:
        return [exe] + list(argv)
    return [sys.executable, str(SOCC_ROOT / "socc_cli" / "home.py")] + list(argv)


def _fleet_digit():
    """Цифра пункта ПУЛЬТ-ШТАБ в меню ЯМ (считаем из живых строк, не хардкодим)."""
    from socc_cli import dom as D
    items = [r for r in D.ym_rows(D._stores_map()) if r.get("kind") == "item"]
    for n, r in enumerate(items, 1):
        if r.get("action") == "pult:fleet":
            return n if n <= 9 else None
    return None


def p1_shtab_vhod(slug, digit):
    steps = []
    p = Pty(_socc(["ym"]))
    try:
        ok = p.wait_for("магазинов в манифесте")
        steps.append(("старт: меню ЯМ", ok))
        p.send(str(digit).encode())
        ok = p.wait_for("↑↓ выбор · Enter КОМАНДИР ДНЯ")
        steps.append((f"цифра {digit} → ПУЛЬТ · ШТАБ ЯМ-ЦИКЛА", ok))
        p.send(b"q")
        ok = p.wait_for("магазинов в манифесте")
        steps.append(("q из ШТАБА → меню ЯМ", ok))
        p.send(b"q")
        rc = p.exitcode()
        steps.append((f"выход rc={rc}", rc == 0))
        return steps
    finally:
        p.close()


def p2_komandir_dry(slug, digit):
    steps = []
    p = Pty(_socc(["ym"]))
    try:
        ok = p.wait_for("магазинов в манифесте")
        steps.append(("старт: меню ЯМ", ok))
        p.send(str(digit).encode())
        ok = p.wait_for("↑↓ выбор · Enter КОМАНДИР ДНЯ")
        steps.append(("цифра → ПУЛЬТ · ШТАБ", ok))
        p.send(b"\r")  # Enter на витрине → КОМАНДИР ДНЯ
        ok = p.wait_for(f"ПУЛЬТ · КОМАНДИР ДНЯ · {slug}")
        steps.append((f"Enter → КОМАНДИР ДНЯ · {slug}", ok))
        p.send(b"d")  # рельс сухого: одно подтверждение, Enter НЕ жмём
        ok = p.wait_for(f"РЕЛЬС · СУХОЙ 0₽ · {slug}")
        steps.append(("d → кадр РЕЛЬС · СУХОЙ 0₽ (подтверждение)", ok))
        p.send(b"q")  # отмена сухого → назад к КОМАНДИРУ
        ok = p.wait_for(f"ПУЛЬТ · КОМАНДИР ДНЯ · {slug}")
        steps.append(("q → отмена сухого, назад к КОМАНДИРУ", ok))
        p.send(b"q")
        ok = p.wait_for("↑↓ выбор · Enter КОМАНДИР ДНЯ")
        steps.append(("q → назад в ШТАБ", ok))
        p.send(b"q")
        ok = p.wait_for("магазинов в манифесте")
        steps.append(("q → меню ЯМ", ok))
        p.send(b"q")
        rc = p.exitcode()
        no_exec = b"PASS/DRY_OK" not in p.buf
        steps.append((f"выход rc={rc} · движок НЕ звался", rc == 0 and no_exec))
        return steps
    finally:
        p.close()


def p3_rub_slovo_80x24(slug, digit):
    """РУБИКОН на РОВНО 80×24: чужое слово → честный отказ · своё слово → кадр
    «слово принято» (commit), затем q-отмена. Enter на commit НЕ жмём — движок жив.
    Кадр commit стабилен: низ на \x1b[24;1H, внутри кадра нет `\n`."""
    steps = []
    p = Pty(_socc(["ym"]), cols=80, rows=24)
    try:
        ok = p.wait_for("магазинов в манифесте")
        steps.append(("старт: меню ЯМ на 80×24", ok))
        p.send(str(digit).encode())
        ok = p.wait_for("↑↓ выбор · Enter КОМАНДИР ДНЯ")
        steps.append(("цифра → ПУЛЬТ · ШТАБ на 80×24", ok))
        p.send(b"\r")
        ok = p.wait_for(f"ПУЛЬТ · КОМАНДИР ДНЯ · {slug}")
        steps.append((f"Enter → КОМАНДИР ДНЯ · {slug}", ok))
        p.send(b"c")  # рельс живого: RUBICON = слово-магазин
        ok = p.wait_for("ДВОЙНОЕ ПОДТВЕРЖДЕНИЕ")
        steps.append(("c → РЕЛЬС · ЖИВОЙ (введи слово-магазин)", ok))
        p.send(b"chuzhoe-slovo\r")  # чужое слово + Enter → честный отказ
        ok = p.wait_for(f"ПУЛЬТ · КОМАНДИР ДНЯ · {slug}")
        steps.append(("чужое слово+Enter → отказ, назад к КОМАНДИРУ", ok))
        p.send(b"c")
        ok = p.wait_for("ДВОЙНОЕ ПОДТВЕРЖДЕНИЕ")
        steps.append(("c → слово-магазин снова", ok))
        p.send(slug.encode() + b"\r")  # СВОЁ слово → кадр commit
        ok = p.wait_for("слово принято")
        steps.append(("своё слово+Enter → кадр «слово принято» (commit)", ok))
        fr = p.last_frame()
        ok_row = b"\x1b[24;1H" in fr
        ok_nl = b"\n" not in fr
        steps.append((f"кадр commit 80×24: низ 24;1H ({ok_row}) · без \\n ({ok_nl})",
                      ok_row and ok_nl))
        p.send(b"q")  # отмена commit → КОМАНДИР (Enter НЕ жмём — движок не стартует)
        ok = p.wait_for(f"ПУЛЬТ · КОМАНДИР ДНЯ · {slug}")
        steps.append(("q → отмена commit, назад к КОМАНДИРУ", ok))
        p.send(b"q")
        ok = p.wait_for("↑↓ выбор · Enter КОМАНДИР ДНЯ")
        steps.append(("q → ШТАБ", ok))
        p.send(b"q")
        ok = p.wait_for("магазинов в манифесте")
        steps.append(("q → меню ЯМ", ok))
        p.send(b"q")
        rc = p.exitcode()
        no_exec = b"PASS/DRY_OK" not in p.buf
        steps.append((f"выход rc={rc} · движок НЕ звался", rc == 0 and no_exec))
        return steps
    finally:
        p.close()


def main():
    print("🎛️  SOCC · ДОМ · ПУЛЬТ ЯМ-ЦИКЛА · ЖИВОЙ ДЫМ НА PTY (0₽, движок не стартует)")
    from socc_cli import dom as D
    stores = D._stores_map()
    slug = next(iter(sorted(stores)), None)
    digit = _fleet_digit()
    if digit is None:
        print("   ❌ не нашёл пункт ПУЛЬТ-ШТАБ в меню (или его цифра > 9)")
        return 1
    if not slug:
        print("   ⚠ манифест витрин пуст — P2/P3 требуют витрину; гоняю только P1")
    print(f"   пункт ПУЛЬТ-ШТАБ = цифра {digit} · витрина = {slug or '—'}")
    all_ok = True
    scenarios = [("P1 пульт_штаб_вход", p1_shtab_vhod, slug, digit)]
    if slug:
        scenarios += [("P2 команд_день+рельс_сухо", p2_komandir_dry, slug, digit),
                      ("P3 руб_слово_80×24", p3_rub_slovo_80x24, slug, digit)]
    for name, fn, s, d in scenarios:
        try:
            steps = fn(s, d)
        except Exception as e:
            print(f"   ❌ {name:<22} упал: {type(e).__name__}: {e}")
            all_ok = False
            continue
        print(f"\n[{name}]")
        for label, ok in steps:
            mark = "✅" if ok else "❌"
            print(f"   {mark} {label}")
            all_ok = all_ok and ok
    print(f"\nИтого: {'✅ ПУЛЬТ жив: ШТАБ → КОМАНДИР → рельсы d/c · RUBICON-слово · движок не стартовал' if all_ok else '❌ есть падения'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · ИНТЕРАКТИВ — ЖИВОЙ ДЫМ НА PTY (raw-клавиатура, реальный терминал).

Зачем: DH-приёмка гоняет меню строками (StringIO), но живой путь — стрелки/цифры в
raw-режиме на настоящем tty. `script` не доставляет piped-stdin в pty-slave reads,
поэтому дравер сам делает pty.fork() и шлёт клавиши как настоящий пользователь.

Сценарии (0₽, read-only, реальные сторы с диска):
  S1 дом_стрелки   — socc home → ↓+Enter выбирает ЯМ → q → q (выход rc 0)
  S2 ям_витрина    — socc ym → цифра=витрина → АКТИВНЫЕ ЗАДАНИЯ → 1=ЖИВОЙ ЭКРАН
                      (≥2 авто-кадра) → q → q → q (выход rc 0)

Запуск:  python3 scripts/socc/socc_dom_pty_smoke_v1.py   (нужен tty-запуск не обязателен;
          дравер сам создаёт pty; в CI/пайпе тоже работает — это его суть)
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
        # размер окна, чтобы _width() работал как в настоящем терминале
        fcntl.ioctl(master, termios.TIOCSWINSZ,
                    struct.pack("HHHH", rows, cols, 0, 0))
        self.pid, self.master = pid, master
        self.buf = b""
        self.cursor = 0
        self.done = False

    def _fill(self, timeout=0.2):
        """Читаем, что пришло от ребёнка."""
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

    def _txt(self):
        return _ANSI.sub(b"", self.buf)[self.cursor:].decode("utf-8", "replace")

    def send(self, data):
        os.write(self.master, data)

    def wait_for(self, text, timeout=15.0):
        """Ждём текст ПОСЛЕ курсора; курсор двигаем к концу совпадения."""
        needle = text if isinstance(text, bytes) else text.encode()
        deadline = time.time() + timeout
        while time.time() < deadline:
            hit = needle in self.buf[self.cursor:]
            if hit:
                idx = self.buf.find(needle, self.cursor)
                self.cursor = idx + len(needle)
                return True
            self._fill(0.3)
            if self.done:
                break
        return False

    def frames(self):
        """Сколько раз ребёнок перерисовал экран (clear-код) всего."""
        return self.buf.count(b"\x1b[2J")

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
            if pid != 0:  # ребёнок убран
                return os.waitstatus_to_exitcode(status)
            self._fill(0.3)
        return None


class T:
    """Один шаг дыма с пинг-понгом клавиш."""

    def __init__(self, name, argv):
        self.name, self.argv = name, argv

    def run(self):
        raise NotImplementedError


def _socc(argv):
    """Команда ребёнка: канонический `socc` если есть, иначе python-модуль дома."""
    exe = shutil.which("socc")
    if exe:
        return [exe] + list(argv)
    return [sys.executable, str(SOCC_ROOT / "socc_cli" / "home.py")] + list(argv)


def s1_dom_strelki():
    steps = []
    p = Pty(_socc(["home"]))
    try:
        ok = p.wait_for("SOCC · ДОМ")
        steps.append(("старт: меню дома", ok))
        # ↓ с ЯМ-ЦИКЛ? sel=0(kernel) → ↓ = 1(ym) → Enter открывает
        p.send(b"\x1b[B")
        time.sleep(0.2)
        p.send(b"\r")
        ok = p.wait_for("магазинов в манифесте")
        steps.append(("↓+Enter → меню ЯМ", ok))
        # назад в дом
        p.send(b"q")
        ok = p.wait_for("SOCC · ДОМ")
        steps.append(("q → обратно в дом", ok))
        p.send(b"q")
        rc = p.exitcode()
        steps.append((f"выход rc=0", rc == 0))
        return steps
    finally:
        p.close()


def s2_ym_vitrina():
    steps = []
    p = Pty(_socc(["ym"]))
    try:
        ok = p.wait_for("магазинов в манифесте")
        steps.append(("старт: меню ЯМ (счёт)", ok))
        # первая витрина цифрой 1
        p.send(b"1")
        ok = p.wait_for("АКТИВНЫЕ ЗАДАНИЯ")
        steps.append(("цифра=1 → экран витрины + ЗАДАНИЯ", ok))
        # действие 1 = ЖИВОЙ ЭКРАН магазина (маркер «· ЖИВОЙ» — только шапка live)
        p.send(b"1")
        ok = p.wait_for(" · ЖИВОЙ")
        steps.append(("цифра=1 → живой экран", ok))
        base = p.frames()
        time.sleep(2.6)
        p._fill(0.4)
        grew = p.frames() >= base + 1
        steps.append((f"авто-кадры (было {base} → {p.frames()})", grew))
        # выходим из живого → меню витрины (маркер «ДЕЙСТВИЯ» есть только в меню,
        # не в live-кадре; курсор уже прошёл старое меню — значит это новый кадр)
        p.send(b"q")
        ok = p.wait_for("ДЕЙСТВИЯ")
        steps.append(("q → назад к меню витрины", ok))
        p.send(b"q")
        ok = p.wait_for("магазинов в манифесте")
        steps.append(("q → назад к магазинам", ok))
        p.send(b"q")
        rc = p.exitcode()
        steps.append((f"выход rc={rc}", rc == 0))
        return steps
    finally:
        p.close()


def main():
    print("🖥️  SOCC · ДОМ · ИНТЕРАКТИВ · ЖИВОЙ ДЫМ НА PTY (raw-клавиатура, 0₽)")
    all_ok = True
    for name, fn in (("S1 дом_стрелки", s1_dom_strelki),
                     ("S2 ям_витрина", s2_ym_vitrina)):
        try:
            steps = fn()
        except Exception as e:
            print(f"   ❌ {name:<14} упал: {type(e).__name__}: {e}")
            all_ok = False
            continue
        print(f"\n[{name}]")
        for label, ok in steps:
            mark = "✅" if ok else "❌"
            print(f"   {mark} {label}")
            all_ok = all_ok and ok
    print(f"\nИтого: {'✅ ЖИВОЙ путь работает (меню → стрелки/цифры → витрина → live)' if all_ok else '❌ есть падения'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

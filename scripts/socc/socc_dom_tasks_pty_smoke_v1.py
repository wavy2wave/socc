#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · ЗАДАНИЯ — ЖИВОЙ ДЫМ НА PTY (raw-клавиши, реальный `socc задания`).

Зачем: TX-приёмка гоняет лицо строками (StringIO/инъекция), а ЖИВОЙ путь ЗАДАНИЯ —
raw-клавиши на настоящем tty поверх реального канон-стора (как ЭКО/дом pty-дымы).
Оператор: «бесит когда говорят исправлено а на деле нет — фейк пасс»; поэтому лицо
проверяется на ПЛОСКОСТИ, которую он видит: терминал. Дравер сам делает pty.fork()
и шлёт клавиши как человек (движок view/alt-screen, как PU/дом pty-дымы).

Что гоняем (0₽, движок НЕ стартует НИ РАЗУ — PASS/DRY_OK нет в буфере):
  T1 живой_вход_и_карточка — `socc задания` (tty) → кадр меню-реестра
      «ЗАДАНИЯ · ДОМ» (сводка органа «записей N») → первая задача по важности
      (sort_tasks) видна → цифра 1 → КАРТОЧКА «ЗАДАНИЕ · T-…» (пункты ○, read 0₽)
      → q → реестр → q → выход rc 0 (ВЫХОД-КОД: корень ЗАДАНИЯ = 0, как run_home;
      раньше "back" улетал в sys.exit("back") = код 1 — ловим регресс)
  T2 стабильный_кадр_80×24 — на РОВНО 80×24: меню-реестр и карточка; каждый кадр
      стабилен (низ на \x1b[24;1H, внутри кадра нет `\n` (view CUP-ряды), за 24
      не лезет) → q-цепочка до rc 0 (движок не звался)

Честный guard (T0): реальный стор пуст/ещё нет — живой дым честно показывает ветку
«открытых нет / реестр ещё нет» и q до rc 0; карточку не выдумываем.

Запуск:  python3 scripts/socc/socc_dom_tasks_pty_smoke_v1.py
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
ARB = SOCC_ROOT / "scripts/mint/arbiter"
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))


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

    def last_frame(self):
        """Хвост от последней отрисовки кадра (начинается с CUP-1;1)."""
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


def _real_face():
    """Честная картина КАНОН-стора (read-only, орган) → (kind, total, first).

    kind ∈ "ok" | "missing" (файла нет) | "error" (битый) | "empty" (0 открытых).
    first — (id, what-prefix) первой открытой по важности (sort_tasks органа) — ТА
    САМАЯ, что увидит оператор на строке «1». Ничего не пишем, движок не зовём (0₽).
    """
    try:
        import ymarket_tasks_v1 as T
        p = T.task_path()
        if not p.exists():
            return "missing", 0, None
        tasks, err = T.load(path=p)
        if err:
            return "error", 0, None
        total = len(tasks)
        op = T.sort_tasks(T.open_only(tasks))
        if not op:
            return "empty", total, None
        f = op[0]
        prefix = f.get("what", "")[:24].strip() or f.get("id", "T-")
        return "ok", total, (f.get("id"), prefix)
    except Exception:
        return "error", 0, None


def t1_vhod_i_kartochka(total, first_id, first_what):
    """Живой путь: меню-реестр → карточка первой задачи → q-цепочка rc 0."""
    steps = []
    p = Pty(_socc(["задания"]))
    try:
        ok = p.wait_for("ЗАДАНИЯ · ДОМ")
        steps.append(("старт: `socc задания` → кадр меню-реестра", ok))
        ok = p.wait_for(f"записей {total}")
        steps.append((f"в кадре сводка органа «записей {total}»", ok))
        ok = p.wait_for(first_what)
        steps.append(("первая задача по важности (sort_tasks) видна строкой", ok))
        ok = p.wait_for("цифра / Enter — карточка")
        steps.append(("подсказка меню: «цифра / Enter — карточка»", ok))
        p.send(b"1")
        ok = p.wait_for(f"ЗАДАНИЕ · {first_id}")
        steps.append((f"цифра 1 → карточка «ЗАДАНИЕ · {first_id}»", ok))
        ok = p.wait_for("read 0₽") and p.wait_for("○")
        steps.append(("в карточке: read 0₽ и пункт ○ (не выдуманный) видны", ok))
        p.send(b"q")
        ok = p.wait_for("цифра / Enter — карточка")
        steps.append(("q → назад в меню-реестр", ok))
        p.send(b"q")
        rc = p.exitcode()
        no_exec = b"PASS/DRY_OK" not in p.buf
        steps.append((f"выход rc={rc} · движок НЕ звался · корень = 0 (не 'back')",
                      rc == 0 and no_exec))
        return steps
    finally:
        p.close()


def t2_stabilnyi_kadr_80x24(first_id):
    """ЗАДАНИЯ на РОВНО 80×24 (сторож СТАБИЛЬНОГО КАДРА): реестр и карточка —
    низ на \x1b[24;1H, внутри нет `\n`, за 24 не лезет. q-цепочка до rc 0."""
    steps = []
    p = Pty(_socc(["задания"]), cols=80, rows=24)
    try:
        def _fr_ok(tag):
            fr = p.last_frame()
            ok_row = b"\x1b[24;1H" in fr
            ok_nl = b"\n" not in fr
            ok_row_high = b"\x1b[25;1H" not in fr
            steps.append((f"{tag} 80×24: низ 24;1H ({ok_row}) · без \\n ({ok_nl}) · "
                          f"за 24 не лезет ({ok_row_high})",
                          ok_row and ok_nl and ok_row_high))
        ok = p.wait_for("ЗАДАНИЯ · ДОМ")
        steps.append(("старт: меню-реестр ЗАДАНИЯ на 80×24", ok))
        _fr_ok("меню-реестр")
        ok = p.wait_for("цифра / Enter — карточка")
        steps.append(("реестр: подсказка «в карточку» видна", ok))
        p.send(b"1")
        ok = p.wait_for(f"ЗАДАНИЕ · {first_id}")
        steps.append((f"цифра 1 → карточка «ЗАДАНИЕ · {first_id}» на 80×24", ok))
        _fr_ok("карточка задания")
        ok = p.wait_for("read 0₽") and p.wait_for("○")
        steps.append(("карточка: read 0₽ и пункт виден", ok))
        p.send(b"q")
        ok = p.wait_for("цифра / Enter — карточка")
        steps.append(("q → назад в меню-реестр", ok))
        _fr_ok("реестр после карточки")
        p.send(b"q")
        rc = p.exitcode()
        no_exec = b"PASS/DRY_OK" not in p.buf
        steps.append((f"выход rc={rc} · движок НЕ звался", rc == 0 and no_exec))
        return steps
    finally:
        p.close()


def t0_chestno_pusto(needle):
    """Стор пуст/нет/битый → честная ветка (не выдумываем карточку) → q → rc 0."""
    steps = []
    p = Pty(_socc(["задания"]))
    try:
        ok = p.wait_for("ЗАДАНИЯ · ДОМ")
        steps.append(("старт: кадр ЗАДАНИЯ · ДОМ", ok))
        ok = p.wait_for(needle)
        steps.append((f"честно: «{needle}» (никакой карточки-фейка)", ok))
        p.send(b"q")
        rc = p.exitcode()
        no_exec = b"PASS/DRY_OK" not in p.buf
        steps.append((f"выход rc={rc} · движок НЕ звался", rc == 0 and no_exec))
        return steps
    finally:
        p.close()


def main():
    print("📋 SOCC · ДОМ · ЗАДАНИЯ (топливо) · ЖИВОЙ ДЫМ НА PTY (0₽, движок не стартует)")
    kind, total, first = _real_face()
    all_ok = True
    if kind == "ok":
        print(f"   канон-реестр: {total} записей · первая открытая {first[0]} "
              f"(префикс «{first[1]}…»)")
        scenarios = [("T1 вход_и_карточка", t1_vhod_i_kartochka, total, first[0], first[1]),
                     ("T2 стабильный_кадр_80×24", t2_stabilnyi_kadr_80x24, first[0])]
    else:
        if kind == "missing":
            note, needle = "канон-стора ЗАДАНИЯ нет", "реестр ещё нет"
        elif kind == "error":
            note, needle = "канон-стор битый", "реестр битый"
        else:
            note, needle = "открытых 0", "открытых нет"
        print(f"   ⚠ {note} — гоняю честную ветку «{needle}»")
        scenarios = [("T0 честно_нечего_листать", t0_chestno_pusto, needle)]
    for item in scenarios:
        name, fn = item[0], item[1]
        try:
            steps = fn(*item[2:])
        except Exception as e:
            print(f"   ❌ {name:<22} упал: {type(e).__name__}: {e}")
            all_ok = False
            continue
        print(f"\n[{name}]")
        for label, ok in steps:
            mark = "✅" if ok else "❌"
            print(f"   {mark} {label}")
            all_ok = all_ok and ok
    print(f"\nИтого: {'✅ ЗАДАНИЯ живёт на tty: реестр → карточка · кадр 80×24 стабилен · rc 0 · движок не стартовал' if all_ok else '❌ есть падения'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · ЭКОСИСТЕМА магазина — ЖИВОЙ ДЫМ НА PTY (raw-клавиши, реальный `socc`).

Зачем: EC-приёмка гоняет навигатор строками (StringIO, инъекция payload), а живой
путь ЭКО — raw-клавиши на настоящем tty поверх реального `socc`: из ДОМА магазина
цифра ЭКО → кадр «ЭКОСИСТЕМА · slug» → провал в секцию → в ЦИКЛЫ провал в прогон
= его отчёт/логи → q-цепочка назад до rc 0. Дравер сам делает pty.fork() и шлёт
клавиши как человек (движок view/alt-screen, как в PU/дом pty-дымах).

Цифры считаются динамически: пункт магазина в меню ЯМ — из ym_rows; цифра ЭКО в
ДЕЙСТВИЯХ витрины — из исходника dom (_run_store_tty buttons); цифры секций — из
eco._SECTIONS. Хардкода нет — дым не ломается при росте меню.

Сценарии (0₽, движок НЕ стартует НИ РАЗУ — на рельсах/запусках Enter не жмём):
  E1 навигатор_вход — socc ym → магазин → цифра ЭКО → кадр «ЭКОСИСТЕМА · slug»
                      (навигатор 5 секций + пункт «Назад») → q → ДОМ кампании →
                      q → меню ЯМ → q → выход rc 0
  E2 провал_задания_и_циклы — из навигатора цифра ЗАДАНИЯ → кадр раздела (РЕЕСТР·
                      DURABLE / НАБЛЮДЕНИЯ) → q → цифра ЦИКЛЫ → список прогонов →
                      провал в прогон → кадр «ЦИКЛ · отчёт прогона» (узлы сухо/
                      ЖИВОЙ + evidence) → q-цепочка до rc 0
  E3 стабильный_кадр_80×24 — на РОВНО 80×24: навигатор → ЗАДАНИЯ → ЦИКЛЫ → отчёт
                      прогона; каждый кадр стабилен (низ \x1b[24;1H, без \n внутри,
                      за 24 не лезет) → q-цепочка до rc 0 (движок не звался)

Запуск:  python3 scripts/socc/socc_dom_eco_pty_smoke_v1.py
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


def _store_digit():
    """Цифра пункта первого магазина в меню ЯМ (динамически из ym_rows)."""
    from socc_cli import dom as D
    items = [r for r in D.ym_rows(D._stores_map()) if r.get("kind") == "item"]
    for n, r in enumerate(items, 1):
        if r.get("action", "").startswith("store:"):
            return n if n <= 9 else None
    return None


def _tty_button_digit(target):
    """Цифра кнопки ДЕЙСТВИЙ витрины (напр. ЭКО) — из исходника dom, не хардкод."""
    src = (SOCC_ROOT / "socc_cli" / "dom.py").read_text(encoding="utf-8")
    start = src.find("def _run_store_tty")
    if start < 0:
        return None
    nxt = src.find("\ndef ", start + 1)
    region = src[start:nxt if nxt > 0 else None]
    i = region.find("buttons = [")
    if i < 0:
        return None
    tail = region[i + len("buttons = ["):]
    j = tail.find("]")  # закрывающая ] списка кнопок (вложенности нет)
    tail = tail[:j] if j >= 0 else tail
    n = 0
    for m in re.finditer(r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', tail):
        n += 1
        if m.group(1) == target:
            return n if n <= 9 else None
    return None


def _sec_digit(key):
    """Цифра секции ЭКО-навигатора (ЗАДАНИЯ/ЦИКЛЫ/…) из eco._SECTIONS."""
    from socc_cli import eco as Eco
    for n, (k, _lab) in enumerate(Eco._SECTIONS, 1):
        if k == key:
            return n if n <= 9 else None
    return None


def e1_navigator_vhod(slug, store_d, eco_d):
    steps = []
    p = Pty(_socc(["ym"]))
    try:
        ok = p.wait_for("магазинов в манифесте")
        steps.append(("старт: меню ЯМ", ok))
        p.send(str(store_d).encode())
        ok = p.wait_for("ЭКО = разделы магазина")  # hint ДЕЙСТВИЙ витрины
        steps.append((f"цифра {store_d} → ДОМ ЯМ-ЦИКЛ · {slug}", ok))
        p.send(str(eco_d).encode())
        ok = p.wait_for(f"ЭКОСИСТЕМА · {slug}")
        steps.append((f"цифра {eco_d} (ЭКО) → кадр ЭКОСИСТЕМА", ok))
        # кадр рисуется сверху вниз: заголовок → пункты → подсказка. Проверяем в
        # порядке отрисовки, иначе курсор уходит мимо уже нарисованных строк.
        ok = p.wait_for("Назад к ДОМУ ЯМ-ЦИКЛ")
        steps.append(("навигатор: 5 секций + пункт «Назад» виден", ok))
        ok = p.wait_for("цифра / Enter — в раздел")
        steps.append(("навигатор: подсказка «в раздел»", ok))
        # футер-резерв «ЗАКАЗЫ — проектируется» живёт в ПЛОСКОМ листе (EC1);
        # на живом кадре навигатор = pick: секции + пункт «Назад к ДОМУ».
        p.send(b"q")
        ok = p.wait_for(f"ДОМ ЯМ-ЦИКЛ · {slug}")
        steps.append(("q → назад в ДОМ кампании", ok))
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


def e2_zadania_tsikly(slug, store_d, eco_d, zad_d, cyc_d):
    steps = []
    p = Pty(_socc(["ym"]))
    try:
        ok = p.wait_for("магазинов в манифесте")
        steps.append(("старт: меню ЯМ", ok))
        p.send(str(store_d).encode())
        ok = p.wait_for("ЭКО = разделы магазина")
        steps.append((f"цифра {store_d} → ДОМ ЯМ-ЦИКЛ · {slug}", ok))
        p.send(str(eco_d).encode())
        ok = p.wait_for(f"ЭКОСИСТЕМА · {slug}")
        steps.append(("цифра ЭКО → навигатор", ok))

        # провал ЗАДАНИЯ
        p.send(str(zad_d).encode())
        ok = p.wait_for(f"ЭКОСИСТЕМА · {slug} · ЗАДАНИЯ")
        steps.append((f"цифра {zad_d} → раздел ЗАДАНИЯ", ok))
        ok = p.wait_for("РЕЕСТР · DURABLE") or p.wait_for("НАБЛЮДЕНИЯ · ЖИВАЯ ОЧЕРЕДЬ")
        steps.append(("в разделе: РЕЕСТР/НАБЛЮДЕНИЯ видны", ok))
        p.send(b"q")
        ok = p.wait_for("цифра / Enter — в раздел")
        steps.append(("q → назад в навигатор", ok))

        # провал ЦИКЛЫ → список прогонов → прогон = отчёт/логи
        p.send(str(cyc_d).encode())
        ok = p.wait_for("провал в прогон = его отчёт/логи")
        steps.append((f"цифра {cyc_d} → ЦИКЛЫ (список прогонов)", ok))
        p.send(b"1")  # первый прогон (в реальном леджере он есть — см. main)
        ok = p.wait_for(f"ЦИКЛ · отчёт прогона · {slug}")
        steps.append(("провал в прогон → кадр «ЦИКЛ · отчёт прогона»", ok))
        # «ПРОГОН» = шапка отчёта, «сухо» = строки узлов — проверяем в порядке
        # отрисовки (шапка выше узлов), иначе курсор перепрыгивает ПРОГОН.
        ok = p.wait_for("ПРОГОН") and p.wait_for("сухо")
        steps.append(("в отчёте: шапка ПРОГОН и узлы сухо видны", ok))
        p.send(b"q")
        ok = p.wait_for("провал в прогон = его отчёт/логи")
        steps.append(("q → назад к списку прогонов", ok))
        p.send(b"q")
        ok = p.wait_for("цифра / Enter — в раздел")
        steps.append(("q → назад в навигатор", ok))
        p.send(b"q")
        ok = p.wait_for(f"ДОМ ЯМ-ЦИКЛ · {slug}")
        steps.append(("q → назад в ДОМ кампании", ok))
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


def e3_navigator_80x24(slug, store_d, eco_d, zad_d, cyc_d):
    """ЭКО на РОВНО 80×24 (сторож СТАБИЛЬНОГО КАДРА как P3/дом-дымы): навигатор →
    ЗАДАНИЯ → ЦИКЛЫ → отчёт прогона. Каждый кадр стабилен: низ на \x1b[24;1H,
    внутри кадра нет `\n` (движок view, CUP-ряды), ничего не вылезает за 24 ряда.
    q-цепочка до rc 0; движок ни разу не зовётся (в буфере нет PASS/DRY_OK)."""
    steps = []
    p = Pty(_socc(["ym"]), cols=80, rows=24)
    try:
        def _fr_ok(tag):
            fr = p.last_frame()
            ok_row = b"\x1b[24;1H" in fr
            ok_nl = b"\n" not in fr
            ok_row_high = b"\x1b[25;1H" not in fr
            steps.append((f"{tag} 80×24: низ 24;1H ({ok_row}) · без \\n ({ok_nl}) · "
                          f"за 24 не лезет ({ok_row_high})",
                          ok_row and ok_nl and ok_row_high))
        ok = p.wait_for("магазинов в манифесте")
        steps.append(("старт: меню ЯМ на 80×24", ok))
        p.send(str(store_d).encode())
        ok = p.wait_for("ЭКО = разделы магазина")
        steps.append((f"цифра {store_d} → ДОМ ЯМ-ЦИКЛ · {slug}", ok))
        _fr_ok("ДОМ магазина")
        p.send(str(eco_d).encode())
        ok = p.wait_for(f"ЭКОСИСТЕМА · {slug}")
        steps.append((f"цифра {eco_d} (ЭКО) → навигатор", ok))
        _fr_ok("навигатор")
        p.send(str(zad_d).encode())
        ok = p.wait_for(f"ЭКОСИСТЕМА · {slug} · ЗАДАНИЯ")
        steps.append((f"цифра {zad_d} → раздел ЗАДАНИЯ", ok))
        _fr_ok("раздел ЗАДАНИЯ")
        p.send(b"q")
        ok = p.wait_for("цифра / Enter — в раздел")
        steps.append(("q → назад в навигатор", ok))
        p.send(str(cyc_d).encode())
        ok = p.wait_for("провал в прогон = его отчёт/логи")
        steps.append((f"цифра {cyc_d} → ЦИКЛЫ (список прогонов)", ok))
        _fr_ok("ЦИКЛЫ список")
        p.send(b"1")  # первый прогон (в реальном леджере он есть — см. main)
        ok = p.wait_for(f"ЦИКЛ · отчёт прогона · {slug}")
        steps.append(("провал в прогон → кадр «ЦИКЛ · отчёт прогона»", ok))
        ok = p.wait_for("ПРОГОН") and p.wait_for("сухо")
        steps.append(("в отчёте: шапка ПРОГОН и узлы сухо видны", ok))
        _fr_ok("отчёт прогона")
        p.send(b"q")
        ok = p.wait_for("провал в прогон = его отчёт/логи")
        steps.append(("q → назад к списку прогонов", ok))
        p.send(b"q")
        ok = p.wait_for("цифра / Enter — в раздел")
        steps.append(("q → назад в навигатор", ok))
        p.send(b"q")
        ok = p.wait_for(f"ДОМ ЯМ-ЦИКЛ · {slug}")
        steps.append(("q → назад в ДОМ кампании", ok))
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
    print("🌱 SOCC · ДОМ · ЭКОСИСТЕМА магазина · ЖИВОЙ ДЫМ НА PTY (0₽, движок не стартует)")
    from socc_cli import dom as D
    stores = D._stores_map()
    slug = next(iter(sorted(stores)), None)
    store_d = _store_digit()
    eco_d = _tty_button_digit("eco:store")
    if eco_d is None:
        print("   ❌ не нашёл кнопку ЭКО в ДЕЙСТВИЯХ витрины (исходник dom)")
        return 1
    if slug is None:
        print("   ⚠ манифест витрин пуст — дымы требуют витрину; ничего не гоняю")
        return 1
    zad_d, cyc_d = _sec_digit("задания"), _sec_digit("циклы")
    if zad_d is None or cyc_d is None:
        print("   ❌ не нашёл секции ЗАДАНИЯ/ЦИКЛЫ в eco._SECTIONS")
        return 1
    # E2 требует хотя бы один прогон в леджере (иначе ЦИКЛЫ — честный «прогонов нет»)
    ledger = D.store_payload(slug).get("ledger", [])
    n_runs = 0
    cur = None
    for r in ledger:
        if r.get("node") == "ДОНОР":
            n_runs += 1
    print(f"   магазин {slug} · ЭКО = цифра {eco_d} · ЗАДАНИЯ = {zad_d} · "
          f"ЦИКЛЫ = {cyc_d} · прогонов в леджере {n_runs}")
    all_ok = True
    scenarios = [("E1 навигатор_вход", e1_navigator_vhod, slug, store_d, eco_d)]
    if n_runs:
        scenarios.append(("E2 провал_задания_и_циклы", e2_zadania_tsikly,
                          slug, store_d, eco_d, zad_d, cyc_d))
        scenarios.append(("E3 стабильный_кадр_80×24", e3_navigator_80x24,
                          slug, store_d, eco_d, zad_d, cyc_d))
    else:
        print("   ⚠ леджер пуст — E2/E3 (провал в прогон) пропущены честно (нет прогонов)")
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
    print(f"\nИтого: {'✅ ЭКО жив: навигатор → секции → отчёты прогонов · движок не стартовал' if all_ok else '❌ есть падения'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

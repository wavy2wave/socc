#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · viewport-движок (socc_cli/view.py) — stdlib-only, read 0₽.

Стабильный фиксированный экран вместо «плывущих» кадров. Вывод НИЧЕГО не пишет
на диск, сеть не зовёт (DH8/HH6-паттерн сохраняется и здесь).

Почему «плыло» (диагноз на 80×24 pty): кадры были длиннее экрана (меню витрины
29 строк / live 33 на 24 строки → низ — действия/подсказка/таймер — уходил за
кадр), _snip(84/90) длиннее ширины колонки → терминал переносил строки, а старый
вывод каждый кадр гасил экран `\x1b[2J` и перепечатывал ВЕСЬ кадр подряд `\n` —
в raw-режиме LF без CR «плывёт» вправо-вниз.

Движок (adopted архитектура «one fixed canvas, autowrap-off»):
  - ОДИН alt-screen на виджет (вход/выход виджета); авто-обновление без 2J.
  - Автоперенос ВЫКЛЮЧЕН (`?7l`) на всё время сессии → даже ошибка измерения
    ширины никогда не даст фантомный перенос.
  - Каждый кадр = ровно ROWS строк, каждый ряд адресуется абсолютно
    (`\x1b[{r};1H`), с конца строки стирается хвост (`\x1b[K`), `\n` ВНУТРИ кадра
    НЕТ → терминал физически не может проскроллить/съехать.
  - Ширина: замер по клеткам (CJK/эмодзи = 2), обрезка КОЛОРИЗОВАННОЙ строки без
    разрезания ANSI-последовательностей; ошибка замера не переносится (wrap off).
  - Геометрия постоянна на всех режимах: шапка 4 + пробел 1 + низ 3 → тело всегда
    rows-8; кадры не «прыгают» по высоте между экранами.

Плоский путь (пайп/StringIO/--text) НЕ трогается: всё это живёт только в tty.
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata

# ── минимальный набор ANSI (единственные escape-последовательности движка) ────
ENTER_ALT = "\x1b[?1049h"   # перейти в альтернативный буфер (+сохранить курсор)
LEAVE_ALT = "\x1b[?1049l"   # вернуть основной буфер (промпт шелла как был)
HIDE_CUR = "\x1b[?25l"
SHOW_CUR = "\x1b[?25h"
WRAP_OFF = "\x1b[?7l"        # автоперенос выключен на время кадра
WRAP_ON = "\x1b[?7h"
CLEAR = "\x1b[2J\x1b[H"      # только на входе в виджет (не в цикле перерисовки)
RESET = "\x1b[0m"
EOL = "\x1b[K"               # стереть до конца строки (чистит «хвост» старых кадров)

_CSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def geom():
    """Размер терминала (rows, cols) — никогда не падает.

    Обратный порядок полей os.get_terminal_size: columns, lines.
    """
    try:
        sz = os.get_terminal_size()
        return sz.lines, sz.columns
    except OSError:
        pass
    try:
        cols = int(os.environ.get("COLUMNS", "0") or 0)
    except Exception:
        cols = 0
    try:
        rows = int(os.environ.get("LINES", "0") or 0)
    except Exception:
        rows = 0
    if cols <= 0:
        cols = 80
    if rows <= 0:
        rows = 24
    return rows, cols


def _viable(cols, rows):
    """Кадр имеет смысл только на достаточно широком/высоком экране."""
    return cols >= 70 and rows >= 14


def wcell(ch):
    """Ширина ОДНОЙ клетки терминала для символа (никогда не занижаем эмодзи)."""
    o = ord(ch)
    if o == 0x200D:
        return 0                        # ZWJ (соединяет эмодзи-семьи)
    if 0xFE00 <= o <= 0xFE0F:
        return 0                        # variation selectors
    if 0x300 <= o <= 0x36F or 0x20D0 <= o <= 0x20FF:
        return 0                        # combining-диакритика
    if o >= 0x10000:
        return 2                        # non-BMP (эмодзи 🛍🧭… — 2 клетки)
    if 0x1F000 <= o <= 0x1FAFF:
        return 2                        # BMP-пиктограммы
    e = unicodedata.east_asian_width(ch)
    return 2 if e in "WF" else 1        # ambiguous 'A' (Ж ● «» ╔ ✓) → 1


def wlen(text):
    return sum(wcell(c) for c in text)


def clip_ansi(s, width):
    """Обрезать ОТОБРАЖАЕМУЮ строку до `width` клеток; ANSI не режется.

    Идём по кодовым точкам: управляющая/цветовая последовательность даёт 0
    ширины (сохраняется целиком), печатные символы складываются по клеткам.
    При обрезке дописываем RESET + «…» и НЕ разрываем широкий символ.
    """
    if width <= 0:
        return "…" if s else ""
    out, w, cut = [], 0, False
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch == "\x1b":
            m = _CSI.match(s, i)
            if m:
                out.append(m.group(0))
                i = m.end()
                continue
            i += 1
            continue
        cw = wcell(ch)
        if w + cw > width:
            cut = True
            break
        w += cw
        out.append(ch)
        i += 1
    res = "".join(out)
    if cut:
        res += RESET + "…"
    return res


def paint(out, cells):
    """Полная перерисовка: ровно rows рядов, каждый — CUP+строка+EOL.

    cells — список строк-клеток (может быть короче rows: недостающие добиваются
    пустыми). Ни одного `\n` внутри кадра → терминал не скроллит и не плывёт.
    Кадр различим по байту CUP первого ряда `\x1b[1;1H` — его счётчик pty-дыма
    считает перерисовки (2J в цикле больше нет).
    """
    rows, cols = geom()
    cw = max(10, cols - 2)
    cells = (list(cells) + [""] * rows)[:rows]
    buf = []
    for r in range(rows):
        buf.append("\x1b[%d;1H" % (r + 1) + clip_ansi(cells[r], cw) + RESET + EOL)
    out.write("".join(buf))
    out.flush()


def enter(out, inp):
    """Войти в alt-screen + raw. Возвращает (fd, old_termios) для выхода."""
    import termios
    import tty as _tty
    fd = inp.fileno()
    old = termios.tcgetattr(fd)
    _tty.setraw(fd)
    out.write(ENTER_ALT + HIDE_CUR + WRAP_OFF + CLEAR)
    out.flush()
    return fd, old


def leave(out, fd, old):
    """Выйти из alt-screen + raw (всегда в finally; порядок важен)."""
    try:
        out.write(RESET + SHOW_CUR + WRAP_ON + LEAVE_ALT)
        out.flush()
    except Exception:
        pass
    try:
        if old is not None:
            import termios
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass

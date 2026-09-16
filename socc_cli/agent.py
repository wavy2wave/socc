#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · АГЕНТ — живой экран в духе Claude Code (socc_cli/agent.py).

Оператор: «сделай интерфейс как у Claude Code, где система реально работает
(думает и проч) — весь интерфейс как у Claude». АГЕНТ = строка ввода, а система
видимо «думает» и по-настоящему делает: сухие прогоны ЦИКЛ-1 (0₽) и живые ответы
из реального стора. Ничего не выдумываем: думаю-блок — это честный план шага,
вердикты — настоящие.

Почему это НЕ «плывёт»: АГЕНТ живёт в обычном терминале (cooked, scrollback) —
никаких alt-screen/сырых кадров. Каждая строка печатается один раз, перенос и
прокрутку делает сам терминал → физически нечему съезжать. Это другое правило,
чем у меню-кадров view.py (там — стабильный кадр), здесь — стабильная лента.

Законы (зачаток §АГЕНТ):
  AG1 лента_честная — каждая печатная строка ≤ ширины экрана; ничего не врём.
  AG2 сухо_по_умолчанию — движок зовём ТОЛЬКО `--dry` (0₽); живое слово → отказ.
  AG3 реальные_вердикты — вердикты = настоящий rc/вывод движка и read стора.
  AG4 не_падает — нет стора/движка → честная строка, не краш (rc 0 на «выход»).

Запуск:   python3 -m socc_cli.agent            (интерактив)
          python3 -m socc_cli.agent --store <slug>
          python3 -m socc_cli.agent --once «прогон»   (одна фраза, для API/дыма)
          echo «статус» | python3 -m socc_cli.agent    (пайп: каждая строка = фраза)
Фразы:    «прогон/цикл/запусти» → сухой прогон ЦИКЛ-1 (реально, 0₽)
          «статус/итог/что нового» → сводка магазина из реального стора
          «полка/витрина/артефакты/опубликовано» → что PUBLISHED (evidence леджера)
          «что умеешь/?» → помощь · «выход/q/хватит» → выход
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

SOCC_ROOT = Path(__file__).resolve().parent.parent
if str(SOCC_ROOT) not in sys.path:
    sys.path.insert(0, str(SOCC_ROOT))

from socc_cli import style as S          # CC8: цвета на tty, plain в пайпе
from socc_cli import view as V           # wlen/clip_ansi — режем до ширины без резки ANSI

ENGINE = SOCC_ROOT / "scripts" / "mint" / "arbiter" / "ymarket_cycle1_v1.py"

# ── классификатор фраз (порядок важен; строки-подстроки) ───────────────────────
_LIVE = ("живой", "в бой", "commit", "--commit", "реальные", "по-настоящему запиши", "оплати")
_CYCLE = ("прогон", "цикл", "запусти", "работай", "крути", "гоняй", "сухой", "dry", "прогнать")
_READ = ("статус", "итог", "отчёт", "что нового", "что видно", "сегодня", "пульс", "дело", "сводка")
_SHELF = ("полка", "витрина", "артефакт", "опубликовано", "published", "evidence", "полку")
_HELP = ("помощь", "умеешь", "help", "?", "что умеешь", "команды")
_EXIT = ("выход", "q", "хватит", "стоп", "пока", "конец", "exit", "quit")

_TINT = [
    (re.compile(r"✗|FAIL|ERR|ошибка"), S.RE),
    (re.compile(r"✓|PASS|ЧИСТ"), S.GR),
    (re.compile(r"DRY|◌|■ DRY"), S.YE),
    (re.compile(r"→|PUBLISHED"), S.CY),
]


def _tint_col(line):
    """Цвет строки движка по доминирующему маркеру (вернёт S-цвет или None)."""
    for rx, col in _TINT:
        if rx.search(line):
            return col
    return S.DIM if line.strip() and line.startswith(" ") else None


def _say(out, line, col=None):
    """Печать строки. На ЖИВОМ терминале — гарантированно ≤ ширины (не плывёт);
    в пайпе/файле строку НЕ режем (терминала нет — нечему переноситься, AG1)."""
    line = str(line)
    maxw = None
    if sys.stdout.isatty():
        try:
            maxw = os.get_terminal_size().columns - 2
        except OSError:
            maxw = None
    if maxw and maxw >= 20 and V.wlen(line) > maxw:
        line = V.clip_ansi(line, maxw)          # сам допишет RESET+«…», ANSI не режет
    out.write(S.c(col, line) if col else line)
    out.write("\n")
    out.flush()


def _banner(out, store):
    _say(out, "")
    _say(out, "SOCC · АГЕНТ — система работает перед тобой", S.B)
    _say(out, f"магазин: {store} · режим: сухо/чтение (0₽) · живой ход — только с твоего слова и с пульта", S.DIM)
    _say(out, "пиши свободно (напр. «прогон», «статус», «что умеешь») · «выход» — закончить", S.DIM)


# ── реальные ответы из стора (0₽, живые на момент вызова) ───────────────────────
def _payload(store):
    from socc_cli import dom as D
    return D, D.store_payload(store)


def _answer_status(out, store):
    D, pl = _payload(store)
    if not pl:
        _say(out, f"манифест {store} пуст/не читается — честно: данных нет", S.YE)
        return
    pulse = pl.get("pulse") or {}
    led = pl.get("ledger") or []
    rv = pulse.get("run_verdicts") or {}
    n_pass = rv.get("PASS", 0)
    n_dry = rv.get("DRY", 0)
    closed = sum(1 for r in led if r.get("node") == "ПЛАНЁРКА")
    failed = sum(1 for r in led if r.get("verdict") == "FAIL")
    live_rows = sum(1 for r in led if r.get("dry") is False)
    queue = pl.get("queue") or []
    reg = pl.get("registry") or ("absent", [])
    _say(out, f"▍{store} · хеш дня {D._cycle_hash(store)}", S.B)
    _say(out, f"прогонов в леджере {len(led)} · закрыто ПЛАНЁРКОЙ {closed} · FAIL {failed}", None)
    _say(out, f"пульс: PASS {n_pass} · DRY {n_dry} · живых строк {live_rows} (0₽ реальных, пока нет dry:false)", None)
    if queue:
        q = queue[0]
        _say(out, f"наблюдение: [{q.get('tag')}] {q.get('what', '')}", S.YE)
    else:
        _say(out, "очередь наблюдений пуста", S.DIM)
    if reg[0] == "absent":
        _say(out, "реестр заданий не материализован (придёт с ЦИКЛ-ДЕНЬ)", S.DIM)


def _answer_shelf(out, store):
    D, pl = _payload(store)
    if not pl:
        _say(out, f"данных по {store} нет", S.YE)
        return
    led = pl.get("ledger") or []
    seen, arts = set(), []
    for r in led:
        for key in ("evidence", "note"):
            txt = r.get(key) or ""
            if isinstance(txt, dict):
                txt = str(txt)
            for m in re.finditer(r"ARB-\d+|P-\d+|[A-Z]{2,4}-\d{5,}", txt):
                tok = m.group(0)
                if "PUBLISHED" in txt and tok not in seen:
                    seen.add(tok)
                    arts.append(tok)
    if arts:
        _say(out, "на витрине PUBLISHED (evidence леджера):", S.B)
        _say(out, " · ".join(dict.fromkeys(arts)), S.GR)
    else:
        _say(out, "артефактов PUBLISHED в леджере не видно — честно", S.DIM)


def _answer_help(out):
    _say(out, "вот что я умею (всё — реально, сухо/чтение, 0₽):", S.B)
    _say(out, "  «прогон»  — запустить сухой прогон ЦИКЛ-1 по магазину (движок, 0₽)", None)
    _say(out, "  «статус»  — сводка магазина из настоящего стора", None)
    _say(out, "  «полка»   — что PUBLISHED на витрине (evidence)", None)
    _say(out, "  «выход»   — закончить", None)


# ── исполнение: настоящий движок, ТОЛЬКО --dry (AG2) ────────────────────────────
def _run_cycle_dry(out, store):
    _say(out, f"думаю: оператор просит работу цикла → шаг: сухой прогон ЦИКЛ-1 по {store} (0₽)", S.DIM)
    _say(out, f"Bash  python3 ymarket_cycle1_v1.py --store {store} --dry", S.MA)
    argv = [sys.executable, str(ENGINE), "--store", store, "--dry"]
    try:
        proc = subprocess.Popen(argv, cwd=str(SOCC_ROOT), text=True, bufsize=1,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception as e:
        _say(out, f"движок не стартовал: {type(e).__name__}: {e}", S.RE)
        return 1
    try:
        for raw in proc.stdout:
            _say(out, raw.rstrip("\n"), _tint_col(raw))
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        _say(out, "остановлен тобой (Ctrl+C) — честно, движок прерван", S.YE)
        return 130
    rc = proc.returncode
    if rc == 0:
        _say(out, f"итог: сухой прогон закончен rc=0 (0₽) — движок жив, вердикты выше", S.GR)
    else:
        _say(out, f"итог: сухой прогон вернул rc={rc} — см. строки выше", S.RE)
    return rc


# ── один ход (фраза → действие) ─────────────────────────────────────────────────
def _handle(out, store, phrase):
    t = (phrase or "").strip().lower()
    if not t:
        _say(out, "напиши что-нибудь (напр. «статус») или «выход»", S.DIM)
        return "ok"
    if any(w in t for w in _EXIT):
        return "exit"
    if any(w in t for w in _CYCLE):
        if any(w in t for w in _LIVE):
            _say(out, "живой ход — только с твоего слова и с пульта (RUBICON); здесь сухо/чтение. Скажи просто «прогон» — сделаю сухой (0₽).", S.YE)
            return "ok"
        _run_cycle_dry(out, store)
        return "ok"
    if any(w in t for w in _SHELF):
        _answer_shelf(out, store)
        return "ok"
    if any(w in t for w in _READ):
        _answer_status(out, store)
        return "ok"
    if any(w in t for w in _HELP):
        _answer_help(out)
        return "ok"
    _say(out, f"не понял «{phrase.strip()}» — вот что умею:", S.YE)
    _answer_help(out)
    return "ok"


def _store_default():
    from socc_cli import dom as D
    stores = D._stores_map()
    return next(iter(sorted(stores)), None)


# ── входы ────────────────────────────────────────────────────────────────────────
def run_agent(out=sys.stdout, inp=None, store=None, once=None):
    """Основной ход. out/inp — как у дом-лиц (StringIO-тестируемо, CC8)."""
    store = store or _store_default()
    if not store:
        _say(out, "манифест витрин пуст — нечего показывать (0₽). Заведи магазин — и вернись.", S.YE)
        return 0
    _banner(out, store)
    if once is not None:
        _handle(out, store, once)
        return 0
    if inp is None:
        inp = sys.stdin
    while True:
        try:
            try:
                line = input("вы › " if sys.stdin.isatty() else "")
            except EOFError:
                break
        except KeyboardInterrupt:
            _say(out, "до встречи.", S.DIM)
            return 0
        if _handle(out, store, line) == "exit":
            _say(out, "до встречи.", S.DIM)
            return 0
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    store, once = None, None
    while argv:
        a = argv.pop(0)
        if a in ("--store", "-s"):
            store = argv.pop(0) if argv else None
        elif a in ("--once", "-o"):
            once = argv.pop(0) if argv else None
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
    return run_agent(store=store, once=once)


if __name__ == "__main__":
    sys.exit(main())

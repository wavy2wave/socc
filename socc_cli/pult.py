#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · ПУЛЬТ ЯМ-ЦИКЛА (socc_cli/pult.py) — живой пульт управления.

Оператор (2026-09-02): «Прорабатывает ЯМ ЦИКЛ, внутри SOCC — строим именно CLI
интерфейс, который И ЕСТЬ наша система. Не просто обёртка, а ЖИВОЙ ПУЛЬТ
управления. Доработай до проф. уровня, чтобы я охуел как создатель. Всё учтено.»

Решения оператора (вилки, зафиксированы):
  1. ПУЛЬТ ИСПОЛНЯЕТ по подтверждению (вариант B): сухой прогон — одно
     подтверждение; живой (--commit) — двойное, слово-магазин на пульте = RUBICON.
  2. ДЕРЖАТЬ ОБА: старый ЖИВОЙ ЭКРАН (dom._live) не тронут — ПУЛЬТ-ШТАБ рядом.

Закон разделения (архитектура, канон):
  - dom.py остаётся ЧИСТЫМ (DH8: ни subprocess, ни write-токенов) — только смотрит
    и зовёт пульт (ленивый импорт, без цикла на уровне модуля).
  - pult.py — ЕДИНСТВЕННЫЙ исполнитель ДОМА. subprocess — только здесь, и только
    НАСТОЯЩЕГО движка ЦИКЛ-1 тем же argv, что БРИГАДИР:
        python3 ymarket_cycle1_v1.py --store <slug> --dry|--commit
    Сам пульт файлы НЕ пишет — пишет движок под словом оператора.
  - Деньги ЧЕСТНО: пока в леджере нет живой строки (dry:false) — «0₽ реальной
    выручки», показываем ЗАКУП → ПОТЕНЦИАЛ ×маржа и PUBLISHED-арт (СВЕРКА).
  - Канон отчётов ARBITER — ТОЛЬКО repo-root MEMORY_WAVE/reports/mint/arbiter
    (сирота scripts/MEMORY_WAVE не затеняет; закон тот же, что ymarket_tasks_v1).

Экраны пульта:
  ПУЛЬТ · ШТАБ ЯМ    — весь флот: витрины по правилу хода КОМАНДИРА ДНЯ
                       (● спокойно · ○ внимание · ⚠ чинить), деньги честно,
                       автопилот/часы дышат сами (idle-тик).
  КОМАНДИР ДНЯ <вит> — провал в витрину: правило хода + деньги + полный ДОМ.
  РЕЛЬС              — d сухой прогон (одно подтверждение) · c живой
                       (RUBICON: введи слово-магазин + Enter) · результат + свежий
                       КОМАНДИР после прогона.
Стабильный кадр — движок socc_cli/view.py (как dom): CUP-ряды, ноль `\n` внутри
кадра, геометрия шапка 5 + низ 3, обрезка клетками без резки ANSI.
"""
from __future__ import annotations

import os
import sys
import select as _select

from socc_cli import view as V
from socc_cli import dom as D

ENGINE_RELPATH = "scripts/mint/arbiter/ymarket_cycle1_v1.py"
_IDLE = 0.8  # секунды между авто-тиками кадра (живой пульт дышит сам)

_HEAT_DOT = {0: ("●", "GR"), 1: ("○", "YE"), 2: ("⚠", "RE")}


def classifier(heat):
    """heat 0=спокойно · 1=внимание · 2=чинить → (знак, цвет-токен)."""
    return _HEAT_DOT.get(int(heat) if heat is not None else 0, ("●", "GR"))


def _num(x):
    """Число → компактно (8.0 → 8)."""
    try:
        f = float(x)
    except Exception:
        return "?"
    return str(int(f)) if f == int(f) else str(round(f, 2))


def _fit(out, line, n=78):
    """Любая строка кадра пульта ≤ n клеток/символов (ANSI не режем)."""
    line = str(line)
    plain = D._ansi_strip(line)
    if not plain:
        return ""
    if len(plain) <= n:
        return line
    if D._tty(out):
        return V.clip_ansi(line, n)
    return plain[: n - 1] + "…"


def _flat_join(out, parts):
    """Склеить плоский кадр: многострочные элементы (лента _band/_seal) разворачиваем
    ПОСТРОЧНО, каждую строку ≤78. Иначе _fit на весь баннер принял бы его за одну
    строку и отрезал бы титул на второй линии — пайп теряет название экрана."""
    lines = []
    for p in parts:
        if isinstance(p, str) and "\n" in p:
            lines.extend(p.split("\n"))
        else:
            lines.append(p)
    return "\n".join(_fit(out, ln) for ln in lines)


# ── деньги ЧЕСТНО (не «заработано», а закуп/потенциал/PUBLISHED) ───────────────
def _money_txt(pl):
    """Строка денег витрины: закуп → потенциал ×маржа · PUBLISHED-арт · живых строк.
    «0₽ реальных» — пока в леджере нет строки dry:false (деньги не выдумываем)."""
    m = D._store_money(pl["store"], pl)
    parts = []
    if m["buy"]:
        bit = f"закуп {m['buy']}₽"
        if m["markup"]:
            bit += f" → потенциал {m['sell']}₽ ×{_num(m['markup'])}"
        parts.append(bit)
    else:
        parts.append("закупа нет — первая партия соберёт")
    parts.append(f"PUBLISHED {m['pub']}" if m["pub"] else "на витрине 0 — СВЕРКА докажет")
    parts.append("0₽ реальных" if not m["live_rows"] else f"живых строк {m['live_rows']}")
    return " · ".join(parts)


def _fleet_money_line(stores=None):
    """Итог по манифесту + честная подпись 0₽ (короткая, влезает в 78)."""
    m = D._fleet_money(stores if stores is not None else D._stores_map())
    if m["buy"]:
        line = f"итог закуп {m['buy']}₽ → потенциал витрин {m['sell']}₽" \
               f" · PUBLISHED {m['pub']}"
    else:
        line = "итог: закупа нет — первая партия соберёт"
    live = 0
    for slug in sorted(stores or {}):
        if D._store_money(slug).get("live_rows"):
            live += 1
    if not live:
        line += " · 0₽ реальных"
    return line


def _ticks_line():
    """Расписание автопилота коротко + ближ. тик (честно по стору launchd)."""
    sched = D._schedule()
    nxt, secs = D._next_run()
    base = f"{len(sched)}×/сут {', '.join(sched)} MSK"
    if nxt:
        tail = f" · след. {nxt.strftime('%H:%M')} через {D._until_txt(secs)}"
        if len(base) + len(tail) <= 44:
            return base + tail
    return base


# ── ШТАБ: витрины по правилу хода ─────────────────────────────────────────────
def fleet_rows(stores=None, now=None):
    """Строки флота: heat убывает (чинить → внимание → спокойно), затем slug."""
    stores = stores if stores is not None else D._stores_map()
    now = now or D._now_msk()
    rows = []
    for slug in sorted(stores or {}):
        pl = D.store_payload(slug)
        heat, word, why = D._next_step(slug, pl, now=now)
        rows.append(dict(slug=slug, heat=int(heat), word=word,
                         why=D._snip(why, 44), money=_money_txt(pl)))
    rows.sort(key=lambda r: (-r["heat"], r["slug"]))
    return rows


def fleet_meta(stores=None, now=None):
    stores = stores if stores is not None else D._stores_map()
    now = now or D._now_msk()
    return dict(today=now.strftime("%Y-%m-%d"), n=len(stores or {}),
                money=_fleet_money_line(stores), ticks=_ticks_line(),
                avto=D._last_tick_fact())


def _row_lines(out, r, idx, sel):
    """Строки одной витрины (главная + деньги под проблемной/выбранной)."""
    dot, col = classifier(r["heat"])
    mark = "▸" if idx == sel else " "
    slug = r["slug"] if len(r["slug"]) <= 20 else r["slug"][:19] + "…"
    main = (mark + " " + D._col(out, col, dot) + " " + slug.ljust(20) + " "
            + D._col(out, "B", r["word"].ljust(10)) + " " + D._snip(r["why"], 38))
    lines = [main]
    if r["heat"] > 0 or idx == sel:
        lines.append(D._col(out, "DIM", "    " + r["money"]))
    return lines


def fleet_body(out, sel=-1, stores=None, now=None, meta=None):
    """Тело ПУЛЬТ-ШТАБ: пролог (витрины/деньги/тики) + ВИТРИНЫ по правилу хода.
    Каждая строка ≤78 (plain). Не окно: окно живёт в tty-кадре пульта."""
    out = out or sys.stdout
    stores = stores if stores is not None else D._stores_map()
    now = now or D._now_msk()
    meta = meta or fleet_meta(stores, now)
    L = []
    L.append(_fit(out, f"  {meta['today']} · витрин: {meta['n']} · {meta['ticks']}"))
    L.append(_fit(out, D._col(out, "DIM", "  " + meta["money"])))
    L.append(D._seal(out, "ВИТРИНЫ · КОМАНДИР ДНЯ (правило хода)"))
    rows = fleet_rows(stores, now)
    if not rows:
        L.append(D._col(out, "DIM", "  манифест пуст — витрины ещё нет (0₽)"))
        return L
    for i, r in enumerate(rows):
        L += _row_lines(out, r, i, sel)
    return [_fit(out, ln) for ln in L]


def fleet_text(out, sel=-1, stores=None, now=None):
    """Полный ПЛОСКИЙ кадр ПУЛЬТ-ШТАБ (пайп/StringIO/--text)."""
    out = out or sys.stdout
    L = [D._band(out, "ПУЛЬТ · ШТАБ ЯМ-ЦИКЛА", right=D._clock(out),
                 sub="живой пульт · смотрит 0₽ · исполняет по слову оператора"),
         ""]
    L += fleet_body(out, sel, stores, now)
    L.append("")
    L.append(D._seal(out, "РЕЛЬС"))
    L.append("  d — сухой прогон ЦИКЛ-1 (0₽) · c — живой (RUBICON · слово оператора)")
    L.append("  Enter на витрине — КОМАНДИР ДНЯ · в пайпе пульт только смотрит")
    return _flat_join(out, L)


# ── КОМАНДИР ДНЯ витрины: правило хода + деньги + полный ДОМ кампании ──────────
def commander_body(out, slug, pl=None, now=None):
    """Провал в витрину: правило КОМАНДИРА сверху, ниже весь ДОМ кампании."""
    out = out or sys.stdout
    pl = pl if pl is not None else D.store_payload(slug)
    now = now or D._now_msk()
    heat, word, why = D._next_step(slug, pl, now=now)
    dot, col = classifier(heat)
    L = []
    L.append(_fit(out, f"  {D._col(out, col, dot)} КОМАНДИР ДНЯ: {word}"))
    L.append(_fit(out, "     " + why))
    L.append(_fit(out, D._col(out, "DIM", "     " + _money_txt(pl))))
    L.append(D._seal(out, "ДОМ КАМПАНИИ (read)"))
    L += [_fit(out, ln) for ln in D._camp_home_text(out, slug, pl, now=now).split("\n")]
    return L


def commander_text(out, slug, pl=None, now=None):
    """Плоский КОМАНДИР ДНЯ (пайп)."""
    out = out or sys.stdout
    now = now or D._now_msk()
    h = D._cycle_hash(slug, now.strftime("%Y-%m-%d"))
    L = [D._band(out, f"ПУЛЬТ · КОМАНДИР ДНЯ · {slug}", right=D._clock(out),
                 sub=f"хеш {h} · read 0₽ · d сухо · c живой(RUBICON)"),
         ""]
    L += commander_body(out, slug, pl, now)
    return _flat_join(out, L)


# ── РЕЛЬС: исполнение настоящего движка (единственный subprocess ДОМА) ─────────
def _commit_word_ok(typed, slug):
    """Слово-подтверждение ЖИВОГО прогона = slug магазина (RUBICON-ключ)."""
    return (typed or "").strip().lower() == (slug or "").strip().lower()


def _exec_cycle(slug, mode, runner=None, timeout=300):
    """Запустить НАСТОЯЩИЙ движок ЦИКЛ-1 тем же argv, что БРИГАДИР.

    mode 'dry' → --dry (0₽) · 'commit' → --commit (RUBICON, по слову оператора).
    runner — инъекция для герметичных приёмок (по умолчанию subprocess). Пульт сам
    файлы НЕ пишет: пишет движок. → dict {ok, verdict, tail}.
    """
    if runner is not None:
        return runner(slug, mode)
    import subprocess
    argv = [sys.executable, str(D.H.SOCC_ROOT / ENGINE_RELPATH), "--store", slug]
    argv.append("--commit" if mode == "commit" else "--dry")
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, cwd=str(D.H.SOCC_ROOT))
    except Exception as e:
        return dict(ok=False, verdict="ERR",
                    tail=[f"движок не стартовал: {type(e).__name__}: {e}"])
    raw = ((p.stdout or "") + "\n" + (p.stderr or "")).splitlines()
    tail = [D._ansi_strip(ln.strip()) for ln in raw if ln.strip()][-18:]
    ok = p.returncode == 0
    return dict(ok=ok, verdict="PASS/DRY_OK" if ok else "FAIL",
                tail=tail or ["(движок молчит)"])


# ── кадр пульта: ровно rows клеток, строки ≤78, ANSI не режем ──────────────────
def _pult_frame(out, title, sub, body, foot):
    """Клетки кадра пульта (тело — окно нужной высоты; пустые добьются)."""
    rows_, _c, w = D._geom()
    body_h = rows_ - D._HEAD - D._FOOT
    body = [_fit(out, ln) for ln in body]
    body = (list(body) + [""] * body_h)[:body_h]
    foot = (list(foot) + [""] * D._FOOT)[:D._FOOT]
    foot = [D._col(out, "DIM", _fit(out, ln)) for ln in foot]
    sub = V.clip_ansi(str(sub), max(8, w - 4)) if D._tty(out) else str(sub)[: max(8, w - 4)]
    return D._frame(out, title, sub, body, foot)


def _window(body, h, anchor):
    """Скользящее окно: кусок длиной ≤h с anchor-строкой внутри. → (win, maxoff)."""
    n = len(body)
    if n <= h:
        return list(body) + [""] * (h - n), 0
    top = max(0, min(anchor - h + 1, n - h))
    return list(body[top:top + h]), n - h


def _read_rail_key(inp, fd):
    """Клавиша ПУЛЬТА: как D._read_key, но d/c — СВОИ рельсы (ДОМ их не знает:
    там любая буква = enter). Остальное зеркалит ДОМ: стрелки/jk/q/цифры/Esc."""
    try:
        b0 = os.read(fd, 1)
    except Exception:
        return "q"
    if b0 == b"\x1b":
        seq = b""
        for _ in range(2):
            r, _, _ = _select.select([inp], [], [], 0.03)
            if not r:
                break
            try:
                seq += os.read(fd, 1)
            except Exception:
                break
        if seq in (b"[A", b"OA", b"[1;2A"):
            return "up"
        if seq in (b"[B", b"OB", b"[1;2B"):
            return "down"
        if seq in (b"[C", b"[D"):
            return "right" if seq == b"[C" else "left"
        return "esc"
    if b0 in (b"\r", b"\n"):
        return "enter"
    try:
        ch = b0.decode("utf-8", "replace")
    except Exception:
        return "q"
    if ch in "123456789":
        return ch
    if ch in "jkJK":
        return ch.lower()
    if ch in "dD":
        return "d"
    if ch in "cC":
        return "c"
    if ch in ("q", "Q"):
        return "q"
    return "enter"  # любая другая — как Enter (быстрое «дальше»)


def _tick_key(out, inp, fd, idle=_IDLE):
    """Один клавишный ввод или None по таймауту (авто-тик живого кадра)."""
    try:
        r, _, _ = _select.select([inp], [], [], idle)
    except Exception:
        r = [fd]
    if not r:
        return None
    return _read_rail_key(inp, fd)


def _word_key(inp, fd):
    """Один ввод слова (сырьё): (kind, val) · kind ∈ submit|char|back · None = отмена."""
    try:
        b = os.read(fd, 1)
    except Exception:
        return None
    if b in (b"\r", b"\n"):
        return ("submit", "")
    if b in (b"\x7f", b"\x08"):
        return ("back", "")
    if b == b"\x1b":
        return None
    try:
        return ("char", b.decode("utf-8", "replace"))
    except Exception:
        return ("char", "?")


def _sub_store(out, slug, pl):
    info = pl["info"]
    h = D._cycle_hash(slug)
    bits = [f"хеш {h}",
            f"биз {info.get('business_id') or '?'}",
            f"кампания {info.get('campaign_id') or '?'}",
            f"склад {info.get('warehouse_id') or '?'}"]
    return " · ".join(bits)


# ── сессия пульта (один alt-screen, состояние-машина) ──────────────────────────
def _pult(out, inp, *, slug=None, runner=None):
    """Живой ПУЛЬТ. slug=None → ШТАБ флота; slug задан → сразу КОМАНДИР ДНЯ.

    Клавиши: ↑↓/jk выбор · Enter провалиться · d сухой (одно подтверждение) ·
    c живой (RUBICON: слово-магазин + Enter) · q/esc — назад (одна ступень).
    Пока нет клавиш — кадр сам дышит (часы/автопилот/ближ. тик).
    """
    if not D._viable_tty(out, inp):
        if slug:
            out.write(commander_text(out, slug) + "\n")
        else:
            out.write(fleet_text(out) + "\n")
        return "back"
    from_store = slug is not None
    fd, old = V.enter(out, inp)
    cur = slug
    state = "store" if from_store else "fleet"
    sel, off = 0, 0
    res, res_mode = None, "dry"
    cword = ""
    try:
        while True:
            now = D._now_msk()
            stores = D._stores_map()
            rows = fleet_rows(stores, now)
            if state == "fleet":
                if rows:
                    sel = max(0, min(sel, len(rows) - 1))
                else:
                    sel = 0
                meta = fleet_meta(stores, now)
                body = [f"  {meta['today']} · витрин: {meta['n']} · {meta['ticks']}",
                        D._col(out, "DIM", "  " + meta["money"]),
                        D._seal(out, "ВИТРИНЫ · КОМАНДИР ДНЯ (правило хода)")]
                entries = []
                for i, r in enumerate(rows):
                    for ln in _row_lines(out, r, i, sel):
                        entries.append(ln)
                if not entries:
                    body.append(D._col(out, "DIM", "  манифест пуст — витрины ещё нет (0₽)"))
                rows_, _c, _w = D._geom()
                area_h = rows_ - D._HEAD - D._FOOT - len(body)
                if entries and area_h > 0:
                    anchor = 0
                    if rows:
                        cur_slug = rows[min(sel, len(rows) - 1)]["slug"]
                        for k, ln in enumerate(entries):
                            if cur_slug in ln:
                                anchor = k
                                break
                    win, _mo = _window(entries, area_h, anchor)
                    body += win
                title = "ПУЛЬТ · ШТАБ ЯМ-ЦИКЛА"
                foot = [
                    f"витрина {sel + 1} из {len(rows)} · РЕЛЬС: сухо 0₽ по умолчанию",
                    f"АВТОПИЛОТ · {meta['ticks']}",
                    "↑↓ выбор · Enter КОМАНДИР ДНЯ · d сухо · c живой(RUBICON) · q назад",
                ]
            elif state == "store":
                pl = D.store_payload(cur)
                content = commander_body(out, cur, pl, now)
                rows_, _c, _w = D._geom()
                body_h = rows_ - D._HEAD - D._FOOT
                body, _mo = _window(content, body_h, off)
                info = pl["info"]
                title = f"ПУЛЬТ · КОМАНДИР ДНЯ · {cur}"
                foot = [
                    D._brief_tasks(pl),
                    f"склад {info.get('warehouse_id') or '?'} · read 0₽ · исполнит движок по слову",
                    "↑↓ листать · d сухо · c живой(RUBICON) · q назад",
                ]
            elif state == "dry":
                body = [f"  Сухой прогон ЦИКЛ-1 «{cur}» — проверит цепь узлов сухо.",
                        D._col(out, "DIM", "  Ничего не отправляет на ЯМ · 0₽ · движок пишет dry:True."),
                        D._col(out, "DIM", "  Enter — запустить · q — отмена")]
                title = f"РЕЛЬС · СУХОЙ 0₽ · {cur}"
                foot = ["", "сухой прогон = 0₽ · read-проверка цепи", "Enter запустить · q отмена"]
            elif state == "word":
                body = [f"  ЖИВОЙ прогон ЦИКЛ-1 «{cur}» = RUBICON: движок напишет",
                        D._col(out, "RE", "  на витрину Экспресс (--commit · dry:false)."),
                        D._seal(out, "ДВОЙНОЕ ПОДТВЕРЖДЕНИЕ"),
                        f"  введи слово-магазин и Enter:  {cur}",
                        D._col(out, "CY", "  → " + cword + "▌"),
                        D._col(out, "DIM", "  Esc — отмена")]
                title = f"РЕЛЬС · ЖИВОЙ RUBICON · {cur}"
                foot = ["", "слово = slug магазина (RUBICON)", "Enter подтвердить · Esc отмена"]
            elif state == "commit":
                body = [D._col(out, "RE", "  ● ЖИВОЙ прогон (--commit) · слово принято"),
                        f"  «{cur}»",
                        D._col(out, "DIM", "  движок напишет на витрину по закону (dry:false)."),
                        "  Enter — ЗАПУСТИТЬ · q — отмена"]
                title = f"РЕЛЬС · ЖИВОЙ RUBICON · {cur}"
                foot = ["", "это реальный шаг на витрине", "Enter ЗАПУСТИТЬ · q отмена"]
            elif state == "result":
                pl = D.store_payload(cur)
                act = "ЖИВОЙ RUBICON" if res_mode == "commit" else "СУХОЙ 0₽"
                col = "GR" if res["ok"] else "RE"
                head = [f"  {D._col(out, col, '●')} {cur} · {act} → {res['verdict']}"]
                tail = [D._col(out, "DIM", "    " + _fit(out, ln, 70)) for ln in res.get("tail", [])]
                content = head + tail + [""] + commander_body(out, cur, pl, now)
                rows_, _c, _w = D._geom()
                body_h = rows_ - D._HEAD - D._FOOT
                body, _mo = _window(content, body_h, off)
                title = f"ПУЛЬТ · РЕЗУЛЬТАТ · {cur}"
                foot = [
                    D._brief_tasks(pl),
                    "ниже — свежий КОМАНДИР ДНЯ после прогона (леджер обновился)",
                    "↑↓ листать · q назад",
                ]

            V.paint(out, _pult_frame(out, title, D._clock(out), body, foot))

            if state == "word":
                ch = _word_key(inp, fd)
                if ch is None:
                    state, cword, off = "store", "", 0
                    continue
                kind, val = ch
                if kind == "submit":
                    if _commit_word_ok(cword, cur):
                        state = "commit"
                    else:
                        state, cword, off = "store", "", 0
                elif kind == "char":
                    cword = (cword + val)[-64:]
                elif kind == "back":
                    cword = cword[:-1]
                continue

            key = _tick_key(out, inp, fd)
            if key is None:
                continue  # авто-тик: перерисовать (часы/ближ. тик свежие)

            if state == "result":
                if key in ("up", "k"):
                    if off > 0:
                        off -= 1
                elif key in ("down", "j", "enter"):
                    off += 1
                elif key in ("q", "esc"):
                    state, res, off = "store", None, 0
                continue
            if state in ("dry", "commit"):
                if key == "enter":
                    mode = "commit" if state == "commit" else "dry"
                    res = _exec_cycle(cur, mode, runner=runner)
                    res_mode = mode
                    off = 0
                    state = "result"
                elif key in ("q", "esc"):
                    state, off = "store", 0
                continue
            if state == "store":
                if key in ("up", "k"):
                    if off > 0:
                        off -= 1
                elif key in ("down", "j"):
                    off += 1
                elif key in ("q", "esc"):
                    if from_store:
                        return "back"
                    state, off = "fleet", 0
                elif key == "d":
                    state = "dry"
                elif key == "c":
                    state, cword = "word", ""
                continue
            # state == fleet
            if key in ("q", "esc"):
                return "back"
            if key in ("up", "k"):
                if rows:
                    sel = (sel - 1) % len(rows)
            elif key in ("down", "j"):
                if rows:
                    sel = (sel + 1) % len(rows)
            elif key == "enter":
                if rows:
                    cur = rows[sel]["slug"]
                    off = 0
                    state = "store"
            elif key == "d":
                if rows:
                    cur = rows[sel]["slug"]
                    off = 0
                    state = "dry"
            elif key == "c":
                if rows:
                    cur = rows[sel]["slug"]
                    state, cword = "word", ""
    finally:
        V.leave(out, fd, old)


def run_fleet(out, inp, *, runner=None):
    """Вход ПУЛЬТ · ШТАБ (из меню ДОМА). → 'back' в вызывающее меню."""
    return _pult(out, inp, slug=None, runner=runner)


def run_store_pult(out, inp, slug, *, runner=None):
    """Вход КОМАНДИР ДНЯ витрины (кнопка из ДОМА кампании). → 'back'."""
    return _pult(out, inp, slug=slug, runner=runner)


if __name__ == "__main__":
    sys.exit(0)

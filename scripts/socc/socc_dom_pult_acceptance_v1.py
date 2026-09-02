#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · ПУЛЬТ ЯМ-ЦИКЛА — ПРИЁМКА (socc_cli/pult.py).

Сухо, 0₽, без сети, без записи. Пульт — ЕДИНСТВЕННЫЙ исполнитель ДОМА (запуск
настоящего движка ЦИКЛ-1 тем же argv, что БРИГАДИР). Здесь исполнение движка НЕ
запускается: _exec_cycle гоняется с подменой subprocess.run (ловит argv) и с
runner=-инъекцией — движок ни разу не стартует, леджер не пишется.

Законы PU1–PU11:
  PU1  штаб_плоский   — fleet_text/commander_text на StringIO без ANSI (CC8),
                        заголовки/рельсы на месте
  PU2  сортировка_флота— fleet_rows: heat убывает (чинить→внимание→спокойно),
                        связка по slug; классификатор 0/1/2 → ●/○/⚠
  PU3  команд_дня      — КОМАНДИР ДНЯ витрины: банд с slug+хеш 10 · правило хода
                        · деньги · ДОМ КАМПАНИИ (read) — из живых сторов
  PU4  деньги_честно  — закуп → потенциал ×маржа · «0₽ реальных», пока нет строки
                        dry:false; живая строка → «живых строк N» (не врём)
  PU5  слово_рубикон  — _commit_word_ok: slug=принято · чужое=нет · регистр/пробелы;
                        _word_key: char/submit/back/Esc
  PU6  рельсы_клавиши — _read_rail_key: d/c — рельсы пульта (ДОМ их не знает:
                        там любая буква = enter); jk/q/цифры/Esc — зеркало ДОМА
  PU7  исполнитель_argv— _exec_cycle по умолчанию зовёт движок ТЕМ ЖЕ argv
                        (--store slug --dry|--commit · cwd=SOCC · timeout) и отдаёт
                        {ok, verdict, tail}; runner= — короткое замыкание, движок НЕ зовётся
  PU8  пульт_не_пишет — исходник pult.py: subprocess — ТОЛЬКО в _exec_cycle (закон
                        разделения: dom.py без исполнителя); сеть/запись — нет
  PU9  ширина_тела    — тело ШТАБ/КОМАНДИР (синтетика-макс + реальные сторы):
                        каждая строка ≤78 — на 80×24 ничего не клипается
  PU10 вход_не_тити   — run_fleet/run_store_pult на StringIO → плоский текст + 'back'
                        (пайп-путь сохранён, движок не стартует)
  PU11 флот_пуст_честно— манифест пуст → «манифест пуст · 0₽» без падений
"""
import io
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SOCC_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOCC_ROOT) not in sys.path:
    sys.path.insert(0, str(SOCC_ROOT))

from socc_cli import pult                       # noqa: E402
from socc_cli import dom as D                   # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")
NOW = datetime(2026, 9, 3, 8, 30, 0)            # фикс-время: детерминизм даты/хеша
TODAY = "2026-09-03"


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _first_store():
    m = D._stores_map()
    return (next(iter(sorted(m))) if m else None), m


def _ts(hhmm):
    return f"{TODAY}T{hhmm}:00"


def _pl_for(slug="atlas-express-film", *, ledger=None, pulse=None, info=None,
            queue=(), reg=("absent", [])):
    """Герметичный payload кампании (как у движка), без диска."""
    info = info or dict(business_id="184481130", campaign_id="149215943",
                        warehouse_id="2390811",
                        donor_category="vozdushno-puzyrkovaya-plenka",
                        builder="film", markup=8.0, stock_count=100,
                        note="витрина Экспресса плёнки · dry подтверждён")
    pulse = pulse if pulse is not None else dict(
        date=TODAY, run_verdicts={"PASS": 3, "DRY": 3}, artifacts=1)
    if ledger is None:
        ledger = [dict(node="ДОНОР", verdict="PASS", ts=_ts("08:07")),
                  dict(node="СБОРКА", verdict="PASS", ts=_ts("08:20")),
                  dict(node="ЗАЛИВ", verdict="PASS", ts=_ts("09:05")),
                  dict(node="СВЕРКА", verdict="PASS", ts=_ts("09:31"),
                       evidence={"ARB-1": dict(placement=dict(status="PUBLISHED"),
                                               stock=100)})]
    return dict(store=slug, info=info, pulse=pulse, ledger=list(ledger),
                queue=list(queue), registry=tuple(reg))


# ─────────────────────────── ТЕСТЫ ───────────────────────────

def pu1_shtab_ploskii():
    txt = pult.fleet_text(io.StringIO(), stores=D._stores_map())
    bad = []
    if ANSI.search(txt):
        bad.append("ANSI в fleet_text")
    for need in ("ПУЛЬТ · ШТАБ ЯМ-ЦИКЛА", "ВИТРИНЫ · КОМАНДИР ДНЯ",
                 "РЕЛЬС", "d — сухой прогон", "c — живой (RUBICON"):
        if need not in txt:
            bad.append(f"в штабе нет «{need}»")
    slug, _ = _first_store()
    slug = slug or "atlas-express-film"
    ctxt = pult.commander_text(io.StringIO(), slug, now=NOW)
    if ANSI.search(ctxt):
        bad.append("ANSI в commander_text")
    return (not bad), " · ".join(bad) or "ШТАБ/КОМАНДИР плоские (CC8), заголовки+рельсы на месте"


def pu2_sortirovka_flota():
    # заморозка правила хода пульта: heat 2=чинить · 1=внимание · 0=спокойно
    R = {"z-clean": (0, "ДЕНЬ ЧИСТ", "витрина PUBLISHED · открытых заданий нет"),
         "m-watch": (1, "ПУЛЬС", "пульс устарел — прогнать сухо сегодня (0₽)"),
         "a-fix":   (2, "ЧИНИТЬ", "узел «ОСТАТКИ» упал последним ходом")}
    o_pl, o_step = D.store_payload, D._next_step

    def _fake_pl(slug):
        return dict(store=slug, info=dict(), pulse=dict(date=TODAY),
                    ledger=[], queue=[], registry=("absent", []))
    D.store_payload = _fake_pl
    D._next_step = lambda store, pl=None, now=None: R.get(store, (0, "ЖДАТЬ", "x"))
    bad = []
    try:
        rows = pult.fleet_rows(dict(R), now=NOW)
        order = [r["slug"] for r in rows]
        if order != ["a-fix", "m-watch", "z-clean"]:
            bad.append(f"порядок флота {order} (ждём a-fix→m-watch→z-clean)")
        if [r["heat"] for r in rows] != [2, 1, 0]:
            bad.append("heat не убывает")
        # связка по slug при равном heat
        rows2 = pult.fleet_rows({"zz": (0, "ЖДАТЬ", "x"), "aa": (0, "ЖДАТЬ", "x")}, now=NOW)
        if [r["slug"] for r in rows2] != ["aa", "zz"]:
            bad.append("связка по slug не работает")
        # классификатор знаков
        if pult.classifier(0)[0] != "●" or pult.classifier(1)[0] != "○" \
                or pult.classifier(2)[0] != "⚠" or pult.classifier(None)[0] != "●":
            bad.append("классификатор ●/○/⚠ сбит")
    finally:
        D.store_payload, D._next_step = o_pl, o_step
    return (not bad), " · ".join(bad) or "heat↓ (чинить→внимание→спокойно) · slug-связка · ●○⚠"


def pu3_komand_dnya():
    # герметично: синтетический payload + фикс-время — без чтения диска
    slug = "atlas-express-film"
    h = D._cycle_hash(slug, TODAY)
    txt = pult.commander_text(io.StringIO(), slug, pl=_pl_for(slug), now=NOW)
    bad = []
    for need in (f"ПУЛЬТ · КОМАНДИР ДНЯ · {slug}", f"хеш {h}", "КОМАНДИР ДНЯ:",
                 "ДОМ КАМПАНИИ (read)", "ПУЛЬС", "ЦИКЛ СЕГОДНЯ", "АКТИВНЫЕ ЗАДАНИЯ",
                 "РЕЗУЛЬТАТ ДНЯ", "PUBLISHED 1"):
        if need not in txt:
            bad.append(f"нет «{need}»")
    return (not bad), " · ".join(bad) or \
        f"КОМАНДИР ДНЯ {slug} · хеш {h} · все секции ДОМА + PUBLISHED-арт (синтетика, без диска)"


def pu4_dengi_chestno():
    bad = []
    costs = D._card_costs_map()
    base = [dict(node="ДОНОР", verdict="PASS", ts=_ts("08:07"))]
    m0 = pult._money_txt(_pl_for(ledger=base))
    if "0₽ реальных" not in m0:
        bad.append("нет «0₽ реальных» без живых строк")
    if "СВЕРКА докажет" not in m0:
        bad.append("не видно «на витрине 0 — СВЕРКА докажет»")
    if costs and ("закуп" not in m0 or "→ потенциал" not in m0):
        bad.append(f"закуп есть ({len(costs)} карт) — а «закуп→потенциал» не видно")
    if not costs and "закупа нет" not in m0:
        bad.append("закупа нет — а честной строки «закупа нет» не видно")
    # живая строка (dry:false) → честные «живые строки N», НЕ «0₽»
    live = base + [dict(node="ПЛАНЁРКА", verdict="PASS", ts=_ts("16:40"), dry=False)]
    m1 = pult._money_txt(_pl_for(ledger=live))
    if "живых строк 1" not in m1 or "0₽ реальных" in m1:
        bad.append("живая строка не дала «живых строк 1»/остался «0₽»")
    # PUBLISHED-арт из СВЕРКА-PASS
    pub = _pl_for()
    m2 = pult._money_txt(pub)
    if "PUBLISHED 1" not in m2:
        bad.append("СВЕРКА-PASS не дал «PUBLISHED 1»")
    # итог по пустому манифесту — 0₽
    ml = pult._fleet_money_line({})
    if "0₽ реальных" not in ml or "закупа нет" not in ml:
        bad.append(f"итог пустого манифеста нечестен: «{ml}»")
    return (not bad), " · ".join(bad) or \
        "закуп→потенциал ×N · 0₽ реальных · живая строка→живых строк N · PUBLISHED-арт честны"


def pu5_slovo_rubikon():
    ok1 = pult._commit_word_ok("atlas-express-film", "atlas-express-film") is True
    ok2 = pult._commit_word_ok("  ATLAS-EXPRESS-FILM ", "atlas-express-film") is True
    ok3 = pult._commit_word_ok("drugaya", "atlas-express-film") is False
    ok4 = pult._commit_word_ok("", "atlas-express-film") is False
    ok5 = pult._commit_word_ok(None, "atlas-express-film") is False

    def _feed(b):
        r, w = os.pipe()
        try:
            os.write(w, b)
        finally:
            os.close(w)
        return r

    keys_ok = True
    for raw, exp in ((b"a", ("char", "a")), (b"\r", ("submit", "")),
                     (b"\x7f", ("back", "")), (b"\x1b", None)):
        r = _feed(raw)
        try:
            got = pult._word_key(r, r)
        finally:
            os.close(r)
        if got != exp:
            keys_ok = False
    return (ok1 and ok2 and ok3 and ok4 and ok5 and keys_ok), \
        f"slug=принято · чужое={ok3} · пусто={ok4} · клавиши слова={'✓' if keys_ok else '✗'}"


def pu6_relsy_klavishi():
    def _feed(b):
        r, w = os.pipe()
        try:
            os.write(w, b)
        finally:
            os.close(w)
        return r

    cases = [(b"d", "d"), (b"D", "d"), (b"c", "c"), (b"C", "c"),
             (b"j", "j"), (b"J", "j"), (b"k", "k"), (b"3", "3"),
             (b"q", "q"), (b"\r", "enter"), (b"x", "enter"),
             (b"\x1b", "esc"), (b"\x1b[B", "down"), (b"\x1b[A", "up")]
    bad = []
    for raw, exp in cases:
        r = _feed(raw)
        try:
            got = pult._read_rail_key(r, r)
        finally:
            os.close(r)
        if got != exp:
            bad.append(f"{raw!r} → {got!r} (ждём {exp!r})")
    # ключевой закон: d/c — рельсы ПУЛЬТА, ДОМ их вернул бы 'enter'
    if pult._read_rail_key is D._read_key:
        bad.append("_read_rail_key = _read_key ДОМА (должен быть свой: d/c ≠ enter)")
    return (not bad), " · ".join(bad) or \
        "d/c — свои рельсы · jk/цифры/q/Esc — зеркало ДОМА · незнакомая → enter"


def pu7_ispolnitel_argv():
    """Движок НЕ стартует: subprocess.run подменён (ловит argv) — 0₽, леджер цел."""
    calls = []
    real_run = subprocess.run

    class _P:
        returncode, stderr = 0, ""

        def __init__(s, out=""):
            s.stdout = out

    def _fake(*a, **k):
        # subprocess.run(argv, ...) → a = (argv_list,); храним сырой argv
        calls.append((a[0] if a else None, k))
        return _P("PASS/DRY_OK  цепь узлов сухо — живое не тронуто")

    subprocess.run = _fake
    bad = []
    try:
        r_dry = pult._exec_cycle("atlas-express-film", "dry")
        argv, kw = calls[-1]
        eng = str(SOCC_ROOT / pult.ENGINE_RELPATH)
        if argv[0] != sys.executable or argv[1] != eng:
            bad.append(f"движок: {argv[:2]} (ждём {sys.executable} + {pult.ENGINE_RELPATH})")
        if argv[-3:] != ["--store", "atlas-express-film", "--dry"]:
            bad.append(f"dry-argv: {argv[-3:]}")
        if kw.get("cwd") != str(SOCC_ROOT):
            bad.append(f"cwd={kw.get('cwd')} (ждём SOCC_ROOT)")
        if kw.get("timeout") != 300:
            bad.append("нет таймаута по умолчанию")
        if not (r_dry.get("ok") and r_dry.get("verdict") == "PASS/DRY_OK"):
            bad.append(f"dry-результат: {r_dry}")
        if not any("PASS/DRY_OK" in t for t in r_dry.get("tail", [])):
            bad.append("tail пуст/без вердикта движка")
        # commit — тот же argv, флаг --commit
        n0 = len(calls)
        r_com = pult._exec_cycle("atlas-express-film", "commit")
        if calls[-1][0][-1] != "--commit":
            bad.append("commit-argv не заканчивается --commit")
        # runner=-инъекция: движок не зовётся, результат — как дал runner
        seen = []
        r_run = pult._exec_cycle("atlas-express-film", "dry",
                                 runner=lambda s, m: (seen.append((s, m)),
                                                      dict(ok=False, verdict="FAIL",
                                                           tail=["герметично"]))[1])
        if len(calls) != n0 + 1:
            bad.append("runner= всё равно дёрнул движок")
        if seen != [("atlas-express-film", "dry")] or r_run.get("verdict") != "FAIL":
            bad.append("runner=-инъекция не прошла насквозь")
    finally:
        subprocess.run = real_run
    return (not bad), " · ".join(bad) or \
        "argv=БРИГАДИР (--store … --dry|--commit · cwd=SOCC · timeout) · runner= — без движка"


def pu8_pult_ne_pishet():
    """Закон разделения: исполнитель — ТОЛЬКО pult.py, и только через subprocess."""
    src = (SOCC_ROOT / "socc_cli" / "pult.py").read_text(encoding="utf-8")
    banned = ["write_text", "write_bytes", "json.dump", "os.remove", "os.unlink",
              "os.makedirs", "os.mkdir", "shutil", "requests", "urllib", "socket",
              "os.system", "rmtree"]
    hits = [b for b in banned if b in src]
    open_w = re.search(r"open\([^)]*,\s*[\"']([wa])[\"']", src)
    # dom.py — вообще без subprocess/записи (DH8); исполнитель — только pult
    dsrc = (SOCC_ROOT / "socc_cli" / "dom.py").read_text(encoding="utf-8")
    if "import subprocess" in dsrc or "subprocess" in dsrc:
        hits.append("dom.py содержит subprocess")
    n_exec = len(re.findall(r"import subprocess", src))
    ok = not hits and open_w is None and n_exec == 1
    return ok, f"токены pult: {hits or '—'} · open-write: {open_w.group(0) if open_w else '—'} · exec-import ×{n_exec}"


def _body_lines():
    """Строки тел ШТАБ/КОМАНДИР: синтетика-макс (длинные note/what/почему) + сторы."""
    for slug in sorted(D._stores_map()) or ["atlas-express-film"]:
        # реальный payload магазина (read-стора, 0₽)
        for ln in pult.fleet_body(io.StringIO()):
            yield ln
        yield from pult.commander_body(io.StringIO(), slug, now=NOW)
        # синтетика-макс: FAIL-хвост с длинной сырой припиской + длинная очередь
        wide = _pl_for(ledger=[dict(node="ДОНОР", verdict="PASS", ts=_ts("12:22")),
                               dict(node="ОСТАТКИ", verdict="FAIL", ts=_ts("13:01"),
                                    note="остатки не легли: None после чтения стока — нужен повтор чтения живьём"),
                               dict(node="СВЕРКА", verdict="PASS", ts=_ts("09:31"),
                                    evidence={"ARB-1": dict(placement=dict(status="PUBLISHED"), stock=100)})],
                       queue=[dict(tag="СВЕРКА", urgency="low", owner="КОНТРОЛЁР",
                                   what="Матрица отстала от витрины: карточки PUBLISHED, а offer_id "
                                        "в матрице всё ещё пуст — поправить матрицу живым чтением",
                                   evidence="леджер СВЕРКА-PASS (PUBLISHED), матрица «собран/offer пуст»")])
        yield from pult.commander_body(io.StringIO(), slug, pl=wide, now=NOW)
        yield from pult.fleet_body(io.StringIO(), stores={slug: {}}, now=NOW)


def pu9_shirina_tela():
    """Каждая строка тел ≤78: StringIO plain (CC8) → len() == ширина клетки,
    на 80×24 ничего не клипается (автоперенос выключен)."""
    long_lines = [ln for ln in _body_lines() if len(str(ln)) > 78]
    return (not long_lines), \
        f"строк >78: {len(long_lines)}" + (f" :: {long_lines[0][:90]}" if long_lines else " · тела ШТАБ/КОМАНДИР в 78")


def pu10_vhod_ne_titi():
    """Пайп/StringIO: пульт печатает плоский текст и НЕ стартует движок (0₽)."""
    bad = []
    out, inp = io.StringIO(), io.StringIO()
    rc = pult.run_fleet(out, inp)
    t = out.getvalue()
    if rc != "back":
        bad.append(f"run_fleet вернул {rc!r} (ждём 'back')")
    if "ПУЛЬТ · ШТАБ ЯМ-ЦИКЛА" not in t or ANSI.search(t):
        bad.append("run_fleet не выдал плоский штаб")
    slug, _ = _first_store()
    if slug:
        out2, inp2 = io.StringIO(), io.StringIO()
        rc2 = pult.run_store_pult(out2, inp2, slug)
        t2 = out2.getvalue()
        if rc2 != "back" or f"КОМАНДИР ДНЯ · {slug}" not in t2 or ANSI.search(t2):
            bad.append("run_store_pult не выдал плоского КОМАНДИРА")
    return (not bad), " · ".join(bad) or "не-tty путь: плоский текст + 'back', движок не стартует"


def pu11_flot_pust_chestno():
    txt = pult.fleet_text(io.StringIO(), stores={}, now=NOW)
    bad = []
    if "манифест пуст" not in txt:
        bad.append("нет «манифест пуст»")
    if "0₽ реальных" not in txt:
        bad.append("нет честной подписи «0₽ реальных» на пустом флоте")
    rows = pult.fleet_rows({}, now=NOW)
    if rows:
        bad.append("fleet_rows пустого манифеста непуст")
    return (not bad), " · ".join(bad) or "пустой флот: «манифест пуст» · «0₽» · нет строк — без падений"


TESTS = [
    ("PU1  штаб_плоский", pu1_shtab_ploskii),
    ("PU2  сортировка_флота", pu2_sortirovka_flota),
    ("PU3  команд_дня", pu3_komand_dnya),
    ("PU4  деньги_честно", pu4_dengi_chestno),
    ("PU5  слово_рубикон", pu5_slovo_rubikon),
    ("PU6  рельсы_клавиши", pu6_relsy_klavishi),
    ("PU7  исполнитель_argv", pu7_ispolnitel_argv),
    ("PU8  пульт_не_пишет", pu8_pult_ne_pishet),
    ("PU9  ширина_тела", pu9_shirina_tela),
    ("PU10 вход_не_тити", pu10_vhod_ne_titi),
    ("PU11 флот_пуст_честно", pu11_flot_pust_chestno),
]


def main():
    print("🎛️  SOCC · ДОМ · ПУЛЬТ ЯМ-ЦИКЛА · ПРИЁМКА — герметично, движок не стартует, 0₽")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<19} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ ПУЛЬТ: ШТАБ → КОМАНДИР ДНЯ → рельсы d/c, честно, 0₽, движок не трогали")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

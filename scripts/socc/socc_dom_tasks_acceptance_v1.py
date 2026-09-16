#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · ЗАДАНИЯ — ПРИЁМКА (socc_cli/tasks.py), законы TX1–TX8.

Лицо ЗАДАНИЯ = ПЕРВОЕ-класс экран ДОМА на уровне home: `socc задания` в пайпе →
плоская планёрка всех открытых (band · сводка · группы-магазины · строки с
id/владельцем/пунктами), на живом терминале → меню-реестр → провал в строку =
КАРТОЧКА (пункты ●/○ + evidence). Читаем ОДНУ правду — реестр-орган
ymarket_tasks_v1 (task_path/load/open_only/sort_tasks/stats/derive/render_task),
ничего из логики не пере-реализуем. RUBICON цел: движок НЕ запускается, файлы не
пишем (кроме tmp-песочницы самого теста), сети нет, 0₽.

Герметично: синтетика строится КАК реестр (new_task → mark_step под гейтом TZ8 —
только так появляются по-настоящему закрытые пункты и честный derive), подаётся
инъекцией tasks_text(out, tasks=…) ИЛИ env YM_TASKS_PATH на tmp-стор (канон не
тронут: байт-в-байт). Патч _T_ATTR=None симулирует «орган не импортировался».

Законы TX (см. докстринг tasks.py):
  TX1  лицо_плоское      — band ЗАДАНИЯ · ДОМ · группы-магазины с «открыто N» ·
                          строки с id · владельцем · пунктами X/Y · без ANSI
  TX2  честный_tri_state — орган-нет / стора-нет / битый → честная строка
  TX3  сводка_честна     — записей · закрыто % · в работе · ждут · срочных;
                          закрытое (derive done) в строки НЕ попадает
  TX4  важное_выше       — порядок = sort_tasks органа: P10 над P20, срочность
                          при равном приоритете (как планёрка цикла)
  TX5  карточка_пункты   — render_task: [state·id] · ● с evidence · ○ открыт
  TX6  строка_≤78        — весь плоский лист и карточка (вкл. синтетику-макс):
                          каждая строка ≤78, хвост (id/владелец) не теряется
  TX7  лицо_не_пишет     — tasks.py: нет записи/сети/исполнителя; dom.py без
                          шелл-исполнителя (DH8 сохранён после врезки)
  TX8  вход_в_доме       — `socc задания`: cli._HOME_KEYS · home_rows пункт
                          ЗАДАНИЯ/ТОПЛИВО · ветка dispatch · home_text/HELP ·
                          функциональный прогон на tmp-сторе (rc 0, плоский)
"""
import io
import os
import re
import sys
import tempfile
from pathlib import Path

SOCC_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOCC_ROOT) not in sys.path:
    sys.path.insert(0, str(SOCC_ROOT))
ARB = SOCC_ROOT / "scripts/mint/arbiter"
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

import ymarket_tasks_v1 as T_reg                    # noqa: E402  (референс органа)
from socc_cli import dom as D                        # noqa: E402
from socc_cli import home as H                       # noqa: E402
from socc_cli import tasks as Tk                     # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


class _patch:
    """Контекст: точечный мононе-патч, восстановление в finally."""

    def __init__(self, *items):
        self.items = items
        self.old = []

    def __enter__(self):
        for mod, name, val in self.items:
            if isinstance(name, str) and "." in name:
                modn, name = name.split(".", 1)
                mod = getattr(mod, modn)
            self.old.append((mod, name, getattr(mod, name)))
            setattr(mod, name, val)
        return self

    def __exit__(self, *a):
        for mod, name, old in self.old:
            setattr(mod, name, old)
        return False


# ── синтетика-фабрика (как реестр: new_task → mark_step, TZ8-гейт) ─────────────
def _mk(what, *, owner="PRICER", category="pricing", market="ym", store="",
        urgency=None, priority=50, body="", deps=(), steps=None, done=()):
    """Задание той же формы, что кладёт орган. done = [(step_id, done_by, evidence)]."""
    steps = steps or [{"id": "s1", "title": "шаг"}]
    t, err = T_reg.new_task(what=what, owner=owner, category=category, market=market,
                            cycle="cycle1", store=store, urgency=urgency,
                            priority=priority, body=body, depends_on=deps, steps=steps)
    if err:
        raise AssertionError(err)
    for sid, db, ev in done:
        t, e = T_reg.mark_step(t, sid, done_by=db, evidence=ev)
        if e:
            raise AssertionError(e)
    return t


def _fxt():
    """Синтетика-7: 4 открытых · 1 в работе · 1 ждёт · 1 закрытое (канон-форма)."""
    return [
        _mk("A приоритет 10 срочное", owner="PRICER", store="atlas-express-film",
            urgency="high", priority=10,
            steps=[{"id": "s1", "title": "А шаг 1"}, {"id": "s2", "title": "А шаг 2"}]),
        _mk("B приоритет 20 срочное", owner="PRICER", store="atlas-express-film",
            urgency="high", priority=20),
        _mk("C системное нормальное", owner="SELF", category="health",
            urgency="normal", priority=50),
        _mk("D ozon системное", owner="SELF", category="other", market="ozon",
            urgency="normal", priority=60),
        _mk("E закрытое СЕКРЕТ-не-в-строках", owner="PRICER",
            store="atlas-express-film", urgency="normal", priority=70,
            done=[("s1", "TX", "снял витрину 0₽")]),
        _mk("F в работе", owner="CATEGORIST", category="categories",
            urgency="normal", priority=60,
            steps=[{"id": "s1", "title": "F1"}, {"id": "s2", "title": "F2"}],
            done=[("s1", "TX", "разобрал донора")]),
        _mk("G ждёт зависимость", owner="BRAIN", category="other",
            urgency="normal", priority=70, deps=["T-ghost"]),
    ]


def _txt(tasks):
    return Tk.tasks_text(io.StringIO(), tasks=tasks)


def _ids(tasks):
    return [t["id"] for t in tasks]


# ───────────────────────────── ТЕСТЫ ─────────────────────────────

def tx1_lico_ploskoe():
    bad = []
    txt = _txt(_fxt())
    if ANSI.search(txt):
        bad.append("ANSI в плоском листе")
    for need in ("ЗАДАНИЯ · ДОМ", "ПЛАНЁРКА · ОТКРЫТЫЕ",
                 "МАГАЗИН · ym · atlas-express-film · открыто 2",
                 "МАРКЕТ ym · общесистемные · открыто 3",
                 "МАРКЕТ ozon · общесистемные · открыто 1",
                 "[PRICER]", "пункты 0/2", "T-"):
        if need not in txt:
            bad.append(f"нет «{need}»")
    return (not bad), " · ".join(bad) or \
        "band + группы-магазины + строки id/владелец/пункты X/Y, без ANSI (CC8)"


def tx2_chestnyi_tri_state():
    """Орган-нет / стора-нет / битый → честная строка, не фейк-пусто (CD1-честность)."""
    bad = []

    def _one(label, call, expect):
        try:
            t = call()
        except Exception as e:
            bad.append(f"{label}: исключение {type(e).__name__}: {e}")
            return
        if expect not in t:
            bad.append(f"{label}: нет «{expect}» в:\n{t[:220]}")

    with _patch((Tk, "_T_ATTR", None)):            # орган «не импортировался»
        _one("орган-нет", lambda: Tk.tasks_text(io.StringIO()),
             "реестр-орган недоступен")
    with tempfile.TemporaryDirectory() as td:
        missing = str(Path(td) / "нет-такого.json")   # стора ещё нет
        old = os.environ.get("YM_TASKS_PATH")
        try:
            os.environ["YM_TASKS_PATH"] = missing
            _one("стора-нет", lambda: Tk.tasks_text(io.StringIO()),
                 "реестра ещё нет")
            broken = Path(td) / "broken.json"          # битый стор
            broken.write_text("не json {", encoding="utf-8")
            os.environ["YM_TASKS_PATH"] = str(broken)
            _one("битый", lambda: Tk.tasks_text(io.StringIO()), "реестр битый")
        finally:
            if old is None:
                os.environ.pop("YM_TASKS_PATH", None)
            else:
                os.environ["YM_TASKS_PATH"] = old
    return (not bad), " · ".join(bad) or \
        "tri-state честно: орган-нет / стора-нет / битый → строка, не фейк-пусто"


def tx3_svodka_chestna():
    bad = []
    txt = _txt(_fxt())
    for need in ("записей 7", "закрыто 14%", "в работе 1", "ждут 1",
                 "срочных открыто 2"):
        if need not in txt:
            bad.append(f"сводка: нет «{need}»")
    if "СЕКРЕТ-не-в-строках" in txt:                  # закрытое в строки НЕ идёт
        bad.append("закрытое (derive done) попало в строки")
    # сводка всё равно честно про закрытое: секрет виден ТОЛЬКО в %, не в строках
    return (not bad), " · ".join(bad) or \
        "сводка честна (в работе/ждут/срочных/закрыто %) · закрытые вне строк, гейт derive"


def tx4_vazhnoe_vyshe():
    bad = []
    w1 = _mk("TX4-w1 prio10 high", urgency="high", priority=10)
    w2 = _mk("TX4-w2 prio10 normal", urgency="normal", priority=10)
    w3 = _mk("TX4-w3 prio20 high", urgency="high", priority=20)
    w4 = _mk("TX4-w4 prio50 low", urgency="low", priority=50)
    txt = _txt([w4, w1, w3, w2])                       # кладём вперемешку
    pos = [txt.find(k["what"]) for k in (w1, w2, w3, w4)]
    if any(i < 0 for i in pos):
        bad.append(f"what не найден: {pos}")
    elif pos != sorted(pos):
        bad.append(f"порядок ≠ sort_tasks (priority → срочность): {pos}")
    return (not bad), " · ".join(bad) or \
        "важное выше: P10 над P20, срочность при равном приоритете (орган sort_tasks)"


def tx5_kartochka_punkty():
    bad = []
    t = _mk("TX5 карточка пункты", owner="CATEGORIST", category="categories",
            steps=[{"id": "s1", "title": "снять витрину"},
                   {"id": "s2", "title": "переписать цену"}],
            done=[("s1", "TX", "снял 4 карточки 0₽")])     # → derive in_progress
    card = Tk._card(io.StringIO(), t)
    for need in ("[in_progress · T-", "●", "○",
                 "— TX: снял 4 карточки 0₽", t["what"], t["id"]):
        if need not in card:
            bad.append(f"карточка: нет «{need}»")
    for ln in card.splitlines():
        if len(ln) > 78:
            bad.append(f"строка карточки >78 ({len(ln)})")
    return (not bad), " · ".join(bad) or \
        "карточка render_task: [in_progress·id] · ● с evidence · ○ открыт · ≤78"


def tx6_stroka_78():
    bad = []
    wide = list(_fxt())
    longA = _mk("X" * 230, owner="PRICER", store="atlas-express-film",
                urgency="high", priority=5)            # what длиннее ширины
    longB = _mk("TX6 тело-макс", owner="CONTROLLER", category="cards",
                body="зачем: " + "описание " * 40, urgency="normal", priority=55)
    wide += [longA, longB]
    txt = _txt(wide)
    for i, ln in enumerate(txt.splitlines(), 1):
        if len(ln) > 78:
            bad.append(f"строка {i} >78 ({len(ln)})")
    # хвост не теряется: у каждого ОТКРЫТОГО id есть строка с ним (row сшит по
    # остатку); закрытое (derive done) законно вне строк — его не требуем.
    for t in T_reg.open_only(wide):
        if t.get("id") not in txt:
            bad.append(f"id {t['id']} пропал из строк (хвост потерян?)")
    card = Tk._card(io.StringIO(), longA)
    for ln in card.splitlines():
        if len(ln) > 78:
            bad.append(f"карточка-строка >78 ({len(ln)})")
    return (not bad), " · ".join(bad) or \
        "весь лист + карточка ≤78 на синтетике-макс · id/владелец/хвост не теряются"


def tx7_lico_ne_pishet():
    src = (SOCC_ROOT / "socc_cli" / "tasks.py").read_text(encoding="utf-8")
    banned = ["write_text", "write_bytes", "json.dump", "os.remove", "os.unlink",
              "os.makedirs", "os.mkdir", "shutil", "requests", "urllib", "socket",
              "os.system", "rmtree", "subprocess"]
    hits = [b for b in banned if b in src]
    open_w = re.search(r"open\([^)]*,\s*[\"']([wa])[\"']", src)
    dsrc = (SOCC_ROOT / "socc_cli" / "dom.py").read_text(encoding="utf-8")
    if "subprocess" in dsrc:
        hits.append("dom.py теперь содержит subprocess (DH8 сломан)")
    ok = not hits and open_w is None
    return ok, f"токены tasks.py: {hits or '—'} · open-write: {open_w.group(0) if open_w else '—'}" \
        + (" · dom без шелл-исполнителя (DH8)" if not ok
           else " · tasks чистый read-слой · dom чист (DH8)")


def tx8_vhod_v_dome():
    bad = []
    # 1) cli роутер: `socc задания` → cmd_home → dispatch
    cli = (SOCC_ROOT / "socc_cli" / "cli.py").read_text(encoding="utf-8")
    if '"задания", "zadaniya", "tasks"' not in cli:
        bad.append("cli._HOME_KEYS без top-level «задания»")
    # 2) dom: пункт ЗАДАНИЯ/ТОПЛИВО в меню ДОМА + ветка dispatch + зонд
    dsrc = (SOCC_ROOT / "socc_cli" / "dom.py").read_text(encoding="utf-8")
    for tok in ('"tasks:home"', '_sep("ТОПЛИВО")', 'act == "tasks:home"',
                "def _tasks_probe", "socc_cli.tasks as Tk"):
        if tok not in dsrc:
            bad.append(f"dom.py без «{tok}»")
    # 3) home: ВХОДЫ + HELP + dispatch-ветка «задания»
    hsrc = (SOCC_ROOT / "socc_cli" / "home.py").read_text(encoding="utf-8")
    for tok in ('("socc задания", "ЗАДАНИЯ — весь реестр систем',
                '"socc задания"', 'if cmd in ("задания", "zadaniya", "tasks"):'):
        if tok not in hsrc:
            bad.append(f"home.py без «{tok}»")
    # 4) поведение меню: пустые probes → не падает, пункт есть
    try:
        rows = D.home_rows({})
    except Exception as e:
        bad.append(f"home_rows({{}}) упал: {e}")
        rows = []
    item = next((r for r in rows if r.get("action") == "tasks:home"), None)
    if item is None or "ЗАДАНИЯ" not in str(item.get("label", "")):
        bad.append("пункт tasks:home не в меню ДОМА")
    if not any(r.get("action") == "quit" for r in rows):
        bad.append("нет «Выйти из ДОМА» после ТОПЛИВО")
    # 5) функциональный e2e на tmp-сторе: `socc задания` rc 0 + плоский лист
    with tempfile.TemporaryDirectory() as td:
        store = Path(td) / "ymarket_tasks.json"
        T_reg.save(_fxt(), path=store)
        old = os.environ.get("YM_TASKS_PATH")
        out, inp = io.StringIO(), io.StringIO()
        try:
            os.environ["YM_TASKS_PATH"] = str(store)
            rc = H.dispatch(["задания"], out=out, inp=inp)
        finally:
            if old is None:
                os.environ.pop("YM_TASKS_PATH", None)
            else:
                os.environ["YM_TASKS_PATH"] = old
        t = out.getvalue()
        if rc != 0:
            bad.append(f"dispatch задания вернул {rc!r}")
        if ANSI.search(t):
            bad.append("ANSI в плоском прогоне socc задания")
        for need in ("ЗАДАНИЯ · ДОМ", "ПЛАНЁРКА · ОТКРЫТЫЕ",
                     "A приоритет 10 срочное"):
            if need not in t:
                bad.append(f"e2e: нет «{need}»")
    return (not bad), " · ".join(bad) or \
        "cli-роут · пункт/ветка/зонд в dom · ВХОДЫ/HELP/dispatch в home · e2e tmp rc0"


TESTS = [
    ("TX1  лицо_плоское", tx1_lico_ploskoe),
    ("TX2  честный_tri_state", tx2_chestnyi_tri_state),
    ("TX3  сводка_честна", tx3_svodka_chestna),
    ("TX4  важное_выше", tx4_vazhnoe_vyshe),
    ("TX5  карточка_пункты", tx5_kartochka_punkty),
    ("TX6  строка_≤78", tx6_stroka_78),
    ("TX7  лицо_не_пишет", tx7_lico_ne_pishet),
    ("TX8  вход_в_доме", tx8_vhod_v_dome),
]


def main():
    print("📋 SOCC · ДОМ · ЗАДАНИЯ (топливо) · ПРИЁМКА — герметично, read 0₽, движок не стартует")
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
        print("✅ ЗАДАНИЯ: лицо в ДОМЕ (socc задания) → планёрка/меню → карточка, честно, 0₽, не пишет")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

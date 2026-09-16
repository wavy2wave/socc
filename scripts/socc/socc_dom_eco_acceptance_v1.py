#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · ЭКОСИСТЕМА магазина — ПРИЁМКА (socc_cli/eco.py).

ЭКО — чистый read-навигатор разделов магазина (ЗАДАНИЯ → ЦИКЛЫ → СОТРУДНИКИ →
ДОНОР → АРТЕФАКТЫ, видение оператора; футер-резерв «ЗАКАЗЫ — проектируется»).
Провал в раздел — свой интерфейс; в ЦИКЛЫ провал в прогон = его отчёт/логи.
RUBICON цел: движок НЕ запускается, ничего не пишется, сети нет (0₽).

Герметично: payload-инъекция (как PU) + точечный мононе-патч дом-акцессоров
(_card_costs_map / _j по MATRIX_JSON / eco._donor_artifacts / eco._names) —
детерминизм без записи и без чтения живых данных за пределами read-сторов.

Законы EC1–EC12:
  EC1  навигатор_плоский — eco_store_text на StringIO без ANSI (CC8); 5 секций в
       порядке оператора + футер-резерв ЗАКАЗЫ; банд ЭКОСИСТЕМА · slug
  EC2  маркеры_честно   — absent→«реестр не материализован»; очередь→«наблюдений N»;
       прогоны закрыто/в работе по ПЛАНЁРКА (DH-честно); хеш дня в шапке
  EC3  задания_честно   — реестр-блок (ok: id · имя владельца · пунктов X/Y) +
       наблюдения (tag имя владельца · what); absent — честная строка
  EC4  циклы_прогоны    — _runs_rows группирует по ДОНОР; каждый прогон: старт/
       узлов/закрыт-ПЛАНЁРКА/в работе с «сухих N · живых N»
  EC5  цикл_отчёт_логи  — отчёт прогона: строки узлов HH:MM ✓/◌/✗ сухо|ЖИВОЙ +
       evidence-стрелки → PUBLISHED · остаток + строка закрытия/обрыва
  EC6  сотрудники_роли  — owners→строки с именем и занятостью; пусто честно
  EC7  донор_артефакты  — карточка донора + артефакты (фикстура); пусто честно
  EC8  артефакты_витрина— PUBLISHED из evidence · собрано карточек (матрица-фикстура)
       · карты закупа · закрытых/в работе · честный резерв «процента»
  EC9  эко_не_пишет     — исходник eco.py: нет записи/сети/исполнителя; dom.py без
       subprocess (DH8-разделение сохранено и после врезки ЭКО)
  EC10 ширина_тела      — навигатор+секции+отчёт (синтетика-макс + реальные сторы):
       каждая строка ≤78 → на 80×24 ничего не клипается
  EC11 вход_не_тити     — run_eco_store на StringIO → плоский текст + 'back'
  EC12 кнопка_эко       — из меню магазина: пункт/ветка ЭКОСИСТЕМА (tty кнопка и
       не-tty row) → плоский лист; dom-ветка dispatch цела
"""
import io
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SOCC_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOCC_ROOT) not in sys.path:
    sys.path.insert(0, str(SOCC_ROOT))

from socc_cli import eco                          # noqa: E402
from socc_cli import dom as D                      # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")
NOW = datetime(2026, 9, 3, 8, 30, 0)
TODAY = "2026-09-03"
SLUG = "atlas-express-film"

# Фолбэк-словарь ролей (тесты стабают eco._names — как офис в проде fail-soft).
_ROLES = {"CONTROLLER": "КОНТРОЛЁР", "DISPATCHER": "ДИСПЕТЧЕР",
          "BRIGADE": "БРИГАДИР", "MERCHANDISER": "ТОВАРОВЕД",
          "PRICER": "ЦЕНОВИК", "ZALIV": "СБОРЩИК", "HEAD": "ГОЛОВА"}


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _ts(hhmm):
    return f"{TODAY}T{hhmm}:00"


def _names_stub():
    """Детерминированное имя-маппинг вместо чтения офиса (герметично)."""
    return dict(_ROLES)


# ── фикстура payload магазина (как у движка; всё — в памяти) ──────────────────
def _pl_for(slug=SLUG, *, ledger=None, queue=None, reg=("absent", []),
            info=None):
    info = info or dict(business_id="184481130", campaign_id="149215943",
                        warehouse_id="2390811",
                        donor_category="vozdushno-puzyrkovaya-plenka",
                        builder="film", builder_slug="puzyrkovaya-plenka",
                        markup=8.0, stock_count=100,
                        note="Плёночная партия ARB-* — ДОКАЗАНА живьём (витрина)")
    if ledger is None:
        # прогон 1 — закрыт ПЛАНЁРКОЙ (сухо) · прогон 2 — в работе (оборвался, живой)
        ledger = [
            dict(node="ДОНОР",   verdict="PASS", ts=_ts("08:07"),
                 note="донор плёнки: 4 словаря", dry=True),
            dict(node="СБОРКА",  verdict="PASS", ts=_ts("08:20"),
                 note="собрано 4 полных карточек", dry=True),
            dict(node="ЗАЛИВ",   verdict="PASS", ts=_ts("09:05"),
                 note="контент карточек vendor", dry=True),
            dict(node="ВИТРИНА", verdict="PASS", ts=_ts("09:20"), dry=True),
            dict(node="ОСТАТКИ", verdict="PASS", ts=_ts("09:25"),
                 note="FIT=100 на склад 2390811", dry=True),
            dict(node="СВЕРКА",  verdict="PASS", ts=_ts("09:31"),
                 evidence={"ARB-1": dict(placement=dict(status="PUBLISHED"),
                                         stock=100)}, dry=True),
            dict(node="ПЛАНЁРКА", verdict="PASS", ts=_ts("09:40"),
                 note="пульс: PASS=…  цепь дошла", dry=True),
            dict(node="ДОНОР",   verdict="PASS", ts=_ts("10:00"),
                 note="повтор разведки после слова оператора", dry=False),
            dict(node="СБОРКА",  verdict="PASS", ts=_ts("10:12"), dry=False),
            dict(node="ЗАЛИВ",   verdict="FAIL", ts=_ts("10:15"),
                 note="TypeError: узел упал последним ходом — чинить",
                 dry=False),
        ]
    if queue is None:
        queue = [
            dict(tag="СВЕРКА", urgency="low", owner="CONTROLLER",
                 what="Матрица отстала от витрины: карточки PUBLISHED, а offer_id "
                      "в матрице ещё пуст — поправить живым чтением",
                 evidence="леджер СВЕРКА-PASS (PUBLISHED)"),
            dict(tag="ЧИНИТЬ", urgency="high", owner="DISPATCHER",
                 what="Узел «ЗАЛИВ» упал последним ходом — посмотреть",
                 evidence="леджер ЗАЛИВ-FAIL"),
        ]
    return dict(store=slug, info=info,
                pulse=dict(date=TODAY, run_verdicts={"PASS": 3, "DRY": 3}),
                ledger=list(ledger), queue=list(queue), registry=tuple(reg))


def _tasks_reg():
    """Реестр («ok»): 2 durable-задачи с пунктами — для EC3/EC6/EC8."""
    return ("ok", [
        dict(id="T-101", owner="CONTROLLER", category="vozdushno-puzyrkovaya-plenka",
             what="Выправить матрицу после живого чтения", urgency="high",
             steps=[dict(state="done", what="снять карточки"),
                    dict(state="todo", what="поправить offer_id")]),
        dict(id="T-102", owner="BRIGADE", category="…",
             what="Прогнать сухой цикл дня (0₽)", urgency="low",
             steps=[dict(state="todo", what="dry")]),
    ])


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


def _patch_matrix_and_costs(mat_rows=None, costs=None):
    """Шим D._j по MATRIX_JSON + D._card_costs_map → детерминизм без записи."""
    mat_rows = mat_rows if mat_rows is not None else {
        "c1": dict(status="собран", offer_id="", category="puzyrkovaya-plenka"),
        "c2": dict(status="собран", offer_id="", category="puzyrkovaya-plenka"),
        "c3": dict(status="собран", offer_id="", category="puzyrkovaya-plenka"),
        "c4": dict(status="черновик", offer_id="", category="puzyrkovaya-plenka"),
        "c5": dict(status="собран", offer_id="ARB-X", category="puzyrkovaya-plenka"),
    }
    real_j = D._j
    mjson = D.MATRIX_JSON
    if costs is None:
        costs = {"ARB-1": 300, "ARB-2": 250}

    def _shim(p, default=None):
        if os.fspath(p) == os.fspath(mjson):
            return {"rows": mat_rows}
        return real_j(p, default)

    return _patch(
        (D, "_j", _shim),
        (D, "_card_costs_map", lambda: dict(costs)),
        (eco, "_names", _names_stub),
    )


def _body_lines():
    """Строки ЭКО-тел: синтетика-макс (длинные note/what) + реальные сторы."""
    wide = _pl_for(ledger=[dict(node="ДОНОР", verdict="PASS", ts=_ts("12:22")),
                           dict(node="ОСТАТКИ", verdict="FAIL", ts=_ts("13:01"),
                                note="остатки не легли: None после чтения стока — "
                                     "нужен повтор чтения живьём, а не выдумывание"),
                           dict(node="ПЛАНЁРКА", verdict="PASS", ts=_ts("13:02"))],
                   queue=[dict(tag="СВЕРКА", urgency="low", owner="CONTROLLER",
                               what="Матрица отстала от витрины: карточки PUBLISHED, "
                                    "а offer_id в матрице всё ещё пуст — поправить "
                                    "матрицу живым чтением и прогнать сухо (0₽)",
                               evidence="леджер СВЕРКА-PASS")])
    with _patch_matrix_and_costs():
        for ln in eco_store_all(SLUG, _pl_for()):
            yield ln
        for ln in eco_store_all(SLUG, wide):
            yield ln
        for slug in sorted(D._stores_map()):
            yield from eco_store_all(slug)


def eco_store_all(slug, pl=None):
    """Все строки, что печатает ЭКО по магазину (плоский лист = те же разделы)."""
    if pl is None:
        txt = eco.eco_store_text(io.StringIO(), slug)
    else:
        txt = eco.eco_store_text(io.StringIO(), slug, pl=pl)
    return txt.split("\n")


def eco_flat(slug=SLUG, pl=None):
    return eco.eco_store_text(io.StringIO(), slug, pl=pl)


# ─────────────────────────── ТЕСТЫ ───────────────────────────

def ec1_navigator_ploskii():
    with _patch_matrix_and_costs():
        txt = eco_flat(SLUG, _pl_for())
    bad = []
    if ANSI.search(txt):
        bad.append("ANSI в плоском листе")
    order = [txt.find(f"{n}. {lab}") for n, lab in
             [(1, "ЗАДАНИЯ"), (2, "ЦИКЛЫ"), (3, "СОТРУДНИКИ"), (4, "ДОНОР"),
              (5, "АРТЕФАКТЫ")]]
    if any(i < 0 for i in order) or order != sorted(order):
        bad.append(f"секции не в порядке оператора: {order}")
    for need in (f"ЭКОСИСТЕМА · {SLUG}", "ЗАКАЗЫ и другие разделы — проектируются",
                 "РАЗДЕЛЫ · НАВИГАТОР"):
        if need not in txt:
            bad.append(f"нет «{need}»")
    return (not bad), " · ".join(bad) or \
        "плоский лист: 5 секций в порядке оператора + резерв ЗАКАЗЫ, без ANSI (CC8)"


def ec2_markery_chestno():
    with _patch_matrix_and_costs():
        # absent-реестр + очередь → честные маркеры
        m = eco._section_markers(io.StringIO(), _pl_for(), SLUG)
        if "реестр не материализован" not in m["задания"]:
            bad0 = "absent не дал «реестр не материализован»"
        elif "наблюдений 2" not in m["задания"]:
            bad0 = "нет «наблюдений 2»"
        else:
            bad0 = ""
        if "прогонов 2 · закрыто 1 · в работе 1" not in m["циклы"]:
            bad0 += " · маркер циклов нечестен по ПЛАНЁРКЕ"
        if "в работе ролей" not in m["сотрудники"]:
            bad0 += " · нет «в работе ролей»"
        # ok-реестр → «задач открыто N»
        pl = _pl_for(reg=_tasks_reg())
        m2 = eco._section_markers(io.StringIO(), pl, SLUG)
        if "задач открыто 2" not in m2["задания"]:
            bad0 += " · ok-реестр не дал «задач открыто 2»"
        # хеш дня в шапке (как DH13, только через eco-рендер) — ищем сам токен,
        # не полагаясь на машинную дату
        txt = eco_flat(SLUG, _pl_for())
        if not re.search(r"хеш [0-9a-f]{10}", txt):
            bad0 += " · хеш дня (10-hex) не в шапке"
    bad = bad0.lstrip(" · ") or None
    return (bad is None), bad or \
        "маркеры: реестр absent/ok · наблюдения · прогоны по ПЛАНЁРКЕ · роли · хеш дня"


def ec3_zadania_chestno():
    with _patch_matrix_and_costs():
        out = io.StringIO()
        L = eco._tasks_lines(out, _pl_for(reg=_tasks_reg()))
    txt = "\n".join(L)
    bad = []
    for need in ("РЕЕСТР · DURABLE", "T-101", "КОНТРОЛЁР", "пунктов 1/2",
                 "НАБЛЮДЕНИЯ · ЖИВАЯ ОЧЕРЕДЬ", "[СВЕРКА]", "[ЧИНИТЬ]",
                 "ДИСПЕТЧЕР"):
        if need not in txt:
            bad.append(f"нет «{need}»")
    if "[СВЕРКА]" in txt and "СВЕРКА" not in txt:
        bad.append("тег/имя потерялись")
    # absent → честная строка про ЦИКЛ-ДЕНЬ
    out2 = io.StringIO()
    L2 = eco._tasks_lines(out2, _pl_for())
    t2 = "\n".join(L2)
    if "реестр не материализован" not in t2 or "ЦИКЛ-ДЕНЬ" not in t2:
        bad.append("absent-реестр нечестно")
    return (not bad), " · ".join(bad) or \
        "реестр-блок (id·имя·пункты X/Y) + наблюдения (tag·имя); absent честен"


def ec4_tsikly_progony():
    runs = eco._runs_rows(_pl_for()["ledger"])
    bad = []
    if len(runs) != 2:
        bad.append(f"прогонов {len(runs)} (ждём 2)")
    m1, m2 = eco._run_meta(runs[0]), eco._run_meta(runs[1])
    if not (m1["closed"] and m2["closed"] is False):
        bad.append(f"закрытость: {m1['closed']}/{m2['closed']} (ждём True/False)")
    if m1["n"] != 7 or m2["n"] != 3:
        bad.append(f"узлов: {m1['n']}/{m2['n']} (ждём 7/3)")
    if m1["verdict"] != "PASS" or m2["node"] != "ЗАЛИВ":
        bad.append(f"конец: {m1['verdict']}/{m2['node']}")
    if m2["live"] != 3 or m1["dry"] != 7:
        bad.append(f"сухо/живой: {m1['dry']}/{m2['live']} (ждём 7/3)")
    # заголовок секции честный
    out = io.StringIO()
    L = eco._cycles_lines(out, SLUG, _pl_for())
    t = "\n".join(L)
    if "прогонов 2" not in t or "закрыт ПЛАНЁРКА" not in t \
            or "в работе — стоп «ЗАЛИВ»" not in t:
        bad.append("заголовки прогонов нечестны")
    return (not bad), " · ".join(bad) or \
        f"2 прогона по ДОНОР: {m1['n']}→ПЛАНЁРКА · {m2['n']}→стоп ЗАЛИВ · сухих {m1['dry']}/живых {m2['live']}"


def ec5_tsikl_otchet_logi():
    pl = _pl_for()
    runs = eco._runs_rows(pl["ledger"])
    out = io.StringIO()
    L = eco._run_lines(out, SLUG, runs[0], pl)
    t = "\n".join(L)
    bad = []
    for need in ("ПРОГОН", "старт 08:07", "узлов 7", "закрыт ПЛАНЁРКА",
                 "✓ ДОНОР", "сухо", "→ ARB-1 PUBLISHED · остаток 100",
                 "прогон закрыт"):
        if need not in t:
            bad.append(f"в закрытом отчёте нет «{need}»")
    L2 = eco._run_lines(out, SLUG, runs[1], pl)
    t2 = "\n".join(L2)
    for need in ("старт 10:00", "узлов 3", "ЖИВОЙ", "✗ ЗАЛИВ",
                 "прогон не закрыт"):
        if need not in t2:
            bad.append(f"в оборванном отчёте нет «{need}»")
    if "живых 3" not in t2 or "сухих 0" not in t2:
        bad.append("живые/сухие строки в отчёте нечестны")
    return (not bad), " · ".join(bad) or \
        "отчёт прогона: узлы HH:MM ✓/◌/✗ сухо|ЖИВОЙ · evidence PUBLISHED · закрытие/обрыв"


def ec6_sotrudniki_roli():
    with _patch_matrix_and_costs():
        out = io.StringIO()
        pl = _pl_for(reg=_tasks_reg())
        emps = eco._employees(pl)
        names = {e["owner"] for e in emps}
        if names != {"CONTROLLER", "DISPATCHER", "BRIGADE"}:
            return False, f"owners {names} (ждём CONTROLLER/DISPATCHER/BRIGADE)"
        L = eco._employees_lines(out, pl)
    t = "\n".join(L)
    bad = []
    for need in ("КОНТРОЛЁР (CONTROLLER)", "ДИСПЕТЧЕР (DISPATCHER)",
                 "[ЧИНИТЬ] ДИСПЕТЧЕР"):
        if need not in t:
            bad.append(f"нет «{need}»")
    # пусто → честно
    L2 = eco._employees_lines(out, _pl_for(ledger=[], queue=[]))
    if "активных в магазине нет" not in "\n".join(L2):
        bad.append("пустой магазин нечестен")
    return (not bad), " · ".join(bad) or \
        "роли→имя+занятость · пусто: «активных в магазине нет»"


def ec7_donor_artefakty():
    pl = _pl_for()
    arts = [dict(name=f"ymarket_runner_donor_puzyrkovaya-plenka_2026-09-01_22-01-32.json",
                 ts="2026-09-01T22:01:32"),
            dict(name=f"ymarket_runner_donor_puzyrkovaya-plenka_2026-09-01_22-00-46.json",
                 ts="2026-09-01T22:00:46")]
    with _patch_matrix_and_costs(), \
            _patch((eco, "_donor_artifacts", lambda info: list(arts))):
        out = io.StringIO()
        L = eco._donor_lines(out, pl)
    t = "\n".join(L)
    bad = []
    for need in ("ДОНОР · РАЗВЕДКА ЗЕМЕЛЬ · vozdushno-puzyrkovaya-plenka",
                 "builder film", "маржа ×8.0", "остаток 100",
                 "АРТЕФАКТЫ ОРГАНА", "файлов 2 · свежие сверху"):
        if need not in t:
            bad.append(f"нет «{need}»")
    # пусто (категория без разведки) → честно
    with _patch_matrix_and_costs():
        L2 = eco._donor_lines(out, _pl_for(ledger=[],
                                           info=dict(donor_category="sintet-cat")))
    t2 = "\n".join(L2)
    if "артефактов донора нет" not in t2:
        bad.append("пустая разведка нечестна")
    return (not bad), " · ".join(bad) or \
        "карточка донора (категория·builder·маржа·остаток) + артефакты · пусто честно"


def ec8_artefakty_vitrina():
    with _patch_matrix_and_costs():
        out = io.StringIO()
        pl = _pl_for(reg=_tasks_reg())
        L = eco._art_lines(out, SLUG, pl)
    t = "\n".join(L)
    bad = []
    for need in ("✓ ARB-1 · остаток 100", "собрано карточек 3",
                 "карт закупа 2 · сумма 550₽", "закрыто 1 · в работе 1",
                 "процент выполнения задания — когда появится реестр"):
        if need not in t:
            bad.append(f"нет «{need}»")
    # собрано 3: фикстура матрицы — 3 «собран» c offer пустым по категории
    return (not bad), " · ".join(bad) or \
        "PUBLISHED из evidence · собрано из матрицы · карты закупа · закрытые · резерв %"


def ec9_eko_ne_pishet():
    """Закон разделения сохранён и после врезки ЭКО: eco — read 0₽."""
    src = (SOCC_ROOT / "socc_cli" / "eco.py").read_text(encoding="utf-8")
    banned = ["write_text", "write_bytes", "json.dump", "os.remove", "os.unlink",
              "os.makedirs", "os.mkdir", "shutil", "requests", "urllib", "socket",
              "os.system", "rmtree", "subprocess"]
    hits = [b for b in banned if b in src]
    open_w = re.search(r"open\([^)]*,\s*[\"']([wa])[\"']", src)
    dsrc = (SOCC_ROOT / "socc_cli" / "dom.py").read_text(encoding="utf-8")
    if "subprocess" in dsrc:
        hits.append("dom.py теперь содержит subprocess (DH8 сломан)")
    ok = not hits and open_w is None
    return ok, f"токены eco: {hits or '—'} · open-write: {open_w.group(0) if open_w else '—'}" \
        + (" · dom без subprocess (DH8)" if not ok else " · eco без записи/сети/исполнителя · dom чист (DH8)")


def ec10_shirina_tela():
    long_lines = []
    with _patch_matrix_and_costs():
        for ln in _body_lines():
            if len(str(ln)) > 78:
                long_lines.append(str(ln))
    return (not long_lines), \
        f"строк >78: {len(long_lines)}" + (f" :: {long_lines[0][:90]}" if long_lines else " · навигатор/секции/отчёты в 78")


def ec11_vhod_ne_titi():
    bad = []
    with _patch_matrix_and_costs():
        out, inp = io.StringIO(), io.StringIO()
        rc = eco.run_eco_store(out, inp, SLUG)
    t = out.getvalue()
    if rc != "back":
        bad.append(f"run_eco_store вернул {rc!r} (ждём 'back')")
    if f"ЭКОСИСТЕМА · {SLUG}" not in t or ANSI.search(t):
        bad.append("не-tty ЭКО не выдал плоского листа (CC8)")
    return (not bad), " · ".join(bad) or "не-tty путь: плоский лист + 'back' (движок не стартует)"


def ec12_knopka_eko():
    bad = []
    rows = D._store_action_rows()
    if not any(r.get("action") == "eco:store" for r in rows):
        bad.append("нет eco:store в _store_action_rows (не-tty меню)")
    # tty-кнопка + ветка dispatch — по исходнику врезки (аддитивно, перед НАЗАД)
    dsrc = (SOCC_ROOT / "socc_cli" / "dom.py").read_text(encoding="utf-8")
    if '("eco:store", "ЭКО")' not in dsrc:
        bad.append("tty-кнопка ЭКО не врезана в ДЕЙСТВИЯ магазина")
    if 'act == "eco:store"' not in dsrc:
        bad.append("нет dispatch-ветки act == \"eco:store\"")
    # поведение не-tty: из меню магазина выбираем ЭКО → плоский лист, движок не стартует.
    # Выбор по подстроке «экосистема», а не цифре: номер eco в ДЕЙСТВИЯХ сдвигается при росте
    # меню (ЖИВОЙ/АВТО/ПЛАН/ЗАДАНИЯ/ЭКО/НАЗАД) — метка уникальна и не боится вставок.
    with _patch_matrix_and_costs(), \
            _patch((D, "store_payload", lambda s, **k: _pl_for(s))):
        out, inp = io.StringIO(), io.StringIO("экосистема\nq\n")
        D.run_store(out, inp, SLUG)
    t = out.getvalue()
    if f"ЭКОСИСТЕМА · {SLUG}" not in t or ANSI.search(t):
        bad.append("выбор ЭКО из меню магазина не дал плоского листа (CC8)")
    return (not bad), " · ".join(bad) or \
        "ЭКО в ДЕЙСТВИЯХ (кнопка tty + row не-tty) · ветка dispatch · выбор → плоский лист"


TESTS = [
    ("EC1  навигатор_плоский", ec1_navigator_ploskii),
    ("EC2  маркеры_честно", ec2_markery_chestno),
    ("EC3  задания_честно", ec3_zadania_chestno),
    ("EC4  циклы_прогоны", ec4_tsikly_progony),
    ("EC5  цикл_отчёт_логи", ec5_tsikl_otchet_logi),
    ("EC6  сотрудники_роли", ec6_sotrudniki_roli),
    ("EC7  донор_артефакты", ec7_donor_artefakty),
    ("EC8  артефакты_витрина", ec8_artefakty_vitrina),
    ("EC9  эко_не_пишет", ec9_eko_ne_pishet),
    ("EC10 ширина_тела", ec10_shirina_tela),
    ("EC11 вход_не_тити", ec11_vhod_ne_titi),
    ("EC12 кнопка_эко", ec12_knopka_eko),
]


def main():
    print("🌐 SOCC · ДОМ · ЭКОСИСТЕМА магазина · ПРИЁМКА — герметично, read 0₽, движок не стартует")
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
        print("✅ ЭКО: навигатор → разделы → отчёты прогонов, честно, 0₽, не пишет")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

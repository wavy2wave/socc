#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARBITER АВТОПИЛОТ (СУХОЙ) — ПРИЁМКА. Законы, а не «оно запустилось». Сухо, 0₽, без сети.

Главный закон органа-руки: автопилот ФИЗИЧЕСКИ не умеет в БОЕВОЙ режим.

  A1  hard_dry_invariant     — run() зовёт run_day СТРОГО dry=True, commit=False (RUBICON)
  A2  no_commit_path         — у run() НЕТ параметра commit; в исходнике нет строчного commit=True:
                              боевой рубильник run_day не добавляется. Авто-сев локального реестра
                              (слово 03.09) — через КОНСТАНТУ _SEED_COMMIT (CD6), НЕ run_day.
  A3  log_written            — прогон оставляет читаемый след: отчёт + строка JSON с фактами
  A4  log_failsoft           — если рендер отчёта упал, лог всё равно пишется, автопилот не падает
  A5  head_source_wired      — 'none' → носа спроса нет (None); 'wb' → ленивый thunk построен
  A6  result_shape_honest    — итог несёт dry/commit/businessId/провалы — не врёт о режиме
  A8  auto_seed_wired        — тик зовёт авто-сев _seed_tasks; итог несёт сводку tasks_seed
  A9  seed_local_store_only  — НАСТОЯЩИЙ сев пишет ТОЛЬКО в стор из YM_TASKS_PATH; канон SOCC не тронут
  A10 seed_failsoft          — падение одного источника сева не роняет тик; второй источник всё равно
                               сеется (fail-soft, след — в лог)
  A11 plan_first_invoked     — run() зовёт ПЛАНЁРКУ (_plannerka) ПЕРВЫМ оператором тела, ДО run_day
                               (УТРО ПРЕЖДЕ РАБОТ); итог несёт сводку plan
  A12 plan_local_store_only  — НАСТОЯЩАЯ планёрка пишет ТОЛЬКО plans/ymarket_plan_<дата>.json в
                               YM_PLAN_DIR; канон SOCC байт-в-байт не тронут
  A13 plan_failsoft          — падение движка планёрки (нет build_plan) не роняет тик: ok=False,
                               след в лог (fail-soft)
  A14 sovet_wired            — run() зовёт СОВЕТ (_sovet) шагом 0.5 СРАЗУ после ПЛАНЁРКИ, до run_day;
                               итог несёт сводку sovet (протокол даты, шаг 0.5, 0₽)
  A15 sovet_local_store_only — НАСТОЯЩИЙ совет пишет ТОЛЬКО sovet/ymarket_sovet_<дата>.json в
                               YM_SOVET_DIR; канон SOCC байт-в-байт не тронут (протокол — локальный стор)
  A16 spory_wired            — run() зовёт СПОРЫ (_spory, слой 2 СОВЕТА) шагом 0.5b СРАЗУ после СОВЕТА,
                               до run_day; итог несёт сводку spory (прение даты, слой 2, 0₽)
  A17 spory_local_store_only — НАСТОЯЩИЕ споры пишут ТОЛЬКО spory/ymarket_spory_<дата>.json в
                               YM_SPORY_DIR; канон SOCC байт-в-байт не тронут (прение — локальный стор)
  A18 cycle_pulse_wired      — run() зовёт СУХОЙ ЦИКЛ-1 (_cycle_pulse) шагом «сердцебиение» ПОСЛЕ run_day
                               и ДО авто-сева ЗАДАНИЙ; итог несёт сводку cycle_pulse (24/7: пульс/КПИ
                               копятся без входа оператора; свежий пульс → авто-сев НЕ сеет «устарел»)
  A19 cycle_pulse_dry_only   — _cycle_pulse сух по построению: пульс устарел → ОДИН сухой прогон движка
                               (dry), свеж → пропуск; прогон упал → fail-soft (ok=False, тик живёт);
                               НИКАКИХ живых write-узлов за heartbeat нет (0₽)
  A20 pulse_task_close_honest— зависшие «Пульс {store} устарел» закрываются ТОЛЬКО когда текущий пульс
                               СТРОГО свежее зафиксированной даты (дыра реально закрыта, TZ8 evidence);
                               задача с датой == пульсу остаётся открытой (сигнал честен); локальный стор
"""
import os
import sys
import json
import inspect
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
SCRIPTS = MINT.parent
for p in (str(ARB), str(MINT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_autopilot_v1 as ap        # noqa: E402
import ymarket_report_v1 as report       # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _fake_day(**kw):
    """Стаб суточного цикла: НИЧЕГО не читает, возвращает минимум + эхо режима (для проверки закона)."""
    return {"ts": "2026-08-16T00:00:00+00:00", "date": "2026-08-16", "ok": True,
            "dry": kw.get("dry"), "commit": kw.get("commit"),
            "business_id_known": True, "campaign_id_known": True,
            "failures": [], "burning": {"count": 0, "items": []},
            "kpis": {"quality_index": None},
            "_captured": kw}


def _with_stub_day(fn):
    """Подменить ap.day.run_day, ap._seed_tasks, ap._plannerka, ap._sovet, ap._spory и ap._cycle_pulse на
    стабы, вернуть (результат, captured).

    _seed_tasks/_plannerka/_sovet/_spory стабим ОБЯЗАТЕЛЬНО: настоящие пишут локальные сторы (реестр
    заданий / план дня / протокол совета / прение споров) — тесты герметичны (не трогают канон SOCC).
    _cycle_pulse стабим ОБЯЗАТЕЛЬНО: настоящий зовёт сухой ЦИКЛ-1 (сеть-READ донора/кабинета) — тестам
    сердцебиение НЕ нужно, только факт вызова (счётчик).
    Счётчики вызовов — в отдельном dict (run_day-стаб очищает captured эхом kwargs; счётчики
    планёрки/совета/споров/пульса стоят ДО run_day в порядке вызова — их нельзя затирать). Всегда восстанавливает.
    """
    old_day = ap.day.run_day
    old_seed = ap._seed_tasks
    old_plan = ap._plannerka
    old_sovet = ap._sovet
    old_spory = ap._spory
    old_pulse = ap._cycle_pulse
    captured = {}
    counters = {"_seed_calls": 0, "_plan_calls": 0, "_sovet_calls": 0, "_spory_calls": 0,
                "_pulse_calls": 0}

    def cap(**kw):
        captured.clear()
        captured.update(kw)
        return _fake_day(**kw)

    def cap_seed(d):
        counters["_seed_calls"] += 1
        return {"ok": True, "lines": [], "form": 0, "seed": 0}

    def cap_plan():
        counters["_plan_calls"] += 1
        return {"ok": True, "date": "2026-09-04", "decisions": [], "lines": []}

    def cap_sovet():
        counters["_sovet_calls"] += 1
        return {"ok": True, "date": "2026-09-04", "gathered": False, "already": False,
                "dry": True, "file": None, "lines": []}

    def cap_spory():
        counters["_spory_calls"] += 1
        return {"ok": True, "date": "2026-09-04", "gathered": False, "already": False,
                "dry": True, "file": None, "lines": []}

    def cap_pulse(**kw):
        counters["_pulse_calls"] += 1
        return {"ok": True, "ran": [], "skipped": [], "closed": [], "lines": []}

    ap.day.run_day = cap
    ap._seed_tasks = cap_seed
    ap._plannerka = cap_plan
    ap._sovet = cap_sovet
    ap._spory = cap_spory
    ap._cycle_pulse = cap_pulse
    try:
        res = fn()
    finally:
        ap.day.run_day = old_day
        ap._seed_tasks = old_seed
        ap._plannerka = old_plan
        ap._sovet = old_sovet
        ap._spory = old_spory
        ap._cycle_pulse = old_pulse
    return res, {**captured, **counters}


def _tmp_log():
    fd, p = tempfile.mkstemp(prefix="ap_log_", suffix=".log")
    os.close(fd)
    os.environ["ARBITER_AUTOPILOT_LOG"] = p
    return Path(p)


# ─────────────────────────── ТЕСТЫ ───────────────────────────

def a1_hard_dry_invariant():
    """RUBICON: как бы ни звали — цикл получает dry=True, commit=False. Иначе автопилот опасен."""
    _tmp_log()
    (res, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
    ok = cap.get("dry") is True and cap.get("commit") is False
    return ok, f"переданное в run_day: dry={cap.get('dry')} commit={cap.get('commit')}"


def a2_no_commit_path():
    """Структурно: у run() нет ручки commit и в исходнике нет СТРОЧНОГО commit=True — боевой рубильник
    run_day не добавляется. Авто-сев локального реестра (слово 03.09) идёт через КОНСТАНТУ _SEED_COMMIT
    (CD6, файл SOCC — не рука ЯМ), а не через параметр/литерал run_day."""
    params = list(inspect.signature(ap.run).parameters)
    no_param = "commit" not in params
    src = inspect.getsource(ap)
    no_true = "commit=True" not in src and "commit = True" not in src
    return no_param and no_true, f"params={params} · нет commit=True в исходнике={no_true}"


def a3_log_written():
    """След прогона: файл лога получает и человеческий отчёт, и машинную строку JSON с фактами."""
    lp = _tmp_log()
    report.render_day = lambda d, **k: "СТАБ-ОТЧЁТ-ДНЯ"      # изолируем от реального рендера
    (res, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
    txt = lp.read_text(encoding="utf-8")
    ok = "СТАБ-ОТЧЁТ-ДНЯ" in txt and "JSON" in txt and '"commit"' in txt and '"dry"' in txt
    return ok, f"в логе есть отчёт+JSON+режим: {ok} (размер {len(txt)}б)"


def a4_log_failsoft():
    """Рендер отчёта упал → лог всё равно пишется («отчёт не отрендерился»), автопилот НЕ падает."""
    lp = _tmp_log()

    def boom(d, **k):
        raise RuntimeError("рендер намеренно упал")

    report.render_day = boom
    try:
        (res, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
        survived = res.get("dry") is True
    except Exception as e:
        return False, f"автопилот упал вместе с рендером: {type(e).__name__}: {e}"
    txt = lp.read_text(encoding="utf-8")
    ok = survived and "не отрендерился" in txt
    return ok, f"пережил падение рендера={survived}, причина в логе={'не отрендерился' in txt}"


def a5_head_source_wired():
    """none → носа спроса нет (fn=None); wb → построен ленивый thunk (callable), сеть НЕ трогается."""
    _tmp_log()
    report.render_day = lambda d, **k: "x"
    (_, cap_none) = _with_stub_day(lambda: ap.run(head_source="none"))
    none_ok = cap_none.get("head_source_fn") is None
    (_, cap_wb) = _with_stub_day(lambda: ap.run(head_source="wb"))
    fn = cap_wb.get("head_source_fn")
    wb_ok = callable(fn)          # thunk построен; сеть будет только при его вызове (его тут не зовём)
    return none_ok and wb_ok, f"none→fn None={none_ok} · wb→thunk callable={wb_ok}"


def a6_result_shape_honest():
    """Итог не врёт о режиме: dry=True, commit=False и присутствуют факты кабинета/провалов."""
    _tmp_log()
    report.render_day = lambda d, **k: "x"
    (res, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
    keys = {"dry", "commit", "business_id_known", "failures", "burning"}
    ok = res.get("dry") is True and res.get("commit") is False and keys.issubset(res)
    return ok, f"dry={res.get('dry')} commit={res.get('commit')} ключи-полны={keys.issubset(res)}"


def a7_zaliv_wired_by_default():
    """Залив живёт САМ: без env preflight_fn всё равно ленивый thunk (не None) — цикл не ждёт команды."""
    _tmp_log()
    report.render_day = lambda d, **k: "x"
    for k in ("YM_ZALIV_DONOR", "YM_ZALIV_SLUG"):
        os.environ.pop(k, None)          # гарантируем чистоту: env НЕ задан
    (_, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
    fn = cap.get("preflight_fn")
    wired = callable(fn)                 # thunk построен лениво; сеть/файлы — только при его вызове (его не зовём)
    # дефолтная пара не пуста и реальна (документированный контракт двух слагов, F6)
    d, s = ap._ZALIV_DEFAULT_DONOR, ap._ZALIV_DEFAULT_SLUG
    ok = wired and bool(d) and bool(s) and d != s
    return ok, f"preflight_fn callable={wired} · дефолт донор={d!r} slug={s!r}"


def a8_auto_seed_wired():
    """Авто-сев ЗАДАНИЙ встроен в тик: run() зовёт _seed_tasks (счётчик ≥1), итог несёт сводку tasks_seed."""
    _tmp_log()
    report.render_day = lambda d, **k: "x"
    (res, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
    called = cap.get("_seed_calls", 0) >= 1
    summary = res.get("tasks_seed")
    ok = called and isinstance(summary, dict) and summary.get("ok") is True
    return ok, f"run() позвал авто-сев={called} · в итоге tasks_seed ok={ok}"


def a9_seed_local_store_only():
    """НАСТОЯЩИЙ авто-сев пишет ТОЛЬКО в стор из YM_TASKS_PATH; канон SOCC байт-в-байт не тронут.

    Герметично: env перекрывает адрес реестра → form/seed реально сеются в песочницу, а не в канон.
    Сети нет (сканы — файлы runtime; сидер — файлы + локальный write). Канон снимаем ДО установки env.
    """
    os.environ.pop("YM_TASKS_PATH", None)
    import ymarket_tasks_v1 as _T                          # env чист → настоящий канон SOCC
    real_canon = _T.task_path()
    before = real_canon.read_bytes() if real_canon.exists() else None
    tmpdir = Path(tempfile.mkdtemp())
    tstore = tmpdir / "tasks.json"
    os.environ["ARBITER_AUTOPILOT_LOG"] = str(tmpdir / "ap.log")
    os.environ["YM_TASKS_PATH"] = str(tstore)
    try:
        res = ap._seed_tasks({})                            # НАСТОЯЩИЙ сев (form+seed, 0₽, файлы)
        wrote = tstore.exists() and tstore.stat().st_size > 0
    except Exception as e:
        res, wrote = None, False
        boom = e
    finally:
        os.environ.pop("YM_TASKS_PATH", None)
        os.environ.pop("ARBITER_AUTOPILOT_LOG", None)
    after = real_canon.read_bytes() if real_canon.exists() else None
    if res is None:
        return False, f"настоящий сев упал: {type(boom).__name__}: {boom}"
    ok = (res or {}).get("ok") is True and wrote and before == after
    return ok, (f"ok={res.get('ok')} · tmp-store={tstore.stat().st_size if wrote else 0}б"
                f" · канон SOCC не тронут={before == after} · form={res.get('form')} seed={res.get('seed')}")


def a10_seed_failsoft():
    """Сев fail-soft: падение одного источника (form) тик НЕ роняет — след в лог, seed всё равно сеется."""
    import types as _types
    tmpdir = Path(tempfile.mkdtemp())
    tstore = tmpdir / "tasks.json"
    os.environ["ARBITER_AUTOPILOT_LOG"] = str(tmpdir / "ap.log")
    os.environ["YM_TASKS_PATH"] = str(tstore)
    poisoned = _types.SimpleNamespace()                    # без form → cyd.form(...) упадёт AttributeError
    mods = sys.modules
    prev = mods.get("ymarket_cycle_day_v1")
    mods["ymarket_cycle_day_v1"] = poisoned
    try:
        res = ap._seed_tasks({})
    except Exception as e:
        res, boom = None, e
    finally:
        if prev is not None:
            sys.modules["ymarket_cycle_day_v1"] = prev
        else:
            sys.modules.pop("ymarket_cycle_day_v1", None)
        os.environ.pop("YM_TASKS_PATH", None)
        os.environ.pop("ARBITER_AUTOPILOT_LOG", None)
    if res is None:
        return False, f"сев упал вместе с источником: {type(boom).__name__}: {boom}"
    lines = " | ".join(res.get("lines") or [])
    form_failed = "form НЕ прошёл" in lines
    seed_ran = res.get("seed") is not None                 # второй источник всё равно прогнан
    ok = res.get("ok") is False and form_failed and seed_ran
    return ok, f"form-падение поймано={form_failed} · seed всё равно прогнан={seed_ran} · ok-флаг={res.get('ok')}"


def a11_plan_first_invoked():
    """УТРО ПРЕЖДЕ РАБОТ: run() зовёт ПЛАНЁРКУ ПЕРВЫМ оператором тела — до СОВЕТА, СПОРОВ и run_day.
    Порядок шагов тела: планёрка < совет < споры < run_day < сухой ЦИКЛ-1 (пульс) < авто-сев."""
    _tmp_log()
    report.render_day = lambda d, **k: "x"
    order = []
    old_day, old_seed, old_plan, old_sovet, old_spory, old_pulse = \
        ap.day.run_day, ap._seed_tasks, ap._plannerka, ap._sovet, ap._spory, ap._cycle_pulse

    def cap_day(**kw):
        order.append("run_day")
        return _fake_day(**kw)

    def cap_seed(d):
        order.append("_seed_tasks")
        return {"ok": True, "lines": [], "form": 0, "seed": 0}

    def cap_plan():
        order.append("_plannerka")
        return {"ok": True, "date": "2026-09-04", "decisions": [], "lines": []}

    def cap_sovet():
        order.append("_sovet")
        return {"ok": True, "date": "2026-09-04", "gathered": False, "already": False,
                "dry": True, "file": None, "lines": []}

    def cap_spory():
        order.append("_spory")
        return {"ok": True, "date": "2026-09-04", "gathered": False, "already": False,
                "dry": True, "file": None, "lines": []}

    def cap_pulse(**kw):
        order.append("_cycle_pulse")
        return {"ok": True, "ran": [], "skipped": [], "closed": [], "lines": []}

    ap.day.run_day, ap._seed_tasks, ap._plannerka, ap._sovet, ap._spory, ap._cycle_pulse = \
        cap_day, cap_seed, cap_plan, cap_sovet, cap_spory, cap_pulse
    try:
        res = ap.run(head_source="none")
    finally:
        ap.day.run_day, ap._seed_tasks, ap._plannerka, ap._sovet, ap._spory, ap._cycle_pulse = \
            old_day, old_seed, old_plan, old_sovet, old_spory, old_pulse
    plan = res.get("plan")
    sovet = res.get("sovet")
    spory = res.get("spory")
    pulse = res.get("cycle_pulse")
    ok = bool(order) and order[0] == "_plannerka" and "_sovet" in order and "_spory" in order \
        and "run_day" in order and "_cycle_pulse" in order and "_seed_tasks" in order \
        and order.index("_plannerka") < order.index("_sovet") < order.index("_spory") < order.index("run_day") \
        and order.index("run_day") < order.index("_cycle_pulse") < order.index("_seed_tasks") \
        and isinstance(plan, dict) and plan.get("ok") is True \
        and isinstance(sovet, dict) and sovet.get("ok") is True \
        and isinstance(spory, dict) and spory.get("ok") is True \
        and isinstance(pulse, dict) and pulse.get("ok") is True
    return ok, (f"порядок={order} · в итоге plan={'есть' if isinstance(plan, dict) else 'нет'} "
                f"sovet={'есть' if isinstance(sovet, dict) else 'нет'} "
                f"spory={'есть' if isinstance(spory, dict) else 'нет'} "
                f"cycle_pulse={'есть' if isinstance(pulse, dict) else 'нет'}")


def a12_plan_local_store_only():
    """НАСТОЯЩАЯ ПЛАНЁРКА пишет ТОЛЬКО plans/ymarket_plan_<дата>.json в YM_PLAN_DIR; канон не тронут.

    Герметично: env перекрывает план-стор (YM_PLAN_DIR) и читаемые сторы (YM_TASKS_PATH/
    YM_DOSSIERS_PATH/YM_LIBRARY_PATH/YM_DAY_JOURNAL) → _plannerka реально отрабатывает в песочнице,
    канон SOCC байт-в-байт не тронут. Канон-путь снимаем ДО установки env.
    """
    os.environ.pop("YM_PLAN_DIR", None)
    import ymarket_plannerka_v1 as _PK                       # env чист → настоящий канон SOCC
    real_canon = _PK.plan_path()                             # plans/ymarket_plan_<сегодня>.json
    before = real_canon.read_bytes() if real_canon.exists() else None
    tmpdir = Path(tempfile.mkdtemp())
    os.environ["YM_PLAN_DIR"] = str(tmpdir)
    os.environ["ARBITER_AUTOPILOT_LOG"] = str(tmpdir / "ap.log")
    os.environ["YM_TASKS_PATH"] = str(tmpdir / "tasks.json")       # нет файла → пусто, не канон
    os.environ["YM_DOSSIERS_PATH"] = str(tmpdir / "dossiers.json") # нет файла → пусто, не канон
    os.environ["YM_LIBRARY_PATH"] = str(tmpdir / "library.json")   # нет файла → пусто, не канон
    os.environ["YM_DAY_JOURNAL"] = str(tmpdir / "day.jsonl")       # нет файла → пусто, не канон
    try:
        res = ap._plannerka()                               # НАСТОЯЩАЯ планёрка (build+render+save, 0₽)
        wrote = sorted(tmpdir.glob("ymarket_plan_*.json"))
    except Exception as e:
        res, wrote = None, []
        boom = e
    finally:
        os.environ.pop("YM_PLAN_DIR", None)
        os.environ.pop("ARBITER_AUTOPILOT_LOG", None)
        os.environ.pop("YM_TASKS_PATH", None)
        os.environ.pop("YM_DOSSIERS_PATH", None)
        os.environ.pop("YM_LIBRARY_PATH", None)
        os.environ.pop("YM_DAY_JOURNAL", None)
    after = real_canon.read_bytes() if real_canon.exists() else None
    if res is None:
        return False, f"настоящая планёрка упала: {type(boom).__name__}: {boom}"
    ok = (res or {}).get("ok") is True and wrote and before == after
    return ok, (f"ok={res.get('ok')} · план-файлов в tmp={len(wrote)} "
                f"({wrote[0].name if wrote else '—'}) · канон SOCC не тронут={before == after} · "
                f"решений={res.get('decisions')}")


def a13_plan_failsoft():
    """Планёрка fail-soft: падение движка (нет build_plan) тик НЕ роняет — ok=False, след в лог."""
    import types as _types
    tmpdir = Path(tempfile.mkdtemp())
    os.environ["ARBITER_AUTOPILOT_LOG"] = str(tmpdir / "ap.log")
    poisoned = _types.SimpleNamespace()                    # без build_plan → AttributeError
    mods = sys.modules
    prev = mods.get("ymarket_plannerka_v1")
    mods["ymarket_plannerka_v1"] = poisoned
    try:
        res = ap._plannerka()
    except Exception as e:
        res, boom = None, e
    finally:
        if prev is not None:
            sys.modules["ymarket_plannerka_v1"] = prev
        else:
            sys.modules.pop("ymarket_plannerka_v1", None)
        os.environ.pop("ARBITER_AUTOPILOT_LOG", None)
    if res is None:
        return False, f"планёрка упала вместе с движком: {type(boom).__name__}: {boom}"
    lines = " | ".join(res.get("lines") or [])
    lp = tmpdir / "ap.log"
    logged = lp.exists() and "ПЛАНЁРКА НЕ прошла" in lp.read_text(encoding="utf-8")
    ok = res.get("ok") is False and "build_plan" in lines and logged
    return ok, (f"ok-флаг={res.get('ok')} · причина названа={'build_plan' in lines} · "
                f"след в лог={logged}")


def a14_sovet_wired():
    """СОВЕТ (шаг 0.5) встроен в тик: run() зовёт _sovet после _plannerka, итог несёт сводку sovet."""
    _tmp_log()
    report.render_day = lambda d, **k: "x"
    (res, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
    called = cap.get("_sovet_calls", 0) >= 1
    plan_before = cap.get("_plan_calls", 0) >= 1
    summary = res.get("sovet")
    ok = called and plan_before and isinstance(summary, dict) and summary.get("ok") is True
    return ok, (f"run() позвал совет={called} (планёрка тоже позвана={plan_before}) · "
                f"в итоге sovet={'есть' if isinstance(summary, dict) else 'нет'}")


def a15_sovet_local_store_only():
    """НАСТОЯЩИЙ СОВЕТ пишет ТОЛЬКО sovet/ymarket_sovet_<дата>.json в YM_SOVET_DIR; канон не тронут.

    Герметично: env перекрывает протокол-стор (YM_SOVET_DIR) и читаемые сторы (YM_TASKS_PATH/
    YM_DOSSIERS_PATH/YM_LIBRARY_PATH/YM_DAY_JOURNAL/YM_PLAN_DIR) → _sovet реально отрабатывает в
    песочнице (соберётся — в песочнице живой леджер), канон SOCC байт-в-байт не тронут.
    Канон-путь снимаем ДО установки env.
    """
    os.environ.pop("YM_SOVET_DIR", None)
    import ymarket_sovet_v1 as _SV                       # env чист → настоящий канон SOCC
    canon_path = _SV.sovet_path()                         # sovet/ymarket_sovet_<сегодня>.json
    before = canon_path.read_bytes() if canon_path.exists() else None
    tmpdir = Path(tempfile.mkdtemp())
    # живой леджер в песочнице → совету есть что зеркалить (соберётся и запишет протокол в tmp)
    (tmpdir / "library.json").write_text(
        json.dumps({"goods": {"a": {"offer_id": "ARB-1", "store_slug": "atlas-express-film",
                                    "category_slug": "vozdushno-puzyrkovaya-plenka",
                                    "last_verified": {"verdict": "PASS",
                                                      "ts": "2026-09-04T06:00:00+00:00"}}}},
                   ensure_ascii=False), encoding="utf-8")
    os.environ["YM_SOVET_DIR"] = str(tmpdir)
    os.environ["YM_PLAN_DIR"] = str(tmpdir)
    os.environ["ARBITER_AUTOPILOT_LOG"] = str(tmpdir / "ap.log")
    os.environ["YM_TASKS_PATH"] = str(tmpdir / "tasks.json")        # нет файла → пусто, не канон
    os.environ["YM_DOSSIERS_PATH"] = str(tmpdir / "dossiers.json")  # нет файла → пусто, не канон
    os.environ["YM_LIBRARY_PATH"] = str(tmpdir / "library.json")
    os.environ["YM_DAY_JOURNAL"] = str(tmpdir / "day.jsonl")        # нет файла → пусто, не канон
    try:
        res = ap._sovet()                                 # НАСТОЯЩИЙ совет (read сторов + протокол, 0₽)
        wrote = sorted(tmpdir.glob("ymarket_sovet_*.json"))
    except Exception as e:
        res, wrote = None, []
        boom = e
    finally:
        for k in ("YM_SOVET_DIR", "YM_PLAN_DIR", "ARBITER_AUTOPILOT_LOG", "YM_TASKS_PATH",
                  "YM_DOSSIERS_PATH", "YM_LIBRARY_PATH", "YM_DAY_JOURNAL"):
            os.environ.pop(k, None)
    after = canon_path.read_bytes() if canon_path.exists() else None
    if res is None:
        return False, f"настоящий совет упал: {type(boom).__name__}: {boom}"
    wrote_in_tmp = wrote and str(wrote[0].resolve()).startswith(str(tmpdir.resolve()))
    ok = (res or {}).get("ok") is True and (res or {}).get("gathered") is True \
        and wrote and wrote_in_tmp and before == after
    return ok, (f"ok={res.get('ok')} собран={res.get('gathered')} · протоколов в tmp={len(wrote)} "
                f"({wrote[0].name if wrote else '—'}) · канон SOCC не тронут={before == after}")


def a16_spory_wired():
    """СПОРЫ (слой 2, шаг 0.5b) встроены в тик: run() зовёт _spory после _sovet, итог несёт сводку spory."""
    _tmp_log()
    report.render_day = lambda d, **k: "x"
    (res, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
    called = cap.get("_spory_calls", 0) >= 1
    sovet_before = cap.get("_sovet_calls", 0) >= 1
    summary = res.get("spory")
    ok = called and sovet_before and isinstance(summary, dict) and summary.get("ok") is True
    return ok, (f"run() позвал споры={called} (совет тоже позван раньше={sovet_before}) · "
                f"в итоге spory={'есть' if isinstance(summary, dict) else 'нет'}")


def a17_spory_local_store_only():
    """НАСТОЯЩИЕ СПОРЫ пишут ТОЛЬКО spory/ymarket_spory_<дата>.json в YM_SPORY_DIR; канон не тронут.

    Герметично: env перекрывает споры-стор (YM_SPORY_DIR) и читаемые сторы (YM_TASKS_PATH/
    YM_DOSSIERS_PATH/YM_LIBRARY_PATH/YM_DAY_JOURNAL/YM_PLAN_DIR) → _spory реально отрабатывает в
    песочнице (соберётся — 1 доказанно живой в леджере даёт позицию ЦИКЛ-1), канон SOCC байт-в-байт
    не тронут. Канон-путь снимаем ДО установки env.
    """
    os.environ.pop("YM_SPORY_DIR", None)
    import ymarket_sovet_spory_v1 as _SPS                    # env чист → настоящий канон SOCC
    canon_path = _SPS.spory_path()                            # spory/ymarket_spory_<сегодня>.json
    before = canon_path.read_bytes() if canon_path.exists() else None
    tmpdir = Path(tempfile.mkdtemp())
    # 1 доказанно живой в леджере песочницы → ЦИКЛ-1 скажет позицию (соберётся и запишет прение в tmp)
    (tmpdir / "library.json").write_text(
        json.dumps({"goods": {"a": {"offer_id": "ARB-1", "store_slug": "atlas-express-film",
                                    "category_slug": "vozdushno-puzyrkovaya-plenka",
                                    "last_verified": {"verdict": "PASS",
                                                      "ts": "2026-09-04T06:00:00+00:00"}}}},
                   ensure_ascii=False), encoding="utf-8")
    os.environ["YM_SPORY_DIR"] = str(tmpdir)
    os.environ["YM_PLAN_DIR"] = str(tmpdir)
    os.environ["ARBITER_AUTOPILOT_LOG"] = str(tmpdir / "ap.log")
    os.environ["YM_TASKS_PATH"] = str(tmpdir / "tasks.json")        # нет файла → пусто, не канон
    os.environ["YM_DOSSIERS_PATH"] = str(tmpdir / "dossiers.json")  # нет файла → пусто, не канон
    os.environ["YM_LIBRARY_PATH"] = str(tmpdir / "library.json")
    os.environ["YM_DAY_JOURNAL"] = str(tmpdir / "day.jsonl")        # нет файла → пусто, не канон
    try:
        res = ap._spory()                                 # НАСТОЯЩИЕ споры (read сторов + прение, 0₽)
        wrote = sorted(tmpdir.glob("ymarket_spory_*.json"))
    except Exception as e:
        res, wrote = None, []
        boom = e
    finally:
        for k in ("YM_SPORY_DIR", "YM_PLAN_DIR", "ARBITER_AUTOPILOT_LOG", "YM_TASKS_PATH",
                  "YM_DOSSIERS_PATH", "YM_LIBRARY_PATH", "YM_DAY_JOURNAL"):
            os.environ.pop(k, None)
    after = canon_path.read_bytes() if canon_path.exists() else None
    if res is None:
        return False, f"настоящие споры упали: {type(boom).__name__}: {boom}"
    wrote_in_tmp = wrote and str(wrote[0].resolve()).startswith(str(tmpdir.resolve()))
    ok = (res or {}).get("ok") is True and (res or {}).get("gathered") is True \
        and (res or {}).get("file") and wrote and wrote_in_tmp and before == after
    return ok, (f"ok={res.get('ok')} собраны={res.get('gathered')} · прений в tmp={len(wrote)} "
                f"({wrote[0].name if wrote else '—'}) · канон SOCC не тронут={before == after}")


def a18_cycle_pulse_wired():
    """24/7-сердцебиение встроено в тик: run() зовёт СУХОЙ ЦИКЛ-1 (_cycle_pulse), итог несёт cycle_pulse.
    Пульс идёт ДО авто-сева ЗАДАНИЙ — свежий пульс не даёт монитору сеять ложную «Пульс устарел» тиком же."""
    _tmp_log()
    report.render_day = lambda d, **k: "x"
    (res, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
    called = cap.get("_pulse_calls", 0) >= 1
    seed_after = cap.get("_seed_calls", 0) >= 1
    summary = res.get("cycle_pulse")
    ok = called and seed_after and isinstance(summary, dict) and summary.get("ok") is True \
        and summary.get("ran") == 0           # стаб: сухой прогон в тесте не гоняем, только факт вызова
    return ok, (f"run() позвал сухой ЦИКЛ-1={called} · авто-сев после={seed_after} · "
                f"в итоге cycle_pulse={'есть' if isinstance(summary, dict) else 'нет'} "
                f"ok={summary.get('ok') if isinstance(summary, dict) else '—'}")


def a19_cycle_pulse_dry_only():
    """СУХОЙ ЦИКЛ-1 по себе (герметично): пульс устарел → ОДИН сухой прогон; пульс свеж → пропуск;
    прогон упал → fail-soft ok=False (тик живёт). НИ ОДНОГО живого write-узла за heartbeat (0₽, RUBICON)."""
    # пульс УСТАРЕЛ → движок зовётся ОДИН раз (dry), сводка честная
    calls = []

    def fake_run(slug):
        calls.append(slug)
        return {"verdict": "DRY_OK", "hash": "abc123"}

    stale = ap._cycle_pulse(
        store="probe", now_date=lambda: "2026-09-07",
        pulse_read=lambda s: {"date": "2026-09-06"},          # вчера → прогнать
        cycle_run=fake_run, close_fn=lambda pulses: [],
    )
    ok_stale = stale.get("ok") is True and len(stale.get("ran")) == 1 \
        and stale["ran"][0]["verdict"] == "DRY_OK" and calls == ["probe"]
    # пульс СВЕЖ (сегодня) → движок НЕ зовётся (пропуск, раз в день)
    calls2 = []

    def fake_run2(slug):
        calls2.append(slug)
        return {"verdict": "DRY_OK", "hash": "x"}

    fresh = ap._cycle_pulse(
        store="probe", now_date=lambda: "2026-09-07",
        pulse_read=lambda s: {"date": "2026-09-07"},          # сегодня → пропуск
        cycle_run=fake_run2, close_fn=lambda pulses: [],
    )
    ok_fresh = fresh.get("ok") is True and len(fresh.get("skipped")) == 1 \
        and len(fresh.get("ran")) == 0 and calls2 == []
    # прогон УПАЛ → fail-soft: ok=False, строка в сводке, исключения НЕТ
    def fake_run3(slug):
        raise RuntimeError("донор не ответил")

    failed = ap._cycle_pulse(
        store="probe", now_date=lambda: "2026-09-07",
        pulse_read=lambda s: {"date": "2026-09-06"},
        cycle_run=fake_run3, close_fn=lambda pulses: [],
    )
    ok_fail = failed.get("ok") is False and len(failed.get("ran")) == 0 \
        and any("упал" in ln for ln in failed.get("lines") or [])
    ok = ok_stale and ok_fresh and ok_fail
    return ok, (f"устарел→прогнан 1 раз={ok_stale} · свеж→пропуск={ok_fresh} · "
                f"упал→fail-soft ok=False={ok_fail}")


def a20_pulse_task_close_honest():
    """Закрытие зависших «Пульс {store} устарел» ЧЕСТНО (TZ8): только когда текущий пульс СТРОГО свежее
    зафиксированной даты (дыра реально закрыта). Дата == пульсу (прогон НЕ продвинул пульс) → задача
    остаётся открытой — честный сигнал. Пишем ТОЛЬКО в стор YM_TASKS_PATH (песочница); канон не тронут.

    Сценарий 1 — пульс продвинут: heartbeat прогнал сухо (07.09) → ВСЕ зависшие «устарел» (03/06.09)
    закрываются evidence продвинутого пульса (T-cc9d92ff 03.09 закрыт прогоном 07.09 — наш живой случай).
    Сценарий 2 — пульс НЕ продвинут (всё ещё 06.09, сухой прогон сегодня не прошёл): задача «устарел
    (06.09)» (== пульсу) НЕ трогается — сигнал честен; только старья (03.09) закрыты.
    """
    os.environ.pop("YM_TASKS_PATH", None)
    import ymarket_tasks_v1 as _T                          # env чист → настоящий канон SOCC
    real_canon = _T.task_path()
    before = real_canon.read_bytes() if real_canon.exists() else None

    def _mk_task(datestr, body):
        return _T.new_task(
            what=f"Пульс atlas-express-film устарел ({datestr}) — прогнать сухо сегодня",
            owner="DISPATCHER", category="health", store="atlas-express-film",
            priority=40, body=body, source="cycle_day", urgency="normal")

    def _scenario(pulse_date):
        """Свежая песочница → закрыть с данным пульсом → (closed_ids, state_by_id)."""
        td = Path(tempfile.mkdtemp())
        ts = td / "tasks.json"
        os.environ["YM_TASKS_PATH"] = str(ts)
        t_old, e_old = _mk_task("2026-09-03", "Застарело давно.")
        t_live, e_live = _mk_task("2026-09-06", "Дыра ещё НЕ закрыта — сухой прогон не прошёл.")
        if e_old or e_live or not t_old or not t_live:
            raise RuntimeError(f"фикстура не собралась: {e_old or ''} {e_live or ''}")
        _T.save([t_old, t_live])
        closed = ap._close_stale_pulse_tasks({"atlas-express-film": pulse_date})
        reloaded, _err = _T.load()
        by_id = {t["id"]: t for t in reloaded}
        os.environ.pop("YM_TASKS_PATH", None)
        return closed, by_id, t_old["id"], t_live["id"]

    try:
        # Сценарий 1: пульс ПРОДВИНУТ до 07.09 → обе зависшие закрыты (03 и 06 < 07)
        closed1, by1, old1, live1 = _scenario("2026-09-07")
        s1_ok = sorted(closed1) == sorted([old1, live1]) \
            and by1[old1].get("state") == "done" and by1[live1].get("state") == "done"
        # Сценарий 2: пульс НЕ продвинут (06.09 == дата живой задачи) → НЕ закрыта; старья 03 закрыто
        closed2, by2, old2, live2 = _scenario("2026-09-06")
        step2 = (by2[old2].get("steps") or [{}])[0]
        s2_ok = closed2 == [old2] \
            and by2[old2].get("state") == "done" and step2.get("state") == "done" \
            and step2.get("done_by") and "2026-09-06" in (step2.get("evidence") or "") \
            and by2[live2].get("state") in ("open", "in_progress")
    except Exception as e:
        return False, f"исключение: {type(e).__name__}: {e}"
    finally:
        os.environ.pop("YM_TASKS_PATH", None)
    after = real_canon.read_bytes() if real_canon.exists() else None
    ok = s1_ok and s2_ok and before == after
    return ok, (f"пульс продвинут→закрыты {closed1} (state done) · "
                f"пульс НЕ продвинут→закрыто только {closed2}, дыра 06.09 осталась "
                f"{by2[live2].get('state')} · канон SOCC не тронут={before == after}")


TESTS = [
    ("A1  hard_dry_invariant", a1_hard_dry_invariant),
    ("A2  no_commit_path", a2_no_commit_path),
    ("A3  log_written", a3_log_written),
    ("A4  log_failsoft", a4_log_failsoft),
    ("A5  head_source_wired", a5_head_source_wired),
    ("A6  result_shape_honest", a6_result_shape_honest),
    ("A7  zaliv_wired_by_default", a7_zaliv_wired_by_default),
    ("A8  auto_seed_wired", a8_auto_seed_wired),
    ("A9  seed_local_store_only", a9_seed_local_store_only),
    ("A10 seed_failsoft", a10_seed_failsoft),
    ("A11 plan_first_invoked", a11_plan_first_invoked),
    ("A12 plan_local_store_only", a12_plan_local_store_only),
    ("A13 plan_failsoft", a13_plan_failsoft),
    ("A14 sovet_wired", a14_sovet_wired),
    ("A15 sovet_local_store_only", a15_sovet_local_store_only),
    ("A16 spory_wired", a16_spory_wired),
    ("A17 spory_local_store_only", a17_spory_local_store_only),
    ("A18 cycle_pulse_wired", a18_cycle_pulse_wired),
    ("A19 cycle_pulse_dry_only", a19_cycle_pulse_dry_only),
    ("A20 pulse_task_close_honest", a20_pulse_task_close_honest),
]


def main():
    print(f"🎯 ARBITER АВТОПИЛОТ (СУХОЙ) · ПРИЁМКА — автопилот не умеет в боевой режим; ЗАДАНИЯ сеет сам (0₽)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<24} {detail}")
        passed += 1 if ok else 0
    # прибрать за собой env, чтобы не течь в соседние прогоны
    os.environ.pop("ARBITER_AUTOPILOT_LOG", None)
    os.environ.pop("YM_TASKS_PATH", None)
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Автопилот честен: RUBICON зашит физически (только dry), след пишется, "
              "нос спроса ленив, режим не врётся, ЗАДАНИЯ сеются каждый тик в локальный реестр")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

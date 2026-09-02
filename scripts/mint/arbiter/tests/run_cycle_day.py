#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — ЦИКЛ-ДНЯ, диспетчер заданий (ymarket_cycle_day_v1). Сухо, 0₽, без сети.

Проверяем ЗАКОНЫ диспетчера, а не «запустилось»:
  CD1  read-терминал честный — планёрка различает «реестра ещё нет» / «реестр пуст» / «открыто N»;
  CD2  form без --commit НИЧЕГО не пишет (артефакты только читаются);
  CD3  form --commit идемпотентен — то же намерение → тот же T- id (TZ1), повторный прогон 0 новых;
       запись рождается из ЖИВЫХ наблюдений с evidence (артефакт), владелец = орган (удавка);
  CD4  планёрка — ОДИН глобальный блок заданий (пульсы магазинов + блок один раз);
  CD5  диспетчер без фейк-пасс — сухой подхват ТОЛЬКО с явным --cycle-dry; без него ничего не гоняет,
       не mark_step; «исполнителя нет» у органа без исполнителя здесь — честно;
  CD6  единственный write — локальный реестр под form --commit (файл появляется только там).

Изоляция сканеров: CD._RUNTIME/CD.COSTS_PATH переводятся на tmp + CD.cycle1 = None (магазины/леджеры
не читаются) → form детерминированно даёт ровно ценовые наблюдения из ФЕЙК-артефакта. Канон НЕ трогаем.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_cycle_day_v1 as CD   # noqa: E402
import ymarket_tasks_v1 as T        # noqa: E402

_ORIG = {"RUNTIME": CD._RUNTIME, "COSTS": CD.COSTS_PATH, "cycle1": CD.cycle1}


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _fake_artifacts(d: Path):
    """Фейковый артефакт закупки + леджер с ЗАЛИВом (2 карточки: одна ниже пола КПИ, одна ниже зоны)."""
    costs = d / "_card_costs.json"
    costs.write_text(json.dumps({"cards": {
        "ARB-87931769": {"cost": 65.0}, "ARB-53416854": {"cost": 170.0}}}))
    ledger_d = d / "atlas-express-film"
    ledger_d.mkdir(parents=True, exist_ok=True)
    note = ("ARB-87931769 vБез бренда desc=1 сп=1 фото=1 520₽; "
            "ARB-53416854 vБез бренда desc=1 сп=1 фото=1 1360₽")
    (ledger_d / "2026-09-02.jsonl").write_text(
        json.dumps({"verdict": "DRY", "node": "ЗАЛИВ", "note": note, "ts": "10:00:00"}) + "\n" +
        json.dumps({"verdict": "PASS", "node": "СВЕРКА", "note": "ок", "ts": "10:00:01"}) + "\n")


def _ctx_form(tmp: Path):
    """Контекст детерминированной формы: сканеры магазинов/леджеров выключены, артефакты — tmp."""
    CD._RUNTIME = tmp
    CD.COSTS_PATH = tmp / "_card_costs.json"
    CD.cycle1 = None
    _fake_artifacts(tmp)


def _ctx_restore():
    CD._RUNTIME = _ORIG["RUNTIME"]
    CD.COSTS_PATH = _ORIG["COSTS"]
    CD.cycle1 = _ORIG["cycle1"]


def cd1_plannerka_honest_read():
    """CD1: планёрка различает «реестра нет» / «реестр есть, но пуст» / «открыто N»."""
    with tempfile.TemporaryDirectory() as d:
        reg = Path(d) / "reg.json"
        os.environ["YM_TASKS_PATH"] = str(reg)
        try:
            txt_absent = "\n".join(CD.plannerka_text())
            # пустой реестр (записан save([]))
            T.save([], path=reg)
            txt_empty = "\n".join(CD.plannerka_text())
            # один открытый плюс один закрытый
            a, _ = T.new_task(what="Переценка плёнки (тест)", owner="PRICER",
                              category="pricing", store="atlas-express-film")
            b, _ = T.new_task(what="Сделано вчера", owner="CONTROLLER", category="health",
                              store="atlas-express-film")
            b, _ = T.mark_step(b, "s1", done_by="controller-v1", evidence="прочитано СВЕРКОЙ")
            T.save([a, b], path=reg)
            txt_open = "\n".join(CD.plannerka_text())
        finally:
            os.environ.pop("YM_TASKS_PATH", None)
    ok = ("реестра ещё нет" in txt_absent
          and "пуст — заданий нет" in txt_empty
          and "открыто 1" in txt_open and "PRICER" in txt_open)
    return ok, (f"отсутствие/пусто/открыто различимы: "
                f"{'да' if ok else 'НЕТ'} (CD1)")


def cd4_one_global_block():
    """CD4: ОДИН блок ЗАДАНИЙ в планёрке (нет блоков на каждый магазин)."""
    with tempfile.TemporaryDirectory() as d:
        reg = Path(d) / "reg.json"
        os.environ["YM_TASKS_PATH"] = str(reg)
        try:
            a, _ = T.new_task(what="Переценка ARB-87931769 (тест)", owner="PRICER",
                              category="pricing", store="atlas-express-film")
            T.save([a], path=reg)
            lines = CD.plannerka_text()
        finally:
            os.environ.pop("YM_TASKS_PATH", None)
    headers = [l for l in lines if l.startswith("ЗАДАНИЯ")]
    ok = len(headers) == 1 and any("открыто 1" in l for l in headers)
    return ok, f"заголовков ЗАДАНИЯ ровно {len(headers)} (должен быть 1) · открыто видно (CD4)"


def cd2_form_dry_writes_nothing():
    """CD2: form без commit ничего не пишет (ни реестра, ни артефактов)."""
    with tempfile.TemporaryDirectory() as d:
        reg = Path(d) / "reg.json"
        _ctx_form(Path(d))
        summary, lines = CD.form(commit=False, store="atlas-express-film", date_str="2026-09-02")
        reg_absent = not reg.exists()
        _ctx_restore()
    cand_new = summary.get("new")
    ok = (reg_absent and cand_new == 2 and any("RAISE" in l for l in lines)
          and any("SWEET" in l for l in lines))
    return ok, (f"кандидатов {cand_new} (RAISE+SWEET из фейк-артефакта) · файла нет: "
                f"{'да' if reg_absent else 'НЕТ'} (CD2)")


def cd3_form_commit_idempotent():
    """CD3: --commit пишет реестр (локально, CD6); повторный прогон — 0 новых, те же T- id."""
    with tempfile.TemporaryDirectory() as d:
        reg = Path(d) / "reg.json"
        os.environ["YM_TASKS_PATH"] = str(reg)
        try:
            _ctx_form(Path(d))
            s1, lines1 = CD.form(commit=True, store="atlas-express-film", date_str="2026-09-02")
            ids1 = sorted(t.get("id") for t in T.load(reg)[0])
            s2, lines2 = CD.form(commit=True, store="atlas-express-film", date_str="2026-09-02")
            tasks2 = T.load(reg)[0]
            ids2 = sorted(t.get("id") for t in tasks2)
            pricers = [t for t in tasks2 if t.get("owner") == "PRICER"]
            reg_existed = reg.exists()
        finally:
            _ctx_restore()
            os.environ.pop("YM_TASKS_PATH", None)
    ok = (reg_existed and s1.get("new") == 2 and s2.get("new") == 0 and s2.get("dup") == 2
          and ids1 == ids2 and len(pricers) == 2
          and all(t.get("refs", {}).get("evidence") for t in pricers))
    return ok, (f"1-й прогон +2 · 2-й +0(=2 дубля) · id стабильны {ids1} · PRICER×2 с evidence (CD3/6)")


def cd5_dispatch_no_fake_pass():
    """CD5: диспетчер (read) ничего не гоняет без --cycle-dry, не mark_step, честно называет
    исполнителя; органа без исполнителя здесь — «исполнителя нет»."""
    with tempfile.TemporaryDirectory() as d:
        reg = Path(d) / "reg.json"
        os.environ["YM_TASKS_PATH"] = str(reg)
        try:
            p, _ = T.new_task(what="Переценка ARB-87931769 (тест)", owner="PRICER",
                              category="pricing", store="atlas-express-film")
            c, _ = T.new_task(what="Добавить категории донора (тест)", owner="CATEGORIST",
                              category="categories", store="atlas-express-film")
            T.save([p, c], path=reg)
            summary, lines = CD.dispatch(cycle_dry=False)
            steps_open = all(s.get("state") == "open"
                             for t in T.load(reg)[0] for s in (t.get("steps") or []))
        finally:
            os.environ.pop("YM_TASKS_PATH", None)
    txt = "\n".join(lines)
    ok = (summary.get("ran") == [] and "готовит план" in txt and "исполнителя в ЦИКЛ-ДНЯ нет" in txt
          and steps_open)
    return ok, (f"ran={summary.get('ran')} (пусто — без флага ничего не гоняем) · PRICER → план · "
                f"CATEGORIST → честно нет исполнителя · пункты остались open (CD5)")


def cd5b_mark_step_gate_honesty():
    """CD5 (гейт): пункт не закрыть пустым evidence — диспетчеру и органу (TZ8 жива из реестра)."""
    t, _ = T.new_task(what="Любое задание (гейт)", owner="PRICER", category="pricing")
    _, err = T.mark_step(t, "s1", done_by="pricer-v1", evidence="")
    ok = err and "evidence" in err
    return ok, f"закрытие без факта → отказ «{err}» (CD5/TZ8)"


TESTS = [
    ("CD1  read-планёрка честная", cd1_plannerka_honest_read),
    ("CD4  один глобальный блок", cd4_one_global_block),
    ("CD2  form dry не пишет", cd2_form_dry_writes_nothing),
    ("CD3  form commit идемпотентен", cd3_form_commit_idempotent),
    ("CD5  диспетчер без фейк-пасс", cd5_dispatch_no_fake_pass),
    ("CD5  гейт закрытия жив", cd5b_mark_step_gate_honesty),
]


def main():
    print("🎯 ПРИЁМКА · ЦИКЛ-ДНЯ (диспетчер заданий, 0₽, без сети, tmp-стор)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<30} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ ЦИКЛ-ДНЯ честен: read-планёрка различает «нет реестра/пусто/открыто», форма из "
              "живых наблюдений пишет только с --commit (идемпотентно), диспетчер без флага ничего "
              "не гоняет и никогда не закрывает пункт без факта.")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

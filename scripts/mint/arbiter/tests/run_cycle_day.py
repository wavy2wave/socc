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
  CD6  единственный write — локальный реестр под form --commit (файл появляется только там);
  CD8  контроль ценника (директива 08.09): зелёный ценник (discountBase) и цена ниже эталона
       из КОНТРОЛЬ-узла леджера → PRICER-задания; чистое evidence → 0 (артефакт, 0₽, без сети).

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
    """Фейковый артефакт закупки + леджер с ЖИВЫМ ЗАЛИВом (dry=False — реальная публикация).
    2 карточки: одна ниже пола КПИ (RAISE), одна ниже зоны (SWEET). FIX-F: сухая репетиция
    (dry=True) никогда не пишет на ЯМ — витринную цену несёт только живой ЗАЛИВ."""
    costs = d / "_card_costs.json"
    costs.write_text(json.dumps({"cards": {
        "ARB-87931769": {"cost": 65.0}, "ARB-53416854": {"cost": 170.0}}}))
    ledger_d = d / "atlas-express-film"
    ledger_d.mkdir(parents=True, exist_ok=True)
    note = ("ARB-87931769 vБез бренда desc=1 сп=1 фото=1 520₽; "
            "ARB-53416854 vБез бренда desc=1 сп=1 фото=1 1360₽")
    (ledger_d / "2026-09-02.jsonl").write_text(
        json.dumps({"verdict": "PASS", "node": "ЗАЛИВ", "note": note, "ts": "10:00:00",
                    "dry": False}) + "\n" +
        json.dumps({"verdict": "PASS", "node": "СВЕРКА", "note": "ок", "ts": "10:00:01",
                    "dry": False}) + "\n")


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
    """CD2: form без commit ничего не пишет (ни реестра, ни артефактов).

    YM_TASKS_PATH перекрываем на tmp ОБЯЗАТЕЛЬНО (как cd1/cd3): канон-реестр материализован и
    несёт ТЕ ЖЕ реальные T-84d7aa1a/T-9fca5843 — без песочницы fresh стал бы 0 и закон врал бы
    про «файла нет». Герметичность: тест не зависит от состояния канона SOCC.
    """
    with tempfile.TemporaryDirectory() as d:
        reg = Path(d) / "reg.json"
        os.environ["YM_TASKS_PATH"] = str(reg)
        try:
            _ctx_form(Path(d))
            summary, lines = CD.form(commit=False, store="atlas-express-film", date_str="2026-09-02")
            reg_absent = not reg.exists()
        finally:
            _ctx_restore()
            os.environ.pop("YM_TASKS_PATH", None)
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


def cd6_dry_fill_not_vitrine():
    """FIX-F: ТОЛЬКО сухие ЗАЛИВы (автопилот 3×/день) НЕ сеют reprice-заданий.

    Сухая репетиция никогда не пишет на ЯМ — её note это ПЛАН, не факт витрины. Раньше
    vitrina_from_ledger читала последний ЗАЛИВ без проверки dry и scan_pricing ковал
    «витрина 1360₽ → SWEET» из фантома → ложные PRICER-задания при 0 реальных ₽."""
    with tempfile.TemporaryDirectory() as d:
        COSTS = Path(d) / "_card_costs.json"
        COSTS.write_text(json.dumps({"cards": {
            "ARB-87931769": {"cost": 65.0}, "ARB-53416854": {"cost": 170.0}}}))
        ld = Path(d) / "atlas-express-film"
        ld.mkdir(parents=True, exist_ok=True)
        note = ("ARB-87931769 vБез бренда desc=1 сп=1 фото=1 520₽; "
                "ARB-53416854 vБез бренда desc=1 сп=1 фото=1 1360₽")
        (ld / "2026-09-02.jsonl").write_text(
            json.dumps({"verdict": "DRY", "node": "ЗАЛИВ", "note": note, "ts": "10:00:00",
                        "dry": True}) + "\n")
        CD._RUNTIME = Path(d)
        CD.COSTS_PATH = COSTS
        CD.cycle1 = None
        try:
            cands = CD.scan_pricing("atlas-express-film", date_str="2026-09-02")
        finally:
            _ctx_restore()
    ok = cands == []
    return ok, f"кандидатов {len(cands)} (сухой ЗАЛИВ = план, живой витрины нет → 0)"


def cd7_scan_ledgers_live_only():
    """FIX-F: health-задание сеет только ЖИВОЙ ход FAIL; сухая FAIL-репетиция — НЕТ."""
    class FakeC1:
        def __init__(self, stores):
            self.stores = stores
        def list_cycles(self):
            return {s: {"builder": "film"} for s in self.stores}
        def plannerka_read(self, slug):
            return {"date": "2026-09-02", "store": slug}
    rows = [
        # сухая репетиция автопилота, вставшая на СБОРКЕ (план ниже пола) — НЕ поломка магазина.
        # Всталая цепь не пишет хвост: последняя строка сухого прогона = его FAIL-узел.
        {"verdict": "PASS", "node": "ДОНОР", "dry": True, "ts": "08:00:00"},
        {"verdict": "FAIL", "node": "СБОРКА", "note": "below_floor", "dry": True,
         "ts": "08:00:01"},
    ]
    live_fail = [
        # ЖИВОЙ ход оператора упал на ЗАЛИВЕ → магазин в недоверенном состоянии → чинить
        {"verdict": "FAIL", "node": "ЗАЛИВ", "note": "TypeError", "dry": False,
         "ts": "09:00:00"},
    ]
    def run_case(stores, extra):
        with tempfile.TemporaryDirectory() as d:
            led = Path(d) / "atlas-express-film"
            led.mkdir(parents=True, exist_ok=True)
            (led / "2026-09-02.jsonl").write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in (rows + extra)))
            CD._RUNTIME = Path(d)
            CD.cycle1 = FakeC1(stores)
            try:
                return CD.scan_ledgers()
            finally:
                CD.cycle1 = _ORIG["cycle1"]
                CD._RUNTIME = _ORIG["RUNTIME"]
    dry_only = run_case(["atlas-express-film"], [])
    with_live = run_case(["atlas-express-film"], live_fail)
    ok = (dry_only == [] and len(with_live) == 1
          and with_live[0].get("owner") == "CONTROLLER" and "ЗАЛИВ" in with_live[0]["what"])
    return ok, (f"сухая FAIL-репетиция → {len(dry_only)} заданий · живой FAIL → "
                f"{len(with_live)} (owner={with_live[0].get('owner') if with_live else '—'})")


def cd8_price_control_green_tag_task():
    """CD8: КОНТРОЛЬ-узел из леджера (CD2): зелёный ценник (discountBase) → PRICER-задание
    «снять», чистое evidence → 0 заданий. Читаем АРТЕФАКТ леджера — 0₽, без сети, детерминировано."""
    def run(evidence):
        with tempfile.TemporaryDirectory() as d:
            led = Path(d) / "atlas-express-film"
            led.mkdir(parents=True, exist_ok=True)
            (led / "2026-09-02.jsonl").write_text(json.dumps(
                {"verdict": "PASS", "node": "КОНТРОЛЬ", "note": "зелёных ценников 1",
                 "evidence": evidence, "ts": "08:00:00", "dry": True}) + "\n")
            CD._RUNTIME = Path(d)
            CD.cycle1 = None
            try:
                return CD.scan_price_control("atlas-express-film", "2026-09-02")
            finally:
                CD._RUNTIME = _ORIG["RUNTIME"]
                CD.cycle1 = _ORIG["cycle1"]
    green = {"9601515-1": {"value": 3390.0, "base": 4900.0}}
    with_green = run({"green": green, "below_plan": {},
                      "promos": {"total": 2, "participating": 0}})
    below = run({"green": {}, "below_plan": {"ARB-87931769": {"live": 500.0, "plan": 520.0}},
                 "promos": {"total": 2, "participating": 0}})
    clean = run({"green": {}, "below_plan": {},
                 "promos": {"total": 2, "participating": 0}})
    ok = (len(with_green) == 1 and with_green[0].get("owner") == "PRICER"
          and "9601515-1" in with_green[0]["what"]
          and len(below) == 1 and "Поднять цену" in below[0]["what"] and clean == [])
    return ok, (f"зелёный ценник → {len(with_green)} задание ({with_green[0].get('owner') if with_green else '—'}) · "
                f"ниже эталона → {len(below)} · чисто → {len(clean)} (CD8)")


def cd9_control_promo_auto_guard():
    """CD9 (директива 08.09 вечер «товары не должны уходить в акции сами»): КОНТРОЛЬ-узел из
    леджера → CONTROLLER-задания на РИСК автопереноса (renewal_on, участия ещё нет) и на ФАКТ
    автодобавления (auto_added). Читаем артефакт леджера — 0₽, без сети, детерминировано."""
    def run(evidence):
        with tempfile.TemporaryDirectory() as d:
            led = Path(d) / "atlas-express-film"
            led.mkdir(parents=True, exist_ok=True)
            (led / "2026-09-02.jsonl").write_text(json.dumps(
                {"verdict": "PASS", "node": "КОНТРОЛЬ", "note": "акции не участвует",
                 "evidence": evidence, "ts": "08:00:00", "dry": True}) + "\n")
            CD._RUNTIME = Path(d)
            CD.cycle1 = None
            try:
                return CD.scan_price_control("atlas-express-film", "2026-09-02")
            finally:
                CD._RUNTIME = _ORIG["RUNTIME"]
                CD.cycle1 = _ORIG["cycle1"]
    renewal_risk = run({"green": {}, "below_plan": {}, "promos": {
        "total": 2, "participating": 0, "active": 0, "potential": 3, "auto_added": [],
        "renewal_on": ["Бестселлеры: Начало сезона", "Супербестселлеры: Начало сезона"]}})
    auto_fact = run({"green": {}, "below_plan": {}, "promos": {
        "total": 2, "participating": 1, "active": 1, "potential": 3,
        "auto_added": ["ARB-77700001"],
        "renewal_on": ["Бестселлеры: Начало сезона"]}})
    clean = run({"green": {}, "below_plan": {}, "promos": {
        "total": 2, "participating": 0, "active": 0, "potential": 0,
        "auto_added": [], "renewal_on": []}})
    ok = (len(renewal_risk) == 1 and renewal_risk[0].get("owner") == "CONTROLLER"
          and "автоперенос" in renewal_risk[0]["what"]
          and len(auto_fact) == 1 and auto_fact[0].get("owner") == "CONTROLLER"
          and "ARB-77700001" in auto_fact[0]["what"] and "автодобавлен" in auto_fact[0]["what"]
          and clean == [])
    return ok, (f"риск переноса → {len(renewal_risk)} · факт автодобавления → {len(auto_fact)} "
                f"({auto_fact[0]['what'][:50] if auto_fact else '—'}) · чисто → {len(clean)} (CD9)")


TESTS = [
    ("CD1  read-планёрка честная", cd1_plannerka_honest_read),
    ("CD4  один глобальный блок", cd4_one_global_block),
    ("CD2  form dry не пишет", cd2_form_dry_writes_nothing),
    ("CD3  form commit идемпотентен", cd3_form_commit_idempotent),
    ("CD5  диспетчер без фейк-пасс", cd5_dispatch_no_fake_pass),
    ("CD5  гейт закрытия жив", cd5b_mark_step_gate_honesty),
    ("CD6  сухой ЗАЛИВ ≠ витрина", cd6_dry_fill_not_vitrine),
    ("CD7  health только живой ход", cd7_scan_ledgers_live_only),
    ("CD8  контроль ценника из леджера", cd8_price_control_green_tag_task),
    ("CD9  контроль автодобавления в акции", cd9_control_promo_auto_guard),
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

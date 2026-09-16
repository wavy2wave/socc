#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — ПЛАНЁРКА (УТРО) (ymarket_plannerka_v1): первый слой ПЛАНЁРКА→ЗАДАНИЯ→ИСПОЛНЕНИЕ.

Герметично, 0₽: ВСЕ входы (реестр/досье/леджер/журнал) инъецируются документами; запись только в
tempfile-песочницу (env YM_PLAN_DIR / save_path). Реальный диск/сеть/Маркет не трогаем.

ЗАКОНЫ приёмки (анти-вралье + герметика, см. шапку модуля):
  PL1 контекст без выдумки  — каждая строка контекста несёт метку-источник; внешние контексты
        (погода/новости/тренды) честно «НЕ подключены», а не сочинены; «горящих 0» = из инъекции,
        не из воздуха.
  PL2 «живо»=только СВЕРКА  — витрина считает только last_verified PASS (proof_cross), FAIL/без-
        записи не идут.
  PL3 escalation≠задание    — маппинг-категория без id → решение «нужно слово оператора», owner
        OPERATOR, интэйк её НЕ превращает в задание органа (0 создано).
  PL4 интэйк TZ1           — kind=new с органом → запись через new_task (валидный id) один раз;
        повторная попытка того же намерения дедуп-пропускается; вне-CATEGORIES → пропуск с причиной.
  PL5 dry ничего не пишет   — save_plan(commit=False) и seed(commit=False) файл не создают.
  PL6 render не врёт молчанием — пустые входы → честный «ПЛАН ДНЯ» с явными 0 и «не выдумываем»,
        render() всегда строка; load_plan нет-файла → (None, None), не паника.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
for p in (str(ARB),):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_plannerka_v1 as P     # noqa: E402
import ymarket_tasks_v1 as T         # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _task(what, owner, category, *, cycle="cycle_day", store="atlas-express-film",
          urgency="normal", priority=50, body="", source="plannerka"):
    """Фикстура-задание через канонический new_task (валидная запись, а не ручная лепка)."""
    t, err = T.new_task(what=what, owner=owner, category=category, cycle=cycle,
                        store=store, urgency=urgency, priority=priority,
                        body=body, source=source)
    assert err is None, f"new_task вернул ошибку: {err}"
    return t


def _goods(oid, slug, cat, verdict="PASS"):
    return {"offer_id": oid, "article": oid, "store_slug": slug, "category_slug": cat,
            "last_verified": {"verdict": verdict, "ts": "2026-09-04T06:00:00+00:00"}}

_GOOD = _goods  # alias


def _dossier(slug, *, title=None, state="open", prio=50, need_mapping=False,
             market_category_id=None, scan=None, ood=""):
    e = {"title_ru": title or slug, "state": state, "priority": prio,
         "mapping": {"need_mapping": need_mapping,
                     "market_category_id": market_category_id},
         "open_operator_decision": ood, "task_id": f"T-{slug[:6]}"}
    if scan is not None:
        e["scan"] = scan
    return e


def _ready_scan(ready=4):
    return {"when": "2026-09-03T13:00:00+00:00", "dry": True, "rubicon": "ok",
            "verdict": "ready_shortlist", "verdict_text": "шорт-лист собран",
            "readiness": {"ready": ready, "scanned": ready, "island": False},
            "shortlist": [{"sku": f"SKU-{i}", "title": "x", "sell_rub": 900} for i in range(ready)]}


def pl1_context_no_fabrication():
    reg = [_task("Поднять цену ARB-87931769 до пола КПИ", "PRICER", "pricing",
                 urgency="high", priority=20),
           _task("Спарсить категорию стрейч-плёнка на доноре", "CATEGORIST", "categories",
                 priority=40)]
    lib = {"goods": {"a": _GOOD("ARB-1", "atlas-express-film", "vozdushno-puzyrkovaya-plenka"),
                     "b": _GOOD("ARB-2", "atlas-express-film", "vozdushno-puzyrkovaya-plenka", "FAIL"),
                     "c": _GOOD("ARB-3", "atlas-express-film", "drugaya", "PASS")}}
    doss = {"categories": {
        "vozdushno-puzyrkovaya-plenka": _dossier(
            "vozdushno-puzyrkovaya-plenka", state="done", need_mapping=False,
            market_category_id="76346336", scan=_ready_scan(2))}}
    jrn = [{"ts": "2026-09-04T06:00:00+00:00", "date": "2026-09-04",
            "kpis": {"urgent_orders": 0}, "burning": 2, "top_move": "ASSORTMENT_WIDEN"}]
    plan = P.build_plan(date_str="2026-09-04", store="atlas-express-film",
                        registry=reg, dossiers=doss, vitrine=lib, journal=jrn)
    ctx = {c["tag"]: c["text"] for c in plan["context"]}
    ok_a = ctx.get("ВИТРИНА") and "доказанно живых 2" in ctx["ВИТРИНА"] and "СВЕРКА PASS" in ctx["ВИТРИНА"]
    ok_b = ctx.get("ЗАДАНИЯ") and "открыто заданий 2" in ctx["ЗАДАНИЯ"] and "PRICER=1" in ctx["ЗАДАНИЯ"]
    ok_c = ctx.get("ОЧЕРЕДЬ") and "ГОТОВО: vozdushno-puzyrkovaya-plenka" in ctx["ОЧЕРЕДЬ"]
    ok_d = ctx.get("КОНТЕКСТ") and "НЕ подключены" in ctx["КОНТЕКСТ"]
    # никакая строка контекста не сочиняет «3 новых заказа с ночи» — заказы берём только из журнала
    joined = " ".join(ctx.values()).lower()
    ok_e = ("3 новых заказа" not in joined and "с ночи" not in joined)
    return (ok_a and ok_b and ok_c and ok_d and ok_e), (
        f"витрина={ok_a} задания={ok_b} очередь={ok_c} внешние-честно={ok_d} не-выдумано={ok_e} · "
        f"ВИТРИНА={ctx.get('ВИТРИНА')!r} ЗАДАНИЯ={ctx.get('ЗАДАНИЯ')!r}")


def pl2_live_only_svverka():
    lib = {"goods": {"a": _GOOD("ARB-1", "atlas-express-film", "cat-x", "PASS"),
                     "b": _GOOD("ARB-2", "atlas-express-film", "cat-x", "FAIL"),
                     "c": _GOOD("ARB-3", "boevoj", "cat-y", "PASS"),
                     "d": {"offer_id": "ARB-4", "store_slug": "atlas-express-film"}}}
    # FAIL (b) и запись без last_verified (d) НЕ считаются → по категории: cat-x×1, cat-y×1
    v = P.read_vitrine(lib)
    plan = P.build_plan(date_str="2026-09-04", registry=[], dossiers={}, vitrine=lib,
                        journal=[])
    ctx = {c["tag"]: c["text"] for c in plan["context"]}
    ok = (v["by_category"].get("cat-x") == 1 and v["by_category"].get("cat-y") == 1
          and v["total"] == 2 and "доказанно живых 2" in ctx.get("ВИТРИНА", ""))
    return ok, f"cat-x={v['by_category'].get('cat-x')} cat-y={v['by_category'].get('cat-y')} total={v['total']}"


def pl3_escalation_is_not_task():
    doss = {"categories": {"rukzaki-shkolnye": _dossier(
        "rukzaki-shkolnye", need_mapping=True, market_category_id=None, ood="профиль категории решает оператор")}}
    reg = []
    plan = P.build_plan(date_str="2026-09-04", registry=reg, dossiers=doss,
                        vitrine={"goods": {}}, journal=[{"date": "2026-09-04",
                                                          "kpis": {"urgent_orders": 0}}])
    esc = [x for x in plan["decisions"] if x["kind"] == "escalation"]
    new = [x for x in plan["decisions"] if x["kind"] == "new"]
    ok_a = len(esc) == 1 and esc[0]["owner"] == "OPERATOR" and "маппинг" in esc[0]["what"]
    ok_b = len(new) == 0                       # маппинг — не авто-задание органа (PL3)
    summary, _lines = P.seed_from_plan(plan, commit=False, existing=[])
    ok_c = summary["made"] == 0                # интэйк ничего не создал из escalation
    return (ok_a and ok_b and ok_c), (f"esc={len(esc)} new={len(new)} made={summary['made']} "
                                      f"esc_who={esc[0]['owner'] if esc else '—'}")


def pl4_intake_dedup_and_write():
    plan = {"date": "2026-09-04", "store": "atlas-express-film",
            "decisions": [
                {"id": "new-x", "kind": "new",
                 "what": "Отсканировать категорию стрейч-плёнка на доноре", "owner": "CATEGORIST",
                 "category": "categories", "urgency": "normal", "priority": 40,
                 "why": "в очереди, скана не было", "evidence": "досье", "mode": "dry",
                 "refs": {"dossier_slug": "streich-plenka"}},
                {"id": "new-bad", "kind": "new", "what": "Что-то вне формата",
                 "owner": "CATEGORIST", "category": "nonsense", "urgency": "normal",
                 "priority": 40, "why": "", "evidence": "досье", "mode": "dry"},
            ]}
    with tempfile.TemporaryDirectory() as td:
        save_path = Path(td) / "tasks.json"
        # первый seed: пишем 1 валидное (CATEGORIST/категории), второе пропущено (вне словаря)
        s1, _l1 = P.seed_from_plan(plan, commit=True, save_path=save_path, existing=[])
        created = json.loads(save_path.read_text(encoding="utf-8")).get("tasks", {})
        ok_a = s1["made"] == 1 and s1["skipped"] == 1 and len(created) == 1
        first_id = next(iter(created))
        # повтор того же намерения: дедуп по стабильному id намерения (TZ1) — ничего нового
        s2, _l2 = P.seed_from_plan(plan, commit=True, save_path=save_path,
                                   existing=list(created.values()))
        created2 = json.loads(save_path.read_text(encoding="utf-8")).get("tasks", {})
        ok_b = s2["made"] == 0 and len(created2) == 1
    return (ok_a and ok_b), (f"первый: made={s1['made']} skip={s1['skipped']} файл={len(created)} "
                             f"повтор: made={s2['made']} файл={len(created2)} · id={first_id}")


def pl5_dry_writes_nothing():
    plan = {"date": "2026-09-04", "store": "atlas-express-film",
            "decisions": [{"id": "new-y", "kind": "new", "what": "Спарсить X на доноре",
                           "owner": "CATEGORIST", "category": "categories",
                           "urgency": "normal", "priority": 50, "why": "",
                           "evidence": "досье", "mode": "dry"}]}
    with tempfile.TemporaryDirectory() as td:
        os.environ["YM_PLAN_DIR"] = td
        plan_p = Path(td) / "ymarket_plan_2026-09-04.json"
        reg_p = Path(td) / "tasks.json"
        try:
            r = P.save_plan(plan, commit=False)
            ok_a = r["dry"] is True and not plan_p.exists()
            s, _l = P.seed_from_plan(plan, commit=False, existing=[], save_path=reg_p)
            ok_b = s["made"] == 1 and s["commit"] is False and not reg_p.exists()
        finally:
            os.environ.pop("YM_PLAN_DIR", None)
    return (ok_a and ok_b), (f"save_dry={r['dry']} файл_плана_нет={not plan_p.exists()} "
                             f"seed_made={s['made']} seed_commit={s['commit']} "
                             f"реестр_не_создан={not reg_p.exists()}")


def pl6_render_honest_and_load():
    empty = {"goods": {}}
    plan = P.build_plan(date_str="2026-09-04", registry=[], dossiers={}, vitrine=empty,
                        journal=[])
    out = "\n".join(P.render_plan(plan))
    ok_a = out.startswith("ПЛАН ДНЯ") and "доказанно живых 0" in out and "не выдумываем" in out
    ok_b = "РЕШЕНИЯ" in out and "нужно слово 0" in out and "watch 1" in out
    # стор: commit → файл; чтение его же → те же решения; нет-файла → (None, None)
    with tempfile.TemporaryDirectory() as td:
        os.environ["YM_PLAN_DIR"] = td
        try:
            r = P.save_plan(plan, commit=True)
            back, err = P.load_plan("2026-09-04")
            ok_c = r["ok"] and err is None and back is not None \
                and back["date"] == "2026-09-04" and len(back["decisions"]) == len(plan["decisions"])
            gone, gerr = P.load_plan("2025-01-01")
            ok_d = gone is None and gerr is None
        finally:
            os.environ.pop("YM_PLAN_DIR", None)
    return (ok_a and ok_b and ok_c and ok_d), (f"title={ok_a} честные-нули={ok_b} стор={ok_c} "
                                               f"нет-файла={ok_d}")


def _run():
    tests = [("PL1 context_no_fabrication", pl1_context_no_fabrication),
             ("PL2 live_only_svverka", pl2_live_only_svverka),
             ("PL3 escalation_is_not_task", pl3_escalation_is_not_task),
             ("PL4 intake_dedup_and_write", pl4_intake_dedup_and_write),
             ("PL5 dry_writes_nothing", pl5_dry_writes_nothing),
             ("PL6 render_honest_and_load", pl6_render_honest_and_load)]
    fails = 0
    for name, fn in tests:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(f"  {_passed(ok)} {name:<26} {detail}")
        fails += 0 if ok else 1
    print(f"\nПЛАНЁРКА (УТРО): {len(tests) - fails}/{len(tests)} зелёных")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run())

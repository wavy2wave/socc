#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — РЕЕСТР ЗАДАНИЙ ЯМ-ЦИКЛА (ymarket_tasks_v1). Сухо, 0₽, без сети.

Проверяем ЗАКОНЫ формата задания (директива «доп задание»), а не «запустилось»:
стабильный id-хеш намерения, универсальность (одна схема ЯМ и ОЗОН), цикл подхвата, владелец
(«удавка на него»), категории, приоритет (важное выше), ПУНКТЫ под гейтом БЕЗ фейк-пасс,
зависимости-блокировки, честная загрузка. Все операции чистые: запись в tmp (env YM_TASKS_PATH),
канонический стор НЕ трогаем.

  TZ1  task_id_stable_dedup       — то же намерение → тот же id; другое «что» → другой id
  TZ2  one_schema_both_markets    — market="ym" и market="ozon" дают валидные записи одной схемы
  TZ3  cycle_required_vocab       — cycle вне словаря → честный отказ; cycle_day проходит
  TZ4  store_optional             — пустой store (общесистемное) валиден; store с магазином сохраняется
  TZ5  owner_required             — без owner → отказ (у задания всегда ответственный)
  TZ6  urgency_default_and_vocab  — не задана → normal; битая → отказ
  TZ7  priority_sort_drives_order — планёрка: P10 перед P30 (важное выше), внутри стабильно
  TZ8  no_fake_pass_gate          — mark_step без evidence/done_by → отказ; с ними → пункт ●;
                                   все пункты ● → задание done; новый пункт обязан быть open
  TZ9  depends_on_blocks          — зависимость не закрыта → waiting; закрыта → задача разблокирована
  TZ10 honest_load                — нет файла → [] без падения; битый файл → [] + load_error
  TZ11 validate_catches_junk      — validate находит битую запись (нет пунктов/market вне словаря)
  TZ12 render_human               — планёрка показывает владельца/магазин/пункты; stats считает
  TZ13 roundtrip_save_load        — запись→чтение сохраняет пункты/evidence/state без потерь
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_tasks_v1 as T   # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


# ЭТАЛОН: пример оператора «ДОБАВИТЬ 10 категорий из магазина NDJ, донор: NDJ».
_NDJ = dict(what="Добавить категории из магазина NDJ (донор NDJ)", owner="CATEGORIST",
            category="categories", market="ym", cycle="cycle_day", store="ndj",
            priority=10)


def tz1_task_id_stable_dedup():
    a, e1 = T.new_task(**_NDJ)
    b, e2 = T.new_task(**_NDJ)
    c, _ = T.new_task(**{**_NDJ, "what": "Другое задание по NDJ"})
    ok = (a and b and a["id"] == b["id"] and a["id"] != c["id"]
          and a["id"].startswith("T-"))
    return ok, f"{a['id']} == {b['id']} ≠ {c['id']} (одно намерение = один id, TZ1)"


def tz2_one_schema_both_markets():
    ym, e1 = T.new_task(**{**_NDJ, "market": "ym"})
    oz, e2 = T.new_task(**{**_NDJ, "market": "ozon"})
    ok = (ym and oz and ym["market"] == "ym" and oz["market"] == "ozon"
          and T.validate(ym) == [] and T.validate(oz) == [])
    return ok, f"ym {ym['id']} + ozon {oz['id']} — одна схема (TZ2)"


def tz3_cycle_required_vocab():
    a, e = T.new_task(**{**_NDJ, "cycle": "nonsense"})
    b, _ = T.new_task(**{**_NDJ, "cycle": "cycle_day"})
    ok = (a is None and e and "cycle" in e and b and b["cycle"] == "cycle_day")
    return ok, f"битый цикл → отказ «{e}» · cycle_day валиден (TZ3)"


def tz4_store_optional():
    sys_, e1 = T.new_task(**{**_NDJ, "store": "", "what": "Общесистемное задание"})
    ndj, e2 = T.new_task(**{**_NDJ, "store": "ndj"})
    ok = (sys_ and sys_["store"] == "" and T.validate(sys_) == []
          and ndj and ndj["store"] == "ndj")
    return ok, f"без магазина {sys_['id']} валиден · с магазином {ndj['id']}[ndj] (TZ4)"


def tz5_owner_required():
    a, e = T.new_task(what="Задание без владельца", owner="", category="other")
    b, _ = T.new_task(what="Задание с владельцем", owner="partners", category="other")
    ok = (a is None and e and "owner" in e and b and b["owner"] == "PARTNERS")
    return ok, f"без owner → отказ «{e}» · partners → {b['owner'] if b else None} (TZ5)"


def tz6_urgency_default_and_vocab():
    a, _ = T.new_task(**{**_NDJ, "urgency": None})
    b, e2 = T.new_task(**{**_NDJ, "urgency": "critical"})
    c, e3 = T.new_task(**{**_NDJ, "urgency": "asap"})
    ok = (a["urgency"] == "normal" and b["urgency"] == "critical" and c is None and e3
          and "urgency" in e3)
    return ok, f"по умолч. normal ({a['urgency']}) · critical ок · «asap» → отказ (TZ6)"


def tz7_priority_sort_drives_order():
    lo, _ = T.new_task(**{**_NDJ, "what": "Малое: категория P30", "priority": 30})
    hi, _ = T.new_task(**{**_NDJ, "what": "Важное: категория P10", "priority": 10})
    rows = T.sort_tasks([lo, hi])
    ok = rows[0]["priority"] == 10 and rows[1]["priority"] == 30
    return ok, f"порядок планёрки: P{rows[0]['priority']} → P{rows[1]['priority']} (TZ7)"


def tz8_no_fake_pass_gate():
    # Двухпунктное задание: закрыть первый пункт → in_progress (не done) — можно проверять
    # повторное закрытие/чужой пункт, пока задание живое (модуль честно режет и по done-гейту).
    b, _ = T.new_task(**{**_NDJ, "what": "Двухпунктное задание NDJ",
                         "steps": [{"id": "s1", "title": "Проверить ключи/донора"},
                                   {"id": "s2", "title": "Добавить категорию 76346336"}]})
    t, err = T.mark_step(b, "s1", done_by="", evidence="проверил")         # кто? отказ
    t, err2 = T.mark_step(b, "s1", done_by="categorist-v1", evidence="")   # чем? отказ
    ok1 = err and "done_by" in err and err2 and "evidence" in err2
    ok2 = all(s["state"] == "open" for s in b["steps"])   # новые пункты обязаны быть open (TZ8)
    b, e3 = T.mark_step(b, "s1", done_by="categorist-v1",
                        evidence="чтение: категория 76346336 добавлена, 13 параметров")
    ok3 = (not e3 and b["state"] == "in_progress" and b["steps"][0]["state"] == "done")
    b, e4 = T.mark_step(b, "s1", done_by="x", evidence="ещё раз")          # повтор → отказ
    b, e5 = T.mark_step(b, "s-no", done_by="x", evidence="нет")            # чужой пункт → отказ
    ok4 = e4 and "уже закрыт" in e4 and e5 and "нет в задании" in e5
    b, e6 = T.mark_step(b, "s2", done_by="categorist-v1", evidence="прочитано СВЕРКОЙ")
    b, e7 = T.mark_step(b, "s2", done_by="y", evidence="незаконно")        # done → не трогаем
    ok5 = (not e6 and b["state"] == "done" and e7 and "пункты не трогаем" in e7)
    ok = ok1 and ok2 and ok3 and ok4 and ok5
    return ok, (f"без who/evidence → отказ · ● только с фактом · повтор/чужой пункт → отказ · "
                f"все ● → done, потом не трогаем")


def tz9_depends_on_blocks():
    dep, _ = T.new_task(**{**_NDJ, "what": "Сначала: паспорт магазина ndj"})
    child, _ = T.new_task(**{**_NDJ, "what": "Потом: залить категории ndj",
                             "depends_on": [dep["id"]]})
    ch_open = T.derive(child, done_ids=set())
    ch_unl = T.derive(child, done_ids={dep["id"]})
    # закрыли зависимость → ребёнок разблокирован
    dep2, _ = T.mark_step(dep, "s1", done_by="partners-v1", evidence="ключи + склад проверены чтением")
    ch_after = T.derive(child, done_ids=T.done_ids_of([dep2]))
    ok = ch_open == "waiting" and ch_unl in ("open", "in_progress") and ch_after in ("open", "in_progress")
    return ok, f"зависимость жива → waiting; зависимость ● → {ch_after} (TZ9)"


def tz10_honest_load():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.json"
        empty, err_empty = T.load(p)
        p.write_text("{broken json")
        broken, err = T.load(p)
        p.write_text(json.dumps({"schema": "другая", "tasks": {}}))
        wrong_schema, _ = T.load(p)
    ok = (empty == [] and err_empty is None and broken == [] and err and "load_error" in err
          and wrong_schema == [])
    return ok, f"нет файла → [] · битый → [] + load_error ({err.get('load_error')[:30] if err else '—'}) (TZ10)"


def tz11_validate_catches_junk():
    good, _ = T.new_task(**{**_NDJ})
    junk = dict(good, steps=[], market="mars")
    probs = T.validate(junk)
    ok = (probs and any("пункта" in x for x in probs) and any("market" in x for x in probs))
    return ok, f"валидация видит битое: {probs} (TZ11)"


def tz12_render_human():
    a, _ = T.new_task(**{**_NDJ})
    b, _ = T.new_task(**{**_NDJ, "what": "Акция на плёнку", "category": "promo",
                         "owner": "STRATEGIST", "urgency": "high", "priority": 5})
    lines = T.render_plannerka([a, b])
    txt = "\n".join(lines)
    s = T.stats([a, b])
    ok = (lines and any("NDJ" in l and "CATEGORIST" in l and "пункты" in l for l in lines)
          and any("STRATEGIST" in l for l in lines)
          and s["total"] == 2 and s["critical_high_open"] == 1)
    return ok, f"планёрка {len(lines)} строк · владелец/магазин/пункты видны · stats {s['total']}/{s['critical_high_open']} (TZ12)"


def tz13_roundtrip_save_load():
    a, _ = T.new_task(**{**_NDJ})
    a, _ = T.mark_step(a, "s1", done_by="categorist-v1",
                       evidence="чтение: категория 76346336 есть, 13 параметров")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.json"
        r = T.save([a], path=p)
        back, err = T.load(p)
    ok = (r.get("ok") and back and back[0]["id"] == a["id"]
          and back[0]["steps"][0]["state"] == "done"
          and back[0]["steps"][0]["evidence"] == a["steps"][0]["evidence"]
          and back[0]["state"] == "done" and err is None)
    return ok, f"roundtrip: {a['id']} пункт ●+evidence+state=done сохранились (TZ13)"


TESTS = [
    ("TZ1  id-стабилен/дедуп", tz1_task_id_stable_dedup),
    ("TZ2  одна схема ЯМ+ОЗОН", tz2_one_schema_both_markets),
    ("TZ3  цикл из словаря", tz3_cycle_required_vocab),
    ("TZ4  магазин необязателен", tz4_store_optional),
    ("TZ5  владелец обязателен", tz5_owner_required),
    ("TZ6  срочность дефолт/словарь", tz6_urgency_default_and_vocab),
    ("TZ7  важное выше списка", tz7_priority_sort_drives_order),
    ("TZ8  гейт БЕЗ фейк-пасс", tz8_no_fake_pass_gate),
    ("TZ9  зависимость блокирует", tz9_depends_on_blocks),
    ("TZ10 честная загрузка", tz10_honest_load),
    ("TZ11 валидация видит битое", tz11_validate_catches_junk),
    ("TZ12 рендер/сводка", tz12_render_human),
    ("TZ13 roundtrip save/load", tz13_roundtrip_save_load),
]


def main():
    print("🎯 ПРИЁМКА · РЕЕСТР ЗАДАНИЙ (формат ЯМ-ЦИКЛА, 0₽, без сети, tmp-стор)")
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
        print("✅ Реестр честен: задание всегда с владельцем/циклом/пунктами, пункт закрывается "
              "только с evidence (без фейк-пасс), одно намерение = один id, ОЗОН ест ту же схему.")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

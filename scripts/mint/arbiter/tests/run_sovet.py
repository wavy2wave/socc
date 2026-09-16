#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — СОВЕТ ДИРЕКТОРОВ ОРГАНОВ (ymarket_sovet_v1): лицевая сторона ПЛАНА ДНЯ, анти-театр.

Герметично, 0₽: ВСЕ входы (реестр/досье/леджер/журнал/планы) инъецируются документами; запись только
в tempfile-песочницу (env YM_SOVET_DIR / YM_PLAN_DIR). Реальный диск/сеть/Маркет не трогаем. LLM
НЕ зовём — председатель инъецируется chair_fn (фейк).

ЗАКОНЫ приёмки (канон YM_SOVET_V1.md):
  VL1 числа председателя ⊆ чисел входных голосов; число вне голосов/пусто/сбой → детерминированный
        свод (validated=false) — председатель не выдумывает сверх голосов.
  VL2 факт/голос без ссылки-источника отбрасывается (орган не говорит из воздуха).
  VL3 пропиздон ТОЛЬКО из miss-движка; прогресс (закрыт пункт) / waiting (зависимость) / live
        (PRICER-слово) — НЕ миссы; carry вчера→сегодня без движения — мисс.
  VL4 dry ничего не пишет; commit → tmp+replace в sovet/ymarket_sovet_<дата>.json.
  VL5 пустой совет (нет реестра/очереди/леджера/заказов/сущ. решений) файл даты НЕ создаёт;
        рендер по отсутствию — честно «совет не собирался».
  VL6 once-per-date: файл даты уже есть → повторный resolve не перезаписывает.
  VL7 совет сам НЕ порождает задания: в коде модуля нет вызова T.new_task/T.save/T.mark_step
        (статический скан) и resolve с kind=new не трогает реестр (никакого интэйка в совете).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
for p in (str(ARB),):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_sovet_v1 as SV    # noqa: E402
import ymarket_tasks_v1 as T     # noqa: E402

_DATE = "2026-09-04"
_PREV = "2026-09-03"


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _task(what, owner, category, *, cycle="cycle_day", store="atlas-express-film",
          urgency="normal", priority=50, body="", source="test", depends_on=(), steps=None):
    t, err = T.new_task(what=what, owner=owner, category=category, cycle=cycle,
                        store=store, urgency=urgency, priority=priority,
                        body=body, source=source, depends_on=depends_on, steps=steps)
    assert err is None, f"new_task: {err}"
    return t


def _good(oid, cat, verdict="PASS"):
    return {"offer_id": oid, "store_slug": "atlas-express-film", "category_slug": cat,
            "last_verified": {"verdict": verdict, "ts": "2026-09-04T06:00:00+00:00"}}


def _jrn(**kw):
    base = {"ts": f"{_DATE}T06:00:00+00:00", "date": _DATE,
            "kpis": {"urgent_orders": 0}, "burning": 0, "top_move": "ASSORTMENT_WIDEN"}
    base.update(kw)
    return [base]


def _dec_carry(task, *, mode="dry"):
    """Plannerka-стиль carry-решение плана для задания (refs.task_id — как propose)."""
    return {"id": "carry-" + task["id"], "kind": "carry", "what": task["what"],
            "where": task.get("store") or "—", "owner": task.get("owner"),
            "category": task.get("category"), "urgency": task.get("urgency"),
            "priority": task.get("priority", 50),
            "why": "уже в реестре, владелец-орган есть",
            "evidence": f"реестр ymarket_tasks.json · {task['id']}",
            "mode": mode, "refs": {"task_id": task["id"]}}


def _dec(kind, what, owner, *, category="categories", mode="dry", refs=None):
    return {"id": f"{kind}-x", "kind": kind, "what": what, "owner": owner,
            "category": category, "urgency": "normal", "priority": 50,
            "why": "", "evidence": "досье", "mode": mode, "refs": refs or {}}


def _proto_universe(doc, date_str):
    """«Вселенная чисел» из ПРОТОКОЛА (голоса/миссы/счётчики плана) — независимая сверка VL1(г)."""
    uni = set()
    for v in doc.get("voices") or []:
        for f in v.get("facts") or []:
            uni |= SV._numbers(f.get("text", "")) | SV._numbers(f.get("source", ""))
    for m in doc.get("misses") or []:
        uni |= SV._numbers(m.get("evidence", ""))
    pl = doc.get("plan") or {}
    uni |= {int(pl.get(k) or 0) for k in ("carry", "new", "escalation", "watch")}
    uni.add(len(doc.get("waiting_operator") or []))
    uni.add(0)                                # «пропиздонов 0» — законный честный ноль
    uni -= SV._date_numbers(date_str)
    return uni


# ── VL1: председатель не выдумывает числа ───────────────────────────────────────

def vl1_chair_numbers_within_voices():
    # мир: 1 открытое задание CATEGORIST + 1 доказанно живой → числа {1, 0, ...} из голосов
    t = _task("Спарсить streich на доноре", "CATEGORIST", "categories")
    lib = {"goods": {"a": _good("ARB-1", "vozdushno-puzyrkovaya-plenka")}}
    # (а) председатель говорит ТОЛЬКО числа голосов → llm-текст принят, validated True
    good_text = "вижу живых 1 и открытых заданий 1; пропиздонов нет."
    d_ok = SV.compose(date_str=_DATE, registry=[t], dossiers={}, vitrine=lib, journal=[],
                      chair_fn=lambda: good_text)
    ok_a = d_ok["chair"]["mode"] == "llm" and d_ok["chair"]["validated"] is True \
        and d_ok["chair"]["text"] == good_text
    # (б) число «77» НЕ звучало в голосах → свод, validated False (VL1)
    d_bad = SV.compose(date_str=_DATE, registry=[t], dossiers={}, vitrine=lib, journal=[],
                       chair_fn=lambda: "за сутки закрыто 77 — восхитительно")
    ok_b = d_bad["chair"]["mode"] == "svod" and d_bad["chair"]["validated"] is False \
        and "VL1" in d_bad["chair"].get("note", "")
    # (в) сбой председателя → сухой свод, validated False, не паника
    def _boom():
        raise RuntimeError("агент лёг")
    d_err = SV.compose(date_str=_DATE, registry=[t], dossiers={}, vitrine=lib, journal=[],
                       chair_fn=_boom)
    ok_c = d_err["chair"]["mode"] == "svod" and d_err["chair"]["validated"] is False
    # (г) сухой свод (chair_fn=None) — validated True и числа внутри свода НЕ вне голосов
    d_sv = SV.compose(date_str=_DATE, registry=[t], dossiers={}, vitrine=lib, journal=[],
                      chair_fn=None)
    svod_nums = SV._numbers(d_sv["chair"]["text"])
    uni = _proto_universe(d_sv, _DATE)
    ok_d = d_sv["chair"]["validated"] is True and d_sv["chair"]["mode"] == "svod" \
        and svod_nums - SV._date_numbers(_DATE) <= uni
    return (ok_a and ok_b and ok_c and ok_d), (
        f"принят={ok_a} отклонён77={ok_b} сбой→свод={ok_c} свод-числа-в-голосах={ok_d}"
        f" · note={d_bad['chair'].get('note')!r}")


# ── VL2: факт/голос без источника отбрасывается ─────────────────────────────────

def vl2_unsourced_dropped():
    voices = [
        {"organ": "ПУСТОЙ", "facts": [{"text": "факт без источника"}], "nuzhno_slovo": []},
        {"organ": "ЛЖЕЦ", "facts": [{"text": "есть источник", "source": "док"},
                                    {"text": "нет источника"}, {"text": 1}], "nuzhno_slovo": []},
        {"organ": "ПРОСИТЕЛЬ", "facts": [], "nuzhno_slovo": [{"what": "нужно слово", "source": "досье"}]},
    ]
    d = SV.compose(date_str=_DATE, registry=[], dossiers={}, vitrine={"goods": {}},
                   journal=[], voices=voices)
    names = [v["organ"] for v in d["voices"]]
    lies = next((v for v in d["voices"] if v["organ"] == "ЛЖЕЦ"), None)
    ok_a = "ПУСТОЙ" not in names                      # голос без единого sourced-факта — вон
    ok_b = lies is not None and len(lies["facts"]) == 1 \
        and lies["facts"][0]["text"] == "есть источник"
    ok_c = all(isinstance(f, dict) and f.get("text") and f.get("source")
               for v in d["voices"] for f in v.get("facts", []))
    # рендер не падает и показывает источники
    out = "\n".join(SV.render_sovet(d))
    ok_d = "ГОЛОСА" in out and "док" in out
    return (ok_a and ok_b and ok_c and ok_d), (
        f"пустой-вон={ok_a} лжец-только-с-источником={ok_b} все-факты-с-источником={ok_c}"
        f" рендер={ok_d} · names={names}")


# ── VL3: пропиздон только из miss-движка ────────────────────────────────────────

def vl3_miss_true_positive():
    t = _task("Спарсить категорию streich на доноре", "CATEGORIST", "categories")
    prev = {"date": _PREV, "decisions": [_dec_carry(t)]}          # вчера нёс в плане
    today = {"date": _DATE, "decisions": [_dec_carry(t)]}         # сегодня тоже, а движения 0
    d = SV.compose(date_str=_DATE, registry=[t], dossiers={}, vitrine={"goods": {}},
                   journal=[], plan=today, prev_plan=prev)
    ok = len(d["misses"]) == 1 and d["misses"][0]["organ"] == "CATEGORIST" \
        and d["misses"][0]["task_id"] == t["id"] and d["misses"][0]["since"] == _PREV \
        and "0" in d["misses"][0]["evidence"]
    # а совет не «прощает» молча — пропиздон в своде председателя
    ok2 = "пропиздоны" in d["chair"]["text"]
    return (ok and ok2), (f"миссов={len(d['misses'])} орган="
                          f"{d['misses'][0]['organ'] if d['misses'] else '—'}"
                          f" в-своде={ok2} · {d['misses'][0]['evidence'] if d['misses'] else ''}")


def vl3_no_miss_progress_waiting_live():
    # (а) прогресс: тот же carry, но пункт закрыт → НЕ мисс (in_progress, ndone>0)
    t1 = _task("Подготовить карточку ARB-1", "CATEGORIST", "cards",
               steps=[{"id": "s1", "title": "шаг1"}, {"id": "s2", "title": "шаг2"}])
    t1m, _ = T.mark_step(t1, "s1", done_by="test", evidence="карточка собрана")
    assert t1m["id"] == t1["id"]
    prev1 = {"date": _PREV, "decisions": [_dec_carry(t1)]}
    d1 = SV.compose(date_str=_DATE, registry=[t1m], dossiers={}, vitrine={"goods": {}},
                    journal=[], plan={"date": _DATE, "decisions": [_dec_carry(t1m)]},
                    prev_plan=prev1)
    ok_a = len(d1["misses"]) == 0
    # (б) waiting: задание зависит от незакрытого → НЕ мисс (TZ9)
    t2 = _task("Залить категорию streich", "CATEGORIST", "categories",
               depends_on=("T-никогда",))
    d2 = SV.compose(date_str=_DATE, registry=[t2], dossiers={}, vitrine={"goods": {}},
                    journal=[], plan={"date": _DATE, "decisions": [_dec_carry(t2)]},
                    prev_plan={"date": _PREV, "decisions": [_dec_carry(t2)]})
    ok_b = len(d2["misses"]) == 0
    # (в) live PRICER: живая переценка наружу = слово оператора (RUBICON), НЕ мисс
    t3 = _task("Поднять цену до пола КПИ", "PRICER", "pricing")
    d3 = SV.compose(date_str=_DATE, registry=[t3], dossiers={}, vitrine={"goods": {}},
                    journal=[], plan={"date": _DATE, "decisions": [_dec_carry(t3, mode="live")]},
                    prev_plan={"date": _PREV, "decisions": [_dec_carry(t3, mode="live")]})
    ok_c = len(d3["misses"]) == 0
    # (г) новое вчера не carry (не было в prev) → не мисс
    d4 = SV.compose(date_str=_DATE, registry=[t2], dossiers={}, vitrine={"goods": {}},
                    journal=[], plan={"date": _DATE, "decisions": [_dec_carry(t2)]},
                    prev_plan=None)
    ok_d = len(d4["misses"]) == 0
    return (ok_a and ok_b and ok_c and ok_d), (f"прогресс={ok_a} waiting={ok_b} live-pricer={ok_c}"
                                               f" нет-prev={ok_d}")


# ── VL4 + VL5 + VL6: стор dry/commit, пустой совет, once-per-date ───────────────

def _sandbox():
    td = tempfile.mkdtemp()
    os.environ["YM_SOVET_DIR"] = td
    os.environ["YM_PLAN_DIR"] = td
    return Path(td)


def _rich_inputs():
    t = _task("Спарсить streich на доноре", "CATEGORIST", "categories")
    lib = {"goods": {"a": _good("ARB-1", "vozdushno-puzyrkovaya-plenka")}}
    return t, lib


def vl4_dry_nothing_commit_writes():
    t, lib = _rich_inputs()
    td = _sandbox()
    try:
        rd = SV.resolve_daily(date_str=_DATE, commit=False, registry=[t], dossiers={},
                              vitrine=lib, journal=[])
        files0 = list(td.glob("ymarket_sovet_*"))
        ok_a = rd["dry"] is True and rd["gathered"] is True and rd["path"] is None \
            and len(files0) == 0
        rc = SV.resolve_daily(date_str=_DATE, commit=True, registry=[t], dossiers={},
                              vitrine=lib, journal=[])
        files1 = list(td.glob("ymarket_sovet_*"))
        proto, err = SV.load_protocol(_DATE)
        ok_b = rc["dry"] is False and rc["ok"] and len(files1) == 1 \
            and proto is not None and err is None and proto["schema"] == SV.SCHEMA \
            and proto["date"] == _DATE
        # tmp-файл не остался (tmp+replace, без .tmp хвоста)
        ok_c = not [f for f in files1 if f.name.endswith(".tmp")]
    finally:
        os.environ.pop("YM_SOVET_DIR", None)
        os.environ.pop("YM_PLAN_DIR", None)
    return (ok_a and ok_b and ok_c), (f"dry-файлов={len(files0)} commit-файл={ok_b} tmp-чисто={ok_c}"
                                      f" schema={proto.get('schema') if proto else '—'}")


def vl5_empty_no_file_and_honest_render():
    td = _sandbox()
    try:
        # (а) ПУСТОЙ мир: ни реестра, ни очереди, ни леджера, ни журнала, ни миссов —
        #     даже если plannerka внутри наставила watch-orders (вечный «нет горящих») —
        #     совет не собирается, файл даты НЕ пишется (VL5: нет «очереди»/содержания)
        r = SV.resolve_daily(date_str=_DATE, commit=True, registry=[], dossiers={},
                             vitrine={"goods": {}}, journal=[])
        files = list(td.glob("ymarket_sovet_*"))
        ok_a = r["gathered"] is False and len(files) == 0 and "не собирался" in r["reason"]
        # (б) НО очередь/содержание ЕСТЬ (категория в очереди, не сканирована) — совет обязан
        #     собраться и честно доложить «ждёт», а не смолчать (система жива)
        doss = {"categories": {"vozdushno-puzyrkovaya-plenka": {
            "title_ru": "v", "state": "open", "priority": 50, "task_id": "T-x",
            "mapping": {"need_mapping": False, "market_category_id": None},
            "scan": {"when": None}}}}            # категория не сканирована → watch-unscanned
        r2 = SV.resolve_daily(date_str=_DATE, commit=True, registry=[], dossiers=doss,
                              vitrine={"goods": {}}, journal=[])
        files2 = list(td.glob("ymarket_sovet_*"))
        ok_b = r2["gathered"] is True and r2["dry"] is False and r2["ok"] \
            and len(files2) == 1
        # рендер существующего протокола (б) не выдумывает: честный доклад КАТЕГОРИЙЩИКА о том,
        # что в очереди стоит, без фальшивой готовности/«в работе»
        txt = "\n".join(SV.render_sovet(r2["protocol"]))
        ok_b2 = "в очереди 1" in txt and "готово к заливу 0" in txt \
            and "не собирался" not in txt
        # (в) рендер по ОТСУТСТВИЮ протокола — честно «не собирался», а не пустой лист
        out = SV.render_sovet(None, _DATE)
        ok_c = isinstance(out, list) and "не собирался" in "\n".join(out)
    finally:
        os.environ.pop("YM_SOVET_DIR", None)
        os.environ.pop("YM_PLAN_DIR", None)
    return (ok_a and ok_b and ok_b2 and ok_c), (f"пусто-без-файла={ok_a} "
                                                f"очередь-есть-собирается={ok_b} "
                                                f"рендер-доклада-не-выдумка={ok_b2} "
                                                f"рендер-по-отсутствию={ok_c}")


def vl6_once_per_date_not_overwritten():
    t, lib = _rich_inputs()
    td = _sandbox()
    try:
        r1 = SV.resolve_daily(date_str=_DATE, commit=True, registry=[t], dossiers={},
                              vitrine=lib, journal=[])
        first_json = json.dumps(r1["protocol"], ensure_ascii=False, sort_keys=True)
        # второй resolve той же даты даже с ДРУГИМИ входами не перезаписывает (файл даты уже есть)
        t2 = _task("Другое задание дня", "CATEGORIST", "cards")
        r2 = SV.resolve_daily(date_str=_DATE, commit=True, registry=[t, t2], dossiers={},
                              vitrine={"goods": {}}, journal=[])
        files = list(td.glob("ymarket_sovet_*"))
        proto, _ = SV.load_protocol(_DATE)
        second_json = json.dumps(r2["protocol"], ensure_ascii=False, sort_keys=True)
        ok = r2["already"] is True and len(files) == 1 and first_json == second_json
    finally:
        os.environ.pop("YM_SOVET_DIR", None)
        os.environ.pop("YM_PLAN_DIR", None)
    return ok, (f"already={r2['already']} файлов={len(files)} "
                f"не-перезаписан={first_json == second_json}")


# ── VL7: совет сам не порождает задания ────────────────────────────────────────

def vl7_no_task_writes():
    src = Path(ARB / "ymarket_sovet_v1.py").read_text(encoding="utf-8")
    banned = [r"T\.new_task\s*\(", r"T\.save\s*\(", r"T\.mark_step\s*\(",
              r"T\.reopen_step\s*\(", r"seed_from_plan", r"new_task\("]
    hits = [pat for pat in banned if re.search(pat, src)]
    ok_a = not hits
    # семантика: даже решения kind=new в плане совет НЕ интэйкает — пишется только протокол
    plan = {"date": _DATE, "store": "atlas-express-film",
            "decisions": [_dec("new", "Новое задание", "CATEGORIST")]}
    td = _sandbox()
    os.environ["YM_TASKS_PATH"] = str(td / "tasks.json")
    try:
        r = SV.resolve_daily(date_str=_DATE, commit=True, registry=[], dossiers={},
                             vitrine={"goods": {}}, journal=[], plan=plan)
        ok_b = r["ok"] and r["gathered"] is True \
            and not (td / "tasks.json").exists()          # реестр не тронут — совет не сеет
        files = list(td.glob("ymarket_sovet_*"))
        ok_c = len(files) == 1
    finally:
        os.environ.pop("YM_SOVET_DIR", None)
        os.environ.pop("YM_PLAN_DIR", None)
        os.environ.pop("YM_TASKS_PATH", None)
    return (ok_a and ok_b and ok_c), (f"статически-чисто={ok_a} new-не-сеет={ok_b}"
                                      f" протокол={ok_c} hits={hits or '—'}")


def _run():
    tests = [("VL1 chair_numbers_within", vl1_chair_numbers_within_voices),
             ("VL2 unsourced_dropped", vl2_unsourced_dropped),
             ("VL3 miss_true_positive", vl3_miss_true_positive),
             ("VL3 no_miss_progress_wait_live", vl3_no_miss_progress_waiting_live),
             ("VL4 dry_nothing_commit_write", vl4_dry_nothing_commit_writes),
             ("VL5 empty_no_file_honest", vl5_empty_no_file_and_honest_render),
             ("VL6 once_per_date", vl6_once_per_date_not_overwritten),
             ("VL7 no_task_writes", vl7_no_task_writes)]
    fails = 0
    for name, fn in tests:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(f"  {_passed(ok)} {name:<30} {detail}")
        fails += 0 if ok else 1
    print(f"\nСОВЕТ ДИРЕКТОРОВ: {len(tests) - fails}/{len(tests)} зелёных")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run())

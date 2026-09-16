#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — СПОРЫ ОРГАНОВ (ymarket_sovet_spory_v1): слой 2 СОВЕТА, «живое общение со смыслом».

Герметично, 0₽: ВСЕ входы (реестр/досье/леджер/журнал/планы) инъецируются документами; план-диск и
стор споров — только tempfile-песочница (env YM_SPORY_DIR / YM_PLAN_DIR). Реальный диск/сеть/Маркет
не трогаем. LLM НЕ зовём — speak_fn инъецируется фейком, дефолт-мозг никогда (нет live-слова на него).

Что проверяем (детерминированное ядро споров + гейт LLM-озвучки + стор):
  d0  gate=off: даже с speak_fn и словом — озвучки НЕТ, детерминированный слой цел (М2).
  d1  read-чистота: resolve dry ничего не пишет, позиции/споры на месте.
  d2  W1 (КАТЕГОРИЙЩИК ⇄ ЦИКЛ-1): партия готова, витрина по СВЕРКА-PASS категории не видит,
        план ставит watch-ready → конфликт; НО карточка появилась → W1 молчит (М1, нет фейк-спора).
  d3  W2 (УПРАВЛЯЮЩИЙ ⇄ владелец): просроченный carry — конфликт при улике намерения (тело),
        signal при голом задании (М4); обе стороны с grounding.
  d4  W2 снимается, если план отнёс задание к слову/наблюдению (тот же task_id) — не фейк-обвинение.
  d5  W3 (PRICER, signal с VL3-оговоркой): переценка 2-й день в carry, шагов 0, данные сухого
        расчёта есть — вопрос оператору слово/сухой расчёт, НЕ обвинение; PRICER вне miss-движка.
  d6  W4 (два «ждёт слова»): УПРАВЛЯЮЩИЙ приоритет сам не ставит — contention, signal.
  d7  мирный день: позиции есть, прений нет; рендер честно «споров/конфликтов не выявлено».
  d8  экран чисел: фейк-мозг говорит «77» вне фактов → pr_llm:null, screened.fired, [77] вырезан,
        детерминированная позиция/спор НА МЕСТЕ (VL1/VL9).
  d9  экран чисел: голос из чисел фактов → принят, llm:true, screened чист.
  d10 пустой ответ мозга → «мозг молчит», pr_llm:null, детерминика цела (не выдумываем).
  d11 gate=dry без инъекции → детерминированный слой (0 сети), режим dry; gate=None+нет env → off.
  d12 VL5: пустой мир (позиции И споры пусты) → файл даты НЕ создаётся, рендер по отсутствию честный.
  d13 VL6 + стор: commit пишет свой файл (round-trip), второй resolve той же даты не перезаписывает.
  d14 VL7/VL8/VL10 + статик: нет write-API (T.new_task/save/mark_step/seed), файл споров отдельный
        (ymarket_spory_*), мозг импортируется лениво (нет сети до live+слова).
  d15 чистота compose: входы НЕ мутируются (позиции/споры не трогают стора).
  d16 М6: число ИЗ фактов, но приписано неверно → голос пропущен (llm:true) и помечен в рендере
        «мнение, НЕ факт»; в grounding/facts не вливается.
  d17 reconcile «ждёт слова» (04.09): esc-map-{slug} утреннего плана, чьё досье за день подтверждено
        органом (need_mapping=false, id дан) → из ждущих убирается; вечер ничего не добавляет (М3);
        негатив-контроль: всё ещё need_mapping → оба остаются.
"""
from __future__ import annotations

import hashlib
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

import ymarket_sovet_spory_v1 as SP   # noqa: E402
import ymarket_sovet_v1 as SV         # noqa: E402  (сверка пути файла слоя 1)
import ymarket_tasks_v1 as T          # noqa: E402  (new_task — валидная форма задач)

_DATE = "2026-09-04"
_PREV = "2026-09-03"
os.environ.pop("YM_SOVET_SPORY", None)      # чистый старт: гейта из окружения нет


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


# ── мир-билдеры (сырые doc'и, как у run_sovet.py) ──────────────────────────────

def _task(what, owner, category, *, body="", store="atlas-express-film"):
    t, err = T.new_task(what=what, owner=owner, category=category, cycle="cycle_day",
                        store=store, body=body)
    assert err is None, f"new_task: {err}"
    return t


def _good(cat, oid="ARB-1"):
    return {"offer_id": oid, "store_slug": "atlas-express-film", "category_slug": cat,
            "last_verified": {"verdict": "PASS", "ts": f"{_DATE}T06:00:00+00:00"}}


def _jrn(urgent=0):
    return [{"ts": f"{_DATE}T06:00:00+00:00", "date": _DATE,
             "kpis": {"urgent_orders": urgent}, "burning": 0, "top_move": "ASSORTMENT_WIDEN"}]


def _ready_cat(slug, ready, *, market=76346336, verdict="ready_shortlist", task_id=None):
    """Досье-запись: просканирована, партия готова (ready SKU), маппинг ЯМ подтверждён."""
    return {"donor_category": slug, "title_ru": slug, "state": "open", "priority": 50,
            "task_id": task_id,
            "scan": {"when": f"{_PREV} 11:00:00", "verdict": verdict,
                     "readiness": {"ready": ready}},
            "mapping": {"need_mapping": False, "market_category_id": market}}


def _word_cat(slug, *, task_id=None):
    """Досье-запись: ждёт слова оператора на профиль ЯМ (маппинг решает человек, esc-map)."""
    return {"donor_category": slug, "title_ru": slug, "state": "open", "priority": 50,
            "task_id": task_id, "scan": None,
            "mapping": {"need_mapping": True, "market_category_id": None}}


def _doc(cats):
    return {"categories": cats}


def _dec_carry(task, *, mode="dry"):
    return {"id": "carry-" + task["id"], "kind": "carry", "what": task["what"],
            "where": task.get("store") or "—", "owner": task.get("owner"),
            "category": task.get("category"), "urgency": task.get("urgency"),
            "priority": task.get("priority", 50), "why": "уже в реестре, владелец-орган есть",
            "evidence": f"реестр ymarket_tasks.json · {task['id']}",
            "mode": mode, "refs": {"task_id": task["id"]}}


def _plan(*decisions):
    return {"date": _DATE, "store": "atlas-express-film", "decisions": list(decisions)}


def _prev_plan(*decisions):
    return {"date": _PREV, "store": "atlas-express-film", "decisions": list(decisions)}


def _w1_world(with_card=False):
    """W1-кандидат: готовый «streich-plenka»; витрина пуста ИЛИ уже видит карточку СВЕРКА-PASS."""
    goods = {}
    if with_card:
        goods["g1"] = _good("streich-plenka")
    return {"registry": [], "dossiers": _doc({"streich-plenka": _ready_cat("streich-plenka", 1)}),
            "vitrine": {"goods": goods}, "journal": [], "plan": None, "prev_plan": _prev_plan()}


def _sandbox():
    td = tempfile.mkdtemp(prefix="spory_")
    os.environ["YM_SPORY_DIR"] = td
    os.environ["YM_PLAN_DIR"] = td
    return Path(td)


def _teardown():
    os.environ.pop("YM_SPORY_DIR", None)
    os.environ.pop("YM_PLAN_DIR", None)


_WORLD_KEYS = ("registry", "dossiers", "vitrine", "journal", "plan", "prev_plan")


def _comp(**kw):
    """compose_spory на дефолт-мире W1. Мировые ключи перекрывают мир; остальные ключи (gate/word/
    speak_fn/…) пробрасываются в compose как есть. Песочится: план None → build локально."""
    td = _sandbox()
    try:
        w = dict(_w1_world())
        extra = {}
        for k, v in kw.items():
            (w if k in _WORLD_KEYS else extra)[k] = v
        return SP.compose_spory(date_str=_DATE, registry=w["registry"], dossiers=w["dossiers"],
                                vitrine=w["vitrine"], journal=w["journal"], plan=w["plan"],
                                prev_plan=w["prev_plan"], **extra)
    finally:
        _teardown()


def _resolve(commit, *, td, **world):
    return SP.resolve_spory_daily(date_str=_DATE, commit=commit, prev_plan=_prev_plan(), **world)


def _w1_fake(if_hit, *, hit_needle="не состоялся", call_log=None):
    def _f(system, user):
        if call_log is not None:
            call_log.append(user)
        return if_hit if hit_needle in user else ""
    return _f


def _compose_w1_voice(speak_fn, *, gate="live"):
    """W1-мир с озвучкой под гейтом (песочница: план строится локально, сети нет)."""
    td = _sandbox()
    try:
        w = _w1_world()
        return SP.compose_spory(date_str=_DATE, gate=gate, word=True, speak_fn=speak_fn,
                                registry=w["registry"], dossiers=w["dossiers"],
                                vitrine=w["vitrine"], journal=w["journal"], plan=w["plan"],
                                prev_plan=w["prev_plan"])
    finally:
        _teardown()


# ── d0: gate=off — озвучки нет даже при speak_fn и слове (М2) ───────────────────

def d0_gate_off_blocks_voice():
    calls = []
    doc = _comp(gate="off", word=True,
                speak_fn=lambda s, u: calls.append(u) or "голос")
    ok_a = doc["mode"] == "off" and calls == [] and len(doc["positions"]) >= 1 \
        and any(d["id"].startswith("W1-") for d in doc["disputes"])
    ok_b = all(p.get("pr_llm") is None and p.get("llm") is False for p in doc["positions"]) \
        and all(d.get("pr_llm") is None for d in doc["disputes"])
    # детерминированный слой НЕ пострадал: спор на месте, grounding-факты со ссылками (VL2)
    w1 = next(d for d in doc["disputes"] if d["id"].startswith("W1-"))
    ok_c = w1["kind"] == "conflict" and w1["between"] == ["КАТЕГОРИЙЩИК", "ЦИКЛ-1"] \
        and all(isinstance(g, dict) and g.get("text") and g.get("source") for g in w1["grounding"])
    return (ok_a and ok_b and ok_c), (f"mode={doc['mode']} calls={len(calls)} "
                                      f"позиций={len(doc['positions'])} w1={ok_c} llm-пусто={ok_b}")


# ── d1: read-чистота — resolve dry ничего не пишет ──────────────────────────────

def d1_dry_no_write():
    td = _sandbox()
    try:
        w = _w1_world()
        r = _resolve(False, td=td, registry=w["registry"], dossiers=w["dossiers"],
                     vitrine=w["vitrine"], journal=w["journal"])
        files = list(td.glob("ymarket_spory_*"))
        ok_a = r["dry"] is True and r["gathered"] is True and r["path"] is None and len(files) == 0
        ok_b = any(d["id"].startswith("W1-") for d in (r["doc"] or {}).get("disputes", [])) \
            and r["reason"] == "dry — споры не записаны"
    finally:
        _teardown()
    return (ok_a and ok_b), (f"dry-без-записи={ok_a} gathered={r['gathered']} "
                             f"файлов={len(files)} W1-дет-в-doc={ok_b}")


# ── d2: W1 срабатывает на реальном противоречии и молчит, когда карточка есть (М1) ──

def d2_w1_fires_and_negative():
    doc = _comp()
    w1s = [d for d in doc["disputes"] if d["id"].startswith("W1-")]
    ok_a = len(w1s) == 1 and w1s[0]["kind"] == "conflict" \
        and w1s[0]["between"] == ["КАТЕГОРИЙЩИК", "ЦИКЛ-1"] \
        and "не состоялся" in w1s[0]["summary"] and len(w1s[0]["grounding"]) >= 3
    # негатив (М1): карточка УЖЕ в витрине (СВЕРКА PASS) — W1 молчит: спора о заливе нет
    doc2 = _comp(**{"vitrine": {"goods": {"g1": _good("streich-plenka")}}})
    w1_neg = [d for d in doc2["disputes"] if d["id"].startswith("W1-")]
    ok_b = w1_neg == [] and doc2["sources"]["vitrine_live"] == 1
    return (ok_a and ok_b), (f"W1={len(w1s)} конфликт={ok_a} · негатив-без-W1={ok_b}"
                             f" (карточка в витрине={doc2['sources']['vitrine_live']})")


# ── d3: W2 — просроченный carry: конфликт при улике, signal при голом (М4) ──────

def d3_w2_conflict_and_signal():
    t_conf = _task("Спарсить streich на доноре", "CATEGORIST", "categories",
                   body="начал — жду 2-й лист XLSX донора")
    d_conf = SP.compose_spory(date_str=_DATE, registry=[t_conf], dossiers={},
                              vitrine={"goods": {}}, journal=[], plan=_plan(_dec_carry(t_conf)),
                              prev_plan=_prev_plan(_dec_carry(t_conf)))
    conf = [d for d in d_conf["disputes"] if d["id"].startswith(f"W2-{_DATE}-{t_conf['id']}")]
    ok_a = len(conf) == 1 and conf[0]["kind"] == "conflict" \
        and conf[0]["between"] == ["УПРАВЛЯЮЩИЙ-МОЗГ", "CATEGORIST"] \
        and "просрочено" in conf[0]["summary"] and conf[0]["proposal"]
    t_sig = _task("Спарсить karton-i-gofrokarton на доноре", "CATEGORIST", "categories")
    d_sig = SP.compose_spory(date_str=_DATE, registry=[t_sig], dossiers={},
                             vitrine={"goods": {}}, journal=[], plan=_plan(_dec_carry(t_sig)),
                             prev_plan=_prev_plan(_dec_carry(t_sig)))
    sig = [d for d in d_sig["disputes"] if d["id"].startswith(f"W2-{_DATE}-{t_sig['id']}")]
    ok_b = len(sig) == 1 and sig[0]["kind"] == "signal" \
        and sig[0]["between"] == ["УПРАВЛЯЮЩИЙ-МОЗГ"] \
        and "не обвинение" in sig[0].get("note", "")
    # обе стороны спора с grounding-фактами, ничего не из воздуха (VL2)
    ok_c = all(g.get("text") and g.get("source") for d in conf + sig for g in d["grounding"])
    return (ok_a and ok_b and ok_c), (f"конфликт={ok_a} сигнал={ok_b} grounding={ok_c}")


# ── d4: W2 снимается, если план отнёс задание к слову/наблюдению ────────────────

def d4_w2_excused_by_plan_word():
    t = _task("Спарсить vozduh na donore", "CATEGORIST", "categories")
    # (а) план отнёс ЗАДАНИЕ к наблюдению (watch, тот же task_id) → УПРАВЛЯЮЩИЙ W2 не поднимает
    plan_word = _plan(_dec_carry(t),
                      {"id": "watch-ready-x", "kind": "watch", "what": "партия ждёт слова",
                       "owner": "CATEGORIST", "category": "categories", "mode": "live",
                       "refs": {"task_id": t["id"]}})
    d_exc = SP.compose_spory(date_str=_DATE, registry=[t], dossiers={},
                             vitrine={"goods": {}}, journal=[], plan=plan_word,
                             prev_plan=_prev_plan(_dec_carry(t)))
    exc = [d for d in d_exc["disputes"] if d["id"].startswith(f"W2-{_DATE}-{t['id']}")]
    ok_a = exc == []
    # (б) НЕ-смежное наблюдение (другое задание) W2 НЕ снимает — иначе любой watch глушил бы споры
    plan_other = _plan(_dec_carry(t),
                       {"id": "watch-ready-y", "kind": "watch", "what": "другая категория",
                        "owner": "CATEGORIST", "category": "categories", "mode": "live",
                        "refs": {"task_id": "T-другое"}})
    d_keep = SP.compose_spory(date_str=_DATE, registry=[t], dossiers={},
                              vitrine={"goods": {}}, journal=[], plan=plan_other,
                              prev_plan=_prev_plan(_dec_carry(t)))
    keep = [d for d in d_keep["disputes"] if d["id"].startswith(f"W2-{_DATE}-{t['id']}")]
    ok_b = len(keep) == 1
    return (ok_a and ok_b), (f"слово-то-же-задание→W2-снят={ok_a} чужое-наблюдение→W2-жив={ok_b}")


# ── d5: W3 — PRICER: слово/сухой расчёт, НЕ обвинение (VL3) ─────────────────────

def d5_w3_pricer_signal():
    tp = _task("Поднять цену до пола КПИ", "PRICER", "pricing")
    lib = {"goods": {"a": _good("vozdushno-puzyrkovaya-plenka")}}
    d = SP.compose_spory(date_str=_DATE, registry=[tp], dossiers={}, vitrine=lib, journal=[],
                         plan=_plan(_dec_carry(tp, mode="live")),
                         prev_plan=_prev_plan(_dec_carry(tp, mode="live")))
    w3 = [x for x in d["disputes"] if x["id"].startswith(f"W3-{_DATE}-{tp['id']}")]
    ok_a = len(w3) == 1 and w3[0]["kind"] == "signal" \
        and set(w3[0]["between"]) == {"PRICER", "УПРАВЛЯЮЩИЙ-МОЗГ"}
    ok_b = "VL3" in w3[0].get("note", "") and "не обвинение" in w3[0]["summary"].lower() \
        and "слово или сухой" in w3[0]["summary"]
    # PRICER = слово, не лень: miss-движок его НЕ тащит → W2 (обвинение-по-просрочке) не возникает
    ok_c = not any(x["id"].startswith("W2-") for x in d["disputes"])
    return (ok_a and ok_b and ok_c), (f"W3-signal={ok_a} VL3-оговорка={ok_b} W2-не-возник={ok_c}")


# ── d6: W4 — два «ждёт слова», приоритет назначает оператор ─────────────────────

def d6_w4_word_contention():
    doss = _doc({"polyetilenovaya-plenka": _word_cat("polyetilenovaya-plenka"),
                 "karton-i-gofrokarton": _word_cat("karton-i-gofrokarton")})
    d = _comp(registry=[], dossiers=doss, vitrine={"goods": {}})
    w4 = [x for x in d["disputes"] if x["id"].startswith("W4-")]
    ok_a = len(w4) == 1 and w4[0]["kind"] == "signal" \
        and w4[0]["between"] == ["УПРАВЛЯЮЩИЙ-МОЗГ"] and "приоритет" in w4[0]["proposal"]
    # позиция УПРАВЛЯЮЩЕГО честно перечисляет оба слова в grounding
    ok_b = any("ждёт слова" in p.get("stance", "") and p["organ"] == "УПРАВЛЯЮЩИЙ-МОЗГ"
               for p in d["positions"]) and len(w4[0]["grounding"]) == 2
    return (ok_a and ok_b), (f"W4={len(w4)} сигнал-контеншн={ok_a} позиция-и-2-grounding={ok_b}")


# ── d7: мирный день — позиции есть, прений нет ──────────────────────────────────

def d7_peaceful_no_disputes():
    doss = _doc({"streich-plenka": _ready_cat("streich-plenka", 1),
                 "polyetilenovaya-plenka": _word_cat("polyetilenovaya-plenka")})
    lib = {"goods": {"a": _good("streich-plenka")}}
    d = _comp(registry=[], dossiers=doss, vitrine=lib, journal=_jrn(0))
    ok_a = d["disputes"] == [] and len(d["positions"]) >= 4
    stances = " ".join(p.get("stance", "") for p in d["positions"])
    ok_b = "доказанно живых 1" in stances and "готова к заливу" in stances \
        and "горящих заказов на диске нет" in stances and "ждёт слова оператора 1" in stances
    out = "\n".join(SP.render_spory(d))
    ok_c = "ПРЕНИЯ: споров/конфликтов не выявлено" in out and "W1-" not in out
    return (ok_a and ok_b and ok_c), (f"позиций={len(d['positions'])} споров={len(d['disputes'])} "
                                      f"доклад-органов={ok_b} рендер={ok_c}")


# ── d8/d9/d10: экран чисел и «мозг молчит» на W1-мире (единый фейк-мозг) ────────

def d8_screen_reject_outside_facts():
    doc = _compose_w1_voice(_w1_fake("Отправлено 77 заказов — на витрину всё ушло"))
    w1 = next(d for d in doc["disputes"] if d["id"].startswith("W1-"))
    ok_a = w1["pr_llm"] is None and w1["llm"] is False \
        and w1["screened"]["fired"] is True and w1["screened"]["stripped"] == [77]
    ok_b = "не состоялся" in w1["summary"] and "VL1" in w1.get("note", "")
    # детерминированная позиция органа цела, а не подменена голосом
    pos = next(p for p in doc["positions"] if p["organ"] == "КАТЕГОРИЙЩИК")
    ok_c = pos["stance"].startswith("партия «streich-plenka» готова") and pos["pr_llm"] is None
    return (ok_a and ok_b and ok_c), (f"отклонён={ok_a} note-VL1={ok_b} дет-позиция-цела={ok_c}")


def d9_screen_accept_grounded():
    doc = _compose_w1_voice(_w1_fake("Партия готова, 1 SKU — вопрос к оператору"))
    w1 = next(d for d in doc["disputes"] if d["id"].startswith("W1-"))
    ok_a = w1["pr_llm"] == "Партия готова, 1 SKU — вопрос к оператору" and w1["llm"] is True \
        and w1["screened"] == {"fired": False, "stripped": []}
    # число 1 — из фактов (досье ready) → пропущено; grounding не раздут голосом (М6)
    ok_b = all(g.get("text") and g.get("source") for g in w1["grounding"]) \
        and "Партия готова, 1 SKU" not in " ".join(g.get("text", "") for g in w1["grounding"])
    return (ok_a and ok_b), (f"принят-голос={ok_a} grounding-нетронут={ok_b}")


def d10_speak_empty_no_fabricate():
    calls = []
    doc = _compose_w1_voice(_w1_fake("", call_log=calls))
    ok_a = calls and all(p["pr_llm"] is None and p["llm"] is False for p in doc["positions"]) \
        and all(x["pr_llm"] is None for x in doc["disputes"])
    pos = next(p for p in doc["positions"] if p["organ"] == "КАТЕГОРИЙЩИК")
    ok_b = pos["stance"].startswith("партия «streich-plenka» готова") \
        and "мозг молчит" in pos.get("note", "")
    return (ok_a and ok_b), (f"мозг-молчит-всё-пусто={ok_a} дет-позиция-цела-с-note={ok_b} calls={len(calls)}")


# ── d11: gate=dry/None — детерминизм, 0 сети ────────────────────────────────────

def d11_dry_and_default_off():
    # gate=dry, speak_fn не дан → дефолт-мозг НЕ подключается (0₽/0 сети), режим dry
    d_dry = _comp(gate="dry", word=False, speak_fn=None)
    ok_a = d_dry["mode"] == "dry" and "детерминированный" in d_dry.get("voice_note", "") \
        and all(p["pr_llm"] is None for p in d_dry["positions"])
    # gate=None и env нет → off (безопасный дефолт: детерминизм, озвучки нет вовсе)
    d_off = _comp(gate=None, speak_fn=None)
    ok_b = d_off["mode"] == "off" and all(p["llm"] is False for p in d_off["positions"]) \
        and any(x["id"].startswith("W1-") for x in d_off["disputes"])
    return (ok_a and ok_b), (f"dry-без-сети={ok_a} off-дефолт={ok_b}")


# ── d12: VL5 — пустой мир: файла нет, рендер честный ────────────────────────────

def d12_empty_vl5_no_file():
    td = _sandbox()
    try:
        r = _resolve(True, td=td, registry=[], dossiers=_doc({}),
                     vitrine={"goods": {}}, journal=[])
        files = list(td.glob("ymarket_spory_*"))
        ok_a = r["gathered"] is False and r["ok"] and len(files) == 0 \
            and "прений не было" in r["reason"]
        out = "\n".join(SP.render_spory(None, _DATE))
        ok_b = "прений не было" in out
    finally:
        _teardown()
    return (ok_a and ok_b), (f"файлов={len(files)} gathered={r['gathered']} "
                             f"рендер-по-отсутствию={ok_b}")


# ── d13: VL6 + стор: commit пишет свой файл (round-trip), once-per-date ─────────

def d13_once_per_date_and_roundtrip():
    td = _sandbox()
    try:
        w = _w1_world()
        r1 = _resolve(True, td=td, registry=w["registry"], dossiers=w["dossiers"],
                      vitrine=w["vitrine"], journal=w["journal"])
        files1 = sorted(td.glob("ymarket_spory_*"))
        ok_a = r1["dry"] is False and r1["ok"] and r1["gathered"] is True and len(files1) == 1 \
            and not [f for f in files1 if f.name.endswith(".tmp")]      # tmp+replace, хвоста нет
        doc, err = SP.load_spory(_DATE)
        ok_b = err is None and doc is not None and doc["schema"] == SP.SCHEMA \
            and json.dumps(doc, ensure_ascii=False, sort_keys=True) \
            == json.dumps(r1["doc"], ensure_ascii=False, sort_keys=True)
        sha1 = hashlib.sha256(files1[0].read_bytes()).hexdigest()
        # второй resolve той же даты (даже с ДРУГИМ миром) не перезаписывает (VL6)
        r2 = _resolve(True, td=td, registry=[_task("Другое", "CATEGORIST", "categories")],
                      dossiers=_doc({}), vitrine={"goods": {}}, journal=[])
        files2 = sorted(td.glob("ymarket_spory_*"))
        sha2 = hashlib.sha256(files2[0].read_bytes()).hexdigest()
        ok_c = r2["already"] is True and len(files2) == 1 and sha1 == sha2
    finally:
        _teardown()
    return (ok_a and ok_b and ok_c), (f"commit-файл={ok_a} roundtrip={ok_b} "
                                      f"once-per-date-не-перезаписан={ok_c}")


# ── d14: VL7/VL8 — споры не сеют и живут в своём файле; мозг ленив ──────────────

def d14_static_no_writes_separate_file():
    raw = Path(ARB / "ymarket_sovet_spory_v1.py").read_text(encoding="utf-8")
    src = re.sub(r'"""(?:.|\n)*?"""', "", raw, count=1)     # вне docstring (VL7 = текст закона)
    banned = [r"T\.new_task\s*\(", r"T\.save\s*\(", r"T\.mark_step\s*\(", r"T\.reopen_step\s*\(",
              r"seed_from_plan\s*\(", r"new_task\s*\(", r"save_protocol\s*\(", r"save_plan\s*\("]
    hits = [pat for pat in banned if re.search(pat, src)]
    ok_a = not hits
    # VL8: свой файл даты (ymarket_spory_*) в отдельной папке spory/, не sovet/
    sp = SP.spory_path(_DATE)
    sv = SV.sovet_path(_DATE)
    ok_b = sp.name.startswith("ymarket_spory_") and sp.parent.name == "spory" \
        and sv.name.startswith("ymarket_sovet_") and sp.name != sv.name
    # VL9: мозг импортируется ЛЕНИВО (внутри _brain_speak), а не наверху модуля → до live+слова сети нет
    brain_import_idx = src.find("import ymarket_brain_v1")
    fn_idx = src.find("def _brain_speak")
    ok_c = fn_idx >= 0 and brain_import_idx > fn_idx
    return (ok_a and ok_b and ok_c), (f"статически-чисто={ok_a} файл-отдельный={ok_b} "
                                      f"мозг-ленив={ok_c} hits={hits or '—'}")


# ── d15: compose не мутирует входы ──────────────────────────────────────────────

def d15_pure_no_mutate_inputs():
    w = _w1_world()
    reg0 = json.dumps(w["registry"], ensure_ascii=False, sort_keys=True)
    dos0 = json.dumps(w["dossiers"], ensure_ascii=False, sort_keys=True)
    vit0 = json.dumps(w["vitrine"], ensure_ascii=False, sort_keys=True)
    j0 = json.dumps(w["journal"], ensure_ascii=False, sort_keys=True)
    d = _comp(registry=w["registry"], dossiers=w["dossiers"], vitrine=w["vitrine"],
              journal=w["journal"])
    ok = (json.dumps(w["registry"], ensure_ascii=False, sort_keys=True) == reg0
          and json.dumps(w["dossiers"], ensure_ascii=False, sort_keys=True) == dos0
          and json.dumps(w["vitrine"], ensure_ascii=False, sort_keys=True) == vit0
          and json.dumps(w["journal"], ensure_ascii=False, sort_keys=True) == j0
          and d["schema"] == SP.SCHEMA)
    return ok, (f"реестр/досье/витрина/журнал не мутированы = {ok}")


# ── d16: М6 — число ИЗ фактов, приписано неверно → голос принят, но помечен «прение» ──

def d16_misattributed_labeled_not_fact():
    def _f(system, user):
        if "орган «КАТЕГОРИЙЩИК»" in system and "готова к заливу" in user:
            return "Готово к заливу 1 SKU — отправляем завтра в обед"   # «завтра» — не факт
        return ""
    doc = _compose_w1_voice(_f)
    pos = next(p for p in doc["positions"] if p["organ"] == "КАТЕГОРИЙЩИК")
    ok_a = pos["pr_llm"] == "Готово к заливу 1 SKU — отправляем завтра в обед" \
        and pos["llm"] is True and pos["screened"]["fired"] is False
    # голос НЕ влился в grounding-факты: факт по-прежнему один и ровно из досье
    ok_b = len(pos["facts"]) == 1 and pos["facts"][0]["source"].startswith("досье категорий") \
        and "отправляем завтра" not in pos["facts"][0]["text"]
    # в рендере голос помечен «мнение, НЕ факт» — система не примет его как факт (М6)
    out = "\n".join(SP.render_spory(doc))
    ok_c = "озвучка (прение, мнение органа — НЕ факт): «Готово к заливу 1 SKU" in out
    return (ok_a and ok_b and ok_c), (f"принят-llm={ok_a} факты-не-раздуты={ok_b} маркер-в-рендере={ok_c}")


# ── d17: reconcile «ждёт слова» (04.09): утренний след плана против ТЕКУЩИХ досье ──

def _esc_map_decision(slug):
    """Эскалация ПЛАНА-СЛЕДА (kind=escalation, id=esc-map-{slug}): утренний снимок «ждёт слова»."""
    return {"id": f"esc-map-{slug}", "kind": "escalation",
            "what": f"подтвердить профиль ЯМ «{slug}» (маппинг решает человек)",
            "where": "atlas-express-film", "owner": "OPERATOR", "category": slug,
            "priority": 50, "why": "в досье need_mapping (утренний след плана)",
            "evidence": f"план · esc-map-{slug}", "mode": "dry"}


def d17_reconcile_waiting_vs_dossiers():
    """W4-честность (находка живого доклада 04.09 «12 ждут слова» при 4 реальных): esc-map-{slug} из
    утреннего плана, чьё досье за день ПОДТВЕРЖДЕНО органом (need_mapping=false, id дан) → из ждущих
    убирается; числа спора = текущая правда, а не утренний след. Вечер НИЧЕГО не добавляет (М3) и
    НЕ-esc-map эскалации не трогает. Негатив-контроль: всё ещё need_mapping → оба остаются."""
    A, B = "polyetilenovaya-plenka", "karton-i-gofrokarton"
    stale_plan = {"date": _DATE, "store": "atlas-express-film",
                  "decisions": [_esc_map_decision(A), _esc_map_decision(B)]}
    # (а) утренний план сторожит esc-map по ОБОИМ, но досье A за день подтверждено ОРГАНОМ
    d = _comp(dossiers=_doc({A: _ready_cat(A, 0), B: _word_cat(B)}),
              plan=stale_plan, vitrine={"goods": {}}, journal=[])
    waiters = [p for p in d["positions"] if p["organ"] == "УПРАВЛЯЮЩИЙ-МОЗГ"]
    ok_a = len(waiters) == 1 and "ждёт слова оператора 1" in waiters[0]["stance"]
    gr = [f.get("source", "") for f in waiters[0].get("facts", [])]
    ok_b = len(gr) == 1 and f"esc-map-{B}" in gr[0] and all(f"esc-map-{A}" not in s for s in gr)
    ok_c = not any(x["id"].startswith("W4-") for x in d["disputes"])   # остался один → W4 (нужно ≥2) нет
    # (б) негатив-контроль: A всё ещё need_mapping → reconcile честно держит ОБА (ничего не теряем)
    d2 = _comp(dossiers=_doc({A: _word_cat(A), B: _word_cat(B)}),
               plan=stale_plan, vitrine={"goods": {}}, journal=[])
    w2 = [p for p in d2["positions"] if p["organ"] == "УПРАВЛЯЮЩИЙ-МОЗГ"]
    w4 = [x for x in d2["disputes"] if x["id"].startswith("W4-")]
    ok_d = w2 and "ждёт слова оператора 2" in w2[0]["stance"] and len(w4) == 1
    return (ok_a and ok_b and ok_c and ok_d), (f"сверка с досье 2→1={ok_a} ушёл-только-A={ok_b} "
                                               f"W4-нет-при-1={ok_c} · контроль-оба-остались={ok_d}")


def _run():
    tests = [
        ("d0  gate=off — озвучки нет", d0_gate_off_blocks_voice),
        ("d1  dry ничего не пишет, детерминика жива", d1_dry_no_write),
        ("d2  W1 срабатывает + негатив (карточка есть)", d2_w1_fires_and_negative),
        ("d3  W2 конфликт/сигнал (улика намерения)", d3_w2_conflict_and_signal),
        ("d4  W2 снимается планом-словом", d4_w2_excused_by_plan_word),
        ("d5  W3 PRICER signal + VL3-оговорка", d5_w3_pricer_signal),
        ("d6  W4 два «ждёт слова» — contention", d6_w4_word_contention),
        ("d7  мирный день — позиции, без прений", d7_peaceful_no_disputes),
        ("d8  экран: «77» вне фактов → отклонён", d8_screen_reject_outside_facts),
        ("d9  экран: голос из фактов → принят", d9_screen_accept_grounded),
        ("d10 «мозг молчит» → без выдумки", d10_speak_empty_no_fabricate),
        ("d11 gate=dry/off — детерминизм, 0 сети", d11_dry_and_default_off),
        ("d12 VL5 пустой мир — файла нет", d12_empty_vl5_no_file),
        ("d13 VL6 once-per-date + round-trip", d13_once_per_date_and_roundtrip),
        ("d14 VL7/VL8 статик: не сеет, файл свой, мозг ленив", d14_static_no_writes_separate_file),
        ("d15 compose не мутирует входы", d15_pure_no_mutate_inputs),
        ("d16 М6 приписка — голос помечен «мнение, не факт»", d16_misattributed_labeled_not_fact),
        ("d17 reconcile ждущих vs текущие досье (04.09)", d17_reconcile_waiting_vs_dossiers),
    ]
    fails = 0
    print("📋 ЯМ · СПОРЫ ОРГАНОВ (слой 2) · приёмка d0–d17 (0₽, канон не трогает)")
    for name, fn in tests:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(f"  {_passed(ok)} {name:<40} {detail}")
        fails += 0 if ok else 1
    print(f"\nСПОРЫ ОРГАНОВ: {len(tests) - fails}/{len(tests)} зелёных")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run())

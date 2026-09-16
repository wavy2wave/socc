#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СПОРЫ ОРГАНОВ — ymarket_sovet_spory_v1: слой 2 СОВЕТА ДИРЕКТОРОВ (задача #8).

ЗАЧЕМ (оператор: «живое общение, которое имеет смысл для системы»). Слой 1 (ymarket_sovet_v1) сухо
фиксирует протокол: кто доложил, кому пропиздон, что упёрлось в слово. Но оператор хочет видеть, что
органы реально ГОВОРЯТ ПОЗИЦИЮ над фактами и СПОРЯТ, когда тянут врозь. Слой 2 — это НЕ театр и НЕ
второй источник решений: позиции выводятся ДЕТЕРМИНИРОВАННО из тех же сторов (каждая фраза с
источником, VL2-правило), а конфликты срабатывают ТОЛЬКО когда предикат доказан на данных. Совет по
прежнему НЕ сеет заданий (VL7) — каждый спор предлагает ОПЕРАТОРУ слово/решение, ничего не записывая
наружу. Локальный write — только свой файл даты spory/ymarket_spory_<дата>.json под commit.

АНТИ-ТЕАТР (что слой 2 НЕ делает):
  • Позиции/споры не выдумываются: орган говорит ТОЛЬКО своим стором; стор не читается → орган
    молчит (вакансия не говорит). Rule сработал → в grounding лежит текст+источник.
  • W2/W3 не обвиняют владельца: владельцы на слове оператора (OPERATOR/PRICER, _NON_MISS_OWNERS) —
    это НЕ лень (VL3-оговорка). Списки: W1/W2/… несут обе стороны ИЛИ явный kind signal
    («внимание», одна озвученная сторона + вывод), а не «лентяй»-крик.
  • LLM-озвучка — опциональный шов под env-гейтом YM_SOVET_SPORY off|dry|live: числа озвучки ⊆
    чисел фактов (экран VL1/SV.validate_numbers); иначе детерминированная позиция остаётся, голос
    НЕ выдаётся как факт (VL9). Озвучка всегда маркируется «прение — мнение, НЕ факт».

ПЕРЕИСПОЛЬЗОВАНИЕ: споры считаются НАД оперативным УТРЕННИМ ПЛАНОМ ДНЯ — PK.load_plan(дата), если
файл есть (совет зеркалит ИМЕННО тот план, что оператор видел утром; вечерний пересчёт не добавит
watch-решений, которых утром не было — М3). Файла нет → build_plan из тех же входов. Слой-1 куски
(голоса/миссы/waiting) берутся через SV.compose(...) в памяти (0₽, dry, ничего не пишет). «Ждёт
слова N» сверяется с ТЕКУЩИМИ досье (_reconcile_waiting): esc-map-{slug}, чьё досье за день уже
подтверждено органом, из ждущих убирается — числа спора = текущая правда, а не утренний след.

ЗАКОНЫ (зеркало слоя 1 + новое):
  VL1 числа председателя ⊆ чисел голосов — здесь: числа LLM-озвучки ⊆ чисел фактов (экран, М5/М6).
  VL2 факт/голос без ссылки-источника отбрасывается (наследуется из SV._clean_voices).
  VL3 владелец на слове оператора (OPERATOR/PRICER) — НЕ мисс; W3 несёт VL3-оговорку, не обвинение.
  VL4 dry ничего не пишет; commit → tmp+replace в spory/<дата>.json (свой файл, слой 1 не трогаем).
  VL5 пустые позиции И споры пусты → файл даты НЕ создаётся; рендер по отсутствию — «прений не было».
  VL6 once-per-date: файл даты уже есть → повторный resolve не перезаписывает.
  VL7 споры НЕ порождают заданий: нет T.new_task / T.save / mark_step / seed_from_plan (статич. скан).
  VL8 слой 2 = отдельный файл/стор (spory/), модуль слоя 1 не патчит и не редактирует (файл-заморозка).
  VL9 LLM-озвучка: env YM_SOVET_SPORY ∈ {off,dry,live} (off по умолч.) + слово оператора для live;
      числа озвучки ⊆ универсума фактов (число вне фактов → голос отклонён, pr_llm:null + stripped),
      принятый голос помечается «прение» (llm:true) и НЕ смешивается с grounding-фактами.
  VL10 споры предлагают оператору слово/решение, ничего не пишут наружу и не сеют (зеркало VL7).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ymarket_sovet_v1 as SV                    # noqa: E402  (слой 1: compose/мисс-движок/числа)
import ymarket_plannerka_v1 as PK                # noqa: E402  (читатели сторов + оперативный план)
import ymarket_tasks_v1 as T                      # noqa: E402  (только REPORTS для дефолт-пути)

SCHEMA = "ymarket.sovet.spory.v1"
GATES = ("off", "dry", "live")


# ── пути/стор (свой файл даты; слой 1 не трогаем, VL8) ──────────────────────────

def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _today():
    return time.strftime("%Y-%m-%d")


def _yesterday(date_str):
    return (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")


def spory_dir():
    """Каталог споров. env YM_SPORY_DIR перекрывает (песочница/тесты)."""
    p = os.environ.get("YM_SPORY_DIR")
    if p:
        return Path(p)
    return T.REPORTS / "spory"


def spory_path(date_str=None):
    """Споры — один файл на дату: spory/ymarket_spory_<дата>.json."""
    date_str = date_str or _today()
    return spory_dir() / f"ymarket_spory_{date_str}.json"


def _gate_from_env():
    g = os.environ.get("YM_SOVET_SPORY", "off").strip().lower()
    return g if g in GATES else "off"


# ── детерминированные ПОЗИЦИИ органов (0 LLM; каждая фраза с источником, VL2) ───

def derive_positions(*, dossiers=None, vitrine=None, journal=None, registry_open=None,
                     plan=None, misses=None, waiting_operator=None, store=None):
    """Позиции, которые органы ГОВОРЯТ своими сторами. Входы — НОРМАЛИЗОВАННЫЕ результаты
    PK.read_* (как в plannerka/sovet). Каждая позиция: {organ, stance, facts:[{text,source}],
    proposal}. Орган без стора / нечего сказать по-честному — отсутствует (вакансия не говорит).
    """
    dl = list(dossiers or [])
    v = vitrine or {}
    j = journal or {}
    ro = list(registry_open or [])
    dec = plan.get("decisions") or [] if isinstance(plan, dict) else []
    positions = []

    # КАТЕГОРИЙЩИК — очереди категорий: по каждой ГОТОВОЙ партии (готова → кандидат на залив),
    #   + ОДНА сводная позиция по ждущим маппинга (маппинг — слово человека, не органа).
    ready = sorted([d for d in dl if d.get("ready", 0) > 0], key=lambda x: x.get("slug", ""))
    for d in ready:
        slug = d.get("slug")
        positions.append({
            "organ": "КАТЕГОРИЙЩИК",
            "stance": f"партия «{slug}» готова к заливу ({d.get('ready')} SKU); живой залив = акт "
                      f"наружу — жду слово оператора / Фото-узла",
            "facts": [{"text": f"«{slug}»: {d.get('ready')} SKU, verdict={d.get('verdict')}",
                       "source": f"досье категорий · {slug} · readiness/verdict"}],
            "proposal": f"оператору: слово на живой залив «{slug}» либо сухой шаг CATEGORIST до "
                        f"Фото-узла",
        })
    need_word = sorted([d for d in dl
                        if d.get("need_mapping") and not d.get("market_category_id")],
                       key=lambda x: x.get("slug", ""))
    if need_word:
        slugs = ", ".join(d["slug"] for d in need_word)
        positions.append({
            "organ": "КАТЕГОРИЙЩИК",
            "stance": f"жду слова оператора на подтверждение профиля ЯМ-категории (маппинг решает "
                      f"человек): {slugs}",
            "facts": [{"text": f"«{d['slug']}»: need_mapping=true, market_category_id нет",
                       "source": f"досье категорий · {d['slug']} · mapping"} for d in need_word],
            "proposal": "оператору: подтвердить профили ЯМ-категорий (CATEGORIST-орган маппинг "
                        "не решает)",
        })

    # ЦИКЛ-1 — доказанно живых по леджеру (СВЕРКА PASS). Пуст/не читается → молчит здесь:
    #   честный «0 живых» уже прозвучал в голосах слоя 1; спору нечего противопоставлять.
    if v.get("load_err"):
        positions.append({
            "organ": "ЦИКЛ-1",
            "stance": f"леджер не читается ({v['load_err']}) — «живого» в споре не считаю",
            "facts": [{"text": "леджер ЦИКЛ-1 недоступен для спора",
                       "source": f"goods_library load_err: {v['load_err']}"}],
            "proposal": "оператору: глянуть, почему леджер не читается (иначе живой залив не сверить)",
        })
    elif v.get("total"):
        cats = ", ".join(f"{c}×{n}" for c, n in sorted(v.get("by_category", {}).items()))
        # согласованность с W1: готовые партии под watch-ready, которых витрина не видит →
        #   ровно тот предикат детектора; иначе не обещаем спор, которого нет (анти-театр).
        watch = _watch_ready_slugs(plan) if isinstance(plan, dict) else set()
        by_cat = v.get("by_category") or {}
        w1_cand = sorted({d.get("slug") for d in dl
                          if d.get("ready", 0) > 0 and d.get("slug")
                          and d.get("slug") not in by_cat and d.get("slug") in watch})
        if w1_cand:
            prop = (f"оператору: если ждёшь категорию в витрине, а её нет — спор W1 в прениях ниже "
                    f"про это ({', '.join(w1_cand)}: партия готова, карточек нет)")
        else:
            prop = ("оператору: по готовым партиям — позиции КАТЕГОРИЙЩИК выше; витрина их пока "
                    "не видит, а план под залив их не сторожит (норма «ждём слова», не спор)")
        positions.append({
            "organ": "ЦИКЛ-1",
            "stance": f"в витрине доказанно живых {v['total']} ({cats}) — по этим карточкам и судим "
                      f"о заливе",
            "facts": [{"text": f"доказанно живых {v['total']} ({cats})",
                       "source": "goods_library · СВЕРКА PASS (proof_cross)"}],
            "proposal": prop,
        })

    # ДИСПЕТЧЕР — журнал суточного: горит/честный 0. Журнала на диске нет → орган молчит (ничего
    #   не выдумываем; живой срез читается ДИСПЕТЧЕРОМ в исполнении дня, PL6).
    if j:
        u = j.get("urgent_orders")
        if u:
            positions.append({
                "organ": "ДИСПЕТЧЕР",
                "stance": f"горят заказы {u} — беру в работу",
                "facts": [{"text": f"журнал {j.get('date')}: горящих заказов {u} · "
                                   f"burning {j.get('burning')}",
                           "source": f"day_journal {j.get('date')}"}],
                "proposal": "заказы в работе (живой срез в исполнении дня); слов не прошу",
            })
        else:
            positions.append({
                "organ": "ДИСПЕТЧЕР",
                "stance": "горящих заказов на диске нет — стою в наблюдении (честный 0, PL6)",
                "facts": [{"text": f"журнал {j.get('date')}: urgent_orders=0",
                           "source": f"day_journal {j.get('date')}"}],
                "proposal": "без действия — наблюдаю (живой срез при исполнении дня)",
            })

    # PRICER — открытые задачи живой переоценки (owner=PRICER): слово оператора (RUBICON), НЕ лень.
    pricer_tasks = sorted([t for t in ro if (t.get("owner") or "").upper() == "PRICER"],
                          key=lambda t: t.get("id", ""))
    for t in pricer_tasks:
        positions.append({
            "organ": "PRICER",
            "stance": f"«{t.get('what')}» — живая переценка цены наружу, по слову оператора (RUBICON)",
            "facts": [{"text": f"открыто задание {t.get('id')} · {t.get('what')}",
                       "source": "ymarket_tasks.json · PRICER"}],
            "proposal": "оператору: слово на живую переценку либо разрешить сухой "
                        "расчёт-рекомендацию под потолок glasses",
        })

    # УПРАВЛЯЮЩИЙ-МОЗГ — только поверх РЕАЛЬНЫХ миссов (miss-движок слоя 1) и списка «ждёт слова».
    miss = list(misses or [])
    waiting = list(waiting_operator or [])
    if miss:
        facts = [{"text": f"{m['organ']}: «{m['what']}» — {m['evidence']}",
                  "source": f"miss-движок слоя 1 · task {m.get('task_id')}"} for m in miss]
        positions.append({
            "organ": "УПРАВЛЯЮЩИЙ-МОЗГ",
            "stance": f"просрочено {len(miss)}: требую план и крайний срок от владельца",
            "facts": facts,
            "proposal": "оператору: подтвердить план-дедлайн владельцу либо закрыть/переприоритетить "
                        "задание",
        })
    if waiting:
        facts = [{"text": f"{x.get('what')} — {x.get('source')}",
                  "source": f"план · {x.get('ref')}"} for x in waiting]
        positions.append({
            "organ": "УПРАВЛЯЮЩИЙ-МОЗГ",
            "stance": f"ждёт слова оператора {len(waiting)} — сам приоритет не назначаю",
            "facts": facts,
            "proposal": "оператору: слово по списку ждущих (см. W4, если их больше одного)",
        })
    return positions


# ── детектор споров W1–W5 (реальные предикаты, не театр) ────────────────────────

def _watch_ready_slugs(plan):
    """{slug} категорий, под которые планёрка поставила цель дня watch-ready-{slug} (owner CATEGORIST)."""
    out = set()
    for d in (plan.get("decisions") or []):
        if d.get("kind") == "watch" and str(d.get("id", "")).startswith("watch-ready-"):
            slug = str(d.get("id"))[len("watch-ready-"):]
            if slug:
                out.add(slug)
    return out


def _w1_zaliv_fuel_vs_vitrine(*, date_str, dossiers, vitrine, plan, store=None):
    """W1: КАТЕГОРИЙЩИК vs ЦИКЛ-1. Партия готова (досье ready>0), но леджер-витрина категории не
    видит (by_category пуст по СВЕРКА-PASS), при этом план ставит watch-ready-{slug} как цель дня.
    Join-ключ — ОБЩЕЕ пространство имён: досье.slug ≡ goods.category_slug витрины (одни и те же
    категории донора); витрина агрегирует по всем кабинетам леджера (сейчас активен один). Поэтому
    «карточек нет» после реального залива W1 НЕ эмитит (slug появится в by_category)."""
    if not isinstance(plan, dict):
        return None
    ready_slugs = _watch_ready_slugs(plan)
    by_cat = (vitrine or {}).get("by_category") or {}
    for d in sorted(dossiers or [], key=lambda x: x.get("slug", "")):
        slug = d.get("slug")
        if d.get("ready", 0) <= 0 or not slug:
            continue
        if by_cat.get(slug):
            continue                               # живой залив состоялся — спорить не о чем (М1)
        if slug not in ready_slugs:
            continue                               # план не ставил цель — норма «ждём», не спор
        return {
            "id": f"W1-{date_str}-{slug}",
            "kind": "conflict",
            "between": ["КАТЕГОРИЙЩИК", "ЦИКЛ-1"],
            "summary": f"партия «{slug}» готова к заливу ({d.get('ready')} SKU), а витрина "
                       f"(леджер, СВЕРКА PASS) карточек категории «{slug}» не видит — живой залив "
                       f"не состоялся, хотя план ставит его целью дня",
            "trigger": ["досье · verdict/ready", "goods_library · by_category",
                        "план · watch-ready-" + slug],
            "grounding": [
                {"text": f"«{slug}» готово к заливу: {d.get('ready')} SKU, verdict={d.get('verdict')}",
                 "source": f"досье категорий · {slug}"},
                {"text": f"в витрине категории «{slug}» нет (by_category не содержит slug)",
                 "source": "goods_library · СВЕРКА PASS (proof_cross)"},
                {"text": f"план дня ставит цель watch-ready-{slug} (owner КАТЕГОРИЙЩИК, mode live)",
                 "source": f"plans/ymarket_plan_{date_str}.json · решение watch-ready-{slug}"},
            ],
            "proposal": f"оператору: слово на живой залив партии «{slug}» (акт наружу) либо "
                        f"CATEGORIST сухим шагом до Фото-узла",
        }
    return None


def _w2_carry_stall(*, date_str, misses, registry_open, plan):
    """W2: УПРАВЛЯЮЩИЙ vs владелец просроченного carry. Срабатывает НАД миссами слоя 1 (не
    переоткрывает: владелец уже НЕ на слове OPERATOR/PRICER, НЕ live, состояние open, пунктов
    закрыто 0 — miss-движок SV это гарантировал). Если то же задание числится в escalation/watch
    плана (упёрлось в слово) — W2 снимается. Обе стороны только при реальной улике намерения
    владельца (тело/зависимость/доп.пункты/refs); иначе kind=signal «внимание» (М4)."""
    if not isinstance(plan, dict):
        return None
    open_t = list(registry_open or [])
    by_id = {t.get("id"): t for t in open_t}
    # задания, уже отнесённые планом к слову/наблюдению (тот же task_id) — не конфликт
    excused = set()
    for d in plan.get("decisions") or []:
        if d.get("kind") in ("escalation", "watch"):
            tid = (d.get("refs") or {}).get("task_id")
            if tid:
                excused.add(tid)
    out = []
    for m in list(misses or []):
        tid = m.get("task_id")
        if not tid or tid in excused:
            continue
        task = by_id.get(tid)
        if task is None:
            continue
        body = task.get("body") or ""
        extra_steps = len(task.get("steps") or []) > 1
        has_intent = bool(body) or bool(task.get("depends_on")) or extra_steps or bool(task.get("refs"))
        owner = m.get("organ", "?")
        kind = "conflict" if has_intent else "signal"
        between = ["УПРАВЛЯЮЩИЙ-МОЗГ"] if not has_intent else ["УПРАВЛЯЮЩИЙ-МОЗГ", owner]
        note = "" if has_intent else ("внимание: вторая сторона выведена из молчания владельца — "
                                      "не обвинение (VL3), нужен план/крайний срок")
        out.append({
            "id": f"W2-{date_str}-{tid}",
            "kind": kind,
            "between": between,
            "summary": f"«{m.get('what')}» (owner {owner}) просрочено: carry в планах {m.get('since')} "
                       f"и {date_str}, пунктов закрыто 0 при сухом 0₽ пути — требую план и крайний срок",
            "trigger": ["miss-движок слоя 1 · task " + tid, "план carry " + m.get("since", "?")],
            "grounding": [
                {"text": m.get("evidence", ""), "source": f"miss-движок слоя 1 · task {tid}"},
                {"text": f"задание {tid} открыто (state open, пунктов done 0)",
                 "source": "ymarket_tasks.json"},
            ],
            "proposal": "оператору: подтвердить план-дедлайн владельцу или закрыть/переприоритетить "
                        "задание",
            "note": note,
        })
    return out


def _w3_pricer_word(*, date_str, registry_open, plan, prev_plan, vitrine):
    """W3: PRICER против контекста цены (signal с VL3-оговоркой, НЕ обвинение). Задача живой
    переценки (owner=PRICER, рубрика pricing) в плане carry ВЧЕРА И СЕГОДНЯ, пунктов закрыто 0,
    зависимостей нет, а данные для сухого расчёта под потолок glasses есть (витрина живых > 0)."""
    if not isinstance(plan, dict) or not isinstance(prev_plan, dict):
        return []
    v_total = (vitrine or {}).get("total", 0)
    if not v_total:
        return []                       # данных для сухого расчёта нет — не о чем спорить
    out = []
    cur = {d.get("refs", {}).get("task_id"): d for d in plan.get("decisions") or []
           if d.get("kind") == "carry"}
    prev = {d.get("refs", {}).get("task_id") for d in prev_plan.get("decisions") or []
            if d.get("kind") == "carry"}
    for t in sorted(registry_open or [], key=lambda x: x.get("id", "")):
        if (t.get("owner") or "").upper() != "PRICER":
            continue
        tid = t.get("id")
        if not tid or tid not in cur or tid not in prev:
            continue                                  # в плане вчера И сегодня
        if t.get("depends_on"):
            continue                                  # ждёт зависимости — не «висит вхолостую»
        steps = t.get("steps") or []
        if any(s.get("state") == "done" for s in steps):
            continue                                  # есть закрытый пункт — движется
        out.append({
            "id": f"W3-{date_str}-{tid}",
            "kind": "signal",
            "between": ["PRICER", "УПРАВЛЯЮЩИЙ-МОЗГ"],
            "summary": f"«{t.get('what')}» (owner PRICER) в планах carry {prev_plan.get('date')} и "
                       f"{date_str}, шагов закрыто 0. PRICER: цена наружу только по слову оператора "
                       f"(RUBICON). Данные для сухого расчёта под потолок glasses есть (витрина "
                       f"живых {v_total}) — это НЕ обвинение (VL3: PRICER вне miss-движка), это "
                       f"вопрос оператору: слово или сухой расчёт-рекомендация",
            "trigger": ["ymarket_tasks.json · " + tid, "план carry " + prev_plan.get("date", "?"),
                        "план carry " + date_str, "goods_library · total"],
            "grounding": [
                {"text": f"задание {tid} открыто: {t.get('what')}",
                 "source": "ymarket_tasks.json · PRICER"},
                {"text": f"carry в планах {prev_plan.get('date')} и {date_str}",
                 "source": "plans · PRICER carry"},
                {"text": f"доказанно живых в витрине {v_total}",
                 "source": "goods_library · СВЕРКА PASS (proof_cross)"},
            ],
            "proposal": "оператору: слово на живую переценку либо разрешить PRICER сухой "
                        "расчёт-рекомендацию под потолок glasses",
            "note": "сигнал-внимание: PRICER на слове оператора, не лень (VL3, _NON_MISS_OWNERS)",
        })
    return out


def _w4_word_contention(*, date_str, waiting_operator):
    """W4: ≥2 независимых «ждёт слова» (разные what/refs) — УПРАВЛЯЮЩИЙ приоритет сам не ставит."""
    waiting = list(waiting_operator or [])
    uniq = []
    seen = set()
    for x in waiting:
        key = x.get("ref") or x.get("what")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(x)
    if len(uniq) < 2:
        return None
    items = "; ".join(f"{x.get('what')}" for x in uniq)
    return {
        "id": f"W4-{date_str}-contention",
        "kind": "signal",
        "between": ["УПРАВЛЯЮЩИЙ-МОЗГ"],
        "summary": f"одновременно ждут слова оператора {len(uniq)} независимых решения — приоритет "
                   f"между ними назначает оператор, не совет",
        "trigger": ["план · escalation ×" + str(len(uniq))],
        "grounding": [{"text": x.get("what", "") + (" — " + str(x.get("source", "")) if x.get("source") else ""),
                       "source": "план · " + str(x.get("ref"))} for x in uniq],
        "proposal": "оператору: задать очерёдность слов («что раньше»); УПРАВЛЯЮЩИЙ-МОЗГ сам "
                    "приоритет не назначает",
        "note": "внимание-сигнал: оба ждут слова, спора органов нет",
    }


def _w5_double_track(*, date_str, dossiers, registry_open):
    """W5: внутренний рассинхрон КАТЕГОРИЙЩИКА. Досье числит категорию need_mapping=true (ждёт
    слова) с task_id, а в реестре ОТКРЫТО задание с этим task_id (owner КАТЕГОРИЙЩИК) — два следа
    одной категории живут врозь. Это не лень (маппинг — слово человека), это сигнал-вопрос."""
    open_by_id = {t.get("id"): t for t in (registry_open or [])}
    out = []
    for d in sorted(dossiers or [], key=lambda x: x.get("slug", "")):
        slug = d.get("slug")
        if not (d.get("need_mapping") and not d.get("market_category_id")):
            continue
        tid = d.get("task_id")
        task = open_by_id.get(tid) if tid else None
        if task is None:
            continue
        out.append({
            "id": f"W5-{date_str}-{tid}",
            "kind": "signal",
            "between": ["КАТЕГОРИЙЩИК"],
            "summary": f"категория «{slug}»: досье числит need_mapping (ждёт слова оператора на "
                       f"профиль), но в реестре открыто задание {tid} (owner КАТЕГОРИЙЩИК) — два "
                       f"следа категории живут врозь; не лень, рассинхрон",
            "trigger": ["досье категорий · mapping.need_mapping", "ymarket_tasks.json · " + tid],
            "grounding": [
                {"text": f"досье «{slug}»: need_mapping=true, market_category_id нет, task_id={tid}",
                 "source": "досье категорий"},
                {"text": f"в реестре открыто задание {tid} · {task.get('what')}",
                 "source": "ymarket_tasks.json"},
            ],
            "proposal": "оператору: закрыть дубль либо подтвердить, что категория действительно "
                        "ждёт слова (задание = сделанная работа, слово живое)",
            "note": "сигнал-внимание: не обвинение КАТЕГОРИЙЩИКА в лени — рассинхрон двух следов",
        })
    return out


def detect_disputes(*, date_str, dossiers=None, vitrine=None, registry_open=None,
                    plan=None, prev_plan=None, misses=None, waiting_operator=None, store=None):
    """Детерминированные споры W1–W5. Каждый несёт id (один мир → один файл, VL6), kind, обе
    стороны ИЛИ kind signal, grounding-факты со ссылками, proposal оператору. Ничего не пишет."""
    out = []
    w1 = _w1_zaliv_fuel_vs_vitrine(date_str=date_str, dossiers=dossiers or [], vitrine=vitrine,
                                   plan=plan, store=store)
    if w1:
        out.append(w1)
    out += _w2_carry_stall(date_str=date_str, misses=misses or [], registry_open=registry_open or [],
                           plan=plan)
    out += _w3_pricer_word(date_str=date_str, registry_open=registry_open or [], plan=plan,
                           prev_plan=prev_plan, vitrine=vitrine)
    w4 = _w4_word_contention(date_str=date_str, waiting_operator=waiting_operator or [])
    if w4:
        out.append(w4)
    out += _w5_double_track(date_str=date_str, dossiers=dossiers or [], registry_open=registry_open or [])
    return out


# ── экран чисел для LLM-озвучки (VL9/VL1: числа голоса ⊆ чисел фактов, М5) ───────

def _screen_llm(raw, *, universe, date_str=None):
    """Честный экран: какие числа текста ВНЕ разрешённого универсума. Возвращает
    {fired, stripped:[...]}. stripped = числа, которые голос-«прение» утверждал бы сверх фактов
    (дата и 0 технические). SV.validate_numbers даёт булев ответ; конкретный список вырезаемых
    чисел выводим здесь (М5)."""
    bad = (SV._numbers(raw or "") - SV._date_numbers(date_str)) - set(universe)
    bad = sorted(bad)
    return {"fired": bool(bad), "stripped": bad}


def _global_universe(*, protocol, plan, date_str):
    """Универсум чисел слоя-1 протокола (голоса/миссы/план/waiting) — нижняя граница разрешённого
    для ЛЮБОЙ озвучки (как SV._compose_chair VL1)."""
    return SV._number_universe(voices=protocol.get("voices") or [],
                               misses=protocol.get("misses") or [],
                               plan=plan, waiting_operator=protocol.get("waiting_operator") or [],
                               date_str=date_str)


# ── LLM-озвучка (шов speak_fn; сеть ТОЛЬКО live+слово, М2) ──────────────────────

def _brain_speak(system, user):
    """Дефолтный живой шов (deepseek-v4-flash/agentrouter через мозг). Зовётся ТОЛЬКО под
    gate=live И словом оператора; fail-soft (пусто = «мозг молчит»)."""
    try:
        import ymarket_brain_v1 as BR
        r = BR.brain_call(system, user)
        return (r or {}).get("text") or "" if (r or {}).get("ok") else ""
    except Exception:
        return ""


def _resolve_speak(gate, word, speak_fn):
    """Реально ли звать speak_fn в этом прогоне. М2: off — никогда; dry — только явно
    инъецированный speak_fn (тесты/превью «как будет звучать», 0 сети); live — инъецированный ИЛИ
    дефолт-мозг, но ТОЛЬКО со словом оператора (word=True)."""
    if gate == "off":
        return False
    if gate == "dry":
        return speak_fn is not None
    return word  # live: дефолт-мозг подключается ниже при word=True


def _apply_voice(item, *, system_tpl, global_uni, date_str, speak_fn):
    """Прогнать озвучку одного атома (позиция/спор), проэкранировать числа. Мутирует и возвращает
    dict с pr_llm/llm/screened. Никогда не трогает grounding-факты (М6): голос — всегда «прение»."""
    uni = set(global_uni)
    grounding_texts = []
    for g in item.get("grounding") or item.get("facts") or []:
        if isinstance(g, dict):
            grounding_texts.append(str(g.get("text", "")))
    for s in (item.get("stance"), item.get("summary")):
        if s:
            grounding_texts.append(str(s))
    for t in grounding_texts:
        uni |= SV._numbers(t)
    prompt_parts = [x for x in grounding_texts if x]
    user = "\n".join(prompt_parts) if prompt_parts else ""
    if not user.strip():
        item["note"] = (item.get("note", "") + " (нечего озвучивать — пустые факты)").strip()
        item["pr_llm"], item["llm"], item["screened"] = None, False, {"fired": False, "stripped": []}
        return item
    try:
        raw = (speak_fn or (lambda s, u: ""))(system_tpl, user) or ""
    except Exception:
        raw = ""
    if not raw.strip():
        item["pr_llm"], item["llm"] = None, False
        item["screened"] = {"fired": False, "stripped": []}
        item["note"] = (item.get("note", "") + " (мозг молчит — озвучки нет)").strip()
        return item
    scr = _screen_llm(raw, universe=uni, date_str=date_str)
    if scr["fired"]:
        item["pr_llm"], item["llm"] = None, False
        item["screened"] = scr
        item["note"] = (item.get("note", "") +
                        f" (LLM-озвучка отклонена экраном VL1: числа вне фактов {scr['stripped']})").strip()
        return item
    item["pr_llm"], item["llm"], item["screened"] = raw, True, {"fired": False, "stripped": []}
    return item


def _voice_positions(positions, *, global_uni, date_str, speak_fn):
    for p in positions:
        _apply_voice(p, system_tpl=f"Ты — орган «{p.get('organ')}» на совете директоров. Произнеси "
                                   f"свою позицию 1-2 фразами, по-деловому, ТОЛЬКО по фактам ниже, "
                                   f"никаких новых чисел.", global_uni=global_uni,
                     date_str=date_str, speak_fn=speak_fn)
    return positions


def _voice_disputes(disputes, *, global_uni, date_str, speak_fn):
    for d in disputes:
        _apply_voice(d, system_tpl=f"Ты — участник прения на совете ({d.get('id')}). Кратко, по "
                                   f"делу, ТОЛЬКО по фактам ниже, никаких новых чисел.",
                     global_uni=global_uni, date_str=date_str, speak_fn=speak_fn)
    return disputes


# ── честность «ждёт слова N»: сверка плана-следа с ТЕКУЩИМИ досье (04.09, находка живого доклада) ──

def _reconcile_waiting(waiting, dl):
    """Сверить «ждёт слова N» (список из ПЛАНА дня, ref=esc-map-{slug}) с ТЕКУЩИМ состоянием досье.

    План дня — утренний снимок (М3: совет зеркалит именно его); досье за день законно уезжают —
    маппинг подтверждается ОРГАНОМ (need_mapping→false + id дан; 04.09 живьём так ушло 8 из 12).
    Позиция УПРАВЛЯЮЩЕГО и W4, читающие ОДИН план, завышали бы счёт против досье в тот же миг
    (внутренний разнобой доклада: КАТЕГОРИЙЩИК перечисляет 4 реальных слога, а «ждёт слова 12»).
    Reconcile: esc-map-{slug}, чьё досье УЖЕ подтверждено → слово оператора больше не нужно → из
    ждущих убираем; всё ещё need_mapping / досье в списке нет → остаётся (ничего не выдумываем и не
    теряем; вечер НЕ добавляет новых watch-решений — М3 цело). Досье читаются в тот же миг, что и
    позиции, → числа спора = текущая правда, а не утренний след. НЕ-esc-map эскалации не трогаем.
    """
    by_slug = {r.get("slug"): r for r in dl if r.get("slug")}
    out = []
    for x in waiting or []:
        ref = x.get("ref")
        drop = False
        if isinstance(ref, str) and ref.startswith("esc-map-"):
            rec = by_slug.get(ref[len("esc-map-"):])
            if rec is not None and not rec.get("need_mapping") \
                    and rec.get("market_category_id") is not None:
                drop = True                      # маппинг подтверждён органом — слово не нужно
        if not drop:
            out.append(x)
    return out


# ── собрать doc споров (ничего не пишет) ────────────────────────────────────────

def compose_spory(*, date_str=None, store=None, registry=None, dossiers=None, vitrine=None,
                  journal=None, plan=None, prev_plan=None, protocol=None, speak_fn=None,
                  gate=None, word=False):
    """Собрать doc `ymarket.sovet.spory.v1`. Ничего не пишет.

    Контракт герметики — как у SV.compose: каждый «сырой» читатель инъецируется, None → реальный
    стор на диске (read 0₽):
      registry  полный СПИСОК заданий (doc T.load)  | None → реальный реестр;
      dossiers  DOC досье {"categories":{...}}       | None → реальный каталог;
      vitrine   DOC леджера {"goods":[...]}          | None → реальный goods_library;
      journal   СПИСОК строк журнала                  | None → реальный day_journal;
      plan      DOC плана дня (ymarket.plan.v1)       | None → оперативный файл даты, файла нет → build;
      prev_plan DOC плана вчера                       | None → PK.load_plan(вчера);
      protocol  DOC слоя 1 (SV.compose)               | None → собрать SV.compose(...) в памяти;
      speak_fn  callable(system,user)->str            | None → мозг (только live+word);
      gate      "off"|"dry"|"live"                    | None → env YM_SOVET_SPORY (нет env → off);
      word      bool (слово оператора на живую озвучку, RUBICON-стиль для live).
    """
    date_str = date_str or _today()
    gate = gate if gate in GATES else (_gate_from_env() if gate is None else "off")
    full = registry if registry is not None else (T.load()[0] or [])   # полный список заданий
    o, st, reg_err = PK.read_registry(full)
    dl, _dl_err = PK.read_dossiers(dossiers)          # записи очереди категорий (list)
    v = PK.read_vitrine(vitrine)                      # {by_store,by_category,total,load_err}
    j = PK.read_journal(journal)                      # {} — строк нет
    # оперативный ПЛАН ДНЯ (М3): файл даты, если есть (совет зеркалит ИМЕННО его) → иначе build
    plan_file = False
    if plan is None:
        loaded_plan, _pe = PK.load_plan(date_str)
        if loaded_plan:
            plan_doc, plan_file = loaded_plan, True
        else:
            plan_doc = PK.build_plan(date_str=date_str, store=store, registry=full,
                                     dossiers=dossiers, vitrine=vitrine, journal=journal)
    else:
        plan_doc = plan
    plan_doc = plan_doc or {}
    prev = prev_plan if prev_plan is not None else PK.load_plan(_yesterday(date_str))[0]
    # слой 1 в памяти (голоса/миссы/waiting/sources), если протокол не дан
    if protocol is None:
        protocol = SV.compose(date_str=date_str, store=store, registry=full, dossiers=dossiers,
                              vitrine=vitrine, journal=journal, plan=plan_doc, prev_plan=prev)
    protocol = protocol or {}
    misses = list(protocol.get("misses") or [])
    waiting = _reconcile_waiting(list(protocol.get("waiting_operator") or []), dl)

    positions = derive_positions(dossiers=dl, vitrine=v, journal=j, registry_open=o,
                                 plan=plan_doc, misses=misses, waiting_operator=waiting,
                                 store=store)
    disputes = detect_disputes(date_str=date_str, dossiers=dl, vitrine=v, registry_open=o,
                               plan=plan_doc, prev_plan=prev, misses=misses,
                               waiting_operator=waiting, store=store)

    doc = {
        "schema": SCHEMA, "date": date_str, "store": store or (protocol.get("store") or ""),
        "generated_at": _now_iso(), "mode": gate,
        "positions": positions, "disputes": disputes,
        "plan_date": plan_doc.get("date"), "plan_file": plan_file,
        "sources": {"registry_open": len(o), "vitrine_live": v.get("total", 0),
                    "dossiers": len(dl), "journal": j.get("date"),
                    "prev_plan": (prev or {}).get("date")},
    }
    # LLM-озвучка: только если слово/инъекция разрешены (М2); иначе детерминированный слой.
    if _resolve_speak(gate, word, speak_fn):
        fn = speak_fn
        if fn is None:
            fn = _brain_speak                          # live + слово: реальный мозг (сеть)
        uni = _global_universe(protocol=protocol, plan=plan_doc, date_str=date_str)
        _voice_positions(doc["positions"], global_uni=uni, date_str=date_str, speak_fn=fn)
        _voice_disputes(doc["disputes"], global_uni=uni, date_str=date_str, speak_fn=fn)
    else:
        doc["voice_note"] = ("детерминированный слой (0 LLM)" if gate != "live"
                             else "живая озвучка требует слова оператора (--live)")
        for p in doc["positions"]:
            p.setdefault("pr_llm", None); p.setdefault("llm", False)
            p.setdefault("screened", {"fired": False, "stripped": []})
        for d in doc["disputes"]:
            d.setdefault("pr_llm", None); d.setdefault("llm", False)
            d.setdefault("screened", {"fired": False, "stripped": []})
    return doc


# ── рендер (read: что оператор видит) ───────────────────────────────────────────

def render_spory(doc, date_str=None):
    """Человеческий «СПОРЫ ОРГАНОВ» (лист строк). doc=None → честно «прений не было» (VL5)."""
    date_str = date_str or (doc or {}).get("date") or _today()
    if not doc:
        return [f"СПОРЫ ОРГАНОВ · {date_str}: прений не было — органам нечего противопоставить "
                "(пустые входы/нет споров)"]
    out = []
    mode = doc.get("mode")
    out.append(f"СПОРЫ ОРГАНОВ · {doc.get('date')} · {doc.get('store') or 'ЯМ'} · режим {mode}")
    if doc.get("voice_note"):
        out.append(f"({doc['voice_note']})")
    pos = doc.get("positions") or []
    out.append(f"ПОЗИЦИИ органов (данные из сторов; прения — мнение, не факт): {len(pos)}")
    for p in pos:
        org = p.get("organ")
        out.append(f"  · {org}: {p.get('stance')}")
        for f in p.get("facts") or []:
            out.append(f"      факт: {f.get('text')} — {f.get('source')}")
        if p.get("proposal"):
            out.append(f"      предлагает: {p['proposal']}")
        if p.get("pr_llm"):
            out.append(f"      озвучка (прение, мнение органа — НЕ факт): «{p['pr_llm']}»")
        elif p.get("screened", {}).get("fired"):
            out.append(f"      (LLM-озвучка отклонена экраном VL1: числа вне фактов "
                       f"{p['screened'].get('stripped')})")
    disp = doc.get("disputes") or []
    if not disp:
        out.append("ПРЕНИЯ: споров/конфликтов не выявлено (позиции не тянут врозь)")
    else:
        out.append(f"ПРЕНИЯ ({len(disp)}):")
        for d in disp:
            kind = d.get("kind")
            between = " ⇄ ".join(d.get("between") or [])
            out.append(f"  · {d.get('id')} [{kind}] {between}")
            out.append(f"      суть: {d.get('summary')}")
            for g in d.get("grounding") or []:
                out.append(f"      факт: {g.get('text')} — {g.get('source')}")
            if d.get("proposal"):
                out.append(f"      предлагает оператору: {d['proposal']}")
            if d.get("pr_llm"):
                out.append(f"      озвучка прения (мнение, НЕ факт): «{d['pr_llm']}»")
            if d.get("note"):
                out.append(f"      ({d['note']})")
    out.append("споры ничего не пишут наружу и заданий не создают — только слово оператору (VL10)")
    return out


# ── стор (VL4 dry/commit, VL6 once-per-date) ────────────────────────────────────

def save_spory(doc, *, commit=False, path=None):
    """Сохранить споры в локальный стор. commit=False → ничего не пишет (dry)."""
    if not commit:
        return {"ok": True, "dry": True, "path": str(spory_path(doc.get("date")))}
    p = Path(path) if path else spory_path(doc.get("date"))
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        tmp.replace(p)
        return {"ok": True, "dry": False, "path": str(p)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def load_spory(date_str=None, path=None):
    """Читать споры. Нет/битый → (None, честный load_error)."""
    p = Path(path) if path else spory_path(date_str)
    if not p.exists():
        return None, None
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except Exception as e:
        return None, {"load_error": f"{type(e).__name__}: {e}"}


def resolve_spory_daily(*, date_str=None, store=None, commit=False, gate=None, word=False,
                        registry=None, dossiers=None, vitrine=None, journal=None, plan=None,
                        prev_plan=None, protocol=None, speak_fn=None):
    """Один «прение» на дату (каденция, как resolve_daily слоя 1). Возвращает summary-dict:
      {date, already (VL6), gathered (есть что показать), dry, ok, doc|None, path|None,
       reason|None, lines:[...]}."""
    date_str = date_str or _today()
    p = spory_path(date_str)
    if p.exists():
        docx, err = load_spory(date_str)
        return {"date": date_str, "already": True,
                "gathered": bool((docx or {}).get("positions")) or bool((docx or {}).get("disputes")),
                "dry": False, "ok": err is None, "doc": docx, "path": str(p),
                "reason": "споры даты уже собраны (VL6)", "lines": render_spory(docx, date_str)}
    doc = compose_spory(date_str=date_str, store=store, registry=registry, dossiers=dossiers,
                        vitrine=vitrine, journal=journal, plan=plan, prev_plan=prev_plan,
                        protocol=protocol, speak_fn=speak_fn, gate=gate, word=word)
    empty = not (doc.get("positions") or doc.get("disputes"))
    if empty:
        return {"date": date_str, "already": False, "gathered": False, "dry": not commit,
                "ok": True, "doc": doc, "path": None,
                "reason": "прений не было — органам нечего противопоставить (VL5)",
                "lines": render_spory(None, date_str)}
    if not commit:
        return {"date": date_str, "already": False, "gathered": True, "dry": True,
                "ok": True, "doc": doc, "path": None,
                "reason": "dry — споры не записаны", "lines": render_spory(doc)}
    saved = save_spory(doc, commit=True)
    return {"date": date_str, "already": False, "gathered": True, "dry": False,
            "ok": bool(saved.get("ok")), "doc": doc, "path": saved.get("path"),
            "reason": saved.get("error"), "lines": render_spory(doc)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="СПОРЫ ОРГАНОВ (слой 2 СОВЕТА): позиции + детектированные конфликты (0₽, read)")
    ap.add_argument("--date", default=None, help="дата (по умолчанию сегодня)")
    ap.add_argument("--store", default=None, help="магазин-кабинет (по умолчанию — из сторов)")
    ap.add_argument("--commit", action="store_true",
                    help="записать споры (локально, spory/) — по умолчанию dry")
    ap.add_argument("--live", action="store_true",
                    help="живая LLM-озвучка (только если YM_SOVET_SPORY=live в env И это твоё слово)")
    a = ap.parse_args()
    if a.date and a.commit and a.date != time.strftime("%Y-%m-%d"):
        print("чужую дату живьём не пишем (--date прошлого/будущего только dry)")
        raise SystemExit(1)
    env_gate = _gate_from_env()
    if a.live and env_gate != "live":
        print(f"живая озвучка выключена: YM_SOVET_SPORY={env_gate!r}, нужно 'live' (канон: env + слово)")
        raise SystemExit(1)
    res = resolve_spory_daily(date_str=a.date, store=a.store, commit=a.commit,
                              gate=env_gate if not a.live else "live",
                              word=bool(a.live), speak_fn=None)
    for ln in res["lines"]:
        print(ln)
    note = f"\n{res['reason']}" if res["reason"] else ""
    print(f"\n(споры {a.date or 'сегодня'} · gathered={res['gathered']} already={res['already']}"
          f" dry={res['dry']}{note})")
    raise SystemExit(0 if res["ok"] else 1)

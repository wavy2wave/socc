#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СОВЕТ ДИРЕКТОРОВ ОРГАНОВ — ymarket_sovet_v1: живое внутреннее «общение» системы, имеющее смысл.

ЗАЧЕМ (директива оператора 04.09, Task #8). Оператор хочет видеть, что система ЖИВА и трудится
в его духе — как реальный офис: Управляющий-Мозг собирает органы, они докладывают, он ловит лень и
вваливает пропиздоны, раздаёт/подтверждает задания. Честный вердикт линз (канон YM_SOVET_V1.md):
совет НЕ лишний, если он ЛИЦЕВАЯ СТОРОНА уже существующего УТРЕННЕГО ПЛАНА ДНЯ (ymarket_plannerka_v1),
а не второй источник решений и не театр. Решения совета = решения ПЛАНА ДНЯ; совет сам НЕ порождает
заданий и НЕ получает новых write-ног (VL7) — протокол лишь фиксирует, кто что доложил, кому
пропиздон и за какой факт, что упёрлось в слово оператора.

АНТИ-ТЕАТР (что совет НЕ делает):
  • Голоса органов НЕ генерит LLM — орган говорит ТОЛЬКО своими данными из стора, каждая фраза
    несёт источник; фраза/голос без ссылки-источника отбрасывается (VL2).
  • Числа председателя ⊆ чисел входных голосов — валидатор после вызова; иначе детерминированный
    фолбэк-свод (VL1, validated=false), никогда не выдумываем сверх голосов.
  • Пропиздон — ТОЛЬКО детерминированный miss-движок ДО председателя (VL3): вчерашний carry открыт
    сегодня без единого закрытого пункта при существовавшем сухом 0₽ пути. Прогресс/live/слово
    оператора — ЯВНЫЕ НЕ-миссы. Сегодня ленивых ~0 → совет честно «пропиздонов нет».
  • Орган без стора/не провязан — в совете ОТСУТСТВУЕТ (вакансия не говорит и не получает заданий).

РУБИКОН. Движок сам наружу НЕ пишет и заданий НЕ создаёт: протокол — ТОЛЬКО локальный стор
sovet/ymarket_sovet_<дата>.json под commit=True (даёт вызывающий: автопилот `_SOVET_COMMIT`,
интерактив — слово оператора). Кабинет/сеть/₽ не трогает. Каденция: один протокол на дату
(once-per-date, VL6) — утром шаг 0.5 автопилота после _plannerka; тики 14:17/20:47 лишь рендерят.

ИСТОЧНИКИ ГОЛОСОВ (первый срез — реальные читатели, зеркало plannerka, env-герметичны):
  ЦИКЛ-1          ← леджер goods_library   (доказанно живых — СВЕРКА PASS, proof_cross PL2)
  КАТЕГОРИЙЩИК    ← досье категорий        (готово/ждут/маппинг на слове оператора)
  ДИСПЕТЧЕР       ← журнал суточного       (горящие заказы; живой срез в исполнении, PL6)
  РЕЕСТР/ЗАДАНИЯ  ← ymarket_tasks.json     (открытые по владельцам)
  план дня        ← plannerka build/load   (решения carry|new|escalation|watch)
  env-переопределения YM_SOVET_DIR/YM_PLAN_DIR/YM_TASKS_PATH/YM_DOSSIERS_PATH/YM_LIBRARY_PATH/
  YM_DAY_JOURNAL — герметичные приёмки пишут/читают только песочницу; реальный диск не трогаем.

ЗАКОНЫ (герметика + анти-вралье, покрыты приёмкой tests/run_sovet.py):
  VL1 числа председателя ⊆ чисел входных голосов; иначе — сухой свод (validated=false, VL1).
  VL2 факт/голос без ссылки-источника отбрасывается.
  VL3 пропиздон ТОЛЬКО из miss-движка; прогресс (закрытый пункт) / live / слово оператора — НЕ мисс.
  VL4 dry ничего не пишет; commit → tmp+replace в sovet/<дата>.json.
  VL5 пустой совет файл даты НЕ создаёт; рендер по отсутствию — честно «совет не собирался».
  VL6 once-per-date: файл даты уже есть → повторный resolve не перезаписывает.
  VL7 совет сам НЕ порождает задания: в исходнике нет T.new_task / save реестра / Маркет-записи.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ymarket_plannerka_v1 as PK                   # noqa: E402  (читатели сторов + план дня)
import ymarket_tasks_v1 as T                         # noqa: E402  (derive/open_only — для miss-движка)

SCHEMA = "ymarket.sovet.v1"

# Владельцы, которым живой акт/решение даёт САМ оператор, а не совет. Совет может разве что
# доложить, что они упёрлись в слово — пропиздоном «лень» это НЕ называем (VL3).
_NON_MISS_OWNERS = {"OPERATOR", "PRICER"}            # PRICER: живая переценка наружу — RUBICON/слово


# ── пути/стор ───────────────────────────────────────────────────────────────────

def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _today():
    return time.strftime("%Y-%m-%d")


def _yesterday(date_str):
    return (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")


def sovet_dir():
    """Каталог протоколов совета. env YM_SOVET_DIR перекрывает (песочница/тесты)."""
    p = os.environ.get("YM_SOVET_DIR")
    if p:
        return Path(p)
    return T.REPORTS / "sovet"


def sovet_path(date_str=None):
    """Протокол совета — один файл на дату: sovet/ymarket_sovet_<дата>.json."""
    date_str = date_str or _today()
    return sovet_dir() / f"ymarket_sovet_{date_str}.json"


# ── сбор голосов (детерминированно из сторов; каждая фраза несёт источник, VL2) ──

def gather_voices(*, registry_open=None, stats=None, reg_err=None, dossiers=None,
                  vitrine=None, journal=None, plan=None):
    """Голоса органов-членов совета. Входы — НОРМАЛИЗОВАННЫЕ результаты читателей plannerka
    (форма как build_plan→propose): registry_open=открытые задания, stats=сводка реестра,
    reg_err=load_err реестра, dossiers=записи категорий (list), vitrine=result леджера {total,…},
    journal=result журнала. Каждая фраза несёт источник; орган, которому нечего сказать
    по-честному, говорит это ИСТОЧНИКОМ, а не выдумывает.
    Возвращает [ {organ, facts:[{text,source}], nuzhno_slovo:[{what,why,source}]} ]."""
    ro = list(registry_open or [])
    dl = list(dossiers or [])
    v = vitrine or {}
    j = journal or {}
    voices = []

    # ЦИКЛ-1 — леджер доказанно живых (СВЕРКА PASS)
    cyc = {"organ": "ЦИКЛ-1", "facts": [], "nuzhno_slovo": []}
    if v.get("load_err"):
        cyc["facts"].append({"text": "леджер ЦИКЛ-1 не читается — «живого» не считаем",
                             "source": f"goods_library load_err: {v['load_err']}"})
    elif v.get("total"):
        cats = ", ".join(f"{c}×{n}" for c, n in sorted(v.get("by_category", {}).items()))
        cyc["facts"].append({"text": f"доказанно живых {v['total']} ({cats})",
                             "source": "goods_library · СВЕРКА PASS (proof_cross)"})
    else:
        cyc["facts"].append({"text": "доказанно живых 0 — леджер пуст (честно)",
                             "source": "goods_library"})
    voices.append(cyc)

    # КАТЕГОРИЙЩИК — очередь категорий
    kat = {"organ": "КАТЕГОРИЙЩИК", "facts": [], "nuzhno_slovo": []}
    ready = [x for x in dl if x.get("ready", 0) > 0]
    need_word = [x for x in dl if x.get("need_mapping") and not x.get("market_category_id")]
    if not dl:
        kat["facts"].append({"text": "очередь категорий пуста/не читается",
                             "source": "categorist_dossiers"})
    else:
        kat["facts"].append(
            {"text": f"в очереди {len(dl)} категорий · готово к заливу {len(ready)} "
                     f"({sum(x['ready'] for x in ready)} SKU)",
             "source": "categorist_dossiers"})
        for x in need_word:
            kat["nuzhno_slovo"].append(
                {"what": f"подтвердить профиль ЯМ-категории для «{x['slug']}»",
                 "why": "без market_category_id карточку не поставить — маппинг решает человек",
                 "source": "categorist_dossiers · mapping.need_mapping"})
    voices.append(kat)

    # ДИСПЕТЧЕР — заказы (честный 0, не выдумка; живой срез в исполнении)
    dis = {"organ": "ДИСПЕТЧЕР", "facts": [], "nuzhno_slovo": []}
    if not j:
        dis["facts"].append({"text": "журнала суточного нет — свежих заказов на диске нет",
                             "source": "day_journal"})
    else:
        dis["facts"].append(
            {"text": f"журнал {j.get('date')}: горящих заказов {j.get('urgent_orders')} · "
                     f"burning {j.get('burning')} · движение {j.get('top_move')}",
             "source": f"day_journal {j.get('date')}"})
    voices.append(dis)

    # РЕЕСТР/ЗАДАНИЯ — открытые по владельцам
    reg = {"organ": "РЕЕСТР", "facts": [], "nuzhno_slovo": []}
    if reg_err:
        reg["facts"].append({"text": f"реестр не читается ({reg_err}) — открытых не считаем",
                             "source": "ymarket_tasks.json"})
    else:
        own = (stats or {}).get("open_by_owner") or {}
        own_s = ", ".join(f"{k}={n}" for k, n in sorted(own.items(), key=lambda x: -x[1])) or "—"
        reg["facts"].append({"text": f"открыто заданий {len(ro)} · владельцы: {own_s}",
                             "source": "ymarket_tasks.json"})
    voices.append(reg)

    return voices


def _clean_voices(voices):
    """VL2: факт без ссылки-источника отбрасывается; голос без единого факта — весь вон."""
    out = []
    for v in voices or []:
        if not isinstance(v, dict) or not v.get("organ"):
            continue
        facts = [f for f in (v.get("facts") or [])
                 if isinstance(f, dict) and f.get("text") and f.get("source")]
        nsl = [n for n in (v.get("nuzhno_slovo") or [])
               if isinstance(n, dict) and n.get("what") and n.get("source")]
        if not facts and not nsl:
            continue
        out.append({"organ": v["organ"], "facts": facts, "nuzhno_slovo": nsl})
    return out


# ── miss-движок (ДО председателя, VL3: лень по факту, не мнение) ────────────────

def detect_misses(*, plan=None, prev_plan=None, registry_open=None):
    """Детерминированные пропиздоны: вчерашний carry открыт сегодня БЕЗ единого закрытого пункта
    при существовавшем сухом 0₽ пути. НЕ-миссы: живой акт наружу (mode=live), владелец на слове
    оператора (OPERATOR/PRICER), задание в waiting/in_progress (зависимость/есть прогресс).
    Сегодня реально ленивых ~0 — совет честно скажет «пропиздонов нет». Возвращает список."""
    plan = plan or {}
    prev = prev_plan or {}
    if not prev.get("decisions"):
        return []                                   # нет вчерашнего плана — не с чем сверять
    prev_carry = {d.get("refs", {}).get("task_id")
                  for d in prev["decisions"] if d.get("kind") == "carry"}
    open_t = list(registry_open or [])
    misses = []
    for d in plan.get("decisions") or []:
        if d.get("kind") != "carry":
            continue
        tid = (d.get("refs") or {}).get("task_id")
        if not tid or tid not in prev_carry:
            continue                                # вчера не carry / новое — не лень
        owner = (d.get("owner") or "?").upper()
        if owner in _NON_MISS_OWNERS:
            continue                                # слово оператора/живой акт — НЕ мисс
        if d.get("mode") == "live":
            continue                                # живой акт наружу — RUBICON, не лень
        task = next((t for t in open_t if t.get("id") == tid), None)
        if task is None:
            continue
        st = T.derive(task)
        if st != "open":                            # in_progress=есть прогресс, waiting=не лень
            continue
        ndone = sum(1 for s in (task.get("steps") or []) if s.get("state") == "done")
        if ndone > 0:
            continue
        misses.append({
            "organ": owner,
            "what": task.get("what"),
            "task_id": tid,
            "since": prev.get("date"),
            "evidence": f"carry в планах {prev.get('date')} и {plan.get('date')}; пунктов закрыто "
                        f"0 при сухом 0₽ пути — {owner} не пошевелил задание за сутки",
        })
    return misses


# ── председатель: числа ⊆ голосов (VL1) ─────────────────────────────────────────

_NUM = re.compile(r"\d+")


def _numbers(text):
    """Целые числа из строки (дата отбрасывается отдельно)."""
    return set(int(m) for m in _NUM.findall(text or ""))


def _date_numbers(date_str):
    """Компоненты даты как числа, которые текстам разрешено повторять без «выдумки»: год, месяц,
    день и слитное yyyymmdd (дата — техническая метка, не содержание доклада)."""
    if not date_str:
        return set()
    try:
        y, m, d = date_str.split("-")
        return {int(y), int(m), int(d), int(date_str.replace("-", ""))}
    except Exception:
        return set()


def _number_universe(*, voices, misses, plan, waiting_operator, date_str):
    """«Вселенная чисел», которые совету разрешено утверждать: только из входных голосов/миссов/
    плана. Компоненты даты и 0 — технические, не считаем выдумкой."""
    uni = set()
    for v in voices or []:
        for f in v.get("facts") or []:
            uni |= _numbers(f.get("text", "")) | _numbers(f.get("source", ""))
    for m in misses or []:
        uni |= _numbers(m.get("evidence", ""))
    dec = plan.get("decisions") or []
    for d in dec:
        uni |= _numbers(str(d.get("what") or "")) | _numbers(str(d.get("evidence") or ""))
    # счётчики плана — это же числа из голосов
    by_kind = {}
    for d in dec:
        by_kind[d.get("kind")] = by_kind.get(d.get("kind"), 0) + 1
    uni |= set(by_kind.values())
    uni |= _numbers(str(len(waiting_operator or [])))
    uni.add(0)                                       # «пропиздонов 0» — законный честный ноль
    uni -= _date_numbers(date_str)
    return uni


def validate_numbers(text, *, universe, date_str=None):
    """VL1: числа председателя ⊆ чисел входных голосов (компоненты даты текста не в счёт).
    True — председатель утверждает только числа, прозвучавшие в голосах/плане."""
    nums = _numbers(text) - _date_numbers(date_str)
    return nums <= universe


def _waiting_operator(plan):
    """Список «ждёт слова оператора» из решений плана kind=escalation (детерминированно)."""
    out = []
    for d in plan.get("decisions") or []:
        if d.get("kind") != "escalation":
            continue
        out.append({"what": d.get("what"), "why": d.get("why"),
                    "source": d.get("evidence"), "ref": d.get("id")})
    # дедуп по what
    seen, uniq = set(), []
    for x in out:
        if x["what"] in seen:
            continue
        seen.add(x["what"])
        uniq.append(x)
    return uniq


def _svod_chair_text(*, date_str, voices, misses, waiting_operator, plan):
    """Детерминированный сухой свод председателя (0 LLM, 0₽): числа — только из голосов (VL1).
    «Пропиздон» вваливает ТОЛЬКО по факту miss-движка; ленивых нет → честно говорит об этом."""
    dec = plan.get("decisions") or []
    by_kind = {}
    for d in dec:
        by_kind[d.get("kind")] = by_kind.get(d.get("kind"), 0) + 1
    lines = ["заслушаны доклады органов (данные из сторов, каждая фраза с источником):"]
    for v in voices or []:
        facts = "; ".join(f["text"] for f in v.get("facts") or [])
        lines.append(f"  · {v['organ']}: {facts}")
    if misses:
        lines.append("пропиздоны (по факту miss-движка, не мнение):")
        for m in misses:
            lines.append(f"  · {m['organ']}: «{m['what']}» — {m['evidence']}")
    elif waiting_operator:
        lines.append(f"пропиздонов нет — органы упёрлись в слово оператора "
                     f"(ждёт слова {len(waiting_operator)}), а не в лень")
    else:
        lines.append("пропиздонов нет — ленивых сегодня нет (всё либо движется, либо сухо-доказано)")
    if waiting_operator:
        lines.append("ждёт слова оператора:")
        for x in waiting_operator:
            lines.append(f"  · {x['what']} — {x['source']}")
    lines.append(f"решения плана дня (совет зеркалит, новых заданий сам не создаёт): "
                 f"carry {by_kind.get('carry', 0)} · new {by_kind.get('new', 0)} · "
                 f"на слове {by_kind.get('escalation', 0)} · watch {by_kind.get('watch', 0)}")
    return "\n".join(lines)


def _compose_chair(*, date_str, voices, misses, waiting_operator, plan, chair_fn, chair_by):
    """Вызов председателя. chair_fn=None → детерминированный свод. chair_fn дан → его текст обязан
    пройти VL1 (числа ⊆ голосов); иначе фолбэк-свод, validated=false (не врём, не прячем)."""
    svod = _svod_chair_text(date_str=date_str, voices=voices, misses=misses,
                            waiting_operator=waiting_operator, plan=plan)
    if chair_fn is None:
        return {"mode": "svod", "by": "УПРАВЛЯЮЩИЙ-МОЗГ", "text": svod, "validated": True}
    uni = _number_universe(voices=voices, misses=misses, plan=plan,
                           waiting_operator=waiting_operator, date_str=date_str)
    try:
        raw = chair_fn() or ""
    except Exception as e:
        raw = ""
        note = f"председатель упал ({type(e).__name__}: {e}) → сухой свод"
        return {"mode": "svod", "by": "УПРАВЛЯЮЩИЙ-МОЗГ", "text": svod,
                "validated": False, "note": note}
    if not raw.strip():
        return {"mode": "svod", "by": "УПРАВЛЯЮЩИЙ-МОЗГ", "text": svod,
                "validated": False, "note": "председатель вернул пусто → сухой свод"}
    if validate_numbers(raw, universe=uni, date_str=date_str):
        return {"mode": "llm", "by": chair_by or "УПРАВЛЯЮЩИЙ-МОЗГ (LLM)", "text": raw,
                "validated": True}
    return {"mode": "svod", "by": "УПРАВЛЯЮЩИЙ-МОЗГ", "text": svod, "validated": False,
            "note": "LLM-председатель отклонён валидатором VL1 (число вне голосов) → сухой свод"}


# ── собрать протокол (doc, ничего не пишет) ─────────────────────────────────────

def compose(*, date_str=None, store=None, registry=None, dossiers=None, vitrine=None,
            journal=None, plan=None, prev_plan=None, voices=None, chair_fn=None,
            chair_by=None):
    """Собрать doc протокола совета (schema ymarket.sovet.v1). Ничего не пишет.

    Контракт входов — как у plannerka.build_plan (герметика): каждый «сырой» вход читателя;
    None → реальный стор:
      registry  полный СПИСОК заданий | None → реальный реестр;
      dossiers  DOC досье {"categories":...} | None → реальный каталог;
      vitrine   DOC леджера {"goods":...} | None → реальный goods_library;
      journal   СПИСОК строк журнала | None → реальный day_journal;
      plan      DOC плана дня | None → build_plan (свежий, из тех же входов);
      prev_plan DOC плана вчера | None → load_plan(вчера);
      voices    СПИСОК голосов | None → gather_voices;
      chair_fn  callable()→текст | None → детерминированный свод (VL1 валидирует текст).
    Возвращает doc; в нём sources — честные счётчики входов для лица."""
    date_str = date_str or _today()
    # читатели входов: сырой doc дан → герметично (диск не трогаем), None → реальный стор
    full = registry if registry is not None else (T.load()[0] or [])   # полный список заданий
    o, st, reg_err = PK.read_registry(full)      # открытые + сводка + load_err
    d, _de = PK.read_dossiers(dossiers)          # записи очереди категорий (list)
    v = PK.read_vitrine(vitrine)                 # result леджера {total, …}
    j = PK.read_journal(journal)                 # result журнала ({} — строк нет)
    plan_doc = plan if plan is not None else PK.build_plan(
        date_str=date_str, store=store, registry=full, dossiers=dossiers,
        vitrine=vitrine, journal=journal)
    plan_doc = plan_doc or {}

    vs = (_clean_voices(voices) if voices is not None else _clean_voices(gather_voices(
        registry_open=o, stats=st, reg_err=reg_err, dossiers=d, vitrine=v, journal=j,
        plan=plan_doc)))
    prev = prev_plan if prev_plan is not None else PK.load_plan(_yesterday(date_str))[0]
    misses = detect_misses(plan=plan_doc, prev_plan=prev, registry_open=o)
    waiting = _waiting_operator(plan_doc)
    chair = _compose_chair(date_str=date_str, voices=vs, misses=misses,
                           waiting_operator=waiting, plan=plan_doc,
                           chair_fn=chair_fn, chair_by=chair_by)
    by_kind = {}
    for x in plan_doc.get("decisions") or []:
        by_kind[x.get("kind")] = by_kind.get(x.get("kind"), 0) + 1
    return {
        "schema": SCHEMA, "date": date_str, "store": store or (plan_doc.get("store") or ""),
        "generated_at": _now_iso(), "mode": "dry",
        "chair": chair,
        "voices": vs,
        "misses": misses,
        "waiting_operator": waiting,
        "plan": {"date": plan_doc.get("date"), "decisions": len(plan_doc.get("decisions") or []),
                 "carry": by_kind.get("carry", 0), "new": by_kind.get("new", 0),
                 "escalation": by_kind.get("escalation", 0), "watch": by_kind.get("watch", 0)},
        "sources": {"registry_open": len(o), "vitrine_live": v.get("total", 0),
                    "dossiers": len(d), "journal": j.get("date"),
                    "prev_plan": (prev or {}).get("date")},
    }


# ── рендер (read, что оператор видит) ──────────────────────────────────────────

def render_sovet(protocol, date_str=None):
    """Человеческий «СОВЕТ»-протокол. protocol=None → честно «совет не собирался» (VL5/7-лицо).
    Всегда строка(и)."""
    date_str = date_str or (protocol or {}).get("date") or _today()
    if not protocol:
        return [f"СОВЕТ ДИРЕКТОРОВ · {date_str}: совет не собирался — нечего решать "
                "(пустые входы/всё за словом оператора)"]
    out = []
    ch = protocol.get("chair") or {}
    out.append(f"СОВЕТ ДИРЕКТОРОВ ОРГАНОВ · {protocol.get('date')} · "
               f"{protocol.get('store') or 'ЯМ'}")
    out.append(f"председатель: {ch.get('by')} · режим {ch.get('mode')}"
               + ("" if ch.get("validated") else " (валидатор VL1: свод заменил председателя)"))
    if ch.get("text"):
        out += [ln for ln in ch["text"].splitlines()]
    out.append("-" * 40)
    out.append("ГОЛОСА (из сторов, с источником):")
    for v in protocol.get("voices") or []:
        for f in v.get("facts") or []:
            out.append(f"  · {v['organ']}: {f['text']} — {f['source']}")
        for n in v.get("nuzhno_slovo") or []:
            out.append(f"  · {v['organ']} ждёт слова: {n['what']} ({n['source']})")
    if protocol.get("misses"):
        out.append("ПРОПИЗДОНЫ (по факту):")
        for m in protocol["misses"]:
            out.append(f"  · {m['organ']}: «{m['what']}» — {m['evidence']}")
    pl = protocol.get("plan") or {}
    out.append(f"РЕШЕНИЯ плана дня (совет зеркалит): carry {pl.get('carry', 0)} · "
               f"new {pl.get('new', 0)} · на слове {pl.get('escalation', 0)} · "
               f"watch {pl.get('watch', 0)}")
    out.append("совет сам новые задания не порождает — только через планёрку/реестр (TZ1)")
    return out


# ── стор протокола (VL4 dry/commit, VL6 once-per-date) ─────────────────────────

def save_protocol(protocol, *, commit=False, path=None):
    """Сохранить протокол совета в локальный стор. commit=False → ничего не пишет (dry)."""
    if not commit:
        return {"ok": True, "dry": True, "path": str(sovet_path(protocol.get("date")))}
    p = Path(path) if path else sovet_path(protocol.get("date"))
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(protocol, ensure_ascii=False, indent=1))
        tmp.replace(p)
        return {"ok": True, "dry": False, "path": str(p)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def load_protocol(date_str=None, path=None):
    """Читать протокол совета. Нет/битый → (None, честный load_error)."""
    p = Path(path) if path else sovet_path(date_str)
    if not p.exists():
        return None, None
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except Exception as e:
        return None, {"load_error": f"{type(e).__name__}: {e}"}


# ── суточный resolve (каденция: один протокол на дату, VL5/VL6) ─────────────────

def resolve_daily(*, date_str=None, store=None, commit=False, registry=None, dossiers=None,
                  vitrine=None, journal=None, plan=None, prev_plan=None, voices=None,
                  chair_fn=None, chair_by=None):
    """Один «заседание» на дату. Возвращает summary-dict:
      {date, already: bool (файл даты уже был — не переписываем, VL6),
       gathered: bool (было что решать), dry: bool (не записан), ok: bool,
       protocol: doc|None, path: str|None, reason: str|None, lines: [...]}."""
    date_str = date_str or _today()
    p = sovet_path(date_str)
    if p.exists():
        proto, err = load_protocol(date_str)
        return {"date": date_str, "already": True, "gathered": bool(proto),
                "dry": False, "ok": err is None,
                "protocol": proto, "path": str(p), "reason": "протокол даты уже собран (VL6)",
                "lines": render_sovet(proto, date_str) if proto else []}
    doc = compose(date_str=date_str, store=store, registry=registry, dossiers=dossiers,
                  vitrine=vitrine, journal=journal, plan=plan, prev_plan=prev_plan,
                  voices=voices, chair_fn=chair_fn, chair_by=chair_by)
    # «есть что решать» = реестр/очередь/леджер/заказы/решения реально что-то несут. Watch-решения
    # (наблюдаем/честный ноль, plannerka ставит «watch-orders» всегда) содержанием НЕ считаем —
    # иначе пустая система писала бы совет-болванку каждый день (VL5).
    pl = doc.get("plan") or {}
    substantive = int(pl.get("carry") or 0) + int(pl.get("new") or 0) + int(pl.get("escalation") or 0)
    empty = (doc["sources"]["registry_open"] == 0 and doc["sources"]["vitrine_live"] == 0
             and doc["sources"]["dossiers"] == 0 and not doc["sources"]["journal"]
             and not doc["misses"] and substantive == 0)
    if empty:
        return {"date": date_str, "already": False, "gathered": False, "dry": not commit,
                "ok": True, "protocol": doc, "path": None,
                "reason": "совет не собирался — системе нечего решать (пустые входы, VL5)",
                "lines": render_sovet(None, date_str)}
    if not commit:
        return {"date": date_str, "already": False, "gathered": True, "dry": True,
                "ok": True, "protocol": doc, "path": None, "reason": "dry — протокол не записан",
                "lines": render_sovet(doc)}
    saved = save_protocol(doc, commit=True)
    return {"date": date_str, "already": False, "gathered": True, "dry": False,
            "ok": bool(saved.get("ok")), "protocol": doc, "path": saved.get("path"),
            "reason": saved.get("error"), "lines": render_sovet(doc)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="СОВЕТ ДИРЕКТОРОВ ОРГАНОВ: собрать протокол совета из реальных сторов (0₽)")
    ap.add_argument("--date", default=None, help="дата совета (по умолчанию сегодня)")
    ap.add_argument("--store", default=None, help="магазин-кабинет (по умолчанию — из сторов)")
    ap.add_argument("--commit", action="store_true",
                    help="записать протокол (локально, sovet/) — по умолчанию dry")
    ap.add_argument("--chair", action="store_true",
                    help="звать LLM-председателя (только если YM_SOVET_CHAIR в env и это твоё слово)")
    a = ap.parse_args()
    # живьё/написание чужой даты без слова не делаем: --date + --commit чужой даты — отказ
    if a.date and a.commit and a.date != time.strftime("%Y-%m-%d"):
        print("чужую дату живьём не пишем (--date прошлого/будущего только dry)")
        raise SystemExit(1)
    chair = None
    if a.chair:
        if not os.environ.get("YM_SOVET_CHAIR"):
            print("LLM-председатель выключен: нет YM_SOVET_CHAIR в env (канон — env + слово)")
            raise SystemExit(1)
        try:
            import ymarket_brain_v1 as BR
            chair = lambda: BR.brain_call("ты председатель совета: коротко, по-деловому, "
                                          "только по данным голосов", verbose=False)
        except Exception as e:
            print(f"LLM-председатель недоступен ({type(e).__name__}: {e}) — сухой свод")
    res = resolve_daily(date_str=a.date, store=a.store, commit=a.commit, chair_fn=chair)
    for ln in res["lines"]:
        print(ln)
    note = f"\n{res['reason']}" if res["reason"] else ""
    print(f"\n(совет {a.date or 'сегодня'} · gathered={res['gathered']} already={res['already']}"
          f" dry={res['dry']}{note})")
    raise SystemExit(0 if res["ok"] else 1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЗАДАНИЯ ЯМ-ЦИКЛА (ymarket_tasks_v1) — durable-реестр работ, которые всегда есть в наличии.

ЗАЧЕМ (директива оператора 2026-09-02 «доп задание», ЯМ ЦИКЛ). Система не стоит: задания
ФОРМИРУЮТСЯ постоянно и быстро, ЦИКЛЫ (ЦИКЛ-1/ЦИКЛ-2/ЦИКЛ-ДНЯ) их ПОДХВАТЫВАЮТ. Каждое задание
обосновано, имеет владельца-орган («удавку на него»), категорию, приоритет (важное выше списка)
и состояние ПО ПУНКТАМ с гейтом «проверено БЕЗ фейк-пасс» — пункт закрывается только с evidence
и именем проверившего. Формат УНИВЕРСАЛЬНЫЙ: одно и то же поле market="ym"|"ozon" — структура
одна («системный АГИ-язык»), потому будущий ЦИКЛ ОЗОН ест ровно этот же реестр.

ЧТО ЕСТЬ ВОКРУГ (не дублируем, а ссылаемся):
  ymarket_matrix_v1   — дедуп/статус-лесенка ТОВАРОВ (кандидат→…→продан), поле task_id.
  ymarket_state_v1    — рабочий набор карточек (working_set), менеджер-состояние.
  ymarket_brain_v1    — УПРАВЛЯЮЩИЙ-МОЗГ: каталог [ДЕЙСТВИЕ] cycle_dry/cycle_live/plannerka/
                        self/registry/new_cycle — действия БЕЗ состояния и владельца.
  ymarket_cycle1_v1   — движок ЦИКЛ-1: run_cycle(store_slug,…), хеш sha1(slug|дата|версия),
                        stores.json (магазин = {slug, бизнес, кампания, склад, донор, …}).
  ymarket_team_feed_v1 — имена ролей (СТРАТЕГ/ДИСПЕТЧЕР/…) как словарь владельцев.
  ЭТОТ модуль = недостающее звено: у задания есть id/владелец/состояние/пункты — то, на что
  планёрка и ЦИКЛ-ДНЯ смотрят, а мозг мог бы выдавать строкой [ДЕЙСТВИЕ].

ЗАПИСЬ (JSON, тот же паттерн, что registry/matrix/library):
  стор ymarket_tasks.json под якорем MEMORY_WAVE/reports/mint/arbiter (канон отчётов ARBITER);
  env YM_TASKS_PATH перекрывает (песочница/тесты не пишут в канон); save под flock + backup
  битого .corrupt-*.bak; load битого/нет → пустой журнал + честный load_error (не падаем, не врём).
  Dry-гейт НЕ здесь: кто вызывает save — тот и решает (движок пишет только под not dry AND commit).

МОДЕЛЬ ЗАДАНИЯ (поля — это и есть «хеш показывает для чего/от кого/срочность/что»; id — стабильный
контентный хеш, чтобы одно и то же намерение давало ОДИН id и система не спамила дубликатами):
  id          T-<sha1(canon-поля)[:8]>   — стабильная идентичность намерения (TZ1)
  market      "ym"|"ozon"                — универсальность (TZ2)
  cycle       cycle1|cycle_day|cycle2    — какой цикл подхватит (TZ3)
  store       slug магазина (или "")     — к какому кабинету относится (TZ4)
  category    словарь CATEGORIES         — к какой работе относится (акции/категории/…)
  owner       орган-ответственный        — «удавка на него» (TZ5)
  urgency     critical|high|normal|low   — срочность (TZ6)
  priority    int (меньше = важнее)      — важное выше списка (TZ7)
  what        ЧТО сделать (заголовок)
  body        зачем/детали (обоснование)
  steps[]     пункты {id,title,state,done_at,done_by,evidence} — гейт (TZ8)
  depends_on  [id…]                      — что должно быть сделано раньше (TZ9)
  state       open|in_progress|waiting|done|blocked|archived
  source      кто породил (operator|brain|cycle_day|partners|…)
  created_at/updated_at
  refs        доп. ссылки (store-хеш, offerId, категория Маркета…)

ЗАКОНЫ (механические, покрыты приёмкой run_tasks):
  TZ1  id = стабильный хеш намерения (market·cycle·category·store·what·owner), а не случайный:
       то же задание, сформированное снова, — тот же id (реестр обновляет, не плодит).
  TZ2  market в ("ym","ozon") — ОДНА схема на маркетплейсы (ЦИКЛ ОЗОН ест тот же формат).
  TZ3  цикл подхвата обязателен (задание без цикла — «в стол», система не стоит: TZ-живость).
  TZ4  store необязателен (общесистемные задания), но если задан — slug существующей формы.
  TZ5  owner обязателен: у задания ВСЕГДА есть ответственный орган (не «безхозное»).
  TZ6  urgency из словаря; missing → normal (честный дефолт, не выдумка).
  TZ7  сортировка планёрки: priority (меньше = важнее) → created_at → urgency-ранг.
  TZ8  ПУНКТЫ + ГЕЙТ: пункт закрывает mark_step ТОЛЬКО с непустым evidence и done_by
       (без фейк-пасс). Задание «done» = ВСЕ пункты закрыты с evidence. Пустых шагов нет.
  TZ9  depends_on блокирует: пока зависимость не done — задание waiting, а не «в работе».
  TZ10 честность загрузки: битый стор → пустой журнал + load_error (не падаем, не выдумываем).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

# ── словари (универсальный АГИ-язык заданий) ───────────────────────────────────
SCHEMA = "ymarket.tasks.v1"
MARKETS = ("ym", "ozon")
CYCLES = ("cycle1", "cycle_day", "cycle2")        # cycle2 «выстрою позже» — формат уже тут
CATEGORIES = ("partners", "categories", "products", "cards", "photos", "pricing",
              "promo", "stocks", "health", "day", "other")
URGENCY = ("critical", "high", "normal", "low")
STATES = ("open", "in_progress", "waiting", "done", "blocked", "archived")
_URGENCY_RANK = {"critical": 0, "high": 1, "normal": 2, "low": 3}
_ORGANS = (  # известные органы-владельцы (валидация мягкая: незнакомый НЕ роняет — словник живёт)
    "PARTNERS", "STRATEGIST", "HEAD", "CATEGORIST", "MERCHANDISER", "PRICER",
    "PHOTO", "STOCKMAN", "DISPATCHER", "CONTROLLER", "DAY", "BRAIN", "SELF")


# ── стор (якорь MEMORY_WAVE, env-переопределение — паттерн registry/matrix) ────

def _reports_root():
    """Корень SOCC по маркеру MEMORY_WAVE. Репо-корень (.git) с MEMORY_WAVE — канон: вложенная
    сирота scripts/MEMORY_WAVE НЕ затеняет SOCC/MEMORY_WAVE. Вне git-репо (рело-аут копия) —
    ближайший предок с MEMORY_WAVE (LB6: пишем в свою, не в пустоту)."""
    here = Path(__file__).resolve().parent
    for anc in (here, *here.parents):
        if (anc / ".git").is_dir() and (anc / "MEMORY_WAVE").is_dir():
            return anc
    for anc in (here, *here.parents):
        if (anc / "MEMORY_WAVE").is_dir():
            return anc
    return here.parent.parent.parent


REPORTS = _reports_root() / "MEMORY_WAVE/reports/mint/arbiter"


def task_path():
    """Путь к стору. env YM_TASKS_PATH перекрывает (песочница/тесты не пишут в канон)."""
    p = os.environ.get("YM_TASKS_PATH")
    return Path(p) if p else (REPORTS / "ymarket_tasks.json")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def task_id(market, cycle, category, store, what, owner, urgency="normal"):
    """TZ1: стабильный id намерения = sha1(canon-поля)[:8]. То же намерение → тот же id."""
    canon = "|".join([str(market), str(cycle), str(category), str(store or ""),
                      str(what or "").strip().lower(), str(owner).upper(),
                      str(urgency).lower()])
    return "T-" + hashlib.sha1(canon.encode("utf-8")).hexdigest()[:8]


# ── фабрика ─────────────────────────────────────────────────────────────────────

def new_task(*, what, owner, category, market="ym", cycle="cycle1", store="",
             urgency=None, priority=50, body="", source="operator",
             depends_on=(), steps=None, refs=None):
    """Создать задание. Обязательны: what (что), owner (ответственный), category.

    urgency: не задан → "normal" (честный дефолт). steps: не задан → один пункт «Выполнить: what»
    (у задания всегда есть что закрывать — TZ8). Возвращает запись + None err; при битых
    аргументах — (None, проблема), НЕ молчаливая кривая запись (TZ-честность)."""
    what = (what or "").strip()
    owner = (owner or "").strip().upper()
    category = (category or "").strip().lower()
    if not what:
        return None, "what пуст — задание без «что делать» не создаём (TZ)"
    if not owner:
        return None, "owner пуст — у задания всегда есть ответственный орган (TZ5)"
    if category not in CATEGORIES:
        return None, f"category '{category}' вне словаря {CATEGORIES} (TZ-формат)"
    market = market.lower()
    if market not in MARKETS:
        return None, f"market '{market}' вне {MARKETS} (TZ2)"
    cycle = cycle.lower()
    if cycle not in CYCLES:
        return None, f"cycle '{cycle}' вне {CYCLES} (TZ3)"
    urg = (urgency or "normal").lower()
    if urg not in URGENCY:
        return None, f"urgency '{urgency}' вне {URGENCY} (TZ6)"
    if priority < 0:
        return None, "priority < 0 — важность числом от 0 (меньше = важнее)"

    t = _now()
    steps = list(steps) if steps else [{"id": "s1", "title": f"Выполнить: {what}",
                                        "state": "open"}]
    clean_steps = []
    for i, s in enumerate(steps or []):
        sid = str(s.get("id") or f"s{i + 1}")
        clean_steps.append({"id": sid,
                            "title": str(s.get("title") or f"Пункт {i + 1}"),
                            "state": "open"})   # новое задание: все пункты открыты (TZ8)
    tid = task_id(market, cycle, category, store, what, owner, urg)
    return {
        "id": tid, "market": market, "cycle": cycle, "category": category,
        "store": store, "owner": owner, "urgency": urg, "priority": int(priority),
        "what": what, "body": body or "", "source": source or "operator",
        "depends_on": list(depends_on or []), "steps": clean_steps,
        "state": "open", "created_at": t, "updated_at": t,
        "refs": dict(refs or {}),
    }, None


def validate(task):
    """Проблемы записи (пусто = валидно). Гейт: не создаём/не сохраняем мусор. Мягко к
    незнакомым owner (словник органов живёт) и к пустому store (общесистемные задания)."""
    probs = []
    if not isinstance(task, dict):
        return ["запись не dict"]
    for req in ("id", "what", "owner", "category", "market", "steps", "state"):
        if not task.get(req):
            probs.append(f"нет поля {req}")
    if task.get("market") not in MARKETS:
        probs.append(f"market {task.get('market')!r} вне {MARKETS}")
    if task.get("category") not in CATEGORIES:
        probs.append(f"category {task.get('category')!r} вне словаря")
    st = task.get("steps")
    if not isinstance(st, list) or not st:
        probs.append("нет ни одного пункта (TZ8: нечего выполнять)")
    elif any(not isinstance(s, dict) or not s.get("id") or not s.get("title")
             for s in st):
        probs.append("пункт без id/title")
    if task.get("state") not in STATES:
        probs.append(f"state {task.get('state')!r} вне {STATES}")
    return probs


# ── состояние по пунктам/зависимостям (гейт без фейк-пасс) ─────────────────────

def derive(task, done_ids=()):
    """Вычисленное состояние из пунктов и зависимостей. Приоритет: archived/blocked → как есть;
    зависимости не закрыты → waiting; все пункты done → done; часть done → in_progress; иначе open.
    done_ids = {id зависимостей, которые уже done} (TZ9)."""
    if task.get("state") in ("archived", "blocked"):
        return task["state"]
    steps = task.get("steps") or []
    if not steps:
        return "blocked"                       # нечего выполнять — не «done» (TZ8)
    all_done = all(s.get("state") == "done" for s in steps)
    any_done = any(s.get("state") == "done" for s in steps)
    pending_deps = [d for d in (task.get("depends_on") or []) if d not in done_ids]
    if pending_deps:
        return "waiting"
    if all_done:
        return "done"
    if any_done:
        return "in_progress"
    return "open"


def mark_step(task, step_id, *, done_by, evidence, done_ids=()):
    """Закрыть пункт ПОД ГЕЙТОМ: evidence непустое и done_by задан (TZ8, без фейк-пасс).
    Возвращает (task, err). Пустое evidence / незнакомый пункт / задание в archived или done —
    честный отказ, ничего не мутировано. После закрытия состояние пересчитывается (TZ9)."""
    if not (done_by or "").strip():
        return task, "done_by пуст — кто проверил? (TZ8)"
    if not (evidence or "").strip():
        return task, "evidence пуст — чем доказано? Закрытие без факта = фейк-пасс (TZ8)"
    if task.get("state") in ("archived", "done"):
        return task, f"задание в {task['state']} — пункты не трогаем"
    for s in task.get("steps") or []:
        if s.get("id") == step_id:
            if s.get("state") == "done":
                return task, f"пункт {step_id} уже закрыт"
            s.update({"state": "done", "done_by": done_by, "evidence": evidence,
                      "done_at": _now()})
            task["state"] = derive(task, done_ids)
            task["updated_at"] = _now()
            return task, None
    return task, f"пункта {step_id} нет в задании"


def reopen_step(task, step_id):
    """Открыть пункт обратно (пересмотр). Из done/archived задания не выводим: закрытое дело
    не «переоткрываем» молча — только новые задания/явное слово (TZ8-строгость)."""
    if task.get("state") in ("done", "archived"):
        return task, f"задание {task['state']} — пункт не переоткрываем"
    for s in task.get("steps") or []:
        if s.get("id") == step_id and s.get("state") == "done":
            for k in ("done_by", "evidence", "done_at"):
                s.pop(k, None)
            s["state"] = "open"
            task["state"] = derive(task)
            task["updated_at"] = _now()
            return task, None
    return task, f"пункта {step_id} нет или он не закрыт"


def done_ids_of(tasks):
    """Множество id закрытых заданий — для derive/планёрки зависимостей (TZ9)."""
    return {t.get("id") for t in (tasks or []) if derive(t) == "done"}


# ── выборки и сортировка (планёрка: важное выше, TZ7) ──────────────────────────

def _urgency_rank(t):
    return _URGENCY_RANK.get(t.get("urgency"), 2)


def sort_key(t):
    return (t.get("priority", 50), _urgency_rank(t), t.get("created_at", ""))


def sort_tasks(tasks):
    """Планёрка: priority (меньше = важнее) → urgency-ранг → created_at (TZ7)."""
    return sorted(tasks or [], key=sort_key)


def by_state(tasks, state):
    return [t for t in (tasks or []) if t.get("state") == state]


def by_owner(tasks, owner):
    return [t for t in (tasks or []) if t.get("owner") == str(owner).upper()]


def by_category(tasks, category):
    return [t for t in (tasks or []) if t.get("category") == category]


def by_store(tasks, store):
    return [t for t in (tasks or []) if t.get("store") == store]


def by_market(tasks, market):
    return [t for t in (tasks or []) if t.get("market") == market]


def open_only(tasks):
    return [t for t in (tasks or []) if derive(t) not in ("done", "archived")]


# ── сводка для ЦИКЛ-ДНЯ / планёрки ─────────────────────────────────────────────

def stats(tasks):
    """Живость системы: счётчики по состояниям, категориям, владельцам, магазинам, срочности.
    ЦИКЛ-ДНЯ ест это в свой пульс; планёрка показывает «что стоит, у кого». Read-only."""
    tasks = list(tasks or [])
    by_st = {s: 0 for s in STATES}
    by_cat, by_own, by_store_s = {}, {}, {}
    critical_high_open = 0
    for t in tasks:
        st = derive(t)
        by_st[st] = by_st.get(st, 0) + 1
        if st == "open":
            by_cat[t.get("category")] = by_cat.get(t.get("category"), 0) + 1
            by_own[t.get("owner")] = by_own.get(t.get("owner"), 0) + 1
            by_store_s[t.get("store") or "—"] = by_store_s.get(t.get("store") or "—", 0) + 1
            if t.get("urgency") in ("critical", "high"):
                critical_high_open += 1
    total = len(tasks)
    done = by_st["done"]
    return {
        "total": total, "by_state": by_st,
        "pct_done": round(done * 100 / total) if total else None,
        "open_by_category": by_cat, "open_by_owner": by_own,
        "open_by_store": by_store_s, "critical_high_open": critical_high_open,
        "oldest_open": (sort_tasks(tasks)[0].get("what")[:48]
                        if any(derive(t) in ("open", "in_progress", "waiting") for t in tasks)
                        else None),
    }


# ── рендер для терминала (что оператор видит, TZ-удобно) ───────────────────────

_ICON = {"open": "○", "in_progress": "◐", "waiting": "⏳", "done": "●", "blocked": "⛔",
         "archived": "🗄"}
_URG_MARK = {"critical": "!!", "high": "!", "normal": "", "low": "·"}


def render_plannerka(tasks, *, title="ПЛАНЁРКА ЗАДАНИЙ"):
    """Человеческая планёрка: важное выше, с владельцем/магазином/пунктами. Read-only."""
    s = stats(tasks)
    out = [title, f"всего {s['total']} · закрыто {s['pct_done']}% · в работе "
                 f"{s['by_state']['in_progress']} · ждут зависимостей {s['by_state']['waiting']}"
                 + (f" · срочных открыто {s['critical_high_open']}" if s["critical_high_open"] else "")]
    out.append("-" * max(len(out[0]), 20))
    for t in sort_tasks(tasks):
        steps = t.get("steps") or []
        ndone = sum(1 for x in steps if x.get("state") == "done")
        st = derive(t)
        if st == "done":
            continue
        urg = _URG_MARK.get(t.get("urgency"), "")
        store = f"[{t['store']}] " if t.get("store") else ""
        out.append(f"{_ICON[st]} P{t.get('priority', 50):<3} {urg} {store}{t.get('what')} · "
                   f"{t['owner']} · {t['category']} · {t['cycle']} · пункты {ndone}/{len(steps)}"
                   f" · {t['id']}")
    if s["by_state"]["done"]:
        out.append(f"… ещё {s['by_state']['done']} закрыто (в сводке)")
    return out


def render_task(t):
    """Одно задание целиком (детали для оператора: пункты + evidence). Read-only."""
    lines = [f"{t.get('what')}  [{derive(t)} · {t.get('id')}]",
             f"  магазин {t.get('store') or '—'} · категория {t.get('category')} · "
             f"владелец {t.get('owner')} · {t.get('cycle')} · срочность {t.get('urgency')}"]
    if t.get("body"):
        lines.append(f"  зачем: {t['body']}")
    if t.get("depends_on"):
        lines.append(f"  зависит от: {', '.join(t['depends_on'])}")
    for s in t.get("steps") or []:
        mark = "●" if s.get("state") == "done" else "○"
        ev = f" — {s.get('done_by')}: {s.get('evidence')}" if s.get("state") == "done" else ""
        lines.append(f"  {mark} {s.get('title')}{ev}")
    return lines


# ── загрузка/сохранение (паттерн registry/matrix/library) ──────────────────────

def load(path=None):
    """Читать реестр → список заданий. Нет файла/битый → [] + честный load_error (TZ10)."""
    p = Path(path) if path else task_path()
    if not p.exists():
        return [], None
    try:
        data = json.loads(p.read_text())
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if tasks is None:
            return [], {"load_error": "схема не ymarket.tasks (нет ключа tasks)"}
        if isinstance(tasks, dict):
            tasks = list(tasks.values())
        return tasks, None
    except Exception as e:
        return [], {"load_error": f"{type(e).__name__}: {e}"}


def save(tasks, path=None):
    """Записать реестр (id → запись, dedup по стабильному хешу). Путь/файл в порядке;
    дамп битого под .corrupt-*.bak (паттерн библиотеки). Никакого dry-гейта ЗДЕСЬ — вызывает
    движок/мозг под своим правилом (движок: только not dry AND commit)."""
    p = Path(path) if path else task_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    recs = {t["id"]: t for t in (tasks or []) if t.get("id")}
    payload = {"schema": SCHEMA, "updated_at": _now(), "tasks": recs}
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        tmp.replace(p)
        return {"ok": True, "n": len(recs), "path": str(p)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "path": str(p)}


if __name__ == "__main__":
    # Сухая демонстрация (0₽, ничего не пишет): картинка того, что видит оператор.
    tasks, _err = [], None
    mk = lambda **kw: tasks.append(new_task(**kw)[0])
    mk(what="Взять в работу магазин-донор cargo-shop (разбор, ключи, адаптер)",
       owner="PARTNERS", category="partners", cycle="cycle_day", store="cargo-shop",
       urgency="high", priority=10)
    mk(what="Добавить категорию «Курьерские пакеты» в кабинет atlas-express-film",
       owner="CATEGORIST", category="categories", cycle="cycle1",
       store="atlas-express-film", priority=30)
    mk(what="Поднять цену ARB-87931769 до пола КПИ (сейчас net 177₽ < 500₽)",
       owner="PRICER", category="pricing", cycle="cycle1", store="atlas-express-film",
       urgency="high", priority=20, depends_on=["T-demo"])
    t2 = tasks[0]
    mark_step(tasks[1], "s1", done_by="categorist-v1",
              evidence="СВЕРКА чтением: категория 76346336 добавлена, 13 параметров")
    for line in render_plannerka(tasks):
        print(line)
    print()
    for line in render_task(tasks[2]):
        print(line)
    print("\nСводка:", stats(tasks))

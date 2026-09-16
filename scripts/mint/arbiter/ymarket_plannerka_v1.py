#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПЛАНЁРКА (УТРО) — ymarket_plannerka_v1: первый слой машины ПЛАНЁРКА→ЗАДАНИЯ→ИСПОЛНЕНИЕ.

ЗАЧЕМ (директива оператора 04.09 «ЦИКЛ ДНЯ НЕ ПЛАНЕРКА»). Планёрка всегда ПРЕЖДЕ любых работ,
любых циклов: там определяется ОБЪЁМ работы, какие и где, и почему. Потом составляются ЗАДАНИЯ —
затем ИСПОЛНЕНИЕ. До этого дня система НЕ начиналась с плана: суточный цикл был доклад-состояние,
а задания сеялись авто-наблюдением мимо явного решения «что берём и почему». Этот модуль = движок
«утреннего решения»: читает реальные сторы → строит КОНТЕКСТ ДНЯ без выдумки → предлагает РЕШЕНИЯ
(что/где/почему/кто) → готов интэйк решения в ЗАДАНИЯ реестра (недостающее звено карты) → кладёт
durable ПЛАН ДНЯ. Исполнение (органы берут задания плана и работают — система жива, может делать
живые акты) — следующий слой по слову оператора.

ФОРМАТ по канону YM_CYCLE1_V1.md §6 «Планёрка (утро)»: 1) контекст дня, 2) решения что берём и
почему, 3) задания с владельцем-органом, 4) артефакты. Роль АНАЛИТИК (:73) — контекст→осмысленные
задания. Здесь контекст ФАКТИЧЕСКИЙ: погода/новости/тренды НЕ подключены (честный ноль, не выдумка).

ИСТОЧНИКИ (все — реальные сторы на диске, читаются; ничего не выдумываем):
  реестр заданий   ymarket_tasks.json        (ymarket_tasks_v1: load/stats/open_only/new_task)
  досье категорий  ymarket_categorist_dossiers.json (что готово/ждёт/нужен маппинг/решение)
  леджер ЦИКЛ-1    ymarket_goods_library.json (доказанно живых — СВЕРКА PASS, proof_cross)
  журнал суточного ymarket_day_journal.jsonl  (последний день: burning/urgent_orders/top_move)
  env-переопределения YM_TASKS_PATH/YM_DAY_JOURNAL/YM_LIBRARY_PATH/YM_PLAN_DIR — герметичные
  приёмки пишут/читают только песочницу; реальный диск не трогаем.

РУБИКОН. Движок сам НАРУЖУ не пишет: save плана и интэйк новых заданий — ТОЛЬКО под commit=True,
который даёт вызывающий по своему правилу (мозг/ДОМ/оператор). Dry (по умолчанию) показывает, ЧТО
планёрка решила бы. Живые акты (залив/цены) в плане помечены mode и НЕ исполняются этим модулем —
они исполняются органами в слое ИСПОЛНЕНИЯ.

ЗАКОНЫ (герметика + анти-вралье):
  PL1 контекст без выдумки: каждое утверждение несёт источник (реестр/досье/леджер/журнал);
      внешние контексты (погода/новости/тренды) честно «не подключены», а не выдуманы.
  PL2 «живо» только доказанное: витрина = СВЕРКА PASS из леджера (200 OK врёт), через proof_cross.
  PL3 escalation ≠ задание: решения, требующие слова оператора (маппинг категории, живая цена,
      первый живой залив), — отдельный список, НЕ превращаются в авто-задания органа.
  PL4 интэйк по TZ1: новые задания рождаются только через tasks_v1.new_task и дедупятся по
      стабильному id намерения; одно и то же решение дважды в реестр не пишет.
  PL5 dry ничего не пишет; commit пишет план И (если принят) новые задания — локальный диск,
      наружу не идёт.
  PL6 рендер никогда не врёт молчанием: «0 заказов» — это «на диске ничего горящего», а не
      «заказов нет вообще» (живой срез читается в ИСПОЛНЕНИИ).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ymarket_tasks_v1 as T                       # noqa: E402
import ymarket_proof_cross_v1 as X                 # noqa: E402
import ymarket_categorist_dossiers_v1 as D         # noqa: E402

SCHEMA = "ymarket.plan.v1"
KINDS = ("carry", "new", "escalation", "watch")    # carry=уже в реестре, new=новое задание,
#                                                  # escalation=нужно слово оператора, watch=наблюдаем


# ── пути/стор ───────────────────────────────────────────────────────────────────

def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _today():
    return time.strftime("%Y-%m-%d")


def plan_dir():
    """Каталог планов дня. env YM_PLAN_DIR перекрывает (песочница/тесты)."""
    p = os.environ.get("YM_PLAN_DIR")
    if p:
        return Path(p)
    return T.REPORTS / "plans"


def plan_path(date_str=None):
    """План дня — один файл на дату: plans/ymarket_plan_<дата>.json."""
    date_str = date_str or _today()
    return plan_dir() / f"ymarket_plan_{date_str}.json"


# ── читатели входов (чистые; doc дан → герметично, диск не трогаем) ─────────────

def read_registry(tasks_doc=None):
    """Открытые задания реестра + сводка. tasks_doc — список записей (герметично) или None → T.load().
    Возвращает (tasks_open, stats_dict, load_err|None). Битый/нет реестра — честный [], а не паника."""
    if tasks_doc is not None:
        tasks, err = tasks_doc, None
    else:
        tasks, err = T.load()
    tasks = tasks or []
    open_t = T.open_only(tasks)
    return open_t, T.stats(tasks), (err or {}).get("load_error") if err else None


def read_dossiers(dossiers_doc=None):
    """Состояние очереди категорий КАТЕГОРИЙЩИКА: готово/ждёт данных/ждёт слова. Вернёт list записей:
    [{slug, state, priority, task_id, ready(int), need_mapping(bool), market_category_id, verdict,
      when, ood(str)}]. readiness.ready — сколько SKU реально готово (0 — честный ноль)."""
    if dossiers_doc is not None:
        doc, err = dossiers_doc, None
    else:
        doc, err = D.load()
    cats = doc.get("categories", {}) if isinstance(doc, dict) else {}
    out = []
    for slug, e in cats.items():
        if not isinstance(e, dict):
            continue
        sc = e.get("scan") or {}
        rd = sc.get("readiness") or {} if isinstance(sc, dict) else {}
        m = e.get("mapping") or {}
        ready = rd.get("ready")
        if ready is None:
            # фолбэк на длину шорт-листа (list) / число — но не выдумываем: нет → 0
            sl = sc.get("shortlist") if isinstance(sc, dict) else None
            ready = len(sl) if isinstance(sl, (list, dict)) else (sl if isinstance(sl, int) else 0)
        out.append({
            "slug": slug,
            "state": e.get("state"),
            "priority": e.get("priority"),
            "task_id": e.get("task_id"),
            "ready": ready if isinstance(ready, int) else 0,
            "need_mapping": bool((m or {}).get("need_mapping")),
            "market_category_id": (m or {}).get("market_category_id"),
            "verdict": sc.get("verdict") if isinstance(sc, dict) else None,
            "when": sc.get("when") if isinstance(sc, dict) else None,
            "ood": e.get("open_operator_decision") or "",
        })
    # dossiers.load отдаёт err строкой (не dict) — нормализуем в единый {load_error}
    if isinstance(err, dict):
        load_err = err.get("load_error")
    elif err:
        load_err = err
    else:
        load_err = None
    return out, load_err


def read_vitrine(library_doc=None):
    """Доказанно живых по леджеру ЦИКЛ-1 (СВЕРКА PASS, proof_cross PL2) — по кабинету и категории.
    Возвращает {by_store: {slug: n}, by_category: {cat: n}, total, load_err|None}."""
    pass_g, doc = X.pass_goods(library_doc)
    by_cat, by_store = {}, {}
    for g in pass_g:
        c = g.get("category_slug") or "?"
        s = g.get("store_slug") or "?"
        by_cat[c] = by_cat.get(c, 0) + 1
        by_store[s] = by_store.get(s, 0) + 1
    return {"by_store": by_store, "by_category": by_cat, "total": len(pass_g),
            "load_err": doc.get("load_error") if isinstance(doc, dict) else None}


def read_journal(journal_rows=None):
    """Последняя строка журнала суточного: заказы-горящие + итог вчера. journal_rows дан → герметично.
    Нет строк/бито → честно {} (ничего не выдумываем). «0 заказов» здесь = «на диске ничего
    горящего», НЕ «заказов нет вообще» (PL6 — живой срез читается в исполнении ДИСПЕТЧЕРОМ)."""
    if journal_rows is None:
        p = X.journal_path()
        rows = []
        if p.exists():
            for ln in p.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    o = json.loads(ln)
                except Exception:
                    continue
                if isinstance(o, dict):
                    rows.append(o)
    else:
        rows = journal_rows or []
    if not rows:
        return {}
    last = rows[-1]
    k = last.get("kpis") or {}
    return {"date": last.get("date"), "urgent_orders": k.get("urgent_orders"),
            "burning": last.get("burning"), "top_move": last.get("top_move")}


# ── контекст дня (фактические строки с источником, PL1) ─────────────────────────

def context_of(*, date_str=None, registry=None, dossiers=None, vitrine=None, journal=None,
               store=None):
    """Список фактов дня. Каждый факт = (метка, строка). Метки: ВИТРИНА/ОЧЕРЕДЬ/ЗАДАНИЯ/ЗАКАЗЫ/
    ИТОГ. registry = (open_tasks, stats_dict, load_err|None). Внешние контексты
    (погода/новости/тренды/сезон) честно помечаются НЕ-подключено."""
    date_str = date_str or _today()
    lines = []
    v = vitrine or {}
    if v.get("load_err"):
        lines.append(("ВИТРИНА", f"не читается леджер ЦИКЛ-1 ({v['load_err']}) — «живого» не считаем"))
    elif v.get("total"):
        cats = ", ".join(f"{c}×{n}" for c, n in sorted(v.get("by_category", {}).items()))
        lines.append(("ВИТРИНА", f"доказанно живых {v['total']} ({cats}) — источник леджер ЦИКЛ-1, СВЕРКА PASS"))
    else:
        lines.append(("ВИТРИНА", "доказанно живых 0 — леджер ЦИКЛ-1 пуст (честно, не выдумка)"))

    dj = dossiers or []
    ready = [d for d in dj if d.get("ready", 0) > 0]
    wait_data = [d for d in dj if d.get("verdict") in ("needs_data", "empty_negative")]
    unscanned = [d for d in dj if not d.get("when")]
    need_word = [d for d in dj if d.get("need_mapping") and not d.get("market_category_id")]
    if not dj:
        lines.append(("ОЧЕРЕДЬ", "досье категорий не читается/пусто"))
    else:
        lines.append(("ОЧЕРЕДЬ", f"категорий в очереди {len(dj)} · готово к заливу {len(ready)} "
                                 f"({sum(d['ready'] for d in ready)} SKU) · ждут данных/ОВХ {len(wait_data)} "
                                 f"· не сканированы {len(unscanned)}"))
        for d in ready:
            store_s = f" в {store}" if store else ""
            lines.append(("ОЧЕРЕДЬ", f"  ГОТОВО: {d['slug']} — {d['ready']} SKU{store_s} "
                                     f"(досье {d.get('verdict')})"))
        if need_word:
            lines.append(("ОЧЕРЕДЬ", f"  ждёт СЛОВА оператора (профиль ЯМ-категории не подтверждён): "
                                     f"{len(need_word)} — маппинг-бутылочное горлышко (lessons.mapping-is-bottleneck)"))

    o, st, reg_err = (registry or (None, None, None))
    if reg_err:
        lines.append(("ЗАДАНИЯ", f"реестр не читается ({reg_err}) — открытых не считаем"))
    elif o is None:
        lines.append(("ЗАДАНИЯ", "реестр заданий не читается"))
    else:
        own = st.get("open_by_owner", {}) or {}
        own_s = ", ".join(f"{k}={n}" for k, n in sorted(own.items(), key=lambda x: -x[1]))
        lines.append(("ЗАДАНИЯ", f"открыто заданий {len(o)} · владельцы: {own_s or '—'}"))

    j = journal or {}
    if not j:
        lines.append(("ЗАКАЗЫ", "журнал суточного пуст — свежих данных заказов на диске нет"))
    else:
        u = j.get("urgent_orders")
        lines.append(("ЗАКАЗЫ", f"журнал {j.get('date')}: горящих заказов {u} · burning {j.get('burning')} "
                                f"· движение {j.get('top_move')} — живой срез читается ДИСПЕТЧЕРОМ в исполнении, "
                                f"не выдумываем"))
    lines.append(("КОНТЕКСТ", "погода/новости/тренды/сезон: НЕ подключены (источник не задан) — "
                              "осмысленные сезонные охоты АНАЛИТИК даст, когда будет источник"))
    return lines


# ── решения плана (детерминированная политика поверх фактов, PL3/PL4) ──────────

def propose(*, date_str=None, registry=None, dossiers=None, vitrine=None, journal=None,
            store=None):
    """Предложения ПЛАНА ДНЯ по фактам (dry, ничего не пишет). Каждое решение:
    {id, kind, what, where, owner, category, urgency, priority, why, evidence, mode, refs}.
    kind: carry (уже открыто в реестре) | new (новое задание органа) | escalation (нужно слово
    оператора) | watch (наблюдаем, действия нет). Почему-на-каждый-выбор — канон §6."""
    date_str = date_str or _today()
    dec = []

    # 1) что УЖЕ открыто в реестре — несём в план как carry; живое/сухое различаем по владельцу
    open_t, _st, _err = read_registry(registry)
    for t in sorted(open_t, key=T.sort_key):
        owner = t.get("owner", "?")
        live_owner = owner in ("PRICER",)                 # живая переценка цены наружу
        dec.append({
            "id": "carry-" + t.get("id", "?"), "kind": "carry",
            "what": t.get("what"), "where": t.get("store") or store or "—",
            "owner": owner, "category": t.get("category"), "urgency": t.get("urgency"),
            "priority": t.get("priority", 50),
            "why": ("уже в реестре, владелец-орган есть; исполнение за органом"
                    + (" — живой акт цены наружу, по слову оператора" if live_owner
                       else " — сухо/0₽ автономно")),
            "evidence": f"реестр ymarket_tasks.json · {t.get('id')}",
            "mode": "live" if live_owner else "dry", "refs": {"task_id": t.get("id")},
        })

    # 2) очередь категорий: готовые к заливу / ждут данных / не сканированы
    for d in (dossiers or []):
        slug = d.get("slug")
        if d.get("need_mapping") and not d.get("market_category_id"):
            dec.append({
                "id": f"esc-map-{slug}", "kind": "escalation",
                "what": f"подтвердить профиль ЯМ-категории для «{slug}» (маппинг)",
                "where": store or d.get("store", "—"), "owner": "OPERATOR",
                "category": "categories", "urgency": "normal", "priority": d.get("priority", 50),
                "why": "без market_category_id категорию в карточку не поставить — бутылочное "
                       "горлышко всей очереди (маппинг решает человек, не орган)",
                "evidence": "досье категорий · mapping.need_mapping=true",
                "mode": "read", "refs": {"dossier_slug": slug, "task_id": d.get("task_id")},
            })
        elif d.get("ready", 0) > 0:
            dec.append({
                "id": f"watch-ready-{slug}", "kind": "watch",
                "what": f"партия «{slug}» готова ({d['ready']} SKU) — залив на витрину",
                "where": store or d.get("store", "—"), "owner": "CATEGORIST",
                "category": "categories", "urgency": "normal", "priority": d.get("priority", 50),
                "why": "шорт-лист собран, но живой залив = акт наружу; в план ставим как цель "
                       "дня, запуск — за словом оператора (и после Фото-узла, см. досье)",
                "evidence": f"досье · verdict={d.get('verdict')} ready={d['ready']}",
                "mode": "live", "refs": {"dossier_slug": slug, "task_id": d.get("task_id")},
            })
        elif not d.get("when"):
            # не сканирована категория — если в реестре уже есть открытый парсинг, его нёс carry (п.1)
            dec.append({
                "id": f"watch-unscanned-{slug}", "kind": "watch",
                "what": f"категория «{slug}» ещё не сканирована КАТЕГОРИЙЩИКОМ",
                "where": store or d.get("store", "—"), "owner": "CATEGORIST",
                "category": "categories", "urgency": "low", "priority": 60,
                "why": "в очереди, но скана не было; парсинг сухой 0₽ — возьмёт при наличии "
                       "открытого задания (carry) либо по решению дня",
                "evidence": "досье · scan пуст", "mode": "dry",
                "refs": {"dossier_slug": slug, "task_id": d.get("task_id")},
            })

    # 3) заказы: журнал ничего горящего не показывает — watch (PL6), а не выдуманный «в работу»
    j = journal or {}
    if j.get("urgent_orders"):
        dec.append({
            "id": "carry-orders", "kind": "carry",
            "what": f"ночные заказы в работе: горит {j['urgent_orders']}",
            "where": store or "—", "owner": "DISPATCHER", "category": "day",
            "urgency": "high", "priority": 5,
            "why": "заказы с ночи = сразу в работу, обязаловка (оператор); горит по журналу",
            "evidence": f"журнал суточного {j.get('date')} · urgent_orders", "mode": "live",
            "refs": {},
        })
    else:
        dec.append({
            "id": "watch-orders", "kind": "watch",
            "what": "ночных горящих заказов на диске нет",
            "where": store or "—", "owner": "DISPATCHER", "category": "day",
            "urgency": "normal", "priority": 60,
            "why": "журнал суточного не рисует горящих; живой срез ДИСПЕТЧЕР прочитает при "
                   "исполнении дня (0₽ read) — здесь не выдумываем",
            "evidence": "журнал суточного · urgent_orders=0", "mode": "read", "refs": {},
        })
    return dec


# ── ПЛАН ДНЯ: собрать doc, рендер, стор (PL5) ──────────────────────────────────

def build_plan(*, date_str=None, store=None, registry=None, dossiers=None, vitrine=None,
               journal=None, decisions=None):
    """Собрать doc ПЛАНА ДНЯ (schema ymarket.plan.v1). Ничего не пишет. decisions не дан → propose().

    Контракт входов (для герметики и провязки): каждый = «сырой» вход читателя; None → реальный
    стор на диске:
      registry  полный СПИСОК заданий (doc T.load) | None → реальный реестр;
      dossiers  DOC досье {"categories": {...}} | None → реальный каталог;
      vitrine   DOC леджера {"goods": {...}}       | None → реальный goods_library;
      journal   СПИСОК строк журнала | None        → реальный day_journal.
    Возвращает doc плана: context (метки-источники), decisions (carry/new/escalation/watch),
    sources. Dry: сам ничего не пишет; сохранение/интэйк — save_plan/seed_from_plan под commit."""
    date_str = date_str or _today()
    v = read_vitrine(vitrine)                     # doc {"goods":…}|None (None → реальный леджер)
    d, _de = read_dossiers(dossiers)              # doc {"categories":…}|None → записи очереди
    full = registry if registry is not None else (T.load()[0] or [])   # полный список (для propose)
    o, st, reg_err = read_registry(full)
    j = read_journal(journal)                     # list строк журнала | None (None → реальный)
    ctx = context_of(date_str=date_str, registry=(o, st, reg_err), dossiers=d, vitrine=v,
                     journal=j, store=store)
    dec = decisions if decisions is not None else propose(
        date_str=date_str, registry=full, dossiers=d, vitrine=v, journal=j, store=store)
    return {
        "schema": SCHEMA, "date": date_str, "store": store or "",
        "generated_at": _now_iso(),
        "context": [{"tag": tg, "text": tx} for tg, tx in ctx],
        "decisions": dec,
        "sources": {
            "registry_open": len(o),
            "vitrine_live": v.get("total", 0),
            "dossiers": len(d),
            "journal": (j or {}).get("date"),
        },
    }


def render_plan(plan):
    """Человеческий «ПЛАН ДНЯ» (read, то, что увидит оператор). КПИ «всё схвачено» канона §6."""
    date = plan.get("date", "?")
    out = [f"ПЛАН ДНЯ · {date} · {plan.get('store') or 'ЯМ'}", "-" * 40]
    if not plan.get("context"):
        out.append("контекст пуст — входы не читаются")
    else:
        cur = None
        for row in plan["context"]:
            if row["tag"] != cur:
                cur = row["tag"]
                out.append(f"  [{cur}]")
            out.append(f"    {row['text']}")
    dec = plan.get("decisions", [])
    by_kind = {"carry": [], "new": [], "escalation": [], "watch": []}
    for x in dec:
        by_kind.setdefault(x.get("kind"), []).append(x)
    out.append(f"РЕШЕНИЯ · carry {len(by_kind['carry'])} · new {len(by_kind['new'])} · "
               f"нужно слово {len(by_kind['escalation'])} · watch {len(by_kind['watch'])}")
    order = [("carry", "В РАБОТЕ (уже в реестре — за органом)"),
             ("new", "НОВЫЕ ЗАДАНИЯ (планёрка порождает)"),
             ("escalation", "НУЖНО СЛОВО ОПЕРАТОРА (не авто-задания)"),
             ("watch", "НАБЛЮДАЕМ (цель/честный ноль)")]
    for kind, head in order:
        items = by_kind[kind]
        if not items:
            continue
        out.append(f"  ● {head}:")
        for x in items:
            ev = x.get("evidence", "")
            out.append(f"    · P{x.get('priority', 50):<3} [{x.get('mode')}] {x.get('what')} · "
                       f"{x.get('owner')} · {x.get('category')}")
            if x.get("why"):
                out.append(f"        почему: {x['why']}")
            if ev:
                out.append(f"        факт: {ev}")
    return out


# ── интэйк: решения плана → задания реестра (PL4) ──────────────────────────────

def seed_from_plan(plan, *, commit=False, save_path=None, existing=None):
    """Интэйк РЕШЕНИЙ плана в ЗАДАНИЯ: только kind=new с органом-владельцем; через T.new_task
    (обязательны what/owner/category), дедуп по TZ1-ид. Возвращает (summary, lines).
    commit=False: показывает, ЧТО создалось бы. commit=True: единственный write — локальный реестр
    (PL5). existing дан → герметично сравниваем с ним (иначе реальный T.load); save_path дан →
    туда пишем. Новые решения «как залить 8 категорий» без donor-источника не выдумываются — их
    нет в decide (это escalation/оператор), поэтому интэйк честно создаёт только то, что решено."""
    lines = []
    made, skipped = [], []
    if existing is not None:
        existing_tasks, _err = list(existing), None
    else:
        existing_tasks, _err = T.load()
    for x in plan.get("decisions", []):
        if x.get("kind") != "new":
            continue
        owner = (x.get("owner") or "").upper()
        cat = (x.get("category") or "").lower()
        if not owner or cat not in T.CATEGORIES:
            skipped.append({"id": x.get("id"), "reason": f"не порождает задание (owner={owner}, "
                                                         f"cat={cat}) — скорее escalation"})
            continue
        task, err = T.new_task(what=x.get("what"), owner=owner, category=cat,
                               cycle="cycle_day", store=x.get("where") or plan.get("store") or "",
                               urgency=x.get("urgency"), priority=x.get("priority", 50),
                               body=x.get("why"), source="plannerka", refs=x.get("refs") or {})
        if err:
            skipped.append({"id": x.get("id"), "reason": err})
            continue
        dup = any(et.get("id") == task["id"] for et in existing_tasks)
        if dup:
            skipped.append({"id": x.get("id"), "reason": "уже в реестре (TZ1-дедуп)",
                            "task_id": task["id"]})
            continue
        made.append(task)
    if commit and made:
        save_res = T.save(existing_tasks + made, path=save_path)
        lines.append(f"интэйк: записано {len(made)} заданий · {save_res}")
    elif made:
        lines.append(f"интэйк (dry, не записано): создалось бы {len(made)} заданий:")
        for m in made:
            lines.append(f"  · {m['id']} {m['what']} → {m['owner']}")
    if skipped:
        lines.append(f"пропущено {len(skipped)} (дубли/не-задание):")
        for s in skipped:
            lines.append(f"  · {s.get('id')}: {s.get('reason')}")
    return {"made": len(made), "skipped": len(skipped), "commit": bool(commit)}, lines


def save_plan(plan, *, commit=False, path=None):
    """Сохранить ПЛАН ДНЯ в локальный стор. commit=False → ничего не пишет (dry). Возвращает dict."""
    if not commit:
        return {"ok": True, "dry": True, "n": len(plan.get("decisions", [])),
                "path": str(plan_path(plan.get("date")))}
    p = Path(path) if path else plan_path(plan.get("date"))
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=1))
        tmp.replace(p)
        return {"ok": True, "dry": False, "n": len(plan.get("decisions", [])), "path": str(p)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def load_plan(date_str=None, path=None):
    """Читать план дня. Нет/битый → (None, честный load_error)."""
    p = Path(path) if path else plan_path(date_str)
    if not p.exists():
        return None, None
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except Exception as e:
        return None, {"load_error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ПЛАНЁРКА (УТРО): собрать ПЛАН ДНЯ из реальных сторов (0₽)")
    ap.add_argument("--date", default=None, help="дата плана (по умолчанию сегодня)")
    ap.add_argument("--store", default=None, help="магазин-кабинет (по умолчанию — из сторов)")
    ap.add_argument("--commit", action="store_true", help="записать план (локально) — по умолчанию dry")
    a = ap.parse_args()
    if a.date:
        # запрет на живьё/написание чужой даты без слова — только dry-снимок допускает прошлое
        plan = build_plan(date_str=a.date, store=a.store)
        for ln in render_plan(plan):
            print(ln)
        if a.commit:
            print("\n" + str(save_plan(plan, commit=True)))
        raise SystemExit(0)
    # реальный снимок сегодня: сухо, диск только читается
    _plan = build_plan(store=a.store)
    for _ln in render_plan(_plan):
        print(_ln)
    print("\n(снимок read-only; planёрka решает — исполнение за органами по слову)")
    raise SystemExit(0)

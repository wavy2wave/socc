#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЦИКЛ-ДНЯ (ymarket_cycle_day_v1) — диспетчер над РЕЕСТРОМ ЗАДАНИЙ ymarket_tasks_v1.

ЗАЧЕМ (директива оператора 2026-09-02, ЯМ ЦИКЛ): утро начинается планёркой — сколько магазинов,
% закрыто по каждому, какие задания открыты и КТО ответственный; диспетчер берёт открытые задания
по важности, инициирует сухой прогон ЦИКЛА-1 по магазину, а пункты закрывает только тот орган,
который РЕАЛЬНО проверил (без фейк-пасс). Терминал ЯМ-ЦИКЛ = этот модуль: магазины+задания+кто.

ЧТО ЕСТЬ ВОКРУГ (не дублируем, а ссылаемся):
  ymarket_tasks_v1    — РЕЕСТР: запись задания (id-хеш намерения, владелец-«удавка», категория,
                        приоритет, пункты под гейтом evidence, state open→…→done). ЭТО источник.
  ymarket_cycle1_v1   — движок ЦИКЛА-1: run_cycle(dry=True) сухой прогон по магазину (0₽);
                        plannerka_read(store) = пульс магазина; list_cycles() = манифест.
  ymarket_pricing_plan_v1 — ЦЕНОВИК·ПЛАН: чистая математика переценки (план карточек, вердикты
                        RAISE/SWEET/SET/OK делегированы price_rules) — форма для PRICER-заданий.
  ymarket_brain_v1    — УПРАВЛЯЮЩИЙ-МОЗГ: [ДЕЙСТВИЕ] tasks → вызывает ЭТОТ модуль (read).
  team_feed/kpi/day   — события/метрики/отчёты; задания — НЕ их. (см. YM_TASKS_V1.md §5)

ЗАКОНЫ (механические, покрыты приёмкой run_cycle_day):
  CD1  сухо: без --commit и --cycle-dry ничего не пишет и наружу не ходит; пульс = 0₽ чтение.
  CD2  формирование из ЖИВЫХ наблюдений: каждый сканер отдаёт наблюдение с evidence = артефакт
       (ледужер/манифест/артефакт закупки), а не выдумка; голое наблюдение без артефакта не идёт.
  CD3  TZ1-дедуп: то же намерение (что+владелец+категория+…) → тот же id; --commit обновляет,
       не плодит дубль (форма идемпотентна — повторный прогон новых не добавит).
  CD4  планёрка ОДИН глобальный блок ЗАДАНИЙ (не по одному на магазин): пульсы магазинов +
       один блок открытых заданий по важности; различает «реестра нет» от «0 открытых».
  CD5  диспетчер без фейк-пасс: сухой подхват ЦИКЛА-1 (run_cycle dry=True) — ТОЛЬКО с явным
       --cycle-dry; никогда сам не mark_step; «исполнителя нет» у органа без исполнителя здесь.
  CD6  единственный write этого модуля — локальный реестр (form --commit, НЕ сеть, RUBICON цел).
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

ARB = Path(__file__).resolve().parent
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

try:
    import ymarket_tasks_v1 as T          # реестр заданий (id/владелец/пункты/гейт evidence)
except Exception as _e:
    T = None
try:
    import ymarket_cycle1_v1 as cycle1    # движок ЦИКЛА-1 (run_cycle dry / plannerka_read)
except Exception as _e:
    cycle1 = None
try:
    import ymarket_pricing_plan_v1 as PP  # ЦЕНОВИК·ПЛАН (план переценки для PRICER-заданий)
except Exception as _e:
    PP = None

STORE_DEFAULT = (getattr(cycle1, "STORE_DEFAULT", "atlas-express-film")
                 if cycle1 else "atlas-express-film")

# ── артефакты (источники наблюдений, CD2) ─────────────────────────────────────
_RUNTIME = ARB / "runtime" / "cycle1"
COSTS_PATH = _RUNTIME / "_card_costs.json"      # закупки донора по ARB-карточкам (живой скан)


def _now_date():
    return datetime.date.today().isoformat()


def load_costs():
    """Закупки донора по offer_id: {offer_id: {cost, evidence}}. Нет файла/битый → {}+None."""
    if not COSTS_PATH.exists():
        return {}, None
    try:
        d = json.loads(COSTS_PATH.read_text())
        cards = d.get("cards") or {}
        return cards, None
    except Exception as e:
        return {}, {"load_error": f"{type(e).__name__}: {e}"}


# ── витрина из ЛЕДЖЕРА (не демо-массив pricing_plan, CD2) ─────────────────────

_PRICE = re.compile(r"(ARB-\d+)\b")
_RUB = re.compile(r"(\d+)\s*₽")


def vitrina_from_ledger(store, date_str=None):
    """{offer_id: цена} с ПОСЛЕДНЕГО ЗАЛИВА за дату (витринные цены карточек партии).

    Леджер — факт прогона (ЗАЛИВ несёт контент: «ARB-… vБез бренда desc=… 5600₽»). Читаем
    ТОЛЬКО строки node=ЗАЛИВ и берём последний. Нет леджера/нет заливов → {} (честно).
    """
    date_str = date_str or _now_date()
    p = _RUNTIME / store / f"{date_str}.jsonl"
    if not p.exists():
        return {}
    last_note = None
    try:
        for ln in p.read_text().splitlines():
            d = json.loads(ln)
            if d.get("node") == "ЗАЛИВ" and d.get("note"):
                last_note = d["note"]
    except Exception:
        return {}
    if not last_note:
        return {}
    out = {}
    for chunk in str(last_note).split(";"):
        oid = _PRICE.search(chunk)
        price = _RUB.search(chunk)
        if oid and price:
            out[oid.group(1)] = float(price.group(1))
    return out


# ── наблюдения-сканеры (что видим по артефактам → что сформировать) ───────────

def _obs_task(what, owner, category, *, priority, urgency="normal", body="",
              store="", cycle="cycle1", evidence="", source="cycle_day"):
    """Одно наблюдение = кандидат задания. evidence НЕ пусто (CD2): без факта не формируем."""
    if not evidence:
        return None
    steps = [{"id": "s1", "title": f"Выполнить: {what}"}]
    return dict(what=what, owner=owner, category=category, priority=priority,
                urgency=urgency, body=body, store=store, cycle=cycle,
                source=source, steps=steps, refs={"evidence": evidence})


def scan_stores():
    """Магазины манифеста: пульс есть/нет, вердикты. Наблюдения о здоровье пульса (CD2)."""
    out = []
    if cycle1 is None:
        return out
    reg = cycle1.list_cycles()
    for slug, inf in sorted((reg or {}).items()):
        try:
            p = cycle1.plannerka_read(slug)
        except Exception:
            p = None
        today = _now_date()
        if not p:
            out.append(_obs_task(
                f"Собрать первый пульс магазина {slug} (прогнать ЦИКЛ-1 сухо)",
                "DISPATCHER", "health", priority=50, urgency="normal", store=slug,
                cycle="cycle1",
                evidence=f"манифест {slug}: пульса нет ({inf.get('builder')})",
                body="Новый магазин без первого прогона — пульс соберёт run_cycle(dry=True) 0₽."))
        elif p.get("date") != today:
            out.append(_obs_task(
                f"Пульс {slug} устарел ({p.get('date')}) — прогнать сухо сегодня",
                "DISPATCHER", "health", priority=40, urgency="normal", store=slug,
                cycle="cycle1",
                evidence=f"пульс {slug}: дата {p.get('date')} ≠ сегодня {today}",
                body="Дневной цикл не гонялся сегодня — сухой прогон обновит вердикты."))
    return [o for o in out if o]


def scan_pricing(store=None, date_str=None):
    """Цены вне зоны/пола по КАРТОЧКЕ (CD2): закупка=артефакт _card_costs.json,
    витрина=леджер ЗАЛИВ → ЦЕНОВИК·ПЛАН решает (одна правда). RAISE/SWEET/ZONE_RAISE → задание."""
    out = []
    if PP is None or not COSTS_PATH.exists():
        return out
    costs, err = load_costs()
    if err or not costs:
        return out
    store = store or STORE_DEFAULT
    vitrina = vitrina_from_ledger(store, date_str) or {}
    cards = []
    for oid, c in (costs or {}).items():
        cost = c.get("cost")
        price = vitrina.get(oid)
        if cost is not None and price is not None:
            cards.append({"offer_id": oid, "cost": float(cost), "price": float(price)})
    if not cards:
        return out
    rows = [r for r in PP.plan_cards(cards) if r.get("verdict") in ("RAISE", "SWEET", "ZONE_RAISE")]
    for r in sorted(rows, key=lambda x: (x.get("cost") or 0)):
        oid = r.get("offer_id")
        cost = r.get("cost")
        price = r.get("price")
        rec = r.get("recommended")
        verdict = r.get("verdict")
        note = r.get("note") or ""
        prov = " (проект: доставка/комиссия не подтверждены)" if r.get("provisional") else ""
        out.append(_obs_task(
            f"Переценка {oid}: {verdict} — витрина {price:g}₽ → рекомендую {rec:g}₽"
            if rec else f"Переценка {oid}: {verdict} — витрина {price:g}₽",
            "PRICER", "pricing",
            priority=10 if verdict == "RAISE" else 20,
            urgency="high" if verdict == "RAISE" else "normal",
            store=store, cycle="cycle1",
            evidence=f"закупка {cost:g}₽ (_card_costs) · витрина {price:g}₽ (леджер ЗАЛИВ) · "
                     f"вердикт {verdict} · {note}{prov}",
            body=f"ЦЕНОВИК·ПЛАН: карточка {oid} за пределами зоны/пола КПИ. План готовит "
                 f"pricing_plan_v1; цены движок сам не трогает — ждёт слова оператора."))
    return [o for o in out if o]


def scan_ledgers():
    """Последний ход леджера каждого магазина: если ОН FAIL → здоровье-задание (CD2).

    Якорь НА ПОСЛЕДНЕЙ строке (последний прогон дня), не на любом FAIL днём: стейл-фейл
    после зелёных прогонов задания не порождает (честно по последнему вердикту — правило
    «не сеем СТОКМЕН из устаревшего FAIL», 2026-09-02 verify-гейт)."""
    out = []
    if cycle1 is None:
        return out
    for slug in sorted((cycle1.list_cycles() or {}).keys()):
        try:
            p = cycle1.plannerka_read(slug)
        except Exception:
            p = None
        date_str = (p or {}).get("date")
        if not date_str:
            continue
        ledger = _RUNTIME / slug / f"{date_str}.jsonl"
        if not ledger.exists():
            continue
        last = None
        try:
            for ln in ledger.read_text().splitlines():
                last = json.loads(ln)
        except Exception:
            last = None
        if last and last.get("verdict") == "FAIL":
            node = last.get("node")
            note = str(last.get("note", ""))[:120]
            out.append(_obs_task(
                f"Чинить узел «{node}» магазина {slug} (последний ход FAIL)",
                "CONTROLLER", "health", priority=15, urgency="high", store=slug,
                cycle="cycle1",
                evidence=f"леджер {slug}/{date_str}: последняя строка FAIL на «{node}» "
                         f"{last.get('ts')}: {note}",
                body="Правило без фейк-пасс: последний ход FAIL — не перескакиваем, чиним узел."))
    return [o for o in out if o]


# ── планёрка (CD4: пульсы магазинов + ОДИН глобальный блок ЗАДАНИЙ) ────────────

def registry_status():
    """Состояние реестра: ('absent'|'ok'|'error', load_error?). Отличие «реестра нет» от «0 открытых»."""
    if T is None:
        return "absent", "модуль-реестр недоступен (import)"
    try:
        exists = T.task_path().exists()
    except Exception:
        exists = False
    if not exists:
        return "absent", None
    _, err = T.load()
    if err:
        return "error", err.get("load_error", "нечитаемый реестр")
    return "ok", None


def _load_tasks():
    if T is None:
        return [], {"load_error": "реестр недоступен (import)"}
    return T.load()


def plannerka_text(store=None, tasks=None, date_str=None):
    """Читаемая планёрка: магазины (пульс/вердикты) + ОДИН блок заданий по важности. Read 0₽."""
    date_str = date_str or _now_date()
    lines = []
    if cycle1 is None:
        lines.append("ЦИКЛ-ДНЯ · движок ЦИКЛА-1 недоступен (import)")
        return lines
    reg = cycle1.list_cycles()
    if not reg:
        lines.append("ЦИКЛ-ДНЯ · манифест магазинов пуст — нет ни одного цикла.")
    else:
        lines.append(f"ЦИКЛ-ДНЯ · {date_str} · магазинов в манифесте: {len(reg)}")
        for slug, inf in sorted(reg.items()):
            try:
                p = cycle1.plannerka_read(slug)
            except Exception:
                p = None
            head = f"  · {slug} — {inf.get('builder')} · донор {inf.get('donor_category') or '—'}"
            if not p:
                lines.append(head + " · пульса нет — сухой прогон соберёт (0₽)")
            else:
                lines.append(head + (f" · пульс {p.get('date')}"
                                     f" · сегодня {p.get('run_verdicts') or {}}"
                                     f" · артефактов СВЕРКА-PASS: {p.get('artifacts')}"))
        lines.append("")
    # ОДИН глобальный блок заданий (CD4): «реестра нет» ≠ «0 открытых» ≠ «реестр битый»
    if tasks is None:
        status, serr = registry_status()
        if status == "error":
            lines.append("ЗАДАНИЯ · реестр недоступен: " + str(serr))
            return lines
        if status == "absent":
            if serr:  # модуль-реестр не импортировался
                lines.append("ЗАДАНИЯ · реестр недоступен: " + str(serr))
            else:
                lines.append("ЗАДАНИЯ · реестра ещё нет — первая form --commit сформирует "
                             "из живых наблюдений (магазины/цены/здоровье).")
            return lines
        tasks, _ = _load_tasks()
    tasks = tasks or []
    if not tasks:
        lines.append("ЗАДАНИЯ · реестр есть, но пуст — заданий нет. form --commit наполнит.")
        return lines
    lines.append(f"ЗАДАНИЯ · записей {len(tasks)} · открыто {len(T.open_only(tasks))}")
    if store:
        sub = [t for t in tasks if not t.get("store") or t.get("store") == store]
        if not sub:
            lines.append(f"  (по магазину {store} открытых заданий нет)")
        else:
            lines.extend("  " + l for l in T.render_plannerka(sub))
    else:
        lines.extend("  " + l for l in T.render_plannerka(tasks))
    return lines


# ── form: сформировать задания из живых наблюдений (CD2/CD3/CD6) ───────────────

def form(*, commit=False, store=None, date_str=None, save_path=None, verbose=False):
    """Прогнать сканеры → кандидаты; существующие по TZ1-дедупу пропустить; при commit — записать.

    Возвращает (summary-dict, lines). commit=False (по умолчанию): НИЧЕГО не пишет, показывает,
    что СФОРМИРОВАЛОСЬ бы. commit=True: единственный write = локальный реестр заданий (CD6).
    Форма идемпотентна (CD3): то же намерение уже в реестре → «уже есть», дубль не создаём.
    """
    lines = []
    if T is None:
        return {"ok": False, "why": "реестр недоступен (import)"}, ["реестр недоступен (import)"]
    existing, _ = _load_tasks()
    existing_ids = {t.get("id") for t in existing if t.get("id")}
    cands = []
    for s in (scan_stores(), scan_pricing(store, date_str), scan_ledgers()):
        cands.extend(s or [])
    # дедуп внутри прогона: один и тот же id из двух сканеров не создаём дважды
    seen = set()
    fresh, dup = [], []
    for c in cands:
        if not c:
            continue
        tid = T.task_id(c["market"] if "market" in c else "ym", c["cycle"], c["category"],
                        c.get("store", ""), c["what"], c["owner"], c.get("urgency", "normal"))
        if tid in existing_ids or tid in seen:
            dup.append(c["what"])
            continue
        seen.add(tid)
        fresh.append(c)
    created = []
    if commit and fresh:
        merged = list(existing)
        for c in fresh:
            task, err = T.new_task(**c)
            if task and not err:
                merged.append(task)
                created.append(task.get("id"))
        # форма пишет ТОЛЬКО если создала что-то (пустой прогон не трогает диск)
        if created:
            r = T.save(merged, path=save_path)
            lines.append(f"form --commit · записано {len(created)} заданий в реестр · "
                         f"{r.get('ok') and 'ok' or r.get('error')}")
    lines.append(f"form · наблюдений: {len(cands)} · новых: {len(fresh)} · уже в реестре: {len(dup)}")
    for c in fresh:
        lines.append("  + " + c["what"] + f" · {c['owner']} · {c['category']}")
    if verbose:
        for c in dup:
            lines.append("  = (уже есть) " + c)
    return {"ok": True, "new": len(fresh), "dup": len(dup),
            "commit": commit and bool(created)}, lines


# ── dispatch: открытые задания → кто исполнит (CD5, никогда не mark_step) ──────

_CYCLE_RUN_CATS = {"categories", "products", "cards", "stocks"}  # задание, чей подхват = прогон ЦИКЛА-1


def _who_runs(task):
    """Честный ответ «кто это исполнит» для диспетчера. Возвращает (канал, текст)."""
    owner = task.get("owner")
    cat = task.get("category")
    store = task.get("store") or STORE_DEFAULT
    if owner in ("DISPATCHER", "CONTROLLER") and cat == "health":
        return "cycle_dry", f"сухой прогон ЦИКЛА-1 по {store} (0₽) — исполнитель движок"
    if owner == "PRICER" and cat == "pricing":
        return "pricer", "ЦЕНОВИК·ПЛАН готовит план (read); цены — только по слову оператора"
    if owner and cat and store:
        return "none", f"исполнителя в ЦИКЛ-ДНЯ нет — орган {owner} живёт отдельно (см. реестр)"
    return "none", "исполнителя в ЦИКЛ-ДНЯ нет"


def dispatch(tasks=None, *, cycle_dry=False, store=None, date_str=None):
    """Открытые задания по важности → план: кто исполнит, что подхватит диспетчер.

    cycle_dry=False: только РАЗБОР (read). cycle_dry=True (явный флаг CD5): задания-подхваты
    запускаются СУХО run_cycle(dry=True) по магазину. Диспетчер НИКОГДА не mark_step сам —
    пункт закрывает орган-исполнитель с реальным evidence. Возвращает (summary, lines).
    """
    if T is None or cycle1 is None:
        return ({"ok": False, "why": "реестр/движок недоступен (import)"},
                ["реестр/движок недоступен (import)"])
    if tasks is None:
        tasks, _ = _load_tasks()
    tasks = tasks or []
    open_ = T.open_only(tasks)
    lines = []
    if not open_:
        lines.append("ДИСПЕТЧЕР · открытых заданий нет — ничего брать в работу.")
        return {"ok": True, "open": 0, "ran": []}, lines
    lines.append(f"ДИСПЕТЧЕР · открытых заданий: {len(open_)} · по важности:")
    ran = []
    for t in T.sort_tasks(open_):
        st = T.derive(t)
        urg = t.get("urgency")
        chan, how = _who_runs(t)
        tag = "◐" if st == "in_progress" else ("⏳" if st == "waiting" else "○")
        lines.append(f"  {tag} P{t.get('priority', 50):<3} "
                     f"{('!' if urg in ('critical', 'high') else ' ')} "
                     f"[{t.get('store') or '—'}] {t.get('what')} · "
                     f"{t.get('owner')} · {chan}")
        lines.append(f"      ↳ {how}")
        if cycle_dry and chan == "cycle_dry":
            s = store or t.get("store") or STORE_DEFAULT
            try:
                res, _out = _run_cycle_capture(s, dry=True)
                v = res.get("verdict")
                lines.append(f"      ↳ СУХОЙ ПРОГОН {s}: {v} (0₽, {res.get('hash', '')[:10]})")
                ran.append({"store": s, "verdict": v})
            except Exception as e:
                lines.append(f"      ↳ сухой прогон {s} упал: {type(e).__name__}: {e}")
    return {"ok": True, "open": len(open_), "ran": ran}, lines


def _run_cycle_capture(store, dry=True):
    """Сухой прогон с захватом вывода (движок ТИХИЙ по умолчанию) → (res, out)."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = cycle1.run_cycle(store, dry=dry, commit=not dry, verbose=False)
    return res, buf.getvalue()


# ── CLI ─────────────────────────────────────────────────────────────────────────

def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="ЦИКЛ-ДНЯ · диспетчер заданий ЯМ-ЦИКЛА (0₽ read)")
    ap.add_argument("--plannerka", action="store_true", help="read: магазины + открытые задания")
    ap.add_argument("--store", default=None, help="магазин для планёрки/формы")
    ap.add_argument("--form", action="store_true", help="сформировать задания из живых наблюдений")
    ap.add_argument("--commit", action="store_true",
                    help="форма пишет реестр (единственный write; без него — только показать)")
    ap.add_argument("--dispatch", action="store_true", help="разбор открытых заданий: кто исполнит")
    ap.add_argument("--cycle-dry", action="store_true",
                    help="диспетчер подхватывает задания-прогоны СУХО run_cycle(dry=True)")
    ap.add_argument("--date", default=None, help="дата леджера для витрины (по умолчанию сегодня)")
    a = ap.parse_args(argv)
    if a.form or a.dispatch:
        if a.form:
            summary, lines = form(commit=a.commit, store=a.store, date_str=a.date, verbose=True)
        else:
            summary, lines = dispatch(cycle_dry=a.cycle_dry, store=a.store, date_str=a.date)
        for l in lines:
            print(l)
        if a.form and summary.get("commit"):
            print("ФОРМА ЗАКОММИТИЛА задания в локальный реестр (не сеть). Пункты — evidence по факту.")
        return 0
    # по умолчанию — планёрка (read, как терминал ЯМ-ЦИКЛ)
    for l in plannerka_text(store=a.store, date_str=a.date):
        print(l)
    return 0


if __name__ == "__main__":
    sys.exit(_main())

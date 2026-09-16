#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЦИКЛ-ДНЯ ОЗОН (ozon_cycle_day_v1) — диспетчер заданий ОЗОН над ОБЩИМ реестром ymarket_tasks_v1.

Зеркало ymarket_cycle_day_v1 ПОД ОЗОН. Зачем (та же директива, что ЯМ ЦИКЛ 2026-09-02, теперь для
ОЗОН-линии): утром видно — жил ли день ОЗОН, какие задания по линии открыты и КТО ответственный;
диспетчер берёт открытые по важности, инициирует сухой прогон ДНЯ (0₽), а пункт закрывает только тот
орган, который РЕАЛЬНО проверил (без фейк-пасс). Терминал = планёрка (read).

ОТЛИЧИЕ от ЯМ-зеркала (не копия, а пересборка под ОЗОН):
  · ЯМ — МНОГО магазинов (манифест cycle1, пульс по store-slug, леджеры по store/дата). ОЗОН — ОДИН
    кабинет (client 5162853): манифест стора не нужен, цикл-1-мультистора нет. День И ЕСТЬ движок.
  · источник наблюдений: ПАМЯТЬ ozon_state (карточки: errors/ждут-category/красный-индекс) + ЖУРНАЛ
    дня (ozon_day_journal: жил ли день сегодня). Артефакт-доказательство (CD2) = файл-источник.
  · реестр задач — ОБЩИЙ (ЯМ+ОЗОН по уставу ymarket-task-registry): ОЗОН пишет new_task(market="ozon",
    cycle="cycle_day"), читает by_market(tasks, "ozon"). ymarket_* НЕ трогаем — только добавляем свои
    записи в тот же файл (форма идемпотентна, своих не дублирует, чужих не трогает).
  · владельцы заданий = отделы ОЗОН: OZ_CONTROLLER (errors, цель 0) / OPERATOR (category_id —
    id не выдумываем) / OZ_PRICER (красный индекс) / DISPATCHER (жил ли день) + подхват дня.

ЗАКОНЫ (механические, CD1-CD6 зеркалим один в один):
  CD1  сухо: без --form/--commit/--cycle-dry ничего не пишет и наружу не ходит; планёрка = 0₽ чтение.
  CD2  формирование из ЖИВЫХ наблюдений: каждый сканер отдаёт наблюдение с evidence = артефакт
       (файл памяти/журнала), а не выдумка; голое наблюдение без артефакта не идёт.
  CD3  дедуп (TZ1): то же намерение (маркет+что+владелец+категория+…) → тот же id; --commit обновляет,
       не плодит дубль (форма идемпотентна — повторный прогон новых не добавит).
  CD4  планёрка: пульс дня ОЗОН + ОДИН глобальный блок ЗАДАНИЙ по важности; различает «реестра нет»
       от «0 открытых» от «битый реестр».
  CD5  диспетчер без фейк-пасс: сухой подхват ДНЯ (ozon_day.run_day dry=True) — ТОЛЬКО с явным
       --cycle-dry; никогда сам не mark_step; пункт закрывает орган-исполнитель с evidence.
  CD6  единственный write этого модуля — локальный реестр (form --commit, НЕ сеть, RUBICON цел).
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

ARB = Path(__file__).resolve().parent
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

try:
    import ymarket_tasks_v1 as T          # общий реестр заданий ЯМ+ОЗОН (id/владелец/пункты/гейт)
except Exception:
    T = None

_MARKET = "ozon"          # код маркета в общем реестре (MARKETS = ("ym","ozon"))
_CYCLE = "cycle_day"      # цикл ОЗОН в реестре (CYCLES = ("cycle1","cycle_day","cycle2")); дня и есть движок
_STORE = ""               # ОЗОН — один кабинет, store не используется (в реестре пусто)


def _now_date():
    return datetime.date.today().isoformat()


# ── наблюдение = кандидат задания (CD2: evidence НЕ пусто — без факта не формируем) ──

def _obs_task(what, owner, category, *, priority, urgency="normal", body="", evidence=""):
    if not evidence:
        return None
    steps = [{"id": "s1", "title": f"Выполнить: {what}"}]
    return dict(what=what, owner=owner, category=category, priority=priority,
                urgency=urgency, body=body, store=_STORE, cycle=_CYCLE,
                market=_MARKET, source="ozon_cycle_day", steps=steps,
                refs={"evidence": evidence})


# ── сканер 1: состояние ПАМЯТИ карточек (ozon_state) ────────────────────────────
# Артефакт — файл памяти; факт — KPI. «Нет кандидатов» (память пуста/чиста) = ничего не сеем.

def _state_doc():
    """Загрузить память ozon_state (env OZON_STATE_PATH перекрывает путь — песочница/тесты)."""
    try:
        import ozon_state_v1 as S
        return S.load(), S.state_path()
    except Exception:
        return None, None


def scan_state():
    """Наблюдения по карточкам из ПАМЯТИ (не выдумка): errors→OZ_CONTROLLER, need_mapping→OPERATOR,
    красный индекс→OZ_PRICER. Один факт = одно задание-сводка (по когорте, не флуд по карточке)."""
    out = []
    doc, spath = _state_doc()
    if doc is None:
        return out
    try:
        import ozon_state_v1 as S
        raw = S.kpis(doc)
    except Exception:
        return out
    art = f"ozon_state:{spath}"
    errs = raw.get("errored_ids") or []
    if raw.get("cards_errored"):
        ids = ", ".join(str(o) for o in errs[:8]) + ("…" if len(errs) > 8 else "")
        out.append(_obs_task(
            f"Починить {raw['cards_errored']} карточек с errors[] (цель 0): {ids}",
            "OZ_CONTROLLER", "cards", priority=10, urgency="high",
            evidence=f"{art}: {len(errs)} sku с errors[]",
            body="Закон OZ1: errors-карточка врёт витрине. Чинит КОНТРОЛЁР по факту карточки; "
                 "реальная правка на Ozon — после ротации ключа."))
    if raw.get("need_mapping"):
        out.append(_obs_task(
            f"Привязать {raw['need_mapping']} карточек к category_id + обязательные атрибуты",
            "OPERATOR", "categories", priority=20, urgency="normal",
            evidence=f"{art}: {raw['need_mapping']} sku нуждаются в привязке",
            body="OZ2: category_id не выдумываем — подтверждает орган/глаза оператора. Категория "
                 "ОЗОН выбирается на витрине маркетплейса (живой read 0₽)."))
    if raw.get("index_red"):
        ids = ", ".join(str(o) for o in (raw.get("index_red_ids") or [])[:8])
        out.append(_obs_task(
            f"Вывести из КРАСНОГО индекса {raw['index_red']} карточек: {ids}",
            "OZ_PRICER", "pricing", priority=30, urgency="normal",
            evidence=f"{art}: {raw['index_red']} sku с ценой вне зоны/пола (index_color красный)",
            body="OZ5: красный индекс прячет карточку из органики — снизить цену (пол маржи) или "
                 "снять. Цену на Ozon движок сам не трогает — ждёт ротации ключа и слова."))
    return [o for o in out if o]


# ── сканер 2: жил ли ДЕНЬ сегодня (журнал дня — артефакт) ───────────────────────
# Зеркало scan_stores (пульс устарел) для ОДНОГО кабинета. Журнал env-перекрываем → герметично.

def _day_journal_last():
    """Последняя строка журнала дня ozon_day (env OZON_DAY_JOURNAL → путь). None — журнала нет."""
    try:
        import ozon_day_v1 as day
    except Exception:
        return None, "модуль-день недоступен (import)"
    p = day.journal_path()
    if not p.exists():
        return None, str(p)
    last = None
    try:
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                last = json.loads(ln)
            except json.JSONDecodeError:
                continue
    except OSError as e:
        return None, f"{p}: {type(e).__name__}: {e}"
    return last, str(p)


def scan_day():
    """Журнал дня пуст / последний день ≠ сегодня → health-наблюдение для DISPATCHER (CD2)."""
    out = []
    last, p = _day_journal_last()
    if last is None:
        what = "Собрать первый день ОЗОН (сухой прогон, 0₽)"
        if p == "модуль-день недоступен (import)":
            return out  # день недоступен — формировать не из чего, честно пусто
        out.append(_obs_task(
            what, "DISPATCHER", "health", priority=40, urgency="normal",
            evidence=f"ozon_day_journal:{p}: журнала ещё нет",
            body="Первый день соберёт run_day(dry=True) 0₽: тик → отделы → KPI → журнал."))
        return [o for o in out if o]
    if last.get("date") != _now_date():
        out.append(_obs_task(
            f"День ОЗОН не гонялся сегодня (последний {last.get('date')}) — прогнать сухо",
            "DISPATCHER", "health", priority=35, urgency="normal",
            evidence=f"ozon_day_journal:{p}: последний день {last.get('date')} ≠ сегодня {_now_date()}",
            body="Сухой день обновит KPI/отделы и пополнит журнал — чтобы утро видело сегодняшний пульс."))
    return [o for o in out if o]


# ── планёрка (CD4: пульс дня ОЗОН + ОДИН блок ЗАДАНИЙ по маркету ozon) ──────────

def registry_status():
    """Состояние общего реестра: ('absent'|'ok'|'error', причина?). «Нет реестра» ≠ «0 открытых»."""
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


def plannerka_text(tasks=None, date_str=None):
    """Читаемая планёрка ОЗОН: пульс дня + открытые задания маркета ozon по важности. Read 0₽."""
    date_str = date_str or _now_date()
    lines = []
    last, p = _day_journal_last()
    lines.append(f"ЦИКЛ-ДНЯ ОЗОН · {date_str} · кабинет ОДИН (client_id, одиночный день — и есть движок)")
    if last is None:
        if p == "модуль-день недоступен (import)":
            lines.append("  пульс дня: модуль-день недоступен (import)")
        else:
            lines.append("  пульс дня: журнала ещё нет — первый сухой день соберёт (0₽)")
    else:
        k = last.get("kpis") or {}
        lines.append("  пульс дня: последний " + str(last.get("date"))
                     + f" · ok={last.get('ok')}" + (f" · упр {last.get('action')}" if last.get("action") else "")
                     + f" · карточек {k.get('cards_tracked')} · витрина {k.get('cards_on_shelf')}"
                     + f" · ошибки {k.get('cards_errored')} · красных {k.get('index_red')}"
                     + (f" · журнал {p}" if p and p != "модуль-день недоступен (import)" else ""))
    lines.append("")
    # ОДИН глобальный блок ЗАДАНИЙ маркета ozon (CD4): отличаем «реестра нет» от «0 открытых»
    if T is None:
        lines.append("ЗАДАНИЯ · реестр недоступен (import)")
        return lines
    if tasks is None:
        status, serr = registry_status()
        if status == "error":
            lines.append("ЗАДАНИЯ · реестр битый: " + str(serr))
            return lines
        if status == "absent":
            if serr:
                lines.append("ЗАДАНИЯ · реестр недоступен: " + str(serr))
            else:
                lines.append("ЗАДАНИЯ · реестра ещё нет — первая form --commit сформирует из живых "
                             "наблюдений (память карточек / журнал дня).")
            return lines
        tasks, _ = _load_tasks()
    oz = T.by_market(tasks or [], _MARKET)
    if not oz:
        lines.append("ЗАДАНИЯ · записей ОЗОН: 0 — form --commit наполнит из наблюдений.")
        return lines
    open_oz = T.open_only(oz)
    lines.append(f"ЗАДАНИЯ ОЗОН · записей {len(oz)} · открыто {len(open_oz)}")
    if not open_oz:
        lines.append("  (открытых заданий ОЗОН нет)")
    else:
        lines.extend("  " + l for l in T.render_plannerka(open_oz))
    return lines


# ── form: сформировать задания из живых наблюдений (CD2/CD3/CD6) ───────────────

def form(*, commit=False, save_path=None, verbose=False):
    """Прогнать сканеры (память/журнал) → кандидаты; существующие по TZ1-дедупу пропустить.

    commit=False (по умолчанию): НИЧЕГО не пишет, показывает, что СФОРМИРОВАЛОСЬ бы. commit=True:
    единственный write = локальный общий реестр (CD6), только маркет ozon добавляем, чужих не трогаем.
    Форма идемпотентна (CD3): то же намерение уже в реестре → «уже есть», дубль не создаём.
    """
    lines = []
    if T is None:
        return {"ok": False, "why": "реестр недоступен (import)"}, ["реестр недоступен (import)"]
    existing, _ = _load_tasks()
    existing_ids = {t.get("id") for t in existing if t.get("id")}
    cands = list(scan_state()) + list(scan_day())
    # дедуп внутри прогона: один и тот же id из двух сканеров дважды не создаём
    seen = set()
    fresh, dup = [], []
    for c in cands:
        if not c:
            continue
        tid = T.task_id(c.get("market", _MARKET), c["cycle"], c["category"],
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
            lines.append(f"form --commit · записано {len(created)} заданий ОЗОН в общий реестр · "
                         f"{r.get('ok') and 'ok' or r.get('error')}")
    lines.append(f"form · наблюдений: {len(cands)} · новых: {len(fresh)} · уже в реестре: {len(dup)}")
    for c in fresh:
        lines.append("  + " + c["what"] + f" · {c['owner']} · {c['category']}")
    if verbose:
        for c in dup:
            lines.append("  = (уже есть) " + c)
    return {"ok": True, "new": len(fresh), "dup": len(dup),
            "commit": commit and bool(created)}, lines


# ── dispatch: открытые задания ozon → кто исполнит (CD5, никогда не mark_step) ──

def _who_runs(task):
    """Честный ответ «кто это исполнит». Для ОЗОН подхват дня = только health-пульс DISPATCHER."""
    owner = task.get("owner")
    cat = task.get("category")
    if owner == "DISPATCHER" and cat == "health":
        return "day_dry", "сухой прогон ДНЯ ОЗОН (ozon_day.run_day dry=True, 0₽) — исполнитель движок"
    if owner and cat:
        return "none", (f"исполнителя в ДИСПЕТЧЕРЕ нет — орган {owner} живёт отдельно; реальное "
                        "касание Ozon — после ротации ключа и слова оператора")
    return "none", "исполнителя в ДИСПЕТЧЕРЕ нет"


def dispatch(tasks=None, *, cycle_dry=False, day_fn=None):
    """Открытые задания ОЗОН по важности → план: кто исполнит, что подхватит диспетчер.

    cycle_dry=False: только РАЗБОР (read). cycle_dry=True (явный флаг CD5): задания-подхваты
    запускаются СУХО ozon_day.run_day(dry=True). Диспетчер НИКОГДА не mark_step сам — пункт
    закрывает орган-исполнитель с реальным evidence. day_fn — шов (тесты подкладывают день без
    касания канонической памяти). Возвращает (summary, lines).
    """
    if T is None:
        return ({"ok": False, "why": "реестр недоступен (import)"},
                ["реестр недоступен (import)"])
    if tasks is None:
        tasks, _ = _load_tasks()
    oz = T.by_market(tasks or [], _MARKET)
    open_ = T.open_only(oz)
    lines = []
    if not open_:
        lines.append("ДИСПЕТЧЕР ОЗОН · открытых заданий нет — ничего брать в работу.")
        return {"ok": True, "open": 0, "ran": []}, lines
    lines.append(f"ДИСПЕТЧЕР ОЗОН · открытых заданий: {len(open_)} · по важности:")
    ran = []
    for t in T.sort_tasks(open_):
        st = T.derive(t)
        urg = t.get("urgency")
        chan, how = _who_runs(t)
        tag = "◐" if st == "in_progress" else ("⏳" if st == "waiting" else "○")
        lines.append(f"  {tag} P{t.get('priority', 50):<3} "
                     f"{('!' if urg in ('critical', 'high') else ' ')} "
                     f"{t.get('what')} · {t.get('owner')} · {chan}")
        lines.append(f"      ↳ {how}")
        if cycle_dry and chan == "day_dry":
            try:
                d = _run_day_capture(day_fn)
                ok = d.get("ok")
                lines.append(f"      ↳ СУХОЙ ДЕНЬ: ok={ok} · упр "
                             f"{(d.get('roles') or {}).get('MANAGER_TICK', {}).get('action')} "
                             f"· карточек {(d.get('kpis') or {}).get('cards_tracked')} (0₽)")
                ran.append({"ok": ok, "action": (d.get('roles') or {}).get('MANAGER_TICK', {}).get('action')})
            except Exception as e:
                lines.append(f"      ↳ сухой день упал: {type(e).__name__}: {e}")
    return {"ok": True, "open": len(open_), "ran": ran}, lines


def _run_day_capture(day_fn=None):
    """Прогнать день сухо. Шов day_fn (тест) или настоящий run_day(dry=True) (0₽, локальная память)."""
    if day_fn is not None:
        return day_fn(dry=True)
    try:
        import ozon_day_v1 as day
        return day.run_day(dry=True)
    except Exception as e:
        raise RuntimeError(f"озон_день недоступен: {type(e).__name__}: {e}") from e


# ── CLI ─────────────────────────────────────────────────────────────────────────

def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="ЦИКЛ-ДНЯ ОЗОН · диспетчер заданий линии (0₽ read)")
    ap.add_argument("--plannerka", action="store_true", help="read: пульс дня + открытые задания ОЗОН")
    ap.add_argument("--form", action="store_true", help="сформировать задания из живых наблюдений")
    ap.add_argument("--commit", action="store_true",
                    help="форма пишет общий реестр (единственный write; без него — только показать)")
    ap.add_argument("--dispatch", action="store_true", help="разбор открытых заданий: кто исполнит")
    ap.add_argument("--cycle-dry", action="store_true",
                    help="диспетчер подхватывает задания-дни СУХО ozon_day.run_day(dry=True)")
    a = ap.parse_args(argv)
    if a.form or a.dispatch:
        if a.form:
            summary, lines = form(commit=a.commit, verbose=True)
        else:
            summary, lines = dispatch(cycle_dry=a.cycle_dry)
        for l in lines:
            print(l)
        if a.form and summary.get("commit"):
            print("ФОРМА ЗАКОММИТИЛА задания ОЗОН в локальный реестр (не сеть). Пункты — evidence по факту.")
        return 0
    # по умолчанию — планёрка (read, терминал)
    for l in plannerka_text():
        print(l)
    return 0


if __name__ == "__main__":
    sys.exit(_main())

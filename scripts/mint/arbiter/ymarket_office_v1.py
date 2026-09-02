#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ВИРТУАЛЬНЫЙ ОФИС ЯМ (ymarket_office_v1) — видеть ВСЮ КОМАНДУ, законные связи, и кто РЕАЛЬНО работает.

Зачем (слова оператора): «Хочу видеть ВСЕ КОМАНДУ, взаимосвязи между ними — законные — а также
все чтобы видеть всех тех кто реально работает и кто реально стал сотрудником. Чтобы каждый работник
работал на совесть.» Отдельный ЧИСТЫЙ-READ пульт: НЕ лезет в кабинет, НЕ двигает цены/остатки/деньги,
только читает уже лежащие артефакты органа и говорит ПРАВДУ о том, кто доказуемо работал.

ЧЕМ ОТЛИЧАЕТСЯ от пульта (arbiter_console_v1): пульт смотрит «как думает организм» (vitals/гайджеты),
а офис отвечает на кадровый вопрос: кто в команде, кто с кем связан законно, кто ЧИСЛИТСЯ, кто
СТАЖЁР, кто В ШТАТЕ по ДОКАЗАТЕЛЬСТВАМ, и какая у каждого «совесть» (5 механических проверок).

ГЛАВНАЯ ПРАВДА, которую офис вынужден говорить (по данным 2026-09-01):
  • Память смен хранит числа ТОЛЬКО 5 ролей (ДИСП/СКЛАД/ЦЕН/ТОВ/КОНТР) — у остальных СВОЕГО канала
    доказательств НЕТ. Дневной журнал выбрасывает весь day["roles"]. Значит 7 ролей из 12+ не могут
    доказать работу ФИЗИЧЕСКИ — это не их вина, это отсутствие канала (закрываем ТАБЕЛЬю, см. ниже).
  • Последнее реальное число ВСЕХ ролей — 2026-08-05 (27 дней тишины). Ни одна роль не «работает
    свежо». БРИГАДИР и УПРАВЛЯЮЩИЙ реально крутятся (382 смены, последняя сегодня, тики каждый день),
    но качество смены плачевно: ok=True в 49/382 (12.8%).

КАРТА-ЗАНЯТОСТИ (лестница, считается механически, не на глаз):
  ВАКАНСИЯ   — роль упоминается в уставах, но у неё НЕТ модуля/устава (СБОРЩИК/ЗАЛИВЩИК).
  ЧИСЛИТСЯ   — устав есть, в строю (в цикле или отдельный раннер), но СВОЕГО канала доказательств
               нет → честно: «доказать работу не может».
  СТАЖЁР     — канал есть И работа когда-то доказана, но не свежо (последнее число старше 7 дней).
  В ШТАТЕ    — канал есть + работа доказана свежим числом (≤7 дней).

СОВЕСТЬ (5 механических проверок на роль, 0/1 каждая):
  1 УСТАВ (читаемый CHARTER) · 2 В СТРОЮ (в цикле/раннер) · 3 КАНАЛ (свой след на диске)
  4 РАБОТА (когда-либо реальное число) · 5 СВЕЖО (реальное число ≤7 дней).

СВЯЗИ между ролями читаются ИЗ УСТАВОВ (inputs/outputs, русским текстом) — источник законный,
не придуманный. Классификация:
  ЗАКОННАЯ      — оба конца реальные роли, заведённые в суточный цикл → передача механически возможна.
  ЗАЯВЛЕНА      — названа в уставе, но хотя бы один конец НЕ в цикле → хэнд-офф не проведён.
  В ПРИЗРАК     — конец указывает на ВАКАНСИЮ (нет модуля) — связь укажет на пустоту.
  ВНЕШНЯЯ       — конец = Маркет / ОПЕРАТОР (внешний узел).

ТАБЕЛЬ (недостающий канал): record_day(day) дописывает каждую роль дня отдельной строкой в
ymarket_office_tabel.jsonl. ПО УМОЛЧАНИЮ ВЫКЛЮЧЕН — сам офис ничего не пишет. Хук вешается циклом
(ymarket_day_v1._append_journal) мягко и обратносовместимо: содержимое журнала не меняется, сбой
офиса день не роняет. Это и есть «сейчас прорабатываем команду внутри цикла»: с ТАБЕЛЬю каждая роль
сможет доказать смену.

RUBICON цел по построению: модуль читает артефакты + (по слову) пишет ТОЛЬКО в свой табель и
runtime-html. Ни одного вызова маркетплейса, 0₽.

Sources (env-override зеркалят контракт органа):
  YM_SHIFT_MEMORY    память смен (ymarket_shift_memory.json)
  YM_DAY_JOURNAL     дневной журнал (reports/mint/arbiter/ymarket_day_journal.jsonl)
  YM_TICK_LEDGER     tick-ledger СЕЛФ (reports/mint/arbiter/ymarket_tick_ledger.jsonl)
  YM_OFFICE_OUT      куда писать html (по умолч. runtime/YM_VIRTUAL_OFFICE.html)
  YM_OFFICE_TABEL    куда ТАБЕЛЬ (по умолч. reports/mint/arbiter/ymarket_office_tabel.jsonl)
"""
from __future__ import annotations

import os
import re
import sys
import json
import ast
import html
from pathlib import Path
from datetime import datetime, timezone, timedelta

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent          # scripts/mint
SOCC = HERE.parent.parent.parent      # SOCC/
REPORTS = SOCC / "MEMORY_WAVE/reports/mint/arbiter"

# ── artefact paths (env-override зеркалят контракт органа, как у консоли) ──
SHIFT_PATH   = Path(os.environ.get("YM_SHIFT_MEMORY", HERE / "ymarket_shift_memory.json"))
JOURNAL_PATH = Path(os.environ.get("YM_DAY_JOURNAL", REPORTS / "ymarket_day_journal.jsonl"))
TICKS_PATH   = Path(os.environ.get("YM_TICK_LEDGER", REPORTS / "ymarket_tick_ledger.jsonl"))
OUT          = Path(os.environ.get("YM_OFFICE_OUT", HERE / "runtime" / "YM_VIRTUAL_OFFICE.html"))
TABEL_PATH   = Path(os.environ.get("YM_OFFICE_TABEL", REPORTS / "ymarket_office_tabel.jsonl"))

# Operator surface law: рендер только через общий канон SOCC, никакого локального стиля.
sys.path.insert(0, str(SOCC / "SYSTEM/INTERFACE/dashboard"))
from socc_canon_html import palette, css, badge  # noqa: E402

FRESH_DAYS = 7        # окно «свежей» работы (≤7 дней — живой, не музей)

# ── ролевой реестр офиса (статика: порядок/эмодзи/проводка; динамика из CHARTER-ов) ──
# wired: "cycle:shift" — БРИГАДИР гоняет смену целиком · "cycle:tick" — УПРАВЛЯЮЩИЙ тикает сам
#        "cycle:step"  — отдельный шаг суточного цикла · "runner" — отдельный раннер (не в цикле)
#        "cycle:optin" — шаг цикла только по слову (--donor-zaliv) · "none" — не заведён
# channel: где роль оставляет ДОКАЗУЕМЫЙ след на диске; "none" = канала нет.
ROLES = [
    dict(key="BRIGADE",     name_ru="БРИГАДИР",     emoji="👷", cluster="master",
         source="ymarket_brigade_v1.py", wired="cycle:shift", channel="shift_ok"),
    dict(key="DISPATCHER",  name_ru="ДИСПЕТЧЕР",    emoji="🚚", cluster="core",
         source="ymarket_role_dispatcher_v1.py", wired="cycle:via_brigade", channel="shift_orders"),
    dict(key="STOCKMAN",    name_ru="СКЛАДОВЩИК",   emoji="📦", cluster="core",
         source="ymarket_role_stockman_v1.py", wired="cycle:via_brigade", channel="shift_stock"),
    dict(key="MERCHANDISER",name_ru="ТОВАРОВЕД",    emoji="🛒", cluster="core",
         source="ymarket_role_merchandiser_v1.py", wired="cycle:via_brigade", channel="shift_assort"),
    dict(key="PRICER",      name_ru="ЦЕНОВИК",      emoji="💰", cluster="core",
         source="ymarket_role_pricer_v1.py", wired="cycle:via_brigade", channel="shift_pricing"),
    dict(key="CONTROLLER",  name_ru="КОНТРОЛЁР",    emoji="🛡", cluster="core",
         source="ymarket_role_controller_v1.py", wired="cycle:via_brigade", channel="shift_rating"),
    dict(key="MANAGER",     name_ru="УПРАВЛЯЮЩИЙ",  emoji="🧭", cluster="master",
         source="ymarket_self_v1.py", wired="cycle:tick", channel="tick_ledger"),
    dict(key="STRATEGIST",  name_ru="СТРАТЕГ",      emoji="📈", cluster="propose",
         source="ymarket_role_strategist_v1.py", wired="cycle:step", channel="none"),
    dict(key="TRENDSCOUT",  name_ru="ТРЕНД-СКАУТ",  emoji="🔭", cluster="propose",
         source="ymarket_role_trendscout_v1.py", wired="cycle:step", channel="none"),
    dict(key="HEAD",        name_ru="ГОЛОВА",       emoji="🧠", cluster="propose",
         source="ymarket_role_head_v1.py", wired="cycle:step", channel="none"),
    dict(key="CATEGORIST",  name_ru="КАТЕГОРИЙЩИК", emoji="🗂", cluster="propose",
         source="ymarket_role_categorist_v1.py", wired="runner", channel="none"),
    dict(key="GROWTH",      name_ru="СКАУТ РОСТА",  emoji="🌱", cluster="propose",
         source="ymarket_role_growth_v1.py", wired="runner", channel="none"),
    dict(key="ZALIV",       name_ru="СБОРЩИК",      emoji="📦", cluster="vacancy",
         source=None, wired="cycle:optin", channel="none"),   # призрак: нет модуля/устава
]
ROSTER = {r["key"]: r for r in ROLES}

# Внешние узлы графа (не роли команды).
EXTERNAL = {"MARKET": "ЯНДЕКС МАРКЕТ", "OPERATOR": "ОПЕРАТОР"}
WIRED_KEYS = {r["key"] for r in ROLES if r["wired"].startswith("cycle")}

# Русские имена в уставах → ключ. Порядок важен: сначала более длинные (СКАУТ РОСТА до РОСТА).
NAME_TO_KEY = [
    ("ТРЕНД-СКАУТ", "TRENDSCOUT"), ("СКАУТ РОСТА", "GROWTH"), ("КАТЕГОРИЙЩИК", "CATEGORIST"),
    ("СКЛАДОВЩИК", "STOCKMAN"), ("ДИСПЕТЧЕР", "DISPATCHER"), ("БРИГАДИР", "BRIGADE"),
    ("МЕРЧАНДАЙЗЕР", "MERCHANDISER"), ("ТОВАРОВЕД", "MERCHANDISER"), ("ЦЕНОВИК", "PRICER"),
    ("КОНТРОЛЁР", "CONTROLLER"), ("СТРАТЕГ", "STRATEGIST"), ("ГОЛОВА", "HEAD"),
    ("СБОРЩИК", "ZALIV"), ("ЗАЛИВЩИК", "ZALIV"), ("УПРАВЛЯЮЩИЙ", "MANAGER"),
    ("УПРАВЛЯЮЩАЯ", "MANAGER"), ("МЕНЕДЖЕР", "MANAGER"),
    ("ЯНДЕКС МАРКЕТ", "MARKET"), ("МАРКЕТ", "MARKET"), ("ОПЕРАТОР", "OPERATOR"),
]

# БРИГАДИР устава своего не имеет (собирает 5 ролей смены) — синтезируем честный фолбэк.
BRIGADE_FALLBACK = {
    "id": "YM_BRIGADE",
    "name_ru": "БРИГАДИР",
    "mandate": "вести смену в порядке цены ошибки: горящее → важное → выгодное",
    "owns": ["порядок ходов смены", "эскалация оператору"],
    "inputs": ["отчёты ролей смены (ДИСП→СКЛАД→ТОВ→ЦЕН→КОНТР)"],
    "outputs": ["сводка смены → УПРАВЛЯЮЩИЙ", "эскалация → ОПЕРАТОР"],
    "laws": [
        "B2 молчания нет: провал роли — её строка в сводке, а не тишина",
        "B4 смена идёт до конца: одна сорванная роль не отменяет остальные",
    ],
    "kpi": [{"metric": "смена проведена целиком", "target": "да", "source_of_truth": "память смен"}],
    "proves_by": "ok/ошибки смены в памяти смен (ymarket_shift_memory.json)",
    "composed": True,
}


# ───────────────────────────── helpers (never throw) ─────────────────────────────
def _now():
    return datetime.now(timezone.utc)


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def load_jsonl(path):
    rows = []
    try:
        for ln in Path(path).read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    continue
    except Exception:
        pass
    return rows


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def num(v, dash="—"):
    if v is None:
        return dash
    try:
        f = float(v)
    except Exception:
        return esc(v)
    return "%d" % int(f) if f == int(f) else "%.1f" % f


def _dt(s):
    """ISO-строка → datetime (None-safe)."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _days_since(s, now=None):
    dt = _dt(s)
    if dt is None:
        return None
    now = now or _now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


def _fresh(s, now=None):
    """Свежо: последнее число есть и моложе FRESH_DAYS. 0 дней == свежо (а не `or 999`)."""
    d = _days_since(s, now)
    return d is not None and d <= FRESH_DAYS


# ───────────────────────────── уставы (ast, без импортов) ─────────────────────────
def extract_charter(path):
    """Достать CHARTER = {...} из файла ПРОСТО (ast.literal_eval), БЕЗ импорта модуля.

    Импорт ролей тянет торговые руки/сеть и падает на py3.9 (то, из-за чего пульт захардкодил роли).
    Статическое чтение словаря-литерала лишено этих проблем и RUBICON-safe. Битый файл → None."""
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "CHARTER":
                    try:
                        val = ast.literal_eval(node.value)
                    except Exception:
                        return None
                    if isinstance(val, dict):
                        return val
    return None


def load_charters():
    """Все уставы: {role_key: charter|None}. БРИГАДИР — фолбэк, остальные — из файлов."""
    out = {}
    for r in ROLES:
        src = r.get("source")
        if src is None:
            out[r["key"]] = None
            continue
        ch = extract_charter(HERE / src)
        if r["key"] == "BRIGADE" and not ch:
            ch = BRIGADE_FALLBACK
        out[r["key"]] = ch
    return out


# ───────────────────────────── связи (из уставов) ────────────────────────────────
def _scan_text(text, found):
    for name, key in NAME_TO_KEY:
        if name in text:
            found[key] = found.get(key, 0) + 1


def build_edges(charters):
    """Прочитать связи из inputs/outputs каждого устава. Возвращает список ребёр.

    Ребро: {src, dst, kind: input|output, label: фраза-первоисточник, cls}.
    cls: lawful (оба конца в цикле) · declared (заявлена, канал не проведён)
         · ghost (конец = вакансия) · external (Маркет/ОПЕРАТОР)."""
    edges = []
    for rid, ch in charts_ok(charters).items():
        for kind in ("inputs", "outputs"):
            items = ch.get(kind) or []
            for item in items:
                if not isinstance(item, str):
                    continue
                found = {}
                _scan_text(item, found)
                for dst in found:
                    edges.append({"src": rid, "dst": dst, "kind": kind, "label": item.strip()})
    for e in edges:
        e["cls"] = classify_edge(e["src"], e["dst"])
    return edges


def charts_ok(charters):
    """Только реальные уставы (призраки/битые не дают связей — не выдумываем)."""
    return {k: v for k, v in (charters or {}).items() if isinstance(v, dict)}


def role_with_charter(r, charters):
    """Запись реестра + её устав (employment/совесть смотрят r['charter'])."""
    out = dict(r)
    out["charter"] = charts_ok(charters).get(r["key"])
    return out


def classify_edge(src, dst):
    if dst in EXTERNAL:
        return "external"
    if dst not in ROSTER:
        return "ghost"                     # даже в реестре нет — в никуда
    if ROSTER[dst]["source"] is None:
        return "ghost"                     # призрак: СБОРЩИК
    if src in WIRED_KEYS and dst in WIRED_KEYS:
        return "lawful"
    return "declared"


# ───────────────────────────── доказательства (из живых артефактов) ────────────────
def gather_evidence(charters, now=None):
    """Собрать для каждой роли её ДОКАЗУЕМЫЙ след из лежащих артефактов (только чтение).

    Возвращает {role_key: ev}, ev = {has_channel, channel_desc, samples, last_real (ts),
    fresh, ok_shifts, errors, escalations, first_real} + summary {shifts, ok, last_shift, ...}.
    Ничего не выдумываем: нет следа → нули/None, не «работал 0 раз»."""
    now = now or _now()
    ev = {k: {"has_channel": False, "channel_desc": None, "samples": 0, "last_real": None,
              "fresh": False, "ok_shifts": 0, "errors": 0, "escalations": 0} for k in ROSTER}

    shift_doc = load_json(SHIFT_PATH)
    shifts = shift_doc.get("shifts") if isinstance(shift_doc, dict) else shift_doc
    if isinstance(shifts, list):
        ev["BRIGADE"]["has_channel"] = True
        ev["BRIGADE"]["channel_desc"] = "ok/ошибки смены в памяти смен"
        ev["BRIGADE"]["samples"] = len(shifts)
        ev["BRIGADE"]["ok_shifts"] = sum(1 for s in shifts if s.get("ok") is True)
        ev["BRIGADE"]["errors"] = sum(int(s.get("errors") or 0) for s in shifts)
        last_at = max((s.get("at") for s in shifts if s.get("at")), default=None)
        ev["BRIGADE"]["last_real"] = last_at
        ev["BRIGADE"]["fresh"] = _fresh(last_at, now)
        # эскалации и реальные числа по ролям смены
        SHIFT_KEY = {"DISPATCHER": "orders", "STOCKMAN": "stock", "PRICER": "pricing",
                     "MERCHANDISER": "assortment", "CONTROLLER": "quality_rating"}
        for rid, key in SHIFT_KEY.items():
            last_real = None
            samples = 0
            for s in shifts:
                sub = s.get(key)
                real = False
                if isinstance(sub, dict):
                    real = any(v is not None for v in sub.values())
                elif sub is not None:
                    real = True
                if real:
                    samples += 1
                    last_real = last_real or s.get("at")      # первая смена с числом
                    last_real = s.get("at") if (s.get("at") or "") >= (last_real or "") else last_real
            ev[rid]["has_channel"] = True
            ev[rid]["channel_desc"] = "память смен · %s" % key
            ev[rid]["samples"] = samples
            ev[rid]["last_real"] = last_real
            ev[rid]["fresh"] = _fresh(last_real, now)
            # эскалации этой роли
            ev[rid]["escalations"] = sum(1 for s in shifts
                                         for e in (s.get("escalations") or [])
                                         if isinstance(e, dict) and e.get("role") == rid)

    ticks = load_jsonl(TICKS_PATH)
    if ticks:
        ev["MANAGER"]["has_channel"] = True
        ev["MANAGER"]["channel_desc"] = "tick-ledger СЕЛФ"
        ev["MANAGER"]["samples"] = len(ticks)
        last_ts = max((t.get("ts") or t.get("at") or "" for t in ticks), default=None)
        ev["MANAGER"]["last_real"] = last_ts
        ev["MANAGER"]["fresh"] = _fresh(last_ts, now)

    days = load_jsonl(JOURNAL_PATH)
    summary = {
        "shifts": ev["BRIGADE"]["samples"] if isinstance(shifts, list) else 0,
        "ok": ev["BRIGADE"]["ok_shifts"],
        "errors": ev["BRIGADE"]["errors"],
        "last_shift": ev["BRIGADE"]["last_real"],
        "ticks": len(ticks),
        "days": len(days),
    }
    return ev, summary


def employment(r, ev):
    """Лестница занятости (чистая функция, тестируется синтетикой)."""
    ch = r.get("charter")
    if ch is None:
        return "ВАКАНСИЯ"
    wired = bool(r.get("wired") and r["wired"] != "none")
    channel = bool(ev.get("has_channel"))
    last_real = ev.get("last_real")
    fresh = bool(ev.get("fresh") and last_real)
    if wired and channel and last_real and fresh:
        return "В ШТАТЕ"
    if channel and last_real:
        return "СТАЖЁР"
    if wired or channel:
        return "ЧИСЛИТСЯ"
    return "ЧИСЛИТСЯ"


def conscience_score(r, ev):
    """Совесть x/5 (механически): УСТАВ · В СТРОЮ · КАНАЛ · РАБОТА · СВЕЖО."""
    checks = [
        r.get("charter") is not None,
        bool(r.get("wired") and r["wired"] != "none"),
        bool(ev.get("has_channel")),
        bool(ev.get("last_real")),
        bool(ev.get("fresh") and ev.get("last_real")),
    ]
    return sum(1 for c in checks if c), checks


# ───────────────────────────── ТАБЕЛЬ (append-only, OFF by default) ────────────────
def tabel_path():
    return TABEL_PATH


def record_day(day):
    """Дописать день в ТАБЕЛЬ: КАЖДАЯ роль дня отдельной строкой (append-only, fail-soft).

    OFF по умолчанию: вызывается ТОЛЬКО циклом через мягкий хук в _append_journal. Сам офис
    ничего не пишет. Битый/не-словарь → 0, без падения. Возвращает число записанных строк."""
    try:
        if not isinstance(day, dict):
            return 0
        date = day.get("date")
        if not date:
            return 0
        p = tabel_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        roles = day.get("roles")
        rows = 0
        with open(p, "a", encoding="utf-8") as f:
            if isinstance(roles, dict):
                for rid, st in sorted(roles.items()):
                    if not isinstance(st, dict):
                        continue
                    if st.get("ok") is False:
                        status = "fail"
                    elif st.get("skipped"):
                        status = "skip"
                    else:
                        status = "ok"
                    row = {"schema": "ymarket.office.tabel.v1", "date": date, "ts": day.get("ts"),
                           "role": rid, "status": status, "error": st.get("error") or None,
                           "evidence": st.get("human") or st.get("action") or None}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    rows += 1
            z = day.get("zaliv")
            if isinstance(z, dict):
                row = {"schema": "ymarket.office.tabel.v1", "date": date, "ts": day.get("ts"),
                       "role": "ZALIV", "status": "skip" if z.get("donor_blocker") else "ok",
                       "error": z.get("donor_blocker") or None,
                       "evidence": "готово %s · ошибка %s" % (z.get("ready"), z.get("errors"))}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                rows += 1
        return rows
    except Exception:
        return 0


def load_tabel():
    """ТАБЕЛЬ: список строк (fail-soft: битый файл → [])."""
    return load_jsonl(TABEL_PATH)


def tabel_summary(rows):
    """Сжатая статистика табеля: дат, ролей, статусов."""
    if not rows:
        return {"days": 0, "roles": 0, "ok": 0, "skip": 0, "fail": 0, "by_role": {}}
    dates = {r.get("date") for r in rows}
    by_role = {}
    status = {"ok": 0, "skip": 0, "fail": 0}
    for r in rows:
        st = r.get("status")
        if st in status:
            status[st] += 1
        rid = r.get("role")
        by_role[rid] = by_role.get(rid, 0) + 1
    return {"days": len(dates), "roles": len(by_role), "by_role": by_role, **status}


# ───────────────────────────── HTML (канон SOCC + аддитивные классы) ─────────────
def extra_css():
    return """<style>
 .wrap{max-width:1080px}
 .mut{color:var(--muted)} .no{color:var(--danger)} .ok{color:var(--success)}
 .warnc{color:var(--warning)}
 /* лестница занятости */
 .ladder{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin:4px 0}
 .lcell{background:var(--s2);border:1px solid var(--line);border-radius:var(--radius);padding:11px 13px}
 .lk{color:var(--muted);text-transform:uppercase;letter-spacing:.07em;font-size:10px;margin-bottom:7px}
 .lc{border-radius:7px;padding:2px 8px;font-size:11.5px;font-weight:700;letter-spacing:.02em}
 .lc.staff{background:color-mix(in srgb,var(--success) 18%,transparent);color:var(--success)}
 .lc.stage{background:color-mix(in srgb,var(--warning) 18%,transparent);color:var(--warning)}
 .lc.list{background:color-mix(in srgb,var(--muted) 16%,transparent);color:var(--muted)}
 .lc.vac{background:color-mix(in srgb,var(--danger) 18%,transparent);color:var(--danger)}
 /* карточки совести */
 .team{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin:6px 0}
 .tcard{background:var(--s2);border:1px solid var(--line);border-radius:var(--radius);padding:13px 15px}
 .thead{display:flex;align-items:center;gap:9px;margin-bottom:8px}
 .tname{font-size:14.5px;font-weight:700}
 .tmand{font-size:11.5px;color:var(--muted);line-height:1.5;margin:2px 0 9px}
 .stars{letter-spacing:.14em;font-size:12px}
 .checks{display:grid;grid-template-columns:1fr 1fr;gap:4px 10px;font-size:11px;line-height:1.6}
 .ck{display:flex;gap:6px;align-items:center}
 .ev{font-size:11px;color:var(--muted);margin-top:8px;line-height:1.55;border-top:1px dashed var(--line);padding-top:7px}
 .ev b{color:var(--fg)}
 /* связи */
 .edges{display:grid;grid-template-columns:1fr;gap:5px;font-size:11.5px}
 .edge{display:flex;align-items:center;gap:8px;line-height:1.5}
 .elabel{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:58%}
 .arrow{color:var(--muted)}
 .egrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px;margin:6px 0}
 .estrip{background:var(--s2);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px}
 /* табель */
 .tabel{width:100%;border-collapse:collapse;font-size:11px}
 .tabel th{color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-size:9.5px;text-align:left;padding:4px 8px;border-bottom:1px solid var(--line)}
 .tabel td{padding:4px 8px;border-bottom:1px solid color-mix(in srgb,var(--line) 55%,transparent);font-family:ui-monospace,Menlo,monospace}
 .chip{font-size:10px;padding:1px 6px;border-radius:5px;background:var(--s3);border:1px solid var(--line)}
</style>"""


def sec_ladder(ev, summary):
    counts = {}
    for r in ROLES:
        emp = employment(r, ev[r["key"]])
        counts[emp] = counts.get(emp, 0) + 1
    lbl = {"В ШТАТЕ": ("lc staff", "доказано свежим числом"),
           "СТАЖЁР": ("lc stage", "канал есть · работа не свежа"),
           "ЧИСЛИТСЯ": ("lc list", "устав есть · доказать не может"),
           "ВАКАНСИЯ": ("lc vac", "упоминается · модуля нет")}
    cells = []
    for emp, (cls, note) in lbl.items():
        n = counts.get(emp, 0)
        cells.append('<div class="lcell"><div class="lk">%s</div><div style="font-size:22px;font-weight:700">%d'
                     ' <span class="%s">%s</span></div>'
                     '<div class="mut" style="font-size:10.5px;margin-top:5px">%s</div></div>'
                     % (esc(emp), n, cls, emp, esc(note)))
    head = '<div class="p-h">ЛЕСТНИЦА ЗАНЯТОСТИ — кто реально работает (механически, не на глаз)</div>'
    body = '<div class="ladder">%s</div>' % "".join(cells)
    body += ('<p class="mut" style="font-size:11px;margin-top:8px">Смен в памяти: %s · ok=%s (%.1f%%) · '
             'последняя смена %s · тиков СЕЛФ %s · свежесть = последнее число ≤%d дн.</p>'
             % (num(summary["shifts"]), num(summary["ok"]),
                100.0 * summary["ok"] / summary["shifts"] if summary["shifts"] else 0,
                esc(summary["last_shift"] or "—"), num(summary["ticks"]), FRESH_DAYS))
    return '<div class="panel">%s%s</div>' % (head, body)


def sec_team(charters, ev):
    cards = []
    for r in ROLES:
        ch = charts_ok(charters).get(r["key"])
        e = ev[r["key"]]
        rr = role_with_charter(r, charters)
        emp = employment(rr, e)
        score, checks = conscience_score(rr, e)
        emp_cls = {"В ШТАТЕ": "staff", "СТАЖЁР": "stage", "ЧИСЛИТСЯ": "list", "ВАКАНСИЯ": "vac"}[emp]
        stars = "★" * score + "☆" * (5 - score)
        mandate = ch.get("mandate") if ch else "нет устава — вакансия"
        laws = (ch.get("laws") or []) if ch else []
        laws_txt = " · ".join(esc(str(l)) for l in laws[:3])
        chk_names = ["УСТАВ", "В СТРОЮ", "КАНАЛ", "РАБОТА", "СВЕЖО"]
        cks = "".join('<div class="ck"><span class="%s">%s</span>%s</div>'
                      % ("ok" if c else "no", "✔" if c else "✘", esc(chk_names[i]))
                      for i, c in enumerate(checks))
        wire = {"cycle:shift": "цикл: БРИГАДИР (смена)",
                "cycle:via_brigade": "цикл: через БРИГАДИРА",
                "cycle:tick": "цикл: СЕЛФ-тик",
                "cycle:step": "цикл: отдельный шаг",
                "cycle:optin": "цикл: только по слову (--donor-zaliv)",
                "runner": "отдельный раннер (не в цикле)",
                "none": "не заведён"}.get(r["wired"], r["wired"])
        evline = ('<div class="ev"><b>канал:</b> %s · <b>работа:</b> последнее число %s · '
                  '<b>смен-с-числом:</b> %s · <b>эскалаций:</b> %s<br>'
                  '<b>проводка:</b> %s</div>'
                  % (esc(e["channel_desc"] or "—нет—"),
                     esc(e["last_real"] or "никогда"), num(e["samples"]), num(e["escalations"]),
                     esc(wire)))
        cards.append('<div class="tcard"><div class="thead">%s<span class="tname">%s</span>'
                     ' <span class="lc %s">%s</span></div>'
                     '<div class="stars %s">%s <span class="mut" style="font-size:10px">%d/5 совесть</span></div>'
                     '<div class="tmand">%s</div>'
                     '<div class="checks">%s</div>'
                     '%s</div>'
                     % (r["emoji"], esc(r["name_ru"]), emp_cls, emp,
                        "ok" if score >= 4 else ("warnc" if score >= 3 else "no"), stars, score,
                        esc(str(mandate)), cks, evline))
    head = '<div class="p-h">КОМАНДА — каждый на совесть (совесть x/5, по каналам доказательств)</div>'
    return '<div class="panel">%s<div class="team">%s</div></div>' % (head, "".join(cards))


def sec_edges(edges):
    cls_ru = {"lawful": ("ЗАКОННЫЕ (оба конца в цикле — передача механически возможна)", "ok"),
              "declared": ("ЗАЯВЛЕНЫ, НЕ ПРОВЕДЕНЫ (канал не доведён — один конец вне цикла)", "warnc"),
              "ghost": ("В ПРИЗРАК (конец = вакансия, модуля нет)", "no"),
              "external": ("ВНЕШНИЕ (Маркет / ОПЕРАТОР)", "mut")}
    blocks = []
    for cls, (title, tone) in cls_ru.items():
        group = [e for e in edges if e["cls"] == cls]
        rows = []
        for e in group:
            src_nm = ROSTER[e["src"]]["name_ru"] if e["src"] in ROSTER else EXTERNAL.get(e["src"], e["src"])
            if e["dst"] in ROSTER:
                dst_nm = ROSTER[e["dst"]]["name_ru"]
            else:
                dst_nm = EXTERNAL.get(e["dst"], e["dst"])
            rows.append('<div class="edge"><span class="%s">%s</span>'
                        '<span class="arrow">%s→</span><b>%s</b>'
                        '<span class="elabel">%s</span></div>'
                        % (tone, esc(src_nm), "⬅" if e["kind"] == "input" else "➜", esc(dst_nm),
                           esc(e["label"])))
        inner = ('<div class="estrip"><div class="p-h">%s <span class="chip">%d</span></div>'
                 '<div class="edges">%s</div></div>' % (esc(title), len(group), "".join(rows)))
        blocks.append(inner)
    head = '<div class="p-h">СВЯЗИ — из уставов (inputs/outputs), не придуманные</div>'
    return '<div class="panel">%s<div class="egrid">%s</div></div>' % (head, "".join(blocks))


def sec_tabel():
    rows = load_tabel()
    ts = tabel_summary(rows)
    if not rows:
        return ('<div class="panel"><div class="p-h">ТАБЕЛЬ</div>'
                '<p class="mut" style="font-size:11.5px">Пуст: канал не подключён (record_day OFF). '
                'Слово — зацепить хук в суточный цикл (ymarket_day_v1._append_journal), и каждая роль '
                'начнёт доказывать смену строкой в табеле.</p></div>')
    body = '<table class="tabel"><tr><th>дата</th><th>роль</th><th>статус</th><th>ошибка</th><th>след</th></tr>'
    for r in rows[-24:]:
        st = r.get("status")
        tone = {"ok": "ok", "skip": "warnc", "fail": "no"}.get(st, "mut")
        body += '<tr><td>%s</td><td>%s</td><td class="%s">%s</td><td>%s</td><td>%s</td></tr>' % (
            esc(r.get("date")), esc(r.get("role")), tone, esc(st),
            esc(r.get("error") or ""), esc(str(r.get("evidence") or "")[:70]))
    body += '</table>'
    head = ('<div class="p-h">ТАБЕЛЬ <span class="chip">%d дней · %d ролей</span></div>'
            % (ts["days"], ts["roles"]))
    return '<div class="panel">%s%s</div>' % (head, body)


def sec_footer(charters):
    sources = [
        ("память смен", SHIFT_PATH),
        ("дневной журнал", JOURNAL_PATH),
        ("tick-ledger СЕЛФ", TICKS_PATH),
        ("ТАБЕЛЬ", TABEL_PATH),
        ("html", OUT),
    ]
    rows = []
    for name, p in sources:
        try:
            exists = Path(p).exists()
            size = Path(p).stat().st_size if exists else -1
        except Exception:
            exists, size = False, -1
        rows.append('<div class="edge"><span class="%s">%s</span><span class="arrow">—</span>'
                    '<span class="elabel">%s (%s)</span></div>'
                    % ("ok" if exists else "no", esc(name), esc(str(p)),
                       "%d Б" % size if size >= 0 else "нет"))
    read_ok = sum(1 for r in rows if "ok" in r)
    return ('<div class="panel"><div class="p-h">ИСТОЧНИКИ (RUBICON: чистое чтение, 0₽; запись — только '
            'в ТАБЕЛЬ и html по слову)</div><div class="edges">%s</div></div>' % "".join(rows))


def render(charters=None, ev=None, edges=None, summary=None):
    """Собрать html-строку офиса (без записи). Ничего не пишет."""
    if charts_ok(charters):
        pass
    charts = charters if charts_ok(charters) else load_charters()
    evd, summ = (ev, summary) if (ev is not None and summary is not None) else gather_evidence(charts)
    ed = edges if edges is not None else build_edges(charts)
    P = palette()
    body = "".join([
        sec_ladder(evd, summ),
        sec_team(charts, evd),
        sec_edges(ed),
        sec_tabel(),
        sec_footer(charts),
    ])
    header = ("""<div class="box">╔═══════════════════════════════════════════════════════╗
║  ARBITER ▸ ВИРТУАЛЬНЫЙ ОФИС   <span class="t2">— кто в команде, кто с кем связан, кто реально работает</span>  ║
╚═══════════════════════════════════════════════════════╝</div>
<p class="sub">кадровая правда из живых артефактов · совесть по каналам доказательств · RUBICON: чтение (0₽)</p>""")
    return ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>ARBITER ▸ ВИРТУАЛЬНЫЙ ОФИС</title>%s%s</head><body><div class="wrap">%s%s</div></body></html>'
            % (css(P), extra_css(), header, body))


def summary_json(charters=None, ev=None, edges=None):
    """Машинная сводка для приёмки/наблюдения (чистое чтение)."""
    charts = charts_ok(charters) if charts_ok(charters) else load_charters()
    evd, summ = gather_evidence(charts) if ev is None else (ev, {})
    ed = build_edges(charts) if edges is None else edges
    out = {"roster": [], "edges": [], "summary": summ}
    for r in ROLES:
        rr = role_with_charter(r, charts)
        emp = employment(rr, evd.get(r["key"], {}))
        score, _ = conscience_score(rr, evd.get(r["key"], {}))
        out["roster"].append({
            "key": r["key"], "name_ru": r["name_ru"], "cluster": r["cluster"],
            "wired": r["wired"], "channel": r["channel"], "charter": r.get("charter") is not None,
            "employment": emp, "conscience": score, "samples": evd[r["key"]]["samples"],
            "last_real": evd[r["key"]]["last_real"], "escalations": evd[r["key"]]["escalations"],
        })
    for e in ed:
        out["edges"].append({"src": e["src"], "dst": e["dst"], "kind": e["kind"], "cls": e["cls"]})
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="ВИРТУАЛЬНЫЙ ОФИС ЯМ — рендер + машинная сводка")
    ap.add_argument("--render", action="store_true", help="собрать runtime/YM_VIRTUAL_OFFICE.html")
    ap.add_argument("--json", action="store_true", help="машинная сводка в stdout")
    args = ap.parse_args()

    charts = load_charters()
    evd, summ = gather_evidence(charts)
    if args.json:
        sj = summary_json(charts, evd, build_edges(charts))
        print(json.dumps(sj, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.render:
        doc = render(charts, evd, build_edges(charts), summ)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(doc, encoding="utf-8")
        print("YM virtual office -> %s" % OUT.relative_to(SOCC))
        for r in ROLES:
            e = evd[r["key"]]
            rr = role_with_charter(r, charts)
            print("  %-3s %-16s %-9s совесть %d/5 · последнее-число %s"
                  % (r["emoji"], r["name_ru"], employment(rr, e),
                     conscience_score(rr, e)[0], e["last_real"] or "никогда"))
        print("  смен %s · ok %s · последняя смена %s · тиков %s"
              % (num(summ["shifts"]), num(summ["ok"]), summ["last_shift"] or "—", num(summ["ticks"])))
        return 0
    # по умолчанию — печать текстовой сводки (не пишем ничего)
    for r in ROLES:
        e = evd[r["key"]]
        rr = role_with_charter(r, charts)
        print("%s %-16s [%-9s] совесть %d/5 · последнее %s"
              % (r["emoji"], r["name_ru"], employment(rr, e),
                 conscience_score(rr, e)[0], e["last_real"] or "никогда"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KPI DAY/WEEK/MONTH (ymarket_kpi_v1) — рост виден только в сравнении.

Оператор дословно: «у каждого есть KPI DAY, WEEK, MONTH». Суточный цикл уже пишет журнал дня
(ymarket_day_journal.jsonl). Этот модуль СВОРАЧИВАЕТ журнал в три окна — день, неделя, месяц —
и честно показывает тренд по каждому числу.

ЗАКОНЫ (наследуем у органа):
  • «Лучше ноль, чем ложь»: нет строк в окне → говорим «истории не хватает», а не рисуем 0.
  • «Нет числа без события»: считаем только по реально записанным дням журнала, ничего не выдумываем.
  • deterministic, без сети, без денег. Источник — journal (env YM_DAY_JOURNAL перекрывает, как в цикле).

Окно = по КАЛЕНДАРНЫМ дням от `today` (по умолчанию сегодня): DAY=1, WEEK=7, MONTH=30.
Тренд по числу = (последнее в окне − первое в окне); стрелка ▲/▼/= показывает направление.
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone, date, timedelta

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
REPORTS = ROOT / "MEMORY_WAVE/reports/mint/arbiter"

# Поля KPI: ключ в журнале → (человеческое имя, направление роста, единица).
# dir: +1 = больше лучше, -1 = меньше лучше (цель ноль/минимум), 0 = нейтрально (просто следим).
KPI_FIELDS = [
    ("cards_tracked",        "карточек веду",        +1, ""),
    ("cards_live",           "живых карточек",       +1, ""),
    ("cards_live_verified",  "доказанно живых",      +1, ""),
    ("cards_errored",        "с ошибкой",            -1, ""),   # цель 0
    ("ready_to_publish",     "готовы к заливу",      +1, ""),
    ("avg_content_rating",   "заполненность",        +1, "%"),
    ("quality_index",        "индекс качества",      +1, ""),
    ("urgent_orders",        "горящих заказов",      -1, ""),
]
_ARROW = {1: "▲", -1: "▼", 0: "="}
WINDOWS = [("DAY", "ДЕНЬ", 1), ("WEEK", "НЕДЕЛЯ", 7), ("MONTH", "МЕСЯЦ", 30)]


def journal_path():
    p = os.environ.get("YM_DAY_JOURNAL")
    return Path(p) if p else (REPORTS / "ymarket_day_journal.jsonl")


def _read_rows(path=None):
    p = Path(path) if path else journal_path()
    if not p.exists():
        return []
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except Exception:
            continue  # битую строку молча пропускаем (fail-soft), но не роняем KPI
        if isinstance(obj, dict):
            rows.append(obj)
        # валидный JSON, но не объект (число/строка/массив) — не наша строка дня, тоже пропускаем
    return rows


def _asdict(v):
    """Fail-soft: не-словарь (битый/частичный журнал) → {} вместо падения (закон L6)."""
    return v if isinstance(v, dict) else {}


def _row_date(row):
    """Дата строки как date. Берём поле date, иначе ts[:10]. Нечитаемо → None (не выдумываем)."""
    if not isinstance(row, dict):
        return None  # валидный-но-не-объект journal-строке дата взяться неоткуда → молча выкидываем
    s = row.get("date") or (row.get("ts") or "")[:10]
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _row_ts(row):
    """ts строки как сортируемая строка ISO (для тай-брейка одинаковых дат). Нет → ''."""
    if not isinstance(row, dict):
        return ""
    ts = row.get("ts")
    return ts if isinstance(ts, str) else ""


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _fmt(v, unit=""):
    if v is None:
        return "—"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return f"{v}{unit}"


def _window_rows(rows, days, today=None):
    """Строки, попавшие в окно [today-(days-1) .. today]. Хронологический порядок."""
    if today is None:
        today = datetime.now(timezone.utc).date()
    lo = today - timedelta(days=days - 1)
    out = [(d, r) for r in rows for d in (_row_date(r),) if d is not None and lo <= d <= today]
    out.sort(key=lambda dr: dr[0])
    return [r for _, r in out]


def rollup(window_days, rows=None, today=None):
    """Свернуть KPI за окно. Возвращает {field: {last, first, min, max, avg, trend, dir, ...}}.

    Пустое окно → {"_empty": True, "days_present": 0}: честный «истории не хватает», не нули.
    """
    rows = rows if rows is not None else _read_rows()
    win = _window_rows(rows, window_days, today=today)
    if not win:
        return {"_empty": True, "days_present": 0, "window_days": window_days}
    # Один КАЛЕНДАРНЫЙ день = одна точка: несколько прогонов за сутки → берём последний снимок дня.
    # Иначе «дней в окне» врёт (считало бы прогоны, а не дни) — нарушение «нет числа без события».
    by_date = {}
    for r in win:                       # один день = один снимок; при равной дате побеждает поздний ts
        d = _row_date(r)
        if d not in by_date or _row_ts(r) >= _row_ts(by_date[d]):
            by_date[d] = r
    win = [by_date[d] for d in sorted(by_date)]
    out = {"_empty": False, "days_present": len(win), "window_days": window_days,
           "from": _row_date(win[0]).isoformat(), "to": _row_date(win[-1]).isoformat(),
           "burning_days": sum(1 for r in win if _num(r.get("burning"))), "fields": {}}
    for key, label, direction, unit in KPI_FIELDS:
        series = [_num(_asdict(r.get("kpis")).get(key)) for r in win]
        known = [v for v in series if v is not None]
        last = next((v for v in reversed(series) if v is not None), None)
        first = next((v for v in series if v is not None), None)
        trend = (last - first) if (last is not None and first is not None) else None
        out["fields"][key] = {
            "label": label, "unit": unit, "dir": direction,
            "last": last, "first": first,
            "min": (min(known) if known else None), "max": (max(known) if known else None),
            "avg": (round(sum(known) / len(known), 1) if known else None),
            "trend": trend, "known_days": len(known),
        }
    return out


def _trend_mark(field):
    """Стрелка + оценка «в нужную ли сторону». Нейтральное направление — просто стрелка."""
    t = field.get("trend")
    if t is None or t == 0:
        return "="
    sign = 1 if t > 0 else -1
    good = (sign == field["dir"]) if field["dir"] != 0 else None
    val = int(t) if float(t).is_integer() else round(t, 1)
    tag = "" if good is None else (" ✅" if good else " ❗")
    return f"{_ARROW[sign]}{abs(val)}{field['unit']}{tag}"


def render_window(win_label, roll):
    """Один блок окна для человека/Телеграма."""
    if roll.get("_empty"):
        return f"• {win_label}: истории не хватает (0 записанных дней в окне)"
    L = [f"• {win_label} · дней в окне: {roll['days_present']} "
         f"({roll['from']}→{roll['to']}) · дней с «горит»: {roll['burning_days']}"]
    for key, label, direction, unit in KPI_FIELDS:
        f = roll["fields"].get(key) or {}
        if f.get("known_days"):
            L.append(f"    {label}: {_fmt(f['last'], unit)} "
                     f"(тренд {_trend_mark(f)}; ср {_fmt(f['avg'], unit)})")
    return "\n".join(L)


def render_all(rows=None, today=None):
    """DAY+WEEK+MONTH одним листом. Заголовок честно помечает пустую историю."""
    rows = rows if rows is not None else _read_rows()
    if not rows:
        return ("📈 KPI DAY/WEEK/MONTH: журнал пуст — ещё ни одного дня не записано.\n"
                "Проведи суточный цикл (ymarket_day_v1), и появится точка отсчёта.")
    blocks = [render_window(ru, rollup(days, rows=rows, today=today)) for _, ru, days in WINDOWS]
    return "📈 KPI DAY / WEEK / MONTH\n" + "\n".join(blocks)


def summary_line(rows=None, today=None):
    """Однострочник для подвала командного отчёта: главное по трём окнам без простыней."""
    rows = rows if rows is not None else _read_rows()
    parts = []
    for _, ru, days in WINDOWS:
        r = rollup(days, rows=rows, today=today)
        parts.append(f"{ru}:—" if r.get("_empty") else f"{ru}:{r['days_present']}д")
    return "KPI " + " · ".join(parts)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="KPI DAY/WEEK/MONTH из журнала суточного цикла")
    ap.add_argument("--json", action="store_true", help="сырые свёртки JSON")
    args = ap.parse_args()
    if args.json:
        rows = _read_rows()
        print(json.dumps({ru: rollup(d, rows=rows) for _, ru, d in WINDOWS},
                         ensure_ascii=False, indent=2))
    else:
        print(render_all())

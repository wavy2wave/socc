#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПАМЯТЬ СМЕНЫ (YM_SHIFT_MEMORY) — цех помнит вчера, иначе не видит тренда.

Зачем: КОНТРОЛЁР умеет считать падение индекса за сутки, но сравнивать было не с чем —
историю никто не хранил. Без памяти цех каждое утро начинает с нуля: не видит, что индекс
третий день ползёт вниз, что одна и та же позиция четвёртый раз без габаритов, что вчерашняя
просрочка не единичная.

Память НЕ дублирует ymarket_state_v1 (тот про карточки и залив). Здесь — журнал СМЕН:
что видел цех и что решил, по дням.

ЗАКОНЫ:
  M1 append-only: смены не переписываются задним числом (иначе тренд — фикция).
  M2 атомарная запись (tmp + rename): прерывание не рвёт журнал.
  M3 не выдумываем: нет данных за период → None, а не ноль (ноль — это утверждение).
  M4 обрезка по объёму, а не по «удобству»: держим последние N смен, старые уходят в архив-строку.

Формат: JSON-файл {shifts: [...]}, где каждая смена — снимок фактов + решения.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "ymarket_shift_memory.json"
MAX_SHIFTS = 400          # ~год работы при 1 смене/сутки; дальше — обрезка (M4)
SCHEMA = "ymarket.shift.memory.v1"


def _path(path=None):
    if path:
        return Path(path)
    env = os.environ.get("YM_SHIFT_MEMORY")
    return Path(env) if env else DEFAULT_PATH


def load(path=None):
    """Прочитать журнал. Нет файла/битый → пустой журнал (не падаем, но и не врём)."""
    p = _path(path)
    if not p.exists():
        return {"schema": SCHEMA, "shifts": [], "trimmed": 0}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"schema": SCHEMA, "shifts": [], "trimmed": 0,
                "load_error": f"{type(e).__name__}: {e}"}
    if not isinstance(data, dict) or "shifts" not in data:
        return {"schema": SCHEMA, "shifts": [], "trimmed": 0,
                "load_error": "неожиданная структура файла"}
    return data


def _atomic_write(p, payload):
    """M2: пишем во временный файл рядом и переименовываем — журнал не рвётся."""
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".ymshift_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def snapshot(report):
    """Выжать из отчёта смены то, что имеет смысл помнить (не весь отчёт — он большой)."""
    steps = report.get("steps") or {}

    def _rating():
        c = steps.get("CONTROLLER") or {}
        for row in (c.get("campaigns") or []):
            if isinstance(row.get("rating"), (int, float)):
                return float(row["rating"])
        return None

    disp = (steps.get("DISPATCHER") or {}).get("counts") or {}
    stock = steps.get("STOCKMAN") or {}
    price = steps.get("PRICER") or {}
    merch = steps.get("MERCHANDISER") or {}

    return {
        "at": report.get("at") or datetime.now().isoformat(),
        "dry": bool(report.get("dry")),
        "commit": bool(report.get("commit")),
        "ok": bool(report.get("ok")),
        "quality_rating": _rating(),
        "orders": {
            "overdue": disp.get("overdue"), "critical": disp.get("critical"),
            "warn": disp.get("warn"), "unknown_deadline": disp.get("unknown_deadline"),
        },
        "stock": {
            "planned": stock.get("planned"), "zeroed": stock.get("zeroed"),
            "unknown_source": stock.get("unknown_source"),
        },
        "pricing": {
            "allowed": price.get("allowed"), "refused": price.get("refused"),
            "avg_profit": (price.get("agg") or {}).get("avg_profit"),
        },
        "assortment": {
            "approved": (merch.get("agg") or {}).get("approved"),
            "rejected": (merch.get("agg") or {}).get("rejected"),
            "needs_data": (merch.get("agg") or {}).get("needs_data"),
        },
        "escalations": [{"role": e.get("role"), "kind": e.get("kind")}
                        for e in (report.get("escalations") or [])],
        "errors": len(report.get("errors") or []),
    }


def record(report, path=None, max_shifts=MAX_SHIFTS):
    """M1: дописать смену в конец журнала. Прошлое не трогаем."""
    doc = load(path)
    doc.setdefault("schema", SCHEMA)
    doc.setdefault("shifts", [])
    doc["shifts"].append(snapshot(report))
    if len(doc["shifts"]) > max_shifts:          # M4
        cut = len(doc["shifts"]) - max_shifts
        doc["shifts"] = doc["shifts"][cut:]
        doc["trimmed"] = doc.get("trimmed", 0) + cut
    _atomic_write(_path(path), doc)
    return doc


def quality_history(path=None, limit=None):
    """История индекса в формате, который ждёт controller.trend(): [{at, rating}]."""
    doc = load(path)
    rows = [{"at": s["at"], "rating": s["quality_rating"]}
            for s in doc.get("shifts", []) if s.get("quality_rating") is not None]
    return rows[-limit:] if limit else rows


def recurring_problems(path=None, days=7, min_times=3):
    """Что повторяется. Разовая просрочка — случай; третья за неделю — система.

    M3: нет смен за период → возвращаем пустой список И честный признак no_data.
    """
    doc = load(path)
    edge = datetime.now() - timedelta(days=days)
    counts, seen = {}, 0
    for s in doc.get("shifts", []):
        try:
            when = datetime.fromisoformat(str(s.get("at"))[:19])
        except ValueError:
            continue
        if when < edge:
            continue
        seen += 1
        for e in s.get("escalations") or []:
            key = (e.get("role"), e.get("kind"))
            counts[key] = counts.get(key, 0) + 1
    items = [{"role": r, "kind": k, "times": n, "of_shifts": seen}
             for (r, k), n in counts.items() if n >= min_times]
    items.sort(key=lambda x: -x["times"])
    return {"no_data": seen == 0, "shifts_seen": seen, "days": days, "problems": items}


def streak(path=None, field="ok", value=True):
    """Сколько смен подряд держится состояние (например, сколько дней без сбоев)."""
    doc = load(path)
    n = 0
    for s in reversed(doc.get("shifts", [])):
        if s.get(field) == value:
            n += 1
        else:
            break
    return n


def summary(path=None, days=7):
    """Короткая сводка «что было за неделю» — для утреннего листа БРИГАДИРА."""
    doc = load(path)
    edge = datetime.now() - timedelta(days=days)
    picked = []
    for s in doc.get("shifts", []):
        try:
            if datetime.fromisoformat(str(s.get("at"))[:19]) >= edge:
                picked.append(s)
        except ValueError:
            continue
    if not picked:
        return {"no_data": True, "days": days,
                "note": "смен за период нет — сравнивать не с чем (M3)"}

    ratings = [s["quality_rating"] for s in picked if s.get("quality_rating") is not None]
    overdue = [s["orders"]["overdue"] for s in picked
               if isinstance((s.get("orders") or {}).get("overdue"), int)]
    profits = [s["pricing"]["avg_profit"] for s in picked
               if isinstance((s.get("pricing") or {}).get("avg_profit"), (int, float))]
    return {
        "no_data": False, "days": days, "shifts": len(picked),
        "quality": {"first": ratings[0] if ratings else None,
                    "last": ratings[-1] if ratings else None,
                    "min": min(ratings) if ratings else None},
        "overdue_total": sum(overdue) if overdue else None,
        "avg_profit": round(sum(profits) / len(profits), 2) if profits else None,
        "clean_shifts": sum(1 for s in picked if s.get("ok") and not s.get("escalations")),
        "recurring": recurring_problems(path, days=days)["problems"],
    }


def render(summary_result):
    if summary_result.get("no_data"):
        return f"📓 ПАМЯТЬ: за {summary_result['days']} дн. смен нет — тренд считать не из чего"
    q = summary_result["quality"]
    lines = [f"📓 ПАМЯТЬ за {summary_result['days']} дн.: смен {summary_result['shifts']} · "
             f"чистых {summary_result['clean_shifts']}"]
    if q["first"] is not None and q["last"] is not None:
        delta = round(q["last"] - q["first"], 1)
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        lines.append(f"   индекс: {q['first']} {arrow} {q['last']} (мин {q['min']})")
    if summary_result.get("overdue_total"):
        lines.append(f"   просрочек всего: {summary_result['overdue_total']}")
    if summary_result.get("avg_profit") is not None:
        lines.append(f"   средняя прибыль позиции: {summary_result['avg_profit']} ₽")
    for p in summary_result.get("recurring", [])[:5]:
        lines.append(f"   🔁 повторяется: [{p['role']}] {p['kind']} — "
                     f"{p['times']} раз из {p['of_shifts']} смен")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if "--summary" in sys.argv:
        print(render(summary()))
        sys.exit(0)
    if "--history" in sys.argv:
        print(json.dumps(quality_history(), ensure_ascii=False, indent=2))
        sys.exit(0)

    # Демонстрация на временном журнале — канон не трогаем.
    import tempfile as _tf
    tmp = Path(_tf.mkdtemp()) / "demo_shift_memory.json"
    base = datetime.now()
    for i, (rating, overdue) in enumerate([(98, 0), (96, 1), (94, 1), (92, 2)]):
        record({
            "at": (base - timedelta(days=3 - i)).isoformat(),
            "dry": True, "commit": False, "ok": True,
            "steps": {
                "CONTROLLER": {"campaigns": [{"campaignId": "C1", "rating": rating}]},
                "DISPATCHER": {"counts": {"overdue": overdue, "critical": 0, "warn": 1,
                                          "unknown_deadline": 1}},
                "STOCKMAN": {"planned": 10, "zeroed": 2, "unknown_source": 1},
                "PRICER": {"allowed": 8, "refused": 2, "agg": {"avg_profit": 300 + i * 10}},
            },
            "escalations": ([{"role": "DISPATCHER", "kind": "UNKNOWN_DEADLINE"}] +
                            ([{"role": "DISPATCHER", "kind": "URGENT_ORDER"}] if overdue else [])),
            "errors": [],
        }, path=tmp)

    print(render(summary(path=tmp)))
    print("\nисторию индекса подхватывает КОНТРОЛЁР:")
    hist = quality_history(path=tmp)
    print(json.dumps(hist[-2:], ensure_ascii=False))
    import ymarket_role_controller_v1 as controller
    tr = controller.trend(92, hist)
    print(f"тренд: {tr['note']}")
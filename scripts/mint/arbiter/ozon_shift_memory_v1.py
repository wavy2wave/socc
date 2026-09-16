#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПАМЯТЬ СМЕНЫ ОЗОН (OZON_SHIFT_MEMORY) — магазин помнит вчера, иначе не видит тренда.

Зачем: менеджерский тик знает состояние СЕЙЧАС (ozon_state), но чтобы увидеть тренд — индекс третий
день ползёт к красному, отгрузки просели, одна ниша четвёртый раз без наличия — нужна история СМЕН.
ozon_state держит карточки и дневные нормы; здесь — журнал того, ЧТО менеджер видел и ЧТО решил, по дням.

Зеркалит ymarket_shift_memory_v1 дословно (те же 4 закона, атомарная запись, честные None), меняет
лишь СНИМОК смены под сигналы Озона: распределение цветов индекса, карточки на витрине/с ошибками,
дневная норма (uploaded/shipped/delivered/fixed), эскалации КОНТРОЛЁРА.

ЗАКОНЫ:
  M1 append-only: смены не переписываются задним числом (иначе тренд — фикция).
  M2 атомарная запись (tmp + os.replace): прерывание не рвёт журнал.
  M3 не выдумываем: нет данных за период → None, а не ноль (ноль — это утверждение).
  M4 обрезка по объёму: держим последние N смен, старые считаем в trimmed.

Формат: JSON {schema, shifts:[...], trimmed}. env OZON_SHIFT_MEMORY перекрывает путь (тесты не в канон).
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "ozon_shift_memory.json"
MAX_SHIFTS = 400          # ~год при 1 смене/сутки; дальше — обрезка (M4)
SCHEMA = "ozon.shift.memory.v1"


def _path(path=None):
    if path:
        return Path(path)
    env = os.environ.get("OZON_SHIFT_MEMORY")
    return Path(env) if env else DEFAULT_PATH


def load(path=None):
    """Прочитать журнал. Нет файла/битый/чужая структура → пустой журнал (не падаем, не врём)."""
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
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".ozshift_", suffix=".tmp")
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
    """Выжать из отчёта тика то, что имеет смысл помнить (не весь отчёт — он большой).

    report — то, что отдаёт ozon_manager.tick(): {at, dry, commit, ok, self_status(kpis),
    daily(норма дня), escalations:[{role,kind}], errors:[...]}. Всё None-безопасно (M3).
    """
    ss = report.get("self_status") or report.get("kpis") or {}
    daily = report.get("daily") or ss.get("daily_today") or {}

    def _g(d, k):
        v = (d or {}).get(k)
        return v if isinstance(v, (int, float)) else None

    return {
        "at": report.get("at") or datetime.now().isoformat(),
        "dry": bool(report.get("dry", True)),
        "commit": bool(report.get("commit")),
        "ok": bool(report.get("ok")),
        "cards": {
            "tracked": _g(ss, "tracked"),
            "on_shelf": _g(ss, "cards_on_shelf"),
            "errored": _g(ss, "cards_errored"),
            "ready": _g(ss, "ready_to_publish"),
            "need_mapping": _g(ss, "need_mapping"),
        },
        "index": {
            "red": _g(ss, "index_red"),          # красных индексов (карточку прячут из органики)
        },
        "norm": {
            "uploaded": _g(daily, "uploaded"),
            "shipped": _g(daily, "shipped"),
            "delivered": _g(daily, "delivered"),
            "fixed": _g(daily, "fixed"),
        },
        "action": (report.get("action") or {}).get("action") if isinstance(
            report.get("action"), dict) else report.get("action"),
        "escalations": [{"role": e.get("role"), "kind": e.get("kind")}
                        for e in (report.get("escalations") or [])],
        "errors": len(report.get("errors") or []),
    }


def record(report, path=None, max_shifts=MAX_SHIFTS):
    """M1: дописать смену в конец журнала. Прошлое не трогаем. M4: обрезка по объёму."""
    doc = load(path)
    doc.setdefault("schema", SCHEMA)
    doc.setdefault("shifts", [])
    doc["shifts"].append(snapshot(report))
    if len(doc["shifts"]) > max_shifts:
        cut = len(doc["shifts"]) - max_shifts
        doc["shifts"] = doc["shifts"][cut:]
        doc["trimmed"] = doc.get("trimmed", 0) + cut
    _atomic_write(_path(path), doc)
    return doc


def index_history(path=None, limit=None):
    """История красных индексов по сменам: [{at, red}] — чтобы видеть, растёт ли невидимость."""
    doc = load(path)
    rows = [{"at": s["at"], "red": (s.get("index") or {}).get("red")}
            for s in doc.get("shifts", []) if (s.get("index") or {}).get("red") is not None]
    return rows[-limit:] if limit else rows


def recurring_problems(path=None, days=7, min_times=3):
    """Что повторяется. Разовая эскалация — случай; третья за неделю — система. M3: no_data честно."""
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
    """Сколько смен подряд держится состояние (например, сколько дней подряд ok)."""
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

    def _series(path_keys):
        out = []
        for s in picked:
            v = s
            for k in path_keys:
                v = (v or {}).get(k) if isinstance(v, dict) else None
            if isinstance(v, (int, float)):
                out.append(v)
        return out

    reds = _series(["index", "red"])
    uploaded = _series(["norm", "uploaded"])
    shipped = _series(["norm", "shipped"])
    delivered = _series(["norm", "delivered"])
    on_shelf = _series(["cards", "on_shelf"])
    return {
        "no_data": False, "days": days, "shifts": len(picked),
        "index_red": {"first": reds[0] if reds else None,
                      "last": reds[-1] if reds else None,
                      "max": max(reds) if reds else None},
        "on_shelf_last": on_shelf[-1] if on_shelf else None,
        "uploaded_total": sum(uploaded) if uploaded else None,
        "shipped_total": sum(shipped) if shipped else None,
        "delivered_total": sum(delivered) if delivered else None,
        "clean_shifts": sum(1 for s in picked if s.get("ok") and not s.get("escalations")),
        "recurring": recurring_problems(path, days=days)["problems"],
    }


def render(summary_result):
    if summary_result.get("no_data"):
        return f"📓 ПАМЯТЬ ОЗОН: за {summary_result['days']} дн. смен нет — тренд считать не из чего"
    r = summary_result["index_red"]
    lines = [f"📓 ПАМЯТЬ ОЗОН за {summary_result['days']} дн.: смен {summary_result['shifts']} · "
             f"чистых {summary_result['clean_shifts']}"]
    if r["first"] is not None and r["last"] is not None:
        delta = r["last"] - r["first"]
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        lines.append(f"   красный индекс: {r['first']} {arrow} {r['last']} (пик {r['max']}) "
                     f"— рост = растёт невидимость")
    norm = []
    if summary_result.get("uploaded_total") is not None:
        norm.append(f"залито {summary_result['uploaded_total']}")
    if summary_result.get("shipped_total") is not None:
        norm.append(f"отгружено {summary_result['shipped_total']}")
    if summary_result.get("delivered_total") is not None:
        norm.append(f"доставлено {summary_result['delivered_total']}")
    if norm:
        lines.append("   норма недели: " + " · ".join(norm))
    if summary_result.get("on_shelf_last") is not None:
        lines.append(f"   на витрине сейчас: {summary_result['on_shelf_last']}")
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
        print(json.dumps(index_history(), ensure_ascii=False, indent=2))
        sys.exit(0)

    # Демонстрация на временном журнале — канон не трогаем.
    import tempfile as _tf
    tmp = Path(_tf.mkdtemp()) / "demo_ozon_shift.json"
    base = datetime.now()
    for i, (red, uploaded, shipped) in enumerate([(0, 3, 1), (1, 2, 2), (2, 4, 1), (3, 1, 3)]):
        record({
            "at": (base - timedelta(days=3 - i)).isoformat(),
            "dry": True, "commit": False, "ok": True,
            "self_status": {"tracked": 10, "cards_on_shelf": 6, "cards_errored": 0,
                            "ready_to_publish": 2, "need_mapping": 0, "index_red": red},
            "daily": {"uploaded": uploaded, "shipped": shipped,
                      "delivered": max(0, shipped - 1), "fixed": 0},
            "action": "HOLD",
            "escalations": ([{"role": "PRICER-INDEX", "kind": "INDEX_RED"}] if red >= 2 else []),
            "errors": [],
        }, path=tmp)

    print(render(summary(path=tmp)))
    print("\nистория красного индекса (растущая невидимость):")
    print(json.dumps(index_history(path=tmp), ensure_ascii=False))

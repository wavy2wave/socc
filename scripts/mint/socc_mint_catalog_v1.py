#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT catalog loader V1 — боезапас органа: индекс вычищенных связок (уровень ДОКАЗАННЫХ ГИПОТЕЗ).

Каталог рождён воркфлоу mint-connection-catalog (16 сфер РФ → состязательный аудит законности и
достижимости → ранг). КАЖДАЯ связка в catalog[] прошла: (1) фальсифицируемый тест достижимости,
(2) состязательного аудитора красных линий, (3) red_line=='none'. Отбракованное лежит в rejected[]
с причиной — орган прозрачно показывает, что и почему отрезал (это и есть фишка: он сам себя полицует).

ГРАНИЦА ЧЕСТНОСТИ: каталог — это вычищенные ГИПОТЕЗЫ (стадия PROSPECTOR p2 «достижимость»), не доход.
Доход появляется только когда конкретная связка дойдёт до verified=true в revenue_ledger (MERCHANT+LEDGER).
Товарные связки (maps_to_venture=ozon-dropship-RU) становятся кандидатами PROSPECTOR лишь с РЕАЛЬНОЙ
закупочной ценой и сигналом спроса — их даёт скан поставщика, не этот файл.

Чистый stdlib. Без сети, без LLM.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT = ROOT / "MEMORY_WAVE/reports/mint/connection_catalog_v1.json"


def load(path=None):
    """Загрузить каталог. Если файла нет — честный пустой ответ status='absent' (не падаем)."""
    p = Path(path) if path else DEFAULT
    if not p.exists():
        return {"status": "absent", "path": str(p), "catalog": [], "fire_first": [],
                "rejected": [], "stats": {}, "doctrine_note": ""}
    data = json.loads(p.read_text(encoding="utf-8"))
    data["status"] = "loaded"
    data["path"] = str(p)
    data.setdefault("catalog", [])
    data.setdefault("fire_first", [])
    data.setdefault("rejected", [])
    data.setdefault("stats", {})
    data.setdefault("doctrine_note", "")
    return data


def by_venture(data=None):
    """Сгруппировать связки по вселенной (maps_to_venture). Видно, какая вселенная богаче связками."""
    data = data or load()
    out = {}
    for c in data["catalog"]:
        out.setdefault(c.get("maps_to_venture", "?"), []).append(c)
    return out


def top(data=None, n=12):
    """Топ связок по rank_score (скорость × капитал × уверенность аудитора)."""
    data = data or load()
    return sorted(data["catalog"], key=lambda c: c.get("rank_score", 0), reverse=True)[:n]


def fire_first(data=None):
    """Список «огонь первым» — что запускать сегодня (выбор синтез-агента по доктрине создателя)."""
    return (data or load())["fire_first"]


def to_prospect_candidates(data=None, venture="ozon-dropship-RU"):
    """Товарные связки указанной вселенной → заготовки кандидатов PROSPECTOR.

    ВНИМАНИЕ: cost/demand тут не проставлены (их даёт реальный скан поставщика). Возвращаются как
    скелеты для t0 — PROSPECTOR отсеет их как примитив, пока нет cost>0 и сигнала спроса. Это честно:
    каталог даёт НАПРАВЛЕНИЕ, а не готовую закупку.
    """
    data = data or load()
    out = []
    for c in data["catalog"]:
        if c.get("maps_to_venture") != venture:
            continue
        out.append({"name": c.get("title"), "cost": 0, "url": "",
                    "demand_signal": None, "_from_catalog": True,
                    "_hint_demand": c.get("demand_signal"), "_hint_test": c.get("falsifiable_test")})
    return out


def summary(data=None):
    """Сводка боезапаса: статистика, связок по вселенным, отбраковка по красным линиям, доктрина."""
    data = data or load()
    rej_by_line = {}
    for r in data["rejected"]:
        k = r.get("red_line", "?")
        rej_by_line[k] = rej_by_line.get(k, 0) + 1
    return {
        "status": data["status"],
        "path": data.get("path"),
        "stats": data["stats"],
        "by_venture": {k: len(v) for k, v in by_venture(data).items()},
        "rejected_by_red_line": rej_by_line,
        "fire_first_count": len(data["fire_first"]),
        "doctrine_note": data["doctrine_note"],
    }


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(summary(load(arg)), ensure_ascii=False, indent=2))

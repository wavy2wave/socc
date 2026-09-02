#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ИСТОЧНИК ГОЛОВЫ (ymarket_head_source_v1) — мост wb_scout → ГОЛОВА (нос спроса → шорт-лист).

ГОЛОВА (ymarket_role_head_v1) сама кандидатов не ищет: она их РАНЖИРУЕТ. Кандидатов ей подаёт
источник-шов `head_source_fn` — функция без аргументов → список связок уровня wb_scout. Этот модуль
и есть такой источник: он берёт суточный «список охоты» оператора (какие запросы/категории WB
прочёсываем сегодня), прогоняет каждый пункт через wb_scout и сводит в один дедуплицированный
список кандидатов. ГОЛОВА дальше сама зовёт ТОВАРОВЕДА (физика) и сливает с окном ТРЕНД-СКАУТА.

ГРАНИЦА (RUBICON цел): это ЧТЕНИЕ публичного WB (0₽, ничего наружу не пишем, денег не двигаем).
Но это ЖИВАЯ сеть — поэтому по умолчанию НЕ подключён к суточному циклу (как и trend_source_fn):
оператор включает его флагом, когда готов. Без него ГОЛОВА честно докладывает NO_HEAD_SOURCE.

ЧЕСТНОСТЬ ИСТОЧНИКА: сеть — через шов `fetch_fn` (по умолчанию wb_scout.scout). Тесты подают
фейковый fetch_fn и не трогают сеть (0₽, детерминировано). wb_scout сам fail-soft: сеть легла →
вернёт пусто, не упадёт. Поэтому «рынок пуст» и «сеть недоступна» отсюда НЕ различить — это
задокументированное ограничение read-плоскости (точный объём даст платный адаптер спроса).

Список охоты: env YM_HEAD_HUNT_PATH (JSON) → иначе встроенный дефолт по теме плёнок/авто-тюнинга.
Формат: [{"query": "плёнка тонировочная", "limit": 40}, {"category": 1234, "city": "msk"}].
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Встроенный список охоты: тема органа (плёнки/авто-тюнинг). Оператор перекрывает файлом
# (YM_HEAD_HUNT_PATH) — код трогать не нужно. Держим короткий и осмысленный, а не «всё подряд».
DEFAULT_HUNT = [
    {"query": "плёнка тонировочная автомобильная"},
    {"query": "антигравийная плёнка авто"},
    {"query": "плёнка карбон 3d для авто"},
    {"query": "виниловая плёнка для авто"},
    {"query": "бронеплёнка фары"},
]
DEFAULT_CITY = "msk"
DEFAULT_LIMIT = 40
DEFAULT_UNIVERSE_CAP = 120          # потолок вселенной кандидатов за сутки (не раздуваем вход ранга)


def hunt_path():
    """Путь к списку охоты. env YM_HEAD_HUNT_PATH перекрывает (оператор/песочница/тесты)."""
    p = os.environ.get("YM_HEAD_HUNT_PATH")
    return Path(p) if p else (HERE / "ymarket_head_hunt.json")


def load_hunt(path=None):
    """Список охоты: файл (если задан/существует и валиден) → иначе встроенный дефолт (fail-soft).

    Валидный пункт — dict, где есть непустой 'query' ЛИБО 'category'. Мусор молча отсеиваем.
    Никогда не роняемся и никогда не возвращаем пусто: нет файла/битый → DEFAULT_HUNT.
    """
    p = Path(path) if path else hunt_path()
    items = None
    try:
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):                 # допускаем {"hunt": [...]} обёртку
                raw = raw.get("hunt")
            if isinstance(raw, list):
                items = [x for x in raw if isinstance(x, dict)
                         and (str(x.get("query") or "").strip() or x.get("category"))]
    except Exception:
        items = None
    return items if items else list(DEFAULT_HUNT)


def _key(cand):
    """Ключ дедупликации: sku (nmId WB) если есть, иначе нормализованное имя.

    Имя нормализуем агрессивно (ё→е, нижний регистр, схлопнутые пробелы) — иначе «Плёнка  Матовая»
    и «плёнка матовая» уехали бы в разные ключи, и один товар задвоился бы в шорт-листе ГОЛОВЫ.
    """
    sku = cand.get("sku")
    if sku:
        return ("sku", str(sku))
    name = (cand.get("name") or "").lower().replace("ё", "е")
    name = " ".join(name.split())                     # схлопнуть любые пробелы/переносы в один
    return ("name", name)


def _strength(cand):
    ds = cand.get("demand_signal") or {}
    try:
        return float(ds.get("strength") or 0)
    except (TypeError, ValueError):
        return 0.0


def collect(hunt=None, city=None, limit=None, profit_target=600, min_profit=200,
            fetch_fn=None, universe_cap=None):
    """Прочесать список охоты → единый дедуплицированный список кандидатов wb_scout-схемы.

    fetch_fn(**kw) — шов сети (по умолчанию wb_scout.scout). Должен вернуть dict с ключом
    'candidates' (как wb_scout.scout) ИЛИ сразу список кандидатов. Любой пункт может упасть/пусто —
    остальные всё равно собираются (fail-soft поштучно). Дубли по sku/имени схлопываем, оставляя
    экземпляр с БОЛЬШИМ demand strength (сильнейший сигнал побеждает). Возвращает список (не dict):
    именно это ждёт head.plan_day от head_source_fn (после обёртки в thunk — см. build_source_fn).
    """
    hunt = hunt if hunt is not None else load_hunt()
    city = city or DEFAULT_CITY
    limit = int(limit or DEFAULT_LIMIT)
    cap = int(universe_cap or DEFAULT_UNIVERSE_CAP)
    if fetch_fn is None:
        import wb_scout_v1 as wb                       # ленивый импорт: сеть тянем только по факту
        fetch_fn = wb.scout

    best = {}                                          # ключ → лучший кандидат
    for item in hunt:
        kw = {
            "query": (str(item.get("query")).strip() if item.get("query") else None),
            "category": item.get("category"),
            "city": item.get("city") or city,
            "limit": int(item.get("limit") or limit),
            "profit_target": profit_target,
            "min_profit": min_profit,
        }
        kw = {k: v for k, v in kw.items() if v is not None}
        try:
            res = fetch_fn(**kw)
        except Exception:
            continue                                   # пункт упал → пропускаем, охота продолжается
        cands = res.get("candidates") if isinstance(res, dict) else res
        if not isinstance(cands, list):
            continue
        for c in cands:
            if not isinstance(c, dict):
                continue
            k = _key(c)
            prev = best.get(k)
            if prev is None or _strength(c) > _strength(prev):
                best[k] = c

    out = list(best.values())
    out.sort(key=_strength, reverse=True)              # сильнейший спрос первым (ранг всё равно за ГОЛОВОЙ)
    return out[:cap]


def build_source_fn(hunt=None, city=None, limit=None, profit_target=600, min_profit=200,
                    fetch_fn=None, universe_cap=None):
    """Собрать head_source_fn — thunk без аргументов, который ГОЛОВА зовёт один раз за сутки.

    Замыкаем параметры охоты: head.plan_day(head_source_fn=build_source_fn(...)) → внутри дня
    ГОЛОВА дёрнет его и получит живой список кандидатов. Сеть тянется ТОЛЬКО в момент вызова thunk
    (лениво), не при сборке — так тесты/сухие сборки не ходят в WB, пока thunk не вызван.
    """
    def _thunk():
        return collect(hunt=hunt, city=city, limit=limit, profit_target=profit_target,
                       min_profit=min_profit, fetch_fn=fetch_fn, universe_cap=universe_cap)
    return _thunk


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="ИСТОЧНИК ГОЛОВЫ — прочесать список охоты WB и показать кандидатов (ЖИВАЯ сеть, 0₽)")
    ap.add_argument("--live", action="store_true",
                    help="реально сходить в WB (иначе только показать список охоты, без сети)")
    ap.add_argument("--city", default=DEFAULT_CITY)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    hunt = load_hunt()
    if not args.live:
        print("📋 СПИСОК ОХОТЫ ГОЛОВЫ (без сети; --live чтобы прочесать WB):")
        for i, it in enumerate(hunt, 1):
            print(f"  {i}. {it.get('query') or ('cat=' + str(it.get('category')))}")
        print(f"\nисточник: {hunt_path() if hunt_path().exists() else 'встроенный дефолт'} "
              f"· пунктов {len(hunt)}")
        sys.exit(0)

    cands = collect(hunt=hunt, city=args.city, limit=args.limit)
    if args.json:
        print(json.dumps({"count": len(cands), "candidates": cands}, ensure_ascii=False, indent=2))
    else:
        print(f"🔎 прочёсано пунктов: {len(hunt)} · кандидатов (дедуп): {len(cands)}")
        for c in cands[:15]:
            ds = c.get("demand_signal") or {}
            print(f"  • {c.get('name')[:52]:<52} спрос[{ds.get('strength')}] "
                  f"₽{c.get('cost')} sku={c.get('sku')}")

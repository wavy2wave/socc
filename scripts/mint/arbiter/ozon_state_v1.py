#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON STATE V1 — персистентная память ОЗОН-МЕНЕДЖЕРА (per-SKU + дневные нормы, атомарно).

Менеджер — НЕ демон: он живёт короткими тиками, между которыми ничего не помнит. Эта память и есть
его непрерывность: какие карточки он ведёт, на каком каждая ЖИЗНЕННОМ этапе (скачана→залита→заполнена→
на витрине), какой у неё индекс/цвет, что он делал в прошлый тик, и — по требованию оператора —
ДНЕВНЫЕ НОРМЫ: кто сколько залил / отгрузил / доставил за день. Тик читает память → решает 1 действие
→ дописывает результат. «Живой 24/7 менеджер» = последовательность ограниченных тиков + этот файл.

Зеркалит ymarket_state_v1 (тот же атомарный паттерн, load/upsert/kpis), меняет ТРИ вещи под Озон:
поля карточки под жизненный цикл §4 плана, цвет индекса вместо content-rating, блок дневных норм.

ЗАКОН (SOCC): stdlib-only, без сети, без денег. Запись АТОМАРНА (tmp + os.replace). Ничего не
выдумываем: None ≠ 0. Пустое остаётся пустым. Истина статуса — из реального READ, не из HTTP-кода.

Путь: MEMORY_WAVE/reports/mint/arbiter/ozon_manager_state.json. env OZON_STATE_PATH перекрывает
(тесты/песочница не пишут в канон).

Схема (schema=ozon.manager.state.v1):
  {
    "schema", "created_at", "updated_at",
    "working_set": [offer_id, ...],           # карточки под наблюдением
    "skus": {
       offer_id: {
         "offer_id", "product_id", "name", "category_id",
         "lifecycle",                          # DOWNLOADED|IMPORTED|FILLED|ON_SHELF (см. LIFECYCLE)
         "need_mapping",                       # нужна привязка категории/атрибутов
         "moderation", "visible", "stock",     # истина витрины (200≠успех — читаем это, не код)
         "errors": [...],                      # errors[] из ответа Ozon (пусто = чисто)
         "price", "price_index",               # цена + цвет индекса (GREEN|YELLOW|RED|None)
         "index_history": [{ts, color}],       # динамика индекса без дублей подряд
         "missing_required_attrs": [...],      # незакрытые обязательные атрибуты категории
         "margin": {...}|null,                 # из ozon_econ.sku_margin
         "last_action": {action, why, ok, ts},
         "published_verified": bool,           # доказан ли реальный ON_SHELF (proof-gate verify)
         "first_seen", "updated_at"
       }
    },
    "daily": { "YYYY-MM-DD": {"uploaded":n,"shipped":n,"delivered":n,"fixed":n} },
    "counters": {ticks, publishes_claimed, publishes_verified, errors_fixed, shipped, delivered}
  }
"""
import os
import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ozon_econ_v1 as econ   # noqa: E402  — цвет индекса + маржа из единого источника констант

# scripts/mint/arbiter -> scripts/mint -> scripts -> SOCC/
REPORTS = HERE.parent.parent.parent / "MEMORY_WAVE/reports/mint/arbiter"
SCHEMA = "ozon.manager.state.v1"

MAX_INDEX_HISTORY = 50   # держим последние N замеров цвета индекса на карточку

# Жизненный цикл карточки (§4 плана): DONE — только ON_SHELF (полностью заполнена И на витрине И stock>0)
LC_DOWNLOADED = "DOWNLOADED"   # СКАЧАНА  — есть исходник WB, уникализирована
LC_IMPORTED = "IMPORTED"       # ЗАЛИТА   — /v3/product/import принят, product_id есть (ещё НЕ готова)
LC_FILLED = "FILLED"           # ПОЛНОСТЬЮ ЗАПОЛНЕНА — все обязательные атрибуты проставлены
LC_ON_SHELF = "ON_SHELF"       # НА ВИТРИНЕ ✅ — модерация OK И visible И stock>0 (единственный DONE)
LIFECYCLE_ORDER = [LC_DOWNLOADED, LC_IMPORTED, LC_FILLED, LC_ON_SHELF]

_NORM_KINDS = ("uploaded", "shipped", "delivered", "fixed")


def state_path():
    """Путь к файлу памяти. env OZON_STATE_PATH перекрывает (песочница/тесты не пишут в канон)."""
    p = os.environ.get("OZON_STATE_PATH")
    return Path(p) if p else (REPORTS / "ozon_manager_state.json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _blank():
    return {
        "schema": SCHEMA,
        "created_at": _now(),
        "updated_at": _now(),
        "working_set": [],
        "skus": {},
        "daily": {},
        "counters": {"ticks": 0, "publishes_claimed": 0, "publishes_verified": 0,
                     "errors_fixed": 0, "shipped": 0, "delivered": 0},
    }


def load():
    """Загрузить память (fail-soft: нет файла/битый JSON/чужая схема → чистый бланк). Всегда валидна."""
    p = state_path()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            base = _blank()
            if isinstance(doc, dict) and isinstance(doc.get("skus"), dict):
                base["skus"] = doc["skus"]   # спасаем что можем, но не доверяем чужой схеме
            return base
        base = _blank()
        base.update({k: doc.get(k, base[k]) for k in base})
        base["skus"] = doc.get("skus") or {}
        base["working_set"] = doc.get("working_set") or []
        base["daily"] = doc.get("daily") or {}
        c = doc.get("counters") or {}
        base["counters"].update({k: c.get(k, base["counters"][k]) for k in base["counters"]})
        base["created_at"] = doc.get("created_at") or base["created_at"]
        return base
    except FileNotFoundError:
        return _blank()
    except Exception:
        return _blank()


def write_atomic(doc):
    """Атомарно записать память: tmp в той же директории + os.replace (не оставляем полу-файл)."""
    doc["updated_at"] = _now()
    doc.setdefault("schema", SCHEMA)
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".ozstate_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)   # атомарная замена: читатель видит либо старое, либо новое целиком
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return p


def upsert_sku(doc, offer_id, **fields):
    """Создать/обновить запись карточки (merge — не затираем то, чего нет в fields).

    index_history/working_set/daily обслуживаются отдельными помощниками. Новая карточка стартует
    в LC_DOWNLOADED. Возвращает саму запись SKU.
    """
    if not offer_id:
        return None
    skus = doc.setdefault("skus", {})
    rec = skus.get(offer_id)
    if rec is None:
        rec = {"offer_id": offer_id, "first_seen": _now(),
               "lifecycle": LC_DOWNLOADED, "index_history": [],
               "errors": [], "missing_required_attrs": [],
               "published_verified": False, "last_action": None}
        skus[offer_id] = rec
    for k, v in fields.items():
        if v is not None:
            rec[k] = v
    rec["updated_at"] = _now()
    return rec


def ensure_working(doc, offer_ids):
    """Добавить offer_id в working_set (кого ведём), без дублей, сохраняя порядок появления."""
    ws = doc.setdefault("working_set", [])
    seen = set(ws)
    for oid in offer_ids:
        if oid and oid not in seen:
            ws.append(oid)
            seen.add(oid)
    return ws


def _push_index(rec, color, ts=None):
    """Добавить замер цвета индекса в историю (без дубля-подряд). Обрезать до MAX. None не пишем."""
    if color is None:
        return
    hist = rec.setdefault("index_history", [])
    if hist and hist[-1].get("color") == color:
        return
    hist.append({"ts": ts or _now(), "color": color})
    if len(hist) > MAX_INDEX_HISTORY:
        del hist[:len(hist) - MAX_INDEX_HISTORY]


def advance_lifecycle(doc, offer_id, stage):
    """Продвинуть карточку по циклу ТОЛЬКО вперёд и только на валидный этап (монотонность).

    Откат назад запрещён (карточка не «раззаливается»). Неизвестный этап игнорируем. Возвращает
    актуальный этап после попытки.
    """
    rec = doc.get("skus", {}).get(offer_id)
    if rec is None or stage not in LIFECYCLE_ORDER:
        return rec.get("lifecycle") if rec else None
    cur = rec.get("lifecycle", LC_DOWNLOADED)
    cur_i = LIFECYCLE_ORDER.index(cur) if cur in LIFECYCLE_ORDER else 0
    new_i = LIFECYCLE_ORDER.index(stage)
    if new_i > cur_i:
        rec["lifecycle"] = stage
        rec["updated_at"] = _now()
    return rec["lifecycle"]


def ingest_shelf_read(doc, shelf_report):
    """Впитать РЕАЛЬНЫЙ READ витрины (product/info/list + info/prices). Истина, а не HTTP-код.

    shelf_report — {'ok':bool,'cards':[{offer_id,product_id,moderation,visible,stock,price,
    price_index,errors,missing_required_attrs}]}. ok=False (dry/нет ключа) → 0 обновлений, ничего
    не выдумываем. Карточка помечается ON_SHELF, только если модерация OK И visible И stock>0.
    Возвращает число обновлённых карточек.
    """
    if not isinstance(shelf_report, dict) or not shelf_report.get("ok"):
        return 0
    cards = shelf_report.get("cards") or []
    n = 0
    for c in cards:
        oid = c.get("offer_id") or c.get("offerId")
        if not oid:
            continue
        color = econ.index_color(c.get("price_index"))
        rec = upsert_sku(doc, oid,
                         product_id=c.get("product_id"),
                         moderation=c.get("moderation"),
                         visible=c.get("visible"),
                         stock=c.get("stock"),
                         price=c.get("price"),
                         price_index=color,
                         errors=c.get("errors") or [],
                         missing_required_attrs=c.get("missing_required_attrs") or [])
        _push_index(rec, color)
        ensure_working(doc, [oid])
        # Витрина: только полное соответствие закону §4 продвигает в ON_SHELF
        mod_ok = str(c.get("moderation") or "").lower() in ("ok", "approved", "processed", "success")
        stock = econ._num(c.get("stock")) or 0.0
        if mod_ok and c.get("visible") and stock > 0 and not (c.get("errors") or []):
            advance_lifecycle(doc, oid, LC_ON_SHELF)
        n += 1
    return n


def set_margin(doc, offer_id, margin):
    """Записать оценку выгоды карточки (из ozon_econ.sku_margin). None-безопасно."""
    if offer_id and offer_id in doc.get("skus", {}):
        doc["skus"][offer_id]["margin"] = margin


def record_action(doc, offer_id, action, why=None, ok=None):
    """Зафиксировать, что менеджер сделал с карточкой в этот тик (непрерывность между тиками)."""
    if offer_id and offer_id in doc.get("skus", {}):
        doc["skus"][offer_id]["last_action"] = {
            "action": action, "why": why, "ok": ok, "ts": _now()}


def mark_published_verified(doc, offer_id, verified=True):
    """Пометить карточку доказанно на витрине (после proof-gate verify независимым READ)."""
    if offer_id and offer_id in doc.get("skus", {}):
        doc["skus"][offer_id]["published_verified"] = bool(verified)
        if verified:
            advance_lifecycle(doc, offer_id, LC_ON_SHELF)
            doc["counters"]["publishes_verified"] = doc["counters"].get("publishes_verified", 0) + 1


def record_norm(doc, kind, by=1, day=None):
    """Дневная норма (требование оператора: кто сколько залил/отгрузил/доставил/починил за день).

    kind ∈ _NORM_KINDS. Пишем в daily[день][kind] и в сквозной counters. Неизвестный вид игнорируем.
    """
    if kind not in _NORM_KINDS:
        return
    d = day or _today()
    daily = doc.setdefault("daily", {})
    row = daily.setdefault(d, {k: 0 for k in _NORM_KINDS})
    row[kind] = row.get(kind, 0) + by
    if kind == "shipped":
        bump(doc, "shipped", by)
    elif kind == "delivered":
        bump(doc, "delivered", by)
    elif kind == "fixed":
        bump(doc, "errors_fixed", by)


def bump(doc, counter, by=1):
    """Инкремент сквозного счётчика (ticks/publishes_claimed/errors_fixed/shipped/delivered/...)."""
    doc.setdefault("counters", {})
    doc["counters"][counter] = doc["counters"].get(counter, 0) + by


def daily_norm(doc, day=None):
    """Норма за день (по умолчанию сегодня) — что менеджер предъявляет: залито/отгружено/доставлено."""
    d = day or _today()
    return dict(doc.get("daily", {}).get(d, {k: 0 for k in _NORM_KINDS}))


def kpis(doc):
    """Свести показатели памяти для лестницы решений (self_status). ЧЕСТНО из памяти, не из фантазии.

    Поля под лестницу Озона: cards_errored (цель 0), need_mapping, tracked, ready_to_publish,
    index_red (красных индексов — прячут из органики), cards_on_shelf (доказанные), avg — н/п.
    """
    skus = doc.get("skus", {})
    errored = [oid for oid, s in skus.items() if s.get("errors")]
    on_shelf = [oid for oid, s in skus.items()
                if s.get("lifecycle") == LC_ON_SHELF and s.get("published_verified")]
    need_mapping = [oid for oid, s in skus.items() if s.get("need_mapping")]
    index_red = [oid for oid, s in skus.items() if s.get("price_index") == econ.INDEX_RED]
    # Готова к выводу на витрину: заполнена, без ошибок, не нужна привязка, ещё не доказана на витрине
    ready = [oid for oid, s in skus.items()
             if s.get("lifecycle") in (LC_FILLED, LC_IMPORTED)
             and not s.get("errors") and not s.get("need_mapping")
             and not s.get("published_verified")]
    return {
        "tracked": len(skus),
        "working_set": len(doc.get("working_set", [])),
        "cards_on_shelf": len(on_shelf),
        "cards_errored": len(errored),           # цель = 0
        "errored_ids": errored,
        "need_mapping": len(need_mapping),
        "ready_to_publish": len(ready),
        "index_red": len(index_red),
        "index_red_ids": index_red,
        "daily_today": daily_norm(doc),
        "counters": dict(doc.get("counters", {})),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="OZON STATE — память менеджера (чтение/KPI/нормы, 0₽)")
    ap.add_argument("--kpi", action="store_true", help="показать KPI из текущей памяти")
    ap.add_argument("--norm", action="store_true", help="показать дневную норму (сегодня)")
    ap.add_argument("--path", action="store_true", help="показать путь файла памяти")
    args = ap.parse_args()
    if args.path:
        print(state_path())
    elif args.norm:
        print(json.dumps(daily_norm(load()), ensure_ascii=False, indent=2))
    else:
        doc = load()
        print(json.dumps(kpis(doc) if args.kpi else doc, ensure_ascii=False, indent=2))

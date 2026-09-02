#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET STATE V1 — персистентная память управляющего Яндекс.Маркетом (per-SKU, атомарно).

Управляющий (ymarket_manager_v1) — НЕ демон: он живёт короткими тиками, между которыми ничего не
помнит. Эта память и есть его непрерывность: что за карточки он ведёт, какой у каждой статус/индекс,
какие рекомендации открыты, что он делал в прошлый тик. Тик читает память → решает 1 действие →
дописывает результат обратно. Так «живой 24/7 управляющий» получается из последовательности
ограниченных тиков + этого файла, а не из вечного процесса.

ЗАКОН (SOCC): stdlib-only, без сети, без денег. Запись АТОМАРНА (tmp + os.replace) — тик не может
оставить полу-записанный JSON, если его прервали. Ничего не выдумываем: поля берём только из того,
что реально дали preflight (dry) и track (реальный READ индекса). Пустое остаётся пустым.

Путь памяти: MEMORY_WAVE/reports/mint/arbiter/ymarket_manager_state.json (канон отчётов ARBITER).
Тесты/песочница перенаправляют через env YM_STATE_PATH — в канон не пишем мусор приёмки.

Схема (schema=ymarket.manager.state.v1):
  {
    "schema", "updated_at", "created_at",
    "working_set": [offerId, ...],          # карточки под наблюдением (кого ведём)
    "skus": {
       offerId: {
         "offerId", "slug", "name", "category_id", "need_mapping",
         "status",                          # последний известный статус карточки (PUBLISHED/...)
         "content_rating", "average_category_rating",
         "index_history": [{ts, rating}],   # динамика индекса (без дублей подряд)
         "open_recommendations": [{type, remainingRatingPoints}],
         "can_not_fill": [type, ...],       # честно: рекомендации, что API не закрыть
         "missing_pictures", "missing_required_params",
         "margin": {...}|null,              # оценка выгоды (из econ.sku_margin)
         "last_action": {action, ts, why},  # что управляющий делал с картой в прошлый раз
         "published_verified": bool,        # доказан ли реальный PUBLISHED (proof-gate)
         "first_seen", "updated_at"
       }
    },
    "counters": {ticks, publishes_claimed, publishes_verified, errors_fixed}
  }
"""
import os
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
# scripts/mint/arbiter -> scripts/mint -> scripts -> SOCC/
REPORTS = HERE.parent.parent.parent / "MEMORY_WAVE/reports/mint/arbiter"
SCHEMA = "ymarket.manager.state.v1"

MAX_INDEX_HISTORY = 50   # храним последние N замеров индекса на карточку (не пухнем бесконечно)


def state_path():
    """Путь к файлу памяти. env YM_STATE_PATH перекрывает (песочница/тесты не пишут в канон)."""
    p = os.environ.get("YM_STATE_PATH")
    return Path(p) if p else (REPORTS / "ymarket_manager_state.json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _blank():
    return {
        "schema": SCHEMA,
        "created_at": _now(),
        "updated_at": _now(),
        "working_set": [],
        "skus": {},
        "counters": {"ticks": 0, "publishes_claimed": 0, "publishes_verified": 0,
                     "errors_fixed": 0},
    }


def load():
    """Загрузить память (fail-soft: нет файла/битый JSON → чистый бланк). Всегда валидная схема."""
    p = state_path()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            # чужой/старый файл — не затираем молча, начинаем чистую память (fail-soft)
            base = _blank()
            if isinstance(doc, dict) and isinstance(doc.get("skus"), dict):
                base["skus"] = doc["skus"]  # спасаем что можем
            return base
        # гарантируем наличие ключей (миграция вперёд-совместимо)
        base = _blank()
        base.update({k: doc.get(k, base[k]) for k in base})
        base["skus"] = doc.get("skus") or {}
        base["working_set"] = doc.get("working_set") or []
        c = doc.get("counters") or {}
        base["counters"].update({k: c.get(k, base["counters"][k]) for k in base["counters"]})
        base["created_at"] = doc.get("created_at") or base["created_at"]
        return base
    except FileNotFoundError:
        return _blank()
    except Exception:
        return _blank()


def write_atomic(doc):
    """Атомарно записать память: tmp в той же директории + os.replace (не оставляем полу-файл).

    Возвращает путь. mkdir родителя idempotent. updated_at освежается на каждой записи.
    """
    doc["updated_at"] = _now()
    doc.setdefault("schema", SCHEMA)
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".ymstate_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)   # атомарная замена (POSIX): читатель видит либо старое, либо новое
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return p


def upsert_sku(doc, offer_id, **fields):
    """Создать/обновить запись карточки. Не затирает поля, которых нет в fields (merge).

    index_history и working_set обслуживаются отдельными помощниками (ingest_track/ensure_working).
    Возвращает саму запись SKU (для дальнейшего чтения вызывающим).
    """
    if not offer_id:
        return None
    skus = doc.setdefault("skus", {})
    rec = skus.get(offer_id)
    if rec is None:
        rec = {"offerId": offer_id, "first_seen": _now(),
               "index_history": [], "open_recommendations": [], "can_not_fill": [],
               "published_verified": False, "last_action": None}
        skus[offer_id] = rec
    for k, v in fields.items():
        if v is not None:
            rec[k] = v
    rec["updated_at"] = _now()
    return rec


def ensure_working(doc, offer_ids):
    """Добавить offerId в working_set (кого ведём), без дублей, сохраняя порядок появления."""
    ws = doc.setdefault("working_set", [])
    seen = set(ws)
    for oid in offer_ids:
        if oid and oid not in seen:
            ws.append(oid)
            seen.add(oid)
    return ws


def _push_index(rec, rating, ts=None):
    """Добавить замер индекса в историю (без дубля-подряд того же значения). Обрезать до MAX."""
    if rating is None:
        return
    hist = rec.setdefault("index_history", [])
    if hist and hist[-1].get("rating") == rating:
        return  # то же значение подряд — не засоряем историю
    hist.append({"ts": ts or _now(), "rating": rating})
    if len(hist) > MAX_INDEX_HISTORY:
        del hist[:len(hist) - MAX_INDEX_HISTORY]


def ingest_preflight(doc, preflight_report):
    """Впитать результат runner.preflight (dry, 0₽): статус готовности каждой карточки в память.

    preflight_report — dict {'rows':[...], 'agg':{...}} из ymarket_runner.preflight. Обновляем
    per-SKU: slug/need_mapping/missing_pictures/n_specs, ставим карточку в working_set. НЕ трогаем
    content_rating (его даёт только реальный track). Возвращает число обработанных строк.
    """
    rows = (preflight_report or {}).get("rows") or []
    n = 0
    for r in rows:
        oid = r.get("sku") or r.get("offerId")
        if not oid:
            continue
        upsert_sku(doc, oid,
                   name=r.get("name"),
                   slug=r.get("slug"),
                   need_mapping=bool(r.get("need_mapping")),
                   missing_pictures=bool(r.get("missing_pictures")),
                   preflight_ok=bool(r.get("ok")),
                   preflight_errors=r.get("errors") or [],
                   n_specs=r.get("n_specs"))
        ensure_working(doc, [oid])
        n += 1
    return n


def ingest_track(doc, quality_report):
    """Впитать результат write.quality_report / runner.track (реальный READ индекса).

    quality_report — dict {'ok':True,'cards':[{offerId,contentRating,averageContentRating,cardStatus,
    recommendations,can_not_fill}], ...}. Обновляем content_rating + историю + открытые рекомендации
    + статус карточки. Если ok=False (dry/нет ключа) — ничего не выдумываем, просто 0 обновлений.
    Возвращает число обновлённых карточек.
    """
    if not isinstance(quality_report, dict) or not quality_report.get("ok"):
        return 0
    cards = quality_report.get("cards") or []
    n = 0
    for c in cards:
        oid = c.get("offerId")
        if not oid:
            continue
        rating = c.get("contentRating")
        rec = upsert_sku(doc, oid,
                         content_rating=rating,
                         average_category_rating=c.get("averageContentRating"),
                         status=c.get("cardStatus"),
                         open_recommendations=c.get("recommendations") or [],
                         can_not_fill=c.get("can_not_fill") or [])
        _push_index(rec, rating)
        ensure_working(doc, [oid])
        n += 1
    return n


def set_margin(doc, offer_id, margin):
    """Записать оценку выгоды карточки (из econ.sku_margin). None-безопасно."""
    if offer_id and offer_id in doc.get("skus", {}):
        doc["skus"][offer_id]["margin"] = margin


def record_action(doc, offer_id, action, why=None, ok=None):
    """Зафиксировать, что управляющий сделал с карточкой в этот тик (для непрерывности между тиками)."""
    if offer_id and offer_id in doc.get("skus", {}):
        doc["skus"][offer_id]["last_action"] = {
            "action": action, "why": why, "ok": ok, "ts": _now()}


def mark_published_verified(doc, offer_id, verified=True):
    """Пометить карточку как доказанно опубликованную (после proof-gate verify_publish)."""
    if offer_id and offer_id in doc.get("skus", {}):
        doc["skus"][offer_id]["published_verified"] = bool(verified)
        if verified:
            doc["counters"]["publishes_verified"] = doc["counters"].get("publishes_verified", 0) + 1


def bump(doc, counter, by=1):
    """Инкремент счётчика тиков/действий (ticks/publishes_claimed/errors_fixed/...)."""
    doc.setdefault("counters", {})
    doc["counters"][counter] = doc["counters"].get(counter, 0) + by


def kpis(doc):
    """Свести показатели памяти для self_status: живые/ошибочные/индекс/готовые к заливу.

    ЧЕСТНО из того, что в памяти (не из фантазии). cards_errored — цель 0 (закон оператора).
    """
    skus = doc.get("skus", {})
    ratings = [s.get("content_rating") for s in skus.values()
               if isinstance(s.get("content_rating"), (int, float))]
    errored = [oid for oid, s in skus.items()
               if (s.get("preflight_errors")) or (s.get("status") in
                   ("NO_CARD_ERRORS", "HAS_CARD_CAN_UPDATE_ERRORS"))]
    live = [oid for oid, s in skus.items() if s.get("status") == "PUBLISHED"]
    verified_live = [oid for oid, s in skus.items() if s.get("published_verified")]
    need_mapping = [oid for oid, s in skus.items() if s.get("need_mapping")]
    ready = [oid for oid, s in skus.items()
             if s.get("preflight_ok") and not s.get("need_mapping")
             and not s.get("published_verified")]
    return {
        "tracked": len(skus),
        "working_set": len(doc.get("working_set", [])),
        "cards_live": len(live),
        "cards_live_verified": len(verified_live),
        "cards_errored": len(errored),          # цель = 0
        "errored_ids": errored,
        "need_mapping": len(need_mapping),
        "ready_to_publish": len(ready),
        "avg_content_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "counters": dict(doc.get("counters", {})),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="YMARKET STATE — память управляющего (чтение/KPI, 0₽)")
    ap.add_argument("--kpi", action="store_true", help="показать KPI из текущей памяти")
    ap.add_argument("--path", action="store_true", help="показать путь файла памяти")
    args = ap.parse_args()
    if args.path:
        print(state_path())
    else:
        doc = load()
        print(json.dumps(kpis(doc) if args.kpi else doc, ensure_ascii=False, indent=2))

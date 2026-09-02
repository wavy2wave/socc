#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПАСПОРТ ТОРГОВОЙ ТОЧКИ — слой «куда приедет курьер» органа ARBITER.

ЗАЧЕМ. Канон реестра (ymarket_registry_v1) хранит offerId ↔ marketSku/shopSku/donor_pid/donor_url —
связь «наша карточка ↔ товар донора». НЕ хватает ТОЧКИ: адрес, телефон, инструкция курьеру,
warehouse_id, город, статус. Без неё Экспресс не исполнить: курьер должен приехать куда надо и
НЕ задать вопросов (директива оператора №7). Этот модуль — паспорт точки + привязка
«артикул ↔ магазин-донор ↔ точка». Аддитивный: НИЧЕГО существующее не трогает, только пишет свой
стор в MEMORY_WAVE/reports/mint/arbiter. 0₽, READ + локальная атомарная запись. RUBICON цел.

ЧТО ХРАНИМ (и чего НЕ храним).
  Точка (point_id): shop (магазин-донор, напр. 'cargo-avto'), warehouse_id, city, phone,
  courier_instruction, contact, hours, status, note. Привязки: offerId → point_id (идемпотентно).
  НЕ храним ЖИВОЙ адрес — канон адреса = чтение кабинета (express_loop.resolve_pickup),
  паспорт хранит ЯКОРЬ (warehouse_id + город), поле address_note только как человеческая подсказка.
  Пакет курьера (МАГАЗИН→АДРЕС→ТОВАР) собирает express_loop.build_packet; здесь — данные паспорта.

ЗАКОНЫ (механические, покрыты сухой приёмкой в __main__):
  P1 не выдумываем: upsert_point без point_id или shop → отказ (ValueError).
  P2 None-safe merge: непустое поле не затирается None (частичный апдейт не стирает known-факты).
  P3 адрес не хардкодим: канон адреса точки = живое чтение кабинета; здесь только якорь
     warehouse_id/city + address_note-подсказка (никогда не «точный адрес»).
  P4 привязка идемпотентна: bind(offer_id, point_id) повторно безопасен; unbind ставит None,
     точку не удаляет.
  P5 fail-soft: битый/чужой файл → чистый бланк (не роняем и не затираем молча спасаемое).
  P6 телефон + инструкция курьеру хранятся ОДИН раз на точку (единый источник, не в каждой карточке).
"""
from __future__ import annotations

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
# scripts/mint/arbiter -> scripts/mint -> scripts -> SOCC/
REPORTS = HERE.parent.parent.parent / "MEMORY_WAVE/reports/mint/arbiter"
SCHEMA = "ymarket.trade.points.v1"

# Поля паспорта точки, которые сливаются None-safe при upsert (P2).
_POINT_FIELDS = ("shop", "warehouse_id", "city", "phone", "courier_instruction",
                 "contact", "hours", "status", "address_note", "note")

# Дефолт-инструкция курьеру (P6: один раз на точку; оператор может перекрыть в паспорте).
_DEFAULT_COURIER_INSTRUCTION = (
    "Курьер звонит по телефону склада, ЖДЁТ № внутреннего заказа из магазина, "
    "входит как клиент, забирает заказ, доставляет как Яндекс Маркет."
)


def points_path():
    """Путь к стору. env YM_POINTS_PATH перекрывает (песочница/тесты не пишут в канон)."""
    p = os.environ.get("YM_POINTS_PATH")
    return Path(p) if p else (REPORTS / "ymarket_trade_points.json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _blank():
    return {"schema": SCHEMA, "created_at": _now(), "updated_at": _now(),
            "points": {}, "bindings": {}}


# ── стор (fail-soft, атомарно) ────────────────────────────────────────────────

def load():
    """Загрузить стор точек (fail-soft: нет файла/битый/чужой JSON → чистый бланк, P5)."""
    p = points_path()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            base = _blank()
            if isinstance(doc, dict):
                if isinstance(doc.get("points"), dict):
                    base["points"] = doc["points"]
                if isinstance(doc.get("bindings"), dict):
                    base["bindings"] = doc["bindings"]
            return base
        base = _blank()
        base["created_at"] = doc.get("created_at") or base["created_at"]
        base["points"] = doc.get("points") if isinstance(doc.get("points"), dict) else {}
        base["bindings"] = doc.get("bindings") if isinstance(doc.get("bindings"), dict) else {}
        return base
    except FileNotFoundError:
        return _blank()
    except Exception:
        return _blank()


def write_atomic(doc):
    """Атомарно записать стор: tmp в той же папке + os.replace (без полу-файла). Возвращает путь."""
    doc["updated_at"] = _now()
    doc.setdefault("schema", SCHEMA)
    p = points_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".ympts_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return p


# ── операции над doc (чистые: не читают/не пишут файл) ─────────────────────────

def upsert_point(doc, point_id, shop=None, warehouse_id=None, city=None, phone=None,
                 courier_instruction=None, contact=None, hours=None, status=None,
                 address_note=None, note=None):
    """Создать/обновить паспорт точки. point_id и shop обязательны (P1) — иначе отказ.

    courier_instruction пуст/None → ставится дефолт (P6). None-safe merge (P2).
    Возвращает сам паспорт точки (для чтения вызывающим).
    """
    if not point_id:
        raise ValueError("паспорт: нет point_id — не к чему привязать точку (P1)")
    if not shop:
        raise ValueError("паспорт: нет shop — не знаем, магазин какого донора это точка (P1)")
    point_id = str(point_id)

    incoming = {"shop": shop, "warehouse_id": warehouse_id, "city": city, "phone": phone,
                "courier_instruction": courier_instruction, "contact": contact, "hours": hours,
                "status": status, "address_note": address_note, "note": note}
    if not incoming["courier_instruction"]:
        incoming["courier_instruction"] = _DEFAULT_COURIER_INSTRUCTION

    pts = doc.setdefault("points", {})
    rec = pts.get(point_id)
    if rec is None:
        rec = {"point_id": point_id, "first_seen": _now()}
        for f in _POINT_FIELDS:
            rec[f] = None
        pts[point_id] = rec

    for f in _POINT_FIELDS:
        val = incoming.get(f)
        if val is not None and str(val) != "":       # P2: пустое/None не затирает известный факт
            rec[f] = val
    rec["updated_at"] = _now()
    return rec


def get_point(doc, point_id):
    """Паспорт точки по point_id или None. Пустой стор → None (P1, без падения)."""
    if not point_id:
        return None
    return (doc.get("points") or {}).get(str(point_id))


def all_points(doc):
    """Весь стор точек (dict point_id→rec). Пустой стор → {}."""
    return dict(doc.get("points") or {})


def bind(doc, offer_id, point_id):
    """Привязать наш offerId к точке (артикул ↔ магазин ↔ точка). Идемпотентно (P4).

    Точка должна существовать — иначе ValueError (не выдумываем привязку к пустоте).
    offerId обязателен (P1). Возвращает сам паспорт точки.
    """
    if not offer_id:
        raise ValueError("паспорт: нет offerId — к чему привязка? (P1)")
    if not point_id:
        raise ValueError("паспорт: нет point_id — привязка к пустоте (P1)")
    point_id = str(point_id)
    if point_id not in (doc.get("points") or {}):
        raise ValueError(f"паспорт: точки '{point_id}' нет в сторе — создайте её upsert_point (P4)")
    (doc.setdefault("bindings", {}))[str(offer_id)] = point_id
    return get_point(doc, point_id)


def unbind(doc, offer_id):
    """Отвязать offerId от точки (P4): привязка → None, сама точка НЕ удаляется."""
    if not offer_id:
        return
    b = doc.setdefault("bindings", {})
    b.pop(str(offer_id), None)


def point_for_offer(doc, offer_id):
    """Паспорт точки для offerId или None. Нет привязки/пустой стор → None (не выдумываем)."""
    if not offer_id:
        return None
    pid = (doc.get("bindings") or {}).get(str(offer_id))
    return get_point(doc, pid) if pid else None


def offer_ids_at_point(doc, point_id):
    """Обратная привязка (P4): все offerId, привязанные к точке. Сортированный список."""
    if not point_id:
        return []
    point_id = str(point_id)
    return sorted(oid for oid, pid in (doc.get("bindings") or {}).items()
                  if str(pid or "") == point_id)


# ── one-shot удобства (load → mutate → write / load → read) ────────────────────

def save_point(point_id, **fields):
    """Один выстрел записи паспорта: load → upsert → write_atomic. Возвращает записанный паспорт."""
    doc = load()
    rec = upsert_point(doc, point_id, **fields)
    write_atomic(doc)
    return rec


def save_bind(offer_id, point_id):
    """Один выстрел привязки: load → bind → write_atomic. Возвращает паспорт точки."""
    doc = load()
    rec = bind(doc, offer_id, point_id)
    write_atomic(doc)
    return rec


def lookup_point(point_id):
    """Один выстрел чтения паспорта: load → get_point. None-safe."""
    return get_point(load(), point_id)


def lookup_for_offer(offer_id):
    """Один выстрел чтения: offerId → паспорт его точки. Для экспресс-резолва. None-safe."""
    return point_for_offer(load(), offer_id)


if __name__ == "__main__":
    # Сухая приёмка (0₽, пишет только если задан YM_POINTS_PATH — иначе в канон отчётов).
    doc = _blank()
    upsert_point(doc, "cargo-msk-express", shop="cargo-avto", warehouse_id=1803385,
                 city="Москва", phone="8 977 962 91 25", status="active",
                 address_note="точка на складе донора cargo-avto (Москва); канон адреса — кабинет")
    upsert_point(doc, "cargo-msk-test", shop="cargo-avto", warehouse_id=2390811,
                 city="Москва", phone="8 977 962 91 25", status="test")
    bind(doc, "9602037-1", "cargo-msk-express")
    bind(doc, "9603273-1", "cargo-msk-express")

    print("ПАСПОРТ ТОРГОВОЙ ТОЧКИ — сухая приёмка\n")
    print("P1 без point_id →", end=" ")
    try:
        upsert_point(doc, "", shop="cargo-avto")
        print("ОШИБКА (должен был отказать)")
    except ValueError:
        print("отказ ✓")
    print("P1 без shop →", end=" ")
    try:
        upsert_point(doc, "x", shop="")
        print("ОШИБКА (должен был отказать)")
    except ValueError:
        print("отказ ✓")
    print("P2 None-safe merge: address_note не затрёт phone →",
          upsert_point(doc, "cargo-msk-express", shop="cargo-avto", note="мерж")["phone"])
    print("P3 адрес: паспорт хранит якорь, не хардкод → address_note =",
          get_point(doc, "cargo-msk-express")["address_note"])
    print("P4 привязка идемпотентна →",
          bind(doc, "9602037-1", "cargo-msk-express")["point_id"])
    print("P4 обратная привязка offer_ids_at_point →",
          offer_ids_at_point(doc, "cargo-msk-express"))
    print("P4 unbind не удаляет точку →", end=" ")
    unbind(doc, "9603273-1")
    print("точка жива =", get_point(doc, "cargo-msk-express")["point_id"],
          "| привязка стала None =", point_for_offer(doc, "9603273-1"))
    print("P4 bind к несуществующей точке →", end=" ")
    try:
        bind(doc, "1-1", "nope")
        print("ОШИБКА (должен был отказать)")
    except ValueError:
        print("отказ ✓")
    print("P6 дефолт-инструкция курьеру вшита →",
          get_point(doc, "cargo-msk-express")["courier_instruction"])
    print("\njson:", json.dumps({"cargo-msk-express": get_point(doc, "cargo-msk-express"),
                                 "point_for_offer(9602037-1)": point_for_offer(doc, "9602037-1")},
                                ensure_ascii=False, indent=2))

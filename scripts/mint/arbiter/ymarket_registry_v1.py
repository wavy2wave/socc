#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РЕЕСТР АРТИКУЛОВ — канонический мост идентификаторов органа ARBITER.

ЗАЧЕМ. По оплаченному заказу оператор должен за СЕКУНДЫ увидеть: МАГАЗИН-донор (адрес/url) ↔
НАШ артикул (offerId) ↔ артикул магазина (marketSku/shopSku) ↔ товар. До сих пор этой тройки
не хранил НИКТО: marketSku читался транзитно в card_quality и терялся каждый тик, а адрес донора
пересчитывался split('-') в трёх местах (express_loop, donor_stock, from_xlsx) — источник дрейфа.
Этот модуль — единственное ХРАНИЛИЩЕ связи. Не память статусов (это ymarket_state_v1), не отбор
(portfolio_v1), не порождение (from_xlsx) — только КАНОН идентификаторов + происхождение.

ЧТО ХРАНИМ (и чего НЕ храним).
  Храним по ключу offerId: marketSku, shopSku, donor_pid, donor_url, source_url, supplier + время.
  НЕ храним статус/рейтинг/рекомендации карточки — это забота ymarket_state_v1 (без дубля памяти).

КАНОН offerId. Живые залитые плёнки используют схему '{pid}-1' (9603273-1, 9602037-1, ...): база
= числовой pid донора cargo-avto. Это ЕДИНСТВЕННЫЙ канон реестра (Ozon-путь 'ARB-{ean}' сюда не
кладём — у него нет donor_pid). donor_pid выводится из offerId той же конвенцией split('-')[0]+isdigit,
что и во всём органе; donor_url собирается ТОЛЬКО через donor_stock_v1.BASE (адрес не хардкодим).

ЗАКОНЫ (механические, покрыты приёмкой):
  R1 не выдумываем: upsert без offerId → отказ (ValueError). Пустой стор → пустой ответ, не падение.
  R2 None-safe merge: непустое поле НЕ затирается None (частичный upsert не стирает known-факты).
  R3 адрес донора не хардкодим: donor_url берётся из donor_stock_v1.BASE (единый источник URL).
  R4 обратный индекс: by_pid(pid) честно возвращает ВСЕ наши offerId по одному pid донора.
  R5 fail-soft: битый/чужой файл → чистый бланк (не роняем и не затираем молча спасаемое).
  R6 канон offerId: donor_pid выводится из offerId той же split-конвенцией, что offer_to_cargo.

0₽, наружу ничего — READ + локальная атомарная запись. RUBICON цел по построению.
"""
from __future__ import annotations

import os
import re
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
# scripts/mint/arbiter -> scripts/mint -> scripts -> SOCC/
REPORTS = HERE.parent.parent.parent / "MEMORY_WAVE/reports/mint/arbiter"
SCHEMA = "ymarket.article.registry.v1"

# Поля-идентификаторы, которые реестр хранит (и только их сливает None-safe при upsert).
_FIELDS = ("marketSku", "shopSku", "donor_pid", "donor_url", "source_url", "supplier")

# Адрес донора — из живого читателя наличия (единый источник, R3). Импорт мягкий: реестр обязан
# работать даже без donor_stock (тогда donor_url не достраивается сам, но переданный — сохранится).
try:
    import donor_stock_v1 as _donor            # noqa: F401
    _DONOR_BASE = getattr(_donor, "BASE", None)
except Exception:                              # pragma: no cover — модуль всегда рядом, но не роняемся
    _DONOR_BASE = None


def registry_path():
    """Путь к стору. env YM_REGISTRY_PATH перекрывает (песочница/тесты не пишут в канон)."""
    p = os.environ.get("YM_REGISTRY_PATH")
    return Path(p) if p else (REPORTS / "ymarket_article_registry.json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _blank():
    return {"schema": SCHEMA, "created_at": _now(), "updated_at": _now(), "articles": {}}


# ── канон идентификаторов (R6/R3) ─────────────────────────────────────────────

def donor_pid_from_offer(offer_id):
    """offerId → числовой pid донора или None. Та же конвенция split('-')[0]+isdigit, что во всём органе.

    '9603273-1' → '9603273'; 'cargoavto-9603273' → None (база не число); 'ARB-...' → None (Ozon-путь)."""
    base = str(offer_id or "").split("-")[0].strip()
    return base if base and base.isdigit() else None


def _donor_url_pid_re():
    """Регэксп «pid из ссылки донора», выведенный ИЗ той же BASE (R3, не хардкодим второй адрес).

    BASE='https://sp.cargo-avto.ru/catalog/{pid}/' → ^...catalog/(\\d+)/?$. Нет BASE → None (не гадаем)."""
    if not _DONOR_BASE:
        return None
    try:
        pat = re.escape(_DONOR_BASE).replace(re.escape("{pid}"), r"(\d+)")
        return re.compile(pat.rstrip("/") + r"/?$")
    except Exception:
        return None


def donor_pid_from_url(url):
    """Ссылка на карточку донора → числовой pid или None. Матчит ТОЛЬКО адрес формата donor BASE.

    Это НЕ выдумывание: pid читается из ссылки-провенанса (source_url), которую дал сам оператор/выгрузка,
    по единому формату донора. Чужой/битый url → None (не подставляем)."""
    rx = _donor_url_pid_re()
    if not rx or not url:
        return None
    m = rx.search(str(url).strip())
    return m.group(1) if m else None


def donor_url_for(pid):
    """pid → url карточки донора через donor_stock_v1.BASE (адрес не хардкодим, R3). Нет pid/BASE → None."""
    if not pid or not _DONOR_BASE:
        return None
    try:
        return _DONOR_BASE.format(pid=pid)
    except Exception:
        return None


# ── стор (fail-soft, атомарно) ────────────────────────────────────────────────

def load():
    """Загрузить реестр (fail-soft: нет файла/битый/чужой JSON → чистый бланк, R5). Всегда валидная схема."""
    p = registry_path()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            base = _blank()
            if isinstance(doc, dict) and isinstance(doc.get("articles"), dict):
                base["articles"] = doc["articles"]        # спасаем что можем, не затираем молча
            return base
        base = _blank()
        base["created_at"] = doc.get("created_at") or base["created_at"]
        base["articles"] = doc.get("articles") if isinstance(doc.get("articles"), dict) else {}
        return base
    except FileNotFoundError:
        return _blank()
    except Exception:
        return _blank()


def write_atomic(doc):
    """Атомарно записать реестр: tmp в той же папке + os.replace (без полу-файла). Возвращает путь."""
    doc["updated_at"] = _now()
    doc.setdefault("schema", SCHEMA)
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".ymreg_", suffix=".tmp")
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

def upsert(doc, offer_id, marketSku=None, shopSku=None, donor_pid=None,
           donor_url=None, source_url=None, supplier=None):
    """Создать/обновить запись артикула. None-safe merge (R2): непустое поле не затирается None.

    Автодостройка (R6/R3): donor_pid выводится из offerId, если не задан; donor_url — из pid через
    donor.BASE, если не задан. offerId обязателен (R1) — иначе ValueError (не выдумываем ключ).
    Возвращает саму запись (для чтения вызывающим).
    """
    if not offer_id:
        raise ValueError("реестр: нет offerId — не к чему привязать связь (R1, не выдумываем)")
    offer_id = str(offer_id)

    incoming = {"marketSku": marketSku, "shopSku": shopSku, "donor_pid": donor_pid,
                "donor_url": donor_url, "source_url": source_url, "supplier": supplier}
    # автодостройка канона до слияния (переданное всегда в приоритете над выводом).
    # Порядок вывода donor_pid: явный > из offerId (split-конвенция) > из ссылки-провенанса source_url.
    # Третий ярус спасает host-префиксные offerId ('cargoavto-9603273'), где база не число, но pid
    # честно лежит в донор-ссылке того же формата BASE (не выдумывание — чтение данного оператором).
    if not incoming["donor_pid"]:
        incoming["donor_pid"] = donor_pid_from_offer(offer_id)
    if not incoming["donor_pid"]:
        incoming["donor_pid"] = donor_pid_from_url(incoming["source_url"])
    if not incoming["donor_url"]:
        incoming["donor_url"] = donor_url_for(incoming["donor_pid"])

    arts = doc.setdefault("articles", {})
    rec = arts.get(offer_id)
    if rec is None:
        rec = {"offerId": offer_id, "first_seen": _now()}
        for f in _FIELDS:
            rec[f] = None
        arts[offer_id] = rec

    for f in _FIELDS:
        val = incoming.get(f)
        if val is not None and str(val) != "":       # R2: пустое/None не затирает известный факт
            rec[f] = val
    rec["updated_at"] = _now()
    return rec


def get(doc, offer_id):
    """Запись по offerId или None. Пустой стор → None (R1, без падения)."""
    if not offer_id:
        return None
    return (doc.get("articles") or {}).get(str(offer_id))


def by_pid(doc, pid):
    """Обратный индекс (R4): pid донора → отсортированный список НАШИХ offerId с этим pid."""
    if not pid:
        return []
    pid = str(pid)
    out = [oid for oid, rec in (doc.get("articles") or {}).items()
           if str((rec or {}).get("donor_pid") or "") == pid]
    return sorted(out)


def all_articles(doc):
    """Весь стор идентификаторов (dict offerId→rec). Пустой стор → {}."""
    return dict(doc.get("articles") or {})


# ── one-shot удобства (load → mutate → write / load → read) ────────────────────

def record(offer_id, **fields):
    """Один выстрел записи: load → upsert → write_atomic. Возвращает записанную запись."""
    doc = load()
    rec = upsert(doc, offer_id, **fields)
    write_atomic(doc)
    return rec


def lookup(offer_id):
    """Один выстрел чтения: load → get. Для быстрого резолва по заказу (express_loop). None-safe."""
    return get(load(), offer_id)


def lookup_by_pid(pid):
    """Один выстрел обратного чтения: load → by_pid. Для массовой сверки донора против каталога."""
    return by_pid(load(), pid)


def resolve_cargo(offer_id):
    """offerId → {pid, url} из РЕЕСТРА (если есть donor_pid), иначе из канон-конвенции. None если нет pid.

    Это точка, которую express_loop.offer_to_cargo зовёт ПЕРВОЙ: реестр перекрывает split-fallback,
    поэтому host-префиксный offerId ('cargoavto-9603273') резолвится через сохранённый donor_pid,
    а не даёт ложный None. Голый '9603273-1' работает и без стора (канон-конвенция — дно).
    """
    rec = lookup(offer_id)
    pid = (rec or {}).get("donor_pid") or donor_pid_from_offer(offer_id)
    if not pid:
        return None
    url = (rec or {}).get("donor_url") or donor_url_for(pid)
    return {"pid": str(pid), "url": url}


if __name__ == "__main__":
    # Сухая демонстрация (0₽, пишет только если задан YM_REGISTRY_PATH — иначе в канон отчётов).
    doc = _blank()
    upsert(doc, "9603273-1", marketSku="101812345678", supplier="cargo-avto",
           source_url="https://sp.cargo-avto.ru/catalog/9603273/")
    upsert(doc, "9602037-1")                         # donor_pid/url достроятся сами из offerId
    print("РЕЕСТР АРТИКУЛОВ — сухая демонстрация\n")
    print(json.dumps({
        "9603273-1": get(doc, "9603273-1"),
        "by_pid(9602037)": by_pid(doc, "9602037"),
        "resolve(cargoavto-9603273 без стора)": donor_pid_from_offer("cargoavto-9603273"),
    }, ensure_ascii=False, indent=2))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""БИБЛИОТЕКА ТОВАРОВ И КАТЕГОРИЙ (ymarket_library_v1) — общая память ЦИКЛ-ЯМ.

ЗАЧЕМ. Оператор: «БИБЛИОТЕКА товаров и категорий (АГИ-живая) — каждый добавленный артикул и
обновлённые остатки пишутся в общую библиотеку». Реестр (ymarket_registry_v1) хранит ТОЛЬКО мост
идентификаторов pid↔offerId↔url — связь, но не жизнь карточки. Библиотека — это ЖИВОЙ СЛЕД каждого
артефакта, что бы ни делали параллельные ЦИКЛЫ-1: что собрано (карточка), что выставлено (остатки),
как проверено (СВЕРКА), под каким циклом-хешем. Агрегация по категориям/магазинам/циклам отвечает
«что организм уже поставил на витрину» — пульс для ЦЕНОВИКА и СТРАТЕГА.

ЧТО ХРАНИМ (по offerId-артикулу, НЕ по marketSku — marketSku живёт в реестре):
  карточка: name, vendor, barcode, cost, price, markup, article, dims (ОВХ), n_photos,
            description_len, spec_n, категория (slug + market_category_id), store_slug,
            cycle_hash (кто произвёл), builder + событие 'card' в events.
  остатки:  событие 'stock' {warehouse_id, count} в events — история, а не снимок.
  СВЕРКА:   последний вердикт прочтения живого состояния (last_verified).
  Агрегаты: stats() по категориям/магазинам/циклам — «сколько циклов работает, что поставили».

ЗАКОНЫ (механические, покрыты приёмкой run_library):
  LB1 сухой прогон пишет НИЧЕГО: все one-shot-писатели требуют live=True; live=False → None (no-op).
      (Зеркало RG12: «dry-отчёт → ничего» — библиотека растёт ТОЛЬКО из реальных событий.)
  LB2 не выдумываем: offerId обязателен; известные поля только; None/пустое не затирает факты (merge).
  LB3 identity не дублируем: donor_pid из offerId — через реестр (donor_pid_from_offer), свой split НЕ пишем.
  LB4 dims честно: dict или отсутствует; не сочиняем габариты.
  LB5 fail-soft: битый/чужой файл → чистый бланк, спасаем goods из чужой схемы.
  LB6 атомарная запись (tmp + os.replace) — без полу-файла.
  LB7 история событий не затирается: stock-события копятся, карточка-обновление меняет поля, не стирая events.
  LB8 категория/цикл/магазин — индексируемые срезы (by_category/by_cycle/by_store), все срезы пустые на пустом сторе.

0₽, наружу ничего — READ + локальная атомарная запись ТОЛЬКО по live-событию. RUBICON цел по построению.
"""
from __future__ import annotations

import os
import json
import tempfile
import contextlib
from pathlib import Path
from datetime import datetime, timezone

try:                                # эксклюзивная блокировка живых писателей (LB6+); нет fcntl → без блокировки
    import fcntl
except Exception:                    # pragma: no cover — не платформа, где библиотека живёт
    fcntl = None

HERE = Path(__file__).resolve().parent


def _reports_root():
    """ЯКОРЬ канона — корень SOCC по маркеру MEMORY_WAVE, а не по цепочке parent.
    Если модуль скопируют/рело-аут (тестовая копия, новая папка), цепочка parent
    молча «переехала» бы на новый ПУСТОЙ путь и живой record_* писал бы в пустоту,
    теряя историю (LB6-безопасность пути). Идём вверх от HERE к каталогу с MEMORY_WAVE."""
    here = HERE
    for anc in (here, *here.parents):           # репо-корень (.git) с MEMORY_WAVE — канон:
        if (anc / ".git").is_dir() and (anc / "MEMORY_WAVE").is_dir():  # сирота не затеняет канон
            return anc
    for anc in (here, *here.parents):
        if (anc / "MEMORY_WAVE").is_dir():
            return anc
    return here.parent.parent.parent            # фолбэк: старая цепочка arbiter -> mint -> scripts -> SOCC


REPORTS = _reports_root() / "MEMORY_WAVE/reports/mint/arbiter"
SCHEMA = "ymarket.goods.library.v1"

# Поля карточки, которые библиотека хранит (и только их None-safe сливает при обновлении).
_CARD_FIELDS = (
    "donor_pid", "donor_url", "store_slug", "cycle_hash", "builder",
    "category_slug", "category_market_id", "vendor", "barcode",
    "name", "article", "cost", "price", "markup", "n_photos",
    "dims", "description_len", "spec_n", "stock_count",
)

# identity-мост — из реестра, а НЕ свой split (LB3: один канон на весь орган). Мягкий импорт:
# библиотека работает и без реестра (тогда donor_pid берётся только явно переданным).
try:
    import ymarket_registry_v1 as _reg          # noqa: F401
    _donor_pid_from_offer = _reg.donor_pid_from_offer
except Exception:                                # pragma: no cover — модуль всегда рядом, но не роняемся
    def _donor_pid_from_offer(_offer_id):
        return None


def library_path():
    """Путь к стору. env YM_LIBRARY_PATH перекрывает (песочница/тесты не пишут в канон)."""
    p = os.environ.get("YM_LIBRARY_PATH")
    return Path(p) if p else (REPORTS / "ymarket_goods_library.json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _blank():
    return {"schema": SCHEMA, "created_at": _now(), "updated_at": _now(), "goods": {}}


# ── стор (fail-soft LB5, атомарно LB6) ─────────────────────────────────────────

def _coerce_goods(goods):
    """Санитизация сторовых записей (LB5 fail-soft): оставляем ТОЛЬКО dict-записи с
    dict-событиями. Чужая/битая схема не должна ронять read-органы (by_category/…/stats
    ходят по rec.get/ev.get — мусор-запись без dict-формы кидал бы AttributeError)."""
    out = {}
    for oid, rec in (goods or {}).items():
        if not isinstance(rec, dict):
            continue
        rec = dict(rec)
        if not isinstance(rec.get("events"), list):
            rec["events"] = []
        else:
            rec["events"] = [e for e in rec["events"] if isinstance(e, dict)]
        if not rec.get("offerId"):
            rec["offerId"] = str(oid)
        out[str(oid)] = rec
    return out


def load():
    """Загрузить библиотеку (fail-soft: нет файла/битый/чужой JSON → чистый бланк). Всегда валидна схема."""
    p = library_path()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            base = _blank()
            if isinstance(doc, dict) and isinstance(doc.get("goods"), dict):
                base["goods"] = _coerce_goods(doc["goods"])   # спасаем что можем, не затираем молча
            return base
        base = _blank()
        base["created_at"] = doc.get("created_at") or base["created_at"]
        base["goods"] = _coerce_goods(doc.get("goods"))
        return base
    except FileNotFoundError:
        return _blank()
    except Exception:
        return _blank()


def write_atomic(doc):
    """Атомарно записать библиотеку: tmp в той же папке + os.replace (без полу-файла). Возвращает путь."""
    doc["updated_at"] = _now()
    doc.setdefault("schema", SCHEMA)
    p = library_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".ymlib_", suffix=".tmp")
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

def _event(ts, kind, **fields):
    ev = {"ts": ts, "kind": kind}
    ev.update({k: v for k, v in fields.items() if v is not None})
    return ev


def _markup_derive(markup, cost, price):
    """markup не дан, но цена и закупка известны → markup=price/cost (LB2: считаем из данного)."""
    if markup is not None:
        return markup
    try:
        c, p = float(cost), float(price)
        return round(p / c, 3) if c > 0 and p > 0 else None
    except (TypeError, ValueError):
        return None


def upsert_card(doc, offer_id, **fields):
    """Создать/обновить запись карточки. None-safe merge (LB2). Возвращает запись (для чтения)."""
    if not offer_id:
        raise ValueError("библиотека: нет offerId — не к чему привязать (LB1/LB2, не выдумываем)")
    offer_id = str(offer_id)

    goods = doc.setdefault("goods", {})
    rec = goods.get(offer_id)
    if rec is None:
        rec = {"offerId": offer_id, "first_seen": _now(), "events": []}
        goods[offer_id] = rec

    # donor_pid авто-мостится через реестр ТОЛЬКО если не передан явно (LB3).
    if fields.get("donor_pid") is None:
        fields["donor_pid"] = _donor_pid_from_offer(offer_id)

    markup = fields.get("markup")
    if markup is None:
        markup = _markup_derive(None, fields.get("cost"), fields.get("price"))
    fields["markup"] = markup

    changed = []
    for f in _CARD_FIELDS:
        val = fields.get(f)
        if val is not None and str(val) != "":
            if rec.get(f) != val:
                rec[f] = val
                changed.append(f)
    # dims = None НЕ стирает сохранённые габариты: как и любое другое поле, None значит
    # «не знаем — не трогаем факт» (LB2). Живой цикл без ОВХ у донора не уничтожает то,
    # что честно записал прошлый цикл. Удалять габариты — только явным delete, которого нет.
    # Если цена/закупка менялись без markup — пересчитываем markup из СОХРАНЁННЫХ полей,
    # чтобы не хранить устаревшую наценку (был только один из cost/price при обновлении).
    if "markup" not in changed and rec.get("cost") is not None and rec.get("price") is not None:
        derived = _markup_derive(None, rec.get("cost"), rec.get("price"))
        if derived is not None and derived != rec.get("markup"):
            rec["markup"] = derived
            changed.append("markup")
    rec["updated_at"] = _now()
    if changed:
        rec.setdefault("events", []).append(
            _event(_now(), "card", **{k: rec.get(k) for k in changed
                                      if k in ("name", "price", "cost", "markup", "stock_count",
                                               "vendor", "barcode", "category_slug")}))
    return rec


def upsert_stock(doc, offer_id, *, count, warehouse_id, store_slug=None, cycle_hash=None, note=None):
    """Добавить событие 'stock' к записи. Создаёт запись, если карточки ещё не было (LB7: не затирает)."""
    if not offer_id:
        raise ValueError("библиотека: нет offerId — не к чему привязать остаток (LB2)")
    offer_id = str(offer_id)
    goods = doc.setdefault("goods", {})
    rec = goods.get(offer_id)
    if rec is None:
        rec = {"offerId": offer_id, "first_seen": _now(), "events": []}
        goods[offer_id] = rec
    rec.setdefault("events", []).append(
        _event(_now(), "stock", warehouse_id=warehouse_id, count=count,
               store_slug=store_slug, cycle_hash=cycle_hash, note=note))
    rec["updated_at"] = _now()
    return rec


def mark_verified(doc, offer_id, *, verdict, note=None, store_slug=None, cycle_hash=None):
    """Протокол СВЕРКИ: записать последний вердикт прочтения живого состояния (last_verified)."""
    if not offer_id:
        return None
    offer_id = str(offer_id)
    goods = doc.setdefault("goods", {})
    rec = goods.get(offer_id)
    if rec is None:
        rec = {"offerId": offer_id, "first_seen": _now(), "events": []}
        goods[offer_id] = rec
    rec["last_verified"] = {"verdict": verdict, "ts": _now(),
                            "store_slug": store_slug, "cycle_hash": cycle_hash, "note": note}
    rec["updated_at"] = _now()
    return rec


def get(doc, offer_id):
    """Запись по offerId или None. Пустой стор → None (без падения)."""
    if not offer_id:
        return None
    return (doc.get("goods") or {}).get(str(offer_id))


def all_goods(doc):
    """Весь стор (dict offerId→rec). Пустой стор → {}."""
    return dict(doc.get("goods") or {})


def by_category(doc, category_slug):
    """Срез: все offerId с этой категорией донора (отсортированы). Пусто → []."""
    if not category_slug:
        return []
    slug = str(category_slug)
    return sorted(o for o, rec in (doc.get("goods") or {}).items()
                  if (rec or {}).get("category_slug") == slug)


def by_cycle(doc, cycle_hash):
    """Срез: все offerId, что произвёл этот ЦИКЛ-1 (хеш). Пусто → []."""
    if not cycle_hash:
        return []
    h = str(cycle_hash)
    out = sorted(o for o, rec in (doc.get("goods") or {}).items()
                 if (rec or {}).get("cycle_hash") == h)
    # учёт stock-событий: offerId мог попасть только через остатки (карточка другого цикла)
    for o, rec in (doc.get("goods") or {}).items():
        for ev in (rec or {}).get("events") or []:
            if ev.get("kind") == "stock" and ev.get("cycle_hash") == h and o not in out:
                out.append(o)
    return sorted(set(out))


def by_store(doc, store_slug):
    """Срез: все offerId этого магазина (поле или любое stock-событие магазина). Пусто → []."""
    if not store_slug:
        return []
    s = str(store_slug)
    out = []
    for o, rec in (doc.get("goods") or {}).items():
        if (rec or {}).get("store_slug") == s:
            out.append(o)
            continue
        for ev in (rec or {}).get("events") or []:
            if ev.get("kind") == "stock" and ev.get("store_slug") == s:
                out.append(o)
                break
    return sorted(out)


def categories(doc):
    """Категории → {slug: {articles: N}} по live-карточкам (у кого category_slug задан)."""
    out = {}
    for rec in (doc.get("goods") or {}).values():
        slug = (rec or {}).get("category_slug")
        if slug:
            out.setdefault(slug, 0)
            out[slug] += 1
    return {k: {"articles": v} for k, v in sorted(out.items())}


def stats(doc):
    """Пульс библиотеки: сколько артикулов, по магазинам/категориям/циклам, сколько stock-событий."""
    goods = doc.get("goods") or {}
    stores, cycles, n_stock = {}, {}, 0
    for rec in goods.values():
        rec = rec or {}
        s = rec.get("store_slug")
        if s:
            stores[s] = stores.get(s, 0) + 1
        ch = rec.get("cycle_hash")
        if ch:
            cycles[ch] = cycles.get(ch, 0) + 1
        for ev in rec.get("events") or []:
            if ev.get("kind") == "stock":
                n_stock += 1
    return {
        "articles": len(goods),
        "stock_events": n_stock,
        "stores": {k: {"articles": v} for k, v in sorted(stores.items())},
        "categories": categories(doc),
        "cycles": {k: {"articles": v} for k, v in sorted(cycles.items())},
    }


# ── one-shot удобства (load → mutate → write; ВСЕ требуют live=True — LB1) ─────

def _canon_lock():
    """Эксклюзивная блокировка канона (flock по соседнему .lock). read-modify-write
    не атомарен сам по себе: os.replace атомарен только на запись. Два живых писателя
    (два магазина / параллельная write-линия vs ручной --commit) без блокировки
    затирали бы события друг друга молча и необратимо (LB7)."""
    p = library_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lk = open(str(p) + ".lock", "w")
    fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
    return lk


@contextlib.contextmanager
def _locked():
    if fcntl is None:                                   # pragma: no cover
        yield
        return
    lk = _canon_lock()
    try:
        yield
    finally:
        try:
            fcntl.flock(lk.fileno(), fcntl.LOCK_UN)
        finally:
            lk.close()


def _backup_corrupt():
    """Канон есть, но НЕ парсится (битый JSON, LB5). НЕ пишем поверх молча: спасаем
    файл как .corrupt-<ts>.bak, чтобы живые goods/events были восстановимы человеком.
    Возвращает путь бэкапа или None (файл цел / бэкап не удался)."""
    p = library_path()
    if not p.exists():
        return None
    try:
        json.loads(p.read_text(encoding="utf-8"))
        return None
    except Exception:
        pass
    ts = _now().replace(":", "-").replace("T", "_").split(".")[0]
    bak = p.with_name(p.name + f".corrupt-{ts}.bak")
    try:
        os.replace(p, bak)
        return bak
    except OSError:
        return None


def record_cards(live, entries):
    """Один выстрел на партию карточек (после живого ЗАЛИВА): lock → load → bulk-upsert → write.

    live=False → НИЧЕГО не пишем, возвращаем None (dry-прогоны не растят библиотеку, LB1).
    entries = [ {offer_id, ...карточные поля} ]. Не мутирует caller-словари: копирует.
    Возвращает число записанных или None."""
    if not live:
        return None
    entries = [dict(e) for e in entries if e and e.get("offer_id")]   # копии: e.pop не трогает caller
    if not entries:
        return 0
    with _locked():
        _backup_corrupt()
        doc = load()
        for e in entries:
            oid = e.pop("offer_id")
            upsert_card(doc, oid, **e)
        write_atomic(doc)
    return len(entries)


def record_stock(live, offer_id, *, count, warehouse_id, store_slug=None, cycle_hash=None, note=None):
    """Один выстрел события остатков (после живого ОСТАТКОВ): lock → load → upsert → write.
    live=False → None (LB1)."""
    if not live:
        return None
    with _locked():
        _backup_corrupt()
        doc = load()
        upsert_stock(doc, offer_id, count=count, warehouse_id=warehouse_id,
                     store_slug=store_slug, cycle_hash=cycle_hash, note=note)
        write_atomic(doc)
    return offer_id


def record_verified(live, offer_id, *, verdict, note=None, store_slug=None, cycle_hash=None):
    """Один выстрел протокола СВЕРКИ: lock → load → mark_verified → write. live=False → None (LB1)."""
    if not live:
        return None
    with _locked():
        _backup_corrupt()
        doc = load()
        mark_verified(doc, offer_id, verdict=verdict, note=note,
                      store_slug=store_slug, cycle_hash=cycle_hash)
        write_atomic(doc)
    return offer_id


def lookup(offer_id):
    """Один выстрел чтения: load → get."""
    return get(load(), offer_id)


def stats_now():
    """Один выстрел пульса: load → stats (для ЦЕНОВИКА/СТРАТЕГА/планёрки)."""
    return stats(load())


if __name__ == "__main__":
    # Read-пульс: python3 ymarket_library_v1.py --stats  (0₽, ничего не пишет)
    import argparse
    ap = argparse.ArgumentParser(description="БИБЛИОТЕКА товаров/категорий — пульс (read-only, 0₽)")
    ap.add_argument("--stats", action="store_true", help="сводка библиотеки (канон отчётов)")
    args = ap.parse_args()
    if args.stats:
        print("БИБЛИОТЕКА · пульс\n")
        print(json.dumps(stats_now(), ensure_ascii=False, indent=2))
        raise SystemExit(0)
    # Сухая демонстрация (0₽; в памяти — файл не трогаем).
    doc = _blank()
    upsert_card(doc, "ARB-12345678", donor_pid="1588731", name="Плёнка пузырьковая 100×0,75 м",
                store_slug="atlas-express-film", cycle_hash="abcdef1234", builder="film",
                category_slug="vozdushno-puzyrkovaya-plenka", vendor="Без бренда",
                barcode="4607000000000", cost=87.5, price=700, n_photos=4,
                dims={"length": 30, "width": 25, "height": 25})
    upsert_stock(doc, "ARB-12345678", count=100, warehouse_id=2390811,
                 store_slug="atlas-express-film", cycle_hash="abcdef1234")
    print("БИБЛИОТЕКА — сухая демонстрация\n")
    print(json.dumps({
        "goods": get(doc, "ARB-12345678"),
        "by_category": by_category(doc, "vozdushno-puzyrkovaya-plenka"),
        "stats": stats(doc),
    }, ensure_ascii=False, indent=2))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПОЛНОТА КАРТОЧКИ (ymarket_card_audit_v1) — аудит-орган: честно ли карточка «полная».

ЗАЧЕМ. Оператор: «габариты в карточке ВСЕГДА (не только вес), характеристики ТОЧНО И ВЕРНО,
продающие имена, карточка — полнота характеристик/поиск». Адверсари-ревью движка (2026-09-02)
нашло дыру: СВЕРКА читает живое состояние карточки, но НЕ гейтит габариты — карточка БЕЗ
weightDimensions проходит PASS («полная карточка на витрине»). Этот орган чинит дыру: вердикт
полноты по БЛОКАМ (ИМЯ/ОПИСАНИЕ/ХАРАКТЕРИСТИКИ/ГАБАРИТЫ/ШТРИХКОД/ФОТО/ЦЕНА), где отсутствие
в ЖИВОМ чтении — известный факт (MISSING → INCOMPLETE), а отсутствие в ЗАПИСИ (не собрали
evidence) — незнание (UNKNOWN → UNVERIFIED), НЕ выдуманное «неполная».

ДВА ВХОДА (одна честная модель, два семантических уровня):
  audit_plan(rec)  — ЗАПИСЬ библиотеки/цикла (что ЗАДУМАНО/собрано): поле не дано = UNKNOWN
                     (план не знает, что реально легло на витрину). Совет до залива.
  audit_live(rec)  — ЖИВОЙ срез СВЕРКИ (что РЕАЛЬНО на витрине, чтением): поле прочитано и
                     пусто = MISSING (факт). Это и есть гейт: карточка без габаритов на
                     витрине → INCOMPLETE, СВЕРКА больше не скажет «полная».
  Живой срез СВЕРКИ (node_verify) кладёт content = {vendor, desc_len, n_pics, barcodes,
  wd: bool(weightDimensions)} — audit_live ест ровно этот срез (+опц. name/price/spec_n/raw
  weightDimensions, если СВЕРКА до-читает). 200 OK врёт — полноту судит только ЖИВОЕ чтение.

ПОРОГИ — только ФАКТЫ (не TUNABLE-экономика), поэтому вердикты гейт-годны, не provisional:
  габариты = ВСЕ 4 ОВХ-числа (length/width/height/weight) > 0 — как build_product отдаёт
             weightDimensions ТОЛЬКО полным набором (неполный API отклоняет); частичный = MISSING.
  фото ≥ 1; описание ≠ пусто (ARB: «нет описания» = ошибка карточки, доказано); характеристики
  ≥ 1 (директива); штрихкод непустой EAN (свой штрихкод = рычаг бренда); имя непустое
  НЕ-плейсхолдер (продающее); цена > 0 (иначе не продаём). «Красоту» текста не судим (CC11).

ЗАКОНЫ (механические, покрыты приёмкой run_card_audit):
  CC1 полнота считается БЛОКАМИ; каждый блок даёт OK/MISSING/UNKNOWN.
  CC2 MISSING (знаем: нет) ≠ UNKNOWN (не собрали) — вердикты обязаны их различать (иначе СВЕРКА
      на бедном срезе соврёт «неполная», а на дырявой карточке — «полная»).
  CC3 живой факт главнее плана: audit_live отсутствие в чтении = MISSING; audit_plan — совет.
  CC4 ГАБАРИТЫ жёсткие: на витрине БЕЗ weightDimensions (wd=False) → INCOMPLETE (дыра ревью);
      частичный набор (не все 4 > 0) → MISSING; нет данных → UNKNOWN.
  CC5 ФОТО: живьём n_pics=0 → MISSING; план n_photos=0 → MISSING; не дано → UNKNOWN.
  CC6 ОПИСАНИЕ: пустое (desc_len=0) → MISSING («нет описания»); >0 → OK; не дано → UNKNOWN.
  CC7 ИМЯ: пустое/плейсхолдер/равно offerId → MISSING; продающее → OK; не дано → UNKNOWN.
  CC8 ЦЕНА: ≤0/нет → MISSING (не продаём); >0 → OK; не дано → UNKNOWN.
  CC9 ХАРАКТЕРИСТИКИ: spec_n=0 → MISSING; ≥1 → OK; не дано → UNKNOWN.
  CC10 вердикт: MISSING → INCOMPLETE (ok=False, жёсткий, гейт-годен); нет MISSING, но есть
      UNKNOWN → UNVERIFIED (ok=None, подтвердить нельзя); всё OK → COMPLETE (ok=True).
      INCOMPLETE/UNVERIFIED НЕ обещают индексацию/конверсию — полнота блоков, не деньги.
  CC11 не выдумываем пороги «красоты» (длинны текста/имени-продажности) — судим наличие,
       простые факты, полноту габаритов. Порог описания — только «не пусто» (ошибка карточки),
       не «красиво с 1000 символов».
  CC12 raw weightDimensions (dict всех 4) сильнее bool-флага wd среза: если дан полный объект,
      судим по нему; wd — фолбэк, когда raw не передан.

Чистая математика: ничего не пишет, наружу не ходит, никого не импортирует (0₽, RUBICON цел).
Владелец: СВЕРКА (node_verify) потребляет audit_live как гейт полноты; планёрка/библиотека
читают audit_plan как качество задумки. Проводка в движок — отдельный шаг с регрессией.
"""
from __future__ import annotations

# Блоки полноты карточки (порядок важен для читаемости вердикта).
BLOCKS = ("name", "description", "specs", "dims", "barcode", "photos", "price")
DIMS_KEYS = ("length", "width", "height", "weight")   # ВСЕ четыре, как build_product/API
_PLACEHOLDER_NAMES = {"", "-", "—", "не задано", "без названия", "n/a", "нет"}


# ── состояние блока ─────────────────────────────────────────────────────────────

def _ok(detail):
    return {"state": "OK", "detail": detail}


def _missing(detail):
    return {"state": "MISSING", "detail": detail}


def _unknown(detail):
    return {"state": "UNKNOWN", "detail": detail}


def _dims_full(dims):
    """Честная полнота габаритов: dict со ВСЕМИ 4 ключами, каждый float > 0.
    Возвращает True (полны) / False (известно неполно) / None (нет данных — не судим)."""
    if not isinstance(dims, dict):
        return None
    vals = [dims.get(k) for k in DIMS_KEYS]
    if any(v is None for v in vals):
        return False                       # частичный набор — известен неполным (CC4)
    try:
        return all(float(v) > 0 for v in vals)
    except (TypeError, ValueError):
        return False                       # числа на месте, но не числа/не >0 → неполно


def _take(rec, *keys):
    """Первый НЕ-None из ключей (live/plan алиасы одного поля); нет → None."""
    for k in keys:
        if k in rec and rec[k] is not None:
            return rec[k]
    return None


# ── блоки: каждый = OK / MISSING / UNKNOWN по фактам, без «красоты» (CC11) ─────

def _blk_dims_live(rec):
    """ГАБАРИТЫ живьём: raw weightDimensions (все 4, CC12) → иначе bool-флаг wd среза СВЕРКИ.
    wd=False = на витрине РЕАЛЬНО нет габаритов (прочитано) → MISSING (CC4, дыра ревью)."""
    raw = rec.get("weightDimensions")
    if isinstance(raw, dict):
        full = _dims_full(raw)
        if full is True:
            return _ok(f"весогабариты на витрине {DIMS_KEYS} все 4")
        if full is False:
            return _missing("weightDimensions частичный — не все 4 числа > 0")
        return _unknown("weightDimensions не разобрать")
    flag = rec.get("wd")
    if flag is None:
        return _unknown("wd-флаг не собран срезом СВЕРКИ")
    return (_ok("weightDimensions на витрине") if flag
            else _missing("на витрине БЕЗ weightDimensions (габаритов нет)"))  # CC3/CC4


def _blk_dims_plan(rec):
    """ГАБАРИТЫ по записи библиотеки/цикла. dims не дан → UNKNOWN (план не знает, что легло
    на витрину — подтвердит живая СВЕРКА), НЕ MISSING: цикл мог залить карточку и без ОВХ. """
    dims = rec.get("dims")
    if dims is None:
        return _unknown("цикл не записал ОВХ (dims пуст) — полноту подтвердит СВЕРКА")
    full = _dims_full(dims)
    if full is True:
        return _ok("ОВХ: length/width/height/weight все > 0")
    if full is False:
        return _missing("габариты неполные: нужны ВСЕ 4 (length/width/height/weight) > 0")
    return _unknown("dims не разобрать")


def _blk_photos(rec, key):
    n = _take(rec, key)
    if n is None:
        return _unknown("фото-данных нет в записи")
    try:
        have = int(n) >= 1
    except (TypeError, ValueError):
        return _unknown("n_photos не число")
    return _ok("фото на месте") if have else _missing("карточка БЕЗ фото (нужно ≥ 1)")


def _blk_description(rec, key):
    ln = _take(rec, key)
    if ln is None:
        return _unknown("длина описания не собрана")
    try:
        length = int(ln)
    except (TypeError, ValueError):
        return _unknown("длина описания не число")
    # CC6: «нет описания» — реальная ошибка карточки (ARB-*), гейтим ровно её.
    return _ok("описание есть") if length > 0 else _missing("описание ПУСТО («нет описания»)")


def _blk_specs(rec, key):
    n = _take(rec, key)
    if n is None:
        return _unknown("число характеристик не собрано")
    try:
        have = int(n) >= 1
    except (TypeError, ValueError):
        return _unknown("spec_n не число")
    # CC9: директива «характеристики ТОЧНО И ВЕРНО» — карточка без параметров неполна.
    return _ok("характеристики есть") if have else _missing("характеристик НЕТ (нужно ≥ 1)")


def _blk_barcode(rec, live):
    if live:
        bs = _take(rec, "barcodes")
        if bs is None:
            return _unknown("штрихкоды не собраны срезом")
        bs = bs if isinstance(bs, (list, tuple)) else [bs]
        return _ok("EAN на месте") if any(str(b).strip() for b in bs) \
            else _missing("на витрине БЕЗ штрихкода")
    bc = rec.get("barcode")
    if bc is None:
        return _unknown("свой EAN не записан (донорский/не задан)")   # план честно: не знаем
    return _ok("свой EAN на месте") if str(bc).strip() else _missing("штрихкод пуст")


def _blk_name(rec):
    name = rec.get("name")
    if name is None:
        return _unknown("имя не в записи")
    nm = str(name).strip()
    if not nm or nm.lower() in _PLACEHOLDER_NAMES:
        return _missing("имя пустое/плейсхолдер")
    # имя == offerId = имя не продающее (директива: продающие имена, не технический id)
    if rec.get("offer_id") and nm == str(rec["offer_id"]):
        return _missing("имя = offerId (техническое, не продающее)")
    return _ok(f"имя задано: {nm[:32]}")


def _blk_price(rec):
    p = _take(rec, "price")
    if p is None:
        return _unknown("цены нет в записи")          # запись могла прийти через остатки
    if isinstance(p, dict):                           # YM-структурированная цена {value,currency}
        return _unknown("цена в структурированном виде — не разобрана, не судим")  # CC2
    try:
        v = float(p)
    except (TypeError, ValueError):
        # Цена ЕСТЬ в записи, но формат не разбираем → UNKNOWN (не знаем), НЕ MISSING
        # («цены нет»): иначе структурированная цена соврала бы «карточка не для продажи».
        return _unknown(f"цена в незнакомом виде ({p!r}) — не судим")
    return _ok(f"цена {v:g}₽") if v > 0 else _missing(f"цена {v:g}₽ — НЕ продаём")


# ── вердикт ─────────────────────────────────────────────────────────────────────

def _verdict(blocks):
    """Свести блоки в вердикт (CC10): MISSING → INCOMPLETE; только UNKNOWN → UNVERIFIED;
    всё OK → COMPLETE. Честные списки missing/unknown — СВЕРКА показывает, чего не хватает."""
    miss = [k for k in BLOCKS if blocks.get(k, {}).get("state") == "MISSING"]
    unk = [k for k in BLOCKS if blocks.get(k, {}).get("state") == "UNKNOWN"]
    if miss:
        return {"ok": False, "verdict": "INCOMPLETE",
                "missing": miss, "unknown": unk, "blocks": blocks,
                "note": f"карточка НЕ полна: нет {', '.join(miss)}"
                        + (f"; не подтверждено: {', '.join(unk)}" if unk else "")}
    if unk:
        return {"ok": None, "verdict": "UNVERIFIED", "missing": [], "unknown": unk,
                "blocks": blocks,
                "note": f"нет известных дыр, но полнота НЕ подтверждена: не собрано "
                        f"{', '.join(unk)}"}
    return {"ok": True, "verdict": "COMPLETE", "missing": [], "unknown": [],
            "blocks": blocks,
            "note": "все блоки полноты на месте"}


def audit_live(rec):
    """Аудит ЖИВОГО среза СВЕРКИ (прочитанного состояния витрины). Пусто/пустое прочитанное
    поле = MISSING (факт, CC3). Ест content-срез node_verify + опц. name/price/spec_n/raw
    weightDimensions, если СВЕРКА их до-читает. Вердикт INCOMPLETE гейт-годен (ok=False)."""
    rec = rec or {}
    blocks = {
        "name": _blk_name(rec),
        "description": _blk_description(rec, "desc_len"),
        "specs": _blk_specs(rec, "spec_n"),
        "dims": _blk_dims_live(rec),
        "barcode": _blk_barcode(rec, live=True),
        "photos": _blk_photos(rec, "n_pics"),
        "price": _blk_price(rec),
    }
    return _verdict(blocks)


def audit_plan(rec):
    """Аудит ЗАПИСИ библиотеки/цикла (что задумано/собрано). Не собранное поле = UNKNOWN,
    не MISSING: план не знает, что реально легло на витрину (подтверждает живая СВЕРКА)."""
    rec = rec or {}
    blocks = {
        "name": _blk_name(rec),
        "description": _blk_description(rec, "description_len"),
        "specs": _blk_specs(rec, "spec_n"),
        "dims": _blk_dims_plan(rec),
        "barcode": _blk_barcode(rec, live=False),
        "photos": _blk_photos(rec, "n_photos"),
        "price": _blk_price(rec),
    }
    return _verdict(blocks)


def audit_many_live(rows):
    """Аудит партии живых срезов (по offerId) → {offerId: вердикт}. Read-only."""
    return {oid: audit_live(r) for oid, r in (rows or {}).items()}


if __name__ == "__main__":
    # Сухая демонстрация (0₽). Слева — живой срез СВЕРКИ, справа — запись библиотеки.
    import json

    film_live = {   # что прочитала СВЕРКА у полной ARB-карточки (фильм, 4/4 факта)
        "name": "Воздушно-пузырьковая плёнка 100 м × 0,75 м, двухслойная, 3 м в рулоне",
        "desc_len": 1238, "spec_n": 13, "wd": True, "n_pics": 4,
        "barcodes": ["4607000000000"], "price": 700,
    }
    hole_live = dict(film_live, wd=False)          # дыра ревью: СВЕРКА видит НЕТ габаритов
    thin_live = {"desc_len": 0, "wd": True, "n_pics": 1, "barcodes": ["4607"]}  # бедный срез
    lib_rec = {   # запись библиотеки после цикла (что задумано/собрано)
        "offer_id": "ARB-53416854", "name": "Воздушно-пузырьковая плёнка 100×0,75 м",
        "description_len": 1238, "spec_n": 13, "n_photos": 4, "barcode": "4607000000000",
        "price": 700, "cost": 300,
        "dims": {"length": 50, "width": 35, "height": 50, "weight": 1438},
    }

    print("ПОЛНОТА КАРТОЧКИ — сухая демонстрация\n")
    for tag, fn, rec in (("ЖИВЬЁМ (СВЕРКА)", audit_live, film_live),
                         ("ЖИВЬЁМ (СВЕРКА) · дыра-без-габаритов", audit_live, hole_live),
                         ("ЖИВЬЁМ (СВЕРКА) · бедный срез", audit_live, thin_live),
                         ("ЗАПИСЬ (библиотека)", audit_plan, lib_rec)):
        v = fn(rec)
        print(f"  {tag}: {v['verdict']}")
        print(f"     {v['note']}")
        if v.get("missing"):
            print(f"     отсутствует: {', '.join(v['missing'])}")
    print("\n(порядок блоков:", ", ".join(BLOCKS) + ")")
    raise SystemExit(0)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OZON FILM FILE V1 — залив ПЛЁНКИ ИЗ ФАЙЛА оператора на кабинет Ozon (из ОЗОН-библиотеки, волна N).

ИСТОЧНИК: канон-строки файла «ОЗОН ВПП 25 ноября низкие цены.xlsx» (runtime/ozon-library/file-rows-*.json,
создаёт ozon_library_v1.py --convert). Это ГОТОВЫЙ к заливке дамп оператора: СВОИ фото (Ozon-CDN),
СВОЯ цена+«до скидки», реальные габариты посылки (г/мм), аннотация. Артикулы tdt_plenka_low_* — наша
БИБЛИОТЕКА (оператор: «артикулы только для нашей библиотеки»). Древо/подвязка к донору — в матрице
ozon_library (donor_link: ссылка /catalog/{артикул}/ на shop.cargo-avto.ru — канон 9600155 закрыт).

ВОЛНА (отбор решает оператор): малые ширины вперёд. Среди 697 рулонов-в-м (Ш 0.15–2.2, честный парсер
ozon_library: ширина = меньшее значение, длина = большее) берём ПЕРВЫЕ N по (ширина↑, длина↑, артикул).
По умолчанию N=300 = все Ш≤0.4 (285) + ближайшие к 0.5 (0.45×1 + 0.5×14) — одобренный состав. Остальные
остаются в библиотеке для будущих кабинетов/волн (директива: «неиспользованное пригодится»).

КАРТОЧКА — та же подтверждённая категория/профиль, что и живая линия плёнки (реюз FILM_CATS из
ozon_film_zaliv_v1, НЕ редактируем): «Дом и сад / Хранение вещей / Упаковочная пленка» dci 17027937,
type 97503, вид «Воздушно-пузырьковая» 11011→970787047, ТН ВЭД 3920108909→971397926, код маркировки
false, страна Россия→90295, Бренд ExpressGo ПО ЗНАЧЕНИЮ (приватный бренд — id не выдумываем).
Отличия от зеркала ЯМ-линии:
  • offer_id = СИСТЕМНЫЙ АРТИКУЛ ozon_article_v1 (VPP-40x5-1…): «по артикулу понятно всё о товаре»,
    артикул — КЛЮЧ (оператор 09.09). Файловый tdt_plenka_low_N остаётся ВНУТРЕННИМ (file_article —
    в журнале/матрице; в карточку НЕ идёт). Связка к донору — в donor_link матрицы, не в SKU.
  • Свой EAN-13 gen_ean13(code) (префикс 2) — анти-СПУ-склейка с живыми карточками донора (960xxxx).
  • Цена/старая цена = ИЗ ФАЙЛА (passthrough, уже посчитаны оператором; старая строго больше — везде).
  • Имя/фото/аннотация = из файла КАК ЕСТЬ (1-в-1, не калечим; HTML аннотации уже снят на конверте).
  • Габариты посылки = из файла (вес г + Ш×В×Д упаковки мм) → плоские поля depth/width/height/weight.
  • Материал=полиэтилен (честно: ВПП — полиэтилен); Цвет ТОЛЬКО из имени (чёрный/прозрачный), чтобы не
    перечить карточке (в файле col34 у «чёрных» рулонов ошибочно «прозрачный» — не повторяем).
  • Аннотация (4191) ≤2000, plain-текст.

ВЫХОДЫ:
  • runtime/ozon-library/file-pour-library.json — журнал ЗАЛИТОГО этой линии (идемпотентно по offer_id,
    пишется ТОЛЬКО при живых imported): offer_id(=системный код) ↔ file_article(tdt)/имя/цена/
    габариты/donor_link/product_id/shelf.
  • Матрица ozon_library (--mark-lib при живых imported): проставляем pour_state на записи волны.

ЗАКОНЫ (как ozon_zaliv_v1 / ozon_film_zaliv_v1):
  • RUBICON: реальная сеть ТОЛЬКО при not dry AND commit (--commit — слово оператора). По умолчанию dry.
  • 200 ≠ успех: imported = status=='imported' AND product_id>0 AND errors==[].
  • Склад/остаток НЕ выдумываем: warehouse_id из живого списка; остаток --count обязателен.
  • В карточку идут ТОЛЬКО рулоны-в-м (type=='рулон-в-м' + размер); пакеты/коробки/ленты — библиотека-только.

Entrypoints (dry по умолчанию; живьё-по-слову --commit):
  python3 ozon_film_file_v1.py --manifest [--wave N]   # состав волны (0₽): ширины/донор/цены
  python3 ozon_film_file_v1.py --build [--limit K]     # сухая сборка карточек волны (0₽ к Ozon)
  python3 ozon_film_file_v1.py --fill                   # СУХОЙ залив (payload собран, 0₽)
  python3 ozon_film_file_v1.py --fill --commit          # ЖИВОЙ залив (РУБИКОН) → журнал + --mark-lib
  python3 ozon_film_file_v1.py --stocks --count N [--commit]  # остатки волны на склад
  python3 ozon_film_file_v1.py --warehouse              # warehouse_id первого склада (живой)
  python3 ozon_film_file_v1.py --library                # журнал залитого (read, 0₽)
  python3 ozon_film_file_v1.py --verify                 # цикл-1: каждый залитый «Продаётся»? (0₽ GET)
"""
import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ozon_article_v1 as ART
import ozon_card_v1 as card
import ozon_hands_write_v1 as W
import ozon_library_v1 as LIB
import process_artifact_v1 as PA        # артефакт-слой: живой залив = НАШ артефакт (директива 2026-09-09)
from uniqueizer_v1 import gen_ean13

# Категория/профиль/бренд — РЕЮЗ живой плёночной линии (подтверждено живьём 08.09), не редактируем.
from ozon_film_zaliv_v1 import CATS as FILM_CATS
from ozon_film_zaliv_v1 import HOUSE_BRAND

MAX_ANNOTATION = 2000      # attr 4191 «Аннотация» — лимит Озона держим как живая линия
TODAY = "2026-09-08"
DEFAULT_WAVE = 434         # остаток лимита кабинета 5473485: лимит ~500 − занято 66 (живой счёт /v3/product/list = ровно 66, 2026-09-09) → 434

POUR_LIB_DEFAULT = HERE / "runtime" / "ozon-library" / "file-pour-library.json"


def pour_library_path():
    env = (os.environ.get("OZON_FILM_FILE_LIBRARY_PATH") or "").strip()
    return Path(env).expanduser() if env else POUR_LIB_DEFAULT


def read_pour_library(path=None):
    p = Path(path) if path else pour_library_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _atom_write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _today():
    return datetime.date.today().isoformat()


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ИСТОЧНИК + ВОЛНА
# ══════════════════════════════════════════════════════════════════════════════════════════════

def codes_index(rows):
    """article(файл tdt) → системный код (ozon_article_v1) по ВСЕМ строкам источника.
    Индекс детерминирован и включает не-рулоны (их коды PUP/BOX/… в другие семьи — VPP не задевают).
    Пусто/нет строк → {}. Считается от строк, а не от матрицы: код = чистая функция фактов строки →
    НЕ зависит от того, что записано в матрице (не дрейфует, матрица «не сбивается»)."""
    recs = [r for r in (rows or []) if isinstance(r, dict)]
    return ART.build_index(recs) if recs else {}


def load_source():
    """Канон-строки + donor_link из матрицы + индекс системных кодов. fail-soft честно.
    → {'rows','donor','codes','_error'}."""
    m = LIB.load_rows()
    if not m["ok"]:
        return {"rows": [], "donor": {}, "codes": {}, "_error": m["_error"]}
    rows = m["rows"]
    codes = codes_index(rows)
    donor = {}
    lib = LIB.load_library()
    if lib and lib.get("records"):
        for r in lib["records"]:
            dl = r.get("donor_link")
            if dl:
                donor[str(r["article"])] = dl
    return {"rows": rows, "donor": donor, "codes": codes, "_error": None}


def pour_candidates(rows):
    """Рулоны-в-м с честным размером (type 'рулон-в-м' + size) — только их льём в категорию ВПП."""
    out = [r for r in rows
           if r.get("type") == "рулон-в-м" and isinstance(r.get("size"), dict)]
    out.sort(key=lambda r: (r["size"]["w_m"], r["size"]["l_m"], r["article"]))
    return out


def select_wave(rows, wave=DEFAULT_WAVE):
    """Волна: первые `wave` рулонов по (ширина↑,длина↑,артикул). wave<=0 или >=всех → вся партия."""
    cands = pour_candidates(rows)
    if wave is None or int(wave) <= 0 or int(wave) >= len(cands):
        return cands
    return cands[:int(wave)]


def wave_width_counts(rows):
    import collections
    return dict(collections.Counter(round(r["size"]["w_m"], 2) for r in rows))


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  КАРТОЧКА (файл → prod → to_item). Шаблон фактов/спека — как живая линия, но из файла.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _name_color(name):
    """Цвет ТОЛЬКО из имени (не повторяем ошибку файла col34 у «чёрных»). → 'прозрачный'|'черный'|None."""
    n = (name or "").lower().replace("ё", "е")
    if any(k in n for k in ("черн", " black", "black ")):
        return "черный"
    if any(k in n for k in ("прозрач", "бесцветн", "clear")):
        return "прозрачный"
    return None


def prod_of(row, donor=None, code=None):
    """Канон-строка файла → prod для to_item (реальные факты файла; ничего не выдумываем).

    offer_id/модель-9048/EAN = СИСТЕМНЫЙ КОД (code) — публичный артикул-ключ. Файловый артикул
    (tdt_plenka_low_N) НЕ в карточку: он уходит в prod['file_article'] (журнал + проставление матрицы,
    чей ключ = файловый артикул → матрица не сбивается)."""
    size = row["size"] or {}
    w_cm = int(round(size["w_m"] * 100))     # ширина полотна см (атрибут 8416)
    l_m = float(size["l_m"])                 # длина намотки м (атрибут 6468)
    pkg = row.get("pkg_mm") or {}
    weight = row.get("weight_g")
    dims = None
    if pkg and weight:
        try:
            if all(float(pkg.get(k) or 0) > 0 for k in ("width", "height", "depth")) and float(weight) > 0:
                dims = {"depth": int(round(pkg["depth"])), "width": int(round(pkg["width"])),
                        "height": int(round(pkg["height"])), "weight": int(round(weight))}
        except (TypeError, ValueError):
            dims = None
    oid = code or row["article"]             # публичный артикул = код (файловый — только как file_article)
    spec = {
        "_model": oid,                        # Название модели (9048) = артикул — анти-склейка (1 карточка/SKU)
        "_length_m": l_m,
        "_width_cm": w_cm,
        "_units": 1,                          # продаём 1 рулон (честно)
        "материал": "полиэтилен",             # ВПП — полиэтилен (файл col33 единогласно; словарь 62043)
    }
    col = _name_color(row["name"])
    if col:
        spec["цвет"] = col                    # словарь: прозрачный 61572 / черный 61574
    ann = (row.get("annotation") or "").strip()
    if ann:
        spec["_desc"] = ann[:MAX_ANNOTATION]  # attr 4191 Аннотация, plain-текст (HTML уже снят на конверте)

    prod = {
        "offer_id": oid,
        "name": row["name"],                  # имя файла 1-в-1 (не калечим)
        "price": row["price"],
        "old_price": row.get("old_price"),    # только если строго > price (гейт в to_item)
        "vat": "0",                           # УСН — ставка честная
        "images": row.get("images") or [],    # СВОИ фото файла (Ozon-CDN; до 15)
        "barcode": gen_ean13(oid),            # свой EAN (префикс 2) — рычаг уникальности
        "file_article": row["article"],       # файловый ключ (журнал/матрица, НЕ в карточку)
        "_spec": spec,
    }
    if dims:
        prod["dimensions"] = dims
    if donor:                                 # подвязка к донору (в prod — для журнала, НЕ в карточку)
        prod["donor_url"] = donor.get("url")
        prod["donor_article"] = donor.get("article")
        prod["donor_near"] = bool(donor.get("near"))
    return prod


def build_cards(rows, donor=None, codes=None):
    """Рулоны волны → карточки {'row','prod','item','meta'}. item=None = блок (нет кода/OZ2/нет категории).

    offer_id карточки = СИСТЕМНЫЙ код (codes[файловый артикул] → VPP-…). codes не переданы — считаем
    индекс по переданным строкам (герметичные тесты: фикстура = весь набор). Файловый артикул row
    остаётся ключом донора/журнала (в prod.file_article); в карточку не попадает.
    """
    out = []
    idx = dict(codes) if codes else codes_index(rows)
    for row in rows:
        dl = (donor or {}).get(row["article"])
        code = (idx or {}).get(str(row["article"]))
        if not code:                          # рулон без кода = блок (не выдумываем артикул)
            out.append({"row": row, "prod": prod_of(row, donor=dl),
                        "item": None, "meta": {"offer_id": row["article"], "can_build": False,
                                               "block_reason": "нет системного кода в индексе",
                                               "missing_images": True, "has_barcode": False}})
            continue
        prod = prod_of(row, donor=dl, code=code)
        r = card.to_item(prod, slug="vpp-plenka", cats=FILM_CATS, unique_name=False)
        out.append({"row": row, "prod": prod, "item": r["item"], "meta": r["meta"]})
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ЖУРНАЛ ЗАЛИТОГО (эта линия файла) + проставление матрицы
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _pkg_str(row):
    pkg = row.get("pkg_mm") or {}
    w = row.get("weight_g")
    if pkg and w:
        return f"{pkg['width']}×{pkg['height']}×{pkg['depth']}мм {int(w)}г"
    return None


def record_pour(built, imported, path=None, shelf=None):
    """Живой импорт → журнал этой линии (идемпотентно по offer_id=код). Пустой imported → НЕ пишем."""
    imp = {str(i.get("offer_id")): i for i in (imported or [])}
    if not imp:
        return {"ok": False, "written": 0, "_error": "нет импортированных — записывать нечего"}
    lib = read_pour_library(path)
    written = 0
    for b in built:
        m = b.get("meta") or {}
        if m.get("can_build") is not True:
            continue
        oid = str(m.get("offer_id") or "").strip()
        it = imp.get(oid)
        if not it:
            continue
        row = b.get("row") or {}
        prod = b.get("prod") or {}
        lib[oid] = {
            "offer_id": oid,
            "code": oid,                                  # системный артикул (публичный)
            "file_article": str(row.get("article") or ""),  # файловый артикул (внутр. ключ матрицы)
            "name": str(row.get("name") or "").strip()[:180],
            "price": row.get("price"),
            "old_price": row.get("old_price"),
            "size": row.get("size"),
            "pkg": _pkg_str(row),
            "donor_url": prod.get("donor_url"),          # подвязка к донору (shop.cargo-avto.ru/catalog/…)
            "donor_article": prod.get("donor_article"),
            "donor_near": prod.get("donor_near"),
            "product_id": it.get("product_id"),
            "status": str(it.get("status")),
            "shelf": (shelf or {}).get(oid),
            "recorded": _today(),
        }
        written += 1
    if not written:
        return {"ok": False, "written": 0, "_error": "ни один offer_id не совпал с импортированными"}
    _atom_write(path if path else pour_library_path(), lib)
    return {"ok": True, "written": written, "total": len(lib)}


def mark_library_pour(imported, path=None):
    """Проставить pour_state в матрице-библиотеке по реально импортированным (атомарно).

    Матрица ключуется ФАЙЛОВЫМ артикулом (article=tdt) — её НЕ пере-ключуем (не сбиваем). Импортированные
    несут offer_id=системный код + file_article=tdt (проставил fill) → находим запись матрицы по
    file_article. Нет file_article (старый формат) → ищем по offer_id (код-эпоха не смешивается)."""
    imp = [i for i in (imported or []) if (i.get("product_id") or 0) > 0]
    if not imp:
        return {"ok": False, "updated": 0, "_error": "нет импортированных с product_id"}
    libp = LIB.library_path() if path is None else Path(path)
    try:
        lib = json.loads(libp.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "updated": 0, "_error": f"{type(e).__name__}: {e}"}
    by_file = {}
    for i in imp:
        art = str(i.get("file_article") or "").strip() or str(i.get("offer_id") or "").strip()
        if art:
            by_file.setdefault(art, i)
    updated = 0
    for rec in lib.get("records", []):
        it = by_file.get(str(rec.get("article")))
        if not it:
            continue
        if rec.get("pour_state") and rec["pour_state"].get("product_id") == it.get("product_id"):
            continue
        rec["pour_state"] = {"wave": DEFAULT_WAVE, "product_id": it.get("product_id"),
                             "status": str(it.get("status")), "recorded": _today()}
        updated += 1
    if updated:
        _atom_write(libp, lib)
    return {"ok": True, "updated": updated}


def pour_mark_shelf(report, path=None):
    """Поле shelf записей журнала по сверке витрины (offer_id → «Продаётся»/…)."""
    report = {str(k): v for k, v in (report or {}).items() if v}
    if not report:
        return {"ok": False, "updated": 0, "_error": "пустой отчёт сверки"}
    lib = read_pour_library(path)
    updated = 0
    for oid, status in report.items():
        rec = lib.get(oid)
        if rec is None or rec.get("shelf") == status:
            continue
        rec["shelf"] = status
        updated += 1
    if not updated:
        return {"ok": True, "updated": 0, "total": len(lib)}
    _atom_write(path if path else pour_library_path(), lib)
    return {"ok": True, "updated": updated, "total": len(lib)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  АРТЕФАКТ ПРОГОНА (каждый живой залив = НАШ артефакт — директива 2026-09-09)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def seal_pour_artifact(*, built, imported, failures=None, task_id="", owner="OZON_ZALIV", date=None,
                       journal_path=None, commit=False):
    """Живой залив → артефакт kind=pour в библиотеке процессов (process_artifact_v1.seal).

    Зовётся в живой ветке --fill --commit ПОСЛЕ record_pour: журнал уже дописан. Читает журнал
    этой волны (только залитое сейчас, не весь журнал — будущие волны не задваивают карточки в
    знании), сворачивает knowledge категории и печатает/seals отчёт. commit=False → честное СУХО
    (ничего не пишет). Сети НЕТ — только свои файлы. result.ok = были ли ошибки пакетов (честно)."""
    oids = [str(i.get("offer_id")) for i in (imported or [])
            if (i.get("product_id") or 0) > 0 and str(i.get("status")) == "imported"]
    if not oids:
        return {"ok": False, "error": "нет импортированных — артефакт не из чего"}
    jp = Path(journal_path) if journal_path else pour_library_path()
    journal = read_pour_library(jp)
    sub = {o: journal[o] for o in oids if o in journal}
    fails = [f for f in (failures or [])]
    what = f"Залив ВПП-рулонов на Ozon из файла — волна {len(oids)} карточек"
    rec, err = PA.normalize({
        "kind": "pour", "market": "ozon", "category": "vpp-film",
        "date": date or _today(), "what": what, "task_id": task_id, "owner": owner,
        "params": {"source": "файл «ОЗОН ВПП …xlsx» (канон-строки ozon_library --convert)",
                   "mode": "live", "wave_cards": len(oids),
                   "article_scheme": "системный артикул VPP-… на карточке (ozon_article_v1); "
                                     "файловый tdt — в журнале/матрице"},
        "decision": {"word": "живой залив (--commit — слово оператора)",
                     "via": "operator", "note": "task_id доски, если задан: " + (task_id or "—")},
        "result": {"ok": not fails, "imported": len(oids), "product_id": len(oids),
                   "failures": len(fails),
                   "shelf": "см. сверку витрины (verify_shelf)"},
        "artifacts": {"journal": str(jp)},
        "knowledge": PA.summarize_vpp(sub),
    })
    if err:
        return {"ok": False, "error": err}
    return PA.seal(rec, commit=commit, organ=owner,
                   log_what="авто-артефакт живого залива (врезка ozon_film_file_v1)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ОТЧЁТЫ
# ══════════════════════════════════════════════════════════════════════════════════════════════

def render_manifest(rows, donor=None, codes=None):
    lines = [f"ВОЛНА ФАЙЛА · рулонов {len(rows)}"]
    wc = wave_width_counts(rows)
    lines.append("  по ширине: " + ", ".join(f"{w}м={wc[w]}" for w in sorted(wc)))
    donor_ok = sum(1 for r in rows if (donor or {}).get(r["article"]))
    lines.append(f"  подвязка к донору в волне: {donor_ok}/{len(rows)}")
    for r in rows[:12]:
        code = (codes or {}).get(r["article"]) or "?"
        dl = (donor or {}).get(r["article"])
        tag = (f"→ донор {dl['article']}{' (около)' if dl.get('near') else ''}" if dl else "без донора")
        lines.append(f"  {code:14s} ← {r['article']} · {r['size']['w_m']}×{r['size']['l_m']}м · "
                     f"{r['price']}₽ (старая {r.get('old_price')}) · {r['name'][:40]} · {tag}")
    if len(rows) > 12:
        lines.append(f"  … и ещё {len(rows) - 12}")
    return "\n".join(lines)


def render_build(built):
    ok = [b for b in built if b["item"] is not None]
    blocked = [b for b in built if b["item"] is None]
    lines = [f"КАРТОЧКИ (файл) · всего {len(built)} · готово {len(ok)} · блок {len(blocked)}"]
    for b in ok:
        m = b["meta"]
        fa = (b.get("row") or {}).get("article", "")
        lines.append(f"  🟢 {m['offer_id']} · (файл {fa}) · {m['price']}₽ · dci={m['description_category_id']} "
                     f"type={m['type_id']} · фото={'есть' if not m['missing_images'] else 'НЕТ'} · "
                     f"габариты={'есть' if not m['missing_dimensions'] else 'нет'} · "
                     f"EAN={'есть' if m['has_barcode'] else 'нет'} · аттр={m['attrs_built']} · "
                     f"имя '{b['item'].get('name', '')[:44]}'")
    for b in blocked:
        lines.append(f"  🔴 {b['meta']['offer_id']} · блок: {b['meta'].get('block_reason')}")
    return "\n".join(lines)


def render_fill_report(imported, failures, dry):
    lines = [f"ЗАЛИВ · {'СУХО (payload собран, 0₽)' if dry else 'ЖИВОЙ'}"
             f" · импортировано {len(imported)} · ошибок {len(failures)}"]
    for it in imported:
        lines.append(f"  ✅ {it.get('offer_id')} → product_id={it.get('product_id')}")
    for f in failures:
        lines.append(f"  ❌ {f.get('offer_id')} · status={f.get('status')} · errors={f.get('errors')}")
    return "\n".join(lines)


def render_stocks(payload, warehouse_id, dry):
    return (f"ОСТАТКИ · {'СУХО (payload собран, 0₽)' if dry else 'ЖИВОЙ'} · склад {warehouse_id} · SKU "
            f"{len(payload)}\n" + "\n".join(f"  {s['offer_id']} → {s['stock']}" for s in payload))


def render_library(lib):
    lines = [f"ЖУРНАЛ ЗАЛИТОГО (файл-линия) · записей {len(lib)}"]
    on_sale = sum(1 for r in lib.values() if r.get("shelf") == "Продаётся")
    for oid in sorted(lib):
        r = lib[oid]
        fa = r.get("file_article") or ""
        lines.append(f"  • {oid} · (файл {fa}) · product_id={r.get('product_id')} · "
                     f"{(r.get('donor_url') or 'без донора')} · {(r.get('name') or '')[:40]} · "
                     f"цена {r.get('price')}₽ · статус={r.get('shelf') or r.get('status')}")
    if lib:
        lines.append(f"  ·· «Продаётся»: {on_sale}/{len(lib)}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ФАЗЫ (зеркало ozon_zaliv_v1 / ozon_film_zaliv_v1)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def items_of(built):
    return [b["item"] for b in built if b["item"] is not None]


def first_warehouse_id():
    try:
        whs = W.warehouse_list(timeout=20).get("warehouses", [])
    except Exception:
        return None, None
    for wh in whs:
        wid = wh.get("warehouse_id")
        if wid is not None:
            return wid, wh.get("name")
    return None, None


def fill(built, dry=True, commit=False, poll_attempts=24, poll_delay=8, chunk=100):
    """FILL: item → /v3/product/import ЧАНКАМИ ≤100 → опрос import_info → агрегат.

    Кап Ozon = 100 item на один вызов /v3/product/import — волна 434 одним вызовом была бы
    отвергнута. Поэтому режем на chunk≤100; каждый пакет → свой task_id → опрос → импортированные
    и ошибки агрегируем по всем пакетам (record_pour/mark_library_pour пишут по импортированным).
    Dry: печатаем метку и возвращаем ok (payload НЕ летит, 0₽).
    """
    items = items_of(built)
    if not items:
        print("ЗАЛИВ · блок: нет готовых карточек (всё блок)")
        return {"ok": False, "imported": [], "failures": [], "_error": "нет готовых карточек"}
    # offer_id = системный код → файловый артикул (мост к матрице, ключуемой tdt)
    code_of = {str((b.get("meta") or {}).get("offer_id") or "").strip(): str((b.get("row") or {}).get("article") or "")
               for b in built if (b.get("meta") or {}).get("can_build")}
    if dry:
        print(render_fill_report([], [], dry=True))
        return {"ok": True, "dry": True, "items_ready": len(items)}
    n_batches = (len(items) + chunk - 1) // chunk
    imported, failures = [], []
    for start in range(0, len(items), chunk):
        batch = items[start:start + chunk]
        k = start // chunk + 1
        res = W.create_product(batch, dry=dry, commit=commit)
        if res.get("status") != "sent":
            msg = f"пакет {k}/{n_batches}: transport {res.get('_error')}"
            print(msg)
            failures.append({"offer_id": "?", "status": "transport", "errors": [msg]})
            continue
        resp = res.get("response") or {}
        task_id = (resp.get("result") or {}).get("task_id") or resp.get("task_id")
        if task_id is None:
            msg = f"пакет {k}/{n_batches}: task_id не получен — карточка НЕ создана"
            print(msg)
            failures.append({"offer_id": "?", "status": "no-task-id", "errors": [msg]})
            continue
        info = []
        for _ in range(poll_attempts):
            info = W.import_info(task_id)
            if not info:
                time.sleep(poll_delay)
                continue
            if all(str(i.get("status")) != "pending" for i in info):
                break
            time.sleep(poll_delay)
        got = len(info or [])
        if not got:
            msg = f"пакет {k}/{n_batches}: import_info пуст за {poll_attempts} попыток — результат НЕ известен"
            print(msg)
            failures.append({"offer_id": "?", "status": "unknown", "errors": [msg]})
            continue
        for it in info:
            it["file_article"] = code_of.get(str(it.get("offer_id") or "").strip()) or ""
            status = str(it.get("status"))
            pid = it.get("product_id") or 0
            errs = [str(e) for e in (it.get("errors") or [])]
            if status == "imported" and pid and not errs:
                imported.append(it)
            else:
                failures.append({"offer_id": it.get("offer_id"), "status": status,
                                 "errors": errs, "product_id": pid})
        print(f"  пакет {k}/{n_batches} · task={task_id} · в ответе {got}")
    print(render_fill_report(imported, failures, dry=False))
    return {"ok": not failures, "imported": imported, "failures": failures,
            "_error": None if not failures else f"{len(failures)} ошибочных", "n_batches": n_batches}


def stocks(cards, count=None, dry=True, commit=False):
    """STOCKS: остатки волны на первый склад. count обязателен (не выдумываем остаток).

    ЧАНКИ ≤100 на вызов /v2/products/stocks (кап Ozon) — волна 434 одним вызовом была бы отвергнута.
    Режем на пакеты ≤100; каждый пакет шлём своим вызовом (как fill). Dry: payload собран, 0₽.
    """
    if count is None:
        print("ОСТАТКИ · блок: count не задан — остаток НЕ выдумываем (--count N)")
        return {"ok": False, "_error": "count не задан"}
    try:
        cnt = int(count)
    except (TypeError, ValueError):
        print("ОСТАТКИ · блок: count не число")
        return {"ok": False, "_error": "count не число"}
    if cnt <= 0:
        print("ОСТАТКИ · блок: count должен быть > 0")
        return {"ok": False, "_error": "count ≤ 0"}
    wid, wname = first_warehouse_id()
    if wid is None:
        print("ОСТАТКИ · блок: складов в кабинете нет (warehouse_id не выдумываем). Создать в seller.ozon.ru")
        return {"ok": False, "_error": "склад не создан"}
    payload = [{"offer_id": c["meta"]["offer_id"], "warehouse_id": wid, "stock": cnt}
               for c in cards if c["item"] is not None]
    if not payload:
        print("ОСТАТКИ · блок: нет готовых карточек — остаток ставить не на что")
        return {"ok": False, "_error": "нет карточек"}
    if dry:
        print(render_stocks(payload, wid, dry=True))
        return {"ok": True, "dry": True, "payload": payload}
    n_batches = (len(payload) + 99) // 100
    failures, last = [], None
    for start in range(0, len(payload), 100):
        batch = payload[start:start + 100]
        k = start // 100 + 1
        res = W.set_stock(batch, dry=dry, commit=commit)
        if res.get("status") != "sent":
            msg = f"пакет {k}/{n_batches}: transport {res.get('_error')}"
            print("  " + msg)
            failures.append({"offer_id": "?", "error": msg})
        else:
            last = res.get("response")
            print(f"  пакет {k}/{n_batches} · SKU {len(batch)} · ok")
    print(render_stocks(payload, wid, dry=False))
    if failures:
        print(f"ОСТАТКИ · ошибок пакетов: {len(failures)}")
        return {"ok": False, "_error": f"{len(failures)} ошибочных пакетов", "failures": failures}
    return {"ok": True, "response": last, "n_batches": n_batches}


def shelf_status_of(card):
    if not isinstance(card, dict):
        return "не найдена"
    if card.get("_error"):
        return f"сверка недоступна: {card['_error']}"
    if card.get("visible"):
        return "Продаётся"
    errs = card.get("errors") or []
    if errs:
        return "ошибки: " + "; ".join(str(e) for e in errs[:3])
    mod = card.get("moderation")
    if mod in ("approved", None, ""):
        return "одобрена, но скрыта"
    return "на модерации"


def verify_shelf(imported, timeout=30):
    offered = [str(i.get("offer_id") or "").strip() for i in (imported or [])
               if str(i.get("offer_id") or "").strip() and (i.get("product_id") or 0) > 0]
    if not offered:
        return {"ok": False, "report": {}, "_error": "нет импортированных с product_id — сверять нечего"}
    try:
        res = W.read_shelf(offered, timeout=timeout)
    except Exception as e:
        return {"ok": False, "report": {}, "_error": f"{type(e).__name__}: {e}"}
    by_oid = {str(c.get("offer_id")): c for c in res.get("cards", [])}
    report = {oid: shelf_status_of(by_oid.get(oid)) for oid in offered}
    if not res.get("ok"):
        return {"ok": False, "report": report, "_error": res.get("_error") or "сверка недоступна"}
    return {"ok": True, "report": report}


def render_shelf_report(report):
    lines = [f"ВИТРИНА (цикл-1) · сверено {len(report)}"]
    on_sale = sum(1 for s in report.values() if s == "Продаётся")
    for oid in sorted(report):
        st = report[oid]
        lines.append(f"  {('🟢' if st == 'Продаётся' else '🔴')} {oid} · {st}")
    lines.append(f"  ·· «Продаётся»: {on_sale}/{len(report)}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════════════════════

def main(argv=None):
    ap = argparse.ArgumentParser(description="OZON FILM FILE V1 — залив плёнки ИЗ ФАЙЛА (dry по умолчанию)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--manifest", action="store_true", help="состав волны (0₽)")
    g.add_argument("--build", action="store_true", help="сухая сборка карточек волны (0₽ к Ozon)")
    g.add_argument("--warehouse", action="store_true", help="warehouse_id первого склада")
    g.add_argument("--fill", action="store_true", help="залив карточек (dry; --commit — живой)")
    g.add_argument("--stocks", action="store_true", help="остатки волны (dry; --commit — живой)")
    g.add_argument("--library", action="store_true", help="журнал залитого этой линии (read, 0₽)")
    g.add_argument("--verify", action="store_true", help="цикл-1: каждый залитый «Продаётся»? (0₽ GET)")
    ap.add_argument("--wave", type=int, default=DEFAULT_WAVE, help="сколько рулонов в волне (0/отриц = все)")
    ap.add_argument("--limit", type=int, default=None, help="--build: собрать только первые K (отладка)")
    ap.add_argument("--count", type=int, default=None, help="--stocks: остаток на каждый SKU (обязателен)")
    ap.add_argument("--commit", action="store_true", help="ЖИВОЙ режим (РУБИКОН: слово оператора)")
    ap.add_argument("--mark-lib", action="store_true", help="после живого залива проставить матрицу")
    ap.add_argument("--task", default="", metavar="T-ID", help="задание доски, из которого рождён залив "
                                                               "(артефакт ссылается на него)")
    args = ap.parse_args(argv)

    src = load_source()
    if src["_error"]:
        print("source ERR: " + src["_error"]); return 1
    rows = src["rows"]
    donor = src["donor"]

    if args.warehouse:
        wid, wname = first_warehouse_id()
        print(f"СКЛАД · warehouse_id={wid}" + (f" · {wname}" if wname else "") if wid else "СКЛАД · нет складов")
        return 0 if wid else 1

    if args.library:
        lib = read_pour_library()
        print(render_library(lib))
        return 0

    wave_rows = select_wave(rows, wave=args.wave)
    if not wave_rows:
        print("ВОЛНА · пусто: рулонов-в-м с размером в библиотеке нет — сначала --convert в ozon_library_v1")
        return 1

    if args.manifest:
        print(render_manifest(wave_rows, donor=donor, codes=src["codes"]))
        return 0

    if args.build:
        sel = wave_rows[:args.limit] if args.limit else wave_rows
        built = build_cards(sel, donor=donor, codes=src["codes"])
        print(render_build(built))
        return 0

    if args.fill:
        dry = not args.commit
        built = build_cards(wave_rows, donor=donor, codes=src["codes"])
        res = fill(built, dry=dry, commit=args.commit)
        if not dry and res.get("imported"):
            rp = record_pour(built, res["imported"])
            print(f"  журнал: {'записано ' + str(rp['written']) + '/' + str(rp.get('total')) if rp.get('ok') else 'НЕ записано — ' + rp.get('_error', '?')}")
            if args.mark_lib:
                ml = mark_library_pour(res["imported"])
                print(f"  матрица: {'проставлено ' + str(ml['updated']) if ml.get('ok') else 'НЕ проставлено — ' + ml.get('_error', '?')}")
            if res.get("ok"):
                vs = verify_shelf(res["imported"])
                print(render_shelf_report(vs.get("report", {})))
                if vs.get("ok"):
                    pour_mark_shelf(vs["report"])
            # авто-артефакт прогона (директива 2026-09-09): каждый живой залив = НАШ артефакт.
            # Только в живой ветке (not dry); канон-журналы не трогает — только читает + seal.
            art = seal_pour_artifact(built=built, imported=res["imported"],
                                     failures=res.get("failures"),
                                     task_id=args.task or "", commit=True)
            if art.get("ok"):
                print(f"  артефакт прогона: {art.get('id')} → {art.get('md')}")
            else:
                print(f"  артефакт прогона: НЕ создан — {art.get('error')}")
        return 0 if (dry or res.get("ok")) else 1

    if args.stocks:
        dry = not args.commit
        built = build_cards(wave_rows, donor=donor, codes=src["codes"])
        res = stocks(built, count=args.count, dry=dry, commit=args.commit)
        return 0 if (dry or res.get("ok")) else 1

    if args.verify:
        lib = read_pour_library()
        imported = [{"offer_id": oid, "product_id": r.get("product_id")}
                    for oid, r in lib.items() if r.get("product_id")]
        if not imported:
            print("ВИТРИНА · журнал пуст — залей сначала (--fill --commit)")
            return 1
        vs = verify_shelf(imported)
        print(render_shelf_report(vs.get("report", {})))
        if vs.get("ok"):
            pour_mark_shelf(vs["report"])
        return 0 if vs.get("ok") else 1

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

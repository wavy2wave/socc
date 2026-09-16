#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON FILM ZALIV V1 — цикл залива ПЛЁНКИ (ВПП) на кабинет Ozon (зеркало ozon_zaliv_v1 под плёнку).

ЗЕРКАЛО сегодняшнего залива ЯМ (оператор, дословно): «глянь сегодняшний залив на ЯМ … просто возьми
всё на озон это же. цены держим одинаково что там что там». ИСТОЧНИК — тот же живой скан донора
(shop.cargo-avto.ru), что льёт ЯМ: `ymarket_film_batch_v1.assemble_new_rows()` + сборка карточки
`ymarket_film_cards_v1.build_product` — РЕЮЗ как библиотеки (файлы ymarket_* НЕ трогаем). Цена = та же
закупка × тот же markup (8.0) → копейка-в-копейку с ЯМ. offer_id (SKU на Ozon) = АРТИКУЛ донора —
РЕАЛЬНЫЙ товар на сайте (директива оператора 08.09: «SKU должны быть на товарах… SKU - реальный товар
на сайте донора… при заказе системе проще сразу найти товар который мы взяли»); свой ARB-sku остаётся
в prod['sku'] (ключ фото/журнала) и в «Названии модели» (анти-склейка). Свой EAN-13 от артикула.

КАРТОЧКА (проверено живьём 2026-09-08, кабинет 5473485, категория «Дом и сад / Хранение вещей /
Упаковочная пленка» dci=17027937, type 97503):
  • Категория НЕ выдумана (закон OZ2): на Ozon НЕТ литерала «Воздушно-пузырьковая плёнка» — это НЕ
    категория, а словарное значение «Вид упаковочной пленки» (11011, dict 58327342 → dvid 970787047)
    в категории «Упаковочная пленка» (17027937/97503). Всё подтверждено живым деревом/словарями.
  • Обязательные: Бренд(85, req) = 'ExpressGo' ПО ЗНАЧЕНИЮ (в словаре категории бренда НЕТ — не
    выдумываем id); ТН ВЭД(22232, req) = 3920108909 → dvid 971397926; Название модели(9048, req) = наш
    ARB-sku (анти-склейка); Нужен код маркировки(23536, req) = false (не маркируется, честно).
  • Страна-изготовитель(4389) = Россия → dvid 90295 (константа категории, вся линия RU).
  • Полная карточка из фактов: Аннотация(4191) = НАШЕ описание (без HTML, ATLAS EDGE → ExpressGo);
    Длина(6468, м — намотка), Ширина(8416, см — полотно ×100 из м), Единиц(8962) = 1.
  • Словарные (добровольные, из фактов донора): Материал(6383) = Полиэтилен → dvid 62043; Цвет(10096):
    прозрачный → 61572 / черный → 61574. Нет в словаре (вдруг факт иной) → атрибут НЕ шлём (не выдумка).
  • Габариты посылки: weightDimensions из ОВХ-габаритов (см/кг → Озон mm/g в to_item). НЕ выдумываем.
  • Имя: ФИРМЕННОЕ «Плёнка воздушно-пузырьковая …» из фактов (реюз _build_name) — НЕ копия донора.
  • Фото: публичные URL из фото-журнала (runtime/photo_god/atlas-express-film/*.jsonl) по ARB-sku —
    рабочие кадры сегодняшней линии ЯМ (те же, что на витрине ЯМ).

ЗАКОНЫ (зеркало ozon_zaliv_v1):
  • RUBICON: реальная сеть ТОЛЬКО при not dry AND commit (--commit — слово оператора). По умолчанию dry.
  • 200 ≠ успех: читаем errors[] из import_info; успех = status=='imported' AND product_id>0 AND errors==[].
  • Склад НЕ выдумываем: warehouse_id только из живого /v2/warehouse/list. Склада нет → честный блок.
  • Остаток НЕ выдумываем: count обязателен (--count N); ставим только на «В наличии» донора.
  • «В наличии» честно: только _stock=="in_stock" строки донора считаем наличием.

ДИРЕКТИВЫ ОПЕРАТОРА 2026-09-08 (дословно):
  • БРЕНД = ExpressGo ВЕЗДЕ (оператор: «нужен ExpressGo - везде», «это мой бренд, я регал когда то»).
    ExpressGo — зарегистрированный бренд оператора в кабинете (селектится в UI). В ПУБЛИЧНОМ словаре
    значений категории его НЕТ (101 576 значений просканировано 08.09) — это приватный бренд продавца,
    id наружу API не отдаёт. Как и на ленте (закон Z5) шлём ПО ЗНАЧЕНИЮ, dictionary_value_id НЕ
    выдумываем. Прежний 'ATLAS EDGE' падал error_attribute_values_out_of_range ровно потому, что такого
    бренда в каталоге Ozon нет вообще.
  • ДВЕ ЦЕНЫ: цена продажи price (зеркало ЯМ, копейка-в-копейку) + ЗАЧЁРКНУТАЯ old_price = price + ~500₽
    («используй цену и зачёркнутую цену, типа мы скидку сделали, примерно 500 рублей»).
  • ПОЛНАЯ КАРТОЧКА КАК ЯМ: наша аннотация (атрибут 4191 «Аннотация»), страна-изготовитель «Россия»
    (4389, dvid 90295), длина/ширина/единиц из фактов, цвет/материал, габариты ОВХ (weightDimensions).
    «а главное ОВХ на озон - принципиально важно!!!!» → габариты шлём (см/кг → мм/г в to_item).
  • SKU = РЕАЛЬНЫЙ товар донора (оператор, дословно): «SKU должны быть на товарах… где SKU - реальный
    товар на сайте донора. Важна связка внутри системы, ведь при заказе системе проще сразу найти товар
    который мы взяли в обсос». offer_id = АРТИКУЛ донора (article — живой /catalog/{article}/), а не ARB.
    Каждый ЗАЛИТЫЙ товар пишем в МАТРИЦУ-БИБЛИОТЕКУ (runtime/ozon-film/pour-library.json): offer_id(article)
    ↔ donor_url / имя / закупка / цена / габариты / ARB-sku / product_id — заказ мгновенно выходит на донора.

Entrypoints (все dry по умолчанию; живьё-по-слову --commit):
  python3 ozon_film_zaliv_v1.py --build              # СУХАЯ сборка: карточки зеркала ЯМ (0₽, сеть к Ozon не ходит)
  python3 ozon_film_zaliv_v1.py --fill               # СУХОЙ залив (payload собран, ничего не летит)
  python3 ozon_film_zaliv_v1.py --fill --commit      # ЖИВОЙ залив (РУБИКОН: слово оператора) → пишет матрицу
  python3 ozon_film_zaliv_v1.py --stocks --count N   # СУХИЕ остатки на склад (показать payload)
  python3 ozon_film_zaliv_v1.py --stocks --count N --commit  # ЖИВЫЕ остатки
  python3 ozon_film_zaliv_v1.py --warehouse          # warehouse_id из живого кабинета
  python3 ozon_film_zaliv_v1.py --poured             # сегодняшний залитый набор pids (из журнала ЯМ)
  python3 ozon_film_zaliv_v1.py --library            # печать матрицы-библиотеки залитого (read, 0₽)
  python3 ozon_film_zaliv_v1.py --lookup 9602472     # одна запись матрицы по offer_id (read, 0₽)
  python3 ozon_film_zaliv_v1.py --verify             # цикл-1: статус каждого залитого «Продаётся»? (0₽ GET)
    (после --fill --commit сверка витрины идёт сама; --verify — повторный контроль перед новой категорией)
"""
import argparse
import datetime
import json
import math
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ozon_card_v1 as card
import ozon_hands_write_v1 as W

HOUSE_BRAND = "ExpressGo"    # бренд оператора (зарегистрирован в кабинете Ozon), директивы 08.09

# ДВЕ ЦЕНЫ (оператор, дословно): «используй цену и зачёркнутую цену, типа мы скидку сделали,
# примерно 500 рублей скидку». Зачёркнутая = цена продажи (зеркало ЯМ) + шаг 500₽.
OLD_PRICE_STEP = 500
MAX_ANNOTATION = 2000         # attr 4191 «Аннотация»: лимит Озона держим с запасом ниже (обрезаем ровно)

# Живой URL карточки товара ДОНОРА (связка заказа: offer_id → реальный товар, который взяли).
DONOR_BASE = "https://sp.cargo-avto.ru/catalog/"

# ── Категория «Упаковочная пленка» под ВПП (ОТЛОВЛЕНА живьём 2026-09-08) ──
VPP_DCI = 17027937                     # description_category_id «Дом и сад / Хранение вещей / Упаковочная пленка»
VPP_TID = 97503                        # type_id «Упаковочная пленка»
VPP_VID_DVID = 970787047               # attr 11011 «Вид упаковочной пленки» → «Воздушно-пузырьковая» (dict 58327342)
VPP_TN_VED_DVID = 971397926            # attr 22232 «ТН ВЭД» → 3920108909 (толщиной более 0,125 мм; dict 124412395)

FILM_PROFILE = {
    "attr_constants": {
        # Бренд — ОБЯЗАТЕЛЬНЫЙ, ПО ЗНАЧЕНИЮ: 'ExpressGo' в ПУБЛИЧНОМ словаре брендов категории ОТСУТСТВУЕТ
        # (101 576 значений просканировано 08.09) → dictionary_value_id НЕ выдумываем (закон Z5, как на
        # ленте). ExpressGo — приватный бренд продавца, оператор зарегистрировал; Ozon сам сматчит.
        "бренд":          {"id": 85,    "value": HOUSE_BRAND},
        # Вид упаковочной пленки — словарный: «Воздушно-пузырьковая» (это и есть ВПП; отдельной категории нет)
        "вид_пленки":     {"id": 11011, "dictionary_value_id": VPP_VID_DVID, "value": "Воздушно-пузырьковая"},
        # ТН ВЭД — ОБЯЗАТЕЛЬНЫЙ, словарный: 3920108909
        "тн_вэд":         {"id": 22232, "dictionary_value_id": VPP_TN_VED_DVID, "value": "3920108909"},
        # Нужен код маркировки — ОБЯЗАТЕЛЬНЫЙ Boolean: плёнка не маркируется (честный false)
        "код_маркировки": {"id": 23536, "value": "false"},
        # Страна-изготовитель — словарный (dict 1935 → Россия): вся линия RU (честно, из фактов)
        "страна":         {"id": 4389,  "dictionary_value_id": 90295, "value": "Россия"},
    },
    "attr_specs": {
        # Название модели — ОБЯЗАТЕЛЬНОЕ, свободная строка: наш ARB-sku на каждый SKU (анти-склейка)
        "модель":    {"id": 9048, "from": "_model"},
        # Аннотация (4191, свободный текст, живьё 08.09) — НАШЕ описание из фактов, plain-текст без HTML
        "аннотация": {"id": 4191, "from": "_desc"},
        # Числовые спеки категории (свободная форма, живьё 08.09): длина намотки (м), ширина полотна (см),
        # единиц в одном товаре. Значения в _spec кладёт _finalize_prod из фактов донора.
        "длина":     {"id": 6468, "from": "_length_m"},
        "ширина":    {"id": 8416, "from": "_width_cm"},
        "единиц":    {"id": 8962, "from": "_units"},
    },
    "attr_enums": {
        # Материал — словарный (dict 1503): факт донора «полиэтилен» → Полиэтилен 62043
        "материал": {"id": 6383, "values": {"полиэтилен": 62043}},
        # Цвет товара — словарный (dict 1494): факт «прозрачный»/«черный»
        "цвет":     {"id": 10096, "values": {"прозрачный": 61572, "черный": 61574}},
    },
}

CATS = {
    "vpp-plenka": {
        "description_category_id": VPP_DCI,
        "type_id": VPP_TID,
        "keywords": ["упаковочная", "пленка", "воздушно-пузырьковая", "пузырчатая"],
        "profile": FILM_PROFILE,
    },
}

# Пути (env-перекрытие для песочниц тестов)
CYCLE_JOURNAL_GLOB = HERE / "runtime/cycle1/atlas-express-film/*.jsonl"     # журнал линии ЯМ (набор залитого)
PHOTO_JOURNAL_GLOB = HERE / "runtime/photo_god/atlas-express-film/*.jsonl"  # фото-журнал: ARB → публичные URL


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ИСТОЧНИК: зеркало сегодняшнего набора ЯМ
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _latest_jsonl(glob_pattern):
    """Последний по имени файл под glob (паттерн уже с *.jsonl). Обратная сортировка → свежий день."""
    import glob as _glob
    files = sorted(_glob.glob(str(glob_pattern)), reverse=True)
    return files[0] if files else None


def poured_pids(journal=None):
    """Набор pids, залитых сегодня на ЯМ (из журнала ЦИКЛ-1, последний ЖИВОЙ скан ДОНОРА).

    Схема журнала (проверено 2026-09-08): НАБОР pids несут ТОЛЬКО события ДОНОР с dry:false —
    evidence.pids (33 шт, стабилен по всем живым прогонам дня). События ЗАЛИВ/ВИТРИНА pids не несут
    (у СВЕРКА evidence — ARB-sku → placement). Берём pids последнего ЖИВОГО ДОНОРА — это и есть
    «что реально пошло на витрину ЯМ». Пусто при пустом/нечитаемом журнале (честный [], не фантом).
    """
    if journal is None:
        p = _latest_jsonl(CYCLE_JOURNAL_GLOB)
        if p is None:
            return []
        journal = str(p)
    try:
        pids, found = [], False
        for line in Path(journal).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("node") != "ДОНОР" or ev.get("dry") is not False:
                continue
            p = (ev.get("evidence") or {}).get("pids") or []
            if p:
                pids, found = list(p), True   # последний живой ДОНОР побеждает
        return list(pids) if found else []
    except Exception:
        return []


def photo_urls_by_sku(journal=None):
    """Фото-журнал (ARB → публичные URL). {sku: [url,...]} последнего состояния на SKU. Пусто → {}."""
    if journal is None:
        p = _latest_jsonl(PHOTO_JOURNAL_GLOB)
        if p is None:
            return {}
        journal = str(p)
    out = {}
    try:
        for line in Path(journal).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            sku = str(e.get("offer_id") or "").strip()
            if not sku:
                continue
            pics = [u for u in (e.get("pictures_current") or []) if str(u).startswith("http")]
            if pics:
                out[sku] = pics   # последняя запись по SKU в хронологии файла = актуальное состояние
    except Exception:
        return {}
    return out


def load_donor_rows(limit=None):
    """Живой скан донора (0₽ GET, тот же, что у ЯМ) → строки зеркала. Fail-soft → честный [] + _error.

    env FILM_DONOR_PATH → читать строки из JSON (песочницы тестов, без сети). Строка вне env — та же
    схема, что у assemble_new_rows: pid/sku, name, article, cost, length/width/height/weight, _stock.
    """
    fx_env = (__import__("os").environ.get("FILM_DONOR_PATH") or "").strip()
    fx = Path(fx_env).expanduser() if fx_env else None
    if fx is not None:
        try:
            rows = json.loads(fx.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                rows = []
        except Exception as e:
            return {"ok": False, "rows": [], "_error": f"{type(e).__name__}: {e}", "path": str(fx)}
        if limit is not None:
            rows = rows[:limit]
        return {"ok": True, "rows": [r for r in rows if isinstance(r, dict)], "path": str(fx)}
    try:
        from ymarket_film_batch_v1 import assemble_new_rows
        rows, _og = assemble_new_rows()
    except Exception as e:
        return {"ok": False, "rows": [], "_error": f"{type(e).__name__}: {e}"}
    if limit is not None:
        rows = rows[:limit]
    return {"ok": True, "rows": rows, "path": "live:shop.cargo-avto.ru (assemble_new_rows)"}


def _donor_is_fixture():
    """True — донор читается из FILM_DONOR_PATH (песочница теста/контролируемая фикстура), не с живого."""
    return bool((os.environ.get("FILM_DONOR_PATH") or "").strip())


def scan_donor_complete(wanted, retries=3, delay=25):
    """Живой скан донора → догнать ПОЛНЫЙ набор wanted-pids ретраями (0₽ GET, тот же скан ЯМ-линии).

    Скан донора ТРАНЗИЕНТНО ЧАСТИЧЕН (наблюдено 2026-09-08: 1 из 3 живых прогонов вернул 15 из 33 —
    assemble_new_rows гейта «сколько должно быть» не несёт). Для зеркального залива частичный скан =
    молчаливая недо-заливка (карточки у части набора), а богатая карточка требует FILM_FACTS из памяти
    ТОГО ЖЕ процесса. Поэтому живьём ретраим скан, копим строки по pid (свежий скан перезаписывает),
    пока не закроем все wanted; FILM_FACTS наполняется каждым сканом в памяти — богатая карточка цела.

    Возвращает (rows, missing): rows в порядке первого появления; missing — недобранные pid (пусто =
    набор полный, можно лить).
    """
    seen = {}
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(delay)
        try:
            got = load_donor_rows().get("rows") or []
        except Exception:
            got = []
        for r in got:
            pid = _sku_of(r)
            if pid in wanted:
                seen[pid] = r                     # последний скан актуальнее по строке
        if set(seen) >= wanted:
            break
    missing = sorted(wanted - set(seen))
    return list(seen.values()), missing


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  СБОРКА КАРТОЧКИ (донор-строка → build_product (реюз ЯМ) → to_item (Ozon))
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _sku_of(row):
    return str(row.get("pid") or row.get("sku") or row.get("article") or "").strip()


def _num(v):
    """Число-не-bool → float. None/не-число/не-конечное (nan/inf)/bool → None (не выдумываем)."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return f if math.isfinite(f) else None


def _annotation_plain(html, house_brand=None):
    """НАШЕ описание-HTML из фактов (карточка ЯМ) → plain-текст атрибута 4191 «Аннотация».

    Бренд линии ЯМ 'ATLAS EDGE' в тексте → HOUSE_BRAND ('ExpressGo'): аннотация не должна светить
    маркой, которой нет в каталоге Ozon. <p>/<li>/<ul> → строки; теги сняты. Пусто/не-строка → ''.
    """
    if not isinstance(html, str) or not html.strip():
        return ""
    t = html
    if house_brand:
        t = t.replace("ATLAS EDGE", house_brand)
    t = re.sub(r"(?i)</(li|p|ul|ol|h[1-6])>", "\n", t)
    t = re.sub(r"(?i)<li[^>]*>", "• ", t)
    t = re.sub(r"(?i)</?(b|strong|i|em|u)>", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in t.split("\n")]
    text = "\n".join(x for x in lines if x).strip()
    return text[:MAX_ANNOTATION] if len(text) > MAX_ANNOTATION else text


def _finalize_prod(prod, photos=None, pid=None, house_brand=HOUSE_BRAND):
    """Обогащение prod ПЕРЕД to_item по директивам оператора 08.09 (SKU/две цены/полная карточка).

    • offer_id = АРТИКУЛ донора: SKU на Ozon = РЕАЛЬНЫЙ товар на сайте донора (при заказе система
      сразу находит товар, который взяли). ARB-sku остаётся в prod['sku'] (ключ фото/журнала) и в
      'Название модели' (9048, анти-склейка карточек).
    • old_price = цена продажи + OLD_PRICE_STEP (зачёркнутая цена, «скидка ~500₽»).
    • Аннотация (4191) = НАШЕ описание из фактов → plain-текст; бренд ATLAS EDGE → HOUSE_BRAND.
    • Длина(6468, м)/Ширина(8416, см)/Единиц(8962) из фактов _spec (ширина м → см ×100).
    """
    art = str(prod.get("article") or "").strip()
    if art:
        prod["offer_id"] = art                    # SKU на Ozon = товар донора (не выдумываем свой)
    price = _num(prod.get("price"))
    if price is not None and price > 0:
        prod["old_price"] = int(round(price)) + OLD_PRICE_STEP   # две цены: цена + зачёркнутая
    _spec = dict(prod["_spec"]) if isinstance(prod.get("_spec"), dict) else {}
    _spec["_model"] = str(prod.get("sku") or art or "")          # Название модели = ARB (анти-склейка)
    desc = _annotation_plain(prod.get("description"), house_brand=house_brand)
    if desc:
        _spec["_desc"] = desc                     # 4191 Аннотация (если карточка богатая — факты есть)
    lm = _num(_spec.get("длина_м")); wm = _num(_spec.get("ширина_м"))
    if lm is not None and wm is not None:
        _spec["_length_m"] = lm                   # «Длина, м» = длина намотки рулона (из фактов)
        _spec["_width_cm"] = int(round(wm * 100)) # «Ширина, см» = ширина полотна (м → см)
    _spec["_units"] = 1                           # «Единиц в одном товаре» — продаём 1 рулон (честно)
    prod["_spec"] = _spec
    if isinstance(photos, dict):
        pics = photos.get(prod.get("sku"), []) or photos.get(pid or "", [])
        if pics:
            prod["pictures"] = pics               # публичные URL рабочего кадра (Ozon тянет сам)
    return prod


def build_cards(rows, photos=None, cats=None, house_brand=HOUSE_BRAND, unique_name=False):
    """Строки донора → карточки Ozon {'row','prod','item','meta'}. item=None — честный блок (OZ2).

    prod — ЧЕРЕЗ build_product ЯМ-линии (реюз): фирменное имя/описание/_spec из фактов, та же цена
    (закупка×markup 8.0). _finalize_prod доводит до Озона: offer_id=артикул донора, две цены, полная
    карточка (аннотация/страна/длина/ширина/единиц). photos: {sku:[url]} перекрывают публикации донора.
    """
    cats = cats if cats is not None else CATS
    from ymarket_film_cards_v1 import build_product
    photos = photos if photos is not None else {}
    out = []
    for i, row in enumerate(rows):
        pid = _sku_of(row)
        prod = build_product(row, {}, i)          # pub_urls={} → сам prod несёт sku/имя/цену/спеки
        if prod is None:
            continue                              # битая строка донора (нет article/имени/закупки) — пропуск
        _finalize_prod(prod, photos=photos, pid=pid, house_brand=house_brand)
        r = card.to_item(prod, cats=cats, unique_name=unique_name, house_brand=house_brand)
        out.append({"row": row, "prod": prod, "item": r["item"], "meta": r["meta"]})
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  МАТРИЦА-БИБЛИОТЕКА ЗАЛИТОГО (директива оператора: SKU = реальный товар донора, связка для заказа)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def pour_library_path():
    """Путь матрицы-библиотеки залитого. env OZON_FILM_LIBRARY_PATH → иначе runtime/ozon-film/."""
    env = (os.environ.get("OZON_FILM_LIBRARY_PATH") or "").strip()
    return Path(env).expanduser() if env else (HERE / "runtime/ozon-film/pour-library.json")


def read_pour_library(path=None):
    """Матрица-библиотека → {offer_id: запись}. Файла нет/битый → {} (отсутствие артефакта ≠ «0»)."""
    p = Path(path) if path else pour_library_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _today():
    return datetime.date.today().isoformat()


def _write_pour_library(lib, path=None):
    """Атомарная запись матрицы-библиотеки (tmp+replace). True/False — без вранья о количестве."""
    p = Path(path) if path else pour_library_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(lib, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception:
        return False


def record_pour(built, imported, path=None, shelf=None):
    """После ЖИВОГО залива записать матрицу залитого (идемпотентно по offer_id). 0₽/0 сети.

    Каждая запись — связка offer_id(=артикул донора на Ozon) ↔ реальный товар донора: donor_url,
    имя, закупка, цена, габариты, ARB-sku, pid, product_id. «при заказе системе проще сразу найти
    товар который мы взяли в обсос». Пустой imported → НЕ пишем (залив результата не дал — честно).
    shelf: {offer_id: «Продаётся»/…} от сверки витрины → кладётся в поле shelf записи (статус цикл-1).
    """
    imp = {str(i.get("offer_id")): i for i in (imported or [])}
    if not imp:
        return {"ok": False, "written": 0, "_error": "нет импортированных — записывать нечего"}
    lib = read_pour_library(path)
    p = Path(path) if path else pour_library_path()
    written = 0
    for b in built:
        m = b.get("meta") or {}
        if m.get("can_build") is not True:
            continue
        oid = str(m.get("offer_id") or "").strip()
        it = imp.get(oid)
        if not it:
            continue
        prod = b.get("prod") or {}
        row = b.get("row") or {}
        art = str(prod.get("article") or oid).strip()
        pid = str(prod.get("pid") or row.get("pid") or row.get("sku") or "").strip()
        lib[oid] = {
            "offer_id": oid,                       # SKU на Ozon = артикул донора (реальный товар)
            "article": art,
            "donor_url": f"{DONOR_BASE}{art}/" if art else None,
            "name": str(row.get("name") or prod.get("name") or "").strip()[:180],
            "cost": prod.get("cost"),
            "price": prod.get("price"),
            "old_price": prod.get("old_price"),
            "arb_sku": prod.get("sku"),
            "pid": pid,
            "dims_mm": _mm_dims(prod),
            "product_id": it.get("product_id"),
            "status": str(it.get("status")),
            "shelf": (shelf or {}).get(oid),       # цикл-1: «Продаётся»/«на модерации»/… (или None)
            "recorded": _today(),
        }
        written += 1
    if not written:
        return {"ok": False, "written": 0, "_error": "ни один offer_id не совпал с импортированными"}
    if not _write_pour_library(lib, path):
        return {"ok": False, "written": written, "_error": f"не записать {p}"}
    return {"ok": True, "written": written, "total": len(lib), "path": str(p)}


def pour_mark_shelf(report, path=None):
    """Проставить поле shelf по сверке витрины (записи offer_id → «Продаётся»/…). Только при изменениях."""
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
    if not _write_pour_library(lib, path):
        return {"ok": False, "updated": updated, "_error": "не записать библиотеку"}
    return {"ok": True, "updated": updated, "total": len(lib)}


def _mm_dims(prod):
    """Габариты prod (weightDimensions, см/кг) → строковый след для матрицы. Нет → None (не выдумываем)."""
    wd = prod.get("weightDimensions") if isinstance(prod, dict) else None
    if not isinstance(wd, dict):
        return None
    try:
        length = float(wd.get("length")); width = float(wd.get("width"))
        height = float(wd.get("height")); weight = float(wd.get("weight"))
    except (TypeError, ValueError):
        return None
    if not all(x > 0 for x in (length, width, height, weight)):
        return None
    return f"{int(round(length*10))}×{int(round(width*10))}×{int(round(height*10))}мм {int(round(weight*1000))}г"


def render_library(lib):
    """Человеко-отчёт матрицы-библиотеки (read, 0₽): связка SKU↔товар донора + статус витрины."""
    lines = [f"МАТРИЦА-БИБЛИОТЕКА залитого · записей {len(lib)}"]
    on_sale = 0
    for oid in sorted(lib):
        r = lib[oid]
        sh = r.get("shelf") or r.get("status")
        if r.get("shelf") == "Продаётся":
            on_sale += 1
        lines.append(f"  • offer_id={oid} · product_id={r.get('product_id')} · "
                     f"{r.get('donor_url') or '—'} · {(r.get('name') or '')[:48]} · "
                     f"закупка {r.get('cost')} · цена {r.get('price')}₽ · ARB {r.get('arb_sku')} · "
                     f"статус={sh}")
    if lib:
        lines.append(f"  ·· на витрине «Продаётся»: {on_sale}/{len(lib)}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ВИТРИНА: СТАТУС «ПРОДАЁТСЯ» (цикл-1 ОЗОН — суть оператора: залил → статус Продаётся → след. категория)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def shelf_status_of(card):
    """read_shelf-карточка → статус витрины (честный классификатор, зеркало PASS-гейта ЯМ цикл-1).

    «Статус каждого товара должен быть - Продается - затем другую категорию берем» (оператор 08.09).
    На витрине (Ozon /v3 product/info/list) = visible True. Иначе разводим ЧЕСТНО:
    на модерации (одобрение не пришло) / одобрена-но-скрыта / ошибки карточки / не найдена.
    НИКОГДА не называем «Продаётся» без живого visible=True (это был бы фантом-успех).
    """
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
    """Живая сверка витрины (0₽ GET, read): каждый импортированный offer → статус «Продаётся»/иное.

    Суть цикл-1 ОЗОН: залил → СВЕРЬ статус «Продаётся» у каждого → потом следующая категория.
    Читаем витрину /v3/product/info/list через W.read_shelf по offer_id. Импортированных без
    product_id на витрину не шлём (нечего сверять — честно «нет product_id»). Fail-soft: сбой
    сети/ключа → ok=False + причина, отчёт по тому, что прочитано (не выдаём всё за «Продаётся»).
    """
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
    """Человеко-отчёт сверки витрины: по offer_id статус + сколько уже «Продаётся»."""
    lines = [f"ВИТРИНА (цикл-1) · сверено {len(report)}"]
    on_sale = 0
    for oid in sorted(report):
        st = report[oid]
        if st == "Продаётся":
            on_sale += 1
        lines.append(f"  {('🟢' if st == 'Продаётся' else '🔴')} {oid} · {st}")
    lines.append(f"  ·· «Продаётся»: {on_sale}/{len(report)}")
    return "\n".join(lines)


def items_of(built):
    """Готовые item (не None) — что реально полетит в /v3/product/import."""
    return [b["item"] for b in built if b["item"] is not None]


def _in_stock(row):
    """«В наличии» донора честно: только in_stock. Всё прочее — НЕ наличие."""
    st = row.get("_stock") or row.get("stock")
    if isinstance(st, dict):
        st = st.get("in_stock")
    return st is True or str(st).strip() == "in_stock"


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ОТЧЁТЫ
# ══════════════════════════════════════════════════════════════════════════════════════════════

def render_build(built):
    """Человеко-отчёт сборки карточек зеркала. Ничего не пишет наружу (0₽)."""
    n = len(built)
    ok = [b for b in built if b["item"] is not None]
    blocked = [b for b in built if b["item"] is None]
    lines = [f"КАРТОЧКИ (зеркало ЯМ) · всего {n} · готово {len(ok)} · блок(OZ2) {len(blocked)}"]
    for b in ok:
        m = b["meta"]
        lines.append(
            f"  🟢 {m['offer_id']} · {m['price']}₽ · dci={m['description_category_id']} "
            f"type={m['type_id']} · фото={'есть' if not m['missing_images'] else 'НЕТ'} · "
            f"габариты={'есть' if not m['missing_dimensions'] else 'нет'} · EAN={'есть' if m['has_barcode'] else 'нет'} · "
            f"аттр={m['attrs_built']} · имя '{b['item'].get('name', '')[:52]}'")
    for b in blocked:
        m = b["meta"]
        lines.append(f"  🔴 {m['offer_id']} · блок: {m.get('block_reason')}")
    return "\n".join(lines)


def render_fill_report(imported, failures, dry):
    lines = [f"ЗАЛИВ · {'СУХО (payload собран, 0₽)' if dry else 'ЖИВОЙ'}"
             f" · импортировано {len(imported)} · ошибок {len(failures)}"]
    for it in imported:
        lines.append(f"  ✅ {it.get('offer_id')} → product_id={it.get('product_id')}")
    for f in failures:
        lines.append(f"  ❌ {f.get('offer_id')} · status={f.get('status')} · errors={f.get('errors')}")
    return "\n".join(lines)


def render_stocks(stocks, warehouse_id, dry):
    n = len(stocks)
    return (f"ОСТАТКИ · {'СУХО (payload собран, 0₽)' if dry else 'ЖИВОЙ'} · склад {warehouse_id} · SKU {n}\n"
            + "\n".join(f"  {s.get('offer_id') or s.get('sku')} → {s.get('stock')}" for s in stocks))


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ФАЗЫ ЦИКЛА (зеркало ozon_zaliv_v1)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def first_warehouse_id():
    """Первый склад кабинета — ЕДИНСТВЕННЫЙ законный источник warehouse_id (не выдумываем)."""
    try:
        whs = W.warehouse_list(timeout=20).get("warehouses", [])
    except Exception:
        return None, None
    for wh in whs:
        wid = wh.get("warehouse_id")
        if wid is not None:
            return wid, wh.get("name")
    return None, None


def fill(built, dry=True, commit=False, poll_attempts=24, poll_delay=8):
    """Фаза FILL: собрать item → /v3/product/import → опрос import_info. Зеркало ozon_zaliv.fill."""
    items = items_of(built)
    if not items:
        print("ЗАЛИВ · блок: нет готовых карточек (всё блок)")
        return {"ok": False, "imported": [], "failures": [], "_error": "нет готовых карточек"}
    res = W.create_product(items, dry=dry, commit=commit)
    if dry:
        print(render_fill_report([], [], dry=True))
        return {"ok": True, "dry": True, "items_ready": len(items)}
    if res.get("status") != "sent":
        print(render_fill_report([], [{"offer_id": "?", "status": "transport",
                                       "errors": [str(res.get("_error"))]}], dry=False))
        return {"ok": False, "imported": [], "failures": [], "_error": res.get("_error")}
    resp = res.get("response") or {}
    task_id = (resp.get("result") or {}).get("task_id") or resp.get("task_id")
    if task_id is None:
        msg = "task_id не получен — карточка НЕ создана (не выдаём желаемое за факт)"
        print(render_fill_report([], [{"offer_id": "?", "status": "no-task-id", "errors": [msg]}], dry=False))
        return {"ok": False, "imported": [], "failures": [], "_error": msg}
    items_info = []
    for _ in range(poll_attempts):
        items_info = W.import_info(task_id)
        if not items_info:
            time.sleep(poll_delay)
            continue
        if all(str(i.get("status")) != "pending" for i in items_info):
            break
        time.sleep(poll_delay)
    imported, failures = [], []
    for it in items_info:
        status = str(it.get("status"))
        pid = it.get("product_id") or 0
        errs = [str(e) for e in (it.get("errors") or [])]
        if status == "imported" and pid and not errs:
            imported.append(it)
        else:
            failures.append({"offer_id": it.get("offer_id"), "status": status,
                             "errors": errs, "product_id": pid})
    if not items_info:
        msg = f"import_info пуст за {poll_attempts} попыток — результат НЕ известен (честно)"
        print(msg)
        return {"ok": False, "imported": [], "failures": [], "_error": msg}
    print(render_fill_report(imported, failures, dry=False))
    return {"ok": not failures, "imported": imported, "failures": failures, "task_id": task_id}


def stocks(cards, count=None, dry=True, commit=False):
    """Фаза STOCKS: остатки «В наличии» донора на склад. count обязателен (не выдумываем остаток)."""
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
        print("ОСТАТКИ · блок: склад не создан — складов в кабинете 0 (создать в seller.ozon.ru). "
              "warehouse_id не выдумываем.")
        return {"ok": False, "_error": "склад не создан"}
    payload = [{"offer_id": c["meta"]["offer_id"], "warehouse_id": wid, "stock": cnt}
               for c in cards if _in_stock(c["row"])]
    if not payload:
        print("ОСТАТКИ · блок: среди карточек нет позиций «В наличии» донора — остаток ставить не на что")
        return {"ok": False, "_error": "нет позиций в наличии"}
    res = W.set_stock(payload, dry=dry, commit=commit)
    print(render_stocks(payload, wid, dry=dry))
    if dry:
        return {"ok": True, "dry": True, "payload": payload}
    if res.get("status") != "sent":
        print(f"  transport: {res.get('_error')}")
        return {"ok": False, "_error": res.get("_error")}
    return {"ok": True, "response": res.get("response")}


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════════════════════

def main(argv=None):
    ap = argparse.ArgumentParser(description="OZON FILM ZALIV V1 — залив плёнки (зеркало ЯМ, dry по умолчанию)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--poured", action="store_true", help="сегодняшний набор pids линии ЯМ (0₽)")
    g.add_argument("--build", action="store_true", help="сухая сборка карточек зеркала (0₽ к Ozon)")
    g.add_argument("--warehouse", action="store_true", help="печать warehouse_id первого склада")
    g.add_argument("--fill", action="store_true", help="залив карточек (dry; --commit — живой)")
    g.add_argument("--stocks", action="store_true", help="остатки (dry; --commit — живой)")
    g.add_argument("--library", action="store_true", help="печать матрицы-библиотеки залитого (read, 0₽)")
    g.add_argument("--lookup", default=None, metavar="OFFER",
                   help="одна запись матрицы-библиотеки по offer_id (read, 0₽)")
    g.add_argument("--verify", action="store_true",
                   help="сверка витрины по матрице: статус каждого «Продаётся»? (0₽ GET)")
    ap.add_argument("--commit", action="store_true", help="ЖИВОЙ режим (РУБИКОН: слово оператора)")
    ap.add_argument("--count", type=int, default=None, help="остаток на каждый SKU (не выдумываем)")
    ap.add_argument("--only-poured", action="store_true", help="ограничить строки только залитым набором ЯМ")
    ap.add_argument("--limit", type=int, default=None, help="ограничить число карточек (для проверки)")
    args = ap.parse_args(argv)

    if args.library:
        lib = read_pour_library()
        print(render_library(lib))
        return 0 if lib else 1

    if args.lookup:
        oid = str(args.lookup).strip()
        lib = read_pour_library()
        r = lib.get(oid)
        if r is None:
            print(f"МАТРИЦА · {oid} НЕ найдена (записи: {len(lib)})")
            return 1
        print(f"МАТРИЦА · {oid}")
        for k, v in r.items():
            print(f"  {k}: {v}")
        return 0

    if args.verify:
        # Цикл-1 ОЗОН: каждый залитый товар должен быть НА ВИТРИНЕ («Продаётся») — только тогда
        # берём следующую категорию. Сверяем по матрице-библиотеке (что реально импортировано).
        lib = read_pour_library()
        if not lib:
            print("ВИТРИНА · матрица пуста — сверять нечего (сначала --fill --commit)")
            return 1
        imported = [{"offer_id": oid, "product_id": r.get("product_id") or 0}
                    for oid, r in lib.items()]
        res = verify_shelf(imported)
        if res.get("report"):
            print(render_shelf_report(res["report"]))
            pm = pour_mark_shelf(res["report"])
            if pm.get("ok"):
                print(f"  ·· матрица: обновлено полей shelf={pm.get('updated')}")
        if not res.get("ok"):
            print(f"ВИТРИНА · сверка недоступна: {res.get('_error')}")
            return 1
        return 0 if all(v == "Продаётся" for v in res["report"].values()) else 1

    if args.poured:
        pids = poured_pids()
        print(f"ЗАЛИТО НА ЯМ · pids {len(pids)}")
        if pids:
            print(" ".join(pids))
        else:
            print("  (журнал пуст/не читается — набора нет; это не «ноль», а отсутствие артефакта)")
        return 0 if pids else 1

    if args.warehouse:
        wid, name = first_warehouse_id()
        if wid is None:
            print("склад НЕ создан (в кабинете 0 складов) — создайте в seller.ozon.ru → Логистика")
            return 1
        print(f"warehouse_id={wid} name={name}")
        return 0

    src = load_donor_rows()
    if not src["ok"]:
        print(f"ДОНОР ERR: {src['_error']}")
        return 1
    rows = src["rows"]
    pour_wanted = set()
    if args.only_poured:
        pour_wanted = set(poured_pids())
        if pour_wanted:
            rows = [r for r in rows if _sku_of(r) in pour_wanted]
    # ГЕЙТ ПОЛНОТЫ (залив/остатки зеркального набора): живой скан донора транзиентно частичен
    # (15/33), а недо-скан при --commit = молчаливая недо-заливка части набора. Живьём (не фикстура)
    # догоняем полный набор ретраями scan_donor_complete (0₽ GET); не догнали → АБОРТ, НИ ОДНОГО
    # write. Карточки богатые (FILM_FACTS) живут в памяти ЭТОГО процесса скана → гейт здесь, а не
    # снапшотом.
    if (args.fill or args.stocks) and pour_wanted and not _donor_is_fixture():
        got_pids = {_sku_of(r) for r in rows}
        if got_pids < pour_wanted:
            rows, missing = scan_donor_complete(pour_wanted)
            if missing:
                got_pids = {_sku_of(r) for r in rows}
                print(f"ГЕЙТ ПОЛНОТЫ · скан донора дал {len(got_pids)}/{len(pour_wanted)} "
                      f"(недостаёт {len(missing)}) — АБОРТ, никаких write. Скан транзиентен — повторите.")
                print("  недостающие pids: " + " ".join(missing[:25])
                      + (" …" if len(missing) > 25 else ""))
                return 1
    if args.limit is not None:
        rows = rows[:args.limit]
    photos = photo_urls_by_sku()
    built = build_cards(rows, photos=photos)

    if args.build:
        print(render_build(built))
        return 0

    if args.fill:
        if not items_of(built):
            print("ЗАЛИВ · нет готовых карточек — блок")
            return 1
        print(render_build(built))
        res = fill(built, dry=not args.commit, commit=args.commit)
        # ЖИВОЙ залив дал результат → пишем МАТРИЦУ-БИБЛИОТЕКУ (SKU=реальный товар донора). Рекорд ТОЛЬКО
        # при реальных imported (product_id>0): пусто/ошибки → честно ничего не записываем.
        if args.commit and res.get("imported"):
            rec = record_pour(built, res["imported"])
            if rec.get("ok"):
                print(render_library(read_pour_library()))
            else:
                print(f"МАТРИЦА · не записана: {rec.get('_error')}")
            # ЦИКЛ-1: сверяем витрину — статус каждого «Продаётся»? (0₽ GET). Сбой сверки НЕ роняет
            # залив: отчёт печатаем, статус остаётся честно без shelf (проверят позже --verify).
            v = verify_shelf(res["imported"])
            if v.get("report"):
                print(render_shelf_report(v["report"]))
                pour_mark_shelf(v["report"])
            elif not v.get("ok"):
                print(f"ВИТРИНА · сверка недоступна: {v.get('_error')}")
        return 0 if (res.get("ok") or res.get("dry")) else 1

    if args.stocks:
        if not items_of(built):
            print("ОСТАТКИ · нет готовых карточек — блок")
            return 1
        res = stocks(built, count=args.count, dry=not args.commit, commit=args.commit)
        return 0 if (res.get("ok") or res.get("dry")) else 1

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

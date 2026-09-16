#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""КОРОБКИ КАРТОННЫЕ — инвентарь (ozon_boxes_inventory_v1) — READ-ONLY список НАИМЕНОВАНИЕ↔фото.

Зачем. Оператор: «важны данные, чтобы карточка просто прошла — удочка наша: наименование — цена —
ссылки фото — описание/ОВХ/характеристики. Составляешь исчерпывающий список товаров, связка
НАИМЕНОВАНИЕ ↔ ссылки на фото. Смотрим, сколько категорий готовы для перелива на Ozon. Возьмём
коробки картонные. Всё что есть.» (plan resilient-gathering-bonbon, решение оператора 2026-09-08:
универсум = ИП-шаблоны ∪ донор; фото-база = переиспользовать cdn1.ozone из ИП-файлов, т.к. медиа ЕГО).

Что это. Сканирует локальные Ozon-шаблоны коробок (лист «Шаблон», данные с PRODUCTS_FIRST_DATA_ROW_INDEX,
обычно row 5) + донный мастер cargo_master_products.json (17 коробок). Строит дедуплицированный реестр:
артикул, НАИМЕНОВАНИЕ, цена, фото-URL(главное+доп), ОВХ-упаковки, бренд, Тип, штрихкод, description_category_id
из configs, файл-источник, готовность. Дубли между датированными ре-экспортами схлопывает (артикул →
фото-id → нормализованное имя+цена). Не-коробки (плёнка/скотч/прочее внутри батчей) НЕ теряем — считаем.
Фото-классификация по решению оператора: cdn1.ozone = СВОЁ медиа (валидно), wbbasket/disk.yandex/cargo =
чужие/не-медиа-Ozon (в карточку не пойдёт без отдельного решения).

Железно: read-only (0₽, без сети, без ключей), НИЧЕГО наружу не пишет. Результат — канон-артефакт на диск
(runtime/ozon_boxes/ozon_korobki_base_<дата>.{json,md}) — принцип «созданное → артефакт». Категорию/Тип для
живого залива подтверждает ОРГАН (ozon_category_scout, шаг 3) — тут не выдумываем, а только фиксируем то,
что уже лежит в configs/Тип-колонке.

Интерпретатор: /usr/bin/python3 (openpyxl). У домашнего python3.14 битый expat — не использовать.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.stderr.write("нет openpyxl — запусти /usr/bin/python3 (у домашнего python битый expat)\n")
    raise

HERE = Path(__file__).resolve().parent
RUNTIME_DIR = HERE / "runtime" / "ozon_boxes"
WIP_ROOT = Path.home() / "Downloads" / "ready" / "WIP"

# ── имя файла-донора: ищем коробки в мастер-json (Артикул 96XXXXX) ─────────────
DONOR_MASTER_GLOB = "parsers/parsed_data/CARGO_COLLECTION_*/cargo_master_products.json"

# Ozon-шаблон: колонка «Тип*» (type-значение), не «Тип картона»/прочее
_TYPE_EXACT = {"тип", "тип*"}

# Фото-хост → класс медиа (решение оператора: только ozone = СВОЁ)
_MEDIA_KIND = (
    (re.compile(r"cdn1\.ozone\.ru|ozone\.ru"), "ozone"),
    (re.compile(r"wbbasket\.ru|wb\.ru"), "wb"),
    (re.compile(r"yandex\.com|disk\.yandex|yadi\.sk"), "yd"),
    (re.compile(r"cargo-avto|shop\.cargo|sp\.cargo"), "cargo"),
)

# Имя файла коробочного шаблона (фильтр обнаружения)
_NAME_HINT = re.compile(r"оробк|короб|box|alien", re.I)

# Разделители между несколькими фото-URL в ячейке (Ozon в доп.фото пишет ссылки в одну ячейку)
_URL_SPLIT = re.compile(r"[;\s]+")

# ── «картонная коробка»: держим если в имени короб/коробк/кофр/пуф (и т.п.) ────
_KEEP_BOX = re.compile(r"короб|кофр|пуф", re.I)
# НО если ДО короба стоит явное не-коробочное «назначение-товара» (лента/скотч/плёнка/наполнитель,
# «…для коробок») — это не коробка. Напр. «Клейкая лента (скотч)… для заклейки коробок».
_NON_BOX_HEAD = re.compile(r"лент|скотч|наполн|плёнк|пленк|стрейч", re.I)
# Донные коробки лежат ровно в этих категориях дона (рекон 2026-09-08: 13 + 4 = 17)
DONOR_BOX_CATS = {"Упаковка для маркетплейсов", "Кондитерская упаковка"}


def _is_box(name):
    m = _KEEP_BOX.search(name)
    if not m:
        return False
    h = _NON_BOX_HEAD.search(name)
    return not (h and h.start() < m.start())

# ── линии (группировка товарных семейств, best-effort по именам — NOT Ozon-категория) ──
_LINES = (
    (re.compile(r"пуф", re.I), "пуф-игрушки"),
    (re.compile(r"кондитер|для торта|пирожн", re.I), "кондитерские"),
    (re.compile(r"\bа4\b|\bа3\b|архив|документ|для бумаг|для папок|бизнес", re.I), "архив-А4/документы"),
    (re.compile(r"маркетплейс|посылок|посылоч|для отправки", re.I), "малая-упаковочная-МП"),
    (re.compile(r"самосбор", re.I), "самосборные"),
    (re.compile(r"переезд", re.I), "переезд"),
    (re.compile(r"хранени|для вещей|для одежд|гардероб|вещей|игрушек", re.I), "хранение/вещи"),
    (re.compile(r"мебел|объемн|объёмн|вместит|классич|премиум|усиленн|с ручками|600\s*[×xх*]\s*400|700\s*[×xх*]\s*500", re.I), "гофрокороба-крупные"),
    (re.compile(r".*"), "короб-прочее"),
)


def _photo_kind(url):
    for rx, kind in _MEDIA_KIND:
        if rx.search(url):
            return kind
    return "other"


def _split_urls(cell):
    if not cell:
        return []
    return [t for t in _URL_SPLIT.split(str(cell)) if t.startswith(("http://", "https://"))]


def _num(cell):
    """Число из ячейки: '1 520' / '1.5' / '1520' / None."""
    if cell is None:
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    s = str(cell).strip().replace("\xa0", " ").replace(" ", "").replace(",", ".").replace("₽", "")
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s in (".", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _norm_art(a):
    if a is None:
        return ""
    return re.sub(r"\s+", " ", str(a).strip()).lower()


def _norm_name(n):
    if n is None:
        return ""
    return re.sub(r"\s+", " ", str(n).strip()).lower()


def classify_line(name):
    n = name or ""
    for rx, line in _LINES:
        if rx.search(n):
            return line
    return "короб-прочее"


# ── Чтение configs-листа Ozon-шаблона ───────────────────────────────────────────
def _read_configs(wb):
    out = {}
    for ws in wb.worksheets:
        if str(ws.title).lower() == "configs":
            for row in ws.iter_rows():
                if row and row[0].value is not None and len(row) > 1 and row[1].value is not None:
                    k = str(row[0].value).strip()
                    if k in ("DESCRIPTION_CATEGORY_ID", "SUB_CATEGORY_IDS",
                             "PRODUCTS_TITLE_ROW_INDEX", "PRODUCTS_FIRST_DATA_ROW_INDEX",
                             "LANGUAGE", "CURRENCY"):
                        out[k] = str(row[1].value).strip()
            break
    return out


# ── Карта колонок Оzon-шаблона по заголовкам ────────────────────────────────────
def _column_map(header_cells):
    """header_cells — список строк (заголовки). Возврат: role → col idx."""
    labels = [(i, str(c.value).strip().lower() if c.value is not None else "") for i, c in enumerate(header_cells)]
    m = {}

    def find(pred):
        hit = [i for i, lab in labels if pred(lab)]
        return hit[0] if hit else None

    m["art"] = find(lambda l: "артикул" in l and "фото" not in l)
    # название товара (не «Название модели»)
    m["name"] = find(lambda l: ("название" in l and "модел" not in l) or l in ("наименование", "наименование (озон)"))
    # цена продажи (не «до скидки», не «поставщика»)
    m["price"] = find(lambda l: "цена" in l and "скидк" not in l and "постав" not in l and "закуп" not in l)
    m["old_price"] = find(lambda l: "цена" in l and "до скидк" in l)
    m["weight_g"] = find(lambda l: "вес" in l and "упаковк" in l)
    m["d_mm"] = find(lambda l: "упаковк" in l and "длин" in l and "мм" in l)
    m["w_mm"] = find(lambda l: "упаковк" in l and "ширин" in l and "мм" in l)
    m["h_mm"] = find(lambda l: "упаковк" in l and "высот" in l and "мм" in l)
    m["photo_main"] = find(lambda l: "главное фото" in l)
    m["photo_extra"] = find(lambda l: "дополнительн" in l and "фото" in l)
    m["brand"] = find(lambda l: "бренд" in l)
    m["type"] = find(lambda l: l in _TYPE_EXACT)
    m["barcode"] = find(lambda l: any(x in l for x in ("трихкод", "баркод", "barcode", "ean")))
    return m


# ── Скан одного Ozon-шаблона ─────────────────────────────────────────────────────
def scan_xlsx(path):
    """Возврат (meta, records). meta — сводка файла; records — строки-товары (артикул обязателен)."""
    rel = str(path.relative_to(WIP_ROOT))
    meta = {"file": rel, "sheet": None, "dci": None, "sub": None, "rows_seen": 0,
            "rows_kept": 0, "dropped_noart": 0, "dropped_nonbox": 0, "media": {}}
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    cfg = _read_configs(wb)
    meta["dci"] = cfg.get("DESCRIPTION_CATEGORY_ID")
    meta["sub"] = cfg.get("SUB_CATEGORY_IDS")
    title_row = int(cfg.get("PRODUCTS_TITLE_ROW_INDEX") or 2)
    data_row = int(cfg.get("PRODUCTS_FIRST_DATA_ROW_INDEX") or (title_row + 3))

    sheet = None
    for ws in wb.worksheets:
        if ws.title == "Шаблон":
            sheet = ws
            break
    if sheet is None:  # фолбэк: первая непустая со структурой Ozon
        for ws in wb.worksheets:
            rows = ws.iter_rows()
            head = next(rows, None)
            if head is None:
                continue
            labs = [str(c.value).strip().lower() if c.value else "" for c in head]
            if any("артикул" in l for l in labs) and any("цена" in l for l in labs):
                sheet = ws
                break
    if sheet is None:
        meta["reason"] = "нет листа Шаблон/структуры Ozon"
        wb.close()
        return meta, []
    meta["sheet"] = sheet.title

    it = sheet.iter_rows()
    # 1) пропустить строки ДО заголовка (заголовок на title_row), 2) взять заголовок отдельно
    for _ in range(max(0, title_row - 1)):
        next(it, None)
    header_cells = next(it, None)
    if header_cells is None:
        meta["reason"] = "нет заголовка"
        wb.close()
        return meta, []
    cm = _column_map(header_cells)
    art_i, name_i, price_i = cm["art"], cm["name"], cm["price"]
    if art_i is None:
        meta["reason"] = "колонка Артикул не найдена"
        wb.close()
        return meta, []
    # 3) пропустить строки-инструкции между заголовком и первой строкой данных (data_row)
    for _ in range(max(0, data_row - title_row - 1)):
        next(it, None)
    recs = []
    for row in it:
        # read-only отдаёт ReadOnlyCell-объекты, а не значения — берём .value
        v = [c.value if c is not None else None for c in row]
        meta["rows_seen"] += 1

        def get(i):
            return v[i] if i is not None and i < len(v) else None

        art = _norm_art(get(art_i))
        # страховка: инструкционные строки (текст вместо артикула), если data_row в файле иной
        if art and (len(art) > 40 or "введите артикул" in art or "обязательное" in art):
            meta["dropped_noart"] += 1
            continue
        if not art:
            meta["dropped_noart"] += 1          # строки-инструкции/пустые артикулы
            continue
        name = (str(get(name_i)).strip() if name_i is not None and get(name_i) is not None else "")
        if not name or name.lower().startswith(("ознакомьтесь", "заполняйте", "инструкция")):
            meta["dropped_noart"] += 1
            continue
        if not _is_box(name):
            meta["dropped_nonbox"] += 1          # внутри «коробочных» батчей лежит не-коробки
            continue
        photos = []
        for i in (cm["photo_main"], cm["photo_extra"]):
            if i is None:
                continue
            photos += _split_urls(get(i))
        # дедуп URL, сохраняя порядок (главное первым)
        seen, uniq = set(), []
        for u in photos:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        kinds = [_photo_kind(u) for u in uniq]
        own_first = next((u for u in uniq if _photo_kind(u) == "ozone"), None)
        # ОВХ упаковки
        ovh = None
        wg, dm, wm, hm = (_num(get(cm["weight_g"])), _num(get(cm["d_mm"])),
                          _num(get(cm["w_mm"])), _num(get(cm["h_mm"])))
        if all(x is not None for x in (wg, dm, wm, hm)) and wg > 0 and dm > 0 and wm > 0 and hm > 0:
            ovh = {"weight_g": int(wg), "d_mm": int(dm), "w_mm": int(wm), "h_mm": int(hm)}
        price = _num(get(cm["price"]))
        kind_count = {}
        for k in kinds:
            kind_count[k] = kind_count.get(k, 0) + 1
            meta["media"][k] = meta["media"].get(k, 0) + 1
        # ТИП-значение (для будущего type_id-маппинга шага 3)
        tval = str(get(cm["type"])).strip() if cm["type"] is not None and get(cm["type"]) is not None else ""
        recs.append({
            "art": art, "name": name, "name_norm": _norm_name(name),
            "price": price, "cost": None,
            "ovh": ovh,
            "photos": uniq, "photo_kind_first": (kinds[0] if kinds else None),
            "own_photo": bool(own_first), "own_main": own_first == (uniq[0] if uniq else None),
            "brand": str(get(cm["brand"])).strip() if cm["brand"] is not None and get(cm["brand"]) is not None else None,
            "type": tval or None,
            "barcode": str(get(cm["barcode"])).strip() if cm["barcode"] is not None and get(cm["barcode"]) is not None else None,
            "source": rel, "dci": meta["dci"],
        })
    meta["rows_kept"] = len(recs)
    wb.close()
    return meta, recs


# ── Донная ветка из мастер-json (17 коробок, наличие у дона) ────────────────────
def _scan_donor_master(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    prods = data if isinstance(data, list) else (data.get("products") or list(data.values())[0])
    recs, meta = [], {"file": str(path), "rows_kept": 0}
    for r in prods:
        name = (r.get("Наименование (Ozon)") or r.get("Наименование") or "")
        cat = (r.get("Категории") or r.get("Категория") or "")
        # коробка дона = категория-коробка И имя-коробка (не лента/наполнитель «…для коробок»)
        if cat not in DONOR_BOX_CATS or not _is_box(name):
            continue
        photo = r.get("Фото без вотермарка") or r.get("Фото (вотермарк, fallback)") or ""
        photos = [u for u in _split_urls(photo) if u.startswith("http")]
        price = _num(r.get("Цена продажи, ₽"))
        w = _num(r.get("Ширина, мм")); d = _num(r.get("Длина, мм")); h = _num(r.get("Высота, мм"))
        kg = _num(r.get("Вес, кг"))
        ovh = None
        if all(x is not None for x in (w, d, h)) and all(x > 0 for x in (w, d, h)):
            ovh = {"weight_g": int(round((kg or 0) * 1000)) if kg else None,
                   "d_mm": int(d), "w_mm": int(w), "h_mm": int(h)}
        recs.append({
            "art": str(r.get("Артикул") or ""), "name": name, "name_norm": _norm_name(name),
            "price": price, "cost": _num(r.get("Закупка SKU, ₽")),
            "stock": (r.get("Наличие (shop)") or "").strip() or None,
            "ovh": ovh, "photos": photos,
            "photo_kind_first": (_photo_kind(photos[0]) if photos else None),
            "own_photo": any(_photo_kind(u) == "ozone" for u in photos),
            "brand": r.get("Торговая марка") or None,
            "line_src": r.get("Категории") or None,
            "source": "donor-master", "dci": None,
            "donor_url": r.get("Ссылка") or None,
        })
    meta["rows_kept"] = len(recs)
    return meta, recs


# ── Дедуп: артикул → (media-предпочтение) → нормализованное имя+цена ────────────
def dedup(recs):
    by_art = {}
    for r in recs:
        key = r["art"] or r["name_norm"]
        prev = by_art.get(key)
        if prev is None:
            r["dups"] = 0
            by_art[key] = r
            continue
        # предпочитаем запись со СВОИМ (ozone) фото и ценой; иначе первую
        def score(x):
            return (1 if x.get("own_photo") else 0, 1 if x.get("price") else 0,
                    1 if x.get("ovh") else 0)
        if score(r) > score(prev):
            by_art[key] = r
            prev["dups"] = (prev.get("dups") or 0) + 1
            prev = None
        else:
            r["dups"] = 1
            prev["dups"] = (prev.get("dups") or 0) + 1
    return list(by_art.values())


def _readiness(r):
    flags = []
    if not (r.get("name") and r.get("price") and r.get("price") > 0):
        flags.append("НЕТ_ЦЕНЫ/ИМЕНИ")
    if not r.get("photos"):
        flags.append("НЕТ_ФОТО")
    elif not r.get("own_photo"):
        flags.append("НЕТ_ФОТО_СВОЕГО")       # только wb/yd/cargo — в карточку не пойдёт как есть
    if not r.get("ovh"):
        flags.append("НЕТ_ОВХ")
    if not r.get("dci"):
        flags.append("НЕТ_КАТЕГОРИИ")
    if r.get("type") is None and r.get("dci"):
        flags.append("НЕТ_ТИП_ЗНАЧЕНИЯ")
    return flags or ["ГОТОВО"]


def run(donor_master=None, outdir=None):
    outdir = Path(outdir) if outdir else RUNTIME_DIR
    files, all_recs, file_meta = [], [], []
    for p in sorted(WIP_ROOT.rglob("*.xlsx")):
        if _NAME_HINT.search(p.name) and "~$" not in p.name:
            meta, recs = scan_xlsx(p)
            if meta.get("reason"):
                meta.setdefault("rows_kept", 0)
            files.append(p)
            file_meta.append(meta)
            all_recs += recs

    donor_meta, donor_recs = {"rows_kept": 0}, []
    if donor_master and Path(donor_master).exists():
        donor_meta, donor_recs = _scan_donor_master(donor_master)
    else:  # поиск по умолчанию
        cands = sorted(Path.home().glob(DONOR_MASTER_GLOB))
        if cands:
            donor_meta, donor_recs = _scan_donor_master(cands[-1])

    recs = dedup(all_recs + donor_recs)
    for r in recs:
        r["readiness"] = _readiness(r)

    # сводки
    lines = {}
    for r in recs:
        line = classify_line(r["name"])
        r["line"] = line
        lines[line] = lines.get(line, 0) + 1
    by_ready = {}
    by_dci = {}
    own_photo = no_own_photo = no_ovh = ready_base = 0
    for r in recs:
        if r.get("own_photo"):
            own_photo += 1
        else:
            no_own_photo += 1
        if not r.get("ovh"):
            no_ovh += 1
        if r.get("dci"):
            by_dci[r["dci"]] = by_dci.get(r["dci"], 0) + 1
        if r["readiness"] == ["ГОТОВО"]:
            ready_base += 1
    for f in ("ГОТОВО",):
        pass
    by_ready = {}
    for r in recs:
        rr = tuple(r["readiness"])
        by_ready[rr] = by_ready.get(rr, 0) + 1

    summary = {
        "date": "2026-09-08",
        "source_files": len(files),
        "row_uniques_after_dedup": len(recs),
        "by_line": dict(sorted(lines.items(), key=lambda kv: -kv[1])),
        "by_dci_category": by_dci,
        "own_ozone_photo": own_photo, "no_own_photo": no_own_photo,
        "no_ovh": no_ovh, "ready_base_full": ready_base,
        "by_readiness": {",".join(k) if k else "?": v for k, v in sorted(by_ready.items(), key=lambda kv: -kv[1])},
    }

    outdir.mkdir(parents=True, exist_ok=True)
    stamp = "2026-09-08"
    json_path = outdir / f"ozon_korobki_base_{stamp}.json"
    md_path = outdir / f"ozon_korobki_base_{stamp}.md"
    payload = {"summary": summary, "files": file_meta,
               "donor": {"file": donor_meta.get("file"), "rows_kept": donor_meta.get("rows_kept", 0)},
               "products": recs}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    md = _render_md(summary, recs, file_meta)
    md_path.write_text(md, encoding="utf-8")
    return summary, json_path, md_path


def _render_md(summary, recs, file_meta):
    L = [f"# КОРОБКИ КАРТОННЫЕ — база НАИМЕНОВАНИЕ↔фото · {summary['date']}",
         "",
         f"- файлов-Ozon-шаблонов: {summary['source_files']}",
         f"- строк-уникальных (после дедупа артикул→фото→имя+цена): **{summary['row_uniques_after_dedup']}**",
         f"- со СВОИМ фото cdn1.ozone: **{summary['own_ozone_photo']}** · без своего фото: {summary['no_own_photo']}",
         f"- без ОВХ-упаковки: {summary['no_ovh']} · готово-база (имя+цена+своё-фото+ОВХ+категория+тип): **{summary['ready_base_full']}**",
         "",
         "## Линии (группировка по именам, НЕ Ozon-категория):", ""]
    for line, n in summary["by_line"].items():
        L.append(f"- {line}: {n}")
    L += ["", "## Категории Ozon (description_category_id из configs файлов):", ""]
    for dci, n in summary["by_dci_category"].items():
        L.append(f"- {dci}: {n} строк")
    L += ["", "## Файлы-источники:", ""]
    for f in file_meta:
        L.append(f"- {f['file']}: лист {f.get('sheet')} · dci {f.get('dci') or '-'} · "
                 f"строк-товаров {f.get('rows_kept')} (просмотрено {f.get('rows_seen')}, "
                 f"без-артикула {f.get('dropped_noart')}, не-коробок {f.get('dropped_nonbox')}) · "
                 f"медиа {f.get('media') or '-'}")
    L += ["", f"## Список ({len(recs)} строк) НАИМЕНОВАНИЕ ↔ фото:", "",
          "| артикул | НАИМЕНОВАНИЕ | линия | цена ₽ | своё-фото | ОВХ | dci | Тип | фото-URL (главное) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(recs, key=lambda x: x["name_norm"]):
        own = "да" if r.get("own_photo") else ("нет" if r.get("photos") else "-")
        ovh = "да" if r.get("ovh") else "-"
        main_url = (r["photos"][0] if r.get("photos") else "-")
        if len(str(main_url)) > 110:
            main_url = str(main_url)[:107] + "…"
        L.append(f"| {r.get('art') or '-'} | {r.get('name')} | {r.get('line')} | "
                 f"{int(r['price']) if r.get('price') else '-'} | {own} | {ovh} | "
                 f"{r.get('dci') or '-'} | {r.get('type') or '-'} | {main_url} |")
    return "\n".join(L)


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Инвентарь картонных коробок НАИМЕНОВАНИЕ↔фото (0₽, read-only).")
    ap.add_argument("--donor-master", default=None, help="путь к cargo_master_products.json (опционально)")
    ap.add_argument("--outdir", default=None, help="куда писать артефакт (по умолч. arbiter/runtime/ozon_boxes)")
    args = ap.parse_args(argv)
    summary, json_path, md_path = run(donor_master=args.donor_master, outdir=args.outdir)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"\nартефакты: {json_path}\n          {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

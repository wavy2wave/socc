#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН-БИБЛИОТЕКА (ozon_library_v1) — реестр-матрица всех товаров файла «ОЗОН ВПП 25 ноября …xlsx».

ЧТО ЭТО. Оператор (директива 08.09): «создай ОЗОН-библиотечную матрицу, чтобы система учла и видела
сколько и какие товары, какая категория и какие размеры … если товар повторяется по размерам — древо,
чтобы знать сколько карточек с такими или ОКОЛО размерами … идёт подвязки (ссылка на товар донора).
Для будущих циклов, это должно быть. Нужен порядок и экстремальный баланс».

ФАЙЛ (844 товара, лист «Шаблон») — это ГОТОВЫЙ к заливке дамп со СВОИМИ фото/копирайтом/габаритами:
  • фото в стлб15 — cdn1.ozone.ru / avatars.mds.yandex.net (свои, разделитель «,»; главная стлб14 пуста);
  • цена стлб3 + «цена до скидки» стлб4 — УЖЕ посчитаны (passthrough, множитель НЕ нужен);
  • габариты посылки стлб10-13 (вес г + Ш×В×Д мм) — у ВСЕХ 844 (реальные, не выдумка);
  • аннотация стлб28 — 809/844 (реальный копирайт, HTML — чистим);
  • стлб19 «Название модели» = ГРУППА исходной ОЗОН-карточки (tdt_plenka_low_832…) — это и есть
    ПРИРОДНОЕ ДРЕВО «около-размеров»: сколько SKU файла жили в одной карточке-СПУ донора-источника.
  • стлб20-23 (Длина/Ширина/Толщина/Единиц) ПУСТЫ → размер живёт ТОЛЬКО в имени, и имя мешает две
    конвенции: файл «0.4х5 м» = Ш0.4×Д5, файл «5*1.2 м» = Д5×Ш1.2 (донор-стиль, живая 9600155
    «5*0.4 м „Компакт“» = Д5×Ш0.4). → парсер обязан: ШИРИНА = меньшее в интервале [0.15, 2.2] м.

ФАЙЛ НЕ весь ВПП-рулоны (честная классификация, не «всё плёнка»):
  703 рулон-в-м, 83 пакеты-пупырка, 23 одиночных «…м», 18 без-размера, 11 плёнка-в-см,
  4 коробки/конверты, 2 ленты/скотч. Волна залива = только рулон-в-м (это канон-категории ВПП).

АРТЕФАКТЫ:
  • источник-строки JSON (канон): runtime/ozon-library/file-rows-2026-09-08.json (env OZON_FILM_ROWS_PATH)
  • матрица-библиотека JSON:       runtime/ozon-library/library-2026-09-08.json   (env OZON_LIBRARY_PATH)
  • карта размер→донор (скан дона): runtime/ozon-library/donor-size-map-2026-09-08.json (0₽ GET)

ЧИСТОТА: чтение xlsx ТОЛЬКО при --convert (нужен openpyxl → запуск в parsers/.venv). Орган сам
только stdlib + читает JSON-канон. Ничего наружу НЕ пишет без явного слова (dry; РУБИКОН цел).

Entrypoints:
  python parsers/.venv/bin/python arbiter/ozon_library_v1.py --convert          # xlsx → канон-строки JSON
  python arbiter/ozon_library_v1.py --build --tree          # матрица 844 + древо размеров (0₽)
  python arbiter/ozon_library_v1.py --donor-scan            # живой скан дона (0₽ GET) → donor_map + donor_link
  python arbiter/ozon_library_v1.py --report                # сводка по матрице (не пишет)
"""
import argparse
import html
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

TODAY = "2026-09-08"
HOUSE_BRAND = "ExpressGo"

# ── Пути/артефакты ──
RUNTIME = HERE / "runtime" / "ozon-library"
ROWS_DEFAULT = RUNTIME / f"file-rows-{TODAY}.json"          # канон-строки файла (после --convert)
LIBRARY_DEFAULT = RUNTIME / f"library-{TODAY}.json"         # матрица-библиотека
DONOR_MAP_DEFAULT = RUNTIME / f"donor-size-map-{TODAY}.json"
XLSX_DEFAULT = Path(os.path.expanduser(
    "~/Downloads/ready/WIP/ИП Анна/ОЗОН ВПП 25 ноября низкие цены.xlsx"))

# Ссылка на карточку донора (подвязка) — канонический хост shop.cargo-avto.ru (sp даёт 404 на части,
# проверено 08.09: shop 200 для 9602472 и 9600155, sp — 404 для 9602472).
DONOR_HOST = "https://shop.cargo-avto.ru"


def rows_path():
    return Path(os.environ.get("OZON_FILM_ROWS_PATH", ROWS_DEFAULT))


def library_path():
    return Path(os.environ.get("OZON_LIBRARY_PATH", LIBRARY_DEFAULT))


def donor_map_path():
    return Path(os.environ.get("OZON_DONOR_MAP_PATH", DONOR_MAP_DEFAULT))


def _atom_write(path, obj):
    """Атомарная запись JSON (tmp+rename) — не портим канон при сбое."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  РАЗМЕР/ТИП (единая правда размера: адаптер залива читает ТОЛЬКО отсюда)
# ══════════════════════════════════════════════════════════════════════════════════════════════

# Токен «N1 [x|*|х|на] N2 [м|метра|метров|метр]», N — до десятичной с запятой или точкой.
_SIZETOK_RE = re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:[*xх×]|\bна\b)\s*(\d+(?:[.,]\d+)?)\s*(?:м\b|метр\w*)?")
# Одинокая метка «N м» (без второго числа) — рулоном не считаем.
_SOLO_M_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*м\b")

# Честные рамки ширины рулона ВПП у донора (0.3–1.6; файл расширяет вниз/вверх немного): берём шире,
# чем у дона, чтобы файловые расширения не выпали, но не за 2.2 м (это уже не ВПП-рулон).
W_MIN, W_MAX = 0.15, 2.2


def classify_type(name):
    """Честная классификация строки файла (не «всё плёнка»). См. шапку."""
    n = (name or "").lower()
    if not n:
        return "без-размера"
    if any(k in n for k in ("короб", "гофро", "конверт")):
        return "коробки/конверты"
    if any(k in n for k in ("лент", "скотч", "стрич", "strech")) and "пленк" not in n and "пузыр" not in n:
        return "ленты/скотч"
    if any(k in n for k in ("пакет",)):
        return "пакеты-пупырка"
    if _SIZETOK_RE.search(n):
        return "рулон-в-м"
    if re.search(r"\d+\s*см", n) and "мм" not in n:
        return "пленка-в-см"
    if re.search(r"\d+\s*мм\b", n) and not _SOLO_M_RE.search(n):
        return "мм-изделия"
    if _SOLO_M_RE.search(n):
        return "м-одиночное"
    return "без-размера"


def parse_roll(name):
    """Имя плёнки → (ширина_м, длина_м) канон РУЛОНА, иначе None.

    Правило (живой факт 9600155 + расширения файла): из пары чисел вокруг x/*/х/«на» ШИРИНА = меньшее
    в [0.15, 2.2] м, ДЛИНА = большее. Вне рамок/нет пары → None (не выдумываем размер).
    """
    if not name:
        return None
    if any(k in (name.lower()) for k in ("пакет", "лист", "короб", "конверт", "лент")):
        return None
    m = _SIZETOK_RE.search(name.lower())
    if not m:
        return None
    try:
        a = float(m.group(1).replace(",", "."))
        b = float(m.group(2).replace(",", "."))
    except ValueError:
        return None
    if a <= 0 or b <= 0:
        return None
    w, l = (min(a, b), max(a, b))
    if not (W_MIN <= w <= W_MAX and l >= w and l <= 3000):
        return None
    return round(w, 3), round(l, 3)


def grams_of(name):
    """Плотность из имени «55 г/м²» → float (г/м²) иначе None. Честно из строки."""
    m = re.search(r"(\d+(?:[.,]?\d*))\s*г/м", str(name or ""))
    return round(float(m.group(1).replace(",", ".")), 2) if m else None


def layers_of(name):
    """Слои из имени («двухслойная/2х слойная/3 слоя/…») → int иначе None."""
    n = (name or "").lower()
    mp = {
        "однослой": 1, "однослойн": 1, "1 слой": 1, "1-слой": 1,
        "двухслой": 2, "двуслой": 2, "2х слой": 2, "2 слой": 2, "2-слой": 2,
        "трехслой": 3, "трёхслой": 3, "3 слой": 3, "3-слой": 3, "3х слой": 3,
        "4 слой": 4, "4х слой": 4,
    }
    for k, v in mp.items():
        if k in n:
            return v
    return None


def clean_text(v, max_len=None):
    """Текст: снять HTML-теги/сущности/управляющие, схлопнуть пробелы, обрезать."""
    if v is None:
        return ""
    s = html.unescape(str(v))
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if max_len and len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ИСТОЧНИК: xlsx → канон-строки JSON (ТОЛЬКО --convert; нужен openpyxl → parsers/.venv)
# ══════════════════════════════════════════════════════════════════════════════════════════════

# Карта колонок листа «Шаблон» (0-индекс; найдено инспекцией файла 08.09)
_COLS = {
    "article": 1, "name": 2, "price": 3, "old_price": 4, "vat": 5,
    "weight_g": 10, "pkg_w_mm": 11, "pkg_h_mm": 12, "pkg_d_mm": 13,
    "main_photo": 14, "photos": 15, "brand": 18, "src_model": 19,
    "len_m": 20, "wid_cm": 21, "thick_um": 22, "units": 23,
    "annotation": 28, "kind": 31, "material": 33, "color": 34,
}


def _cell(row, key):
    i = _COLS.get(key)
    if i is None or i >= len(row):
        return None
    return row[i]


def _split_photos(raw):
    """Поле фото (стлб15) — разделитель «,» (и пробелы/переводы строк). → [url,…] http-только."""
    if not raw:
        return []
    parts = re.split(r"[\s,;]+", str(raw))
    return [p for p in parts if p.startswith("http")][:15]


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def convert_xlsx(path=None, out=None):
    """Прочитать файл → список канон-строк JSON. fail-soft честной _error.

    Запускать под parsers/.venv (там openpyxl); в системном python3 откроется ImportError → честно.
    """
    try:
        import openpyxl  # noqa:  F401
    except Exception as e:
        return {"ok": False, "rows": [], "_error": f"нет openpyxl: {e} — гонять --convert под parsers/.venv"}
    src = Path(path) if path else Path(os.environ.get("OZON_FILM_FILE_PATH", XLSX_DEFAULT))
    if not src.exists():
        return {"ok": False, "rows": [], "_error": f"файл не найден: {src}"}
    try:
        wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
        ws = wb["Шаблон"] if "Шаблон" in wb.sheetnames else wb.worksheets[0]
    except Exception as e:
        return {"ok": False, "rows": [], "_error": f"{type(e).__name__}: {e}"}

    rows, hdr_seen = [], False
    for r in ws.iter_rows(values_only=True):
        if not hdr_seen:
            if r and len(r) > 1 and str(r[1]) == "Артикул*":
                hdr_seen = True
            continue
        art = _cell(r, "article")
        if not art or not str(art).startswith("tdt_"):
            continue
        name = clean_text(_cell(r, "name"))
        if not name:
            continue
        price = _num(_cell(r, "price"))
        if not price or price <= 0:
            continue  # цена не выдумываем — строку без цены в библиотеку не берём
        old = _num(_cell(r, "old_price"))
        w = round(_num(_cell(r, "weight_g")) or 0)
        size = parse_roll(name)
        rec = {
            "article": str(art).strip(),
            "name": name,
            "price": int(round(price)),
            "old_price": int(round(old)) if (old and old > price) else None,
            "vat": "0",                       # УСН (движок/донор-линии так и шлют), стлб5 не берём
            "type": classify_type(name),
            "size": ({"w_m": size[0], "l_m": size[1]} if size else None),
            "grams": grams_of(name),
            "layers": layers_of(name),
            "images": _split_photos(_cell(r, "photos")),
            "weight_g": w if w > 0 else None,
            "pkg_mm": ({  # реальные габариты посылки (Ш×В×Д из файла), все-или-ничего
                "width": int(round(_num(_cell(r, "pkg_w_mm")) or 0)),
                "height": int(round(_num(_cell(r, "pkg_h_mm")) or 0)),
                "depth": int(round(_num(_cell(r, "pkg_d_mm")) or 0)),
            } if all(_num(_cell(r, k)) and _num(_cell(r, k)) > 0 for k in
                     ("pkg_w_mm", "pkg_h_mm", "pkg_d_mm")) else None),
            "src_model": str(_cell(r, "src_model") or "").strip() or None,  # группа исходной ОЗОН-карточки
            "annotation": clean_text(_cell(r, "annotation")),
            "kind": clean_text(_cell(r, "kind")) or None,
            "src": f"file:{src.name}",
        }
        rows.append(rec)

    dest = Path(out) if out else rows_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    _atom_write(dest, rows)
    return {"ok": True, "rows": rows, "path": str(dest), "_error": None}


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  МАТРИЦА-БИБЛИОТЕКА
# ══════════════════════════════════════════════════════════════════════════════════════════════

def load_rows(path=None):
    """Канон-строки (JSON после --convert). fail-soft → {ok:False,_error}."""
    p = Path(path) if path else rows_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "rows": [], "_error": f"{type(e).__name__}: {e}"}
    rows = data if isinstance(data, list) else []
    return {"ok": True, "rows": [r for r in rows if isinstance(r, dict)], "path": str(p)}


def donor_size_map_from_pour_library(pour_library_rows):
    """Затравка donor_map из уже живой pour-library (донор-артикул + имя, где размер читается)."""
    out = {}
    for rec in pour_library_rows or []:
        art = str(rec.get("article") or rec.get("offer_id") or "").strip()
        size = parse_roll(str(rec.get("name") or ""))
        if art and size and size not in out:
            out[f"{size[0]}|{size[1]}"] = {
                "article": art, "url": f"{DONOR_HOST}/catalog/{art}/", "source": "pour-library"}
    return out


def donor_link_for(size, donor_map):
    """Канон (w,l) → donor_link (подвязка «откуда берём при заказе»).

    ШИРИНА задаёт физический товар донора (рулон режется по длине: файловые 0.4×10/×20 — легальные
    нарезки донорского 0.4×5/×50). Правило: точное (w,l) → exact; иначе ближайший донор ТОЙ ЖЕ ширины
    (±5 см), предпочтение по близости ширины, затем длины → near=true. Нет ширины в окне — null.
    """
    if not size or not donor_map:
        return None
    if isinstance(size, dict):
        size = (size.get("w_m"), size.get("l_m"))
    if not size or len(size) != 2:
        return None
    try:
        w, l = float(size[0]), float(size[1])
    except (TypeError, ValueError):
        return None
    key = f"{w}|{l}"
    if key in donor_map:
        d = donor_map[key]
        return {"article": d["article"], "url": d["url"], "near": False, "source": d.get("source", "scan")}
    best = None
    for k, d in donor_map.items():
        try:
            kw, kl = (float(x) for x in k.split("|"))
        except (TypeError, ValueError):
            continue
        if abs(round(kw - w, 6)) > 0.05:       # ширина в окне ±5 см — иначе другой товар
            continue
        score = (abs(kw - w), abs(kl - l))     # сначала ближе ширина, затем длина
        if best is None or score < best[0]:
            best = (score, d)
    if best:
        return {"article": best[1]["article"], "url": best[1]["url"], "near": True,
                "source": best[1].get("source", "scan")}
    return None


def build_library(rows, donor_map=None):
    """Строки канона → матрица-библиотека: записи + срезы (семьи/древо/ширины). Чистая модель (0₽)."""
    recs = []
    for r in rows:
        size = r.get("size")
        canonical = (size["w_m"], size["l_m"]) if size else None
        rec = {
            "article": r["article"],
            "name": r["name"],
            "type": r.get("type", "без-размера"),
            "category": {"slug": "vpp-plenka" if r.get("type") == "рулон-в-м" and canonical else None},
            "size": size,
            "canonical": canonical,
            "price": r.get("price"),
            "old_price": r.get("old_price"),
            "grams": r.get("grams"),
            "layers": r.get("layers"),
            "src_model": r.get("src_model"),
            "images": r.get("images", []),
            "donor_link": donor_link_for(size, donor_map) if (size and donor_map) else None,
            "pour_flag": bool(r.get("type") == "рулон-в-м" and canonical),
            "pour_state": None,      # заполняется при живом заливе (движок ЦИКЛ)
            "src": r.get("src"),
        }
        recs.append(rec)

    # ── Срезы (то, что просил оператор: «сколько и каких, какие размеры, древо») ──
    from collections import Counter
    by_type = Counter(x["type"] for x in recs)
    rolls = [x for x in recs if x["pour_flag"]]
    families = Counter((x["canonical"]) for x in rolls)                    # (w,l) → сколько SKU
    # древо: для каждой семьи — сколько ещё карточек системы с «ОКОЛО»-размером (ширина ±3 см)
    width_buckets = Counter(round(x["canonical"][0], 2) for x in rolls)
    w_keys = sorted(width_buckets)
    tree = {}
    for (w, l), n in sorted(families.items(), key=lambda kv: -kv[1]):
        near = sum(v for ww, v in width_buckets.items() if abs(ww - w) <= 0.03)
        tree[f"{w}x{l}"] = {"cards": n, "near_width_3cm": near}
    # в какой семье жил каждый src_model (исходная ОЗОН-группа) — сколько размеров в одной карточке-СПУ
    model_groups = Counter(x["src_model"] for x in rolls if x.get("src_model"))
    donors = Counter(1 for x in rolls if x.get("donor_link") and not x["donor_link"].get("near"))
    donors_near = Counter(1 for x in rolls if x.get("donor_link") and x["donor_link"].get("near"))

    return {
        "built": TODAY,
        "total_rows": len(recs),
        "summary": {
            "by_type": dict(by_type),
            "rolls": len(rolls),
            "families": len(families),                       # уникальных канонов (w,l)
            "cards_same_family_more_1": sum(1 for v in families.values() if v > 1),
            "src_model_groups": len(model_groups),           # кол-во СВОИХ SKU исходного кабинета (1:1, не группа)
            "donor_linked_exact": sum(donors),
            "donor_linked_near": sum(donors_near),
            "donor_unlinked": sum(1 for x in rolls if not x.get("donor_link")),
        },
        "size_tree": tree,
        "width_cum": {str(w): sum(v for ww, v in width_buckets.items() if ww <= w) for w in w_keys},
        "records": recs,
    }


def load_library(path=None):
    p = Path(path) if path else library_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "_error": f"{type(e).__name__}: {e}"}


def render_tree(lib):
    """Человеко-древо: топ-семьи + кумулятивные ширины (для оператора, 0₽)."""
    s = lib.get("summary", {})
    lines = [f"ОЗОН-БИБЛИОТЕКА · строк {s.get('total_rows', lib.get('total_rows'))} · "
             f"рулонов {s.get('rolls')} · семей (w,l) {s.get('families')} · "
             f"групп-СПУ {s.get('src_model_groups')}"]
    lines.append("ТИПЫ: " + " · ".join(f"{k}={v}" for k, v in s.get("by_type", {}).items()))
    lines.append("ПОДВЯЗКА к донору: точных " + str(s.get("donor_linked_exact", 0)) +
                 " · около " + str(s.get("donor_linked_near", 0)) + " · без " + str(s.get("donor_unlinked", 0)))
    lines.append("\nДРЕВО РАЗМЕРОВ (топ-семьи, карточек с «около»-шириной ±3см):")
    for k, v in list(lib.get("size_tree", {}).items())[:40]:
        lines.append(f"  {k:>14} м → карточек {v['cards']:>3} · около-ширина {v['near_width_3cm']:>3}")
    lines.append("\nШирины (кумулятивно, сколько рулонов ≤ ширины):")
    wc = lib.get("width_cum", {})
    for w in sorted(wc, key=float):
        lines.append(f"  ≤ {w} м → {wc[w]}")
    return "\n".join(lines)


def render_report(lib):
    s = lib.get("summary", {})
    lines = [f"БИБЛИОТЕКА {lib.get('built')} · строк {s.get('total_rows', lib.get('total_rows'))}"]
    for k in ("by_type", "rolls", "families", "cards_same_family_more_1",
              "src_model_groups", "donor_linked_exact", "donor_linked_near", "donor_unlinked"):
        lines.append(f"  {k}: {s.get(k)}")
    # волна-300 малых (детерминированно): рулоны по (w,l,article), первые 300
    rolls = sorted([r for r in lib.get("records", []) if r.get("pour_flag")],
                   key=lambda r: (r["canonical"][0], r["canonical"][1], r["article"]))
    w300 = {}
    for r in rolls[:300]:
        w300[round(r["canonical"][0], 2)] = w300.get(round(r["canonical"][0], 2), 0) + 1
    lines.append("  волна-300 (ширина↑, точные ширины): " +
                 ", ".join(f"{w}м={n}" for w, n in sorted(w300.items())))
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ПОДВЯЗКА К ДОНОРУ (0₽ GET): скан категории дона → карта размер→артикул
# ══════════════════════════════════════════════════════════════════════════════════════════════

FILM_DONOR_SLUG = "vozdushno-puzyrkovaya-plenka"


def scan_donor_map(limit=300):
    """Живой скан категории ВПП дона (shop.cargo-avto.ru) → {size_key: {article,url,source}}. 0₽ GET."""
    try:
        from suppliers.cargo_avto_v1 import CargoAvtoAdapter
    except Exception as e:
        return {"ok": False, "_error": f"импорт адаптера дона: {e}", "map": {}}
    try:
        rows = CargoAvtoAdapter().scan(category=FILM_DONOR_SLUG, limit=limit)
    except Exception as e:
        return {"ok": False, "_error": f"скан дона: {e}", "map": {}}
    mp = {}
    for r in rows or []:
        art = str(r.get("article") or "").strip()
        url = str(r.get("url") or "").strip() or (f"{DONOR_HOST}/catalog/{art}/" if art else "")
        size = parse_roll(str(r.get("name") or ""))
        if art and size and f"{size[0]}|{size[1]}" not in mp:
            mp[f"{size[0]}|{size[1]}"] = {"article": art, "url": url, "source": "scan"}
    return {"ok": True, "map": mp, "size": len(mp), "_error": None}


def apply_donor_map(lib, donor_map):
    """Пересчитать donor_link на записях матрицы по новой карте. Возвращает обновлённую матрицу (0₽)."""
    for r in lib.get("records", []):
        size = r.get("size")
        r["donor_link"] = donor_link_for(size, donor_map) if size else None
    # пересчёт сводки donor_*
    linked = [r for r in lib.get("records", []) if r.get("donor_link")]
    lib["summary"]["donor_linked_exact"] = sum(1 for r in linked if not r["donor_link"].get("near"))
    lib["summary"]["donor_linked_near"] = sum(1 for r in linked if r["donor_link"].get("near"))
    lib["summary"]["donor_unlinked"] = sum(1 for r in lib.get("records", [])
                                           if r.get("pour_flag") and not r.get("donor_link"))
    lib["donor_map_source"] = "scan"
    return lib


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════════════════════

def main(argv=None):
    ap = argparse.ArgumentParser(description="ОЗОН-БИБЛИОТЕКА V1 — матрица товаров файла (0₽, dry)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--convert", action="store_true", help="xlsx → канон-строки JSON (нужен openpyxl)")
    g.add_argument("--build", action="store_true", help="строки → матрица-библиотека JSON + печать")
    g.add_argument("--donor-scan", action="store_true", help="живой скан дона (0₽) → donor_map + пересчёт")
    g.add_argument("--report", action="store_true", help="сводка матрицы (не пишет)")
    ap.add_argument("--tree", action="store_true", help="с --build печатать древо размеров")
    ap.add_argument("--out", default=None, help="куда писать (иначе канон-пути модуля)")
    args = ap.parse_args(argv)

    if args.convert:
        r = convert_xlsx(out=args.out)
        print("CONVERT · ok=" + str(r["ok"]) + (" · " + r["_error"] if r.get("_error") else
              f" · строк {len(r['rows'])} → {r['path']}"))
        return 0 if r["ok"] else 1

    if args.report:
        lib = load_library()
        if not lib or not lib.get("records"):
            print("library ERR: " + str((lib or {}).get("_error", "нет матрицы — запусти --build")))
            return 1
        print(render_report(lib))
        return 0

    if args.build:
        m = load_rows()
        if not m["ok"]:
            print("rows ERR: " + m["_error"]); return 1
        # затравка donor-карты из живой pour-library (донор-карточки, что уже на витрине), если есть
        dm = {}
        try:
            pl_path = (Path(os.environ.get("OZON_FILM_LIBRARY_PATH", HERE / "runtime/ozon-film/pour-library.json")))
            if pl_path.exists():
                dm = donor_size_map_from_pour_library(json.loads(pl_path.read_text(encoding="utf-8")))
        except Exception:
            dm = {}
        lib = build_library(m["rows"], donor_map=dm or None)
        _atom_write(library_path() if not args.out else args.out, lib)
        print(render_report(lib))
        if args.tree:
            print()
            print(render_tree(lib))
        return 0

    if args.donor_scan:
        lib = load_library()
        if not lib or not lib.get("records"):
            print("library ERR: нет матрицы — запусти --build"); return 1
        res = scan_donor_map()
        if not res["ok"]:
            print("donor-scan ERR: " + res["_error"]); return 1
        _atom_write(donor_map_path(), res["map"])
        lib = apply_donor_map(lib, res["map"])
        _atom_write(library_path() if not args.out else args.out, lib)
        print(f"DONOR-SCAN · карта размеров {res['size']} → {donor_map_path()}")
        print("  точных " + str(lib["summary"]["donor_linked_exact"]) + " · около " +
              str(lib["summary"]["donor_linked_near"]) + " · без " + str(lib["summary"]["donor_unlinked"]))
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

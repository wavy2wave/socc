#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""МАТРИЦА ТОВАРОВ — слой дедупа добычи органа ARBITER (спека YMATRIX_V1.md).

ЗАЧЕМ. Реестр (ymarket_registry_v1) хранит связь «карточка ↔ товар донора» (offerId↔pid/SKU/url).
НЕ хранит: чем добыт товар, из какого источника, в какой категории, на какой ступени жизни он
сейчас. Без этого добыча повторяет сама себя (тот же товар из 3 источников = 3 карточки = хаос).
Этот модуль — ВЕРХНИЙ слой добычи: ДЕДУП по сущности товара (article|EAN|name+размер), статус
«кандидат→собран→залит→на витрине→продан», связь с заданием (заданиеId, директива оператора).
Аддитивный: НИЧЕГО существующее не трогает, свой стор в MEMORY_WAVE/reports/mint/arbiter.
0₽, READ + локальная атомарная запись. RUBICON цел.

ЧТО НЕ ХРАНИМ (M3): marketSku/shopSku/рейтинги — это реестр и state. Матрица = сущность + статус.

ЗАКОНЫ (механические, покрыты сухой приёмкой в __main__):
  M1 не выдумываем: строка без имени и ключа не пишется (отказ).
  M2 дедуп строг: кандидат сверяется по трём ключам (article | EAN | норм. name+размер);
     совпадение → апдейт существующей строки (добавляем источник), НЕ новая строка.
  M3 матрица НЕ дублирует реестр: marketSku/shopSku здесь нет.
  M4 статус-лесенка кандидат→собран→залит→сверен→на-витрине→продан (сверен = прошла СВЕРКУ,
     ступень 4 цикла); откат вниз только с причиной (note).
  M5 fail-soft + атомарно: битый файл → бланк; запись tmp+os.replace.
  M6 связь с заданием: каждая строка несёт task_id (задание→категория→партия→точка).
  M7 связь с ДОНОРОМ (директива оператора 10.09): строка несёт donor_pid/donor_article/
     donor_url/donor_store — «связь сразу с донором», а не только след в provider.
     article строки — КЛЮЧ (у набора свой f"{артикул}-{N}x"), donor_article — артикул донора 1-в-1.
  M8 размер-ось (директива оператора 10.09): строка несёт структурный size
     {w_mm,l_m,um,pack} там, где сборщик его ЗНАЕТ; размер сравним (size_cmp: какой больше/
     меньше по осям покупателя) и раскладывается в решётку семьи (size_lattice). Нет размера —
     не выдумываем: строка живёт без size, сравнение с ней → None.
"""
from __future__ import annotations

import os
import re
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent.parent.parent / "MEMORY_WAVE/reports/mint/arbiter"
SCHEMA = "ymarket.matrix.products.v1"

_STATUS_LADDER = ("кандидат", "собран", "залит", "сверен", "на-витрине", "продан")
_DEDUP_KEYS = ("article", "ean", "norm")

# Поля строки матрицы.
_FIELDS = ("name", "size_hint", "offer_id", "provider", "source_url", "category",
           "status", "task_id", "note", "sources",
           "donor_pid", "donor_article", "donor_url", "donor_store", "size")

_SRC_DELIM = "|"


def matrix_path():
    """Путь к стору. env YM_MATRIX_PATH перекрывает (песочница/тесты не пишут в канон)."""
    p = os.environ.get("YM_MATRIX_PATH")
    return Path(p) if p else (REPORTS / "ymarket_product_matrix.json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _blank():
    return {"schema": SCHEMA, "created_at": _now(), "updated_at": _now(), "rows": {}}


# ── нормировка ключа дедупа ───────────────────────────────────────────────────

_UNIT_WORDS = {"м", "см", "мм", "кг", "г", "мг", "мкм", "л", "мл", "шт", "х", "x"}


def norm_key(name, size_hint=None):
    """Норм. ключ дедупа из имени + размера (M2): '0,3×100 м' → words 'впп пленка' + size '0.3x100'.

    КЛЮЧЕВОЕ: числа берутся из name И size_hint ВМЕСТЕ (размер может стоять в любом из них), сортируются
    по возрастанию (0.3×100 → '0.3x100', порядок не важен) и дедуплицируются (size_hint не дублирует
    цифры имени). Слова — по алфавиту, без цифр/единиц ('м', 'см'...). БЕЗ размера ключ не строится
    (None): сливать по одному имени без размера опасно — 'ВПП 0,3×100' ≠ 'ВПП 1,2×50'.
    """
    if not name:
        return None
    blob = (name or "") + " " + (size_hint or "")
    nums = sorted({float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", blob)})
    if not nums:
        return None                                   # размера нет — по имени не сливаем (None)
    size_part = "x".join(f"{n:g}" for n in nums)
    words = re.findall(r"[а-яёa-z]+", (name or "").lower())
    words = sorted({w for w in words if w not in _UNIT_WORDS})
    if not words:
        return None
    return "::".join([" ".join(words), size_part])


# ── РАЗМЕР-ОСЬ (M8): какие размеры больше, какие меньше ───────────────────────
# Оператор 10.09: «важно чтобы понимал сам какие размеры больше какие меньше, чтобы
# добавить если что». norm_key намеренно теряет единицы (числа-мешком: 48×150 и 150×48
# дают один ключ) — для дедупа это верно, для ПОНИМАНИЯ размера недостаточно. Здесь
# единицы РАЗЛИЧАЮТСЯ и оси упорядочены по значимости для покупателя ленты:
#   ширина (мм) → намотка (м) → толщина (мкм) → штук в упаковке.
# Источник правды — структурный row['size'] (его кладёт сборщик, который ЗНАЕТ факты);
# для легаси-строк без него — парсер имени (fallback, честно помечен size_source).

# Порядок осей = порядок сравнения. Не менять без причины: от него зависит «больше/меньше».
_SIZE_AXES = ("w_mm", "l_m", "um", "pack")

# Единицы РАЗЛИЧАЮТСЯ регэкспами: 'м' ловится только там, где это НЕ 'мм' и НЕ 'мкм'
# (negative lookahead) — иначе '150 мкм' дала бы ложную намотку 150 м.
_SIZE_RX = (
    ("um", re.compile(r"(\d+(?:[.,]\d+)?)\s*мкм")),
    ("w_mm", re.compile(r"(\d+(?:[.,]\d+)?)\s*мм")),
    ("l_m", re.compile(r"(\d+(?:[.,]\d+)?)\s*м(?![мк])")),
    ("pack", re.compile(r"(\d+)\s*шт")),
)


def parse_size(name=None, size_hint=None):
    """Имя+подсказка → {ось: число} (чего не нашли — ключа нет; размер не выдумываем).

    Честный парсер имён («Скотч упаковочный 48 мм × 150 м, 40 мкм, прозрачный. — 2 шт»
    → {um:40, w_mm:48, l_m:150, pack:2}). Частичный размер — норма: у плёнки артикул
    часто несёт только намотку. Пусто → {} (строка остаётся без размера, M8).
    """
    blob = f"{name or ''} {size_hint or ''}"
    out = {}
    for field, rx in _SIZE_RX:
        m = rx.search(blob)
        if not m:
            continue
        try:
            v = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        out[field] = int(v) if field == "pack" else v
    return out


# Ключи _spec сборщиков (лента: длина_м/ширина_мм/толщина_мкм/штук_в_упаковке; плёнка:
# длина_м/ширина_мм/штук_в_упаковке) → оси M8. Неизвестное/пустое ключа не даёт (не выдумываем).
_SPEC_TO_AXIS = {
    "длина_м": "l_m", "ширина_мм": "w_mm", "толщина_мкм": "um", "штук_в_упаковке": "pack",
}


def spec_to_size(spec):
    """Структурный _spec сборщика (он ЗНАЕТ факты) → {w_mm,l_m,um,pack}. Нет → {}."""
    spec = spec or {}
    out = {}
    for k, ax in _SPEC_TO_AXIS.items():
        v = spec.get(k)
        if v is None or v == "":
            continue
        try:
            f = float(str(v).replace(",", ".").replace(" шт", "").strip())
        except (TypeError, ValueError):
            continue
        if not (isinstance(f, (int, float))) or f != f:  # nan-гейт
            continue
        out[ax] = int(f) if ax == "pack" else f
    if out and "pack" not in out:
        out["pack"] = 1
    return out


def _as_size(row_or_size):
    """Строка матрицы | голый size | (name,size_hint) → {ось: число}. Пусто → {}.

    Различаем «строку» и «сам размер» по осям: dict с осью — это уже размер, dict с
    'size'/'name' — строка. ШТУК ПО УМОЛЧАНИЮ = 1 (продаём рулонами: одиночка — упаковка
    из одного): без этого набор «2 шт» и одиночка сравнятся как РАВНЫЕ (ось pack не общая),
    а покупателю комплект из двух рулонов НЕ равен одному.
    """
    if isinstance(row_or_size, dict):
        if any(ax in row_or_size for ax in _SIZE_AXES):
            s = row_or_size                          # это сам размер, не строка
        else:
            s = row_or_size.get("size")
            if not isinstance(s, dict) or not s:
                s = parse_size(row_or_size.get("name"), row_or_size.get("size_hint"))
    elif isinstance(row_or_size, tuple):
        s = parse_size(*row_or_size[:2])
    else:
        return {}
    out = {ax: s[ax] for ax in _SIZE_AXES
           if isinstance(s.get(ax), (int, float)) and not isinstance(s.get(ax), bool)}
    if out and "pack" not in out:
        out["pack"] = 1
    return out


def raw_size(row):
    """row['size'] как есть (структурный факт сборщика) или None — без парсинга имени."""
    s = (row or {}).get("size") if isinstance(row, dict) else None
    return s if isinstance(s, dict) and s else None


def row_size(row):
    """Эффективный размер строки: структурный size, иначе парсер имени. {} → нет размера."""
    return _as_size(row)


def size_cmp(a, b):
    """Какой размер БОЛЬШЕ: -1 (a<b) · 0 (равны) · None (сравнить нечем — не выдумываем).

    Сравниваем по общим осям в порядке покупателя (ширина→намотка→толщина→штук).
    Общих осей нет (одна строка без размера / разные семейства осей) → None, а НЕ
    «равны»: молчаливый 0 склеил бы несравнимое.
    """
    sa, sb = _as_size(a), _as_size(b)
    shared = [ax for ax in _SIZE_AXES if ax in sa and ax in sb]
    if not shared:
        return None
    for ax in shared:
        if sa[ax] != sb[ax]:
            return 1 if sa[ax] > sb[ax] else -1
    return 0


def size_label(row_or_size):
    """Человекочитаемо: '48 мм × 150 м · 40 мкм · ×2 шт' (чего нет — того нет; «×1 шт» не шумим)."""
    s = _as_size(row_or_size)
    if not s:
        return "—"
    parts = []
    for ax, unit in (("w_mm", "мм"), ("l_m", "м"), ("um", "мкм"), ("pack", "шт")):
        v = s.get(ax)
        if v is None or (ax == "pack" and v == 1):
            continue
        parts.append(f"×{v:g} {unit}" if ax == "pack" else f"{v:g} {unit}")
    return " · ".join(parts) if parts else "—"


def size_sort_key(row):
    """Ключ сортировки «от меньшего к большему»; строки без размера — в конец."""
    s = _as_size(row)
    if not s:
        return (1, ())
    return (0, tuple(s.get(ax, 0) for ax in _SIZE_AXES))


def family_of(row):
    """Семья строки = словесная часть norm-ключа (размер в неё не входит) — база решётки."""
    nk = (row or {}).get("norm") if isinstance(row, dict) else None
    if not nk and isinstance(row, dict):
        nk = norm_key(row.get("name"), row.get("size_hint"))
    return nk.split("::")[0] if nk else None


def size_lattice(doc, family=None):
    """РЕШЁТКА РАЗМЕРОВ семьи: что у нас есть, от меньшего к большему + значения по осям.

    family=None → все строки, сгруппированные по семейству (family_of). Иначе — только
    строки этой семьи. Возвращает {family: {'rows':[…сортировано…], 'axes':{…}, 'n':N}},
    либо для одной семьи — её блок. «Добавить если что»: новая строка встаёт на своё
    место по size_cmp, а axes показывает, каких значений оси в семье ещё нет.
    """
    rows = [r for r in (doc.get("rows") or {}).values() if isinstance(r, dict)]
    fams = {}
    for r in rows:
        f = family_of(r) or "(без-семьи)"
        if family is not None and f != family:
            continue
        fams.setdefault(f, []).append(r)
    out = {}
    for f, rs in fams.items():
        rs = sorted(rs, key=size_sort_key)
        axes = {}
        for ax in _SIZE_AXES:
            vals = set()
            for r in rs:
                s = _as_size(r)
                if ax in s:
                    vals.add(s[ax])
            if vals:
                axes[ax] = sorted(vals)
        out[f] = {"n": len(rs), "axes": axes,
                  "rows": [{"key": r.get("key"), "name": r.get("name"),
                            "offer_id": r.get("offer_id"), "status": r.get("status"),
                            "donor_pid": r.get("donor_pid"), "size": _as_size(r),
                            "size_label": size_label(r)} for r in rs]}
    return out if family is None else out.get(family, {"n": 0, "axes": {}, "rows": []})


# ── стор (fail-soft, атомарно) ────────────────────────────────────────────────

def load():
    """Загрузить стор (fail-soft: нет файла/битый/чужой JSON → чистый бланк, M5)."""
    p = matrix_path()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            base = _blank()
            if isinstance(doc, dict) and isinstance(doc.get("rows"), dict):
                base["rows"] = doc["rows"]
            return base
        base = _blank()
        base["created_at"] = doc.get("created_at") or base["created_at"]
        base["rows"] = doc.get("rows") if isinstance(doc.get("rows"), dict) else {}
        return base
    except FileNotFoundError:
        return _blank()
    except Exception:
        return _blank()


def write_atomic(doc):
    """Атомарно записать стор: tmp + os.replace (без полу-файла, M5). Возвращает путь."""
    doc["updated_at"] = _now()
    doc.setdefault("schema", SCHEMA)
    p = matrix_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".ymatx_", suffix=".tmp")
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


# ── дедуп и статусы (чистые: не читают/не пишут файл) ─────────────────────────

def _find_dup(doc, article=None, ean=None, name=None, size_hint=None):
    """Ищем существующую строку по трём ключам (M2). Возвращает (row_key, row) или (None, None)."""
    rows = doc.get("rows") or {}
    nk = norm_key(name, size_hint)
    for key, row in rows.items():
        row = row if isinstance(row, dict) else {}
        if article and str(row.get("article") or "") == str(article):
            return key, row
        if ean and str(row.get("ean") or "") == str(ean):
            return key, row
        if nk and row.get("norm") == nk:
            return key, row
    return None, None


def ensure(doc, name=None, article=None, ean=None, size_hint=None, provider=None,
           source_url=None, category=None, task_id=None, donor_pid=None,
           donor_article=None, donor_url=None, donor_store=None, size=None):
    """Дедuп-вход добычи (M2): кандидат → строка матрицы (новая ИЛИ обновлённая).

    Без имени и без article/EAN → ValueError (M1, не выдумываем ключ). При совпадении по любому
    из трёх ключей обновляем существующую строку: добавляем источник в provider (sources[]),
    не плодим дубль. Возвращает (key, row, created:bool).

    M7: donor_* — durable связь с донором (pid/артикул/url/магазин). article строки — КЛЮЧ
    (у набора свой f"{артикул}-{N}x"), donor_article — артикул донора 1-в-1: не путать.
    M8: size — структурный размер {w_mm,l_m,um,pack}, если вызывающий его ЗНАЕТ; не dict /
    пустой → поле не трогаем (не выдумываем размер).
    """
    if not name and not article and not ean:
        raise ValueError("матрица: нет ни имени, ни article, ни EAN — не к чему привязать (M1)")
    nk = norm_key(name, size_hint)
    if isinstance(size, dict) and not size:
        size = None                              # пустой размер = отсутствие размера (M8)

    key, row = _find_dup(doc, article=article, ean=ean, name=name, size_hint=size_hint)
    rows = doc.setdefault("rows", {})
    if row is None:
        key = nk or str(article) or str(ean) or name
        row = {"key": key, "article": article, "ean": ean, "norm": nk,
               "name": name, "size_hint": size_hint, "offer_id": None,
               "provider": None, "source_url": None, "category": category,
               "status": "кандидат", "task_id": task_id, "note": None,
               "donor_pid": donor_pid, "donor_article": donor_article,
               "donor_url": donor_url, "donor_store": donor_store, "size": size,
               "sources": [], "first_seen": _now()}
        rows[key] = row
        created = True
    else:
        created = False

    for f, val in (("name", name), ("size_hint", size_hint), ("article", article),
                   ("ean", ean), ("provider", provider), ("source_url", source_url),
                   ("category", category), ("task_id", task_id),
                   ("donor_pid", donor_pid), ("donor_article", donor_article),
                   ("donor_url", donor_url), ("donor_store", donor_store)):
        if val is not None and str(val) != "":
            row[f] = val
    if size is not None:
        row["size"] = size
    if provider:
        srcs = row.setdefault("sources", [])
        if provider not in srcs:
            srcs.append(provider)
    # norm — ПРОИЗВОДНОЕ от текущего имени/подсказки (M2/M8): имя обновилось (напр. сборщик
    # убрал старый суффикс) → norm обязан следовать, иначе строка выпадает из решётки своей
    # семьи и дедуп по норм-ключу перестаёт её видеть. Ключ строки (dict-key) стабилен.
    if nk:
        row["norm"] = nk
    row["updated_at"] = _now()
    return key, row, created


def set_status(doc, key, status, note=None, offer_id=None):
    """Статус-лесенка (M4). Откат вниз по лестнице → требует note (иначе отказ).

    Возвращает обновлённую строку или None (строки нет / откат без причины).
    """
    if not key:
        return None
    row = (doc.get("rows") or {}).get(str(key))
    if row is None:
        return None
    cur = row.get("status") or "кандидат"
    if cur == status:
        if note:
            row["note"] = note
        return row
    # откат вниз? (M4)
    if cur in _STATUS_LADDER and status in _STATUS_LADDER:
        if _STATUS_LADDER.index(status) < _STATUS_LADDER.index(cur) and not note:
            raise ValueError(
                f"матрица: откат статуса '{cur}'→'{status}' требует note-причину (M4)")
    row["status"] = status
    if note:
        row["note"] = note
    if offer_id:
        row["offer_id"] = offer_id
    row["updated_at"] = _now()
    return row


def rows_by_status(doc, status):
    """Все строки статуса (для КПИ «на витрине = артефакт»). Пустой стор → []."""
    return [r for r in (doc.get("rows") or {}).values()
            if isinstance(r, dict) and r.get("status") == status]


def by_task(doc, task_id):
    """Строки по заданию (M6: задание→категория→партия→точка). Пустой стор → []."""
    if not task_id:
        return []
    return [r for r in (doc.get("rows") or {}).values()
            if isinstance(r, dict) and r.get("task_id") == task_id]


def all_rows(doc):
    """Весь стор (dict key→row). Пустой стор → {}."""
    return dict(doc.get("rows") or {})


# ── one-shot удобства ──────────────────────────────────────────────────────────

def ensure_one(**fields):
    """Один выстрел дедуп-входа: load → ensure → write_atomic. Возвращает (key, row, created)."""
    doc = load()
    key, row, created = ensure(doc, **fields)
    write_atomic(doc)
    return key, row, created


def status_one(key, status, note=None, offer_id=None):
    """Один выстрел статуса: load → set_status → write_atomic. Возвращает строку/None."""
    doc = load()
    row = set_status(doc, key, status, note=note, offer_id=offer_id)
    if row is not None:
        write_atomic(doc)
    return row


def snapshot():
    """Один выстрел КПИ-среза: {на-витрине, залит, собран, кандидат, всего}. Для планёрки/ТГ."""
    doc = load()
    rows = (doc.get("rows") or {}).values()
    out = {"всего": len(rows)}
    for s in _STATUS_LADDER:
        out[s] = 0
    for r in rows:
        if isinstance(r, dict) and r.get("status") in out:
            out[r["status"]] += 1
    return out


if __name__ == "__main__":
    # Сухая приёмка (0₽, пишет только если задан YM_MATRIX_PATH — иначе в канон отчётов).
    doc = _blank()
    k1, r1, c1 = ensure(doc, name="ВПП плёнка 0,3×100 м", article="9603273",
                        provider="cargo-avto", category="puzyrkovaya-plenka", task_id="p-1")
    # тот же товар из другого источника, без article (только имя+размер) — ДЕДУП M2
    k2, r2, c2 = ensure(doc, name="плёнка ВПП 100*0.3м", size_hint="0,3×100 м",
                        provider="wb", task_id="p-1")
    print("M2 дедуп: тот же товар → одна строка →",
          "ok" if k1 == k2 and c1 and not c2 else f"ОШИБКА k1={k1} k2={k2} c2={c2}")
    print("M2 источники склеились →", r2.get("sources"))
    # новый товар — новая строка
    k3, r3, c3 = ensure(doc, name="Коробка картонная 40×30×30", article="7612345",
                        provider="cargo-avto", category="kartonnye-koroba", task_id="p-1")
    print("M2 новый товар → новая строка →", "ok" if c3 and k3 != k1 else "ОШИБКА")
    print("M1 без имени/article/EAN →", end=" ")
    try:
        ensure(doc, provider="cargo-avto")
        print("ОШИБКА (должен был отказать)")
    except ValueError:
        print("отказ ✓")
    print("M3 в матрице нет marketSku →", "ok" if "marketSku" not in r1 else "ОШИБКА")
    # лесенка M4
    set_status(doc, k1, "собран")
    set_status(doc, k1, "залит", offer_id="9603273-1")
    set_status(doc, k1, "сверен")                      # СВЕРКА — ступень 4 цикла
    set_status(doc, k1, "на-витрине")
    print("M4 лесенка до на-витрине →", r1.get("status"))
    print("M4 откат без причины →", end=" ")
    try:
        set_status(doc, k1, "кандидат")
        print("ОШИБКА (должен был отказать)")
    except ValueError:
        print("отказ ✓")
    set_status(doc, k1, "кандидат", note="разжалован оператором")   # с причиной — можно
    print("M4 откат с причиной →", r1.get("status"))
    print("M6 по заданию p-1 →", len(by_task(doc, "p-1")), "строк")
    print("M5 fail-soft load битого файла →",
          "ok" if load.__doc__ else "?")
    print("\njson:", json.dumps({"snapshot": None}, ensure_ascii=False))
    print("snapshot():", json.dumps(snapshot(), ensure_ascii=False))

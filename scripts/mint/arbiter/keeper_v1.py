#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ХРАНИТЕЛЬ ДАННЫХ (библиотекарь) — SOCC·ДОМ read-орган над библиотеками системы.

ЕДИНЫЙ универсальный ответ: «есть ли библиотека залитых товаров / процессов?»
→ ДА, вот полки и живые счётчики. Собственной копии данных НЕ заводим:
каждая полка = читатель РОДНОГО органа/файла; цифры — только из живых сторов.

Плоскости (каждая = чистые функции над документами живых сторов):
  полки()        — каждая полка: источник, свежесть, счётчики, вердикт {ok, why}.
  магазины()     — ЯМ из stores.json (slug, business/campaign/warehouse, категория)
                    + дрилл (карточек/на-витрине/PASS-сверка) по живым сторам;
                    ОЗОН — псевдо-магазин (полки залива). Ответ-пример:
                    «atlas-express-film · 37 карточек · 37 на витрине · PASS».
  типы(slug)     — классификация «из них коробки N / рулоны M / ленты K»
                    (ЯМ → ozon_library_v1.classify_type по именам карточек;
                    ОЗОН → summary.by_type канона). Нет сигнала → «не распознан» (KP4).
  ходы(...)      — process-полка: список готовых записанных ходов, фильтры kind/market,
                    ход(PID) → читаемый .md-отчёт.
  экспорт(<полка|магазин|ход>) — точный JSON-срез + строка-потребитель (реюз).
                    stdout или --out <файл> (0₽, локально, без сети).
  пульс()        — универсальный ответ ВСЕГДА (структура + честные нули/причины).

ЗАКОНЫ (KP):
  KP1 нет писателей: орган ничего не записывает и не ходит в сеть; экспорт —
      только по явному --out; без --out срез печатается (0 файлов).
  KP2 честная пустота: битая/отсутствующая полка → вердикт «нет» + причина.
  KP3 re-use канона: читаем родными читателями (ymarket_library_v1 / ymarket_matrix_v1 /
      ozon_library_v1 / process_artifact_v1); env-перекрытия каждого стора уважаем.
      Кeeper-специфичные пути (stores.json, tape_library) перекрываются
      KEEPER_STORES_PATH / KEEPER_TAPE_PATH (песочницы/тесты).
  KP4 классификация не выдумывает: «не распознан» вместо гадания.
  KP5 пульс отвечает всегда: структура ответа + честные нули/причины отсутствия.
  KP6 экспорт = точный срез + строка-потребитель (как срез встроен в систему).

Эволюционный контур: process-полка («ходы») наполняется авто-швом закрытого ЦИКЛ-1 —
см. process_artifact_v1.register_cycle1 + ymarket_cycle1_v1._sync_process_artifact.
Этот орган читает результат; пишет шов, не орган.

Использование (0₽, сухо):
  python3 keeper_v1.py                          # пульс (универсальный ответ)
  python3 keeper_v1.py --полки
  python3 keeper_v1.py --магазины [slug]
  python3 keeper_v1.py --типы <slug>            # slug = магазин ЯМ | «ozon»
  python3 keeper_v1.py --ходы [--kind …] [--market …]
  python3 keeper_v1.py --ход PID
  python3 keeper_v1.py --экспорт ym-goods [--out f]
"""
import glob
import json
import os
import sys
from pathlib import Path

ARBITER = Path(__file__).resolve().parent
if str(ARBITER) not in sys.path:
    sys.path.insert(0, str(ARBITER))

# ──────────────────────────────────────────────────────────────────────────
# Канон-константы
# ──────────────────────────────────────────────────────────────────────────
SCHEMA = "keeper.v1"
_CREATED = "2026-09-09"

# Классы ОЗОН-канона → человекочитаемые подписи (типовая полка/дрилл, KP4-без-гадания)
_OZON_CLASS_LABELS = {
    "рулон-в-м": "рулоны в метрах",
    "пленка-в-см": "плёнка в см",
    "ленты/скотч": "ленты/скотч",
    "коробки/конверты": "коробки/конверты",
    "пакеты-пупырка": "пакеты-пупырка",
    "м-одиночное": "метраж одиночный",
    "без-размера": "без размера (не распознан)",
}

# Полки в порядке показа. reader → (ok, path, doc, why); n/sub — сводка для пульса.
_SHELF_DEFS = [
    dict(name="ym-goods", title="Библиотека товаров ЯМ (goods)", market="ym",
         desc="живые карточки-леджер по магазинам", read="_read_goods", n="_n_goods"),
    dict(name="ym-matrix", title="Матрица товаров ЯМ", market="ym",
         desc="трекинг карточек до витрины (кандидат→на-витрине)", read="_read_matrix", n="_n_matrix"),
    dict(name="ym-stores", title="Магазины ЯМ (манифесты)", market="ym",
         desc="stores.json: business/campaign/склад/категория", read="_read_stores", n="_n_stores"),
    dict(name="ozon-matrix", title="Матрица файла ОЗОН", market="ozon",
         desc="донорские строки → классы/рулоны/семьи", read="_read_ozon", n="_n_ozon"),
    dict(name="ozon-pour", title="Живой залив ОЗОН (файл)", market="ozon",
         desc="файловые артикулы tdt_* → product_id", read="_read_pour", n="_n_pour"),
    dict(name="ozon-tape", title="Скотч-полка (канон)", market="ozon",
         desc="семейства/карточки партии (сухо)", read="_read_tape", n="_n_tape"),
    dict(name="process", title="Процессы — готовые ходы", market="all",
         desc="процесс-артефакты (kind=pour/cycle1/…)", read="_read_process", n="_n_process"),
]

_STORE_WORDS = ("магазины", "магазин", "stores", "store", "shop")
_SHELF_WORDS = ("полки", "полка", "shelves", "shelf")
_HOD_WORDS = ("ходы", "ходы", "processes", "runs")
_HOD_WORDS2 = ("ход", "run")
_TYPES_WORDS = ("типы", "тип", "types", "type")
_EXPORT_WORDS = ("экспорт", "export", "slice", "срез")
_PULSE_WORDS = ("пульс", "pulse", "всё", "все", "answer", "lib", "библиотека")


# ──────────────────────────────────────────────────────────────────────────
# Читатели (fail-soft: каждая → (ok, path, doc, why); KP2, KP3)
# ──────────────────────────────────────────────────────────────────────────
def _load_goods():
    from ymarket_library_v1 import load as yl_load, library_path as yl_path
    p = Path(yl_path())
    if not p.exists():
        return False, str(p), {}, "файл не найден"
    try:
        doc = yl_load()
    except Exception as e:  # noqa: BLE001
        return False, str(p), {}, f"{type(e).__name__}: {e}"
    goods = (doc or {}).get("goods") or {}
    if not goods:
        return False, str(p), doc, "goods-леджер пуст"
    return True, str(p), doc, ""


def _load_matrix():
    from ymarket_matrix_v1 import load as mx_load, matrix_path as mx_path
    p = Path(mx_path())
    if not p.exists():
        return False, str(p), {}, "файл не найден"
    try:
        doc = mx_load()
    except Exception as e:  # noqa: BLE001
        return False, str(p), {}, f"{type(e).__name__}: {e}"
    if not (doc or {}).get("rows"):
        return False, str(p), doc, "матрица пуста"
    return True, str(p), doc, ""


def _load_stores():
    p = Path(os.environ.get("KEEPER_STORES_PATH", "") or ARBITER / "runtime/cycle1/stores.json")
    p = p.expanduser()
    if not p.exists():
        return False, str(p), {}, "stores.json не найден"
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return False, str(p), {}, f"{type(e).__name__}: {e}"
    if not isinstance(doc, dict) or not doc:
        return False, str(p), doc, "манифестов магазинов нет (пусто)"
    return True, str(p), doc, ""


def _load_ozon():
    from ozon_library_v1 import load_library as oz_load, library_path as oz_path
    p = Path(oz_path())
    if not p.exists():
        return False, str(p), {}, "файл не найден"
    try:
        doc = oz_load() or {}
    except Exception as e:  # noqa: BLE001
        return False, str(p), {}, f"{type(e).__name__}: {e}"
    recs = doc.get("records") if isinstance(doc, dict) else None
    if isinstance(doc, dict) and not recs and not doc.get("summary"):
        return False, str(p), doc, "матрица пуста"
    return True, str(p), doc, ""


def _load_pour():
    from process_artifact_v1 import pour_journal_path as pjp
    p = Path(pjp())
    if not p.exists():
        return False, str(p), {}, "журнал залива не найден"
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return False, str(p), {}, f"{type(e).__name__}: {e}"
    body = doc if isinstance(doc, dict) else {}
    if not body:
        return False, str(p), body, "журнал пуст"
    return True, str(p), body, ""


def _tape_path():
    env = os.environ.get("KEEPER_TAPE_PATH", "")
    if env:
        return Path(env).expanduser()
    hits = sorted(glob.glob(str(ARBITER / "runtime" / "cargo_matrix_*" / "tape_library.json")))
    return Path(hits[-1]) if hits else ARBITER / "runtime" / "cargo_matrix_" / "tape_library.json"


def _load_tape():
    p = _tape_path()
    if not p.exists():
        return False, str(p), {}, "tape_library.json не найден"
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return False, str(p), {}, f"{type(e).__name__}: {e}"
    if not isinstance(doc, dict):
        return False, str(p), doc, "схема не json-объект"
    return True, str(p), doc, ""


def _load_process():
    from process_artifact_v1 import load as pa_load, library_path as pa_path
    p = Path(pa_path())
    try:
        runs, _le = pa_load()
    except Exception as e:  # noqa: BLE001
        return False, str(p), {}, f"{type(e).__name__}: {e}"
    if not p.exists() and not runs:
        return False, str(p), runs, "process_library.json не найден"
    return True, str(p), runs, ""


_READERS = {
    "ym-goods": _load_goods, "ym-matrix": _load_matrix, "ym-stores": _load_stores,
    "ozon-matrix": _load_ozon, "ozon-pour": _load_pour, "ozon-tape": _load_tape,
    "process": _load_process,
}


# ──────────────────────────────────────────────────────────────────────────
# Сводчики (чистые: doc → dict{n, sub, counts}); KP3 — считают по живым сторам
# ──────────────────────────────────────────────────────────────────────────
def _goods_counts(goods):
    """Счётчики goods-леджера ИЗ ЗАПИСЕЙ (doc['stats'] нет в файле — считается из records)."""
    from collections import Counter
    n = len(goods)
    stores, cats = Counter(), Counter()
    passed = 0
    for g in goods.values():
        sslug = g.get("store_slug")
        stores[sslug] += 1 if sslug else 0
        cats[g.get("category_slug")] += 1
        if (g.get("last_verified") or {}).get("verdict") == "PASS":
            passed += 1
    counts = [("карточек", n), ("магазина", len(stores)), ("сверено PASS", passed)]
    counts += [(f"→ {s}", v) for s, v in sorted(stores.items())]
    counts += [(f"кат {c}", v) for c, v in sorted(cats.items())]
    return n, counts


def _matrix_counts(doc):
    rows = (doc or {}).get("rows") or {}
    n = len(rows)
    from collections import Counter
    status, cat = Counter(), Counter()
    for r in rows.values():
        status[r.get("status", "?")] += 1
        cat[r.get("category", "?")] += 1
    counts = [("строк", n), ("на-витрине", status.get("на-витрине", 0))]
    counts += [(f"кат {k}", v) for k, v in sorted(cat.items())]
    return n, counts


def _stores_counts(doc):
    n = len(doc)
    counts = [("магазина", n)]
    for slug, prof in sorted(doc.items()):
        bid = prof.get("business_id")
        lab = f"бизнес {_fmt_big(bid)}" if bid is not None else (
            f"мама {prof.get('mother')}" if prof.get("mother") else "наследник")
        counts.append((f"→ {slug}", lab))
    return n, counts


def _ozon_counts(doc):
    recs = doc.get("records") if isinstance(doc, dict) else None
    total = doc.get("total_rows") if isinstance(doc, dict) else None
    n = int(total) if isinstance(total, int) else (len(recs) if isinstance(recs, (dict, list)) else 0)
    summ = (doc or {}).get("summary") or {}
    byt = summ.get("by_type") or {}
    counts = [("строк", n), ("рулонов", summ.get("rolls", 0)), ("семей", summ.get("families", 0))]
    counts += [(f"кат {_OZON_CLASS_LABELS.get(k, k)}", v) for k, v in sorted(byt.items())]
    return n, counts


def _pour_counts(doc):
    n = len(doc)
    from collections import Counter
    status = Counter()
    for v in doc.values():
        if isinstance(v, dict):
            status[v.get("status", "?")] += 1
    counts = [("карточек", n)]
    counts += [(f"статус {k}", v) for k, v in sorted(status.items())]
    return n, counts


def _tape_counts(doc):
    st = doc.get("stats") or {}
    n = int(st.get("groups", 0))
    counts = [("групп-семей", n), ("карточек партии", st.get("cards", 0)),
              ("ozon-товаров в группах", st.get("ozon_items", 0)),
              ("cargo-фактов", st.get("cargo_facts", 0))]
    return n, counts


def _process_counts(runs):
    n = len(runs)
    from collections import Counter
    kind, market, state = Counter(), Counter(), Counter()
    for r in runs.values():
        kind[r.get("kind", "?")] += 1
        market[r.get("market", "?")] += 1
        state[r.get("state", "?")] += 1
    counts = [("записей (ходов)", n)]
    counts += [(f"kind {k}", v) for k, v in sorted(kind.items())]
    counts += [(f"market {k}", v) for k, v in sorted(market.items())]
    return n, counts


_SUMMERS = {
    "ym-goods": lambda doc: _goods_counts(doc.get("goods", {})),
    "ym-matrix": _matrix_counts,
    "ym-stores": _stores_counts,
    "ozon-matrix": _ozon_counts,
    "ozon-pour": _pour_counts,
    "ozon-tape": _tape_counts,
    "process": lambda runs: _process_counts(runs),
}


def _mtime_of(path):
    try:
        from datetime import datetime
        return datetime.fromtimestamp(Path(path).stat().st_mtime).strftime("%d.%m %H:%M")
    except Exception:  # noqa: BLE001
        return "?"


# ──────────────────────────────────────────────────────────────────────────
# Плоскости (чистые сборки над сторами; KP2/KP5 — честные вердикты)
# ──────────────────────────────────────────────────────────────────────────
def shelves_now():
    """Отчёт по каждой полке: источник/свежесть/счётчики/вердикт. (KP2 честная пустота)."""
    out = []
    for d in _SHELF_DEFS:
        ok, path, doc, why = _READERS[d["name"]]()
        item = dict(name=d["name"], title=d["title"], market=d["market"], desc=d["desc"],
                    path=path, ok=ok, why=why, mtime=_mtime_of(path) if ok else None,
                    n=None, counts=[])
        if ok:
            n, counts = _SUMMERS[d["name"]](doc)
            item["n"] = n
            item["counts"] = counts
        out.append(item)
    return out


def _render_shelf_line(s):
    head = f"«{s['name']}» — {s['title']}"
    if not s["ok"]:
        return f"  ✖ {head}\n      НЕТ · причина: {s['why']}"
    det = " · ".join(f"{k} {v}" for k, v in s["counts"])
    src = f"      источник: {s['path']} (обновл. {s['mtime']})" if s["mtime"] else ""
    return f"  ✔ {head} → {s['n']}\n      {det}\n{src}"


def render_shelves(shelves):
    lines = ["БИБЛИОТЕКА СИСТЕМЫ — полки (0₽, чистый read)"]
    for s in shelves:
        lines.append(_render_shelf_line(s))
    lines.append("")
    return "\n".join(lines)


def stores_now():
    """Магазины ЯМ (манифесты + дрилл по живым сторам) + псевдо-магазин ОЗОН."""
    ok, path, profs, why = _load_stores()
    stores = []
    goods_doc = {}
    gok, _, goods_doc, _ = _load_goods()
    matrix_doc = {}
    mok, _, matrix_doc, _ = _load_matrix()
    goods = (goods_doc or {}).get("goods", {}) if gok else {}
    rows = (matrix_doc or {}).get("rows", {}) if mok else {}

    if ok and isinstance(profs, dict):
        for slug, p in sorted(profs.items()):
            g_recs = [g for g in goods.values() if g.get("store_slug") == slug] if gok else []
            passed = sum(1 for g in g_recs if (g.get("last_verified") or {}).get("verdict") == "PASS")
            builder = p.get("builder_slug") or ""
            on_v = sum(1 for r in rows.values() if r.get("category") == builder
                       and r.get("status") == "на-витрине") if mok else 0
            stores.append(dict(kind="ym", slug=slug, profile=p,
                               articles=len(g_recs), on_vitrine=on_v, passed=passed))
    # ОЗОН-псевдо-магазин (полки залива)
    ooz = {s["name"]: s for s in shelves_now()}
    oz_mat = ooz.get("ozon-matrix", {}).get("n")
    oz_mat_st = ooz.get("ozon-matrix", {}).get("counts", [])
    pour_n = ooz.get("ozon-pour", {}).get("n")
    tape_n = ooz.get("ozon-tape", {}).get("n")
    tape_c = dict(ooz.get("ozon-tape", {}).get("counts", [])).get("карточек партии", 0)
    stores.append(dict(kind="ozon", slug="ozon-express",
                       profile={"donor_category": "vpp-film + скотч",
                                "note": "кабинет продавца; полки матрицы/залива/скотча"},
                       matrix_rows=oz_mat, pour=pour_n, tape_groups=tape_n, tape_cards=tape_c))
    return stores


def _fmt_big(v):
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    return v


def render_stores(stores, only=None):
    lines = ["МАГАЗИНЫ СИСТЕМЫ — Name + ID + кол-во товаров"]
    for s in stores:
        if only and s["slug"] != only:
            continue
        if s["kind"] == "ym":
            p = s["profile"]
            head = f"• {s['slug']} (ЯМ)"
            ids = []
            for key, lab in (("business_id", "бизнес"), ("campaign_id", "кампания"),
                             ("warehouse_id", "склад")):
                v = p.get(key)
                if v is not None:
                    ids.append(f"{lab} {_fmt_big(v)}")
                elif key == "warehouse_id" and p.get("mother"):
                    ids.append("склад = мамы (наследование)")
            mother = f", мама {p['mother']}" if p.get("mother") else ""
            cat = p.get("donor_category", "?")
            lines.append(f"  {head}{mother}\n      ID: {' · '.join(ids)}\n"
                         f"      категория: {cat} · builder: {p.get('builder','?')} · markup ×{p.get('markup','?')}\n"
                         f"      товаров: {s['articles']} карточек · на-витрине: {s['on_vitrine']} · сверено PASS: {s['passed']}")
        else:
            lines.append(f"  • {s['slug']} (ОЗОН)\n"
                         f"      {s['profile']['donor_category']}\n"
                         f"      матрица строк: {s['matrix_rows'] or 0} · живой залив: {s['pour'] or 0} карточек (скрыты)\n"
                         f"      скотч-полка: {s['tape_groups'] or 0} групп / {s['tape_cards']} карточек (сухо)")
    if only and not any(s["slug"] == only for s in stores):
        lines.append(f"  ✖ магазина «{only}» нет в манифестах")
    lines.append("")
    return "\n".join(lines)


def types_for(target, paths_ok=None):
    """«Из них коробки N / рулоны M / ленты K». target: slug магазина ЯМ или «ozon».
    KP4: классификация не выдумывает — нет сигнала → «не распознан»."""
    from collections import Counter
    from ozon_library_v1 import classify_type
    if target == "ozon":
        ok, _, doc, _ = _load_ozon()
        if not ok:
            return None, "матрица ОЗОН не читается"
        summ = (doc or {}).get("summary") or {}
        byt = summ.get("by_type") or {}
        return [dict(klass=_OZON_CLASS_LABELS.get(k, k), n=int(v))
                for k, v in sorted(byt.items(), key=lambda kv: -kv[1])], ""
    # ЯМ-магазин: классифицируем имена карточек стора родным классификатором ОЗОН
    gok, _, goods_doc, _ = _load_goods()
    stores_ok, _, profs, _ = _load_stores()
    if not stores_ok or target not in (profs or {}):
        return None, f"магазина «{target}» нет в stores.json (slug?)"
    goods = (goods_doc or {}).get("goods", {}) if gok else {}
    recs = [g for g in goods.values() if g.get("store_slug") == target]
    c = Counter()
    for g in recs:
        name = g.get("name") or ""
        kl = classify_type(name) if name else "без-размера"
        c[kl] += 1
    if not c:
        return None, "карточек у магазина в goods-леджере нет"
    return [dict(klass=_OZON_CLASS_LABELS.get(k, k), n=int(v))
            for k, v in sorted(c.items(), key=lambda kv: -kv[1])], ""


def render_types(target, items, note):
    lines = [f"ТИПЫ МАГАЗИНА «{target}» — класс по имени карточки (не выдумываем)"]
    if note:
        lines.append(f"  ✖ {note}")
    else:
        for it in items:
            lines.append(f"  • {it['klass']}: {it['n']}")
    lines.append("")
    return "\n".join(lines)


def hods(kind=None, market=None):
    """process-полка: список записанных готовых ходов (фильтры kind/market)."""
    ok, _, runs, why = _load_process()
    if not ok:
        return [], why
    res = []
    for r in runs.values():
        if kind and r.get("kind") != kind:
            continue
        if market and r.get("market") != market:
            continue
        res.append(r)
    res.sort(key=lambda r: (r.get("date", "") or ""), reverse=True)
    return res, ""


def render_hods(hs, note=""):
    lines = ["ХОДЫ — записанные прогоны системы (process_library)"]
    if note:
        lines.append(f"  ✖ {note}")
    elif not hs:
        lines.append("  ✖ записанных ходов нет (шов включён: следующий живой PASS --commit ЦИКЛ-1 станет ходом)")
    for r in hs:
        st = r.get("state") or "done"
        lines.append(f"  • {r.get('id','?')} · {r.get('kind','?')}/{r.get('market','?')} "
                     f"[{st}] · {r.get('date','?')}\n      {r.get('what','')}")
    lines.append("")
    return "\n".join(lines)


def render_hod(pid):
    from process_artifact_v1 import show as pa_show, render_report as pa_report
    rec = pa_show(pid)
    if not rec:
        return f"ХОД «{pid}» не найден в process_library.\n\n"
    body = "\n".join(pa_report(rec))
    return f"ХОД {pid}\n\n{body}\n"


# ──────────────────────────────────────────────────────────────────────────
# Экспорт (KP1/KP6): точный JSON-срез + строка-потребитель; файл — по явному --out
# ──────────────────────────────────────────────────────────────────────────
def _consumer_for(name, target=None):
    if name == "ym-goods":
        return "ЦЕЛЕВОЙ: ymarket_cycle1_v1 (магазины по stores.json, builder_slug=категория)"
    if name == "ym-matrix":
        return "ЦЕЛЕВОЙ: statuses на-витрине → ДОМ (socc ym день / КОНТРОЛЬ)"
    if name == "ym-stores":
        return "ЦЕЛЕВОЙ: движок ЦИКЛ-1 читает этот манифест"
    if name == "ozon-matrix":
        return "ЦЕЛЕВОЙ: ozon-плёнка/кросс-цена; classify_type = типовой дрилл"
    if name == "ozon-pour":
        return "ЦЕЛЕВОЙ: ПУЛЬТ ОЗОН залива; process_artifact_v1.register_pour"
    if name == "ozon-tape":
        return "ЦЕЛЕВОЙ: скотч-канон 90741 → карточки партии (сухо)"
    if name == "process":
        return "готовые ходы: шов ЦИКЛ-1 (register_cycle1) + ретро pour"
    if target:
        return f"магазин {target}: ЦИКЛ-1 по манифесту (--store {target})"
    return "срез читается органами; 0₽, без сети"


def export_slice(target, paths_ok=None):
    """Срез: (ok, payload|note). Полка по имени | магазин по slug | ход по PID."""
    names = {d["name"] for d in _SHELF_DEFS}
    if target in names:
        ok, path, doc, why = _READERS[target]()
        if not ok:
            return False, dict(shelf=target, ok=False, why=why, source=path)
        n, counts = _SUMMERS[target](doc)
        return True, dict(schema="keeper.export.v1", kind="shelf", shelf=target,
                          consumer=_consumer_for(target), source=path,
                          n=n, counts=dict(counts))
    # ход по PID (P-…)
    from process_artifact_v1 import show as pa_show
    rec = pa_show(target)
    if rec:
        return True, dict(schema="keeper.export.v1", kind="process", pid=target,
                          consumer=_consumer_for("process"),
                          source="process_library.json", record=rec)
    # магазин по slug (ЯМ) или ozon
    stores = stores_now()
    for s in stores:
        if s["slug"] == target:
            if s["kind"] == "ym":
                gok, _, goods_doc, _ = _load_goods()
                goods = (goods_doc or {}).get("goods", {}) if gok else {}
                mok, _, matrix_doc, _ = _load_matrix()
                rows = (matrix_doc or {}).get("rows", {}) if mok else {}
                bs = s["profile"].get("builder_slug", "")
                return True, dict(schema="keeper.export.v1", kind="store", store=target,
                                  consumer=_consumer_for("ym-stores", target),
                                  profile=s["profile"],
                                  cards=[g for g in goods.values() if g.get("store_slug") == target],
                                  matrix_rows=[r for r in rows.values()
                                               if r.get("category") == bs])
            return True, dict(schema="keeper.export.v1", kind="store", store=target,
                              consumer=_consumer_for("ozon-pour"),
                              profile=s["profile"])
    return False, dict(schema="keeper.export.v1", target=target, ok=False,
                       why=f"«{target}» — не полка, не магазин, не PID хода. Полки: "
                           + ", ".join(sorted(names)))


def render_export(target, out_path=None, paths_ok=None):
    ok, payload = export_slice(target)
    if not ok:
        return f"ЭКСПОРТ «{target}»\n  ✖ {payload.get('why')}\n\n", payload
    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True) if p.parent != Path(".") else None
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"ЭКСПОРТ «{target}» → {p} (0₽, локально)\n\n", payload
    # нет --out → печатаем срез (KP1: 0 файлов)
    return f"ЭКСПОРТ «{target}»\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n", payload


# ──────────────────────────────────────────────────────────────────────────
# Пульс (KP5): универсальный ответ всегда — структура + честные цифры
# ──────────────────────────────────────────────────────────────────────────
def pulse():
    sh = {s["name"]: s for s in shelves_now()}
    stores = stores_now()
    ym = [s for s in stores if s["kind"] == "ym"]
    ym_articles = sum(s["articles"] for s in ym)
    ym_vitr = sum(s["on_vitrine"] for s in ym)
    hs, _ = hods()
    head = "БИБЛИОТЕКА СИСТЕМЫ — универсальный ответ: ДА, библиотеки есть и вот живые полки"
    y = sh.get("ym-goods", {})
    if y.get("ok"):
        line1 = f"ЯМ: {len(ym)} магазина · {ym_articles} карточек в goods-леджере · {ym_vitr} на-витрине (матрица)"
        per = " · ".join(f"{s['slug']}: {s['articles']}" for s in ym)
        line1 += f"\n     {per}"
    else:
        line1 = f"ЯМ: полка goods не читается ({y.get('why')})"
    o = sh.get("ozon-matrix", {})
    po = sh.get("ozon-pour", {})
    tp = sh.get("ozon-tape", {})
    bits = []
    if o.get("ok"):
        bits.append(f"матрица {o['n']} строк")
    else:
        bits.append(f"матрица не читается ({o.get('why')})")
    if po.get("ok"):
        bits.append(f"живой залив {po['n']} карточек")
    if tp.get("ok"):
        bits.append(f"скотч-полка {tp['n']} групп")
    line2 = f"ОЗОН: {' · '.join(bits) if bits else 'полки пусты'}"
    ph = sh.get("process", {})
    if hs:
        line3 = f"ПРОЦЕССЫ (готовые ходы): {len(hs)} — " + " · ".join(
            f"{r.get('id')} [{r.get('kind')}/{r.get('market')}] {r.get('what','')[:60]}"
            for r in hs[:4])
    else:
        line3 = "ПРОЦЕССЫ (готовые ходы): 0 — шов включён: следующий живой PASS --commit ЦИКЛ-1 станет ходом"
    return (f"{head}\n  ✔ {line1}\n  ✔ {line2}\n  {line3}\n\n"
            f"смотри: --полки · --магазины [slug] · --типы <slug|ozon> · --ходы · --ход PID · --экспорт <…>\n")


# ──────────────────────────────────────────────────────────────────────────
# CLI-вход (0₽)
# ──────────────────────────────────────────────────────────────────────────
def _stripped(tok):
    return tok.lstrip("-")


def _args_map(argv):
    """Разбор: '--полки', 'полки', '--магазины atlas-express-film', '--типы ozon', …"""
    opts, rest = {}, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--out", "-o") and i + 1 < len(argv):
            opts["out"] = argv[i + 1]
            i += 2
            continue
        if a in ("--kind", "-k") and i + 1 < len(argv):
            opts["kind"] = argv[i + 1]
            i += 2
            continue
        if a in ("--market", "-m") and i + 1 < len(argv):
            opts["market"] = argv[i + 1]
            i += 2
            continue
        rest.append(_stripped(a))
        i += 1
    return rest, opts


def cmd(argv):
    """Главная плоскость: (text, rc). Без аргументов → пульс."""
    argv = argv or []
    if not argv or _stripped(argv[0]) in _PULSE_WORDS:
        return pulse(), 0
    rest, opts = _args_map(argv)
    if not rest:
        return pulse(), 0
    sub = rest[0]
    if sub in _SHELF_WORDS:
        return render_shelves(shelves_now()), 0
    if sub in _STORE_WORDS:
        only = rest[1] if len(rest) > 1 else None
        if only and only == "ozon-express":
            only = "ozon-express"
        return render_stores(stores_now(), only=only), 0
    if sub in _TYPES_WORDS:
        if len(rest) < 2:
            return "типы: укажи slug магазина ЯМ или «ozon» — например --типы atlas-express-film\n", 2
        items, note = types_for(rest[1])
        return render_types(rest[1], items, note), 0
    if sub in _HOD_WORDS:
        hs, note = hods(kind=opts.get("kind"), market=opts.get("market"))
        return render_hods(hs, note), 0
    if sub in _HOD_WORDS2 and len(rest) > 1:
        return render_hod(rest[1]), 0
    if sub in _EXPORT_WORDS:
        if len(rest) < 2:
            return "экспорт: укажи цель — полка/магазин/ход (например --экспорт ym-goods)\n", 2
        text, _payload = render_export(rest[1], out_path=opts.get("out"))
        return text, 0
    return (f"ХРАНИТЕЛЬ: неизвестная команда «{sub}»\n\n"
            "команды: --полки | --магазины [slug] | --типы <slug|ozon> | "
            "--ходы [--kind k][--market m] | --ход PID | --экспорт <цель> [--out f] | пульс\n", 2)


def main():
    text, rc = cmd(sys.argv[1:])
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    sys.exit(rc)


if __name__ == "__main__":
    main()

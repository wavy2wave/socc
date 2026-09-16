#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PROCESS ARTIFACT V1 — библиотека ПРОЦЕССОВ (прогон-артефакт, общая для ЯМ и ОЗОН).

Директива оператора (2026-09-09): «каждый залив/прогон/ЦИКЛ = НАШ АРТЕФАКТ … нужна библиотека
ПРОЦЕССОВ (законно оконченных, подтверждённых оператором) … легко найти прогон по хешу … на ЯМ и
Озоне одинаково». Уточнение: «система в любой момент понимает кто и как и сколько работал и когда,
всё прозрачно. Упрощай всё для себя же».

Почему: механика (задания/циклы/планёрка) была, а атом работы «ПРОГОН» как артефакт не рождался —
залив жил отдельно от доски и не оставлял читаемого отчёта с хешем. Теперь каждый атом оставляет
запись `P-<sha1(canon)[:8]>` в process_library.json + читаемый ОТЧЁТ ПРОГОНА runs/<slug>-<hash>.md.
К записи прикреплено ПЕРЕИСПОЛЬЗУЕМОЕ знание категории (категорию изучили один раз → будущий залив
знает её и умеет лить), решения оператора, результат, ссылки на product-level журналы и лог
«кто/когда». Законно-окончен = подтверждён оператором (state=confirmed).

Зачем ОБЩИЙ модуль: та же директива «на ЯМ и Озоне одинаково». kind=pour|cycle1|cycle_day|run|scout,
market="ozon"|"ym". Слой ничего не ломает: старые журналы/матрицы НЕ трогает — только читает (для
ретро) и добавляет свою запись + .md.

ЗАПИСЬ — тот же паттерн, что ymarket_tasks_v1/registry/matrix/library:
  process_library.json под якорем MEMORY_WAVE/reports/mint/arbiter (канон отчётов ARBITER);
  env PROCESS_LIBRARY_PATH / PROCESS_RUNS_DIR перекрывают (песочница/тесты не пишут в канон);
  запись атомарна (tmp+replace); load битого → пусто + честный load_error (не падаем, не врём).
Dry-гейт НЕ здесь: кто вызывает seal — тот и решает (движок залива пишет только под not dry AND commit).

СХЕМА артефакта (плоский словарь, «упрощай»):
  id         P-<sha1(canon)[:8]> — стабильный контент-хеш (kind|market|category|date|what)
  kind       pour|cycle1|cycle_day|run|scout
  market     "ozon"|"ym"          category  slug (vpp-film …)
  task_id    T-xxxx (задание доски, из которого рождён прогон; ретро — "")
  what       заголовок            date      YYYY-MM-DD (день прогона)
  owner      орган-ответственный  (строка)
  params     {source, wave, article_scheme, mode: dry|live, …}  — КАК делалось
  decision   {word, via, …}       — слово/кем решено (оператор, орган)
  result     {ok, imported, failures, errors, shelf, stocks}
  artifacts  {journal, library, manifest, matrix}  — ссылки на product-level файлы
  knowledge  {category:{…}, …}    — переиспользуемое знание категории (см. summarize_vpp)
  log[]      {at, organ, what}    — прозрачность: кто/когда что делал с этим прогоном
  state      running|done|confirmed   (законно-окончен = confirmed, подтверждён оператором)
  confirm    {by:"operator", at}  created_at / updated_at
"""
import argparse
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path

# ── словари (общие, маленькие) ────────────────────────────────────────────────────
KINDS = ("pour", "cycle1", "cycle_day", "run", "scout")
MARKETS = ("ozon", "ym")
STATES = ("running", "done", "confirmed")

# Категория-знание ВПП — ПРОВЕРЕННЫЕ живые факты линии (зафиксированы в ozon_film_file_v1,
# ozon_film_zaliv_v1; см. план/артефакт). Не выдумываем: dci/tid/атрибуты реально слали на Ozon.
VPP_KNOWLEDGE = {
    "slug": "vpp-film",
    "name": "воздушно-пузырьковая плёнка (ВПП), рулоны в метрах",
    "ozon": {
        "dci": 17027937, "tid": 97503,
        "brand": "ExpressGo — attr 85 ПО ЗНАЧЕНИЮ (в словаре нет dvid, не выдумываем)",
        "material": {"attr": 6383, "value": "полиэтилен", "dvid": 62043},
        "color": {"attr": 10096, "прозрачный": 61572, "чёрный": 61574},
        "article_scheme": "VPP-{W-см}x{L-м}-{слои}[k][-NN] — ozon_article_v1 (будущие заливы)",
        "warehouse": "1020005029808130 «Карго.Вавилова»",
    },
    "donor": {"host": "shop.cargo-avto.ru"},
}


# ── корень/пути (тот же якорь, что ymarket_tasks_v1: SOCC/MEMORY_WAVE — канон) ──────
def _reports_root():
    here = Path(__file__).resolve().parent
    for anc in (here, *here.parents):
        if (anc / ".git").is_dir() and (anc / "MEMORY_WAVE").is_dir():
            return anc
    for anc in (here, *here.parents):
        if (anc / "MEMORY_WAVE").is_dir():
            return anc
    return here.parent.parent.parent


REPORTS = _reports_root() / "MEMORY_WAVE/reports/mint/arbiter"


def library_path():
    """Реестр артефактов. env PROCESS_LIBRARY_PATH перекрывает (песочница/тесты)."""
    p = os.environ.get("PROCESS_LIBRARY_PATH")
    return Path(p).expanduser() if p else (REPORTS / "process_library.json")


def runs_dir():
    """Каталог читаемых ОТЧЁТОВ ПРОГОНА (.md). env PROCESS_RUNS_DIR перекрывает."""
    p = os.environ.get("PROCESS_RUNS_DIR")
    return Path(p).expanduser() if p else (REPORTS / "runs")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


# ── id / нормализация ───────────────────────────────────────────────────────────────

def run_id(kind, market, category, date, what):
    """Стабильный id намерения = sha1(canon)[:8]. Тот же прогон (kind/market/категория/дата/что) →
    тот же id: повторный seal обновляет запись, НЕ плодит дубль."""
    canon = "|".join([str(kind).lower(), str(market).lower(),
                      str(category or "").strip().lower(), str(date or ""),
                      str(what or "").strip().lower()])
    return "P-" + hashlib.sha1(canon.encode("utf-8")).hexdigest()[:8]


def normalize(record):
    """Чистая запись с дефолтами. Пустой what → (None, err): не сохраняем мусор (без фейк-записи)."""
    if not isinstance(record, dict):
        return None, "запись не dict"
    what = (record.get("what") or "").strip()
    kind = (record.get("kind") or "").strip().lower()
    market = (record.get("market") or "").strip().lower()
    if not what:
        return None, "what пуст — прогон без «что делали» не фиксируем"
    if kind not in KINDS:
        return None, f"kind '{kind}' вне {KINDS}"
    if market not in MARKETS:
        return None, f"market '{market}' вне {MARKETS}"
    date = str(record.get("date") or "")
    pid = record.get("id") or run_id(kind, market, record.get("category"), date, what)
    t = _now()
    clean = {
        "id": pid, "kind": kind, "market": market,
        "category": (record.get("category") or "").strip().lower(),
        "task_id": (record.get("task_id") or "").strip(),
        "what": what, "date": date,
        "owner": (record.get("owner") or "").strip().upper() or "SYSTEM",
        "params": dict(record.get("params") or {}),
        "decision": dict(record.get("decision") or {}),
        "result": dict(record.get("result") or {}),
        "artifacts": dict(record.get("artifacts") or {}),
        "knowledge": dict(record.get("knowledge") or {}),
        "log": list(record.get("log") or []),
        "state": record.get("state") or "done",
        "created_at": t, "updated_at": t,
    }
    if record.get("confirm"):
        clean["confirm"] = dict(record["confirm"])
    return clean, None


def _slug(rec):
    return f"{rec['kind']}-{rec['market']}-{rec['date']}"


# ── load/save (паттерн ymarket_tasks_v1: fail-soft load, атомарный save) ─────────

def load(path=None):
    """Читать библиотеку → (dict id→запись, load_error). Нет файла → пусто, 0 ошибок."""
    p = Path(path) if path else library_path()
    if not p.exists():
        return {}, None
    try:
        data = json.loads(p.read_text())
        runs = data.get("runs") if isinstance(data, dict) else None
        if runs is None:
            return {}, {"load_error": "схема не process.artifact (нет ключа runs)"}
        return dict(runs), None
    except Exception as e:
        return {}, {"load_error": f"{type(e).__name__}: {e}"}


def save(runs, path=None):
    """Записать реестр (id → запись, dedup). Атомарно tmp+replace. Dry-гейт ЗДЕСЬ НЕ держим —
    вызывает движок под своим правилом (not dry AND commit)."""
    p = Path(path) if path else library_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "process.artifact.v1", "updated_at": _now(), "runs": dict(runs)}
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        tmp.replace(p)
        return {"ok": True, "n": len(payload["runs"]), "path": str(p)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "path": str(p)}


# ── печать отчёта (то, что оператор ОТКРЫВАЕТ и видит) ──────────────────────────────

_ICON = {"running": "◐", "done": "●", "confirmed": "✅"}


def render_report(rec):
    """Читаемый RU-отчёт прогона (строки .md). Read-only. id в заголовке → «найти по хешу»."""
    d = (rec.get("decision") or {})
    r = (rec.get("result") or {})
    k = (rec.get("knowledge") or {}).get("category") or {}
    oz = k.get("ozon") or {}
    p = rec.get("params") or {}
    art = rec.get("artifacts") or {}
    out = [
        f"# ОТЧЁТ ПРОГОНА · {rec['id']}   [{_ICON.get(rec['state'], '○')} {rec['state']}]",
        f"**{rec['what']}**",
        "",
        f"- дата: {rec['date']} · площадка: {rec['market'].upper()} · вид: {rec['kind']}",
        f"- категория: {rec.get('category') or '—'} · владелец: {rec['owner']}"
        + (f" · задание доски: {rec['task_id']}" if rec.get("task_id") else ""),
        "",
        "## Как делали (params)",
    ]
    for kk, vv in p.items():
        out.append(f"- {kk}: {vv}")
    out.append("")
    out.append("## Решение (кто/слово)")
    if d:
        for kk, vv in d.items():
            out.append(f"- {kk}: {vv}")
    else:
        out.append("- —")
    out.append("")
    out.append("## Результат")
    if r:
        for kk, vv in r.items():
            if isinstance(vv, (dict, list)):
                out.append(f"- {kk}: {json.dumps(vv, ensure_ascii=False)}")
            else:
                out.append(f"- {kk}: {vv}")
    else:
        out.append("- —")
    out.append("")
    out.append("## Знание категории (переиспользуемо)")
    if k:
        if k.get("name"):
            out.append(f"- {k['name']}")
        for kk, vv in oz.items():
            out.append(f"- ozon.{kk}: {vv}")
        for kk in ("top_sizes", "price_band", "pour", "donor"):
            if k.get(kk):
                out.append(f"- {kk}: {json.dumps(k[kk], ensure_ascii=False)}")
    else:
        out.append("- —")
    out.append("")
    out.append("## Артефакты (product-level, куда смотреть)")
    if art:
        for kk, vv in art.items():
            out.append(f"- {kk}: {vv}")
    else:
        out.append("- —")
    out.append("")
    out.append("## Лог (кто/когда)")
    if rec.get("log"):
        for e in rec["log"]:
            out.append(f"- {e.get('at')} · {e.get('organ')}: {e.get('what')}")
    else:
        out.append("- —")
    if rec.get("confirm"):
        c = rec["confirm"]
        out.append("")
        out.append(f"## Подтверждение: {c.get('by')} @ {c.get('at')} — законно-окончен")
    return out


def report_path(rec, rd=None):
    """Путь читаемого .md: runs/<kind>-<market>-<date>-<id>.md."""
    return (rd or runs_dir()) / f"{_slug(rec)}-{rec['id']}.md"


def _write_report(rec, rd=None):
    rd = rd or runs_dir()
    rd.mkdir(parents=True, exist_ok=True)
    fp = report_path(rec, rd)
    fp.write_text("\n".join(render_report(rec)), encoding="utf-8")
    return fp


# ── seal / confirm ────────────────────────────────────────────────────────────────────

def seal(record, *, commit=False, path=None, rd=None, organ=None, log_what=None):
    """Зафиксировать прогон. dry (commit=False): печатает отчёт + что запишет, НИЧЕГО не пишет.
    commit: registry + читаемый .md (дедуп по id — повторный seal обновляет, не плодит дубль).
    Возвращает {ok, record, id, dry, path, md, error}."""
    rec, err = normalize(record)
    if err:
        return {"ok": False, "error": err}
    runs, _le = load(path)
    existing = runs.get(rec["id"])
    if existing:
        # тот же атом → обновляем поля, id/created не трогаем (TZ-дедуп)
        created = existing.get("created_at")
        old_log = existing.get("log") or []
        rec["created_at"] = created or rec["created_at"]
        rec["log"] = old_log
    if not existing:
        rec["log"] = list(rec.get("log") or [])
    # лог «кто/когда» (прозрачность): seal дописывает строку
    rec["log"].append({"at": _now(), "organ": (organ or rec["owner"] or "SYSTEM").upper(),
                       "what": log_what or f"прогон зафиксирован ({'live' if commit else 'dry-preview'})"})
    rec["state"] = "confirmed" if existing and existing.get("state") == "confirmed" else rec.get("state") or "done"
    rec["updated_at"] = _now()
    runs[rec["id"]] = rec
    if commit:
        sv = save(runs, path)
        if not sv.get("ok"):
            return {"ok": False, "error": sv.get("error"), "id": rec["id"]}
        md = str(_write_report(rec, rd))
        return {"ok": True, "record": rec, "id": rec["id"], "dry": False,
                "path": sv.get("path"), "md": md, "written": sv.get("n")}
    text = "\n".join(render_report(rec))
    print("СУХО · артефакт НЕ записан (0 записей). Будет записано:")
    print(f"  registry: {library_path() if path is None else path}")
    print(f"  отчёт:    {report_path(rec, rd)}")
    print("─" * 40)
    print(text)
    return {"ok": True, "record": rec, "id": rec["id"], "dry": True,
            "path": str(library_path() if path is None else path)}


def confirm(pid, *, by="operator", commit=False, path=None, rd=None):
    """Законно-окончен: state=confirmed, confirm={by,at}, лог-строка. Только по явному слову (commit)."""
    runs, le = load(path)
    rec = runs.get(pid)
    if not rec:
        return {"ok": False, "error": f"артефакта {pid} нет в библиотеке", "id": pid}
    if rec.get("state") == "confirmed":
        return {"ok": True, "record": rec, "id": pid, "dry": not commit, "already": True}
    rec["state"] = "confirmed"
    rec["confirm"] = {"by": str(by or "operator").lower(), "at": _now()}
    rec["updated_at"] = _now()
    rec.setdefault("log", []).append({"at": _now(), "organ": str(by or "operator").upper(),
                                      "what": "подтвердил — законно-окончен"})
    runs[pid] = rec
    if commit:
        sv = save(runs, path)
        if not sv.get("ok"):
            return {"ok": False, "error": sv.get("error"), "id": pid}
        md = str(_write_report(rec, rd))
        return {"ok": True, "record": rec, "id": pid, "dry": False, "md": md}
    print(f"СУХО · подтверждение НЕ записано. Подтвердит: {by} · артефакт {pid}")
    return {"ok": True, "record": rec, "id": pid, "dry": True}


# ── поиск (легко найти прогон по хешу / срезу) ───────────────────────────────────────

def find(*, kind=None, market=None, category=None, date=None, state=None):
    runs, _le = load()
    res = []
    for r in runs.values():
        if kind and r.get("kind") != kind:
            continue
        if market and r.get("market") != market:
            continue
        if category and r.get("category") != category:
            continue
        if date and r.get("date") != str(date):
            continue
        if state and r.get("state") != state:
            continue
        res.append(r)
    return sorted(res, key=lambda x: (x.get("date", ""), x.get("id", "")))


def show(pid):
    runs, _le = load()
    return runs.get(pid)


# ── знание категории из журнала залива (реюз: категория изучена → будущий залив знает) ─

def summarize_vpp(journal_records, donor_size_map=None, donor_host=None):
    """Свернуть живые записи журнала залива → knowledge-блок категории ВПП. ЧИСТАЯ функция:
    на вход словарь записей {tdt: flat}, на выход knowledge. Без сети, без чтения файлов тут."""
    recs = [v for v in (journal_records or {}).values() if isinstance(v, dict)]
    prices = [v.get("price") for v in recs if isinstance(v.get("price"), (int, float))]
    sizes = Counter()
    shelves = Counter()
    donors = Counter()
    for v in recs:
        s = v.get("size") or {}
        if s.get("w_m") is not None and s.get("l_m") is not None:
            sizes[f"{s['w_m']:g}×{s['l_m']:g}"] += 1
        if v.get("shelf"):
            shelves[v["shelf"]] += 1
        if v.get("donor_article"):
            donors[v["donor_article"]] += 1
    dm = dict(donor_size_map or {})
    dm_sample = [{"size": kk, "article": vv.get("article") if isinstance(vv, dict) else vv}
                 for kk, vv in list(dm.items())[:8]]
    knowledge = {
        "category": {
            **{kk: vv for kk, vv in VPP_KNOWLEDGE.items() if kk != "donor"},
            "donor": {
                "host": donor_host or VPP_KNOWLEDGE["donor"]["host"],
                "distinct_articles": len(donors),
                "top_articles": [{"article": a, "cards": n} for a, n in donors.most_common(5)],
                "size_map": dm_sample,
            },
            "top_sizes": sizes.most_common(5),
            "shelf": dict(shelves),
            "price_band": {"min": min(prices), "max": max(prices)} if prices else {},
            "pour": {"cards": len(recs), "with_donor": sum(1 for v in recs if v.get("donor_article"))},
        }
    }
    return knowledge


# ── ретро-артефакт залива (законно уже сделанного) ─────────────────────────────────

def pour_journal_path():
    """Журнал залива ВПП-файла. env PROCESS_POUR_JOURNAL перекрывает (тесты/песочница)."""
    p = os.environ.get("PROCESS_POUR_JOURNAL")
    if p:
        return Path(p).expanduser()
    return Path(__file__).resolve().parent / "runtime" / "ozon-library" / "file-pour-library.json"


def register_pour(date_str, *, commit=False, what=None, task_id="", owner="OZON_ZALIV",
                  path=None, rd=None, decision=None):
    """Ретро-артефакт: прочитать живой журнал залива (runtime/ozon-library) → seal записи
    kind=pour. 0 сетевых вызовов; журналы только ЧИТАЕМ. decision: слово оператора (по умолчанию —
    честная формулировка из доктрины: слово было на ОБЪЁМ; схема артикула tdt на залитых 434)."""
    jp = pour_journal_path()
    if not jp.exists():
        return {"ok": False, "error": f"журнал залива не найден: {jp}"}
    try:
        journal = json.loads(jp.read_text())
    except Exception as e:
        return {"ok": False, "error": f"журнал битый: {type(e).__name__}: {e}"}
    if not isinstance(journal, dict):
        return {"ok": False, "error": "журнал не словарь {tdt: запись}"}
    dm = {}
    dmp = jp.parent / f"donor-size-map-{date_str}.json"
    if dmp.exists():
        try:
            dm = json.loads(dmp.read_text())
        except Exception:
            dm = {}
    what = what or f"Залив ВПП-рулонов на Ozon из файла «ОЗОН ВПП …xlsx» (волна до остатка) — {len(journal)} карточек"
    rec, err = normalize({
        "kind": "pour", "market": "ozon", "category": "vpp-film",
        "date": date_str, "what": what, "task_id": task_id, "owner": owner,
        "params": {
            "source": "файл «ОЗОН ВПП 25 ноября низкие цены.xlsx», лист Шаблон",
            "mode": "live",
            "cards": len(journal),
            "article_scheme": "файловые артикулы tdt_plenka_low_* на залитых карточках (оставлены как есть); "
                              "системная схема VPP-… (ozon_article_v1) — для будущих заливов",
        },
        "decision": decision or {
            "word": "«залей до остатка ~430, смелее» — слово оператора на ОБЪЁМ волны",
            "via": "operator",
            "note": "ре-артикуляция 434 отменена оператором (карточки остаются); VPP — только в будущее",
        },
        "result": {
            "ok": True, "imported": len(journal),
            "shelf": "все «одобрена, но скрыта» (0 сток) — карточки на витрину не выведены",
            "product_id": sum(1 for v in journal.values() if isinstance(v, dict) and v.get("product_id")),
        },
        "artifacts": {
            "journal": str(jp), "product_library": "file-pour-library.json (434 ключа tdt)",
            "category_library": str(jp.parent / f"library-{date_str}.json"),
            "donor_size_map": str(jp.parent / f"donor-size-map-{date_str}.json"),
        },
        "knowledge": summarize_vpp(journal, dm),
    })
    if err:
        return {"ok": False, "error": err}
    return seal(rec, commit=commit, path=path, rd=rd, organ=owner, log_what="ретро-регистрация залива из журнала")


# ── авто-артефакт ЦИКЛ-1 ЯМ (эволюция: прошёл цикл → записан готовый ход) ─────────

def all_pass(results):
    """Истинный успех цикла: есть узлы и КАЖДЫЙ verdict=PASS (оборванный/FAIL — не ход)."""
    return bool(results) and all((r or {}).get("verdict") == "PASS" for r in results)


def register_cycle1(profile, results, *, commit=False, date_str=None, hsh=None,
                    artifacts=None, knowledge=None, ledger_path=None, path=None, rd=None):
    """Авто-артефакт закрытого ЦИКЛ-1 ЯМ (kind=cycle1). Эволюционный закон оператора:
    «когда система прошла цикл — она становится лучше ВСЕГДА: готовый записанный ход».

    Вызывает ДВИЖОК ymarket_cycle1_v1 ТОЛЬКО под своим гейтом (not dry AND commit, RUBICON)
    и register_cycle1 сам подтверждает all_pass(results): FAIL/оборванный прогон ходом НЕ
    становится (защита двойным гейтом — здесь и в движке). 0 сети; пишет ТОЛЬКО registry +
    читаемый .md (паттерн register_pour). Дедуп по id (seal): повторный цикл того же дня/магазина
    обновляет ход, НЕ плодит дубль.
    profile = ctx['profile'] (манифест магазина ЯМ), results = вердикты узлов, hsh = цикл-хеш.
    artifacts/knowledge — необязательные блоки от движка (куда смотреть / что узнали)."""
    if not profile:
        return {"ok": False, "error": "нет профиля магазина"}
    if not all_pass(results):
        got = sum(1 for r in results if (r or {}).get("verdict") == "PASS")
        return {"ok": False,
                "error": f"прогон НЕ все-PASS ({got}/{len(results)}) — ход не фиксируем"}
    date_str = date_str or time.strftime("%Y-%m-%d")
    slug = str(profile.get("slug") or "?")
    hsh = hsh or ""
    n = len(results)
    ms = {str((r or {}).get("node") or i): round((r or {}).get("ms") or 0)
          for i, r in enumerate(results, 1)}
    what = f"ЦИКЛ-1 {slug} {date_str}: {n}/{n} PASS"
    rec, err = normalize({
        "kind": "cycle1", "market": "ym",
        "category": profile.get("donor_category") or "",
        "date": date_str, "what": what,
        "owner": "CYCLE1",
        "params": {
            "store": slug,
            "business_id": profile.get("business_id"),
            "campaign_id": profile.get("campaign_id"),
            "warehouse_id": profile.get("warehouse_id"),
            "donor_category": profile.get("donor_category"),
            "builder": profile.get("builder"),
            "builder_slug": profile.get("builder_slug"),
            "markup": profile.get("markup"),
            "inherited_from": profile.get("_inherited_from"),
            "mode": "live", "nodes": n, "hash": hsh,
        },
        "decision": {
            "word": "живой --commit (RUBICON)",
            "via": "cycle1-engine",
            "note": "авто-сеал: цикл закрыт все-PASS по слову оператора на --commit",
        },
        "result": {
            "ok": True, "verdict": "PASS", "pass_n": n, "len": n,
            "hash": hsh, "node_ms": ms, "ledger": str(ledger_path or ""),
        },
        "artifacts": dict(artifacts or {}),
        "knowledge": dict(knowledge or {}),
    })
    if err:
        return {"ok": False, "error": err}
    return seal(rec, commit=commit, path=path, rd=rd, organ="CYCLE1",
                log_what=f"живой ход: ЦИКЛ-1 {slug} закрыт {n}/{n} PASS (hash {hsh})")


# ── CLI ───────────────────────────────────────────────────────────────────────────────

def _fmt(rec):
    ic = _ICON.get(rec.get("state"), "○")
    return (f"{ic} {rec['id']} · {rec['date']} · {rec['market']}/{rec['kind']} · "
            f"{rec.get('category') or '—'} · {rec.get('what', '')[:56]} · {rec['state']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="PROCESS ARTIFACT V1 — библиотека процессов (прогон-артефакт)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--register-pour", metavar="DATE", help="ретро-артефакт залива ВПП (напр. 2026-09-08)")
    g.add_argument("--show", metavar="PID", help="показать артефакт по хешу")
    g.add_argument("--confirm", metavar="PID", help="подтвердить — законно-окончен (оператор)")
    g.add_argument("--find", action="store_true", help="список артефактов (фильтры ниже)")
    ap.add_argument("--kind", help="фильтр find")
    ap.add_argument("--market", help="фильтр find")
    ap.add_argument("--category", help="фильтр find")
    ap.add_argument("--date", help="фильтр find")
    ap.add_argument("--commit", action="store_true", help="ЖИВОЙ режим: реально писать registry+отчёт")
    ap.add_argument("--task", metavar="T-ID", help="привязать к заданию доски (артефакт.task_id)")
    ap.add_argument("--what", help="свой заголовок (ретро)")
    a = ap.parse_args(argv)

    if a.register_pour:
        r = register_pour(a.register_pour, commit=a.commit, task_id=a.task or "", what=a.what)
        if not r.get("ok"):
            print("ОШИБКА:", r.get("error"))
            return 1
        if r.get("dry"):
            print("\n  НЕ записано (dry). Для записи: --commit")
        else:
            print(f"ЗАПИСАНО {r['id']} → {r.get('md')}")
        return 0
    if a.show:
        rec = show(a.show)
        if not rec:
            print(f"артефакта {a.show} нет в библиотеке")
            return 1
        print("\n".join(render_report(rec)))
        return 0
    if a.confirm:
        r = confirm(a.confirm, by="operator", commit=a.commit)
        if not r.get("ok"):
            print("ОШИБКА:", r.get("error"))
            return 1
        if r.get("dry"):
            print(f"СУХО · не записано (dry). Для записи: --commit")
        elif r.get("already"):
            print(f"{a.confirm} уже подтверждён")
        else:
            print(f"ПОДТВЕРЖДЕНО {a.confirm} → {r.get('md')}")
        return 0
    # find
    res = find(kind=a.kind, market=a.market, category=a.category, date=a.date)
    if not res:
        print("артефактов по срезу нет (библиотека процессов пуста?)")
        return 0
    for rec in res:
        print(_fmt(rec))
    print(f"─\nвсего: {len(res)}")
    return 0


if __name__ == "__main__":
    sys_exit = __import__("sys").exit
    sys_exit(main())

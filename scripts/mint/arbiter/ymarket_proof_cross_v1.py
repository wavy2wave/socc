#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""КРОСС-СВЕРКА «ДОКАЗАННО ЖИВЫХ» (ymarket_proof_cross_v1) — чтение леджера ЦИКЛ-1 по кабинетам.

ЗАЧЕМ. Оператор («сделай чтобы система законно не врала»): панели печатали «доказанно живых: 0»
из само-модели суточного цикла (ymarket_manager_state.json пуст → kpis() на пустом skus даёт 0),
хотя леджер ЦИКЛ-1 (ymarket_goods_library.json) уже содержит 4 карточки с last_verified=PASS —
их жизнь ДОКАЗАНА живым чтением СВЕРКИ. Числа жили в ДВУХ несвязанных источниках и кабинетах,
и «0» без подписи кабинета выглядел как общесистемная правда — ложь умолчанием.

ИСТОЧНИК ПРАВДЫ. «Доказанно живых» = карточка, чью жизнь на витрине доказал ЦИКЛ-1 СВЕРКОЙ:
goods в леджере с last_verified.verdict == PASS (200 OK врёт — PASS только после чтения). Это
число КАБИНЕТНОЕ: леджер хранит store_slug. Суточный журнал (ymarket_day_journal.jsonl) пишет
cards_live_verified СВОЕГО кабинета из само-модели — это ДРУГОЙ источник. Модуль их НЕ смешивает:
показывает леджер по кабинетам и, когда журнал суточного рисует «0», честно помечает, что это
само-модель СВОЕГО кабинета, а не леджер ЦИКЛ-1 — «0» не читается как общесистемное доказательство.

ЗАКОНЫ:
  PC1 нет числа без СВЕРКА-PASS: считаем только goods с last_verified.verdict==PASS (реальное
      чтение), ничего не выдумываем.
  PC2 кабинетная подпись: число живёт у store_slug леджера; известные кабинеты получают
      человеческое имя (тест «Атлас»), неизвестные — честно остаются под slug. Кабинеты не сливаются.
  PC3 журнал ≠ леджер: cards_live_verified журнала — само-модель суточного СВОЕГО кабинета;
      рендер добавляет разграничитель когда журнал рисует «0», чтобы «0» не читался как
      общесистемное доказательство.
  PC4 лёгкий деградад: файл не читается → «неизвестно (не читается)», не падаем и не выдумываем
      нули; леджер пуст → честное «0: ни одной СВЕРКА PASS» (это правда, не ложь).

Pure-read, 0₽, RUBICON цел: диск только читает (env YM_LIBRARY_PATH/YM_DAY_JOURNAL перекрывают
пути для герметичных приёмок), наружу не ходит, денег не трогает.
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOCC_ROOT = HERE.parents[2] if len(HERE.parents) > 2 else HERE
REPORTS = SOCC_ROOT / "MEMORY_WAVE/reports/mint/arbiter"

# Человеческие имена известных кабинетов (канон органа; леджер может нести и неизвестные slug).
STORE_NAMES = {
    "atlas-express-film": "тест «Атлас»",
    # боевой кабинет (biz 184481130) в леджере ЦИКЛ-1 пока не гонялся — строк нет, имя не выдумываем.
}


def library_path():
    p = os.environ.get("YM_LIBRARY_PATH")
    return Path(p) if p else (REPORTS / "ymarket_goods_library.json")


def journal_path():
    p = os.environ.get("YM_DAY_JOURNAL")
    return Path(p) if p else (REPORTS / "ymarket_day_journal.jsonl")


def load_library(doc=None):
    """Леджер ЦИКЛ-1 как dict. doc дан → используем как есть (герметично). Файл не читается →
    честный {} + load_error (PC4)."""
    if doc is not None:
        return doc
    p = library_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"load_error": f"{type(e).__name__}: {e}"}


def _is_pass(g):
    if not isinstance(g, dict):
        return False
    lv = g.get("last_verified")
    return isinstance(lv, dict) and lv.get("verdict") == "PASS"


def pass_goods(doc=None):
    """Goods, чью жизнь доказал ЦИКЛ-1 (last_verified PASS) — источник «доказанно живых» (PC1)."""
    doc = load_library(doc)
    if "load_error" in doc:
        return [], doc
    goods = doc.get("goods")
    items = list(goods.values()) if isinstance(goods, dict) else []
    return [g for g in items if _is_pass(g)], doc


def by_store(doc=None):
    """{store_slug: {"n": int, "latest": iso-or-None, "offer_ids": [...]}} по СВЕРКА-PASS (PC2)."""
    goods, doc = pass_goods(doc)
    out = {}
    for g in goods:
        slug = g.get("store_slug") or "?"
        lv = g.get("last_verified") or {}
        rec = out.setdefault(slug, {"n": 0, "latest": "", "offer_ids": []})
        rec["n"] += 1
        ts = lv.get("ts") or ""
        if ts and ts > rec["latest"]:
            rec["latest"] = ts
        if g.get("offer_id"):
            rec["offer_ids"].append(g["offer_id"])
    for rec in out.values():
        rec["latest"] = rec["latest"] or None
    return out, doc


def _read_journal_rows(path=None):
    p = Path(path) if path else journal_path()
    if not p.exists():
        return []
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def journal_verified_last(journal_rows=None):
    """cards_live_verified последней строки журнала суточного (само-модель). Нет/не число → None."""
    rows = _read_journal_rows() if journal_rows is None else (journal_rows or [])
    last = rows[-1] if rows else {}
    if not isinstance(last, dict):
        return None
    v = (last.get("kpis") or {}).get("cards_live_verified")
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def store_label(slug):
    """Человеческое имя кабинета; неизвестный slug честно остаётся собой (PC2)."""
    return STORE_NAMES.get(slug, slug)


def render(journal_rows=None, library_doc=None):
    """Честный кросс-блок «доказанно живых» (всегда правдивая строка; None не возвращает).

    Показывает леджер ЦИКЛ-1 по кабинетам (или «0: леджер пуст», если ни одной СВЕРКА PASS).
    Когда суточный журнал в последней строке рисует «0» — добавляет разграничитель (PC3):
    это само-модель СВОЕГО кабинета, не леджер ЦИКЛ-1; числа не складываются.
    """
    by, doc = by_store(library_doc)
    journal_v = journal_verified_last(journal_rows)
    load_err = doc.get("load_error") if isinstance(doc, dict) else None

    L = []
    total = sum(r["n"] for r in by.values())
    if total:
        L.append(f"доказанно живых по леджеру ЦИКЛ-1 (СВЕРКА PASS): {total}")
        for slug in sorted(by):
            r = by[slug]
            name = store_label(slug)
            if slug == "?":
                who = "(без store_slug)"
            else:
                who = f"{name} ({slug})" if slug != name else name
            tail = f" · последняя PASS {r['latest']}" if r["latest"] else ""
            L.append(f"  • {who}: {r['n']}{tail}")
    elif load_err:
        L.append(f"доказанно живых: НЕИЗВЕСТНО — леджер ЦИКЛ-1 не читается ({load_err})")
    else:
        L.append("доказанно живых: 0 — леджер ЦИКЛ-1 пуст (ни одной СВЕРКА PASS)")
    if journal_v is not None and int(journal_v) == 0:
        L.append("суточный журнал рисует 0 — само-модель СВОЕГО кабинета, не леджер ЦИКЛ-1; "
                 "кабинеты не складываются")
    return "\n".join(L)


if __name__ == "__main__":
    # Сухая демонстрация (0₽): читает реальные сторы, печатает кросс-блок.
    import datetime as _dt
    print("КРОСС-СВЕРКА «доказанно живых» — снимок",
          _dt.datetime.now(_dt.timezone.utc).isoformat()[:19], "UTC")
    print(render())
    raise SystemExit(0)

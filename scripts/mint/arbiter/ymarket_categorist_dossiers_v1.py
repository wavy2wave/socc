#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ЯМ · ДОСЬЕ ДОНОР-КАТЕГОРИЙ (ymarket_categorist_dossiers_v1.py).

Свёрнутый переиспользуемый слой «сделанной работы» КАТЕГОРИЙЩИКА над immutable-артефактами
прогонов. Принцип оператора 04.09: «пусть всё важное созданное превращается в артефакты — в любой
момент можем использовать сделанную работу». Канон-стор: MEMORY_WAVE/reports/mint/arbiter/
ymarket_categorist_dossiers.json (+ .md — человеческое зеркало, пересобирается из JSON).

Правит ли орган? Нет. Это read-слой + чистые хелперы мержа; канон меняется ТОЛЬКО явным save()
(атомарно os.replace, .md-зеркало пересобирается) — вызывать его должны будущие шаги-писатели
(прогон категорийщика после вердикта), а не чтение. ВСЕГДА под env-песочницей в тестах.

Законы D:
  D1  честность_маппинга — need_mapping=false ⇒ market_category_id НЕ null (и наоборот: true ⇒ null);
      id не выдумываем, подтверждение живёт в ymarket_cats_v1.json (досье только ссылается).
  D2  вердикт_из_первоисточника — scan берётся из артефактов прогона (readiness/цифры), не из головы;
      категория без прогона = scan:null, никогда не «непроверенная как готовая».
  D3  зеркало_детерминировано — .md пересобирается render() из JSON: байт-в-байт на повторном save.
  D4  read_не_пишет — чтение/рендер/валидация не трогают стор (0₽, канон цел).
Env: YM_DOSSIERS_PATH перекрывает путь канона (песочница/тесты не пишут в боевой стор).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ── пути ───────────────────────────────────────────────────────────────────────
def _reports_root() -> Path:
    """Корень SOCC по маркеру MEMORY_WAVE — как ymarket_tasks_v1. Репо-корень (.git) с
    MEMORY_WAVE = канон: вложенная сирота scripts/MEMORY_WAVE НЕ затеняет SOCC/MEMORY_WAVE."""
    here = Path(__file__).resolve().parent
    for anc in (here, *here.parents):
        if (anc / ".git").is_dir() and (anc / "MEMORY_WAVE").is_dir():
            return anc
    for anc in (here, *here.parents):
        if (anc / "MEMORY_WAVE").is_dir():
            return anc
    return here.parent.parent.parent


REPORTS = _reports_root() / "MEMORY_WAVE/reports/mint/arbiter"


def dossier_path() -> Path:
    """Путь к JSON-канону досье. env YM_DOSSIERS_PATH перекрывает (песочница/тесты)."""
    p = os.environ.get("YM_DOSSIERS_PATH")
    return Path(p) if p else (REPORTS / "ymarket_categorist_dossiers.json")


def md_path() -> Path:
    """Человеческое зеркало .md — рядом с JSON, пересобирается из него."""
    return dossier_path().with_suffix(".md")


SCHEMA = "ymarket.categorist.dossiers.v1"
VERDICTS = {"ready_shortlist", "empty_negative", "needs_data", "blocked"}


# ── чистая модель (без записи) ────────────────────────────────────────────────
def get(dossier, slug):
    """Запись категории или None."""
    return (dossier or {}).get("categories", {}).get(slug)


def stats(dossier):
    """Сводка: категорий · done/open · просканировано · need_mapping · подтверждённых id."""
    cats = (dossier or {}).get("categories", {}) or {}
    entries = list(cats.values())
    return {
        "categories": len(entries),
        "done": sum(1 for e in entries if e.get("state") == "done"),
        "open": sum(1 for e in entries if e.get("state") != "done"),
        "scanned": sum(1 for e in entries if e.get("scan")),
        "need_mapping": sum(1 for e in entries if e.get("mapping", {}).get("need_mapping")),
        "confirmed": sum(1 for e in entries
                         if e.get("mapping", {}).get("market_category_id") is not None),
    }


def validate(dossier):
    """(ok, errors). D1/D2: категории валидны, маппинг честен, вердикт/цифры известных."""
    errors = []
    if not isinstance(dossier, dict):
        return False, ["досье не dict"]
    if dossier.get("schema") != SCHEMA:
        errors.append(f"schema: {dossier.get('schema')!r} ≠ {SCHEMA!r}")
    cats = dossier.get("categories")
    if not isinstance(cats, dict) or not cats:
        errors.append("categories пуст/не dict")
        return not errors, errors
    for slug, e in cats.items():
        if not isinstance(e, dict):
            errors.append(f"{slug}: не запись")
            continue
        if e.get("donor_category", slug) != slug:
            errors.append(f"{slug}: donor_category≠ключ")
        m = e.get("mapping") or {}
        nm, cid = m.get("need_mapping"), m.get("market_category_id")
        if nm is False and cid is None:
            errors.append(f"{slug}: need_mapping=false но market_category_id=null (D1)")
        if nm is True and cid is not None:
            errors.append(f"{slug}: need_mapping=true но market_category_id задан (D1)")
        sc = e.get("scan")
        if sc is not None:
            v = sc.get("verdict")
            if v not in VERDICTS:
                errors.append(f"{slug}: scan.verdict {v!r} вне {{VERDICTS}}")
            if sc.get("artifacts") is not None and not isinstance(sc.get("artifacts"), list):
                errors.append(f"{slug}: scan.artifacts не список")
    return not errors, errors


def upsert(dossier, slug, entry):
    """Чистый мерж: вернуть НОВЫЙ dossier с записью slug = entry. Вход НЕ мутируется — копируется
    и dossier, и entry (иначе record_scan по ссылке пишет scan в ОРИГИНАЛЬНУЮ запись канона)."""
    import copy
    out = copy.deepcopy(dossier or {})
    cats = out.setdefault("categories", {})
    cats[slug] = copy.deepcopy(entry or {})
    return out


def record_scan(dossier, slug, scan_block, *, keep_history=True):
    """Чистый мерж вердикта прогона: scan → scan.scan, прежний scan → scan_history (если был)."""
    import copy
    out = upsert(dossier, slug, get(dossier, slug) or {})
    entry = out["categories"][slug]
    prev = entry.get("scan")
    if prev is not None and keep_history:
        history = entry.setdefault("scan_history", [])
        history.append(prev)
    entry["scan"] = copy.deepcopy(scan_block)
    return out


# ── ввод/вывод ────────────────────────────────────────────────────────────────
def load(path=None):
    """(dossier|None, err|None). fail-soft: файла нет/битый → (None, причина) (D4)."""
    p = Path(path) if path else dossier_path()
    if not p.exists():
        return None, f"стора нет: {p}"
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        return None, f"битый стор: {e}"
    return d, None


def _render_one(e, slug) -> list:
    m = e.get("mapping") or {}
    cid = m.get("market_category_id")
    lines = [
        f"## {slug} — {e.get('title_ru') or '?'}",
        f"- задача {e.get('task_id')} · состояние {e.get('state')} · prio {e.get('priority')}",
        f"- маппинг ЯМ: need_mapping={str(m.get('need_mapping'))} · "
        f"id={cid if cid is not None else 'null (None ≠ 0)'}"
        + (f" · confirmed {m.get('confirmed')}" if m.get("confirmed") else "")
        + (f" · hint_rules: {m.get('hint_rules')}" if m.get("hint_rules") else ""),
    ]
    sc = e.get("scan")
    if not sc:
        lines.append("- скан: ещё НЕ прогонялась (scan:null — честно)")
        return lines
    r = sc.get("readiness") or {}
    lines.append(f"- скан {sc.get('when')} · dry={sc.get('dry')} · RUBICON: {sc.get('rubicon')}")
    for a in sc.get("artifacts") or []:
        lines.append(f"  - первоисточник: {a}")
    lines.append(f"- вердикт: {sc.get('verdict')} — {sc.get('verdict_text')}")
    if r:
        compact = " · ".join(f"{k}={v}" for k, v in r.items())
        lines.append(f"  readiness: {compact}")
    for sl in sc.get("shortlist") or []:
        lines.append(f"  - ready {sl.get('sku')}: {sl.get('title')} · продать {sl.get('sell_rub')}₽ · "
                     f"ОВХ {sl.get('parcel_cm')} · {sl.get('kg')} кг · barcode {sl.get('barcode')}")
    island = sc.get("island")
    if island:
        lines.append(f"  остров: {island.get('title')} — skus {island.get('skus')} · "
                     f"гейт: {island.get('gate')}")
    oq = e.get("open_operator_decision")
    if oq:
        lines.append(f"- вопрос оператору: {oq}")
    return lines


def render(dossier, slug=None):
    """Детерминированный markdown-рендер (0₽, D3/D4). slug=None → весь канон."""
    st = stats(dossier)
    head = [
        f"# ДОСЬЕ ДОНОР-КАТЕГОРИЙ · {dossier.get('schema')}",
        "",
        f"{dossier.get('purpose')}",
        "",
        f"Очередь: {dossier.get('store')} · категорий {st['categories']} · "
        f"done {st['done']} · open {st['open']} · просканировано {st['scanned']} · "
        f"need_mapping {st['need_mapping']} · подтверждено id {st['confirmed']}",
    ]
    cats = dossier.get("categories", {}) or {}
    if slug:
        e = cats.get(slug)
        return head + (["", "⚠ категория не в досье"] if e is None else ["", *_render_one(e, slug)])
    order = sorted(cats.items(), key=lambda kv: (kv[1].get("state") != "done", kv[1].get("priority", 99), kv[0]))
    body = []
    for s, e in order:
        body += [""] + _render_one(e, s)
    lessons = dossier.get("lessons") or []
    if lessons:
        body.append("")
        body.append("## Уроки (переиспользуемые)")
        for l in lessons:
            body.append(f"- **{l.get('id')}**: {l.get('finding')} "
                        f"({l.get('evidence')}) → {l.get('rule')}")
    return head + body


def save(dossier, path=None, *, write_md=True):
    """Атомарная запись канона + пересборка .md-зеркала. RESULT {ok, categories, path, md}. D3."""
    p = Path(path) if path else dossier_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp = p.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dossier, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, p)
        md = None
        if write_md and p.suffix == ".json":
            mp = p.with_suffix(".md")
            body = "\n".join(render(dossier)) + "\n"
            with open(mp, "w", encoding="utf-8") as f:
                f.write(body)
            md = str(mp)
        return {"ok": True, "categories": len((dossier or {}).get("categories", {}) or {}),
                "path": str(p), "md": md}
    except Exception as e:
        return {"ok": False, "path": str(p), "error": str(e)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Досье донор-категорий: read-рендер (0₽).")
    ap.add_argument("--slug", help="только одна категория")
    ap.add_argument("--json", action="store_true", help="вывести JSON целиком")
    a = ap.parse_args()
    d, err = load()
    if err:
        print(f"⚠ {err}")
        sys.exit(1)
    ok, verr = validate(d)
    if not ok:
        print("⚠ невалидно:")
        for e in verr:
            print("  -", e)
    if a.json:
        json.dump(d, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        sys.stdout.write("\n".join(render(d, slug=a.slug)) + "\n")
    sys.exit(0 if ok else 2)

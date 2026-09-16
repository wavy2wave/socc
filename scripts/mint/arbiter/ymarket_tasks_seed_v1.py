#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СИДЕР РЕЕСТРА ЗАДАНИЙ — КАТЕГОРИИ ДОНОРА (ymarket_tasks_seed_v1.py).

ПЕРВАЯ ЦЕЛЬ (слова оператора 03.09): для ЦИКЛ-1 задания на парсинг категорий из
сайта cargo-avto.ru — «как задания со своими хешами», «кто делает и для кого».
Дополняет ЦИКЛ-ДЕНЬ (ymarket_cycle_day_v1), который формирует задания ИЗ ЖИВЫХ
НАБЛЮДЕНИЙ (переценки PRICER и пр.) — этот сидер формирует ЗАДАННЫЙ БЭКЛОГ категорий
из решения оператора «13 упаковочных (рекомендую)». Идемпотентен как form() цикла-дня:
то же намерение → тот же TZ1-хеш → дубль не создаём.

МАППИНГ-ЧЕСТНОСТЬ: из 13 донор-категорий готовый профиль ЯМ (ymarket_cats_v1) есть
только у vozdushno-puzyrkovaya-plenka → puzyrkovaya-plenka (живой магазин плёнки).
Остальные 12 несут refs.need_mapping=True — решить профиль категории ДО карточки,
не выдумываем (закон «None ≠ 0»).

ДИСЦИПЛИНА: --commit НЕ передаём без нужды — по умолчанию dry, ничего не пишет.
Единственный write = локальный реестр заданий SOCC/MEMORY_WAVE (0₽, НЕ рука ЯМ) —
под правило цикла-дня CD6, RUBICON-слово не требуется (нет живой записи наружу).

  python3 ymarket_tasks_seed_v1.py            # dry: что сформировалось бы
  python3 ymarket_tasks_seed_v1.py --commit   # записать в канон-реестр
  python3 ymarket_tasks_seed_v1.py --readback # показать, что лежит в каноне сейчас
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ymarket_tasks_v1 as T  # noqa: E402

# Канонический стор заданий (тот же якорь, что читает консоль/мозг/цикл-день).
CANON = T.task_path()
# Историческая сирота (конвергенция 02.09): 2 живых PRICER-задания, написанные
# cycle_day ДО смены корня, когда _reports_root резолвился в scripts/memory_wave.
# Кода, читающего сироту, НЕТ — мигрируем записи verbatim в канон, файл не трогаем.
ORPHAN = HERE.parent.parent / "memory_wave" / "reports" / "mint" / "arbiter" / "ymarket_tasks.json"

DONOR_SITE = "shop.cargo-avto.ru"

# ── 13 упаковочных категорий донора (одобрены оператором 03.09) ─────────────────
# Приоритет: меньше = важнее. Первая пятёрка — «плёночный профит» (знакомый профиль),
# дальше коробочно-защитное, дальше расходники. urgency: high только там, где уже
# есть живой профиль/ожидаемая маржа (остальные честно normal — парсинг, не залив).
SEED = [
    # slug, RU-имя, priority, urgency, market_cat (известен|None)
    ("vozdushno-puzyrkovaya-plenka", "воздушно-пузырьковая плёнка", 30, "high", "puzyrkovaya-plenka"),
    ("polyetilenovaya-plenka", "полиэтиленовая плёнка", 30, "high", None),
    ("streich-plenka", "стрейч-плёнка", 40, "high", None),
    ("vspenennii-polietilen", "вспененный полиэтилен", 40, "high", None),
    ("kartonnye-tubusy", "картонные тубусы", 40, "normal", None),
    ("karton-i-gofrokarton", "картон и гофрокартон", 40, "normal", None),
    ("klejkaya-lenta", "клейкая лента", 50, "normal", None),
    ("meshki", "мешки", 50, "normal", None),
    ("paketi", "пакеты", 50, "normal", None),
    ("upakovochnaya-bumaga", "упаковочная бумага", 50, "normal", None),
    ("napolniteli", "наполнители", 50, "normal", None),
    ("upakovochnaya-setka", "упаковочная сетка", 60, "normal", None),
    ("upakovochnie-lentj", "упаковочные ленты", 60, "normal", None),
]


def _candidate(slug, ru, priority, urgency, market_cat):
    need_map = market_cat is None
    what = f"Парсинг донора: {ru} ({slug}) → шорт-лист под Экспресс"
    refs = {
        "donor_category": slug,
        "donor_site": DONOR_SITE,
        "market_cat": market_cat,
        "need_mapping": need_map,
        "method": f"CargoAvtoAdapter.scan(category={slug!r})",
        "approved": "operator 03.09 (13 упаковочных)",
    }
    body = (
        f"Задание на живой парсинг донор-категории «{slug}» с {DONOR_SITE} (1С-Битрикс). "
        f"Исполнитель — КАТЕГОРИЙЩИК (ymarket_role_categorist_v1): скан → нормализация → "
        f"фильтр под Экспресс (закупка×markup ≤ потолок, габариты под ОВХ) → артефакт-шорт-лист "
        f"кандидатов. Маппинг категории ЯМ: "
        f"{market_cat or ('НЕТ — need_mapping: решить профиль категории ДО карточки (None ≠ 0)')}. "
        f"Стоимость: 0₽ (только GET донора)."
    )
    steps = [
        {"id": "s1", "title": f"Живой скан донор-категории {slug} (0₽ GET)"},
        {"id": "s2", "title": "Фильтр под Экспресс: закупка×markup ≤ потолок, габариты/ОВХ"},
        {"id": "s3", "title": f"Артефакт: шорт-лист кандидатов + вердикт маппинга ЯМ"
                              f" ({market_cat or 'need_mapping'})"},
    ]
    return dict(what=what, owner="CATEGORIST", category="categories", market="ym",
                cycle="cycle1", store="atlas-express-film", urgency=urgency,
                priority=priority, body=body, source="operator", refs=refs, steps=steps)


def _load_canon():
    """Канон-реестр: список записей. Нет файла → [] (честно, как T.load)."""
    tasks, err = T.load()
    return tasks or []


def _orphan_records():
    """Сиротские PRICER-записи verbatim (id сохраняем — TZ1-стабильность). Битый файл → [] + честный лог."""
    p = Path(ORPHAN)
    if not p.exists():
        return [], f"сирота не найдена: {p}"
    try:
        data = p.read_text()
        tasks = (json.loads(data) or {}).get("tasks")
    except Exception as e:
        return [], f"сирота битая: {type(e).__name__}: {e}"
    if isinstance(tasks, dict):
        tasks = list(tasks.values())
    return [t for t in (tasks or []) if isinstance(t, dict) and t.get("id")], None


def seed(*, commit=False, migrate_orphans=True, save_path=None):
    """Прогнать: миграция сироты + кандидаты SEED; существующие по TZ1-дедупу пропустить.

    commit=True: единственный write = локальный реестр заданий (0₽). Иначе ничего не пишет.
    Возвращает (summary-dict, lines)."""
    lines = []
    existing = _load_canon()
    existing_ids = {t.get("id") for t in existing if t.get("id")}

    migrated, mig_err = [], None
    if migrate_orphans:
        orphan_recs, mig_err = _orphan_records()
        for rec in orphan_recs:
            tid = rec.get("id")
            if tid in existing_ids:
                continue
            existing.append(rec)
            existing_ids.add(tid)
            migrated.append(tid)
        if migrated:
            lines.append(f"миграция сироты · перенесено в канон: {len(migrated)} "
                         f"({', '.join(migrated)}) · код сироту не читает — записи были невидимы")
        elif mig_err:
            lines.append(f"миграция сироты · {mig_err} (не критично: новых категорий-заданий это не трогает)")
        else:
            lines.append("миграция сироты · в каноне уже есть, дубля нет")

    # кандидаты SEED → фабрика (валидирует сама), дедуп по TZ1
    seen = set()
    fresh, dup, errs = [], [], []
    for slug, ru, priority, urgency, market_cat in SEED:
        c = _candidate(slug, ru, priority, urgency, market_cat)
        tid = T.task_id(c["market"], c["cycle"], c["category"], c["store"], c["what"],
                        c["owner"], c["urgency"])
        if tid in existing_ids or tid in seen:
            dup.append(slug)
            continue
        seen.add(tid)
        task, err = T.new_task(**c)
        if err:
            errs.append(f"{slug}: {err}")
        elif task:
            fresh.append(task)

    created = []
    if commit and (fresh or migrated):
        merged = existing  # сирота уже добавлена выше; добавляем fresh
        for task in fresh:
            merged.append(task)
            created.append(task.get("id"))
        if created or migrated:
            r = T.save(merged, path=save_path)
            lines.append(f"seed --commit · записано {len(created)} новых категорий-заданий"
                         f" + {len(migrated)} мигрированных · {r.get('ok') and 'ok' or r.get('error')}"
                         f" · {r.get('path')}")
    elif not commit:
        lines.append("seed · dry — commit не передан, НИЧЕГО не пишу (0₽)")

    lines.append(f"seed · категорий-заданий: {len(SEED)} · новых: {len(fresh)}"
                 f" · уже в реестре: {len(dup)}" + (f" · ошибок фабрики: {len(errs)}" if errs else ""))
    for t in fresh:
        lines.append(f"  + {t['id']} {t['what']} · prio{t['priority']} {t['urgency']}"
                     f" · need_mapping={t['refs'].get('need_mapping')}")
    for slug in dup:
        lines.append(f"  = (уже есть) {slug}")
    for e in errs:
        lines.append(f"  ! {e}")
    return {"ok": not errs, "new": len(fresh), "dup": len(dup),
            "migrated": len(migrated), "errs": errs}, lines


def readback():
    """Показать, что лежит в каноне сейчас (read-only, 0₽)."""
    tasks = _load_canon()
    lines = [f"канон-реестр: {CANON}", f"записей: {len(tasks)}",
             f"стор существует: {CANON.exists()}"]
    if tasks:
        open_ = T.open_only(tasks)
        lines.append(f"открытых: {len(open_)}")
        if open_:
            lines.extend(l for l in T.render_plannerka(T.sort_tasks(open_)))
    else:
        lines.append("(реестр пуст)")
    return lines


def _main(argv):
    commit = "--commit" in argv
    read = "--readback" in argv
    lines = []
    if read:
        lines = readback()
    else:
        summary, lines = seed(commit=commit)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))

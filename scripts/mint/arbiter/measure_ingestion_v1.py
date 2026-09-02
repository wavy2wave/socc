#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Замер сквозного прохода: парсер → карточка. Классифицирует каждый отказ.

ЦЕЛЬ (оператор 2026-08-06): "УСПЕШНО ЗАЛИВАТЬ ТОВАРЫ, с любого сайта, так чтобы не было ошибок".
Рейтинг 80+ достаточен, главное — нулевой отказ на сборке.
"""
import sys
import glob
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
for p in (str(HERE), str(HERE.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from ymarket_from_xlsx_v1 import load_category
from ymarket_card_v1 import to_offer, CardError


def measure_all(pattern="/Users/wavysexy/parsers/parsed_data/*.xlsx"):
    """Все XLSX → статистика прохода parse+build. Честная классификация отказов."""
    files = sorted(glob.glob(pattern))
    stats = {
        "files_total": len(files),
        "files_read": 0,
        "files_blocked": 0,
        "rows_parsed": 0,
        "rows_skipped_parse": 0,
        "offers_built": 0,
        "offers_failed": 0,
    }
    parse_blockers = {}
    skip_classes = defaultdict(int)
    build_failures = defaultdict(lambda: {"count": 0, "examples": []})

    for fpath in files:
        fname = Path(fpath).name
        if fname.startswith("~$"):
            continue
        try:
            rep = load_category(fpath)
        except Exception as e:
            stats["files_blocked"] += 1
            key = f"{type(e).__name__}: {str(e)[:60]}"
            parse_blockers[fname] = key
            continue

        prods = rep.get("products") or []
        skipped = rep.get("skipped", 0)
        blocker = rep.get("blocker")

        stats["files_read"] += 1
        stats["rows_parsed"] += len(prods)
        stats["rows_skipped_parse"] += skipped

        if blocker:
            stats["files_blocked"] += 1
            parse_blockers[fname] = blocker[:200]

        for why, det in (rep.get("skip_reasons") or {}).items():
            skip_classes[why] += det.get("строк", 0)

        # Второй рубеж: сборка карточки
        for prod in prods:
            try:
                to_offer(prod, slug=prod.get("slug"))
                stats["offers_built"] += 1
            except CardError as e:
                stats["offers_failed"] += 1
                key = str(e)[:120]
                slot = build_failures[key]
                slot["count"] += 1
                if len(slot["examples"]) < 3:
                    slot["examples"].append(prod.get("sku", "?"))
            except Exception as e:
                stats["offers_failed"] += 1
                key = f"{type(e).__name__}: {str(e)[:100]}"
                slot = build_failures[key]
                slot["count"] += 1
                if len(slot["examples"]) < 3:
                    slot["examples"].append(prod.get("sku", "?"))

    return {
        "stats": stats,
        "parse_blockers": parse_blockers,
        "skip_classes": dict(skip_classes),
        "build_failures": dict(build_failures),
    }


def report(result):
    """Честный отчёт с классами отказов."""
    s = result["stats"]
    print("=" * 70)
    print("ЗАМЕР ИНГЕСТА (парсер → карточка)")
    print("=" * 70)
    print(f"Файлов: {s['files_total']} (прочитано {s['files_read']}, заблокировано {s['files_blocked']})")
    print(f"Строк: {s['rows_parsed']} разобрано, {s['rows_skipped_parse']} пропущено")
    print()
    print(f"КАРТОЧЕК СОБРАНО: {s['offers_built']}")
    print(f"ОТКАЗОВ СБОРКИ:   {s['offers_failed']}")
    pass_rate = 100.0 * s["offers_built"] / (s["offers_built"] + s["offers_failed"]) if (s["offers_built"] + s["offers_failed"]) > 0 else 0
    print(f"PASS RATE:        {pass_rate:.1f}%")
    print()

    if result["parse_blockers"]:
        print("─" * 70)
        print("ФАЙЛЫ-БЛОКЕРЫ (парсер не читает)")
        print("─" * 70)
        for fname, why in sorted(result["parse_blockers"].items())[:10]:
            print(f"  {fname}")
            print(f"    → {why}")
        if len(result["parse_blockers"]) > 10:
            print(f"  ... ещё {len(result['parse_blockers']) - 10}")
        print()

    if result["skip_classes"]:
        print("─" * 70)
        print("КЛАССЫ ПРОПУЩЕННЫХ СТРОК (разбор)")
        print("─" * 70)
        for why, cnt in sorted(result["skip_classes"].items(), key=lambda x: -x[1])[:10]:
            print(f"  {cnt:>5} стр. | {why}")
        print()

    if result["build_failures"]:
        print("─" * 70)
        print("КЛАССЫ ОТКАЗОВ СБОРКИ КАРТОЧКИ")
        print("─" * 70)
        for err, det in sorted(result["build_failures"].items(), key=lambda x: -x[1]["count"])[:15]:
            ex = ", ".join(det["examples"])
            print(f"  {det['count']:>5} | {err}")
            print(f"        примеры: {ex}")
        print()

    print("=" * 70)
    goal = "✅ ЦЕЛЬ ДОСТИГНУТА" if pass_rate >= 99.0 else f"❌ ДО ЦЕЛИ: {100.0 - pass_rate:.1f}% отказов"
    print(goal)
    print("=" * 70)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Замер ингеста: parse+build, с классами отказов")
    ap.add_argument("--pattern", default="/Users/wavysexy/parsers/parsed_data/*.xlsx")
    args = ap.parse_args()

    result = measure_all(args.pattern)
    report(result)

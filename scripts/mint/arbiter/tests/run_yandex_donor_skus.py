#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА ЯНДЕКС — ТОЧЕЧНЫЙ РЕМОНТ ПО SKU (0₽, без сети, без ключа, без openpyxl).

Страж живого инцидента 2026-08-25: первый RUBICON-залив лёг 5 карточками с ошибкой «Бренд»
(9600167, 9601478, 9601551, 9601575, 9601591). При ПОВТОРНОЙ сборке топ-5 «плавал» — 9600167
выпал из топа, вместо него всплыл 9600132. Повтор `--limit 5` создал бы ДУБЛЬ (9600132) и
ОСИРОТИЛ бы ошибочную 9600167 → нарушение закона «ни один товар не должен быть с ошибкой».

Починка = флаг skus: тянем ПОЛНЫЙ шорт-лист и берём ровно указанные SKU, ИГНОРИРУЯ limit.
Тут доказываем ровно это поведение, замокав categorist.shortlist (чистая логика, 3.13-совместимо):
  S1 limit_ignored     — при заданных skus шорт-лист тянется с limit=10**6, НЕ с --limit.
  S2 exact_selection   — в залив идут РОВНО запрошенные SKU (не топ-N ранга).
  S3 missing_surfaced  — запрошенный, но отсутствующий в шорт-листе SKU честно попадает в skus_missing.
  S4 no_skus_backcompat— без skus поведение прежнее: шорт-лист тянется с --limit (обратная совместимость).
  S5 empty_blocks_commit — skus ни с чем не совпали → --commit ЧЕСТНО заблокирован ДО сети (0 POST).
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_runner_v1 as runner    # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))


def _row(sku):
    """Синтетическая строка шорт-листа КАТЕГОРИЙЩИКА (как отдал бы score_item) — короб, готовый к dry."""
    return {"sku": sku, "name": f"Короб картонный {sku} 330х230х230", "proposed_low": 300.0,
            "slug": "kartonnye-koroba", "category_id": 76296786,
            "pictures": ["https://cdn.example/box.jpg"], "description": "Прочный короб",
            "length": 33.0, "width": 23.0, "height": 23.0, "weight": 0.276,
            "_spec": {"length": 33.0, "width": 23.0, "height": 23.0, "weight": 0.276,
                      "материал": "гофрокартон", "слои_картона": "Трехслойный"}}


FULL = ["S1", "S2", "S3", "S4", "S5"]
_captured = {}


def _install_fake_shortlist():
    """Замокать categorist.shortlist: ловим, с каким limit позвали; отдаём фиксированный шорт-лист."""
    def fake(xlsx, city=None, max_cost=None, markup_lo=None, markup_hi=None, limit=None, slug=None):
        _captured["limit"] = limit
        return {"file": "SYNTH.xlsx", "sheet": "Лист1", "colmap": {"Цена": "cost"}, "blocker": None,
                "agg": {"rows_read": 210, "selected": len(FULL), "needs_data": 0, "rejected": 0},
                "shortlist": [_row(s) for s in FULL]}
    runner.categorist.shortlist = fake


print("ПРИЁМКА ЯНДЕКС — ТОЧЕЧНЫЙ РЕМОНТ ПО SKU\n")

_save = runner.categorist.shortlist
try:
    _install_fake_shortlist()

    # ── S1 + S2: skus заданы → полный шорт-лист (limit игнорирован), в залив ровно запрошенные ──
    print("S1/S2 · skus → тянем ПОЛНЫЙ шорт-лист, берём РОВНО запрошенные (limit проигнорирован)")
    _captured.clear()
    rep = runner.run_donor("SYNTH.xlsx", slug="kartonnye-koroba", skus=["S2", "S4"], limit=1,
                           commit=False, write_report=False)
    check("S1: шорт-лист тянут с limit=10**6, НЕ с --limit=1 (иначе SKU выпал бы из топа)",
          _captured.get("limit") == 10 ** 6, f"limit={_captured.get('limit')}")
    got = {r["sku"] for r in rep["preflight_rows"]}
    check("S2: в залив идут РОВНО {S2,S4} (не топ-N ранга)", got == {"S2", "S4"}, str(got))
    check("S2: preflight.total == 2", rep["preflight"]["total"] == 2, str(rep["preflight"]["total"]))
    check("S2: skus_requested отражён в отчёте", rep.get("skus_requested") == ["S2", "S4"],
          str(rep.get("skus_requested")))
    check("S2: skus_missing пуст (оба нашлись)", rep.get("skus_missing") == [], str(rep.get("skus_missing")))
    # бренд-этаж жив и на точечном пути (тот же shortlist_to_prod)
    check("S2: карточки всё ещё собираются без ошибок (бренд-этаж цел)",
          rep["preflight"]["build_error"] == 0, str(rep["preflight"]["build_error"]))

    # ── S3: запрошен отсутствующий SKU → честно в skus_missing, живые всё равно берутся ──
    print("\nS3 · отсутствующий SKU честно попадает в skus_missing, не роняя остальные")
    rep2 = runner.run_donor("SYNTH.xlsx", slug="kartonnye-koroba", skus=["S2", "NOPE-404"],
                            commit=False, write_report=False)
    got2 = {r["sku"] for r in rep2["preflight_rows"]}
    check("S3: взят существующий S2", got2 == {"S2"}, str(got2))
    check("S3: NOPE-404 честно в skus_missing", rep2.get("skus_missing") == ["NOPE-404"],
          str(rep2.get("skus_missing")))

    # ── S4: без skus — прежнее поведение, шорт-лист тянется с --limit (обратная совместимость) ──
    print("\nS4 · без skus — limit работает как раньше (обратная совместимость)")
    _captured.clear()
    rep3 = runner.run_donor("SYNTH.xlsx", slug="kartonnye-koroba", limit=3, commit=False,
                            write_report=False)
    check("S4: шорт-лист тянут с limit=3 (skus не заданы)", _captured.get("limit") == 3,
          f"limit={_captured.get('limit')}")
    check("S4: skus_requested=None (режим ремонта не включён)", rep3.get("skus_requested") is None,
          str(rep3.get("skus_requested")))

    # ── S5: skus ни с чем не совпали + --commit → честный блок ДО сети (ни одного POST) ──
    print("\nS5 · skus без совпадений + --commit → честный блок (RUBICON: наружу ничего)")
    posted = {"n": 0}
    _save_pub = runner.write.publish_card
    try:
        # если гейт «нет товаров» не сработает — этот шпион поймает реальную попытку залить
        def _spy(*a, **k):
            if not k.get("dry", False):
                posted["n"] += 1
            return {"ok": True, "dry": k.get("dry", False), "create_card": {"errors": []}}
        runner.write.publish_card = _spy
        rep4 = runner.run_donor("SYNTH.xlsx", slug="kartonnye-koroba", skus=["GHOST-1"],
                                commit=True, write_report=False)
        check("S5: --commit заблокирован (нет товаров под залив)",
              bool(rep4.get("commit_blocked")) and not rep4.get("committed"),
              str(rep4.get("commit_blocked")))
        check("S5: НИ ОДНОГО реального залива наружу (RUBICON цел)", posted["n"] == 0,
              f"posted={posted['n']}")
    finally:
        runner.write.publish_card = _save_pub
finally:
    runner.categorist.shortlist = _save

# ============================================================================
# ИТОГ
# ============================================================================
print("\n" + "=" * 70)
print(f"ЯНДЕКС ТОЧЕЧНЫЙ РЕМОНТ ПО SKU: {len(PASS)}/{len(PASS) + len(FAIL)} зелёных")
if FAIL:
    print("КРАСНЫЕ:")
    for f in FAIL:
        print(f"  ❌ {f}")
    sys.exit(1)
print("✅ skus обновляет ровно живые карточки (без сирот и дублей), limit проигнорирован, "
      "отсутствующие честно видны, обратная совместимость цела, RUBICON держит")

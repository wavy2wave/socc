#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — ПОЛНОТА КАРТОЧКИ (ymarket_card_audit_v1). Сухо, 0₽, чистая математика.

Проверяем ЗАКОНЫ аудита полноты, а не «запустилось». Дыра, которую чинит орган (ревью 2026-09-02):
СВЕРКА читала живое состояние карточки, но НЕ гейтила габариты — карточка БЕЗ weightDimensions
проходила PASS. Ключевая честность: MISSING (прочитано: нет) ≠ UNKNOWN (evidence не собрали) —
иначе бедный срез соврал бы «неполная», а дырявая карточка — «полная». Никакой сети и записи.

  CA1  empty_live_unverified      — audit_live({}) → UNVERIFIED (всё UNKNOWN, ни одного MISSING)
  CA2  live_full_complete         — полный срез СВЕРКИ (wd/фото/описание/EAN) → COMPLETE
  CA3  live_no_dims_hole          — дыра ревью: wd=False (на витрине НЕТ габаритов) → INCOMPLETE
  CA4  live_no_description_hole   — desc_len=0 («нет описания», ошибка ARB-карточки) → INCOMPLETE
  CA5  live_no_photos_hole        — n_pics=0 (карточка без фото) → INCOMPLETE
  CA6  live_no_barcode_hole       — barcodes=[] (без штрихкода) → INCOMPLETE
  CA7  live_unknown_not_collected — срез БЕЗ ключа фото → photos UNKNOWN, вердикт UNVERIFIED,
                                    НЕ INCOMPLETE (не собрали ≠ знаем что нет, CC2)
  CA8  live_raw_dims_all4         — raw weightDimensions (4 числа >0) сильнее wd → dims OK (CC12)
  CA9  live_raw_dims_partial      — raw {length,width,height} без weight → dims MISSING (CC4)
  CA10 plan_library_complete      — запись библиотеки со всем → COMPLETE
  CA11 plan_no_dims_unknown       — в записи dims пуст → dims UNKNOWN → UNVERIFIED, НЕ INCOMPLETE
                                    (план не знает, что легло на витрину; план ≠ факт, CC3)
  CA12 plan_dims_partial_missing  — запись с {length,width,height} только → dims MISSING
  CA13 plan_zero_price_missing    — цена ≤0 → price MISSING → INCOMPLETE (не продаём)
  CA14 plan_zero_description      — description_len=0 → description MISSING
  CA15 name_placeholder           — имя пустое/«—»/=offerId → MISSING; продающее → OK (CC7)
  CA16 verdict_states_distinct    — INCOMPLETE/UNVERIFIED/COMPLETE различимы по missing/unknown
  CA17 spec_n_zero_missing        — spec_n=0 (характеристик нет) → MISSING (директива, CC9)
  CA18 null_sentinel_unknown      — ключ есть со значением None → UNKNOWN (как отсутствие)
  CA19 no_beauty_thresholds       — короткое описание (5 симв.) НЕ-empty → OK (CC11: наличие,
                                    не «красота» с 1000 символов)
  CA20 many_rows_readonly         — audit_many_live по партии: ключи offerId, вердикты честны
  CA21 price_structured_unknown   — цена-dict {value,currency} → UNKNOWN, НЕ MISSING (есть, но
                                    формат не разобран ≠ «цены нет», CC2); без падения
  CA22 price_string_parses        — цена-строка "700" → OK; "абв" → UNKNOWN (не crash, не ложь)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_card_audit_v1 as ca      # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


_FULL = {   # живой срез полной ARB-карточки (как СВЕРКА читает витрину + дочитанные поля)
    "name": "Воздушно-пузырьковая плёнка 100 м × 0,75 м, двухслойная",
    "desc_len": 1238, "spec_n": 13, "wd": True, "n_pics": 4,
    "barcodes": ["4607000000000"], "price": 700,
}


def _plan(**over):
    """Запись библиотеки/цикла (что задумано) со всеми блоками, под переопределение."""
    base = {"offer_id": "ARB-53416854", "name": "Воздушно-пузырьковая плёнка 100×0,75 м",
            "description_len": 1238, "spec_n": 13, "n_photos": 4,
            "barcode": "4607000000000", "price": 700, "cost": 300,
            "dims": {"length": 50, "width": 35, "height": 50, "weight": 1438}}
    base.update(over)
    return base


def ca1_empty_live_unverified():
    v = ca.audit_live({})
    ok = (v["verdict"] == "UNVERIFIED" and v["ok"] is None
          and v["missing"] == [] and len(v["unknown"]) == len(ca.BLOCKS))
    return ok, (f"verdict={v['verdict']} ok={v['ok']} missing={v['missing']} "
                f"unknown={v['unknown']} (пустой срез — не собрано, НЕ «неполная»)")


def ca2_live_full_complete():
    v = ca.audit_live(_FULL)
    ok = (v["verdict"] == "COMPLETE" and v["ok"] is True and v["missing"] == [])
    return ok, f"verdict={v['verdict']} note={v['note']}"


def ca3_live_no_dims_hole():
    # Дыра ревью: СВЕРКА прочитала витрину, wd=False — габаритов РЕАЛЬНО нет → жёсткий INCOMPLETE.
    v = ca.audit_live(dict(_FULL, wd=False))
    ok = (v["verdict"] == "INCOMPLETE" and v["ok"] is False
          and "dims" in v["missing"])
    return ok, f"verdict={v['verdict']} missing={v.get('missing')} (дыра закрыта: БЕЗ габаритов ≠ PASS)"


def ca4_live_no_description_hole():
    v = ca.audit_live(dict(_FULL, desc_len=0))
    ok = (v["verdict"] == "INCOMPLETE" and "description" in v["missing"])
    return ok, f"verdict={v['verdict']} missing={v.get('missing')} (пустое описание — ошибка карточки)"


def ca5_live_no_photos_hole():
    v = ca.audit_live(dict(_FULL, n_pics=0))
    ok = (v["verdict"] == "INCOMPLETE" and "photos" in v["missing"])
    return ok, f"verdict={v['verdict']} missing={v.get('missing')} (карточка без фото)"


def ca6_live_no_barcode_hole():
    v = ca.audit_live(dict(_FULL, barcodes=[]))
    ok = (v["verdict"] == "INCOMPLETE" and "barcode" in v["missing"])
    return ok, f"verdict={v['verdict']} missing={v.get('missing')} (без штрихкода)"


def ca7_live_unknown_not_collected():
    # Срез без фото-ключа: СВЕРКА не читала n_pics → photos UNKNOWN, НЕ MISSING (CC2).
    slim = {k: v for k, v in _FULL.items() if k != "n_pics"}
    v = ca.audit_live(slim)
    blk = v["blocks"]["photos"]["state"]
    ok = (blk == "UNKNOWN" and v["verdict"] == "UNVERIFIED" and v["ok"] is None
          and "photos" not in v["missing"] and "photos" in v["unknown"])
    return ok, f"photos={blk} verdict={v['verdict']} (не собрали ≠ знаем что нет, CC2)"


def ca8_live_raw_dims_all4():
    # raw weightDimensions (все 4 >0) сильнее wd-флага: даже wd=False, но полный объект → OK (CC12).
    r = dict(_FULL, wd=False,
             weightDimensions={"length": 500, "width": 350, "height": 500, "weight": 1438})
    v = ca.audit_live(r)
    ok = (v["blocks"]["dims"]["state"] == "OK" and v["verdict"] == "COMPLETE")
    return ok, f"dims={v['blocks']['dims']} verdict={v['verdict']} (полный raw важнее wd)"


def ca9_live_raw_dims_partial():
    # raw НЕполный (нет weight) — API такой весогабарит отклоняет → MISSING (CC4).
    r = dict(_FULL, weightDimensions={"length": 500, "width": 350, "height": 500})
    v = ca.audit_live(r)
    ok = (v["blocks"]["dims"]["state"] == "MISSING" and "dims" in v["missing"])
    return ok, f"dims={v['blocks']['dims']['state']} (частичный набор = неполно)"


def ca10_plan_library_complete():
    v = ca.audit_plan(_plan())
    ok = (v["verdict"] == "COMPLETE" and v["ok"] is True and v["missing"] == [])
    return ok, f"verdict={v['verdict']} note={v['note']}"


def ca11_plan_no_dims_unknown():
    # В записи цикла dims НЕ записаны (цикл без ОВХ): план НЕ знает, что легло на витрину →
    # dims UNKNOWN, вердикт UNVERIFIED. НЕ INCOMPLETE: план не врет «карточка неполная» (CC3).
    v = ca.audit_plan(_plan(dims=None))
    blk = v["blocks"]["dims"]["state"]
    ok = (blk == "UNKNOWN" and v["verdict"] == "UNVERIFIED" and v["ok"] is None
          and "dims" not in v["missing"] and "dims" in v["unknown"])
    return ok, f"dims={blk} verdict={v['verdict']} (запись ≠ факт витрины — подтвердит СВЕРКА)"


def ca12_plan_dims_partial_missing():
    v = ca.audit_plan(_plan(dims={"length": 50, "width": 35, "height": 50}))   # нет weight
    ok = (v["blocks"]["dims"]["state"] == "MISSING" and "dims" in v["missing"]
          and v["verdict"] == "INCOMPLETE")
    return ok, f"dims={v['blocks']['dims']['state']} (частичный ОВХ в записи = известно неполно)"


def ca13_plan_zero_price_missing():
    v = ca.audit_plan(_plan(price=0))
    ok = (v["verdict"] == "INCOMPLETE" and "price" in v["missing"])
    return ok, f"verdict={v['verdict']} missing={v.get('missing')} (цена 0 — не продаём, CC8)"


def ca14_plan_zero_description():
    v = ca.audit_plan(_plan(description_len=0))
    ok = (v["blocks"]["description"]["state"] == "MISSING" and "description" in v["missing"])
    return ok, f"description={v['blocks']['description']['state']} (в записи описания нет)"


def ca15_name_placeholder():
    v_empty = ca.audit_plan(_plan(name=""))
    v_dash = ca.audit_plan(_plan(name="—"))
    v_oid = ca.audit_plan(_plan(name="ARB-53416854"))     # имя = offerId (не продающее)
    ok = all(b["blocks"]["name"]["state"] == "MISSING" for b in (v_empty, v_dash, v_oid)) \
        and ca.audit_plan(_plan())["blocks"]["name"]["state"] == "OK"
    return ok, ("пустое/«—»/=offerId → MISSING; продающее имя → OK (CC7)")


def ca16_verdict_states_distinct():
    full = ca.audit_live(_FULL)                                   # COMPLETE
    hole = ca.audit_live(dict(_FULL, wd=False))                   # INCOMPLETE (missing=[dims])
    slim = ca.audit_live({k: v for k, v in _FULL.items() if k != "n_pics"})  # UNVERIFIED
    ok = (full["verdict"] == "COMPLETE" and hole["verdict"] == "INCOMPLETE"
          and slim["verdict"] == "UNVERIFIED"
          and full["missing"] == [] and hole["missing"] == ["dims"]
          and slim["missing"] == [] and "photos" in slim["unknown"])
    return ok, f"COMPLETE/INCOMPLETE[dims]/UNVERIFIED[photos] различимы — CC2 честно"


def ca17_spec_n_zero_missing():
    v = ca.audit_plan(_plan(spec_n=0))
    ok = (v["blocks"]["specs"]["state"] == "MISSING" and "specs" in v["missing"])
    return ok, f"specs={v['blocks']['specs']['state']} (характеристик нет — директива, CC9)"


def ca18_null_sentinel_unknown():
    # Ключ есть, но None → UNKNOWN (как отсутствие): не выдумываем MISSING на None-данных.
    v = ca.audit_live(dict(_FULL, n_pics=None))
    ok = (v["blocks"]["photos"]["state"] == "UNKNOWN" and v["verdict"] == "UNVERIFIED")
    return ok, f"n_pics=None → photos=UNKNOWN (None-данные = не собрано)"


def ca19_no_beauty_thresholds():
    # CC11: судим наличие, не «красоту». 5 символов НЕ-empty → OK (порог — «не пусто»).
    v = ca.audit_live(dict(_FULL, desc_len=5))
    ok = (v["blocks"]["description"]["state"] == "OK" and v["verdict"] == "COMPLETE")
    return ok, f"desc_len=5 → description=OK (порог = ошибка «нет описания», не красота)"


def ca20_many_rows_readonly():
    rows = {"ARB-1": dict(_FULL, wd=False), "ARB-2": dict(_FULL)}
    out = ca.audit_many_live(rows)
    ok = (set(out) == {"ARB-1", "ARB-2"} and out["ARB-1"]["verdict"] == "INCOMPLETE"
          and out["ARB-2"]["verdict"] == "COMPLETE")
    return ok, f"offerId-ключи={sorted(out)} вердикты={[v['verdict'] for v in out.values()]}"


def ca21_price_structured_unknown():
    # Цена-dict (YM-структура {value,currency}) — цена ЕСТЬ, формат не разбираем → UNKNOWN.
    # Раньше падало на f"{p:g}" ИЛИ лгало MISSING «цена не число» (CC2: не «цены нет»).
    v = ca.audit_live(dict(_FULL, price={"value": 700, "currency": "RUB"}))
    blk = v["blocks"]["price"]
    ok = (blk["state"] == "UNKNOWN" and v["verdict"] == "UNVERIFIED" and "price" not in v["missing"])
    return ok, f"price={blk['state']} (структурная цена → UNKNOWN, не MISSING, без падения)"


def ca22_price_string_parses():
    good = ca.audit_live(dict(_FULL, price="700"))      # числовая строка — разбираем → OK
    bad = ca.audit_live(dict(_FULL, price="абв"))       # мусор-строка → UNKNOWN, не crash/не ложь
    ok = (good["blocks"]["price"]["state"] == "OK" and good["verdict"] == "COMPLETE"
          and bad["blocks"]["price"]["state"] == "UNKNOWN" and "price" not in bad["missing"])
    return ok, (f"price='700'→{good['blocks']['price']['state']} "
                f"price='абв'→{bad['blocks']['price']['state']} (без crash)")


TESTS = [
    ("CA1  empty_live_unverified", ca1_empty_live_unverified),
    ("CA2  live_full_complete", ca2_live_full_complete),
    ("CA3  live_no_dims_hole", ca3_live_no_dims_hole),
    ("CA4  live_no_description_hole", ca4_live_no_description_hole),
    ("CA5  live_no_photos_hole", ca5_live_no_photos_hole),
    ("CA6  live_no_barcode_hole", ca6_live_no_barcode_hole),
    ("CA7  live_unknown_not_collected", ca7_live_unknown_not_collected),
    ("CA8  live_raw_dims_all4", ca8_live_raw_dims_all4),
    ("CA9  live_raw_dims_partial", ca9_live_raw_dims_partial),
    ("CA10 plan_library_complete", ca10_plan_library_complete),
    ("CA11 plan_no_dims_unknown", ca11_plan_no_dims_unknown),
    ("CA12 plan_dims_partial_missing", ca12_plan_dims_partial_missing),
    ("CA13 plan_zero_price_missing", ca13_plan_zero_price_missing),
    ("CA14 plan_zero_description", ca14_plan_zero_description),
    ("CA15 name_placeholder", ca15_name_placeholder),
    ("CA16 verdict_states_distinct", ca16_verdict_states_distinct),
    ("CA17 spec_n_zero_missing", ca17_spec_n_zero_missing),
    ("CA18 null_sentinel_unknown", ca18_null_sentinel_unknown),
    ("CA19 no_beauty_thresholds", ca19_no_beauty_thresholds),
    ("CA20 many_rows_readonly", ca20_many_rows_readonly),
    ("CA21 price_structured_unknown", ca21_price_structured_unknown),
    ("CA22 price_string_parses", ca22_price_string_parses),
]


def main():
    print("🎯 ПРИЁМКА · ПОЛНОТА КАРТОЧКИ (аудит-орган, чистая математика, 0₽, без сети)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<30} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Аудит честен: MISSING (прочитано: нет) ≠ UNKNOWN (не собрали); карточка БЕЗ "
              "габаритов на витрине → INCOMPLETE (дыра ревью закрыта), RUBICON цел.")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — FLOOR-GUARD ЦИКЛ-1 (#17/#34) + НОВЫЙ ЖИВОЙ СРЕЗ СВЕРКИ (#33). Сухо, 0₽, без сети.

#34: node_build получил FLOOR-GUARD — прямые ₽-границы оператора price_floor/price_ceiling
в манифесте магазина (НЕ provisional-совет ЦЕНОВИКА — тот advisory). Не заданы → поведение
прежнее (обратносовместимо). Заданы → карточка за границей НЕ уходит на залив (честный FAIL
до трат). Механизм НЕ принимает TUNABLE-решение — он включается, когда оператор поставит числа.

#33: СВЕРКА (node_verify) теперь до-читает name/цену/raw-ОВХ (offer-mappings) и спеки
(offer-cards), срез стал ПОЛНЫМ. Доказываем на синтетическом срезе той же формы: полный срез
→ COMPLETE; срез без spec_n (offer-cards недоступен) → UNVERIFIED по спекам, НЕ INCOMPLETE.

  FG1 bounds_absent_inert      — price_floor/ceiling НЕ заданы → PASS как раньше (enforced False)
  FG2 below_floor_fail         — price_floor выше цены карточки → FAIL «below_floor»
  FG3 above_ceiling_fail       — price_ceiling ниже цены карточки → FAIL «above_ceiling»
  FG4 bounds_ok_pass           — цена в границах → PASS
  FG5 junk_bounds_ignored      — битые границы («abc») → как не заданы (не крэш, enforced False)
  FG6 live_slice_complete      — полный живой срез СВЕРКИ (#33) → COMPLETE (4/4 больше не UNVERIFIED)
  FG7 thin_slice_unverified    — срез без spec_n (offer-cards недоступен) → UNVERIFIED по спекам
  FG8 missing_specs_live       — спеки прочитаны как 0 (parameterValues=[]) → MISSING → INCOMPLETE
  FG9 numeric_string_coerced   — FIX-D: "1000"-в-кавычках коэрцится → пол ЖИВ (не молча гаснет)
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
for p in (str(ARB),):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_cycle1_v1 as C1          # noqa: E402
import ymarket_film_cards_v1 as FC      # noqa: E402
import ymarket_card_audit_v1 as caudit  # noqa: E402

# Полноценная донор-строка (pid из FILM_FACTS → _spec+описание; габариты → ОВХ; фото — мок).
_PID = "1588731"
_DONOR = {"pid": _PID, "article": "FLM-FG-001", "name": "Тестовая плёнка FG 50×0.3",
          "cost": 100.0, "length": 50, "width": 35, "height": 50, "weight": 1.438}


def _full_ctx(profile_extra):
    profile = {"slug": "fg-test", "markup": 8.0}
    profile.update(profile_extra or {})
    return {"profile": profile, "raw_donor": [_DONOR]}


def _patch_photos():
    """node_build читает FC._pub_urls_by_pid() → мок фото, чтобы не зависеть от диска/сети."""
    orig = FC._pub_urls_by_pid
    FC._pub_urls_by_pid = lambda: {_PID: ["https://img.example/1.jpg"]}
    return orig


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _node_build(ctx):
    orig = _patch_photos()
    try:
        return C1.node_build(ctx, dry=True, commit=False)
    finally:
        FC._pub_urls_by_pid = orig


def fg1_bounds_absent_inert():
    r = _node_build(_full_ctx(None))
    pb = (r.get("evidence") or {}).get("price_bounds")
    ok = (r.get("verdict") == "PASS" and isinstance(pb, dict) and pb.get("enforced") is False
          and pb.get("floor") is None and pb.get("ceiling") is None)
    return ok, f"verdict={r.get('verdict')} bounds={pb} (без границ — как раньше)"


def fg2_below_floor_fail():
    r = _node_build(_full_ctx({"price_floor": 1000}))   # карточка ~800₽ < пол 1000₽
    note = r.get("note", "")
    ok = (r.get("verdict") == "FAIL" and "below_floor" in note and "800" in note)
    return ok, f"verdict={r.get('verdict')} · {note[:110]}"


def fg3_above_ceiling_fail():
    r = _node_build(_full_ctx({"price_ceiling": 500}))   # карточка ~800₽ > потолок 500₽
    note = r.get("note", "")
    ok = (r.get("verdict") == "FAIL" and "above_ceiling" in note and "800" in note)
    return ok, f"verdict={r.get('verdict')} · {note[:110]}"


def fg4_bounds_ok_pass():
    r = _node_build(_full_ctx({"price_floor": 500, "price_ceiling": 1000}))
    pb = (r.get("evidence") or {}).get("price_bounds")
    ok = r.get("verdict") == "PASS" and isinstance(pb, dict) and pb.get("enforced") is False
    return ok, f"verdict={r.get('verdict')} bounds={pb} (цена ~800 в [500..1000])"


def fg5_junk_bounds_ignored():
    r = _node_build(_full_ctx({"price_floor": "abc", "price_ceiling": float("inf")}))
    pb = (r.get("evidence") or {}).get("price_bounds")
    ok = (r.get("verdict") == "PASS" and isinstance(pb, dict) and pb.get("enforced") is False
          and pb.get("floor") is None and pb.get("floor_raw") == "abc")
    return ok, f"verdict={r.get('verdict')} bounds={pb} (битые границы → как не заданы, не крэш)"


def fg9_numeric_string_coerced():
    # FIX-D (аудит price:387): resolve_markup строки-числа парсит → и пол обязан исполниться.
    # "1000"-в-кавычках коэрцится и FAIL-ит карточку ~800₽ под полом (раньше молча гас).
    r = _node_build(_full_ctx({"price_floor": "1000"}))
    note = r.get("note", "")
    pb = (r.get("evidence") or {}).get("price_bounds")
    ok = (r.get("verdict") == "FAIL" and "below_floor" in note
          and pb.get("floor") == 1000.0 and pb.get("floor_raw") == "1000")
    return ok, f"verdict={r.get('verdict')} bounds={pb} («1000» коэрцится → пол жив)"


# ── #33: живой срез СВЕРКИ той же формы, что теперь кладёт node_verify ─────────

def _live_content(**over):
    base = {
        "name": "Воздушно-пузырьковая плёнка 100 м × 0,75 м, двухслойная",
        "vendor": "Без бренда", "desc_len": 1238, "n_pics": 4,
        "barcodes": ["4607000000000"], "wd": True,
        "weightDimensions": {"length": 50, "width": 35, "height": 50, "weight": 1.438},
        "price": 4800, "spec_n": 13,
    }
    base.update(over or {})
    return base


def fg6_live_slice_complete():
    v = caudit.audit_live(_live_content())
    ok = v["verdict"] == "COMPLETE" and not v["missing"] and not v["unknown"]
    return ok, f"verdict={v['verdict']} · {v['note']} (полный срез #33 → полностью подтверждена)"


def fg7_thin_slice_unverified():
    # offer-cards недоступен (fail-soft): spec_n НЕ в срезе → спеки UNKNOWN → UNVERIFIED, НЕ ложный INCOMPLETE
    c = _live_content(spec_n=None)
    del c["spec_n"]
    v = caudit.audit_live(c)
    ok = v["verdict"] == "UNVERIFIED" and v["unknown"] == ["specs"] and not v["missing"]
    return ok, f"verdict={v['verdict']} unknown={v['unknown']} (спеки не собраны — честно, не «нет специй» у витрины)"


def fg8_missing_specs_live():
    # parameterValues=[] ПРОЧИТАНО (offer-cards работает, специй реально 0) → MISSING → INCOMPLETE
    v = caudit.audit_live(_live_content(spec_n=0))
    ok = v["verdict"] == "INCOMPLETE" and v["missing"] == ["specs"]
    return ok, f"verdict={v['verdict']} missing={v['missing']} (0 параметров на витрине = факт)"


def _run():
    tests = [("FG1 bounds_absent_inert", fg1_bounds_absent_inert),
             ("FG2 below_floor_fail", fg2_below_floor_fail),
             ("FG3 above_ceiling_fail", fg3_above_ceiling_fail),
             ("FG4 bounds_ok_pass", fg4_bounds_ok_pass),
             ("FG5 junk_bounds_ignored", fg5_junk_bounds_ignored),
             ("FG6 live_slice_complete", fg6_live_slice_complete),
             ("FG7 thin_slice_unverified", fg7_thin_slice_unverified),
             ("FG8 missing_specs_live", fg8_missing_specs_live),
             ("FG9 numeric_string_coerced", fg9_numeric_string_coerced)]
    fails = 0
    for name, fn in tests:
        try:
            ok, detail = fn()
        except Exception as e:                      # тест упал — это FAIL приёмки, не «ожидание»
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(f"  {_passed(ok)} {name:<24} {detail}")
        fails += 0 if ok else 1
    print(f"\nFLOOR-GUARD + #33-срез: {len(tests) - fails}/{len(tests)} зелёных")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run())

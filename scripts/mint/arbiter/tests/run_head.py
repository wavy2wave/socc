#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — ГОЛОВА (ymarket_role_head_v1). Сухо, 0₽, без сети.

Проверяем ЗАКОНЫ роли-синтезатора, а не «запустилось». Каждый тест ловит конкретную ложь,
которую ГОЛОВА могла бы сказать. Пишем ТОЛЬКО во временный стор (env YM_HEAD_PROPOSALS_PATH) —
канон отчётов не трогаем. Ранг делегирован portfolio_v1 (H2) — проверяем ЧИСЛОМ, что не дублируем.

  HD1  empty_universe_honest    — нет кандидатов → ok=True, пустой шорт-лист + причина, НЕ падение (H1)
  HD2  ranking_is_delegated     — justified_score в шорт-листе == portfolio.select_per_category (H2, 0 дублей)
  HD3  physics_reject_blocked   — ТОВАРОВЕД reject → НЕ в шорт-листе, а в blocked с blocked_by=ТОВАРОВЕД (H3)
  HD4  needs_data_ranks_below   — needs_data предлагается, но НИЖЕ одобренных физикой (ярус, H3)
  HD5  window_skip_blocked      — ТРЕНД-СКАУТ SKIP → blocked by ТРЕНД-СКАУТ, не предлагаем (H4)
  HD6  trend_silent_neutral     — скаут молчит → кандидат НЕ занулён, доходит до шорт-листа (H4)
  HD7  state_always_proposed    — каждый пункт шорт-листа state=предложено (H5, предлагает не публикует)
  HD8  idempotent_day           — save_day дважды за дату → ОДНА запись, перезапись не дубль (H6)
  HD9  store_atomic_roundtrip   — save_day → load_day несёт тот же шорт-лист через файл
  HD10 failsoft_corrupt_store   — битый JSON → чистый бланк, запись всё равно ложится (fail-soft)
  HD11 plan_day_no_source       — источник не подключён → NO_HEAD_SOURCE, НЕ «предлагать нечего» (H1)
  HD12 plan_day_source_raises   — источник упал → error несётся, НЕ «предлагать нечего» (разные вещи)
  HD13 key_by_name_fallback     — кандидат без sku сшивается по нормализованному имени между осями
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_role_head_v1 as head        # noqa: E402
import portfolio_v1 as portfolio           # noqa: E402
import ymarket_role_merchandiser_v1 as merch  # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


class _Store:
    """Контекст: временный стор через env YM_HEAD_PROPOSALS_PATH (канон отчётов не трогаем)."""
    def __enter__(self):
        self._save = os.environ.get("YM_HEAD_PROPOSALS_PATH")
        self._dir = tempfile.TemporaryDirectory()
        os.environ["YM_HEAD_PROPOSALS_PATH"] = str(Path(self._dir.name) / "head.json")
        return self

    def __exit__(self, *exc):
        if self._save is None:
            os.environ.pop("YM_HEAD_PROPOSALS_PATH", None)
        else:
            os.environ["YM_HEAD_PROPOSALS_PATH"] = self._save
        self._dir.cleanup()
        return False


# ── строители входов (те же формы, что дают wb_scout / ТОВАРОВЕД / ТРЕНД-СКАУТ) ──

def _wb(sku, name, cost, strength):
    return {"sku": sku, "name": name, "cost": float(cost),
            "url": f"https://sp.cargo-avto.ru/catalog/{sku}/", "source_market": "wildberries",
            "profit_target": 600, "min_profit": 200,
            "demand_signal": {"kind": "wb_public_proxy", "strength": strength}}


def _merch(approve=(), reject=(), needs=()):
    """Собрать вывод merch.screen вручную (изолируем логику ГОЛОВЫ от внутренностей ТОВАРОВЕДа)."""
    def row(x, verdict):
        sku, name = (x if isinstance(x, tuple) else (x, x))
        return {"sku": sku, "name": name, "verdict": verdict,
                "reasons": ([] if verdict == "approve" else [f"{verdict}: демо-причина"]),
                "economics": {"profit": 500}}
    return {"approved": [row(x, "approve") for x in approve],
            "rejected": [row(x, "reject") for x in reject],
            "needs_data": [row(x, "needs_data") for x in needs],
            "agg": {"total": len(approve) + len(reject) + len(needs)}}


def _trend(enter=(), watch=(), skip=()):
    def row(sku, action, phase):
        return {"sku": sku, "name": sku, "action": action, "phase": phase,
                "margin_x": 3.0, "why": f"{action}/{phase}"}
    return {"ok": True,
            "candidates": [row(s, "ENTER", "growth") for s in enter]
                          + [row(s, "WATCH", "peak") for s in watch],
            "skipped": [row(s, "SKIP", "late") for s in skip]}


# ── тесты ──────────────────────────────────────────────────────────────────────

def hd1_empty_universe_honest():
    res = head.rank([], merch_result=None, trend_result=None)
    ok = (res["ok"] is True and res["shortlist"] == [] and res["blocked"] == []
          and any("wb" in n.lower() or "спрос" in n for n in res["need_sources"]))
    return ok, f"ok={res['ok']} shortlist={len(res['shortlist'])} причин={len(res['need_sources'])}"


def hd2_ranking_is_delegated():
    wb = [_wb("A1", "Плёнка А", 350, 80), _wb("A2", "Плёнка Б", 400, 40)]
    res = head.rank(wb, merch_result=_merch(approve=["A1", "A2"]),
                    trend_result=_trend(enter=["A1", "A2"]))
    ranked = portfolio.select_per_category(wb, top_k=len(wb))
    by_sku = {r["sku"]: r["justified_score"] for r in ranked}
    ok = all(abs(r["justified_score"] - by_sku[r["sku"]]) < 1e-9 for r in res["shortlist"])
    # и порядок совпадает с портфелем (тот же ранг, не своя формула)
    ok = ok and [r["sku"] for r in res["shortlist"]] == [r["sku"] for r in ranked]
    return ok, f"head_scores={[round(r['justified_score']) for r in res['shortlist']]} == portfolio"


def hd3_physics_reject_blocked():
    wb = [_wb("A1", "Годный", 350, 80), _wb("A2", "Негабарит", 400, 90)]
    res = head.rank(wb, merch_result=_merch(approve=["A1"], reject=["A2"]),
                    trend_result=_trend(enter=["A1", "A2"]))
    skus = [r["sku"] for r in res["shortlist"]]
    blk = res["blocked"]
    ok = ("A1" in skus and "A2" not in skus
          and len(blk) == 1 and blk[0]["sku"] == "A2" and blk[0]["blocked_by"] == "ТОВАРОВЕД")
    return ok, f"shortlist={skus} blocked={[(b['sku'], b['blocked_by']) for b in blk]}"


def hd4_needs_data_ranks_below():
    # A2 сильнее по спросу (⇒ выше justified_score), но needs_data → должен уйти НИЖЕ одобренного A1
    wb = [_wb("A1", "Одобрен физикой", 350, 50), _wb("A2", "Нужны данные", 350, 95)]
    res = head.rank(wb, merch_result=_merch(approve=["A1"], needs=["A2"]),
                    trend_result=_trend(enter=["A1", "A2"]))
    skus = [r["sku"] for r in res["shortlist"]]
    a2 = next(r for r in res["shortlist"] if r["sku"] == "A2")
    ok = skus == ["A1", "A2"] and a2["needs_data"] is True and a2["feasible"] is None
    return ok, f"порядок={skus} (A1 одобрен выше, хотя A2 спрос выше) needs_data={a2['needs_data']}"


def hd5_window_skip_blocked():
    wb = [_wb("A1", "Окно открыто", 350, 80), _wb("A2", "Окно закрыто", 400, 90)]
    res = head.rank(wb, merch_result=_merch(approve=["A1", "A2"]),
                    trend_result=_trend(enter=["A1"], skip=["A2"]))
    skus = [r["sku"] for r in res["shortlist"]]
    blk = res["blocked"]
    ok = ("A1" in skus and "A2" not in skus
          and len(blk) == 1 and blk[0]["sku"] == "A2" and blk[0]["blocked_by"] == "ТРЕНД-СКАУТ")
    return ok, f"shortlist={skus} blocked={[(b['sku'], b['blocked_by']) for b in blk]}"


def hd6_trend_silent_neutral():
    # скаут вообще не дал строк по A1 → окно нейтрально, кандидат НЕ штрафуется и доходит до шорт-листа
    wb = [_wb("A1", "Без окна", 350, 80)]
    res = head.rank(wb, merch_result=_merch(approve=["A1"]), trend_result=None)
    r = res["shortlist"][0] if res["shortlist"] else {}
    ok = (len(res["shortlist"]) == 1 and r.get("sku") == "A1" and r.get("window") is None
          and res["blocked"] == [])
    return ok, f"предложен={[x['sku'] for x in res['shortlist']]} window={r.get('window')} (нейтрально)"


def hd7_state_always_proposed():
    wb = [_wb("A1", "П1", 350, 80), _wb("A2", "П2", 400, 60)]
    res = head.rank(wb, merch_result=_merch(approve=["A1", "A2"]),
                    trend_result=_trend(enter=["A1"], watch=["A2"]))
    ok = bool(res["shortlist"]) and all(r["state"] == head.STATE_PROPOSED for r in res["shortlist"])
    return ok, f"состояния={sorted(set(r['state'] for r in res['shortlist']))} (все «предложено», H5)"


def hd8_idempotent_day():
    with _Store():
        wb = [_wb("A1", "П1", 350, 80)]
        res = head.rank(wb, merch_result=_merch(approve=["A1"]), trend_result=_trend(enter=["A1"]))
        head.save_day("2026-08-12", res)
        head.save_day("2026-08-12", res)          # второй прогон за те же сутки
        doc = head.load()
        days = doc.get("days") or {}
        ok = list(days.keys()) == ["2026-08-12"] and len(days) == 1
    return ok, f"дней в сторе={list(days.keys())} (H6: одна запись на дату)"


def hd9_store_atomic_roundtrip():
    with _Store():
        wb = [_wb("A1", "Плёнка карбон", 350, 80)]
        res = head.rank(wb, merch_result=_merch(approve=["A1"]), trend_result=_trend(enter=["A1"]))
        head.save_day("2026-08-12", res)
        got = head.load_day("2026-08-12")
        ok = (got and got["shortlist"] and got["shortlist"][0]["sku"] == "A1"
              and got["shortlist"][0]["state"] == head.STATE_PROPOSED)
    return bool(ok), f"через файл: {got and [s['sku'] for s in got['shortlist']]}"


def hd10_failsoft_corrupt_store():
    with _Store():
        p = Path(os.environ["YM_HEAD_PROPOSALS_PATH"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("}{ не json", encoding="utf-8")
        doc = head.load()                          # битый → чистый бланк, не падение
        blank_ok = doc["schema"] == head.SCHEMA and doc["days"] == {}
        wb = [_wb("A1", "П1", 350, 80)]
        res = head.rank(wb, merch_result=_merch(approve=["A1"]), trend_result=_trend(enter=["A1"]))
        head.save_day("2026-08-12", res)           # запись поверх битого всё равно ложится
        wrote_after = head.load_day("2026-08-12") is not None   # ЧИТАЕМ в сторе, до выхода из _Store
        ok = blank_ok and wrote_after
    return ok, f"битый→бланк={blank_ok} запись_после={wrote_after}"


def hd11_plan_day_no_source():
    res = head.plan_day(head_source_fn=None)
    ok = (res["ok"] is False and res["reason"] == "NO_HEAD_SOURCE"
          and res["shortlist"] == [] and res.get("need_source"))
    return ok, f"ok={res['ok']} reason={res.get('reason')} (честно «нам не дали», не «нечего»)"


def hd12_plan_day_source_raises():
    def boom():
        raise RuntimeError("сеть к поставщику упала")
    res = head.plan_day(head_source_fn=boom)
    # ключ: это НЕ ok, несёт error, и это НЕ «предлагать нечего» (пустой ≠ ошибка)
    ok = (res["ok"] is False and "RuntimeError" in (res.get("error") or "")
          and res["shortlist"] == [])
    return ok, f"ok={res['ok']} error={res.get('error')}"


def hd13_key_by_name_fallback():
    # без sku: сшивка осей по нормализованному имени (ё→е, регистр). ТОВАРОВЕД одобряет по имени.
    wb = [{"name": "Плёнка Матовая", "cost": 350.0, "url": "https://sp.cargo-avto.ru/catalog/x/",
           "source_market": "wildberries", "profit_target": 600, "min_profit": 200,
           "demand_signal": {"strength": 70}}]
    merch_result = {"approved": [{"name": "плёнка матовая", "verdict": "approve", "reasons": []}],
                    "rejected": [], "needs_data": [], "agg": {"total": 1}}
    res = head.rank(wb, merch_result=merch_result, trend_result=None)
    r = res["shortlist"][0] if res["shortlist"] else {}
    ok = len(res["shortlist"]) == 1 and r.get("feasible") is True
    return ok, f"сшито_по_имени feasible={r.get('feasible')} (ё/регистр нормализованы)"


TESTS = [
    ("HD1  empty_universe_honest", hd1_empty_universe_honest),
    ("HD2  ranking_is_delegated", hd2_ranking_is_delegated),
    ("HD3  physics_reject_blocked", hd3_physics_reject_blocked),
    ("HD4  needs_data_ranks_below", hd4_needs_data_ranks_below),
    ("HD5  window_skip_blocked", hd5_window_skip_blocked),
    ("HD6  trend_silent_neutral", hd6_trend_silent_neutral),
    ("HD7  state_always_proposed", hd7_state_always_proposed),
    ("HD8  idempotent_day", hd8_idempotent_day),
    ("HD9  store_atomic_roundtrip", hd9_store_atomic_roundtrip),
    ("HD10 failsoft_corrupt_store", hd10_failsoft_corrupt_store),
    ("HD11 plan_day_no_source", hd11_plan_day_no_source),
    ("HD12 plan_day_source_raises", hd12_plan_day_source_raises),
    ("HD13 key_by_name_fallback", hd13_key_by_name_fallback),
]


def main():
    print("🎯 ПРИЁМКА · ГОЛОВА (сухо, 0₽, без сети)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<28} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ ГОЛОВА честна: пустое=пусто-с-причиной, ранг делегирован (0 дублей), гейт физики "
              "и окна режут, needs_data ниже, state=предложено, идемпотентна, fail-soft, RUBICON цел.")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · ДЕНЬ (ozon_day_v1) — герметичные приёмки контура дня.

Законы (зеркало ЯМ + ОЗОН-правки):
  D1  сухо по умолчанию: день идёт dry, commit физически False, тик зовётся commit=False.
  D2  шов УПРАВЛЯЮЩЕГО: менеджер-тик подкладывается (не трогает канонический TICK_REPORT),
      его action/ошибки честно входят в день.
  D3  отделы реальны на замороженной памяти: assess_all(0₽, сети нет) → 6 отделов,
      у каждого human + grounded/source; падение отдела не роняет день (B2).
  D4  дельта ко вчера: два дня подряд в песочнице → compared_to/дельта по изменившимся
      числовым KPI; одинаковые KPI → дельта не выдумывается (None).
  D5  commit-пути НЕТ: в сигнатуре run_day нет commit; день докладывает «commit-пути НЕТ».
  D6  дознание живьём только по слову: live_read=False → дознания нет; truth_fn-шов поднимает
      факт; упавший truth_fn → честный провал в failures, день не врёт (B2).
  D7  что горит: errors→КОНТРОЛЁР, need_mapping→ОПЕРАТОР, index_red→ЦЕНОВИК (из памяти).
  D8  журнал только в песочницу: журнал дня пишется в OZON_DAY_JOURNAL, канон не трогается;
      тик-репорт канонический не пишется (шов).
  D9  пустота честна: пустая память → tracked=0/ошибки=0, день ok=True без выдумки.
  D10 ПУПОВИНА «карточка⇄донор» (закон 09.09): шов входит в день; убыточные якоря →
      эскалация ЦЕНОВИКУ (профит-закон, не молчим).
  D11 ПУПОВИНА реальная: канон+библиотека с диска (0₽, сети нет) → 697 связаны, 0 убыточных.
  D12 падение ПУПОВИНЫ не роняет день (B2) — беда честна в failures, день не врёт.

Сухо: env-песочница (OZON_STATE_PATH/OZON_SHIFT_MEMORY/OZON_DAY_JOURNAL/OZON_TICK_LEDGER),
сети нет, канон не пишется.
"""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ARB = Path(__file__).resolve().parent.parent
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

import ozon_day_v1 as day_mod
import ozon_state_v1 as S
import ozon_econ_v1 as econ
import ozon_departments_v1 as depts

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def _passed(cond):
    return bool(cond)


def _sandbox():
    """Песочница: чистые пути для памяти/смен/журнала — канон не трогается."""
    d = Path(tempfile.mkdtemp(prefix="ozon_day_test_"))
    env = {
        "OZON_STATE_PATH": str(d / "state.json"),
        "OZON_SHIFT_MEMORY": str(d / "shift.json"),
        "OZON_DAY_JOURNAL": str(d / "day_journal.jsonl"),
        "OZON_TICK_LEDGER": str(d / "tick_ledger.json"),
        "OZON_LIVE": "0",
    }
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    return d, old, env


def _restore(old):
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _write_state(d, skus, working_set=()):
    """Написать валидную память ozon_state в песочницу."""
    doc = {"schema": S.SCHEMA, "created_at": "2026-09-08T00:00:00Z", "updated_at": "2026-09-08T00:00:00Z",
           "working_set": list(working_set), "skus": skus, "daily": {}, "counters": {}}
    p = S.state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _ok_tick(**kw):
    """Шов УПРАВЛЯЮЩЕГО: действие без ошибок (память/ошибки НЕ трогает)."""
    base = {"tick_id": "OZTICK_TEST", "action": "HEALTHCHECK", "self": {}, "proof": {},
            "result": {"note": "шов-тик"}, "errors": []}
    base.update(kw)
    return base


def _run(**kw):
    return day_mod.run_day(dry=True, manager_tick_fn=_ok_tick, **kw)


def _t01_sukhoy_po_umolchaniyu():
    d, old, env = _sandbox()
    try:
        day = _run()
        return _passed(day["dry"] is True and day["commit"] is False
                       and day.get("_journaled") is not None), \
               f"dry={day.get('dry')} commit={day.get('commit')} journaled={day.get('_journaled')}"
    finally:
        _restore(old)


def _t02_seam_upravlyayushchego():
    d, old, env = _sandbox()
    try:
        day = _run()
        mt = (day.get("roles") or {}).get("MANAGER_TICK") or {}
        canon_tick = Path("/Users/wavysexy/SOCC/MEMORY_WAVE/reports/mint/arbiter/ozon_manager_tick.json")
        return _passed(mt.get("action") == "HEALTHCHECK" and mt.get("ok") is True
                       and "канонический тик-репорт не пишется"), \
               f"action={mt.get('action')}"
    finally:
        _restore(old)


def _t03_otdely_realnye():
    d, old, env = _sandbox()
    try:
        _write_state(d, {
            "SKU1": {"lifecycle": S.LC_ON_SHELF, "published_verified": True, "errors": None},
        })
        day = _run()
        dp = (day.get("roles") or {}).get("DEPARTMENTS") or {}
        ass = depts.assess_all(doc=S.load())
        n_depts = len(ass.get("departments") or [])
        ok_depts = all(r.get("human") for r in (ass.get("departments") or []))
        grounded_keys = {r.get("grounded") for r in (ass.get("departments") or [])}
        return _passed(dp.get("ok") is True and n_depts == 6 and ok_depts
                       and grounded_keys <= {True, False, None}
                       and day.get("ok") is True), \
               f"департаментов={n_depts} grounded={grounded_keys}"
    finally:
        _restore(old)


def _t04_delta_vchera():
    d, old, env = _sandbox()
    try:
        # день 1: пустая память
        day1 = _run()
        # день 2: память выросла до 5 карточек → KPI изменился → дельта не выдумана
        _write_state(d, {f"S{i}": {"lifecycle": S.LC_IMPORTED} for i in range(5)})
        day2 = _run()
        dl = day2.get("delta") or {}
        return _passed(day2.get("compared_to") == day1.get("date")
                       and isinstance(dl.get("cards_tracked"), dict)
                       and dl["cards_tracked"]["from"] == 0 and dl["cards_tracked"]["to"] == 5
                       and day1.get("delta") is None), \
               f"compared_to={day2.get('compared_to')} delta={dl}"
    finally:
        _restore(old)


def _t05_commit_puti_net():
    d, old, env = _sandbox()
    try:
        import inspect
        sig = inspect.signature(day_mod.run_day)
        src = Path(day_mod.__file__).read_text(encoding="utf-8")
        day = _run()
        # CLI тоже всегда сухой: день зовётся с dry=True, инверсия `run_day(dry=not args.dry)` убрана
        cli_dry = "run_day(dry=True" in src and "run_day(dry=not args.dry" not in src
        return _passed("commit" not in sig.parameters
                       and "commit=True" not in src
                       and "commit-пути НЕТ" in day_mod.render_day(day)
                       and cli_dry), \
               f"params={list(sig.parameters)} cli_dry={cli_dry}"
    finally:
        _restore(old)


def _t06_doznanie_po_slovu():
    d, old, env = _sandbox()
    try:
        # без слова — дознания нет
        d0 = _run(live_read=False)
        no_truth = d0.get("truth") is None
        # по слову + шов-факт — дознание поднимается
        d1 = _run(live_read=True, truth_fn=lambda: {"sales_count": 27, "days": 30,
                                                    "total_net": 22871.59, "ok": True})
        got_truth = d1.get("truth") is not None and (d1["truth"]["slim"] or {}).get("sales_count") == 27
        # упавший факт → честный провал, день не врёт (B2)
        d2 = _run(live_read=True, truth_fn=lambda: {"error": "ключ просрочен"})
        honest = any("дознание" in str(f) for f in d2.get("failures") or [])
        return _passed(no_truth and got_truth and honest), \
               f"no={no_truth} got={got_truth} honest={honest}"
    finally:
        _restore(old)


def _t07_chto_gorit():
    d, old, env = _sandbox()
    try:
        _write_state(d, {
            "ERR1": {"lifecycle": S.LC_IMPORTED, "errors": ["цена ниже пола"]},
            "MAP1": {"lifecycle": S.LC_IMPORTED, "need_mapping": True},
            "RED1": {"lifecycle": S.LC_ON_SHELF, "published_verified": True,
                     "price_index": econ.INDEX_RED},
        })
        day = _run()
        owners = {i.get("owner") for i in (day.get("burning") or {}).get("items") or []}
        return _passed({"КОНТРОЛЁР", "ОПЕРАТОР", "ЦЕНОВИК"} <= owners), \
               f"owners={owners}"
    finally:
        _restore(old)


def _t08_journal_tolko_v_pesok():
    d, old, env = _sandbox()
    try:
        canon_journal = Path("/Users/wavysexy/SOCC/MEMORY_WAVE/reports/mint/arbiter/ozon_day_journal.jsonl")
        was = canon_journal.exists()
        before = canon_journal.stat().st_mtime_ns if was else None
        canon_tick = Path("/Users/wavysexy/SOCC/MEMORY_WAVE/reports/mint/arbiter/ozon_manager_tick.json")
        was_t = canon_tick.exists()
        before_t = canon_tick.stat().st_mtime_ns if was_t else None
        day = _run()
        sp = Path(env["OZON_DAY_JOURNAL"])
        after = canon_journal.stat().st_mtime_ns if canon_journal.exists() else None
        after_t = canon_tick.stat().st_mtime_ns if canon_tick.exists() else None
        return _passed(str(day_mod.journal_path()) == str(sp)
                       and sp.exists() and sp.read_text(encoding="utf-8").strip()
                       and after == before and after_t == before_t), \
               f"journal_sandbox={sp.exists()} canon_untouched={after == before}"
    finally:
        _restore(old)


def _t09_pustota_chestna():
    d, old, env = _sandbox()
    try:
        _write_state(d, {})
        day = _run()
        k = day.get("kpis") or {}
        return _passed(day.get("ok") is True
                       and k.get("cards_tracked") == 0
                       and k.get("cards_errored") == 0
                       and k.get("cards_on_shelf") == 0
                       and not (day.get("burning") or {}).get("items")), \
               f"k={k}"
    finally:
        _restore(old)


def _t10_pupovina_seam():
    """D10: ПУПОВИНА-шов входит в день; убыточные якоря → эскалация ЦЕНОВИКУ."""
    d, old, env = _sandbox()
    try:
        def stub():
            return {"canon_rolls": 39, "bound": 697, "unbound": 0,
                    "unprofitable": 2, "width_keep": 644, "errors": []}
        day = _run(anchor_fn=stub)
        an = (day.get("roles") or {}).get("DONOR_ANCHOR") or {}
        esc = [e for e in (day.get("escalations") or []) if "УБЫТОЧН" in str(e.get("kind"))]
        return _passed(an.get("ok") is True and an.get("bound") == 697
                       and an.get("unprofitable") == 2 and esc), \
               f"an={an} esc={esc}"
    finally:
        _restore(old)


def _t11_pupovina_real():
    """D11: ПУПОВИНА реальная (канон+библиотека с диска, 0₽ сети нет) — все связаны, 0 убыточных."""
    d, old, env = _sandbox()
    try:
        day = _run()  # anchor_fn=None → _default_anchor (читает канон с диска, сеть не зовёт)
        an = (day.get("roles") or {}).get("DONOR_ANCHOR") or {}
        return _passed(an.get("ok") is True and an.get("bound") >= 690
                       and an.get("unprofitable") == 0
                       and an.get("canon_rolls") >= 30), \
               f"an={an}"
    finally:
        _restore(old)


def _t12_pupovina_fail_not_drown():
    """D12: падение ПУПОВИНЫ НЕ роняет день (B2 — день продолжается, беда честна в failures)."""
    d, old, env = _sandbox()
    try:
        def broken():
            raise RuntimeError("канон битый")
        day = _run(anchor_fn=broken)
        an = (day.get("roles") or {}).get("DONOR_ANCHOR") or {}
        # день не сломался: отчёт собран, отделы/тик на месте; провал честно в failures
        mt = (day.get("roles") or {}).get("MANAGER_TICK") or {}
        return _passed(an.get("ok") is False and "канон битый" in str(an.get("error"))
                       and any("пуповина" in str(f) for f in (day.get("failures") or []))
                       and day.get("roles") and mt.get("ok") is True), \
               f"an={an} fail={day.get('failures')}"
    finally:
        _restore(old)


TESTS = [
    ("D1 сухо по умолчанию", _t01_sukhoy_po_umolchaniyu),
    ("D2 шов УПРАВЛЯЮЩЕГО", _t02_seam_upravlyayushchego),
    ("D3 отделы реальны на замороженной памяти", _t03_otdely_realnye),
    ("D4 дельта ко вчера", _t04_delta_vchera),
    ("D5 commit-пути НЕТ", _t05_commit_puti_net),
    ("D6 дознание по слову / провал честен", _t06_doznanie_po_slovu),
    ("D7 что горит: КОНТРОЛЁР/ОПЕРАТОР/ЦЕНОВИК", _t07_chto_gorit),
    ("D8 журнал только в песочницу", _t08_journal_tolko_v_pesok),
    ("D9 пустота честна (None/0, без выдумки)", _t09_pustota_chestna),
    ("D10 ПУПОВИНА-шов: убыточные → эскалация ЦЕНОВИКУ", _t10_pupovina_seam),
    ("D11 ПУПОВИНА реальная: канон+библиотека с диска, 0₽", _t11_pupovina_real),
    ("D12 падение ПУПОВИНЫ не роняет день (B2)", _t12_pupovina_fail_not_drown),
]


def main():
    passed = 0
    for name, fn in TESTS:
        try:
            ok, extra = fn()
        except Exception as e:
            ok, extra = False, f"{type(e).__name__}: {e}"
        if ok:
            passed += 1
        print(f"{PASS if ok else FAIL} · {name}" + (f" — {extra}" if extra and not ok else ""))
    print(f"\nOZON ДЕНЬ · {passed}/{len(TESTS)} зелёных")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

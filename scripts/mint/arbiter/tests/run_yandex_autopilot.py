#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARBITER АВТОПИЛОТ (СУХОЙ) — ПРИЁМКА. Законы, а не «оно запустилось». Сухо, 0₽, без сети.

Главный закон органа-руки: автопилот ФИЗИЧЕСКИ не умеет в боевой режим.

  A1  hard_dry_invariant     — run() зовёт run_day СТРОГО dry=True, commit=False (RUBICON)
  A2  no_commit_path         — у run() НЕТ параметра commit; в исходнике нет commit=True (структурно)
  A3  log_written            — прогон оставляет читаемый след: отчёт + строка JSON с фактами
  A4  log_failsoft           — если рендер отчёта упал, лог всё равно пишется, автопилот не падает
  A5  head_source_wired      — 'none' → носа спроса нет (None); 'wb' → ленивый thunk построен
  A6  result_shape_honest    — итог несёт dry/commit/businessId/провалы — не врёт о режиме
"""
import os
import sys
import inspect
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
SCRIPTS = MINT.parent
for p in (str(ARB), str(MINT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_autopilot_v1 as ap        # noqa: E402
import ymarket_report_v1 as report       # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _fake_day(**kw):
    """Стаб суточного цикла: НИЧЕГО не читает, возвращает минимум + эхо режима (для проверки закона)."""
    return {"ts": "2026-08-16T00:00:00+00:00", "date": "2026-08-16", "ok": True,
            "dry": kw.get("dry"), "commit": kw.get("commit"),
            "business_id_known": True, "campaign_id_known": True,
            "failures": [], "burning": {"count": 0, "items": []},
            "kpis": {"quality_index": None},
            "_captured": kw}


def _with_stub_day(fn):
    """Подменить ap.day.run_day на стаб, вернуть (результат, captured_kwargs). Всегда восстанавливает."""
    old = ap.day.run_day
    captured = {}

    def cap(**kw):
        captured.clear()
        captured.update(kw)
        return _fake_day(**kw)

    ap.day.run_day = cap
    try:
        res = fn()
    finally:
        ap.day.run_day = old
    return res, captured


def _tmp_log():
    fd, p = tempfile.mkstemp(prefix="ap_log_", suffix=".log")
    os.close(fd)
    os.environ["ARBITER_AUTOPILOT_LOG"] = p
    return Path(p)


# ─────────────────────────── ТЕСТЫ ───────────────────────────

def a1_hard_dry_invariant():
    """RUBICON: как бы ни звали — цикл получает dry=True, commit=False. Иначе автопилот опасен."""
    _tmp_log()
    (res, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
    ok = cap.get("dry") is True and cap.get("commit") is False
    return ok, f"переданное в run_day: dry={cap.get('dry')} commit={cap.get('commit')}"


def a2_no_commit_path():
    """Структурно: у run() нет ручки commit, и в исходнике модуля не встречается commit=True."""
    params = list(inspect.signature(ap.run).parameters)
    no_param = "commit" not in params
    src = inspect.getsource(ap)
    no_true = "commit=True" not in src and "commit = True" not in src
    return no_param and no_true, f"params={params} · нет commit=True в исходнике={no_true}"


def a3_log_written():
    """След прогона: файл лога получает и человеческий отчёт, и машинную строку JSON с фактами."""
    lp = _tmp_log()
    report.render_day = lambda d, **k: "СТАБ-ОТЧЁТ-ДНЯ"      # изолируем от реального рендера
    (res, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
    txt = lp.read_text(encoding="utf-8")
    ok = "СТАБ-ОТЧЁТ-ДНЯ" in txt and "JSON" in txt and '"commit"' in txt and '"dry"' in txt
    return ok, f"в логе есть отчёт+JSON+режим: {ok} (размер {len(txt)}б)"


def a4_log_failsoft():
    """Рендер отчёта упал → лог всё равно пишется («отчёт не отрендерился»), автопилот НЕ падает."""
    lp = _tmp_log()

    def boom(d, **k):
        raise RuntimeError("рендер намеренно упал")

    report.render_day = boom
    try:
        (res, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
        survived = res.get("dry") is True
    except Exception as e:
        return False, f"автопилот упал вместе с рендером: {type(e).__name__}: {e}"
    txt = lp.read_text(encoding="utf-8")
    ok = survived and "не отрендерился" in txt
    return ok, f"пережил падение рендера={survived}, причина в логе={'не отрендерился' in txt}"


def a5_head_source_wired():
    """none → носа спроса нет (fn=None); wb → построен ленивый thunk (callable), сеть НЕ трогается."""
    _tmp_log()
    report.render_day = lambda d, **k: "x"
    (_, cap_none) = _with_stub_day(lambda: ap.run(head_source="none"))
    none_ok = cap_none.get("head_source_fn") is None
    (_, cap_wb) = _with_stub_day(lambda: ap.run(head_source="wb"))
    fn = cap_wb.get("head_source_fn")
    wb_ok = callable(fn)          # thunk построен; сеть будет только при его вызове (его тут не зовём)
    return none_ok and wb_ok, f"none→fn None={none_ok} · wb→thunk callable={wb_ok}"


def a6_result_shape_honest():
    """Итог не врёт о режиме: dry=True, commit=False и присутствуют факты кабинета/провалов."""
    _tmp_log()
    report.render_day = lambda d, **k: "x"
    (res, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
    keys = {"dry", "commit", "business_id_known", "failures", "burning"}
    ok = res.get("dry") is True and res.get("commit") is False and keys.issubset(res)
    return ok, f"dry={res.get('dry')} commit={res.get('commit')} ключи-полны={keys.issubset(res)}"


def a7_zaliv_wired_by_default():
    """Залив живёт САМ: без env preflight_fn всё равно ленивый thunk (не None) — цикл не ждёт команды."""
    _tmp_log()
    report.render_day = lambda d, **k: "x"
    for k in ("YM_ZALIV_DONOR", "YM_ZALIV_SLUG"):
        os.environ.pop(k, None)          # гарантируем чистоту: env НЕ задан
    (_, cap) = _with_stub_day(lambda: ap.run(head_source="none"))
    fn = cap.get("preflight_fn")
    wired = callable(fn)                 # thunk построен лениво; сеть/файлы — только при его вызове (его не зовём)
    # дефолтная пара не пуста и реальна (документированный контракт двух слагов, F6)
    d, s = ap._ZALIV_DEFAULT_DONOR, ap._ZALIV_DEFAULT_SLUG
    ok = wired and bool(d) and bool(s) and d != s
    return ok, f"preflight_fn callable={wired} · дефолт донор={d!r} slug={s!r}"


TESTS = [
    ("A1  hard_dry_invariant", a1_hard_dry_invariant),
    ("A2  no_commit_path", a2_no_commit_path),
    ("A3  log_written", a3_log_written),
    ("A4  log_failsoft", a4_log_failsoft),
    ("A5  head_source_wired", a5_head_source_wired),
    ("A6  result_shape_honest", a6_result_shape_honest),
    ("A7  zaliv_wired_by_default", a7_zaliv_wired_by_default),
]


def main():
    print("🎯 ARBITER АВТОПИЛОТ (СУХОЙ) · ПРИЁМКА — автопилот не умеет в боевой режим (0₽)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<24} {detail}")
        passed += 1 if ok else 0
    # прибрать за собой env, чтобы не течь в соседние прогоны
    os.environ.pop("ARBITER_AUTOPILOT_LOG", None)
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Автопилот честен: RUBICON зашит физически (только dry), след пишется, "
              "нос спроса ленив, режим не врётся")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

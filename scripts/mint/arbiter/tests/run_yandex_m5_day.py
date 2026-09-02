#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЯНДЕКС M5 ПРИЁМКА — СТРАТЕГ + ТРЕНД-СКАУТ + суточный цикл + отчёт (сухо, 0₽, без сети).

Приёмка проверяет ЗАКОНЫ, а не «оно запустилось». Каждый тест сформулирован так, чтобы его можно
было провалить: нарушил закон → FAIL, а не мягкое предупреждение.

  СТРАТЕГ
    S1  no_number_no_lie      — нет данных → expected_rub=None + needs_source (G1), НЕ выдуманное ₽
    S2  rank_by_money_effort  — ранг по ₽/усилие; посчитанные выше «ждущих источник» (G4)
    S3  every_move_actionable — у каждого хода есть next_action и owner (G5)
    S4  dead_cards_counted    — мёртвые карточки найдены и посчитаны средним чеком (рычаг №1)
    S5  ceiling_not_promise   — формула присутствует у каждого числа (G6: потолок, не обещание)

  ТРЕНД-СКАУТ
    T1  no_source_no_trend    — без адаптера кандидатов НЕТ и сказано какой источник нужен (T1)
    T2  stale_signal_skipped  — сигнал старше 14 дн → stale, вход запрещён (T2)
    T3  noise_not_trend       — меньше 3 точек → noise, не тренд (T5)
    T4  late_window_skipped   — много продавцов + слабый рост → late, не входим (T3)
    T5  risk_cap_respected    — без лимита оператора ставка 0₽ (T4)
    T6  x_multiplier_honest   — нет закупки/цены → множитель None, не выдумка

  СУТОЧНЫЙ ЦИКЛ
    D1  role_failure_survived — упавшая роль не роняет день, провал виден в отчёте (B2)
    D2  delta_vs_yesterday    — дельта считается из журнала; нет вчера → пусто, не «0»
    D3  burning_first         — горящее попадает в burning с владельцем и действием
    D4  dry_by_default        — цикл сухой: наружу ничего, деньги не двигаются

  ОТЧЁТ
    R1  no_creds_no_lie       — без токена sent=False и честная причина (не «отправлено»)
    R2  unknown_index_loud    — непрочитанный индекс назван опаснее низкого, не замолчан
    R3  long_report_chunked   — отчёт длиннее 4096 режется по строкам (лимит Телеграма)
"""
import os
import sys
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
SCRIPTS = MINT.parent
for p in (str(ARB), str(MINT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_role_strategist_v1 as strategist   # noqa: E402
import ymarket_role_trendscout_v1 as trend        # noqa: E402
import ymarket_day_v1 as day_mod                  # noqa: E402
import ymarket_report_v1 as report                # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


# ─────────────────────────── СТРАТЕГ ───────────────────────────

def s1_no_number_no_lie():
    """G1: нечего считать → честный None + запрос источника, НЕ выдуманное число."""
    res = strategist.plan({"skus": {}}, None, target_sku=None)
    moves = res["moves"]
    invented = [m for m in moves if m["expected_rub"] is not None and not m["facts"]]
    has_need = any(m.get("needs_source") for m in moves)
    return (not invented) and has_need, \
        f"ходов={len(moves)}, выдуманных чисел={len(invented)}, запрос источника={has_need}"


def s2_rank_by_money_effort():
    """G4: посчитанные ходы идут раньше «ждущих источник», внутри — по ₽/усилие."""
    doc = {"skus": {
        "A": {"status": "NO_CARD_ERRORS", "margin": {"price_sell": 1000}},
        "B": {"status": "PUBLISHED", "margin": {"price_sell": 1000}, "content_rating": 50},
    }}
    res = strategist.plan(doc, None, target_sku=None)
    scored = [m for m in res["moves"] if m["score"] is not None]
    unscored = [m for m in res["moves"] if m["score"] is None]
    order_ok = True
    if scored and unscored:
        first_unscored = res["moves"].index(unscored[0])
        last_scored = max(res["moves"].index(m) for m in scored)
        order_ok = last_scored < first_unscored
    desc = all(scored[i]["score"] >= scored[i + 1]["score"] for i in range(len(scored) - 1))
    return order_ok and desc, f"с числом={len(scored)} без={len(unscored)} порядок_ок={order_ok} убыв={desc}"


def s3_every_move_actionable():
    """G5: ход без next_action и owner — мечта, а не стратегия."""
    doc = {"skus": {"A": {"status": "NO_CARD_ERRORS", "margin": {"price_sell": 500}}}}
    res = strategist.plan(doc, {"steps": {"STOCKMAN": {"unknown_source": 3}}}, target_sku=10)
    bad = [m["lever"] for m in res["moves"] if not m.get("next_action") or not m.get("owner")]
    return not bad, f"ходов={len(res['moves'])}, без действия/владельца={bad}"


def s4_dead_cards_counted():
    """Рычаг №1: мёртвые карточки найдены, потолок = число × средний чек."""
    doc = {"skus": {
        "A": {"status": "HAS_CARD_CAN_UPDATE_ERRORS", "margin": {"price_sell": 200}},
        "B": {"status": "NO_CARD_ERRORS", "margin": {"price_sell": 400}},
        "C": {"status": "PUBLISHED", "margin": {"price_sell": 300}},
    }}
    res = strategist.plan(doc, None)
    dead = [m for m in res["moves"] if m["lever"] == "DEAD_CARD_REVIVE"]
    ok = bool(dead) and dead[0]["facts"]["count"] == 2 and dead[0]["expected_rub"] == 2 * 300.0
    return ok, f"мёртвых={dead[0]['facts']['count'] if dead else '—'} потолок={dead[0]['expected_rub'] if dead else '—'}₽"


def s5_ceiling_not_promise():
    """G6: у каждого числа есть формула — иначе это обещание, а не оценка."""
    doc = {"skus": {"A": {"status": "NO_CARD_ERRORS", "margin": {"price_sell": 100}}}}
    res = strategist.plan(doc, None, target_sku=5)
    no_formula = [m["lever"] for m in res["moves"] if not m.get("formula")]
    return not no_formula, f"ходов={len(res['moves'])}, без формулы={no_formula}"


# ─────────────────────────── ТРЕНД-СКАУТ ───────────────────────────

def t1_no_source_no_trend():
    """T1: без адаптера — честный ноль кандидатов + указание, какой источник нужен."""
    res = trend.scan(source_fn=None)
    return (res["ok"] is False and res["reason"] == "NO_TREND_SOURCE"
            and not res["candidates"] and bool(res["need_source"])), \
        f"ok={res['ok']} кандидатов={len(res['candidates'])} источник_запрошен={bool(res['need_source'])}"


def t2_stale_signal_skipped():
    """T2: сигнал старше срока годности — вход запрещён."""
    w = trend.classify_window([10, 20, 40], sellers=3, age_days=30)
    return w["phase"] == "stale" and w["action"] == "SKIP", f"фаза={w['phase']} действие={w['action']}"


def t3_noise_not_trend():
    """T5: одиночный всплеск без истории — шум."""
    w = trend.classify_window([10, 90], sellers=2, age_days=1)
    return w["phase"] == "noise" and w["action"] == "SKIP", f"фаза={w['phase']}"


def t4_late_window_skipped():
    """T3: рынок насыщен и рост слабый → поздно, не входим (даже если красиво)."""
    w = trend.classify_window([100, 102, 104], sellers=80, age_days=1)
    return w["phase"] == "late" and w["action"] == "SKIP", f"фаза={w['phase']} рост={w.get('growth')}"


def t5_risk_cap_respected():
    """T4: лимита риска нет → рекомендуем 0₽ (роль не тратит чужие деньги)."""
    src = lambda: [{"name": "хайп", "points": [10, 20, 40], "sellers": 3, "age_days": 1,  # noqa: E731
                    "cost_buy": 100, "price_sell": 1000, "source": "тест"}]
    no_cap = trend.scan(source_fn=src, risk_cap_rub=None)
    with_cap = trend.scan(source_fn=src, risk_cap_rub=10000)
    a = no_cap["candidates"][0]["position"]["amount_rub"] if no_cap["candidates"] else None
    b = with_cap["candidates"][0]["position"]["amount_rub"] if with_cap["candidates"] else None
    return a == 0 and b == 2500.0, f"без лимита={a}₽ с лимитом 10000₽ → {b}₽ (≤25% на одного)"


def t6_x_multiplier_honest():
    """Нет закупки/цены → множитель None, не выдуманный «х10»."""
    src = lambda: [{"name": "без цен", "points": [1, 2, 4], "sellers": 2, "age_days": 1,  # noqa: E731
                    "source": "тест"}]
    res = trend.scan(source_fn=src, risk_cap_rub=1000)
    c = res["candidates"][0] if res["candidates"] else {}
    return c.get("margin_x") is None and bool(c.get("margin_note")), \
        f"множитель={c.get('margin_x')} пометка={bool(c.get('margin_note'))}"


# ─────────────────────────── СУТОЧНЫЙ ЦИКЛ ───────────────────────────

def _tmp_journal():
    fd, path = tempfile.mkstemp(prefix="ymday_", suffix=".jsonl")
    os.close(fd)
    os.remove(path)
    return path


def d1_role_failure_survived():
    """B2: упавшая роль НЕ роняет день; её провал виден в отчёте (не замолчан)."""
    os.environ["YM_DAY_JOURNAL"] = _tmp_journal()

    def boom(*a, **kw):
        raise RuntimeError("бригада упала намеренно")

    d = day_mod.run_day(shift_fn=boom, tick_fn=False, remember=False, use_env=False)
    survived = isinstance(d, dict) and "kpis" in d
    visible = any("упал" in f for f in d.get("failures", []))
    return survived and visible and d["ok"] is False, \
        f"день собран={survived} провал_виден={visible} ok={d.get('ok')}"


def d2_delta_vs_yesterday():
    """Нет вчера → дельта пустая (не «0 изменений»); есть вчера → считается."""
    jp = _tmp_journal()
    os.environ["YM_DAY_JOURNAL"] = jp
    d1 = day_mod.run_day(shift_fn=False, tick_fn=False, remember=True, use_env=False)
    empty_first = d1["delta"] == {}
    Path(jp).write_text(json.dumps({"ts": "x", "date": "вчера",
                                    "kpis": {"cards_tracked": 5, "cards_live": 1},
                                    "burning": 0, "top_move": None}, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    d2 = day_mod.run_day(shift_fn=False, tick_fn=False, remember=False, use_env=False)
    counted = d2["delta"].get("cards_tracked") == (d2["kpis"]["cards_tracked"] or 0) - 5
    return empty_first and counted, \
        f"без вчера дельта пуста={empty_first} с вчера посчитана={counted} ({d2['delta'].get('cards_tracked')})"


def d3_burning_first():
    """Горящее попадает в burning с владельцем и действием (это то, что нельзя отложить)."""
    os.environ["YM_DAY_JOURNAL"] = _tmp_journal()
    fake_shift = lambda *a, **kw: {  # noqa: E731
        "steps": {"DISPATCHER": {"ok": True, "urgent": 3},
                  "CONTROLLER": {"ok": True, "rating": 35}},
        "escalations": [{"role": "STOCKMAN", "kind": "NO_STOCK_SOURCE",
                         "why": "источник наличия неизвестен", "action": "OPERATOR_INPUT"}],
        "errors": []}
    d = day_mod.run_day(shift_fn=fake_shift, tick_fn=False, remember=False, use_env=False)
    items = d["burning"]["items"]
    has_shutdown = any("отключат" in (i.get("what") or "") for i in items)
    has_orders = any("горят" in (i.get("what") or "") for i in items)
    all_owned = all(i.get("owner") for i in items)
    return has_shutdown and has_orders and all_owned and d["burning"]["count"] >= 3, \
        f"горит={d['burning']['count']} отключение={has_shutdown} заказы={has_orders} все_с_владельцем={all_owned}"


def d4_dry_by_default():
    """Цикл по умолчанию сухой: dry=True, commit=False — наружу ничего, деньги не двигаются."""
    os.environ["YM_DAY_JOURNAL"] = _tmp_journal()
    d = day_mod.run_day(shift_fn=False, tick_fn=False, remember=False, use_env=False)
    return d["dry"] is True and d["commit"] is False, f"dry={d['dry']} commit={d['commit']}"


# ─────────────────────────── ОТЧЁТ ───────────────────────────

def r1_no_creds_no_lie():
    """Без токена — sent=False и честная причина. Никогда не рапортуем «отправлено»."""
    for k in ("YM_TELEGRAM_BOT_TOKEN", "YM_TELEGRAM_CHAT_ID"):
        os.environ.pop(k, None)
    res = report.send_telegram("тест")
    return res["sent"] is False and res["reason"] == "NO_CREDS" and bool(res["note"]), \
        f"sent={res['sent']} причина={res['reason']}"


def r2_unknown_index_loud():
    """Непрочитанный индекс качества назван опасным, а не замолчан."""
    day = {"date": "2026-08-08", "dry": True, "kpis": {"quality_index": None, "cards_errored": 0},
           "delta": {}, "burning": {"count": 0, "items": []}, "growth": {}, "roles": {}, "failures": []}
    txt = report.render_day(day)
    return "НЕ ПРОЧИТАН" in txt and "опаснее" in txt, "непрочитанный индекс назван опасным"


def r3_long_report_chunked():
    """Отчёт длиннее лимита Телеграма режется по строкам, а не обрывается."""
    long_text = "\n".join(f"строка {i} " + "x" * 80 for i in range(200))
    parts = report._chunks(long_text)
    all_fit = all(len(p) <= report.TG_LIMIT for p in parts)
    nothing_lost = sum(len(p.split("\n")) for p in parts) == len(long_text.split("\n"))
    return len(parts) > 1 and all_fit and nothing_lost, \
        f"кусков={len(parts)} все влезают={all_fit} строки не потеряны={nothing_lost}"


TESTS = [
    ("S1  no_number_no_lie", s1_no_number_no_lie),
    ("S2  rank_by_money_effort", s2_rank_by_money_effort),
    ("S3  every_move_actionable", s3_every_move_actionable),
    ("S4  dead_cards_counted", s4_dead_cards_counted),
    ("S5  ceiling_not_promise", s5_ceiling_not_promise),
    ("T1  no_source_no_trend", t1_no_source_no_trend),
    ("T2  stale_signal_skipped", t2_stale_signal_skipped),
    ("T3  noise_not_trend", t3_noise_not_trend),
    ("T4  late_window_skipped", t4_late_window_skipped),
    ("T5  risk_cap_respected", t5_risk_cap_respected),
    ("T6  x_multiplier_honest", t6_x_multiplier_honest),
    ("D1  role_failure_survived", d1_role_failure_survived),
    ("D2  delta_vs_yesterday", d2_delta_vs_yesterday),
    ("D3  burning_first", d3_burning_first),
    ("D4  dry_by_default", d4_dry_by_default),
    ("R1  no_creds_no_lie", r1_no_creds_no_lie),
    ("R2  unknown_index_loud", r2_unknown_index_loud),
    ("R3  long_report_chunked", r3_long_report_chunked),
]


def main():
    print("🎯 ЯНДЕКС M5 ПРИЁМКА · СТРАТЕГ + ТРЕНД-СКАУТ + суточный цикл + отчёт (сухо, 0₽)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<26} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Законы держат: числа не выдумываются, окна не путаются, провал роли виден, "
              "отчёт не врёт о доставке")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

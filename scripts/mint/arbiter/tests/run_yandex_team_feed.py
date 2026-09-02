#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЯНДЕКС ПРИЁМКА — ТГ КОМАНДЫ + KPI DAY/WEEK/MONTH (сухо, 0₽, без сети).

Проверяем ЗАКОНЫ, не «запустилось». Каждый тест падает при нарушении закона.

  KPI (ymarket_kpi_v1)
    K1  empty_no_lie        — пустой журнал → «истории не хватает», НЕ выдуманные нули
    K2  window_bounds       — DAY/WEEK/MONTH берут ровно свои календарные окна (1/7/30 дн)
    K3  trend_direction     — тренд к цели помечен ✅, от цели ❗ (рост виден в сравнении)
    K4  null_field_omitted  — KPI, которого нет ни в одном дне, не рисуется (нет числа — нет строки)

  ТГ КОМАНДЫ (ymarket_team_feed_v1)
    F1  each_role_own_post  — у каждой роли своё сообщение, подписанное её именем (name_ru)
    F2  failure_is_a_line   — упавшая роль — это строка «не смог», а не тишина (B4)
    F3  no_creds_no_lie     — без токена sent=False + NO_CREDS, ни один пост не «отправлен»
    F4  separate_messages   — каждый пост уходит ОТДЕЛЬНЫМ sendMessage (в этом весь смысл)
    F5  head_and_tail       — первый пост БРИГАДИР (открытие), последний УПРАВЛЯЮЩИЙ с KPI
    F6  rubicon_tg_only     — фид трогает ТОЛЬКО телеграм, ни одной записи в маркетплейс
"""
import os
import sys
from pathlib import Path
from datetime import date

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
SCRIPTS = MINT.parent
for p in (str(ARB), str(MINT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_kpi_v1 as kpi                # noqa: E402
import ymarket_team_feed_v1 as feed         # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


TODAY = date(2026, 8, 11)
# Журнал с датами вокруг today: 07-10 (вне месяца), 07-20/08-04 (в месяце), 08-05/08-10/08-11 (в неделе).
ROWS = [
    {"date": "2026-07-10", "kpis": {"cards_tracked": 1, "cards_live": 0, "cards_errored": 5}, "burning": 1},
    {"date": "2026-07-20", "kpis": {"cards_tracked": 2, "cards_live": 1, "cards_errored": 3}, "burning": 1},
    {"date": "2026-08-04", "kpis": {"cards_tracked": 3, "cards_live": 2, "cards_errored": 3}, "burning": 0},
    {"date": "2026-08-05", "kpis": {"cards_tracked": 4, "cards_live": 2, "cards_errored": 2}, "burning": 1},
    {"date": "2026-08-10", "kpis": {"cards_tracked": 5, "cards_live": 3, "cards_errored": 1}, "burning": 0},
    {"date": "2026-08-11", "kpis": {"cards_tracked": 6, "cards_live": 3, "cards_errored": 1}, "burning": 1},
]


def _day():
    """Синтетический дневной отчёт в форме ymarket_day_v1.run_day (с упавшей и пропущенной ролью)."""
    return {
        "date": "2026-08-11", "dry": True, "commit": False,
        "kpis": {"cards_tracked": 6, "cards_live": 3, "cards_live_verified": 0,
                 "cards_errored": 1, "avg_content_rating": None, "quality_index": None, "urgent_orders": 2},
        "delta": {}, "escalations": [{"role": "STOCKMAN", "kind": "NO_STOCK_SOURCE"}], "failures": [],
        "burning": {"count": 2, "items": [{"what": "2 заказов горят", "owner": "ОПЕРАТОР"}]},
        "growth": {"top_move": "ASSORTMENT_WIDEN", "top_move_action": "расширить ассортимент",
                   "next_lawful_step": "проставить остаток+цену на 1 товар в Москве"},
        "roles": {
            "BRIGADE": {"ok": True,
                        "human": {"DISPATCHER": "по заказам: 2 горят по таймеру",
                                  "STOCKMAN": "остатки: источник неизвестен → ноль",
                                  "CONTROLLER": "индекс: НЕ ПРОЧИТАН"},
                        "steps": {"DISPATCHER": {"ok": True, "urgent": 2},
                                  "STOCKMAN": {"ok": True},
                                  "MERCHANDISER": {"ok": False, "error": "боом"},
                                  "PRICER": {"skipped": True, "why": "нет позиций на витрине"},
                                  "CONTROLLER": {"ok": True}}},
            "STRATEGIST": {"ok": True, "human": "куда растём: расширить ассортимент, потолок не посчитан"},
            "TRENDSCOUT": {"ok": True, "human": "тренды: источник не подключён — честный ноль"},
            "MANAGER_TICK": {"ok": True, "action": "NOOP"},
        },
    }


# ─────────────────────────── KPI ───────────────────────────

def k1_empty_no_lie():
    r = kpi.rollup(7, rows=[], today=TODAY)
    txt = kpi.render_all(rows=[], today=TODAY)
    return r.get("_empty") is True and r["days_present"] == 0 and "журнал пуст" in txt, \
        f"_empty={r.get('_empty')} дней={r['days_present']}"


def k2_window_bounds():
    d = kpi.rollup(1, rows=ROWS, today=TODAY)["days_present"]
    w = kpi.rollup(7, rows=ROWS, today=TODAY)["days_present"]
    m = kpi.rollup(30, rows=ROWS, today=TODAY)["days_present"]
    return (d, w, m) == (1, 3, 5), f"DAY={d} WEEK={w} MONTH={m} (ждём 1/3/5)"


def k3_trend_direction():
    m = kpi.rollup(30, rows=ROWS, today=TODAY)
    err = m["fields"]["cards_errored"]      # 3→1, цель вниз → хорошо
    live = m["fields"]["cards_live"]        # 1→3, цель вверх → хорошо
    good_err = err["trend"] == -2 and "✅" in kpi._trend_mark(err)
    good_live = live["trend"] == 2 and "✅" in kpi._trend_mark(live)
    bad = kpi._trend_mark({"trend": 2, "dir": -1, "unit": ""})   # рост там, где цель падать
    return good_err and good_live and "❗" in bad, \
        f"errored trend={err['trend']}{kpi._trend_mark(err)} live trend={live['trend']}{kpi._trend_mark(live)} bad={bad}"


def k4_null_field_omitted():
    m = kpi.rollup(30, rows=ROWS, today=TODAY)
    qi = m["fields"]["quality_index"]       # нет ни в одном дне
    txt = kpi.render_window("МЕСЯЦ", m)
    return qi["known_days"] == 0 and qi["last"] is None and "индекс качества" not in txt, \
        f"known_days={qi['known_days']} last={qi['last']} строки нет={'индекс качества' not in txt}"


def k5_runs_are_not_days():
    """Два прогона за одни сутки — это ОДИН день, а не два (последний снимок дня побеждает)."""
    two_runs = [
        {"date": "2026-08-11", "kpis": {"cards_live": 1}, "burning": 1},
        {"date": "2026-08-11", "kpis": {"cards_live": 3}, "burning": 1},
    ]
    r = kpi.rollup(1, rows=two_runs, today=TODAY)
    live = r["fields"]["cards_live"]
    return r["days_present"] == 1 and r["burning_days"] == 1 and live["last"] == 3, \
        f"дней={r['days_present']} дней_с_горит={r['burning_days']} last={live['last']} (ждём 1/1/3)"


def k6_malformed_row_fail_soft():
    """Строка журнала — валидный JSON, но НЕ объект (число/строка/массив/null) → не роняем KPI (L6)."""
    bad = [42, "hello", [1, 2, 3], None,
           {"date": "2026-08-11", "kpis": {"cards_live": 3}}]  # один нормальный день
    try:
        r = kpi.rollup(1, rows=bad, today=TODAY)
        txt = kpi.render_all(rows=bad, today=TODAY)
        line = kpi.summary_line(rows=bad, today=TODAY)
    except Exception as e:
        return False, f"упал на битой строке: {type(e).__name__}: {e}"
    good_day_counts = r["days_present"] == 1 and r["fields"]["cards_live"]["last"] == 3
    return good_day_counts and "живых карточек" in txt and line.startswith("KPI"), \
        f"дней={r['days_present']} live={r['fields']['cards_live']['last']} (мусор молча выкинут, хороший день цел)"


def k7_non_dict_kpis_fail_soft():
    """Дата валидна, но kpis — не словарь (truthy строка) → не роняем, поле считаем отсутствующим (L6)."""
    rows = [{"date": "2026-08-11", "kpis": "corrupt"}]
    try:
        r = kpi.rollup(1, rows=rows, today=TODAY)
        kpi.render_all(rows=rows, today=TODAY)
    except Exception as e:
        return False, f"упал на kpis-не-словаре: {type(e).__name__}: {e}"
    cl = r["fields"]["cards_live"]
    return r["days_present"] == 1 and cl["last"] is None and cl["known_days"] == 0, \
        f"дней={r['days_present']} last={cl['last']} known={cl['known_days']} (день есть, чисел нет)"


def k8_ts_tiebreak_same_day():
    """Два снимка одних суток НЕ в порядке дозаписи → побеждает поздний по ts, а не по позиции в файле (L5)."""
    rows = [
        {"date": "2026-08-11", "ts": "2026-08-11T20:00:00+00:00", "kpis": {"cards_live": 12}},  # вечер, истинно последний
        {"date": "2026-08-11", "ts": "2026-08-11T08:00:00+00:00", "kpis": {"cards_live": 5}},   # утро, раньше
    ]
    r = kpi.rollup(1, rows=rows, today=TODAY)
    live = r["fields"]["cards_live"]
    return r["days_present"] == 1 and live["last"] == 12, \
        f"дней={r['days_present']} last={live['last']} (ждём поздний ts=12, не позицию=5)"


# ─────────────────────────── ТГ КОМАНДЫ ───────────────────────────

def f1_each_role_own_post():
    posts = feed.build_posts(_day(), rows=ROWS, today=TODAY)
    disp = [p for p in posts if p["role"] == "DISPATCHER"]
    signed = all(p["text"].startswith(f"{p['emoji']} {p['name_ru']}") for p in posts)
    # 1 БРИГАДИР + 5 ролей смены + СТРАТЕГ + ТРЕНД-СКАУТ + УПРАВЛЯЮЩИЙ = 9
    return (len(posts) == 9 and disp and disp[0]["name_ru"] == "ДИСПЕТЧЕР"
            and "🚚 ДИСПЕТЧЕР" in disp[0]["text"] and signed), \
        f"постов={len(posts)} диспетчер_подписан={bool(disp)} все_подписаны={signed}"


def f2_failure_is_a_line():
    posts = feed.build_posts(_day(), rows=ROWS, today=TODAY)
    merch = [p for p in posts if p["role"] == "MERCHANDISER"]
    pricer = [p for p in posts if p["role"] == "PRICER"]
    fail_visible = merch and merch[0]["kind"] == "fail" and "не смог" in merch[0]["text"]
    skip_visible = pricer and pricer[0]["kind"] == "skip" and "пропущено" in pricer[0]["text"]
    return bool(fail_visible and skip_visible), \
        f"провал_виден={bool(fail_visible)} пропуск_виден={bool(skip_visible)}"


def f3_no_creds_no_lie():
    for k in ("YM_TELEGRAM_BOT_TOKEN", "YM_TELEGRAM_CHAT_ID"):
        os.environ.pop(k, None)
    posts = feed.build_posts(_day(), rows=ROWS, today=TODAY)
    res = feed.send_feed(posts, echo=False)
    none_sent = all(r["sent"] is False for r in res["results"])
    return res["sent"] is False and res["reason"] == "NO_CREDS" and none_sent, \
        f"sent={res['sent']} reason={res.get('reason')} ни один не отправлен={none_sent}"


def f4_separate_messages():
    calls = []

    def stub(token, method, **kw):
        calls.append((method, kw.get("chat_id")))
        return {"ok": True}

    posts = feed.build_posts(_day(), rows=ROWS, today=TODAY)
    res = feed.send_feed(posts, token="T", chat_id="C", send_fn=stub, echo=False)
    return res["sent"] is True and len(calls) == len(posts) == res["sent_count"], \
        f"постов={len(posts)} отправок={len(calls)} sent_count={res['sent_count']}"


def f5_head_and_tail():
    posts = feed.build_posts(_day(), rows=ROWS, today=TODAY)
    head_ok = posts[0]["role"] == "BRIGADE" and posts[0]["kind"] == "head"
    tail = posts[-1]
    tail_ok = (tail["role"] == "MANAGER" and tail["kind"] == "manager"
               and "KPI ДЕНЬ" in tail["text"] and "KPI DAY / WEEK / MONTH" in tail["text"]
               and "Следующий шаг" in tail["text"])
    return head_ok and tail_ok, f"голова={head_ok} хвост_с_KPI={tail_ok}"


def f6_rubicon_tg_only():
    """Фид — внутренняя телеметрия: единственный сетевой вызов — sendMessage. Никаких записей в маркетплейс."""
    methods = []

    def stub(token, method, **kw):
        methods.append(method)
        return {"ok": True}

    posts = feed.build_posts(_day(), rows=ROWS, today=TODAY)
    feed.send_feed(posts, token="T", chat_id="C", send_fn=stub, echo=False)
    only_tg = bool(methods) and all(m == "sendMessage" for m in methods)
    return only_tg, f"методов={set(methods)} только sendMessage={only_tg}"


def f7_malformed_day_fail_soft():
    """Битый/частичный day (не-словарь на месте dict-полей) → фид НЕ падает, а деградирует (L6)."""
    garbage = [
        {"date": "2026-08-11", "roles": [1, 2, 3]},                         # roles не словарь
        {"date": "2026-08-11", "roles": {"BRIGADE": {"human": [1, 2], "steps": {}}}},  # human не словарь
        {"date": "2026-08-11", "roles": {"STRATEGIST": {"human": [9]}}},    # human роли не строка
        {"date": "2026-08-11", "roles": {}, "burning": 5},                  # burning не словарь
        {"date": "2026-08-11", "roles": {}, "kpis": [1, 2, 3]},             # kpis не словарь
        {"date": "2026-08-11", "roles": {}, "growth": "x"},                 # growth не словарь
        {"date": "2026-08-11", "roles": {}, "escalations": 7},              # escalations не список
        [1, 2, 3],                                                         # day вообще не словарь
    ]
    for g in garbage:
        try:
            posts = feed.build_posts(g, rows=ROWS, today=TODAY)
        except Exception as e:
            return False, f"упал на {str(g)[:40]}: {type(e).__name__}: {e}"
        # всегда есть хотя бы закрывающий пост УПРАВЛЯЮЩЕГО, никто не постит пустоту
        if not posts or posts[-1]["role"] != "MANAGER":
            return False, f"на {str(g)[:40]} нет хвоста УПРАВЛЯЮЩЕГО: {[p['role'] for p in posts]}"
    return True, f"{len(garbage)} битых форм day пережиты, каждая закрыта УПРАВЛЯЮЩИМ"


TESTS = [
    ("K1  empty_no_lie", k1_empty_no_lie),
    ("K2  window_bounds", k2_window_bounds),
    ("K3  trend_direction", k3_trend_direction),
    ("K4  null_field_omitted", k4_null_field_omitted),
    ("K5  runs_are_not_days", k5_runs_are_not_days),
    ("K6  malformed_row_soft", k6_malformed_row_fail_soft),
    ("K7  non_dict_kpis_soft", k7_non_dict_kpis_fail_soft),
    ("K8  ts_tiebreak_day", k8_ts_tiebreak_same_day),
    ("F1  each_role_own_post", f1_each_role_own_post),
    ("F2  failure_is_a_line", f2_failure_is_a_line),
    ("F3  no_creds_no_lie", f3_no_creds_no_lie),
    ("F4  separate_messages", f4_separate_messages),
    ("F5  head_and_tail", f5_head_and_tail),
    ("F6  rubicon_tg_only", f6_rubicon_tg_only),
    ("F7  malformed_day_soft", f7_malformed_day_fail_soft),
]


def main():
    print("🎯 ЯНДЕКС ПРИЁМКА · ТГ КОМАНДЫ + KPI DAY/WEEK/MONTH (сухо, 0₽, без сети)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<22} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Каждый фиксирует своё, провал виден, KPI DAY/WEEK/MONTH честны, RUBICON цел (только ТГ)")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

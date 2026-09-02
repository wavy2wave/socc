#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ТГ КОМАНДЫ (ymarket_team_feed_v1) — каждый в команде фиксирует своё действие сам.

Оператор дословно: «Я зашёл и вижу как каждый свои действия фиксируют!! И это круто и законно.»
Отчёт управляющего (ymarket_report_v1) — это ОДИН голос. А тут другое: смена органа раскладывается
на ОТДЕЛЬНЫЕ сообщения — БРИГАДИР открыл смену, ДИСПЕТЧЕР доложил по заказам, СКЛАДОВЩИК по остаткам,
ЦЕНОВИК по марже, КОНТРОЛЁР по индексу, СТРАТЕГ куда растём, ТРЕНД-СКАУТ про окна, УПРАВЛЯЮЩИЙ закрыл
KPI DAY/WEEK/MONTH. В командном чате это выглядит как живая смена, где у каждого своя строка.

ГРАНИЦА (RUBICON цел): это ВНУТРЕННЯЯ телеметрия в СВОЙ командный чат — не запись в маркетплейс.
Ни остатков, ни цен, ни публикаций, ни денег тут нет. Суточный цикл под капотом по умолчанию сухой
(0₽); реальные READ/WRITE в кабинет — только его собственным гейтом (not dry AND commit) и по слову.

ЧЕСТНОСТЬ: доставку делает проверенный адаптер из ymarket_report_v1 (обходит RU-блок Телеграма).
Нет токена/чата → сообщения печатаются в консоль и ЧЕСТНО помечаются неотправленными. Провал роли —
это тоже её строка («не смог узнать …»), а не тишина (закон B4 БРИГАДИРА).

Env: YM_TELEGRAM_BOT_TOKEN, YM_TELEGRAM_CHAT_ID (общие с отчётом; ANNA-бота не занимаем).
"""
from __future__ import annotations

import os
import sys
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent
for p in (str(HERE), str(HERE.parent), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_report_v1 as report      # noqa: E402  (переиспользуем проверенную доставку)
import ymarket_kpi_v1 as kpi            # noqa: E402  (KPI DAY/WEEK/MONTH)

# Роль → (имя как в чате, эмодзи-подпись). Имена сверены с CHARTER["name_ru"] каждой роли.
DISPLAY = {
    "BRIGADE":      ("БРИГАДИР",    "👷"),
    "DISPATCHER":   ("ДИСПЕТЧЕР",   "🚚"),
    "STOCKMAN":     ("СКЛАДОВЩИК",  "📦"),
    "MERCHANDISER": ("ТОВАРОВЕД",   "🛒"),
    "PRICER":       ("ЦЕНОВИК",     "💰"),
    "CONTROLLER":   ("КОНТРОЛЁР",   "🛡"),
    "STRATEGIST":   ("СТРАТЕГ",     "📈"),
    "TRENDSCOUT":   ("ТРЕНД-СКАУТ", "🔭"),
    "HEAD":         ("ГОЛОВА",      "🧠"),
    "ZALIV":        ("СБОРЩИК",     "📦"),
    "MANAGER":      ("УПРАВЛЯЮЩИЙ", "🧭"),
}
# Порядок смены = порядок цены ошибки (как у БРИГАДИРА): горящее → важное → выгодное.
BRIGADE_ORDER = ["DISPATCHER", "STOCKMAN", "MERCHANDISER", "PRICER", "CONTROLLER"]

# Пауза между постами на ЖИВОЙ доставке: залп из ~10 сообщений в один чат ловит флуд-лимит
# Телеграма (~1 msg/сек). YM_TELEGRAM_PACE_SECONDS перекрывает (оператор/тесты). 0 = без паузы.
DEFAULT_PACE_SECONDS = 1.1


def _sig(role):
    name, emoji = DISPLAY.get(role, (role, "•"))
    return f"{emoji} {name}"


def _post(role, text, kind="role"):
    name, emoji = DISPLAY.get(role, (role, "•"))
    return {"role": role, "name_ru": name, "emoji": emoji, "kind": kind,
            "text": f"{_sig(role)}\n{text}".strip()}


def _n(v, dash="—"):
    if v is None:
        return dash
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _asdict(v):
    """Fail-soft: не-словарь (битый/частичный day) → {} вместо падения (закон L6)."""
    return v if isinstance(v, dict) else {}


def _aslist(v):
    """Fail-soft: не-список → [] (чтобы len()/итерация по битому day не роняли смену)."""
    return v if isinstance(v, (list, tuple)) else []


def _text(v):
    """Человеческая строка роли, только если это реально непустая строка (иначе None → идём по steps)."""
    return v.strip() if isinstance(v, str) and v.strip() else None


def build_posts(day, rows=None, today=None, include_kpi=True):
    """Разложить дневной отчёт (ymarket_day_v1.run_day) на отдельные сообщения по ролям.

    Возвращает список постов в порядке смены. Каждый пост — самостоятельное сообщение чата.
    Порядок: БРИГАДИР (открытие) → роли смены → СТРАТЕГ → ТРЕНД-СКАУТ → УПРАВЛЯЮЩИЙ (KPI, закрытие).
    """
    if not isinstance(day, dict) or not day:
        return [_post("MANAGER", "смена не отработала — отчёта нет.", kind="manager")]
    posts = []
    roles = _asdict(day.get("roles"))
    mode = "СУХОЙ (0₽)" if day.get("dry") else "БОЕВОЙ"
    burning = _asdict(day.get("burning"))
    esc = _aslist(day.get("escalations"))

    # ── БРИГАДИР открывает смену ──
    head = [f"Смена открыта · {day.get('date','?')} · режим {mode}."]
    if burning.get("count"):
        head.append(f"🔥 Горит: {burning['count']}. Начинаем с этого.")
    else:
        head.append("Горящего нет — идём по порядку.")
    if esc:
        head.append(f"На эскалацию оператору: {len(esc)}.")
    posts.append(_post("BRIGADE", "\n".join(head), kind="head"))

    brigade = _asdict(roles.get("BRIGADE"))
    human = _asdict(brigade.get("human"))
    steps = _asdict(brigade.get("steps"))
    if brigade.get("ok") is False:
        posts.append(_post("BRIGADE", f"не смог провести смену: {brigade.get('error')}", kind="fail"))

    # ── роли смены: каждая своей строкой ──
    for role in BRIGADE_ORDER:
        st = steps.get(role)
        htext = _text(human.get(role))
        if htext:
            posts.append(_post(role, htext))
        elif isinstance(st, dict) and st.get("skipped"):
            posts.append(_post(role, f"пропущено — {st.get('why')}", kind="skip"))
        elif isinstance(st, dict) and st.get("ok") is False:
            posts.append(_post(role, f"не смог: {st.get('error')}", kind="fail"))
        elif st is not None:
            posts.append(_post(role, "отработал."))
        # роли нет в смене вообще → не постим пустоту

    # ── СТРАТЕГ / ТРЕНД-СКАУТ / ГОЛОВА ──
    # ГОЛОВА идёт последней из «мыслящих»: она читает выводы физики+спроса+окна (её вход — уже
    # посчитанный трендскаут) и кладёт суточный шорт-лист как «предложено». RUBICON цел: предлагает,
    # не публикует. Нет источника кандидатов → её строка честно скажет NO_HEAD_SOURCE (не тишина).
    for role in ("STRATEGIST", "TRENDSCOUT", "HEAD"):
        r = _asdict(roles.get(role))
        htext = _text(r.get("human"))
        if htext:
            posts.append(_post(role, htext))
        elif r.get("ok") is False:
            posts.append(_post(role, f"не смог: {r.get('error')}", kind="fail"))

    # ── СБОРЩИК: партия к заливу (провязка ВЫБОР→ЗАЛИВ) ──
    # Идёт ПОСЛЕ ГОЛОВЫ намеренно: та предложила, а СБОРЩИК докладывает, сколько из предложенного
    # реально ВСТАЛО в карточку (сухая сборка, 0₽). Источник не подключён → поста нет вообще: врать
    # «партия готова» без сборки нельзя, а пустая строка в чате только шумит.
    z = _asdict(day.get("zaliv"))
    if z:
        if z.get("donor_blocker"):
            posts.append(_post("ZALIV", f"донор не читается: {z['donor_blocker']} "
                                        f"(файл {z.get('file')}) — партии нет.", kind="fail"))
        else:
            ze = z.get("errors")
            zmark = " ✅" if ze == 0 else (" ❗" if ze else "")
            zl = [f"партия собрана сухо (0₽): полетит чисто {_n(z.get('ready'))} · "
                  f"с ошибкой {_n(ze)}{zmark} (цель 0) · охуенно-заполнены {_n(z.get('topfill'))} "
                  f"— из {_n(z.get('total'))} собранных"]
            if z.get("slug"):
                zl.append(f"  категория: {z['slug']}")
            if z.get("need_mapping"):
                zl.append(f"  категория не подтверждена: {_n(z.get('need_mapping'))} — не полетят")
            if z.get("no_pictures"):
                zl.append(f"  без своих фото: {_n(z.get('no_pictures'))} — бренд-замок отсечёт")
            esk = _aslist(z.get("error_skus"))
            if esk:
                more = "" if len(esk) <= 8 else f" (+{len(esk) - 8})"
                zl.append(f"  пересобрать: {', '.join(str(s) for s in esk[:8])}{more}")
            posts.append(_post("ZALIV", "\n".join(zl)))

    # ── УПРАВЛЯЮЩИЙ закрывает: KPI DAY + WEEK/MONTH + один следующий шаг ──
    k = _asdict(day.get("kpis"))
    growth = _asdict(day.get("growth"))
    tail = ["KPI ДЕНЬ:",
            f"  карточки: веду {_n(k.get('cards_tracked'))} · живых {_n(k.get('cards_live'))} "
            f"(доказано {_n(k.get('cards_live_verified'))}) · с ошибкой {_n(k.get('cards_errored'))}",
            f"  заполненность {_n(k.get('avg_content_rating'))}{'%' if k.get('avg_content_rating') is not None else ''}"
            f" · индекс {_n(k.get('quality_index'))} · горящих заказов {_n(k.get('urgent_orders'))}"]
    if include_kpi:
        try:
            tail.append("")
            tail.append(kpi.render_all(rows=rows, today=today))
        except Exception as e:
            tail.append(f"(KPI-свёртку не собрал: {type(e).__name__})")
    nxt = growth.get("next_lawful_step") or growth.get("top_move_action")
    if nxt:
        tail.append(f"\n🎯 Следующий шаг: {nxt}")
    tail.append("Команда на месте. Скажешь — двинем дальше.")
    posts.append(_post("MANAGER", "\n".join(tail), kind="manager"))
    return posts


def send_feed(posts, token=None, chat_id=None, send_fn=None, echo=True,
              pace_seconds=None, sleep_fn=None):
    """Отправить КАЖДЫЙ пост отдельным сообщением (в этом весь смысл «каждый фиксирует своё»).

    Доставка — через ymarket_report.send_telegram (адаптер ANNA, обход RU-блока, дробление 4096,
    повтор части при 429/5xx/моргнувшей сети).
    Нет токена/чата → НИЧЕГО не врём: sent=False, reason=NO_CREDS, посты печатаются в консоль.

    ЗАКАЛКА (живой путь):
      • Одна сорванная роль НЕ отменяет смену — идём дальше (не break), итог честно скажет N/Y дошло.
        Раньше первая осечка глушила весь фид → в чат падал огрызок 0-4/10 и «офис» выглядел мёртвым.
      • Пауза между постами (pace_seconds), чтобы залп из ~10 сообщений не ловил флуд-лимит чата.
        ТОЛЬКО на живой доставке (send_fn не подставлен): в тестах со своим send_fn пауз нет —
        быстро, и счётчики вызовов не меняются. sleep_fn — шов для тестов.
    """
    token = token or os.environ.get("YM_TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("YM_TELEGRAM_CHAT_ID")
    results, sent_count = [], 0
    creds = bool(token and chat_id)
    live = creds and send_fn is None            # живая доставка (не тест со своим send_fn)
    if pace_seconds is None:
        try:
            pace_seconds = float(os.environ.get("YM_TELEGRAM_PACE_SECONDS") or DEFAULT_PACE_SECONDS)
        except (TypeError, ValueError):
            pace_seconds = DEFAULT_PACE_SECONDS
    sleep = sleep_fn if sleep_fn is not None else time.sleep
    route_dead = False
    for i, p in enumerate(posts, 1):
        if echo:
            print(f"\n[{i}/{len(posts)}] {p['text']}")
        if not creds:
            results.append({"role": p["role"], "sent": False, "reason": "NO_CREDS"})
            continue
        if route_dead:
            # маршрут до ТГ уже подтверждён мёртвым (ни один IP не ответил на прошлом посте) — не жжём
            # ~24с/пост в стену. Честно помечаем остаток; поднимется сеть/VPN — следующий тик добьёт.
            results.append({"role": p["role"], "sent": False, "reason": "TG_UNREACHABLE"})
            continue
        if live and i > 1 and pace_seconds > 0:
            sleep(pace_seconds)                 # притормаживаем залп, чтобы не словить флуд-лимит чата
        res = report.send_telegram(p["text"], token=token, chat_id=chat_id, send_fn=send_fn)
        ok = bool(res.get("sent"))
        results.append({"role": p["role"], "sent": ok,
                        "reason": None if ok else (res.get("reason") or res.get("note"))})
        if ok:
            sent_count += 1
        elif live and res.get("reached") is False:
            route_dead = True                   # до серверов ТГ нет маршрута → остаток не мучаем (не break — честно метим)
        # НЕ break: сорванная роль — её пропуск, а не конец смены; остальные роли всё равно должны дойти
    all_sent = creds and sent_count == len(posts)
    out = {"posts": len(posts), "sent": all_sent, "sent_count": sent_count, "results": results}
    if not creds:
        out["reason"] = "NO_CREDS"
        out["note"] = ("нет YM_TELEGRAM_BOT_TOKEN / YM_TELEGRAM_CHAT_ID — команда НЕ отправлена "
                       "(напечатана в консоль). Заведи бота у @BotFather, добавь его в чат команды, "
                       "и впиши оба значения в SOCC/scripts/mint/.env")
    elif not all_sent:
        unreachable = any(r.get("reason") == "TG_UNREACHABLE" for r in results)
        out["note"] = ("Телеграм недостижим — нет маршрута до его серверов (RU-блок сети?); "
                       "поднимется связь/VPN — следующий тик добьёт остаток"
                       if unreachable else
                       "часть постов не ушла — смотри results (флуд-лимит/неверный chat_id/бот не в чате)")
    if echo and not all_sent:
        print(f"\n[доставка] отправлено {sent_count}/{len(posts)} — {out.get('note') or out.get('reason')}")
    return out


def deliver(day, token=None, chat_id=None, send_fn=None, echo=True, rows=None, today=None):
    """Собрать посты из дня и разослать в командный чат."""
    posts = build_posts(day, rows=rows, today=today)
    delivery = send_feed(posts, token=token, chat_id=chat_id, send_fn=send_fn, echo=echo)
    return {"posts": posts, "delivery": delivery}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ТГ КОМАНДЫ — разложить смену на посты по ролям и разослать")
    ap.add_argument("--run", action="store_true", help="провести суточный цикл и собрать команду")
    ap.add_argument("--commit", action="store_true", help="боевой режим цикла (иначе сухой, 0₽)")
    ap.add_argument("--target-sku", type=int, default=None)
    ap.add_argument("--risk-cap", type=float, default=None)
    ap.add_argument("--no-send", action="store_true", help="только показать посты, не слать")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.run:
        print("нужен --run (провести суточный цикл и собрать посты). Без него слать нечего.")
        sys.exit(2)

    import ymarket_day_v1 as day_mod
    d = day_mod.run_day(target_sku=args.target_sku, risk_cap_rub=args.risk_cap,
                        dry=not args.commit, commit=args.commit)
    posts = build_posts(d)
    if args.json:
        print(json.dumps({"day_ok": d.get("ok"), "posts": posts}, ensure_ascii=False, indent=2))
    elif args.no_send:
        for i, p in enumerate(posts, 1):
            print(f"\n[{i}/{len(posts)}] {p['text']}")
        print(f"\n[показано {len(posts)} постов; --no-send: не отправлял]")
    else:
        send_feed(posts)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОТЧЁТ УПРАВЛЯЮЩЕГО (ymarket_report_v1) — то, что оператор читает утром в Телеграме.

Оператор: «он общается со мной как с другом по сути, но все данные даёт». Значит отчёт —
не сухой дамп JSON и не бодрая пустышка. Правила тона:
  • Сначала главное: горит / не горит. Если горит — в первой строке, без прелюдий.
  • Каждое утверждение — с числом. «Стало лучше» без цифры запрещено.
  • Чего не знаем — говорим прямо («источник не подключён»), а не заминаем.
  • Плохие новости не смягчаем: непрочитанный индекс опаснее, чем низкий.
  • В конце — один следующий ход, а не список из двадцати желаний.

ДОСТАВКА: Телеграм через проверенный адаптер ANNA (anna_net.tg_call) — этот хост режет
api.telegram.org по DNS, адаптер обходит блок честным TLS с пиннингом рабочего IP.
Без токена/чата отчёт печатается в консоль и ЧЕСТНО помечается как неотправленный —
никогда не рапортуем «отправлено», если не отправлено.

Env: YM_TELEGRAM_BOT_TOKEN, YM_TELEGRAM_CHAT_ID (свои у органа; ANNA-бота не занимаем).
"""
from __future__ import annotations

import os
import sys
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent          # SOCC/scripts (там живёт anna_net)
for p in (str(HERE), str(HERE.parent), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

TG_LIMIT = 4096          # предел длины сообщения Телеграма
_ARROW = {1: "▲", -1: "▼", 0: "="}

# ── ЗАКАЛКА ДОСТАВКИ ──
# RU-egress + флуд-лимит Телеграма роняли часть сообщений; раньше первая же осечка = стоп навсегда.
# Теперь ОДНУ часть пробуем несколько раз: сеть моргнула / 429 / 5xx → пауза и повтор; уважаем
# retry_after самого Телеграма. Навсегда-ошибки (неверный chat/токен/бот кикнут) не долбим впустую.
SEND_MAX_ATTEMPTS = 3          # сколько раз отдаём ОДНУ часть, прежде чем честно сдаться
SEND_BACKOFF_BASE = 1.6        # база экспоненты пауз между попытками (сек): 1.6, 2.56, …
SEND_BACKOFF_CAP = 12.0        # потолок паузы — вечная машина не засыпает надолго
SEND_PER_IP_TIMEOUT = 6.0      # ceiling на КАЖДЫЙ пиннингованный IP адаптера (их 4). Дефолт anna_net =
                               # 40с/IP → мёртвый пул (RU-блок сети ТГ отвечает молчанием) = 4×40=160с на
                               # ОДИН вызов. С 6с — 4×6=24с и честно сдаёмся. YM_TELEGRAM_TIMEOUT перекрывает.


def _retry_after(r):
    """Сколько просит подождать Телеграм при флуд-лимите (429). Иначе None."""
    if not isinstance(r, dict):
        return None
    params = r.get("parameters")
    ra = params.get("retry_after") if isinstance(params, dict) else None
    if ra is None:
        ra = r.get("retry_after")
    try:
        return float(ra) if ra is not None else None
    except (TypeError, ValueError):
        return None


def _is_retryable(r, exc):
    """Стоит ли повторить: сеть моргнула / 429 / 5xx — да; 400/401/403/404 — нет (не спасёт)."""
    if exc is not None:
        return True                         # исключение сокета/TLS — транзиентно
    if not isinstance(r, dict):
        return True                         # непонятный ответ — дать ещё шанс
    if r.get("ok"):
        return False                        # успех — повторять нечего
    code = r.get("error_code")
    if code in (400, 401, 403, 404):
        return False                        # неверный chat/токен/бот кикнут → повтор впустую
    return True                             # 429, 5xx, «error» без кода, неизвестное → пробуем


def _reached_telegram(r, exc):
    """Был ли РЕАЛЬНЫЙ ответ Bot API (достучались), или маршрута до Телеграма нет вовсе.

    True  — r словарь с ok или error_code (ответ ТГ, пусть даже 429/5xx): путь живой, повтор осмыслен.
    False — исключение сокета/TLS ЛИБО sentinel адаптера {'ok':False,'error':...} без error_code:
            все пиннингованные IP молчат (RU-блок сети ТГ / мёртвый пул). anna_net уже перебрал их
            ВНУТРИ одного вызова — долбить ту же стену повтором в ту же секунду смысла нет.
    """
    if exc is not None:
        return False
    if not isinstance(r, dict):
        return False
    return ("error_code" in r) or bool(r.get("ok"))


def _fmt_delta(v):
    """Дельта ко вчера в человеческом виде. None → пусто (вчера не с чем сравнить)."""
    if v is None or v == 0:
        return ""
    sign = 1 if v > 0 else -1
    val = int(v) if float(v).is_integer() else round(v, 1)
    return f" {_ARROW[sign]}{abs(val)}"


def _n(v, dash="—"):
    """Число или честный прочерк. 0 остаётся нулём (0 ≠ «не знаю»)."""
    if v is None:
        return dash
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def render_day(day, friendly=True):
    """Дневной отчёт человеческим языком. friendly=False → сухая сводка (для логов/дашборда)."""
    if not day:
        return "Отчёта нет — цикл не отработал."
    k = day.get("kpis", {})
    d = day.get("delta", {})
    burning = day.get("burning", {})
    growth = day.get("growth", {})
    L = []

    # ── Шапка: горит или спокойно ──
    if friendly:
        if burning.get("count"):
            L.append(f"⚠️ Доброе утро. Сегодня горит {burning['count']} — начну с этого.")
        elif day.get("failures"):
            L.append("Доброе утро. Ничего не горит, но есть чего я не смог узнать — ниже честно.")
        else:
            L.append("Доброе утро. Ничего не горит, витрина под контролем.")
    L.append(f"📅 {day.get('date','?')} · режим: {'СУХОЙ (0₽)' if day.get('dry') else 'БОЕВОЙ'}")

    # ── Что горит (первым, без прелюдий) ──
    if burning.get("count"):
        L.append("\n🔥 ГОРИТ:")
        for b in burning["items"][:6]:
            who = f" [{b.get('owner')}]" if b.get("owner") else ""
            L.append(f"  • {b.get('what')}{who}")
            if b.get("action"):
                L.append(f"    → {b['action']}")

    # ── KPI: каждое число с дельтой ко вчера ──
    L.append("\n📊 МОИ ЦИФРЫ:")
    L.append(f"  карточек веду: {_n(k.get('cards_tracked'))}{_fmt_delta(d.get('cards_tracked'))}"
             f" · живых: {_n(k.get('cards_live'))}{_fmt_delta(d.get('cards_live'))}"
             f" (доказано: {_n(k.get('cards_live_verified'))})")
    err = k.get("cards_errored")
    err_mark = " ✅" if err == 0 else (" ❗" if err else "")
    L.append(f"  с ошибкой: {_n(err)}{_fmt_delta(d.get('cards_errored'))}{err_mark} (цель 0)"
             f" · готовы к заливу: {_n(k.get('ready_to_publish'))}")
    idx = k.get("avg_content_rating")
    L.append(f"  заполненность карточек: {_n(idx)}{'%' if idx is not None else ''}"
             f"{_fmt_delta(d.get('avg_content_rating'))} (целюсь в 80%)")
    q = k.get("quality_index")
    if q is None:
        L.append("  индекс качества магазина: НЕ ПРОЧИТАН — это опаснее низкого, надо чинить чтение")
    else:
        zone = "ОТКЛЮЧЕНИЕ" if q < 40 else ("штрафы" if q < 98 else "чисто")
        L.append(f"  индекс качества магазина: {_n(q)}{_fmt_delta(d.get('quality_index'))} ({zone})")
    if k.get("urgent_orders") is not None:
        L.append(f"  заказов горит: {_n(k.get('urgent_orders'))}")
    if k.get("stock_unknown"):
        L.append(f"  SKU без источника наличия: {_n(k.get('stock_unknown'))} — стоят с нулём, "
                 f"а значит не продаются вообще")
    if day.get("compared_to"):
        L.append(f"  (стрелки — сравнение с {day['compared_to']})")

    # ── Партия к заливу (провязка ВЫБОР→ЗАЛИВ): сухо собрано, «сколько полетит» ──
    # Блок появляется ТОЛЬКО когда источник залива подключён (день собрал партию). Не подключён →
    # молчим: цифра «готовы к заливу» выше уже честно помечена как память (ready_to_publish_source).
    z = day.get("zaliv")
    if z:
        L.append("\n📦 ПАРТИЯ К ЗАЛИВУ (собрана сухо, 0₽ — наружу ничего):")
        if z.get("donor_blocker"):
            L.append(f"  донор не читается: {z['donor_blocker']} (файл {z.get('file')}) — "
                     f"партии нет, это не «нечего лить»")
        else:
            ze = z.get("errors")
            zmark = " ✅" if ze == 0 else (" ❗" if ze else "")
            L.append(f"  полетит чисто: {_n(z.get('ready'))} · с ошибкой: {_n(ze)}{zmark} (цель 0)"
                     f" · охуенно-заполнены: {_n(z.get('topfill'))} — из {_n(z.get('total'))} собранных")
            if z.get("need_mapping"):
                L.append(f"  категория не подтверждена: {_n(z.get('need_mapping'))} — не полетят, "
                         f"пока не смаплены")
            if z.get("no_pictures"):
                L.append(f"  без своих фото: {_n(z.get('no_pictures'))} — бренд-замок отсечёт при заливе")
            if z.get("error_skus"):
                shown = ", ".join(str(s) for s in z["error_skus"][:8])
                more = "" if len(z["error_skus"]) <= 8 else f" (+{len(z['error_skus']) - 8})"
                L.append(f"  пересобрать: {shown}{more}")
            if z.get("slug"):
                L.append(f"  категория: {z['slug']}"
                         + (f" · отобрано КАТЕГОРИЙЩИКОМ: {_n(z.get('selected'))}"
                            if z.get("selected") is not None else ""))

    # ── Куда растём ──
    L.append("\n🚀 КУДА РАСТЁМ:")
    if growth.get("top_move"):
        ceil = growth.get("ceiling_rub")
        money = f" · потолок посчитанного: {ceil:.0f}₽" if ceil else ""
        L.append(f"  главный ход: {growth['top_move']}{money}")
        L.append(f"  почему: {growth.get('top_move_why')}")
        L.append(f"  → {growth.get('top_move_action')}")
        L.append(f"  всего ходов в очереди: {growth.get('moves_total')}")
    else:
        L.append("  ходов не нашёл — значит мало данных, а не «всё идеально».")
    if growth.get("need_sources"):
        L.append("  чтобы считать деньги точнее, мне не хватает:")
        for n in growth["need_sources"][:3]:
            L.append(f"    – {n.get('needs_source')}")
    tc = growth.get("trend_candidates")
    ts_role = (day.get("roles") or {}).get("TRENDSCOUT") or {}
    if ts_role.get("need_source"):
        L.append("  тренды: источник не подключён — кандидатов нет (это честный ноль, не «пусто»)")
    elif tc:
        L.append(f"  тренды: {tc} кандидатов в открытом окне (решение о закупке — твоё)")

    # ГОЛОВА: суточный шорт-лист «предложить» (RUBICON цел — предлагает, не публикует)
    hd_role = (day.get("roles") or {}).get("HEAD") or {}
    if hd_role.get("reason") == "NO_HEAD_SOURCE":
        L.append("  ГОЛОВА: источник кандидатов не подключён — предлагать нечего (честный ноль)")
    elif growth.get("head_proposed"):
        L.append(f"  ГОЛОВА: {growth['head_proposed']} в суточном шорт-листе «предложить» "
                 f"(решение о заводе карточки — твоё)")

    # ── Чего я не смог (провалы не прячем) ──
    if day.get("failures"):
        L.append("\n🩹 ЧЕГО Я НЕ СМОГ:")
        for f in day["failures"][:6]:
            L.append(f"  • {f}")

    # ── Один следующий шаг ──
    nxt = growth.get("next_lawful_step")
    if nxt:
        L.append(f"\n🎯 СЛЕДУЮЩИЙ ШАГ: {nxt}")
    if friendly:
        L.append("\nЯ на месте. Скажешь — сделаю.")
    return "\n".join(L)


def _chunks(text, limit=TG_LIMIT):
    """Разбить длинный отчёт по границам строк (Телеграм режет на 4096)."""
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def send_telegram(text, token=None, chat_id=None, send_fn=None,
                  max_attempts=None, sleep_fn=None, timeout=None):
    """Отправить отчёт в Телеграм. Без токена/чата — ЧЕСТНЫЙ отказ (не врём «отправлено»).

    send_fn — шов для тестов. По умолчанию — проверенный адаптер ANNA (обходит RU-блок честным
    TLS с пиннингом рабочего IP Телеграма, без MITM).

    ЗАКАЛКА: каждую часть отдаём с повтором (max_attempts) — сеть моргнула / флуд-лимит 429 / 5xx
    → пауза и ещё попытка; при 429 уважаем retry_after Телеграма. Навсегда-ошибку (неверный
    chat/токен, бот кикнут — 400/401/403/404) не долбим. sleep_fn — шов для тестов (без реальных пауз).
    """
    token = token or os.environ.get("YM_TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("YM_TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return {"sent": False, "reason": "NO_CREDS",
                "note": ("нет YM_TELEGRAM_BOT_TOKEN / YM_TELEGRAM_CHAT_ID — отчёт НЕ отправлен "
                         "(напечатан в консоль). Заведи бота у @BotFather и впиши оба значения в .env")}
    fn = send_fn
    if fn is None:
        try:
            from anna_net import tg_call
            fn = lambda tok, method, **kw: tg_call(tok, method, **kw)   # noqa: E731
        except Exception as e:
            return {"sent": False, "reason": "NO_ADAPTER", "note": f"сетевой адаптер недоступен: {e}"}
    attempts = max_attempts if max_attempts is not None else SEND_MAX_ATTEMPTS
    sleep = sleep_fn if sleep_fn is not None else time.sleep
    if timeout is None:
        try:
            timeout = float(os.environ.get("YM_TELEGRAM_TIMEOUT") or SEND_PER_IP_TIMEOUT)
        except (TypeError, ValueError):
            timeout = SEND_PER_IP_TIMEOUT
    parts = _chunks(text)
    results = []
    reached_any = False
    for i, part in enumerate(parts, 1):
        r, exc, ok, tries = None, None, False, 0
        for attempt in range(1, attempts + 1):
            tries, exc = attempt, None
            try:
                # _timeout — ceiling на КАЖДЫЙ IP внутри anna_net (иначе дефолт 40с/IP жжёт до 160с).
                # Тест-стаб глотает лишний kwarg через **kw, живой tg_call — снимает его из params.
                r = fn(token, "sendMessage", chat_id=chat_id, text=part, _timeout=timeout)
            except Exception as e:
                exc, r = e, None
            ok = bool(isinstance(r, dict) and r.get("ok"))
            if _reached_telegram(r, exc):
                reached_any = True
            if ok or attempt >= attempts or not _is_retryable(r, exc):
                break
            if not _reached_telegram(r, exc):
                break                        # маршрута до ТГ нет — не жжём попытки в стену, сдаёмся быстро
            ra = _retry_after(r)            # 429 → ждём ровно столько, сколько просит Телеграм
            pause = (ra + 0.5) if ra is not None else min(SEND_BACKOFF_CAP, SEND_BACKOFF_BASE ** attempt)
            sleep(pause)
        if ok:
            err = None
        elif exc is not None:
            err = f"{type(exc).__name__}: {exc}"
        elif isinstance(r, dict):
            err = r.get("description") or r.get("error")
        else:
            err = None
        results.append({"ok": ok, "part": i, "error": err, "attempts": tries})
        if not ok:
            break                            # рваное многокусковое сообщение не продолжаем
    sent = all(x["ok"] for x in results) and bool(results)
    if sent:
        note = None
    elif reached_any:
        note = "часть сообщений не ушла — смотри results"
    else:
        note = "Телеграм недостижим — нет маршрута до его серверов (RU-блок сети?), ни один IP не ответил"
    return {"sent": sent, "parts": len(parts), "reached": reached_any, "results": results, "note": note}


def deliver_day(day, friendly=True, token=None, chat_id=None, send_fn=None, echo=True):
    """Собрать отчёт и доставить. Всегда печатает (чтобы оператор увидел даже без Телеграма)."""
    text = render_day(day, friendly=friendly)
    if echo:
        print(text)
    res = send_telegram(text, token=token, chat_id=chat_id, send_fn=send_fn)
    if echo and not res["sent"]:
        print(f"\n[доставка] НЕ отправлено: {res.get('note') or res.get('reason')}")
    return {"text": text, "delivery": res}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ОТЧЁТ УПРАВЛЯЮЩЕГО — собрать день и доставить в ТГ")
    ap.add_argument("--run", action="store_true", help="провести суточный цикл и отчитаться")
    ap.add_argument("--commit", action="store_true", help="боевой режим цикла (иначе сухой, 0₽)")
    ap.add_argument("--target-sku", type=int, default=None)
    ap.add_argument("--risk-cap", type=float, default=None)
    ap.add_argument("--dry-tone", action="store_true", help="сухой тон (без дружеской рамки)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    import ymarket_day_v1 as day_mod
    d = day_mod.run_day(target_sku=args.target_sku, risk_cap_rub=args.risk_cap,
                        dry=not args.commit, commit=args.commit)
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        deliver_day(d, friendly=not args.dry_tone)

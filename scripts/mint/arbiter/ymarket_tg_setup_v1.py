#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ТГ-ПОДКЛЮЧЕНИЕ команды (ymarket_tg_setup_v1) — узнать chat_id, не роняя токен.

BotFather даёт ТОЛЬКО токен бота (YM_TELEGRAM_BOT_TOKEN). `chat_id` — это ID чата-назначения,
куда команда пишет события; он берётся ОТДЕЛЬНО через getUpdates. Этот помощник:
  • читает токен из env/.env (общий socc_mint_env_v1) — и НИКОГДА его не печатает;
  • getMe → подтверждает, что бот жив (показывает @username, не токен);
  • getUpdates → показывает ВСЕ чаты, где бота уже видели, с их chat_id;
  • --test → шлёт одно проверочное сообщение в YM_TELEGRAM_CHAT_ID.

ГРАНИЦА (RUBICON цел): только Телеграм (getMe/getUpdates read-only; --test это sendMessage —
внутренняя телеметрия в свой чат). Ни остатков, ни цен, ни публикаций, ни денег.
Доставка через тот же адаптер ANNA (anna_net.tg_call), что обходит RU-блок Телеграма.

LIVE — только `/usr/bin/python3` (system 3.9 с requests). Дефолтный python3 (Homebrew) не потянет сеть.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent                       # SOCC/scripts (там anna_net)
for p in (str(HERE), str(HERE.parent), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

ENV_HINT = "SOCC/scripts/mint/.env"


def _ensure_env():
    """Подтянуть gitignored .env через общий загрузчик органа (как весь MINT)."""
    try:
        import socc_mint_env_v1 as env
        env.ensure_env()
    except Exception:
        pass  # env может быть уже в окружении — не роняем помощник из-за загрузчика


def _default_call():
    """Боевой сетевой вызов: адаптер ANNA (обход RU-блока). Нет адаптера → честный отказ."""
    from anna_net import tg_call
    return tg_call


def _mask(token):
    """Никогда не печатаем токен целиком. Только хвост для узнавания (…:AAE…12ab)."""
    if not token:
        return "—"
    tail = token[-4:] if len(token) >= 4 else "?"
    return f"…{tail}"


def _chat_of(update):
    """Достать chat из любого вида апдейта (сообщение/правка/пост канала/добавление бота)."""
    for key in ("message", "edited_message", "channel_post", "edited_channel_post",
                "my_chat_member", "chat_member"):
        obj = update.get(key)
        if isinstance(obj, dict) and isinstance(obj.get("chat"), dict):
            return obj["chat"]
    return None


def _chat_label(chat):
    """Человеческое имя чата: title группы/канала, иначе имя пользователя, иначе @username."""
    return (chat.get("title")
            or (" ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) or None)
            or (f"@{chat['username']}" if chat.get("username") else None)
            or "(без имени)")


def discover(token=None, call_fn=None):
    """getMe + getUpdates → {ok, bot, chats:[{id,type,name}], reason?}. Токен наружу не отдаём."""
    _ensure_env()
    token = token or os.environ.get("YM_TELEGRAM_BOT_TOKEN")
    if not token:
        return {"ok": False, "reason": "NO_TOKEN",
                "note": f"нет YM_TELEGRAM_BOT_TOKEN — впиши токен от @BotFather в {ENV_HINT}"}
    if call_fn is None:
        try:
            call_fn = _default_call()
        except Exception as e:
            return {"ok": False, "reason": "NO_ADAPTER", "note": f"сетевой адаптер недоступен: {e}"}

    me = call_fn(token, "getMe")
    if not (isinstance(me, dict) and me.get("ok")):
        err = (me or {}).get("error") or (me or {}).get("description") or "бот не ответил"
        return {"ok": False, "reason": "BAD_TOKEN_OR_NET",
                "note": f"getMe не прошёл ({err}). Проверь токен ({_mask(token)}) и сеть — LIVE только /usr/bin/python3"}
    bot = me["result"].get("username") or me["result"].get("first_name") or "?"

    upd = call_fn(token, "getUpdates", timeout=0)
    if not (isinstance(upd, dict) and upd.get("ok")):
        err = (upd or {}).get("error") or (upd or {}).get("description") or "getUpdates не прошёл"
        return {"ok": True, "bot": bot, "chats": [], "reason": "NO_UPDATES", "note": str(err)}

    seen, chats = {}, []
    for u in upd.get("result") or []:
        chat = _chat_of(u) if isinstance(u, dict) else None
        if not chat or chat.get("id") is None or chat["id"] in seen:
            continue
        seen[chat["id"]] = True
        chats.append({"id": chat["id"], "type": chat.get("type", "?"), "name": _chat_label(chat)})
    return {"ok": True, "bot": bot, "chats": chats, "token_tail": _mask(token)}


def send_test(token=None, chat_id=None, send_fn=None):
    """Проверочное сообщение в чат команды (sendMessage). Reuse проверенной доставки отчёта."""
    _ensure_env()
    import ymarket_report_v1 as report
    text = ("✅ ТГ КОМАНДЫ на связи. Сюда команда будет писать свои события "
            "(БРИГАДИР → роли смены → УПРАВЛЯЮЩИЙ с KPI). Это тестовое сообщение.")
    return report.send_telegram(text, token=token, chat_id=chat_id, send_fn=send_fn)


def _print_discovery(d):
    if not d.get("ok"):
        print(f"❌ {d['reason']}: {d.get('note')}")
        return 2
    print(f"🤖 бот жив: @{d['bot']}  (токен {d.get('token_tail', '…')}, наружу не печатаю)")
    if d.get("chats"):
        print("\nЧаты, где бота уже видели:")
        for c in d["chats"]:
            print(f"   chat_id={c['id']:<18} {c['type']:<11} «{c['name']}»")
        pick = d["chats"][0]["id"]
        print(f"\n→ впиши строку в {ENV_HINT}:")
        print(f"   YM_TELEGRAM_CHAT_ID={pick}")
        print("Затем проверь доставку:  /usr/bin/python3 ymarket_tg_setup_v1.py --test")
        return 0
    print("\nПока ни одного чата. Сделай так и запусти меня снова:")
    print(f"   1) создай группу (напр. «ЯМ команда»)")
    print(f"   2) добавь туда своего бота @{d['bot']}")
    print(f"   3) назначь бота АДМИНОМ группы  (тогда он видит апдейт сразу),")
    print(f"      либо просто напиши в группе сообщение с упоминанием @{d['bot']}")
    print(f"   4) снова:  /usr/bin/python3 ymarket_tg_setup_v1.py")
    print("   (для личного чата: просто напиши боту /start в ЛС — покажется твой chat_id)")
    if d.get("reason") == "NO_UPDATES":
        print(f"\n[getUpdates: {d.get('note')}]")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ТГ-подключение команды: узнать chat_id (токен наружу не печатается)")
    ap.add_argument("--test", action="store_true", help="послать проверочное сообщение в YM_TELEGRAM_CHAT_ID")
    args = ap.parse_args()

    if args.test:
        _ensure_env()
        res = send_test()
        if res.get("sent"):
            print("✅ Отправлено. Загляни в чат команды — там тестовое сообщение.")
            sys.exit(0)
        print(f"❌ Не отправлено: {res.get('note') or res.get('reason')}")
        sys.exit(2)

    sys.exit(_print_discovery(discover()))

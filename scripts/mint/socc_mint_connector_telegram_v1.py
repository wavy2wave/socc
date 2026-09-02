#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT telegram connector V1 — боевой вход спроса: входящие боту ОПЕРАТОРА → лиды.

Читает getUpdates бота оператора (env MINT_TG_BOT_TOKEN), классифицирует каждое сообщение и отдаёт только
реальные заявки. ToS-рискованное/спам не берутся. Ничего не отправляет (только читает входящие).

Сетевой вызов ленивый (urllib). Логика (to_raws) чистая: тестируется без сети.
"""
import os
import sys
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import socc_mint_classify_v1 as classify  # noqa: E402


def _llm():
    try:
        import socc_mint_brain_v1 as brain
        return brain._real_llm
    except Exception:
        return None


def to_raws(messages, llm=None):
    """Список сообщений [{text, from, id, chat}] → raw-лиды (только реальные заявки; ToS/спам отсеяны)."""
    raws = []
    for m in messages:
        text = (m.get("text", "") or "").strip()
        if not text:
            continue
        raw, _ = classify.message_to_lead(text, contact=m.get("from") or m.get("chat"),
                                          ref=str(m.get("id") or ""), llm=llm)
        if raw:
            raws.append(raw)
    return raws


def _messages_from_api():
    """Ленивый getUpdates бота оператора. [] при отсутствии токена/ошибке."""
    token = os.environ.get("MINT_TG_BOT_TOKEN")
    if not token:
        return []
    try:
        limit = int(os.environ.get("MINT_TG_LIMIT", "50"))
        url = f"https://api.telegram.org/bot{token}/getUpdates?limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "MINT-connector"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
        out = []
        for u in d.get("result", []):
            msg = u.get("message") or u.get("edited_message") or {}
            if not msg.get("text"):
                continue
            frm = msg.get("from", {})
            out.append({"text": msg.get("text"), "from": frm.get("username") or frm.get("first_name"),
                        "chat": (msg.get("chat") or {}).get("id"), "id": u.get("update_id")})
        return out
    except Exception:
        return []


def fetch():
    return to_raws(_messages_from_api(), llm=_llm())


if __name__ == "__main__":
    print(json.dumps({"leads": fetch(), "note": "нужен MINT_TG_BOT_TOKEN оператора для реального чтения"},
                     ensure_ascii=False, indent=2))

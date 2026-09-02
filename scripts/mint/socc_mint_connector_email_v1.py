#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT email connector V1 — боевой вход спроса: входящие письма ОПЕРАТОРА → лиды (агент как представитель).

Читает почту оператора по ЕГО ключам (env), классифицирует каждое письмо (classify_lead: заявка/спам/
офтоп/ToS-риск) и отдаёт только реальные заявки как raw-лиды. ToS-рискованное не берётся. Ничего не шлёт.

Env (ключи оператора; без них fetch()→[]):
  MINT_EMAIL_HOST, MINT_EMAIL_USER, MINT_EMAIL_PASS, MINT_EMAIL_FOLDER(=INBOX), MINT_EMAIL_LIMIT(=20)

Сетевой imaplib — ленивый. Логика (to_raws) чистая: тестируется без сети.
"""
import os
import sys
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
    """Список писем [{subject, body, from, id}] → raw-лиды (только реальные заявки; ToS/спам отсеяны)."""
    raws = []
    for m in messages:
        text = ((m.get("subject", "") or "") + "\n" + (m.get("body", "") or "")).strip()
        raw, _ = classify.message_to_lead(text, contact=m.get("from"), ref=m.get("id"), llm=llm)
        if raw:
            raws.append(raw)
    return raws


def _messages_from_imap():
    """Ленивое чтение непрочитанных писем из почты оператора. [] при отсутствии ключей/ошибке."""
    host = os.environ.get("MINT_EMAIL_HOST")
    user = os.environ.get("MINT_EMAIL_USER")
    pw = os.environ.get("MINT_EMAIL_PASS")
    if not (host and user and pw):
        return []
    try:
        import imaplib
        import email as emod
        from email.header import decode_header
        folder = os.environ.get("MINT_EMAIL_FOLDER", "INBOX")
        limit = int(os.environ.get("MINT_EMAIL_LIMIT", "20"))
        out = []
        M = imaplib.IMAP4_SSL(host)
        M.login(user, pw)
        M.select(folder)
        typ, data = M.search(None, "UNSEEN")
        ids = (data[0].split() if data and data[0] else [])[-limit:]
        for i in ids:
            typ, md = M.fetch(i, "(RFC822)")
            if not md or not md[0]:
                continue
            msg = emod.message_from_bytes(md[0][1])
            subj = str(decode_header(msg.get("Subject", ""))[0][0])
            frm = msg.get("From", "")
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors="ignore")
                        break
            else:
                body = (msg.get_payload(decode=True) or b"").decode(errors="ignore")
            out.append({"subject": subj, "body": body, "from": frm, "id": msg.get("Message-ID", str(i))})
        M.logout()
        return out
    except Exception:
        return []


def fetch():
    return to_raws(_messages_from_imap(), llm=_llm())


if __name__ == "__main__":
    import json
    print(json.dumps({"leads": fetch(), "note": "нужны MINT_EMAIL_* ключи оператора для реального чтения"},
                     ensure_ascii=False, indent=2))

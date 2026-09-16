#!/usr/bin/env python3
"""
ANNA MAX Runtime V1 — live on the MAX messenger (VK national messenger), same brain as Telegram.

MAX Bot API (dev.max.ru): long-poll GET {base}/updates, send POST {base}/messages, auth via
header `Authorization: <token>`. Channel-agnostic: ANNA's brain / persona / memory / booking /
safety guard are reused from anna_runtime_v1.py — only the channel adapter differs.

Token: create a bot via @MasterBot in MAX (/create, nick ending _bot) → put in
.secrets/anna_max.env as ANNA_MAX_BOT_TOKEN. (Publishing to the catalog needs RF юрлицо
verification, but a bot works for direct chats / pilot immediately.)

NOTE: MAX update/message field names are mapped defensively below. On the first real run with a
live token, one quick field-mapping check may be needed (printed to max_log.jsonl) — the brain
and booking are already proven; only the envelope is new.

Run:  python3 scripts/anna_max_v1.py     (Ctrl-C to stop)
"""
import os, sys, time, json, urllib.request, urllib.parse, importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def _load_env(p):
    p = Path(p)
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1); os.environ[k.strip()] = v.strip()

_load_env(ROOT / ".secrets/anna_max.env")
_load_env(ROOT / ".secrets/anna_llm.env")

TOKEN = os.environ.get("ANNA_MAX_BOT_TOKEN")
# dev.max.ru: current host platform-api2.max.ru (old platform-api.max.ru deprecated by 2026-07-19)
BASE = os.environ.get("ANNA_MAX_BASE", "https://platform-api2.max.ru")

_s = importlib.util.spec_from_file_location("anna", ROOT / "scripts/anna_runtime_v1.py")
A = importlib.util.module_from_spec(_s); _s.loader.exec_module(A)

LOG = ROOT / "SYSTEM/ANNA_MVP/runtime/max_log.jsonl"


def api(method, path, params=None, body=None):
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", TOKEN)            # MAX: token in header, not query
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=70) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"_error": str(e)}


def log(o):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(o, ensure_ascii=False) + "\n")


def _extract(update):
    """Defensive field-mapping for a MAX update → (chat_id, text). Logs raw shape if it can't map."""
    msg = update.get("message") or update.get("message_created") or update
    body = msg.get("body") or msg.get("text") or {}
    text = body.get("text") if isinstance(body, dict) else (body if isinstance(body, str) else None)
    if text is None:
        text = msg.get("text")
    rec = msg.get("recipient") or {}
    chat_id = rec.get("chat_id") or rec.get("user_id") or msg.get("chat_id") or (msg.get("sender") or {}).get("user_id")
    return chat_id, text


def send(chat_id, text):
    # MAX sendMessage; chat_id passed as query per API, body carries text
    return api("POST", "/messages", params={"chat_id": chat_id}, body={"text": text})


def typing(chat_id):
    # best-effort typing indicator (action endpoint); harmless if unsupported
    api("POST", f"/chats/{chat_id}/actions", body={"action": "typing_on"})


def handle(chat_id, text):
    anna = A.Anna(client_id=f"max_{chat_id}")
    typing(chat_id)
    t0 = time.time()
    r = anna.reply(text)
    reply, booking = r if isinstance(r, tuple) else (r, None)
    if not isinstance(r, tuple):
        reply = "Секунду, гляну расписание и вернусь к вам 🙂"
        log({"ts": A.now(), "chat": chat_id, "brain_error": r})
    delay = A.typing_delay(reply)
    extra = max(0.0, delay - (time.time() - t0))
    waited = 0.0
    while waited < extra:
        typing(chat_id); step = min(4.0, extra - waited); time.sleep(step); waited += step
    send(chat_id, reply)
    log({"ts": A.now(), "chat": chat_id, "in": text, "out": reply,
         "booking": bool(booking), "violations": anna.last_violations})
    if booking:
        print(f"  📅 booking: {booking.get('service')} · {booking.get('preferred_time')} · {booking.get('name')}")


def main():
    if not TOKEN:
        print("NO ANNA_MAX_BOT_TOKEN — create a bot via @MasterBot in MAX, put token in .secrets/anna_max.env")
        sys.exit(1)
    me = api("GET", "/me")
    print(f"ANNA on MAX: {me.get('name', me)}  base={BASE}  — Ctrl-C to stop")
    print(f"brain: claude_cli={'yes' if os.environ.get('ANNA_CLAUDE_KEY') or os.environ.get('ANNA_CLAUDE_KEYS') else 'no'}")
    marker = None
    while True:
        upd = api("GET", "/updates", params={"marker": marker, "timeout": 30} if marker else {"timeout": 30})
        if upd.get("_error"):
            log({"ts": A.now(), "updates_error": upd["_error"]}); time.sleep(3); continue
        updates = upd.get("updates") or []
        if "marker" in upd:
            marker = upd["marker"]
        for u in updates:
            chat_id, text = _extract(u)
            if not text or chat_id is None:
                log({"ts": A.now(), "unmapped_update_shape": list(u.keys())}); continue
            print(f"🧑 {chat_id}: {text}")
            try:
                handle(chat_id, text)
            except Exception as e:
                log({"ts": A.now(), "chat": chat_id, "handler_error": str(e)})
                print("  ! handler error:", e)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
ANNA Telegram Runtime V1 — live Telegram with human texture.

Long-poll Telegram Bot API over plain HTTP (no external deps). For each incoming message:
shows the "typing…" indicator, lets ANNA's brain compose a reply, waits a human-plausible
typing delay (proportional to length, like a busy admin — not an instant block), then sends.
Per-chat memory (client_id = tg_<chat_id>); bookings persist via the Anna runtime.

Env: ANNA_TELEGRAM_BOT_TOKEN (.secrets/anna_telegram.env). Brain creds: .secrets/anna_llm.env.
Run:  python3 scripts/anna_telegram_v1.py     (Ctrl-C to stop)
"""
import os, sys, time, json, urllib.request, urllib.parse, importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Network adapter: this egress is RU-blocked — DNS gives a dead IP for api.telegram.org.
# anna_net pins a reachable Telegram IP while keeping real TLS (SNI + validated cert).
_ns = importlib.util.spec_from_file_location("anna_net", ROOT / "scripts/anna_net.py")
AN = importlib.util.module_from_spec(_ns); _ns.loader.exec_module(AN)

def _load_env(p):
    p = Path(p)
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1); os.environ[k.strip()] = v.strip()

_load_env(ROOT / ".secrets/anna_telegram.env")
_load_env(ROOT / ".secrets/anna_llm.env")

# R1 SAFE-MODE BY DEFAULT: a Telegram demo must be PHYSICALLY unable to write to live systems.
# ANNA runs safe (no bookings/CRM/memory writes, no outbound webhooks) UNLESS the operator
# explicitly sets ANNA_LIVE=1 — going live is a separate, deliberate fire, never an accident.
# The intent-aware no-diagnosis judge is on by default for a public demo (oblique jailbreaks).
if os.environ.get("ANNA_LIVE") != "1":
    os.environ["ANNA_SAFE_MODE"] = "1"
os.environ.setdefault("ANNA_SEMANTIC_GUARD", "1")
SAFE_MODE = os.environ.get("ANNA_SAFE_MODE") == "1"

TOKEN = os.environ.get("ANNA_TELEGRAM_BOT_TOKEN")
API = f"https://api.telegram.org/bot{TOKEN}"

_s = importlib.util.spec_from_file_location("anna", ROOT / "scripts/anna_runtime_v1.py")
A = importlib.util.module_from_spec(_s); _s.loader.exec_module(A)

_b = importlib.util.spec_from_file_location("anna_booking", ROOT / "scripts/anna_booking_v1.py")
B = importlib.util.module_from_spec(_b); _b.loader.exec_module(B)   # L2 booking spine (confirmations/reminders)

LOG = ROOT / "SYSTEM/ANNA_MVP/runtime/telegram_log.jsonl"


# offset/seen persisted to disk → a restart never replays the backlog (no duplicate replies/bookings)
OFFSET_FILE = ROOT / "SYSTEM/ANNA_MVP/runtime/telegram_offset.txt"
SEEN_FILE = ROOT / "SYSTEM/ANNA_MVP/runtime/telegram_seen.json"


def api(method, _timeout=70, **params):
    """Telegram Bot API call through the blockade-aware adapter (returns {'ok':False,...} on failure).
    `_timeout` is the socket deadline; Telegram's own long-poll `timeout` stays inside params."""
    return AN.tg_call(TOKEN, method, _timeout=_timeout, **params)


def log(obj):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _load_offset():
    try:
        return int(OFFSET_FILE.read_text().strip())
    except Exception:
        return None


def _save_offset(o):
    try:
        OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = OFFSET_FILE.with_suffix(".txt.tmp"); tmp.write_text(str(o)); tmp.replace(OFFSET_FILE)
    except Exception:
        pass


def _load_seen():
    try:
        return set(json.loads(SEEN_FILE.read_text()))
    except Exception:
        return set()


def _save_seen(s):
    try:
        SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SEEN_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(sorted(s)[-500:]))   # keep last 500 ids — bounded
        tmp.replace(SEEN_FILE)
    except Exception:
        pass


def _tg_send(client_id, answer):
    """Deliver a drained (recovered) lead's real answer back to the patient's chat."""
    chat = str(client_id).replace("tg_", "")
    api("sendMessage", chat_id=chat, text=answer)


def handle(chat_id, text):
    anna = A.Anna(client_id=f"tg_{chat_id}")
    api("sendChatAction", chat_id=chat_id, action="typing", _timeout=10)
    t0 = time.time()
    reply, booking = anna.reply(text)         # always a 2-tuple; brain call is slow, typing shows meanwhile
    if anna.last_degraded:                     # brain was down → reply is an in-character holding line;
        log({"ts": A.now(), "chat": chat_id,   # the runtime already queued the lead + alerted the operator
             "brain_degraded": True, "in": text})
    # human typing rhythm: keep the indicator alive, then a length-based pause
    delay = A.typing_delay(reply)
    elapsed = time.time() - t0
    extra = max(0.0, delay - min(elapsed, delay))
    waited = 0.0
    while waited < extra:
        api("sendChatAction", chat_id=chat_id, action="typing", _timeout=10)
        step = min(4.0, extra - waited); time.sleep(step); waited += step
    api("sendMessage", chat_id=chat_id, text=reply)
    log({"ts": A.now(), "chat": chat_id, "in": text, "out": reply, "degraded": anna.last_degraded,
         "booking": bool(booking), "violations": anna.last_violations, "delay": delay})
    if booking:
        print(f"  📅 booking: {booking.get('service')} · {booking.get('preferred_time')} · {booking.get('name')}")


def main():
    if not TOKEN:
        print("NO ANNA_TELEGRAM_BOT_TOKEN"); sys.exit(1)
    me = api("getMe").get("result", {})
    print(f"ANNA on Telegram: @{me.get('username','?')} ({me.get('first_name','')})  — Ctrl-C to stop")
    print(f"backends: gateway keys={len(A._claude_keys())}  ·  offset persisted={'yes' if OFFSET_FILE.exists() else 'fresh'}")
    offset = _load_offset()
    seen = _load_seen()
    last_drain, fails = 0.0, 0
    while True:
        # answer recovered leads the moment the brain is back (bounded to ~once/60s, never blocks polling long)
        if time.time() - last_drain > 60:
            try:
                done = A.drain_pending(send=_tg_send)
                if done:
                    print(f"  ↻ восстановлено лидов: {len(done)}")
            except Exception as e:
                print("  ! drain error:", e)
            try:                                  # L2: deliver confirmations + queue/send reminders to patients
                B.due_reminders()
                sent = B.drain_outbox(send=_tg_send)
                if sent:
                    print(f"  📤 доставлено пациентам: {len(sent)}")
            except Exception as e:
                print("  ! booking drain error:", e)
            last_drain = time.time()

        upd = api("getUpdates", offset=offset, timeout=30)
        if not upd.get("ok"):
            fails += 1
            time.sleep(min(30, 2 ** min(fails, 4)))   # exponential backoff, capped 30s — don't hammer a degraded API
            continue
        fails = 0
        for u in upd.get("result", []):
            try:                                       # one bad update must NEVER kill the loop (was a permanent-exit path)
                uid = u.get("update_id")
                if uid is None:
                    continue
                offset = uid + 1
                if uid in seen:                        # replay (restart/reconnect) → skip, don't double-handle/double-book
                    _save_offset(offset); continue
                msg = u.get("message") or u.get("edited_message") or {}
                text = msg.get("text"); chat = (msg.get("chat") or {}).get("id")
                if text and chat is not None:
                    print(f"🧑 {chat}: {text}")
                    handle(chat, text)
                seen.add(uid); _save_seen(seen); _save_offset(offset)   # confirm only AFTER fully handled
            except Exception as e:
                log({"ts": A.now(), "handler_error": str(e)})
                print("  ! handler error:", e)


if __name__ == "__main__":
    main()

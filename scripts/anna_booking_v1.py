#!/usr/bin/env python3
"""
ANNA L2 — Booking spine V1 (manual confirmation loop).

The thin vertical slice of L2 "real booking": a record now has a LIFECYCLE instead of dying as a
local note. ANNA captures the lead (requested) → the clinic's reception confirms it in THEIR own
system → ANNA sends the patient a real confirmation → a reminder is queued. Works for ANY clinic
with zero external API/partnership and full stealth (it reads as a live admin checking the schedule).

Booking-spine: _book() routes to a backend by clinic config — here `manual` (default). The local JSON
under SYSTEM/ANNA_MVP/runtime/appointments stays the journal-of-truth under every backend; future
backends (gcal/yclients/dikidi) plug in behind the same create/confirm/remind/cancel interface.

Patient-facing messages (confirmation/reminder) are queued to patient_outbox.jsonl and DELIVERED by the
channel (Telegram drains it) — the same durable outbox+drain pattern as the L1 recovery queue.

Deterministic. No LLM (confirmations are reliable templates, not generated). No network here.

CLI (the reception/operator does the manual confirm):
  python3 scripts/anna_booking_v1.py list                       # pending + confirmed appointments
  python3 scripts/anna_booking_v1.py confirm <appt_id> [--when "сегодня 19:00"]
  python3 scripts/anna_booking_v1.py cancel  <appt_id>
  python3 scripts/anna_booking_v1.py reminders                  # queue due reminders
  python3 scripts/anna_booking_v1.py drain                      # deliver queued patient messages (no channel → dry print)
"""
import os, sys, json, argparse, importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_s = importlib.util.spec_from_file_location("anna", ROOT / "scripts/anna_runtime_v1.py")
A = importlib.util.module_from_spec(_s); _s.loader.exec_module(A)

_g = importlib.util.spec_from_file_location("anna_gcal", ROOT / "scripts/anna_gcal_v1.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G)   # gcal backend (gated behind creds)

APPTS = A.APPTS
OUTBOX = ROOT / "SYSTEM/ANNA_MVP/runtime/patient_outbox.jsonl"   # confirmations/reminders ANNA owes patients
BACKEND = os.environ.get("ANNA_BOOKING_BACKEND", "manual")       # manual (default) | gcal | yclients | dikidi


def now():
    return A.now()


def _load_appts(status=None):
    out = []
    if not APPTS.exists():
        return out
    for p in sorted(APPTS.glob("*.json")):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        rec["_id"] = p.stem; rec["_path"] = str(p)
        if status is None or rec.get("status") == status:
            out.append(rec)
    return out


def _save_appt(rec):
    p = Path(rec["_path"])
    d = {k: v for k, v in rec.items() if not k.startswith("_")}
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(p)


def _find(appt_id):
    for r in _load_appts():
        if r["_id"] == appt_id:
            return r
    return None


def _queue_patient(client_id, text, kind):
    A._append_jsonl(OUTBOX, {"ts": now(), "client_id": client_id, "text": text, "kind": kind, "sent": False})


def confirm(appt_id, when=None, start_iso=None):
    """Reception confirmed the slot → mark confirmed and queue a REAL confirmation to the patient.
    ANNA never claimed 'you are booked' on her own; the patient hears it only once it's actually true.
    If backend=gcal + creds + a real ISO slot → also create the real calendar event (external_id)."""
    r = _find(appt_id)
    if not r:
        return None
    r["status"] = "confirmed"
    r["backend"] = BACKEND
    r["confirmed_time"] = when or r.get("preferred_time") or ""
    if start_iso:
        r["confirmed_time_iso"] = start_iso
    # real calendar write — only when explicitly configured with clinic creds AND a real ISO slot
    if BACKEND == "gcal" and start_iso and G.configured():
        summary = f"Приём: {r.get('service','')} — {r.get('name') or r.get('client_id')}".strip()
        ev_id, err = G.create_event(summary, start_iso, description=(r.get("notes") or ""))
        if ev_id:
            r["external_id"] = ev_id
        else:
            r["backend"] = "manual"; r["gcal_error"] = err   # honest fallback: never pretend a calendar write happened
    _save_appt(r)
    t = r.get("confirmed_time") or ""
    msg = f"Всё, записала вас{(' на ' + t) if t else ''}. Если что-то поменяется, просто напишите, подстроимся."
    _queue_patient(r.get("client_id"), A._deemdash(msg), "confirmation")
    return r


def cancel(appt_id, tell_patient=True):
    r = _find(appt_id)
    if not r:
        return None
    r["status"] = "cancelled"; _save_appt(r)
    if tell_patient:
        _queue_patient(r.get("client_id"),
                       "Подскажите, удобнее перенести визит на другое время? Подберём, как вам комфортно.", "cancel")
    return r


def due_reminders():
    """Queue one reminder per confirmed-but-not-yet-reminded appointment. (Freeform time strings →
    keep it deterministic: remind once after confirmation; precise time-window logic is a later frontier.)"""
    queued = []
    for r in _load_appts(status="confirmed"):
        if r.get("reminded"):
            continue
        t = r.get("confirmed_time") or r.get("preferred_time") or ""
        msg = f"Напоминаю про визит{(' ' + t) if t else ''}, ждём вас. Если планы меняются, напишите, на связи."
        _queue_patient(r.get("client_id"), A._deemdash(msg), "reminder")
        r["reminded"] = True; _save_appt(r); queued.append(r["_id"])
    return queued


def drain_outbox(send=None):
    """Deliver queued patient messages (confirmations/reminders). `send(client_id, text)` is the channel
    hook (Telegram). Tolerant of torn lines — never stalls. Returns delivered messages."""
    if not OUTBOX.exists():
        return []
    rows = []
    for ln in OUTBOX.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue   # torn line → skip, never stall
    delivered, changed = [], False
    for m in rows:
        if m.get("sent"):
            continue
        if send:
            try:
                send(m["client_id"], m["text"])
            except Exception:
                continue   # delivery failed → leave unsent for next drain
        m["sent"] = True; m["sent_at"] = now(); changed = True
        delivered.append(m)
    if changed:
        tmp = OUTBOX.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
        tmp.replace(OUTBOX)
    return delivered


def main():
    p = argparse.ArgumentParser(description="ANNA L2 booking spine — manual confirmation loop")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    c = sub.add_parser("confirm"); c.add_argument("appt_id"); c.add_argument("--when"); c.add_argument("--start-iso")
    cn = sub.add_parser("cancel"); cn.add_argument("appt_id")
    sub.add_parser("reminders")
    sub.add_parser("drain")
    a = p.parse_args()

    if a.cmd == "list":
        reqs = _load_appts(status="requested"); conf = _load_appts(status="confirmed")
        print(f"📋 Записи · к подтверждению: {len(reqs)} · подтверждено: {len(conf)} · backend={BACKEND}\n")
        for r in reqs + conf:
            mark = "🟡 ждёт" if r.get("status") == "requested" else "🟢 подтв"
            print(f"{mark} [{r['_id']}] {r.get('service','')} · {r.get('confirmed_time') or r.get('preferred_time','')} "
                  f"· {r.get('name') or r.get('client_id')} · {r.get('phone','')}")
    elif a.cmd == "confirm":
        r = confirm(a.appt_id, when=a.when, start_iso=a.start_iso)
        if r:
            extra = f" · gcal event {r['external_id']}" if r.get("external_id") else (" · backend=manual" if BACKEND == "gcal" else "")
            print(f"🟢 подтверждено {a.appt_id} → подтверждение пациенту в outbox{extra}")
        else:
            print("❌ не найдено")
    elif a.cmd == "cancel":
        r = cancel(a.appt_id)
        print(f"⚪ отменено {a.appt_id}" if r else "❌ не найдено")
    elif a.cmd == "reminders":
        q = due_reminders(); print(f"⏰ поставлено напоминаний: {len(q)} {q}")
    elif a.cmd == "drain":
        d = drain_outbox()   # no send hook → dry: shows what WOULD be delivered (channel delivers in prod)
        print(f"📤 к доставке пациентам: {len(d)}")
        for m in d:
            print(f"→ {m['client_id']} [{m['kind']}]: {m['text']}")


if __name__ == "__main__":
    main()

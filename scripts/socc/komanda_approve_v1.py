#!/usr/bin/env python3
"""
КОМАНДА Approve V1 — the operator's one-screen approve gate (the only human step, by law).

The команда finds + drafts autonomously. SENDING a cold touch is gated to the operator's approve —
this is both ANNA's law H1 and ФЗ-38 (no mass auto-send of cold ads). This tool is that gate:
list the pending drafts, approve or skip them ONE BY ONE. Approving marks intent in the LEDGER;
the actual send (over the chosen channel) is a further explicit step, never automatic here.

Usage:
  python3 komanda_approve_v1.py --list                 # pending drafts (reachable first)
  python3 komanda_approve_v1.py --show 3               # full message of #3
  python3 komanda_approve_v1.py --approve 1,2,5        # mark approved (intent); prints how to send
  python3 komanda_approve_v1.py --approve reachable    # approve all reachable
  python3 komanda_approve_v1.py --skip 4              # never contact #4
"""
import sys, json, importlib.util as _ilu
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPROVE_Q = ROOT / "SOVEREIGN/LEDGER/komanda_approve_queue.json"
_ls = _ilu.spec_from_file_location("komanda_ledger_v1", ROOT / "scripts/socc/komanda_ledger_v1.py")
LED = _ilu.module_from_spec(_ls); _ls.loader.exec_module(LED)


def _load_q():
    if not APPROVE_Q.exists():
        print("очередь пуста — прогони команду: python3 scripts/socc/komanda_pipeline_v1.py --live \"<район>\"")
        raise SystemExit(0)
    return json.loads(APPROVE_Q.read_text(encoding="utf-8"))


def _save_q(q):
    APPROVE_Q.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")


def _pending(q):
    return [it for it in q["items"] if it.get("status") == "PENDING_APPROVE"]


def _resolve(arg, q):
    items = q["items"]
    if arg == "all":
        return [it["n"] for it in items if it.get("status") == "PENDING_APPROVE"]
    if arg == "reachable":
        return [it["n"] for it in items if it.get("status") == "PENDING_APPROVE" and it.get("reachable")]
    return [int(x) for x in arg.replace(" ", "").split(",") if x.strip().isdigit()]


def cmd_list(q):
    p = _pending(q)
    print(f"\n📋 ОЧЕРЕДЬ НА APPROVE · {q.get('place')} · {len(p)} писем · демо {q.get('demo_bot')}")
    print(f"   достижимы: {q['counts'].get('reachable', 0)}  ·  без канала: {q['counts'].get('unreachable', 0)}\n")
    for it in q["items"]:
        if it.get("status") != "PENDING_APPROVE":
            continue
        mark = "📨" if it.get("reachable") else "🚫"
        ch = it.get("channel", "?"); contact = it.get("contact") or "—"
        print(f"  {mark} [{it['n']:>2}] {it['clinic'][:34]:<34} {ch:<9} {contact[:32]}")
    print(f"\n  📨 = есть канал доставки · 🚫 = канал не найден (нужен контакт)")
    print(f"  approve: python3 scripts/socc/komanda_approve_v1.py --approve 1,2  |  --approve reachable")
    print(f"  показать письмо: --show <n>   ·   не беспокоить: --skip <n>")


def cmd_show(q, n):
    it = next((x for x in q["items"] if x["n"] == n), None)
    if not it:
        print(f"нет #{n}"); return
    print(f"\n──[{it['n']}] {it['clinic']}  ({it.get('channel')} · {it.get('contact') or 'нет канала'})  [{it['status']}]")
    print(f"   сигналы: {', '.join(it.get('signals', []))}\n")
    for line in it["message"].split("\n"):
        print(f"   {line}" if line else "")


def cmd_set(q, ns, status, led):
    changed = 0
    for it in q["items"]:
        if it["n"] in ns and it.get("status") == "PENDING_APPROVE":
            it["status"] = status
            LED.mark(led, it["key"], "approved" if status == "APPROVED" else "skip")
            changed += 1
            if status == "APPROVED":
                how = (f"канал {it.get('channel')} → {it.get('contact')}" if it.get("reachable")
                       else "⚠ канал не найден — нужен контакт перед отправкой")
                print(f"  ✅ approved [{it['n']}] {it['clinic']}  ·  {how}")
            else:
                print(f"  ⏭  skip [{it['n']}] {it['clinic']}")
    LED.save(led)
    _save_q(q)
    print(f"\n{changed} обновлено. ⛔ Отправка — отдельный явный шаг (огонь), ничего не ушло автоматически.")


def main():
    args = sys.argv[1:]
    q = _load_q()
    led = LED.load()
    if "--show" in args:
        cmd_show(q, int(args[args.index("--show") + 1])); return
    if "--approve" in args:
        cmd_set(q, _resolve(args[args.index("--approve") + 1], q), "APPROVED", led); return
    if "--skip" in args:
        cmd_set(q, _resolve(args[args.index("--skip") + 1], q), "SKIP", led); return
    cmd_list(q)


if __name__ == "__main__":
    main()

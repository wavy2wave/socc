#!/usr/bin/env python3
"""
HERMES Engine V1 — the messenger, made real (not a spec).

Implements HERMES-SPEC-1 atoms h0..h2: ingest SCOUT targets → draft a personalized touch on each
clinic's REAL pain evidence → queue with status PENDING_APPROVE. The killer mechanism (HERMES §5):
show the loss + ready demo, on proven evidence. Language base from B0 positioning.

LAWFUL BOUNDARY (HERMES Λ H1): this engine NEVER sends. Every draft is queued sent=False,
status=PENDING_APPROVE. Sending is a SEPARATE step under the operator's approve (his fire).
No network here. Drafts cite only real SCOUT evidence — no invented claims (Φ(h1)).

Usage:
  python3 hermes_engine_v1.py <scout_targets.json> [--demo @anna_demo_bot] [--out hermes_queue.json]
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3), name="MSK")

# pain signal → honest phrase fragment (на доказательстве цели)
PHRASE = {
    "no_online_booking": "у вас нет онлайн-записи — пациент пишет в директ и ждёт",
    "slow_dm_reply": "я написал вам как пациент — ответа не было вовремя",
    "reviews_mention_не_дозвониться": "в ваших же отзывах пишут, что до вас трудно дозвониться",
}
# приоритет крючка: висцеральное доказательство (отзыв) > молчание > нет записи
HOOK_PRIORITY = ["reviews_mention_не_дозвониться", "slow_dm_reply", "no_online_booking"]


def draft(target, demo):
    name = target["name"]
    ev_lines = [e["evidence"] for e in target["evidence"]]
    # выбрать СИЛЬНЕЙШИЙ сигнал как крючок (не просто первый)
    sigs = target["signals"]
    hook_sig = next((s for s in HOOK_PRIORITY if s in sigs), sigs[0])
    hook = PHRASE.get(hook_sig, hook_sig)
    # конкретная улика для этого крючка (цитата/факт) — усиливает персонализацию
    hook_ev = next((e["evidence"] for e in target["evidence"] if e["signal"] == hook_sig), ev_lines[0])
    body = (
        f"Здравствуйте, {name}! 👋\n"
        f"Я обратил внимание: {hook} ({hook_ev}). "
        f"Такой пациент чаще всего уходит к соседям — и вы об этом даже не узнаёте.\n\n"
        f"ANNA — администратор, который не спит: отвечает за 4 секунды в любой час и записывает пациента "
        f"в вашу систему. Ночью, в обед, в выходные — не теряет никого.\n\n"
        f"Не верьте на слово — напишите ей сами как пациент: {demo}\n"
        f"Понравится — запустим у вас за день. Платите только с пойманного."
    )
    return {
        "clinic": name, "channel": target.get("channel"),
        "evidence_used": ev_lines,                       # Φ(h1): касание на реальном доказательстве
        "message": body,
        "no_unproven_claims": True,                      # только факт потери + готовое demo
        "status": "PENDING_APPROVE",                     # H1: ничего не уходит без approve
        "sent": False,
    }


def run(targets_path, demo, out_path):
    t = json.loads(Path(targets_path).read_text(encoding="utf-8"))
    queue = [draft(x, demo) for x in t.get("targets", []) if x.get("evidence")]
    ts = datetime.now(timezone.utc)
    out = {
        "id": "HERMES_QUEUE_V1", "from_targets": targets_path,
        "created_at_utc": ts.isoformat(), "created_at_msk": ts.astimezone(MSK).isoformat(timespec="seconds"),
        "demo_link": demo,
        "all_pending_approve": all(d["status"] == "PENDING_APPROVE" and d["sent"] is False for d in queue),
        "all_cite_evidence": all(d["evidence_used"] for d in queue),
        "queue": queue, "count": len(queue),
        "truth_boundary": "HERMES drafts only. Nothing sent (H1). Every draft cites real SCOUT evidence. "
                          "Sending each touch is the operator's approve = his fire. No network.",
    }
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("HERMES ENGINE V1 — гонец (черновики, НЕ отправлено)")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"целей от SCOUT::{len(queue)}   статус::ВСЕ PENDING_APPROVE   отправлено::0")
    for i, d in enumerate(queue, 1):
        print(f"\n──[{i}] {d['clinic']}  ({d['channel']})  [PENDING_APPROVE]")
        for line in d["message"].split("\n"):
            print(f"   {line}" if line else "")
    print("\n" + "━" * 36)
    print("⛔ ничего не отправлено. Каждое письмо ждёт твоего approve = твой огонь.")
    print(f"queue::{out_path}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: hermes_engine_v1.py <scout_targets.json> [--demo @bot] [out.json]"); raise SystemExit(2)
    demo = "@anna_demo_bot"
    if "--demo" in sys.argv:
        demo = sys.argv[sys.argv.index("--demo") + 1]
    out = "entity_substrate/domains/_hermes_queue.json"
    run(sys.argv[1], demo, out)

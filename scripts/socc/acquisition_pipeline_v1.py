#!/usr/bin/env python3
"""
Acquisition Pipeline V1 — the one console for the selling machine.

Chains SCOUT → HERMES lawfully (PXS-1 gate: HERMES runs only if SCOUT produced PASS targets),
then gives the operator the APPROVE button. This is the "ты жмёшь одну кнопку" experience, end
to end, on sample data, fire-free.

LAWFUL BOUNDARY: approve only flips a draft to APPROVED_FOR_SEND. It does NOT send — actual
sending is a separate step that opens network (operator's fire). No network anywhere here.

Commands:
  run <domain.json> <feed.json> [--demo @bot]   # SCOUT→HERMES, build approve-queue
  status                                          # show queue + states
  approve <n|all>                                 # flip draft(s) to APPROVED_FOR_SEND (NOT sent)
"""
import json, sys, importlib.util
from pathlib import Path

ROOT = Path(".")
QUEUE = ROOT / "entity_substrate/domains/_hermes_queue.json"
TARGETS = ROOT / "entity_substrate/domains/_scout_targets.json"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def cmd_run(domain, feed, demo):
    scout = _load("scout_engine_v1", "scripts/socc/scout_engine_v1.py")
    hermes = _load("hermes_engine_v1", "scripts/socc/hermes_engine_v1.py")

    print("▶ STEP 1/2 · SCOUT — ищет и доказывает боль\n")
    s = scout.run(domain, feed, str(TARGETS))

    # PXS-1 gate: HERMES opens ONLY if SCOUT produced targets with evidence (s5 PASS)
    gate = bool(s["targets"]) and s["all_have_pain_evidence"]
    print(f"\n⛓  GATE SCOUT→HERMES :: {'OPEN (proof: targets с болью)' if gate else 'CLOSED (нет целей) — HERMES не стартует'}")
    if not gate:
        print("fail-closed: HERMES не запущен, потому что SCOUT не дал доказанных целей."); return

    print("\n▶ STEP 2/2 · HERMES — пишет касания (PENDING_APPROVE)\n")
    hermes.run(str(TARGETS), demo, str(QUEUE))
    print("\n✓ цепочка прошла. Дальше — ТВОЯ кнопка:  approve <n|all>")


def cmd_status():
    if not QUEUE.exists():
        print("очередь пуста — сначала `run`"); return
    q = json.loads(QUEUE.read_text(encoding="utf-8"))
    print("━━ ОЧЕРЕДЬ КАСАНИЙ ━━")
    for i, d in enumerate(q["queue"], 1):
        mark = "✅ APPROVED_FOR_SEND" if d["status"] == "APPROVED_FOR_SEND" else "⏳ PENDING_APPROVE"
        sent = "ОТПРАВЛЕНО" if d.get("sent") else "не отправлено"
        print(f"  {i}. {d['clinic']:<20} {mark:<22} · {sent}")
    n_app = sum(1 for d in q["queue"] if d["status"] == "APPROVED_FOR_SEND")
    print(f"— одобрено {n_app}/{len(q['queue'])} · отправлено 0 (отправка = огонь, сеть)")


def cmd_approve(sel):
    if not QUEUE.exists():
        print("очередь пуста — сначала `run`"); return
    q = json.loads(QUEUE.read_text(encoding="utf-8"))
    idxs = range(len(q["queue"])) if sel == "all" else [int(sel) - 1]
    for i in idxs:
        if 0 <= i < len(q["queue"]):
            q["queue"][i]["status"] = "APPROVED_FOR_SEND"   # НЕ sent — отправка отдельный шаг (огонь)
            q["queue"][i]["sent"] = False
    QUEUE.write_text(json.dumps(q, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✅ одобрено: {'все' if sel=='all' else sel}. Статус → APPROVED_FOR_SEND.")
    print("⛔ всё ещё НЕ отправлено. Реальная отправка открывает сеть = твой явный огонь (отдельный шаг).")
    cmd_status()


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); raise SystemExit(0)
    if a[0] == "run" and len(a) >= 3:
        demo = a[a.index("--demo") + 1] if "--demo" in a else "@anna_demo_bot"
        cmd_run(a[1], a[2], demo)
    elif a[0] == "status":
        cmd_status()
    elif a[0] == "approve" and len(a) >= 2:
        cmd_approve(a[1])
    else:
        print(__doc__)

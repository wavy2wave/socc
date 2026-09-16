#!/usr/bin/env python3
"""
ANNA Autonomy V1 — a REAL continuous loop that runs for days/weeks, lawfully.

Each cycle (cheap: ~2 brain calls): present ANNA a realistic patient opener (or a real
Telegram conversation if a new one arrived), let her brain answer, then a strict judge
scores it and extracts one concrete lesson. Lessons + rolling quality are accumulated so
ANNA's weak spots surface from REAL patterns (live learning, not a one-off sandbox).

Lawful + safe by construction:
- bounded per cycle, no entity/anna birth, no network beyond the brain gateway
- token-metered (token ledger), paced (sleep between cycles) to respect daily limits
- key rotation + backoff: if all keys hit the daily limit, it SLEEPS and resumes (survives days)
- operator kill-switch (touch STOP file) + max hours/cycles
- it does NOT silently rewrite ANNA's prompt — it surfaces fixes for operator review (no drift)
- operator-visible state + cycle log + periodic proof

Run (background):  nohup python3 scripts/anna_autonomy_v1.py &
Stop:              touch SYSTEM/ANNA_MVP/autonomy/STOP
"""
import os, sys, time, json, random, importlib.util, hashlib, atexit, signal
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
_s = importlib.util.spec_from_file_location("anna", ROOT / "scripts/anna_runtime_v1.py")
A = importlib.util.module_from_spec(_s); _s.loader.exec_module(A)

AUT = ROOT / "SYSTEM/ANNA_MVP/autonomy"
STATE = AUT / "STATE.json"
STOP = AUT / "STOP"
CYCLES = AUT / "cycles.jsonl"
LESSONS = AUT / "lessons.jsonl"
PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/SOCC_ANNA_AUTONOMY_V1_PROOF.json"
TG_LOG = ROOT / "SYSTEM/ANNA_MVP/runtime/telegram_log.jsonl"

SLEEP = int(os.environ.get("ANNA_AUT_SLEEP", "150"))      # pace between cycles (s)
MAX_HOURS = float(os.environ.get("ANNA_AUT_MAX_HOURS", "720"))   # ~30 days
BACKOFF = int(os.environ.get("ANNA_AUT_BACKOFF", "1800"))  # sleep when all keys exhausted (s)

SYMPTOMS = ["ноет зуб справа снизу", "скол переднего зуба", "кровит десна при чистке",
            "болит под коронкой", "застряло между зубами и ноет", "шатается зуб",
            "флюс на щеке", "ребёнку 6 лет, жалуется на зуб", "выпала пломба",
            "ноет зуб мудрости", "чувствительность на холодное", "запах изо рта и кровит"]
STATES = ["второй день терпит", "паникует, боится стоматолога", "торопится, на работе",
          "хочет просто узнать цену", "недоволен прошлой клиникой", "сомневается, надо ли вообще",
          "просит срочно сегодня", "спокойно планирует осмотр"]
OPENERS = ["привет", "Здравствуйте", "можно записаться?", "вы работаете сегодня?",
           "сколько стоит осмотр", "у меня вопрос"]

JUDGE_SYS = (
    "Ты строгий тренер администратора стоматологии. Дан один ответ Анны клиенту. Оцени КОРОТКО. "
    "Верни СТРОГО JSON одной строкой: "
    '{"human":N,"brevity":N,"empathy":N,"booking_drive":N,"lesson":"один короткий вывод как улучшить"}. '
    "N=1..5. Будь придирчив к длинным/ботовским/шаблонным ответам.")


def now(): return datetime.now(timezone.utc).isoformat()
def rj(p):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return {}
def append(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
def wj(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + ".tmp")                         # atomic: a crash mid-write never wipes state to {}
    tmp.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def make_opener(i):
    if random.random() < 0.4:
        return random.choice(OPENERS)
    return f"Здравствуйте, {random.choice(SYMPTOMS)}, {random.choice(STATES)}"


def judge(opener, reply):
    # multi-backend (not a single gateway) so one dead host doesn't zero all scoring
    out, err = A.llm_complete(JUDGE_SYS, [{"role": "user", "content": f"Клиент: {opener}\nАнна: {reply}"}])
    if not out:
        return None
    import re
    m = re.search(r"\{.*\}", out, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None


def write_proof(state):
    p = {"id": "SOCC_ANNA_AUTONOMY_V1_PROOF", "created_at_utc": now(), "status": "RUNNING",
         "cycles": state["cycles"], "rolling_avg": state["rolling_avg"],
         "started_at": state["started_at"], "last_cycle_at": state["last_cycle_at"],
         "entity_born": False, "anna_born": False, "no_daemon_beyond_this_bounded_trainer": True,
         "no_network_beyond_brain": True, "operator_killswitch": str(STOP),
         "truth_boundary": ("Bounded continuous ANNA training loop. Evaluates dialogues and "
                            "accumulates lessons; does NOT rewrite ANNA's prompt, birth anything, "
                            "or act outside the brain gateway. Operator can stop via STOP file.")}
    p["proof_hash"] = hashlib.sha256(json.dumps(p, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    wj(PROOF, p)


_RUN = {"st": None}


def _finalize(*_a):
    """Honest liveness: mark not-running on ANY exit (clean / SIGTERM / crash) so STATE never lies green."""
    st = _RUN.get("st")
    if st is not None:
        st["running"] = False
        st["last_beat"] = now()
        try:
            wj(STATE, st)
        except Exception:
            pass


def main():
    AUT.mkdir(parents=True, exist_ok=True)
    if STOP.exists(): STOP.unlink()
    st = rj(STATE) or {}
    if not st.get("cycles") and CYCLES.exists():        # corrupt/empty STATE → recover count from the cycle log
        try: st["cycles"] = sum(1 for _ in open(CYCLES, encoding="utf-8"))
        except Exception: pass
    st.setdefault("started_at", now()); st.setdefault("cycles", 0)
    st.setdefault("scores", []); st.setdefault("rolling_avg", None)
    st["running"] = True; st["pid"] = os.getpid(); st["last_beat"] = now()
    _RUN["st"] = st
    wj(STATE, st)
    atexit.register(_finalize)
    for _sig in (signal.SIGTERM, signal.SIGINT):
        try: signal.signal(_sig, lambda *a: sys.exit(0))   # → atexit fires _finalize, STATE honestly marked stopped
        except Exception: pass
    print(f"ANNA Autonomy started · pid={os.getpid()} · sleep={SLEEP}s · stop: touch {STOP}")
    t_start = time.time()

    while True:
        if STOP.exists():
            print("STOP flag — exiting"); break
        if (time.time() - t_start) / 3600.0 > MAX_HOURS:
            print("max hours reached — exiting"); break

        try:                                              # one bad cycle must NEVER kill the loop
            st["last_beat"] = now()                       # honest heartbeat: a monitor derives alive from this + live pid
            opener = make_opener(st["cycles"])
            anna = A.Anna(client_id=f"aut_{st['cycles'] % 50}")
            anna.mem = {"client_id": anna.client_id, "profile_summary": "", "history": []}
            reply, _booking = anna.reply(opener)

            if anna.last_degraded:                        # brain down (all backends) → sleep & resume, survives days
                print(f"  brain unavailable → backoff {BACKOFF}s")
                st["last_error"] = "brain_degraded"; wj(STATE, st)
                time.sleep(BACKOFF); continue

            verdict = judge(opener, reply)
            score = None
            if verdict:
                vals = [verdict.get(k) for k in ("human", "brevity", "empathy", "booking_drive") if isinstance(verdict.get(k), int)]
                score = round(sum(vals) / len(vals), 2) if vals else None
                if verdict.get("lesson"):
                    append(LESSONS, {"ts": now(), "cycle": st["cycles"], "lesson": verdict["lesson"], "score": score})

            st["cycles"] += 1
            st["last_cycle_at"] = now()
            if score is not None:
                st["scores"] = (st["scores"] + [score])[-100:]
                st["rolling_avg"] = round(sum(st["scores"]) / len(st["scores"]), 2)
            append(CYCLES, {"ts": now(), "cycle": st["cycles"], "opener": opener,
                            "reply": reply, "score": score, "violations": anna.last_violations})
            wj(STATE, st)
            if st["cycles"] % 20 == 0:
                write_proof(st)
            if st["cycles"] % 25 == 0:                 # periodically re-distill lessons → PROPOSED playbook
                try:                                    # (operator still approves before ANNA applies it — no drift)
                    _sp = importlib.util.spec_from_file_location("anna_playbook", ROOT / "scripts/anna_playbook_v1.py")
                    _pb = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(_pb)
                    prop = _pb.distill(); _pb.self_model()
                    st["playbook_proposed"] = {"principles": len(prop.get("principles", [])), "at": now()}
                    print(f"  📋 playbook re-distilled → PROPOSED ({len(prop.get('principles', []))} принципов) · approve when ready")
                except Exception as _e:
                    print(f"  (playbook distill skipped: {_e})")
            print(f"  cycle {st['cycles']}: score={score} avg={st['rolling_avg']} | {opener[:32]} → {reply[:48]}")
            time.sleep(SLEEP)
        except Exception as e:                            # defense in depth (the supervisor also restarts on death)
            append(CYCLES, {"ts": now(), "cycle": st.get("cycles"), "error": str(e)[:200]})
            st["last_error"] = str(e)[:200]
            try: wj(STATE, st)
            except Exception: pass
            time.sleep(min(BACKOFF, 60))

    st["running"] = False; wj(STATE, st); write_proof(st)
    print("ANNA Autonomy stopped.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import json, argparse, time, hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT=Path(__file__).resolve().parents[2]
MSK=timezone(timedelta(hours=3), name="MSK")

ROUTE=ROOT/"core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
LOOP_DIR=ROOT/"core/socc/autonomy/self_building/loop"
STATE=LOOP_DIR/"SELF_BUILDING_MODE_STATE_V1.json"
PROGRESS=LOOP_DIR/"SELF_BUILDING_VISIBLE_PROGRESS_V1.json"
LEDGER=LOOP_DIR/"SELF_BUILDING_TICK_LEDGER_V1.jsonl"
STOP=LOOP_DIR/"STOP_SELF_BUILDING.flag"

def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")

def now_utc():
    return datetime.now(timezone.utc).isoformat()

def read(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def write(p,o):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(o,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def append_jsonl(p,o):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(o,ensure_ascii=False,sort_keys=True)+"\n")

def h(o):
    return hashlib.sha256(json.dumps(o,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:24]

def tick_once(i):
    route=read(ROUTE)
    state=read(STATE)
    lawful_next=route.get("lawful_next") or route.get("real_next")

    allowed_routes=[
        "validate_observable_bounded_self_building_loop_v1",
        "enable_self_building_mode_v1",
        "self_building_idle_visible_tick_v1"
    ]

    can_execute = lawful_next in allowed_routes

    tick={
        "tick":i,
        "created_at_msk":now_msk(),
        "created_at_utc":now_utc(),
        "status":"PASS" if can_execute else "BLOCKED",
        "current_route":route.get("current_route"),
        "lawful_next":lawful_next,
        "executed_action":"visible_tick_only",
        "can_execute_route":can_execute,
        "proof_written":True,
        "semantic_null_detected":False if can_execute else True,
        "self_building_mode_enabled":state.get("self_building_mode_enabled") is True,
        "continuous_loop_enabled":state.get("continuous_loop_enabled") is True,
        "daemon_running":False,
        "scheduler_installed":False,
        "background_loop_enabled":False,
        "network_used":False,
        "agi_claim_allowed":False,
        "truth_boundary":"Observable bounded loop tick only. No daemon, scheduler, background process, network, queue widening, Entity birth, ANNA birth, final canon, or AGI claim."
    }
    tick["tick_hash"]=h(tick)

    append_jsonl(LEDGER,tick)

    progress={
        "id":"SELF_BUILDING_VISIBLE_PROGRESS_V1",
        "updated_at_msk":now_msk(),
        "last_tick":i,
        "last_tick_status":tick["status"],
        "last_lawful_next":lawful_next,
        "last_tick_hash":tick["tick_hash"],
        "total_ticks_recorded":i,
        "stop_file_exists":STOP.exists(),
        "daemon_running":False,
        "scheduler_installed":False,
        "background_loop_enabled":False,
        "network_used":False
    }
    write(PROGRESS,progress)

    print("TICK::"+str(i))
    print("STATUS::"+tick["status"])
    print("LAWFUL_NEXT::"+str(lawful_next))
    print("ACTION::visible_tick_only")
    print("LEDGER::"+str(LEDGER))
    print("TICK_HASH::"+tick["tick_hash"])
    print("----")

    return tick["status"]=="PASS"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=3)
    ap.add_argument("--sleep", type=float, default=0.5)
    args=ap.parse_args()

    if args.ticks < 1:
        raise SystemExit("ticks must be >= 1")

    print("SOCC OBSERVABLE BOUNDED SELF-BUILDING LOOP")
    print("MODE::visible_bounded")
    print("MAX_TICKS::"+str(args.ticks))
    print("STOP_FILE::"+str(STOP))

    passed=0
    for i in range(1,args.ticks+1):
        if STOP.exists():
            print("STOP_FILE_DETECTED::True")
            break
        if tick_once(i):
            passed+=1
        time.sleep(args.sleep)

    print("LOOP_FINISHED::True")
    print("TICKS_ATTEMPTED::"+str(args.ticks))
    print("TICKS_PASS::"+str(passed))
    print("DAEMON_RUNNING::False")
    print("SCHEDULER_INSTALLED::False")
    print("BACKGROUND_LOOP_ENABLED::False")
    print("NETWORK_USED::False")

if __name__=="__main__":
    main()

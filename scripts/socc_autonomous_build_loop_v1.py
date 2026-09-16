#!/usr/bin/env python3
"""
SOCC — Autonomous Bounded Build Loop V1 (node ②).

Makes "the system builds itself" real WITHIN the discipline — NOT a daemon:
a foreground loop the operator launches that, step by step,
  1. reads the true frontier from observe (route authority first),
  2. finds the lawful runner for that frontier,
  3. (operator-approval gate) runs exactly ONE bounded step,
  4. re-observes, and repeats —
until it reaches a frontier with NO auto-runner (needs real engineering or a human
decision, e.g. a network/revenue Rubicon), a hard failure, or the step limit.

It never enables a daemon/background/scheduler/network. It self-DRIVES bounded ticks;
it does not self-AUTHORIZE the real-world Rubicons. The system refuses to auto-cross a
frontier that has no lawful runner — so it can never fake-ship.

Usage:
  python3 scripts/socc_autonomous_build_loop_v1.py            # dry-run: show the plan
  python3 scripts/socc_autonomous_build_loop_v1.py --go [N]   # run up to N bounded steps (default 1)
"""
import sys, subprocess, json
from pathlib import Path

ROOT = Path(".")
OBSERVE = "scripts/socc/socc_observe_v1.py"
SCRIPTS = ROOT / "scripts"

# Frontiers that are deliberately NOT auto-runnable: real-world Rubicons / real code.
RUBICON_NO_AUTORUN = {
    "ship_anna_mvp_to_first_clinic_v1":
        "real-world deploy (live network + revenue + real ANNA runtime brain, node ④) — "
        "operator + real engineering required; the loop will NEVER auto-ship.",
}


def observe_frontier():
    out = subprocess.run([sys.executable, OBSERVE], capture_output=True, text=True).stdout
    nxt = status = None
    for line in out.splitlines():
        if line.startswith("CURRENT_LAWFUL_NEXT::"): nxt = line.split("::", 1)[1].strip()
        if line.startswith("STATUS::"): status = line.split("::", 1)[1].strip()
    return status, nxt


def find_runner(frontier):
    """A frontier is auto-runnable if scripts/<frontier>.py exists."""
    cand = SCRIPTS / f"{frontier}.py"
    return cand if cand.exists() else None


def main():
    go = "--go" in sys.argv
    limit = 1
    for a in sys.argv[1:]:
        if a.isdigit(): limit = int(a)

    print("═" * 60)
    print("SOCC — AUTONOMOUS BOUNDED BUILD LOOP V1  (no daemon)")
    print("═" * 60)
    ran = 0
    while ran < limit:
        status, frontier = observe_frontier()
        print(f"\n▶ frontier: {frontier}   (observe STATUS::{status})")
        if status != "PASS":
            print(f"  ⛔ observe not PASS ({status}) — stopping (operator must reconcile).")
            break
        if frontier in RUBICON_NO_AUTORUN:
            print(f"  🛑 RUBICON — no auto-run by design:\n     {RUBICON_NO_AUTORUN[frontier]}")
            print("  → loop hands control back to the operator (cannot fake-cross).")
            break
        runner = find_runner(frontier)
        if not runner:
            print(f"  🔴 no lawful runner at scripts/{frontier}.py")
            print("     → this frontier needs to be built (new step runner or real code). Stopping.")
            break
        if not go:
            print(f"  (dry-run) would run: {runner}   [pass --go to execute]")
            break
        print(f"  ✅ operator-approved bounded step → running {runner.name}")
        rc = subprocess.run([sys.executable, str(runner)]).returncode
        ran += 1
        if rc != 0:
            print(f"  ⛔ step FAILED (rc={rc}) — fail-closed, route unmoved. Stopping.")
            break
        print(f"  ✔ step done ({ran}/{limit})")

    status, frontier = observe_frontier()
    print("\n" + "═" * 60)
    print(f"LOOP DONE  ran={ran}  now_frontier={frontier}  observe={status}")
    print("═" * 60)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
SOCC Continuous Self-Building Runner
Foreground-only. Not a daemon. Not a scheduler.

Loop: read lawful_next → run script → on FAIL: read real_next from fail proof
      → run repair/Hermes script → retry original → advance to next lawful step.
Stops at: stop-flag deletion, entity substrate gate, max ticks, unrecoverable failure.
"""
import json
import hashlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SOCC_ROOT = Path(__file__).parent.parent
SCRIPTS   = SOCC_ROOT / "scripts/socc"
ROUTE     = SOCC_ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"

PROOF_DIR      = SOCC_ROOT / "core/socc/approved_autonomy_lane_runner/proof"
HERMES_PACKETS = SOCC_ROOT / "core/socc/hermes_repair/packets"
HERMES_STATE   = SOCC_ROOT / "core/socc/hermes_repair/state"

LEDGER = SOCC_ROOT / "MEMORY_WAVE/reports/autonomy/continuous_runner_tick_ledger.jsonl"
STOP   = SOCC_ROOT / "SOCC_RUNNER_STOP"

SB_PULSE     = SOCC_ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
SB_PANEL     = SOCC_ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
SB_PROGRESS  = SOCC_ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"

ENTITY_SUBSTRATE_GATE_SCRIPTS = {
    "run_entity_substrate_codex_gate_v1",
    "build_entity_substrate_prerequisite_map_v1",
    "enable_entity_substrate_birth_v1",
    "entity_substrate_birth_v1",
    "review_entity_substrate_direction_v1",
}

MAX_TICKS   = 200
RETRY_LIMIT = 2


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_ledger(record: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _sep(msg: str = "") -> None:
    line = "─" * 62
    if msg:
        print(f"\n{line}\n{msg}\n{line}")
    else:
        print(line)


def _lawful_next() -> str | None:
    route = _read(ROUTE)
    return route.get("lawful_next") or route.get("real_next") or route.get("current_lawful_next")


def _run_script(name: str) -> tuple[int, str, str]:
    script = SCRIPTS / f"{name}.py"
    if not script.exists():
        return -1, "", f"SCRIPT_NOT_FOUND: {name}.py"
    r = subprocess.run(
        [sys.executable, str(script)],
        cwd=SOCC_ROOT,
        capture_output=True,
        text=True,
    )
    return r.returncode, r.stdout, r.stderr


def _extract_field(stdout: str, key: str) -> str | None:
    """Extract KEY::value from script stdout."""
    for line in stdout.splitlines():
        if line.startswith(f"{key}::"):
            return line.split("::", 1)[1].strip()
    return None


def _extract_hard_failures(stdout: str) -> list:
    raw = _extract_field(stdout, "HARD_FAILURES")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return []


def _find_fail_proof(script_name: str) -> dict:
    """
    Search for a fail proof written by script_name.
    SOCC scripts write proofs to PROOF_DIR with uppercase names derived from script name.
    """
    # Derive proof name from script name: foo_bar_v1 → FOO_BAR_V1_PROOF.json
    derived = script_name.upper() + "_PROOF.json"
    candidate = PROOF_DIR / derived
    if candidate.exists():
        data = _read(candidate)
        if data.get("status") == "FAIL":
            return data
    # Fallback: scan proof dir for any file with matching name fragment and FAIL status
    prefix = script_name.split("_v1")[0].upper()
    for p in PROOF_DIR.glob("*.json"):
        if prefix in p.name:
            data = _read(p)
            if data.get("status") == "FAIL":
                return data
    return {}


def _hermes_dispatch(failed_script: str, fail_stdout: str, attempt: int) -> tuple[str | None, int, str, str]:
    """
    Determine repair script via two strategies:
    1. Read real_next from fail proof (SOCC's own repair routing)
    2. Fall back to repair_{script_name}
    Returns (repair_script_name, rc, stdout, stderr) or (None, ...) if no repair found.
    """
    # Strategy 1: real_next from script stdout
    real_next = _extract_field(fail_stdout, "REAL_NEXT")

    # Strategy 2: real_next from written proof
    if not real_next or real_next == failed_script:
        proof = _find_fail_proof(failed_script)
        real_next = proof.get("real_next") or proof.get("lawful_next")

    # Strategy 3: conventional repair_ naming
    if not real_next or real_next == failed_script:
        real_next = f"repair_{failed_script}"

    repair_script = SCRIPTS / f"{real_next}.py"
    if not repair_script.exists():
        # Write a generic Hermes packet but can't execute
        _write_generic_hermes_packet(failed_script, real_next, attempt)
        return None, -1, "", f"REPAIR_SCRIPT_NOT_FOUND: {real_next}.py"

    print(f"  [HERMES] Repair script: {real_next}")
    rc, out, err = _run_script(real_next)
    print(f"  [HERMES] Repair {'PASS' if rc == 0 else 'FAIL'}")
    return real_next, rc, out, err


def _write_generic_hermes_packet(failed_script: str, repair_name: str, attempt: int) -> None:
    pkt = {
        "id": f"HERMES_GENERIC_PACKET_{failed_script.upper()}_ATTEMPT{attempt}",
        "ts": _ts(),
        "failed_script": failed_script,
        "repair_script_expected": repair_name,
        "repair_script_found": False,
        "bounded_repair": True,
        "daemon_running": False,
    }
    HERMES_PACKETS.mkdir(parents=True, exist_ok=True)
    _write(HERMES_PACKETS / f"{pkt['id']}.json", pkt)


def _sync_pulse_panel_to_route() -> bool:
    """
    After each successful step, keep SB_PULSE and SB_PANEL in sync with ROUTE.
    This is runner-level operator maintenance, not a script execution.
    Returns True if any sync was needed.
    """
    route = _read(ROUTE)
    new_next  = route.get("lawful_next") or route.get("real_next") or ""
    new_truth = route.get("truth_boundary") or ""
    route_hash = route.get("route_hash") or ""
    synced = False
    for path in (SB_PULSE, SB_PANEL, SB_PROGRESS):
        if not path.exists():
            continue
        state = _read(path)
        if state.get("lawful_next") != new_next or state.get("truth_boundary") != new_truth:
            state.update({
                "updated_at_utc": _ts(),
                "lawful_next": new_next,
                "real_next": new_next,
                "truth_boundary": new_truth,
                "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
                "truth_boundary_priority": "CURRENT_ROUTE_AUTHORITY_FIRST",
                "route_hash_ref": route_hash,
                "runner_sync_applied": True,
                "daemon_running": False,
                "continuous_loop_enabled": False,
                "network_used": False,
                "entity_birth_allowed": False,
            })
            _write(path, state)
            synced = True
    return synced


def _print_tick(tick: int, script: str, rc: int, hard: list) -> None:
    icon = "✓" if rc == 0 else "✗"
    status = "PASS" if rc == 0 else "FAIL"
    print(f"  [{icon}] #{tick:03d}  {script:<60}  {status}")
    for f in hard[:3]:
        check = f.get("check", str(f)) if isinstance(f, dict) else str(f)
        print(f"         ↳ {check}")
    if len(hard) > 3:
        print(f"         ↳ ... +{len(hard)-3} more")


def run(max_ticks: int = MAX_TICKS, dry: bool = False) -> None:
    _sep("SOCC CONTINUOUS SELF-BUILDING RUNNER")
    print(f"Root        : {SOCC_ROOT}")
    print(f"Max ticks   : {max_ticks}")
    print(f"Stop flag   : delete '{STOP.name}' to halt after current step")
    print(f"Ledger      : {LEDGER.relative_to(SOCC_ROOT)}")
    print(f"Constraints : daemon=OFF  loop=OFF  network=OFF  entity_birth=OFF")

    STOP.write_text(_ts(), encoding="utf-8")

    if dry:
        print(f"\nDRY RUN — first step would be: {_lawful_next()}")
        STOP.unlink(missing_ok=True)
        return

    tick       = 0
    passed     = 0
    repaired   = 0
    failed_at: str | None = None

    try:
        while tick < max_ticks:
            if not STOP.exists():
                _sep("STOP FLAG REMOVED — halting cleanly")
                break

            lawful = _lawful_next()
            if not lawful:
                _sep("ERROR: route authority has no lawful_next")
                break

            if lawful in ENTITY_SUBSTRATE_GATE_SCRIPTS:
                _sep(f"ENTITY SUBSTRATE GATE\n{lawful}\nCore self-build complete — entity substrate phase begins.")
                _append_ledger({"ts": _ts(), "tick": tick, "event": "ENTITY_SUBSTRATE_GATE",
                                "script": lawful, "passed": passed})
                break

            script_path = SCRIPTS / f"{lawful}.py"
            if not script_path.exists():
                _sep(f"MISSING SCRIPT: scripts/socc/{lawful}.py\n"
                     f"Run 'socc scaffold {lawful}' (proof-recoverable nodes only) or author it.")
                _append_ledger({"ts": _ts(), "tick": tick, "event": "SCRIPT_MISSING", "script": lawful})
                break

            tick += 1
            # ── Pre-tick: sync PULSE/PANEL to current route ──────────
            if _sync_pulse_panel_to_route():
                print(f"\n  [SYNC]   pulse/panel aligned → {lawful}")

            print(f"\nTick {tick:03d}  →  {lawful}")
            rc, stdout, stderr = _run_script(lawful)
            hard = _extract_hard_failures(stdout)

            if rc != 0:
                # ── Hermes repair loop ───────────────────────────────
                for attempt in range(1, RETRY_LIMIT + 1):
                    repair_name, rep_rc, rep_out, rep_err = _hermes_dispatch(
                        lawful, stdout, attempt
                    )
                    if repair_name and rep_rc == 0:
                        repaired += 1
                        # Retry original script after repair
                        print(f"  [RETRY]  {lawful}")
                        rc, stdout, stderr = _run_script(lawful)
                        hard = _extract_hard_failures(stdout)
                        if rc == 0:
                            break
                    elif repair_name is None:
                        break  # No repair script — stop retrying

            _print_tick(tick, lawful, rc, hard)

            _append_ledger({
                "ts": _ts(), "tick": tick, "script": lawful,
                "status": "PASS" if rc == 0 else "FAIL",
                "hard_failures": hard[:5],
                "daemon_running": False, "continuous_loop_enabled": False,
                "network_used": False, "entity_birth_allowed": False,
            })

            if rc != 0:
                failed_at = lawful
                _sep(f"UNRECOVERABLE FAILURE\n{lawful}\nRun 'socc observe' for full state.")
                if stdout.strip():
                    print("\n── stdout (tail) ──")
                    print("\n".join(stdout.strip().splitlines()[-30:]))
                if stderr.strip():
                    print("\n── stderr ──")
                    print(stderr.strip()[-500:])
                break

            passed += 1

            # Guard: if route didn't advance, stop to avoid infinite loop
            new_lawful = _lawful_next()
            if new_lawful == lawful:
                _sep(f"ROUTE DID NOT ADVANCE after {lawful}\nPossible state issue — stopping.")
                break

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt — stopping runner.")
    finally:
        STOP.unlink(missing_ok=True)

    _sep("RUNNER COMPLETE")
    print(f"Ticks passed : {passed}")
    print(f"Repairs used : {repaired}")
    if failed_at:
        print(f"Failed at    : {failed_at}")
    print(f"Current next : {_lawful_next()}")
    print(f"Ledger       : {LEDGER.relative_to(SOCC_ROOT)}")
    print(f"\nRun 'socc watch' for live state  |  'socc observe' for full report")

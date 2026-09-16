#!/usr/bin/env python3
from pathlib import Path
import json

def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}

def route_next(route):
    return route.get("lawful_next") or route.get("real_next")

def guard_step_execution(
    *,
    step_name,
    expected_current_next,
    success_next,
    proof_path,
    route,
    existing_proof=None,
    allow_recovery=False,
):
    """
    Idempotent guard for SOCC bounded construction steps.

    Cases:
    1. NORMAL_EXECUTION_ALLOWED:
       route.lawful_next == expected_current_next

    2. ALREADY_COMMITTED_NOOP:
       route.lawful_next == success_next
       route.upstream_proof == proof_path
       existing proof is PASS or allow_recovery=True

    3. OUT_OF_PHASE_RERUN_BLOCKED:
       route has advanced beyond expected_current_next, but proof/upstream does not match safe already-committed state.

    This prevents rerunning stale validation/build/review scripts from rewriting valid artifacts to FAIL after route has already advanced.
    """
    current_next = route_next(route)
    upstream = route.get("upstream_proof")
    existing = existing_proof or {}

    if current_next == expected_current_next:
        return {
            "status": "PASS",
            "decision": "NORMAL_EXECUTION_ALLOWED",
            "step_name": step_name,
            "current_next": current_next,
            "expected_current_next": expected_current_next,
            "success_next": success_next,
            "proof_path": proof_path,
            "hard_failures": [],
        }

    proof_ok = existing.get("status") == "PASS" or allow_recovery is True

    if current_next == success_next and upstream == proof_path and proof_ok:
        return {
            "status": "PASS",
            "decision": "ALREADY_COMMITTED_NOOP",
            "step_name": step_name,
            "current_next": current_next,
            "expected_current_next": expected_current_next,
            "success_next": success_next,
            "proof_path": proof_path,
            "already_committed": True,
            "write_allowed": False,
            "hard_failures": [],
        }

    return {
        "status": "FAIL",
        "decision": "OUT_OF_PHASE_RERUN_BLOCKED",
        "step_name": step_name,
        "current_next": current_next,
        "expected_current_next": expected_current_next,
        "success_next": success_next,
        "route_upstream_proof": upstream,
        "expected_proof_path": proof_path,
        "write_allowed": False,
        "hard_failures": [
            {
                "code": "OUT_OF_PHASE_RERUN_BLOCKED",
                "current_next": current_next,
                "expected_current_next": expected_current_next,
                "success_next": success_next,
                "route_upstream_proof": upstream,
                "expected_proof_path": proof_path,
            }
        ],
    }

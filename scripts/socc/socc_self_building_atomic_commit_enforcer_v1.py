#!/usr/bin/env python3
import json
import importlib.util
from pathlib import Path

ROOT = Path(".")
HELPER = ROOT / "scripts/socc/socc_route_atomic_commit_helper_v1.py"
POLICY = ROOT / "core/socc/autonomy/self_building/atomic_commit/enforcement/ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_POLICY_V1.json"

FORBIDDEN_DIRECT_ROUTE_WRITE_REASON = "direct_route_write_forbidden_after_atomic_commit_review"

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def load_helper():
    spec = importlib.util.spec_from_file_location("socc_route_atomic_commit_helper_v1", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def policy_enabled():
    p = read_json(POLICY)
    return p.get("status") == "ENFORCED" and p.get("atomic_commit_required_for_route_transitions") is True

def enforce_atomic_commit_transition(
    *,
    lawful_next,
    upstream_proof,
    truth_boundary,
    route_updates=None,
    pulse_updates=None,
    panel_updates=None,
    progress_updates=None,
    reason="atomic_commit_enforced_self_building_lane",
):
    if not policy_enabled():
        return {
            "status": "FAIL",
            "committed": False,
            "hard_failures": [
                {"code": "POLICY_NOT_ENFORCED", "check": "policy_enabled", "actual": policy_enabled()}
            ],
        }

    helper = load_helper()
    return helper.atomic_commit(
        lawful_next=lawful_next,
        upstream_proof=upstream_proof,
        truth_boundary=truth_boundary,
        route_updates=route_updates or {},
        pulse_updates=pulse_updates or {},
        panel_updates=panel_updates or {},
        progress_updates=progress_updates or {},
        reason=reason,
    )

def reject_direct_route_write(reason=None):
    return {
        "status": "BLOCKED",
        "allowed": False,
        "reason": reason or FORBIDDEN_DIRECT_ROUTE_WRITE_REASON,
        "required_method": "enforce_atomic_commit_transition",
    }

#!/usr/bin/env python3
import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PROGRESS = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"

ROLLBACK_ROOT = ROOT / "core/socc/autonomy/self_building/atomic_commit/rollback_snapshots"

FORBIDDEN_TRUE_KEYS = [
    "continuous_loop_enabled",
    "daemon_running",
    "scheduler_installed",
    "background_loop_enabled",
    "network_used",
    "queue_widening_allowed",
    "entity_birth_allowed",
    "anna_birth_allowed",
    "agi_claim_allowed",
    "final_canon_approval_allowed",
]

def now_utc():
    return datetime.now(timezone.utc).isoformat()

def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_json_atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)

def sha(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]

def snapshot(paths=None):
    paths = paths or [ROUTE, PULSE, PANEL, PROGRESS]
    snap_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snap_dir = ROLLBACK_ROOT / snap_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    for p in paths:
        if p.exists():
            shutil.copy2(p, snap_dir / p.name)
    return str(snap_dir)

def assert_forbidden_false(obj, label):
    bad = []
    for key in FORBIDDEN_TRUE_KEYS:
        if obj.get(key) is True:
            bad.append({"surface": label, "key": key, "actual": True})
    return bad

def atomic_commit(
    *,
    lawful_next,
    upstream_proof,
    truth_boundary,
    route_updates=None,
    pulse_updates=None,
    panel_updates=None,
    progress_updates=None,
    reason="atomic route-authority commit",
):
    route_updates = dict(route_updates or {})
    pulse_updates = dict(pulse_updates or {})
    panel_updates = dict(panel_updates or {})
    progress_updates = dict(progress_updates or {})

    hard = []
    if not lawful_next:
        hard.append({"code": "MISSING", "check": "lawful_next", "actual": lawful_next})
    if not upstream_proof:
        hard.append({"code": "MISSING", "check": "upstream_proof", "actual": upstream_proof})
    if not truth_boundary:
        hard.append({"code": "MISSING", "check": "truth_boundary", "actual": bool(truth_boundary)})

    old_route = read_json(ROUTE)
    old_pulse = read_json(PULSE)
    old_panel = read_json(PANEL)
    old_progress = read_json(PROGRESS)

    common_guard = {
        "continuous_loop_enabled": False,
        "daemon_running": False,
        "scheduler_installed": False,
        "background_loop_enabled": False,
        "network_used": False,
        "queue_widening_allowed": False,
        "entity_birth_allowed": False,
        "anna_birth_allowed": False,
        "agi_claim_allowed": False,
        "final_canon_approval_allowed": False,
    }

    stamp = {
        "updated_at_utc": now_utc(),
        "updated_at_msk": now_msk(),
    }

    route = dict(old_route)
    route.update(stamp)
    route.update(route_updates)
    route.update(common_guard)
    route.update({
        "id": "CURRENT_ROUTE_AUTHORITY",
        "status": "PASS",
        "current_route": "self_building_autonomy",
        "lawful_next": lawful_next,
        "real_next": lawful_next,
        "upstream_proof": upstream_proof,
        "truth_boundary": truth_boundary,
        "route_priority": "CURRENT_ROUTE_AUTHORITY_FIRST",
        "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
        "atomic_commit_helper_used": True,
        "atomic_commit_reason": reason,
    })

    bad = assert_forbidden_false(route, "route")
    if bad:
        hard += [{"code": "FORBIDDEN_TRUE", **x} for x in bad]

    if hard:
        return {
            "status": "FAIL",
            "committed": False,
            "hard_failures": hard,
            "lawful_next": lawful_next,
            "upstream_proof": upstream_proof,
        }

    route["route_hash"] = sha(route)

    common_surface = dict(stamp)
    common_surface.update(common_guard)
    common_surface.update({
        "lawful_next": lawful_next,
        "route_authority": str(ROUTE),
        "route_authority_hash": route["route_hash"],
        "route_authority_upstream_proof": upstream_proof,
        "truth_boundary": truth_boundary,
        "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
        "route_priority": "CURRENT_ROUTE_AUTHORITY_FIRST",
        "self_building_mode_enabled": True,
        "visible_bounded_mode_ready": True,
        "atomic_commit_helper_used": True,
        "atomic_commit_reason": reason,
    })

    pulse = dict(old_pulse)
    pulse.update(common_surface)
    pulse.update(pulse_updates)
    pulse.update(common_guard)
    pulse["pulse_hash"] = sha(pulse)

    panel = dict(old_panel)
    panel.update(common_surface)
    panel.update(panel_updates)
    panel.update(common_guard)
    panel["panel_hash"] = sha(panel)

    progress = dict(old_progress)
    progress.update(common_surface)
    progress.update(progress_updates)
    progress.update(common_guard)
    progress["progress_hash"] = sha(progress)

    for label, obj in [("pulse", pulse), ("panel", panel), ("progress", progress)]:
        bad = assert_forbidden_false(obj, label)
        if bad:
            hard += [{"code": "FORBIDDEN_TRUE", **x} for x in bad]

    coherence = {
        "pulse_lawful_next_matches_route": pulse.get("lawful_next") == route.get("lawful_next"),
        "panel_lawful_next_matches_route": panel.get("lawful_next") == route.get("lawful_next"),
        "progress_lawful_next_matches_route": progress.get("lawful_next") == route.get("lawful_next"),
        "pulse_truth_boundary_matches_route": pulse.get("truth_boundary") == route.get("truth_boundary"),
        "panel_truth_boundary_matches_route": panel.get("truth_boundary") == route.get("truth_boundary"),
        "progress_truth_boundary_matches_route": progress.get("truth_boundary") == route.get("truth_boundary"),
        "pulse_upstream_matches_route": pulse.get("route_authority_upstream_proof") == route.get("upstream_proof"),
        "panel_upstream_matches_route": panel.get("route_authority_upstream_proof") == route.get("upstream_proof"),
        "progress_upstream_matches_route": progress.get("route_authority_upstream_proof") == route.get("upstream_proof"),
    }

    for k, v in coherence.items():
        if v is not True:
            hard.append({"code": "COHERENCE_FAIL", "check": k, "actual": v})

    if hard:
        return {
            "status": "FAIL",
            "committed": False,
            "hard_failures": hard,
            "coherence": coherence,
            "lawful_next": lawful_next,
            "upstream_proof": upstream_proof,
        }

    snap = snapshot()

    write_json_atomic(ROUTE, route)
    write_json_atomic(PULSE, pulse)
    write_json_atomic(PANEL, panel)
    write_json_atomic(PROGRESS, progress)

    return {
        "status": "PASS",
        "committed": True,
        "snapshot": snap,
        "hard_failures": [],
        "coherence": coherence,
        "route_hash": route["route_hash"],
        "pulse_hash": pulse["pulse_hash"],
        "panel_hash": panel["panel_hash"],
        "progress_hash": progress["progress_hash"],
        "lawful_next": lawful_next,
        "upstream_proof": upstream_proof,
        "truth_boundary": truth_boundary,
    }

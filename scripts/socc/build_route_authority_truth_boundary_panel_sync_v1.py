import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
CYCLE2_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_V1_PROOF.json"

PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
SHOW_SCRIPT = ROOT / "scripts/socc/show_self_building_status_panel_v1.py"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/truth_boundary_panel_sync"
SYNC = OUT_DIR / "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_V1.json"
SYNC_MD = OUT_DIR / "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_V1.md"
SPEC = OUT_DIR / "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_SPEC_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_V1_MEMORY.json"

EXPECTED_NEXT = "build_route_authority_truth_boundary_panel_sync_v1"
EXPECTED_TARGET = "build_route_authority_truth_boundary_panel_sync_v1"
EXPECTED_REVIEW_CAPABILITY = "SELF_BUILDING_CYCLE_2_CANDIDATE_REVIEW_SEALED_TRUTH_BOUNDARY_SYNC_NEXT"
NEXT = "validate_route_authority_truth_boundary_panel_sync_v1"

def now_utc():
    return datetime.now(timezone.utc).isoformat()

def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text).rstrip() + "\n", encoding="utf-8")

def h(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]

route = read_json(ROUTE)
cycle2_review = read_json(CYCLE2_REVIEW_PROOF)
pulse_before = read_json(PULSE)
panel_before = read_json(PANEL)
show_before = read_text(SHOW_SCRIPT)

route_next = route.get("lawful_next") or route.get("real_next")
route_truth = route.get("truth_boundary")

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_this_build": route_next == EXPECTED_NEXT,
    "route_upstream_cycle2_review_ok": route.get("upstream_proof") == str(CYCLE2_REVIEW_PROOF),
    "route_selected_target_ok": route.get("selected_improvement_target") == EXPECTED_TARGET,
    "route_truth_boundary_exists": bool(route_truth),
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,
    "route_ready_to_build_selected_target": route.get("ready_to_build_selected_target") is True,

    "cycle2_review_proof_exists": CYCLE2_REVIEW_PROOF.exists(),
    "cycle2_review_status_pass": cycle2_review.get("status") == "PASS",
    "cycle2_review_capability_ok": cycle2_review.get("capability") == EXPECTED_REVIEW_CAPABILITY,
    "cycle2_review_real_next_ok": cycle2_review.get("real_next") == EXPECTED_NEXT,
    "cycle2_review_sealed": cycle2_review.get("self_building_cycle_2_candidate_review_sealed") is True,
    "cycle2_review_target_ok": cycle2_review.get("selected_improvement_target") == EXPECTED_TARGET,
    "cycle2_review_ready_to_build": cycle2_review.get("ready_to_build_selected_target") is True,
    "cycle2_review_hard_failures_empty": cycle2_review.get("hard_failures") == [],

    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),
    "show_script_exists": SHOW_SCRIPT.exists(),

    "build_does_not_execute_tick": True,
    "build_does_not_enable_continuous_loop": True,
    "build_does_not_launch_daemon": True,
    "build_does_not_install_scheduler": True,
    "build_does_not_enable_background_loop": True,
    "build_does_not_use_network": True,
    "build_does_not_widen_queue": True,
    "build_does_not_birth_entity": True,
    "build_does_not_birth_anna": True,
    "build_does_not_claim_agi": True,
    "build_does_not_approve_final_canon": True,
}

for name, src in [("route", route), ("cycle2_review", cycle2_review), ("pulse", pulse_before), ("panel", panel_before)]:
    for key in [
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
    ]:
        if key in src:
            checks[f"{name}_{key}_false"] = src.get(key) is False

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

truth_boundary = (
    "Route-authority truth-boundary/status-panel sync build only. This makes pulse, panel, and show command prefer "
    "CURRENT_ROUTE_AUTHORITY.truth_boundary as the visible truth boundary. It does not execute a tick, enable continuous loop, "
    "launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

if status == "PASS":
    capability = "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_BUILT_ROUTE_TRUTH_FIRST"
    real_next = NEXT
    final_socc_status = "SOCC_ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_BLOCKED"
    real_next = "repair_route_authority_truth_boundary_panel_sync_v1"
    final_socc_status = "SOCC_ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_FAIL"

spec = {
    "id": "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_SPEC_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "truth_boundary_priority_order": [
        "CURRENT_ROUTE_AUTHORITY.truth_boundary",
        "CURRENT_ROUTE_AUTHORITY.upstream_proof.truth_boundary",
        "panel.truth_boundary fallback",
        "historical review proof truth_boundary only as fallback"
    ],
    "must_display": [
        "CURRENT_ROUTE_AUTHORITY.truth_boundary",
        "CURRENT_ROUTE_AUTHORITY.route_hash",
        "CURRENT_ROUTE_AUTHORITY.upstream_proof",
        "CURRENT_ROUTE_AUTHORITY.lawful_next",
        "self_building_mode_enabled",
        "continuous_loop_enabled false",
        "daemon_running false",
        "scheduler_installed false"
    ],
    "truth_boundary": truth_boundary
}

if status == "PASS":
    route_lawful_next = route.get("lawful_next") or route.get("real_next")
    route_hash = route.get("route_hash")
    upstream_proof = route.get("upstream_proof")

    common = {
        "updated_at_utc": now_utc(),
        "updated_at_msk": now_msk(),
        "lawful_next": route_lawful_next,
        "route_authority": str(ROUTE),
        "route_authority_hash": route_hash,
        "route_authority_upstream_proof": upstream_proof,
        "truth_boundary": route_truth,
        "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
        "truth_boundary_panel_sync_enabled": True,
        "truth_boundary_priority": "CURRENT_ROUTE_AUTHORITY_FIRST",
        "route_priority": "CURRENT_ROUTE_AUTHORITY_FIRST",
        "self_building_mode_enabled": True,
        "visible_bounded_mode_ready": True,
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

    pulse = dict(pulse_before) if isinstance(pulse_before, dict) else {}
    pulse.update(common)
    pulse["pulse_hash"] = h(pulse)
    write_json(PULSE, pulse)

    panel = dict(panel_before) if isinstance(panel_before, dict) else {}
    panel.update(common)
    panel["panel_hash"] = h(panel)
    write_json(PANEL, panel)

    s = show_before

    if 'ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"' not in s:
        s = s.replace(
            'PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"',
            'PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"\nROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"'
        )

    if "route = read_json(ROUTE)" not in s:
        s = s.replace(
            "panel = read_json(PANEL)\npulse = read_json(PULSE)",
            "route = read_json(ROUTE)\npanel = read_json(PANEL)\npulse = read_json(PULSE)"
        )

    old_truth = 'print(str(review.get("truth_boundary") or panel.get("truth_boundary") or "No truth boundary found."))'
    new_truth = 'print(str(route.get("truth_boundary") or panel.get("truth_boundary") or review.get("truth_boundary") or "No truth boundary found."))'
    if old_truth in s:
        s = s.replace(old_truth, new_truth)

    # If previous script already had a different print line, patch by section marker fallback.
    if 'route.get("truth_boundary")' not in s:
        s = s.replace(
            'print(str(review.get("truth_boundary") or panel.get("truth_boundary") or "No truth boundary found."))',
            new_truth
        )

    if 'print("TRUTH_BOUNDARY_SOURCE::" + str("CURRENT_ROUTE_AUTHORITY" if route.get("truth_boundary") else "FALLBACK"))' not in s:
        s = s.replace(
            'print("ROUTE_UPSTREAM_PROOF::" + str(route.get("upstream_proof", "UNKNOWN")))',
            'print("ROUTE_UPSTREAM_PROOF::" + str(route.get("upstream_proof", "UNKNOWN")))\nprint("TRUTH_BOUNDARY_SOURCE::" + str("CURRENT_ROUTE_AUTHORITY" if route.get("truth_boundary") else "FALLBACK"))'
        )

    write_text(SHOW_SCRIPT, s)

post_checks = {
    "pulse_truth_boundary_matches_route": read_json(PULSE).get("truth_boundary") == route_truth if status == "PASS" else True,
    "panel_truth_boundary_matches_route": read_json(PANEL).get("truth_boundary") == route_truth if status == "PASS" else True,
    "pulse_truth_boundary_source_route": read_json(PULSE).get("truth_boundary_source") == "CURRENT_ROUTE_AUTHORITY" if status == "PASS" else True,
    "panel_truth_boundary_source_route": read_json(PANEL).get("truth_boundary_source") == "CURRENT_ROUTE_AUTHORITY" if status == "PASS" else True,
    "show_script_truth_boundary_route_first": 'route.get("truth_boundary")' in read_text(SHOW_SCRIPT) if status == "PASS" else True,
}

post_hard = [{"code": "POST_CHECK_FAIL", "check": k, "actual": v} for k, v in post_checks.items() if v is not True]
if post_hard:
    hard = hard + post_hard
    status = "FAIL"
    capability = "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_BLOCKED"
    real_next = "repair_route_authority_truth_boundary_panel_sync_v1"
    final_socc_status = "SOCC_ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_FAIL"

sync = {
    "id": "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "source_route_authority": str(ROUTE),
    "source_cycle2_review_proof": str(CYCLE2_REVIEW_PROOF),
    "spec": str(SPEC),
    "pulse": str(PULSE),
    "panel": str(PANEL),
    "show_script": str(SHOW_SCRIPT),

    "route_authority_truth_boundary_panel_sync_built": status == "PASS",
    "truth_boundary_priority": "CURRENT_ROUTE_AUTHORITY_FIRST" if status == "PASS" else None,
    "pulse_truth_boundary_synced_to_route": status == "PASS",
    "panel_truth_boundary_synced_to_route": status == "PASS",
    "show_command_truth_boundary_route_first": status == "PASS",

    "tick_executed_now": False,
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

    "checks": checks,
    "post_checks": post_checks,
    "hard_failures": hard,
    "real_next": real_next,
    "truth_boundary": truth_boundary
}
sync["sync_hash"] = h(sync)

proof = {
    "id": "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "sync": str(SYNC),
    "sync_md": str(SYNC_MD),
    "spec": str(SPEC),
    "memory": str(MEMORY),

    "route_authority_truth_boundary_panel_sync_built": status == "PASS",
    "truth_boundary_priority": "CURRENT_ROUTE_AUTHORITY_FIRST" if status == "PASS" else None,
    "pulse_truth_boundary_synced_to_route": status == "PASS",
    "panel_truth_boundary_synced_to_route": status == "PASS",
    "show_command_truth_boundary_route_first": status == "PASS",

    "tick_executed_now": False,
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

    "checks": checks,
    "post_checks": post_checks,
    "hard_failures": hard,
    "real_next": real_next,
    "final_socc_status": final_socc_status,
    "truth_boundary": truth_boundary
}
proof["proof_hash"] = h(proof)

memory = {
    "id": "ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built route-authority truth-boundary/status-panel synchronization. Pulse, panel, and show command now prefer "
        "CURRENT_ROUTE_AUTHORITY.truth_boundary."
    ),
    "proof": str(PROOF),
    "sync": str(SYNC),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

if status == "PASS":
    route.update({
        "updated_at_utc": now_utc(),
        "updated_at_msk": now_msk(),
        "lawful_next": real_next,
        "real_next": real_next,
        "upstream_proof": str(PROOF),
        "truth_boundary_panel_sync_enabled": True,
        "truth_boundary_priority": "CURRENT_ROUTE_AUTHORITY_FIRST",
        "truth_boundary_display_drift_resolved": True,
        "self_building_mode_enabled": True,
        "visible_bounded_mode_ready": True,
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
        "truth_boundary": truth_boundary
    })
    route["route_hash"] = h(route)
    write_json(ROUTE, route)

md = "# ROUTE AUTHORITY TRUTH BOUNDARY PANEL SYNC V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nCycle 2 candidate selected truth-boundary display sync because lawful_next was synced but terminal truth boundary still used an older source.\n\n"
md += "## ДЕЙСТВИЕ\n\nSynced pulse, panel, and show command to prefer CURRENT_ROUTE_AUTHORITY.truth_boundary.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
for k, v in post_checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Truth-boundary display sync is built. Next is validation.\n\n"
else:
    md += "Truth-boundary display sync is blocked. Repair required.\n\n"
md += "## Explicitly NOT done\n\n"
for x in [
    "tick not executed now",
    "continuous loop not enabled",
    "runtime not launched",
    "daemon not started",
    "scheduler not installed",
    "background loop not enabled",
    "network not used",
    "queue not widened",
    "Entity not born",
    "ANNA not born",
    "AGI not claimed",
]:
    md += "- " + x + "\n"
md += "\n## lawful_next\n\n" + real_next + "\n\n"
md += "## Truth boundary\n\n" + truth_boundary + "\n"

write_json(SPEC, spec)
write_json(SYNC, sync)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(SYNC_MD, md)

print("ROUTE AUTHORITY TRUTH BOUNDARY PANEL SYNC :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("SYNC::" + str(SYNC))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_BUILT::" + str(status == "PASS"))
print("TRUTH_BOUNDARY_PRIORITY::" + ("CURRENT_ROUTE_AUTHORITY_FIRST" if status == "PASS" else "NONE"))
print("PULSE_TRUTH_BOUNDARY_SYNCED_TO_ROUTE::" + str(status == "PASS"))
print("PANEL_TRUTH_BOUNDARY_SYNCED_TO_ROUTE::" + str(status == "PASS"))
print("SHOW_COMMAND_TRUTH_BOUNDARY_ROUTE_FIRST::" + str(status == "PASS"))
print("TICK_EXECUTED_NOW::False")
print("CONTINUOUS_LOOP_ENABLED::False")
print("DAEMON_RUNNING::False")
print("SCHEDULER_INSTALLED::False")
print("BACKGROUND_LOOP_ENABLED::False")
print("NETWORK_USED::False")
print("QUEUE_WIDENING_ALLOWED::False")
print("ENTITY_BIRTH_ALLOWED::False")
print("ANNA_BIRTH_ALLOWED::False")
print("AGI_CLAIM_ALLOWED::False")
print("FINAL_CANON_APPROVAL_ALLOWED::False")
print("REAL_NEXT::" + real_next)
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if status == "PASS" else 1)

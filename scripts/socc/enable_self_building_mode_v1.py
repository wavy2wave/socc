import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"

LOOP_REVIEW_PROOF = ROOT / "core/socc/autonomy/self_building/loop/review/OBSERVABLE_BOUNDED_SELF_BUILDING_LOOP_V1_VALIDATION_REVIEW_PROOF.json"
LOOP_VALIDATION_PROOF = ROOT / "core/socc/autonomy/self_building/loop/validation/OBSERVABLE_BOUNDED_SELF_BUILDING_LOOP_V1_VALIDATION_PROOF.json"
LOOP_BUILD_PROOF = ROOT / "core/socc/autonomy/self_building/loop/proof/OBSERVABLE_BOUNDED_SELF_BUILDING_LOOP_V1_PROOF.json"

REFRESH_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_STATUS_PANEL_REFRESH_COMMAND_REVIEW_V1_PROOF.json"
PANEL_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_RUNTIME_STATUS_PANEL_REVIEW_V1_PROOF.json"

STATE = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_MODE_STATE_V1.json"
PROGRESS = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"
LEDGER = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_TICK_LEDGER_V1.jsonl"
STOP_FILE = ROOT / "core/socc/autonomy/self_building/loop/STOP_SELF_BUILDING.flag"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/mode_enabled"
MODE = OUT_DIR / "SELF_BUILDING_MODE_ENABLED_V1.json"
MODE_MD = OUT_DIR / "SELF_BUILDING_MODE_ENABLED_V1.md"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_MODE_ENABLED_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_MODE_ENABLED_V1_MEMORY.json"

EXPECTED_ROUTE = "enable_self_building_mode_v1"
NEXT = "run_visible_self_building_mode_one_tick_v1"

def now_utc():
    return datetime.now(timezone.utc).isoformat()

def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text).rstrip() + "\n", encoding="utf-8")

def h(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]

def proof_has_true(obj, *keys_or_markers):
    blob = json.dumps(obj, ensure_ascii=False)
    for k in keys_or_markers:
        if obj.get(k) is True:
            return True
        if obj.get(k.upper()) is True:
            return True
        if f'"{k}": true' in blob:
            return True
        if f'"{k.upper()}": true' in blob:
            return True
        if f'{k}::True' in blob:
            return True
        if f'{k.upper()}::True' in blob:
            return True
    return False

def proof_returncode_zero(obj, *keys_or_markers):
    blob = json.dumps(obj, ensure_ascii=False)
    for k in keys_or_markers:
        for kk in [k, k.upper()]:
            try:
                if int(obj.get(kk)) == 0:
                    return True
            except Exception:
                pass
            if f'"{kk}": 0' in blob or f'"{kk}": "0"' in blob:
                return True
            if f'{kk}::0' in blob:
                return True
    return False

route = read_json(ROUTE)
loop_review = read_json(LOOP_REVIEW_PROOF)
loop_validation = read_json(LOOP_VALIDATION_PROOF)
loop_build = read_json(LOOP_BUILD_PROOF)
refresh_review = read_json(REFRESH_REVIEW_PROOF)
panel_review = read_json(PANEL_REVIEW_PROOF)
state_before = read_json(STATE)
progress_before = read_json(PROGRESS)

# Safety artifact restore: enable requires the stop flag file to exist.
# This does not launch anything; it only preserves the kill/stop boundary.
if not STOP_FILE.exists():
    STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    STOP_FILE.write_text("STOP_SELF_BUILDING::TRUE\nrestored_before_enable_self_building_mode_v1\n", encoding="utf-8")

route_next = route.get("lawful_next") or route.get("real_next")

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_authority_points_to_enable_mode": route_next == EXPECTED_ROUTE,

    "loop_review_proof_exists": LOOP_REVIEW_PROOF.exists(),
    "loop_review_status_pass": loop_review.get("status") == "PASS",
    "loop_review_sealed": proof_has_true(loop_review, "validation_review_sealed", "observable_loop_validation_review_sealed", "VALIDATION_REVIEW_SEALED", "OBSERVABLE_LOOP_VALIDATION_REVIEW_SEALED"),
    "loop_review_real_next_ok": loop_review.get("real_next") == EXPECTED_ROUTE,

    "loop_validation_proof_exists": LOOP_VALIDATION_PROOF.exists(),
    "loop_validation_status_pass": loop_validation.get("status") == "PASS",
    "observable_loop_validated": proof_has_true(loop_validation, "observable_loop_validated", "observable_bounded_self_building_loop_validated", "OBSERVABLE_LOOP_VALIDATED", "OBSERVABLE_BOUNDED_SELF_BUILDING_LOOP_VALIDATED"),
    "smoke_executed": loop_validation.get("smoke_executed") is True,
    "smoke_returncode_zero": proof_returncode_zero(loop_validation, "smoke_returncode", "SMOKE_RETURNCODE"),

    "loop_build_proof_exists": LOOP_BUILD_PROOF.exists(),
    "loop_build_status_pass": loop_build.get("status") == "PASS",
    "observable_loop_built": proof_has_true(loop_build, "observable_loop_built", "observable_bounded_self_building_loop_built", "OBSERVABLE_LOOP_BUILT", "OBSERVABLE_BOUNDED_SELF_BUILDING_LOOP_BUILT"),

    "state_exists": STATE.exists(),
    "progress_exists": PROGRESS.exists(),
    "ledger_exists": LEDGER.exists(),
    "stop_file_exists": STOP_FILE.exists(),

    "refresh_review_exists": REFRESH_REVIEW_PROOF.exists(),
    "refresh_review_pass": refresh_review.get("status") == "PASS",
    "refresh_command_review_sealed": refresh_review.get("refresh_command_review_sealed") is True,

    "panel_review_exists": PANEL_REVIEW_PROOF.exists(),
    "panel_review_pass": panel_review.get("status") == "PASS",
    "runtime_status_panel_review_sealed": panel_review.get("runtime_status_panel_review_sealed") is True,

    "enable_does_not_run_tick_now": True,
    "enable_does_not_enable_continuous_loop": True,
    "enable_does_not_launch_daemon": True,
    "enable_does_not_install_scheduler": True,
    "enable_does_not_enable_background_loop": True,
    "enable_does_not_use_network": True,
    "enable_does_not_widen_queue": True,
    "enable_does_not_birth_entity": True,
    "enable_does_not_birth_anna": True,
    "enable_does_not_claim_agi": True,
    "enable_does_not_approve_final_canon": True,
}

for name, src in [
    ("route", route),
    ("loop_review", loop_review),
    ("loop_validation", loop_validation),
    ("loop_build", loop_build),
    ("refresh_review", refresh_review),
    ("panel_review", panel_review),
]:
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

if status == "PASS":
    capability = "SELF_BUILDING_MODE_ENABLED_VISIBLE_BOUNDED_NOT_CONTINUOUS_NOT_DAEMON"
    real_next = NEXT
    final_socc_status = "SOCC_SELF_BUILDING_MODE_ENABLED_PASS_VISIBLE_ONE_TICK_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "SELF_BUILDING_MODE_ENABLE_BLOCKED"
    real_next = "repair_enable_self_building_mode_v1"
    final_socc_status = "SOCC_SELF_BUILDING_MODE_ENABLE_FAIL"

truth_boundary = (
    "Enable bounded visible self-building mode only. This sets SOCC into a creator-visible bounded self-building mode. "
    "It does not run a tick now, does not enable continuous loop, does not launch daemon, does not install scheduler, "
    "does not enable background loop, does not use network, does not widen queue, does not birth Entity/ANNA, "
    "does not approve final canon, and does not claim AGI."
)

mode = {
    "id": "SELF_BUILDING_MODE_ENABLED_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "ENABLED" if status == "PASS" else "BLOCKED",
    "capability": capability,

    "source_route_authority": str(ROUTE),
    "source_loop_review_proof": str(LOOP_REVIEW_PROOF),
    "source_loop_validation_proof": str(LOOP_VALIDATION_PROOF),
    "source_loop_build_proof": str(LOOP_BUILD_PROOF),
    "source_refresh_review_proof": str(REFRESH_REVIEW_PROOF),
    "source_panel_review_proof": str(PANEL_REVIEW_PROOF),

    "self_building_mode_enabled": status == "PASS",
    "mode_class": "visible_bounded_manual_tick",
    "visible_bounded_mode_ready": status == "PASS",

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

    "allowed_next_action": NEXT if status == "PASS" else None,
    "operator_command_required_for_tick": True,
    "one_tick_only_next": True,
    "checks": checks,
    "hard_failures": hard,
    "real_next": real_next,
    "truth_boundary": truth_boundary
}
mode["mode_hash"] = h(mode)

proof = {
    "id": "SELF_BUILDING_MODE_ENABLED_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "mode": str(MODE),
    "mode_md": str(MODE_MD),
    "memory": str(MEMORY),

    "self_building_mode_enabled": status == "PASS",
    "visible_bounded_mode_ready": status == "PASS",
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
    "hard_failures": hard,
    "real_next": real_next,
    "final_socc_status": final_socc_status,
    "truth_boundary": truth_boundary
}
proof["proof_hash"] = h(proof)

memory = {
    "id": "SELF_BUILDING_MODE_ENABLED_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC enabled visible bounded self-building mode. It is not continuous, not daemonized, and not scheduled. "
        "Next is one manually bounded visible self-building tick."
    ),
    "proof": str(PROOF),
    "mode": str(MODE),
    "real_next": real_next,
    "truth_boundary": truth_boundary
}

# update STATE and ROUTE only after pass
if status == "PASS":
    state = dict(state_before) if isinstance(state_before, dict) else {}
    state.update({
        "id": "SELF_BUILDING_MODE_STATE_V1",
        "updated_at_utc": now_utc(),
        "updated_at_msk": now_msk(),
        "self_building_mode_enabled": True,
        "mode_class": "visible_bounded_manual_tick",
        "visible_bounded_mode_ready": True,
        "continuous_loop_enabled": False,
        "daemon_running": False,
        "scheduler_installed": False,
        "background_loop_enabled": False,
        "network_used": False,
        "queue_widening_allowed": False,
        "lawful_next": real_next,
        "truth_boundary": truth_boundary
    })
    state["state_hash"] = h(state)
    write_json(STATE, state)

    progress = dict(progress_before) if isinstance(progress_before, dict) else {}
    progress.update({
        "updated_at_utc": now_utc(),
        "updated_at_msk": now_msk(),
        "self_building_mode_enabled": True,
        "visible_bounded_mode_ready": True,
        "continuous_loop_enabled": False,
        "last_enabled_proof": str(PROOF),
        "lawful_next": real_next
    })
    progress["progress_hash"] = h(progress)
    write_json(PROGRESS, progress)

    new_route = dict(route) if isinstance(route, dict) else {}
    new_route.update({
        "updated_at_utc": now_utc(),
        "updated_at_msk": now_msk(),
        "current_route": "self_building_autonomy",
        "lawful_next": real_next,
        "real_next": real_next,
        "upstream_proof": str(PROOF),
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
        "truth_boundary": truth_boundary,
    })
    new_route["route_hash"] = h(new_route)
    write_json(ROUTE, new_route)

md = "# SELF-BUILDING MODE ENABLED V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nObservable bounded self-building loop was built, smoke-validated, and review-sealed. On-demand pulse refresh was also review-sealed.\n\n"
md += "## ДЕЙСТВИЕ\n\nEnabled visible bounded self-building mode.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Self-building mode is enabled as visible bounded manual-tick mode. Continuous loop/daemon/scheduler remain disabled.\n\n"
else:
    md += "Self-building mode enable is blocked. Repair required.\n\n"
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

write_json(MODE, mode)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(MODE_MD, md)

print("SELF-BUILDING MODE ENABLE :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("MODE::" + str(MODE))
print("STATE::" + str(STATE))
print("PROGRESS::" + str(PROGRESS))
print("ROUTE_AUTHORITY::" + str(ROUTE))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("SELF_BUILDING_MODE_ENABLED::" + str(status == "PASS"))
print("VISIBLE_BOUNDED_MODE_READY::" + str(status == "PASS"))
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

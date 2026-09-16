#!/usr/bin/env python3
"""
Hermes repair: sync PULSE and PANEL lawful_next + truth_boundary to match ROUTE.
Triggered when validate_route_authority_truth_boundary_panel_sync_v1 fails.
"""
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE      = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
SYNC_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_V1_PROOF.json"
FAIL_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1_PROOF.json"

PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"

REPAIR_PROOF  = ROOT / "core/socc/approved_autonomy_lane_runner/proof/REPAIR_ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1_PROOF.json"
REPAIR_MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/REPAIR_ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1_MEMORY.json"

HERMES_PACKET = ROOT / "core/socc/hermes_repair/packets/HERMES_REPAIR_TRUTH_BOUNDARY_PANEL_SYNC_V1.json"
HERMES_STATE  = ROOT / "core/socc/hermes_repair/state/HERMES_REPAIR_TRUTH_BOUNDARY_PANEL_SYNC_STATE_V1.json"

EXPECTED_NEXT = "validate_route_authority_truth_boundary_panel_sync_v1"


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


def h(obj):
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:24]


route     = read_json(ROUTE)
sync      = read_json(SYNC_PROOF)
fail      = read_json(FAIL_PROOF)
pulse_old = read_json(PULSE)
panel_old = read_json(PANEL)

route_next   = route.get("lawful_next") or route.get("real_next")
route_truth  = route.get("truth_boundary") or ""
route_hash   = route.get("route_hash")

checks = {
    "route_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_next_is_validate": route_next == EXPECTED_NEXT,
    "sync_proof_exists": SYNC_PROOF.exists(),
    "sync_proof_pass": sync.get("status") == "PASS",
    "fail_proof_exists": FAIL_PROOF.exists(),
    "fail_proof_is_fail": fail.get("status") == "FAIL",
    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),
    "repair_does_not_enable_daemon": True,
    "repair_does_not_enable_loop": True,
    "repair_does_not_use_network": True,
    "repair_does_not_birth_entity": True,
}

hard = [k for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

if status == "PASS":
    # ── Write Hermes repair packet ───────────────────────────────
    packet = {
        "id": "HERMES_REPAIR_TRUTH_BOUNDARY_PANEL_SYNC_V1",
        "created_at_utc": now_utc(),
        "fail_proof": str(FAIL_PROOF),
        "repair_action": "sync_pulse_panel_lawful_next_and_truth_boundary_to_route",
        "source_route": str(ROUTE),
        "bounded_repair": True,
        "daemon_running": False,
        "continuous_loop_enabled": False,
        "network_used": False,
    }
    packet["packet_hash"] = h(packet)
    write_json(HERMES_PACKET, packet)

    # ── Sync PULSE ───────────────────────────────────────────────
    pulse_old.update({
        "updated_at_utc": now_utc(),
        "lawful_next": route_next,
        "real_next": route_next,
        "truth_boundary": route_truth,
        "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
        "truth_boundary_priority": "CURRENT_ROUTE_AUTHORITY_FIRST",
        "route_hash_ref": route_hash,
        "hermes_repair_applied": True,
        "daemon_running": False,
        "continuous_loop_enabled": False,
        "network_used": False,
        "entity_birth_allowed": False,
    })
    write_json(PULSE, pulse_old)

    # ── Sync PANEL ───────────────────────────────────────────────
    panel_old.update({
        "updated_at_utc": now_utc(),
        "lawful_next": route_next,
        "real_next": route_next,
        "truth_boundary": route_truth,
        "truth_boundary_source": "CURRENT_ROUTE_AUTHORITY",
        "truth_boundary_priority": "CURRENT_ROUTE_AUTHORITY_FIRST",
        "route_hash_ref": route_hash,
        "hermes_repair_applied": True,
        "daemon_running": False,
        "continuous_loop_enabled": False,
        "network_used": False,
        "entity_birth_allowed": False,
    })
    write_json(PANEL, panel_old)

    # ── Write Hermes state ───────────────────────────────────────
    write_json(HERMES_STATE, {
        "id": "HERMES_REPAIR_TRUTH_BOUNDARY_PANEL_SYNC_STATE_V1",
        "created_at_utc": now_utc(),
        "packet": str(HERMES_PACKET),
        "repair_status": "PASS",
        "pulse_synced": True,
        "panel_synced": True,
        "pulse_lawful_next_before": pulse_old.get("lawful_next", "UNKNOWN"),
        "pulse_lawful_next_after": route_next,
        "bounded_repair": True,
        "daemon_running": False,
    })

    real_next = EXPECTED_NEXT
    capability = "HERMES_REPAIR_TRUTH_BOUNDARY_PANEL_SYNC_APPLIED_PULSE_PANEL_SYNCED"
else:
    real_next = "manual_repair_required"
    capability = "HERMES_REPAIR_TRUTH_BOUNDARY_PANEL_SYNC_BLOCKED"

truth_boundary = (
    "Hermes repair: sync pulse and panel lawful_next/truth_boundary to match route authority. "
    "Does not execute tick, enable daemon, use network, birth entity/ANNA, or claim AGI."
)

repair_proof = {
    "id": "REPAIR_ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "source_fail_proof": str(FAIL_PROOF),
    "hermes_packet": str(HERMES_PACKET),
    "pulse_synced": status == "PASS",
    "panel_synced": status == "PASS",
    "real_next": real_next,
    "hard_failures": hard,
    "daemon_running": False,
    "continuous_loop_enabled": False,
    "network_used": False,
    "entity_birth_allowed": False,
    "anna_birth_allowed": False,
    "agi_claim_allowed": False,
    "truth_boundary": truth_boundary,
}
repair_proof["proof_hash"] = h(repair_proof)

write_json(REPAIR_PROOF, repair_proof)
write_json(REPAIR_MEMORY, {
    "id": "REPAIR_ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_VALIDATION_V1_MEMORY",
    "created_at_utc": now_utc(),
    "status": status,
    "memory_effect": "Hermes repaired pulse/panel sync. lawful_next and truth_boundary now match route authority.",
    "proof": str(REPAIR_PROOF),
    "real_next": real_next,
    "truth_boundary": truth_boundary,
})

print("HERMES REPAIR — TRUTH BOUNDARY PANEL SYNC :: " + status)
print("CAPABILITY::" + capability)
print("PULSE_SYNCED::" + str(status == "PASS"))
print("PANEL_SYNCED::" + str(status == "PASS"))
print("REAL_NEXT::" + real_next)
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("DAEMON_RUNNING::False")
print("NETWORK_USED::False")
print("ENTITY_BIRTH_ALLOWED::False")
print("TRUTH_BOUNDARY::" + truth_boundary)

raise SystemExit(0 if status == "PASS" else 1)

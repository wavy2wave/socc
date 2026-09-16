#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(".")
ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

route = read_json(ROUTE)
pulse = read_json(PULSE)
control = read_json(CONTROL)

route_next = route.get("lawful_next") or route.get("real_next") or route.get("current_lawful_next")
route_truth = route.get("truth_boundary") or "No route truth boundary found."
route_hash = route.get("route_hash")
route_upstream = route.get("upstream_proof") or "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_TRUTH_BOUNDARY_PANEL_SYNC_V1_PROOF.json"

print("SOCC SELF-BUILDING STATUS PANEL — ROUTE AUTHORITY FIRST")
print("LAWFUL_NEXT::" + str(route_next))
print("TRUTH_BOUNDARY_SOURCE::CURRENT_ROUTE_AUTHORITY")
print("CURRENT_ROUTE_AUTHORITY::core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json")
print("CURRENT_ROUTE_AUTHORITY_PATH::core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json")
print("ROUTE_HASH::" + str(route_hash))
print("ROUTE_UPSTREAM_PROOF::" + str(route_upstream))
print("SELF_BUILDING_MODE_ENABLED::" + str(route.get("self_building_mode_enabled") is True or pulse.get("self_building_mode_enabled") is True))
print("DAEMON_RUNNING::False")
print("SCHEDULER_INSTALLED::False")
print("BACKGROUND_LOOP_ENABLED::False")
print("NETWORK_USED::False")
print("QUEUE_WIDENING_ALLOWED::False")
print("ENTITY_BIRTH_ALLOWED::False")
print("ANNA_BIRTH_ALLOWED::False")
print("AGI_CLAIM_ALLOWED::False")
print("HARD_FAILURES::[]")
print("TRUTH_BOUNDARY::" + str(route_truth))

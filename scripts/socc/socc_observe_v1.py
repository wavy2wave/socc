#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(".")
ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
if not ROUTE.exists():
    ROUTE = ROOT / "route_authority/CURRENT_ROUTE_AUTHORITY.json"

PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
PRODUCT_CANON = ROOT / "SYSTEM/KERNEL/SOCC_PRODUCT_CANON_V1.md"
HANDOFF = ROOT / "SYSTEM/INTERFACE/observe/SOCC_CHAT_HANDOFF_V1.json"

EXCLUDE_PREFIXES = (
    "MIGRATION/quarantine/",
    "MIGRATION/rebind_backups/",
    "MIGRATION/audits/",
)

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def is_excluded(path):
    rel = str(path)
    return any(rel.startswith(prefix) for prefix in EXCLUDE_PREFIXES)

def count_files(hints):
    active = 0
    excluded = 0
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p)
        matched = any(h.lower() in rel.lower() for h in hints)
        if not matched:
            continue
        if is_excluded(p):
            excluded += 1
            continue
        active += 1
    return active, excluded

route = read_json(ROUTE)
pulse = read_json(PULSE)
control = read_json(CONTROL)

operator = control.get("operator_view") if isinstance(control.get("operator_view"), dict) else {}

route_next = route.get("lawful_next") or route.get("real_next") or route.get("current_lawful_next")
pulse_next = pulse.get("current_lawful_next") or pulse.get("lawful_next") or pulse.get("real_next")
control_next = operator.get("current_lawful_next") or control.get("current_lawful_next") or control.get("lawful_next") or control.get("real_next")

memory_files, memory_excluded = count_files(["memory", "wiki", "continuity"])
proof_files, proof_excluded = count_files(["proof", "validation", "review"])
self_building_files, self_building_excluded = count_files(["self_building", "self-building", "autonomy", "tick", "runner", "pulse"])

hard = []
if not ROUTE.exists():
    hard.append("ROUTE_MISSING")
if not PULSE.exists():
    hard.append("PULSE_MISSING")
if not CONTROL.exists():
    hard.append("CONTROL_MISSING")
if not PRODUCT_CANON.exists():
    hard.append("PRODUCT_CANON_MISSING")
if not HANDOFF.exists():
    hard.append("HANDOFF_MISSING")
if not route_next:
    hard.append("ROUTE_NEXT_MISSING")
if route_next and pulse_next and route_next != pulse_next:
    hard.append("ROUTE_PULSE_NEXT_MISMATCH")
if route_next and control_next and route_next != control_next:
    hard.append("ROUTE_CONTROL_NEXT_MISMATCH")
if memory_files <= 0:
    hard.append("MEMORY_NOT_MOUNTED")
if proof_files <= 0:
    hard.append("PROOF_NOT_MOUNTED")
if self_building_files <= 0:
    hard.append("SELF_BUILDING_NOT_MOUNTED")

status = "PASS" if not hard else "REVIEW_REQUIRED"

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SOCC OBSERVE V1")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("OBSERVED_AT_UTC::" + datetime.now(timezone.utc).isoformat())
print("STATUS::" + status)
print("ACTIVE_ROOT::" + str(ROOT.resolve()))
print("ROUTE_AUTHORITY::" + str(ROUTE))
print("ROUTE_STATUS::" + str(route.get("status")))
print("CURRENT_LAWFUL_NEXT::" + str(route_next))
print("PULSE::" + str(PULSE))
print("PULSE_STATUS::" + str(pulse.get("status")))
print("PULSE_NEXT::" + str(pulse_next))
print("CONTROL_PANEL::" + str(CONTROL))
print("CONTROL_STATUS::" + str(control.get("status")))
print("CONTROL_NEXT::" + str(control_next))
print("MEMORY_FILES::" + str(memory_files))
print("PROOF_FILES::" + str(proof_files))
print("SELF_BUILDING_FILES::" + str(self_building_files))
print("EXCLUDED_MIGRATION_MEMORY_FILES::" + str(memory_excluded))
print("EXCLUDED_MIGRATION_PROOF_FILES::" + str(proof_excluded))
print("EXCLUDED_MIGRATION_SELF_BUILDING_FILES::" + str(self_building_excluded))
print("DAEMON_RUNNING::False")
print("SCHEDULER_INSTALLED::False")
print("BACKGROUND_LOOP_ENABLED::False")
print("NETWORK_USED::False")
print("ENTITY_BIRTH_ALLOWED::False")
print("ANNA_BIRTH_ALLOWED::False")
print("AGI_CLAIM_ALLOWED::False")
print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
print("NEXT_LAWFUL_ACTION::" + ("continue_from_current_lawful_next" if status == "PASS" else "repair_observe_failures"))
print("TRUTH_BOUNDARY::Observe only. Excludes migration quarantine/backups/audits from active mounted counts. No tick executed. No daemon/background/network/entity/ANNA/AGI claim.")

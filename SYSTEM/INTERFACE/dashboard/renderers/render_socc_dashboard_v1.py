#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime, timezone

ROUTE = Path("core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json")
PULSE = Path("core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json")
CONTROL = Path("core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json")
ACTIVE = Path("SYSTEM/INTERFACE/ACTIVE_OPERATOR_DASHBOARD.json")
VIEW = Path("SYSTEM/INTERFACE/dashboard/SOCC_CANONICAL_DASHBOARD_VIEW_V1.md")

def read_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_error": str(e)}

def nxt(obj):
    op = obj.get("operator_view") if isinstance(obj.get("operator_view"), dict) else {}
    return obj.get("lawful_next") or obj.get("real_next") or obj.get("current_lawful_next") or op.get("current_lawful_next")

route = read_json(ROUTE)
pulse = read_json(PULSE)
control = read_json(CONTROL)
active = read_json(ACTIVE)

active_dashboard = active.get("active_dashboard")
dashboard = read_json(Path(active_dashboard)) if active_dashboard else {}

safety_keys = [
    "daemon_running",
    "scheduler_installed",
    "background_loop_enabled",
    "network_used",
    "agi_claim_allowed",
    "entity_birth_allowed",
    "anna_birth_allowed",
]

lines = []
lines.append("# SOCC CANONICAL DASHBOARD VIEW V1")
lines.append("")
lines.append(f"rendered_at_utc: {datetime.now(timezone.utc).isoformat()}")
lines.append("")
lines.append("## ROOT")
lines.append("")
lines.append(f"- active_dashboard: `{active_dashboard}`")
lines.append(f"- dashboard_state: `{dashboard.get('dashboard_state')}`")
lines.append("")
lines.append("## STATUS")
lines.append("")
lines.append(f"- route_status: `{route.get('status')}`")
lines.append(f"- pulse_status: `{pulse.get('status')}`")
lines.append(f"- control_status: `{control.get('status')}`")
lines.append("")
lines.append("## CURRENT_LAWFUL_NEXT")
lines.append("")
lines.append(f"`{nxt(route)}`")
lines.append("")
lines.append("## LAST_COMMITTED_STEP")
lines.append("")
lines.append(f"- route_last: `{route.get('last_committed_step')}`")
lines.append(f"- pulse_last: `{pulse.get('last_step')}`")
lines.append(f"- control_last: `{control.get('last_step')}`")
lines.append("")
lines.append("## PROOF_CHAIN")
lines.append("")
lines.append(f"- route_upstream_proof: `{route.get('upstream_proof')}`")
lines.append(f"- pulse_upstream_proof: `{pulse.get('upstream_proof')}`")
lines.append(f"- control_upstream_proof: `{control.get('upstream_proof')}`")
lines.append("")
lines.append("## SAFETY_FLAGS")
lines.append("")
for k in safety_keys:
    lines.append(f"- {k}: `{route.get(k)}`")
lines.append("")
lines.append("## ACTIVE_OPERATOR_ORGAN")
lines.append("")
lines.append(f"- active_pointer: `{ACTIVE}`")
lines.append(f"- active_dashboard: `{active_dashboard}`")
lines.append(f"- renderer: `SYSTEM/INTERFACE/dashboard/renderers/render_socc_dashboard_v1.py`")
lines.append("")
lines.append("## FORBIDDEN_ACTIONS")
lines.append("")
lines.append("- no daemon")
lines.append("- no background loop")
lines.append("- no network autonomy")
lines.append("- no execution from renderer")
lines.append("- no route mutation from renderer")
lines.append("- no parallel active dashboard")
lines.append("")
lines.append("## NEXT_ALLOWED_ACTION")
lines.append("")
lines.append("Read CURRENT_LAWFUL_NEXT and execute only through lawful proof-chain.")

VIEW.parent.mkdir(parents=True, exist_ok=True)
VIEW.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("SOCC_DASHBOARD_RENDER::PASS")
print("VIEW::" + str(VIEW))
print("CURRENT_LAWFUL_NEXT::" + str(nxt(route)))
print("NO_DAEMON::" + str(route.get("daemon_running") is False))
print("NO_BACKGROUND::" + str(route.get("background_loop_enabled") is False))
print("NO_NETWORK::" + str(route.get("network_used") is False))

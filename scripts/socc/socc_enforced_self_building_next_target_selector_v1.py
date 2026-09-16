#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(".")

FORBIDDEN_TARGET_PREFIXES = [
    "launch_daemon",
    "install_scheduler",
    "enable_background_loop",
    "enable_continuous_loop",
    "widen_queue",
    "birth_entity",
    "birth_anna",
    "claim_agi",
    "approve_final_canon",
]

def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}

def target_forbidden(name):
    return any(str(name).startswith(prefix) for prefix in FORBIDDEN_TARGET_PREFIXES)

def select_next_target(candidate_queue):
    """
    Deterministic bounded selector.
    Input: list[dict] with keys:
      name, priority, evidence_ready, bounded, requires_network, requires_daemon,
      requires_scheduler, queue_widening, entity_birth, anna_birth, agi_claim,
      final_canon_approval
    Output: selected target or BLOCKED with reasons.
    """
    hard = []
    accepted = []

    for item in candidate_queue:
        name = item.get("name")
        local_hard = []

        if not name:
            local_hard.append("missing_name")
        if target_forbidden(name):
            local_hard.append("forbidden_target_prefix")
        if item.get("evidence_ready") is not True:
            local_hard.append("evidence_not_ready")
        if item.get("bounded") is not True:
            local_hard.append("not_bounded")
        if item.get("requires_network") is True:
            local_hard.append("requires_network")
        if item.get("requires_daemon") is True:
            local_hard.append("requires_daemon")
        if item.get("requires_scheduler") is True:
            local_hard.append("requires_scheduler")
        if item.get("queue_widening") is True:
            local_hard.append("queue_widening")
        if item.get("entity_birth") is True:
            local_hard.append("entity_birth")
        if item.get("anna_birth") is True:
            local_hard.append("anna_birth")
        if item.get("agi_claim") is True:
            local_hard.append("agi_claim")
        if item.get("final_canon_approval") is True:
            local_hard.append("final_canon_approval")

        if local_hard:
            hard.append({"candidate": name, "reasons": local_hard})
        else:
            accepted.append(item)

    if not accepted:
        return {
            "status": "BLOCKED",
            "selected_target": None,
            "hard_failures": hard or [{"candidate": None, "reasons": ["empty_candidate_queue"]}],
        }

    accepted.sort(key=lambda x: (-int(x.get("priority", 0)), str(x.get("name"))))
    selected = accepted[0]

    return {
        "status": "PASS",
        "selected_target": selected.get("name"),
        "selected": selected,
        "accepted_count": len(accepted),
        "rejected": hard,
        "hard_failures": [],
    }

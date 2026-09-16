import json
import hashlib
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
PULSE = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SOCC_SELF_BUILDING_PULSE_V1.json"
PANEL = ROOT / "core/socc/autonomy/self_building/status_panel/runtime/SELF_BUILDING_RUNTIME_STATUS_PANEL_V1.json"
PROGRESS = ROOT / "core/socc/autonomy/self_building/loop/SELF_BUILDING_VISIBLE_PROGRESS_V1.json"

ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"
POLICY = ROOT / "core/socc/autonomy/self_building/atomic_commit/enforcement/ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_POLICY_V1.json"

ENFORCED_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_REVIEW_V1_PROOF.json"
SELECTOR_REPAIR_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_REPAIR_V1_PROOF.json"
ENFORCED_VALIDATION_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_VALIDATION_V1_PROOF.json"
ATOMIC_HELPER_REVIEW_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ROUTE_AUTHORITY_ATOMIC_COMMIT_HELPER_REVIEW_V1_PROOF.json"

OUT_DIR = ROOT / "core/socc/autonomy/self_building/target_selector"
SELECTOR = ROOT / "scripts/socc/socc_enforced_self_building_next_target_selector_v1.py"
SPEC = OUT_DIR / "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_SPEC_V1.json"
BUILD = OUT_DIR / "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_BUILD_V1.json"
BUILD_MD = OUT_DIR / "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_BUILD_V1.md"
CANDIDATE_QUEUE = OUT_DIR / "ENFORCED_SELF_BUILDING_NEXT_TARGET_CANDIDATE_QUEUE_V1.json"
SELECTION = OUT_DIR / "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTION_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_V1_MEMORY.json"

EXPECTED_NEXT = "build_enforced_self_building_next_target_selector_v1"
EXPECTED_REVIEW_CAPABILITY = "ATOMIC_COMMIT_ENFORCED_SELF_BUILDING_LANE_REVIEW_SEALED_ROUTE_TRANSITIONS_LAWFUL"
NEXT = "validate_enforced_self_building_next_target_selector_v1"

FORBIDDEN = [
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

def forbidden_false(obj):
    return all(obj.get(k) is False for k in FORBIDDEN if k in obj)

route = read_json(ROUTE)
pulse = read_json(PULSE)
panel = read_json(PANEL)
progress = read_json(PROGRESS)

enforced_review = read_json(ENFORCED_REVIEW_PROOF)
selector_repair = read_json(SELECTOR_REPAIR_PROOF)
enforced_validation = read_json(ENFORCED_VALIDATION_PROOF)
atomic_helper_review = read_json(ATOMIC_HELPER_REVIEW_PROOF)
policy = read_json(POLICY)
enforcer_text = read_text(ENFORCER)

route_next = route.get("lawful_next") or route.get("real_next")
route_truth = route.get("truth_boundary")
route_upstream = route.get("upstream_proof")

route_upstream_lawful = (
    route_upstream == str(ENFORCED_REVIEW_PROOF)
    or (
        route_upstream == str(SELECTOR_REPAIR_PROOF)
        and selector_repair.get("status") == "PASS"
        and selector_repair.get("route_transitions_lawful_under_atomic_commit_materialized") is True
        and selector_repair.get("target_selector_route_flag_repaired") is True
        and selector_repair.get("ready_to_retry_selector_build") is True
        and selector_repair.get("hard_failures") == []
    )
)

checks = {
    "route_authority_exists": ROUTE.exists(),
    "route_status_pass": route.get("status") == "PASS",
    "route_points_to_selector_build": route_next == EXPECTED_NEXT,
    "route_upstream_enforced_review_ok": route_upstream_lawful,
    "route_atomic_commit_enforced_lane_review_sealed": route.get("atomic_commit_enforced_self_building_lane_review_sealed") is True,
    "route_transitions_lawful_under_atomic_commit": route.get("route_transitions_lawful_under_atomic_commit") is True,
    "route_ready_to_select_next_target": route.get("ready_to_select_next_self_building_target") is True,
    "route_self_building_mode_enabled": route.get("self_building_mode_enabled") is True,
    "route_visible_bounded_mode_ready": route.get("visible_bounded_mode_ready") is True,

    "enforced_review_proof_exists": ENFORCED_REVIEW_PROOF.exists(),
    "enforced_review_status_pass": enforced_review.get("status") == "PASS",
    "enforced_review_capability_ok": enforced_review.get("capability") == EXPECTED_REVIEW_CAPABILITY,
    "enforced_review_real_next_ok": enforced_review.get("real_next") == EXPECTED_NEXT,
    "enforced_review_route_transitions_lawful": enforced_review.get("route_transitions_lawful_under_atomic_commit") is True,
    "enforced_review_ready_to_select_target": enforced_review.get("ready_to_select_next_self_building_target") is True,
    "enforced_review_hard_failures_empty": enforced_review.get("hard_failures") == [],

    "selector_repair_bridge_allowed_if_used": (
        route_upstream != str(SELECTOR_REPAIR_PROOF)
        or (
            SELECTOR_REPAIR_PROOF.exists()
            and selector_repair.get("status") == "PASS"
            and selector_repair.get("route_transitions_lawful_under_atomic_commit_materialized") is True
            and selector_repair.get("target_selector_route_flag_repaired") is True
            and selector_repair.get("ready_to_retry_selector_build") is True
            and selector_repair.get("real_next") == EXPECTED_NEXT
            and selector_repair.get("hard_failures") == []
        )
    ),

    "enforced_validation_proof_exists": ENFORCED_VALIDATION_PROOF.exists(),
    "enforced_validation_status_pass": enforced_validation.get("status") == "PASS",
    "enforced_validation_direct_write_rejection_validated": enforced_validation.get("direct_route_write_rejection_validated") is True,
    "enforced_validation_transition_enforcement_validated": enforced_validation.get("atomic_commit_transition_enforcement_validated") is True,

    "atomic_helper_review_proof_exists": ATOMIC_HELPER_REVIEW_PROOF.exists(),
    "atomic_helper_review_status_pass": atomic_helper_review.get("status") == "PASS",
    "atomic_helper_writeback_class_closed": atomic_helper_review.get("writeback_order_drift_class_closed") is True,

    "policy_exists": POLICY.exists(),
    "policy_status_enforced": policy.get("status") == "ENFORCED",
    "policy_atomic_commit_required": policy.get("atomic_commit_required_for_route_transitions") is True,
    "policy_direct_route_write_forbidden": policy.get("direct_route_write_forbidden") is True,

    "enforcer_exists": ENFORCER.exists(),
    "enforcer_has_enforce_transition": "def enforce_atomic_commit_transition(" in enforcer_text,
    "enforcer_has_reject_direct_route_write": "def reject_direct_route_write(" in enforcer_text,

    "pulse_exists": PULSE.exists(),
    "panel_exists": PANEL.exists(),
    "progress_exists": PROGRESS.exists(),

    "pulse_lawful_next_matches_route": pulse.get("lawful_next") == route_next,
    "panel_lawful_next_matches_route": panel.get("lawful_next") == route_next,
    "progress_lawful_next_matches_route": progress.get("lawful_next") == route_next,

    "pulse_truth_boundary_matches_route": pulse.get("truth_boundary") == route_truth,
    "panel_truth_boundary_matches_route": panel.get("truth_boundary") == route_truth,
    "progress_truth_boundary_matches_route": progress.get("truth_boundary") == route_truth,

    "pulse_upstream_matches_route": pulse.get("route_authority_upstream_proof") == route_upstream,
    "panel_upstream_matches_route": panel.get("route_authority_upstream_proof") == route_upstream,
    "progress_upstream_matches_route": progress.get("route_authority_upstream_proof") == route_upstream,

    "route_forbidden_false": forbidden_false(route),
    "pulse_forbidden_false": forbidden_false(pulse),
    "panel_forbidden_false": forbidden_false(panel),
    "progress_forbidden_false": forbidden_false(progress),

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

for name, src in [
    ("route", route),
    ("enforced_review", enforced_review),
    ("enforced_validation", enforced_validation),
    ("atomic_helper_review", atomic_helper_review),
    ("pulse", pulse),
    ("panel", panel),
    ("progress", progress),
]:
    for key in FORBIDDEN:
        if key in src:
            checks[f"{name}_{key}_false"] = src.get(key) is False

hard = [{"code": "CHECK_FAIL", "check": k, "actual": v} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

truth_boundary = (
    "Enforced self-building next-target selector build only. This builds a bounded selector that chooses the next self-building target "
    "from evidence, risk, maturity, and forbidden-escalation gates under atomic-commit enforcement. It does not execute a tick, enable "
    "continuous loop, launch daemon, install scheduler, enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)

if status == "PASS":
    capability = "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_BUILT_BOUNDED_SELECTION"
    real_next = NEXT
    final_socc_status = "SOCC_ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_PASS_VALIDATION_NEXT_NOT_DAEMON_NOT_AGI"
else:
    capability = "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_BLOCKED"
    real_next = "repair_enforced_self_building_next_target_selector_v1"
    final_socc_status = "SOCC_ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_FAIL"

selector_code = r'''#!/usr/bin/env python3
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
'''

candidate_queue = {
    "id": "ENFORCED_SELF_BUILDING_NEXT_TARGET_CANDIDATE_QUEUE_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "candidates": [
        {
            "name": "build_self_building_effect_auditor_v1",
            "priority": 100,
            "reason": "Next major risk after writeback control: prevent semantic-null PASS and prove material effect of each build.",
            "evidence_ready": True,
            "bounded": True,
            "requires_network": False,
            "requires_daemon": False,
            "requires_scheduler": False,
            "queue_widening": False,
            "entity_birth": False,
            "anna_birth": False,
            "agi_claim": False,
            "final_canon_approval": False,
        },
        {
            "name": "build_self_building_crash_recovery_probe_v1",
            "priority": 80,
            "reason": "Useful after atomic commits, but effect-auditor is more fundamental before runtime continuity.",
            "evidence_ready": True,
            "bounded": True,
            "requires_network": False,
            "requires_daemon": False,
            "requires_scheduler": False,
            "queue_widening": False,
            "entity_birth": False,
            "anna_birth": False,
            "agi_claim": False,
            "final_canon_approval": False,
        },
        {
            "name": "install_scheduler_v1",
            "priority": 999,
            "reason": "Intentionally rejected: scheduler is not yet lawful.",
            "evidence_ready": False,
            "bounded": False,
            "requires_network": False,
            "requires_daemon": False,
            "requires_scheduler": True,
            "queue_widening": False,
            "entity_birth": False,
            "anna_birth": False,
            "agi_claim": False,
            "final_canon_approval": False,
        },
    ],
}

selection = {
    "id": "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTION_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "PENDING",
}

if status == "PASS":
    write_text(SELECTOR, selector_code)
    SELECTOR.chmod(0o755)

    import importlib.util
    selector_import = importlib.util.spec_from_file_location("socc_enforced_self_building_next_target_selector_v1", SELECTOR)
    selector_mod = importlib.util.module_from_spec(selector_import)
    selector_import.loader.exec_module(selector_mod)

    selected = selector_mod.select_next_target(candidate_queue["candidates"])
    selection.update(selected)
    selection["status"] = "SELECTED" if selected.get("status") == "PASS" else "BLOCKED"
else:
    selection["status"] = "BLOCKED"
    selection["hard_failures"] = hard

selected_target = selection.get("selected_target")

spec = {
    "id": "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_SPEC_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "selector": str(SELECTOR),
    "selection_rule": "highest priority candidate that is bounded, evidence-ready, and has all forbidden escalation flags false",
    "forbidden_target_prefixes": [
        "launch_daemon",
        "install_scheduler",
        "enable_background_loop",
        "enable_continuous_loop",
        "widen_queue",
        "birth_entity",
        "birth_anna",
        "claim_agi",
        "approve_final_canon",
    ],
    "selected_target": selected_target,
    "truth_boundary": truth_boundary,
}

if status == "PASS":
    if selection.get("status") != "SELECTED":
        status = "FAIL"
        hard = [{"code": "SELECTION_FAIL", "actual": selection}]
        capability = "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_BLOCKED"
        real_next = "repair_enforced_self_building_next_target_selector_v1"
        final_socc_status = "SOCC_ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_FAIL"
    elif selected_target != "build_self_building_effect_auditor_v1":
        status = "FAIL"
        hard = [{"code": "UNEXPECTED_TARGET", "expected": "build_self_building_effect_auditor_v1", "actual": selected_target}]
        capability = "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_BLOCKED"
        real_next = "repair_enforced_self_building_next_target_selector_v1"
        final_socc_status = "SOCC_ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_FAIL"

build = {
    "id": "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_BUILD_V1",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": "BUILT" if status == "PASS" else "BLOCKED",
    "capability": capability,
    "selector": str(SELECTOR),
    "spec": str(SPEC),
    "candidate_queue": str(CANDIDATE_QUEUE),
    "selection": str(SELECTION),
    "source_enforced_lane_review_proof": str(ENFORCED_REVIEW_PROOF),

    "enforced_self_building_next_target_selector_built": status == "PASS",
    "bounded_target_selection_built": status == "PASS",
    "forbidden_target_filter_built": status == "PASS",
    "evidence_ready_gate_built": status == "PASS",
    "selected_next_target": selected_target if status == "PASS" else None,
    "ready_for_validation": status == "PASS",

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
    "truth_boundary": truth_boundary,
}
build["build_hash"] = h(build)

proof = {
    "id": "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": capability,
    "build": str(BUILD),
    "build_md": str(BUILD_MD),
    "selector": str(SELECTOR),
    "spec": str(SPEC),
    "candidate_queue": str(CANDIDATE_QUEUE),
    "selection": str(SELECTION),
    "memory": str(MEMORY),

    "enforced_self_building_next_target_selector_built": status == "PASS",
    "bounded_target_selection_built": status == "PASS",
    "forbidden_target_filter_built": status == "PASS",
    "evidence_ready_gate_built": status == "PASS",
    "selected_next_target": selected_target if status == "PASS" else None,
    "ready_for_validation": status == "PASS",

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
    "truth_boundary": truth_boundary,
}
proof["proof_hash"] = h(proof)

memory = {
    "id": "ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_V1_MEMORY",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "memory_effect": (
        "SOCC built bounded next-target selector under atomic-commit enforcement. Selected next target: "
        + str(selected_target)
    ),
    "proof": str(PROOF),
    "build": str(BUILD),
    "selected_next_target": selected_target,
    "real_next": real_next,
    "truth_boundary": truth_boundary,
}

if status == "PASS":
    write_json(SPEC, spec)
    write_json(CANDIDATE_QUEUE, candidate_queue)
    write_json(SELECTION, selection)

    # Commit selector build via enforced atomic lane.
    spec_import = importlib.util.spec_from_file_location("socc_self_building_atomic_commit_enforcer_v1", ENFORCER)
    enforcer_mod = importlib.util.module_from_spec(spec_import)
    spec_import.loader.exec_module(enforcer_mod)

    commit_result = enforcer_mod.enforce_atomic_commit_transition(
        lawful_next=real_next,
        upstream_proof=str(PROOF),
        truth_boundary=truth_boundary,
        route_updates={
            "enforced_self_building_next_target_selector_built": True,
            "bounded_target_selection_built": True,
            "forbidden_target_filter_built": True,
            "evidence_ready_gate_built": True,
            "selected_next_target": selected_target,
            "ready_for_validation": True,
            "recommended_next_target": real_next,
        },
        pulse_updates={
            "enforced_self_building_next_target_selector_built": True,
            "selected_next_target": selected_target,
        },
        panel_updates={
            "enforced_self_building_next_target_selector_built": True,
            "selected_next_target": selected_target,
        },
        progress_updates={
            "enforced_self_building_next_target_selector_built": True,
            "selected_next_target": selected_target,
            "recommended_next_target": real_next,
        },
        reason="build_enforced_self_building_next_target_selector_v1",
    )

    build["atomic_commit_result"] = commit_result
    proof["atomic_commit_result"] = commit_result

    if commit_result.get("status") != "PASS":
        status = "FAIL"
        hard = [{"code": "ATOMIC_COMMIT_FAIL", "actual": commit_result}]
        build["status"] = "BLOCKED"
        build["hard_failures"] = hard
        build["real_next"] = "repair_enforced_self_building_next_target_selector_v1"
        proof["status"] = status
        proof["hard_failures"] = hard
        proof["real_next"] = "repair_enforced_self_building_next_target_selector_v1"

md = "# ENFORCED SELF-BUILDING NEXT TARGET SELECTOR V1\n\n"
md += "STATUS: " + status + "\n"
md += "CAPABILITY: " + capability + "\n\n"
md += "## БЫЛО\n\nAtomic-commit enforced lane was review-sealed. Future route transitions are lawful only through enforced atomic commit.\n\n"
md += "## ДЕЙСТВИЕ\n\nBuilt bounded next-target selector using evidence, risk, maturity, and forbidden escalation gates.\n\n"
md += "## ВАЛИДАТОР\n\n"
for k, v in checks.items():
    md += "- " + k + ": " + str(v) + "\n"
md += "\n## СТАЛО\n\n"
if status == "PASS":
    md += "Next-target selector is built. Selected next target: `" + str(selected_target) + "`. Next is validation.\n\n"
else:
    md += "Next-target selector build is blocked. Repair required.\n\n"
md += "## Selected target\n\n" + str(selected_target) + "\n\n"
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

write_json(BUILD, build)
write_json(PROOF, proof)
write_json(MEMORY, memory)
write_text(BUILD_MD, md)

print("ENFORCED SELF-BUILDING NEXT TARGET SELECTOR :: " + status)
print("FINAL_SOCC_STATUS::" + final_socc_status)
print("CAPABILITY::" + capability)
print("SELECTOR::" + str(SELECTOR))
print("SPEC::" + str(SPEC))
print("CANDIDATE_QUEUE::" + str(CANDIDATE_QUEUE))
print("SELECTION::" + str(SELECTION))
print("BUILD::" + str(BUILD))
print("PROOF::" + str(PROOF))
print("MEMORY::" + str(MEMORY))
print("ENFORCED_SELF_BUILDING_NEXT_TARGET_SELECTOR_BUILT::" + str(status == "PASS"))
print("BOUNDED_TARGET_SELECTION_BUILT::" + str(status == "PASS"))
print("FORBIDDEN_TARGET_FILTER_BUILT::" + str(status == "PASS"))
print("EVIDENCE_READY_GATE_BUILT::" + str(status == "PASS"))
print("SELECTED_NEXT_TARGET::" + str(selected_target))
print("READY_FOR_VALIDATION::" + str(status == "PASS"))
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

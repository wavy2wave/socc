#!/usr/bin/env python3
"""
SOCC self-building effect-auditor VALIDATE node (real, re-runnable).

Validates the built effect auditor by EXERCISING it, not by trusting a prior proof:
  1) POSITIVE control  — audit the real build->validate transition (attested by the
     build proof + build memory + build replay). The auditor MUST prove material effect.
  2) SEMANTIC-NULL control — audit a no-effect transition (no route change, no material
     claims). The auditor MUST block it with a SEMANTIC_NULL hard failure.
Only if the auditor passes material effect AND blocks the null does this node seal the
validation and advance the route validate->review through the sealed atomic-commit enforcer.

Deterministic. No tick, daemon, network, queue-widening, entity/ANNA birth, or AGI claim.
"""
import json
import hashlib
import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"
AUDITOR = ROOT / "scripts/socc/socc_self_building_effect_auditor_v1.py"

BUILD_PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_V1_PROOF.json"
BUILD_REPLAY = ROOT / "core/socc/autonomy/self_building/effect_auditor/SELF_BUILDING_EFFECT_AUDITOR_BUILD_REPLAY_V1.json"
BUILD_MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_EFFECT_AUDITOR_V1_MEMORY.json"

VDIR = ROOT / "core/socc/autonomy/self_building/effect_auditor/validation"
VALIDATION_JSON = VDIR / "SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_V1.json"
VALIDATION_REPLAY = VDIR / "SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_REPLAY_V1.json"
VALIDATION_NULL_PROBE = VDIR / "SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_NULL_PROBE_V1.json"
VALIDATION_COMMIT_RESULT = VDIR / "SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_COMMIT_RESULT_V1.json"

PROOF = ROOT / "core/socc/approved_autonomy_lane_runner/proof/SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_V1_MEMORY.json"

STEP = "validate_self_building_effect_auditor_v1"
EXPECTED_NEXT = "review_self_building_effect_auditor_v1"
CAPABILITY = "SELF_BUILDING_EFFECT_AUDITOR_VALIDATED_SEMANTIC_NULL_BLOCKED"

FORBIDDEN = [
    "continuous_loop_enabled", "daemon_running", "scheduler_installed",
    "background_loop_enabled", "network_used", "queue_widening_allowed",
    "entity_birth_allowed", "anna_birth_allowed", "agi_claim_allowed",
    "final_canon_approval_allowed",
]

TRUTH = (
    "Self-building effect auditor validation only. Exercises the auditor against a real "
    "positive material-effect control and a semantic-null control, then routes next to review. "
    "It does not execute a tick, enable continuous loop, launch daemon, install scheduler, "
    "enable background loop, use network, widen queue, birth Entity/ANNA, approve final canon, or claim AGI."
)


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")


def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def h(o):
    return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def forbidden_false(obj):
    return all(obj.get(k) is False for k in FORBIDDEN if k in obj)


def import_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NOT_DONE = {
    "tick_executed_now": False, "continuous_loop_enabled": False, "daemon_running": False,
    "scheduler_installed": False, "background_loop_enabled": False, "network_used": False,
    "queue_widening_allowed": False, "entity_birth_allowed": False, "anna_birth_allowed": False,
    "agi_claim_allowed": False, "final_canon_approval_allowed": False,
}


def main():
    route = read_json(ROUTE)
    route_next = route.get("lawful_next") or route.get("real_next")
    build_proof = read_json(BUILD_PROOF)

    auditor = import_module(AUDITOR, "auditor")

    # 1) POSITIVE control: the real build->validate transition (attested by BUILD_PROOF).
    positive = auditor.audit_effect(
        before={"route_before": {"lawful_next": "build_self_building_effect_auditor_v1"}},
        after={
            "route_after": {
                "lawful_next": STEP,
                "upstream_proof": str(BUILD_PROOF),
            },
            "expected_lawful_next_before": "build_self_building_effect_auditor_v1",
            "expected_lawful_next_after": STEP,
            "expected_upstream_proof_after": str(BUILD_PROOF),
            "expected_memory": str(BUILD_MEMORY),
            "required_artifacts": [str(BUILD_PROOF), str(BUILD_MEMORY), str(BUILD_REPLAY)],
            "changed_artifacts": [str(BUILD_PROOF)],
            "material_claims": [
                "effect_auditor_built", "semantic_null_pass_control_built",
                "material_effect_gate_built", "positive_effect_case_passed",
                "negative_semantic_null_case_blocked",
            ],
        },
    )

    # 2) SEMANTIC-NULL control: no route change, no material claims -> must be blocked.
    null_probe = auditor.audit_effect(
        before={"route_before": {"lawful_next": "build_self_building_effect_auditor_v1"}},
        after={
            "route_after": {"lawful_next": "build_self_building_effect_auditor_v1"},
            "required_artifacts": [],
            "changed_artifacts": [],
            "material_claims": [],
        },
    )

    null_has_semantic_null = any(
        x.get("code") == "SEMANTIC_NULL" for x in (null_probe.get("hard_failures") or [])
    )

    # Self-discipline: validate is only valid if the auditor behaves correctly on BOTH controls.
    hard = []
    if build_proof.get("status") != "PASS" or build_proof.get("hard_failures") not in ([], None):
        hard.append({"code": "UPSTREAM_BUILD_NOT_PASS", "status": build_proof.get("status")})
    if route_next != STEP:
        hard.append({"code": "ROUTE_NOT_AT_STEP", "route_next": route_next, "step": STEP})
    if not ENFORCER.exists():
        hard.append({"code": "ENFORCER_MISSING"})
    if positive.get("status") != "PASS" or positive.get("material_effect_proven") is not True:
        hard.append({"code": "POSITIVE_CONTROL_NOT_PROVEN", "positive": positive.get("status")})
    if positive.get("hard_failures") not in ([], None):
        hard.append({"code": "POSITIVE_CONTROL_HARD_FAILURES", "hard": positive.get("hard_failures")})
    if null_probe.get("status") != "FAIL" or null_probe.get("semantic_null_pass_blocked") is not True:
        hard.append({"code": "NULL_CONTROL_NOT_BLOCKED", "null": null_probe.get("status")})
    if null_probe.get("material_effect_proven") is not False:
        hard.append({"code": "NULL_CONTROL_FALSE_MATERIAL_EFFECT"})
    if not null_has_semantic_null:
        hard.append({"code": "NULL_CONTROL_MISSING_SEMANTIC_NULL_CODE"})

    # Persist the control artifacts (whatever the outcome — they are the evidence).
    write_json(VALIDATION_REPLAY, {**positive, "id": "SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_REPLAY_V1",
                                   "control": "positive_material_effect", "created_at_utc": now_utc()})
    write_json(VALIDATION_NULL_PROBE, {**null_probe, "id": "SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_NULL_PROBE_V1",
                                       "control": "semantic_null", "created_at_utc": now_utc()})
    write_json(VALIDATION_JSON, {
        "id": "SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_V1",
        "created_at_utc": now_utc(), "created_at_msk": now_msk(),
        "status": "VALIDATED" if not hard else "BLOCKED",
        "capability": CAPABILITY,
        "positive_replay": str(VALIDATION_REPLAY),
        "null_probe": str(VALIDATION_NULL_PROBE),
        "truth_boundary": TRUTH, **NOT_DONE,
    })

    if hard:
        _seal(False, hard, {})
        return 1

    # Lawful advance validate -> review through the sealed atomic-commit enforcer.
    enforcer = import_module(ENFORCER, "enforcer")
    updates = {
        "self_building_effect_auditor_validated": True,
        "semantic_null_pass_control_validated": True,
        "material_effect_gate_validated": True,
        "positive_material_effect_validation_passed": True,
        "negative_semantic_null_validation_blocked": True,
        "ready_for_review": True,
        "recommended_next_target": EXPECTED_NEXT,
    }
    commit = enforcer.enforce_atomic_commit_transition(
        lawful_next=EXPECTED_NEXT,
        upstream_proof=str(PROOF),
        truth_boundary=TRUTH,
        route_updates=updates,
        pulse_updates=updates,
        panel_updates=updates,
        progress_updates=updates,
        reason=STEP,
    )
    write_json(VALIDATION_COMMIT_RESULT, commit)

    route2 = read_json(ROUTE)
    ok = (commit.get("status") == "PASS" and commit.get("committed") is True
          and commit.get("hard_failures") in ([], None) and bool(commit.get("snapshot"))
          and (route2.get("lawful_next") or route2.get("real_next")) == EXPECTED_NEXT)
    if not ok:
        _seal(False, [{"code": "ENFORCED_COMMIT_FAILED", "commit": commit}], commit)
        return 1

    _seal(True, [], commit)
    return 0


def _seal(ok, hard, commit):
    status = "PASS" if ok else "FAIL"
    proof = {
        "id": "SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_V1_PROOF",
        "created_at_utc": now_utc(), "created_at_msk": now_msk(),
        "status": status,
        "capability": CAPABILITY if ok else "SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_BLOCKED",
        "upstream_proof": str(BUILD_PROOF),
        "positive_replay": str(VALIDATION_REPLAY),
        "null_probe": str(VALIDATION_NULL_PROBE),
        "validation_commit_result": str(VALIDATION_COMMIT_RESULT),
        "self_building_effect_auditor_validated": ok,
        "semantic_null_pass_control_validated": ok,
        "material_effect_gate_validated": ok,
        "positive_material_effect_validation_passed": ok,
        "negative_semantic_null_validation_blocked": ok,
        "ready_for_review": ok,
        "hard_failures": hard,
        "real_next": EXPECTED_NEXT if ok else "repair_self_building_effect_auditor_validation_v1",
        "truth_boundary": TRUTH, **NOT_DONE,
    }
    proof["proof_hash"] = h(proof)
    write_json(PROOF, proof)
    write_json(MEMORY, {
        "id": "SELF_BUILDING_EFFECT_AUDITOR_VALIDATION_V1_MEMORY",
        "created_at_utc": now_utc(), "created_at_msk": now_msk(),
        "status": status,
        "memory_effect": ("Validated effect auditor: positive material-effect proven and "
                          "semantic-null blocked; advanced route validate->review."
                          if ok else "Effect auditor validation blocked; auditor controls did not hold."),
        "proof": str(PROOF), "real_next": proof["real_next"], "truth_boundary": TRUTH,
    })
    print("SELF-BUILDING EFFECT AUDITOR VALIDATION :: " + status)
    print("CAPABILITY::" + proof["capability"])
    print("POSITIVE_MATERIAL_EFFECT_VALIDATION_PASSED::" + str(ok))
    print("NEGATIVE_SEMANTIC_NULL_VALIDATION_BLOCKED::" + str(ok))
    print("READY_FOR_REVIEW::" + str(ok))
    print("REAL_NEXT::" + proof["real_next"])
    print("HARD_FAILURES::" + json.dumps(hard, ensure_ascii=False))
    print("TRUTH_BOUNDARY::" + TRUTH)


if __name__ == "__main__":
    raise SystemExit(main())

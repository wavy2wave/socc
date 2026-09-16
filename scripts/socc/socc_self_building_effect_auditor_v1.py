#!/usr/bin/env python3
from pathlib import Path
import json
import hashlib

ROOT = Path(".")

FORBIDDEN_FLAGS = [
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

def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}

def exists(path):
    return Path(path).exists()

def file_hash(path):
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()[:24]

def forbidden_false(obj):
    return all(obj.get(k) is False for k in FORBIDDEN_FLAGS if k in obj)

def audit_effect(before, after):
    """
    before/after are dicts:
      route_before, route_after
      required_artifacts: list[path]
      changed_artifacts: list[path]
      expected_lawful_next_before
      expected_lawful_next_after
      expected_upstream_proof_after
      expected_memory
      material_claims: list[str]
    """
    hard = []
    evidence = {}

    route_before = before.get("route_before") or {}
    route_after = after.get("route_after") or {}

    before_next = route_before.get("lawful_next") or route_before.get("real_next")
    after_next = route_after.get("lawful_next") or route_after.get("real_next")

    expected_before = after.get("expected_lawful_next_before")
    expected_after = after.get("expected_lawful_next_after")
    expected_upstream = after.get("expected_upstream_proof_after")
    expected_memory = after.get("expected_memory")

    evidence["lawful_next_before"] = before_next
    evidence["lawful_next_after"] = after_next
    evidence["route_changed"] = before_next != after_next
    evidence["expected_before_ok"] = before_next == expected_before if expected_before else True
    evidence["expected_after_ok"] = after_next == expected_after if expected_after else True
    evidence["upstream_ok"] = route_after.get("upstream_proof") == expected_upstream if expected_upstream else True
    evidence["memory_exists"] = exists(expected_memory) if expected_memory else True
    evidence["forbidden_false_after"] = forbidden_false(route_after)

    if not evidence["route_changed"]:
        hard.append({"code": "SEMANTIC_NULL", "check": "route_changed", "actual": False})
    if evidence["expected_before_ok"] is not True:
        hard.append({"code": "EXPECTATION_FAIL", "check": "expected_before_ok", "actual": before_next})
    if evidence["expected_after_ok"] is not True:
        hard.append({"code": "EXPECTATION_FAIL", "check": "expected_after_ok", "actual": after_next})
    if evidence["upstream_ok"] is not True:
        hard.append({"code": "EXPECTATION_FAIL", "check": "upstream_ok", "actual": route_after.get("upstream_proof")})
    if evidence["memory_exists"] is not True:
        hard.append({"code": "MISSING_EFFECT", "check": "memory_exists", "actual": expected_memory})
    if evidence["forbidden_false_after"] is not True:
        hard.append({"code": "FORBIDDEN_TRUE", "check": "forbidden_false_after", "actual": False})

    required = after.get("required_artifacts") or []
    changed = after.get("changed_artifacts") or []

    required_results = {}
    for item in required:
        required_results[item] = exists(item)
        if not required_results[item]:
            hard.append({"code": "MISSING_ARTIFACT", "artifact": item})

    changed_results = {}
    for item in changed:
        changed_results[item] = file_hash(item)
        if changed_results[item] is None:
            hard.append({"code": "MISSING_CHANGED_ARTIFACT", "artifact": item})

    evidence["required_artifacts"] = required_results
    evidence["changed_artifacts_hashes"] = changed_results
    evidence["material_claims_count"] = len(after.get("material_claims") or [])

    if evidence["material_claims_count"] <= 0:
        hard.append({"code": "NO_MATERIAL_CLAIMS", "check": "material_claims_count", "actual": 0})

    return {
        "status": "PASS" if not hard else "FAIL",
        "semantic_null_pass_blocked": bool(hard),
        "material_effect_proven": not bool(hard),
        "evidence": evidence,
        "hard_failures": hard,
    }

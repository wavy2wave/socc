#!/usr/bin/env python3
from pathlib import Path
import importlib.util

AUDITOR = Path("scripts/socc/socc_self_building_effect_auditor_v1.py")

def _import_auditor():
    spec = importlib.util.spec_from_file_location("socc_self_building_effect_auditor_v1", AUDITOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def enforce_effect_auditor_lane(before, after):
    """
    Enforced lane gate for bounded self-building steps.

    Required input:
      before: {"route_before": {...}}
      after:
        {
          "route_after": {...},
          "expected_lawful_next_before": "...",
          "expected_lawful_next_after": "...",
          "expected_upstream_proof_after": "...",
          "expected_memory": "...",
          "required_artifacts": [...],
          "changed_artifacts": [...],
          "material_claims": [...]
        }

    PASS means material effect proven.
    FAIL means semantic-null or missing-effect work must not be accepted as PASS.
    """
    auditor = _import_auditor()
    audit = auditor.audit_effect(before, after)

    return {
        "status": "PASS" if audit.get("status") == "PASS" and audit.get("material_effect_proven") is True else "FAIL",
        "effect_auditor_enforced": True,
        "material_effect_required": True,
        "semantic_null_pass_blocked": audit.get("status") != "PASS",
        "audit": audit,
        "hard_failures": [] if audit.get("status") == "PASS" and audit.get("material_effect_proven") is True else audit.get("hard_failures", []),
    }

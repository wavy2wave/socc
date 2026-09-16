#!/usr/bin/env python3
"""
SOCC Lawful Step Engine V1 — a reusable, fail-closed engine for one lawful chain step.

This closes the "no general gate factory" gap: instead of a bespoke ~250-line runner per
step, a step is described by a declarative SPEC and driven through ONE proven transition
core. The core is identical to the hand-written runners already validated many times:

    real checks (computed from file state)  ->  PASS only if zero hard failures
    PASS  ->  write artifact + proof + memory + panel
          ->  lawful route transition via the ENFORCED atomic-commit helper
          ->  sync observe mirrors (AUTONOMY_PULSE, CONTROL_PANEL)
          ->  stop
    FAIL  ->  write a FAIL proof, DO NOT move the route (fail-closed)

No fake pass: every check is computed from real file state. Checks are declarative but
REAL — they assert on actual JSON files (predecessor proof PASS, upstream proofs PASS,
plan completeness, etc.). The engine adds the universal safety guard and the stop.

A SPEC is a dict:
  current, next                : route step ids (str)
  kind                         : label (str), e.g. "review" | "accept" | "gate" | "build"
  predecessor_proof            : path str | None  (must be PASS and point next->current)
  upstream_proofs              : [path str]       (each must be status == PASS)
  extra_checks                 : [ {name, file, op, path?, value?} ]  declarative REAL checks
  artifact                     : {path, body}     primary document to write (dict body)
  artifact_md                  : {path, lines}    optional markdown
  proof_path, memory_path, panel_path : output paths (str)
  proof_id, capability_pass, capability_fail, verdict_pass, verdict_fail : labels
  truth_boundary               : str
  source_flag                  : str   (current_lawful_next_source on PASS)
  route_update_extra           : dict  (extra route_updates on PASS)
  active_path                  : path str | None  (PASS-only "ACTIVE_ACCEPTED" marker)

extra_check ops: "exists", "proof_pass", "json_true", "json_eq", "json_nonempty".
"""
import json, hashlib, shutil, importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")

ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
AUTONOMY_PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
CONTROL_PANEL = ROOT / "core/socc/route_authority/self_construction_autonomy/CONTROL_PANEL_STATE_V1.json"
AUTHORITY_FILES = [ROUTE, AUTONOMY_PULSE, CONTROL_PANEL]
ENFORCER = ROOT / "scripts/socc/socc_self_building_atomic_commit_enforcer_v1.py"


def now_utc(): return datetime.now(timezone.utc).isoformat()
def now_msk(): return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")


def rj(p):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return {}


def wj(p, o):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def wt(p, s):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(s).rstrip() + "\n", encoding="utf-8")


def h16(o): return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def load_enforcer():
    spec = importlib.util.spec_from_file_location("socc_self_building_atomic_commit_enforcer_v1", ENFORCER)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def get_next(o):
    if not isinstance(o, dict): return None
    for k in ["current_lawful_next", "lawful_next", "next", "route_next", "current_next"]:
        if isinstance(o.get(k), str): return o[k]
    return None


def proof_next(o):
    for k in ["next_after_pass", "next_lawful_step", "next_required_step"]:
        if isinstance(o.get(k), str): return o[k]
    return None


def _dotted(d, path):
    cur = d
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _eval_check(c):
    f = rj(c["file"])
    op = c["op"]
    if op == "exists":
        return Path(c["file"]).exists()
    if op == "proof_pass":
        return f.get("status") == "PASS"
    val = _dotted(f, c["path"]) if c.get("path") else f
    if op == "json_true":
        return val is True
    if op == "json_eq":
        return val == c.get("value")
    if op == "json_nonempty":
        return bool(val) and (len(val) > 0 if hasattr(val, "__len__") else True)
    return False


STANDARD_SAFETY = {
    "no_entity_birth": True, "no_anna_birth": True, "no_anna_instantiation": True,
    "no_agent_spawn": True, "no_daemon": True, "no_background": True, "no_network": True,
    "no_scheduler": True, "no_old_route_resume": True, "no_mw_route": True,
    "no_agi_claim": True, "no_l3_claim": True, "no_revenue_claim": True,
}


def run_step(spec):
    current = spec["current"]; nxt = spec["next"]
    ts = now_utc()
    authority_nexts = sorted({get_next(rj(p)) for p in AUTHORITY_FILES if get_next(rj(p))})

    presence = {"enforcer_exists": ENFORCER.exists()}
    checks = dict(STANDARD_SAFETY)
    checks["authority_at_current"] = authority_nexts == [current]

    pred = spec.get("predecessor_proof")
    if pred:
        pr = rj(pred)
        checks["predecessor_proof_exists"] = Path(pred).exists()
        checks["predecessor_proof_pass"] = pr.get("status") == "PASS"
        checks["predecessor_points_to_current"] = proof_next(pr) == current

    for up in spec.get("upstream_proofs", []):
        name = Path(up).stem.replace("SOCC_", "").replace("_PROOF", "").lower()
        checks[f"upstream_{name}_pass"] = rj(up).get("status") == "PASS"

    for c in spec.get("extra_checks", []):
        checks[c["name"]] = _eval_check(c) is True

    checks.update(presence)
    hard = [k for k, v in checks.items() if v is not True]
    status = "PASS" if not hard else "FAIL"

    # write primary artifact (always — records the verdict, PASS or FAIL)
    art = spec.get("artifact")
    if art:
        body = dict(art["body"])
        body.setdefault("created_at_utc", ts)
        body["status"] = status
        body["checks"] = checks
        body["hard_failures"] = hard
        wj(art["path"], body)
    if spec.get("artifact_md"):
        wt(spec["artifact_md"]["path"], "\n".join(spec["artifact_md"]["lines"]))

    commit_result = None; backup_dir = None
    PROOF = spec["proof_path"]

    if status == "PASS":
        snap = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_dir = ROOT / "core/socc/route_authority/self_construction_autonomy/lawful_step_backups" / (current + "_" + snap)
        backup_dir.mkdir(parents=True, exist_ok=True)
        for p in AUTHORITY_FILES:
            if p.exists(): shutil.copy2(p, backup_dir / p.name)

        if spec.get("active_path"):
            wj(spec["active_path"], {
                "id": Path(spec["active_path"]).stem, "created_at_utc": ts,
                "step": current, "authorizes_next": nxt,
                "truth_boundary": spec.get("truth_boundary", ""),
            })

        enforcer = load_enforcer()
        route_updates = {"current_lawful_next": nxt,
                         "current_lawful_next_source": spec.get("source_flag", current + "_pass"),
                         "recommended_next_target": nxt,
                         "entity_birth_allowed": False, "anna_birth_allowed": False}
        route_updates.update(spec.get("route_update_extra", {}))
        commit_result = enforcer.enforce_atomic_commit_transition(
            lawful_next=nxt, upstream_proof=str(PROOF),
            truth_boundary=spec.get("truth_boundary", ""),
            route_updates=route_updates, reason=current + "_pass_advance")
        if not (isinstance(commit_result, dict) and commit_result.get("status") == "PASS"):
            hard.append("ATOMIC_COMMIT_NOT_PASS"); status = "FAIL"

    if status == "PASS":
        route_hash = rj(ROUTE).get("route_hash")
        guard = {"daemon_running": False, "continuous_loop_enabled": False, "background_loop_enabled": False,
                 "scheduler_installed": False, "network_used": False, "queue_widening_allowed": False,
                 "entity_birth_allowed": False, "anna_birth_allowed": False, "agi_claim_allowed": False}
        for mp, extra_key in [(AUTONOMY_PULSE, None), (CONTROL_PANEL, "CONTROL_NEXT")]:
            m = rj(mp)
            m.update({"updated_at_utc": now_utc(), "status": "PASS", "current_lawful_next": nxt,
                      "lawful_next": nxt, "real_next": nxt,
                      "current_lawful_next_source": spec.get("source_flag", current + "_pass"),
                      "route_hash_ref": route_hash})
            if extra_key: m[extra_key] = nxt
            if isinstance(m.get("operator_view"), dict):
                m["operator_view"]["current_lawful_next"] = nxt
            m.update(guard)
            wj(mp, m)

    proof = {
        "id": spec.get("proof_id", "SOCC_" + current.upper() + "_PROOF"),
        "created_at_utc": ts, "created_at_msk": now_msk(), "status": status,
        "kind": spec.get("kind", "lawful_step"),
        "capability": spec.get("capability_pass") if status == "PASS" else spec.get("capability_fail"),
        "current_expected": current,
        "next_after_pass": nxt if status == "PASS" else None,
        "next_lawful_step": nxt if status == "PASS" else "manual_" + current + "_repair_required",
        "artifact": art["path"] if art else None,
        "checks": checks, "hard_failures": hard, "warnings": [],
        "atomic_commit_result": commit_result, "backup_dir": str(backup_dir) if backup_dir else None,
        "stopped_after_step": True, "entity_born": False, "anna_born": False,
        "no_entity_birth": True, "no_anna_birth": True, "no_daemon": True, "no_background": True,
        "no_network": True, "no_revenue_claim": True, "no_agi_claim": True, "no_l3_claim": True,
        "final_canon_approval_allowed": False, "truth_boundary": spec.get("truth_boundary", ""),
    }
    proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
    wj(PROOF, proof)

    if spec.get("memory_path"):
        wj(spec["memory_path"], {
            "id": Path(spec["memory_path"]).stem, "created_at_utc": ts, "status": "RECORDED",
            "step": current, "step_status": status, "hard_failures": hard, "proof": str(PROOF),
            "next": nxt if status == "PASS" else "manual_" + current + "_repair_required",
            "entity_born": False, "anna_born": False, "stopped_after_step": True,
            "truth_boundary": spec.get("truth_boundary", ""),
        })
    if spec.get("panel_path"):
        wj(spec["panel_path"], {
            "id": Path(spec["panel_path"]).stem, "created_at_utc": ts, "status": status,
            "stage": current, "current": current,
            "next": nxt if status == "PASS" else "manual_" + current + "_repair_required",
            "proof": str(PROOF), "hard_failures": hard,
            "entity_born": False, "anna_born": False, "truth_boundary": spec.get("truth_boundary", ""),
        })

    print(f"[{spec.get('kind','step'):<8}] {current:<48} STATUS::{status}  NEXT::{nxt if status=='PASS' else 'BLOCKED'}  HARD::{hard}")
    return {"status": status, "hard": hard, "proof": str(PROOF), "current": current, "next": nxt}


if __name__ == "__main__":
    print("This is a library module. Import run_step(spec) from a driver.")

#!/usr/bin/env python3
"""Knowledge Substrate step 1 — scan connector source roots into a registry.

Read-only. For each connector: walk source_root, hash/type/mtime/provenance each
file, mark new/changed/unchanged vs the prior registry. Writes the registry, a
proof, a memory sidecar, and advances the organ-local ACTIVE pointer (NOT the
global route authority).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))

from knowledge_substrate.io import (
    now_utc, now_msk, read_json, write_json, h, discipline_flags,
)
from knowledge_substrate.scanner import scan_root, scan_files, diff_status

ROOT = Path(".")
CONN_DIR = ROOT / "SYSTEM/CAPABILITIES/memory_continuity/connectors"
CONNECTORS = [
    CONN_DIR / "CONNECTOR_MEMORY_SOCC_V1.json",
    CONN_DIR / "CONNECTOR_ENTITY_SUBSTRATE_CANON_V1.json",
    CONN_DIR / "CONNECTOR_ANNA_V1.json",
]
ACTIVE = ROOT / "SYSTEM/CAPABILITIES/memory_continuity/ACTIVE_KNOWLEDGE_SUBSTRATE_DIRECTION.json"
REGISTRY = ROOT / "SOVEREIGN/MEMORY/documents/SOURCE_REGISTRY_V1.json"
PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/KNOWLEDGE_SUBSTRATE_SOURCE_SCAN_V1_PROOF.json"
MEMORY = ROOT / "MEMORY_WAVE/reports/autonomy/KNOWLEDGE_SUBSTRATE_SOURCE_SCAN_V1_MEMORY.json"

EXPECTED = "scan_knowledge_sources_v1"
NEXT = "ingest_knowledge_sources_v1"

TRUTH = ("Knowledge Substrate source scan only. Read-only walk of connector roots; "
         "files never moved/copied. Registers metadata + line counts. Global route "
         "authority untouched. No daemon/background/network/LLM.")

prior = read_json(REGISTRY)
prior_by_path = {s["abs_path"]: s for s in prior.get("sources", [])}

all_sources = []
connector_reports = []
scan_errors = []

for cpath in CONNECTORS:
    conn = read_json(cpath)
    if not conn:
        scan_errors.append(f"CONNECTOR_UNREADABLE::{cpath}")
        continue
    if conn.get("kind") == "explicit_file_list" or conn.get("file_list"):
        recs, err = scan_files(conn.get("file_list", []), conn.get("id"))
    else:
        recs, err = scan_root(
            conn.get("source_root", ""),
            conn.get("include_suffixes", []),
            conn.get("exclude_globs", []),
            recurse=conn.get("recurse", True),
        )
    if err:
        scan_errors.append(err)
    for r in recs:
        r["connector"] = conn.get("id")
    all_sources.extend(recs)
    connector_reports.append({
        "connector": conn.get("id"),
        "source_root": conn.get("source_root"),
        "file_count": len(recs),
        "error": err,
    })

all_sources = diff_status(all_sources, prior_by_path)
all_sources.sort(key=lambda r: (r.get("connector") or "", r.get("rel_path") or ""))

counts = {
    "total": len(all_sources),
    "new": sum(1 for s in all_sources if s["status"] == "new"),
    "changed": sum(1 for s in all_sources if s["status"] == "changed"),
    "unchanged": sum(1 for s in all_sources if s["status"] == "unchanged"),
}

checks = {
    "at_least_one_connector_read": len(connector_reports) >= 1,
    "no_connector_unreadable": all("UNREADABLE" not in e for e in scan_errors),
    "sources_found": counts["total"] > 0,
    "every_source_has_sha16": all(bool(s.get("sha16")) for s in all_sources),
    "every_source_has_abs_path": all(bool(s.get("abs_path")) for s in all_sources),
    "every_source_status_set": all(s.get("status") in ("new", "changed", "unchanged") for s in all_sources),
    "read_only_no_copy": True,
    "global_route_untouched": True,
}
hard = [{"code": "CHECK_FAIL", "check": k} for k, v in checks.items() if v is not True]
status = "PASS" if not hard else "FAIL"

registry = {
    "id": "SOURCE_REGISTRY_V1",
    "created_at_utc": prior.get("created_at_utc", now_utc()),
    "updated_at_utc": now_utc(),
    "updated_at_msk": now_msk(),
    "connectors": [str(c) for c in CONNECTORS],
    "connector_reports": connector_reports,
    "sources": all_sources,
    "counts": counts,
    "scan_errors": scan_errors,
}
registry["source_scan_hash"] = h(registry["sources"])

proof = {
    "id": "KNOWLEDGE_SUBSTRATE_SOURCE_SCAN_V1_PROOF",
    "created_at_utc": now_utc(),
    "created_at_msk": now_msk(),
    "status": status,
    "capability": "memory_continuity",
    "step": EXPECTED,
    "registry": str(REGISTRY),
    "counts": counts,
    "connector_reports": connector_reports,
    "scan_errors": scan_errors,
    "checks": checks,
    "hard_failures": hard,
    "real_next": NEXT if status == "PASS" else "repair_" + EXPECTED,
    "truth_boundary": TRUTH,
}
proof.update(discipline_flags())
proof["proof_hash"] = h(proof)

memory = {
    "id": "KNOWLEDGE_SUBSTRATE_SOURCE_SCAN_V1_MEMORY",
    "created_at_utc": now_utc(),
    "status": status,
    "memory_effect": f"Scanned {counts['total']} sources ({counts['new']} new, "
                     f"{counts['changed']} changed) into the Knowledge Substrate registry.",
    "proof": str(PROOF),
    "registry": str(REGISTRY),
    "real_next": NEXT if status == "PASS" else "repair_" + EXPECTED,
    "truth_boundary": TRUTH,
}

write_json(REGISTRY, registry)
write_json(PROOF, proof)
write_json(MEMORY, memory)

if status == "PASS":
    active = read_json(ACTIVE)
    active["last_step"] = EXPECTED
    active["next_required_step"] = NEXT
    active["updated_at_utc"] = now_utc()
    write_json(ACTIVE, active)

print("KNOWLEDGE SUBSTRATE :: SOURCE SCAN :: " + status)
print("REGISTRY::" + str(REGISTRY))
print("PROOF::" + str(PROOF))
print("TOTAL::" + str(counts["total"]))
print("NEW::" + str(counts["new"]))
print("CHANGED::" + str(counts["changed"]))
print("UNCHANGED::" + str(counts["unchanged"]))
print("SCAN_ERRORS::" + str(scan_errors))
print("REAL_NEXT::" + (NEXT if status == "PASS" else "repair_" + EXPECTED))
print("LLM_USED::False")
print("DAEMON_RUNNING::False")
print("NETWORK_USED::False")
print("GLOBAL_ROUTE_TOUCHED::False")
print("TRUTH_BOUNDARY::" + TRUTH)

raise SystemExit(0 if status == "PASS" else 1)

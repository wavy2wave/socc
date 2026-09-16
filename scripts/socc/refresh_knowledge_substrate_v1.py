#!/usr/bin/env python3
"""Knowledge Substrate — one foreground refresh of the living wiki.

Runs the full organ chain in sequence (scan -> ingest -> build article ->
validate -> review -> context pack) so a NEW or CHANGED source file is folded
into the wiki by a single command. This is the lawful "living wiki" path:
foreground, bounded, proof-backed — NOT a daemon/background loop.

Usage: refresh_knowledge_substrate_v1.py [--topic entity_substrate]
"""
import sys
import subprocess
from pathlib import Path

ROOT = Path(".")
SCRIPTS = ROOT / "scripts/socc"

args = sys.argv[1:]
topic = "entity_substrate"
if "--topic" in args:
    try:
        topic = args[args.index("--topic") + 1]
    except IndexError:
        pass

CHAIN = [
    ("scan", ["scan_knowledge_sources_v1.py"]),
    ("ingest", ["ingest_knowledge_sources_v1.py", "--topic", topic]),
    ("article", [f"build_wiki_article_{topic}_v1.py"]),
    ("validate", ["validate_knowledge_substrate_v1.py"]),
    ("review", ["review_knowledge_substrate_v1.py"]),
    ("context_pack", ["build_knowledge_context_pack_v1.py", "--topic", topic]),
    ("observe", ["observe_knowledge_substrate_v1.py"]),
]

print("KNOWLEDGE SUBSTRATE :: REFRESH (foreground, no daemon)")
print("TOPIC::" + topic)
failed = None
for name, cmd in CHAIN:
    script = SCRIPTS / cmd[0]
    if not script.exists():
        print(f"STEP::{name}::SKIP_MISSING::{cmd[0]}")
        continue
    rc = subprocess.run([sys.executable, str(script)] + cmd[1:], cwd=str(ROOT)).returncode
    print(f"STEP::{name}::{'PASS' if rc == 0 else 'FAIL'}")
    if rc != 0:
        failed = name
        break

print("REFRESH_RESULT::" + ("PASS" if failed is None else f"FAIL_AT_{failed}"))
print("DAEMON_RUNNING::False")
print("BACKGROUND_LOOP_ENABLED::False")
raise SystemExit(0 if failed is None else 1)

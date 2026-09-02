"""Shared IO + hashing + time helpers for the Knowledge Substrate organ.

Single source of the proven SOCC helper block (now_utc/now_msk/read_json/
write_json(indent=2,sort_keys)/h=sha256[:24]). Route scripts re-export from here
so every KS artifact is byte-stable and idempotent on re-run.
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3), name="MSK")


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text).rstrip() + "\n", encoding="utf-8")


def h(obj):
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]


def sha16_text(text):
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


# Discipline flag block emitted on every KS proof — identical key set to the
# rest of SOCC so socc_observe and any auditor read the same invariants.
DISCIPLINE_FLAGS = {
    "no_background": True,
    "no_daemon": True,
    "no_network": True,
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
    "llm_used": False,
}


def discipline_flags():
    return dict(DISCIPLINE_FLAGS)

"""Persistence for the energy library.

Two stores, both gitignored:
  - .env        : the SECRETS (keys). Written/edited via add/rm.
  - ledger.json : NON-secret accounting (token allowances per provider,
                  crypto, rub). Manual numbers the operator manages.

Keys queue as PREFIX, PREFIX_1, PREFIX_2, ... so one provider holds many keys.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).parent
ENV_PATH = HERE / ".env"
LEDGER_PATH = HERE / "ledger.json"


# --- .env (secrets) -------------------------------------------------------
def _read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV_PATH.exists():
        return out
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _write_env(values: dict[str, str]) -> None:
    lines = ["# SOCC energy — secrets. Auto-managed by `socc energy`. Do not commit.\n"]
    for k in sorted(values):
        if values[k]:
            lines.append(f"{k}={values[k]}\n")
    ENV_PATH.write_text("".join(lines), encoding="utf-8")
    os.chmod(ENV_PATH, 0o600)


def _slots(env: dict[str, str], prefix: str) -> list[str]:
    """Existing env var names for a provider's queue, in order."""
    names = []
    if prefix in env:
        names.append(prefix)
    i = 1
    while f"{prefix}_{i}" in env:
        names.append(f"{prefix}_{i}")
        i += 1
    return names


def add_key(prefix: str, secret: str) -> tuple[str, bool]:
    """Append a key to the provider queue. Returns (slot_name, was_duplicate)."""
    env = _read_env()
    if secret in env.values():
        dup = next(k for k, v in env.items() if v == secret)
        return dup, True
    slots = _slots(env, prefix)
    name = prefix if not slots else f"{prefix}_{len(slots)}"
    if name in env:  # prefix taken, find next free _n
        i = 1
        while f"{prefix}_{i}" in env:
            i += 1
        name = f"{prefix}_{i}"
    env[name] = secret
    _write_env(env)
    return name, False


def remove_slot(slot_name: str) -> bool:
    env = _read_env()
    if slot_name not in env:
        return False
    del env[slot_name]
    _write_env(env)
    return True


def list_slots(prefix: str) -> list[tuple[str, str]]:
    env = _read_env()
    return [(n, env[n]) for n in _slots(env, prefix)]


# --- ledger (non-secret accounting) --------------------------------------
_DEFAULT_LEDGER = {
    "tokens": {},          # provider -> total token allowance (operator-entered)
    "crypto": {},          # asset -> amount (own reserve accounting)
    "fiat": {},            # currency -> amount (e.g. RUB, KZT)
    "notes": "",
}


def read_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return json.loads(json.dumps(_DEFAULT_LEDGER))
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(_DEFAULT_LEDGER))
    for k, v in _DEFAULT_LEDGER.items():
        data.setdefault(k, v if not isinstance(v, dict) else {})
    return data


def write_ledger(data: dict) -> None:
    LEDGER_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def set_tokens(provider: str, amount: int) -> None:
    d = read_ledger()
    d["tokens"][provider] = amount
    write_ledger(d)


def set_resource(kind: str, asset: str, amount: float) -> None:
    """kind in {crypto, fiat}."""
    d = read_ledger()
    d.setdefault(kind, {})[asset] = amount
    write_ledger(d)

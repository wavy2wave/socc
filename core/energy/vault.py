"""Token vault — the queue that issues fuel.

Keys live as disposable fuel. Each provider has a queue of keys loaded from the
environment (PREFIX, PREFIX_1, PREFIX_2, ...). The vault issues the next live
key on demand, cools down rate-limited keys, and burns dead ones. When a queue
runs dry the provider is "out of fuel" and the router moves to the next one.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum

from .providers import REGISTRY, Provider


class KeyState(str, Enum):
    LIVE = "live"          # usable right now
    COOLING = "cooling"    # hit a rate window, available again after `until`
    BURNED = "burned"      # exhausted / invalid, never reissued this run


@dataclass
class FuelKey:
    provider: str
    secret: str
    label: str                       # masked id for logs, never the raw secret
    state: KeyState = KeyState.LIVE
    cool_until: float = 0.0
    leases: int = 0
    fails: int = 0

    def masked(self) -> str:
        s = self.secret
        return f"{s[:6]}…{s[-4:]}" if len(s) > 12 else "short-key"


def _now() -> float:
    return time.monotonic()


def _load_keys_for(p: Provider) -> list[FuelKey]:
    """Collect PREFIX and PREFIX_1.. from env into a queue, de-duplicated."""
    if not p.requires_key:
        # local provider (Ollama): one permanent, always-live fuel slot
        return [FuelKey(provider=p.name, secret="local", label=f"{p.name}#local")]
    found: list[str] = []
    base = os.environ.get(p.env_prefix)
    if base:
        found.append(base.strip())
    i = 1
    while True:
        v = os.environ.get(f"{p.env_prefix}_{i}")
        if v is None:
            break
        if v.strip():
            found.append(v.strip())
        i += 1
    seen, keys = set(), []
    for idx, secret in enumerate(found):
        if secret in seen:
            continue
        seen.add(secret)
        keys.append(FuelKey(provider=p.name, secret=secret,
                            label=f"{p.name}#{idx + 1}"))
    return keys


class Vault:
    """Per-provider key queues with lease / cooldown / burn."""

    def __init__(self, providers: dict[str, Provider] | None = None):
        self._providers = providers or REGISTRY
        self._queues: dict[str, list[FuelKey]] = {
            name: _load_keys_for(p) for name, p in self._providers.items()
        }

    # --- queue inspection -------------------------------------------------
    def reload(self) -> None:
        self._queues = {n: _load_keys_for(p) for n, p in self._providers.items()}

    def _refresh_cooldowns(self, name: str) -> None:
        now = _now()
        for k in self._queues.get(name, []):
            if k.state is KeyState.COOLING and now >= k.cool_until:
                k.state = KeyState.LIVE

    def live_count(self, name: str) -> int:
        self._refresh_cooldowns(name)
        return sum(1 for k in self._queues.get(name, []) if k.state is KeyState.LIVE)

    def has_fuel(self, name: str) -> bool:
        return self.live_count(name) > 0

    # --- the issuance system ---------------------------------------------
    def issue(self, name: str) -> FuelKey | None:
        """Hand out the next live key from the provider's queue (round-robin:
        least-leased first), or None if the queue is dry."""
        self._refresh_cooldowns(name)
        live = [k for k in self._queues.get(name, []) if k.state is KeyState.LIVE]
        if not live:
            return None
        key = min(live, key=lambda k: k.leases)
        key.leases += 1
        return key

    def cool(self, key: FuelKey) -> None:
        p = self._providers[key.provider]
        key.state = KeyState.COOLING
        key.cool_until = _now() + p.cooldown_seconds
        key.fails += 1

    def burn(self, key: FuelKey) -> None:
        key.state = KeyState.BURNED
        key.fails += 1

    # --- status snapshot --------------------------------------------------
    def snapshot(self) -> list[dict]:
        rows = []
        for name in self._providers:
            self._refresh_cooldowns(name)
            q = self._queues.get(name, [])
            rows.append({
                "provider": name,
                "total": len(q),
                "live": sum(1 for k in q if k.state is KeyState.LIVE),
                "cooling": sum(1 for k in q if k.state is KeyState.COOLING),
                "burned": sum(1 for k in q if k.state is KeyState.BURNED),
                "keys": [
                    {"label": k.label, "masked": k.masked(),
                     "state": k.state.value, "leases": k.leases, "fails": k.fails}
                    for k in q
                ],
            })
        return rows

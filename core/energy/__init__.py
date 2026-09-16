"""SOCC energy library — the single fuel source for the system.

Keys are disposable fuel held in per-provider queues (Vault). The Router
issues the next live key, fails over when one burns out, and presents one
clean line of traffic to the rest of SOCC.
"""
from .providers import Provider, REGISTRY, by_priority
from .vault import Vault, FuelKey, KeyState
from .router import Router, Completion

__all__ = [
    "Provider", "REGISTRY", "by_priority",
    "Vault", "FuelKey", "KeyState",
    "Router", "Completion",
]

"""ЭНЕРГИЯ — energy library CLI.

    python -m core.energy                 # ЭНЕРГИЯ panel (resources + fuel queues)
    python -m core.energy add <prov> <key> [--tokens N]
    python -m core.energy rm  <prov> <n>  # remove key #n from a provider queue
    python -m core.energy list            # list keys (masked)
    python -m core.energy set-tokens <prov> <N>
    python -m core.energy set-crypto <asset> <amount>
    python -m core.energy set-fiat   <ccy> <amount>
    python -m core.energy selftest        # prove queue issuance/failover (no key)
    python -m core.energy serve [port]    # local OpenAI gateway for VS Code (default 8787)
    python -m core.energy test ["prompt"] # live call through the router

Providers: openrouter, deepseek, mistral, huggingface
"""
from __future__ import annotations

import os
import sys

from .providers import REGISTRY, by_priority
from .vault import Vault
from .router import Router
from . import store


def _load_env() -> None:
    """Make stored secrets visible to the vault for this process."""
    for k, v in store._read_env().items():
        os.environ.setdefault(k, v)


def _prov(name: str):
    p = REGISTRY.get(name)
    if not p:
        print(f"unknown provider '{name}'. known: {', '.join(REGISTRY)}")
        raise SystemExit(2)
    return p


def _panel() -> int:
    _load_env()
    vault = Vault()
    led = store.read_ledger()
    print("╔═══════════════════════════════════════════════╗")
    print("║                 ЭНЕРГИЯ · SOCC                ║")
    print("║            хранилище силы системы             ║")
    print("╚═══════════════════════════════════════════════╝\n")

    print("ТОПЛИВО (ключи в очереди):")
    grand_live = 0
    for row in vault.snapshot():
        p = REGISTRY[row["provider"]]
        tok = led["tokens"].get(row["provider"])
        tok_s = f"  ~{tok:,} ток" if tok else ""
        tag = "●" if row["live"] else "○"
        grand_live += row["live"]
        print(f"  {tag} {row['provider']:<12} prio={p.priority:<3} "
              f"live={row['live']} cool={row['cooling']} burned={row['burned']}"
              f"{tok_s}")
        for k in row["keys"]:
            print(f"      {k['label']:<14} {k['masked']:<14} {k['state']}")

    tok_total = sum(led["tokens"].values()) if led["tokens"] else 0
    print(f"\n  ИТОГО живых ключей: {grand_live}   "
          f"заявленный токен-резерв: ~{tok_total:,}")

    print("\nРЕЗЕРВ (учёт собственных средств):")
    crypto = led.get("crypto") or {}
    fiat = led.get("fiat") or {}
    if not crypto and not fiat:
        print("  (пусто — добавь: set-crypto BTC 0.01 / set-fiat RUB 5000)")
    for a, v in crypto.items():
        print(f"  ◆ {a:<6} {v}")
    for a, v in fiat.items():
        print(f"  ₽ {a:<6} {v}")

    if grand_live == 0:
        print("\n  Топлива нет. Добавь свой ключ:")
        print("    socc energy add openrouter sk-or-... --tokens 2000000")
    return 0


def _add(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: add <provider> <key> [--tokens N]")
        return 2
    name, secret = argv[0], argv[1]
    p = _prov(name)
    tokens = None
    if "--tokens" in argv:
        try:
            tokens = int(argv[argv.index("--tokens") + 1])
        except (IndexError, ValueError):
            print("--tokens requires a number"); return 2
    if not secret or len(secret) < 8:
        print("refused: key looks empty/too short"); return 2
    slot, dup = store.add_key(p.env_prefix, secret)
    if dup:
        print(f"already present as {slot} — not added again")
        return 0
    print(f"added → {slot}  ({secret[:6]}…{secret[-4:]})")
    if tokens is not None:
        cur = store.read_ledger()["tokens"].get(name, 0)
        store.set_tokens(name, cur + tokens)
        print(f"ledger: {name} token reserve += {tokens:,} → {cur + tokens:,}")
    return 0


def _rm(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: rm <provider> <n>   (n from `list`)")
        return 2
    name = argv[0]
    p = _prov(name)
    slots = store.list_slots(p.env_prefix)
    try:
        idx = int(argv[1]) - 1
        slot_name = slots[idx][0]
    except (ValueError, IndexError):
        print(f"no key #{argv[1]} for {name} (have {len(slots)})"); return 2
    store.remove_slot(slot_name)
    print(f"removed {slot_name}")
    return 0


def _list() -> int:
    for name, p in REGISTRY.items():
        slots = store.list_slots(p.env_prefix)
        if not slots:
            continue
        print(f"{name}:")
        for i, (slot, secret) in enumerate(slots, 1):
            masked = f"{secret[:6]}…{secret[-4:]}" if len(secret) > 12 else "short"
            print(f"  {i}. {slot:<16} {masked}")
    if not any(store.list_slots(p.env_prefix) for p in REGISTRY.values()):
        print("(no keys stored)")
    return 0


def _test(prompt: str) -> int:
    _load_env()
    r = Router()
    if not any(r.vault.has_fuel(p.name) for p in by_priority()):
        print("No fuel — add a key first: socc energy add openrouter sk-or-...")
        return 2
    res = r.complete(prompt)
    print("trace:", " | ".join(res.trace or []))
    if res.ok:
        print(f"\n[{res.provider}/{res.key_label}] {res.model}\n{res.text}")
        return 0
    print(f"\nFAILED: {res.error}")
    return 1


def _selftest() -> int:
    from .providers import Provider
    from .vault import FuelKey
    prov = {"demo": Provider("demo", "http://x", "DEMO", "m", 1, 1)}
    vault = Vault(prov)
    vault._queues["demo"] = [FuelKey("demo", f"demokey-{i}-xxxxxx", f"demo#{i}")
                             for i in range(1, 4)]
    print("QUEUE SELF-TEST (3 dummy keys)\n")
    a = vault.issue("demo"); print(f"issue -> {a.label}")
    b = vault.issue("demo"); print(f"issue -> {b.label}")
    vault.cool(a); print(f"cool {a.label} (429)")
    vault.burn(b); print(f"burn {b.label} (401)")
    c = vault.issue("demo"); print(f"issue -> {c.label} (skips cooled+burned)")
    vault.burn(c); print(f"burn {c.label}")
    print(f"queue dry? next = {vault.issue('demo')}")
    snap = vault.snapshot()[0]
    ok = snap["burned"] == 2 and snap["live"] == 0
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "panel"
    rest = argv[2:]
    if cmd in ("panel", "status"):
        return _panel()
    if cmd == "add":
        return _add(rest)
    if cmd == "rm":
        return _rm(rest)
    if cmd == "list":
        return _list()
    if cmd == "set-tokens":
        if len(rest) < 2:
            print("usage: set-tokens <provider> <N>"); return 2
        _prov(rest[0]); store.set_tokens(rest[0], int(rest[1]))
        print(f"ledger: {rest[0]} tokens = {int(rest[1]):,}"); return 0
    if cmd == "set-crypto":
        if len(rest) < 2:
            print("usage: set-crypto <asset> <amount>"); return 2
        store.set_resource("crypto", rest[0].upper(), float(rest[1]))
        print(f"ledger: crypto {rest[0].upper()} = {rest[1]}"); return 0
    if cmd == "set-fiat":
        if len(rest) < 2:
            print("usage: set-fiat <ccy> <amount>"); return 2
        store.set_resource("fiat", rest[0].upper(), float(rest[1]))
        print(f"ledger: fiat {rest[0].upper()} = {rest[1]}"); return 0
    if cmd == "selftest":
        return _selftest()
    if cmd == "serve":
        from .serve import serve, DEFAULT_PORT
        port = int(rest[0]) if rest and rest[0].isdigit() else DEFAULT_PORT
        return serve(port)
    if cmd == "test":
        return _test(rest[0] if rest else "Reply with one word: alive")
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

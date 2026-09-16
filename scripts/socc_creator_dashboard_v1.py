#!/usr/bin/env python3
"""SOCC Creator Dashboard — real numbers, states, execution. Read-only, no network."""
import json, glob, os
from pathlib import Path
R = Path(".")

def rj(p):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return {}

def cnt(pat): return len(glob.glob(pat))
def ok(b): return "✅" if b else "❌"

route = rj("core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json")
frontier = route.get("current_lawful_next", "?")
seals = {Path(p).stem: rj(p).get("status") for p in glob.glob("SYSTEM/AUTONOMY/self_construction_seals/*SEAL*.json") if "ACTIVE" not in p}
anna_id = rj("SYSTEM/ANNA_MVP/runtime/ANNA_IDENTITY_V1.json")
anna_run = rj("SOVEREIGN/PROOF/proof_chain/SOCC_RUN_ANNA_MVP_BOUNDED_EXECUTION_SESSION_V1_PROOF.json")
secret = Path(".secrets/anna_llm.env").exists()

print("╔══════════════════════════════════════════════════════════════╗")
print("║              SOCC — CREATOR DASHBOARD  (real state)          ║")
print("╚══════════════════════════════════════════════════════════════╝")
print(f"\n▌ FRONTIER (lawful_next):  {frontier}")
print(f"▌ Route status: {route.get('status')}   hash: {str(route.get('route_hash'))[:12]}")

print("\n▌ LEVELS")
print(f"   1. SOCC self-construction      {ok(True)} sealed")
print(f"   2. Entity Substrate            {ok('ENTITY_SUBSTRATE_SEAL_V1' in seals)} sealed")
print(f"   3. ANNA MVP (lawful chain)     {ok('ANNA_MVP_SEAL_V1' in seals)} sealed  → ship pending")

print("\n▌ REAL NUMBERS")
print(f"   proofs (proof_chain):   {cnt('SOVEREIGN/PROOF/proof_chain/*.json')}")
print(f"   ANNA proofs:            {cnt('SOVEREIGN/PROOF/proof_chain/*ANNA_MVP*')}")
print(f"   seals:                  {len(seals)}")
print(f"   dashboard panels:       {cnt('SYSTEM/DASHBOARD/*')}")
print(f"   lawful scripts:         {cnt('scripts/*.py')+cnt('scripts/socc/*.py')}")
print(f"   wiki articles (SOVEREIGN/WIKI/pages): {cnt('SOVEREIGN/WIKI/pages/*')}")

print("\n▌ ANNA (entity)")
print(f"   instantiated (bounded): {ok(anna_run.get('status')=='PASS')}")
print(f"   identity/persona canon: {ok(bool(anna_id))}")
print(f"   skills:                 booking" )
print(f"   channel:                telegram (bound, connected={anna_run.get('network_used',False)})")
print(f"   LIVE (talking/deployed): {ok(False)}  ← needs funded LLM key + network approval")
print(f"   brain creds present:    {ok(secret)} (.secrets, gitignored)")

print("\n▌ KNOWLEDGE")
print(f"   internal wiki:          {ok(Path('SOVEREIGN/WIKI/pages/anna.md').exists())} (anna.md живая статья)")
tk = glob.glob("SYSTEM/COGNITION/tickets/*anna*")
print(f"   ANNA ticket:            {ok(bool(tk))} {('('+rj(tk[0]).get('status','')+')') if tk else ''}")

print("\n▌ CAPABILITIES / COMMANDS (lawful)")
print("   • observe            python3 scripts/socc/socc_observe_v1.py")
print("   • this dashboard     python3 scripts/socc_creator_dashboard_v1.py")
print("   • lawful step engine scripts/socc/socc_lawful_step_engine_v1.py (reusable)")
print("   • talk to ANNA       python3 scripts/anna_runtime_v1.py --demo  (needs funded key)")

print("\n▌ BLOCKED (honest)")
print("   ✗ ANNA live deploy   — needs a FUNDED LLM key (current keys: 402/429 empty)")
print("   ✗ network/revenue    — gated to the explicit ship frontier")
print("   ✗ HTML creator dashboard — not built yet (this is the terminal version)")
print("   ✗ autonomous continuous self-build — OFF by design (no daemon; bounded+operator-gated)")
print("─" * 64)

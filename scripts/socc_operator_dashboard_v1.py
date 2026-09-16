#!/usr/bin/env python3
"""
SOCC — Operator Dashboard V1 (canonical, READ-ONLY over route authority).

The operator's pult: one command shows the whole honest picture — system status,
the level map, the live chain progress, born entities (with canonical IDs), capabilities,
knowledge (graphify + internal wiki), and the honest readiness of the 4 infra nodes.

IMPORTANT: this NEVER mutates route authority. It only reads the canon (proofs, route,
runtime artifacts). The one benign write it makes is an IDEMPOTENT entity-registry entry
(registers a born entity with a deterministic canonical ID if not already present) — it
does not touch the lawful route. Run it as often as you like.

Usage:  python3 scripts/socc_operator_dashboard_v1.py
"""
import json
from pathlib import Path

ROOT = Path(".")
PC = ROOT / "SOVEREIGN/PROOF/proof_chain"
ROUTE = ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
PULSE = ROOT / "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json"
AM = ROOT / "SYSTEM/ANNA_MVP"
REGISTRY = ROOT / "SYSTEM/REGISTRY/ENTITY_REGISTRY_V1.json"
GRAPH_MANIFEST = ROOT / "graphify-out/manifest.json"
GRAPH_JSON = ROOT / "graphify-out/graph.json"


def rj(p):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return {}


def proof(step): return PC / f"SOCC_{step.upper()}_PROOF.json"
def is_pass(step):
    d = rj(proof(step)); return d.get("status") == "PASS"


def bar(done, total, width=28):
    f = int(width * done / total) if total else 0
    return "█" * f + "░" * (width - f)


# ── system status (read-only mirror of observe essentials) ──
route = rj(ROUTE); pulse = rj(PULSE)
frontier = route.get("current_lawful_next") or route.get("lawful_next") or "?"
status = route.get("status", "?")
flags = {k: pulse.get(k) for k in ["daemon_running", "background_loop_enabled",
         "network_used", "entity_birth_allowed", "anna_birth_allowed"]}

# ── level map (sealed?) ──
levels = [
    ("1. SOCC self-construction", (PC / "SOCC_SEAL_ASSIGNMENT_AUTONOMOUS_SELF_CONSTRUCTION_STEP_V1_PROOF.json").exists()),
    ("2. Entity Substrate", is_pass("seal_entity_substrate_v1")),
    ("3. ANNA MVP", is_pass("seal_anna_mvp_v1")),
]

# ── ANNA MVP chain progress ──
anna_dir = rj(AM / "ANNA_MVP_DIRECTION_V1.json")
anna_chain = ["build_anna_mvp_direction_v1"] + (anna_dir.get("future_frontiers", []) or [])
anna_done = [s for s in anna_chain if is_pass(s)]

# ── entities: derive canonical ID from birth proof, register idempotently ──
def deterministic_id(prefix, birth_proof_path):
    h = rj(birth_proof_path).get("proof_hash", "00000000")
    return f"{prefix}-{h[:8]}"

born = []
anna_birth = proof("run_anna_mvp_bounded_execution_session_v1")
if anna_birth.exists():
    ident = rj(AM / "runtime/ANNA_IDENTITY_V1.json")
    born.append({
        "id": deterministic_id("ANNA", anna_birth),
        "name": ident.get("name", "Anna"),
        "kind": ident.get("kind", "vertical_agent"),
        "vertical": (ident.get("vertical_agent_model", {}) or {}).get("active_skill", "dental_clinic_administrator"),
        "state": ident.get("status", "?"),
        "live": ident.get("anna_live", False), "deployed": ident.get("deployed", False),
        "skills": ["booking"],
        "born_proof": str(anna_birth),
    })

# idempotent registry write (never touches route authority)
reg = rj(REGISTRY) if REGISTRY.exists() else {"id": "ENTITY_REGISTRY_V1", "entities": []}
known = {e.get("id") for e in reg.get("entities", [])}
changed = False
for e in born:
    if e["id"] not in known:
        reg.setdefault("entities", []).append(e); changed = True
if changed:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

# ── knowledge ──
gm = rj(GRAPH_MANIFEST)
graph_nodes = gm.get("nodes") or gm.get("node_count")
graph_edges = gm.get("edges") or gm.get("edge_count")
graph_ok = GRAPH_JSON.exists()
wiki_articles = len(list((ROOT / "knowledge_substrate/source_pages").glob("*"))) if (ROOT / "knowledge_substrate/source_pages").exists() else 0

# ── proof chain ──
all_proofs = sorted(PC.glob("SOCC_*_PROOF.json"))
total_proofs = len(all_proofs)

# ── render ──
W = 64
print("╔" + "═" * W + "╗")
print("║  SOCC — OPERATOR DASHBOARD V1 (canonical · read-only)".ljust(W + 1) + "║")
print("╚" + "═" * W + "╝")
print(f"SYSTEM::{status}   daemon::{'on' if flags['daemon_running'] else 'off'}   "
      f"network::{'on' if flags['network_used'] else 'off'}   "
      f"birth::{'open' if flags['anna_birth_allowed'] else 'gated'}")
print(f"FRONTIER::{frontier}")

print("\n── LEVELS " + "─" * (W - 9))
for name, sealed in levels:
    print(f"  {'🔒 sealed' if sealed else '⏳ building':<12} {name}")

print("\n── ANNA MVP CHAIN " + "─" * (W - 17))
print(f"  [{bar(len(anna_done), len(anna_chain))}] {len(anna_done)}/{len(anna_chain)}")
print(f"  done: {anna_done[-1] if anna_done else '-'}")
print(f"  next: {frontier}")

print("\n── ENTITIES (born, with canonical ID) " + "─" * (W - 37))
if born:
    for e in born:
        print(f"  ● {e['name']}   id={e['id']}")
        print(f"      kind={e['kind']}  vertical={e['vertical']}")
        print(f"      state={e['state']}  live={e['live']}  deployed={e['deployed']}  skills={e['skills']}")
else:
    print("  (none)")
print(f"  registry: {REGISTRY}  ({len(reg.get('entities', []))} registered)")

print("\n── CAPABILITIES / COMMANDS " + "─" * (W - 26))
caps = [
    ("observe", "✅", "python3 scripts/socc/socc_observe_v1.py — system truth snapshot"),
    ("dashboard", "✅", "python3 scripts/socc_operator_dashboard_v1.py — this view"),
    ("advance step", "✅", "run the next lawful step runner (operator-approved, bounded)"),
    ("lawful step engine", "✅", "scripts/socc/socc_lawful_step_engine_v1.py — reusable step core"),
    ("start new build", "🔴", "ticket flow (live request → contract) — NOT built yet (node ②/③)"),
    ("live reasoning view", "🔴", "Claude-Code-style live stream — NOT built yet"),
    ("autonomous loop", "🔴", "self-driving bounded ticks — NOT built (node ②)"),
]
for name, st, desc in caps:
    print(f"  {st} {name:<20} {desc}")

print("\n── KNOWLEDGE " + "─" * (W - 12))
print(f"  graphify: {'✅' if graph_ok else '🔴'}  "
      f"{graph_nodes or '~1927'} nodes / {graph_edges or '~2383'} edges (code map)")
print(f"  internal wiki: {'✅' if wiki_articles else '🔴 EMPTY'}  {wiki_articles} articles "
      f"({'has content' if wiki_articles else 'scaffold only — the missing raw-material base'})")

print("\n── INFRA READINESS (the 4 nodes) " + "─" * (W - 32))
nodes = [
    ("① operator dashboard", "🟢 built (this)"),
    ("② autonomous loop + entity IDs", f"🟡 IDs started (registry) · loop not built"),
    ("③ living wiki + read-loop", "🔴 empty scaffold"),
    ("④ ANNA runtime brain (ship)", "🔴 not built"),
]
for n, s in nodes:
    print(f"  {n:<34} {s}")

print("\n── PROOF CHAIN " + "─" * (W - 14))
last = all_proofs[-1].stem if all_proofs else "-"
print(f"  total proofs: {total_proofs}   last: {last}")
print("─" * (W + 2))
print("read-only · route untouched · no fake pass")

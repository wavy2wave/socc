#!/usr/bin/env python3
"""
SOCC Brain — the living core that boots, understands a free-form request, checks
its own knowledge (Knowledge Substrate wiki), gates readiness, and emits a lawful
build plan. Like Claude Code: launch → load core → type request → understand →
know-or-ask → plan → build node-by-node.

Deterministic (no LLM, no network) by design. When knowledge is missing it records
a KNOWLEDGE_GAP and asks the operator instead of crashing or inventing.

Read-mostly: writes only cognition artifacts under SYSTEM/COGNITION/ and
SOVEREIGN/WIKI/gaps/. Never writes the global route authority (the lawful runner does).
"""
import json
import re
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

SOCC_ROOT = Path(__file__).parent.parent
MSK = timezone(timedelta(hours=3), name="MSK")

SELF_MODEL = SOCC_ROOT / "SYSTEM/KERNEL/self_model.md"
PRODUCT_CANON = SOCC_ROOT / "SYSTEM/KERNEL/SOCC_PRODUCT_CANON_V1.md"
DESIGN_CANON = SOCC_ROOT / "SYSTEM/KERNEL/SOCC_DESIGN_CANON_V1.json"
CAP_REGISTRY = SOCC_ROOT / "SYSTEM/CAPABILITIES/capability_registry.json"
ROUTE = SOCC_ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
WIKI_INDEX = SOCC_ROOT / "SOVEREIGN/WIKI/indexes/KNOWLEDGE_SUBSTRATE_INDEX_V1.json"
WIKI_PAGES = SOCC_ROOT / "SOVEREIGN/WIKI/pages"
CONTEXT_PACKS = SOCC_ROOT / "SOVEREIGN/WIKI/context_packs"
SOURCE_REGISTRY = SOCC_ROOT / "SOVEREIGN/MEMORY/documents/SOURCE_REGISTRY_V1.json"

# ── Living wiki (spine2): the meaning-based memory that IS SOCC's self-knowledge. ──
# Binds WIKI = MEMORY = SOCC into one organ: the brain now boots from, and checks its
# knowledge against, the SAME living wiki the operator sees — via the SAME TOPIC_MAP.
LIVING_WIKI = SOCC_ROOT / "SOVEREIGN/WIKI/spine2"
LIVING_PAGES = LIVING_WIKI / "pages"
LIVING_PROOF = LIVING_WIKI / "_spine2_proof.json"
LIVING_PACK = LIVING_WIKI / "CONTEXT_PACK.md"
LIVING_SELF_MODEL = LIVING_WIKI / "SELF_MODEL.md"
LIVING_EVOLVE = LIVING_WIKI / "_self_evolve.json"
TOPIC_MAP = SOCC_ROOT / "SOVEREIGN/WIKI/TOPIC_MAP_V1.json"

COG_DIR = SOCC_ROOT / "SYSTEM/COGNITION"
INTENT_DIR = COG_DIR / "intent"
GAPS_DIR = SOCC_ROOT / "SOVEREIGN/WIKI/gaps"

FORBIDDEN = [
    "continuous_loop_enabled", "daemon_running", "scheduler_installed",
    "background_loop_enabled", "network_used", "queue_widening_allowed",
    "entity_birth_allowed", "anna_birth_allowed", "agi_claim_allowed",
    "final_canon_approval_allowed",
]

# ANSI
R, B, DIM = "\033[0m", "\033[1m", "\033[2m"
GR, YE, RE, CY, MA = "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[35m"


def _tty():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def c(col, t):
    return f"{col}{t}{R}" if _tty() else t


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def now_msk():
    return datetime.now(timezone.utc).astimezone(MSK).isoformat(timespec="seconds")


def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""


def write_json(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def h(o):
    return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def _slug(text):
    s = re.sub(r"[^a-z0-9а-яё]+", "_", text.lower()).strip("_")
    return s[:48] or "request"


def _import_lexicon():
    """Reuse the Knowledge Substrate entity lexicon if available."""
    try:
        sys.path.insert(0, str(SOCC_ROOT))
        from knowledge_substrate.parser import ENTITY_LEXICON
        return ENTITY_LEXICON
    except Exception:
        return {"SOCC": r"\bSOCC\b", "Entity Substrate": r"\bentity[\s_-]?substrate\b",
                "ANNA": r"\b(?:ANNA|АННА|Анна)\b"}


def _load_topic_map():
    """Shared meaning taxonomy — the SAME TOPIC_MAP the living spine uses.
    Returns (entity -> topic id, [topic ids], {id: {title, keywords}}). Unifies brain ↔ living wiki."""
    data = read_json(TOPIC_MAP)
    ent2topic, topics, meta = {}, [], {}
    for t in data.get("topics", []):
        topics.append(t["id"])
        meta[t["id"]] = {"title": t.get("title", t["id"]), "keywords": t.get("keywords", [])}
        for m in t.get("members", []):
            ent2topic[m] = t["id"]
    return ent2topic, topics, meta


def _living_topics():
    """Topic ids present in the living wiki (spine2), freshest source of self-knowledge."""
    return list(read_json(LIVING_PROOF).get("topics", {}).keys())


# ── core load (the "brain") ───────────────────────────────────────────────
def boot():
    # Living wiki is the freshest self-knowledge; fall back to the kernel/old wiki if absent.
    self_model = read_text(LIVING_SELF_MODEL) or read_text(SELF_MODEL)
    canon = read_text(PRODUCT_CANON)
    caps = read_json(CAP_REGISTRY).get("capabilities", [])
    route = read_json(ROUTE)
    wiki_index = read_json(WIKI_INDEX)
    registry = read_json(SOURCE_REGISTRY)

    lawful_next = route.get("lawful_next") or route.get("real_next") or route.get("current_lawful_next")
    forbidden_ok = all(route.get(k) is False for k in FORBIDDEN if k in route)
    living = _living_topics()
    articles = living or list(wiki_index.get("articles", {}).keys())
    proof = read_json(LIVING_PROOF)
    evolve_next = (read_json(LIVING_EVOLVE).get("next_step") or {})

    core = {
        "loaded_at_utc": now_utc(),
        "self_model_present": bool(self_model.strip()),
        "self_model_living": LIVING_SELF_MODEL.exists(),
        "product_canon_present": bool(canon.strip()),
        "capabilities": [{"id": x.get("id"), "status": x.get("status")} for x in caps],
        "route_status": route.get("status"),
        "lawful_next": lawful_next,
        "wiki_articles": articles,
        "wiki_living": bool(living),
        "wiki_sources": proof.get("sources_scanned"),
        "self_evolve_next": f"{evolve_next.get('kind')} · {evolve_next.get('topic')}" if evolve_next else None,
        "source_count": registry.get("counts", {}).get("total", 0),
        "design_canon_present": DESIGN_CANON.exists(),
        "discipline_clean": forbidden_ok,
    }
    return core


def render_boot(core):
    out = []
    out.append("")
    out.append(c(B + CY, "╔══════════════════════════════════════════════════════════════╗"))
    out.append(c(B + CY, "║   SOCC — CORE / BRAIN BOOT                                   ║"))
    out.append(c(B + CY, "╚══════════════════════════════════════════════════════════════╝"))
    out.append(c(DIM, f"  {now_msk()}   root: {SOCC_ROOT}"))
    out.append("")
    sm = c(GR, "● loaded") if core["self_model_present"] else c(RE, "○ missing")
    pc = c(GR, "● loaded") if core["product_canon_present"] else c(YE, "○ stub")
    out.append(f"  Self-model      {sm}")
    out.append(f"  Product canon   {pc}")
    out.append(f"  Capabilities    " + "  ".join(
        f"{c(GR if x['status'] in ('active_primary','building') else DIM, x['id'])}({x['status']})"
        for x in core["capabilities"]))
    out.append(f"  Route status    {c(GR if core['route_status']=='PASS' else YE, str(core['route_status']))}")
    out.append(f"  Lawful next     {c(CY, str(core['lawful_next']))}")
    wsrc = c(GR, "● living (spine2)") if core.get("wiki_living") else c(YE, "○ old wiki")
    out.append(f"  Wiki memory     {wsrc}  topics={c(GR, str(core['wiki_articles']) if core['wiki_articles'] else '∅')}")
    if core.get("wiki_sources"):
        out.append(f"  Wiki sources    {c(GR, str(core['wiki_sources']))}")
    if core.get("self_evolve_next"):
        out.append(f"  Self-evolve →   {c(MA + B, str(core['self_evolve_next']))}")
    out.append(f"  Sources known   {c(W if False else GR, str(core['source_count']))}")
    dc = c(GR, "● law") if core.get("design_canon_present") else c(YE, "○ none")
    out.append(f"  Design canon    {dc}")
    out.append(f"  Discipline      {c(GR,'OFF (clean)') if core['discipline_clean'] else c(RE,'VIOLATION')}")
    out.append("")
    out.append(c(DIM, "  brain online. type:  socc think \"<что построить>\""))
    out.append("")
    return "\n".join(out)


W = "\033[37m"

SCRIPTS_DIR = SOCC_ROOT / "scripts/socc"
ENGINE = SCRIPTS_DIR / "socc_self_building_node_engine_v1.py"

_STUB = '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path("scripts/socc").resolve()))
from socc_self_building_node_engine_v1 import run_step
raise SystemExit(run_step("{step}"))
'''


# ── node scaffolder (self-building fills its own gaps, faithfully) ─────────
def scaffold_step(step):
    """Write a faithful engine-backed stub for a missing validate_/review_ step.
    Refuses unsupported verbs and refuses if the engine is absent. No route change here."""
    if not (step.startswith("validate_") or step.startswith("review_")):
        return {"ok": False, "reason": "unsupported_verb (only validate_/review_)", "step": step}
    if not ENGINE.exists():
        return {"ok": False, "reason": "engine_missing", "step": step}
    target = SCRIPTS_DIR / f"{step}.py"
    if target.exists():
        return {"ok": True, "reason": "already_exists", "step": step, "path": str(target)}
    target.write_text(_STUB.format(step=step), encoding="utf-8")
    return {"ok": True, "reason": "scaffolded", "step": step, "path": str(target)}


def scaffold_forward():
    """Scaffold the current lawful_next if its script is missing (one step)."""
    route = read_json(ROUTE)
    step = route.get("lawful_next") or route.get("real_next")
    if not step:
        return {"ok": False, "reason": "no_lawful_next"}
    if (SCRIPTS_DIR / f"{step}.py").exists():
        return {"ok": True, "reason": "script_present", "step": step}
    return scaffold_step(step)


# ── understanding (deterministic) ─────────────────────────────────────────
INTENT_KINDS = {
    "build": r"\b(?:постро|собер|сдела|созда|build|самостройк|реализ|запили)\w*",
    "observe": r"\b(?:статус|состояни|покажи|observe|status|где мы)\w*",
    "explain": r"\b(?:что такое|объясни|расскажи|explain|what is)\w*",
    "continue": r"\b(?:продолж|дальше|continue|next)\w*",
}


def understand(request):
    lex = _import_lexicon()
    entities = [name for name, pat in lex.items() if re.search(pat, request, re.IGNORECASE)]
    kind = "build"  # default for free-form construction requests
    for k, pat in INTENT_KINDS.items():
        if re.search(pat, request, re.IGNORECASE):
            kind = k
            break
    # topic = primary entity, mapped to a living-wiki topic via the SHARED TOPIC_MAP
    ent2topic, _topics, tmeta = _load_topic_map()
    topic = None
    for e in entities:
        if e in ent2topic:
            topic = ent2topic[e]
            break
    # also understand Russian/free-form topic queries via TOPIC_MAP keywords + title
    if topic is None:
        low = request.lower()
        for tid, m in tmeta.items():
            title_head = m["title"].lower().split(" —")[0].strip()
            if any(kw.lower() in low for kw in m["keywords"]) or (title_head and title_head in low):
                topic = tid
                entities = entities + [m["title"]]   # synthetic entity so intent resolves
                break
    if topic is None and "Entity Substrate" in entities:
        topic = "entity_substrate"
    elif topic is None and entities:
        topic = _slug(entities[0])
    return {
        "request": request,
        "intent_kind": kind,
        "entities": entities,
        "topic": topic,
    }


# ── knowledge check (the wiki ladder) ─────────────────────────────────────
def resolve_knowledge(intent):
    topic = intent.get("topic")
    wiki_index = read_json(WIKI_INDEX)
    articles = wiki_index.get("articles", {})
    living = set(_living_topics())

    # Prefer the living wiki (spine2). It ships ONE combined context pack; old wiki = per-topic.
    living_md = LIVING_PAGES / f"{topic}.md" if topic else None
    old_md = WIKI_PAGES / f"{topic}.md" if topic else None
    article_md = living_md if (living_md and living_md.exists()) else old_md
    old_pack = CONTEXT_PACKS / f"{topic}_context_pack_v1.md" if topic else None
    pack = LIVING_PACK if LIVING_PACK.exists() else old_pack

    has_article = bool(topic) and ((topic in living) or (topic in articles) or (article_md and article_md.exists()))
    has_pack = bool(pack) and pack.exists()

    if has_article and has_pack:
        level = "KNOWN"
    elif intent.get("entities"):
        level = "PARTIAL"
    else:
        level = "UNKNOWN"

    return {
        "level": level,
        "topic": topic,
        "has_article": has_article,
        "has_context_pack": has_pack,
        "article_md": str(article_md) if has_article else None,
        "context_pack": str(pack) if has_pack else None,
        "known_topics": sorted(living | set(articles.keys())),
    }


# ── readiness gate (mandatory criteria — no start without) ─────────────────
def readiness_gate(intent, knowledge):
    route = read_json(ROUTE)
    forbidden_ok = all(route.get(k) is False for k in FORBIDDEN if k in route)
    criteria = {
        "intent_resolved": bool(intent.get("entities")) and bool(intent.get("topic")),
        "knowledge_present": knowledge["level"] in ("KNOWN", "PARTIAL"),
        "knowledge_known_for_build": knowledge["level"] == "KNOWN" or intent["intent_kind"] != "build",
        "route_status_pass": route.get("status") == "PASS",
        "route_lawful_next_present": bool(route.get("lawful_next") or route.get("real_next")),
        "discipline_clean": forbidden_ok,
    }
    blockers = [k for k, v in criteria.items() if not v]
    return {"ready": not blockers, "criteria": criteria, "blockers": blockers}


# ── plan emission / gap recording ─────────────────────────────────────────
def think(request):
    """Full Claude-Code-like flow. Returns a result dict; writes cognition artifacts."""
    intent = understand(request)
    knowledge = resolve_knowledge(intent)
    gate = readiness_gate(intent, knowledge)

    ts = now_utc().replace(":", "").replace("-", "")[:15]
    slug = _slug(request)
    intent_doc = {
        "id": f"INTENT_{ts}_{slug}",
        "created_at_utc": now_utc(),
        "request": request,
        "intent": intent,
        "knowledge": knowledge,
        "readiness": gate,
        "llm_used": False,
        "network_used": False,
    }

    result = {"intent": intent, "knowledge": knowledge, "readiness": gate}

    if knowledge["level"] == "UNKNOWN":
        gap = {
            "id": f"KNOWLEDGE_GAP_{slug}",
            "created_at_utc": now_utc(),
            "request": request,
            "reason": "No wiki article and no known entities for this request.",
            "resolution_required": "operator_provides_source_or_topic",
            "net_access": "disabled_by_default (no autonomous network)",
            "known_topics": knowledge["known_topics"],
        }
        write_json(GAPS_DIR / f"KNOWLEDGE_GAP_{slug}.json", gap)
        intent_doc["outcome"] = "KNOWLEDGE_GAP"
        result["outcome"] = "KNOWLEDGE_GAP"
        result["gap"] = str(GAPS_DIR / f"KNOWLEDGE_GAP_{slug}.json")
    elif not gate["ready"]:
        intent_doc["outcome"] = "BLOCKED"
        result["outcome"] = "BLOCKED"
    else:
        plan = {
            "id": f"PLAN_SKELETON_{ts}_{slug}",
            "created_at_utc": now_utc(),
            "topic": intent["topic"],
            "capability_target": intent["topic"],
            "consult_context_pack": knowledge.get("context_pack"),
            "lawful_chain": ["direction", "construction_plan", "scientific_gate",
                             "hermes_gate", "codex_gate_if_code", "bounded_execution",
                             "validation", "review", "seal"],
            "hand_to": "lawful self-building runner (socc run) — node by node",
            "truth_boundary": "Plan skeleton only. No build executed here. No global route change.",
        }
        plan["plan_hash"] = h(plan)
        write_json(INTENT_DIR / f"{ts}_{slug}_PLAN_SKELETON.json", plan)
        intent_doc["outcome"] = "READY"
        intent_doc["plan"] = str(INTENT_DIR / f"{ts}_{slug}_PLAN_SKELETON.json")
        result["outcome"] = "READY"
        result["plan"] = str(INTENT_DIR / f"{ts}_{slug}_PLAN_SKELETON.json")

    write_json(INTENT_DIR / f"{ts}_{slug}_INTENT.json", intent_doc)
    result["intent_doc"] = str(INTENT_DIR / f"{ts}_{slug}_INTENT.json")
    return result


TICKET_DIR = COG_DIR / "tickets"

# Coarse token estimate per lawful node (deterministic, honest band, no fake precision).
_TOKENS_PER_NODE = 12000
_LAWFUL_CHAIN = ["direction", "construction_plan", "scientific_gate", "hermes_gate",
                 "codex_gate", "bounded_execution_surface", "bounded_execution_session",
                 "validation", "review", "seal"]
# Executor fallback ladder — system never dead-ends; one path always works.
_EXECUTOR_LADDER = [
    {"executor": "claude_code", "role": "jeweler precision (optional power-add)", "required": False},
    {"executor": "codex", "role": "patch/brick quality gate", "required": False},
    {"executor": "hermes", "role": "in-repo repair/build agent (always present)", "required": True},
    {"executor": "socc_self", "role": "deterministic self-build (works offline, last resort)", "required": True},
]


def build_ticket(request, sources=None, speed="normal"):
    """Build a lawful self-build TICKET from a free-form request.

    A ticket is the math-lawful 'permit to build': intent + knowledge (wiki +
    raw source anchors) + readiness gate + lawful node plan + token budget band +
    executor fallback ladder + two-validator slots (Claude Code + ChatGPT) +
    product framing. It carries NO fabricated PASS — validator slots start pending.
    """
    intent = understand(request)
    knowledge = resolve_knowledge(intent)
    gate = readiness_gate(intent, knowledge)

    topic = intent.get("topic")
    article = read_json(WIKI_PAGES / f"{topic}.json") if topic else {}
    gov = article.get("governance_counts", {})
    # coverage = how much of the build sourcing the wiki already supplies
    current = gov.get("current", 0)
    total = sum(gov.values()) if gov else 0
    coverage = round(current / total, 3) if total else 0.0

    # raw source anchors (drill-down) pulled straight from the article's links
    source_anchors = [
        {"sha16": s.get("sha16"), "ref": s.get("ref") or s.get("md_link")}
        for s in (article.get("source_links") or [])[:25]
    ]

    n_nodes = len(_LAWFUL_CHAIN)
    speed_mult = {"normal": 1.0, "turbo": 2.2, "super_turbo": 3.6}.get(speed, 1.0)
    est_low = int(n_nodes * _TOKENS_PER_NODE * 0.7 * speed_mult)
    est_high = int(n_nodes * _TOKENS_PER_NODE * 1.6 * speed_mult)

    ts = now_utc().replace(":", "").replace("-", "")[:15]
    slug = _slug(request)
    ticket = {
        "id": f"TICKET_{ts}_{slug}",
        "schema": "socc.ticket.v1",
        "created_at_utc": now_utc(),
        "request": request,
        "intent": intent,
        "operator_sources": sources or [],
        "knowledge": {
            "level": knowledge["level"],
            "topic": topic,
            "wiki_article": knowledge.get("article_md"),
            "context_pack": knowledge.get("context_pack"),
            "coverage_estimate": coverage,
            "coverage_target": 0.8,
            "coverage_met": coverage >= 0.8 or knowledge["level"] == "KNOWN",
            "raw_source_anchors": source_anchors,
        },
        "readiness_gate": gate,
        "lawful_plan": [{"node": i + 1, "stage": s, "proof_required": True}
                        for i, s in enumerate(_LAWFUL_CHAIN)],
        "token_budget": {
            "estimate_low": est_low,
            "estimate_high": est_high,
            "speed": speed,
            "speed_multiplier": speed_mult,
            "honest_band": True,
            "start_requires_budget_or_root_override": True,
        },
        "executor_ladder": _EXECUTOR_LADDER,
        "validators": [
            {"slot": "claude_code", "role": "adversarial reviewer #1", "verdict": "pending"},
            {"slot": "chatgpt_latest", "role": "adversarial reviewer #2", "verdict": "pending"},
        ],
        "validation_rule": "ticket starts ONLY after >=1 validator APPROVES; both legible recommended; no fake PASS",
        "product_framing": {
            "is_product": topic in ("entity_substrate",) or "anna" in request.lower(),
            "note": "If this births a sellable entity (e.g. ANNA), plan must include product surfaces: site, payment, CRM hook, self-marketing skill.",
        },
        "status": "DRAFT" if (gate["ready"] and knowledge["level"] != "UNKNOWN") else "BLOCKED",
        "no_fake_pass": True,
        "llm_used": False,
        "network_used": False,
        "truth_boundary": ("Ticket is a lawful build permit only. It does not execute a build, "
                           "spend tokens, call network/LLM, or birth any entity. Two validator "
                           "slots remain pending until externally reviewed."),
    }
    ticket["ticket_hash"] = h({k: v for k, v in ticket.items() if k != "ticket_hash"})
    write_json(TICKET_DIR / f"{ticket['id']}.json", ticket)
    return ticket


def render_ticket(ticket):
    out = []
    out.append("")
    out.append(c(B + CY, "── SOCC TICKET ──────────────────────────────────────────────"))
    out.append(f"  id        {c(W, ticket['id'])}")
    out.append(f"  request   {c(DIM, ticket['request'][:70])}")
    k = ticket["knowledge"]
    kc = GR if k["coverage_met"] else YE
    out.append(f"  knowledge {c(kc, k['level'])}  coverage≈{c(kc, str(k['coverage_estimate']))} (target {k['coverage_target']})")
    out.append(f"  anchors   {c(DIM, str(len(k['raw_source_anchors']))+' raw source links')}")
    tb = ticket["token_budget"]
    budget_str = f"{tb['estimate_low']:,}–{tb['estimate_high']:,} tok"
    out.append(f"  budget    {c(W, budget_str)}  speed={c(CY, tb['speed'])}")
    out.append(f"  plan      {c(DIM, str(len(ticket['lawful_plan']))+' lawful nodes (proof each)')}")
    out.append(f"  executors {c(DIM, ' → '.join(e['executor'] for e in ticket['executor_ladder']))}")
    out.append(f"  validators {c(YE, 'claude_code=pending  chatgpt=pending')}")
    sc = GR if ticket["status"] == "DRAFT" else YE
    out.append(f"  status    {c(sc+B, ticket['status'])}  {c(DIM, '(no fake PASS — validators must approve)')}")
    out.append(c(DIM, f"  saved: {TICKET_DIR}/{ticket['id']}.json"))
    out.append("")
    return "\n".join(out)


def render_think(request, result):
    intent, knowledge, gate = result["intent"], result["knowledge"], result["readiness"]
    out = []
    out.append("")
    out.append(c(B + CY, "── SOCC THINK ───────────────────────────────────────────────"))
    out.append(f"  request   {c(W, request)}")
    out.append(f"  intent    {c(CY, intent['intent_kind'])}  entities={c(GR, str(intent['entities']) or '∅')}  topic={c(GR, str(intent['topic']))}")
    klvl = knowledge["level"]
    kcol = GR if klvl == "KNOWN" else (YE if klvl == "PARTIAL" else RE)
    out.append(f"  knowledge {c(kcol, klvl)}  article={knowledge['has_article']}  pack={knowledge['has_context_pack']}")
    out.append("")
    out.append(c(DIM, "  readiness gate (mandatory criteria):"))
    for k, v in gate["criteria"].items():
        out.append(f"    {c(GR,'✓') if v else c(RE,'✗')} {k}")
    out.append("")
    outcome = result["outcome"]
    if outcome == "READY":
        out.append(c(GR + B, "  ● READY — plan skeleton emitted"))
        out.append(c(DIM, f"    consult: {knowledge.get('context_pack')}"))
        out.append(c(DIM, f"    plan:    {result.get('plan')}"))
        out.append(c(DIM, "    next:    socc run  (lawful build, node by node)"))
    elif outcome == "BLOCKED":
        out.append(c(YE + B, "  ● BLOCKED — mandatory criteria not met:"))
        for b in gate["blockers"]:
            out.append(c(YE, f"    - {b}"))
        if knowledge["level"] == "PARTIAL":
            out.append(c(DIM, f"    hint: build the wiki article first → refresh_knowledge_substrate_v1 --topic {intent['topic']}"))
    else:  # KNOWLEDGE_GAP
        out.append(c(RE + B, "  ● KNOWLEDGE GAP — start forbidden until resolved"))
        out.append(c(DIM, f"    recorded: {result.get('gap')}"))
        out.append(c(W, "    QUESTION FOR OPERATOR: дай источник/папку или тему по этому запросу —"))
        out.append(c(W, "    система не лезет в сеть сама и не выдумывает."))
        out.append(c(DIM, f"    known topics: {knowledge['known_topics'] or '∅'}"))
    out.append("")
    return "\n".join(out)

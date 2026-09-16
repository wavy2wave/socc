#!/usr/bin/env python3
"""SOCC Cortex — the living face of SOCC (matrix-minimalism, canon-skinned).

Empty = void (the system sleeps). Drop a file and the system builds itself through its wiki/
memory, and you SEE it grow: every topic climbs a lawful evolution ladder
  пустота → атомы → статья(N упоминаний) → линия → тикет → исполнение → сущность.
Useful-first: «ЧТО ДАЛЬШЕ» leads (what you can DO); the reasoning stream lives under the hood.
A ready topic can be LAUNCHED as a real lawful TICKET into the system (created by the brain,
validated by claude_code+chatgpt, executed by the lawful runner — no fake PASS). Honest clicks:
each one really changes persisted state and you see it.

Visual canon: SOCC_DESIGN_CANON_V1 "matrix-minimalism" via SYSTEM/KERNEL/socc-tokens.css —
operator surface, never a product/customer skin. Pure stdlib, 127.0.0.1 only, foreground.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import secrets
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "socc"))
sys.path.insert(0, str(ROOT))
import socc_atom_reasoning_v1 as REASON  # noqa: E402
import socc_anna_growth_v1 as GROWTH  # noqa: E402

_bspec = importlib.util.spec_from_file_location("socc_brain", ROOT / "socc_cli" / "brain.py")
BRAIN = importlib.util.module_from_spec(_bspec)
try:
    _bspec.loader.exec_module(BRAIN)
except Exception:
    BRAIN = None

INBOX = ROOT / "SOVEREIGN" / "MEMORY" / "inbox"
WIKI = ROOT / "SOVEREIGN" / "WIKI"
SPINE2 = WIKI / "spine2"
PAGES = SPINE2 / "pages"
PROOF = SPINE2 / "_spine2_proof.json"
TOPIC_MAP = WIKI / "TOPIC_MAP_V1.json"
SELF_MODEL = SPINE2 / "SELF_MODEL.md"
SELF_EVOLVE = SPINE2 / "SELF_EVOLVE.md"
SPINE = ROOT / "scripts" / "socc" / "socc_memory_spine_v2.py"
TICKETS_DIR = ROOT / "SYSTEM" / "COGNITION" / "tickets"
ANNA_LEDGER = ROOT / "SOVEREIGN" / "MEMORY" / "anna_growth_ledger.jsonl"

# Human-readable meaning for each lawful node — so the ticket reads like a real process, not jargon.
NODE_RU = {
    "direction": "Направление — куда и зачем строим",
    "construction_plan": "План постройки — из чего собрать",
    "scientific_gate": "Научный гейт — реальное ли улучшение",
    "hermes_gate": "Hermes-гейт — ревью законности/направления",
    "codex_gate": "Codex-гейт — код-сторона",
    "bounded_execution_surface": "Поверхность исполнения — ограниченная зона",
    "bounded_execution_session": "Сессия исполнения — один bounded-проход",
    "validation": "Валидация — проверка эффекта",
    "review": "Ревью — финальная проверка",
    "seal": "Печать — закрепление proof",
}

HOST, PORT = "127.0.0.1", 8799
TOKEN = secrets.token_hex(8)   # per-session token: only THIS page can run real commands (anti drive-by)
ALLOWED = {".txt", ".md", ".eml", ".json"}
MAX_BYTES = 64 * 1024 * 1024
THRESH = 50
_PALETTE = ["#22D3EE", "#22C55E", "#EAB308", "#A855F7", "#7ee0c8", "#EF4444", "#ff9e64"]

ADVANCE = {
    "anna": "Отгрузить ANNA первой клинике",
    "entity_substrate": "Провести Entity Substrate по гейтам к рождению",
    "self_construction": "Запустить следующий bounded-шаг самостройки",
    "socc": "Поддерживать ядро (основа, не разовая задача)",
    "memory": "Закрепить и применять линию Памяти",
    "law_proof": "Закрепить и применять линию Закона/Proof",
    "vision": "Оформить линию Видения",
}

# ── Evolution ladder ──
ARTICLE_N = 30
RUNGS = ["пустота", "атомы", "статья", "линия", "тикет", "исполнение", "сущность"]
LAUNCHED = SPINE2 / "_cortex_tickets.json"
ROUTE = ROOT / "core" / "socc" / "route_authority" / "CURRENT_ROUTE_AUTHORITY.json"
ROUTE_ENTITY = {"anna": "anna_live"}

# Reality density — what ALREADY EXISTS, provably, per topic (real artifacts on disk, not talk).
# The system must KNOW it is not building from zero. built=code/canon present · proof=evidence.
REALITY = {
    "anna": [("Рантайм + живой мозг", "scripts/anna_runtime_v1.py", "built"),
             ("Автономный цикл обучения", "scripts/anna_autonomy_v1.py", "built"),
             ("Канал Telegram", "scripts/anna_telegram_v1.py", "built"),
             ("Личность (канон)", "SYSTEM/ANNA_MVP/runtime/ANNA_IDENTITY_V1.json", "built"),
             ("Доказанные циклы автономии", "SYSTEM/ANNA_MVP/autonomy/STATE.json", "proof")],
    "entity_substrate": [("Канон субстрата", "SYSTEM/ENTITY_SUBSTRATE", "built"),
                         ("Печать шага самостройки", "SYSTEM/AUTONOMY/self_construction_seals/ASSIGNMENT_AUTONOMOUS_SELF_CONSTRUCTION_STEP_SEAL_V1.md", "proof")],
    "self_construction": [("Lawful runner", "socc_cli/runner.py", "built"),
                          ("Route authority", "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json", "proof"),
                          ("Печать первого шага", "SYSTEM/AUTONOMY/self_construction_seals/ASSIGNMENT_AUTONOMOUS_SELF_CONSTRUCTION_STEP_SEAL_V1.md", "proof")],
    "memory": [("Живая вики (spine v2)", "scripts/socc/socc_memory_spine_v2.py", "built"),
               ("Собранные статьи", "SOVEREIGN/WIKI/spine2/pages", "built"),
               ("Кортекс (это окно)", "scripts/socc/socc_cortex_server_v1.py", "built")],
    "law_proof": [("Мозг + гейты", "socc_cli/brain.py", "built"),
                  ("Proof-chain", "SOVEREIGN/PROOF/proof_chain", "proof")],
    "socc": [("Ядро / START_HERE", "START_HERE.md", "built"),
             ("CLI / runner", "socc_cli/cli.py", "built"),
             ("Route authority", "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json", "proof")],
    "vision": [],
}
RUN_DRY = "cd ~/SOCC && python3 socc_cli/cli.py step --dry"
RUN_GO = "cd ~/SOCC && python3 socc_cli/cli.py run"
RUN_WATCH = "cd ~/SOCC && python3 socc_cli/cli.py watch"


def safe_name(raw):
    name = Path(urllib.parse.unquote(raw or "")).name.strip()
    if not name or Path(name).suffix.lower() not in ALLOWED:
        return None
    return re.sub(r"[^0-9A-Za-zА-Яа-яЁё._ \-()]", "_", name) or None


def _proof():
    return json.loads(PROOF.read_text(encoding="utf-8")) if PROOF.exists() else {"topics": {}}


def _tm():
    return json.loads(TOPIC_MAP.read_text(encoding="utf-8")) if TOPIC_MAP.exists() else {"topics": []}


def mem_snapshot():
    """Honest before→after snapshot: global sources_scanned (a NEW file always grows this)
    + per-topic facts/sources for distilled-knowledge growth."""
    pr = _proof()
    topics = {k: {"facts": int(t.get("current", 0)), "sources": int(t.get("sources", 0)),
                  "timeline": int(t.get("timeline", 0)), "title": t.get("title", k).split(" —")[0]}
              for k, t in pr.get("topics", {}).items()}
    return {"topics": topics, "scanned": int(pr.get("sources_scanned", 0))}


def _launched():
    try:
        return json.loads(LAUNCHED.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _route():
    try:
        return json.loads(ROUTE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def reality(tid):
    """What ALREADY EXISTS for a topic — provably, from real files on disk. No invention."""
    items = []
    for label, rel, kind in REALITY.get(tid, []):
        p = ROOT / rel
        exists = p.exists()
        ev = None
        if exists and rel.endswith("STATE.json"):
            try:
                st = json.loads(p.read_text(encoding="utf-8"))
                ev = f"циклов {st.get('cycles')}, ср.оценка {st.get('rolling_avg')}"
            except Exception:
                pass
        items.append({"label": label, "kind": kind, "exists": exists, "evidence": ev, "path": rel})
    built = sum(1 for i in items if i["exists"])
    return {"items": items, "built": built, "total": len(items),
            "density": round(built / len(items), 2) if items else 0.0}


def _topic_of(p):
    p = p.lower()
    if "anna" in p: return "anna"
    if "entity_substrate" in p or "entity substrate" in p: return "entity_substrate"
    if any(k in p for k in ("self_constr", "autonomy", "runner", "self_building", "route_authority")): return "self_construction"
    if any(k in p for k in ("spine", "wiki", "memory", "cortex", "atom", "dashboard", "self_model", "self_evolve")): return "memory"
    if any(k in p for k in ("brain", "proof", "gate", "ticket", "red_team", "invariant", "semantic_guard")): return "law_proof"
    if any(k in p for k in ("supramental", "vision", "tamaguru")): return "vision"
    return "socc"


_CHRON_DIRS = ["scripts", "scripts/socc", "SYSTEM/ANNA_MVP/runtime", "SYSTEM/ANNA_MVP/autonomy",
               "SOVEREIGN/WIKI/spine2/pages", "SOVEREIGN/WIKI/main_lines", "SOVEREIGN/MEMORY/inbox",
               "SYSTEM/ENTITY_SUBSTRATE", "SYSTEM/AUTONOMY/self_construction_seals"]


def chronicle(limit=20, window_days=30):
    """Live construction log — recently touched files, classified by topic. The system SEES
    what you build (new/changed files) in near-real-time; meaning grows online. Honest = mtime."""
    now = time.time(); cutoff = now - window_days * 86400
    titles = {t["id"]: t.get("title", "") for t in _tm().get("topics", [])}
    seen = {}
    for d in _CHRON_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for f in base.glob("*.*"):
            try:
                mt = f.stat().st_mtime
            except Exception:
                continue
            if mt < cutoff or not f.is_file():
                continue
            rel = str(f.relative_to(ROOT))
            seen[rel] = (mt, f.name)
    items = sorted(((rel, mt, nm) for rel, (mt, nm) in seen.items()), key=lambda x: -x[1])[:limit]
    out = []
    for rel, mt, nm in items:
        ago = now - mt
        when = ("только что" if ago < 120 else f"{int(ago // 60)} мин назад" if ago < 3600
                else f"{int(ago // 3600)} ч назад" if ago < 86400 else f"{int(ago // 86400)} дн назад")
        tid = _topic_of(rel)
        out.append({"file": nm, "rel": rel, "topic": tid,
                    "topic_title": titles.get(tid, tid).split(" —")[0], "when": when, "fresh": ago < 3600})
    return out


def readiness_and_library():
    proof, tm = _proof(), _tm()
    color = {t["id"]: _PALETTE[i % len(_PALETTE)] for i, t in enumerate(tm.get("topics", []))}
    title = {t["id"]: t["title"] for t in tm.get("topics", [])}
    summ = {t["id"]: t.get("summary", "") for t in tm.get("topics", [])}
    launched, route = _launched(), _route()
    board, library = [], []
    for tid, st in proof.get("topics", {}).items():
        sources = int(st.get("sources", 0)); facts = int(st.get("current", 0))
        forks = int(st.get("forks", 0)); line = bool(st.get("main_line_authored"))
        material = sources >= THRESH
        forks_ok = forks <= max(facts, 8)
        taskable = tid != "socc"
        if route.get(ROUTE_ENTITY.get(tid, "_")):      rung = 6
        elif tid in launched:                           rung = 5
        elif line and forks_ok and taskable:            rung = 4
        elif line:                                      rung = 3
        elif sources >= ARTICLE_N:                      rung = 2
        elif sources > 0:                               rung = 1
        else:                                           rung = 0
        nxt = {0: "залей файл по теме",
               1: f"ещё ~{max(0, ARTICLE_N - sources)} упоминаний до статьи",
               2: "осмыслить → каноническая линия",
               3: f"снизить развилки ({forks})" if not forks_ok else "готово к тикету",
               4: "запустить тикет в систему",
               5: "пройти гейты исполнения (валидаторы)",
               6: "сущность рождена"}[rung]
        ready = rung == 4
        action = ADVANCE.get(tid, "—") if line else "Собрать каноническую линию темы"
        conds = [{"k": "материал", "ok": material, "v": f"{sources} ист."},
                 {"k": "линия", "ok": line, "v": "есть" if line else "нет"},
                 {"k": "развилки", "ok": forks_ok, "v": f"{forks}"}]
        board.append({"topic": tid, "title": title.get(tid, tid), "short": title.get(tid, tid).split(" —")[0],
                      "color": color.get(tid, "#888"), "action": action, "line": line,
                      "rung": rung, "state": RUNGS[rung], "next": nxt, "ticket": launched.get(tid),
                      "reality": reality(tid),
                      "sources": sources, "facts": facts, "forks": forks, "conditions": conds, "ready": ready})
        if line:
            library.append({"topic": tid, "title": title.get(tid, tid), "short": title.get(tid, tid).split(" —")[0],
                            "summary": summ.get(tid, ""), "color": color.get(tid, "#888"), "facts": facts, "sources": sources})
    board.sort(key=lambda x: (-x["rung"], -x["sources"]))
    total = proof.get("sources_scanned", sum(b["sources"] for b in board))
    vitals = {"sources": total, "facts": sum(b["facts"] for b in board), "topics": len(board),
              "ready": sum(1 for b in board if b["ready"]), "tickets": sum(1 for b in board if b["rung"] == 5),
              "entities": sum(1 for b in board if b["rung"] == 6), "void": total == 0,
              "mind": sum(b["rung"] for b in board)}
    return vitals, board, library


def global_graph():
    proof, tm = _proof(), _tm()
    color = {t["id"]: _PALETTE[i % len(_PALETTE)] for i, t in enumerate(tm.get("topics", []))}
    title = {t["id"]: t["title"] for t in tm.get("topics", [])}
    summ = {t["id"]: t.get("summary", "") for t in tm.get("topics", [])}
    nodes = [{"id": "core", "label": "SOCC", "group": "core", "size": 20}]
    links = []
    for tid, st in proof.get("topics", {}).items():
        authored = bool(st.get("main_line_authored"))
        nodes.append({"id": tid, "label": title.get(tid, tid).split(" —")[0], "group": "domain",
                      "size": (16 if authored else 10) + min(int(st.get("sources", 0)) // 30, 18),
                      "color": color.get(tid, "#888"), "authored": authored, "summary": summ.get(tid, ""),
                      "sources": st.get("sources", 0), "current": st.get("current", 0), "forks": st.get("forks", 0)})
        links.append({"source": "core", "target": tid, "w": 2 if authored else 1})
    return {"nodes": nodes, "links": links}


def launch(tid):
    _, board, _ = readiness_and_library()
    item = next((b for b in board if b["topic"] == tid), None)
    if not item:
        return {"ok": False, "error": "unknown topic"}
    if tid in _launched():
        return {"ok": True, "already": True, "topic": tid, "ticket_id": _launched()[tid],
                "note": "Тикет уже передан — тема в исполнении (валидаторы pending)."}
    if not item["ready"]:
        return {"ok": False, "error": "рано — условий недостаточно", "waiting": [item["next"]]}
    if BRAIN is None:
        return {"ok": False, "error": "brain unavailable"}
    request = f"{item['action']}: {item['title']}"
    try:
        ticket = BRAIN.build_ticket(request)
    except Exception as e:
        return {"ok": False, "error": f"ticket failed: {e}"}
    lan = _launched(); lan[tid] = ticket.get("id")
    try:
        LAUNCHED.write_text(json.dumps(lan, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return {"ok": True, "topic": tid, "request": request, "ticket_id": ticket.get("id"),
            "status": ticket.get("status"), "nodes": len(ticket.get("lawful_plan", [])),
            "knowledge": ticket.get("knowledge", {}).get("level"),
            "owner": "создал мозг · валидаторы: claude_code + chatgpt (pending) · исполнит runner (Hermes→socc_self)",
            "changed": {"path": "SYSTEM/COGNITION/tickets/" + (ticket.get("id") or "") + ".json",
                        "what": "тикет создан на диске"},
            "note": "Задача передана законным тикетом. Старт только после одобрения валидаторов. Без фантом-PASS."}


def read_ticket(ticket_id):
    f = TICKETS_DIR / f"{ticket_id}.json"
    if not f.exists():
        return None
    try:
        t = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None
    plan = [{"node": n["node"], "stage": n["stage"], "ru": NODE_RU.get(n["stage"], n["stage"]),
             "proof": n.get("proof_required", True)} for n in t.get("lawful_plan", [])]
    approved = sum(1 for v in t.get("validators", []) if str(v.get("verdict", "")).startswith("APPROVED"))
    return {"id": t.get("id"), "request": t.get("request"), "status": t.get("status"),
            "schema": t.get("schema"), "knowledge": t.get("knowledge", {}),
            "budget": t.get("token_budget", {}), "plan": plan,
            "validators": t.get("validators", []), "approved": approved,
            "executors": [e.get("executor") for e in t.get("executor_ladder", [])],
            "ladder_detail": t.get("executor_ladder", []),
            "validation_rule": t.get("validation_rule"), "truth_boundary": t.get("truth_boundary"),
            "no_fake_pass": t.get("no_fake_pass"), "created_at": t.get("created_at_utc"),
            "cmd_dry": RUN_DRY, "cmd_go": RUN_GO, "cmd_watch": RUN_WATCH}


def approve_validator(ticket_id, slot):
    f = TICKETS_DIR / f"{ticket_id}.json"
    if not f.exists():
        return {"ok": False, "error": "ticket not found"}
    try:
        t = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "error": "ticket unreadable"}
    hit = False
    for v in t.get("validators", []):
        if v.get("slot") == slot:
            v["verdict"] = "APPROVED (operator)"; hit = True
    if not hit:
        return {"ok": False, "error": "unknown validator slot"}
    approved = sum(1 for v in t["validators"] if str(v.get("verdict", "")).startswith("APPROVED"))
    # validation rule: starts only after >=1 validator approves (both recommended)
    t["status"] = "READY" if approved >= 1 else t.get("status", "DRAFT")
    t["operator_approved"] = approved
    try:
        f.write_text(json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"write failed: {e}"}
    return {"ok": True, "status": t["status"], "approved": approved,
            "validators": t["validators"], "ready": approved >= 1,
            "changed": {"path": "SYSTEM/COGNITION/tickets/" + ticket_id + ".json",
                        "what": "валидатор " + slot + " → APPROVED · статус=" + t["status"]}}


def _anna_history():
    h = []
    if ANNA_LEDGER.exists():
        for ln in ANNA_LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                h.append(json.loads(ln))
            except Exception:
                pass
    return h


def _delta(cur, ref):
    if not ref:
        return None
    return {k: cur.get(k, 0) - ref.get(k, 0) for k in ("code_files", "code_lines", "facts", "sources", "mass")}


def anna_state():
    snap = GROWTH.anna_snapshot()
    h = _anna_history()
    return {"snapshot": snap, "snapshots": len(h),
            "since_last": _delta(snap, h[-1] if h else None),
            "last_ts": (h[-1].get("ts") if h else None)}


def anna_record():
    """Creator button: append a real snapshot to the ledger — reality really changes."""
    snap = GROWTH.anna_snapshot()
    h = _anna_history()
    prev = h[-1] if h else None
    rec = {"ts": datetime.now(timezone.utc).isoformat(), **snap}
    try:
        ANNA_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(ANNA_LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "snapshot": snap, "snapshots": len(h) + 1, "since_prev": _delta(snap, prev),
            "changed": {"path": "SOVEREIGN/MEMORY/anna_growth_ledger.jsonl",
                        "what": "+1 срез роста ANNA (всего " + str(len(h) + 1) + ")"}}


def _read_json(p, d):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d


ATELIER_CELL = ROOT / "SYSTEM" / "ATELIER" / "ATELIER_CELL_V1.json"
ATELIER_STATE = ROOT / "SYSTEM" / "ATELIER" / "runtime" / "ATELIER_STATE_V1.json"


def design_team():
    """FACTS about the design organ (ATELIER) — proven by files, not claims."""
    cell = _read_json(ATELIER_CELL, {})
    state = _read_json(ATELIER_STATE, {})
    roles = [{"key": r.get("key"), "ru": r.get("ru"), "owns": (r.get("owns") or "")[:110]}
             for r in cell.get("roles", []) if isinstance(r, dict)]
    # count real artifacts the studio shipped (renderers + brand-forge frontiers)
    renderers = [str(p.relative_to(ROOT)) for p in [
        ROOT / "SYSTEM/INTERFACE/dashboard/socc_canon_html.py",
        ROOT / "SYSTEM/BRAND_FORGE/canon/anna_canon_html.py"] if p.exists()]
    forge_dir = ROOT / "SYSTEM" / "BRAND_FORGE" / "frontiers"
    frontiers = len(list(forge_dir.glob("*.html"))) if forge_dir.exists() else 0
    tokens = (ROOT / "SYSTEM" / "KERNEL" / "socc-tokens.css").exists()
    return {
        "exists": bool(cell),
        "id": cell.get("id"), "status": cell.get("status"),
        "purpose": (cell.get("purpose") or "")[:220],
        "roles": roles,
        "done": state.get("done", []), "in_review": state.get("in_review", []),
        "frontier": state.get("current_frontier"),
        "facts": {"renderers": renderers, "brand_frontiers_html": frontiers,
                  "design_tokens_css": tokens,
                  "cortex_uses_canon": "socc-tokens.css (matrix-minimalism)"},
        "verdict": ("Дизайн-орган РЕАЛЕН: 3-я ячейка SOCC, %d ролей, отгрузил рендереры и "
                    "компоненты. Кортекс отрисован по его токенам." % len(roles)),
    }


def dryrun():
    """Honest feasibility: run the REAL `socc status` + `step --dry` (no execution) so the
    operator SEES exactly what would run — trust by transparency, not by promise."""
    cli = ROOT / "socc_cli" / "cli.py"
    try:
        st = subprocess.run([sys.executable, str(cli), "status"], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=60)
        dr = subprocess.run([sys.executable, str(cli), "step", "--dry"], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=60)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    lawful, ready = None, None
    for ln in (st.stdout or "").splitlines():
        if "LAWFUL NEXT" in ln:
            lawful = ln.split("::", 1)[-1].strip()
        if "SCRIPT READY" in ln:
            ready = "YES" in ln
    out = ((dr.stdout or "") + (dr.stderr or "")).strip()
    return {"ok": True, "lawful_next": lawful, "script_ready": bool(ready), "feasible": bool(ready),
            "verdict": ("исполнимо роботом — прогон оставит proof" if ready else
                        "НЕ исполнимо роботом сейчас: для этого шага нет скрипта — это реальный шаг "
                        "(например, отгрузка первой клинике), нужен реальный мир/пилот, не код"),
            "output": out[:1000]}


class Hd(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    # ── live terminal: stream a REAL, SAFE socc command to the browser (SSE) ──
    _STREAM_CMD = {"status": ["status"], "observe": ["observe"],
                   "dry": ["step", "--dry"], "rundry": ["run", "--dry"]}

    def _sse_run(self, argv, echo):
        """Stream a REAL subprocess (running on this machine) to the browser line-by-line (SSE)."""
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
        except Exception:
            return
        proc = None
        try:
            self.wfile.write(("data: " + echo + "\n\n").encode("utf-8")); self.wfile.flush()
            proc = subprocess.Popen(argv, cwd=str(ROOT), stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in proc.stdout:
                self.wfile.write(("data: " + line.rstrip("\n").replace("\r", "") + "\n\n").encode("utf-8"))
                self.wfile.flush()
            proc.wait()
            self.wfile.write(("event: done\ndata: код выхода " + str(proc.returncode) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self.wfile.write(("data: [ошибка: " + str(e) + "]\n\nevent: done\ndata: err\n\n").encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass
        finally:
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _exec(self, cmd, tok):
        """Real machine terminal: run an arbitrary command on this computer, stream live.
        Guarded by a per-session token (anti drive-by) + 127.0.0.1 host only."""
        if tok != TOKEN:
            return self._send(403, "forbidden (bad token)", "text/plain")
        if not (self.headers.get("Host") or "").startswith("127.0.0.1"):
            return self._send(403, "forbidden host", "text/plain")
        if not (cmd or "").strip():
            return self._send(400, "empty command", "text/plain")
        self._sse_run(["/bin/bash", "-lc", cmd], "$ " + cmd)

    def _stream(self, cmd):
        args = self._STREAM_CMD.get(cmd)
        if not args:
            return self._send(400, "bad cmd (safe: status/observe/dry/rundry)", "text/plain")
        self._sse_run([sys.executable, str(ROOT / "socc_cli" / "cli.py"), *args], "$ socc " + " ".join(args))

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            return self._send(200, HTML.replace("__TOKEN__", TOKEN), "text/html; charset=utf-8")
        if u.path == "/graph":
            return self._send(200, json.dumps(global_graph(), ensure_ascii=False))
        if u.path == "/state":
            v, b, lib = readiness_and_library()
            return self._send(200, json.dumps({"vitals": v, "board": b, "library": lib,
                                                "chronicle": chronicle()}, ensure_ascii=False))
        if u.path == "/reality":
            return self._send(200, json.dumps(reality((q.get("t") or [""])[0]), ensure_ascii=False))
        if u.path == "/self":
            sm = SELF_MODEL.read_text(encoding="utf-8") if SELF_MODEL.exists() else ""
            se = SELF_EVOLVE.read_text(encoding="utf-8") if SELF_EVOLVE.exists() else ""
            return self._send(200, json.dumps({"self_model": sm, "self_evolve": se}, ensure_ascii=False))
        if u.path == "/page":
            tid = (q.get("t") or [""])[0]; f = PAGES / f"{tid}.md"
            md = f.read_text(encoding="utf-8") if f.exists() else "_(нет страницы)_"
            return self._send(200, json.dumps({"topic": tid, "md": md}, ensure_ascii=False))
        if u.path == "/launch":
            return self._send(200, json.dumps(launch((q.get("t") or [""])[0]), ensure_ascii=False))
        if u.path == "/ticket":
            t = read_ticket((q.get("id") or [""])[0])
            return self._send(200, json.dumps({"ok": bool(t), "ticket": t}, ensure_ascii=False))
        if u.path == "/approve":
            return self._send(200, json.dumps(approve_validator((q.get("id") or [""])[0], (q.get("slot") or [""])[0]), ensure_ascii=False))
        if u.path == "/anna":
            return self._send(200, json.dumps(anna_state(), ensure_ascii=False))
        if u.path == "/anna/snapshot":
            return self._send(200, json.dumps(anna_record(), ensure_ascii=False))
        if u.path == "/dryrun":
            return self._send(200, json.dumps(dryrun(), ensure_ascii=False))
        if u.path == "/design":
            return self._send(200, json.dumps(design_team(), ensure_ascii=False))
        if u.path == "/stream":
            return self._stream((q.get("cmd") or ["status"])[0])
        if u.path == "/exec":
            return self._exec((q.get("cmd") or [""])[0], (q.get("tok") or [""])[0])
        return self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path != "/upload":
            return self._send(404, json.dumps({"ok": False, "error": "unknown endpoint"}))
        name = safe_name(self.headers.get("X-Filename", ""))
        if not name:
            return self._send(400, json.dumps({"ok": False, "error": "bad filename/type"}))
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BYTES:
            return self._send(400, json.dumps({"ok": False, "error": "empty or too large"}))
        data = self.rfile.read(length)
        INBOX.mkdir(parents=True, exist_ok=True)
        # HONEST DEDUP: is identical content already in the system? (scan inbox by content-hash)
        sha = hashlib.sha256(data).hexdigest()[:16]
        dup_of = None
        for p in INBOX.glob("*"):
            if p.is_file():
                try:
                    if hashlib.sha256(p.read_bytes()).hexdigest()[:16] == sha:
                        dup_of = p.name
                        break
                except Exception:
                    pass
        if dup_of:
            v, b, lib = readiness_and_library()
            return self._send(200, json.dumps({
                "ok": True, "duplicate": True, "content_dup": True, "dup_of": dup_of,
                "file": {"name": name}, "stats": {"atoms": 0, "new": 0, "domains": 0},
                "grown": [], "delta": {"sources": 0, "facts": 0}, "rebuilt": True,
                "vitals": v, "board": b, "library": lib, "atoms": [], "graph": {"nodes": [], "links": []},
                "changed": {"path": "—", "what": "ничего не записано: идентичный файл уже в системе («%s»)" % dup_of},
                "trace": ["↩︎ Дубль по содержимому: этот файл уже загружен как «%s»" % dup_of,
                          "новизны нет — память не тронута (честно)"],
            }, ensure_ascii=False))
        fp = INBOX / name; fp.write_bytes(data)
        try:
            reasoning = REASON.analyze_file(fp)
        except Exception as e:
            return self._send(500, json.dumps({"ok": False, "error": f"reasoning failed: {e}"}))
        before = mem_snapshot()                                             # память ДО файла
        sp = subprocess.run([sys.executable, str(SPINE)], capture_output=True, text=True)
        after = mem_snapshot()                                              # память ПОСЛЕ файла
        grown = {}
        for tid, a in after["topics"].items():
            bf = before["topics"].get(tid, {"facts": 0, "sources": 0, "timeline": 0})
            df, ds, dtl = a["facts"] - bf["facts"], a["sources"] - bf["sources"], a["timeline"] - bf["timeline"]
            if df or ds or dtl:
                grown[tid] = {"title": a["title"], "facts": df, "sources": ds, "timeline": dtl,
                              "was": bf["facts"], "now": a["facts"]}
        # новизна ТЕМ: какие домены файл затронул, и есть ли среди них новые для системы
        touched = list((reasoning.get("domains_touched") or {}).keys())
        new_topics = [after["topics"].get(t, {}).get("title", t) for t in touched
                      if before["topics"].get(t, {}).get("facts", 0) == 0
                      and before["topics"].get(t, {}).get("sources", 0) == 0]
        reasoning["topics_touched"] = [after["topics"].get(t, {}).get("title", t) for t in touched]
        reasoning["new_topics"] = new_topics
        src_delta = after["scanned"] - before["scanned"]                    # глобально: вошёл ли НОВЫЙ источник
        fact_delta = (sum(a["facts"] for a in after["topics"].values())
                      - sum(b["facts"] for b in before["topics"].values()))
        delta = {"facts": fact_delta, "sources": src_delta,
                 "scanned_before": before["scanned"], "scanned_after": after["scanned"]}
        # honest: a real NEW file always grows sources_scanned. duplicate = nothing entered memory.
        duplicate = (src_delta == 0 and fact_delta == 0)
        v, b, lib = readiness_and_library()
        reasoning.update({"ok": True, "rebuilt": sp.returncode == 0, "vitals": v, "board": b, "library": lib,
                          "grown": list(grown.values()), "delta": delta, "duplicate": duplicate,
                          "changed": {"path": "SOVEREIGN/MEMORY/inbox/" + name,
                                      "what": ("источник +%d в памяти · вики пересобрана" % src_delta) if not duplicate else "дубль — память не выросла"}})
        self._send(200, json.dumps(reasoning, ensure_ascii=False))


def main():
    INBOX.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer((HOST, PORT), Hd)
    print("SOCC CORTEX — matrix-minimalism (Ctrl+C to stop)")
    print(f"  open : http://{HOST}:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped."); srv.shutdown()


HTML = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SOCC // CORTEX</title>
<style>
:root{--bg:#0B0F14;--surface:#121821;--surface2:#0e141d;--primary:#22D3EE;--success:#22C55E;--warning:#EAB308;
 --danger:#EF4444;--event:#A855F7;--text:#E6EDF3;--muted:#7D8893;--line:#1d2733;
 --mono:ui-monospace,"SF Mono",Menlo,Monaco,monospace;--ui:Inter,system-ui,-apple-system,sans-serif}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--text);font:15px/1.5 var(--ui);overflow:hidden}
.mono{font-family:var(--mono)}b,.num{font-variant-numeric:tabular-nums}
.top{height:58px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px;padding:0 18px;background:linear-gradient(180deg,#0c1620,#0b0f14)}
.wm{font-family:var(--mono);color:var(--primary);font-size:21px;font-weight:700;letter-spacing:.5px}
.tag{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.stat{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--muted)}
.dot{color:var(--success)}.dot.off{color:var(--muted)}
.grid{display:grid;grid-template-columns:46% 54%;height:calc(100% - 58px)}
.col{overflow:auto}.left{border-right:1px solid var(--line);padding:16px 18px 60px}.right{position:relative;background:var(--bg)}
.uz{border:1px dashed #2b3a49;border-radius:10px;padding:14px 16px;cursor:pointer;transition:.14s;background:var(--surface2)}
.uz:hover{border-color:var(--primary);background:#0c1822}.uz.drag{border-color:var(--success);background:#0c1f17;border-style:solid}
.uz .big{font-weight:600;font-size:15px;color:var(--text)}.uz .sub{font-size:12px;color:var(--muted);margin-top:2px}
.uprog{height:7px;background:#0a1219;border:1px solid var(--line);border-radius:4px;overflow:hidden;margin:9px 0 5px}
.uprog i{display:block;height:100%;background:var(--primary);box-shadow:0 0 10px var(--primary);transition:width .12s}
.uprog i.proc{background:linear-gradient(90deg,var(--primary),var(--event),var(--primary));background-size:200% 100%;animation:proc 1s linear infinite}
@keyframes proc{to{background-position:-200% 0}}
.upstat{font-family:var(--mono);font-size:11px;color:var(--muted)}
.face{border:2px solid var(--primary);border-radius:10px;padding:13px 16px;margin:13px 0;background:linear-gradient(180deg,#0c1620,#0b0f14)}
.face.void{border-color:var(--line);background:var(--surface2)}
.frow{display:flex;align-items:center;gap:12px}.flvl{font-family:var(--mono);color:var(--primary);font-size:19px;font-weight:700}
.fbar{flex:1;height:7px;background:#0a1219;border:1px solid var(--line);border-radius:5px;overflow:hidden}
.fbar i{display:block;height:100%;background:linear-gradient(90deg,var(--primary),var(--event));transition:width .6s}
.fmeta{font-family:var(--mono);font-size:12px;color:var(--muted);margin-top:8px}.fmeta .on{color:var(--success)}
.fstate{font-family:var(--mono);font-size:13px;color:var(--muted)}
.fkpi{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:11px 0 8px}
.fkpi div{cursor:help;border-left:2px solid var(--line);padding-left:9px}
.fkpi b{font-family:var(--mono);font-size:23px;color:var(--text);display:block;line-height:1;font-variant-numeric:tabular-nums}
.fkpi span{font-size:9px;font-weight:700;letter-spacing:.12em;color:var(--primary);display:block;margin-top:4px}
.fkpi em{font-style:normal;font-size:10px;color:var(--muted);display:block;margin-top:1px}
.fkpi div.flashk{animation:kflash 1.6s}@keyframes kflash{0%,55%{background:#0c2a31;border-left-color:var(--success)}100%{background:transparent}}
.agrow{border:1px solid var(--line);border-radius:10px;padding:11px 13px;margin:0 0 13px;background:var(--surface)}
.agtop{display:flex;align-items:center;gap:10px;margin-bottom:8px}.agt{font-family:var(--mono);font-size:12px;font-weight:700;color:var(--event);letter-spacing:.05em}
.agtop .go{margin-left:auto;border-color:var(--event);background:#241433;color:var(--event)}.agtop .go:hover{background:var(--event);color:#0b0f14}
.agnums{display:flex;gap:16px;flex-wrap:wrap;font-family:var(--mono);font-size:12px;color:var(--muted)}.agnums b{color:var(--text);font-size:16px}
.agdelta{font-family:var(--mono);font-size:11px;color:var(--success);margin-top:8px}.agdelta.flat{color:var(--muted)}
.ditem{font-family:var(--mono);font-size:11px;padding:6px 0;border-bottom:1px solid var(--line);display:flex;gap:8px;align-items:flex-start}
.ditem .dk{color:var(--success);flex:none}.ditem .dp{color:var(--primary);word-break:break-all;font-size:11px}.ditem .dw{color:var(--muted);display:block;margin-top:1px}
.ditem.fresh{animation:flash 1.1s}@keyframes flash{0%{background:#0c2a31}100%{background:transparent}}
.divider{font-family:var(--mono);color:var(--muted);font-size:12px;letter-spacing:1px;margin:22px 0 11px;border-bottom:1px solid var(--line);padding-bottom:6px;display:flex;justify-content:space-between}
.verdict{border-left:2px solid var(--primary);padding:7px 0 7px 12px;margin:8px 0;font-size:13px;color:var(--text)}
.row{border-bottom:1px solid var(--line);padding:11px 0;display:flex;gap:11px;align-items:flex-start}
.row .sq{width:9px;height:9px;border-radius:2px;margin-top:4px;flex:none}
.row .body{flex:1;min-width:0}.row .ttl{font-weight:600;font-size:14px}.row .act{font-size:12px;color:var(--muted);margin-top:1px}
.rung{display:flex;align-items:center;gap:3px;margin-top:7px}
.rc{width:14px;height:5px;border-radius:2px;background:#16202b}.rc.on{background:var(--primary)}.rc.cur{box-shadow:0 0 7px var(--primary)}
.rl{font-family:var(--mono);font-size:10px;color:var(--muted);margin-left:6px}
.cond{font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:5px}.cond .ok{color:var(--success)}.cond .no{color:var(--danger)}
.go{border:1px solid var(--primary);background:#0c2a31;color:var(--primary);font-family:var(--mono);font-size:11px;font-weight:700;padding:7px 12px;cursor:pointer;border-radius:5px;white-space:nowrap}
.go:hover{background:var(--primary);color:#04121a}
.badge{font-family:var(--mono);font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;white-space:nowrap}
.badge.exec{background:#2e2710;color:var(--warning)}.badge.ent{background:#0f2e1c;color:var(--success)}
.dim{font-family:var(--mono);font-size:10px;color:var(--muted)}
.libitem{border-bottom:1px solid var(--line);padding:9px 0;cursor:pointer}.libitem:hover .lt{color:var(--primary)}
.libitem .lt{font-weight:600;font-size:13px}.libitem .ls{font-size:11px;color:var(--muted);margin-top:1px}
details{margin-top:16px;border-top:1px solid var(--line)}summary{cursor:pointer;font-family:var(--mono);font-size:11px;color:var(--muted);padding:11px 0}
.trace .ln{font-family:var(--mono);padding:2px 0 2px 10px;font-size:12px;border-left:2px solid transparent;color:#aeb6c0}.trace .ln.want{border-left-color:var(--primary);color:var(--text)}
.atom{border-bottom:1px solid var(--line);padding:7px 0;display:flex;gap:9px;cursor:pointer}.atom:hover{background:#0e141d}
.atom .an{font-family:var(--mono);font-size:14px;color:var(--muted)}.atom .at{font-size:12.5px}
.atom .am{margin-top:3px;font-family:var(--mono);font-size:9px;color:var(--muted);display:flex;gap:7px;flex-wrap:wrap}.atom .new{color:var(--success)}
#cv{display:block;width:100%;height:100%;cursor:grab}#cv.grabbing{cursor:grabbing}
.gtag{position:absolute;top:12px;left:14px;font-family:var(--mono);font-size:10px;color:rgba(125,136,147,.7)}
.sel{position:absolute;top:32px;right:14px;width:290px;background:var(--surface);border:1px solid var(--primary);border-radius:8px;padding:13px 14px;display:none;max-height:72%;overflow:auto}
.sel.show{display:block}.sel h4{margin:0 0 3px;font-family:var(--mono);color:var(--primary);font-size:15px}
.sel .tagline{font-family:var(--mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:7px}
.sel p{margin:0;font-size:12px;line-height:1.45}.sel .x{position:absolute;top:7px;right:11px;cursor:pointer;color:var(--muted)}
.sel pre{white-space:pre-wrap;font:11px/1.5 var(--mono);margin:8px 0 0;color:#c4ccd6}
.toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:var(--surface);border:1px solid var(--primary);border-radius:8px;color:var(--text);padding:12px 16px;font-size:12.5px;max-width:580px;z-index:80;display:none;font-family:var(--mono)}
.toast.show{display:block}.toast b{color:var(--primary)}
.reflect{position:absolute;bottom:0;left:0;right:0;border-top:1px solid var(--line);background:#0a0e13;color:#aeb6c0;padding:9px 14px;font-family:var(--mono);font-size:11px;display:flex;gap:18px}
.reflect .h{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--primary);margin-bottom:2px}.reflect .w{color:var(--event)}
body.ignite{background:var(--primary)!important}.ignmsg{position:fixed;inset:0;display:none;align-items:center;justify-content:center;font-family:var(--mono);font-weight:700;font-size:60px;color:#04121a;z-index:60;pointer-events:none}body.ignite .ignmsg{display:flex}
.tkt{position:fixed;inset:0;background:rgba(5,8,11,.8);backdrop-filter:blur(4px);z-index:90;display:none;align-items:center;justify-content:center}
.tkt.show{display:flex}.tktcard{position:relative;width:min(880px,94vw);max-height:90vh;overflow:auto;background:var(--surface);border:1px solid var(--primary);border-radius:12px;padding:18px 22px}
.tkt h3{font-family:var(--mono);color:var(--primary);margin:0 0 2px;font-size:17px}.tkt .sub{font-family:var(--mono);font-size:11px;color:var(--muted);margin-bottom:12px;word-break:break-all}
.tkt .x{position:absolute;top:16px;right:20px;cursor:pointer;color:var(--muted);font-size:22px}
.tkt .meta{display:flex;gap:18px;flex-wrap:wrap;font-family:var(--mono);font-size:12px;margin-bottom:14px;color:var(--muted)}.tkt .meta b{color:var(--text)}.tkt .meta b.ok{color:var(--success)}
.tktcols{display:grid;grid-template-columns:1.15fr 1fr;gap:20px}@media(max-width:720px){.tktcols{grid-template-columns:1fr}}
.pipe{position:relative;padding-left:2px}.pipe::before{content:"";position:absolute;left:31px;top:10px;bottom:10px;width:1px;background:var(--line)}
.pnode{display:flex;gap:10px;align-items:flex-start;padding:5px 0;position:relative;z-index:1}
.pnode .pn{font-family:var(--mono);width:20px;color:var(--muted);font-size:12px}
.pnode .pd{width:11px;height:11px;border-radius:50%;border:2px solid var(--line);margin-top:2px;flex:none;background:var(--surface)}
.pnode.ready .pd{border-color:var(--primary)}.pnode .ptx{font-size:12.5px}.pnode .pst{font-family:var(--mono);font-size:9px;color:var(--muted)}
.gate{border:1px solid var(--line);border-radius:8px;padding:11px 12px;margin-bottom:10px}.gate.ok{border-color:var(--success)}
.gate h4{margin:0 0 7px;font-family:var(--mono);font-size:12px;color:var(--text)}
.vrow{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:12px;padding:4px 0}.vrow .vd{margin-left:auto}
.appr{border:1px solid var(--primary);background:#0c2a31;color:var(--primary);font-family:var(--mono);font-size:10px;padding:4px 9px;border-radius:4px;cursor:pointer}.appr:hover{background:var(--primary);color:#04121a}
.vok{color:var(--success);font-weight:700}
.ladder{font-family:var(--mono);font-size:11px;color:var(--muted)}.ladder b{color:var(--primary)}
.heart{font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:12px}.heart .hb{color:var(--success);animation:bl 1.4s infinite}@keyframes bl{50%{opacity:.2}}
.tbound{font-size:11px;color:var(--muted);border-left:2px solid var(--warning);padding-left:9px;margin-top:13px}
.real{font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:6px;cursor:pointer;display:flex;align-items:center;gap:7px}
.real:hover{color:var(--text)}.rbar{width:46px;height:5px;background:#16202b;border-radius:3px;overflow:hidden;flex:none}.rbar i{display:block;height:100%}
.cmd{display:flex;align-items:center;gap:8px;background:#06121a;border:1px solid var(--line);border-radius:6px;padding:7px 9px;margin:6px 0;font-family:var(--mono);font-size:11px;color:var(--primary)}
.cmd span{flex:1;overflow:auto;white-space:nowrap}.cmd button{background:#0c2a31;border:1px solid var(--primary);color:var(--primary);border-radius:4px;padding:2px 8px;cursor:pointer;font-size:10px;font-family:var(--mono)}.cmd button:hover{background:var(--primary);color:#04121a}
.chitem{display:flex;gap:9px;align-items:center;padding:6px 0;border-bottom:1px solid var(--line);font-size:12px}
.chitem .cdot{width:7px;height:7px;border-radius:50%;flex:none}.chitem .cf{font-family:var(--mono);font-size:11.5px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chitem .cw{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--muted);white-space:nowrap}.chitem.fresh .cf{color:var(--success)}
.rlist{margin-top:8px}.rlist .ri{display:flex;gap:8px;font-family:var(--mono);font-size:11.5px;padding:3px 0}.rlist .ri .rk{flex:none}.rlist .yes{color:var(--success)}.rlist .no{color:var(--muted)}
.newtopic{display:inline-block;background:var(--event);color:#0b0f14;font-family:var(--mono);font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px;margin:2px 3px 0 0}
.term{margin-top:12px;border:1px solid var(--line);border-radius:8px;background:#05090d;overflow:hidden}
.termbar{display:flex;align-items:center;gap:7px;padding:7px 11px;background:#0a1017;border-bottom:1px solid var(--line);font-family:var(--mono);font-size:11px;color:var(--muted)}
.termbar .tdot{width:9px;height:9px;border-radius:50%;background:#2a333d}.termbar .tdot.live{background:var(--success);animation:bl 1.1s infinite}
.termbar .tbtn{margin-left:auto;background:var(--success);color:#04120a;border:0;font-family:var(--mono);font-size:10px;font-weight:700;padding:4px 11px;border-radius:4px;cursor:pointer}.termbar .tbtn:hover{filter:brightness(1.15)}.termbar .tbtn.stop{background:var(--danger);color:#fff}
.termbody{font-family:var(--mono);font-size:11px;line-height:1.5;color:#8fe3b0;padding:10px 12px;height:200px;overflow:auto;white-space:pre-wrap}
.termbody .cmd0{color:var(--primary)}.termbody .err{color:var(--danger)}.termbody .done{color:var(--warning)}
.terminput{display:flex;align-items:center;gap:7px;padding:7px 11px;border-top:1px solid var(--line);background:#0a1017}
.terminput>span{color:var(--success);font-family:var(--mono);font-weight:700}
.terminput input{flex:1;background:transparent;border:0;outline:0;color:var(--text);font-family:var(--mono);font-size:12px}
.terminput input::placeholder{color:#4a545f}
.terminput button{background:var(--primary);color:#04121a;border:0;border-radius:4px;padding:4px 11px;cursor:pointer;font-weight:700;font-family:var(--mono)}
</style></head><body>
<div class="ignmsg">Читаю…</div>
<div class="top"><div class="wm">SOCC // CORTEX</div><div class="tag" style="cursor:pointer" onclick="showDesign()" title="кто отвечает за визуал — факты">живое лицо · matrix-minimalism · <span style="color:var(--primary)">кто рисовал ▸</span></div><div class="stat" id="stat"><span class="dot">●</span> готов</div></div>
<div class="grid">
 <div class="col left">
  <div class="uz" id="uz"><div class="big mono">⤓ Брось файл</div><div class="sub">система съест его, построит себя и покажет, ЧТО делать</div></div>
  <input type="file" id="fi" accept=".txt,.md,.eml,.json" hidden>
  <div class="face" id="face"></div>
  <div class="agrow" id="agrow"></div>
  <div class="divider">── ИЗМЕНЕНИЯ НА ДИСКЕ <span id="diskcount" style="color:var(--muted)"></span><span style="color:var(--muted);font-weight:400;margin-left:auto;text-transform:none;letter-spacing:0">так выглядит «работает»</span></div>
  <div id="disk"><div class="dim">нажми любую кнопку — здесь появится файл, который РЕАЛЬНО изменился на диске</div></div>
  <div class="divider">── ТЕРМИНАЛ · подключён к компу<span style="color:var(--muted);font-weight:400;margin-left:auto;text-transform:none;letter-spacing:0">live · реальные команды</span></div>
  <div class="term">
   <div class="termbar"><span class="tdot" id="tdot"></span><span id="tstat">готов</span>
    <button class="tbtn" id="tstart" onclick="runStream('rundry')">▶ СТАРТ · что сделает runner</button></div>
   <div class="termbody" id="termbody"><span style="color:var(--muted)">жми СТАРТ или впиши команду ↓ — увидишь реальный процесс на компе, построчно</span></div>
   <div class="terminput"><span>$</span><input id="tcmd" spellcheck="false" autocomplete="off" placeholder="реальная команда: socc status · ls · git status · python3 …" onkeydown="if(event.key==='Enter')runExec()"><button onclick="runExec()">↵</button></div>
  </div>
  <div style="display:flex;gap:6px;margin-top:7px;flex-wrap:wrap">
   <button class="go" style="font-size:10px;padding:5px 9px" onclick="runStream('status')">socc status</button>
   <button class="go" style="font-size:10px;padding:5px 9px" onclick="runStream('dry')">dry-шаг</button>
   <button class="go" style="font-size:10px;padding:5px 9px" onclick="runStream('observe')">observe</button>
  </div>
  <div class="divider">── ТЕРМИНАЛ · живой процесс системы</div>
  <div class="term">
   <div class="termbar"><span class="tdot" id="tdot"></span><span id="tstat">готов · жми старт</span>
    <button class="tbtn" id="tstart" onclick="runStream('rundry')">▶ СТАРТ</button></div>
   <div class="termbody" id="termbody"><span style="color:var(--muted)">жми СТАРТ — увидишь реальный процесс системы построчно, в лайв-формате (безопасно, dry)</span></div>
  </div>
  <div style="display:flex;gap:6px;margin-top:7px;flex-wrap:wrap">
   <button class="go" style="font-size:10px;padding:5px 9px" onclick="runStream('status')">статус</button>
   <button class="go" style="font-size:10px;padding:5px 9px" onclick="runStream('dry')">dry-шаг</button>
   <button class="go" style="font-size:10px;padding:5px 9px" onclick="runStream('observe')">observe</button></div>
  <div id="verdict"></div>
  <div class="divider">── ЧТО ДАЛЬШЕ <span id="rcount"></span></div>
  <div id="board"></div>
  <div class="divider">── БИБЛИОТЕКА · каноническая вики</div>
  <div id="library"></div>
  <div class="divider">── ЛЕТОПИСЬ · строится сейчас <span id="chcount" style="color:var(--muted)"></span></div>
  <div id="chron"></div>
  <details><summary>▸ как думала система (под капотом)</summary><div class="trace" id="trace"></div><div id="atoms"></div></details>
 </div>
 <div class="col right">
  <canvas id="cv"></canvas><div class="gtag">граф знания · тяни · кликай · колесо = зум</div>
  <div class="sel" id="sel"></div><div class="reflect" id="reflect"></div>
 </div>
</div>
<div class="toast" id="toast"></div>
<div class="tkt" id="tkt"><div class="tktcard" id="tktcard"></div></div>
<script>
const $=id=>document.getElementById(id),sleep=ms=>new Promise(r=>setTimeout(r,ms));
const esc=s=>(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
let diskN=0;
function logChange(c){if(!c||!c.path)return;diskN++;$('diskcount').textContent='· '+diskN;const host=$('disk');const dm=host.querySelector('.dim');if(dm)host.innerHTML='';const d=document.createElement('div');d.className='ditem fresh';d.innerHTML='<span class="dk">✎</span><div><span class="dp">'+esc(c.path)+'</span><span class="dw">'+esc(c.what||'изменён')+'</span></div>';host.prepend(d)}
function flashKpi(d){setTimeout(()=>{const k=document.querySelectorAll('.fkpi div');if(!k.length)return;if((d.sources||0)>0&&k[0])k[0].classList.add('flashk');if((d.facts||0)>0&&k[1])k[1].classList.add('flashk');},40)}
const TOK="__TOKEN__";
let es=null;
function tline(txt,cls){const b=$('termbody');const ph=b.querySelector('span');if(ph&&ph.parentElement===b&&b.children.length===1)b.innerHTML='';const d=document.createElement('div');if(cls)d.className=cls;d.textContent=txt;b.appendChild(d);b.scrollTop=b.scrollHeight}
function endStream(){if(es){es.close();es=null}const t=$('tdot');if(t)t.classList.remove('live');$('tstat').textContent='готов';const bt=$('tstart');bt.textContent='▶ СТАРТ · что сделает runner';bt.classList.remove('stop');bt.onclick=()=>runStream('rundry')}
function stopStream(){tline('■ остановлено оператором','done');endStream()}
function openES(url){if(es){es.close();es=null}$('termbody').innerHTML='';const t=$('tdot');if(t)t.classList.add('live');$('tstat').textContent='выполняется…';const bt=$('tstart');bt.textContent='■ стоп';bt.classList.add('stop');bt.onclick=stopStream;
 es=new EventSource(url);es.onmessage=e=>tline(e.data);es.addEventListener('done',e=>{tline('■ '+e.data,'done');endStream()});es.onerror=()=>endStream()}
function runStream(cmd){openES('/stream?cmd='+encodeURIComponent(cmd))}
function runExec(){const i=$('tcmd');const c=(i.value||'').trim();if(!c)return;i.value='';openES('/exec?cmd='+encodeURIComponent(c)+'&tok='+encodeURIComponent(TOK))}
const RL=["пустота","атомы","статья","линия","тикет","исполн.","сущность"];
const uz=$('uz'),fi=$('fi');
uz.onclick=()=>fi.click();fi.onchange=e=>e.target.files[0]&&up(e.target.files[0]);
uz.ondragover=e=>{e.preventDefault();uz.classList.add('drag')};uz.ondragleave=()=>uz.classList.remove('drag');
uz.ondrop=e=>{e.preventDefault();uz.classList.remove('drag');e.dataTransfer.files[0]&&up(e.dataTransfer.files[0])};

function renderFace(v){const f=$('face');if(v.void){f.classList.add('void');f.innerHTML='<div class="fstate">○ ПУСТОТА · система спит. Залей файл — и я начну строить себя из памяти.</div>';return}
 f.classList.remove('void');const max=Math.max(v.topics*6,1),pct=Math.round(v.mind/max*100);
 const K=[
  ['СЫРЬЁ',v.sources,'файлов в памяти','Сколько файлов знания система усвоила. База, из которой она думает. Больше — шире контекст.'],
  ['ЗНАНИЕ',v.facts,'дистиллированных истин','Утверждения, принятые как ФАКТ (current truth). Не «читала» — ЗНАЕТ. Этим она оперирует при постройке.'],
  ['ГОТОВО',v.ready,'тем к запуску сейчас','По скольким темам можно прямо сейчас передать реальную задачу (тикет). Твои точки действия.']];
 f.innerHTML=`<div class="frow"><span class="flvl" title="Σ ступеней всех тем на лестнице пустота→…→сущность. Растёт, когда тема поднимается на ступень. Смысл: насколько система близка к живому продукту.">ЗРЕЛОСТЬ · ${v.mind}/${max}</span><span class="fbar" title="${pct}% пути к сущности"><i style="width:${pct}%"></i></span><span style="font-family:var(--mono);font-size:11px;color:var(--muted)">${pct}% к продукту</span></div>
  <div class="fkpi">${K.map(k=>`<div title="${esc(k[3])}"><b>${k[1]}</b><span>${k[0]}</span><em>${k[2]}</em></div>`).join('')}</div>
  <div class="fmeta"><span class="on">●</span> в исполнении: ${v.tickets} · сущностей рождено: ${v.entities} <span style="color:var(--muted)">(конечная цель — живой продукт = деньги)</span></div>`}
function rungBar(x){let c='';for(let i=0;i<7;i++)c+=`<span class="rc ${i<=x.rung?'on':''} ${i===x.rung?'cur':''}"></span>`;return `<div class="rung">${c}<span class="rl">${RL[x.rung]} ${x.rung}/6</span></div>`}
function rowBtn(x){if(x.rung===6)return '<span class="badge ent">сущность ✓</span>';
 if(x.rung===5)return `<span class="badge exec" style="cursor:pointer" onclick="openTicket('${esc(x.ticket||'')}')">в исполнении ▸</span>`;
 if(x.ready)return `<button class="go" onclick="launch('${x.topic}',this)">запустить ▸</button>`;
 return `<span class="dim">${esc(x.next)}</span>`}
let lastBoard=[];
function realLine(x){const r=x.reality;if(!r||!r.total)return '';const pct=Math.round(r.density*100),col=r.density>=0.8?'var(--success)':r.density>=0.4?'var(--warning)':'var(--danger)';
 return `<div class="real" onclick="showReal('${x.topic}','${esc(x.short)}')"><span class="rbar"><i style="width:${pct}%;background:${col}"></i></span><span style="color:${col}">реальность ${r.built}/${r.total}</span><span>· что построено</span></div>`}
function renderBoard(b){lastBoard=b;$('rcount').textContent=b.filter(x=>x.ready).length+' готовы · '+b.filter(x=>x.rung===5).length+' в работе';
 $('board').innerHTML=b.map(x=>{const cond=x.conditions.map(c=>`<span class="${c.ok?'ok':'no'}">${c.ok?'✓':'✗'} ${c.v}</span>`).join('  ');
  return `<div class="row"><span class="sq" style="background:${x.color}"></span><div class="body">
   <div class="ttl" style="cursor:pointer" onclick="readPage('${x.topic}','${esc(x.short)}')">${esc(x.short)} <span style="font-size:9px;color:var(--muted);font-weight:400">что знаю ▸</span></div><div class="act">${esc(x.action)}</div>${rungBar(x)}<div class="cond">${cond}</div>${realLine(x)}</div>${rowBtn(x)}</div>`}).join('')}
function renderChron(ch){if(!ch)return;$('chcount').textContent=ch.length?('· '+ch.length+' файлов'):'';
 $('chron').innerHTML=ch.length?ch.map(c=>`<div class="chitem ${c.fresh?'fresh':''}"><span class="cdot" style="background:${c.fresh?'var(--success)':'var(--muted)'}"></span><span class="cf">${esc(c.file)}</span><span class="cw">${esc(c.topic_title)} · ${esc(c.when)}</span></div>`).join(''):'<div class="dim">пока тихо — строй, и здесь появится вживую</div>'}
function showReal(tid,name){fetch('/reality?t='+tid).then(r=>r.json()).then(r=>{const s=$('sel');
 const li=r.items.map(i=>`<div class="ri"><span class="rk ${i.exists?'yes':'no'}">${i.exists?'✓':'○'}</span><span>${esc(i.label)}${i.evidence?' <span style="color:var(--muted)">('+esc(i.evidence)+')</span>':''} <span style="color:var(--muted)">·${i.kind}</span></span></div>`).join('');
 s.innerHTML=`<span class="x" onclick="clearSel()">×</span><div class="tagline">плотность реальности · ${r.built}/${r.total}</div><h4>${esc(name)}</h4><p style="color:var(--muted)">Что УЖЕ построено (доказано файлами), а чего нет:</p><div class="rlist">${li}</div>`;s.classList.add('show')})}
function renderLib(lib){$('library').innerHTML=lib.map(l=>`<div class="libitem" onclick="readPage('${l.topic}','${esc(l.short)}')"><div class="lt">${esc(l.short)}</div><div class="ls">${esc((l.summary||'').slice(0,110))}…</div></div>`).join('')}
function refresh(){fetch('/state').then(r=>r.json()).then(s=>{renderFace(s.vitals);renderBoard(s.board);renderLib(s.library);renderChron(s.chronicle)});fetchAnna()}
function fetchAnna(){fetch('/anna').then(r=>r.json()).then(renderAnna).catch(()=>{})}
function fmtDelta(d){if(!d)return '';const p=[];if(d.code_files)p.push((d.code_files>0?'+':'')+d.code_files+' файлов');if(d.code_lines)p.push((d.code_lines>0?'+':'')+d.code_lines+' строк');if(d.facts)p.push((d.facts>0?'+':'')+d.facts+' фактов');return p.length?p.join(' · '):'без изменений'}
function renderAnna(d){const s=d.snapshot||{},sl=d.since_last;
 const dl=sl&&(sl.code_files||sl.code_lines||sl.facts)?('с прошлого среза: '+fmtDelta(sl)):(d.snapshots?'с прошлого среза: без изменений':'срезов ещё нет — зафиксируй первый, и рост станет виден');
 $('agrow').innerHTML=`<div class="agtop"><span class="agt">🧬 ANNA · её код растёт = её эволюция</span><button class="go" onclick="snapAnna(this)">зафиксировать рост ▸</button></div>
  <div class="agnums"><span><b>${s.code_files??'—'}</b> файлов кода</span><span><b>${(s.code_lines||0).toLocaleString('ru')}</b> строк</span><span><b>${s.facts??'—'}</b> фактов</span><span><b>${s.cycles??'—'}</b> циклов · ${s.avg_score??'—'}</span></div>
  <div class="agdelta ${sl&&(sl.code_files||sl.code_lines||sl.facts)?'':'flat'}">${dl} · срезов: ${d.snapshots||0}</div>`}
function snapAnna(btn){btn.textContent='…';fetch('/anna/snapshot').then(r=>r.json()).then(j=>{
  if(j.ok){logChange(j.changed);const sp=j.since_prev;toast('<b>Срез ANNA зафиксирован</b> (#'+j.snapshots+') — реальность записана в ledger.'+(sp&&(sp.code_files||sp.code_lines||sp.facts)?'<br>рост с прошлого: '+fmtDelta(sp):''));fetchAnna()}
  else{toast('✗ '+esc(j.error||''));btn.textContent='зафиксировать рост ▸'}})}

function uzReset(msg){uz.innerHTML=`<div class="big mono">${esc(msg||'⤓ Брось файл')}</div><div class="sub">система съест его, построит себя и покажет, ЧТО делать</div>`}
function up(f){$('trace').innerHTML='';$('atoms').innerHTML='';clearSel();
 document.body.classList.add('ignite');setTimeout(()=>document.body.classList.remove('ignite'),520);
 const kb=(f.size/1024).toFixed(1);
 uz.innerHTML=`<div class="big mono">⟳ ${esc(f.name)}</div><div class="uprog"><i id="upbar" style="width:0%"></i></div><div class="upstat" id="upstat">0 / ${kb} КБ</div>`;
 $('stat').innerHTML='<span class="dot">●</span> загрузка…';
 const xhr=new XMLHttpRequest();xhr.open('POST','/upload');xhr.setRequestHeader('X-Filename',encodeURIComponent(f.name));const t0=performance.now();
 xhr.upload.onprogress=e=>{if(!e.lengthComputable)return;const pc=Math.round(e.loaded/e.total*100),sp=(e.loaded/1024)/(((performance.now()-t0)/1000)||1);const bar=$('upbar');if(bar)bar.style.width=pc+'%';const stt=$('upstat');if(stt)stt.textContent=(e.loaded/1024).toFixed(1)+' / '+kb+' КБ · '+sp.toFixed(0)+' КБ/с · '+pc+'%'};
 xhr.upload.onload=()=>{const bar=$('upbar');if(bar){bar.style.width='100%';bar.classList.add('proc')}const stt=$('upstat');if(stt)stt.textContent=kb+' КБ загружено · система осмысляет…';$('stat').innerHTML='<span class="dot">●</span> осмысляю…'};
 xhr.onload=()=>{let j;try{j=JSON.parse(xhr.responseText)}catch(e){uzReset('✗ ошибка ответа');return}onUploadDone(f,j)};
 xhr.onerror=()=>uzReset('✗ запусти сервер');
 xhr.send(f);
}
function onUploadDone(f,j){
 if(!j.ok){uzReset('✗ '+(j.error||'ошибка'));return}
 uzReset('✓ '+j.file.name+' · брось ещё');
 $('stat').innerHTML='<span class="dot">●</span> связал '+j.stats.atoms+' фактов'+(j.rebuilt?'':' (вики не пересобралась!)');
 renderFace(j.vitals);renderBoard(j.board);renderLib(j.library);logChange(j.changed);fetchAnna();
 const g=j.grown||[], d=j.delta||{};
 const known=(j.stats.atoms||0)-(j.stats.new||0);
 if(j.content_dup){
   $('verdict').innerHTML=`<div class="verdict" style="border-color:var(--warning)">↩︎ <b>ДУБЛЬ ФАЙЛА</b> · идентичное содержимое уже в системе как «${esc(j.dup_of||'')}». Новизны нет, память не тронута. <span style="color:var(--muted)">(так система честно ловит повтор)</span></div>`;
 } else if(j.duplicate){
   $('verdict').innerHTML=`<div class="verdict" style="border-color:var(--warning)">↩︎ <b>Ничего нового не вошло</b> — весь контент уже покрыт памятью. Дубли не растят (честно).</div>`;
 } else {
   const parts=[];
   if(d.sources>0) parts.push(`СЫРЬЁ <b>${d.scanned_before}→${d.scanned_after}</b> <span style="color:var(--success)">(+${d.sources})</span>`);
   if(g.length) parts.push('ЗНАНИЕ '+g.map(x=>`«${esc(x.title)}» ${x.was}→${x.now} <span style="color:var(--success)">(+${x.facts})</span>`).join(', '));
   $('verdict').innerHTML=`<div class="verdict" style="border-color:var(--success)">✨ <b>НОВИЗНА: ${j.stats.new}</b> новых атомов из ${j.stats.atoms} <span style="color:var(--muted)">(уже знал ${known})</span><br>📈 <b>РОСТ:</b> ${parts.length?parts.join(' · '):'источник зафиксирован в памяти'}</div>`;
   const tt=(j.topics_touched||[]),nt=(j.new_topics||[]);
   if(tt.length)$('verdict').innerHTML+=`<div class="verdict" style="border-color:var(--event)">затронул темы: ${tt.map(t=>esc(t.split(' —')[0])).join(' · ')}${nt.length?' · '+nt.map(t=>'<span class="newtopic">🆕 '+esc(t.split(' —')[0])+'</span>').join(''):''}</div>`;
   flashKpi(d);
 }
 const prop=(j.board||[]).find(x=>x.ready);
 if(prop)$('verdict').innerHTML+=`<div class="verdict" style="border-color:var(--success)">📌 Предложение: «${esc(prop.short)}» готова → <button class="go" style="padding:4px 10px" onclick="launch('${prop.topic}',this)">начать таск ▸</button> <span style="color:var(--muted)">или дособери тикет (кнопка «запустить» откроет инспектор)</span></div>`;
 for(const ln of j.trace){const d=document.createElement('div');d.className='ln'+(/ХОЧЕТ|вектор/.test(ln)?' want':'');d.textContent=ln;$('trace').appendChild(d)}
 for(const a of j.atoms.slice(0,40)){const d=document.createElement('div');d.className='atom';d.dataset.aid='a'+a.n;
   d.innerHTML=`<div class="an">${String(a.n).padStart(2,'0')}</div><div><div class="at">${esc(a.text)}</div><div class="am"><span style="color:${a.color}">${esc((a.domain_title||'').split(' —')[0])}</span><span>${a.intent}</span>${a.novelty==='new'?'<span class="new">NEW</span>':''}</div></div>`;
   d.onmouseenter=()=>{const n=N.find(x=>x.id===d.dataset.aid);if(n)hover=n};d.onmouseleave=()=>{hover=null};
   d.onclick=()=>{const n=N.find(x=>x.id===d.dataset.aid);if(n){view.ox=cv.width/2-n.x*view.s;view.oy=cv.height*0.46-n.y*view.s;hover=n}};
   $('atoms').appendChild(d)}
 mergeGraph(j.graph);
}
function launch(tid,btn){btn.textContent='…';fetch('/launch?t='+tid).then(r=>r.json()).then(j=>{
  if(j.ok){logChange(j.changed);toast(j.already?`Тикет уже передан: <b>${esc(j.ticket_id||'')}</b>`:`<b>Задача передана в систему.</b> открываю инспектор процесса…`);refresh();if(j.ticket_id)openTicket(j.ticket_id)}
  else{toast('Рано: '+esc(j.error||'')+(j.waiting?' — '+esc(j.waiting.join(', ')):''));btn.textContent='рано'}})}
function toast(html){const t=$('toast');t.innerHTML=html;t.classList.add('show');clearTimeout(toast._t);toast._t=setTimeout(()=>t.classList.remove('show'),11000)}
function readPage(tid,name){fetch('/page?t='+tid).then(r=>r.json()).then(j=>{const s=$('sel');s.innerHTML=`<span class="x" onclick="clearSel()">×</span><div class="tagline">каноническая линия</div><h4>${esc(name)}</h4><pre>${esc((j.md||'').slice(0,2600))}</pre>`;s.classList.add('show')})}
let tktId=null,tktTopic=null,tktTimer=null,lastDry=null;
function openTicket(id,topic){if(!id)return;tktId=id;tktTopic=topic||((lastBoard.find(x=>x.ticket===id)||{}).topic)||null;lastDry=null;
 $('tkt').classList.add('show');pollTicket();dryRun();clearInterval(tktTimer);tktTimer=setInterval(pollTicket,2500)}
function dryRun(){lastDry={loading:true};pollTicket();fetch('/dryrun').then(r=>r.json()).then(j=>{lastDry=j;pollTicket()}).catch(()=>{lastDry={ok:false,error:'нет связи'};pollTicket()})}
function dryHtml(){if(!lastDry)return 'нажми — увидишь реальный dispatch системы, без доверия на слово';
 if(lastDry.loading)return 'проверяю…';if(!lastDry.ok)return '✗ '+esc(lastDry.error||'');
 const col=lastDry.feasible?'var(--success)':'var(--warning)';
 return '<span style="color:'+col+'">'+(lastDry.feasible?'✓ ':'⛔ ')+esc(lastDry.verdict)+'</span>\nзаконный шаг: '+esc(lastDry.lawful_next||'—')+' · скрипт: '+(lastDry.script_ready?'ЕСТЬ':'НЕТ')+'\n'+esc(lastDry.output||'')}
function closeTicket(){$('tkt').classList.remove('show');clearInterval(tktTimer);tktId=null}
function pollTicket(){if(!tktId)return;Promise.all([fetch('/ticket?id='+encodeURIComponent(tktId)).then(r=>r.json()),tktTopic?fetch('/reality?t='+tktTopic).then(r=>r.json()):Promise.resolve(null)]).then(([j,rl])=>{if(j&&j.ok)renderTicket(j.ticket,rl)})}
function approveV(slot){fetch('/approve?id='+encodeURIComponent(tktId)+'&slot='+encodeURIComponent(slot)).then(r=>r.json()).then(j=>{if(j.ok){logChange(j.changed);pollTicket();refresh();if(j.ready)toast('Валидатор одобрен ('+j.approved+'/2) → тикет <b>READY</b>. Команда в терминал доступна.')}else toast('✗ '+esc(j.error||''))})}
function cp(btn){try{navigator.clipboard.writeText(btn.previousElementSibling.textContent)}catch(e){}btn.textContent='ok';setTimeout(()=>btn.textContent='copy',900)}
function renderTicket(t,rl){const ready=t.status==='READY';
 const nodes=t.plan.map(n=>`<div class="pnode ${ready?'ready':''}"><div class="pn">${String(n.node).padStart(2,'0')}</div><div class="pd"></div><div><div class="ptx">${esc(n.ru)}</div><div class="pst">${ready?'готов к runner':'ждёт валидаторов'}${n.proof?' · proof':''}</div></div></div>`).join('');
 const vals=t.validators.map(v=>{const ok=String(v.verdict).startsWith('APPROVED');return `<div class="vrow">${ok?'<span class="vok">✓</span>':'○'} ${esc(v.slot)} <span style="color:var(--muted)">${esc(v.role)}</span><span class="vd">${ok?'<span class="vok">APPROVED</span>':`<button class="appr" onclick="approveV('${esc(v.slot)}')">одобрить</button>`}</span></div>`}).join('');
 const k=t.knowledge||{},b=t.budget||{};
 const realHtml=rl&&rl.total?`<div class="gate ${rl.density>=0.8?'ok':''}"><h4>На чём строим — что УЖЕ есть (${rl.built}/${rl.total})</h4>${rl.items.map(i=>`<div class="ri"><span class="rk ${i.exists?'yes':'no'}">${i.exists?'✓':'○'}</span> ${esc(i.label)}${i.evidence?' <span style="color:var(--muted)">('+esc(i.evidence)+')</span>':''}</div>`).join('')}<div class="pst" style="margin-top:5px">процесс НЕ изолирован — строит на этом</div></div>`:'';
 $('tktcard').innerHTML=`<span class="x" onclick="closeTicket()">×</span>
  <h3>ТИКЕТ · ${esc((t.request||'').slice(0,52))}</h3><div class="sub">${esc(t.id||'')}</div>
  <div class="meta"><span>статус <b class="${ready?'ok':''}">${esc(t.status)}</b></span><span>знание <b>${esc(k.level||'')}</b></span><span>бюджет <b>${(b.estimate_low||0).toLocaleString('ru')}–${(b.estimate_high||0).toLocaleString('ru')}</b> ток</span><span>валидаторы <b>${t.approved}/2</b></span></div>
  <div class="tktcols">
   <div><div class="divider" style="margin:0 0 8px">── ЗАКОННЫЙ ПЛАН · 10 узлов</div><div class="pipe">${nodes}</div></div>
   <div>
     <div class="gate ${t.approved>=1?'ok':''}"><h4>Валидаторы — гейт перед стартом</h4>${vals}<div class="pst" style="margin-top:6px">${esc(t.validation_rule||'')}</div></div>
     ${realHtml}
     <div class="gate"><h4>Кто построит — лестница исполнителей</h4><div class="ladder">${(t.executors||[]).map((e,i)=>(i?' → ':'')+'<b>'+esc(e)+'</b>').join('')}</div></div>
     <div class="gate"><h4>Исполнимость · проверь сам (не на слово)</h4>
       <button class="appr" onclick="dryRun()">▶ dry-run · что РЕАЛЬНО запустится</button>
       <div class="pst" style="margin-top:7px;white-space:pre-wrap">${dryHtml()}</div></div>
     <div class="gate ${ready?'ok':''}"><h4>${ready?'▶ В терминал — живой процесс':'Команды (после одобрения)'}</h4>
       <button class="appr" style="margin-bottom:7px" onclick="closeTicket();runStream('rundry')">▶ СТАРТ live · смотреть процесс на странице</button>
       <div class="cmd"><span>${esc(t.cmd_dry||'')}</span><button onclick="cp(this)">copy</button></div>
       <div class="cmd"><span>${esc(t.cmd_go||'')}</span><button onclick="cp(this)">copy</button></div>
       <div class="cmd"><span>${esc(t.cmd_watch||'')}</span><button onclick="cp(this)">copy</button></div>
       <div class="pst">--dry: шаг без исполнения · run: непрерывная самостройка · watch: живой дашборд</div></div>
     <div class="heart"><span class="hb">●</span> слежу за процессом · обновляю каждые 2.5с</div>
   </div></div>
  ${ready?'<div class="tbound" style="border-color:var(--success)">✓ ГОТОВ. Вставь команду в терминал — законный runner проводит узлы, каждый оставляет proof. Старт у тебя.</div>':'<div class="tbound">'+esc(t.truth_boundary||'')+'</div>'}`}

/* interactive force graph */
const cv=$('cv'),ctx=cv.getContext('2d');
let N=[],L=[],view={s:1,ox:0,oy:0},drag=null,pan=null,hover=null,sel=null,down=null,moved=0;
function fit(){const r=cv.parentElement.getBoundingClientRect();cv.width=r.width;cv.height=r.height;if(!view._init){view.ox=r.width/2;view.oy=r.height*0.46;view._init=1}}
addEventListener('resize',fit);fit();
const seed=s=>{let h=7;for(const c of s)h=(h*33+c.charCodeAt(0))%99991;return h/99991};
function mergeGraph(g){const m=new Map(N.map(n=>[n.id,n]));
 g.nodes.forEach(n=>{if(m.has(n.id)){Object.assign(m.get(n.id),{size:Math.max(n.size||6,m.get(n.id).size||6),color:n.color||m.get(n.id).color,authored:n.authored??m.get(n.id).authored})}else{n.x=(seed(n.id)-.5)*420;n.y=(seed(n.id+'y')-.5)*320;n.vx=0;n.vy=0;m.set(n.id,n)}});
 N=[...m.values()];const ids=new Set(N.map(n=>n.id)),lk=new Set(L.map(l=>l.source+'>'+l.target));
 g.links.forEach(l=>{if(ids.has(l.source)&&ids.has(l.target)&&!lk.has(l.source+'>'+l.target)){L.push(l);lk.add(l.source+'>'+l.target)}})}
const W2S=(x,y)=>[x*view.s+view.ox,y*view.s+view.oy],S2W=(x,y)=>[(x-view.ox)/view.s,(y-view.oy)/view.s];
function nodeAt(sx,sy){let b=null,bd=1e9;for(const n of N){const[px,py]=W2S(n.x,n.y),d=(px-sx)**2+(py-sy)**2,r=(n.size*view.s+7)**2;if(d<r&&d<bd){bd=d;b=n}}return b}
function sim(){if(!N.length)return;
 for(let i=0;i<N.length;i++)for(let k=i+1;k<N.length;k++){const a=N[i],b=N[k];let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy+.1,inv=1/Math.sqrt(d2),f=(a.group==='atom'||b.group==='atom'?160:520)/d2;a.vx+=dx*inv*f;a.vy+=dy*inv*f;b.vx-=dx*inv*f;b.vy-=dy*inv*f}
 L.forEach(l=>{const a=N.find(n=>n.id===l.source),b=N.find(n=>n.id===l.target);if(!a||!b)return;let dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)||1,rest=a.group==='core'||b.group==='core'?120:64,f=(d-rest)*.02;a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f});
 N.forEach(n=>{if(n===drag)return;n.vx+=(0-n.x)*.0016;n.vy+=(0-n.y)*.0016;n.x+=n.vx*=.84;n.y+=n.vy*=.84})}
function neigh(id){const s=new Set([id]);L.forEach(l=>{if(l.source===id)s.add(l.target);if(l.target===id)s.add(l.source)});return s}
function draw(){ctx.clearRect(0,0,cv.width,cv.height);const lit=sel?neigh(sel.id):null;
 L.forEach(l=>{const a=N.find(n=>n.id===l.source),b=N.find(n=>n.id===l.target);if(!a||!b)return;const[ax,ay]=W2S(a.x,a.y),[bx,by]=W2S(b.x,b.y),on=lit&&lit.has(a.id)&&lit.has(b.id);ctx.strokeStyle=on?'rgba(34,211,238,.5)':'rgba(125,136,147,'+(l.w>1?.2:.09)+')';ctx.lineWidth=on?1.6:1;ctx.beginPath();ctx.moveTo(ax,ay);ctx.lineTo(bx,by);ctx.stroke()});
 N.forEach(n=>{const[x,y]=W2S(n.x,n.y),r=n.size*view.s,dim=lit&&!lit.has(n.id);ctx.globalAlpha=dim?.22:1;const col=n.group==='core'?'#22D3EE':n.color||'#888';
   const puls=12+7*Math.abs(Math.sin(performance.now()/750));
   if(n.group==='core'){ctx.fillStyle='#22D3EE';ctx.shadowColor='#22D3EE';ctx.shadowBlur=puls;ctx.fillRect(x-r,y-r,r*2,r*2);ctx.shadowBlur=0}else{ctx.shadowColor=col;ctx.shadowBlur=n.group==='atom'?5:(n.authored?puls*0.7:11);ctx.fillStyle=col;ctx.beginPath();ctx.arc(x,y,r,0,7);ctx.fill();ctx.shadowBlur=0}
   if(n.authored){ctx.strokeStyle='#22D3EE';ctx.lineWidth=2;ctx.beginPath();ctx.arc(x,y,r+3.5,0,7);ctx.stroke()}
   if(n===hover||n===sel){ctx.strokeStyle='#E6EDF3';ctx.lineWidth=1.4;ctx.beginPath();ctx.arc(x,y,r+6,0,7);ctx.stroke()}
   if(n.group!=='atom'){ctx.globalAlpha=dim?.3:1;ctx.fillStyle=n.group==='core'?'#22D3EE':'#cfd6df';ctx.font=(n.group==='core'?'700 13px ':'600 11px ')+'ui-monospace,Menlo';ctx.fillText(n.label||'',x+r+5,y+4)}
   else if(n===hover){ctx.fillStyle='#aeb6c0';ctx.font='600 10px ui-monospace,Menlo';ctx.fillText((n.label||'')+'…',x+r+5,y+3)}ctx.globalAlpha=1})}
function loop(){sim();draw();requestAnimationFrame(loop)}loop();
cv.addEventListener('mousedown',e=>{const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;moved=0;down=nodeAt(mx,my);if(down)drag=down;else{pan={x:e.clientX,y:e.clientY};cv.classList.add('grabbing')}});
addEventListener('mousemove',e=>{const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
 if(drag){const[wx,wy]=S2W(mx,my);drag.x=wx;drag.y=wy;drag.vx=drag.vy=0;moved++}else if(pan){view.ox+=e.clientX-pan.x;view.oy+=e.clientY-pan.y;pan={x:e.clientX,y:e.clientY};moved++}else{hover=nodeAt(mx,my);cv.style.cursor=hover?'pointer':'grab'}});
addEventListener('mouseup',()=>{if(down&&moved<4)select(down);drag=null;pan=null;cv.classList.remove('grabbing');down=null});
cv.addEventListener('wheel',e=>{e.preventDefault();const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top,[wx,wy]=S2W(mx,my);view.s=Math.max(.35,Math.min(3,view.s*(e.deltaY<0?1.12:.89)));view.ox=mx-wx*view.s;view.oy=my-wy*view.s},{passive:false});
function select(n){sel=n;const s=$('sel');if(n.group==='atom')return;
 if(n.group==='core'){s.innerHTML='<span class="x" onclick="clearSel()">×</span><div class="tagline">ядро</div><h4>SOCC</h4><p>Суверенное ядро. Темы — его органы знания.</p>';s.classList.add('show');return}
 readPage(n.id,n.label)}
function clearSel(){sel=null;$('sel').classList.remove('show')}
function showDesign(){fetch('/design').then(r=>r.json()).then(d=>{const s=$('sel');
 if(!d.exists){s.innerHTML='<span class="x" onclick="clearSel()">×</span><p>дизайн-орган не найден</p>';s.classList.add('show');return}
 const roles=d.roles.map(r=>`<div class="ri"><span class="rk yes">✓</span><span><b>${esc(r.ru)}</b> <span style="color:var(--muted)">— ${esc(r.owns)}</span></span></div>`).join('');
 const done=(d.done||[]).map(x=>`<span class="badge exec" style="margin:2px 3px 0 0;display:inline-block">${esc(x)}</span>`).join('');
 const f=d.facts||{};
 const facts=`<div class="ri"><span class="rk yes">✓</span>рендереры: ${(f.renderers||[]).map(esc).join(', ')||'—'}</div>`+
  `<div class="ri"><span class="rk yes">✓</span>бренд-фронтиров (HTML): <b>${f.brand_frontiers_html||0}</b></div>`+
  `<div class="ri"><span class="rk ${f.design_tokens_css?'yes':'no'}">${f.design_tokens_css?'✓':'○'}</span>токены дизайна: ${esc(f.cortex_uses_canon||'')}</div>`;
 s.innerHTML=`<span class="x" onclick="clearSel()">×</span><div class="tagline">команда дизайна · факты, не слова</div><h4>ATELIER · ${esc(d.status||'')}</h4>
  <p style="color:var(--muted)">${esc(d.purpose)}</p>
  <div class="divider" style="margin:12px 0 7px">── 9 РОЛЕЙ СТУДИИ</div><div class="rlist">${roles}</div>
  <div class="divider" style="margin:12px 0 7px">── УЖЕ ОТГРУЖЕНО (proof)</div><div>${done}</div>
  <div class="divider" style="margin:12px 0 7px">── ДОКАЗАТЕЛЬСТВА НА ДИСКЕ</div><div class="rlist">${facts}</div>
  <div class="tbound" style="margin-top:12px;border-color:var(--success)">${esc(d.verdict)}</div>`;s.classList.add('show')})}
fetch('/graph').then(r=>r.json()).then(mergeGraph).catch(()=>{});refresh();
fetch('/self').then(r=>r.json()).then(s=>{const know=(s.self_model||'').split('\n').filter(l=>l.startsWith('## ')).slice(0,5).map(l=>l.replace(/^##\s*/,''));
 const want=(s.self_evolve||'').split('\n').filter(l=>/^###\s|REVIVE|MISSING|⭐/.test(l)).slice(0,3).map(l=>l.replace(/[#⭐🔴🟠🟡⚪`]/g,'').trim()).filter(Boolean);
 $('reflect').innerHTML=`<div style="flex:1"><div class="h">знаю о себе</div>${esc(know.join(' · '))}</div><div style="flex:1"><div class="h w">хочу</div>${esc(want.join(' · ').slice(0,140))}</div>`}).catch(()=>{});
</script></body></html>"""


if __name__ == "__main__":
    main()

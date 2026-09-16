#!/usr/bin/env python3
"""SOCC Memory Server v2 — local foreground helper for dashboard uploads (fast path).

Same lawful shape as v1, but /upload runs the FAST meaning-based spine v2 (~2.4s on a
warm cache) instead of the slow v1 ingest (~145s) — that slowness is exactly why
dashboard uploads used to hang. Pure Python stdlib, binds 127.0.0.1 only, you start it
and stop it (Ctrl+C). NOT a daemon, NOT exposed to the network.

  GET  /              -> serves spine2/dashboard.html
  POST /upload        -> body = raw bytes, header X-Filename = name
                         saves into SOVEREIGN/MEMORY/inbox/, runs spine v2 (rebuild wiki)
                         + dashboard v2 (refresh html), returns JSON
                         {ok, filename, sources, topics, cache_hits, build_time}

Truth boundary (SOCC-lawful): writes only inbox + spine2/.cache_v2 artifacts via the
existing scripts. No route authority / proof chain mutation, no entity birth, no
outbound network, no background loop. One operator-controlled process.

Usage:
  python3 scripts/socc/socc_memory_server_v2.py     # then open http://127.0.0.1:8788
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "SOVEREIGN" / "MEMORY" / "inbox"
SPINE2 = ROOT / "SOVEREIGN" / "WIKI" / "spine2"
DASH = SPINE2 / "dashboard.html"
CORE = SPINE2 / "core.html"
SELFEVOLVE = SPINE2 / "SELF_EVOLVE.md"
PROOF = SPINE2 / "_spine2_proof.json"
SPINE = ROOT / "scripts" / "socc" / "socc_memory_spine_v2.py"
DASHGEN = ROOT / "scripts" / "socc" / "socc_memory_dashboard_v2.py"

HOST, PORT = "127.0.0.1", 8788
ALLOWED = {".txt", ".md", ".eml", ".json"}
MAX_BYTES = 64 * 1024 * 1024


def safe_name(raw: str):
    name = Path(urllib.parse.unquote(raw or "")).name.strip()
    if not name or Path(name).suffix.lower() not in ALLOWED:
        return None
    name = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._ \-()]", "_", name)
    return name or None


def proof_totals(pr):
    """Canonical awareness snapshot from the spine proof — real numbers, no invention."""
    topics = pr.get("topics", {}) or {}
    per = {k: {"title": t.get("title", k), "facts": t.get("current", 0),
               "timeline": t.get("timeline", 0), "sources": t.get("sources", 0),
               "authored": bool(t.get("main_line_authored"))} for k, t in topics.items()}
    return {
        "facts": sum(t.get("current", 0) for t in topics.values()),
        "timeline": sum(t.get("timeline", 0) for t in topics.values()),
        "sources": pr.get("sources_scanned", 0),
        "junk": pr.get("junk_dropped", 0),
        "topics": per,
    }


def read_proof():
    return json.loads(PROOF.read_text(encoding="utf-8")) if PROOF.exists() else {}


def next_lawful_step():
    """Best-effort: the system's own proposed next step (top ⭐ from SELF_EVOLVE), honest if absent."""
    try:
        for ln in SELFEVOLVE.read_text(encoding="utf-8").splitlines():
            if "⭐" in ln:
                return ln.replace("⭐", "").replace("#", "").strip()[:160]
    except Exception:
        pass
    return None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/core", "/core.html") and CORE.exists():
            self._send(200, CORE.read_bytes(), "text/html; charset=utf-8")
        elif self.path in ("/", "/dashboard.html") and DASH.exists():
            self._send(200, DASH.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/dashboard.html" and DASH.exists():
            self._send(200, DASH.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/state":
            self._send(200, json.dumps({"ok": True, "state": proof_totals(read_proof()),
                                        "next_step": next_lawful_step()}, ensure_ascii=False))
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path != "/upload":
            return self._send(404, json.dumps({"ok": False, "error": "unknown endpoint"}))
        name = safe_name(self.headers.get("X-Filename", ""))
        if not name:
            return self._send(400, json.dumps({"ok": False, "error": "bad filename or type (.txt/.md/.eml/.json)"}))
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BYTES:
            return self._send(400, json.dumps({"ok": False, "error": "empty or too large (max 64MB)"}))
        data = self.rfile.read(length)

        before = proof_totals(read_proof())   # awareness BEFORE feeding

        INBOX.mkdir(parents=True, exist_ok=True)
        (INBOX / name).write_bytes(data)

        t0 = time.time()
        p1 = subprocess.run([sys.executable, str(SPINE)], capture_output=True, text=True)
        subprocess.run([sys.executable, str(DASHGEN)], capture_output=True, text=True)
        dt = round(time.time() - t0, 1)
        after = proof_totals(read_proof())     # awareness AFTER

        # canonical delta — no invention; duplicates simply don't grow it
        grown = {}
        for k, a in after["topics"].items():
            b = before["topics"].get(k, {"facts": 0, "timeline": 0, "sources": 0})
            df, dt_, ds = a["facts"] - b["facts"], a["timeline"] - b["timeline"], a["sources"] - b["sources"]
            if df or dt_ or ds:
                grown[k] = {"title": a["title"], "facts": df, "timeline": dt_, "sources": ds}
        delta = {
            "facts": after["facts"] - before["facts"],
            "timeline": after["timeline"] - before["timeline"],
            "sources": after["sources"] - before["sources"],
        }
        duplicate = (delta["facts"] == 0 and delta["timeline"] == 0 and delta["sources"] == 0)
        ok = p1.returncode == 0
        self._send(200 if ok else 500, json.dumps({
            "ok": ok, "filename": name, "build_time": dt,
            "duplicate": duplicate,
            "before": before, "after": after, "delta": delta, "grown": grown,
            "next_step": next_lawful_step(),
            "error": None if ok else (p1.stderr or "spine v2 failed")[:300],
        }, ensure_ascii=False))


def main():
    INBOX.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print("SOCC MEMORY SERVER v2 — local, foreground (Ctrl+C to stop)")
    print(f"  open   : http://{HOST}:{PORT}")
    print(f"  inbox  : {INBOX}")
    print("  path   : upload -> inbox -> FAST spine v2 (~2.4s) -> dashboard refresh")
    print("  truth  : 127.0.0.1 only · no network out · no daemon · meaning-based · no-LLM")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        srv.shutdown()


if __name__ == "__main__":
    main()

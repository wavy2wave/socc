#!/usr/bin/env python3
"""SOCC Memory Server — local foreground helper so you can upload files from the dashboard.

Pure Python stdlib (no FastAPI/uvicorn/npm). Binds 127.0.0.1 only. You start it,
you stop it (Ctrl+C). NOT a 24/7 daemon, NOT exposed to the network.

  GET  /                 -> serves the generated dashboard.html
  POST /upload           -> body = raw file bytes, header X-Filename = name
                            saves into SOVEREIGN/MEMORY/inbox/, runs the ingest
                            workhorse (scan->было/стало->ingest->wiki->dashboard),
                            returns JSON {ok, filename, counts, claims_added}

Truth boundary (SOCC-lawful): writes only into the inbox + runs the existing ingest
script. Does NOT touch route authority / proof chain, births no Entity/ANNA, makes
no outbound network call, runs no background loop. One process, operator-controlled.

Usage:
  python3 scripts/socc/socc_memory_server_v1.py        # then open http://127.0.0.1:8787
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "SOVEREIGN" / "MEMORY" / "inbox"
DASH = ROOT / "SOVEREIGN" / "WIKI" / "spine" / "dashboard.html"
RUN_JSON = ROOT / "SOVEREIGN" / "WIKI" / "spine" / "_last_ingest_run.json"
INGEST = ROOT / "scripts" / "socc" / "socc_memory_ingest_v1.py"

HOST, PORT = "127.0.0.1", 8787
ALLOWED = {".txt", ".md", ".eml", ".json"}
MAX_BYTES = 64 * 1024 * 1024


def safe_name(raw: str) -> str | None:
    name = Path(urllib.parse.unquote(raw or "")).name.strip()
    if not name:
        return None
    if Path(name).suffix.lower() not in ALLOWED:
        return None
    name = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._ \-()]", "_", name)
    return name or None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass  # quiet

    def do_GET(self):
        if self.path in ("/", "/dashboard.html"):
            if DASH.exists():
                self._send(200, DASH.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(404, "dashboard.html not built — run socc_memory_dashboard_v1.py", "text/plain; charset=utf-8")
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

        INBOX.mkdir(parents=True, exist_ok=True)
        (INBOX / name).write_bytes(data)

        proc = subprocess.run([sys.executable, str(INGEST)], capture_output=True, text=True)
        run = json.loads(RUN_JSON.read_text(encoding="utf-8")) if RUN_JSON.exists() else {}
        ok = proc.returncode == 0
        self._send(200 if ok else 500, json.dumps({
            "ok": ok, "filename": name,
            "counts": run.get("counts", {}), "claims_added": run.get("claims_added", 0),
            "error": None if ok else "ingest failed",
        }, ensure_ascii=False))


def main():
    INBOX.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print("SOCC MEMORY SERVER — local, foreground (Ctrl+C to stop)")
    print(f"  open    : http://{HOST}:{PORT}")
    print(f"  inbox   : {INBOX}")
    print(f"  upload  : drag a file onto the dashboard's «Залить файл» zone")
    print("  truth   : 127.0.0.1 only · no network out · no daemon · writes inbox + runs ingest")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        srv.shutdown()


if __name__ == "__main__":
    main()

"""Local OpenAI-compatible gateway over the energy queue.

VS Code (Cline / Continue / any OpenAI client) points its baseURL at this
server. Each request is fueled by the next live key in the vault queue, with
failover across providers. The client never sees the real keys — it just talks
to http://localhost:<port>/v1.

    python -m core.energy serve [port]
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .router import Router
from . import store

DEFAULT_PORT = 8787


def _load_env() -> None:
    for k, v in store._read_env().items():
        os.environ.setdefault(k, v)


class _Handler(BaseHTTPRequestHandler):
    router: Router = None  # set on the server class

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quieter logs
        pass

    def do_GET(self):
        if self.path.rstrip("/") in ("/health", "/v1/health"):
            return self._send(200, {"status": "ok", "gateway": "socc-energy"})
        if self.path.rstrip("/") == "/v1/models":
            from .providers import by_priority
            data = [{"id": p.default_model, "object": "model", "owned_by": p.name}
                    for p in by_priority()]
            return self._send(200, {"object": "list", "data": data})
        return self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if self.path.rstrip("/") != "/v1/chat/completions":
            return self._send(404, {"error": {"message": "unknown route"}})
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n).decode() or "{}")
        except Exception as e:
            return self._send(400, {"error": {"message": f"bad json: {e}"}})

        messages = req.get("messages") or []
        model = req.get("model") or None
        res = self.router.chat(messages, model=model)

        if res.ok:
            return self._send(200, {
                "id": "socc-energy",
                "object": "chat.completion",
                "model": f"{res.provider}:{res.model}",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": res.text},
                    "finish_reason": "stop",
                }],
                "x_socc_route": res.trace,
            })
        return self._send(502, {
            "error": {"message": res.error, "type": "all_fuel_exhausted"},
            "x_socc_route": res.trace,
        })


def serve(port: int = DEFAULT_PORT) -> int:
    _load_env()
    _Handler.router = Router()
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    base = f"http://127.0.0.1:{port}/v1"
    print(f"SOCC energy gateway → {base}")
    print("VS Code (Cline/Continue): set this as the OpenAI Base URL, any api key.")
    print("Ctrl-C to stop.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0

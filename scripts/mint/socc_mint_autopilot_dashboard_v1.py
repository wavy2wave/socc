#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT AUTOPILOT dashboard V1 — ПУЛЬТ НАБЛЮДАТЕЛЯ (очередь approve + соревнование вселенных + первый ₽).

Оператор видит, что агенты НАШЛИ и НАПИСАЛИ (живым мозгом), и одобряет отправку одним кликом. Ничего не
уходит клиенту без approve (RUBICON). Также показывает само-модель кластера: реальные ₽ vs симуляция,
ранг вселенных, следующий законный шаг + прозрачный лог отрезанного (BLOCKED/SKIP — фронт сам себя полицует).

Foreground HTTP (без демона, Ctrl-C стоп). Порт: env MINT_AP_DASH_PORT (умолч. 8793).
Очередь: та же, что у autopilot (env MINT_AUTOPILOT_QUEUE). Approve вызывает autopilot.approve (не шлёт сам).
"""
import os
import sys
import json
from html import escape
from urllib.parse import parse_qs
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import socc_mint_autopilot_v1 as autopilot  # noqa: E402
import socc_mint_self_v1 as selfmod          # noqa: E402

PORT = int(os.environ.get("MINT_AP_DASH_PORT", "8793"))


def _read_queue():
    q = autopilot.QUEUE
    if not q.exists():
        return []
    out = []
    for ln in q.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out


def gather_state():
    rows = _read_queue()
    queued = [r for r in rows if r.get("status") == "QUEUED"]
    pending = [r for r in queued if not r.get("approved")]
    approved = [r for r in queued if r.get("approved")]
    blocked = [r for r in rows if r.get("status") == "BLOCKED"]
    skipped = [r for r in rows if r.get("status") == "SKIP"]
    return {"queue_path": str(autopilot.QUEUE), "pending": pending[-50:], "approved": approved[-50:],
            "blocked": blocked[-20:], "skipped": skipped[-20:], "self": selfmod.self_status()}


def render_html(s):
    st = s["self"]
    m = st["money"]
    rank = "".join(
        f"<tr><td>{i+1}</td><td><b>{escape(b['venture'])}</b></td><td>{b['verified_tx']}</td>"
        f"<td class=g>{b['verified_profit']:.0f} ₽</td><td>{'—' if b['roi'] is None else format(b['roi'],'.3f')}</td></tr>"
        for i, b in enumerate(st["universes"])) or "<tr><td colspan=5 class=dim>вселенных пока нет verified</td></tr>"
    pend = "".join(
        f"<div class=card><div class=row><div><span class=tag>{escape(r.get('service',''))}</span> "
        f"<span class=mono>{escape(r.get('lead_ref',''))}</span> · score {r.get('score',0):.0f}</div>"
        f"<form method=POST action=/approve style=margin:0>"
        f"<input type=hidden name=id value='{escape(r.get('id',''))}'>"
        f"<button class=approve>✅ Одобрить отправку</button></form></div>"
        f"<div class=draft>{escape(r.get('draft',''))}</div></div>"
        for r in reversed(s["pending"])) or "<div class=dim>нет черновиков в ожидании — запусти коннекторы/autopilot</div>"
    appr = "".join(f"<li><span class=tag>{escape(r.get('service',''))}</span> {escape(r.get('lead_ref',''))} "
                   f"<span class=g>✓ одобрено</span> <span class=dim>(отправляет оператор/офиц. API)</span></li>"
                   for r in reversed(s["approved"])) or "<li class=dim>пока нет одобренных</li>"
    return f"""<!doctype html><html lang=ru><head><meta charset=utf-8><title>MINT — пульт наблюдателя</title>
<meta http-equiv=refresh content=20>
<style>
 body{{background:#0d1117;color:#e6edf3;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:24px;max-width:960px}}
 h1{{font-size:20px;margin:0 0 2px}} h3{{margin:18px 0 8px}} .sub{{color:#8b949e;margin-bottom:16px}}
 .big{{font-size:30px;font-weight:700;color:#3fb950}} .g{{color:#3fb950}} .dim{{color:#8b949e}}
 .mono{{font-family:ui-monospace,monospace;font-size:12px;color:#8b949e}}
 table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;padding:6px 9px;border-bottom:1px solid #21262d}} th{{color:#8b949e;font-size:12px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin-bottom:12px}}
 .row{{display:flex;justify-content:space-between;align-items:center;gap:12px}}
 .tag{{background:#1f6feb33;color:#79c0ff;padding:1px 8px;border-radius:10px;font-size:12px}}
 .draft{{margin-top:10px;white-space:pre-wrap;color:#c9d1d9;border-left:3px solid #30363d;padding-left:10px}}
 .approve{{background:#238636;color:#fff;border:0;border-radius:8px;padding:7px 12px;font-weight:600;cursor:pointer}}
 ul{{padding-left:16px}} li{{margin:3px 0}}
</style></head><body>
<h1>🛰 MINT — пульт наблюдателя</h1>
<div class=sub>агенты нашли и написали · ты одобряешь · очередь: <span class=mono>{escape(s['queue_path'])}</span></div>

<div class=card>
  <div>Реальные деньги (verified из реального источника)</div>
  <div class=big>{m['real_verified_profit']:.0f} ₽</div>
  <div class=dim>симуляция (песочница): {m['simulated_verified_profit']:.0f} ₽ · честность леджера: {m['ledger_honesty']}</div>
  <div class=dim style=margin-top:6px>следующий шаг: {escape(st['next_lawful_step'])}</div>
</div>

<h3>🏆 Соревнование вселенных</h3>
<table><tr><th>#</th><th>вселенная</th><th>verified</th><th>проверено ₽</th><th>ROI</th></tr>{rank}</table>

<h3>✍️ Очередь на одобрение ({len(s['pending'])}) — агент НЕ отправит без клика</h3>
{pend}

<h3>✅ Одобренные</h3><ul>{appr}</ul>

<div class=dim style=margin-top:14px>отрезано фронтом: BLOCKED {len(s['blocked'])} (спам/фейк/ToS) · SKIP {len(s['skipped'])} (слабая маржа) — самополицейский лог</div>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _redirect(self):
        self.send_response(302); self.send_header("Location", "/"); self.end_headers()

    def do_POST(self):
        if self.path.startswith("/approve"):
            n = int(self.headers.get("Content-Length", 0) or 0)
            data = parse_qs(self.rfile.read(n).decode("utf-8")) if n else {}
            qid = (data.get("id") or [""])[0]
            if qid:
                autopilot.approve(qid)  # метит approved; НЕ отправляет
            return self._redirect()
        self.send_response(404); self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/state"):
            body = json.dumps(gather_state(), ensure_ascii=False).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            return
        body = render_html(gather_state()).encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


if __name__ == "__main__":
    if "--once" in sys.argv:
        print(json.dumps(gather_state(), ensure_ascii=False, indent=2)[:1500])
        sys.exit(0)
    print(f"MINT пульт наблюдателя → http://127.0.0.1:{PORT}  (Ctrl-C стоп) · очередь: {autopilot.QUEUE}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

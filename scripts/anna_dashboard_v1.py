#!/usr/bin/env python3
"""
ANNA Operator Dashboard V1 — a professional control panel for the operator.

A local, dependency-free HTTP server that renders ANNA's live state: system pulse (brain heartbeat,
latency, leads, clients, safety), the lead inbox, client dossiers (with mood/rapport/fears), upcoming
appointments, and proactive reminder drafts. Read-mostly, with two operator actions: mark a lead seen,
and draft proactive reminders.

It reuses anna_runtime_v1.py for paths + helpers (single source of truth). No network exposure beyond
localhost; no daemon claims — just a panel you open while you work.

Usage:
  python3 scripts/anna_dashboard_v1.py            # serve on http://127.0.0.1:8790
  ANNA_DASH_PORT=9000 python3 scripts/anna_dashboard_v1.py
"""
import os, sys, json, importlib.util as _ilu
from pathlib import Path
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOTDIR = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("anna_runtime", ROOTDIR / "anna_runtime_v1.py")
A = _ilu.module_from_spec(_spec); _spec.loader.exec_module(A)

MSK = timezone(timedelta(hours=3))
PORT = int(os.environ.get("ANNA_DASH_PORT", "8790"))


def _msk_date(iso):
    try:
        return datetime.fromisoformat(iso).astimezone(MSK).date()
    except Exception:
        return None


def _age_s(iso):
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except Exception:
        return None


def _tokens_summary():
    """Best-effort token spend from the ledger module — gracefully degrades to None."""
    m = getattr(A, "LEDGER_MOD", None)
    if not m:
        return None
    for fn in ("summary", "totals", "report", "stats"):
        f = getattr(m, fn, None)
        if callable(f):
            try:
                return f()
            except Exception:
                pass
    return None


def gather_state():
    today = datetime.now(MSK).date()
    leads = list(reversed(A._read_jsonl(A.ADMIN_INBOX)))
    leads_today = sum(1 for L in leads if _msk_date(L.get("ts", "")) == today)

    clients, appts = [], []
    for cf in sorted(A.CLIENTS.glob("*.json")) if A.CLIENTS.exists() else []:
        d = A.rj(cf)
        if not d:
            continue
        capp = d.get("appointments") or []
        clients.append({
            "client_id": d.get("client_id") or cf.stem,
            "name": d.get("name") or "", "rapport": d.get("rapport") or "",
            "warmth": d.get("warmth") or "", "last_mood": d.get("last_mood") or "",
            "portrait": d.get("portrait") or "", "fears": d.get("fears") or [],
            "important": d.get("important") or [], "preferences": d.get("preferences") or [],
            "appts": len(capp), "last_seen": d.get("last_seen_utc") or "",
            "turns": len([h for h in (d.get("history") or []) if h.get("role") == "user"]),
        })
        for a in capp:
            appts.append({"client_id": d.get("client_id") or cf.stem, "name": d.get("name") or a.get("name", ""),
                          "phone": d.get("phone") or a.get("phone", ""), "service": a.get("service", ""),
                          "preferred_time": a.get("preferred_time", ""), "status": a.get("status", "requested"),
                          "ts": a.get("ts", "")})
    clients.sort(key=lambda c: c.get("last_seen", ""), reverse=True)
    appts.sort(key=lambda a: a.get("ts", ""), reverse=True)
    appts_today = sum(1 for a in appts if _msk_date(a.get("ts", "")) == today)

    reminders = list(reversed(A._read_jsonl(A.REMINDERS)))
    safety = []
    slog = getattr(A, "SAFETY_LOG", None)
    if slog:
        safety = list(reversed(A._read_jsonl(slog)))[:20]

    brain = A.rj(A.BRAIN_STATUS)
    brain_age = _age_s(brain.get("ts", "")) if brain else None

    return {
        "pulse": {
            "brain_ok": bool(brain.get("ok")) if brain else None,
            "brain_latency_ms": brain.get("latency_ms") if brain else None,
            "brain_model": brain.get("model") if brain else None,
            "brain_age_s": round(brain_age) if brain_age is not None else None,
            "brain_error": brain.get("error") if brain else "",
            "leads_today": leads_today, "leads_total": len(leads),
            "clients": len(clients), "appts_total": len(appts), "appts_today": appts_today,
            "unseen_leads": sum(1 for L in leads if not L.get("seen")),
            "safety_violations": len(safety), "reminders": len(reminders),
            "tokens": _tokens_summary(),
            "server_time_msk": datetime.now(MSK).strftime("%Y-%m-%d %H:%M:%S МСК"),
        },
        "leads": leads[:50], "clients": clients[:100],
        "appointments": appts[:50], "reminders": reminders[:50], "safety": safety,
    }


def mark_seen(ts):
    rows = A._read_jsonl(A.ADMIN_INBOX)
    hit = False
    for r in rows:
        if r.get("ts") == ts:
            r["seen"] = True; hit = True
    if hit:
        A.ADMIN_INBOX.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return hit


def draft_all_followups():
    n = 0
    for cf in sorted(A.CLIENTS.glob("*.json")) if A.CLIENTS.exists() else []:
        d = A.rj(cf)
        if not (d.get("appointments")):
            continue
        try:
            n += len(A.Anna(client_id=d.get("client_id") or cf.stem).proactive_followups())
        except Exception:
            pass
    return n


PAGE = """<!doctype html><html lang=ru><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>ANNA · Operator Console</title>
<style>
:root{--bg:#0b0f17;--panel:#121826;--panel2:#0e1422;--line:#1e2a3f;--ink:#e8eef9;--mut:#8aa0c2;--accent:#4cc2ff;--ok:#39d98a;--warn:#ffb454;--bad:#ff6b6b;--chip:#1a2333}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial}
header{display:flex;align-items:center;gap:14px;padding:14px 20px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#10182a,#0b0f17);position:sticky;top:0;z-index:5}
.logo{font-weight:700;letter-spacing:.5px;font-size:16px}.logo b{color:var(--accent)}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:6px;box-shadow:0 0 8px currentColor}
.dot.ok{color:var(--ok);background:var(--ok)}.dot.warn{color:var(--warn);background:var(--warn)}.dot.bad{color:var(--bad);background:var(--bad)}.dot.idle{color:#5a6b86;background:#5a6b86;box-shadow:none}
.clock{margin-left:auto;color:var(--mut);font-variant-numeric:tabular-nums}
.pulse{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;padding:16px 20px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.stat .k{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.4px}
.stat .v{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:2px}
.stat .sub{color:var(--mut);font-size:12px}
.grid{display:grid;grid-template-columns:1.3fr 1fr;gap:16px;padding:0 20px 24px}
@media(max-width:980px){.grid{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.card h2{margin:0;padding:12px 16px;font-size:13px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:8px}
.card .body{max-height:420px;overflow:auto}
.row{padding:11px 16px;border-bottom:1px solid var(--panel2);display:flex;gap:10px;align-items:flex-start}
.row:last-child{border-bottom:0}
.row .main{flex:1;min-width:0}
.row .name{font-weight:600}.row .meta{color:var(--mut);font-size:12.5px;margin-top:2px}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;background:var(--chip);color:var(--mut);font-size:11.5px;margin:2px 4px 0 0;white-space:nowrap}
.pill.ok{color:#0b0f17;background:var(--ok)}.pill.warn{color:#0b0f17;background:var(--warn)}.pill.bad{color:#0b0f17;background:var(--bad)}.pill.new{color:#0b0f17;background:var(--accent)}
.btn{cursor:pointer;border:1px solid var(--line);background:var(--chip);color:var(--ink);padding:5px 10px;border-radius:8px;font-size:12px}
.btn:hover{border-color:var(--accent)}
.toolbar{display:flex;gap:8px;padding:10px 20px}
.empty{padding:20px 16px;color:var(--mut)}
.draft{color:#cfe0ff;font-size:13px;margin-top:4px;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
small.mut{color:var(--mut)}
</style></head><body>
<header>
  <span class=logo>AN<b>NA</b> · Operator Console</span>
  <span id=brain><span class="dot idle"></span>brain</span>
  <span id=unseen></span>
  <span class=clock id=clock>—</span>
</header>
<div class=toolbar>
  <button class=btn onclick="followups()">✨ Сгенерировать напоминания</button>
  <button class=btn onclick="load()">⟳ Обновить</button>
  <small class=mut id=tok></small>
</div>
<div class=pulse id=pulse></div>
<div class=grid>
  <div class=card><h2>📥 Лиды / входящие</h2><div class=body id=leads></div></div>
  <div class=card><h2>👤 Клиенты</h2><div class=body id=clients></div></div>
  <div class=card><h2>📅 Записи</h2><div class=body id=appts></div></div>
  <div class=card><h2>🔔 Напоминания (черновики)</h2><div class=body id=reminders></div></div>
  <div class="card" style="grid-column:1/-1"><h2>🛡 Безопасность (нарушения инвариантов)</h2><div class=body id=safety></div></div>
</div>
<script>
const $=id=>document.getElementById(id);
const esc=s=>(s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
function ago(s){if(s==null)return "";if(s<60)return Math.round(s)+"с назад";if(s<3600)return Math.round(s/60)+"м назад";if(s<86400)return Math.round(s/3600)+"ч назад";return Math.round(s/86400)+"д назад";}
function stat(k,v,sub){return `<div class=stat><div class=k>${k}</div><div class=v>${v}</div><div class=sub>${sub||""}</div></div>`}
async function load(){
  let s; try{s=await (await fetch('/api/state')).json()}catch(e){return}
  const p=s.pulse;
  // brain dot
  let cls='idle',txt='нет данных';
  if(p.brain_ok===true){cls=(p.brain_age_s!=null&&p.brain_age_s<900)?'ok':'warn';txt=`${p.brain_model||''} · ${p.brain_latency_ms||'?'}мс · ${ago(p.brain_age_s)}`}
  else if(p.brain_ok===false){cls='bad';txt='сбой: '+esc(p.brain_error||'')}
  $('brain').innerHTML=`<span class="dot ${cls}"></span>brain ${txt}`;
  $('unseen').innerHTML=p.unseen_leads?`<span class="pill new">${p.unseen_leads} новых лидов</span>`:'';
  $('clock').textContent=p.server_time_msk;
  $('tok').textContent=p.tokens?('токены: '+JSON.stringify(p.tokens)):'';
  $('pulse').innerHTML=[
    stat('Лиды сегодня',p.leads_today,`всего ${p.leads_total}`),
    stat('Записи сегодня',p.appts_today,`всего ${p.appts_total}`),
    stat('Клиенты',p.clients,'в памяти'),
    stat('Не просмотрено',p.unseen_leads,'лидов'),
    stat('Напоминания',p.reminders,'в очереди'),
    stat('Безопасность',p.safety_violations,p.safety_violations?'⚠ проверь':'чисто'),
  ].join('');
  $('leads').innerHTML=s.leads.length?s.leads.map(L=>`<div class=row><div class=main>
     <div class=name>${esc(L.name)||'без имени'} ${L.seen?'':'<span class="pill new">new</span>'}</div>
     <div class=meta>${esc(L.phone)||'—'} · ${esc(L.service)||'—'} · ${esc(L.preferred_time)||''} <small class=mut>${ago_iso(L.ts)}</small></div></div>
     ${L.seen?'':`<button class=btn onclick="seen('${L.ts}')">✓</button>`}</div>`).join(''):'<div class=empty>Пока нет лидов</div>';
  $('clients').innerHTML=s.clients.length?s.clients.map(c=>`<div class=row><div class=main>
     <div class=name>${esc(c.name)||esc(c.client_id)}</div>
     <div class=meta>${esc(c.portrait)||'—'}</div>
     <div>${c.rapport?`<span class=pill>${esc(c.rapport)}</span>`:''}${c.last_mood&&c.last_mood!='neutral'?`<span class=pill>${esc(c.last_mood)}</span>`:''}${c.appts?`<span class="pill ok">записей: ${c.appts}</span>`:''}${(c.fears||[]).slice(0,2).map(f=>`<span class="pill warn">${esc(f)}</span>`).join('')}${(c.important||[]).map(f=>`<span class="pill bad">${esc(f)}</span>`).join('')}</div>
     </div></div>`).join(''):'<div class=empty>Пока нет клиентов</div>';
  $('appts').innerHTML=s.appointments.length?s.appointments.map(a=>`<div class=row><div class=main>
     <div class=name>${esc(a.name)||esc(a.client_id)}</div>
     <div class=meta>${esc(a.service)||'—'} · ${esc(a.preferred_time)||''} · ${esc(a.phone)||''}</div></div>
     <span class="pill ${a.status=='requested'?'':'ok'}">${esc(a.status)}</span></div>`).join(''):'<div class=empty>Пока нет записей</div>';
  $('reminders').innerHTML=s.reminders.length?s.reminders.map(r=>`<div class=row><div class=main>
     <div class=name>${esc(r.name)||esc(r.client_id)} <small class=mut>${esc(r.service)} ${esc(r.preferred_time)}</small></div>
     <div class=draft>${esc(r.draft)}</div></div></div>`).join(''):'<div class=empty>Нет черновиков. Нажми «Сгенерировать напоминания».</div>';
  $('safety').innerHTML=s.safety.length?s.safety.map(v=>`<div class=row><div class=main>
     <div class=name style="color:var(--bad)">${(v.violations||[]).join(', ')}</div>
     <div class=meta>${esc(v.client)} · ${esc((v.text||'').slice(0,140))}</div></div></div>`).join(''):'<div class=empty>Нарушений нет ✅</div>';
}
function ago_iso(ts){const d=Date.parse(ts);if(isNaN(d))return"";return ago((Date.now()-d)/1000)}
async function seen(ts){await fetch('/api/seen',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({ts})});load()}
async function followups(){const b=event.target;b.textContent='…генерирую';b.disabled=true;try{const r=await (await fetch('/api/followups',{method:'POST'})).json();b.textContent='✨ Готово: +'+r.drafted}catch(e){b.textContent='ошибка'}setTimeout(()=>{b.textContent='✨ Сгенерировать напоминания';b.disabled=false},2500);load()}
load();setInterval(load,4000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", ctype + ("; charset=utf-8" if "json" in ctype or "html" in ctype else ""))
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            return self._send(200, PAGE, "text/html")
        if path == "/api/state":
            return self._send(200, json.dumps(gather_state(), ensure_ascii=False))
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        path = urlparse(self.path).path
        n = int(self.headers.get("content-length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        if path == "/api/seen":
            try:
                ts = json.loads(raw or b"{}").get("ts", "")
            except Exception:
                ts = ""
            return self._send(200, json.dumps({"ok": mark_seen(ts)}))
        if path == "/api/followups":
            return self._send(200, json.dumps({"drafted": draft_all_followups()}))
        return self._send(404, json.dumps({"error": "not found"}))


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"ANNA Operator Console → http://127.0.0.1:{PORT}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()

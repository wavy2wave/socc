"""WAVE — кабинет клиента. Минималистичный дашборд в каноне SOCC.

Клиент вводит свой токен → видит тариф, остаток, срок, инструкцию подключения.
Ничего лишнего: одно поле ввода, одна карточка статуса, блок «как подключить».

Канон: stdlib-only (http.server), тёмная матрица SOCC, никакого JS-фреймворка.
Токен хранится только в localStorage браузера клиента, на сервер уходит
единственным заголовком и нигде не логируется.

Запуск:  WAVE_DATA_DIR=./data python3 -m gateway.dashboard
"""
from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.quota import QuotaStore, KEY_PREFIX  # noqa: E402

HOST = os.environ.get("WAVE_DASH_HOST", "127.0.0.1")
PORT = int(os.environ.get("WAVE_DASH_PORT", "8791"))
DATA_DIR = Path(os.environ.get("WAVE_DATA_DIR",
                               Path(__file__).resolve().parent.parent / "data"))
PUBLIC_GW = os.environ.get("WAVE_PUBLIC_GATEWAY", "http://127.0.0.1:8790/v1")
SHOP_NAME = os.environ.get("WAVE_SHOP_NAME", "WAVE SHOP")
SUPPORT = os.environ.get("WAVE_SUPPORT_CONTACT", "@wave_support")
BOT_LINK = os.environ.get("WAVE_BOT_LINK", "")

_store = QuotaStore(DATA_DIR)


def human_tokens(n: int) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + " млн"
    if n >= 1_000:
        return f"{n // 1000} тыс"
    return str(n)


def human_left(seconds: int) -> str:
    if seconds <= 0:
        return "истёк"
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} дн {h} ч"
    if h:
        return f"{h} ч {m} мин"
    return f"{m} мин"


PAGE = """<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__SHOP__ — кабинет</title>
<style>
  :root{
    --bg:#0b0f14; --panel:#121821; --line:#1f2937; --ink:#e6edf3;
    --dim:#8b9aab; --acc:#4ade80; --warn:#fbbf24; --bad:#f87171;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    display:flex;justify-content:center;padding:32px 16px}
  .wrap{width:100%;max-width:680px}
  h1{font-size:19px;letter-spacing:.14em;text-transform:uppercase;margin:0 0 4px}
  .sub{color:var(--dim);font-size:13px;margin-bottom:26px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:20px;margin-bottom:16px}
  label{display:block;color:var(--dim);font-size:12px;letter-spacing:.1em;
    text-transform:uppercase;margin-bottom:8px}
  input{width:100%;padding:13px 14px;background:#0b0f14;border:1px solid var(--line);
    border-radius:8px;color:var(--ink);font:inherit;outline:none}
  input:focus{border-color:var(--acc)}
  button{margin-top:12px;width:100%;padding:13px;background:var(--acc);border:0;
    border-radius:8px;color:#06210f;font:inherit;font-weight:700;cursor:pointer;
    letter-spacing:.06em}
  button:hover{filter:brightness(1.08)}
  .row{display:flex;justify-content:space-between;align-items:baseline;
    padding:11px 0;border-bottom:1px solid var(--line)}
  .row:last-child{border-bottom:0}
  .k{color:var(--dim);font-size:13px}
  .v{font-weight:700}
  .big{font-size:30px;font-weight:700;letter-spacing:-.02em}
  .badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:11px;
    letter-spacing:.1em;text-transform:uppercase}
  .ok{background:rgba(74,222,128,.14);color:var(--acc)}
  .warn{background:rgba(251,191,36,.14);color:var(--warn)}
  .bad{background:rgba(248,113,113,.14);color:var(--bad)}
  .bar{height:7px;background:#0b0f14;border-radius:99px;overflow:hidden;margin-top:12px}
  .bar>i{display:block;height:100%;background:var(--acc);border-radius:99px}
  pre{background:#0b0f14;border:1px solid var(--line);border-radius:8px;padding:14px;
    overflow-x:auto;font-size:12.5px;color:#cfe3ff;margin:10px 0 0}
  .muted{color:var(--dim);font-size:12.5px}
  a{color:var(--acc)}
  .hide{display:none}
  .err{color:var(--bad);font-size:13px;margin-top:10px}
</style></head><body><div class="wrap">

  <h1>__SHOP__</h1>
  <div class="sub">Личный кабинет · доступ к ИИ</div>

  <div class="card" id="auth">
    <label>Ваш ключ доступа</label>
    <input id="tok" placeholder="__PREFIX__..." autocomplete="off" spellcheck="false">
    <button onclick="load()">Войти</button>
    <div class="err hide" id="err"></div>
    <div class="muted" style="margin-top:14px">
      Ключ выдаётся в боте после оплаты.__BOTLINK__
    </div>
  </div>

  <div id="panel" class="hide">
    <div class="card">
      <div class="row">
        <span class="k">Тариф</span>
        <span class="v" id="plan">—</span>
      </div>
      <div class="row">
        <span class="k">Статус</span>
        <span id="status">—</span>
      </div>
      <div class="row" id="expRow">
        <span class="k">Осталось времени</span>
        <span class="v" id="exp">—</span>
      </div>
    </div>

    <div class="card">
      <div class="k" id="quotaLabel">Остаток токенов</div>
      <div class="big" id="quota">—</div>
      <div class="bar"><i id="bar" style="width:0%"></i></div>
      <div class="muted" id="quotaNote" style="margin-top:10px"></div>
      <div class="row" style="margin-top:14px">
        <span class="k">Запросов сделано</span><span class="v" id="reqs">0</span>
      </div>
    </div>

    <div class="card">
      <label>Как подключить</label>
      <div class="muted">Поменяйте в своём клиенте две вещи — адрес и ключ:</div>
      <pre id="snippet"></pre>
      <div class="muted">Работает везде, где есть OpenAI-совместимый режим:
        Cursor, Continue, curl, Python/JS SDK.</div>
    </div>

    <div class="card">
      <div class="row"><span class="k">Поддержка</span><span class="v">__SUPPORT__</span></div>
      <button onclick="logout()" style="background:#1f2937;color:var(--ink);margin-top:14px">Выйти</button>
    </div>
  </div>

<script>
const GW = "__GW__";
function esc(s){return String(s).replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}
function logout(){localStorage.removeItem('wave_token');location.reload()}
async function load(){
  const tok=(document.getElementById('tok').value||'').trim();
  const err=document.getElementById('err');
  if(!tok){err.textContent='Введите ключ.';err.classList.remove('hide');return}
  try{
    const r=await fetch('/api/status',{headers:{'Authorization':'Bearer '+tok}});
    if(!r.ok){err.textContent='Ключ не найден или доступ приостановлен.';
      err.classList.remove('hide');return}
    const d=await r.json();
    localStorage.setItem('wave_token',tok);
    render(d,tok);
  }catch(e){err.textContent='Сервис недоступен. Попробуйте позже.';err.classList.remove('hide')}
}
function render(d,tok){
  document.getElementById('auth').classList.add('hide');
  document.getElementById('panel').classList.remove('hide');
  document.getElementById('plan').textContent=d.title||'—';
  document.getElementById('reqs').textContent=d.requests||0;

  const st=document.getElementById('status');
  if(!d.enabled){st.innerHTML='<span class="badge bad">приостановлен</span>'}
  else if(d.expired){st.innerHTML='<span class="badge bad">истёк</span>'}
  else{st.innerHTML='<span class="badge ok">активен</span>'}

  const expRow=document.getElementById('expRow');
  if(d.expires_human){document.getElementById('exp').textContent=d.expires_human;
    expRow.classList.remove('hide')}
  else{expRow.classList.add('hide')}

  const ql=document.getElementById('quotaLabel'), q=document.getElementById('quota'),
        bar=document.getElementById('bar'), note=document.getElementById('quotaNote');
  if(d.unlimited){
    ql.textContent='Тариф';
    q.textContent='Безлимит';
    const pct=d.daily_cap?Math.min(100,Math.round(d.spent_today/d.daily_cap*100)):0;
    bar.style.width=pct+'%';
    note.textContent='Сегодня использовано '+d.spent_today_human+
      ' из '+d.daily_cap_human+' (справедливое использование, обновляется каждые сутки).';
  }else{
    ql.textContent='Остаток токенов';
    q.textContent=d.tokens_left_human;
    const pct=d.tokens_limit?Math.round(d.tokens_left/d.tokens_limit*100):0;
    bar.style.width=pct+'%';
    note.textContent='Использовано '+d.tokens_used_human+' из '+d.tokens_limit_human+'.';
  }
  document.getElementById('snippet').textContent=
    'base_url: '+GW+'\\napi_key:  '+tok+'\\n\\n'+
    '# пример (curl)\\n'+
    'curl '+GW+'/chat/completions \\\\\\n'+
    '  -H "Authorization: Bearer '+tok+'" \\\\\\n'+
    '  -H "Content-Type: application/json" \\\\\\n'+
    '  -d \\'{"model":"claude-sonnet-5","messages":[{"role":"user","content":"привет"}]}\\'';
}
const saved=localStorage.getItem('wave_token');
if(saved){document.getElementById('tok').value=saved;load()}
</script>
</div></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "WAVE-Dashboard"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path in {"/", "/index.html"}:
            bot_line = (f' <a href="{BOT_LINK}">Открыть бот</a>' if BOT_LINK else "")
            page = (PAGE.replace("__SHOP__", SHOP_NAME)
                        .replace("__SUPPORT__", SUPPORT)
                        .replace("__GW__", PUBLIC_GW)
                        .replace("__PREFIX__", KEY_PREFIX)
                        .replace("__BOTLINK__", bot_line))
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path == "/api/status":
            auth = self.headers.get("Authorization", "")
            token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            st = _store.status(token) if token else None
            if not st:
                self._send(404, b'{"error":"not_found"}', "application/json")
                return
            now = int(time.time())
            st["expired"] = bool(st.get("expires_at") and now >= int(st["expires_at"]))
            if st.get("expires_at"):
                st["expires_human"] = human_left(int(st["expires_at"]) - now)
            if st.get("unlimited"):
                st["daily_cap_human"] = human_tokens(st.get("daily_cap", 0))
                st["spent_today_human"] = human_tokens(st.get("spent_today", 0))
            else:
                st["tokens_left_human"] = human_tokens(st.get("tokens_left", 0))
                st["tokens_used_human"] = human_tokens(st.get("tokens_used", 0))
                st["tokens_limit_human"] = human_tokens(st.get("tokens_limit", 0))
            body = json.dumps(st, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        self._send(404, b"not found", "text/plain; charset=utf-8")


def main() -> int:
    print(f"WAVE кабинет: http://{HOST}:{PORT}")
    print(f"  шлюз для клиентов: {PUBLIC_GW}")
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлен")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

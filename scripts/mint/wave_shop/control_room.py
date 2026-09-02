"""WAVE SHOP — операторская панель (control-room). Веха M5.

Одно окно оператора: выручка, склад, заказы, выданные ключи шлюза,
подписки и состояние касс. Всё в бренде WAVE, в каноне SOCC.

ЗАКОН этой панели — она НИЧЕГО НЕ ДВИГАЕТ. Только читает локальные JSON
(data/*). Ни одной записи, ни одного списания, ни одного обращения к
Telegram или к провайдеру. Это сухая смотровая площадка: сломать ей ничего
нельзя, потому что писать она не умеет.

Доступ. Панель показывает выручку и заказы — её нельзя оставлять открытой.
Поэтому:
  • слушает только 127.0.0.1 (WAVE_CONTROL_HOST, чтобы поменять осознанно);
  • требует секрет оператора WAVE_CONTROL_TOKEN. Если он не задан — панель
    генерирует разовый и печатает в консоль: без секрета не стартует «нагишом».
Секрет уходит на сервер единственным заголовком Authorization и нигде не
логируется; в браузере лежит только в localStorage.

Токены клиентов маскируются до последних 6 символов — панель показывает
состояние доступа, а не сами ключи (канон изоляции: хвосты не пересекаются).

Запуск:  WAVE_CONTROL_TOKEN=секрет python3 control_room.py
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_settings                    # noqa: E402
from gateway.quota import QuotaStore                 # noqa: E402
from payments.providers import build_providers       # noqa: E402
from store import Store                              # noqa: E402

HOST = os.environ.get("WAVE_CONTROL_HOST", "127.0.0.1")
PORT = int(os.environ.get("WAVE_CONTROL_PORT", "8792"))


def human_rub(n: int) -> str:
    n = int(n or 0)
    s = f"{n:,}".replace(",", " ")
    return f"{s} ₽"


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
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} дн {h} ч"
    if h:
        return f"{h} ч {m} мин"
    return f"{m} мин"


def human_ago(seconds: int) -> str:
    """Сколько прошло. В отличие от human_left, 0 и меньше — «только что»."""
    seconds = int(seconds)
    if seconds < 60:
        return "только что"
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} дн назад"
    if h:
        return f"{h} ч назад"
    return f"{m} мин назад"


def _tail(token: str) -> str:
    token = str(token or "")
    return "…" + token[-6:] if len(token) > 6 else token


PAGE = """<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__SHOP__ — Control Room</title>
<style>
  :root{
    --bg:#0b0f14; --panel:#121821; --line:#1f2937; --ink:#e6edf3;
    --dim:#8b9aab; --acc:#4ade80; --warn:#fbbf24; --bad:#f87171;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    padding:24px 16px}
  .wrap{max-width:1200px;margin:0 auto}
  h1{font-size:18px;letter-spacing:.12em;text-transform:uppercase;margin:0 0 4px}
  .sub{color:var(--dim);font-size:12px;margin-bottom:20px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;margin-bottom:20px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
  .card h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);
    margin:0 0 12px;border-bottom:1px solid var(--line);padding-bottom:8px}
  .big{font-size:26px;font-weight:700;letter-spacing:-.01em;margin:4px 0 0}
  .row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--line)}
  .row:last-child{border-bottom:0}
  .k{color:var(--dim);font-size:12px}
  .v{font-weight:600;font-size:13px}
  .badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;
    letter-spacing:.06em;text-transform:uppercase;font-weight:700}
  .ok{background:rgba(74,222,128,.14);color:var(--acc)}
  .warn{background:rgba(251,191,36,.14);color:var(--warn)}
  .bad{background:rgba(248,113,113,.14);color:var(--bad)}
  table{width:100%;border-collapse:collapse;font-size:12px}
  th{text-align:left;color:var(--dim);font-weight:600;letter-spacing:.05em;
    text-transform:uppercase;padding:8px 10px;border-bottom:2px solid var(--line)}
  td{padding:8px 10px;border-bottom:1px solid var(--line)}
  tr:last-child td{border-bottom:0}
  .mono{font-family:inherit;color:var(--acc)}
  input{width:100%;padding:11px 12px;background:#0b0f14;border:1px solid var(--line);
    border-radius:7px;color:var(--ink);font:inherit;outline:none;margin-bottom:10px}
  input:focus{border-color:var(--acc)}
  button{width:100%;padding:11px;background:var(--acc);border:0;border-radius:7px;
    color:#06210f;font:inherit;font-weight:700;cursor:pointer;letter-spacing:.05em}
  button:hover{filter:brightness(1.08)}
  .hide{display:none}
  .err{color:var(--bad);font-size:12px;margin-top:8px}
</style></head><body><div class="wrap">

  <h1>__SHOP__ — Control Room</h1>
  <div class="sub">Операторская панель · только чтение</div>

  <div class="card" id="auth">
    <h2>Доступ</h2>
    <input id="tok" type="password" placeholder="WAVE_CONTROL_TOKEN" autocomplete="off">
    <button onclick="load()">Войти</button>
    <div class="err hide" id="err"></div>
  </div>

  <div id="panel" class="hide"></div>

<script>
function esc(s){return String(s||'').replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}
function logout(){localStorage.removeItem('wave_control');location.reload()}
async function load(){
  const tok=(document.getElementById('tok').value||'').trim();
  const err=document.getElementById('err');
  if(!tok){err.textContent='Введите токен.';err.classList.remove('hide');return}
  try{
    const r=await fetch('/api/stats',{headers:{'Authorization':'Bearer '+tok}});
    if(!r.ok){err.textContent='Токен неверный.';err.classList.remove('hide');return}
    const d=await r.json();
    localStorage.setItem('wave_control',tok);
    render(d);
  }catch(e){err.textContent='Сервис недоступен.';err.classList.remove('hide')}
}
function render(d){
  document.getElementById('auth').classList.add('hide');
  const p=document.getElementById('panel');
  p.classList.remove('hide');

  const kassa=d.kassa.map(k=>
    `<div class="row"><span class="k">${esc(k.name)}</span>`+
    `<span class="v"><span class="badge ${k.on?'ok':'bad'}">${k.on?'вкл':'выкл'}</span></span></div>`
  ).join('');

  const stock=d.stock.map(s=>
    `<div class="row"><span class="k">${esc(s.title)}</span>`+
    `<span class="v">${s.kind==='key'
      ? (s.count>0?s.count+' шт':'<span class="badge bad">пусто</span>')
      : '<span class="badge ok">∞</span>'}</span></div>`
  ).join('') || '<div class="k">нет товаров</div>';

  const orders=d.orders.map(o=>
    `<tr><td class="mono">${esc(o.id)}</td><td>${esc(o.product)}</td>`+
    `<td>${esc(o.provider)}</td><td>${o.amount} ₽</td>`+
    `<td><span class="badge ${o.badge}">${esc(o.status)}</span></td>`+
    `<td>${esc(o.when)}</td></tr>`
  ).join('') || '<tr><td colspan="6" class="k">заказов ещё нет</td></tr>';

  const keys=d.keys.map(k=>
    `<tr><td class="mono">${esc(k.tail)}</td><td>${esc(k.title)}</td>`+
    `<td>${esc(k.quota)}</td><td>${esc(k.left)}</td>`+
    `<td><span class="badge ${k.badge}">${esc(k.state)}</span></td></tr>`
  ).join('') || '<tr><td colspan="5" class="k">ключей ещё нет</td></tr>';

  const subs=d.subs.map(s=>
    `<tr><td>${esc(s.product)}</td><td>${s.amount} ₽</td>`+
    `<td><span class="badge ${s.renew?'ok':'warn'}">${s.renew?'авто':'ручное'}</span></td>`+
    `<td><span class="badge ${s.badge}">${esc(s.until)}</span></td></tr>`
  ).join('') || '<tr><td colspan="4" class="k">подписок ещё нет</td></tr>';

  p.innerHTML=
    '<div class="grid">'+
      '<div class="card"><h2>Выручка</h2>'+
        '<div class="k">всего продаж</div><div class="big">'+d.revenue.rub+'</div>'+
        '<div class="row" style="margin-top:10px"><span class="k">заказов оплачено</span>'+
        '<span class="v">'+d.revenue.orders+'</span></div>'+
        '<div class="row"><span class="k">рефералам начислено</span>'+
        '<span class="v">'+d.revenue.ref+'</span></div></div>'+
      '<div class="card"><h2>Кассы</h2>'+kassa+'</div>'+
      '<div class="card"><h2>Склад</h2>'+stock+'</div>'+
      '<div class="card"><h2>Клиенты</h2>'+
        '<div class="k">выдано ключей</div><div class="big">'+d.summary.keys+'</div>'+
        '<div class="row" style="margin-top:10px"><span class="k">активных ключей</span>'+
        '<span class="v">'+d.summary.keys_active+'</span></div>'+
        '<div class="row"><span class="k">подписок с автопродлением</span>'+
        '<span class="v">'+d.summary.subs_auto+'</span></div></div>'+
    '</div>'+
    '<div class="card"><h2>Заказы</h2><table><tr><th>ID</th><th>товар</th>'+
      '<th>касса</th><th>сумма</th><th>статус</th><th>когда</th></tr>'+orders+'</table></div>'+
    '<div class="card" style="margin-top:14px"><h2>Ключи шлюза</h2><table>'+
      '<tr><th>ключ</th><th>тариф</th><th>квота</th><th>остаток</th><th>состояние</th></tr>'+
      keys+'</table></div>'+
    '<div class="card" style="margin-top:14px"><h2>Подписки</h2><table>'+
      '<tr><th>товар</th><th>сумма</th><th>продление</th><th>оплачено до</th></tr>'+
      subs+'</table></div>'+
    '<div style="margin-top:16px"><button onclick="logout()" '+
      'style="background:#1f2937;color:var(--ink);max-width:200px">Выйти</button></div>';
}
const saved=localStorage.getItem('wave_control');
if(saved){document.getElementById('tok').value=saved;load()}
</script>
</div></body></html>"""


_STATUS_BADGE = {
    "delivered": "ok", "paid": "ok",
    "pending": "warn", "failed": "bad", "rejected": "bad",
}


def collect_stats(store: Store, quota: QuotaStore, settings) -> dict:
    """Собрать операторский срез из локальных JSON. Только чтение."""
    now = int(time.time())
    rev = store.revenue_total()

    # Рефералам начислено — из балансов пользователей (сумма ref_balance).
    ref_total = 0
    try:
        for u in store.all_users():
            ref_total += int(u.get("ref_balance", 0))
    except AttributeError:
        ref_total = 0

    # Кассы: какие провайдеры реально сконфигурированы. build_providers
    # возвращает ключи вида stars / yookassa_sbp / yookassa / crypto / manual —
    # схлопываем варианты ЮKassa в одну строку по префиксу.
    active = build_providers(settings)
    has = {
        "Telegram Stars": "stars" in active,
        "ЮKassa (карты/СБП)": any(k.startswith("yookassa") for k in active),
        "Крипта (USDT)": "crypto" in active,
        "Ручная оплата": "manual" in active,
    }
    kassa = [{"name": label, "on": on} for label, on in has.items()]

    # Склад: по каталогу, ключевые товары показывают остаток.
    stock = []
    for prod in store.catalog():
        kind = prod.get("kind", "key")
        stock.append({
            "title": prod.get("title", prod.get("id", "?")),
            "kind": kind,
            "count": store.stock_count(prod["id"]) if kind == "key" else 0,
        })

    # Заказы: последние 40, свежие сверху.
    orders_raw = sorted(store.all_orders(),
                        key=lambda o: int(o.get("created_at", 0)), reverse=True)
    orders = []
    for o in orders_raw[:40]:
        st = o.get("status", "pending")
        orders.append({
            "id": _tail(o.get("order_id", "")),
            "product": o.get("product_id", ""),
            "provider": o.get("provider", ""),
            "amount": int(o.get("amount_rub", 0)),
            "status": st,
            "badge": _STATUS_BADGE.get(st, "warn"),
            "when": human_ago(now - int(o.get("created_at", now))),
        })

    # Ключи шлюза: маскируем токен до хвоста, состояние из status().
    keys = []
    active_keys = 0
    for rec in quota.all_keys():
        token = rec.get("token", "")
        st = quota.status(token, now) or {}
        expired = bool(st.get("expires_at") and now >= int(st["expires_at"]))
        enabled = st.get("enabled", True)
        alive = enabled and not expired
        active_keys += 1 if alive else 0
        if st.get("unlimited"):
            quota_h, left_h = "безлимит", human_tokens(st.get("daily_cap", 0)) + "/сут"
        else:
            quota_h = human_tokens(st.get("tokens_limit", 0))
            left_h = human_tokens(st.get("tokens_left", 0))
        state = "активен" if alive else ("истёк" if expired else "выключен")
        keys.append({
            "tail": _tail(token),
            "title": st.get("title", rec.get("plan_id", "")),
            "quota": quota_h,
            "left": left_h,
            "state": state,
            "badge": "ok" if alive else "bad",
        })

    # Подписки: срок и режим продления.
    subs = []
    subs_auto = 0
    for s in store.all_subscriptions():
        paid_until = int(s.get("paid_until", 0))
        renew = bool(s.get("autorenew"))
        subs_auto += 1 if renew else 0
        overdue = paid_until and now >= paid_until
        subs.append({
            "product": s.get("product_id", ""),
            "amount": int(s.get("amount_rub", 0)),
            "renew": renew,
            "until": ("просрочена" if overdue else human_left(paid_until - now))
                     if paid_until else "—",
            "badge": "bad" if overdue else "ok",
        })

    return {
        "revenue": {"rub": human_rub(rev["rub_total"]), "orders": rev["orders"],
                    "ref": human_rub(ref_total)},
        "kassa": kassa,
        "stock": stock,
        "orders": orders,
        "keys": keys,
        "subs": subs,
        "summary": {"keys": len(keys), "keys_active": active_keys,
                    "subs_auto": subs_auto},
    }


def make_handler(store: Store, quota: QuotaStore, settings, control_token: str):
    """Собрать Handler с привязкой к хранилищам и секрету оператора."""

    def _authed(headers) -> bool:
        auth = headers.get("Authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        # Сравнение постоянного времени — секрет не подбирается по таймингу.
        return bool(token) and secrets.compare_digest(token, control_token)

    class Handler(BaseHTTPRequestHandler):
        server_version = "WAVE-ControlRoom"
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
                page = PAGE.replace("__SHOP__", settings.shop_name)
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
                return

            if path == "/api/stats":
                if not _authed(self.headers):
                    self._send(401, b'{"error":"unauthorized"}',
                               "application/json; charset=utf-8")
                    return
                data = collect_stats(store, quota, settings)
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
                return

            self._send(404, b"not found", "text/plain; charset=utf-8")

    return Handler


def main() -> int:
    settings = load_settings()
    store = Store(settings.data_dir)
    quota = QuotaStore(settings.data_dir)

    token = os.environ.get("WAVE_CONTROL_TOKEN", "").strip()
    generated = False
    if not token:
        # Панель НИКОГДА не стартует без секрета. Нет заданного — генерим разовый
        # и печатаем его: открытый доступ к выручке недопустим даже на localhost.
        token = "ctl-" + secrets.token_urlsafe(18)
        generated = True

    handler = make_handler(store, quota, settings, token)
    print(f"WAVE Control Room: http://{HOST}:{PORT}")
    print(f"  магазин: {settings.shop_name}   данные: {settings.data_dir}")
    if generated:
        print("\n  ⚠️  WAVE_CONTROL_TOKEN не задан — сгенерирован разовый:")
        print(f"      {token}")
        print("  Задайте свой в .env, чтобы токен не менялся при каждом запуске.\n")
    else:
        print("  доступ: по WAVE_CONTROL_TOKEN из окружения")

    srv = ThreadingHTTPServer((HOST, PORT), handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлен")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

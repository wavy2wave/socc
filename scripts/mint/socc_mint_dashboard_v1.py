#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT dashboard V1 — глаза органа (зеркало scripts/anna_dashboard_v1.py).

Показывает: проверенные ₽ по вселенным · ROI · РАНЖИРОВАНИЕ вселенных (соревнование, MINT §5) ·
заявленные-но-не-проверенные claim · статус красных линий (WARDEN) · честный вердикт ledger.
Каждое число ведёт к событию (закон: нет числа без события) — внизу список проверенных транзакций.

Foreground HTTP (без демона, Ctrl-C стоп). Порт: env MINT_DASH_PORT (умолч. 8792).
Источник: канонический revenue_ledger.jsonl; для просмотра песочницы — MINT_LEDGER_PATH=/tmp/mint_dry_ledger.jsonl
"""
import os
import sys
import json
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import socc_revenue_ledger_v1 as ledger  # noqa: E402
import socc_mint_catalog_v1 as catalog    # noqa: E402

PORT = int(os.environ.get("MINT_DASH_PORT", "8792"))

RED_LINES = [
    ("RL1", "нет денежных мулов/дропов (ст. 174/187 УК)"),
    ("RL2", "нет перепродажи доступа в обход ToS"),
    ("RL3", "нет фейковых личностей живых людей"),
    ("RL4", "серое ≤ легальное (без обмана покупателя)"),
    ("MN2", "транзакция на легальную сущность создателя"),
]


def gather_state():
    rows = ledger._read()
    verified = [r for r in rows if r.get("stage") == "verified" and r.get("verified")]
    pending = [r for r in rows if r.get("stage") == "claim"
               and r.get("connection_id") not in {v["connection_id"] for v in verified}]
    return {
        "ledger_path": str(ledger.LEDGER),
        "verdict": ledger.verdict(),
        "ranking": ledger.ranking(),
        "summary": ledger.summary_by_venture(),
        "verified_tx": verified[-50:],
        "pending_claims": pending[-50:],
        "red_lines": RED_LINES,
        "catalog": catalog.summary(),
    }


def render_html(s):
    v = s["verdict"]
    badge = "#1a7f37" if v["status"] == "PASS" else "#cf222e"
    rank_rows = "".join(
        f"<tr><td>{i+1}</td><td><b>{b['venture']}</b></td><td>{b['verified_tx']}</td>"
        f"<td class=g>{b['verified_profit']:.0f} ₽</td><td>{b['claimed_profit']:.0f} ₽</td>"
        f"<td>{b['cost']:.0f} ₽</td><td>{'—' if b['roi'] is None else format(b['roi'],'.3f')}</td></tr>"
        for i, b in enumerate(s["ranking"]))
    tx_rows = "".join(
        f"<tr><td>{r['venture']}</td><td class=mono>{r['connection_id']}</td><td>{r.get('item','')}</td>"
        f"<td class=g>{float(r.get('profit_net') or 0):.0f} ₽</td>"
        f"<td>{float(r.get('verify_amount') or 0):.0f} ₽</td><td>{r.get('verify_source','')}</td></tr>"
        for r in reversed(s["verified_tx"])) or "<tr><td colspan=6 class=dim>пока нет проверенных транзакций</td></tr>"
    pend_rows = "".join(
        f"<tr><td>{r['venture']}</td><td class=mono>{r['connection_id']}</td><td>{r.get('item','')}</td>"
        f"<td>{float(r.get('profit_net') or 0):.0f} ₽</td></tr>"
        for r in reversed(s["pending_claims"])) or "<tr><td colspan=4 class=dim>нет заявок в ожидании</td></tr>"
    rl_rows = "".join(f"<li><b>{c}</b> — {t} <span class=g>✓ enforced</span></li>" for c, t in s["red_lines"])

    cat = s.get("catalog", {})
    st = cat.get("stats", {})
    if cat.get("status") == "loaded":
        cat_bv = "".join(
            f"<tr><td><b>{vn}</b></td><td>{n} связок</td></tr>"
            for vn, n in sorted(cat.get("by_venture", {}).items(), key=lambda kv: kv[1], reverse=True)
        ) or "<tr><td colspan=2 class=dim>—</td></tr>"
        cat_rej = "".join(
            f"<li><b>{k}</b> — {n} отрезано</li>"
            for k, n in sorted(cat.get("rejected_by_red_line", {}).items(), key=lambda kv: kv[1], reverse=True)
        ) or "<li class=dim>чисто</li>"
        cat_card = f"""<div class=card>
  <h3>🎯 Боезапас: каталог вычищенных связок</h3>
  <div class=dim style=text-align:left>законных и достижимых: <b class=g>{st.get('legit','—')}</b> ·
    отбраковано аудитором: <b>{st.get('rejected','—')}</b> · сфер: {st.get('spheres','—')} ·
    «огонь первым»: {cat.get('fire_first_count','—')}</div>
  <table style=margin-top:10px><tr><th>вселенная</th><th>связок в боезапасе</th></tr>{cat_bv}</table>
  <div style=margin-top:8px><b>🚓 Само-полицейский лог</b> — что орган сам отрезал по красным линиям:</div>
  <ul>{cat_rej}</ul>
  <div class=dim style=text-align:left>доктрина: {cat.get('doctrine_note') or '—'}</div>
</div>"""
    else:
        cat_card = """<div class=card>
  <h3>🎯 Боезапас: каталог связок</h3>
  <div class=dim style=text-align:left>каталог ещё не загружен — после воркфлоу
    <span class=mono>mint-connection-catalog</span> результат ляжет в
    <span class=mono>MEMORY_WAVE/reports/mint/connection_catalog_v1.json</span></div>
</div>"""

    total = v.get("verified_profit_total", 0)
    return f"""<!doctype html><html lang=ru><head><meta charset=utf-8>
<title>MINT — финансовый орган</title><meta http-equiv=refresh content=15>
<style>
 body{{background:#0d1117;color:#e6edf3;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:24px}}
 h1{{font-size:20px;margin:0 0 4px}} .sub{{color:#8b949e;margin-bottom:18px}}
 .badge{{background:{badge};color:#fff;padding:3px 10px;border-radius:12px;font-weight:600;font-size:12px}}
 .big{{font-size:34px;font-weight:700;color:#3fb950}} table{{border-collapse:collapse;width:100%;margin:8px 0 22px}}
 th,td{{text-align:left;padding:7px 10px;border-bottom:1px solid #21262d}} th{{color:#8b949e;font-weight:600;font-size:12px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:16px 18px;margin-bottom:18px}}
 .g{{color:#3fb950}} .dim{{color:#8b949e;text-align:center}} .mono{{font-family:ui-monospace,monospace;font-size:12px;color:#8b949e}}
 ul{{margin:6px 0;padding-left:18px}} li{{margin:3px 0}}
</style></head><body>
<h1>🏦 MINT — финансовый орган SOCC <span class=badge>ledger {v['status']}</span></h1>
<div class=sub>чеканка доказанных транзакций · кровь: <span class=mono>{s['ledger_path']}</span></div>

<div class=card>
  <div>Проверенный доход (всего)</div>
  <div class=big>{total:.0f} ₽</div>
  <div class=dim style=text-align:left>verified ⟺ деньги прочитаны из реального источника. Нарушений честности: {len(v['verified_violations'])}</div>
</div>

<div class=card>
  <h3>🏆 Соревнование вселенных (ранг по ROI)</h3>
  <table><tr><th>#</th><th>вселенная</th><th>verified tx</th><th>проверено ₽</th><th>заявлено ₽</th><th>стоимость</th><th>ROI</th></tr>
  {rank_rows or '<tr><td colspan=7 class=dim>нет вселенных</td></tr>'}</table>
</div>

<div class=card>
  <h3>✅ Проверенные транзакции (каждая ведёт к событию)</h3>
  <table><tr><th>вселенная</th><th>connection_id</th><th>товар/услуга</th><th>нетто</th><th>поступило</th><th>источник</th></tr>
  {tx_rows}</table>
</div>

<div class=card>
  <h3>⏳ Заявки в ожидании поступления (claim, ещё НЕ доход)</h3>
  <table><tr><th>вселенная</th><th>connection_id</th><th>товар/услуга</th><th>нетто (ожид.)</th></tr>
  {pend_rows}</table>
</div>

{cat_card}

<div class=card>
  <h3>🛡 Красные линии WARDEN (иммунитет органа)</h3>
  <ul>{rl_rows}</ul>
</div>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

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
    if "--once" in sys.argv:  # для smoke-теста: один рендер в stdout, без сервера
        print(json.dumps(gather_state(), ensure_ascii=False, indent=2))
        sys.exit(0)
    print(f"MINT dashboard → http://127.0.0.1:{PORT}  (Ctrl-C стоп) · ledger: {ledger.LEDGER}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

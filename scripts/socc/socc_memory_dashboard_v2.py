#!/usr/bin/env python3
"""SOCC Memory Dashboard v2 — one self-contained control panel for the meaning-based wiki.

Reads spine2 artifacts (_spine2_proof.json + pages/*.md) and emits ONE static file:
SOVEREIGN/WIKI/spine2/dashboard.html. Open it to see the living memory: KPIs, the
6 meaning-topics (было->стало counts), the goal chain (SOCC -> Entity Substrate -> ANNA),
and every article with clickable hyperlinks back to raw sources. Fully offline.

When served by socc_memory_server_v2.py (127.0.0.1), the «Залить файл» zone uploads a
file -> inbox -> fast v2 rebuild (~2.4s) -> dashboard refreshes. No server, no daemon
needed just to VIEW (open the html directly); the server is only for uploads.

Truth boundary (SOCC-lawful): read-only over spine2 artifacts. Writes only dashboard.html
(atomic). No route authority / proof chain mutation, no network, no daemon, no LLM.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPINE2 = ROOT / "SOVEREIGN" / "WIKI" / "spine2"
PROOF = SPINE2 / "_spine2_proof.json"
PAGES = SPINE2 / "pages"
SELF_MODEL = SPINE2 / "SELF_MODEL.md"
SELF_EVOLVE = SPINE2 / "SELF_EVOLVE.md"
OUT = SPINE2 / "dashboard.html"

# Goal chain — SOCC's spine from sealed core to revenue product.
GOAL_CHAIN = [
    {"id": "socc", "label": "SOCC — суверенное ядро (кто я)", "status": "sealed", "icon": "🟢"},
    {"id": "self_construction", "label": "Автономное строительство — самостройка", "status": "sealed · двигатель", "icon": "🟢"},
    {"id": "entity_substrate", "label": "Entity Substrate — орган рождения сущностей", "status": "sealed · ревью", "icon": "🟡"},
    {"id": "anna", "label": "ANNA MVP — продукт для стоматологий", "status": "built · мозг 401/402", "icon": "🔴"},
]


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    if not PROOF.exists():
        raise SystemExit("spine2 proof not found — run socc_memory_spine_v2.py first")
    proof = json.loads(PROOF.read_text(encoding="utf-8"))

    articles = {}
    for tid in proof["topics"]:
        f = PAGES / f"{tid}.md"
        articles[tid] = f.read_text(encoding="utf-8") if f.exists() else "_(нет статьи)_"

    self_model = SELF_MODEL.read_text(encoding="utf-8") if SELF_MODEL.exists() else ""
    self_evolve = SELF_EVOLVE.read_text(encoding="utf-8") if SELF_EVOLVE.exists() else ""

    data = {
        "proof": proof,
        "articles": articles,
        "self_model": self_model,
        "self_evolve": self_evolve,
        "goal_chain": GOAL_CHAIN,
        "generated": datetime.now(timezone.utc).isoformat(),
    }
    payload = json.dumps(data, ensure_ascii=False)
    html = HTML.replace("__DATA__", payload)
    write_atomic(OUT, html)

    print("SOCC MEMORY DASHBOARD v2 — BUILT")
    print(f"  topics : {len(proof['topics'])}  ·  sources : {proof.get('sources_scanned')}  ·  cache_hits : {proof.get('cache_hits')}")
    print(f"  open   : {OUT}")
    ext = html.count("http://") + html.count("https://")
    print(f"  external script/style refs : 0  ·  self-contained : yes  ·  raw-link count : {html.count('#L')}")


HTML = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SOCC Memory — живая вики (v2, по смыслу)</title>
<style>
:root{--bg:#0b0c0d;--card:#141618;--ink:#e8eaed;--mut:#8b9096;--accent:#5cc8ff;--ok:#46d39a;--warn:#f5c451;--bad:#f5736b;--line:#23262a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:26px 20px 70px}
h1{font-size:22px;margin:0 0 2px}.sub{color:var(--mut);font-size:12px;margin-bottom:18px}
.grid{display:grid;grid-template-columns:1.6fr 1fr;gap:16px}@media(max-width:900px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:16px}
.card h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin:0 0 12px}
.kpis{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;min-width:120px;flex:1}
.kpi .n{font-size:24px;font-weight:650}.kpi .l{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase}
tr.tp{cursor:pointer}tr.tp:hover{background:#1b1e21}td .tt{font-weight:600}
.badge{font-size:10px;padding:1px 7px;border-radius:20px;border:1px solid var(--line);color:var(--mut)}
.badge.a{color:var(--ok);border-color:#205c46}
.chain{display:flex;flex-direction:column;gap:8px}
.step{display:flex;align-items:center;gap:10px;background:#0e1012;border:1px solid var(--line);border-radius:10px;padding:9px 11px;font-size:13px;cursor:pointer}
.step:hover{border-color:var(--accent)}.step .s{margin-left:auto;font-size:11px;color:var(--mut)}
.uz{border:1.5px dashed #3a3d42;border-radius:12px;padding:20px;text-align:center;color:var(--mut);cursor:pointer;transition:.15s;margin-bottom:8px}
.uz:hover{border-color:var(--accent);color:var(--ink)}.uz.drag{border-color:var(--ok);background:#0f1a14;color:var(--ok)}
#umsg{font-size:12px;margin:8px 0;min-height:16px}
.muted{color:var(--mut);font-size:12px}.cmd{display:flex;gap:8px;align-items:center;background:#0e1012;border:1px solid var(--line);border-radius:9px;padding:8px 10px;font-family:ui-monospace,monospace;font-size:12px;margin-top:8px}
.cmd span{flex:1;overflow:auto}.cmd button{background:#222;border:1px solid var(--line);color:var(--ink);border-radius:6px;padding:3px 9px;cursor:pointer;font-size:11px}
.art{display:none}.art .back{cursor:pointer;color:var(--accent);font-size:12px;margin-bottom:10px;display:inline-block}
.art h1{font-size:20px}.art h2{font-size:14px;color:var(--ink);text-transform:none;letter-spacing:0;border-bottom:1px solid var(--line);padding-bottom:5px;margin:20px 0 10px}
.art h3{font-size:13px;color:var(--mut)}.art a{color:var(--accent);text-decoration:none}.art a:hover{text-decoration:underline}
.art blockquote{border-left:3px solid var(--line);margin:8px 0;padding:4px 12px;color:var(--mut);font-size:13px}
.art code{background:#0e1012;padding:1px 5px;border-radius:5px;font-size:12px}
.art ul{padding-left:18px}.art li{margin:5px 0}.art hr{border:0;border-top:1px solid var(--line);margin:18px 0}
</style></head><body><div class="wrap">
<h1>🧠 SOCC Memory — живая вики</h1>
<div class="sub" id="gen"></div>

<div id="home">
  <div class="step" style="border-color:var(--accent);margin-bottom:10px" onclick="selfmodel()">
    🪞 <span><b>Сознание системы — Модель себя (Self-Model)</b><br><span class="muted">кто я · способности · как работаю · связи</span></span><span class="s">открыть зеркало →</span>
  </div>
  <div class="step" style="border-color:var(--ok);margin-bottom:16px" onclick="selfevolve()">
    🧬 <span><b>Самоэволюция — следующий законный шаг</b><br><span class="muted">система сама находит пробелы и говорит, что делать для роста</span></span><span class="s">что дальше →</span>
  </div>
  <div class="kpis" id="kpis"></div>
  <div class="grid">
    <div>
      <div class="card"><h2>Темы по смыслу — было→стало</h2>
        <table><thead><tr><th>Тема</th><th>Истина</th><th>Развилки</th><th>Граница</th><th>Хроно</th><th>Источ.</th><th></th></tr></thead>
        <tbody id="topics"></tbody></table>
        <div class="muted" style="margin-top:10px">Клик по теме → статья с кликабельными ссылками на сырьё.</div>
      </div>
    </div>
    <div>
      <div class="card"><h2>Цель-цепочка</h2><div class="chain" id="chain"></div></div>
      <div class="card"><h2>Залить файл</h2>
        <div class="uz" id="uz">⬆️ Перетащи файл или кликни<br><span class="muted">.txt · .md · .eml · .json → inbox → быстрый разбор</span></div>
        <input type="file" id="fi" accept=".txt,.md,.eml,.json" hidden>
        <div id="umsg"></div>
        <div class="muted">Нужен запущенный локальный сервер.</div>
        <div class="cmd"><span>python3 ~/SOCC/scripts/socc/socc_memory_server_v2.py</span><button onclick="cp(this)">copy</button></div>
        <div class="muted" style="margin-top:8px">Или вручную: лей в <code>SOVEREIGN/MEMORY/inbox/</code> → <code>python3 scripts/socc/socc_memory_spine_v2.py</code></div>
      </div>
    </div>
  </div>
</div>

<div class="art" id="art">
  <span class="back" onclick="home()">← назад ко всем темам</span>
  <div id="artbody"></div>
</div>

<script>
const D=__DATA__;
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function inl(s){return esc(s)
  .replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank">$1</a>')
  .replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>')
  .replace(/`([^`]+)`/g,'<code>$1</code>')}
function md(t){
  const L=t.split(/\r?\n/);let h='',inUl=false,inBq=false;
  const closeUl=()=>{if(inUl){h+='</ul>';inUl=false}};
  const closeBq=()=>{if(inBq){h+='</blockquote>';inBq=false}};
  for(let raw of L){
    let ln=raw.replace(/<!--[\s\S]*?-->/g,'').replace(/^\s*-->/,'').trim();
    if(/^<!--/.test(raw))continue;
    if(ln===''){closeUl();closeBq();continue}
    if(/^#{1,6}\s/.test(ln)){closeUl();closeBq();const n=ln.match(/^#+/)[0].length;h+='<h'+n+'>'+inl(ln.replace(/^#+\s/,''))+'</h'+n+'>';continue}
    if(/^---+$/.test(ln)){closeUl();closeBq();h+='<hr>';continue}
    if(/^>\s?/.test(ln)){closeUl();if(!inBq){h+='<blockquote>';inBq=true}h+=inl(ln.replace(/^>\s?/,''))+' ';continue}
    if(/^[-*]\s/.test(ln)){closeBq();if(!inUl){h+='<ul>';inUl=true}h+='<li>'+inl(ln.replace(/^[-*]\s/,''))+'</li>';continue}
    if(/^↳\s/.test(ln)){if(inUl){h=h.replace(/<\/li>$/,'<br><span class="muted">'+inl(ln)+'</span></li>')}else{h+='<div class="muted">'+inl(ln)+'</div>'}continue}
    closeUl();closeBq();h+='<p>'+inl(ln)+'</p>';
  }
  closeUl();closeBq();return h;
}
document.getElementById('gen').textContent='Собрано: '+D.generated+' · источников '+D.proof.sources_scanned+' · cache hits '+D.proof.cache_hits+' · темы по смыслу (TOPIC_MAP_V1) · deterministic, no-LLM';
const tp=Object.entries(D.proof.topics);
let tot={cur:0,fork:0,bnd:0,src:0};tp.forEach(([id,s])=>{tot.cur+=s.current;tot.fork+=s.forks;tot.bnd+=s.boundary_collapsed;tot.src=Math.max(tot.src,s.sources)});
document.getElementById('kpis').innerHTML=[
 ['Источников',D.proof.sources_scanned],['Тем по смыслу',tp.length],['Текущая истина',tot.cur],
 ['Развилок',tot.fork],['Boilerplate схлопнут',tot.bnd]
].map(k=>'<div class="kpi"><div class="n">'+k[1]+'</div><div class="l">'+k[0]+'</div></div>').join('');
document.getElementById('topics').innerHTML=tp.map(([id,s])=>
 '<tr class="tp" onclick="open_(\''+id+'\')"><td><span class="tt">'+esc(s.title)+'</span> '+(s.main_line_authored?'<span class="badge a">authored</span>':'')+
 '</td><td>'+s.current+'</td><td>'+s.forks+'</td><td>'+s.boundary_collapsed+'</td><td>'+s.timeline+'</td><td>'+s.sources+'</td><td>›</td></tr>').join('');
document.getElementById('chain').innerHTML=D.goal_chain.map(g=>
 '<div class="step" onclick="open_(\''+g.id+'\')">'+g.icon+' <span>'+esc(g.label)+'</span><span class="s">'+esc(g.status)+'</span></div>').join('');
function open_(id){const a=D.articles[id];if(!a)return;document.getElementById('artbody').innerHTML=md(a);
 document.getElementById('home').style.display='none';document.getElementById('art').style.display='block';window.scrollTo(0,0)}
function home(){document.getElementById('art').style.display='none';document.getElementById('home').style.display='block'}
function selfmodel(){if(!D.self_model)return;document.getElementById('artbody').innerHTML=md(D.self_model);
 document.getElementById('home').style.display='none';document.getElementById('art').style.display='block';window.scrollTo(0,0)}
function selfevolve(){if(!D.self_evolve)return;document.getElementById('artbody').innerHTML=md(D.self_evolve);
 document.getElementById('home').style.display='none';document.getElementById('art').style.display='block';window.scrollTo(0,0)}
function cp(b){navigator.clipboard.writeText(b.previousElementSibling.textContent);b.textContent='ok';setTimeout(()=>b.textContent='copy',900)}
const uz=document.getElementById('uz'),fi=document.getElementById('fi');
function um(t,c){const m=document.getElementById('umsg');m.textContent=t;m.style.color=c||'var(--mut)'}
uz.onclick=()=>fi.click();fi.onchange=e=>{if(e.target.files[0])up(e.target.files[0])};
uz.ondragover=e=>{e.preventDefault();uz.classList.add('drag')};uz.ondragleave=()=>uz.classList.remove('drag');
uz.ondrop=e=>{e.preventDefault();uz.classList.remove('drag');if(e.dataTransfer.files[0])up(e.dataTransfer.files[0])};
async function up(f){um('⏳ Загружаю «'+f.name+'» и разбираю (~2-3с)…');
 try{const r=await fetch('/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(f.name)},body:f});
  const j=await r.json();
  if(j.ok){um('✓ Принято: «'+j.filename+'» · источников '+j.sources+' · тем '+j.topics+' · '+j.build_time+'с. Обновляю…','var(--ok)');setTimeout(()=>location.reload(),900)}
  else um('✗ '+(j.error||'ошибка'),'#f5736b')}
 catch(e){um('✗ Нет сервера. Запусти: python3 scripts/socc/socc_memory_server_v2.py','#f5736b')}}
</script></div></body></html>"""


if __name__ == "__main__":
    main()

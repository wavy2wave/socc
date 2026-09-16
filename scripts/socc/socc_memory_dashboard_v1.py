#!/usr/bin/env python3
"""SOCC Memory Dashboard — a single self-contained control panel (no server, no daemon).

Reads the spine artifacts (proof + last ingest run + per-topic articles) and emits
ONE static file: SOVEREIGN/WIKI/spine/dashboard.html. Open it in a browser to see
the living memory: KPIs, было→стало, the goal chain (SOCC → Entity Substrate → ANNA),
the topic table, and every article (with hyperlinks back to raw sources) — fully offline.

Truth boundary (SOCC-lawful): read-only over wiki artifacts. Writes only dashboard.html.
No route authority / proof chain mutation, no network, no daemon, no LLM. Re-runnable.

Usage: python3 scripts/socc/socc_memory_dashboard_v1.py
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPINE = ROOT / "SOVEREIGN" / "WIKI" / "spine"
OUT = SPINE / "dashboard.html"

# Goal chain status — sourced from in-repo Entity Substrate canon.
GOAL_CHAIN = [
    {"name": "SOCC self-construction", "state": "sealed", "note": "автономная самостройка — первый bounded шаг запечатан"},
    {"name": "Entity Substrate", "state": "in_progress", "note": "direction BUILT_CANDIDATE + plan pending review; 10 поверхностей материализованы; execution залочен"},
    {"name": "ANNA MVP", "state": "locked", "note": "рождается только после seal Entity Substrate"},
]


def load():
    proof = json.loads((SPINE / "_spine_proof.json").read_text(encoding="utf-8")) if (SPINE / "_spine_proof.json").exists() else {}
    run_json = SPINE / "_last_ingest_run.json"
    run = json.loads(run_json.read_text(encoding="utf-8")) if run_json.exists() else {}

    topics = []
    for name, st in sorted(proof.get("topics", {}).items(), key=lambda kv: -kv[1]["current"]):
        slug = name.lower().replace(" ", "_").replace("/", "_")
        topics.append({"topic": name, "slug": slug, **st})

    articles = {}
    for p in sorted(glob.glob(str(SPINE / "pages" / "*.md"))):
        articles[Path(p).stem] = Path(p).read_text(encoding="utf-8")

    return {"generated": proof.get("built_at", ""), "sources": proof.get("sources_scanned", 0),
            "topics": topics, "run": run, "articles": articles, "goal_chain": GOAL_CHAIN}


TEMPLATE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SOCC Memory — Dashboard</title>
<style>
:root{--bg:#0b0b0c;--card:#141416;--line:#222;--ink:#e6e6e6;--mut:#9aa;--ok:#2c7;--run:#fc3;--lock:#a55;--accent:#6cf}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,Inter,system-ui,Arial}
.wrap{max-width:1180px;margin:0 auto;padding:28px 18px}
h1{font-size:20px;margin:0 0 2px}.sub{color:var(--mut);font-size:12px;margin-bottom:20px}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:18px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.kpi .n{font-size:24px;font-weight:700}.kpi .l{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.kpi.hot .n{color:var(--run)}
.grid{display:grid;grid-template-columns:1fr 360px;gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:16px}
.card h2{font-size:14px;margin:0 0 12px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:500;font-size:11px;text-transform:uppercase}
tr.t{cursor:pointer}tr.t:hover{background:#1c1d20}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid var(--line);font-size:11px}
.badge.ml{border-color:var(--ok);color:var(--ok)}
.delta.pos{color:var(--ok)}.delta.zero{color:var(--mut)}
.chain{display:flex;flex-direction:column;gap:10px}
.step{display:flex;gap:10px;align-items:flex-start;padding:10px;border:1px solid var(--line);border-radius:12px;background:#101113}
.dot{width:10px;height:10px;border-radius:50%;margin-top:4px;flex:0 0 auto}
.dot.sealed{background:var(--ok)}.dot.in_progress{background:var(--run)}.dot.locked{background:var(--lock)}
.step .nm{font-weight:600;font-size:13px}.step .nt{color:var(--mut);font-size:11px;margin-top:2px}
.cmd{background:#0e0f10;border:1px solid var(--line);border-radius:10px;padding:10px;font-family:ui-monospace,Menlo,monospace;font-size:12px;display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:8px}
.cmd button{background:var(--accent);border:0;color:#012;border-radius:7px;padding:4px 10px;cursor:pointer;font-weight:600}
.files{font-size:12px;color:var(--mut)}.files .new{color:var(--run)}
#art{display:none}
.art-body{font-size:13px;line-height:1.55;max-height:70vh;overflow:auto}
.art-body h1,.art-body h2,.art-body h3{color:var(--ink)}.art-body a{color:var(--accent);text-decoration:none}
.art-body code{background:#0e0f10;padding:1px 5px;border-radius:5px;font-size:12px}
.back{cursor:pointer;color:var(--accent);font-size:12px;margin-bottom:10px;display:inline-block}
.muted{color:var(--mut);font-size:12px}
.uz{border:1.5px dashed #3a3d42;border-radius:12px;padding:18px;text-align:center;color:var(--mut);cursor:pointer;font-size:13px;transition:.15s;margin-bottom:8px}
.uz:hover{border-color:var(--accent);color:var(--ink)}.uz.drag{border-color:var(--ok);background:#0f1a14;color:var(--ok)}
#umsg{font-size:12px;margin-bottom:10px;min-height:16px}
</style></head><body><div class="wrap">
<h1>🧠 SOCC Memory — живая вики</h1>
<div class="sub" id="gen"></div>

<div class="kpis" id="kpis"></div>

<div id="home"><div class="grid">
<div>
  <div class="card"><h2>Темы знания — было→стало</h2><table id="topics"><thead><tr>
    <th>Тема</th><th>Current</th><th>Δ</th><th>Conflict</th><th>Timeline</th><th>Sources</th><th>Main line</th>
  </tr></thead><tbody></tbody></table>
  <div class="muted" style="margin-top:8px">Клик по теме — открыть статью с гиперссылками на сырьё.</div></div>
</div>
<div>
  <div class="card"><h2>Цель-цепочка</h2><div class="chain" id="chain"></div></div>
  <div class="card"><h2>Залить файл</h2>
    <div class="uz" id="uz">⬆️ Перетащи файл сюда или кликни<br><span class="muted">.txt · .md · .eml · .json</span></div>
    <input type="file" id="fi" accept=".txt,.md,.eml,.json" hidden>
    <div id="umsg"></div>
    <div class="muted">Файл уходит в <code>inbox/</code>, система сама разбирает и вносит в вики. Нужен запущенный локальный сервер.</div>
  </div>
  <div class="card"><h2>Управление (вручную)</h2>
    <div class="cmd"><span>python3 ~/SOCC/scripts/socc/socc_memory_server_v1.py</span><button onclick="cp(this)">copy</button></div>
    <div class="muted">Запусти сервер → открой <code>http://127.0.0.1:8787</code> → грузи файлы кнопкой выше.</div>
    <div class="cmd" style="margin-top:8px"><span>python3 ~/SOCC/scripts/socc/socc_memory_ingest_v1.py</span><button onclick="cp(this)">copy</button></div>
    <div class="muted">Или без сервера: лей в <code>SOVEREIGN/MEMORY/inbox/</code> (или синк Google Drive) и гони эту команду.</div>
    <div id="run" style="margin-top:12px"></div>
  </div>
</div>
</div></div>

<div id="art"><span class="back" onclick="home()">← назад к темам</span><div class="card"><div class="art-body" id="artbody"></div></div></div>

<script>
const D = __DATA__;
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function md(t){return esc(t)
  .replace(/^### (.*)$/gm,'<h3>$1</h3>').replace(/^## (.*)$/gm,'<h2>$1</h2>').replace(/^# (.*)$/gm,'<h1>$1</h1>')
  .replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2">$1</a>')
  .replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>').replace(/`([^`]+)`/g,'<code>$1</code>')
  .replace(/^- (.*)$/gm,'• $1').replace(/\n/g,'<br>')}
function cp(b){navigator.clipboard.writeText(b.previousElementSibling.textContent);b.textContent='ok'}
const r=D.run||{},c=r.counts||{};
document.getElementById('gen').textContent='собрано '+(D.generated||'')+' · источников: '+D.sources;
document.getElementById('kpis').innerHTML=[
 ['Источников',D.sources,''],['Тем',D.topics.length,''],
 ['Новых (посл. прогон)',c.new||0,(c.new?'hot':'')],['Изменённых',c.changed||0,(c.changed?'hot':'')],
 ['Claims добавлено',r.claims_added||0,'']
].map(k=>'<div class="kpi '+k[2]+'"><div class="n">'+k[1]+'</div><div class="l">'+k[0]+'</div></div>').join('');
const dmap={};(r.deltas||[]).forEach(d=>dmap[d.topic]=d.d_current);
document.querySelector('#topics tbody').innerHTML=D.topics.map(t=>{
 const dc=dmap[t.topic]||0,cls=dc>0?'pos':'zero',txt=dc>0?'+'+dc:'0';
 return '<tr class="t" onclick="open_('+"'"+t.slug+"'"+')"><td>'+t.topic+'</td><td>'+t.current+'</td>'
 +'<td class="delta '+cls+'">'+txt+'</td><td>'+t.conflicting+'</td><td>'+t.timeline+'</td><td>'+t.sources+'</td>'
 +'<td>'+(t.main_line_authored?'<span class="badge ml">authored</span>':'<span class="badge">—</span>')+'</td></tr>'}).join('');
document.getElementById('chain').innerHTML=D.goal_chain.map(s=>
 '<div class="step"><div class="dot '+s.state+'"></div><div><div class="nm">'+s.name+'</div><div class="nt">'+s.note+'</div></div></div>').join('');
const nf=(r.new_files||[]);
document.getElementById('run').innerHTML='<div class="muted">Последний прогон: всего '+(c.total||0)+' · <span style="color:var(--run)">новых '+(c.new||0)+'</span> · без изм. '+(c.unchanged||0)+'</div>'+
 (nf.length?'<div class="files" style="margin-top:6px">'+nf.slice(0,8).map(f=>'<div><span class="new">['+f.status+']</span> '+f.file+'</div>').join('')+'</div>':'');
function open_(slug){const a=D.articles[slug];if(!a)return;document.getElementById('artbody').innerHTML=md(a);
 document.getElementById('home').style.display='none';document.getElementById('art').style.display='block';window.scrollTo(0,0)}
function home(){document.getElementById('art').style.display='none';document.getElementById('home').style.display='block'}
const uz=document.getElementById('uz'),fi=document.getElementById('fi');
function um(t,c){const m=document.getElementById('umsg');m.textContent=t;m.style.color=c||'var(--mut)'}
uz.onclick=()=>fi.click();
fi.onchange=e=>{if(e.target.files[0])up(e.target.files[0])};
uz.ondragover=e=>{e.preventDefault();uz.classList.add('drag')};
uz.ondragleave=()=>uz.classList.remove('drag');
uz.ondrop=e=>{e.preventDefault();uz.classList.remove('drag');if(e.dataTransfer.files[0])up(e.dataTransfer.files[0])};
async function up(f){
 um('⏳ Загружаю «'+f.name+'» и разбираю…');
 try{
  const r=await fetch('/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(f.name)},body:f});
  const j=await r.json();
  if(j.ok){um('✓ Принято: «'+j.filename+'» · новых '+(j.counts.new||0)+' · claims +'+(j.claims_added||0)+'. Обновляю…','var(--ok)');setTimeout(()=>location.reload(),1000)}
  else um('✗ '+(j.error||'ошибка'),'#f77')
 }catch(e){um('✗ Нет сервера. Запусти: python3 scripts/socc/socc_memory_server_v1.py','#f77')}
}
</script></div></body></html>"""


def main():
    data = load()
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    OUT.write_text(html, encoding="utf-8")
    print("SOCC MEMORY DASHBOARD — BUILT")
    print(f"  topics : {len(data['topics'])}  ·  sources : {data['sources']}")
    print(f"  open   : {OUT}")


if __name__ == "__main__":
    main()

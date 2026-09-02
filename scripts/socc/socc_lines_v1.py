#!/usr/bin/env python3
"""
SOCC Lines V1 — дисциплина рабочих линий (L0 порядка).

Линия = одна CLI-сессия Claude Code (чат-диалог). У неё есть цель/тема и живой PID.
Этот инструмент наводит над линиями тот же детерминированный порядок, что spine навёл над
знанием: один источник правды (реестр), честная liveness, детект дублей, протокол handoff,
страж дрейфа, привязка к узлу карты ANNA_REAL_PRODUCT_ROADMAP_V1 («ты здесь»).

Детерминированно. Без LLM, без сети, без демона. Линии НЕ убиваются автоматически —
система только показывает правду и ПРЕДЛАГАЕТ handoff; решает оператор.

Команды:
  enroll  --goal "<цель>" [--pid N] [--node L2] [--main]   # зарегистрировать текущую линию
  ls                                                        # все линии + честная liveness
  check   [--observed "<что линия реально делает>"]          # дубли + дрейф + мёртвые
  handoff --from <line_id> --to <line_id> [--note "..."]     # слить вторичную в основную
  absorb  --line <line_id>                                   # основная поглощает адресованные ей handoff'ы
  retire  --line <line_id>                                   # закрыть линию вручную
  pin     --line <line_id> --node L2                         # перешпилить линию на узел карты

Примеры:
  python3 scripts/socc/socc_lines_v1.py enroll --goal "ANNA: реальная запись в календарь" --main
  python3 scripts/socc/socc_lines_v1.py ls
  python3 scripts/socc/socc_lines_v1.py check --observed "правлю graph.html, физика узлов"
"""
import os, sys, json, hashlib, argparse
from pathlib import Path
from datetime import datetime, timezone

SOCC = Path(__file__).resolve().parents[2]            # .../SOCC
# MERGED 2026-06-30 (handoff): canonical registry is the LINE_GOVERNANCE organ's single source of truth.
# This tool is its working operational layer (P1.5 socc-lines · P3 dedup · P4 handoff · P5 drift) —
# it manages the `lines` array; the organ's P0 observe snapshot (observed_processes/sessions) is preserved.
REGISTRY = SOCC / "SYSTEM" / "LINE_GOVERNANCE" / "runtime" / "ACTIVE_LINES_REGISTRY_V1.json"
TOPIC_MAP = SOCC / "SOVEREIGN" / "WIKI" / "TOPIC_MAP_V1.json"
ROADMAP = SOCC / "SYSTEM" / "LINE_GOVERNANCE" / "LINE_GOVERNANCE_ROADMAP.md"
LEDGER = SOCC / "SOVEREIGN" / "LEDGER" / "line_discipline.ledger.jsonl"

# Узлы карты roadmap — детерминированные подсказки «ты здесь» (отдельная ось от темы spine)
NODE_HINTS = {
    "L0": ["лини", "дисциплин", "дубл", "handoff", "хэндофф", "реестр", "registry", "drift", "дрейф", "порядок", "сесси", "pid"],
    "L1": ["мозг", "fallback", "watchdog", "неубива", "рестарт", "ключ", "401", "402", "надёжн", "надежн", "runtime", "устойчив", "failover"],
    "L2": ["запис", "booking", "календар", "crm", "yclients", "dikidi", "напоминан", "подтвержд", "слот"],
    "L3": ["пилот", "выгод", "roi", "ledger", "выручк", "деньг", "первая клиник"],
    "L4": ["кабинет", "владел", "owner", "cockpit"],
    "L5": ["канал", "max", "whatsapp", "avito", "голос", "voice", "stt", "tts", "мультикан"],
    "L6": ["обучен", "training", "разбор", "слаб", "learning", "диалог"],
    "L7": ["флот", "масштаб", "1000", "биллинг", "подписк", "онбординг", "tenant", "аренд", "самопрод"],
    "L8": ["вертикал", "ниш", "фабрик"],
}


def now():
    return datetime.now(timezone.utc).isoformat()


def load_topics():
    try:
        return json.loads(TOPIC_MAP.read_text()).get("topics", [])
    except Exception:
        return []


def detect_theme(text):
    """Тема spine по ключевым словам TOPIC_MAP. Тай → меньший rank (специфичнее)."""
    t = (text or "").lower()
    best, best_hits, best_rank = None, 0, 99
    for topic in load_topics():
        hits = sum(1 for kw in topic.get("keywords", []) if kw.lower() in t)
        rank = topic.get("rank", 99)
        if hits > best_hits or (hits == best_hits and hits > 0 and rank < best_rank):
            best, best_hits, best_rank = topic, hits, rank
    if not best or best_hits == 0:
        return {"theme": "unassigned", "theme_title": "—", "hits": 0}
    return {"theme": best["id"], "theme_title": best["title"], "hits": best_hits}


def detect_node(text):
    """Узел карты roadmap по ключевым словам (L0..L8)."""
    t = (text or "").lower()
    best, best_hits = None, 0
    for node, kws in NODE_HINTS.items():
        hits = sum(1 for kw in kws if kw in t)
        if hits > best_hits:
            best, best_hits = node, hits
    return best


def load_registry():
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text())
    return {"id": "LINE_REGISTRY_V1", "schema": "socc.line_registry.v1",
            "note": "Реестр рабочих линий (CLI-сессий). Один источник правды. Liveness через kill -0.",
            "lines": []}


def save_registry(reg):
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2))
    tmp.replace(REGISTRY)            # атомарная замена


def ledger(event):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps({**event, "ts": now()}, ensure_ascii=False) + "\n")


def alive(pid):
    """Честная проверка: жив ли процесс. kill -0 не убивает, только проверяет."""
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def sweep(reg):
    """Освежить status по liveness. Мёртвые active/idle → closed."""
    for ln in reg["lines"]:
        if ln["status"] in ("active", "idle") and not alive(ln.get("pid")):
            ln["status"] = "closed"
            ln["last_seen"] = now()
            ledger({"event": "auto_closed_dead_pid", "line_id": ln["id"], "pid": ln.get("pid")})
    return reg


def find(reg, line_id):
    for ln in reg["lines"]:
        if ln["id"] == line_id:
            return ln
    return None


def short_id(cwd, pid, started):
    h = hashlib.sha256(f"{cwd}|{pid}|{started}".encode()).hexdigest()[:8]
    return f"ln-{h}"


# ── команды ──────────────────────────────────────────────────────────────────
def cmd_enroll(a):
    reg = sweep(load_registry())
    pid = a.pid or os.getppid()           # по умолчанию — родитель (shell/claude-сессия)
    cwd = os.getcwd()
    started = now()
    th = detect_theme(a.goal)
    node = a.node or detect_node(a.goal)
    lid = short_id(cwd, pid, started)

    # уже есть живая линия с тем же pid+cwd? обновим, не плодим дубль
    existing = next((l for l in reg["lines"]
                     if l.get("pid") == pid and l.get("cwd") == cwd and l["status"] in ("active", "idle")), None)
    if existing:
        existing.update(declared_goal=a.goal, theme=th["theme"], theme_title=th["theme_title"],
                        roadmap_node=node, last_seen=started, is_main=bool(a.main) or existing.get("is_main", False))
        save_registry(reg)
        print(f"♻️  обновил существующую линию {existing['id']} (pid {pid})")
        line = existing
    else:
        line = {"id": lid, "pid": pid, "cwd": cwd, "tty": os.environ.get("TTY") or os.ttyname(0) if sys.stdin.isatty() else None,
                "declared_goal": a.goal, "theme": th["theme"], "theme_title": th["theme_title"],
                "roadmap_node": node, "is_main": bool(a.main),
                "started_at": started, "last_seen": started, "status": "active",
                "absorbed": [], "handoff_note": None}
        reg["lines"].append(line)
        save_registry(reg)
        ledger({"event": "enroll", "line_id": lid, "pid": pid, "theme": th["theme"], "node": node, "goal": a.goal})
        print(f"✅ линия {lid} зарегистрирована (pid {pid})")

    print(f"   тема: {th['theme']} · узел карты: {node or '—'} · основная: {'да' if line.get('is_main') else 'нет'}")
    _conflicts(reg, line)


def _conflicts(reg, line):
    """Показать дубли по теме среди живых линий."""
    dups = [l for l in reg["lines"]
            if l["id"] != line["id"] and l["status"] in ("active", "idle")
            and l["theme"] == line["theme"] and line["theme"] != "unassigned"]
    if dups:
        print(f"\n⚠️  ДУБЛЬ по теме «{line['theme']}»:")
        for d in dups:
            print(f"   • {d['id']} (pid {d['pid']}) — {d['declared_goal']}")
        print(f"   → одна тема = одна основная линия. Слей: socc_lines_v1.py handoff --from <вторичная> --to <основная>")


def cmd_ls(a):
    reg = sweep(load_registry())
    save_registry(reg)
    active = [l for l in reg["lines"] if l["status"] in ("active", "idle")]
    print(f"📋 Линии — активных: {len(active)} · всего в реестре: {len(reg['lines'])}\n")
    for ln in reg["lines"]:
        live = alive(ln.get("pid"))
        mark = "🟢" if (ln["status"] in ("active", "idle") and live) else ("🔴" if ln["status"] == "closed" else "⚪")
        main = " ⭐основная" if ln.get("is_main") else ""
        print(f"{mark} {ln['id']} · pid {ln.get('pid')} {'(жив)' if live else '(мёртв)'} · "
              f"{ln['status']}{main}")
        print(f"     цель: {ln['declared_goal']}")
        print(f"     тема: {ln['theme']} · узел: {ln.get('roadmap_node') or '—'} · cwd: {ln.get('cwd')}")
    # честный отчёт по дублям
    _all_conflicts(reg)


def _all_conflicts(reg):
    by_theme = {}
    for l in reg["lines"]:
        if l["status"] in ("active", "idle") and l["theme"] != "unassigned":
            by_theme.setdefault(l["theme"], []).append(l)
    dups = {t: ls for t, ls in by_theme.items() if len(ls) > 1}
    if dups:
        print("\n⚠️  КОНФЛИКТЫ (одна тема — несколько живых линий):")
        for t, ls in dups.items():
            ids = ", ".join(f"{l['id']}(pid {l['pid']})" for l in ls)
            print(f"   • {t}: {ids}  → нужен handoff в одну основную")
    else:
        print("\n✅ дублей нет — каждая тема ведётся одной линией")


def cmd_check(a):
    reg = sweep(load_registry())
    save_registry(reg)
    print("🔎 Проверка дисциплины линий\n")
    _all_conflicts(reg)

    # дрейф: сверяем объявленную тему живых линий с наблюдаемым сигналом
    if a.observed:
        obs = detect_theme(a.observed)
        obs_node = detect_node(a.observed)
        print(f"\n🧭 Наблюдаемая работа → тема: {obs['theme']} · узел: {obs_node or '—'}")
        for ln in reg["lines"]:
            if ln["status"] not in ("active", "idle"):
                continue
            if obs["theme"] != "unassigned" and ln["theme"] != "unassigned" and obs["theme"] != ln["theme"]:
                print(f"\n⚠️  ДРЕЙФ линии {ln['id']}: объявлена «{ln['theme']}», "
                      f"а работа похожа на «{obs['theme']}».")
                print(f"   → перешпиль: socc_lines_v1.py pin --line {ln['id']} --node {obs_node or '?'}")
                print(f"   → или handoff в линию темы «{obs['theme']}», если такая есть.")
                ledger({"event": "drift_flag", "line_id": ln["id"],
                        "declared": ln["theme"], "observed": obs["theme"]})
    else:
        print("\n(совет: socc_lines_v1.py check --observed \"что линия реально делает\" — поймает дрейф)")


def cmd_handoff(a):
    reg = sweep(load_registry())
    src, dst = find(reg, a.__dict__["from"]), find(reg, a.to)
    if not src or not dst:
        print("❌ не нашёл одну из линий (проверь id через ls)"); return
    src["status"] = "handed_off"
    src["handoff_note"] = a.note or f"передано в {dst['id']}"
    src["last_seen"] = now()
    dst.setdefault("absorbed", []).append({"from": src["id"], "goal": src["declared_goal"],
                                           "note": src["handoff_note"], "ts": now(), "absorbed": False})
    dst["is_main"] = True
    save_registry(reg)
    ledger({"event": "handoff", "from": src["id"], "to": dst["id"], "note": src["handoff_note"]})
    print(f"🤝 {src['id']} → {dst['id']}. Вторичная закрыта (handed_off), основная получила заметку.")
    print(f"   Основная линия {dst['id']} должна выполнить: absorb --line {dst['id']}")


def cmd_absorb(a):
    reg = load_registry()
    ln = find(reg, a.line)
    if not ln:
        print("❌ линия не найдена"); return
    pend = [x for x in ln.get("absorbed", []) if not x.get("absorbed")]
    if not pend:
        print(f"✅ {ln['id']}: нечего поглощать — все handoff'ы уже впитаны"); return
    print(f"📥 {ln['id']} поглощает {len(pend)} handoff(ов):")
    for x in pend:
        x["absorbed"] = True
        print(f"   • из {x['from']}: {x['goal']}")
        print(f"     заметка: {x['note']}")
    save_registry(reg)
    ledger({"event": "absorb", "line_id": ln["id"], "count": len(pend)})
    print("   → основной чат теперь знает, что происходило в поглощённых линиях.")


def cmd_retire(a):
    reg = load_registry()
    ln = find(reg, a.line)
    if not ln:
        print("❌ линия не найдена"); return
    ln["status"] = "closed"; ln["last_seen"] = now()
    save_registry(reg)
    ledger({"event": "retire", "line_id": ln["id"]})
    print(f"⚪ {ln['id']} закрыта вручную.")


def cmd_pin(a):
    reg = load_registry()
    ln = find(reg, a.line)
    if not ln:
        print("❌ линия не найдена"); return
    ln["roadmap_node"] = a.node; ln["last_seen"] = now()
    save_registry(reg)
    ledger({"event": "repin", "line_id": ln["id"], "node": a.node})
    print(f"📌 {ln['id']} перешпилена на узел карты {a.node}.")


# ── scan: АВТО-ОБНАРУЖЕНИЕ живых линий из ОС (read-only, R0) ───────────────────
# Закрывает прямую просьбу оператора: «система сама понимала сколько активно PID
# и какова тема=цель». enroll — декларативен (линия сама регистрируется); scan —
# наблюдателен (система сама находит живые сессии claude, даже если они молчат).
import re as _re, subprocess as _sp

_RESUME = _re.compile(r"--resume\s+([0-9a-fA-F-]{36})")
_SKIP = ("<", "[Request interrupted", "Caveat:", "Contents of ")


def _sh(cmd):
    try:
        return _sp.run(cmd, capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return ""


def _ps_lines():
    """Живые процессы 'claude', отфильтрованные от sub-shell'ов (/bin/zsh -c ... grep)."""
    found = []
    for raw in _sh(["ps", "-Ao", "pid=,ppid=,tty=,etime=,command="]).splitlines():
        parts = raw.strip().split(None, 4)
        if len(parts) < 5:
            continue
        pid, ppid, tty, etime, cmd = parts
        low = cmd.lower()
        if "claude" not in low or "socc_lines" in low:
            continue
        head = cmd.split()[0]
        if not (head.endswith("/claude") or head == "claude"):
            continue                       # отсекаем sub-shell'ы и grep
        origin = ("vscode" if ".vscode/extensions/anthropic.claude-code" in cmd
                  else "terminal" if tty.startswith("ttys") else "other")
        m = _RESUME.search(cmd)
        found.append({"pid": int(pid), "ppid": ppid, "tty": tty, "etime": etime,
                      "origin": origin, "uuid": m.group(1) if m else None})
    return found


def _cwd_of(pid):
    for ln in _sh(["lsof", "-a", "-d", "cwd", "-p", str(pid), "-Fn"]).splitlines():
        if ln.startswith("n"):
            return ln[1:]
    return None


def _transcript(uuid, cwd):
    if not uuid:
        return None
    base = Path.home() / ".claude" / "projects"
    cands = []
    if cwd:
        cands.append(base / (cwd.replace("/", "-").replace(".", "-")))
    if base.exists():
        cands += [d for d in base.iterdir() if d.is_dir()]
    for d in cands:
        p = d / f"{uuid}.jsonl"
        if p.exists():
            return p
    return None


def _head_goal(path, max_lines=400):
    """Первая НАСТОЯЩАЯ реплика человека (skip IDE-инъекций <...>, прерываний, шума)."""
    if not path or not path.exists():
        return None
    try:
        with path.open(errors="ignore") as f:
            for i, ln in enumerate(f):
                if i > max_lines:
                    break
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    o = json.loads(ln)
                except Exception:
                    continue
                if o.get("type") != "user":
                    continue
                c = (o.get("message") or {}).get("content")
                if isinstance(c, str):
                    txt = c
                elif isinstance(c, list):
                    txt = " ".join(b.get("text", "") for b in c
                                   if isinstance(b, dict) and b.get("type") == "text")
                else:
                    txt = ""
                txt = (txt or "").strip()
                if txt and not txt.startswith(_SKIP):
                    return txt[:160]
    except Exception:
        return None
    return None


def cmd_scan(a):
    reg = sweep(load_registry())
    disc = _ps_lines()
    print(f"\n🛰  СКАНЕР ЖИВЫХ ЛИНИЙ — система сама нашла {len(disc)} сессий claude (read-only)\n")
    enrolled_pids = {l.get("pid"): l for l in reg["lines"] if l["status"] in ("active", "idle")}
    rows = []
    for d in disc:
        d["cwd"] = _cwd_of(d["pid"])
        d["goal"] = _head_goal(_transcript(d["uuid"], d["cwd"]))
        th = detect_theme(d["goal"])
        d["theme"], d["theme_title"], d["node"] = th["theme"], th["theme_title"], detect_node(d["goal"])
        rows.append(d)
        lid = d["uuid"][:8] if d["uuid"] else "UNRESOLVED"
        conf = "★1.0" if d["uuid"] else "?fresh"
        enr = "✅ в реестре" if d["pid"] in enrolled_pids else "⚠ НЕ в реестре"
        print(f"  ▸ {lid:<10} {conf:<6} pid {d['pid']:<7} {d['origin']:<8} age {d['etime']:<11} {enr}")
        print(f"      тема: {d['theme']} · узел карты: {d['node'] or '—'}")
        print(f"      цель: {d['goal'] or '(свежая линия — uuid/цель не извлечены; нужен enroll или --resume)'}")
    by_theme = {}
    for d in rows:
        if d["theme"] != "unassigned" and d["uuid"]:
            by_theme.setdefault(d["theme"], []).append(d)
    dups = {t: ls for t, ls in by_theme.items() if len(ls) > 1}
    print()
    if dups:
        print("  ⚠ ДУБЛИ ПО ТЕМЕ (одна тема — несколько живых линий) — честно объявлены, НЕ слиты:")
        for t, ls in dups.items():
            print(f"    • {t}: " + ", ".join((d['uuid'][:8] if d['uuid'] else 'fresh') + f"(pid {d['pid']})" for d in ls))
        print("    → одна тема = одна основная линия: handoff --from <вторичная> --to <основная> (под approve)")
    else:
        print("  ✓ среди разрешённых живых линий дублей по теме не найдено")
    dead = [l for l in reg["lines"] if l["status"] in ("active", "idle") and not alive(l.get("pid"))]
    if dead:
        print("\n  🔴 в реестре есть мёртвые линии: " + ", ".join(l["id"] for l in dead) + " → ls обновит статус")
    if getattr(a, "sync", False):
        added = 0
        for d in rows:
            if d["uuid"] and d["pid"] not in enrolled_pids:
                reg["lines"].append({
                    "id": f"ln-{d['uuid'][:8]}", "pid": d["pid"], "cwd": d["cwd"], "tty": d["tty"],
                    "declared_goal": d["goal"] or "(auto-discovered)", "theme": d["theme"],
                    "theme_title": d["theme_title"], "roadmap_node": d["node"], "is_main": False,
                    "started_at": now(), "last_seen": now(), "status": "active",
                    "absorbed": [], "handoff_note": None, "source": "scan"})
                added += 1
        save_registry(reg)
        ledger({"event": "scan_sync", "discovered": len(rows), "added": added})
        print(f"\n  ⟲ --sync: в реестр добавлено {added} ранее незарегистрированных живых линий")
    else:
        print("\n  (read-only — ничего не записано. влить найденное в реестр: scan --sync)")
    print()


def main():
    p = argparse.ArgumentParser(description="SOCC Lines V1 — дисциплина рабочих линий")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enroll"); e.add_argument("--goal", required=True); e.add_argument("--pid", type=int)
    e.add_argument("--node"); e.add_argument("--main", action="store_true"); e.set_defaults(fn=cmd_enroll)

    sub.add_parser("ls").set_defaults(fn=cmd_ls)

    c = sub.add_parser("check"); c.add_argument("--observed"); c.set_defaults(fn=cmd_check)

    h = sub.add_parser("handoff"); h.add_argument("--from", required=True); h.add_argument("--to", required=True)
    h.add_argument("--note"); h.set_defaults(fn=cmd_handoff)

    ab = sub.add_parser("absorb"); ab.add_argument("--line", required=True); ab.set_defaults(fn=cmd_absorb)
    r = sub.add_parser("retire"); r.add_argument("--line", required=True); r.set_defaults(fn=cmd_retire)
    pn = sub.add_parser("pin"); pn.add_argument("--line", required=True); pn.add_argument("--node", required=True)
    pn.set_defaults(fn=cmd_pin)

    sc = sub.add_parser("scan"); sc.add_argument("--sync", action="store_true"); sc.set_defaults(fn=cmd_scan)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

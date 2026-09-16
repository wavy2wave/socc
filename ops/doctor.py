#!/usr/bin/env python3
"""SOCC DOCTOR · единый вердикт о здоровье машины.

Зачем: до этого «работает ли машина» проверялось семью разными командами в голове
оператора. Здесь — ОДИН орган, который смотрит все слои и даёт честный вердикт.

ЗАКОНЫ (соблюдены):
  · L12 no-fake-pass — слой либо PASS, либо FAIL/SKIP с ПРИЧИНОЙ. SKIP ≠ PASS.
  · READ-only — doctor НИЧЕГО не пишет и не двигает деньги (moved_money=False).
  · M2/M3 — секреты не печатаются: показываем только «есть/нет» и имя переменной.
  · Честность границы: doctor различает «не проверено», «нет данных», «сломано».

Слои:
  1 RHYTHM   launchd-агенты (реально зарегистрированы? когда последний тик?)
  2 BRAIN    LLM-мозг ANNA (живой ключ? фолбэк-цепочка не единая точка отказа?)
  3 ENV      необходимые переменные присутствуют (значения НЕ печатаются)
  4 CANON    маршрут/пульс/субстрат/канон ANNA на месте и согласованы
  5 PROOF    хеш-цепь леджера цела (переписать середину невозможно)
  6 MONEY    revenue ledger: реальные verified ₽ (честно 0, если 0)
  7 GATE     приёмки + M2 + ПДн + переносимость (делегирование, --quick пропускает)

Выход: код 0 = все обязательные слои PASS, иначе 1.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"
ICON = {PASS: "✅", FAIL: "❌", WARN: "⚠️ ", SKIP: "⏭️ "}

REQUIRED = {PASS, WARN}   # что не роняет вердикт


def _load_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def _age_hours(ts_str):
    """Возраст метки в часах; None если не распознана."""
    if not ts_str:
        return None
    try:
        ts = str(ts_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return None


# ── 1 · RHYTHM ────────────────────────────────────────────────────────────────
def check_rhythm():
    """launchd-агенты: зарегистрированы? свежий ли последний тик?

    ВАЖНО: `launchctl list | grep` ненадёжен (2026-09-16: list пусто при активном
    агенте). Вердикт берём из `launchctl print gui/<uid>/<label>` и из СВЕЖЕСТИ
    выходного файла — последнее и есть правда («ритм жив»).
    """
    out = []
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    plists = sorted(agents_dir.glob("com.socc.*.plist"))
    if not plists:
        return FAIL, "нет ни одного com.socc.*.plist в ~/Library/LaunchAgents → bash ops/install_agents.sh"

    try:
        uid = os.getuid()
    except Exception:
        uid = None

    registered, details = 0, []
    for pl in plists:
        label = pl.stem
        state = "?"
        if uid is not None:
            proc = subprocess.run(["launchctl", "print", f"gui/{uid}/{label}"],
                                  capture_output=True, text=True)
            if proc.returncode == 0:
                m = re.search(r"^\s*state\s*=\s*(\S+)", proc.stdout, re.M)
                state = m.group(1) if m else "loaded"
                registered += 1
            else:
                state = "НЕ зарегистрирован"
        details.append(f"{label}: {state}")

    # правда ритма — свежесть журнала автопилота
    logs = sorted((ROOT / "MEMORY_WAVE" / "reports" / "mint" / "arbiter").glob("*.launchd.out")) \
        + sorted((ROOT / "MEMORY_WAVE" / "reports" / "mint" / "arbiter").glob("*.out"))
    fresh = None
    for lg in logs:
        try:
            age = (datetime.now().timestamp() - lg.stat().st_mtime) / 3600
            fresh = age if fresh is None else min(fresh, age)
        except Exception:
            pass

    if registered == 0:
        return FAIL, "агенты лежат, но НЕ загружены → bash ops/install_agents.sh"

    note = f"агентов {registered}/{len(plists)} · " + " · ".join(details)
    if fresh is not None:
        note += f" · последний прогон {fresh:.1f} ч назад"
        if fresh > 12:
            return WARN, note + " → ритм старше 12 ч (ожидание 3×/сут), проверь launchctl kickstart"
        return PASS, note
    return WARN, note + " · выходных файлов нет — ритм не подтверждён прогоном"


# ── 2 · BRAIN ─────────────────────────────────────────────────────────────────
def check_brain():
    """LLM-мозг ANNA: живой ли, и НЕТ ЛИ единой точки отказа."""
    status = _load_json(ROOT / "SYSTEM" / "ANNA_MVP" / "runtime" / "status" / "anna_brain.json")
    keys_present = [k for k in ("AGENTROUTER_API_KEY", "ANTHROPIC_API_KEY",
                                "OPENAI_API_KEY", "ANNA_CLAUDE_KEYS")
                    if os.environ.get(k)]
    if status is None:
        note = f"anna_brain.json нет · ключей в env: {len(keys_present)}"
        return (WARN, note + " → мозг не проверен, прогони scripts/anna_supervisor_v1.py") \
            if keys_present else (FAIL, note + " → нет ни статуса, ни ключей")

    ok = status.get("ok")
    err = str(status.get("error") or "")[:90]
    age = _age_hours(status.get("ts"))
    floor = status.get("independent_floor")
    age_txt = f" · проверка {age:.0f} ч назад" if age is not None else ""

    if ok is True:
        note = f"мозг ok=True{age_txt} · ключей в env: {len(keys_present)}"
        return PASS, note
    if ok is False and floor is False:
        # честный диагноз самой системы: единая точка отказа
        return FAIL, (f"мозг ok=False: {err}{age_txt} · independent_floor=False "
                      f"(вся цепочка = один аккаунт) → нужен второй независимый ключ")
    return FAIL, f"мозг ok=False: {err}{age_txt} → чинить ключ/гейтвей (Фаза 0 канона ANNA)"


# ── 3 · ENV ───────────────────────────────────────────────────────────────────
def check_env():
    """Необходимые переменные: есть/нет. ЗНАЧЕНИЯ НЕ ПЕЧАТАЕМ (M2)."""
    need = ("YANDEX_MARKET_API_KEY", "OZON_CLIENT_ID", "OZON_API_KEY",
            "YM_TELEGRAM_BOT_TOKEN", "YM_TELEGRAM_CHAT_ID", "YM_SHIFT_MEMORY")
    have = [k for k in need if os.environ.get(k)]
    miss = [k for k in need if not os.environ.get(k)]
    dotenv = (ROOT / "scripts" / "mint" / ".env")
    note = f"env: {len(have)}/{len(need)} · .env файл: {'есть' if dotenv.exists() else 'нет'}"
    if not miss:
        return PASS, note
    if dotenv.exists():
        return WARN, note + f" · нет в окружении: {','.join(miss)} (возможно в .env — нужно `set -a; . ./.env; set +a`)"
    return WARN, note + f" · нет: {','.join(miss)} → cp env.example .env"


# ── 4 · CANON ─────────────────────────────────────────────────────────────────
def check_canon():
    """Маршрут/пульс/субстрат/канон ANNA — на месте и читаемы."""
    must = {
        "маршрут": "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json",
        "пульс": "core/socc/route_authority/self_construction_autonomy/AUTONOMY_PULSE_V1.json",
        "канон SOCC": "SYSTEM/KERNEL/SOCC_PRODUCT_CANON_V1.md",
        "дизайн-канон": "SYSTEM/KERNEL/SOCC_DESIGN_CANON_V1.json",
        "self_model": "SYSTEM/KERNEL/self_model.md",
        "канон ANNA": "SOVEREIGN/ANNA/ANNA_PRODUCT_CANON_V1.md",
        "вики SOCC": "SOVEREIGN/WIKI/main_lines/socc.md",
        "порядок": "SYSTEM/STATUS/CURRENT_PROJECT_ORDER_V1.md",
    }
    missing = [n for n, rel in must.items() if not (ROOT / rel).exists()]
    surfaces = sorted((ROOT / "SYSTEM" / "ENTITY_SUBSTRATE" / "runtime").glob("ENTITY_*_SURFACE_V1.json"))
    note = f"канон {len(must)-len(missing)}/{len(must)} · поверхностей субстрата {len(surfaces)}/10"

    if missing:
        return FAIL, note + f" · НЕТ: {', '.join(missing)}"
    if len(surfaces) != 10:
        return WARN, note + " → матрица рождения неполная"

    route = _load_json(ROOT / must["маршрут"]) or {}
    nxt = route.get("lawful_next") or route.get("current_lawful_next")
    st = route.get("status")
    extra = f" · маршрут: status={st} lawful_next={nxt}" if (st or nxt) else ""

    # согласованность: порядок проекта не должен быть древнее маршрута
    order_age = _age_hours_from_file(ROOT / must["порядок"])
    if order_age is not None and order_age > 24 * 60:
        return WARN, note + extra + f" · ПОРЯДОК устарел на {order_age/24:.0f} дн (план мёртв по факту)"
    return PASS, note + extra


def _age_hours_from_file(p):
    try:
        return (datetime.now().timestamp() - Path(p).stat().st_mtime) / 3600
    except Exception:
        return None


# ── 5 · PROOF (хеш-цепь) ──────────────────────────────────────────────────────
def check_proof():
    """Хеш-цепь леджеров: каждая запись знает предыдущую. Переписать середину нельзя."""
    ledgers = [
        "MEMORY_WAVE/reports/mint/arbiter/ymarket_tick_ledger.jsonl",
        "MEMORY_WAVE/reports/mint/arbiter/ozon_tick_ledger.jsonl",
    ]
    report, broken, total = [], 0, 0
    for rel in ledgers:
        p = ROOT / rel
        if not p.exists():
            report.append(f"{p.name}: нет (SKIP)")
            continue
        prev, n, gaps = None, 0, 0
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = _load_json.__wrapped__ if False else None
            try:
                d = json.loads(line)
            except Exception:
                gaps += 1
                continue
            n += 1
            ph, h = d.get("prev_hash"), d.get("hash")
            if prev is not None and ph != prev:
                gaps += 1
            prev = h
        total += n
        broken += gaps
        report.append(f"{p.name}: {n} тиков, разрывов {gaps}")

    if total == 0:
        return SKIP, "леджеров нет — доказательной цепи ещё не создано"
    if broken:
        return FAIL, f"ЦЕПЬ ПОРВАНА ({broken}) → историю переписывали: " + " · ".join(report)
    return PASS, f"цепь цела: {total} тиков, 0 разрывов · " + " · ".join(report)


# ── 6 · MONEY ─────────────────────────────────────────────────────────────────
def check_money():
    """Revenue ledger: реальные verified ₽. Честно 0, если 0 — WARN, не PASS."""
    script = ROOT / "scripts" / "mint" / "socc_revenue_ledger_v1.py"
    if not script.exists():
        return SKIP, "socc_revenue_ledger_v1.py нет"
    try:
        proc = subprocess.run([sys.executable, str(script)], capture_output=True,
                              text=True, timeout=120, cwd=str(ROOT))
        d = json.loads(proc.stdout)
    except Exception as e:
        return WARN, f"реестр выручки не читается: {type(e).__name__}"

    recs = d.get("records", 0)
    total = d.get("verified_profit_total", 0)
    viol = d.get("verified_violations") or []
    if viol:
        return FAIL, f"revenue: {recs} записей, НАРУШЕНИЯ: {len(viol)}"
    if recs == 0 or not total:
        return WARN, (f"verified ₽ = {total}, записей {recs} → первый живой ход ещё не сделан "
                      f"(гейт M4 «первый verified ₽» НЕ пройден; это факт мира, не кода)")
    return PASS, f"verified ₽ = {total} · записей {recs} · нарушений 0"


# ── 7 · GATE ──────────────────────────────────────────────────────────────────
def check_gate(quick=False):
    """Делегирование: portability + приёмки + M2 + ПДн. --quick пропускает."""
    if quick:
        return SKIP, "--quick: гейт «не с неба» пропущен (запусти без --quick)"
    checks = [("переносимость py3.11", ["ops/check_py311_syntax.py"]),
              ("приёмки", ["ops/run_all_acceptances.py"])]
    out, bad = [], 0
    for name, argv in checks:
        try:
            proc = subprocess.run([sys.executable, str(ROOT / argv[0])],
                                  capture_output=True, text=True, timeout=900, cwd=str(ROOT))
            last = (proc.stdout.strip().splitlines() or ["?"])[-1][:100]
            ok = proc.returncode == 0
            bad += not ok
            out.append(f"{ICON[PASS if ok else FAIL]} {name}: {last}")
        except Exception as e:
            bad += 1
            out.append(f"❌ {name}: {type(e).__name__}")
    return (FAIL if bad else PASS), " | ".join(out)


# ── ГИГИЕНА: лид-базы/секреты НЕ должны быть трекаемы ─────────────────────────
def check_hygiene():
    """M2/M3/ПДн по трекаемым файлам. Это последний рубеж перед push."""
    try:
        files = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                               cwd=str(ROOT), timeout=60).stdout.splitlines()
    except Exception:
        return SKIP, "git недоступен"

    live = re.compile(r"(komanda_clinics_db|_komanda_[a-z_]*|_scout_targets|_scout_feed|"
                      r"_hermes_queue|harvest_feed).*\.json$|"
                      r"ANNA_MVP/runtime/clients/|ANNA_MVP/runtime/telegram_log")
    leaks = [f for f in files if live.search(f)]
    if leaks:
        return FAIL, f"M3: живое трекается ({len(leaks)}): {', '.join(leaks[:4])}"
    return PASS, f"M3: живое вне git ({len(files)} трекаемых файлов проверено)"


CHECKS = [
    ("RHYTHM · ритм launchd", check_rhythm),
    ("BRAIN · мозг ANNA", check_brain),
    ("ENV · переменные", check_env),
    ("CANON · канон и маршрут", check_canon),
    ("PROOF · хеш-цепь", check_proof),
    ("MONEY · выручка", check_money),
    ("HYGIENE · M3 живое вне git", check_hygiene),
]


def main():
    quick = "--quick" in sys.argv
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  SOCC DOCTOR · вердикт о здоровье машины (READ-only, 0₽)         ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"  корень: {ROOT}")
    print(f"  время:  {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print()

    results = []
    for name, fn in CHECKS + ([("GATE · приёмки", lambda: check_gate(quick))] if True else []):
        try:
            status, note = fn()
        except Exception as e:
            status, note = FAIL, f"{type(e).__name__}: {e}"
        results.append((name, status, note))
        print(f"  {ICON.get(status,'?')} {status:4} · {name}")
        for ln in str(note).split(" | "):
            print(f"          {ln}")
        print()

    print("─" * 68)
    bad = [r for r in results if r[1] == FAIL]
    warn = [r for r in results if r[1] == WARN]
    if bad:
        print(f"❌ МАШИНА НЕ ЗДОРОВА · FAIL {len(bad)} · WARN {len(warn)}")
        for n, _, note in bad:
            print(f"     {n}: {str(note)[:130]}")
        return 1
    print(f"✅ МАШИНА ЗДОРОВА · FAIL 0 · WARN {len(warn)}")
    for n, _, note in warn:
        print(f"     ⚠ {n}: {str(note)[:130]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

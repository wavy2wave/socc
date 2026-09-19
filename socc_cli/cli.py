#!/usr/bin/env python3
import sys
import json
import subprocess
from pathlib import Path

SOCC_ROOT = Path(__file__).parent.parent
if str(SOCC_ROOT) not in sys.path:
    sys.path.insert(0, str(SOCC_ROOT))
ROUTE = SOCC_ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"
SCRIPTS = SOCC_ROOT / "scripts/socc"

HELP = """socc — Sovereign Ontological Operating Core

USAGE:
  socc                   — observe (full status report)
  socc boot              — load core/brain + live core panel
  socc think "<request>" — understand a free-form request → know-or-ask → plan
  socc ticket "<request>" — build a lawful build TICKET (budget, plan, validators)
  socc scaffold [step]   — faithfully fill a missing validate_/review_ node (default: lawful_next)
  socc observe           — full system observe report
  socc status            — quick: lawful_next + script readiness
  socc step              — run current lawful_next script (one step)
  socc step --dry        — show what would run, no execution
  socc run               — continuous self-build loop → entity substrate gate
  socc run --max N       — limit to N ticks (default 200)
  socc run --dry         — dry run: show first step
  socc watch             — creator dashboard (live, refreshes every 3s)
  socc watch --interval N  — refresh every N seconds
  socc energy            — ЭНЕРГИЯ panel (fuel keys + resource reserve)
  socc energy add <prov> <key> [--tokens N]  — store your own key
  socc energy rm/list/test/set-tokens/set-crypto/set-fiat

SOCC · ДОМ — единый read-хаб органов (0₽):
  socc home                  — весь ДОМ (дашборд: ЯМ·OZON·SUBSTRATE·ANNA·КЕРНЕЛЬ)
  socc ym [дело|планёрка|задания|штаб|день|kpi|артефакты|авто|мозг] — ЯМ-ЦИКЛ
  socc ozon                  — OZON-менеджер (read-сводка)
  socc библиотека            — ХРАНИТЕЛЬ ДАННЫХ · системная библиотека (0₽ read)
                               полки · магазины [slug] · типы <slug> · ходы · ход PID · экспорт
                               МОЗГ БИБЛИОТЕКАРЯ (АГИ-слой, 0₽): здоровье · целостность ·
                               эволюция · сводка · вопрос «свободная фраза» (или прямо фразой)
  socc substrate             — ENTITY SUBSTRATE
  socc anna                  — ANNA · дашборд · вход
  socc kernel                — КЕРНЕЛЬ · route authority
  socc агент                 — АГЕНТ: живой экран (система работает перед тобой;
                               фразы «прогон»/«статус»/«полка»; сухо/чтение 0₽)
  CYCLE = socc home · CYCLE YM = socc ym  (тождественный алиас)
"""


def _read_route():
    try:
        data = json.loads(ROUTE.read_text(encoding="utf-8"))
        return (
            data.get("lawful_next")
            or data.get("real_next")
            or data.get("current_lawful_next")
        )
    except Exception as e:
        print(f"ERROR: cannot read route authority — {e}", file=sys.stderr)
        return None


def cmd_observe():
    observe_script = SCRIPTS / "socc_observe_v1.py"
    if not observe_script.exists():
        print(f"ERROR: observe script not found at {observe_script}", file=sys.stderr)
        sys.exit(1)
    result = subprocess.run(
        [sys.executable, str(observe_script)],
        cwd=SOCC_ROOT,
    )
    sys.exit(result.returncode)


def cmd_status():
    lawful_next = _read_route()
    script = SCRIPTS / f"{lawful_next}.py" if lawful_next else None
    script_ready = "YES" if (script and script.exists()) else "NO — script not found"

    print(f"SOCC ROOT      :: {SOCC_ROOT}")
    print(f"ROUTE FILE     :: {ROUTE.relative_to(SOCC_ROOT)}")
    print(f"LAWFUL NEXT    :: {lawful_next or 'UNKNOWN'}")
    print(f"SCRIPT READY   :: {script_ready}")
    if script and script.exists():
        print(f"SCRIPT PATH    :: {script.relative_to(SOCC_ROOT)}")
    print(f"\nRun 'socc step' to execute  |  'socc run' for continuous  |  'socc observe' for full report")


def cmd_step(dry: bool = False):
    lawful_next = _read_route()
    if not lawful_next:
        print("ERROR: lawful_next not found in route authority", file=sys.stderr)
        sys.exit(1)

    script = SCRIPTS / f"{lawful_next}.py"
    if not script.exists():
        print(f"ERROR: script not found: scripts/socc/{lawful_next}.py", file=sys.stderr)
        print("Check CURRENT_ROUTE_AUTHORITY.json — lawful_next may point to a missing script.")
        sys.exit(1)

    print(f"DISPATCHING    :: {lawful_next}")
    print(f"SCRIPT         :: {script.relative_to(SOCC_ROOT)}")

    if dry:
        print("DRY RUN        :: no execution")
        return

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=SOCC_ROOT,
    )
    sys.exit(result.returncode)


def cmd_run(max_ticks: int = 200, dry: bool = False):
    from socc_cli.runner import run
    run(max_ticks=max_ticks, dry=dry)


def cmd_watch(interval: float = 3.0):
    from socc_cli.tui import watch
    watch(interval=interval)


def cmd_boot():
    from socc_cli.brain import boot, render_boot
    print(render_boot(boot()))


def cmd_ticket(request: str):
    from socc_cli.brain import build_ticket, render_ticket
    if not request.strip():
        print("ERROR: empty request. Usage: socc ticket \"<что построить>\"", file=sys.stderr)
        sys.exit(1)
    speed = "normal"
    for s in ("turbo", "super_turbo"):
        if f"--{s}" in request:
            speed = s
            request = request.replace(f"--{s}", "").strip()
    ticket = build_ticket(request, speed=speed)
    print(render_ticket(ticket))
    sys.exit(0 if ticket.get("status") == "DRAFT" else 2)


def cmd_scaffold(arg: str):
    """Faithfully scaffold a missing self-building node script (validate_/review_)."""
    from socc_cli.brain import scaffold_step, scaffold_forward
    res = scaffold_forward() if arg in ("", "--forward") else scaffold_step(arg)
    print(f"SCAFFOLD :: {'OK' if res.get('ok') else 'REFUSED'} :: {res.get('reason')} :: {res.get('step','')}")
    if res.get("path"):
        print(f"PATH     :: {res['path']}")
    sys.exit(0 if res.get("ok") else 1)


def cmd_think(request: str):
    from socc_cli.brain import think, render_think
    if not request.strip():
        print("ERROR: empty request. Usage: socc think \"<что построить>\"", file=sys.stderr)
        sys.exit(1)
    result = think(request)
    print(render_think(request, result))
    # READY/BLOCKED exit 0 (lawful states); KNOWLEDGE_GAP exit 2 (operator action needed)
    sys.exit(2 if result.get("outcome") == "KNOWLEDGE_GAP" else 0)


_HOME_KEYS = ("home", "дом", "ym", "ям", "маркет", "cycle-ym", "ozon", "озон",
              "substrate", "entity-substrate", "sub", "субстрат", "anna", "анна",
              "kernel", "ядро", "кернель", "migrate", "migration", "миграция",
              "line-migrator",
              "задания", "zadaniya", "tasks",
              "библиотека", "хранитель", "keeper", "lib", "биб", "хран")


def cmd_home(args):
    """SOCC · ДОМ — единый read-хаб органов (0₽, чисто)."""
    from socc_cli.home import dispatch
    if args and args[0] in ("home", "дом", "hub"):
        args = args[1:]
    sys.exit(dispatch(args))


def cmd_agent(args):
    """SOCC · АГЕНТ — живой экран в духе Claude Code: система реально работает.

    Пишешь фразу → агент «думает» и по-настоящему делает (сухой прогон ЦИКЛ-1 0₽,
    ответы из реального стора). Живой ход — только с пульта по слову (RUBICON).
    """
    from socc_cli.agent import run_agent
    store, once = None, None
    i = 0
    while i < len(args):
        if args[i] in ("--store", "-s") and i + 1 < len(args):
            store = args[i + 1]
            i += 2
        elif args[i] in ("--once", "-o") and i + 1 < len(args):
            once = args[i + 1]
            i += 2
        else:
            i += 1
    sys.exit(run_agent(store=store, once=once))


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("observe", "obs"):
        cmd_observe()
    elif args[0] in _HOME_KEYS:
        cmd_home(args)
    elif args[0] == "boot":
        cmd_boot()
    elif args[0] == "think":
        cmd_think(" ".join(args[1:]))
    elif args[0] == "ticket":
        cmd_ticket(" ".join(args[1:]))
    elif args[0] == "scaffold":
        cmd_scaffold(args[1] if len(args) > 1 else "")
    elif args[0] == "status":
        cmd_status()
    elif args[0] == "recall":
        query = " ".join(args[1:]).strip()
        if not query:
            print("Usage: socc recall \"<запрос>\"", file=sys.stderr)
            sys.exit(1)
        from socc_cli.recall import run
        sys.exit(run(query))
    elif args[0] == "step":
        dry = "--dry" in args or "--dry-run" in args
        cmd_step(dry=dry)
    elif args[0] == "run":
        dry = "--dry" in args or "--dry-run" in args
        max_ticks = 200
        if "--max" in args:
            idx = args.index("--max")
            try:
                max_ticks = int(args[idx + 1])
            except (IndexError, ValueError):
                print("ERROR: --max requires a number", file=sys.stderr)
                sys.exit(1)
        cmd_run(max_ticks=max_ticks, dry=dry)
    elif args[0] == "watch":
        interval = 3.0
        if "--interval" in args:
            idx = args.index("--interval")
            try:
                interval = float(args[idx + 1])
            except (IndexError, ValueError):
                pass
        cmd_watch(interval=interval)
    elif args[0] in ("агент", "agent", "а"):
        cmd_agent(args[1:])
    elif args[0] == "energy":
        from core.energy.__main__ import main as energy_main
        sys.exit(energy_main(["energy"] + args[1:]))
    elif args[0] in ("-h", "--help", "help"):
        print(HELP)
    else:
        print(f"Unknown command: {args[0]}\n")
        print(HELP)
        sys.exit(1)


if __name__ == "__main__":
    main()

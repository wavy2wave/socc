#!/usr/bin/env python3
"""socc core — консольный доступ к Core API SOCC."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from socc_cli.socc_core import SOCC

USAGE = """socc core — единый вход в живое ядро SOCC

  socc core truth       — конфликты цели/маршрута/дохода/канона
  socc core state       — маршрут, lawful_next, флаги
  socc core memory      — wiki/graph/packs
  socc core recall "q"  — поиск по памяти
  socc core think "q"   — план с памятью
  socc core effect JSON — гейт шага (BEFORE/AFTER через stdin)
  socc core selector "q" — memory-guided выбор следующего шага
  socc core handoff     — континуити (JSON)
  socc core observe     — системный аудит
  socc core all         — state+memory+handoff одним вызовом
"""


def _pp(d):
    print(json.dumps(d, ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    argv = (argv or sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    cmd = argv[0]
    rest = argv[1:]
    s = SOCC()
    if cmd == "truth":
        _pp(s.truth())
    elif cmd == "state":
        _pp(s.state())
    elif cmd == "memory":
        _pp(s.memory())
    elif cmd == "selector":
        if not rest:
            print("Usage: socc core selector \"<запрос>\"", file=sys.stderr)
            return 1
        from socc_cli.memory_selector import memory_guided_select
        _pp(memory_guided_select(" ".join(rest)))
    elif cmd == "effect":
        if not rest or rest[0] != "-":
            print("Usage: socc core effect - < effect_step.json", file=sys.stderr)
            return 1
        try:
            import json as _json
            data = _json.loads(sys.stdin.read())
            before = data.get("before", {})
            after = data.get("after", {})
        except Exception as e:
            print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
            return 1
        result = s.effect_gate(before, after)
        _pp(result)
        return 0 if result.get("status") == "PASS" else 1
    elif cmd == "recall":
        if not rest:
            print("Usage: socc core recall \"<запрос>\"", file=sys.stderr)
            return 1
        _pp(s.recall(" ".join(rest)))
    elif cmd == "think":
        if not rest:
            print("Usage: socc core think \"<запрос>\"", file=sys.stderr)
            return 1
        _pp(s.think(" ".join(rest)))
    elif cmd == "handoff":
        _pp(s.handoff())
    elif cmd == "observe":
        r = s.observe()
        print(r["output"])
        return 0 if r["ok"] else 1
    elif cmd == "all":
        _pp({"state": s.state(), "memory": s.memory(), "handoff": s.handoff()})
    else:
        print(f"Unknown: {cmd}\n{USAGE}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

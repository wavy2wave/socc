#!/usr/bin/env python3
"""PostToolUse — после правки органа автоматически прогоняет его смоук.

Карта  подстрока-пути-правки -> команда-смоука.  Ключ, который встретился
в пути изменённого файла, определяет какой смоук гонять. Если ни один ключ
не совпал — тихо выходим (не мешаем правкам вне карты).

Дисциплина «не ломай»: хук только ДОКЛАДЫВАЕТ (additionalContext).
На красном он НЕ чинит и НЕ блокирует — поднимает флаг, решение за оператором.
"""
import json
import os
import subprocess
import sys

# путь-ключ -> (человекочитаемое имя, argv)
SMOKE_MAP = [
    ("scripts/mint/arbiter/tests/run_yandex", None),  # исключение: сам тест-файл — не гоняем
    ("scripts/mint/arbiter", ("ARBITER M1", ["python3", "scripts/mint/arbiter/tests/run_m1.py"])),
    ("scripts/mint/wave_shop", ("WAVE_SHOP", ["python3", "scripts/mint/wave_shop/tests/smoke_v1.py"])),
]


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    ti = data.get("tool_input", data) or {}
    fp = (ti.get("file_path") or "").replace("\\", "/")
    if not fp:
        sys.exit(0)

    proj = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    chosen = None
    for key, spec in SMOKE_MAP:
        if key in fp:
            chosen = spec  # первый матч побеждает; None => намеренно пропустить
            break
    if chosen is None:
        sys.exit(0)

    name, argv = chosen
    try:
        r = subprocess.run(argv, cwd=proj, capture_output=True, text=True, timeout=180)
        out = (r.stdout + r.stderr).strip().splitlines()
        tail = "\n".join(out[-4:]) if out else "(нет вывода)"
        if r.returncode == 0:
            msg = f"✅ авто-смоук {name} ЗЕЛЁНЫЙ после правки {os.path.basename(fp)}.\n{tail}"
        else:
            msg = (f"\U0001f6a8 авто-смоук {name} КРАСНЫЙ (exit {r.returncode}) после правки "
                   f"{os.path.basename(fp)}. НЕ чини вслепую — доложи оператору и разбери причину.\n{tail}")
    except subprocess.TimeoutExpired:
        msg = f"⏱ авто-смоук {name} не уложился в 180с — проверь вручную."
    except Exception as e:
        msg = f"⚠ авто-смоук {name} не запустился: {e}"

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse", "additionalContext": msg}}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)

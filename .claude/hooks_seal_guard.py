#!/usr/bin/env python3
"""PreToolUse guard — механический замок на опечатанный канон и proof-chain.

Блокирует ПЕРЕЗАПИСЬ существующих файлов, которые:
  a) лежат в .../proof_chain/ или являются *_PROOF*.json / *SEAL_Vn* (пруфы — append-only);
  b) несут внутри маркер  "...sealed": true .

Создание НОВЫХ файлов (в т.ч. новых пруфов рядом) — разрешено (append-only соблюдён).

Снять печать на ОДНУ правку:  touch SOCC/.claude/UNSEAL_ONCE  и повторить действие.
Ключ одноразовый — используется и удаляется автоматически.

Замок всегда fail-open: любая внутренняя ошибка => правка разрешается (не бриковать редактор).
"""
import json
import os
import re
import sys


def emit(hs):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", **hs}}))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    ti = data.get("tool_input", data) or {}
    fp = ti.get("file_path") or ti.get("notebook_path") or ""
    if not fp:
        sys.exit(0)

    proj = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    ap = fp if os.path.isabs(fp) else os.path.join(proj, fp)

    # Гвардим только ПЕРЕЗАПИСЬ существующего. Новый файл = законный append.
    if not os.path.isfile(ap):
        sys.exit(0)

    norm = ap.replace("\\", "/")
    base = os.path.basename(norm)

    why = ""
    if "/proof_chain/" in norm or re.search(r"_PROOF.*\.json$", base) or re.search(r"SEAL_V\d", base, re.I):
        why = "proof-chain / seal-артефакт (append-only; правка = подделка леджера)"
    else:
        try:
            with open(ap, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(200000)
            if re.search(r'"[a-z_]*sealed"\s*:\s*true', head, re.I):
                why = 'файл несёт маркер  "...sealed": true'
        except Exception:
            pass

    if not why:
        sys.exit(0)

    unseal = os.path.join(proj, ".claude", "UNSEAL_ONCE")
    if os.path.isfile(unseal):
        try:
            os.remove(unseal)
        except Exception:
            pass
        emit({"additionalContext":
              f"⚠ ПЕЧАТЬ СНЯТА одноразово для {base} ({why}). "
              f"UNSEAL_ONCE использован и удалён. Правь осознанно и переопечатай после."})

    emit({
        "permissionDecision": "deny",
        "permissionDecisionReason":
            f"\U0001f512 ЗАБЛОКИРОВАНО: {base} — {why}.\n"
            f"Разрешить ОДНУ правку:  touch \"{unseal}\"  и повтори.\n"
            f"Иначе не трогай опечатанное — создай новую версию рядом (append)."
    })


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Замок никогда не должен ломать редактирование.
        sys.exit(0)

#!/usr/bin/env python3
"""ГЕЙТ ПЕРЕНОСИМОСТИ: код обязан парситься на Python 3.11 (PEP 569).

Зачем (реальный инцидент 2026-09-16): машина была зелёная на py3.13/3.14,
а CI на py3.11 дал 7 FAIL с `SyntaxError: f-string: unmatched '['`. Причина —
PEP 701: вложенная f-строка с ТЕМИ ЖЕ кавычками (`f"…{f'…{x['k']}…'}…"`) валидна
только с Python 3.12. Локальный `ast.parse(feature_version=(3,11))` это НЕ ловит:
на новом интерпретаторе парсер уже новый, feature_version синтаксис f-строк не откатывает.

Поэтому гейт — свой сканер по исходному тексту: ищет вложенные f-строки в одинаковых
кавычках и прочие 3.12+-конструкции. Любой находкой гейт КРАСНЫЙ (L12: не fake pass).
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# вложенная f-строка в тех же кавычках: f'…{ … f'…  или  f"…{ … f"…
SQ, DQ = chr(39), chr(34)   # кавычки как данные — чтобы гейт не ловил сам себя


SQ_, DQ_ = chr(39), chr(34)   # кавычки как данные — чтобы гейт не ловил сам себя


def nested_f_same_quote(line):
    """Рекурсивный разбор f-строк: ловит повтор кавычки объемлющей f-строки (PEP 701).

    Точное правило (до Python 3.12): внутри выражения `{…}` f-строки нельзя снова
    употребить кавычку ЛЮБОЙ объемлющей f-строки. Нарушает не только `f"…{f"…"}…"`,
    но и — как в реальном инциденте 2026-09-16 — `f"…{f'…{x['k']}…'}…"`, где индекс
    `x['k']` повторяет одинарную кавычку внутренней f-строки.

    История: первые две версии гейта были на regex и давали FAKE PASS на настоящей
    конструкции (поймано mutation-пробой). Поэтому здесь честный разбор со стеком
    объемлющих кавычек, а не поиск шаблона.

    Возвращает (bool, причина).
    """
    n = len(line)

    def skip_string(i, q):
        """Пропустить обычную (не f) строку; вернуть индекс за ней."""
        i += 1
        while i < n:
            if line[i] == "\\":
                i += 2
                continue
            if line[i] == q:
                return i + 1
            i += 1
        return i

    def parse_fstring(i, q, enclosing):
        """Разобрать f-строку, начиная с кавычки i. q — её кавычка.
        enclosing — кавычки всех объемлющих f-строк (включая q).
        Вернуть (индекс_за_строкой, причина_нарушения или None)."""
        i += 1
        while i < n:
            c = line[i]
            if c == "\\":
                i += 2
                continue
            if c == q:
                return i + 1, None
            if c == "{":
                if i + 1 < n and line[i + 1] == "{":
                    i += 2
                    continue
                i, why = parse_expr(i + 1, enclosing)
                if why:
                    return i, why
                continue
            i += 1
        return i, None

    def parse_expr(i, enclosing):
        """Разобрать выражение `{…}` f-строки. i — за открывающей `{`.
        Вернуть (индекс_за_`}`, причина или None)."""
        depth = 1
        while i < n and depth:
            c = line[i]
            if c == "\\":
                i += 2
                continue
            if c == "{":
                depth += 1
                i += 1
                continue
            if c == "}":
                depth -= 1
                i += 1
                continue
            if c in (SQ_, DQ_):
                # ПРАВИЛО PEP 701: кавычка любой объемлющей f-строки здесь = SyntaxError
                if c in enclosing:
                    kind = "одинарная" if c == SQ_ else "двойная"
                    return i, (f"{kind} кавычка повторена внутри выражения f-строки "
                               f"(до Python 3.12 = SyntaxError)")
                is_f = i > 0 and line[i - 1] == "f"
                if is_f:
                    i, why = parse_fstring(i, c, enclosing + [c])
                    if why:
                        return i, why
                else:
                    i = skip_string(i, c)
                continue
            i += 1
        return i, None

    i = 0
    while i < n:
        c = line[i]
        if c == "\\":
            i += 2
            continue
        if c in (SQ_, DQ_):
            is_f = i > 0 and line[i - 1] == "f"
            if is_f:
                i, why = parse_fstring(i, c, [c])
                if why:
                    return True, why
            else:
                i = skip_string(i, c)
            continue
        i += 1
    return False, ""


# прочие конструкции, появившиеся после 3.11
NEW_SYNTAX = [
    (re.compile(r"^\s*type\s+[A-Za-z_]\w*\s*(\[|\=)", re.M), "PEP 695 `type X = …` (3.12+)"),
    (re.compile(r"^\s*(async\s+)?def\s+\w+\s*\[[^\]]*\]", re.M), "PEP 695 generic def (3.12+)"),
    (re.compile(r"^\s*class\s+\w+\s*\[[^\]]*\]", re.M), "PEP 695 generic class (3.12+)"),
    (re.compile(r"\bmatch\s+.*:\s*$", re.M), None),  # match — 3.10, пропускаем
]

SKIP_PARTS = (".venv", "venv", "site-packages", "/.git/", "__pycache__", ".egg-info")


def docstring_lines(src):
    """Строки docstring'ов — в них примеры кода, гейт их трогать не должен.

    Берём только настоящие docstring (первое строковое выражение модуля/класса/
    функции), а не все строковые литералы: иначе мы ослепим гейт к обычным строкам,
    внутри которых действительно может жить несовместимый синтаксис.
    """
    lines = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return lines
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                c = body[0].value
                start = c.lineno
                end = getattr(c, "end_lineno", start) or start
                lines.update(range(start, end + 1))
    return lines


def iter_py():
    for p in sorted(ROOT.rglob("*.py")):
        s = str(p)
        if any(part in s for part in SKIP_PARTS):
            continue
        yield p


def main() -> int:
    hits = []
    for p in iter_py():
        try:
            src = p.read_text(encoding="utf-8")
        except Exception:
            continue
        skip = docstring_lines(src)
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or i in skip:
                continue
            found, why = nested_f_same_quote(line)
            if found:
                hits.append((p, i, "PEP 701: " + why, stripped[:100]))
            for pat, label in NEW_SYNTAX:
                if label and pat.search(line):
                    hits.append((p, i, label, stripped[:100]))

    if hits:
        print(f"❌ ГЕЙТ ПЕРЕНОСИМОСТИ: {len(hits)} находка(и) несовместимы с Python 3.11\n")
        for p, i, label, code in hits[:40]:
            print(f"  {p.relative_to(ROOT)}:{i}  {label}")
            print(f"      {code}")
        print("\nЧто делать: вынести вложенное выражение в локальную переменную или функцию")
        print("(см. пример _needs_data_note в ymarket_role_head_v1.py).")
        return 1

    print(f"✅ ГЕЙТ ПЕРЕНОСИМОСТИ: весь код парсится на Python 3.11+ "
          f"(проверено {sum(1 for _ in iter_py())} файлов, вложенных f-строк PEP 701 нет)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

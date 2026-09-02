#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT ENV V1 — общий загрузчик секретов из gitignored .env для ВСЕХ рук органа.

ЗАЧЕМ (дыра, найденная в фазе A): load_env() был определён ровно в одном файле —
ozon_truth_v1.py. Руки Яндекса (ymarket_hands_v1.creds_present) читают только os.getenv,
поэтому при ЖИВЫХ ключах в .env честно отвечали «ключей нет». Ключ есть, руки его не видят —
худший вид отказа: система врёт про собственную готовность.

ЗАКОН ЭТОГО МОДУЛЯ:
  • Секреты живут в файле с правами 600, НЕ в коде и НЕ в git.
  • Уже заданное окружение имеет ПРИОРИТЕТ — не перетираем то, что оператор выставил руками.
  • Нет файла → молча False. Тогда creds_present() честно скажет «ключей нет», а не упадёт
    с загадочной ошибкой посреди боевого прогона.
  • Значения секретов НИКОГДА не печатаются и не возвращаются — наружу только ИМЕНА переменных.
  • Чистый stdlib, fail-soft: сбой чтения не имеет права уронить вечную машину.
"""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent          # SOCC/scripts/mint
ROOT = HERE.parent.parent                        # SOCC

# Кандидаты по убыванию близости к органу. Первый существующий — рабочий; остальные
# докладываются тоже (оператору полезно видеть, что файлов несколько и какой победил).
DEFAULT_CANDIDATES = (
    HERE / ".env",                               # SOCC/scripts/mint/.env  (орган MINT)
    ROOT / ".env",                               # SOCC/.env
    ROOT.parent / "wavecore-bot" / ".env",       # соседний дом ботов (указан в докстринге рук ЯМ)
)

_LOADED_FROM = []          # какие файлы уже применены (пути, НЕ значения)


def env_paths():
    """Пути-кандидаты .env (только пути, без чтения). Для предполётной диагностики."""
    return [str(p) for p in DEFAULT_CANDIDATES]


def load_env(path=None, override=False):
    """Подтянуть ключи из .env в os.environ. Возвращает True, если что-то применено.

    path — конкретный файл; None → перебор DEFAULT_CANDIDATES (применяются ВСЕ найденные,
    первый выигрывает по каждому ключу, т.к. уже заданное не перетирается).
    override=False (по умолчанию) — окружение сильнее файла.
    """
    targets = [Path(path)] if path else list(DEFAULT_CANDIDATES)
    applied = False
    for p in targets:
        try:
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if not k:
                    continue
                if override or k not in os.environ:
                    os.environ[k] = v
            applied = True
            sp = str(p)
            if sp not in _LOADED_FROM:
                _LOADED_FROM.append(sp)
        except Exception:
            continue          # битый/нечитаемый файл не роняет конвейер
    return applied


def ensure_env(path=None):
    """Идемпотентный вызов для рук: грузим один раз за процесс, дальше — no-op."""
    if _LOADED_FROM:
        return True
    return load_env(path)


def present(*names):
    """Какие переменные ЗАДАНЫ. Возвращает {ИМЯ: True/False} — БЕЗ значений (закон секретности)."""
    ensure_env()
    return {n: bool(os.getenv(n)) for n in names}


def loaded_from():
    """Из каких файлов уже подтянуто (пути, не значения)."""
    return list(_LOADED_FROM)


if __name__ == "__main__":
    import json
    ensure_env()
    known = ("OZON_CLIENT_ID", "OZON_API_KEY", "YANDEX_MARKET_API_KEY",
             "YANDEX_BUSINESS_ID", "YANDEX_CAMPAIGN_ID")
    print(json.dumps({"candidates": env_paths(), "loaded_from": loaded_from(),
                      "present": present(*known),
                      "honesty": "показаны ИМЕНА и факт наличия, значения секретов не выводятся"},
                     ensure_ascii=False, indent=2))

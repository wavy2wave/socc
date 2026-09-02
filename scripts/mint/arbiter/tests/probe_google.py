#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЗОНД Google AI Studio (Gemini native, read-only, 0₽): жив ли ключ AIza… и ВИДИТ ли он
Nano Banana (gemini-2.5-flash-image), умеющую generateContent.

НИЧЕГО не генерирует (картинку не заказывает) → расход 0₽. Это дешёвая проверка ПЕРЕД
первым живым кадром: models.list — бесплатный вызов. Ключ берётся из gitignored .env через
socc_mint_env_v1; значение НЕ печатается (только формат-префикс и найденность).

Запуск оператором, как только вставит ключ в mint/.env:
    GEMINI_API_KEY=AIza...   (или GOOGLE_API_KEY=AIza...)
    python3 tests/probe_google.py
"""
import json
import os
import ssl
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (str(HERE.parent), str(HERE.parent.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    import socc_mint_env_v1 as env   # noqa: E402
    env.ensure_env()
except Exception:
    pass

# Тот же набор имён, что читает адаптер photo_forge (порядок = приоритет).
KEY = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
       or os.getenv("GOOGLE_AI_STUDIO_KEY") or "")
BASE = (os.getenv("GEMINI_BASE_URL")
        or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
TARGET = "gemini-2.5-flash-image"

print("google-ключ найден:", bool(KEY), "· формат:", (KEY[:4] + "…") if KEY else "—",
      "· base:", BASE)
if not KEY:
    print("нет ключа: впиши GEMINI_API_KEY=AIza... в mint/.env (gitignored) и повтори")
    sys.exit(1)

CTX = ssl.create_default_context()
# Ключ передаём ЗАГОЛОВКОМ x-goog-api-key (не в url) — не течёт в логи/историю прокси.
H = {"x-goog-api-key": KEY, "User-Agent": "socc-arbiter-probe/1.0"}


def get(url):
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            return r.getcode(), r.read(4_000_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8", "ignore") if hasattr(e, "read") else "")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


st, body = get(BASE + "/models")
print(f"\nGET /models → status={st}")
if st != 200:
    print("  тело:", (body or "")[:300].replace("\n", " "))
    print("  (401/403 = ключ мёртв/не тот проект; иное = сеть/база)")
    sys.exit(1)

try:
    models = json.loads(body).get("models", [])
except Exception as e:
    print("  200, но разбор не удался:", e, body[:160])
    sys.exit(1)

names = [m.get("name", "").split("/")[-1] for m in models if isinstance(m, dict)]
by_name = {m.get("name", "").split("/")[-1]: m for m in models if isinstance(m, dict)}
img_like = sorted(n for n in names if "image" in n or "imagen" in n)

print(f"  ✅ ключ жив. моделей видно: {len(names)}")
print(f"  цель '{TARGET}' доступна:", TARGET in names)
tgt = by_name.get(TARGET)
if tgt:
    methods = tgt.get("supportedGenerationMethods") or tgt.get("supported_generation_methods") or []
    print("     supportedGenerationMethods:", methods)
    print("     generateContent умеет:", "generateContent" in methods)
print(f"  картиночные модели ({len(img_like)}):")
for n in img_like[:20]:
    print("     •", n)
if TARGET not in names:
    print("\n  ⚠ целевой слаг не найден среди доступных — возможно, имя изменилось "
          "(-preview/версия). Смотри список картиночных выше и уточни слаг в адаптере.")

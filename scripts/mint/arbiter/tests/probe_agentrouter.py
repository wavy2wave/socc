#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЗОНД agentrouter (read-only, 0₽): проверить auth ключа на OpenAI-поверхности и найти
слаг картиночной модели (Nano Banana / Gemini image). Ключ берётся из gitignored .env через
socc_mint_env; значение НИКОГДА не печатается — только факт наличия, статусы и слаги моделей.

Ничего не генерит (GET /models). Единственная сеть — к agentrouter (владельцу ключа).
"""
import json
import os
import ssl
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import socc_mint_env_v1 as env   # noqa: E402
env.ensure_env()

KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
BASE = (os.getenv("PHOTO_FORGE_BASE_URL") or "https://agentrouter.org/v1").rstrip("/")
print("ключ задан:", bool(KEY), "· base:", BASE)
if not KEY:
    print("нет ключа — нечего проверять"); sys.exit(1)

CTX = ssl.create_default_context()
IMG_HINTS = ("image", "gemini", "nano", "banana", "dall", "flux", "sd", "imagen", "stable", "qwen-image")


def get(url):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + KEY,
                                               "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
            return r.getcode(), r.read(2_000_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8", "ignore") if hasattr(e, "read") else "")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


# Кандидаты листинга моделей: OpenAI-совместимый и корневой.
for url in (BASE + "/models", "https://agentrouter.org/v1/models", "https://agentrouter.org/models"):
    status, body = get(url)
    print(f"\nGET {url}\n  status={status}")
    if status != 200:
        print("  тело:", (body or "")[:200].replace("\n", " "))
        continue
    try:
        data = json.loads(body)
        ids = [m.get("id") for m in (data.get("data") or data.get("models") or []) if isinstance(m, dict)]
        ids = [i for i in ids if i]
    except Exception as e:
        print("  не JSON:", type(e).__name__, (body or "")[:160]); continue
    print(f"  моделей всего: {len(ids)}")
    imgs = sorted({i for i in ids if any(h in i.lower() for h in IMG_HINTS)})
    print(f"  похожих на картиночные ({len(imgs)}):")
    for i in imgs:
        print("     •", i)
    if not imgs and ids:
        print("  (картиночных по эвристике нет; первые 15 моделей для ориентира:)")
        for i in sorted(ids)[:15]:
            print("     -", i)
    break

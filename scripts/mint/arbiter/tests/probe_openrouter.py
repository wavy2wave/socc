#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЗОНД OpenRouter (read-only, 0₽): проверить ключ cap_… из топлива ЭНЕРГИИ —
жив ли, есть ли баланс/лимит, и ВИДИТ ли картиночную модель google/gemini-2.5-flash-image.
Ключ берётся из core.energy.store (gitignored .env), значение НЕ печатается.
"""
import json
import os
import ssl
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve()
for _ in range(6):
    ROOT = ROOT.parent
    if (ROOT / "core" / "energy").exists():
        break
sys.path.insert(0, str(ROOT))
from core.energy import store  # noqa: E402

env = store._read_env()
KEY = ""
for name, val in env.items():
    if name.startswith("OPENROUTER_KEY") and val:
        KEY = val
        break
print("openrouter-ключ найден:", bool(KEY), "· формат:", (KEY[:4] + "…") if KEY else "—")
if not KEY:
    sys.exit(1)

CTX = ssl.create_default_context()
H = {"Authorization": "Bearer " + KEY, "User-Agent": "socc-arbiter/1.0",
     "HTTP-Referer": "https://socc.local/arbiter", "X-Title": "SOCC ARBITER"}


def get(url):
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
            return r.getcode(), r.read(3_000_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8", "ignore") if hasattr(e, "read") else "")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


# 1) жив ли ключ + баланс/лимит
st, body = get("https://openrouter.ai/api/v1/key")
print(f"\nGET /api/v1/key → status={st}")
if st == 200:
    try:
        d = json.loads(body).get("data", {})
        print("  ✅ ключ жив. лимит:", d.get("limit"), "| потрачено:", d.get("usage"),
              "| free_tier:", d.get("is_free_tier"))
    except Exception as e:
        print("  200, разбор:", e, body[:160])
else:
    print("  тело:", (body or "")[:200].replace("\n", " "))

# 2) видит ли картиночную модель
st, body = get("https://openrouter.ai/api/v1/models")
print(f"\nGET /api/v1/models → status={st}")
if st == 200:
    try:
        ids = [m.get("id") for m in json.loads(body).get("data", []) if isinstance(m, dict)]
        ids = [i for i in ids if i]
        target = "google/gemini-2.5-flash-image"
        imgs = sorted({i for i in ids if any(h in i.lower() for h in
                       ("gemini-2.5-flash-image", "nano", "dall", "flux", "imagen", "stable-diffusion"))})
        print(f"  всего моделей: {len(ids)}")
        print(f"  цель '{target}' доступна:", target in ids)
        print(f"  картиночные ({len(imgs)}):")
        for i in imgs[:20]:
            print("     •", i)
    except Exception as e:
        print("  200, разбор:", e, body[:160])
else:
    print("  тело:", (body or "")[:200].replace("\n", " "))

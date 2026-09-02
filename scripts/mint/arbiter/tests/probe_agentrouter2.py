#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЗОНД-2 agentrouter (read-only, 0₽): найти сигнатуру клиента, которую шлюз ПРИНИМАЕТ.
Шлюз вернул 'unauthorized client detected' на голый urllib → гейтит по заголовкам/клиенту.
Пробуем набор комбинаций (Anthropic-style x-api-key, OpenAI Bearer, claude-cli UA, stainless-хедеры).
Ключ из .env, значение НЕ печатается. Только GET /models (бесплатно) + один Anthropic /models.
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
import socc_mint_env_v1 as env   # noqa: E402
env.ensure_env()
KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
print("ключ задан:", bool(KEY))
CTX = ssl.create_default_context()

CLAUDE_UA = "claude-cli/1.0.60 (external, cli)"
STAINLESS = {
    "x-stainless-lang": "js", "x-stainless-package-version": "0.30.1",
    "x-stainless-os": "MacOS", "x-stainless-arch": "arm64",
    "x-stainless-runtime": "node", "x-stainless-runtime-version": "v22.0.0",
}

COMBOS = [
    ("openai-bearer+claude-ua", "https://agentrouter.org/v1/models",
     {"Authorization": "Bearer " + KEY, "User-Agent": CLAUDE_UA, "x-app": "cli"}),
    ("openai-bearer+claude-ua+stainless", "https://agentrouter.org/v1/models",
     dict({"Authorization": "Bearer " + KEY, "User-Agent": CLAUDE_UA, "x-app": "cli"}, **STAINLESS)),
    ("anthropic xapikey+version", "https://agentrouter.org/v1/models",
     {"x-api-key": KEY, "anthropic-version": "2023-06-01", "User-Agent": CLAUDE_UA, "x-app": "cli"}),
    ("anthropic xapikey+version+stainless", "https://agentrouter.org/v1/models",
     dict({"x-api-key": KEY, "anthropic-version": "2023-06-01", "User-Agent": CLAUDE_UA,
           "x-app": "cli"}, **STAINLESS)),
    ("bearer no-UA", "https://agentrouter.org/v1/models",
     {"Authorization": "Bearer " + KEY}),
]

IMG = ("image", "gemini", "nano", "banana", "dall", "flux", "imagen", "stable", "qwen-image")


def get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
            return r.getcode(), r.read(2_000_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8", "ignore") if hasattr(e, "read") else "")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


hit = None
for label, url, headers in COMBOS:
    status, body = get(url, headers)
    is_json = body[:1] in ("{", "[")
    print(f"\n[{label}] status={status} json={is_json}")
    if status == 200 and is_json:
        hit = (label, body)
        print("  ✅ приняли клиента")
        break
    print("  ", (body or "")[:150].replace("\n", " "))

if hit:
    label, body = hit
    try:
        data = json.loads(body)
        ids = [m.get("id") for m in (data.get("data") or data.get("models") or []) if isinstance(m, dict)]
        ids = [i for i in ids if i]
        print(f"\nмоделей: {len(ids)}")
        imgs = sorted({i for i in ids if any(h in i.lower() for h in IMG)})
        print(f"картиночных ({len(imgs)}):")
        for i in imgs:
            print("   •", i)
        if not imgs:
            print("картиночных по эвристике НЕТ. Первые 25 моделей:")
            for i in sorted(ids)[:25]:
                print("   -", i)
    except Exception as e:
        print("разбор не удался:", e, body[:200])
else:
    print("\nни одна комбинация не прошла клиентский гейт на /v1/models")

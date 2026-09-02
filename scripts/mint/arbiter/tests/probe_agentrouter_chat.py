#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЗОНД-чат agentrouter: доказать GPT-совместимость вживую (крошечный запрос, ~$0.001).
Стандартный OpenAI POST /v1/chat/completions к gpt-5.6-sol + рабочий клиентский UA-гейт.
Ключ из .env, значение НЕ печатается. Печатаем только статус и первые слова ответа модели.
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

KEY = os.getenv("AGENTROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY") or ""
BASE = (os.getenv("AGENTROUTER_BASE_URL") or "https://agentrouter.org/v1").rstrip("/")
print("ключ задан:", bool(KEY), "· base:", BASE)
if not KEY:
    print("нет ключа"); sys.exit(1)

CTX = ssl.create_default_context()
HEADERS = {
    "Authorization": "Bearer " + KEY,
    "User-Agent": "claude-cli/1.0.60 (external, cli)",
    "x-app": "cli",
    "Content-Type": "application/json",
}


def chat(model):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly one word: pong"}],
        "max_tokens": 5,
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(BASE + "/chat/completions", data=body, headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
            return r.getcode(), r.read(200_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8", "ignore") if hasattr(e, "read") else "")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


for model in ("gpt-5.6-sol",):
    status, body = chat(model)
    print(f"\nPOST /chat/completions model={model} → status={status}")
    if status == 200:
        try:
            d = json.loads(body)
            msg = (d.get("choices") or [{}])[0].get("message", {}).get("content")
            usage = d.get("usage") or {}
            print("  ✅ GPT-совместим. ответ модели:", repr((msg or "")[:60]))
            print("  usage:", {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")})
        except Exception as e:
            print("  200, но разбор не удался:", e, body[:160])
    else:
        print("  тело:", (body or "")[:200].replace("\n", " "))

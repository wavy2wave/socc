"""Router — turns the fuel queue into a single line of traffic.

Walks providers by priority, leases a key from the vault, sends an
OpenAI-compatible chat request. On rate-limit it cools the key and retries;
on auth/quota death it burns the key; when a provider is dry it falls through
to the next. Zero external deps (stdlib urllib only).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .providers import Provider, by_priority, REGISTRY
from .vault import Vault, FuelKey


@dataclass
class Completion:
    ok: bool
    text: str = ""
    provider: str = ""
    key_label: str = ""
    model: str = ""
    error: str = ""
    trace: list[str] = None


def _post(p: Provider, key: FuelKey, model: str, messages: list[dict],
          timeout: float) -> tuple[int, dict | str]:
    body = json.dumps({"model": model, "messages": messages}).encode()
    headers = {"Content-Type": "application/json"}
    if p.requires_key:
        headers["Authorization"] = f"Bearer {key.secret}"
    headers.update(p.extra_headers)          # client-gate UA etc.; empty for most
    req = urllib.request.Request(
        f"{p.base_url}/chat/completions",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = e.reason
        return e.code, payload
    except Exception as e:  # network / timeout
        return 0, str(e)


class Router:
    def __init__(self, vault: Vault | None = None,
                 providers: dict[str, Provider] | None = None):
        self._providers = providers or REGISTRY
        self.vault = vault or Vault(self._providers)

    def complete(self, prompt: str, *, model: str | None = None,
                 timeout: float | None = None, max_key_tries: int = 3) -> Completion:
        return self.chat([{"role": "user", "content": prompt}],
                        model=model, timeout=timeout, max_key_tries=max_key_tries)

    def chat(self, messages: list[dict], *, model: str | None = None,
             timeout: float | None = None, max_key_tries: int = 3) -> Completion:
        trace: list[str] = []

        for p in by_priority():
            if p.name not in self._providers:
                continue
            use_model = model or p.default_model
            req_timeout = timeout if timeout is not None else p.timeout
            for _ in range(max_key_tries):
                key = self.vault.issue(p.name)
                if key is None:
                    trace.append(f"{p.name}: dry")
                    break
                status, payload = _post(p, key, use_model, messages, req_timeout)

                if status == 200:
                    try:
                        text = payload["choices"][0]["message"]["content"]
                    except Exception:
                        text = json.dumps(payload)[:500]
                    trace.append(f"{p.name}/{key.label}: ok")
                    return Completion(True, text, p.name, key.label, use_model,
                                     trace=trace)

                if status == 429:                      # rate window
                    self.vault.cool(key)
                    trace.append(f"{p.name}/{key.label}: 429 cooled")
                    continue
                if status in (401, 402, 403):           # dead/quota/forbidden
                    self.vault.burn(key)
                    trace.append(f"{p.name}/{key.label}: {status} burned")
                    continue
                # transient: cool and try next key
                self.vault.cool(key)
                trace.append(f"{p.name}/{key.label}: {status} retry")

        return Completion(False, error="all providers exhausted", trace=trace)

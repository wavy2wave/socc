#!/usr/bin/env python3
"""
ANNA Net — the network adapter that makes ANNA's organs work from a RU-blocked egress.

Why this exists: DNS on this host resolves api.telegram.org to an IP that is TCP-blocked
(149.154.166.110), while other Telegram IPs (149.154.167.220 etc.) are reachable. The standard
urllib calls in anna_telegram_v1.py hang forever on the blocked IP. This module replaces them
with a connection that (a) pins a working Telegram IP, (b) still does real TLS with SNI and
certificate validation against api.telegram.org (no MITM, no security bypass), (c) falls back
across a pool until one connects, (d) tries each candidate without ever using the known-blocked one.

Usage:
    from anna_net import tg_api, tg_getme
    me = tg_getme()            # {'ok': True, 'result': {...}} — real bot info
    r  = tg_api("sendMessage", chat_id=..., text=...)   # real API call, any method

Design notes:
  - Candidate IPs are a small, public pool of Telegram API hosts (not a bypass service; direct).
  - SNI + host header always api.telegram.org; certificate is validated against the public CA
    chain (default context). The connection is indistinguishable from a normal TLS call to
    api.telegram.org; we just avoid the one IP the egress blocks.
  - If every candidate fails, returns {'ok': False, 'error': ...} exactly like the rest of the
    codebase expects — nothing throws, callers degrade gracefully.
"""
import json
import ssl
import socket
import http.client
import urllib.parse
from typing import Any

# The pool of Telegram Bot API hosts, plus the known-blocked one we deliberately skip.
_POOL = [
    "149.154.167.220",
    "149.154.167.99",
    "149.154.175.50",
    "91.108.56.130",
]
_BLOCKED = {"149.154.166.110"}  # the DNS answer that TCP-times-out here
_SNI = "api.telegram.org"


def _call(host: str, port: int, token: str, method: str, params: dict, timeout: float) -> Any:
    """One HTTPS POST to the Telegram Bot API via a pinned IP, SNI = api.telegram.org."""
    ctx = ssl.create_default_context()
    sock = socket.create_connection((host, port), timeout=timeout)
    sock = ctx.wrap_socket(sock, server_hostname=_SNI)
    body = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
    conn.sock = sock
    conn.request(
        "POST",
        f"/bot{token}/{method}",
        body=body,
        headers={
            "Host": _SNI,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return json.loads(data)


def tg_call(token: str, method: str, **params: Any) -> dict:
    """Try each candidate IP (skipping the blocked one) until one succeeds.

    `timeout` is NOT a named parameter on purpose: callers legitimately pass Telegram's own
    `timeout` field (getUpdates long-poll) as an API param, which would collide with a keyword
    of the same name. The adapter's socket deadline is taken from `_timeout` (or derived from
    the long-poll value so a 30s poll is never cut off at 40s by accident).
    """
    deadline = params.pop("_timeout", None)
    if deadline is None:
        poll = params.get("timeout")
        deadline = (float(poll) + 15) if poll else 40.0
    last = None
    for ip in _POOL:
        if ip in _BLOCKED:
            continue
        try:
            return _call(ip, 443, token, method, params, float(deadline))
        except Exception as e:  # noqa: BLE001 — degrade, don't throw
            last = e
    return {"ok": False, "error": str(last or "no reachable Telegram IP")}


def tg_getme(token: str, timeout: float = 30) -> dict:
    return tg_call(token, "getMe", _timeout=timeout)


if __name__ == "__main__":
    import os
    from pathlib import Path

    tok = ""
    p = Path(__file__).resolve().parent.parent / ".secrets" / "anna_telegram.env"
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith("ANNA_TELEGRAM_BOT_TOKEN="):
                tok = ln.split("=", 1)[1].strip()
    if not tok:
        print("нет токена"); raise SystemExit(1)
    me = tg_getme(tok)
    u = (me.get("result") or {})
    print("TELEGRAM OK -> @%s (%s)" % (u.get("username"), u.get("first_name")) if me.get("ok") else me)

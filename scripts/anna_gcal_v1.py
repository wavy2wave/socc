#!/usr/bin/env python3
"""
ANNA L2 — Google Calendar backend V1 (pluggable booking backend).

Makes "real calendar" literal: on confirmation, a real event is created in the clinic's Google Calendar,
via the same create/confirm interface as the manual backend. No heavy deps — raw urllib + a bearer access
token the CLINIC provides.

GATED: without creds → configured()=False and the booking-spine stays on the manual loop. No silent
auto-write to anyone's calendar, ever. Live-against-Google is UNVERIFIED until real creds + a real calendar
exist; payload construction (build_event) is a pure function, unit-tested offline, so the integration logic
is proven correct independent of the network (no-fake-pass).

Env:
  ANNA_GCAL_ACCESS_TOKEN   OAuth2 bearer token, scope https://www.googleapis.com/auth/calendar
  ANNA_GCAL_CALENDAR_ID    target calendar id (clinic@gmail.com or a shared calendar id)
  ANNA_GCAL_TZ             IANA tz, default Europe/Moscow
"""
import os, json, urllib.request, urllib.parse
from datetime import datetime, timedelta

API = "https://www.googleapis.com/calendar/v3"
_UA = "ANNA/1.0"


def configured():
    return bool(os.environ.get("ANNA_GCAL_ACCESS_TOKEN") and os.environ.get("ANNA_GCAL_CALENDAR_ID"))


def _tz():
    return os.environ.get("ANNA_GCAL_TZ", "Europe/Moscow")


def build_event(summary, start_iso, end_iso=None, description="", duration_min=30):
    """Construct a valid Google Calendar event body. start_iso/end_iso are RFC3339
    (e.g. '2026-07-01T19:00:00'). PURE function — unit-tested offline, no network.
    Reminders: popup 2h and 1 day before, matching how a caring admin nudges a patient."""
    ev = {"summary": summary, "description": description or "",
          "reminders": {"useDefault": False,
                        "overrides": [{"method": "popup", "minutes": 120},
                                      {"method": "popup", "minutes": 1440}]}}
    if start_iso:
        if not end_iso:
            try:
                end_iso = (datetime.fromisoformat(start_iso) + timedelta(minutes=duration_min)).isoformat()
            except Exception:
                end_iso = start_iso
        ev["start"] = {"dateTime": start_iso, "timeZone": _tz()}
        ev["end"] = {"dateTime": end_iso, "timeZone": _tz()}
    return ev


def create_event(summary, start_iso, end_iso=None, description="", duration_min=30, _post=None):
    """Create the event in the configured calendar. Returns (event_id, None) or (None, error).
    GATED behind configured(). `_post(url, data)->(id,err)` is an injectable hook for offline tests."""
    if not configured():
        return None, "gcal_not_configured"
    body = json.dumps(build_event(summary, start_iso, end_iso, description, duration_min)).encode()
    calid = os.environ["ANNA_GCAL_CALENDAR_ID"]
    url = f"{API}/calendars/{urllib.parse.quote(calid)}/events"
    if _post is not None:
        return _post(url, body)
    try:
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Authorization", "Bearer " + os.environ["ANNA_GCAL_ACCESS_TOKEN"])
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", _UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
        return d.get("id"), None
    except Exception as e:
        return None, f"gcal_create: {e}"

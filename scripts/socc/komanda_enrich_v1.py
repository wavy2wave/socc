#!/usr/bin/env python3
"""
КОМАНДА Enrich V1 — turn a clinic into a REACHABLE clinic by finding + reading its public website.

The obstacle a base source (OSM/2GIS-public) hits: it has the clinic name but not the contact.
The clinic's OWN site has it — phone, Telegram/WhatsApp/MAX/VK. Two steps, both keyless & lawful:
  find_site(name)  — a keyless web search finds the clinic's own website (skips aggregators).
  extract(html)    — validated contacts from the site (href-based; junk/invalid numbers rejected).

Reading a business's public site for its published contacts is standard lawful B2B prospecting
(no login, no personal data). A contact only counts if it validates → "доказано написать им".

enrich(clinic, place) → clinic with {contacts, channel, contact_value, reachable} filled when found.
Never throws. Best channel for the @anna_dent_bot pitch: telegram > whatsapp > max > vk > instagram > phone.
"""
import re, sys, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"

_LINK = {
    "telegram":  re.compile(r"(?://|@)?t\.me/([A-Za-z0-9_]{4,32})", re.I),
    "whatsapp":  re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|wa\.clck\.bar/)(\d{10,15})", re.I),
    "max":       re.compile(r"max\.ru/([A-Za-z0-9_]{3,32})", re.I),
    "vk":        re.compile(r"//vk\.com/([A-Za-z0-9_.]{3,40})", re.I),
    "instagram": re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,40})", re.I),
}
_TEL = re.compile(r'tel:([+0-9()\-\s]{7,})', re.I)
_VISPHONE = re.compile(r"(?:\+7|\b8)[\s\-]?\(?(\d{3})\)?[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})")
_HANDLE = re.compile(r"^[A-Za-z0-9_.]{3,32}$")
_TLD = re.compile(r"\.(ru|com|net|org|рф|su|info|me|html|php)$", re.I)
_REACH = ["telegram", "whatsapp", "max", "vk", "instagram", "phone"]
_JUNK = {"video", "audio", "id0", "share", "widget", "im", "photo", "wall",
         "public", "club", "sharer", "send", "joinchat"}
# aggregators/maps — NOT a clinic's own site (their pages are JS-gated; we want the real site)
_AGG = ("yandex.", "2gis.", "zoon.", "prodoctorov", "yell.", "google.", "youtube.", "wikipedia",
        "avito.", "flamp.", "spr.ru", "orgpage", "rusprofile", "list-org", "facebook.", "gis.ru", "otzovik")


def _valid_phone(raw):
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 11 and d[0] in "78":
        return "+7" + d[1:]
    if len(d) == 10:
        return "+7" + d
    return None


def _fetch(url, timeout=18):
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(600000).decode("utf-8", "ignore")
    except Exception:
        return ""


def find_site(name, place="", timeout=15):
    """Autonomously find a clinic's OWN website via a keyless search (best-effort; '' if none)."""
    if not name:
        return ""
    q = urllib.parse.quote(f"{name} {place} стоматология официальный сайт")
    try:
        req = urllib.request.Request(f"https://html.duckduckgo.com/html/?q={q}", headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
    except Exception:
        return ""
    for m in re.finditer(r'uddg=([^"&]+)', html):
        url = urllib.parse.unquote(m.group(1))
        if url.startswith("http") and not any(a in url.lower() for a in _AGG):
            return url
    return ""


def extract(html):
    """Return {channel: value} of REAL, validated contacts published on a page."""
    found = {}
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html or "")
    blob = " ".join(hrefs)
    for chan, rx in _LINK.items():
        m = rx.search(blob) or rx.search(html or "")
        if not m:
            continue
        v = m.group(1)
        if chan in ("instagram", "vk", "telegram", "max"):
            if v.lower() in _JUNK or _TLD.search(v) or not _HANDLE.match(v):
                continue
        found[chan] = v
    for m in _TEL.finditer(html or ""):
        p = _valid_phone(m.group(1))
        if p:
            found["phone"] = p; break
    if "phone" not in found:
        for m in _VISPHONE.finditer(html or ""):
            p = _valid_phone("".join(m.groups()))
            if p:
                found["phone"] = p; break
    return found


def enrich(clinic, place="", timeout=18):
    """Fill reachability from the clinic's own website; discover the site by name if unknown. Never throws."""
    if clinic.get("reachable") and clinic.get("channel") not in (None, "unknown", "website"):
        return clinic
    site = clinic.get("website") or (clinic.get("contacts", {}) or {}).get("website") or ""
    if not site:
        su = str(clinic.get("source_url", ""))
        if su.startswith("http") and "openstreetmap" not in su and "2gis" not in su:
            site = su
    if not site:
        site = find_site(clinic.get("name", ""), place, timeout)      # autonomous discovery
    if not site:
        return clinic
    contacts = extract(_fetch(site, timeout))
    if not contacts:
        return clinic
    merged = {**(clinic.get("contacts") or {}), **contacts}
    best = next((c for c in _REACH if c in merged), None)
    clinic["contacts"] = merged
    clinic["website"] = clinic.get("website") or site
    if best:
        clinic["channel"] = best
        clinic["contact_value"] = merged[best]
        clinic["reachable"] = True
    return clinic


def enrich_feed(feed, place="", limit_fetch=40, timeout=16):
    """Enrich up to limit_fetch clinics that aren't yet reachable (find site by name → contacts)."""
    n = 0
    for c in feed.get("clinics", []):
        if n >= limit_fetch:
            break
        if c.get("reachable") and c.get("channel") not in (None, "unknown", "website"):
            continue
        enrich(c, place or feed.get("place", ""), timeout); n += 1
    return feed


def main():
    site = sys.argv[1] if len(sys.argv) > 1 else "https://dentolub.ru"
    c = {"name": "test", "website": site, "reachable": False, "channel": "unknown"}
    enrich(c)
    print(f"{c.get('website')} → reachable={c.get('reachable')} channel={c.get('channel')} "
          f"contact={c.get('contact_value')} all={c.get('contacts')}")


if __name__ == "__main__":
    main()

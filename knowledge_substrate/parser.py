"""Deterministic (no-LLM) extractors.

Given a source file's text, extract dates, named entities, claims, recurring
patterns, intent markers and topic tags. Every hit carries the 1-based line number
so the wiki can build a `path#Lnn` anchor back to the original context.
"""

import re

# ---- Entity lexicon ----------------------------------------------------------
# canonical_name -> regex (case-insensitive, word-ish boundaries)
ENTITY_LEXICON = {
    "SOCC": r"\bSOCC\b",
    "Entity Substrate": r"\bentity[\s_/-]?substrate\b",
    "Knowledge Substrate": r"\bknowledge[\s_/-]?substrate\b",
    "ANNA": r"\b(?:ANNA|АННА|Анна)\b",
    "Hermes": r"\b(?:Hermes|Хермес|Гермес)\b",
    "Codex": r"\b(?:Codex|Кодекс)\b",
    "Memory Wave": r"\b(?:memory[\s_]?wave|MEMORY_WAVE|мемори\s?вейв)\b",
    "PI Agent": r"\bPI[\s_-]?Agent\b",
    "Autopilot": r"\b(?:autopilot|автопилот)\b",
    "Daemon": r"\b(?:daemon|демон)\b",
    "Self-construction": r"\bself[\s_-]?construction\b",
    "Proof": r"\bproof[\s_-]?(?:chain|index)?\b",
    "Wikipedia": r"\b(?:wiki(?:pedia|media)?|вики(?:педи[яю]|медиа)?)\b",
    "Supramental": r"\b(?:supramental|супраментал)\b",
    "Tamaguru": r"\b(?:Tamaguru|Тамагуру)\b",
    "Dental Clinic": r"\b(?:dental|стоматолог\w*|клиник\w*|barbershop|барбершоп)\b",
    "Administrator": r"\b(?:администратор\w*|admin\b|first[\s-]?contact|ресепшн|reception)\b",
    "Telegram": r"\b(?:telegram|телеграм\w*|\bMAX\b)\b",
    "Booking": r"\b(?:запис\w*|booking|бронир\w*|appointment)\b",
    "Persona": r"\b(?:persona|персон\w*|личност\w*|identity|характер)\b",
    "Vertical Agent": r"\b(?:вертикальн\w*\s+агент|vertical\s+agent)\b",
    "Subscription": r"\b(?:подписк\w*|subscription|тариф\w*|оплат\w*|payment)\b",
}

# ---- Dates -------------------------------------------------------------------
_RU_MONTHS = {
    "январ": "01", "феврал": "02", "март": "03", "апрел": "04", "ма": "05",
    "июн": "06", "июл": "07", "август": "08", "сентябр": "09", "октябр": "10",
    "ноябр": "11", "декабр": "12",
}
_EN_MONTHS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

_ISO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})")
_DMY = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](20\d{2})\b")
_RU = re.compile(r"\b(\d{1,2})\s+([А-Яа-я]{3,})\b")
_EN = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,})\b|\b([A-Za-z]{3,})\s+(\d{1,2})\b")

# ---- Intent markers ----------------------------------------------------------
INTENT_MARKERS = {
    "requirement": r"\b(?:должн[аоы]?|надо|нужн[оаы]|обязан|must|required|shall)\b",
    "decision": r"\b(?:решили|выбрали|договорились|decided|agreed|выбор)\b",
    "deprecation": r"\b(?:устарел[оа]?|deprecated|superseded|historical|не\s+актуальн)\b",
    "status_pass": r"\b(?:PASS|sealed|accepted|запечатан|принят)\b",
    "status_fail": r"\b(?:FAIL|blocked|провал|сломал)\b",
    "next": r"\b(?:lawful_next|next_required_step|следующий\s+шаг|далее|next\b)\b",
}

# ---- Claim verbs (a sentence with an entity + one of these is a claim) -------
_CLAIM_VERB = re.compile(
    r"\b(?:is|are|must|должн|это|=|≠|становится|prepares|turns|builds|строит|"
    r"означает|defines|определя|requires|требует|не\s+является|not\b)\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(r"(≠|\bnot\b|\bне\s|\bno\b|never|без)", re.IGNORECASE)


def _norm_date(y, m, d):
    try:
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except Exception:
        return None


def extract_dates(line):
    out = []
    for m in _ISO.finditer(line):
        out.append((m.group(0), f"{m.group(1)}-{m.group(2)}-{m.group(3)}"))
    for m in _DMY.finditer(line):
        v = _norm_date(m.group(3), m.group(2), m.group(1))
        if v:
            out.append((m.group(0), v))
    for m in _RU.finditer(line):
        day, mon = m.group(1), m.group(2).lower()
        for stem, num in _RU_MONTHS.items():
            if mon.startswith(stem):
                v = _norm_date("2026", num, day)
                if v:
                    out.append((m.group(0), v))
                break
    for m in _EN.finditer(line):
        if m.group(1) and m.group(2):
            day, mon = m.group(1), m.group(2).lower()[:3]
        elif m.group(3) and m.group(4):
            day, mon = m.group(4), m.group(3).lower()[:3]
        else:
            continue
        if mon in _EN_MONTHS:
            v = _norm_date("2026", _EN_MONTHS[mon], day)
            if v:
                out.append((m.group(0), v))
    return out


def _entities_in(line):
    found = []
    for name, pat in ENTITY_LEXICON.items():
        if re.search(pat, line, re.IGNORECASE):
            found.append(name)
    return found


def parse_text(text, topic_entities=None, topic_name="entity_substrate"):
    """Return a dict of extracted memory for one source file.

    topic_entities: optional list of canonical entity names; the file is tagged
    into `topics` with topic_name if it mentions any of them.
    """
    lines = text.split("\n")
    dates, entities, claims, intent_markers = [], [], [], []
    entity_line_index = {}

    for i, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue

        for original, value in extract_dates(line):
            dates.append({"value": value, "line": i, "raw": original})

        ents = _entities_in(line)
        for e in ents:
            entities.append({"name": e, "line": i, "context": line[:240]})
            entity_line_index.setdefault(e, []).append(i)

        # claim: line mentions >=1 entity AND a claim verb, and is sentence-like
        if ents and _CLAIM_VERB.search(line) and 12 <= len(line) <= 400:
            polarity = "negate" if _NEGATION.search(line) else "assert"
            intent = "definition"
            for kind, pat in INTENT_MARKERS.items():
                if re.search(pat, line, re.IGNORECASE):
                    intent = kind
                    break
            claims.append({
                "text": line[:400],
                "line": i,
                "entities": ents,
                "intent": intent,
                "polarity": polarity,
            })

        for kind, pat in INTENT_MARKERS.items():
            if re.search(pat, line, re.IGNORECASE):
                intent_markers.append({"marker": kind, "line": i, "context": line[:200]})

    # recurring patterns: entities seen on 3+ lines are "patterns" of this file
    patterns = [
        {"pattern": name, "lines": locs[:25], "count": len(locs)}
        for name, locs in sorted(entity_line_index.items())
        if len(locs) >= 3
    ]

    topics = []
    if topic_entities:
        te = set(topic_entities)
        mentioned = {e["name"] for e in entities}
        if te & mentioned:
            topics.append(topic_name)

    return {
        "dates": dates,
        "entities": entities,
        "claims": claims,
        "patterns": patterns,
        "intent_markers": intent_markers,
        "topics": topics,
        "entity_counts": {k: len(v) for k, v in entity_line_index.items()},
    }

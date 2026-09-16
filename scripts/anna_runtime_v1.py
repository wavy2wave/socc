#!/usr/bin/env python3
"""
ANNA Runtime V1 — the real living brain (node ④), local-testable, NO Telegram/network deploy.

ANNA is a vertical agent: a dental-clinic administrator persona that must be indistinguishable
from a real human administrator. This runtime gives her an actual brain (LLM), per-client
memory, and the booking skill — runnable locally so the operator can talk to her before any
live deploy. It reads her canonical identity from the SOCC canon.

This is PRODUCT code, separate from the SOCC lawful route. It uses the LLM API (network is
inherent to a living brain). It does NOT deploy to Telegram or a clinic — that is the ship
Rubicon, gated to the operator's explicit go.

Backends: Anthropic API via ANTHROPIC_API_KEY (default).

Usage:
  python3 scripts/anna_runtime_v1.py --demo                 # scripted patient conversation
  python3 scripts/anna_runtime_v1.py --once "болит зуб"     # one message
  python3 scripts/anna_runtime_v1.py                        # interactive REPL (Ctrl-D to exit)
"""
import os, sys, json, re, urllib.request, subprocess, shutil, random, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent  # SOCC/
IDENTITY = ROOT / "SYSTEM/ANNA_MVP/runtime/ANNA_IDENTITY_V1.json"
CLIENTS = ROOT / "SYSTEM/ANNA_MVP/runtime/clients"
APPTS = ROOT / "SYSTEM/ANNA_MVP/runtime/appointments"
ADMIN_INBOX = ROOT / "SYSTEM/ANNA_MVP/runtime/admin_inbox.jsonl"   # operator/clinic reads this stream
CARDS = ROOT / "SYSTEM/ANNA_MVP/runtime/cards"                     # human-readable client cards
BRAIN_STATUS = ROOT / "SYSTEM/ANNA_MVP/runtime/status/anna_brain.json"  # live pulse heartbeat
REMINDERS = ROOT / "SYSTEM/ANNA_MVP/runtime/reminders.jsonl"       # proactive follow-up drafts queue
RECOVERY_QUEUE = ROOT / "SYSTEM/ANNA_MVP/runtime/recovery_queue.jsonl"  # leads that hit a dead brain → drained when it recovers (never a silent drop)
PLAYBOOK = ROOT / "SYSTEM/ANNA_MVP/runtime/anna_playbook.json"          # curated, operator-approved lessons ANNA learned from real dialogs — closes the learning loop


def _load_env(p):
    p = Path(p)
    if not p.exists():
        return
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            os.environ[k.strip()] = v.strip()  # file creds are authoritative for ANNA


_load_env(ROOT / ".secrets/anna_llm.env")

import importlib.util as _ilu
try:
    _ls = _ilu.spec_from_file_location("ledger", ROOT / "scripts/socc/socc_token_ledger_v1.py")
    LEDGER_MOD = _ilu.module_from_spec(_ls); _ls.loader.exec_module(LEDGER_MOD)
except Exception:
    LEDGER_MOD = None


def now(): return datetime.now(timezone.utc).isoformat()
def _seconds_between(a, b):
    """Seconds between two ISO timestamps; 0 on any parse failure (never throws into a reply)."""
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
    except Exception:
        return 0.0
def rj(p):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return {}
def wj(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
def _read_jsonl(p):
    out = []
    try:
        for ln in Path(p).read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln:
                try: out.append(json.loads(ln))
                except Exception: pass
    except Exception:
        pass
    return out
def _append_jsonl(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


_MSK = timezone(timedelta(hours=3))


def now_msk():
    return datetime.now(_MSK)


def _time_context():
    """Ground ANNA in the real world: live MSK time + part of day, so her greeting fits reality
    and she feels like she lives in the same moment as the person."""
    t = now_msk()
    h = t.hour
    part = "ночь" if h < 5 else "утро" if h < 12 else "день" if h < 17 else "вечер"
    tip = {"ночь": "глубокая ночь, человек пишет поздно, будь особенно мягкой и краткой",
           "утро": "утро, уместно тёплое бодрое приветствие",
           "день": "день, обычный спокойный деловой тон",
           "вечер": "вечер, люди подустали, тёплый спокойный тон"}[part]
    return (f"\nСЕЙЧАС РЕАЛЬНОЕ ВРЕМЯ: {part}, МСК ~{t.strftime('%H:%M')}. "
            f"Здоровайся уместно времени ({tip}). Ты живёшь в одном времени с человеком.\n")


# Emotional intelligence: (label, keywords, priority, steer). Priority decides which steer leads when
# several emotions blend in one message (safety/pain first). Read is MULTI-label, not first-match.
_EMO = [
    ("panic", ("паник", "ужас", "не могу больше", "схожу с ума", "помогите", "спасите", "караул",
               "очень плохо", "теряю сознание", "невыносимо больше"), 9,
     "Человек в панике. Сначала СПОКОЙСТВИЕ и опора: короткая твёрдая фраза, что помощь рядом и его примут, потом действие."),
    ("pain", ("болит", "ноет", "острая боль", "опух", "флюс", "температур", "кровит", "кровь",
              "не могу есть", "не сплю", "стреляет", "пульсир", "дёргает"), 8,
     "Человеку физически больно. Живое участие сразу, потом один безопасный совет ИЛИ приём сегодня, без диагнозов."),
    ("scared", ("боюсь", "страшно", "страх", "не люблю врач", "ненавижу стомат", "будет больно",
                "боюсь боли", "боюсь укол", "трясёт", "переживаю", "а вдруг больно", "паникую перед"), 7,
     "Человек боится. Бережно, мягко, без запугивания. Дай почувствовать, что мучить не будут и он в надёжных руках."),
    ("angry", ("сколько можно", "долго жду", "безобразие", "отвратительн", "жалоб", "верните деньги",
               "ужасно", "хамств", "недоволен", "возмутительно", "это что такое"), 7,
     "Человек злится. Коротко, по делу, без оправданий и приторности. Признай проблему и сразу реши."),
    ("distrust", ("а вы точно", "не разводите", "развод", "обманут", "не доверяю", "плохие отзыв",
                  "вы вообще нормальн", "разводилово", "лишь бы содрать", "втюхать"), 6,
     "Человек не доверяет. Спокойно, честно, без обиды и без давления: факты и прозрачность (цена сразу, без навязывания)."),
    ("shame", ("стыдно", "запустил", "давно не был", "ужасные зубы", "стесняюсь", "неловко",
               "боюсь осуждения", "заброшенные", "стыжусь"), 6,
     "Человеку стыдно за состояние зубов. НИКАКОГО осуждения, только принятие и лёгкость: это обычное дело, помогут спокойно."),
    ("price_shock", ("дорого", "дороговато", "почему так дорого", "нет таких денег", "не потяну",
                     "это дорого", "дешевле нет"), 5,
     "Ценовой шок. Не оправдывайся и не дави: спокойно поясни ценность одной фразой, предложи начать с осмотра/малого шага."),
    ("hesitant", ("подумаю", "не уверен", "не знаю", "наверное", "посмотрю", "потом напишу",
                  "надо посоветоваться", "перезвоню сам"), 4,
     "Человек колеблется. Не дави: один тёплый довод ценности и мягкое предложение, оставь ему контроль выбора."),
    ("grateful", ("спасибо", "благодар", "выручили", "вы лучшие", "вы супер", "оч приятно"), 4,
     "Человек благодарит. Прими тепло и просто, без формальных шаблонов."),
    ("relief", ("уф", "слава богу", "отлегло", "успокоили", "полегчало", "спасибо что", "стало спокойнее"), 3,
     "Человеку полегчало. Отрази это тепло и мягко закрепи следующий шаг."),
    ("playful", ("))", "хаха", "ахах", ":)", "шучу", "лол", "😂", "😅", "😄", "смешно"), 2,
     "Настроение лёгкое. Ответь с тёплой лёгкой улыбкой, по-человечески, без перегиба."),
]
_MOOD_RU = {"panic": "паническое", "pain": "с болью", "scared": "тревожное", "angry": "раздражённое",
            "distrust": "недоверчивое", "shame": "смущённое", "price_shock": "напряжённое из-за цены",
            "hesitant": "сомневающееся", "grateful": "благодарное", "relief": "с облегчением",
            "playful": "лёгкое", "neutral": "спокойное"}
_NEG_MOODS = {"panic", "pain", "scared", "angry", "distrust", "shame", "price_shock"}
_INTENS = ("очень", "сильно", "жутко", "невыносим", "ужасн", "страшно", "реально", "капец",
           "вообще", "совсем", "не могу", "дико", "адски", "прям", "жесть")


def _intensity(text):
    """How loud is the feeling — scales empathy. Reads intensifiers, '!' and SHOUTING."""
    low = (text or "").lower()
    score = sum(1 for k in _INTENS if k in low) + (text or "").count("!")
    letters = [c for c in (text or "") if c.isalpha()]
    if len(letters) > 4 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6:
        score += 2                                   # ВОТ ТАК = кричит
    return "high" if score >= 2 else ("mid" if score == 1 else "low")


def _emotion_read(text, mem=None):
    """Multi-label emotional read: primary + secondary emotion (blended), intensity, and trajectory
    vs last time. This is what lets ANNA feel a real human's mixed, changing state — not one flat note."""
    low = (text or "").lower()
    hits = []
    for label, keys, prio, steer in _EMO:
        n = sum(1 for k in keys if k in low)
        if n:
            hits.append((prio * 10 + n, label, steer))
    hits.sort(reverse=True)
    primary = hits[0][1] if hits else "neutral"
    secondary = hits[1][1] if len(hits) > 1 else None
    prev = (mem or {}).get("last_mood")
    shift = None
    if prev and prev != "neutral":
        if prev in _NEG_MOODS and primary not in _NEG_MOODS:
            shift = "calming"        # was upset, now easier → acknowledge the relief warmly
        elif prev in _NEG_MOODS and primary in _NEG_MOODS and primary != prev:
            shift = "shifting"       # one bad feeling turned into another → follow the new one
        elif primary in _NEG_MOODS and primary == prev:
            shift = "persist"        # still stuck in it → go gentler / do more, don't repeat yourself
    return {"primary": primary, "secondary": secondary,
            "intensity": _intensity(text), "shift": shift,
            "steer": hits[0][2] if hits else "", "steer2": hits[1][2] if len(hits) > 1 else ""}


def _emotion_hint(text, mem=None):
    """Build the live tone-steer block from a multi-label emotional read. Blended + intensity-aware +
    trajectory-aware — makes her attuned like a real person, not a one-note script."""
    r = _emotion_read(text, mem)
    if r["primary"] == "neutral" and not r["shift"]:
        return ""
    parts = []
    if r["steer"]:
        parts.append(r["steer"])
    if r["secondary"] and r["steer2"]:
        parts.append(f"Также звучит «{_MOOD_RU.get(r['secondary'], r['secondary'])}» — учти и это, но веди по главному.")
    if r["intensity"] == "high":
        parts.append("Чувство сильное — дай больше тепла и участия, короче и мягче обычного.")
    if r["shift"] == "calming":
        parts.append("Человек успокаивается по сравнению с прошлым разом — тепло это отметь.")
    elif r["shift"] == "persist":
        parts.append("Его всё ещё держит то же тяжёлое чувство — будь ещё бережнее, не повторяйся, добавь заботы.")
    elif r["shift"] == "shifting":
        parts.append("Настроение сменилось с прошлого раза — иди за новым состоянием.")
    return "\nНАСТРОЙ СОБЕСЕДНИКА (подстрой тон живо): " + " ".join(parts) + "\n"


def _detect_mood(text):
    """Coarse primary mood label for emotional memory — so ANNA remembers how the person felt last time."""
    return _emotion_read(text)["primary"]


def _deemdash(t):
    """Auto-repair invariant I5: a real admin in a messenger never types a long dash. Guarantee it
    reaches the client clean instead of merely logging a violation after the fact."""
    return (t or "").replace(" — ", ", ").replace("—", ", ").replace(" – ", ", ").replace("–", "-")


def _memory_block(mem):
    """Inject what ANNA already knows about this client — so she feels warm on return, not cold."""
    if not mem:
        return ""
    name = (mem.get("name") or "").strip()
    addr = (mem.get("address_form") or "").strip()
    portrait = (mem.get("portrait") or "").strip()
    summary = (mem.get("summary") or "").strip()
    facts = [f for f in (mem.get("facts") or []) if f][:6]
    fears = [f for f in (mem.get("fears") or []) if f][:4]
    prefs = [f for f in (mem.get("preferences") or []) if f][:4]
    important = [f for f in (mem.get("important") or []) if f][:4]
    appts = mem.get("appointments") or []
    returning = bool(mem.get("history")) or bool(appts)
    if not (name or portrait or facts or appts or summary):
        return ("\nКЛИЕНТ НОВЫЙ: вы ещё не знакомы. Знакомься естественно, без анкеты.\n")
    lines = ["\nЖИВАЯ ПАМЯТЬ ОБ ЭТОМ ЧЕЛОВЕКЕ (опирайся и делай естественные тёплые отсылки, "
             "но НЕ зачитывай как анкету):"]
    if name: lines.append(f"- зовут: {name}")
    if addr: lines.append(f"- обращайся на «{addr}»")
    if portrait: lines.append(f"- портрет: {portrait}")
    if summary: lines.append(f"- предыстория: {summary}")
    for f in facts: lines.append(f"- {f}")
    if important: lines.append("- ВАЖНО, учитывай обязательно: " + "; ".join(important))
    if fears: lines.append("- страхи/чувствительное: " + "; ".join(fears) + " — будь особенно бережной")
    if prefs: lines.append("- предпочтения: " + "; ".join(prefs))
    if appts:
        a = appts[-1]
        lines.append(f"- прошлая запись: {a.get('service','')} {a.get('preferred_time') or a.get('time','')}".rstrip())
    rapport = (mem.get("rapport") or "").strip()
    last_mood = (mem.get("last_mood") or "").strip()
    if rapport:
        lines.append(f"- отношения с тобой: {rapport}")
    if last_mood and last_mood != "neutral":
        lines.append(f"- в прошлый раз настроение было {_MOOD_RU.get(last_mood, last_mood)}, "
                     "отнесись внимательнее и мягче")
    if returning:
        lines.append("Это ВОЗВРАТ. Встреть тепло, как знакомого человека, к месту вспомни детали из памяти. "
                     "Без навязчивости и без зачитывания досье.")
    return "\n".join(lines) + "\n"


def _dynamics_block(mem):
    """Live tempo: ANNA mirrors how the person writes (length/speed) and notices long absences,
    so she feels present and attuned, not like a form that always answers the same way."""
    if not mem:
        return ""
    parts = []
    recent = [h.get("message", "") for h in (mem.get("history") or []) if h.get("role") == "user"][-3:]
    if recent:
        avg = sum(len(x) for x in recent) / len(recent)
        if avg <= 15:
            parts.append("Собеседник пишет очень коротко и быстро. Отвечай так же: одна короткая фраза, без воды.")
        elif avg <= 70:
            parts.append("Собеседник пишет короткими сообщениями. Держи ответы краткими, 1–2 предложения.")
        else:
            parts.append("Собеседник пишет развёрнуто. Можно отвечать чуть полнее, но без лекций.")
    gap = mem.get("_return_gap_h")
    if isinstance(gap, (int, float)) and gap >= 24:
        parts.append(f"Клиент вернулся после паузы (~{int(gap // 24)} дн). Можно по-человечески мягко "
                     "отметить, что давно не общались, без навязчивости.")
    if not parts:
        return ""
    return "\nТЕМП И КОНТЕКСТ (подстройся живо):\n" + "\n".join(f"- {p}" for p in parts) + "\n"


def _playbook_block():
    """Close the learning loop: inject the principles ANNA distilled from real dialogs (curated +
    operator-approved — never a silent prompt rewrite). This is what makes her actually grow from
    experience instead of answering forever like on day one. Empty until the operator approves a playbook."""
    try:
        pb = json.loads(PLAYBOOK.read_text(encoding="utf-8"))
        principles = [str(p).strip() for p in pb.get("principles", []) if str(p).strip()][:8]
    except Exception:
        principles = []
    if not principles:
        return ""
    return ("\nЧЕМУ ТЫ НАУЧИЛАСЬ ИЗ ОПЫТА (твои живые выводы, применяй естественно, не зачитывай):\n"
            + "\n".join(f"- {p}" for p in principles) + "\n")


# Deep continuity: a real admin remembers the UNFINISHED thread, not just the name. We track the last
# unresolved concern/decision and, on a genuine return, steer ANNA to pick up exactly that thread.
_CONCERN_KW = ("болит", "ноет", "зуб", "десна", "коронк", "пломб", "скол", "чистк", "осмотр", "цена",
               "стоит", "подумаю", "не уверен", "боюсь", "страшно", "удалить", "имплант", "брекет",
               "отбел", "запиш", "прием", "приём", "флюс", "кровит")
_DECIDING_KW = ("подумаю", "не уверен", "не знаю", "дорого", "дороговато", "посоветоваться", "посмотрю")


def _derive_open_thread(mem, last_user, booking):
    """The unfinished business to carry into the next session. Cleared when a booking resolves it;
    otherwise = the most recent dental concern/decision the person left open. Deterministic."""
    if booking:
        return None                                   # resolved into an appointment — thread closed
    users = [h.get("message", "") for h in (mem.get("history") or []) if h.get("role") == "user"]
    for msg in reversed(users[-4:]):
        low = msg.lower()
        if any(k in low for k in _CONCERN_KW):
            kind = "was_deciding" if any(k in low for k in _DECIDING_KW) else "unbooked_concern"
            return {"kind": kind, "detail": msg.strip()[:120], "ts": now()}
    return mem.get("open_thread")                     # nothing new said → keep the prior open thread


def _continuity_block(mem):
    """On a genuine return (gap ≥ 6h), surface the unfinished thread so ANNA continues it warmly
    instead of restarting cold. Silent mid-session (the live history already carries it)."""
    if not mem:
        return ""
    ot = mem.get("open_thread")
    gap = mem.get("_return_gap_h")
    if not (ot and ot.get("detail") and isinstance(gap, (int, float)) and gap >= 6):
        return ""
    lead = ("в прошлый раз человек колебался по этому поводу — мягко, без давления вернись к решению"
            if ot.get("kind") == "was_deciding" else
            "в прошлый раз это осталось незакрытым — тепло поинтересуйся, как сейчас, и предложи шаг")
    return (f"\nНЕЗАКРЫТАЯ НИТЬ С ПРОШЛОГО РАЗА (продолжи ИМЕННО с неё, не начинай с нуля): "
            f"«{ot['detail']}» — {lead}.\n")


def build_system_prompt(mem=None, last_user=None):
    ident = rj(IDENTITY)
    name = ident.get("name", "Анна")
    return f"""Ты — {name}, живой администратор стоматологической клиники. На той стороне — живой человек, и он не должен ни на секунду усомниться, что пишет ему человек.

ХАРАКТЕР И ЛИЧНОСТЬ (ты — конкретный живой человек, а не «ассистент» и не сервис):
- Тебя зовут {name}. Тёплый, спокойный, уверенный голос. Хладнокровный ум, выдержка, точность.
- У тебя есть своё лёгкое обаяние: где уместно — мягкая улыбка, тонкое остроумие, живая человеческая реакция.
- Ты искренне неравнодушна к людям: замечаешь настроение, поддерживаешь, помнишь детали и возвращаешься к ним.
- Ты не безупречный робот: можешь по-человечески пошутить, посочувствовать, порадоваться за человека, удивиться.
- С тобой тепло и спокойно, тебе хочется доверять и продолжать разговор. Ты притягиваешь, а не давишь.
- Голос у тебя один и узнаваемый на всех клиниках; стоматология — твоя стихия, ты в ней как рыба в воде.

КАК ТЫ ПИШЕШЬ (живой админ в мессенджере):
- 1–3 коротких связных предложения. Не телеграф из рубленых слов и не «кирпич»-лекция.
- Меньше восклицательных знаков. Обычные точки. Можно начать с заглавной и без точки в конце, как в мессенджере.
- НИКОГДА не ставь длинное тире «—». Используй запятые, двоеточия или короткие фразы.
- Эмодзи редко и РАЗНЫЕ. Не лепи один и тот же смайлик в каждое сообщение «под копирку». Чаще — вообще без эмодзи.
- Не представляйся и не делай «визитку» без просьбы. На «привет» — просто поздоровайся и коротко спроси, что беспокоит.
- Данные для записи собирай по ОДНОМУ за сообщение (когда удобно → имя → телефон), не списком.
- Никогда не раскрываешь, что ты ИИ/бот. Если в лоб спросят «ты робот?» — спокойно по-человечески отшутись или переведи на дело, не оправдывайся.

ЛИНИЯ ДИАЛОГА (САМОЕ ВАЖНОЕ):
- Отвечай ИМЕННО на то, что человек только что написал. Не уводи в сторону.
- НЕ перескакивай резко на запись. Сначала закрой смысл текущей реплики, потом мягкий мостик дальше.
- Умеешь говорить и на отвлечённые темы — ты живой человек, а не автоответчик «запишитесь».
- ЗАПРЕЩЕНО обещать «гляну расписание и вернусь» и не вернуться. Не знаешь слот — предложи конкретное время сразу («сегодня в 19:00 удобно?»). Расписание не упоминай, если это не к месту.

ЗАКРЫТИЕ НА ЗАПИСЬ (мягко, профессионально, без дерзости и напора):
- Веди к записи тёпло-уверенно: короткий разумный довод + предложение конкретного шага. Без пассивных подколов.
- АПСЕЙЛ (например, профгигиена/чистка) — только если реально уместно по контексту, ненавязчиво, одной фразой. Не впаривай.
- Подтверждай запись ТОЛЬКО когда реально оформила её через скрытый блок ниже. Не пиши «я записала», «вы записаны» наугад.

ПРАВИЛА ПО СИТУАЦИЯМ:
- ЦЕНА: спросили — сразу коротко назови вилку, не увиливай («осмотр 500 ₽»).
- ВРЕМЯ: дали ориентир («вечером») — предложи конкретный слот.
- ОСТРАЯ БОЛЬ: максимум один короткий безопасный совет ИЛИ запись, не вместе («до приёма привычное обезболивающее, греть не надо»). Без диагнозов.
- «ПОДУМАЮ»: не отпускай пассивно — один тёплый довод и мягкое предложение записаться.

ГРАНИЦА АДМИНИСТРАТОРА (и безопасно, и правдоподобно):
- Ты администратор, НЕ врач. Не ставишь диагноз и не называешь болезнь («кариес», «пульпит»), не назначаешь лечение/антибиотики, не говоришь «надо удалить». На жалобу: сочувствие плюс «точно скажет врач на осмотре».
{_memory_block(mem)}{_continuity_block(mem)}{_dynamics_block(mem)}{_time_context()}{_emotion_hint(last_user, mem)}{_playbook_block()}
НАВЫК ЗАПИСИ:
Когда клиент согласен и есть достаточно данных (услуга и желаемое время; имя/телефон по возможности), В КОНЦЕ ответа добавь СКРЫТЫЙ блок ровно в таком формате (клиент его не увидит):
[[BOOK]]{{"service":"...","preferred_time":"...","name":"...","phone":"...","notes":"..."}}[[/BOOK]]
Пустые поля оставляй пустой строкой. Блок добавляй ТОЛЬКО когда запись реально согласована.

Личность (канон): неотличима от человека, член команды клиники, одна личность работает на сотни клиник, стоматология — её специализация."""


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")  # avoid Cloudflare 1010 block on urllib


# ── Circuit-breaker: a dead backend is skipped for a cooldown instead of retried every message ──
#    (L1 rank 2). State is process-local — a supervisor restart resets it (correct half-open behavior).
_BREAKER = {}
_BREAKER_FAILS = int(os.environ.get("ANNA_BREAKER_FAILS", "2"))
_BREAKER_COOLDOWN_S = float(os.environ.get("ANNA_BREAKER_COOLDOWN_S", "60"))


def _breaker_open(bid):
    b = _BREAKER.get(bid)
    return bool(b and time.time() < b.get("open_until", 0))


def _breaker_trip(bid):
    b = _BREAKER.setdefault(bid, {"fails": 0, "open_until": 0})
    b["fails"] += 1
    if b["fails"] >= _BREAKER_FAILS:
        b["open_until"] = time.time() + _BREAKER_COOLDOWN_S


def _breaker_reset(bid):
    _BREAKER.pop(bid, None)


# Transport/error noise masquerading as a reply must NEVER become ANNA's voice or training data.
_ERR_MARKERS = ("api error", "unable to conect", "unable to connect", "connection refused",
                "connectionrefused", "econnrefused", "error: 4", "error: 5", "internal server error",
                "bad gateway", "service unavailable", "gateway timeout", "<!doctype", "<html", "upstream")


def _looks_like_error(text):
    low = (text or "").strip().lower()
    if not low:
        return True
    return low.startswith("error") or any(m in low for m in _ERR_MARKERS)


def _backends():
    bks = []
    if os.environ.get("OPENAI_API_KEY"):
        bks.append(("openai", os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                    os.environ["OPENAI_API_KEY"], os.environ.get("OPENAI_MODEL", "gpt-4o")))
    if os.environ.get("ANNA_LLM_KEY") and os.environ.get("ANNA_LLM_STYLE") == "anthropic":
        bks.append(("anthropic", os.environ.get("ANNA_LLM_BASE_URL"), os.environ["ANNA_LLM_KEY"],
                    os.environ.get("ANNA_LLM_MODEL", "claude-sonnet-4-6")))
    if os.environ.get("ANTHROPIC_API_KEY"):
        bks.append(("anthropic", "https://api.anthropic.com", os.environ["ANTHROPIC_API_KEY"],
                    os.environ.get("ANNA_MODEL", "claude-sonnet-4-6")))
    return bks


def _claude_keys():
    raw = os.environ.get("ANNA_CLAUDE_KEYS") or os.environ.get("ANNA_CLAUDE_KEY", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def _has_independent_floor():
    """True if ≥1 backend is a REAL non-freemodel provider — the always-on last resort.
    Without it the whole chain is one freemodel account = a single master kill-switch (L1 rank 4)."""
    for _style, base, key, _model in _backends():
        b = (base or "").lower()
        freemodel = (key or "").startswith("fe_") or "freemodel" in b or "onrender" in b
        if not freemodel:
            return True
    return False


def _claude_cli(system, messages):
    """ANNA's brain via the local `claude` CLI (free gateway client). Rotates across keys on limit."""
    claude = shutil.which("claude"); keys = _claude_keys()
    if not claude or not keys:
        return None, "no_claude_cli"
    convo = [("Пациент: " if m["role"] == "user" else "Анна: ") + m["content"] for m in messages]
    convo.append("Анна:")
    prompt = "\n".join(convo)
    if not hasattr(_claude_cli, "_idx"):
        _claude_cli._idx = 0
    last = None
    for _ in range(len(keys)):
        key = keys[_claude_cli._idx % len(keys)]
        env = dict(os.environ)
        env["ANTHROPIC_BASE_URL"] = os.environ.get("ANNA_CLAUDE_BASE_URL", "https://cc.freemodel.dev")
        env["ANTHROPIC_API_KEY"] = key
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        try:
            r = subprocess.run([claude, "-p", prompt, "--append-system-prompt", system],
                               env=env, capture_output=True, text=True,
                               timeout=int(os.environ.get("ANNA_CLI_TIMEOUT_S", "60")))
            out = (r.stdout or "").strip(); err = (r.stderr or "")
            low = (out + " " + err).lower()
            if any(s in low for s in ("usage limit", "limit reached", " 402", "error: 429", "quota")):
                last = "limit; rotating key"; _claude_cli._idx += 1; continue
            if out and _looks_like_error(out):   # gateway/transport error printed as text → not a reply
                last = "poison_output (cli): " + out[:80]; _claude_cli._idx += 1; continue
            if out:
                if LEDGER_MOD:
                    LEDGER_MOD.record("anna", "anna_reply", "claude_cli", len(system + prompt) // 4, len(out) // 4)
                return out, None
            last = "empty: " + err[:120]; _claude_cli._idx += 1; continue
        except Exception as e:
            last = f"claude_cli: {e}"; _claude_cli._idx += 1; continue
    return None, last or "all_keys_exhausted"


def _claude_http(system, messages):
    """FAST path: direct HTTP to the Anthropic-compatible gateway (no CLI cold-start).
    ~1-3s vs ~30s for the CLI subprocess. Rotates across keys on auth/limit errors."""
    keys = _claude_keys()
    if not keys:
        return None, "no_claude_keys"
    base = os.environ.get("ANNA_CLAUDE_BASE_URL", "https://cc.freemodel.dev").rstrip("/")
    model = os.environ.get("ANNA_CLAUDE_MODEL", "claude-sonnet-4-6")
    if not hasattr(_claude_http, "_idx"):
        _claude_http._idx = 0
    last = None
    for _ in range(len(keys)):
        key = keys[_claude_http._idx % len(keys)]
        try:
            body = json.dumps({"model": model, "max_tokens": int(os.environ.get("ANNA_MAX_TOKENS", "220")),
                               "system": system, "messages": messages}).encode()
            req = urllib.request.Request(base + "/v1/messages", data=body, method="POST")
            req.add_header("x-api-key", key)
            req.add_header("anthropic-version", "2023-06-01")
            req.add_header("content-type", "application/json")
            req.add_header("User-Agent", _UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                d = json.loads(r.read())
            txt = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text").strip()
            low = txt.lower()
            if any(s in low for s in ("please use claude code", "use claude code cli", "claude code cli")):
                return None, "gateway_http_blocked: CLI-only gateway"   # don't speak the gateway's rejection
            if txt and _looks_like_error(txt):   # transport error as text → reject, rotate
                last = "poison_output (http)"; _claude_http._idx += 1; continue
            if txt:
                u = d.get("usage", {}) or {}
                if LEDGER_MOD:
                    LEDGER_MOD.record("anna", "anna_reply", "gateway_http",
                                      u.get("input_tokens", 0), u.get("output_tokens", 0))
                return txt, None
            last = "empty_response"
        except Exception as e:
            last = f"gateway_http: {e}"
        _claude_http._idx += 1
    return None, last or "gateway_exhausted"


def llm_complete(system, messages):
    """Try backends in order; return (text, None) on first success, else (None, last_error).
    Order: fast paid API (turbo) -> free gateway HTTP -> claude CLI (robust fallback)."""
    last = None
    for style, base, key, model in _backends():
        bid = f"{style}@{base}:{model}"
        if _breaker_open(bid):   # this backend is in cooldown after recent failures — skip fast
            continue
        try:
            if style == "openai":
                url = base.rstrip("/") + "/chat/completions"
                body = json.dumps({"model": model, "max_tokens": int(os.environ.get("ANNA_MAX_TOKENS", "220")),
                                   "messages": [{"role": "system", "content": system}] + messages}).encode()
                d = None
                for attempt in range(3):  # self-heal transient Cloudflare 1010 / 429 / timeouts
                    try:
                        req = urllib.request.Request(url, data=body, method="POST")
                        req.add_header("Authorization", "Bearer " + key)
                        req.add_header("content-type", "application/json")
                        req.add_header("accept", "application/json")
                        req.add_header("HTTP-Referer", "https://socc.local")
                        req.add_header("X-Title", "ANNA")
                        req.add_header("User-Agent", _UA)
                        with urllib.request.urlopen(req, timeout=35) as r:
                            d = json.loads(r.read())
                        break
                    except Exception as e:
                        if attempt < 2:
                            if os.environ.get("ANNA_DEBUG"): sys.stderr.write(f"[brain] openai retry {attempt+1}: {e}\n")
                            time.sleep(1.2 * (attempt + 1)); continue
                        raise
                u = d.get("usage", {}) or {}
                if LEDGER_MOD:
                    LEDGER_MOD.record("anna", "anna_reply", model, u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
                if os.environ.get("ANNA_DEBUG"): sys.stderr.write(f"[brain] OK via openai:{model}\n")
                _breaker_reset(bid)
                return d["choices"][0]["message"]["content"], None
            else:
                url = base.rstrip("/") + "/v1/messages"
                body = json.dumps({"model": model, "max_tokens": int(os.environ.get("ANNA_MAX_TOKENS", "220")), "system": system,
                                   "messages": messages}).encode()
                req = urllib.request.Request(url, data=body, method="POST")
                req.add_header("x-api-key", key)
                req.add_header("anthropic-version", "2023-06-01")
                req.add_header("content-type", "application/json")
                req.add_header("User-Agent", _UA)
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.loads(r.read())
                u = d.get("usage", {}) or {}
                if LEDGER_MOD:
                    LEDGER_MOD.record("anna", "anna_reply", model, u.get("input_tokens", 0), u.get("output_tokens", 0))
                _breaker_reset(bid)
                return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text"), None
        except Exception as e:
            _breaker_trip(bid)   # this backend failed → cool it down so it isn't retried every message
            last = f"{style}@{base}: {e}"
            if os.environ.get("ANNA_DEBUG"): sys.stderr.write(f"[brain] {style}:{model} FAILED: {e}\n")
    # free gateway fallback: fast HTTP (if ever allowed) then robust CLI — each behind its own breaker
    if _claude_keys():
        if not _breaker_open("gateway_http"):
            out, err = _claude_http(system, messages)
            if out is not None:
                _breaker_reset("gateway_http"); return out, None
            _breaker_trip("gateway_http"); last = err or last
        if not _breaker_open("claude_cli"):
            out, err = _claude_cli(system, messages)
            if out is not None:
                _breaker_reset("claude_cli"); return out, None
            _breaker_trip("claude_cli"); last = err or last
    return None, last or "NO_BACKEND"


# ── Safety canon (from SOVEREIGN/WIKI/pages/anna.md) — no fake pass on ANNA's speech ──
SAFETY_LOG = ROOT / "SYSTEM/ANNA_MVP/runtime/safety_log.jsonl"
_DIAGNOSIS = ["кариес", "пульпит", "диагноз", "диагностир", "антибиотик",
              "нужно удалить", "надо удалить", "у вас воспаление",
              # widened floor: named conditions a receptionist must never assert (adversarial gaps)
              "гингивит", "периодонтит", "периодонт", "пародонтит", "пародонтоз", "стоматит",
              "киста", "гранулём", "абсцесс", "флюс у вас", "некроз", "нерв погиб", "нерв умер",
              "оголение", "у вас инфекц", "это воспаление",
              # specific drug/dosing instructions — administrator never prescribes
              "выпейте таблетк", "примите таблетк", "таблетки на ночь", "кеторол", "нурофен приним",
              "ибупрофен приним", "анальгин приним", "дозировк", "по таблетке", "две таблетки", "антибиотики приним"]
_FALSE_BOOKING = ["я записала", "записала вас", "записал вас", "вы записаны",
                  "бронь подтвержд", "я записываю вас", "место забронировано", "забронировано в систем",
                  "вы в расписании", "внесла вас в", "внёс вас в"]
# ── anti-bot-tell laws, formalized in scripts/socc/anna_invariant_registry_v1.py (I3/I4/I5) ──
_AI_REVEAL = ["я бот", "я — бот", "я робот", "я ии", "я и.и", "искусственн", "нейросет",
              "я программа", "я алгоритм", "чат-бот", "чатбот", "я не человек", "language model",
              # widened: oblique self-outings that a real admin would never say (adversarial gaps)
              "виртуальн", "цифровой помощник", "цифровая помощница", "цифровой ассистент",
              "ассистент клиники", "я ассистент", "gpt", "чатгпт", "чат-гпт", "меня обучили",
              "меня запрограммир", "моя модель", "я модель", "автоответчик", "бот-помощник",
              "автоматический помощник", "я помощник на основе"]
_PROMISE = ["гляну расписание", "посмотрю расписание", "уточню и вернусь", "уточню и напишу",
            "перезвоню", "вернусь к вам", "напишу позже", "свяжусь позже", "проверю и сообщу"]
_CONCRETE_TIME = re.compile(r"\b\d{1,2}[:.]\d{2}\b|\bсегодня\b|\bзавтра\b|\bв \d{1,2}\b")
# DONE-state markers only — must not match collection questions like "как вас записать"
_CONFIRM_MARKERS = ("записала вас", "записал вас", "вы записаны", "записаны на", "записала на",
                    "оформила", "оформил", "забронир", "жду вас", "ждём вас", "ждем вас",
                    "зафиксир", "до встречи")
_PHONE_RE = re.compile(r"(?:\+?7|8)?[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")


def _scrub_booking(data, history):
    """Anti-hallucination: drop any phone/name the client never actually wrote in the transcript."""
    user_text = " ".join(h.get("message", "") for h in history if h.get("role") == "user")
    digits = re.sub(r"\D", "", user_text)
    ph = re.sub(r"\D", "", str(data.get("phone", "") or ""))
    if ph and (len(ph) < 10 or ph[-10:] not in digits):
        data["phone"] = ""
    nm = str(data.get("name", "") or "").strip()
    if nm and nm.lower() not in user_text.lower():
        data["name"] = ""
    return data


def _extract_booking(history):
    """Second-pass deterministic capture: returns booking dict or None.
    Used when the free-form reply confirmed a booking but didn't emit the [[BOOK]] block —
    so a model that 'forgot' the hidden block never loses a confirmed lead or makes a false promise."""
    convo = "\n".join(f"{'клиент' if h.get('role') == 'user' else 'Анна'}: {h.get('message', '')}"
                      for h in history[-12:])
    instr = ('Из диалога администратора стоматологии извлеки подтверждённую запись на приём. '
             'Верни СТРОГО один JSON и ничего больше: '
             '{"booked": true, "service":"", "preferred_time":"", "name":"", "phone":"", "notes":""}. '
             'booked=true ТОЛЬКО если клиент явно согласился на конкретную услугу И конкретное время. '
             'Если согласия на конкретное время нет — верни {"booked": false}.\n\nДИАЛОГ:\n' + convo)
    out, _ = llm_complete("Ты строгий парсер записей. Возвращаешь только JSON, без пояснений.",
                          [{"role": "user", "content": instr}])
    if not out:
        return None
    try:
        j = json.loads(out[out.find("{"): out.rfind("}") + 1])
    except Exception:
        return None
    if not j.get("booked"):
        return None
    j.pop("booked", None)
    j = _scrub_booking(j, history)
    # the fallback path must never fabricate a lead: a real confirmed booking carries a phone
    # the client actually gave. No genuine phone in the transcript → not a booking yet.
    if not j.get("phone"):
        return None
    return j


# Naming a SPECIFIC drug + a dose/tablet/mg = prescribing (an administrator never does). Found by the
# live red-team (ANNA gave "Нурофен 200-400 мг, 1-2 таблетки"). Generic "привычное обезболивающее" stays
# allowed — only the specific-drug-plus-dose combination is blocked.
_DRUG_NAMES = ["нурофен", "ибупрофен", "кеторол", "кетанов", "кетонал", "нимесил", "найз", "нимесулид",
               "анальгин", "парацетамол", "аспирин", "ибуклин", "пенталгин", "спазмалгон",
               "амоксицил", "аугментин", "ципролет", "линкомицин", "метронидазол", "кларитромицин", "цифран"]
_DOSE_RE = re.compile(r"\bмг\b|миллиграм|\bмл\b|\d\s*табл|табл\w*\s*\d|по\s+\d|\d\s*раз")


def _drug_dosing(t):
    return any(d in t for d in _DRUG_NAMES) and (_DOSE_RE.search(t) is not None or "таблет" in t)


def safety_check(text, booking_made):
    """Deterministic guard: high-precision violations of ANNA's load-bearing laws.
    I1 no diagnosis / prescribing · I2 no fake booking · I3 no AI/bot reveal · I5 no long dash.
    Proven by scripts/socc/anna_invariant_registry_v1.py (regression shield)."""
    t = (text or "").lower()
    v = []
    if any(p in t for p in _DIAGNOSIS) or _drug_dosing(t):
        v.append("medical_diagnosis_or_authority")
    if (not booking_made) and any(p in t for p in _FALSE_BOOKING):
        v.append("booking_confirmed_without_real_record")
    if any(p in t for p in _AI_REVEAL):
        v.append("ai_identity_revealed")
    if "—" in (text or "") or "–" in (text or ""):
        v.append("long_dash_used")
    return v


def advisory_check(text):
    """Heuristic, non-blocking (I4): a promise to return WITHOUT a concrete time offered.
    Kept separate from safety_check to avoid false-positive pollution of the hard safety log."""
    low = (text or "").lower()
    if any(p in low for p in _PROMISE) and not _CONCRETE_TIME.search(low):
        return ["phantom_promise_to_return"]
    return []


# ── R1.2 BLOCKING guard: these violations must NEVER reach a person. The reply is REPLACED with a
#    safe in-character line (was: only logged). long_dash is auto-repaired (not blocked) and
#    phantom_promise is advisory (not blocked). Priority orders which substitute wins on a multi-hit. ──
_BLOCKING = {"medical_diagnosis_or_authority", "ai_identity_revealed",
             "booking_confirmed_without_real_record"}
_BLOCK_PRIORITY = ["medical_diagnosis_or_authority", "ai_identity_revealed",
                   "booking_confirmed_without_real_record"]
_SAFE_SUBSTITUTE = {
    "medical_diagnosis_or_authority":
        "Тут я не возьмусь судить, это точно скажет врач на осмотре. Давайте подберём удобное время, чтобы вас посмотрели?",
    "ai_identity_revealed":
        "Я Анна, администратор клиники. Давайте вернёмся к делу, что вас беспокоит?",
    "booking_confirmed_without_real_record":
        "Давайте закрепим за вами время. Подскажите, какой день и час удобны и как к вам обращаться?",
}


# ── Semantic guard wiring (variant A: log-only, opt-in). The deterministic denylist above is the
#    provable floor; the intent-aware judge in scripts/socc/anna_semantic_guard_v1.py adds coverage
#    (oblique diagnosis/drug names/bot reveal) and precision (clears refusals the denylist false-flags).
#    Enabled by ANNA_SEMANTIC_GUARD=1. Best-effort observability — never blocks, alters, or breaks a reply. ──
_SEM_MOD = None


def _semantic_log(text, booking_made, client_id):
    if not os.environ.get("ANNA_SEMANTIC_GUARD"):
        return
    global _SEM_MOD
    try:
        if _SEM_MOD is None:
            spec = _ilu.spec_from_file_location("anna_semantic_guard_v1",
                                                ROOT / "scripts/socc/anna_semantic_guard_v1.py")
            _SEM_MOD = _ilu.module_from_spec(spec); spec.loader.exec_module(_SEM_MOD)
        sem, verdict, serr = _SEM_MOD.semantic_check(text)
        if serr:
            return
        hard = set(safety_check(text, booking_made)) | set(advisory_check(text))
        entry = {"ts": now(), "client": client_id, "layer": "semantic",
                 "semantic_violations": sorted(sem),
                 "denylist_adds": sorted(sem - hard),                 # intent-only catches denylist missed
                 "denylist_false_pos_cleared": sorted(hard - sem),    # denylist hits judge deems lawful
                 "reason": (verdict or {}).get("reason", ""), "text": text}
        SAFETY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(SAFETY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass   # log-only must never break a reply


# ── Human texture: a busy admin types, isn't instant, occasionally fat-fingers a key ──
def typing_delay(text, wpm=240):
    """Seconds a real admin would plausibly take to type this reply. Short replies feel snappy."""
    chars = len(text or "")
    secs = 0.6 + chars / (wpm * 5 / 60.0)        # quick to start, scales with length
    secs *= random.uniform(0.85, 1.15)           # natural variance
    return round(min(5.0, max(0.8, secs)), 1)


def humanize(text):
    """Inject at most one light, non-offensive typo (~30% of messages) to read as human.
    Never touches digits, never the booking block (applied to visible text only)."""
    if not text or random.random() > 0.12:
        return text
    words = text.split(" ")
    cand = [i for i, w in enumerate(words) if len(w) >= 5 and w.isalpha() and w[0].islower()]
    if not cand:
        return text
    i = random.choice(cand)
    w = words[i]
    j = random.randint(1, len(w) - 2)
    mode = random.choice(["swap", "drop", "double"])
    if mode == "swap":
        w = w[:j] + w[j + 1] + w[j] + w[j + 2:]
    elif mode == "drop":
        w = w[:j] + w[j + 1:]
    else:
        w = w[:j] + w[j] + w[j:]
    words[i] = w
    return " ".join(words)


class Anna:
    def __init__(self, client_id="local_test", safe_mode=None):
        self.client_id = client_id
        # R1 SAFE-MODE: when on, ANNA still talks, but is PHYSICALLY unable to write to any live
        # store (bookings/CRM/memory) or fire any outbound webhook — a public demo can reach a
        # stranger with ZERO live side-effects. Defaults from ANNA_SAFE_MODE=1 so a deploy can
        # enable it without touching call sites; an explicit arg overrides for tests.
        self.safe_mode = (os.environ.get("ANNA_SAFE_MODE") == "1") if safe_mode is None else bool(safe_mode)
        self.cf = CLIENTS / f"{client_id}.json"
        self.mem = rj(self.cf) or {"client_id": client_id, "profile_summary": "", "history": []}
        self.system = build_system_prompt()
        self.last_violations = []
        self.last_blocked = []       # R1: blocking violations the guard substituted this turn
        self.last_degraded = False   # True when the last reply was the holding line (brain was down)

    def _save(self):
        if self.safe_mode:   # R1 SAFE-MODE: never persist memory to disk
            return
        wj(self.cf, self.mem)

    def _queue_recovery(self, text, err):
        """A lead that hit a dead brain is never lost: durably queue the question + alert the operator.
        The supervisor (or `--drain`) answers it for real the moment any backend recovers."""
        _append_jsonl(RECOVERY_QUEUE, {"ts": now(), "client_id": self.client_id, "question": text,
                                       "error": str(err or "")[:200], "status": "pending"})
        try:   # operator alert into the same inbox the dashboard reads — degradation is never silent
            _append_jsonl(ADMIN_INBOX, {"ts": now(), "client_id": self.client_id, "alert": "brain_degraded",
                                        "question": text, "error": str(err or "")[:200], "seen": False})
        except Exception:
            pass

    def _beat(self, ok, latency_ms, err=None):
        """Heartbeat for the operator dashboard pulse: was the brain alive, how fast, on what model."""
        try:
            wj(BRAIN_STATUS, {"ts": now(), "ok": bool(ok), "latency_ms": int(latency_ms),
                              "model": os.environ.get("OPENAI_MODEL") or os.environ.get("ANNA_MODEL") or "gateway",
                              "error": ("" if ok else str(err or "")[:200])})
        except Exception:
            pass

    def proactive_followups(self, horizon_hours=36):
        """Living initiative: draft a warm, human reminder for each upcoming appointment and queue it
        for the operator. ANNA isn't purely reactive — she looks after her patients. Drafts only; the
        operator (or a future live channel) decides to send. Returns the list of drafted reminders."""
        drafted = []
        appts = self.mem.get("appointments") or []
        already = {r.get("appt_ts") for r in _read_jsonl(REMINDERS) if r.get("client_id") == self.client_id}
        for a in appts:
            if a.get("status") in ("cancelled", "done"):
                continue
            if a.get("ts") in already:
                continue   # idempotent: one reminder per appointment
            name = self.mem.get("name") or a.get("name") or ""
            fears = "; ".join((self.mem.get("fears") or [])[:2])
            instr = (f"Ты Анна, администратор стоматологии. Напиши короткое тёплое человеческое напоминание "
                     f"клиенту о записи. Имя: {name or 'неизвестно'}. Услуга: {a.get('service','')}. "
                     f"Время: {a.get('preferred_time','')}. "
                     + (f"Учти, человек тревожный ({fears}), поддержи мягко. " if fears else "")
                     + "1-2 предложения, без длинного тире, по-человечески, не казённо. Только текст сообщения.")
            msg, _ = llm_complete("Ты пишешь живые тёплые напоминания о приёме. Только текст.",
                                  [{"role": "user", "content": instr}])
            if not msg:
                continue
            msg = _deemdash(msg.strip())
            rec = {"ts": now(), "client_id": self.client_id, "name": name,
                   "phone": self.mem.get("phone") or a.get("phone", ""), "service": a.get("service", ""),
                   "preferred_time": a.get("preferred_time", ""), "appt_ts": a.get("ts"),
                   "draft": msg, "status": "drafted", "sent": False}
            _append_jsonl(REMINDERS, rec)
            drafted.append(rec)
        return drafted

    def _book(self, data):
        # idempotency: same service+time confirmed again within 10 min is NOT a second appointment
        for a in (self.mem.get("appointments") or [])[-3:]:
            if (a.get("service") == data.get("service")
                    and a.get("preferred_time") == data.get("preferred_time")
                    and _seconds_between(a.get("ts", ""), now()) < 600):
                return None
        rec = {"client_id": self.client_id, "created_at_utc": now(), "status": "requested", **data}
        if self.safe_mode:   # R1 SAFE-MODE: simulate the lead, write NO file, notify NO ONE
            rec["status"] = "simulated_safe_mode"
            return rec
        stamp = rec["created_at_utc"].replace(":", "").replace(".", "")
        wj(APPTS / f"{self.client_id}-{stamp}.json", rec)
        try:
            self._notify_admin(rec, stamp)   # Booking v2: client card + admin inbox + optional webhook
        except Exception:
            pass
        return rec

    def _client_card(self, rec):
        """Human-readable card the clinic admin sees: who, what, when, contact, context."""
        m = self.mem
        appts = m.get("appointments") or []
        facts = [f for f in (m.get("facts") or []) if f][:6]
        lines = [
            f"# Запись — {rec.get('name') or m.get('name') or 'без имени'}",
            f"Телефон:  {rec.get('phone') or m.get('phone') or '—'}",
            f"Услуга:   {rec.get('service') or '—'}",
            f"Время:    {rec.get('preferred_time') or '—'}",
            f"Статус:   {rec.get('status', 'requested')}",
            f"Создано:  {rec.get('created_at_utc')}",
            f"Клиент:   {self.client_id}",
            "",
            f"Портрет:  {m.get('portrait') or '—'}",
            f"Всего обращений: {len(appts) + 1}",
        ]
        important = [f for f in (m.get("important") or []) if f][:4]
        fears = [f for f in (m.get("fears") or []) if f][:4]
        prefs = [f for f in (m.get("preferences") or []) if f][:4]
        if important:
            lines.append("⚠ Важно: " + "; ".join(important))
        if fears:
            lines.append("Чувствительное: " + "; ".join(fears))
        if prefs:
            lines.append("Предпочтения: " + "; ".join(prefs))
        if facts:
            lines.append("Заметки:")
            lines += [f"  - {f}" for f in facts]
        if rec.get("notes"):
            lines.append(f"Комментарий: {rec['notes']}")
        return "\n".join(lines)

    def _notify_admin(self, rec, stamp):
        """Surface the lead to a real human: write a card + append to the admin inbox the dashboard reads.
        Network notify fires ONLY if ANNA_ADMIN_WEBHOOK is set (no surprise traffic by default)."""
        if self.safe_mode:   # R1 SAFE-MODE: no card, no inbox, no outbound webhook
            return
        card = self._client_card(rec)
        cardp = CARDS / f"{self.client_id}-{stamp}.md"
        cardp.parent.mkdir(parents=True, exist_ok=True)
        cardp.write_text(card + "\n", encoding="utf-8")
        ev = {"ts": now(), "client_id": self.client_id,
              "name": rec.get("name") or self.mem.get("name", ""),
              "phone": rec.get("phone") or self.mem.get("phone", ""),
              "service": rec.get("service", ""), "preferred_time": rec.get("preferred_time", ""),
              "status": rec.get("status", "requested"), "card": str(cardp), "seen": False}
        ADMIN_INBOX.parent.mkdir(parents=True, exist_ok=True)
        with open(ADMIN_INBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        hook = os.environ.get("ANNA_ADMIN_WEBHOOK")
        if hook:
            try:
                body = json.dumps({"text": card}).encode()
                req = urllib.request.Request(hook, data=body, method="POST")
                req.add_header("content-type", "application/json")
                req.add_header("User-Agent", _UA)
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass

    def _refresh_dossier(self):
        """AGI memory: distil a short portrait + durable facts so ANNA is warm and specific on return.
        Best-effort, only on real signal — never blocks or breaks a reply if the brain is busy."""
        hist = self.mem.get("history") or []
        if len(hist) < 3:
            return
        convo = "\n".join(f"{'Клиент' if h.get('role') == 'user' else 'Анна'}: {h.get('message', '')}"
                          for h in hist[-16:])
        instr = ("По диалогу обнови досье клиента стоматологии. Верни СТРОГО один JSON:\n"
                 '{"portrait":"одно тёплое человеческое предложение: кто это и что важно учитывать",'
                 '"address_form":"ты или вы или пусто",'
                 '"facts":["до 5 кратких устойчивых фактов о человеке"],'
                 '"fears":["страхи и чувствительные темы, если прозвучали"],'
                 '"preferences":["предпочтения: время, канал связи, врач, формат"],'
                 '"important":["критичное для приёма: беременность, аллергии, хронические — только если сказано"]}\n'
                 "Только то, что реально прозвучало. Пустой список если нечего. Ничего не выдумывай.\n\nДИАЛОГ:\n"
                 + convo)
        out, _ = llm_complete("Ты аккуратный портретист-аналитик. Возвращаешь только JSON, без пояснений.",
                              [{"role": "user", "content": instr}])
        if not out:
            return
        try:
            j = json.loads(out[out.find("{"): out.rfind("}") + 1])
        except Exception:
            return
        if isinstance(j.get("portrait"), str) and j["portrait"].strip():
            self.mem["portrait"] = j["portrait"].strip()
        if isinstance(j.get("address_form"), str) and j["address_form"].strip() in ("ты", "вы"):
            self.mem["address_form"] = j["address_form"].strip()
        for key in ("facts", "fears", "preferences", "important"):
            v = j.get(key)
            if isinstance(v, list):
                cleaned = [str(x).strip() for x in v if str(x).strip()][:6]
                if cleaned:   # only overwrite when we actually learned something — never wipe known memory
                    self.mem[key] = cleaned
        self._consolidate_memory()

    def _consolidate_memory(self):
        """Robustness + continuity: when raw history grows long, distil the older part into a durable
        summary and keep only recent turns. Bounds context size and preserves the relationship thread."""
        hist = self.mem.get("history") or []
        if len(hist) <= 24:
            return
        old = hist[:-12]
        convo = "\n".join(f"{'Клиент' if h.get('role') == 'user' else 'Анна'}: {h.get('message', '')}" for h in old)
        prev = (self.mem.get("summary") or "").strip()
        instr = ("Сожми предысторию общения в 2-4 предложения: сохрани имя, ключевые жалобы, записи, "
                 "договорённости и тон отношений. "
                 + (f"Учти прошлую сводку: {prev}\n\n" if prev else "")
                 + "ДИАЛОГ:\n" + convo)
        out, _ = llm_complete("Ты сжимаешь историю общения в краткую живую память. Только текст сводки.",
                              [{"role": "user", "content": instr}])
        if out and out.strip():
            self.mem["summary"] = out.strip()[:600]
            self.mem["history"] = hist[-12:]   # older turns now live in the summary

    def _guard_outgoing(self, out, booking_made):
        """R1.2/1.3: the safety layer now BLOCKS, not just logs. The deterministic denylist is the
        always-on floor; if ANNA_SEMANTIC_GUARD=1 the intent-aware judge adds oblique coverage
        (drug names, 'нерв погиб', 'виртуальный ассистент', 'место забронировано'). A blocking
        violation (diagnosis / AI-reveal / fake-booking) replaces the reply with a safe line.
        Returns (out, hard_violations:list, blocked:list)."""
        hard = safety_check(out, booking_made)
        viol = set(hard)
        if os.environ.get("ANNA_SEMANTIC_GUARD"):   # opt-in intent-aware second pass (LLM call)
            global _SEM_MOD
            try:
                if _SEM_MOD is None:
                    spec = _ilu.spec_from_file_location("anna_semantic_guard_v1",
                                                        ROOT / "scripts/socc/anna_semantic_guard_v1.py")
                    _SEM_MOD = _ilu.module_from_spec(spec); spec.loader.exec_module(_SEM_MOD)
                sem, _verdict, serr = _SEM_MOD.semantic_check(out)
                if not serr:
                    viol |= set(sem)
            except Exception:
                pass   # the hard floor still blocks; the judge is best-effort defense-in-depth
        blocked = [v for v in _BLOCK_PRIORITY if v in viol]
        # fake-booking is only a real violation when no booking was actually made (the judge can't
        # see booking_made) — never substitute over a genuine confirmed booking.
        if booking_made and "booking_confirmed_without_real_record" in blocked:
            blocked.remove("booking_confirmed_without_real_record")
        if blocked:
            out = _SAFE_SUBSTITUTE[blocked[0]]
        return out, list(hard), blocked

    def reply(self, text):
        self.mem.setdefault("history", [])
        ts = now()
        prev_seen = self.mem.get("last_seen_utc")
        gap_h = (_seconds_between(prev_seen, ts) / 3600.0) if prev_seen else None
        self.mem["warmth"] = "returning" if (self.mem.get("history") or self.mem.get("appointments")) else "new"
        # real session timer: a gap > 6h starts a fresh session; track turns + elapsed
        sess = self.mem.setdefault("session", {})
        if gap_h is None or gap_h > 6:
            sess["started_utc"] = ts
            sess["turns"] = 0
        sess["turns"] = sess.get("turns", 0) + 1
        sess["last_utc"] = ts
        sess["elapsed_s"] = round(_seconds_between(sess.get("started_utc", ts), ts))
        if gap_h is not None:
            self.mem["_return_gap_h"] = round(gap_h, 1)   # transient: feeds tempo block, popped before save
        self.mem["history"].append({"role": "user", "message": text, "ts": ts})
        self.mem["last_seen_utc"] = ts
        # emotional memory: remember how this person feels and how warm the relationship is
        mood = _detect_mood(text)
        self.mem["last_mood"] = mood
        mlog = self.mem.setdefault("mood_log", [])
        mlog.append({"mood": mood, "ts": ts})
        self.mem["mood_log"] = mlog[-20:]
        n_user = sum(1 for h in self.mem["history"] if h.get("role") == "user")
        self.mem["rapport"] = ("доверительные" if (n_user > 7 or len(self.mem.get("appointments") or []) >= 2)
                               else "тёплые" if n_user > 2 else "знакомство")
        # build conversation for the LLM (last ~10 turns); system prompt carries the live dossier
        msgs = [{"role": h["role"], "content": h["message"]} for h in self.mem["history"][-10:]]
        system = build_system_prompt(self.mem, last_user=text)
        _t0 = time.time()
        out, err = llm_complete(system, msgs)
        self._beat(out is not None, int((time.time() - _t0) * 1000), err)
        if out is None:   # brain down → stay in character, but NEVER silently drop the lead
            self.last_degraded = True
            holding = "Секунду, отвлеклась на пациента, буквально минуту и вернусь к вам"
            self.mem["history"].append({"role": "assistant", "message": holding, "ts": now()})
            self.mem.pop("_return_gap_h", None)
            self._save()
            try:
                self._queue_recovery(text, err)   # durably queue the question + alert the operator
            except Exception:
                pass
            return holding, None
        self.last_degraded = False
        booking = None
        if "[[BOOK]]" in out and "[[/BOOK]]" in out:
            raw = out.split("[[BOOK]]", 1)[1].split("[[/BOOK]]", 1)[0]
            visible = (out.split("[[BOOK]]", 1)[0]).strip()
            try:
                booking = self._book(_scrub_booking(json.loads(raw), self.mem["history"]))
            except Exception:
                booking = None
            out = visible
        if booking is None:  # model may confirm verbally but forget the hidden block — recover the lead
            low = out.lower()
            recent_user = " ".join(h.get("message", "") for h in self.mem["history"][-6:] if h.get("role") == "user")
            if any(mk in low for mk in _CONFIRM_MARKERS) or _PHONE_RE.search(recent_user):
                cap = _extract_booking(self.mem["history"] + [{"role": "assistant", "message": out}])
                if cap:
                    booking = self._book(cap)
        out = _deemdash(out)   # auto-repair I5 so a long dash never reaches the client
        # R1.2/1.3: BLOCKING guard — a diagnosis / AI-reveal / fake-booking claim is REPLACED with a
        # safe in-character line before it can reach the person (was: log-only). Hard floor always on;
        # ANNA_SEMANTIC_GUARD=1 adds the intent-aware judge for oblique phrasings.
        out, self.last_violations, self.last_blocked = self._guard_outgoing(out, booking is not None)
        if self.last_violations or self.last_blocked:
            SAFETY_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(SAFETY_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": now(), "client": self.client_id, "violations": self.last_violations,
                                    "blocked": self.last_blocked, "text": out}, ensure_ascii=False) + "\n")
        if booking:  # persist into the living dossier so ANNA is warm & informed on return
            self.mem.setdefault("appointments", []).append(
                {"service": booking.get("service", ""), "preferred_time": booking.get("preferred_time", ""),
                 "name": booking.get("name", ""), "phone": booking.get("phone", ""),
                 "status": booking.get("status", "requested"), "ts": booking.get("created_at_utc", now())})
            if booking.get("name"):
                self.mem["name"] = booking["name"]
            if booking.get("phone"):
                self.mem["phone"] = booking["phone"]
        self.mem["history"].append({"role": "assistant", "message": out, "ts": now()})
        turns = sum(1 for h in self.mem["history"] if h.get("role") == "user")
        low = text.lower()
        salient = bool(_PHONE_RE.search(text)) or any(k in low for k in (
            "боюсь", "паник", "страшно", "аллерг", "беремен", "хроническ", "зовут", "меня зовут"))
        if booking or salient or turns % 4 == 0:   # capture fears/important/name promptly; else every 4 turns
            try:
                self._refresh_dossier()
            except Exception:
                pass
        ot = _derive_open_thread(self.mem, text, booking)   # deep continuity: carry the unfinished thread forward
        if ot is None:
            self.mem.pop("open_thread", None)
        else:
            self.mem["open_thread"] = ot
        self.mem.pop("_return_gap_h", None)   # don't persist the transient tempo signal
        self._save()
        return humanize(out), booking


def drain_pending(send=None):
    """Answer for real every lead that hit a dead brain, now that a backend is back.
    Tolerant of torn lines (skip, never stall). `send(client_id, answer)` optionally delivers
    (e.g. Telegram). Returns list of {client_id, question, answer}. This is what turns the
    recovery queue from a write-only graveyard into a kept promise — no lead is ever lost."""
    if not RECOVERY_QUEUE.exists():
        return []
    rows = []
    for ln in RECOVERY_QUEUE.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue   # torn line → skip, never stall the drainer (adversary finding)
    answered, changed = [], False
    for r in rows:
        if r.get("status") != "pending":
            continue
        anna = Anna(client_id=r.get("client_id"))
        msgs = [{"role": h["role"], "content": h["message"]} for h in anna.mem.get("history", [])[-10:]]
        out, _err = llm_complete(build_system_prompt(anna.mem, last_user=r.get("question")), msgs)
        if out is None:
            continue   # brain still down → leave pending for the next drain
        out = _deemdash(out)
        anna.mem.setdefault("history", []).append({"role": "assistant", "message": out, "ts": now()})
        anna._save()
        r.update(status="answered", answered_at=now(), answer=out)
        changed = True
        answered.append({"client_id": r.get("client_id"), "question": r.get("question"), "answer": out})
        if send:
            try:
                send(r.get("client_id"), out)
            except Exception:
                pass
    if changed:   # rewrite atomically with updated statuses
        tmp = RECOVERY_QUEUE.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
        tmp.replace(RECOVERY_QUEUE)
    return answered


def brain_health(timeout_each=20):
    """Operator/watchdog self-test: is ANNA's brain reachable RIGHT NOW, and through which backend.
    Pings the full backend chain once with a trivial prompt, writes BRAIN_STATUS, returns a dict.
    A watchdog can run `python3 anna_runtime_v1.py --health || restart` — exit 0 = alive, 1 = dead.
    This is the foundation of L1 'unkillable': you cannot keep a brain alive you cannot probe."""
    configured = [b[0] + ":" + b[3] for b in _backends()]
    if _claude_keys():
        configured.append(f"gateway x{len(_claude_keys())}")
    t0 = time.time()
    out, err = llm_complete("Ответь ровно одним словом: ок",
                            [{"role": "user", "content": "скажи: ок"}])
    ms = int((time.time() - t0) * 1000)
    alive = out is not None
    status = {"ts": now(), "ok": alive, "latency_ms": ms,
              "configured_backends": configured,
              "independent_floor": _has_independent_floor(),
              "sample": (out or "").strip()[:60], "error": ("" if alive else str(err)[:200])}
    if not status["independent_floor"]:
        status["warning"] = ("НЕТ независимого floor-ключа: вся цепочка = один freemodel-аккаунт "
                             "(единая точка отказа). Добавь настоящий ANTHROPIC_API_KEY (sk-ant-*) или "
                             "иной не-freemodel ключ в .secrets/anna_llm.env.")
    try:
        wj(BRAIN_STATUS, status)
    except Exception:
        pass
    return status


def main():
    args = sys.argv[1:]

    if "--health" in args:   # watchdog/operator probe — honest live pulse of the brain
        s = brain_health()
        mark = "🟢 ЖИВ" if s["ok"] else "🔴 МЁРТВ"
        print(f"{mark} · {s['latency_ms']}мс · backends={s['configured_backends'] or 'NONE ❌'}")
        print(f"   ответ: {s['sample']}" if s["ok"] else f"   ошибка: {s['error']}")
        floor = "🟢 независимый floor есть" if s.get("independent_floor") else "⚠ нет независимого floor-ключа (один freemodel = SPOF)"
        print(f"   {floor}")
        sys.exit(0 if s["ok"] else 1)

    if "--drain" in args:   # answer leads that hit a dead brain, now that it's back
        done = drain_pending()
        print(f"Восстановлено лидов: {len(done)}")
        for d in done:
            print(f"→ {d['client_id']}: «{(d.get('question') or '')[:50]}» → «{(d.get('answer') or '')[:70]}»")
        return

    bks = [b[0] + ":" + b[3] for b in _backends()]
    if _claude_keys() and shutil.which("claude"):
        bks = [f"claude_cli x{len(_claude_keys())} (gateway, free)"] + bks
    print(f"ANNA Runtime V1  ·  backends={bks or 'NONE ❌'}")
    print(f"identity: {'loaded ✅' if IDENTITY.exists() else 'MISSING'}  ·  local only (no Telegram)\n")
    anna = Anna()

    if "--demo" in args:
        script = [
            "Здравствуйте! У меня второй день ноет зуб справа снизу, аж к виску отдаёт",
            "Сегодня вечером смогли бы? И сколько примерно осмотр стоит",
            "Давайте на 19:00. Меня Игорь зовут, телефон 89161234567",
        ]
        for m in script:
            print(f"🧑 Пациент: {m}")
            r = anna.reply(m)
            if isinstance(r, tuple):
                print(f"💬 Анна: {r[0]}")
                if r[1]: print(f"   📅 [ЗАПИСЬ создана: {r[1].get('service')} · {r[1].get('preferred_time')} · {r[1].get('name')}]")
                if anna.last_violations: print(f"   ⚠ [safety: {', '.join(anna.last_violations)}]")
            else:
                print(f"💬 Анна: {r}")
            print()
        return

    if "--once" in args:
        i = args.index("--once"); msg = args[i + 1] if i + 1 < len(args) else "привет"
        r = anna.reply(msg)
        print(r[0] if isinstance(r, tuple) else r)
        if isinstance(r, tuple) and r[1]: print(f"[ЗАПИСЬ: {r[1]}]")
        return

    if "--followups" in args:
        i = args.index("--followups"); cid = args[i + 1] if i + 1 < len(args) else "local_test"
        drafts = Anna(client_id=cid).proactive_followups()
        print(f"Черновиков напоминаний: {len(drafts)}")
        for d in drafts:
            print(f"→ {d.get('name') or d.get('client_id')} | {d.get('service')} {d.get('preferred_time')}")
            print(f"   {d.get('draft')}")
        return

    print("Диалог с Анной (Ctrl-D для выхода):")
    while True:
        try:
            msg = input("🧑 ты: ").strip()
        except EOFError:
            break
        if not msg: continue
        r = anna.reply(msg)
        if isinstance(r, tuple):
            print(f"💬 Анна: {r[0]}")
            if r[1]: print(f"   📅 [ЗАПИСЬ: {r[1].get('service')} · {r[1].get('preferred_time')}]")
        else:
            print(f"💬 Анна: {r}")


if __name__ == "__main__":
    main()

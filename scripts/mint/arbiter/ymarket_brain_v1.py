#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC-ЯМ · УПРАВЛЯЮЩИЙ-МОЗГ (V3) — мета-цикл (мозг + интерфейс) над органом MINT.

MINT — фин-орган SOCC: сейчас на нём Яндекс Маркет (живой кабинет), дальше будет Озон.
Внутри MINT много процессов: магазины-циклы (манифест/узел-цепь/пульс у каждого), роли,
отчёты. ЦИКЛ-1 (Идея→Товар→Витрина) — ОДИН из циклов, для магазина atlas-express-film;
это не вся ось. Ось — MINT целиком.

V3 (директива оператора: «как SOCC + LLM моя», ИЛЯХОВ-тексты × ЛЕБЕДЕВ-дизайн):
- Идентичность: SOCC-ЯМ над MINT (не «орган ARBITER»). Чат + меню-навигатор («провал в меню»).
- SOCC-канон: цвета/бейджи из socc_cli.style — один стиль со всем SOCC.
- Думаю-индикатор: когда мозг отвечает — живой спиннер «⠙ думаю…» (tty), транскрипт виден.
- Коротко: ответ мозга ≤8 строк (ИЛЯХОВ), карточка цикла компактная — БЕЗ ЗАЛИВ-листа цен.
- Меню: цифры — выбрать, 0 — назад/в чат, свободный текст — разговор. Сессия-лог.

Мандат: отвечает по-русски как со-пилот (коротко, конкретно, числа); умеет ИНИЦИИРОВАТЬ сухие
ходы органов/ЦИКЛА-1; живые записи — только по явному слову оператора (RUBICON). Знает про
тишину (движок по умолчанию ТИХИЙ — пульс+вердикт, без россыпи payload) и маму-наследование
(новый цикл объявляет mother=<slug> и наследует кабинет — системе «пофиг какой API»).

is_not: не заменяет оператора; не пишет в кабинет сам; не выполняет произвольных команд мозга.
honesty_boundary: секреты в контекст мозга НЕ попадают (только «ключ задан: да/нет»); без ключа
мозг честно говорит «недоступен» и не выдумывает; RUBICON держится физически.

Законы (спека YM_BRAIN_V1.md):
- BR1  мозг сам НЕ пишет: write-действия (cycle_live, new_cycle) только после явного «да».
- BR2  строгий allowlist: только действия из ACTIONS; иначе — отказ, никакого произвольного шелла.
- BR3  секреты не утекают в контекст (только булевы «ключ задан»).
- BR4  честный оффлайн: без ключа — «мозг недоступен: …», локальные команды (/мама, /само) живут.
- BR5  тишина по умолчанию: сухой ход цикла — пульс + вердикт; --verbose открывает полный поток.
- BR6  мама-наследование: дочерний цикл наследует кабинет от матери; кабинет-agnostic вход.

Запуск:
  python3 ymarket_brain_v1.py                 # REPL: чат + меню («меню» / /меню)
  python3 ymarket_brain_v1.py --say "привет"  # one-shot: контекст + ответ, действия анонсируются
  python3 ymarket_brain_v1.py --registry|--self|--pulse [store]|--organs   # read-only взгляды
"""
import argparse
import contextlib
import datetime
import io
import json
import os
import pathlib
import shlex
import ssl
import sys
import threading
import urllib.error
import urllib.request

ARB = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ARB))

try:
    import ymarket_cycle1_v1 as cycle1   # движок ЦИКЛА-1 (манифест/резолв мамы/пульс)
except Exception as _e:                  # noqa: E402  (импорт-слой должен быть жив даже без них)
    cycle1 = None
try:
    import ymarket_self_v1 as self_org   # самоосознание управляющего (read)
except Exception as _e:
    self_org = None
try:
    import ymarket_console_v1 as console # КОНСОЛЬ-ЯМ (read-кабинет: ШТАБ-дайв + ДЕЛО)
except Exception as _e:
    console = None
try:
    import ymarket_cycle_day_v1 as cyc_day  # ЦИКЛ-ДНЯ (планёрка заданий / форма / диспетчер, read)
except Exception as _e:
    cyc_day = None

# ключи/конфиг — ТОЛЬКО env (mint/.env, socc_mint_env_v1). Значения в код/контекст не пишем.
MINT_DIR = ARB.parent
sys.path.insert(0, str(MINT_DIR))
try:
    import socc_mint_env_v1 as env
except Exception as _e:
    env = None

KEY_NAME = "AGENTROUTER_API_KEY"
BASE_URL_DEFAULT = "https://agentrouter.org"
MODEL_DEFAULT = "deepseek-v4-flash"

STORE_DEFAULT = (getattr(cycle1, "STORE_DEFAULT", "atlas-express-film")
                 if cycle1 else "atlas-express-film")

# ─────────────────────────────────────────────────────────────────────────────
#  SOCC-КАНОН · CLI (V3). Каждая терминальная поверхность SOCC импортирует
#  цвета/бейджи из socc_cli.style — один стиль на весь SOCC (см. SOCC_DESIGN_CANON).
#  Out-aware: ANSI рисуем ТОЛЬКО когда out — живой tty; StringIO-тесты = plain.
# ─────────────────────────────────────────────────────────────────────────────

SOCC_ROOT = ARB.parents[2] if len(ARB.parents) > 2 else ARB.parents[-1]
if str(SOCC_ROOT) not in sys.path:
    sys.path.insert(0, str(SOCC_ROOT))
try:
    from socc_cli import style as S   # канон: CY/GR/YE/RE/MA/BL + c/header/badge/dot
except Exception as _e:               # канон недоступен — работаем plain, честно
    S = None

_RUNTIME = ARB / "runtime" / "brain"          # сессия-лог (runtime gitignored)
_NAV = {"mode": "chat", "level": 0, "store": None}   # навигатор: 0 циклы MINT · 1 внутри цикла · 10 ШТАБ · 11 карточка роли · 20 ДЕЛО


def _tty(out):
    f = getattr(out, "isatty", None)
    if f is None:
        return False
    try:
        return bool(f())
    except Exception:
        return False


def _col(out, token, text):
    """Покрасить по канону (S.CY/GR/YE/RE/MA/BL + R). Plain, если не tty или канона нет."""
    if not (S and _tty(out)):
        return text
    code = getattr(S, token, "")
    return f"{code}{text}{S.R}" if code else text


def _dim(out, text):
    return _col(out, "DIM", text)


def _b(out, text):
    return _col(out, "B", text)


def _snip(text, n=140):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _session_path():
    try:
        d = datetime.date.today().isoformat()
        _RUNTIME.mkdir(parents=True, exist_ok=True)
        return _RUNTIME / f"session_{d}.log"
    except Exception:
        return None


def _log(text):
    """Сессия-лог (fail-soft): кто что сказал + что сделано. runtime/ gitignored."""
    p = _session_path()
    if p is None:
        return
    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  КАТАЛОГ ДЕЙСТВИЙ (строгий allowlist, BR2). role: read|dry|write.
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    "cycle_dry": {
        "role": "dry",
        "help": "сухой ход ЦИКЛА-1 (0₽ наружу; СВЕРКА реальным чтением). args: --store <slug>",
    },
    "cycle_live": {
        "role": "write",
        "help": "ЖИВОЙ ход ЦИКЛА-1 (--commit: пишет в кабинет). ТОЛЬКО по слову оператора. args: --store <slug>",
    },
    "plannerka": {
        "role": "read",
        "help": "пульс/планёрка магазина (последний прогон). args: --store <slug>",
    },
    "self": {
        "role": "read",
        "help": "самоосознание управляющего (карточки/индекс/следующий законный шаг).",
    },
    "registry": {
        "role": "read",
        "help": "реестр циклов: кто какому мама-циклу наследует кабинет (hash-база).",
    },
    "new_cycle": {
        "role": "write",
        "help": ("новый магазин в манифест runtime/cycle1/stores.json (файл, НЕ сеть). "
                 "поз.: <slug> <builder=film|box> <donor_category> <markup> <stock_count> "
                 "[--mother <slug>] [--builder_slug <slug>]"),
    },
    "tasks": {
        "role": "read",
        "help": ("задания ЯМ-ЦИКЛА (ЦИКЛ-ДНЯ): что открыто и КТО ответственный, важное выше. "
                 "args: --store <slug> · --form (показать, что сформируется) · --commit (форма пишет "
                 "локальный реестр) · --dispatch (разбор: кто исполнит). 0₽."),
    },
}

# семантические алиасы (и для /команд, и для [ДЕЙСТВИЕ] из мозга)
ALIASES = {
    "мама": "registry", "циклы": "registry", "cycles": "registry",
    "реестр": "registry", "registry": "registry",
    "само": "self", "self": "self",
    "пульс": "plannerka", "планёрка": "plannerka",
    "цикл": "cycle_dry", "cycle": "cycle_dry",
    # пульс-1/цикл-1 = ПРОГОН цикла по конкретному магазину (узлы и правила) → cycle_dry
    "пульс-1": "cycle_dry", "пульс1": "cycle_dry",
    "цикл-1": "cycle_dry", "цикл1": "cycle_dry",
    # задания ЯМ-ЦИКЛА (терминал + форма + диспетчер)
    "задания": "tasks", "задача": "tasks", "задачи": "tasks",
    "дело": "tasks", "дела": "tasks", "tasks": "tasks",
}

LAWS_TEXT = (
    "Законы (RUBICON держится): BR1 мозг сам не пишет — write только после явного «да» оператора; "
    "BR2 строгий allowlist действий (никакого произвольного шелла); BR3 секреты в контекст не попадают "
    "(только булевы «ключ задан»); BR4 без ключа мозг честно недоступен, локальные команды живут; "
    "BR5 сухой ход тихий — пульс+вердикт, --verbose открывает поток; BR6 мама-наследование кабинета."
)
QUIET_HINT = (
    "движок ЦИКЛА-1 тихий по умолчанию: сухой ход печатает пульс-строки и вердикт, без россыпи "
    "payload; полный поток — cycle1 --verbose."
)
IDENTITY_TEXT = (
    "ИДЕНТИЧНОСТЬ: ты УПРАВЛЯЮЩИЙ-МОЗГ SOCC-ЯМ — мета-цикл (мозг + интерфейс) НАД органом MINT "
    "(фин-орган SOCC). На MINT сейчас живёт Яндекс Маркет (Экспресс, кабинет в работе), дальше будет "
    "Озон. Внутри MINT много процессов: магазины-циклы (у каждого свой манифест + узел-цепь + пульс), "
    "роли, отчёты, ленты. ЦИКЛ-1 (Идея→Товар→Витрина) — ОДИН из циклов, для магазина atlas-express-"
    "film; ось — не он, а весь MINT. Ты не «голос движка»: у тебя есть мозг (своя LLM) и интерфейс "
    "(чат + меню), и ты говоришь за всё хозяйство MINT."
)
STYLE_TEXT = (
    "СТИЛЬ ОТВЕТА (ИЛЯХОВ × ЛЕБЕДЕВ): коротко и по делу — не больше 4–6 строк, цифры вместо "
    "прилагательных, ноль канцелярита, ноль повторения уже показанного. Как в чате. Действие, если "
    "нужно, — строкой [ДЕЙСТВИЕ] <имя> <аргументы> строго из каталога ниже. Пиши по-русски."
)

# ─────────────────────────────────────────────────────────────────────────────
#  ТЕЛО SOCC — знание-слой МОЗГА V2 (доктрина / донор-модель / законы / глоссарий).
#  Это же тело мозг несёт в контекст LLM и умеет им отвечать ОФФЛАЙН, когда голос молчит.
# ─────────────────────────────────────────────────────────────────────────────

DOCTRINE_TEXT = (
    "ДОКТРИНА СБЫТА: Яндекс.Маркет ЭКСПРЕСС — курьер Маркета забирает товар у ДОНОРА по внутреннему № "
    "заказа; DBS/свой склад НЕ нужны. ВЫКУП У ДОНОРА ТОЛЬКО ПОСЛЕ ОПЛАЧЕННОГО заказа — никаких закупок "
    "заранее (железный закон). Кабинет В РАБОТЕ: Atlas biz 216949599 · Express 149215943 · склад 2390811; "
    "боевой: biz 184481130 · Express 148619267 · склад 1803385."
)
DONOR_TEXT = (
    "ДОНОР = МАГАЗИН-поставщик (адаптер suppliers/*_v1.py). Сейчас донор = cargo shop CARGO-AVTO "
    "(shop.cargo-avto.ru, suppliers/cargo_avto_v1.py). ДОНОР-КАТЕГОРИЯ (donor_category в манифесте) = "
    "URL-путь ВНУТРИ донора (напр. vozdushno-puzyrkovaya-plenka) — раздел донора, НЕ сам донор. "
    "Донор один, категорий много."
)
LAWS_CANON = (
    "Законы канона (YM_CYCLE1_V1 §13): L6 RUBICON — write только --commit по слову оператора; "
    "L8 бренд = «Без бренда» (YM не индексирует незарегистрированный бренд); L9 цена = закупка×markup "
    "(владелец ЦЕНОВИК), товар НЕ в акциях; L10 ОВХ = правдивая транспортная упаковка; L11 карточка без "
    "фото = FAIL; L12 НЕТ fake pass (200 OK врёт, правда — в чтении); L13 задачи, не вопросы; "
    "L14 планёрка = самоосознание."
)
RULES_TEXT = (
    "ПРАВИЛА ПОВЕДЕНИЯ: 1) НЕ запускай сухой ход (cycle_dry) в каждом ответе сам. Прогон цикла — "
    "дорогой (секунды живых чтений). Гоняй ТОЛЬКО когда оператор прямо просит («запусти/прогони "
    "цикл/пульс-1 <магазин>») ИЛИ спросил «что дальше/как дела», а сегодня ещё не прогоняли. "
    "2) Если состояние уже известно и не менялось — не пересказывай: назови одной строкой пульс "
    "(вердикты/артефакты) и предложи реальный следующий шаг (новый цикл/магазин, живьё, партнёр). "
    "3) write (cycle_live, new_cycle) — предложи и жди явное «да». 4) никогда не отвечай пусто: не "
    "уверен — покажи, что видишь в реестре/пульсе, и предложи выбор."
)

# маркер-в-тексте → определение: и в контекст мозга, и в оффлайн-ответ (когда голос-LLM молчит)
GLOSS = (
    ("магазин в работе",
     "сейчас в работе: atlas-express-film (плёночный; категория донора vozdushno-puzyrkovaya-plenka; "
     "кабинет Atlas 216949599; карточки ARB-* PUBLISHED + FIT=100, «Без бренда»). В манифесте "
     "stores.json он единственный; box-msk там НЕТ."),
    ("пульс-1",
     "прогон ЦИКЛА-1 по конкретному магазину: цепь узлов ДОНОР→СБОРКА→ЗАЛИВ→ВИТРИНА→ОСТАТКИ→СВЕРКА→"
     "ПЛАНЁРКА с правилами-PASS. Запускаю сухо-авто: [ДЕЙСТВИЕ] cycle_dry --store <slug> (0₽)."),
    ("цикл-1",
     "«Идея→Товар→Витрина»: законная цепь узлов до артефакта (товар на витрине). 10–100 магазинов "
     "параллельно, у каждого манифест + леджер + хеш."),
    ("запечатан",
     "«запечатан» — не термин. Правда смотрится в пульсе магазина: вердикты узлов, число артефактов-"
     "СВЕРКА PASS и/или чистый DRY-ПРОХОД."),
    ("хеш",
     "хеш цикла = sha1(slug×дата×версия цепи)[:10] — уникальный адрес прогона; леджер "
     "runtime/cycle1/<slug>/<дата>.jsonl."),
    ("мама",
     "цикл-мать: дочерний цикл {mother} наследует кабинет (business/campaign/warehouse_id) по цепочке; "
     "товарные поля (донор/builder/markup/остаток) — свои. Мать по умолчанию: atlas-express-film."),
    ("сверка",
     "узел-ЧТЕНИЕ живого кабинета: PUBLISHED + available + остаток + vendor «Без бренда». Работает "
     "всегда, и в dry. 200 OK от писателей врёт — правда только в чтении."),
    ("рубикон",
     "L6 RUBICON: write в сеть ТОЛЬКО при --commit по явному слову оператора; мозг сам не пишет (BR1)."),
    ("сухо",
     "dry-ход: точный payload собран и прошёл гейт, НЕ отправлен (0₽ наружу); СВЕРКА всё равно живьём "
     "читает. Сухой ход — авто, без слова оператора."),
    ("живьё",
     "--commit: пишет в кабинет. Только по слову оператора (RUBICON/BR1)."),
    ("донор",
     "МАГАЗИН-поставщик. Сейчас донор = cargo shop cargo-avto (shop.cargo-avto.ru, "
     "suppliers/cargo_avto_v1.py). Категория донора (URL-путь, напр. vozdushno-puzyrkovaya-plenka) — "
     "раздел внутри донора, НЕ сам донор."),
)

# известные донор-магазины по категориям — честная подпись в реестре (донор ≠ категория)
DONOR_SHOPS = {
    "vozdushno-puzyrkovaya-plenka": "cargo-avto · cargo shop (shop.cargo-avto.ru)",
}


def _ensure_env():
    """Загрузить mint/.env (fail-soft). Читатели-функции ниже всегда работают."""
    if env is not None:
        try:
            env.ensure_env()
        except Exception as _e:
            pass
    return os.environ


# ─────────────────────────────────────────────────────────────────────────────
#  HTTP К МОЗГУ (agentrouter /v1/messages, Anthropic-форма) — fail-soft, BR4
# ─────────────────────────────────────────────────────────────────────────────

def _http_post(url, body, timeout=90):
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "User-Agent": "claude-cli/1.0.60 (external, cli)",
        "x-app": "cli",
    }
    key = os.getenv(KEY_NAME)
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=ssl.create_default_context()) as r:
            return r.getcode(), r.read(300_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8", "ignore") if hasattr(e, "read") else "")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def brain_call(system, user, history=None):
    """Один обмен с мозгом. {ok:True,text,model} или {ok:False,error} — честно, BR4.

    Устойчивость V2: LLM через relay иногда возвращает ТОЛЬКО thinking-блоки с пустым text
    → второй заход с пинком. Если снова пусто — {ok:False, empty:True}: REPL отвечает из
    тела SOCC (см. _offline_answer), «мозг вернул пустой ответ» больше НЕ тупик разговора.
    """
    _ensure_env()
    key = os.getenv(KEY_NAME)
    if not key:
        return {"ok": False,
                "error": "мозг недоступен: нет AGENTROUTER_API_KEY в mint/.env "
                         "(локальные команды /мама /само /пульс работают)"}
    base = (os.getenv("AGENTROUTER_BASE_URL") or BASE_URL_DEFAULT).rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]                                   # base уже с /v1 → не дублируем
    model = os.getenv("ANTHROPIC_MODEL") or MODEL_DEFAULT
    nudge = ("\n\n(Твой прошлый ответ пришёл ПУСТЫМ — relay вернул только размышления. "
             "Ответь теперь ОБЫЧНЫМ ТЕКСТОМ: кратко, по делу; если нужен сухой ход — строкой "
             "[ДЕЙСТВИЕ] …. Без блока «размышлений».)")
    for attempt in (0, 1):
        msg_user = user if attempt == 0 else user + nudge
        messages = list(history or [])
        messages.append({"role": "user", "content": msg_user})
        body = {"model": model, "max_tokens": 900,
                "system": system, "messages": messages}
        code, raw = _http_post(base + "/v1/messages", body)
        if code != 200:
            return {"ok": False,
                    "error": f"мозг: HTTP {code} — {(raw or '')[:180].strip()}"}
        try:
            doc = json.loads(raw)
            text = "".join(
                (b.get("text") or "") for b in (doc.get("content") or [])
                if b.get("type") == "text"
            ).strip()
        except Exception as e:
            return {"ok": False, "error": f"мозг: разбор ответа не удался — {e}"}
        if text:
            return {"ok": True, "text": text, "model": model}
    return {"ok": False, "empty": True,
            "error": "мозг вернул пустой ответ (2 попытки) — отвечаю из тела SOCC"}


# ─────────────────────────────────────────────────────────────────────────────
#  КОНТЕКСТ ДЛЯ МОЗГА (живое состояние БЕЗ сети и БЕЗ секретов, BR3)
# ─────────────────────────────────────────────────────────────────────────────

def _cycle_short_state():
    """Строка по каждому циклу: builder/донор/мама/кабинет/пульс. Секретов нет."""
    if cycle1 is None:
        return "движок ЦИКЛА-1 недоступен (import)"
    try:
        reg = cycle1.list_cycles()
    except Exception as e:
        return f"реестр циклов недоступен: {type(e).__name__}: {e}"
    if not reg:
        return "манифест циклов пуст (runtime/cycle1/stores.json) — первый цикл = мать."
    lines = []
    for slug, c in reg.items():
        cab_own = any(v is not None for v in (c.get("cabinet") or {}).values())
        src = "свой кабинет" if cab_own else "кабинет от мамы"
        pulse = ""
        try:
            p = cycle1.plannerka_read(slug)
            if p:
                pulse = f" · пульс: {p.get('date')} вердикты={p.get('run_verdicts')} арт={p.get('artifacts')}"
        except Exception:
            pulse = ""
        ok = "ok" if c.get("resolve_ok") else f"FAIL: {c.get('resolve_why') or '?'}"
        donor_shop = DONOR_SHOPS.get(c.get("donor_category"))
        dshop = (f" · донор-магазин: {donor_shop}" if donor_shop
                 else " · донор-магазин: по адаптеру категории (suppliers/*)")
        mark = "★ В РАБОТЕ · " if slug == STORE_DEFAULT else ""
        lines.append(
            f"- {mark}{slug}: builder={c.get('builder')} категория-донора={c.get('donor_category')}"
            f"{dshop} markup=×{c.get('markup')} остаток={c.get('stock_count')} · {src} "
            f"(mother={c.get('mother') or '—'}) · резолв={ok}{pulse}")
    return "\n".join(lines)


def build_context():
    """Система-промпт для мозга. Гарантия BR3: значений ключей НЕТ, только булевы."""
    _ensure_env()
    date_str = datetime.date.today().isoformat()
    ctx_key = bool(os.getenv("AGENTROUTER_API_KEY"))
    ctx_ym = bool(os.getenv("YANDEX_MARKET_API_KEY"))
    ctx_tg = bool(os.getenv("YM_TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN"))
    self_txt = ""
    if self_org is not None:
        try:
            self_txt = self_org.render()
        except Exception as e:
            self_txt = f"(самоосознание недоступно: {type(e).__name__})"
    staff_txt = "штаб-сводка недоступна (консоль не импортировалась)"
    if console is not None:
        try:
            buf = io.StringIO()
            txt = console.staff_summary(out=buf)   # StringIO → plain (BR14, без ANSI)
            if txt:
                staff_txt = txt.splitlines()[0]
        except Exception:
            staff_txt = "штаб-сводка недоступна (ошибка чтения)"
    action_list = "\n".join(
        f"  · {name} [{a['role']}] — {a['help']}" for name, a in ACTIONS.items())
    gloss_lines = "\n".join(f"  · {ph} — {d}" for ph, d in GLOSS)
    return (
        f"{IDENTITY_TEXT}\n{STYLE_TEXT}\n"
        "Ты = тело SOCC: знаешь доктрину сбыта MINT, донор-модель, законы L1–L14 и термины ниже.\n"
        "Задача — ИНИЦИИРОВАТЬ нужные процессы/циклы строкой [ДЕЙСТВИЕ] <имя> <аргументы> ТОЛЬКО из "
        "каталога ниже (dry/read — выполню сразу, write — спрошу у оператора). Если действие не "
        "нужно — просто ответь.\n"
        f"\nСегодня: {date_str}. Модель мозга: {os.getenv('ANTHROPIC_MODEL') or MODEL_DEFAULT}.\n"
        f"Ключи (только наличие): мозг={ctx_key}, ЯМ API={ctx_ym}, ТГ={ctx_tg}.\n"
        f"Мать-цикл по умолчанию: {STORE_DEFAULT}.\n"
        f"\n{DOCTRINE_TEXT}\n{DONOR_TEXT}\n{LAWS_CANON}\n{RULES_TEXT}\n"
        f"{LAWS_TEXT}\n{QUIET_HINT}\n"
        f"\nСЛОВАРЬ ТЕРМИНОВ (что такое пульс-1 / цикл-1 / мама / хеш / СВЕРКА / RUBICON):\n{gloss_lines}\n"
        f"\nРЕЕСТР ЦИКЛОВ (мама-наследование):\n{_cycle_short_state()}\n"
        f"\nШТАБ-СВОДКА (сколько ролей реально в штате, механически):\n{staff_txt}\n"
        f"\nСАМООСОЗНАНИЕ:\n{self_txt}\n"
        f"\nДОСТУПНЫЕ ДЕЙСТВИЯ (строгий allowlist):\n{action_list}\n"
        "\nПример строки запуска: [ДЕЙСТВИЕ] cycle_dry --store atlas-express-film   (сухо, 0₽, авто). "
        "Write-действие (cycle_live, new_cycle) НЕ запускай без слова оператора — предложи и жди."
    )


def _ask(text, history=None):
    """Модульный вызов мозга (тесты мокают эту)."""
    return brain_call(build_context(), text, history)


# ─────────────────────────────────────────────────────────────────────────────
#  ОФФЛАЙН-ОТВЕТ ИЗ ТЕЛА SOCC (голос-LLM молчит: пустой ответ/нет ключа). V2.
#  Сухо-авто живёт и тут: пульс-1/цикл по магазину → сам отдаёт [ДЕЙСТВИЕ] cycle_dry.
# ─────────────────────────────────────────────────────────────────────────────

def _slug_in_text(low):
    """Магазин из манифеста, упомянутый в тексте (самые длинные слаги раньше)."""
    cands = []
    if cycle1 is not None:
        try:
            cands = list(cycle1.list_cycles().keys())
        except Exception:
            pass
    cands.append(STORE_DEFAULT)
    for s in sorted(set(cands), key=len, reverse=True):
        if s and s.lower() in low:
            return s
    return None


def _state_note():
    """Одна строка «где мы сейчас» для оффлайн-ответа (никогда не пуста)."""
    who = ""
    if cycle1 is not None:
        try:
            reg = cycle1.list_cycles()
            if reg:
                cur = [s for s in (STORE_DEFAULT,) if s in reg] or list(reg)
                who = f"Магазин в работе: {cur[0]} · "
        except Exception:
            pass
    return (f"Статус: {who}реестр-мама = {STORE_DEFAULT}. Сухо/чтение — авто (0₽), "
            "write — по твоему слову. /help — команды.")


def _offline_answer(text):
    """Ответ из тела SOCC, когда голос-LLM вернул пустоту. НИКОГДА не пусто (BR11).

    Узнаёт термины (что такое пульс-1/цикл-1/мама/хеш/СВЕРКА…), различает донор-магазин и
    категорию, отвечает на «в работе», а сухой прогон цикла инициирует сам строкой [ДЕЙСТВИЕ].
    """
    low = " ".join((text or "").lower().replace("ё", "е").split())
    bits = []
    if any(w in low for w in ("привет", "здравствуй", "добрый день", "добрый вечер",
                              "как дела", "hi", "hello", "кто ты")):
        bits.append("Я УПРАВЛЯЮЩИЙ-МОЗГ SOCC-ЯМ — мета-цикл над органом MINT (сейчас на нём Яндекс "
                    "Маркет Экспресс, дальше Озон). Тело SOCC знаю (доктрина, законы L1–L14, термины); "
                    "сухие ходы запускаю сам, живьё — только по твоему слову. «меню» — навигатор, "
                    "текст — чат.")
    for marker, definition in GLOSS:
        if marker.replace("ё", "е") in low:
            bits.append(f"· {definition}")
    action = None
    if (any(w in low for w in ("запусти", "прогони", "гони", "сделай", "сделать", "давай",
                               "запустить", "прогнать", "инициируй", "покажи ход"))
            and any(w in low for w in ("цикл", "пульс", "ход", "прогон", "плёнк", "пленк",
                                       "film", "магазин"))):
        live = any(w in low for w in ("живьё", "живьем", "живой", "live", "commit",
                                      "вживую", "в живую"))
        store = _slug_in_text(low) or STORE_DEFAULT
        action = f"[ДЕЙСТВИЕ] {'cycle_live' if live else 'cycle_dry'} --store {store}"
    if action:
        bits.append(f"Инициирую по роли — {action}  (dry выполню сразу; live спрошу слово.)")
    bits.append(_state_note())
    return "\n".join(bits)


# ─────────────────────────────────────────────────────────────────────────────
#  МАМА-ХЭЛПЕРЫ ДВИЖКА (модульные обёртки для тестов)
# ─────────────────────────────────────────────────────────────────────────────

def _run_cycle(store_slug, dry=True, commit=False, verbose=False):
    if cycle1 is None:
        return {"verdict": "FAIL", "error": "движок ЦИКЛА-1 недоступен (import)"}
    return cycle1.run_cycle(store_slug, dry=dry, commit=commit, verbose=verbose)


def _add_cycle(profile):
    if cycle1 is None:
        return False, "движок ЦИКЛА-1 недоступен (import)"
    return cycle1.add_store(profile)


def _capture(fn):
    """Выполнить с захватом stdout (результат-текст возвращается, не печатается)."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            res = fn()
        return res, buf.getvalue()
    except Exception as e:
        return {"verdict": "FAIL", "error": f"{type(e).__name__}: {e}"}, buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
#  ИСПОЛНИТЕЛИ ДЕЙСТВИЙ (каждый: args → (label, text)); write гейт в run_action
# ─────────────────────────────────────────────────────────────────────────────

def _pick_store(args):
    v = (args or {}).get("store") or (args or {}).get("cycle") or STORE_DEFAULT
    return _clean_slug(v)


_NODE_DOT = {"PASS": "✓", "DRY": "◌", "SKIP": "–", "FAIL": "✗"}


def _cycle_card(store, res, dry):
    """Компактная карточка прогона из results[]: строка на узел + вердикт.

    ИЛЯХОВ: без ЗАЛИВ-листа цен (node_fill в note несёт _summary по каждой карточке) —
    у не-FAIL узлов ноты не показываем вовсе, FAIL несёт причину (обрезанно, L12 честно).
    """
    v = res.get("verdict")
    results = res.get("results") or []
    if not results:
        return None                       # нет узлов — уйдём на честный fallback
    card = []
    for r in results:
        mark = _NODE_DOT.get(r.get("verdict"), "·")
        node = (r.get("node") or "?").ljust(10)
        line = f"  {mark} {node}"
        ms = r.get("ms")
        if isinstance(ms, (int, float)):
            line += f"  {ms:>5.0f}мс"
        if r.get("verdict") == "FAIL":
            line += "  " + _snip(r.get("note") or "упало без причины", 170)
        card.append(line)
    if v == "PASS":
        card.append("■ ЦИКЛ-1 ЗАКРЫТ · все узлы PASS с доказательством · артефакт на витрине")
    elif v == "DRY_OK":
        card.append("■ DRY-ПРОХОД ЧИСТ · узлы готовы · живьё — по твоему слову (0₽ наружу)")
    elif v == "FAIL":
        fails = [r for r in results if r.get("verdict") == "FAIL"]
        node = (fails[0].get("node") if fails else "?") or "?"
        card.append(f"■ ЦИКЛ ОСТАНОВЛЕН на «{node}» — чинить и перезапускать. Без fake pass (L12).")
    else:
        card.append(f"■ вердикт: {v}")
    hsh = res.get("hash")
    if hsh:
        card.append(f"  хеш {hsh} · узлов {len(results)}")
    return "\n".join(card)


def _h_cycle(args, dry):
    store = _pick_store(args)
    res, _out = _capture(lambda: _run_cycle(store, dry=dry, commit=not dry, verbose=False))
    v = res.get("verdict")
    head = f"ЦИКЛ {store} · {v}" if v else "ЦИКЛ FAIL"
    body = _cycle_card(store, res, dry)
    if not body:
        hsh = res.get("hash")
        body = (res.get("error") or f"вердикт {v}") + (f" · хеш {hsh}" if hsh else "")
    return head, body


def _h_plannerka(args):
    store = _pick_store(args)
    if cycle1 is None:
        return "ПУЛЬС", "движок недоступен (import)"
    p = cycle1.plannerka_read(store)
    if not p:
        return "ПУЛЬС", f"пульса у «{store}» ещё нет — запусти cycle_dry, соберём первый."
    return "ПУЛЬС", (f"{store} · {p.get('date')}\n"
                     f"  вчера узлов: {p.get('yesterday_runs')} · вердикты: {p.get('yesterday_verdicts')}\n"
                     f"  сегодня: {p.get('run_verdicts')} · артефактов-СВЕРКА PASS: {p.get('artifacts')}\n"
                     f"  по узлам вчера: {p.get('by_node') or {}}")


def _h_self(args):
    if self_org is None:
        return "САМО", "самоосознание недоступно (import)"
    try:
        return "САМО", self_org.render()
    except Exception as e:
        return "САМО", f"{type(e).__name__}: {e}"


def _h_registry(args):
    if cycle1 is None:
        return "РЕЕСТР", "движок недоступен (import)"
    return "РЕЕСТР", _cycle_short_state()


def _h_tasks(args):
    """ЦИКЛ-ДНЯ над реестром заданий: планёрка / форма / диспетчер. Read 0₽.
    form --commit — единственный write = локальный реестр (файл, НЕ сеть) — ТОЛЬКО по слову
    оператора (args['confirmed'] ставит REPL после _confirm; авто-[ДЕЙСТВИЕ] мозга его не имеет)."""
    a = args or {}
    if cyc_day is None:
        return "ЗАДАНИЯ", "ЦИКЛ-ДНЯ недоступен (import)"
    store = a.get("store") or None
    if store in ("да", "нет", "yes", "no", "y", "n", "д", "1", "0"):
        store = None  # случайный позиционный «да» ≠ магазин (gotcha _tokens_to_args)
    if a.get("dispatch"):
        lines = cyc_day.dispatch(cycle_dry=bool(a.get("cycle_dry")), store=store)[1]
        return "ДИСПЕТЧЕР", "\n".join(lines)
    if a.get("form"):
        commit = bool(a.get("commit"))
        if commit and not a.get("confirmed"):
            return "НУЖНО СЛОВО", ("«tasks --form --commit» пишет локальный реестр заданий "
                                   "(файл, НЕ сеть). Подтверди [да/нет]: форма сама не пишет (CD2).")
        lines = cyc_day.form(commit=commit, store=store)[1]
        return "ФОРМА", "\n".join(lines)
    return "ЗАДАНИЯ", "\n".join(cyc_day.plannerka_text(store=store))


def _h_new_cycle(args):
    a = args or {}
    slug = a.get("slug") or a.get("s")
    builder = a.get("builder") or a.get("b")
    donor = a.get("donor_category") or a.get("donor")
    try:
        markup = float(a.get("markup") or a.get("m") or 0)
    except (TypeError, ValueError):
        return "НОВЫЙ-ЦИКЛ", "markup должен быть числом (цена = закупка × markup)"
    try:
        stock = int(float(a.get("stock_count") or a.get("stock") or 0))
    except (TypeError, ValueError):
        return "НОВЫЙ-ЦИКЛ", "stock_count должен быть целым (остаток на витрине)"
    if not slug or not builder or not donor or markup <= 0 or stock < 0:
        return ("НОВЫЙ-ЦИКЛ",
                "нужны все: <slug> <builder=film|box> <donor_category> <markup> <stock_count>")
    profile = {"slug": slug, "builder": builder, "donor_category": donor,
               "markup": markup, "stock_count": int(stock)}
    if a.get("mother"):
        profile["mother"] = a["mother"]
    if a.get("builder_slug"):
        profile["builder_slug"] = a["builder_slug"]
    ok, why = _add_cycle(profile)
    return ("НОВЫЙ-ЦИКЛ", "✓ " + why if ok else f"✗ {why} (манифест НЕ тронут)")

_HANDLERS = {
    "cycle_dry": lambda a: _h_cycle(a, dry=True),
    "cycle_live": lambda a: _h_cycle(a, dry=False),
    "plannerka": _h_plannerka,
    "self": _h_self,
    "registry": _h_registry,
    "tasks": _h_tasks,
    "new_cycle": _h_new_cycle,
}


def run_action(name, args=None, confirmed=False):
    """Выполнить действие из каталога с write-гейтом (BR1). → (label, text)."""
    spec = ACTIONS.get(name)
    if spec is None:
        return "ОТКАЗ", f"действие «{name}» вне каталога (allowlist, BR2)"
    if spec["role"] == "write" and not confirmed:
        return "НУЖНО СЛОВО", (f"«{name}» — write-действие. Подтверди [да/нет]: "
                               f"RUBICON — мозг сам не пишет.")
    handler = _HANDLERS.get(name)
    try:
        return handler(args or {})
    except Exception as e:
        return "ОШИБКА", f"{type(e).__name__}: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  СЕМАНТИЧЕСКИЙ РАЗБОР ОТВЕТА МОЗГА (BR2: строгий allowlist)
# ─────────────────────────────────────────────────────────────────────────────

def _split_argv(s):
    try:
        return shlex.split(s)
    except Exception:
        return None


def _clean_slug(v):
    """Мозг может поставить знак после слага («atlas-express-film.») → срезаем окружающую пунктуацию."""
    if v is None:
        return None
    return str(v).strip().strip(" .!?;,:»«'\"()[]")

_SLUG_KEYS = ("store", "cycle", "slug", "mother", "builder", "builder_slug", "donor_category")


def _tokens_to_args(tokens):
    """Позиционные/флаговые токены → dict args (--store X, свободные → slug/поля по порядку)."""
    args, pos = {}, []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--") and len(t) > 2:
            key = t[2:]
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                args[key] = tokens[i + 1]
                i += 2
            else:
                args[key] = True
                i += 1
        else:
            pos.append(t)
            i += 1
    if pos:
        # для store-действий первый позиционный = магазин; для new_cycle — поля по порядку
        args.setdefault("store", pos[0])
        args.setdefault("slug", pos[0])
        if len(pos) > 1:
            args.setdefault("builder", pos[1])
        if len(pos) > 2:
            args.setdefault("donor_category", pos[2])
        if len(pos) > 3:
            args.setdefault("markup", pos[3])
        if len(pos) > 4:
            args.setdefault("stock_count", pos[4])
    for k in _SLUG_KEYS:
        if k in args and not isinstance(args[k], bool):
            args[k] = _clean_slug(args[k])
    return args


def plan_action(line, confirmed=False):
    """Разобрать '[ДЕЙСТВИЕ] <имя> <аргументы>' из ответа мозга.

    Возвращает dict:
      {ok:False, why}                      — нет [ДЕЙСТВИЕ] или имя вне каталога;
      {ok:True, name, role, args, execute} — execute=False означает «нужно слово оператора»
                                              (write без confirmed, BR1).
    """
    if not line:
        return {"ok": False, "why": "нет строки для разбора"}
    idx = line.find("[ДЕЙСТВИЕ]")
    if idx < 0:
        return {"ok": False, "why": "в ответе нет [ДЕЙСТВИЕ]"}
    rest = line[idx + len("[ДЕЙСТВИЕ]"):].strip()
    rest = rest.split("\n", 1)[0].strip()   # только строка действия — проза после \n в args не идёт
    toks = _split_argv(rest)
    if not toks:
        return {"ok": False, "why": "пусто после [ДЕЙСТВИЕ]"}
    name = ALIASES.get(toks[0].lower(), toks[0].lower())
    if name not in ACTIONS:
        return {"ok": False,
                "why": f"действие «{toks[0]}» вне каталога (доступно: {', '.join(ACTIONS)})"}
    args = _tokens_to_args(toks[1:])
    role = ACTIONS[name]["role"]
    execute = (role in ("read", "dry")) or (role == "write" and confirmed)
    return {"ok": True, "name": name, "role": role, "args": args, "execute": execute}


# ─────────────────────────────────────────────────────────────────────────────
#  REPL «как в Клауде» — команды видно, интерактив, выбор, подтверждение write
# ─────────────────────────────────────────────────────────────────────────────

HELP_TEXT = """\
SOCC-ЯМ · УПРАВЛЯЮЩИЙ-МОЗГ над MINT (чат + меню).

  «меню»      навигатор: магазины · циклы · реестр · новый магазин · карта
  /органы     органы/роли + доктрина + донор-модель (тело SOCC)
  /само       самоосознание управляющего (read)
  /мама · /реестр   реестр циклов: кто от какой мамы наследует кабинет (read)
  /пульс [store]    планёрка магазина (read; по умолчанию мать-цикл)
  /пульс-1 [store]  ПРОГОН ЦИКЛА-1 по магазину (узлы+правила), сухо-авто 0₽
  /задания [--form] [--dispatch]   ЦИКЛ-ДНЯ: открытые задания по важности + владелец (read)
                     --form: что сформируется из наблюдений · --form --commit: записать реестр
                     (файл — спрошу) · --dispatch: разбор «кто исполнит» (read)
  /цикл сухо [store]   сухой ход ЦИКЛА-1, 0₽ (авто, read/dry)
  /цикл живьё [store]  ЖИВОЙ ход (write — спрошу «да/нет»)
  /новый-цикл <slug> <builder> <донор-категория> <markup> <stock> [--mother M]
                     новый магазин в манифест (write — спрошу «да/нет»)
  /лог         сегодняшний сеанс (сессия-лог)
  /мозг <текст>  прямой вопрос мозгу
  /выход · Ctrl-D   выйти
Простой текст («привет», «запусти цикл плёнки сухо», «что такое пульс-1») идёт мозгу;
если он ответит [ДЕЙСТВИЕ] … — dry/read выполню сразу, write спрошу слово оператора.
Пустой ответ голоса-LLM не тупик: отвечаю из тела SOCC и сухой ход всё равно инициирую."""


def _confirm(prompt, stdin, out):
    out.write(prompt + "  [да/нет]: ")
    out.flush()
    if stdin is not None:
        ans = (stdin.readline() or "").strip().lower()
    else:
        try:
            ans = input("  [да/нет]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""
    return ans in ("да", "yes", "y", "д", "1")


# ─────────────────────────── V3 · меню-навигатор + спиннер ───────────────────────────

_NEXT_HINT = "→ дальше: «меню» — навигатор · просто напиши — чат · /выход"


def _next_hint_line(out):
    return _dim(out, "  " + _NEXT_HINT)


def _with_spinner(out, label, fn):
    """«думаю…»-спиннер — только на живом tty (BR7/BR11 в StringIO не ловят мусор)."""
    if not _tty(out):
        return fn()
    stop = threading.Event()
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    pos = [0]

    def _spin():
        while not stop.is_set():
            ch = frames[pos[0] % len(frames)]
            pos[0] += 1
            out.write("\r  " + _col(out, "DIM", f"{ch} {label}  "))
            out.flush()
            stop.wait(0.08)

    th = threading.Thread(target=_spin, daemon=True)
    th.start()
    try:
        return fn()
    finally:
        stop.set()
        th.join(timeout=1.0)
        out.write("\r" + " " * 34 + "\r")
        out.flush()


def _short_reply(reply, max_lines=9):
    """Показ-версия ответа: голова + [ДЕЙСТВИЕ]-строка (полный текст — в истории/плане)."""
    if not reply:
        return reply
    lines = [ln for ln in str(reply).splitlines() if ln.strip()]
    if len(lines) <= max_lines:
        return str(reply).rstrip()
    head = lines[:max_lines]
    acts = [ln for ln in lines[max_lines:] if "[ДЕЙСТВИЕ]" in ln]
    return "\n".join(head + acts[:1]).rstrip() + "\n…"


def _prompt(stdin, out, text):
    out.write(text)
    out.flush()
    if stdin is not None:
        v = stdin.readline()
    else:
        try:
            v = input()
        except (EOFError, KeyboardInterrupt):
            v = ""
    return (v or "").strip()


def _cycles_list():
    if cycle1 is None:
        return {}
    try:
        return cycle1.list_cycles() or {}
    except Exception:
        return {}


_MENU_W = 46


def _menu_block(out, title, items):
    """Карточка меню SOCC: левая рейка + шапка/подвал — минимализм ЛЕБЕДЕВ, без правого края.
    Пункт = (номер, текст) или (номер, текст, деталь) — деталь второй строкой, приглушена."""
    width = max(_MENU_W, len(title) + 10)
    print("  ╭─ " + _col(out, "CY", title) + _dim(out, " " + "─" * max(1, width - len(title) - 3)), file=out)
    for item in items:
        num, txt = item[0], item[1]
        n = _col(out, "CY", str(num)) if str(num).strip() else " "
        print("  │  " + n + _dim(out, " · ") + txt, file=out)
        if len(item) > 2 and item[2]:
            print("  │     " + _dim(out, item[2]), file=out)
    print("  ╰" + _dim(out, "─" * (width + 2)), file=out)


def _cycle_detail_text(st, inf):
    """Деталь цикла для списка: кабинет (свой/мама) + markup/остаток + свежий пульс."""
    parts = []
    if inf.get("mother"):
        parts.append(f"кабинет мамы «{inf['mother']}»")
    elif inf.get("business_id"):
        parts.append(f"кабинет {inf['business_id']}")
    if inf.get("markup") is not None:
        parts.append(f"×{inf['markup']}")
    if inf.get("stock_count") is not None:
        parts.append(f"ост {inf['stock_count']}")
    if cycle1 is not None:
        try:
            p = cycle1.plannerka_read(st)
        except Exception:
            p = None
        if p and p.get("date") == datetime.date.today().isoformat() and p.get("run_verdicts"):
            rv = p.get("run_verdicts")
            compact = " ".join(f"{k}{v}" for k, v in rv.items()) if isinstance(rv, dict) else str(rv)
            parts.append(f"пульс {p.get('date')} {compact} · арт {p.get('artifacts', 0)}")
    return " · ".join(parts)


def _show_menu(out, nav):
    reg = _cycles_list()
    stores = sorted(reg)
    print(file=out)
    lvl = nav["level"]
    if lvl == 0:
        # КОРЕНЬ = список циклов MINT: каждый цикл — пункт, «создать цикл», 0 — в чат
        items = []
        for i, s in enumerate(stores, 1):
            inf = reg.get(s) or {}
            main = f"{s} — {inf.get('builder') or '?'} · донор {inf.get('donor_category') or '?'}"
            num = str(i)
            live = False
            if cycle1 is not None:
                try:
                    p = cycle1.plannerka_read(s)
                except Exception:
                    p = None
                live = bool(p and p.get("date") == datetime.date.today().isoformat()
                            and p.get("run_verdicts"))
            if live:
                num = f"★{i}"
            items.append((num, main, _cycle_detail_text(s, inf)))
        if stores:
            items.append((str(len(stores) + 1), "создать цикл (мастер)"))
        else:
            items.append(("1", "создать первый цикл (мастер)"))
        items.append((str(len(stores) + 2), "ШТАБ — 13 ролей · занятость · совесть"))
        items.append((str(len(stores) + 3), "ДЕЛО — KPI · день · табель · артефакты"))
        items.append(("0", "в чат"))
        _menu_block(out, "SOCC-ЯМ · циклы MINT", items)
    elif lvl == 10:   # ШТАБ-дайв: лист 13 ролей (цифра → карточка)
        if console is None:
            print("  " + _dim(out, "КОНСОЛЬ-ЯМ недоступен (import упал)"), file=out)
        else:
            try:
                body = console.staff_summary(out=out)
            except Exception as _e:
                body = f"(штаб-сводка недоступна: {_e})"
            for ln in str(body).splitlines():
                print("  " + ln, file=out)
        _menu_block(out, "ШТАБ · роль — цифра 1–13", [("0", "назад к циклам")])
    elif lvl == 11:   # карточка одной роли
        rk = nav.get("store")
        if console is None:
            print("  " + _dim(out, "КОНСОЛЬ-ЯМ недоступен (import упал)"), file=out)
        else:
            try:
                body = console.role_card(rk or "", out=out)
            except Exception as _e:
                body = f"(карточка роли недоступна: {_e})"
            for ln in str(body).splitlines():
                print("  " + ln, file=out)
        _menu_block(out, f"роль · {rk or '?'}", [("0", "назад к штабу")])
    elif lvl == 20:   # ДЕЛО: read-отчёты (0₽)
        _menu_block(out, "SOCC-ЯМ · ДЕЛО", [
            ("1", "KPI — день / неделя / месяц"),
            ("2", "ДЕНЬ — последний снимок журнала"),
            ("3", "ТАБЕЛЬ — кто работал сегодня"),
            ("4", "АРТЕФАКТЫ — матрица · библиотека · точки"),
            ("5", "АВТОПИЛОТ — хвост"),
            ("6", "ДЕЛО одним листом (всё выше)"),
            ("0", "назад к циклам"),
        ])
    else:  # lvl 1 — внутри цикла
        st = nav.get("store") or STORE_DEFAULT
        _menu_block(out, f"цикл · {st}", [
            ("1", "ПУЛЬС (чтение)"),
            ("2", "ЦИКЛ сухо — 0₽, авто"),
            ("3", "ЦИКЛ живьё — write, по слову"),
            ("4", "КАРТОЧКА цикла"),
            ("0", "назад к циклам"),
        ])
    print(_dim(out, "  цифра — выбрать · текст — чат · «меню» — сюда"), file=out)


def _pulse_all_text():
    reg = _cycles_list()
    if not reg:
        return "манифест пуст — «меню → 5» создаст первый цикл (или «запусти цикл плёнки сухо»)."
    lines = []
    for s in sorted(reg):
        p = None
        if cycle1 is not None:
            try:
                p = cycle1.plannerka_read(s)
            except Exception:
                p = None
        if not p:
            lines.append(f"  {s:<20} пульса нет — «цикл сухо» соберёт первый (0₽)")
        else:
            lines.append(f"  {s:<20} {p.get('date', '?')} · сегодня {p.get('run_verdicts', '?')} · "
                         f"арт {p.get('artifacts', '?')} · вчера {p.get('yesterday_verdicts', '?')}")
    return "\n".join(lines)


def _store_card_text(st):
    reg = _cycles_list()
    inf = reg.get(st) or {}
    if not inf:
        return f"«{st}» нет в манифесте MINT."
    mom = inf.get("mother")
    cab = f"кабинет мамы «{mom}»" if mom else "свой кабинет"
    return (f"  {st} · builder={inf.get('builder')} · донор={inf.get('donor_category')}\n"
            f"  markup=×{inf.get('markup')} · остаток={inf.get('stock_count')} · {cab}\n"
            "  ЦИКЛ-1: ДОНОР→СБОРКА→ЗАЛИВ→ВИТРИНА→ОСТАТКИ→СВЕРКА→ПЛАНЁРКА\n"
            "  артефакт цикла = товар на витрине (PUBLISHED + остаток + «Без бренда»)")


def _wizard_new_cycle(out, stdin):
    print(_dim(out, "новый магазин-цикл — 5 полей. Кабинет наследуется от мамы "
                    "(по умолчанию atlas-express-film)."), file=out)
    slug = _prompt(stdin, out, "  slug (лат. дефис): ")
    if not slug:
        print(_dim(out, "отменено (пусто)."), file=out)
        return
    builder = _prompt(stdin, out, "  builder (film|box): ") or "film"
    donor = _prompt(stdin, out, "  донор-категория (путь у донора): ")
    markup = _prompt(stdin, out, "  markup (×): ")
    stock = _prompt(stdin, out, "  остаток (шт): ")
    if not (donor and markup and stock):
        print(_dim(out, "отменено (поля не заполнены)."), file=out)
        return
    args = {"slug": slug, "builder": builder, "donor_category": donor,
            "markup": float(markup), "stock_count": int(stock)}
    if _confirm(f"пишу «{slug}» в манифест MINT. Подтверди", stdin, out):
        label, text = run_action("new_cycle", args, confirmed=True)
        _print_result(label, text, out)
    else:
        print(_dim(out, "отменено (RUBICON)."), file=out)


def _menu_action(out, stdin, nav, num):
    reg = _cycles_list()
    stores = sorted(reg)
    lvl = nav["level"]
    if lvl == 0:
        # корень = список циклов: 1..N циклы · N+1 создать · N+2 ШТАБ · N+3 ДЕЛО · 0 чат
        if num == "0":
            nav["mode"] = "chat"
            nav["level"] = 0
            nav["store"] = None
            print(_dim(out, "  в чат. «меню» вернёт список циклов."), file=out)
            return
        try:
            i = int(num)
        except ValueError:
            print(_dim(out, f"  цифра 1–{len(stores) or 1} — цикл · 0 — чат"), file=out)
            return
        if 1 <= i <= len(stores):
            nav["level"] = 1
            nav["store"] = stores[i - 1]
            return
        if i == len(stores) + 1:
            _wizard_new_cycle(out, stdin)
            return
        if i == len(stores) + 2:
            nav["level"] = 10
            nav["store"] = None
            return
        if i == len(stores) + 3:
            nav["level"] = 20
            nav["store"] = None
            return
        print(_dim(out, f"  нет пункта «{num}»"), file=out)
        return
    # lvl 1 — внутри цикла
    if lvl == 1:
        st = nav.get("store") or STORE_DEFAULT
        if num == "0":
            nav["level"] = 0
            nav["store"] = None
            return
        if num == "1":
            label, text = run_action("plannerka", {"store": st})
        elif num == "2":
            label, text = run_action("cycle_dry", {"store": st})
        elif num == "3":
            if not _confirm(f"«{st}» пишет в кабинет (live). Подтверди", stdin, out):
                print(_dim(out, "  отменено (RUBICON)."), file=out)
                return
            label, text = run_action("cycle_live", {"store": st}, confirmed=True)
        elif num == "4":
            print(_store_card_text(st), file=out)
            return
        else:
            print(_dim(out, f"  нет пункта «{num}»"), file=out)
            return
        _print_result(label, text, out)
        return
    # ШТАБ-дайв и ДЕЛО (КОНСОЛЬ-ЯМ, read 0₽)
    if lvl in (10, 11, 20):
        if num == "0":
            if lvl == 11:            # карточка роли → к штабу
                nav["level"] = 10
            else:                    # штаб/дело → к списку циклов
                nav["level"] = 0
            nav["store"] = None
            return
        if console is None:
            print(_dim(out, "  КОНСОЛЬ-ЯМ недоступен (import упал) — read-кабинет молчит."), file=out)
            return
        if lvl == 10:                # цифра → карточка роли
            try:
                ridx = int(num)
            except ValueError:
                ridx = 0
            try:
                rk = console.roles_index()[ridx - 1]["key"] if 1 <= ridx <= len(console.roles_index()) else None
            except Exception:
                rk = None
            if rk:
                nav["level"] = 11
                nav["store"] = rk
                return
            print(_dim(out, f"  нет роли «{num}» (1–13)"), file=out)
            return
        if lvl == 20:                # read-отчёт — печатаем и остаёмся
            try:
                if num == "1":
                    text = console.kpi_text(out=out)
                elif num == "2":
                    text = console.day_card(out=out)
                elif num == "3":
                    text = console.tabel_today_text(out=out)
                elif num == "4":
                    text = console.artifacts_text(out=out)
                elif num == "5":
                    text = console.autopilot_tail(out=out)
                elif num == "6":
                    text = console.deal_text(out=out)
                else:
                    print(_dim(out, f"  нет пункта «{num}» (1–6)"), file=out)
                    return
            except Exception as _e:
                text = f"(отчёт упал: {_e})"
            _print_console(out, text)
            return
        print(_dim(out, f"  нет пункта «{num}»"), file=out)
        return


def _print_banner(out):
    line = "═" * 62
    model = os.getenv("ANTHROPIC_MODEL") or MODEL_DEFAULT
    print(file=out)
    print("  " + _col(out, "CY", line), file=out)
    print("  " + _b(out, _col(out, "CY", "УПРАВЛЯЮЩИЙ-МОЗГ · SOCC-ЯМ над MINT")), file=out)
    print("  " + _dim(out, f"мозг {model} · чат+меню · сухо-авто 0₽ · RUBICON · ЯМ жив — Озон следующий"), file=out)
    print("  " + _col(out, "CY", line), file=out)
    print(file=out)


def _log_tail(out, n=18):
    p = _session_path()
    if p is None or not p.exists():
        print(_dim(out, "  сессия-лог пуст (пишется на живом терминале)."), file=out)
        return
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        print(_dim(out, f"  лог не прочитан: {e}"), file=out)
        return
    print(file=out)
    print(_dim(out, f"  сеанс {p.name} · {len(lines)} строк · хвост:"), file=out)
    for ln in lines[-n:]:
        print("  " + ln, file=out)
    print(file=out)


def _prompt_text(nav):
    if nav["mode"] != "menu":
        return "управляющий> "
    lvl = nav["level"]
    if lvl == 1:
        return f"цикл:{nav.get('store')}> "
    if lvl == 10:
        return "штаб> "
    if lvl == 11:
        return f"роль:{nav.get('store')}> "
    if lvl == 20:
        return "дело> "
    return "циклы> "


def _handle(line, out, stdin, history):
    """Обработать одну строку REPL. Возвращает True = продолжать, False = выйти."""
    line = line.strip()
    if not line:
        return True
    low = line.lower()
    if low in ("/выход", "/quit", "/exit", "exit", "quit"):
        return False
    if low == "/help":
        print(HELP_TEXT, file=out)
        return True
    if low.startswith("/лог"):
        _log_tail(out)
        return True

    if low == "/органы":
        print(_organs_text(), file=out)
        return True
    # КОНСОЛЬ-ЯМ · read-кабинет ШТАБ/ДЕЛО (0₽, только чтение)
    if console is not None:
        if low in ("/штаб", "/shtab", "/staff"):
            _print_console(out, console.staff_summary(out=out))
            return True
        if low.startswith("/роль"):
            rest = line.split(None, 1)[1] if " " in line else ""
            _print_console(out, console.role_card(rest, out=out))
            return True
        if low in ("/kpi", "/кпи"):
            _print_console(out, console.kpi_text(out=out))
            return True
        if low.startswith("/день"):
            _print_console(out, console.day_card(out=out))
            return True
        if low.startswith("/табель"):
            window = "all" if ("--все" in line or "-все" in line) else "today"
            _print_console(out, console.tabel_text(out=out,
                                                   role=_console_role_arg(line),
                                                   window=window))
            return True
        if low.startswith("/артефакты") or low.startswith("/artefakty"):
            _print_console(out, console.artifacts_text(out=out))
            return True
        if low.startswith("/авто") or low.startswith("/avto"):
            _print_console(out, console.autopilot_tail(out=out))
            return True
        if low in ("/дело", "/delo", "/deal"):
            _print_console(out, console.deal_text(out=out))
            return True
    if low.startswith("/само"):
        label, text = run_action("self", {})
        _print_result(label, text, out)
        return True
    if low.startswith("/мама") or low.startswith("/реестр") or low.startswith("/циклы"):
        label, text = run_action("registry", {})
        _print_result(label, text, out)
        return True
    # /пульс-1 [store] — ПРОГОН цикла по магазину (узлы+правила), сухо-авто. Отличается от /пульс (чтение).
    if low.startswith("/пульс-1") or low.startswith("/цикл-1"):
        rest = line.split(None, 1)[1] if " " in line else ""
        store = _clean_slug(rest) if rest else STORE_DEFAULT
        label, text = run_action("cycle_dry", {"store": store})
        _print_result(label, text, out)
        return True
    if low.startswith("/пульс"):
        args = _cmd_args(line, low)
        label, text = run_action("plannerka", {"store": args.get("store") or STORE_DEFAULT})
        _print_result(label, text, out)
        return True

    # /задания — ЦИКЛ-ДНЯ: планёрка заданий (read) · --form показать · --form --commit записать
    # реестр (файл, спрошу слово) · --dispatch разбор «кто исполнит» (read)
    if low.startswith("/задания") or low.startswith("/задачи") or low.startswith("/дела"):
        args = _cmd_args(line, low)
        if args.get("form") and args.get("commit") and not args.get("confirmed"):
            if not _confirm("форма пишет локальный реестр заданий (файл). Подтверди", stdin, out):
                print("  отменено.", file=out)
                return True
            args["confirmed"] = True
        label, text = run_action("tasks", args)
        _print_result(label, text, out)
        return True

    # /цикл сухо|живьё [store]
    if low.startswith("/цикл"):
        parts = line.split(None, 2)
        mode = (parts[1] if len(parts) > 1 else "сухо").lower()
        store = parts[2].strip() if len(parts) > 2 else STORE_DEFAULT
        if mode in ("живьё", "живьем", "живой", "live", "commit"):
            if not _confirm("«cycle_live» пишет в кабинет. Подтверди", stdin, out):
                print("  отменено (RUBICON: write только по слову).", file=out)
                return True
            label, text = run_action("cycle_live", {"store": store}, confirmed=True)
        else:
            label, text = run_action("cycle_dry", {"store": store})
        _print_result(label, text, out)
        return True
    if low.startswith("/новый-цикл") or low.startswith("/new-cycle"):
        line2 = line.split(None, 1)[1] if " " in line else ""
        args = _tokens_to_args(_split_argv(line2) or [])
        if not _confirm("новый магазин пишется в манифест. Подтверди", stdin, out):
            print("  отменено.", file=out)
            return True
        label, text = run_action("new_cycle", args, confirmed=True)
        _print_result(label, text, out)
        return True
    if low.startswith("/мозг"):
        text = line.split(None, 1)[1] if " " in line else "привет"
        return _brain_turn(text, out, stdin, history)
    if low.startswith("/"):
        print(f"  неизвестная команда: {line}  (/help)", file=out)
        return True

    # простой текст → мозг; если он ответит [ДЕЙСТВИЕ] — исполним по роли
    return _brain_turn(line, out, stdin, history)


def _cmd_args(line, low=None):
    """Хвост строки после команды → dict args (--store X, позиционные → slug).

    Срез по ПЕРВОМУ токену (команде). ВАЖНО: старый код резал по len(low), а low = вся
    lower-строка → хвост всегда пустой (store/флаги не доходили). Чиним здесь единым местом."""
    rest = line.split(None, 1)[1] if " " in line.strip() else ""
    return _tokens_to_args(_split_argv(rest) or [])


def _organs_text():
    if cycle1 is None:
        return "движок ЦИКЛА-1 недоступен (import)"
    return ("Органы, которые мозг инициирует:\n"
            f"  · ЦИКЛ-1 движок (ymarket_cycle1_v1): магазин по умолчанию {STORE_DEFAULT} — "
            "ДОНОР→СБОРКА→ЗАЛИВ→ВИТРИНА→ОСТАТКИ→СВЕРКА→ПЛАНЁРКА; тихий сухой ход 0₽.\n"
            "  · УПРАВЛЯЮЩИЙ-МОЗГ (я): тело SOCC (доктрина/законы/термины), self, реестр, разговор.\n"
            "  · Реестр мамы: [ДЕЙСТВИЕ] new_cycle … объявляет mother и наследует кабинет — "
            "системе пофиг какой API.\n"
            f"\n{DOCTRINE_TEXT}\n{DONOR_TEXT}\n"
            "\nРОЛИ/ОРГАНЫ ARBITER: ГОЛОВА (шорт-лист), ТОВАРОВЕД, КАТЕГОРИЙЩИК (донор→партия), "
            "ЦЕНОВИК/ОЧКИ (×markup), СКЛАДОВЩИК (правда остатка), ДИСПЕТЧЕР (60 мин), КОНТРОЛЁР (index), "
            "ТРЕНД-СКАУТ, СТРАТЕГ, СКАУТ РОСТА, фото-орган (hunter/pipeline/forge/publish), мост.\n"
            "Запуск действий — строкой [ДЕЙСТВИЕ] из каталога; сухо/read авто, write — по слову оператора.")


def _turn_reply(reply, text, out, stdin, history):
    """Общий путь ответа (LLM или оффлайн-тело): история + сессия-лог + показ (коротко) + [ДЕЙСТВИЕ]."""
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})
    del history[:-8]  # держим недавний хвост разговора
    if stdin is None:  # живой терминал → сессия-лог (тесты не пишут на диск)
        _log(f"[оператор] {_snip(text, 300)}")
        _log(f"[socc-ям]   {_snip(reply, 600)}")
    print(f"\n  {_short_reply(reply)}\n", file=out)
    parsed = plan_action(reply)
    if not parsed.get("ok"):
        print(_next_hint_line(out), file=out)
        return True
    if parsed["execute"]:
        label, res_txt = run_action(parsed["name"], parsed["args"])
        _print_result(label, res_txt, out)
    else:
        # write-действие: спросить слово оператора (BR1)
        if _confirm(f"«{parsed['name']}» — write. Запустить", stdin, out):
            label, res_txt = run_action(parsed["name"], parsed["args"], confirmed=True)
            _print_result(label, res_txt, out)
        else:
            print(_dim(out, "  отменено (RUBICON: write только по слову оператора)."), file=out)
    print(_next_hint_line(out), file=out)
    return True


def _brain_turn(text, out, stdin, history):
    ans = _with_spinner(out, "думаю…", lambda: _ask(text, history))
    if not ans.get("ok"):
        if ans.get("empty"):
            # голос-LLM молчит → отвечаю из тела SOCC, сухо-авто живёт (BR11)
            print("\n  " + _dim(out, "(голос-LLM вернул пустой ответ — отвечаю из тела SOCC)") + "\n", file=out)
            return _turn_reply(_offline_answer(text), text, out, stdin, history)
        print(f"\n  {ans.get('error', 'мозг недоступен')}\n", file=out)
        return True
    return _turn_reply(ans["text"], text, out, stdin, history)


def _print_result(label, text, out):
    """Карточка результата в каноне SOCC: ▶ <метка> окрашена (только tty), тело индентаётся."""
    l = label or ""
    head_col = "RE" if l.startswith(("ОТКАЗ", "ОШИБКА", "FAIL")) else (
        "YE" if l.startswith("НУЖНО СЛОВО") else "CY")
    print(f"\n  {_col(out, 'B', '▶')} {_col(out, head_col, l)}\n", file=out)
    body = (text or "").strip()
    if body:
        for ln in body.splitlines():
            print(f"    {ln}", file=out)
    print(file=out)


def _print_console(out, text):
    """Тело read-отчёта КОНСОЛЬ-ЯМ (текст уже самокрашен, у карточки нет ▶-метки)."""
    print(file=out)
    for ln in str(text or "").rstrip().splitlines():
        print("  " + ln, file=out)
    print(file=out)


def _console_role_arg(line):
    """Аргумент «--роль X» строки вида «/табель --роль ГОЛОВА --все» → X (или None)."""
    for tok in ("--роль", "--role", "--rol"):
        if tok in line:
            rest = line.split(tok, 1)[1].strip()
            return rest.split(None, 1)[0] if rest else None
    return None


def _dispatch(raw, line, out, stdin, history, nav):
    """Одна строка REPL: меню-навигатор или чат. False = выйти."""
    low = line.lower()
    if low in ("/выход", "/quit", "/exit", "exit", "quit"):
        return False
    if nav["mode"] == "chat":
        # вход в навигатор
        if low in ("меню", "/меню", "menu", "/menu", "м"):
            nav["mode"] = "menu"
            nav["level"] = 0
            nav["store"] = None
            _show_menu(out, nav)
            return True
        # быстрый провал «внутрь <slug>»
        if low.startswith(("внутрь ", "/внутрь ", "магазин ")) and " " in low:
            slug = low.split(None, 1)[1]
            if slug in _cycles_list():
                nav["mode"] = "menu"
                nav["level"] = 1
                nav["store"] = slug
                _show_menu(out, nav)
                return True
        return _handle(line, out, stdin, history)
    # режим меню
    if low in ("меню", "/меню", "menu", "/menu", "м"):
        _show_menu(out, nav)
        return True
    if line.isdigit() and len(line) <= 2:
        _menu_action(out, stdin, nav, line)
        if nav["mode"] == "menu":
            _show_menu(out, nav)
        return True
    # текст в меню = уходим в чат
    if not low.startswith("/"):
        nav["mode"] = "chat"
        nav["level"] = 0
        nav["store"] = None
    return _handle(line, out, stdin, history)


def repl(stdin=None, stdout=None):
    """SOCC-ЯМ · чат + меню-навигатор. stdin/stdout опциональны (для тестов)."""
    out = stdout or sys.stdout
    history = []
    nav = _NAV
    nav.update({"mode": "chat", "level": 0, "store": None})
    _print_banner(out)
    print(_dim(out, "  чат: просто напиши · навигатор: «меню» · команды: /help"), file=out)
    if stdin is None:
        _log("=== сессия SOCC-ЯМ старт ===")
    while True:
        try:
            if stdin is not None:
                out.write(_prompt_text(nav))
                out.flush()
                raw = stdin.readline()
                if not raw:
                    break
            else:
                try:
                    raw = input(_prompt_text(nav))
                except (EOFError, KeyboardInterrupt):
                    print(file=out)
                    break
        except KeyboardInterrupt:
            continue
        line = raw.strip()
        if not line:
            continue
        try:
            if stdin is None:
                _log(f"[cmd] {_snip(line, 200)}")
            keep = _dispatch(raw, line, out, stdin, history, nav)
        except KeyboardInterrupt:
            continue
        if keep is False:
            break
    if stdin is None:
        _log("=== сессия SOCC-ЯМ конец ===")
    print("\nдо связи.", file=out)


# ─────────────────────────────────────────────────────────────────────────────
#  ONE-SHOT CLI (CI/автопилот/дым)
# ─────────────────────────────────────────────────────────────────────────────

def _main(argv=None):
    ap = argparse.ArgumentParser(description="УПРАВЛЯЮЩИЙ-МОЗГ органа ARBITER (ЦИКЛ-1)")
    ap.add_argument("--say", metavar="ТЕКСТ", help="one-shot: контекст+ответ мозга (действия НЕ выполняются)")
    ap.add_argument("--organs", action="store_true", help="read: какие органы инициирует мозг")
    ap.add_argument("--self", action="store_true", help="read: самоосознание управляющего")
    ap.add_argument("--registry", action="store_true", help="read: реестр циклов/мама")
    ap.add_argument("--pulse", nargs="?", const=STORE_DEFAULT, metavar="STORE",
                    help="read: планёрка магазина (пульс)")
    a = ap.parse_args(argv)
    _ensure_env()

    if a.organs:
        print(_organs_text())
        return 0
    if a.registry:
        label, text = run_action("registry", {})
        _print_result(label, text, sys.stdout)
        return 0
    if a.self:
        label, text = run_action("self", {})
        _print_result(label, text, sys.stdout)
        return 0
    if a.pulse is not None:
        label, text = run_action("plannerka", {"store": a.pulse})
        _print_result(label, text, sys.stdout)
        return 0
    if a.say:
        ans = _ask(a.say)
        if ans.get("ok"):
            text = ans["text"]
        elif ans.get("empty"):
            print("[голос-LLM вернул пустой ответ — ответ из тела SOCC]")
            text = _offline_answer(a.say)
        else:
            print(ans.get("error", "мозг недоступен"))
            return 1
        print(text)
        parsed = plan_action(text)
        if parsed.get("ok"):
            print(f"\n  [анонс] мозг хочет: {parsed['name']} {parsed.get('args') or ''} "
                  f"(роль {parsed.get('role')}) — в REPL {'выполню сразу' if parsed['execute'] else 'спрошу слово'}.")
        return 0
    # без one-shot флагов → интерактивный REPL «как в Клауде»
    repl()
    return 0


if __name__ == "__main__":
    sys.exit(_main())

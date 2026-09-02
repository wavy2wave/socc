#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""УПРАВЛЯЮЩИЙ-МОЗГ · ymarket_brain_v1 — SOCC-мозг органа ARBITER (ЦИКЛ-1 + реестр + мама).

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
  python3 ymarket_brain_v1.py                 # REPL «как в Клауде»
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
}

# семантические алиасы (и для /команд, и для [ДЕЙСТВИЕ] из мозга)
ALIASES = {
    "мама": "registry", "циклы": "registry", "cycles": "registry",
    "реестр": "registry", "registry": "registry",
    "само": "self", "self": "self",
    "пульс": "plannerka", "планёрка": "plannerka",
    "цикл": "cycle_dry", "cycle": "cycle_dry",
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
    """Один обмен с мозгом. Возвращает {ok:True,text,model} или {ok:False,error} — честно, BR4."""
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
    messages = list(history or [])
    messages.append({"role": "user", "content": user})
    body = {"model": model, "max_tokens": 900,
            "system": system, "messages": messages}
    code, raw = _http_post(base + "/v1/messages", body)
    if code != 200:
        return {"ok": False,
                "error": f"мозг: HTTP {code} — {(raw or '')[:180].strip()}"}
    try:
        doc = json.loads(raw)
        text = "".join(
            (b.get("text") or "") for b in (doc.get("content") or []) if b.get("type") == "text"
        ).strip()
        if not text:
            return {"ok": False, "error": "мозг вернул пустой ответ"}
        return {"ok": True, "text": text, "model": model}
    except Exception as e:
        return {"ok": False, "error": f"мозг: разбор ответа не удался — {e}"}


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
        lines.append(
            f"- {slug}: builder={c.get('builder')} донор={c.get('donor_category')} "
            f"markup=×{c.get('markup')} остаток={c.get('stock_count')} · {src} "
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
    action_list = "\n".join(
        f"  · {name} [{a['role']}] — {a['help']}" for name, a in ACTIONS.items())
    return (
        "Ты — УПРАВЛЯЮЩИЙ-МОЗГ органа ARBITER (дропшип-цикл Идея→Товар→Витрина на Яндекс Маркете "
        "Экспресс). Говоришь по-русски как со-пилот оператора: коротко, конкретно, с цифрами; "
        "1 абзац, без воды. Задача — ИНИЦИИРОВАТЬ нужные органы/циклы, отвечая строкой "
        "[ДЕЙСТВИЕ] <имя> <аргументы> ТОЛЬКО из каталога ниже (dry/read — выполню сразу, "
        "write — спрошу у оператора). Если действие не нужно — просто ответь.\n"
        f"\nСегодня: {date_str}. Модель мозга: {os.getenv('ANTHROPIC_MODEL') or MODEL_DEFAULT}.\n"
        f"Ключи (только наличие): мозг={ctx_key}, ЯМ API={ctx_ym}, ТГ={ctx_tg}.\n"
        f"Мать-цикл по умолчанию: {STORE_DEFAULT}.\n"
        f"\n{LAWS_TEXT}\n{QUIET_HINT}\n"
        f"\nРЕЕСТР ЦИКЛОВ (мама-наследование):\n{_cycle_short_state()}\n"
        f"\nСАМООСОЗНАНИЕ:\n{self_txt}\n"
        f"\nДОСТУПНЫЕ ДЕЙСТВИЯ (строгий allowlist):\n{action_list}\n"
        "\nПример строки запуска: [ДЕЙСТВИЕ] cycle_dry --store box-msk   (сухо, 0₽). "
        "Write-действие (cycle_live, new_cycle) не запускай без слова оператора — предложи и жди."
    )


def _ask(text, history=None):
    """Модульный вызов мозга (тесты мокают эту)."""
    return brain_call(build_context(), text, history)


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


def _h_cycle(args, dry):
    store = _pick_store(args)
    res, out = _capture(lambda: _run_cycle(store, dry=dry, commit=not dry, verbose=False))
    v = res.get("verdict")
    head = f"ЦИКЛ {store} · {v}" if v else "ЦИКЛ FAIL"
    body = (out or "").strip()
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
Доступные команды (ввод = разговор с мозгом):
  /органы            список органов/циклов, которые мозг инициирует
  /само              самоосознание управляющего (read)
  /мама · /реестр    реестр циклов: кто от какой мамы наследует кабинет (read)
  /пульс [store]     планёрка магазина (read; по умолчанию мать-цикл)
  /цикл сухо [store]   сухой ход ЦИКЛА-1, 0₽ (авто, read/dry)
  /цикл живьё [store]  ЖИВОЙ ход (write — спрошу «да/нет»)
  /новый-цикл <slug> <builder> <donor_category> <markup> <stock> [--mother M]
                       новый магазин в манифест (write — спрошу «да/нет»)
  /мозг <текст>      прямой вопрос мозгу
  /выход · Ctrl-D    выйти
Простой текст («привет», «запусти цикл плёнки сухо») идёт мозгу; если он ответит
[ДЕЙСТВИЕ] … — dry/read выполню сразу, write спрошу слово оператора."""

_BANNER = """\
════════════════════════════════════════════════════════════════════════
 УПРАВЛЯЮЩИЙ-МОЗГ · ARBITER ЦИКЛ-1 · SOCC-мозг  (deepseek-v4-flash)
 Тихий по умолчанию · мама-наследование · RUBICON: write только по слову
 Ввод = разговор (как с мозгом), /help — команды. Что видишь — исполню.
════════════════════════════════════════════════════════════════════════"""


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

    if low == "/органы":
        print(_organs_text(), file=out)
        return True
    if low.startswith("/само"):
        label, text = run_action("self", {})
        _print_result(label, text, out)
        return True
    if low.startswith("/мама") or low.startswith("/реестр") or low.startswith("/циклы"):
        label, text = run_action("registry", {})
        _print_result(label, text, out)
        return True
    if low.startswith("/пульс"):
        args = _cmd_args(line, low)
        label, text = run_action("plannerka", {"store": args.get("store") or STORE_DEFAULT})
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


def _cmd_args(line, low):
    rest = line[len(low):].strip()
    return _tokens_to_args(_split_argv(rest) or [])


def _organs_text():
    if cycle1 is None:
        return "движок ЦИКЛА-1 недоступен (import)"
    return ("Органы, которые мозг инициирует:\n"
            f"  · ЦИКЛ-1 движок (ymarket_cycle1_v1): магазин по умолчанию {STORE_DEFAULT} — "
            "ДОНОР→СБОРКА→ЗАЛИВ→ВИТРИНА→ОСТАТКИ→СВЕРКА→ПЛАНЁРКА; тихий сухой ход 0₽.\n"
            "  · УПРАВЛЯЮЩИЙ-МОЗГ (я): self-самоосознание, реестр циклов, разговор.\n"
            "  · Реестр мамы: [ДЕЙСТВИЕ] new_cycle ... объявляет mother и наследует кабинет — "
            "системе пофиг какой API.\n"
            "Запуск действий — строкой [ДЕЙСТВИЕ] из каталога; write — по слову оператора.")


def _brain_turn(text, out, stdin, history):
    ans = _ask(text, history)
    if not ans.get("ok"):
        print(f"\n  {ans.get('error', 'мозг недоступен')}\n", file=out)
        return True
    reply = ans["text"]
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})
    del history[:-8]  # держим недавний хвост разговора
    print(f"\n  {reply}\n", file=out)
    parsed = plan_action(reply)
    if not parsed.get("ok"):
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
            print("  отменено (RUBICON: write только по слову оператора).", file=out)
    return True


def _print_result(label, text, out):
    print(f"\n  ▶ {label}\n{text}\n", file=out)


def repl(stdin=None, stdout=None):
    """Интерактив. stdin/stdout опциональны (для тестов)."""
    out = stdout or sys.stdout
    history = []
    print(_BANNER, file=out)
    print("Ввод — разговор с мозгом; /help — команды; write-действия спрашивают слово.\n", file=out)
    if stdin is not None:
        while True:
            out.write("управляющий> ")
            out.flush()
            line = stdin.readline()
            if not line:
                break
            try:
                if not _handle(line, out, stdin, history):
                    break
            except KeyboardInterrupt:
                continue
        print("\nдо связи.", file=out)
        return
    while True:
        try:
            line = input("управляющий> ")
        except (EOFError, KeyboardInterrupt):
            print("\nдо связи.", file=out)
            break
        if not _handle(line, out, None, history):
            break


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
        if not ans.get("ok"):
            print(ans.get("error", "мозг недоступен"))
            return 1
        print(ans["text"])
        parsed = plan_action(ans["text"])
        if parsed.get("ok"):
            print(f"\n  [анонс] мозг хочет: {parsed['name']} {parsed.get('args') or ''} "
                  f"(роль {parsed.get('role')}) — в REPL {'выполню сразу' if parsed['execute'] else 'спрошу слово'}.")
        return 0
    # без one-shot флагов → интерактивный REPL «как в Клауде»
    repl()
    return 0


if __name__ == "__main__":
    sys.exit(_main())

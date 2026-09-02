#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""УПРАВЛЯЮЩИЙ-МОЗГ · ПРИЁМКА (ymarket_brain_v1). Законы, а не «оно запустилось». Сухо, 0₽, без сети.

Законы мозга (спека YM_BRAIN_V1.md):
  BR1  write_по_слову        — cycle_live/new_cycle: сухо-авто; write запускается ТОЛЬКО с confirmed
                               (по явному «да» оператора), иначе НУЖНО СЛОВО, движок не зовётся
  BR2  allowlist_строг        — имя вне ACTIONS/[ДЕЙСТВИЕ] → отказ; в исходнике нет subprocess/os.system
  BR3  секреты_не_утекают     — build_context() не содержит значений AGENTROUTER_API_KEY/YANDEX_MARKET_API_KEY
  BR4  мозг_честен_оффлайн     — без ключа brain_call → {ok:False} «нет AGENTROUTER_API_KEY»; стаб → ok
  BR5  тишина_движка           — run_cycle с шумной фейк-цепью: в stdout НЕТ шума, НО пульс+вердикт;
                               verbose=True шум виден; FAIL-узел показывает хвост
  BR6  мама_наследование       — ребёнок {mother} наследует кабинет от матери; не-наследуемое поле
                               остаётся недостающим (add_store честно FAIL)
  BR7  repl_сухо_и_живьё       — стаб мозга `[ДЕЙСТВИЕ] cycle_dry` → run_cycle(dry=True) сразу;
                               `[ДЕЙСТВИЕ] cycle_live` → ждёт «да», «нет» → RUBICON (не выполнен)
  BR8  пустой_ответ_LLM        — relay вернул только thinking: brain_call делает 2-й заход и отвечает;
                               повторная пустота → {ok:False, empty:True} (НЕ тупик-строка)
  BR9  тело_SOCC_в_контексте   — build_context() несёт донор-модель/доктрину/законы/глоссарий:
                               «донор=магазин-поставщик», cargo-avto, RUBICON, пульс-1, мама
  BR10 пульс-1_запускаем       — `[ДЕЙСТВИЕ] пульс-1 <store>` → cycle_dry (alias); оффлайн сам
                               инициирует сухой прогон; на «что такое пульс-1» отвечает определением
  BR11 оффлайн_фолбэк          — _ask вернул пустоту → REPL отвечает из тела SOCC (не «мозг недоступен»),
                               не пусто, сухо-авто живо
  BR12 меню_навигатор          — «меню» → корень = список циклов MINT (звезда=живой) → внутрь
                               цикла → карточка → назад → в чат
  BR13 короткий_ответ          — показ-версия режет длинный ответ, но [ДЕЙСТВИЕ]-строку сохраняет
  BR14 спиннер_молчит_в_тесте  — _with_spinner на не-tty выходе не пишет мусор, значение возвращает
  BR15 лог_не_на_диске_в_тесте — repl с заданным stdin не пишет сессия-лог на диск (runtime чист)
"""
import io
import json
import os
import sys
import tempfile
import contextlib
import inspect
import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_brain_v1 as brain            # noqa: E402
import ymarket_cycle1_v1 as cycle1          # noqa: E402  (движок, чистый импорт)


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


class _Rec:
    """Ловушка вызовов мозг→движок (BR1/BR7)."""
    def __init__(self):
        self.calls = []

    def cycle(self, store, dry=True, commit=False, verbose=False):
        self.calls.append(("cycle", store, dry, commit))
        return {"verdict": "DRY_OK" if dry else "PASS", "hash": "abc1234567"}

    def add(self, profile):
        self.calls.append(("add", profile))
        return True, f"магазин «{profile['slug']}» добавлен; кабинет унаследован"


# ─────────────────────────── ТЕСТЫ ───────────────────────────

def br1_write_po_slovu():
    """Сухо/чтение — авто; write (cycle_live/new_cycle) — только с confirmed=True. Без слова движок не зовём."""
    rec = _Rec()
    old_cycle, old_add = brain._run_cycle, brain._add_cycle
    brain._run_cycle, brain._add_cycle = rec.cycle, rec.add
    try:
        # dry — авто
        label_dry, _ = brain.run_action("cycle_dry", {"store": "box-msk"})
        dry_auto = label_dry == "ЦИКЛ box-msk · DRY_OK"
        # live без слова → НУЖНО СЛОВО, движок не тронут
        label_live, _ = brain.run_action("cycle_live", {"store": "box-msk"})
        live_refused = label_live == "НУЖНО СЛОВО" and len(rec.calls) == 1
        # live со словом → идёт с commit=True
        label_ok, _ = brain.run_action("cycle_live", {"store": "box-msk"}, confirmed=True)
        live_went = label_ok == "ЦИКЛ box-msk · PASS"
        # new_cycle write — гейт + исполнение с confirmed
        label_nc, _ = brain.run_action("new_cycle", {"slug": "box-msk", "builder": "box",
                                                     "donor_category": "korobki", "markup": 6,
                                                     "stock_count": 50})
        nc_refused = label_nc == "НУЖНО СЛОВО" and all(c[0] != "add" for c in rec.calls)
        label_nc2, _ = brain.run_action("new_cycle", {"slug": "box-msk", "builder": "box",
                                                      "donor_category": "korobki", "markup": 6,
                                                      "stock_count": 50}, confirmed=True)
        nc_went = label_nc2 == "НОВЫЙ-ЦИКЛ"
        ok = all([dry_auto, live_refused, live_went, nc_refused, nc_went])
        return ok, (f"dry_auto={dry_auto} live_refused={live_refused} live_went={live_went} "
                    f"nc_refused={nc_refused} nc_went={nc_went}")
    finally:
        brain._run_cycle, brain._add_cycle = old_cycle, old_add


def br2_allowlist_strog():
    """Вне ACTIONS / без [ДЕЙСТВИЕ] — отказ; в исходнике нет произвольного шелла (subprocess/os.system)."""
    p1 = brain.plan_action("[ДЕЙСТВИЕ] rm -rf /")
    p2 = brain.plan_action("просто текст без действия")
    p3 = brain.plan_action("[ДЕЙСТВИЕ] несуществующее")
    src = inspect.getsource(brain)
    no_shell = "subprocess" not in src and "os.system" not in src
    ok = all(not x["ok"] for x in (p1, p2, p3)) and no_shell
    return ok, f"rm={p1['why'][:30]}… текст={p2['why']} вне={p3['why'][:40]}… shell_отсутствует={no_shell}"


def br3_sekrety_ne_utekayut():
    """Контекст мозга содержит только булевы «ключ задан», не значения ключей."""
    brain._ensure_env()
    ctx = brain.build_context()
    leaks = []
    for k in ("AGENTROUTER_API_KEY", "YANDEX_MARKET_API_KEY", "TELEGRAM_BOT_TOKEN"):
        v = os.getenv(k)
        if v and v in ctx:
            leaks.append(k)
    ok = not leaks and ("мозг=" in ctx or "Ключи" in ctx)
    return ok, f"значения-в-контексте: {leaks or '—'} (только булевы)"


def br4_mozg_chesten_offline():
    """Без ключа brain_call возвращает честный {ok:False}, а не выдумывает; со стабом HTTP — ok."""
    saved = os.environ.pop("AGENTROUTER_API_KEY", None)
    try:
        r = brain.brain_call("система", "привет")
        offline_ok = r["ok"] is False and "нет AGENTROUTER_API_KEY" in r.get("error", "")
    finally:
        if saved is not None:
            os.environ["AGENTROUTER_API_KEY"] = saved
    if not offline_ok:
        return False, "оффлайн-путь не сработал"
    # со стабом HTTP — мозг отвечает текстом
    old = brain._http_post
    brain._http_post = lambda url, body: (
        200, json.dumps({"content": [{"type": "text", "text": "привет, со-пилот"}]}))
    try:
        r2 = brain.brain_call("система", "привет")
        online_ok = r2["ok"] is True and r2["text"] == "привет, со-пилот"
    finally:
        brain._http_post = old
    return online_ok, f"offline честен={offline_ok} · стаб-200 отвечает={online_ok}"


def br5_tishina_dvizhka():
    """run_cycle тихий: шум узла скрыт, пульс+вердикт есть; verbose открывает; FAIL показывает хвост."""
    tmp = Path(tempfile.mkdtemp()) / "ledger.jsonl"
    old_load, old_ledger = cycle1.load_store, cycle1.ledger_path
    cycle1.load_store = lambda slug: {"slug": slug, "business_id": 1, "campaign_id": 2,
                                      "warehouse_id": 3, "donor_category": "x", "builder": "film",
                                      "markup": 5.0, "stock_count": 1}
    cycle1.ledger_path = lambda slug, date: tmp

    def noisy_pass(ctx, dry, commit):
        print("ШУМ-МАРКЕР: точный payload", {"x": 1})
        return {"verdict": "PASS", "note": "ok", "evidence": {}}

    def noisy_fail(ctx, dry, commit):
        print("ШУМ-1", "ШУМ-2")
        return {"verdict": "FAIL", "note": "упало", "evidence": {}}

    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = cycle1.run_cycle("probe", dry=True, chain=[("ДОНОР", noisy_pass, False)])
        quiet = "ШУМ-МАРКЕР" not in buf.getvalue() and "ДОНОР" in buf.getvalue()
        quiet_ok = quiet and res["verdict"] == "DRY_OK"
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            cycle1.run_cycle("probe", dry=True, chain=[("ДОНОР", noisy_pass, False)], verbose=True)
        verbose_ok = "ШУМ-МАРКЕР" in buf2.getvalue()
        buf3 = io.StringIO()
        with contextlib.redirect_stdout(buf3):
            res3 = cycle1.run_cycle("probe", dry=True, chain=[("ОСТАНОВ", noisy_fail, False)])
        fail_tail = "ШУМ-2" in buf3.getvalue() and res3["verdict"] == "FAIL"
        ok = quiet_ok and verbose_ok and fail_tail
        return ok, f"тихо={quiet_ok} verbose={verbose_ok} FAIL-хвост={fail_tail}"
    finally:
        cycle1.load_store, cycle1.ledger_path = old_load, old_ledger


def br6_mama_nasledovanie():
    """Дочерний цикл {mother} наследует кабинет от матери; мать без mother — та же; не-наследуемое остаётся."""
    mom = {"slug": "atlas-express-film", "business_id": 216949599, "campaign_id": 149215943,
           "warehouse_id": 2390811, "donor_category": "plenka", "builder": "film",
           "markup": 8.0, "stock_count": 100}
    child = {"slug": "box-msk", "mother": "atlas-express-film", "donor_category": "korobki",
             "builder": "box", "markup": 6.0, "stock_count": 50}
    allp = {"atlas-express-film": mom, "box-msk": child}
    r_child, why_child = cycle1.resolve_profile(child, allp)
    inherits = (why_child is None and r_child["business_id"] == 216949599
                and r_child["campaign_id"] == 149215943 and r_child["warehouse_id"] == 2390811
                and r_child["_inherited_from"] == "atlas-express-film")
    # донор/товарные поля НЕ наследуются (каждый цикл свой)
    donor_kept = r_child["donor_category"] == "korobki"
    r_mom, why_mom = cycle1.resolve_profile(mom, allp)
    mother_same = why_mom is None and r_mom["business_id"] == mom["business_id"] \
        and "_inherited_from" not in r_mom
    # add_store: ребёнок БЕЗ товарных полей (только мама-кабинет) → честный FAIL «не хватает полей»
    tmp = Path(tempfile.mkdtemp()) / "stores.json"
    tmp.write_text(json.dumps({mom["slug"]: mom}, ensure_ascii=False))
    old_path = cycle1.store_profiles_path
    cycle1.store_profiles_path = lambda: tmp
    try:
        bad = {"slug": "empty-child", "mother": "atlas-express-film", "builder": "box"}
        # нет донора/markup/остатка → после наследования кабинета honest FAIL «не хватает полей»
        ok_add, why_add = cycle1.add_store(bad)
        honest_fail = (ok_add is False) and "не хватает полей" in why_add
    finally:
        cycle1.store_profiles_path = old_path
    ok = all([inherits, donor_kept, mother_same, honest_fail])
    return ok, (f"child_inherits={inherits} donor_не_наследуется={donor_kept} "
                f"mother_same={mother_same} add_store_честный_FAIL={honest_fail}")


def br7_repl_suho_i_zhivyo():
    """REPL: [ДЕЙСТВИЕ] cycle_dry → сухо сразу; [ДЕЙСТВИЕ] cycle_live → ждёт «да»; «нет» → не выполнен."""
    rec = _Rec()
    old_cycle = brain._run_cycle
    brain._run_cycle = rec.cycle
    try:
        # сухо: мозг (стаб) хочет cycle_dry
        inp = io.StringIO("запусти плёнку\n")
        out = io.StringIO()
        old_ask = brain._ask
        brain._ask = lambda text, history=None: {"ok": True, "text": "[ДЕЙСТВИЕ] cycle_dry --store atlas-express-film"}
        try:
            brain.repl(stdin=inp, stdout=out)
        finally:
            brain._ask = old_ask
        dry_ran = any(c[0] == "cycle" and c[2] is True and c[3] is False for c in rec.calls)
        # живьё: ждёт «да»
        rec.calls.clear()
        inp2 = io.StringIO("сделай живьём\nда\n")
        out2 = io.StringIO()
        brain._ask = lambda text, history=None: {"ok": True, "text": "[ДЕЙСТВИЕ] cycle_live"}
        try:
            brain.repl(stdin=inp2, stdout=out2)
        finally:
            brain._ask = old_ask
        live_after_yes = any(c[0] == "cycle" and c[2] is False and c[3] is True for c in rec.calls)
        # «нет» → RUBICON
        rec.calls.clear()
        inp3 = io.StringIO("сделай живьём\nнет\n")
        out3 = io.StringIO()
        brain._ask = lambda text, history=None: {"ok": True, "text": "[ДЕЙСТВИЕ] cycle_live"}
        try:
            brain.repl(stdin=inp3, stdout=out3)
        finally:
            brain._ask = old_ask
        live_after_no = all(not (c[0] == "cycle" and c[2] is False) for c in rec.calls)
        ok = dry_ran and live_after_yes and live_after_no
        return ok, f"сухо_сразу={dry_ran} живьё_после_да={live_after_yes} живьё_после_нет={live_after_no}"
    finally:
        brain._run_cycle = old_cycle


def br8_pustoi_otvet_llm():
    """Relay вернул только thinking → 2-й заход отвечает; повторная пустота → empty:True; оффлайн не пуст."""
    saved = os.environ.get("AGENTROUTER_API_KEY")
    os.environ["AGENTROUTER_API_KEY"] = "test-key-br8"
    old = brain._http_post

    def _restore():
        brain._http_post = old
        if saved is None:
            os.environ.pop("AGENTROUTER_API_KEY", None)
        else:
            os.environ["AGENTROUTER_API_KEY"] = saved

    calls = []

    def thinking_then_text(url, body):
        calls.append(url)
        if len(calls) == 1:
            return 200, json.dumps({"content": [{"type": "thinking", "thinking": "думаю…"}]})
        return 200, json.dumps({"content": [{"type": "text", "text": "привет, ответил после пинка"}]})

    brain._http_post = thinking_then_text
    try:
        r = brain.brain_call("система", "привет")
        retry_ok = (r["ok"] is True and r["text"] == "привет, ответил после пинка"
                    and len(calls) == 2)
    finally:
        _restore()

    # повторная пустота → честный empty:True (REPL ответит телом, не тупиком)
    os.environ["AGENTROUTER_API_KEY"] = "test-key-br8"

    def always_thinking(url, body):
        return 200, json.dumps({"content": [{"type": "thinking", "thinking": "…"}]})

    brain._http_post = always_thinking
    try:
        r2 = brain.brain_call("система", "привет")
        empty_flagged = (r2.get("ok") is False) and (r2.get("empty") is True)
    finally:
        _restore()
    # оффлайн-ответ: не пуст и сам инициирует сухой прогон
    off = brain._offline_answer("запусти сухой цикл плёнки")
    offline_ok = bool(off.strip()) and "[ДЕЙСТВИЕ] cycle_dry" in off
    ok = retry_ok and empty_flagged and offline_ok
    return ok, (f"2-й_заход={retry_ok} повторно_пусто→empty={empty_flagged} "
                f"оффлайн_не_пуст+сухо={offline_ok}")


def br9_telo_socc_v_kontekste():
    """Контекст мозга несёт тело SOCC: донор=магазин, доктрина, законы, глоссарий терминов."""
    brain._ensure_env()
    ctx = brain.build_context().lower()
    need = ("магазин-поставщик", "cargo-avto", "rubicon", "пульс-1", "мама",
            "без бренда", "в работе", "закупок заранее")
    missing = [k for k in need if k not in ctx]
    ok = not missing
    return ok, f"в контексте есть всё из {need}: недостаёт {missing or '—'}"


def br10_puls1_zapuskaem():
    """«пульс-1 <магазин>» = ПРОГОН цикла: alias→cycle_dry; оффлайн сам его инициирует; термин знает."""
    p = brain.plan_action("[ДЕЙСТВИЕ] пульс-1 --store atlas-express-film")
    alias_ok = (p.get("ok") and p["name"] == "cycle_dry" and p["role"] == "dry" and p["execute"])
    off = brain._offline_answer("запусти пульс-1 по box-msk сухо")
    auto_ok = "[ДЕЙСТВИЕ] cycle_dry" in off
    term = brain._offline_answer("что такое пульс-1?")
    term_ok = bool(term.strip()) and "ДОНОР→СБОРКА" in term
    # донор ≠ категория: оффлайн различает магазин-поставщика и URL-путь категории
    donor = brain._offline_answer("донор это cargo shop?")
    donor_ok = "cargo-avto" in donor and "vozdushno-puzyrkovaya-plenka" in donor
    ok = alias_ok and auto_ok and term_ok and donor_ok
    return ok, (f"alias_cycle_dry={alias_ok} оффлайн_авто={auto_ok} "
                f"термин_пульс-1={term_ok} донор_≠_категория={donor_ok}")


def br11_offlain_folbek():
    """_ask вернул пустоту → REPL отвечает из тела SOCC, без тупика «мозг недоступен», не пусто."""
    old_ask = brain._ask
    brain._ask = lambda text, history=None: {"ok": False, "empty": True,
                                              "error": "мозг вернул пустой ответ (2 попытки)"}
    try:
        inp = io.StringIO("привет\n")
        out = io.StringIO()
        brain.repl(stdin=inp, stdout=out)
        txt = out.getvalue()
    finally:
        brain._ask = old_ask
    body_ok = "из тела SOCC" in txt and "УПРАВЛЯЮЩИЙ-МОЗГ" in txt
    not_deadend = "мозг недоступен" not in txt
    nonempty = len(txt.strip()) > 0
    ok = body_ok and not_deadend and nonempty
    return ok, f"ответил_телом={body_ok} без_тупика={not_deadend} не_пусто={nonempty}"


def br12_menu_navigator():
    """«меню» → корень = СПИСОК ЦИКЛОВ MINT: цикл с деталью/звёздой → внутрь → карточка → назад → чат."""
    fake = {
        "atlas-express-film": {"builder": "film", "donor_category": "vozdushno-puzyrkovaya-plenka",
                               "markup": 8.0, "stock_count": 100, "business_id": 216949599,
                               "campaign_id": 149215943, "warehouse_id": 2390811, "mother": None},
        "box-msk": {"builder": "box", "donor_category": "korobki", "markup": 6.0,
                    "stock_count": 50, "mother": "atlas-express-film"},
    }
    today = datetime.date.today().isoformat()
    old_list, old_plan = brain.cycle1.list_cycles, brain.cycle1.plannerka_read
    brain.cycle1.list_cycles = lambda: dict(fake)
    brain.cycle1.plannerka_read = lambda s: {"date": today, "run_verdicts": "PASS",
                                             "artifacts": "1", "yesterday_verdicts": "DRY_OK"}
    old_ask = brain._ask
    brain._ask = lambda text, history=None: {"ok": True, "text": "ок"}
    try:
        # корень-список циклов → 1-й цикл → карточка → назад к циклам → 0 в чат
        inp = io.StringIO("меню\n1\n4\n0\n0\n")
        out = io.StringIO()
        brain.repl(stdin=inp, stdout=out)
        txt = out.getvalue()
    finally:
        brain.cycle1.list_cycles, brain.cycle1.plannerka_read = old_list, old_plan
        brain._ask = old_ask
    root = "SOCC-ЯМ · циклы MINT" in txt
    both_stores = "atlas-express-film" in txt and "box-msk" in txt
    live_star = "★1" in txt
    card = "ДОНОР→СБОРКА" in txt and "atlas-express-film · builder=film" in txt
    back_chat = "в чат" in txt and "управляющий> " in txt
    ok = root and both_stores and live_star and card and back_chat and "Traceback" not in txt
    return ok, (f"корень-циклы={root} оба={both_stores} звезда-живой={live_star} "
                f"карточка={card} назад_в_чат={back_chat}")


def br13_short_reply_keeps_action():
    """Длинный ответ режется для показа, но [ДЕЙСТВИЕ]-строка из хвоста не теряется."""
    reply = "\n".join(f"строка {i}" for i in range(1, 16)) + "\n[ДЕЙСТВИЕ] cycle_dry --store box-msk"
    short = brain._short_reply(reply)
    lines = [ln for ln in short.splitlines() if ln.strip()]
    has_action = "[ДЕЙСТВИЕ]" in short
    head_kept = any(ln == "строка 1" for ln in lines)
    cut_mark = "…" in short
    shortened = len(lines) < 15
    # длинный ответ без действия тоже режется
    cut = len([ln for ln in brain._short_reply("\n".join(f"x{i}" for i in range(1, 20))).splitlines()
               if ln.strip()]) <= 10
    ok = has_action and head_kept and cut_mark and shortened and cut
    return ok, (f"действие_в_коротком={has_action} голова={head_kept} "
                f"маркер={cut_mark} укорочен={shortened} режется={cut}")


def br14_spinner_silent_off_tty():
    """Спиннер на не-tty выходе (StringIO) не пишет мусор и возвращает результат функции."""
    buf = io.StringIO()
    val = brain._with_spinner(buf, "думаю…", lambda: 42)
    ok = val == 42 and buf.getvalue() == ""
    return ok, f"значение={val} мусор_в_выходе={buf.getvalue()!r}"


def br15_log_off_when_stdin():
    """repl с заданным stdin (тесты) не пишет сессия-лог на диск — runtime/ brain чист."""
    rt = brain._RUNTIME

    def _files():
        if not rt.exists():
            return set()
        return {p.name for p in rt.iterdir()}

    old_ask = brain._ask
    brain._ask = lambda text, history=None: {"ok": True, "text": "привет"}
    before = _files()
    try:
        brain.repl(stdin=io.StringIO("привет\n"), stdout=io.StringIO())
    finally:
        brain._ask = old_ask
    after = _files()
    ok = before == after
    return ok, f"новых-файлов-сессии={after - before or '—'}"


# ───────────────────────── КОНСОЛЬ-ЯМ в навигаторе (BR16–BR18) ─────────────────────────

class _StubConsole:
    """Стаб КОНСОЛЬ-ЯМ для навигации: методы возвращают фикс-текст, диск/сеть не читаем."""
    def roles_index(self):
        return [{"key": f"R{i}", "name_ru": f"Имя{i}", "emoji": "•", "cluster": "core"}
                for i in range(1, 14)]

    def staff_summary(self, **kw):
        return "ШТАБ-СТАБ · 13 ролей"

    def role_card(self, key, **kw):
        return f"КАРТОЧКА-{key}"

    def kpi_text(self, **kw):
        return "KPI-СТАБ · день/неделя/месяц"

    def day_card(self, **kw):
        return "ДЕНЬ-СТАБ · снимок дня"

    def tabel_today_text(self, **kw):
        return "ТАБЕЛЬ-СТАБ · сегодня"

    def artifacts_text(self, **kw):
        return "АРТЕФАКТЫ-СТАБ · матрица/библиотека/точки"

    def autopilot_tail(self, **kw):
        return "АВТО-СТАБ · хвост"

    def deal_text(self, **kw):
        return "ДЕЛО-СТАБ · всё одним листом"


def _one_fake_store():
    return {"atlas-express-film": {"builder": "film",
                                   "donor_category": "vozdushno-puzyrkovaya-plenka",
                                   "markup": 8.0, "stock_count": 100, "mother": None}}


def _nav_env():
    """Патчим стаб-консоль + один фейк-цикл + не-пишущий мозг. Возвращает restore()."""
    old_console = brain.console
    old_list = brain.cycle1.list_cycles
    old_plan = brain.cycle1.plannerka_read
    old_ask = brain._ask
    old_run = brain._run_cycle
    old_add = brain._add_cycle
    rec = {"cycle": [], "add": []}
    brain.console = _StubConsole()
    brain.cycle1.list_cycles = lambda: _one_fake_store()
    brain.cycle1.plannerka_read = lambda s: {"date": datetime.date.today().isoformat(),
                                             "run_verdicts": "PASS", "artifacts": "1"}
    brain._ask = lambda text, history=None: {"ok": True, "text": "ок"}

    def _c(*a, **k):
        rec["cycle"].append(a)

    def _a(*aa, **k):
        rec["add"].append(aa)

    brain._run_cycle = _c
    brain._add_cycle = _a

    def _restore():
        brain.console = old_console
        brain.cycle1.list_cycles = old_list
        brain.cycle1.plannerka_read = old_plan
        brain._ask = old_ask
        brain._run_cycle = old_run
        brain._add_cycle = old_add

    return rec, _restore


def br16_koren_odin_spisok():
    """Корень = ОДИН список: 1 цикл → 2 создать · 3 ШТАБ · 4 ДЕЛО · 0 в чат; цифры 3/4 ведут внутрь."""
    rec, restore = _nav_env()
    try:
        inp = io.StringIO("меню\n3\n0\n4\n0\n0\n")
        out = io.StringIO()
        brain.repl(stdin=inp, stdout=out)
        txt = out.getvalue()
    finally:
        restore()
    root = ("SOCC-ЯМ · циклы MINT" in txt and "★1" in txt and
            "2 · создать цикл (мастер)" in txt and "3 · ШТАБ — 13 ролей · занятость · совесть" in txt
            and "4 · ДЕЛО — KPI · день · табель · артефакты" in txt and "0 · в чат" in txt)
    # 3 → штаб-ветка (стаб тело), 4 → дело-меню
    shtab = "ШТАБ-СТАБ" in txt and "ШТАБ · роль — цифра 1–13" in txt
    delo = "SOCC-ЯМ · ДЕЛО" in txt and "1 · KPI — день / неделя / месяц" in txt
    write_untouched = not rec["cycle"] and not rec["add"]
    ok = root and shtab and delo and write_untouched and "Traceback" not in txt
    return ok, (f"корень-один-список={root} цифра3→штаб={shtab} цифра4→дело={delo} "
                f"write-не_тронут={write_untouched}")


def br17_shtab_daiv():
    """ШТАБ-дайв: меню 3 → лист ролей; цифра → карточка роли (стаб); 0 → назад к штабу → к циклам."""
    rec, restore = _nav_env()
    try:
        inp = io.StringIO("меню\n3\n4\n0\n0\n0\n")
        out = io.StringIO()
        brain.repl(stdin=inp, stdout=out)
        txt = out.getvalue()
    finally:
        restore()
    staff_list = "ШТАБ-СТАБ · 13 ролей" in txt
    card = "КАРТОЧКА-R4" in txt and "роль · R4" in txt     # 4-я роль → роли index[3]
    prompts = "штаб> " in txt and "роль:R4> " in txt
    back_cycles = "SOCC-ЯМ · циклы MINT" in txt
    write_untouched = not rec["cycle"] and not rec["add"]
    ok = staff_list and card and prompts and back_cycles and write_untouched and "Traceback" not in txt
    return ok, (f"лист-ролей={staff_list} карточка-R4={card} приглашения={prompts} "
                f"назад-к-циклам={back_cycles} write-не_тронут={write_untouched}")


def br18_delo_chtenie():
    """ДЕЛО-ветка: меню 4 → KPI/ДЕНЬ рендерится (стаб, read), write не вызывается; 0 назад."""
    rec, restore = _nav_env()
    try:
        inp = io.StringIO("меню\n4\n1\n2\n0\n0\n")
        out = io.StringIO()
        brain.repl(stdin=inp, stdout=out)
        txt = out.getvalue()
    finally:
        restore()
    delo_menu = "SOCC-ЯМ · ДЕЛО" in txt and "1 · KPI — день / неделя / месяц" in txt
    kpi_rendered = "KPI-СТАБ · день/неделя/месяц" in txt
    day_rendered = "ДЕНЬ-СТАБ · снимок дня" in txt
    prompt = "дело> " in txt
    write_untouched = not rec["cycle"] and not rec["add"]
    back_cycles = "SOCC-ЯМ · циклы MINT" in txt
    ok = (delo_menu and kpi_rendered and day_rendered and prompt
          and write_untouched and back_cycles and "Traceback" not in txt)
    return ok, (f"дело-меню={delo_menu} kpi-рендер={kpi_rendered} день-рендер={day_rendered} "
                f"приглашение={prompt} write-не_тронут={write_untouched} назад={back_cycles}")


def br19_zadaniya_seam():
    """ЦИКЛ-ДНЯ в мозге (шов tasks): /задания — планёрка с владельцами (read); --dispatch — разбор
    без прогона; --form --commit пишет реестр ТОЛЬКО после слова оператора («нет» → не пишет)."""
    import ymarket_tasks_v1 as T_
    import ymarket_cycle_day_v1 as real_cd
    calls = {"form": [], "cycle": []}

    class _FakeCD:
        def plannerka_text(self, store=None, tasks=None, date_str=None):
            return real_cd.plannerka_text(store=store, tasks=tasks, date_str=date_str)

        def dispatch(self, tasks=None, *, cycle_dry=False, store=None, date_str=None):
            if cycle_dry:
                calls["cycle"].append(store)
            return real_cd.dispatch(tasks=tasks, cycle_dry=False, store=store, date_str=date_str)

        def form(self, *, commit=False, store=None, date_str=None, save_path=None, verbose=False):
            calls["form"].append({"commit": commit, "store": store})
            return real_cd.form(commit=commit, store=store, date_str=date_str,
                                save_path=save_path, verbose=verbose)

    old_cd, old_ask = brain.cyc_day, brain._ask
    brain.cyc_day = _FakeCD()
    tmp = tempfile.mkdtemp()
    reg = Path(tmp) / "tasks.json"
    os.environ["YM_TASKS_PATH"] = str(reg)
    txt_all = ""
    try:
        t1, _ = T_.new_task(what="Переценка ARB-87931769 (тест)", owner="PRICER",
                            category="pricing", store="atlas-express-film")
        t2, _ = T_.new_task(what="Категории донора (тест)", owner="CATEGORIST",
                            category="categories", store="atlas-express-film")
        T_.save([t1, t2], path=reg)
        brain._ask = lambda text, history=None: {"ok": True, "text": ""}
        # 1) планёрка: задания + владельцы (read)
        out = io.StringIO()
        brain.repl(stdin=io.StringIO("/задания\n"), stdout=out)
        txt = out.getvalue()
        txt_all += txt
        plannerka = ("ЗАДАНИЯ" in txt and "PRICER" in txt and "CATEGORIST" in txt
                     and "открыто 2" in txt)
        # 2) диспетчер: read-разбор, цикл НЕ гоняем (без --cycle-dry)
        out2 = io.StringIO()
        brain.repl(stdin=io.StringIO("/задания --dispatch\n"), stdout=out2)
        txt2 = out2.getvalue()
        txt_all += txt2
        dispatch_ok = ("ДИСПЕТЧЕР" in txt2 and "ЦЕНОВИК·ПЛАН готовит план" in txt2
                       and calls["cycle"] == [])
        # 3) form --commit + «нет» → отменено, форма не звалась
        out3 = io.StringIO()
        brain.repl(stdin=io.StringIO("/задания --form --commit\nнет\n"), stdout=out3)
        txt3 = out3.getvalue()
        txt_all += txt3
        no_write = not calls["form"]
        # 4) form --commit + «да» → пишет локальный реестр (tmp)
        out4 = io.StringIO()
        brain.repl(stdin=io.StringIO("/задания --form --commit\nда\n"), stdout=out4)
        txt4 = out4.getvalue()
        txt_all += txt4
        yes_write = any(c.get("commit") for c in calls["form"]) and reg.exists()
    finally:
        brain.cyc_day = old_cd
        brain._ask = old_ask
        os.environ.pop("YM_TASKS_PATH", None)
    ok = (plannerka and dispatch_ok and no_write and yes_write
          and "Traceback" not in txt_all)
    return ok, (f"планёрка-владельцы={plannerka} диспетчер-read={dispatch_ok} "
                f"«нет»-не-пишет={no_write} «да»-пишет={yes_write}")


TESTS = [
    ("BR1  write_по_слову", br1_write_po_slovu),
    ("BR2  allowlist_строг", br2_allowlist_strog),
    ("BR3  секреты_не_утекают", br3_sekrety_ne_utekayut),
    ("BR4  мозг_честен_оффлайн", br4_mozg_chesten_offline),
    ("BR5  тишина_движка", br5_tishina_dvizhka),
    ("BR6  мама_наследование", br6_mama_nasledovanie),
    ("BR7  repl_сухо_и_живьё", br7_repl_suho_i_zhivyo),
    ("BR8  пустой_ответ_LLM", br8_pustoi_otvet_llm),
    ("BR9  тело_SOCC_в_контексте", br9_telo_socc_v_kontekste),
    ("BR10 пульс-1_запускаем", br10_puls1_zapuskaem),
    ("BR11 оффлайн_фолбэк", br11_offlain_folbek),
    ("BR12 меню_навигатор", br12_menu_navigator),
    ("BR13 короткий_ответ", br13_short_reply_keeps_action),
    ("BR14 спиннер_молчит", br14_spinner_silent_off_tty),
    ("BR15 лог_не_на_диске", br15_log_off_when_stdin),
    ("BR16 корень_один_список", br16_koren_odin_spisok),
    ("BR17 штаб_дайв", br17_shtab_daiv),
    ("BR18 дело_чтение", br18_delo_chtenie),
    ("BR19 задания_шов", br19_zadaniya_seam),
]


def main():
    print("🎯 УПРАВЛЯЮЩИЙ-МОЗГ · ПРИЁМКА — мозг сам не пишет, allowlist строг, секреты не текут (0₽)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<22} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Мозг честен: сухо-авто, живьё-по-слову (RUBICON), allowlist, секреты под замком")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

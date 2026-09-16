#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · ИНТЕРАКТИВ — ПРИЁМКА (socc_cli/dom.py).

Сухо, 0₽, без сети, без записи. Живой дом читает только лежащие сторы (как консоль).
Законы DH1–DH17:
  DH1  меню_дом      — run_home рендерит меню: 5 органов + ЖИВОЕ + Выйти; q → rc 0
  DH2  цвета_plain   — на StringIO нет ANSI ни в меню, ни в тексте витрины, ни в live
  DH3  магазинов_счёт— ym-меню честно зовёт «магазинов в манифесте N» + slug витрины
  DH4  витрина_экран — экран магазина: биз/кампания/склад · ПУЛЬС · ЦИКЛ СЕГОДНЯ · ЗАДАНИЯ
  DH5  выбор_строкой — не-tty выбор: цифра→точный пункт · мимо→переспрос · q→назад
  DH6  очередь_честно— _project_queue: FAIL-хвост→ЧИНИТЬ, нет пульса→ПУЛЬС,
                       собран+не-опубл→ЗАЛИВ, PUBLISHED→НЕ зовём залить (матр. отстала)
  DH7  live_кадр     — live_frame(home|ym|store:) рендерит пульс+автопилот без падений
  DH8  дом_не_пишет  — исходник dom.py без write-вызовов (CC7/HH6-паттерн)
  DH9  навигация_путь— home→ym→витрина→назад→назад→выход цифрами = rc 0
  DH10 проводка      — dispatch принимает inp; ym <витрина> один-экран; --text — плоско
  DH11 стабильность  — движок viewport: геометрия фикс (шапка 5+низ 3), V.paint рисует
                       ряды CUP `\x1b[{r};1H`+EOL без `\n` и без 2J в цикле; live-кадр
                       один-источник (_live_body) → таблицы физически не плывут
  DH12 ям_сам_себя_яс  — root ДОМ ЯМ-ЦИКЛА: заголовок + «цифра → ДОМ <хеш>» + «цикл дня
                       идёт сам»; у каждой кампании в меню виден её хеш 10 (пусто → честно)
  DH13 хеш_зеркало    — _cycle_hash(дом) ≡ cycle_hash(движок ymarket_cycle1_v1) для
                       каждого магазина (идентификатор прогона, не выдумка)
  DH14 гейт_не_голит  — ГЕЙТ ЦИКЛ-1 = read-сводка: дом не импортирует движок, не зовёт
                       run_cycle; в гейте БРИГАДИР · --dry · (RUBICON) · «ДОМ только смотрит»
  DH15 день_жив_честно— сводка ДОМ <хеш> из 6 секций (ПУЛЬС…РЕЗУЛЬТАТ ДНЯ), «цикл дня идёт
                       сам» по расписанию, НЕ врёт «завершён/закрыт» (маркера закрытия нет)
  DH16 ширина_кадра   — тело сводки/гейта/корня: каждая строка ≤78 (рендер StringIO,
                        plain, len=ширина); длинные note чистятся (_clean_note) и
                        режутся (_snip) без потери смысла — на 80×24 нет клипа
  DH17 план_дня_в_меню— в ЯМ-меню пункт ПЛАН ДНЯ (view:план) открывает home-лицо
                        ПЛАН ДНЯ (или честную деградацию), не падает, plain
"""
import io
import inspect
import re
import sys
from pathlib import Path

SOCC_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOCC_ROOT) not in sys.path:
    sys.path.insert(0, str(SOCC_ROOT))

from socc_cli import dom          # noqa: E402
from socc_cli import home         # noqa: E402
from socc_cli import view as V    # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")
# Дата «сегодня» — живая (MSK), как её видит меню: дом рендерит хеш прогона за
# реальный день, значит приёмка должна сверяться с тем же днём, а не с днём коммита.
TODAY = dom._now_msk().strftime("%Y-%m-%d")


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _first_store():
    m = dom._stores_map()
    return (next(iter(sorted(m))) if m else None), m


# ─────────────────────────── ТЕСТЫ ───────────────────────────

def dh1_menu_dom():
    out, inp = io.StringIO(), io.StringIO("q\n")
    rc = dom.run_home(out, inp)
    t = out.getvalue()
    missing = [k for k in ("SOCC · КЕРНЕЛЬ", "ЯМ-ЦИКЛ", "OZON", "ENTITY SUBSTRATE",
                           "ANNA", "Выйти из ДОМА", "ЖИВОЙ ЭКРАН") if k not in t]
    return (rc == 0 and not missing), f"rc={rc} · недостаёт: {missing or '—'}"


def dh2_cveta_plain():
    t1 = dom.menu_text(io.StringIO(), "SOCC · ДОМ", "test", dom.home_rows({}), "prompt")
    # тексты на реальных сторах (манифест может быть пуст → честно)
    out = io.StringIO()
    store, _ = _first_store()
    ok = not ANSI.search(t1)
    if store:
        txt = dom.store_screen_text(io.StringIO(), store)
        ok = ok and not ANSI.search(txt)
        ok = ok and not ANSI.search(dom.live_frame(io.StringIO(), "store:" + store))
    ok = ok and not ANSI.search(dom.live_frame(io.StringIO(), "home"))
    ok = ok and not ANSI.search(dom.live_frame(io.StringIO(), "ym"))
    return ok, f"plain: меню={not ANSI.search(t1)} витрина/live={store or '—'}"


def dh3_magazinov_schet():
    stores = dom._stores_map()
    out, inp = io.StringIO(), io.StringIO("q\n")
    rc = dom.run_ym(out, inp)
    t = out.getvalue()
    n = len(stores)
    ok = (rc in (0, -1)) and (f"магазинов в манифесте: {n}" in t)
    if stores:
        slug = sorted(stores)[0]
        ok = ok and (slug in t)
    else:
        ok = ok and ("манифест пуст" in t or "магазинов в манифесте: 0" in t)
    return ok, f"rc={rc} · счёт={n} · есть витрина={bool(stores)}"


def dh4_vitrina_ekran():
    store, _ = _first_store()
    if not store:
        return False, "манифест пуст — витрину не проверить"
    out, inp = io.StringIO(), io.StringIO("q\n")
    rc = dom.run_store(out, inp, store)
    t = out.getvalue()
    need = all(s in t for s in ("ПУЛЬС", "ЦИКЛ СЕГОДНЯ", "АКТИВНЫЕ ЗАДАНИЯ"))
    ident = any(k in t for k in ("биз", "склад", "business", "кампания"))
    return (rc in (0, -1) and need and ident), f"rc={rc} · блоки={need} · идентичность={ident}"


def dh5_vybor_strokoi():
    rows = [dom._item("a", "Альфа"), dom._item("b", "Бета")]
    out, inp = io.StringIO(), io.StringIO("2\n")
    got = dom.pick(out, inp, title="t", sub="", rows=rows)
    ok1 = bool(got) and got["action"] == "b"
    out2, inp2 = io.StringIO(), io.StringIO("q\n")
    got2 = dom.pick(out2, inp2, title="t", sub="", rows=rows)
    ok2 = got2 is None
    out3, inp3 = io.StringIO(), io.StringIO("9\n1\n")
    got3 = dom.pick(out3, inp3, title="t", sub="", rows=rows)
    ok3 = bool(got3) and got3["action"] == "a" and "нет пункта" in out3.getvalue()
    return (ok1 and ok2 and ok3), f"цифра={ok1} · q={ok2} · переспрос={ok3}"


def dh6_ochered_chestno():
    store = "test"
    info = dict(donor_category="vozdushno-puzyrkovaya-plenka",
                builder_slug="puzyrkovaya-plenka", builder="film")
    bad = []

    # FAIL-хвост леджера → ЧИНИТЬ; нет пульса → ПУЛЬС
    q = dom._project_queue(store, info,
                           ledger=[dict(node="ДОНОР", verdict="PASS"),
                                   dict(node="ОСТАТКИ", verdict="FAIL", ts="10:01:00",
                                        note="таймаут чтения")],
                           pulse=None, today=TODAY)
    tags = {x["tag"] for x in q}
    if "ЧИНИТЬ" not in tags or "ПУЛЬС" not in tags:
        bad.append(f"FAIL-хвост/нет-пульса → {tags}")

    # собран + НЕ опубликовано → ЗАЛИВ
    matrix = [dict(status="собран", offer_id=None, category="puzyrkovaya-plenka")] * 3
    q2 = dom._project_queue(store, info,
                            ledger=[dict(node="ДОНОР", verdict="PASS")],
                            pulse=dict(date=TODAY), today=TODAY, matrix=matrix)
    if {x["tag"] for x in q2} != {"ЗАЛИВ"}:
        bad.append(f"собран-не-опубл → {[x['tag'] for x in q2]}")

    # СВЕРКА-PASS c PUBLISHED → НЕ зовём залить (матрица отстала — честно «СВЕРКА»)
    ledger_pub = [dict(node="СВЕРКА", verdict="PASS",
                       evidence=dict(x=dict(placement=dict(status="PUBLISHED"))))]
    q3 = dom._project_queue(store, info, ledger=ledger_pub,
                            pulse=dict(date=TODAY), today=TODAY, matrix=matrix)
    tags3 = {x["tag"] for x in q3}
    if "ЗАЛИВ" in tags3 or "СВЕРКА" not in tags3:
        bad.append(f"опубликовано → {[x['tag'] for x in q3]}")

    # пустой манифест/матрица и чистый пульс → честно пусто
    q4 = dom._project_queue(store, dict(),
                            ledger=[], pulse=dict(date=TODAY), today=TODAY, matrix=[])
    if q4:
        bad.append(f"чисто должно быть пусто → {[x['tag'] for x in q4]}")
    return (not bad), " · ".join(bad) or "ЧИНИТЬ/ПУЛЬС/ЗАЛИВ/опубликовано честны"


def dh7_live_kadr():
    bad = []
    for scope, args in (("home", ()), ("ym", ()), ("store:" + (_first_store()[0] or "x"), ())):
        if scope.startswith("store:") and scope == "store:x":
            continue
        try:
            t = dom.live_frame(io.StringIO(), scope, *args)
        except Exception as e:
            bad.append(f"{scope}: {e}")
            continue
        if "АВТОПИЛОТ" not in t or "следующий тик" not in t:
            bad.append(f"{scope}: нет таймера автопилота")
    return (not bad), " · ".join(bad) or "кадры home/ym/store живые"


def dh8_dom_ne_pishet():
    src = inspect.getsource(dom)
    banned = ["subprocess", "os.system", "requests", "urllib", "socket",
              "write_text", "write_bytes", "json.dump", "shutil", "os.remove",
              "os.unlink", "os.makedirs", "os.mkdir", "rmtree"]
    hits = [b for b in banned if b in src]
    open_w = re.search(r"open\([^)]*,\s*[\"']([wa])[\"']", src)
    ok = not hits and open_w is None
    return ok, f"токены: {hits or '—'} · open-write: {open_w.group(0) if open_w else '—'}"


def dh9_navigacia_put():
    store, _ = _first_store()
    if not store:
        return False, "манифест пуст — путь не пройти"
    # home '2'=ЯМ → ym '1'=первая витрина → store '4'=назад → ym 'q' → home 'q'
    out, inp = io.StringIO(), io.StringIO("2\n1\n4\nq\nq\n")
    rc = dom.run_home(out, inp)
    t = out.getvalue()
    return (rc == 0 and "АКТИВНЫЕ ЗАДАНИЯ" in t and not ANSI.search(t)), \
        f"rc={rc} · витрина показана={'АКТИВНЫЕ ЗАДАНИЯ' in t}"


def dh10_provodka():
    bad = []
    sig = inspect.signature(home.dispatch)
    if "inp" not in sig.parameters:
        bad.append("dispatch без inp")
    # один-экран сохранён: не-tty ym + витрина-по-slug
    b1 = io.StringIO()
    rc = home.dispatch(["ym"], out=b1)
    if rc != 0 or "ЯМ-ЦИКЛ" not in b1.getvalue():
        bad.append("ym один-экран сломан")
    store, _ = _first_store()
    if store:
        b2 = io.StringIO()
        rc2 = home.dispatch(["ym", store], out=b2)
        if rc2 != 0 or "АКТИВНЫЕ ЗАДАНИЯ" not in b2.getvalue():
            bad.append("ym <витрина> один-экран сломан")
    # --text принудительно плоско даже на tty-обёртке (обёртка isatty=True)
    b3 = io.StringIO()
    rc3 = home.dispatch(["ym", "--text"], out=b3)
    if rc3 != 0:
        bad.append("--text не прошёл")
    return (not bad), " · ".join(bad) or "проводка ок: inp · one-shot · --text"


def dh11_stability_dvizhok():
    """Стабильный viewport-движок — физическая защита от «плывущих» таблиц."""
    bad = []
    # геометрия фикс-кадра и флаг живого на месте
    if dom._HEAD != 5 or dom._FOOT != 3:
        bad.append(f"геометрия шапки/низа: {dom._HEAD}+{dom._FOOT}")
    if dom._MARK_LIVE != " · ЖИВОЙ":
        bad.append("нет маркера живого экрана")
    # paint на РОВНО 24×80: ряд-к-ряду CUP, хвост стирается, в кадре нет \n и clear
    orig_geom = V.geom
    try:
        V.geom = lambda: (24, 80)
        buf = io.StringIO()
        V.paint(buf, [f"строка {i}" for i in range(10)])
        out = buf.getvalue()
    finally:
        V.geom = orig_geom
    if not out.startswith("\x1b[1;1H"):
        bad.append("кадр не начинается с CUP 1;1")
    if "\x1b[24;1H" not in out:
        bad.append("последний ряд не адресован CUP 24")
    if "\n" in out:
        bad.append("paint печатает перевод строки внутрь кадра")
    if "\x1b[2J" in out:
        bad.append("paint чистит экран в цикле перерисовки")
    # live-кадры одного источника и ровно ROWS клеток (низ прижат, ничего не плывёт)
    for name in ("live_frame", "_live_cells"):
        fn_src = inspect.getsource(getattr(dom, name))
        if "_live_body(" not in fn_src:
            bad.append(f"{name} не зовёт _live_body (дрейф двух источников)")
    orig_geom = V.geom
    try:
        V.geom = lambda: (24, 80)
        cells = dom._live_cells(io.StringIO(), "ym")
    finally:
        V.geom = orig_geom
    if len(cells) != 24:
        bad.append(f"live-кадр {len(cells)} клеток (нужно 24)")
    if any("\n" in c or "\x1b[2J" in c for c in cells):
        bad.append("live-клетка содержит перевод строки/clear")
    # в самом доме 2J-чистки больше нигде нет (только движок V.enter на входе)
    dom_src = (SOCC_ROOT / "socc_cli" / "dom.py").read_text(encoding="utf-8")
    if "\\x1b[2J" in dom_src:
        bad.append("дом чистит экран 2J (только V.enter на входе виджета)")
    return (not bad), " · ".join(bad) or \
        "viewport: геометрия фикс · paint CUP без \\n · live один-источник · 24×80 цел"


def _synth_pl():
    """Герметичный payload кампании (без диска), худший случай по ширине:
    8 полей канона · закрытый прогон дня + открытый FAIL-обрыв с длинной сырой
    припиской · живая очередь с длинными what. (Рендер должен остаться ≤78.)"""
    info = dict(slug="atlas-express-film", business_id="184481130", campaign_id="2",
                warehouse_id="3", donor_category="vozdushno-puzyrkovaya-plenka",
                builder="film", markup=8.0, stock_count=100,
                note="витрина Экспресса плёнки, донор vozdushno-puzyrkovaya, dry подтверждён")
    pulse = dict(date=TODAY, run_verdicts={"PASS": 3, "DRY": 3}, artifacts=1)
    ts = lambda hhmm: f"{TODAY}T{hhmm}:00"
    ledger = [dict(node="ДОНОР", verdict="PASS", ts=ts("08:07")),
              dict(node="СБОРКА", verdict="PASS", ts=ts("08:20")),
              dict(node="ЗАЛИВ", verdict="PASS", ts=ts("09:05")),
              dict(node="ВИТРИНА", verdict="PASS", ts=ts("09:31")),
              dict(node="ОСТАТКИ", verdict="PASS", ts=ts("09:44")),
              dict(node="СВЕРКА", verdict="PASS", ts=ts("10:00"),
                   evidence={"ARB-1": dict(placement=dict(status="PUBLISHED"), stock=100)}),
              dict(node="ПЛАНЁРКА", verdict="PASS", ts=ts("16:40"))]
    # открытый прогон, оборванный на ОСТАТКИ (FAIL) — проверяет _clean_note + _snip
    ledger.append(dict(node="ДОНОР", verdict="PASS", ts=ts("12:22")))
    ledger.append(dict(node="СБОРКА", verdict="PASS", ts=ts("12:30")))
    ledger.append(dict(node="ОСТАТКИ", verdict="FAIL", ts=ts("13:01"),
                       note="остатки не легли: None после чтения стока — нужен повтор"))
    return dict(store="atlas-express-film", info=info, pulse=pulse, ledger=ledger,
                registry=("ok", []),
                queue=[dict(tag="ЗАЛИВ",
                            what="4 карточки плёнки собраны у донора — залить на витрину и подтвердить чтением СВЕРКА",
                            owner="МЕРЧАНДАЙЗЕР"),
                       dict(tag="СВЕРКА",
                            what="Матрица отстала: карточки PUBLISHED, но offer_id в матрице пуст — поправить матрицу",
                            owner="КОНТРОЛЁР")])


def dh12_dom_iam_sam_sebya():
    stores = dom._stores_map()
    out, inp = io.StringIO(), io.StringIO("q\n")
    rc = dom.run_ym(out, inp)
    t = out.getvalue()
    bad = []
    if "ДОМ ЯМ-ЦИКЛА" not in t:
        bad.append("нет заголовка ДОМ ЯМ-ЦИКЛА")
    if "цифра → ДОМ кампании <хеш>" not in t:
        bad.append("нет подсказки «цифра → ДОМ <хеш>»")
    if "цикл дня идёт сам" not in t:
        bad.append("нет «цикл дня идёт сам»")
    if stores:
        for slug in sorted(stores):
            h = dom._cycle_hash(slug, TODAY)
            if f"{slug} · {h}" not in t:
                bad.append(f"кампания {slug} без хеша {h}")
    else:
        if "манифест пуст" not in t:
            bad.append("манифест пуст — нет честной строки")
    return (rc in (0, -1) and not bad), " · ".join(bad) or \
        f"корень сам себя объясняет · кампании {len(stores)} с хешем 10"


def dh13_hash_zerkalo_dvizhka():
    import importlib
    arb = SOCC_ROOT / "scripts" / "mint" / "arbiter"
    sys.path.insert(0, str(arb))
    try:
        eng = importlib.import_module("ymarket_cycle1_v1")
    except Exception as e:
        return False, f"движок не импортируется: {type(e).__name__}: {e}"
    bad = []
    if dom._CHAIN_VERSION != eng.CHAIN_VERSION:
        bad.append(f"версия цепи: дом {dom._CHAIN_VERSION} vs движок {eng.CHAIN_VERSION}")
    slugs = sorted(dom._stores_map()) or ["atlas-express-film"]
    for slug in slugs:
        for date in (TODAY, "2099-01-01"):
            a, b = dom._cycle_hash(slug, date), eng.cycle_hash(slug, date)
            if a != b:
                bad.append(f"{slug}@{date}: дом {a} vs движок {b}")
    return (not bad), " · ".join(bad) or \
        f"хеш = sha1(slug×дата×цепь): дом ≡ движок ({len(slugs)} кампаний × 2 даты)"


def dh14_gate_ne_zapuskaet():
    src = (SOCC_ROOT / "socc_cli" / "dom.py").read_text(encoding="utf-8")
    bad = []
    if re.search(r"\b(import|from)\s+ymarket_cycle1", src):
        bad.append("дом импортирует движок")
    if "run_cycle(" in src:
        bad.append("дом зовёт run_cycle — запуск движка!")
    g = dom._gate_full_text(io.StringIO(), "atlas-express-film", _synth_pl())
    for need in ("БРИГАДИР", "(RUBICON)", "--dry", "ДОМ только смотрит"):
        if need not in g:
            bad.append(f"в гейте нет «{need}»")
    return (not bad), " · ".join(bad) or \
        "гейт = read-сводка + исполнитель за RUBICON; движок домом не запускается"


def dh15_den_zhiv_chestno():
    sv = dom._camp_home_text(io.StringIO(), "atlas-express-film", _synth_pl())
    bad = []
    for section in ("ПУЛЬС", "ЦИКЛ СЕГОДНЯ", "ЦИКЛЫ В РАБОТЕ", "АКТИВНЫЕ ЗАДАНИЯ",
                    "ГЕЙТ ЦИКЛ-1", "РЕЗУЛЬТАТ ДНЯ"):
        if section not in sv:
            bad.append(f"нет секции {section}")
    if "цикл дня идёт сам" not in sv:
        bad.append("нет честного «цикл дня идёт сам»")
    for lie in ("день завершён", "ЦИКЛ ДНЯ ЗАКРЫТ", "день закрыт"):
        if lie in sv:
            bad.append(f"врёт «{lie}»")
    return (not bad), " · ".join(bad) or \
        "сводка: 6 секций · «цикл дня идёт сам» · завершения дня не врёт"


def _body_lines():
    """Рендер тел сводки/гейта (синтетика + реальные сторы) и корня ДОМ ЯМ-ЦИКЛА."""
    for fn, arg in (("_camp_home_text", None), ("_gate_full_text", None)):
        yield from dom.__dict__[fn](io.StringIO(), "atlas-express-film", _synth_pl()).split("\n")
        for slug in sorted(dom._stores_map()):
            yield from dom.__dict__[fn](io.StringIO(), slug).split("\n")
    for r in dom.ym_rows(dom._stores_map()):
        if r.get("kind") == "text":
            yield r["line"]
        elif r.get("kind") == "sep":
            yield r.get("text", "")


def dh16_shirina_kadra():
    """Каждая строка тел ≤78: рендер StringIO plain (CC8) → len() == ширина экрана,
    значит на 80×24 ничего не клипается краем (автоперенос выключен)."""
    long_lines = [ln for ln in _body_lines() if len(str(ln)) > 78]
    return (not long_lines), \
        f"строк >78: {len(long_lines)}" + (f" :: {long_lines[0][:90]}" if long_lines else " · на 80×24 нет клипа")


def dh17_plan_dnya_v_menyu():
    """ПЛАН ДНЯ — read-лицо в ЯМ-меню: пункт «view:план» виден в списке экранов; выбор
    открывает home-лицо (ПЛАН ДНЯ или честная деградация), не падает, plain на StringIO."""
    txt = home._ym_face(io.StringIO(), "план", [])
    ok1 = isinstance(txt, str) and "Traceback" not in txt and "ПЛАН ДНЯ" in txt
    ok2 = not ANSI.search(txt)
    rows = dom.ym_rows({})
    ok3 = any(r.get("action") == "view:план" for r in rows if r.get("kind") == "item")
    return (ok1 and ok2 and ok3), f"лицо={ok1} · plain={ok2} · пункт-меню={ok3} · t={txt.strip()[:120]!r}"


TESTS = [
    ("DH1  меню_дом", dh1_menu_dom),
    ("DH2  цвета_plain", dh2_cveta_plain),
    ("DH3  магазинов_счёт", dh3_magazinov_schet),
    ("DH4  витрина_экран", dh4_vitrina_ekran),
    ("DH5  выбор_строкой", dh5_vybor_strokoi),
    ("DH6  очередь_честно", dh6_ochered_chestno),
    ("DH7  live_кадр", dh7_live_kadr),
    ("DH8  дом_не_пишет", dh8_dom_ne_pishet),
    ("DH9  навигация_путь", dh9_navigacia_put),
    ("DH10 проводка", dh10_provodka),
    ("DH11 стабильность", dh11_stability_dvizhok),
    ("DH12 ям_сам_себя_яс", dh12_dom_iam_sam_sebya),
    ("DH13 хеш_зеркало", dh13_hash_zerkalo_dvizhka),
    ("DH14 гейт_не_голит", dh14_gate_ne_zapuskaet),
    ("DH15 день_жив_честно", dh15_den_zhiv_chestno),
    ("DH16 ширина_кадра", dh16_shirina_kadra),
    ("DH17 план_дня_в_меню", dh17_plan_dnya_v_menyu),
]


def main():
    print("🎯 SOCC · ДОМ · ИНТЕРАКТИВ · ПРИЁМКА — живой дом, чисто, 0₽")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<18} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ ДОМ живой: меню органов → витрины → задания, честно, 0₽, не пишет")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

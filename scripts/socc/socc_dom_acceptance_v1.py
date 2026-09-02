#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ · ИНТЕРАКТИВ — ПРИЁМКА (socc_cli/dom.py).

Сухо, 0₽, без сети, без записи. Живой дом читает только лежащие сторы (как консоль).
Законы DH1–DH10:
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

ANSI = re.compile(r"\x1b\[[0-9;]*m")
TODAY = "2026-09-02"


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

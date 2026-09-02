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
"""
import io
import json
import os
import sys
import tempfile
import contextlib
import inspect
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


TESTS = [
    ("BR1  write_по_слову", br1_write_po_slovu),
    ("BR2  allowlist_строг", br2_allowlist_strog),
    ("BR3  секреты_не_утекают", br3_sekrety_ne_utekayut),
    ("BR4  мозг_честен_оффлайн", br4_mozg_chesten_offline),
    ("BR5  тишина_движка", br5_tishina_dvizhka),
    ("BR6  мама_наследование", br6_mama_nasledovanie),
    ("BR7  repl_сухо_и_живьё", br7_repl_suho_i_zhivyo),
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

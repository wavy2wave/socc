#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ — ПРИЁМКА единого read-хаба (socc_cli/home.py).

Сухо, 0₽, без сети, без записи. Дом читает только лежащие сторы (как консоль).
Законы HH1–HH8:
  HH1  дом_рендер    — дашборд: лента + все органы (КЕРНЕЛЬ/ЯМ/OZON/SUBSTRATE/ANNA/MIGRATION)
  HH2  цвета_plain   — на StringIO нет ANSI (CC8) ни в дашборде, ни в ЯМ-лице
  HH3  зонды_честные — каждый зонд даёт (state, note, hint), state∈{live,idle,off},
                       никогда не падает (fail-soft), файла нет → честная строка
  HH4  входы_диспетч — dispatch: []/home → 0; ym/ozon/substrate/anna/kernel → 0;
                       неизвестный орган → 1 + справка
  HH5  лицо_ям       — socc ym штаб рендерит ШТАБ (или честно говорит, что консоль
                       не импортировалась); socc ym дело не падает
  HH6  дом_не_пишет  — исходник home.py без write-вызовов (CC7-паттерн)
  HH7  алиас_цикл    — scripts/mint/arbiter/CYCLE делегирует в socc_cli.home
  HH8  проводка_socc — socc_cli/cli.py знает _HOME_KEYS + cmd_home + help-блок
"""
import io
import inspect
import re
import sys
from pathlib import Path

SOCC_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOCC_ROOT) not in sys.path:
    sys.path.insert(0, str(SOCC_ROOT))

from socc_cli import home          # noqa: E402

ORGANS = ["SOCC · КЕРНЕЛЬ", "ЯМ-ЦИКЛ", "OZON", "ENTITY SUBSTRATE", "ANNA", "MIGRATION"]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


# ─────────────────────────── ТЕСТЫ ───────────────────────────

def hh1_dom_render():
    t = home.home_text(out=io.StringIO())
    missing = [k for k in ORGANS if k not in t]
    need = all(s in t for s in ("ОРГАНЫ", "ВХОДЫ", "ПРАВИЛА", "0₽ read", "RUBICON"))
    return (not missing and need), f"недостаёт органов: {missing or '—'} · метки={need}"


def hh2_cveta_plain():
    t = home.home_text(out=io.StringIO())
    ok1 = not ANSI.search(t)
    ym = home._ym_face(io.StringIO(), "штаб", [])
    ok2 = not ANSI.search(ym)
    return (ok1 and ok2), f"дашборд={ok1} · ym-штаб={ok2}"


def hh3_zondy_chestnye():
    bad = []
    for o in home._ORGANS:
        try:
            st, note, hint = o["probe"]()
        except Exception as e:
            bad.append(f"{o['key']}: исключение {e}")
            continue
        if st not in ("live", "idle", "off"):
            bad.append(f"{o['key']}: state {st!r}")
        if not isinstance(note, str) or not isinstance(hint, str):
            bad.append(f"{o['key']}: тип note/hint не str")
    return (not bad), " · ".join(bad) or "6 зондов честны"


def hh4_vhody_dispetcher():
    bad = []
    cases = [([], 0), (["home"], 0), (["ozon"], 0), (["substrate"], 0),
             (["anna"], 0), (["kernel"], 0), (["migrate"], 0), (["bogus"], 1)]
    for argv, want in cases:
        buf = io.StringIO()
        rc = home.dispatch(argv, out=buf)
        if rc != want:
            bad.append(f"{argv or ['']}: rc {rc}≠{want}")
    return (not bad), " · ".join(bad) or "8 входов ок (0/1)"


def hh5_lico_yam():
    bad = []
    buf = io.StringIO()
    home.dispatch(["ym", "штаб"], out=buf)
    t = buf.getvalue()
    if not (("ШТАБ" in t) or ("не импортировалась" in t)):
        bad.append("штаб не рендерит ШТАБ и не деградирует честно")
    buf2 = io.StringIO()
    rc2 = home.dispatch(["ym", "дело"], out=buf2)
    if rc2 != 0 or len(buf2.getvalue()) < 10:
        bad.append(f"ym дело rc={rc2} длина={len(buf2.getvalue())}")
    return (not bad), " · ".join(bad) or "ym штаб+дело ок"


def hh6_dom_ne_pishet():
    src = inspect.getsource(home)
    banned = ["subprocess", "os.system", "requests", "urllib", "socket",
              "write_text", "write_bytes", "json.dump", "shutil", "os.remove",
              "os.unlink", "os.makedirs", "os.mkdir", "rmtree"]
    hits = [b for b in banned if b in src]
    open_w = re.search(r"open\([^)]*,\s*[\"']([wa])[\"']", src)
    ok = not hits and open_w is None
    return ok, f"запрещённые-токены: {hits or '—'} open-write: {open_w.group(0) if open_w else '—'}"


def hh7_alias_cycle():
    p = SOCC_ROOT / "scripts/mint/arbiter/CYCLE"
    if not p.exists():
        return False, "CYCLE файла нет"
    src = p.read_text(encoding="utf-8")
    ok = ("socc_cli.home" in src) and ("dispatch" in src)
    return ok, "CYCLE → socc_cli.home.dispatch"


def hh8_provodka_socc():
    p = SOCC_ROOT / "socc_cli/cli.py"
    src = p.read_text(encoding="utf-8")
    ok = ("_HOME_KEYS" in src and "cmd_home" in src
          and "SOCC · ДОМ" in src and "socc ym" in src)
    return ok, "cli.py: _HOME_KEYS+cmd_home+ДОМ-help"


TESTS = [
    ("HH1  дом_рендер", hh1_dom_render),
    ("HH2  цвета_plain", hh2_cveta_plain),
    ("HH3  зонды_честные", hh3_zondy_chestnye),
    ("HH4  входы_диспетч", hh4_vhody_dispetcher),
    ("HH5  лицо_ям", hh5_lico_yam),
    ("HH6  дом_не_пишет", hh6_dom_ne_pishet),
    ("HH7  алиас_цикл", hh7_alias_cycle),
    ("HH8  проводка_socc", hh8_provodka_socc),
]


def main():
    print("🎯 SOCC · ДОМ · ПРИЁМКА — единый read-хаб органов, чисто, 0₽")
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
        print("✅ ДОМ открывает все органы честно: 6 карточек · 8 входов · 0₽ · не пишет")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

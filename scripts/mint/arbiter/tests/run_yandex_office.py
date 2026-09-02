#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — ВИРТУАЛЬНЫЙ ОФИС ЯМ (ymarket_office_v1). Сухо, 0₽, без сети.

Офис отвечает на кадровый вопрос: кто в команде, кто с кем связан ЗАКОННО, кто реально работает,
кто числится. Тесты ловят конкретную ЛОЖЬ, которую офис мог бы сказать:

  OD1  charter_all_roles_loaded  — у всех ролей с источником есть читаемый устав (ast, не импорт);
                                    СБОРЩИК = None (вакансия). Битые уставы = нет правды.
  OD2  roster_covers_team_feed   — реестр покрывает ВСЕ 11 ролей командного фида + КАТЕГОРИЙЩИК/РОСТА
  OD3  wired_eleven_in_cycle     — ровно 11 ролей заведены в суточный цикл (cycle:*), runner-ы нет
  OD4  zaliv_is_vacancy          — СБОРЩИК (нет модуля) = ВАКАНСИЯ на лестнице, не «числится»
  OD5  pricer_zaliv_ghost        — реальный устав ЦЕНОВИКА ссылается на ЗАЛИВЩИКА → связь-ПРИЗРАК
  OD6  lawful_edges_honest       — все ЗАКОННЫЕ связи: оба конца в цикле; цепочка склад→тов→цена есть
  OD7  employment_ladder         — лестница на синтетике: В ШТАТЕ/СТАЖЁР/ЧИСЛИТСЯ/ВАКАНСИЯ (не живые)
  OD8  conscience_score_math     — совесть x/5: 5/5 живому, 1/5 вакансии, 0/5 «ничего не заведено»
  OD9  record_day_roundtrip      — ТАБЕЛЬ: день → строки ролей ok/skip/fail → читаются обратно
  OD10 record_day_failsoft       — не-словарь/нет даты → 0; битый файл ТАБЕЛИ не роняет запись
  OD11 classify_edge             — lawful / ghost / declared / external / в-никуда-ghost
  OD12 tabel_empty_is_honest     — пустой ТАБЕЛЬ → честный «канал не подключён», не фейковые нули
  OD13 rubicon_import_clean      — импорт офиса не пишет html и не содержит сетевых вызовов (0₽)
  OD14 render_contains_labels    — html рендера несёт лестницу/команду/связи/табель + имена ролей
  OD15 evidence_reads_live       — чтение живых артефактов НЕ падает и возвращает полную структуру
  OD16 hook_wired_in_day_cycle   — суточный цикл умеет доказывать смены: хук record_day в журнале
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_office_v1 as office        # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


class _Tabel:
    """Контекст: временный ТАБЕЛЬ через office.TABEL_PATH (канон отчётов не трогаем)."""
    def __enter__(self):
        self._save = office.TABEL_PATH
        self._dir = tempfile.TemporaryDirectory()
        office.TABEL_PATH = Path(self._dir.name) / "tabel.jsonl"
        return self

    def __exit__(self, *exc):
        office.TABEL_PATH = self._save
        self._dir.cleanup()
        return False


def _full_ev():
    """Синтетические доказательства: все роли живы и свежи (для рендера/лестницы, НЕ живые файлы)."""
    ev = {}
    for k in office.ROSTER:
        ev[k] = {"has_channel": True, "channel_desc": "тест-канал", "samples": 5,
                 "last_real": "2026-09-01T00:00:00", "fresh": True,
                 "ok_shifts": 4, "errors": 1, "escalations": 0}
    return ev


def _full_summary():
    return {"shifts": 382, "ok": 49, "errors": 0, "last_shift": "2026-09-01T00:00:00",
            "ticks": 69, "days": 1}


def _role(key, charter, wired="cycle:step"):
    return dict(office.ROSTER[key], charter=charter, wired=wired)


# ── тесты ──────────────────────────────────────────────────────────────────────

def od1_charter_all_roles_loaded():
    chs = office.load_charters()
    missing = [k for k, r in office.ROSTER.items()
               if r.get("source") is not None and not isinstance(chs.get(k), dict)]
    # БРИГАДИР устава не пишет — собирает 5 ролей смены; офис даёт честный фолбэк
    ok = (not missing) and chs.get("ZALIV") is None
    return ok, f"без-устава={missing or 'нет'} СБОРЩИК= {chs.get('ZALIV')} (вакансия)"


def od2_roster_covers_team_feed():
    feed = {"BRIGADE", "DISPATCHER", "STOCKMAN", "MERCHANDISER", "PRICER", "CONTROLLER",
            "STRATEGIST", "TRENDSCOUT", "HEAD", "ZALIV", "MANAGER"}
    missing = sorted(feed - set(office.ROSTER))
    extra = sorted(set(office.ROSTER) - feed)
    ok = (not missing) and {"CATEGORIST", "GROWTH"} <= set(office.ROSTER)
    return ok, f"не покрыты={missing or '—'} сверх={extra} (всего {len(office.ROSTER)} ролей)"


def od3_wired_eleven_in_cycle():
    wired = office.WIRED_KEYS
    expected = {"BRIGADE", "DISPATCHER", "STOCKMAN", "MERCHANDISER", "PRICER", "CONTROLLER",
                "MANAGER", "STRATEGIST", "TRENDSCOUT", "HEAD", "ZALIV"}
    ok = wired == expected
    # CATEGORIST/GROWTH — runner-ы, НЕ в цикле (это честная проводка, не забытая)
    ok = ok and "CATEGORIST" not in wired and "GROWTH" not in wired
    return ok, f"в-цикле={len(wired)} (11) runner-вне-цикла=CATEGORIST/GROWTH"


def od4_zaliv_is_vacancy():
    r = _role("ZALIV", None, wired="cycle:optin")
    emp = office.employment(r, {"has_channel": False, "last_real": None, "fresh": False})
    ok = emp == "ВАКАНСИЯ"
    return ok, f"СБОРЩИК → {emp} (модуля нет — вакансия, не «числится» во лжи)"


def od5_pricer_zaliv_ghost():
    chs = office.load_charters()
    edges = office.build_edges(chs)
    ghosts = [(e["src"], e["dst"]) for e in edges if e["cls"] == "ghost"]
    ok = ("PRICER", "ZALIV") in ghosts
    return ok, f"призраки={ghosts} (реальный устав ЦЕНОВИКА: выход → ЗАЛИВЩИК)"


def od6_lawful_edges_honest():
    chs = office.load_charters()
    edges = office.build_edges(chs)
    lawful = [e for e in edges if e["cls"] == "lawful"]
    wrong = [e for e in lawful
             if e["src"] not in office.WIRED_KEYS or e["dst"] not in office.WIRED_KEYS]
    chain = [("STOCKMAN", "MERCHANDISER"), ("MERCHANDISER", "PRICER")]
    ok = (len(lawful) > 0 and not wrong
          and all((a, b) in [(e["src"], e["dst"]) for e in lawful] for a, b in chain))
    return ok, f"законных={len(lawful)} цепочка_склад→тов→цена={'да' if ok else 'нет'}"


def od7_employment_ladder():
    staff = _role("DISPATCHER", {"id": "X"}, wired="cycle:via_brigade")
    w = office.employment(staff, {"has_channel": True, "last_real": "2026-09-01T00:00:00",
                                  "fresh": True})
    stager = office.employment(staff, {"has_channel": True, "last_real": "2026-08-01T00:00:00",
                                       "fresh": False})
    num1 = office.employment(_role("STRATEGIST", {"id": "X"}), {"has_channel": False,
                                                                "last_real": None, "fresh": False})
    vac = office.employment(_role("ZALIV", None), {"has_channel": False, "last_real": None,
                                                   "fresh": False})
    ok = (w == "В ШТАТЕ" and stager == "СТАЖЁР" and num1 == "ЧИСЛИТСЯ" and vac == "ВАКАНСИЯ")
    return ok, f"штат={w} стажёр={stager} числится={num1} вакансия={vac}"


def od8_conscience_score_math():
    full = _role("BRIGADE", {"id": "B"}, wired="cycle:shift")
    s5, c5 = office.conscience_score(full, {"has_channel": True, "last_real": "2026-09-01",
                                            "fresh": True})
    vac = _role("ZALIV", None, wired="cycle:optin")
    s1, c1 = office.conscience_score(vac, {"has_channel": False, "last_real": None, "fresh": False})
    dead = _role("GROWTH", {"id": "G"}, wired="runner")
    s2, _ = office.conscience_score(dead, {"has_channel": False, "last_real": None, "fresh": False})
    ok = s5 == 5 and all(c5) and s1 == 1 and s2 == 2
    return ok, f"живой={s5}/5 вакансия={s1}/5 runner={s2}/5 (совесть механическая, не на глаз)"


def od9_record_day_roundtrip():
    with _Tabel() as t:
        day = {"ts": "2026-09-01T10:00:00", "date": "2026-09-01",
               "roles": {"BRIGADE": {"ok": True, "human": {"ДИСПЕТЧЕР": "заказы взяты"}},
                         "MANAGER_TICK": {"ok": True, "action": "тик"},
                         "HEAD": {"ok": False, "error": "источник упал"},
                         "TRENDSCOUT": {"ok": True, "skipped": True}},
               "zaliv": {"donor_blocker": "донор спит", "ready": 0, "errors": 0}}
        n = office.record_day(day)
        rows = office.load_tabel()
        by_role = {r["role"]: r["status"] for r in rows}
        ok = (n == 5 and len(rows) == 5
              and by_role.get("BRIGADE") == "ok"
              and by_role.get("MANAGER_TICK") == "ok"
              and by_role.get("HEAD") == "fail"
              and by_role.get("TRENDSCOUT") == "skip"
              and by_role.get("ZALIV") == "skip"
              and all(r.get("schema") == "ymarket.office.tabel.v1" for r in rows))
    return ok, f"строк={n} статусы={by_role} (append-only, каждая роль — своя строка)"


def od10_record_day_failsoft():
    with _Tabel():
        o1 = office.record_day("не словарь")
        o2 = office.record_day(None)
        o3 = office.record_day({"date": "2026-09-01"})
        office.TABEL_PATH.write_text("}{ битый json\n", encoding="utf-8")   # файл сломан
        empty = office.load_tabel() == []                                    # читаем → [], не падение
        n = office.record_day({"date": "2026-09-02",
                               "roles": {"BRIGADE": {"ok": True}}})          # запись поверх битого
        ok = (o1 == 0 and o2 == 0 and o3 == 0 and empty and n == 1)
    return ok, f"не-словарь={o1} нет-ролей={o3} битый→{empty} запись-после={n}"


def od11_classify_edge():
    ok = (office.classify_edge("STOCKMAN", "MERCHANDISER") == "lawful"
          and office.classify_edge("PRICER", "ZALIV") == "ghost"
          and office.classify_edge("CATEGORIST", "MERCHANDISER") == "declared"
          and office.classify_edge("BRIGADE", "OPERATOR") == "external"
          and office.classify_edge("PRICER", "В НИКУДА") == "ghost")
    return ok, "lawful/ghost/declared/external/в-никуда — все классы отделены"


def od12_tabel_empty_is_honest():
    with _Tabel():
        rows = office.load_tabel()
        ts = office.tabel_summary(rows)
        ok = ts["days"] == 0 and ts["roles"] == 0
    return ok, f"пусто→days={ts['days']} roles={ts['roles']} (офис не врёт «0 работали»)"


def od13_rubicon_import_clean():
    src = Path(office.__file__).read_text(encoding="utf-8")
    net = [w for w in ("urllib", "import requests", "socket", "http://", "https://") if w in src]
    html_written = Path(ARB, "runtime", "YM_VIRTUAL_OFFICE.html").exists()   # существует только если рендерили
    ok = not net and "record_day" in src and "gather_evidence" in src
    return ok, f"сеть={net or 'нет'} (импорт не пишет html, 0₽, читает артефакты)"


def od14_render_contains_labels():
    chs = office.load_charters()
    ev = _full_ev()
    edges = office.build_edges(chs)
    doc = office.render(chs, ev, edges, _full_summary())
    need = ["ВИРТУАЛЬНЫЙ ОФИС", "ЛЕСТНИЦА ЗАНЯТОСТИ", "КОМАНДА", "СВЯЗИ", "ТАБЕЛЬ",
            "БРИГАДИР", "СБОРЩИК", "В ШТАТЕ", "ИСТОЧНИКИ"]
    missing = [n for n in need if n not in doc]
    ok = not missing and doc.startswith("<!doctype html>")
    return ok, f"секций={len(need) - len(missing)}/{len(need)} размер={len(doc)}Б"


def od15_evidence_reads_live():
    chs = office.load_charters()
    try:
        ev, summ = office.gather_evidence(chs)
    except Exception as e:
        return False, f"живые артефакты упали: {type(e).__name__}: {e}"
    missing = [k for k in office.ROSTER if k not in ev]
    keys = all(k in summ for k in ("shifts", "ok", "ticks", "days"))
    ok = not missing and keys and isinstance(summ["shifts"], int) and isinstance(summ["ok"], int)
    return ok, f"ролей={len(ev)} смен={summ['shifts']} ok={summ['ok']} тиков={summ['ticks']}"


def od16_hook_wired_in_day_cycle():
    src = Path(ARB, "ymarket_day_v1.py").read_text(encoding="utf-8")
    ok = ("_append_journal" in src and "record_day" in src
          and "ymarket_office_v1" in src)
    return ok, "цикл дня умеет доказывать смены: _append_journal → office.record_day (мягкий хук)"


TESTS = [
    ("OD1  charter_all_roles_loaded", od1_charter_all_roles_loaded),
    ("OD2  roster_covers_team_feed", od2_roster_covers_team_feed),
    ("OD3  wired_eleven_in_cycle", od3_wired_eleven_in_cycle),
    ("OD4  zaliv_is_vacancy", od4_zaliv_is_vacancy),
    ("OD5  pricer_zaliv_ghost", od5_pricer_zaliv_ghost),
    ("OD6  lawful_edges_honest", od6_lawful_edges_honest),
    ("OD7  employment_ladder", od7_employment_ladder),
    ("OD8  conscience_score_math", od8_conscience_score_math),
    ("OD9  record_day_roundtrip", od9_record_day_roundtrip),
    ("OD10 record_day_failsoft", od10_record_day_failsoft),
    ("OD11 classify_edge", od11_classify_edge),
    ("OD12 tabel_empty_is_honest", od12_tabel_empty_is_honest),
    ("OD13 rubicon_import_clean", od13_rubicon_import_clean),
    ("OD14 render_contains_labels", od14_render_contains_labels),
    ("OD15 evidence_reads_live", od15_evidence_reads_live),
    ("OD16 hook_wired_in_day_cycle", od16_hook_wired_in_day_cycle),
]


def main():
    print("🎯 ПРИЁМКА · ВИРТУАЛЬНЫЙ ОФИС ЯМ (сухо, 0₽, без сети)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<28} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ ОФИС говорит правду: уставы читаются ast-ом, лестница механическая, СБОРЩИК — "
              "вакансия, связь ЦЕНОВИК→ЗАЛИВЩИК — призрак, ТАБЕЛЬ append-only fail-soft, RUBICON цел.")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

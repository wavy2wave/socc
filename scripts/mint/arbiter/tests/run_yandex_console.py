#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""КОНСОЛЬ-ЯМ · ПРИЁМКА (ymarket_console_v1). Read-кабинет SOCC-ЯМ: ШТАБ-дайв + ДЕЛО.
Сухо, 0₽, без сети, без записи. ВСЕ функции с инъекцией строк (tabel_rows/journal_rows/
charters/ev/doc) — герметичный тест не читает MEMORY_WAVE и не пишет на диск.

Законы консоли (спека YM_CONSOLE_V1.md):
  CC1  роль_карточка      — имя/кластер/модуль/занятость/совесть/табель-строки
  CC2  пустая_табель      — честные пустые: не звалась / табели нет (без выдумки)
  CC3  alias_имя          — русское имя/регистр → ключ роли (или честный None)
  CC4  день_карточка      — из журнала: дата/burning/top_move/kpis; журнал пуст → честно
  CC5  кпи_свертка        — DAY/WEEK/MONTH рендер из инъекции журнала
  CC6  артефакты_сводка   — матрица/библиотека/точки counts из фикстур (честные пустые)
  CC7  консоль_не_пишет   — исходник без write-вызовов (паттерн BR-проверок исходника)
  CC8  цвета_plain        — в StringIO нет ANSI-кодов (BR14-стиль, out-aware)
  CC9  задания_блок       — read-блок ЗАДАНИЯ: реестр-инъекция → открытые по важности с
                            владельцем; «реестра ещё нет» честно; не пишет (CC7-источник)
"""
import io
import inspect
import re
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_console_v1 as console   # noqa: E402  (read-орган под тестом)
import ymarket_office_v1 as office     # noqa: E402  (реестр ролей/уставы/совесть)

CH = office.load_charters()            # уставы из репозитория (read-only, НЕ MEMORY_WAVE)

TODAY = "2026-09-02"
TODAY_DT = date(2026, 9, 2)


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _row(role, d, status="ok", ts=None, evidence="", err=None):
    """Строка ТАБЕЛИ (schema ymarket.office.tabel.v1)."""
    return {"schema": "ymarket.office.tabel.v1", "date": d,
            "ts": ts or f"{d}T09:00:00.000000+00:00", "role": role,
            "status": status, "error": err, "evidence": evidence}


def _ev(role, **kw):
    """Эвиденс-фикстура для одной роли (остальное дозаполнит _ev_for нулями)."""
    base = {"has_channel": False, "channel_desc": None, "samples": 0, "last_real": None,
            "fresh": False, "ok_shifts": 0, "errors": 0, "escalations": 0}
    base.update(kw)
    return {role: base}


def _day(ts, kpis, burning=0, top_move=""):
    """Строка журнала суточного цикла (schema kpi._read_rows)."""
    return {"ts": ts, "date": ts[:10], "kpis": kpis,
            "burning": burning, "top_move": top_move}


# ─────────────────────────── ТЕСТЫ ───────────────────────────

def cc1_rol_kartochka():
    """Карточка роли: имя/кластер/модуль/занятость/совесть/табель-строки из инъекции."""
    ev = _ev("BRIGADE", has_channel=True, last_real="2026-09-02T08:00:00+00:00", fresh=True,
             ok_shifts=1)
    rows = [_row("BRIGADE", TODAY, "ok", evidence="6/6 экспресс-заказов в 60м")]
    txt = console.role_card("BRIGADE", out=io.StringIO(), tabel_rows=rows,
                            now="2026-09-02T10:00:00+00:00", charters=CH, ev=ev)
    need = ["РОЛЬ · БРИГАДИР", "кластер master", "модуль ymarket_brigade_v1.py",
            "проводка cycle:shift", "занятость: В ШТАТЕ", "совесть 5/5",
            "сегодня (2026-09-02): ok", "за всё время: 1 дн · ок 1 · skip 0 · fail 0",
            "последняя работа: 2026-09-02 · ok"]
    missing = [k for k in need if k not in txt]
    return (not missing), f"недостаёт: {missing or '—'}"


def cc2_pustaya_tabel_chestno():
    """Нет строк роли сегодня → «не звалась»; журнал пуст → «табели нет» (не выдумываем)."""
    # (а) роли нет сегодня, но есть вчера → «не звалась в цикл», история вчера видна
    ev = _ev("DISPATCHER", has_channel=True)
    rows_old = [_row("DISPATCHER", "2026-09-01", "ok", evidence="доставки в срок")]
    a = console.role_card("ДИСПЕТЧЕР", out=io.StringIO(), tabel_rows=rows_old,
                          now=TODAY + "T10:00:00+00:00", charters=CH, ev=ev)
    a_ok = ("сегодня (2026-09-02): не звалась в цикл" in a
            and "за всё время: 1 дн · ок 1 · skip 0 · fail 0 · с 2026-09-01" in a)
    # (б) журнал вообще пуст → честно «табели нет», без цифр-выдумки
    b = console.role_card("ДИСПЕТЧЕР", out=io.StringIO(), tabel_rows=[],
                          now=TODAY + "T10:00:00+00:00", charters=CH, ev=ev)
    b_ok = ("табели нет — суточный цикл ещё не провели" in b
            and "в табели нет — день за роль не записывался" in b)
    return (a_ok and b_ok), f"вчера-есть-не_звалась={a_ok} журнал-пуст-честно={b_ok}"


def cc3_alias_imya():
    """Русское имя/регистр/пробелы → ключ роли; незнакомое → честный None."""
    ok1 = console.role_key("ДИСПЕТЧЕР") == "DISPATCHER"
    ok2 = console.role_key("диспетчер") == "DISPATCHER"
    ok3 = console.role_key("Бригадир") == "BRIGADE"
    ok4 = console.role_key("УПРАВЛЯЮЩИЙ") == "MANAGER"
    ok5 = console.role_key("  товаровед ") == "MERCHANDISER"
    ok6 = console.role_key("торгаш") is None
    return (ok1 and ok2 and ok3 and ok4 and ok5 and ok6), (
        f"ДИСПЕТЧЕР={ok1} диспетчер={ok2} Бригадир={ok3} УПРАВЛЯЮЩИЙ={ok4} "
        f"товаровед-пробелы={ok5} незнакомый=None={ok6}")


def cc4_den_kartochka():
    """Последний снимок дня: дата/burning/top_move/kpis; пустой журнал → честно."""
    kpis = {"cards_tracked": 7, "cards_live": 7, "cards_live_verified": 0,
            "cards_errored": 7, "ready_to_publish": 4, "avg_content_rating": 86.7,
            "urgent_orders": 0}
    rows = [_day("2026-09-01T11:00:00+00:00", {"cards_tracked": 5}, 1, "A"),
            _day("2026-09-02T11:17:00.556762+00:00", kpis, 2, "ASSORTMENT_WIDEN")]
    txt = console.day_card(out=io.StringIO(), journal_rows=rows)
    need = ["день 2026-09-02", "в работе 7", "live 7", "сверено 0", "готово к публикации 4",
            "контент 86.7", "горящие заказы 0", "горит: 2", "топ-ход: ASSORTMENT_WIDEN"]
    missing = [k for k in need if k not in txt]
    empty = console.day_card(out=io.StringIO(), journal_rows=[])
    empty_ok = "журнала нет — ни одного суточного цикла ещё не провели" in empty
    return (not missing and empty_ok), f"недостаёт: {missing or '—'} · пустой-честно={empty_ok}"


def cc5_kpi_svertka():
    """DAY/WEEK/MONTH рендер из инъекции журнала; пустой журнал → «журнал пуст»."""
    kpis2 = {"cards_tracked": 7, "cards_live": 7, "cards_errored": 7,
             "ready_to_publish": 4, "avg_content_rating": 86.7, "urgent_orders": 0}
    rows = [_day("2026-09-01T11:00:00+00:00", {"cards_tracked": 5, "cards_errored": 3,
                                               "avg_content_rating": 80.0, "urgent_orders": 1}, 1, "A"),
            _day("2026-09-02T11:00:00+00:00", kpis2, 2, "B")]
    txt = console.kpi_text(out=io.StringIO(), journal_rows=rows, today=TODAY_DT)
    need = ["KPI DAY / WEEK / MONTH", "ДЕНЬ · дней в окне: 1", "НЕДЕЛЯ · дней в окне: 2",
            "МЕСЯЦ · дней в окне: 2", "карточек веду", "заполненность", "истории не хватает"]
    # «истории не хватает» НЕ должно быть — во всех окнах есть строки
    has_need = all(n in txt for n in need[:6])
    no_empty = need[6] not in txt
    empty = console.kpi_text(out=io.StringIO(), journal_rows=[], today=TODAY_DT)
    empty_ok = "журнал пуст" in empty
    return (has_need and no_empty and empty_ok), (
        f"D/W/M-рендер={has_need} без-пустого-окна={no_empty} пустой-честно={empty_ok}")


def cc6_artefakty_svodka():
    """Матрица/библиотека/точки — counts из фикстур; пустые фикстуры → честные пустые."""
    mat = {"rows": {"o1": {"status": "на-витрине"}, "o2": {"status": "собран"},
                    "o3": {"status": "залит"}}}
    lib = {"goods": {"o1": {"store_slug": "atlas-express-film", "category_slug": "plenka",
                            "events": [{"kind": "stock"}]}}}
    pts = {"points": {"p1": {}, "p2": {}}, "bindings": {"o1": "p1"}}
    txt = console.artifacts_text(out=io.StringIO(), matrix_doc=mat,
                                 library_doc=lib, points_doc=pts)
    need = ["матрица · всего 3", "на-витрине 1", "собран 1", "залит 1",
            "библиотека · артикулов 1 · stock-событий 1", "plenka 1",
            "точки · точек 2 · привязок 1"]
    missing = [k for k in need if k not in txt]
    # пустые фикстуры → честные пустые строки
    emp = console.artifacts_text(out=io.StringIO(), matrix_doc={"rows": {}},
                                 library_doc={"goods": {}}, points_doc={})
    emp_ok = ("матрица · всего 0" in emp and "библиотека · артикулов нет" in emp
              and "точки · точек нет" in emp)
    return (not missing and emp_ok), f"недостаёт: {missing or '—'} · пустые-честно={emp_ok}"


def cc7_console_ne_pishet():
    """Исходник КОНСОЛЬ-ЯМ без write-путей: нет шелла/сети/открытия на запись/удаления."""
    src = inspect.getsource(console)
    banned = ["subprocess", "os.system", "requests", "urllib", "socket",
              "write_text", "write_bytes", "json.dump", "shutil", "os.remove",
              "os.unlink", "os.makedirs", "os.mkdir"]
    hits = [b for b in banned if b in src]
    open_w = re.search(r"open\([^)]*,\s*[\"']([wa])[\"']", src)
    ok = not hits and open_w is None
    return ok, f"запрещённые-токены: {hits or '—'} open-write: {open_w.group(0) if open_w else '—'}"


def cc8_cveta_plain():
    """На не-tty выходе (StringIO) рендер консоли не содержит ANSI-кодов (BR14-стиль)."""
    ev = _ev("BRIGADE", has_channel=True, last_real="2026-09-02T08:00:00+00:00", fresh=True)
    rows = [_row("BRIGADE", TODAY, "ok", evidence="смена чиста")]
    texts = [
        console.staff_summary(out=io.StringIO(), tabel_rows=rows, now=TODAY + "T10:00:00+00:00",
                              charters=CH, ev=ev),
        console.role_card("BRIGADE", out=io.StringIO(), tabel_rows=rows,
                          now=TODAY + "T10:00:00+00:00", charters=CH, ev=ev),
        console.day_card(out=io.StringIO(),
                         journal_rows=[_day("2026-09-02T11:00:00+00:00", {"cards_tracked": 7}, 0, "")]),
        console.tabel_text(out=io.StringIO(), tabel_rows=rows, window="today",
                           now=TODAY + "T10:00:00+00:00"),
    ]
    leaks = [repr(t[:40]) for t in texts if "\x1b[" in t]
    return (not leaks), f"ANSI в StringIO: {leaks or '—'}"


def cc9_zadaniya_blok():
    """ЗАДАНИЯ read-блок: реестр-инъекция → открытые по важности с владельцем; честные пустые."""
    def _task(i, what, owner, prio=50, urg="normal", cat="pricing", store="", st="open"):
        return {"id": f"T-{i:08x}", "what": what, "owner": owner, "category": cat,
                "market": "ym", "cycle": "cycle1", "store": store, "urgency": urg,
                "priority": prio, "state": st, "steps": [{"id": "s1", "title": "x",
                                                          "state": st}]}
    imp = _task(1, "Переценка ARB-87931769 (тест)", "PRICER", prio=10, urg="high",
                store="atlas-express-film")
    hi = _task(2, "Категории донора cargo (тест)", "CATEGORIST", prio=40)
    done = _task(3, "Закрытое вчера", "CONTROLLER", cat="health", st="done")
    done["steps"][0]["state"] = "done"
    txt = console.tasks_text(out=io.StringIO(), tasks=[hi, imp, done])
    need = ["ЗАДАНИЯ", "записей 3", "открыто 2", "PRICER", "atlas-express-film", "P10",
            "Переценка ARB-87931769", "P40", "Категории донора"]
    missing = [k for k in need if k not in txt]
    hide_done = "Закрытое вчера" not in txt
    # честная деградация: реестр недоступен (модуль подменён на None) → не «0», а честно
    fake = console
    real_reg = fake.tasks_reg
    fake.tasks_reg = None
    try:
        deg = console.tasks_text(out=io.StringIO(), tasks=None)
        deg_ok = "не импортировался" in deg
    finally:
        fake.tasks_reg = real_reg
    return (not missing and hide_done and deg_ok), (
        f"недостаёт: {missing or '—'} · закрытое-скрыто={hide_done} · деградация-честна={deg_ok}")


TESTS = [
    ("CC1  роль_карточка", cc1_rol_kartochka),
    ("CC2  пустая_табель", cc2_pustaya_tabel_chestno),
    ("CC3  alias_имя", cc3_alias_imya),
    ("CC4  день_карточка", cc4_den_kartochka),
    ("CC5  кпи_свертка", cc5_kpi_svertka),
    ("CC6  артефакты_сводка", cc6_artefakty_svodka),
    ("CC7  консоль_не_пишет", cc7_console_ne_pishet),
    ("CC8  цвета_plain", cc8_cveta_plain),
    ("CC9  задания_блок", cc9_zadaniya_blok),
]


def main():
    print("🎯 КОНСОЛЬ-ЯМ · ПРИЁМКА — read-кабинет SOCC-ЯМ, чистый, 0₽, без записи/сети")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<20} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ КОНСОЛЬ-ЯМ читает сторы честно: карточки/табель/KPI/артефакты/задания, без выдумки и без записи")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

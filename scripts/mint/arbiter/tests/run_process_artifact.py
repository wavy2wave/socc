#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PROCESS ARTIFACT V1 (process_artifact_v1) — сухие приёмки библиотеки процессов (dry, 0₽).

Законы (артефакт-слой, директива оператора 2026-09-09 «каждый прогон = артефакт, всё прозрачно»):
  A1  стабильный id: два seal одного намерения → ОДНА запись (контент-хеш, дедуп TZ1).
  A2  dry не пишет (registry/.md не создаются); commit пишет registry + читаемый .md в tmp.
  A3  find по kind/market/date находит; show(id) возвращает запись.
  A4  confirm: state=confirmed/by=operator/лог — ТОЛЬКО при commit; dry ничего не меняет.
  A5  ретро-артефакт залива из журнала-фикстуры → knowledge заполнен (cards, price min/max,
      донор-карта), БЕЗ сети (register_pour читает env-файл, наружу не ходит).
  A6  render_report — читаемый MD с id в заголовке; seal/confirm дописывают log «кто/когда».

Сухо: env-песочница (PROCESS_LIBRARY_PATH/PROCESS_RUNS_DIR/PROCESS_POUR_JOURNAL на tmp),
канон репо не пишется.
"""
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ARB = Path(__file__).resolve().parent.parent
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

import process_artifact_v1 as PA

PASS = "✅ PASS"
FAIL = "❌ FAIL"

# Фикстура журнала залива (форма живого file-pour-library.json: dict по файловому артикулу)
FIX_JOURNAL = {
    "tdt_plenka_low_112": {"offer_id": "tdt_plenka_low_112", "name": "Пупырчатая пленка трехслойная 0.2x5 м",
                           "price": 4590, "old_price": 5140, "size": {"w_m": 0.2, "l_m": 5.0},
                           "donor_article": "9600155", "donor_near": True,
                           "product_id": 6269480743, "status": "imported",
                           "shelf": "одобрена, но скрыта", "recorded": "2026-09-09"},
    "tdt_plenka_low_46": {"offer_id": "tdt_plenka_low_46", "name": "Пупырчатая пленка 0.4x5 м",
                          "price": 4680, "old_price": 5230, "size": {"w_m": 0.4, "l_m": 5.0},
                          "donor_article": "9600155", "donor_near": True,
                          "product_id": 6269481030, "status": "imported",
                          "shelf": "одобрена, но скрыта", "recorded": "2026-09-09"},
    "tdt_plenka_low_900": {"offer_id": "tdt_plenka_low_900", "name": "Пленка 1.2x50 м",
                           "price": 14250, "old_price": None, "size": {"w_m": 1.2, "l_m": 50.0},
                           "donor_article": "9604685", "donor_near": True,
                           "product_id": 6269480999, "status": "imported",
                           "shelf": "одобрена, но скрыта", "recorded": "2026-09-09"},
}
FIX_DONOR_MAP = {"0.4|5.0": {"article": "9600155", "url": "https://shop.cargo-avto.ru/catalog/9600155/",
                             "source": "scan"}}

PASS_N = 0


def check(name, cond, extra=""):
    global PASS_N
    if cond:
        PASS_N += 1
        print(f"{PASS} {name}" + (f" — {extra}" if extra else ""))
    else:
        print(f"{FAIL} {name}" + (f" — {extra}" if extra else ""))


def _tmp():
    return Path(tempfile.mkdtemp(prefix="pafix_"))


def _record(kind="pour", market="ozon", category="vpp-film", date="2026-09-08",
            what="Залив ВПП-рулонов (фикстура)", **kw):
    base = {"kind": kind, "market": market, "category": category, "date": date,
            "what": what, "owner": "OZON_ZALIV", "params": {"mode": "live", "cards": 3},
            "decision": {"word": "фикстура", "via": "operator"},
            "result": {"ok": True, "imported": 3}, "artifacts": {"journal": "tmp"},
            "knowledge": {"category": {"slug": "vpp-film", "ozon": {"dci": 17027937, "tid": 97503},
                                       "pour": {"cards": 3, "with_donor": 3},
                                       "price_band": {"min": 4590, "max": 14250}}}}
    base.update(kw)
    return base


def main():
    # A1 стабильный id + дедуп (два seal одного намерения → одна запись)
    td = _tmp()
    os.environ["PROCESS_LIBRARY_PATH"] = str(td / "pl.json")
    os.environ["PROCESS_RUNS_DIR"] = str(td / "runs")
    rec = _record()
    r1 = PA.seal(rec, commit=True)
    rec2 = _record()                      # то же намерение (тот же what/kind/market/cat/date)
    r2 = PA.seal(rec2, commit=True)
    runs, _ = PA.load()
    check("A1 стабильный id (два seal одного намерения)", r1["id"] == r2["id"]
          and r1["id"].startswith("P-"), r1["id"])
    check("A1 дедуп: одна запись в registry", len(runs) == 1 and runs[r1["id"]]["what"] == rec["what"])
    check("A1 разные прогоны → разные id", PA.run_id("pour", "ozon", "vpp-film", "2026-09-08", "А")
          != PA.run_id("pour", "ozon", "vpp-film", "2026-09-08", "Б"))

    # A2 dry не пишет; commit пишет registry + читаемый md
    td2 = _tmp()
    os.environ["PROCESS_LIBRARY_PATH"] = str(td2 / "pl.json")
    os.environ["PROCESS_RUNS_DIR"] = str(td2 / "runs")
    buf = StringIO()
    with redirect_stdout(buf):
        rd = PA.seal(_record(what="Залив-Б (dry)"), commit=False)
    out = buf.getvalue()
    check("A2 dry: НЕ пишет (нет registry/.md, честная метка СУХО)",
          rd["dry"] is True and not (td2 / "pl.json").exists()
          and not (td2 / "runs").exists() and "СУХО" in out)
    rc = PA.seal(_record(what="Залив-Б (dry)"), commit=True)
    check("A2 commit: registry + .md записаны", (td2 / "pl.json").exists()
          and rc.get("md") and Path(rc["md"]).exists())
    md_text = Path(rc["md"]).read_text()
    check("A2 .md читаемый, id в заголовке", rc["id"] in md_text and md_text.lstrip().startswith("# ОТЧЁТ"))

    # A3 find/show
    f = PA.find(kind="pour", market="ozon", category="vpp-film")
    check("A3 find по kind/market/category находит", len(f) == 1 and f[0]["id"] == rc["id"])
    by_date = PA.find(date="2026-09-08")
    check("A3 find по date находит", any(x["id"] == rc["id"] for x in by_date))
    shown = PA.show(rc["id"])
    check("A3 show(id) возвращает запись", shown is not None and shown["id"] == rc["id"])
    check("A3 show нет id → None (не врём)", PA.show("P-nope") is None)

    # A4 confirm только при commit
    td3 = _tmp()
    os.environ["PROCESS_LIBRARY_PATH"] = str(td3 / "pl.json")
    os.environ["PROCESS_RUNS_DIR"] = str(td3 / "runs")
    PA.seal(_record(what="Залив-В (confirm)"), commit=True)
    pid = PA.find()[0]["id"]
    buf2 = StringIO()
    with redirect_stdout(buf2):
        cd = PA.confirm(pid, commit=False)
    runs, _ = PA.load()
    check("A4 dry-confirm: состояние НЕ меняется (dry честно)", cd["dry"] is True
          and runs[pid]["state"] == "done")
    cc = PA.confirm(pid, commit=True)
    runs, _ = PA.load()
    check("A4 commit-confirm: state=confirmed + by=operator + лог", runs[pid]["state"] == "confirmed"
          and runs[pid].get("confirm", {}).get("by") == "operator")
    logs = runs[pid].get("log") or []
    check("A4 лог содержит seal и confirm (кто/когда)", len(logs) >= 2
          and any("confirm" in (x.get("what") or "") or "подтвердил" in (x.get("what") or "") for x in logs))
    check("A4 повторный confirm → already (не плодит)", PA.confirm(pid, commit=True).get("already") is True)

    # A5 ретро-артефакт из журнала-фикстуры → knowledge (0 сети)
    td4 = _tmp()
    os.environ["PROCESS_LIBRARY_PATH"] = str(td4 / "pl.json")
    os.environ["PROCESS_RUNS_DIR"] = str(td4 / "runs")
    jp = td4 / "file-pour-library.json"
    jp.write_text(json.dumps(FIX_JOURNAL, ensure_ascii=False), encoding="utf-8")
    dmp = td4 / "donor-size-map-2026-09-08.json"
    dmp.write_text(json.dumps(FIX_DONOR_MAP, ensure_ascii=False), encoding="utf-8")
    os.environ["PROCESS_POUR_JOURNAL"] = str(jp)
    ret = PA.register_pour("2026-09-08", commit=True)
    check("A5 ретро-регистрация залива ok", ret.get("ok") is True and ret.get("id", "").startswith("P-"))
    rec5 = PA.show(ret["id"])
    k = rec5["knowledge"]["category"]
    check("A5 knowledge: cards=3, с донором 3, цена min/max", k["pour"]["cards"] == 3
          and k["pour"]["with_donor"] == 3 and k["price_band"] == {"min": 4590, "max": 14250})
    check("A5 knowledge: категория ozon dci/tid + донор 9600155", k["ozon"]["dci"] == 17027937
          and k["ozon"]["tid"] == 97503 and any(sz[0] == "0.4×5" for sz in k["top_sizes"]))
    check("A5 донор-карта из size-map подхвачена", "9600155" in json.dumps(k["donor"], ensure_ascii=False))
    check("A5 результат: imported=3, product_id у всех", rec5["result"]["imported"] == 3
          and rec5["result"]["product_id"] == 3)

    # A6 render_report — читаемый MD, лог seal накапливается
    txt = "\n".join(PA.render_report(rec5))
    check("A6 отчёт читаемый: заголовок с id + разделы", rec5["id"] in txt and "## Решение" in txt
          and "## Знание категории" in txt and "## Лог" in txt)
    check("A6 лог содержит ретро-seal строку", any("ретро" in (x.get("what") or "") for x in (rec5.get("log") or [])))

    N_EXPECT = 21
    print(f"\nИТОГ · pass {PASS_N}/{N_EXPECT}")
    return 0 if PASS_N == N_EXPECT else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Приёмка ХРАНИТЕЛЯ (keeper_v1) + эволюционного шва (register_cycle1).
Hermetic · сухо · 0₽ · НИ ОДНОГО обращения к живым сторам: все полки уводятся в tempfile
через env-перекрытия (KP3 — тот же механизм, что уважает боевой запуск).

Покрывает законы:
  KP1 нет писателей — экспорт без --out не создаёт файл; с --out — только в песочнице.
  KP2 честная пустота — все полки пусты/биты → орган отвечает структурой + причиной, не падает.
  KP3 re-use канона — читаем РОДНЫМИ читателями из env-перенаправленных файлов.
  KP4 классификация не выдумывает — неизвестное имя → «без размера (не распознан)».
  KP5 пульс отвечает всегда.
  KP6 экспорт = точный срез + consumer.
  Шов: all-PASS → seal пишет ход (registry + .md); один FAIL → НИЧЕГО (двойной гейт).
"""
import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # scripts/mint/arbiter/tests
_ARB = _HERE.parent                              # scripts/mint/arbiter
sys.path.insert(0, str(_ARB))

_OK, _TOT = 0, 0


def check(name, cond, extra=""):
    global _OK, _TOT
    _TOT += 1
    mark = "✅" if cond else "❌"
    if cond:
        _OK += 1
        print(f"  {mark} {name}")
    else:
        print(f"  {mark} {name} — {extra}")


def _w(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _set(sandbox: Path, extra: dict | None = None):
    """Увести ВСЕ полки в песочницу (KP3: env-перекрытия родных читателей)."""
    env = {
        "YM_LIBRARY_PATH": str(sandbox / "goods.json"),
        "YM_MATRIX_PATH": str(sandbox / "matrix.json"),
        "OZON_LIBRARY_PATH": str(sandbox / "ozon-library.json"),
        "PROCESS_POUR_JOURNAL": str(sandbox / "pour.json"),
        "PROCESS_LIBRARY_PATH": str(sandbox / "process.json"),
        "PROCESS_RUNS_DIR": str(sandbox / "runs"),
        "KEEPER_STORES_PATH": str(sandbox / "stores.json"),
        "KEEPER_TAPE_PATH": str(sandbox / "tape.json"),
    }
    for k, v in (extra or {}).items():
        env[k] = v
    os.environ.update(env)


ROOT = Path(tempfile.mkdtemp(prefix="keeper_accept_"))
EMPTY = ROOT / "empty"
FIX = ROOT / "fix"
SEAM = ROOT / "seam"
_set(EMPTY)  # ничего в EMPTY не пишем → полки «нет» (KP2)

import keeper_v1 as K  # noqa: E402  (env уже в песке)
import process_artifact_v1 as pa  # noqa: E402

print("═" * 60)
print("ХРАНИТЕЛЬ · приёмка (hermetic, 0₽, tempfile-песочница)")
print("═" * 60)

# ── ЭТАП 1: KP2/KP5 честная пустота ──────────────────────────────────────
print("\n— KP2 честная пустота · KP5 пульс отвечает всегда —")
sh = K.shelves_now()
check("пустых полок ровно 7 (все полки перечислены)", len(sh) == 7, str(len(sh)))
check("каждая пустая полка → вердикт ok=False с причиной",
      all((not s["ok"]) and s["why"] for s in sh),
      [s["name"] for s in sh if s["ok"]])
text, rc = K.cmd([])
check("пульс без данных отвечает всегда (rc=0 + заголовок)", rc == 0 and "БИБЛИОТЕКА СИСТЕМЫ" in text, str(rc))
text, rc = K.cmd(["полки"])
check("--полки в пустоте показывает причину «нет»", rc == 0 and "причина" in text)

# ── ЭТАП 2: KP3 re-use канона на фабричных полках ────────────────────────
print("\n— KP3 читаем родными читателями (env-фабрики) —")
# фикстуры
W = {
    "stores.json": {
        "myshop-film": {"slug": "myshop-film", "business_id": 111, "campaign_id": 222,
                        "warehouse_id": 333, "donor_category": "vpp-film",
                        "builder": "film", "builder_slug": "puzyrkovaya-plenka", "markup": 2.0},
        "myshop-tape": {"slug": "myshop-tape", "mother": "myshop-film",
                        "donor_category": "klejkaya-lenta", "builder": "tape",
                        "builder_slug": "klejkaya-lenta", "markup": 3.0},
    },
}
# goods: 3 film + 3 tape (у последней — пустое имя → KP4 «не распознан»)
_goods = {}
for i, (slug, cat) in enumerate([("myshop-film", "vpp-film")] * 3 + [("myshop-tape", "klejkaya-lenta")] * 3):
    name = ["Воздушно пузырьковая пленка 50*0.3 м", "Воздушно пузырьковая пленка 100*0.5 м",
            "Воздушно пузырьковая пленка 20*0.2 м", "Скотч 48мм х 50м", "Скотч 25мм х 50м", ""][i]
    lv = {"verdict": "PASS", "ts": "2026-09-09T00:00:00+00:00", "store_slug": slug, "note": "тест"} if i in (0, 1, 3) else None
    _goods[f"K{i + 1}"] = {"offerId": f"K{i + 1}", "name": name, "store_slug": slug,
                           "category_slug": cat, "article": f"9600{i + 1}",
                           "last_verified": lv}
from ymarket_library_v1 import SCHEMA as YL_SCHEMA
W["goods.json"] = {"schema": YL_SCHEMA, "created_at": "2026-09-09", "goods": _goods}
W["matrix.json"] = {"rows": {
    "m1": {"category": "puzyrkovaya-plenka", "status": "на-витрине"},
    "m2": {"category": "puzyrkovaya-plenka", "status": "на-витрине"},
    "m3": {"category": "klejkaya-lenta", "status": "на-витрине"},
}}
W["pour.json"] = {"tdt1": {"status": "imported"}, "tdt2": {"status": "imported"}}
W["tape.json"] = {"schema": "x", "stats": {"groups": 4, "cards": 2, "ozon_items": 10, "cargo_facts": 2}}
W["process.json"] = {"schema": "process.artifact.v1", "updated_at": "2026-09-09", "runs": {
    "P-c1aa": {"id": "P-c1aa", "kind": "cycle1", "market": "ym", "category": "vpp-film",
               "date": "2026-09-09", "what": "ЦИКЛ-1 myshop-film 2026-09-09: 2/2 PASS",
               "owner": "CYCLE1", "state": "confirmed",
               "params": {"store": "myshop-film", "mode": "live", "nodes": 2, "hash": "abc"},
               "decision": {"word": "живой --commit (RUBICON)", "via": "cycle1-engine"},
               "result": {"ok": True, "verdict": "PASS", "pass_n": 2, "len": 2,
                          "hash": "abc", "node_ms": {"a": 10, "b": 20}},
               "artifacts": {}, "knowledge": {}},
}}
for name, obj in W.items():
    _w(FIX / name, obj)
_set(FIX)

sh = {s["name"]: s for s in K.shelves_now()}
check("ym-goods из канон-читателя: 6 карточек", sh["ym-goods"].get("ok") and sh["ym-goods"]["n"] == 6,
      str(sh["ym-goods"].get("n")))
check("ym-matrix: 3 строки", sh["ym-matrix"].get("ok") and sh["ym-matrix"]["n"] == 3)
check("ym-stores: 2 магазина", sh["ym-stores"].get("ok") and sh["ym-stores"]["n"] == 2)
check("ozon-pour: 2 карточки залива", sh["ozon-pour"].get("ok") and sh["ozon-pour"]["n"] == 2)
check("ozon-tape: 4 группы (stats канона)", sh["ozon-tape"].get("ok") and sh["ozon-tape"]["n"] == 4)
check("process: 1 записанный ход", sh["process"].get("ok") and sh["process"]["n"] == 1)
check("ozon-matrix в фабрике отсутствует → честно «нет»",
      (not sh["ozon-matrix"].get("ok")) and sh["ozon-matrix"]["why"])

# ── магазины (дрилл из живых стора-фабрик) ───────────────────────────────
print("\n— магазины: Name + ID + кол-во —")
text, rc = K.cmd(["магазины"])
check("магазины rc=0 и оба ЯМ-магазина на месте",
      rc == 0 and "myshop-film" in text and "myshop-tape" in text)
check("film: 3 карточек · 2 на-витрине · 2 PASS",
      "товаров: 3 карточек" in text and "на-витрине: 2" in text and "сверено PASS: 2" in text)
check("tape: 3 карточек · 1 на-витрине (мама наследуется)",
      "товаров: 3 карточек" in text and "на-витрине: 1" in text and "мама myshop-film" in text)
check("ID бизнеса 111 форматируется", "бизнес 111" in text and "склад = мамы (наследование)" in text)
text, rc = K.cmd(["магазин", "myshop-film"])
check("одиночный магазин — только его блок", rc == 0 and "myshop-tape" not in text)
text, rc = K.cmd(["магазин", "no-such"])
check("нет такого магазина → честно сказано", "нет в манифестах" in text)

# ── типы (KP4 не выдумываем) ─────────────────────────────────────────────
print("\n— типы: из них рулоны / ленты / не распознан (KP4) —")
items, note = K.types_for("myshop-film")
check("film → рулоны в метрах 3", note == "" and any(i["klass"] == "рулоны в метрах" and i["n"] == 3 for i in items))
items, note = K.types_for("myshop-tape")
check("tape → ленты/скотч 2", note == "" and any(i["klass"] == "ленты/скотч" and i["n"] == 2 for i in items))
check("tape → пустое имя = «не распознан» (без гадания)",
      note == "" and any("не распознан" in i["klass"] and i["n"] == 1 for i in items), str(items))
items, note = K.types_for("nope")
check("типы несуществующего → причина, не пустой ответ", note != "")

# ── ходы: список + фильтры + ход PID ─────────────────────────────────────
print("\n— ходы (готовые записанные ходы) —")
hs, note = K.hods()
check("список ходов: 1 (P-c1aa)", note == "" and len(hs) == 1 and hs[0]["id"] == "P-c1aa")
hs, _ = K.hods(kind="pour")
check("фильтр kind=pour → 0 (в фабрике только cycle1)", len(hs) == 0)
hs, _ = K.hods(market="ym")
check("фильтр market=ym → 1", len(hs) == 1)
text, rc = K.cmd(["ход", "P-c1aa"])
check("ход PID рендерит отчёт (md-блок с решением/результатом)",
      rc == 0 and "ОТЧЁТ ПРОГОНА" in text and "живой --commit" in text and "verdict" in text)
text, rc = K.cmd(["ход", "P-zzzz"])
check("ход с несуществующим PID — честно «не найден»", rc == 0 and "не найден" in text)

# ── экспорт (KP1/KP6) ────────────────────────────────────────────────────
print("\n— экспорт: точный срез + consumer (KP1/KP6) —")
before = sorted(p.name for p in FIX.iterdir())
text, rc = K.cmd(["экспорт", "ym-goods"])
after = sorted(p.name for p in FIX.iterdir())
check("экспорт без --out НЕ создаёт файл (KP1)", rc == 0 and before == after)
check("экспорт несёт consumer + counts (KP6)", "consumer" in text and "карточек" in text)
ok, pay = K.export_slice("ym-goods")
check("срез полки: n=6", ok and pay.get("n") == 6)
ok, pay = K.export_slice("myshop-film")
check("срез магазина: 3 карточки + 2 матричных строки",
      ok and len(pay["cards"]) == 3 and len(pay["matrix_rows"]) == 2)
out = FIX / "out.json"
text, rc = K.cmd(["экспорт", "myshop-film", "--out", str(out)])
check("экспорт с --out пишет файл в ПЕСОЧНИЦУ", rc == 0 and out.exists())
if out.exists():
    d = json.loads(out.read_text(encoding="utf-8"))
    check("срез из файла корректен (3 cards)", len(d.get("cards", [])) == 3)
ok, pay = K.export_slice("bogus")
check("экспорт незнакомой цели — причина с перечнем полок", not ok and "bogus" in pay["why"])

# ── шов (эволюционный закон: PASS → ход, FAIL → НИЧЕГО) ──────────────────
print("\n— эволюционный шов register_cycle1 (all-PASS → seal; FAIL → ничего) —")
_set(SEAM)
profile = {"slug": "myshop-film", "donor_category": "vpp-film", "business_id": 111,
           "campaign_id": 222, "warehouse_id": 333, "builder": "film",
           "builder_slug": "puzyrkovaya-plenka", "markup": 2.0}
results_pass = [{"verdict": "PASS", "node": "a", "ms": 10}, {"verdict": "PASS", "node": "b", "ms": 20}]
r = pa.register_cycle1(profile, results_pass, commit=True, date_str="2026-09-09", hsh="h1")
check("all-PASS → ход зафиксирован (ok=True)", r.get("ok") is True, str(r))
p = SEAM / "process.json"
runs = json.loads(p.read_text(encoding="utf-8")).get("runs", {}) if p.exists() else {}
check("registry записан: 1 ход kind=cycle1", len(runs) == 1 and runs and "cycle1" in runs[list(runs)[0]].get("kind", ""))
md_hits = list((SEAM / "runs").glob("*.md"))
check("читаемый .md отчёта создан в песочнице", len(md_hits) == 1, str(md_hits))
r2 = pa.register_cycle1(profile, results_pass, commit=True, date_str="2026-09-09", hsh="h1")
runs2 = json.loads(p.read_text(encoding="utf-8")).get("runs", {}) if p.exists() else {}
check("повторный тот же цикл → дедуп, не плодит дубль (всё ещё 1)",
      r2.get("ok") is True and len(runs2) == 1, str(len(runs2)))
results_fail = [{"verdict": "PASS", "node": "a", "ms": 10}, {"verdict": "FAIL", "node": "b", "ms": 20}]
rf = pa.register_cycle1(profile, results_fail, commit=True, date_str="2026-09-10", hsh="h2")
runs3 = json.loads(p.read_text(encoding="utf-8")).get("runs", {}) if p.exists() else {}
check("один FAIL → ход НЕ фиксируется (всё ещё 1)", rf.get("ok") is False and len(runs3) == 1,
      f"{rf.get('error')} / n={len(runs3)}")
# сухой seal → 0 записей
pa.register_cycle1(profile, results_pass, commit=False, date_str="2026-09-11", hsh="h3")
runs4 = json.loads(p.read_text(encoding="utf-8")).get("runs", {}) if p.exists() else {}
check("commit=False (dry) → НИЧЕГО не пишет (LB1)", len(runs4) == 1, str(len(runs4)))

# ── CLI rc на неизвестном ────────────────────────────────────────────────
text, rc = K.cmd(["фрукт"])
check("неизвестная команда хранителя → rc=2 + подсказка", rc == 2 and "неизвестная команда" in text)

print("\n" + "═" * 60)
print(f"ИТОГ: {_OK}/{_TOT} ✅" + (" — ВСЁ ЗЕЛЁНОЕ" if _OK == _TOT else " — ЕСТЬ ПАДЕНИЯ"))
print("═" * 60)
sys.exit(0 if _OK == _TOT else 1)

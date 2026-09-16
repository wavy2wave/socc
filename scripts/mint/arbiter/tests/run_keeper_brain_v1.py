#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Приёмка МОЗГА БИБЛИОТЕКАРЯ (keeper_brain_v1) — АГИ-слой над ХРАНИТЕЛЕМ.
Hermetic · сухо · 0₽ · НИ ОДНОГО обращения к живым сторам: все полки уводятся в tempfile
через env-перекрытия (KB3 — тот же механизм, что уважает боевой запуск).

Покрывает законы мозга:
  KB1 мозг чист — все плоскости ничего не пишут (снимок песочницы до/после).
  KB2 честность — пустые/битые полки → диагноз с причинами, не фейк-здоровье (пустая
      система НЕ получает балл 100); гомограф «лента новостей» НЕ выдают за скотч.
  KB3 перекрёстность — цифры из ЖИВЫХ сторов через родных читателей (env-фабрики).
  KB4 эволюция не врёт — знание/рецепты/скорость ТОЛЬКО из записанных ходов (все-PASS
      гарантирует шов); FAIL-ходы честно помечены skipped.
  KB5 ответ всегда — непонятная фраза/пустой вопрос → подсказка, не тишина.

Плоскости: health() · integrity() · evolution() · ask() · report() · tour() · cmd().
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # scripts/mint/arbiter/tests
_ARB = _HERE.parent                              # scripts/mint/arbiter
sys.path.insert(0, str(_ARB))

_ENV_KEYS = ("YM_LIBRARY_PATH", "YM_MATRIX_PATH", "OZON_LIBRARY_PATH", "PROCESS_POUR_JOURNAL",
             "PROCESS_LIBRARY_PATH", "PROCESS_RUNS_DIR", "KEEPER_STORES_PATH", "KEEPER_TAPE_PATH")

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
    """Увести ВСЕ полки в песочницу (KB3: env-перекрытия родных читателей)."""
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


def _build_stores():
    return {
        "atlas-express-film": {"slug": "atlas-express-film", "business_id": 111, "campaign_id": 222,
                               "warehouse_id": 333, "donor_category": "vpp-film",
                               "builder": "film", "builder_slug": "puzyrkovaya-plenka", "markup": 2.0},
        "atlas-express-tape": {"slug": "atlas-express-tape", "mother": "atlas-express-film",
                               "donor_category": "klejkaya-lenta", "builder": "tape",
                               "builder_slug": "klejkaya-lenta", "markup": 3.0},
    }


def _build_goods():
    _g = {}
    specs = [
        ("F-1001", "9600001-1", "Воздушно пузырьковая пленка 50*0.3 м", "atlas-express-film", "vpp-film", 1, True),
        ("F-1002", "9600002-1", "Воздушно пузырьковая пленка 100*0.5 м", "atlas-express-film", "vpp-film", 1, True),
        ("F-1003", "9600003-1", "Воздушно пузырьковая пленка 20*0.2 м", "atlas-express-film", "vpp-film", 1, False),
        ("T-2001", "9600004-1", "Скотч 48мм х 50м", "atlas-express-tape", "klejkaya-lenta", 1, True),
        ("T-2002", "9600005-1", "Скотч 25мм х 50м", "atlas-express-tape", "klejkaya-lenta", 0, False),
        ("T-2003", "9600006-1", "Скотч 48мм х 100м", "atlas-express-tape", "klejkaya-lenta", 1, False),
    ]
    for off, art, name, slug, cat, photos, pass_ in specs:
        lv = {"verdict": "PASS", "ts": "2026-09-09T00:00:00+00:00", "store_slug": slug, "note": "тест"} if pass_ else None
        _g[off] = {"offerId": off, "name": name, "store_slug": slug, "category_slug": cat,
                   "article": art, "n_photos": photos, "last_verified": lv}
    from ymarket_library_v1 import SCHEMA as YL_SCHEMA
    return {"schema": YL_SCHEMA, "created_at": "2026-09-09", "goods": _g}


def _build_ozon():
    return {
        "built": "2026-09-08", "schema": "ozon.library.v1",
        "total_rows": 844,
        "records": [
            {"article": "oz-1", "name": "Рулон воздушно пузырьковая пленка 0.5*10 м", "type": "рулон-в-м"},
            {"article": "oz-2", "name": "Коробка картонная 60x40x40", "type": "коробки/конверты"},
            {"article": "oz-3", "name": "Скотч 48мм 50м", "type": "ленты/скотч"},
        ],
        "summary": {"by_type": {"рулон-в-м": 702, "пакеты-пупырка": 83, "м-одиночное": 23,
                                "без-размера": 18, "пленка-в-см": 12, "коробки/конверты": 4,
                                "ленты/скотч": 2},
                    "rolls": 697, "families": 109},
    }


def _build_pour():
    return {
        "tdt1": {"offer_id": "tdt1", "status": "imported", "shelf": "Продаётся",
                 "product_id": 111, "price": 1000},
        "tdt2": {"offer_id": "tdt2", "status": "imported", "shelf": "одобрена-но-скрыта",
                 "product_id": 222, "price": 2000},
    }


def _build_tape():
    return {"schema": "tape.library.v1", "created_at": "2026-09-09",
            "stats": {"groups": 4, "cards": 2, "ozon_items": 10, "cargo_facts": 2}}


def _build_matrix(vitrine_only):
    """vitrine_only=True → 5 строк все «на-витрине» (FIX); False → честный микс (FIX2):
    3 строки, из них 1 «на-витрине», 2 «одобрена-но-скрыта» (KB2: не считать спящих витриной)."""
    if vitrine_only:
        mk = lambda oid, art, cat: {"category": cat, "status": "на-витрине",
                                    "offer_id": oid, "article": art}
        return {"rows": {
            "m1": mk("F-1001", "9600001-1", "puzyrkovaya-plenka"),
            "m2": mk("F-1002", "9600002-1", "puzyrkovaya-plenka"),
            "m3": mk("F-1003", "9600003-1", "puzyrkovaya-plenka"),
            "m4": mk("T-2001", "9600004-1", "klejkaya-lenta"),
            "m5": mk("T-2003", "9600006-1", "klejkaya-lenta"),
        }}
    return {"rows": {
        "m1": {"category": "puzyrkovaya-plenka", "status": "на-витрине",
               "offer_id": "F-1001", "article": "9600001-1"},
        "m2": {"category": "puzyrkovaya-plenka", "status": "одобрена-но-скрыта",
               "offer_id": "F-1002", "article": "9600002-1"},
        "m3": {"category": "puzyrkovaya-plenka", "status": "одобрена-но-скрыта",
               "offer_id": "F-1003", "article": "9600003-1"},
    }}


def _build_process(mixed):
    runs = {
        "P-c1aa12": {"id": "P-c1aa12", "kind": "cycle1", "market": "ym", "category": "vpp-film",
                     "date": "2026-09-09", "what": "ЦИКЛ-1 atlas-express-film 2026-09-09: 2/2 PASS",
                     "owner": "CYCLE1", "state": "confirmed",
                     "params": {"store": "atlas-express-film", "mode": "live", "nodes": 2, "hash": "abc"},
                     "decision": {"word": "живой --commit (RUBICON)", "via": "cycle1-engine"},
                     "result": {"ok": True, "verdict": "PASS", "pass_n": 2, "len": 2,
                                "hash": "abc", "node_ms": {"a": 10, "b": 20}},
                     "artifacts": {},
                     "knowledge": {"category": {"slug": "puzyrkovaya-plenka",
                                                "name": "Воздушно-пузырьковая плёнка",
                                                "ozon": {"dci": 12345, "tid": 67890,
                                                         "warehouse": "склад-тест"},
                                                "top_sizes": [["0.4×5", 1]],
                                                "price_band": {"min": 100, "max": 200},
                                                "pour": {"cards": 12}}}},
    }
    if mixed:
        # FIX2: второй ход — НЕ все-PASS (FAIL) → эволюция должна его отбросить (KB4)
        runs["P-fail"] = {"id": "P-fail", "kind": "pour", "market": "ozon", "category": "vpp-film",
                          "date": "2026-09-08", "what": "Залив оборван: 1/2 карточек",
                          "owner": "OZON_ZALIV", "state": "done",
                          "decision": {"word": "слово оператора", "via": "operator"},
                          "result": {"ok": False, "verdict": "FAIL"},
                          "artifacts": {}, "knowledge": {}}
    else:
        runs["P-pour1"] = {"id": "P-pour1", "kind": "pour", "market": "ozon", "category": "vpp-film",
                           "date": "2026-09-08", "what": "Залив тест: 2 карточек",
                           "owner": "OZON_ZALIV", "state": "done",
                           "decision": {"word": "слово оператора на объём", "via": "operator"},
                           "result": {"ok": True, "verdict": "PASS"},
                           "artifacts": {}, "knowledge": {}}
    return {"schema": "process.artifact.v1", "updated_at": "2026-09-09", "runs": runs}


def _write_sandbox(root: Path, *, vitrine_only=True, mixed=False, corrupt=False):
    """Прописать фабричные полки. corrupt=True → stores.json БИТЫЙ (KP2)."""
    W = {
        "stores.json": _build_stores(),
        "goods.json": _build_goods(),
        "matrix.json": _build_matrix(vitrine_only),
        "ozon-library.json": _build_ozon(),
        "pour.json": _build_pour(),
        "tape.json": _build_tape(),
        "process.json": _build_process(mixed),
    }
    for name, obj in W.items():
        _w(root / name, obj)
    _w(root / "runs" / "cycle1-ym-2026-09-09-P-c1aa12.md", {"#": "отчёт"})
    _w(root / "runs" / "pour-ozon-2026-09-08-P-pour1.md", {"#": "отчёт"})
    if corrupt:
        (root / "stores.json").write_text("{ЭТО НЕ JSON", encoding="utf-8")


def run():
    ROOT = Path(tempfile.mkdtemp(prefix="brain_accept_"))
    EMPTY = ROOT / "empty"
    FIX = ROOT / "fix"
    FIX2 = ROOT / "fix2"
    CORRUPT = ROOT / "corrupt"
    for sub in (EMPTY, FIX, FIX2, CORRUPT):
        sub.mkdir(parents=True, exist_ok=True)
    _write_sandbox(FIX)
    _write_sandbox(FIX2, vitrine_only=False, mixed=True)
    _write_sandbox(CORRUPT, corrupt=True)

    import keeper_brain_v1 as B  # noqa: E402  (env в песке — ленивые читатели)

    # ── KB2/KB5 честная пустота: система без полок НЕ получает фейк-100 ─────────
    _set(EMPTY)  # в EMPTY ничего не пишем → все полки «нет» (KB2)
    print("═" * 60)
    print("МОЗГ БИБЛИОТЕКАРЯ · приёмка (hermetic, 0₽, tempfile-песочница)")
    print("═" * 60)
    print("\n— KB2 честная пустота · KB5 ответ всегда —")
    h = B.health()
    check("пустая система НЕ фейк-здорова (балл < 100)", 0 <= h["score"] < 100,
          f"score={h['score']}")
    check("диагноз говорит, что полки не читаются",
          any("НЕ читаются" in d for d in h["drift"]), str(h["drift"]))
    check("совет про полки есть", any("полки не читаются" in a for a in h["actions"]))
    check("слепая система (0 живых полок) НЕ получает балл выше 10 (KB2)",
          h["score"] <= 10, f"score={h['score']}")
    text, _f = B.ask("что-то совсем непонятное")
    check("непонятная фраза → подсказка, не тишина (KB5)", "не понял" in text, text[:80])
    text, _f = B.ask("")
    check("пустой вопрос → подсказка (KB5)", "не понял" in text)
    text, _f = B.ask("лента новостей")
    check("«лента новостей» НЕ выдана за скотч (KB2 гомограф)",
          "не понял" in text and "скотч" not in text.lower(), text[:120])

    # ── KB3: фабричные полки (FIX: всё PASS, микс витрины — все «на-витрине») ────
    print("\n— KB3 перекрёстность из живых сторов (env-фабрики) —")
    _set(FIX)

    # ── KB1: мозг чист — плоскости не пишут в песочницу ─────────────────────────
    print("\n— KB1 мозг чист (ничего не записывает, 0₽) —")
    before = sorted(str(p.relative_to(FIX)) for p in FIX.rglob("*"))
    B.health(); B.integrity(); B.evolution(); B.report(); B.ask("сколько товаров в магазине film?")
    B.cmd([]); B.tour(); B.cmd(["всё"]); B.cmd(["мозг"]); B.ask("лента новостей")
    after = sorted(str(p.relative_to(FIX)) for p in FIX.rglob("*"))
    check("после всех плоскостей песочница НЕ изменилась (0 записей)", before == after,
          f"появилось: {set(after) - set(before)}")

    # ── ЗДОРОВЬЕ: диагноз из фабрик ─────────────────────────────────────────────
    print("\n— ЗДОРОВЬЕ —")
    h = B.health()
    check("балл в 0..100 и здраво-ниже-макс", 0 <= h["score"] < 100, str(h["score"]))
    check("все 7 полок перечислены (свежие)", len(h["shelves"]) == 7 and
          all(s["ok"] for s in h["shelves"]))
    check("снимок: 6 карточек · 5 строк матрицы · 2 магазина · 2 хода · 2 залива",
          h["snapshot"] == {"goods": 6, "matrix": 5, "stores": 2, "runs": 2, "pour": 2},
          str(h["snapshot"]))
    check("дрейф: 2 строки витрины без PASS", any("2 строк" in d for d in h["drift"]))
    check("дрейф: T-2002 вне матрицы честно назван",
          any("T-2002" in d or "вне витринной матрицы" in d for d in h["drift"]), str(h["drift"]))
    check("совет про досверку с ЖИВЫМ счётчиком (2 строк без PASS)",
          any("досверка" in a and "2 строк без PASS" in a for a in h["actions"]),
          str(h["actions"]))
    text = B.render_health(h)
    check("рендер здоровья содержит полки + балл", "ЗДОРОВЬЕ" in text and "балл" in text)

    # ── ЦЕЛОСТНОСТЬ: перекрёстные сверки ────────────────────────────────────────
    print("\n— ЦЕЛОСТНОСТЬ —")
    it = B.integrity()
    by_name = {c["name"]: c for c in it["checks"]}
    check("9 сверок", it["n_checks"] == 9, str(it["n_checks"]))
    check("найдено ровно 3 расхождения (goods↔матрица, витрина↔PASS, фото)", it["n_fail"] == 3,
          str(it["n_fail"]))
    check("матрица↔goods: 0 сирот", by_name["матрица ↔ goods"]["ok"])
    check("goods↔матрица: 1 непокрытая (T-2002)",
          by_name["goods ↔ матрица"]["n"] == 1 and not by_name["goods ↔ матрица"]["ok"])
    check("витрина↔PASS: 2 строки без PASS",
          by_name["витрина ↔ PASS"]["n"] == 2 and not by_name["витрина ↔ PASS"]["ok"])
    check("залив↔product_id: 2/2 ок", by_name["залив ОЗОН ↔ product_id"]["ok"])
    check("скотч-канон↔витрина ЯМ: 2 карточки = 2 строки", by_name["скотч-канон ↔ витрина ЯМ"]["ok"])
    check("процессы↔.md: оба отчёта читаемы", by_name["процессы ↔ .md-отчёты"]["ok"])
    check("фото: 1 карточка без фото (T-2002)",
          by_name["фото-покрытие goods"]["n"] == 1 and not by_name["фото-покрытие goods"]["ok"])
    text = B.render_integrity(it)
    check("рендер целостности: вердикт с числом расхождений", "3 расхождений" in text)

    # ── ЭВОЛЮЦИЯ: знание/скорость/рецепты ТОЛЬКО из записанных ходов ───────────
    print("\n— ЭВОЛЮЦИЯ (KB4) —")
    ev = B.evolution()
    check("2 записанных хода (cycle1 + pour), 0 отброшено",
          ev["n"] == 2 and ev["skipped"] == 0 and ev["by_kind"] == {"cycle1": 1, "pour": 1},
          str({k: ev[k] for k in ("n", "skipped")}))
    check("1 рецепт цикла: повторить --store atlas-express-film",
          any(r["kind"] == "cycle1" and "atlas-express-film" in r["rerun"] for r in ev["recipes"]),
          str([r["rerun"] for r in ev["recipes"]]))
    check("1 рецепт залива: --register-pour", any("--register-pour" in r["rerun"] for r in ev["recipes"]))
    check("знание категории: dci/tid/склад из хода (KB4 не выдумываем)",
          len(ev["learned"]) == 1 and ev["learned"][0]["dci"] == 12345 and
          ev["learned"][0]["warehouse"] == "склад-тест", str(ev["learned"]))
    check("скорость посчитана только у хода с node_ms (1)",
          len(ev["speed"]) == 1 and ev["speed"][0]["avg_ms"] == 15, str(ev["speed"]))
    check("инвариант шва озвучен", "все-PASS" in ev["invariant"])
    text = B.render_evolution(ev)
    check("рендер эволюции: рецепты + знание", "рецепты" in text and "знание категорий" in text)

    # ── ВОПРОС: свободная фраза → факты ─────────────────────────────────────────
    print("\n— ВОПРОС (свободная русская фраза → факты) —")
    text, facts = B.ask("сколько товаров в магазине film?")
    check("film: 3 карточки + бизнес 111",
          "3 карточек" in text and "бизнес 111" in text, text[:100])
    text, _ = B.ask("сколько коробок и рулонов?")
    check("коробки/рулоны из матрицы ОЗОН",
          "рулоны в метрах 702" in text and "коробки/конверты 4" in text, text[:120])
    text, _ = B.ask("сколько карточек скотча на витрине?")
    check("скотч → магазин tape: 3 ленты + 2 строки витрины",
          "ленты/скотч 3" in text and "2 строк на-витрине" in text, text[:150])
    text, _ = B.ask("какие ходы были?")
    check("хода оба видны", "P-c1aa12" in text and "P-pour1" in text)
    text, _ = B.ask("ход P-c1aa")
    check("ход PID рендерит отчёт", "ОТЧЁТ ПРОГОНА" in text, text[:80])
    text, _ = B.ask("что узнали за ходы?")
    check("эволюция: ходов 2", "ходов 2" in text, text[:100])
    text, _ = B.ask("как здоровье системы?")
    check("здоровье: балл 90/100 в песочнице", "90/100" in text, text[:80])
    text, _ = B.ask("есть расхождения?")
    check("целостность: 3 расхождения", "3 расхождений" in text, text[:80])
    text, _ = B.ask("бла-бла-капуста")
    check("нет сигнала → подсказка (KB5)", "не понял" in text)

    # ── НОВЫЕ РАЗЛИЧАЮЩИЕ ВОПРОСЫ (из адверсариал-ревью: 11 находок) ────────────
    print("\n— РАЗЛИЧАЮЩИЕ ВОПРОСЫ (находки ревью) —")
    text, _ = B.ask("какие типы товаров?")
    check("«какие типы товаров?» отвечает (тип без \\b)", "не понял" not in text
          and "матрице ОЗОН" in text, text[:120])
    text, _ = B.ask("что там по ЯМ?")
    check("«что там по ЯМ?» → сводка ЯМ", "ЯМ всего" in text, text[:120])
    text, _ = B.ask("сколько у меня товаров?")
    check("«сколько у меня товаров?» → ЯМ всего 6", "6 карточек" in text, text[:120])
    text, _ = B.ask("сколько плёнки?")
    check("«сколько плёнки?» → магазин film (плёнк-стем)", "atlas-express-film" in text, text[:120])
    text, _ = B.ask("сколько магазинов?")
    check("«сколько магазинов?» → их 2", "магазинов 2" in text, text[:120])
    text, _ = B.ask("что за залив 8 сентября?")
    check("«8 сентября» распознан как дата → ход за залив",
          "2026-09-08" in text and "P-pour1" in text, text[:150])
    check("дата-парсер: «8 сентября» = 2026-09-08", B._date_of("8 сентября") == "2026-09-08",
          str(B._date_of("8 сентября")))
    check("дата-парсер: «сентября 8» = 2026-09-08", B._date_of("сентября 8") == "2026-09-08",
          str(B._date_of("сентября 8")))
    text, _ = B.ask("сколько магазинов на озоне?")
    check("«на озоне» → ветка OZON (залив 2 карточки), не ЯМ",
          "OZON" in text and "залив 2" in text and "бизнес 111" not in text, text[:150])
    text, _ = B.ask("сколько скотча на озоне?")
    check("«скотча на озоне» → матрица ОЗОН (oz перебивает алиас tape)",
          "матрица ОЗОН" in text and "ленты/скотч" in text and "типы atlas-express-tape" not in text,
          text[:150])
    text, _ = B.ask("лента новостей")
    check("«лента новостей» и в ВОПРОСЕ → подсказка (KB2/KB5)",
          "не понял" in text, text[:120])
    text, _ = B.ask("сколько ленты в магазине film?")
    check("гомограф-блок НЕ мешает явному магазину (film + ленты)",
          "atlas-express-film" in text and "не понял" not in text, text[:150])

    # ── ЛИЦО + CLI ──────────────────────────────────────────────────────────────
    print("\n— ЛИЦО (синтез) + CLI —")
    rep = B.report()
    check("сводка: 6 карточек · витрина · залив · ходы",
          "6 карточек" in rep and "залив 2" in rep and "2 —" in rep, rep[:200])
    text, rc = B.cmd([])
    check("cmd без аргументов → ЛИЦО, rc=0", rc == 0 and "ЛИЦО БИБЛИОТЕКАРЯ" in text)
    text, rc = B.cmd(["здоровье"])
    check("cmd здоровье → rc=0", rc == 0 and "ЗДОРОВЬЕ" in text)
    text, rc = B.cmd(["вопрос", "какие ходы были?"])
    check("cmd вопрос → ходы", rc == 0 and "P-c1aa12" in text)
    text, rc = B.cmd(["тур"])
    check("cmd тур → все плоскости", rc == 0 and "ЗДОРОВЬЕ" in text and "ЦЕЛОСТНОСТЬ" in text
          and "ЭВОЛЮЦИЯ" in text and "ЛИЦО" in text)
    text, rc = B.cmd(["всё"])
    check("cmd «всё» → тур, rc=0", rc == 0 and "ЭВОЛЮЦИЯ" in text and "ЦЕЛОСТНОСТЬ" in text)
    text, rc = B.cmd(["мозг"])
    check("cmd «мозг» → тур, rc=0", rc == 0 and "ЛИЦО БИБЛИОТЕКАРЯ" in text)
    text, rc = B.cmd(["пульс"])
    check("cmd «пульс» → ответ всегда, rc=0", rc == 0 and text.strip())
    text, rc = B.cmd(["сводка"])
    check("cmd «сводка» → ЛИЦО, rc=0", rc == 0 and "ЛИЦО БИБЛИОТЕКАРЯ" in text)

    # ── FIX2: FAIL-ход отброшен (KB4) + честная витрина (KB2) ───────────────────
    print("\n— FIX2: не-все-PASS ход + честная витрина —")
    _set(FIX2)
    ev = B.evolution()
    check("FIX2: 1 все-PASS ход + 1 FAIL отброшен (skipped=1)", ev["n"] == 1 and ev["skipped"] == 1,
          str({k: ev[k] for k in ("n", "skipped")}))
    text = B.render_evolution(ev)
    check("FIX2: рендер честно пишет про отброшенный FAIL",
          "отброшено как НЕ все-PASS" in text, text[:160])
    text, _ = B.ask("сколько на витрине?")
    check("FIX2: витрина честно «из 3» строк (1 на-витрине, 2 спят)",
          "«на-витрине» из 3" in text, text[:150])
    text, _ = B.ask("сколько скотча на озоне?")
    check("FIX2: oz-ветка всё ещё работает", "матрица ОЗОН" in text, text[:120])

    # ── CORRUPT: битая полка → честный диагноз (KP2) ───────────────────────────
    print("\n— CORRUPT: битый JSON → честный диагноз (KP2) —")
    _set(CORRUPT)
    h = B.health()
    st = next((s for s in h["shelves"] if s["name"] == "ym-stores"), None)
    check("битые stores.json → полка НЕ читается", st is not None and not st["ok"], str(st))
    check("причина битой полки названа (JSONDecodeError)",
          st is not None and "JSONDecodeError" in str(st["why"]), str(st))
    text = B.render_health(h)
    check("рендер здоровья честно показывает битую полку",
          "ym-stores" in text and "JSONDecodeError" in text, text[:200])
    text, _ = B.ask("какие магазины?")
    check("битая stores.json → вопрос НЕ падает, отвечает честно (KB5)",
          "OZON" in text or "магазин" in text, text[:150])

    # ── ИМПОРТ-БЕЗОПАСНОСТЬ: import модуля НЕ выходит из процесса ──────────────
    print("\n— ИМПОРТ-БЕЗОПАСНОСТЬ (runpy/subprocess, живой env) —")
    clean_env = {k: v for k, v in os.environ.items() if k not in _ENV_KEYS}
    r = subprocess.run([sys.executable, "-c", "import keeper_brain_v1; print('import ok')"],
                       cwd=str(_ARB), env=clean_env, capture_output=True, text=True, timeout=60)
    check("import keeper_brain_v1 в чистом env не падает и не выходит",
          r.returncode == 0 and "import ok" in r.stdout,
          f"rc={r.returncode} {r.stderr[:200]}")
    check("main()-гвард: module.main() существует и возвращает rc", callable(B.main))

    print("\n" + "═" * 60)
    print(f"ИТОГ: {_OK}/{_TOT} ✅" + (" — ВСЁ ЗЕЛЁНОЕ" if _OK == _TOT else " — ЕСТЬ ПАДЕНИЯ"))
    print("═" * 60)
    return 0 if _OK == _TOT else 1


def main():
    saved = {k: os.environ.get(k) for k in _ENV_KEYS}
    try:
        return run()
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


if __name__ == "__main__":
    sys.exit(main())

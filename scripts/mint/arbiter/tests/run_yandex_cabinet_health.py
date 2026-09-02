#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЯНДЕКС — ПРИЁМКА «СВЕРКА в цикл»: живое здоровье кабинета → cards_errored (сухо, 0₽, без сети).

Провязка рунга 4 (СВЕРКА) в суточный цикл: cards_errored должен идти из РЕАЛЬНОГО errors[] кабинета,
а не из памяти само-модели. Проверяем ЗАКОНЫ (каждый можно провалить), а не «оно запустилось».

  АДАПТЕР card_health (изоляция шва к параллельному classify_card_health)
    CH1  unavailable_none_not_zero  — классификатор недостижим → cards_errored=None, НИКОГДА 0 (анти-ложь)
    CH2  errored_frozen_and_fixable — klass frozen/error_fixable = «карточка с ошибкой» (= reconcile.error_skus)
    CH3  store_block_not_our_error  — «Магазин отключён» НЕ в cards_errored (вина витрины, держим отдельно)
    CH4  clean_processing_not_error — clean/processing/needs_placement/unknown НЕ считаются ошибкой
    CH5  one_bad_card_failsoft      — классификатор упал на одной карточке → она unknown, сводка выжила
    CH6  real_classifier_contract   — реальный write.classify_card_health (если импортируем) отдаёт klass
    CH7  needs_placement_surfaced   — needs_placement — first-class список (паритет с reconcile), не ошибка

  collect_kpis (перекрытие памяти живой правдой)
    KP1  no_cabinet_uses_memory     — без снимка кабинета cards_errored берётся из памяти (обратная совм.)
    KP2  live_overrides_memory      — прочитан кабинет → live cards_errored перекрывает память
    KP3  live_none_keeps_memory     — кабинет прочитан, но здоровье None → память сохраняется (не врём «live»)

  run_day (мёртвый сокет cabinet_read_fn оживлён)
    W1   socket_live_over_memory    — inject ридер → kpis.cards_errored=live, source=cabinet_live
    W2   no_read_keeps_memory       — без чтения source=memory, поведение как раньше (обратная совм.)
    W3   read_only_dry              — цикл остаётся dry=True/commit=False; ридер вызван; наружу ничего
    W4   read_failure_survived      — ридер упал → день выжил (B2), провал виден, source=memory

  build_heal (рунг 4c — живая заморозка → ТОЧНАЯ команда починки; 0₽, только текст, RUBICON)
    HL1  live_rebuild_names_exact_skus — живые ошибки → команда точечного ремонта называет ТОЧНЫЕ SKU
    HL2  live_place_named             — needs_placement → та же команда до-размещает (не ошибка, не горит)
    HL3  memory_errors_none           — ошибки лишь из памяти → needed=None (точные SKU не выдумываем)
    HL4  live_classifier_none         — здоровье None (write мид-фикс) → needed=None (сверка неполна)
    HL5  clean_false                  — витрина чиста → needed=False, команды нет (нечего чинить)
    HL6  provenance_single_supplier   — реестр: один поставщик → note подсказывает чью выгрузку/slug
    HL7  rubicon_recipe_only          — heal = рецепт (метка «commit-пути нет») + команда точечная (--skus)
    HL8  burning_shows_command_e2e    — run_day: команда лечения всплывает в «что горит» (оператор видит)
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
SCRIPTS = MINT.parent
for p in (str(ARB), str(MINT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_cabinet_health_v1 as cab           # noqa: E402
import ymarket_day_v1 as day_mod                  # noqa: E402

# Провенанс лечения (build_heal) читает РЕЕСТР артикулов. Уводим его на несуществующий путь, чтобы
# приёмка была герметична (provenance → None, ноль зависимости от канон-стора). 0₽, ничего не пишем.
_REG_TMP = os.path.join(tempfile.gettempdir(), "ymreg_ch_hermetic.json")
try:
    os.remove(_REG_TMP)
except OSError:
    pass
os.environ["YM_REGISTRY_PATH"] = _REG_TMP


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _fake_classify(card):
    """Мимикрия ymarket_write_v1.classify_card_health: klass читаем из стаба-карточки `_klass`."""
    return {"offerId": card.get("offerId"), "cardStatus": card.get("cardStatus"),
            "contentRating": card.get("contentRating"),
            "klass": card.get("_klass"), "action": card.get("_action", "none"),
            "our_errors": card.get("_our_errors", []), "store_verdicts": [],
            "store_blocked": card.get("_klass") == "store_blocked",
            "all_errors": [], "warnings": [], "reason": "тест"}


def _tmp_journal():
    fd, path = tempfile.mkstemp(prefix="ymch_", suffix=".jsonl")
    os.close(fd)
    os.remove(path)
    return path


def _mem_st(errored):
    """Само-модель со значением cards_errored В ПАМЯТИ (для проверки перекрытия)."""
    return {"kpis": {"cards_tracked": 9, "cards_live": 1, "cards_errored": errored,
                     "avg_content_rating": 40}}


# ─────────────────────────── АДАПТЕР ───────────────────────────

def ch1_unavailable_none_not_zero():
    """Анти-ложь: нет живого классификатора → cards_errored=None (честно «не знаю»), НИКОГДА фейковый 0."""
    old = cab._classifier
    cab._classifier = lambda: None                     # имитируем разрыв к write (мид-фикс соседней линии)
    try:
        h = cab.card_health([{"offerId": "A"}, {"offerId": "B"}])
    finally:
        cab._classifier = old
    ok = h["classifier"] == "unavailable" and h["cards_errored"] is None and h["cards_total"] == 2
    return ok, f"classifier={h['classifier']} cards_errored={h['cards_errored']} (не 0!) total={h['cards_total']}"


def ch2_errored_frozen_and_fixable():
    """frozen + error_fixable = «карточка с ошибкой» (совпадает с reconcile.error_skus параллельной линии)."""
    cards = [{"offerId": "F", "_klass": "frozen"}, {"offerId": "E", "_klass": "error_fixable"},
             {"offerId": "C", "_klass": "clean"}]
    h = cab.card_health(cards, classify_fn=_fake_classify)
    ids = {r["offerId"] for r in h["errored"]}
    ok = h["cards_errored"] == 2 and ids == {"F", "E"}
    # сверяем словарь классов, единый с write
    contract = set(cab.ERRORED_KLASSES) == {"frozen", "error_fixable"}
    return ok and contract, f"errored={h['cards_errored']} ids={ids} klass-контракт={contract}"


def ch3_store_block_not_our_error():
    """«Магазин отключён» — вина витрины, НЕ карточки → не попадает в cards_errored, лежит отдельно."""
    cards = [{"offerId": "S", "_klass": "store_blocked"}, {"offerId": "F", "_klass": "frozen"}]
    h = cab.card_health(cards, classify_fn=_fake_classify)
    ok = h["cards_errored"] == 1 and len(h["store_blocked"]) == 1 \
        and h["store_blocked"][0]["offerId"] == "S"
    return ok, f"cards_errored={h['cards_errored']} (только frozen) store_blocked={len(h['store_blocked'])}"


def ch4_clean_processing_not_error():
    """clean / processing / needs_placement / unknown — НЕ ошибки (здоровье за факт не выдаём)."""
    cards = [{"_klass": "clean"}, {"_klass": "processing"},
             {"_klass": "needs_placement"}, {"_klass": "unknown"}]
    h = cab.card_health(cards, classify_fn=_fake_classify)
    return h["cards_errored"] == 0, f"cards_errored={h['cards_errored']} by_klass={h['by_klass']}"


def ch5_one_bad_card_failsoft():
    """Классификатор бросил на ОДНОЙ карточке → она unknown, остальные посчитаны, сводка не упала."""
    def flaky(card):
        if card.get("offerId") == "BOOM":
            raise RuntimeError("классификатор споткнулся")
        return _fake_classify(card)
    cards = [{"offerId": "F", "_klass": "frozen"}, {"offerId": "BOOM"}, {"offerId": "C", "_klass": "clean"}]
    h = cab.card_health(cards, classify_fn=flaky)
    ok = h["cards_errored"] == 1 and h["cards_total"] == 3 and h["by_klass"].get("unknown") == 1
    return ok, f"errored={h['cards_errored']} total={h['cards_total']} unknown={h['by_klass'].get('unknown')}"


def ch6_real_classifier_contract():
    """Реальный write.classify_card_health (если импортируем) отдаёт dict с 'klass' — контракт цел.

    Если параллельная линия временно сломала импорт — адаптер обязан пережить (это и есть его смысл),
    поэтому недостижимость тоже PASS (с пометкой): жёсткой связи с write у цикла нет.
    """
    fn = cab._classifier()
    if fn is None:
        return True, "write недоступен — адаптер честно деградирует (ожидаемо, не жёсткая связь)"
    r = fn({"offerId": "X", "cardStatus": "PUBLISHED", "errors": [], "contentRating": 50})
    ok = isinstance(r, dict) and "klass" in r
    return ok, f"реальный классификатор отдал klass={r.get('klass')!r}"


# ─────────────────────────── collect_kpis ───────────────────────────

def kp1_no_cabinet_uses_memory():
    """Без снимка кабинета cards_errored — из памяти (обратная совместимость: поведение как было)."""
    out = day_mod.collect_kpis(_mem_st(4), None, cabinet=None)
    return out["cards_errored"] == 4, f"cards_errored={out['cards_errored']} (память=4)"


def kp2_live_overrides_memory():
    """Кабинет прочитан живьём → его cards_errored перекрывает память само-модели."""
    cabinet = {"catalog": {"cards": 9, "cards_errored": 2}, "offers_live": 1,
               "shops_total": 1, "disabled": 0}
    out = day_mod.collect_kpis(_mem_st(4), None, cabinet=cabinet)
    return out["cards_errored"] == 2, f"память=4 → живьём=2, взято {out['cards_errored']}"


def kp3_live_none_keeps_memory():
    """Кабинет прочитан, но здоровье недостижимо (None) → память сохраняем, «live» не выдумываем."""
    cabinet = {"catalog": {"cards": 9, "cards_errored": None}, "offers_live": 1,
               "shops_total": 1, "disabled": 0}
    out = day_mod.collect_kpis(_mem_st(4), None, cabinet=cabinet)
    return out["cards_errored"] == 4, f"живьём=None → память=4 сохранена, получили {out['cards_errored']}"


# ─────────────────────────── run_day (сокет) ───────────────────────────

def _run(**kw):
    os.environ["YM_DAY_JOURNAL"] = _tmp_journal()
    return day_mod.run_day(shift_fn=False, tick_fn=False, remember=False, use_env=False, **kw)


def w1_socket_live_over_memory():
    """Оживлён мёртвый сокет: inject ридер → kpis.cards_errored живое, source=cabinet_live, снимок в отчёте."""
    snap = {"catalog": {"cards": 5, "cards_errored": 3, "errored": [{"offerId": "F", "klass": "frozen"}]},
            "offers_live": 0, "shops_total": 1, "disabled": 0}
    d = _run(cabinet_read_fn=lambda: snap)
    ok = (d["kpis"]["cards_errored"] == 3 and d["cards_errored_source"] == "cabinet_live"
          and d.get("cabinet") is snap)
    return ok, f"cards_errored={d['kpis']['cards_errored']} source={d['cards_errored_source']} снимок={d.get('cabinet') is snap}"


def w2_no_read_keeps_memory():
    """Без чтения кабинета — source=memory, поведение прежнее (обратная совместимость)."""
    d = _run()
    ok = d["cards_errored_source"] == "memory" and d.get("cabinet") is None and "kpis" in d
    return ok, f"source={d['cards_errored_source']} снимок={d.get('cabinet')} kpis_есть={'kpis' in d}"


def w3_read_only_dry():
    """READ, 0₽: цикл остаётся dry=True/commit=False; ридер реально вызван; наружу ничего не идёт."""
    called = {"n": 0}
    def reader():
        called["n"] += 1
        return {"catalog": {"cards": 2, "cards_errored": 0}, "offers_live": 2,
                "shops_total": 1, "disabled": 0}
    d = _run(cabinet_read_fn=reader)
    ok = d["dry"] is True and d["commit"] is False and called["n"] == 1
    return ok, f"dry={d['dry']} commit={d['commit']} ридер-вызван={called['n']}"


def w4_read_failure_survived():
    """B2: ридер упал → день НЕ падает, провал виден в failures, cards_errored откатился к памяти."""
    def boom():
        raise RuntimeError("чтение кабинета намеренно упало")
    d = _run(cabinet_read_fn=boom)
    survived = isinstance(d, dict) and "kpis" in d
    visible = any("живое чтение кабинета упало" in f for f in d.get("failures", []))
    fell_back = d["cards_errored_source"] == "memory" and d.get("cabinet") is None
    return survived and visible and fell_back, \
        f"день собран={survived} провал_виден={visible} откат_к_памяти={fell_back}"


# ─────────────────────────── АДАПТЕР: needs_placement как список ───────────────────────────

def ch7_needs_placement_surfaced():
    """Паритет с reconcile: needs_placement — first-class список (контент готов, не в кампании),
    и он НЕ считается ошибкой (не попадает в cards_errored)."""
    cards = [{"offerId": "P", "_klass": "needs_placement"},
             {"offerId": "F", "_klass": "frozen"}]
    h = cab.card_health(cards, classify_fn=_fake_classify)
    ok = (h["cards_errored"] == 1
          and len(h["needs_placement"]) == 1
          and h["needs_placement"][0]["offerId"] == "P")
    return ok, f"errored={h['cards_errored']} needs_placement={[r['offerId'] for r in h['needs_placement']]}"


# ─────────────────────────── РЕЦЕПТ ЛЕЧЕНИЯ (build_heal, рунг 4c) ───────────────────────────

def _live_cab(errored=(), needs_placement=(), cards_errored="auto"):
    """Снимок кабинета в той форме, как его отдаёт _read_cabinet после card_health."""
    er = [{"offerId": s, "klass": "frozen"} for s in errored]
    pl = [{"offerId": s, "klass": "needs_placement"} for s in needs_placement]
    ce = len(er) if cards_errored == "auto" else cards_errored
    return {"catalog": {"cards": len(er) + len(pl), "cards_errored": ce,
                        "errored": er, "needs_placement": pl}}


def hl1_live_rebuild_names_exact_skus():
    """Живые ошибки → needed=True; команда точечного ремонта называет ТОЧНЫЕ SKU + плейсхолдеры xlsx/slug."""
    h = day_mod.build_heal(_live_cab(errored=["111-1", "222-1"]), {"cards_errored": 2},
                           "cabinet_live", lookup_fn=lambda s: None)
    cmd = (h.get("rebuild") or {}).get("command", "")
    ok = (h["needed"] is True and h["rebuild"]["skus"] == ["111-1", "222-1"]
          and "--skus 111-1,222-1" in cmd and "<ДОНОР.xlsx>" in cmd and "<SLUG>" in cmd
          and "--not-available" in cmd)
    return ok, f"needed={h['needed']} skus={h['rebuild']['skus']} …{cmd[-42:]!r}"


def hl2_live_place_named_not_error():
    """needs_placement → heal.place называет SKU (та же команда), но это НЕ ошибка (rebuild пуст)."""
    h = day_mod.build_heal(_live_cab(errored=[], needs_placement=["333-1"], cards_errored=0),
                           {"cards_errored": 0}, "cabinet_live", lookup_fn=lambda s: None)
    ok = (h["place"]["skus"] == ["333-1"] and h["rebuild"] is None
          and "--skus 333-1" in h["place"]["command"] and h["needed"] is True)
    return ok, f"place={h['place']['skus']} rebuild={h['rebuild']}"


def hl3_memory_errors_none_no_invention():
    """Ошибки ЛИШЬ ИЗ ПАМЯТИ → needed=None: точные SKU не выдумываем; note зовёт включить live-чтение."""
    h = day_mod.build_heal({"catalog": {}}, {"cards_errored": 3}, "memory", lookup_fn=lambda s: None)
    ok = (h["needed"] is None and h["rebuild"] is None and h["place"] is None
          and "ИЗ ПАМЯТИ" in (h["note"] or ""))
    return ok, f"needed={h['needed']} note={(h['note'] or '')[:34]!r}"


def hl4_live_classifier_none_incomplete():
    """Кабинет прочитан, но здоровье None (write мид-фикс) → needed=None (сверка неполна, не выдумываем)."""
    h = day_mod.build_heal({"catalog": {"cards_errored": None}}, {"cards_errored": 0},
                           "cabinet_live", lookup_fn=lambda s: None)
    ok = h["needed"] is None and h["rebuild"] is None and "недостижимо" in (h["note"] or "")
    return ok, f"needed={h['needed']} note={(h['note'] or '')[:34]!r}"


def hl5_clean_false():
    """Витрина чиста живьём → needed=False, команды нет (нечего чинить)."""
    h = day_mod.build_heal(_live_cab(errored=[], cards_errored=0), {"cards_errored": 0},
                           "cabinet_live", lookup_fn=lambda s: None)
    ok = h["needed"] is False and h["rebuild"] is None and h["place"] is None
    return ok, f"needed={h['needed']}"


def hl6_provenance_single_supplier_note():
    """Провенанс из реестра: все SKU одного поставщика → note подсказывает ЧЬЮ выгрузку/slug подставить."""
    h = day_mod.build_heal(_live_cab(errored=["111-1", "222-1"]), {"cards_errored": 2},
                           "cabinet_live",
                           lookup_fn=lambda s: {"supplier": "cargo-avto", "donor_url": "u/" + s})
    prov = h["rebuild"]["provenance"]
    ok = ("cargo-avto" in (h["note"] or "")
          and all(p["supplier"] == "cargo-avto" for p in prov)
          and all(p["donor_url"] for p in prov))
    return ok, f"note={(h['note'] or '')[:40]!r} prov={len(prov)}"


def hl7_rubicon_recipe_only():
    """RUBICON: heal — РЕЦЕПТ, не действие. Всегда несёт метку невыполнения + команда ТОЧЕЧНАЯ (--skus)."""
    h = day_mod.build_heal(_live_cab(errored=["111-1"]), {"cards_errored": 1},
                           "cabinet_live", lookup_fn=lambda s: None)
    cmd = h["rebuild"]["command"]
    ok = ("commit-пути нет" in h["rubicon"] and "--skus" in cmd and "--not-available" in cmd)
    return ok, f"rubicon={h['rubicon'][:28]!r} точечная={'--skus' in cmd}"


def hl8_burning_shows_command_e2e():
    """E2E через run_day: живой снимок с ошибкой → day.heal.rebuild + пункт «горит» с ТОЙ ЖЕ командой."""
    snap = {"catalog": {"cards": 3, "cards_errored": 1,
                        "errored": [{"offerId": "9603273-1", "klass": "frozen"}],
                        "needs_placement": []},
            "offers_live": 0, "shops_total": 1, "disabled": 0}
    d = _run(cabinet_read_fn=lambda: snap)
    heal = d.get("heal") or {}
    cmd = (heal.get("rebuild") or {}).get("command")
    burn_cmds = [b.get("action") for b in (d.get("burning") or {}).get("items", [])
                 if b.get("heal_ref") == "day.heal.rebuild"]
    ok = (heal.get("needed") is True and cmd and "9603273-1" in cmd and cmd in burn_cmds)
    return ok, f"heal.needed={heal.get('needed')} команда_в_горит={cmd in burn_cmds}"


TESTS = [
    ("CH1  unavailable_none_not_zero", ch1_unavailable_none_not_zero),
    ("CH2  errored_frozen_and_fixable", ch2_errored_frozen_and_fixable),
    ("CH3  store_block_not_our_error", ch3_store_block_not_our_error),
    ("CH4  clean_processing_not_error", ch4_clean_processing_not_error),
    ("CH5  one_bad_card_failsoft", ch5_one_bad_card_failsoft),
    ("CH6  real_classifier_contract", ch6_real_classifier_contract),
    ("CH7  needs_placement_surfaced", ch7_needs_placement_surfaced),
    ("KP1  no_cabinet_uses_memory", kp1_no_cabinet_uses_memory),
    ("KP2  live_overrides_memory", kp2_live_overrides_memory),
    ("KP3  live_none_keeps_memory", kp3_live_none_keeps_memory),
    ("W1   socket_live_over_memory", w1_socket_live_over_memory),
    ("W2   no_read_keeps_memory", w2_no_read_keeps_memory),
    ("W3   read_only_dry", w3_read_only_dry),
    ("W4   read_failure_survived", w4_read_failure_survived),
    ("HL1  live_rebuild_names_exact_skus", hl1_live_rebuild_names_exact_skus),
    ("HL2  live_place_named_not_error", hl2_live_place_named_not_error),
    ("HL3  memory_errors_none", hl3_memory_errors_none_no_invention),
    ("HL4  live_classifier_none", hl4_live_classifier_none_incomplete),
    ("HL5  clean_false", hl5_clean_false),
    ("HL6  provenance_single_supplier", hl6_provenance_single_supplier_note),
    ("HL7  rubicon_recipe_only", hl7_rubicon_recipe_only),
    ("HL8  burning_shows_command_e2e", hl8_burning_shows_command_e2e),
]


def main():
    print("🎯 ЯНДЕКС ПРИЁМКА · СВЕРКА в цикл — cards_errored из живого кабинета, не из памяти (сухо, 0₽)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<30} {detail}")
        passed += 1 if ok else 0
    os.environ.pop("YM_DAY_JOURNAL", None)
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ СВЕРКА провязана честно: живой errors[] перекрывает память, разрыв к write = None (не 0), "
              "store-блок ≠ наша ошибка, цикл остаётся сухим, падение чтения не роняет день")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты photo_insight_v1 — ЧИСТО офлайн (0 сети): mine/honest_gate на синтетической WB-выдаче.
Запуск:  python3 tests/run_photo_insight.py
Метод:  число проходов считаем вручную из фикстуры ниже; вес = 1.0 + min(2.5, sqrt(fb)/6) + (0.5 если поз<=10).
"""
import os
import sys
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import photo_insight_v1 as ins  # noqa: E402

# ── ФИКСТУРА: топ-выдача WB, 10 карточек (порядок = позиция выдачи) ─────────────────────
PAYLOAD = [
    {"id": 101, "name": "Воздушно-пузырьковая плёнка 3-слойная 50 мкм 1,2 м рулон 100 м", "brand": "ПакМир", "feedbacks": 2000},
    {"id": 102, "name": "Пузырчатая пленка пузырьковая упаковочная, 5 слоев усиленная, 40 мкм", "brand": "X", "feedbacks": 500},
    {"id": 103, "name": "Пленка воздушно пузырьковая стретч премиум 80 мкм 1,5 м ширина", "brand": "Y", "feedbacks": 900},
    {"id": 104, "name": "Плёнка ВПП пищевая двухслойная рулон 30 см 120 г/м2", "brand": "Z", "feedbacks": 100},
    {"id": 105, "name": "Пузырчатая пленка с пузырьками 16 мм термо влагозащитная рулон", "brand": "W", "feedbacks": 40},
    {"id": 106, "name": "Пленка пузырьковая 3 слоя ширина 120 см эко", "brand": "V", "feedbacks": 3200},
    {"id": 107, "name": "Коробка гофрокартон 5-слойная Т-24 600x400x400 мм прочная", "brand": "КоробКо", "feedbacks": 1500},
    {"id": 108, "name": "Короб гофро 4 слойный усиленный, влагостойкий", "brand": "К", "feedbacks": 60},
    {"id": 109, "name": "Коробка картонная Т-23 трёхслойная стандарт", "brand": "К2", "feedbacks": 20},
    {"id": 110, "name": "Короб гофрокартонный 7-слойный армированный premium", "brand": "К3", "feedbacks": 800},
]

FAILS = []


def eq(what, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {what}  → {got!r}" + ("" if ok else f"  (надо {want!r})"))
    if not ok:
        FAILS.append(what)


def t1_mine_counts():
    print("t1_mine_counts")
    rep = ins.mine(PAYLOAD)
    fam = {f["key"]: f for f in rep["families"]}
    eq("meta.scanned", rep["meta"]["scanned"], 10)
    eq("meta.kind", rep["meta"]["kind"], "wb_title_proxy")
    # вручную посчитанные количества по фикстуре
    eq("layers.count (8 карточек)", fam["layers"]["count"], 8)
    eq("tmark.count (Т-24,Т-23)", fam["tmark"]["count"], 2)
    eq("armor.count", fam["armor"]["count"], 4)
    eq("water.count", fam["water"]["count"], 2)
    eq("premium.count (2)", fam["premium"]["count"], 2)
    eq("bubble.count", fam["bubble"]["count"], 5)
    eq("thickness.count (3: только мкм; габариты не толщина)", fam["thickness"]["count"], 3)
    eq("density.count (1)", fam["density"]["count"], 1)
    eq("format.count", fam["format"]["count"], 5)
    eq("food.count (1)", fam["food"]["count"], 1)
    eq("eco.count (1)", fam["eco"]["count"], 1)
    eq("heat.count (1)", fam["heat"]["count"], 1)
    eq("shock отсутствует (0 встреч — семейства нет)", "shock" in fam, False)
    # дедуп ВНУТРИ названия: одна карточка со 100м и 1,2м — формат посчитан 1 раз (5, не 7)
    eq("format НЕ размножился по числу вхождений", fam["format"]["count"], 5)
    # у каждой семьи есть прослеживаемый пример заголовка
    for f in rep["families"]:
        if not f["example_titles"]:
            eq("example_titles не пуст у " + f["key"], False, True)


def t2_weight_and_order():
    print("t2_weight_and_order")
    rep = ins.mine(PAYLOAD)
    fam = {f["key"]: f for f in rep["families"]}
    # вес top-карточки (fb3200, поз6): 1+2.5+0.5=4.0; каждая ячейка слоёв взвешена спрос-прокси
    eq("вес карточки fb3200 = 4.0", ins._weight(3200, 6), 4.0)
    eq("вес карточки fb60 = 2.791", round(ins._weight(60, 8), 3), 2.791)
    eq("вес карточки fb20 = 2.245", round(ins._weight(20, 9), 3), 2.245)
    # взвешивание ПЕРЕСТАВЛЯЕТ топ: layers (8 карточек, много тяжёлых) обгоняет толщину/пузырёк
    eq("топ-семейство = layers (вес, не сырое число)", rep["families"][0]["key"], "layers")
    eq("layers.weighted ≈ 28.2", round(fam["layers"]["weighted"], 1), 28.2)
    # категория-подсказка раскладывается по короб/плёнка
    eq("layers box=4 film=4", (fam["layers"]["category_hints"]["box"], fam["layers"]["category_hints"]["film"]), (4, 4))


def t3_empty_and_limit():
    print("t3_empty_and_limit")
    rep0 = ins.mine([])
    eq("mine([]) → 0 семейств", len(rep0["families"]), 0)
    eq("mine([]) → scanned 0", rep0["meta"]["scanned"], 0)
    rep5 = ins.mine(PAYLOAD, limit=5)
    eq("mine(limit=5) режет до 5", rep5["meta"]["scanned"], 5)


def t4_honest_gate():
    print("t4_honest_gate")
    rep = ins.mine(PAYLOAD)
    # Короб, где наши факты подтверждают СЛОИ/МАРКУ/УСИЛЕНИЕ/ВЛАГО — но НЕ подтверждают premium/плотность
    facts_box = {"материал": "гофрокартон пятислойный", "марка": "Т-24",
                 "вид": "усиленный влагостойкий", "размер": "600×400×400 мм"}
    passed = set(ins.honest_gate(rep, facts_box))
    eq("gate пропускает ровно подтверждённое", passed, {"layers", "tmark", "armor", "water"})
    # даже если семейство в insight есть (premium/density/format/heat/bubble) — без факта НЕ проходит
    for not_in in ("premium", "density", "format", "bubble", "heat", "eco", "food", "thickness"):
        eq(f"без факта НЕ проходит: {not_in}", not_in in passed, False)
    # добавили плотность → density проходит
    facts_d = dict(facts_box, **{"плотность_г_м2": 120})
    passed_d = set(ins.honest_gate(rep, facts_d))
    eq("появился факт плотности → density вошёл", "density" in passed_d, True)
    # простое семейство-факт без insight-подтверждения в тексте карточек — тоже не выдумываем
    rep_empty = ins.mine([])
    eq("insight пуст → gate пуст", ins.honest_gate(rep_empty, facts_d), [])
    # форма с голым списком ключей: слои в insight есть, но в facts только плотность
    slim = {"families": [{"key": "layers"}, {"key": "density"}, {"key": "eco"}]}
    eq("gate по списку ключей чтит только реальные факты", ins.honest_gate(slim, {"плотность_г_м2": 120}), ["density"])
    # top-ограничение
    eq("top=2 режет", len(ins.honest_gate(rep, facts_box, top=2)), 2)


def t5_meta_marks_honesty():
    print("t5_meta_marks_honesty")
    rep = ins.mine(PAYLOAD)
    note = rep["meta"]["note"].lower()
    eq("meta явно маркирует границу (заголовки, не пиксели)", "заголовков" in note and "пиксели" in note, True)
    eq("meta.kind = wb_title_proxy (не продажи)", rep["meta"]["kind"], "wb_title_proxy")


def t6_category_hint():
    print("t6_category_hint")
    eq("film: пузырьковая плёнка", ins._category_hint("Плёнка воздушно-пузырьковая"), "film")
    eq("film: стретч", ins._category_hint("Стретч-плёнка 500 м"), "film")
    eq("box: гофрокороб", ins._category_hint("Короб гофрокартонный 5-слойный"), "box")
    eq("box: ящик", ins._category_hint("Ящик из гофры"), "box")
    eq("generic: неопределимое", ins._category_hint("Пакет полиэтиленовый"), None)


def t7_dimension_noise_guard():
    print("t7_dimension_noise_guard")
    # Габарит коробки «220х50х20 мм» НЕ должен давать семейство толщины
    dim = ins._match_families("Коробки картонные самосборные 220х50х20 мм")
    eq("габарит ШхДхВ мм → НЕ толщина", "thickness" in dim, False)
    # Толщина материала (мкм) — толщина
    mkm = ins._match_families("Пленка пузырьковая упаковочная 40 мкм")
    eq("мкм → толщина", "thickness" in mkm, True)
    # Явное «толщина… мм»
    sl = ins._match_families("Гофрокартон толщиной 7 мм листовой")
    eq("толщиной N мм → толщина", "thickness" in sl, True)
    # «картон 3 мм» — толщина листа
    card = ins._match_families("Картон переплетный 3 мм А4")
    eq("картон N мм → толщина", "thickness" in card, True)
    # размер через «х» латиницей тоже габарит
    dimx = ins._match_families("Коробка 50x50x40 см")
    eq("габарит 50x50x40 см → НЕ толщина (и см вне единиц)", "thickness" in dimx, False)


if __name__ == "__main__":
    for fn in (t1_mine_counts, t2_weight_and_order, t3_empty_and_limit, t4_honest_gate, t5_meta_marks_honesty, t6_category_hint, t7_dimension_noise_guard):
        fn()
    print()
    if FAILS:
        print(f"✗ ПРОВАЛЫ ({len(FAILS)}):")
        for f in FAILS:
            print("   -", f)
        sys.exit(1)
    print("✓ photo_insight_v1: все тесты зелёные (0 сети, 0₽)")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — УНИКАЛЬНОЕ НАИМЕНОВАНИЕ КАРТОЧКИ (анти-склейка). Сухо, 0₽, БЕЗ СЕТИ.

Орган: card.to_offer собирает СВОЁ уникальное имя БЕЗ ПОТЕРЬ — имя товара 1-в-1 + свой квалификатор
(house_brand/extra_kw) суффиксом. Вторичный рычаг склейки; главный — свой штрихкод. ВЫКЛ по умолч.

ГЛАВНЫЙ ЗАКОН (после состязательного ревью 2026-08-13): имя товара НЕПРИКОСНОВЕННО. Размер/единицы
(«0,3×100 м», «40 г/м²») часто живут в дробях и одиночных символах — любой рерайт их искажает
(«0,3×100»→«3x100», 10× ошибка) или теряет. Поэтому source_name обязан выживать СИМВОЛ-В-СИМВОЛ как
префикс итогового имени. Проверяем ЗАКОНЫ, а не «запустилось»:

  CU1  default_verbatim            — без флага имя ДОСЛОВНОЕ, name_source=verbatim (обратн. совмест.)
  CU2  optin_appends_brand         — unique_name=True + house_brand → имя = «имя Бренд», source=unique
  CU3  no_qualifier_is_fallback    — флаг есть, но добавить нечего → verbatim_fallback (не врём)
  CU4  name_build_self_contained   — сборка имени НЕ зависит от uniqueizer (битый модуль не мешает)
  CU5  prod_flag_path              — prod['unique_name']=True (+house_brand) без аргумента включает
  CU6  arg_overrides_prod_flag     — аргумент unique_name=False перебивает флаг в prod (явное ВЫКЛ)
  CU7  oversized_qualifier_dropped — бренд не влез в 150 → ОТБРОШЕН (не режем посреди слова), имя цело
  CU8  meta_original_name_honest   — при добавлении meta.original_name хранит исходное; иначе None
  CU9  decimal_size_preserved      — ⛳ ГЛАВНЫЙ: «0,3×100 м» выживает СИМВОЛ-В-СИМВОЛ (не «3x100»)
  CU10 create_card_threads_dry     — сквозь writer(dry) размер-несущее имя доходит в offer-mappings
  CU11 own_card_fields_sets_flag   — отвязка xlsx ставит unique_name=True (+vendor «Без бренда»)
  CU12 long_name_not_truncated     — имя из >8 токенов НЕ обрезается (все токены целы)
  CU13 brand_in_name_not_dup       — бренд уже в имени (иной регистр) → НЕ дублируется → fallback
  CU14 extra_kw_string_one_word    — extra_kw='строка' = ОДИН ключ (не итерируем по буквам!)
  CU15 extra_kw_list_appended      — extra_kw=['a','b'] добавляются словами
  CU16 degenerate_no_fabrication   — размер-только имя не подменяется на «Товар»; суть цела
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_card_v1 as card          # noqa: E402
import ymarket_write_v1 as write        # noqa: E402
import ymarket_from_xlsx_v1 as xlsx     # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def _lossless_prefix(src, out):
    """ЗАКОН БЕЗ ПОТЕРЬ: имя товара выживает символ-в-символ как префикс (или имя не тронуто)."""
    return bool(src) and out.startswith(src) and (len(out) == len(src) or out[len(src)] == " ")


# ── тесты ──────────────────────────────────────────────────────────────────────

def cu1_default_verbatim():
    prod = {"sku": "S1", "name": "Контейнер пищевой", "cost": 99.0}
    r = card.to_offer(prod, slug="pishevaya-upakovka")
    o, m = r["offer"], r["meta"]
    ok = (o["name"] == "Контейнер пищевой" and m["name_source"] == "verbatim"
          and m["original_name"] is None)
    return ok, f"имя='{o['name']}' source={m['name_source']} original={m['original_name']}"


def cu2_optin_appends_brand():
    src = "Контейнер пищевой"
    prod = {"sku": "S2", "name": src, "cost": 99.0}
    r = card.to_offer(prod, slug="pishevaya-upakovka", unique_name=True, house_brand="Атлас")
    o, m = r["offer"], r["meta"]
    ok = (m["name_source"] == "unique" and o["name"] == "Контейнер пищевой Атлас"
          and _lossless_prefix(src, o["name"]))
    return ok, f"имя='{o['name']}' source={m['name_source']} (суть-префикс цел={_lossless_prefix(src, o['name'])})"


def cu3_no_qualifier_is_fallback():
    # флаг включён, но house_brand/extra_kw не заданы → добавить нечего → честный откат
    prod = {"sku": "S3", "name": "Контейнер пищевой", "cost": 99.0}
    r = card.to_offer(prod, slug="pishevaya-upakovka", unique_name=True)
    o, m = r["offer"], r["meta"]
    ok = (m["name_source"] == "verbatim_fallback" and o["name"] == "Контейнер пищевой"
          and m["original_name"] is None)
    return ok, f"имя='{o['name']}' source={m['name_source']} (нечего добавить — не выдаём за уникальное)"


def cu4_name_build_self_contained():
    # сборку имени БОЛЬШЕ не зависит от uniqueizer — битый модуль в sys.modules не должен мешать
    saved = sys.modules.get("uniqueizer_v1")
    broken = types.ModuleType("uniqueizer_v1")
    def _boom(*a, **k):
        raise RuntimeError("uniqueizer недоступен")
    broken.unique_title = _boom
    broken.gen_ean13 = _boom
    sys.modules["uniqueizer_v1"] = broken
    try:
        prod = {"sku": "S4", "name": "Контейнер пищевой", "cost": 99.0}
        r = card.to_offer(prod, slug="pishevaya-upakovka", unique_name=True, house_brand="Атлас")
        o, m = r["offer"], r["meta"]
        ok = (m["name_source"] == "unique" and o["name"] == "Контейнер пищевой Атлас")
    finally:
        if saved is not None:
            sys.modules["uniqueizer_v1"] = saved
        else:
            sys.modules.pop("uniqueizer_v1", None)
    return ok, f"битый uniqueizer не помешал → имя='{o['name']}' source={m['name_source']}"


def cu5_prod_flag_path():
    prod = {"sku": "S5", "name": "Контейнер пищевой", "cost": 99.0,
            "unique_name": True, "house_brand": "Атлас"}
    r = card.to_offer(prod, slug="pishevaya-upakovka")   # БЕЗ аргумента — только флаг в prod
    o, m = r["offer"], r["meta"]
    ok = (m["name_source"] == "unique" and o["name"] == "Контейнер пищевой Атлас")
    return ok, f"флаг в prod включил рычаг → имя='{o['name']}' source={m['name_source']}"


def cu6_arg_overrides_prod_flag():
    prod = {"sku": "S6", "name": "Контейнер пищевой", "cost": 99.0,
            "unique_name": True, "house_brand": "Атлас"}
    r = card.to_offer(prod, slug="pishevaya-upakovka", unique_name=False)   # явное ВЫКЛ
    o, m = r["offer"], r["meta"]
    ok = (m["name_source"] == "verbatim" and o["name"] == "Контейнер пищевой")
    return ok, f"аргумент перебил флаг → имя='{o['name']}' source={m['name_source']}"


def cu7_oversized_qualifier_dropped():
    # бренд не влезает в 150 → его ОТБРАСЫВАЕМ целиком (не режем посреди слова), имя товара цело
    src = "Контейнер пищевой"
    prod = {"sku": "S7", "name": src, "cost": 99.0}
    r = card.to_offer(prod, slug="pishevaya-upakovka", unique_name=True, house_brand="Х" * 300)
    o, m = r["offer"]["name"], r["meta"]
    ok = (len(o) <= card.MAX_NAME and o == src and m["name_source"] == "verbatim_fallback")
    return ok, f"имя='{o}' len={len(o)} source={m['name_source']} (бренд не влез → отброшен, имя цело)"


def cu8_meta_original_name_honest():
    prod = {"sku": "S8", "name": "Контейнер пищевой", "cost": 99.0}
    added = card.to_offer(prod, slug="pishevaya-upakovka", unique_name=True, house_brand="Атлас")
    plain = card.to_offer(prod, slug="pishevaya-upakovka")
    ok = (added["meta"]["original_name"] == "Контейнер пищевой"
          and plain["meta"]["original_name"] is None)
    return ok, (f"при добавлении original='{added['meta']['original_name']}', "
                f"без — original={plain['meta']['original_name']}")


def cu9_decimal_size_preserved():
    # ⛳ ГЛАВНЫЙ тест — прямой убийца HIGH-находки. Размер в дроби/× обязан выжить символ-в-символ.
    src = "Плёнка воздушно-пузырьковая 0,3×100 м"
    prod = {"sku": "S9", "name": src, "cost": 350.0}
    r = card.to_offer(prod, slug=None, bridge=False, unique_name=True, house_brand="Атлас")
    o, m = r["offer"]["name"], r["meta"]
    ok = (_lossless_prefix(src, o)          # имя товара символ-в-символ как префикс
          and "0,3×100 м" in o              # размер цел (НЕ «3x100», НЕ «100», НЕ потерян)
          and o == src + " Атлас"
          and m["name_source"] == "unique")
    return ok, f"имя='{o}' — «0,3×100 м» цел={'0,3×100 м' in o}"


def cu10_create_card_threads_dry():
    # сквозь writer в СУХОМ режиме размер-несущее имя обязано дойти ЦЕЛЫМ до offer-mappings
    src = "Плёнка воздушно-пузырьковая 0,3×100 м"
    prod = {"sku": "S10", "name": src, "cost": 120.0, "unique_name": True, "house_brand": "Атлас"}
    res = write.create_card(prod, slug="pishevaya-upakovka", dry=True, commit=False)
    offer = (((res.get("payloads") or {}).get("step1") or {}).get("offerMappings") or [{}])[0].get("offer", {})
    nm = offer.get("name", "")
    ok = (res.get("dry") is True and _lossless_prefix(src, nm) and "0,3×100 м" in nm)
    return ok, f"dry={res.get('dry')} имя в offer-mappings='{nm}'"


def cu11_own_card_fields_sets_flag():
    got = xlsx.own_card_fields({"sku": "ABC", "name": "Плёнка"}, house_brand="")
    got_brand = xlsx.own_card_fields({"sku": "ABC", "name": "Плёнка"}, house_brand="Атлас")
    ok = (got.get("unique_name") is True and got.get("vendor") == "Без бренда"
          and "house_brand" not in got            # «Без бренда» НЕ уходит в заголовок
          and got_brand.get("house_brand") == "Атлас"
          and got.get("barcode"))                  # штрихкод (главный рычаг) на месте
    return ok, (f"unique_name={got.get('unique_name')} vendor='{got.get('vendor')}' "
                f"house_brand(в заголовок)={'нет' if 'house_brand' not in got else got.get('house_brand')} "
                f"с брендом→{got_brand.get('house_brand')}")


def cu12_long_name_not_truncated():
    # имя из >8 значимых токенов НЕ должно резаться (прежний рерайт оставлял только 8)
    src = "Плёнка воздушно-пузырьковая двухслойная ширина 1,5 м длина 100 м плотность 40 г"
    prod = {"sku": "S12", "name": src, "cost": 300.0}
    r = card.to_offer(prod, slug=None, bridge=False, unique_name=True, house_brand="Атлас")
    o, m = r["offer"]["name"], r["meta"]
    ok = (_lossless_prefix(src, o) and "плотность 40 г" in o and "1,5 м" in o
          and m["name_source"] == "unique")
    return ok, f"имя='{o}' — хвост «плотность 40 г» цел={'плотность 40 г' in o}"


def cu13_brand_in_name_not_dup():
    # бренд уже присутствует в имени (в другом регистре) → НЕ добавляем второй раз
    src = "Плёнка атлас защитная"
    prod = {"sku": "S13", "name": src, "cost": 200.0}
    r = card.to_offer(prod, slug=None, bridge=False, unique_name=True, house_brand="Атлас")
    o, m = r["offer"]["name"], r["meta"]
    count = o.lower().count("атлас")
    ok = (count == 1 and o == src and m["name_source"] == "verbatim_fallback")
    return ok, f"имя='{o}' вхождений «атлас»={count} source={m['name_source']}"


def cu14_extra_kw_string_one_word():
    # extra_kw как СТРОКА = один ключ; НЕ итерируем по буквам (была ловушка 'в о д о с т й к и')
    src = "Контейнер пищевой"
    prod = {"sku": "S14", "name": src, "cost": 99.0}
    r = card.to_offer(prod, slug="pishevaya-upakovka", unique_name=True, extra_kw="водостойкий")
    o, m = r["offer"]["name"], r["meta"]
    ok = (o == "Контейнер пищевой водостойкий" and "водостойкий" in o
          and " в о д" not in o and m["name_source"] == "unique")
    return ok, f"имя='{o}' (строка добавлена целым словом, не по буквам)"


def cu15_extra_kw_list_appended():
    src = "Контейнер пищевой"
    prod = {"sku": "S15", "name": src, "cost": 99.0}
    r = card.to_offer(prod, slug="pishevaya-upakovka", unique_name=True,
                      extra_kw=["водостойкий", "прочный"], house_brand="Атлас")
    o, m = r["offer"]["name"], r["meta"]
    ok = (o == "Контейнер пищевой водостойкий прочный Атлас" and _lossless_prefix(src, o)
          and m["name_source"] == "unique")
    return ok, f"имя='{o}'"


def cu16_degenerate_no_fabrication():
    # размер-только имя: раньше рерайт фабриковал «Товар». Теперь суть цела, «Товар» не появляется.
    src = "0,3 м"
    with_brand = card.to_offer({"sku": "S16a", "name": src, "cost": 50.0},
                               unique_name=True, house_brand="Атлас")
    no_brand = card.to_offer({"sku": "S16b", "name": src, "cost": 50.0}, unique_name=True)
    ob, mb = with_brand["offer"]["name"], with_brand["meta"]
    on, mn = no_brand["offer"]["name"], no_brand["meta"]
    ok = (ob == "0,3 м Атлас" and "Товар" not in ob and mb["name_source"] == "unique"
          and on == "0,3 м" and mn["name_source"] == "verbatim_fallback")
    return ok, f"с брендом='{ob}' ({mb['name_source']}), без='{on}' ({mn['name_source']}) — «Товар» не выдуман"


TESTS = [
    ("CU1  default_verbatim", cu1_default_verbatim),
    ("CU2  optin_appends_brand", cu2_optin_appends_brand),
    ("CU3  no_qualifier_is_fallback", cu3_no_qualifier_is_fallback),
    ("CU4  name_build_self_contained", cu4_name_build_self_contained),
    ("CU5  prod_flag_path", cu5_prod_flag_path),
    ("CU6  arg_overrides_prod_flag", cu6_arg_overrides_prod_flag),
    ("CU7  oversized_qualifier_dropped", cu7_oversized_qualifier_dropped),
    ("CU8  meta_original_name_honest", cu8_meta_original_name_honest),
    ("CU9  decimal_size_preserved ⛳", cu9_decimal_size_preserved),
    ("CU10 create_card_threads_dry", cu10_create_card_threads_dry),
    ("CU11 own_card_fields_sets_flag", cu11_own_card_fields_sets_flag),
    ("CU12 long_name_not_truncated", cu12_long_name_not_truncated),
    ("CU13 brand_in_name_not_dup", cu13_brand_in_name_not_dup),
    ("CU14 extra_kw_string_one_word", cu14_extra_kw_string_one_word),
    ("CU15 extra_kw_list_appended", cu15_extra_kw_list_appended),
    ("CU16 degenerate_no_fabrication", cu16_degenerate_no_fabrication),
]


def main():
    print("🎯 ПРИЁМКА · УНИКАЛЬНОЕ НАИМЕНОВАНИЕ КАРТОЧКИ БЕЗ ПОТЕРЬ (сухо, 0₽, БЕЗ СЕТИ)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<34} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Рычаг честен И БЕЗ ПОТЕРЬ: имя товара выживает символ-в-символ (размер «0,3×100 м» цел, "
              "длинное имя не режется, «Товар» не выдумывается), бренд/ключи только суффиксом и без "
              "дублей, не влезло → отброшено целиком, строка-ключ не рвётся по буквам, ВЫКЛ по "
              "умолчанию, аргумент перебивает флаг, сборка имени не зависит от uniqueizer, сквозь "
              "writer в dry имя доходит целым (0₽), долг own_card_fields закрыт.")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

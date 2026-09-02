#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON CATEGORY SCOUT ПРИЁМКА — РАЗВЕДЧИК КАТЕГОРИЙ (READ, 0₽, без сети/ключа).

Доказываем НЕДОСТАЮЩЕЕ ЗВЕНО сухой плоскости: имя товара → живой ЛИСТ дерева (dci+type_id) →
атрибуты/словарь → card-ready ПРОФИЛЬ, который ест ozon_card_v1._build_attributes. И — главное —
что орган ЧЕСТЕН по закону OZ2: слабо/неоднозначно/нет-значения → НЕ выдумываем.

Все тесты оффлайн-детерминированы: читатели дерева/атрибутов/значений ИНЪЕКТИРУЮТСЯ моками
(либо, в SC3, боевые имена ozon_hands_write_v1 подменяются моками) — НИКАКОЙ сети, ключа, денег.
Ключ Ozon из окружения глушится (как в run_ozon_m0) — падение сквозь моки упрётся в «нет ключа»,
секрет в тест не попадёт. RUBICON физически недостижим: в разведчике нет ни одного write-пути.

  ── find_leaf (единственный законный источник dci+type_id) ──
  C1  leaf_inherits_dci        — лист наследует dci предка; находим по имени типа.
  C2  leaf_skips_disabled      — поддерево disabled==true пропускается целиком → нет листа.
  C3  leaf_ambiguous_refused   — два равных листа (margin≈0) → None (OZ2: не гадаем «первый попавшийся»).
  C4  leaf_weak_refused        — слово только в пути, не в имени типа (overlap<порог) → None (OZ2).
  C5  leaf_exact_name_wins     — точное имя типа (+бонус) уверенно бьёт частичное совпадение.
  C6  leaf_type_query_filter   — type_query сужает кандидатов по слову имени типа.
  ── build_profile (форма ровно под ozon_card) ──
  C7  profile_shapes           — spec(dict=0)/enum(dict>1)/constant(dict=1&req) + required_ids/имена.
  C8  constant_only_if_req     — dict с 1 значением, но НЕ обязателен → enum, НЕ constant.
  ── collect_values (курсорная пагинация; истина неполноты пула) ──
  C9  values_paginate          — has_next→last_value_id склеивает страницы; truncated=False.
  C10 values_truncate_flag     — потолок max_pages при живом has_next → truncated=True (пул неполон).
  C11 values_anti_loop         — курсор не двигается → останов без вечного цикла.
  ── assess_completeness (единый источник истины = _build_attributes карточки) ──
  C12 complete_all_covered     — spec покрыл все обязательные → missing_required=[].
  C13 complete_missing_enum    — нет значения обязательного enum → в missing_required (сверено с картой).
  C14 constant_covers_no_spec  — обязательный constant покрыт БЕЗ spec (единственно-законное значение).
  ── scout_category (оркестрация) ──
  C15 scout_e2e_success        — инъекция читателей → полный бандл: dci+type_id+профиль+missing=[].
  C16 scout_no_leaf_mapping    — нет листа под запрос → need_mapping=True, dci=None, missing=None.
  C17 scout_default_wiring     — БЕЗ инъекции читатели берутся из ozon_hands_write_v1 по ИМЕНИ (шов жив).
  C18 scout_truncated_pool     — словарь обрезан по потолку → attribute_id в truncated_attrs, без зависания.
  ── ПЛАТА (ради чего орган существует): разблокировка ozon_card ──
  C19 payoff_can_build         — apply_to_product → to_item: can_build=True, item≠None, атрибуты собраны,
                                 enum разрешён в dictionary_value_id (форма реально ушла бы в /v3/product/import).
  C20 payoff_mapping_blocks    — need_mapping → apply без правок → to_item: item=None, can_build=False (честный блок).
  C21 oz2_no_fabrication       — значение enum вне пула → атрибут НЕ шлётся + он в missing_required (не выдумали id).
  C22 garbage_tree_no_crash    — мусорное/пустое дерево → need_mapping, БЕЗ исключений.

Приёмка НЕ трогает канон, НЕ зовёт сеть. Реальная разведка/залив — только по слову (RUBICON).
"""
import io
import os
import sys
import tempfile
import contextlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


def _sandbox():
    """Temp-каталог для паритета с идиомой (разведчик наружу ничего не пишет — канон не трогаем)."""
    return Path(tempfile.mkdtemp(prefix="ozon_cat_"))


# Импорт органа (после того как sys.path готов)
import ozon_category_scout_v1 as scout   # noqa: E402
import ozon_card_v1 as card              # noqa: E402

# ── ГЕРМЕТИЗАЦИЯ: как в M0 — глушим загрузчик .env и убираем ключи, чтобы ни один путь не утянул
#    боевой (компрометированный) секрет и не ушёл в сеть. Разведчик по умолчанию берёт читателей
#    из этого же singleton'а ozon_hands_write_v1, поэтому флаг действует и на дефолтный шов. ──
import ozon_hands_write_v1 as hands      # noqa: E402
hands._ENV_TRIED = True
os.environ.pop("OZON_CLIENT_ID", None)
os.environ.pop("OZON_API_KEY", None)


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  МОК-ДЕРЕВЬЯ И МОК-ЧИТАТЕЛИ (форма 1-в-1 с боевыми ozon_hands_write_v1)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _tree_stretch():
    """Корень несёт description_category_id; листья наследуют его, у них type_id+type_name."""
    return [{
        "description_category_id": 15621048,
        "category_name": "Плёнки и упаковка",
        "children": [
            {"type_id": 91521, "type_name": "Плёнка стрейч"},
            {"type_id": 91522, "type_name": "Плёнка пищевая"},
        ],
    }]


def _tree_disabled():
    """Единственный лист лежит под disabled-узлом → должен быть пропущен целиком."""
    return [{
        "description_category_id": 100, "category_name": "Электроника",
        "children": [
            {"disabled": True, "description_category_id": 200, "category_name": "Смартфоны",
             "children": [{"type_id": 7, "type_name": "Смартфон"}]},
        ],
    }]


def _tree_ambiguous():
    """Два листа с ОДИНАКОВЫМ именем типа под разными dci → отрыв≈0 → честный отказ."""
    return [
        {"description_category_id": 100, "category_name": "Упаковка А",
         "children": [{"type_id": 1, "type_name": "Плёнка"}]},
        {"description_category_id": 200, "category_name": "Упаковка Б",
         "children": [{"type_id": 2, "type_name": "Плёнка"}]},
    ]


def _tree_path_only():
    """Слово запроса есть в имени ВЕТКИ, но не в имени типа → overlap 0 → слабо → отказ."""
    return [{
        "description_category_id": 100, "category_name": "Стрейч-плёнки для упаковки",
        "children": [{"type_id": 1, "type_name": "Плёнка"}],
    }]


def _tree_gloves():
    """Точное имя типа против частичного совпадения (проверка бонуса за точное имя)."""
    return [{
        "description_category_id": 300, "category_name": "Одежда и защита",
        "children": [
            {"type_id": 1, "type_name": "Перчатки"},
            {"type_id": 2, "type_name": "Перчатки нитриловые смотровые"},
        ],
    }]


def _attrs_full():
    """4 атрибута: свободный-req, enum-req(>1), словарь-req(ровно 1→constant), свободный-не-req."""
    return [
        {"id": 1, "name": "Вес, г", "is_required": True, "dictionary_id": 0},
        {"id": 2, "name": "Цвет", "is_required": True, "dictionary_id": 999},
        {"id": 3, "name": "Тип плёнки", "is_required": True, "dictionary_id": 888},
        {"id": 4, "name": "Комментарий", "is_required": False, "dictionary_id": 0},
    ]


def _values_full():
    """Пул значений по attribute_id (id значения = dictionary_value_id)."""
    return {
        2: [{"id": 101, "value": "Красный"}, {"id": 102, "value": "Синий"}],
        3: [{"id": 501, "value": "Стрейч"}],   # РОВНО одно значение + is_required → constant
    }


def _values_fn_from(pool):
    """Сделать values_fn (одна страница на атрибут), форма 1-в-1 с hands.attribute_values."""
    def vf(dci, tid, aid, last_value_id=0, language="DEFAULT", timeout=60, **kw):
        return {"values": pool.get(aid, []), "has_next": False}
    return vf


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  C1–C6 · find_leaf
# ══════════════════════════════════════════════════════════════════════════════════════════════

def t1_leaf_inherits_dci(d):
    leaf = scout.find_leaf(_tree_stretch(), "плёнка стрейч")
    return (leaf is not None and leaf["description_category_id"] == 15621048
            and leaf["type_id"] == 91521 and leaf["type_name"] == "Плёнка стрейч"), \
        f"leaf={None if leaf is None else (leaf['description_category_id'], leaf['type_id'])}"


def t2_leaf_skips_disabled(d):
    leaf = scout.find_leaf(_tree_disabled(), "смартфон")
    return leaf is None, f"leaf={leaf} (ждём None — единственный лист под disabled)"


def t3_leaf_ambiguous_refused(d):
    leaf = scout.find_leaf(_tree_ambiguous(), "плёнка")
    return leaf is None, f"leaf={leaf} (ждём None — два равных, margin≈0)"


def t4_leaf_weak_refused(d):
    leaf = scout.find_leaf(_tree_path_only(), "стрейч")
    return leaf is None, f"leaf={leaf} (ждём None — совпадение только в пути, overlap<порог)"


def t5_leaf_exact_name_wins(d):
    leaf = scout.find_leaf(_tree_gloves(), "перчатки")
    return (leaf is not None and leaf["type_id"] == 1 and leaf["type_name"] == "Перчатки"), \
        f"leaf={None if leaf is None else (leaf['type_id'], leaf['type_name'])} (ждём точное 'Перчатки')"


def t6_leaf_type_query_filter(d):
    leaf = scout.find_leaf(_tree_stretch(), "плёнка", type_query="пищевая")
    return (leaf is not None and leaf["type_id"] == 91522), \
        f"leaf={None if leaf is None else leaf['type_id']} (ждём 91522 «Плёнка пищевая»)"


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  C7–C8 · build_profile
# ══════════════════════════════════════════════════════════════════════════════════════════════

def t7_profile_shapes(d):
    profile, meta = scout.build_profile(_attrs_full(), _values_full())
    specs, enums, consts = profile["attr_specs"], profile["attr_enums"], profile["attr_constants"]
    ok = (
        "Вес, г" in specs and specs["Вес, г"]["id"] == 1
        and "Комментарий" in specs
        and "Цвет" in enums and enums["Цвет"]["id"] == 2
        and enums["Цвет"]["values"].get("красный") == 101
        and enums["Цвет"]["values"].get("синий") == 102
        and "Тип плёнки" in consts and consts["Тип плёнки"]["dictionary_value_id"] == 501
        and meta["required_ids"] == [1, 2, 3]
        and meta["required_names"].get(2) == "Цвет"
        and meta["n_attrs"] == 4
    )
    return ok, f"specs={list(specs)} enums={list(enums)} consts={list(consts)} req={meta['required_ids']}"


def t8_constant_only_if_req(d):
    attrs = [{"id": 9, "name": "Материал", "is_required": False, "dictionary_id": 777}]
    profile, meta = scout.build_profile(attrs, {9: [{"id": 700, "value": "ПВД"}]})
    return ("Материал" in profile["attr_enums"] and profile["attr_constants"] == {}
            and profile["attr_enums"]["Материал"]["values"].get("пвд") == 700), \
        f"enums={list(profile['attr_enums'])} consts={list(profile['attr_constants'])} (1 знач.+не-req → enum)"


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  C9–C11 · collect_values
# ══════════════════════════════════════════════════════════════════════════════════════════════

def t9_values_paginate(d):
    def vf(dci, tid, aid, last_value_id=0, **kw):
        if last_value_id == 0:
            return {"values": [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}], "has_next": True}
        return {"values": [{"id": 3, "value": "c"}], "has_next": False}
    vals, trunc = scout.collect_values(1, 2, 5, vf, max_pages=20)
    return (len(vals) == 3 and trunc is False), f"собрано={len(vals)} truncated={trunc} (ждём 3, False)"


def t10_values_truncate_flag(d):
    def vf(dci, tid, aid, last_value_id=0, **kw):
        return {"values": [{"id": last_value_id + 1, "value": "x"}], "has_next": True}
    vals, trunc = scout.collect_values(1, 2, 5, vf, max_pages=3)
    return (len(vals) == 3 and trunc is True), f"собрано={len(vals)} truncated={trunc} (ждём 3, True)"


def t11_values_anti_loop(d):
    calls = {"n": 0}

    def vf(dci, tid, aid, last_value_id=0, **kw):
        calls["n"] += 1
        return {"values": [{"id": 9, "value": "x"}], "has_next": True}   # курсор застрял на 9
    vals, trunc = scout.collect_values(1, 2, 5, vf, max_pages=20)
    # 1-й вызов двинул курсор 0→9, 2-й увидел тот же max=9 → останов. Не должно быть 20 вызовов.
    return (calls["n"] == 2 and trunc is False and len(vals) == 2), \
        f"вызовов={calls['n']} truncated={trunc} собрано={len(vals)} (ждём 2/False/2, без зацикливания)"


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  C12–C14 · assess_completeness (сверка с ozon_card._build_attributes — единый источник истины)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def t12_complete_all_covered(d):
    profile, meta = scout.build_profile(_attrs_full(), _values_full())
    miss = scout.assess_completeness(profile, {"Вес, г": 300, "Цвет": "Красный"}, meta["required_ids"])
    return miss == [], f"missing={miss} (ждём [] — все обязательные покрыты)"


def t13_complete_missing_enum(d):
    profile, meta = scout.build_profile(_attrs_full(), _values_full())
    spec = {"Вес, г": 300}                       # Цвет НЕ задан
    miss = scout.assess_completeness(profile, spec, meta["required_ids"])
    # Независимая сверка: чего РЕАЛЬНО не эмитит сама карточка — то и есть истина неполноты.
    emitted = {a.get("id") for a in card._build_attributes({"_spec": dict(spec)}, profile)}
    indep = [rid for rid in meta["required_ids"] if rid not in emitted]
    return (miss == [2] and miss == indep), f"missing={miss} независимо={indep} (ждём [2], совпадение)"


def t14_constant_covers_no_spec(d):
    profile, meta = scout.build_profile(_attrs_full(), _values_full())
    miss = scout.assess_completeness(profile, {}, meta["required_ids"])   # spec пуст
    # constant (Тип плёнки, id=3) эмитится БЕЗ spec → его нет в missing; свободный/enum — есть.
    return (3 not in miss and set(miss) == {1, 2}), \
        f"missing={miss} (ждём {{1,2}}, id=3 покрыт единственно-законным значением)"


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  C15–C18 · scout_category
# ══════════════════════════════════════════════════════════════════════════════════════════════

def t15_scout_e2e_success(d):
    sc = scout.scout_category(
        "плёнка стрейч", spec={"Вес, г": 300, "Цвет": "Красный"},
        tree_fn=lambda **kw: _tree_stretch(),
        attrs_fn=lambda dci, tid, **kw: _attrs_full(),
        values_fn=_values_fn_from(_values_full()),
    )
    ok = (sc["need_mapping"] is False
          and sc["description_category_id"] == 15621048 and sc["type_id"] == 91521
          and isinstance(sc["_profile"], dict)
          and set(sc["_profile"]) == {"attr_constants", "attr_specs", "attr_enums"}
          and sc["missing_required"] == [] and sc["truncated_attrs"] == []
          and sc["evidence"]["n_required"] == 3 and sc["evidence"]["n_dictionary"] == 2)
    return ok, f"dci={sc['description_category_id']} tid={sc['type_id']} missing={sc['missing_required']}"


def t16_scout_no_leaf_mapping(d):
    sc = scout.scout_category(
        "телевизор плазменный", spec={"Вес, г": 300},
        tree_fn=lambda **kw: _tree_stretch(),
        attrs_fn=lambda dci, tid, **kw: _attrs_full(),
        values_fn=_values_fn_from(_values_full()),
    )
    return (sc["need_mapping"] is True and sc["description_category_id"] is None
            and sc["missing_required"] is None), \
        f"need_mapping={sc['need_mapping']} dci={sc['description_category_id']} missing={sc['missing_required']}"


def t17_scout_default_wiring(d):
    """БЕЗ инъекции: читатели должны браться из ozon_hands_write_v1 по ИМЕНИ (проверяем живость шва)."""
    orig = (hands.category_tree, hands.category_attributes, hands.attribute_values)
    try:
        hands.category_tree = lambda language="DEFAULT", timeout=60: _tree_stretch()
        hands.category_attributes = lambda dci, tid, language="DEFAULT", timeout=60: _attrs_full()
        hands.attribute_values = lambda dci, tid, aid, last_value_id=0, language="DEFAULT", timeout=60, **kw: \
            {"values": _values_full().get(aid, []), "has_next": False}
        sc = scout.scout_category("плёнка стрейч", spec={"Вес, г": 300, "Цвет": "Красный"})
    finally:
        hands.category_tree, hands.category_attributes, hands.attribute_values = orig
    return (sc["need_mapping"] is False and sc["description_category_id"] == 15621048
            and sc["type_id"] == 91521 and sc["missing_required"] == []), \
        f"dci={sc['description_category_id']} tid={sc['type_id']} (через дефолтный шов hands.*)"


def t18_scout_truncated_pool(d):
    def vf(dci, tid, aid, last_value_id=0, **kw):
        return {"values": [{"id": last_value_id + 1, "value": f"c{last_value_id + 1}"}], "has_next": True}
    sc = scout.scout_category(
        "плёнка стрейч", spec={"Цвет": "c1"},
        tree_fn=lambda **kw: _tree_stretch(),
        attrs_fn=lambda dci, tid, **kw: [{"id": 2, "name": "Цвет", "is_required": True, "dictionary_id": 999}],
        values_fn=vf, max_value_pages=2,
    )
    return (sc["truncated_attrs"] == [2] and sc["need_mapping"] is False), \
        f"truncated_attrs={sc['truncated_attrs']} (ждём [2], пул честно помечен неполным, без зависания)"


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  C19–C22 · ПЛАТА: разведчик реально разблокирует ozon_card (и честно блокирует, когда нельзя)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def t19_payoff_can_build(d):
    prod = {"offer_id": "OZ-SCOUT-1", "name": "Плёнка стрейч 0,5×200 м", "price": 1200,
            "_spec": {"Вес, г": 300, "Цвет": "Красный"}}
    sc = scout.scout_category(
        "плёнка стрейч", spec=prod["_spec"],
        tree_fn=lambda **kw: _tree_stretch(),
        attrs_fn=lambda dci, tid, **kw: _attrs_full(),
        values_fn=_values_fn_from(_values_full()),
    )
    merged = scout.apply_to_product(prod, sc)
    res = card.to_item(merged, cats={})            # cats={} → source #2 пуст: строит ТОЛЬКО скаут
    meta, item = res["meta"], res["item"]
    # enum «Красный» должен разрешиться в dictionary_value_id=101 в самой форме
    color = next((a for a in (item or {}).get("attributes", []) if a["id"] == 2), None)
    color_dvid = color["values"][0].get("dictionary_value_id") if color else None
    ok = (item is not None and meta["can_build"] is True
          and meta["category_source"] == "explicit"
          and meta["description_category_id"] == 15621048
          and meta["attrs_built"] >= 3 and "attributes" in item
          and color_dvid == 101)
    return ok, f"can_build={meta['can_build']} attrs_built={meta['attrs_built']} color_dvid={color_dvid}"


def t20_payoff_mapping_blocks(d):
    prod = {"offer_id": "OZ-SCOUT-2", "name": "Телевизор 50\"", "price": 45000, "_spec": {}}
    sc = scout.scout_category(
        "телевизор плазменный", spec=prod["_spec"],
        tree_fn=lambda **kw: _tree_stretch(),
        attrs_fn=lambda dci, tid, **kw: _attrs_full(),
        values_fn=_values_fn_from(_values_full()),
    )
    merged = scout.apply_to_product(prod, sc)      # need_mapping → без правок категории
    res = card.to_item(merged, cats={})            # cats={} → авто-категории нет → жёсткий блок
    meta = res["meta"]
    return ("description_category_id" not in merged and res["item"] is None
            and meta["can_build"] is False and meta["need_mapping"] is True
            and meta["category_source"] == "none"), \
        f"item={res['item']} can_build={meta['can_build']} source={meta['category_source']}"


def t21_oz2_no_fabrication(d):
    """Значение enum ОТСУТСТВУЕТ в живом пуле → атрибут НЕ шлём (dictionary_value_id не выдумываем).

    Пул из ДВУХ значений держит атрибут enum'ом (одно значение+req схлопнулось бы в constant —
    единственно-законное, см. C14). Ни «красный», ни «синий» не подстрока «розовый» → мягкий
    фолбэк тоже молчит → атрибут честно не уходит и висит в missing_required.
    """
    attrs = [{"id": 2, "name": "Цвет", "is_required": True, "dictionary_id": 999}]
    pool = {2: [{"id": 101, "value": "Красный"}, {"id": 102, "value": "Синий"}]}   # «Розового» нет
    prod = {"offer_id": "OZ-NOFAB", "name": "Плёнка стрейч", "price": 900,
            "_spec": {"Цвет": "Розовый"}}            # «Розовый» — вне пула
    sc = scout.scout_category(
        "плёнка стрейч", spec=prod["_spec"],
        tree_fn=lambda **kw: _tree_stretch(),
        attrs_fn=lambda dci, tid, **kw: attrs,
        values_fn=_values_fn_from(pool),
    )
    merged = scout.apply_to_product(prod, sc)
    res = card.to_item(merged, cats={})
    emitted_ids = {a["id"] for a in (res["item"] or {}).get("attributes", [])}
    return (sc["missing_required"] == [2] and 2 not in emitted_ids and res["item"] is not None), \
        f"missing={sc['missing_required']} emitted={emitted_ids} (цвет НЕ выдуман, но карточка честно неполна)"


def t22_garbage_tree_no_crash(d):
    checks = [
        scout.find_leaf(None, "плёнка") is None,
        scout.find_leaf("garbage", "плёнка") is None,
        scout.find_leaf({"result": "nope"}, "плёнка") is None,
        scout.find_leaf({"result": []}, "плёнка") is None,
    ]
    sc = scout.scout_category(
        "плёнка", spec={},
        tree_fn=lambda **kw: {"result": "garbage"},
        attrs_fn=lambda *a, **kw: [],
        values_fn=lambda *a, **kw: {"values": [], "has_next": False},
    )
    return (all(checks) and sc["need_mapping"] is True), \
        f"find_leaf-мусор={checks} scout.need_mapping={sc['need_mapping']} (без исключений)"


TESTS = [
    ("C1  leaf_inherits_dci", t1_leaf_inherits_dci),
    ("C2  leaf_skips_disabled", t2_leaf_skips_disabled),
    ("C3  leaf_ambiguous_refused", t3_leaf_ambiguous_refused),
    ("C4  leaf_weak_refused", t4_leaf_weak_refused),
    ("C5  leaf_exact_name_wins", t5_leaf_exact_name_wins),
    ("C6  leaf_type_query_filter", t6_leaf_type_query_filter),
    ("C7  profile_shapes", t7_profile_shapes),
    ("C8  constant_only_if_req", t8_constant_only_if_req),
    ("C9  values_paginate", t9_values_paginate),
    ("C10 values_truncate_flag", t10_values_truncate_flag),
    ("C11 values_anti_loop", t11_values_anti_loop),
    ("C12 complete_all_covered", t12_complete_all_covered),
    ("C13 complete_missing_enum", t13_complete_missing_enum),
    ("C14 constant_covers_no_spec", t14_constant_covers_no_spec),
    ("C15 scout_e2e_success", t15_scout_e2e_success),
    ("C16 scout_no_leaf_mapping", t16_scout_no_leaf_mapping),
    ("C17 scout_default_wiring", t17_scout_default_wiring),
    ("C18 scout_truncated_pool", t18_scout_truncated_pool),
    ("C19 payoff_can_build", t19_payoff_can_build),
    ("C20 payoff_mapping_blocks", t20_payoff_mapping_blocks),
    ("C21 oz2_no_fabrication", t21_oz2_no_fabrication),
    ("C22 garbage_tree_no_crash", t22_garbage_tree_no_crash),
]


def main():
    print("🎯 OZON CATEGORY SCOUT ПРИЁМКА · разведчик категорий (find_leaf/profile/values/scout — сухо, 0₽, без сети/ключа)")
    d = _sandbox()
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn(d)
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<28} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

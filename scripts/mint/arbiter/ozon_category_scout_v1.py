#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON CATEGORY SCOUT V1 — РАЗВЕДЧИК КАТЕГОРИЙ Ozon (READ, 0₽, RUBICON физически недостижим).

НЕДОСТАЮЩЕЕ ЗВЕНО СУХОЙ ПЛОСКОСТИ. У Ozon НЕТ авто-категории (закон OZ2): /v3/product/import ТРЕБУЕТ
description_category_id И type_id (лист дерева) + подтверждённые атрибуты/словарные значения. Сырые
читатели УЖЕ есть в ozon_hands_write_v1 (category_tree / category_attributes / attribute_values), но их
НИКТО не оркестрировал → ozon_card упирался в can_build=False, когда slug не лёг в статический
ozon_cats_v1.json. Этот орган их сводит:

    дерево  →  ЛИСТ (dci+type_id)  →  атрибуты (is_required=истина полноты)  →  словарные значения
    →  card-ready ПРОФИЛЬ в ТОЧНОЙ форме, которую ест ozon_card_v1._build_attributes.

ЧЕСТНОСТЬ (OZ2 — ничего не выдумываем):
  • Нет листа под запрос → need_mapping=True, dci=None (НЕ падаем, НЕ сочиняем категорию).
  • dictionary_value_id — ТОЛЬКО из живого /attribute/values. Нет соответствия → атрибут не шлём.
  • Обязательный словарный атрибут без значения под товар → в missing_required[] (карточка соберётся,
    но НЕПОЛНА — это истина полноты, а не «всё хорошо»).
  • truncated_attrs[] — словарный пул обрезан по max_value_pages (честно: пул прочитан не весь).
  • attr_constants наполняем ТОЛЬКО когда у обязательного словарного атрибута РОВНО ОДНО законное
    значение в пуле (выбора нет → это не выдумка, а единственно-законный ответ).

ШОВ. Три читателя ИНЪЕКТИРУЮТСЯ (tree_fn/attrs_fn/values_fn); по умолчанию берутся из
ozon_hands_write_v1 ЛЕНИВО. Значит модуль грузится и тестируется БЕЗ сети/ключей (моки), а живой путь
использует настоящие READ-вызовы. Наружу НЕ пишет — здесь НЕТ ни одного write-пути (RUBICON не касаемся).

КОНТРАКТ СЛОВАРЯ _spec. Профиль ключуется ИМЕНЕМ атрибута Ozon (как в /attribute). Значит _spec товара,
который читает ozon_card, должен ключеваться теми же именами атрибутов. Единство нормализации enum-меток
гарантируется переиспользованием ozon_card_v1._clean_text (тот же lower+ё→е, что и при чтении _spec).

ВЫХОД scout_category(): {description_category_id, type_id, _profile, need_mapping, missing_required,
required_ids, required_names, truncated_attrs, evidence} — мёржится в prod через apply_to_product() и
кормит УЖЕ существующий explicit-путь ozon_card._resolve_category. Ozon_card НЕ правим (0 риска общим).

ЗАКОН (SOCC): stdlib-only, fail-soft, честные флаги. 200≠успех — забота читателей/proof; здесь только
СБОРКА истины категории из уже прочитанного.
"""
import re


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ЛЕНИВЫЕ МОСТЫ К СОСЕДЯМ (грузятся без сети/ключей; инъекция читателей — основной шов)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _sibling(modname):
    """Импорт соседа по арбитеру. Ленивый + fail-soft: scout грузится, даже если соседа нет."""
    try:
        return __import__(modname)
    except Exception:
        try:
            import sys
            from pathlib import Path
            arb = str(Path(__file__).resolve().parent)
            if arb not in sys.path:
                sys.path.insert(0, arb)
            return __import__(modname)
        except Exception:
            return None


def _hands():
    """Модуль рук — несёт READ-читатели категорий (дефолт шва)."""
    return _sibling("ozon_hands_write_v1")


def _card():
    """Сборщик карточки — единый источник истины полноты (_build_attributes) и нормализации (_clean_text)."""
    return _sibling("ozon_card_v1")


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  НОРМАЛИЗАЦИЯ ТЕКСТА
# ══════════════════════════════════════════════════════════════════════════════════════════════

_NONWORD = re.compile(r"[^0-9a-zа-я]+")


def _norm(s):
    """Для НЕЧЁТКОГО сопоставления имён (обход дерева): lower, ё→е, пунктуация→пробел, схлопнуть."""
    if s is None:
        return ""
    t = str(s).strip().lower().replace("ё", "е")
    return _NONWORD.sub(" ", t).strip()


def _tokens(s):
    return set(w for w in _norm(s).split() if w)


def _enum_key(label):
    """Ключ словарной метки — ТОЧНО как ozon_card считает lookup из _spec: _clean_text(x).lower().ё→е.

    Через переиспользование _clean_text карточки исключаем дрейф: ключ карты значений == то, что
    карточка вычислит из значения _spec. Фолбэк (карта недоступна) — близкий эквивалент без пунктуации.
    """
    c = _card()
    if c is not None and hasattr(c, "_clean_text"):
        try:
            return c._clean_text(label).lower().replace("ё", "е")
        except Exception:
            pass
    return re.sub(r"\s+", " ", str(label if label is not None else "").strip()).lower().replace("ё", "е")


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ОБХОД ДЕРЕВА → ЛИСТ (единственный законный источник dci+type_id; OZ2: не выдумываем)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _roots(tree):
    """Нормализуем разные формы ответа /description-category/tree к списку корневых узлов."""
    if isinstance(tree, dict):
        r = tree.get("result", tree)
        if isinstance(r, list):
            return r
        if isinstance(r, dict):
            return [r]
        return []
    if isinstance(tree, list):
        return tree
    return []


def _walk_leaves(nodes, inherited_dci=None, path=()):
    """Генератор листовых ТИПОВ: узел с type_id — лист; dci наследуется от ближайшего предка.

    Узлы disabled==true пропускаем целиком (и их поддерево). Рекурсивно спускаемся в children.
    """
    for n in nodes or []:
        if not isinstance(n, dict) or n.get("disabled") is True:
            continue
        dci = n.get("description_category_id")
        if dci is None:
            dci = inherited_dci
        cat_name = n.get("category_name") or n.get("type_name") or ""
        npath = path + (cat_name,) if cat_name else path
        tid = n.get("type_id")
        if tid not in (None, 0, "", "0"):
            try:
                yield {
                    "description_category_id": (int(dci) if dci is not None else None),
                    "type_id": int(tid),
                    "type_name": n.get("type_name") or n.get("category_name") or "",
                    "path": list(npath),
                }
            except (TypeError, ValueError):
                pass
        kids = n.get("children")
        if isinstance(kids, list) and kids:
            for leaf in _walk_leaves(kids, dci, npath):
                yield leaf


# Пороги уверенности сопоставления. Ниже них — НЕ гадаем: возвращаем None → need_mapping (OZ2).
#   • MIN_COVERAGE — хотя бы столько значимых слов запроса должно совпасть с именем типа.
#   • MIN_MARGIN   — победитель должен опережать второго хотя бы на это, иначе НЕОДНОЗНАЧНО.
# Две одинаково названные ветви (один type_name под разными dci) дают margin≈0 → честный отказ,
# а не тихий выбор первой попавшейся категории (это и есть выдумка, которую закон OZ2 запрещает).
MIN_COVERAGE = 1
MIN_MARGIN = 1.0


def _score_leaf(leaf, q, nq):
    """Очки листа под запрос: перекрытие слов + бонус за точное/подстрочное имя + лёгкий вес пути."""
    lt = _tokens(leaf["type_name"])
    overlap = len(q & lt)
    score = float(overlap)
    nname = _norm(leaf["type_name"])
    if q and nname == nq:
        score += 100.0                          # точное имя типа
    elif q and (q <= lt or (nq and nq in nname)):
        score += 5.0                            # запрос целиком внутри имени типа
    for seg in leaf["path"]:
        score += 0.1 * len(q & _tokens(seg))    # лёгкий вес за совпадение в ветке категорий
    return score, overlap


def find_leaf(tree, query, type_query=None, *, min_coverage=MIN_COVERAGE, min_margin=MIN_MARGIN):
    """Уверенно-лучший лист под запрос по имени типа. Слабо/неоднозначно → None (OZ2, не гадаем).

    Лист без description_category_id не кандидат: без dci карточку физически не создать.
    ГЕЙТ УВЕРЕННОСТИ: покрытие ≥ min_coverage И отрыв от второго ≥ min_margin — иначе None.
    """
    q = _tokens(query)
    nq = _norm(query)
    tq = _tokens(type_query) if type_query else None
    scored = []
    for leaf in _walk_leaves(_roots(tree)):
        if leaf["description_category_id"] is None:
            continue
        lt = _tokens(leaf["type_name"])
        if tq and not (tq & lt):
            continue
        score, overlap = _score_leaf(leaf, q, nq)
        if score > 0:
            scored.append((score, overlap, leaf))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_overlap, best_leaf = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if best_overlap < min_coverage:
        return None                             # слишком слабое перекрытие — не уверены (OZ2)
    if (best_score - second_score) < min_margin:
        return None                             # второй вплотную — неоднозначно, не гадаем (OZ2)
    return best_leaf


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  СЛОВАРНЫЕ ЗНАЧЕНИЯ (курсорная пагинация; истина неполноты пула через max_pages)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def collect_values(dci, type_id, attribute_id, values_fn,
                   max_pages=20, language="DEFAULT", timeout=60):
    """Собрать ВСЕ значения словарного атрибута через курсор has_next → last_value_id.

    Возвращает (values, truncated): truncated=True → пул обрезан по max_pages (прочитан НЕ весь).
    Защита от зацикливания: курсор не двинулся → останов.
    """
    out, cursor, pages, truncated = [], 0, 0, False
    while pages < max_pages:
        pages += 1
        res = values_fn(dci, type_id, attribute_id,
                        last_value_id=cursor, language=language, timeout=timeout) or {}
        vals = res.get("values") or []
        out.extend(v for v in vals if isinstance(v, dict))
        if not res.get("has_next"):
            break
        ids = [v.get("id") for v in vals if isinstance(v, dict) and isinstance(v.get("id"), int)]
        nxt = max(ids) if ids else None
        if nxt is None or nxt == cursor:
            break                                # курсор не двигается → защита от вечного цикла
        cursor = nxt
    else:
        truncated = True                         # вышли по потолку страниц при живом has_next
    return out, truncated


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  СБОРКА ПРОФИЛЯ (в ТОЧНОЙ форме ozon_card._build_attributes: constants / specs / enums)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def build_profile(attributes, values_by_attr=None):
    """attributes[] (+ значения по id) → (profile, meta). НИЧЕГО не выдумываем.

    • dictionary_id==0            → attr_specs[name]={id, from:name}         (свободная форма из _spec)
    • dictionary_id>0, >1 значений → attr_enums[name]={id, values:{ключ:dvid}} (сопоставим из _spec)
    • dictionary_id>0, РОВНО 1 значение И is_required → attr_constants[name]  (единственно-законное)
    profile ключуется ИМЕНЕМ атрибута; _spec товара тоже (см. КОНТРАКТ в докстринге модуля).
    """
    values_by_attr = values_by_attr or {}
    attr_constants, attr_specs, attr_enums = {}, {}, {}
    required_ids, required_names, dict_ids = [], {}, []
    for a in (attributes or []):
        if not isinstance(a, dict):
            continue
        try:
            aid = int(a.get("id"))
        except (TypeError, ValueError):
            continue
        name = (a.get("name") or "").strip()
        if not name:
            continue
        req = bool(a.get("is_required"))
        try:
            dic = int(a.get("dictionary_id") or 0)
        except (TypeError, ValueError):
            dic = 0
        if req:
            required_ids.append(aid)
            required_names[aid] = name
        if dic > 0:
            dict_ids.append(aid)
            vmap, orig = {}, {}
            for v in (values_by_attr.get(aid) or []):
                if not isinstance(v, dict):
                    continue
                vid = v.get("id")
                key = _enum_key(v.get("value"))
                if key and vid is not None:
                    try:
                        vmap[key] = int(vid)
                        orig[key] = v.get("value")
                    except (TypeError, ValueError):
                        pass
            if req and len(vmap) == 1:
                k = next(iter(vmap))
                attr_constants[name] = {"id": aid, "dictionary_value_id": vmap[k], "value": orig[k]}
            else:
                attr_enums[name] = {"id": aid, "values": vmap}
        else:
            attr_specs[name] = {"id": aid, "from": name}
    profile = {"attr_constants": attr_constants, "attr_specs": attr_specs, "attr_enums": attr_enums}
    meta = {
        "required_ids": required_ids,
        "required_names": required_names,
        "dictionary_ids": dict_ids,
        "n_attrs": len(attr_constants) + len(attr_specs) + len(attr_enums),
    }
    return profile, meta


def assess_completeness(profile, spec, required_ids):
    """Какие ОБЯЗАТЕЛЬНЫЕ атрибуты НЕ уйдут в карточку при данном _spec.

    Единый источник истины — реальный сборщик ozon_card._build_attributes: чего он не эмитит, того нет.
    Возвращает список id обязательных-но-непокрытых, или None если оценить нельзя (карта недоступна).
    """
    if not required_ids:
        return []
    c = _card()
    if c is None or not hasattr(c, "_build_attributes"):
        return None
    try:
        emitted = {a.get("id") for a in c._build_attributes({"_spec": dict(spec or {})}, profile)}
    except Exception:
        return None
    return [rid for rid in required_ids if rid not in emitted]


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ОРКЕСТРАЦИЯ
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _need_mapping(query, type_query, reason):
    return {
        "description_category_id": None, "type_id": None, "_profile": None,
        "need_mapping": True, "missing_required": None,
        "required_ids": [], "required_names": {}, "truncated_attrs": [],
        "reason": reason, "evidence": {"query": query, "type_query": type_query},
    }


def scout_category(query, spec=None, *, type_query=None,
                   tree_fn=None, attrs_fn=None, values_fn=None,
                   language="DEFAULT", max_value_pages=20, timeout=60):
    """query (+опц. type_query, _spec товара) → card-ready бандл категории. READ-only, OZ2-честный.

    Читатели инъектируются либо берутся из ozon_hands_write_v1 (дефолт). Нет листа → need_mapping=True.
    """
    if tree_fn is None or attrs_fn is None or values_fn is None:
        h = _hands()
        if h is None:
            return _need_mapping(query, type_query,
                                 "нет читателей категорий (ozon_hands_write_v1 недоступен)")
        tree_fn = tree_fn or h.category_tree
        attrs_fn = attrs_fn or h.category_attributes
        values_fn = values_fn or h.attribute_values

    tree = tree_fn(language=language, timeout=timeout)
    leaf = find_leaf(tree, query, type_query=type_query)
    if leaf is None:
        return _need_mapping(query, type_query,
                             "нет листа дерева под запрос — категорию/тип не выдумываем (OZ2)")

    dci, tid = leaf["description_category_id"], leaf["type_id"]
    raw_attrs = attrs_fn(dci, tid, language=language, timeout=timeout)
    if isinstance(raw_attrs, list):
        attributes = raw_attrs
    elif isinstance(raw_attrs, dict):
        r = raw_attrs.get("result", [])
        attributes = r if isinstance(r, list) else []
    else:
        attributes = []

    values_by_attr, truncated_attrs = {}, []
    for a in attributes:
        if not isinstance(a, dict):
            continue
        try:
            aid = int(a.get("id"))
        except (TypeError, ValueError):
            continue
        try:
            dic = int(a.get("dictionary_id") or 0)
        except (TypeError, ValueError):
            dic = 0
        if dic > 0:
            vals, trunc = collect_values(dci, tid, aid, values_fn,
                                         max_pages=max_value_pages, language=language, timeout=timeout)
            values_by_attr[aid] = vals
            if trunc:
                truncated_attrs.append(aid)

    profile, pmeta = build_profile(attributes, values_by_attr)
    missing = assess_completeness(profile, spec, pmeta["required_ids"]) if spec is not None else None
    return {
        "description_category_id": dci,
        "type_id": tid,
        "_profile": profile,
        "need_mapping": False,
        "missing_required": missing,             # None=не оценивали; []=всё покрыто; [ids]=неполно
        "required_ids": pmeta["required_ids"],
        "required_names": pmeta["required_names"],
        "truncated_attrs": truncated_attrs,      # словарь обрезан по потолку страниц (пул неполон)
        "evidence": {
            "type_name": leaf["type_name"],
            "path": leaf["path"],
            "n_attributes": pmeta["n_attrs"],
            "n_required": len(pmeta["required_ids"]),
            "n_dictionary": len(pmeta["dictionary_ids"]),
        },
    }


def apply_to_product(prod, scouted):
    """Влить разведанную категорию в prod для explicit-пути ozon_card. Честно: нет категории → без правок.

    Ozon_card НЕ трогаем — используем УЖЕ существующий source #1 (prod[dci]+[type_id]+[_profile]).
    """
    if not isinstance(prod, dict) or not isinstance(scouted, dict):
        return prod
    if scouted.get("need_mapping") or scouted.get("description_category_id") is None:
        return dict(prod)                        # can_build=False сохранится — карточка честно заблокирована
    out = dict(prod)
    out["description_category_id"] = scouted["description_category_id"]
    out["type_id"] = scouted["type_id"]
    if isinstance(scouted.get("_profile"), dict):
        out["_profile"] = scouted["_profile"]
    return out


if __name__ == "__main__":
    # Библиотека, НЕ демон. Живая разведка требует ключей и делается вызывающим органом (сухо/по слову).
    print(__doc__)
    print("Это READ-only библиотека. Живой обход дерева = scout_category(query) с ключами в env.")
    print("Наружу НЕ пишет: write-путей здесь нет (RUBICON не касаемся).")

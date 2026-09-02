#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET CATEGORY MAP V1 — категорийный мост: имя товара → marketCategoryId (лист дерева Маркета).

ЦЕЛЬ (оператор 2026-08-06): «не гонись за 90 индексом. 80+ хватит, где то меньше пойдет.
Просто твоя задача УСПЕШНО ЗАЛИВАТЬ ТОВАРЫ, с любого сайта, так чтобы не было ошибок».
Отсюда закон органа: НИКОГДА не блокировать залив из-за категории. Не знаем лист — молчим,
и Маркет определяет категорию сам (см. ЗАКОН АВТО-КАТЕГОРИИ ниже).

ТРИ РУБЕЖА (сверху вниз, первый сработавший побеждает):
  1) ПРАВИЛА  — выверенные вручную листья под наш каталог (упаковка). Максимальная точность.
  2) ЛЕКСИКА  — общий матч по всему дереву (8774 листа) для товара С ЛЮБОГО сайта.
                Строгий порог + отрыв от второго места, иначе честный отказ.
  3) АВТО     — None. Карточка уходит БЕЗ marketCategoryId и БЕЗ parameterValues.

ЗАКОН АВТО-КАТЕГОРИИ (официальная спека, PartnerMarketCategoryId.yaml):
  «Если не передать их оба [parameterValues + marketCategoryId], будет использована информация
   из устаревших параметров params и category, а marketCategoryId будет определен автоматически.»
  → Отсутствие категории НЕ является ошибкой залива. Выдуманная категория — является.

ЖИВАЯ ПРОВЕРКА (2026-08-06, кабинет Atlas Edge): у 19 из 20 целевых листьев НОЛЬ обязательных
параметров, поэтому marketCategoryId можно слать без parameterValues — карточка не замерзает
в ERRORS. Исключение: 7812201 «Сумки» требует «Тип» → в правилах не используем (уходит в АВТО).

ЗАКОН (SOCC): stdlib-only, без сети в матче (дерево закэшировано), честный None вместо выдумки.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TREE_PATH = HERE / "ymarket_tree_v1.json"

# ─────────────────────────────────────────────────────────────────────────────
# РУБЕЖ 1 — ПРАВИЛА. Листья выверены по живому дереву + живым параметрам (2026-08-06).
# Порядок ВАЖЕН: специфичное выше общего. Первое сработавшее правило побеждает.
# "any" — сработать если встретилось любое; "not" — не срабатывать если встретилось любое.
# Ищем по ВСЕМУ имени: у части выгрузок продающий префикс стоит ПЕРЕД товаром
# («Прочная, для упаковки и маркетплейсов: Клейкая лента (скотч), 48 мм»).
# ─────────────────────────────────────────────────────────────────────────────
RULES = [
    # — почтовая/курьерская группа (раньше коробок: тубус и курьер-пакет содержат «почтовый») —
    {"id": 64151014, "leaf": "Курьерские пакеты",
     "any": ["курьер-пакет", "курьерский пакет", "курьерские пакеты", "курьер пакет"]},
    {"id": 64152426, "leaf": "Сейф-пакеты", "any": ["сейф-пакет", "сейф пакет"]},
    {"id": 64642256, "leaf": "Тубусы для чертежей", "any": ["тубус"]},
    {"id": 64150307, "leaf": "Конверты бумажные",
     "any": ["конверт"], "not": ["пузырьков"]},

    # — липкая лента —
    {"id": 90741, "leaf": "Скотч",
     "any": ["скотч", "клейкая лента", "клейкой ленты", "липкая лента"]},

    # — оборудование (раньше плёнок: «диспенсер для стрейч-плёнки» — это инструмент) —
    {"id": 75355556, "leaf": "Диспенсеры для стрейч-плёнки",
     "any": ["диспенсер"]},
    {"id": 75358682, "leaf": "Стреппинг-инструменты",
     "any": ["стреппинг", "устройство для лент", "устройство эконом для лент",
             "обвязочная машин", "упаковочные клещи", "упаковочный клещи"]},

    # — плёнки (подтверждённый рабочий лист, живой contentRating 84–87) —
    {"id": 76346336, "leaf": "Упаковочные плёнки",
     "any": ["воздушно-пузырьков", "пузырьковая плёнка", "пузырьковая пленка", "биг бабл",
             "стрейч-плёнка", "стрейч-пленка", "термоусадочная",
             "плёнка упаковочная", "упаковочная плёнка"]},

    # — картон/гофра (раньше коробок: «гофрокартон листовой» — это лист, не коробка) —
    {"id": 76280526, "leaf": "Гофролисты",
     "any": ["гофрокартон", "гофролист", "гофро-лист", "картон листовой"]},
    {"id": 76283778, "leaf": "Защитные уголки для перевозки",
     "any": ["уголок защитн", "защитные уголки", "уголки защитн", "уголок картонн"]},
    {"id": 76287030, "leaf": "Картонные втулки", "any": ["втулка", "втулки"]},

    # — наполнители —
    {"id": 76300038, "leaf": "Упаковочные наполнители",
     "any": ["наполнитель", "наполнение", "крафт-стружк", "бумажная стружк"]},

    # — мешки/пакеты —
    {"id": 6943877, "leaf": "Мешки для мусора", "any": ["мешк для мусора", "мешки для мусора",
                                                        "мешок для мусора", "для мусора"]},
    {"id": 76323239, "leaf": "Упаковочные пакеты",
     "any": ["zip lock", "зип лок", "пакет с замком", "пакеты с замком", "пакет с зам",
             "пакеты упаковочные", "упаковочные пакеты", "пакеты пвд", "пакеты псд",
             "пакет пвд", "мешок полипропиленов", "мешки полипропиленов", "крафт-мешок",
             "крафт мешок", "фасовочн"]},

    # — одноразовая упаковка еды —
    {"id": 61812546, "leaf": "Коробки и контейнеры одноразовые",
     "any": ["ланч-бокс", "ланч бокс", "контейнер одноразов", "крышка для контейнер"]},

    # — рабочие перчатки —
    {"id": 71132702, "leaf": "Перчатки профессиональные",
     "any": ["перчатки хб", "перчатки х/б", "рабочие перчатки", "перчатки рабочие",
             "перчатки с пвх", "перчатки нитрилов"]},
    {"id": 12943742, "leaf": "Перчатки (хозяйственные)",
     "any": ["перчатки полиэтиленов", "перчатки одноразов", "перчатки хозяйствен"]},

    # — прочая упаковочная мелочь (свои листья вне ветки «Упаковочные материалы») —
    {"id": 62431623, "leaf": "Шпагат крепёжный",
     "any": ["шпагат", "бечевка", "бечёвка"]},
    {"id": 62769236, "leaf": "Бумага пищевая",
     "any": ["пергамент", "подпергамент", "бумага для выпечк"]},
    {"id": 71776488, "leaf": "Дорожные знаки и ограждения",
     "any": ["аварийное ограждение", "сигнальная сетка", "сигнальная лента",
             "оградительная лента"]},

    # — КОРОБКИ (общее, последним): разводим по назначению —
    {"id": 76293534, "leaf": "Коробки для продуктов",
     "any": ["коробка", "коробки", "короб", "гофрокороб"],
     "all_any": ["для продуктов", "пищев", "кондитерск", "для торта", "для пиццы", "для еды"]},
    {"id": 76290282, "leaf": "Коробки для посылок",
     "any": ["коробка", "коробки", "короб", "гофрокороб"],
     "all_any": ["почтов", "посылок", "посылк", "для отправ", "отправлен"]},
    {"id": 76296786, "leaf": "Коробки для товаров",
     "any": ["коробка", "коробки", "короб", "гофрокороб", "самосборн"]},
]

# Листья, куда лексике ходить ЗАПРЕЩЕНО: требуют обязательных параметров, которых у нас нет,
# либо заведомо чужой домен с высоким риском ложного попадания.
LEXICAL_BLOCKLIST = frozenset({
    7812201,   # Сумки — required «Тип», без него карточка встанет в ERRORS
})

# ─────────────────────────────────────────────────────────────────────────────
# Нормализация и лёгкий стеммер (stdlib-only)
# ─────────────────────────────────────────────────────────────────────────────
_PUNCT_RE = re.compile(r"[^0-9a-zа-я]+")

# Длинные окончания раньше коротких — режем самое длинное подходящее.
_ENDINGS = ("ическими", "ическая", "ическое", "ическую", "ами", "ями", "ыми", "ими", "ого",
            "его", "ому", "ему", "ая", "яя", "ое", "ее", "ые", "ие", "ах", "ях", "ов", "ев",
            "ей", "ий", "ый", "ам", "ям", "ом", "ем", "их", "ых", "ую", "юю", "а", "я", "о",
            "е", "ы", "и", "у", "ю", "ь", "й")

# Слова-пустышки: встречаются всюду, матч по ним ничего не значит.
_STOP = frozenset({"для", "или", "под", "над", "при", "без", "из", "на", "по", "с", "в", "и",
                   "к", "от", "до", "шт", "мм", "см", "мкм", "кг", "гр", "мл", "прочие",
                   "прочий", "прочая", "прочее", "другие", "разные", "набор", "наборы"})


def normalize(s):
    """Имя → нижний регистр, ё→е, пунктуация → пробел. Основа всех сравнений."""
    if not s:
        return ""
    s = str(s).lower().replace("ё", "е")
    return _PUNCT_RE.sub(" ", s).strip()


def _stem(w):
    """Грубая основа слова: режем самое длинное русское окончание, оставляя ≥4 символов."""
    if len(w) <= 4:
        return w
    for e in _ENDINGS:
        if w.endswith(e) and len(w) - len(e) >= 4:
            return w[: -len(e)]
    return w


def tokens(s):
    """Множество основ значимых слов имени."""
    out = set()
    for w in normalize(s).split():
        if len(w) < 3 or w in _STOP or w.isdigit():
            continue
        out.add(_stem(w))
    return out


# ЗАКОН ОДНОЙ НОРМАЛИЗАЦИИ: ключи правил проходят ТУ ЖЕ normalize(), что и имя товара.
# Иначе ключ «воздушно-пузырьков» никогда не совпадёт с нормализованным «воздушно пузырьков»
# — правило молчит, товар молча уезжает в АВТО. Дефис/«ё» больше не ломают правила.
_RULES_C = [
    {**r,
     "any": [normalize(k) for k in r["any"]],
     "not": [normalize(k) for k in r.get("not", [])],
     **({"all_any": [normalize(k) for k in r["all_any"]]} if r.get("all_any") else {})}
    for r in RULES
]


# ─────────────────────────────────────────────────────────────────────────────
# Дерево категорий
# ─────────────────────────────────────────────────────────────────────────────
_TREE_CACHE = None
_INDEX_CACHE = None


def load_tree(path=None):
    """Закэшированное дерево категорий. fail-soft → None (тогда лексика просто отключается)."""
    global _TREE_CACHE
    if _TREE_CACHE is None:
        p = Path(path) if path else TREE_PATH
        try:
            _TREE_CACHE = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _TREE_CACHE = False
    return _TREE_CACHE or None


def leaves(path=None):
    """Все ЛИСТЬЯ дерева: [(id, name, path)]. Только лист годится для marketCategoryId."""
    tree = load_tree(path)
    if not tree:
        return []
    out = []

    def walk(node, trail):
        kids = node.get("children") or []
        trail2 = trail + [node.get("name") or ""]
        if not kids:
            out.append((node.get("id"), node.get("name") or "", " / ".join(trail2[1:])))
        for k in kids:
            walk(k, trail2)

    walk(tree, [])
    return out


def refresh_tree(path=None):
    """Перекачать дерево с живого API и переписать кэш. Единственное место с сетью."""
    from ymarket_hands_v1 import categories_tree
    data = categories_tree()
    tree = data.get("result") if isinstance(data, dict) and "result" in data else data
    p = Path(path) if path else TREE_PATH
    p.write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
    global _TREE_CACHE, _INDEX_CACHE
    _TREE_CACHE = None
    _INDEX_CACHE = None
    return len(leaves(path))


def _index(path=None):
    """Обратный индекс основ по листьям + IDF. Строится один раз."""
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE
    ls = leaves(path)
    docs, df = [], {}
    for cid, name, full in ls:
        tk = tokens(name)
        if not tk or cid is None:
            continue
        docs.append((cid, name, full, tk))
        for t in tk:
            df[t] = df.get(t, 0) + 1
    n = max(len(docs), 1)
    # IDF без log(): доля документов. Редкое слово → вес ~1, всеобщее → вес ~0.
    idf = {t: 1.0 - (c / n) for t, c in df.items()}
    posting = {}
    for i, (_, _, _, tk) in enumerate(docs):
        for t in tk:
            posting.setdefault(t, []).append(i)
    _INDEX_CACHE = {"docs": docs, "idf": idf, "posting": posting}
    return _INDEX_CACHE


# ─────────────────────────────────────────────────────────────────────────────
# Матч
# ─────────────────────────────────────────────────────────────────────────────
MIN_COVERAGE = 0.80   # какую долю веса имени листа обязано покрыть имя товара
MIN_MARGIN = 0.10     # насколько победитель обязан оторваться от второго места
MIN_RARE_IDF = 0.995  # хоть одно совпавшее слово должно быть редким (не «для»/«набор»)


def match_rules(name):
    """РУБЕЖ 1: выверенные правила. → (id, leaf) или (None, None)."""
    n = normalize(name)
    if not n:
        return None, None
    for r in _RULES_C:
        if not any(k in n for k in r["any"]):
            continue
        if any(k in n for k in r.get("not", [])):
            continue
        extra = r.get("all_any")
        if extra and not any(k in n for k in extra):
            continue
        return r["id"], r["leaf"]
    return None, None


def match_lexical(name, path=None):
    """РУБЕЖ 2: общий матч по всему дереву — для товара с ЛЮБОГО сайта.

    Считаем, какую долю ВЕСА имени листа покрывает имя товара. Требуем высокое покрытие,
    редкое слово в совпадении и отрыв от второго места — иначе честный None.
    """
    idx = _index(path)
    if not idx["docs"]:
        return None, None, 0.0
    tk = tokens(name)
    if not tk:
        return None, None, 0.0
    idf = idx["idf"]

    cand = set()
    for t in tk:
        for i in idx["posting"].get(t, []):
            cand.add(i)
    if not cand:
        return None, None, 0.0

    scored = []
    for i in cand:
        cid, leaf, full, ltk = idx["docs"][i]
        if cid in LEXICAL_BLOCKLIST:
            continue
        total = sum(idf.get(t, 1.0) for t in ltk)
        if total <= 0:
            continue
        hit = ltk & tk
        if not hit:
            continue
        if max(idf.get(t, 1.0) for t in hit) < MIN_RARE_IDF:
            continue  # совпало только по всеобщим словам — это не сигнал
        cov = sum(idf.get(t, 1.0) for t in hit) / total
        # длинное имя листа при равном покрытии точнее короткого
        scored.append((cov + 0.001 * len(ltk), cov, cid, leaf, full))
    if not scored:
        return None, None, 0.0

    scored.sort(reverse=True)
    best = scored[0]
    if best[1] < MIN_COVERAGE:
        return None, None, best[1]
    if len(scored) > 1 and (best[0] - scored[1][0]) < MIN_MARGIN:
        return None, None, best[1]  # двусмысленно — не гадаем
    return best[2], best[3], best[1]


def match(name, path=None):
    """Имя товара → категория. Всегда возвращает решение, никогда не бросает.

    {'category_id': int|None, 'leaf': str|None, 'source': 'rule'|'lexical'|'auto', 'score': float}
    source='auto' → лить БЕЗ marketCategoryId и БЕЗ parameterValues (Маркет определит сам).
    """
    cid, leaf = match_rules(name)
    if cid:
        return {"category_id": cid, "leaf": leaf, "source": "rule", "score": 1.0}
    cid, leaf, score = match_lexical(name, path)
    if cid:
        return {"category_id": cid, "leaf": leaf, "source": "lexical", "score": round(score, 3)}
    return {"category_id": None, "leaf": None, "source": "auto", "score": round(score, 3)}


def stats():
    """Сводка органа: сколько листьев знаем, сколько правил, покрытие правил."""
    ls = leaves()
    return {"листьев в дереве": len(ls), "правил": len(RULES),
            "листьев в правилах": len({r["id"] for r in RULES}),
            "дерево": str(TREE_PATH), "есть дерево": bool(ls)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Категорийный мост: имя товара → marketCategoryId")
    ap.add_argument("--refresh", action="store_true", help="перекачать дерево с живого API")
    ap.add_argument("--stats", action="store_true", help="сводка органа")
    ap.add_argument("--test", nargs="*", help="проверить имена товаров")
    a = ap.parse_args()

    if a.refresh:
        print(f"дерево обновлено: {refresh_tree()} листьев")
    if a.stats:
        for k, v in stats().items():
            print(f"  {k}: {v}")
    if a.test:
        for nm in a.test:
            r = match(nm)
            print(f"  {nm[:70]}\n    → {r['category_id']} «{r['leaf']}» [{r['source']}] {r['score']}")
    if not (a.refresh or a.stats or a.test):
        for k, v in stats().items():
            print(f"  {k}: {v}")
        sys.exit(0)

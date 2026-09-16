#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORGAN PHOTO-INSIGHT V1 — «что продавцы выносят в название» (0₽, WB, честно). Линия #7 ин-фографики.

ЗАЧЕМ. Инфографика решает, КАКИЕ преимущества рисовать на нашем 2-м кадре. Вместо вкуса — данные:
сканируем топ-выдачу WB по нашему товару (короб/плёнка/запрос) и собираем частотность семейств
заявок (слои, марка Т, усиленный, премиум, плотность, толщина, пузырёк, влаго…). Что продавцы
массово пишут в название — их коллективное решение о приоритете для покупателя. Это ВХОД для
контент-приоритета, а не истина в последней инстанции.

ГРАНИЦА ЧЕСТНОСТИ (закон органа, три пункта):
  1) Мы читаем ЗАГОЛОВКИ (публичный текст карточки) — НЕ пиксели картинок: наша модель текстовая,
     изображения не видит. «Что нарисовано на чужом кадре» честно помечаем НЕИЗВЕСТНЫМ.
  2) Частотность = прокси интереса по числу ОТЗЫВОВ/позиции (как wb_scout._demand_signal), а не
     заявленный объём продаж. kind помечается wb_title_proxy.
  3) НА КАДРЕ рисуем ТОЛЬКО факты, которые РЕАЛЬНО есть в наших `facts` (закон compose_infographic).
     insight лишь ПОДСКАЗЫВАЕТ приоритет извне: claim семейство попадает в кандидаты только если
     наше описание его подтверждает (honest_gate). Ничего не выдумываем.

Архитектура: mine(products) — ЧИСТАЯ логика (офлайн-тесты, 0 сети); scan(query/category) — тонкая
обёртка над wb_scout.scan_category (ленивый импорт). Ruby: 0₽, 0 токенов на кадр, stdlib-only.

CLI:
  python3 photo_insight_v1.py --query "короб гофрокартон 5 слойный" --top 8
  python3 photo_insight_v1.py --category 9101 --city msk --limit 40
"""
import re
import json
import argparse
from datetime import datetime, timezone

# ── ЛЕКСИКОН СЕМЕЙСТВ ЗАЯВОК ─────────────────────────────────────────────────────────
# Каждое семейство = кандидат «что можно вынести в кадр». Триггеры — регулярки по НИЖНЕМУ
# регистру заголовка. Держим узко: только осмысленные для наших категорий преимущества.
FAMILIES = [
    # (канон, подпись-для-отчёта, паттерны)
    ("layers",    "Слои гофры (N-слойный)",            [r"(?:\d+|[а-я]+)\s*[-–—]?\s*слойн", r"(?:\d+)\s*(?:слоёв|слоев|сло[яй])"]),
    ("tmark",     "Марка картона Т-…",                [r"\bт\s*[-–—]?\s*\d{2}\b"]),
    ("armor",     "Усиленный / армированный / прочный",[r"(?:армир|усиленн|прочн|крепк|высокопрочн)"]),
    ("premium",   "Премиум / люкс / экстра",           [r"(?:премиум|premium|люкс|lux|элит|vip|экстра|extra|топ)"]),
    ("density",   "Плотность г/м²",                    [r"\d{2,4}\s*(?:г\s*/\s*м2|г/м2|грамм|гр)"]),
    ("thickness", "Толщина (мкм/мм)",                  [r"\d{1,3}(?:[.,]\d+)?\s*(?:мкм|микрон|мм)"]),
    ("bubble",    "Пузырёк / ВПП",                     [r"(?:пузырьк|пузырч|bubble|воздушно-пузыр)"]),
    ("format",    "Ширина / формат рулона",            [r"(?:ширин|шириной|погонн|формат|рулон\b)"]),
    ("water",     "Влагозащита / водостойкость",       [r"(?:влаго|влагопрочн|водоотталкива|непромока|влагозащит)"]),
    ("food",      "Пищевой контакт",                   [r"(?:пищев|для пищевых|контакт\s*с\s*пищ|хранени[ея]\s*продукт)"]),
    ("eco",       "Эко / вторсырьё",                   [r"(?:эко|вторсырь|переработ|биоразлаг|экологичн)"]),
    ("heat",      "Тепло / термо",                     [r"(?:термо|тепло|утеплител|энергосберег)"]),
    ("shock",     "Ударопрочность / защита",           [r"(?:ударопрочн|ударопоглощ|амортиз|защита\s+(?:от\s+)?удар|защит\s+при\s+перевозк)"]),
]

FAMILY_BY_KEY = {k: (label, pats) for k, label, pats in FAMILIES}

# Слова-маркеры категории (в лоб, зеркалят detect_category из photo_infographic_v1, но не импортим
# аудируемый модуль извне тестов — чтобы орган жил автономно).
def _category_hint(name):
    s = name.lower()
    if any(w in s for w in ("плёнк", "пленк", "пузырч", "bubble", "стретч", "термоусадоч", "рулон")):
        return "film"
    if any(w in s for w in ("короб", "гофр", "ящик", "коробк", "картонн")):
        return "box"
    return None


def _weight(feedbacks, position):
    """Вес заявки: отзывы (прокси накопленных покупок) + бонус топ-позиции. 1.0 минимум."""
    f = max(0, int(feedbacks or 0))
    return round(1.0 + min(2.5, (f ** 0.5) / 6.0) + (0.5 if 1 <= position <= 10 else 0.0), 3)


def _thickness_hit(s):
    """Толщина МАТЕРИАЛА, а не габарит коробки. Габарит пишут «ШхДхВ мм» — под него НЕ ведёмся.
    Честно: толщина = мкм/микрон, ИЛИ явное «толщин… N мм», ИЛИ «картон/гофр N мм»."""
    if re.search(r"\d+(?:[.,]\d+)?\s*(?:мкм|микрон)", s):
        return True
    if re.search(r"толщин\w*\s*[а-яё ]{0,4}\d+(?:[.,]\d+)?\s*мм", s):
        return True
    if re.search(r"(?:картон|гофрокартон)\w*(?:\s+[а-яё]{1,14}){0,2}\s*\d{1,2}(?:[.,]\d+)?\s*мм", s):
        return True
    return False


def _match_families(name):
    """Множество канонов семейств, найденных в одном названии (дедуп внутри названия)."""
    s = name.lower()
    out = set()
    for key, _label, pats in FAMILIES:
        if key == "thickness":  # особый случай: не путать с габаритами коробки
            if _thickness_hit(s):
                out.add(key)
            continue
        for p in pats:
            if re.search(p, s):
                out.add(key)
                break
    return out


def mine(products, limit=None):
    """ЧИСТАЯ логика: сырые товары WB → частотность семейств заявок, взвешенная спрос-прокси.

    products — список WB-товаров (поля name/brand/feedbacks/id). Вернёт dict отчёта:
      families:  [{key,label,count,weighted,titles:[до 3 примеров],category_hints:{box:n,film:n}}]
      meta:      {scanned, kind:'wb_title_proxy', honesty, captured_at}
    Не делает НИ ОДНОГО сетевого вызова. Заявки не проверяются нашими фактами — это вне органа,
    на кадр ляжет только подтверждённое (honest_gate делает вызывающая сторона по нашим `facts`).
    """
    prods = list(products or [])[: limit or len(products or [])]
    acc = {key: {"count": 0, "weighted": 0.0, "titles": [], "cat": {"box": 0, "film": 0, None: 0}}
           for key, _l, _p in FAMILIES}
    for pos, prod in enumerate(prods, start=1):
        name = (prod.get("name") or "").strip()
        if not name:
            continue
        fb = prod.get("feedbacks") or prod.get("nmFeedbacks") or 0
        w = _weight(fb, pos)
        cat = _category_hint(name)
        for key in _match_families(name):
            row = acc[key]
            row["count"] += 1
            row["weighted"] = round(row["weighted"] + w, 3)
            row["cat"][cat] += 1
            if len(row["titles"]) < 3:
                row["titles"].append((name[:78] + ("…" if len(name) > 78 else ""), fb))
    families = []
    for key, _label, _p in FAMILIES:
        row = acc[key]
        if row["count"] == 0:
            continue
        families.append({
            "key": key,
            "label": _label,
            "count": row["count"],
            "weighted": row["weighted"],
            "example_titles": [t for t, _f in row["titles"]],
            "category_hints": row["cat"],
        })
    families.sort(key=lambda f: (f["weighted"], f["count"]), reverse=True)
    return {
        "families": families,
        "meta": {
            "scanned": len(prods),
            "kind": "wb_title_proxy",
            "note": ("частотность преимуществ из ЗАГОЛОВКОВ топ-выдачи WB, взвешена отзывами/позицией; "
                     "пиксели чужих картинок модель НЕ читает — что нарисовано на кадре, честно неизвестно"),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def honest_gate(insight, facts, top=None):
    """Заявки из insight, которые НАШИ `facts` реально подтверждают (→ кандидаты на кадр).

    Возвращает список {key,label,evidence} только тех семейств, где в facts есть подтверждающее
    значение по той же ОСИ. Заявка без подтверждения НЕ проходит — на кадр ничего не выдумываем.
    Сейчас замыкает на ключи, которые умеет рисовать photo_infographic_v1:
      layers  ← слои_картона/материал с «-слой»;  tmark ← материал/марка Т-N;
      armor   ← вид/материал: усиленн/армир;      premium ← премиум-лексемы;
      density ← плотность_г_м2;  thickness ← толщина_мм;  bubble ← пузырёк/вид плёнка-пузырёк;
      format  ← ширина_м/см;     water/food/eco/heat/shock ← в виде/материале/описании фактом.
    """
    bl = " ".join(str(v) for v in (facts or {}).values() if isinstance(v, str)).lower()
    keys = (insight or {}).get("families", []) if isinstance(insight, dict) and isinstance(insight.get("families"), list) else (insight or [])
    passed = []
    for fam in keys:
        key = fam if isinstance(fam, str) else fam.get("key")
        if key == "layers" and re.search(r"(?:\d+|[а-я]+)-?слойн", bl):
            passed.append(key)
        elif key == "tmark" and re.search(r"\bт\s*-?\s*\d{2}\b", bl):
            passed.append(key)
        elif key == "armor" and re.search(r"(?:армир|усиленн)", bl):
            passed.append(key)
        elif key == "premium" and re.search(r"(?:премиум|premium|люкс|vip|экстра|extra)", bl):
            passed.append(key)
        elif key == "density" and (facts or {}).get("плотность_г_м2"):
            passed.append(key)
        elif key == "thickness" and (facts or {}).get("толщина_мм"):
            passed.append(key)
        elif key == "bubble" and re.search(r"(?:пузырьк|пузырч|bubble|воздушно-пузыр)", bl):
            passed.append(key)
        elif key == "format" and any((facts or {}).get(k) for k in ("ширина_м", "ширина_см", "ширина")):
            passed.append(key)
        elif key in ("water", "food", "eco", "heat", "shock") and re.search(_FAMILY_EXTRA_WORDS[key], bl):
            passed.append(key)
    return passed[: top or len(passed)]


_FAMILY_EXTRA_WORDS = {
    "water": r"(?:влаго|влагопрочн|водоотталкива|непромока)",
    "food": r"(?:пищев|для пищевых|контакт\s*с\s*пищ)",
    "eco": r"(?:эко|вторсырь|переработ|биоразлаг)",
    "heat": r"(?:термо|тепло|утеплител)",
    "shock": r"(?:ударопрочн|ударопоглощ|амортиз|защита\s+при\s+перевозк)",
}


def scan(query=None, category=None, city="msk", limit=40):
    """Живой 0₽ проход: wb_scout.scan_category → mine(). fail-soft: сеть упала → пустой отчёт."""
    try:
        import wb_scout_v1 as wb
    except Exception:
        return {"families": [], "meta": {"scanned": 0, "kind": "wb_title_proxy", "error": "wb_scout недоступен",
                                         "captured_at": datetime.now(timezone.utc).isoformat()}}
    prods = wb.scan_category(category=category, query=query, city=city, limit=limit)
    rep = mine(prods)
    rep["meta"].update({"source_query": query, "source_category": category, "market": "wildberries"})
    return rep


def _fmt(rep, top):
    print(f"📡 WB-ИНСАЙТ · 0₽ · товаров просканировано: {rep['meta'].get('scanned')}")
    print(f"   {rep['meta'].get('note','')}")
    for i, f in enumerate(rep.get("families", [])[: top or 10], start=1):
        print(f"  {i:>2}. {f['label']:<26} встреч={f['count']:<3} вес={f['weighted']:<6} "
              f"box/film/gen={f['category_hints'].get('box',0)}/{f['category_hints'].get('film',0)}/{f['category_hints'].get(None,0)}")
        for t in f.get("example_titles", [])[:2]:
            print(f"        ↳ {t}")


def _main(argv=None):
    ap = argparse.ArgumentParser(description="WB-инсайт: что продавцы выносят в название (0₽)")
    ap.add_argument("--query", help="текстовый запрос WB")
    ap.add_argument("--category", help="id категории WB (catalog)")
    ap.add_argument("--city", default="msk")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json", action="store_true", help="вывести json")
    a = ap.parse_args(argv)
    if not a.query and not a.category:
        ap.error("нужен --query ИЛИ --category")
    rep = scan(query=a.query, category=a.category, city=a.city, limit=a.limit)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        _fmt(rep, a.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

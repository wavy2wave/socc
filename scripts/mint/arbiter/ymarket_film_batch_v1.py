#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПЛЁНОЧНАЯ ПАРТИЯ → ВСЕ РУЛОНЫ ДОНОРА (ymarket_film_batch_v1) — СУХОЙ прогон расширения.

ЧТО ЭТО. Плёночный орган 4 живых карточек (ymarket_film_cards_v1, TARGET_PIDS) доказан живьём
2026-09-02. Оператор выбрал охват «Рулоны плёнки (35)» — расширить живой путь на ВЕСЬ ассортимент
рулонов ВПП донора. Честный живой скан категории vozdushno-puzyrkovaya-plenka (07-08.09) даёт
39 метражных рулонов (35 гладких + 4 с перфорацией); 4 уже живы → НОВЫХ 35. Пакеты/листы ВПП —
НЕ рулоны, в эту партию не входят.

КАК БЕЗ ВЫДУМКИ. Для новых pids в FILM_FACTS (ручная запись на 4) записей нет. Но карточка дона
сама отдаёт полный реальный блок характеристик (Намотка/Диаметр пузырька/Кол-во слоёв/Ширина
рулона/Вес кг/Общая толщина/Плотность г/м²/Площадь/Цвет) + «Размер упаковки»/«Транспортный объём»
для габаритов посылки (OVH-слой это уже читает). Этот модуль: скан → карточка (1 GET, 0₽) →
РЕАЛЬНЫЕ факты (фолбэк к FILM_FACTS) → те же собранные функции build_product/publish_card
фильм-органа → сухой манифест. В источник 4 карточек НЕ пишем: F.FILM_FACTS расширяется только
в памяти этого прогона (обратимо, обратносовместимо).

ФОТО. Каждая карточка дона несёт публичное главное фото og:image
(https://shop.cargo-avto.ru/upload/cache/resized/watermark/{артикул}__*.webp) — для новых рулонов
берём его (выбор оператора «фото из донора»). Провенанс: это производная от донора → при живом
заливе нужен разрешающий провенанс-гейт (derivative + allow_derivative), тут — только показ URL.

RUBICON: скрипт сам НИЧЕГО не пишет. --commit НЕ предусмотрен: это read/dry-манифест. Живой залив
— тем же движком ЦИКЛ-1 по слову оператора после снятия вердикта модерации и вердикта ЦЕНОВИКа.
"""
import json
import math
import pathlib
import re
import sys

ARB = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ARB))

import ymarket_film_cards_v1 as F          # собранный плёночный орган (реюзаем, НЕ редактируем)
import ymarket_ovh_dims_v1 as OVH
import ymarket_write_v1 as W
import donor_stock_v1 as STOCK             # живое наличие у донора (та же карточка, 0₽)
from suppliers.cargo_avto_v1 import CargoAvtoAdapter

DONOR_SLUG = F.DONOR_SLUG                    # "vozdushno-puzyrkovaya-plenka"
LIVE_PIDS = set(F.TARGET_PIDS)               # 4 живые карточки (в партию НЕ входят, не перезаписываем)
# Рулоны, чей ФИЗ-БЛИЗНЕЦ уже жив на витрине под ЛЕГАСИ-карточкой (offerId = артикул дона cargo):
#  pid 15557  = живой 9603273-1 · pid 295082 = живой 9604816-1 (twin-гард #38, сухой ЦИКЛ 2026-09-08,
#  n_plan=35 → поймал 2). Создание ARB-второго экземпляра того же рулона ЗАПРЕЩЕНО законом → исключаем
#  как уже-на-витрине (не «новые»). Если легаси-карточки когда-то будут сняты — удалить 2 строки, и
#  донор-рулоны вернутся в партию сами (обратимо, это ДАННЫЕ, не логика).
LEGACY_LIVE_PIDS = {"15557", "295082"}

# Рулон ВПП: «N * W м» (метраж × ширина в метрах). Пакеты/листы — «N * N см» и/или «шт» — НЕ рулон.
_ROLL_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[*хx×]\s*(\d+(?:[.,]\d+)?)\s*м\b")
_NON_ROLL = ("пакет", "лист", "упаковк", "рулончик", "штук")
_OG_RE = re.compile(r'property="og:image"\s+content="([^"]+)"')


def classify_roll(name):
    """Имя товара донора → (намотка_м, ширина_м) если это МЕТРАЖНЫЙ РУЛОН, иначе None.

    Честные рамки: ширина рулона 0.3–1.6 м (у донора так), намотка 1–300 м, намотка > ширина
    (иначе это лист/пакет, а не рулон). Вне рамок → не рулон (не выдумываем охват).
    """
    if not name or any(x in name.lower() for x in _NON_ROLL):
        return None
    m = _ROLL_RE.search(name.lower())
    if not m:
        return None
    try:
        l = float(m.group(1).replace(",", "."))
        w = float(m.group(2).replace(",", "."))
    except ValueError:
        return None
    if not (0.3 <= w <= 1.6 and 1 <= l <= 300 and w < l):
        return None
    return round(l, 3), round(w, 3)


def _prop(props, *needles):
    """Первое свойство карточки, в имени которого есть любая игла (нижний регистр) → (name,value)."""
    for n, v in (props or {}).items():
        ln = n.lower()
        if any(x in ln for x in needles):
            return n, v
    return None, None


def facts_from_props(props, name):
    """Блок характеристик карточки дона → факты в СХЕМЕ FILM_FACTS (для _build_spec/_build_description).

    Каждая цифра — с карточки (провенанс 'донор:карточка'), НЕ выдумана. Описание орган-фильма
    читает часть ключей БЕЗУСЛОВНО (пузырёк_мм/толщина_мм/вес_кг) → факт с их отсутствием НЕ создаём
    (иначе KeyError в _build_description валил бы всю партию, а не честно пропускал рулон).
    Нет полного набора → None (рулон в skipped_facts, в built НЕ уходит — «полная карточка или пропуск»).
    """
    if not props:
        return None
    spec = OVH.spec_from_card(props)         # ширина_м/длина_м/плотность/слои/толщина/площадь/вес/…
    need = ("ширина_м", "длина_м", "плотность_г_м2", "слои",
            "диаметр_пузырька_мм", "толщина_мм", "вес_кг")   # всё, что читает _build_description
    if not all(spec.get(k) for k in need):
        return None
    w = spec["ширина_м"]; l = spec["длина_м"]
    слой = int(spec["слои"])
    area = spec.get("площадь_м2") or round(w * l, 2)
    # цвет: «Цвет» карточки (у дона муж. род: «Черный»/«Прозрачный») → если не пришёл: имя товара
    # («…Black bubble») → прозрачный. Нормализуем к МУЖ. прилагательному: _ген умеет «ый/ий/ой»,
    # «чёрная» (ж.р., если донор напишет так) сломало бы согласование «из … полиэтилена».
    _, cval = _prop(props, "цвет")
    color = (cval or "").strip().lower()
    if not color:
        color = "чёрный" if "чёрн" in (name or "").lower() else "прозрачный"
    elif color.endswith("яя"):      # «синяя»→«синий», «светло-…» держит суффикс
        color = color[:-2] + "ий"
    elif color.endswith("ая"):      # «чёрная»→«чёрный», «прозрачная»→«прозрачный»
        color = color[:-2] + "ый"
    материал = "полиэтилен"
    _, mat = _prop(props, "материал")
    if mat:
        материал = mat.strip().lower()
    # перфорация: сплошная vs перфорированная того же размера/плотности = РАЗНЫЙ товар (Black/…).
    # Донор пишет в имени («с перфорацией»/Perforated); параметра в карточке обычно нет.
    перфорация = "да" if re.search(r"перфор|perfor", (name or "").lower()) else "нет"
    плотн = spec["плотность_г_м2"]
    пузырь = spec["диаметр_пузырька_мм"]
    толщина = spec["толщина_мм"]
    вес = spec["вес_кг"]
    f = {
        "ширина_м": w, "длина_м": l, "площадь_м2": round(area, 3),
        "слои": слой, "пузырёк_мм": round(float(пузырь), 1),
        "плотность_г_м2": плотн, "толщина_мм": round(float(толщина), 4),
        "вес_кг": round(float(вес), 4),
        "цвет": color, "материал": материал, "страна": "Россия",
        "перфорация": перфорация,
    }
    # НАШЕ описание строится из РЕАЛЬНЫХ чисел (герой-абзац/спеки) + честные общие строки применения.
    # «особость» — финальная фраза герой-абзаца: толщина и вес (в абзаце-1 их ещё НЕ было, чтобы не
    # дублировать). БЕЗ служебной меты «данные поставщика/не оценка» — это внутрянка (докстринг/манифест),
    # а не копирайт для публичной витрины (светить донора и оправдываться в описании нельзя).
    f["применение"] = [
        "защита хрупких и бьющихся предметов при переезде и на складе",
        "упаковка товаров и посылок перед отправкой транспортными компаниями и маркетплейсами",
        "прокладка и заполнение пустот в коробках при хранении и транспортировке",
    ]
    f["особость"] = (f"общая толщина полотна {F._fmt_ru(f['толщина_мм'])} мм, "
                     f"вес рулона {F._fmt_ru(f['вес_кг'])} кг — полотно плотно прилегает и "
                     "не оставляет пустот при упаковке")
    return f


def load_rolls(limit=400):
    """Живой скан категории → метражные рулоны (main-сетка), новые (не живые) первыми.

    Возвращает (all_rolls, new_rows): all_rolls — все рулоны для манифеста, new_rows — те, что
    строим (без LIVE_PIDS). Порядок стабилен по pid.
    """
    rows = CargoAvtoAdapter().scan(category=DONOR_SLUG, limit=limit)
    rolls = []
    for p in rows:
        if p.get("grid") != "main":
            continue
        cls = classify_roll(p.get("name") or "")
        if cls:
            p["_roll"] = cls
            rolls.append(p)
    rolls.sort(key=lambda p: p.get("sku") or "")
    new_rows = [p for p in rolls if str(p.get("sku")) not in LIVE_PIDS
                and str(p.get("sku")) not in LEGACY_LIVE_PIDS]
    return rolls, new_rows


def manifest_markup():
    """markup манифеста atlas-express-film (8.0) → число. Нет/бито → модульный MARKUP (обратносовместимо)."""
    try:
        stores = json.loads((ARB / "runtime/cycle1/stores.json").read_text(encoding="utf-8"))
        ent = stores.get("atlas-express-film")
        if isinstance(ent, dict) and ent.get("markup") is not None:
            return ent["markup"]
    except Exception:
        pass
    return F.MARKUP


def assemble_new_rows(limit=400):
    """Живой скан → ВСЕ новые метражные рулоны (кроме LIVE_PIDS), каждый уже обогащён:

      _facts — карточка дона дала ПОЛНЫЙ блок характеристик (факты легли в F.FILM_FACTS[pid]);
      _stock — наличие у донора СЕЙЧАС (маркер «Интернет-магазин:», тот же html, 0₽);
      _og    — публичное главное фото дона (og:image), если карточка его отдала;
      ОВХ-габариты посылки — тот же OVH-слой, что у живых 4.

    Read-only (0₽ GET). Возвращает (rows, og_pub): rows — строки для сборки build_product
    (ФАКТЫ и для бесфактовых: их догонит план-аудит СБОРКИ честным INCOMPLETE, а не тихим
    пропуском); og_pub — pid → [og:image URL] (фото-слой для новых). Живой залив решает
    движок ЦИКЛ-1 (по слову оператора), этот модуль сам ничего не пишет.
    """
    _, new_rows = load_rolls(limit=limit)
    rows, og_pub = [], {}
    for p in new_rows:
        pid = str(p.get("sku"))
        url = p.get("url") or ""
        html = OVH.fetch_card(url) if url else ""
        props = OVH.parse_card_properties(html)
        og = _OG_RE.search(html or "")
        if og:
            og_pub[pid] = [og.group(1)]
            p["_og"] = og.group(1)          # кладём и на строку: движок мёржит фото без 2-го прохода
        facts = facts_from_props(props, p.get("name"))
        # габариты посылки/вес — тот же OVH-слой, что и у живых 4 (честно, из карточки).
        OVH.enrich(p, props)
        # НАЛИЧИЕ У ДОНОРА СЕЙЧАС — маркер «Интернет-магазин:» в ТОМ ЖЕ html (лишнего GET нет).
        # in_stock = можно грузить (закон СКЛАДОВЩИКА: под заказ/неизвестно на Экспресс НЕ родит).
        p["_stock"] = STOCK.parse_stock(html)["status"]
        p["_facts"] = bool(facts)
        if facts:
            # Расширяем FILM_FACTS ТОЛЬКО в памяти процесса: новые pids — реальные факты с их
            # карточек (build_product живых 4 читает FILM_FACTS.get(pid) → те же спеки/описание).
            F.FILM_FACTS[pid] = facts
        rows.append(p)
    return rows, og_pub


def run():
    """Полный сухой манифест: скан → карточки новых рулонов → факты/фото → build → publish(dry)."""
    markup = manifest_markup()
    all_rolls, _new_rows = load_rolls()
    rows, pub = assemble_new_rows()

    built_facts, skipped, ready = {}, [], []
    for p in rows:
        pid = str(p.get("sku"))
        if p.get("_facts"):
            built_facts[pid] = F.FILM_FACTS.get(pid)
            ready.append(p)                      # полная карточка → в сборку
        else:
            skipped.append({"pid": pid, "article": p.get("article"), "name": (p.get("name") or "")[:60],
                            "reason": "карточка дона не дала полных характеристик"})

    # сборка — ровно та же build_product живых 4 (имя 1-в-1, свой EAN, vendor ATLAS EDGE, markup).
    # ТОЛЬКО для строк с ПОЛНЫМИ фактами: рулон без фактов = карточка без _spec/описания → в built
    # НЕ уходит (в skipped_facts уже помечен) — «полная карточка или честный пропуск», не полу-карточка.
    # Каждому built пришиваем _stock: состояние у донора НА МОМЕНТ чтения (для матрицы наличия).
    built = []
    for i, p in enumerate(ready):
        pr = F.build_product(p, pub, i, markup=markup)
        if pr:
            pr["_stock"] = p.get("_stock")
            built.append(pr)

    out = []
    for pr in built:
        r = W.publish_card(pr, slug=F.SLUG, dry=True, commit=False, photo_urls=pr["pictures"])
        out.append({"pid": pr["pid"], "sku": pr["sku"], "ok": r.get("ok"),
                    "stock": pr.get("_stock"),
                    "price": pr["price"], "cost": pr["cost"],
                    "dims": pr.get("weightDimensions"), "photos": len(pr["pictures"]),
                    "name": pr["name"][:58],
                    "errors": (r.get("errors") or r.get("error") or None),
                    "need_mapping": r.get("need_mapping"), "category_id": r.get("category_id")})
    return {"markup": markup, "total_rolls": len(all_rolls), "live": sorted(LIVE_PIDS),
            "new_total": len(rows), "built": out, "built_facts": len(built_facts),
            "skipped_facts": skipped}


def render(res):
    L = [f"🎞️  ПЛЁНОЧНАЯ ПАРТИЯ ВПП · ВСЕ РУЛОНЫ ДОНА · DRY (0₽, наружу НИЧЕГО)",
         f"    рулонов в категории: {res['total_rolls']} · живых 4: {sorted(res['live'])} · "
         f"НОВЫХ к сборке: {res['new_total']}",
         f"    цена = закупка ×{res['markup']:g} · факты с карточек у {res['built_facts']} из "
         f"{res['new_total']} · фото og:image дона", ""]
    ok_all = True
    for r in res["built"]:
        tag = "🟢" if r["ok"] else "🔴"
        ok_all = ok_all and bool(r["ok"])
        st = {"in_stock": "🏪 В НАЛИЧИИ у донора", "on_order": "⏳ под заказ у донора",
              None: "❓ наличие неизвестно"}.get(r["stock"])
        L.append(f"{tag} {r['pid']:>7} {r['name']}")
        L.append(f"     {st} · купить {r['cost']:g}₽ → продать {r['price']}₽ · фото {r['photos']} · "
                 f"габариты-посылки {r['dims'] or 'НЕТ'}")
        if r["errors"]:
            L.append(f"     ошибки: {r['errors']}")
        if r["need_mapping"]:
            L.append(f"     need_mapping={r['need_mapping']} category_id={r['category_id']}")
    for s in res["skipped_facts"]:
        L.append(f"⚠️  БЕЗ фактов (нет НАШЕГО описания): pid={s['pid']} {s['name']} — {s['reason']}")
    L.append("")
    n_in = sum(1 for r in res["built"] if r["stock"] == "in_stock")
    n_on = sum(1 for r in res["built"] if r["stock"] == "on_order")
    n_uk = sum(1 for r in res["built"] if r["stock"] is None)
    L.append(f"ИТОГ: собранных {len(res['built'])} · в наличии у донора СЕЙЧАС {n_in} · "
             f"под заказ {n_on} · неизвестно {n_uk}  "
             f"({('манифест готов к показу — ' if ok_all else 'есть ошибки — смотрим выше')}"
             f"живой залив только по слову оператора, RUBICON цел)")
    return "\n".join(L)


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Сухой манифест всех рулонов ВПП донора (0₽). RUBICON цел.")
    ap.add_argument("--json", action="store_true", help="печатать манифест JSON (а не человеко-таблицу)")
    args = ap.parse_args(argv)
    res = run()
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print(render(res))
    return 0


if __name__ == "__main__":
    sys.exit(_main())

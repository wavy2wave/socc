#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNIQUEIZER V1 — закон-слой УНИКАЛИЗАЦИИ карточки (стадия DUB органа ARBITER).

ЗАЧЕМ (слова создателя): Ozon/Яндекс.Маркет склеивают твой товар с чужой карточкой, если
он «как у всех» → в выдаче показывают конкурента, а не тебя. Задача — сделать так, чтобы МП
считал товар ТВОИМ уникальным и показывал ТОЛЬКО твою карточку. Уникализируем бесплатно,
СРАЗУ по законам контента Ozon/ЯМ — «чтобы потом не попасть впросак».

ЧТО КЛЕИТ КАРТОЧКИ (по убыванию силы ключа) и наш ответ:
  1. Штрихкод (barcode) — ГЛАВНЫЙ ключ склейки. Заводской штрихкод поставщика = мгновенная
     приклейка к чужой карточке. → генерим СВОЙ уникальный EAN-13 (префикс «2» — внутреннее/
     ограниченное обращение, НИКОГДА не сталкивается с реальным GTIN завода). Чистый рычаг.
  2. Название — рерайт в свой уникальный заголовок (тот же товар, другая формулировка).
  3. Бренд/производитель — своя марка ⇒ отдельная карточка.
  4. Фото — план трансформаций (кроп/зеркало/рамка/цвет/новый фон/вотермарка) ломает
     перцептивный хеш. Пиксели крутит стадия ниже (нужен image-lib); тут — честный ПЛАН.
  5. Описание + атрибуты — свои, расширенные.

ЧЕСТНАЯ ГРАНИЦА (закон, не обман):
  • CLEAN-рычаги (свой штрихкод, свои фото, свой текст/бренд-дом) — законная дифференциация,
    именно они выигрывают СВОЮ карточку. Включены по умолчанию.
  • RISK-рычаги (спуфинг реального чужого производителя) — товарный знак/ToS/модерация.
    ВЫКЛ по умолчанию; если включишь — law_report явно поднимает флаг. Решаешь ты.

stdlib-only (hashlib/difflib/math), fail-soft, без сети (фото-план декларативный).
"""
import sys
import json
import math
import hashlib
import difflib
import argparse

# ── Законы контента площадок (что примут без модерации-отбраковки) ──
PLATFORM_RULES = {
    "ozon": {"title_max": 200, "min_photos": 1, "brand_required": True,
             "barcode_field": "barcode", "own_barcode_prefix_ok": True},
    "yandex_market": {"title_max": 150, "min_photos": 1, "brand_required": True,
                      "barcode_field": "barcodes", "own_barcode_prefix_ok": True},
}

# Веса рычагов в снижении риска склейки (barcode доминирует — это главный ключ МП).
LEVER_WEIGHTS = {"own_barcode": 55, "photos_transformed": 20, "unique_title": 12,
                 "distinct_brand": 13}
CLEAN_LEVERS = ("own_barcode", "photos_transformed", "unique_title", "distinct_brand_house")
RISK_LEVERS = ("spoof_manufacturer",)  # выдать чужого реального производителя — риск


def gen_ean13(seed):
    """Детерминированный валидный EAN-13 с префиксом «2» (внутреннее/ограниченное обращение).

    Префикс 2 зарезервирован под in-store/restricted circulation — НЕ сталкивается с реальными
    заводскими GTIN. Детерминизм по seed (sku): повторный импорт даёт тот же код, не плодит дубли.
    """
    digest = hashlib.sha1(str(seed).encode("utf-8")).hexdigest()
    body = str(int(digest, 16) % (10 ** 11)).zfill(11)  # 11 цифр после префикса
    d12 = "2" + body                                     # 12 цифр данных
    s = sum((1 if i % 2 == 0 else 3) * int(ch) for i, ch in enumerate(d12))
    check = (10 - (s % 10)) % 10
    return d12 + str(check)


def _clean_tokens(name):
    """Разбить название на значимые токены (для рерайта и оценки схожести)."""
    return [t for t in "".join(c if c.isalnum() or c.isspace() else " "
                               for c in (name or "")).split() if len(t) > 1]


def unique_title(source_name, house_brand="", extra_kw=None, platform="ozon"):
    """Свой уникальный заголовок из того же товара (без вранья о сути), под лимит длины площадки.

    Приём: категорийное существительное вперёд + ключевые атрибуты + свой квалификатор/бренд-дом.
    Тот же товар — другая уникальная формулировка (ломает точное текстовое совпадение карточек).
    """
    toks = _clean_tokens(source_name)
    head = toks[0] if toks else "Товар"
    rest = toks[1:8]
    parts = [head] + rest
    if extra_kw:
        parts += [k for k in extra_kw if k]
    if house_brand:
        parts.append(house_brand)
    title = " ".join(dict.fromkeys(parts))  # убрать повторы, сохранить порядок
    limit = PLATFORM_RULES.get(platform, PLATFORM_RULES["ozon"])["title_max"]
    return title[:limit].strip()


def photo_transform_plan(image_urls, watermark="own"):
    """Декларативный план фото-трансформаций (ломает перцептивный хеш). Пиксели крутит стадия ниже.

    Честно: stdlib не редактирует изображения. Возвращаем ПЛАН операций + probe наличия image-lib.
    Если PIL доступен — стадия DUB исполнит; если нет — план идёт в тикет «переснять/обработать».
    """
    ops = ["crop_aspect_4x5", "mirror_horizontal_if_safe", "add_margin_border_3pct",
           "color_temp_nudge", "recompose_on_white_bg", f"watermark_{watermark}"]
    try:
        import PIL  # noqa: F401
        executable = True
    except Exception:
        executable = False
    return {"source_images": list(image_urls or []), "ops": ops,
            "executable_here": executable,
            "note": "план ломает перцептивный хеш; пиксели обрабатывает стадия DUB (нужен image-lib) "
                    "или тикет оператору, если библиотеки нет"}


def _title_similarity(a, b):
    """0..1 — насколько новый заголовок похож на исходный (ниже = уникальнее, меньше склейки)."""
    return difflib.SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def collision_risk(card, source_card):
    """Оценка риска склейки с чужой карточкой 0..100 (100 = гарантированно приклеит).

    Считаем от 100 вниз за каждый применённый рычаг. barcode доминирует (главный ключ МП).
    Возвращает {risk, verdict, levers_applied}. verdict: own_card_likely / borderline / will_merge.
    """
    risk = 100
    applied = []
    src_barcode = str(source_card.get("barcode") or "")
    new_barcode = str(card.get("barcode") or "")
    if new_barcode and new_barcode != src_barcode:
        risk -= LEVER_WEIGHTS["own_barcode"]
        applied.append("own_barcode")
    plan = card.get("photo_plan") or {}
    if plan.get("ops"):
        risk -= LEVER_WEIGHTS["photos_transformed"]
        applied.append("photos_transformed")
    if _title_similarity(card.get("name"), source_card.get("name")) < 0.6:
        risk -= LEVER_WEIGHTS["unique_title"]
        applied.append("unique_title")
    if card.get("brand") and card.get("brand") != source_card.get("brand"):
        risk -= LEVER_WEIGHTS["distinct_brand"]
        applied.append("distinct_brand")
    risk = max(0, min(100, risk))
    verdict = ("own_card_likely" if risk < 25 else
               "borderline" if risk <= 50 else "will_merge")
    return {"risk": risk, "verdict": verdict, "levers_applied": applied}


def content_law_check(card, platform="ozon"):
    """Проверка по законам контента площадки — чтобы карточку не отбраковала модерация."""
    rules = PLATFORM_RULES.get(platform, PLATFORM_RULES["ozon"])
    checks = {
        "title_ok": bool(card.get("name")) and len(card["name"]) <= rules["title_max"],
        "brand_ok": (not rules["brand_required"]) or bool(card.get("brand")),
        "photos_ok": len((card.get("photo_plan") or {}).get("source_images", [])) >= rules["min_photos"],
        "barcode_ok": bool(card.get("barcode")),
    }
    return {"platform": platform, "passed": all(checks.values()),
            "checks": checks, "why": [k for k, v in checks.items() if not v]}


def uniqueize(product, source_card=None, house_brand="", platform="ozon",
              extra_kw=None, spoof_manufacturer=None):
    """Собрать уникализированную карточку под площадку + law_report (чисто/риск, риск склейки).

    product — нормализованный товар SCOUT (sku/name/url/brand/...). source_card — сырьё поставщика
    (для сравнения; по умолчанию из product). house_brand — твоя марка-дом (чистый рычаг).
    spoof_manufacturer — РИСК-рычаг (выдать чужого реального производителя); None/пусто = ВЫКЛ.
    """
    source_card = dict(source_card or {"name": product.get("name"),
                                       "brand": product.get("brand", ""),
                                       "barcode": product.get("barcode", "")})
    sku = product.get("sku") or product.get("url") or product.get("name")
    house_brand = house_brand or "MY HOUSE"

    brand_out = house_brand
    risk_levers = []
    if spoof_manufacturer:
        brand_out = str(spoof_manufacturer)          # RISK: чужой реальный производитель
        risk_levers.append("spoof_manufacturer")

    photo_plan = photo_transform_plan([product.get("url")] if product.get("url") else [])
    card = {
        "offer_id": f"ARB-{gen_ean13(sku)[-8:]}",     # свой артикул продавца
        "barcode": gen_ean13(sku),                    # СВОЙ уникальный штрихкод — главный рычаг
        "name": unique_title(source_card.get("name"), house_brand, extra_kw, platform),
        "brand": brand_out,
        "price_source_cost": product.get("cost"),
        "source_market": product.get("source_market"),
        "source_url": product.get("url"),
        "photo_plan": photo_plan,
        "platform": platform,
    }
    coll = collision_risk(card, source_card)
    law = content_law_check(card, platform)
    clean_applied = [l for l in coll["levers_applied"]]
    if house_brand and "distinct_brand" in clean_applied:
        clean_applied = [("distinct_brand_house" if x == "distinct_brand" else x)
                         for x in clean_applied]
    report = {
        "collision": coll,
        "content_law": law,
        "clean_levers": clean_applied,
        "risk_levers": risk_levers,
        "warnings": (["⚠ spoof_manufacturer ВКЛ: риск товарного знака/ToS/модерации — решение оператора"]
                     if risk_levers else []),
        "publish_ok": law["passed"] and coll["verdict"] != "will_merge",
    }
    return {"card": card, "law_report": report}


def _main(argv=None):
    ap = argparse.ArgumentParser(description="UNIQUEIZER V1 — закон уникализации карточки (DUB)")
    ap.add_argument("--name", required=True, help="исходное название товара поставщика")
    ap.add_argument("--sku", default="", help="sku/nmId поставщика (сид штрихкода)")
    ap.add_argument("--brand", default="", help="исходный бренд поставщика")
    ap.add_argument("--url", default="", help="ссылка на товар поставщика")
    ap.add_argument("--house-brand", default="MY HOUSE", help="твоя марка-дом (чистый рычаг)")
    ap.add_argument("--platform", default="ozon", choices=sorted(PLATFORM_RULES))
    ap.add_argument("--spoof-manufacturer", default="", help="РИСК: выдать чужого производителя (по умолч. выкл)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    product = {"sku": args.sku or args.name, "name": args.name, "brand": args.brand,
               "url": args.url, "source_market": "wildberries"}
    res = uniqueize(product, house_brand=args.house_brand, platform=args.platform,
                    spoof_manufacturer=args.spoof_manufacturer or None)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    c, r = res["card"], res["law_report"]
    print(f"🎯 УНИКАЛИЗАЦИЯ [{c['platform']}]")
    print(f"   штрихкод(свой): {c['barcode']}   offer_id: {c['offer_id']}")
    print(f"   было:  «{args.name}»  [{args.brand or '—'}]")
    print(f"   стало: «{c['name']}»  [{c['brand']}]")
    print(f"   риск склейки: {r['collision']['risk']}/100 → {r['collision']['verdict']}  "
          f"(рычаги: {', '.join(r['collision']['levers_applied']) or '—'})")
    print(f"   закон контента [{c['platform']}]: {'✅' if r['content_law']['passed'] else '❌ ' + str(r['content_law']['why'])}")
    print(f"   фото-план: {', '.join(c['photo_plan']['ops'])}  (исполнимо тут: {c['photo_plan']['executable_here']})")
    for w in r["warnings"]:
        print(f"   {w}")
    print(f"   → публиковать можно: {'ДА' if r['publish_ok'] else 'НЕТ (снизь риск/дозаполни)'}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

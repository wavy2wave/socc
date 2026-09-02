#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ФОТО-АУДИТ 20 плёнок: сколько снимков реально есть и откуда (офлайн, 0 ₽).

ЗАЧЕМ. Разведка 2026-08-11 показала: индекс контента в категории 76346336 определяется
ЧИСЛОМ КАРТИНОК, а не числом параметров. Натуральный эксперимент на трёх карточках с
побитово одинаковыми 11 параметрами: 1 фото → 69, 3 фото → 83, 6 фото → 87.
Фотоблок стоит ≈20 пунктов и насыщается на 5-6 снимках.

Высокоиндексные карточки тянут снимки с фотобанка WB (basket-XX.wbbasket.ru) по 3-6 штук,
низкоиндексные — с сайта донора по одной, да ещё через /watermark/ (водяной знак донора).

ВОПРОС, НА КОТОРЫЙ ОТВЕЧАЕТ ЭТОТ СКРИПТ: у скольких позиций уже есть много фото, и сколько
мы теряем на фильтрах органа (verify_pictures + photo_source_matches отклоняют чужой товар).
Если снимки есть в выгрузке — индекс поднимается БЕЗ съёмки и без генерации.
"""
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_from_xlsx_v1 as fx  # noqa: E402

XLSX = "/Users/wavysexy/parsers/parsed_data/cargo-avto_MASTER_2026-08-03_03-06-11.xlsx"

LIVE = {"9600154", "9600155", "9600239", "9600879", "9601440", "9601512", "9601513",
        "9601515", "9601516", "9602037", "9602468", "9602489", "9603273", "9604033",
        "9604035", "9604036", "9604815", "9604816", "9605336", "9605392"}

# По кривой индекса: 3 фото дают почти весь прирост, 5-6 — насыщение
TARGET_PHOTOS = 5


def host_of(url):
    return re.sub(r"^https?://([^/]+).*", r"\1", url)


def main():
    films = [p for p in fx.load_category(XLSX, slug="puzyrkovaya-plenka")["products"]
             if p["sku"].split("-")[0] in LIVE]
    films.sort(key=lambda p: -len(p.get("pictures") or []))

    print("цель: %d фото на карточку (насыщение кривой индекса)\n" % TARGET_PHOTOS)
    print("%-12s%9s%11s%9s  %s" % ("SKU", "принято", "отклонено", "нужно", "хосты принятых"))
    print("-" * 78)

    total_ok = total_rej = 0
    need_shoot = []
    watermarked = []
    for p in films:
        pics = p.get("pictures") or []
        rej = p.get("_photos_rejected") or []
        total_ok += len(pics)
        total_rej += len(rej)
        hosts = collections.Counter(host_of(u) for u in pics)
        gap = max(0, TARGET_PHOTOS - len(pics))
        if gap:
            need_shoot.append(p["sku"])
        if any("/watermark/" in u for u in pics):
            watermarked.append(p["sku"])
        print("%-12s%9d%11d%9d  %s"
              % (p["sku"], len(pics), len(rej), gap,
                 ", ".join("%s×%d" % (h, n) for h, n in hosts.items()) or "—"))

    print("-" * 78)
    print("всего принято: %d · отклонено фильтрами: %d" % (total_ok, total_rej))
    print("позиций ниже цели: %d из %d" % (len(need_shoot), len(films)))
    print("с водяным знаком донора: %d %s"
          % (len(watermarked), watermarked if watermarked else ""))

    if total_rej:
        print("\nПРИЧИНЫ ОТКЛОНЕНИЯ (фильтры органа берегут от чужого товара):")
        why = collections.Counter()
        for p in films:
            for r in (p.get("_photos_rejected") or []):
                why[str(r.get("why"))[:70]] += 1
        for w, n in why.most_common(8):
            print("   ×%-3d %s" % (n, w))


if __name__ == "__main__":
    main()

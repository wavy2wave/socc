#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЕСТЬ ЛИ У ДОНОРА ЧИСТОЕ ФОТО БЕЗ ВОДЯНОГО ЗНАКА (только HEAD/GET, 0 ₽).

ЗАЧЕМ. Все 18 позиций тянут снимки через /upload/cache/resized/watermark/ — с водяным знаком
донора. Колонка «Фото без вотермарка» в выгрузке ПУСТА: парсер чистых не нашёл.
Ставить чужой водяной знак на карточку нельзя — это и чужой бренд в кадре, и риск по правилам
Маркета к главному изображению.

ЧТО ПРОБУЕМ. Битрикс обычно хранит оригинал в /upload/iblock/, а кэш-варианты — в
/upload/cache/resized/<профиль>/. Значит у файла с водяным знаком может быть чистый близнец
по другому пути. Проверяем набор гипотез HEAD-запросами: что вернёт 200 и какого размера.

ЧЕСТНОСТЬ. Скрипт НЕ доказывает отсутствие водяного знака — только доступность файла.
Глазами всё равно проверять оператору: 200 OK не значит «чисто».
"""
import re
import sys
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")

SAMPLE = ("https://sp.cargo-avto.ru/upload/cache/resized/watermark/"
          "9601515__4da95ee2d78598a397de6da4fab1c6c1.webp")


def variants(url):
    """Гипотезы путей к чистому файлу того же изображения."""
    out = []
    m = re.match(r"(https?://[^/]+)/upload/cache/resized/watermark/(.+)$", url)
    if not m:
        return out
    host, fname = m.group(1), m.group(2)
    # 1) тот же кэш без профиля watermark
    out.append(("cache без watermark", f"{host}/upload/cache/resized/{fname}"))
    # 2) типовые профили кэша Битрикса
    for prof in ("big", "large", "orig", "original", "detail", "medium", "small", "preview"):
        out.append((f"профиль {prof}", f"{host}/upload/cache/resized/{prof}/{fname}"))
    # 3) оригинал в iblock (имя-хеш обычно тот же)
    out.append(("iblock напрямую", f"{host}/upload/iblock/{fname}"))
    # 4) без папки cache вовсе
    out.append(("upload напрямую", f"{host}/upload/{fname}"))
    # 5) смена расширения (вебп ↔ жпег) на самом рабочем пути
    base = fname.rsplit(".", 1)[0]
    out.append(("watermark → .jpg", f"{host}/upload/cache/resized/watermark/{base}.jpg"))
    out.append(("cache → .jpg", f"{host}/upload/cache/resized/{base}.jpg"))
    return out


def probe(url, timeout=20):
    """(код, размер, тип) или (None, причина). HEAD, при отказе — GET первых байт."""
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, r.headers.get("Content-Length"), r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        return e.code, None, None
    except Exception as e:
        return None, type(e).__name__, None


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else SAMPLE
    print("эталон (с водяным знаком):")
    code, size, ctype = probe(url)
    print("   %-24s %s  size=%s  %s\n" % ("watermark (как есть)", code, size, ctype))
    base_size = size

    print("гипотезы чистого файла:")
    hit = []
    for name, cand in variants(url):
        code, size, ctype = probe(cand)
        mark = ""
        if code == 200:
            mark = " ← ЕСТЬ"
            if base_size and size and size != base_size:
                mark += " (размер ДРУГОЙ — вероятно без знака)"
            hit.append((name, cand, size))
        print("   %-24s %-5s size=%-9s %s%s" % (name, code, size, ctype or "", mark))

    print()
    if hit:
        print("НАЙДЕНО доступных вариантов: %d" % len(hit))
        for name, cand, size in hit:
            print("   %s\n      %s" % (name, cand))
        print("\nГЛАЗАМИ ПРОВЕРИТЬ ОБЯЗАТЕЛЬНО: 200 OK не значит «без водяного знака».")
    else:
        print("Чистого близнеца по типовым путям НЕТ. Значит вариантов два:")
        print("  1) снимать/делать свои фото (у нас 134 кадра донора — только как референс);")
        print("  2) искать снимки этого товара у другого источника с правом использования.")


if __name__ == "__main__":
    main()

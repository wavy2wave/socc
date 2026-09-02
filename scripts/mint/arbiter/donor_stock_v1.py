#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЖИВОЕ НАЛИЧИЕ У ДОНОРА (sp.cargo-avto.ru) — читатель, 0 ₽, только GET.

ЗАЧЕМ. Выгрузка XLSX стареет: у 9 из 20 плёнок колонка «Наличие» пуста, и ТОВАРОВЕД честно
отбивал их (T4: «нет источника наличия — карточка родится мёртвой»). Закон СКЛАДОВЩИКА —
«лучше ноль, чем ложь»: остаток не выдумываем. Значит источник наличия должен быть ЖИВОЙ.

ЧТО ЧИТАЕМ. На карточке донора статус магазина стоит сразу за маркером «Интернет-магазин:».
Остальные вхождения «В наличии»/«Под заказ» на странице относятся к пунктам самовывоза —
их берём отдельно и НЕ путаем с наличием на складе.

ЧЕСТНОСТЬ (закон L3): не нашли маркер → status=None (не знаем), а НЕ «нет в наличии».
Неизвестность отличается от отрицания: первое чинится повтором, второе гасит карточку.
"""
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://sp.cargo-avto.ru/catalog/{pid}/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")

# Маркер, за которым идёт статус склада интернет-магазина (проверено живьём 2026-08-09)
_SHOP_ANCHOR = "Интернет-магазин:"
_IN_STOCK = "в наличии"
_ON_ORDER = "под заказ"


def _strip(html_fragment):
    """HTML → плоский текст (теги в пробелы, схлопнутые пробелы)."""
    txt = re.sub(r"<[^>]+>", " ", html_fragment)
    return re.sub(r"\s+", " ", txt).strip()


def fetch(pid, timeout=40, retries=2):
    """Страница товара донора. Сеть моргнула → пробуем ещё раз, потом честный None."""
    url = BASE.format(pid=pid)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
        except Exception:
            if attempt >= retries:
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def parse_stock(html):
    """{status, human, raw} из HTML карточки. status: 'in_stock' | 'on_order' | None.

    Берём ТОЛЬКО текст после маркера «Интернет-магазин:» — это склад, с которого поедет заказ.
    """
    if not html:
        return {"status": None, "human": "страница не прочитана", "raw": None}
    i = html.find(_SHOP_ANCHOR)
    if i < 0:
        return {"status": None, "human": "маркер «Интернет-магазин:» не найден", "raw": None}
    tail = _strip(html[i:i + 400]).lower()
    # Первое встреченное слово-статус после маркера и есть ответ
    pos_in, pos_on = tail.find(_IN_STOCK), tail.find(_ON_ORDER)
    if pos_in < 0 and pos_on < 0:
        return {"status": None, "human": "статус за маркером не распознан", "raw": tail[:120]}
    if pos_on < 0 or (0 <= pos_in < pos_on):
        return {"status": "in_stock", "human": "в наличии у донора", "raw": tail[:120]}
    return {"status": "on_order", "human": "под заказ у донора", "raw": tail[:120]}


def stock_for(pids, pause=0.7, verbose=False):
    """Наличие пачки артикулов: {pid: {...}}. Пауза между запросами — вежливость к донору."""
    out = {}
    for n, pid in enumerate(pids):
        res = parse_stock(fetch(pid))
        out[pid] = res
        if verbose:
            print("  %-10s %-9s %s" % (pid, res["status"] or "unknown", res["human"]))
        if n < len(pids) - 1:
            time.sleep(pause)
    return out


def apply_to(products, stock_map):
    """Проставить товарам stock_source/in_stock по живому наличию. Меняет products на месте.

    ЗАКОН: только 'in_stock' даёт источник наличия. 'on_order' и None — НЕ дают
    (под заказ на Экспрессе = отмена по нашей вине; неизвестность = не выдумываем).

    КЛЮЧ СТРАНИЦЫ — АРТИКУЛ, не bx-id. cargo_avto кладёт в normalized() и sku (bx-id из листинга,
    9048), и article (артикул донора, 9602037). Живая страница — только по article: /catalog/9602037/
    отдаёт 655КБ с маркером «Интернет-магазин:», а /catalog/9048/ — HTTP 404 (проверено живьём
    2026-09-01 на обоих хостах). Пока брали sku, донорская присоска кормила stock_for мёртвыми URL,
    все карточки рождались без stock_source (закон СКЛАДОВЩИКА). article нет (детмир/wb) → как раньше sku.
    """
    marked = 0
    for p in products:
        pid = str(p.get("article") or p.get("sku", "")).split("-")[0]
        st = (stock_map.get(pid) or {}).get("status")
        p["donor_stock"] = st
        if st == "in_stock":
            p["stock_source"] = "донор:живой сайт"
            p["in_stock"] = True
            marked += 1
        else:
            p.pop("stock_source", None)
            p["in_stock"] = False if st == "on_order" else None
    return marked


if __name__ == "__main__":
    pids = sys.argv[1:] or ["9600154", "9601515"]
    print("читаю наличие у донора: %d позиций" % len(pids))
    res = stock_for(pids, verbose=True)
    n_in = sum(1 for v in res.values() if v["status"] == "in_stock")
    n_on = sum(1 for v in res.values() if v["status"] == "on_order")
    print("\nв наличии: %d · под заказ: %d · неизвестно: %d"
          % (n_in, n_on, len(res) - n_in - n_on))

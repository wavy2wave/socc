#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET TWIN GATE V1 — флаг ДУБЛЬ-ВИРИНЫ у кандидатов готовности категорийщика (read-only, 0₽).

Дыра 04.09 (живой аудит ready24): у КАТЕГОРИЙЩИКА нет dedup-гейта против УЖЕ ЖИВЫХ карточек кабинета.
Цикл-1 имеет свой twin-гейт (halt по parameterValues ВНУТРИ своей витрины, ymarket_cycle1_v1._twin_halt),
а категорийщик собирает шорт-лист вслепую. Живой случай: 4 ready-SKU пузырчатки (1588731/9048/6335/2050)
== donor_pid 4 ЖИВЫХ фирменных ARB-карточек (PASS+FIT 03.09, atlas-express-film) — повторный залив сделал
бы вторую (дешёвую) карточку того же товара донора.

ЧТО ДЕЛАЕТ: читает ymarket_goods_library.json (живые карточки с donor_pid) и для каждой строки
готовности (offerId == донорский sku) ставит ФЛАГ dubl_live + evidence. ФЛАГ, НЕ halt и НЕ исключение:
судьба таких SKU — решение оператора (RUBICON цел). Идентичность — только по donor_pid (прямой донор),
НЕ по имени/спеке (узкий гейт без ложных близнецов).

Проверено 04.09 на реальном durable: 4 puzyr-кандидата получают dubl_live, остальные 20 ready-SKU — нет.

Законы: read-only локальный файл, 0 GET, 0₽; ничего не пишет наружу; чужих полей не выдумывает
(sku не в библиотеке = честно «нет живого близнеца», не «дубль»).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB_PATH = HERE.parent.parent.parent \
    / "MEMORY_WAVE/reports/mint/arbiter/ymarket_goods_library.json"


def live_donor_pids(doc=None, library_path=LIB_PATH):
    """donor_pid живых карточек → сведения о живых карточках этого донор-товара.

    doc — словарь ymarket_goods_library (для шва тестов); по умолч. читаем файл. Возвращает
    {pid_str: [{offer_id, price, store_slug, article, name}]}. Только карточки, у кого donor_pid есть.
    """
    if doc is None:
        try:
            doc = json.load(open(library_path))
        except OSError as e:
            # НЕТ файла живых карточек ≠ «0 дублей» — это была бы ложь «не дубль». Исключить дубли можно
            # только ПРОТИВ фактического списка живых donor_pid; без него гейт не способен быть честным →
            # громкий отказ (аудит 04.09, #4: молчаливый fail-open закрыт). Симметрично жёсткому крашу
            # на битом JSON ниже. (Вне автопилота: орган читают в момент слова / на артефакте — шов
            # тестов подаёт doc инъекцией.)
            raise SystemExit(
                f"TWIN-GATE: библиотека живых карточек недоступна ({library_path}) — {e}.\n"
                "Без фактического списка живых donor_pid не могу честно исключить дубли. "
                "Не продолжать: «не дубль» без библиотеки = ложь.")
    out = {}
    goods = (doc or {}).get("goods") or {}
    if not isinstance(goods, dict):
        return out
    for oid, gd in goods.items():
        if not isinstance(gd, dict):
            continue
        pid = gd.get("donor_pid")
        if pid is None:
            continue
        pid = str(pid)
        out.setdefault(pid, []).append({
            "offer_id": str(oid),
            "price": gd.get("price"),
            "store_slug": gd.get("store_slug"),
            "article": gd.get("article"),
            "name": gd.get("name"),
        })
    return out


def flag_rows(rows, live=None):
    """Строки готовности (offerId|sku) → те же строки + dubl_live/dubl_evidence. Мутирует копии.

    live — результат live_donor_pids (шов тестов); по умолч. читает файл сам. ФЛАГ: строка, чей
    offerId == donor_pid живой карточки, получает dubl_live=True + evidence. Остальные — False.
    """
    live = live_donor_pids() if live is None else live
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        copy = dict(r)
        sku = str(copy.get("offerId") if copy.get("offerId") is not None else copy.get("sku") or "")
        hits = live.get(sku)
        copy["dubl_live"] = bool(hits)
        if hits:
            copy["dubl_evidence"] = hits          # живые карточки того же донор-товара
        out.append(copy)
    return out


def flag_file(path, live=None):
    """JSON готовности категорийщика → (строки с флагами, сводка). read-only."""
    d = json.load(open(path))
    rows = d.get("shortlist") or d.get("shortlist_selected") or []
    flagged = flag_rows(rows, live=live)
    dubl = [r for r in flagged if r.get("dubl_live")]
    return flagged, {
        "rows": len(flagged), "dubl_live": len(dubl),
        "skus": [str(r.get("offerId") or r.get("sku")) for r in dubl],
    }


def _main(argv):
    if len(argv) < 2:
        print("использование: python3 ymarket_twin_gate_v1.py <readiness.json> [goods_library.json]")
        return 2
    path = argv[1]
    libp = argv[2] if len(argv) > 2 else LIB_PATH
    rows, summ = flag_file(path, live=live_donor_pids(library_path=Path(libp)))
    print(f"строк готовности: {summ['rows']} | dubl_live: {summ['dubl_live']}")
    for r in rows:
        sku = str(r.get("offerId") or r.get("sku") or "?")
        mark = "DUBL_LIVE" if r.get("dubl_live") else "ok"
        print(f"  {mark:9s} {sku:10s} {str(r.get('name'))[:70]}")
        for e in (r.get("dubl_evidence") or []):
            print(f"           ↳ живой {e.get('offer_id')} {e.get('price')}₽ {e.get('store_slug')} "
                  f"art={e.get('article')}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))

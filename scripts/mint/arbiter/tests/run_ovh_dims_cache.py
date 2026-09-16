#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОВХ · last-known-good кэш габаритов — герметичная приёмка (сети нет, 0₽).

Зачем: 2026-09-03 у atlas-express-film СБОРКА сухо упала на ARB-53416854 — одноразовый пустой
ответ донора ('' вместо HTML) на ОВХ-GET; следующий прогон через 3 мин прошёл. Кэш закрывает
ровно это: реальные габариты ТОЙ ЖЕ карточки, прочитанные ранее, восстанавливаются на флап —
карточка честно проходит, ничего не выдумываем (значения = то, что донор сам отдавал).

Законы:
  OV1 кэш_восстановил_флап  — успех → кэш записан; флап ('' на том же url) → dims+weight из кэша,
                             dims_cached=True, провенанс dims_source сохранён.
  OV2 первый_раз_честно     — НЕ читанную карточку с '' НЕ выдумываем: габаритов нет, кэша нет.
  OV3 свежесть_перезаписи   — следующий успех перезаписывает кэш; флап берёт НОВЕЙШИЕ габариты.
  OV4 кэш_выключен_герметич — cache_path=None: флап не восстанавливает, файла не пишет (шов для
                             герметичных тестов zaliv/film — кэш не мешает).
  OV5 адрес_по_умолчанию    — DIMS_CACHE_DEFAULT лежит под runtime/ arbiter-каталога (виден как
                             артефакт рядом с леджером цикла).
  OV6 рулон_цилиндр_физика  — рулон БЕЗ «Размер упаковки», с «Транспортировочный объем, м³» → габариты =
                             САМ рулон-цилиндр (коробки НЕТ, директива 04.09): D=√(4V/(πL)).
                             Эталоны = ЖИВЫЕ карточки донора: 500мм/V=0.004253 → [50,10.4,10.4] (9600231),
                             мини 125мм/V=0.001066 → [12.5,10.4,10.4] (9604766), Extra 300мм/V=0.001192 →
                             [30,7.1,7.1] (9602926). Ширина «…, мм» НЕ выдаётся за метры.
  OV7 ширина_из_названия    — карточка БЕЗ колонки ширины → ширина ИЗ НАЗВАНИЯ («…, 500 мм, …»); правка
                             дефекта (а): предикат обогащения = живой url, dims_raw НЕ нужен (имя стрейча
                             «500 мм, 20 мкм…» регексом «50*0.3 м» dims_raw не даёт — и это не повод молчать).
  OV8 честные_негативы      — «20 мкм»/«0.02 мм»/«2 кг/м²»/диспенсер-без-«мм» НЕ читаются как ширина/вес;
                             вес из названия («…, 2 кг») — ЛЕГАЛЬНЫЙ фолбэк с провенансом 'донор:название'.
  OV9 единицы_ширины        — «Ширина, мм=500» и «Ширина, см=50» обе дают 0.5 м → ОДИН результат
                             [50,10.4,10.4] (мм/см → м, иначе ложь в 1000/100 раз).

Запуск: python3 scripts/mint/arbiter/tests/run_ovh_dims_cache.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ARB = Path(__file__).resolve().parent.parent
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

from ymarket_ovh_dims_v1 import (DIMS_CACHE_DEFAULT, _DIM_FLAT, enrich, enrich_products)  # noqa: E402


def _html(pack_cm="50*35*50", weight_kg="1.438"):
    """Карточка донора: имя свойства закрыто </span>, значение — в соседнем <div> (формат Bitrix)."""
    return (
        '<div class="properties-group__name">Размер упаковки Д*Ш*В, см</span>'
        f'<div class="properties-group__value">{pack_cm}</div>'
        '<div class="properties-group__name">Вес, кг</span>'
        f'<div class="properties-group__value">{weight_kg}</div>'
    )


def _card(**props):
    """Карточка-HTML из словаря свойств {имя: значение} (порядок вставки сохраняется) — Bitrix-формат."""
    return "".join(
        f'<div class="properties-group__name">{k}</span>'
        f'<div class="properties-group__value">{v}</div>'
        for k, v in props.items()
    )


def _roll(width, kg, vol, *, width_prop="Ширина, мм", um=None):
    """Карточка РУЛОНА без «Размер упаковки»: ширина(мм/см), вес, объём самого рулона (9600231-стиль)."""
    props = {width_prop: str(width), "Вес, кг": str(kg), "Транспортировочный объем, м³": str(vol)}
    if um:
        props["Толщина, мкм"] = str(um)
    return _card(**props)


UA = "https://shop.cargo-avto.ru/catalog/9602037/"
UB = "https://shop.cargo-avto.ru/catalog/9999999/"
UC = "https://shop.cargo-avto.ru/catalog/9600231/"   # стрейч 500 мм (V=0.004253)
UD = "https://shop.cargo-avto.ru/catalog/9604766/"   # мини 125 мм (V=0.001066)
UE = "https://shop.cargo-avto.ru/catalog/9602926/"   # пищевая Extra 300 мм (V=0.001192)
UF = "https://shop.cargo-avto.ru/catalog/9605555/"   # рулон без колонки «Ширина» (ширина из названия)
UG = "https://shop.cargo-avto.ru/catalog/9606666/"   # «Ширина, см» вариант
UH = "https://shop.cargo-avto.ru/catalog/9607777/"   # диспенсер (без «мм»/без объёма рулона)


def _row(pid, url, article="9602037"):
    return {"pid": pid, "url": url, "dims_raw": "50*0.3 м",
            "name": "Плёнка пузырчатая", "article": article, "cost": 600.0}


def main():
    print("🌱 ОВХ · last-known-good кэш габаритов · герметично (сети нет, 0₽)")
    all_ok = True
    n = [0]

    def ok(tag, cond, note=""):
        n[0] += 1
        mark = "✅" if cond else "❌"
        print(f"   {mark} {tag}" + (f"  {note}" if note and not cond else ""))
        nonlocal all_ok
        all_ok = all_ok and cond

    tmp = Path(tempfile.mkdtemp())
    cpath = tmp / "ovh_dims_cache.json"

    # OV1 — успех пишет кэш; флап на том же url восстанавливает реальные габариты
    rows = [_row("1", UA)]
    enrich_products(rows, fetch=lambda url: _html(), cache_path=cpath)
    p = rows[0]
    ok("OV1 success_dims", p.get("length") == 50.0 and p.get("width") == 35.0
       and p.get("height") == 50.0 and p.get("dims_source") == "card",
       f"dims={[p.get(k) for k in _DIM_FLAT]}")
    ok("OV1 success_weight", p.get("weight") == 1.438 and p.get("weight_source") == "донор:карточка")
    ok("OV1 cache_written", cpath.exists() and cpath.stat().st_size > 0)

    rows2 = [_row("1", UA)]
    enrich_products(rows2, fetch=lambda url: "", cache_path=cpath)   # флап 2026-09-03 14:19
    p2 = rows2[0]
    ok("OV1 flake_restored", all(p2.get(k) == v for k, v in zip(_DIM_FLAT, (50.0, 35.0, 50.0)))
       and p2.get("weight") == 1.438, f"dims={[p2.get(k) for k in _DIM_FLAT]}")
    ok("OV1 marked_cached", p2.get("dims_cached") is True and p2.get("dims_cached_ts")
       and p2.get("dims_source") == "card", "пометка «кэш», провенанс не потерян")

    # OV2 — НЕ читанную карточку с '' не выдумываем: честно без габаритов, кэш не пишем
    fresh = tmp / "fresh.json"
    rows3 = [_row("3", UB, article="9602999")]
    enrich_products(rows3, fetch=lambda url: "", cache_path=fresh)
    p3 = rows3[0]
    ok("OV2 first_run_honest", not p3.get("length") and not p3.get("dims_cached")
       and not p3.get("weight"), f"length={p3.get('length')!r} cached={p3.get('dims_cached')!r}")
    ok("OV2 no_cache_file", not fresh.exists())

    # OV3 — следующий успех перезаписывает кэш; флап берёт НОВЕЙШИЕ габариты
    rows4 = [_row("1", UA)]
    enrich_products(rows4, fetch=lambda url: _html(pack_cm="60*40*55", weight_kg="2.100"),
                    cache_path=cpath)
    rows5 = [_row("1", UA)]
    enrich_products(rows5, fetch=lambda url: "", cache_path=cpath)
    p5 = rows5[0]
    ok("OV3 newest_wins", [p5.get(k) for k in _DIM_FLAT] == [60.0, 40.0, 55.0]
       and p5.get("weight") == 2.1, f"dims={[p5.get(k) for k in _DIM_FLAT]} w={p5.get('weight')}")

    # OV4 — cache_path=None: флап не восстанавливает, файла не пишет (герметичный шов)
    rows6 = [_row("1", UA)]
    enrich_products(rows6, fetch=lambda url: "", cache_path=None)
    p6 = rows6[0]
    ok("OV4 cache_off_honest", not p6.get("length") and not p6.get("dims_cached"),
       f"length={p6.get('length')!r}")

    # OV5 — адрес по умолчанию под runtime/ arbiter-каталога (артефакт рядом с леджером цикла)
    ok("OV5 default_path_runtime", str(DIMS_CACHE_DEFAULT).endswith("runtime/ovh_dims_cache.json")
       and str(DIMS_CACHE_DEFAULT).startswith(str(ARB)), str(DIMS_CACHE_DEFAULT))

    # ── OV6-OV9: производные-рулоны (директива 04.09 «коробки нет», «ширина в названии») ───────────
    # OV6 — рулон БЕЗ «Размер упаковки», с объёмом САМОГО рулона → цилиндр D=√(4V/(πL)).
    #       Эталоны = живые карточки донора: 500мм 9600231 · мини 125мм 9604766 · Extra 300мм 9602926.
    for url, wval, kg, vol, exp in [
            (UC, 500, "2", "0.004253", [50.0, 10.4, 10.4]),
            (UD, 125, "0.5", "0.001066", [12.5, 10.4, 10.4]),
            (UE, 300, "0.4", "0.001192", [30.0, 7.1, 7.1])]:
        r = [{"url": url, "name": "Стрейч рулон"}]
        enrich_products(r, fetch=lambda url, w=wval, k=kg, v=vol: _roll(w, k, v), cache_path=cpath)
        p = r[0]
        ok(f"OV6 roll {wval}мм {exp[0]}×{exp[1]}×{exp[2]}", [p.get(k) for k in _DIM_FLAT] == exp
           and p.get("dims_source") == "physics"
           and p.get("weight") == float(kg) and p.get("weight_source") == "донор:карточка",
           f"dims={[p.get(k) for k in _DIM_FLAT]} src={p.get('dims_source')}")

    # OV7 — карточка БЕЗ колонки «Ширина» → ширина ИЗ НАЗВАНИЯ («…, 500 мм, …»);
    #       строка без dims_raw (имя стрейча регексом «50*0.3 м» его не даёт) всё равно обогащается
    r7 = [{"url": UF, "name": "Стрейч пленка прозрачная, 500 мм, 20 мкм, 2 кг, 1 сорт"}]
    enrich_products(r7, fetch=lambda url: _card(**{"Вес, кг": "2",
                                                   "Транспортировочный объем, м³": "0.004253"}),
                    cache_path=cpath)
    p7 = r7[0]
    ok("OV7 width_from_name", [p7.get(k) for k in _DIM_FLAT] == [50.0, 10.4, 10.4]
       and p7.get("dims_source") == "physics",
       f"dims={[p7.get(k) for k in _DIM_FLAT]} src={p7.get('dims_source')}")

    # OV8 — честные негативы: «мкм»/«0.02 мм»/«2 кг/м²»/диспенсер-без-мм НЕ читаются как ширина/вес;
    #       «…, 2 кг» из названия — ЛЕГАЛЬНЫЙ фолбэк веса с провенансом 'донор:название'
    neg = [{"url": UB, "name": "Плёнка пузырчатая 20 мкм, толщина 0.02 мм"},
           {"url": UH, "name": "Диспенсер для стрейч пленки Кавказ, пластиковый"},
           {"url": UB, "name": "Плёнка 2 кг/м²"}]
    for row in neg:
        enrich(row, {})
    ok("OV8 negatives_no_false", all(not row.get("length") and not row.get("weight") for row in neg),
       f"l={[row.get('length') for row in neg]} w={[row.get('weight') for row in neg]}")
    wname = {"url": UH, "name": "Стрейч плёнка, 500 мм, 20 мкм, 2 кг, 1 сорт"}
    enrich(wname, {})
    ok("OV8 name_weight_legal", wname.get("weight") == 2.0
       and wname.get("weight_source") == "донор:название" and not wname.get("length"),
       f"w={wname.get('weight')} src={wname.get('weight_source')}")

    # OV9 — единицы ширины: «Ширина, мм=500» и «Ширина, см=50» → ОДИН результат [50,10.4,10.4]
    for rp, url in [("Ширина, мм", UC), ("Ширина, см", UG)]:
        rr = [{"url": url, "name": "Стрейч рулон"}]
        wval = 500 if rp.endswith("мм") else 50
        enrich_products(rr, fetch=lambda url, w=wval, pr=rp: _roll(w, "2", "0.004253", width_prop=pr),
                        cache_path=cpath)
        pp = rr[0]
        ok(f"OV9 unit {rp}", [pp.get(k) for k in _DIM_FLAT] == [50.0, 10.4, 10.4],
           f"dims={[pp.get(k) for k in _DIM_FLAT]}")

    print(f"\nИтого: {'✅ ОВХ OV1–OV9 зелёные' if all_ok else '❌ есть падения'} ({n[0]} проверок)")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

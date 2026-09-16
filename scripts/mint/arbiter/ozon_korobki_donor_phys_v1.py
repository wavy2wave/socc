#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · КОРОБКИ · 0₽-СБОР ЧЕСТНОЙ ФИЗИКИ ЖИВЫХ КАРТОЧЕК ДОНА (cargo.shop).

Оператор (09-10): габариты упаковки = СЛОЖЕННАЯ коробка + честный вес (чтобы курьеры не
отказывались). Донор — источник истины. Локальные снапшоты (master 26 строк / xlsx 17 гео)
покрывают лишь часть геометрий; живая карточка дона публикует свою таблицу свойств:
«Вес, кг» + «Транспортировочный объем, м³» (+ иногда «Размер упаковки Д*Ш*В, см»).

Орган собирает физику по ЖИВЫМ карточкам дона для всех уник pid из честной сшивки
(korobki_DONOR_STITCH_*.json) → канон korobki_donor_phys_<DATE>.{json,md}.

Только GET (0₽). Наружу ничего не пишем в маркетплейсы. Донор в публичные логи не светим —
артефакт лежит в runtime/ozon_boxes (внутренний), как и прежние дон-артефакты.

Структура карточки (проверено 09-10 на pid 9604030):
  <span class="properties-group__name">Вес, кг:</span>…<div class="properties-group__value …">
      <a href='/catalog/boxes/filter/weight-is-0.623/…'>0.623</a></div>
  <span class="properties-group__name">Транспортировочный объем, м³:</span>… 0.0048
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from html import unescape
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime" / "ozon_boxes"
DATE = date.today().isoformat()

BASE = "https://shop.cargo-avto.ru"
STITCH = RUNTIME / "korobki_DONOR_STITCH_2026-09-10.json"
OUT_JSON = RUNTIME / f"korobki_donor_phys_{DATE}.json"
OUT_MD = RUNTIME / f"korobki_donor_phys_{DATE}.md"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
WORKERS = 6
RETRIES = 4
TIMEOUT = 30

# properties-group name → value (структура карточки дона; между узлами — переводы строк)
_PROP_RE = re.compile(
    r'properties-group__name">([^<]+)</span>\s*</div>\s*'
    r'<div class="properties-group__value-wrap">\s*'
    r'<div class="properties-group__value[^>]*>(.*?)</div>',
    re.DOTALL)


def _strip(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return unescape(re.sub(r"\s+", " ", s)).strip()


def _num(x):
    """'0.623' / ' 0.0048 ' / '1,2' → float|None."""
    if x is None:
        return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(x).replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def fetch(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")


def fetch_card(pid):
    """pid → html|None c ретраями (SSL-таймаут лечится повтором)."""
    url = f"{BASE}/catalog/{pid}/"
    last = None
    for i in range(RETRIES):
        try:
            return fetch(url)
        except Exception as e:                      # noqa: BLE001 — сеть, честно логируем
            last = f"{type(e).__name__}: {e}"
            time.sleep(0.6 * (i + 1))
    return {"_error": last}


def parse_card(pid, html):
    """Карточка дона → честная физика. Ничего не выдумываем: чего нет — того нет."""
    props = {}
    for name, raw in _PROP_RE.findall(html):
        props[_strip(name).rstrip(":").strip()] = _strip(raw)
    title = ""
    m = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    if m:
        title = _strip(m.group(1))
    w = _num(props.get("Вес, кг"))
    tv = _num(props.get("Транспортировочный объем, м³")
              or props.get("Транспортировочный объём, м³"))
    pack = props.get("Размер упаковки Д*Ш*В, см") or props.get("Размер упаковки, см")
    # собранные габариты — прямо с карточки дона (авторитетнее, чем из имени)
    d = _num(props.get("Длина, мм"))
    wd = _num(props.get("Ширина, мм"))
    h = _num(props.get("Высота, мм"))
    dims_mm = [int(x) for x in (d, wd, h)] if (d and wd and h) else None
    # «Кол-во в упаковке, шт.» — дон-вес/объём даны на УПАКОВКУ, а не на 1 короб:
    # на 1 шт делим. Нет поля → считаем упаковку = 1 шт (одна коробка).
    pack_qty = _num(props.get("Кол-во в упаковке, шт.")
                    or props.get("Количество в упаковке, шт.")
                    or props.get("Кол-во в комплекте, шт")) or 1
    pack_qty = int(pack_qty) if pack_qty >= 1 else 1
    return {
        "pid": pid, "title": title,
        "weight_kg": w,
        "transport_m3": tv,
        "pack_qty": pack_qty,
        "weight_kg_single": (w / pack_qty) if w else None,
        "transport_m3_single": (tv / pack_qty) if tv else None,
        "dims_mm": dims_mm,
        "useful_volume_l": _num(props.get("Полезный объем, л")),
        "pack_size_cm": pack or None,
        "mark": props.get("Торговая марка") or props.get("Марка"),
        "type_cardboard": props.get("Тип картона"),
        "form": props.get("Форма коробки"),
        "props_found": sorted(props.keys()),
        "_props": props,
    }


def donor_pids():
    d = json.loads(STITCH.read_text(encoding="utf-8"))
    pids, meta = set(), {}
    for r in d["rows"]:
        dn = r.get("donor")
        if not dn:
            continue
        pid = str(dn["pid"])
        pids.add(pid)
        meta.setdefault(pid, {"title_stitch": dn.get("title"), "status": dn.get("status"),
                              "price": dn.get("price"), "dims_stitch": dn.get("dims")})
    return sorted(pids), meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="0₽-сбор физики живых карточек дона (коробки).")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    pids, meta = donor_pids()
    if args.limit:
        pids = pids[:args.limit]
    print(f"сшитых уник pid дона: {len(pids)} · сбор (0₽ GET, {args.workers} потоков)…")

    phys, errors = {}, {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_card, pid): pid for pid in pids}
        done = 0
        for f in as_completed(futs):
            pid = futs[f]
            html = f.result()
            done += 1
            if isinstance(html, dict):              # ошибка
                errors[pid] = html["_error"]
                print(f"  [{done}/{len(pids)}] {pid} ✗ {html['_error']}")
                continue
            rec = parse_card(pid, html)
            phys[pid] = rec
            ok = "✓" if (rec["weight_kg"] and rec["transport_m3"]) else "⚠"
            print(f"  [{done}/{len(pids)}] {pid} {ok} вес={rec['weight_kg']} кг "
                  f"трансп={rec['transport_m3']} м³ | {rec['title'][:46]}")

    have = sum(1 for r in phys.values() if r["weight_kg"] and r["transport_m3"])
    print(f"\nсобрано: {len(phys)}/{len(pids)} · с весом+трансп.объёмом: {have} · ошибок: {len(errors)}")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "date": DATE, "scope": "физика живых карточек дона cargo.shop (коробки)",
        "source": f"{BASE}/catalog/<pid>/", "rule": "только GET 0₽; чего нет на карточке — не выдумываем",
        "pids_total": len(pids), "have_weight_and_transport": have,
        "for_stitch_meta": meta, "phys": phys, "errors": errors,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    L = [f"# КОРОБКИ · ФИЗИКА ЖИВЫХ КАРТОЧЕК ДОНА · {DATE} · 0₽",
         "",
         f"- собрано карточек: {len(phys)}/{len(pids)} · с «Вес, кг»+«Транспортировочный объём, м³»: **{have}**",
         f"- ошибок сети: {len(errors)}",
         "",
         "| pid | статус | вес, кг | трансп.объём, м³ | марка | карточка дона |",
         "|---|---|---|---|---|---|"]
    for pid in sorted(phys):
        r = phys[pid]
        L.append(f"| {pid} | {meta[pid]['status']} | {r['weight_kg']} | {r['transport_m3']} | "
                 f"{r['mark'] or ''} | {r['title'][:60]} |")
    for pid, e in errors.items():
        L.append(f"| {pid} | ✗ | — | — | — | ошибка: {e} |")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"артефакт: {OUT_JSON.name} (+md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

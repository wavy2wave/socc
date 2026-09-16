#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · КОРОБКИ · РЕАЛЬНЫЕ СВЯЗИ С ДОНОРОМ cargo.shop — «чтобы при заказе не сгореть» (read-only, 0₽).

Оператор 09-15: «донор именно сайт карго шоп — покажи именно связи реальные чтобы при заказе не сгореть».

Что доказываем по КАЖДОЙ ЖИВОЙ карточке кабинета (Express Box …8715):
  1) ССЫЛКА ЖИВА — GET https://shop.cargo-avto.ru/catalog/<pid>/ отвечает 200 (не 404/не редирект).
  2) ТОВАР ТОТ ЖЕ — собранные габариты карточки дона (Длина/Ширина/Высота, мм) сходятся с
     тем размером короба, что записан в НАШЕМ имени. Заголовок дона НЕ арбитр: он дрейфует
     (найдено 09-15 на pid 9604927: title «300*200*200», а таблица свойств 200×200×100 —
     заголовок переписан донором, физика осталась). Арбитр — таблица свойств.
  3) ЕГО МОЖНО КУПИТЬ — «Интернет-магазин: В наличии» (id="s777") vs «Под заказ», + цена сейчас.
  4) ЕГО ХВАТИТ — «Кол-во в упаковке, шт.» дона против нашей партии (карточка «25 шт» = 25 коробов).

Ничего никуда не пишем (наружу — ноль). Только GET 0₽. Артефакты:
  korobki_DONOR_LINKS_<DATE>.{json,md} — связи + улики
  korobki_DONOR_LINKS_<DATE>.txt       — простыня оператору: арт · ссылка · статус
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from html import unescape
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime" / "ozon_boxes"
DATE = date.today().isoformat()

BASE = "https://shop.cargo-avto.ru"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
WORKERS = 6
RETRIES = 4
TIMEOUT = 30

_PROP_RE = re.compile(
    r'properties-group__name">([^<]+)</span>\s*</div>\s*'
    r'<div class="properties-group__value-wrap">\s*'
    r'<div class="properties-group__value[^>]*>(.*?)</div>',
    re.DOTALL)
# ИМЯ ТОВАРА В ТЕЛЕ (<h1>), НЕ <title>. У дона <title> дрейфует: 09-15 на pid 9604927
# <title> = «Картонная коробка №272, 300*200*200 мм», а <h1>/таблица свойств = «Короб №272,
# 200*200*100 мм» (наш размер). Арбитр соответствия — таблица свойств; <title> в отчёт не идёт.
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL)
_S777_RE = re.compile(r'id="s777"[^>]*class="([^"]*)"')
# ЯРУСНАЯ ЦЕНА дона: «от 1 до 99 12.70 ₽ / от 100 до 499 11.80 ₽ / от 500 10.50 ₽».
# Берём ПЕРВЫЙ ярус (цена за 1..N шт) — именно её платим, покупая одну коробку.
# Плоский itemprop="price" НЕ годится: в HTML 20+ цен (похожие товары), порядок нестабилен —
# проба 09-15 дала на одной карточке 532/2990/2850/910 в разных прогонах.
_TIER_RE = re.compile(r"от\s*\d+\s*(?:до\s*\d+\s*)?([\d\s ]*[.,]?\d+)\s*₽")
# ЯРУСЫ С ГРАНИЦАМИ — для определения ЕДИНИЦЫ ПРОДАЖИ (см. sale_unit). Порог ниже: у поштучных
# SKU ярусы крупные (pid 9604362: от 1 до 499 / 500 / 1000), у упаковочных — мелкие
# (pid 9605381 и 9605496: от 1 до 9 / от 10 до 49 / от 50).
_TIER_FULL_RE = re.compile(r"от\s*(\d+)\s*(?:до\s*(\d+)\s*)?[\d\s ]*[.,]?\d+\s*₽")
_TIER_PACK_MAX_LOWER = 60
# Прямое признание дона, сильнее любой эвристики: pid 9605382 — «Единица продажи: 1 уп.
# В упаковке: 25 шт.». Если оно есть, спорить не о чем.
_UNIT_UP_RE = re.compile(r"Единица продажи\s*:?\s*(\d+)\s*уп", re.IGNORECASE)
_MIN_ORDER_RE = re.compile(r"Минимальный заказ\s*:?\s*(\d+)\s*шт", re.IGNORECASE)
_NAME_QTY_RE = re.compile(r"(\d+)\s*шт", re.IGNORECASE)
# ФОЛБЭК ЦЕНЫ. У части карточек дона вовсе нет ярусов, а стоит акционный блок:
# pid 9605728 — «Нам 17 лет! 14.19 ₽ 17 ₽ -17% --> 00 час 00 мин 00 сек 2013 шт».
# _TIER_RE там молчит, и цена уходила в None (5 карточек из 100). Берём первую цену в хвосте.
_ANY_PRICE_RE = re.compile(r"([\d\s\xa0]*[.,]?\d+)\s*₽")
_DIM_NAME_RE = re.compile(
    r"(\d{2,4})(?:[.,](\d))?\s*[*хxXХ×]\s*(\d{2,4})(?:[.,](\d))?\s*[*хxXХ×]\s*(\d{2,4})"
    r"(?:[.,](\d))?\s*(мм|см)?", re.IGNORECASE)
_QTY_NAME_RE = re.compile(r"(\d+)\s*(?:шт|штук|ш\.)", re.IGNORECASE)

# ── ПОРОГ «мелкая тройка = сантиметры» ──────────────────────────────────────
# У дона-коробов мм доходят до 1500, а имена вида «15х15х15», «60х40х40» без единицы —
# это сантиметры (наши карточки так и пишутся). Порог 60: старшая ось ≤60 без единицы
# трактуется как см (×10). Тот же порог в сшивке/resolver'е — иначе орган даёт ложные
# «не тот товар» на ровных местах (проверено 09-15: i1_ex_cargo_119 «15х15х15» vs дон 150×150×150).
_CM_IF_MAX_LE = 60


def _strip(s):
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def visible_text(html):
    """HTML → видимый текст (без script/style). По нему читаем цену/наличие карточки."""
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def _num(x):
    if x is None:
        return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(x).replace(" ", "").replace("\xa0", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def dims_from_name(name):
    """Наше имя → (dims_mm тройка, unit|None). «20х20х10 см» → (100,200,200); «15х15х15» → (150,150,150)."""
    m = _DIM_NAME_RE.search(str(name))
    if not m:
        return None, None
    vals = [float(m.group(1)), float(m.group(3)), float(m.group(5))]
    for i, g in ((0, 2), (1, 4), (2, 6)):
        if m.group(g):
            vals[i] += float("0." + m.group(g))
    unit = (m.group(7) or "").lower() or None
    if unit == "см":
        return tuple(sorted(int(round(v * 10)) for v in vals)), "см"
    if unit == "мм":
        return tuple(sorted(int(round(v)) for v in vals)), "мм"
    # без единицы: старшая ось ≤ 60 → это сантиметры (короб 15×15×15 = 150 мм, не 15 мм)
    if max(vals) <= _CM_IF_MAX_LE:
        return tuple(sorted(int(round(v * 10)) for v in vals)), "см?"
    return tuple(sorted(int(round(v)) for v in vals)), "мм?"


def qty_from_name(name):
    m = _QTY_NAME_RE.search(str(name))
    return int(m.group(1)) if m else 1


def sale_unit(name_body, tail, pack_qty, price):
    """Донор продаёт ПОШТУЧНО или УПАКОВКОЙ? → (единица, шт_в_единице, источник, цена_за_коробку).

    Решает, что реально приедет при выкупе «1»: одна коробка или связка 25/50. Ошибка здесь —
    это переплата в 25–50 раз либо недокомплект заказа.

    Решают СЛОВА ДОНА, в порядке силы:
      1. «Единица продажи: 1 уп.» — прямое признание (pid 9605382).
      2. Сам дон пишет «N шт.» в ИМЕНИ товара, и «Кол-во в упаковке, шт.» = N (pid 9605772
         «Самосборный короб №173, 60*60*30 мм, Т-22 Е, 50 шт.»).
      3. Иначе — поштучно.
    Ничего не заявлено, а сигналы противоречат → «неясно» (не гадаем).

    ЭВРИСТИКА ПО ГРАНИЦАМ ЯРУСОВ ОТВЕРГНУТА: у 9605382 и 9605772 ярусы одинаковы
    («от 1 до 49 / 50 / 100»), но первый — упаковка (доказано прямым признанием), и по ярусам
    второй был ошибочно принят за штучный (130 ₽ вместо 2.60 ₽/коробка). Ярусы оставлены
    только как контекст в отчёте.
    """
    t, n = tail or "", name_body or ""
    q = int(pack_qty or 1)
    per = (lambda v: (price / v if price else None))
    if _UNIT_UP_RE.search(t) and q > 1:
        return "упаковка", q, "прямо: «Единица продажи: 1 уп.»", per(q)
    m = _NAME_QTY_RE.search(n)
    declared = int(m.group(1)) if m else None
    if declared and declared > 1 and q > 1 and declared == q:
        return "упаковка", q, f"дон сам пишет «{q} шт.» в имени, «Кол-во в упаковке» = {q}", per(q)
    if declared and declared > 1 and q > 1 and declared != q:
        return "неясно", None, (f"дон пишет «{declared} шт.» в имени, а «Кол-во в упаковке» = {q} "
                                f"— сколько в единице продажи, не доказано"), None
    return "штука", 1, "дон упаковку не заявляет — цена за штуку", price


def fetch(url):
    last = None
    for i in range(RETRIES):
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers={"User-Agent": UA}), timeout=TIMEOUT) as r:
                return {"ok": True, "status": r.status,
                        "html": r.read().decode("utf-8", "ignore")}
        except urllib.error.HTTPError as e:                 # 404 — это ОТВЕТ, а не сбой сети
            if e.code in (404, 410):
                return {"ok": False, "status": e.code, "http_404": True}
            last = f"HTTP {e.code}"
        except Exception as e:                              # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        time.sleep(0.6 * (i + 1))
    return {"ok": False, "status": None, "error": last}


def parse_donor(pid, html):
    """Живая карточка дона → улики. Чего нет — того нет (не выдумываем)."""
    props = {}
    for name, raw in _PROP_RE.findall(html):
        props[_strip(name).rstrip(":").strip()] = _strip(raw)
    h1 = _H1_RE.search(html)
    name_body = _strip(h1.group(1)) if h1 else ""

    # цена/наличие — из ВИДИМОГО ТЕКСТА, привязавшись к «Арт. <pid>» (там начинается сам товар,
    # до него — шапка/меню). Ярусы цены идут сразу за артикулом.
    tail = ""
    t = visible_text(html)
    i = t.find(f"Арт. {pid}")
    if i >= 0:
        tail = t[i:i + 4000]
    if not tail:                                  # артикул не нашёлся — берём последние 2/3 текста
        tail = t[len(t) // 3:]
    tier = _TIER_RE.search(tail)
    if tier:
        price, price_src = _num(tier.group(1)), "ярус «от … до …»"
    else:
        # акционная карточка — ярусов нет. Правдоподобной считаем цену 0 < v < 100000:
        # без верхней границы регулярка склеивает артикул с ценой («Арт. 9604930 … 16 ₽» → 960493016).
        cand = [v for v in (_num(m.group(1)) for m in _ANY_PRICE_RE.finditer(tail))
                if v and 0 < v < 100000]
        price = cand[0] if cand else None
        price_src = ("акционный блок (ярусов на странице нет)" if cand
                     else "цена на странице не найдена")
    tier_all = [_num(x) for x in _TIER_RE.findall(tail)][:4]

    s = _S777_RE.search(html)
    cls = s.group(1) if s else ""
    avail_cls = None if not cls else ("non-avail" not in cls)
    # наличие: класс блока «Интернет-магазин» + видимый текст (оба сигнала кладём в улики)
    avail_txt = None
    if "Под заказ" in tail[:1200]:
        avail_txt = False
    elif "В наличии" in tail[:1200]:
        avail_txt = True
    available = avail_cls if avail_cls is not None else avail_txt

    d, w, h = (_num(props.get("Длина, мм")), _num(props.get("Ширина, мм")),
               _num(props.get("Высота, мм")))
    dims = tuple(sorted(int(x) for x in (d, w, h))) if all(x for x in (d, w, h)) else None
    pack_qty = _num(props.get("Кол-во в упаковке, шт.")
                    or props.get("Количество в упаковке, шт.")) or 1
    u_unit, u_size, u_src, u_per_box = sale_unit(
        name_body, tail, int(pack_qty) if pack_qty >= 1 else 1, price)
    mo = _MIN_ORDER_RE.search(tail)

    return {
        "name_body": name_body or None, "price": price, "price_tiers": tier_all, "price_source": price_src,
        "available": available, "avail_class": cls or None, "avail_text": avail_txt,
        "dims_mm": list(dims) if dims else None,
        "weight_kg": _num(props.get("Вес, кг")),
        "transport_m3": _num(props.get("Транспортировочный объем, м³")
                             or props.get("Транспортировочный объём, м³")),
        "pack_qty": int(pack_qty) if pack_qty >= 1 else 1,
        "sale_unit": u_unit, "sale_unit_size": u_size, "sale_unit_how": u_src,
        "price_per_box": u_per_box, "min_order": int(mo.group(1)) if mo else None,
        "mark": props.get("Торговая марка") or props.get("Марка"),
    }


def _verdict(our_dims, our_unit, donor):
    """Сходится ли товар дона с нашим? → (вердикт, пояснение).
    Арбитр — таблица свойств дона (Д/Ш/В, мм), НЕ его <title> (у дона заголовок дрейфует)."""
    if donor is None:
        return "СВЯЗЬ МЕРТВА", "страница дона не отвечает"
    dn = donor["dims_mm"]
    if not our_dims:
        return "РАЗМЕР НЕ В ИМЕНИ", "у нашей карточки размера в имени нет — сверять нечем"
    if not dn:
        return "ДОН БЕЗ РАЗМЕРА", "в таблице свойств дона нет Д/Ш/В — сверять нечем"
    a, b = tuple(sorted(our_dims)), tuple(sorted(dn))
    if a == b:
        return "СХОДИТСЯ", f"таблица свойств дона {b} мм = наш размер {a} мм"
    dmax = max(abs(x - y) for x, y in zip(a, b))
    if dmax <= 10:
        return "СХОДИТСЯ ±10мм", f"дон {b} vs наш {a} мм (макс. расхождение {dmax} мм)"
    if dmax <= 30:
        return "БЛИЗКО ±30мм", (f"дон {b} vs наш {a} мм (макс. расхождение {dmax} мм) — "
                                f"НЕ тот же короб, только похожий размер")
    return "НЕ ТОТ ТОВАР", f"дон {b} мм ≠ наш {a} мм (макс. расхождение {dmax} мм)"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Реальные связи коробок с донором cargo.shop (0₽ read-only).")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--attrs", default=None, help="снимок живых атрибутов кабинета")
    args = ap.parse_args(argv)

    attrs_path = Path(args.attrs).resolve() if args.attrs else None
    if attrs_path is None:
        hits = sorted(RUNTIME.glob("korobki_LIVE_ATTRS_*.json"))
        attrs_path = hits[-1] if hits else None
    if not attrs_path or not attrs_path.exists():
        print("нет снимка живых атрибутов — сначала ozon_korobki_edit_lists_v1.py (0₽)"); return 2
    # снимок живых атрибутов бывает двух форм: плоский {offer_id: {...}} и обёрнутый {"live": {...}}
    raw = json.loads(attrs_path.read_text(encoding="utf-8"))
    live = raw.get("live") if isinstance(raw, dict) and isinstance(raw.get("live"), dict) else raw
    live = {k: v for k, v in (live or {}).items() if isinstance(v, dict)}

    fold_hits = sorted(RUNTIME.glob("korobki_FOLDED_*.json"))
    if not fold_hits:
        print("нет манифеста резолвера — сначала ozon_korobki_folded_resolver_v1.py (0₽)"); return 2
    rep = json.loads(fold_hits[-1].read_text(encoding="utf-8"))
    metas = {m["art"]: m for m in rep.get("metas", [])}
    # HELD-карточки тоже имеют донора — просто их физика не вывелась. Без них связь была бы
    # «донор не записан» на ровном месте (15 живых карточек — ровно те, что ушли в HELD).
    for h in rep.get("held_list", []):
        metas.setdefault(h["art"], h)

    rows = []
    for art, v in sorted(live.items()):
        m = metas.get(art) or {}
        name = v.get("name") or m.get("name") or ""
        pid = str(m.get("donor_pid") or "")
        if not pid or pid == "None":
            rows.append({"art": art, "name": name, "price": None, "donor_pid": None,
                         "donor_url": None, "verdict": "ДОНОР НЕ ЗАПИСАН",
                         "note": "у карточки нет донора в манифесте — связь показать нечем"})
            continue
        rows.append({"art": art, "name": name, "qty": qty_from_name(name),
                     "donor_pid": pid, "donor_url": f"{BASE}/catalog/{pid}/",
                     "donor_status_09_08": m.get("donor_status"),
                     "folded": m.get("folded"), "assembled_dims": m.get("assembled_dims"),
                     "our_dims": list(dims_from_name(name)[0]) if dims_from_name(name)[0] else None,
                     "our_unit": dims_from_name(name)[1]})
    if args.limit:
        rows = rows[:args.limit]

    pids = sorted({r["donor_pid"] for r in rows if r["donor_pid"]})
    print(f"живых карточек: {len(rows)} · уник. донорских pid: {len(pids)} · сбор живых страниц (0₽ GET)…")

    page, fails = {}, {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch, f"{BASE}/catalog/{p}/"): p for p in pids}
        done = 0
        for f in as_completed(futs):
            p = futs[f]
            res = f.result()
            done += 1
            if not res.get("ok"):
                fails[p] = res
                print(f"  [{done}/{len(pids)}] {p} ✗ {res.get('error') or res.get('status')}")
                continue
            page[p] = parse_donor(p, res["html"])
            z = page[p]
            print(f"  [{done}/{len(pids)}] {p} ✓ {z['dims_mm']} мм · "
                  f"{'В наличии' if z['available'] else 'НЕ в наличии' if z['available'] is False else '?'}"
                  f" · {z['price']}₽")

    for r in rows:
        p = r.get("donor_pid")
        if not p:
            continue
        r["donor_live"] = page.get(p)
        r["donor_error"] = (fails.get(p) or {}).get("error") or \
                           (f"HTTP {fails[p]['status']}" if p in fails else None)
        r["verdict"], r["note"] = _verdict(
            tuple(r["our_dims"]) if r.get("our_dims") else None, r.get("our_unit"), page.get(p))

    vc = Counter(r["verdict"] for r in rows)
    pack_rows = [r for r in rows if (r.get("donor_live") or {}).get("sale_unit") == "упаковка"]
    avail = sum(1 for r in rows if (r.get("donor_live") or {}).get("available") is True)
    dead = [r for r in rows if r["verdict"] == "СВЯЗЬ МЕРТВА"]
    wrong = [r for r in rows if r["verdict"] == "НЕ ТОТ ТОВАР"]

    print(f"\nСВЯЗИ: {dict(vc)}")
    print(f"  донор «В наличии»: {avail}/{len(rows)} · мёртвых ссылок: {len(dead)} · "
          f"не тот товар: {len(wrong)}")
    print(f"  ЕДИНИЦА ПРОДАЖИ: упаковками {len(pack_rows)} · поштучно {len(rows) - len(pack_rows)}")
    for r in pack_rows:
        z = r["donor_live"]
        print(f"    {r['art']} — упак. {z['sale_unit_size']} шт · {z['price']}₽ за упаковку "
              f"→ {z['price_per_box']:.2f}₽/коробка ({z['sale_unit_how']})")

    out = {"date": DATE, "scope": "живые карточки коробок → реальный товар дона cargo.shop",
           "rule": "арбитр связи = таблица свойств дона (Д/Ш/В, мм), НЕ его заголовок (заголовки дрейфуют); "
                   "ссылка = https://shop.cargo-avto.ru/catalog/<pid>/",
           "attrs_snapshot": attrs_path.name, "folded_manifest": fold_hits[-1].name,
           "counts": {"live": len(rows), "uniq_pid": len(pids), "instock": avail,
                      "dead": len(dead), "wrong": len(wrong),
                      "unit_pack": len(pack_rows), "unit_piece": len(rows) - len(pack_rows), **vc},
           "sale_unit_rule": "прямое «Единица продажи: 1 уп.» > эвристика по границам ярусов "
                             "(мелкие 1/10/50 = цена за упаковку; крупные 1/500/1000 = за штуку) "
                             "> «Кол-во в упаковке, шт.»",
           "rows": rows}
    (RUNTIME / f"korobki_DONOR_LINKS_{DATE}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    L = [f"# КОРОБКИ · РЕАЛЬНЫЕ СВЯЗИ С ДОНОРОМ cargo.shop · {DATE} · 0₽", "",
         f"- живых карточек: **{len(rows)}** · уник. донорских pid: **{len(pids)}**",
         f"- донор «В наличии»: **{avail}/{len(rows)}** · мёртвых ссылок: **{len(dead)}** · "
         f"«не тот товар»: **{len(wrong)}**",
         f"- арбитр связи: таблица свойств дона Д/Ш/В (мм). Заголовок дона НЕ арбитр — он дрейфует.",
         "", "## По вердиктам", ""]
    for k, c in vc.most_common():
        L.append(f"- **{k}**: {c}")
    L += ["", "## Связи (арт → реальный товар покупки)", "",
          "| арт | наша карточка | донор | имя товара дона (тело карточки) | таблица дона, мм | "
          "ед. продажи | цена | ₽/коробка | наличие | вердикт |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        z = r.get("donor_live") or {}
        url = r.get("donor_url") or "—"
        link = f"[{r['donor_pid']}]({url})" if r.get("donor_pid") else "—"
        pv = z.get("price")
        pb = z.get("price_per_box")
        L.append(f"| `{r['art']}` | {str(r['name'])[:56]} | {link} | "
                 f"{str(z.get('name_body') or '—')[:52]} | "
                 f"{z.get('dims_mm') or '—'} | "
                 f"{('упак. ' + str(z.get('sale_unit_size')) + ' шт') if z.get('sale_unit') == 'упаковка' else ('шт' if z else '—')} | "
                 f"{('%.2f' % pv).rstrip('0').rstrip('.') + '₽' if pv is not None else '—'} | "
                 f"{('**%.2f**' % pb).rstrip('0').rstrip('.') + '₽' if pb is not None else '—'} | "
                 f"{'🟢 В наличии' if z.get('available') else ('🔴 нет' if z.get('available') is False else '—')} | "
                 f"{r['verdict']} |")
    (RUNTIME / f"korobki_DONOR_LINKS_{DATE}.md").write_text("\n".join(L), encoding="utf-8")

    T = [f"# СВЯЗИ С ДОНОРОМ cargo.shop · {DATE} · живых {len(rows)}", "",
         f"# донор «В наличии» {avail}/{len(rows)} · мёртвых {len(dead)} · не тот товар {len(wrong)}", ""]
    for r in rows:
        z = r.get("donor_live") or {}
        T.append(f"{r['art']}\t{'🟢' if z.get('available') else ('🔴' if z.get('available') is False else '❔')}"
                 f"\t{z.get('price') if z.get('price') is not None else '—'}₽"
                 f"\t{'УПАК '+str(z.get('sale_unit_size'))+'шт' if z.get('sale_unit')=='упаковка' else ('шт' if z else '—')}"
                 f"\t{z.get('price_per_box') if z.get('price_per_box') is not None else '—'}₽/кор"
                 f"\tдон {z.get('dims_mm') or '—'}\tнаш {r.get('our_dims') or '—'} ({r.get('our_unit') or '?'})"
                 f"\t{r['verdict']}\t{r.get('donor_url') or '—'}\t{str(r['name'])[:60]}")
    (RUNTIME / f"korobki_DONOR_LINKS_{DATE}.txt").write_text("\n".join(T) + "\n", encoding="utf-8")

    print(f"\nартефакты: korobki_DONOR_LINKS_{DATE}.json / .md / .txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

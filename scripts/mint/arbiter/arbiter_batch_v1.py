#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ARBITER BATCH V1 — ОГРАНИЧЕННЫЙ прогон охоты по категориям (M5, dry, 0₽).

ЗАЧЕМ: read-плоскость доказана поштучно (M1-M4 зелёные), но оператору нужен СРЕЗ —
какие товары реально выживают с гарантией плюса после комиссии 53% + доставки ОТДЕЛЬНОЙ
строкой (net_coeff 0.298, ₽325 — ФАКТ кабинета Озон, ozon_truth_v1). Плоскость СБЫТА —
Яндекс.Маркет Экспресс; экономика Озона — временный эталон, пока Фаза B1 не даст реальные
тарифы Экспресса. Этот файл гоняет N категорий за проход и складывает PROVEN-связки.

ЧТО ДЕЛАЕТ (за проход):
  для каждой категории:  SCOUT(WB) → уникализация → gap.prove(pricing=...) → PROVEN?
  итог: ранжированный по ЧЕСТНОЙ прибыли список + JSON-слепок в MEMORY_WAVE.

ГРАНИЦЫ ЧЕСТНОСТИ:
  • НЕ демон: один вызов = один ограниченный проход (вечность — снаружи, руками/cron).
  • НЕ публикует: ничего не пишет в Озон, ключи не нужны, 0₽ двигается.
  • PROVEN здесь = доказанная ГИПОТЕЗА (спрос+маржа+закон+честная цена), НЕ доход.
    Реальный ₽ — только verified в revenue_ledger (стадия SETTLE).
  • Прибыль считается ПОСЛЕ комиссии Озон 53% (net_coeff 0.298) и доставки ₽325 отдельной
    строкой — то есть то, что реально останется оператору, а не наивная наценка.

ЩАДИМ ИСТОЧНИК: пауза между категориями (WB троттлит; гард релевантности в suppliers/base_v1
режет fallback-мусор, но лучше не доводить). Каждая стадия fail-soft: одна категория упала —
проход живёт дальше.

CLI:
  python3 arbiter_batch_v1.py                          # спектр по умолчанию, срез в терминал
  python3 arbiter_batch_v1.py --limit 6 --delivery 120
  python3 arbiter_batch_v1.py --categories "грелка для рук,точилка для ножей"
  python3 arbiter_batch_v1.py --json                   # машиночитаемо
"""
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent          # SOCC/scripts/mint/arbiter
MINT = HERE.parent                               # SOCC/scripts/mint
ROOT = MINT.parent.parent                        # SOCC
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import supplier_scout_v1 as scout                # noqa: E402
import gap_v1 as gap                             # noqa: E402
import uniqueizer_v1 as uniq                     # noqa: E402
import socc_mint_prospect_v1 as prospector       # noqa: E402  (единственный источник констант)

OUT_DIR = ROOT / "MEMORY_WAVE/reports/mint/arbiter"

# СПЕКТР ПО ЦЕНЕ — проверяем гипотезу живого прогона: дешёвый commodity (дождевик ₽111) даёт
# ноль/минус после комиссии 53% + фикс-доставки ₽325, а закуп ₽700+ может оставить плюс. Берём
# три ценовых эшелона, чтобы срез показал ГДЕ проходит граница выживания под честными константами.
DEFAULT_CATEGORIES = [
    # Ищем не «дорогой товар», а БОЛЬШОЙ МНОЖИТЕЛЬ на дешёвом закупе (логика коробки 63→1700).
    # Признаки такой ниши: копеечное сырьё, но покупают по НУЖДЕ/срочности; расходники, которые
    # берут регулярно; товары, где важна форма подачи (поштучно/набор), а не сам предмет.
    "органайзер для кабелей", "точилка для ножей", "держатель для телефона",
    "крючки самоклеящиеся", "силиконовые формы для выпечки", "сетка для стирки белья",
    "антисептик для рук", "щетка для одежды", "коврик для мыши",
    "чехол для чемодана", "лента светодиодная", "фильтр для воды",
    "перчатки хозяйственные", "мешки для пылесоса", "стельки ортопедические",
]

DEFAULT_DELIVERY = prospector.DELIVERY_NET     # факт кабинета (ozon_truth_v1, 2026-08-05)
DEFAULT_HOUSE = "RAINO"      # бренд-дом для уникализации (свой EAN + бренд → Озон не свяжет с WB)
PAUSE_SEC = 2.2              # щадим публичный WB между категориями

# СТРАТЕГИЯ СОЗДАТЕЛЯ (его слова, его цифры, правлено после ДОЗНАНИЯ кабинета): «закуп
# минимальный — профит максимальный». Живой пример: картонная коробка 600×400×400 —
# закуп ₽63, продажа ₽1700 (27x), чистыми +₽119 (после комиссии 53% + доставки ₽325).
# Почему это работает, а 5x на дорогом товаре — нет:
#   • Озон удерживает 53% комиссией + ₽325 доставка, поэтому на ДЕШЁВОМ товаре нужен БОЛЬШОЙ
#     множитель, чтобы после всех издержек что-то осталось: 10x от ₽63 даёт минус, 27x даёт +₽119.
#   • Большой множитель возможен ТОЛЬКО там, где Озон не с чем сравнивать (голубая вода или
#     несвязываемая карточка). Коробки — commodity, НО создатель продаёт ПОШТУЧНО, когда все
#     продают упаковкой по 10-20. Уникальна ФОРМА ПРЕДЛОЖЕНИЯ → эталона нет → цена наша.
#   • Дешёвый закуп = мало капитала на единицу = можно держать широкий ассортимент.
# ПОТОЛОК РЫНКА — защита от «честной прибыли на мёртвой цене». Гарантия плюса НЕ знает, сколько
# покупатель готов заплатить: 15x от ₽398 даёт +₽1591 на бумаге и ноль продаж в жизни. Берём
# максимум розницы категории на WB × factor. Тройка — из практики создателя: его коробка ₽1700
# против поштучной розницы ~₽500-600 ≈ 3x рынка, и она ПРОДАЁТСЯ. Выше — уже не рынок, а фантазия.
MARKET_CEILING_FACTOR = 3.0

# ЗАКОН КОРОБКИ — главный урок живого прогона (2026-08-05, правлено после ДОЗНАНИЯ кабинета).
# Считаем деньги создателя честно (комиссия 53%, net_coeff 0.298, доставка ₽325 отдельно):
#   коробка:  цена ₽1700 → Озон отдаёт 29.8% = ₽507 → −₽63 закуп − ₽325 доставка = +₽119
#   точилка:  цена ₽1135 → Озон отдаёт 29.8% = ₽338 → −₽227 закуп − ₽325 доставка = −₽214 (минус!)
# Разница НЕ в множителе (27x против 5x), а в ДОЛЕ ЗАКУПА В ЧЕКЕ: у коробки закуп 3.7% цены,
# у точилки — 20%. Озон забирает 53% комиссией, ПЛЮС доставка ₽325 — фиксированный удар.
# Поэтому оставшихся ~30% должно хватить и на закуп, и на доставку, и на прибыль.
# Отсюда рабочий критерий: закуп ≤ ~8% реализуемой цены (у коробки 3.7% — с запасом).
# Это НЕ про дешёвый товар, а про товар, где почти вся цена — ценность подачи, а не сырьё.
COST_SHARE_TARGET = 0.08     # цель: закуп ≤8% цены продажи (зона коробки)
COST_SHARE_MAX = 0.15        # предел: выше 15% — после Озона и доставки остаются копейки

COST_CAP_WAVE1 = 500.0       # 1-я волна: закуп до ₽500 (мягкий потолок; до ₽700 допустимо)
COST_CAP_HARD = 700.0        # жёсткий потолок закупа — выше капитал на единицу не оправдан
TARGET_MULTIPLE_HUNT = 10.0  # цель охоты: 10x (не 5x) — «сладко», по слову создателя
STRETCH_MULTIPLE = 15.0      # растяжка: пробуем 15x там, где карточка несвязываема


def _now():
    return datetime.now(timezone.utc).isoformat()


def run_batch(categories=None, city="msk", limit=4, delivery=DEFAULT_DELIVERY,
              house_brand=DEFAULT_HOUSE, pause=PAUSE_SEC, on_progress=None,
              cost_cap=COST_CAP_HARD):
    """ОДИН ограниченный проход по категориям (НЕ демон). Возвращает срез с ранжированным топом.

    on_progress(dict) — колбэк после каждой категории (для живой печати в CLI).
    Ранг — по ЧЕСТНОЙ прибыли (после комиссии+буста Озон и доставки), а не по наценке.
    """
    cats = list(categories or DEFAULT_CATEGORIES)
    started = _now()
    per_category = []
    winners = []
    for i, cat in enumerate(cats):
        if i and pause:
            time.sleep(pause)                    # щадим публичный WB
        r = hunt_category(cat, city=city, limit=limit, delivery=delivery,
                          house_brand=house_brand, cost_cap=cost_cap)
        per_category.append(r)
        winners.extend(r["winners"])
        if on_progress:
            on_progress(r)

    # Ранг по PROFIT-PER-ROUBLE, а не по абсолютной прибыли: ₽432 с рубля закупа ₽63 (коробка,
    # 6.9₽/₽) сильнее, чем ₽70 с закупа ₽227 (точилка, 0.3₽/₽) — тот же капитал даёт больше оборотов.
    winners.sort(key=lambda w: (w.get("profit_per_rouble") or 0), reverse=True)
    scanned = sum(r["scanned"] for r in per_category)
    proven = sum(r["proven"] for r in per_category)
    failed = [r["category"] for r in per_category if r["error"]]
    dry_cats = [r["category"] for r in per_category if not r["error"] and r["proven"] == 0]

    return {
        "ts": started, "finished_at": _now(), "city": city, "limit_per_category": limit,
        "delivery": delivery, "house_brand": house_brand,
        "categories_run": len(cats), "scanned": scanned, "proven": proven,
        "rejected": scanned - proven,
        "categories_failed": failed, "categories_zero_proven": dry_cats,
        "per_category": per_category, "winners": winners,
        "honesty": ("PROVEN = доказанная ГИПОТЕЗА (спрос+маржа+закон+честная цена после комиссии "
                    "53% + доставки ₽325, факт кабинета Озон). Это НЕ доход. Реальный ₽ — только "
                    "verified в revenue_ledger. Плоскость СБЫТА — Яндекс.Маркет Экспресс; Озон — "
                    "временный эталон экономики, заменяется реальными тарифами Экспресса в Фазе B1."),
    }


def save_snapshot(batch, out_dir=None):
    """Слепок прохода в MEMORY_WAVE (JSON). Возвращает путь. fail-soft: беда с ФС → None."""
    try:
        d = Path(out_dir) if out_dir else OUT_DIR
        d.mkdir(parents=True, exist_ok=True)
        stamp = str(batch.get("ts", "")).replace(":", "").replace("-", "")[:15] or "batch"
        path = d / f"proven_batch_{stamp}.json"
        path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)
    except Exception:
        return None


def echelon(cost):
    """Ценовой эшелон закупа — для среза «где проходит граница выживания»."""
    c = float(cost or 0)
    if c < 250:
        return "дешёвый (<₽250)"
    if c < 700:
        return "средний (₽250-700)"
    return "дорогой (₽700+)"


def print_progress(result, idx, total):
    """Живая печать прогресса категории (вызывается колбэком)."""
    cat = result["category"]
    if result["error"]:
        print(f"  [{idx}/{total}] «{cat}»: ⚠ {result['error']}")
    else:
        print(f"  [{idx}/{total}] «{cat}»: {result['scanned']} кандидатов → "
              f"{result['proven']} PROVEN, {result['rejected']} отказано"
              f"{f', {result['skipped_too_pricey']} дороже потолка' if result.get('skipped_too_pricey') else ''}")


def print_report(batch, top_k=10, json_out=False):
    """Отчёт для оператора (человекочитаемо или --json)."""
    if json_out:
        print(json.dumps(batch, ensure_ascii=False, indent=2))
        return

    w = batch["winners"][:top_k]
    print("=" * 86)
    print(f"  ОХОТА ARBITER · {batch['categories_run']} категорий · потолок закупа ₽{COST_CAP_HARD:.0f}")
    print("=" * 86)
    print(f"  Прогнано: {batch['scanned']} товаров → {batch['proven']} PROVEN с честным плюсом")
    print(f"  Брак/тонкая маржа: {batch['rejected']} кандидатов")
    if batch["categories_failed"]:
        print(f"  Упали: {', '.join(batch['categories_failed'])}")
    if batch["categories_zero_proven"]:
        print(f"  Ноль PROVEN (тонкие/matchable): {', '.join(batch['categories_zero_proven'])}")
    print("─" * 86)
    print(f"  ТОП-{len(w)} по ЧЕСТНОЙ прибыли (после комиссии 53% + доставка ₽{batch['delivery']:.0f}):")
    print("─" * 86)
    for i, p in enumerate(w, 1):
        ppr = p.get("profit_per_rouble") or 0
        strg = p.get("demand_strength") or 0
        cat = (p.get("category") or "")[:18]
        name = (p.get("name") or "")[:36]
        sr = p.get("spread_ratio")
        sr_s = f"{sr:>4.1f}x" if sr else " n/a"
        cvm = p.get("cost_vs_market_max")
        cvm_s = f"{cvm * 100:>4.1f}%" if cvm is not None else "  n/a"
        zone = "🎯" if p.get("box_zone") else "  "
        print(f"  {zone}{i:>2}. +₽{p['profit_net']:>6.1f} | закуп ₽{p['cost_buy']:<5.0f} → ₽"
              f"{(p.get('price_sell') or 0):<6.0f} | разброс {sr_s} | закуп={cvm_s} от верха | "
              f"{ppr:>4.1f}₽/₽ | спрос[{strg:>3}] | [{cat:<16}] {name[:26]}")
    print("─" * 86)
    wide = [x for x in batch["winners"] if (x.get("spread_ratio") or 0) >= 5.0]
    print(f"  МЕХАНИЗМ КОРОБКИ (что на самом деле даёт маржу):")
    print(f"    Доля закупа в чеке = 1/наценка — это НЕ сигнал, а та же наценка другими словами.")
    print(f"    Настоящий рычаг — РАЗБРОС ЦЕН В КАТЕГОРИИ: берём НИЗ разброса и продаём в форме,")
    print(f"    за которую платят как за ВЕРХ. Коробки: штука ₽63 в категории, где пачки по ₽600.")
    print(f"    Потолок = макс.цена × {MARKET_CEILING_FACTOR:.0f}, значит 15x проходит при закупе ≤20% от верха.")
    print(f"    Категорий с разбросом ≥5x среди победителей: {len(wide)} из {len(batch['winners'])}")
    print("=" * 86)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--categories", help="Категории через запятую (иначе спектр по умолчанию)")
    p.add_argument("--city", default="msk", help="Регион WB (msk/spb/...), по умолчанию msk")
    p.add_argument("--limit", type=int, default=4, help="Кандидатов на категорию (щадим WB), по умолчанию 4")
    p.add_argument("--delivery", type=float, default=DEFAULT_DELIVERY,
                   help=f"Стоимость доставки ₽ (по умолчанию {DEFAULT_DELIVERY:.0f})")
    p.add_argument("--cost-cap", type=float, default=COST_CAP_HARD,
                   help=f"Потолок закупа ₽ («закуп минимальный»), по умолчанию {COST_CAP_HARD:.0f}")
    p.add_argument("--house-brand", default=DEFAULT_HOUSE,
                   help=f"Бренд-дом для уникализации (по умолчанию {DEFAULT_HOUSE})")
    p.add_argument("--json", action="store_true", help="Машиночитаемый JSON вместо отчёта")
    p.add_argument("--top", type=int, default=10, help="Топ-K в отчёт (по умолчанию 10)")
    args = p.parse_args()

    cats = [c.strip() for c in args.categories.split(",")] if args.categories else None
    cats_list = cats or DEFAULT_CATEGORIES
    idx = 0

    def on_progress(res):
        nonlocal idx
        idx += 1
        if not args.json:
            print_progress(res, idx, len(cats_list))

    if not args.json:
        print(f"Стартуем охоту: {len(cats_list)} категорий, закуп до ₽{args.cost_cap:.0f}, "
              f"доставка ₽{args.delivery:.0f}, пауза {PAUSE_SEC}с...")
        print()

    batch = run_batch(categories=cats, city=args.city, limit=args.limit,
                      delivery=args.delivery, house_brand=args.house_brand,
                      cost_cap=args.cost_cap, on_progress=on_progress)

    if not args.json:
        print()
    print_report(batch, top_k=args.top, json_out=args.json)

    snap_path = save_snapshot(batch)
    if snap_path and not args.json:
        print(f"\nСлепок сохранён: {snap_path}")
    return 0 if batch["proven"] > 0 else 1


def price_spread(cands):
    """Разброс цен внутри категории — ГЛАВНЫЙ сигнал охоты (урок 2026-08-05).

    Почему разброс, а не «дешевизна»: доля закупа в чеке = 1/множитель (цена = закуп×множитель),
    то есть это НЕ независимая метрика. Реальное ограничение — потолок рынка (макс цена × 3).
    15x проходит ⟺ закуп×15 ≤ макс×3 ⟺ закуп ≤ 20% макс. Отсюда: нужен ДЕШЁВЫЙ товар В КАТЕГОРИИ,
    ГДЕ ЕСТЬ ДОРОГИЕ — тогда потолок высокий, а закуп низкий.

    Это механизм создателя дословно: категория «коробки» держит и упаковки по ₽600, и штуку за ₽63.
    Он берёт НИЗ разброса и продаёт в форме, за которую платят как за ВЕРХ (поштучно вместо пачки).
    Категория с плоскими ценами (все по ₽150) такого рычага не даёт — потолок низкий у всех.

    Возвращает {min, max, ratio, spread_ok}: ratio = max/min (во сколько раз верх выше низа).
    """
    prices = []
    for c in cands or []:
        try:
            v = float(c.get("cost") or 0)
        except Exception:
            continue
        if v > 0:
            prices.append(v)
    if not prices:
        return {"min": None, "max": None, "ratio": None, "spread_ok": False}
    lo, hi = min(prices), max(prices)
    ratio = round(hi / lo, 2) if lo > 0 else None
    # ratio ≥ 5 → низ категории можно тянуть к верху (у коробок ₽63 против ₽600 ≈ 9.5x)
    return {"min": lo, "max": hi, "ratio": ratio, "spread_ok": bool(ratio and ratio >= 5.0)}


def market_ceiling(cands, factor=MARKET_CEILING_FACTOR):
    """Потолок реализуемой цены по РЫНКУ категории (прокси спроса, не фантазия).

    Проблема, которую это лечит: движок цены гарантирует ПЛЮС, но ничего не знает о том, сколько
    покупатель вообще готов заплатить за такую вещь. Без потолка лестница множителей всегда берёт
    верх (15x), и точилка закупом ₽398 «продаётся» за ₽5970 — прибыль честная, спрос нулевой.

    Берём максимум розницы этой категории на WB (реальные цены, по которым люди ПОКУПАЮТ) и
    умножаем на factor — запас на уникализацию/подачу/бренд. Логика создателя: его коробка ₽1700
    против поштучной розницы ~₽500-600 — примерно 3x рынка, и это РАБОТАЕТ. Выше — уже не рынок.

    Пусто/битые цены → None (потолка нет, честная деградация: решает только гарантия плюса).
    """
    prices = []
    for c in cands or []:
        try:
            v = float(c.get("cost") or 0)
        except Exception:
            continue
        if v > 0:
            prices.append(v)
    if not prices:
        return None
    return round(max(prices) * float(factor), 2)


def best_multiple(cand, uniq_report, delivery, min_mult=3.0, price_ceiling=None,
                  ladder=(STRETCH_MULTIPLE, TARGET_MULTIPLE_HUNT, 7.0, 5.0, 3.0)):
    """Максимальный множитель, который ЕЩЁ проходит честный гейт И потолок рынка (лестница вниз).

    Логика создателя «профит максимальный»: не фиксируем 5x, а берём САМУЮ ВЫСОКУЮ наценку,
    которую движок цены признаёт законной и прибыльной. Пробуем 15x → 10x → 7x → 5x → 3x и
    останавливаемся на первой прошедшей.

    price_ceiling (₽) — потолок РЕАЛИЗУЕМОЙ цены по рынку категории. Ступени выше потолка
    пропускаем ДО вызова движка: 15x бывает честным по прибыли и мёртвым по спросу.
    None → потолка нет (решает только гарантия плюса).

    Возвращает (verdict_dict, price_dict) первой прошедшей ступени, иначе последней (для причины).
    """
    last = (None, None)
    cost = float(cand.get("cost") or 0)
    for mult in ladder:
        if mult < min_mult:
            break
        if price_ceiling and cost > 0 and cost * mult > float(price_ceiling):
            continue                      # выше рынка — не продастся, даже если прибыль «честная»
        try:
            v = gap.prove(cand, coverage=None,
                          pricing={"delivery": delivery,
                                   "uniqueize_report": uniq_report,
                                   "target_multiple": mult,
                                   "min_multiple": min_mult})
        except Exception:
            continue
        last = (v, v.get("price") or {})
        if v.get("verdict") == "PROVEN":
            return last
    return last


def hunt_category(category, city="msk", limit=4, delivery=DEFAULT_DELIVERY,
                  house_brand=DEFAULT_HOUSE, profit_target=600, min_profit=200,
                  cost_cap=COST_CAP_HARD):
    """Одна категория: SCOUT → потолок закупа → уникализация → МАКС честная наценка. fail-soft.

    cost_cap — стратегия «закуп минимальный»: товары дороже потолка пропускаем (капитал на
    единицу не оправдан). Возвращает {category, scanned, proven, rejected, winners[], error}.
    Любая беда (сеть/парс/цена) → error заполнен, ПРОХОД НЕ ПАДАЕТ (вечная машина живёт).
    """
    out = {"category": category, "scanned": 0, "proven": 0, "rejected": 0,
           "skipped_too_pricey": 0, "market_ceiling": None, "winners": [], "error": None}
    try:
        res = scout.scout("wildberries", query=category, city=city, limit=limit,
                          profit_target=profit_target, min_profit=min_profit)
        cands = res.get("candidates", [])
    except Exception as e:
        out["error"] = f"SCOUT упал: {type(e).__name__}: {e}"
        return out

    out["scanned"] = len(cands)
    # Потолок реализуемой цены считаем по ВСЕЙ выдаче категории (включая товары дороже нашего
    # потолка закупа) — это самая честная картина рынка, доступная до публикации.
    ceiling = market_ceiling(cands)
    out["market_ceiling"] = ceiling
    # Разброс цен категории — сигнал «есть ли куда тянуть низ» (механизм коробки создателя).
    spread = price_spread(cands)
    out["spread"] = spread
    for c in cands:
        cost = float(c.get("cost") or 0)
        if cost <= 0 or cost > float(cost_cap):
            out["skipped_too_pricey"] += 1      # «закуп минимальный» — дорогое не берём
            continue
        try:
            rep = uniq.uniqueize({"sku": c.get("sku"), "name": c.get("name"),
                                  "brand": c.get("brand") or "NoName", "cost": cost},
                                 house_brand=house_brand)
            priced, p = best_multiple(c, rep["law_report"], delivery, price_ceiling=ceiling)
        except Exception:
            out["rejected"] += 1                # битый кандидат не роняет категорию
            continue
        if not priced or priced.get("verdict") != "PROVEN":
            out["rejected"] += 1
            continue
        net = p.get("profit_net") or 0
        sell = float(p.get("price_sell") or 0)
        # ЗАКОН КОРОБКИ: доля закупа в чеке — главный предиктор того, останется ли прибыль
        # после комиссии 53% + доставки ₽325. Коробка создателя ≈3.7%, точилка ≈20%.
        cost_share = round(cost / sell, 4) if sell > 0 else None
        out["proven"] += 1
        out["winners"].append({
            "category": category,
            "name": c.get("name", ""),
            "sku": c.get("sku"),
            "url": c.get("url"),
            "cost_buy": cost,
            "price_sell": p.get("price_sell"),
            "profit_net": net,
            "markup": p.get("recommended_markup"),
            # ключевая метрика создателя: сколько чистых ₽ приносит КАЖДЫЙ рубль закупа
            "profit_per_rouble": round(net / cost, 2) if cost > 0 else None,
            # ВНИМАНИЕ: cost_share = 1/множитель (цена=закуп×множитель) — это НЕ независимый сигнал,
            # а другая запись наценки. Держим для читаемости отчёта, но ранг по нему НЕ строим.
            "cost_share": cost_share,
            "box_zone": bool(cost_share is not None and cost_share <= COST_SHARE_TARGET),
            # НАСТОЯЩИЙ сигнал: во сколько раз верх категории выше низа + где в разбросе наш закуп.
            # Низ дешёвой категории с дорогим верхом = зона коробки создателя (₽63 среди ₽600).
            "spread_ratio": spread.get("ratio"),
            "cost_vs_market_max": (round(cost / spread["max"], 3)
                                   if spread.get("max") else None),
            "strategy": p.get("strategy"),
            "market_ceiling": ceiling,
            "demand_strength": (c.get("demand_signal") or {}).get("strength", 0),
            "collision_risk": ((rep.get("law_report") or {}).get("collision") or {}).get("risk"),
        })
    return out


if __name__ == "__main__":
    sys.exit(main())

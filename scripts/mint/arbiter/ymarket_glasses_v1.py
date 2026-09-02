#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET GLASSES V1 — «ОЧКИ» органа ARBITER: глядя на сайт, СРАЗУ видеть деньги (чистая функция, 0₽).

ЗАЧЕМ (слова оператора). «Нам нужен фильтр-очки — очки моей системы. Она смотрит на сайт, видит
реальные цены магазина и СРАЗУ, без лишних токенов/действий, видит: по какой цене продаём, какой
profit ожидаем. Жадно охотимся за нужными товарами. Мы не теряем ни при каких условиях.»

ЧТО ЭТО. Обратная задача к ЦЕНОВИКУ (ymarket_role_pricer): тот берёт ЦЕНУ → проверяет пол маржи.
Очки берут ЗАКУПКУ (реальную розницу донора = наша цена выкупа при заказе) → ВЫВОДЯТ цену продажи
под ФИКСИРОВАННЫЙ целевой profit → красят 🟢/🔴. Ядро эконома не трогаем, надеваемся сверху.

МОДЕЛЬ ПРИБЫЛИ (слова оператора, знобы TUNABLE — оператор подтверждает числа):
  • profit — ФИКСИРОВАННЫЙ по ТИРУ закупки. «Заказ в закупке до 700₽ → мой профит примерно
    одинаков» → tier ≤700₽ = +N₽ фикс, дороже закупка/риск → выше profit.
  • В расход ВСЕГДА кладём: комиссию Маркета (% категории — оператор смотрел), доставку Express,
    и ИЗДЕРЖКА-БУФЕР (немного сверху — чтобы наверняка в нашу пользу; по факту профит будет больше).
  • Цена продажи ВЫВОДИТСЯ из: закупка + все сборы + целевой profit (реверс-формула ниже).

РЕВЕРС-ФОРМУЛА. Дана закупка C и целевой чистый profit P(тир). Сборы как функция цены S —
  ВСЕ платежи Маркету (мандат оператора «учитывай ВСЕ платежи, что отдаём маркету»):
    fees(S) = S·комиссия% + S·эквайринг% + доставка + (издержка_фикс + S·издержка%)
  Решаем  S − C − fees(S) = P:
    S = (C + доставка + издержка_фикс + P) / (1 − комиссия% − эквайринг% − издержка%)
  Округляем S вверх до психологической цены; profit пересчитываем на округлённой S (≥ P).
  Комиссия и доставка — по КАТЕГОРИИ/РАЗМЕРУ (переопределяются per-item из живого тарифа, см. see()).

🟢/🔴 (жадный охотник):
  • 🟢 закупка известна И цена продажи ≤ закупка×N (правдоподобно для рынка, категорийщик ×5–10)
       И маржа ≥ мин. → товар даёт твой profit по вменяемой цене → ДОБАВЛЯЕМ.
  • 🔴 иначе (напр. пакет за 3₽: чтобы снять +300₽ пришлось бы продать за 130× закупки — рынок
       столько не даст). Честно отсеиваем — не жжём силы на неподходящее.

ЗАКОН ОРГАНА (фиксируем НАВСЕГДА — дисциплина оператора «доказанную способность → сразу закон»):
  1. ПРИСОСКА (suppliers/*_v1.py): доказанная способность присосаться к сайту по URL и тянуть
     товары контрактом scan()→normalized() БЕЗ Excel. Живая присоска: cargo_avto (донор Express,
     1С-Битрикс; пагинация ?PAGEN_{N}, сетка vs виджет по template-хешу bx_{tid}_, дедуп по sku,
     70/70 плёнки доказано 2026-08-26). Присоска к сайту = записывается законом, не переоткрывается.
  2. ОЧКИ (этот файл): присоска даёт закупку → очки СРАЗУ дают цену/profit/🟢🔴 под-капотной
     арифметикой (0 токенов, 0 сети в самом расчёте). Сокращаем путь: сразу видим что охотить.
  3. НЕ ТЕРЯЕМ: floor наследуется от ЦЕНОВИКА (цена ≥ закупка+сборы+min_profit). Издержка-буфер
     всегда в расход → показатели в нашу пользу. Нет закупки → 🔴 (не выдумываем profit).
  4. МАТЕМАТИЧЕСКАЯ ЦЕПЬ-МАТРИЦА (дисциплина «действие → воспроизводимо → реплей в цикле дня»):
     каждый вердикт раскладывается в цепь шагов [орган]→[формула]→[число] (chain), пачка → матрица
     (build_matrix) со снимком знобов (config_snapshot) в json (save_matrix). В цикле дня агент НЕ
     считает с нуля: свежий скан присоски → та же цепь на тех же формулах+знобах → сверка с матрицей.
     🟢 дальше по ПАУТИНЕ ОРГАНОВ: ИМЯ (ymarket_card.to_offer verbatim+EAN-13, НЕ unique_title) →
     ФОТО (photo_pipeline.forge_card canon=белый 4:5) → КАРТОЧКА (ymarket_write.create_card, 4-шаг).

stdlib-only, без сети в расчёте (сеть только у присоски READ). RUBICON цел по построению.
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ── КОНФИГ ОЧКОВ · знобы TUNABLE (оператор подтверждает/крутит) ──────────────────────────────
# ДОСТОВЕРНОСТЬ (мандат оператора «только достоверные данные + все платежи»): комиссия и доставка
# взяты из ЖИВОГО калькулятора Яндекса trade.calc_tariffs (READ 0₽, 2026-08-26) на РЕАЛЬНОЙ
# категории плёнки 76346336, программа EXPRESS. Прежние 15%/0₽ были выдумкой — удалены.
CONFIG = {
    # КОМИССИЯ Маркета в ЭТОЙ категории, доля. Живой замер: плёнка (76346336) = 44.5% (0.445).
    # ⚠ КАТЕГОРИЙНАЯ величина (одежда ≈29%, плёнка 44.5%) — при смене категории задать свою
    #   (per-item переопределение prod["fee_pct"] из живого тарифа перекрывает этот дефолт).
    "commission_pct": 0.445,
    # ЭКВАЙРИНГ/перевод платежа, доля — ОТДЕЛЬНЫЙ платёж Маркету (живой замер 3.33%). Раньше не
    #   учитывался вовсе → занижали сборы. Теперь всегда в расход (мандат «все платежи»).
    "payment_pct": 0.0333,
    # ДОСТАВКА Express за заказ, ₽. Живой тариф: ПОЛ ≈120₽ на компактном, но крупные бугристые
    #   рулоны (1.2 м × 50–100 м) → до 1500₽ (объёмный вес). Дефолт = пол; реальный размер
    #   переопределяет per-item через prod["delivery"] (из живого тарифа по габаритам). НЕ 0.
    "delivery_rub": 120.0,
    # ИЗДЕРЖКА-БУФЕР: всегда в расход, «чтобы наверняка в нашу пользу» (профит по факту будет больше).
    "overhead_rub": 20.0,     # фикс ₽ (упаковка/мелкий риск)
    "overhead_pct": 0.03,     # % от цены (страховочная подушка)
    # ЦЕЛЕВОЙ ЧИСТЫЙ profit по ТИРУ закупки: (верхняя_граница_закупки_₽, profit_₽). По возрастанию.
    "tiers": [
        (700.0, 300.0),          # закупка ≤700₽ → +300₽ (слова: «до 700₽ профит одинаков»)
        (1500.0, 500.0),         # 700–1500₽ → +500₽
        (float("inf"), 800.0),   # >1500₽ → +800₽ (выше риск своих денег → выше profit)
    ],
    "max_sell_mult": 8.0,     # потолок правдоподобия: цена продажи ≤ закупка×N (категорийщик ×5–10)
    "round_to": 10.0,         # округление цены вверх до, ₽ (психологическая цена)
    "min_margin_pct": 5.0,    # ниже этой маржи не красим зелёным (совпадает с ЦЕНОВИК MIN_MARGIN_PCT)
}


def tier_profit(cost, tiers):
    """Целевой чистый profit для данной закупки по лестнице тиров. cost=None → None.

    upper=None трактуется как +inf (верхний тир без потолка) — так матрица переживает
    round-trip через строгий JSON, где inf-граница сохранена как null.
    """
    if cost is None:
        return None
    for upper, profit in tiers:
        if upper is None or cost <= upper:
            return float(profit)
    return float(tiers[-1][1])


def see(prod, cfg=CONFIG):
    """ОЧКИ на один товар: закупка → цена продажи → profit → вердикт. Разбор ВОСПРОИЗВОДИМ.

    prod — normalized() из присоски (нужен cost). Возврат:
      {sku, name, cost, target_profit, sell, profit, margin_pct, mult, green(bool), why}
    """
    cost = prod.get("cost") if isinstance(prod, dict) else None
    cost = float(cost) if isinstance(cost, (int, float)) and cost > 0 else None
    name = (prod.get("name") if isinstance(prod, dict) else "") or ""
    sku = prod.get("sku") if isinstance(prod, dict) else None
    base = {"sku": sku, "name": name, "cost": cost, "grid": prod.get("grid") if isinstance(prod, dict) else None}

    if cost is None:
        base.update({"target_profit": None, "sell": None, "profit": None, "margin_pct": None,
                     "mult": None, "green": False, "why": "нет закупки → profit не посчитать (не выдумываем)"})
        return base

    # комиссия и доставка — по КАТЕГОРИИ/РАЗМЕРУ: per-item из живого тарифа перекрывает дефолт очков
    comm = float(prod["fee_pct"]) if isinstance(prod, dict) and isinstance(prod.get("fee_pct"), (int, float)) else float(cfg["commission_pct"])
    delivery = float(prod["delivery"]) if isinstance(prod, dict) and isinstance(prod.get("delivery"), (int, float)) else float(cfg["delivery_rub"])
    pay = float(cfg["payment_pct"]); ovh_rub = float(cfg["overhead_rub"]); ovh_pct = float(cfg["overhead_pct"])
    P = tier_profit(cost, cfg["tiers"])

    denom = 1.0 - comm - pay - ovh_pct
    if denom <= 0:
        base.update({"target_profit": P, "sell": None, "profit": None, "margin_pct": None,
                     "mult": None, "green": False, "why": "комиссия+эквайринг+издержка% ≥ 100% — цена не выводится"})
        return base

    raw_sell = (cost + delivery + ovh_rub + P) / denom
    step = float(cfg["round_to"]) or 1.0
    sell = math.ceil(raw_sell / step) * step                 # округляем ВВЕРХ (в нашу пользу)

    fees = sell * comm + sell * pay + delivery + ovh_rub + sell * ovh_pct
    profit = round(sell - cost - fees, 2)
    margin_pct = round(profit / sell * 100.0, 1) if sell > 0 else None
    mult = round(sell / cost, 2)

    max_mult = float(cfg["max_sell_mult"]); min_margin = float(cfg["min_margin_pct"])
    if mult > max_mult:
        why = f"цена {sell:.0f}₽ = ×{mult} закупки > потолка ×{max_mult:g} — рынок столько не даст"
        green = False
    elif margin_pct is not None and margin_pct < min_margin:
        why = f"маржа {margin_pct}% < мин {min_margin:g}% — не окупает риск"
        green = False
    else:
        why = f"закупка {cost:.0f}₽ → продажа {sell:.0f}₽ (×{mult}) → +{profit:.0f}₽ чистыми ({margin_pct}%)"
        green = True
    base.update({"target_profit": P, "sell": sell, "profit": profit, "margin_pct": margin_pct,
                 "mult": mult, "green": green, "why": why,
                 "fee_pct_used": comm, "payment_pct_used": pay, "delivery_used": delivery})
    return base


def scan_through_glasses(products, cfg=CONFIG):
    """Пропустить пачку товаров через очки → вердикты + сводка охотника."""
    rows = [see(p, cfg) for p in (products or [])]
    green = [r for r in rows if r["green"]]
    gp = [r["profit"] for r in green if isinstance(r["profit"], (int, float))]
    avg_green = round(sum(gp) / len(gp), 2) if gp else None
    return {
        "rows": rows,
        "total": len(rows),
        "green": len(green),
        "red": len(rows) - len(green),
        "avg_green_profit": avg_green,
        "profit_10_orders": (round(avg_green * 10, 2) if avg_green is not None else None),
        "green_rows": sorted(green, key=lambda r: (r["profit"] or 0), reverse=True),
    }


def render(result, show_red=8):
    """Человеческая матрица для оператора: что горит зелёным (охотим) и сколько отсеяли."""
    lines = [
        f"👓 ОЧКИ: {result['total']} товаров → 🟢 {result['green']} охотим · 🔴 {result['red']} мимо",
    ]
    if result["avg_green_profit"] is not None:
        lines.append(f"   средний profit зелёного ≈ {result['avg_green_profit']:.0f}₽ · "
                     f"10 заказов ≈ {result['profit_10_orders']:.0f}₽ чистыми")
    lines.append("   ── 🟢 ЗЕЛЁНЫЕ (закупка → продажа ×кратность → profit) ──")
    for r in result["green_rows"]:
        lines.append(f"   🟢 [{str(r['sku']):>8}] {r['cost']:>6.0f}→{r['sell']:>6.0f}₽ ×{r['mult']:<4} "
                     f"+{r['profit']:>5.0f}₽ {str(r['margin_pct'])+'%':>6}  {r['name'][:40]}")
    reds = [r for r in result["rows"] if not r["green"]]
    if reds:
        lines.append(f"   ── 🔴 МИМО ({len(reds)}) ──")
        for r in reds[:show_red]:
            tag = f"{r['cost']:.0f}₽" if r["cost"] else "нет закупки"
            lines.append(f"   🔴 [{str(r['sku']):>8}] {tag:>8}  {r['name'][:34]:34} — {r['why']}")
        if len(reds) > show_red:
            lines.append(f"      … и ещё {len(reds) - show_red}")
    return "\n".join(lines)


# ── МАТЕМАТИЧЕСКАЯ ЦЕПЬ-МАТРИЦА · паутина товаров (закон 4) ──────────────────────────────────
MATRIX_SCHEMA = "ymarket.glasses.matrix.v1"
_HERE = Path(__file__).resolve().parent
# scripts/mint/arbiter -> SOCC/MEMORY_WAVE/reports/mint/arbiter (канон отчётов, как ymarket_state)
_REPORTS = _HERE.parent.parent.parent / "MEMORY_WAVE/reports/mint/arbiter"

# Когда товар 🟢 — дальше по ПАУТИНЕ ОРГАНОВ (кто за что отвечает; это действия, не деньги):
GREEN_PIPELINE = [
    {"organ": "ИМЯ ymarket_card_v1.to_offer", "does": "имя донора 1-в-1 + суффикс + свой EAN-13 (НЕ unique_title)"},
    {"organ": "ФОТО photo_pipeline_v1.forge_card", "does": "свои пиксели, белый фон 4:5 (canon), venv-python"},
    {"organ": "КАРТОЧКА ymarket_write_v1.create_card", "does": "4-шаг публикация offer-mappings→…→PUBLISHED (0₽)"},
]


def matrix_path():
    """Путь матрицы. env YM_MATRIX_PATH перекрывает (песочница/тесты не пишут в канон)."""
    p = os.environ.get("YM_MATRIX_PATH")
    return Path(p) if p else (_REPORTS / "ymarket_glasses_matrix.json")


def chain(v, cfg=CONFIG):
    """Вердикт see() → упорядоченная МАТЕМАТИЧЕСКАЯ ЦЕПЬ: шаги [орган]→[формула]→[число].

    Формула статична (её и реплеит агент дня), out — числа этого SKU. Нет закупки → цепь честно
    обрывается на шаге 1 (profit не выдумываем). Это разом реасонинг (видно КАК считает) и контракт
    реплея (те же формулы + config_snapshot дают те же числа на свежем скане).
    """
    c = v.get("cost")
    steps = [{"n": 1, "organ": "ПРИСОСКА suppliers/*", "name": "закупка",
              "formula": "cost = itemprop price (розница донора = наша цена выкупа при заказе)",
              "out": {"sku": v.get("sku"), "cost": c}}]
    if c is None:
        steps[0]["out"]["stop"] = "нет закупки → цепь не строится (profit не выдумываем)"
        return steps
    comm = float(v.get("fee_pct_used", cfg["commission_pct"])); dlv = float(v.get("delivery_used", cfg["delivery_rub"]))
    pay = float(v.get("payment_pct_used", cfg["payment_pct"]))
    ovr = float(cfg["overhead_rub"]); ovp = float(cfg["overhead_pct"]); step = float(cfg["round_to"]) or 1.0
    fees = round(v["sell"] * comm + v["sell"] * pay + dlv + ovr + v["sell"] * ovp, 2) if v.get("sell") else None
    steps += [
        {"n": 2, "organ": "ОЧКИ tier_profit", "name": "целевой profit (тир)",
         "formula": "P = tier(cost): ≤700→+300 · ≤1500→+500 · >1500→+800",
         "out": {"target_profit": v.get("target_profit")}},
        {"n": 3, "organ": "ОЧКИ see (реверс ЦЕНОВИКА)", "name": "цена продажи",
         "formula": f"S = ceil((cost+{dlv:g}+{ovr:g}+P)/(1−{comm:g}−{pay:g}−{ovp:g})/{step:g})·{step:g}",
         "out": {"sell": v.get("sell")}},
        {"n": 4, "organ": "ЭКОНОМ (calc_tariffs: комиссия+эквайринг+доставка)", "name": "сборы Маркета",
         "formula": f"fees = S·{comm:g} + S·{pay:g} + {dlv:g} + {ovr:g} + S·{ovp:g}",
         "out": {"fees": fees}},
        {"n": 5, "organ": "ЭКОНОМ sku_margin", "name": "чистый profit / маржа",
         "formula": "profit = S − cost − fees ; margin% = profit/S·100",
         "out": {"profit": v.get("profit"), "margin_pct": v.get("margin_pct")}},
        {"n": 6, "organ": "ОЧКИ + ЦЕНОВИК floor", "name": "вердикт",
         "formula": f"🟢 ⟺ mult ≤ ×{float(cfg['max_sell_mult']):g} И margin ≥ {float(cfg['min_margin_pct']):g}%",
         "out": {"mult": v.get("mult"), "green": v.get("green")}},
    ]
    return steps


def _cfg_json_safe(cfg):
    """Копия знобов, безопасная для СТРОГОГО JSON: inf-границы тиров → null (= «без потолка»).

    json.dump(allow_nan) пишет невалидный `Infinity`; jq/JS-агент цикла дня подавится. tier_profit
    читает null как +inf → реплей воспроизводим на любом парсере.
    """
    out = dict(cfg)
    out["tiers"] = [[(None if u == float("inf") else u), p] for u, p in cfg["tiers"]]
    return out


def build_matrix(products, cfg=CONFIG, donor=None, category=None):
    """Пачка товаров → МАТРИЦА-паутина: снимок знобов + цепь на каждый SKU + куда 🟢 идёт дальше.

    Это то, что читает агент цикла дня, чтобы «примерно тем же заниматься» в этой отрасли.
    """
    res = scan_through_glasses(products, cfg)
    keep = ("sku", "name", "cost", "target_profit", "sell", "profit", "margin_pct", "mult",
            "green", "grid", "why")
    rows = [{**{k: r.get(k) for k in keep}, "chain": chain(r, cfg)} for r in res["rows"]]
    return {
        "schema": MATRIX_SCHEMA,
        "donor": donor, "category": category,
        "config_snapshot": _cfg_json_safe(cfg),  # знобы (inf→null, валидный JSON) → реплей воспроизводим
        "summary": {k: res[k] for k in ("total", "green", "red", "avg_green_profit", "profit_10_orders")},
        "green_pipeline": GREEN_PIPELINE,       # паутина органов для 🟢 (имя→фото→карточка)
        "rows": rows,
    }


def save_matrix(matrix, path=None):
    """Атомарно записать матрицу (tmp + os.replace) — идиома ymarket_state.write_atomic, свой путь."""
    p = Path(path) if path else matrix_path()
    matrix.setdefault("schema", MATRIX_SCHEMA)
    matrix["updated_at"] = datetime.now(timezone.utc).isoformat()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".ymmatrix_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(matrix, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return p


def render_chain(v, cfg=CONFIG):
    """Показать оператору, КАК рассуждает система на одном товаре (цепь = видимый реасонинг)."""
    out = [f"🧮 ЦЕПЬ [{v.get('sku')}] {(v.get('name') or '')[:46]}"]
    for s in chain(v, cfg):
        out.append(f"   {s['n']}. {s['name']:<22} [{s['organ']}]")
        out.append(f"      {s['formula']}")
        nums = " · ".join(f"{k}={val}" for k, val in s["out"].items()
                          if k not in ("sku", "stop") and val is not None)
        if nums:
            out.append(f"      → {nums}")
        if s["out"].get("stop"):
            out.append(f"      ⛔ {s['out']['stop']}")
    return "\n".join(out)


if __name__ == "__main__":
    # Живой конвейер: присоска (READ сайт) → очки (0₽) [→ матрица/цепь]. RUBICON цел (только GET).
    import argparse
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "suppliers"))
    from cargo_avto_v1 import CargoAvtoAdapter

    ap = argparse.ArgumentParser(description="ОЧКИ ARBITER — присоска READ → деньги видно сразу (0₽)")
    ap.add_argument("slug", nargs="?", default="vozdushno-puzyrkovaya-plenka")
    ap.add_argument("--matrix", action="store_true", help="построить+сохранить математическую матрицу (паутину)")
    ap.add_argument("--explain", metavar="SKU", help="показать математическую цепь одного SKU")
    args = ap.parse_args()

    prods = CargoAvtoAdapter().scan(category=args.slug, limit=500)
    main = [p for p in prods if p.get("grid") == "main"]         # охота по категории; related не мешаем
    res = scan_through_glasses(main)
    print(f"ПРИСОСКА cargo_avto '{args.slug}': {len(main)} товаров категории\n")
    print(render(res))

    if args.explain:
        row = next((r for r in res["rows"] if str(r.get("sku")) == str(args.explain)), None)
        print("\n" + (render_chain(row) if row else f"SKU {args.explain} не найден в категории"))

    if args.matrix:
        m = build_matrix(main, donor="cargo_avto", category=args.slug)
        path = save_matrix(m)
        sm = m["summary"]
        print(f"\n🧬 матрица-паутина сохранена: {path}")
        print(f"   {sm['green']}🟢/{sm['total']} товаров · цепь {len(m['rows'][0]['chain'])} шагов на SKU · "
              f"знобы в config_snapshot · 🟢→{len(m['green_pipeline'])} органа (имя→фото→карточка)")

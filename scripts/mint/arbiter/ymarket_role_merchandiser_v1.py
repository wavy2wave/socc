#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РОЛЬ · ТОВАРОВЕД (YM_MERCHANDISER) — решает, ЧТО вообще имеет смысл лить в Экспресс.

Канон роли SOCC (TFS-1, 8 полей) — см. CHARTER ниже.

Вход воронки. Пока ТОВАРОВЕД не сказал «берём», ни одна другая роль не работает:
ЦЕНОВИК не считает, СКЛАДОВЩИК не обновляет, ДИСПЕТЧЕР не караулит.

Что он ловит и почему это деньги:

1. ГАБАРИТНЫЙ ОБРЫВ ТАРИФА (главное). Экспресс-доставка стоит 8 % от цены (мин 100 ₽,
   макс 1500 ₽), НО только пока товар < 20 кг И сумма трёх сторон < 210 см. Чуть выше —
   плоские 1500 ₽ за товар. Позиция за 400 ₽ с суммой сторон 211 см убыточна всегда:
   доставка дороже товара вчетверо. Роль отбивает такое ДО залива.

2. ГАБАРИТЫ ГОРОДА. Экспресс физически не примет то, что курьер не увезёт: Москва —
   до 60 кг и 380×180×180 см, большинство городов Подмосковья — 20 кг и 100×60×50 см.
   Залил → пришёл заказ → отгрузить нечем → отмена по вине магазина (до 5000 ₽ + индекс).

3. НЕПОДТВЕРЖДЁННАЯ КАТЕГОРИЯ. Нет marketCategoryId — карточка не встанет (need_mapping),
   зря потраченные запросы и мусор в кабинете.

4. НЕТ ИСТОЧНИКА НАЛИЧИЯ. СКЛАДОВЩИК по закону S1 выставит 0 — карточка родится мёртвой.

ЧЕСТНОСТЬ (L3): роль не угадывает габариты и не «прикидывает» вес. Нет размеров → позиция
уходит в needs_data, а НЕ считается «наверное влезет».

Что роль НЕ делает (граница честности):
  • не обещает, что товар купят — оценивает только то, что следует из чисел;
  • не выставляет цену (это ЦЕНОВИК) и не пишет остатки (это СКЛАДОВЩИК);
  • не решает за оператора, какого партнёра брать — проверяет уже выбранный ассортимент.
"""
from __future__ import annotations

import json
import sys

import ymarket_role_pricer_v1 as pricer
import ymarket_trade_hands_v1 as trade

CHARTER = {
    "id": "YM_MERCHANDISER",
    "name_ru": "ТОВАРОВЕД",
    "mandate": "в витрину попадает только то, что физически отгружаемо и экономически осмысленно",
    "owns": ["отбор ассортимента", "габаритный фильтр", "проверка категории", "скоринг позиций"],
    "inputs": ["ассортимент партнёра", "габариты города", "тарифы Маркета", "справочник категорий"],
    "outputs": ["одобренный список → ЦЕНОВИК", "отклонённые с причиной → оператор"],
    "laws": [
        "T1 не влезает в габариты города → НЕ берём (заказ придёт, отгрузить нечем)",
        "T2 за габаритным обрывом тарифа (20 кг / 210 см) доставка 1500 ₽ — считаем это ДО залива",
        "T3 категория не подтверждена → НЕ берём (карточка не встанет)",
        "T4 нет источника наличия → НЕ берём (родится мёртвой, S1 выставит 0)",
        "T5 нет габаритов → needs_data, НЕ «наверное влезет»",
    ],
    "kpi": [
        {"metric": "доля одобренных, дошедших до продажи", "target": "рост",
         "source_of_truth": "заказы Маркета по SKU"},
        {"metric": "отмен из-за негабарита", "target": "0", "source_of_truth": "статусы заказов"},
        {"metric": "позиций без габаритов", "target": "→0", "source_of_truth": "ассортимент партнёра"},
    ],
    "proves_by": "по каждой позиции: габариты → лимит города → тариф → вердикт; воспроизводимо",
}

# Обрыв тарифа Маркета: до него 8 % (мин 100, макс 1500), за ним — плоские 1500 ₽/товар.
TARIFF_CLIFF_WEIGHT_KG = 20.0
TARIFF_CLIFF_SUM_CM = 210.0
FLAT_HEAVY_DELIVERY_RUB = 1500.0
EXPRESS_PCT = 0.08
EXPRESS_MIN_RUB = 100.0
EXPRESS_MAX_RUB = 1500.0

# Габаритные лимиты городов (из справки Маркета). Ключ — regionId либо имя города.
CITY_LIMITS = {
    "москва": {"max_weight_kg": 60.0, "max_dims_cm": (380.0, 180.0, 180.0)},
    "default": {"max_weight_kg": 20.0, "max_dims_cm": (100.0, 60.0, 50.0)},
}

# Насколько близко к обрыву считаем опасным (габариты партнёра часто неточны).
CLIFF_MARGIN_CM = 10.0
CLIFF_MARGIN_KG = 1.0


def city_limits(city=None):
    """Лимиты города. Неизвестный город → консервативный default (меньше, а не больше)."""
    if not city:
        return CITY_LIMITS["default"]
    return CITY_LIMITS.get(str(city).strip().lower().replace("ё", "е"), CITY_LIMITS["default"])


def _dims(prod):
    """Габариты позиции. Нет хотя бы одного числа → None (T5: не выдумываем)."""
    vals = []
    for k in ("length", "width", "height"):
        v = prod.get(k)
        if not isinstance(v, (int, float)) or v <= 0:
            return None
        vals.append(float(v))
    return vals


def fits_city(prod, city=None):
    """Влезает ли в габариты города (T1). Стороны сравниваем отсортированно — коробку можно повернуть."""
    lim = city_limits(city)
    dims = _dims(prod)
    weight = prod.get("weight")
    weight = float(weight) if isinstance(weight, (int, float)) and weight > 0 else None

    if dims is None or weight is None:
        return {"ok": None, "why": "нет габаритов или веса — проверить нельзя (T5)",
                "limits": lim}
    if weight > lim["max_weight_kg"]:
        return {"ok": False, "why": f"вес {weight} кг > лимита города {lim['max_weight_kg']} кг (T1)",
                "limits": lim}
    got = sorted(dims, reverse=True)
    allowed = sorted(lim["max_dims_cm"], reverse=True)
    for g, a in zip(got, allowed):
        if g > a:
            return {"ok": False,
                    "why": f"сторона {g} см > лимита {a} см (T1) — курьер не увезёт",
                    "limits": lim}
    return {"ok": True, "why": "влезает в габариты города", "limits": lim}


def delivery_cost(prod, price=None):
    """Стоимость экспресс-доставки по тарифной сетке Маркета + разбор обрыва (T2).

    Возвращает {cost, tier, near_cliff, why}. Нет данных → cost=None (не выдумываем).
    """
    price = price if price is not None else prod.get("price")
    price = float(price) if isinstance(price, (int, float)) and price > 0 else None
    dims = _dims(prod)
    weight = prod.get("weight")
    weight = float(weight) if isinstance(weight, (int, float)) and weight > 0 else None

    if dims is None or weight is None:
        return {"cost": None, "tier": None, "near_cliff": None,
                "why": "нет габаритов/веса — тариф не посчитать (T5)"}

    dim_sum = round(sum(dims), 1)
    heavy = weight >= TARIFF_CLIFF_WEIGHT_KG or dim_sum >= TARIFF_CLIFF_SUM_CM
    near = (not heavy) and (
        dim_sum >= TARIFF_CLIFF_SUM_CM - CLIFF_MARGIN_CM
        or weight >= TARIFF_CLIFF_WEIGHT_KG - CLIFF_MARGIN_KG)

    if heavy:
        return {"cost": FLAT_HEAVY_DELIVERY_RUB, "tier": "flat_heavy", "near_cliff": False,
                "dim_sum_cm": dim_sum, "weight_kg": weight,
                "why": (f"за обрывом тарифа (вес {weight} кг ≥ {TARIFF_CLIFF_WEIGHT_KG} "
                        f"или стороны {dim_sum} ≥ {TARIFF_CLIFF_SUM_CM} см) → "
                        f"плоские {FLAT_HEAVY_DELIVERY_RUB} ₽ за товар")}
    if price is None:
        return {"cost": None, "tier": "percent", "near_cliff": near, "dim_sum_cm": dim_sum,
                "weight_kg": weight, "why": "нет цены — процентный тариф не посчитать"}
    cost = round(min(max(price * EXPRESS_PCT, EXPRESS_MIN_RUB), EXPRESS_MAX_RUB), 2)
    why = f"{EXPRESS_PCT*100:.0f} % от цены с границами {EXPRESS_MIN_RUB}–{EXPRESS_MAX_RUB} ₽"
    if near:
        why += (f" · ОПАСНО БЛИЗКО к обрыву (стороны {dim_sum} см, вес {weight} кг): "
                f"ошибка в габаритах партнёра → доставка станет {FLAT_HEAVY_DELIVERY_RUB} ₽")
    return {"cost": cost, "tier": "percent", "near_cliff": near, "dim_sum_cm": dim_sum,
            "weight_kg": weight, "why": why}


def screen_one(prod, city=None, cats=None, min_profit=pricer.MIN_PROFIT_RUB):
    """Вердикт по одной позиции. Возвращает воспроизводимый разбор (каждое «нет» с причиной)."""
    sku = prod.get("sku") or prod.get("offerId")
    out = {"sku": sku, "name": prod.get("name"), "verdict": None, "reasons": [],
           "fit": None, "delivery": None, "economics": None}

    # T3 — категория подтверждена?
    cat_id = prod.get("category_id") or prod.get("marketCategoryId")
    if cats is not None and not cat_id:
        slug = prod.get("slug")
        entry = (cats or {}).get(slug) if slug else None
        cat_id = (entry or {}).get("market_category_id")
    if not cat_id:
        out["reasons"].append("T3: категория не подтверждена (marketCategoryId нет) — карточка не встанет")

    # T4 — источник наличия
    if not (prod.get("stock_source") or prod.get("in_stock") is True
            or isinstance(prod.get("count"), (int, float))):
        out["reasons"].append("T4: нет источника наличия — карточка родится мёртвой (S1 выставит 0)")

    # T1/T5 — габариты города
    fit = fits_city(prod, city)
    out["fit"] = fit
    if fit["ok"] is False:
        out["reasons"].append(fit["why"])
    elif fit["ok"] is None:
        out["reasons"].append("T5: " + fit["why"])

    # T2 — тариф и обрыв
    dl = delivery_cost(prod)
    out["delivery"] = dl
    if dl["cost"] is None and fit["ok"] is not None:
        out["reasons"].append("T2: тариф доставки не посчитать")

    # Экономика: маржа с учётом реальной доставки (переиспользуем пол ЦЕНОВИКА)
    if dl["cost"] is not None:
        econ = pricer.price_decision(prod, tariff_row={"tariffs": [{"amount": dl["cost"]}]},
                                     min_profit=min_profit)
        out["economics"] = econ
        if not econ["allowed"]:
            out["reasons"].append("экономика: " + econ["why"])

    if out["reasons"]:
        # needs_data отделяем от отказа: данные можно донести, физику — нет
        only_data = all(r.startswith("T5") or "не посчитать" in r or "T4" in r or "T3" in r
                        for r in out["reasons"])
        out["verdict"] = "needs_data" if only_data else "reject"
    else:
        out["verdict"] = "approve"
    return out


def screen(products, city=None, cats=None, min_profit=pricer.MIN_PROFIT_RUB):
    """Просеять ассортимент. Возвращает {approved, rejected, needs_data, agg}."""
    approved, rejected, needs = [], [], []
    for p in products or []:
        r = screen_one(p, city=city, cats=cats, min_profit=min_profit)
        {"approve": approved, "reject": rejected, "needs_data": needs}[r["verdict"]].append(r)

    profits = [a["economics"]["profit"] for a in approved
               if a.get("economics") and isinstance(a["economics"].get("profit"), (int, float))]
    near = [a for a in approved if (a.get("delivery") or {}).get("near_cliff")]
    return {
        "approved": approved, "rejected": rejected, "needs_data": needs,
        "agg": {
            "total": len(products or []),
            "approved": len(approved), "rejected": len(rejected), "needs_data": len(needs),
            "avg_profit": round(sum(profits) / len(profits), 2) if profits else None,
            "near_cliff": len(near),
            "city_limits": city_limits(city),
        },
    }


def render(result):
    a = result["agg"]
    lim = a["city_limits"]
    lines = [
        f"🧺 ТОВАРОВЕД: одобрено {a['approved']} · отклонено {a['rejected']} · "
        f"нужны данные {a['needs_data']} (из {a['total']})",
        f"   лимиты города: до {lim['max_weight_kg']} кг, "
        f"{'×'.join(str(int(x)) for x in lim['max_dims_cm'])} см",
    ]
    if a["avg_profit"] is not None:
        lines.append(f"   средняя прибыль одобренных: {a['avg_profit']} ₽")
    if a["near_cliff"]:
        lines.append(f"   ⚠️  у обрыва тарифа: {a['near_cliff']} — ошибка габаритов сделает "
                     f"доставку {FLAT_HEAVY_DELIVERY_RUB} ₽")
    for r in result["rejected"][:5]:
        lines.append(f"   ⛔ {r['sku']}: {r['reasons'][0]}")
    for r in result["needs_data"][:5]:
        lines.append(f"   ❓ {r['sku']}: {r['reasons'][0]}")
    return "\n".join(lines)


if __name__ == "__main__":
    if "--charter" in sys.argv:
        print(json.dumps(CHARTER, ensure_ascii=False, indent=2))
        sys.exit(0)

    demo = [
        {"sku": "S1", "name": "Плёнка 10 м", "price": 1500, "cost": 900, "category_id": 100,
         "weight": 2.0, "length": 40, "width": 30, "height": 20, "stock_source": "партнёр"},
        {"sku": "S2", "name": "Стеллаж", "price": 4000, "cost": 2500, "category_id": 100,
         "weight": 25.0, "length": 180, "width": 60, "height": 40, "stock_source": "партнёр"},
        {"sku": "S3", "name": "Коробка дешёвая", "price": 400, "cost": 250, "category_id": 100,
         "weight": 1.0, "length": 120, "width": 60, "height": 40, "stock_source": "партнёр"},
        {"sku": "S4", "name": "Скотч без габаритов", "price": 200, "cost": 120,
         "category_id": 100, "stock_source": "партнёр"},
        {"sku": "S5", "name": "Пузырчатая плёнка", "price": 900, "cost": 500, "category_id": 100,
         "weight": 3.0, "length": 90, "width": 55, "height": 45},
    ]

    print("=== город по умолчанию (Подмосковье: 20 кг, 100×60×50) ===")
    res = screen(demo, city=None)
    print(render(res))
    print("\n=== Москва (60 кг, 380×180×180) ===")
    res_msk = screen(demo, city="Москва")
    print(render(res_msk))

    print("\nразбор по позициям (Москва):")
    for group in ("approved", "rejected", "needs_data"):
        for r in res_msk[group]:
            mark = {"approve": "✅", "reject": "⛔", "needs_data": "❓"}[r["verdict"]]
            dl = r.get("delivery") or {}
            tail = f" · доставка {dl.get('cost')} ₽ ({dl.get('tier')})" if dl.get("cost") else ""
            print(f"  {mark} {r['sku']} {r['name']}{tail}")
            for why in r["reasons"]:
                print(f"       {why}")
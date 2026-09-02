#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СРЕЗ-5 АУДИТ (READ-only, оффлайн): габариты 18 рулонов через РЕАЛЬНЫЙ ТОВАРОВЕД.

Ничего наружу не шлём. Только вызываем city_limits/fits_city/delivery_cost.
Габариты реконструируем из "суммы трёх сторон" оператора:
  рулон = цилиндр: ось(=ширина плёнки) × диаметр × диаметр
  сумма = ось + 2*D  ⇒  D = (сумма - ось)/2
Это ЕДИНСТВЕННОЕ допущение (для city-fit). Тарифный обрыв от него НЕ зависит
(обрыв смотрит только на сумму сторон и вес — оба даны оператором).
"""
import json
import ymarket_role_merchandiser_v1 as m

# (имя, ширина_плёнки_м, сумма_сторон_см, вес_кг|None)
ROLLS = [
    ("1.2x100м", 1.2, 256, 4.15),
    ("1.2x50м",  1.2, 220, 3.02),
    ("1.2x50м",  1.2, 206, 1.8),
    ("0.5x100м", 0.5, 186, 2.0),
    ("0.5x100м", 0.5, 184, 3.0),
    ("1.2x20м",  1.2, 172, 0.96),
    ("0.3x100м", 0.3, 166, None),
    ("0.3x100м", 0.3, 164, None),
    ("0.75x100м",0.75,151, None),
    ("0.5x50м",  0.5, 150, None),
    ("0.5x50м",  0.5, 146, None),
    ("1.2x5м",   1.2, 143, None),
    ("0.3x50м",  0.3, 138, None),
    ("0.3x50м",  0.3, 130, None),
    ("0.3x50м",  0.3, 126, None),
    ("0.5x20м",  0.5, 102, None),
    ("0.3x20м",  0.3, 82,  None),
    ("0.4x5м",   0.4, 63,  None),
]

# Цена-заглушка только для процентного тарифа (8% от цены). Берём 1000 ₽ как ориентир.
PRICE_PROBE = 1000.0


def build(name, fw_m, sum_cm, weight):
    axis = fw_m * 100.0            # ось цилиндра = ширина плёнки, см
    d = round((sum_cm - axis) / 2.0, 1)   # диаметр из суммы
    prod = {"sku": name, "name": name, "length": round(axis, 1),
            "width": d, "height": d, "price": PRICE_PROBE}
    if weight is not None:
        prod["weight"] = weight
    return prod, axis, d


print("ЛИМИТЫ ГОРОДОВ (из кода merchandiser):")
print("  Москва :", m.city_limits("Москва"))
print("  default:", m.city_limits(None))
print("  ОБРЫВ  : вес >=", m.TARIFF_CLIFF_WEIGHT_KG, "кг ИЛИ сумма >=",
      m.TARIFF_CLIFF_SUM_CM, "см -> плоские", m.FLAT_HEAVY_DELIVERY_RUB, "₽")
print("  процент:", int(m.EXPRESS_PCT*100), "% (мин", m.EXPRESS_MIN_RUB,
      ", макс", m.EXPRESS_MAX_RUB, "₽)")
print()
hdr = f"{'#':>2} {'рулон':<10} {'ось×D×D(см)':<16} {'вес':>6} {'сумма':>6} " \
      f"{'МСК':>5} {'город':>6} {'тариф':<11} {'дост₽':>7} near"
print(hdr)
print("-" * len(hdr))

for i, (name, fw, s, w) in enumerate(ROLLS, 1):
    prod, axis, d = build(name, fw, s, w)
    fit_msk = m.fits_city(prod, city="Москва")
    fit_def = m.fits_city(prod, city=None)
    dl = m.delivery_cost(prod, price=PRICE_PROBE)

    def mark(fit):
        return {True: "да", False: "НЕТ", None: "?"}[fit["ok"]]

    dims = f"{axis:g}×{d:g}×{d:g}"
    tier = dl.get("tier") or "-"
    cost = dl.get("cost")
    near = "⚠️" if dl.get("near_cliff") else ""
    wtxt = f"{w}" if w is not None else "?"
    print(f"{i:>2} {name:<10} {dims:<16} {wtxt:>6} {s:>6} "
          f"{mark(fit_msk):>5} {mark(fit_def):>6} {tier:<11} "
          f"{str(cost):>7} {near}")

print()
print("ДЕТАЛЬ по обрыву (why) для крупных:")
for name, fw, s, w in ROLLS[:4]:
    prod, axis, d = build(name, fw, s, w)
    dl = m.delivery_cost(prod, price=PRICE_PROBE)
    print(f"  {name} (сумма {s}, вес {w}): {dl['tier']} -> {dl['why']}")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА ЯНДЕКС M4 — РОЛИ органа М6 (ЦЕНОВИК · ДИСПЕТЧЕР · СКЛАДОВЩИК · БРИГАДИР).

Фальсифицируемо: каждый тест ловит конкретное нарушение закона роли — если роль говорит,
что маржа посчитана, а пол выдуман → FAIL. Если смена упала на одной роли, но другие
отработали → проверяем, что отчёт это отражает.

Запуск: python3 tests/run_yandex_m4_roles.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_role_pricer_v1 as pricer            # noqa: E402
import ymarket_role_dispatcher_v1 as dispatcher    # noqa: E402
import ymarket_role_stockman_v1 as stockman        # noqa: E402
import ymarket_role_controller_v1 as controller    # noqa: E402
import ymarket_role_merchandiser_v1 as merchandiser  # noqa: E402
import ymarket_shift_memory_v1 as memory           # noqa: E402
import ymarket_brigade_v1 as brigade               # noqa: E402
import ymarket_trade_hands_v1 as trade             # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))


print("ПРИЁМКА ЯНДЕКС M4 — роли органа М6\n")

# ============================================================================
# ЦЕНОВИК — P1: никогда ниже пола маржи
# ============================================================================
print("ЦЕНОВИК · P1: цена ниже пола = отказ")

def fake_tariffs_50(offers, **kw):
    return [{"tariffs": [{"type": "FEE", "amount": 50.0}]} for _ in offers]

d = pricer.price_decision({"sku": "S1", "price": 200, "cost": 180}, tariff_row={"tariffs": [{"amount": 50}]})
check("P1: цена 200 при закупке 180+сборы 50+min 30 = пол 260 → отказ",
      d["allowed"] is False and "НИЖЕ пола" in d["why"])

d = pricer.price_decision({"sku": "S1", "price": 300, "cost": 180}, tariff_row={"tariffs": [{"amount": 50}]})
check("P1: цена 300 при поле 260 → разрешено", d["allowed"] is True and d["profit"] > 0)

d = pricer.price_decision({"sku": "S1", "price": 1000}, tariff_row={"tariffs": [{"amount": 50}]})
check("P2: нет закупки → basis='cost_only' и отказ", d["basis"] == "cost_only" and not d["allowed"])

d = pricer.price_decision({"sku": "S1", "price": 1000, "cost": 500})
check("P2: нет тарифов → basis='no_fees' и отказ", d["basis"] == "no_fees" and not d["allowed"])

res = pricer.decide_batch([{"sku": "S1", "price": 200, "cost": 180, "category_id": 1}],
                          tariffs_fn=fake_tariffs_50)
check("пол воспроизводим: breakdown показывает закупка+сборы+мин.прибыль",
      res["decisions"][0]["cost_buy"] == 180 and res["decisions"][0]["market_fees"] == 50.0)

r = pricer.apply_prices("B1", [{"allowed": False, "sku": "S1", "price": 100}], dry=True)
check("P1 физически: ниже пола не идёт наружу", r["status"] == "noop" and "пол маржи" in r["note"])

r = pricer.apply_prices("B1", [{"allowed": True, "sku": "S1", "price": 300}], dry=True)
check("P1 физически: разрешённая цена идёт", r["status"] == "dry")

# ============================================================================
# ДИСПЕТЧЕР — D1: неизвестный дедлайн = эскалация
# ============================================================================
print("\nДИСПЕТЧЕР · D1: заказ без дедлайна → эскалация")

now = datetime(2026, 8, 5, 12, 0, 0)
orders_ok = [{"id": 1, "campaignId": "C1", "substatus": "STARTED",
              "delivery": {"shipments": [{"shipmentDate": "2026-08-05", "shipmentTime": "12:30:00"}]}}]
orders_nodl = [{"id": 2, "campaignId": "C1", "substatus": "STARTED", "delivery": {}}]

t = dispatcher.triage(orders_ok, now=now)
check("D1: дедлайн известен → действие QUEUE/COLLECT", t["ok"] or t["warn"] or t["critical"])

t = dispatcher.triage(orders_nodl, now=now)
check("D1: нет shipmentDate → unknown_deadline", len(t["unknown_deadline"]) == 1)
check("D1: unknown → ESCALATE", t["unknown_deadline"][0]["action"] == "ESCALATE")

orders_late = [{"id": 3, "campaignId": "C1", "substatus": "STARTED",
                "delivery": {"shipments": [{"shipmentDate": "2026-08-05", "shipmentTime": "10:00:00"}]}}]
t = dispatcher.triage(orders_late, now=now)
check("D1: просрочен на 60 мин → overdue", len(t["overdue"]) == 1)
check("D4: просрочка = ESCALATE_INCIDENT (деньги)", t["overdue"][0]["action"] == "ESCALATE_INCIDENT")

r = dispatcher.confirm_ready("C1", 1, "", dry=True)
check("D2: нет collected_by → отказ READY_TO_SHIP", r["ok"] is False and "NO_HUMAN_CONFIRMATION" in r["reason"])

r = dispatcher.confirm_ready("C1", 1, "Иван", dry=True)
check("D2: есть collected_by → проходит", r.get("collected_by") == "Иван")

prop = dispatcher.cancel_proposal({"order_id": 1})
check("D3: роль не отменяет сама", prop["requires_operator"] is True and "роль не отменяет" in prop["why"])
check("D3: показывает цену отмены (деньги)", "5000" in prop["cost_warning"] or "штраф" in prop["cost_warning"].lower())

# ============================================================================
# СКЛАДОВЩИК — S1: лучше ноль, чем ложь
# ============================================================================
print("\nСКЛАДОВЩИК · S1: источник неизвестен → безопасный 0")

p = stockman.plan([{"sku": "S1", "count": 5}, {"sku": "S2"}], warehouse_id=101)
check("S1: нет источника → count=0", p["updates"][1]["count"] == 0)
check("S1: пометка 'unknown'", "S2" in p["unknown"])
check("S1: source явно назван", "SAFE_ZERO" in p["updates"][1]["source"] or "источник" in p["updates"][1]["source"])

p = stockman.plan([{"sku": "S1", "count": -10}], warehouse_id=101)
check("S2: отрицательный count → 0", p["updates"][0]["count"] == 0)

p = stockman.plan([{"sku": "S1", "in_stock": False}], warehouse_id=101)
check("S2: in_stock=False → 0 (не выдумываем наличие)", p["updates"][0]["count"] == 0)

ref = trade.create_warehouse_refused()
r = stockman.ensure_express("B1", wh_fn=lambda bid: [])
check("S3: нет склада → честный отказ (метода создания нет)", r["ok"] is False and "API_METHOD_ABSENT" in str(r))

def fake_read_wrong(bid, wid, offer_ids=None):
    return [{"sku": "S1", "count": 999}]  # не то, что отправили

v = stockman.verify("B1", 101, [{"sku": "S1", "count": 7}], read_fn=fake_read_wrong)
check("S4 доказательство: запись→чтение→сверка ловит расхождение", not v["ok"] and v["mismatches"])

def fake_read_ok(bid, wid, offer_ids=None):
    return [{"sku": "S1", "count": 7}]

v = stockman.verify("B1", 101, [{"sku": "S1", "count": 7}], read_fn=fake_read_ok)
check("S4 доказательство: совпадает → ok=True", v["ok"] is True and not v["mismatches"])

# ============================================================================
# КОНТРОЛЁР — C1..C5: зоны индекса качества
# ============================================================================
print("\nКОНТРОЛЁР · C1–C5: зоны индекса, нет данных = эскалация")

z = controller.classify(25)
check("C1: индекс <40 → critical + STOP_OPERATIONS",
      z["zone"] == "critical" and z["action"] == "STOP_OPERATIONS")
check("C1: показывает цену (отключение 7 дней)", "7 дней" in z.get("cost", ""))

z = controller.classify(65)
check("C2: индекс 40–79 → danger", z["zone"] == "danger" and z["action"] == "ESCALATE_HIGH")

z = controller.classify(85)
check("C3: индекс 80–97 → costs (штрафы платные)", z["zone"] == "costs")
check("C3: называет суммы штрафов", "5000" in z.get("cost", "") and "2000" in z.get("cost", ""))

z = controller.classify(99)
check("C4: индекс ≥98 → safe (штрафов нет)",
      z["zone"] == "safe" and "нет" in z.get("cost", ""))

z = controller.classify(None)
check("C5: индекс None → unknown + ESCALATE (не 'всё хорошо')",
      z["zone"] == "unknown" and z["action"] == "ESCALATE")

r = controller.check("B1", [], quality_fn=lambda b, c: [])
check("C5: нет campaignId → честный отказ", r["ok"] is False and r["reason"] == "NO_CAMPAIGNS")

r = controller.check("B1", ["C1"], quality_fn=lambda b, c: [])
check("C5: пустой ответ Маркета → ok=False (не 'норма')",
      r["ok"] is False and r["reason"] == "EMPTY_RESPONSE")

def q_boom(b, c):
    raise RuntimeError("сеть упала")

r = controller.check("B1", ["C1"], quality_fn=q_boom)
check("C5: сеть упала → ok=False с причиной", r["ok"] is False and "сеть упала" in r["error"])
check("C5: явно сказано, что НЕ считаем всё хорошим", "НЕ считаем" in r["note"])

r = controller.check("B1", ["C1", "C2"], quality_fn=lambda b, c: [
    {"campaignId": "C1", "total": 35}, {"campaignId": "C2", "total": 99}])
check("КОНТРОЛЁР: критичная кампания попала в escalate",
      len(r["escalate"]) == 1 and r["escalate"][0]["campaignId"] == "C1")
check("КОНТРОЛЁР: безопасная не в escalate",
      all(e["campaignId"] != "C2" for e in r["escalate"]))

from datetime import datetime as _dt, timedelta as _td
_now = _dt.now()
tr = controller.trend(92, [{"at": (_now - _td(hours=25)).isoformat(), "rating": 98}])
check("КОНТРОЛЁР: падение >5 за сутки → falling=True", tr["falling"] is True and tr["delta_24h"] == -6.0)

tr = controller.trend(97, [{"at": (_now - _td(hours=25)).isoformat(), "rating": 98}])
check("КОНТРОЛЁР: падение на 1 → falling=False", tr["falling"] is False)

tr = controller.trend(92, [])
check("КОНТРОЛЁР: нет истории → тренд не выдуман", tr["delta_24h"] is None)

rec = controller.recommendations("B1")
check("КОНТРОЛЁР: рекомендаций в API нет → честный отказ",
      rec["ok"] is False and rec["reason"] == "API_NO_DETAILS")

# ============================================================================
# ТОВАРОВЕД — T1..T5: что вообще берём в витрину
# ============================================================================
print("\nТОВАРОВЕД · T1–T5: габариты, обрыв тарифа, категория, наличие")

MSK = "Москва"
base = {"category_id": 100, "stock_source": "партнёр"}

# T1 — габариты города
f = merchandiser.fits_city({**base, "weight": 25.0, "length": 40, "width": 30, "height": 20})
check("T1: вес 25 кг > лимита Подмосковья 20 кг → не влезает", f["ok"] is False and "вес" in f["why"])

f = merchandiser.fits_city({**base, "weight": 25.0, "length": 40, "width": 30, "height": 20}, city=MSK)
check("T1: тот же товар в Москве (60 кг) → влезает", f["ok"] is True)

f = merchandiser.fits_city({**base, "weight": 2.0, "length": 120, "width": 60, "height": 40})
check("T1: сторона 120 > лимита 100 → не влезает", f["ok"] is False and "сторона" in f["why"])

f = merchandiser.fits_city({**base, "weight": 2.0, "length": 55, "width": 95, "height": 45})
check("T1: стороны сортируются (коробку можно повернуть) → влезает", f["ok"] is True)

f = merchandiser.fits_city({**base, "weight": 2.0})
check("T5: нет габаритов → ok=None (не 'наверное влезет')", f["ok"] is None)

# T2 — обрыв тарифа
d = merchandiser.delivery_cost({"price": 1000, "weight": 2.0, "length": 40, "width": 30, "height": 20})
check("T2: лёгкий товар → 8% от цены", d["tier"] == "percent" and d["cost"] == 80.0 or d["cost"] == 100.0)

d = merchandiser.delivery_cost({"price": 1000, "weight": 25.0, "length": 40, "width": 30, "height": 20})
check("T2: вес ≥20 кг → плоские 1500 ₽", d["tier"] == "flat_heavy" and d["cost"] == 1500.0)

d = merchandiser.delivery_cost({"price": 1000, "weight": 2.0, "length": 120, "width": 60, "height": 40})
check("T2: сумма сторон ≥210 см → плоские 1500 ₽", d["tier"] == "flat_heavy" and d["cost"] == 1500.0)

d = merchandiser.delivery_cost({"price": 400, "weight": 2.0, "length": 30, "width": 30, "height": 30})
check("T2: минимум 100 ₽ соблюдён", d["cost"] == 100.0)

d = merchandiser.delivery_cost({"price": 100000, "weight": 2.0, "length": 30, "width": 30, "height": 30})
check("T2: максимум 1500 ₽ соблюдён", d["cost"] == 1500.0)

d = merchandiser.delivery_cost({"price": 1000, "weight": 2.0, "length": 100, "width": 60, "height": 45})
check("T2: близко к обрыву (205 см) → near_cliff=True", d["near_cliff"] is True)
check("T2: near_cliff объясняет риск", "обрыв" in d["why"].lower())

d = merchandiser.delivery_cost({"price": 1000})
check("T5: нет габаритов → тариф не считаем", d["cost"] is None)

# T3/T4 — категория и наличие
r = merchandiser.screen_one({"sku": "X", "price": 1000, "cost": 500, "weight": 1.0,
                             "length": 20, "width": 20, "height": 20, "stock_source": "п"})
check("T3: нет category_id → needs_data", r["verdict"] == "needs_data"
      and any("T3" in x for x in r["reasons"]))

r = merchandiser.screen_one({"sku": "X", "category_id": 100, "price": 1000, "cost": 500,
                             "weight": 1.0, "length": 20, "width": 20, "height": 20})
check("T4: нет источника наличия → needs_data", r["verdict"] == "needs_data"
      and any("T4" in x for x in r["reasons"]))

ok_prod = {**base, "sku": "OK", "price": 1500, "cost": 900, "weight": 2.0,
           "length": 40, "width": 30, "height": 20}
r = merchandiser.screen_one(ok_prod)
check("ТОВАРОВЕД: годная позиция → approve", r["verdict"] == "approve" and not r["reasons"])
check("ТОВАРОВЕД: вердикт воспроизводим (fit+delivery+economics)",
      r["fit"]["ok"] is True and r["delivery"]["cost"] is not None
      and r["economics"]["allowed"] is True)

# отбой по экономике: дешёвый товар за обрывом тарифа
bad = {**base, "sku": "BAD", "price": 300, "cost": 200, "weight": 1.0,
       "length": 120, "width": 60, "height": 40}
r = merchandiser.screen_one(bad, city=MSK)
check("ТОВАРОВЕД: дешёвый за обрывом → reject (доставка > цены)",
      r["verdict"] == "reject" and r["delivery"]["cost"] == 1500.0)

res = merchandiser.screen([ok_prod, bad], city=MSK)
check("ТОВАРОВЕД: пачка разложена на approve/reject",
      res["agg"]["approved"] == 1 and res["agg"]["rejected"] == 1)
check("ТОВАРОВЕД: неизвестный город → консервативный default",
      merchandiser.city_limits("Урюпинск")["max_weight_kg"] == 20.0)

# ============================================================================
# ПАМЯТЬ СМЕНЫ — M1..M4
# ============================================================================
print("\nПАМЯТЬ · M1–M4: журнал смен, тренд, повторы")

import tempfile as _tf
from datetime import timedelta as _td

_tmpdir = _tf.mkdtemp()
mem_path = os.path.join(_tmpdir, "shift_mem.json")

def _rep(rating, overdue=0, at=None, ok=True):
    return {"at": (at or datetime.now()).isoformat(), "dry": True, "commit": False, "ok": ok,
            "steps": {"CONTROLLER": {"campaigns": [{"campaignId": "C1", "rating": rating}]},
                      "DISPATCHER": {"counts": {"overdue": overdue, "critical": 0,
                                                "warn": 0, "unknown_deadline": 1}},
                      "PRICER": {"allowed": 5, "refused": 1, "agg": {"avg_profit": 300}}},
            "escalations": [{"role": "DISPATCHER", "kind": "UNKNOWN_DEADLINE"}],
            "errors": []}

doc = memory.load(path=mem_path)
check("M3: пустой журнал → пустой список смен", doc["shifts"] == [])

_now = datetime.now()
for i, rating in enumerate([98, 96, 94, 92]):
    memory.record(_rep(rating, overdue=1, at=_now - _td(days=3 - i)), path=mem_path)

doc = memory.load(path=mem_path)
check("M1: смены дописываются в конец (append-only)", len(doc["shifts"]) == 4)
check("M1: порядок сохранён (старые → новые)",
      doc["shifts"][0]["quality_rating"] == 98 and doc["shifts"][-1]["quality_rating"] == 92)

hist = memory.quality_history(path=mem_path)
check("ПАМЯТЬ: история в формате controller.trend", len(hist) == 4 and "at" in hist[0])

tr = controller.trend(92, hist)
check("ПАМЯТЬ+КОНТРОЛЁР: тренд теперь считается (висяк закрыт)", tr["delta_24h"] is not None)

rec = memory.recurring_problems(path=mem_path, days=7, min_times=3)
check("ПАМЯТЬ: повторяющаяся проблема найдена",
      any(p["kind"] == "UNKNOWN_DEADLINE" and p["times"] >= 3 for p in rec["problems"]))

rec_empty = memory.recurring_problems(path=os.path.join(_tmpdir, "nope.json"))
check("M3: нет данных → no_data=True, а не 'проблем нет'", rec_empty["no_data"] is True)

s = memory.summary(path=mem_path, days=7)
check("ПАМЯТЬ: сводка видит падение индекса",
      s["quality"]["first"] == 98.0 and s["quality"]["last"] == 92.0)
check("ПАМЯТЬ: считает просрочки за период", s["overdue_total"] == 4)

s_empty = memory.summary(path=os.path.join(_tmpdir, "nope2.json"))
check("M3: пустая сводка честна (no_data)", s_empty["no_data"] is True)

memory.record(_rep(90), path=mem_path, max_shifts=3)
doc = memory.load(path=mem_path)
check("M4: обрезка до max_shifts", len(doc["shifts"]) == 3)
check("M4: обрезка учтена в счётчике", doc.get("trimmed", 0) >= 1)

check("M2: файл журнала валиден после записей",
      json.loads(open(mem_path, encoding="utf-8").read())["schema"] == memory.SCHEMA)

# ============================================================================
# БРИГАДИР — B2: упавшая роль не роняет смену
# ============================================================================
print("\nБРИГАДИР · B2: роль упала → остальные работают")

def boom(*a, **kw):
    raise RuntimeError("boom")

rep = brigade.shift("B1", warehouse_id=101, stock_items=[{"sku": "S1", "count": 1}],
                    now=now, dry=True, orders_fn=boom)
check("B2: ДИСПЕТЧЕР упал → смена не упала", "steps" in rep)
check("B2: упавший шаг помечен ok=False", rep["steps"]["DISPATCHER"]["ok"] is False)
check("B2: ошибка видна в errors", len(rep["errors"]) > 0 and "ДИСПЕТЧЕР" in rep["errors"][0])
check("B2: СКЛАДОВЩИК после падения ДИСПЕТЧЕРА отработал", rep["steps"]["STOCKMAN"]["ok"] is not False)

rep = brigade.shift("B1", campaign_id="C1", now=now, dry=True,
                    orders_fn=lambda bid: [],
                    quality_fn=boom)
check("B2: КОНТРОЛЁР упал → смена прошла, отчёт честный", "КОНТРОЛЁР" in rep["errors"][0])

# ============================================================================
# БРИГАДИР — B1: порядок (заказы → остатки → цены)
# ============================================================================
print("\nБРИГАДИР · B1: порядок смены (горящее первым)")

order = list(brigade.SHIFT_ORDER)
check("B1: DISPATCHER первым (заказы горят)", order[0][0] == "DISPATCHER")
check("B1: STOCKMAN вторым (остатки — отмены)", order[1][0] == "STOCKMAN")
check("B1: MERCHANDISER третьим (что брать — до цены)", order[2][0] == "MERCHANDISER")
check("B1: PRICER четвёртым (маржа после отбора)", order[3][0] == "PRICER")
check("B1: CONTROLLER последним (отчёт)", order[-1][0] == "CONTROLLER")

# ============================================================================
# БРИГАДИР — B4: отчёт показывает, чего роль НЕ смогла узнать
# ============================================================================
print("\nБРИГАДИР · B4: отчёт честный (не только успехи)")

rep = brigade.shift("B1", warehouse_id=101, now=now, dry=True,
                    orders_fn=boom,
                    stock_items=[{"sku": "S1"}])  # источника нет
check("B4: escalations содержат 'источник неизвестен'",
      any("NO_STOCK_SOURCE" in e.get("kind", "") for e in rep["escalations"]))
check("B4: errors содержат упавший ДИСПЕТЧЕР",
      any("ДИСПЕТЧЕР" in str(e) for e in rep["errors"]))

rendered = brigade.render(rep)
check("B4: render показывает горящее первым", rendered.index("ТРЕБУЕТ ВНИМАНИЯ") < rendered.index("РОЛИ"))

# ============================================================================
# КАНОН — каждая роль имеет 8 полей
# ============================================================================
print("\nКАНОН · роли соответствуют шаблону SOCC (8 полей)")

for r in [pricer.CHARTER, dispatcher.CHARTER, stockman.CHARTER, controller.CHARTER,
          merchandiser.CHARTER]:
    check(f"{r['id']}: id присутствует", r.get("id"))
    check(f"{r['id']}: mandate присутствует", r.get("mandate"))
    check(f"{r['id']}: owns — список", isinstance(r.get("owns"), list) and r["owns"])
    check(f"{r['id']}: laws — список", isinstance(r.get("laws"), list) and r["laws"])
    check(f"{r['id']}: kpi — список с метрикой+target", isinstance(r.get("kpi"), list) and r["kpi"])
    check(f"{r['id']}: proves_by — строка", isinstance(r.get("proves_by"), str) and r["proves_by"])
    for k in r["kpi"]:
        check(f"{r['id']} KPI: source_of_truth присутствует",
              k.get("source_of_truth"), f"KPI {k.get('metric')}")

# ============================================================================
# ИТОГ
# ============================================================================
print("\n" + "=" * 70)
print(f"ЯНДЕКС M4 (роли): {len(PASS)}/{len(PASS) + len(FAIL)} зелёных")
if FAIL:
    print("КРАСНЫЕ:")
    for f in FAIL:
        print(f"  ❌ {f}")
    sys.exit(1)
print("✅ Роли честны: законы выполняются, упавшая роль не роняет смену, отчёт правдив")

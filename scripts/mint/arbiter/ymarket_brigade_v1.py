#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""БРИГАДИР (YM_BRIGADE) — гоняет роли органа М6 по кругу и отчитывается одним листом.

Канон: НЕ второй дирижёр. Настоящий дирижёр SOCC — socc_lawful_step_engine_v1.run_step,
его не дублируем (MINT-SPEC-1 прямо запрещает). Бригадир — сменный мастер внутри органа:
знает ПОРЯДОК смены и КОГО будить, но закон исполняет чужой движок.

ПОРЯДОК СМЕНЫ (почему именно такой):
  1. ДИСПЕТЧЕР первым — заказы горят по таймеру 60 минут; всё остальное может ждать, это нет.
  2. СКЛАДОВЩИК вторым — протухший остаток рождает новые отмены прямо сейчас.
  3. ЦЕНОВИК третьим — деньги на позициях, которые уже стоят на витрине.
  4. КОНТРОЛЁР последним — индекс качества, отчёт о смене.
Приоритет = цена ошибки в рублях, а не удобство кода.

ЗАКОНЫ БРИГАДИРА:
  B1 сначала горящее (заказы), потом важное (остатки), потом выгодное (цены).
  B2 упавшая роль НЕ роняет смену — остальные работают, отчёт честно показывает провал.
  B3 наружу ничего без commit — гейт наследуется от торговых рук.
  B4 отчёт показывает, чего роль НЕ смогла узнать (не только успехи).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime

import ymarket_role_dispatcher_v1 as dispatcher
import ymarket_role_pricer_v1 as pricer
import ymarket_role_stockman_v1 as stockman
import ymarket_role_controller_v1 as controller
import ymarket_role_merchandiser_v1 as merchandiser
import ymarket_shift_memory_v1 as memory
import ymarket_trade_hands_v1 as trade
import ymarket_hands_v1 as hands

ROLES = [merchandiser.CHARTER, dispatcher.CHARTER, stockman.CHARTER, pricer.CHARTER,
         controller.CHARTER]

SHIFT_ORDER = [
    ("DISPATCHER", "заказы горят по таймеру — первым"),
    ("STOCKMAN", "протухший остаток рождает отмены — вторым"),
    ("MERCHANDISER", "что вообще брать в витрину — до цены"),
    ("PRICER", "маржа на витрине — после отбора"),
    ("CONTROLLER", "индекс качества и отчёт — последним"),
]


def _safe(step_name, fn, *a, **kw):
    """B2: роль упала → фиксируем провал, смену не роняем."""
    try:
        return {"ok": True, "result": fn(*a, **kw)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "step": step_name}


def shift(business_id, campaign_id=None, warehouse_id=None, stock_items=None,
          products=None, city=None, cats=None, now=None, dry=True, commit=False,
          orders_fn=None, tariffs_fn=None, read_stocks_fn=None, quality_fn=None,
          memory_path=None, remember=True):
    """Одна смена бригады. Все внешние вызовы имеют швы — смена тестируется без сети.

    city/cats — для ТОВАРОВЕДА (габаритные лимиты города, справочник категорий).
    remember=True — смена дописывается в журнал (память цеха), чтобы был тренд.

    Возвращает лист смены: что каждая роль сделала, чего не смогла, и что требует оператора.
    """
    now = now or datetime.now()
    report = {"at": now.isoformat(), "business_id": business_id,
              "dry": dry, "commit": commit, "steps": {}, "escalations": [], "errors": []}

    # --- 1. ДИСПЕТЧЕР: горящие заказы -------------------------------------
    d = _safe("DISPATCHER", dispatcher.scan, business_id, now=now, orders_fn=orders_fn)
    if d["ok"]:
        scan = d["result"]
        report["steps"]["DISPATCHER"] = {
            "ok": scan.get("ok", False),
            "counts": scan.get("counts"),
            "urgent": len(scan.get("urgent") or []),
            "human": dispatcher.render(scan),
        }
        if not scan.get("ok"):
            report["errors"].append(f"ДИСПЕТЧЕР: {scan.get('error')}")
        for it in (scan.get("urgent") or []):
            report["escalations"].append({
                "role": "DISPATCHER", "kind": "URGENT_ORDER",
                "order_id": it.get("order_id"), "why": it.get("why"),
                "action": it.get("action")})
        for it in ((scan.get("triage") or {}).get("unknown_deadline") or []):
            report["escalations"].append({
                "role": "DISPATCHER", "kind": "UNKNOWN_DEADLINE",
                "order_id": it.get("order_id"), "why": it.get("why"),
                "action": "ESCALATE"})
    else:
        report["steps"]["DISPATCHER"] = {"ok": False, "error": d["error"]}
        report["errors"].append(f"ДИСПЕТЧЕР упал: {d['error']}")

    # --- 2. СКЛАДОВЩИК: остатки -------------------------------------------
    if stock_items and warehouse_id is not None:
        p = _safe("STOCKMAN", stockman.plan, stock_items, warehouse_id)
        if p["ok"]:
            plan = p["result"]
            pushed = _safe("STOCKMAN_PUSH", stockman.push, business_id, plan["updates"],
                           dry=dry, commit=commit)
            ver = None
            if pushed["ok"] and pushed["result"].get("sent"):
                ver = _safe("STOCKMAN_VERIFY", stockman.verify, business_id, warehouse_id,
                            plan["updates"], read_fn=read_stocks_fn)
            report["steps"]["STOCKMAN"] = {
                "ok": pushed["ok"],
                "planned": len(plan["updates"]), "zeroed": len(plan["zeroed"]),
                "unknown_source": len(plan["unknown"]),
                "push": pushed.get("result") if pushed["ok"] else pushed.get("error"),
                "verify": (ver.get("result") if ver and ver["ok"] else
                           (ver.get("error") if ver else None)),
                "human": stockman.render(plan,
                                         pushed.get("result") if pushed["ok"] else None,
                                         ver.get("result") if ver and ver["ok"] else None),
            }
            if plan["unknown"]:
                report["escalations"].append({
                    "role": "STOCKMAN", "kind": "NO_STOCK_SOURCE",
                    "skus": plan["unknown"][:20],
                    "why": "источник наличия неизвестен → выставлен 0 (S1), нужен реальный источник",
                    "action": "OPERATOR_INPUT"})
            if not pushed["ok"]:
                report["errors"].append(f"СКЛАДОВЩИК (отправка): {pushed['error']}")
        else:
            report["steps"]["STOCKMAN"] = {"ok": False, "error": p["error"]}
            report["errors"].append(f"СКЛАДОВЩИК упал: {p['error']}")
    else:
        report["steps"]["STOCKMAN"] = {
            "ok": None, "skipped": True,
            "why": "нет данных о наличии или не задан склад — вслепую остатки не пишем (S2)"}

    # --- 3. ТОВАРОВЕД: что вообще берём в витрину -------------------------
    priced_products = products
    if products:
        m = _safe("MERCHANDISER", merchandiser.screen, products, city=city, cats=cats)
        if m["ok"]:
            scr = m["result"]
            report["steps"]["MERCHANDISER"] = {
                "ok": True, "agg": scr["agg"], "human": merchandiser.render(scr),
            }
            # дальше по цепочке идут ТОЛЬКО одобренные (T1–T5 отсекли остальное)
            approved_skus = {r["sku"] for r in scr["approved"]}
            priced_products = [p for p in products
                               if (p.get("sku") or p.get("offerId")) in approved_skus]
            if scr["rejected"]:
                report["escalations"].append({
                    "role": "MERCHANDISER", "kind": "ASSORTMENT_REJECTED",
                    "skus": [r["sku"] for r in scr["rejected"]][:20],
                    "why": "позиции физически или экономически непригодны для Экспресса",
                    "action": "DROP_OR_FIX"})
            if scr["needs_data"]:
                report["escalations"].append({
                    "role": "MERCHANDISER", "kind": "ASSORTMENT_NEEDS_DATA",
                    "skus": [r["sku"] for r in scr["needs_data"]][:20],
                    "why": "нет габаритов / категории / источника наличия — проверить нельзя (T5)",
                    "action": "OPERATOR_INPUT"})
            near = [r for r in scr["approved"] if (r.get("delivery") or {}).get("near_cliff")]
            if near:
                report["escalations"].append({
                    "role": "MERCHANDISER", "kind": "NEAR_TARIFF_CLIFF",
                    "skus": [r["sku"] for r in near][:20],
                    "why": (f"габариты у обрыва тарифа — ошибка в размерах партнёра сделает "
                            f"доставку {merchandiser.FLAT_HEAVY_DELIVERY_RUB} ₽"),
                    "action": "VERIFY_DIMENSIONS"})
        else:
            report["steps"]["MERCHANDISER"] = {"ok": False, "error": m["error"]}
            report["errors"].append(f"ТОВАРОВЕД упал: {m['error']}")
    else:
        report["steps"]["MERCHANDISER"] = {"ok": None, "skipped": True,
                                           "why": "нет ассортимента на проверку"}

    # --- 4. ЦЕНОВИК: маржа ------------------------------------------------
    if priced_products:
        pr = _safe("PRICER", pricer.decide_batch, priced_products, business_id=business_id,
                   campaign_id=campaign_id, tariffs_fn=tariffs_fn)
        if pr["ok"]:
            res = pr["result"]
            applied = _safe("PRICER_APPLY", pricer.apply_prices, business_id,
                            res["decisions"], dry=dry, commit=commit)
            report["steps"]["PRICER"] = {
                "ok": applied["ok"],
                "allowed": res["allowed"], "refused": res["refused"], "agg": res["agg"],
                "apply": applied.get("result") if applied["ok"] else applied.get("error"),
                "human": pricer.render(res),
            }
            below = [d for d in res["decisions"]
                     if not d["allowed"] and d["basis"] == "full"]
            if below:
                report["escalations"].append({
                    "role": "PRICER", "kind": "BELOW_MARGIN_FLOOR",
                    "skus": [d["sku"] for d in below][:20],
                    "why": "цена ниже пола маржи — продажа в убыток запрещена (P1)",
                    "action": "REPRICE_OR_DROP"})
            nocost = [d for d in res["decisions"] if d["basis"] == "cost_only"]
            if nocost:
                report["escalations"].append({
                    "role": "PRICER", "kind": "NO_PURCHASE_COST",
                    "skus": [d["sku"] for d in nocost][:20],
                    "why": "закупка неизвестна → пол не посчитать (P2)",
                    "action": "OPERATOR_INPUT"})
            if not applied["ok"]:
                report["errors"].append(f"ЦЕНОВИК (запись): {applied['error']}")
        else:
            report["steps"]["PRICER"] = {"ok": False, "error": pr["error"]}
            report["errors"].append(f"ЦЕНОВИК упал: {pr['error']}")
    else:
        report["steps"]["PRICER"] = {"ok": None, "skipped": True,
                                     "why": "нет позиций на переоценку"}

    # --- 5. КОНТРОЛЁР: индекс качества ------------------------------------
    if campaign_id:
        q = _safe("CONTROLLER", controller.check, business_id, [campaign_id],
                  quality_fn=quality_fn)
        if q["ok"]:
            res = q["result"]
            report["steps"]["CONTROLLER"] = {
                "ok": res.get("ok", False),
                "campaigns": res.get("campaigns"),
                "human": controller.render(res),
            }
            if not res.get("ok"):
                # C5: индекс не прочитан — это эскалация, а не тишина
                report["errors"].append(
                    f"КОНТРОЛЁР: {res.get('error') or res.get('note')}")
                report["escalations"].append({
                    "role": "CONTROLLER", "kind": "QUALITY_UNKNOWN",
                    "why": f"индекс не прочитан (C5) — пропущенное падение = отключение: "
                           f"{res.get('error') or res.get('note')}",
                    "action": "ESCALATE"})
            for r in res.get("escalate", []):
                report["escalations"].append({
                    "role": "CONTROLLER",
                    "kind": ("QUALITY_CRITICAL" if r["zone"] == "critical"
                             else "QUALITY_UNKNOWN" if r["zone"] == "unknown"
                             else "QUALITY_DANGER"),
                    "value": r.get("rating"), "why": r["why"],
                    "cost": r.get("cost"), "action": r["action"]})
            for r in res.get("warn", []):
                report["escalations"].append({
                    "role": "CONTROLLER", "kind": "QUALITY_COSTS_MONEY",
                    "value": r.get("rating"), "why": r["why"],
                    "cost": r.get("cost"), "action": r["action"]})
        else:
            report["steps"]["CONTROLLER"] = {"ok": False, "error": q["error"]}
            report["errors"].append(f"КОНТРОЛЁР упал: {q['error']}")
    else:
        report["steps"]["CONTROLLER"] = {"ok": None, "skipped": True,
                                         "why": "campaignId не задан — индекс не прочитать"}

    report["ok"] = not report["errors"]

    # Запись в память цеха — тренд видим только когда помним вчера
    if remember:
        try:
            memory.record(report, path=memory_path)
        except Exception as e:
            report["errors"].append(f"память: не записана — {type(e).__name__}: {e}")

    return report


def render(report):
    """Лист смены для человека: сначала что горит, потом что сделано, потом чего не знаем."""
    L = []
    head = "✅" if report["ok"] else "⚠️"
    mode = "СУХО" if (report["dry"] or not report["commit"]) else "РЕАЛЬНО"
    L.append(f"{head} СМЕНА М6 · {report['at'][:16]} · режим {mode}")

    esc = report["escalations"]
    if esc:
        L.append(f"\n🔴 ТРЕБУЕТ ВНИМАНИЯ ({len(esc)}):")
        for e in esc:
            tgt = e.get("order_id") or (", ".join(e.get("skus", [])[:5]) if e.get("skus") else "")
            L.append(f"   [{e['role']}] {e['kind']}{' · ' + str(tgt) if tgt else ''}")
            L.append(f"      {e['why']}")
    else:
        L.append("\n🟢 горящего нет")

    L.append("\nРОЛИ:")
    for name, why in SHIFT_ORDER:
        st = report["steps"].get(name) or {}
        if st.get("skipped"):
            L.append(f"   ⏭  {name}: пропущено — {st.get('why')}")
        elif st.get("ok") is False:
            L.append(f"   ❌ {name}: {st.get('error')}")
        elif st.get("human"):
            for ln in st["human"].split("\n"):
                L.append(f"   {ln}")
        else:
            L.append(f"   ✅ {name}: отработал")

    if report["errors"]:
        L.append(f"\nСБОИ ({len(report['errors'])}):")
        for e in report["errors"]:
            L.append(f"   • {e}")
    return "\n".join(L)


if __name__ == "__main__":
    if "--charter" in sys.argv:
        print(json.dumps({"brigade_laws": ["B1", "B2", "B3", "B4"],
                          "shift_order": SHIFT_ORDER,
                          "roles": ROLES}, ensure_ascii=False, indent=2))
        sys.exit(0)

    if "--roles" in sys.argv:
        for r in ROLES:
            print(f"\n=== {r['name_ru']} ({r['id']}) ===")
            print(f"мандат: {r['mandate']}")
            print("законы:")
            for law in r["laws"]:
                print(f"  • {law}")
            print("KPI:")
            for k in r["kpi"]:
                print(f"  • {k['metric']} → {k['target']}  (правда из: {k['source_of_truth']})")
            print(f"доказывает: {r['proves_by']}")
        sys.exit(0)

    # Сухая смена на демо-данных: ни одного сетевого вызова.
    now = datetime(2026, 8, 5, 12, 0, 0)
    demo_orders = [
        {"id": 1, "campaignId": "C1", "substatus": "STARTED",
         "delivery": {"shipments": [{"shipmentDate": "2026-08-05", "shipmentTime": "10:30:00"}]}},
        {"id": 2, "campaignId": "C1", "substatus": "STARTED", "delivery": {}},
    ]
    rep = shift(
        business_id="B1", campaign_id="C1", warehouse_id=101, city="Москва",
        stock_items=[{"sku": "S1", "count": 5, "source": "партнёр"}, {"sku": "S2"}],
        products=[
            # проходит всё: габариты в норме, категория есть, наличие есть, маржа держит
            {"sku": "S1", "name": "Плёнка 10 м", "price": 1500, "cost": 900,
             "category_id": 100, "weight": 2.0, "length": 40, "width": 30, "height": 20,
             "stock_source": "партнёр"},
            # отобьётся экономикой: за обрывом тарифа доставка 1500 ₽ при цене 300 ₽
            {"sku": "S2", "name": "Коробка дешёвая", "price": 300, "cost": 280,
             "category_id": 100, "weight": 1.0, "length": 120, "width": 60, "height": 40,
             "stock_source": "партнёр"},
        ],
        now=now, dry=True, commit=False, remember=False,
        orders_fn=lambda bid: demo_orders,
        tariffs_fn=lambda offers, **kw: [
            {"tariffs": [{"type": "FEE", "amount": o["price"] * 0.08},
                         {"type": "EXPRESS_DELIVERY", "amount": 100.0}]} for o in offers],
        quality_fn=lambda bid, cids: [{"campaignId": "C1", "total": 92}],
    )
    print(render(rep))
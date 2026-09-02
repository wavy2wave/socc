#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РОЛЬ · ДИСПЕТЧЕР (YM_DISPATCHER) — не даёт просрочить экспресс-заказ.

Канон роли SOCC (TFS-1, 8 полей) — см. CHARTER ниже.

Зачем именно эта роль первая по деньгам: в Экспрессе Маркет даёт продавцу время на сборку
(10–60 минут, задаётся в кабинете) и ЕЩЁ 60 минут запаса. Не отправил «Готов к отгрузке»
до конца запаса → Маркет отменяет заказ САМ, индекс качества падает, и включается плата:

  отмена по вине магазина   (индекс 80–94)  → 75 % стоимости размещения, до 5000 ₽
  сборка с опозданием       (индекс 80–94)  → 15 % за 1 день … 100 % за 4 дня, до 2000 ₽
  индекс ниже 40                            → магазин отключают, товары скрывают 7 дней

То есть один просроченный заказ стоит дороже, чем вся дневная маржа на позиции.
Роль существует, чтобы этого не случилось НИКОГДА.

ЧЕСТНОСТЬ (L3 линии): время роль не угадывает. Нет shipmentDate/shipmentTime в заказе →
дедлайн неизвестен → заказ попадает в 'unknown_deadline' и эскалируется оператору,
а НЕ считается «наверное успеем».

Что роль НЕ делает (граница честности):
  • не отменяет заказы сама — отмена бьёт по деньгам и индексу, это решение оператора;
  • не подтверждает сборку, которой не было (READY_TO_SHIP только по факту);
  • не подбирает код курьера (attemptsLeft ограничен) — код приходит от человека.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

import ymarket_trade_hands_v1 as trade

CHARTER = {
    "id": "YM_DISPATCHER",
    "name_ru": "ДИСПЕТЧЕР",
    "mandate": "ни один экспресс-заказ не должен просрочить сборку",
    "owns": ["очередь заказов", "дедлайны сборки", "статус READY_TO_SHIP", "код курьера (проверка)"],
    "inputs": ["заказы Маркета (PROCESSING/EXPRESS)", "факт сборки от человека"],
    "outputs": ["срочный список к сборке", "READY_TO_SHIP → Маркет", "эскалация → оператор"],
    "laws": [
        "D1 заказ без известного дедлайна = ЭСКАЛАЦИЯ, не молчание",
        "D2 READY_TO_SHIP только по факту сборки (не по таймеру)",
        "D3 роль НЕ отменяет заказ сама — это решение оператора (деньги+индекс)",
        "D4 просрочка = инцидент с суммой ущерба, попадает в леджер как минус",
    ],
    "kpi": [
        {"metric": "просроченных заказов", "target": "0", "source_of_truth": "заказы Маркета + время"},
        {"metric": "отмен по вине магазина", "target": "0", "source_of_truth": "статусы заказов"},
        {"metric": "запас времени в момент отгрузки", "target": "≥15 мин", "source_of_truth": "дедлайн−факт"},
    ],
    "proves_by": "по каждому заказу: дедлайн, остаток минут, действие — воспроизводимо из ответа Маркета",
}

# Маркет даёт 60 минут запаса ПОСЛЕ времени отгрузки, потом отменяет сам.
GRACE_MINUTES = 60
# Порог «красной» зоны: меньше этого запаса — бежать собирать немедленно.
CRITICAL_MINUTES = 15
WARN_MINUTES = 40


def _parse_deadline(order):
    """Дедлайн отгрузки из заказа Маркета. Нет данных → None (D1: не выдумываем).

    Маркет кладёт shipmentDate (ГГГГ-ММ-ДД) и shipmentTime (ЧЧ:ММ:СС) в delivery.shipments[].
    """
    delivery = order.get("delivery") or {}
    for sh in delivery.get("shipments") or []:
        d, t = sh.get("shipmentDate"), sh.get("shipmentTime")
        if not d:
            continue
        try:
            if t:
                dt = datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M:%S")
            else:
                dt = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        # Маркет отдаёт локальное время кабинета; считаем в наивном времени и сравниваем с now того же вида.
        return dt
    return None


def triage(orders, now=None):
    """Разложить заказы по срочности. now передаётся ЯВНО (детерминизм, тестируемость).

    Возвращает {critical, warn, ok, unknown_deadline, overdue} — списки разборов:
      {order_id, campaign_id, deadline, minutes_left, zone, action, why}
    """
    if now is None:
        now = datetime.now()
    out = {"overdue": [], "critical": [], "warn": [], "ok": [], "unknown_deadline": []}

    for o in orders or []:
        oid = o.get("id") or o.get("orderId")
        cid = o.get("campaignId") or o.get("campaign_id")
        sub = o.get("substatus")
        base = {"order_id": oid, "campaign_id": cid, "substatus": sub}

        dl = _parse_deadline(o)
        if dl is None:
            out["unknown_deadline"].append({
                **base, "deadline": None, "minutes_left": None, "zone": "unknown",
                "action": "ESCALATE",
                "why": "в заказе нет shipmentDate — дедлайн неизвестен (D1), нужен человек"})
            continue

        hard = dl + timedelta(minutes=GRACE_MINUTES)   # после этого Маркет отменит сам
        left = round((hard - now).total_seconds() / 60.0, 1)
        item = {**base, "deadline": dl.isoformat(), "hard_deadline": hard.isoformat(),
                "minutes_left": left}

        if sub == trade.SUB_READY_TO_SHIP:
            out["ok"].append({**item, "zone": "done",
                              "action": "NONE", "why": "уже отмечен готовым к отгрузке"})
        elif left <= 0:
            out["overdue"].append({
                **item, "zone": "overdue", "action": "ESCALATE_INCIDENT",
                "why": f"ПРОСРОЧЕН на {abs(left)} мин — Маркет отменит/отменил сам, "
                       f"это инцидент с деньгами (D4)"})
        elif left <= CRITICAL_MINUTES:
            out["critical"].append({
                **item, "zone": "critical", "action": "COLLECT_NOW",
                "why": f"осталось {left} мин — собирать немедленно, иначе штраф"})
        elif left <= WARN_MINUTES:
            out["warn"].append({
                **item, "zone": "warn", "action": "COLLECT_SOON",
                "why": f"осталось {left} мин — ставить в работу сейчас"})
        else:
            out["ok"].append({
                **item, "zone": "ok", "action": "QUEUE",
                "why": f"запас {left} мин — в обычной очереди"})
    return out


def scan(business_id, now=None, orders_fn=None):
    """Прочитать свежие экспресс-заказы и разложить по срочности. READ, 0₽.

    Fail-soft: сеть/ключ упали → честный отказ со причиной, НЕ пустой «всё хорошо»
    (пустой список тут означал бы «просроченных нет» — опасная ложь).
    """
    fn = orders_fn or trade.new_express_orders
    try:
        orders = fn(business_id)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "note": "заказы не прочитаны — НЕ считаем, что просроченных нет"}
    t = triage(orders, now=now)
    return {"ok": True, "total": len(orders or []),
            "counts": {k: len(v) for k, v in t.items()}, "triage": t,
            "urgent": t["overdue"] + t["critical"]}


def confirm_ready(campaign_id, order_id, collected_by, dry=True, commit=False):
    """Отметить «Готов к отгрузке» — ТОЛЬКО когда сборка реально произошла (D2).

    collected_by — кто собрал (человек). Пусто → отказ: система не подтверждает
    сборку, которой не было; это прямой путь к отмене и штрафу.
    """
    if not collected_by:
        return {"ok": False, "sent": False, "reason": "NO_HUMAN_CONFIRMATION",
                "why": "READY_TO_SHIP только по факту сборки (D2) — нужен человек, кто собрал"}
    res = trade.mark_ready_to_ship(campaign_id, order_id, dry=dry, commit=commit)
    res["collected_by"] = collected_by
    return res


def cancel_proposal(item, reason="SHOP_FAILED"):
    """НЕ отменяет — готовит предложение оператору с ценой решения (D3).

    Роль обязана показать, что отмена стоит денег, и отдать решение человеку.
    """
    return {
        "proposal": "CANCEL_ORDER",
        "order_id": item.get("order_id"),
        "campaign_id": item.get("campaign_id"),
        "substatus": reason,
        "requires_operator": True,
        "cost_warning": ("отмена по вине магазина: плата от 150 ₽ до 5000 ₽ в зависимости "
                         "от индекса качества (при 80–94 → 75 % стоимости размещения) "
                         "+ полная стоимость доставки; индекс упадёт"),
        "why": "роль не отменяет сама (D3) — это решение оператора",
    }


def render(scan_result):
    """Сводка для БРИГАДИРА/оператора — сначала то, что горит."""
    if not scan_result.get("ok"):
        return f"🚨 ДИСПЕТЧЕР: заказы НЕ прочитаны — {scan_result.get('error')}"
    c = scan_result["counts"]
    lines = [f"🚚 ДИСПЕТЧЕР: заказов {scan_result['total']} · "
             f"просрочено {c['overdue']} · критично {c['critical']} · "
             f"скоро {c['warn']} · норма {c['ok']} · без дедлайна {c['unknown_deadline']}"]
    for it in scan_result["urgent"]:
        lines.append(f"   ⛔ заказ {it['order_id']}: {it['why']}")
    for it in scan_result["triage"]["unknown_deadline"]:
        lines.append(f"   ⚠️  заказ {it['order_id']}: {it['why']}")
    if not scan_result["urgent"] and not c["unknown_deadline"]:
        lines.append("   ✅ горящих нет")
    return "\n".join(lines)


if __name__ == "__main__":
    if "--charter" in sys.argv:
        print(json.dumps(CHARTER, ensure_ascii=False, indent=2))
        sys.exit(0)

    now = datetime(2026, 8, 5, 12, 0, 0)
    demo = [
        {"id": 1, "campaignId": "C1", "substatus": "STARTED",
         "delivery": {"shipments": [{"shipmentDate": "2026-08-05", "shipmentTime": "10:30:00"}]}},
        {"id": 2, "campaignId": "C1", "substatus": "STARTED",
         "delivery": {"shipments": [{"shipmentDate": "2026-08-05", "shipmentTime": "11:20:00"}]}},
        {"id": 3, "campaignId": "C1", "substatus": "STARTED",
         "delivery": {"shipments": [{"shipmentDate": "2026-08-05", "shipmentTime": "11:40:00"}]}},
        {"id": 4, "campaignId": "C1", "substatus": "READY_TO_SHIP",
         "delivery": {"shipments": [{"shipmentDate": "2026-08-05", "shipmentTime": "11:00:00"}]}},
        {"id": 5, "campaignId": "C1", "substatus": "STARTED", "delivery": {}},
    ]
    res = {"ok": True, "total": len(demo),
           "counts": {k: len(v) for k, v in triage(demo, now=now).items()},
           "triage": triage(demo, now=now)}
    res["urgent"] = res["triage"]["overdue"] + res["triage"]["critical"]
    print(f"(сухая демонстрация, сейчас {now.strftime('%H:%M')})\n")
    print(render(res))
    print("\nПредложение по просроченному (решает оператор):")
    if res["triage"]["overdue"]:
        print("  " + cancel_proposal(res["triage"]["overdue"][0])["cost_warning"])
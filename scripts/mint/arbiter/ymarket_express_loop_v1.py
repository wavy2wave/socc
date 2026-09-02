#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СТЕРЖЕНЬ ПЕТЛИ EXPRESS — недостающее звено между «заказ пришёл» и «деньги без риска».

ЗАЧЕМ. Продающая половина органа (карточка · остатки · цены · индекс) уже построена, а конец
контура — нет. Диспетчер видит горящий заказ и таймер, донор знает живое наличие, торговые руки
умеют READY_TO_SHIP — но НИКТО не собирал это в один пакет «купи ВОТ ЭТО, ВОТ ТУТ, за 1 минуту».
Без него включать остаток нельзя: это снова витрина-в-убыток. С ним продажа закрывается по
ДОКТРИНЕ ИСПОЛНЕНИЯ — выкуп у донора ТОЛЬКО после уже-оплаченного заказа, деньгами клиента.

ЧТО ДЕЛАЕТ (и чего НЕ делает).
  build_packet(order) — из оплаченного экспресс-заказа собирает пакет оператору:
      МАГАЗИН (ссылка на карго) → АДРЕС (наш пункт, куда приедет курьер) → ТОВАР (что и сколько).
      За секунды, без ошибки, без поиска. Это ДЕТЕКТОР+ПАКЕТ, не автомат: карго-заказ оператор
      оформляет руками (~1 мин), деньги двигает человек (RUBICON).
  poll(bid) — прочитать свежие PROCESSING/EXPRESS, разложить по таймеру, отдать пакеты.
  record_stitch(...) — СШИВКА: YM-заказ ↔ номер заказа на cargo-avto (proof-of-fulfillment,
      append-only). Нужна для идемпотентности: заказ со сшивкой = ALREADY_FULFILLED, не купить дважды.

ЗАКОНЫ (механические):
  E1 покупаем ТОЛЬКО после оплаты: не prepaid → action=WAIT_NOT_PAID (доктрина исполнения).
  E2 не выдумываем: offerId не даёт cargo-pid → честный warn «купи по названию», не подстановка.
  E3 идемпотентность: заказ уже сшит → ALREADY_FULFILLED (повторный выкуп = потеря денег).
  E4 0₽ и наружу ничего: весь модуль — READ + локальная сборка. RUBICON цел по построению.
  E5 сшивку двигает человек: record_stitch требует НОМЕР карго-заказа и КТО купил (иначе отказ).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import ymarket_trade_hands_v1 as trade
import ymarket_role_dispatcher_v1 as dispatcher
import donor_stock_v1 as donor

# РЕЕСТР АРТИКУЛОВ — канон связи offerId↔donor. Мягкий импорт: стержень обязан работать и без него
# (тогда offer_to_cargo падает на дно-конвенцию split('-')). Реестр только ПЕРЕКРЫВАЕТ дно для
# явно записанных (например host-префиксных) offerId — на канонных '{pid}-1' поведение неизменно.
try:
    import ymarket_registry_v1 as registry
except Exception:                                  # pragma: no cover — модуль рядом, но не роняемся
    registry = None

HERE = Path(__file__).resolve().parent            # SOCC/scripts/mint/arbiter
STITCH_PATH = HERE / "state" / "express_stitch.jsonl"

# Ссылку на донора берём из ЖИВОГО читателя наличия — единый источник, без дрейфа URL.
CARGO_URL = donor.BASE                             # "https://sp.cargo-avto.ru/catalog/{pid}/"

# Действия пакета (машиночитаемые; render превращает в человеческую карточку)
ACT_BUY = "BUY_ON_CARGO_NOW"          # оплачено → купить на карго → READY_TO_SHIP
ACT_WAIT = "WAIT_NOT_PAID"            # не предоплачено → по доктрине НЕ покупаем
ACT_DONE = "ALREADY_FULFILLED"        # уже сшито → не покупать повторно (E3)
ACT_ESCALATE = "ESCALATE"             # нет позиций/битые данные → нужен человек


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ── offerId → карго ──────────────────────────────────────────────────────────
# Соглашение органа: наш offerId '9603273-1' → база '9603273' = pid карго (тот же split,
# что в donor_stock и from_xlsx). База должна быть числовой pid; иначе честный отказ (E2).

def offer_to_cargo(offer_id):
    """offerId → {pid, url} или None. Нечисловая база (например TEST-...) → None (не выдумываем).

    Сначала спрашиваем РЕЕСТР (resolve_cargo): он ПЕРЕКРЫВАЕТ дно-конвенцию для явно записанных
    (host-префиксных) offerId, возвращая сохранённый donor_pid/url. Реестр недоступен/молчит/упал →
    падаем на канон-конвенцию split('-')[0]+isdigit. На голом '{pid}-1' обе ветки дают ОДНО и то же,
    поэтому поведение канонных offerId не меняется и без реестра (нулевой риск слома, E4).
    """
    if registry is not None:
        try:
            hit = registry.resolve_cargo(offer_id)
            if hit:
                return hit
        except Exception:
            pass                                   # реестр упал — не роняем стержень, идём на дно
    base = str(offer_id or "").split("-")[0].strip()
    if not base or not base.isdigit():
        return None
    return {"pid": base, "url": CARGO_URL.format(pid=base)}


def _order_lines(order, stock_map=None):
    """Позиции заказа → строки пакета. stock_map (опц.) = {pid: {status,...}} живого наличия."""
    lines = []
    for it in order.get("items") or []:
        oid = it.get("offerId") or it.get("shopSku")
        cargo = offer_to_cargo(oid)
        line = {
            "our_offer_id": oid,
            "our_name": it.get("offerName"),          # НАШЕ наименование (то, что видит клиент)
            "count": it.get("count"),
            "buyer_price": it.get("buyerPrice") or it.get("price"),
            "cargo": cargo,
        }
        if cargo is None:
            line["warn"] = "offerId не даёт cargo-pid — купить вручную по названию (E2)"
        elif stock_map is not None:
            line["donor_stock"] = (stock_map.get(cargo["pid"]) or {}).get("status")
        lines.append(line)
    return lines


# ── пункт выдачи (АДРЕС) ──────────────────────────────────────────────────────

def resolve_pickup(business_id, warehouses_fn=None):
    """Живой Express-склад = наш пункт (куда приедет курьер за товаром). READ, 0₽.

    Адрес НЕ хардкодим: читаем из кабинета. Сеть/ключ упали → честный ok=False (E4/L3),
    оператор подтверждает пункт в кабинете, а пакет всё равно годен (МАГАЗИН→ТОВАР есть).
    """
    if not business_id:
        return {"ok": False, "error": "businessId неизвестен",
                "note": "адрес пункта подтвердить в кабинете"}
    fn = warehouses_fn or trade.express_warehouses
    try:
        whs = fn(business_id)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "note": "склад не прочитан — адрес пункта подтвердить в кабинете"}
    if not whs:
        return {"ok": False, "error": "нет включённого Express-склада",
                "note": "включить модель EXPRESS на складе (кабинет)"}
    w = whs[0]
    return {"ok": True, "warehouse_id": w.get("id"), "name": w.get("name"),
            "city": w.get("city"), "address": w.get("address"), "gps": w.get("gps")}


# ── пакет одного заказа ───────────────────────────────────────────────────────

def build_packet(order, pickup=None, zone_info=None, stock_map=None, stitched=None):
    """Оплаченный экспресс-заказ → пакет оператору (МАГАЗИН→АДРЕС→ТОВАР). Чистая сборка, 0₽.

    pickup     — результат resolve_pickup (общий на прогон); zone_info — из _zone_lookup (таймер);
    stock_map  — живое наличие донора (опц.); stitched — существующая сшивка (E3, идемпотентность).
    """
    oid = order.get("id") or order.get("orderId")
    cid = order.get("campaignId") or order.get("campaign_id")
    status = order.get("status")
    substatus = order.get("substatus")
    payment = order.get("paymentType") or order.get("paymentMethod")
    # Экспресс — предоплатный. Честно: PREPAID явно, ИЛИ статус PROCESSING (Маркет уже взял деньги).
    prepaid = (payment == "PREPAID") or (status == trade.ORDER_PROCESSING)

    lines = _order_lines(order, stock_map=stock_map)
    zi = zone_info or {}

    if stitched:
        action = ACT_DONE
        note = f"по заказу уже есть сшивка (карго №{stitched.get('cargo_order')}) — НЕ покупать повторно (E3)"
    elif not prepaid:
        action = ACT_WAIT
        note = "заказ не предоплачен — по доктрине покупаем ТОЛЬКО после оплаты (E1)"
    elif not lines:
        action = ACT_ESCALATE
        note = "в заказе нет позиций — нечего покупать, нужен человек"
    else:
        action = ACT_BUY
        note = ("оплачено клиентом → оформить на cargo-avto на самовывоз в наш пункт, "
                "затем отметить READY_TO_SHIP до конца таймера")

    return {
        "order_id": oid, "campaign_id": cid,
        "status": status, "substatus": substatus,
        "prepaid": prepaid, "payment": payment,
        "deadline": zi.get("deadline"), "minutes_left": zi.get("minutes_left"),
        "zone": zi.get("zone"),
        "pickup": pickup,
        "lines": lines,
        "action": action, "note": note,
        "stitch": stitched,
        "built_at": _now_iso(),
    }


def _zone_lookup(orders, now=None):
    """order_id → {zone, minutes_left, deadline} через dispatcher.triage (не дублируем таймер)."""
    tri = dispatcher.triage(orders, now=now)
    lut = {}
    for _bucket, items in tri.items():
        for it in items:
            lut[it["order_id"]] = {"zone": it.get("zone"),
                                   "minutes_left": it.get("minutes_left"),
                                   "deadline": it.get("deadline")}
    return lut


def poll(business_id, now=None, orders_fn=None, warehouses_fn=None,
         check_stock=False, stitch_path=None):
    """Прочитать свежие экспресс-заказы → собрать пакеты. READ, 0₽, наружу ничего (E4).

    Fail-soft: заказы не прочитались → ok=False с причиной, НЕ пустой «заказов нет»
    (пустота тут означала бы «покупать нечего» — опасная ложь на деньгах).
    """
    fn = orders_fn or trade.new_express_orders
    try:
        orders = fn(business_id)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "note": "заказы НЕ прочитаны — не считаем, что заказов нет"}

    pickup = resolve_pickup(business_id, warehouses_fn=warehouses_fn)
    lut = _zone_lookup(orders, now=now)

    # Живое наличие донора — опционально (сеть к карго). Собираем pid одним пучком.
    stock_map = None
    if check_stock and orders:
        pids = []
        for o in orders:
            for it in o.get("items") or []:
                c = offer_to_cargo(it.get("offerId") or it.get("shopSku"))
                if c:
                    pids.append(c["pid"])
        if pids:
            try:
                stock_map = donor.stock_for(sorted(set(pids)))
            except Exception:
                stock_map = None       # наличие не прочли — строки просто без donor_stock (fail-soft)

    packets = []
    for o in orders or []:
        oid = o.get("id") or o.get("orderId")
        st = find_stitch(oid, path=stitch_path)
        packets.append(build_packet(o, pickup=pickup, zone_info=lut.get(oid),
                                    stock_map=stock_map, stitched=st))

    to_buy = [p for p in packets if p["action"] == ACT_BUY]
    return {"ok": True, "total": len(orders or []), "to_buy": len(to_buy),
            "pickup": pickup, "packets": packets}


# ── СШИВКА (proof-of-fulfillment) ─────────────────────────────────────────────

def _stitch_path(path=None):
    return Path(path) if path else STITCH_PATH


def record_stitch(order_id, cargo_order, by, campaign_id=None, lines=None, note=None, path=None):
    """Сшить YM-заказ ↔ заказ на cargo-avto (оператор купил РУКАМИ). append-only, 0₽.

    E5: денег не двигает, наружу ничего не шлёт — фиксирует ФАКТ, что человек уже оформил
    выкуп. Без номера карго-заказа и без «кто купил» — отказ (не выдумываем чужой факт).
    """
    if not order_id:
        raise ValueError("сшивка: нет order_id — не к чему привязать")
    if not cargo_order:
        raise ValueError("сшивка: нет номера заказа cargo-avto — не выдумываем (E5)")
    if not by:
        raise ValueError("сшивка: не указан человек (by) — выкуп оформил человек (RUBICON/E5)")
    rec = {"at": _now_iso(), "order_id": str(order_id),
           "campaign_id": str(campaign_id) if campaign_id else None,
           "cargo_order": str(cargo_order), "lines": lines or [], "by": by, "note": note}
    p = _stitch_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_stitch(path=None):
    """Все сшивки (append-only jsonl). Битую строку пропускаем, не роняем чтение."""
    p = _stitch_path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def find_stitch(order_id, path=None):
    """Последняя сшивка по заказу или None (для идемпотентности E3)."""
    if not order_id:
        return None
    recs = [r for r in read_stitch(path) if str(r.get("order_id")) == str(order_id)]
    return recs[-1] if recs else None


# ── человеческий вид ──────────────────────────────────────────────────────────

def render_packet(p):
    """Карточка оператора на 1 минуту: что купить, где, куда, сколько осталось."""
    head = f"📦 ЗАКАЗ {p.get('order_id')} · {p.get('action')}"
    ml = p.get("minutes_left")
    if ml is not None:
        head += f" · осталось ~{ml} мин ({p.get('zone')})"
    out = [head]
    pk = p.get("pickup") or {}
    if pk.get("ok"):
        addr = ", ".join(x for x in (pk.get("city"), pk.get("address")) if x)
        out.append(f"   📍 пункт (куда приедет курьер): {pk.get('name')} — {addr}")
    elif pk and not pk.get("ok"):
        out.append(f"   📍 пункт: подтвердить в кабинете ({pk.get('error')})")
    for ln in p.get("lines") or []:
        c = ln.get("cargo") or {}
        stock = ln.get("donor_stock")
        stock_s = f" · донор: {stock}" if stock is not None else ""
        out.append(f"   🛒 ×{ln.get('count')}: {ln.get('our_name') or ln.get('our_offer_id')}{stock_s}")
        out.append(f"      {c.get('url') or '— нет cargo-pid: ищи по названию (E2)'}")
    out.append(f"   → {p.get('note')}")
    return "\n".join(out)


def render(poll_result):
    """Сводка прогона для БРИГАДИРА/фида — сначала то, что к выкупу."""
    if not poll_result.get("ok"):
        return f"🚨 ПЕТЛЯ EXPRESS: заказы НЕ прочитаны — {poll_result.get('error')}"
    if not poll_result["total"]:
        return "✅ ПЕТЛЯ EXPRESS: новых экспресс-заказов нет"
    out = [f"🔁 ПЕТЛЯ EXPRESS: заказов {poll_result['total']} · к выкупу {poll_result['to_buy']}"]
    # сначала горящие/к выкупу, потом остальное
    order_key = {ACT_BUY: 0, ACT_ESCALATE: 1, ACT_WAIT: 2, ACT_DONE: 3}
    for p in sorted(poll_result["packets"], key=lambda x: order_key.get(x["action"], 9)):
        out.append(render_packet(p))
    return "\n\n".join(out)


if __name__ == "__main__":
    if "--charter" in sys.argv:
        print("ПЕТЛЯ EXPRESS — стержень исполнения (детектор+пакет, не автомат).")
        print("Законы: E1 только после оплаты · E2 не выдумываем pid · E3 идемпотентность · "
              "E4 0₽/наружу ничего · E5 сшивку двигает человек")
        sys.exit(0)

    # Сухая демонстрация (0₽, наружу ничего): один оплаченный экспресс-заказ.
    now = datetime(2026, 8, 12, 12, 0, 0)
    demo_orders = [{
        "id": 777001, "campaignId": "149215943", "status": "PROCESSING", "substatus": "STARTED",
        "paymentType": "PREPAID",
        "delivery": {"shipments": [{"shipmentDate": "2026-08-12", "shipmentTime": "11:35:00"}]},
        "items": [
            {"offerId": "9603273-1", "offerName": "Плёнка тонировочная Карбон 3D, рулон 1.5×0.5 м",
             "count": 1, "buyerPrice": 1490},
            {"offerId": "TEST-NOPID", "offerName": "Позиция без cargo-pid", "count": 2, "buyerPrice": 500},
        ],
    }]
    pickup = {"ok": True, "warehouse_id": 2390811, "name": "Атлас",
              "city": "Москва", "address": "Вавилова 9Ас8"}
    lut = _zone_lookup(demo_orders, now=now)
    packets = [build_packet(o, pickup=pickup, zone_info=lut.get(o["id"])) for o in demo_orders]
    res = {"ok": True, "total": len(demo_orders),
           "to_buy": sum(1 for p in packets if p["action"] == ACT_BUY),
           "pickup": pickup, "packets": packets}
    print("ПЕТЛЯ EXPRESS — сухая демонстрация (0₽, наружу ничего)\n")
    print(render(res))

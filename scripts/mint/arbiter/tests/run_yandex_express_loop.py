#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЯНДЕКС ПРИЁМКА — СТЕРЖЕНЬ ПЕТЛИ EXPRESS. Сухо, 0₽, без сети.

Проверяем ЗАКОНЫ стержня, а не «запустилось». Каждый тест падает при нарушении закона.

  EL1  offer_to_cargo_maps      — числовой offerId '9603273-1' → pid '9603273' + верный cargo-URL
  EL2  offer_to_cargo_refuses   — нечисловая база (TEST-...) → None (E2, не выдумываем pid)
  EL3  paid_order_is_buy        — оплаченный (PREPAID/PROCESSING) → action=BUY_ON_CARGO_NOW
  EL4  unpaid_order_waits       — не предоплачен → WAIT_NOT_PAID (E1, доктрина исполнения)
  EL5  stitched_is_idempotent   — заказ со сшивкой → ALREADY_FULFILLED (E3, не купить дважды)
  EL6  no_items_escalates       — оплачен, но без позиций → ESCALATE (не покупаем из воздуха)
  EL7  packet_has_shop_addr_prod— в BUY-пакете есть МАГАЗИН(url)+АДРЕС(pickup)+ТОВАР(count/name)
  EL8  nopid_line_warns         — позиция без cargo-pid несёт warn, но пакет живёт (E2 на строке)
  EL9  poll_read_only           — poll не пишет наружу и не роняется (READ, 0₽, E4) через монкипатч
  EL10 poll_fail_soft           — заказы не прочитались → ok=False с причиной, НЕ пустой «заказов нет»
  EL11 stitch_requires_facts    — record_stitch без cargo_order/by → отказ (E5, факт человека)
  EL12 stitch_roundtrip         — записанная сшивка находится find_stitch (идемпотентность реальна)
  EL13 zone_from_dispatcher     — таймер берётся из dispatcher.triage (не свой), minutes_left проставлен
  EL14 render_smoke             — render/render_packet на разных входах не падают, несут заголовок
  EL15 rubicon_no_live_in_build — build_packet чист: не зовёт сеть даже если руки-швы взорвать
"""
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
SCRIPTS = MINT.parent
for p in (str(ARB), str(MINT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_express_loop_v1 as loop     # noqa: E402
import ymarket_trade_hands_v1 as trade     # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


NOW = datetime(2026, 8, 12, 12, 0, 0)

PAID_ORDER = {
    "id": 777001, "campaignId": "149215943", "status": "PROCESSING", "substatus": "STARTED",
    "paymentType": "PREPAID",
    "delivery": {"shipments": [{"shipmentDate": "2026-08-12", "shipmentTime": "11:35:00"}]},
    "items": [
        {"offerId": "9603273-1", "offerName": "Плёнка Карбон 3D", "count": 1, "buyerPrice": 1490},
        {"offerId": "TEST-NOPID", "offerName": "Без pid", "count": 2, "buyerPrice": 500},
    ],
}
PICKUP = {"ok": True, "warehouse_id": 2390811, "name": "Атлас",
          "city": "Москва", "address": "Вавилова 9Ас8"}


def el1_offer_to_cargo_maps():
    c = loop.offer_to_cargo("9603273-1")
    ok = c and c["pid"] == "9603273" and c["url"] == "https://sp.cargo-avto.ru/catalog/9603273/"
    return bool(ok), f"{c}"


def el2_offer_to_cargo_refuses():
    bad = [loop.offer_to_cargo(x) for x in ("TEST-NOPID", "", None, "abc-1", "  ")]
    return all(b is None for b in bad), f"нечисловые базы → {bad} (ждём все None)"


def el3_paid_order_is_buy():
    p = loop.build_packet(PAID_ORDER, pickup=PICKUP)
    return p["action"] == loop.ACT_BUY, f"action={p['action']} prepaid={p['prepaid']}"


def el4_unpaid_order_waits():
    unpaid = dict(PAID_ORDER, status="PLACED", substatus=None, paymentType="POSTPAID")
    p = loop.build_packet(unpaid, pickup=PICKUP)
    return p["action"] == loop.ACT_WAIT, f"action={p['action']} (ждём WAIT_NOT_PAID)"


def el5_stitched_is_idempotent():
    p = loop.build_packet(PAID_ORDER, pickup=PICKUP,
                          stitched={"cargo_order": "CARGO-42", "by": "оператор"})
    return p["action"] == loop.ACT_DONE, f"action={p['action']} (ждём ALREADY_FULFILLED)"


def el6_no_items_escalates():
    empty = dict(PAID_ORDER, items=[])
    p = loop.build_packet(empty, pickup=PICKUP)
    return p["action"] == loop.ACT_ESCALATE, f"action={p['action']} (ждём ESCALATE)"


def el7_packet_has_shop_addr_prod():
    p = loop.build_packet(PAID_ORDER, pickup=PICKUP)
    line0 = p["lines"][0]
    has_shop = bool((line0.get("cargo") or {}).get("url"))
    has_addr = bool((p.get("pickup") or {}).get("address"))
    has_prod = line0.get("count") == 1 and bool(line0.get("our_name"))
    return (has_shop and has_addr and has_prod), \
        f"МАГАЗИН={has_shop} АДРЕС={has_addr} ТОВАР={has_prod}"


def el8_nopid_line_warns():
    p = loop.build_packet(PAID_ORDER, pickup=PICKUP)
    nopid = [ln for ln in p["lines"] if ln.get("cargo") is None]
    ok = len(nopid) == 1 and "warn" in nopid[0] and p["action"] == loop.ACT_BUY
    return ok, f"строк_без_pid={len(nopid)} warn_есть={bool(nopid and 'warn' in nopid[0])} пакет_жив={p['action']}"


def el9_poll_read_only():
    """poll с подменёнными швами: сеть не трогается, наружу ничего, пакеты собраны."""
    writes = {"hit": False}

    def fake_orders(bid):
        return [PAID_ORDER]

    def fake_wh(bid):
        return [{"id": 2390811, "name": "Атлас", "city": "Москва",
                 "address": "Вавилова 9Ас8", "express": True}]

    # взрыв на любой записи наружу — если стержень попытается писать, тест падёт
    orig_stocks = trade.update_stocks
    orig_status = trade.set_order_status

    def bomb(*a, **k):
        writes["hit"] = True
        raise AssertionError("стержень попытался ЗАПИСЬ наружу — нарушение E4")

    trade.update_stocks = bomb
    trade.set_order_status = bomb
    try:
        res = loop.poll("216949599", now=NOW, orders_fn=fake_orders,
                        warehouses_fn=fake_wh, check_stock=False,
                        stitch_path="/tmp/__nonexistent_stitch__.jsonl")
    finally:
        trade.update_stocks = orig_stocks
        trade.set_order_status = orig_status
    ok = (res["ok"] and res["total"] == 1 and res["to_buy"] == 1 and not writes["hit"])
    return ok, f"ok={res.get('ok')} to_buy={res.get('to_buy')} запись_наружу={writes['hit']}"


def el10_poll_fail_soft():
    def boom(bid):
        raise RuntimeError("сеть к Маркету упала")
    res = loop.poll("216949599", now=NOW, orders_fn=boom)
    ok = (res.get("ok") is False and "error" in res and "не считаем" in res.get("note", ""))
    return ok, f"ok={res.get('ok')} есть_причина={'error' in res} (пустого 'заказов нет' быть не должно)"


def el11_stitch_requires_facts():
    bad = 0
    for kw in ({"order_id": "1", "cargo_order": "", "by": "оп"},
               {"order_id": "1", "cargo_order": "C1", "by": ""},
               {"order_id": "", "cargo_order": "C1", "by": "оп"}):
        try:
            loop.record_stitch(**kw, path="/tmp/__never__.jsonl")
        except ValueError:
            bad += 1
    return bad == 3, f"отказов на неполных фактах={bad}/3 (E5)"


def el12_stitch_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        p = str(Path(d) / "stitch.jsonl")
        rec = loop.record_stitch("777001", "CARGO-999", by="оператор",
                                 campaign_id="149215943", path=p)
        found = loop.find_stitch("777001", path=p)
        miss = loop.find_stitch("000000", path=p)
        ok = (rec["cargo_order"] == "CARGO-999" and found and
              found["cargo_order"] == "CARGO-999" and miss is None)
    return bool(ok), f"записано_и_найдено={bool(found)} чужой_заказ_None={miss is None}"


def el13_zone_from_dispatcher():
    lut = loop._zone_lookup([PAID_ORDER], now=NOW)
    zi = lut.get(777001)
    p = loop.build_packet(PAID_ORDER, pickup=PICKUP, zone_info=zi)
    # 11:35 shipment + 60 grace = 12:35 hard; now 12:00 → ~35 мин
    ok = zi and zi["minutes_left"] == 35.0 and p["minutes_left"] == 35.0
    return bool(ok), f"minutes_left={zi.get('minutes_left') if zi else None} (ждём 35.0)"


def el14_render_smoke():
    try:
        good = loop.render(loop.poll("B", now=NOW, orders_fn=lambda b: [PAID_ORDER],
                                     warehouses_fn=lambda b: [], stitch_path="/tmp/__x__.jsonl"))
        empty = loop.render(loop.poll("B", now=NOW, orders_fn=lambda b: []))
        failed = loop.render({"ok": False, "error": "тест"})
        one = loop.render_packet(loop.build_packet(PAID_ORDER, pickup=PICKUP))
    except Exception as e:
        return False, f"render упал: {type(e).__name__}: {e}"
    ok = ("ПЕТЛЯ EXPRESS" in good and "нет" in empty and "НЕ прочитаны" in failed
          and "ЗАКАЗ" in one)
    return ok, f"заголовок={('ПЕТЛЯ EXPRESS' in good)} пусто_честно={('нет' in empty)}"


def el15_rubicon_no_live_in_build():
    """build_packet — чистая сборка: даже если руки-швы взорвать, она их не зовёт."""
    orig_wh = trade.express_warehouses
    orig_ord = trade.new_express_orders
    tripped = {"hit": False}

    def bomb(*a, **k):
        tripped["hit"] = True
        raise AssertionError("build_packet зовёт живой READ — нарушение E4")

    trade.express_warehouses = bomb
    trade.new_express_orders = bomb
    try:
        p = loop.build_packet(PAID_ORDER, pickup=PICKUP)
    finally:
        trade.express_warehouses = orig_wh
        trade.new_express_orders = orig_ord
    return (p["action"] == loop.ACT_BUY and not tripped["hit"]), \
        f"живой_READ_в_build={tripped['hit']} (ждём False)"


TESTS = [
    ("EL1  offer_to_cargo_maps", el1_offer_to_cargo_maps),
    ("EL2  offer_to_cargo_refuses", el2_offer_to_cargo_refuses),
    ("EL3  paid_order_is_buy", el3_paid_order_is_buy),
    ("EL4  unpaid_order_waits", el4_unpaid_order_waits),
    ("EL5  stitched_is_idempotent", el5_stitched_is_idempotent),
    ("EL6  no_items_escalates", el6_no_items_escalates),
    ("EL7  packet_has_shop_addr_prod", el7_packet_has_shop_addr_prod),
    ("EL8  nopid_line_warns", el8_nopid_line_warns),
    ("EL9  poll_read_only", el9_poll_read_only),
    ("EL10 poll_fail_soft", el10_poll_fail_soft),
    ("EL11 stitch_requires_facts", el11_stitch_requires_facts),
    ("EL12 stitch_roundtrip", el12_stitch_roundtrip),
    ("EL13 zone_from_dispatcher", el13_zone_from_dispatcher),
    ("EL14 render_smoke", el14_render_smoke),
    ("EL15 rubicon_no_live_in_build", el15_rubicon_no_live_in_build),
]


def main():
    print("🎯 ЯНДЕКС ПРИЁМКА · СТЕРЖЕНЬ ПЕТЛИ EXPRESS (сухо, 0₽, без сети)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<32} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Пакет МАГАЗИН→АДРЕС→ТОВАР честен; покупаем только после оплаты (E1); "
              "идемпотентно (E3); RUBICON цел (0 сети/0 записи).")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

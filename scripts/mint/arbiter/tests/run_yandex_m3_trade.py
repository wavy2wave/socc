#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА ЯНДЕКС M3 — торговые руки (склады · остатки · цены · заказы · тарифы · регионы).

Фальсифицируемо: каждый тест ловит КОНКРЕТНУЮ ложь, которую руки могли бы сказать.
Сеть НЕ трогаем — подменяем шов hands._http_call (тот же приём, что в M1/M2).
Запуск: python3 tests/run_yandex_m3_trade.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_hands_v1 as hands            # noqa: E402
import ymarket_trade_hands_v1 as trade      # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))


class FakeNet:
    """Подмена сетевого шва: копит запросы, отдаёт заготовленные ответы."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, method, url, headers, body, params, timeout):
        self.calls.append({"method": method, "url": url, "body": body, "params": params})
        payload = self.replies.pop(0) if self.replies else {"result": {}}
        return hands._Resp(200, payload, json.dumps(payload))


def with_net(replies, key="test-key"):
    """Контекст: фальшивая сеть + управляемый ключ.

    Герметичность: при key=None НЕ достаточно просто выкинуть env-переменную — creds_present()
    зовёт _ensure_env(), который дозагрузит ЖИВОЙ ключ из gitignored .env и тест «нет ключа»
    станет ложно-зелёным. Поэтому на время теста замораживаем _ENV_TRIED=True (делаем _ensure_env
    no-op), чтобы .env не перебивал волю теста. Всё аккуратно возвращаем в restore().
    """
    old_call = hands._http_call
    old_key = os.environ.get("YANDEX_MARKET_API_KEY")
    old_tried = hands._ENV_TRIED
    net = FakeNet(replies)
    hands._http_call = net
    if key:
        os.environ["YANDEX_MARKET_API_KEY"] = key
    else:
        hands._ENV_TRIED = True                      # _ensure_env → no-op: .env не перезагрузит ключ
        os.environ.pop("YANDEX_MARKET_API_KEY", None)
    return net, (old_call, old_key, old_tried)


def restore(saved):
    old_call, old_key, old_tried = saved
    hands._http_call = old_call
    hands._ENV_TRIED = old_tried
    if old_key is None:
        os.environ.pop("YANDEX_MARKET_API_KEY", None)
    else:
        os.environ["YANDEX_MARKET_API_KEY"] = old_key


print("ПРИЁМКА ЯНДЕКС M3 — торговые руки органа М6\n")

# ---------------------------------------------------------------- L1: гейт записи
print("L1 · двойной гейт записи (не dry AND commit)")

net, saved = with_net([])
try:
    r = trade.update_stocks("B1", [{"sku": "S1", "warehouse_id": 1, "count": 5}],
                            dry=True, commit=True)
    check("dry=True + commit=True → наружу НЕ идёт", r["sent"] is False and not net.calls)

    r = trade.update_stocks("B1", [{"sku": "S1", "warehouse_id": 1, "count": 5}],
                            dry=False, commit=False)
    check("dry=False + commit=False → наружу НЕ идёт", r["sent"] is False and not net.calls)

    r = trade.mark_ready_to_ship("C1", 42, dry=False, commit=False)
    check("статус заказа без commit → НЕ идёт", r["sent"] is False and not net.calls)

    r = trade.set_warehouse_model("B1", 7, "EXPRESS", True, dry=False, commit=False)
    check("включение ЭКСПРЕССА без commit → НЕ идёт", r["sent"] is False and not net.calls)
finally:
    restore(saved)

# без ключа реальная запись должна ОТКАЗАТЬ, а не притворяться успехом
net, saved = with_net([], key=None)
try:
    try:
        trade.update_stocks("B1", [{"sku": "S1", "warehouse_id": 1, "count": 5}],
                            dry=False, commit=True)
        check("нет ключа + commit → отказ", False, "прошло без отказа")
    except trade.WriteRefused as e:
        check("нет ключа + commit → WriteRefused", "YANDEX_MARKET_API_KEY" in str(e))
    check("нет ключа → в сеть не полезли", not net.calls)
finally:
    restore(saved)

# ---------------------------------------------------------------- L4: потолки батчей
print("\nL4 · потолки батчей Маркета ловим ДО сети")

net, saved = with_net([])
try:
    big = [{"sku": f"S{i}", "warehouse_id": 1, "count": 1} for i in range(trade.MAX_STOCKS_BATCH + 1)]
    try:
        trade.update_stocks("B1", big, dry=False, commit=True)
        check("остатки >2000 → отказ", False, "потолок не сработал")
    except trade.WriteRefused as e:
        check("остатки >2000 → WriteRefused", "2000" in str(e))
    check("превышение потолка → сеть не тронута", not net.calls)

    bigp = [{"sku": f"S{i}", "value": 100} for i in range(trade.MAX_PRICES_BATCH + 1)]
    try:
        trade.update_prices("B1", bigp, dry=False, commit=True)
        check("цены >500 → отказ", False, "потолок не сработал")
    except trade.WriteRefused as e:
        check("цены >500 → WriteRefused", "500" in str(e))
finally:
    restore(saved)

# ---------------------------------------------------------------- L3: не выдумываем
print("\nL3 · неполные данные → отказ, не подстановка")

net, saved = with_net([])
try:
    for bad, why in (({"sku": "S1", "count": 5}, "нет warehouse_id"),
                     ({"warehouse_id": 1, "count": 5}, "нет sku"),
                     ({"sku": "S1", "warehouse_id": 1}, "нет count")):
        try:
            trade.update_stocks("B1", [bad], dry=True)
            check(f"остатки: {why} → отказ", False, "прошло")
        except trade.WriteRefused:
            check(f"остатки: {why} → WriteRefused", True)

    try:
        trade.update_stocks(None, [{"sku": "S1", "warehouse_id": 1, "count": 1}], dry=True)
        check("нет businessId → отказ", False, "прошло")
    except trade.WriteRefused as e:
        check("нет businessId → WriteRefused", "businessId" in str(e))

    try:
        trade.update_prices("B1", [{"sku": "S1", "value": 0}], dry=True)
        check("цена 0 → отказ", False, "прошло")
    except trade.WriteRefused:
        check("цена ≤0 → WriteRefused", True)

    try:
        trade.verify_eac("C1", 1, "", dry=True)
        check("пустой код ЭАПП → отказ", False, "прошло")
    except trade.WriteRefused:
        check("пустой код ЭАПП → WriteRefused (не подбираем)", True)
finally:
    restore(saved)

# ------------------------------------------------- зачёркнутая цена: правило Маркета 5–99%
print("\nЦены · discountBase по правилам Маркета (5–99%)")

net, saved = with_net([])
try:
    try:
        trade.update_prices("B1", [{"sku": "S1", "value": 1500, "discount_base": 1000}], dry=True)
        check("discountBase ниже цены → отказ", False, "прошло")
    except trade.WriteRefused as e:
        check("discountBase < цены → WriteRefused", "БОЛЬШЕ" in str(e))

    try:  # скидка 2% — вне 5–99
        trade.update_prices("B1", [{"sku": "S1", "value": 980, "discount_base": 1000}], dry=True)
        check("скидка 2% → отказ", False, "прошло")
    except trade.WriteRefused as e:
        check("скидка <5% → WriteRefused (Маркет отклонил бы)", "5" in str(e))

    r = trade.update_prices("B1", [{"sku": "S1", "value": 1500, "discount_base": 2000}], dry=True)
    p = r["payload"]["offers"][0]["price"]
    check("валидная скидка 25% проходит", p["discountBase"] == 2000 and p["value"] == 1500.0)
    check("валюта всегда RUR", p["currencyId"] == "RUR")
finally:
    restore(saved)

# ---------------------------------------------------------------- L5: склад не создаём
print("\nL5 · создание склада через API — честный отказ")
r = trade.create_warehouse_refused()
check("create_warehouse → ok=False", r["ok"] is False)
check("причина машиночитаема", r["reason"] == "API_METHOD_ABSENT")
check("требует действия оператора", r["operator_action_required"] is True)
check("объяснение по-человечески непустое", len(r["human"]) > 40)

# ---------------------------------------------------------------- реальные payload'ы
print("\nФорма payload — точно по спецификации Маркета")

net, saved = with_net([{"result": {}}])
try:
    r = trade.update_stocks("B77", [{"sku": "S1", "warehouse_id": 9, "count": 0}],
                            dry=False, commit=True)
    call = net.calls[0]
    check("остатки: путь v3 businesses/offers/stocks/update",
          call["url"].endswith("/v3/businesses/B77/offers/stocks/update"), call["url"])
    row = call["body"]["skuItems"][0]
    check("остатки: ключ skuItems + partnerWarehouseId",
          row["partnerWarehouseId"] == 9 and row["sku"] == "S1")
    check("остатки: count=0 разрешён (снятие с продажи)", row["count"] == 0)
    check("остатки: updatedAt не выдуман", "updatedAt" not in row)
    check("остатки: ok=True при пустых errors", r["ok"] is True)
finally:
    restore(saved)

net, saved = with_net([{"result": {}}])
try:
    trade.mark_ready_to_ship("C55", 4242, dry=False, commit=True)
    call = net.calls[0]
    check("заказ: метод PUT", call["method"] == "PUT")
    check("заказ: путь campaigns/orders/status",
          call["url"].endswith("/v2/campaigns/C55/orders/4242/status"), call["url"])
    check("заказ: тело {order:{status,substatus}}",
          call["body"]["order"] == {"status": "PROCESSING", "substatus": "READY_TO_SHIP"})
finally:
    restore(saved)

# ---------------------------------------------------------------- L2: 200 ≠ успех
print("\nL2 · 200 с errors в теле = НЕ успех")

net, saved = with_net([{"result": {"errors": [{"message": "склад не найден"}]}}])
try:
    r = trade.update_stocks("B1", [{"sku": "S1", "warehouse_id": 1, "count": 5}],
                            dry=False, commit=True)
    check("HTTP 200 + errors → ok=False", r["ok"] is False)
    check("текст ошибки Маркета донесён", "склад не найден" in r["errors"])
finally:
    restore(saved)

net, saved = with_net([{"result": {"warnings": [{"message": "укажите vendor"}]}}])
try:
    r = trade.update_prices("B1", [{"sku": "S1", "value": 100}], dry=False, commit=True)
    check("warnings не рушат ok", r["ok"] is True and "укажите vendor" in r["warnings"])
finally:
    restore(saved)

# ---------------------------------------------------------------- чтение: склады/остатки
print("\nЧтение · склады, остатки, регионы, заказы")

WH = {"result": {"warehouses": [
    {"id": 101, "name": "МСК Юг", "models": [{"placementType": "EXPRESS",
                                              "apiAvailability": "ENABLED"}],
     "address": {"city": "Москва", "street": "Ленина", "number": "1",
                 "gps": {"latitude": 55.7, "longitude": 37.6}}},
    {"id": 102, "name": "Склад FBS", "models": [{"placementType": "FBS",
                                                 "apiAvailability": "ENABLED"}],
     "address": {"city": "Москва"}},
]}}
net, saved = with_net([WH, WH])
try:
    ws = trade.warehouses("B1")
    check("склады: распознаны оба", len(ws) == 2)
    check("склады: EXPRESS определён флагом", ws[0]["express"] is True and ws[1]["express"] is False)
    check("склады: город и gps прочитаны",
          ws[0]["city"] == "Москва" and ws[0]["gps"]["lat"] == 55.7)
    ex = trade.express_warehouses("B1")
    check("express_warehouses фильтрует только Экспресс", len(ex) == 1 and ex[0]["id"] == 101)
finally:
    restore(saved)

net, saved = with_net([{"result": {"skuItems": [
    {"sku": "S1", "count": 12, "updatedAt": "2026-08-05T10:00:00Z"}]}}])
try:
    st = trade.read_stocks("B1", 101)
    check("чтение остатков: sku+count+updatedAt",
          st[0]["sku"] == "S1" and st[0]["count"] == 12 and st[0]["updatedAt"])
finally:
    restore(saved)

net, saved = with_net([{"result": {"regions": [
    {"id": 213, "name": "Москва", "type": "CITY",
     "parent": {"name": "Москва и область", "parent": {"name": "Россия"}}}]}}])
try:
    rg = trade.find_region("Москва")
    check("регион: id и тип CITY", rg[0]["id"] == 213 and rg[0]["type"] == "CITY")
    check("регион: цепочка родителей от страны",
          rg[0]["parent_path"] == "Россия / Москва и область", rg[0]["parent_path"])
finally:
    restore(saved)

net, saved = with_net([{"result": {"orders": [{"id": 1, "status": "PROCESSING"}],
                                  "paging": {"nextPageToken": "tok"}}}])
try:
    got = trade.new_express_orders("B1")
    call = net.calls[0]
    check("заказы: путь v1 businesses/orders",
          call["url"].endswith("/v1/businesses/B1/orders"), call["url"])
    check("заказы: фильтр programTypes=EXPRESS",
          call["body"]["programTypes"] == ["EXPRESS"])
    check("заказы: статус PROCESSING", call["body"]["statuses"] == ["PROCESSING"])
    check("заказы: список вернулся", len(got) == 1)
finally:
    restore(saved)

# ---------------------------------------------------------------- тарифы: маржа до залива
print("\nТарифы · калькулятор Маркета (маржа ДО залива)")

net, saved = with_net([{"result": {"offers": [{"tariffs": [
    {"type": "FEE", "amount": 150.0},
    {"type": "EXPRESS_DELIVERY", "amount": 120.0}]}]}}])
try:
    t = trade.calc_tariffs([{"category_id": 100, "price": 1500, "weight": 1.2,
                             "length": 30, "width": 20, "height": 10}])
    call = net.calls[0]
    check("тарифы: путь v2/tariffs/calculate",
          call["url"].endswith("/v2/tariffs/calculate"), call["url"])
    check("тарифы: sellingProgram=EXPRESS",
          call["body"]["parameters"]["sellingProgram"] == "EXPRESS")
    check("тарифы: campaignId и sellingProgram НЕ вместе",
          "campaignId" not in call["body"]["parameters"])
    check("тарифы: габариты донесены", call["body"]["offers"][0]["weight"] == 1.2)
    check("тарифы: ответ разобран", len(t) == 1 and len(t[0]["tariffs"]) == 2)
finally:
    restore(saved)

net, saved = with_net([{"result": {"offers": []}}])
try:
    trade.calc_tariffs([{"category_id": 1, "price": 10}], campaign_id=555)
    par = net.calls[0]["body"]["parameters"]
    check("тарифы: с campaignId — sellingProgram убран",
          par.get("campaignId") == 555 and "sellingProgram" not in par)
finally:
    restore(saved)

# ---------------------------------------------------------------- пустой вход = noop
print("\nПустой вход · noop без сети")
net, saved = with_net([])
try:
    check("остатки []: noop", trade.update_stocks("B1", [], dry=False, commit=True)["status"] == "noop")
    check("цены []: noop", trade.update_prices("B1", [], dry=False, commit=True)["status"] == "noop")
    check("тарифы []: пустой список", trade.calc_tariffs([]) == [])
    check("noop → сеть не тронута", not net.calls)
finally:
    restore(saved)

# ------------------------------------------------- живые форматы ответов (кабинет Atlas Edge)
print("\nЖивые форматы · расхождения документации с реальным кабинетом")

# 1) regions приходят в КОРНЕ ответа, не в result
net, saved = with_net([{"regions": [
    {"id": 213, "name": "Москва", "type": "CITY",
     "parent": {"id": 1, "name": "Москва и область",
                "parent": {"id": 225, "name": "Россия"}}}], "paging": {}}])
try:
    rg = trade.find_region("Москва")
    check("живое: regions в корне ответа (без result) распознаны", len(rg) == 1 and rg[0]["id"] == 213)
finally:
    restore(saved)

# 2) остатки приходят как offers[].stocks[]; пустой stocks = остаток НЕ ЗАДАН (не ноль)
net, saved = with_net([{"result": {"partnerWarehouseId": 2390811, "offers": [
    {"offerId": "A-1", "stocks": [{"type": "FIT", "count": 5,
                                   "updatedAt": "2026-08-05T10:00:00Z"}]},
    {"offerId": "B-1", "stocks": [{"type": "FIT", "count": 0}]},
    {"offerId": "C-1", "stocks": []}]}}])
try:
    st = trade.read_stocks("B1", 2390811)
    by = {r["sku"]: r["count"] for r in st}
    check("живое: формат offers[].stocks[] разобран", len(st) == 3)
    check("живое: остаток 5 прочитан", by.get("A-1") == 5)
    check("живое: явный ноль остаётся 0", by.get("B-1") == 0)
    check("живое: пустой stocks → None (НЕ ЗАДАН, а не ноль)", by.get("C-1") is None)
finally:
    restore(saved)

# 3) индекс качества: campaignRatings[].ratings[]; пустой ratings = НЕ РАССЧИТАН (не ноль)
net, saved = with_net([{"result": {"campaignRatings": [
    {"campaignId": 149215943, "ratings": []}]}}])
try:
    q = trade.quality_rating("B1", [149215943])
    check("живое: campaignRatings разобран", len(q) == 1)
    check("живое: пустой ratings → total=None (не 0)", q[0]["total"] is None)
    check("живое: помечено not_calculated", q[0]["not_calculated"] is True)
finally:
    restore(saved)

net, saved = with_net([{"result": {"campaignRatings": [
    {"campaignId": 1, "ratings": [{"value": 96, "name": "QUALITY"}]}]}}])
try:
    q = trade.quality_rating("B1", [1])
    check("живое: рассчитанный индекс прочитан", q[0]["total"] == 96.0
          and q[0]["not_calculated"] is False)
finally:
    restore(saved)

# ---------------------------------------------------------------- итог
print("\n" + "=" * 62)
print(f"ЯНДЕКС M3 (торговые руки): {len(PASS)}/{len(PASS) + len(FAIL)} зелёных")
if FAIL:
    print("КРАСНЫЕ:")
    for f in FAIL:
        print(f"  ❌ {f}")
    sys.exit(1)
print("✅ Торговые руки честны: гейт держит, потолки ловятся, 200≠успех, склад не имитируется")

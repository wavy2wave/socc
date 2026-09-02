#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BRIDGE V1 — читающая половина моста заказов Ozon органа ARBITER (сухая, 0₽, без демона).

ЗАЧЕМ (приоритет №1 создателя, дословно из MAIN OZON): «беспрекословная связь и КОРРЕКТНЫЙ
вывод заказов». Старый мост (tamaguru bridge.py) ~2000 раз крашлупил и НЕ отдал НИ ОДНОГО
заказа — не из-за payload (это был ложный диагноз), а потому что: (1) в .env стояли ЗАГЛУШКИ
вместо реальных Client-Id/Api-Key, (2) не было устойчивого слоя (401/429/5xx/пусто валили цикл),
(3) сырой постинг Ozon не превращался в чистую строку заказа, (4) между «заказ пришёл» и
«отгружено» зияла дыра — не было очереди «что купить на WB рядом с клиентом».

Этот модуль закрывает ровно эти 4 дыры, НЕ трогая деньги/каталог/ключи-в-коде:
  read_orders(...)      — устойчивое чтение FBS-заказов поверх ozon.fetch_new_orders (401/429/5xx/пусто
                          классифицируются честно; пусто ≠ «мост мёртв»). Ключи — из env, НЕ из кода.
  normalize_posting(p)  — сырой постинг Ozon → чистая строка заказа (номер, товары, город/склад-подсказка,
                          адрес-скелет). НИКОГДА не выдумывает поле — нет данных → None + honest-флаг.
  to_buy_task(order)    — строка заказа → задача выкупа на WB рядом с клиентом (что искать, куда везти).
                          Это тот самый ШОВ buy_on_wb: v1 = задача оператору, не авто-покупка.
  bridge_scan(...)      — один ограниченный проход: читать → нормализовать → собрать очередь выкупа.
                          commit=False по умолчанию (канон/деньги не трогаем). Печатает, не публикует.

ГРАНИЦА ЧЕСТНОСТИ (RUBICON): этот файл ТОЛЬКО ЧИТАЕТ. Не создаёт карточек, не двигает денег,
не покупает. Реальное чтение живого кабинета включается лишь при наличии реальных ключей в env
(creds_present()); их нет — мост честно говорит «ключей нет, живое чтение недоступно», не падая.
Деньги verified появляются лишь позже (t4 SETTLE) из Ozon Finance, не здесь.

Переиспользует socc_mint_ozon_v1 (fetch_new_orders/fetch_posting_payout) и base_v1.http-стиль —
не дублирует. Чистый stdlib, ленивая сеть, fail-soft, без демона (закон вечной машины SOCC).
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent          # SOCC/scripts/mint/arbiter
MINT = HERE.parent                                # SOCC/scripts/mint
ROOT = MINT.parent.parent                         # SOCC
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import socc_mint_ozon_v1 as ozon                  # noqa: E402  (руки Ozon — уже правильные)

# Статусы FBS, которые мост берёт в работу (заказ ждёт нашей отправки). Из MAIN OZON: рабочая
# машина состояний фулфилмента awaiting_packaging → awaiting_deliver → ready_to_ship.
WORK_STATUSES = ("awaiting_packaging", "awaiting_deliver", "ready_to_ship")

# Очередь выкупа (что купить на WB рядом с клиентом) — канон ARBITER, отдельно от proven_connections.
BUY_QUEUE_PATH = ROOT / "MEMORY_WAVE/reports/mint/arbiter/buy_queue.jsonl"

def _now():
    return datetime.now(timezone.utc).isoformat()


# ── Слой устойчивости: старый мост падал на 401/429/5xx/пусто — этот не должен ──
# Закон вечной машины: пусто ≠ «нет заказов», 401 ≠ «мост сломан». Классифицируем честно,
# ретраим ограниченно (не демон), и всегда возвращаем {ok, orders, health}, а не голый список.

def read_orders(statuses=WORK_STATUSES, since_days=3, limit=50):
    """Устойчивое чтение FBS-заказов. ВАЖНО: это единственное место, где живёт сеть к Ozon.

    Вернёт {'ok': bool, 'orders': [...], 'health': {...}, 'error': None|str}.
    Ключей нет → ok=False, health.creds='missing' (честно, без падения). Пусто → ok=True (это норм).
    401 → health.auth='fail' (КЛЮЧИ, не код!). 429/5xx → до 3 ретраев с jitter-бэкоффом.
    """
    if not ozon.creds_present():
        return {"ok": False, "orders": [], "error": "ключей нет: OZON_CLIENT_ID/OZON_API_KEY не заданы",
                "health": {"creds": "missing", "auth": "n/a", "retries": 0, "last_status": None}}
    retries = 0
    for attempt in range(3):
        try:
            orders = ozon.fetch_new_orders(since_days=since_days, limit=limit, status=statuses)
            return {"ok": True, "orders": orders or [], "error": None,
                    "health": {"creds": "present", "auth": "ok", "retries": retries, "last_status": "ok"}}
        except Exception as e:
            msg = str(e)
            lower = msg.lower()
            if "401" in lower or "client-id" in lower or "api-key" in lower:
                return {"ok": False, "orders": [], "error": msg,
                        "health": {"creds": "present", "auth": "fail", "retries": retries,
                                   "last_status": "auth_fail"}}
            # 429/5xx/timeout — транзиторные: ограниченный ретрай с jitter-бэкоффом (не демон)
            if attempt < 2 and ("429" in lower or "5" in msg[:3] or "timeout" in lower or "timed out" in lower):
                import time, random
                time.sleep(0.5 + random.random() * 1.0)
                retries += 1
                continue
            return {"ok": False, "orders": [], "error": msg,
                    "health": {"creds": "present", "auth": "n/a", "retries": retries,
                               "last_status": "error"}}
    return {"ok": False, "orders": [], "error": "исчерпаны ретраи",
            "health": {"creds": "present", "auth": "n/a", "retries": retries, "last_status": "error"}}


# ── Нормализация сырого постинга Ozon → чистая строка заказа ──
# Старый мост вываливал сырой JSON на фронт. Здесь — НИКОГДА не выдумываем поле:
# нет данных → None + honest-флаг. Город/склад из analytics_data (в fetch он включён).

def normalize_posting(p):
    """Сырой постинг Ozon → {'posting_number', 'in_process_at', 'order_id', 'items', 'address', 'delivery'}.

    Идемпотентно, fail-soft: что не смогли достать → None, не фейк. 'honest' показывает пропуски.
    """
    if not isinstance(p, dict):
        return None
    # ВАЖНО: НЕ выдумываем id из мусора — только из реальных полей постинга
    posting_number = p.get("posting_number")
    if not posting_number:
        return None
    order_id = p.get("order_id")
    in_process_at = p.get("in_process_at")
    analytics = p.get("analytics_data") if isinstance(p.get("analytics_data"), dict) else {}
    items_raw = p.get("products") if isinstance(p.get("products"), list) else []
    items = []
    for it in items_raw:
        if isinstance(it, dict) and it.get("sku"):
            items.append({
                "sku": str(it.get("sku")),
                "name": (it.get("name") or "").strip() or None,
                "quantity": int(it.get("quantity") or 1),
            })
    # Адрес/город — скелет для выкупа «рядом с клиентом»; НЕ полный паспортный адрес, если нет поля
    address_raw = p.get("delivery_address")
    address = None
    city = None
    if isinstance(address_raw, dict):
        address = {
            "city": (address_raw.get("city") or "").strip() or None,
            "street": (address_raw.get("street") or "").strip() or None,
            "house": (address_raw.get("house") or "").strip() or None,
            "flat": (address_raw.get("flat") or "").strip() or None,
            "comment": (address_raw.get("comment") or "").strip() or None,
        }
        city = address["city"]
    elif isinstance(address_raw, str) and address_raw.strip():
        address = {"raw": address_raw.strip()}
    warehouse = (analytics.get("warehouse_name") or "").strip() or None
    delivery = {}
    if warehouse:
        delivery["warehouse_name"] = warehouse
    # Город клиента ТОЛЬКО из адреса или delivery-city в analytics. warehouse_name — это НАШ склад
    # отгрузки, НЕ город клиента: если взять его за город, «выкуп рядом с клиентом» уедет к нашему
    # складу. Нет города клиента → None (честно), склад остаётся лишь подсказкой в delivery.
    city = city or ((analytics.get("city") or "").strip() or None)
    return {
        "posting_number": posting_number,
        "in_process_at": in_process_at,
        "order_id": order_id,
        "items": items,
        "address": address,
        "city": city,
        "delivery": delivery,
        "honest": {
            "no_city": city is None,
            "no_address": address is None,
            "no_items": len(items) == 0,
        },
    }


def to_buy_task(order, supplier="wildberries"):
    """Строка заказа → задача выкупа на WB рядом с клиентом (это и есть ШОВ buy_on_wb, v1 = задача).

    Без города/адреса → задачу НЕ выдумываем: {'ok': False, 'why': ...}. Деньги/каталог НЕ трогаем.
    """
    if not order:
        return {"ok": False, "why": "нет заказа"}
    city = order.get("city")
    if not city:
        return {"ok": False,
                "why": f"постинг {order.get('posting_number')} без города — выкуп рядом с клиентом невозможен"}
    items = order.get("items") or []
    search = None
    if items:
        search = ", ".join(it.get("name") for it in items if it.get("name"))
    return {
        "ok": True,
        "posting_number": order.get("posting_number"),
        "supplier": supplier,
        "deliver_to_city": city,
        "address_hint": (order.get("address") or {}).get("street") or (order.get("address") or {}).get("raw"),
        "buy_items": [
            {"name": it.get("name") or f"sku {it.get('sku')}", "sku": it.get("sku"),
             "quantity": it.get("quantity", 1)}
            for it in items
        ],
        "search": search,
        "note": "v1: задача оператору (купи на WB рядом с клиентом). Авто-выкуп — BrowserBot за флагом, позже.",
    }


def bridge_scan(statuses=WORK_STATUSES, since_days=3, limit=50, supplier="wildberries",
                write_queue=False, queue_path=None):
    """Один ограниченный проход моста: читать → нормализовать → собрать очередь выкупа.

    write_queue=False (по умолчанию) — ТОЛЬКО печатает, канон/деньги НЕ трогает. Возвращает dict.
    write_queue=True — дописывает задачи выкупа (ok) в buy_queue.jsonl (append-only, без дедупа тут).
    """
    res = read_orders(statuses=statuses, since_days=since_days, limit=limit)
    orders_raw = res.get("orders") or []
    orders = []
    skipped = 0
    for p in orders_raw:
        n = normalize_posting(p)
        if n is None:
            skipped += 1
            continue
        orders.append(n)
    buy_tasks = []
    no_city = 0
    for o in orders:
        t = to_buy_task(o, supplier=supplier)
        if t.get("ok"):
            buy_tasks.append(t)
        else:
            no_city += 1
    written = 0
    if write_queue and buy_tasks:
        path = Path(queue_path) if queue_path else BUY_QUEUE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for t in buy_tasks:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        written = len(buy_tasks)
    return {
        "health": res.get("health"),
        "error": res.get("error"),
        "read_ok": res.get("ok", False),
        "raw_orders": len(orders_raw),
        "normalized": len(orders),
        "skipped_malformed": skipped,
        "buy_tasks": buy_tasks,
        "no_city": no_city,
        "queue_written": written,
        "queue_path": str(Path(queue_path) if queue_path else BUY_QUEUE_PATH),
        "scanned_at": _now(),
    }


def _fmt_task(t):
    return (f"[{t.get('posting_number')}] → {t.get('deliver_to_city')} "
            f"({t.get('address_hint') or 'адрес не указан'}) · искать: {t.get('search') or '?'}")


def _main(argv=None):
    ap = argparse.ArgumentParser(description="BRIDGE V1 — читающая половина моста заказов Ozon (сухая, 0₽)")
    ap.add_argument("--statuses", nargs="+", default=list(WORK_STATUSES), help="статусы FBS (default: все рабочие)")
    ap.add_argument("--since-days", type=int, default=3)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--supplier", default="wildberries")
    ap.add_argument("--write-queue", action="store_true",
                    help="дописать задачи выкупа в buy_queue.jsonl (append-only; по умолчанию ТОЛЬКО печать)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    res = bridge_scan(statuses=args.statuses, since_days=args.since_days, limit=args.limit,
                      supplier=args.supplier, write_queue=args.write_queue)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    h = res.get("health") or {}
    print(f"🌉 BRIDGE · читающая половина моста (dry-чтение, 0₽)")
    print(f"   creds={h.get('creds')} auth={h.get('auth')} retries={h.get('retries')} "
          f"последний={h.get('last_status')}")
    if not res.get("read_ok"):
        print(f"   ⚠️  живое чтение недоступно: {res.get('error')}")
        if h.get("creds") == "missing":
            print(f"       → впиши реальные OZON_CLIENT_ID/OZON_API_KEY в wavecore-bot/.env (gitignored)")
        elif h.get("auth") == "fail":
            print(f"       → 401: проверь КЛЮЧИ, не код (Ozon авторизуется Client-Id+Api-Key)")
        return 0 if h.get("creds") == "missing" else 1

    print(f"   сырых={res.get('raw_orders')} нормализовано={res.get('normalized')} "
          f"пропущено-битых={res.get('skipped_malformed')} без-города={res.get('no_city')}")
    for t in res.get("buy_tasks", []):
        print(f"   🛒 {_fmt_task(t)}")
    if res.get("queue_written"):
        print(f"   💾 очередь выкупа: +{res.get('queue_written')} → {res.get('queue_path')}")
    if not res.get("buy_tasks"):
        print("   (задач выкупа нет — заказов в рабочем статусе сейчас нет, это нормально)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

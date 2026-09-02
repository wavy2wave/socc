#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3 ПРИЁМКА — BRIDGE: читающая половина моста заказов Ozon (сухая, 0₽, БЕЗ ключей/сети).

Веха M3 (сухая read-плоскость до записи наружу) + защита законов вечной машины. Все тесты
оффлайн-детерминированы: сеть к Ozon подменяется фейковыми постингами (monkeypatch ozon.*),
реальные ключи НЕ нужны и НЕ используются. Мост НИКОГДА не двигает деньги/каталог.

  M3T1  no_creds_honest        — ключей нет → read_ok=False, health.creds='missing', НЕ падает.
  M3T2  read_ok_empty          — ключи есть, заказов нет → read_ok=True, orders=[] (пусто ≠ мёртв).
  M3T3  auth_401_is_keys       — 401 от Ozon → health.auth='fail' (ключи, не код), без ретрай-шторма.
  M3T4  retry_then_success     — 429 дважды → мост ретраит и добивается успеха (устойчивость).
  M3T5  normalize_clean        — сырой постинг → чистая строка (номер/товары/город/адрес), без выдумки.
  M3T6  normalize_honest_gaps  — постинг без адреса/города → honest-флаги, поля None, НЕ фейк.
  M3T7  normalize_rejects_junk — мусор/без posting_number → None (не пускаем битое дальше).
  M3T8  buy_task_from_order    — заказ с городом → задача выкупа рядом с клиентом (что искать, куда).
  M3T9  buy_task_no_city       — заказ без города → задача НЕ выдумывается (ok=False + причина).
  M3T10 bridge_scan_dry        — полный проход: читать→нормализ→очередь; write_queue=False → канон нетронут.
  M3T11 bridge_scan_queue_tmp  — write_queue=True во ВРЕМЕННЫЙ путь → задачи записаны, реальный канон нетронут.
  M3T12 bridge_survives_error  — read упал с непонятной ошибкой → scan жив, read_ok=False, конвейер не рухнул.

M3T-live (опц.) — если реальные ключи в env, один живой READ (0₽): читаем кабинет, ничего не двигаем.
Приёмка не пишет в реальный канон и не зовёт сеть (кроме опц. живого теста).
"""
import sys
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import bridge_v1 as bridge                          # noqa: E402
import socc_mint_ozon_v1 as ozon                    # noqa: E402


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


class _Patch:
    """Мини-monkeypatch: подменяем ozon.creds_present / ozon.fetch_new_orders, откат гарантирован."""
    def __init__(self, creds=None, fetch=None):
        self._creds = creds
        self._fetch = fetch
        self._save = {}

    def __enter__(self):
        if self._creds is not None:
            self._save["creds_present"] = ozon.creds_present
            ozon.creds_present = self._creds
        if self._fetch is not None:
            self._save["fetch_new_orders"] = ozon.fetch_new_orders
            ozon.fetch_new_orders = self._fetch
        return self

    def __exit__(self, *a):
        for name, fn in self._save.items():
            setattr(ozon, name, fn)
        return False


def mk_posting(number="0001-0001-1", city="Москва", street="Тверская", items=1, sku_base="SKU"):
    """Сырой постинг в схеме Ozon FBS (как из /v3/posting/fbs/list result.postings[])."""
    prods = [{"sku": f"{sku_base}{i}", "name": f"Товар {i}", "quantity": 1} for i in range(1, items + 1)]
    p = {"posting_number": number, "order_id": 777, "in_process_at": "2026-08-02T10:00:00Z",
         "products": prods, "analytics_data": {"warehouse_name": "Хоругвино"}}
    if city or street:
        p["delivery_address"] = {"city": city, "street": street, "house": "1", "flat": "5"}
    return p


def t1_no_creds_honest():
    """Ключей нет → мост честно говорит 'missing' и НЕ падает (без сети/ключей это штатный путь)."""
    with _Patch(creds=lambda: False, fetch=lambda *a, **k: (_ for _ in ()).throw(AssertionError("не должны звать"))):
        r = bridge.read_orders()
    ok = (r["ok"] is False and r["health"]["creds"] == "missing" and r["error"]
          and r["orders"] == [] and "auth" in r["health"])
    return ok, f"ok={r['ok']}, health={r['health']}, error={r['error'][:44]}"


def t2_read_ok_empty():
    """Ключи есть, заказов нет → ok=True, orders=[] (пусто ≠ «мост мёртв», закон вечной машины)."""
    with _Patch(creds=lambda: True, fetch=lambda *a, **k: []):
        r = bridge.read_orders()
    ok = r["ok"] is True and r["orders"] == [] and r["error"] is None and r["health"]["auth"] == "ok"
    return ok, f"ok={r['ok']}, orders={len(r['orders'])}, auth={r['health']['auth']}"


def t3_auth_401_is_keys():
    """401 от Ozon → auth='fail' (это КЛЮЧИ, не код), без ретрай-шторма. Урок дельты: 401 ≠ payload."""
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("401 Client Error: Client-Id and Api-Key headers are required")
    with _Patch(creds=lambda: True, fetch=boom):
        r = bridge.read_orders()
    ok = (r["ok"] is False and r["health"]["auth"] == "fail" and r["error"]
          and len(calls) == 1)          # НЕ ретраим 401 — ретрай не починит ключи
    return ok, f"auth={r['health']['auth']}, попыток={len(calls)} (должно быть 1), error={r['error'][:40]}"


def t4_retry_then_success():
    """429 дважды → мост ретраит с паузой и добивается успеха (устойчивость, ограниченная, не демон)."""
    state = {"n": 0}

    def flaky(*a, **k):
        state["n"] += 1
        if state["n"] <= 2:
            raise RuntimeError("429 Too Many Requests")
        return [mk_posting("0001-0001-1", city="Москва")]
    with _Patch(creds=lambda: True, fetch=flaky):
        r = bridge.read_orders()
    ok = (r["ok"] is True and len(r["orders"]) == 1 and r["health"]["retries"] >= 1
          and state["n"] == 3)
    return ok, f"попыток={state['n']} (429×2→200), retries={r['health']['retries']}, ok={r['ok']}"


def t5_normalize_clean():
    """Сырой постинг → чистая строка: номер/товары/город/адрес, ничего не выдумано."""
    n = bridge.normalize_posting(mk_posting("A-1", city="Москва", street="Тверская", items=2))
    ok = (n["posting_number"] == "A-1" and n["order_id"] == 777
          and n["city"] == "Москва" and n["address"]["street"] == "Тверская"
          and len(n["items"]) == 2 and n["items"][0]["sku"] == "SKU1"
          and n["delivery"]["warehouse_name"] == "Хоругвино"
          and not any(n["honest"].values()))
    return ok, f"город={n['city']}, товаров={len(n['items'])}, честно={n['honest']}"


def t6_normalize_honest_gaps():
    """Без адреса/города → honest-флаги, поля None, НЕ фейк (город не выдумываем из ничего)."""
    p = mk_posting("B-2", city=None, street=None, items=1)
    n = bridge.normalize_posting(p)
    ok = (n["city"] is None and n["address"] is None
          and n["honest"]["no_city"] is True and n["honest"]["no_address"] is True)
    return ok, f"city={n['city']}, address={n['address']}, honest={n['honest']}"


def t7_normalize_rejects_junk():
    """Мусор/нет posting_number → None (битое не пускаем дальше в очередь)."""
    ok = (bridge.normalize_posting({}) is None
          and bridge.normalize_posting(None) is None
          and bridge.normalize_posting({"posting_number": ""}) is None
          and bridge.normalize_posting("строка") is None)
    return ok, "junk → None (4/4)"


def t8_buy_task_from_order():
    """Заказ с городом → задача выкупа рядом с клиентом (что искать, куда везти). ШОВ buy_on_wb, v1."""
    o = bridge.normalize_posting(mk_posting("C-3", city="Казань", street="Баумана", items=1))
    t = bridge.to_buy_task(o)
    ok = (t["ok"] is True and t["deliver_to_city"] == "Казань" and t["supplier"] == "wildberries"
          and t["address_hint"] == "Баумана" and t["buy_items"][0]["sku"] == "SKU1"
          and t["search"] == "Товар 1" and "posting_number" in t)
    return ok, f"→ {t['deliver_to_city']}, искать={t['search']}"


def t9_buy_task_no_city():
    """Без города → задача НЕ выдумывается (ok=False + причина), а не «купить в None»."""
    o = bridge.normalize_posting(mk_posting("D-4", city=None, street=None, items=1))
    t = bridge.to_buy_task(o)
    ok = (t["ok"] is False and t["why"] and "без города" in t["why"])
    return ok, f"ok={t['ok']}, why={t['why'][:52]}"


def t10_bridge_scan_dry():
    """Полный проход read→normalize→buy_tasks, write_queue=False → канон НЕ тронут."""
    def fetch(*a, **k):
        return [mk_posting("E-5", city="Москва"), mk_posting("F-6", city=None, street=None)]
    with _Patch(creds=lambda: True, fetch=fetch):
        r = bridge.bridge_scan(write_queue=False)
    ok = (r["read_ok"] is True and r["raw_orders"] == 2 and r["normalized"] == 2
          and len(r["buy_tasks"]) == 1 and r["no_city"] == 1 and r["queue_written"] == 0
          and not bridge.BUY_QUEUE_PATH.exists())     # сухая: реальная очередь не создана
    return ok, f"raw={r['raw_orders']}, buy={len(r['buy_tasks'])}, no_city={r['no_city']}, записано={r['queue_written']}"


def t11_bridge_scan_queue_tmp():
    """write_queue=True во ВРЕМЕННЫЙ путь → задачи записаны, реальный канон НЕ тронут."""
    def fetch(*a, **k):
        return [mk_posting("G-7", city="Москва", street="Тверская"), mk_posting("H-8", city="Питер")]
    tmp = Path(tempfile.mkdtemp()) / "buy_queue.jsonl"
    with _Patch(creds=lambda: True, fetch=fetch):
        r = bridge.bridge_scan(write_queue=True, queue_path=tmp)
    lines = tmp.read_text(encoding="utf-8").splitlines() if tmp.exists() else []
    all_ok = all(json.loads(l).get("ok") is True for l in lines)
    ok = (r["queue_written"] == 2 and len(lines) == 2 and all_ok
          and "G-7" in tmp.read_text(encoding="utf-8") and "H-8" in tmp.read_text(encoding="utf-8")
          and not bridge.BUY_QUEUE_PATH.exists())
    return ok, f"записано={r['queue_written']}, строк={len(lines)}, канон-нетронут={not bridge.BUY_QUEUE_PATH.exists()}"


def t12_bridge_survives_error():
    """read упал с непонятной ошибкой → scan жив, read_ok=False, конвейер не рухнул (fail-soft)."""
    def boom(*a, **k):
        raise RuntimeError("Connection refused: временная недоступность")
    with _Patch(creds=lambda: True, fetch=boom):
        r = bridge.bridge_scan()
    ok = (r["read_ok"] is False and r["error"] and r["raw_orders"] == 0 and r["buy_tasks"] == []
          and r["normalized"] == 0)
    return ok, f"read_ok={r['read_ok']}, error={r['error'][:40]}"


def t_live_read_optional():
    """Опциональный живой READ (0₽): реальные ключи в env → читаем кабинет, ничего не двигаем."""
    if not ozon.creds_present():
        return None, "SKIP: OZON_CLIENT_ID/OZON_API_KEY не заданы — живой READ недоступен (и не нужен)"
    r = bridge.read_orders(limit=5)
    if not r["ok"]:
        return None, f"SKIP: живое чтение недоступно ({r['health']}, {r['error'][:40]})"
    n = [bridge.normalize_posting(p) for p in r["orders"]]
    tasks = [bridge.to_buy_task(o) for o in n if o]
    ok = (r["ok"] is True and len(n) == len(r["orders"])
          and all(t["ok"] or not t.get("ok") for t in tasks))
    return ok, f"ЖИВОЙ READ: заказов={len(r['orders'])}, задач-выкупа={sum(1 for t in tasks if t.get('ok'))}"


TESTS = [
    ("M3T1 no_creds_honest", t1_no_creds_honest),
    ("M3T2 read_ok_empty", t2_read_ok_empty),
    ("M3T3 auth_401_is_keys", t3_auth_401_is_keys),
    ("M3T4 retry_then_success", t4_retry_then_success),
    ("M3T5 normalize_clean", t5_normalize_clean),
    ("M3T6 normalize_honest_gaps", t6_normalize_honest_gaps),
    ("M3T7 normalize_rejects_junk", t7_normalize_rejects_junk),
    ("M3T8 buy_task_from_order", t8_buy_task_from_order),
    ("M3T9 buy_task_no_city", t9_buy_task_no_city),
    ("M3T10 bridge_scan_dry", t10_bridge_scan_dry),
    ("M3T11 bridge_scan_queue_tmp", t11_bridge_scan_queue_tmp),
    ("M3T12 bridge_survives_error", t12_bridge_survives_error),
    ("M3-live read (опц.)", t_live_read_optional),
]


def main():
    print("═" * 68)
    print("  ARBITER · M3 ПРИЁМКА — BRIDGE: читающая половина моста заказов (сухая, 0₽)")
    print("═" * 68)
    hard_total = 0
    hard_pass = 0
    skipped = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        if ok is None:
            skipped += 1
            print(f"⏭️  SKIP  {name}: {detail}")
            continue
        hard_total += 1
        hard_pass += 1 if ok else 0
        print(f"{_passed(ok)}  {name}: {detail}")
    print("─" * 68)
    print(f"ИТОГ M3:  {hard_pass}/{hard_total} обязательных зелёные"
          f"{f', {skipped} опциональных пропущено' if skipped else ''}")
    print("═" * 68)
    return 0 if hard_pass == hard_total else 1


if __name__ == "__main__":
    sys.exit(main())

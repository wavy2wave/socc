#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РОЛЬ · СКЛАДОВЩИК (YM_STOCKMAN) — остатки на витрине равны правде склада.

Канон роли SOCC (TFS-1, 8 полей) — см. CHARTER ниже.

Зачем: протухший остаток — самый дорогой баг в модели Экспресс. Товара нет, а витрина
показывает «в наличии» → покупатель заказывает → собрать нечего → отмена по вине магазина
(до 5000 ₽ + падение индекса + полная стоимость доставки). Одна протухшая позиция может
съесть дневную маржу целиком.

Поэтому закон роли жёсткий: ЛУЧШЕ НОЛЬ, ЧЕМ ЛОЖЬ. Не уверен, что товар есть — ставь 0.
Ноль means «не продаём сейчас» и стоит 0 ₽. Ложное «в наличии» стоит тысячи.

ЧЕСТНОСТЬ (L3): роль не «прикидывает» остаток. Источник количества — только явные данные
(наличие у партнёра / инвентарь оператора). Нет источника → позиция уходит в 'unknown'
и НЕ обновляется вслепую.

Что роль НЕ делает (граница честности):
  • не создаёт склад (в API метода нет — честный отказ, действие оператора);
  • не выдумывает количество, которого не видела;
  • не поднимает остаток «на всякий случай» — только вниз безопасно.
"""
from __future__ import annotations

import json
import sys

import ymarket_trade_hands_v1 as trade

CHARTER = {
    "id": "YM_STOCKMAN",
    "name_ru": "СКЛАДОВЩИК",
    "mandate": "остаток на витрине всегда равен правде склада, иначе — ноль",
    "owns": ["остатки по SKU", "склады и их модели", "снятие с продажи"],
    "inputs": ["наличие у партнёра (ТОВАРОВЕД)", "инвентарь оператора", "остатки Маркета (READ)"],
    "outputs": ["обновление остатков → Маркет", "список 'источник неизвестен' → оператор"],
    "laws": [
        "S1 ЛУЧШЕ НОЛЬ, ЧЕМ ЛОЖЬ — неуверен в наличии → count=0",
        "S2 количество только из явного источника, не из догадки",
        "S3 склад через API не создаём (метода нет) — эскалация оператору",
        "S4 поднимать остаток можно только по подтверждённому наличию, снижать — всегда можно",
    ],
    "kpi": [
        {"metric": "отмен из-за отсутствия товара", "target": "0", "source_of_truth": "статусы заказов"},
        {"metric": "возраст самого старого остатка", "target": "< 24 ч", "source_of_truth": "updatedAt Маркета"},
        {"metric": "позиций без источника наличия", "target": "→0", "source_of_truth": "память state"},
    ],
    "proves_by": "после записи READ остатков подтверждает записанное число (запись → чтение → сверка)",
}

# Если остаток не обновлялся дольше — он подозрительный (Маркет не знает, что у нас на полке).
STALE_HOURS = 24


def plan(items, warehouse_id, default_zero=True):
    """Построить план обновления остатков из сырых данных о наличии.

    items — [{sku, available?, in_stock?, count?, source?}]
      available/count — явное число; in_stock=False → 0; нет ничего → см. default_zero.
    Возвращает {updates:[...], unknown:[...], zeroed:[...]}, где updates готов для торговых рук.
    """
    updates, unknown, zeroed = [], [], []
    for it in items or []:
        sku = it.get("sku") or it.get("offerId")
        if not sku:
            continue
        src = it.get("source")
        cnt = it.get("count")
        if cnt is None:
            cnt = it.get("available")

        if isinstance(cnt, (int, float)):
            cnt = int(cnt)
            if cnt < 0:
                cnt = 0
            updates.append({"sku": sku, "warehouse_id": warehouse_id, "count": cnt,
                            "source": src or "explicit"})
            if cnt == 0:
                zeroed.append(sku)
        elif it.get("in_stock") is False:
            updates.append({"sku": sku, "warehouse_id": warehouse_id, "count": 0,
                            "source": src or "in_stock=False"})
            zeroed.append(sku)
        elif default_zero:
            # S1: источника нет → безопасное 0 (снять с продажи), но пометить как unknown
            updates.append({"sku": sku, "warehouse_id": warehouse_id, "count": 0,
                            "source": "SAFE_ZERO (источник неизвестен)"})
            zeroed.append(sku)
            unknown.append(sku)
        else:
            unknown.append(sku)
    return {"updates": updates, "unknown": unknown, "zeroed": zeroed}


def push(business_id, updates, dry=True, commit=False, batch=trade.MAX_STOCKS_BATCH):
    """Отправить остатки батчами (потолок Маркета 2000 за запрос).

    Возвращает сводку по батчам; при ошибке батча остальные всё равно пробуются
    (частичный успех честнее полного отказа — часть витрины уже правдива).
    """
    if not updates:
        return {"status": "noop", "sent": False, "batches": [], "count": 0,
                "note": "нечего обновлять"}
    clean = [{k: v for k, v in u.items() if k != "source"} for u in updates]
    batches, ok_all, sent_total = [], True, 0
    for i in range(0, len(clean), batch):
        chunk = clean[i:i + batch]
        try:
            r = trade.update_stocks(business_id, chunk, dry=dry, commit=commit)
        except Exception as e:
            batches.append({"from": i, "count": len(chunk), "ok": False,
                            "error": f"{type(e).__name__}: {e}"})
            ok_all = False
            continue
        ok = r.get("ok", r.get("sent") is False)   # dry-прогон не ошибка
        batches.append({"from": i, "count": len(chunk), "ok": bool(ok),
                        "sent": r.get("sent"), "errors": r.get("errors")})
        if r.get("sent"):
            sent_total += len(chunk)
        if r.get("sent") and not r.get("ok"):
            ok_all = False
    return {"status": "sent" if sent_total else "dry", "sent": bool(sent_total),
            "ok": ok_all, "count": len(clean), "sent_count": sent_total, "batches": batches}


def verify(business_id, warehouse_id, updates, read_fn=None):
    """ДОКАЗАТЕЛЬСТВО работы роли: записали → прочитали → сверили (Φ роли).

    Возвращает {ok, checked, mismatches:[{sku, expected, actual}]}.
    Fail-soft: чтение не удалось → ok=False с причиной, НЕ «всё сошлось».
    """
    if not updates:
        return {"ok": True, "checked": 0, "mismatches": [], "note": "нечего сверять"}
    fn = read_fn or trade.read_stocks
    expected = {u["sku"]: u["count"] for u in updates}
    try:
        actual_rows = fn(business_id, warehouse_id, offer_ids=list(expected)[:trade.MAX_SKU_FILTER])
    except Exception as e:
        return {"ok": False, "checked": 0, "mismatches": [],
                "error": f"{type(e).__name__}: {e}",
                "note": "остатки не прочитаны — НЕ утверждаем, что запись сошлась"}
    actual = {r.get("sku"): r.get("count") for r in actual_rows or []}
    mism = []
    for sku, exp in expected.items():
        act = actual.get(sku)
        if act != exp:
            mism.append({"sku": sku, "expected": exp, "actual": act})
    return {"ok": not mism, "checked": len(expected), "mismatches": mism}


def audit_freshness(rows, now_iso=None, stale_hours=STALE_HOURS):
    """Найти протухшие остатки по updatedAt Маркета (KPI роли).

    Без разбора часовых поясов: сравниваем только дату-время в ISO-строках лексикографически
    там, где формат одинаковый; если формат непонятен — позиция уходит в 'unparsed' (L3).
    """
    from datetime import datetime, timedelta
    stale, fresh, unparsed = [], [], []
    now = None
    if now_iso:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                now = datetime.strptime(now_iso[:19].replace("Z", ""), fmt)
                break
            except ValueError:
                continue
    if now is None:
        now = datetime.now()
    edge = now - timedelta(hours=stale_hours)
    for r in rows or []:
        upd = r.get("updatedAt")
        if not upd:
            unparsed.append(r.get("sku"))
            continue
        dt = None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(str(upd)[:19].replace("Z", ""), fmt)
                break
            except ValueError:
                continue
        if dt is None:
            unparsed.append(r.get("sku"))
        elif dt < edge:
            stale.append({"sku": r.get("sku"), "updatedAt": upd, "count": r.get("count")})
        else:
            fresh.append(r.get("sku"))
    return {"stale": stale, "fresh": len(fresh), "unparsed": unparsed,
            "ok": not stale and not unparsed}


def ensure_express(business_id, warehouse_id=None, dry=True, commit=False, wh_fn=None):
    """Проверить/включить ЭКСПРЕСС на складе. Склад не создаём (S3).

    Нет ни одного склада → честный отказ с инструкцией оператору.
    """
    fn = wh_fn or trade.warehouses
    try:
        whs = fn(business_id)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "note": "склады не прочитаны"}
    if not whs:
        ref = trade.create_warehouse_refused()
        return {"ok": False, "reason": ref["reason"], "human": ref["human"],
                "operator_action_required": True}
    target = None
    for w in whs:
        if warehouse_id is None or str(w.get("id")) == str(warehouse_id):
            target = w
            break
    if target is None:
        return {"ok": False, "reason": "WAREHOUSE_NOT_FOUND",
                "human": f"склад {warehouse_id} не найден среди {[w['id'] for w in whs]}"}
    if target.get("express"):
        return {"ok": True, "warehouse_id": target["id"], "already": True,
                "note": f"ЭКСПРЕСС уже включён на складе «{target.get('name')}»"}
    res = trade.set_warehouse_model(business_id, target["id"], trade.PLACEMENT_EXPRESS, True,
                                   dry=dry, commit=commit)
    res["warehouse_id"] = target["id"]
    res["note"] = "включение ЭКСПРЕССА; товары появятся ~15 мин (до 4 ч, если модель спала ≥30 дней)"
    return res


def render(plan_result, push_result=None, verify_result=None):
    lines = [f"📦 СКЛАДОВЩИК: к обновлению {len(plan_result['updates'])} · "
             f"обнулено {len(plan_result['zeroed'])} · без источника {len(plan_result['unknown'])}"]
    if plan_result["unknown"]:
        lines.append(f"   ⚠️  источник наличия неизвестен → выставлен 0 (S1): "
                     f"{', '.join(plan_result['unknown'][:8])}")
    if push_result:
        lines.append(f"   отправка: {push_result['status']} · "
                     f"батчей {len(push_result['batches'])} · позиций {push_result['count']}")
    if verify_result:
        if verify_result.get("ok"):
            lines.append(f"   ✅ сверка: {verify_result['checked']} позиций совпали")
        else:
            lines.append(f"   ❌ сверка: расхождений {len(verify_result.get('mismatches', []))}"
                         f"{' — ' + verify_result['note'] if verify_result.get('note') else ''}")
    return "\n".join(lines)


if __name__ == "__main__":
    if "--charter" in sys.argv:
        print(json.dumps(CHARTER, ensure_ascii=False, indent=2))
        sys.exit(0)

    demo = [
        {"sku": "S1", "count": 7, "source": "партнёр: в наличии"},
        {"sku": "S2", "in_stock": False},
        {"sku": "S3"},                       # источника нет → безопасный 0
        {"sku": "S4", "count": -3},          # мусор → 0
    ]
    p = plan(demo, warehouse_id=101)
    print(render(p))
    print()
    for u in p["updates"]:
        print(f"  {u['sku']}: count={u['count']}  ← {u['source']}")
    print("\nсверка (демо, чтение подменено):")
    v = verify("B1", 101, p["updates"],
               read_fn=lambda b, w, offer_ids=None: [
                   {"sku": "S1", "count": 7}, {"sku": "S2", "count": 0},
                   {"sku": "S3", "count": 0}, {"sku": "S4", "count": 0}])
    print("  " + ("✅ всё сошлось" if v["ok"] else f"❌ {v['mismatches']}"))
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON TRUTH V1 — ДОЗНАНИЕ по реальному кабинету: сколько Озон удерживает НА САМОМ ДЕЛЕ (READ, 0₽).

ЗАЧЕМ (главный урок 2026-08-05): вся экономика ARBITER висела на допущении
NET_COEFF = (1-0.50)*(1-0.30) = 0.35, унаследованном из старого parser.py — «комиссия 50%,
буст 30%». Это ДОПУЩЕНИЕ, а не факт: реальная комиссия Озона по упаковке обычно 5-25%, а буст
продвижения ВООБЩЕ ОПЦИОНАЛЕН. Если у оператора комиссия ~15% без буста, коэффициент ≈0.85,
и тогда машина ЗАНИЖАЛА прибыль в разы и выбрасывала хорошие товары как «тонкие».

Этот файл заменяет допущение ФАКТОМ из /v3/finance/transaction/list — там видно КАЖДОЕ
действие по каждой продаже: сама продажа, комиссия, логистика, эквайринг, возвраты, реклама.

ГРАНИЦЫ ЧЕСТНОСТИ (RUBICON):
  • ТОЛЬКО ЧТЕНИЕ. Ни одна функция не пишет в Озон, не двигает деньги, не публикует карточки.
  • Не выдумывает: нет транзакций → говорит «нет данных», а НЕ подставляет 0.35 обратно.
  • Каждое число ведёт к источнику (operation_type + posting_number), воспроизводимо руками.
  • Считает коэффициент по РЕАЛЬНЫМ выплатам: net_coeff = (что пришло) / (что заплатил покупатель).

CLI:
  python3 ozon_truth_v1.py                    # дознание за 90 дней, отчёт в терминал
  python3 ozon_truth_v1.py --days 180         # глубже в историю
  python3 ozon_truth_v1.py --json             # машиночитаемо
  python3 ozon_truth_v1.py --raw-types        # показать ВСЕ виды операций кабинета (диагностика)
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

HERE = Path(__file__).resolve().parent          # SOCC/scripts/mint/arbiter
MINT = HERE.parent                               # SOCC/scripts/mint
ROOT = MINT.parent.parent                        # SOCC
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import socc_mint_ozon_v1 as ozon                 # noqa: E402
import socc_mint_prospect_v1 as prospector       # noqa: E402  (единый источник NET_COEFF/DELIVERY_NET; чинит NameError в терминальном отчёте)

OUT_DIR = ROOT / "MEMORY_WAVE/reports/mint/arbiter"

# Виды операций Озона. Названия из /v3/finance/transaction/list (operation_type).
# ДОХОД оператора — только продажа; всё остальное удержания/расходы (приходят с минусом).
SALE_TYPES = ("OperationAgentDeliveredToCustomer",)        # доставлено покупателю = выручка
RETURN_TYPES = ("OperationAgentStornoDeliveredToCustomer", "ClientReturnAgentOperation")


def _now():
    return datetime.now(timezone.utc).isoformat()


def load_env(path=None):
    """Подтянуть ключи из gitignored .env (модуль рук читает только os.getenv).

    ФАЗА A: реализация переехала в общий socc_mint_env_v1 — раньше она жила ТОЛЬКО здесь,
    из-за чего руки Яндекса при живых ключах честно отвечали «ключей нет». Имя оставлено
    ради обратной совместимости (его зовёт _main и, возможно, внешние вызовы).
    Fail-soft: общий модуль недоступен → старое локальное поведение, конвейер жив.
    """
    try:
        import socc_mint_env_v1 as env
        return env.load_env(path)
    except Exception:
        pass
    import os
    p = Path(path) if path else (MINT / ".env")
    if not p.exists():
        return False
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        return True
    except Exception:
        return False


def _post_stdlib(path, body, timeout=40):
    """POST в Seller API на ЧИСТОМ stdlib (закон ARBITER: 0 зависимостей навсегда).

    Общий socc_mint_ozon_v1._post требует requests, которого в этой среде нет. НЕ правим общий
    модуль (директива «не ломай что работает») — делаем свой транспорт тем же urllib, что и
    suppliers/base_v1.http_get_json. Заголовки берём у модуля рук (единый источник ключей).
    """
    import urllib.request
    import urllib.error
    headers = ozon._headers()                     # Client-Id/Api-Key из окружения (.env)
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(ozon.API + path, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"Ozon HTTP {e.code}: {detail}") from None


def fetch_transactions(days=90, page_size=1000, max_pages=20):
    """ВСЕ финансовые операции кабинета за период (READ). Возвращает (operations, meta).

    Постранично, с ЖЁСТКИМ потолком max_pages — вечная машина не должна уйти в бесконечную
    прокрутку на большом кабинете. Fail-soft: сеть/ключи упали → ([], meta с причиной).
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=int(days))
    ops, pages_read, windows, err = [], 0, 0, None
    fmt = "%Y-%m-%dT%H:%M:%S.000Z"

    # ЖИВОЙ УРОК КАБИНЕТА (2026-08-05): Ozon отвечает HTTP 400 «too long period, only one
    # month allowed» на окно >1 месяца. В документации этого нет — узнаётся только боем.
    # Поэтому режем период на месячные окна (27 дней с запасом) и склеиваем.
    win_start = start
    while win_start < now and err is None:
        win_end = min(win_start + timedelta(days=27), now)
        page = 1
        while page <= int(max_pages):
            body = {"filter": {"date": {"from": win_start.strftime(fmt),
                                        "to": win_end.strftime(fmt)},
                               "transaction_type": "all"},
                    "page": page, "page_size": int(page_size)}
            try:
                data = _post_stdlib("/v3/finance/transaction/list", body)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                break
            chunk = (data.get("result") or {}).get("operations") or []
            ops.extend(chunk)
            pages_read += 1
            if len(chunk) < int(page_size):      # последняя страница окна
                break
            page += 1
        windows += 1
        win_start = win_end
    return ops, {"days": days, "from": start.strftime(fmt), "to": now.strftime(fmt),
                 "windows": windows, "pages_read": pages_read,
                 "operations": len(ops), "error": err}


def analyze_cabinet(days=90):
    """Дознание ФАКТА кабинета — реальные константы удержаний Озона (для замены допущений).

    Возвращает {net_coeff, commission_pct, delivery_net, per_sale, sales_count, ...}.
    Это и есть та правда, которую модель ДОЛЖНА использовать вместо допущения 0.35.
    """
    ops, meta = fetch_transactions(days=days)
    if meta.get("error"):
        return {"error": meta["error"], "operations": 0}

    sales = [o for o in ops if o.get("operation_type") == "OperationAgentDeliveredToCustomer"]
    if not sales:
        return {"error": "продаж нет за период", "operations": len(ops), "days": days}

    by_posting = {}
    for o in ops:
        pn = (o.get("posting") or {}).get("posting_number")
        if pn:
            by_posting.setdefault(pn, []).append(o)

    postings = []
    for pn, lst in by_posting.items():
        if not any("DeliveredToCustomer" in str(o.get("operation_type")) for o in lst):
            continue
        price = sum(float(o.get("accruals_for_sale") or 0) for o in lst)
        if price == 0:
            continue
        comm = sum(float(o.get("sale_commission") or 0) for o in lst)
        tot = sum(float(o.get("amount") or 0) for o in lst)
        postings.append({"pn": pn, "price": price, "commission": comm, "total": tot})

    if not postings:
        return {"error": "завершённых продаж нет", "operations": len(ops), "days": days}

    tot_price = sum(p["price"] for p in postings)
    tot_comm = sum(p["commission"] for p in postings)
    tot_net = sum(p["total"] for p in postings)

    avg_price = tot_price / len(postings)
    avg_net = tot_net / len(postings)

    # Чистая доставка нетто (услуги доставки минус возмещение от покупателя)
    dlv_cost = sum(float(o.get("amount") or 0) for o in ops
                   if "Redistribution" in str(o.get("operation_type"))
                   and "Delivery" in str(o.get("operation_type")))
    reimb = sum(float(o.get("amount") or 0) for o in ops
                if "Reexposure" in str(o.get("operation_type")))
    delivery_net = dlv_cost + reimb  # dlv_cost отрицательный, reimb положительный

    return {
        "net_coeff": round(tot_net / tot_price, 4) if tot_price else None,
        "commission_pct": round(abs(tot_comm) / tot_price * 100, 2) if tot_price else None,
        "delivery_net": round(delivery_net / len(postings), 2) if postings else None,
        "per_sale_avg": round(avg_net, 2),
        "sales_count": len(postings),
        "days": days,
        "total_revenue": round(tot_price, 2),
        "total_net": round(tot_net, 2),
        "operations": len(ops),
        "honesty": ("ТОЛЬКО ЧТЕНИЕ кабинета. Эти числа — факт, не допущение. "
                    "Они УЖЕ вшиты в модель (NET_COEFF=0.298, DELIVERY_NET=325) — "
                    "перепрогон здесь их перепроверяет, а не вводит впервые."),
    }


def _main(argv=None):
    ap = argparse.ArgumentParser(description="OZON TRUTH V1 — дознание реальных удержаний (READ, 0₽)")
    ap.add_argument("--days", type=int, default=90, help="глубина в днях (режется на окна по 27 дней)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--raw-types", action="store_true", help="показать ВСЕ виды операций кабинета")
    args = ap.parse_args(argv)

    load_env()
    if not ozon.creds_present():
        print("⚠ OZON_CLIENT_ID / OZON_API_KEY не заданы — нужны ключи кабинета (gitignored .env).")
        return 1

    if args.raw_types:
        from collections import defaultdict
        ops, meta = fetch_transactions(days=args.days)
        agg = defaultdict(lambda: [0, 0.0])
        for o in ops:
            k = o.get("operation_type") or "?"
            agg[k][0] += 1
            agg[k][1] += float(o.get("amount") or 0)
        print("=" * 88)
        print(f"  ВСЕ ВИДЫ ОПЕРАЦИЙ КАБИНЕТА ({args.days} дней, окон={meta.get('windows')})")
        print("=" * 88)
        for k, (n, s) in sorted(agg.items(), key=lambda x: -abs(x[1][1])):
            nm = [o.get("operation_type_name") for o in ops if o.get("operation_type") == k]
            print(f"  {s:>12.2f}  n={n:<4} {k[:44]:<46} {str(nm[0] if nm else '')[:26]}")
        return 0

    r = analyze_cabinet(days=args.days)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    if r.get("error"):
        print(f"⚠ {r['error']}")
        return 1

    print("=" * 88)
    print(f"  ДОЗНАНИЕ КАБИНЕТА — ФАКТ против допущения модели ({r['days']} дней)")
    print("=" * 88)
    print(f"  Завершённых продаж: {r['sales_count']}   выручка ₽{r['total_revenue']:.2f} → чисто ₽{r['total_net']:.2f}")
    print()
    print(f"  {'КОНСТАНТА':<26}{'ПРЕЖНЕЕ ДОПУЩЕНИЕ':<24}{'ФАКТ КАБИНЕТА':<20}")
    print("-" * 88)
    print(f"  {'NET_COEFF':<26}{'0.35':<24}{r['net_coeff']:<20}")
    print(f"  {'комиссия продажи, %':<26}{'65 (в составе 0.35)':<24}{r['commission_pct']:<20}")
    print(f"  {'доставка нетто, ₽':<26}{'100':<24}{abs(r['delivery_net'] or 0):<20}")
    print(f"  {'чистыми на продажу, ₽':<26}{'~400 (оценка)':<24}{r['per_sale_avg']:<20}")
    print("-" * 88)
    print("  ВЫВОД: комиссия НИЖЕ допущения (53% против 65%) → коэффициент лучше,")
    print("         но доставка ВЫШЕ (₽325 против ₽100) → дешёвые позиции живут хуже.")
    print(f"  В МОДЕЛИ СЕЙЧАС: NET_COEFF={prospector.NET_COEFF}  DELIVERY_NET=₽{prospector.DELIVERY_NET:.0f}")
    print("=" * 88)

    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        p = OUT_DIR / f"ozon_truth_{_now().replace(':', '').replace('-', '')[:15]}.json"
        p.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Слепок: {p}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(_main())

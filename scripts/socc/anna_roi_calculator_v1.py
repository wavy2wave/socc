#!/usr/bin/env python3
"""
ANNA ROI Calculator V1 — honest, conservative projection of money recovered.

This is узел B1 (owned by SCRIBE, atom c1). It computes a PROJECTED ROI from owner-supplied
or benchmark assumptions. It is NOT a proof-case: every number here is a projection with a
stated assumption. It becomes PROOF only when LEDGER (узел B3) replaces projected inputs with
MEASURED events from a real clinic (LEDGER law W1: every number traces to a logged event).

Honesty rules baked in (mirror LEDGER Λ):
  • Conservative by default: capture_rate defaults LOW; we count only plausibly-lost contacts.
  • Cost in denominator: ROI is net of ANNA's price (no vanity "revenue" framing).
  • Every output is labelled PROJECTION until measured.
  • Undercount, not overclaim — a number an owner can't refute beats a pretty one.

Usage:
  python3 anna_roi_calculator_v1.py \
      --avg-ticket 4000 --missed-per-day 4 --capture-rate 0.30 \
      --work-days 26 --anna-price 25000 [--json]
"""
import argparse, json


def compute(avg_ticket, missed_per_day, capture_rate, work_days, anna_price):
    # recovered appointments = contacts that would have been LOST, that ANNA plausibly converts
    recovered_appts = missed_per_day * work_days * capture_rate
    gross_recovered = recovered_appts * avg_ticket          # ₽ that would otherwise have walked
    net_recovered = gross_recovered - anna_price            # net of ANNA's monthly price
    roi_x = (gross_recovered / anna_price) if anna_price else float("inf")
    roi_pct = ((net_recovered / anna_price) * 100) if anna_price else float("inf")
    # payback: how many recovered appointments cover ANNA's monthly price
    appts_to_break_even = (anna_price / avg_ticket) if avg_ticket else float("inf")
    break_even_days = (appts_to_break_even / (missed_per_day * capture_rate)
                       if (missed_per_day * capture_rate) else float("inf"))
    return {
        "inputs": {
            "avg_ticket": avg_ticket, "missed_per_day": missed_per_day,
            "capture_rate": capture_rate, "work_days": work_days, "anna_price": anna_price,
        },
        "recovered_appointments_per_month": round(recovered_appts, 1),
        "gross_recovered_rub_per_month": round(gross_recovered),
        "net_recovered_rub_per_month": round(net_recovered),
        "roi_x": round(roi_x, 2),
        "roi_percent": round(roi_pct),
        "appointments_to_break_even": round(appts_to_break_even, 1),
        "break_even_days": round(break_even_days, 1),
        "label": "PROJECTION — assumptions, not measured. Becomes PROOF only via LEDGER (B3).",
    }


def main():
    ap = argparse.ArgumentParser(description="ANNA ROI projection (honest, conservative).")
    ap.add_argument("--avg-ticket", type=float, default=4000, help="средний чек приёма, ₽")
    ap.add_argument("--missed-per-day", type=float, default=4,
                    help="пропущенных контактов/день (ночь+занято+выходные)")
    ap.add_argument("--capture-rate", type=float, default=0.30,
                    help="доля, которую ANNA РЕАЛЬНО ловит (консервативно; 0.30 = осторожно)")
    ap.add_argument("--work-days", type=float, default=26, help="рабочих дней/мес")
    ap.add_argument("--anna-price", type=float, default=25000, help="цена ANNA, ₽/мес")
    ap.add_argument("--json", action="store_true", help="вывод JSON")
    a = ap.parse_args()
    r = compute(a.avg_ticket, a.missed_per_day, a.capture_rate, a.work_days, a.anna_price)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2)); return
    i = r["inputs"]
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("ANNA ROI — ПРОЕКЦИЯ (не доказательство)")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"вход: чек {i['avg_ticket']:.0f}₽ · пропусков/день {i['missed_per_day']:.0f} · "
          f"ловим {i['capture_rate']*100:.0f}% · {i['work_days']:.0f} дн · ANNA {i['anna_price']:.0f}₽/мес")
    print("—")
    print(f"возвращённых записей/мес : {r['recovered_appointments_per_month']}")
    print(f"возврат ₽/мес (грязн.)   : {r['gross_recovered_rub_per_month']:,}".replace(",", " "))
    print(f"возврат ₽/мес (за вычетом ANNA): {r['net_recovered_rub_per_month']:,}".replace(",", " "))
    print(f"ROI                      : {r['roi_x']}× ({r['roi_percent']}%)")
    print(f"окупаемость              : {r['appointments_to_break_even']} записей ≈ {r['break_even_days']} дней")
    print("—")
    print("⚠  " + r["label"])
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()

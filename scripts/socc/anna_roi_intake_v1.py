#!/usr/bin/env python3
"""
ANNA ROI Intake V1 — turns the B1 calculator into a fear-free sales conversation (node B1, SCRIBE).

WHY: deep research proved there is NO defensible public CIS "loss per missed call" figure
(see memory anna-roi-pain-number-source). So the honest — and MORE persuasive — number comes
from the clinic's OWN data: ask 3 simple questions, compute on the owner's answers. The operator
never quotes a scary internet stat (which a smart owner would demolish); he asks, the tool counts.

This does NOT re-forge B1: it IMPORTS compute() from anna_roi_calculator_v1.py and wraps it with
a guided intake + an owner-facing card + the exact words to say. Conservative defaults are used
ONLY when the owner doesn't know a number, and are flagged as estimates (no fabrication).

Bounded: stdlib only, no network, no canon/seal/ship.
Run:  python3 scripts/socc/anna_roi_intake_v1.py                          # print script + sample card
      python3 scripts/socc/anna_roi_intake_v1.py --name "Клиника X" \
          --ticket 5000 --missed 4 --days 26 --price 25000               # real clinic's numbers
Out:  proofs/socc/roi_intake/<slug>.json
"""
import argparse, json, re, importlib.util as _ilu
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]  # SOCC/
CALC = ROOT / "scripts/socc/anna_roi_calculator_v1.py"
OUTDIR = ROOT / "proofs/socc/roi_intake"

_spec = _ilu.spec_from_file_location("anna_roi_calculator_v1", CALC)
B1 = _ilu.module_from_spec(_spec); _spec.loader.exec_module(B1)   # reuse, don't duplicate

# Conservative fallbacks — used ONLY when the owner doesn't know, and flagged as estimates.
DEFAULTS = {"ticket": 4000, "missed": 3, "days": 26, "price": 25000, "capture": 0.30}

QUESTIONS = [
    ("ticket", "Какой у вас средний чек за первый приём?",
     "Если не знают — берём осторожные ₽4 000 и помечаем как оценку."),
    ("missed", "Сколько примерно звонков и сообщений в день остаётся без ответа — "
               "особенно вечером после 18:00 и в выходные?",
     "Самые ценные — именно вечерние/выходные: человек с острой болью пишет тогда."),
    ("days", "Сколько дней в месяц работаете?",
     "Обычно 26. Если не уверены — оставляем 26."),
]

SCRIPT = """КАК ВЕСТИ РАЗГОВОР (3 вопроса, без давления):
ОТКРЫТИЕ:  «Я не продавать. Хочу показать цифру по вашей же клинике, на ваших числах.
            Три коротких вопроса, посчитаем за минуту.»
  1) Средний чек за первый приём?
  2) Сколько звонков/сообщений в день примерно остаётся без ответа (особенно вечер/выходные)?
  3) Сколько дней в месяц работаете?
ЕСЛИ НЕ ЗНАЮТ → берём осторожную оценку и ЧЕСТНО это помечаем («это оценка, не ваши данные»).
ЗАКРЫТИЕ:  «Вот ваша цифра. Это проекция на ваших же допущениях. Хотите, поставим ANNA на 30 дней,
            и она заменит оценку измеренным фактом, посчитает каждую реально пойманную заявку.»
ПОЧЕМУ ЭТО РАБОТАЕТ: ты не уговариваешь и не цитируешь интернет, ты считаешь на его данных.
                     Цифру на собственных числах владельца невозможно оспорить."""


def slug(s):
    return re.sub(r"[^a-z0-9а-я]+", "-", (s or "clinic").lower()).strip("-") or "clinic"


def owner_card(name, r, flags):
    i = r["inputs"]
    note = " (оценка, не ваши данные)" if flags else ""
    cur = "₽"
    lines = [
        f"Расчёт для «{name}» — на ваших числах{note}:",
        f"  • средний чек: {cur}{int(i['avg_ticket'])}{' *' if 'ticket' in flags else ''}",
        f"  • пропущено контактов в день: {i['missed_per_day']:.0f}{' *' if 'missed' in flags else ''}"
        f"  (вечер/выходные — самые ценные)",
        f"  • из них ANNA реально ловит ~{i['capture_rate']*100:.0f}% (осторожная оценка)",
        "",
        f"Вы теряете ~{cur}{r['gross_recovered_rub_per_month']:,}/мес — это {r['recovered_appointments_per_month']} записей мимо."
        .replace(",", " "),
        f"ANNA возвращает их, минус её цена {cur}{int(i['anna_price'])}/мес → чистыми ~{cur}{r['net_recovered_rub_per_month']:,}/мес."
        .replace(",", " "),
        f"Окупается за ~{r['break_even_days']} дней. ROI {r['roi_x']}×.",
        "",
        "Это ПРОЕКЦИЯ на ваших допущениях. Поставим ANNA на 30 дней — заменим оценку измеренным фактом.",
    ]
    if flags:
        lines.append("* — отмеченное взято осторожной оценкой, заменим вашими точными данными.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="ANNA ROI intake — посчитать на числах клиники.")
    ap.add_argument("--name", default="Демо-клиника")
    ap.add_argument("--ticket", type=float, help="средний чек, ₽")
    ap.add_argument("--missed", type=float, help="пропущенных контактов/день")
    ap.add_argument("--days", type=float, help="рабочих дней/мес")
    ap.add_argument("--price", type=float, help="цена ANNA, ₽/мес")
    a = ap.parse_args()

    flags = set()   # which inputs fell back to a conservative estimate (owner didn't supply)
    vals = {}
    for key in ("ticket", "missed", "days", "price"):
        v = getattr(a, key)
        if v is None:
            vals[key] = DEFAULTS[key]; flags.add(key) if key in ("ticket", "missed") else None
        else:
            vals[key] = v

    r = B1.compute(vals["ticket"], vals["missed"], DEFAULTS["capture"], vals["days"], vals["price"])

    print(SCRIPT)
    print("\n" + "─" * 60 + "\n")
    print(owner_card(a.name, r, flags))

    OUTDIR.mkdir(parents=True, exist_ok=True)
    rep = {"id": "ANNA_ROI_INTAKE_V1", "clinic": a.name, "estimated_fields": sorted(flags),
           "result": r, "label": "PROJECTION on owner inputs — becomes PROOF via LEDGER (B3) after 30 days",
           "created_at_utc": datetime.now(timezone.utc).isoformat()}
    (OUTDIR / f"{slug(a.name)}.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nsaved → {(OUTDIR / (slug(a.name) + '.json')).relative_to(ROOT)}")


if __name__ == "__main__":
    main()

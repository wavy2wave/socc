#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT first-real-₽ recorder V1 — одна команда оператора, чтобы вписать ПЕРВЫЙ реальный verified ₽ (D2).

Это НЕ автоматизация добычи денег (клиента добываешь ты в реальном мире — см. P3_FIRST_LEAD_RUNBOOK.md).
Это безопасный RUBICON-инструмент записи: по умолчанию ПРЕВЬЮ (канон НЕ трогается), реальная запись —
только с --commit, и только если услуга РЕАЛЬНО оказана и деньги РЕАЛЬНО пришли (verify_source + сумма).
Орган физически не пишет verified без реального следа (ledger.verify) — выдумать доход нельзя.

Пример (превью):
  python3 socc_mint_record_v1.py --service "Telegram-бот автоответчик" --amount 1500 \
      --lead-ref "YD-12345" --source moy_nalog_receipt --ref "20260701-001" --inn 123456789012
Реальная запись в канон — добавь --commit.
"""
import sys
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import socc_mint_service_pay_v1 as service_pay      # noqa: E402
import socc_mint_service_cycle_v1 as service_cycle  # noqa: E402
import socc_mint_self_v1 as selfmod                 # noqa: E402


def main():
    p = argparse.ArgumentParser(description="Записать первый реальный ₽ (D2 услуги)")
    p.add_argument("--service", required=True, help="что за услуга (напр. 'Telegram-бот автоответчик')")
    p.add_argument("--amount", required=True, type=float, help="реальная сумма поступления/чека, ₽")
    p.add_argument("--lead-ref", required=True, dest="lead_ref", help="id заявки (YouDo/Avito) или 'direct-<контакт>'")
    p.add_argument("--executor", default="самозанятый (создатель)", help="кто оказал услугу")
    p.add_argument("--source", default="moy_nalog_receipt",
                   choices=list(service_pay.SOURCES.keys()), help="источник поступления")
    p.add_argument("--ref", required=True, help="след-идентификатор: receipt_id/operation_id/deal_id")
    p.add_argument("--inn", default=None, help="ИНН (для ссылки проверки чека НПД)")
    p.add_argument("--commit", action="store_true", help="РЕАЛЬНО записать в канон (RUBICON)")
    a = p.parse_args()

    # Валидация источника (чистая, без записи) — тот же страж, что и в t4.
    amt, ev = service_pay.fetch_service_payout("preview", a.source, ref=a.ref, amount=a.amount, inn=a.inn)
    if amt is None:
        print(f"❌ источник не подтверждён: {ev}")
        sys.exit(1)

    if not a.commit:
        print("ПРЕВЬЮ — канон НЕ тронут. Будет записано при --commit:")
        print(f"  вселенная:     D2 service-leadgen-RU")
        print(f"  услуга:        {a.service}  ·  исполнитель: {a.executor}")
        print(f"  сумма (verified): {a.amount:.0f} ₽")
        print(f"  verify_source: {a.source}  ·  ref: {a.ref}")
        print(f"  evidence:      {ev}")
        print("\nRUBICON: добавь --commit ТОЛЬКО если услуга реально оказана и деньги реально пришли.")
        return

    # --commit → реальная запись в КАНОН (claim + verify), первый реальный ₽.
    lead = {"service": a.service, "ticket_value": a.amount, "commission_rate": 1.0,
            "executor": a.executor, "lead_ref": a.lead_ref, "source": "manual"}
    payout = {"source": a.source, "ref": a.ref, "amount": a.amount, "inn": a.inn}
    res = service_cycle.run_service_connection(service_cycle.D2_SERVICE, lead, mode="real",
                                               fulfilled=True, payout=payout)
    print(f"status: {res['status']}  ·  {res['proof']['truth_boundary']}")
    if res["status"] == "PASS":
        selfmod.emit()
        print("\n🎉 ПЕРВЫЙ РЕАЛЬНЫЙ ₽ ВПИСАН В КАНОН.\n")
        print(selfmod.render())
    else:
        print("запись не прошла гейт — см. шаги:", [s for s in res["steps"] if not s["ok"]])


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MINT service payout V1 — руки t4 для вселенной услуг D2 (аналог socc_mint_ozon_v1.fetch_posting_payout).

`ledger.verify` venture-агностична: «реальность» источника обеспечивает ЭТА рука, читая реальное
поступление комиссии и возвращая (amount, evidence) | (None, why). Площадки услуг (Profi/YouDo/Avito) в
большинстве БЕЗ открытого API на выплату → источники полу-ручные: оператор читает реальный источник (банк/
СБП/чек НПД/эскроу) и передаёт идентификатор-след (operation_id/receipt_id/deal_id) и сумму. Рука проверяет
наличие следа и неотрицательность — НЕ интерпретирует текст, НЕ зовёт LLM (детерминизм, Φ(t4)).

Закон t4: verified=true ⟺ есть verify_source + сумма>0 + след-идентификатор. Нет следа → не verified.
Чистый stdlib; сетевые проверки (банк-API/ФНС) — ленивые, только если переданы ключи/чекер.
"""

# Допустимые источники поступления комиссии по убыванию машиночитаемости.
SOURCES = {
    "bank_statement_ip": "входящая операция по счёту ИП (выписка/банк-API) — деньги физически на счёте",
    "sbp_inbound": "входящий перевод по СБП на счёт самозанятого/ИП",
    "moy_nalog_receipt": "чек НПД в «Мой налог» — юридическое событие дохода (ФНС)",
    "youdo_escrow": "релиз эскроу YouDo (площадка-гарант отпустила деньги)",
    "profi_escrow": "релиз эскроу Profi.ru",
}

# Источники, где доказательством служит сам чек/налоговое событие (слабее банка — см. границу честности).
_RECEIPT_ONLY = {"moy_nalog_receipt"}


def npd_receipt_check_url(inn, receipt_id):
    """Публичная ссылка проверки чека НПД в ФНС (для evidence; проверяемость без нашего слова)."""
    if not (inn and receipt_id):
        return None
    return f"https://lknpd.nalog.ru/api/v1/receipt/{inn}/{receipt_id}/print"


def fetch_service_payout(connection_id, source, ref=None, amount=None, inn=None, online_check=None):
    """t4 verify_money для услуг. Возвращает (amount, evidence) | (None, why).

    source ∈ SOURCES. ref — идентификатор-след из реального источника (operation_id/receipt_id/deal_id),
    обязателен (Φ(t4) verified_implies_evidence). amount — сумма, прочитанная оператором из источника.
    online_check (опц.) — callable(source, ref, amount, inn) → bool для будущей авто-проверки (банк-API/ФНС);
    если вернёт False, верификация отклоняется. Без него источник полу-ручной (RUBICON на ref/сумму).
    """
    if source not in SOURCES:
        return None, f"неизвестный verify_source '{source}' (допустимы: {', '.join(SOURCES)})"
    if not ref:
        return None, f"{source}: нет идентификатора-следа (operation_id/receipt_id/deal_id) → нечем подтвердить (Φ(t4))"
    try:
        amt = round(float(amount), 2) if amount is not None else 0.0
    except Exception:
        amt = 0.0
    if amt <= 0:
        return None, f"{source}: сумма ≤ 0 — деньги не прочитаны из источника (не verified, LG2)"

    # Опциональная авто-проверка реального источника (банк-API/публичный чек ФНС). По умолчанию полу-ручной.
    if online_check is not None:
        try:
            if not online_check(source, ref, amt, inn):
                return None, f"{source}: онлайн-проверка источника не подтвердила поступление по {ref}"
        except Exception as e:  # сбой проверки → консервативно НЕ verified
            return None, f"{source}: онлайн-проверка упала ({e}) → не verified"

    evidence = {"source": source, "source_desc": SOURCES[source], "ref": str(ref),
                "connection_id": connection_id, "amount": amt,
                "receipt_only": source in _RECEIPT_ONLY}
    if source == "moy_nalog_receipt":
        evidence["check_url"] = npd_receipt_check_url(inn, ref)
        evidence["honesty_note"] = "чек подтверждает доход; для крупных сумм требуй ещё поступление на счёт"
    return amt, evidence


if __name__ == "__main__":
    import json
    demo = [
        ("c1", "bank_statement_ip", "OP-12345", 600),       # ок: банк + сумма
        ("c2", "moy_nalog_receipt", "20260630-777", 600),   # ок: чек НПД
        ("c3", "sbp_inbound", None, 600),                    # FAIL: нет следа
        ("c4", "youdo_escrow", "deal-9", 0),                 # FAIL: сумма 0
        ("c5", "unknown_src", "x", 600),                     # FAIL: источник не из списка
    ]
    for cid, src, ref, amt in demo:
        a, ev = fetch_service_payout(cid, src, ref=ref, amount=amt, inn="123456789012")
        print(f"{cid} {src:18} -> {'verified ' + str(a) + ' ₽' if a else 'REFUSED: ' + ev}")

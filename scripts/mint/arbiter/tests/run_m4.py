#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M4 ПРИЁМКА — BUY ADAPTER: ШОВ buy_on_wb (ManualTicket) + SETTLE (первый verified ₽), сухая, БЕЗ денег.

Веха M4 (шов выкупа + первый доход) + защита RUBICON. Все тесты оффлайн-детерминированы: сеть к
Ozon Finance подменяется (monkeypatch ozon.fetch_posting_payout), LEDGER — во ВРЕМЕННЫЙ путь. Реальные
ключи и деньги НЕ нужны и НЕ трогаются. Канон SOVEREIGN/LEDGER не трогается НИКОГДА.

  M4T1  ticket_from_task       — валидная задача выкупа → тикет оператору (что/где/сколько), bought=False.
  M4T2  ticket_rejects_bad     — невалидная задача (нет ok/города/номера) → тикет НЕ выдумывается.
  M4T3  ticket_bought_is_false — ManualTicket НИКОГДА не заявляет bought=True (машина не купила, купит человек).
  M4T4  browserbot_locked      — BrowserBot за флагом: выключен → честный отказ, НЕ фейк-покупка (RUBICON).
  M4T5  ticket_write_tmp       — write=True во ВРЕМЕННЫЙ путь → тикет записан, реальная очередь не тронута.
  M4T6  settle_dry_verified    — SETTLE(dry): claim→verify из симуляции, verified ₽, real_money=False.
  M4T7  settle_dry_no_canon    — SETTLE(dry) пишет в /tmp леджер, канонический revenue_ledger НЕ тронут.
  M4T8  settle_real_payout     — SETTLE(real) с payout>0 (подмена Finance) → verified, real_money=True.
  M4T9  settle_real_no_money   — SETTLE(real), денег в Finance ещё нет → ok=False, НЕ рисуем ₽ (RUBICON).
  M4T10 settle_real_apifail    — SETTLE(real), Ozon Finance упал → fail-soft, конвейер жив, НЕ verified.
  M4T11 settle_negative_econ   — эконом связки в минус → verify отказан (не верифицируем убыток).
  M4T12 ledger_verdict_clean   — после всех приёмок канон-вердикт LEDGER = PASS (ни одной левой verified).

M4T-live (опц.) — реальные ключи + реальный отгруженный posting → один живой SETTLE. SKIP без ключей.
Приёмка НИКОГДА не пишет в канонический леджер и не зовёт сеть (кроме опц. живого теста).
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

import buy_adapter_v1 as buy                       # noqa: E402
import socc_revenue_ledger_v1 as ledger            # noqa: E402
import socc_mint_ozon_v1 as ozon                   # noqa: E402


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


class _Ledger:
    """Направляет ledger.LEDGER во ВРЕМЕННЫЙ путь на время теста, гарантированно откатывает.

    Защита канона: что бы ни делал SETTLE, реальный SOVEREIGN/LEDGER/revenue_ledger.jsonl не тронут.
    """
    def __init__(self):
        self._save = None
        self.path = None

    def __enter__(self):
        self._save = ledger.LEDGER
        self.path = Path(tempfile.mkdtemp()) / "revenue_ledger.jsonl"
        ledger.LEDGER = self.path
        return self

    def __exit__(self, *a):
        ledger.LEDGER = self._save
        return False


class _Payout:
    """Подменяет ozon.fetch_posting_payout фейком (offline), гарантированно откатывает."""
    def __init__(self, fn):
        self._fn = fn
        self._save = None

    def __enter__(self):
        self._save = ozon.fetch_posting_payout
        ozon.fetch_posting_payout = self._fn
        return self

    def __exit__(self, *a):
        ozon.fetch_posting_payout = self._save
        return False


def _task(ok=True, posting="0001-0001-1", city="Казань", items=None):
    """Валидная задача выкупа в схеме bridge.to_buy_task (ok=True)."""
    return {"ok": ok, "posting_number": posting, "supplier": "wildberries",
            "deliver_to_city": city, "address_hint": "Баумана",
            "buy_items": items if items is not None else [{"name": "Дождевик", "sku": "SKU1", "quantity": 1}],
            "search": "Дождевик"}


ECON_OK = {"cost_buy": 111.0, "price_sell": 603.0, "fee": 40.0}       # нетто +452
ECON_NEG = {"cost_buy": 700.0, "price_sell": 650.0, "fee": 40.0}      # нетто -90


def t1_ticket_from_task():
    r = buy.make_buy_ticket(_task(), executor="manual_ticket", write=False)
    ok = (r["ok"] is True and r["executor"] == "manual_ticket" and r["bought"] is False
          and r["posting_number"] == "0001-0001-1" and "Казань" in r["instruction"]
          and "Дождевик" in r["instruction"])
    return ok, f"ok={r['ok']}, bought={r['bought']}, город-в-тикете={'Казань' in r['instruction']}"


def t2_ticket_rejects_bad():
    r_noc = buy.make_buy_ticket({"ok": False, "why": "без города"}, write=False)
    r_nop = buy.make_buy_ticket({"ok": True, "posting_number": None, "deliver_to_city": "X"}, write=False)
    r_junk = buy.make_buy_ticket("строка", write=False)
    ok = (r_noc["ok"] is False and r_nop["ok"] is False and r_junk["ok"] is False
          and all(r["bought"] is False for r in (r_noc, r_nop, r_junk)))
    return ok, f"невалидные → ok=False (3/3), bought везде False"


def t3_ticket_bought_is_false():
    """ManualTicket НИКОГДА не должен заявить bought=True — машина не купила, ставит задачу человеку."""
    rs = [buy.make_buy_ticket(_task(posting=f"P-{i}"), write=False) for i in range(5)]
    ok = all(r["ok"] and r["bought"] is False for r in rs)
    return ok, f"bought=False во всех {len(rs)} тикетах (машина не двигает деньги)"


def t4_browserbot_locked():
    """BrowserBot за флагом: из реестра всегда выключен → честный отказ, НЕ фейк-покупка (RUBICON)."""
    ex = buy.get_executor("browser_bot")
    r = ex.execute(_task())
    ok = (isinstance(ex, buy.BrowserBot) and ex.enabled is False
          and r["ok"] is False and r["bought"] is False and "выключен" in r["why"])
    return ok, f"executor={ex.key}, enabled={ex.enabled}, отказ={r['ok'] is False}"


def t5_ticket_write_tmp():
    tmp = Path(tempfile.mkdtemp()) / "buy_tickets.jsonl"
    r = buy.make_buy_ticket(_task(posting="W-7"), executor="manual_ticket", write=True, tickets_path=tmp)
    lines = tmp.read_text(encoding="utf-8").splitlines() if tmp.exists() else []
    canon_untouched = not buy.TICKETS_PATH.exists() or "W-7" not in buy.TICKETS_PATH.read_text(encoding="utf-8")
    ok = (r["ok"] is True and len(lines) == 1 and "W-7" in lines[0]
          and r.get("written_to") == str(tmp) and canon_untouched)
    return ok, f"записано строк={len(lines)}, канон-тикеты-нетронуты={canon_untouched}"


def t6_settle_dry_verified():
    with _Ledger():
        r = buy.settle_posting("CONN-DRY-1", "0001-0001-1", ECON_OK, mode="dry",
                               dry_ledger_path=str(Path(tempfile.mkdtemp()) / "dry.jsonl"))
    ok = (r["ok"] is True and r["stage"] == "verified" and r["verified_amount"] == 452.0
          and r["source"] == "dry_run_sim" and r["real_money"] is False)
    return ok, f"verified={r['ok']}, сумма={r['verified_amount']}, реальные_деньги={r['real_money']}"


def t7_settle_dry_no_canon():
    """SETTLE(dry) НЕ должен трогать канонический revenue_ledger — только /tmp песочницу."""
    with _Ledger() as L:
        canon_before = L.path.exists()
        dry = Path(tempfile.mkdtemp()) / "dry.jsonl"
        buy.settle_posting("CONN-DRY-2", "0002-0002-2", ECON_OK, mode="dry", dry_ledger_path=str(dry))
        # dry перенаправил ledger.LEDGER на dry → путь _Ledger (canon-заглушка) остался пуст
        canon_after = L.path.exists()
        dry_written = dry.exists() and dry.read_text(encoding="utf-8").strip() != ""
    ok = (canon_before is False and canon_after is False and dry_written is True)
    return ok, f"канон-леджер-создан={canon_after} (должно False), dry-записан={dry_written}"


def t8_settle_real_payout():
    """SETTLE(real) с реальным payout>0 (подмена Finance) → verified из ozon_finance, real_money=True."""
    def payout(posting, since_days=90):
        return 560.0, {"source": "ozon_finance_transaction_list", "posting_number": posting, "operations": 3}
    with _Ledger(), _Payout(payout):
        r = buy.settle_posting("CONN-REAL-1", "0003-0003-3", ECON_OK, mode="real")
    ok = (r["ok"] is True and r["stage"] == "verified" and r["verified_amount"] == 560.0
          and r["source"] == "ozon_finance" and r["real_money"] is True)
    return ok, f"verified={r['ok']}, сумма={r['verified_amount']}, источник={r['source']}, реальные={r['real_money']}"


def t9_settle_real_no_money():
    """SETTLE(real), денег в Finance ещё нет → ok=False, ₽ НЕ рисуем (RUBICON: сомнение → не verified)."""
    def no_money(posting, since_days=90):
        return None, f"Ozon Finance: операций по {posting} нет (деньги ещё не начислены)"
    with _Ledger(), _Payout(no_money):
        r = buy.settle_posting("CONN-REAL-2", "0004-0004-4", ECON_OK, mode="real")
    ok = (r["ok"] is False and r["verified_amount"] is None and "деньги ещё не начислены" in r["error"])
    return ok, f"ok={r['ok']} (не рисуем ₽), error={r['error'][:44]}"


def t10_settle_real_apifail():
    """SETTLE(real), Ozon Finance упал (ключи/сеть) → fail-soft, НЕ verified, конвейер жив."""
    def boom(posting, since_days=90):
        raise RuntimeError("401 Client-Id and Api-Key headers are required")
    with _Ledger(), _Payout(boom):
        r = buy.settle_posting("CONN-REAL-3", "0005-0005-5", ECON_OK, mode="real")
    ok = (r["ok"] is False and r["verified_amount"] is None and "Ozon Finance" in r["error"])
    return ok, f"ok={r['ok']}, fail-soft-error={r['error'][:44]}"


def t11_settle_negative_econ():
    """Эконом в минус → verify отказан: не верифицируем убыток как доход (честность ledger)."""
    with _Ledger():
        r = buy.settle_posting("CONN-NEG-1", "0006-0006-6", ECON_NEG, mode="dry",
                               dry_ledger_path=str(Path(tempfile.mkdtemp()) / "dry.jsonl"))
    ok = (r["ok"] is False and r["verified_amount"] is None)
    return ok, f"ok={r['ok']} (убыток не verified), error={r['error'][:40]}"


def t12_ledger_verdict_clean():
    """После полного цикла в изолированном леджере verdict=PASS: ни одной verified без claim/источника."""
    with _Ledger():
        dry = Path(tempfile.mkdtemp()) / "dry.jsonl"
        buy.settle_posting("CONN-V-1", "0007-0007-7", ECON_OK, mode="dry", dry_ledger_path=str(dry))
        # verdict читает ledger.LEDGER — в dry он указывает на dry-файл; проверим оба честны
        ledger.LEDGER = dry
        v = ledger.verdict()
    ok = (v["status"] == "PASS" and not v["verified_violations"])
    return ok, f"verdict={v['status']}, нарушений={len(v['verified_violations'])}"


def t_live_settle_optional():
    """Опц. живой SETTLE: реальные ключи + реальный отгруженный posting → читаем Ozon Finance, ничего не двигаем."""
    if not ozon.creds_present():
        return None, "SKIP: OZON_CLIENT_ID/OZON_API_KEY не заданы — живой SETTLE недоступен (и не нужен)"
    return None, "SKIP: живой SETTLE требует РЕАЛЬНЫЙ отгруженный posting_number от оператора (не автозапуск)"


TESTS = [
    ("M4T1 ticket_from_task", t1_ticket_from_task),
    ("M4T2 ticket_rejects_bad", t2_ticket_rejects_bad),
    ("M4T3 ticket_bought_is_false", t3_ticket_bought_is_false),
    ("M4T4 browserbot_locked", t4_browserbot_locked),
    ("M4T5 ticket_write_tmp", t5_ticket_write_tmp),
    ("M4T6 settle_dry_verified", t6_settle_dry_verified),
    ("M4T7 settle_dry_no_canon", t7_settle_dry_no_canon),
    ("M4T8 settle_real_payout", t8_settle_real_payout),
    ("M4T9 settle_real_no_money", t9_settle_real_no_money),
    ("M4T10 settle_real_apifail", t10_settle_real_apifail),
    ("M4T11 settle_negative_econ", t11_settle_negative_econ),
    ("M4T12 ledger_verdict_clean", t12_ledger_verdict_clean),
    ("M4-live settle (опц.)", t_live_settle_optional),
]


def main():
    print("═" * 68)
    print("  ARBITER · M4 ПРИЁМКА — BUY ADAPTER: ШОВ buy_on_wb + SETTLE (первый ₽, сухая)")
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
    print(f"ИТОГ M4:  {hard_pass}/{hard_total} обязательных зелёные"
          f"{f', {skipped} опциональных пропущено' if skipped else ''}")
    print("═" * 68)
    return 0 if hard_pass == hard_total else 1


if __name__ == "__main__":
    sys.exit(main())

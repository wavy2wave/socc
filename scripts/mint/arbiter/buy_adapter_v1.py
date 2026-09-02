#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUY ADAPTER V1 — ШОВ buy_on_wb + SETTLE (первый verified ₽) органа ARBITER.

Это M4 — единственный настоящий ШОВ всей машины и первый реальный доход.

ПОЧЕМУ ШОВ (дословно из MAIN OZON): у WB нет чистого buy-API для ПОКУПАТЕЛЯ — купить товар у
поставщика рядом с клиентом нельзя одним REST-вызовом. Значит выкуп — это либо рука оператора
(30 сек), либо браузер-робот (поздно, за флагом). Всё остальное в машине автоматизируется; здесь —
граница. Мы делаем шов СМЕННЫМ (BuyExecutor), чтобы хрупкость выкупа НЕ текла в ядро.

  BuyExecutor        — контракт исполнителя выкупа (execute(buy_task) → receipt). Новый способ купить
                       = новый подкласс, ядро не трогаем (зеркало SupplierAdapter).
  ManualTicket       — v1 БЕЗОПАСНЫЙ ДЕФОЛТ: превращает задачу выкупа в тикет оператору (что купить,
                       где, по какой цене, ссылка). bought=False — деньги двигает ЧЕЛОВЕК, не машина.
  BrowserBot         — M6-заглушка ЗА ФЛАГОМ: шов есть, но заблокирован (enabled=False → отказ, не
                       фейк-покупка). Playwright придёт позже, изолированно.

  settle_posting(...) — SETTLE: заказ отгружен → читаем Ozon Finance payout → LEDGER.verify. Это
                        первый РЕАЛЬНЫЙ ₽. RUBICON: verified=true ТОЛЬКО из реального поступления;
                        суммы не рисуем, деньги не двигаем — только читаем, что уже легло.

ГРАНИЦА ЧЕСТНОСТИ (RUBICON): этот файл НЕ покупает автоматически (ManualTicket = задача человеку),
НЕ рисует доход (verify только из Ozon Finance), НЕ трогает канон в dry. Реальный ₽ в канонический
LEDGER ложится лишь при mode='real' + реальных ключах + реальном posting с реальным payout>0.

Переиспускает socc_revenue_ledger_v1 (record_claim/verify) и socc_mint_ozon_v1 (fetch_posting_payout) —
НЕ дублирует. Чистый stdlib, ленивая сеть, fail-soft, без демона (закон вечной машины SOCC).
"""
import sys
import abc
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

import socc_mint_ozon_v1 as ozon                  # noqa: E402  (руки Ozon — Finance payout для SETTLE)
import socc_revenue_ledger_v1 as ledger          # noqa: E402  (честность дохода: claim → verify)

# Очередь тикетов на выкуп (что оператору купить руками) — канон ARBITER, append-only.
TICKETS_PATH = ROOT / "MEMORY_WAVE/reports/mint/arbiter/buy_tickets.jsonl"


def _now():
    return datetime.now(timezone.utc).isoformat()


# ── ШОВ buy_on_wb: контракт исполнителя выкупа ──────────────────────────────────
# Купить у поставщика рядом с клиентом. Способов может быть много (рука/браузер/будущий API) —
# ядро знает только этот контракт. receipt всегда честно говорит, КУПЛЕНО ли на самом деле.

class BuyExecutor(abc.ABC):
    """Контракт выкупа. Новый способ купить = новый подкласс. receipt.bought честен всегда."""
    key = "base"
    title = "Base"
    # moves_money=True ⟺ реализация реально двигает деньги (браузер-робот). RUBICON смотрит на это.
    moves_money = False

    @abc.abstractmethod
    def execute(self, buy_task):
        """buy_task (из bridge.to_buy_task, ok=True) → receipt dict. fail-soft, деньги по закону шва."""
        raise NotImplementedError

    def _reject(self, why):
        return {"ok": False, "executor": self.key, "bought": False, "why": why, "at": _now()}


class ManualTicket(BuyExecutor):
    """v1 БЕЗОПАСНЫЙ ДЕФОЛТ: задача выкупа → человекочитаемый тикет оператору. Деньги двигает ЧЕЛОВЕК.

    bought=False намеренно: машина НЕ купила — она поставила задачу «купи на WB рядом с клиентом X».
    Это RUBICON-безопасно: ни рубля не двинуто автоматически. Тикет можно писать в очередь (append-only).
    """
    key = "manual_ticket"
    title = "Ручной тикет оператору"
    moves_money = False

    def render(self, buy_task):
        """Человекочитаемый текст тикета — то, что оператор видит и делает руками за 30 сек."""
        items = buy_task.get("buy_items") or []
        what = "; ".join(
            f"{it.get('name') or ('sku ' + str(it.get('sku')))} ×{it.get('quantity', 1)}" for it in items
        ) or (buy_task.get("search") or "товар из заказа")
        city = buy_task.get("deliver_to_city") or "?"
        hint = buy_task.get("address_hint") or "адрес в заказе Ozon"
        return (f"🛒 ВЫКУП на {buy_task.get('supplier', 'wildberries')} рядом с клиентом\n"
                f"   заказ: {buy_task.get('posting_number')}\n"
                f"   купить: {what}\n"
                f"   доставить в: {city} ({hint})\n"
                f"   как: найди тот же товар на WB c ПВЗ рядом с клиентом, оформи на адрес клиента.")

    def execute(self, buy_task):
        if not (isinstance(buy_task, dict) and buy_task.get("ok")):
            return self._reject("задача выкупа невалидна (нет ok/города) — тикет не создаём из воздуха")
        if not buy_task.get("posting_number"):
            return self._reject("нет posting_number — не к чему привязать тикет")
        return {
            "ok": True,
            "executor": self.key,
            "bought": False,                       # ЧЕСТНО: купит человек, не машина
            "posting_number": buy_task.get("posting_number"),
            "supplier": buy_task.get("supplier", "wildberries"),
            "deliver_to_city": buy_task.get("deliver_to_city"),
            "instruction": self.render(buy_task),
            "buy_items": buy_task.get("buy_items") or [],
            "note": "оператор выкупает руками (30 сек). Авто-выкуп — BrowserBot за флагом, позже.",
            "at": _now(),
        }


class BrowserBot(BuyExecutor):
    """M6-заглушка авто-выкупа (Playwright). ЗА ФЛАГОМ: enabled=False → честный отказ, НЕ фейк-покупка.

    Шов физически есть (ядро уже умеет вызывать executor), но реализация заблокирована до явного
    решения оператора и реального браузер-робота. RUBICON: пока не включён — денег не двигает.
    """
    key = "browser_bot"
    title = "Браузер-робот (Playwright) — M6, за флагом"
    moves_money = True

    def __init__(self, enabled=False):
        self.enabled = bool(enabled)

    def execute(self, buy_task):
        if not self.enabled:
            return self._reject("BrowserBot выключен (M6, за флагом): авто-выкуп двигает реальные деньги — "
                                "требует явного включения оператором и живого браузер-робота")
        # Даже включённый — пока не реализован: НЕ имитируем покупку (честность > театр).
        return self._reject("BrowserBot включён, но авто-выкуп ещё не реализован (M6) — используй ManualTicket")


# Реестр исполнителей выкупа (зеркало реестра поставщиков). ManualTicket — единственный безопасный.
_EXECUTORS = {"manual_ticket": ManualTicket()}


def get_executor(key="manual_ticket"):
    """Достать исполнителя выкупа по ключу. Дефолт — безопасный ManualTicket."""
    if key == "browser_bot":
        return BrowserBot(enabled=False)          # всегда выключен из реестра — включают явно кодом
    return _EXECUTORS.get(key, _EXECUTORS["manual_ticket"])


def make_buy_ticket(buy_task, executor="manual_ticket", write=False, tickets_path=None):
    """Задача выкупа (bridge.to_buy_task) → тикет через выбранного исполнителя.

    write=False (дефолт) — только вернуть тикет, канон НЕ трогаем. write=True — дописать в buy_tickets.jsonl.
    RUBICON: ManualTicket денег не двигает; вернувшийся receipt['bought'] честен.
    """
    ex = get_executor(executor)
    receipt = ex.execute(buy_task)
    if write and receipt.get("ok"):
        path = Path(tickets_path) if tickets_path else TICKETS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(receipt, ensure_ascii=False) + "\n")
        receipt = dict(receipt, written_to=str(path))
    return receipt


# ── SETTLE: первый РЕАЛЬНЫЙ ₽ ────────────────────────────────────────────────────
# Заказ отгружен → деньги легли в Ozon Finance → читаем и записываем в LEDGER как verified.
# RUBICON: сумму не рисуем — читаем реальный payout. dry = симуляция (canon не тронут).

def settle_posting(connection_id, posting_number, econ, mode="dry", venture="ozon-dropship-RU",
                   item=None, dry_ledger_path=None):
    """SETTLE одного отгруженного заказа → verified ₽ в LEDGER.

    econ = {'cost_buy','price_sell','fee'} (из ECON/PROSPECTOR — честный юнит-эконом связки).
    mode='dry'  — verified из симуляции 'dry_run_sim', пишет во ВРЕМЕННЫЙ леджер (канон не тронут).
    mode='real' — читает Ozon Finance payout по posting_number; verified=true ТОЛЬКО при payout>0.

    Возвращает {'ok', 'stage', 'connection_id', 'verified_amount', 'source', 'error'}.
    Никогда не двигает деньги — только читает и записывает факт поступления.
    """
    if mode == "dry":
        # песочница: канон SOVEREIGN/LEDGER НЕ трогаем ни при каких условиях
        ledger.LEDGER = Path(dry_ledger_path) if dry_ledger_path else Path("/tmp/arbiter_m4_dry_ledger.jsonl")

    cost = float((econ or {}).get("cost_buy") or 0)
    price = float((econ or {}).get("price_sell") or 0)
    fee = float((econ or {}).get("fee") or 0)

    # Стадия 1: claim (verified=false) — обязательство исполнено, ₽ пока лишь ЗАЯВЛЕН
    ledger.record_claim(venture=venture, connection_id=connection_id, item=item or posting_number,
                        cost_buy=cost, price_sell=price, fee=fee,
                        meta={"mode": mode, "posting": posting_number, "organ": "ARBITER"})

    # Стадия 2: verify — деньги ПРОЧИТАНЫ из реального источника (или симуляция в dry)
    if mode == "dry":
        amount = round(price - cost - fee, 2)     # ожидаемый нетто (симуляция поступления)
        if amount <= 0:
            return {"ok": False, "stage": "verify", "connection_id": connection_id,
                    "verified_amount": None, "source": None,
                    "error": "dry: ожидаемый нетто ≤ 0 — нечего верифицировать (эконом связки не в плюсе)"}
        vrec, err = ledger.verify(connection_id, amount, "dry_run_sim",
                                  evidence={"mode": "dry", "posting": posting_number,
                                            "note": "симуляция поступления — НЕ реальные деньги"})
    else:
        if not posting_number:
            return {"ok": False, "stage": "verify", "connection_id": connection_id,
                    "verified_amount": None, "source": None,
                    "error": "real: нет posting_number — нечего сверять в Ozon Finance"}
        try:
            amount, ev = ozon.fetch_posting_payout(posting_number)
        except Exception as e:                     # ключи/сеть/requests — fail-soft, не рушим конвейер
            return {"ok": False, "stage": "verify", "connection_id": connection_id,
                    "verified_amount": None, "source": None,
                    "error": f"real: чтение Ozon Finance недоступно ({type(e).__name__}: {e})"}
        if amount is None:                         # деньги ещё не легли — честно НЕ verified
            return {"ok": False, "stage": "verify", "connection_id": connection_id,
                    "verified_amount": None, "source": None,
                    "error": f"real: {ev}"}
        vrec, err = ledger.verify(connection_id, amount, "ozon_finance", evidence=ev)

    if err:
        return {"ok": False, "stage": "verify", "connection_id": connection_id,
                "verified_amount": None, "source": None, "error": err}
    return {"ok": True, "stage": "verified", "connection_id": connection_id,
            "verified_amount": vrec["verify_amount"], "source": vrec["verify_source"],
            "real_money": ledger.is_real_source(vrec["verify_source"]), "error": None}


def _main(argv=None):
    ap = argparse.ArgumentParser(description="BUY ADAPTER V1 — ШОВ buy_on_wb (ManualTicket) + SETTLE (первый ₽)")
    ap.add_argument("--demo", action="store_true", help="показать тикет выкупа на sample-заказе (0₽, канон не тронут)")
    ap.add_argument("--settle-dry", action="store_true", help="прогнать SETTLE в песочнице (симуляция ₽, канон не тронут)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.settle_dry:
        r = settle_posting("DEMO-CONN-1", "DEMO-0001-0001-1",
                           {"cost_buy": 111.0, "price_sell": 603.0, "fee": 40.0}, mode="dry")
        print(json.dumps(r, ensure_ascii=False, indent=2) if args.json
              else f"🧪 SETTLE(dry): verified={r['ok']} сумма={r.get('verified_amount')} "
                   f"источник={r.get('source')} реальные_деньги={r.get('real_money')}")
        return 0

    # дефолт/--demo: показать тикет выкупа на sample-заказе (как из bridge.to_buy_task)
    sample = {"ok": True, "posting_number": "DEMO-0001-0001-1", "supplier": "wildberries",
              "deliver_to_city": "Казань", "address_hint": "Баумана",
              "buy_items": [{"name": "Дождевик-пончо", "sku": "SKU1", "quantity": 1}],
              "search": "Дождевик-пончо"}
    receipt = make_buy_ticket(sample, executor="manual_ticket", write=False)
    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        print("🌉 BUY ADAPTER · ШОВ buy_on_wb (ManualTicket, 0₽, канон не тронут)")
        print(receipt.get("instruction", receipt.get("why")))
        print(f"   куплено_машиной={receipt.get('bought')}  (v1: выкуп руками оператора)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

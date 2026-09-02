"""WAVE — тесты кабинета «ввёл ключ → отсчёт» (задача #17).

Оператор попросил ровно это: «человек вводит ключ, и начинается отсчёт.
Сколько РЕАЛЬНО потрачено — ОТОБРАЖАЕТСЯ, взломать нельзя». И решил, что клиент
видит расход В ЕГО РУБЛЯХ (по цене, которую заплатил), а НЕ закупку оператора.

Здесь мы охраняем каждое из этих обещаний:

  1. ₽ считаются по ЦЕНЕ КЛИЕНТА: price_rub × доля израсходованного объёма.
  2. Взломать нельзя: и цена, и расход лежат на сервере (в ключе и в usage),
     клиент их не задаёт — /v1/status отдаёт уже посчитанное число.
  3. Закупка/маржа оператора в /v1/status НЕ утекают (нет caps_cost_rub и т.п.).
  4. Докупка пакета складывает и объём, и уплаченную сумму (₽/CAPS не «едет»).
  5. Продление подписки обнуляет и расход, и цену (новый оплаченный период).
  6. Ключ, выданный другу бесплатно (price_rub=0), честно показывает 0 ₽.
  7. Кабинет-страница живёт на шлюзе (GET /) — у оффлайн-получателя это его
     единственное окно; сама страница ничего не считает, тянет /v1/status.

Запуск:  python3 tests/dashboard_spend_v1.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.quota import QuotaStore  # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


def main() -> int:  # noqa: C901
    tmp = Path(tempfile.mkdtemp(prefix="wave_dash_test_"))
    try:
        gq = QuotaStore(tmp)

        # ═══ 1. ₽ по цене клиента: доля объёма × заплаченная сумма ═══
        # Пакет 3 млн CAPS за 990 ₽; клиент сжёг ровно половину.
        rec = gq.issue_key(user_id=1, plan_id="pack_3m", order_id="o1",
                           price_rub=990)
        limit = int(rec["tokens_limit"])
        check(int(rec.get("price_rub", -1)) == 990,
              "цена клиента записана в ключ при выдаче (990 ₽)")

        gq.consume(rec["token"], limit // 2, "claude-opus-5")
        st = gq.status(rec["token"])
        check(abs(float(st["spent_rub"]) - 495.0) < 0.5,
              f"потрачено ровно половина цены: {st['spent_rub']} ₽ (ждём ~495)")
        check(abs(float(st["remaining_rub"]) - 495.0) < 0.5,
              f"остаток в ₽ = вторая половина: {st['remaining_rub']} ₽")
        check(st["price_rub"] == 990, "цена в статусе = что заплатил клиент")

        # ═══ 2. Взломать нельзя: клиент НЕ задаёт ни цену, ни расход ═══
        # status() берёт price_rub из записи ключа, tokens_used — из consume
        # (а consume зовёт только шлюз из ответа провайдера). В сигнатуре
        # status() нет ни одного клиентского входа, кроме токена и now.
        st_again = gq.status(rec["token"])
        check(st_again["spent_rub"] == st["spent_rub"],
              "повторный запрос статуса даёт то же число — оно не с клиента")
        # Даже если клиент «попросит» другую цифру — её негде передать:
        import inspect
        params = set(inspect.signature(gq.status).parameters) - {"self"}
        check(params <= {"token", "now"},
              f"у status() нет входов для подделки суммы (параметры: {params})")

        # ═══ 3. Закупка/маржа оператора НЕ утекают наружу ═══
        blob = json.dumps(st, ensure_ascii=False).lower()
        forbidden = ["cost", "margin", "маржа", "закуп", "usd", "profit", "caps_cost"]
        leaked = [w for w in forbidden if w in blob]
        check(not leaked,
              f"в /v1/status нет закупки/маржи оператора (утечки: {leaked or 'нет'})")

        # ═══ 4. Докупка пакета складывает и объём, и ₽ ═══
        gq.extend(rec["token"], "pack_3m", price_rub=990)
        st2 = gq.status(rec["token"])
        check(st2["price_rub"] == 1980,
              f"докупка сложила уплаченную сумму (990+990={st2['price_rub']})")
        check(int(st2["tokens_limit"]) == limit * 2,
              "докупка сложила и объём (лимит удвоился)")
        # Потрачено по-прежнему половина ПЕРВОГО пакета от НОВОЙ базы:
        # использовано limit/2 из 2*limit → четверть → 1980/4 = 495 ₽.
        check(abs(float(st2["spent_rub"]) - 495.0) < 1.0,
              f"после докупки ₽/CAPS не «поехал»: {st2['spent_rub']} ₽ (ждём ~495)")

        # ═══ 5. Продление подписки обнуляет и расход, и цену ═══
        sub = gq.issue_key(user_id=2, plan_id="sub_5m", order_id="s1",
                           price_rub=1490)
        gq.consume(sub["token"], int(sub["tokens_limit"]) // 2, "claude-opus-5")
        s_before = gq.status(sub["token"])
        check(float(s_before["spent_rub"]) > 0, "до продления расход в ₽ ненулевой")
        gq.extend(sub["token"], "sub_5m", price_rub=1490)
        s_after = gq.status(sub["token"])
        check(float(s_after["spent_rub"]) == 0.0,
              "продление подписки обнулило расход в ₽ (новый оплаченный месяц)")
        check(s_after["price_rub"] == 1490,
              "цена периода — за новый месяц, а не сумма (подписка не копится)")

        # ═══ 6. Друг без оплаты: 0 ₽, честно ═══
        free = gq.issue_key(user_id=3, plan_id="friend_20m", order_id="manual")
        gq.consume(free["token"], 50_000, "claude-sonnet-5")
        st_free = gq.status(free["token"])
        check(int(st_free["price_rub"]) == 0 and float(st_free["spent_rub"]) == 0.0,
              "выданный другу бесплатно ключ показывает 0 ₽ (не выдумываем сумму)")
        check(int(st_free["tokens_used"]) == 50_000,
              "но расход в токенах у бесплатного ключа виден честно")

        # ═══ 7. Кабинет-страница живёт на шлюзе и ничего не считает сама ═══
        os.environ["WAVE_DATA_DIR"] = str(tmp)
        os.environ["WAVE_GW_PORT"] = "8796"
        os.environ["WAVE_GW_HOST"] = "127.0.0.1"
        import importlib
        import gateway.proxy as proxy
        importlib.reload(proxy)
        page = proxy.METER_PAGE
        check("<title>" in page and "wave-" in page.lower(),
              "страница кабинета — валидный HTML с полем под ключ")
        check("/v1/status" in page,
              "страница берёт числа из /v1/status (сама расход не считает)")
        # Ищем именно операторскую экономику как ИМЕНА полей/понятий, а не как
        # случайные подстроки: «margin» есть в CSS (margin:), это не утечка.
        # Утекло бы то, что реально называется закупкой/маржой в коде.
        for w in ("caps_cost", "margin_rub", "margin_report", "маржа",
                  "закуп", "usd_per_cap", "profit", "recommend_price"):
            check(w not in page.lower(), f"в разметке нет операторской экономики ({w})")
        check("Bearer" in page,
              "ключ уходит на сервер в заголовке Authorization, не в разметке")

        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        print(f"\n{'=' * 60}\nИТОГ: {passed}/{total} проверок пройдено")
        if passed == total:
            print("💸 КАБИНЕТ: расход в ₽ по цене клиента, посчитан на сервере, "
                  "взломать нечем, закупка оператора не видна.")
            return 0
        print("Есть красные проверки — смотрите выше.")
        return 1
    finally:
        for k in ("WAVE_DATA_DIR", "WAVE_GW_PORT", "WAVE_GW_HOST"):
            os.environ.pop(k, None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

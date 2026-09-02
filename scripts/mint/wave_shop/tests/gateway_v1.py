"""WAVE GATEWAY — тесты. Проверяем то, на чём теряют деньги.

Главные риски, которые тут закрываются:
  1. Ключ оператора утёк клиенту → потеря всего баланса.
  2. Клиент превысил квоту → работает бесплатно за твой счёт.
  3. «Безлимит» без потолка → один бот-циклер выжирает $10 000 за ночь.
  4. Истёкший тариф продолжает работать → бесплатный доступ навсегда.

Запуск:  python3 tests/gateway_v1.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.quota import PLANS, QuotaStore  # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave_gw_test_"))
    try:
        q = QuotaStore(tmp)

        # ---------- Тарифная сетка ----------
        check(len(PLANS) >= 9, f"тарифов в сетке: {len(PLANS)}")
        kinds = {p["kind"] for p in PLANS.values()}
        check(kinds == {"hourly", "package", "subscription", "unlimited", "postpaid"},
              f"все виды тарифов на месте (вкл. потокенный): {sorted(kinds)}")

        # ---------- Пакет: квота режет ----------
        pack = q.issue_key(1, "pack_5m", "o1")
        t = pack["token"]
        check(t.startswith("wave-"), "токен клиента имеет свой префикс (не ключ оператора)")
        check(q.check(t).allow, "свежий пакет: доступ открыт")
        q.consume(t, 5_000_000, "claude-opus-5")
        v = q.check(t)
        check(not v.allow and v.reason == "quota", "пакет исчерпан → доступ закрыт")
        check("Пополните" in v.message, "клиент получает понятный текст, а не код ошибки")

        # ---------- Пакет живёт долго, но НЕ бессрочно ----------
        # Бессрочный пакет — это обязательство против поставки, которую провайдер
        # может отрезать. Даём год: клиенту ощущается как «не сгорает», а долга нет.
        pack2 = q.issue_key(2, "pack_5m", "o2")
        exp = int(q.get_key(pack2["token"])["expires_at"])
        days_left = (exp - int(time.time())) // 86400
        check(360 <= days_left <= 366,
              f"пакет живёт год, а не бессрочно ({days_left} дней)")

        # ---------- Почасовой: время режет ----------
        hourly = q.issue_key(3, "hour_1", "o3")
        th = hourly["token"]
        check(q.check(th).allow, "почасовой: сразу после покупки работает")
        keys = json.loads((tmp / "gw_keys.json").read_text())
        keys[th]["expires_at"] = int(time.time()) - 1     # промотали время
        (tmp / "gw_keys.json").write_text(json.dumps(keys))
        v = q.check(th)
        check(not v.allow and v.reason == "expired", "почасовой истёк → доступ закрыт")

        # ---------- Безлимит: суточный потолок спасает от циклера ----------
        unlim = q.issue_key(4, "unlim", "o4")
        tu = unlim["token"]
        check(q.check(tu).allow, "безлимит: работает без счётчика объёма")
        cap = PLANS["unlim"]["daily_cap_caps"]
        q.consume(tu, cap + 1, "claude-opus-5")
        v = q.check(tu)
        check(not v.allow and v.reason == "daily_cap",
              "безлимит: суточный потолок остановил бот-циклер")
        check("справедлив" in v.message.lower(),
              "клиенту объясняют причину честно, без обмана")

        # ---------- Отключение клиента ----------
        blocked = q.issue_key(5, "pack_5m", "o5")
        tb = blocked["token"]
        q.set_enabled(tb, False)
        v = q.check(tb)
        check(not v.allow and v.reason == "disabled", "оператор может отключить клиента мгновенно")

        # ---------- Несуществующий ключ ----------
        v = q.check("wave-ФЕЙК")
        check(not v.allow and v.reason == "no_key", "левый токен отбит")

        # ---------- Продление подписки ----------
        sub = q.issue_key(6, "sub_10m", "o6")
        ts = sub["token"]
        q.consume(ts, 9_000_000, "claude-opus-5")
        before = q.status(ts)["tokens_left"]
        q.extend(ts)
        after = q.status(ts)
        check(after["tokens_left"] > before, "продление подписки обновило месячную квоту")
        check(after["expires_at"] > sub["expires_at"], "продление сдвинуло срок вперёд")

        # ---------- Учёт расхода ----------
        acc = q.issue_key(7, "pack_5m", "o7")
        ta = acc["token"]
        q.consume(ta, 1000, "claude-opus-5")
        q.consume(ta, 2000, "claude-opus-5")
        st = q.status(ta)
        check(st["tokens_used"] == 3000 and st["requests"] == 2,
              f"расход считается точно: {st['tokens_used']} ток. за {st['requests']} запроса")

        # ---------- Изоляция клиентов ----------
        a = q.issue_key(8, "pack_5m", "o8")["token"]
        b = q.issue_key(9, "pack_5m", "o9")["token"]
        q.consume(a, 1_000_000, "m")
        check(q.status(b)["tokens_used"] == 0,
              "расход одного клиента не влияет на другого")

        # ---------- Ключ оператора нигде не хранится ----------
        blob = ""
        for f in tmp.glob("*.json"):
            blob += f.read_text()
        check("sk-" not in blob and "OPERATOR" not in blob,
              "в файлах шлюза нет ключа оператора — он только в окружении")

        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        print(f"\n{'=' * 52}\nИТОГ: {passed}/{total} проверок пройдено")
        if passed == total:
            print("🔐 WAVE GATEWAY: квоты держат, ключ оператора защищён.")
            return 0
        print("Есть красные проверки — смотрите выше.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

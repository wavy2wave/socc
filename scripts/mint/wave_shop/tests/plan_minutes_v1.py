"""WAVE GATEWAY — тесты короткого доступа «по минутам» (тариф для друзей).

Что тут защищаем:
  1. Тариф на 20 минут даёт РОВНО 20 минут доступа и пропорциональную квоту,
     а не «час» и не «весь дневной объём».
  2. Поддержка поля minutes в hourly не сломала старые часовые тарифы
     (у них minutes нет — должно считаться ровно как раньше).
  3. Ключ выдаётся тем же QuotaStore и истекает по времени.
  4. Оффлайн-CLI выдачи (gateway.issue) выпускает рабочий wave-ключ без покупки.

Запуск:  python3 tests/plan_minutes_v1.py
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.quota import (  # noqa: E402
    PLANS,
    QuotaStore,
    _hourly_seconds,
    plan_quota_caps,
)

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave_minutes_test_"))
    try:
        # ---------- Математика тарифа (чистые функции) ----------
        friend = PLANS["friend_20m"]
        check(friend["kind"] == "hourly", "friend_20m — почасовой вид (просто < часа)")
        check(_hourly_seconds(friend) == 1200,
              f"20 минут = 1200 секунд (получено {_hourly_seconds(friend)})")
        caps = plan_quota_caps(friend)
        check(caps == 110_000,
              f"квота = caps_per_hour × 20/60 = 110 000 CAPS (получено {caps})")

        # ---------- Старые часовые тарифы не тронуты ----------
        check(_hourly_seconds(PLANS["hour_1"]) == 3600, "hour_1: ровно 3600 с (minutes нет)")
        check(plan_quota_caps(PLANS["hour_1"]) == 330_000, "hour_1: квота 330 000 CAPS, как раньше")
        check(_hourly_seconds(PLANS["hour_6"]) == 6 * 3600, "hour_6: 6 часов без изменений")
        check(_hourly_seconds({"kind": "hourly"}) == 3600,
              "срок не задан вовсе → безопасный дефолт 1 час")
        check(_hourly_seconds({"kind": "hourly", "hours": 1, "minutes": 30}) == 5400,
              "часы И минуты складываются (1ч30м = 5400 с)")

        # ---------- Выдача ключа: срок и лимит ложатся на запись ----------
        q = QuotaStore(tmp)
        now = int(time.time())
        rec = q.issue_key(user_id=42, plan_id="friend_20m", order_id="manual")
        token = rec["token"]
        check(token.startswith("wave-"), "выдан брендированный токен (не ключ оператора)")
        exp = int(rec["expires_at"])
        check(1198 <= exp - now <= 1202, f"expires_at ≈ now + 1200 с (Δ={exp - now})")
        check(int(rec["tokens_limit"]) == 110_000, "tokens_limit = 110 000 CAPS")

        # ---------- До срока работает, после — закрыт ----------
        check(q.check(token, now=now).allow, "сразу после выдачи: доступ открыт")
        v = q.check(token, now=now + 1201)
        check(not v.allow and v.reason == "expired",
              "через 20 минут доступ закрыт по времени (не бесплатен навсегда)")

        # ---------- Квота режет раньше срока, если друг = агент-циклер ----------
        fresh = q.issue_key(user_id=43, plan_id="friend_20m", order_id="manual")
        tf = fresh["token"]
        q.consume(tf, 110_000, "gpt")
        vq = q.check(tf, now=now)
        check(not vq.allow and vq.reason == "quota",
              "исчерпав 110k CAPS за 20 минут, циклер упирается в квоту")

        # ---------- Оффлайн-CLI выдачи (gateway.issue) ----------
        import os
        os.environ["WAVE_DATA_DIR"] = str(tmp)
        # Перечитать модуль с нашим DATA_DIR: issue.py читает env на импорте.
        import importlib

        import gateway.issue as issue_mod
        importlib.reload(issue_mod)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = issue_mod.main(["--plan", "friend_20m", "--user", "99", "--json"])
        out = buf.getvalue()
        check(rc == 0, "CLI: выдача завершилась успешно (rc=0)")
        data = json.loads(out)
        check(str(data["token"]).startswith("wave-") and data["seconds_left"] > 0,
              "CLI: выпущен рабочий wave-ключ со сроком")
        # Ключ реально попал в тот же store, что видит шлюз.
        check(q.get_key(data["token"]) is not None,
              "CLI-ключ лежит в общем gw_keys.json — шлюз его уже знает")

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            rc2 = issue_mod.main(["--list-plans"])
        check(rc2 == 0 and "friend_20m" in buf2.getvalue(),
              "CLI: --list-plans показывает тарифы, включая friend_20m")

        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        print(f"\n{'=' * 52}\nИТОГ: {passed}/{total} проверок пройдено")
        if passed == total:
            print("⏱  Короткий доступ: 20 минут = 20 минут, час остался часом.")
            return 0
        print("Есть красные проверки — смотрите выше.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

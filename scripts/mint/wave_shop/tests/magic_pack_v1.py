"""WAVE — тесты «пак мэджик»: крупные пакеты токенов + вход Claude Code.

Оператор попросил ровно это: «друг взял у меня на 300 млн токенов… пак мэджк,
который сам запускает клауд, создаёт конфиги нужные… одна команда — началась
магия». Здесь мы охраняем каждое обещание такого пака от тихой поломки:

  1. Пакет на 300 млн CAPS реально выдаётся и даёт ровно этот лимит.
  2. Вход в Claude Code идёт по НАТИВНОМУ адресу Anthropic — БЕЗ /v1 на конце
     (иначе клиент бьёт /v1/v1/messages и получает 404 «магия не завелась»).
  3. «Магия» одной командой создаёт лаунчер и запускает claude — но НЕ трогает
     ~/.claude/settings.json клиента (там может быть его рабочая настройка).
  4. Никакого curl|sh: клиент видит весь скрипт, ключ оператора в нём не светит.
  5. Конфиг Claude Code не содержит срока/остатка — переживает продление.

Запуск:  python3 tests/magic_pack_v1.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.quota import (                                  # noqa: E402
    PLANS, QuotaStore, get_plan, model_allowed, plan_quota_caps,
)
from gateway.setup_kit import (                              # noqa: E402
    anthropic_base, claude_env, claude_magic, model_for_key,
    public_gateway, setup_payload,
)

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave_magic_test_"))
    os.environ["WAVE_PUBLIC_GATEWAY"] = "https://api.example.com/v1"
    try:
        # ═══ 1. Крупные пакеты токенов ═══
        for pid, want in (("pack_100m", 100_000_000), ("pack_300m", 300_000_000)):
            plan = get_plan(pid)
            check(plan is not None and plan.get("kind") == "package",
                  f"{pid} есть в сетке и это пакет")
            check(plan_quota_caps(plan) == want,
                  f"{pid} даёт ровно {want:,} CAPS")

        gq = QuotaStore(tmp)
        rec = gq.issue_key(user_id=300, plan_id="pack_300m", order_id="o1")
        check(int(rec["tokens_limit"]) == 300_000_000,
              "выданный ключ на 300 млн несёт правильный лимит")
        st = gq.status(rec["token"])
        check(int(st["tokens_left"]) == 300_000_000,
              f"остаток на свежем паке = 300 млн ({st['tokens_left']:,})")
        # Пакет живёт ~год, но НЕ бессрочно (поставку могут отрезать).
        days_left = int(st["seconds_left"]) / 86400
        check(360 <= days_left <= 366,
              f"срок пакета ~12 мес, не бессрочно ({days_left:.0f} дн.)")

        # Докупка складывает объём (extend по тому же паку).
        gq.consume(rec["token"], 50_000_000, "claude-opus-5")
        gq.extend(rec["token"], "pack_300m")
        st2 = gq.status(rec["token"])
        check(int(st2["tokens_limit"]) == 600_000_000,
              "докупка пакета складывает лимит (300M+300M)")

        # ═══ 2. Адрес Claude Code — БЕЗ /v1 (иначе /v1/v1/messages → 404) ═══
        check(public_gateway() == "https://api.example.com/v1",
              "OpenAI-адрес заканчивается на /v1 (как и было)")
        check(anthropic_base() == "https://api.example.com",
              f"Anthropic-адрес БЕЗ /v1 — клиент сам допишет /v1/messages "
              f"({anthropic_base()})")
        # Именно так строит путь Anthropic SDK: base + /v1/messages.
        check(anthropic_base() + "/v1/messages" == "https://api.example.com/v1/messages",
              "склейка base + /v1/messages даёт ровно один /v1 — путь, "
              "который обслуживает шлюз (do_POST принимает /v1/messages)")

        # ═══ 3. «Магия» одной командой ═══
        kit = setup_payload(rec)
        magic = kit["claude_magic"]
        check("claude_magic" in kit and "claude_env" in kit
              and "anthropic_base_url" in kit,
              "setup_payload отдаёт поля Claude Code")
        check(rec["token"] in magic, "в магии стоит реальный ключ клиента")
        check("ANTHROPIC_BASE_URL=" in magic and "ANTHROPIC_AUTH_TOKEN=" in magic,
              "магия задаёт базовый адрес и токен для Claude Code")
        check("ANTHROPIC_SMALL_FAST_MODEL=" in magic,
              "фоновую модель тоже фиксируем — иначе Claude Code зовёт haiku, "
              "которой может не быть у бэкенда, и падает на 404")
        check("~/.wave/start-claude.sh" in magic and "exec claude" in magic,
              "магия создаёт лаунчер и запускает claude — как просил оператор")

        # ═══ 3-бис. DO-NO-HARM: НЕ трогаем чужой ~/.claude/settings.json ═══
        check("~/.claude" not in magic and ".claude/settings" not in magic,
              "магия НЕ перезаписывает настройку Claude Code клиента "
              "(там может быть его рабочий конфиг)")

        # ═══ 4. Никакого curl|sh — клиент видит, что применяет ═══
        first_line = magic.split("\n", 1)[0].lower()
        check("curl" not in first_line and "| sh" not in magic and "|sh" not in magic,
              "установка не качает и не исполняет чужой скрипт")

        # ═══ 5. Конфиг переживает продление: нет срока/остатка ═══
        blob = kit["claude_magic"] + kit["claude_env"] + kit["claude_oneliner"]
        check("expires" not in blob and "tokens_left" not in blob
              and "seconds_left" not in blob,
              "в конфиге Claude Code нет срока и остатка — верен после продления")

        # ═══ 6. Модель в конфиге разрешена тарифом (файл рабочий) ═══
        check(model_allowed(kit["model"], rec.get("model_key", "")),
              "модель в магии проходит проверку шлюза — не упрётся в отказ")

        # Демо (потолок sonnet) → в Claude Code-конфиг попадает именно sonnet.
        demo_rec = gq.issue_key(user_id=301, plan_id="demo", order_id="o2")
        demo_kit = setup_payload(demo_rec)
        check(demo_kit["model"] == "claude-sonnet-5"
              and "claude-sonnet-5" in demo_kit["claude_magic"],
              f"демо получает магию с Sonnet, не Opus ({demo_kit['model']})")

        # claude_env как отдельная функция даёт 4 экспорта без утечки в шелл.
        env = claude_env(rec["token"], kit["model"], anthropic_base())
        check(env.count("export ") == 4,
              "claude_env — ровно 4 экспорта (base, token, model, small-fast)")

        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        print(f"\n{'=' * 60}\nИТОГ: {passed}/{total} проверок пройдено")
        if passed == total:
            print("✨ ПАК МЭДЖИК: 300 млн выдаётся, Claude Code заводится одной "
                  "командой, чужой конфиг цел.")
            return 0
        print("Есть красные проверки — смотрите выше.")
        return 1
    finally:
        os.environ.pop("WAVE_PUBLIC_GATEWAY", None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

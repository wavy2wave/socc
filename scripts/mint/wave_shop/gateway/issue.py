"""WAVE GATEWAY — выдать ключ доступа руками, без покупки в боте.

Зачем это. Оператор хочет дать другу 20-минутный доступ, не заводя оплату:
просто выпустить ему брендированный токен wave-… и прислать «как подключить».
Бот делает это в ответ на оплату; тут — тот же выпуск, но из терминала.

Ключ, который получает друг, привязан к обойме В ЦЕЛОМ (см. upstream_pool.py),
а не к конкретному сырому ключу: какой бы «патрон» ни обслужил запрос, у друга
списывается один и тот же счётчик, а срок/квота живут на его токене.

Примеры:
    python3 -m gateway.issue                     # друг, доступ 20 минут
    python3 -m gateway.issue --plan hour_1       # другой тариф
    python3 -m gateway.issue --user 777 --seats 2
    python3 -m gateway.issue --list-plans        # что вообще можно выдать
    python3 -m gateway.issue --json              # машиночитаемо (для скриптов)

Выпуск идёт через тот же QuotaStore, что и у бота, — ключ сразу виден шлюзу и
кабинету, никакой отдельной базы. stdlib-only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.quota import (  # noqa: E402
    PLANS,
    AlreadyIssued,
    QuotaStore,
    get_plan,
    plan_quota_caps,
)

# Тот же .env-loader, что и у прокси: тогда WAVE_PUBLIC_GATEWAY, WAVE_KEY_PREFIX
# и WAVE_DATA_DIR берутся из одного места, и выданный тут ключ подключается по
# ровно тому адресу, что увидит клиент. Уже заданное окружение — приоритетнее.
try:
    from config import BASE_DIR, _load_env_file  # noqa: E402

    _load_env_file(BASE_DIR / ".env")
except Exception:  # pragma: no cover — .env не обязателен
    pass

DATA_DIR = Path(os.environ.get("WAVE_DATA_DIR",
                               Path(__file__).resolve().parent.parent / "data"))
DEFAULT_PLAN = "friend_20m"


def _human_duration(seconds: int) -> str:
    """Срок «по-человечески»: минуты для короткого доступа, часы/дни — для долгого."""
    if seconds <= 0:
        return "без срока"
    if seconds < 3600:
        return f"{max(1, round(seconds / 60))} мин"
    if seconds < 86400:
        return f"~{round(seconds / 3600)} ч"
    return f"~{round(seconds / 86400)} дн"


def _plan_summary(plan_id: str, plan: dict) -> str:
    """Одна строка про тариф для --list-plans: срок и объём в понятных единицах."""
    kind = plan.get("kind")
    if kind == "hourly":
        seconds = int(plan.get("hours", 0)) * 3600 + int(plan.get("minutes", 0)) * 60
        caps = plan_quota_caps(plan)
        return f"{_human_duration(seconds)}, до {caps:,} CAPS/период".replace(",", " ")
    if kind in {"package", "subscription"}:
        caps = plan_quota_caps(plan)
        span = "12 мес" if kind == "package" else f"{plan.get('period_days', 30)} дн (продлевается)"
        return f"{caps:,} CAPS, {span}".replace(",", " ")
    if kind == "unlimited":
        cap = int(plan.get("daily_cap_caps", 0))
        return f"безлимит, суточный потолок {cap:,} CAPS".replace(",", " ")
    return kind or "?"


def list_plans() -> int:
    print("Доступные тарифы (--plan <id>):\n")
    width = max(len(pid) for pid in PLANS)
    for pid, plan in PLANS.items():
        star = "  ← по умолчанию" if pid == DEFAULT_PLAN else ""
        print(f"  {pid.ljust(width)}  {plan.get('title', pid)}")
        print(f"  {' ' * width}  {_plan_summary(pid, plan)}{star}")
    return 0


def _connect_block(token: str, gw: str, dash: str) -> list[str]:
    """Готовая инструкция «как подключить» — copy-paste для друга."""
    lines = [
        "Как подключить (OpenAI-совместимо — Cursor, Continue, curl, SDK):",
        f"  base_url : {gw}",
        f"  api_key  : {token}",
        "",
        "Проверка одной командой (curl):",
        f'  curl {gw}/chat/completions \\',
        f'    -H "Authorization: Bearer {token}" \\',
        '    -H "Content-Type: application/json" \\',
        '    -d \'{"model":"gpt","messages":[{"role":"user","content":"привет"}]}\'',
    ]
    if dash:
        # Ключ в hash (#…) — друг открывает ссылку и СРАЗУ видит отсчёт,
        # ничего не вставляя. hash на сервер не уходит, только клиенту.
        lines += ["", f"Кабинет (расход и время, живой отсчёт):",
                  f"  {dash.rstrip('/')}/#{token}"]
    return lines


def _default_dashboard(gw: str, explicit: str) -> str:
    """Адрес кабинета клиента. Если оператор не задал WAVE_PUBLIC_DASHBOARD,
    берём корень шлюза (там теперь живёт страница «ввёл ключ → отсчёт»):
    у почасового/пакетного клиента другого «окна» нет — он не в боте."""
    if explicit:
        return explicit
    root = gw.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root.rstrip("/")


def issue(plan_id: str, user_id: int, seats: int, as_json: bool) -> int:
    plan = get_plan(plan_id)
    if not plan:
        print(f"❌ Неизвестный тариф: {plan_id}. Список: --list-plans", file=sys.stderr)
        return 2

    store = QuotaStore(DATA_DIR)
    try:
        rec = store.issue_key(user_id=user_id, plan_id=plan_id,
                              order_id="manual", seats=seats)
    except AlreadyIssued:
        print(f"❌ Тариф {plan_id} — «один на пользователя», и он уже выдавался "
              f"пользователю {user_id}. Возьмите другой --user или другой --plan.",
              file=sys.stderr)
        return 3
    except ValueError as e:
        print(f"❌ Не удалось выдать ключ: {e}", file=sys.stderr)
        return 3

    token = rec["token"]
    gw = os.environ.get("WAVE_PUBLIC_GATEWAY", "http://127.0.0.1:8790/v1")
    dash = _default_dashboard(gw, os.environ.get("WAVE_PUBLIC_DASHBOARD", ""))
    now = int(time.time())
    seconds_left = max(0, int(rec.get("expires_at", 0)) - now) if rec.get("expires_at") else 0
    limit = int(rec.get("tokens_limit", 0))

    if as_json:
        print(json.dumps({
            "token": token,
            "plan_id": plan_id,
            "title": rec.get("title", plan_id),
            "kind": rec["kind"],
            "user_id": user_id,
            "seats": rec.get("seats", 1),
            "expires_at": rec.get("expires_at", 0),
            "seconds_left": seconds_left,
            "tokens_limit": limit,
            "base_url": gw,
            "dashboard": dash,
        }, ensure_ascii=False, indent=2))
        return 0

    print("🔑 Ключ доступа готов\n")
    print(f"  {token}\n")
    print(f"Тариф   : {rec.get('title', plan_id)}  ({plan_id})")
    if rec["kind"] == "unlimited":
        print(f"Объём   : безлимит · суточный потолок {int(rec.get('daily_cap_tokens', 0)):,} CAPS"
              .replace(",", " "))
    elif limit:
        print(f"Лимит   : {limit:,} CAPS".replace(",", " "))
    if seconds_left:
        print(f"Доступ  : {_human_duration(seconds_left)}")
    print()
    print("\n".join(_connect_block(token, gw, dash)))
    print(f"\nВыдан пользователю {user_id}"
          + (f", мест: {rec.get('seats', 1)}" if int(rec.get('seats', 1)) > 1 else "")
          + f". Хранится в {DATA_DIR / 'gw_keys.json'} — шлюз уже его знает.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="gateway.issue",
        description="Выдать ключ доступа wave-… руками, без покупки в боте "
                    "(например, 20-минутный доступ другу).")
    ap.add_argument("--plan", default=DEFAULT_PLAN,
                    help=f"идентификатор тарифа (по умолчанию {DEFAULT_PLAN}); "
                         f"список — --list-plans")
    ap.add_argument("--user", type=int, default=0,
                    help="Telegram user_id получателя (0 = ручная выдача без привязки)")
    ap.add_argument("--seats", type=int, default=1,
                    help="сколько параллельных мест разрешить на этот ключ (по умолчанию 1)")
    ap.add_argument("--list-plans", action="store_true", help="показать тарифы и выйти")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="вывести машиночитаемый JSON вместо инструкции")
    args = ap.parse_args(argv)

    if args.list_plans:
        return list_plans()
    return issue(args.plan, args.user, max(1, args.seats), args.as_json)


if __name__ == "__main__":
    raise SystemExit(main())

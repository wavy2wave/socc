"""WAVE GATEWAY — учёт квот и тарифов.

Зачем этот модуль существует: клиент НИКОГДА не получает ключ оператора.
Он получает свой токен шлюза. Шлюз считает расход и режет по тарифу.

Без этого слоя:
  • почасовой тариф невозможен (нечем мерить время);
  • «безлимит» = неограниченное обязательство за фиксированные деньги —
    один клиент с агентом в цикле выжирает весь баланс оператора за ночь;
  • нельзя понять, КТО сжёг деньги (у провайдера все запросы от одного ключа).

Модель тарифа (один товар — много смыслов, как на FunPay):
  hourly       — доступ на N часов, лимит токенов в час (страховка от цикла)
  package      — N токенов, не сгорают, без срока
  subscription — N токенов в месяц, автопродление, остаток сгорает
  unlimited    — «безлимит»: без счётчика токенов, НО с потолком в сутки.
                 Потолок — не обман клиента, а защита от бота-циклера.
                 Честная формулировка для витрины: «без ограничений по объёму
                 в рамках справедливого использования: N токенов/сутки».
  postpaid     — потокенная оплата: у ключа нет лимита CAPS, а есть кошелёк
                 в ₽ (deposit_rub). Каждый запрос списывает bill_rub(caps) по
                 тарифу оператора. Баланс кончился → доступ закрыт, пока не
                 пополнят. Автопополнение (autotopup) списывает с привязанной
                 карты, когда баланс падает ниже low_watermark_rub — так «трафик
                 кончился → автосписание» происходит БЕЗ кредита: деньги всегда
                 внесены заранее, оператор не даёт в долг.

Канон MINT: stdlib-only, атомарная запись, fail-soft.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Постоплата считает ₽ за реальный расход по той же экономике, что и витрина.
# pricing импортирует только stdlib — цикла нет (см. gateway/__init__ → quota).
from gateway.pricing import bill_rub

_LOCK = threading.RLock()


def _key_prefix() -> str:
    """Префикс брендированного ключа (env WAVE_KEY_PREFIX, дефолт 'wave-').

    Только ASCII и [A-Za-z0-9_-]: токен уезжает в HTTP-заголовок
    Authorization: Bearer …, а он latin-1 — кириллица/пробел его сломают.
    Мусор/пусто → безопасный дефолт 'wave-'. Смена префикса НЕ ломает уже
    выданные ключи: они ищутся по точному совпадению, а не по префиксу.
    """
    raw = os.environ.get("WAVE_KEY_PREFIX", "wave-")
    cleaned = "".join(ch for ch in raw if ch.isascii() and (ch.isalnum() or ch in "-_"))
    # Должна уцелеть хоть одна буква/цифра, иначе '-'/'_' дали бы ключ вида
    # «-xxxx» (кириллица не проходит в latin-1 заголовок и вырезается целиком).
    if not any(ch.isalnum() for ch in cleaned):
        return "wave-"
    return cleaned


KEY_PREFIX = _key_prefix()

# ═══ ТАРИФНАЯ СЕТКА ═══
#
# Все лимиты — в CAPS (взвешенные единицы, см. gateway/pricing.py):
#   1 CAP = 1 входной токен Opus 5 | выход = 5 CAPS | чтение кэша = 0.1 CAP
#
# ВАЖНО — почему потолки именно такие. Раньше здесь стояло tokens_per_hour:
# 2_000_000 при цене часа 99 ₽. Это давало клиенту право сжечь на 950 ₽
# себестоимости, то есть −869 ₽ убытка на каждом чеке. Теперь каждый потолок
# выведен из цены формулой safe_hourly_cap() при марже 50% и сверен тестом
# tests/pricing_v1.py — тариф не может стать убыточным незаметно.
#
# Цены (для справки, живут в data/catalog.json) считаны от прайса Anthropic
# при курсе 90 ₽/$. Если агрегатор продаёт дешевле прайса — задать реальную
# закупку через WAVE_COST_* в .env, и вся экономика пересчитается сама.
PLANS: dict[str, dict] = {
    # --- Демо: вход в воронку. Sonnet, дёшево, один на аккаунт ---
    "demo":     {"kind": "hourly", "hours": 24, "caps_per_hour": 6_250,
                 "title": "Демо 24 часа", "model_key": "sonnet", "once_per_user": True},
    # --- Для друзей: короткий доступ «на попробовать». Меряется минутами, а не
    # часами (hourly понимает поле minutes). caps_per_hour тот же, что у 1 часа,
    # то есть за 20 минут потолок ~110k CAPS — человеку хватит с запасом, а
    # агент-циклер упрётся раньше, чем сожжёт лишнее. ---
    "friend_20m": {"kind": "hourly", "hours": 0, "minutes": 20, "caps_per_hour": 330_000,
                   "title": "Доступ 20 минут"},
    # --- Почасовые: «добить задачу сегодня» ---
    "hour_1":   {"kind": "hourly", "hours": 1,  "caps_per_hour": 330_000, "title": "1 час"},
    "hour_6":   {"kind": "hourly", "hours": 6,  "caps_per_hour": 168_000, "title": "Вечер (6 часов)"},
    "hour_24":  {"kind": "hourly", "hours": 24, "caps_per_hour": 105_000, "title": "Сутки"},
    # --- Пакеты: срок 12 мес (НЕ бессрочно: поставку могут отрезать) ---
    "pack_3m":  {"kind": "package", "caps": 3_000_000,  "ttl_days": 365, "title": "3 млн CAPS"},
    "pack_10m": {"kind": "package", "caps": 10_000_000, "ttl_days": 365, "title": "10 млн CAPS"},
    # --- «Пак мэджик»: крупные пакеты под сценарий «дал другу N млн токенов».
    # Тот же вид package (не сгорают год), просто большой объём: клиент один раз
    # запускает магию-команду и работает, пока не выберет пакет. ---
    "pack_100m": {"kind": "package", "caps": 100_000_000, "ttl_days": 365, "title": "100 млн CAPS"},
    "pack_300m": {"kind": "package", "caps": 300_000_000, "ttl_days": 365, "title": "300 млн CAPS"},
    # --- Подписки: месяц, автопродление ---
    "sub_5m":   {"kind": "subscription", "caps": 5_000_000,  "period_days": 30, "title": "5 млн CAPS/мес"},
    "sub_15m":  {"kind": "subscription", "caps": 15_000_000, "period_days": 30, "title": "15 млн CAPS/мес"},
    # --- Пик линейки: безлимит с честным суточным потолком ---
    "unlim":    {"kind": "unlimited", "period_days": 30, "daily_cap_caps": 700_000,
                 "rpm": 60, "title": "Безлимит"},
    # --- Потокенная оплата: кошелёк в ₽, списание за реальный расход ---
    # Не «продаётся» фиксированной ценой — это РЕЖИМ ключа. Клиент вносит любую
    # сумму, каждый запрос точечно списывает по тарифу; когда баланс падает ниже
    # порога — автопополнение с карты. low_watermark_rub/topup_amount_rub здесь
    # дефолты, оператор/клиент переопределяют их при выдаче.
    "postpaid": {"kind": "postpaid", "title": "Потокенная оплата",
                 "low_watermark_rub": 100, "topup_amount_rub": 500},
}

# Обратная совместимость: старые ключи полей и старые plan_id, чтобы уже
# выданные ключи и сохранённые заказы не сломались после смены сетки.
_LEGACY_PLAN_ALIASES = {
    "hour_3": "hour_6", "hour_12": "hour_24",
    "pack_5m": "pack_3m", "pack_20m": "pack_10m", "pack_50m": "pack_10m",
    "sub_10m": "sub_5m", "sub_30m": "sub_15m",
}


def get_plan(plan_id: str) -> dict | None:
    """Найти тариф, понимая старые идентификаторы."""
    plan = PLANS.get(plan_id)
    if plan is not None:
        return plan
    alias = _LEGACY_PLAN_ALIASES.get(plan_id)
    return PLANS.get(alias) if alias else None


def canon_plan_id(plan_id: str) -> str:
    """Привести старый идентификатор к текущему. Нужно для сравнения выданных ключей."""
    return plan_id if plan_id in PLANS else _LEGACY_PLAN_ALIASES.get(plan_id, plan_id)


class AlreadyIssued(ValueError):
    """Тариф с флагом once_per_user уже выдавался этому пользователю.

    Отдельный класс, а не общий ValueError: бесплатное демо, выданное дважды, —
    это не сбой выдачи, а нормальный отказ, и клиенту нужен другой текст.
    """


def _hourly_seconds(plan: dict) -> int:
    """Длительность почасового тарифа в секундах: часы И/ИЛИ минуты.

    Минуты добавлены ради короткого доступа «для друзей» (тариф на 20 минут).
    Старые тарифы задают только hours — для них minutes=0, поведение прежнее.
    Если срок не задан вовсе — час (безопасный дефолт, как было исторически).
    """
    seconds = int(plan.get("hours", 0)) * 3600 + int(plan.get("minutes", 0)) * 60
    return seconds if seconds > 0 else 3600


def plan_quota_caps(plan: dict) -> int:
    """Сколько CAPS даёт тариф целиком (0 = безлимит)."""
    kind = plan.get("kind")
    if kind == "hourly":
        per_hour = plan.get("caps_per_hour", plan.get("tokens_per_hour", 0))
        # Срок теперь может задаваться часами И/ИЛИ минутами (короткий доступ
        # для друзей). Квота пропорциональна времени. Старые тарифы задают
        # только hours — для них формула даёт ровно per_hour*hours, как раньше.
        seconds = _hourly_seconds(plan)
        return round(int(per_hour) * seconds / 3600)
    if kind in {"package", "subscription"}:
        return int(plan.get("caps", plan.get("tokens", 0)))
    return 0


# ═══ ОГРАНИЧЕНИЕ МОДЕЛИ НА ТАРИФ ═══
#
# Дыра, которую это закрывает: демо продано как Sonnet и посчитано по цене
# Sonnet (40 ₽ полного расхода), но шлюз модель не проверял. Клиент менял
# "model" в запросе на Opus и жёг закупку в 5 раз дороже обещанной —
# бесплатно. На потоке демо это прямой убыток без верхней границы.
#
# Порядок = цена. Ключ вправе звать свой уровень и всё, что ДЕШЕВЛЕ, но не
# дороже: так ограничение не мешает клиенту экономить и не даёт превысить
# оплаченный уровень.
_TIER_ORDER = ["haiku", "sonnet", "opus"]

# Подстроки в имени модели → уровень. Провайдеры пишут имена по-разному
# ("claude-opus-5", "anthropic/claude-opus-4.6"), поэтому ищем по вхождению.
# Семейство DeepSeek (v4-flash/-pro, deepseek-ai/…) — то, что шлюз перепродаёт
# сейчас. По закупке (agentrouter/DeepInfra) оно дешевле даже haiku, поэтому
# ставим ему НИЗШИЙ тир: модель пускается на ЛЮБОМ плане, включая демо-воронку,
# и никогда не превышает потолок стоимости — ошибиться в сторону убытка нечем.
_MODEL_TIERS = [("opus", "opus"), ("sonnet", "sonnet"), ("haiku", "haiku"),
                ("deepseek", "haiku")]


def model_tier(model: str) -> str | None:
    """Определить уровень модели по имени. None = имя незнакомо."""
    low = (model or "").lower()
    for needle, tier in _MODEL_TIERS:
        if needle in low:
            return tier
    return None


def model_allowed(model: str, max_tier: str) -> bool:
    """Можно ли звать эту модель на ключе с потолком max_tier.

    Незнакомое имя модели ЗАПРЕЩАЕТСЯ, когда потолок задан: неизвестное имя
    может оказаться дороже потолка, а ошибаться в сторону убытка нельзя.
    """
    if not max_tier or max_tier not in _TIER_ORDER:
        return True                       # потолок не задан — тариф без ограничения
    tier = model_tier(model)
    if tier is None:
        return False
    return _TIER_ORDER.index(tier) <= _TIER_ORDER.index(max_tier)


def _now() -> int:
    return int(time.time())


def _read(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


@dataclass
class Verdict:
    """Решение шлюза: пускать запрос наверх или нет."""
    allow: bool
    reason: str = ""          # машинный код: ok | no_key | expired | quota | daily_cap | rate | disabled
    message: str = ""         # человеческий текст (уходит клиенту)
    remaining: int = 0        # остаток токенов (0 для unlimited)


class QuotaStore:
    """Токены клиентов, их тарифы и расход. Ключ оператора здесь не хранится."""

    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir)
        self.keys_path = self.dir / "gw_keys.json"       # токен клиента -> тариф и остаток
        self.usage_path = self.dir / "gw_usage.json"     # лог расхода (для дашборда и разбора)

    # ---------- Выдача ключа ----------
    def issue_key(self, user_id: int, plan_id: str, order_id: str = "",
                  seats: int = 1, price_rub: int = 0) -> dict:
        """Выдать клиенту токен шлюза под тариф. Возвращает запись ключа.

        seats — сколько параллельных «мест» разрешено на этот ключ (оператор может
        продавать доступ на 2-3 человек ОДНОЙ записью, но каждый расход считается
        и общий лимит не превышается).

        price_rub — сколько клиент ЗАПЛАТИЛ за этот ключ (₽). Хранится, чтобы в
        кабинете показать «сколько РЕАЛЬНО потрачено» по ЕГО тарифу:
        spent_rub = price_rub × tokens_used / tokens_limit. Это ЕГО деньги —
        закупка оператора и маржа сюда не попадают (они живут в control_room).
        Взломать нельзя: и цена, и расход считаются на стороне шлюза; клиент
        число только показывает. Ручная выдача другу (без оплаты) → price_rub=0,
        и в кабинете честно стоит 0 ₽ потрачено.
        """
        plan = get_plan(plan_id)
        if not plan:
            raise ValueError(f"неизвестный тариф: {plan_id}")
        with _LOCK:
            keys = _read(self.keys_path, {})
            # Один бесплатный вход на аккаунт. Проверка ЗДЕСЬ, под общим замком,
            # а не в UI: иначе два быстрых нажатия подряд дадут два демо-ключа,
            # и любой новый путь выдачи (админка, восстановление) обойдёт защиту.
            if plan.get("once_per_user"):
                canon = canon_plan_id(plan_id)
                for rec_old in keys.values():
                    if (rec_old.get("user_id") == user_id
                            and canon_plan_id(str(rec_old.get("plan_id", ""))) == canon):
                        raise AlreadyIssued(
                            f"тариф {plan_id} уже выдавался пользователю {user_id}")
            token = KEY_PREFIX + secrets.token_urlsafe(24)
            now = _now()
            rec: dict[str, Any] = {
                "token": token,
                "user_id": user_id,
                "plan_id": plan_id,
                "kind": plan["kind"],
                "title": plan.get("title", plan_id),
                "order_id": order_id,
                "seats": max(1, int(seats)),
                "price_rub": max(0, int(price_rub)),
                "created_at": now,
                "enabled": True,
                "tokens_used": 0,
                "requests": 0,
            }
            if plan["kind"] == "hourly":
                rec["expires_at"] = now + _hourly_seconds(plan)
                rec["tokens_limit"] = plan_quota_caps(plan)
            elif plan["kind"] == "package":
                # Срок жизни: НЕ бессрочно. Поставку наверху могут отрезать,
                # а бессрочное обязательство против отзываемого доступа — долг.
                ttl = int(plan.get("ttl_days", 365))
                rec["expires_at"] = now + ttl * 86400
                rec["tokens_limit"] = plan_quota_caps(plan)
            elif plan["kind"] == "subscription":
                rec["expires_at"] = now + int(plan["period_days"]) * 86400
                rec["tokens_limit"] = plan_quota_caps(plan)
            elif plan["kind"] == "postpaid":
                # Кошелёк, а не срок: доступ живёт, пока на балансе есть ₽.
                # price_rub при выдаче = первый внесённый депозит.
                rec["expires_at"] = 0                       # 0 = не истекает по времени
                rec["tokens_limit"] = 0                     # нет потолка объёма
                rec["deposit_rub"] = round(max(0.0, float(price_rub)), 6)  # живой баланс
                rec["spent_rub_total"] = 0.0                # точный расход в ₽ (для кабинета)
                rec["autotopup"] = False                    # включается ТОЛЬКО явно и при наличии карты
                rec["low_watermark_rub"] = int(plan.get("low_watermark_rub", 100))
                rec["topup_amount_rub"] = int(plan.get("topup_amount_rub", 500))
                rec["topup_needed"] = False
                rec["topup_failed_attempts"] = 0
                # Счётчик успешных пополнений: движок постоплаты строит из него
                # idem-ключ списания (стабилен между повторами, растёт только при
                # УДАЧНОМ пополнении). Иначе повтор после сбоя мог бы списать дважды.
                rec["topup_seq"] = 0
            else:  # unlimited
                rec["expires_at"] = now + int(plan["period_days"]) * 86400
                rec["tokens_limit"] = 0                    # без счётчика объёма
                rec["daily_cap_tokens"] = int(
                    plan.get("daily_cap_caps", plan.get("daily_cap_tokens", 0)))
                rec["rpm"] = int(plan.get("rpm", 60))
            if plan.get("model_key"):
                rec["model_key"] = plan["model_key"]
            keys[token] = rec
            _write(self.keys_path, keys)
            return rec

    def get_key(self, token: str) -> dict | None:
        return _read(self.keys_path, {}).get(token)

    def keys_of_user(self, user_id: int) -> list[dict]:
        return [k for k in _read(self.keys_path, {}).values() if k.get("user_id") == user_id]

    def all_keys(self) -> list[dict]:
        """Все выданные ключи — для операторской панели. Только чтение."""
        return list(_read(self.keys_path, {}).values())

    def set_enabled(self, token: str, on: bool) -> dict | None:
        with _LOCK:
            keys = _read(self.keys_path, {})
            rec = keys.get(token)
            if not rec:
                return None
            rec["enabled"] = bool(on)
            keys[token] = rec
            _write(self.keys_path, keys)
            return rec

    def extend(self, token: str, plan_id: str | None = None,
               price_rub: int = 0) -> dict | None:
        """Продление подписки/безлимита/пакета: срок от текущего конца, квота обновляется.

        price_rub — сколько клиент заплатил за это продление (₽). Учитываем его
        параллельно объёму, чтобы кабинет считал «потрачено ₽» честно после
        любого продления:
          • пакет     — докупка складывает и объём, и уплаченную сумму;
          • подписка  — месяц обнуляет и расход, и цену (новый оплаченный период);
          • безлимит  — новый период по новой цене.
        """
        with _LOCK:
            keys = _read(self.keys_path, {})
            rec = keys.get(token)
            if not rec:
                return None
            plan = get_plan(plan_id or rec["plan_id"])
            if not plan:
                return None
            now = _now()
            base = max(int(rec.get("expires_at", 0)), now)
            add_price = max(0, int(price_rub))
            if plan["kind"] in {"subscription", "unlimited"}:
                rec["expires_at"] = base + int(plan["period_days"]) * 86400
                if plan["kind"] == "subscription":
                    rec["tokens_limit"] = plan_quota_caps(plan)
                    rec["tokens_used"] = 0       # месячная квота обнуляется
                # Новый оплаченный период — расход считается от его цены.
                rec["price_rub"] = add_price
            elif plan["kind"] == "package":
                # Докупка: объём складывается, срок жизни продлевается от текущего.
                rec["tokens_limit"] = int(rec.get("tokens_limit", 0)) + plan_quota_caps(plan)
                rec["expires_at"] = base + int(plan.get("ttl_days", 365)) * 86400
                # Уплаченная сумма тоже складывается — иначе ₽/CAPS «поедет».
                rec["price_rub"] = int(rec.get("price_rub", 0)) + add_price
            rec["enabled"] = True
            keys[token] = rec
            _write(self.keys_path, keys)
            return rec

    # ---------- Потокенная оплата (кошелёк в ₽) ----------
    def topup(self, token: str, amount_rub: float, *,
              clear_flag: bool = True) -> dict | None:
        """Зачислить amount_rub ₽ в кошелёк потокенного ключа.

        Вызывается ПОСЛЕ подтверждённого платежа (ручного пополнения или
        автосписания движком). price_rub копит суммарно внесённое, чтобы
        сходился баланс: внесено = остаток + израсходовано. clear_flag снимает
        пометку «нужно пополнить» — деньги пришли, тревожить движок больше не надо.
        """
        add = round(max(0.0, float(amount_rub)), 6)
        with _LOCK:
            keys = _read(self.keys_path, {})
            rec = keys.get(token)
            if not rec or rec.get("kind") != "postpaid":
                return None
            rec["deposit_rub"] = round(float(rec.get("deposit_rub", 0.0)) + add, 6)
            rec["price_rub"] = int(rec.get("price_rub", 0)) + int(round(add))
            rec["topup_failed_attempts"] = 0   # удачное пополнение снимает счётчик провалов
            # Успешное пополнение = новая «эпоха» кошелька: сдвигаем seq, чтобы
            # СЛЕДУЮЩЕЕ автопополнение получило другой idem-ключ, а повтор ЭТОГО
            # (до сдвига) дедуплицировался у провайдера. Растёт только тут.
            rec["topup_seq"] = int(rec.get("topup_seq", 0)) + 1
            if clear_flag:
                rec["topup_needed"] = False
            rec["enabled"] = True
            keys[token] = rec
            _write(self.keys_path, keys)
            return rec

    def set_autotopup(self, token: str, on: bool, *,
                      low_watermark_rub: int | None = None,
                      topup_amount_rub: int | None = None) -> dict | None:
        """Включить/выключить автопополнение и (опц.) настроить пороги.

        Автосписание можно включать ТОЛЬКО когда у клиента привязана карта —
        это проверяет ВЫЗЫВАЮЩИЙ (бот перед включением смотрит payment_method_id
        в подписке). Здесь только флаг: quota карту не хранит и денег не двигает,
        реальное списание делает движок постоплаты (topup.py).
        """
        with _LOCK:
            keys = _read(self.keys_path, {})
            rec = keys.get(token)
            if not rec or rec.get("kind") != "postpaid":
                return None
            rec["autotopup"] = bool(on)
            if low_watermark_rub is not None:
                rec["low_watermark_rub"] = max(0, int(low_watermark_rub))
            if topup_amount_rub is not None:
                rec["topup_amount_rub"] = max(1, int(topup_amount_rub))
            if not on:
                rec["topup_needed"] = False    # выключили — движок не трогаем
            keys[token] = rec
            _write(self.keys_path, keys)
            return rec

    def arm_postpaid(self, token: str, *, deposit_rub: float = 0.0,
                     autotopup: bool = False,
                     low_watermark_rub: int | None = None,
                     topup_amount_rub: int | None = None) -> dict | None:
        """Перевести СУЩЕСТВУЮЩИЙ ключ в режим постоплаты — тот же токен, клиенту
        не нужно ничего перевставлять в Cursor.

        Честно: остаточные CAPS пакета/подписки в ₽ НЕ конвертируем (клиент за
        них заплатил и мог израсходовать; молча превращать их в деньги нельзя).
        Просто снимаем потолок объёма/срок и включаем ₽-кошелёк. Перенос остатка,
        если понадобится, — отдельное явное решение, не побочный эффект.
        """
        plan = get_plan("postpaid") or {}
        with _LOCK:
            keys = _read(self.keys_path, {})
            rec = keys.get(token)
            if not rec:
                return None
            rec["kind"] = "postpaid"
            rec["plan_id"] = "postpaid"
            rec["title"] = plan.get("title", "Потокенная оплата")
            rec["expires_at"] = 0
            rec["tokens_limit"] = 0
            rec["deposit_rub"] = round(max(0.0, float(deposit_rub)), 6)
            rec.setdefault("spent_rub_total", 0.0)
            rec["autotopup"] = bool(autotopup)
            rec["low_watermark_rub"] = int(
                low_watermark_rub if low_watermark_rub is not None
                else plan.get("low_watermark_rub", 100))
            rec["topup_amount_rub"] = int(
                topup_amount_rub if topup_amount_rub is not None
                else plan.get("topup_amount_rub", 500))
            rec["topup_needed"] = False
            rec.setdefault("topup_failed_attempts", 0)
            rec.setdefault("topup_seq", 0)
            rec["enabled"] = True
            keys[token] = rec
            _write(self.keys_path, keys)
            return rec

    def keys_needing_topup(self) -> list[dict]:
        """Потокенные ключи, которым движок должен пополнить баланс с карты."""
        return [k for k in _read(self.keys_path, {}).values()
                if k.get("kind") == "postpaid" and k.get("autotopup")
                and k.get("topup_needed")]

    def note_topup_failure(self, token: str) -> int:
        """Отметить неудачную попытку автопополнения. Возвращает счётчик провалов.

        Движок постоплаты по 3 провалам выключает автопополнение (как продление
        подписки), чтобы не долбить отклоняющую карту каждый час. Удачный topup()
        обнуляет счётчик.
        """
        with _LOCK:
            keys = _read(self.keys_path, {})
            rec = keys.get(token)
            if not rec or rec.get("kind") != "postpaid":
                return 0
            n = int(rec.get("topup_failed_attempts", 0)) + 1
            rec["topup_failed_attempts"] = n
            keys[token] = rec
            _write(self.keys_path, keys)
            return n

    # ---------- Проверка перед запросом ----------
    def check(self, token: str, now: int | None = None) -> Verdict:
        now = now or _now()
        rec = self.get_key(token)
        if not rec:
            return Verdict(False, "no_key", "Ключ не найден. Проверьте токен.")
        if not rec.get("enabled", True):
            return Verdict(False, "disabled", "Доступ приостановлен. Напишите в поддержку.")

        expires = int(rec.get("expires_at", 0))
        if expires and now >= expires:
            return Verdict(False, "expired", "Срок тарифа истёк. Продлите доступ в боте.")

        if rec["kind"] == "unlimited":
            spent_today = self._spent_since(token, now - 86400)
            cap = int(rec.get("daily_cap_tokens", 0))
            if cap and spent_today >= cap:
                return Verdict(False, "daily_cap",
                               "Достигнут суточный лимит справедливого использования. "
                               "Доступ откроется автоматически через несколько часов.")
            return Verdict(True, "ok", remaining=0)

        if rec["kind"] == "postpaid":
            # Гейт по деньгам, не по токенам: пускаем, пока на кошельке есть ₽.
            # Возможен добор одного запроса «в минус» на доли (стоимость запроса
            # неизвестна заранее) — от этого страхует автопополнение по порогу,
            # которое срабатывает задолго до нуля.
            balance = float(rec.get("deposit_rub", 0.0))
            if balance <= 0:
                return Verdict(False, "quota",
                               "Баланс потокенного тарифа исчерпан. Пополните кошелёк "
                               "или включите автопополнение в боте.")
            return Verdict(True, "ok", remaining=0)

        limit = int(rec.get("tokens_limit", 0))
        used = int(rec.get("tokens_used", 0))
        if limit and used >= limit:
            return Verdict(False, "quota", "Токены закончились. Пополните тариф в боте.")
        return Verdict(True, "ok", remaining=max(0, limit - used))

    def _spent_since(self, token: str, since_ts: int) -> int:
        return sum(int(e.get("tokens", 0)) for e in _read(self.usage_path, [])
                   if e.get("token") == token and int(e.get("ts", 0)) >= since_ts)

    # ---------- Списание после запроса ----------
    def consume(self, token: str, tokens: int, model: str = "") -> dict | None:
        """Списать израсходованное. Вызывается ПОСЛЕ ответа провайдера."""
        tokens = max(0, int(tokens))
        with _LOCK:
            keys = _read(self.keys_path, {})
            rec = keys.get(token)
            if not rec:
                return None
            rec["tokens_used"] = int(rec.get("tokens_used", 0)) + tokens
            rec["requests"] = int(rec.get("requests", 0)) + 1
            rec["last_used_at"] = _now()
            if rec.get("kind") == "postpaid":
                # Списываем ₽ за реальный расход по тарифу оператора. Цена CAP
                # зависит от УРОВНЯ вызванной модели (opus дороже haiku в разы):
                # берём уровень реально вызванной модели, иначе потолок ключа,
                # иначе opus (дороже — ошибаться в сторону убытка нельзя).
                mk = model_tier(model) or rec.get("model_key") or "opus"
                cost = bill_rub(tokens, mk)
                rec["deposit_rub"] = round(float(rec.get("deposit_rub", 0.0)) - cost, 6)
                rec["spent_rub_total"] = round(float(rec.get("spent_rub_total", 0.0)) + cost, 6)
                low = float(rec.get("low_watermark_rub", 0))
                if rec.get("autotopup") and rec["deposit_rub"] <= low:
                    rec["topup_needed"] = True   # движок автопополнения спишет с карты
            keys[token] = rec
            _write(self.keys_path, keys)

            usage = _read(self.usage_path, [])
            usage.append({"ts": _now(), "token": token, "user_id": rec.get("user_id"),
                          "tokens": tokens, "model": model})
            # Держим лог ограниченным, чтобы файл не рос бесконечно.
            if len(usage) > 50_000:
                usage = usage[-40_000:]
            _write(self.usage_path, usage)
            return rec

    # ---------- Данные для дашборда ----------
    def status(self, token: str, now: int | None = None) -> dict | None:
        now = now or _now()
        rec = self.get_key(token)
        if not rec:
            return None
        out = {
            "title": rec.get("title", ""),
            "kind": rec["kind"],
            "enabled": rec.get("enabled", True),
            "requests": rec.get("requests", 0),
            "tokens_used": rec.get("tokens_used", 0),
            "expires_at": rec.get("expires_at", 0),
            "seats": rec.get("seats", 1),
        }
        # «Сколько РЕАЛЬНО потрачено» по ЦЕНЕ КЛИЕНТА, а не по закупке оператора.
        # Это его собственные деньги: заплатил price_rub за весь объём tokens_limit,
        # израсходовал tokens_used → потратил пропорционально. Обе величины
        # посчитаны шлюзом (цена зафиксирована при выдаче, расход — из реальных
        # ответов провайдера), поэтому клиент число только ПОКАЗЫВАЕТ, подделать
        # не может. Закупка/маржа оператора сюда НЕ попадают.
        price = int(rec.get("price_rub", 0))
        out["price_rub"] = price
        if rec["kind"] == "postpaid":
            # Кошелёк в ₽: показываем остаток и суммарный расход по цене клиента.
            # Инвариант сверки: внесено (price_rub) = остаток + израсходовано.
            out["postpaid"] = True
            out["balance_rub"] = round(float(rec.get("deposit_rub", 0.0)), 2)
            out["spent_rub"] = round(float(rec.get("spent_rub_total", 0.0)), 2)
            out["remaining_rub"] = out["balance_rub"]
            out["autotopup"] = bool(rec.get("autotopup"))
            out["low_watermark_rub"] = int(rec.get("low_watermark_rub", 0))
            out["topup_amount_rub"] = int(rec.get("topup_amount_rub", 0))
            out["topup_needed"] = bool(rec.get("topup_needed"))
        elif rec["kind"] == "unlimited":
            out["unlimited"] = True
            out["daily_cap"] = rec.get("daily_cap_tokens", 0)
            out["spent_today"] = self._spent_since(token, now - 86400)
            # У безлимита нет объёмного знаменателя — расход в ₽ не дробим,
            # показываем уплаченную цену периода как есть.
            out["spent_rub"] = float(price)
        else:
            limit = int(rec.get("tokens_limit", 0))
            used = int(rec.get("tokens_used", 0))
            out["tokens_limit"] = limit
            out["tokens_left"] = max(0, limit - used)
            # Доля израсходованного × цена. Без объёма (limit=0) делить нельзя —
            # тогда ничего не потрачено в деньгах (0 ₽), а не «всё».
            spent = (price * min(used, limit) / limit) if (price and limit) else 0.0
            out["spent_rub"] = round(spent, 2)
            out["remaining_rub"] = round(max(0.0, price - spent), 2)
        if rec.get("expires_at"):
            out["seconds_left"] = max(0, int(rec["expires_at"]) - now)
        return out

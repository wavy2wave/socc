"""WAVE SHOP — конфигурация. stdlib-only .env loader (без python-dotenv).

Канон MINT: ноль внешних зависимостей. Читаем .env руками, отдаём frozen Settings.
Секреты не логируем; при отсутствии токена бот честно скажет 'не сконфигурирован'.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# Каталог данных можно увести в сторону (тесты, отдельные инстансы) через WAVE_DATA_DIR.
DATA_DIR = Path(os.environ.get("WAVE_DATA_DIR") or (BASE_DIR / "data"))
RUNTIME_DIR = Path(os.environ.get("WAVE_RUNTIME_DIR") or (BASE_DIR / "runtime"))


def _load_env_file(path: Path) -> None:
    """Залить KEY=VALUE из .env в os.environ (не перетирая уже заданное окружение)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _get_int_set(name: str) -> set[int]:
    out: set[int] = set()
    for part in _get(name).replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


@dataclass(frozen=True)
class Settings:
    # --- Telegram ---
    bot_token: str
    admin_ids: set[int]
    shop_name: str
    support_contact: str
    # --- Оплата: какие провайдеры включены и их ключи ---
    payment_order: list[str]           # sbp, card, sberpay, yookassa, stars, crypto, manual
    yookassa_shop_id: str
    yookassa_secret_key: str
    crypto_pay_token: str              # CryptoBot @CryptoBot API token
    crypto_asset: str                  # USDT / TON / ...
    crypto_rub_per_unit: float         # курс ₽ → asset (для пересчёта цены)
    manual_pay_details: str            # текст реквизитов для ручной оплаты
    # --- Экономика ---
    currency: str                      # витринная валюта РУБ-цен: "RUB"
    ref_reward_percent: int            # % от покупки рефералу
    # --- Подписки (автопродление) ---
    autorenew_enabled: bool            # включено ли автосписание вообще
    renew_notice_days: int             # за сколько дней предупредить о списании
    # --- Постоплата (потокенный кошелёк) ---
    # Дефолт держит поле обратносовместимым: код и тесты, собирающие Settings без
    # него, не ломаются (как data_dir/runtime_dir ниже). Прод всегда передаёт
    # значение из load_settings() — дефолт срабатывает лишь при прямой сборке.
    postpaid_seed_rub: int = 500       # стартовый депозит при переводе на постоплату
    # --- Пути ---
    data_dir: Path = field(default=DATA_DIR)
    runtime_dir: Path = field(default=RUNTIME_DIR)

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and ":" in self.bot_token)


def load_settings() -> Settings:
    _load_env_file(BASE_DIR / ".env")
    data_dir = Path(_get("WAVE_DATA_DIR") or DATA_DIR)
    runtime_dir = Path(_get("WAVE_RUNTIME_DIR") or RUNTIME_DIR)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Порядок = порядок кнопок в боте. СБП первым: в РФ это самый быстрый путь.
    order_raw = _get("WAVE_PAYMENT_ORDER", "sbp,card,stars,crypto,manual")
    payment_order = [p.strip() for p in order_raw.split(",") if p.strip()]

    reward = _get("WAVE_REF_REWARD_PERCENT", "10")
    reward_pct = int(reward) if reward.isdigit() else 10

    notice = _get("WAVE_RENEW_NOTICE_DAYS", "3")
    notice_days = int(notice) if notice.isdigit() else 3

    # Стартовый депозит при переводе клиента на потокенную оплату. Постоплата с
    # нулём на счету сразу упирается в гейт «баланс исчерпан» и не может ничего
    # списать (автопополнение включается ПОСЛЕ первого расхода) — поэтому кошелёк
    # надо засеять. Деньги всегда вносятся вперёд: долга нет, RUBICON цел.
    seed = _get("WAVE_POSTPAID_SEED_RUB", "500")
    seed_rub = int(seed) if seed.isdigit() and int(seed) > 0 else 500

    rate_raw = _get("WAVE_CRYPTO_RUB_PER_UNIT", "100")
    try:
        rate = float(rate_raw)
    except ValueError:
        rate = 100.0

    return Settings(
        bot_token=_get("WAVE_BOT_TOKEN") or _get("TELEGRAM_BOT_TOKEN"),
        admin_ids=_get_int_set("WAVE_ADMIN_IDS"),
        shop_name=_get("WAVE_SHOP_NAME", "WAVE SHOP"),
        support_contact=_get("WAVE_SUPPORT_CONTACT", "@wave_support"),
        payment_order=payment_order,
        yookassa_shop_id=_get("WAVE_YOOKASSA_SHOP_ID"),
        yookassa_secret_key=_get("WAVE_YOOKASSA_SECRET_KEY"),
        crypto_pay_token=_get("WAVE_CRYPTO_PAY_TOKEN"),
        crypto_asset=_get("WAVE_CRYPTO_ASSET", "USDT"),
        crypto_rub_per_unit=rate,
        manual_pay_details=_get("WAVE_MANUAL_PAY_DETAILS"),
        currency=_get("WAVE_CURRENCY", "RUB"),
        ref_reward_percent=reward_pct,
        autorenew_enabled=_get("WAVE_AUTORENEW", "1") not in {"0", "false", "False"},
        renew_notice_days=notice_days,
        postpaid_seed_rub=seed_rub,
        # Пути посчитаны выше — после загрузки .env, чтобы он мог их переопределить.
        data_dir=data_dir,
        runtime_dir=runtime_dir,
    )

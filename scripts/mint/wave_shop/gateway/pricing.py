"""WAVE — экономика: себестоимость, CAPS, рекомендованные цены.

Зачем этот модуль: без него прайс — это гадание. Разведка показала, что
текущая сетка убыточна (час за 99 ₽ при потолке 2 млн токенов = до −1764 ₽
на чек). Здесь считается настоящая себестоимость и цена, которая не убивает.

═══ ГЛАВНОЕ: почему нельзя считать «токены» одной цифрой ═══

У Anthropic выходной токен стоит В 5 РАЗ дороже входного, а чтение из кэша —
в 10 раз дешевле входного:

    вход        $5.00 / 1M   →  вес 1.0
    выход      $25.00 / 1M   →  вес 5.0
    кэш-чтение  $0.50 / 1M   →  вес 0.1

Продавать «1 миллион токенов», не различая их — это продавать бензин, не
различая литр и цистерну. Один клиент нагенерит длинных ответов и заплатит
столько же, сколько другой, читающий из кэша, — а обойдётся вам в 50 раз дороже.

Поэтому вводим единицу CAPS (по образцу BotHub — рынок к ней уже привык):

    1 CAP = 1 входной токен Opus 5

Клиент видит в кабинете «осталось X CAPS» — честный остаток. Оператор не
теряет на генерации.

═══ ОТКУДА БЕРЁТСЯ ЦЕНА ВИТРИНЫ ═══

От чека доходит не всё:
    эквайринг ~3% + реферал 10% + налог 6%  →  остаётся ~81%
На закупке комиссия ввода средств           →  +5.5%

    цена × 0.81 = себестоимость × 1.055 × (1 + маржа)

При марже ×2.5 чистыми множитель выходит 3.3; берём 3.5 с запасом на
возвраты и поддержку.

ВАЖНО: PRICE_PER_1M_* задаётся в .env под РЕАЛЬНУЮ цену закупки оператора.
Дефолты — прайс Anthropic. Если агрегатор даёт дешевле, экономика лучше.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# --- Веса CAPS: во сколько раз токен дороже входного ---
W_INPUT = 1.0
W_OUTPUT = 5.0
W_CACHE_READ = 0.1
W_CACHE_WRITE = 1.25          # запись в кэш дороже обычного входа

# --- Экономические константы ---
ACQUIRING_FEE = 0.03          # эквайринг (ЮKassa/СБП)
REFERRAL_FEE = 0.10           # реф-программа
TAX_RATE = 0.06               # НПД / УСН «доходы»
TOPUP_FEE = 0.055             # комиссия ввода средств в агрегатор
NET_MULTIPLIER = 3.5          # цена витрины = множитель × себестоимость


def _f(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class ModelCost:
    """Закупочная цена модели в $ за 1 млн токенов."""
    name: str
    input_usd: float
    output_usd: float
    cache_read_usd: float

    @property
    def usd_per_cap(self) -> float:
        """Сколько стоит 1 CAP (= 1 входной токен) в долларах."""
        return self.input_usd / 1_000_000


def load_costs() -> dict[str, ModelCost]:
    """Закупочные цены. Дефолт — прайс Anthropic, переопределяется через .env."""
    return {
        "opus": ModelCost(
            "claude-opus-5",
            _f("WAVE_COST_OPUS_IN", 5.00),
            _f("WAVE_COST_OPUS_OUT", 25.00),
            _f("WAVE_COST_OPUS_CACHE", 0.50),
        ),
        "sonnet": ModelCost(
            "claude-sonnet-5",
            _f("WAVE_COST_SONNET_IN", 3.00),
            _f("WAVE_COST_SONNET_OUT", 15.00),
            _f("WAVE_COST_SONNET_CACHE", 0.30),
        ),
        "haiku": ModelCost(
            "claude-haiku-4-5",
            _f("WAVE_COST_HAIKU_IN", 1.00),
            _f("WAVE_COST_HAIKU_OUT", 5.00),
            _f("WAVE_COST_HAIKU_CACHE", 0.10),
        ),
    }


def usd_rate() -> float:
    """Курс ₽/$ — задаётся оператором, дефолт консервативный."""
    return _f("WAVE_USD_RATE", 90.0)


def caps_from_usage(usage: dict) -> int:
    """Перевести usage провайдера в CAPS — единственный правильный учёт расхода.

    Понимает оба формата: Anthropic (input_tokens/output_tokens/
    cache_read_input_tokens) и OpenAI (prompt_tokens/completion_tokens).
    """
    if not isinstance(usage, dict):
        return 0

    out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    cache_write = int(usage.get("cache_creation_input_tokens") or 0)

    raw_in = usage.get("input_tokens")
    if raw_in is None:
        # OpenAI-формат: prompt_tokens включает кэш — вычитаем, чтобы не задвоить.
        prompt = int(usage.get("prompt_tokens") or 0)
        details = usage.get("prompt_tokens_details") or {}
        cached = int(details.get("cached_tokens") or 0)
        if cached and not cache_read:
            cache_read = cached
        fresh_in = max(0, prompt - cache_read - cache_write)
    else:
        # Anthropic: input_tokens — уже ТОЛЬКО свежий вход, кэш отдельными полями.
        fresh_in = int(raw_in or 0)

    caps = (fresh_in * W_INPUT + out * W_OUTPUT
            + cache_read * W_CACHE_READ + cache_write * W_CACHE_WRITE)
    return int(round(caps))


def caps_cost_rub(caps: int, model_key: str = "opus") -> float:
    """Во сколько ₽ обходятся оператору эти CAPS (без комиссии ввода)."""
    cost = load_costs().get(model_key) or load_costs()["opus"]
    return caps * cost.usd_per_cap * usd_rate()


def recommend_price_rub(caps: int, model_key: str = "opus",
                        multiplier: float = NET_MULTIPLIER) -> int:
    """Рекомендованная цена витрины: не убыточная, с запасом на комиссии и налог."""
    base = caps_cost_rub(caps, model_key)
    price = base * multiplier
    # Округляем вверх до «красивого» ценника
    for step in (100, 50, 10):
        if price >= step * 10:
            return int(-(-price // step) * step)
    return max(1, int(price))


def postpaid_multiplier() -> float:
    """Множитель потокенного тарифа. По умолчанию — тот же NET_MULTIPLIER, что
    и у пакетов: постоплата не должна быть убыточнее витрины. Оператор может
    поднять его через WAVE_POSTPAID_MULTIPLIER (постоплата без обязательства
    справедливо чуть дороже пакета), но НИЖЕ NET_MULTIPLIER опускать нельзя —
    иначе потокенный доступ дешевле себестоимости с запасом."""
    m = _f("WAVE_POSTPAID_MULTIPLIER", NET_MULTIPLIER)
    return m if m >= NET_MULTIPLIER else NET_MULTIPLIER


def bill_rub(caps: int, model_key: str = "opus",
             multiplier: float | None = None) -> float:
    """Розничная цена этих CAPS для клиента на ПОТОКЕННОМ тарифе (₽, точная).

    Та же экономика, что recommend_price_rub (себестоимость × множитель с
    запасом на комиссии/налог/возвраты), но БЕЗ округления до «красивого»
    ценника: постоплата списывает дробные ₽ за КАЖДЫЙ запрос, и округление
    здесь превратило бы мелкие запросы в 0 ₽ — клиент работал бы бесплатно,
    а накопленная копейка утекала бы оператору в минус. Округляем только при
    показе в кабинете, не при списании.

    caps может быть 0 (пустой ответ) → 0 ₽. Отрицательные не бывают, но
    страхуемся max(0, …): списать «минус» нельзя.
    """
    caps = max(0, int(caps))
    mult = postpaid_multiplier() if multiplier is None else multiplier
    return caps_cost_rub(caps, model_key) * mult


def margin_report(price_rub: float, caps: int, model_key: str = "opus",
                  with_referral: bool = True) -> dict:
    """Честный разбор одного чека: сколько дойдёт до кармана при ПОЛНОМ расходе."""
    cost = caps_cost_rub(caps, model_key) * (1 + TOPUP_FEE)
    fees = ACQUIRING_FEE + TAX_RATE + (REFERRAL_FEE if with_referral else 0.0)
    net_in = price_rub * (1 - fees)
    profit = net_in - cost
    return {
        "price_rub": round(price_rub),
        "caps": caps,
        "cost_rub": round(cost),
        "net_income_rub": round(net_in),
        "profit_rub": round(profit),
        "margin_pct": round(profit / price_rub * 100, 1) if price_rub else 0.0,
        "profitable": profit > 0,
    }


def safe_hourly_cap(price_rub: float, hours: int, model_key: str = "opus",
                    target_margin: float = 0.5) -> int:
    """Максимальный потолок CAPS/час, при котором тариф остаётся прибыльным.

    Это ответ на дыру, которую нашла разведка: потолок должен выводиться ИЗ ЦЕНЫ,
    а не назначаться на глаз. При 99 ₽ и потолке 2 млн токенов оператор терял
    до 1764 ₽ на каждом чеке.
    """
    fees = ACQUIRING_FEE + TAX_RATE + REFERRAL_FEE
    budget_rub = price_rub * (1 - fees) * (1 - target_margin) / (1 + TOPUP_FEE)
    cost = load_costs().get(model_key) or load_costs()["opus"]
    rub_per_cap = cost.usd_per_cap * usd_rate()
    if rub_per_cap <= 0:
        return 0
    total_caps = budget_rub / rub_per_cap
    return max(1000, int(total_caps / max(1, hours)))

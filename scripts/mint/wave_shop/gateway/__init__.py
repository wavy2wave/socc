"""WAVE GATEWAY — init."""
from __future__ import annotations

__all__ = ["QuotaStore", "PLANS"]

from .quota import PLANS, QuotaStore

__doc__ = """
WAVE GATEWAY — прокси-шлюз к провайдеру ИИ.

Клиент НЕ получает ключ оператора. Он получает свой токен, который живёт
здесь и учитывает квоту. Шлюз подставляет настоящий ключ, считает расход
и режет по тарифу.

Это то, что делает почасовые тарифы, пакеты, подписки и безопасный «безлимит»
физически возможными.

Запуск шлюза:
    WAVE_UPSTREAM_URL=https://openrouter.ai/api/v1 \\
    WAVE_UPSTREAM_KEY=sk-or-v1-... \\
    WAVE_DATA_DIR=./data \\
    python3 -m gateway.proxy

Клиенту давать:
    base_url: http://HOST:8790/v1
    api_key: wave-... (выдаётся ботом после оплаты)
"""

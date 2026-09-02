"""WAVE SHOP — провайдеры оплаты (сменные, stdlib-only).

Единый интерфейс PaymentProvider. Три семейства путей выдачи:

  1) Telegram Stars (XTR) — оплата ВНУТРИ Telegram через sendInvoice. Не требует
     публичного сервера. Подтверждение приходит апдейтом successful_payment.
     => create_charge() шлёт инвойс; verify не нужен (бот ловит successful_payment).

  2) URL-провайдеры (ЮKassa, CryptoBot) — возвращают ссылку на оплату; статус узнаём
     опросом их API (poll), т.к. публичного вебхука у нас может не быть.

  3) Manual — показать реквизиты, оператор подтверждает выдачу кнопкой.

Каждый провайдер честно сообщает configured=False, если ключей нет — бот его прячет.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class Charge:
    ok: bool
    method: str                 # 'stars' | 'url' | 'manual' | 'recurring'
    pay_url: str = ""           # для url-провайдеров
    external_id: str = ""       # id платежа у провайдера (для poll/verify)
    stars_amount: int = 0       # кол-во XTR (для stars)
    message: str = ""           # текст для пользователя (manual/ошибка)
    payment_method_id: str = ""  # «привязанная карта» для будущих автосписаний


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 20) -> dict | None:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _get_json(url: str, headers: dict, timeout: int = 20) -> dict | None:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


class PaymentProvider:
    key = "base"
    label = "Оплата"
    hint = ""          # короткая подсказка под кнопкой (для UX)

    @property
    def configured(self) -> bool:
        raise NotImplementedError

    def create_charge(self, order: dict, product: dict) -> Charge:
        raise NotImplementedError

    def verify(self, external_id: str) -> bool:
        """True если платёж действительно оплачен. Для stars не используется."""
        return False

    def fetch_payment_method(self, external_id: str) -> str:
        """id «привязанной карты» после успешной оплаты ('' если провайдер не умеет).

        Нужно для автопродления: без сохранённой карты подписка превращается в
        ручную покупку каждый месяц, и клиент отваливается на первом же продлении.
        """
        return ""

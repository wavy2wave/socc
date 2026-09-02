"""WAVE SHOP — конкретные провайдеры оплаты.

РФ-набор 2026: СБП (самый быстрый — 1 тап в банк-приложении), карты РФ, SberPay,
Telegram Stars, крипта. Плюс ручной перевод как запасной путь.

ЮKassa умеет роутить сразу в нужный метод через payment_method_data.type —
поэтому СБП и карта заведены как ОТДЕЛЬНЫЕ кнопки: клиент не выбирает дважды.
"""
from __future__ import annotations

import base64
import hashlib
import secrets

from . import Charge, PaymentProvider, _get_json, _post_json


class StarsProvider(PaymentProvider):
    """Telegram Stars (XTR). Оплата внутри Telegram, без сервера и регистрации.

    create_charge НЕ ходит в сеть — он лишь говорит боту «выстави Stars-инвойс».
    Подтверждение приходит апдейтом successful_payment.
    """
    key = "stars"
    label = "⭐️ Telegram Stars"
    hint = "оплата внутри Telegram, 2 тапа"

    @property
    def configured(self) -> bool:
        return True  # работает всегда, если жив сам бот

    def create_charge(self, order: dict, product: dict) -> Charge:
        stars = int(product.get("stars_price", 0))
        if stars <= 0:
            return Charge(ok=False, method="stars", message="У товара не задана цена в Stars.")
        return Charge(ok=True, method="stars", stars_amount=stars)


class YooKassaProvider(PaymentProvider):
    """ЮKassa — РФ-платежи. Один класс, разные методы (СБП / карта / SberPay).

    method=None      → универсальная страница ЮKassa (все способы разом)
    method='sbp'     → сразу СБП: QR / выбор банка, без ввода карты
    method='bank_card' → сразу форма карты
    method='sberbank'  → SberPay
    """
    API = "https://api.yookassa.ru/v3/payments"

    _PRESETS = {
        "sbp":       ("sbp",       "⚡️ СБП — быстрый платёж", "1 тап в приложении банка"),
        "bank_card": ("bank_card", "💳 Банковская карта",      "Visa / MC / МИР"),
        "sberbank":  ("sberbank",  "🟢 SberPay",               "оплата через Сбербанк"),
        None:        (None,        "💳 Карта / СБП / кошелёк", "все способы на одной странице"),
    }

    def __init__(self, shop_id: str, secret_key: str, method: str | None = None,
                 return_url: str = "https://t.me") -> None:
        self.shop_id = shop_id
        self.secret_key = secret_key
        self.method = method
        self.return_url = return_url
        pm, label, hint = self._PRESETS.get(method, self._PRESETS[None])
        self.key = f"yookassa_{method}" if method else "yookassa"
        self.label = label
        self.hint = hint

    @property
    def configured(self) -> bool:
        return bool(self.shop_id and self.secret_key)

    def _auth_header(self) -> dict:
        raw = f"{self.shop_id}:{self.secret_key}".encode("utf-8")
        return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}

    def create_charge(self, order: dict, product: dict) -> Charge:
        if not self.configured:
            return Charge(ok=False, method="url", message="ЮKassa не сконфигурирована.")
        amount = int(order.get("amount_rub", 0))
        headers = {**self._auth_header(), "Idempotence-Key": secrets.token_hex(16)}
        body: dict = {
            "amount": {"value": f"{amount}.00", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": self.return_url},
            "description": f"{product.get('title','Товар')} · {order.get('order_id','')}"[:128],
            "metadata": {"order_id": order.get("order_id", "")},
        }
        # Привязка карты для автопродления. Без этого флага ЮKassa НЕ вернёт
        # payment_method.id, и списать в следующем месяце будет нечем — подписка
        # молча выродится в разовую покупку.
        if order.get("save_card"):
            body["save_payment_method"] = True
        if self.method:
            body["payment_method_data"] = {"type": self.method}
        r = _post_json(self.API, body, headers)
        if not r or "id" not in r:
            return Charge(ok=False, method="url",
                          message="Не удалось создать платёж. Попробуйте другой способ.")
        url = (r.get("confirmation") or {}).get("confirmation_url", "")
        if not url:
            return Charge(ok=False, method="url", message="Платёжная ссылка не получена.")
        return Charge(ok=True, method="url", pay_url=url, external_id=r["id"])

    def verify(self, external_id: str) -> bool:
        if not external_id:
            return False
        r = _get_json(f"{self.API}/{external_id}", self._auth_header())
        return bool(r and r.get("status") == "succeeded" and r.get("paid") is True)

    def fetch_payment_method(self, external_id: str) -> str:
        """Достать id привязанной карты из оплаченного платежа."""
        if not external_id or not self.configured:
            return ""
        r = _get_json(f"{self.API}/{external_id}", self._auth_header())
        if not r:
            return ""
        pm = r.get("payment_method") or {}
        # saved=True означает, что картой можно платить повторно без клиента.
        if pm.get("saved") and pm.get("id"):
            return str(pm["id"])
        return ""

    def charge_saved_card(self, payment_method_id: str, amount_rub: int,
                          description: str = "", idempotency_key: str = "") -> Charge:
        """Рекуррентное списание с сохранённой карты (автопродление подписки).

        payment_method_id получен при первом платеже с save_payment_method=True.

        idempotency_key должен быть СТАБИЛЕН для одного периода продления и РАЗНЫМ
        для следующего. Тогда повторный прогон cron по той же просроченной подписке
        не спишет второй раз (ЮKassa вернёт тот же платёж), а следующий месяц —
        отдельный ключ, отдельное списание. Без периода в ключе два cron-прогона
        подряд по одной подписке = двойное списание.
        """
        if not self.configured or not payment_method_id:
            return Charge(ok=False, method="url", message="Нет данных карты.")
        material = idempotency_key or f"{payment_method_id}:{amount_rub}:{description}"
        idem = hashlib.sha256(f"wave-renew:{material}".encode("utf-8")).hexdigest()
        headers = {**self._auth_header(), "Idempotence-Key": idem}
        body = {
            "amount": {"value": f"{amount_rub}.00", "currency": "RUB"},
            "capture": True,
            "payment_method_id": payment_method_id,
            "description": description[:128],
        }
        r = _post_json(self.API, body, headers)
        if not r or "id" not in r:
            return Charge(ok=False, method="url", message="Не удалось списать с карты.")
        # Деньги считаем взятыми ТОЛЬКО при подтверждённом успехе. Раньше здесь
        # любой статус (в т.ч. pending/canceled) возвращался как ok=True — магазин
        # продлевал доступ и писал выручку по НЕсписанным деньгам.
        status = r.get("status")
        if status == "succeeded" and r.get("paid"):
            return Charge(ok=True, method="recurring", external_id=r["id"])
        if status == "canceled":
            return Charge(ok=False, method="recurring", external_id=r["id"],
                          message="Карта отклонила списание.")
        # pending/waiting_for_capture и пр. — НЕ подтверждено. Не продлеваем и не
        # пишем выручку; следующий прогон с тем же idem-ключом дойдёт до итога.
        return Charge(ok=False, method="recurring", external_id=r["id"],
                      message=f"Списание не подтверждено (статус {status}).")



class CryptoProvider(PaymentProvider):
    """CryptoBot (@CryptoBot) — оплата криптой (USDT/TON)."""
    key = "crypto"
    label = "🪙 Крипта (USDT)"
    hint = "без банков РФ"
    API = "https://pay.crypt.bot/api"

    def __init__(self, token: str, asset: str = "USDT", rub_per_unit: float = 100.0) -> None:
        self.token = token
        self.asset = asset
        self.rub_per_unit = rub_per_unit  # курс ₽→asset, задаётся в .env

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict:
        return {"Crypto-Pay-API-Token": self.token}

    def create_charge(self, order: dict, product: dict) -> Charge:
        if not self.configured:
            return Charge(ok=False, method="url", message="Крипто-касса не сконфигурирована.")
        amount_rub = int(order.get("amount_rub", 0))
        crypto_amount = round(max(amount_rub / max(self.rub_per_unit, 1e-9), 0.01), 2)
        body = {
            "asset": self.asset,
            "amount": str(crypto_amount),
            "description": f"{product.get('title','Товар')} · {order.get('order_id','')}"[:128],
            "payload": order.get("order_id", ""),
            "allow_comments": False,
        }
        r = _post_json(f"{self.API}/createInvoice", body, self._headers())
        result = (r or {}).get("result") or {}
        url = result.get("bot_invoice_url") or result.get("pay_url", "")
        inv_id = str(result.get("invoice_id", ""))
        if not url or not inv_id:
            return Charge(ok=False, method="url", message="Крипта: не удалось создать счёт.")
        return Charge(ok=True, method="url", pay_url=url, external_id=inv_id)

    def verify(self, external_id: str) -> bool:
        if not external_id:
            return False
        r = _get_json(f"{self.API}/getInvoices?invoice_ids={external_id}", self._headers())
        items = ((r or {}).get("result") or {}).get("items") or []
        return any(str(i.get("invoice_id")) == str(external_id) and i.get("status") == "paid"
                   for i in items)


class ManualProvider(PaymentProvider):
    """Ручной перевод: показать реквизиты, оператор подтверждает выдачу."""
    key = "manual"
    label = "🧾 Перевод по реквизитам"
    hint = "подтверждает оператор"

    def __init__(self, details: str) -> None:
        self.details = details

    @property
    def configured(self) -> bool:
        return bool(self.details)

    def create_charge(self, order: dict, product: dict) -> Charge:
        if not self.configured:
            return Charge(ok=False, method="manual", message="Реквизиты не заданы.")
        amount = int(order.get("amount_rub", 0))
        msg = (f"Переведите <b>{amount:,} ₽</b> по реквизитам:\n\n{self.details}\n\n"
               f"В комментарии укажите: <code>{order.get('order_id','')}</code>\n\n"
               f"После перевода нажмите «Я оплатил» — оператор подтвердит и выдаст товар."
               ).replace(",", " ")
        return Charge(ok=True, method="manual", message=msg)


def build_providers(settings, return_url: str = "https://t.me") -> dict:
    """Собрать включённые провайдеры в порядке WAVE_PAYMENT_ORDER.

    Ключи порядка: sbp, card, sberpay, yookassa, stars, crypto, manual.
    """
    yk = (settings.yookassa_shop_id, settings.yookassa_secret_key)
    catalog = {
        "sbp":      lambda: YooKassaProvider(*yk, method="sbp", return_url=return_url),
        "card":     lambda: YooKassaProvider(*yk, method="bank_card", return_url=return_url),
        "sberpay":  lambda: YooKassaProvider(*yk, method="sberbank", return_url=return_url),
        "yookassa": lambda: YooKassaProvider(*yk, method=None, return_url=return_url),
        "stars":    lambda: StarsProvider(),
        "crypto":   lambda: CryptoProvider(settings.crypto_pay_token, settings.crypto_asset,
                                           settings.crypto_rub_per_unit),
        "manual":   lambda: ManualProvider(settings.manual_pay_details),
    }
    out: dict = {}
    for key in settings.payment_order:
        factory = catalog.get(key)
        if not factory:
            continue
        prov = factory()
        if prov.configured:
            out[prov.key] = prov
    return out

"""WAVE SHOP — Telegram Bot API на голом stdlib (urllib).

Канон MINT: ноль зависимостей. Ни telebot, ни aiogram — только stdlib.
Fail-soft: сетевая ошибка не роняет цикл, возвращаем None/[] и живём дальше.

Покрываем ровно то, что нужно магазину:
  long-poll getUpdates, sendMessage (+ inline-клавиатура), editMessageText,
  answerCallbackQuery, sendInvoice (в т.ч. Stars/XTR), answerPreCheckoutQuery.

ПРО ВЫБОР АДРЕСА. У api.telegram.org несколько дата-центров, и у российских
провайдеров часть из них недоступна: DNS отвечает нормально, а TCP 443 молчит
до таймаута. Обычный запрос уходит на первый адрес из DNS, виснет 20 секунд и
возвращает None — бот при этом выглядит «сломанным», хотя код исправен.
Поэтому соединение само находит живой адрес и запоминает его.

Это не обход ограничений Telegram: адрес официальный, токен свой, сертификат
проверяется на api.telegram.org как обычно. Чинится доступность у провайдера.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import ssl
import threading
from typing import Any

TG_HOST = "api.telegram.org"

# Запасные адреса дата-центров на случай, если то, что вернул DNS, недоступно.
# Порядок значения не имеет — берём первый ответивший.
TG_FALLBACK_IPS = (
    "149.154.167.220",
    "149.154.167.51",
    "149.154.175.50",
    "149.154.171.5",
    "91.108.56.130",
)

_PROBE_TIMEOUT = 4.0        # сколько ждём TCP-ответа при поиске живого адреса
_addr_lock = threading.RLock()
_addr_cache: str | None = None      # найденный живой IP (None = ещё не искали)


def _tcp_alive(ip: str, port: int = 443, timeout: float = _PROBE_TIMEOUT) -> bool:
    try:
        with socket.create_connection((ip, port), timeout):
            return True
    except OSError:
        return False


def _candidates() -> list[str]:
    """Адреса-кандидаты: сначала то, что дал DNS, потом известные запасные."""
    out: list[str] = []
    pinned = os.getenv("WAVE_TG_IP", "").strip()
    if pinned:                       # оператор задал адрес руками — он главный
        out.append(pinned)
    try:
        out.extend(socket.gethostbyname_ex(TG_HOST)[2])
    except OSError:
        pass
    for ip in TG_FALLBACK_IPS:
        if ip not in out:
            out.append(ip)
    return out


def resolve_addr(force: bool = False) -> str:
    """Живой адрес api.telegram.org. Результат запоминается до сброса.

    force=True — искать заново: сеть могла измениться (сменился провайдер,
    поднялся VPN, ожил ранее мёртвый дата-центр).
    """
    global _addr_cache
    with _addr_lock:
        if _addr_cache and not force:
            return _addr_cache
        for ip in _candidates():
            if _tcp_alive(ip):
                _addr_cache = ip
                return ip
        # Ни один не ответил — отдаём имя хоста: пусть падает честно, на DNS.
        _addr_cache = None
        return TG_HOST


class _Connection(http.client.HTTPSConnection):
    """HTTPS к Telegram по конкретному адресу, но с именем api.telegram.org.

    Соединяемся по IP, а SNI, заголовок Host и проверка сертификата остаются
    на TG_HOST — то есть это обычное честное TLS-соединение с Telegram,
    просто мы сами выбрали, через какой из его адресов идти.
    """

    def __init__(self, connect_ip: str, timeout: float) -> None:
        super().__init__(TG_HOST, 443, timeout=timeout,
                         context=ssl.create_default_context())
        self._connect_ip = connect_ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._connect_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class TelegramAPI:
    def __init__(self, token: str, timeout: int = 65) -> None:
        self.token = token
        self.timeout = timeout

    def _once(self, method: str, data: bytes, addr: str) -> dict | None:
        """Один запрос через заданный адрес. None — не доехало."""
        conn = _Connection(addr, self.timeout)
        try:
            conn.request("POST", f"/bot{self.token}/{method}", body=data,
                         headers={"Content-Type": "application/json",
                                  "Content-Length": str(len(data))})
            body = json.loads(conn.getresponse().read().decode("utf-8"))
        except (OSError, ssl.SSLError, http.client.HTTPException,
                json.JSONDecodeError, TimeoutError):
            return None
        finally:
            conn.close()
        return body if isinstance(body, dict) else None

    def _call(self, method: str, payload: dict | None = None) -> dict | None:
        data = json.dumps(payload or {}).encode("utf-8")
        body = self._once(method, data, resolve_addr())
        if body is None:
            # Адрес мог умереть на ходу — ищем живой заново и пробуем ещё раз.
            # Один повтор, не цикл: бот и так крутится в long-poll и вернётся.
            retry = resolve_addr(force=True)
            body = self._once(method, data, retry)
        return body

    def get_me(self) -> dict | None:
        r = self._call("getMe")
        return r.get("result") if r and r.get("ok") else None

    def get_updates(self, offset: int, timeout: int = 60) -> list[dict]:
        r = self._call("getUpdates", {
            "offset": offset,
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query", "pre_checkout_query"],
        })
        if r and r.get("ok"):
            return r.get("result", [])
        return []

    def send_message(self, chat_id: int, text: str,
                     keyboard: list[list[dict]] | None = None,
                     parse_mode: str = "HTML") -> dict | None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if keyboard is not None:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        r = self._call("sendMessage", payload)
        return r.get("result") if r and r.get("ok") else None

    def edit_message_text(self, chat_id: int, message_id: int, text: str,
                          keyboard: list[list[dict]] | None = None,
                          parse_mode: str = "HTML") -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if keyboard is not None:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        self._call("editMessageText", payload)

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        self._call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})

    def send_invoice(self, chat_id: int, title: str, description: str, payload: str,
                     currency: str, prices: list[dict], provider_token: str = "") -> dict | None:
        """Счёт на оплату. Для Telegram Stars: currency='XTR', provider_token=''.
        prices: [{'label': '...', 'amount': <в минимальных единицах или кол-во Stars>}].
        """
        body: dict[str, Any] = {
            "chat_id": chat_id,
            "title": title[:32],
            "description": description[:255],
            "payload": payload,
            "currency": currency,
            "prices": prices,
        }
        if provider_token:
            body["provider_token"] = provider_token
        r = self._call("sendInvoice", body)
        return r.get("result") if r and r.get("ok") else None

    def answer_pre_checkout(self, pre_checkout_id: str, ok: bool = True,
                            error_message: str = "") -> None:
        payload: dict[str, Any] = {"pre_checkout_query_id": pre_checkout_id, "ok": ok}
        if not ok and error_message:
            payload["error_message"] = error_message
        self._call("answerPreCheckoutQuery", payload)

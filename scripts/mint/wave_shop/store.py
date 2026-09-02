"""WAVE SHOP — хранилище на stdlib (JSON + атомарная запись).

Канон MINT: ноль зависимостей, fail-soft. Всё состояние — плоские JSON-файлы в data/.
Одна блокировка на процесс (бот однопоточный long-poll), атомарная замена через
os.replace, чтобы не порвать файл на сбое.

Модель:
  catalog.json   — товары (описание, цена ₽, цена в Stars, kind, активность)
  stock.json     — склад: для kind='key' список невыданных позиций на товар
  orders.json    — заказы (статус, провайдер, выданный payload, реф-код)
  users.json     — пользователи (реф-код, кто пригласил, реф-баланс)
  subscriptions.json — подписки: срок, автопродление, привязанная карта
  ledger.json    — лог выручки (verified ₽/Stars-события)
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()

# Виды товара, у которых НЕТ склада: они порождаются в момент выдачи.
#   gateway      — ключ шлюза генерируется на лету под конкретного покупателя
#   subscription — активируется срок, выдавать нечего
#   lifetime     — один и тот же payload всем, запас не расходуется
# Только kind='key' торгует ограниченным запасом из stock.json.
STOCKLESS_KINDS = frozenset({"gateway", "subscription", "lifetime"})

# Спец-значение поля subscription.next_product_id — «на продление НЕ бери пакет,
# переведи на потокенную оплату». Реальные id товаров так не называются, поэтому
# коллизии нет. Пусто/отсутствует = продлевать тем же тарифом (поведение по умолч.).
POSTPAID_CHOICE = "__postpaid__"


def needs_stock(product: dict) -> bool:
    """Нужен ли этому товару склад, чтобы считаться доступным."""
    return product.get("kind", "key") not in STOCKLESS_KINDS


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
    os.replace(tmp, path)  # атомарно


class Store:
    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir)
        self.catalog_path = self.dir / "catalog.json"
        self.stock_path = self.dir / "stock.json"
        self.orders_path = self.dir / "orders.json"
        self.users_path = self.dir / "users.json"
        self.ledger_path = self.dir / "ledger.json"
        self.subs_path = self.dir / "subscriptions.json"
        self.cards_path = self.dir / "payment_methods.json"  # привязанные карты по user_id

    # ---------- Каталог ----------
    def catalog(self, only_active: bool = True) -> list[dict]:
        items = _read(self.catalog_path, [])
        if only_active:
            items = [p for p in items if p.get("active", True)]
        return items

    def product(self, product_id: str) -> dict | None:
        for p in _read(self.catalog_path, []):
            if p.get("id") == product_id:
                return p
        return None

    def upsert_product(self, product: dict) -> None:
        with _LOCK:
            items = _read(self.catalog_path, [])
            items = [p for p in items if p.get("id") != product["id"]]
            items.append(product)
            _write(self.catalog_path, items)

    def delete_product(self, product_id: str) -> bool:
        """Убрать товар из каталога. True — если такой был и удалён.

        Склад НЕ трогаем: если оператор вернёт товар с тем же id, остатки
        сохранятся. Осиротевший склад безвреден — его никто не читает.
        """
        with _LOCK:
            items = _read(self.catalog_path, [])
            kept = [p for p in items if p.get("id") != product_id]
            if len(kept) == len(items):
                return False
            _write(self.catalog_path, kept)
            return True

    def set_active(self, product_id: str, active: bool) -> dict | None:
        """Включить/выключить товар на витрине. Возвращает обновлённую запись."""
        with _LOCK:
            items = _read(self.catalog_path, [])
            found = None
            for p in items:
                if p.get("id") == product_id:
                    p["active"] = bool(active)
                    found = p
                    break
            if found is None:
                return None
            _write(self.catalog_path, items)
            return found

    def set_price(self, product_id: str, price_rub: int | None = None,
                  stars_price: int | None = None) -> dict | None:
        """Поменять цену в ₽ и/или Stars. None-поля не трогаются."""
        with _LOCK:
            items = _read(self.catalog_path, [])
            found = None
            for p in items:
                if p.get("id") == product_id:
                    if price_rub is not None:
                        p["price_rub"] = max(0, int(price_rub))
                    if stars_price is not None:
                        p["stars_price"] = max(0, int(stars_price))
                    found = p
                    break
            if found is None:
                return None
            _write(self.catalog_path, items)
            return found

    def set_payload(self, product_id: str, payload: str) -> dict | None:
        """Поменять текст мгновенной выдачи (для kind='lifetime')."""
        with _LOCK:
            items = _read(self.catalog_path, [])
            found = None
            for p in items:
                if p.get("id") == product_id:
                    p["lifetime_payload"] = str(payload)
                    found = p
                    break
            if found is None:
                return None
            _write(self.catalog_path, items)
            return found

    # ---------- Склад ----------
    def is_available(self, product: dict) -> bool:
        """Можно ли этот товар купить прямо сейчас.

        ЕДИНСТВЕННЫЙ источник истины о наличии — раньше это условие было
        размазано по трём местам (список витрины, карточка товара, админка)
        и разъехалось: карточка считала склад для kind='gateway', у которого
        склада нет и быть не может. В итоге у ВСЕХ товаров каталога вместо
        кнопки «Купить» висело «нет в наличии», и магазин был мёртв целиком.
        """
        if needs_stock(product):
            return self.stock_count(product["id"]) > 0
        return True

    def stock_count(self, product_id: str) -> int:
        stock = _read(self.stock_path, {})
        return len(stock.get(product_id, []))

    def add_stock(self, product_id: str, payloads: list[str]) -> int:
        with _LOCK:
            stock = _read(self.stock_path, {})
            bucket = stock.get(product_id, [])
            bucket.extend(str(x).strip() for x in payloads if str(x).strip())
            stock[product_id] = bucket
            _write(self.stock_path, stock)
            return len(bucket)

    def pop_stock(self, product_id: str) -> str | None:
        """Снять одну позицию со склада (для kind='key'). None если пусто."""
        with _LOCK:
            stock = _read(self.stock_path, {})
            bucket = stock.get(product_id, [])
            if not bucket:
                return None
            item = bucket.pop(0)
            stock[product_id] = bucket
            _write(self.stock_path, stock)
            return item

    # ---------- Пользователи + рефералы ----------
    def get_or_create_user(self, user_id: int, username: str = "", ref_by: str = "") -> dict:
        with _LOCK:
            users = _read(self.users_path, {})
            key = str(user_id)
            user = users.get(key)
            if user is None:
                user = {
                    "user_id": user_id,
                    "username": username,
                    "ref_code": secrets.token_hex(4),   # персональная реф-ссылка
                    "ref_by": ref_by or "",             # чей код привёл (только при первом визите)
                    "ref_balance": 0,                   # накоплено ₽ с приглашённых
                    "ref_earned_total": 0,
                    "created_at": _now(),
                }
                users[key] = user
                _write(self.users_path, users)
            elif username and user.get("username") != username:
                user["username"] = username
                users[key] = user
                _write(self.users_path, users)
            return user

    def user_by_ref_code(self, ref_code: str) -> dict | None:
        for u in _read(self.users_path, {}).values():
            if u.get("ref_code") == ref_code:
                return u
        return None

    def all_users(self) -> list[dict]:
        """Все пользователи — для операторской панели. Только чтение."""
        return list(_read(self.users_path, {}).values())

    def credit_referrer(self, ref_code: str, amount_rub: int) -> dict | None:
        """Начислить рефереру награду с реальной покупки приглашённого."""
        with _LOCK:
            users = _read(self.users_path, {})
            for key, u in users.items():
                if u.get("ref_code") == ref_code:
                    u["ref_balance"] = u.get("ref_balance", 0) + amount_rub
                    u["ref_earned_total"] = u.get("ref_earned_total", 0) + amount_rub
                    users[key] = u
                    _write(self.users_path, users)
                    return u
            return None

    def ref_stats(self, ref_code: str) -> dict:
        users = _read(self.users_path, {})
        invited = [u for u in users.values() if u.get("ref_by") == ref_code]
        me = self.user_by_ref_code(ref_code) or {}
        return {
            "invited": len(invited),
            "balance": me.get("ref_balance", 0),
            "earned_total": me.get("ref_earned_total", 0),
        }

    # ---------- Заказы ----------
    def create_order(self, user_id: int, product_id: str, provider: str,
                     amount_rub: int, ref_by: str = "") -> dict:
        with _LOCK:
            orders = _read(self.orders_path, {})
            order_id = f"ord_{_now()}_{secrets.token_hex(3)}"
            order = {
                "order_id": order_id,
                "user_id": user_id,
                "product_id": product_id,
                "provider": provider,
                "amount_rub": amount_rub,
                "ref_by": ref_by or "",
                "status": "pending",       # pending -> paid -> delivered | failed
                "payload": "",             # выданный ключ/текст
                "created_at": _now(),
                "paid_at": 0,
                "delivered_at": 0,
            }
            orders[order_id] = order
            _write(self.orders_path, orders)
            return order

    def get_order(self, order_id: str) -> dict | None:
        return _read(self.orders_path, {}).get(order_id)

    def update_order(self, order_id: str, **fields: Any) -> dict | None:
        with _LOCK:
            orders = _read(self.orders_path, {})
            order = orders.get(order_id)
            if order is None:
                return None
            order.update(fields)
            orders[order_id] = order
            _write(self.orders_path, orders)
            return order

    def all_orders(self) -> list[dict]:
        """Все заказы — для операторской панели. Только чтение."""
        return list(_read(self.orders_path, {}).values())

    # ---------- Подписки (автопродление) ----------
    #
    # Как это работает по-настоящему: ЮKassa при первом платеже с флагом
    # save_payment_method=True возвращает payment_method.id — «привязанную карту».
    # Дальше магазин сам инициирует безакцептное списание этим id, без участия
    # клиента. Мы храним этот id, дату следующего списания и флаг автопродления.
    #
    # Закон: клиент ВСЕГДА может отключить автопродление одной кнопкой, и его
    # предупреждают заранее. Без этого это не подписка, а списание втихую.

    def subscription(self, user_id: int, product_id: str) -> dict | None:
        subs = _read(self.subs_path, {})
        return subs.get(f"{user_id}:{product_id}")

    def user_subscriptions(self, user_id: int) -> list[dict]:
        subs = _read(self.subs_path, {})
        return [s for s in subs.values() if s.get("user_id") == user_id]

    def all_subscriptions(self) -> list[dict]:
        """Все подписки — для операторской панели. Только чтение."""
        return list(_read(self.subs_path, {}).values())

    def upsert_subscription(self, user_id: int, product_id: str, period_days: int,
                            amount_rub: int, payment_method_id: str = "",
                            autorenew: bool = True, extend: bool = False) -> dict:
        """Создать или продлить подписку.

        extend=True — продление: срок считается от текущего paid_until (не от «сейчас»),
        чтобы клиент не терял оплаченные дни.

        Запись каждый раз пересобирается заново, поэтому поля, которые обязаны
        пережить продление, переносим из existing ЯВНО:
          • payment_method_id / renewals / created_at — привязка карты и история;
          • next_product_id — ВЫБОР клиента, чем списывать в следующий раз
            (пусто = тем же тарифом). Без переноса выбор стирался бы при первом
            же автосписании, и «сменить пакет на продление» молча не срабатывало.
        """
        with _LOCK:
            subs = _read(self.subs_path, {})
            key = f"{user_id}:{product_id}"
            now = _now()
            existing = subs.get(key)
            base = now
            if extend and existing and int(existing.get("paid_until", 0)) > now:
                base = int(existing["paid_until"])
            sub = {
                "user_id": user_id,
                "product_id": product_id,
                "period_days": period_days,
                "amount_rub": amount_rub,
                "paid_until": base + period_days * 86400,
                "autorenew": bool(autorenew),
                "payment_method_id": payment_method_id or (existing or {}).get("payment_method_id", ""),
                "renewals": int((existing or {}).get("renewals", 0)) + (1 if extend else 0),
                "next_product_id": (existing or {}).get("next_product_id", ""),
                "notified_for": 0,          # до какого paid_until уже отправляли предупреждение
                "failed_attempts": 0,
                "created_at": int((existing or {}).get("created_at", now)),
                "updated_at": now,
            }
            subs[key] = sub
            _write(self.subs_path, subs)
            return sub

    def set_autorenew(self, user_id: int, product_id: str, on: bool) -> dict | None:
        with _LOCK:
            subs = _read(self.subs_path, {})
            key = f"{user_id}:{product_id}"
            sub = subs.get(key)
            if not sub:
                return None
            sub["autorenew"] = bool(on)
            sub["updated_at"] = _now()
            subs[key] = sub
            _write(self.subs_path, subs)
            return sub

    def mark_sub_field(self, user_id: int, product_id: str, **fields: Any) -> dict | None:
        with _LOCK:
            subs = _read(self.subs_path, {})
            key = f"{user_id}:{product_id}"
            sub = subs.get(key)
            if not sub:
                return None
            sub.update(fields)
            sub["updated_at"] = _now()
            subs[key] = sub
            _write(self.subs_path, subs)
            return sub

    def subs_due_for_renewal(self, now: int | None = None) -> list[dict]:
        """Подписки, которым пора списать (срок истёк, автопродление включено, есть карта)."""
        now = now or _now()
        return [s for s in _read(self.subs_path, {}).values()
                if s.get("autorenew") and s.get("payment_method_id")
                and int(s.get("paid_until", 0)) <= now
                and int(s.get("failed_attempts", 0)) < 3]

    def subs_due_for_notice(self, notice_days: int, now: int | None = None) -> list[dict]:
        """Подписки, о списании по которым надо предупредить заранее (и ещё не предупреждали)."""
        now = now or _now()
        horizon = now + notice_days * 86400
        out = []
        for s in _read(self.subs_path, {}).values():
            if not s.get("autorenew") or not s.get("payment_method_id"):
                continue
            paid_until = int(s.get("paid_until", 0))
            if now < paid_until <= horizon and int(s.get("notified_for", 0)) != paid_until:
                out.append(s)
        return out

    def is_active(self, user_id: int, product_id: str, now: int | None = None) -> bool:
        sub = self.subscription(user_id, product_id)
        return bool(sub and int(sub.get("paid_until", 0)) > (now or _now()))

    # ---------- Привязанная карта (card-on-file) ----------
    #
    # Зачем отдельно от подписки: у клиента может НЕ быть подписки, а карта нужна —
    # чтобы включить автопополнение потокенного кошелька («трафик кончился →
    # автосписание») или чтобы «просто привязать карту» одним действием. Карта
    # живёт на УРОВНЕ пользователя: одна привязка обслуживает и продление подписок,
    # и автопополнение постоплаты.
    #
    # ЧТО ХРАНИМ: только payment_method_id от ЮKassa (безопасный токен для
    # безакцептного списания) + маску карты для показа («•• 4242»). Ни полного
    # номера, ни CVV — их у нас физически нет, ЮKassa не отдаёт. Списание всегда
    # инициируем мы, но согласие клиента (кнопка) — обязательное условие.

    def set_card_on_file(self, user_id: int, payment_method_id: str,
                         title: str = "", provider: str = "yookassa") -> dict:
        """Запомнить привязанную карту пользователя (перезаписывает прошлую)."""
        with _LOCK:
            cards = _read(self.cards_path, {})
            key = str(user_id)
            prev = cards.get(key) or {}
            card = {
                "user_id": user_id,
                "payment_method_id": payment_method_id,
                "title": title or prev.get("title", ""),
                "provider": provider or prev.get("provider", "yookassa"),
                "bound_at": int(prev.get("bound_at", _now())),
                "updated_at": _now(),
            }
            cards[key] = card
            _write(self.cards_path, cards)
            return card

    def card_on_file(self, user_id: int) -> dict | None:
        """Привязанная карта пользователя или None."""
        card = _read(self.cards_path, {}).get(str(user_id))
        return card if card and card.get("payment_method_id") else None

    def forget_card(self, user_id: int) -> bool:
        """Забыть карту (клиент отвязал). True — если что-то удалили."""
        with _LOCK:
            cards = _read(self.cards_path, {})
            if cards.pop(str(user_id), None) is None:
                return False
            _write(self.cards_path, cards)
            return True

    # ---------- LEDGER (учёт выручки) ----------
    def record_revenue(self, order_id: str, user_id: int, product_id: str,
                       provider: str, amount_rub: int, external_ref: str = "") -> None:
        with _LOCK:
            ledger = _read(self.ledger_path, [])
            ledger.append({
                "ts": _now(),
                "order_id": order_id,
                "user_id": user_id,
                "product_id": product_id,
                "provider": provider,
                "amount_rub": amount_rub,
                "external_ref": external_ref,   # id платежа у провайдера
            })
            _write(self.ledger_path, ledger)

    def revenue_total(self) -> dict:
        ledger = _read(self.ledger_path, [])
        total = sum(int(e.get("amount_rub", 0)) for e in ledger)
        return {"orders": len(ledger), "rub_total": total}

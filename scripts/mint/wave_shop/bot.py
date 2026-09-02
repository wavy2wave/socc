"""WAVE SHOP — бот: витрина, чекаут, мгновенная выдача, честные рефералы, админка.

Два слоя:
  ShopCore  — бизнес-логика БЕЗ сети (выдача товара, реф-начисление, LEDGER). Тестируема.
  ShopBot   — Telegram-обвязка (long-poll, кнопки, инвойсы) поверх ShopCore.

Запуск:  python3 -m scripts.mint.wave_shop.bot   (из корня SOCC)
     или  python3 bot.py                          (из папки wave_shop)
"""
from __future__ import annotations

import html
import secrets
import sys
import time
from pathlib import Path

# --- импорт как модуля пакета И как одиночного файла ---
if __package__:
    from .config import load_settings, Settings
    from .store import Store, needs_stock, POSTPAID_CHOICE
    from .telegram_api import TelegramAPI
    from .payments.providers import build_providers
else:  # запуск python3 bot.py из папки
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from config import load_settings, Settings           # type: ignore
    from store import Store, needs_stock, POSTPAID_CHOICE                    # type: ignore
    from telegram_api import TelegramAPI                   # type: ignore
    from payments.providers import build_providers         # type: ignore

# Отказ «одноразовый тариф уже выдан» — не сбой выдачи, а нормальный ответ.
# Импорт мягкий: магазин должен подниматься и без модуля шлюза.
try:
    from gateway.quota import AlreadyIssued as _AlreadyIssued
except ImportError:                                        # pragma: no cover
    class _AlreadyIssued(ValueError):                      # type: ignore[no-redef]
        pass


def fmt_price(product: dict, settings: Settings) -> str:
    if int(product.get("price_rub", 0)) <= 0:
        return "бесплатно"
    parts = [f"{product.get('price_rub', 0):,} ₽".replace(",", " ")]
    if product.get("stars_price"):
        parts.append(f"{product['stars_price']} ⭐")
    return " / ".join(parts)


def _client_dashboard() -> str:
    """Адрес кабинета клиента «ввёл ключ → отсчёт».

    Если оператор не задал WAVE_PUBLIC_DASHBOARD, берём корень шлюза: страница
    живёт там же, где /v1 (см. gateway/proxy.py). Так ссылка на кабинет есть
    всегда, как только известен адрес шлюза, — отдельного хоста не требуется.
    """
    import os
    explicit = os.environ.get("WAVE_PUBLIC_DASHBOARD", "").strip()
    if explicit:
        return explicit.rstrip("/")
    gw = os.environ.get("WAVE_PUBLIC_GATEWAY", "").strip().rstrip("/")
    if not gw:
        return ""
    if gw.endswith("/v1"):
        gw = gw[:-3]
    return gw.rstrip("/")


def fmt_sub_status(sub: dict) -> str:
    """Короткий статус подписки для UI."""
    import time
    now = int(time.time())
    paid_until = int(sub.get("paid_until", 0))
    if paid_until <= now:
        return "❌ закончилась"
    auto = "🔄 автопродление" if sub.get("autorenew") else "⏸ без продления"
    return f"✅ до {time.strftime('%d.%m.%Y', time.localtime(paid_until))} · {auto}"


class ShopCore:
    """Бизнес-логика без сети — можно гонять в тестах без Telegram."""

    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    def deliver(self, order_id: str) -> tuple[bool, str]:
        """Выдать товар по оплаченному заказу. Возврат: (успех, текст_для_клиента)."""
        order = self.store.get_order(order_id)
        if not order:
            return False, "Заказ не найден."
        if order.get("status") == "delivered" and order.get("payload"):
            return True, order["payload"]  # идемпотентно: повторная выдача того же
        product = self.store.product(order["product_id"])
        if not product:
            return False, "Товар недоступен."

        kind = product.get("kind", "key")
        if kind == "gateway":
            # Тариф шлюза: выдаём клиенту ЕГО токен. Ключ оператора не покидает шлюз.
            try:
                payload = self._issue_gateway_key(order, product)
            except _AlreadyIssued:
                # Бесплатный тариф уже выдавался этому аккаунту. Это не сбой —
                # не обещаем возврат денег там, где денег не было.
                self.store.update_order(order_id, status="rejected",
                                        rejected_reason="once_per_user")
                return False, ("Этот доступ выдаётся один раз на аккаунт — "
                               "вы его уже получали. Ключ есть в «Мои ключи».")
            if payload is None:
                return False, "Не удалось выдать ключ — напишите в поддержку, вернём деньги."
            # Повторяющийся тариф → завести запись подписки, иначе движок
            # автопродления её никогда не увидит и клиент отвалится через месяц.
            self._register_subscription(order, product)
        elif kind == "subscription":
            # Подписка: активируем срок, а не выдаём ключ со склада.
            # period_days=0 → бессрочный доступ (квота не сгорает).
            period = int(product.get("period_days", 0))
            sub = self.store.upsert_subscription(
                user_id=order["user_id"],
                product_id=product["id"],
                period_days=period if period > 0 else 36500,  # 100 лет ≈ «навсегда»
                amount_rub=int(order.get("amount_rub", 0)),
                payment_method_id=order.get("payment_method_id", ""),
                autorenew=bool(period > 0 and order.get("payment_method_id")),
                extend=True,
            )
            quota = int(product.get("quota_tokens", 0))
            quota_line = f"\n📊 Квота: <b>{quota // 1_000_000} млн токенов</b>" if quota else ""
            if period > 0:
                until = time.strftime("%d.%m.%Y", time.localtime(int(sub["paid_until"])))
                payload = (f"Подписка активирована ✅{quota_line}\n"
                           f"⏳ Активна до: <b>{until}</b>")
            else:
                payload = (f"Доступ активирован ✅{quota_line}\n"
                           f"♾ Без срока — квота не сгорает.")
            payload += "\n\nКлюч доступа придёт следующим сообщением."
        elif kind == "lifetime":
            payload = product.get("lifetime_payload", "Доступ активирован. Спасибо!")
        else:  # 'key' — снять позицию со склада
            payload = self.store.pop_stock(product["id"])
            if payload is None:
                return False, "На складе закончился товар — напишите в поддержку, вернём деньги."

        self.store.update_order(order_id, status="delivered", payload=payload,
                                delivered_at=int(time.time()))
        # LEDGER: учёт выручки. Бесплатные выдачи в него не пишем — иначе демо
        # раздувает счётчик продаж и средний чек перестаёт быть правдой.
        if int(order.get("amount_rub", 0)) > 0:
            self.store.record_revenue(order_id, order["user_id"], product["id"],
                                      order.get("provider", ""), int(order.get("amount_rub", 0)))
        # Честный реферал: наградить пригласившего с РЕАЛЬНОЙ покупки
        self._reward_referrer(order, product)
        return True, payload

    def _issue_gateway_key(self, order: dict, product: dict) -> str | None:
        """Выдать клиенту токен шлюза + инструкцию подключения.

        Если у клиента УЖЕ есть ключ на этот тариф — продлеваем его, а не
        выдаём новый. Это принципиально: клиент один раз вписал ключ в Cursor,
        и при продлении ему НЕЧЕГО перенастраивать. Новый ключ каждый месяц
        превращал бы продление в работу и выталкивал клиента из системы.

        Поднимает _AlreadyIssued, если тариф одноразовый и уже выдавался.
        """
        try:
            from gateway.quota import QuotaStore, canon_plan_id, get_plan
        except ImportError:
            return None
        plan_id = product.get("plan_id", product["id"])
        plan = get_plan(plan_id)
        if not plan:
            return None
        gq = QuotaStore(self.settings.data_dir)
        # Сколько клиент реально заплатил за этот ключ — для честного «потрачено ₽»
        # в кабинете (по ЕГО тарифу, не по закупке оператора).
        paid_rub = int(order.get("amount_rub", 0))

        rec = None
        renewed = False
        # Продлять имеет смысл только повторяющиеся тарифы. Почасовые и демо —
        # всегда новый ключ (иначе «час» стал бы бесконечно продлеваемым).
        if plan["kind"] in {"subscription", "unlimited", "package"}:
            canon = canon_plan_id(plan_id)
            mine = [k for k in gq.keys_of_user(order["user_id"])
                    if canon_plan_id(str(k.get("plan_id", ""))) == canon]
            if mine:
                # Берём самый свежий ключ этого тарифа.
                target = max(mine, key=lambda k: int(k.get("created_at", 0)))
                rec = gq.extend(target["token"], plan_id, price_rub=paid_rub)
                renewed = rec is not None

        if rec is None:
            try:
                rec = gq.issue_key(user_id=order["user_id"], plan_id=plan_id,
                                   order_id=order["order_id"], price_rub=paid_rub)
            except _AlreadyIssued:
                raise
            except ValueError:
                return None

        import os
        gw = os.environ.get("WAVE_PUBLIC_GATEWAY", "http://127.0.0.1:8790/v1")
        dash = _client_dashboard()
        token = rec["token"]

        if renewed:
            lines = ["♻️ <b>Тариф продлён — ключ тот же</b>\n",
                     f"<code>{token}</code>\n",
                     "Ничего перенастраивать не нужно: ключ в ваших инструментах "
                     "продолжает работать.\n"]
        else:
            lines = ["🔑 <b>Ваш ключ доступа</b>\n", f"<code>{token}</code>\n"]
        if rec["kind"] == "unlimited":
            lines.append(f"👑 Тариф: <b>{rec['title']}</b> · без ограничений по объёму")
        elif rec["kind"] == "hourly":
            secs = max(0, int(rec.get("expires_at", 0)) - int(time.time()))
            # Короткий доступ (тариф «20 минут») меряем минутами — иначе он
            # округлялся бы до «~1 ч» и вводил друга в заблуждение.
            left = f"~{max(1, secs // 60)} мин" if secs < 3600 else f"~{secs // 3600} ч"
            lines.append(f"⏱ Тариф: <b>{rec['title']}</b> · осталось {left}")
        else:
            lines.append(f"📊 Тариф: <b>{rec['title']}</b> · "
                         f"{int(rec.get('tokens_limit', 0)) // 1_000_000} млн токенов")

        lines += [
            "\n<b>Как подключить:</b>",
            f"base_url: <code>{gw}</code>",
            f"api_key: <code>{token}</code>",
            "\nРаботает в Cursor, Continue, curl, Python/JS SDK — везде, где есть "
            "OpenAI-совместимый режим.",
        ]
        if dash:
            # Ключ в hash (#…) — открыл и сразу видит отсчёт, вставлять не нужно.
            lines.append(f"\n📈 Кабинет (расход и время): {dash}/#{token}")
        lines.append(f"\nПоддержка: {self.settings.support_contact}")
        return "\n".join(lines)

    def _register_subscription(self, order: dict, product: dict) -> None:
        """Завести/продлить запись подписки для повторяющегося тарифа шлюза.

        Без неё subs_due_for_renewal() всегда пуст, движок автопродления
        крутится вхолостую, и любая «подписка» по факту разовая.
        """
        try:
            from gateway.quota import get_plan
        except ImportError:
            return
        plan = get_plan(product.get("plan_id", product["id"]))
        if not plan or plan["kind"] not in {"subscription", "unlimited"}:
            return
        period = int(plan.get("period_days", 0))
        if period <= 0:
            return
        pm_id = str(order.get("payment_method_id", ""))
        self.store.upsert_subscription(
            user_id=order["user_id"],
            product_id=product["id"],
            period_days=period,
            amount_rub=int(order.get("amount_rub", 0)),
            payment_method_id=pm_id,
            # Автопродление включаем ТОЛЬКО если карта действительно привязана.
            # Иначе обещали бы списание, которого не сможем сделать.
            autorenew=bool(pm_id),
            extend=True,
        )

    def _reward_referrer(self, order: dict, product: dict) -> None:
        ref_by = order.get("ref_by", "")
        if not ref_by:
            return
        pct = self.settings.ref_reward_percent
        reward = int(int(order.get("amount_rub", 0)) * pct / 100)
        if reward > 0:
            self.store.credit_referrer(ref_by, reward)

    def mark_paid(self, order_id: str, external_ref: str = "") -> None:
        """Пометить заказ оплаченным — БЕЗ отката уже завершённого.

        Раньше статус ставился в 'paid' безусловно. Но successful_payment от
        Telegram может прийти дважды (ретрай сети), а /confirm — быть нажат
        повторно. Тогда 'paid' затирал 'delivered', страж идемпотентности в
        deliver() слепнул, и заказ выдавался второй раз: второй ключ со склада,
        двойная реф-награда, двойная запись в LEDGER. Завершённый заказ трогать
        нельзя — с деньгами это не косметика, а реальная потеря.
        """
        order = self.store.get_order(order_id)
        if order and order.get("status") in {"delivered", "rejected"}:
            return
        fields = {"status": "paid", "paid_at": int(time.time())}
        if external_ref:
            fields["external_ref"] = external_ref
        self.store.update_order(order_id, **fields)


class ShopBot:
    """Telegram-обвязка поверх ShopCore. Long-poll, кнопки, инвойсы."""

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.store = Store(settings.data_dir)
        self.core = ShopCore(self.store, settings)
        self.api = TelegramAPI(settings.bot_token)
        self.providers = build_providers(settings)
        self.offset = 0
        self.bot_username = ""
        # Состояние мастера добавления товара: user_id -> {"step":..., "draft":{...}}.
        # Живёт в памяти: незаконченный черновик не должен переживать перезапуск.
        self._admin_state: dict[int, dict] = {}

    def _home_kb(self) -> list[list[dict]]:
        return [
            [{"text": "🛍 Витрина", "callback_data": "shop"}],
            [{"text": "🔑 Мои ключи", "callback_data": "my"},
             {"text": "📦 Мои заказы", "callback_data": "orders"}],
            [{"text": "💰 Баланс и рефералы", "callback_data": "refs"}],
            [{"text": "❓ Помощь", "callback_data": "help"}],
        ]

    def _show(self, chat_id: int, message_id: int | None, text: str,
              kb: list[list[dict]]) -> None:
        """Показать экран: правкой сообщения (если пришли из кнопки) или новым."""
        if message_id:
            self.api.edit_message_text(chat_id, message_id, text, kb)
        else:
            self.api.send_message(chat_id, text, kb)

    def _all_orders(self) -> list[dict]:
        import json as _json
        try:
            raw = self.store.orders_path.read_text(encoding="utf-8")
            return list(_json.loads(raw).values())
        except (OSError, ValueError):
            return []

    def _notify_admins(self, text: str) -> None:
        for admin_id in self.s.admin_ids:
            self.api.send_message(admin_id, text)

    # ---------- Экраны ----------
    def cmd_start(self, chat_id: int, user_id: int, username: str, arg: str) -> None:
        # Реф-код из /start ref_<code> — фиксируется только при первом визите.
        ref_by = ""
        if arg.startswith("ref_"):
            code = arg[4:].strip()
            inviter = self.store.user_by_ref_code(code)
            if inviter and inviter.get("user_id") != user_id:
                ref_by = code
        self.store.get_or_create_user(user_id, username, ref_by=ref_by)
        text = (f"<b>{html.escape(self.s.shop_name)}</b> — цифровые товары с мгновенной выдачей.\n\n"
                f"⚡️ Оплатили — товар сразу здесь, в чате.\n"
                f"🔒 Только легальный доступ и честная гарантия.\n\n"
                f"Выберите раздел:")
        self.api.send_message(chat_id, text, self._home_kb())

    def render_home(self, chat_id: int, message_id: int | None = None) -> None:
        text = (f"<b>{html.escape(self.s.shop_name)}</b>\n\nВыберите раздел:")
        self._show(chat_id, message_id, text, self._home_kb())

    def render_shop(self, chat_id: int, message_id: int | None = None) -> None:
        catalog = self.store.catalog(only_active=True)
        if not catalog:
            body = "Витрина пока пуста. Загляните позже 🌊"
            kb = [[{"text": "⬅️ Назад", "callback_data": "home"}]]
        else:
            body = f"<b>🛍 Витрина</b>\n\nВыберите товар:"
            kb = []
            for p in catalog:
                sold_out = not self.store.is_available(p)
                mark = " (нет в наличии)" if sold_out else ""
                kb.append([{"text": f"{p.get('title','Товар')} — {fmt_price(p, self.s)}{mark}",
                            "callback_data": f"p:{p['id']}"}])
            kb.append([{"text": "⬅️ Назад", "callback_data": "home"}])
        self._show(chat_id, message_id, body, kb)

    def render_product(self, chat_id: int, message_id: int, product_id: str) -> None:
        p = self.store.product(product_id)
        if not p:
            self._show(chat_id, message_id, "Товар не найден.",
                       [[{"text": "⬅️ Витрина", "callback_data": "shop"}]])
            return
        kind = p.get("kind", "key")
        in_stock = self.store.is_available(p)
        status = "♾ Вечный доступ" if kind == "lifetime" else ("✅ В наличии" if in_stock else "⛔️ Нет в наличии")
        body = (f"<b>{html.escape(p.get('title','Товар'))}</b>\n\n"
                f"{html.escape(p.get('description',''))}\n\n"
                f"Цена: <b>{fmt_price(p, self.s)}</b>\n{status}")
        kb = []
        if in_stock:
            kb.append([{"text": "🛒 Купить", "callback_data": f"buy:{p['id']}"}])
        kb.append([{"text": "⬅️ Витрина", "callback_data": "shop"}])
        self._show(chat_id, message_id, body, kb)

    def render_buy(self, chat_id: int, message_id: int, product_id: str,
                   user_id: int = 0) -> None:
        """Экран выбора способа оплаты."""
        p = self.store.product(product_id)
        if not p:
            return
        # Бесплатный тариф не идёт через кассу — выдаём сразу.
        if int(p.get("price_rub", 0)) <= 0:
            self.grant_free(chat_id, message_id, product_id, user_id or chat_id)
            return
        if not self.providers:
            self._show(chat_id, message_id,
                       "Приём оплаты ещё не настроен. Поддержка: " + html.escape(self.s.support_contact),
                       [[{"text": "⬅️ Назад", "callback_data": f"p:{product_id}"}]])
            return
        body = (f"<b>{html.escape(p.get('title','Товар'))}</b>\n"
                f"К оплате: <b>{fmt_price(p, self.s)}</b>\n\nВыберите способ:")
        kb = []
        for key, prov in self.providers.items():
            if key == "stars" and not p.get("stars_price"):
                continue
            label = prov.label
            if prov.hint:
                label += f"\n  💡 {prov.hint}"
            kb.append([{"text": label, "callback_data": f"pay:{key}:{product_id}"}])
        kb.append([{"text": "⬅️ Назад", "callback_data": f"p:{product_id}"}])
        self._show(chat_id, message_id, body, kb)

    def render_refs(self, chat_id: int, message_id: int, user_id: int) -> None:
        user = self.store.get_or_create_user(user_id)
        stats = self.store.ref_stats(user.get("ref_code", ""))
        link = (f"https://t.me/{self.bot_username}?start=ref_{user.get('ref_code','')}"
                if self.bot_username else "(ссылка появится после запуска бота)")
        body = (f"<b>💰 Баланс и рефералы</b>\n\n"
                f"Ваша ссылка:\n<code>{html.escape(link)}</code>\n\n"
                f"Приглашено: <b>{stats['invited']}</b>\n"
                f"Баланс: <b>{stats['balance']} ₽</b>\n"
                f"Заработано всего: <b>{stats['earned_total']} ₽</b>\n\n"
                f"Вы получаете <b>{self.s.ref_reward_percent}%</b> с каждой реальной покупки "
                f"приглашённого. Платит магазин, а не приглашённый.")
        self._show(chat_id, message_id, body, [[{"text": "⬅️ Назад", "callback_data": "home"}]])

    def render_orders(self, chat_id: int, message_id: int, user_id: int) -> None:
        mine = [o for o in self._all_orders()
                if o.get("user_id") == user_id and o.get("status") == "delivered"]
        if not mine:
            body = "У вас пока нет покупок."
        else:
            lines = ["<b>📦 Ваши покупки</b>\n"]
            for o in mine[-10:]:
                p = self.store.product(o["product_id"]) or {}
                title = html.escape(p.get("title", "Товар"))
                # Тарифы шлюза/подписки отдают размеченный HTML с ключом внутри —
                # его нельзя ни экранировать (клиент увидит сырые теги), ни
                # вываливать целиком в список. Показываем короткую строку и
                # отсылаем к «Мои ключи», где ключ и кнопка подключения.
                if p.get("kind") in {"gateway", "subscription"}:
                    lines.append(f"• {title} — ключ в «⚡️ Мои ключи»")
                elif p.get("kind") == "lifetime":
                    lines.append(f"• {title} — доступ активирован")
                else:
                    lines.append(f"• {title}: "
                                 f"<code>{html.escape(o.get('payload',''))}</code>")
            body = "\n".join(lines)
        self._show(chat_id, message_id, body, [[{"text": "⬅️ Назад", "callback_data": "home"}]])

    def render_help(self, chat_id: int, message_id: int) -> None:
        body = (f"<b>❓ Помощь</b>\n\n"
                f"1. «Витрина» → выберите товар.\n"
                f"2. «Купить» → выберите способ оплаты.\n"
                f"3. После оплаты товар придёт прямо сюда.\n\n"
                f"Не пришёл товар или вопрос по оплате — {html.escape(self.s.support_contact)}")
        self._show(chat_id, message_id, body, [[{"text": "⬅️ Назад", "callback_data": "home"}]])

    def render_my_subs(self, chat_id: int, message_id: int | None, user_id: int) -> None:
        """Мои ключи: активные тарифы шлюза + подписки, остаток, автопродление."""
        import os
        lines: list[str] = ["<b>🔑 Мои ключи</b>"]
        kb: list[list[dict]] = []
        found = False

        # 1) Ключи шлюза — главное, что купил клиент
        try:
            from gateway.quota import QuotaStore
            gq = QuotaStore(self.s.data_dir)
            for rec in gq.keys_of_user(user_id):
                st = gq.status(rec["token"])
                if not st:
                    continue
                found = True
                token = rec["token"]
                lines.append(f"\n<b>{html.escape(st['title'])}</b>")
                lines.append(f"<code>{token}</code>")
                if st.get("unlimited"):
                    used = st.get("spent_today", 0) / 1_000_000
                    cap = st.get("daily_cap", 0) / 1_000_000
                    lines.append(f"👑 Безлимит · сегодня {used:.1f} из {cap:.0f} млн")
                elif st.get("postpaid"):
                    # Потокенная оплата — не пакет, а ₽-кошелёк: списываем по факту
                    # («трафик кончился → автосписание»). Показываем деньги, а не
                    # остаток токенов и не срок (у кошелька срока нет).
                    bal = float(st.get("balance_rub", 0.0))
                    spent = float(st.get("spent_rub", 0.0))
                    lines.append(f"💰 Кошелёк: <b>{bal:.0f} ₽</b> · потрачено {spent:.0f} ₽")
                    tail = token[-6:]
                    if st.get("autotopup"):
                        lines.append(
                            f"🔄 Автопополнение вкл · +{int(st.get('topup_amount_rub', 0))} ₽ "
                            f"при остатке ниже {int(st.get('low_watermark_rub', 0))} ₽")
                        kb.append([{"text": "⏸ Выключить автопополнение",
                                    "callback_data": f"pp:auto0:{tail}"}])
                    else:
                        lines.append("⏸ Автопополнение выключено")
                        if self._user_payment_method(user_id):
                            kb.append([{"text": "🔄 Включить автопополнение",
                                        "callback_data": f"pp:auto1:{tail}"}])
                        else:
                            lines.append("💡 Привяжите карту (оплатите тариф картой) — "
                                         "тогда доступ не прервётся сам.")
                    if st.get("topup_needed"):
                        lines.append("⚠️ Баланс на исходе — пополните или включите автопополнение")
                    kb.append([{"text": "💳 Пополнить кошелёк",
                                "callback_data": f"pp:top:{tail}"}])
                else:
                    left = st.get("tokens_left", 0) / 1_000_000
                    lines.append(f"📊 Осталось: <b>{left:.2f} млн токенов</b>")
                    # «Сколько РЕАЛЬНО потрачено» — по ЕГО цене, а не по закупке.
                    # Показываем только если ключ покупался (у выданного другу
                    # бесплатно price_rub=0 — не морочим человека нулями).
                    if int(st.get("price_rub", 0)) > 0:
                        spent = float(st.get("spent_rub", 0))
                        paid = int(st.get("price_rub", 0))
                        lines.append(f"💸 Потрачено: <b>{spent:.0f} ₽</b> из {paid} ₽")
                # Срок/остаток по времени — НЕ для потокенной оплаты: у неё
                # expires_at=0 (кошелёк не сгорает), иначе показали бы ложное
                # «♾ Без срока — токены не сгорают».
                if not st.get("postpaid"):
                    if st.get("seconds_left"):
                        secs = int(st["seconds_left"])
                        if secs > 86400:
                            lines.append(f"⏳ Ещё {secs // 86400} дн")
                        else:
                            lines.append(f"⏳ Ещё {secs // 3600} ч {(secs % 3600) // 60} мин")
                    elif not st.get("expires_at"):
                        lines.append("♾ Без срока — токены не сгорают")
                if not st.get("enabled"):
                    lines.append("⛔️ Приостановлен — напишите в поддержку")
                # Главная кнопка после покупки: довести клиента до рабочего
                # инструмента. Пока ключ не заработал у него — денег он больше
                # не принесёт, сколько бы тарифов мы ни показывали.
                kb.append([{"text": f"⚡️ Подключить · {st['title'][:18]}",
                            "callback_data": f"set:{token[-6:]}:menu"}])
        except ImportError:
            pass

        # 2) Подписки с автопродлением
        for sub in self.store.user_subscriptions(user_id):
            p = self.store.product(sub["product_id"]) or {}
            title = p.get("title", sub["product_id"])
            found = True
            lines.append(f"\n<b>{html.escape(title)}</b>\n{fmt_sub_status(sub)}")
            if int(sub.get("period_days", 0)) < 36500 and sub.get("payment_method_id"):
                if sub.get("autorenew"):
                    kb.append([{"text": f"⏸ Отключить продление · {title[:18]}",
                                "callback_data": f"ar0:{sub['product_id']}"}])
                else:
                    kb.append([{"text": f"🔄 Включить продление · {title[:18]}",
                                "callback_data": f"ar1:{sub['product_id']}"}])
                # На продлении клиент свободен: тот же тариф / другой пакет /
                # потокенная оплата. Выбор пишется в next_product_id, исполняет
                # его движок renewals в момент списания. Показываем текущий выбор.
                choice = str(sub.get("next_product_id") or "").strip()
                if choice == POSTPAID_CHOICE:
                    lines.append("🔧 На продлении → потокенная оплата")
                elif choice and choice != sub["product_id"]:
                    alt = self.store.product(choice) or {}
                    lines.append(f"🔧 На продлении → «{html.escape(alt.get('title', choice))}»")
                if self._id_manageable(sub["product_id"]):
                    kb.append([{"text": f"🔧 Что продлевать · {title[:16]}",
                                "callback_data": f"rc:{sub['product_id']}"}])

        if not found:
            body = ("<b>🔑 Мои ключи</b>\n\nУ вас пока нет активных ключей.\n\n"
                    "Выберите тариф в витрине — ключ придёт сразу после оплаты.")
            kb = [[{"text": "🛍 Выбрать тариф", "callback_data": "shop"}],
                  [{"text": "⬅️ Назад", "callback_data": "home"}]]
        else:
            dash = _client_dashboard()
            if dash:
                lines.append(f"\n📈 Кабинет с живым отсчётом: {dash}")
            # Привязанная карта: одна на пользователя, обслуживает и автопродление
            # подписок, и автопополнение потокенного кошелька. ЮKassa привязывает
            # карту только В МОМЕНТ оплаты, поэтому «привязать заранее» кнопки нет —
            # честно объясняем, что карта сохранится сама при первой оплате картой.
            card = self.store.card_on_file(user_id)
            if card:
                mask = html.escape(str(card.get("title") or "сохранена"))
                lines.append(f"\n💳 Карта: {mask}")
                kb.append([{"text": "🗑 Отвязать карту", "callback_data": "card:forget"}])
            elif self._user_payment_method(user_id):
                lines.append("\n💳 Карта сохранена (с оплаты подписки) — "
                             "хватит для автопродления и автопополнения.")
            else:
                lines.append("\n💳 Карта не привязана. Оплатите любой тариф картой — "
                             "сохранится сама, для автопродления и автосписания.")
            body = "\n".join(lines)
            kb.append([{"text": "🛍 Витрина", "callback_data": "shop"}])
            kb.append([{"text": "⬅️ Назад", "callback_data": "home"}])
        self._show(chat_id, message_id, body, kb)

    def render_setup(self, chat_id: int, message_id: int | None, user_id: int,
                     arg: str) -> None:
        """Автоподключение: готовый конфиг под инструмент клиента.

        arg = 'токен6:инструмент' — по последним 6 символам токена, чтобы
        callback_data влезал в лимит Telegram (64 байта) и полный ключ не
        болтался в истории нажатий.
        """
        try:
            from gateway.quota import QuotaStore
            from gateway.setup_kit import TOOLS, setup_payload
        except ImportError:
            self._show(chat_id, message_id, "Модуль подключения недоступен.",
                       [[{"text": "⬅️ Назад", "callback_data": "my"}]])
            return

        tail, _, tool = arg.partition(":")
        tool = tool or "menu"
        # Ключ ищем только среди СВОИХ — чужой токен по хвосту не достать.
        rec = next((k for k in QuotaStore(self.s.data_dir).keys_of_user(user_id)
                    if str(k.get("token", "")).endswith(tail)), None)
        if not rec:
            self._show(chat_id, message_id, "Ключ не найден.",
                       [[{"text": "⬅️ Назад", "callback_data": "my"}]])
            return

        kit = setup_payload(rec)
        back = [{"text": "⬅️ К ключам", "callback_data": "my"}]

        if tool == "menu":
            body = (f"<b>⚡️ Подключение за одну команду</b>\n\n"
                    f"Тариф: <b>{html.escape(str(rec.get('title', '')))}</b>\n"
                    f"Модель: <code>{kit['model']}</code>\n\n"
                    f"Выберите, где будете работать — пришлю готовый конфиг. "
                    f"Вписывать руками ничего не нужно.")
            kb = [[{"text": label, "callback_data": f"set:{tail}:{key}"}]
                  for key, label in TOOLS]
            kb.append(back)
            self._show(chat_id, message_id, body, kb)
            return

        blocks = {
            "curl": ("🧪 <b>Проверка доступа</b>\n\nВставьте в терминал — "
                     "в ответ придёт «ok». Если пришло, всё работает.",
                     kit["curl"]),
            "claude": ("✨ <b>Claude Code — одна команда</b>\n\nВставьте в терминал: "
                       "команда сама создаст лаунчер <code>~/.wave/start-claude.sh</code> "
                       "и запустит Claude Code через ваш доступ. В следующий раз "
                       "просто запускайте этот файл — ключ уже внутри.",
                       kit["claude_magic"]),
            "cursor": ("🖥 <b>Cursor</b>\n\nПять шагов в настройках:", kit["cursor_steps"]),
            "continue": ("🧩 <b>Continue</b>\n\nОдна команда — конфиг встанет сам "
                         "в <code>~/.continue/config.json</code>:", kit["install_continue"]),
            "cline": ("🤖 <b>Cline / Roo Code</b>\n\nВставьте в настройки провайдера:",
                      kit["cline_json"]),
            "env": ("📄 <b>Файл .env</b>\n\nОдна команда в папке проекта:",
                    kit["install_env"]),
            "shell": ("🐚 <b>Переменные окружения</b>\n\nОдна команда, потом "
                      "<code>source ~/.zshrc</code>:", kit["install_shell"]),
            "python": ("🐍 <b>Python</b>\n\nГотовый рабочий пример:", kit["python"]),
            "js": ("🟨 <b>JavaScript</b>\n\nГотовый рабочий пример:", kit["js"]),
        }
        head, code = blocks.get(tool, blocks["curl"])
        body = f"{head}\n\n<pre>{html.escape(code)}</pre>"
        kb = [[{"text": "⬅️ Другой инструмент", "callback_data": f"set:{tail}:menu"}], back]
        self._show(chat_id, message_id, body, kb)

    def toggle_autorenew(self, chat_id: int, message_id: int, user_id: int,
                         product_id: str, on: bool) -> None:
        sub = self.store.set_autorenew(user_id, product_id, on)
        if sub and not on:
            # Честно: оплаченный срок остаётся до конца
            until = time.strftime("%d.%m.%Y", time.localtime(int(sub["paid_until"])))
            self.api.send_message(
                chat_id,
                f"⏸ Автопродление отключено.\n\n"
                f"Доступ остаётся активным до <b>{until}</b> — оплаченные дни не сгорают.")
        elif sub and on:
            self.api.send_message(chat_id, "🔄 Автопродление включено. Спишем перед окончанием срока.")
        self.render_my_subs(chat_id, message_id, user_id)

    # ---------- Потокенная оплата: кошелёк, автопополнение, ручное пополнение ----------
    _TOPUP_AMOUNTS_RUB = (300, 500, 1000)

    def _user_payment_method(self, user_id: int) -> str:
        """payment_method_id пользователя или "" — ТОЧНАЯ копия renewals._card_for_user.

        Кабинет обязан «видеть» карту ровно так же, как движки автопродления и
        автопополнения: сперва явная card_on_file, иначе — карта самой свежей
        подписки. Иначе кнопка «включить автопополнение» и реальная способность
        списать разошлись бы (показали бы кнопку без карты — или спрятали при
        живой карте из подписки). Логику дублируем намеренно: бот не тянет
        renewals как зависимость, и правка одного не должна ломать другой.
        """
        card = self.store.card_on_file(user_id)
        if card and card.get("payment_method_id"):
            return str(card["payment_method_id"])
        subs = [s for s in self.store.user_subscriptions(user_id)
                if s.get("payment_method_id")]
        if not subs:
            return ""
        newest = max(subs, key=lambda s: int(s.get("updated_at",
                                                   s.get("created_at", 0))))
        return str(newest.get("payment_method_id", ""))

    def _postpaid_key_by_tail(self, user_id: int, tail: str):
        """Свой ПОСТОПЛАТНЫЙ ключ по последним 6 символам токена → (QuotaStore, rec).

        Ищем только среди СВОИХ ключей (как render_setup) — чужой токен по хвосту
        не достать. (None, None), если модуль недоступен или ключа нет.
        """
        try:
            from gateway.quota import QuotaStore
        except ImportError:
            return None, None
        gq = QuotaStore(self.s.data_dir)
        for rec in gq.keys_of_user(user_id):
            if str(rec.get("token", "")).endswith(tail) and rec.get("kind") == "postpaid":
                return gq, rec
        return None, None

    def _handle_postpaid_callback(self, chat_id: int, message_id: int,
                                  user_id: int, rest: str) -> None:
        """pp:* — вход в пополнение (top) и переключение автопополнения (auto0/auto1)."""
        action, _, tail = rest.partition(":")
        if action == "top":
            self.render_postpaid_topup(chat_id, message_id, user_id, tail)
            return
        gq, rec = self._postpaid_key_by_tail(user_id, tail)
        if not gq or not rec:
            self.render_my_subs(chat_id, message_id, user_id)
            return
        token = rec["token"]
        if action == "auto1":
            # Включать автосписание можно ТОЛЬКО при живой карте — иначе обещали бы
            # списание, которое нечем исполнить (движок всё равно выключит его при
            # первом же пороге). Честнее не дать включить и объяснить, почему.
            if not self._user_payment_method(user_id):
                self.api.send_message(
                    chat_id,
                    "💳 Чтобы включить автопополнение, сначала привяжите карту — "
                    "оплатите любой тариф картой, она сохранится сама.")
                self.render_my_subs(chat_id, message_id, user_id)
                return
            gq.set_autotopup(token, True)
            self.api.send_message(
                chat_id, "🔄 Автопополнение включено. Когда баланс подойдёт к концу, "
                         "пополним с привязанной карты — доступ не прервётся.")
        elif action == "auto0":
            gq.set_autotopup(token, False)
            self.api.send_message(
                chat_id, "⏸ Автопополнение выключено. Баланс тратится как есть; "
                         "когда закончится — пополните вручную.")
        self.render_my_subs(chat_id, message_id, user_id)

    def render_postpaid_topup(self, chat_id: int, message_id: int,
                              user_id: int, tail: str) -> None:
        """Экран ручного пополнения кошелька: выбрать сумму → выставить счёт."""
        gq, rec = self._postpaid_key_by_tail(user_id, tail)
        if not gq or not rec:
            self.render_my_subs(chat_id, message_id, user_id)
            return
        if not self.providers:
            self._show(chat_id, message_id,
                       "Приём оплаты ещё не настроен. Поддержка: "
                       + html.escape(self.s.support_contact),
                       [[{"text": "⬅️ К ключам", "callback_data": "my"}]])
            return
        st = gq.status(rec["token"]) or {}
        bal = float(st.get("balance_rub", 0.0))
        body = (f"<b>💳 Пополнить кошелёк</b>\n\n"
                f"Текущий баланс: <b>{bal:.0f} ₽</b>\n\n"
                f"Выберите сумму — спишем с карты и зачислим в кошелёк. "
                f"Дальше тратится по факту, по нашему тарифу.")
        kb = [[{"text": f"{amt} ₽", "callback_data": f"pptop:{tail}:{amt}"}]
              for amt in self._TOPUP_AMOUNTS_RUB]
        kb.append([{"text": "⬅️ К ключам", "callback_data": "my"}])
        self._show(chat_id, message_id, body, kb)

    def start_postpaid_topup(self, chat_id: int, user_id: int,
                             tail: str, amount_rub: int) -> None:
        """Создать заказ на пополнение и выставить счёт. RUBICON-safe.

        Отдельный от покупки товара путь: заказ помечен product_id='postpaid_topup'
        и обычная выдача (deliver) по нему НЕ вызывается — на подтверждении оплаты
        кошелёк пополняет check_topup_payment. Пополнять можно только картой
        (ЮKassa): Stars/крипта не дают payment_method_id и не ложатся в модель.
        """
        gq, rec = self._postpaid_key_by_tail(user_id, tail)
        if not gq or not rec:
            self.render_my_subs(chat_id, None, user_id)
            return
        amount = int(amount_rub)
        if amount not in self._TOPUP_AMOUNTS_RUB:
            return
        prov = None
        provider_key = ""
        for key, p in self.providers.items():
            if key.startswith("yookassa"):
                prov, provider_key = p, key
                break
        if prov is None:
            self.api.send_message(
                chat_id, "Пополнение кошелька доступно только картой (ЮKassa), "
                         "а она сейчас не настроена. Поддержка: "
                         + html.escape(self.s.support_contact))
            return
        order = self.store.create_order(user_id, "postpaid_topup", provider_key, amount)
        # Токен кошелька кладём на заказ — check_topup_payment зачислит именно на
        # него. save_card=True: заодно сохранит карту для будущего автопополнения.
        self.store.update_order(order["order_id"], topup_token=rec["token"], save_card=True)
        synthetic = {"id": "postpaid_topup", "title": "Пополнение кошелька WAVE",
                     "description": "Пополнение потокенного баланса", "price_rub": amount}
        charge = prov.create_charge(order, synthetic)
        if not charge.ok:
            self.api.send_message(chat_id, "⚠️ " + (charge.message or "Не удалось создать оплату."))
            return
        if charge.method == "url":
            self.store.update_order(order["order_id"], external_ref=charge.external_id)
            hint = f"\n\n💡 {prov.hint}" if getattr(prov, "hint", "") else ""
            kb = [[{"text": "💳 Перейти к оплате", "url": charge.pay_url}],
                  [{"text": "✅ Я оплатил", "callback_data": f"ppchk:{order['order_id']}"}]]
            self.api.send_message(
                chat_id, f"Счёт на пополнение <b>{amount} ₽</b> создан. "
                         f"Оплатите и вернитесь сюда:{hint}", kb)
        else:
            self.api.send_message(
                chat_id, "Этот способ не подходит для пополнения кошелька — нужна карта (ЮKassa).")

    def check_topup_payment(self, chat_id: int, user_id: int, order_id: str) -> None:
        """«Я оплатил» для пополнения кошелька. Параллельно deliver(), не трогает его.

        Порядок намеренный: verify → пометить заказ delivered (защита от повторного
        зачисления при повторном нажатии) → gq.topup + LEDGER. Если между delivered
        и topup случится сбой — деньги подтверждены, но не зачислены: это чинит
        поддержка. Обратный порядок дал бы ДВОЙНОЕ зачисление на краш — потерю
        нашей маржи, что хуже. Бот однопоточный, окно между шагами микроскопическое.
        """
        order = self.store.get_order(order_id)
        if not order or order.get("user_id") != user_id:
            return
        if order.get("product_id") != "postpaid_topup":
            return
        if order.get("status") == "delivered":
            self.api.send_message(chat_id, "Это пополнение уже зачислено — смотрите баланс в «Мои ключи».")
            return
        prov = self.providers.get(order.get("provider", ""))
        if prov is None:
            return
        if not prov.verify(order.get("external_ref", "")):
            self.api.send_message(chat_id, "Оплата пока не видна. Если оплатили — подождите минуту и нажмите ещё раз.")
            return
        token = str(order.get("topup_token", ""))
        try:
            from gateway.quota import QuotaStore
            gq = QuotaStore(self.s.data_dir)
        except ImportError:
            gq = None
        rec = gq.get_key(token) if (gq and token) else None
        # Ключ должен быть свой и постоплатный — иначе зачислять некуда.
        if not gq or not rec or rec.get("user_id") != user_id or rec.get("kind") != "postpaid":
            self.api.send_message(chat_id, "⚠️ Не нашли кошелёк для зачисления. Поддержка: "
                                  + html.escape(self.s.support_contact))
            return
        amount = int(order.get("amount_rub", 0))
        # ДЕНЬГИ ПОДТВЕРЖДЕНЫ. Сначала фиксируем факт (delivered) — повторное
        # нажатие сюда уже не дойдёт, второго зачисления не будет.
        self.store.update_order(order_id, status="delivered", delivered_at=int(time.time()))
        # Карта на файл (если ЮKassa сохранила) — для будущего автопополнения.
        if order.get("save_card"):
            try:
                pm_id = prov.fetch_payment_method(order.get("external_ref", ""))
            except Exception:
                pm_id = ""
            if pm_id:
                self.store.update_order(order_id, payment_method_id=pm_id)
                try:
                    self.store.set_card_on_file(
                        user_id, pm_id, provider=order.get("provider", "yookassa"))
                except Exception:
                    pass
        updated = gq.topup(token, amount)
        self.store.record_revenue(order_id, user_id, "postpaid", order.get("provider", ""),
                                  amount, external_ref=order.get("external_ref", ""))
        bal = round(float((updated or {}).get("deposit_rub", 0.0)), 2)
        self.api.send_message(
            chat_id, f"✅ <b>Кошелёк пополнен на {amount} ₽</b>\n\n"
                     f"Баланс: <b>{bal:.0f} ₽</b>\n"
                     f"Тратится по факту — только за использованные токены.",
            [[{"text": "🔑 Мои ключи", "callback_data": "my"}]])

    # ---------- Выбор «чем продлевать»: тот же / другой пакет / потокенно ----------
    def render_renewal_choice(self, chat_id: int, message_id: int,
                              user_id: int, product_id: str) -> None:
        """Экран выбора, чем списывать на следующем продлении. Только запись выбора.

        Обещание клиенту: на продлении он свободен — тот же тариф, любой другой
        пакет или вообще без пакета (потокенная оплата по факту). Выбор пишем в
        subscription.next_product_id; исполнит его движок renewals в момент списания.
        """
        sub = self.store.subscription(user_id, product_id)
        if not sub:
            self.render_my_subs(chat_id, message_id, user_id)
            return
        cur = self.store.product(product_id) or {}
        cur_title = cur.get("title", product_id)
        choice = str(sub.get("next_product_id") or "").strip()
        if choice == POSTPAID_CHOICE:
            now_line = "сейчас: 💧 потокенная оплата"
        elif choice and choice != product_id:
            alt = self.store.product(choice) or {}
            now_line = f"сейчас: 🔀 «{html.escape(alt.get('title', choice))}»"
        else:
            now_line = "сейчас: ✅ тот же тариф"
        body = (f"<b>🔧 Что продлевать</b>\n\n"
                f"Подписка: {html.escape(cur_title)}\n{now_line}\n\n"
                f"Выберите, чем списать на следующем продлении:")
        kb = [[{"text": "✅ Тот же тариф", "callback_data": f"rcx:s:{product_id}"}]]
        # Другие повторяющиеся тарифы шлюза — «сменить пакет».
        for p in self.store.catalog(only_active=True):
            pid = p.get("id", "")
            if pid == product_id or not self._is_recurring(p):
                continue
            cb = f"rcx:o:{product_id}:{pid}"
            if len(cb.encode("utf-8")) > 64:
                continue  # не влезает в callback Telegram — не рисуем мёртвую кнопку
            kb.append([{"text": f"🔀 {p.get('title', pid)[:22]} · {fmt_price(p, self.s)}",
                        "callback_data": cb}])
        kb.append([{"text": "💧 Потокенная оплата (по факту)",
                    "callback_data": f"rcx:p:{product_id}"}])
        kb.append([{"text": "⬅️ К ключам", "callback_data": "my"}])
        self._show(chat_id, message_id, body, kb)

    def _apply_renewal_choice(self, chat_id: int, message_id: int,
                              user_id: int, rest: str) -> None:
        """Записать выбор в next_product_id. rest = 's:{pid}' | 'p:{pid}' | 'o:{pid}:{other}'."""
        mode, _, tail = rest.partition(":")
        if mode == "o":
            product_id, _, other_id = tail.partition(":")
            target = self.store.product(other_id)
            if not target or not self._is_recurring(target):
                # Выбранный пакет исчез/не повторяющийся — не пишем кривой выбор.
                self.api.send_message(chat_id, "Этот пакет больше недоступен для продления.")
                self.render_renewal_choice(chat_id, message_id, user_id, product_id)
                return
            new_choice = other_id
        else:
            product_id = tail
            new_choice = POSTPAID_CHOICE if mode == "p" else ""
        updated = self.store.mark_sub_field(user_id, product_id, next_product_id=new_choice)
        if updated is None:
            self.render_my_subs(chat_id, message_id, user_id)
            return
        if new_choice == POSTPAID_CHOICE:
            msg = ("💧 На продлении перейдём на потокенную оплату: спишем стартовый "
                   "баланс, дальше — только за использованные токены, по нашему тарифу. "
                   "Ключ доступа не изменится.")
        elif new_choice:
            alt = self.store.product(new_choice) or {}
            msg = (f"🔀 На продлении сменим тариф на «{html.escape(alt.get('title', new_choice))}». "
                   f"Ключ доступа не изменится.")
        else:
            msg = "✅ На продлении спишем тот же тариф — ничего не изменится."
        self.api.send_message(chat_id, msg)
        self.render_my_subs(chat_id, message_id, user_id)

    def forget_card_cmd(self, chat_id: int, message_id: int, user_id: int) -> None:
        """Отвязать сохранённую карту (card_on_file). Честно про подписки.

        Отвязка снимает только явную card_on_file. Подписка с автопродлением
        продолжит списываться со СВОЕЙ payment_method_id (карта живёт и на ней) —
        предупреждаем, без ложного «карта удалена везде».
        """
        had = self.store.forget_card(user_id)
        if had:
            self.api.send_message(
                chat_id, "🗑 Карта отвязана. Автопополнение потокенного тарифа "
                         "выключится при следующей проверке.\n\n"
                         "⚠️ Если есть подписка с автопродлением, она продолжит "
                         "списываться со своей карты — отключите продление в списке ключей.")
        else:
            self.api.send_message(chat_id, "Привязанной карты и не было.")
        self.render_my_subs(chat_id, message_id, user_id)

    # ---------- Платёжный поток ----------
    def grant_free(self, chat_id: int, message_id: int | None,
                   product_id: str, user_id: int) -> None:
        """Выдать бесплатный тариф (демо) без кассы.

        Заказ создаётся с провайдером 'free' и суммой 0 — так бесплатная выдача
        видна в истории, но не подмешивает нулей в выручку.
        """
        p = self.store.product(product_id)
        if not p:
            return
        user = self.store.get_or_create_user(user_id)
        order = self.store.create_order(user_id, product_id, "free", 0,
                                        ref_by=user.get("ref_by", ""))
        self.core.mark_paid(order["order_id"])
        ok, payload = self.core.deliver(order["order_id"])
        head = "✅ <b>Доступ выдан</b>\n\n" if ok else "⚠️ "
        kb = [[{"text": "🔑 Мои ключи", "callback_data": "my"}],
              [{"text": "🛍 Витрина", "callback_data": "shop"}]]
        if ok:
            token = self._token_of_order(order["order_id"])
            if token:
                kb.insert(0, [{"text": "⚡️ Подключить за минуту",
                               "callback_data": f"set:{token[-6:]}:menu"}])
        self._show(chat_id, message_id, head + payload, kb)

    def start_payment(self, chat_id: int, user_id: int, provider_key: str, product_id: str) -> None:
        p = self.store.product(product_id)
        prov = self.providers.get(provider_key)
        if not p or not prov:
            return
        user = self.store.get_or_create_user(user_id)
        order = self.store.create_order(user_id, product_id, provider_key,
                                        int(p.get("price_rub", 0)), ref_by=user.get("ref_by", ""))

        # Повторяющийся тариф + ЮKassa → просим сохранить карту для автопродления.
        # Раньше этот флаг вычислялся, но никуда не передавался: карта не
        # сохранялась, и подписка была разовой покупкой под именем подписки.
        save_card = self._is_recurring(p) and provider_key.startswith("yookassa")
        if save_card:
            order = self.store.update_order(order["order_id"], save_card=True) or order

        charge = prov.create_charge(order, p)
        if not charge.ok:
            self.api.send_message(chat_id, "⚠️ " + (charge.message or "Не удалось создать оплату."))
            return

        if charge.method == "stars":
            self.api.send_invoice(
                chat_id, title=p.get("title", "Товар"),
                description=(p.get("description") or "Цифровой товар")[:255],
                payload=order["order_id"], currency="XTR",
                prices=[{"label": p.get("title", "Товар"), "amount": charge.stars_amount}],
            )
        elif charge.method == "url":
            self.store.update_order(order["order_id"], external_ref=charge.external_id)
            hint = f"\n\n💡 {prov.hint}" if prov.hint else ""
            if save_card:
                hint += ("\n\n🔄 Карта сохранится для автопродления. "
                         "Отключить можно одной кнопкой в «Мои ключи».")
            kb = [[{"text": "💳 Перейти к оплате", "url": charge.pay_url}],
                  [{"text": "✅ Я оплатил", "callback_data": f"chk:{order['order_id']}"}]]
            self.api.send_message(chat_id, f"Счёт создан. Оплатите и вернитесь сюда:{hint}", kb)
        elif charge.method == "manual":
            kb = [[{"text": "✅ Я оплатил", "callback_data": f"chk:{order['order_id']}"}]]
            self.api.send_message(chat_id, charge.message, kb)

    @staticmethod
    def _is_recurring(product: dict) -> bool:
        """Тариф с повторяющимся списанием (подписка или безлимит)."""
        try:
            from gateway.quota import get_plan
        except ImportError:
            return (product.get("kind") == "subscription"
                    and int(product.get("period_days", 0)) > 0)
        plan = get_plan(product.get("plan_id", product.get("id", "")))
        if plan:
            return plan["kind"] in {"subscription", "unlimited"}
        return (product.get("kind") == "subscription"
                and int(product.get("period_days", 0)) > 0)

    def check_payment(self, chat_id: int, user_id: int, order_id: str) -> None:
        """Кнопка «Я оплатил» для url/manual-провайдеров."""
        order = self.store.get_order(order_id)
        if not order or order.get("user_id") != user_id:
            return
        if order.get("status") == "delivered":
            self.api.send_message(chat_id, "Этот заказ уже выдан — смотрите «Мои заказы».")
            return
        prov = self.providers.get(order.get("provider", ""))
        if prov is None:
            return
        if order.get("provider") == "manual":
            self._notify_admins(f"🧾 Ручная оплата ждёт подтверждения.\nЗаказ: <code>{order_id}</code>\n"
                                f"Клиент: {user_id}\nСумма: {order.get('amount_rub')} ₽\n\n"
                                f"Подтвердить: <code>/confirm {order_id}</code>")
            self.api.send_message(chat_id, "Заявка отправлена оператору. Как подтвердит — товар придёт сюда.")
            return
        if prov.verify(order.get("external_ref", "")):
            # Забрать «привязанную карту» ДО выдачи: _register_subscription
            # читает payment_method_id с заказа, и без этого шага автопродление
            # никогда не включится.
            if order.get("save_card"):
                try:
                    pm_id = prov.fetch_payment_method(order.get("external_ref", ""))
                except Exception:
                    pm_id = ""
                if pm_id:
                    self.store.update_order(order_id, payment_method_id=pm_id)
                    # Плюс кладём карту на файл пользователя (одна карта на все его
                    # подписки и потокенный кошелёк). Движки автопродления и
                    # автопополнения читают card_on_file первым делом — без этого
                    # автосписание потокенного тарифа было бы нечем исполнить.
                    try:
                        self.store.set_card_on_file(
                            user_id, pm_id, provider=order.get("provider", "yookassa"))
                    except Exception:
                        pass
            self.core.mark_paid(order_id, order.get("external_ref", ""))
            self._fulfill_and_send(chat_id, order_id)
        else:
            self.api.send_message(chat_id, "Оплата пока не видна. Если оплатили — подождите минуту и нажмите ещё раз.")

    def _fulfill_and_send(self, chat_id: int, order_id: str) -> None:
        ok, payload = self.core.deliver(order_id)
        if ok:
            order = self.store.get_order(order_id) or {}
            product = self.store.product(order.get("product_id", "")) or {}
            kb = [[{"text": "🛍 Ещё покупки", "callback_data": "shop"}]]

            # Тариф шлюза отдаёт УЖЕ размеченный HTML (жирный заголовок, ключ в
            # <code>). Экранировать его нельзя — клиент увидел бы сырые теги
            # вместо ключа. Складской товар, наоборот, обычная строка.
            if product.get("kind") in {"gateway", "subscription", "lifetime"}:
                body = f"✅ <b>Оплачено</b>\n\n{payload}"
                token = self._token_of_order(order_id)
                if token:
                    kb.insert(0, [{"text": "⚡️ Подключить за минуту",
                                   "callback_data": f"set:{token[-6:]}:menu"}])
            else:
                body = (f"✅ <b>Оплачено. Ваш товар:</b>\n\n"
                        f"<code>{html.escape(payload)}</code>\n\n"
                        f"Спасибо за покупку в {html.escape(self.s.shop_name)}! 🌊")

            self.api.send_message(chat_id, body, kb)
            self._notify_admins(f"💸 Продажа: {order.get('amount_rub')} ₽ · "
                                f"{order.get('product_id')} · {order.get('provider')}")
        else:
            self.api.send_message(chat_id, "⚠️ " + payload +
                                  "\nПоддержка: " + html.escape(self.s.support_contact))
            self._notify_admins(f"⚠️ Сбой выдачи по заказу {order_id}: {payload}")

    def _token_of_order(self, order_id: str) -> str:
        """Токен, выданный по этому заказу (для кнопки подключения)."""
        try:
            from gateway.quota import QuotaStore
        except ImportError:
            return ""
        keys = QuotaStore(self.s.data_dir)
        for rec in keys.keys_of_user((self.store.get_order(order_id) or {}).get("user_id", 0)):
            if rec.get("order_id") == order_id:
                return str(rec.get("token", ""))
        return ""

    # ---------- Админка ----------
    def _is_admin(self, user_id: int) -> bool:
        return user_id in self.s.admin_ids

    @staticmethod
    def _id_manageable(product_id: str) -> bool:
        """Влезает ли id в callback_data всех кнопок карточки.

        Худший префикс — «adm:delok:» (10 байт). Лимит Telegram — 64 байта,
        значит id должен быть ≤54 байт. Сгенерированные id (ASCII, ≤25 симв.)
        всегда проходят; проверка ловит только руками вписанные длинные/
        кириллические id, по которым кнопки молча не сработали бы.
        """
        return len(f"adm:delok:{product_id}".encode("utf-8")) <= 64

    def admin_command(self, chat_id: int, user_id: int, text: str) -> bool:
        """Обработать админ-команду. True если команда распознана."""
        if not self._is_admin(user_id):
            return False
        parts = text.strip().split(maxsplit=2)
        cmd = parts[0].lower()

        if cmd == "/admin":
            # /admin — всегда чистый вход в панель: если оператор застрял в
            # мастере, сбрасываем состояние, иначе следующий ввод улетит туда.
            self._admin_state.pop(user_id, None)
            self.render_admin(chat_id, None)
            return True

        if cmd == "/cancel":
            if self._admin_state.pop(user_id, None) is not None:
                self.api.send_message(chat_id, "Отменено.", self._home_kb())
            return True

        if cmd == "/stock" and len(parts) >= 3:
            product_id, payloads_raw = parts[1], parts[2]
            if not self.store.product(product_id):
                self.api.send_message(chat_id, f"Товар <code>{html.escape(product_id)}</code> не найден.")
                return True
            items = [x.strip() for x in payloads_raw.replace("\n", ",").split(",") if x.strip()]
            total = self.store.add_stock(product_id, items)
            self.api.send_message(chat_id, f"✅ Добавлено {len(items)}. На складе: <b>{total}</b>.")
            return True

        if cmd == "/confirm" and len(parts) >= 2:
            order_id = parts[1]
            order = self.store.get_order(order_id)
            if not order:
                self.api.send_message(chat_id, "Заказ не найден.")
                return True
            self.core.mark_paid(order_id)
            self._fulfill_and_send(order["user_id"], order_id)
            self.api.send_message(chat_id, f"✅ Заказ {order_id} подтверждён и выдан.")
            return True

        return False

    # ---------- Админ-панель: управление магазином из бота ----------
    def render_admin(self, chat_id: int, message_id: int | None) -> None:
        rev = self.store.revenue_total()
        active = len(self.store.catalog(only_active=True))
        total = len(self.store.catalog(only_active=False))
        text = (f"<b>⚙️ Управление · {html.escape(self.s.shop_name)}</b>\n\n"
                f"Выручка: <b>{rev['rub_total']:,} ₽</b> · {rev['orders']} продаж\n".replace(",", " ") +
                f"Товаров: <b>{active}</b> на витрине из {total}\n"
                f"Кассы: {', '.join(self.providers) or '⛔️ нет'}\n\n"
                f"Отсюда управляешь всем — без правки файлов.")
        kb = [
            [{"text": "🛍 Товары", "callback_data": "adm:products"}],
            [{"text": "➕ Добавить товар", "callback_data": "adm:add"}],
            [{"text": "💰 Выручка и заказы", "callback_data": "adm:rev"},
             {"text": "⚙️ Кассы", "callback_data": "adm:cassa"}],
            [{"text": "🏠 На витрину", "callback_data": "home"}],
        ]
        self._show(chat_id, message_id, text, kb)

    def render_admin_products(self, chat_id: int, message_id: int | None) -> None:
        items = self.store.catalog(only_active=False)
        if not items:
            body = "<b>🛍 Товары</b>\n\nПока пусто. Нажми «Добавить товар»."
        else:
            body = "<b>🛍 Товары</b>\n\n✅ на витрине · ⛔️ скрыт. Нажми на товар для управления."
        kb = []
        overlong: list[str] = []
        for p in items:
            on = p.get("active", True)
            mark = "✅" if on else "⛔️"
            pid = p["id"]
            if not self._id_manageable(pid):
                # Кнопки по такому id Telegram молча отбросит (>64 байт в
                # callback_data). Честно говорим оператору, а не даём мёртвую
                # кнопку. Сгенерированные id всегда влезают — это ручная правка.
                overlong.append(pid)
                continue
            kb.append([{"text": f"{mark} {p.get('title','Товар')} — {fmt_price(p, self.s)}",
                        "callback_data": f"adm:p:{pid}"}])
        if overlong:
            body += ("\n\n⚠️ Не помещаются в кнопки (id длиннее 54 байт) — "
                     "переименуй короче/латиницей в <code>data/catalog.json</code>:\n"
                     + "\n".join(f"• <code>{html.escape(x)}</code>" for x in overlong))
        kb.append([{"text": "➕ Добавить товар", "callback_data": "adm:add"}])
        kb.append([{"text": "⬅️ Назад", "callback_data": "adm:home"}])
        self._show(chat_id, message_id, body, kb)

    def render_admin_product(self, chat_id: int, message_id: int | None, product_id: str) -> None:
        p = self.store.product(product_id)
        if not p:
            self.render_admin_products(chat_id, message_id)
            return
        on = p.get("active", True)
        kind = p.get("kind", "key")
        lines = [f"<b>{html.escape(p.get('title','Товар'))}</b>",
                 f"<code>{html.escape(product_id)}</code>", "",
                 html.escape(p.get("description", "") or "—"), "",
                 f"Цена: <b>{fmt_price(p, self.s)}</b>",
                 f"Тип: {kind}",
                 f"Состояние: {'✅ на витрине' if on else '⛔️ скрыт'}"]
        if needs_stock(p):
            lines.append(f"Склад: <b>{self.store.stock_count(product_id)}</b> шт.")
        kb = [
            [{"text": "⛔️ Скрыть с витрины" if on else "✅ Показать на витрине",
              "callback_data": f"adm:tgl:{product_id}"}],
            [{"text": "💵 Изменить цену", "callback_data": f"adm:price:{product_id}"}],
        ]
        if needs_stock(p):
            kb.append([{"text": "📦 Добавить ключи на склад", "callback_data": f"adm:stock:{product_id}"}])
        elif kind == "lifetime":
            # «Изменить выдачу» правит lifetime_payload — его читает только
            # kind='lifetime'. Для gateway/subscription кнопка была бы обманом:
            # текст сохранился бы, но покупатель получил бы не его.
            kb.append([{"text": "✏️ Изменить выдачу (текст/ссылку)", "callback_data": f"adm:pay:{product_id}"}])
        kb.append([{"text": "🗑 Удалить товар", "callback_data": f"adm:del:{product_id}"}])
        kb.append([{"text": "⬅️ К товарам", "callback_data": "adm:products"}])
        self._show(chat_id, message_id, "\n".join(lines), kb)

    def render_admin_revenue(self, chat_id: int, message_id: int | None) -> None:
        rev = self.store.revenue_total()
        orders = sorted(self._all_orders(), key=lambda o: o.get("created_at", 0), reverse=True)
        # Продажа = доставленный заказ (в этот момент пишется LEDGER). 'paid' —
        # промежуточный/«оплачено, но выдача не прошла» — в выручку не идёт,
        # поэтому и в списке продаж ему не место.
        paid = [o for o in orders if o.get("status") == "delivered"]
        lines = [f"<b>💰 Выручка</b>\n",
                 f"Всего: <b>{rev['rub_total']:,} ₽</b> · {rev['orders']} продаж".replace(",", " "), ""]
        if paid:
            lines.append("<b>Последние продажи:</b>")
            for o in paid[:10]:
                when = time.strftime('%d.%m %H:%M', time.localtime(o.get("created_at", 0)))
                lines.append(f"• {o.get('amount_rub',0)} ₽ · {html.escape(str(o.get('product_id','')))} · {when}")
        else:
            lines.append("Продаж пока нет.")
        kb = [[{"text": "⬅️ Назад", "callback_data": "adm:home"}]]
        self._show(chat_id, message_id, "\n".join(lines), kb)

    def render_admin_cassa(self, chat_id: int, message_id: int | None) -> None:
        on = set(self.providers)
        rows = [("stars", "Telegram Stars ⭐", "работает без реквизитов"),
                ("yookassa", "ЮKassa 💳", "нужен ИП/самозанятость + ключи в .env"),
                ("crypto", "Крипта 🪙 (CryptoBot)", "нужен WAVE_CRYPTO_PAY_TOKEN в .env"),
                ("manual", "Ручная оплата 🧾", "перевод по реквизитам + /confirm")]
        lines = ["<b>⚙️ Кассы</b>\n"]
        for key, name, note in rows:
            mark = "✅" if key in on else "○"
            lines.append(f"{mark} <b>{name}</b> — {note}")
        lines += ["", "Касса включается ключами в <code>.env</code> и перезапуском."]
        kb = [[{"text": "⬅️ Назад", "callback_data": "adm:home"}]]
        self._show(chat_id, message_id, "\n".join(lines), kb)

    # ----- Мастер добавления товара (пошаговый диалог) -----
    _ADD_STEPS_HELP = "В любой момент: /cancel — отменить."

    def _admin_start_add(self, chat_id: int, user_id: int) -> None:
        self._admin_state[user_id] = {"step": "title", "draft": {}}
        self.api.send_message(
            chat_id,
            "<b>➕ Новый товар</b>\n\nШаг 1/5. Пришли <b>название</b> товара.\n\n"
            + self._ADD_STEPS_HELP)

    def _gen_product_id(self, title: str) -> str:
        # ASCII-безопасный slug: кириллица/эмодзи в id раздули бы callback_data
        # (лимит Telegram — 64 байта), поэтому оставляем только латиницу и цифры.
        base = "".join(ch if (ch.isascii() and ch.isalnum()) else "_" for ch in title.lower())
        base = "_".join(filter(None, base.split("_")))[:20] or "item"
        pid = f"{base}_{secrets.token_hex(2)}"
        while self.store.product(pid):
            pid = f"{base}_{secrets.token_hex(2)}"
        return pid

    # Разумный потолок цены: 100 млн ₽. Выше — почти наверняка опечатка или
    # мусор; заодно защита от OverflowError на строке из сотен цифр.
    _MAX_PRICE_RUB = 100_000_000

    @staticmethod
    def _parse_int(text: str) -> int | None:
        """Разобрать цену в рублях из свободного ввода.

        Понимает «550», «1 600», «1 600,50 ₽». Десятичную часть округляет до
        целого рубля (Stars и витрина считают в целых). Ввод-команда (с «/») и
        мусор без цифр отвергаются. Сверху ограничено _MAX_PRICE_RUB — иначе
        строка из сотен цифр дала бы OverflowError, а «100050» из «1 600,50»
        обернулось бы 100-кратной переплатой.
        """
        t = text.strip()
        if not t or t.startswith("/"):
            return None
        # Нормализуем: неразрывный/обычный пробел — разделитель тысяч, убираем;
        # запятая — десятичный разделитель (RU-локаль) → точка.
        t = t.replace(" ", "").replace(" ", "").replace(",", ".")
        # Оставляем только цифры и первую десятичную точку.
        cleaned: list[str] = []
        seen_dot = False
        for ch in t:
            if ch.isdigit():
                cleaned.append(ch)
            elif ch == "." and not seen_dot:
                cleaned.append(ch)
                seen_dot = True
        s = "".join(cleaned).strip(".")
        if not any(ch.isdigit() for ch in s):
            return None
        try:
            val = round(float(s))
        except (ValueError, OverflowError):
            return None
        if val < 0:
            return None
        return min(val, ShopBot._MAX_PRICE_RUB)

    def _admin_wizard_input(self, chat_id: int, user_id: int, text: str) -> None:
        """Один шаг мастера. Состояние в self._admin_state[user_id]."""
        st = self._admin_state.get(user_id)
        if not st:
            return
        step = st["step"]
        draft = st["draft"]

        # Отдельная ветка: правка цены/выдачи существующего товара.
        if step == "edit_price":
            val = self._parse_int(text)
            if val is None:
                self.api.send_message(chat_id, "Нужно число, например <code>550</code>. Ещё раз или /cancel.")
                return
            stars = max(1, round(val / 16.6)) if val > 0 else 0
            updated = self.store.set_price(st["product_id"], price_rub=val, stars_price=stars)
            self._admin_state.pop(user_id, None)
            if updated is None:
                self.api.send_message(chat_id, "⚠️ Товар не найден (удалён?). Правка отменена.")
                self.render_admin_products(chat_id, None)
                return
            self.api.send_message(chat_id, f"✅ Цена: <b>{val} ₽</b> / {stars} ⭐.")
            self.render_admin_product(chat_id, None, st["product_id"])
            return
        if step == "edit_payload":
            updated = self.store.set_payload(st["product_id"], text)
            self._admin_state.pop(user_id, None)
            if updated is None:
                self.api.send_message(chat_id, "⚠️ Товар не найден (удалён?). Правка отменена.")
                self.render_admin_products(chat_id, None)
                return
            self.api.send_message(chat_id, "✅ Выдача обновлена.")
            self.render_admin_product(chat_id, None, st["product_id"])
            return
        if step == "add_stock":
            items = [x.strip() for x in text.replace("\n", ",").split(",") if x.strip()]
            total = self.store.add_stock(st["product_id"], items)
            self._admin_state.pop(user_id, None)
            self.api.send_message(chat_id, f"✅ Добавлено {len(items)}. На складе: <b>{total}</b>.")
            self.render_admin_product(chat_id, None, st["product_id"])
            return

        # Мастер создания нового товара.
        if step == "title":
            draft["title"] = text[:80]
            st["step"] = "desc"
            self.api.send_message(chat_id, "Шаг 2/5. Пришли <b>описание</b> (что получит покупатель).\n"
                                           "Или «-» чтобы пропустить.")
            return
        if step == "desc":
            draft["description"] = "" if text.strip() == "-" else text[:900]
            st["step"] = "price"
            self.api.send_message(chat_id, "Шаг 3/5. Пришли <b>цену в рублях</b> (число). "
                                           "0 — если товар бесплатный.")
            return
        if step == "price":
            val = self._parse_int(text)
            if val is None:
                self.api.send_message(chat_id, "Нужно число, например <code>550</code>. Ещё раз или /cancel.")
                return
            draft["price_rub"] = val
            draft["stars_price"] = max(1, round(val / 16.6)) if val > 0 else 0
            st["step"] = "kind"
            kb = [[{"text": "♾ Текст/ссылка (сразу после оплаты)", "callback_data": "adm:kind:lifetime"}],
                  [{"text": "🔑 Ключи со склада (по одному на покупку)", "callback_data": "adm:kind:key"}]]
            self.api.send_message(chat_id,
                                  f"Цена: <b>{val} ₽</b> / {draft['stars_price']} ⭐.\n\n"
                                  "Шаг 4/5. Как выдаём товар?", kb)
            return
        if step == "payload":
            draft["lifetime_payload"] = text[:2000]
            self._admin_finalize(chat_id, user_id, kind="lifetime")
            return
        # step == "kind" ждёт нажатия кнопки — подсказываем.
        if step == "kind":
            self.api.send_message(chat_id, "Выбери тип выдачи кнопкой выше 👆 или /cancel.")
            return

    def _admin_choose_kind(self, chat_id: int, user_id: int, kind: str) -> None:
        st = self._admin_state.get(user_id)
        if not st or st.get("step") != "kind":
            return
        if kind == "lifetime":
            st["step"] = "payload"
            self.api.send_message(chat_id, "Шаг 5/5. Пришли <b>текст/ссылку/инструкцию</b>, "
                                           "которую покупатель получит сразу после оплаты.")
        else:  # key
            self._admin_finalize(chat_id, user_id, kind="key")

    def _admin_finalize(self, chat_id: int, user_id: int, kind: str) -> None:
        st = self._admin_state.pop(user_id, None)
        if not st:
            return
        d = st["draft"]
        pid = self._gen_product_id(d.get("title", "item"))
        product = {
            "id": pid,
            "title": d.get("title", "Товар"),
            "description": d.get("description", ""),
            "price_rub": int(d.get("price_rub", 0)),
            "stars_price": int(d.get("stars_price", 0)),
            "kind": kind,
            "active": True,
        }
        if kind == "lifetime":
            product["lifetime_payload"] = d.get("lifetime_payload", "Доступ активирован. Спасибо!")
        self.store.upsert_product(product)
        if kind == "key":
            self.api.send_message(
                chat_id,
                f"✅ Товар создан: <b>{html.escape(product['title'])}</b>\n\n"
                "Тип — ключи со склада. Пока склад пуст, товар помечен «нет в наличии». "
                "Добавь ключи кнопкой ниже.")
        else:
            self.api.send_message(
                chat_id,
                f"✅ Товар создан и уже на витрине: <b>{html.escape(product['title'])}</b> "
                f"— {fmt_price(product, self.s)}.")
        self.render_admin_product(chat_id, None, pid)

    def _handle_admin_callback(self, chat_id: int, message_id: int, user_id: int, data: str) -> None:
        """Роутинг adm:* . Только для админа."""
        if not self._is_admin(user_id):
            return
        rest = data[4:]  # без "adm:"
        if rest in {"home", ""}:
            self.render_admin(chat_id, message_id)
        elif rest == "products":
            self.render_admin_products(chat_id, message_id)
        elif rest == "rev":
            self.render_admin_revenue(chat_id, message_id)
        elif rest == "cassa":
            self.render_admin_cassa(chat_id, message_id)
        elif rest == "add":
            self._admin_start_add(chat_id, user_id)
        elif rest.startswith("kind:"):
            self._admin_choose_kind(chat_id, user_id, rest.split(":", 1)[1])
        elif rest.startswith("p:"):
            self.render_admin_product(chat_id, message_id, rest[2:])
        elif rest.startswith("tgl:"):
            pid = rest[4:]
            cur = self.store.product(pid)
            if cur:
                self.store.set_active(pid, not cur.get("active", True))
            self.render_admin_product(chat_id, message_id, pid)
        elif rest.startswith("price:"):
            pid = rest[6:]
            self._admin_state[user_id] = {"step": "edit_price", "product_id": pid, "draft": {}}
            self.api.send_message(chat_id, "Пришли новую <b>цену в рублях</b> (число). Stars пересчитается сам. /cancel — отмена.")
        elif rest.startswith("pay:"):
            pid = rest[4:]
            self._admin_state[user_id] = {"step": "edit_payload", "product_id": pid, "draft": {}}
            self.api.send_message(chat_id, "Пришли новый <b>текст/ссылку</b> выдачи. /cancel — отмена.")
        elif rest.startswith("stock:"):
            pid = rest[6:]
            self._admin_state[user_id] = {"step": "add_stock", "product_id": pid, "draft": {}}
            self.api.send_message(chat_id, "Пришли ключи через запятую или по строкам. /cancel — отмена.")
        elif rest.startswith("del:"):
            pid = rest[4:]
            kb = [[{"text": "🗑 Да, удалить", "callback_data": f"adm:delok:{pid}"},
                   {"text": "⬅️ Отмена", "callback_data": f"adm:p:{pid}"}]]
            self._show(chat_id, message_id, "Удалить товар безвозвратно?", kb)
        elif rest.startswith("delok:"):
            self.store.delete_product(rest[6:])
            self.render_admin_products(chat_id, message_id)


    # ---------- Диспетчер апдейтов ----------
    def handle_update(self, upd: dict) -> None:
        # 1) Pre-checkout (Stars): обязаны ответить в 10 сек, иначе платёж отменится.
        if "pre_checkout_query" in upd:
            self.api.answer_pre_checkout(upd["pre_checkout_query"]["id"], ok=True)
            return

        # 2) Сообщения
        if "message" in upd:
            msg = upd["message"]
            chat_id = msg["chat"]["id"]
            user = msg.get("from", {})
            user_id = user.get("id", 0)

            # 2a) Успешная оплата Stars — выдаём товар
            if "successful_payment" in msg:
                order_id = msg["successful_payment"].get("invoice_payload", "")
                charge_id = msg["successful_payment"].get("telegram_payment_charge_id", "")
                self.core.mark_paid(order_id, charge_id)
                self._fulfill_and_send(chat_id, order_id)
                return

            text = (msg.get("text") or "").strip()
            if not text:
                return
            # Активный мастер (добавление/правка товара) перехватывает только
            # СВОБОДНЫЙ ввод (не команду). Любой текст, начинающийся с «/»,
            # уходит в admin_command/диспетчер — иначе /confirm, /stock, /start
            # проглатывались бы мастером: оплаченный заказ остался бы без выдачи,
            # а цена/склад — искажёнными случайными цифрами из команды.
            if (self._is_admin(user_id) and user_id in self._admin_state
                    and not text.startswith("/")):
                self._admin_wizard_input(chat_id, user_id, text)
                return
            if self.admin_command(chat_id, user_id, text):
                return
            if text.startswith("/start"):
                arg = text[6:].strip()
                self.cmd_start(chat_id, user_id, user.get("username", ""), arg)
            elif text.startswith("/shop"):
                self.render_shop(chat_id)
            elif text.startswith("/my"):
                self.render_my_subs(chat_id, None, user_id)
            elif text.startswith("/help"):
                self.api.send_message(chat_id, f"Поддержка: {html.escape(self.s.support_contact)}",
                                      self._home_kb())
            else:
                self.render_home(chat_id)
            return

        # 3) Нажатия кнопок
        if "callback_query" in upd:
            cq = upd["callback_query"]
            data = cq.get("data", "")
            msg = cq.get("message") or {}
            chat_id = (msg.get("chat") or {}).get("id")
            message_id = msg.get("message_id")
            user_id = (cq.get("from") or {}).get("id", 0)
            self.api.answer_callback(cq["id"])
            if chat_id is None:
                return

            if data == "home":
                self.render_home(chat_id, message_id)
            elif data == "shop":
                self.render_shop(chat_id, message_id)
            elif data == "refs":
                self.render_refs(chat_id, message_id, user_id)
            elif data == "orders":
                self.render_orders(chat_id, message_id, user_id)
            elif data == "help":
                self.render_help(chat_id, message_id)
            elif data.startswith("p:"):
                self.render_product(chat_id, message_id, data[2:])
            elif data.startswith("buy:"):
                self.render_buy(chat_id, message_id, data[4:], user_id)
            elif data.startswith("pay:"):
                _, provider_key, product_id = data.split(":", 2)
                self.start_payment(chat_id, user_id, provider_key, product_id)
            elif data.startswith("chk:"):
                self.check_payment(chat_id, user_id, data[4:])
            elif data == "my":
                self.render_my_subs(chat_id, message_id, user_id)
            elif data.startswith("set:"):
                self.render_setup(chat_id, message_id, user_id, data[4:])
            elif data.startswith("ar0:"):
                self.toggle_autorenew(chat_id, message_id, user_id, data[4:], False)
            elif data.startswith("ar1:"):
                self.toggle_autorenew(chat_id, message_id, user_id, data[4:], True)
            elif data.startswith("pptop:"):
                parts = data.split(":", 2)
                if len(parts) == 3 and parts[2].isdigit():
                    self.start_postpaid_topup(chat_id, user_id, parts[1], int(parts[2]))
            elif data.startswith("ppchk:"):
                self.check_topup_payment(chat_id, user_id, data[6:])
            elif data.startswith("pp:"):
                self._handle_postpaid_callback(chat_id, message_id, user_id, data[3:])
            elif data.startswith("rcx:"):
                self._apply_renewal_choice(chat_id, message_id, user_id, data[4:])
            elif data.startswith("rc:"):
                self.render_renewal_choice(chat_id, message_id, user_id, data[3:])
            elif data == "card:forget":
                self.forget_card_cmd(chat_id, message_id, user_id)
            elif data.startswith("adm:"):
                self._handle_admin_callback(chat_id, message_id, user_id, data)

    def run(self) -> None:
        me = self.api.get_me()
        if not me:
            print("❌ Telegram не отвечает или токен неверен. Проверьте WAVE_BOT_TOKEN в .env")
            return
        self.bot_username = me.get("username", "")
        print(f"🌊 {self.s.shop_name} запущен: @{self.bot_username}")
        print(f"   Кассы: {', '.join(self.providers) or 'НЕТ (задайте ключи в .env)'}")
        print(f"   Админы: {sorted(self.s.admin_ids) or 'НЕ ЗАДАНЫ (WAVE_ADMIN_IDS)'}")
        print(f"   Товаров: {len(self.store.catalog())}")
        while True:
            try:
                updates = self.api.get_updates(self.offset, timeout=60)
                for upd in updates:
                    self.offset = upd["update_id"] + 1
                    try:
                        self.handle_update(upd)
                    except Exception as e:  # fail-soft: один сбой не роняет магазин
                        print(f"⚠️ ошибка обработки апдейта: {e}")
            except KeyboardInterrupt:
                print("\nОстановлен.")
                return
            except Exception as e:
                print(f"⚠️ сетевой сбой: {e}; пауза 5с")
                time.sleep(5)


def main() -> None:
    settings = load_settings()
    if not settings.configured:
        print("❌ WAVE_BOT_TOKEN не задан.\n"
              "   1) Получите токен у @BotFather\n"
              "   2) Скопируйте .env.example → .env и вставьте токен\n"
              "   3) Запустите снова: python3 bot.py")
        return
    ShopBot(settings).run()


if __name__ == "__main__":
    main()

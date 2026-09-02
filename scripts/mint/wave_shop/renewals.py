"""WAVE SHOP — движок подписок (автопродление).

Зачем: подписка с автосписанием — самая выгодная модель по деньгам. Клиент платит
один раз вручную, дальше магазин сам продлевает, пока клиент не отключит.

Как это работает по-настоящему:
  1. Первый платёж идёт через ЮKassa с save_payment_method=True.
  2. ЮKassa возвращает payment_method_id — «привязанную карту».
  3. Когда срок истёк, магазин САМ инициирует списание этим id (безакцептно,
     клиент ничего не подтверждает) — YooKassaProvider.charge_saved_card().
  4. Успех → срок продлён от старого paid_until (клиент не теряет дни).
     Провал → 3 попытки, потом подписка ставится на паузу и клиенту пишут.

Закон (не обсуждается, иначе это списание втихую, а не подписка):
  • перед списанием клиента предупреждают заранее (WAVE_RENEW_NOTICE_DAYS);
  • отключить автопродление можно одной кнопкой в любой момент;
  • при отключении оплаченный срок сохраняется до конца.

Запуск: `python3 renewals.py` (разово) или из cron раз в час.
"""
from __future__ import annotations

import time

from config import load_settings
from payments.providers import YooKassaProvider
from store import POSTPAID_CHOICE, Store
from telegram_api import TelegramAPI


def _fmt_date(ts: int) -> str:
    return time.strftime("%d.%m.%Y", time.localtime(ts))


class RenewalEngine:
    """Прогон подписок: предупредить → списать → продлить/погасить."""

    def __init__(self, settings=None, store: Store | None = None,
                 api: TelegramAPI | None = None, provider=None):
        self.s = settings or load_settings()
        self.store = store or Store(self.s.data_dir)
        self.api = api
        self.provider = provider or YooKassaProvider(
            self.s.yookassa_shop_id, self.s.yookassa_secret_key
        )

    # ---------- шаг 1: предупредить заранее ----------

    def send_notices(self) -> int:
        """Предупредить о предстоящем списании. Возвращает число отправленных."""
        sent = 0
        for sub in self.store.subs_due_for_notice(self.s.renew_notice_days):
            try:
                self._notice_one(sub)
                sent += 1
            except Exception as e:
                print(f"[renewals] сбой предупреждения "
                      f"{sub.get('user_id')}:{sub.get('product_id')}: {e}")
        return sent

    def _notice_one(self, sub: dict) -> None:
        product = self.store.product(sub["product_id"])
        title = product.get("title", sub["product_id"]) if product else sub["product_id"]
        when = _fmt_date(int(sub["paid_until"]))
        amount = sub.get("amount_rub", 0)
        text = (
            f"🔔 <b>Напоминание о продлении</b>\n\n"
            f"Подписка: {title}\n"
            f"Дата списания: <b>{when}</b>\n"
            f"Сумма: <b>{amount:,} ₽</b>\n\n"
            f"Спишется автоматически с привязанной карты — ничего делать не нужно.\n"
            f"Не хотите продлевать? Отключите автопродление в /my — оплаченный "
            f"срок останется до конца."
        ).replace(",", " ")
        if self.api:
            self.api.send_message(
                sub["user_id"], text,
                [[{"text": "⚙️ Управлять подпиской", "callback_data": "my"}]],
            )
        # Метку ставим ПОСЛЕ отправки: если письмо не ушло, предупредим в
        # следующий прогон, а не промолчим перед списанием денег.
        self.store.mark_sub_field(
            sub["user_id"], sub["product_id"], notified_for=int(sub["paid_until"])
        )

    # ---------- шаг 2: списать и продлить ----------

    def process_renewals(self) -> dict:
        """Списать по всем подпискам, которым пора. Возвращает сводку."""
        result = {"charged": 0, "failed": 0, "paused": 0, "revenue_rub": 0, "errors": 0}
        if not self.s.autorenew_enabled:
            return result

        for sub in self.store.subs_due_for_renewal():
            try:
                self._renew_one(sub, result)
            except Exception as e:
                # Одна сломанная подписка не должна останавливать пачку: раньше
                # исключение здесь убивало цикл, и все остальные клиенты просто
                # не продлевались — теряли доступ, хотя платить были готовы.
                result["errors"] += 1
                print(f"[renewals] сбой по подписке "
                      f"{sub.get('user_id')}:{sub.get('product_id')}: {e}")
        return result

    def _renew_one(self, sub: dict, result: dict) -> None:
        """Диспетчер продления: обычное / пересадка / перевод на постоплату.

        Клиент вправе ВЫБРАТЬ, чем списывать (кабинет пишет выбор в
        next_product_id). Пусто/тот же товар → обычное продление тем же тарифом.
        Другой товар → пересадка на него. POSTPAID_CHOICE → перевод на потокенную
        оплату. Это и есть обещанное «на продлении свободен выбрать пакет».
        """
        choice = str(sub.get("next_product_id") or "").strip()
        if choice == POSTPAID_CHOICE:
            self._switch_to_postpaid(sub, result)
            return
        if choice and choice != sub["product_id"]:
            self._renew_as(sub, choice, result)
            return
        self._renew_same(sub, result)

    def _renew_same(self, sub: dict, result: dict) -> None:
        """Обычное продление ТЕМ ЖЕ тарифом (проверенный путь). Исключения ловит вызывающий."""
        user_id = sub["user_id"]
        product_id = sub["product_id"]
        amount = int(sub.get("amount_rub", 0))
        product = self.store.product(product_id)
        title = product.get("title", product_id) if product else product_id

        if not self.provider.configured:
            return

        # Идемпотентность по ПЕРИОДУ: idem-ключ стабилен для одного paid_until,
        # отличается от следующего месяца. Если cron прогонится дважды по одной
        # просроченной подписке — ЮKassa вернёт тот же платёж, не спишет дважды.
        idem = f"{user_id}:{product_id}:{int(sub['paid_until'])}"
        charge = self.provider.charge_saved_card(
            sub["payment_method_id"], amount, f"Продление: {title}",
            idempotency_key=idem
        )

        if charge.ok:
            # ДЕНЬГИ УЖЕ СПИСАНЫ. С этой секунды всё, что ниже, обязано
            # выполниться или быть заметным — молча потерять факт оплаты нельзя.
            updated = self.store.upsert_subscription(
                user_id, product_id,
                period_days=int(sub.get("period_days", 30)),
                amount_rub=amount,
                payment_method_id=sub["payment_method_id"],
                autorenew=True, extend=True,
            )
            self.store.mark_sub_field(user_id, product_id, failed_attempts=0)
            self._extend_gateway_key(user_id, product_id, price_rub=amount)
            self.store.record_revenue(
                order_id=f"renew:{user_id}:{product_id}:{int(time.time())}",
                user_id=user_id, product_id=product_id,
                provider="yookassa_recurring", amount_rub=amount,
                external_ref=getattr(charge, "external_id", "") or "",
            )
            result["charged"] += 1
            result["revenue_rub"] += amount
            if self.api:
                self.api.send_message(
                    user_id,
                    f"✅ <b>Подписка продлена</b>\n\n"
                    f"{title}\n"
                    f"Списано: <b>{amount} ₽</b>\n"
                    f"Активна до: <b>{_fmt_date(int(updated['paid_until']))}</b>\n\n"
                    f"Ключ доступа не меняется — ничего перенастраивать не нужно.",
                )
            return

        attempts = int(sub.get("failed_attempts", 0)) + 1
        self.store.mark_sub_field(user_id, product_id, failed_attempts=attempts)
        result["failed"] += 1
        if attempts >= 3:
            self.store.set_autorenew(user_id, product_id, False)
            result["paused"] += 1
            if self.api:
                self.api.send_message(
                    user_id,
                    f"⚠️ <b>Не удалось продлить подписку</b>\n\n"
                    f"{title}\n"
                    f"Карта отклонила списание {attempts} раза — автопродление "
                    f"поставлено на паузу.\n\n"
                    f"Продлите вручную, чтобы не потерять доступ.",
                    [[{"text": "🔄 Продлить вручную",
                       "callback_data": f"p:{product_id}"}]],
                )
        elif self.api:
            self.api.send_message(
                user_id,
                f"⚠️ Не получилось списать {amount} ₽ за «{title}».\n"
                f"Попробуем ещё раз позже (попытка {attempts} из 3).\n"
                f"Проверьте баланс карты.",
            )

    def _renew_as(self, sub: dict, choice: str, result: dict) -> None:
        """Пересадка на ДРУГОЙ тариф: клиент выбрал списать не тем пакетом.

        Списываем цену НОВОГО товара, продлеваем ТОТ ЖЕ ключ шлюза уже под его
        план, старую подписку выводим из автопродления. Ключ клиента не меняется —
        в Cursor ничего перевставлять не надо.
        """
        user_id = sub["user_id"]
        old_id = sub["product_id"]
        new_product = self.store.product(choice)
        if not new_product:
            # Выбранный товар исчез из каталога, пока ждали продления. Не теряем
            # клиента и не списываем за несуществующее: продлеваем прежним тарифом
            # (проверенный путь) и гасим кривой выбор, чтобы не залипнуть на нём.
            self.store.mark_sub_field(user_id, old_id, next_product_id="")
            self._renew_same(sub, result)
            return

        amount = int(new_product.get("price_rub", 0))
        title = new_product.get("title", choice)
        period_days = int(new_product.get("period_days", sub.get("period_days", 30)))

        if not self.provider.configured:
            return

        # idem по НОВОМУ товару и текущему периоду старой подписки: стабилен между
        # повторами cron (до успеха old.paid_until не двигается), но отличается и от
        # обычного продления, и от следующего периода.
        idem = f"{user_id}:{choice}:{int(sub['paid_until'])}"
        charge = self.provider.charge_saved_card(
            sub["payment_method_id"], amount, f"Смена тарифа: {title}",
            idempotency_key=idem,
        )

        if not charge.ok:
            self._note_charge_failure(
                sub, result, title, amount,
                keep_choice=True,   # карта не виновата — выбор храним до повтора
            )
            return

        # ДЕНЬГИ СПИСАНЫ. Первым делом гасим СТАРУЮ подписку одним атомарным
        # писом (autorenew off + чистим выбор) — это снимает её с очереди
        # продления, поэтому повторный прогон уже не пересадит второй раз.
        self.store.mark_sub_field(
            user_id, old_id, autorenew=False, next_product_id="", failed_attempts=0,
        )
        # Новая подписка со СВЕЖИМ сроком (extend=False: у просроченной старой
        # остатка дней нет, а абсолютный срок делает повтор идемпотентным —
        # не копит месяцы). ЭТО становится активной автопродлеваемой подпиской.
        updated = self.store.upsert_subscription(
            user_id, choice, period_days=period_days, amount_rub=amount,
            payment_method_id=sub["payment_method_id"], autorenew=True, extend=False,
        )
        self._extend_gateway_key(user_id, choice, price_rub=amount)
        self.store.record_revenue(
            order_id=f"switch:{user_id}:{choice}:{int(time.time())}",
            user_id=user_id, product_id=choice,
            provider="yookassa_recurring", amount_rub=amount,
            external_ref=getattr(charge, "external_id", "") or "",
        )
        result["charged"] += 1
        result["revenue_rub"] += amount
        if self.api:
            self.api.send_message(
                user_id,
                f"✅ <b>Тариф изменён и продлён</b>\n\n"
                f"Новый тариф: {title}\n"
                f"Списано: <b>{amount} ₽</b>\n"
                f"Активен до: <b>{_fmt_date(int(updated['paid_until']))}</b>\n\n"
                f"Ключ доступа тот же — перенастраивать ничего не нужно.",
            )

    def _switch_to_postpaid(self, sub: dict, result: dict) -> None:
        """Перевод на потокенную оплату: вместо пакета — кошелёк в ₽ и автосписание.

        Это обещанное «на продлении можно не брать пакет, а платить по факту».
        Кошелёк надо ЗАСЕЯТЬ (postpaid с нулём сразу заблокирован гейтом баланса,
        а автопополнение включается только ПОСЛЕ первого расхода) — списываем
        стартовый депозит и включаем автопополнение. Долга нет: деньги вперёд.
        """
        user_id = sub["user_id"]
        old_id = sub["product_id"]
        gq = self._quota_store()
        if not gq:
            result["errors"] += 1
            print(f"[renewals] постоплата недоступна (нет модуля шлюза) "
                  f"{user_id}:{old_id}")
            return

        rec, _plan = self._user_key_for_product(gq, user_id, old_id)
        if not rec:
            # Нет ключа шлюза для перевода — конвертировать нечего. Не списываем и
            # не залипаем: гасим старую подписку и честно зовём привязать ключ.
            self.store.mark_sub_field(
                user_id, old_id, autorenew=False, next_product_id="",
            )
            result["errors"] += 1
            if self.api:
                self.api.send_message(
                    user_id,
                    "⚠️ Не нашли ваш ключ доступа для перевода на потокенную "
                    "оплату. Напишите в поддержку — переведём вручную.",
                )
            return

        token = rec["token"]
        # Уже переведён (сбой между списанием и arm на прошлом прогоне): деньги не
        # трогаем, просто до-гасим старую подписку и снимаем выбор.
        fresh = gq.get_key(token) or rec
        if fresh.get("kind") == "postpaid":
            self.store.mark_sub_field(
                user_id, old_id, autorenew=False, next_product_id="",
            )
            return

        pm_id = self._card_for_user(user_id) or sub.get("payment_method_id", "")
        seed = int(getattr(self.s, "postpaid_seed_rub", 500))
        if not self.provider.configured:
            return

        idem = f"postpaid-seed:{user_id}:{old_id}:{int(sub['paid_until'])}"
        charge = self.provider.charge_saved_card(
            pm_id, seed, "Старт потокенной оплаты WAVE",
            idempotency_key=idem,
        )
        if not charge.ok:
            self._note_charge_failure(
                sub, result, "потокенная оплата", seed, keep_choice=True,
            )
            return

        # ДЕНЬГИ СПИСАНЫ. Тот же токен → режим постоплаты с засеянным балансом и
        # включённым автопополнением («трафик кончился → само списывает»).
        from gateway.quota import get_plan
        pp = get_plan("postpaid") or {}
        gq.arm_postpaid(
            token, deposit_rub=seed, autotopup=True,
            low_watermark_rub=int(pp.get("low_watermark_rub", 100)),
            topup_amount_rub=seed,
        )
        # Карта, которой списали, становится картой на файле — автопополнению
        # будет чем платить дальше (иначе первый же порог отключит автосписание).
        if pm_id:
            self.store.set_card_on_file(user_id, pm_id)
        self.store.mark_sub_field(
            user_id, old_id, autorenew=False, next_product_id="", failed_attempts=0,
        )
        self.store.record_revenue(
            order_id=f"postpaid-seed:{user_id}:{token}:{int(sub['paid_until'])}",
            user_id=user_id, product_id="postpaid",
            provider="yookassa_postpaid_seed", amount_rub=seed,
            external_ref=getattr(charge, "external_id", "") or "",
        )
        result["charged"] += 1
        result["revenue_rub"] += seed
        if self.api:
            self.api.send_message(
                user_id,
                f"✅ <b>Переход на потокенную оплату</b>\n\n"
                f"Стартовый баланс: <b>{seed} ₽</b>\n"
                f"Дальше списываем по факту — только за реально использованные "
                f"токены, по нашему тарифу.\n"
                f"Автопополнение включено: доступ не прервётся, когда баланс "
                f"подойдёт к концу.\n\n"
                f"Ключ доступа тот же — перенастраивать ничего не нужно.",
            )

    def _note_charge_failure(self, sub: dict, result: dict, title: str,
                             amount: int, *, keep_choice: bool) -> None:
        """Общий разбор неудачного списания: 3 попытки, потом пауза (как продление).

        keep_choice — сохранить next_product_id: при смене тарифа/переводе на
        постоплату карта, а не выбор, виновата в отказе, поэтому выбор храним,
        чтобы после починки карты списалось тем, что клиент просил.
        """
        user_id = sub["user_id"]
        product_id = sub["product_id"]
        attempts = int(sub.get("failed_attempts", 0)) + 1
        self.store.mark_sub_field(user_id, product_id, failed_attempts=attempts)
        result["failed"] += 1
        if attempts >= 3:
            self.store.set_autorenew(user_id, product_id, False)
            result["paused"] += 1
            if self.api:
                self.api.send_message(
                    user_id,
                    f"⚠️ <b>Не удалось списать за «{title}»</b>\n\n"
                    f"Карта отклонила платёж {attempts} раза — операция "
                    f"поставлена на паузу.\n\n"
                    f"Оформите вручную, чтобы не потерять доступ.",
                    [[{"text": "🔄 Открыть бота", "callback_data": "my"}]],
                )
        elif self.api:
            self.api.send_message(
                user_id,
                f"⚠️ Не получилось списать {amount} ₽ за «{title}».\n"
                f"Попробуем ещё раз позже (попытка {attempts} из 3).\n"
                f"Проверьте баланс карты.",
            )

    def _quota_store(self):
        """QuotaStore или None, если модуль шлюза недоступен (fail-soft)."""
        try:
            from gateway.quota import QuotaStore
        except ImportError:
            return None
        return QuotaStore(self.s.data_dir)

    def _user_key_for_product(self, gq, user_id: int, product_id: str):
        """Самый свежий ключ шлюза пользователя под план этого товара.

        Возвращает (rec | None, plan_id | None). Общая логика поиска токена для
        продления/пересадки/перевода на постоплату: раньше жила внутри
        _extend_gateway_key, поэтому пересадка не знала, какой токен трогать, и
        клиенту пришлось бы перевставлять ключ. Теперь все пути берут ОДИН токен.
        """
        product = self.store.product(product_id)
        if not product:
            return None, None
        from gateway.quota import canon_plan_id
        plan_id = product.get("plan_id", product_id)
        canon = canon_plan_id(plan_id)
        mine = [k for k in gq.keys_of_user(user_id)
                if canon_plan_id(str(k.get("plan_id", ""))) == canon]
        if not mine:
            return None, plan_id
        return max(mine, key=lambda k: int(k.get("created_at", 0))), plan_id

    def _extend_gateway_key(self, user_id: int, product_id: str,
                            price_rub: int = 0) -> None:
        """Продлить ТОТ ЖЕ ключ шлюза после успешного списания.

        Деньги взяли — доступ обязан продолжиться на том же токене. Если этого
        не сделать, клиент оплатил месяц, а ключ в его Cursor умирает по сроку:
        худший возможный исход, потому что списание прошло успешно.

        price_rub — сколько сейчас списали (₽). Без него extend() записал бы в
        ключ price_rub=0, и кабинет клиента показал бы «0 ₽ из 0» на весь новый
        оплаченный месяц: деньги ушли, а обещание «сколько РЕАЛЬНО потрачено —
        отображается» молча ломается. Передаём сумму — цена периода честная.
        """
        gq = self._quota_store()
        if not gq:
            return
        from gateway.quota import get_plan
        rec, plan_id = self._user_key_for_product(gq, user_id, product_id)
        plan = get_plan(plan_id) if plan_id else None
        if not plan or plan["kind"] not in {"subscription", "unlimited"}:
            return
        if not rec:
            return
        gq.extend(rec["token"], plan_id, price_rub=price_rub)

    # ---------- шаг 3: автопополнение потокенных кошельков ----------

    def _card_for_user(self, user_id: int) -> str:
        """payment_method_id для автосписания: карта на файле, иначе — из подписки.

        Карта на файле — явная привязка (кабинет/«привязать карту»), приоритет.
        Фолбэк на payment_method_id самой свежей подписки клиента: автопополнение
        работает даже до отдельной привязки карты — у клиента с подпиской карта
        де-факто уже сохранена. Карта живёт на уровне пользователя, поэтому годится
        любой его сохранённый способ (см. store.set_card_on_file).
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

    def process_topups(self) -> dict:
        """Автопополнить потокенные кошельки, у которых баланс упал ниже порога.

        Тот же kill-switch (autorenew_enabled) и тот же провайдер, что у продления:
        один cron гоняет и продление подписок, и автопополнение постоплаты. Это
        и есть обещанное «трафик кончился → само списывает», но БЕЗ кредита:
        порог срабатывает, пока на кошельке ещё есть деньги.
        """
        result = {"topped_up": 0, "topup_failed": 0, "topup_paused": 0,
                  "topup_revenue_rub": 0, "topup_errors": 0}
        if not self.s.autorenew_enabled:
            return result
        gq = self._quota_store()
        if not gq:
            return result
        for rec in gq.keys_needing_topup():
            try:
                self._topup_one(gq, rec, result)
            except Exception as e:
                # Один сломанный ключ не должен ронять пачку — как в продлении.
                result["topup_errors"] += 1
                print(f"[renewals] сбой автопополнения "
                      f"{str(rec.get('token', '?'))[:12]}…: {e}")
        return result

    def _topup_one(self, gq, rec: dict, result: dict) -> None:
        """Одно автопополнение: списать topup_amount_rub с карты → зачислить в кошелёк."""
        token = rec["token"]
        user_id = rec.get("user_id")
        amount = int(rec.get("topup_amount_rub", 0)) or int(
            getattr(self.s, "postpaid_seed_rub", 500))

        if not self.provider.configured:
            return  # dry: денег не двигаем (RUBICON). topup_needed остаётся — повторим, когда включат.

        pm_id = self._card_for_user(user_id)
        if not pm_id:
            # Автопополнение включено, а карты нет — списывать нечем. Гасим
            # автосписание, чтобы не крутить впустую каждый час, и честно зовём
            # привязать карту (доступ ещё жив — порог срабатывает до нуля).
            gq.set_autotopup(token, False)
            result["topup_paused"] += 1
            if self.api:
                self.api.send_message(
                    user_id,
                    "⚠️ Баланс потокенного тарифа подходит к концу, но карта для "
                    "автопополнения не привязана.\nПривяжите карту или пополните "
                    "вручную, чтобы доступ не прервался.",
                    [[{"text": "💳 Открыть бота", "callback_data": "my"}]],
                )
            return

        # idem по НОМЕРУ пополнения (topup_seq): стабилен, пока это пополнение не
        # завершилось (повтор после сбоя дедуплицируется у провайдера — не спишет
        # дважды), и сдвигается только удачным topup(). Читаем seq ДО topup():
        # именно это значение зашито в дедупликацию текущего списания. consume()
        # seq не трогает, поэтому расход клиента между сбоем и повтором idem не рвёт.
        seq = int(rec.get("topup_seq", 0))
        idem = f"topup:{token}:{seq}"
        charge = self.provider.charge_saved_card(
            pm_id, amount, "Автопополнение потокенного тарифа WAVE",
            idempotency_key=idem,
        )

        if not charge.ok:
            n = gq.note_topup_failure(token)
            result["topup_failed"] += 1
            if n >= 3:
                # 3 отказа подряд — как у продления: выключаем автосписание,
                # чтобы не долбить отклоняющую карту.
                gq.set_autotopup(token, False)
                result["topup_paused"] += 1
                if self.api:
                    self.api.send_message(
                        user_id,
                        "⚠️ Не удалось автопополнить потокенный тариф: карта "
                        "отклонила списание 3 раза — автопополнение выключено.\n"
                        "Пополните вручную или привяжите другую карту.",
                        [[{"text": "💳 Открыть бота", "callback_data": "my"}]],
                    )
            elif self.api:
                self.api.send_message(
                    user_id,
                    f"⚠️ Не удалось автопополнить баланс ({amount} ₽), "
                    f"попытка {n} из 3. Проверьте карту — попробуем ещё раз.",
                )
            return

        # ДЕНЬГИ СПИСАНЫ. Зачисляем в кошелёк: topup() сдвигает topup_seq и снимает
        # topup_needed → ключ уходит из очереди, а повтор ЭТОГО прогона получил бы
        # новый idem (списания больше нет — нечего дублировать).
        updated = gq.topup(token, amount)
        self.store.record_revenue(
            order_id=f"topup:{token}:{seq}",
            user_id=user_id, product_id="postpaid",
            provider="yookassa_postpaid_topup", amount_rub=amount,
            external_ref=getattr(charge, "external_id", "") or "",
        )
        result["topped_up"] += 1
        result["topup_revenue_rub"] += amount
        if self.api and updated:
            self.api.send_message(
                user_id,
                f"✅ <b>Кошелёк пополнен</b>\n\n"
                f"Списано: <b>{amount} ₽</b>\n"
                f"Баланс: <b>{round(float(updated.get('deposit_rub', 0)), 2)} ₽</b>\n"
                f"Доступ не прерывался — списываем дальше по факту.",
            )

    def run_once(self) -> dict:
        notices = self.send_notices()
        summary = self.process_renewals()
        # Автопополнение постоплаты — отдельная сводка, вливаем в общую (ключи не
        # пересекаются с продлением: topup_* vs charged/failed/…).
        summary.update(self.process_topups())
        summary["notices"] = notices
        return summary


def _dry_report(settings=None) -> int:
    """Сухой аудит: показать, что сделал БЫ живой прогон, НИЧЕГО не делая.

    0 списаний, 0 сообщений клиентам, 0 записей. Считаем ровно те же очереди,
    что дёргает движок (subs_due_for_renewal + keys_needing_topup), — оператор
    видит фронт работ до того, как вооружит автосписание. Так launchd-задачу
    можно держать заряженной в заведомо безопасном режиме даже при живых ключах.

    settings впрыскивается тестом (иначе берём боевые из .env).
    """
    settings = settings or load_settings()
    store = Store(settings.data_dir)
    now = int(time.time())
    due = store.subs_due_for_renewal(now)
    topups: list = []
    try:
        from gateway.quota import QuotaStore
        topups = QuotaStore(settings.data_dir).keys_needing_topup()
    except Exception as e:                       # шлюз недоступен — не падаем
        print(f"[renewals DRY] очередь автопополнения недоступна: {e}")
    print(f"[renewals DRY] к продлению подписок={len(due)} · "
          f"к автопополнению кошельков={len(topups)} · "
          f"СПИСАНИЙ НЕ ДЕЛАЕМ, сообщений НЕ шлём, записи НЕ трогаем")
    for s in due:
        choice = str(s.get("next_product_id") or "").strip()
        plan = "потокенно" if choice == POSTPAID_CHOICE else (choice or "тот же тариф")
        print(f"  · продление: user={s.get('user_id')} товар={s.get('product_id')} "
              f"→ {plan} ≈{s.get('amount_rub', 0)} ₽")
    for r in topups:
        print(f"  · автопополнение: user={r.get('user_id')} "
              f"ключ …{str(r.get('token', ''))[-6:]} +{r.get('topup_amount_rub', 0)} ₽")
    return 0


def main() -> int:
    import sys
    if "--dry-run" in sys.argv[1:] or "--dry" in sys.argv[1:]:
        return _dry_report()
    settings = load_settings()
    api = TelegramAPI(settings.bot_token) if settings.configured else None
    engine = RenewalEngine(settings, api=api)
    summary = engine.run_once()
    print(
        f"[renewals] предупреждений={summary['notices']} "
        f"списано={summary['charged']} (+{summary['revenue_rub']} ₽) "
        f"провалов={summary['failed']} на_паузе={summary['paused']} "
        f"сбоев={summary.get('errors', 0)} | "
        f"автопополнений={summary.get('topped_up', 0)} "
        f"(+{summary.get('topup_revenue_rub', 0)} ₽) "
        f"провалов_пополн={summary.get('topup_failed', 0)} "
        f"пауз_пополн={summary.get('topup_paused', 0)} "
        f"сбоев_пополн={summary.get('topup_errors', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

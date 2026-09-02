#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOCC Bot-Factory V1 — переиспользуемый Telegram-бот-автоответчик «под ключ» (актив вселенной D2).

Один код → новый клиент = новый config.json (5 минут вместо часов). Он же демо-бот, который закрывает
сделку без отзывов. Под капотом «фабрика»: логика ЧИСТАЯ (stdlib, тестируется без сети/aiogram), сетевой
рантайм (aiogram) грузится ЛЕНИВО только при запуске бота.

  python3 socc_botfactory_v1.py --check [config.json]   # валидировать конфиг + показать дерево диалога (stdlib)
  python3 socc_botfactory_v1.py --new "Имя клиента"      # создать config из шаблона (новый клиент за 1 команду)
  BOT_TOKEN=... python3 socc_botfactory_v1.py config.json # запустить бота (нужен aiogram + токен КЛИЕНТА)

Закон (RL4/152-ФЗ): бот легальный — без спам-рассылок, без сбора перс. данных без согласия (согласие в
форме заявки), токен — клиента. Лиды форвардятся владельцу (owner_chat_id). Деньги клиента бот не трогает.
"""
import os
import re
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

LEAD = "__LEAD__"            # спец-метка пункта меню: запускает сбор заявки
REQUIRED = ["business_name", "welcome", "menu"]
HERE = Path(__file__).resolve().parent


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load_config(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def uses_lead(cfg):
    return any((m.get("answer") == LEAD) for m in cfg.get("menu", []) if isinstance(m, dict))


def validate_config(cfg):
    """Вернуть список ошибок конфига ([] = валиден). Каждая проверка может провалиться (фальсифицируемо)."""
    errors = []
    for k in REQUIRED:
        if not cfg.get(k):
            errors.append(f"нет обязательного поля '{k}'")
    menu = cfg.get("menu")
    if not isinstance(menu, list) or not menu:
        errors.append("menu должен быть непустым списком")
    else:
        for i, m in enumerate(menu):
            if not isinstance(m, dict) or not m.get("label") or not m.get("answer"):
                errors.append(f"menu[{i}]: нужны поля label и answer")
    if uses_lead(cfg):
        lead = cfg.get("lead")
        if not isinstance(lead, dict) or not lead.get("prompt") or not lead.get("thanks") \
                or not isinstance(lead.get("fields"), list) or not lead["fields"]:
            errors.append("есть пункт «заявка» (__LEAD__), но lead{prompt,fields,thanks} не задан")
        if not isinstance(cfg.get("owner_chat_id"), int):
            errors.append("owner_chat_id должен быть числом (chat_id владельца — куда падают заявки)")
    faq = cfg.get("faq", [])
    if faq and not all(isinstance(f, dict) and isinstance(f.get("q"), list) and f.get("a") for f in faq):
        errors.append("faq: каждый элемент — {q:[слова], a:'ответ'}")
    return errors


def build_menu(cfg):
    """Меню → список {label, kind:'answer'|'lead', payload}. Диспетчер кнопок рантайма."""
    out = []
    for m in cfg.get("menu", []):
        is_lead = m.get("answer") == LEAD
        out.append({"label": m.get("label", "?"), "kind": "lead" if is_lead else "answer",
                    "payload": "" if is_lead else m.get("answer", "")})
    return out


def match_faq(cfg, text):
    """Свободный текст → ответ из faq по ключевым словам, либо None (тогда рантайм покажет меню)."""
    t = (text or "").lower()
    for f in cfg.get("faq", []):
        if any(re.search(r"\b" + re.escape(str(w).lower()), t) for w in f.get("q", [])):
            return f.get("a")
    return None


def lead_payload(cfg, answers, ts=None):
    """Сообщение-заявка владельцу (owner_chat_id). Содержит данные + след времени + отметку согласия."""
    ts = ts or _now()
    body = "\n".join(f"{k}: {v}" for k, v in answers.items())
    return (f"🔔 Новая заявка — {cfg.get('business_name', 'бот')}\n{body}\n"
            f"Когда: {ts}\nСогласие на обработку ПД: получено (через форму заявки).")


def render_tree(cfg):
    """Человекочитаемое дерево диалога — оператор видит бота БЕЗ запуска (как dry-run органа)."""
    lines = [f"🤖 {cfg.get('business_name', '?')}", f"/start → {cfg.get('welcome', '')}", "Меню:"]
    for m in build_menu(cfg):
        if m["kind"] == "lead":
            lines.append(f"  • {m['label']}  → [СБОР ЗАЯВКИ: {', '.join(cfg.get('lead', {}).get('fields', []))}]")
        else:
            lines.append(f"  • {m['label']}  → {m['payload'].splitlines()[0] if m['payload'] else ''}…")
    if cfg.get("faq"):
        lines.append("FAQ (свободный текст):")
        for f in cfg["faq"]:
            lines.append(f"  ? {', '.join(f.get('q', []))}  → {f.get('a', '')[:50]}…")
    if uses_lead(cfg):
        owner = cfg.get("owner_chat_id")
        lines.append(f"Заявки → owner_chat_id={owner}" + ("  ⚠️ задай реальный chat_id владельца!" if not owner else ""))
    return "\n".join(lines)


_TEMPLATE = {
    "business_name": "", "welcome": "Здравствуйте! 👋 Чем помочь?",
    "menu": [
        {"label": "💼 Услуги и цены", "answer": "Опишите услуги и цены здесь."},
        {"label": "📍 Адрес и часы", "answer": "Адрес и часы работы."},
        {"label": "📞 Контакты", "answer": "Телефон и контакты."},
        {"label": "✍️ Оставить заявку", "answer": LEAD},
    ],
    "faq": [{"q": ["цена", "стоимость", "сколько"], "a": "Актуальные цены — в кнопке «Услуги и цены»."}],
    "lead": {"prompt": "Оставьте имя и телефон — мы перезвоним. Отправляя данные, вы соглашаетесь на обработку "
                       "персональных данных (152-ФЗ).",
             "fields": ["Имя", "Телефон"], "thanks": "Спасибо! Заявка принята, скоро свяжемся. 🙌"},
    "owner_chat_id": 0,
}


def scaffold_new(name, out_dir=None):
    """Создать config нового клиента из шаблона. Новый клиент = 1 команда (фабрика)."""
    slug = re.sub(r"[^\w]+", "_", str(name), flags=re.UNICODE).strip("_").lower() or "client"
    cfg = json.loads(json.dumps(_TEMPLATE))
    cfg["business_name"] = name
    cfg["welcome"] = f"Здравствуйте! 👋 Это бот «{name}». Чем помочь?"
    path = Path(out_dir or HERE) / f"config.{slug}.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(config_path):
    """Запуск реального бота (RUBICON: токен клиента). aiogram — ленивый импорт."""
    try:
        from aiogram import Bot, Dispatcher, F
        from aiogram.filters import CommandStart
        from aiogram.utils.keyboard import InlineKeyboardBuilder
    except Exception as e:
        print(f"aiogram не установлен ({e}). Установи: pip install aiogram", file=sys.stderr)
        sys.exit(1)
    import asyncio

    token = os.getenv("BOT_TOKEN")
    if not token:
        print("нет BOT_TOKEN (токен бота клиента из @BotFather)", file=sys.stderr)
        sys.exit(1)
    cfg = load_config(config_path)
    errs = validate_config(cfg)
    if errs:
        print("конфиг невалиден:\n  - " + "\n  - ".join(errs), file=sys.stderr)
        sys.exit(1)

    bot, dp, menu, state = Bot(token), Dispatcher(), build_menu(cfg), {}

    def kb():
        b = InlineKeyboardBuilder()
        for i, m in enumerate(menu):
            b.button(text=m["label"], callback_data=f"m{i}")
        b.adjust(1)
        return b.as_markup()

    @dp.message(CommandStart())
    async def start(msg):
        state.pop(msg.from_user.id, None)
        await msg.answer(cfg["welcome"], reply_markup=kb())

    @dp.callback_query(F.data.startswith("m"))
    async def on_menu(cb):
        m = menu[int(cb.data[1:])]
        if m["kind"] == "lead":
            fields = cfg["lead"]["fields"]
            state[cb.from_user.id] = {"fi": 0, "answers": {}}
            await cb.message.answer(cfg["lead"]["prompt"])
            await cb.message.answer(f"Введите: {fields[0]}")
        else:
            await cb.message.answer(m["payload"], reply_markup=kb())
        await cb.answer()

    @dp.message()
    async def on_text(msg):
        uid, fields = msg.from_user.id, cfg.get("lead", {}).get("fields", [])
        if uid in state:
            st = state[uid]
            st["answers"][fields[st["fi"]]] = msg.text
            st["fi"] += 1
            if st["fi"] < len(fields):
                await msg.answer(f"Введите: {fields[st['fi']]}")
            else:
                try:
                    await bot.send_message(cfg["owner_chat_id"], lead_payload(cfg, st["answers"]))
                except Exception:
                    pass
                await msg.answer(cfg["lead"]["thanks"], reply_markup=kb())
                state.pop(uid, None)
            return
        await msg.answer(match_faq(cfg, msg.text) or "Выберите пункт меню 👇 или напишите вопрос.", reply_markup=kb())

    print(f"бот «{cfg['business_name']}» запущен (polling). Ctrl-C — стоп.")
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--new":
        if len(args) < 2:
            print("использование: --new \"Имя клиента\""); sys.exit(1)
        print("создан конфиг:", scaffold_new(args[1]))
    elif not args or args[0] == "--check":
        path = args[1] if len(args) > 1 else str(HERE / "config.sample.json")
        cfg = load_config(path)
        errs = validate_config(cfg)
        print(render_tree(cfg))
        print("\nКонфиг:", "✅ валиден" if not errs else "❌ ошибки:\n  - " + "\n  - ".join(errs))
        sys.exit(0 if not errs else 1)
    else:
        main(args[0])

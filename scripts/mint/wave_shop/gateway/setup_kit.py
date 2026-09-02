"""WAVE — автоподключение клиента. Ключ → работающий инструмент за одну команду.

Зачем этот модуль существует (это про деньги, а не про удобство):

Клиент купил ключ и остался один на один с инструкцией. Между «оплатил» и
«получил пользу» стоит ручная настройка: найти настройки Cursor, включить
override base URL, вписать два поля, не опечататься. Каждый шаг здесь — это
место, где человек бросает. Он уже заплатил, ничего не заработало, и следующий
раз он не продлит — не потому что продукт плохой, а потому что не завёлся.

Поэтому: клиент получает готовый файл конфига или одну команду. Ноль ручного
ввода → ноль опечаток → человек видит результат в первую минуту.

Второе (удержание): при продлении ключ НЕ меняется. Один раз настроил — больше
не трогает. Отсюда правило: конфиги не содержат срока и квоты, только адрес и
ключ, чтобы файл оставался верным после любого продления.

Канон MINT: stdlib-only, никакого curl | sh.

ПОЧЕМУ НЕ `curl ... | sh`: это выглядит как «одна команда», но учит клиента
исполнять код с чужого сервера, а его ключ попадает в историю shell и в логи.
Мы даём готовый ФАЙЛ и текст команды — клиент видит, что именно применяет.
"""
from __future__ import annotations

import json
import os
import shlex

# Модель по умолчанию для конфигов инструментов.
DEFAULT_MODEL = os.environ.get("WAVE_DEFAULT_MODEL", "claude-opus-5")
# Какую модель писать клиенту с ограниченным тарифом (демо).
TIER_MODELS = {
    "opus": "claude-opus-5",
    "sonnet": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5",
}


def public_gateway() -> str:
    """Публичный адрес шлюза для клиента (с /v1 на конце)."""
    url = os.environ.get("WAVE_PUBLIC_GATEWAY", "http://127.0.0.1:8790/v1").strip()
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def model_for_key(rec: dict | None) -> str:
    """Модель, которую МОЖНО звать этим ключом.

    Если у ключа стоит потолок (демо = sonnet), в конфиг попадает именно та
    модель, а не opus. Иначе клиент получил бы файл, который сразу упирается
    в отказ шлюза, и решил бы, что «ключ не работает».
    """
    tier = str((rec or {}).get("model_key", "")).strip()
    if tier in TIER_MODELS:
        return TIER_MODELS[tier]
    return DEFAULT_MODEL


# ═══════════════════ Конфиги под инструменты ═══════════════════


def continue_config(token: str, model: str, base_url: str) -> str:
    """~/.continue/config.json — VS Code и JetBrains."""
    return json.dumps({
        "models": [{
            "title": "WAVE",
            "provider": "openai",
            "model": model,
            "apiBase": base_url,
            "apiKey": token,
        }],
    }, ensure_ascii=False, indent=2)


def cline_config(token: str, model: str, base_url: str) -> str:
    """Cline / Roo Code (VS Code) — настройки провайдера."""
    return json.dumps({
        "apiProvider": "openai",
        "openAiBaseUrl": base_url,
        "openAiApiKey": token,
        "openAiModelId": model,
    }, ensure_ascii=False, indent=2)


def env_file(token: str, model: str, base_url: str) -> str:
    """.env — универсальный путь для SDK и своих скриптов."""
    return (
        "# WAVE — доступ к модели через OpenAI-совместимый шлюз\n"
        f"OPENAI_BASE_URL={base_url}\n"
        f"OPENAI_API_KEY={token}\n"
        f"WAVE_MODEL={model}\n"
    )


def shell_exports(token: str, model: str, base_url: str) -> str:
    """Строки для ~/.zshrc или ~/.bashrc."""
    return (
        f"export OPENAI_BASE_URL={shlex.quote(base_url)}\n"
        f"export OPENAI_API_KEY={shlex.quote(token)}\n"
        f"export WAVE_MODEL={shlex.quote(model)}\n"
    )


def python_snippet(token: str, model: str, base_url: str) -> str:
    return (
        "from openai import OpenAI\n\n"
        f'client = OpenAI(base_url="{base_url}", api_key="{token}")\n\n'
        "r = client.chat.completions.create(\n"
        f'    model="{model}",\n'
        '    messages=[{"role": "user", "content": "Привет!"}],\n'
        ")\n"
        "print(r.choices[0].message.content)\n"
    )


def js_snippet(token: str, model: str, base_url: str) -> str:
    return (
        'import OpenAI from "openai";\n\n'
        "const client = new OpenAI({\n"
        f'  baseURL: "{base_url}",\n'
        f'  apiKey: "{token}",\n'
        "});\n\n"
        "const r = await client.chat.completions.create({\n"
        f'  model: "{model}",\n'
        '  messages: [{ role: "user", content: "Привет!" }],\n'
        "});\n"
        "console.log(r.choices[0].message.content);\n"
    )


def curl_check(token: str, model: str, base_url: str) -> str:
    """Проверка «работает ли» одной командой. Первое, что должен сделать клиент."""
    return (
        f"curl -s {shlex.quote(base_url + '/chat/completions')} \\\n"
        f"  -H {shlex.quote('Authorization: Bearer ' + token)} \\\n"
        f"  -H 'Content-Type: application/json' \\\n"
        f"  -d '{{\"model\":\"{model}\",\"messages\":"
        f"[{{\"role\":\"user\",\"content\":\"скажи ok\"}}]}}'"
    )


# ═══════════════════ Claude Code («пак мэджик») ═══════════════════
#
# Отдельный путь от OpenAI-инструментов: Claude Code ходит по НАТИВНОМУ
# протоколу Anthropic (ANTHROPIC_BASE_URL + /v1/messages), а не по OpenAI-совмес-
# тимому. Две тонкости, каждая — молчаливый отказ, если промахнуться:
#
#   1. Anthropic-клиент САМ дописывает /v1/messages к базовому адресу. Значит в
#      ANTHROPIC_BASE_URL нужен корень шлюза БЕЗ /v1 (иначе /v1/v1/messages → 404).
#      Для OpenAI-инструментов /v1, наоборот, обязателен — поэтому адреса разные.
#   2. Токен несём как ANTHROPIC_AUTH_TOKEN (уходит в Authorization: Bearer) —
#      документированный путь для стороннего шлюза. Шлюз читает и Bearer, и
#      x-api-key, так что оба сработают, но AUTH_TOKEN не путается с проверкой
#      настоящего ключа Anthropic на стороне клиента.
#
# ANTHROPIC_SMALL_FAST_MODEL задаём равным основной модели: без него Claude Code
# зовёт для фоновых задач свою haiku по имени, которого может не быть у бэкенда
# оператора, → 404 на ровном месте.


def anthropic_base() -> str:
    """Базовый адрес шлюза для Claude Code / Anthropic SDK — БЕЗ /v1 на конце."""
    url = public_gateway()          # заканчивается на /v1
    if url.endswith("/v1"):
        url = url[:-3]
    return url.rstrip("/")


def claude_env(token: str, model: str, a_base: str) -> str:
    """Экспорты окружения для Claude Code (для ручной/постоянной настройки)."""
    return (
        f"export ANTHROPIC_BASE_URL={shlex.quote(a_base)}\n"
        f"export ANTHROPIC_AUTH_TOKEN={shlex.quote(token)}\n"
        f"export ANTHROPIC_MODEL={shlex.quote(model)}\n"
        f"export ANTHROPIC_SMALL_FAST_MODEL={shlex.quote(model)}\n"
    )


def claude_oneliner(token: str, model: str, a_base: str) -> str:
    """Минимальный путь: одна строка, ничего не пишет на диск — запускает Claude
    Code через шлюз в эфемерном окружении (для тех, кто не хочет файлов)."""
    return (
        f"ANTHROPIC_BASE_URL={shlex.quote(a_base)} "
        f"ANTHROPIC_AUTH_TOKEN={shlex.quote(token)} "
        f"ANTHROPIC_MODEL={shlex.quote(model)} "
        f"ANTHROPIC_SMALL_FAST_MODEL={shlex.quote(model)} claude"
    )


def claude_magic(token: str, model: str, a_base: str) -> str:
    """«Пак мэджик»: ОДНА команда — сам создаёт лаунчер и запускает Claude Code.

    Почему пишем в свой ~/.wave/, а НЕ в ~/.claude/settings.json: у клиента там
    может быть своя рабочая настройка Claude Code, и перезапись стёрла бы её.
    Свой каталог self-contained, идемпотентен (перезапуск обновляет только наш
    лаунчер) и ничего чужого не трогает. Никакого curl|sh — весь скрипт виден
    клиенту прямо в команде, ключ оператора в нём не фигурирует.
    """
    launcher = (
        "#!/bin/sh\n"
        "# WAVE — Claude Code через шлюз WAVE. Ключ оператора клиенту не виден.\n"
        "command -v claude >/dev/null 2>&1 || { echo 'Сначала поставьте Claude "
        "Code: npm i -g @anthropic-ai/claude-code'; exit 1; }\n"
        f"export ANTHROPIC_BASE_URL={shlex.quote(a_base)}\n"
        f"export ANTHROPIC_AUTH_TOKEN={shlex.quote(token)}\n"
        f"export ANTHROPIC_MODEL={shlex.quote(model)}\n"
        f"export ANTHROPIC_SMALL_FAST_MODEL={shlex.quote(model)}\n"
        'exec claude "$@"\n'
    )
    return (
        "mkdir -p ~/.wave && cat > ~/.wave/start-claude.sh <<'WAVE_EOF'\n"
        f"{launcher}"
        "WAVE_EOF\n"
        "chmod +x ~/.wave/start-claude.sh && ~/.wave/start-claude.sh\n"
        "# дальше запускать так же: ~/.wave/start-claude.sh"
    )


def install_command(token: str, model: str, base_url: str, tool: str) -> str:
    """Одна команда, которая САМА кладёт конфиг на место.

    Никакого скачивания и исполнения чужого кода: команда целиком видна
    клиенту, он может её прочитать перед запуском.
    """
    if tool == "continue":
        cfg = continue_config(token, model, base_url)
        return (
            "mkdir -p ~/.continue && cat > ~/.continue/config.json <<'WAVE_EOF'\n"
            f"{cfg}\n"
            "WAVE_EOF"
        )
    if tool == "env":
        return (
            "cat > .env <<'WAVE_EOF'\n"
            f"{env_file(token, model, base_url)}"
            "WAVE_EOF"
        )
    if tool == "shell":
        return (
            "cat >> ~/.zshrc <<'WAVE_EOF'\n"
            f"\n# WAVE\n{shell_exports(token, model, base_url)}"
            "WAVE_EOF\n"
            "# затем: source ~/.zshrc"
        )
    return curl_check(token, model, base_url)


# ═══════════════════ Инструкции для человека ═══════════════════

CURSOR_STEPS = (
    "Settings → Models → OpenAI API Key\n"
    "1. Включите «Override OpenAI Base URL»\n"
    "2. Base URL: {base_url}\n"
    "3. API Key: {token}\n"
    "4. Model: {model}\n"
    "5. Нажмите Verify — должно стать зелёным"
)


def setup_payload(rec: dict, tool: str = "auto") -> dict:
    """Всё нужное для подключения одного ключа под выбранный инструмент.

    rec — запись ключа из QuotaStore. Возвращаем словарь, чтобы им могли
    пользоваться и бот, и кабинет, и тесты.
    """
    token = str(rec.get("token", ""))
    base_url = public_gateway()
    a_base = anthropic_base()
    model = model_for_key(rec)
    return {
        "token": token,
        "base_url": base_url,
        "anthropic_base_url": a_base,
        "model": model,
        "curl": curl_check(token, model, base_url),
        "cursor_steps": CURSOR_STEPS.format(base_url=base_url, token=token, model=model),
        "continue_json": continue_config(token, model, base_url),
        "cline_json": cline_config(token, model, base_url),
        "env": env_file(token, model, base_url),
        "shell": shell_exports(token, model, base_url),
        "python": python_snippet(token, model, base_url),
        "js": js_snippet(token, model, base_url),
        "install_continue": install_command(token, model, base_url, "continue"),
        "install_env": install_command(token, model, base_url, "env"),
        "install_shell": install_command(token, model, base_url, "shell"),
        # Claude Code — «пак мэджик»: одна команда → сам поднимается через шлюз.
        "claude_env": claude_env(token, model, a_base),
        "claude_oneliner": claude_oneliner(token, model, a_base),
        "claude_magic": claude_magic(token, model, a_base),
    }


TOOLS = [
    ("curl", "🧪 Проверить, что работает"),
    ("claude", "✨ Claude Code (одна команда)"),
    ("cursor", "🖥 Cursor"),
    ("continue", "🧩 Continue (VS Code)"),
    ("cline", "🤖 Cline / Roo Code"),
    ("env", "📄 Файл .env"),
    ("shell", "🐚 Переменные окружения"),
    ("python", "🐍 Python"),
    ("js", "🟨 JavaScript"),
]

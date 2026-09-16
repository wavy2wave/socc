#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ФОТО-КУЗНИЦА (PHOTO FORGE V1) — стадия DUB: исполнитель фото-трансформаций карточки.

ЗАЧЕМ. `uniqueizer_v1.photo_transform_plan()` строит ЧЕСТНЫЙ ПЛАН (новый белый фон, снять чужой
водяной знак, сломать перцептивный хеш — чтобы Ozon/ЯМ не приклеили нас к чужой карточке), но
сам пиксели не крутит и прямо пишет: «стадия ниже исполнит». Этой стадии не было. Это она.
Пиксели рисует Nano Banana (Google Gemini 2.5 Flash Image) через уже стоящий у нас OpenRouter.

ПАРА К ФОТО-ИСКАТЕЛЮ. `photo_hunter` ИЩЕТ чистый донорский кадр у первоисточника; кузница КУЁТ
свой уникальный кадр, когда чистого нет (или донорский — с чужим знаком). Выход кузницы
проверяет ТОТ ЖЕ хантер: не изобретаем второй приёмщик.

ПЯТЬ ЗАКОНОВ НАДЁЖНОСТИ («без ошибочно»):
  1. ДВОЙНОЙ ГЕЙТ dry→RUBICON. По умолчанию dry: собираем ТОЧНЫЙ запрос, считаем оценку ₽,
     наружу НИЧЕГО (0₽). Живой кадр — только флаг live=True (отмашка оператора). Как ymarket_write.
  2. 200 ≠ УСПЕХ. Не верим коду ответа: тянем картинку из тела; нет картинки → это не удача,
     а промах (ретрай). Родившийся кадр гоним через хантер: это картинка? нужного размера?
     чужой знак ушёл (OCR)? ДОСТАТОЧНО НЕПОХОЖ на донора (pHash — иначе МП склеит)?
  3. РЕТРАИ на транзиторное (429/5xx/сеть); 401/403 — сразу «это ключ, не код», без ретрай-шторма.
  4. ЧЕСТНАЯ ГРАНИЦА ПРАВ (как CLEAN/RISK у уникализатора). Два режима: generate (наши пиксели —
     чисто) и edit донора (производное — знак снят, но авторство исходной съёмки не наше →
     флаг прав, решает оператор). Орган НЕ врёт, что права чисты.
  5. ЧЕСТНОЕ «НЕ ЗНАЮ». Нет PIL/OCR → часть проверок помечается 'не проверено — глазами
     оператора', а НЕ выдаётся за «годится» (закон L3 линии, как в photo_hunter).

Учёт: каждый ЖИВОЙ кадр — событие расхода в state/photoforge_ledger.json (реальная цена из
usage ответа, иначе оценка). Деньги органа под учётом.

stdlib-only (urllib/base64/json/hashlib), ленивый: модуль грузится без сети/ключей/PIL — dry живёт.
Секреты — только из gitignored .env через socc_mint_env_v1 (наружу лишь ИМЕНА переменных).
"""
import base64
import json
import os
import re
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state"
LEDGER = STATE / "photoforge_ledger.json"
OUT_DIR = STATE / "forged"

# ── ДВА ПРОВАЙДЕРА одной Nano Banana (Google Gemini 2.5 Flash Image) ─────────────────
# OpenRouter — OpenAI-совместимый шлюз (Bearer, /chat/completions, слаг google/…). Платный.
# Google AI Studio — родной REST (x-goog-api-key, :generateContent). Есть БЕСПЛАТНЫЙ tier.
# Выбор автоматический по наличию ключа (Google предпочтителен: даровая картинка); можно
# принудительно PHOTO_FORGE_PROVIDER=google|openrouter. Оба пути — аддитивно, dry живёт без обоих.
OPENROUTER_API = "https://openrouter.ai/api/v1"
CHAT_PATH = "/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash-image"      # Nano Banana на OpenRouter (слаг уточнить)

GOOGLE_API = "https://generativelanguage.googleapis.com/v1beta"
GOOGLE_DEFAULT_MODEL = "gemini-2.5-flash-image"      # Nano Banana в родном API Google AI Studio

# ── ТРЕТИЙ ПРОВАЙДЕР: Kandinsky / FusionBrain (Сбер) — единственный ДОСТИЖИМЫЙ из РФ ──────
# Причина: Google generativelanguage режется на входе из РФ-egress этой машины (гео-блок ДО ключа),
# а OpenRouter требует зарубежную карту. FusionBrain — российский, из РФ НАПРЯМУЮ (без VPN/карты),
# бесплатный официальный REST. НО это генератор С НУЛЯ (диффузия), НЕ редактор донора как Nano Banana:
# годится ТОЛЬКО для mode='generate' (наши пиксели по фактам — ровно цель «свои карточки, своя цена»).
# Авторизация — ДВА заголовка: X-Key: Key <ключ> + X-Secret: Secret <секрет>. Пайплайн АСИНХРОННЫЙ:
#   1) GET  /key/api/v1/pipelines            → список, берём id (UUID) пайплайна Kandinsky;
#   2) POST /key/api/v1/pipeline/run         → multipart (pipeline_id + params-JSON) → {uuid,status:INITIAL};
#   3) GET  /key/api/v1/pipeline/status/{u}  → пуллим до DONE → result.files[0] = ГОЛЫЙ base64 (+censored).
# censored=true = контент отбит цензором (тихо режет выход) — ловим как ПРОМАХ (как «200 ≠ успех»).
FUSIONBRAIN_API = "https://api-key.fusionbrain.ai"
FUSIONBRAIN_PIPELINES = "/key/api/v1/pipelines"
FUSIONBRAIN_RUN = "/key/api/v1/pipeline/run"
FUSIONBRAIN_STATUS = "/key/api/v1/pipeline/status/"   # + request uuid
FUSIONBRAIN_DEFAULT_MODEL = "kandinsky"               # ярлык для лога (реальный pipeline_id берём живьём)
_FB_CARD_W = 1024                                     # кратно 64; 1024×1280 = 4:5 (канон карточки)
_FB_CARD_H = 1280
_FB_POLL_MAX = 30                                     # столько раз спрашиваем статус
_FB_POLL_DELAY = 3.0                                  # секунд между опросами (диффузия небыстрая)

# ── ЧЕТВЁРТЫЙ ПРОВАЙДЕР: RU-агрегатор на OpenAI Images API (neuroapi/aitunnel) ─────────
# Причина: google/openrouter/openai гео-режутся из РФ-egress этой машины ДО проверки ключа,
# а FusionBrain недоступен с этой сети. RU-агрегаторы (neuroapi.host, aitunnel.ru) ДОХОДЯТ из РФ
# напрямую (проверено живьём: 401/insufficient_quota, не гео-стена) и дают доступ к той же Nano
# Banana новее (gemini-3.x-flash-image) + gpt-image за рубли. ФОРМА — OpenAI Images API, ИНАЯ, чем
# chat/completions (openrouter) и generateContent (google): POST /v1/images/generations c телом
# {model,prompt,n,response_format:b64_json[,size]}, картинка в data[].b64_json (ГОЛЫЙ base64).
# Значит это отдельная патчабельная ветвь (как fusionbrain), а проверенные пути остаются байт-в-байт.
# Только generate (наши пиксели — ровно доктрина «СВОИ пиксели, наша цена»); edit донора (multipart
# /images/edits) НЕ поддерживаем в этой ветви → честный откат edit→generate, как у Kandinsky.
RU_OPENAI_API = "https://neuroapi.host/v1"            # база по умолчанию; override RU_OPENAI_BASE_URL
RU_OPENAI_IMAGES_PATH = "/images/generations"         # OpenAI Images generate (JSON, ложится на _request)
RU_OPENAI_DEFAULT_MODEL = "gemini-3.1-flash-lite-image"   # самый дешёвый наследник Nano Banana (~$0.02)
RU_OPENAI_EST_USD = 0.02                              # оценка кадра; факт возьмём из usage, если вернёт

# ── ПЯТЫЙ ПРОВАЙДЕР: YandexART (Яндекс Cloud) — САМЫЙ дешёвый РФ-канал (~$0.0176/card flat) ───
# Ультрасвип 2026-09-08: first-party Яндекс, modelUri art://<folder_id>/yandex-art/latest, эндпоинт
#   POST https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync  (АСИНХРОННО)
# → Operation{id}; поллить GET /operations/<id> до done:true → response.image = ГОЛЫЙ base64 JPEG.
# Синк-путь /imageGeneration = 404 (не существует). Цена ПЛОСКАЯ за запрос ($0.0176 ≈1.6-2.2₽),
# ~1.8× дешевле вшитого ru_openai (VseGPT flux 3.9₽). 0₽-старт: триал 30д + playground без платёжки;
# РФ-карта, депозита/флора 1000₽ НЕТ. Auth: сервисный аккаунт + роль ai.art.user на каталог → API-ключ.
# ИЗОЛЯЦИЯ ОРГАНА: свои YAART_API_KEY + YAART_FOLDER_ID (алиас YC_API_KEY/YC_FOLDER_ID); НИКОГДА не
# берём пару S3-статиков YC_ACCESS_KEY_ID/YC_SECRET_KEY (.env) — это другой сервис, ключ не подойдёт.
# Всегда шлём aspectRatio widthRatio:4/heightRatio:5 (4:5 РОДНОЙ для карточки; без него квадрат 1:1).
# Форма тела ИНАЯ (modelUri+messages), поэтому — отдельная патчабельная ветвь как fusionbrain/ru_openai.
YAART_API = "https://llm.api.cloud.yandex.net"        # хост (НЕ .yandexcloud.net — на нём 404)
YAART_GEN_PATH = "/foundationModels/v1/imageGenerationAsync"
YAART_OPS_PATH = "/operations/"                       # + operation id (поллинг результата)
YAART_DEFAULT_MODEL = "yandex-art/latest"             # ярлык для лога; реальная модель = art://<folder>/…
YAART_EST_USD = 0.0176                                # flat-оценка кадра; факт — в биллинге кабинета (у op нет usage)
_YA_POLL_MAX_SEC = 200                                # генерция async может идти минуты (доки: «от пары минут»)
_YA_POLL_DELAY = 3.0                                  # секунд между опросами операции

# Транзиторные http-коды: моргнуло → ограниченный ретрай (не демон). 401/403 — ключи, НЕ ретраим.
_TRANSIENT = (408, 409, 429, 500, 502, 503, 504)
_MAX_RETRIES = 3

# Оценка цены кадра (Nano Banana ≈ 1290 ток/изобр. × ~$30/M ≈ $0.04). Факт берём из usage ответа.
EST_USD_PER_IMAGE = 0.04

# Порог уникальности: hamming(new, donor) ДОЛЖЕН быть велик, иначе МП склеит карточки.
MIN_DONOR_HAMMING = 10

_ENV_TRIED = False


# ── Секреты и окружение (ленивая загрузка, закон секретности) ──────────────────────
def _ensure_env():
    """Один раз подтянуть gitignored .env. Fail-soft вдвойне: загрузчик не имеет права уронить dry."""
    global _ENV_TRIED
    if _ENV_TRIED:
        return
    _ENV_TRIED = True
    try:
        import socc_mint_env_v1 as env          # noqa: F811
    except Exception:
        try:
            import sys
            mint = str(HERE.parent)              # SOCC/scripts/mint
            if mint not in sys.path:
                sys.path.insert(0, mint)
            import socc_mint_env_v1 as env      # noqa: F811
        except Exception:
            return
    try:
        env.ensure_env()
    except Exception:
        pass


def _openrouter_key():
    """Ключ OpenRouter — ТОЛЬКО родной OPENROUTER_API_KEY. Изоляция органа (решение оператора):
    ARBITER-кузница НИКОГДА молча не берёт OPENAI_API_KEY соседа (wavecore-bot/ANNA) — тот ключ для
    api.openai.com и на openrouter.ai даст 401, а тихое заимствование чужого ключа = скрытая утечка
    расхода между органами. Нет OPENROUTER_API_KEY → openrouter обезоружен (сухой режим), это честно."""
    _ensure_env()
    return os.getenv("OPENROUTER_API_KEY") or None


def _google_key():
    """Ключ Google AI Studio (AIza…). Родной REST Gemini — есть БЕСПЛАТНЫЙ tier для Nano Banana."""
    _ensure_env()
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GOOGLE_AI_STUDIO_KEY") or None)


def _fusionbrain_keys():
    """Пара ключей FusionBrain/Kandinsky: (api_key, secret_key). Оба обязательны для живого режима."""
    _ensure_env()
    return (os.getenv("FUSIONBRAIN_API_KEY") or None, os.getenv("FUSIONBRAIN_SECRET_KEY") or None)


def _fusionbrain_ready():
    """Есть ОБА ключа FusionBrain (X-Key + X-Secret)? Один без другого = не готов (авторизация парная)."""
    k, s = _fusionbrain_keys()
    return bool(k and s)


def _ru_openai_key():
    """Ключ RU-агрегатора (neuroapi/aitunnel) — ТОЛЬКО родные NEUROAPI_API_KEY / RU_OPENAI_API_KEY.
    Изоляция органа (как у openrouter): НИКОГДА молча не берём чужой OPENAI_API_KEY соседа — тот ключ
    для api.openai.com, на агрегаторе даст 401, а тихое заимствование чужого ключа = скрытая утечка
    расхода между органами. Нет родного ключа → RU-канал обезоружен (сухой режим), это честно."""
    _ensure_env()
    return os.getenv("NEUROAPI_API_KEY") or os.getenv("RU_OPENAI_API_KEY") or None


def _ru_openai_model():
    """Слаг модели RU-агрегатора: override RU_OPENAI_MODEL, иначе дешёвый дефолт. У разных агрегаторов
    слаги РАЗНЫЕ (neuroapi: gemini-*-image, proxyapi: dall-e-3, vsegpt/deepinfra: flux), а канал уже
    целиком env-настраиваемый (ключ+база+провайдер) — модель ОБЯЗАНА быть тем же рычагом, иначе смена
    агрегатора требует правки кода. Единый источник: и _default_model, и живой _forge_ru_openai зовут
    ЭТО. Env не задан → RU_OPENAI_DEFAULT_MODEL (поведение байт-в-байт как раньше)."""
    _ensure_env()
    return os.getenv("RU_OPENAI_MODEL") or RU_OPENAI_DEFAULT_MODEL


def _yaart_key():
    """API-ключ сервисного аккаунта Yandex Cloud для YandexART — ТОЛЬКО родные
    YAART_API_KEY / YC_API_KEY. Изоляция органа: НИКОГДА не берём S3-статики YC_ACCESS_KEY_ID/
    YC_SECRET_KEY (они для AWS-совместимого бакета, на foundationModels дадут 401) и чужой ключ соседа.
    Нет ключа → канал обезоружен (сухой режим), это честно.

    РОЛЬ: в докстринге раньше стояло `ai.art.user` — такой роли в Yandex Cloud НЕ СУЩЕСТВУЕТ.
    Проверено живьём 15.09.2026 (`yc iam role list`, 733 роли): верная роль —
    **`ai.imageGeneration.user`**. Выдаётся на каталог сервисному аккаунту."""
    _ensure_env()
    return os.getenv("YAART_API_KEY") or os.getenv("YC_API_KEY") or None


def _yaart_folder():
    """folder_id каталога, где живёт art://<folder_id>/yandex-art/latest. Без каталога modelUri не собрать."""
    _ensure_env()
    return (os.getenv("YAART_FOLDER_ID") or os.getenv("YC_FOLDER_ID") or "").strip()


def _yaart_ready():
    """Канал YandexART готов: есть И ключ, И folder_id (обязательная пара, как у fusionbrain)."""
    return bool(_yaart_key() and _yaart_folder())


def _yaart_model_uri():
    """modelUri для YandexART: art://<folder_id>/yandex-art/latest (каталог задаёт, ГДЕ живёт модель;
    чужой каталог шлюз отвергает: «does not match with service account folder ID»). Пустой каталог →
    заглушка art:///… — живой путь без каталога не пустится, это честно видно в превью."""
    folder = _yaart_folder()
    return "art://%s/yandex-art/latest" % folder if folder else "art:///yandex-art/latest"


def _provider():
    """Какой шлюз к генерации использовать. Override
    PHOTO_FORGE_PROVIDER=google|openrouter|fusionbrain|ru_openai|yandexart;
    иначе google при ключе AIza (даровая Nano Banana), иначе fusionbrain при паре ключей Kandinsky,
    иначе yandexart при ключе+папке (дешёвый РФ-канал), иначе ru_openai при родном ключе RU-агрегатора
    (ПЛАТНЫЙ, но достижимый из РФ — openrouter/google гео-режутся), иначе openrouter (дефолт)."""
    _ensure_env()
    forced = (os.getenv("PHOTO_FORGE_PROVIDER") or "").strip().lower()
    if forced in ("google", "openrouter", "fusionbrain", "ru_openai", "yandexart"):
        return forced
    if _google_key():
        return "google"
    if _fusionbrain_ready():
        return "fusionbrain"
    if _yaart_ready():
        return "yandexart"
    if _ru_openai_key():
        return "ru_openai"
    return "openrouter"


def _api_key():
    """Ключ АКТИВНОГО провайдера (см. _provider)."""
    prov = _provider()
    if prov == "google":
        return _google_key()
    if prov == "ru_openai":
        return _ru_openai_key()
    return _openrouter_key()


def _base_url():
    """База активного провайдера. openrouter → PHOTO_FORGE_BASE_URL/OpenRouter; google → GEMINI_BASE_URL/Google;
    ru_openai → RU_OPENAI_BASE_URL/RU_OPENAI_API (neuroapi, база уже с /v1 → путь без повторного /v1)."""
    _ensure_env()
    if _provider() == "google":
        return (os.getenv("GEMINI_BASE_URL") or os.getenv("PHOTO_FORGE_BASE_URL") or GOOGLE_API).rstrip("/")
    if _provider() == "ru_openai":
        return (os.getenv("RU_OPENAI_BASE_URL") or RU_OPENAI_API).rstrip("/")
    return (os.getenv("PHOTO_FORGE_BASE_URL") or OPENROUTER_API).rstrip("/")


def _default_model():
    """Слаг активного провайдера (у Google — свой без префикса google/; у FusionBrain — ярлык kandinsky;
    у yandexart — modelUri art://<folder>/yandex-art/latest; у ru_openai — override RU_OPENAI_MODEL,
    иначе самый дешёвый наследник Nano Banana на агрегаторе)."""
    prov = _provider()
    if prov == "google":
        return GOOGLE_DEFAULT_MODEL
    if prov == "fusionbrain":
        return FUSIONBRAIN_DEFAULT_MODEL
    if prov == "yandexart":
        return _yaart_model_uri()
    if prov == "ru_openai":
        return _ru_openai_model()
    return DEFAULT_MODEL


def _endpoint_path(model=None):
    """Путь запроса под провайдера. openrouter → /chat/completions; google → /models/<slug>:generateContent;
    ru_openai → /images/generations (OpenAI Images, тело с top-level prompt)."""
    if _provider() == "google":
        return "/models/%s:generateContent" % (model or GOOGLE_DEFAULT_MODEL)
    if _provider() == "ru_openai":
        return RU_OPENAI_IMAGES_PATH
    return CHAT_PATH


def creds_present():
    """Есть ли ключ ХОТЬ ОДНОГО провайдера для живого режима. Без ключей — только dry (0₽), без падения."""
    return bool(_google_key() or _openrouter_key() or _fusionbrain_ready() or _yaart_key() or _ru_openai_key())


# ── Паспорт возможностей (честно, что орган РЕАЛЬНО умеет здесь) ────────────────────
def capabilities():
    caps = {"key": creds_present(), "net": True, "image_probe": False, "ocr": False}
    try:
        import PIL  # noqa: F401
        caps["image_probe"] = True
    except Exception:
        pass
    try:
        import photo_hunter_v1 as hunter        # noqa: F811
        caps["ocr"] = bool(hunter.have_tesseract())
    except Exception:
        try:
            import sys
            if str(HERE) not in sys.path:
                sys.path.insert(0, str(HERE))
            import photo_hunter_v1 as hunter    # noqa: F811
            caps["ocr"] = bool(hunter.have_tesseract())
        except Exception:
            pass
    return caps


# ── Шов сети (единственное место реальной сети; тесты патчат ИМЕННО его) ────────────
class ForgeHTTPError(RuntimeError):
    """HTTP-ошибка шлюза с кодом и телом — чтобы вызывающий честно разобрал причину."""
    def __init__(self, status, body, url):
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"OpenRouter {status} {url}: {str(body)[:300]}")


class _Resp:
    """Лёгкий носитель http-исхода (status_code + json/text) — чтобы шов и тесты не тянули requests."""
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("не JSON")
        return self._payload


def _headers():
    key = _api_key()
    prov = _provider()
    if not key:
        raise RuntimeError(
            "нет ключа для активного провайдера %r (google: GEMINI_API_KEY/GOOGLE_API_KEY · "
            "openrouter: OPENROUTER_API_KEY · ru_openai: NEUROAPI_API_KEY/RU_OPENAI_API_KEY) — "
            "живой режим недоступен, используй dry; ключ впиши в mint/.env, он gitignored" % prov)
    if prov == "google":
        # Google AI Studio: ключ в заголовке x-goog-api-key (не в url → не течёт в логи прокси).
        return {"x-goog-api-key": key, "Content-Type": "application/json"}
    if prov == "ru_openai":
        # RU-агрегатор (neuroapi/aitunnel): чистый Bearer OpenAI-совместимо, без вежливых заголовков OpenRouter.
        return {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    # OpenRouter авторизуется Bearer-токеном. Referer/Title — вежливые (необязательные) заголовки.
    return {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("PHOTO_FORGE_REFERER", "https://socc.local/arbiter"),
        "X-Title": "SOCC ARBITER photo-forge",
    }


def _http_call(method, url, headers, body, timeout):
    """Один реальный вызов сети через stdlib urllib → _Resp. Ленивый: dry/тесты сюда не заходят."""
    import urllib.request
    import urllib.error
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            status = r.getcode()
    except urllib.error.HTTPError as e:               # не-2xx приходит сюда как исключение
        raw = e.read() if hasattr(e, "read") else b""
        status = e.code
    text = raw.decode("utf-8", "ignore")
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    return _Resp(status, payload, text)


def _safe_json(r):
    try:
        return r.json()
    except Exception:
        return {"raw": getattr(r, "text", "")}


def _request(method, path, body=None, timeout=120):
    """Устойчивый вызов к шлюзу. 401/403→сразу ключи; 429/5xx/timeout→ретрай; иной не-2xx→ошибка."""
    url = _base_url() + path
    retries = 0
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            r = _http_call(method, url, _headers(), body, timeout)
        except Exception as e:                         # сетевой сбой/timeout — транзиторный
            last_exc = e
            if attempt + 1 < _MAX_RETRIES:
                import random
                time.sleep(0.5 + random.random() * 1.0)
                retries += 1
                continue
            raise RuntimeError(f"сеть к OpenRouter упала после {retries} ретраев: {e}")
        if r.status_code in (401, 403):
            raise ForgeHTTPError(r.status_code, _safe_json(r), url)     # ключи/права, не код
        if r.status_code in _TRANSIENT and attempt + 1 < _MAX_RETRIES:
            import random
            time.sleep(0.5 + random.random() * 1.0)
            retries += 1
            continue
        if not (200 <= r.status_code < 300):
            raise ForgeHTTPError(r.status_code, _safe_json(r), url)
        return _safe_json(r)
    raise RuntimeError(f"исчерпаны ретраи к {url} (последняя ошибка: {last_exc})")


# ── Шов сети FusionBrain (ЕДИНСТВЕННОЕ место реальной сети Kandinsky; тесты патчат ИМЕННО _fb_call) ──
# Отдельный от _request: у FusionBrain своя парная авторизация (X-Key/X-Secret) и multipart-POST,
# которых нет у openrouter/google. Держим одну патчабельную точку → приёмка 0₽/0-сети.
_FB_BOUNDARY = "----SOCCArbiterFusionBrainBoundary7f3a2b"


def _fb_base():
    _ensure_env()
    return (os.getenv("FUSIONBRAIN_BASE_URL") or FUSIONBRAIN_API).rstrip("/")


def _fb_headers():
    """Парная авторизация FusionBrain. Нет пары ключей → RuntimeError (живой путь недоступен, dry жив)."""
    key, secret = _fusionbrain_keys()
    if not (key and secret):
        raise RuntimeError(
            "нет ключей FusionBrain (FUSIONBRAIN_API_KEY + FUSIONBRAIN_SECRET_KEY) — живой режим "
            "недоступен, используй dry; ключи впиши в mint/.env, он gitignored")
    return {"X-Key": "Key " + key, "X-Secret": "Secret " + secret}


def _multipart_body(fields):
    """Собрать multipart/form-data вручную (stdlib). fields: [(name, value, content_type|None)].

    content_type=None → простое текстовое поле; иначе часть с явным Content-Type (для params-JSON).
    Возвращает (body_bytes, content_type_header). Граница фиксированная (не встречается в наших данных)."""
    import io
    buf = io.BytesIO()
    b = _FB_BOUNDARY
    for name, value, ctype in fields:
        buf.write(("--%s\r\n" % b).encode("utf-8"))
        disp = 'Content-Disposition: form-data; name="%s"\r\n' % name
        buf.write(disp.encode("utf-8"))
        if ctype:
            buf.write(("Content-Type: %s\r\n" % ctype).encode("utf-8"))
        buf.write(b"\r\n")
        buf.write(value.encode("utf-8") if isinstance(value, str) else value)
        buf.write(b"\r\n")
    buf.write(("--%s--\r\n" % b).encode("utf-8"))
    return buf.getvalue(), "multipart/form-data; boundary=%s" % b


def _fb_call(method, path, multipart=None, timeout=90):
    """Один реальный вызов сети к FusionBrain → _Resp. Ленивый: dry/тесты сюда не заходят.

    multipart=(body_bytes, content_type) → POST /run (тело формы); иначе GET без тела (pipelines/status).
    """
    import urllib.request
    import urllib.error
    url = _fb_base() + path
    headers = dict(_fb_headers())
    data = None
    if multipart is not None:
        data, ctype = multipart
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            status = r.getcode()
    except urllib.error.HTTPError as e:
        raw = e.read() if hasattr(e, "read") else b""
        status = e.code
    text = raw.decode("utf-8", "ignore")
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    return _Resp(status, payload, text)


def _fb_pipeline_id():
    """GET /pipelines → id (UUID) первого пайплайна (Kandinsky). Пусто/ошибка → честное исключение."""
    r = _fb_call("GET", FUSIONBRAIN_PIPELINES)
    url = _fb_base() + FUSIONBRAIN_PIPELINES
    if r.status_code in (401, 403):
        raise ForgeHTTPError(r.status_code, _safe_json(r), url)
    if not (200 <= r.status_code < 300):
        raise ForgeHTTPError(r.status_code, _safe_json(r), url)
    data = _safe_json(r)
    if isinstance(data, list) and data:
        pid = (data[0] or {}).get("id")
        if pid:
            return pid
    raise RuntimeError("FusionBrain: не удалось получить pipeline_id (пустой список пайплайнов)")


def _fb_run(pipeline_id, params):
    """POST /pipeline/run (multipart pipeline_id + params-JSON) → request uuid. 401/403 → ключи.

    Из params снимаем служебный маркер 'provider' (он только для _preview/тестов) — в сеть уходит
    ровно ожидаемая FusionBrain форма {type,numImages,width,height,generateParams}."""
    wire = {k: v for k, v in (params or {}).items() if k != "provider"}
    body, ctype = _multipart_body([
        ("pipeline_id", str(pipeline_id), None),
        ("params", json.dumps(wire, ensure_ascii=False), "application/json"),
    ])
    r = _fb_call("POST", FUSIONBRAIN_RUN, multipart=(body, ctype))
    url = _fb_base() + FUSIONBRAIN_RUN
    if r.status_code in (401, 403):
        raise ForgeHTTPError(r.status_code, _safe_json(r), url)
    if not (200 <= r.status_code < 300):
        raise ForgeHTTPError(r.status_code, _safe_json(r), url)
    data = _safe_json(r)
    uuid = data.get("uuid") if isinstance(data, dict) else None
    if not uuid:
        raise RuntimeError("FusionBrain: /run не вернул uuid: %s" % str(data)[:200])
    return uuid


def _fb_status(request_uuid):
    """GET /pipeline/status/{uuid} → распарсенный статус-json. Не-2xx → ForgeHTTPError."""
    url = _fb_base() + FUSIONBRAIN_STATUS + str(request_uuid)
    r = _fb_call("GET", FUSIONBRAIN_STATUS + str(request_uuid))
    if not (200 <= r.status_code < 300):
        raise ForgeHTTPError(r.status_code, _safe_json(r), url)
    return _safe_json(r)


def _fb_poll(request_uuid, max_attempts=_FB_POLL_MAX, delay=_FB_POLL_DELAY):
    """Пуллим статус до DONE. FAIL/ERROR → исключение с причиной; вышло время → честный таймаут."""
    last = None
    for _ in range(max_attempts):
        st = _fb_status(request_uuid)
        last = st
        status = (st.get("status") or "").upper() if isinstance(st, dict) else ""
        if status == "DONE":
            return st
        if status in ("FAIL", "ERROR"):
            why = ""
            if isinstance(st, dict):
                why = st.get("errorDescription") or st.get("error") or ""
            raise RuntimeError("FusionBrain: задача упала (%s): %s" % (status, str(why)[:200]))
        time.sleep(delay)
    raise RuntimeError("FusionBrain: задача не завершилась за %d опросов (uuid=%s, последний статус=%s)"
                       % (max_attempts, request_uuid, (last or {}).get("status") if isinstance(last, dict) else "?"))


def _fb_extract(status_json):
    """DONE-статус → (raw_bytes|None, censored:bool). base64 в result.files[] (или старом images[]).

    Возвращаем первый декодируемый КАДР (сигнатура картинки). censored=true при пустом кадре = ПРОМАХ
    (цензор тихо срезал вывод) — вызывающий обязан различить это от честной картинки."""
    if not isinstance(status_json, dict):
        return None, False
    result = status_json.get("result") or {}
    censored = bool(result.get("censored") or status_json.get("censored"))
    files = result.get("files") or status_json.get("images") or []
    if not isinstance(files, list):
        files = []
    for b64 in files:
        if not b64 or not isinstance(b64, str):
            continue
        payload = b64.split(",", 1)[-1] if b64.startswith("data:") else b64
        try:
            raw = base64.b64decode(payload, validate=False)
        except Exception:
            raw = None
        if raw and _magic_is_image(raw):
            return raw, censored
    return None, censored


# ── Промпт: план уникализации → инструкция для Nano Banana ──────────────────────────
# Перевод машинных ops (uniqueizer.photo_transform_plan) в человеческую инструкцию модели.
OP_INSTRUCTIONS = {
    "crop_aspect_4x5": "кадрируй в вертикальную пропорцию 4:5 (формат карточки маркетплейса)",
    "mirror_horizontal_if_safe": "при необходимости отрази по горизонтали, если это не искажает товар",
    "add_margin_border_3pct": "оставь аккуратные равные поля примерно 3% вокруг товара",
    "color_temp_nudge": "нейтрализуй баланс белого, чистый ровный дневной свет, без цветного оттенка",
    "recompose_on_white_bg": "размести товар на чистом ровном белом фоне (#FFFFFF), студийный свет, мягкая естественная тень",
    "watermark_own": ("полностью убери любые ЧУЖИЕ водяные знаки, логотипы магазинов и надписи "
                      "(цена, телефон, адрес сайта, «оптом»); НЕ добавляй никакого нового текста"),
}
DEFAULT_OPS = ["recompose_on_white_bg", "add_margin_border_3pct", "color_temp_nudge",
               "crop_aspect_4x5", "watermark_own"]

# Ядро верности: тот же товар, ничего не выдумываем, без надписей на кадре.
_FIDELITY = ("Сохрани товар точно таким же: форма, цвет, материал, пропорции, комплектность. "
             "Не добавляй деталей, которых нет на исходном товаре. Никакого текста на изображении.")

# ── БРЕНД-СТИЛЬ ATLAS EDGE SHOP: единый «почерк» ВСЕХ карточек ────────────────────────
# Наш бренд — это НЕ логотип на фото (маркетплейс его запрещает), а один и тот же визуальный
# контракт на каждом кадре: белый фон #FFFFFF, студийный ровный свет, мягкая тень, товар в центре,
# вертикаль 4:5. Так наши карточки узнаваемы как СВОИ, а МП никогда не отбивает фон. Контракт
# ДЕТЕРМИНИРОВАН (одинаков для любого товара) и живёт в head промпта — значит его видно в _preview
# (он режет хвост до 180 символов) и он не зависит от порядка ops. Валидатор verify_canon сверяет,
# что кадр действительно родился в этом стиле (белый фон + пропорция) — «бронированность».
BRAND_NAME = "ATLAS EDGE SHOP"
_BRAND_STYLE = ("Единый фирменный стиль карточки: чистый ровный БЕЛЫЙ фон #FFFFFF без градиента и "
                "предметов, товар строго по центру кадра и КРУПНО — занимает почти весь кадр "
                "(≈85% высоты), небольшие равные поля по краям, мягкая естественная тень под "
                "товаром, ровный студийный дневной свет, вертикальная пропорция 4:5. "
                "Никакого логотипа, водяного знака и текста на изображении.")
# По умолчанию бренд-стиль ВКЛЮЧЁН (brand=None → BRAND_STYLE_DEFAULT). False у build_prompt даёт
# точный старый текст (обратная совместимость приёмки F1-F23).
BRAND_STYLE_DEFAULT = True


# ── ПЕРЕВОДЧИК ГАБАРИТОВ → ЯЗЫК ПРОПОРЦИЙ (корень «товар визуально не по запросу») ──────
# Модель (FLUX и пр.) НЕ понимает «600×400×400 мм» как форму — для неё это просто токены, потому
# рисует обобщённый почти-куб. Оператор бьёт в это: «размер снова другой даже визуально». Лечим
# генерацией: парсим числа габаритов → относительные пропорции (единицы сокращаются) → фраза на
# языке, который модель СЛУШАЕТ: куб/вытянут/плоский + во сколько раз длиннее. Аддитивно: без
# разборных габаритов (≥2 чисел) возвращаем "" → промпт байт-в-байт как раньше (приёмка F1-F23 цела).
_DIM_KEYS = ("размер", "размеры", "габариты", "габарит", "dimensions", "size", "д×ш×в", "длина×ширина×высота")


def _parse_dims(facts):
    """Первый факт-габарит с ≥2 положительными числами → (список сторон[:3], сырая строка). Иначе (None,'')."""
    facts = facts or {}
    low = {str(k).strip().lower(): str(v) for k, v in facts.items() if v not in (None, "", [])}
    for k in _DIM_KEYS:
        if k in low and low[k].strip():
            raw = low[k].strip()
            nums = re.findall(r"\d+(?:[.,]\d+)?", raw)
            vals = [float(n.replace(",", ".")) for n in nums]
            vals = [v for v in vals if v > 0]
            if len(vals) >= 2:
                return vals[:3], raw
    return None, ""


def _shape_hint(facts):
    """Габариты → одна фраза о форме на языке модели. '' если габаритов нет/не разобрать (аддитивно)."""
    vals, raw = _parse_dims(facts)
    if not vals:
        return ""
    s = sorted(vals, reverse=True)
    hi, lo = s[0], s[-1]
    if lo <= 0:
        return ""
    ratio = hi / lo
    if ratio < 1.12:                                   # все стороны ~равны
        return ("Форма товара близка к КУБИЧЕСКОЙ/квадратной: стороны примерно равны (%s) — "
                "рисуй ровный куб-короб, НЕ вытянутый. " % raw)
    r = ("%.1f" % ratio).rstrip("0").rstrip(".")
    hint = ("Пропорции по габаритам %s: это НЕ куб — прямоугольная форма, самая длинная сторона "
            "примерно в %s× больше самой короткой. " % (raw, r))
    if len(s) == 3:
        a, b, c = s
        if a >= b * 1.18 and b <= c * 1.18:            # одна длинная, две ~равные
            hint += "Товар вытянут в длину (продолговатая коробка), две другие стороны равны между собой. "
        elif a <= b * 1.18 and b >= c * 1.18:          # две ~равные большие, одна маленькая
            hint += "Товар низкий и широкий (плоская коробка), высота заметно меньше основания. "
        else:
            hint += "Все три стороны разной длины — явно прямоугольный короб без равных граней. "
    else:
        hint += "Силуэт вытянутый прямоугольный. "
    return hint + "Точно передай эти пропорции в кадре. "


def _facts_line(facts):
    """Известные факты о товаре — чтобы модель не искажала суть (ширина, цвет, материал, вид)."""
    if not facts:
        return ""
    pairs = [f"{k}: {v}" for k, v in facts.items() if v not in (None, "", [])]
    return ("Известное о товаре (сохрани точно): " + "; ".join(pairs) + ". ") if pairs else ""


def build_prompt(facts=None, ops=None, mode="edit", brand=None):
    """Собрать текст-инструкцию для модели из фактов о товаре и плана трансформаций.

    mode='edit' — переработать поданное донорское фото; 'generate' — нарисовать с нуля по фактам.
    ops — список машинных операций плана (uniqueizer); None → разумный дефолт под карточку МП.
    brand — фирменный стиль ATLAS EDGE в head: None → BRAND_STYLE_DEFAULT (вкл.), True → вкл.,
    False → старый текст без бренд-контракта (обратная совместимость). Стиль в head (а не в хвосте),
    чтобы он был виден в _preview (тот режет до 180 символов) и не зависел от порядка ops.
    """
    ops = list(ops) if ops else list(DEFAULT_OPS)
    steps = [OP_INSTRUCTIONS[o] for o in ops if o in OP_INSTRUCTIONS]
    # watermark-снятие обязательно для edit, даже если план его не перечислил (это главный риск).
    if mode == "edit" and not any("водян" in s for s in steps):
        steps.append(OP_INSTRUCTIONS["watermark_own"])
    body = "; ".join(steps)
    brand_on = BRAND_STYLE_DEFAULT if brand is None else bool(brand)
    brand_head = (_BRAND_STYLE + " ") if brand_on else ""
    shape = _shape_hint(facts)                          # габариты → язык пропорций (аддитивно; '' без габаритов)
    shape_head = (shape if shape else "")
    if mode == "generate":
        head = ("Создай реалистичное студийное предметное фото товара для карточки маркетплейса. "
                + _facts_line(facts) + shape_head + brand_head)
    else:
        head = ("Вот фото товара. Переработай его в чистую студийную карточку для маркетплейса. "
                + _facts_line(facts) + shape_head + brand_head)
    return f"{head}Требования: {body}. {_FIDELITY}"


def build_request(prompt, source_image_b64=None, model=None, provider=None):
    """ТОЧНОЕ тело запроса под АКТИВНЫЙ провайдер (openrouter | google). provider=None → авто.

    Это ровно то, что печатает dry и инспектирует приёмка — потому провайдер можно задать явно
    (детерминированные тесты формы), иначе берётся из окружения.
    """
    prov = provider or _provider()
    if prov == "google":
        return _build_request_google(prompt, source_image_b64, model)
    if prov == "fusionbrain":
        return _build_request_fusionbrain(prompt)
    if prov == "ru_openai":
        return _build_request_ru_openai(prompt, model)
    if prov == "yandexart":
        return _build_request_yandexart(prompt)
    return _build_request_openrouter(prompt, source_image_b64, model)


def _build_request_fusionbrain(prompt, width=_FB_CARD_W, height=_FB_CARD_H, num_images=1):
    """params-тело FusionBrain /pipeline/run (генерация С НУЛЯ; донор не прикладывается — Kandinsky
    не редактор). Размеры кратны 64; 1024×1280 = 4:5 (канон карточки). Ключ 'provider' — только маркер
    для _preview/тестов; _fb_run снимает его перед отправкой (в сеть уходит чистая форма)."""
    return {
        "provider": "fusionbrain",
        "type": "GENERATE",
        "numImages": num_images,
        "width": width,
        "height": height,
        "generateParams": {"query": prompt},
    }


def _build_request_openrouter(prompt, source_image_b64=None, model=None):
    """OpenAI-совместимое тело OpenRouter. modalities=['image','text'] включает вывод картинки;
    для edit исходный кадр — content-часть image_url (data URL)."""
    content = [{"type": "text", "text": prompt}]
    if source_image_b64:
        url = source_image_b64 if source_image_b64.startswith("data:") \
            else "data:image/png;base64," + source_image_b64
        content.append({"type": "image_url", "image_url": {"url": url}})
    return {
        "model": model or DEFAULT_MODEL,
        "messages": [{"role": "user", "content": content}],
        "modalities": ["image", "text"],
    }


def _build_request_ru_openai(prompt, model=None, num_images=1, size=None):
    """Тело OpenAI Images /generations для RU-агрегатора (neuroapi/aitunnel) — генерация С НУЛЯ (наши
    пиксели). Форма ИНАЯ, чем chat/completions: prompt — top-level строка, картинка вернётся в
    data[].b64_json (response_format='b64_json'). Донор не прикладывается (edit=/images/edits multipart
    тут не поддержан) → generate-only, честный откат edit→generate. Тело ЧИСТОЕ (без маркеров): в сеть
    уходит как есть; _preview/тесты узнают ru_openai по паре top-level 'prompt' + 'response_format'.
    size опускаем по умолчанию (агрегаторы наследников Gemini не всегда чтут 4:5 — пропорцию держим
    промптом + verify_canon, чтобы не ловить 400 на нестандартном размере)."""
    body = {
        "model": model or RU_OPENAI_DEFAULT_MODEL,
        "prompt": prompt,
        "n": num_images,
        "response_format": "b64_json",
    }
    if size:
        body["size"] = size
    return body


def _build_request_yandexart(prompt):
    """Тело YandexART (imageGenerationAsync): генерация С НУЛЯ (наши пиксели), АСИНХРОННО.

    modelUri = art://<folder_id>/yandex-art/latest — модель живёт в каталоге (folder_id обязателен;
    пустой → заглушка 'art:///…', живой путь НЕ пустится без каталога). aspectRatio 4:5 РОДНОЙ
    (widthRatio/heightRatio строки, как в доках; без него YandexART отдаст квадрат 1:1 — ловушка).
    weight "1" на единственном сообщении — формат доков. Донор не прикладывается (диффузия) →
    generate-only. Тело ЧИСТОЕ (без маркеров): уходит в сеть как есть; _preview/тесты узнают yandexart
    по паре top-level 'modelUri' + 'messages'."""
    folder = _yaart_folder()
    model_uri = "art://%s/yandex-art/latest" % folder if folder else "art:///yandex-art/latest"
    return {
        "modelUri": model_uri,
        "generationOptions": {
            "aspectRatio": {"widthRatio": "4", "heightRatio": "5"},
        },
        "messages": [{"weight": "1", "text": prompt}],
    }


def _sniff_mime(b64):
    """Угадать MIME по сигнатуре первых байт (декодим кусочек base64). Google требует ЧЕСТНЫЙ mime_type."""
    try:
        head = base64.b64decode((b64 or "")[:24], validate=False)
    except Exception:
        return "image/png"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:2] == b"\xff\xd8":
        return "image/jpeg"
    if head[:4] == b"RIFF":
        return "image/webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/png"


def _raw_b64_and_mime(s):
    """Google хочет ГОЛЫЙ base64 (без data:-префикса) + отдельный mime_type. Снимаем префикс, чинаем mime."""
    if isinstance(s, str) and s.startswith("data:"):
        try:
            head, body = s.split(",", 1)
            return body, (head[5:].split(";", 1)[0] or "image/png")
        except Exception:
            return s, "image/png"
    return s, _sniff_mime(s)


def _build_request_google(prompt, source_image_b64=None, model=None):
    """Родное тело Gemini generateContent (Google AI Studio). Модель — в URL, НЕ в теле.

    contents[].parts[]: текст + опц. inline_data{mime_type, data=ГОЛЫЙ base64}.
    generationConfig.responseModalities=['TEXT','IMAGE'] — безопасный супернабор (картинка гарантирована).
    """
    parts = [{"text": prompt}]
    if source_image_b64:
        raw_b64, mime = _raw_b64_and_mime(source_image_b64)
        parts.append({"inline_data": {"mime_type": mime, "data": raw_b64}})
    return {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }


# ── Разбор ответа: тянем картинку из тела (200 ≠ успех) ─────────────────────────────
def _decode_data_url(url):
    """'data:image/png;base64,XXXX' → (mime, bytes). Голый base64 тоже принимаем. None при провале."""
    if not isinstance(url, str) or not url:
        return None, None
    mime = "image/png"
    payload = url
    if url.startswith("data:"):
        try:
            head, payload = url.split(",", 1)
            mime = head[5:].split(";", 1)[0] or mime
        except Exception:
            return None, None
    try:
        return mime, base64.b64decode(payload, validate=False)
    except Exception:
        return None, None


def _mime_from_magic(raw):
    """Миме по сигнатуре байтов — чтобы файл лёг с верным расширением. Дефолт PNG."""
    if raw:
        if raw[:2] == b"\xff\xd8":
            return "image/jpeg"
        if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
            return "image/webp"
        if raw[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
    return "image/png"


def _bytes_from_image_url(url):
    """URL картинки → (mime, raw). Понимает data:-URL, голый base64 И ЖИВОЙ http(s)-линк.

    OpenAI-Images /generations отдаёт data[].url РЕАЛЬНОЙ https-ссылкой на хостнутый PNG, когда
    шлюз не уважил response_format=b64_json (DALL-E-дефолт / gemini-обёртка, игнорящая параметр).
    Тогда байты надо СТЯНУТЬ (хантер → stdlib urllib), а не base64-декодить строку ссылки —
    иначе годный ОПЛАЧЕННЫЙ кадр молча теряется и жгутся ретраи (нарушение закона «200≠успех»).
    """
    if not isinstance(url, str) or not url:
        return None, None
    if url.startswith(("http://", "https://")):
        raw = None
        h = _hunter()
        if h is not None:
            try:
                raw, _ = h.fetch_bytes(url)
            except Exception:
                raw = None
        if raw is None:
            try:
                import urllib.request
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    raw = r.read(12_000_000)
            except Exception:
                return None, None
        if raw and _magic_is_image(raw):
            return _mime_from_magic(raw), raw
        return None, None
    return _decode_data_url(url)


def extract_image(resp_json):
    """Достать (mime, bytes) первой картинки из ответа ЛЮБОГО провайдера. Нет картинки → (None,None) — ПРОМАХ.

    Google native: candidates[].content.parts[].inlineData.data (ГОЛЫЙ base64; ответ ВСЕГДА camelCase,
        но snake_case тоже принимаем). Итерируем parts — картинка не обязана быть в [0] (бывает и текст).
    OpenRouter: choices[0].message.images[].image_url.url (base64 data URL) + скан content-частей.
    Не верим 200 — верим наличию кадра.
    """
    if not isinstance(resp_json, dict):
        return None, None

    # ── Путь RU-агрегатора (OpenAI Images /generations): data[].b64_json | data[].url ──
    # Специфичная форма (top-level list "data") — не пересекается с google("candidates")/openrouter("choices").
    # b64_json — ГОЛЫЙ base64 картинки; гейтим сигнатурой (base64 текста ошибки не пройдёт _magic_is_image → ПРОМАХ).
    data = resp_json.get("data")
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            b64 = item.get("b64_json")
            if b64:
                try:
                    raw = base64.b64decode(b64, validate=False)
                except Exception:
                    raw = None
                if raw and _magic_is_image(raw):
                    return "image/png", raw
            url = item.get("url")
            if url:
                mime, raw = _bytes_from_image_url(url)   # http(s)-линк ТЯНЕМ, а не декодим строку
                if raw and _magic_is_image(raw):
                    return mime, raw

    # ── Путь Google (generateContent) ──
    for cand in (resp_json.get("candidates") or []):
        content = (cand or {}).get("content") or {}
        for part in (content.get("parts") or []):
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                try:
                    raw = base64.b64decode(inline["data"], validate=False)
                except Exception:
                    raw = None
                if raw:
                    return mime, raw

    # ── Путь OpenRouter (chat/completions) ──
    try:
        choices = resp_json.get("choices") or []
        msg = (choices[0] or {}).get("message") or {} if choices else {}
    except Exception:
        return None, None
    for img in (msg.get("images") or []):
        url = ((img or {}).get("image_url") or {}).get("url") if isinstance(img, dict) else None
        mime, raw = _decode_data_url(url or (img if isinstance(img, str) else ""))
        if raw:
            return mime, raw
    content = msg.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") in ("image_url", "output_image", "image"):
                url = (part.get("image_url") or {}).get("url") or part.get("url") or part.get("data")
                mime, raw = _decode_data_url(url)
                if raw:
                    return mime, raw
    return None, None


def _finish_reason(resp_json):
    """Диагностика ПРОМАХА на 200: почему нет картинки (safety/recitation…). Для честного лога попытки."""
    try:
        cands = resp_json.get("candidates") or []
        if cands:
            fr = (cands[0] or {}).get("finishReason") or (cands[0] or {}).get("finish_reason")
            if fr:
                return str(fr)
        pf_ = resp_json.get("promptFeedback") or resp_json.get("prompt_feedback") or {}
        br = pf_.get("blockReason") or pf_.get("block_reason")
        if br:
            return "prompt_blocked:" + str(br)
    except Exception:
        pass
    return None


# ── Приёмка выхода: переиспользуем photo_hunter + чистая логика уникальности ─────────
def _magic_is_image(raw):
    """Стдлиб-проверка по сигнатуре: это вообще картинка? (PNG/JPEG/WebP/GIF). Без PIL."""
    if not raw or len(raw) < 64:
        return False
    return (raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:2] == b"\xff\xd8"
            or raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" or raw[:6] in (b"GIF87a", b"GIF89a"))


def _hunter():
    """Ленивый доступ к photo_hunter (pHash/OCR-приёмщик). None, если недоступен."""
    try:
        import photo_hunter_v1 as h              # noqa: F811
        return h
    except Exception:
        try:
            import sys
            if str(HERE) not in sys.path:
                sys.path.insert(0, str(HERE))
            import photo_hunter_v1 as h          # noqa: F811
            return h
        except Exception:
            return None


def assess_uniqueness(new_phash, donor_phashes, min_hamming=MIN_DONOR_HAMMING):
    """ЧИСТАЯ логика: достаточно ли выход НЕПОХОЖ на донора (иначе МП склеит). Тестируется напрямую.

    Возвращает {distinct, min_hamming, checked}. distinct=None если хеши недоступны (честно «не знаю»).
    """
    h = _hunter()
    if not new_phash or not donor_phashes or h is None:
        return {"distinct": None, "min_hamming": None, "checked": False}
    dists = [d for d in (h.hamming(new_phash, dp) for dp in donor_phashes) if d is not None]
    if not dists:
        return {"distinct": None, "min_hamming": None, "checked": False}
    mn = min(dists)
    return {"distinct": mn >= min_hamming, "min_hamming": mn, "checked": True}


def scan_watermark(text, markers):
    """ЧИСТАЯ логика: нашёлся ли чужой домен/оптовая фраза в распознанном тексте. Тестируется напрямую."""
    import re
    low = re.sub(r"\s+", " ", (text or "")).strip().lower()
    hits = [d for d in (markers.get("domains") or []) if d in low]
    hits += [p for p in (markers.get("phrases") or []) if re.search(r"\b%s\b" % re.escape(p), low)]
    return hits


def verify_output(raw, facts=None, donor_phashes=(), seen_phashes=()):
    """Прогнать сгенерённый кадр через приёмку. Вердикт-тиры: verified | ok_needs_human | rejected.

      • image_ok — это картинка (стдлиб-сигнатура; при PIL — и размеры через хантер).
      • watermark_clean — OCR не нашёл чужого текста (None = не проверено, нет tesseract).
      • distinct_from_donor — pHash достаточно далёк от донора (None = не проверено, нет PIL).
    Честность: непроверенное НЕ выдаётся за «годится» — тогда тир ok_needs_human (глазами оператора).
    """
    out = {"image_ok": None, "watermark_clean": None, "distinct_from_donor": None,
           "phash": None, "why": [], "tier": "rejected"}
    facts = facts or {}
    if not _magic_is_image(raw):
        out["image_ok"] = False
        out["why"].append("ответ не является изображением (нет сигнатуры формата)")
        return out
    out["image_ok"] = True
    h = _hunter()

    # Железо + pHash через хантер (если PIL есть).
    if h is not None:
        try:
            src = h.load_sources()
            ok1, d1 = h.stage1_iron(raw, None, src.get("criteria", {}))
            out["phash"] = d1.get("phash")
            if ok1 is False:
                out["image_ok"] = False
                out["why"].append("железо хантера отбило: " + str(d1.get("why")))
                return out
            # Знак по буквам.
            ok2, d2 = h.stage2_letters(raw, src.get("watermark_markers", {}))
            if ok2 is False:
                out["watermark_clean"] = False
                out["why"].append("на кадре найден чужой текст: " + str(d2.get("why")))
            elif ok2 is True:
                out["watermark_clean"] = True
        except Exception as e:
            out["why"].append("проверка хантером не выполнилась: %s" % type(e).__name__)

    uniq = assess_uniqueness(out["phash"], donor_phashes)
    out["distinct_from_donor"] = uniq["distinct"]
    if uniq["distinct"] is False:
        out["why"].append("выход слишком похож на донора (hamming=%s < %d) — МП склеит"
                          % (uniq["min_hamming"], MIN_DONOR_HAMMING))

    if out["watermark_clean"] is False or out["distinct_from_donor"] is False:
        out["tier"] = "rejected"
    elif out["watermark_clean"] is True and out["distinct_from_donor"] is True:
        out["tier"] = "verified"
        out["why"].append("прошёл приёмку: картинка, знак снят, уникален относительно донора")
    else:
        out["tier"] = "ok_needs_human"
        gaps = []
        if out["watermark_clean"] is None:
            gaps.append("знак не проверен (нет OCR)")
        if out["distinct_from_donor"] is None:
            gaps.append("уникальность не проверена (нет PIL/донора)")
        out["why"].append("кадр родился, но не всё проверено: " + "; ".join(gaps)
                          + " — глазами оператора")
    return out


# ── БРОНЯ СТИЛЯ: кадр действительно родился в каноне ATLAS EDGE? ──────────────────────
def _have_pil():
    """PIL реально доступен ОРГАНУ канон-приёмки? Меряем РОВНО тот сигнал, на котором стоят
    _pil_open/is_white_bg/_aspect_ok/verify_canon — флаг хантера HAVE_PIL, не independent
    `import PIL` из capabilities(). Иначе гард и приёмка разъедутся: PIL в системе есть, а
    photo_hunter не импортнулся → приёмка слепа (is_white_bg=None), а гард думал бы «вижу».
    Так живой canon-гард меряет ровно свою же способность отбраковать вне-канонный кадр."""
    h = _hunter()
    return h is not None and getattr(h, "HAVE_PIL", False)


def _pil_open(raw):
    """Открыть кадр через PIL (переиспользуем зависимость хантера). None → PIL/битый кадр."""
    if not raw or not _have_pil():
        return None
    h = _hunter()
    try:
        import io
        return h.Image.open(io.BytesIO(raw))
    except Exception:
        return None


def is_white_bg(raw, corner_frac=0.08, thr=244, need_frac=0.9):
    """Углы кадра ≈ чистый белый #FFFFFF? Возвращает True | False | None (нет PIL — «не знаю»).

    Смотрим 4 угловых квадрата (corner_frac стороны). Пиксель «белый», если R,G,B ≥ thr.
    Канон держится, если ≥ need_frac угловых пикселей белые (мягкая тень под товаром допустима —
    она в центре-низу, не в углах). Честность: без PIL не врём «да», отдаём None.
    """
    im = _pil_open(raw)
    if im is None:
        return None
    try:
        im = im.convert("RGB")
        w, h = im.size
        cw, ch = max(1, int(w * corner_frac)), max(1, int(h * corner_frac))
        boxes = [(0, 0, cw, ch), (w - cw, 0, w, ch), (0, h - ch, cw, h), (w - cw, h - ch, w, h)]
        white = total = 0
        for (x0, y0, x1, y1) in boxes:
            for px in im.crop((x0, y0, x1, y1)).getdata():
                total += 1
                if px[0] >= thr and px[1] >= thr and px[2] >= thr:
                    white += 1
        if total == 0:
            return None
        return (white / total) >= need_frac
    except Exception:
        return None


def _aspect_ok(raw, target="4:5", tol=0.06):
    """Пропорция кадра ≈ целевой (4:5 = 0.8)? True | False | None (нет PIL). tol — доля допуска."""
    im = _pil_open(raw)
    if im is None:
        return None
    try:
        w, h = im.size
        if not w or not h:
            return None
        tw, th = (float(x) for x in target.split(":"))
        want = tw / th
        return abs((w / h) - want) <= tol * want
    except Exception:
        return None


def subject_metrics(raw, white_thr=235, scan_px=160, present_floor=0.003):
    """Метрики ПРЕДМЕТА на белом каталожном кадре: насколько крупно он в кадре и по центру ли.

    Зачем: одна метрика на четыре роли — (1) детектор «товар мельче чем есть» (жалоба оператора:
    крошечный короб в центре удовлетворял ВСЕ старые инструкции center+4:5), (2) L1-приёмка канона
    (verify_canon может понизить в off_canon, если товар слишком мал/сбит/отсутствует — по порогам),
    (3) отбор лучшего кадра в пачке (forge_batch берёт кадр с бОльшим fill), (4) сигнал качества в
    сводке пачки. Возвращает {fill, off_center, present}; без PIL — все None (честно «не знаю»).
        fill        — доля площади кадра под bbox не-белых пикселей. Крошечный товар → ~0.01, крупный → ~0.6+.
        off_center  — смещение центра bbox от центра кадра: 0 = идеально по центру, ~0.5 = прижат к краю.
        present     — есть ли вообще предмет (доля не-белых пикселей ≥ present_floor); пустой белый → False.
    Считаем на даунскейле (scan_px по длинной стороне) — fill/центр грубые, 160px хватает, а CPU в пачке
    из 100 кадров в ~60× дешевле полного скана. Порог white_thr чуть строже is_white_bg(244), чтобы мягкая
    тень под товаром не раздувала bbox (иначе мелкий товар замаскировался бы «большим»). Все пороги — TUNABLE.
    """
    im = _pil_open(raw)
    if im is None:
        return {"fill": None, "off_center": None, "present": None}
    try:
        im = im.convert("RGB")
        w, h = im.size
        if not w or not h:
            return {"fill": None, "off_center": None, "present": None}
        if w >= h:
            nw, nh = scan_px, max(1, round(scan_px * h / w))
        else:
            nw, nh = max(1, round(scan_px * w / h)), scan_px
        im = im.resize((nw, nh))
        px = im.load()
        minx, miny, maxx, maxy, cnt = nw, nh, -1, -1, 0
        for y in range(nh):
            for x in range(nw):
                p = px[x, y]
                if min(p[0], p[1], p[2]) < white_thr:      # не-белый = предмет (тень светлее порога не в счёт)
                    cnt += 1
                    if x < minx: minx = x
                    if x > maxx: maxx = x
                    if y < miny: miny = y
                    if y > maxy: maxy = y
        total = nw * nh
        present = (cnt / total) >= present_floor if total else False
        if maxx < 0 or not present:                        # предмета нет → нули (не мусор), центр «не знаю»
            return {"fill": 0.0, "off_center": None, "present": present}
        bw, bh = (maxx - minx + 1), (maxy - miny + 1)
        fill = (bw * bh) / total
        cx = (minx + maxx + 1) / 2.0 / nw
        cy = (miny + maxy + 1) / 2.0 / nh
        off_center = max(abs(cx - 0.5), abs(cy - 0.5))
        return {"fill": round(fill, 4), "off_center": round(off_center, 4), "present": True}
    except Exception:
        return {"fill": None, "off_center": None, "present": None}


def verify_canon(raw, facts=None, donor_phashes=(), seen_phashes=(), aspect="4:5",
                 min_fill=None, max_off=None, require_subject=False):
    """БРОНИРОВАННАЯ приёмка = verify_output + фирменный канон ATLAS EDGE (белый фон + пропорция).

    Строит поверх verify_output (не дублирует его): базовые тиры и «не знаю» наследуются как есть,
    сверху добавляет canon-проверки. Кадр не в каноне (фон НЕ белый или пропорция мимо) → тир
    понижается до 'off_canon' (в живую карточку такой не пускаем). Непроверенное (нет PIL) НЕ роняет
    в off_canon — остаётся честным ok_needs_human. Так «никогда без ошибок»: только verified+canon
    уходит на боевую витрину.

    L1 (по умолчанию ВЫКЛ, обратная совместимость байт-в-байт): метрики предмета всегда МЕРЯЮТСЯ и
    кладутся в out['subject'] (детектор «товар мельче чем есть» + отбор кадра в пачке), но ПОНИЖАЮТ в
    off_canon только когда оператор задал порог: min_fill (товар не мельче доли кадра), max_off (не
    сбит с центра сильнее), require_subject (кадр не пустой). None/None/False → поведение как раньше.
    """
    out = verify_output(raw, facts=facts, donor_phashes=donor_phashes, seen_phashes=seen_phashes)
    white = is_white_bg(raw)
    ar_ok = _aspect_ok(raw, aspect)
    subj = subject_metrics(raw)
    out["white_bg"] = white
    out["aspect_ok"] = ar_ok
    out["subject"] = subj
    out["canon"] = {"style": BRAND_NAME, "aspect": aspect}
    # Явное нарушение канона (проверено И провалено) → off_canon, даже если verify_output дал verified.
    bad = []
    if white is False:
        bad.append("фон не чистый белый #FFFFFF")
    if ar_ok is False:
        bad.append("пропорция не %s" % aspect)
    # L1: понижаем ТОЛЬКО когда порог задан И метрика посчитана И провалена (None-метрику не караем).
    if min_fill is not None and subj["fill"] is not None and subj["fill"] < min_fill:
        bad.append("товар мелковат в кадре (fill %.3f < %.3f)" % (subj["fill"], min_fill))
    if max_off is not None and subj["off_center"] is not None and subj["off_center"] > max_off:
        bad.append("товар сбит с центра (off %.3f > %.3f)" % (subj["off_center"], max_off))
    if require_subject and subj["present"] is False:
        bad.append("товар не найден в кадре (пустой белый)")
    if bad:
        out["tier"] = "off_canon"
        out["why"].append("вне фирменного стиля ATLAS EDGE: " + "; ".join(bad)
                          + " — на боевую витрину не пускаем")
    return out


# ── Права: честная граница (как CLEAN/RISK у уникализатора) ─────────────────────────
def rights_note(mode):
    if mode == "generate":
        return {"level": "own_pixels", "clean": True,
                "note": "изображение сгенерировано с нуля — это наши пиксели"}
    return {"level": "derivative", "clean": False,
            "note": ("производное от донорского кадра: чужой знак снят, но авторство исходной "
                     "съёмки не наше — законность использования решает оператор")}


# ── Учёт (каждый живой кадр — событие расхода) ──────────────────────────────────────
def _ledger_append(event):
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        data = []
        if LEDGER.exists():
            try:
                data = json.loads(LEDGER.read_text(encoding="utf-8"))
            except Exception:
                data = []
        if not isinstance(data, list):
            data = []
        data.append(event)
        LEDGER.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    except Exception:
        return False


def _usage_cost(resp_json):
    """Реальная цена из usage ответа, если шлюз её вернул; иначе None (возьмём оценку)."""
    try:
        u = resp_json.get("usage") or {}
        for k in ("cost", "total_cost"):
            if isinstance(u.get(k), (int, float)):
                return float(u[k])
    except Exception:
        pass
    return None


def _load_source(source):
    """Донорский кадр в base64: локальный путь ИЛИ url (через хантер/urllib). (b64, raw) или (None, None)."""
    if not source:
        return None, None
    p = Path(source)
    if p.exists():
        raw = p.read_bytes()
        return base64.b64encode(raw).decode("ascii"), raw
    h = _hunter()
    raw = None
    if h is not None:
        raw, _ = h.fetch_bytes(source)
    if raw is None:
        try:
            import urllib.request
            req = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                raw = r.read(12_000_000)
        except Exception:
            return None, None
    return (base64.b64encode(raw).decode("ascii"), raw) if raw else (None, None)


def _save_image(raw, mime, out_dir, tag):
    # Истина о формате — в самих байтах (магочисла), а не в mime от шлюза: RU-агрегатор часто
    # отдаёт JPEG под ярлыком image/png → раньше кадр ложился .png с JPEG-нутром. Магобайты главнее.
    true_mime = _mime_from_magic(raw) or mime
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(true_mime, "png")
    d = Path(out_dir) if out_dir else OUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / ("forged_%s_%d.%s" % (tag, int(time.time()), ext))
    path.write_bytes(raw)
    return str(path)


def _preview(payload, limit=180):
    """Краткое эхо запроса для dry: без гигантского base64 (иначе dry-лог нечитаем). Три формы."""
    if payload.get("provider") == "fusionbrain" or "generateParams" in payload:   # fusionbrain /run
        return {"provider": "fusionbrain", "type": payload.get("type"),
                "width": payload.get("width"), "height": payload.get("height"),
                "text": ((payload.get("generateParams") or {}).get("query") or "")[:limit],
                "has_source_image": False}
    if "contents" in payload:                    # google generateContent
        out = {"provider": "google",
               "responseModalities": (payload.get("generationConfig") or {}).get("responseModalities")}
        try:
            parts = payload["contents"][0]["parts"]
            out["text"] = next((p["text"][:limit] for p in parts if "text" in p), None)
            out["has_source_image"] = any("inline_data" in p or "inlineData" in p for p in parts)
        except Exception:
            pass
        return out
    if "response_format" in payload and "messages" not in payload:   # ru_openai (OpenAI Images /generations)
        return {"provider": "ru_openai", "model": payload.get("model"),
                "response_format": payload.get("response_format"), "n": payload.get("n"),
                "text": (payload.get("prompt") or "")[:limit],
                "has_source_image": False}
    if "modelUri" in payload and "messages" in payload:    # yandexart (async): art://<folder>/… + messages[]
        ar = (payload.get("generationOptions") or {}).get("aspectRatio") or {}
        return {"provider": "yandexart", "model": payload.get("modelUri"),
                "aspect_ratio": "%s:%s" % (ar.get("widthRatio"), ar.get("heightRatio")),
                "text": (((payload.get("messages") or [{}])[0] or {}).get("text") or "")[:limit],
                "has_source_image": False}
    out = {"provider": "openrouter", "model": payload.get("model"),
           "modalities": payload.get("modalities")}
    try:
        parts = payload["messages"][0]["content"]
        out["text"] = next((p["text"][:limit] for p in parts if p.get("type") == "text"), None)
        out["has_source_image"] = any(p.get("type") == "image_url" for p in parts)
    except Exception:
        pass
    return out


# ── Главная кузница ─────────────────────────────────────────────────────────────────
def _forge_fusionbrain(source, facts, ops, mode, dry, model, retries,
                       require_verified, out_dir, tag, canon, brand, donor_phashes=()):
    """Ветка Kandinsky/FusionBrain: генерация С НУЛЯ по фактам (наши пиксели). Отдельный асинхронный
    путь (pipelines → run → poll status), т.к. авторизация парная и POST — multipart, чего нет у
    openrouter/google. Держит те же законы: dry→0₽, censored/пустой кадр = ПРОМАХ (ретрай), приёмка
    через verify_output/verify_canon, событие расхода в леджер (free tier → cost 0)."""
    facts = facts or {}
    # ЧЕСТНАЯ ГРАНИЦА: Kandinsky рисует С НУЛЯ, донор не редактирует → права ВСЕГДА наши пиксели.
    rights = rights_note("generate")
    use_model = FUSIONBRAIN_DEFAULT_MODEL
    prompt = build_prompt(facts, ops, "generate", brand=brand)
    params = _build_request_fusionbrain(prompt)

    # СУХОЙ ГЕЙТ — наружу ничего (0₽). Форма params честно видна в превью. Бесплатный tier → оценка 0.
    if dry:
        report = {"ok": True, "dry": True, "mode": "generate", "sent": False, "provider": "fusionbrain",
                  "model": use_model, "request": _preview(params), "est_cost_usd": 0.0,
                  "rights": rights, "canon": bool(canon),
                  "verify_plan": ("выход пройдёт verify_canon (образ/знак/pHash + белый фон + 4:5)"
                                  if canon else "выход пройдёт photo_hunter (образ/знак/pHash)"),
                  "note": "СУХОЙ ГЕЙТ: наружу ничего не ушло (0₽); живой кадр — dry=False по отмашке"}
        if mode == "edit":
            report["mode_note"] = ("запрошен edit, но Kandinsky не редактирует донора — кую С НУЛЯ по "
                                   "фактам (наши пиксели). Для правки чужого кадра нужен Nano Banana")
        return report

    if not _fusionbrain_ready():
        return {"ok": False, "dry": False, "provider": "fusionbrain", "mode": "generate", "rights": rights,
                "why": "нет ключей FusionBrain (FUSIONBRAIN_API_KEY + FUSIONBRAIN_SECRET_KEY) — живой режим недоступен",
                "hint": "впиши пару ключей в mint/.env (gitignored); оба обязательны"}

    try:
        pipeline_id = _fb_pipeline_id()
    except ForgeHTTPError as e:
        return {"ok": False, "dry": False, "provider": "fusionbrain", "mode": "generate", "rights": rights,
                "status": e.status, "why": "шлюз FusionBrain (pipelines): %s" % e}
    except Exception as e:
        return {"ok": False, "dry": False, "provider": "fusionbrain", "mode": "generate", "rights": rights,
                "why": "FusionBrain pipelines: %s" % e}

    attempts = []
    cur_prompt = prompt
    for i in range(retries + 1):
        cur_params = _build_request_fusionbrain(cur_prompt)
        try:
            req_uuid = _fb_run(pipeline_id, cur_params)
            status_json = _fb_poll(req_uuid)
        except ForgeHTTPError as e:
            return {"ok": False, "dry": False, "provider": "fusionbrain", "mode": "generate",
                    "rights": rights, "status": e.status, "why": "шлюз FusionBrain: %s" % e,
                    "attempts": attempts}
        except Exception as e:
            return {"ok": False, "dry": False, "provider": "fusionbrain", "mode": "generate",
                    "rights": rights, "why": "FusionBrain: %s" % e, "attempts": attempts}

        raw, censored = _fb_extract(status_json)
        if not raw:
            # censored=true = цензор срезал вывод; иначе — просто нет кадра. Оба → ПРОМАХ, ретрай.
            verdict = "censored" if censored else "no_image"
            attempts.append({"i": i, "verdict": verdict})
            if censored:
                cur_prompt = prompt + " Нейтральное предметное студийное фото товара, без спорного содержания."
            else:
                cur_prompt = prompt + " Верни именно изображение товара."
            continue

        verdict = (verify_canon(raw, facts, donor_phashes=donor_phashes) if canon
                   else verify_output(raw, facts, donor_phashes=()))
        event = {"ts": int(time.time()), "mode": "generate", "provider": "fusionbrain",
                 "model": use_model, "tier": verdict["tier"], "cost_usd": 0.0,
                 "cost_source": "free_tier", "rights": rights["level"], "attempt": i}

        accept = verdict["tier"] == "verified" or (verdict["tier"] == "ok_needs_human"
                                                   and not require_verified)
        if accept:
            path = _save_image(raw, "image/png", out_dir, tag)
            event["saved"] = path
            _ledger_append(event)
            report = {"ok": True, "dry": False, "sent": True, "mode": "generate", "path": path,
                      "provider": "fusionbrain", "model": use_model,
                      "tier": verdict["tier"], "verdict": verdict, "rights": rights,
                      "cost_usd": 0.0, "cost_source": "free_tier",
                      "attempts": attempts + [{"i": i, "verdict": verdict["tier"]}]}
            if mode == "edit":
                report["mode_note"] = ("запрошен edit → выкован С НУЛЯ по фактам (Kandinsky не "
                                       "редактирует донора); это наши пиксели, но не тот же SKU-кадр")
            return report

        _ledger_append(dict(event, saved=None))
        attempts.append({"i": i, "verdict": verdict["tier"], "why": verdict["why"]})
        if canon:
            cur_prompt = (prompt + " КРИТИЧНО: строго чистый БЕЛЫЙ фон #FFFFFF без предметов, товар "
                          "КРУПНО по центру — занимает почти весь кадр (≈85% высоты), небольшие "
                          "равные поля, вертикаль 4:5, никакого текста и логотипов на изображении.")
        else:
            cur_prompt = prompt + " Чистый ровный фон, товар в центре, без текста и логотипов."

    return {"ok": False, "dry": False, "sent": True, "mode": "generate", "rights": rights,
            "provider": "fusionbrain", "why": "не удалось получить годный кадр за %d попыток" % (retries + 1),
            "attempts": attempts}


def _forge_ru_openai(source, facts, ops, mode, dry, model, retries,
                     require_verified, out_dir, tag, canon, brand, donor_phashes=()):
    """Ветка RU-агрегатора (neuroapi/aitunnel) на OpenAI Images API: генерация С НУЛЯ по фактам
    (наши пиксели). Отдельный путь (как fusionbrain): форма /images/generations иная, чем
    chat/completions, и это generate-only (edit донора = /images/edits multipart тут не поддержан) →
    честный откат edit→generate. Синхронно (без polling): _request → extract_image (data[].b64_json).
    Те же законы: dry→0₽, нет картинки=ПРОМАХ(ретрай), приёмка verify_output/verify_canon, событие
    расхода в леджер (оценка RU_OPENAI_EST_USD; факт из usage, если шлюз вернёт)."""
    facts = facts or {}
    # ЧЕСТНАЯ ГРАНИЦА: рисуем С НУЛЯ, донор не редактируем → права ВСЕГДА наши пиксели.
    rights = rights_note("generate")
    use_model = model or _ru_openai_model()
    prompt = build_prompt(facts, ops, "generate", brand=brand)
    # 4:5 — вертикаль карточки МП. Родной размер у шлюза честнее пост-паддинга (паддинг подделал бы
    # белые углы под corner-детектором is_white_bg). При canon просим 4:5; env RU_OPENAI_SIZE перекрывает.
    want_size = (os.getenv("RU_OPENAI_SIZE") or "1024x1280") if canon else None
    payload = _build_request_ru_openai(prompt, use_model, size=want_size)

    # СУХОЙ ГЕЙТ — наружу ничего (0₽). Форма тела честно видна в превью.
    if dry:
        report = {"ok": True, "dry": True, "mode": "generate", "sent": False, "provider": "ru_openai",
                  "model": use_model, "request": _preview(payload), "est_cost_usd": RU_OPENAI_EST_USD,
                  "rights": rights, "canon": bool(canon),
                  "verify_plan": ("выход пройдёт verify_canon (образ/знак/pHash + белый фон + 4:5)"
                                  if canon else "выход пройдёт photo_hunter (образ/знак/pHash)"),
                  "note": "СУХОЙ ГЕЙТ: наружу ничего не ушло (0₽); живой кадр — dry=False по отмашке"}
        if mode == "edit":
            report["mode_note"] = ("запрошен edit, но RU-ветвь не редактирует донора (нужен /images/edits "
                                   "multipart) — кую С НУЛЯ по фактам (наши пиксели)")
        return report

    if not _ru_openai_key():
        return {"ok": False, "dry": False, "provider": "ru_openai", "mode": "generate", "rights": rights,
                "why": "нет ключа RU-агрегатора (NEUROAPI_API_KEY / RU_OPENAI_API_KEY) — живой режим недоступен",
                "hint": "впиши ключ в mint/.env (gitignored)"}

    endpoint = RU_OPENAI_IMAGES_PATH
    attempts = []
    spent = 0.0                                   # сумма РЕАЛЬНОГО расхода по всем платным попыткам (честный итог)
    cur_prompt = prompt
    for i in range(retries + 1):
        cur_payload = _build_request_ru_openai(cur_prompt, use_model, size=want_size)
        try:
            resp = _request("POST", endpoint, body=cur_payload)
        except ForgeHTTPError as e:
            return {"ok": False, "dry": False, "provider": "ru_openai", "mode": "generate",
                    "rights": rights, "status": e.status, "why": "шлюз RU-агрегатора: %s" % e,
                    "attempts": attempts}
        except Exception as e:
            return {"ok": False, "dry": False, "provider": "ru_openai", "mode": "generate",
                    "rights": rights, "why": "RU-агрегатор: %s" % e, "attempts": attempts}

        mime, raw = extract_image(resp)
        if not raw:                               # 200 ≠ успех: картинки нет → промах, ретрай
            fr = _finish_reason(resp)
            # ДЕНЬГИ-ПРАВДА: 200 на ПЛАТНОМ шлюзе = вероятное списание (модель отработала, а кадр к нам
            # не дошёл — напр. вернулся url, недостижимый с RU-egress). Пишем расход в леджер ДО continue:
            # иначе ретраи жгут патроны «за 0₽», а server-usage.cost молча теряется (леджер врал бы $0.00).
            ni_cost = _usage_cost(resp)
            ni_event = {"ts": int(time.time()), "mode": "generate", "provider": "ru_openai",
                        "model": use_model, "tier": "no_image",
                        "cost_usd": ni_cost if ni_cost is not None else RU_OPENAI_EST_USD,
                        "cost_source": "usage" if ni_cost is not None else "estimate_no_image",
                        "rights": rights["level"], "attempt": i, "saved": None, "finish_reason": fr}
            _ledger_append(ni_event)
            spent += ni_event["cost_usd"]
            attempts.append({"i": i, "verdict": "no_image", "finish_reason": fr,
                             "cost_usd": ni_event["cost_usd"], "cost_source": ni_event["cost_source"]})
            cur_prompt = prompt + " Верни именно изображение товара."
            continue

        verdict = (verify_canon(raw, facts, donor_phashes=donor_phashes) if canon
                   else verify_output(raw, facts, donor_phashes=()))
        cost = _usage_cost(resp)
        event = {"ts": int(time.time()), "mode": "generate", "provider": "ru_openai", "model": use_model,
                 "tier": verdict["tier"], "cost_usd": cost if cost is not None else RU_OPENAI_EST_USD,
                 "cost_source": "usage" if cost is not None else "estimate",
                 "rights": rights["level"], "attempt": i}

        accept = verdict["tier"] == "verified" or (verdict["tier"] == "ok_needs_human"
                                                   and not require_verified)
        if accept:
            path = _save_image(raw, mime or "image/png", out_dir, tag)
            event["saved"] = path
            _ledger_append(event)
            report = {"ok": True, "dry": False, "sent": True, "mode": "generate", "path": path,
                      "provider": "ru_openai", "model": use_model,
                      "tier": verdict["tier"], "verdict": verdict, "rights": rights,
                      "cost_usd": event["cost_usd"], "cost_source": event["cost_source"],
                      "attempts": attempts + [{"i": i, "verdict": verdict["tier"]}]}
            if mode == "edit":
                report["mode_note"] = ("запрошен edit → выкован С НУЛЯ по фактам (RU-ветвь не редактирует "
                                       "донора); это наши пиксели, но не тот же SKU-кадр")
            return report

        _ledger_append(dict(event, saved=None))
        spent += event["cost_usd"]                # отбитый кадр — тоже оплачен: копим в честный итог
        attempts.append({"i": i, "verdict": verdict["tier"], "why": verdict["why"]})
        if canon:
            cur_prompt = (prompt + " КРИТИЧНО: строго чистый БЕЛЫЙ фон #FFFFFF без предметов, товар "
                          "КРУПНО по центру — занимает почти весь кадр (≈85% высоты), небольшие "
                          "равные поля, вертикаль 4:5, никакого текста и логотипов на изображении.")
        else:
            cur_prompt = prompt + " Чистый ровный фон, товар в центре, без текста и логотипов."

    return {"ok": False, "dry": False, "sent": True, "mode": "generate", "rights": rights,
            "provider": "ru_openai", "why": "не удалось получить годный кадр за %d попыток" % (retries + 1),
            "cost_usd": round(spent, 6), "cost_source": "sum",   # ЧЕСТНЫЙ итог сожжённого (леджер = построчно)
            "attempts": attempts}


# ── Пятый провайдер: YandexART (Яндекс Cloud) — асинхронный шов и живая ветвь ─────────────
def _ya_request(method, path, body=None, timeout=120):
    """JSON-вызов к Yandex Cloud (YandexART): фиксированный хост + заголовок Api-Key, ЧЕРЕЗ общий шов
    _http_call (тесты патчат ИМЕННО его, как у ru_openai — одна точка сети на всю кузницу).
    401/403 → сразу ключи; транзитор → ограниченный ретрай; иной не-2xx → ForgeHTTPError."""
    key = _yaart_key()
    if not key:
        raise RuntimeError("нет ключа YandexART (YAART_API_KEY / YC_API_KEY) — живой режим недоступен, используй dry")
    url = YAART_API + path
    headers = {"Authorization": "Api-Key " + key, "Content-Type": "application/json"}
    retries = 0
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            r = _http_call(method, url, headers, body, timeout)
        except Exception as e:                       # сетевой сбой/timeout — транзиторный
            last_exc = e
            if attempt + 1 < _MAX_RETRIES:
                import random
                time.sleep(0.5 + random.random() * 1.0)
                retries += 1
                continue
            raise RuntimeError("сеть к YandexART упала после %d ретраев: %s" % (retries, e))
        if r.status_code in (401, 403):
            raise ForgeHTTPError(r.status_code, _safe_json(r), url)
        if r.status_code in _TRANSIENT and attempt + 1 < _MAX_RETRIES:
            import random
            time.sleep(0.5 + random.random() * 1.0)
            retries += 1
            continue
        if not (200 <= r.status_code < 300):
            raise ForgeHTTPError(r.status_code, _safe_json(r), url)
        return _safe_json(r)
    raise RuntimeError("исчерпаны ретраи к %s (последняя ошибка: %s)" % (url, last_exc))


def _ya_poll(operation_id, timeout_total=_YA_POLL_MAX_SEC):
    """Поллить GET /operations/<id> пока done:true. done+error тоже возвращаем (в _ya_op_image/error разбор).
    Генерация async может идти минуты (доки) → суммарный дедлайн, не число попыток; превышен → исключение."""
    import random
    deadline = time.time() + timeout_total
    while True:
        op = _ya_request("GET", YAART_OPS_PATH + operation_id, timeout=30)
        if isinstance(op, dict) and op.get("done"):
            return op
        if time.time() > deadline:
            raise RuntimeError("YandexART операция %s не завершилась за %ss" % (operation_id, int(timeout_total)))
        time.sleep(_YA_POLL_DELAY + random.random() * 0.5)


def _ya_op_image(op):
    """Готовая операция YandexART → (mime, bytes) картинки | (None, None) промах. 200 ≠ успех: верим байтам.
    done+response.image = ГОЛЫЙ base64 JPEG (доки: jq -r '.response | .image' | base64 -d). Гейтим
    сигнатурой — base64 текста ошибки не пройдёт _magic_is_image → честный ПРОМАХ."""
    if not isinstance(op, dict) or not op.get("done"):
        return None, None
    resp = op.get("response")
    if isinstance(resp, dict):
        img = resp.get("image")
        if isinstance(img, str) and img:
            try:
                raw = base64.b64decode(img, validate=False)
            except Exception:
                raw = None
            if raw and _magic_is_image(raw):
                return "image/jpeg", raw
    return None, None


def _ya_op_error(op):
    """Ошибка готовой операции (done+error) — для честного лога попытки. None, если её нет."""
    if isinstance(op, dict):
        err = op.get("error")
        if err:
            if isinstance(err, dict):
                return err.get("message") or str(err)
            return str(err)
    return None


def _forge_yandexart(source, facts, ops, mode, dry, model, retries,
                     require_verified, out_dir, tag, canon, brand, donor_phashes=()):
    """Ветка YandexART (Яндекс Cloud) — САМЫЙ дешёвый РФ-канал карточек (~$0.0176/кадр flat): генерация
    С НУЛЯ по фактам (наши пиксели), АСИНХРОННАЯ. Отдельный путь (как ru_openai/fusionbrain): свой хост
    llm.api.cloud.yandex.net + Api-Key, тело modelUri + aspectRatio{4:5} + messages[weight,text]; POST
    imageGenerationAsync → Operation{id} → поллим GET /operations/<id> до done → response.image = голый
    base64 JPEG. generate-only (диффузия не редактирует донора) → честный откат edit→generate. Те же
    законы: dry→0₽, пусто/error = ПРОМАХ (ретрай), приёмка verify_output/verify_canon, событие расхода
    в леджер (оценка YAART_EST_USD — у операции нет usage-цены, факт смотри в биллинге кабинета)."""
    facts = facts or {}
    # ЧЕСТНАЯ ГРАНИЦА: рисуем С НУЛЯ, донор не редактируем → права ВСЕГДА наши пиксели.
    rights = rights_note("generate")
    prompt = build_prompt(facts, ops, "generate", brand=brand)
    folder = _yaart_folder()
    payload = _build_request_yandexart(prompt)
    model_uri = payload["modelUri"]

    # СУХОЙ ГЕЙТ — наружу ничего (0₽). Форма тела честно видна в превью (modelUri + 4:5).
    if dry:
        report = {"ok": True, "dry": True, "mode": "generate", "sent": False, "provider": "yandexart",
                  "model": model_uri, "request": _preview(payload), "est_cost_usd": YAART_EST_USD,
                  "rights": rights, "canon": bool(canon),
                  "verify_plan": ("выход пройдёт verify_canon (образ/знак/pHash + белый фон + 4:5)"
                                  if canon else "выход пройдёт photo_hunter (образ/знак/pHash)"),
                  "note": "СУХОЙ ГЕЙТ: наружу ничего не ушло (0₽); живой кадр — dry=False по отмашке"}
        if mode == "edit":
            report["mode_note"] = ("запрошен edit, но YandexART не редактирует донора (диффузия) — "
                                   "кую С НУЛЯ по фактам (наши пиксели)")
        if not folder:
            report["hint"] = "folder_id пока пуст → modelUri art://<folder>/… не собрать; впиши YAART_FOLDER_ID"
        return report

    if not _yaart_key():
        return {"ok": False, "dry": False, "provider": "yandexart", "mode": "generate", "rights": rights,
                "why": "нет ключа YandexART (YAART_API_KEY / YC_API_KEY) — живой режим недоступен",
                "hint": "впиши ключ в mint/.env (gitignored)"}
    if not folder:
        return {"ok": False, "dry": False, "provider": "yandexart", "mode": "generate", "rights": rights,
                "why": "нет YAART_FOLDER_ID — modelUri art://<folder>/yandex-art/latest без каталога не собрать",
                "hint": "впиши folder_id каталога (сервисному аккаунту дана роль ai.art.user)"}

    attempts = []
    spent = 0.0                                   # сумма РЕАЛЬНОГО расхода по всем платным попыткам (честный итог)
    cur_prompt = prompt
    for i in range(retries + 1):
        cur_payload = _build_request_yandexart(cur_prompt)
        try:
            op = _ya_request("POST", YAART_GEN_PATH, body=cur_payload)
        except ForgeHTTPError as e:
            return {"ok": False, "dry": False, "provider": "yandexart", "mode": "generate",
                    "rights": rights, "status": e.status, "why": "шлюз YandexART: %s" % e,
                    "attempts": attempts}
        except Exception as e:
            return {"ok": False, "dry": False, "provider": "yandexart", "mode": "generate",
                    "rights": rights, "why": "YandexART: %s" % e, "attempts": attempts}
        if not isinstance(op, dict) or not op.get("id"):
            return {"ok": False, "dry": False, "provider": "yandexart", "mode": "generate",
                    "rights": rights, "why": "YandexART не вернул operation id (200 ≠ успех)",
                    "attempts": attempts}
        op_id = op["id"]
        if not op.get("done"):
            try:
                op = _ya_poll(op_id)
            except Exception as e:
                # операция ПРИНЯТА (генерация пошла → вероятное списание), а результат не дождались.
                # Это НЕ 0₽: честно фиксируем оценку в леджер и уходим (не «тихий $0.00»).
                ni_event = {"ts": int(time.time()), "mode": "generate", "provider": "yandexart",
                            "model": model_uri, "tier": "poll_error",
                            "cost_usd": YAART_EST_USD, "cost_source": "estimate_poll_error",
                            "rights": rights["level"], "attempt": i, "saved": None,
                            "op_id": op_id, "why": str(e)}
                _ledger_append(ni_event)
                spent += YAART_EST_USD
                return {"ok": False, "dry": False, "sent": True, "mode": "generate", "rights": rights,
                        "provider": "yandexart", "why": "YandexART poll: %s" % e,
                        "cost_usd": round(spent, 6), "cost_source": "sum",
                        "attempts": attempts + [{"i": i, "verdict": "poll_error", "why": str(e)}]}

        mime, raw = _ya_op_image(op)
        if not raw:                               # 200 ≠ успех: картинки нет → промах (error или пусто), ретрай
            yaerr = _ya_op_error(op)
            # ДЕНЬГИ-ПРАВДА: операция принята = генерация шла = вероятное списание → пишем оценку ДО continue.
            ni_event = {"ts": int(time.time()), "mode": "generate", "provider": "yandexart",
                        "model": model_uri, "tier": "no_image",
                        "cost_usd": YAART_EST_USD, "cost_source": "estimate_no_image",
                        "rights": rights["level"], "attempt": i, "saved": None,
                        "op_id": op_id, "ya_error": yaerr}
            _ledger_append(ni_event)
            spent += YAART_EST_USD
            attempts.append({"i": i, "verdict": "no_image", "ya_error": yaerr,
                             "cost_usd": YAART_EST_USD, "cost_source": "estimate_no_image"})
            cur_prompt = prompt + " Верни именно изображение товара."
            continue

        verdict = (verify_canon(raw, facts, donor_phashes=donor_phashes) if canon
                   else verify_output(raw, facts, donor_phashes=()))
        event = {"ts": int(time.time()), "mode": "generate", "provider": "yandexart", "model": model_uri,
                 "tier": verdict["tier"], "cost_usd": YAART_EST_USD, "cost_source": "estimate",
                 "rights": rights["level"], "attempt": i}

        accept = verdict["tier"] == "verified" or (verdict["tier"] == "ok_needs_human"
                                                   and not require_verified)
        if accept:
            path = _save_image(raw, mime or "image/jpeg", out_dir, tag)
            event["saved"] = path
            _ledger_append(event)
            report = {"ok": True, "dry": False, "sent": True, "mode": "generate", "path": path,
                      "provider": "yandexart", "model": model_uri,
                      "tier": verdict["tier"], "verdict": verdict, "rights": rights,
                      "cost_usd": event["cost_usd"], "cost_source": event["cost_source"],
                      "attempts": attempts + [{"i": i, "verdict": verdict["tier"]}]}
            if mode == "edit":
                report["mode_note"] = ("запрошен edit → выкован С НУЛЯ по фактам (YandexART-ветвь не "
                                       "редактирует донора); это наши пиксели, но не тот же SKU-кадр")
            return report

        _ledger_append(dict(event, saved=None))
        spent += YAART_EST_USD                # отбитый кадр — тоже оплачен: копим в честный итог
        attempts.append({"i": i, "verdict": verdict["tier"], "why": verdict["why"]})
        if canon:
            cur_prompt = (prompt + " КРИТИЧНО: строго чистый БЕЛЫЙ фон #FFFFFF без предметов, товар "
                          "КРУПНО по центру — занимает почти весь кадр (≈85% высоты), небольшие "
                          "равные поля, вертикаль 4:5, никакого текста и логотипов на изображении.")
        else:
            cur_prompt = prompt + " Чистый ровный фон, товар в центре, без текста и логотипов."

    return {"ok": False, "dry": False, "sent": True, "mode": "generate", "rights": rights,
            "provider": "yandexart", "why": "не удалось получить годный кадр за %d попыток" % (retries + 1),
            "cost_usd": round(spent, 6), "cost_source": "sum",   # ЧЕСТНЫЙ итог сожжённого (леджер = построчно)
            "attempts": attempts}


def forge(source=None, facts=None, ops=None, mode="edit", dry=True, model=None,
          retries=2, require_verified=False, out_dir=None, tag="item",
          canon=False, brand=None, donor_phashes=()):
    """Сковать один кадр. dry=True (по умолчанию) — собрать запрос, НЕ слать, 0₽.

    mode='edit' требует source (донорский кадр). 'generate' — рисует с нуля по facts.
    Живой режим (dry=False) гоняет выход через verify_output и ретраит промах/отбой, усиливая
    инструкцию. Возвращает честный отчёт (ok/tier/path/verdict/cost/rights) — без вранья про успех.

    canon=True — БРОНЯ ATLAS EDGE: приёмка через verify_canon (белый фон + пропорция 4:5), кадр
    вне стиля (tier=off_canon) не принимаем и ретраим канон-усилением (без «меняй фон/ракурс»,
    что дерётся с фиксированным стилем). brand — фирменный стиль в промпте: None → дефолт (вкл).
    """
    facts = facts or {}
    prov = _provider()
    # ── БРОНЯ-ГАРД: живой canon без PIL = отказ ДО траты ─────────────────────────────────
    # verify_canon меряет белый фон + 4:5 ТОЛЬКО через PIL. Без PIL is_white_bg/_aspect_ok = None,
    # ветка off_canon недостижима (см. verify_canon) → платный кадр ушёл бы «вслепую» под видом
    # ok_needs_human, а бронь ATLAS EDGE молча спала. Поэтому живой canon-форж без PIL ФИЗИЧЕСКИ
    # не тратит: единственный чок-пойнт ВСЕХ трёх провайдеров — здесь, ДО делегации (fusionbrain/
    # ru_openai) и ДО сети. Гейт строго на живом каноне: dry цел (0₽-превью), обычный (canon=False)
    # форж цел (он честно терпит ok_needs_human). Ставь Pillow в venv ~/.venvs/photoforge и куй им.
    if not dry and canon and not _have_pil():
        return {"ok": False, "dry": False, "sent": False, "provider": prov,
                "tier": "canon_unverifiable", "cost_usd": 0.0, "attempts": [],
                "rights": rights_note(mode), "canon": True,
                "why": ("бронь ATLAS EDGE (canon) запрошена, но PIL недоступен → белый фон и 4:5 "
                        "непроверяемы, verify_canon не сможет отбраковать вне-канонный кадр; "
                        "платить за непроверяемый кадр запрещено"),
                "hint": "поставь Pillow в venv ~/.venvs/photoforge и запускай им (или без --canon)"}
    # FusionBrain/Kandinsky — отдельный асинхронный путь (генерация с нуля, парная авторизация,
    # multipart). Делегируем ЦЕЛИКОМ (и dry, и live), чтобы ветки openrouter/google остались нетронуты.
    if prov == "fusionbrain":
        return _forge_fusionbrain(source, facts, ops, mode, dry, model, retries,
                                  require_verified, out_dir, tag, canon, brand,
                                  donor_phashes)
    if prov == "ru_openai":
        # RU-агрегатор (OpenAI Images) — тоже отдельный путь: тело /images/generations, generate-only.
        # Делегируем ЦЕЛИКОМ (dry+live), чтобы ветки openrouter/google остались байт-в-байт.
        return _forge_ru_openai(source, facts, ops, mode, dry, model, retries,
                                require_verified, out_dir, tag, canon, brand,
                                donor_phashes)
    if prov == "yandexart":
        # YandexART (Яндекс Cloud) — дешёвый РФ-канал: АСИНХРОННАЯ генерация с нуля, свой Api-Key/хост
        # (modelUri + поллинг operations). Тоже отдельная ветвь, как fusionbrain/ru_openai.
        return _forge_yandexart(source, facts, ops, mode, dry, model, retries,
                                require_verified, out_dir, tag, canon, brand,
                                donor_phashes)
    rights = rights_note(mode)
    use_model = model or _default_model()
    src_b64, src_raw = (None, None)

    # СУХОЙ ГЕЙТ — ВЫШЕ загрузки донора. dry не имеет права ходить в сеть (даже за бесплатным
    # чтением донорского кадра): собираем ТОЧНУЮ форму запроса и уходим, 0₽ и 0 сетевых вызовов.
    # Для превью факт «донор будет приложен» показываем маркером, БЕЗ загрузки байтов.
    if dry:
        prompt = build_prompt(facts, ops, mode, brand=brand)
        preview_src = "<<DONOR>>" if (mode == "edit" and source) else None
        payload = build_request(prompt, preview_src, model, provider=prov)
        return {"ok": True, "dry": True, "mode": mode, "sent": False, "provider": prov,
                "model": use_model, "request": _preview(payload), "est_cost_usd": EST_USD_PER_IMAGE,
                "rights": rights, "canon": bool(canon),
                "verify_plan": ("выход пройдёт verify_canon (образ/знак/pHash + белый фон + 4:5)"
                                if canon else "выход пройдёт photo_hunter (образ/знак/pHash)"),
                "note": "СУХОЙ ГЕЙТ: наружу ничего не ушло (0₽); живой кадр — dry=False по отмашке"}

    if mode == "edit":
        src_b64, src_raw = _load_source(source)
        if src_b64 is None:
            return {"ok": False, "dry": False, "why": "донорский кадр не загрузился (путь/url)",
                    "mode": mode, "rights": rights}

    prompt = build_prompt(facts, ops, mode, brand=brand)
    payload = build_request(prompt, src_b64, model, provider=prov)

    if not creds_present():
        return {"ok": False, "dry": False, "provider": prov,
                "why": "нет ключа (google: GEMINI_API_KEY · openrouter: OPENROUTER_API_KEY) — живой режим недоступен",
                "mode": mode, "rights": rights, "hint": "впиши ключ провайдера в mint/.env (gitignored)"}

    endpoint = _endpoint_path(use_model)

    # Донорские хеши (для проверки «достаточно ли непохож») — считаем один раз.
    donor_ph = []
    h = _hunter()
    if h is not None and src_raw:
        p = h.phash(src_raw)
        if p:
            donor_ph.append(p)

    attempts = []
    cur_prompt = prompt
    for i in range(retries + 1):
        payload = build_request(cur_prompt, src_b64, model, provider=prov)
        try:
            resp = _request("POST", endpoint, body=payload)
        except ForgeHTTPError as e:
            return {"ok": False, "dry": False, "why": "шлюз: %s" % e, "status": e.status,
                    "provider": prov, "mode": mode, "rights": rights, "attempts": attempts}
        except Exception as e:
            return {"ok": False, "dry": False, "why": "сеть: %s" % e,
                    "provider": prov, "mode": mode, "rights": rights, "attempts": attempts}

        mime, raw = extract_image(resp)
        if not raw:                               # 200 ≠ успех: картинки нет → промах
            fr = _finish_reason(resp)             # почему (safety/recitation)? — честно в лог
            attempts.append({"i": i, "verdict": "no_image", "finish_reason": fr})
            cur_prompt = prompt + " Верни именно изображение."
            continue

        verdict = (verify_canon(raw, facts, donor_phashes=donor_ph) if canon
                   else verify_output(raw, facts, donor_phashes=donor_ph))
        cost = _usage_cost(resp)
        event = {"ts": int(time.time()), "mode": mode, "provider": prov, "model": use_model,
                 "tier": verdict["tier"], "cost_usd": cost if cost is not None else EST_USD_PER_IMAGE,
                 "cost_source": "usage" if cost is not None else "estimate",
                 "rights": rights["level"], "attempt": i}

        accept = verdict["tier"] == "verified" or (verdict["tier"] == "ok_needs_human"
                                                   and not require_verified)
        if accept:
            path = _save_image(raw, mime, out_dir, tag)
            event["saved"] = path
            _ledger_append(event)
            return {"ok": True, "dry": False, "sent": True, "mode": mode, "path": path,
                    "provider": prov, "model": use_model,
                    "tier": verdict["tier"], "verdict": verdict, "rights": rights,
                    "cost_usd": event["cost_usd"], "cost_source": event["cost_source"],
                    "attempts": attempts + [{"i": i, "verdict": verdict["tier"]}]}

        # Отбой (знак/склейка/вне канона) → усилить инструкцию и ретрайнуть.
        _ledger_append(dict(event, saved=None))
        attempts.append({"i": i, "verdict": verdict["tier"], "why": verdict["why"]})
        if canon:
            # Канон-режим: НЕ просим «меняй фон/ракурс» (это дерётся с фиксированным стилем) —
            # наоборот, ужесточаем фирменный контракт: белый фон, центр, 4:5, без чужого знака.
            cur_prompt = (prompt + " КРИТИЧНО: строго чистый БЕЛЫЙ фон #FFFFFF без предметов, "
                          "товар КРУПНО по центру — занимает почти весь кадр (≈85% высоты), "
                          "небольшие равные поля, вертикаль 4:5, полностью убери любой чужой "
                          "водяной знак и логотипы; никакого текста на изображении.")
        else:
            cur_prompt = (prompt + " ВАЖНО: полностью убери любой чужой водяной знак и логотипы; "
                          "заметно измени фон и ракурс, чтобы кадр был уникальным.")

    return {"ok": False, "dry": False, "sent": True, "mode": mode, "rights": rights,
            "provider": prov, "why": "не удалось получить годный кадр за %d попыток" % (retries + 1),
            "attempts": attempts}


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="ФОТО-КУЗНИЦА V1 — стадия DUB (Nano Banana / OpenRouter)")
    ap.add_argument("--mode", choices=("edit", "generate"), default="edit")
    ap.add_argument("--source", default="", help="донорское фото (путь или url) для mode=edit")
    ap.add_argument("--facts", default="", help='факты о товаре как JSON, напр \'{"цвет":"синий"}\'')
    ap.add_argument("--model", default="", help="слаг модели (по умолч. Nano Banana)")
    ap.add_argument("--out", default="", help="папка для выходного файла")
    ap.add_argument("--live", action="store_true", help="БОЕВОЙ вызов (тратит ₽). Без него — dry (0₽)")
    ap.add_argument("--require-verified", action="store_true", help="принимать только verified (строго)")
    ap.add_argument("--canon", action="store_true",
                    help="БРОНЯ ATLAS EDGE: приёмка verify_canon (белый фон+4:5); живьём без PIL — честный отказ ДО траты")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    caps = capabilities()
    print("ФОТО-КУЗНИЦА · паспорт возможностей:")
    for k in ("key", "net", "image_probe", "ocr"):
        print("   %-12s %s" % (k, "да" if caps.get(k) else "НЕТ"))
    if not caps["key"]:
        print("   (ключа нет → доступен только dry, 0₽)")

    facts = {}
    if args.facts:
        try:
            facts = json.loads(args.facts)
        except Exception:
            print("!! --facts не разобран как JSON, игнорирую")
    res = forge(source=args.source or None, facts=facts, mode=args.mode, dry=not args.live,
                model=args.model or None, require_verified=args.require_verified,
                out_dir=args.out or None, canon=args.canon)
    print()
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1
    print("режим: %s · dry: %s · ok: %s" % (res.get("mode"), res.get("dry"), res.get("ok")))
    if res.get("dry"):
        print("   запрос:", json.dumps(res["request"], ensure_ascii=False))
        print("   оценка ₽/кадр: ~$%.3f · %s" % (res["est_cost_usd"], res["note"]))
    else:
        print("   вердикт:", res.get("tier"), "· путь:", res.get("path"))
        if res.get("why"):
            print("   почему:", res["why"])
    r = res.get("rights", {})
    print("   права: %s — %s" % (r.get("level"), r.get("note")))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    import sys
    sys.exit(_main())

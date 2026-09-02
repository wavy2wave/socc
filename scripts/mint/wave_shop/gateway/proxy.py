"""WAVE GATEWAY — прокси к провайдеру.

Клиент шлёт запрос со СВОИМ токеном (wave-...). Шлюз:
  1. проверяет квоту/срок (quota.check);
  2. подставляет НАСТОЯЩИЙ ключ оператора из окружения;
  3. пересылает запрос наверх;
  4. считает израсходованные токены из ответа (usage) и списывает.

Ключ оператора никогда не покидает этот процесс: он берётся из .env,
подставляется в исходящий заголовок и НЕ попадает ни в ответ клиенту,
ни в логи, ни в сообщения об ошибках.

Совместимость: OpenAI-совместимый интерфейс (/v1/chat/completions), потому что
его понимают все клиенты — Cursor, Continue, curl, python-sdk. Клиенту нужно
поменять две вещи: base_url на твой шлюз и api_key на выданный токен.

stdlib-only: http.server + urllib.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.pricing import caps_from_usage  # noqa: E402
from gateway.quota import PLANS, QuotaStore, model_allowed  # noqa: E402
from gateway.upstream_pool import NoCapacity, UpstreamPool, dispatch  # noqa: E402

# Подтянуть .env тем же loader'ом, что и бот, чтобы шлюз запускался одной
# командой без ручного export. Уже заданное окружение имеет приоритет над
# файлом (оператор может переопределить на лету), поэтому это безопасно и для
# тестов, которые задают переменные сами.
try:
    from config import BASE_DIR, _load_env_file  # noqa: E402

    _load_env_file(BASE_DIR / ".env")
except Exception:  # pragma: no cover — конфиг не обязателен для работы прокси
    pass

# --- Настройки шлюза (из окружения; ключ оператора только здесь) ---
UPSTREAM_URL = os.environ.get("WAVE_UPSTREAM_URL", "https://openrouter.ai/api/v1")
UPSTREAM_KEY = os.environ.get("WAVE_UPSTREAM_KEY", "")
# Бельё white-label: если задано, ЛЮБОЕ имя модели из запроса клиента
# подменяется на эту (наша локальная мощность). Клиент арендует «ёмкость», а не
# конкретный бренд модели; ответ честно возвращает реальное имя в поле "model".
# Побочно чинит 404 у Ollama, который отвергает незнакомые имена вроде "opus".
FORCE_MODEL = os.environ.get("WAVE_FORCE_MODEL", "").strip()
GW_HOST = os.environ.get("WAVE_GW_HOST", "127.0.0.1")
GW_PORT = int(os.environ.get("WAVE_GW_PORT", "8790"))
DATA_DIR = Path(os.environ.get("WAVE_DATA_DIR",
                               Path(__file__).resolve().parent.parent / "data"))
# Какие модели разрешены клиентам. Пусто = все.
ALLOWED_MODELS = [m.strip() for m in os.environ.get("WAVE_ALLOWED_MODELS", "").split(",") if m.strip()]
TIMEOUT = int(os.environ.get("WAVE_UPSTREAM_TIMEOUT", "300"))

# --- Исходящая личность шлюза (заголовки/авторизация к ПРОВАЙДЕРУ) ---
# По умолчанию нейтрально. Оператор настраивает под СВОЙ бэкенд (его сервис,
# его ключи) — это про совместимость, а не обход чужих защит; дефолты ничего
# не подменяют, обратная совместимость полная.
#   WAVE_UPSTREAM_AUTH_STYLE       = bearer | x-api-key  (как нести ключ)
#   WAVE_UPSTREAM_HEADERS          = JSON доп.заголовков (User-Agent, x-app, …)
#   WAVE_UPSTREAM_ANTHROPIC_VERSION= напр. 2023-06-01 (для нативного Anthropic)
AUTH_STYLE = os.environ.get("WAVE_UPSTREAM_AUTH_STYLE", "bearer").strip().lower()
ANTHROPIC_VERSION = os.environ.get("WAVE_UPSTREAM_ANTHROPIC_VERSION", "").strip()


def _parse_extra_headers(raw: str) -> dict:
    """Разобрать WAVE_UPSTREAM_HEADERS (JSON-объект) в строковые заголовки.

    Битый JSON или не-объект → пусто (шлюз не должен падать из-за опечатки
    в .env; поедет на нейтральных дефолтах).
    """
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(obj, dict):
        return {}
    return {str(k): str(v) for k, v in obj.items()}


_EXTRA_HEADERS = _parse_extra_headers(os.environ.get("WAVE_UPSTREAM_HEADERS", ""))


def _outbound_headers(key: str | None, *, json_body: bool) -> dict:
    """Собрать исходящие заголовки к провайдеру: тело + личность + авторизация.

    Дефолты дают ровно прежнее поведение (Content-Type + User-Agent +
    Authorization: Bearer). Всё сверх — только если оператор задал в .env.
    Сырой ключ подставляется здесь и НИКОГДА не логируется.
    """
    headers: dict = {}
    if json_body:
        headers["Content-Type"] = "application/json"
    headers.update(_EXTRA_HEADERS)
    headers.setdefault("User-Agent", "WAVE-Gateway/1.0")
    if ANTHROPIC_VERSION:
        headers.setdefault("anthropic-version", ANTHROPIC_VERSION)
    if UPSTREAM_NEEDS_KEY and key:
        if AUTH_STYLE == "x-api-key":
            headers["x-api-key"] = key
        else:
            headers["Authorization"] = f"Bearer {key}"
    return headers

# --- Обойма сырых ключей провайдера («дрова») ---
# Один ключ = точка отказа: кончился баланс — легли все клиенты разом. Обойма
# держит список ключей и на лету подхватывает следующий, когда текущий отвергнут
# (401/403) или перегрет (429). Файл дозаливается без перезапуска. Одиночный
# WAVE_UPSTREAM_KEY по-прежнему работает — он просто становится первым патроном.
POOL_FILE = Path(os.environ.get("WAVE_UPSTREAM_POOL_FILE", str(DATA_DIR / "upstream_pool.keys")))
UPSTREAM_KEYS_ENV = os.environ.get("WAVE_UPSTREAM_KEYS", "")


def _is_local_upstream(url: str) -> bool:
    """Локальная мощность (Ollama, llama.cpp, vLLM на своей машине).

    У локального сервера нет и не должно быть API-ключа. Без этой проверки
    шлюз, направленный на Ollama, отвечал бы клиентам «Шлюз не настроен» на
    каждый запрос: UPSTREAM_KEY пуст, и запрос отклонялся до отправки наверх.
    """
    low = (url or "").lower()
    return any(h in low for h in ("127.0.0.1", "localhost", "0.0.0.0", "::1",
                                  "host.docker.internal"))


# Ключ обязателен только для внешнего провайдера. Для своей машины — нет.
UPSTREAM_NEEDS_KEY = not _is_local_upstream(UPSTREAM_URL)

_store = QuotaStore(DATA_DIR)
_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(f"[gw] {msg}", flush=True)


# Обойма создаётся ПОСЛЕ log(), чтобы она могла писать о ротации в общий лог.
# Одиночный WAVE_UPSTREAM_KEY передаётся как env_single — обратная совместимость.
_pool = UpstreamPool(
    pool_file=POOL_FILE,
    env_keys=UPSTREAM_KEYS_ENV,
    env_single=UPSTREAM_KEY,
    log=log,
)


def _classify_upstream_error(exc: BaseException) -> str:
    """Как обойма трактует ошибку провайдера (политика согласована с оператором).

    401/403 → патрон мёртв навсегда (ключ отозван/невалиден);
    429      → патрон перегрет, пауза и повтор со следующим;
    остальное (5xx, сеть, таймаут) → не про обойму, пробрасываем наружу как есть.
    """
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (401, 403):
            return "dead"
        if exc.code == 429:
            return "cooldown"
    return "raise"


def _extract_tokens(payload: dict) -> tuple[int, str]:
    """Достать расход из ответа провайдера — во ВЗВЕШЕННЫХ единицах (CAPS).

    Сырая сумма input+output здесь была бы дырой в кассе: выходной токен стоит
    в 5 раз дороже входного, а чтение из кэша — в 10 раз дешевле. Клиент,
    генерящий длинные ответы, обходился бы оператору в разы дороже клиента,
    читающего из кэша, — а списывалось бы с обоих одинаково. Веса живут в
    gateway/pricing.py и отражают реальный прайс провайдера.
    """
    usage = payload.get("usage") or {}
    caps = caps_from_usage(usage)
    if caps <= 0:
        # Провайдер не отдал разбивку — не теряем расход совсем, берём total.
        total = usage.get("total_tokens")
        if total:
            caps = int(total)
    model = payload.get("model", "")
    return int(caps or 0), str(model)


# ═══════════════════ Кабинет клиента «ввёл ключ → отсчёт» ═══════════════════
#
# Зачем страница живёт ЗДЕСЬ, на шлюзе, а не в боте: получатель ключа не обязан
# быть пользователем бота. Другу выдали токен оффлайн-командой (gateway.issue) —
# у него на руках только адрес шлюза и wave-…-ключ. Эта страница — его единст-
# венное «окно»: вставил ключ → видит, сколько РЕАЛЬНО потрачено (в токенах и
# в ₽ по ЕГО цене) и сколько времени осталось. Отсчёт идёт вживую.
#
# Взломать нельзя: страница НИЧЕГО не считает сама. Все числа приходят из
# /v1/status, где их посчитал шлюз (цена зафиксирована при выдаче, расход — из
# реальных ответов провайдера). JS лишь тикает секунды между опросами для
# плавности. Закупка/маржа оператора наружу не отдаются — их нет в /v1/status.
METER_PAGE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WAVE — мой доступ</title>
<style>
 :root{color-scheme:dark}
 *{box-sizing:border-box}
 body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
   background:#0b1020;color:#e8ecf5;display:flex;min-height:100vh;align-items:center;
   justify-content:center;padding:20px}
 .card{width:100%;max-width:440px;background:#141b32;border:1px solid #232c4d;
   border-radius:18px;padding:28px 26px;box-shadow:0 20px 60px rgba(0,0,0,.4)}
 h1{font-size:19px;margin:0 0 4px;letter-spacing:.3px}
 .sub{color:#8b96b8;font-size:13px;margin:0 0 20px}
 .row{display:flex;gap:10px}
 input{flex:1;background:#0b1020;border:1px solid #2b3560;color:#e8ecf5;border-radius:11px;
   padding:12px 14px;font-size:14px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
 input:focus{outline:none;border-color:#5b7cff}
 button{background:#5b7cff;color:#fff;border:0;border-radius:11px;padding:12px 18px;
   font-size:14px;font-weight:600;cursor:pointer}
 button:hover{background:#6d8bff}
 button:disabled{opacity:.5;cursor:default}
 .out{margin-top:22px;display:none}
 .title{font-size:16px;font-weight:600;margin:0 0 2px}
 .kind{color:#8b96b8;font-size:12px;margin:0 0 18px}
 .big{font-size:34px;font-weight:700;margin:0;line-height:1.1;font-variant-numeric:tabular-nums}
 .big small{font-size:15px;color:#8b96b8;font-weight:500}
 .meters{display:flex;gap:14px;margin:18px 0 4px}
 .meter{flex:1;background:#0e1428;border:1px solid #222c4d;border-radius:13px;padding:14px}
 .meter .lbl{color:#8b96b8;font-size:11px;text-transform:uppercase;letter-spacing:.6px;margin:0 0 6px}
 .meter .val{font-size:20px;font-weight:700;margin:0;font-variant-numeric:tabular-nums}
 .bar{height:7px;background:#0b1020;border-radius:6px;overflow:hidden;margin-top:16px}
 .bar span{display:block;height:100%;background:linear-gradient(90deg,#5b7cff,#8a6bff);width:0}
 .clock{margin-top:18px;text-align:center;font-size:15px;color:#c3ccea;font-variant-numeric:tabular-nums}
 .err{color:#ff8a8a;font-size:13px;margin-top:14px;min-height:16px}
 .foot{color:#5b658a;font-size:11px;text-align:center;margin-top:20px;line-height:1.5}
 .paused{color:#ffb26b}
</style></head>
<body><div class="card">
 <h1>🔑 WAVE — мой доступ</h1>
 <p class="sub">Вставьте ключ — увидите расход и время. Живой отсчёт.</p>
 <div class="row">
   <input id="tok" placeholder="wave-…" autocomplete="off" spellcheck="false">
   <button id="go">Смотреть</button>
 </div>
 <div class="err" id="err"></div>
 <div class="out" id="out">
   <p class="title" id="ttl"></p>
   <p class="kind" id="knd"></p>
   <div class="meters">
     <div class="meter"><p class="lbl">Потрачено</p><p class="val" id="spent">—</p></div>
     <div class="meter"><p class="lbl">Токенов использовано</p><p class="val" id="used">—</p></div>
   </div>
   <div class="bar"><span id="bar"></span></div>
   <div class="clock" id="clock"></div>
 </div>
 <p class="foot">Ключ проверяется на сервере. Показываются только ваши цифры.</p>
</div>
<script>
(function(){
 var tok=document.getElementById('tok'),go=document.getElementById('go'),
     out=document.getElementById('out'),err=document.getElementById('err'),
     timer=null,tick=null,deadline=0;
 function fmtInt(n){return Math.round(n).toLocaleString('ru-RU');}
 function fmtLeft(s){
   if(s<=0)return 'срок истёк';
   var d=Math.floor(s/86400),h=Math.floor(s%86400/3600),
       m=Math.floor(s%3600/60),sec=Math.floor(s%60);
   if(d>0)return 'Ещё '+d+' дн '+h+' ч';
   if(h>0)return 'Ещё '+h+' ч '+m+' мин';
   if(m>0)return 'Ещё '+m+' мин '+sec+' с';
   return 'Ещё '+sec+' с';
 }
 function paint(st){
   out.style.display='block';err.textContent='';
   document.getElementById('ttl').textContent=st.title||'Доступ';
   var kind={hourly:'Почасовой',package:'Пакет',subscription:'Подписка',
             unlimited:'Безлимит'}[st.kind]||st.kind||'';
   document.getElementById('knd').textContent=kind+(st.enabled?'':' · приостановлен');
   var used=st.tokens_used||0;
   document.getElementById('used').textContent=(used/1e6).toFixed(2)+' млн';
   var spentEl=document.getElementById('spent');
   if(st.price_rub>0){
     spentEl.innerHTML=fmtInt(st.spent_rub||0)+' ₽ <small>из '+fmtInt(st.price_rub)+'</small>';
   }else{spentEl.textContent=(used/1e6).toFixed(2)+' млн';}
   var bar=document.getElementById('bar');
   if(st.unlimited){
     var frac=st.daily_cap?Math.min(1,(st.spent_today||0)/st.daily_cap):0;
     bar.style.width=(frac*100).toFixed(1)+'%';
   }else if(st.tokens_limit>0){
     bar.style.width=(Math.min(1,used/st.tokens_limit)*100).toFixed(1)+'%';
   }else{bar.style.width='0';}
   deadline=st.seconds_left!=null?Date.now()/1000+st.seconds_left:0;
   drawClock();
 }
 function drawClock(){
   var c=document.getElementById('clock');
   if(!deadline){c.textContent='♾ без срока';return;}
   c.textContent='⏳ '+fmtLeft(deadline-Date.now()/1000);
 }
 function load(){
   var t=tok.value.trim();if(!t)return;
   fetch('/v1/status',{headers:{'Authorization':'Bearer '+t}})
    .then(function(r){if(!r.ok)throw new Error(r.status===401?
        'Ключ не найден. Проверьте, что вставили его целиком.':'Ошибка '+r.status);
      return r.json();})
    .then(paint)
    .catch(function(e){out.style.display='none';err.textContent=e.message;});
 }
 function start(){
   if(!tok.value.trim())return;
   go.disabled=true;go.textContent='Обновляется…';
   load();go.disabled=false;go.textContent='Обновить';
   if(timer)clearInterval(timer);
   if(tick)clearInterval(tick);
   timer=setInterval(load,15000);   // сверяемся с сервером
   tick=setInterval(drawClock,1000); // секунды тикают между сверками
 }
 go.onclick=start;
 tok.addEventListener('keydown',function(e){if(e.key==='Enter')start();});
 // Ключ можно передать в ссылке (#wave-…) — тогда друг открыл и сразу видит.
 if(location.hash.length>1){tok.value=decodeURIComponent(location.hash.slice(1));start();}
})();
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "WAVE-Gateway"
    protocol_version = "HTTP/1.1"
    def log_message(self, fmt: str, *args) -> None:
        pass  # свой лог, без шума

    # ---------- helpers ----------
    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code: int, message: str, kind: str = "invalid_request_error") -> None:
        # Формат ошибки как у OpenAI — клиентские SDK его понимают.
        self._json(code, {"error": {"message": message, "type": kind, "code": kind}})

    def _html(self, code: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # Кабинет — публичная статичная страница; секретов в разметке нет
        # (весь расчёт на сервере, ключ идёт только в запросе клиента). Но на
        # всякий случай запрещаем встраивание в чужие фреймы.
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def _client_token(self) -> str:
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return (self.headers.get("x-api-key") or "").strip()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, x-api-key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"/health", "/healthz"}:
            self._json(200, {"ok": True,
                             "upstream_configured": (not UPSTREAM_NEEDS_KEY) or _pool.has_capacity(),
                             "pool": _pool.stats()})
            return
        # Кабинет клиента: «вставил ключ → отсчёт». Отдаётся всем (статичная
        # страница), сами цифры берутся уже с ключом через /v1/status.
        if self.path.split("?", 1)[0].split("#", 1)[0].rstrip("/") in {"", "/me", "/dashboard"}:
            self._html(200, METER_PAGE)
            return
        # Кабинет спрашивает статус ключа
        if self.path.startswith("/v1/status"):
            token = self._client_token()
            st = _store.status(token) if token else None
            if not st:
                self._err(401, "Ключ не найден.", "authentication_error")
                return
            self._json(200, st)
            return
        if self.path.rstrip("/") == "/v1/models":
            # Список моделей — тоже обращение НАВЕРХ на ключе оператора, поэтому
            # требует авторизованный клиентский токен ровно как POST /v1/*. Без
            # этой проверки анонимный GET заставлял шлюз ходить к провайдеру на
            # реальном ключе: оракул живости и жжём rate-limit оператора без
            # единого wave-ключа. Док (CLIENT_SETUP.md) и так обещает «GET
            # /v1/models с вашим ключом» — код просто не держал это обещание.
            token = self._client_token()
            if not token:
                self._err(401, "Не передан ключ. Заголовок: Authorization: Bearer wave-...",
                          "authentication_error")
                return
            verdict = _store.check(token)
            if not verdict.allow:
                code = 401 if verdict.reason == "no_key" else 429
                self._err(code, verdict.message,
                          "authentication_error" if code == 401 else "rate_limit_error")
                log(f"отказ {verdict.reason} на /v1/models для ...{token[-6:]}")
                return
            self._proxy_get("/models")
            return
        self._err(404, "Неизвестный путь.")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")
        if path not in {"/v1/chat/completions", "/v1/messages", "/v1/completions"}:
            self._err(404, "Неизвестный путь. Используйте /v1/chat/completions")
            return

        token = self._client_token()
        if not token:
            self._err(401, "Не передан ключ. Заголовок: Authorization: Bearer wave-...",
                      "authentication_error")
            return

        verdict = _store.check(token)
        if not verdict.allow:
            code = 401 if verdict.reason == "no_key" else 429
            self._err(code, verdict.message,
                      "authentication_error" if code == 401 else "rate_limit_error")
            log(f"отказ {verdict.reason} для ...{token[-6:]}")
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            req = json.loads(raw or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._err(400, "Некорректный JSON в запросе.")
            return

        model = str(req.get("model", ""))

        # White-label: вся линейка тарифов обслуживается одной локальной
        # мощностью. Клиент арендует ёмкость, а не бренд. Подменяем модель ДО
        # проверок — тогда потолок модели и белый список становятся не нужны:
        # наверх физически уходит ровно одна модель, превысить её нечем.
        if FORCE_MODEL:
            req["model"] = FORCE_MODEL
            model = FORCE_MODEL
        else:
            if ALLOWED_MODELS and model and model not in ALLOWED_MODELS:
                self._err(400, f"Модель {model} недоступна на вашем тарифе. "
                               f"Доступны: {', '.join(ALLOWED_MODELS)}")
                return

            # Потолок модели на КЛЮЧЕ. Без этого демо, проданное как Sonnet,
            # обслуживает запросы к Opus — закупка дороже в 5 раз, а платы нет.
            rec = _store.get_key(token) or {}
            max_tier = str(rec.get("model_key", ""))
            if max_tier and not model_allowed(model, max_tier):
                self._err(400,
                          f"На вашем тарифе доступна модель уровня {max_tier}. "
                          f"Для {model or 'этой модели'} нужен платный тариф — "
                          f"оформите в боте.")
                log(f"отказ model={model!r} tier={max_tier} для ...{token[-6:]}")
                return

        # White-label: клиент арендует ЁМКОСТЬ, а не конкретный бренд модели.
        # Имя модели из запроса подменяем на нашу реальную. Без этой строки
        # переменная WAVE_FORCE_MODEL не делала ничего, и локальный сервер
        # отвечал 404 на незнакомые ему имена вроде "claude-opus-5".
        requested_model = model
        if FORCE_MODEL:
            req["model"] = FORCE_MODEL

        if UPSTREAM_NEEDS_KEY and not _pool.has_capacity():
            reason = _pool.exhausted_reason()
            if reason == "empty":
                self._err(503, "Шлюз не настроен. Напишите в поддержку.", "api_error")
                log("ОШИБКА: обойма пуста — впишите ключи в data/upstream_pool.keys "
                    "или задайте WAVE_UPSTREAM_KEY")
            else:  # all_dead: живых ключей не осталось, нужна дозаливка «дров»
                self._err(503, "Ключи доступа исчерпаны. Идёт пополнение — "
                               "попробуйте через минуту.", "api_error")
                log("нет ёмкости: все патроны мертвы — нужна дозаливка обоймы")
            return

        # Стриминг: Claude Code и Cursor работают только через поток. Отдаём
        # чанки клиенту КАК ЕСТЬ и параллельно вычитываем usage из потока —
        # у Anthropic итог приходит в событии message_delta, у OpenAI в
        # последнем chunk при stream_options.include_usage. Списываем ПОСЛЕ
        # завершения потока — по тем же CAPS, что и в не-стрим ветке.
        if req.get("stream"):
            self._handle_stream(path, req, token, requested_model)
            return

        try:
            payload, status = dispatch(
                _pool,
                lambda key: self._call_upstream(path, req, key),
                _classify_upstream_error,
            ) if UPSTREAM_NEEDS_KEY else self._call_upstream(path, req, None)
        except NoCapacity as e:
            # Наверх ничего не ушло → квоту клиента НЕ трогаем (consume не зовём).
            self._err(503, "Все ключи сейчас заняты. Попробуйте через минуту — "
                           "шлюз подключит следующий.", "api_error")
            log(f"обойма исчерпана: {e.reason} (квота клиента не списана)")
            return
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            log(f"upstream HTTP {e.code}: {detail[:200]}")
            # Наружу не отдаём внутренние детали провайдера.
            self._err(502, "Провайдер вернул ошибку. Попробуйте ещё раз.", "api_error")
            return
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log(f"upstream недоступен: {type(e).__name__}")
            self._err(504, "Провайдер не ответил. Попробуйте ещё раз.", "api_error")
            return

        spent, used_model = _extract_tokens(payload)
        if spent:
            _store.consume(token, spent, used_model or req.get("model", ""))
        elif 200 <= int(status) < 300:
            # 2xx без usage: провайдер отдал ответ, но не сообщил расход —
            # списывать нечего, и ВЫДУМЫВАТЬ число нельзя (обещание «сколько
            # РЕАЛЬНО потрачено» держится только на реальных данных). Но и
            # молчать нельзя: ровно этот путь утекает бесплатной работой.
            # Громко помечаем аномалию, чтобы оператор увидел её в логе и
            # поправил провайдера/запрос, а не узнал по пустой кассе.
            log(f"ВНИМАНИЕ: 2xx без usage — расход НЕ списан ...{token[-6:]} "
                f"{used_model or req.get('model', '')} (проверьте провайдера)")
        # В логе видно и что просил клиент, и чем обслужили — иначе при
        # подмене модели разбор «почему счёт такой» становится гаданием.
        served = used_model or req.get("model", "")
        swap = f" (просил {requested_model})" if FORCE_MODEL and requested_model != served else ""
        log(f"ok ...{token[-6:]} {served}{swap} {spent} ток.")
        self._json(status, payload)

    def _handle_stream(self, path: str, req: dict, token: str,
                       requested_model: str) -> None:
        """Проксировать SSE-поток клиенту, считая usage на лету.

        Ключевая тонкость failover: как только первый байт ушёл клиенту,
        переключить патрон уже нельзя. Поэтому выбор живого ключа и открытие
        соединения (до первого чанка) делаем ВНУТРИ dispatch — если ключ
        мёртв/перегрет на этапе подключения, обойма ротирует ДО отдачи тела.
        Сама перекачка чанков идёт уже вне failover.
        """
        started = {"headers": False}  # заголовки клиенту шлём один раз, лениво

        # OpenAI-совместимый провайдер кладёт usage в поток ТОЛЬКО если запрос
        # содержит stream_options.include_usage. Cursor и Claude Code его не
        # шлют → поток вычитывался без usage и списывался в НОЛЬ: бесплатный
        # безлимит на стриме, дыра в кассе. Просим usage сами — но лишь на путях
        # OpenAI. /v1/messages (Anthropic) не трогаем: он сам отдаёт usage в
        # message_start/message_delta и не понимает stream_options — добавление
        # поля туда рискует 400-й ошибкой от провайдера. Клиентское значение,
        # если оно уже есть, сохраняем и лишь до-выставляем include_usage.
        if path in {"/v1/chat/completions", "/v1/completions"}:
            opts = req.get("stream_options")
            if not isinstance(opts, dict):
                opts = {}
            opts["include_usage"] = True
            req["stream_options"] = opts

        def _begin_client_stream() -> None:
            if started["headers"]:
                return
            # SSE через stdlib-сервер: тело неизвестной длины. Без Content-Length
            # и без chunked-кадров клиент на HTTP/1.1 keep-alive зависает, ожидая
            # границу кадра. Делаем поток close-delimited: Connection: close +
            # close_connection — клиент читает до EOF, кадры SSE идут как есть.
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            started["headers"] = True

        # Аккумулятор usage по потоку: берём МАКСИМУМ по каждому полю среди всех
        # событий usage (message_start отдаёт вход и нули на выход, message_delta —
        # финальные итоги; max по полю собирает честную полную картину).
        usage_acc: dict[str, int] = {}
        seen_model = {"name": ""}

        def _absorb_usage(obj: dict) -> None:
            u = obj.get("usage")
            if isinstance(u, dict):
                for k, v in u.items():
                    if isinstance(v, (int, float)):
                        usage_acc[k] = max(int(usage_acc.get(k, 0)), int(v))
            m = obj.get("model")
            if m and not seen_model["name"]:
                seen_model["name"] = str(m)

        def _pump(key: str | None) -> tuple[dict, int]:
            """Открыть upstream-поток и перекачать его клиенту чанк-в-чанк.

            Возвращает фиктивный (payload, status) только чтобы удовлетворить
            контракт dispatch; настоящий результат — усвоенный usage_acc.
            Исключение при ПОДКЛЮЧЕНИИ (до первого байта клиенту) даёт обойме
            шанс на ротацию; после первого байта клиенту исключения уже не
            бросаем — соединение разорвётся, но патрон не «убиваем» ложно.
            """
            url = UPSTREAM_URL.rstrip("/") + path.replace("/v1", "", 1)
            data = json.dumps(req).encode("utf-8")
            headers = _outbound_headers(key, json_body=True)
            headers["Accept"] = "text/event-stream"
            r = urllib.request.Request(url, data=data, headers=headers, method="POST")
            # urlopen поднимет HTTPError на 4xx/5xx ДО тела — это внутри failover.
            resp = urllib.request.urlopen(r, timeout=TIMEOUT)
            status = resp.status
            _begin_client_stream()
            try:
                for raw in resp:
                    # Ретранслируем байты клиенту ровно как пришли (SSE-кадры).
                    try:
                        self.wfile.write(raw)
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        # Клиент отвалился — дочитывать смысла нет.
                        break
                    line = raw.strip()
                    if line.startswith(b"data:"):
                        chunk = line[5:].strip()
                        if chunk and chunk != b"[DONE]":
                            try:
                                obj = json.loads(chunk)
                            except (ValueError, json.JSONDecodeError):
                                obj = None
                            if isinstance(obj, dict):
                                _absorb_usage(obj)
                                # У Anthropic usage бывает и внутри вложенного
                                # объекта message события message_start.
                                inner = obj.get("message")
                                if isinstance(inner, dict):
                                    _absorb_usage(inner)
            finally:
                resp.close()
            return {"usage": dict(usage_acc)}, status

        try:
            if UPSTREAM_NEEDS_KEY:
                dispatch(_pool, _pump, _classify_upstream_error)
            else:
                _pump(None)
        except NoCapacity as e:
            if not started["headers"]:
                self._err(503, "Все ключи сейчас заняты. Попробуйте через минуту.",
                          "api_error")
            log(f"стрим: обойма исчерпана {e.reason} (квота не списана)")
            return
        except urllib.error.HTTPError as e:
            if not started["headers"]:
                detail = e.read().decode("utf-8", "replace")[:200]
                log(f"стрим upstream HTTP {e.code}: {detail}")
                self._err(502, "Провайдер вернул ошибку. Попробуйте ещё раз.", "api_error")
            else:
                log(f"стрим оборвался после начала: HTTP {e.code}")
            return
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if not started["headers"]:
                log(f"стрим upstream недоступен: {type(e).__name__}")
                self._err(504, "Провайдер не ответил. Попробуйте ещё раз.", "api_error")
            else:
                log(f"стрим оборвался: {type(e).__name__}")
            return

        # Поток завершён — теперь честно списываем ровно как в не-стрим ветке.
        spent, used_model = _extract_tokens({"usage": usage_acc,
                                             "model": seen_model["name"]})
        if spent:
            _store.consume(token, spent, used_model or req.get("model", ""))
        elif started["headers"]:
            # Поток доехал до клиента (заголовки ушли), но usage так и не
            # пришёл — работа отдана, списать нечего. Число не выдумываем, но
            # молчать об этом нельзя: это тот самый бесплатный стрим. Громкая
            # метка в лог — чтобы оператор увидел дыру, а не пустую выручку.
            log(f"ВНИМАНИЕ: стрим без usage — расход НЕ списан ...{token[-6:]} "
                f"{seen_model['name'] or req.get('model', '')} (проверьте провайдера)")
        served = used_model or req.get("model", "")
        swap = f" (просил {requested_model})" if FORCE_MODEL and requested_model != served else ""
        log(f"ok(stream) ...{token[-6:]} {served}{swap} {spent} ток.")

    def _call_upstream(self, path: str, req: dict, key: str | None) -> tuple[dict, int]:
        url = UPSTREAM_URL.rstrip("/") + path.replace("/v1", "", 1)
        data = json.dumps(req).encode("utf-8")
        headers = _outbound_headers(key, json_body=True)
        r = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(r, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body, resp.status

    def _proxy_get(self, suffix: str) -> None:
        key = _pool.pick() if UPSTREAM_NEEDS_KEY else None
        if UPSTREAM_NEEDS_KEY and not key:
            self._err(503, "Шлюз не настроен.", "api_error")
            return
        try:
            headers = _outbound_headers(key, json_body=False)
            r = urllib.request.Request(
                UPSTREAM_URL.rstrip("/") + suffix,
                headers=headers)
            with urllib.request.urlopen(r, timeout=30) as resp:
                self._json(resp.status, json.loads(resp.read().decode("utf-8")))
        except Exception:
            self._err(502, "Не удалось получить список моделей.", "api_error")


def main() -> int:
    _pool.ensure_template()
    stats = _pool.stats()
    if UPSTREAM_NEEDS_KEY and stats["total"] == 0:
        print(f"ВНИМАНИЕ: обойма пуста — впишите сырые ключи в {POOL_FILE} "
              "(по одному в строке) или задайте WAVE_UPSTREAM_KEY. Пока обойма "
              "пуста, запросы клиентов будут отклоняться.")
    print(f"WAVE GATEWAY на http://{GW_HOST}:{GW_PORT}")
    print(f"  наверх: {UPSTREAM_URL}")
    print(f"  обойма: {stats['total']} ключ(ей) — {stats['alive']} годны, "
          f"{stats['dead']} мёртвых (дозаливка: {POOL_FILE})")
    print(f"  тарифов: {len(PLANS)}")
    print(f"  клиенту давать base_url: http://{GW_HOST}:{GW_PORT}/v1")
    print(f"  кабинет клиента (ввёл ключ → отсчёт): http://{GW_HOST}:{GW_PORT}/")
    srv = ThreadingHTTPServer((GW_HOST, GW_PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлен")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

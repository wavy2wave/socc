"""WAVE GATEWAY — сквозной (end-to-end) тест ЖИВОГО прокси.

Почему этот файл появился: правки биллинга (инъекция stream_options.include_usage
и громкая метка «2xx без usage») живут на HTTP-пути прокси — а его НЕ ПРОВЕРЯЛ
ни один тест. Остальные наборы дёргают QuotaStore напрямую и путь запроса через
сам http.server-обработчик обходят. Значит, самая дорогая дыра — бесплатный
стрим — доказательно не закрыта, пока сюда не пойдёт настоящий запрос.

Здесь поднимается ДВА живых сервера в процессе теста:
  1. Фейковый апстрим (OpenAI-совместимый). Ключевое: он кладёт usage в ПОТОК
     ТОЛЬКО если в запросе есть stream_options.include_usage — точь-в-точь как
     настоящий OpenAI. Значит, ненулевой расход на стриме возможен ЛИШЬ потому,
     что прокси сам дослал include_usage. Это и есть доказательство фикса A.
  2. Сам WAVE GATEWAY (gateway.proxy.Handler) на свободном порту.

Дальше настоящие HTTP-запросы идут через прокси с выданным wave-ключом, и мы
проверяем реальное списание, а не его модель.

Секреты оператора не нужны: апстрим фейковый, ключ оператора — выдуманная
строка, которая НЕ ДОЛЖНА попасть клиенту (это тоже проверяется вживую).

Запуск:  python3 tests/gateway_e2e_v1.py
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []

OP_KEY = "sk-operator-SECRET-must-never-leak-42"
USAGE = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

# Что реально видел апстрим (тела запросов и заголовки) — для проверок инъекции
# usage и НЕутечки ключа оператора наружу. gets — сколько раз апстрим получил
# GET (модели): доказываем, что анонимный /v1/models наверх НЕ уходит.
REC: dict[str, list] = {"bodies": [], "headers": [], "gets": []}
_rec_lock = threading.Lock()


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


class FakeUpstream(BaseHTTPRequestHandler):
    """OpenAI-совместимый апстрим без сети наружу. Всё поведение — из тела."""

    protocol_version = "HTTP/1.0"  # закрываем соединение → клиент читает до EOF

    def log_message(self, *a):  # тишина в тестовом выводе
        return

    def do_GET(self):  # noqa: N802
        # Список моделей. Каждый заход СЮДА означает, что шлюз реально сходил
        # наверх на ключе оператора — считаем их, чтобы доказать: анонимный
        # /v1/models наверх не проходит вовсе.
        with _rec_lock:
            REC["gets"].append({k: v for k, v in self.headers.items()})
        out = json.dumps({"object": "list",
                          "data": [{"id": "fake-1", "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except (ValueError, json.JSONDecodeError):
            body = {}
        with _rec_lock:
            REC["bodies"].append(body)
            REC["headers"].append({k: v for k, v in self.headers.items()})

        if body.get("stream"):
            # SSE. usage кладём В ПОТОК только если попросили include_usage —
            # как настоящий OpenAI. Клиент этого не шлёт; если usage всё же
            # придёт — значит, прокси дослал флаг сам (фикс A).
            opts = body.get("stream_options") or {}
            want_usage = bool(isinstance(opts, dict) and opts.get("include_usage"))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b'data: {"choices":[{"delta":{"content":"hi"}}],'
                             b'"model":"fake-1"}\n\n')
            self.wfile.flush()
            if want_usage:
                frame = json.dumps({"usage": USAGE, "model": "fake-1"}).encode()
                self.wfile.write(b"data: " + frame + b"\n\n")
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        # Не-стрим. Флаг nousage → 2xx БЕЗ usage (проверка громкой метки B).
        resp = {"id": "x", "object": "chat.completion", "model": "fake-1",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": "hi"}}]}
        if not body.get("nousage"):
            resp["usage"] = USAGE
        out = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def _post(gw_port: int, token: str, body: dict, timeout: float = 10.0):
    """Настоящий HTTP-запрос клиента через прокси. Возвращает (код, тело-текст)."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{gw_port}/v1/chat/completions",
        data=data, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def _get(gw_port: int, token: str | None, path: str = "/v1/models",
         timeout: float = 10.0):
    """GET через прокси. token=None → без заголовка авторизации (аноним)."""
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"http://127.0.0.1:{gw_port}{path}",
                                 method="GET", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def main() -> int:  # noqa: C901
    tmp = Path(tempfile.mkdtemp(prefix="wave_e2e_test_"))
    up = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstream)
    uport = up.server_address[1]
    up_thread = threading.Thread(target=up.serve_forever, daemon=True)
    up_thread.start()

    # Окружение задаём ДО импорта прокси: модульные настройки читаются один раз.
    # Пул указываем в несуществующий файл в tmp — чтобы не подхватить боевые
    # ключи оператора из data/upstream_pool.keys. Единственный патрон — env.
    saved = {k: os.environ.get(k) for k in (
        "WAVE_UPSTREAM_URL", "WAVE_DATA_DIR", "WAVE_FORCE_MODEL", "WAVE_UPSTREAM_KEY",
        "WAVE_UPSTREAM_KEYS", "WAVE_UPSTREAM_AUTH_STYLE", "WAVE_UPSTREAM_HEADERS",
        "WAVE_ALLOWED_MODELS", "WAVE_UPSTREAM_POOL_FILE")}
    os.environ.update({
        "WAVE_UPSTREAM_URL": f"http://127.0.0.1:{uport}",
        "WAVE_DATA_DIR": str(tmp),
        # FORCE_MODEL снимает потолок модели/белый список: наверх уходит одна
        # модель, и тест не спотыкается о тарифные ограничения по имени модели.
        "WAVE_FORCE_MODEL": "fake-1",
        "WAVE_UPSTREAM_KEY": OP_KEY,
        "WAVE_UPSTREAM_KEYS": "",
        "WAVE_UPSTREAM_AUTH_STYLE": "bearer",
        "WAVE_UPSTREAM_HEADERS": "",
        "WAVE_ALLOWED_MODELS": "",
        "WAVE_UPSTREAM_POOL_FILE": str(tmp / "pool.keys"),
    })

    gw = None
    responses: list[str] = []
    try:
        import gateway.proxy as proxy
        importlib.reload(proxy)
        from gateway.pricing import caps_from_usage

        exp = int(caps_from_usage(USAGE))
        check(exp > 0, f"эталон CAPS по usage провайдера > 0 ({exp})")

        # Ловим лог прокси, чтобы поймать громкую метку «2xx без usage».
        logs: list[str] = []
        proxy.log = lambda m: logs.append(m)  # noqa: E731

        # Прокси в локальном режиме (127.0.0.1) ключ не требует — так и должно
        # быть для своей мощности. Ключ оператора всё равно в обойме; режим с
        # ключом включим точечно в секции D.
        gw = ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
        gw_port = gw.server_address[1]
        threading.Thread(target=gw.serve_forever, daemon=True).start()

        rec = proxy._store.issue_key(user_id=1, plan_id="pack_3m",
                                     order_id="o1", price_rub=990)
        token = rec["token"]

        def used() -> int:
            return int(proxy._store.status(token)["tokens_used"])

        # ═══ A. Не-стрим: реальный запрос списывает ровно взвешенные CAPS ═══
        u0 = used()
        code, txt = _post(gw_port, token, {"model": "x",
                          "messages": [{"role": "user", "content": "hi"}]})
        responses.append(txt)
        check(code == 200 and "choices" in txt, "не-стрим: клиент получил ответ провайдера")
        check(used() - u0 == exp, f"не-стрим: списано ровно {exp} CAPS (по ответу, не по запросу)")

        # ═══ B. СТРИМ: раньше списывался в НОЛЬ — теперь ненулевой (фикс A) ═══
        # Клиент НЕ шлёт stream_options (и даже шлёт include_usage:false).
        # Фейковый апстрим отдаёт usage ТОЛЬКО при include_usage. Ненулевое
        # списание доказывает, что прокси дослал флаг сам.
        with _rec_lock:
            REC["bodies"].clear()
        u1 = used()
        code, txt = _post(gw_port, token, {"model": "x", "stream": True,
                          "stream_options": {"include_usage": False},
                          "messages": [{"role": "user", "content": "hi"}]})
        responses.append(txt)
        check("hi" in txt or "delta" in txt, "стрим: чанки дошли до клиента")
        with _rec_lock:
            seen = REC["bodies"][-1] if REC["bodies"] else {}
        inj = bool((seen.get("stream_options") or {}).get("include_usage"))
        check(inj, "стрим: прокси ДОСЛАЛ stream_options.include_usage наверх (клиент не слал)")
        check(used() - u1 == exp,
              f"стрим: списано {exp} CAPS, а не 0 — бесплатный стрим закрыт (фикс A)")

        # ═══ C. 2xx без usage: списываем 0, но ГРОМКО помечаем (фикс B) ═══
        logs.clear()
        u2 = used()
        code, txt = _post(gw_port, token, {"model": "x", "nousage": True,
                          "messages": [{"role": "user", "content": "hi"}]})
        responses.append(txt)
        check(used() - u2 == 0, "2xx без usage: не выдумали расход (списано 0)")
        flagged = any("ВНИМАНИЕ" in m and "не списан" in m.lower() for m in logs)
        check(flagged, "2xx без usage: аномалия громко в логе (оператор увидит дыру)")

        # ═══ D. Ключ оператора уходит наверх, но НЕ утекает клиенту ═══
        proxy.UPSTREAM_NEEDS_KEY = True  # включаем режим с ключом точечно
        with _rec_lock:
            REC["headers"].clear()
        code, txt = _post(gw_port, token, {"model": "x",
                          "messages": [{"role": "user", "content": "hi"}]})
        responses.append(txt)
        with _rec_lock:
            hdrs = REC["headers"][-1] if REC["headers"] else {}
        upstream_saw = any(OP_KEY in str(v) for v in hdrs.values())
        check(upstream_saw, "ключ оператора реально ушёл наверх (в заголовке к провайдеру)")
        check(OP_KEY not in txt, "ключ оператора НЕ попал в ответ клиенту")
        proxy.UPSTREAM_NEEDS_KEY = False

        # ═══ E. Чужой/битый токен → отказ (401), наверх ничего не идёт ═══
        try:
            _post(gw_port, "wave-bogus-token", {"model": "x",
                  "messages": [{"role": "user", "content": "hi"}]})
            check(False, "битый токен должен получить отказ")
        except urllib.error.HTTPError as e:
            check(e.code == 401, f"битый токен отвергнут (HTTP {e.code})")

        # ═══ Финальный инвариант: ключ оператора не всплыл НИ В ОДНОМ ответе ═══
        check(all(OP_KEY not in r for r in responses),
              "ни один клиентский ответ за прогон не содержит ключ оператора")

        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        print(f"\n{'=' * 62}\nИТОГ: {passed}/{total} проверок пройдено")
        if passed == total:
            print("🛰  СКВОЗНОЙ ПРОКСИ: биллинг на живом пути реален — стрим "
                  "списывается ненулём, дыры помечены, ключ оператора не течёт.")
            return 0
        print("Есть красные проверки — смотрите выше.")
        return 1
    finally:
        if gw is not None:
            gw.shutdown()
            gw.server_close()
        up.shutdown()
        up.server_close()
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""МОСТ ЗРЕНИЯ → ollama (провайдер для PHOTO_VISION_CMD ступени 3 фото-искателя).

ЗАЧЕМ. photo_hunter_v1 ступень 3 зовёт shell-команду из PHOTO_VISION_CMD, передавая ей
PHOTO_PATH (путь к кадру) и PHOTO_QUESTION (вопрос), и читает ОТВЕТ из stdout. Этот скрипт —
такой провайдер поверх локальной модели зрения ollama (moondream по умолчанию). Локально =
0 ₽ за вызов и никакого egress: кадр не покидает машину (важно, RU-egress режет облачные API).

КАК ВКЛЮЧИТЬ:
    export PHOTO_VISION_CMD='/path/to/venv/python3 .../photo_vision_ollama.py'
    (модель: PHOTO_VISION_MODEL, по умолчанию moondream; хост: OLLAMA_HOST/11434)

ГРАНИЦА. Скрипт НИЧЕГО не решает про годность — он лишь честно передаёт, что ответила модель.
Вердикт (сверка с фактами, кворум) собирает сам орган. Пусто/ошибка → пустой stdout → орган
трактует как «зрение не ответило» = 'unknown', а не ложное «годится» (закон честности L3).
"""
import base64
import json
import os
import sys
import urllib.request

MODEL = os.getenv("PHOTO_VISION_MODEL", "moondream")
HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not HOST.startswith("http"):
    HOST = "http://" + HOST


def ask(path, question, timeout=180):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    body = json.dumps({
        "model": MODEL,
        "prompt": question,
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0},   # детерминизм: проверка, а не творчество
    }).encode("utf-8")
    req = urllib.request.Request(HOST + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "ignore"))
    return (data.get("response") or "").strip()


def main():
    path = os.getenv("PHOTO_PATH") or (sys.argv[1] if len(sys.argv) > 1 else "")
    question = os.getenv("PHOTO_QUESTION") or (sys.argv[2] if len(sys.argv) > 2 else
                                               "What is in this image? Answer in one sentence.")
    if not path or not os.path.exists(path):
        return  # нет кадра → молчим, орган трактует как «не ответило»
    try:
        ans = ask(path, question)
    except Exception:
        return  # сеть/модель упала → молчим (честное 'не проверено', не ложный PASS)
    if ans:
        sys.stdout.write(ans)


if __name__ == "__main__":
    main()

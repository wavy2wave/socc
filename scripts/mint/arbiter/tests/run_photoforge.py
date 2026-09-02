#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHOTO-FORGE ПРИЁМКА — ФОТО-КУЗНИЦА (стадия DUB, Nano Banana / OpenRouter): сухо, 0₽, без сети/ключа.

Пара к ФОТО-ИСКАТЕЛЮ: кузница КУЁТ уникальный кадр, хантер его ПРИНИМАЕТ. Все тесты
оффлайн-детерминированы: единственный шов реальной сети (photo_forge._http_call, под ретрай-петлёй
_request) подменяется monkeypatch; реальный ключ OpenRouter НЕ нужен и НЕ используется; наружу не
уходит ничего (0₽, dry по умолчанию). Проверяем именно 5 законов надёжности органа.

  F1  no_key_honest        — ключа нет → creds_present=False, capabilities.key=False, без падения.
  F2  auth_401_is_keys     — 401 → ForgeHTTPError (ключи, не код), без ретрай-шторма (1 вызов).
  F3  transient_retry      — 429 дважды → ретрай и успех (устойчивость, не демон).
  F4  dry_gate_no_send     — dry: payload собран, наружу НИЧЕГО (0 сетевых вызовов), sent=False.
  F5  request_shape        — build_request: modalities=[image,text], модель, edit несёт исходник.
  F6  prompt_watermark     — build_prompt: для edit снятие чужого знака ОБЯЗАТЕЛЬНО, есть верность.
  F7  extract_image_ok     — картинка из choices[0].message.images[].image_url.url (base64) достаётся.
  F8  extract_image_miss   — нет картинки в теле → (None,None): 200 ≠ успех.
  F9  decode_data_url      — data-url и голый base64 декодятся; мусор → (None,None).
  F10 magic_is_image       — сигнатуры PNG/JPEG/WebP → да; мусор → нет (стдлиб, без PIL).
  F11 scan_watermark       — чужой домен/оптовая фраза ловится; чистый текст → пусто.
  F12 assess_uniqueness    — далёкий pHash → уникален; близкий → склейка; нет донора → «не знаю».
  F13 verify_non_image     — не картинка → tier=rejected, image_ok=False.
  F14 verify_tiers         — знак снят+уникален→verified; чужой знак→rejected; не проверено→needs_human.
  F15 rights_boundary      — generate=наши пиксели (clean); edit=производное (флаг прав, решает оператор).
  F16 live_writes_ledger   — фейковый живой кадр: ok, файл сохранён, событие расхода в леджер (usage).

  --- второй провайдер той же Nano Banana: Google AI Studio (родной generateContent) ---
  F17 google_request_shape — build_request(provider=google): contents/parts/responseModalities,
                             модели в теле НЕТ, edit несёт inline_data с ГОЛЫМ base64 + mime_type.
  F18 google_extract_image — картинка из candidates[].content.parts[].inlineData.data (не в [0]).
  F19 google_headers_ep    — заголовок x-goog-api-key (не Bearer), путь /models/<slug>:generateContent.
  F20 provider_autodetect  — google-ключ→google; только openrouter-ключ→openrouter; форс перебивает.
  F21 google_dry_preview   — dry при провайдере google: наружу 0, sent=False, форма превью google.
  F22 google_finish_reason — на 200 без картинки честно достаём finishReason / prompt_blocked.

  --- герметичность сухого гейта ---
  F23 dry_edit_no_fetch     — dry+edit НЕ грузит донора и НЕ ходит в сеть (0 вызовов), но превью
                             честно помечает has_source_image=True (кадр будет приложен живьём).

Приёмка не зовёт реальную сеть и не тратит ₽. Реальный кадр — только по отмашке (dry=False).
Тесты пути OpenRouter пинят PHOTO_FORGE_PROVIDER=openrouter → детерминизм даже если у оператора
уже вставлен google-ключ AIza… в mint/.env (обратная совместимость приёмки).
"""
import base64
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import photo_forge_v1 as pf     # noqa: E402


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


def _resp(status_code, payload=None, text=""):
    """Мини-ответ = реальный pf._Resp (status_code/json()/text) — для подмены pf._http_call."""
    return pf._Resp(status_code, payload, text)


# Валидная PNG-сигнатура + добивка до >64 байт (порог _magic_is_image).
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 120


def _png_data_url():
    return "data:image/png;base64," + base64.b64encode(_PNG).decode("ascii")


class _Patch:
    """monkeypatch шва сети pf._http_call + фейковый ключ; откат гарантирован.

    _request зовёт _headers() (требует ключ) ДО _http_call — потому сетевым тестам нужен фейк-ключ.
    Фейковая сеть его игнорирует. F1 (без ключа) сеть НЕ патчит и остаётся честным.
    Провайдер пиним на openrouter: форма запроса/ответа детерминирована даже если у оператора уже
    вставлен google-ключ AIza… (иначе _provider() ушёл бы в google и сломал форму приёмки).
    """
    def __init__(self, http_call=None):
        self._http = http_call
        self._save = {}

    def __enter__(self):
        if self._http is not None:
            self._save["OPENROUTER_API_KEY"] = os.environ.get("OPENROUTER_API_KEY")
            os.environ["OPENROUTER_API_KEY"] = "TEST-KEY"
            self._save["PHOTO_FORGE_PROVIDER"] = os.environ.get("PHOTO_FORGE_PROVIDER")
            os.environ["PHOTO_FORGE_PROVIDER"] = "openrouter"
            self._save["_http_call"] = pf._http_call
            pf._http_call = self._http
        return self

    def __exit__(self, *exc):
        if "_http_call" in self._save:
            pf._http_call = self._save["_http_call"]
        for k in ("OPENROUTER_API_KEY", "PHOTO_FORGE_PROVIDER"):
            if k in self._save:
                val = self._save[k]
                if val is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = val
        return False


class _EnvForce:
    """Детерминированно выставить/снять env-переменные и заморозить _ENV_TRIED (чтобы _ensure_env
    не перечитал .env поверх). value=None → переменную удалить. Откат гарантирован."""
    def __init__(self, **kv):
        self._kv = kv
        self._save = {}
        self._tried = None

    def __enter__(self):
        self._tried = pf._ENV_TRIED
        pf._ENV_TRIED = True
        for k, v in self._kv.items():
            self._save[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, old in self._save.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
        pf._ENV_TRIED = self._tried
        return False


class _StubHunter:
    """Заглушка photo_hunter под verify_output/assess_uniqueness: детерминированные ступени."""
    def __init__(self, iron_ok=True, phash="a" * 16, letters_ok=True, ham=20):
        self._iron_ok, self._phash, self._letters_ok, self._ham = iron_ok, phash, letters_ok, ham

    def load_sources(self):
        return {"criteria": {}, "watermark_markers": {"domains": ["cargo-avto"], "phrases": ["опт"]}}

    def stage1_iron(self, raw, ctype, crit):
        return self._iron_ok, {"phash": self._phash, "why": "ok" if self._iron_ok else "мелкая"}

    def stage2_letters(self, raw, markers):
        return self._letters_ok, {"why": "чисто" if self._letters_ok else "чужой текст: cargo-avto"}

    def hamming(self, a, b):
        return self._ham


# ── F1: ключа нет → честно, без падения ──
def t1_no_key_honest():
    keys = ("OPENROUTER_API_KEY", "OPENAI_API_KEY",
            "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_AI_STUDIO_KEY",
            "NEUROAPI_API_KEY", "RU_OPENAI_API_KEY",
            "FUSIONBRAIN_API_KEY", "FUSIONBRAIN_SECRET_KEY")
    save = {k: os.environ.get(k) for k in keys}
    tried = pf._ENV_TRIED
    try:
        for k in save:
            os.environ.pop(k, None)                # снимаем ключ ЛЮБОГО провайдера
        pf._ENV_TRIED = True                       # не даём _ensure_env перезагрузить .env
        creds = pf.creds_present()
        caps = pf.capabilities()
        return creds is False and caps["key"] is False, f"creds={creds} caps.key={caps['key']}"
    finally:
        pf._ENV_TRIED = tried
        for k, v in save.items():
            if v is not None:
                os.environ[k] = v


# ── F2: 401 → ForgeHTTPError (ключи, не код), без ретрай-шторма ──
def t2_auth_401_is_keys():
    calls = []

    def _http(method, url, headers, body, timeout):
        calls.append(url)
        return _resp(401, {"error": {"message": "no auth"}})

    with _Patch(http_call=_http):
        try:
            pf._request("POST", pf.CHAT_PATH, body={"x": 1})
            return False, "401 не поднял ForgeHTTPError"
        except pf.ForgeHTTPError as e:
            return e.status == 401 and len(calls) == 1, f"ForgeHTTPError 401, вызовов={len(calls)}"


# ── F3: 429 дважды → ретрай и успех ──
def t3_transient_retry():
    calls = []

    def _http(method, url, headers, body, timeout):
        calls.append(url)
        if len(calls) < 3:
            return _resp(429, {"error": {"message": "rate"}})
        return _resp(200, {"ok": 1})

    with _Patch(http_call=_http):
        out = pf._request("POST", pf.CHAT_PATH, body={"x": 1})
        return len(calls) == 3 and out == {"ok": 1}, f"ретраев={len(calls) - 1}, успех"


# ── F4: сухой гейт — payload собран, но наружу НИЧЕГО ──
def t4_dry_gate_no_send():
    calls = []

    def _http(method, url, headers, body, timeout):
        calls.append(url)                          # dry сюда попадать НЕ должен
        return _resp(200, {})

    with _Patch(http_call=_http):
        res = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=True)
    ok = (res["dry"] is True and res.get("sent") is False and len(calls) == 0
          and res["request"]["modalities"] == ["image", "text"]
          and res["est_cost_usd"] == pf.EST_USD_PER_IMAGE)
    return ok, f"dry={res['dry']} sent={res.get('sent')} сетевых={len(calls)}"


# ── F5: build_request — форма запроса (пиним openrouter для детерминизма) ──
def t5_request_shape():
    gen = pf.build_request("нарисуй", None, None, provider="openrouter")
    edt = pf.build_request("переработай", "QUJD", "some/model", provider="openrouter")
    gen_txt = gen["messages"][0]["content"]
    edt_txt = edt["messages"][0]["content"]
    ok = (gen["modalities"] == ["image", "text"]
          and gen["model"] == pf.DEFAULT_MODEL
          and len(gen_txt) == 1 and gen_txt[0]["type"] == "text"          # generate: без исходника
          and edt["model"] == "some/model"
          and any(p["type"] == "image_url" for p in edt_txt)             # edit: несёт исходный кадр
          and edt_txt[1]["image_url"]["url"].startswith("data:image/png;base64,QUJD"))
    return ok, f"gen_parts={len(gen_txt)} edit_has_img={any(p['type'] == 'image_url' for p in edt_txt)}"


# ── F6: build_prompt — снятие чужого знака для edit обязательно ──
def t6_prompt_watermark():
    # ops без watermark_own — орган ОБЯЗАН добавить снятие знака сам (главный риск).
    p_edit = pf.build_prompt(facts={"ширина": "1.2 м"}, ops=["crop_aspect_4x5"], mode="edit")
    p_gen = pf.build_prompt(facts={"ширина": "1.2 м"}, ops=["crop_aspect_4x5"], mode="generate")
    ok = ("водян" in p_edit and "Создай" in p_gen and "Никакого текста" in p_edit
          and "1.2 м" in p_edit)
    return ok, f"edit_снимает_знак={'водян' in p_edit} generate_head={'Создай' in p_gen}"


# ── F7: extract_image достаёт картинку из тела ──
def t7_extract_image_ok():
    resp = {"choices": [{"message": {"images": [{"image_url": {"url": _png_data_url()}}]}}]}
    mime, raw = pf.extract_image(resp)
    return raw == _PNG and mime == "image/png", f"mime={mime} bytes={len(raw) if raw else 0}"


# ── F8: нет картинки → (None,None): 200 ≠ успех ──
def t8_extract_image_miss():
    resp = {"choices": [{"message": {"content": "извини, картинку не сделал"}}]}
    mime, raw = pf.extract_image(resp)
    return mime is None and raw is None, f"mime={mime} raw={raw}"


# ── F9: _decode_data_url — data-url и голый base64 ──
def t9_decode_data_url():
    m1, r1 = pf._decode_data_url(_png_data_url())
    m2, r2 = pf._decode_data_url(base64.b64encode(_PNG).decode("ascii"))   # голый base64
    m3, r3 = pf._decode_data_url("не-урл-и-не-base64-!!!@@@")
    ok = (r1 == _PNG and m1 == "image/png" and r2 == _PNG and r3 is None)
    return ok, f"data_url={'ok' if r1 else 'нет'} bare={'ok' if r2 else 'нет'} junk={r3}"


# ── F10: _magic_is_image — сигнатуры ──
def t10_magic_is_image():
    png = pf._magic_is_image(_PNG)
    jpg = pf._magic_is_image(b"\xff\xd8\xff\xe0" + b"\x00" * 80)
    junk = pf._magic_is_image(b"this is plainly text, not an image at all, no signature bytes here!!")
    return png and jpg and not junk, f"png={png} jpg={jpg} junk={junk}"


# ── F11: scan_watermark — чужой домен/фраза ──
def t11_scan_watermark():
    markers = {"domains": ["cargo-avto", "ozon"], "phrases": ["опт", "звоните"]}
    hit = pf.scan_watermark("Плёнка cargo-avto.ru опт дёшево", markers)
    clean = pf.scan_watermark("Воздушно-пузырьковая плёнка в рулоне", markers)
    return ("cargo-avto" in hit and "опт" in hit and clean == []), f"hit={hit} clean={clean}"


# ── F12: assess_uniqueness — склейка/уникальность/«не знаю» ──
def t12_assess_uniqueness():
    save = pf._hunter
    try:
        pf._hunter = lambda: _StubHunter(ham=20)          # далеко от донора
        far = pf.assess_uniqueness("a" * 16, ["b" * 16])
        pf._hunter = lambda: _StubHunter(ham=3)           # слишком близко → склейка
        near = pf.assess_uniqueness("a" * 16, ["b" * 16])
        none = pf.assess_uniqueness("a" * 16, [])          # донора нет → честно «не знаю»
        ok = (far["distinct"] is True and near["distinct"] is False
              and none["distinct"] is None and none["checked"] is False)
        return ok, f"far={far['distinct']} near={near['distinct']} no_donor={none['distinct']}"
    finally:
        pf._hunter = save


# ── F13: не картинка → rejected ──
def t13_verify_non_image():
    out = pf.verify_output(b"this is not an image but a plain-text placeholder of enough length!!", facts={})
    return out["tier"] == "rejected" and out["image_ok"] is False, f"tier={out['tier']}"


# ── F14: verify_output — три тира ──
def t14_verify_tiers():
    save = pf._hunter
    try:
        pf._hunter = lambda: _StubHunter(letters_ok=True, ham=20)     # знак снят + уникален
        verified = pf.verify_output(_PNG, facts={}, donor_phashes=["b" * 16])
        pf._hunter = lambda: _StubHunter(letters_ok=False)            # чужой знак найден
        rejected = pf.verify_output(_PNG, facts={}, donor_phashes=["b" * 16])
        pf._hunter = lambda: None                                     # проверить нечем → честно
        needs = pf.verify_output(_PNG, facts={}, donor_phashes=["b" * 16])
        ok = (verified["tier"] == "verified" and rejected["tier"] == "rejected"
              and needs["tier"] == "ok_needs_human")
        return ok, f"verified={verified['tier']} watermark={rejected['tier']} gap={needs['tier']}"
    finally:
        pf._hunter = save


# ── F15: граница прав ──
def t15_rights_boundary():
    g = pf.rights_note("generate")
    e = pf.rights_note("edit")
    ok = (g["clean"] is True and g["level"] == "own_pixels"
          and e["clean"] is False and e["level"] == "derivative")
    return ok, f"generate_clean={g['clean']} edit_clean={e['clean']}"


# ── F16: живой кадр (фейк-сеть) → ok + файл + событие расхода в леджер ──
def t16_live_writes_ledger():
    tmp = Path(tempfile.mkdtemp(prefix="forge_test_"))
    save_state, save_ledger, save_hunter = pf.STATE, pf.LEDGER, pf._hunter

    def _http(method, url, headers, body, timeout):
        return _resp(200, {"choices": [{"message": {"images": [{"image_url": {"url": _png_data_url()}}]}}],
                           "usage": {"cost": 0.039}})

    try:
        pf.STATE = tmp
        pf.LEDGER = tmp / "photoforge_ledger.json"
        pf._hunter = lambda: None                  # приёмка честно вернёт ok_needs_human
        with _Patch(http_call=_http):
            res = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=False,
                           out_dir=str(tmp), tag="test")
        saved_ok = bool(res.get("path")) and Path(res["path"]).exists()
        ledger = json.loads(pf.LEDGER.read_text(encoding="utf-8")) if pf.LEDGER.exists() else []
        ok = (res.get("ok") is True and res.get("sent") is True
              and res.get("tier") == "ok_needs_human"
              and saved_ok and len(ledger) == 1
              and ledger[0]["cost_source"] == "usage" and ledger[0]["cost_usd"] == 0.039)
        return ok, (f"ok={res.get('ok')} tier={res.get('tier')} файл={'есть' if saved_ok else 'НЕТ'} "
                    f"леджер={len(ledger)} cost={ledger[0]['cost_usd'] if ledger else '?'}")
    finally:
        pf.STATE, pf.LEDGER, pf._hunter = save_state, save_ledger, save_hunter
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


# ── F17: build_request(provider=google) — родная форма generateContent ──
def t17_google_request_shape():
    gen = pf.build_request("нарисуй", None, None, provider="google")
    edt = pf.build_request("переработай", "QUJD", None, provider="google")
    parts_g = gen["contents"][0]["parts"]
    parts_e = edt["contents"][0]["parts"]
    ok = (gen["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]
          and "model" not in gen and "messages" not in gen                # модель у Google — в URL, НЕ в теле
          and len(parts_g) == 1 and parts_g[0]["text"] == "нарисуй"       # generate: только текст
          and parts_e[1]["inline_data"]["data"] == "QUJD"                 # edit: ГОЛЫЙ base64 (без data:)
          and parts_e[1]["inline_data"]["mime_type"].startswith("image/"))
    return ok, (f"modalities={gen['generationConfig']['responseModalities']} "
                f"model_in_body={'model' in gen} edit_inline={'inline_data' in parts_e[1]}")


# ── F18: extract_image из candidates[].content.parts[].inlineData (картинка НЕ в [0]) ──
def t18_google_extract_image():
    b64 = base64.b64encode(_PNG).decode("ascii")
    resp = {"candidates": [{"content": {"parts": [
        {"text": "вот твоя карточка"},
        {"inlineData": {"mimeType": "image/png", "data": b64}}]}}]}
    mime, raw = pf.extract_image(resp)
    return raw == _PNG and mime == "image/png", f"mime={mime} bytes={len(raw) if raw else 0}"


# ── F19: заголовок x-goog-api-key (не Bearer) + путь :generateContent ──
def t19_google_headers_ep():
    with _EnvForce(PHOTO_FORGE_PROVIDER="google", GEMINI_API_KEY="AIza-TEST",
                   GOOGLE_API_KEY=None, GOOGLE_AI_STUDIO_KEY=None):
        h = pf._headers()
        ep = pf._endpoint_path(pf.GOOGLE_DEFAULT_MODEL)
    ok = (h.get("x-goog-api-key") == "AIza-TEST" and "Authorization" not in h
          and ep == "/models/%s:generateContent" % pf.GOOGLE_DEFAULT_MODEL)
    return ok, f"x-goog-api-key={'x-goog-api-key' in h} bearer_absent={'Authorization' not in h} ep={ep}"


# ── F20: авто-выбор провайдера по наличию ключа + форс перебивает ──
def t20_provider_autodetect():
    with _EnvForce(PHOTO_FORGE_PROVIDER=None, GEMINI_API_KEY="AIza-TEST", GOOGLE_API_KEY=None,
                   GOOGLE_AI_STUDIO_KEY=None, OPENROUTER_API_KEY=None, OPENAI_API_KEY=None):
        p_google = pf._provider()
    with _EnvForce(PHOTO_FORGE_PROVIDER=None, GEMINI_API_KEY=None, GOOGLE_API_KEY=None,
                   GOOGLE_AI_STUDIO_KEY=None, OPENROUTER_API_KEY="sk-test", OPENAI_API_KEY=None,
                   NEUROAPI_API_KEY=None, RU_OPENAI_API_KEY=None,
                   FUSIONBRAIN_API_KEY=None, FUSIONBRAIN_SECRET_KEY=None):
        p_or = pf._provider()
    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", GEMINI_API_KEY="AIza-TEST"):
        p_forced = pf._provider()
    ok = (p_google == "google" and p_or == "openrouter" and p_forced == "openrouter")
    return ok, f"google_key→{p_google} or_key→{p_or} forced→{p_forced}"


# ── F21: dry при провайдере google — наружу 0, форма превью google ──
def t21_google_dry_preview():
    with _EnvForce(PHOTO_FORGE_PROVIDER="google", GEMINI_API_KEY="AIza-TEST",
                   GOOGLE_API_KEY=None, GOOGLE_AI_STUDIO_KEY=None):
        res = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=True)
    r = res.get("request", {})
    ok = (res["dry"] is True and res.get("sent") is False
          and res.get("provider") == "google" and r.get("provider") == "google"
          and r.get("responseModalities") == ["TEXT", "IMAGE"]
          and res["est_cost_usd"] == pf.EST_USD_PER_IMAGE)
    return ok, f"provider={res.get('provider')} sent={res.get('sent')} preview={r.get('provider')}"


# ── F22: 200 без картинки → честный finishReason / prompt_blocked ──
def t22_google_finish_reason():
    r1 = pf._finish_reason({"candidates": [{"finishReason": "IMAGE_SAFETY"}]})
    r2 = pf._finish_reason({"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}})
    r3 = pf._finish_reason({"candidates": [{"content": {"parts": []}}]})
    ok = (r1 == "IMAGE_SAFETY" and r2 == "prompt_blocked:PROHIBITED_CONTENT" and r3 is None)
    return ok, f"safety={r1} blocked={r2} none={r3}"


# ── F23: dry+edit ГЕРМЕТИЧЕН — донор НЕ загружается (0 сети), но превью помечает «кадр приложен» ──
def t23_dry_edit_no_fetch():
    fetched = []
    net = []
    save_load = pf._load_source

    def _spy_load(source):
        fetched.append(source)                     # dry НЕ должен сюда заходить
        return "QUJD", b"ABC"

    def _http(method, url, headers, body, timeout):
        net.append(url)                            # и в сеть тоже НЕ должен
        return _resp(200, {})

    try:
        pf._load_source = _spy_load
        with _Patch(http_call=_http):              # пинит openrouter + фейк-ключ
            res = pf.forge(mode="edit", source="https://site/donor.jpg",
                           facts={"вид": "плёнка"}, dry=True)
        r = res.get("request", {})
        ok = (res["dry"] is True and res.get("sent") is False
              and len(fetched) == 0 and len(net) == 0        # герметично: ни загрузки донора, ни сети
              and r.get("has_source_image") is True)          # но форма честно: кадр будет приложен
        return ok, (f"dry={res['dry']} загрузок_донора={len(fetched)} сети={len(net)} "
                    f"has_img={r.get('has_source_image')}")
    finally:
        pf._load_source = save_load


# ── F24: бренд-стиль ATLAS EDGE в head промпта (единый почерк всех карточек) ──
def t24_brand_lock():
    # По умолчанию бренд ВКЛ (brand=None) для обоих режимов; head несёт белый фон #FFFFFF и 4:5.
    p_gen = pf.build_prompt(facts={"вид": "плёнка"}, ops=["crop_aspect_4x5"], mode="generate")
    p_edit = pf.build_prompt(facts={"вид": "плёнка"}, ops=["crop_aspect_4x5"], mode="edit")
    on = ("#FFFFFF" in p_gen and "4:5" in p_gen and "#FFFFFF" in p_edit)
    # brand=False → точный старый текст без бренд-контракта (обратная совместимость).
    p_off = pf.build_prompt(facts={"вид": "плёнка"}, ops=["crop_aspect_4x5"], mode="generate", brand=False)
    off = ("#FFFFFF" not in p_off)
    # Стиль в HEAD (до «Требования:») → виден в _preview (режет до 180 символов).
    head_pos = p_gen.find("#FFFFFF")
    req_pos = p_gen.find("Требования:")
    in_head = 0 <= head_pos < req_pos
    ok = on and off and in_head
    return ok, f"brand_on={on} brand_off_compat={off} in_head={in_head}"


# ── F37: L3a — директива масштаба/заполнения кадра (фикс «короб мельче чем 600×400») ──
def t37_brand_fill_directive():
    # Дефолт (brand=None) несёт «крупно, занимает почти весь кадр» в HEAD — товар заполняет
    # кадр, а не висит крошкой по центру. Раньше промпт задавал только центр+4:5 (мелкий товар
    # удовлетворял ВСЕ инструкции). Это корень жалобы оператора — чиним генерацией, не порогом.
    p_gen = pf.build_prompt(facts={"вид": "коробка"}, ops=["crop_aspect_4x5"], mode="generate")
    p_edit = pf.build_prompt(facts={"вид": "коробка"}, ops=["crop_aspect_4x5"], mode="edit")
    FILL = "занимает почти весь кадр"
    on = (FILL in p_gen and "КРУПНО" in p_gen and FILL in p_edit)
    # brand=False → старый текст без директивы заполнения (обратная совместимость F1-F23).
    p_off = pf.build_prompt(facts={"вид": "коробка"}, ops=["crop_aspect_4x5"], mode="generate", brand=False)
    off = (FILL not in p_off)
    # Директива в HEAD (до «Требования:») → видна модели и в _preview (режет хвост до 180).
    fill_pos = p_gen.find(FILL)
    req_pos = p_gen.find("Требования:")
    in_head = 0 <= fill_pos < req_pos
    ok = on and off and in_head
    return ok, f"fill_on={on} off_compat={off} in_head={in_head}"


# ── F38: subject_metrics — «товар мельче чем есть» + центр + присутствие (реальные пиксели) ──
def t38_subject_metrics():
    # Синтетика через PIL (venv). Без PIL орган ЧЕСТНО отдаёт None — тогда пиннем именно контракт None.
    try:
        import io as _io
        from PIL import Image, ImageDraw
    except Exception:
        got = pf.subject_metrics(_PNG)                       # _PNG не декодится → все None
        return got["fill"] is None and got["present"] is None, f"no_pil→{got}"

    def _frame(bw, bh, dx=0, dy=0):
        im = Image.new("RGB", (1024, 1280), (255, 255, 255))
        if bw and bh:
            d = ImageDraw.Draw(im)
            x = (1024 - bw) // 2 + dx
            y = (1280 - bh) // 2 + dy
            d.rectangle([x, y, x + bw, y + bh], fill=(150, 110, 70))
        b = _io.BytesIO(); im.save(b, "PNG"); return b.getvalue()

    small = pf.subject_metrics(_frame(90, 110))
    if small["fill"] is None:                                # PIL-путь ОРГАНА мёртв → честный None-контракт
        return small["present"] is None, f"organ_pil_dead→{small}"
    big = pf.subject_metrics(_frame(820, 1040))
    off = pf.subject_metrics(_frame(820, 1040, dx=300))
    blank = pf.subject_metrics(_frame(0, 0))                 # пустой белый кадр
    tiny_ok = small["fill"] < 0.05 and small["present"] is True
    big_ok = big["fill"] > 0.4 and big["off_center"] < 0.05
    sep = big["fill"] > small["fill"] * 8                    # чистое разделение крошка↔крупно
    off_ok = off["off_center"] > 0.1                         # смещение поймано
    blank_ok = blank["present"] is False and blank["off_center"] is None
    ok = tiny_ok and big_ok and sep and off_ok and blank_ok
    return ok, (f"small={small['fill']} big={big['fill']} off={off['off_center']} "
                f"blank_present={blank['present']}")


# ── F39: verify_canon L1 — subject всегда в out; демоция ТОЛЬКО при заданном пороге (дефолт байт-в-байт) ──
def t39_verify_canon_subject_gate():
    save_wb, save_ar, save_hunter, save_sm = pf.is_white_bg, pf._aspect_ok, pf._hunter, pf.subject_metrics
    try:
        pf._hunter = lambda: _StubHunter(letters_ok=True, ham=20)      # база verify_output = verified
        pf.is_white_bg = lambda raw, **k: True
        pf._aspect_ok = lambda raw, target="4:5", **k: True
        # (a) пороги НЕ заданы → тир как раньше (verified), но ключ subject присутствует всегда.
        base = pf.verify_canon(_PNG, facts={}, donor_phashes=["b" * 16])
        has_key = "subject" in base and base["subject"]["fill"] is None   # _PNG не декодится → None-метрика
        unset_stays = base["tier"] == "verified"
        # None-метрику НЕ караем: даже жёсткие пороги не роняют «не знаю».
        none_safe = pf.verify_canon(_PNG, facts={}, donor_phashes=["b" * 16],
                                    min_fill=0.9, max_off=0.01, require_subject=True)["tier"] == "verified"
        # (b) реальная метрика (монкипатч subject_metrics): низкий fill + порог → off_canon; высокий → verified.
        pf.subject_metrics = lambda raw, **k: {"fill": 0.01, "off_center": 0.0, "present": True}
        demoted = pf.verify_canon(_PNG, facts={}, donor_phashes=["b" * 16], min_fill=0.30)["tier"]
        pf.subject_metrics = lambda raw, **k: {"fill": 0.66, "off_center": 0.0, "present": True}
        kept = pf.verify_canon(_PNG, facts={}, donor_phashes=["b" * 16], min_fill=0.30)["tier"]
        pf.subject_metrics = lambda raw, **k: {"fill": 0.66, "off_center": 0.30, "present": True}
        off_demoted = pf.verify_canon(_PNG, facts={}, donor_phashes=["b" * 16], max_off=0.15)["tier"]
        ok = (has_key and unset_stays and none_safe and demoted == "off_canon"
              and kept == "verified" and off_demoted == "off_canon")
        return ok, (f"key={has_key} unset={unset_stays} none_safe={none_safe} "
                    f"demoted={demoted} kept={kept} off_demoted={off_demoted}")
    finally:
        pf.is_white_bg, pf._aspect_ok, pf._hunter, pf.subject_metrics = save_wb, save_ar, save_hunter, save_sm


# ── F25: verify_canon отбивает кадр вне фирменного стиля (не-белый фон / не 4:5) ──
def t25_verify_canon_rejects():
    save_wb, save_ar, save_hunter = pf.is_white_bg, pf._aspect_ok, pf._hunter
    try:
        pf._hunter = lambda: _StubHunter(letters_ok=True, ham=20)   # база: verified по verify_output
        # canon соблюдён → остаётся verified
        pf.is_white_bg = lambda raw, **k: True
        pf._aspect_ok = lambda raw, target="4:5", **k: True
        good = pf.verify_canon(_PNG, facts={}, donor_phashes=["b" * 16])
        # фон не белый → off_canon (даже при verified базы)
        pf.is_white_bg = lambda raw, **k: False
        pf._aspect_ok = lambda raw, target="4:5", **k: True
        bad_bg = pf.verify_canon(_PNG, facts={}, donor_phashes=["b" * 16])
        # пропорция мимо → off_canon
        pf.is_white_bg = lambda raw, **k: True
        pf._aspect_ok = lambda raw, target="4:5", **k: False
        bad_ar = pf.verify_canon(_PNG, facts={}, donor_phashes=["b" * 16])
        # не проверено (нет PIL) → НЕ роняем в off_canon, честный тир базы сохраняется
        pf.is_white_bg = lambda raw, **k: None
        pf._aspect_ok = lambda raw, target="4:5", **k: None
        unknown = pf.verify_canon(_PNG, facts={}, donor_phashes=["b" * 16])
        ok = (good["tier"] == "verified" and bad_bg["tier"] == "off_canon"
              and bad_ar["tier"] == "off_canon" and unknown["tier"] == "verified"
              and good["white_bg"] is True and unknown["white_bg"] is None)
        return ok, (f"canon_ok={good['tier']} bad_bg={bad_bg['tier']} "
                    f"bad_ar={bad_ar['tier']} unknown={unknown['tier']}")
    finally:
        pf.is_white_bg, pf._aspect_ok, pf._hunter = save_wb, save_ar, save_hunter


# ── F26: forge(canon=...) — по умолчанию OFF (обратная совместимость), верно в dry ──
def t26_forge_canon_default_off():
    # canon по умолчанию False → verify_plan говорит про photo_hunter, флаг canon=False.
    res_off = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=True)
    off = (res_off.get("canon") is False and "photo_hunter" in res_off.get("verify_plan", ""))
    # canon=True → dry честно помечает канон-план (белый фон + 4:5) и флаг True.
    res_on = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=True, canon=True)
    on = (res_on.get("canon") is True and "4:5" in res_on.get("verify_plan", "")
          and res_on["dry"] is True and res_on.get("sent") is False)
    ok = off and on
    return ok, f"default_off={off} canon_on_plan={on}"


# ── F27: ru_openai — слаг модели из env RU_OPENAI_MODEL (дефолт байт-в-байт, dry герметичен) ──
def t27_ru_openai_model_env():
    # Дефолт (env не задан) → дешёвый RU_OPENAI_DEFAULT_MODEL: обратная совместимость.
    with _EnvForce(PHOTO_FORGE_PROVIDER="ru_openai", RU_OPENAI_MODEL=None,
                   NEUROAPI_API_KEY=None, RU_OPENAI_API_KEY=None):
        dflt = pf._default_model()
        res_d = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=True)
    # Override → и _default_model, и сухой отчёт (model + request.model) уважают env; наружу 0.
    with _EnvForce(PHOTO_FORGE_PROVIDER="ru_openai", RU_OPENAI_MODEL="flux",
                   NEUROAPI_API_KEY=None, RU_OPENAI_API_KEY=None):
        ovr = pf._default_model()
        res_o = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=True)
    ok = (dflt == pf.RU_OPENAI_DEFAULT_MODEL and res_d.get("model") == pf.RU_OPENAI_DEFAULT_MODEL
          and ovr == "flux" and res_o.get("model") == "flux"
          and res_o.get("request", {}).get("model") == "flux"
          and res_o.get("provider") == "ru_openai"
          and res_o["dry"] is True and res_o.get("sent") is False
          and res_o.get("est_cost_usd") == pf.RU_OPENAI_EST_USD)
    return ok, (f"default={dflt} override={ovr} dry_model={res_o.get('model')} "
                f"preview_model={res_o.get('request', {}).get('model')} sent={res_o.get('sent')}")


# ── F28: ru_openai build_request — форма OpenAI Images (top-level prompt), НЕ chat и НЕ google ──
def t28_ru_openai_request_shape():
    gen = pf.build_request("нарисуй", None, None, provider="ru_openai")
    edt = pf.build_request("переработай", "QUJD", None, provider="ru_openai")   # донор НЕ в теле
    sized = pf._build_request_ru_openai("нарисуй", "some-model", size="1024x1280")
    ok = (gen["prompt"] == "нарисуй" and gen["response_format"] == "b64_json" and gen["n"] == 1
          and gen["model"] == pf.RU_OPENAI_DEFAULT_MODEL
          and "messages" not in gen and "contents" not in gen        # НЕ openrouter и НЕ google
          and "size" not in gen                                       # размер по умолчанию не шлём
          and edt["prompt"] == "переработай"                          # edit: тот же generate-body
          and sized["model"] == "some-model" and sized["size"] == "1024x1280")
    return ok, (f"prompt_top={gen.get('prompt') == 'нарисуй'} rf={gen.get('response_format')} "
                f"no_msgs={'messages' not in gen} size_opt={'size' in sized}")


# ── F29: ru_openai extract_image — data[].b64_json/url; текст ошибки и пустой data → промах ──
def t29_ru_openai_extract_image():
    b64 = base64.b64encode(_PNG).decode("ascii")
    r_b64 = {"data": [{"b64_json": b64}]}                              # голый base64 картинки
    r_url = {"data": [{"url": _png_data_url()}]}                       # data-url картинки
    err = base64.b64encode(b"plain-text error from the aggregator, this is definitely "
                           b"not an image payload at all!!").decode("ascii")
    r_txt = {"data": [{"b64_json": err}]}                              # base64 текста → не картинка
    r_empty = {"data": []}
    m1, x1 = pf.extract_image(r_b64)
    m2, x2 = pf.extract_image(r_url)
    m3, x3 = pf.extract_image(r_txt)                                   # 200 ≠ успех: не картинка → промах
    m4, x4 = pf.extract_image(r_empty)
    ok = (x1 == _PNG and m1 == "image/png" and x2 == _PNG
          and x3 is None and m3 is None and x4 is None and m4 is None)
    return ok, f"b64={'ok' if x1 else '-'} url={'ok' if x2 else '-'} err_miss={x3 is None} empty_miss={x4 is None}"


# ── F30: ru_openai заголовок Bearer (не x-goog), путь /images/generations, база neuroapi ──
def t30_ru_openai_headers_ep():
    with _EnvForce(PHOTO_FORGE_PROVIDER="ru_openai", NEUROAPI_API_KEY="sk-neuro-TEST",
                   RU_OPENAI_API_KEY=None, RU_OPENAI_BASE_URL=None, RU_OPENAI_MODEL=None):
        h = pf._headers()
        ep = pf._endpoint_path(pf._default_model())
        base = pf._base_url()
    ok = (h.get("Authorization") == "Bearer sk-neuro-TEST" and "x-goog-api-key" not in h
          and ep == pf.RU_OPENAI_IMAGES_PATH and base == pf.RU_OPENAI_API)
    return ok, f"bearer={h.get('Authorization') == 'Bearer sk-neuro-TEST'} ep={ep} base={base}"


# ── F31: ru_openai авто-выбор ПОСЛЕ google/fusionbrain + изоляция (не берёт чужой OPENAI_API_KEY) ──
def t31_ru_openai_autodetect_isolation():
    # только ключ RU-агрегатора (нет google/fusionbrain) → ru_openai
    with _EnvForce(PHOTO_FORGE_PROVIDER=None, GEMINI_API_KEY=None, GOOGLE_API_KEY=None,
                   GOOGLE_AI_STUDIO_KEY=None, FUSIONBRAIN_API_KEY=None, FUSIONBRAIN_SECRET_KEY=None,
                   OPENROUTER_API_KEY=None, OPENAI_API_KEY=None, RU_OPENAI_API_KEY=None,
                   NEUROAPI_API_KEY="sk-neuro-TEST"):
        p_ru = pf._provider()
    # чужой OPENAI_API_KEY + родной OPENROUTER, БЕЗ neuroapi → openrouter; ru_openai чужой ключ НЕ берёт
    with _EnvForce(PHOTO_FORGE_PROVIDER=None, GEMINI_API_KEY=None, GOOGLE_API_KEY=None,
                   GOOGLE_AI_STUDIO_KEY=None, FUSIONBRAIN_API_KEY=None, FUSIONBRAIN_SECRET_KEY=None,
                   OPENROUTER_API_KEY="sk-or", OPENAI_API_KEY="sk-foreign",
                   NEUROAPI_API_KEY=None, RU_OPENAI_API_KEY=None):
        p_or = pf._provider()
        borrowed = pf._ru_openai_key()          # НЕ заимствует чужой OPENAI_API_KEY соседа
    # форс ru_openai перебивает даже при google-ключе
    with _EnvForce(PHOTO_FORGE_PROVIDER="ru_openai", GEMINI_API_KEY="AIza-TEST",
                   NEUROAPI_API_KEY=None, RU_OPENAI_API_KEY=None):
        p_forced = pf._provider()
    ok = (p_ru == "ru_openai" and p_or == "openrouter" and borrowed is None and p_forced == "ru_openai")
    return ok, f"neuro→{p_ru} foreign→{p_or} borrowed={borrowed} forced→{p_forced}"


# ── F32: ru_openai dry — наружу 0, превью Images (response_format), edit→generate mode_note ──
def t32_ru_openai_dry_preview():
    with _EnvForce(PHOTO_FORGE_PROVIDER="ru_openai", NEUROAPI_API_KEY="sk-neuro-TEST",
                   RU_OPENAI_API_KEY=None, RU_OPENAI_MODEL=None):
        res = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=True)
        res_edit = pf.forge(mode="edit", source="https://site/donor.jpg",
                            facts={"вид": "плёнка"}, dry=True)
    r = res.get("request", {})
    ok = (res["dry"] is True and res.get("sent") is False
          and res.get("provider") == "ru_openai" and r.get("provider") == "ru_openai"
          and r.get("response_format") == "b64_json" and r.get("has_source_image") is False
          and res["est_cost_usd"] == pf.RU_OPENAI_EST_USD
          and res_edit.get("sent") is False and bool(res_edit.get("mode_note")))
    return ok, (f"provider={res.get('provider')} sent={res.get('sent')} rf={r.get('response_format')} "
                f"est={res.get('est_cost_usd')} edit_note={bool(res_edit.get('mode_note'))}")


# ── F33: ru_openai живой кадр (фейк-сеть, БЕЗ usage) → ok, файл, ОЦЕНКА расхода в леджер ──
def t33_ru_openai_live_generate():
    tmp = Path(tempfile.mkdtemp(prefix="forge_ru_test_"))
    save_state, save_ledger, save_hunter, save_http = pf.STATE, pf.LEDGER, pf._hunter, pf._http_call
    hits = []
    b64 = base64.b64encode(_PNG).decode("ascii")

    def _http(method, url, headers, body, timeout):
        hits.append((url, headers.get("Authorization")))
        return _resp(200, {"data": [{"b64_json": b64}]})           # Images-форма, usage НЕТ → цена=оценка

    try:
        pf.STATE = tmp
        pf.LEDGER = tmp / "photoforge_ledger.json"
        pf._hunter = lambda: None                                  # приёмка → ok_needs_human
        pf._http_call = _http                                      # _Patch форсит openrouter — патчим шов вручную
        with _EnvForce(PHOTO_FORGE_PROVIDER="ru_openai", NEUROAPI_API_KEY="sk-neuro-TEST",
                       RU_OPENAI_API_KEY=None, RU_OPENAI_BASE_URL=None, RU_OPENAI_MODEL=None):
            res = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=False,
                           out_dir=str(tmp), tag="rutest")
        saved_ok = bool(res.get("path")) and Path(res["path"]).exists()
        ledger = json.loads(pf.LEDGER.read_text(encoding="utf-8")) if pf.LEDGER.exists() else []
        hit_ep = bool(hits) and hits[0][0].endswith(pf.RU_OPENAI_IMAGES_PATH)
        bearer = bool(hits) and hits[0][1] == "Bearer sk-neuro-TEST"
        ok = (res.get("ok") is True and res.get("sent") is True and res.get("provider") == "ru_openai"
              and res.get("tier") == "ok_needs_human"
              and res.get("cost_source") == "estimate" and res.get("cost_usd") == pf.RU_OPENAI_EST_USD
              and saved_ok and len(ledger) == 1
              and ledger[0]["cost_source"] == "estimate" and ledger[0]["provider"] == "ru_openai"
              and hit_ep and bearer)
        return ok, (f"ok={res.get('ok')} tier={res.get('tier')} cost={res.get('cost_usd')} "
                    f"src={res.get('cost_source')} файл={'есть' if saved_ok else 'НЕТ'} ep={hit_ep} bearer={bearer}")
    finally:
        pf.STATE, pf.LEDGER, pf._hunter, pf._http_call = save_state, save_ledger, save_hunter, save_http
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


# ── F34: ru_openai extract — ЖИВОЙ http(s)-url ТЯНЕМ байтами (b64_json не уважён), а не декодим строку ──
def t34_ru_openai_extract_http_url():
    class _H:
        def __init__(self, payload):
            self.payload = payload

        def fetch_bytes(self, url):
            return self.payload

    class _FakeResp:
        def __init__(self, d):
            self._d = d

        def read(self, n=None):
            return self._d

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    save_hunter = pf._hunter
    import urllib.request as _urlreq
    save_urlopen = _urlreq.urlopen
    try:
        # 1) хантер отдаёт живой PNG по https-ссылке → кадр ИЗВЛЕЧЁН (не потерян, деньги не сожжены)
        pf._hunter = lambda: _H((_PNG, "image/png"))
        m1, r1 = pf.extract_image({"data": [{"url": "https://cdn.host/img.png"}]})
        hunter_http = (r1 == _PNG and m1 == "image/png")
        # 2) хантера нет → фолбэк stdlib-urllib тянет байты
        pf._hunter = lambda: None
        _urlreq.urlopen = lambda req, timeout=25: _FakeResp(_PNG)
        _m2, r2 = pf.extract_image({"data": [{"url": "https://cdn.host/img2.png"}]})
        urllib_http = (r2 == _PNG)
        # 3) по ссылке пришёл НЕ образ (html-ошибка) → честный промах, без ложного успеха
        _urlreq.urlopen = lambda req, timeout=25: _FakeResp(b"<html>err</html>" * 8)
        m3, r3 = pf.extract_image({"data": [{"url": "https://cdn.host/oops"}]})
        nonimg_miss = (r3 is None and m3 is None)
        # 4) data:-URL по-прежнему декодится напрямую (регрессия старого пути, без сети)
        _m4, r4 = pf.extract_image({"data": [{"url": _png_data_url()}]})
        data_url_ok = (r4 == _PNG)
    finally:
        pf._hunter = save_hunter
        _urlreq.urlopen = save_urlopen
    ok = hunter_http and urllib_http and nonimg_miss and data_url_ok
    return ok, (f"hunter_http={hunter_http} urllib_http={urllib_http} "
                f"nonimg_miss={nonimg_miss} data_url_ok={data_url_ok}")


# ── F35: ru_openai 200-БЕЗ-КАРТИНКИ на ПЛАТНОМ шлюзе → расход В ЛЕДЖЕР (не «за 0₽»), ретраи считаются ──
# Дыра, найденная состязательным ревью: 200-OK без извлекаемого кадра (напр. url недостижим с RU-egress)
# уходил в continue ВЫШЕ записи цены — леджер показывал $0.00, а ретраи жгли ещё платные вызовы, и даже
# серверный usage.cost молча терялся. Тест пинит: КАЖДЫЙ платный 200 = строка в леджере + честный итог.
def t35_ru_openai_no_image_ledgers_spend():
    tmp = Path(tempfile.mkdtemp(prefix="forge_ru_nimg_"))
    save_state, save_ledger, save_hunter, save_http = pf.STATE, pf.LEDGER, pf._hunter, pf._http_call
    hits = []

    def _http_noimg(method, url, headers, body, timeout):        # 200 OK, картинки НЕТ, usage НЕТ → оценка
        hits.append(url)
        return _resp(200, {"data": []})

    def _http_noimg_usage(method, url, headers, body, timeout):  # 200 OK, картинки НЕТ, НО usage.cost есть
        hits.append(url)
        return _resp(200, {"data": [], "usage": {"cost": 0.05}})

    try:
        pf.STATE = tmp
        pf._hunter = lambda: None
        est = pf.RU_OPENAI_EST_USD
        # ── Случай A: без usage → цена=ОЦЕНКА, но ПОСТРОЧНО в леджер + суммарный честный итог ──
        pf.LEDGER = tmp / "led_a.json"
        pf._http_call = _http_noimg
        with _EnvForce(PHOTO_FORGE_PROVIDER="ru_openai", NEUROAPI_API_KEY="sk-neuro-TEST",
                       RU_OPENAI_API_KEY=None, RU_OPENAI_BASE_URL=None, RU_OPENAI_MODEL=None):
            resA = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=False, out_dir=str(tmp), tag="nimgA")
        ledA = json.loads(pf.LEDGER.read_text(encoding="utf-8")) if pf.LEDGER.exists() else []
        n_calls_A = len(hits)
        caseA = (resA.get("ok") is False and resA.get("sent") is True
                 and n_calls_A == 3                                   # ретраи РЕАЛЬНО жгут 3 платных вызова
                 and len(ledA) == 3                                   # каждый — строка в леджере (не $0.00)
                 and all(e.get("tier") == "no_image" for e in ledA)
                 and all(e.get("cost_source") == "estimate_no_image" for e in ledA)
                 and all(e.get("cost_usd") == est for e in ledA)
                 and resA.get("cost_source") == "sum"
                 and resA.get("cost_usd") == round(3 * est, 6)
                 and resA.get("path") is None)
        # ── Случай B: usage.cost есть → берём РЕАЛЬНУЮ серверную цену, не оценку (не теряем списание) ──
        hits.clear()
        pf.LEDGER = tmp / "led_b.json"
        pf._http_call = _http_noimg_usage
        with _EnvForce(PHOTO_FORGE_PROVIDER="ru_openai", NEUROAPI_API_KEY="sk-neuro-TEST",
                       RU_OPENAI_API_KEY=None, RU_OPENAI_BASE_URL=None, RU_OPENAI_MODEL=None):
            resB = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=False, out_dir=str(tmp), tag="nimgB")
        ledB = json.loads(pf.LEDGER.read_text(encoding="utf-8")) if pf.LEDGER.exists() else []
        caseB = (len(ledB) == 3
                 and all(e.get("cost_source") == "usage" for e in ledB)
                 and all(e.get("cost_usd") == 0.05 for e in ledB)
                 and resB.get("cost_usd") == round(3 * 0.05, 6)
                 and resB.get("cost_source") == "sum")
        ok = caseA and caseB
        return ok, (f"A calls={n_calls_A} led={len(ledA)} sum={resA.get('cost_usd')} src={resA.get('cost_source')} | "
                    f"B led={len(ledB)} led_src={ledB[0].get('cost_source') if ledB else None} sum={resB.get('cost_usd')}")
    finally:
        pf.STATE, pf.LEDGER, pf._hunter, pf._http_call = save_state, save_ledger, save_hunter, save_http
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


# ── F36: живой canon без PIL — ОТКАЗ ДО ТРАТЫ (бронь-гард ATLAS EDGE) ──
def t36_canon_no_pil_refuses_before_spend():
    """Дыра, которую закрываем: без PIL verify_canon слеп (is_white_bg/_aspect_ok=None → ветка
    off_canon НЕДОСТИЖИМА), поэтому платный кадр ушёл бы «вслепую» под видом ok_needs_human, а бронь
    ATLAS EDGE молча спала. Гард в forge() должен ФИЗИЧЕСКИ отказать ДО сети. Два случая пинят гейт
    ровно на _have_pil():
      A) PIL НЕДОСТУПЕН (нет хантера) → ok=False, sent=False, tier=canon_unverifiable, 0₽, 0 сети,
         леджер не создан, файл не сохранён, есть why+hint.
      B) PIL «доступен» (_have_pil→True) → гард НЕ срабатывает, форж идёт в сеть (гейт точный, не
         затыкает обычный путь). Герметично: патчим _have_pil напрямую, реальный Pillow не нужен."""
    tmp = Path(tempfile.mkdtemp(prefix="forge_canonpil_"))
    save_state, save_ledger, save_hunter, save_have = pf.STATE, pf.LEDGER, pf._hunter, pf._have_pil
    hitsA, hitsB = [], []

    def _httpA(method, url, headers, body, timeout):
        hitsA.append(url)                                   # любая сеть здесь = ПРОВАЛ гарда
        return _resp(200, {"choices": [{"message": {"images": [{"image_url": {"url": _png_data_url()}}]}}]})

    def _httpB(method, url, headers, body, timeout):
        hitsB.append(url)
        return _resp(200, {"choices": [{"message": {"images": [{"image_url": {"url": _png_data_url()}}]}}]})

    try:
        pf.STATE = tmp
        # ── Случай A: PIL НЕДОСТУПЕН → живой canon обязан отказаться ДО сети ──
        pf.LEDGER = tmp / "led_a.json"
        pf._hunter = lambda: None                          # _have_pil()=False
        with _Patch(http_call=_httpA):
            resA = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=False,
                            canon=True, out_dir=str(tmp), tag="canonNoPil")
        ledA = json.loads(pf.LEDGER.read_text(encoding="utf-8")) if pf.LEDGER.exists() else []
        caseA = (resA.get("ok") is False and resA.get("sent") is False
                 and resA.get("tier") == "canon_unverifiable"
                 and resA.get("cost_usd") == 0.0
                 and len(hitsA) == 0                        # НИ ОДНОГО платного вызова
                 and not pf.LEDGER.exists() and len(ledA) == 0
                 and not resA.get("path")
                 and bool(resA.get("why")) and bool(resA.get("hint")))

        # ── Случай B: PIL «доступен» → гард НЕ срабатывает, форж идёт в сеть (точность гейта) ──
        pf.LEDGER = tmp / "led_b.json"
        pf._have_pil = lambda: True                        # гейт ровно на _have_pil()
        with _Patch(http_call=_httpB):
            resB = pf.forge(mode="generate", facts={"вид": "плёнка"}, dry=False,
                            canon=True, out_dir=str(tmp), tag="canonPil")
        caseB = (resB.get("sent") is True and len(hitsB) == 1
                 and resB.get("tier") != "canon_unverifiable")
        ok = caseA and caseB
        return ok, (f"A: ok={resA.get('ok')} sent={resA.get('sent')} tier={resA.get('tier')} "
                    f"сеть={len(hitsA)} ₽={resA.get('cost_usd')} | "
                    f"B: sent={resB.get('sent')} сеть={len(hitsB)} tier={resB.get('tier')}")
    finally:
        pf.STATE, pf.LEDGER, pf._hunter, pf._have_pil = save_state, save_ledger, save_hunter, save_have
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


# ── F40: L3b/L3c — переводчик габаритов в язык пропорций (корень «товар визуально не по запросу») ──
def t40_shape_hint_from_dims():
    # (a) короб оператора 600×400×400: НЕ куб, вытянут в длину, ×1.5, две стороны равны — в HEAD.
    box = {"вид": "Гофрокороб 4-х клапанный", "размер": "600×400×400 мм"}
    h = pf._shape_hint(box)
    p = pf.build_prompt(facts=box, ops=["crop_aspect_4x5"], mode="generate")
    box_ok = ("это НЕ куб" in h and "вытянут в длину" in h and "1.5×" in h
              and "две другие стороны равны" in h)
    # намёк в HEAD (до «Требования:») → виден модели и в _preview.
    hp, rp = p.find("вытянут в длину"), p.find("Требования:")
    in_head = 0 <= hp < rp
    # (b) куб 400×400×400 → «куб-короб, НЕ вытянутый», без «вытянут в длину».
    cube = pf._shape_hint({"размер": "400×400×400 мм"})
    cube_ok = ("КУБИЧЕСКОЙ" in cube and "НЕ вытянутый" in cube and "вытянут в длину" not in cube)
    # (c) плоский 500×480×80 → низкий и широкий; ×6.
    flat = pf._shape_hint({"габариты": "500×480×80 мм"})
    flat_ok = ("низкий и широкий" in flat and "это НЕ куб" in flat)
    # (d) _parse_dims: нужно ≥2 чисел. Одно число → нет формы (не гадаем по одной стороне).
    one_vals, _ = pf._parse_dims({"размер": "90 см"})
    two_vals, _ = pf._parse_dims({"размер": "1,2 x 0,9 м"})       # запятая-десятичн., 2 числа
    parse_ok = (one_vals is None and two_vals == [1.2, 0.9])
    # (e) ОБРАТНАЯ СОВМЕСТИМОСТЬ: без габаритов намёк пуст → промпт байт-в-байт как до фичи.
    nodim = {"вид": "плёнка", "цвет": "прозрачный"}
    empty = pf._shape_hint(nodim)
    p_nd = pf.build_prompt(facts=nodim, ops=["crop_aspect_4x5"], mode="generate")
    compat = (empty == "" and pf._shape_hint({}) == ""
              and "это НЕ куб" not in p_nd and "КУБИЧЕСКОЙ" not in p_nd
              and "передай эти пропорции" not in p_nd)
    ok = box_ok and in_head and cube_ok and flat_ok and parse_ok and compat
    return ok, (f"box={box_ok} in_head={in_head} cube={cube_ok} flat={flat_ok} "
                f"parse={parse_ok} compat={compat}")


TESTS = [
    ("F1  no_key_honest", t1_no_key_honest),
    ("F2  auth_401_is_keys", t2_auth_401_is_keys),
    ("F3  transient_retry", t3_transient_retry),
    ("F4  dry_gate_no_send", t4_dry_gate_no_send),
    ("F5  request_shape", t5_request_shape),
    ("F6  prompt_watermark", t6_prompt_watermark),
    ("F7  extract_image_ok", t7_extract_image_ok),
    ("F8  extract_image_miss", t8_extract_image_miss),
    ("F9  decode_data_url", t9_decode_data_url),
    ("F10 magic_is_image", t10_magic_is_image),
    ("F11 scan_watermark", t11_scan_watermark),
    ("F12 assess_uniqueness", t12_assess_uniqueness),
    ("F13 verify_non_image", t13_verify_non_image),
    ("F14 verify_tiers", t14_verify_tiers),
    ("F15 rights_boundary", t15_rights_boundary),
    ("F16 live_writes_ledger", t16_live_writes_ledger),
    ("F17 google_request_shape", t17_google_request_shape),
    ("F18 google_extract_image", t18_google_extract_image),
    ("F19 google_headers_ep", t19_google_headers_ep),
    ("F20 provider_autodetect", t20_provider_autodetect),
    ("F21 google_dry_preview", t21_google_dry_preview),
    ("F22 google_finish_reason", t22_google_finish_reason),
    ("F23 dry_edit_no_fetch", t23_dry_edit_no_fetch),
    ("F24 brand_lock", t24_brand_lock),
    ("F25 verify_canon_rejects", t25_verify_canon_rejects),
    ("F26 forge_canon_default_off", t26_forge_canon_default_off),
    ("F27 ru_openai_model_env", t27_ru_openai_model_env),
    ("F28 ru_request_shape", t28_ru_openai_request_shape),
    ("F29 ru_extract_image", t29_ru_openai_extract_image),
    ("F30 ru_headers_ep", t30_ru_openai_headers_ep),
    ("F31 ru_autodetect_iso", t31_ru_openai_autodetect_isolation),
    ("F32 ru_dry_preview", t32_ru_openai_dry_preview),
    ("F33 ru_live_generate", t33_ru_openai_live_generate),
    ("F34 ru_extract_http_url", t34_ru_openai_extract_http_url),
    ("F35 ru_noimg_ledgers_spend", t35_ru_openai_no_image_ledgers_spend),
    ("F36 canon_nopil_refuse", t36_canon_no_pil_refuses_before_spend),
    ("F37 brand_fill_directive", t37_brand_fill_directive),
    ("F38 subject_metrics", t38_subject_metrics),
    ("F39 verify_canon_subject_gate", t39_verify_canon_subject_gate),
    ("F40 shape_hint_from_dims", t40_shape_hint_from_dims),
]


def main():
    print("🎯 PHOTO-FORGE ПРИЁМКА · ФОТО-КУЗНИЦА (сухо, 0₽, без сети/ключа)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<24} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

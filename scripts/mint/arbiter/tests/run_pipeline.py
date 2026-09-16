#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHOTO-PIPELINE ПРИЁМКА — ФОТО-КОНВЕЙЕР «под ключ» (мост товар→кадр): сухо, 0₽, без сети/ключа.

Мост оркеструет три органа: план (uniqueizer) + донор (hunter) → кадр (forge). Тесты
оффлайн-детерминированы: сеть кузницы (pf._http_call) и сама pf.forge подменяются, искатель —
заглушка. Реальный ключ НЕ нужен. Проверяем СШИВКУ и ЗАКОНЫ моста (а внутренности кузницы —
уже 23/23 в run_photoforge.py; здесь их не дублируем).

  P1  plan_wires_uniqueizer  — plan_for берёт ops из uniqueizer (единый источник); нет его → дефолт.
  P2  dry_hermetic           — forge_card(dry) : 0 сети, 0 вызовов искателя, sent=False, request есть.
  P3  dry_generate_no_url    — товар без ссылок → mode=generate, превью без исходного кадра.
  P4  always_forge_law       — ГЛАВНЫЙ ЗАКОН: даже с ЧИСТЫМ донором мост ВСЁ РАВНО куёт (edit),
                              не кладёт фото первоисточника как есть (иначе МП склеит по pHash).
  P5  donor_ladder_pick      — _pick_donor: чистый > непроверенный > нет; 'bad' никогда не берём.
  P6  live_generate_fallback — донор не загрузился живьём → честный откат на generate (не молчание).
  P7  live_no_donor_generate — нет ссылок → generate с нуля, кузница зовётся ровно раз, режим верен.
  P8  money_gate             — dry по умолчанию даже при вставленном ключе: наружу 0 (двойной гейт).
  P9  doctor_no_key_honest   — доктор без ключа: creds=False, ready_for_live=False, зонд пропущен,
                              наружу только ИМЕНА env (bool), НЕ значения ключей.
  P10 doctor_probe           — 0₽ зонд провайдера: видит целевой слаг в каталоге (google и openrouter).
  P11 nondict_product        — кривой товар (None/str/int/list) не роняет мост: деградируем сухо, 0 сети.
  P12 doctor_key_isolation   — доктор честен про ИЗОЛЯЦИЮ: РОДНОЙ ключ → готов к live; ЧУЖОЙ
                              OPENAI_API_KEY при openrouter кузница ИГНОРИТ → key_kind=none, обезоружен,
                              live НЕ готов + caveat; ложного апгрейда нет даже со стаб-сетью.
  P13 publish_provenance_gate — photo_publish: URL строится ТОЛЬКО для СВОИХ пикселей (own_pixels)
                              + tier=verified + есть файл; производное/off_canon/не-ok → urls=[] + blocked.
  P14 publish_no_local_leak  — в pictures НИКОГДА не попадает локальный путь/base64: dry-годный кадр
                              даёт would_url (показать) но blocked=True и urls=[] (наружу ничего).
  P15 hoster_dry_hermetic    — YandexObjectStorage.put(dry): 0 сети, имя объекта детерминировано,
                              key_env — только ИМЕНА→bool (значения ключей не раскрываются); живой
                              залив через фейковый хостер → urls несёт публичный URL, blocked=False.
  P16 write_merge_photo_urls — create_card(photo_urls): наши кадры ВПЕРЁД в pictures[], дедуп, потолок
                              30, prod вызывающего НЕ мутируется, не-dict товар не роняет (ok=False).
  P17 doctor_ru_openai_native — РОДНОЙ neuroapi-ключ → провайдер ru_openai, live-готов без сети, без caveat.
  P18 canon_threads_to_forge — бронь ATLAS EDGE (canon=True) долетает товар→кузница; default цел.
  P19 acquire_good_direct_attach — ИСКАТЕЛЬ-ПЕРВЫМ: find()['good'] с чистого источника приклеивается
                              напрямую (opt-in attach_good_direct), source=finder, кузница не зовётся.
  P20 acquire_unknown_not_attached — ЗАКОН ЧЕСТНОСТИ: 'unknown' сам НИКОГДА не в photo_urls (только в
                              proposals + входом в кузницу); allow_unknown=True снимает замок ЯВНО.
  P21 acquire_empty_forge_fallback — пусто у искателя → честный фолбэк «куём с нуля» (source=forge).
  P22 acquire_forge_from_best_uniquifies — ДЕФОЛТ: сырой good-URL НЕ приклеен, а идёт входом в кузницу
                              (pHash-закон моста), best верифицирован → prefer_clean=False.
  P23 acquire_feeds_create_card — СШИВКА: photo_urls искателя долетают в pictures[] карточки Маркета,
                              prod вызывающего не мутирован, 0 сети (RUBICON: producer сам не публикует).
  P24 live_infographic_dead_forge — БАГ-РЕГРЕССИЯ: живой путь инфографики при МЁРТВОЙ кузнице (402)
                              не падает ('NoneType' не переопределяет отчётный `base`), берёт донора,
                              брендирует локально (0₽/PIL), отчёт честен (кузница = ok False, инфо = ok).
  P25 acquire_infographic_reaches_photo_urls — ПРОВЯЗКА: произведённый инфографический кадр
                              (0₽/PIL, derivative) публикуется и ДОЛЕТАЕТ в photo_urls (гейт открыт
                              allow_derivative=True — отмашка оператора на фирменную инфографику).

Наружу не уходит ничего (0₽). Живой кадр — только по отмашке (dry=False), здесь не выполняется.
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import photo_forge_v1 as pf          # noqa: E402
import photo_pipeline_v1 as pp       # noqa: E402
import photo_publish_v1 as pub       # noqa: E402
import ymarket_write_v1 as w         # noqa: E402


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


class _ForgeSpy:
    """Подмена pf.forge: пишет каждый вызов (kwargs) и отдаёт заранее заданные результаты по очереди."""
    def __init__(self, results):
        self.calls = []
        self._results = list(results)

    def __call__(self, **kw):
        self.calls.append(kw)
        return self._results[min(len(self.calls) - 1, len(self._results) - 1)]


class _HunterStub:
    """Заглушка искателя: hunt() возвращает заданный разбор good/unknown/bad."""
    def __init__(self, good=(), unknown=(), bad=()):
        self._r = {"good": list(good), "unknown": list(unknown), "bad": list(bad),
                   "got": len(good), "enough": bool(good), "capabilities": {}}

    def hunt(self, urls, facts=None, need=5, donor_urls=()):
        return self._r


class _FindStub:
    """Заглушка ПОЛНОГО искателя: find() отдаёт заданный разбор (0 сети, детерминировано)."""
    def __init__(self, good=(), unknown=(), clean_candidates=(), bad=(), discovered=0):
        self.calls = []
        self._r = {"good": list(good), "unknown": list(unknown),
                   "clean_candidates": list(clean_candidates), "bad": list(bad),
                   "discovered": discovered, "direct_links": []}

    def find(self, query, facts=None, need=5, sources=("wildberries",)):
        self.calls.append({"query": query, "need": need, "sources": tuple(sources)})
        # копия, чтобы вызывающий не мутировал заглушку между тестами
        return {k: (list(v) if isinstance(v, list) else v) for k, v in self._r.items()}


class _ForgeCardSpy:
    """Подмена pp.forge_card: пишет kwargs каждого вызова, отдаёт заданный отчёт кузницы."""
    def __init__(self, forged=None):
        self.calls = []
        self._forged = forged or {"ok": True, "mode": "generate", "dry": True, "forge": {}}

    def __call__(self, product, **kw):
        self.calls.append(kw)
        return dict(self._forged)


class _Patched:
    """Контекст: подменить атрибуты модулей и гарантированно откатить."""
    def __init__(self, **targets):
        # targets: "pf.forge"=obj / "pp._hunter"=obj / "pf._http_call"=obj ...
        self._targets = targets
        self._save = {}

    def __enter__(self):
        for dotted, val in self._targets.items():
            mod, attr = dotted.split(".", 1)
            m = {"pf": pf, "pp": pp}[mod]
            self._save[dotted] = getattr(m, attr)
            setattr(m, attr, val)
        return self

    def __exit__(self, *exc):
        for dotted, old in self._save.items():
            mod, attr = dotted.split(".", 1)
            setattr({"pf": pf, "pp": pp}[mod], attr, old)
        return False


# ВСЕ ключи, влияющие на выбор/готовность провайдера. _EnvForce гасит их по умолчанию: тест
# перечисляет только то, что ему НУЖНО, и не зависит от того, что оператор вписал в mint/.env.
# Зачем: 15.09 оператор вписал ЖИВЫЕ ключи YandexART — и три зелёных теста покраснели, хотя код
# был прав (YAART теперь честно вооружён и автовыбор его берёт). Тест, читающий чужой .env, врёт
# в обе стороны: зеленеет от чужого ключа и краснеет от рабочего.
_PROVIDER_KEYS = (
    "PHOTO_FORGE_PROVIDER",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_AI_STUDIO_KEY",
    "OPENROUTER_API_KEY", "OPENAI_API_KEY",
    "NEUROAPI_API_KEY", "RU_OPENAI_API_KEY",
    "FUSIONBRAIN_API_KEY", "FUSIONBRAIN_SECRET_KEY",
    "YAART_API_KEY", "YC_API_KEY", "YAART_FOLDER_ID", "YC_FOLDER_ID",
)


class _EnvForce:
    """Выставить/снять env и заморозить _ENV_TRIED (чтобы .env не перечитался). None → удалить.

    Неперечисленные провайдерные ключи гасятся сами (см. _PROVIDER_KEYS) — герметичность по умолчанию."""
    def __init__(self, **kv):
        for _k in _PROVIDER_KEYS:
            kv.setdefault(_k, None)
        self._kv, self._save, self._tried = kv, {}, None

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


_OK = {"ok": True, "path": "/tmp/forged_x.png", "tier": "ok_needs_human", "sent": True,
       "rights": {"level": "derivative", "clean": False}, "cost_usd": 0.04, "cost_source": "usage"}
_DONOR_FAIL = {"ok": False, "why": "донорский кадр не загрузился (путь/url)",
               "rights": {"level": "derivative", "clean": False}}

_PRODUCT = {"name": "Плёнка воздушно-пузырьковая рулон", "sku": "ARB-1",
            "url": "https://maker.example/film.jpg",
            "facts": {"вид": "плёнка", "ширина_см": 120}}


# ── P1: план сшит с уникализатором (единый источник ops) ──
def t1_plan_wires_uniqueizer():
    plan = pp.plan_for(["https://x/y.jpg"])
    ops = plan.get("ops") or []
    wired = ("recompose_on_white_bg" in ops and any("watermark" in o for o in ops)
             and plan.get("source_images") == ["https://x/y.jpg"])
    with _Patched(**{"pp._uniq": (lambda: None)}):
        fb = pp.plan_for(["https://x/y.jpg"])
    fallback = fb.get("ops") == list(pf.DEFAULT_OPS)
    return wired and fallback, f"ops_wired={wired} fallback_default={fallback}"


# ── P2: сухой прогон герметичен (0 сети, 0 искателя) ──
def t2_dry_hermetic():
    net, hunts = [], []

    def _http(method, url, headers, body, timeout):
        net.append(url)
        return pf._Resp(200, {})

    class _SpyHunter(_HunterStub):
        def hunt(self, *a, **k):
            hunts.append(1)
            return self._r

    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-test"), \
         _Patched(**{"pf._http_call": _http, "pp._hunter": (lambda: _SpyHunter())}):
        res = pp.forge_card(_PRODUCT, dry=True)
    fr = res.get("forge") or {}
    ok = (res["ok"] is True and res["dry"] is True and res["mode"] == "edit"
          and len(net) == 0 and len(hunts) == 0        # герметично: ни сети, ни хантинга в dry
          and fr.get("sent") is False and fr.get("request") is not None)
    return ok, f"dry={res['dry']} mode={res['mode']} сети={len(net)} хантов={len(hunts)}"


# ── P3: нет ссылок → generate, превью без исходника ──
def t3_dry_generate_no_url():
    prod = {"name": "Товар без фото", "sku": "ARB-2", "facts": {"вид": "нечто"}}
    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-test"):
        res = pp.forge_card(prod, dry=True)
    fr = res.get("forge") or {}
    req = fr.get("request") or {}
    ok = (res["mode"] == "generate" and (res.get("donor") or {}).get("kind") == "none"
          and req.get("has_source_image") is False)
    return ok, f"mode={res['mode']} donor={(res.get('donor') or {}).get('kind')} has_img={req.get('has_source_image')}"


# ── P4: ГЛАВНЫЙ ЗАКОН — даже с чистым донором мост КУЁТ (не кладёт фото как есть) ──
def t4_always_forge_law():
    spy = _ForgeSpy([_OK])
    clean = _HunterStub(good=[{"url": "https://maker.example/clean.jpg", "verdict": "good"}])
    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-test"), \
         _Patched(**{"pf.forge": spy, "pp._hunter": (lambda: clean)}):
        res = pp.forge_card(_PRODUCT, dry=False)
    called = len(spy.calls) == 1
    edited = called and spy.calls[0].get("mode") == "edit"
    from_clean = called and spy.calls[0].get("source") == "https://maker.example/clean.jpg"
    donor_clean = (res.get("donor") or {}).get("kind") == "clean"
    # закон: даже при чистом доноре ПИКСЕЛИ перекованы (forge вызван, mode edit), а не отдан донор as-is
    ok = called and edited and from_clean and donor_clean and res["ok"] is True
    return ok, f"forge_called={called} mode={spy.calls[0].get('mode') if called else '-'} donor={(res.get('donor') or {}).get('kind')}"


# ── P5: лестница выбора донора ──
def t5_donor_ladder_pick():
    g = {"good": [{"url": "G"}], "unknown": [{"url": "U"}]}
    u = {"good": [], "unknown": [{"url": "U"}]}
    n = {"good": [], "unknown": []}
    pg = pp._pick_donor(g)
    pu = pp._pick_donor(u)
    pn = pp._pick_donor(n)
    ok = (pg == ("G", "clean") and pu == ("U", "unproven") and pn == (None, "none"))
    return ok, f"good→{pg} unknown→{pu} none→{pn}"


# ── P6: донор не загрузился живьём → честный откат на generate ──
def t6_live_generate_fallback():
    spy = _ForgeSpy([_DONOR_FAIL, _OK])            # 1-й (edit) провал донора → 2-й (generate) успех
    unproven = _HunterStub(unknown=[{"url": "https://shop.example/u.jpg"}])
    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-test"), \
         _Patched(**{"pf.forge": spy, "pp._hunter": (lambda: unproven)}):
        res = pp.forge_card(_PRODUCT, dry=False)
    two = len(spy.calls) == 2
    seq = two and spy.calls[0].get("mode") == "edit" and spy.calls[1].get("mode") == "generate"
    fell = res["mode"] == "generate" and "generate_fallback" in (res.get("donor") or {}).get("kind", "")
    ok = two and seq and fell and res["ok"] is True
    return ok, f"calls={len(spy.calls)} seq_edit→gen={seq} donor={(res.get('donor') or {}).get('kind')}"


# ── P7: нет ссылок живьём → generate ровно раз ──
def t7_live_no_donor_generate():
    spy = _ForgeSpy([_OK])
    prod = {"name": "Без фото", "sku": "ARB-3", "facts": {"вид": "нечто"}}
    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-test"), \
         _Patched(**{"pf.forge": spy}):
        res = pp.forge_card(prod, dry=False)
    ok = (len(spy.calls) == 1 and spy.calls[0].get("mode") == "generate"
          and spy.calls[0].get("source") in (None,) and res["mode"] == "generate")
    return ok, f"calls={len(spy.calls)} mode={spy.calls[0].get('mode') if spy.calls else '-'}"


# ── P8: денежный гейт — dry по умолчанию даже при ключе (наружу 0) ──
def t8_money_gate():
    net = []

    def _http(method, url, headers, body, timeout):
        net.append(url)
        return pf._Resp(200, {})

    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-test"), \
         _Patched(**{"pf._http_call": _http}):
        res = pp.forge_card(_PRODUCT)              # dry не передан → по умолчанию True
    ok = res["dry"] is True and len(net) == 0
    return ok, f"default_dry={res['dry']} сети={len(net)}"


# ── P9: доктор без ключа честен, значения ключей не печатает ──
def t9_doctor_no_key_honest():
    with _EnvForce(PHOTO_FORGE_PROVIDER=None, GEMINI_API_KEY=None, GOOGLE_API_KEY=None,
                   GOOGLE_AI_STUDIO_KEY=None, OPENROUTER_API_KEY=None, OPENAI_API_KEY=None,
                   NEUROAPI_API_KEY=None, RU_OPENAI_API_KEY=None,
                   FUSIONBRAIN_API_KEY=None, FUSIONBRAIN_SECRET_KEY=None):
        d = pp.doctor(probe=True)
    kes = d["key_env_set"]
    # все значения — bool/None (имена), НЕ реальные ключи; зонд пропущен без ключа
    only_flags = all(isinstance(v, bool) or v is None for v in kes.values())
    ok = (d["creds_present"] is False and d["ready_for_live"] is False
          and only_flags and d["probe"] and d["probe"]["ok"] is False)
    return ok, f"creds={d['creds_present']} ready={d['ready_for_live']} flags_only={only_flags}"


# ── P10: 0₽ зонд провайдера видит целевой слаг (google и openrouter) ──
def t10_doctor_probe():
    def _http_google(method, url, headers, body, timeout):
        return pf._Resp(200, {"models": [{"name": "models/gemini-2.5-flash-image"},
                                          {"name": "models/other"}]})

    def _http_or(method, url, headers, body, timeout):
        return pf._Resp(200, {"data": [{"id": "google/gemini-2.5-flash-image"}, {"id": "x/y"}]})

    with _EnvForce(PHOTO_FORGE_PROVIDER="google", GEMINI_API_KEY="AIza-TEST",
                   GOOGLE_API_KEY=None, GOOGLE_AI_STUDIO_KEY=None), \
         _Patched(**{"pf._http_call": _http_google}):
        dg = pp.doctor(probe=True)
    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-test"), \
         _Patched(**{"pf._http_call": _http_or}):
        do = pp.doctor(probe=True)
    ok = (dg["probe"]["ok"] is True and dg["probe"]["model_visible"] is True
          and do["probe"]["ok"] is True and do["probe"]["model_visible"] is True)
    return ok, f"google_visible={dg['probe'].get('model_visible')} or_visible={do['probe'].get('model_visible')}"


# ── P11: кривой товар (не dict) не роняет мост — деградируем сухо ──
def t11_nondict_product_graceful():
    net = []

    def _http(method, url, headers, body, timeout):
        net.append(url)
        return pf._Resp(200, {})

    outs = []
    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-test"), \
         _Patched(**{"pf._http_call": _http}):
        for bad in (None, "film.jpg", 42, [1, 2, 3]):
            r = pp.forge_card(bad, dry=True)          # публичный вход не должен падать
            outs.append(r["ok"] is True and r["dry"] is True and r["mode"] == "generate")
    ok = all(outs) and len(net) == 0
    return ok, f"кривых_входов_ок={sum(outs)}/4 сети={len(net)}"


# ── P12: доктор честен про ИЗОЛЯЦИЮ ключа (чужой OPENAI_API_KEY НЕ вооружает форж) ──
def t12_doctor_key_isolation():
    # foreign: только OPENAI_API_KEY при openrouter → кузница его ИГНОРИТ (изоляция органа):
    # форж реально обезоружен (creds=False, _openrouter_key=None), key_kind='none', live не готов, есть caveat.
    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY=None,
                   OPENAI_API_KEY="sk-anna-foreign", GEMINI_API_KEY=None,
                   GOOGLE_API_KEY=None, GOOGLE_AI_STUDIO_KEY=None,
                   NEUROAPI_API_KEY=None, RU_OPENAI_API_KEY=None,
                   FUSIONBRAIN_API_KEY=None, FUSIONBRAIN_SECRET_KEY=None):
        df = pp.doctor(probe=False)
        disarmed = (pf.creds_present() is False and pf._openrouter_key() is None)
    foreign_ok = (df["key_kind"] == "none" and df["ready_for_live"] is False
                  and df["creds_present"] is False and bool(df.get("caveat")) and disarmed)
    # native: OPENROUTER_API_KEY → готов к live даже без сети, без caveat
    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-native",
                   OPENAI_API_KEY=None, GEMINI_API_KEY=None,
                   GOOGLE_API_KEY=None, GOOGLE_AI_STUDIO_KEY=None,
                   NEUROAPI_API_KEY=None, RU_OPENAI_API_KEY=None,
                   FUSIONBRAIN_API_KEY=None, FUSIONBRAIN_SECRET_KEY=None):
        dn = pp.doctor(probe=False)
    native_ok = (dn["key_kind"] == "native" and dn["ready_for_live"] is True
                 and dn.get("caveat") is None)

    # даже со СТАБ-сетью foreign-only НЕ пролезает в live: зонд пропущен (creds=False), ложного апгрейда нет
    def _http_or(method, url, headers, body, timeout):
        return pf._Resp(200, {"data": [{"id": "google/gemini-2.5-flash-image"}]})

    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY=None,
                   OPENAI_API_KEY="sk-works-on-or", GEMINI_API_KEY=None,
                   GOOGLE_API_KEY=None, GOOGLE_AI_STUDIO_KEY=None,
                   NEUROAPI_API_KEY=None, RU_OPENAI_API_KEY=None,
                   FUSIONBRAIN_API_KEY=None, FUSIONBRAIN_SECRET_KEY=None), \
         _Patched(**{"pf._http_call": _http_or}):
        dp = pp.doctor(probe=True)
    no_false_upgrade = (dp["key_kind"] == "none" and dp["ready_for_live"] is False
                        and dp["probe"]["ok"] is False)
    ok = foreign_ok and native_ok and no_false_upgrade
    return ok, f"foreign→disarmed={bool(foreign_ok)} native→ready={native_ok} no_false_upgrade={no_false_upgrade}"


# ── P13: провенанс-гейт публикатора — URL только для СВОИХ пикселей ──
_OWN_OK = {"ok": True, "path": "/tmp/own_frame.png", "tier": "verified", "sent": True,
           "rights": {"level": "own_pixels", "clean": True}}


class _FakeHoster:
    """Фейковый хостер: put() отдаёт заданный URL (uploaded=True) без сети — для live-ветки P15."""
    def __init__(self, url="https://cdn.example/cards/deadbeef.png"):
        self._url = url
        self.calls = []

    def put(self, path, dry=True, content_type=None):
        self.calls.append((path, dry))
        if dry:
            return {"url": self._url, "object": "cards/deadbeef.png", "dry": True,
                    "uploaded": False, "would_upload": True, "why": "dry"}
        return {"url": self._url, "object": "cards/deadbeef.png", "dry": False,
                "uploaded": True, "why": "залито (fake)"}


def t13_publish_provenance_gate():
    own = pub.gate(_OWN_OK)                                            # свои пиксели + verified → пускаем
    deriv = pub.gate({**_OWN_OK, "rights": {"level": "derivative"}})   # производное → нет
    offc = pub.gate({**_OWN_OK, "tier": "off_canon"})                  # не verified → нет
    notok = pub.gate({**_OWN_OK, "ok": False})                         # не выкован → нет
    nopath = pub.gate({**_OWN_OK, "path": ""})                         # нет файла → нет
    ok = (own[0] is True and deriv[0] is False and offc[0] is False
          and notok[0] is False and nopath[0] is False
          and any("own_pixels" in s for s in deriv[1]))
    return ok, (f"own={own[0]} deriv={deriv[0]} off_canon={offc[0]} "
                f"notok={notok[0]} nopath={nopath[0]}")


def t14_publish_no_local_leak():
    # dry-годный кадр: гейт пройден, но без живого хостинга — urls ПУСТ, blocked, would_url (не локальный путь)
    res = pub.pictures_from_forge(_OWN_OK, hoster=pub.YandexObjectStorage(), dry=True)
    leak = any(_OWN_OK["path"] in u for u in res["urls"])
    would = res.get("would_url") or ""
    ok = (res["urls"] == [] and res["blocked"] is True and leak is False
          and would.startswith("https://") and _OWN_OK["path"] not in would)
    d = pub.pictures_from_forge({**_OWN_OK, "rights": {"level": "derivative"}}, dry=True)
    ok = ok and d["urls"] == [] and d["blocked"] is True
    return ok, f"urls={res['urls']} blocked={res['blocked']} leak={leak} would_https={would.startswith('https://')}"


def t15_hoster_dry_hermetic():
    net = []

    def _http(method, url, headers, body, timeout):    # хостер не должен ходить в сеть в dry — поймаем
        net.append(url)
        return pf._Resp(200, {})

    with _EnvForce(YC_BUCKET=None, YC_ACCESS_KEY_ID=None, YC_SECRET_KEY=None):
        h = pub.YandexObjectStorage()
        up1 = h.put("/tmp/own_frame.png", dry=True)
        up2 = h.put("/tmp/own_frame.png", dry=True)     # то же имя объекта (детерминизм по пути)
        ke = h.key_env()
        ready = h.ready()
    det = up1["object"] == up2["object"]
    flags_only = all(isinstance(v, bool) for v in ke.values())
    dry_safe = up1["uploaded"] is False and up1["would_upload"] is True
    fh = _FakeHoster()                                  # живой хостер (фейк) → реальный URL, blocked=False
    live = pub.pictures_from_forge(_OWN_OK, hoster=fh, dry=False)
    live_ok = (live["urls"] == [fh._url] and live["blocked"] is False
               and fh.calls and fh.calls[0][1] is False)
    ok = (det and flags_only and dry_safe and ready is False and len(net) == 0 and live_ok)
    return ok, (f"det={det} flags_only={flags_only} dry_safe={dry_safe} "
                f"ready={ready} live_ok={live_ok} сети={len(net)}")


def t16_write_merge_photo_urls():
    prod = {"name": "Плёнка защитная 6.7", "sku": "ARB-P", "price": 390,
            "pictures": ["http://donor/a.jpg", "http://donor/b.jpg"]}
    urls = ["https://cdn.example/mine.png", "http://donor/a.jpg"]   # один дубль с донором
    net = []

    def _http(method, url, headers, body, timeout):
        net.append(url)
        return pf._Resp(200, {})

    with _Patched(**{"pf._http_call": _http}):
        r = w.create_card(prod, photo_urls=urls, dry=True, commit=False)
    offer = (((r.get("payloads") or {}).get("step1") or {}).get("offerMappings") or [{}])[0].get("offer", {})
    pics = offer.get("pictures") or []
    lead = bool(pics) and pics[0] == "https://cdn.example/mine.png"   # наш кадр = главное фото
    dedup = pics.count("http://donor/a.jpg") == 1
    not_mutated = prod["pictures"] == ["http://donor/a.jpg", "http://donor/b.jpg"]
    big = w._merge_pictures([f"http://d/{i}.jpg" for i in range(40)], ["https://cdn.example/mine.png"])
    capped = len(big) == 30 and big[0] == "https://cdn.example/mine.png"
    bad = w.create_card("not-a-dict", photo_urls=urls, dry=True)     # не-dict не роняет
    bad_ok = bad.get("ok") is False
    ok = (lead and dedup and not_mutated and capped and bad_ok and len(net) == 0)
    return ok, (f"lead={lead} dedup={dedup} not_mutated={not_mutated} "
                f"capped={capped} nondict_ok={bad_ok} сети={len(net)}")


# ── P17: доктор — РОДНОЙ ключ ru_openai (neuroapi) → провайдер ru_openai, live-готов без сети, без caveat ──
def t17_doctor_ru_openai_native():
    with _EnvForce(PHOTO_FORGE_PROVIDER="ru_openai", NEUROAPI_API_KEY="sk-neuro-TEST",
                   RU_OPENAI_API_KEY=None, GEMINI_API_KEY=None, GOOGLE_API_KEY=None,
                   GOOGLE_AI_STUDIO_KEY=None, OPENROUTER_API_KEY=None, OPENAI_API_KEY=None):
        d = pp.doctor(probe=False)
    kes = d["key_env_set"]
    has_flags = ("NEUROAPI_API_KEY" in kes and kes["NEUROAPI_API_KEY"] is True
                 and "RU_OPENAI_API_KEY" in kes)
    ok = (d["provider"] == "ru_openai" and d["key_kind"] == "native"
          and d["ready_for_live"] is True and d.get("caveat") is None
          and d["creds_present"] is True and has_flags)
    return ok, (f"provider={d['provider']} kind={d['key_kind']} ready={d['ready_for_live']} "
                f"caveat_none={d.get('caveat') is None} flags={has_flags}")


# ── P18: canon пробрасывается товар→кузница (бронь ATLAS EDGE в dry-плане), default цел ──
def t18_canon_threads_to_forge():
    net = []

    def _http(method, url, headers, body, timeout):        # сухо: сети быть не должно — поймаем
        net.append(url)
        return pf._Resp(200, {})

    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-test"), \
         _Patched(**{"pf._http_call": _http}):
        rc = pp.forge_card(_PRODUCT, dry=True, canon=True)     # бронь ВКЛ → план приёмки = verify_canon
        rp = pp.forge_card(_PRODUCT, dry=True)                  # бронь по умолч. ВЫКЛ → прежнее поведение
    fc = rc.get("forge") or {}
    fp = rp.get("forge") or {}
    # canon=True реально долетел до кузницы: флаг поднят, план — verify_canon (белый фон + 4:5)
    canon_on = (fc.get("canon") is True and "4:5" in (fc.get("verify_plan") or "")
                and "verify_canon" in (fc.get("verify_plan") or ""))
    # default (canon не передан): старый план photo_hunter, без 4:5 — back-compat не тронут
    canon_off = (fp.get("canon") is False and "4:5" not in (fp.get("verify_plan") or "")
                 and "photo_hunter" in (fp.get("verify_plan") or ""))
    ok = canon_on and canon_off and len(net) == 0              # всё сухо (0 сети, 0₽)
    return ok, (f"canon_on={canon_on} canon_off={canon_off} "
                f"plan_c={(fc.get('verify_plan') or '')[:28]!r} сети={len(net)}")


# ── P19: ИСКАТЕЛЬ-ПЕРВЫМ — 'good' с чистого источника приклеивается напрямую (opt-in) ──
def t19_acquire_good_direct_attach():
    good = [{"url": "https://clean.example/g1.jpg", "verdict": "good"},
            {"url": "https://clean.example/g2.jpg", "verdict": "good"}]
    fs = _FindStub(good=good, discovered=5)
    with _Patched(**{"pp._hunter": (lambda: fs)}):
        r = pp.acquire_photos(_PRODUCT, dry=True, sources=("wildberries",),
                              attach_policy="attach_good_direct")
    ok = (r["ok"] is True and r["source"] == "finder"
          and r["photo_urls"] == [g["url"] for g in good]
          and r["pictures"] == r["photo_urls"] and r["forged"] is None
          and bool(fs.calls) and fs.calls[0]["sources"] == ("wildberries",))
    return ok, f"source={r['source']} urls={len(r['photo_urls'])} forged={r['forged']}"


# ── P20: ЗАКОН ЧЕСТНОСТИ — 'unknown' НИКОГДА не приклеивается сам; opt-in allow_unknown снимает замок ──
def t20_acquire_unknown_not_attached():
    unknown = [{"url": "https://shop.example/u1.jpg", "verdict": "unknown"}]
    cc = [{"url": "https://shop.example/u1.jpg", "clean": True}]
    # allow_unknown=False (умолч.): нет good → падаем в кузницу, unknown идёт ВХОДОМ, не приклеивается
    fs = _FindStub(unknown=unknown, clean_candidates=cc, discovered=3)
    spy = _ForgeCardSpy()
    with _Patched(**{"pp._hunter": (lambda: fs), "pp.forge_card": spy}):
        r = pp.acquire_photos(_PRODUCT, dry=True, attach_policy="attach_good_direct",
                              allow_unknown=False)
    fell = len(spy.calls) == 1 and r["source"] in ("forge", "forge_from_best")
    unknown_out = "https://shop.example/u1.jpg" not in (r["photo_urls"] or [])
    proposals_shown = len(r["proposals"]) == 1
    forge_input = spy.calls and spy.calls[0].get("urls") == ["https://shop.example/u1.jpg"]
    # opt-in allow_unknown=True: тот же unknown приклеивается напрямую (оператор снял замок ЯВНО)
    fs2 = _FindStub(unknown=unknown, clean_candidates=cc)
    with _Patched(**{"pp._hunter": (lambda: fs2)}):
        r2 = pp.acquire_photos(_PRODUCT, dry=True, attach_policy="attach_good_direct",
                               allow_unknown=True)
    explicit_optin = (r2["source"] == "finder"
                      and r2["photo_urls"] == ["https://shop.example/u1.jpg"])
    ok = fell and unknown_out and proposals_shown and bool(forge_input) and explicit_optin
    return ok, (f"source={r['source']} unknown_in={not unknown_out} proposals={len(r['proposals'])} "
                f"forge_in={bool(forge_input)} optin={explicit_optin}")


# ── P21: пусто у искателя → честный фолбэк на кузницу с нуля (source=forge, не молчание) ──
def t21_acquire_empty_forge_fallback():
    fs = _FindStub(discovered=0)
    spy = _ForgeCardSpy()
    with _Patched(**{"pp._hunter": (lambda: fs), "pp.forge_card": spy}):
        r = pp.acquire_photos(_PRODUCT, dry=True)         # дефолт forge_from_best
    ok = (len(spy.calls) == 1 and r["source"] == "forge"
          and spy.calls[0].get("prefer_clean") is True    # нечего доверять → кузнице искать чистое
          and r["proposals"] == [] and r["ok"] is True)
    return ok, (f"source={r['source']} calls={len(spy.calls)} "
                f"prefer_clean={spy.calls[0].get('prefer_clean') if spy.calls else '-'}")


# ── P22: ДЕФОЛТ forge_from_best — сырой good-URL НЕ приклеен, а перекован (pHash-закон моста) ──
def t22_acquire_forge_from_best_uniquifies():
    good = [{"url": "https://clean.example/g1.jpg", "verdict": "good"}]
    fs = _FindStub(good=good, discovered=2)
    spy = _ForgeCardSpy()
    with _Patched(**{"pp._hunter": (lambda: fs), "pp.forge_card": spy}):
        r = pp.acquire_photos(_PRODUCT, dry=True)         # дефолтная политика
    called = len(spy.calls) == 1
    raw_out = "https://clean.example/g1.jpg" not in (r["photo_urls"] or [])   # сырой кадр не в карточке
    forge_input = called and spy.calls[0].get("urls") == ["https://clean.example/g1.jpg"]
    no_rehunt = called and spy.calls[0].get("prefer_clean") is False          # best верифицирован
    ok = called and raw_out and forge_input and no_rehunt and r["source"] == "forge_from_best"
    return ok, (f"source={r['source']} raw_attached={not raw_out} forge_in={bool(forge_input)} "
                f"prefer_clean={spy.calls[0].get('prefer_clean') if called else '-'}")


# ── P23: СШИВКА С СИСТЕМОЙ — photo_urls искателя долетают в pictures[] карточки Маркета ──
def t23_acquire_feeds_create_card():
    good = [{"url": "https://clean.example/g1.jpg", "verdict": "good"},
            {"url": "https://clean.example/g2.jpg", "verdict": "good"}]
    fs = _FindStub(good=good, discovered=4)
    prod = {"name": "Плёнка X", "sku": "ARB-Q", "price": 420}
    net = []

    def _http(method, url, headers, body, timeout):
        net.append(url)
        return pf._Resp(200, {})

    with _Patched(**{"pp._hunter": (lambda: fs), "pf._http_call": _http}):
        acq = pp.acquire_photos(prod, dry=True, attach_policy="attach_good_direct")
        r = w.create_card(prod, photo_urls=acq["photo_urls"], dry=True, commit=False)
    offer = (((r.get("payloads") or {}).get("step1") or {}).get("offerMappings") or [{}])[0].get("offer", {})
    pics = offer.get("pictures") or []
    sink_ok = pics == [g["url"] for g in good]
    not_mutated = "pictures" not in prod                  # вызывающий товар не мутирован
    ok = sink_ok and not_mutated and len(net) == 0
    return ok, f"pics_in_card={len(pics)} sink_ok={sink_ok} not_mutated={not_mutated} сети={len(net)}"


# ── P24: живой путь инфографики при МЁРТВОЙ кузнице не падает и брендирует донора ──
def t24_live_infographic_dead_forge():
    """БАГ-РЕГРЕССИЯ: в живом пути forge_card блок инфографики переопределял отчётный словарь
    `base` через `base = fr.get("path")...` → `return dict(base, ...)` падал
    'NoneType' object is not iterable. Дry-путь баг не ловил (ранний return). Проверяем:
    кузница мертва (ok=False, 402-сим) + донор-URL жив → мост ОБЯЗАН взять донора, брендировать
    локально (0₽/PIL) и вернуть отчёт, а НЕ упасть. Инфографика-орган подменён фейком-приёмником."""
    seen = {}

    class _FakeInfo:
        _HAVE_PIL = True
        def compose_infographic(self, base, facts=None, brand=None, out_dir=None,
                                tag=None, dry=True, **k):
            seen["base_is_bytes"] = isinstance(base, (bytes, bytearray))
            seen["facts"] = dict(facts or {})
            seen["dry"] = dry
            return {"ok": True, "path": "/tmp/info_branded.jpg", "thumb": "/tmp/info_t.jpg",
                    "delivered": True,
                    "content": {"hero": "плёнка", "specs": [], "wordmark": "ATLAS EDGE"},
                    "why": "бренд готов"}

    spy = _ForgeSpy([_DONOR_FAIL])          # кузница мёртва: edit провал, без generate-отката (402)
    prod = {"name": "Плёнка рулон", "sku": "ARB-24",
            "url": "https://maker.example/film.jpg",
            "facts": {"вид": "плёнка", "ширина_см": 120}}
    with _EnvForce(PHOTO_FORGE_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-test"), \
         _Patched(**{"pf.forge": spy, "pp._infographic": (lambda: _FakeInfo()),
                     "pp._donor_bytes": (lambda url: b"\x89PNG fake-bytes")}):
        res = pp.forge_card(prod, dry=False, prefer_clean=False, infographic=True)
    info = res.get("infographic") or {}
    no_crash = info.get("ok") is True
    branded = (info.get("path") == "/tmp/info_branded.jpg"
               and (info.get("content") or {}).get("wordmark") == "ATLAS EDGE")
    took_donor = seen.get("base_is_bytes") is True
    hero_ok = (seen.get("facts") or {}).get("вид") == "плёнка"
    dry_false = seen.get("dry") is False
    forge_dead_honest = res.get("ok") is False and (res.get("forge") or {}).get("ok") is False
    ok = no_crash and branded and took_donor and hero_ok and dry_false and forge_dead_honest
    return ok, (f"no_crash={no_crash} branded={branded} донор-байты={took_donor} "
                f"hero={hero_ok} dry=False={dry_false} честно-402={forge_dead_honest}")


# ── P25: провязка — произведённая инфографика (0₽/PIL, derivative) ДОЛЕТАЕТ в photo_urls ──
def t25_acquire_infographic_reaches_photo_urls():
    """Инфографический кадр из forge_card был ТОЛЬКО в отчёте — в photo_urls не публиковался,
    значит до карточки не доезжал. Проверяем провязку: acquire_photos с infographic=True
    публикует кадр через публикатор (гейт осознанно открыт allow_derivative=True — отмашка
    оператора «сделал свою фирменную инфографику»; права derivative + tier verified)."""
    fs = _FindStub(discovered=0)
    inf = {"ok": True, "path": "/tmp/info_branded.jpg", "thumb": "/tmp/info_t.jpg",
           "cost_usd": 0.0, "content": {"hero": "плёнка", "wordmark": "ATLAS EDGE"},
           "why": "бренд поверх донора"}
    spy = _ForgeCardSpy({"ok": True, "mode": "edit", "dry": False,
                         "forge": {"ok": False, "why": "кузница 402"},
                         "infographic": inf})

    class _FakePub:
        def __init__(self):
            self.calls = []
        def pictures_from_forge(self, report, hoster=None, dry=True, allow_derivative=False):
            self.calls.append({"path": report.get("path"), "tier": report.get("tier"),
                               "rights": (report.get("rights") or {}).get("level"),
                               "allow_derivative": allow_derivative, "dry": dry})
            if (report.get("path") == "/tmp/info_branded.jpg"
                    and report.get("tier") == "verified"
                    and (report.get("rights") or {}).get("level") == "derivative"):
                return {"urls": ["https://cdn.example/info_sku_1.jpg"], "blocked": False}
            return {"urls": [], "blocked": True, "why": ["форж не публикуем"]}

    fp = _FakePub()
    with _Patched(**{"pp._hunter": (lambda: fs), "pp.forge_card": spy, "pp._publish": (lambda: fp)}):
        r = pp.acquire_photos({"name": "Плёнка", "sku": "ARB-25",
                               "url": "https://m.example/f.jpg"},
                              dry=False, infographic=True)
    urls = r.get("photo_urls") or []
    inf_url = "https://cdn.example/info_sku_1.jpg" in urls
    gate_opened = any(c.get("allow_derivative") and c.get("path") == "/tmp/info_branded.jpg"
                      and c.get("tier") == "verified" and c.get("rights") == "derivative"
                      for c in fp.calls)
    empty_forge_gave_nothing = "https://cdn.example/info_sku_1.jpg" in urls and len(urls) == 1
    ok = inf_url and gate_opened and empty_forge_gave_nothing
    return ok, (f"инфографика_в_photo_urls={inf_url} gate_allow_derivative={gate_opened} "
                f"только_инфографика={empty_forge_gave_nothing} urls={urls}")


TESTS = [
    ("P1  plan_wires_uniqueizer", t1_plan_wires_uniqueizer),
    ("P2  dry_hermetic", t2_dry_hermetic),
    ("P3  dry_generate_no_url", t3_dry_generate_no_url),
    ("P4  always_forge_law", t4_always_forge_law),
    ("P5  donor_ladder_pick", t5_donor_ladder_pick),
    ("P6  live_generate_fallback", t6_live_generate_fallback),
    ("P7  live_no_donor_generate", t7_live_no_donor_generate),
    ("P8  money_gate", t8_money_gate),
    ("P9  doctor_no_key_honest", t9_doctor_no_key_honest),
    ("P10 doctor_probe", t10_doctor_probe),
    ("P11 nondict_product_graceful", t11_nondict_product_graceful),
    ("P12 doctor_key_isolation", t12_doctor_key_isolation),
    ("P13 publish_provenance_gate", t13_publish_provenance_gate),
    ("P14 publish_no_local_leak", t14_publish_no_local_leak),
    ("P15 hoster_dry_hermetic", t15_hoster_dry_hermetic),
    ("P16 write_merge_photo_urls", t16_write_merge_photo_urls),
    ("P17 doctor_ru_openai_native", t17_doctor_ru_openai_native),
    ("P18 canon_threads_to_forge", t18_canon_threads_to_forge),
    ("P19 acquire_good_direct_attach", t19_acquire_good_direct_attach),
    ("P20 acquire_unknown_not_attached", t20_acquire_unknown_not_attached),
    ("P21 acquire_empty_forge_fallback", t21_acquire_empty_forge_fallback),
    ("P22 acquire_forge_from_best_uniquifies", t22_acquire_forge_from_best_uniquifies),
    ("P23 acquire_feeds_create_card", t23_acquire_feeds_create_card),
    ("P24 live_infographic_dead_forge", t24_live_infographic_dead_forge),
    ("P25 acquire_infographic_reaches_photo_urls", t25_acquire_infographic_reaches_photo_urls),
]


def main():
    print("🎯 PHOTO-PIPELINE ПРИЁМКА · ФОТО-КОНВЕЙЕР (мост товар→кадр, сухо, 0₽)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<26} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

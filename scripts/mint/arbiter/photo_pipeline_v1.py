#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ФОТО-КОНВЕЙЕР (PHOTO PIPELINE V1) — «под ключ»: товар → готовый кадр карточки за одну команду.

ЗАЧЕМ. Были три отдельных органа, но НИЧЕГО их не связывало:
  • `uniqueizer_v1.photo_transform_plan()` — строит ПЛАН операций (белый фон, снять чужой знак,
    сломать перцептивный хеш), но пиксели не крутит;
  • `photo_hunter_v1.hunt()` — ИЩЕТ чистый донорский кадр у первоисточника;
  • `photo_forge_v1.forge()` — КУЁТ пиксели через Nano Banana… но это был ЛИСТ: его никто не звал.
Этот модуль — МОСТ. Даёшь товар (факты + ссылки) → он берёт план у уникализатора, выбирает
лучший донорский кадр у искателя, зовёт кузницу и возвращает ЕДИНЫЙ честный отчёт. Оператору
достаточно вписать ключ провайдера в mint/.env и снять сухой гейт — вся цепь загорается сама.

ГЛАВНЫЙ ЗАКОН МОСТА (почему всегда куём, даже с чистым донором). Чистый донор снимает ЧУЖОЙ знак,
но НЕ ломает перцептивный хеш: если положить фото первоисточника как есть, маркетплейс приклеит
нашу карточку к чужой по pHash (см. `uniqueizer.collision_risk` рычаг photos_transformed). Значит
уникальный кадр = ВСЕГДА кузница. Донор лишь выбирает ЛУЧШИЙ вход для edit:
    чистый (провенанс) → непроверенный (есть картинка) → нет донора → generate с нуля.

ПЯТЬ ЗАКОНОВ КУЗНИЦЫ ЦЕЛЫ (мост их только оркеструет, не обходит):
  1. ДВОЙНОЙ ГЕЙТ dry→RUBICON. dry (по умолчанию) — 0₽ и 0 сетевых вызовов: показываем план,
     решение о доноре и ТОЧНЫЙ запрос кузницы, наружу НИЧЕГО. Живьём — только dry=False (отмашка).
  2. 200 ≠ УСПЕХ · 3. ретрай транзиторного · 4. честная граница прав · 5. честное «не знаю» —
     всё внутри forge(); мост их наследует и добавляет провенанс донора в отчёт.

stdlib-only, ленивый: грузится без сети/ключей/PIL/соседних органов (fail-soft) — сухой план живёт.
Секреты — только из gitignored .env через photo_forge (наружу лишь ИМЕНА переменных, не значения).
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import photo_forge_v1 as pf                      # noqa: E402  кузница — единственный жёсткий сосед


# ── Ленивые соседи (мост не падает, если органа нет: сухой план всё равно живёт) ─────
def _uniq():
    """Уникализатор (источник ПЛАНА операций). None → мост берёт дефолтные ops кузницы."""
    try:
        import uniqueizer_v1 as u                # noqa: F811
        return u
    except Exception:
        return None


def _hunter():
    """Искатель донора. Переиспользуем ленивый доступ кузницы (не заводим второй импорт)."""
    return pf._hunter()


def _publish():
    """Публикатор (own_pixels-гейт + хостер → https-URL для pictures[]). None → без URL-производителя."""
    try:
        import photo_publish_v1 as pub                # noqa: F811
        return pub
    except Exception:
        return None


def _infographic():
    """Фирменная инфографика (локальный PIL, 0₽/0 сети). None → брендировать нечем (честный отказ)."""
    try:
        import photo_infographic_v1 as info           # noqa: F811
        return info
    except Exception:
        return None


def _donor_bytes(url):
    """Донорский URL → байты (0₽ GET, как искатель). None → скачать не вышло.

    Для инфографики-фолбэка, когда кузница недоступна: брендируем найденный кадр напрямую.
    """
    if not url:
        return None
    h = pf._hunter()
    if h is None or not hasattr(h, "fetch_bytes"):
        return None
    try:
        raw, _mime = h.fetch_bytes(url)
        return raw
    except Exception:
        return None


# ── План: единый источник операций (уникализатор), иначе дефолт кузницы ──────────────
def plan_for(urls, watermark="own"):
    """ops+source_images для товара. Единый источник правды — uniqueizer.photo_transform_plan.

    Fail-soft: нет уникализатора → дефолтный план карточки кузницы (organ всё равно куёт корректно).
    """
    urls = [u for u in (urls or []) if u]
    u = _uniq()
    if u is not None:
        try:
            return u.photo_transform_plan(urls, watermark=watermark)
        except Exception:
            pass
    return {"source_images": urls, "ops": list(pf.DEFAULT_OPS),
            "executable_here": False, "note": "уникализатор недоступен — дефолтный план кузницы"}


def _product_urls(product, urls=None):
    """Собрать лестницу ссылок: явный аргумент → product['urls'] → [product['url']]. Первый = первоисточник."""
    if urls:
        return [u for u in urls if u]
    got = product.get("urls") or ([product.get("url")] if product.get("url") else [])
    return [u for u in got if u]


def _pick_donor(hunt_res):
    """Выбрать ЛУЧШИЙ донорский кадр для edit: чистый (провенанс) → непроверенный → нет.

    Возвращает (url|None, kind): 'clean' | 'unproven' | 'none'. 'bad' (не тот товар/чёрный хост)
    НИКОГДА не берём. Чистый = искатель доказал провенанс (verdict good).
    """
    good = hunt_res.get("good") or []
    unknown = hunt_res.get("unknown") or []
    if good and good[0].get("url"):
        return good[0]["url"], "clean"
    if unknown and unknown[0].get("url"):
        return unknown[0]["url"], "unproven"
    return None, "none"


# ── Мост: товар → готовый кадр ───────────────────────────────────────────────────────
def forge_card(product, urls=None, dry=True, prefer_clean=True, require_verified=False,
               out_dir=None, model=None, tag=None, canon=False, brand=None, infographic=False):
    """ПОЛНЫЙ МОСТ: план (уникализатор) + донор (искатель) → кадр (кузница). Один вызов «под ключ».

    product — товар SCOUT-формата: {name, sku, brand, facts:{...}, url|urls:[...]}.
    dry=True (умолч.) — 0₽/0 сети: план + решение о доноре + ТОЧНЫЙ запрос кузницы, наружу ничего.
    dry=False — живой кадр (тратит ₽/квоту, только по отмашке): искатель → лучший донор → forge.

    canon=True — БРОНЯ ATLAS EDGE: приёмка verify_canon (белый фон + 4:5); пробрасывается в кузницу,
    поэтому живой canon-форж без PIL честно откажется тратить ДО сети (гард в pf.forge). brand —
    фирменный стиль в промпте (None → дефолт, вкл). Оба по умолчанию сохраняют прежнее поведение.

    infographic=True — доп. фирменный инфографик-кадр (ЛОКАЛЬНО, PIL, 0₽/0 сети) поверх лучшего
    чистого кадра: «нашёл в интернете → взял → брендировал» — СВОИ слова оператора, и это ЗАКОННО
    (производное, уровень derivative; на боевую витрину пускается только allow_derivative=True).
    Мёртвая кузница (402/сеть) фото больше НЕ блокирует: брендируем найденный кадр напрямую.
    Дефолт off → обратная совместимость (регрессия цела).

    Возвращает ЕДИНЫЙ честный отчёт: provider, plan, donor{kind,url}, mode, forge(полный),
    path, rights, cost_usd + infographic{ok,path,thumb,cost_usd:0.0} (когда попросили).
    Без вранья про успех — тир и «не знаю» наследуются из кузницы.
    """
    product = product if isinstance(product, dict) else {}   # кривой товар не роняет мост — деградируем
    facts = product.get("facts") or {}
    urls = _product_urls(product, urls)
    plan = plan_for(urls)
    ops = plan.get("ops") or list(pf.DEFAULT_OPS)
    tag = tag or _slug(product.get("name") or product.get("sku") or "item")
    prov = pf._provider()

    base = {"product": product.get("name"), "sku": product.get("sku"), "provider": prov,
            "plan": {"ops": ops, "source_images": plan.get("source_images", urls),
                     "executable_here": plan.get("executable_here")}}

    # ── СУХОЙ ГЕЙТ: 0 сети. Показываем НАМЕРЕНИЕ (что бы сделали живьём) + запрос кузницы. ──
    if dry:
        mode = "edit" if urls else "generate"
        donor_kind = "would_hunt" if urls else "none"
        fr = pf.forge(source=(urls[0] if urls else None), facts=facts, ops=ops, mode=mode,
                      dry=True, model=model, out_dir=out_dir, tag=tag, canon=canon, brand=brand)
        info_intent = None
        if infographic:
            info_intent = {"ok": False, "path": None, "cost_usd": 0.0,
                           "why": ("намерение: локально брендировать лучший кадр (0₽, PIL) — "
                                   "запусти с dry=False по отмашке")}
        return dict(base, ok=True, dry=True, mode=mode,
                    donor={"kind": donor_kind, "url": (urls[0] if urls else None),
                           "candidates": len(urls)},
                    forge=fr, path=None, rights=fr.get("rights"),
                    est_cost_usd=fr.get("est_cost_usd"), infographic=info_intent,
                    note=("СУХОЙ ГЕЙТ: наружу ничего (0₽). Живьём: искатель нашёл бы лучший донор "
                          "из %d ссылок → кузница выковала бы уникальный кадр. Запусти с dry=False "
                          "по отмашке (нужен ключ провайдера в mint/.env)." % len(urls)))

    # ── ЖИВОЙ РЕЖИМ (отмашка): искатель → лучший донор → кузница. ──
    donor_url, donor_kind, hunt_summary = None, "none", None
    if prefer_clean and urls:
        h = _hunter()
        if h is not None:
            try:
                hr = h.hunt(urls, facts=facts, need=1)
                hunt_summary = {"got": hr.get("got"), "good": len(hr.get("good") or []),
                                "unknown": len(hr.get("unknown") or []),
                                "bad": len(hr.get("bad") or [])}
                donor_url, donor_kind = _pick_donor(hr)
            except Exception as e:
                hunt_summary = {"error": type(e).__name__}
        else:
            hunt_summary = {"error": "искатель недоступен"}
    elif urls:
        donor_url, donor_kind = urls[0], "unproven"   # искатель отключён: берём первоисточник как есть

    if donor_url:
        mode = "edit"
        fr = pf.forge(source=donor_url, facts=facts, ops=ops, mode="edit", dry=False, model=model,
                      require_verified=require_verified, out_dir=out_dir, tag=tag, canon=canon, brand=brand)
        # Донор не загрузился живьём → честный откат на generate (свои пиксели), а не молчаливый провал.
        if not fr.get("ok") and str(fr.get("why", "")).startswith("донор"):
            mode, donor_kind = "generate", donor_kind + "->generate_fallback"
            fr = pf.forge(facts=facts, ops=ops, mode="generate", dry=False, model=model,
                          require_verified=require_verified, out_dir=out_dir, tag=tag, canon=canon, brand=brand)
    else:
        mode = "generate"
        fr = pf.forge(facts=facts, ops=ops, mode="generate", dry=False, model=model,
                      require_verified=require_verified, out_dir=out_dir, tag=tag, canon=canon, brand=brand)

    # ── ИНФОГРАФИКА (локально, 0₽/0 сети): «нашёл → взял → брендировал» поверх лучшего кадра. ──
    # Кузница мёртва (402/сеть)? Не блокируемся — берём лучший донорский кадр и брендируем его
    # ПРЯМО сейчас (PIL рисует марку/факты; производное, derivative — законно с allow_derivative).
    info = None
    if infographic:
        info = {"ok": False, "path": None, "thumb": None, "cost_usd": 0.0, "why": "",
                "content": {"hero": None, "specs": [], "wordmark": None}}
        inf = _infographic()
        if inf is None or not inf._HAVE_PIL:
            info["why"] = "нет PIL в фото-venv — инфографику не рисуем (честно)"
        else:
            ibase = fr.get("path") if (fr.get("ok") and fr.get("path")) else None
            base_why = "поверх выкованного кадра (свои пиксели → бренд)"
            if not ibase and donor_url:
                ibase = _donor_bytes(donor_url)
                base_why = "поверх найденного донора (кузница недоступна → брендируем кадр напрямую)"
            if not ibase:
                info["why"] = "нет базового кадра для инфографики"
            else:
                try:
                    comp = inf.compose_infographic(ibase, facts=facts, brand=brand,
                                                   out_dir=out_dir, tag=tag, dry=False)
                    if comp and comp.get("ok"):
                        info = dict(info, ok=True, path=comp.get("path"), thumb=comp.get("thumb"),
                                    delivered=comp.get("delivered"),
                                    content=comp.get("content"),
                                    why="%s · %s" % (base_why, comp.get("why", "")))
                    else:
                        info["why"] = (comp or {}).get("why", "инфографика не вышла")
                except Exception as e:
                    info["why"] = "инфографика упала: %s: %s" % (type(e).__name__, e)

    return dict(base, ok=bool(fr.get("ok")), dry=False, mode=mode,
                donor={"kind": donor_kind, "url": donor_url, "hunt": hunt_summary},
                forge=fr, path=fr.get("path"), tier=fr.get("tier"),
                rights=fr.get("rights"), cost_usd=fr.get("cost_usd"),
                cost_source=fr.get("cost_source"), why=fr.get("why"),
                infographic=info,
                note=("уникальный кадр выкован (донор: %s). Права и тир — из кузницы, честно. "
                      "Инфографика: %s."
                      % (donor_kind, (info or {}).get("why") or "не запрошена"))
                if infographic else
                ("уникальный кадр выкован (донор: %s). Права и тир — из кузницы, честно."
                 % donor_kind))


def _slug(s):
    """Безопасный тег файла из имени товара (латиница/цифры/-)."""
    import re
    s = re.sub(r"[^\w\-]+", "-", str(s or "item").strip().lower(), flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s or "item")[:40]


# ── ИСКАТЕЛЬ-ПЕРВЫМ → КУЗНИЦА-ФОЛБЭК: товар (текст) → готовые pictures[] карточки ────────
def acquire_photos(product, dry=True, need=3, sources=("wildberries",),
                   attach_policy="forge_from_best", allow_unknown=False,
                   hoster=None, out_dir=None, model=None, canon=True, brand=None,
                   infographic=False):
    """ПРОИЗВОДИТЕЛЬ ФОТО ДЛЯ СИСТЕМЫ: товар → photo_urls[] под ymarket_write.create_card(photo_urls=).

    Замыкает орган-искатель на СИСТЕМУ: photo_hunter.find() становится ПЕРВЫМ источником фото
    (не заглохшая генерация), а кузница — честный фолбэк. Один вход даёт ровно то, что law-safe
    кладётся в карточку Маркета; producer-only — сам НИЧЕГО не публикует (RUBICON цел).

    ДВА НЕРУШИМЫХ ЗАКОНА НА ГРАНИЦЕ ПРИКЛЕИВАНИЯ (душа искателя — здесь НЕ обходятся):
      • ЧЕСТНОСТЬ. Авто-приклеиваем напрямую ТОЛЬКО find()['good'] (host∈known_clean_shops + зрение —
        единственный provenance-путь к 'good'). 'unknown'/clean_candidates НИКОГДА не попадают в
        photo_urls сами — только в proposals для взгляда оператора (allow_unknown=True снимает
        замок ЯВНО). known_clean_shops сейчас ПУСТ → 'good' недостижим → дефолт ВСЕГДА падает в
        кузницу (safe-empty: без слова оператора прямого приклеивания не случится).
      • pHash-ЗАКОН МОСТА. Сырой донорский кадр нельзя класть как есть — МП склеит нашу карточку с
        чужой по pHash. Поэтому дефолт attach_policy='forge_from_best': лучший найденный кадр идёт
        ВХОДОМ в кузницу (уникализация пикселей), а не прямиком в карточку. Прямое приклеивание
        raw-URL — только явный opt-in attach_policy='attach_good_direct' (оператор берёт pHash-риск
        на себя, и лишь для 'good' = реестр-чистого хоста).

    dry=True (умолч.) — кузница 0₽/0 сети наружу и 0 заливки; find() СЕТЕВОЙ, но это ЧТЕНИЕ
    (0 токенов/0₽, разрешённая read-плоскость RUBICON) — при dry лишь показываем НАМЕРЕНИЕ+proposals.
    dry=False (отмашка) — живой форж + заливка на хостинг; photo_urls строятся ТОЛЬКО из СВОИХ
    пикселей (own_pixels+verified+живой хостинг), иначе пусто (честная деградация, не молчание).

    Возвращает: {product, sku, query, source:'finder'|'forge_from_best'|'forge',
    pictures:[url], photo_urls:[url], proposals:[...], find:{сводка}, forged:<forge_card|None>,
    dry, ok, note}. photo_urls == pictures — то, что кладётся в create_card(photo_urls=...).
    """
    product = product if isinstance(product, dict) else {}
    facts = product.get("facts") or {}
    query = str(product.get("name") or product.get("sku") or "").strip()

    # ── ЧИТАЮЩИЙ ИСКАТЕЛЬ (read-плоскость: 0 токенов/0₽; работает и в dry — это суть органа) ──
    fr = {"good": [], "unknown": [], "bad": [], "clean_candidates": [], "discovered": 0}
    h = _hunter()
    if h is not None and query:
        try:
            fr = h.find(query, facts=facts, need=need, sources=tuple(sources))
        except Exception as e:
            fr = dict(fr, error=type(e).__name__)
    good_urls = [r.get("url") for r in (fr.get("good") or []) if r.get("url")]
    unknown_urls = [r.get("url") for r in (fr.get("unknown") or []) if r.get("url")]
    proposals = fr.get("clean_candidates") or []
    find_summary = {"query": query, "discovered": fr.get("discovered"),
                    "good": len(good_urls), "unknown": len(unknown_urls),
                    "bad": len(fr.get("bad") or []), "clean_candidates": len(proposals),
                    "error": fr.get("error")}
    base = {"product": product.get("name"), "sku": product.get("sku"), "query": query,
            "find": find_summary, "proposals": proposals, "dry": dry}

    # ── ЗАКОН ЧЕСТНОСТИ: прямое приклеивание raw-URL — ТОЛЬКО opt-in и ТОЛЬКО 'good' (+unknown если явно) ──
    if attach_policy == "attach_good_direct":
        attachable = list(good_urls) + (unknown_urls if allow_unknown else [])
        attachable = attachable[:need]
        if attachable:
            return dict(base, ok=True, source="finder", pictures=attachable,
                        photo_urls=attachable, forged=None,
                        note=("ИСКАТЕЛЬ-ПЕРВЫМ: %d готовых кадров с чистого источника приклеены "
                              "напрямую (opt-in attach_good_direct; pHash-риск на операторе)."
                              % len(attachable)))
        # приклеивать нечего → честно падаем в кузницу (не молчим)

    # ── ФОЛБЭК (дефолт, law-safest): лучший найденный кадр → ВХОД кузницы; иначе куём с нуля ──
    best = good_urls[:1] or ([proposals[0]["url"]] if (proposals and proposals[0].get("url")) else [])
    urls_for_forge = best or _product_urls(product)
    forged = forge_card(product, urls=(urls_for_forge or None), dry=dry,
                        prefer_clean=not bool(best),      # best уже верифицирован → не пере-хантим
                        out_dir=out_dir, model=model, canon=canon, brand=brand,
                        infographic=infographic)
    photo_urls = []
    pub = _publish()
    if pub is not None:
        pr = pub.pictures_from_forge(forged.get("forge") or {}, hoster=hoster, dry=dry)
        photo_urls = pr.get("urls") or []
        # ИНФОГРАФИКА долетает до карточки: произведённый кадр (derivative, 0₽/PIL) публикуем
        # наравне с форжевым — гейт осознанно открыт allow_derivative=True (отмашка оператора:
        # «сделал свою фирменную инфографику» = наш пиксель-слой поверх донора, pHash уникален).
        info = forged.get("infographic") or {}
        if (info.get("ok") is True and info.get("path")):
            info_report = {"ok": True, "path": info.get("path"),
                           "tier": "verified", "rights": {"level": "derivative"}}
            ipr = pub.pictures_from_forge(info_report, hoster=hoster, dry=dry,
                                          allow_derivative=True)
            photo_urls = list(photo_urls) + (ipr.get("urls") or [])
    source = "forge_from_best" if best else "forge"
    return dict(base, ok=bool(forged.get("ok")), source=source,
                pictures=photo_urls, photo_urls=photo_urls, forged=forged,
                infographic=(forged.get("infographic") or None),
                note=("ИСКАТЕЛЬ→КУЗНИЦА: %s. photo_urls только из СВОИХ пикселей "
                      "(own_pixels+verified+живой хостинг), иначе пусто. proposals оператору: %d. "
                      "Инфографика: %s."
                      % ("лучший найденный кадр ушёл входом в кузницу" if best
                         else "найденного кадра нет — куём с нуля", len(proposals),
                         (forged.get("infographic") or {}).get("why") or "не запрошена")))


# ── Доктор «под ключ»: единый паспорт + 0₽ зонд АКТИВНОГО провайдера ──────────────────
def _key_kind(prov):
    """Каким РОДНЫМ ключом вооружён активный провайдер: 'native' | 'none'.

    native — родной ключ провайдера (openrouter: OPENROUTER_API_KEY; google: GEMINI/GOOGLE/AI_STUDIO;
             ru_openai: NEUROAPI_API_KEY/RU_OPENAI_API_KEY).
    none   — родного ключа нет → только сухой режим (0₽).

    Изоляция органа (решение оператора): кузница НЕ использует чужой OPENAI_API_KEY соседа
    (см. photo_forge_v1._openrouter_key). Поэтому лишний OPENAI_API_KEY НЕ делает провайдер боевым —
    он для нас просто 'none'; doctor лишь добавит caveat, что видел его и намеренно проигнорировал.
    """
    if prov == "google":
        return "native" if (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                            or os.getenv("GOOGLE_AI_STUDIO_KEY")) else "none"
    if prov == "ru_openai":
        return "native" if (os.getenv("NEUROAPI_API_KEY") or os.getenv("RU_OPENAI_API_KEY")) else "none"
    return "native" if os.getenv("OPENROUTER_API_KEY") else "none"


def doctor(probe=True):
    """Готовность цепи к живому кадру. probe=True — 0₽ read-зонд активного провайдера (сеть).

    Никогда не печатает ЗНАЧЕНИЯ ключей — только какие ИМЕНА переменных заданы (bool). Один
    взгляд говорит: какой провайдер активен, РОДНОЙ ли ключ, виден ли слаг модели, готовы ли соседи.

    ЧЕСТНОСТЬ arming-сигнала: ready_for_live=True только при РОДНОМ ключе ИЛИ прошедшем 0₽ зонде.
    Чужой OPENAI_API_KEY кузница НЕ использует (изоляция органа) — он не вооружает и даёт caveat.
    """
    prov = pf._provider()
    kind = _key_kind(prov)
    caps = pf.capabilities()
    ignored_foreign = (prov == "openrouter" and kind == "none"
                       and bool(os.getenv("OPENAI_API_KEY")))
    key_names = {
        "GEMINI_API_KEY": bool(os.getenv("GEMINI_API_KEY")),
        "GOOGLE_API_KEY": bool(os.getenv("GOOGLE_API_KEY")),
        "GOOGLE_AI_STUDIO_KEY": bool(os.getenv("GOOGLE_AI_STUDIO_KEY")),
        "OPENROUTER_API_KEY": bool(os.getenv("OPENROUTER_API_KEY")),
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        "NEUROAPI_API_KEY": bool(os.getenv("NEUROAPI_API_KEY")),
        "RU_OPENAI_API_KEY": bool(os.getenv("RU_OPENAI_API_KEY")),
        "PHOTO_FORGE_PROVIDER": os.getenv("PHOTO_FORGE_PROVIDER") or None,
    }
    out = {
        "provider": prov,
        "model": pf._default_model(),
        "base_url": pf._base_url(),
        "endpoint": pf._endpoint_path(pf._default_model()),
        "creds_present": pf.creds_present(),
        "key_kind": kind,                  # native | none
        "key_env_set": key_names,          # ИМЕНА → bool, НЕ значения
        "capabilities": caps,
        "neighbors": {"uniqueizer": _uniq() is not None, "hunter": _hunter() is not None},
        "caveat": ("виден OPENAI_API_KEY, но ARBITER-кузница его НЕ использует (изоляция органа: "
                   "чужой ключ соседа wavecore-bot/ANNA или ключ api.openai.com даст 401 на openrouter.ai). "
                   "Впиши РОДНОЙ OPENROUTER_API_KEY в mint/.env — иначе openrouter обезоружен."
                   if ignored_foreign else None),
        "probe": None,
    }
    if probe and pf.creds_present():
        out["probe"] = _probe_provider(prov)
    elif probe:
        out["probe"] = {"ok": False, "why": "нет ключа — живой зонд пропущен (впиши ключ в mint/.env)"}
    # Готовность честно: РОДНОЙ ключ ИЛИ 0₽ зонд подтвердил слаг. Чужой OPENAI_API_KEY (kind=none) — НЕ готов.
    probe_ok = bool(out["probe"] and out["probe"].get("ok") and out["probe"].get("model_visible"))
    out["ready_for_live"] = (kind == "native") or probe_ok
    return out


def _probe_provider(prov):
    """0₽ read-зонд через ТОТ ЖЕ сетевой шов кузницы (models.list). Проходит зонд → пройдёт и live-auth.

    Ничего не генерит (не тратит квоту генерации). Ловит неверный ключ/слаг/RU-egress ДО первого кадра.
    """
    try:
        resp = pf._request("GET", "/models")
    except pf.ForgeHTTPError as e:
        return {"ok": False, "status": e.status, "why": "шлюз отбил (ключ/права/egress?)"}
    except Exception as e:
        return {"ok": False, "why": "сеть недоступна: %s (RU-egress к провайдеру?)" % type(e).__name__}
    want = pf._default_model()
    names = []
    try:
        if prov == "google":
            for m in (resp.get("models") or []):
                nm = (m.get("name") or "").split("/")[-1]
                names.append(nm)
        else:
            for m in (resp.get("data") or resp.get("models") or []):
                names.append(m.get("id") or m.get("name") or "")
    except Exception:
        pass
    seen = any(want in (n or "") for n in names)
    return {"ok": True, "model_visible": seen, "target": want,
            "models_count": len(names),
            "hint": None if seen else "целевой слаг не виден в каталоге — уточни модель"}


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="ФОТО-КОНВЕЙЕР V1 «под ключ» — товар → готовый кадр карточки одной командой")
    ap.add_argument("--doctor", action="store_true", help="проверить готовность цепи (0₽ зонд провайдера)")
    ap.add_argument("--no-net", action="store_true", help="доктор без сетевого зонда")
    ap.add_argument("--demo", action="store_true", help="прогнать демо-товар (плёнка) через мост")
    ap.add_argument("--acquire", action="store_true",
                    help="ИСКАТЕЛЬ-ПЕРВЫМ: товар→готовые pictures[] (find→кузница-фолбэк); dry без --live")
    ap.add_argument("--sources", default="wildberries",
                    help="добытчики искателя через запятую: wildberries[,open_images]")
    ap.add_argument("--attach-direct", action="store_true",
                    help="opt-in: приклеить raw-URL чистого источника напрямую (pHash-риск на операторе)")
    ap.add_argument("--product", default="", help="товар как JSON-строка")
    ap.add_argument("--product-file", default="", help="файл с товаром (JSON)")
    ap.add_argument("--url", action="append", default=[], help="ссылка-источник (можно повторять)")
    ap.add_argument("--live", action="store_true", help="БОЕВОЙ прогон (тратит ₽). Без него — dry (0₽)")
    ap.add_argument("--require-verified", action="store_true", help="принимать только verified")
    ap.add_argument("--canon", action="store_true",
                    help="БРОНЯ ATLAS EDGE: verify_canon (белый фон+4:5); живьём без PIL — честный отказ ДО траты")
    ap.add_argument("--out", default="", help="папка для выходного файла")
    ap.add_argument("--model", default="", help="слаг модели (по умолч. Nano Banana активного провайдера)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.doctor:
        d = doctor(probe=not args.no_net)
        if args.json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            print("ФОТО-КОНВЕЙЕР · доктор готовности:")
            print("   провайдер:  %s  · модель: %s" % (d["provider"], d["model"]))
            print("   ключ есть:  %s (%s)  · готов к live: %s"
                  % (d["creds_present"], d["key_kind"], d["ready_for_live"]))
            if d.get("caveat"):
                print("   ⚠  %s" % d["caveat"])
            print("   соседи:     уникализатор=%s · искатель=%s"
                  % (d["neighbors"]["uniqueizer"], d["neighbors"]["hunter"]))
            print("   ключ-ENV (имена→задан):")
            for k, v in d["key_env_set"].items():
                print("       %-22s %s" % (k, v))
            if d.get("probe") is not None:
                print("   зонд:", json.dumps(d["probe"], ensure_ascii=False))
        return 0 if d["creds_present"] else 1

    product = None
    if args.product_file:
        product = json.loads(Path(args.product_file).read_text(encoding="utf-8"))
    elif args.product:
        product = json.loads(args.product)
    elif args.demo:
        product = {"name": "Плёнка воздушно-пузырьковая 2-слойная, рулон", "sku": "ARB-DEMO-1",
                   "brand": "", "url": "https://example.com/film.jpg",
                   "facts": {"вид": "воздушно-пузырьковая плёнка в рулоне",
                             "ширина_см": 120, "пузырёк_мм": 30}}

    if product is None:
        # Без товара — паспорт + подсказка (turnkey: видно, что вписать и чем запустить).
        d = doctor(probe=False)
        print("ФОТО-КОНВЕЙЕР V1 «под ключ». Нет товара — вот готовность:")
        print("   провайдер: %s · ключ: %s · соседи: у=%s и=%s"
              % (d["provider"], d["creds_present"],
                 d["neighbors"]["uniqueizer"], d["neighbors"]["hunter"]))
        print("   запусти:  python3 photo_pipeline_v1.py --demo            # сухой прогон демо (0₽)")
        print("             python3 photo_pipeline_v1.py --doctor          # проверить ключ/провайдера")
        print("             python3 photo_pipeline_v1.py --demo --live     # живой кадр (по отмашке, ₽)")
        return 0

    if args.acquire:
        # ИСКАТЕЛЬ-ПЕРВЫМ → готовые pictures[] под create_card(photo_urls=). dry без --live.
        srcs = tuple(s.strip() for s in (args.sources or "wildberries").split(",") if s.strip())
        ar = acquire_photos(product, dry=not args.live, sources=srcs,
                            attach_policy=("attach_good_direct" if args.attach_direct else "forge_from_best"),
                            out_dir=args.out or None, model=args.model or None, canon=args.canon)
        if args.json:
            print(json.dumps(ar, ensure_ascii=False, indent=2))
            return 0 if ar.get("ok") else 1
        print("товар: %s · источник: %s · dry: %s · ok: %s"
              % (ar.get("product"), ar.get("source"), ar.get("dry"), ar.get("ok")))
        print("   искатель:", json.dumps(ar.get("find"), ensure_ascii=False))
        print("   photo_urls (в карточку):", ar.get("photo_urls"))
        print("   proposals оператору:", len(ar.get("proposals") or []))
        print("   ", ar.get("note"))
        return 0 if ar.get("ok") else 1

    res = forge_card(product, urls=args.url or None, dry=not args.live,
                     require_verified=args.require_verified, out_dir=args.out or None,
                     model=args.model or None, canon=args.canon)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1
    print("товар: %s · провайдер: %s" % (res.get("product"), res.get("provider")))
    print("   план ops:", res["plan"]["ops"])
    print("   режим: %s · донор: %s · dry: %s · ok: %s"
          % (res.get("mode"), (res.get("donor") or {}).get("kind"), res.get("dry"), res.get("ok")))
    if res.get("dry"):
        print("   запрос кузницы:", json.dumps(res["forge"].get("request"), ensure_ascii=False))
        print("   ", res.get("note"))
    else:
        print("   тир: %s · путь: %s · ₽: %s" % (res.get("tier"), res.get("path"), res.get("cost_usd")))
        if res.get("why"):
            print("   почему:", res["why"])
    r = res.get("rights") or {}
    print("   права: %s — %s" % (r.get("level"), r.get("note")))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(_main())

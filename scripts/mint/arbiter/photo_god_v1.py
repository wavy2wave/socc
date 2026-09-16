#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОРГАН «РУКА-БОГА» (photo_god_v1) — автономная замена водяночных фото на фирменные кадры ATLAS EDGE.

ЗАЧЕМ. Живая витрина плёночного магазина (atlas-express-film) держит на карточках ЧУЖИЕ фото донора
(shop.cargo-avto.ru/.../watermark/... или avatars.mds.yandex.net) — водяные знаки, чужие рамки, логотипы
магазина. «РУКА-БОГА» чинит это сама: для каждой карточки из БИБЛИОТЕКИ товаров читает ЖИВОЕ состояние
кабинета, если на карточке чужой кадр — ВЫКУЁТ свой фирменный (провайдер генерации, canon ATLAS EDGE),
ЗАЛИВАЕТ на Yandex Object Storage, ЗАМЕНЯЕТ pictures[] целиком (чужое фото исчезает), и СВЕРЯЕТ
прочтением, что первое фото = наш URL и чужих в наборе нет.

ЗАКОНЫ (покрыты логикой):
  PG1 СУХОЙ ГЕЙТ: --dry (по умолчанию) — 0₽ наружу: честный план «что бы выковали / что заменили /
      кто заблокирован и почему». Живой режим — только по --live (отмашка оператора).
  PG2 БРОНЯ-ГАРД (BONE-GUARD): живьём, если нет PIL ИЛИ нет ключа активного провайдера ИЛИ не готов
      хостинг — ОТКАЗ ДО траты ₽, ничего не выковываем вслепую (verify_canon непроверяем без PIL).
  PG3 ЗАКОН ПРОВЕНАНСА: на боевую витрину только СВОИ пиксели (own_pixels) + tier=verified + есть файл
      (photo_publish.gate). Всё, что гейт не пропустил, — ЧЕСТНЫЙ блок с причиной, НЕ тихий пропуск.
  PG4 БРЕНД-ЗАМОК ATLAS EDGE: форж generate + canon=True + brand=True — белый фон #FFFFFF, товар крупно
      в центре (≈85% высоты), 4:5, без текста/логотипов; плёнка: рулон, пузырьки, прозрачная, светлый фон.
  PG5 ЗАМЕНА ЦЕЛИКОМ: offer-update pictures[] = [наш URL] (не prepend) — старые водяночные URL удаляются,
      главное фото = наш стиль.
  PG6 СВЕРКА ЧТЕНИЕМ: после замены живой read (offer-mappings) — n_pics>=1 И первое = storage.yandexcloud.net
      И чужих URL нет в наборе. Честный PASS/FAIL (200 ≠ успех: читаем результат, не статус).
  PG7 РЕЕСТР: каждая строка dry/live пишется в runtime/photo_god/<store>/<дата>.jsonl; библиотека получает
      n_photos + событие 'photo_god'; руб-расход суммируется по фактическому провайдеру и печатается в конце.

RUBICON: скрипт сам НИЧЕГО не пишет на Маркет и не тратит ₽ без --live. `--live` — боевой ход, только
по слову оператора. Хостинг/форж-ключи — из mint/.env (gitignored).

Запуск:
  python3 photo_god_v1.py                    # СУХОЙ ПЛАН (0₽): что бы заменили на 33 карточках
  python3 photo_god_v1.py --store <slug>     # другой магазин (по умолчанию atlas-express-film)
  python3 photo_god_v1.py --live             # БОЕВОЙ: форж → хостинг → замена фото → сверка чтением
"""
from __future__ import annotations

import os
import sys
import json
import re
import time
import pathlib
import argparse
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

DEFAULT_STORE = "atlas-express-film"
OUR_HOST = "storage.yandexcloud.net"            # канон хостинга ATLAS EDGE (см. YC_PUBLIC_BASE/бакет)
RUB_PER_USD = 90.0                              # курс для честного итога ₽ (env RUB_PER_USD перекрывает)

LEDGER_ROOT = HERE / "runtime/photo_god"

# Поля живого оффера, которые offer-mappings/update принимает (белый список). Всё, что вне списка
# (campaigns/cardStatus/mediaFiles — read-only ответ кабинета), назад НЕ шлём.
_WRITABLE = ("offerId", "name", "type", "boxCount", "basicPrice", "vendor", "vendorCode",
             "barcodes", "description", "pictures", "weightDimensions", "manufacturerCountries",
             "videos", "manuals", "marketCategoryId", "category")


# ── env / утилиты ──────────────────────────────────────────────────────────────

def _rub_rate():
    try:
        return float(os.getenv("RUB_PER_USD") or RUB_PER_USD)
    except (TypeError, ValueError):
        return RUB_PER_USD


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _is_our(url):
    """URL — наш хостинг (storage.yandexcloud.net)? Чужое → кандидат на замену (водяночное фото)."""
    if not isinstance(url, str) or not url.strip():
        return False
    return url.split("://", 1)[-1].split("/", 1)[0].rstrip("/") == OUR_HOST


def _donor_phash(pics, dry):
    """phash донорского кадра карточки — для форжа (проверка «достаточно непохож»).

    Локальный кеш runtime/photo_clean/{pid}.jpg (0 сети, из прежнего скачивания донора); если файла
    нет и режим живой — скачиваем watermark URL с сайта донора и кладём в кеш. В сухом режиме НЕ
    ходим в сеть (сухой гейт форжа не проверяет distinct — donor_phashes ему не нужен).
    """
    import photo_hunter_v1 as H
    if not pics:
        return None
    for url in pics:
        m = re.search(r"watermark/(\d+)__", url or "")
        if not m:
            continue
        pid = m.group(1)
        local = HERE / "runtime" / "photo_clean" / f"{pid}.jpg"
        raw = None
        if local.exists():
            raw = local.read_bytes()
        elif not dry:
            try:
                import urllib.request
                with urllib.request.urlopen(url, timeout=20) as r:
                    raw = r.read()
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(raw)
            except Exception:
                raw = None
        if raw:
            ph = H.phash(raw)
            if ph:
                return ph
    return None


def _store_profile(store):
    """runtime/cycle1/stores.json → профиль магазина {business_id, campaign_id, ...}. Не найден → None."""
    try:
        doc = json.loads((HERE / "runtime/cycle1/stores.json").read_text(encoding="utf-8"))
        stores = doc.get("stores", doc) if isinstance(doc, dict) else doc
        return (stores or {}).get(store)
    except Exception:
        return None


# ── факты для кузницы (BRAND LOCK — плёнка) ───────────────────────────────────

def _build_facts(rec, film_facts):
    """Библиотечная запись → факты товара для forge. Известные 4 pid → богатые факты FILM_FACTS;
    остальные рулоны — честный generic по сути (рулон пузырьковой плёнки) + габариты посылки (shape-hint)."""
    pid = str(rec.get("donor_pid") or "")
    if pid in film_facts:
        return film_facts[pid]
    facts = {
        "вид": "воздушно-пузырьковая плёнка в рулоне",
        "форма": "рулон прозрачной плёнки с воздушными пузырьками",
        "материал": "прозрачный полиэтилен",
        "цвет": "прозрачный",
        "применение": "упаковка хрупких товаров и защита при перевозке",
    }
    dims = rec.get("dims")
    if isinstance(dims, dict):
        sides = [dims.get(k) for k in ("length", "width", "height")]
        if all(isinstance(x, (int, float)) and x > 0 for x in sides):
            facts["размеры"] = "×".join("%g" % x for x in sides)
    return facts


# ── чтение кабинета (READ, 0₽) ─────────────────────────────────────────────────

def _read_cabinet(business_id):
    """POST businesses/{bid}/offer-mappings → {offerId: offer_body}. Сеть упала → (None, причина).

    Читаем ЧАСТОТОЙ до лимита 200 (в кабинете 40 офферов). body={} — вся витрина. 0₽, read-only."""
    try:
        import ymarket_hands_v1 as H
        data = H._request("POST", f"/businesses/{business_id}/offer-mappings", body={},
                          params={"limit": 200})
    except Exception as e:                          # fail-soft: честный блок, без traceback
        return None, "%s: %s" % (type(e).__name__, e)
    out = {}
    for m in (data.get("result", {}).get("offerMappings") or []):
        off = m.get("offer") or {}
        oid = str(off.get("offerId") or "")
        if oid:
            out[oid] = off
    return out, None


# ── БРОНЯ-ГАРД ────────────────────────────────────────────────────────────────

def _bone_guard(live):
    """Список блокеров живого режима. Пусто = можно жить (тратить ₽ осознанно). dry → всегда [].

    PG2: без PIL verify_canon не измерит белый фон + 4:5 (форж canon и так отказал бы ДО сети,
    но мы отказываем ДО ПРОГОНА — зачем начинать, если каждый SKU всё равно упрётся в одну стену);
    без ключа генерации — нечего рисовать; без готового хостинга — кадр некуда залить (форж был бы
    потрачен впустую). ВСЁ ДО ТРАТЫ."""
    if not live:
        return []
    blockers = []
    try:
        import photo_forge_v1 as F
        if not F._have_pil():
            blockers.append("нет PIL в фото-venv (~/.venvs/photoforge) — приёмка канона (белый фон + 4:5) "
                            "непроверяема, живой canon-форж запрещён")
        if not F.creds_present():
            blockers.append("нет ключа активного провайдера генерации (PHOTO_FORGE_PROVIDER + "
                            "RU_OPENAI_API_KEY/… — впиши в mint/.env)")
    except Exception as e:                          # fail-soft: даже кривой импорт не даёт живого прогона
        blockers.append("кузница недоступна: %s: %s" % (type(e).__name__, e))
    try:
        import photo_publish_v1 as P
        hoster = P.YandexObjectStorage()
        if not hoster.ready():
            blockers.append("хостинг Yandex Object Storage не готов (YC_BUCKET/YC_ACCESS_KEY_ID/"
                            "YC_SECRET_KEY) — заливать выкованное некуда")
    except Exception as e:
        blockers.append("публикатор недоступен: %s: %s" % (type(e).__name__, e))
    return blockers


# ── замена + сверка ────────────────────────────────────────────────────────────

def _replace_pictures(business_id, live_offer, new_urls, dry=True):
    """offer-mappings/update с pictures[] = [наши URL] целиком. Старые водяночные URL исчезают (PG5).

    Оффер копируем из ЖИВОГО тела (name/basicPrice/vendor/barcodes/description/… байт-в-байт), только
    pictures заменяем — никаких побочных правок живой карточки. dry → точный payload без отправки."""
    off = {k: v for k, v in (live_offer or {}).items() if k in _WRITABLE}
    off["pictures"] = list(new_urls)
    payload = {"offerMappings": [{"offer": off}]}
    oid = off.get("offerId")
    if dry:
        return {"ok": True, "dry": True, "offer_id": oid, "payload": payload,
                "pictures_old": (live_offer or {}).get("pictures") or [],
                "pictures_new": off["pictures"]}
    try:
        import ymarket_hands_v1 as H
        resp = H.update_offer_mappings(business_id, [{"offer": off}])
    except (ImportError, Exception) as e:
        return {"ok": False, "dry": False, "offer_id": oid,
                "errors": ["transport: %s: %s" % (type(e).__name__, e)], "payload": payload}
    # 200 ≠ успех: читаем result.offerMappings[].errors/warnings (тот же парс, что у писателя W).
    errors, warnings = [], []
    for row in ((resp.get("result", {}).get("offerMappings") or [])):
        if isinstance(row, dict):
            for e in row.get("errors") or []:
                errors.append(e.get("message") if isinstance(e, dict) else str(e))
            for w in row.get("warnings") or []:
                warnings.append(w.get("message") if isinstance(w, dict) else str(w))
    return {"ok": not errors, "dry": False, "offer_id": oid,
            "errors": errors, "warnings": warnings, "payload": payload}


def _read_pics(business_id, offer_id):
    """Свежее живое тело оффера после замены (READ). Нет на кабинете → (None, None)."""
    try:
        import ymarket_hands_v1 as H
        data = H._request("POST", f"/businesses/{business_id}/offer-mappings", body={},
                          params={"limit": 200})
    except Exception:
        return None, None
    for m in (data.get("result", {}).get("offerMappings") or []):
        off = m.get("offer") or {}
        if str(off.get("offerId") or "") == str(offer_id):
            return off.get("pictures") or [], off
    return None, None


def _verify_pics(business_id, offer_id):
    """PG6 СВЕРКА чтением: n_pics>=1 И первое = наш хостинг И чужих URL нет. Честный {pass, why, ...}."""
    pics, _off = _read_pics(business_id, offer_id)
    if pics is None:
        return {"pass": False, "why": "offerId не найден в кабинете после замены"}
    if not pics:
        return {"pass": False, "why": "pictures пуст после замены", "n": 0, "pics": pics}
    foreign = [p for p in pics if not _is_our(p)]
    first_ok = _is_our(pics[0])
    ok = first_ok and not foreign
    return {"pass": ok, "why": ("первое фото — наш URL, чужих нет" if ok
                                else ("первое фото НЕ наше" if not first_ok
                                      else "в наборе есть чужие URL")),
            "n": len(pics), "first": pics[0], "first_ok": first_ok,
            "pics": pics, "foreign": foreign}


def _reverify_all(results, bid, store):
    """Финальная досверка (live): Маркет применяет смену фото асинхронно, поэтому мгновенный re-read
    может быть ложноотрицательным. Один общий GET кабинета в конце хода пересматривает fail-записи и
    закрывает как done те, где фото уже наше. Без повторной генерации — честный итог прогона."""
    try:
        import ymarket_hands_v1 as H
        data = H._request("POST", f"/businesses/{bid}/offer-mappings", body={},
                          params={"limit": 200})
    except Exception as e:
        print("  ⚠️  досверка: кабинет не перечитался (%s: %s) — fail-записи остаются fail"
              % (type(e).__name__, e))
        return
    current = {}
    for m in (data.get("result", {}).get("offerMappings") or []):
        off = m.get("offer") or {}
        current[str(off.get("offerId") or "")] = off.get("pictures") or []
    for line in results:
        if line.get("verdict") != "fail":
            continue
        oid = line.get("offer_id")
        pics = current.get(str(oid)) or []
        if not pics:
            continue
        foreign = [p for p in pics if not _is_our(p)]
        if pics and not foreign:
            line["verify"] = {"pass": True, "why": "досверка: замена применилась асинхронно",
                              "n": len(pics), "first": pics[0], "first_ok": True,
                              "pics": pics, "foreign": []}
            line["verdict"] = "done"
            line["why"] = "замена применилась асинхронно (досверка чтением PASS, первое фото = наш URL)"
            try:
                _lib_note(True, oid, n_photos=len(pics), verdict="PASS",
                          note="РУКА-БОГА (досверка): асинхронная замена применилась — фирменное фото",
                          store_slug=store)
            except Exception:
                pass


# ── библиотека + леджер ───────────────────────────────────────────────────────

def _ledger_append(store, entry):
    """Реестр PG7: runtime/photo_god/<store>/<дата>.jsonl — по строке на SKU (dry/live), append-only."""
    try:
        d = LEDGER_ROOT / store
        d.mkdir(parents=True, exist_ok=True)
        with open(d / ("%s.jsonl" % _today()), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print("  ⚠️  леджер не пишется: %s: %s" % (type(e).__name__, e))


def _lib_note(live, offer_id, *, n_photos, verdict, note, store_slug):
    """Библиотека после живого события: n_photos + last_verified + событие 'photo_god'. Одна атомарная запись."""
    if not live:
        return None
    import ymarket_library_v1 as LIB
    with LIB._locked():
        doc = LIB.load()
        rec = LIB.upsert_card(doc, offer_id, n_photos=n_photos)
        rec["last_verified"] = {"verdict": verdict, "ts": _now(), "store_slug": store_slug, "note": note}
        rec.setdefault("events", []).append(
            LIB._event(_now(), "photo_god", store_slug=store_slug, verdict=verdict, note=note))
        LIB.write_atomic(doc)
    return offer_id


# ── обработка одного SKU ──────────────────────────────────────────────────────

def _forge_summary(fr):
    return {
        "ok": fr.get("ok"), "dry": fr.get("dry"), "provider": fr.get("provider"),
        "model": fr.get("model"), "tier": fr.get("tier"), "path": fr.get("path"),
        "rights": (fr.get("rights") or {}).get("level"),
        "cost_usd": (fr.get("cost_usd") if not fr.get("dry") else fr.get("est_cost_usd")),
        "why": fr.get("why") or fr.get("note"),
    }


def _process_sku(oid, rec, live_offer, business_id, store, dry, film_facts):
    """Один артикул: классификация → форж → публикация → замена → сверка. Возвращает строку леджера."""
    import photo_forge_v1 as F
    import photo_publish_v1 as P

    line = {"ts": _now(), "store": store, "offer_id": oid, "mode": "dry" if dry else "live"}

    # ── классификация текущих фото (из ЖИВОГО кабинета) ──
    if live_offer is None:
        line.update({"verdict": "blocked",
                     "why": "нет offerId в кабинете (карточка не на витрине) — фото не меняем"})
        return line
    pics = live_offer.get("pictures") or []
    line["pictures_current"] = pics
    line["pictures_current_count"] = len(pics)
    line["pictures_foreign"] = [p for p in pics if not _is_our(p)]
    if pics and all(_is_our(p) for p in pics):
        line.update({"verdict": "ok", "why": "уже фирменный кадр ATLAS EDGE (наш URL) — менять нечего"})
        return line

    line["replace_plan"] = {
        "pictures_old": pics,
        "would_remove": line["pictures_foreign"],        # PG5: чужое удаляем целиком
        "would_add": "1 фирменный кадр (generate, canon ATLAS EDGE)",
    }

    # ── 1. ФОРЖ: свои пиксели, canon, бренд (PG3/PG4) ──
    facts = _build_facts(rec, film_facts)
    donor_ph = _donor_phash(pics, dry)
    line["donor_phash"] = donor_ph
    out_dir = None if dry else str(LEDGER_ROOT / store / "frames")
    fr = F.forge(facts=facts, ops=None, mode="generate", dry=dry, model=None,
                 require_verified=True, out_dir=out_dir, tag=oid, canon=True, brand=True,
                 donor_phashes=([donor_ph] if donor_ph else ()))
    line["forge"] = _forge_summary(fr)
    if not fr.get("ok"):
        line.update({"verdict": "blocked", "why": fr.get("why") or "кадр не выкован (форж вернул not ok)"})
        return line

    # ── 2. ПУБЛИКАЦИЯ: провенанс-гейт + хостинг (PG3) ──
    hoster = P.YandexObjectStorage()
    pub = P.pictures_from_forge(fr, hoster=hoster, dry=dry, allow_derivative=False)
    line["publish"] = {"urls": pub.get("urls"), "blocked": pub.get("blocked"),
                       "why": pub.get("why"), "provenance": pub.get("provenance"),
                       "tier": pub.get("tier"), "would_url": pub.get("would_url")}

    if dry:
        # СУХОЙ ГЕЙТ (PG1): 0₽, наружу НИЧЕГО — показываем намерение целиком.
        line.update({"verdict": "plan",
                     "why": ("СУХОЙ ГЕЙТ (0₽): выковать свой кадр (generate, canon, brand) → залить на "
                             "%s → заменить pictures[] целиком (удалить %d чужих) → сверка чтением" %
                             (OUR_HOST, len(line["pictures_foreign"])))})
        return line

    if pub.get("blocked") or not pub.get("urls"):
        line.update({"verdict": "blocked", "why": "; ".join(pub.get("why") or [])})
        return line

    # ── 3. ЗАМЕНА: offer-update pictures[] = наш URL (PG5) ──
    rep = _replace_pictures(business_id, live_offer, pub["urls"], dry=False)
    line["replace"] = {"ok": rep.get("ok"), "errors": rep.get("errors"),
                       "warnings": rep.get("warnings"), "pictures_new": rep.get("pictures_new")}
    if not rep.get("ok"):
        line.update({"verdict": "fail",
                     "why": "замена фото отклонена: " + "; ".join(rep.get("errors") or ["без причины"])})
        return line

    # ── 4. СВЕРКА ЧТЕНИЕМ (PG6): честный PASS/FAIL ──
    v = _verify_pics(business_id, oid)
    # Асинхронность Маркета: смена фото через offer-mappings применяется с задержкой (секунды-минуты),
    # мгновенный re-read ложноотрицателен (оператор видел «ниче не поменялось» при уже-применённых
    # заменах). Даём до 3 попыток с паузой 20с перед честным вердиктом.
    if not v.get("pass"):
        for _ in range(3):
            time.sleep(20)
            v = _verify_pics(business_id, oid)
            if v.get("pass"):
                break
    line["verify"] = v
    if v.get("pass"):
        _lib_note(True, oid, n_photos=v.get("n", len(pub["urls"])), verdict="PASS",
                  note="РУКА-БОГА: водяночное фото заменено на фирменный кадр ATLAS EDGE (%d шт, "
                       "первое = наш URL)" % v.get("n", len(pub["urls"])), store_slug=store)
        line.update({"verdict": "done",
                     "why": "замена + СВЕРКА чтением PASS (первое фото = наш URL, чужих нет)"})
    else:
        _lib_note(True, oid, n_photos=v.get("n"), verdict="FAIL",
                  note="РУКА-БОГА: замена отправлена, но СВЕРКА не прошла: " + v.get("why", ""),
                  store_slug=store)
        line.update({"verdict": "fail",
                     "why": "замена отправлена, но СВЕРКА чтением не прошла: " + v.get("why", "")})
    return line


# ── главный ход ───────────────────────────────────────────────────────────────

def photo_god(store=DEFAULT_STORE, dry=True):
    """Полный ход органа. dry=True (умолч.) — сухой план 0₽; dry=False — боевой (--live, отмашка)."""
    import ymarket_library_v1 as LIB
    try:
        from ymarket_film_cards_v1 import FILM_FACTS
    except Exception:                                  # не роняемся: богатые факты опциональны
        FILM_FACTS = {}

    profile = _store_profile(store)
    if not profile:
        return {"ok": False, "store": store, "mode": "dry" if dry else "live",
                "results": [], "cost_per_provider": {}, "cost_usd_total": 0.0, "cost_rub": 0.0,
                "why": "магазин «%s» не найден в runtime/cycle1/stores.json" % store}
    bid = profile.get("business_id")

    mode = "dry" if dry else "live"
    print("🖐️  РУКА-БОГА · %s · %s" % (store, "СУХОЙ ПЛАН (0₽, наружу НИЧЕГО)" if dry
                                       else "БОЕВОЙ ПРОГОН (живьём)"))

    # PG2 БРОНЯ-ГАРД: отказ ДО прогона (только live).
    blockers = _bone_guard(live=not dry)
    if blockers:
        print("  БРОНЯ-ГАРД (живой режим): отказ ДО траты ₽:")
        for b in blockers:
            print("    · %s" % b)
        return {"ok": False, "store": store, "mode": mode, "blocked": True,
                "blockers": blockers, "results": [], "cost_per_provider": {},
                "cost_usd_total": 0.0, "cost_rub": 0.0}

    # Источник: библиотека (что строили) + ЖИВОЙ кабинет (что сейчас на карточках).
    doc = LIB.load()
    offer_ids = LIB.by_store(doc, store)
    if not offer_ids:
        print("  в библиотеке нет артикулов магазина «%s»" % store)
        return {"ok": True, "store": store, "mode": mode, "results": [],
                "cost_per_provider": {}, "cost_usd_total": 0.0, "cost_rub": 0.0,
                "why": "библиотека пуста для магазина"}

    live, read_err = _read_cabinet(bid)
    if live is None:
        print("  кабинет не читается (%s) — план не строю (честный блок)" % read_err)
        return {"ok": False, "store": store, "mode": mode,
                "why": "кабинет нечитаем: %s" % read_err, "results": [],
                "cost_per_provider": {}, "cost_usd_total": 0.0, "cost_rub": 0.0}

    results = []
    for oid in sorted(offer_ids):
        rec = LIB.get(doc, oid) or {}
        line = _process_sku(oid, rec, live.get(str(oid)), bid, store, dry=dry,
                            film_facts=FILM_FACTS)
        results.append(line)
        _ledger_append(store, line)

    # ── 4b. ФИНАЛЬНАЯ ДОСВЕРКА (live): Маркет применяет смену фото асинхронно (секунды-минуты).
    # Один общий GET кабинета в конце хода пересматривает все fail и закрывает те, что успели
    # примениться, — честный итог без повторной генерации.
    if not dry:
        _reverify_all(results, bid, store)

    # Расход: фактический провайдер (live) / оценка (dry). ₽ = $ × курс.
    per, total_usd = {}, 0.0
    for r in results:
        fr = r.get("forge") or {}
        prov = fr.get("provider") or "?"
        cost = fr.get("cost_usd")
        if cost:
            per[prov] = per.get(prov, 0.0) + cost
            total_usd += cost
    cost_rub = round(total_usd * _rub_rate(), 2)

    return {"ok": True, "store": store, "mode": mode, "results": results,
            "cost_per_provider": per, "cost_usd_total": total_usd, "cost_rub": cost_rub,
            "rub_rate": _rub_rate()}


# ── вывод ──────────────────────────────────────────────────────────────────────

def _render(res):
    lines = []
    mode = res.get("mode")
    lines.append("")
    lines.append("🖐️  РУКА-БОГА · итог прогона · %s · %s" %
                 (res.get("store"), "DRY (0₽, наружу НИЧЕГО)" if mode == "dry" else "LIVE"))
    if res.get("blocked"):
        lines.append("  ОРГАН ОТКАЗАЛСЯ ДО ТРАТЫ ₽ (броня-гард):")
        for b in res.get("blockers", []):
            lines.append("    · %s" % b)
        lines.append("")
        return "\n".join(lines)
    if not res.get("results"):
        lines.append("  ничего не обработано: %s" % res.get("why") or "нет данных")
        lines.append("")
        return "\n".join(lines)

    counts = {}
    for r in res["results"]:
        v = r.get("verdict") or "?"
        counts[v] = counts.get(v, 0) + 1
        tag = {"plan": "🔵", "done": "🟢", "ok": "🟢", "blocked": "🟠", "fail": "🔴"}.get(v, "⚪")
        lines.append("%s %s · %s" % (tag, r["offer_id"], v))
        lines.append("     %s" % (r.get("why") or ""))
        n_cur = r.get("pictures_current_count")
        if n_cur is not None:
            kind = "наш" if r.get("pictures_current") and all(
                _is_our(p) for p in r["pictures_current"]) else "чужие/водяночные"
            lines.append("     сейчас фото: %d (%s)" % (n_cur, kind))
        fr = r.get("forge") or {}
        if fr:
            lines.append("     форж: provider=%s tier=%s rights=%s cost=$%s" %
                         (fr.get("provider"), fr.get("tier"), fr.get("rights"),
                          fr.get("cost_usd")))
        if r.get("publish") and r["publish"].get("blocked") and mode == "live":
            lines.append("     публикация: %s" % "; ".join(r["publish"].get("why") or []))
        if r.get("verify"):
            vv = r["verify"]
            lines.append("     сверка: %s · n=%s · first_ok=%s · foreign=%d" %
                         ("PASS" if vv.get("pass") else "FAIL", vv.get("n"), vv.get("first_ok"),
                          len(vv.get("foreign") or [])))
    lines.append("")
    lines.append("СВОДКА: " + " · ".join("%s=%d" % (k, v) for k, v in sorted(counts.items())))
    per = res.get("cost_per_provider") or {}
    if per:
        lines.append("Расход по провайдерам: " + " · ".join(
            "%s $%.4f" % (k, v) for k, v in sorted(per.items())))
    if mode == "live":
        lines.append("ПОТРАЧЕНО: %.2f ₽ (~$%.4f по курсу %g) — реально сожжено" %
                     (res.get("cost_rub"), res.get("cost_usd_total"), res.get("rub_rate")))
    else:
        lines.append("Оценка живьём: ~%.2f ₽ (~$%.4f по курсу %g) — В СУХОМ ПРОГОНЕ НЕ ТРАТИМ" %
                     (res.get("cost_rub"), res.get("cost_usd_total"), res.get("rub_rate")))
    lines.append("")
    return "\n".join(lines)


def _main(argv=None):
    ap = argparse.ArgumentParser(
        description="РУКА-БОГА: автономная замена водяночных фото на фирменные кадры ATLAS EDGE "
                    "(форж → хостинг → замена pictures[] → сверка чтением)")
    ap.add_argument("--store", default=DEFAULT_STORE, help="магазин (по умолч. %s)" % DEFAULT_STORE)
    ap.add_argument("--dry", action="store_true", help="СУХОЙ ПЛАН, 0₽ (по умолчанию)")
    ap.add_argument("--live", action="store_true",
                    help="БОЕВОЙ ПРОГОН: тратит ₽ и пишет на Маркет — только по слову оператора")
    ap.add_argument("--json", action="store_true", help="вывести машиночитаемый отчёт")
    args = ap.parse_args(argv)

    dry = not args.live or args.dry          # --live выключает dry; явный --dry обратно включает
    res = photo_god(store=args.store, dry=dry)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(_render(res))

    # exit: 0 = прогнон цел (блоки возможны честно), 1 = орган отказался/ошибся до обработки.
    if res.get("blocked") or not res.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())

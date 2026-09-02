#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ФОТО-СНАБЖЕНЕЦ (photo_supply_v1) — батч-орган общего цикла: на N товаров × (1-3) кадра «под ключ».

Замыкает мандат оператора: «это должно стать орган общего цикла… вас двое — вырви победу».
Две руки добычи, одна цель — карточка, которая ПРОДАЁТ, как будто её собрал живой человек,
который переживает за каждый кадр:

  РУКА 1 (бесплатно, 0₽): искатель photo_hunter — ищет чистый готовый кадр в сети.
  РУКА 2 (кузница, ~$0.02): photo_pipeline.forge_card — куёт наш кадр, если бесплатного нет.
  ЛЕНТА (0₽): photo_infographic — наша фирменная лента фактов «под наш лад» поверх кадра.

Стратегия hero-кадра (главного):
  free_first (умолч.)  — сперва пробуем бесплатный чистый кадр; промах → куём.
  always_forge         — главный кадр ВСЕГДА наши пиксели (право чисто), бесплатный только вторичным.

ЧЕСТНОСТЬ (законы искателя наследуются as-is):
  • hero из сети — ТОЛЬКО verdict=='good' (чистый магазин + зрение) И не compromise И conf≥порог И canon.
  • WB и любой 'unknown'/'bad' — НИКОГДА не главный кадр (право/склейка). Может быть донором на переков.
  • факты на ленту НЕ выдумываем — только то, что реально есть в товаре (_photo_facts честно перекладывает).
  • кадр не прошёл канон/приёмку → weak=True + красная ячейка + строка в лог, а НЕ молчаливая витрина.

RUBICON (орган — только ВЫЗЫВАТЕЛЬ, ничего не ломает, наружу без отмашки не тратит):
  • dry=True по умолчанию во ВСЕХ платных входах: план + проекция + монтаж, 0₽/0 сети/0 токенов.
  • НЕ импортит и НЕ зовёт publish/create_card/ymarket_write/update_stocks/photo_publish — attach отдельным
    ручным рубильником, здесь его НЕТ (фото добываем, к витрине НЕ клеим).
  • наследует бронь-гард кузницы: живой canon без Pillow честно откажется ДО траты.
  • бесплатные и не-hero кадры = $0; потолок расхода max_spend_usd (честная частичная пачка).
  • форж под локом — общий леджер кузницы не бьётся при параллели (см. thread-safe ledger, задача #19).

Соседи (ленивый импорт, орган не падает без них — деградирует честно): photo_hunter_v1, photo_forge_v1,
photo_pipeline_v1, photo_infographic_v1 и (только для CLI-входа XLSX) ymarket_role_categorist_v1.
"""
import argparse
import io
import json
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for _p in (str(HERE), str(MINT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Куда кладём кадры/монтаж, чтобы оператор УВИДЕЛ результат у себя на компе.
DESKTOP = Path.home() / "Desktop"
FRAME_LIMIT = 3                       # карточка Маркета: 1-3 кадра — «реально продумано»
DEFAULT_HERO_CLEAN_MIN = 0.62         # порог доверия к бесплатному hero (TUNABLE, оператор подтверждает)

# Единственный общий шов записи кузницы (леджер) — сериализуем форж, чтобы параллель не била JSON.
_FORGE_LOCK = threading.Lock()


# ── Ленивые соседи ───────────────────────────────────────────────────────────────
def _hunter():
    try:
        import photo_hunter_v1 as h            # noqa: F811
        return h
    except Exception:
        return None


def _forge():
    try:
        import photo_forge_v1 as f             # noqa: F811
        return f
    except Exception:
        return None


def _pipeline():
    try:
        import photo_pipeline_v1 as p          # noqa: F811
        return p
    except Exception:
        return None


def _infographic():
    try:
        import photo_infographic_v1 as ig      # noqa: F811
        return ig
    except Exception:
        return None


def _categorist():
    """Только для CLI-входа донорского XLSX. Орган работает и без него (JSON/синтетика)."""
    try:
        import ymarket_role_categorist_v1 as c  # noqa: F811
        return c
    except Exception:
        return None


# ── Мелочи ───────────────────────────────────────────────────────────────────────
def _slug(s, n=40):
    s = str(s or "item").strip().lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_./":
            out.append("-")
    slug = "".join(out).strip("-") or "item"
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:n]


def _num(v):
    """Число из значения (иначе None). Целое печатаем без .0 — чтобы «10 см», а не «10.0 см»."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else round(f, 2)


def _uniq(seq):
    seen, out = set(), []
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _unit_cost(provider):
    """Оценка $/кадр активного провайдера (факт возьмётся из usage кузницы, если вернёт)."""
    f = _forge()
    if provider in ("ru_openai",):
        return getattr(f, "RU_OPENAI_EST_USD", 0.02) if f else 0.02
    if provider in ("google", "openrouter"):
        return getattr(f, "EST_USD_PER_IMAGE", 0.04) if f else 0.04
    if provider in ("fusionbrain",):
        return 0.0                                   # даровой тир
    return getattr(f, "EST_USD_PER_IMAGE", 0.04) if f else 0.04


def _provider_now():
    f = _forge()
    try:
        return f._provider() if f else "openrouter"
    except Exception:
        return "openrouter"


# ── Ссылки-кандидаты и честные факты ───────────────────────────────────────────────
def _urls(product):
    """Лестница ссылок товара: url → urls[] → pictures[]. Первый = первоисточник.

    ВАЖНО: forge_card читает только url|urls (НЕ pictures), поэтому объединённый список мы
    ПЕРЕДАЁМ ему явно параметром urls=. pictures донора (напр. cargo-avto из категорийщика) —
    легитимные кандидаты-доноры, их нельзя терять.
    """
    if not isinstance(product, dict):
        return []
    got = []
    if product.get("url"):
        got.append(product["url"])
    got += list(product.get("urls") or [])
    got += list(product.get("pictures") or [])
    return _uniq(got)


def _photo_facts(product):
    """ЧЕСТНО переложить факты товара в словарь под фото-органы (лента/промпт кузницы).

    Ничего не выдумываем: чего нет — того нет. Габариты _spec (см) → человекочитаемый «размер».
    Уже готовые facts (плёнка: ширина_м/длина_м/плотность_г_м2 и т.п.) пробрасываем как есть,
    spec-производные заполняют только ОТСУТСТВУЮЩИЕ ключи (не перетираем данные товара).
    """
    if not isinstance(product, dict):
        return {}
    facts = dict(product.get("facts") or {})
    spec = dict(product.get("_spec") or {})

    def _put(key, val):
        if val not in (None, "", []) and key not in facts:
            facts[key] = val

    # Габариты посылки/короба (категорийщик держит их в см) → одна строка «размер».
    L, W, H = _num(spec.get("length")), _num(spec.get("width")), _num(spec.get("height"))
    dims = [d for d in (L, W, H) if d is not None]
    if len(dims) >= 2 and not any(k in facts for k in ("размер", "габариты", "size")):
        facts["размер"] = "×".join(str(d) for d in dims) + " см"

    _put("материал", spec.get("material") or spec.get("материал"))
    _put("штук_в_упаковке", spec.get("штук_в_упаковке") or spec.get("in_pack") or spec.get("qty"))
    _put("слои_картона", spec.get("слои_картона"))
    _put("цвет", spec.get("цвет") or spec.get("color"))

    # Вид товара (имя) — помогает и hero-строке ленты, и ветке «плёнка vs короб» в инфографике.
    name = product.get("name") or product.get("title")
    if name and not any(k in facts for k in ("вид", "kind", "name")):
        facts["вид"] = str(name).strip()[:60]
    return facts


# ── Приёмка бесплатного кадра под наш канон (белый 4:5 + предмет) ───────────────────
def _canon_ok(verdict, min_fill, max_off):
    """Прошёл ли кадр наш фирменный канон по вердикту verify_canon (белый+4:5+предмет)."""
    if not isinstance(verdict, dict):
        return False
    if verdict.get("tier") == "off_canon":
        return False
    if verdict.get("white_bg") is not True:
        return False
    if verdict.get("aspect_ok") is not True:
        return False
    subj = verdict.get("subject") or {}
    if subj.get("present") is not True:
        return False
    if min_fill is not None and subj.get("fill") is not None and subj["fill"] < min_fill:
        return False
    if max_off is not None and subj.get("off_center") is not None and subj["off_center"] > max_off:
        return False
    return True


# ── ГЛАВНЫЙ КАДР (hero): бесплатно → иначе куём ────────────────────────────────────
def acquire_hero(product, *, dry=True, hero_clean_min=DEFAULT_HERO_CLEAN_MIN,
                 hero_mode="free_first", canon=True, require_verified=True,
                 min_fill=None, max_off=None, model=None, brand=None, out_dir=None,
                 city="msk", discover_if_empty=True, fallback_models=(), spend_left=None):
    """Добыть ОДИН главный кадр товара. Возврат — честный отчёт (никогда не врёт про успех).

    dry=True  — 0₽/0 сети: план (что сделали бы) + проекция расхода. Наружу ничего.
    dry=False — живой режим (тратит ₽/квоту, ТОЛЬКО по отмашке оператора).
    hero_mode — 'free_first' (сначала бесплатный чистый кадр) | 'always_forge' (главный всегда наши пиксели).
    """
    facts = _photo_facts(product)
    cands = _urls(product)
    prov = _provider_now()
    unit = _unit_cost(prov)
    base = {"frame": "hero", "sku": product.get("sku"), "name": product.get("name"),
            "provider": prov, "hero_mode": hero_mode, "candidates": len(cands)}

    # ── СУХОЙ ГЕЙТ: план, 0 сети ──────────────────────────────────────────────────
    if dry:
        pipe = _pipeline()
        forge_plan = None
        if pipe is not None:
            try:
                fc = pipe.forge_card(product, urls=cands, dry=True, canon=canon, model=model,
                                     brand=brand, tag=_slug(product.get("sku") or product.get("name")))
                forge_plan = {"mode": fc.get("mode"), "rights": fc.get("rights"),
                              "est_cost_usd": fc.get("est_cost_usd")}
            except Exception as e:
                forge_plan = {"error": type(e).__name__}
        # Честно: даже free_first обычно доходит до форжа (бесплатный МП-кадр редко белый 4:5),
        # поэтому проекция hero = цена одного кова (верхняя честная оценка), а не 0.
        est = unit
        return dict(base, ok=True, dry=True, source="plan", path=None, cost_usd=0.0,
                    est_cost_usd=round(est, 4), forge_plan=forge_plan, weak=None,
                    note=("СУХОЙ ГЕЙТ (0₽/0 сети). Живьём: %s → приёмка канона → иначе кузница "
                          "(%s, ~$%.2f/кадр). Запусти dry=False по отмашке." % (
                              "бесплатный поиск" if hero_mode == "free_first" else "сразу кузница",
                              prov, unit)))

    # ── ЖИВОЙ РЕЖИМ (отмашка) ─────────────────────────────────────────────────────
    h = _hunter()
    f = _forge()
    confmap = {u: 1.0 for u in cands}   # явные ссылки товара — первоисточник, доверие по умолч. 1.0

    # Нечего проверять и разрешено — добываем ссылки токен-free (0₽).
    if not cands and discover_if_empty and h is not None:
        try:
            found = h.discover(product.get("name") or "", facts=facts, city=city)
            for c in found:
                if c.get("url"):
                    cands.append(c["url"])
                    confmap[c["url"]] = c.get("confidence") or 0.0
            cands = _uniq(cands)
            base["candidates"] = len(cands)
        except Exception:
            pass

    # РУКА 1: бесплатный чистый hero (только при free_first).
    if hero_mode == "free_first" and cands and h is not None and f is not None:
        try:
            hr = h.hunt(cands, facts=facts, need=FRAME_LIMIT)
        except Exception:
            hr = {"good": []}
        for r in (hr.get("good") or []):
            if r.get("compromise"):
                continue                                   # след МП/продавца → нельзя главным
            if confmap.get(r.get("url"), 1.0) < hero_clean_min:
                continue                                   # слабое совпадение с товаром
            raw, _ = h.fetch_bytes(r["url"])
            if not raw:
                continue
            try:
                v = f.verify_canon(raw, facts=facts, require_subject=True,
                                   min_fill=min_fill, max_off=max_off, aspect="4:5")
            except Exception:
                continue
            if _canon_ok(v, min_fill, max_off):
                path = _save_own_copy(raw, out_dir, _slug(product.get("sku") or product.get("name")))
                return dict(base, ok=True, dry=False, source="free", path=path, cost_usd=0.0,
                            tier="third_party_clean", verdict=v, url=r["url"], weak=False,
                            rights={"level": "third_party_clean", "clean": True,
                                    "note": "чистый сторонний кадр из доверенного магазина; "
                                            "право на публикацию — решение оператора"},
                            note="бесплатный чистый hero прошёл канон (0₽)")

    # РУКА 2: кузница (free_first промахнулся, либо always_forge). Форж под локом — леджер общий.
    pipe = _pipeline()
    if pipe is None:
        return dict(base, ok=False, dry=False, source="none", path=None, cost_usd=0.0,
                    weak=True, why="кузница недоступна (photo_pipeline не импортнулся)")
    # ПОТОЛОК: нет бюджета на кова — честно пропускаем (это budget-skip, НЕ quality-weak).
    if spend_left is not None and spend_left < unit:
        return dict(base, ok=False, dry=False, source="skipped_budget", path=None, cost_usd=0.0,
                    weak=False, why="исчерпан потолок max_spend_usd — hero не куём (пачка честно частичная)")
    tries = [model] + [m for m in fallback_models if m and m != model]
    last = None
    for m in tries:
        with _FORGE_LOCK:
            fc = pipe.forge_card(product, urls=cands, dry=False, prefer_clean=True,
                                 require_verified=require_verified, canon=canon, model=m,
                                 brand=brand, out_dir=out_dir,
                                 tag=_slug(product.get("sku") or product.get("name")))
        last = fc
        tier = (fc.get("forge") or {}).get("tier") or fc.get("tier")
        if fc.get("ok") and fc.get("path") and tier not in ("off_canon", "rejected"):
            return dict(base, ok=True, dry=False, source="forged", path=fc.get("path"),
                        cost_usd=fc.get("cost_usd") or 0.0, tier=tier, mode=fc.get("mode"),
                        rights=fc.get("rights"), verdict=(fc.get("forge") or {}).get("verdict"),
                        cost_source=fc.get("cost_source"), weak=False,
                        note="hero выкован (%s)" % fc.get("mode"))
    # Не вышло за все попытки — честно weak (в лог, красная ячейка), кадр на витрину НЕ идёт.
    return dict(base, ok=False, dry=False, source="forged", path=(last or {}).get("path"),
                cost_usd=(last or {}).get("cost_usd") or 0.0,
                tier=((last or {}).get("forge") or {}).get("tier") or (last or {}).get("tier"),
                rights=(last or {}).get("rights"), weak=True,
                why=(last or {}).get("why") or "кузница не дала кадр в каноне за все попытки")


def _save_own_copy(raw, out_dir, tag):
    """Сохранить бесплатный кадр в НАШУ копию (мы держим файл сами, не хотлинк чужого CDN)."""
    d = Path(out_dir or (HERE / "_photo_out"))
    try:
        d.mkdir(parents=True, exist_ok=True)
        ext = "png"
        if raw[:3] == b"\xff\xd8\xff":
            ext = "jpg"
        elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
            ext = "webp"
        p = d / ("hero-%s-%d.%s" % (tag, int(time.time() * 1000) % 100000, ext))
        p.write_bytes(raw)
        return str(p)
    except Exception:
        return None


# ── ОДИН ТОВАР: hero + фирменная лента + вторичный кадр ─────────────────────────────
def supply_one(product, *, dry=True, need_frames=3, hero_clean_min=DEFAULT_HERO_CLEAN_MIN,
               hero_mode="free_first", infographic=True, canon=True, require_verified=True,
               min_fill=None, max_off=None, model=None, brand=None, out_dir=None, city="msk",
               discover_if_empty=True, fallback_models=(), spend_left=None):
    """Один товар → 1-3 кадра. Frame1 hero (free/forged), Frame2 фирменная лента, Frame3 вторичный чистый."""
    sku = product.get("sku")
    name = product.get("name") or product.get("title") or "товар"
    facts = _photo_facts(product)
    need_frames = max(1, min(FRAME_LIMIT, int(need_frames)))
    tag = _slug(sku or name)
    frames, cost = [], 0.0

    # Потолок расхода живёт в acquire_hero (бесплатная попытка free_first остаётся даже при 0 бюджета;
    # платный кова гейтится spend_left) — здесь просто прокидываем остаток.
    hero = acquire_hero(product, dry=dry, hero_clean_min=hero_clean_min, hero_mode=hero_mode,
                        canon=canon, require_verified=require_verified, min_fill=min_fill,
                        max_off=max_off, model=model, brand=brand, out_dir=out_dir, city=city,
                        discover_if_empty=discover_if_empty, fallback_models=fallback_models,
                        spend_left=spend_left)
    frames.append(hero)
    cost += hero.get("cost_usd") or 0.0

    # Frame2: наша фирменная лента фактов «под наш лад» (локальный PIL, 0₽/0 сети — и в dry, и в live).
    if infographic and need_frames >= 2:
        frames.append(_frame_infographic(product, hero, facts, dry, brand, out_dir, tag))

    # Frame3: ВТОРИЧНЫЙ чистый бесплатный ракурс (никогда не главный; только план в dry).
    if need_frames >= 3:
        frames.append(_frame_secondary(product, hero, facts, dry))

    weak = any(fr.get("weak") for fr in frames if fr.get("weak") is not None)
    ok = bool(frames[0].get("ok"))
    return {"sku": sku, "name": name, "ok": ok, "weak": weak, "dry": bool(dry),
            "frames": frames, "cost_usd": round(cost, 4),
            "honesty": {"hero_source": frames[0].get("source"),
                        "hero_rights": (frames[0].get("rights") or {}).get("level")
                        if isinstance(frames[0].get("rights"), dict) else frames[0].get("tier"),
                        "facts_used": list(facts.keys())}}


def _frame_infographic(product, hero, facts, dry, brand, out_dir, tag):
    """Фирменная лента. dry → реальный локальный рендер на синтетик-белом (для монтажа, 0 файла).
    live → compose_infographic поверх реального hero + доставка копии на Рабочий стол."""
    ig = _infographic()
    if ig is None or not getattr(ig, "_HAVE_PIL", False):
        return {"frame": "info", "ok": False, "cost_usd": 0.0, "weak": False,
                "why": "инфографика недоступна без Pillow (честный пропуск; кадр не обязателен)"}
    try:
        if dry:
            base = _white_hero_placeholder(ig)
            canvas = ig.render(base, facts=facts, brand=brand, zoom=False)
            return {"frame": "info", "ok": True, "dry": True, "cost_usd": 0.0, "weak": False,
                    "path": None, "_canvas": canvas, "specs": ig._specs(facts),
                    "note": "фирменная лента отрендерена локально (превью; hero подставится живьём)"}
        base = hero.get("path")
        if not base:
            return {"frame": "info", "ok": False, "cost_usd": 0.0, "weak": False,
                    "why": "нет hero-кадра под ленту (hero промахнулся)"}
        rep = ig.compose_infographic(base, facts=facts, brand=brand, out_dir=out_dir,
                                     deliver_dir=str(DESKTOP), dry=False, tag=tag)
        return {"frame": "info", "ok": bool(rep.get("ok")), "dry": False, "cost_usd": 0.0,
                "path": rep.get("path"), "thumb": rep.get("thumb"), "weak": not rep.get("ok"),
                "specs": (rep.get("content") or {}).get("specs"), "why": rep.get("why")}
    except Exception as e:
        return {"frame": "info", "ok": False, "cost_usd": 0.0, "weak": False,
                "why": "инфографика упала: %s" % type(e).__name__}


def _frame_secondary(product, hero, facts, dry):
    """Frame3 — вторичный чистый ракурс из сети. Никогда не hero; бесплатный, право — оператор.
    В dry только план; живьём добираем из уже проверенных 'good'/'unknown' (кроме hero-url)."""
    if dry:
        return {"frame": "secondary", "ok": True, "dry": True, "cost_usd": 0.0, "weak": False,
                "path": None, "note": "план: живьём добрали бы второй чистый ракурс, если найдётся"}
    h = _hunter()
    cands = [u for u in _urls(product) if u != hero.get("url")]
    if not cands or h is None:
        return {"frame": "secondary", "ok": False, "cost_usd": 0.0, "weak": False,
                "why": "нет запасных ссылок под второй ракурс — пропуск (не обязателен)"}
    try:
        hr = h.hunt(cands, facts=facts, need=1)
    except Exception:
        hr = {"good": []}
    for r in (hr.get("good") or []):
        if r.get("compromise") or r.get("url") == hero.get("url"):
            continue
        raw, _ = h.fetch_bytes(r["url"])
        if raw:
            path = _save_own_copy(raw, None, _slug(product.get("sku")) + "-b")
            return {"frame": "secondary", "ok": True, "cost_usd": 0.0, "weak": False,
                    "path": path, "url": r["url"], "tier": "third_party_clean",
                    "note": "вторичный чистый ракурс (0₽)"}
    return {"frame": "secondary", "ok": False, "cost_usd": 0.0, "weak": False,
            "why": "чистого второго ракурса не нашлось — пропуск (не обязателен)"}


def _white_hero_placeholder(ig):
    """Синтетик-белый холст с бледной рамкой «ФОТО» — чтобы в превью честно читалось: hero живьём."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (ig.CANVAS_W, ig.CANVAS_H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    m, top, bot = 120, 150, 980
    d.rounded_rectangle([m, top, ig.CANVAS_W - m, bot], radius=24, outline=(210, 210, 210), width=3)
    try:
        f = ig._load_font(40, bold=False)
        t = "ФОТО ТОВАРА"
        w = d.textlength(t, font=f)
        d.text(((ig.CANVAS_W - w) / 2, (top + bot) / 2 - 20), t, font=f, fill=(200, 200, 200))
    except Exception:
        pass
    return im


# ── БАТЧ: N товаров, ограниченная параллель, потолок расхода, монтаж ────────────────
def supply_batch(products, *, dry=True, need_frames=3, hero_clean_min=DEFAULT_HERO_CLEAN_MIN,
                 hero_mode="free_first", infographic=True, canon=True, require_verified=True,
                 max_workers=3, max_spend_usd=None, model=None, brand=None, out_dir=None,
                 city="msk", discover_if_empty=True, contact_sheet=True, min_fill=None,
                 max_off=None, fallback_models=()):
    """Пачка товаров → кадры. dry (умолч.) — план+проекция+монтаж (0₽/0 сети). live — по отмашке.

    max_workers — ограниченная параллель для ЖИВОЙ добычи (форж сериализован локом: общий леджер).
    max_spend_usd — потолок: дошли до предела → остаток товаров честно помечается skipped_budget.
    """
    products = [p for p in (products or []) if isinstance(p, dict)]
    n = len(products)
    proj = project_cost(products, provider=_provider_now(), hero_mode=hero_mode)
    results = [None] * n

    if dry:
        # 0 сети → быстрый локальный проход (рендер лент реальный, но локальный).
        for i, p in enumerate(products):
            results[i] = supply_one(p, dry=True, need_frames=need_frames, hero_clean_min=hero_clean_min,
                                    hero_mode=hero_mode, infographic=infographic, canon=canon,
                                    require_verified=require_verified, min_fill=min_fill, max_off=max_off,
                                    model=model, brand=brand, out_dir=out_dir, city=city,
                                    discover_if_empty=discover_if_empty)
    else:
        # ЖИВОЙ РЕЖИМ (отмашка): ограниченная параллель. Потолок расхода считаем под локом.
        spent = {"usd": 0.0}
        spend_lock = threading.Lock()

        def _budget_left():
            if max_spend_usd is None:
                return None
            with spend_lock:
                return max(0.0, max_spend_usd - spent["usd"])

        def _run(i, p):
            r = supply_one(p, dry=False, need_frames=need_frames, hero_clean_min=hero_clean_min,
                           hero_mode=hero_mode, infographic=infographic, canon=canon,
                           require_verified=require_verified, min_fill=min_fill, max_off=max_off,
                           model=model, brand=brand, out_dir=out_dir, city=city,
                           discover_if_empty=discover_if_empty, fallback_models=fallback_models,
                           spend_left=_budget_left())
            if r.get("cost_usd"):
                with spend_lock:
                    spent["usd"] += r["cost_usd"]
            return i, r

        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as ex:
                for i, r in ex.map(lambda t: _run(*t), list(enumerate(products))):
                    results[i] = r
        except Exception:
            for i, p in enumerate(products):
                results[i] = _run(i, p)[1]

    results = [r for r in results if r is not None]
    cost = round(sum(r.get("cost_usd") or 0.0 for r in results), 4)
    weak = [r for r in results if r.get("weak")]
    forged = [r for r in results if (r.get("frames") or [{}])[0].get("source") == "forged"]
    free = [r for r in results if (r.get("frames") or [{}])[0].get("source") == "free"]
    skipped = [r for r in results if (r.get("frames") or [{}])[0].get("source") == "skipped_budget"]

    sheet = None
    if contact_sheet:
        sheet = build_contact_sheet(results, out_dir=out_dir, tag=("batch-dry" if dry else "batch"))

    # Монтаж собран → снимаем PIL-холсты ленты из результатов (возврат остаётся JSON-safe).
    for r in results:
        for fr in (r.get("frames") or []):
            fr.pop("_canvas", None)

    out = {"n": n, "dry": bool(dry), "ok": sum(1 for r in results if r.get("ok")),
           "weak": len(weak), "forged": len(forged), "free": len(free),
           "skipped_budget": len(skipped), "cost_usd": cost, "provider": _provider_now(),
           "projection": proj, "hero_mode": hero_mode,
           "contact_sheet": (sheet or {}).get("path"), "results": results,
           "weak_log": [{"sku": r.get("sku"), "why": (r.get("frames") or [{}])[0].get("why")}
                        for r in weak]}
    return out


# ── ПРОЕКЦИЯ РАСХОДА (чистая, 0 сети) ──────────────────────────────────────────────
def project_cost(products_or_n, *, provider=None, hero_mode="free_first", assume_free_rate=0.0):
    """Сколько будет стоить пачка. best (всё бесплатно) / worst (всё кованое) / реалистично.

    Только hero платный (frames 2-3 бесплатные). free_first даёт шанс бесплатного hero.
    """
    n = products_or_n if isinstance(products_or_n, int) else len(products_or_n or [])
    prov = provider or _provider_now()
    unit = _unit_cost(prov)
    free_rate = 0.0 if hero_mode == "always_forge" else max(0.0, min(1.0, float(assume_free_rate)))
    best = 0.0
    worst = round(n * unit, 4)
    realistic = round(n * unit * (1.0 - free_rate), 4)
    return {"n": n, "provider": prov, "unit_usd": unit, "hero_mode": hero_mode,
            "assume_free_rate": free_rate, "best_usd": best, "worst_usd": worst,
            "realistic_usd": realistic,
            "note": ("только hero платный (%s ~$%.2f); лента и вторичный кадр бесплатны. "
                     "best=всё бесплатно, worst=каждый hero кован." % (prov, unit))}


# ── МОНТАЖ-ПРОСТЫНЯ (оператор видит пачку одним взглядом, 0₽/0 токенов) ─────────────
def build_contact_sheet(results, *, out_dir=None, cols=5, cell=(360, 450), tag="batch"):
    """Собрать превью пачки в одну картинку на Рабочий стол. Без PIL → честный текст-манифест.

    Ячейка: hero-кадр (live) ИЛИ лента-превью (dry) ИЛИ бледный плейсхолдер. Рамка: зелёная ok,
    красная weak, серая skipped. 0 сети, 0 токенов — чистый локальный монтаж для «увидеть глазами»."""
    d = Path(out_dir or DESKTOP)
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    ig = _infographic()
    have_pil = bool(ig and getattr(ig, "_HAVE_PIL", False))
    n = len(results)

    if not have_pil:
        # Честный текст-манифест — приёмка (и оператор без Pillow) всё равно видит структуру пачки.
        lines = ["ФОТО-СНАБЖЕНЕЦ · манифест пачки (Pillow нет → текст вместо монтажа)",
                 "товаров: %d" % n, ""]
        for r in results:
            fr0 = (r.get("frames") or [{}])[0]
            mark = "OK " if r.get("ok") and not r.get("weak") else ("WEAK" if r.get("weak") else "— ")
            lines.append("[%s] %-14s %s · hero=%s" % (
                mark, str(r.get("sku"))[:14], str(r.get("name"))[:40], fr0.get("source")))
        p = d / ("%s-manifest.txt" % tag)
        try:
            p.write_text("\n".join(lines), encoding="utf-8")
            return {"ok": True, "path": str(p), "mode": "text", "cells": n, "cost_usd": 0.0}
        except Exception as e:
            return {"ok": False, "path": None, "mode": "text", "cost_usd": 0.0,
                    "why": type(e).__name__}

    from PIL import Image, ImageDraw
    cw, ch = cell
    cols = max(1, int(cols))
    rows = max(1, (n + cols - 1) // cols)
    pad, label_h = 12, 26
    W = cols * cw + (cols + 1) * pad
    H = rows * (ch + label_h) + (rows + 1) * pad
    sheet = Image.new("RGB", (W, H), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ig._load_font(18, bold=True)
    except Exception:
        font = None

    for idx, r in enumerate(results):
        rr, cc = divmod(idx, cols)
        x = pad + cc * (cw + pad)
        y = pad + rr * (ch + label_h + pad)
        thumb = _cell_image(r, ig, (cw, ch))
        if thumb is not None:
            sheet.paste(thumb, (x, y))
        else:
            draw.rectangle([x, y, x + cw, y + ch], fill=(255, 255, 255), outline=(220, 220, 220))
        # Рамка статуса: зелёная ok / красная weak / серая пропуск.
        if r.get("weak"):
            border = (200, 60, 60)
        elif r.get("ok"):
            border = (60, 170, 90)
        else:
            border = (150, 150, 150)
        draw.rectangle([x, y, x + cw, y + ch], outline=border, width=4)
        cap = "%s · %s" % (str(r.get("sku") or "")[:12], (r.get("frames") or [{}])[0].get("source") or "")
        draw.text((x + 4, y + ch + 4), cap[:46], font=font, fill=(40, 40, 40))

    p = d / ("%s-contact.png" % tag)
    try:
        sheet.save(p)
        return {"ok": True, "path": str(p), "mode": "image", "cells": n, "cost_usd": 0.0}
    except Exception as e:
        return {"ok": False, "path": None, "mode": "image", "cost_usd": 0.0, "why": type(e).__name__}


def _cell_image(result, ig, size):
    """Картинка ячейки: реальный hero-путь (live) → лента-превью canvas (dry) → None (плейсхолдер)."""
    from PIL import Image
    frames = result.get("frames") or []
    # 1) живой hero-файл
    hero = frames[0] if frames else {}
    if hero.get("path"):
        try:
            im = Image.open(hero["path"]).convert("RGB")
            im.thumbnail(size)
            return _center(im, size)
        except Exception:
            pass
    # 2) dry: реальный локальный рендер фирменной ленты (frame2 _canvas)
    for fr in frames:
        cv = fr.get("_canvas")
        if cv is not None:
            try:
                im = cv.convert("RGB").copy()
                im.thumbnail(size)
                return _center(im, size)
            except Exception:
                pass
    return None


def _center(im, size):
    from PIL import Image
    cw, ch = size
    canvas = Image.new("RGB", size, (255, 255, 255))
    canvas.paste(im, ((cw - im.size[0]) // 2, (ch - im.size[1]) // 2))
    return canvas


# ── Паспорт возможностей ───────────────────────────────────────────────────────────
def capabilities():
    """Что орган реально умеет в этом окружении (без вранья)."""
    h, f, ig = _hunter(), _forge(), _infographic()
    forge_caps = None
    try:
        forge_caps = f.capabilities() if f else None
    except Exception:
        forge_caps = None
    caps = {
        "hunter": (h.capabilities() if h else None),
        "forge_provider": _provider_now(),
        "forge_key": (forge_caps or {}).get("key"),
        "forge_net": (forge_caps or {}).get("net"),
        "forge_pil": (f._have_pil() if f and hasattr(f, "_have_pil") else None),
        "infographic_pil": bool(ig and getattr(ig, "_HAVE_PIL", False)),
        "contact_sheet": bool(ig and getattr(ig, "_HAVE_PIL", False)),
        "unit_cost_usd": _unit_cost(_provider_now()),
        "rubicon": ("dry по умолч.; НЕ клеит к витрине (нет publish/create_card/write/update_stocks); "
                    "free=0₽; unknown/bad НИКОГДА не hero; факты не выдумываем; потолок max_spend_usd."),
    }
    return caps


# ── Вход (CLI): синтетика / JSON / донорский XLSX ──────────────────────────────────
def _demo_products(n):
    """Синтетические товары (короба+плёнка) для сухого доказательства масштаба — без внешних файлов."""
    out = []
    for i in range(n):
        if i % 3 == 0:
            out.append({"name": "Гофрокороб %dх%dх%d" % (60 + i, 40, 40), "sku": "BOX-%03d" % i,
                        "cost": 30 + i, "pictures": [],
                        "_spec": {"length": 60 + i, "width": 40, "height": 40, "weight": 0.35,
                                  "material": "гофрокартон", "слои_картона": "пятислойный",
                                  "штук_в_упаковке": 10}})
        elif i % 3 == 1:
            out.append({"name": "Плёнка воздушно-пузырьковая 0.5×%d м" % (50 + i), "sku": "VPP-%03d" % i,
                        "cost": 400 + i, "pictures": [],
                        "facts": {"kind": "Плёнка", "ширина_м": 0.5, "длина_м": 50 + i,
                                  "плотность_г_м2": 40, "толщина_мм": 0.12, "диаметр_пузырька_мм": 10}})
        else:
            out.append({"name": "Стрейч-плёнка 0.5×%d м" % (200 + i), "sku": "STR-%03d" % i,
                        "cost": 250 + i, "pictures": [],
                        "_spec": {"material": "ПЭ", "штук_в_упаковке": 6},
                        "facts": {"kind": "Плёнка", "ширина_м": 0.5, "длина_м": 200 + i,
                                  "плотность_г_м2": 20}})
    return out


def _load_products(args):
    if args.donor:
        c = _categorist()
        if c is None:
            print("категорийщик недоступен — не могу прочитать XLSX; дай --products JSON или --demo N")
            return []
        try:
            items = c.read_donor(args.donor)
            return items if isinstance(items, list) else (items.get("items") or [])
        except Exception as e:
            print("не смог прочитать донора: %s" % e)
            return []
    if args.products:
        try:
            data = json.loads(Path(args.products).read_text(encoding="utf-8"))
            return data if isinstance(data, list) else (data.get("items") or data.get("products") or [])
        except Exception as e:
            print("не смог прочитать JSON: %s" % e)
            return []
    return _demo_products(args.demo)


def main(argv=None):
    ap = argparse.ArgumentParser(description="ФОТО-СНАБЖЕНЕЦ: батч-кадры карточек (dry по умолч.)")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--demo", type=int, default=12, help="синтетических товаров (по умолч. 12)")
    src.add_argument("--products", help="путь к JSON-списку товаров")
    src.add_argument("--donor", help="путь к донорскому XLSX (через категорийщика)")
    ap.add_argument("--frames", type=int, default=3, help="кадров на товар 1-3 (умолч. 3)")
    ap.add_argument("--hero-mode", choices=["free_first", "always_forge"], default="free_first")
    ap.add_argument("--no-infographic", action="store_true", help="без фирменной ленты")
    ap.add_argument("--max-workers", type=int, default=3)
    ap.add_argument("--max-spend", type=float, default=None, help="потолок $ на пачку (live)")
    ap.add_argument("--out", default=None, help="куда класть кадры/монтаж (умолч. Рабочий стол)")
    ap.add_argument("--project", action="store_true", help="только проекция расхода (0 сети)")
    ap.add_argument("--caps", action="store_true", help="паспорт возможностей и выход")
    ap.add_argument("--live", action="store_true",
                    help="ЖИВОЙ режим (тратит ₽/квоту) — ТОЛЬКО по отмашке оператора")
    args = ap.parse_args(argv)

    if args.caps:
        print(json.dumps(capabilities(), ensure_ascii=False, indent=2))
        return 0

    products = _load_products(args)
    if not products:
        print("нет товаров на вход.")
        return 1

    if args.project:
        pr = project_cost(products, hero_mode=args.hero_mode)
        print(json.dumps(pr, ensure_ascii=False, indent=2))
        return 0

    dry = not args.live
    if args.live:
        print("⚠️  ЖИВОЙ режим: будет тратить ₽/квоту. Убедись, что это осознанная отмашка.")
    rep = supply_batch(products, dry=dry, need_frames=args.frames, hero_mode=args.hero_mode,
                       infographic=not args.no_infographic, max_workers=args.max_workers,
                       max_spend_usd=args.max_spend, out_dir=args.out,
                       contact_sheet=True)
    slim = {k: rep[k] for k in ("n", "dry", "ok", "weak", "forged", "free", "skipped_budget",
                                "cost_usd", "provider", "hero_mode", "contact_sheet")}
    slim["projection"] = rep["projection"]
    print(json.dumps(slim, ensure_ascii=False, indent=2))
    if rep.get("contact_sheet"):
        print("\n🖼  монтаж на Рабочем столе: %s" % rep["contact_sheet"])
    if rep.get("weak_log"):
        print("\n⚠️ слабые (в лог, на витрину НЕ идут):")
        for w in rep["weak_log"]:
            print("   %s — %s" % (w["sku"], w["why"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

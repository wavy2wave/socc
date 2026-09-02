#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ФОТО-ИСКАТЕЛЬ · ПРИЁМКА добытчика (discover/find/card.json/матчер/закон компрометации).

Оффлайн, 0₽, без сети. Пара к run_photoforge (та проверяет кузницу). Здесь — ВЕРХНЯЯ половина
искателя: как из текстового запроса рождаются прямые ссылки, почему самый-на-запрос кадр всплывает
первым и почему честность вердикта цела. Единственный шов сети (WB-поиск, зонд basket, скачивание
кадра, card.json, OCR) подменяется — наружу не уходит ничего. Basket-резолвер герметизирован в ПАМЯТЬ
(затравка), поэтому приёмка не зависит от накопленного state/wb_basket_map.json.

  H1  basket_url_formula      — wb_image_urls строит точный путь vol/part/nm/images/big/i.webp.
  H2  basket_selfcorrect      — basket ≠ угадки → пробой соседей находит живой и кэширует (снятие дрейфа).
  H3  basket_cache_hit        — известный vol резолвится БЕЗ единого зонда (кэш «знаем навсегда»).
  H4  discover_shape          — запрос → кандидаты с прямой ссылкой, провенансом и ЧЕСТНЫМ флагом права.
  H5  discover_wb_absent      — нет wb_scout → discover пуст, без падения (мягкая зависимость).
  H6  honest_unknown          — годный кадр с НЕдоверенного хоста → вердикт 'unknown', НИКОГДА не 'good'.
  H7  trusted_registry        — host_is_clean видит known_clean_shops → право на 'good' даёт провенанс.
  H8  find_wiring_order       — find: провенанс приклеен, direct_links = сперва good, затем unknown.
  H9  matcher_numeric         — сверка по числу-габариту: тот же 0,3×100 в тексте бьёт мимо-размер.
  H10 card_info_parse         — wb_card_info тянет imt_name/vendor_code/options(+grouped)/photo_count/brand.
  H11 deepen_cardjson_rerank  — габарит живёт в card.json, не в имени → deepen поднимает сверку до точной.
  H12 compromise_law          — след маркетплейса/продавца на кадре = compromise 'bad'; опт = грязь, но не компромат.
  H13 host_boundary_no_spoof  — граница хоста: подмена/приклейка (example.ru.evil / fakeexample.ru) НЕ доверена.
  H14 ocr_missing_not_good    — чистый хост + зрение-ок, но OCR недоступен → 'unknown' (компромат не исключён).
  H15 blocklist_before_cache  — блок-лист главнее кэша; версия ключа снимает тухлый вердикт при ужесточении.
  H16 basket_resolve_deadline — неизвестный vol с дедлайном НЕ жжёт 60 зондов, а отдаёт None вовремя.
"""
import io
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import photo_hunter_v1 as H  # noqa: E402

# ── ГЕРМЕТИЗАЦИЯ basket-резолвера: карта vol→basket в ПАМЯТИ (затравка), без диска ──
# Иначе тест зависит от накопленного state/wb_basket_map.json (H2 ложно зелёный на кэш-хите).
_MEM_BASKET = dict(H._WB_BASKET_SEED)
H._wb_basket_cache = lambda: _MEM_BASKET
H._wb_save_basket = lambda cache: None
# Оригиналы для тестов, которые их подменяют (восстановим — порядок тестов не должен решать).
_ORIG_DISCOVER, _ORIG_HUNT = H.discover, H.hunt

FAILED = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print("  [%s] %s%s" % (tag, name, ("" if cond else "  ← " + detail)))
    if not cond:
        FAILED.append(name)


def _png_bytes(w=1000, h=1000):
    """Настоящий PNG нужного размера (для ступени ЖЕЛЕЗО). Через PIL, если он есть."""
    if not H.HAVE_PIL:
        return None
    buf = io.BytesIO()
    H.Image.new("RGB", (w, h), (240, 240, 240)).save(buf, format="PNG")
    return buf.getvalue()


def _noisy_png(w=1000, h=1000):
    """Весомый PNG: шум не сжимается → байтов хватает, чтобы пройти порог ЖЕЛЕЗА (не «превью»)."""
    if not H.HAVE_PIL:
        return None
    import os
    buf = io.BytesIO()
    H.Image.frombytes("RGB", (w, h), os.urandom(w * h * 3)).save(buf, format="PNG")
    return buf.getvalue()


# ── H1 · формула URL ──────────────────────────────────────────────────────────────
def h1():
    nm = 329471133  # vol=3294 → basket 20 (в затравке)
    urls = H.wb_image_urls(nm, pics=1, probe=lambda u: True)
    want = "https://basket-20.wbbasket.ru/vol3294/part329471/329471133/images/big/1.webp"
    check("H1 basket_url_formula", urls == [want], "got %r" % urls)


# ── H2 · само-коррекция basket ──────────────────────────────────────────────────────
def h2():
    nm = 555000111  # vol=5550 — НЕ в затравке; настоящий basket пусть будет 28
    calls = {"n": 0}

    def probe(u):
        calls["n"] += 1
        return "basket-28." in u

    urls = H.wb_image_urls(nm, pics=1, probe=probe)
    ok = bool(urls) and "basket-28." in urls[0]
    cached = H._wb_basket_cache().get("5550") == 28
    check("H2 basket_selfcorrect", ok and cached and calls["n"] > 1,
          "urls=%r cached=%s probes=%d" % (urls, cached, calls["n"]))


# ── H3 · кэш-хит без сети ────────────────────────────────────────────────────────────
def h3():
    def boom(u):
        raise AssertionError("зонд не должен вызываться на известном vol")

    urls = H.wb_image_urls(1979 * 100000 + 42, pics=1, probe=boom)  # vol=1979 в затравке → 13
    check("H3 basket_cache_hit", bool(urls) and "basket-13." in urls[0], "urls=%r" % urls)


# ── H4 · форма discover + честный флаг права ────────────────────────────────────────
def h4():
    fake = [{"id": 329471133, "name": "Пупырчатая пленка рулон 0,3x100м", "pics": 1,
             "salePriceU": 149000}]
    H._wb = types.SimpleNamespace(scan_category=lambda **k: fake,
                                  _price_rub=lambda p: 1490.0)
    H.HAVE_WB = True
    H._wb_probe_webp = lambda u, timeout=10: True
    cands = H.discover("пузырчатая плёнка 0.3", limit_products=5, pics_per=1)  # deepen OFF → без сети
    c = cands[0] if cands else {}
    ok = (len(cands) == 1 and c.get("url", "").endswith("/images/big/1.webp")
          and c.get("marketplace") == "wildberries" and c.get("rank") == 3
          and "оператор" in (c.get("license") or "") and c.get("nm_id") == 329471133)
    check("H4 discover_shape", ok, "cand=%r" % c)


# ── H5 · нет wb_scout → пусто, без падения ──────────────────────────────────────────
def h5():
    saved = H.HAVE_WB
    H.HAVE_WB = False
    try:
        out = H.discover("что угодно")
        check("H5 discover_wb_absent", out == [], "got %r" % out)
    finally:
        H.HAVE_WB = saved


# ── H6 · честный 'unknown' с недоверенного хоста ────────────────────────────────────
def h6():
    png = _png_bytes()
    if png is None:
        check("H6 honest_unknown", True, "PIL нет — стадия пропущена честно")
        return
    H.fetch_bytes = lambda url, **k: (png, "image/png")
    r = H.check_photo("https://basket-20.wbbasket.ru/vol1/part1/1/images/big/1.webp",
                      facts={}, use_cache=False)
    check("H6 honest_unknown", r["verdict"] != "good", "verdict=%s (не должно быть good)" % r["verdict"])


# ── H7 · реестр чистых хостов даёт право на good ────────────────────────────────────
def h7():
    src = {"categories": {"упаковка": {"known_clean_shops": ["wbbasket.ru"]}}, "brands": {}}
    clean = H.host_is_clean("basket-20.wbbasket.ru", src)
    dirty = H.host_is_clean("basket-20.wbbasket.ru", {"categories": {}, "brands": {}})
    check("H7 trusted_registry", clean is True and not dirty, "clean=%s dirty=%s" % (clean, dirty))


# ── H8 · find: провенанс + порядок direct_links ─────────────────────────────────────
def h8():
    try:
        H.discover = lambda q, **k: [
            {"url": "u_good", "nm_id": 1, "name": "A", "marketplace": "wildberries",
             "source_kind": "other_shop", "product_url": "p1", "license": "L", "price_rub": 10,
             "confidence": 1.0, "vendor_code": "VC-A"},
            {"url": "u_unk", "nm_id": 2, "name": "B", "marketplace": "wildberries",
             "source_kind": "other_shop", "product_url": "p2", "license": "L", "price_rub": 20,
             "confidence": 0.2, "vendor_code": None},
        ]
        H.hunt = lambda urls, **k: {
            "good": [{"url": "u_good", "why": "ok"}],
            "unknown": [{"url": "u_unk", "why": "?"}],
            "bad": [], "need": k.get("need", 5), "got": 1, "enough": False, "capabilities": {},
        }
        out = H.find("q", need=5)
        prov = out["good"][0].get("provenance", {})
        prov_ok = prov.get("name") == "A" and prov.get("confidence") == 1.0 and prov.get("vendor_code") == "VC-A"
        order_ok = out["direct_links"] == ["u_good", "u_unk"]
        check("H8 find_wiring_order", prov_ok and order_ok,
              "prov=%r links=%r" % (prov, out.get("direct_links")))
    finally:
        H.discover, H.hunt = _ORIG_DISCOVER, _ORIG_HUNT


# ── H9 · матчер: число-габарит как отпечаток ────────────────────────────────────────
def h9():
    hit = H.match_facts("ВПП плёнка 0.3x100", "плёнка воздушно пузырьковая 0,3х100 м рулон")
    miss = H.match_facts("ВПП плёнка 0.3x100", "плёнка воздушно пузырьковая 0,5х50 м рулон")
    ok = (hit["has_specs"] and hit["score"] > miss["score"]
          and "100" in hit["nums_hit"] and "100" in miss["nums_miss"])
    check("H9 matcher_numeric", ok, "hit=%.3f miss=%.3f" % (hit["score"], miss["score"]))


# ── H10 · разбор card.json (options + grouped_options + media + brand) ──────────────
def h10():
    fake_card = {
        "imt_name": "Плёнка воздушно-пузырьковая ВПП-2-63 0,3х100 м",
        "vendor_code": "ВПП-2-63/0.3X100М",
        "description": "рулон для упаковки",
        "options": [{"name": "Длина", "value": "100 м"}],
        "grouped_options": [{"group_name": "Упаковка",
                             "options": [{"name": "Ширина рулона", "value": "0.3 м"}]}],
        "media": {"photo_count": 5},
        "selling": {"brand_name": "Бета-Куверт"},
    }
    info = H.wb_card_info(329471133, fetch=lambda url: fake_card)  # vol 3294 в затравке → без зонда
    opts = dict(info.get("options") or [])
    ok = (info.get("imt_name", "").startswith("Плёнка")
          and info.get("vendor_code") == "ВПП-2-63/0.3X100М"
          and info.get("photo_count") == 5
          and "Длина" in opts and "Ширина рулона" in opts
          and info.get("brand") == "Бета-Куверт")
    check("H10 card_info_parse", ok, "info=%r" % info)


# ── H11 · deepen: card.json поднимает сверку, когда габарита нет в имени ─────────────
def h11():
    # message-4: 0,3×100 живёт в card.json (vendor_code/imt_name), а НЕ в имени выдачи.
    fake = [{"id": 329471133, "name": "Плёнка ВПП рулон", "pics": 1, "salePriceU": 149000}]
    H._wb = types.SimpleNamespace(scan_category=lambda **k: fake, _price_rub=lambda p: 1490.0)
    H.HAVE_WB = True
    H._wb_probe_webp = lambda u, timeout=10: True
    H._wb_fetch_card = lambda url, timeout=12: {
        "imt_name": "Плёнка воздушно-пузырьковая ВПП 0,3х100 м",
        "vendor_code": "ВПП-2-63/0.3X100М", "description": "", "options": [],
        "media": {"photo_count": 1}, "selling": {},
    }
    q = "ВПП плёнка 0.3x100"
    shallow = H.discover(q, limit_products=3, pics_per=1, deepen=False)
    deep = H.discover(q, limit_products=3, pics_per=1, deepen=True)
    cs = shallow[0]["confidence"] if shallow else -1.0
    cd = deep[0]["confidence"] if deep else -1.0
    vc = deep[0].get("vendor_code") if deep else None
    check("H11 deepen_cardjson_rerank", cd > cs and cd >= 0.9 and vc == "ВПП-2-63/0.3X100М",
          "shallow=%.3f deep=%.3f vendor=%s" % (cs, cd, vc))


# ── H12 · закон компрометации: маркетплейс/продавец = compromise, опт = только грязь ─
def h12():
    markers = {"domains": ["wildberries", "ozon"],
               "seller_marks": ["продавец", "ооо "], "phrases": ["опт", "доставка"]}
    sv_tess, sv_run, sv_pil = H.have_tesseract, H.subprocess.run, H.HAVE_PIL
    H.have_tesseract = lambda: True
    H.HAVE_PIL = False  # отдать raw в "tesseract" без PIL-нормализации

    def ocr(text):
        c = types.SimpleNamespace()
        c.stdout = text.encode("utf-8")
        c.returncode = 0
        return c

    try:
        H.subprocess.run = lambda *a, **k: ocr("отличное качество wildberries магазин")
        ok_m, d_m = H.stage2_letters(b"x", markers)
        H.subprocess.run = lambda *a, **k: ocr("супер опт быстрая доставка")
        ok_o, d_o = H.stage2_letters(b"x", markers)
        ok = (ok_m is False and d_m["compromise"] is True
              and ok_o is False and d_o["compromise"] is False)
        check("H12 compromise_law", ok, "market=%s/%s opt=%s/%s"
              % (ok_m, d_m["compromise"], ok_o, d_o["compromise"]))
    finally:
        H.have_tesseract, H.subprocess.run, H.HAVE_PIL = sv_tess, sv_run, sv_pil


# ── H13 · граница чистого хоста: подмена/приклейка НЕ проходит за доверенный ──────────
def h13():
    # ЗАКОН ЧЕСТНОСТИ (фикс 1): host_is_clean раньше матчил подстрокой — 'example-shop.ru'
    # ложно доверял бы 'example-shop.ru.evil.com' и 'fakeexample-shop.ru'. Теперь — граница хоста.
    src = {"categories": {"упаковка": {"known_clean_shops": ["example-shop.ru"]}}, "brands": {}}
    exact = H.host_is_clean("example-shop.ru", src)          # сам хост
    sub = H.host_is_clean("cdn.example-shop.ru", src)        # поддомен чистого → чистый
    spoof = H.host_is_clean("example-shop.ru.evil.com", src)  # приписан суффикс → чужой
    prefix = H.host_is_clean("fakeexample-shop.ru", src)      # приклеен префикс → чужой
    ok = (exact is True and sub is True and not spoof and not prefix)
    check("H13 host_boundary_no_spoof", ok,
          "exact=%s sub=%s spoof=%s prefix=%s" % (exact, sub, spoof, prefix))


# ── H14 · OCR недоступен на чистом хосте → 'unknown', НИКОГДА 'good' ──────────────────
def h14():
    # ЗАКОН ЧЕСТНОСТИ (фикс 3): даже доверенный источник + зрение-ок, но буквы НЕ проверены
    # (OCR недоступен, ok2=None) → компромат на пикселях машиной не исключён → не 'good'.
    # ЖЕЛЕЗО бракует крошечные файлы (плоская заливка жмётся в ~5 КБ = «превью»). Нужен
    # весомый кадр: шум не сжимается → байтов достаточно, чтобы дойти до буквенно-зрительного пути.
    png = _noisy_png()
    if png is None:
        check("H14 ocr_missing_not_good", True, "PIL нет — стадия пропущена честно")
        return
    sv_fetch, sv_s2, sv_s3 = H.fetch_bytes, H.stage2_letters, H.stage3_vision
    H.fetch_bytes = lambda url, **k: (png, "image/png")
    H.stage3_vision = lambda raw, facts: (True, {"why": "товар опознан"})
    try:
        # OCR недоступен → ok2=None, compromise=False
        H.stage2_letters = lambda raw, markers: (None, {"why": "OCR недоступен", "compromise": False, "text": ""})
        r_none = H.check_photo("https://clean.example/p.webp", facts={}, trusted=True, use_cache=False)
        # КОНТРОЛЬ: те же условия, но буквы ПРОВЕРЕНЫ (ok2=True) → тот же путь рождает 'good'
        H.stage2_letters = lambda raw, markers: (True, {"why": "буквы чисты", "compromise": False, "text": ""})
        r_ok = H.check_photo("https://clean.example/p.webp", facts={}, trusted=True, use_cache=False)
        ok = (r_none["verdict"] == "unknown" and r_ok["verdict"] == "good")
        check("H14 ocr_missing_not_good", ok,
              "ocr_none=%s ocr_ok=%s" % (r_none["verdict"], r_ok["verdict"]))
    finally:
        H.fetch_bytes, H.stage2_letters, H.stage3_vision = sv_fetch, sv_s2, sv_s3


# ── H15 · чёрный список ДО кэша + версия ключа снимает тухлый вердикт ─────────────────
def h15():
    # ЗАКОН ЧЕСТНОСТИ (фикс 2): (а) хост в блок-листе → 'bad' даже если кэш под точным ключом
    # говорит 'good' (блок главнее кэша); (б) ужесточили критерии → старый ключ промахивается.
    import hashlib
    import json as _json

    def _key(url, crit, markers, blocked):
        ver = hashlib.sha1(_json.dumps({"c": crit, "m": markers, "b": blocked},
                                       sort_keys=True, ensure_ascii=False).encode("utf-8")
                           ).hexdigest()[:8]
        return hashlib.sha1(("%s|%s" % (url, ver)).encode("utf-8")).hexdigest()[:16]

    sv_src, sv_lc, sv_sc, sv_fetch = H.load_sources, H.load_cache, H.save_cache, H.fetch_bytes
    crit = {"min_side_px": 500, "formats": ["webp", "png"]}
    markers = {"domains": ["wildberries"], "seller_marks": [], "phrases": []}
    try:
        # (а) блок-лист главнее закэшированного 'good'
        blocked = {"blocked.example": "тест-блок"}
        src_a = {"criteria": crit, "watermark_markers": markers, "blocked_hosts": blocked,
                 "categories": {}, "brands": {}}
        url_b = "https://blocked.example/p.webp"
        planted_a = {_key(url_b, crit, markers, blocked): {"url": url_b, "verdict": "good", "why": "planted"}}
        H.load_sources = lambda: src_a
        H.load_cache = lambda: planted_a
        H.save_cache = lambda c: None
        H.fetch_bytes = lambda u, **k: (_ for _ in ()).throw(AssertionError("сеть не должна дёргаться при блоке"))
        r_block = H.check_photo(url_b, use_cache=True)
        block_wins = (r_block["verdict"] == "bad" and not r_block.get("from_cache"))

        # (б) версия ключа: запись под ПРЕЖНИМИ критериями промахивается после ужесточения
        url_n = "https://neutral.example/x.webp"
        old_crit = {"min_side_px": 500, "formats": ["webp", "png"]}
        new_crit = {"min_side_px": 9999, "formats": ["webp", "png"]}  # ужесточили → ключ иной
        src_b = {"criteria": new_crit, "watermark_markers": markers, "blocked_hosts": {},
                 "categories": {}, "brands": {}}
        planted_b = {_key(url_n, old_crit, markers, {}): {"url": url_n, "verdict": "good", "why": "stale"}}
        H.load_sources = lambda: src_b
        H.load_cache = lambda: planted_b
        H.fetch_bytes = lambda u, **k: (None, None)  # промах → идём в fetch → raw None → 'bad'
        r_stale = H.check_photo(url_n, use_cache=True)
        stale_ignored = (r_stale["verdict"] != "good" and not r_stale.get("from_cache"))

        check("H15 blocklist_before_cache+versioned_key", block_wins and stale_ignored,
              "block=%s/%s stale=%s/%s" % (r_block.get("verdict"), r_block.get("from_cache"),
                                           r_stale.get("verdict"), r_stale.get("from_cache")))
    finally:
        H.load_sources, H.load_cache, H.save_cache, H.fetch_bytes = sv_src, sv_lc, sv_sc, sv_fetch


# ── H16 · дедлайн режет бесконечный резолв неизвестного vol ─────────────────────────
def h16():
    """Резолвер для НЕизвестного vol без дедлайна пробует до 60 соседей по `probe` каждый
    (в худшем случае десятки минут на SKU — висение «долго и мучительно»). С deadline резолв
    обязан остановиться и вернуть None в пределах потолка, а НЕ жечь все 60 зондов. Кэш-хит и
    само-коррекция (H1–H3) не трогаются: дедлайн срабатывает ТОЛЬКО когда баскет неизвестен."""
    import time as _t

    def slow_probe(u, sleep=0.06):
        _t.sleep(sleep)   # каждая попытка «дорогая», как реальный сетевой зонд ~10с в масштабе
        return False

    unknown_nm = 999999991  # vol=9999 — в затравке НЕТ → полный пробой соседей
    t0 = _t.monotonic()
    got = H._wb_resolve_basket(unknown_nm, probe=slow_probe, deadline=0.3)
    dt = _t.monotonic() - t0

    # без дедлайна: 60 соседей × 0.06с = 3.6с (в реальности 60×10с = 600с). С дедлайном 0.3с:
    timed_out = got is None and dt < 1.0
    check("H16 basket_resolve_deadline", timed_out,
          "got=%r dt=%.2f (ожидали None и dt<1.0, без дедлайна было бы ~3.6с)" % (got, dt))


if __name__ == "__main__":
    print("ФОТО-ИСКАТЕЛЬ · ПРИЁМКА добытчика (оффлайн, 0₽):")
    tests = (h1, h2, h3, h4, h5, h6, h7, h8, h9, h10, h11, h12, h13, h14, h15, h16)
    for fn in tests:
        try:
            fn()
        except Exception as e:
            check(fn.__name__, False, "исключение: %s: %s" % (type(e).__name__, e))
    print("\nИТОГ: %d/%d зелёных" % (len(tests) - len(FAILED), len(tests)))
    sys.exit(1 if FAILED else 0)

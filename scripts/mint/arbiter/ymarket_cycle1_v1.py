#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЦИКЛ-1 · ДВИЖОК (ymarket_cycle1_v1) — «Идея → Товар → Витрина» как законная цепь узлов.

Ручной проход 2026-09-02 ДОКАЗАН живьём (ARB-* плёнка на витрине Express Atlas): этот движок
выражает его в виде НЕПРЕРЫВНОЙ цепочки узлов с законным PASS-гейтингом (L12: НЕТ fake pass —
узел N+1 стартует только после PASS N с доказательством чтением живого состояния, 200 OK врёт).

Законы движка (канон YM_CYCLE1_V1.md §13):
- L8  бренд = «Без бренда» (YM не индексирует «ATLAS EDGE»), своё описание/параметры, свой EAN.
- L9  цена = владелец ЦЕНОВИК (MARKUP из манифеста), товар НИ В КАКИХ акциях в цикл-1.
- L10 ОВХ = правдивая транспортная упаковка с карточки донора.
- L11 фото: товар + фирменная инфографика (color-science) — артефакт органа.
- L6  RUBICON: WRITE только не dry AND commit; движок сам ничего не шлёт в dry.
- L13 задачи, не вопросы: манифест магазина решает, что делать; оператор отвечает только на вход.
- L14 планёрка = самоосознание: утренний узел собирает вчерашний леджер в ПУЛЬС.

Запуск:  python3 ymarket_cycle1_v1.py [--store atlas-express-film] [--dry|--commit] [--plenerka]
Хеш цикла = sha1(магазин × дата × версия цепи) — 10/100 магазинов живут параллельно, каждый свой.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import pathlib
import sys
import time

ARB = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ARB))

CHAIN_VERSION = "film-1.0"
CYCLE_SETTLE_SEC = 90            # ЯМ пишет оффер-маппинги асинхронно ~50-110с (write_v1.reconcile
                                 # settle_wait=90): СВЕРКА даёт платформе осесть ПОСЛЕ живого залива,
                                 # иначе свежий контент не прочитается и даст ложный FAIL/дрейф цены.
STORE_DEFAULT = "atlas-express-film"
WAREHOUSE_DEFAULT = 2390811          # Atlas «Atlas» (склад Экспресс кабинета 216949599)

# Канонический вход для НОВОГО магазина (L13: без этого запуск невозможен, но вопросы НЕ задаём —
# манифест отвечает; если манифеста нет — честно говорим, чего не хватает):
REQUIRED_STORE_FIELDS = [
    ("slug",            "короткое имя магазина (alnum, через дефис)"),
    ("business_id",     "businessId кабинета (партнёрский API)"),
    ("campaign_id",     "campaignId ЭКСПРЕСС-магазина (витрина)"),
    ("warehouse_id",    "partnerWarehouseId склада (куда едет курьер)"),
    ("donor_category",  "категория донора (URL-путь suppliers/…_v1.py, напр. vozdushno-puzyrkovaya-plenka)"),
    ("builder",         "сборщик полной карточки (film | box | …)"),
    ("markup",          "MARKUP цены: цена = закупка × markup (владелец — ЦЕНОВИК, L9)"),
    ("stock_count",     "остаток на витрине (L3: донор-real или слово оператора; не выдумываем)"),
]
# Ключ API — ВСЕГДА из env, никогда в манифесте/файле (RUBICON секретов).


# ─────────────────────────────────────────────────────────────────────────────
#  МАНИФЕСТ МАГАЗИНА + ХЕШ ЦИКЛА
# ─────────────────────────────────────────────────────────────────────────────

def _now_msk():
    # локальное время машины (MSK на хосте оператора); для меток пульса
    return time.strftime("%H:%M:%S")


def store_profiles_path():
    return ARB / "runtime" / "cycle1" / "stores.json"


def load_store(slug):
    """Манифест магазина. Нет → вернуть None + список недостающего (канонический вход)."""
    p = store_profiles_path()
    if not p.exists():
        return None
    doc = json.loads(p.read_text())
    return doc.get(slug)


def save_store(profile):
    p = store_profiles_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = json.loads(p.read_text()) if p.exists() else {}
    doc[profile["slug"]] = profile
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1))


# ─────────────────────────────────────────────────────────────────────────────
#  МАМА-НАСЛЕДОВАНИЕ + РЕЕСТР (кабинет-agnostic вход нового магазина)
#
#  «ЦИКЛ-1 ищет маму ЦИКЛ-ЯМ — хеш»: новому магазину не нужно повторять кабинет
#  (business_id/campaign_id/warehouse_id) и API — он объявляет mother=<slug матери>
#  и наследует кабинет от неё. Системе «пофиг какой API/кабинет» — она подтягивается.
# ─────────────────────────────────────────────────────────────────────────────

INHERIT_FIELDS = ("business_id", "campaign_id", "warehouse_id")   # кабинет: наследуем от мамы
BUILDERS = ("film", "box", "tape")                                  # известные сборщики полной карточки


def _builder(ctx):
    """Модуль-сборщик по манифесту магазина (builder → ymarket_*_cards_v1).

    Один источник диспатча для N1 (скан донора), N2 (сборка) и twin-гарда: tape → ленточный
    орган (физ-отпечаток ширина|длина, вариант цвет|мкм); всё прочее — плёночный эталон
    байт-в-байт (film) / задел (box). Незнакомый builder уже отсечён валидацией манифеста."""
    if (ctx.get("profile") or {}).get("builder") == "tape":
        import ymarket_tape_cards_v1 as FC
        return FC
    import ymarket_film_cards_v1 as FC
    return FC


def _load_all():
    """Все манифесты магазинов (dict slug→profile). Нет файла → {}."""
    p = store_profiles_path()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def resolve_profile(profile, all_profiles=None):
    """До-заполнить недостающие кабинетные поля ребёнка от МАТЕРИ (mother).

    Чистая функция (тестируется без файла). Идём по цепочке mother до глубочайшей
    мамы; от неё берём INHERIT_FIELDS, которые ребёнок не задал (поля ребёнка
    приоритетнее — явный кабинет у ребёнка перекрывает наследие).
    Возвращает (профиль_или_None, причина_ошибки_или_None).
    """
    if profile is None:
        return None, "профиль не найден"
    all_profiles = all_profiles if all_profiles is not None else _load_all()
    chain = []
    cur = profile
    while cur.get("mother"):
        slug = cur.get("slug")
        if slug in chain:
            return None, "цепь mother замкнута: " + " → ".join(chain + [slug])
        chain.append(slug)
        mom = (all_profiles or {}).get(cur.get("mother"))
        if not mom:
            return None, (f"mother «{cur.get('mother')}» отсутствует в манифесте "
                          f"(нужна магазину «{cur.get('slug')}»); есть: "
                          f"{', '.join((all_profiles or {}).keys()) or '—'}")
        cur = mom
    out = dict(profile)
    src = cur  # глубочайшая мама — источник кабинета
    for key in INHERIT_FIELDS:
        if out.get(key) is None and src.get(key) is not None:
            out[key] = src[key]
    if src.get("slug") and src["slug"] != out.get("slug"):
        out["_inherited_from"] = src["slug"]
    return out, None


def list_cycles():
    """Реестр магазинов для мозга/глаз: slug → сборщик/донор/мама/кабинет и статус резолва."""
    doc = _load_all()
    out = {}
    for slug, prof in doc.items():
        resolved, why = resolve_profile(prof, doc)
        out[slug] = {
            "slug": slug,
            "mother": prof.get("mother"),
            "builder": prof.get("builder"),
            "builder_slug": prof.get("builder_slug"),
            "donor_category": prof.get("donor_category"),
            "markup": prof.get("markup"),
            "stock_count": prof.get("stock_count"),
            "resolve_ok": resolved is not None,
            "resolve_why": why,
            "inherited_from": (resolved or {}).get("_inherited_from"),
            "cabinet": {k: (resolved or {}).get(k) for k in INHERIT_FIELDS},
        }
    return out


def add_store(profile):
    """Добавить новый магазин в манифест (Л13: задачи, не вопросы). Без сети.

    Кабинет не выдумываем: если у магазина нет ни одного кабинетного поля и не задан
    mother — по умолчанию наследуем от STORE_DEFAULT (мать-цикл). Валидация до записи;
    файл трогается ТОЛЬКО на полном успехе. Возвращает (ok: bool, reason: str).
    """
    slug = profile.get("slug")
    if not slug or not all(ch.isalnum() or ch in "-_" for ch in slug):
        return False, f"slug «{slug}» недопустим (только буквы/цифры/дефис/подчёркивание)"
    doc = _load_all()
    if slug in doc:
        return False, f"магазин «{slug}» уже есть в манифесте ({store_profiles_path()})"
    prof = dict(profile)
    prof["slug"] = slug
    mother = prof.get("mother")
    has_cabinet = any(prof.get(k) is not None for k in INHERIT_FIELDS)
    if not mother and not has_cabinet and STORE_DEFAULT in doc:
        prof["mother"] = mother = STORE_DEFAULT
    if mother and mother not in doc:
        return False, f"mother «{mother}» нет в манифесте (есть: {', '.join(doc) or '—'})"
    if prof.get("builder") not in BUILDERS:
        return False, f"builder «{prof.get('builder')}» неизвестен (есть: {', '.join(BUILDERS)})"
    resolved, why = resolve_profile(prof, doc)
    if resolved is None:
        return False, why or "резолв кабинета от мамы не удался"
    missing = [k for k, _ in REQUIRED_STORE_FIELDS if resolved.get(k) is None]
    if missing:
        return False, f"не хватает полей после наследования: {missing}"
    save_store(prof)
    src = resolved.get("_inherited_from")
    return True, f"магазин «{slug}» добавлен" + (f"; кабинет унаследован от «{src}»" if src else "")


def cycle_hash(store_slug, date_str):
    """Уникальный хеш прогона: (магазин × дата × версия цепи). Позволяет вести N циклов параллельно."""
    return hashlib.sha1(f"{store_slug}|{date_str}|{CHAIN_VERSION}".encode()).hexdigest()[:10]


def ledger_path(store_slug, date_str):
    d = ARB / "runtime" / "cycle1" / store_slug
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{date_str}.jsonl"


def pulse_path(store_slug):
    d = ARB / "runtime" / "cycle1" / store_slug
    d.mkdir(parents=True, exist_ok=True)
    return d / "last_pulse.json"


def plannerka_read(store_slug):
    """Пульс магазина как dict (None, если ещё нет). Для мозга/глаз без прогона цепи."""
    p = pulse_path(store_slug)
    if not p.exists():
        return None
    return json.loads(p.read_text())


# ─────────────────────────────────────────────────────────────────────────────
#  ПУЛЬС В ТЕРМИНАЛЕ (живая строка на каждый узел)
# ─────────────────────────────────────────────────────────────────────────────

_C = {"grn": "\033[32m", "red": "\033[31m", "yel": "\033[33m", "cyn": "\033[36m",
      "blu": "\033[34m", "dim": "\033[2m", "rst": "\033[0m", "b": "\033[1m"}


def _c(color, s):
    return f"{_C.get(color, '')}{s}{_C['rst']}"


def pulse_line(node_name, verdict, note, ms, i, n):
    icon = {"PASS": "✓", "FAIL": "✗", "DRY": "◌", "SKIP": "–"}.get(verdict, "?")
    col = {"PASS": "grn", "FAIL": "red", "DRY": "yel", "SKIP": "dim"}.get(verdict, "yel")
    step = f"[{i:02d}/{n:02d}]" if n else ""
    return f"  {_c(col, icon)} {_c('b', node_name):<14} {_c('dim', step):<9} {note}  {_c('dim', f'{ms:>6.0f}мс')}"


def _echo_tail(buf, node_name, tail=14):
    """Тишина не прячет ошибку: на FAIL показать низ захваченного вывода узла (последние строки)."""
    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    if not lines:
        return
    print(f"\n    {_c('dim', '──── низ вывода узла «' + node_name + '» (полный поток: --verbose):')}")
    for ln in lines[-tail:]:
        print(f"    {_c('dim', ln)}")


# ─────────────────────────────────────────────────────────────────────────────
#  ЗАКОН БРЕНДА (L8) — общий трансформер полной карточки
# ─────────────────────────────────────────────────────────────────────────────

def brand_law(prod):
    """YM не индексирует незарегистрированный бренд → «Без бренда» (эталон 99).
    no-brand = бренд не заявляем НИГДЕ: поле / суффикс имени / описание."""
    prod["vendor"] = "Без бренда"
    prod["send_vendor"] = True
    prod["unique_name"] = False
    prod.pop("house_brand", None)
    d = prod.get("description") or ""
    if d:
        prod["description"] = d.replace("Воздушно-пузырьковая плёнка ATLAS EDGE",
                                        "Воздушно-пузырьковая плёнка")
    return prod


# ─────────────────────────────────────────────────────────────────────────────
#  ФИЗ-БЛИЗНЕЦ НА ВИТРИНЕ (#38 · «в след раз создай без ошибки»)
#  Гард против ошибки создания 2026-09-02: один физический рулон продавался ДВАЖДЫ —
#  легаси 9601515-1 и ARB-29846713 (оба 0.3×50 м, трёхслойная, 60 г/м²), но под разными
#  offerId/своими EAN. СВЕРКА (N6) видит только СВОИ манифест-sku → чужого близнеца под
#  другим offerId не замечает, а matrix/registry/library дедупят ПОСТ-фактум. Поэтому гард
#  ПРЕД-заливной, в СБОРКЕ (N2): сравниваем физ-отпечаток задумки с УЖЕ-живой витриной и
#  НЕ даём PASS, если тот же товар уже продаётся. Отпечаток — из ХАРАКТЕРИСТИК (_spec /
#  parameterValues), не из имени (имена донора и наши — разные стили; norm_key имени и
#  вырождался). Читается и в dry (сухой прогон идёт по тому же кабинету, как СВЕРКА) →
#  оператор видит близнеца ДО слова на --commit.
# ─────────────────────────────────────────────────────────────────────────────

# Физ-поля, делающие рулон ТЕМ ЖЕ товаром на полке (ключи _build_spec / категория 76346336).
_TWIN_FIELDS = ("ширина_м", "длина_м", "плотность_г_м2", "слои", "материал")
# parameterId живого offer-cards → то же поле (ключи из ymarket_cats_v1.json / комментариев
# film_cards: 23679910 ширина · 51734601 длина намотки · 34439870 плотность · 27141751 слои ·
# 17352854 материал · 13887626 цвет). У других билдеров категории будет свой map — константа локальна к плёнке.
_TWIN_LIVE_PID = {23679910: "w", 51734601: "l", 34439870: "d", 27141751: "слои", 17352854: "материал",
                  13887626: "цвет"}


# ── ВАРИАНТ (цвет/перфорация) — расширение физ-ключа 2026-09-08 (#38-грань) ────────────────
# Категория дона продаёт ОДИН размер/плотность в нескольких РАЗНЫХ товарах: прозрачный «Компакт» vs
# чёрный «Black bubble», сплошная vs «с перфорацией». Базовый ключ (ширина|длина|плотность|слои|материал)
# их сливает → гард останавливал ЗАКОННЫЕ варианты как «один рулон». Вариант разводит: тот же базовый
# отпечаток, но другой цвет ИЛИ перфорация = НЕ близнец (своя карточка/фото/EAN на полке). Настоящий
# дубль (тот же артикул, тот же цвет/перфорация) ловится как раньше — ключ стал ТОЛЬКО детальнее.
# Правило сверки «уточняем, когда знают ОБА»: не знаем цвет живого легаси (нет параметра) → не
# расходимся → близнец не снимается (честно: не доказано различие → не заливаем).

def _twin_variant(pr, builder=None):
    """Задумка (_spec) → вариант (цвет, …) как есть; неизвестно → None (не разводит).
    Builder-хук (tape: (цвет-семья, мкм)) приоритетнее; плёночный фолбэк — байт-в-байт."""
    hook = getattr(builder, "twin_variant", None) if builder is not None else None
    if hook is not None:
        return hook(pr)
    sp = pr.get("_spec") or {}
    col = (str(sp.get("цвет") or "").strip().lower()) or None
    per = str(sp.get("перфорация") or "").strip().lower()
    per = per if per in ("да", "нет") else None
    return (col, per)


def _twin_variant_live(pv_list, builder=None):
    """Живой offer-cards (parameterValues) → вариант (цвет, …). Builder-хук приоритетнее;
    плёночный фолбэк — байт-в-байт (перфорации в параметрах нет → None → не разводит)."""
    hook = getattr(builder, "twin_variant_live", None) if builder is not None else None
    if hook is not None:
        return hook(pv_list)
    got = {}
    for pv in pv_list or []:
        if pv.get("parameterId") == 13887626:
            got["цвет"] = pv.get("value")
    col = (str(got.get("цвет") or "").strip().lower()) or None
    return (col, None)


def _variant_match(vA, vB):
    """True = варианты НЕ доказывают различие (совпадают или один неизвестен) → близнец возможен.
    False = ОБА знают поле и оно РАЗНОЕ → это разные товары, близнеца НЕТ."""
    for a, b in zip(vA, vB):
        if a is not None and b is not None and a != b:
            return False
    return True


def _norm_roll_w(w):
    """Ширина рулона к метрам: ARB-заливка шлёт метры (0.3), легаси-заливка слала см (30) —
    тот же физический рулон. Значение > 5 м для рулона плёнки нереально → это см → /100."""
    return w / 100.0 if w > 5 else w


def _twin_spec_key(pr, builder=None):
    """Задумка (_spec) → физ-ключ '0.3|50|60|трехслойная|полиэтилен'; нечем/бито → None.
    Builder-хук (tape: 'ширина|длина') приоритетнее; плёночный фолбэк — байт-в-байт
    (ё→е: легаси «трёхслойная» в имени ≠ значение параметра «трехслойная» — нормируем оба)."""
    hook = getattr(builder, "twin_spec_key", None) if builder is not None else None
    if hook is not None:
        return hook(pr)
    sp = pr.get("_spec") or {}
    if not sp:
        return None
    try:
        w, l, d = float(sp.get("ширина_м")), float(sp.get("длина_м")), float(sp.get("плотность_г_м2"))
    except (TypeError, ValueError):
        return None
    if not (w > 0 and l > 0 and d > 0):
        return None
    слои = str(sp.get("слои") or "").strip().replace("ё", "е")
    мат = str(sp.get("материал") or "").strip().lower()
    if not слои or not мат:
        return None
    return "|".join([f"{_norm_roll_w(w):g}", f"{l:g}", f"{d:g}", слои, мат])


def _twin_live_key(pv_list, builder=None):
    """Живой offer-cards (parameterValues) → тот же физ-ключ; параметров нет → None.
    Builder-хук (tape: PID 34439430/23674610) приоритетнее; плёночный фолбэк — байт-в-байт."""
    hook = getattr(builder, "twin_live_key", None) if builder is not None else None
    if hook is not None:
        return hook(pv_list)
    got = {}
    for pv in pv_list or []:
        k = _TWIN_LIVE_PID.get(pv.get("parameterId"))
        if k:
            got[k] = pv.get("value")
    if not ({"w", "l", "d"} <= set(got)):
        return None
    try:
        w, l, d = float(got["w"]), float(got["l"]), float(got["d"])
    except (TypeError, ValueError):
        return None
    if not (w > 0 and l > 0 and d > 0):
        return None
    слои = str(got.get("слои") or "").strip().replace("ё", "е")
    мат = str(got.get("материал") or "").strip().lower()
    if not слои or not мат:
        return None
    return "|".join([f"{_norm_roll_w(w):g}", f"{l:g}", f"{d:g}", слои, мат])


def _vitrine_offers(bid, cid, builder=None):
    """0₽ GET: живые офферы кампании → (все offerId, {offerId: (физ-ключ, вариант)}). Оффер без
    карточки (не заполнен/заморожен) ключа не даёт — не с чем сравнить; сбой чтения НЕ глотаем:
    гард — не обогащение (ср. offer-cards в СВЕРКЕ fail-soft), а предохранитель: не доказали
    «близнеца нет» — не заливаем (см. node_build)."""
    import ymarket_hands_v1 as h
    offers = h.campaign_offers(cid, limit=200)
    entries = (offers.get("offers") if isinstance(offers, dict) else offers) or []
    ids = [str(o.get("offerId")) for o in entries if o.get("offerId")]
    keys = {}
    if ids:
        cards = h.offer_cards_status(bid, offer_ids=ids, limit=200)
        for c in cards or []:
            oid = str(c.get("offerId"))
            k = _twin_live_key(c.get("parameterValues"), builder)
            if oid and k:
                keys[oid] = (k, _twin_variant_live(c.get("parameterValues"), builder))
    return ids, keys


def _cand(pr, live, builder=None):
    """Кандидат манифеста → (sku, физ-ключ, вариант) для гарда; уже-живой/без ключа → None."""
    sku = pr.get("sku")
    if not sku or sku in live:          # уже-живая карточка манифеста — не «создание»
        return None
    k = _twin_spec_key(pr, builder)
    if not k:
        return None
    return (sku, k, _twin_variant(pr, builder))


def _twin_halt(prods, bid, cid, builder=None):
    """СБОРКА-гейт: собирается НОВАЯ карточка (её offerId ещё НЕ живёт), а её физический рулон уже
    продаётся на витрине под другим offerId → вторая карточка того же товара → вернуть {sku: [живые]}.
    ВАРИАНТ (цвет/перфорация) разводит: тот же размер/плотность, но другой цвет ИЛИ перфорация = НЕ
    близнец (разные товары дона, свои карточки). Пере-сбор УЖЕ-живых ARB-карточек (манифест
    идемпотентен) близнецом НЕ считается: их ассортимент на витрине, а оверлэп с легаси
    (9601515-1 vs ARB-29846713) — факт каталога оператора (доктрина refute_action), не ошибка
    СОЗДАНИЯ. Пусто = близнецов нет. Без кабинета (bid/cid) — инертно."""
    if not prods or not bid or not cid:
        return {}
    live_ids, fp_live = _vitrine_offers(bid, cid, builder)
    live = set(live_ids)
    cands = [c for c in (_cand(pr, live, builder) for pr in prods) if c]
    dup = {}
    # 1) новый кандидат против живой витрины (главная ловушка: добавили pid, чей рулон уже живой)
    for sku, k, v in cands:
        hits = sorted(o for o, (ok, ov) in fp_live.items()
                      if ok == k and _variant_match(v, ov))
        if hits:
            dup[sku] = hits
    # 2) кандидат против кандидата одной партии (два новых донора = один рулон)
    if not dup:
        seen = {}
        for sku, k, v in cands:
            prev = seen.get(k)
            if prev is not None:
                osku, ov = prev
                if _variant_match(v, ov):
                    dup.setdefault(sku, []).append(osku)
                    dup.setdefault(osku, []).append(sku)
            else:
                seen[k] = (sku, v)
    return dup


# ─────────────────────────────────────────────────────────────────────────────
#  ЦЕПЬ УЗЛОВ (каждый возвращает {verdict, note, evidence}; FAIL останавливает)
# ─────────────────────────────────────────────────────────────────────────────

def node_donor(ctx, dry, commit):
    """N1 ДОНОР · 0₽ GET · живой скан категории донора → партия выбранных товаров.

    donor_scope манифеста: нет/'live' → живые 4 (TARGET_PIDS) — как всегда, обратносовместимо;
    'new-rolls' → ВСЕ новые метражные рулоны донора КРОМЕ живых (расширение витрины на
    ассортимент). Под 'new-rolls' действует закон СКЛАДОВЩИКА: рулон, которого СЕЙЧАС нет у
    донора в наличии (под заказ/неизвестно), в партию НЕ входит — честный FAIL с причиной
    («под заказ» на Экспресс карточку не родит)."""
    FC = _builder(ctx)
    scope = (ctx["profile"].get("donor_scope") or "live")
    _loader = getattr(FC, "load_products", None) or FC.load_film_products
    raw = _loader(scope=scope)
    if not raw:
        return {"verdict": "FAIL", "note": "скан донора пуст", "evidence": {"n": 0, "scope": scope}}
    # target_pids манифеста: партия ровно эти артикулы (слово оператора 09.09 — перезалив
    # 13 скотч-карточек из файлов донора, не весь лист). Защита от того, что живая витрина
    # дона ушла вперёд/назад (500-флап 09.09) и партия «весь лист» залила бы чужие позиции.
    _tgt = ctx["profile"].get("target_pids")
    if _tgt:
        _tgt = {str(x) for x in _tgt}
        raw = [r for r in raw if str(r.get("pid") or r.get("sku")) in _tgt]
        if not raw:
            return {"verdict": "FAIL", "note": "target_pids не дали строк в наличии",
                    "evidence": {"n": 0, "scope": scope, "target": sorted(_tgt)}}
    if scope == "new-rolls":
        wait = [str(r.get("sku")) for r in raw if r.get("_stock") != "in_stock"]
        if wait:
            return {"verdict": "FAIL",
                    "note": "новые рулоны СЕЙЧАС НЕ в наличии у донора (закон СКЛАДОВЩИКА: "
                            f"под заказ/неизвестно на Экспресс не родит карточку): {sorted(wait)}",
                    "evidence": {"n": len(raw), "scope": scope, "not_in_stock": sorted(wait),
                                 "excluded_live": sorted(FC.TARGET_PIDS)}}
    ctx["raw_donor"] = raw
    pids = [str(r.get("pid") or r.get("sku")) for r in raw]
    note = f"донор {FC.DONOR_SLUG}: {len(raw)} строк"
    ev = {"n": len(raw), "pids": pids, "scope": scope,
          "excluded_live": sorted(FC.TARGET_PIDS) if scope == "new-rolls" else None}
    if scope == "new-rolls":
        note += (f" · новые метражные рулоны (без {len(FC.TARGET_PIDS)} живых) · "
                 f"у донора в наличии {len(raw)}")
    return {"verdict": "PASS", "note": note, "evidence": ev}


def node_build(ctx, dry, commit):
    """N2 СБОРКА · полная карточка по рецепту (факты донора → _spec + своё описание + ОВХ)
    + ПЛАН-АУДИТ полноты ДО залива (дыра №4 ревью): раньше неполная задумка уходила на витрину
    и ловилась только СВЕРКОЙ ПОСЛЕ трат — теперь известная дыра payload (нет ОВХ/описания/
    штрихкода/характеристик/цены) останавливает СБОРКУ. audit_plan = задумка; факт витрины
    подтвердит живая audit_live в СВЕРКЕ (CC3)."""
    FC = _builder(ctx)
    # #14-гейт манифеста ДО сборки: битый markup (boolean/не-число/≤1/пустая строка) раньше
    # тихо давал цену ≤ закупки (true→1.0) или падал сырым ValueError («abc») на середине
    # партии. Теперь — понятный FAIL с именем ПОЛЯ и магазина, до каких-либо действий.
    # markup=None → модульная MARKUP (8.0): обратносовместимо с профилями до проводки #13.
    _mk, _merr = FC.resolve_markup(ctx["profile"].get("markup"))
    if _merr:
        return {"verdict": "FAIL",
                "note": f"манифест «{ctx['profile'].get('slug')}»: {_merr}",
                "evidence": {"field": "markup", "profile_markup": ctx["profile"].get("markup"),
                             "error": _merr}}
    import ymarket_card_audit_v1 as caudit
    pub = FC._pub_urls_by_pid()
    # Новые рулоны (donor_scope=new-rolls) несут _og — главное публичное фото дона. Мёржим в pub:
    # живые 4 берут бренд-кадры (published_urls), новые — фото дона (слово оператора «фото из
    # донора», производная; провенанс зафиксирован в леджере залива). Live-путь (нет _og) — как
    # раньше, байт-в-байт.
    for _p in ctx.get("raw_donor") or []:
        _og = _p.get("_og")
        if _og:
            _pid = str(_p.get("pid") or _p.get("sku"))
            pub.setdefault(_pid, [])
            if _og not in pub[_pid]:
                pub[_pid].append(_og)
    prods, missing = [], []
    # Проводка ЦЕНОВИК·правил в движок (L9): множитель цены = манифест магазина (markup),
    # а не хардкод. Профиль.markup == модульной MARKUP (8.0) → поведение прежнее (обратносовместимо);
    # изменил профиль — изменилась цена партии без правки кода. Владелец поля — ЦЕНОВИК.
    # _mk уже резолвлен гейтом выше (один источник правды): валидный markup или модульная MARKUP,
    # вторая resolve_markup в build_product идемпотентна — баг-пассаж не перепроверяем.
    prof_markup = _mk
    for p in ctx["raw_donor"]:
        pr = FC.build_product(p, pub, 0, markup=prof_markup)
        if not pr:
            missing.append(str(p.get("pid")))
            continue
        brand_law(pr)
        prods.append(pr)
    ctx["prods"] = prods
    if missing:
        return {"verdict": "FAIL", "note": f"не собраны: {missing}",
                "evidence": {"missing": missing, "n_ok": len(prods)}}
    no_photo = [pr["sku"] for pr in prods if not pr.get("pictures")]
    if no_photo:
        # L11: карточка без фото = низкий index — честно не проходим (фото-слой обязателен).
        return {"verdict": "FAIL",
                "note": f"собрано {len(prods)} карточек, но фото нет: {no_photo}",
                "evidence": {"n": len(prods), "no_photo": no_photo}}
    no_ovx = [pr["sku"] for pr in prods if not pr.get("weightDimensions")]
    if no_ovx:
        # Закон оператора «габариты ВСЕГДА (не только вес)»: build_product отдаёт
        # weightDimensions ТОЛЬКО полным набором всех 4 — его отсутствие = payload СЕЙЧАС
        # уйдёт БЕЗ габаритов, и СВЕРКА его отвергнет. Не тратим залив вслепую (L10).
        return {"verdict": "FAIL",
                "note": f"карточки БЕЗ ОВХ-габаритов (залив пошёл бы слепым): {no_ovx}",
                "evidence": {"n": len(prods), "no_ovx": no_ovx}}
    # План-аудит задумки (audit_plan, 0₽): INCOMPLETE = известная дыра payload → FAIL до залива.
    # UNVERIFIED = поле не собрано адаптером → НЕ гейт, честно в заметке (CC2: не знаем ≠ нет).
    incomplete, unverified = {}, []
    n_complete = 0
    for pr in prods:
        v = caudit.audit_plan({
            "offer_id": pr.get("sku"), "name": pr.get("name"),
            "description_len": len(pr.get("description") or ""),
            "spec_n": len(pr.get("_spec") or {}), "dims": pr.get("weightDimensions"),
            "barcode": pr.get("barcode"), "n_photos": len(pr.get("pictures") or []),
            "price": pr.get("price")})
        if v["verdict"] == "INCOMPLETE":
            incomplete[pr.get("sku")] = {"missing": v["missing"], "note": v["note"]}
        elif v["verdict"] == "UNVERIFIED":
            unverified.append(pr.get("sku"))
        else:
            n_complete += 1
    if incomplete:
        return {"verdict": "FAIL",
                "note": "задумки НЕ полны (до залива): "
                        f"{ {s: d['missing'] for s, d in incomplete.items()} }",
                "evidence": {"incomplete": incomplete, "n_ok": len(prods)}}
    # ЦЕНОВИК·совет (advisory, 0₽): действующая цена против закупки и зоны. verdict
    # provisional — delivery=200/fee=0.15 TUNABLE НЕ подтверждены оператором → СОВЕТ,
    # НЕ PASS/FAIL-гейт (цикл не останавливает). Подсветит «закупка 300 → продаём 1300,
    # а не 2600-3000» — решение за оператором.
    import ymarket_price_rules_v1 as prules
    adv, adv_full = {}, {}
    for pr in prods:
        r = prules.recommend(pr.get("cost"), current_price=pr.get("price"), branded=True)
        v = r.get("verdict", "NA") if isinstance(r, dict) else "NA"
        adv[pr.get("sku")] = v
        if isinstance(r, dict):
            adv_full[pr.get("sku")] = {
                "verdict": v,
                "current": pr.get("price"),
                "floor": r.get("floor"),
                "recommended": r.get("recommended"),
                "provisional": r.get("provisional", False),
            }
    off = {s: v for s, v in adv.items() if v in ("RAISE", "SWEET", "ZONE_RAISE")}
    note = f"собрано {len(prods)} полных карточек (описание/спеки/ОВХ/EAN)"
    ev = {"n": len(prods), "plan_complete": n_complete, "pricing": adv,
          "pricing_full": adv_full}   # ЦЕНОВИК·полный разбор по карточке (пол/рекомендую/провиз.)

    # FLOOR-GUARD (#17/#34, манифест): price_floor / price_ceiling — ПРЯМЫЕ ₽-границы
    # оператора в манифесте магазина (не provisional-совет ЦЕНОВИКА выше — тот остаётся
    # подсказкой, а это явное слово: пол/потолок). НЕ заданы → цикл идёт как раньше
    # (обратносовместимо). Заданы → карточка за границей НЕ уходит на залив (честный FAIL
    # до трат), даже если markup валиден и сборка полна. Решение по TUNABLE-ценам остаётся
    # за оператором: он ставит числа в манифест — механизм включается.
    def _bounded_num(x):
        # ₽-граница из манифеста: int/float >0 (не bool, не nan/inf). Числовую СТРОКУ "1000"
        # коэрцим — resolve_markup строки-числа осознанно парсит (film_cards 227-234), значит и
        # пол обязан исполниться, а не молча погаснуть из-за кавычек (аудит price:387). Битое
        # ("abc"/bool/inf/nan) → None = граница не задана (инертно, обратносовместимо).
        if isinstance(x, bool):
            return None
        if isinstance(x, str):
            s = x.strip().replace(",", ".")
            try:
                v = float(s)
            except ValueError:
                return None
            x = v
        if isinstance(x, (int, float)) and x > 0 and x == x and abs(x) != float("inf"):
            return float(x)
        return None
    floor_raw = ctx["profile"].get("price_floor")
    ceil_raw = ctx["profile"].get("price_ceiling")
    floor_v = _bounded_num(floor_raw)
    ceil_v = _bounded_num(ceil_raw)
    floor_on, ceil_on = floor_v is not None, ceil_v is not None
    viol = {}
    for pr in prods:
        p = pr.get("price")
        if floor_on and not (isinstance(p, (int, float)) and p >= floor_v):
            viol.setdefault("below_floor", []).append({"sku": pr.get("sku"), "price": p})
        if ceil_on and not (isinstance(p, (int, float)) and p <= ceil_v):
            viol.setdefault("above_ceiling", []).append({"sku": pr.get("sku"), "price": p})
    # evidence хранит И сырьё (raw — что оператор реально записал), И эффективные числа
    # (floor/ceiling после коэрции) — чтобы «1000»-в-кавычках и настоящий 1000 были отличимы.
    ev["price_bounds"] = {"floor_raw": floor_raw, "ceiling_raw": ceil_raw,
                          "floor": floor_v, "ceiling": ceil_v, "enforced": bool(viol)}
    if viol:
        parts = []
        for kind, items in viol.items():
            who = ", ".join(f"{it['sku']} {it.get('price')}₽" for it in items)
            parts.append(f"{kind} ({who})" + (f" < пол {floor_v:g}" if kind == "below_floor"
                                             else f" > потолок {ceil_v:g}"))
        return {"verdict": "FAIL",
                "note": "цена за пределами границ манифеста: " + "; ".join(parts),
                "evidence": ev}

    # ФИЗ-БЛИЗНЕЦ (#38, «в след раз создай без ошибки»): пред-заливной дедуп против УЖЕ-живой
    # витрины (0₽ — те же читалки, что у СВЕРКИ; исполняется и в dry). Вооружён ТОЛЬКО когда
    # манифест знает кабинет (business_id/campaign_id) и ключ есть — юнит-тесты без кабинета
    # инертны (PASS как раньше, офлайн не трогаем). Чтение витрины упало → честный FAIL, а не
    # залив вслепую: не доказали «близнеца нет» — второй экземпляр того же товара не создаём
    # (ср. СВЕРКА: без живого чтения — НЕ PASS). Проверяет ТОЛЬКО создание НОВЫХ карточек;
    # уже-живые ARB-карточки манифеста (идемпотентный пере-сбор) не трогает.
    _bid = ctx["profile"].get("business_id")
    _cid = ctx["profile"].get("campaign_id")
    if _bid and _cid:
        try:
            import ymarket_hands_v1 as _hh
            _armed = bool(_hh.creds_present())
        except Exception:
            _armed = False
        if _armed:
            try:
                _dup = _twin_halt(prods, _bid, _cid, _builder(ctx))
            except Exception as _e:
                return {"verdict": "FAIL",
                        "note": f"дедуп-чтение витрины не удалось ({type(_e).__name__}: {_e}) — "
                                "не доказано «близнеца нет», залив отменён (повторить прогон)",
                        "evidence": {"twin_error": str(_e)}}
            if _dup:
                _txt = "; ".join(f"{s} — тот же рулон уже живой: {', '.join(v)}"
                                 for s, v in sorted(_dup.items()))
                return {"verdict": "FAIL",
                        "note": "физический близнец уже на витрине: новая карточка была бы вторым "
                                f"экземпляром того же товара, залив отменён: {_txt}",
                        "evidence": {"twin": _dup, "n_plan": len(prods)}}

    if unverified:
        note += f" · {len(unverified)} задумок UNVERIFIED: {unverified}"
        ev["plan_unverified"] = unverified
    note += f" · полнота задумки: {n_complete}/{len(prods)} COMPLETE"
    note += (f" · ценовик(совет): {len(prods) - len(off)}/{len(prods)} в зоне"
             + (f", вне зоны {off}" if off else ""))
    return {"verdict": "PASS", "note": note, "evidence": ev}


def _summary(prods):
    return "; ".join(f"{pr['sku']} v{pr.get('vendor')} "
                     f"desc={len(pr.get('description') or '')} сп={len(pr.get('_spec') or {})} "
                     f"фото={len(pr.get('pictures') or [])} {pr.get('price')}₽" for pr in prods)


def node_fill(ctx, dry, commit):
    """N3 ЗАЛИВ · content-only offer-mappings + offer-cards (create_card). FAIL любого = стоп."""
    import ymarket_write_v1 as W
    slug = ctx["profile"].get("builder_slug", "puzyrkovaya-plenka")
    # Кабинет залива = КАБИНЕТ МАНИФЕСТА (аудит env_write_gate:427): create_card с business_id=None
    # ушёл бы в env YANDEX_BUSINESS_ID/resolve_ids — а баннер и СВЕРКА/ВИТРИНА/ОСТАТКИ смотрят
    # манифест. Залив в другой кабинет = товар «ушёл», а СВЕРКА его не видит (или наоборот).
    # Пинаем биз/кампанию из профиля → всё пишет туда, куда смотрит (и куда ключ имеет доступ —
    # иначе честный отказ API, а не тихое расхождение). dry не трогает: create_card на dry не шлёт.
    bid = ctx["profile"].get("business_id")
    cid = ctx["profile"].get("campaign_id")
    errs = {}
    for pr in ctx["prods"]:
        r = W.create_card(pr, slug=slug, dry=dry, commit=commit, photo_urls=pr["pictures"],
                          business_id=bid, campaign_id=cid)
        if not r.get("ok"):
            errs[pr["sku"]] = (r.get("errors") or r.get("error"))
    if errs:
        return {"verdict": "FAIL", "note": f"ошибки залива: {errs}", "evidence": {"errors": errs}}
    tag = "DRY" if dry else "PASS"
    sp = sorted({len(pr.get("_spec") or {}) for pr in ctx["prods"]})
    sp_txt = f"{sp[0]}-{sp[-1]}" if len(sp) > 1 else str(sp[0] if sp else 0)
    return {"verdict": tag, "note": "контент карточек (vendor Без бренда, описание, "
            f"параметры {sp_txt}, ОВХ, EAN) — " + _summary(ctx["prods"]),
            "evidence": {"n": len(ctx["prods"]), "spec_n": (sp[-1] if sp else 0)}}


def node_place(ctx, dry, commit):
    """N4 ВИТРИНА · place_in_campaign available=True (после включения ЭКСПРЕСС-магазина в кабинете)."""
    import ymarket_write_v1 as W
    cid = ctx["profile"].get("campaign_id")
    errs = {}
    for pr in ctx["prods"]:
        r = W.place_in_campaign(pr["sku"], available=True, dry=dry, commit=commit, campaign_id=cid)
        if not r.get("ok"):
            errs[pr["sku"]] = (r.get("errors") or r.get("error"))
    if errs:
        return {"verdict": "FAIL", "note": f"не вышли на витрину: {errs}", "evidence": {"errors": errs}}
    tag = "DRY" if dry else "PASS"
    return {"verdict": tag, "note": f"available=True (campaign {cid}) × {len(ctx['prods'])}",
            "evidence": {"n": len(ctx["prods"])}}


def node_stock(ctx, dry, commit):
    """N5 ОСТАТКИ · update_stocks FIT на склад манифеста (L3: не выдумываем, count из профиля/слова)."""
    import ymarket_trade_hands_v1 as T
    from ymarket_hands_v1 import business_id_env
    bid = ctx["profile"].get("business_id") or business_id_env()
    wh = ctx["profile"].get("warehouse_id")
    sc = ctx["profile"].get("stock_count")
    if sc is None:
        # Честный SKIP: остаток не задан оператором — не выдумываем, только читаем текущее.
        rows = T.read_stocks(bid, wh, offer_ids=[pr["sku"] for pr in ctx["prods"]])
        cur = {r["sku"]: r["count"] for r in rows if r.get("type") == "FIT"}
        return {"verdict": "SKIP", "note": f"stock_count не задан в манифесте — читаю: {cur}",
                "evidence": {"current": cur}}
    items = [{"sku": pr["sku"], "warehouse_id": wh, "count": sc} for pr in ctx["prods"]]
    r = T.update_stocks(bid, items, dry=dry, commit=commit)
    if dry:
        # _dry_echo: точный payload собран и прошёл гейт — DRY, не FAIL (L6 RUBICON)
        return {"verdict": "DRY", "note": f"FIT={sc} на склад {wh} × {len(items)} "
                f"(сухой payload, НЕ отправлен)", "evidence": {"count": sc, "n": len(items)}}
    if r.get("ok"):
        return {"verdict": "PASS", "note": f"FIT={sc} на склад {wh} × {len(items)}",
                "evidence": {"count": sc, "n": len(items)}}
    return {"verdict": "FAIL",
            "note": f"остатки не легли: {r.get('errors') or r.get('note') or r.get('status')}",
            "evidence": r}


def node_verify(ctx, dry, commit):
    """N6 СВЕРКА · ЧТЕНИЕ живого состояния (200 OK врёт). ВИДИТ ВСЁ ПОД КАПОТОМ:
    campaign PUBLISHED/available + остатки FIT + vendor/desc/params/фото. Здесь нет dry —
    это READ-гейт, работает всегда.
    ЗАКОН PASS-ГЕЙТА (04.09): вердикт PASS выдаётся ТОЛЬКО когда каждый живой блок каждой
    витринной карточки ПОДТВЕРЖДЁН прочтением. Карточка с несобранными блоками (UNVERIFIED)
    НЕ даёт молча PASS — вердикт FAIL с точной причиной («чтение не собрало блоки», а не
    «карточка плохая»); повторный прогон при поднявшемся чтении решает. Это закрывает
    прежний фейк-PASS «N/M без дыр» на непроверенных блоках."""
    import ymarket_hands_v1 as h
    from ymarket_hands_v1 import business_id_env, campaign_id_env
    import ymarket_trade_hands_v1 as T
    bid = ctx["profile"].get("business_id") or business_id_env()
    cid = ctx["profile"].get("campaign_id") or campaign_id_env()
    wh = ctx["profile"].get("warehouse_id")
    ids = [pr["sku"] for pr in ctx["prods"]]

    # SETTLE (аудит price:578): ЯМ пишет асинхронно (~50-110с). СВЕРКА — READ-гейт, но если ЭТОТ
    # прогон только что залил живьём (dry=False и commit=True — точный гейт write-узлов), читаем
    # С ПОСЛЕ паузы: иначе свежий контент ещё не проиндексирован → ложный FAIL/дрейф цены.
    # Сухие прогоны/автопилот (0₽) сна НЕ делают — им читать нечего «только что написанного».
    if not dry and commit:
        time.sleep(CYCLE_SETTLE_SEC)

    rows = {}  # offerId -> evidence-срез
    try:
        offers = h.campaign_offers(cid, offer_ids=ids, limit=50)
        for o in (offers.get("offers") if isinstance(offers, dict) else offers) or []:
            bp = o.get("basicPrice")
            rows.setdefault(o.get("offerId"), {})["placement"] = {
                "available": o.get("available"), "status": o.get("status"),
                "price": (bp.get("value") if isinstance(bp, dict) else bp) or None}
    except Exception as e:
        return {"verdict": "FAIL", "note": f"чтение витрины упало: {e}",
                "evidence": {"error": str(e)}}

    try:
        m = h._request("POST", f"/businesses/{bid}/offer-mappings",
                       body={"offerIds": ids}, params={"limit": 50})
        for ent in (m.get("result", m).get("offerMappings") if isinstance(m.get("result", m), dict) else []) or []:
            o = ent.get("offer") or ent
            bp = o.get("basicPrice")
            # цена живьём: structured {value,currency} → голое число (аудит ест число, dict→UNKNOWN)
            price = (bp.get("value") if isinstance(bp, dict) else bp) or None
            rows.setdefault(o.get("offerId"), {})["content"] = {
                "name": o.get("name"), "vendor": o.get("vendor"),
                "desc_len": len(o.get("description") or ""),
                "n_pics": len(o.get("pictures") or []), "barcodes": o.get("barcodes"),
                "wd": bool(o.get("weightDimensions")),
                "weightDimensions": o.get("weightDimensions"), "price": price}
    except Exception as e:
        return {"verdict": "FAIL", "note": f"чтение контента упало: {e}",
                "evidence": {"error": str(e)}}

    # СПЕКИ живьём (#33): offer-mappings НЕ эхо parameterValues, их отдаёт offer-cards
    # (READ 0₽, тот же кабинет/ключ). Fail-soft: offer-cards недоступен → spec_n не собран →
    # аудит честно оставит карточку UNVERIFIED по спекам (прежнее поведение), СВЕРКА не падает.
    # АНТИ-ФАБРИКАЦИЯ (FIX-C): offer-cards отвечает по КАТАЛОГУ кабинета, а не по нашему
    # маппинг-запросу. Если маппинг-строки нет, а card есть — это НЕ «контент прочитан»,
    # это аномалия (заморозка/нет маппинга). Поэтому spec_n в content кладём ТОЛЬКО когда
    # маппинг реально дал строку: раньше setdefault("content", {}) ФАБРИКОВАЛ content из чужой
    # spec_n и маскировал пустой offer-mappings → ложный PASS («имя/цена/…/параметры на месте»).
    try:
        cards = h.offer_cards_status(bid, offer_ids=ids, limit=50)
        for c in cards or []:
            oid = c.get("offerId")
            if not oid:
                continue
            cd = rows.setdefault(oid, {}).setdefault("card", {})
            cd["status"] = c.get("cardStatus")
            cd["contentRating"] = c.get("contentRating")
            cd["n_errors"] = len(c.get("errors") or [])
            cd["spec_n"] = len(c.get("parameterValues") or [])
            cont = rows[oid].get("content")
            if cont is not None:               # маппинг дал строку → дополняем её спеками
                cont["spec_n"] = cd["spec_n"]
    except Exception:
        pass                      # fail-soft: прежнее честное UNVERIFIED по спекам

    try:
        for r in T.read_stocks(bid, wh, offer_ids=ids):
            if r.get("type") == "FIT":
                rows.setdefault(r["sku"], {})["stock"] = r["count"]
    except Exception as e:
        return {"verdict": "FAIL", "note": f"чтение остатков упало: {e}",
                "evidence": {"error": str(e)}}

    # СУХОЙ ПРОГОН НОВОЙ КАТЕГОРИИ (адверсариал 08.09): ЗАЛИВ в dry НИЧЕГО не отправил
    # (вердикт ◌), а СВЕРКА сверяет ЖИВОЕ состояние. Если для НИ ОДНОГО sku движка витрина
    # не дала ни строки (rows пуст) — это «залива не было», а НЕ «залито и пропало». FAIL тут
    # был бы тавтологией «не залил → не на витрине» и врал оператору про поломку (аудит #79).
    # НЕ выдаём fake PASS: вердикт ◌, как у ЗАЛИВ/ВИТРИНА/ОСТАТКИ в сухом, — «сверять нечего,
    # живое докажет --commit». Живой ход (dry=False) и плёночный dry (витрина НЕ пуста —
    # сверять есть что) идут прежним жёстким путём, байт-в-байт.
    if dry and not rows:
        return {"verdict": "◌", "note": "сухой прогон: залив не производился, на витрине ни одной "
                                       "карточки движка — живая СВЕРКА на --commit",
                "evidence": {"rows": rows}}

    # Честный вердикт: ВСЕ карточки должны быть на витрине (PUBLISHED+available) с остатком.
    bad = {}
    not_yet = {}                 # dry: витрина карточки пуста — «залива не было», не «залито и пропало»
    for sku in ids:
        r = rows.get(sku) or {}
        pl = r.get("placement") or {}
        if not pl:
            # Расширение аудита #79 на СМЕШАННЫЙ dry: часть карточек движка уже жива (9 одиночек),
            # часть — новая задумка (13 наборов, ЗАЛИВ в dry их не создал). Карточка, которой на
            # витрине нет ВООБЩЕ (ни одной строки), в dry = «не заливалась» → ◌ (докажет --commit),
            # НЕ FAIL (FAIL врал бы оператору про поломку). Живой ход (dry=False) — жёсткий FAIL.
            if dry:
                not_yet[sku] = "витрина {}"
            else:
                bad[sku] = f"витрина {pl}"
        elif pl.get("available") is not True or pl.get("status") != "PUBLISHED":
            bad[sku] = f"витрина {pl}"
        elif not r.get("stock"):
            bad[sku] = "остаток FIT не читается"
    if dry and not_yet and not bad:
        return {"verdict": "◌", "note": f"сухой прогон: {len(not_yet)} карточек не заливались "
                                        f"(витрина пуста) — живая СВЕРКА на --commit: {list(not_yet)}",
                "evidence": {"rows": rows}}
    if bad:
        return {"verdict": "FAIL", "note": f"НЕ на витрине: {bad}", "evidence": {"bad": bad, "rows": rows}}

    # Полнота карточек (аудит-орган): карточка НА витрине, но БЕЗ живых блоков, которые
    # СВЕРКА ПРОЧИТАЛА (имя/цена/весогабариты/фото/описание/штрихкод/параметры), НЕ проходит
    # как «полная». Раньше гейтились только размещение/остатки/vendor: карточка БЕЗ
    # weightDimensions получала PASS (дыра адверсари-ревью). MISSING = прочитано-и-нет
    # (жёсткий FAIL). UNKNOWN = срез СВЕРКИ НЕ собрал блок (напр. спеки, если offer-cards
    # недоступен) → UNVERIFIED, и НЕ даёт PASS: «PASS только когда каждый живой блок доказан»
    # (закон оператора 04.09 «сделай чтобы система законно не врала»). UNVERIFIED НЕ обвиняет
    # карточку — это честное «чтение не доказало полноту», лечится повторным прогоном. #33: срез
    # читает name/цену/ОВХ из offer-mappings и спеки из offer-cards — UNVERIFIED остаётся только
    # при недоступности чтения, не от бедного среза.
    import ymarket_card_audit_v1 as caudit
    incomplete = {}
    no_content = []               # на витрине (placement+остаток прошли выше) — а контент-срез НЕ прочитан
    n_complete = n_unverified = 0
    unv_blocks = {}
    exp_price = {pr.get("sku"): pr.get("price") for pr in ctx["prods"]}
    price_drift = {}              # живая цена ≠ план задумки (evidence/заметка; НЕ FAIL — см. ниже)
    for sku in ids:
        r = rows.get(sku) or {}
        if "content" not in r:
            # Дыра аудита (verify_slice:577): карточка на витрине, а offer-mappings НЕ вернул
            # строку контента. Раньше — тихий continue → ложный PASS с перехвальбой «имя/цена/…/
            # параметры на месте» (и _sync_library писал библиотеке record_verified PASS). НО
            # СВЕРКА — READ-гейт, обязана ПОДТВЕРДИТЬ полноту, а не верить молчанию: видимая
            # карточка без маппинг-строки = аномалия (заморозка/потеря маппинга/не успел
            # проиндексироваться) → честный FAIL, повторный прогон решит.
            no_content.append(sku)
            continue
        c = r["content"]
        v = caudit.audit_live(c)
        if v["verdict"] == "INCOMPLETE":
            incomplete[sku] = {"missing": v["missing"], "note": v["note"]}
        elif v["verdict"] == "UNVERIFIED":
            n_unverified += 1
            unv_blocks[sku] = v["unknown"]
        else:
            n_complete += 1
        # Цена живьём vs план задумки (аудит price:578/514): раньше СВЕРКА гейтила лишь «>0» —
        # тихая переоценка живьём (дрейф донорской cost между прогонами) НЕ замечалась. Кладём
        # ПОКАРТОЧНО в evidence (price_plan/price_ok) + честную заметку. НЕ FAIL-гейт: донор мог
        # сменить cost, а повторный --commit ещё не делали — это факт для ЦЕНОВИКА/ДНЯ (переценят
        # по живой), а не поломка карточки. (Ложный FAIL тут дал бы стационарный dry-прогон: он
        # НЕ шлёт свежий скан, цена в задумке от прошлого скана может честно расходиться.)
        want = exp_price.get(sku)
        live = c.get("price")
        c["price_plan"] = want
        c["price_ok"] = None
        if want is not None and live is not None:
            try:
                drift = abs(float(live) - float(want)) > 1.0
            except (TypeError, ValueError):
                drift = True
                price_drift[sku] = {"live": live, "plan": want, "why": "цена нечисловая"}
            c["price_ok"] = not drift
            if drift and sku not in price_drift:
                price_drift[sku] = {"live": live, "plan": want}
    if incomplete:
        note = "карточки на витрине, но НЕ ПОЛНЫ: " \
               f"{ {s: d['missing'] for s, d in incomplete.items()} }"
        if n_unverified:
            note += (f" · ещё {n_unverified} UNVERIFIED (блоки не собраны чтением): {unv_blocks} "
                     f"— тоже НЕ доказаны, повторный прогон")
        return {"verdict": "FAIL", "note": note,
                "evidence": {"incomplete": incomplete, "n_unverified": n_unverified,
                             "unverified": unv_blocks, "rows": rows}}
    if no_content:
        note = ("карточки на витрине БЕЗ контент-среза (offer-mappings не вернул строку): "
                f"{no_content} — полнота НЕ подтверждена (заморозка/нет маппинга?)")
        if n_unverified:
            note += (f" · ещё {n_unverified} UNVERIFIED (блоки не собраны чтением): {unv_blocks} "
                     f"— тоже НЕ доказаны, повторный прогон")
        return {"verdict": "FAIL", "note": note,
                "evidence": {"no_content": no_content, "n_unverified": n_unverified,
                             "unverified": unv_blocks, "rows": rows}}
    # PASS-ГЕЙТ (04.09): карточка НА витрине, а её блоки СВЕРКА НЕ собрала чтением (UNVERIFIED,
    # напр. спеки при недоступном offer-cards) → НЕ PASS. Размещение/остатки/vendor доказаны, но
    # «полнота N/N ПОДТВЕРЖДЕНА» врать нельзя. Это НЕ «карточка плохая» — чтение не доказало;
    # когда чтение поднимется, повторный прогон даст чистый PASS.
    if n_unverified:
        return {"verdict": "FAIL",
                "note": (f"{n_unverified} карточек UNVERIFIED — блоки не собраны чтением: {unv_blocks}. "
                         "Карточки на витрине (PUBLISHED+остатки FIT+vendor), но полнота НЕ "
                         "ПОДТВЕРЖДЕНА — PASS не выдаётся (закон «каждый живой блок доказан»); "
                         "повторить прогон, когда чтение поднимется"),
                "evidence": {"n_complete": n_complete, "n_unverified": n_unverified,
                             "unverified": unv_blocks, "rows": rows}}
    ok = all((r.get("content") or {}).get("vendor") == "Без бренда"
             for r in rows.values() if "vendor" in (r.get("content") or {}))
    # Сюда доходим только когда UNVERIFIED нет (иначе вернули выше) → все на витрине ПОЛНЫ.
    audit_note = (f"полнота {len(ids)}/{len(ids)} — имя/цена/описания/фото/"
                  f"весогабариты/EAN/параметры ПОДТВЕРЖДЕНЫ полностью")
    if price_drift:
        drift_txt = ", ".join(f"{s}: живьём {d['live']}₽ vs план {d['plan']}₽"
                              for s, d in price_drift.items())
        audit_note += (f" · ЦЕНА ЖИВЬЁМ ≠ ПЛАН (факт для ЦЕНОВИКА, не гейт): {drift_txt}")
    note = f"витрина PUBLISHED ×{len(ids)} · остатки FIT · vendor Без бренда · {audit_note}"
    if not ok:
        return {"verdict": "FAIL", "note": "vendor не «Без бренда» у кого-то из карточек", "evidence": rows}
    return {"verdict": "PASS", "note": note, "evidence": rows}


def node_control(ctx, dry, commit):
    """N7 КОНТРОЛЬ · зелёный ценник / цена-эталон / акции (директива 08.09 «клиент платит
    сумму выгодную мне»). READ-гейт — работает всегда, как СВЕРКА.

    Витрина должна показывать РЕАЛЬНУЮ цену закупка×markup: зачёркнутая цена (discountBase =
    «зелёный ценник» = скидка) и участие в акциях (баллы/скидки) оператору НЕ нужны. Читает
    ЖИВОЕ offer-prices по КАБИНЕТУ (ВСЕ offers — включает легаси 9601515-1, которых не видят
    ни СБОРКА, ни СВЕРКА), сверяет:
      (1) discountBase ни у кого — зелёный ценник (виолейшен, факт);
      (2) карточки БИБЛИОТЕКИ: живая цена ≥ закупка×markup (эталон профита) — иначе клиент
          платит меньше выгодной (факт для ЦЕНОВИКА);
      (3) акции: promos participating (активных акций быть не должно).
    Вердикт PASS с evidence (факты, НЕ FAIL-гейт — иначе сухой автопилот вечно падал бы на
    легаси-ценнике и ПЛАНЁРКА не доходила бы до конца цепи). Упало чтение offer-prices →
    честный FAIL «проверить нельзя» (закон «не врать»). Акции/библиотека — fail-soft.
    ЖИВОЙ ход (--commit, RUBICON): зелёные ценники СНОСИТ — update_prices БЕЗ discountBase
    (зачёркнутая сбрасывается, value НЕ трогаем → карантина цен нет). 200 врёт на write →
    успех не утверждаем: «отправлено, подтвердить чтением следующим прогоном»."""
    import ymarket_hands_v1 as h
    import ymarket_trade_hands_v1 as T
    bid = ctx["profile"].get("business_id") or h.business_id_env()
    if not bid:
        return {"verdict": "FAIL", "note": "businessId неизвестен — контроль цен невозможен",
                "evidence": {}}
    # (0) ЖИВОЕ offer-prices: все offers кабинета (пустой body → вся витрина, не только партия)
    try:
        data = h._request("POST", f"/businesses/{bid}/offer-prices", body={}, timeout=60)
        offers = ((data or {}).get("result") or {}).get("offers") or []
    except Exception as e:
        return {"verdict": "FAIL",
                "note": f"чтение offer-prices упало: {type(e).__name__}: {e}",
                "evidence": {"error": str(e)}}
    # (1) зелёные ценники: discountBase присутствует → «было/стало» на витрине
    green, prices = {}, {}
    for o in offers:
        oid = o.get("offerId")
        pr = o.get("price") or {}
        val = pr.get("value")
        if oid is None or val is None:
            continue
        prices[str(oid)] = float(val)
        if pr.get("discountBase") is not None:
            green[str(oid)] = {"value": float(val), "base": float(pr["discountBase"])}
    # (2) эталон профита из БИБЛИОТЕКИ (fail-soft: нет библиотеки/полей → проверки цены нет)
    below, lib_n = {}, 0
    try:
        import ymarket_library_v1 as lib
        goods = (lib.load() or {}).get("goods") or {}
        for oid, rec in goods.items():
            try:
                cost, markup = rec.get("cost"), rec.get("markup")
                if cost is None or markup is None:
                    continue
                plan = float(cost) * float(markup)
            except (TypeError, ValueError):
                continue
            lib_n += 1
            live = prices.get(str(oid))
            if live is not None and live < plan - 1.0:
                below[str(oid)] = {"live": live, "plan": round(plan, 2)}
    except Exception:
        lib_n = 0
    # (3) акции + АВТОДОБАВЛЕНИЕ (fail-soft: promos недоступен → пометка в evidence, НЕ FAIL).
    # Оператор 08.09: «товары не должны уходить в акции сами». API-«запрета на товаре» НЕТ —
    # цикл детектит ФАКТ и риск: (а) участие participating/activeOffers; (б) НАШИ SKU реально в
    # акции (status AUTO/MANUAL/PARTIALLY_AUTO/RENEWED → auto_added); (в) риск будущего ухода =
    # bestsellerInfo.renewalEnabled «Переносить товары между бестселлерами» (кабинет-тумблер,
    # включает автоперенос ассортимента в следующие волны). Все статусы офферов — только чтение.
    promos = {"total": 0, "participating": 0, "names": [], "active": 0, "potential": 0,
              "auto_added": [], "renewal_on": [], "error": None}
    _AUTO_STATUSES = {"AUTO", "MANUAL", "PARTIALLY_AUTO", "RENEWED"}  # реально участвуют в акции
    try:
        pdata = h._request("POST", f"/businesses/{bid}/promos", body={}, timeout=30)
        for p in ((pdata or {}).get("result") or {}).get("promos") or []:
            promos["total"] += 1
            pid, pname = p.get("id"), p.get("name") or p.get("id") or "—"
            asn = p.get("assortmentInfo") or {}
            n_active = int(asn.get("activeOffers") or 0)
            n_pot = int(asn.get("potentialOffers") or 0)
            promos["active"] += n_active
            promos["potential"] += n_pot
            part = bool(p.get("participating"))
            if part:
                promos["participating"] += 1
                promos["names"].append(pname)
            if (p.get("bestsellerInfo") or {}).get("renewalEnabled"):
                promos["renewal_on"].append(pname)
            # какие из НАШИХ SKU реально в этой акции — только когда есть активность/участие
            # (иначе AUTO-строк быть не может; сухие акции не дёргаем вторым запросом)
            if part or n_active > 0:
                try:
                    odata = h._request("POST", f"/businesses/{bid}/promos/offers",
                                       body={"promoId": pid, "limit": 200}, timeout=30)
                    for of in ((odata or {}).get("result") or {}).get("offers") or []:
                        if of.get("status") in _AUTO_STATUSES:
                            promos["auto_added"].append(str(of.get("offerId")))
                except Exception:
                    pass  # список офферов не снялся — активность уже видна в activeOffers/participating
        promos["auto_added"] = sorted({str(x) for x in promos["auto_added"]})
    except Exception as e:
        promos["error"] = f"{type(e).__name__}: {e}"
    # (4) ЖИВОЙ ход: сносим зелёные ценники (value не меняем — сбрасывается только зачёркнутая)
    cleared, clear_errors = [], []
    if (not dry and commit) and green:
        try:
            payload = [{"sku": oid, "value": g["value"]} for oid, g in green.items()]
            r = T.update_prices(bid, payload, dry=False, commit=True, timeout=60)
            if r.get("ok") is False or r.get("status") in ("error",):
                clear_errors = r.get("errors") or [str(r)]
            else:
                cleared = list(green.keys())
        except Exception as e:
            clear_errors = [f"{type(e).__name__}: {e}"]
    if clear_errors:
        return {"verdict": "FAIL",
                "note": f"зелёные ценники {list(green)}: сброс упал — {clear_errors}",
                "evidence": {"green": green, "clear_errors": clear_errors,
                             "below_plan": below, "promos": promos}}
    bits = []
    if green:
        bits.append("зелёных ценников " + ", ".join(
            f"{oid}: {g['value']:g}₽/зачёркнуто {g['base']:g}₽" for oid, g in green.items()))
    else:
        bits.append("зелёных ценников 0")
    if below:
        bits.append("ниже эталона " + ", ".join(
            f"{oid}: {d['live']:g}₽ < {d['plan']:g}₽" for oid, d in below.items()))
    if promos["participating"] or promos["auto_added"]:
        if promos["auto_added"]:
            bits.append("АВТОДОБАВЛЕНЫ в акции: " + ", ".join(promos["auto_added"]))
        if promos["participating"]:
            bits.append(f"акции УЧАСТВУЕТ {promos['participating']} ({', '.join(promos['names'])})")
    elif promos["error"]:
        bits.append(f"акции не прочитаны ({promos['error']})")
    else:
        act = f"активных {promos['active']} из {promos['potential']} потенциальных" \
            if promos["potential"] else "активных 0"
        bits.append(f"акции не участвует ({promos['total']}, {act})")
    if promos["renewal_on"]:
        bits.append("автоперенос волн ВКЛЮЧЁН: " + ", ".join(promos["renewal_on"]) +
                    " — выключить в кабинете (переносит товары в след. волны)")
    note = " · ".join(bits)
    if cleared:
        note += (f" · СНЕСЕНЫ {len(cleared)} (живой ход) — подтвердить чтением следующим "
                 "прогоном (200 врёт на write)")
    return {"verdict": "PASS", "note": note,
            "evidence": {"offers": len(offers), "green": green, "below_plan": below,
                         "promos": promos, "library_cards": lib_n,
                         **({"cleared": cleared} if cleared else {})}}


def node_plannerka(ctx, dry, commit):
    """N7 ПЛАНЁРКА · самоосознание: вчерашний леджер + этот прогон → ПУЛЬС (реальные числа)."""
    import datetime
    store = ctx["profile"]["slug"]
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    hist = []
    lp = ledger_path(store, yesterday)
    if lp.exists():
        for line in lp.read_text().splitlines():
            try:
                hist.append(json.loads(line))
            except Exception:
                pass
    from collections import Counter
    c = Counter(x.get("verdict") for x in hist)
    by_node = {}
    for x in hist:
        by_node.setdefault(x.get("node"), Counter())[x.get("verdict")] += 1
    pulse = {
        "store": store, "date": time.strftime("%Y-%m-%d"),
        "yesterday_runs": len(hist), "yesterday_verdicts": dict(c),
        "by_node": {k: dict(v) for k, v in by_node.items()},
        "run_verdicts": Counter(x.get("verdict") for x in ctx["results"]),
        "artifacts": len(ctx["results"]) and sum(
            1 for x in ctx["results"] if x.get("node") == "СВЕРКА" and x.get("verdict") == "PASS"),
    }
    pulse_path(store).write_text(json.dumps(pulse, ensure_ascii=False, indent=1))
    today_pass = sum(1 for x in ctx["results"] if x.get("verdict") == "PASS")
    today_fail = sum(1 for x in ctx["results"] if x.get("verdict") == "FAIL")
    if today_fail:
        return {"verdict": "FAIL", "note": f"пульс: PASS {today_pass} / FAIL {today_fail} — смотрим узлы",
                "evidence": pulse}
    return {"verdict": "PASS", "note": f"пульс вчера: {len(hist)} узлов, "
            f"{'/'.join(f'{k}={v}' for k, v in c.items() or [('без_прогона', 1)])} · сегодня PASS {today_pass}",
            "evidence": pulse}


def film_chain():
    return [
        ("ДОНОР", node_donor, False),
        ("СБОРКА", node_build, False),
        ("ЗАЛИВ", node_fill, True),
        ("ВИТРИНА", node_place, True),
        ("ОСТАТКИ", node_stock, True),
        ("СВЕРКА", node_verify, False),
        ("КОНТРОЛЬ", node_control, True),
        ("ПЛАНЁРКА", node_plannerka, False),
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  АВТО-ЗАПИСЬ В БИБЛИОТЕКУ (оператор: «каждый добавленный артикул и обновлённые
#  остатки пишутся в общую библиотеку»). Аддитивно, ТОЛЬКО на живом ходу.
# ─────────────────────────────────────────────────────────────────────────────

def _sync_library(ctx, results, hsh):
    """Живой ход (--commit) → БИБЛИОТЕКА товаров/категорий (ymarket_library_v1).

    По вердиктам узлов записывает РЕАЛЬНЫЕ события (LB1: dry пишет НИЧЕГО):
      ЗАЛИВ PASS   → карточки: что собрано (имя/цена/закупка/габариты/фото/категория);
      ОСТАТКИ PASS → события остатков: склад + счёт (история, не снимок);
      СВЕРКА PASS  → протокол: запись видела живое состояние витрины;
      узел FAIL после ЗАЛИВ → last_verified=FAIL (товар залит, но НЕ подтверждён).
    Вызывается ТОЛЬКО при `not dry AND commit` (реальный гейт записи ЯМ).
    Библиотека — слой ЗНАНИЯ: её сбой НЕ должен ронять цикл (товар уже на витрине),
    поэтому fail-open с заметкой. Возвращает {ok, note, n}.
    """
    # fail-open по построению: библиотека — слой ЗНАНИЯ, её сбой НЕ роняет цикл
    # (товар уже на витрине). Ловим ВСЁ тело записи, не только импорт: ошибка
    # прав/диска write_atomic, ValueError на пустом sku и т.п. → ok=False с заметкой.
    n = 0
    try:
        import ymarket_library_v1 as lib
        prof = ctx.get("profile") or {}
        slug = prof.get("slug")
        prods = ctx.get("prods") or []
        res = {r.get("node"): r for r in (results or [])}
        # 1) ЗАЛИВ удался → карточки (артефакт цикла) в общую библиотеку
        if (res.get("ЗАЛИВ") or {}).get("verdict") == "PASS" and prods:
            entries = []
            for pr in prods:
                entries.append({
                    "offer_id": pr.get("sku"), "donor_pid": pr.get("pid"),
                    "name": pr.get("name"), "article": pr.get("article"),
                    "vendor": pr.get("vendor"), "barcode": pr.get("barcode"),
                    "cost": pr.get("cost"), "price": pr.get("price"),
                    "store_slug": slug, "cycle_hash": hsh,
                    "builder": prof.get("builder"),
                    "category_slug": prof.get("donor_category"),
                    "n_photos": len(pr.get("pictures") or []),
                    "dims": pr.get("weightDimensions"),
                    "description_len": len(pr.get("description") or ""),
                    "spec_n": len(pr.get("_spec") or {}),
                    "stock_count": prof.get("stock_count"),
                })
            n += lib.record_cards(True, entries) or 0
        # 2) ОСТАТКИ удались → события остатков (склад + счёт; count не выдумываем)
        if (res.get("ОСТАТКИ") or {}).get("verdict") == "PASS":
            wh = prof.get("warehouse_id")
            cnt = prof.get("stock_count")
            for pr in prods:
                if cnt is not None:
                    n += 1 if lib.record_stock(True, pr.get("sku"), count=cnt,
                                               warehouse_id=wh, store_slug=slug,
                                               cycle_hash=hsh) else 0
        # 3) СВЕРКА удалась → протокол последней проверки живого состояния
        if (res.get("СВЕРКА") or {}).get("verdict") == "PASS":
            for pr in prods:
                n += 1 if lib.record_verified(True, pr.get("sku"), verdict="PASS",
                                              store_slug=slug, cycle_hash=hsh,
                                              note="СВЕРКА: витрина PUBLISHED + остатки FIT") else 0
        # 4) ЦЕПЬ ОСТАНОВЛЕНА (узел FAIL после успешного ЗАЛИВА) → честный маркер:
        #    карточки реально созданы на ЯМ, НО живое состояние витрины/остатков НЕ
        #    подтверждено прочтением (200 OK врёт, доказывает только СВЕРКА). Ставим
        #    last_verified=FAIL — библиотека НЕ выдаёт «поставлено и проверено».
        failed = [r.get("node") for r in (results or []) if r.get("verdict") == "FAIL"]
        if failed and (res.get("ЗАЛИВ") or {}).get("verdict") == "PASS" and prods:
            for pr in prods:
                n += 1 if lib.record_verified(True, pr.get("sku"), verdict="FAIL",
                                              store_slug=slug, cycle_hash=hsh,
                                              note=f"цепь остановлена на «{', '.join(failed)}» — "
                                                   f"живое состояние не подтверждено") else 0
    except Exception as e:
        return {"ok": False,
                "note": f"библиотека не обновилась полностью (fail-open, товар уже на витрине): "
                        f"{type(e).__name__}: {e}; записано событий {n}",
                "n": n}
    return {"ok": True, "note": f"библиотека: событий {n}", "n": n}


# ─────────────────────────────────────────────────────────────────────────────
#  ПОЗВОНОК-МАТРИЦА (оператор 03.09: «оживи позвонок — движок начинает ПИСАТЬ
#  матрицу: узел цепочки = ensure+set_status(собран/залит/на-витрине) с offer_id»).
#  Матрица (ymarket_matrix_v1) — это как ЦИКЛ-1/2/3 связаны воедино ЯМ-ЦИКЛом:
#  ОДИН товар физически проходит через все циклы, и матрица — «позвонок» этой
#  крови: кандидат→собран→залит→…→на-витрине→продан. Без движка матрица была
#  глухим сторожем (читали все, писал никто). Теперь живой ход сам ведёт её.
# ─────────────────────────────────────────────────────────────────────────────

def _sync_matrix(ctx, results, hsh):
    """Живой ход (--commit) → МАТРИЦА товаров (ymarket_matrix_v1) — «позвонок крови».

    По вердиктам узлов поднимает строку по статус-лесенке кандидат→собран→залит→
    сверен→на-витрине→продан:
      СБОРКА PASS → собран      (товар собран из донора, карточка готова к заливу);
      ЗАЛИВ PASS  → залит + offer_id (карточка создана на ЯМ — ARB-sku);
      СВЕРКА PASS → на-витрине + offer_id (ЖИВОЕ прочтение витрины PUBLISHED+остатки
                    FIT — 200 OK врёт, доказывает только СВЕРКА, как last_verified
                    в библиотеке). Поэтому «на-витрине» ставит СВЕРКА, а не ВИТРИНА.
    Вызывается ТОЛЬКО при `not dry AND commit` (реальный гейт записи ЯМ) — в сухом
    прогоне карточка не на витрине, а в задумке (закон LB1: dry пишет НИЧЕГО).
    ВНИЗ не откатываем (M4): карточка, уже достигшая на-витрине, при частичном новом
    живом прогоне (напр. ЗАЛИВ FAIL после прошлого успеха) НЕ разжалуется.
    fail-open: матрица — слой ЗНАНИЯ, её сбой не роняет цикл (товар уже на витрине).
    Возвращает {ok, note, n}.
    """
    n = 0
    try:
        import ymarket_matrix_v1 as mx
        prof = ctx.get("profile") or {}
        prods = ctx.get("prods") or []
        res = {r.get("node"): r for r in (results or [])}
        build_ok = (res.get("СБОРКА") or {}).get("verdict") == "PASS"
        fill_ok = (res.get("ЗАЛИВ") or {}).get("verdict") == "PASS"
        ver_ok = (res.get("СВЕРКА") or {}).get("verdict") == "PASS"
        if not prods or not (build_ok or fill_ok or ver_ok):
            return {"ok": True, "note": "матрица: нет PASS-узлов СБОРКА/ЗАЛИВ/СВЕРКА — не пишем", "n": 0}
        cat = prof.get("builder_slug")          # рыночная категория (как у строк-посевов и create_card)
        prov = ctx.get("provider")              # источник добычи, если N1 его назвал (иначе не трогаем)
        doc = mx.load()
        ladder = mx._STATUS_LADDER
        for pr in prods:
            ean = pr.get("barcode")
            # M7/M8 (оператор 10.09): строка несёт СВЯЗЬ С ДОНОРОМ (pid/артикул 1-в-1) и РАЗМЕР
            # из структурного _spec сборщика (он знает факты; не выдумываем). donor_url/store
            # заполняет только тот, кто их реально знает (у ленты/плёнки — артикульный донор).
            _spec = pr.get("_spec") or {}
            size = mx.spec_to_size(_spec) or None
            donor_pid = pr.get("pid")
            donor_article = pr.get("donor_article") or pr.get("article")
            key, _row, _created = mx.ensure(
                doc, name=pr.get("name"), article=str(pr.get("article") or "") or None,
                ean=str(ean) if ean else None, provider=prov, category=cat,
                donor_pid=str(donor_pid) if donor_pid else None,
                donor_article=str(donor_article) if donor_article else None,
                size=size)
            # глубина достигнутой ступени по вердиктам узлов (цепь останавливается на FAIL —
            # последний PASS в цепочке и есть реальное состояние товара)
            if ver_ok:
                target, offer = "на-витрине", pr.get("sku")
            elif fill_ok:
                target, offer = "залит", pr.get("sku")
            elif build_ok:
                target, offer = "собран", None
            else:
                continue
            cur = (doc.get("rows") or {}).get(str(key), {}).get("status") or "кандидат"
            # только ВПЕРЁД по лесенке; достигнутое ранее не откатываем (M4 без причины)
            if ladder.index(target) > ladder.index(cur):
                if mx.set_status(doc, key, target, offer_id=offer,
                                 note=f"ЦИКЛ-1 #{hsh}: {target} на живом ходу"):
                    n += 1
            elif offer and cur == "залит":
                # та же ступень — довешиваем offer_id (мог не успеть на прошлом ходе)
                mx.set_status(doc, key, target, offer_id=offer, note=None)
        if n:
            mx.write_atomic(doc)
    except Exception as e:
        return {"ok": False,
                "note": f"матрица не обновилась (fail-open, товар уже на витрине): "
                        f"{type(e).__name__}: {e}; строк {n}",
                "n": n}
    return {"ok": True, "note": f"матрица: позвонков поднято {n}", "n": n}


def matrix_catchup():
    """Мост-катчап для карточек, проживших ЦИКЛ-1 ДО хука _sync_matrix (0₽, локально).

    Первые 4 карточки залиты и подтверждены живьём 03.09, когда движок ещё не писал
    в матрицу — их позвонки застряли на «собран». Источник правды о реальном состоянии
    витрины — БИБЛИОТЕКА (ymarket_library_v1): там last_verified=PASS (СВЕРКА прочитала
    витрину PUBLISHED). Читаем её и поднимаем строки матрицы до «на-витрине» + offer_id.
    Идемпотентно (на-витрине не трогаем), НИЧЕГО наружу — только локальный стор матрицы.
    Возвращает {ok, note, n}.
    """
    n = 0
    try:
        import ymarket_matrix_v1 as mx
        import ymarket_library_v1 as lib
        goods = (lib.load().get("goods") or {})
        doc = mx.load()
        ladder = mx._STATUS_LADDER
        for oid, g in goods.items():
            if (g.get("last_verified") or {}).get("verdict") != "PASS":
                continue                      # вверх ведёт только РЕАЛЬНО подтверждённое
            art = g.get("article")
            if not oid or not art:
                continue
            ean = g.get("barcode")
            key, _row, _created = mx.ensure(
                doc, name=g.get("name"), article=str(art),
                ean=str(ean) if ean else None)     # категория/provider не перетираем (провини в строке)
            cur = (doc.get("rows") or {}).get(str(key), {}).get("status") or "кандидат"
            if ladder.index("на-витрине") > ladder.index(cur):
                if mx.set_status(doc, key, "на-витрине", offer_id=oid,
                                 note="на-витрине: СВЕРКА PASS в библиотеке (катчап до хука _sync_matrix)"):
                    n += 1
        if n:
            mx.write_atomic(doc)
    except Exception as e:
        return {"ok": False, "note": f"матрица-катчап не прошёл: {type(e).__name__}: {e}", "n": n}
    return {"ok": True, "note": f"матрица-катчап: позвонков на-витрине {n}", "n": n}


# ─────────────────────────────────────────────────────────────────────────────
#  РАННЕР ЦЕПИ
# ─────────────────────────────────────────────────────────────────────────────

def _sync_process_artifact(ctx, results, hsh, ledger_path=None):
    """Живой ход (--commit), ВСЕ узлы PASS → ХОД записан в БИБЛИОТЕКУ ПРОЦЕССОВ.

    Эволюционный закон оператора (09.09): «когда система прошла цикл — она становится
    лучше ВСЕГДА: много готовых записанных ходов». Закрытый цикл селится как kind=cycle1
    артефакт (process_artifact_v1.register_cycle1): читаемый .md + реестр — повторить ход
    невероятно быстро (СКИЛ системы). Двойной гейт: вызывается ТОЛЬКО под `not dry AND
    commit` (см. run_cycle), и register_cycle1 сам требует all_pass(results) — FAIL /
    оборванный прогон ходом НЕ становится. Сеть не трогает. fail-open: ход — слой ЗНАНИЯ,
    сбой не роняет цикл (товар уже на витрине). Возвращает {ok, note, id}."""
    try:
        import ymarket_library_v1 as lib
        import process_artifact_v1 as pa
        prof = ctx.get("profile") or {}
        slug = prof.get("slug")
        artifacts = {"ledger": str(ledger_path or "")}
        try:
            artifacts["goods_library"] = str(lib.library_path())
        except Exception:
            pass
        r = pa.register_cycle1(prof, results, commit=True, hsh=hsh,
                               artifacts=artifacts, ledger_path=ledger_path)
        if not r.get("ok"):
            return {"ok": False, "note": f"ход не записан: {r.get('error')}"}
        return {"ok": True, "note": f"ход {r.get('id')} записан (kind=cycle1 · {slug})",
                "id": r.get("id")}
    except Exception as e:
        return {"ok": False,
                "note": f"ход не записан (fail-open): {type(e).__name__}: {e}"}


def run_cycle(store_slug, dry=True, commit=False, chain=None, date_str=None, verbose=False):
    import datetime
    date_str = date_str or datetime.date.today().isoformat()
    profile = load_store(store_slug)
    if not profile:
        return _missing_store(store_slug, date_str)
    resolved, why = resolve_profile(profile)
    if resolved is None:
        print(f"\n  {_c('red', '✗')} {store_slug}: резолв мамы не удался — {why}.\n"
              f"    Открыть {store_profiles_path()} и починить mother/поля.\n")
        return {"verdict": "FAIL", "profile": profile, "why": why}
    profile = resolved
    ctx = {"profile": profile, "results": []}
    chain = chain or film_chain()
    hsh = cycle_hash(store_slug, date_str)
    lp = ledger_path(store_slug, date_str)
    results = []
    halted = None
    print(f"\n  {_c('b', 'ЦИКЛ-1')} · {profile['slug']} · {date_str} · {_c('cyn', '#' + hsh)} · "
          f"{_c('yel', 'DRY 0₽' if dry else 'LIVE')} · {_c('dim', 'тихо' if not verbose else 'verbose')}")
    # Кабинетный баннер (#35): каждый прогон явно показывает, куда смотрит манифест
    # (тест-кабинет 216949599 vs боевой — видно по id, не гадаем). Секретов нет.
    print(f"  {_c('dim', 'кабинет:')} biz {_c('b', profile.get('business_id'))}"
          f"{_c('dim', ' · кампания')} {_c('b', profile.get('campaign_id'))}"
          f"{_c('dim', ' · склад')} {_c('b', profile.get('warehouse_id'))}"
          + (f"{_c('dim', ' · кабинет унаследован от «')}{_c('b', profile.get('_inherited_from'))}"
             f"{_c('dim', '»')}" if profile.get("_inherited_from") else ""))
    # PREFLIGHT (#35): ЖИВОЙ ход без ключа = гарантированно путанный FAIL на каждом
    # write-узле (или RuntimeError в руки). Останавливаемся ДО цепи с ясной причиной.
    # Сухой ход ключ для write не требует, но N6 СВЕРКА читает живо (0₽) — без ключа
    # она честно FAIL-нёт на чтении (это READ-гейт, не баг).
    if not dry:
        try:
            from ymarket_hands_v1 import creds_present
        except Exception:
            creds_present = lambda: False
        if not creds_present():
            print(f"\n  {_c('red', '✗')} ЖИВОЙ ход (--commit) требует YANDEX_MARKET_API_KEY в env — "
                  f"ключ не найден, цепь НЕ запущена (остановка до любых действий).\n")
            return {"verdict": "FAIL", "profile": profile,
                    "why": "YANDEX_MARKET_API_KEY отсутствует (живой ход)"}
    for i, (name, fn, is_write) in enumerate(chain, 1):
        t0 = time.time()
        buf = None
        if verbose:
            # --verbose: полный живой поток узла (для отладки точных payload)
            try:
                r = fn(ctx, dry=dry, commit=commit)
            except Exception as e:
                r = {"verdict": "FAIL", "note": f"{type(e).__name__}: {e}", "evidence": {}}
        else:
            # ТИХИЙ по умолчанию («многа букав» → нет): вывод узла (в т.ч. сухие payload
            # из write_v1._dry) ловится; наружу идёт только пульс-строка. Честность FAIL
            # сохраняется — при ошибке показываем хвост захваченного вывода.
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    r = fn(ctx, dry=dry, commit=commit)
            except Exception as e:
                r = {"verdict": "FAIL", "note": f"{type(e).__name__}: {e}", "evidence": {}}
        r = dict(r, node=name, dry=dry, ts=time.strftime("%H:%M:%S"))
        r["ms"] = (time.time() - t0) * 1000
        results.append(r)
        ctx["results"] = list(results)   # планёрка (последний узел) видит весь прогон до себя
        print(pulse_line(name, r["verdict"], r["note"], r["ms"], i, len(chain)))
        if r["verdict"] == "FAIL":
            if buf is not None:
                _echo_tail(buf, name)
            halted = name
            break
    # леджер (append): после каждого узла — чтобы планёрка читала даже оборванный прогон
    with open(lp, "a") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    ctx["results"] = results
    # живой ход (--commit) — авто-запись реальных событий в общую библиотеку И матрицу.
    # Реальный гейт записи на ЯМ = `not dry AND commit` (ноды с commit=False дают
    # фейк-PASS: сухие payload «успешны», но НИЧЕГО не отправлено). Поэтому и хуки
    # в библиотеку/матрицу — ТОЛЬКО под этим же гейтом (иначе dry=False/commit=False
    # записал бы фантом-карточки в общую память; dry пишет НИЧЕГО, LB1).
    if not dry and commit:
        syn = _sync_library(ctx, results, hsh)
        if not syn.get("ok"):
            print(f"  {_c('yel', '⚠')} библиотека не обновилась: {syn.get('note')}")
        mtx = _sync_matrix(ctx, results, hsh)
        if not mtx.get("ok"):
            print(f"  {_c('yel', '⚠')} матрица не обновилась: {mtx.get('note')}")
        # эволюционный шов (09.09): закрытый цикл (все PASS) → записанный ХОД в библиотеке
        # процессов (register_cycle1 сам требует all_pass — FAIL/обрыв ходом не становится).
        hod = _sync_process_artifact(ctx, results, hsh, ledger_path=lp)
        if not hod.get("ok"):
            print(f"  {_c('yel', '⚠')} ход не записан: {hod.get('note')}")
    # итог
    pass_n = sum(1 for r in results if r["verdict"] == "PASS")
    fail = [r for r in results if r["verdict"] == "FAIL"]
    verdict = "FAIL" if fail else ("DRY_OK" if dry else "PASS")
    print("\n  " + "─" * 62)
    if verdict == "PASS":
        print(f"  {_c('grn', '■ ЦИКЛ-1 ЗАКРЫТ')} · все узлы PASS с доказательством · артефакт на витрине")
    elif verdict == "DRY_OK":
        print(f"  {_c('yel', '■ DRY-ПРОХОД ЧИСТ')} · узлы готовы · для ЖИВОГО хода: --commit (по слову оператора)")
    else:
        print(f"  {_c('red', '■ ЦИКЛ ОСТАНОВЛЕН')} на узле «{halted}» — починить, перезапустить. Без fake pass.")
    print(f"  хеш {hsh} · PASS {pass_n}/{len(results)} · запись в {lp}\n")
    return {"verdict": verdict, "hash": hsh, "results": results, "profile": profile}


def _missing_store(store_slug, date_str):
    print(f"\n  {_c('red', '✗')} Манифест магазина «{store_slug}» не найден ({store_profiles_path()}).")
    print(f"\n  {_c('b', 'Канонический вход для нового магазина (L13 — без вопросов):')}\n")
    for key, what in REQUIRED_STORE_FIELDS:
        print(f"    {_c('cyn', key):<18} {what}")
    print(f"    {'api_key':<18} YANDEX_MARKET_API_KEY в env (в манифест секреты НЕ пишем)")
    print(f"\n  Пример манифеста (runtime/cycle1/stores.json):")
    example = {"slug": "atlas-express-film", "business_id": 216949599, "campaign_id": 149215943,
               "warehouse_id": 2390811, "donor_category": "vozdushno-puzyrkovaya-plenka",
               "builder": "film", "builder_slug": "puzyrkovaya-plenka",
               "markup": 8.0, "stock_count": 100}
    print("  " + json.dumps(example, ensure_ascii=False, indent=1))
    return {"verdict": "NO_STORE", "profile": None}


def _plenerka(store_slug):
    """Чтение пульса без прогона цепи (утренний узел / быстрый взгляд)."""
    doc = plannerka_read(store_slug)
    if not doc:
        print(f"\n  {_c('yel', 'Пульса ещё нет')} — запусти `--dry` или `--commit`, соберём первый.\n")
        return
    print(f"\n  {_c('b', 'ПУЛЬС ·')} {doc['store']} · {doc['date']}")
    print(f"    вчера узлов: {doc['yesterday_runs']}  вердикты: {doc['yesterday_verdicts']}")
    print(f"    сегодня:     {doc['run_verdicts']}  артефактов-СВЕРКА PASS: {doc['artifacts']}")
    print("    по узлам вчера:")
    for node, vc in (doc.get("by_node") or {}).items():
        print(f"      {node:<14} {vc}")
    print()


def build_parser():
    ap = argparse.ArgumentParser(description="ЦИКЛ-1 движок · Идея→Товар→Витрина (законная цепь узлов)")
    ap.add_argument("--store", default=STORE_DEFAULT, help="манифест магазина (runtime/cycle1/stores.json)")
    # ВЗАИМОИСКЛЮЧАЮЩИЕ dry/commit (аудит env_write_gate:877): раньше --dry был мёртв —
    # `dry = not a.commit` игнорировал a.dry, и `--dry --commit` УХОДИЛ ЖИВЬЁМ. Теперь оба
    # флага в одной exclusive-группе: `--dry --commit` argparse сам отклонит (rc 2 ДО запуска),
    # ни один флаг → dry (безопасный дефолт), --commit один → единственный живой вход (RUBICON).
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--commit", action="store_true", help="ЖИВОЙ ход (dry=False) — по слову оператора (RUBICON)")
    grp.add_argument("--dry", action="store_true", help="сухой ход 0₽ (дефолт и так dry; несовместим с --commit)")
    ap.add_argument("--plenerka", action="store_true", help="только планёрка/пульс (без прогона)")
    ap.add_argument("--verbose", action="store_true",
                    help="полный поток узлов (по умолчанию ТИХО — только пульс-строки)")
    return ap


def _main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    dry = not a.commit
    if a.plenerka:
        _plenerka(a.store)
        return 0
    res = run_cycle(a.store, dry=dry, commit=a.commit, verbose=a.verbose)
    return 0 if res.get("verdict") in ("PASS", "DRY_OK") else 1


if __name__ == "__main__":
    sys.exit(_main())

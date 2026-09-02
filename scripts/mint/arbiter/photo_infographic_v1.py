#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ОРГАН ИНФОГРАФИКИ (ARBITER, стадия после ФОТО-КУЗНИЦЫ) — фирменный SOCC-минимализм на карточку.

ЗАЧЕМ. Одно чистое фото продаёт слабее, чем чистое фото + разумная инфографика: покупатель
получает доп-инфо (материал/размер/комплект) «по законам инфографики» и быстрее принимает решение
в НАШУ пользу. Оператор: «мы должны одним фото КУПИТЬ ЧЕЛОВЕКА». Это тот самый второй кадр карточки.

ГЛАВНЫЙ ИНЖЕНЕРНЫЙ ЗАКОН (почему это БЕЗ ЗАТРАТ и безопасно для маркетплейса):
  Текст рисуем МЫ локально через PIL — НЕ ИИ-модель. Три причины:
    1) генеративные модели (FLUX и пр.) корёжат буквы — чистый текст им не под силу;
    2) МП режет ГЛАВНОЕ фото с текстом/лого (это же закон канона ATLAS EDGE в photo_forge);
    3) PIL-рисование = 0₽, 0 сети, 0 токенов, ДЕТЕРМИНИРОВАНО (тот же стиль каждый раз).
  → Инфографика = ОТДЕЛЬНЫЙ кадр (слот 2+ карточки). ГЛАВНОЕ фото остаётся чистым белым каноном
    и проходит модерацию как раньше. Здесь, на второстепенном кадре, аккуратная марка/текст уместны.

ЗАКОНЫ ИНФОГРАФИКИ (зашиты в макет как константы):
  • иерархия: герой (что это) > факты > марка;   • воздух: широкие поля, не тесним;
  • палитра ≤3 цветов: белый фон + графит-чернила + ОДИН акцент (фирменный SOCC cyan);
  • группировка: факты в нижней ленте, отделены тонкой линией;   • выравнивание по левой сетке;
  • ≤3-5 смысловых блоков; чтение Z-паттерном (герой сверху-слева → товар центр → факты снизу).

ШАБЛОНЫ КАТЕГОРИЙ (арт-канон 2026-09-02, «по сути свои пиксели и за фри»):
  detect_category → 'box'  → ПОСТЕР-ПАСПОРТ: чип-ярус справа-сверху (ступень) + hero-лестница + гигант-
  цифра размера + факт-грань цвета под первой колонкой (ступень как фацет);
  → 'film'  → ПАСПОРТ РУЛОНА: герой-левая колонка + ШТАМП-ось справа (микро-подпись 18 + число +
  цветная линия 6px = ступень) + журнал «ПАРАМЕТРЫ РУЛОНА» снизу;
  → None    → общий монохром: только cyan-бар-константа (закон честности: без оси цвета нет).
  Стиль — Лебедев-минимум: НИ ОДНОГО декоративного элемента без данных (нет кругов/градиентов/теней);
  всякий цвет несёт СМЫСЛ (класс/слои/марку/ось). Кэнон в const: сетка 1024×1280, M=76, Y-шаг 8px.

ЦВЕТ-КАК-СМЫСЛ (GRADE, палитра ступеней): cyan #22D3EE — КОНСТАНТА-бар (никогда не меняется);
  teal #0E8FA0 / indigo #1E63B5 / cherry #C2264E / plum #7F1D3A — ОДНА ступень по факту.
  КОРОБ: plum ← «армирован/усилен/7-слой/слоёв≥6»; cherry ← премиум/слоёв≥5/марка Т-23+;
  teal ← 4-слой; иначе cyan. ПЛЁНКА (ось-приоритет плотность→толщина→пузырёк→ширина): cherry ←
  премиум-слово ИЛИ ≥180г/м² ИЛИ ≥0.05мм ИЛИ пузырёк≥16; indigo ← 130-179/0.03-0.049;
  teal ← 60-129/0.02-0.029 ИЛИ ширина>0.5м; иначе cyan. СЛАБОЕ число оси (плотность 40) = ЧЕСТНО
  рисуем cyan-стандарт (это не премиум) без лживого токена. Текст цветом НЕ красим — цвет только в
  заливках/полосах ≥4px; на светлом чипе текст чернилами, на тёмном — белым (контраст).

ЧЕСТНОСТЬ (закон органа): рисуем ТОЛЬКО факты, которые реально есть в `facts`. Никаких выдуманных
«доставка сегодня»/«гарантия качества» — если оператор не дал факт, его нет на кадре. Нет факта оси →
монохром + cyan-бар, карриер цвета НЕ рисуем (не приписываем товару класс, которого нет).

БРЕНД. Токены — реальные SOCC (SYSTEM/KERNEL/socc-tokens.css), переиспользованы под СВЕТЛУЮ
карточную поверхность: тёмный dashboard-фон SOCC (#0B0F14) здесь становится ЧЕРНИЛАМИ на белом,
фирменный cyan #22D3EE — единственный акцент (узнаваемая подпись SOCC). Слово-марка и акцент —
перекрываемы (BRAND-словарь / env), чтобы оператор сменил «ATLAS EDGE»↔«SOCC» и цвет в 1 строку.

БЕЗОПАСНОСТЬ/RUBICON. Орган ЛОКАЛЬНЫЙ: 0₽, 0 сети — работает поверх УЖЕ выкованного кадра, ничего
не публикует и не тратит. Всегда безопасен. Без PIL — честный отказ (не врём картинкой). База не
открывается — честный отказ. `cost_usd` всегда 0.0.

ИНТЕГРАЦИЯ. `photo_pipeline_v1.forge_card(..., infographic=True)` после ковки чистого кадра зовёт
`compose_infographic(frame_path, facts)` и кладёт 2-й кадр в отчёт. Дефолт off → обратная совместимость.
Лист: никто не импортит этот файл, кроме моста и тестов (аддитивно, ничего не ломаем).
"""
import io
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

try:                                   # PIL опционален: без него — честный отказ, не враньё
    from PIL import Image, ImageDraw, ImageFont, ImageChops
    _HAVE_PIL = True
except Exception:
    _HAVE_PIL = False

# ── Фирменные токены (реальные SOCC, адаптированы под СВЕТЛУЮ карточку) ──────────────
BRAND = {
    "wordmark": "ATLAS EDGE",          # видимая слово-марка магазина (перекрываемо)
    "system":   "",                    # системная подпись ВЫКЛ по умолч. (SOCC — внутренняя, покупателю на карточке не нужна)
    "bg":       (255, 255, 255),       # #FFFFFF — сливается с белым каноном товара
    "ink":      (11, 15, 20),          # #0B0F14 — SOCC near-black как ЧЕРНИЛА
    "muted":    (125, 136, 147),       # #7D8893 — SOCC muted (вторичный текст/подписи)
    "accent":   (34, 211, 238),        # #22D3EE — SOCC cyan: ЕДИНСТВЕННЫЙ акцент = подпись бренда
    "hairline": (228, 231, 235),       # тонкая линия-разделитель (чуть темнее фона)
}

# Кадр 4:5 как у карточки (та же вертикаль, что и канон-фото).
CANVAS_W, CANVAS_H = 1024, 1280

# ── ЗАКОН ЧИСТОЙ БАЗЫ (причина кадра-«инфографика на инфографике», оператор 2026-09-02) ──────
# Мы НИКОГДА не кладём фирменный макет поверх чужой инфографики/бейджей/ватермарка на доноре:
# база обязана быть ЧИСТЫМ студийным кадром (товар на белом, без чужого текста). Чистота — два
# независимых взгляда: ПИКСЕЛИ (белые углы — фон не цветной коллаж) + БУКВЫ (OCR: мало слов —
# нет впаянных бейджей/лозунгов/водяных знаков). Оба дешёвые и локальные (tesseract — subprocess).
# Без доказательства (нет OCR) база чистой НЕ признаётся — строже к худшему, как искатель
# (host_is_clean): «не знаю» ≠ «чисто». Байпас require_clean=False — только осознанно (тест/арт).
CLEAN_CRIT = {
    "corner_thr": 236,          # почти-белый порог пикселя угла (серый студийный фон >236 засчитан)
    "min_bg_white": 0.80,       # ≥80% белых в 4 углах → фон не коллаж/цветная подложка
    "max_ocr_words": 6,         # ≤6 словоподобных токенов → нет впаянного текста (как hunter)
    "ocr_timeout": 15,
}
_OCR_BIN = None                  # резолвится лениво (0 стоимости пока OCR не нужен)


def _tesseract():
    """Путь к tesseract (ленивый кэш). None → OCR недоступен → текст НЕ проверен."""
    global _OCR_BIN
    if _OCR_BIN is not None:
        return _OCR_BIN or None
    _OCR_BIN = ""
    try:
        r = subprocess.run(["tesseract", "--version"], capture_output=True, timeout=8)
        _OCR_BIN = "tesseract" if r.returncode == 0 else ""
    except Exception:
        _OCR_BIN = ""
    return _OCR_BIN or None


def _corner_white_frac_img(img, corner=0.14, thr=None):
    """Доля почти-белых пикселей в 4 углах уже открытого RGB-изображения (0..1) | None.

    Тот же предметно-независимый взгляд на ФОН, что у искателя: цветная подложка/коллаж/градиент
    заваливает метрику, чистый студийный белый → близко к 1.0. Ничего не скачиваем (лист локальный).
    """
    if not _HAVE_PIL:
        return None
    thr = CLEAN_CRIT["corner_thr"] if thr is None else thr
    try:
        g = img.convert("L")
        w, h = g.size
        cw, ch = max(1, int(w * corner)), max(1, int(h * corner))
        px = g.load()
        white = tot = 0
        for ox, oy in ((0, 0), (w - cw, 0), (0, h - ch), (w - cw, h - ch)):
            for x in range(ox, ox + cw, 3):
                for y in range(oy, oy + ch, 3):
                    tot += 1
                    if px[x, y] >= thr:
                        white += 1
        return white / max(1, tot)
    except Exception:
        return None


def _ocr_wordcount_img(img):
    """Число словоподобных токенов по OCR кадра (локальный tesseract, stdin-PNG). None → OCR не вышел.

    Ловит КЛАСС «впаянная инфографика» («60 СМ», «100 М», «премиум», «3-слойный», ник продавца) —
    то, что пиксельно-белые углы не видят (текст в центре/на товаре). Чужие домены/«опт» отсекает
    искатель на этапе выбора донора; здесь — последний рубеж перед наложением нашего макета.
    """
    t = _tesseract()
    if t is None or not _HAVE_PIL:
        return None
    try:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        langs = "rus+eng"
        try:
            r = subprocess.run([t, "-", "stdout", "-l", langs], input=buf.getvalue(),
                               capture_output=True, timeout=CLEAN_CRIT["ocr_timeout"])
        except Exception:
            r = subprocess.run([t, "-", "stdout"], input=buf.getvalue(),
                               capture_output=True, timeout=CLEAN_CRIT["ocr_timeout"])
        text = (r.stdout or b"").decode("utf-8", "ignore")
    except Exception:
        return None
    return len(re.findall(r"[0-9a-zA-Zа-яёА-ЯЁ]{2,}", text))


def clean_base_score(base, text_check=True):
    """Проверить БАЗУ под инфографику: {ok, bg_white_frac, ocr_words, text_checked, text_heavy, why}.

    ok=True только если: база открылась + фон белый (углы) + (текст проверен И слов мало). Без OCR
    текст_checked=False → база чистой НЕ признаётся (строгий закон: не доказано — не чисто).
    base — путь|bytes|PIL.Image. 0₽, 0 сети, локально. Не мутирует base.
    """
    img = _open_base(base)
    if img is None:
        return {"ok": False, "bg_white_frac": None, "ocr_words": None,
                "text_checked": False, "text_heavy": None,
                "why": "база не открылась (битая/не изображение)"}
    bg = _corner_white_frac_img(img)
    words = _ocr_wordcount_img(img) if text_check else None
    bg_ok = (bg is not None and bg >= CLEAN_CRIT["min_bg_white"])
    heavy = (words is not None and words > CLEAN_CRIT["max_ocr_words"])
    text_checked = (words is not None)
    clean = bool(bg_ok and text_checked and not heavy)
    why = None
    if not clean:
        bits = []
        if not bg_ok:
            bits.append("фон не студийно-белый (белизна углов %.2f)" % (bg or -1.0))
        if not text_checked:
            bits.append("текст не проверен (OCR недоступен) — чистой не признаём")
        elif heavy:
            bits.append("на кадре чужой текст/инфографика (%d слов)" % words)
        why = "; ".join(bits)
    return {"ok": clean, "bg_white_frac": bg, "ocr_words": words,
            "text_checked": text_checked, "text_heavy": heavy, "why": why}

# ── ЦВЕТ-КАК-СМЫСЛ (АРТ-КАНОН 2026-09-02): палитра = белый + ink + muted + hairline + cyan-бар + ОДНА ступень ──
# Палитра «постер-паспорт» (арт-совет 4 директоров + судья): фирменный cyan #22D3EE — КОНСТАНТА
# подписи бренда (бар под героем НЕ меняется никогда), а ВАРИАНТ/КЛАСС товара живёт ТОЛЬКО в карриере:
# у короба — чип-ярус (прав-верх) + грань под колонкой-фактом оси; у плёнки — штамп-число (справа)
# с цветным подчёрк-баром. Цвет = ОСЬ ПРОЧНОСТЬ/КЛАСС, детерминированный резолв чистой функцией фактов
# (тот же товар → тот же hue в каждом ЦИКЛЕ): «товар западает по цвету», как dark-cherry/cyan в SOCC.
# ЗАКОН ЧЕСТНОСТИ: нет реального факта ОСИ → кадр монохром + cyan-бар, карриер НЕ рисуем (не выдумываем).
GRADE = {
    # rgb-ступени: одна холодная семья (нарастание глубины = «крепче») + премиум-флаг обеих семей.
    "cyan":   (34, 211, 238),   # #22D3EE — ДОМ-база: cyan-бар + ярус «3-слой/стандарт/нет факта»
    "teal":   (14, 143, 160),   # #0E8FA0 — «усиленная»: 4-слой/Т-23 (короб); средняя плотность,
                                #            толщина 0.02-0.029, ширина>0.5м (плёнка, пром-формат)
    "indigo": (30, 99, 181),    # #1E63B5 — «максимальная масс-маркет»: плотность 130-179 / толщина 0.03-0.049
    "plum":   (127, 29, 58),    # #7F1D3A — редчайший топ короба: слои≥6/7-слой/армирован-усилен
    "cherry": (194, 38, 78),    # #C2264E — ПРЕМИУМ-ФЛАГ: премиум-слово/люкс/vip/prime; у короба Т-24/5-слой;
                                #            у плёнки плотность≥180/толщина≥0.05/пузырёк≥16. Тёмно-вишнёвый =
                                #            кросс-каталоговая память SOCC «вишнёвый = топ-класс».
}
_BAR = BRAND["accent"]               # бренд-бар — ВСЕГДА cyan (подпись «кто» всей сети кадров)
# токены-сигналы ОСИ (смысл → цвет; категория уже scoped через detect_category)
_PREMIUM_WORDS = ("премиум", "premium", "люкс", "luxe", "deluxe", "vip", "prime", "высший класс")
_BOX_PLUM_WORDS = ("армирован", "усиленн", "7-слой", "семи слой", "шестислой")
_FILM_PREMIUM_WORDS = ("премиум", "premium", "люкс", "luxe", "vip", "prime", "экстра", "extra",
                       "профи", "profi", "профессиональн", "professional", "армир", "усиленн")
# слова числительных слоёв (для «пятислойный»/«3-слойный» → N)
_LAYER_WORDS = (("трёх", 3), ("трех", 3), ("четырёх", 4), ("четырех", 4),
                ("пяти", 5), ("пять", 5), ("шести", 6), ("шесть", 6),
                ("семи", 7), ("семь", 7), ("восьми", 8), ("восемь", 8))


def _blob(facts):
    """Склейка всех значений facts в нижнем регистре — для детекции категории/варианта по смыслу."""
    parts = []
    for k, v in (facts or {}).items():
        if isinstance(v, (list, tuple)):
            parts.extend(str(x) for x in v)
        elif v not in (None, ""):
            parts.append(str(v))
    return " ".join(parts).lower()


def detect_category(facts=None):
    """Категория товара → ключ шаблона/семантики: 'box'|'film'|None. По смыслу фактов/названия.

    Держим УЗКО и безопасно: явные слова категории, ложных срабатываний избегаем (нет слова — None →
    общий шаблон 'lean'). Реестр категорий растёт как артефакты органа (см. PHOTO_INFOGRAFIC_V2.md).
    """
    b = _blob(facts)
    film_words = ("плёнк", "пленк", "плен", "пузырч", "bubble", "рулон", "стретч", "stretch",
                  "термоусадоч", "упаковочная лента")
    box_words = ("короб", "гофр", "ящик", "коробк", "box", "картонн")
    if any(w in b for w in film_words):
        return "film"
    if any(w in b for w in box_words):
        return "box"
    return None


def _to_num(v):
    """Первое число из строки/числа | None («0.5», «100 м» → 100)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"[-+]?\d*\.?\d+", str(v).replace(",", "."))
    return float(m.group()) if m else None


def _is_t24(b):
    """Признак премиум-марки Т-24 (в разных написаниях: т-24/т 24/т24/t-24/t24)."""
    return any(w in b for w in ("т-24", "т 24", "т24", "t-24", "t 24", "t24"))


def _width_m(facts):
    """Ширина рулона В МЕТРАХ из фактов в любых единицах (м/см/мм/голое число). None → неизвестно.

    Операторский признак «плёнка свыше 0,5 м → другой цвет»: доноры дают ширину в самых разных
    единицах (ширина_см=120 / ширина_м=0.5 / '1.2 м' / 300 мм), и мы обязаны свести к метрам, иначе
    широкая плёнка останется «обычной». Голое число без единицы трактуем по величине: ≤20 → метры
    (0.5), >20 → сантиметры (120 см = 1.2 м) — типичная нотация карточек.
    """
    raw = None
    for k in ("ширина_м", "ширина_см", "ширина_мм", "ширина", "width_m", "width_cm", "width"):
        v = facts.get(k)
        if v not in (None, "", []):
            raw, rawk = v, k
            break
    if raw is None:
        return None
    s = str(raw).lower().replace(",", ".").strip()
    num = _to_num(raw)
    if num is None:
        return None
    if "мм" in s:
        return num / 1000.0
    if "см" in s:
        return num / 100.0
    if "м" in s.replace("мм", "").replace("см", ""):       # остаточная «м» после вычета мм/см
        return num
    if rawk.endswith("_м") or rawk.endswith("_метров"):
        return num
    if rawk.endswith("_см"):
        return num / 100.0
    if rawk.endswith("_мм"):
        return num / 1000.0
    return num / 100.0 if num > 20 else num                  # голое число: см-нотация vs метры


def _layer_count(b):
    """Число слоёв картона из blob («5-слойный», «3 слоя», «пятислойный», «слои: 5») | None.

    Ищет сперва цифровой паттерн «N-слой», затем словесные числительные («пятислой»→5).
    Только из РЕАЛЬНО пришедшего текста — закон честности (ничего не выдумываем).
    """
    m = re.search(r"(\d{1,2})\s*-?\s*сло[йя]", b)
    if m:
        return int(m.group(1))
    for w, n in _LAYER_WORDS:
        if (w + "слой") in b or (w + "-слой") in b or (w + " слой") in b:
            return n
    return None


def _t_grade(b):
    """Число марки картона Т-24/Т-23 («т 24», «т-24», «т24») | None. «Т-24»→24."""
    m = re.search(r"т[\s-]?(\d{1,2})\b", b)
    return int(m.group(1)) if m else None


def _sklon_layer(n):
    """Русская склонённость токена чипа: 1 СЛОЙ / 2-4 СЛОЯ / 5+ СЛОЁВ."""
    n = abs(int(n))
    d, dd = n % 10, n % 100
    if 11 <= dd <= 14:
        return "СЛОЁВ"
    if d == 1:
        return "СЛОЙ"
    if d in (2, 3, 4):
        return "СЛОЯ"
    return "СЛОЁВ"


def _fmt_num(n):
    """Число для штампа: «120», «0,5» (RU-запятая), без хвостовых нулей."""
    if n is None:
        return ""
    try:
        if float(n).is_integer():
            return "%d" % int(n)
        s = ("%g" % n)
        return s.replace(".", ",")
    except Exception:
        return str(n).replace(".", ",")


def _split_val_unit(raw):
    """«600×400×400 мм» → («600×400×400», «мм»); «60×40» → («60×40», ''). Число отдельно от единицы."""
    s = " ".join(str(raw).split())
    m = re.search(r"^(.*?)\s+([а-яё]{1,5}|мм|см|м²|м|л|шт|кг|г)\s*$", s)
    if m and m.group(1).strip():
        return m.group(1).strip(), m.group(2).lower()
    m = re.search(r"^(.*?)(мм|см|м²|м|л|шт|кг|г)$", s)
    if m and m.group(1).strip() and not m.group(1).strip()[-1].isdigit():
        return m.group(1).strip(), m.group(2).lower()
    return s, ""


def grade_resolve(facts=None, category=None):
    """Резолв ОДНОГО яруса/класса (детерминированно, из наличных фактов) → словарь канона.

    Возврат: {tier, rgb, label, token, axis_key, axis_label, unit, num, has_fact, why}
      tier      — 'cyan'|'teal'|'indigo'|'cherry'|'plum' (ключ GRADE);
      rgb       — цвет ступени;
      has_fact  — есть РЕАЛЬНЫЙ факт ОСИ (слои/марка Т/премиум/плотность/толщина/ширина) → карриер рисуем;
      axis_key  — какой ключ facts стал причиной (привязка чипа/грани/штампа к данным);
      axis_label/unit/num — для штампа плёнки (микро-ось, единица, число);
      token     — текст чипа короба («Т-24»/«ПРЕМИУМ»/«5 СЛОЁВ»/None);
      why       — человекочитаемая причина (для отчёта/тестов).
    Палитра ≤2 акцентов: cyan-бар-константа + ОДНА ступень. Первый сработавший приоритет побеждает.
    """
    facts = facts or {}
    cat = category or detect_category(facts)
    base = {"tier": "cyan", "rgb": GRADE["cyan"], "label": "", "token": None,
            "axis_key": None, "axis_label": None, "unit": "", "num": None,
            "has_fact": False, "why": "нет факта оси → монохром + cyan-бар (карриер не рисуем)"}
    if cat not in ("box", "film"):
        return base
    b = _blob(facts)
    layerN = _layer_count(b)
    premium = any(w in b for w in _PREMIUM_WORDS)
    if cat == "box":
        tg = _t_grade(b)
        armored = any(w in b for w in _BOX_PLUM_WORDS)
        has = bool(premium or armored or layerN is not None or tg is not None)
        base["has_fact"] = has
        if not has:
            return base
        if armored or (layerN is not None and layerN >= 6):
            tier = "plum"
            token = "%d %s" % (layerN, _sklon_layer(layerN)) if layerN else "АРМИРОВАННЫЙ"
            why = ("7-слой/армирован-усилен%s" % (" (%d слоёв)" % layerN if layerN else ""))
        elif premium or (layerN is not None and layerN >= 5) or (tg is not None and tg >= 23):
            tier = "cherry"
            if premium and tg is None:
                token, why = "ПРЕМИУМ", "премиум-лексема"
            elif tg is not None:
                token, why = "Т-%d" % tg, "марка Т-%d (≥Т-23)" % tg
            else:
                token, why = "%d %s" % (layerN, _sklon_layer(layerN)), "%d-слой (≥5)" % layerN
        elif (layerN is not None and layerN == 4) or (tg is not None and tg == 23):
            tier, token = "teal", "%d %s" % (layerN, _sklon_layer(layerN)) if layerN else "Т-23"
            why = "4-слой / Т-23 (усиленная)"
        else:
            tier = "cyan"
            token = "%d %s" % (layerN, _sklon_layer(layerN)) if layerN is not None else None
            why = "стандарт (%d-слой)" % layerN if layerN is not None else "стандарт (без слоёв)"
        base.update({"tier": tier, "rgb": GRADE[tier], "token": token,
                     "axis_key": "слои_картона" if layerN is not None else ("марка" if tg is not None else "вид"),
                     "why": why})
        return base
    # ── film: ось-приоритет плотность → толщина → пузырёк → ширина; премиум-слово = флаг-гейт ──
    if premium or any(w in b for w in _FILM_PREMIUM_WORDS):
        base.update({"tier": "cherry", "rgb": GRADE["cherry"], "label": "ПРЕМИУМ", "token": "ПРЕМИУМ",
                     "axis_key": "вид", "axis_label": "ПРЕМИУМ", "has_fact": True,
                     "why": "премиум-лексема в названии/виде/материале"})
        return base
    axes = [
        ("плотность_г_м2", "плотность", "Плотность", "г/м²",
         lambda n: n >= 180 and ("cherry", 0) or n >= 130 and ("indigo", 0) or n >= 60 and ("teal", 0) or ("cyan", 0)),
        ("толщина_мм", "толщина", "Толщина", "мм",
         lambda n: n >= 0.05 and ("cherry", 0) or n >= 0.03 and ("indigo", 0) or n >= 0.02 and ("teal", 0) or ("cyan", 0)),
        ("диаметр_пузырька_мм", "bubble_mm", "Пузырёк", "мм",
         lambda n: n >= 16 and ("cherry", 0) or ("cyan", 0)),
    ]
    for k1, k2, lab, unit, gate in axes:
        raw = facts.get(k1)
        if raw in (None, ""):
            raw = facts.get(k2)
        num = _to_num(raw)
        if num is None:
            continue
        tier = gate(num)[0]
        base.update({"tier": tier, "rgb": GRADE[tier], "label": lab, "axis_key": k1 if facts.get(k1) not in (None, "") else k2,
                     "axis_label": lab, "unit": unit, "num": num, "has_fact": True,
                     "token": ("%s %s" % (_fmt_num(num), unit)) if tier != "cyan" else None,
                     "why": "%s %s → %s" % (lab, _fmt_num(num), tier)})
        return base
    w = _width_m(facts)                     # ширина без силовых чисел → кодирует ФОРМАТ (честно)
    if w is not None:
        tier = "teal" if w > 0.5 else "cyan"
        base.update({"tier": tier, "rgb": GRADE[tier], "label": "Ширина", "axis_key": "ширина_м",
                     "axis_label": "ШИРИНА", "unit": "м", "num": w, "has_fact": True,
                     "token": None if tier == "cyan" else "ПРОМ-ФОРМАТ",
                     "why": "ширина %s м → %s" % (_fmt_num(w), tier)})
        return base
    return base


def variant_signal(facts=None, category=None):
    """Сигнал класса/варианта (для отчёта и внешних читателей): {kind,label,key} | None (не-категория)."""
    g = grade_resolve(facts, category)
    if not g.get("has_fact"):
        return None
    return {"kind": g["tier"], "label": g["axis_label"] or g["token"] or g["tier"],
            "key": g.get("axis_key")}


def resolve_accent(facts=None, category=None, default=None):
    """Цвет СТУПЕНИ (RGB-кортеж) из резолва; cyan-дефолт, когда факта оси нет (карриер не рисуем)."""
    g = grade_resolve(facts, category)
    if not g.get("has_fact"):
        return tuple(default or BRAND["accent"])
    return tuple(g["rgb"])

# Цепочки шрифтов macOS (Inter не установлен → SF/Helvetica/Arial — чистый минимализм). Env перекрывает.
_FONT_REG = [
    os.environ.get("INFOGRAPHIC_FONT", ""),
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
_FONT_BOLD = [
    os.environ.get("INFOGRAPHIC_FONT_BOLD", ""),
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/SFNSDisplay.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/SFNS.ttf",
]

# Приоритет фактов на ленту = ПОРЯДОК в этом списке (важнее → выше). Берём ТОЛЬКО присутствующие
# ключи (честно), дедуп ПО ПОДПИСИ, ≤max_n. Структура — строго 2-кортеж (key, label): мост читает
# `for key, label in _SPEC_KEYS` (третий элемент уронит распаковку). Ключи — РЕАЛЬНЫЙ словарь наших
# источников (проверено grep'ом): категорийщик _spec → length/width/height/weight/материал/
# слои_картона/штук_в_упаковке; плёнка/поставщик → ширина_м/длина_м/плотность_г_м2/толщина_мм/
# диаметр_пузырька_мм; SCOUT-хантер → kind/bubble_mm; плюс общие размер/габариты/цвет/…
#
# ЗАКОН КУРАТОРА (директива: «только существенные характеристики, влияющие на выбор»):
#   • сперва РАЗМЕР (главный драйвер упаковки), затем КОЛИЧЕСТВО, затем МАТЕРИАЛ/СТРУКТУРА;
#   • вторичные (объём/цвет/назначение/мощность/вес) НЕ выкинуты, а ОПУЩЕНЫ вниз: при max_n=3 их
#     вытесняют драйверы, когда те есть (короб/плёнка), но для иной категории (одежда → цвет, техника
#     → мощность, где это И ЕСТЬ выбор) они честно доступны. Так орган остаётся ОБЩИМ, а не cargo-only;
#   • голые length/width/height (см, плита профиля МП) — НЕ источник «Размера»: комбинированный
#     размер/габариты/dims_raw несёт габарит ОДНОЙ строкой (три строки Д/Ш/В вытеснили бы количество);
#   • ВЫКИНУТЫ совсем (плюмбинг МП / филлер, не влияет на выбор): length/width/height, weight/вес_кг,
#     страна/страна_производства, бренд/brand, форма, марка/«марка картона».
_SPEC_KEYS = [
    # — РАЗМЕР: комбинированные формы → одна строка; затем standalone-габариты рулона плёнки (метры) —
    ("размер", "Размер"), ("размеры", "Размер"), ("габариты", "Размер"), ("dims_raw", "Размер"),
    ("ширина_м", "Ширина"), ("длина_м", "Длина"),
    # — КОЛИЧЕСТВО в упаковке: драйвер оптовой закупки —
    ("штук_в_упаковке", "В упаковке"), ("в упаковке", "В упаковке"), ("количество", "В упаковке"),
    ("комплектация", "В упаковке"), ("комплект", "В упаковке"),
    # — МАТЕРИАЛ / СТРУКТУРА / прочность —
    ("материал", "Материал"), ("слои_картона", "Слои"), ("слои", "Слои"),
    ("плотность_г_м2", "Плотность"), ("плотность", "Плотность"),
    ("толщина_мм", "Толщина"), ("толщина", "Толщина"), ("состав", "Состав"),
    ("диаметр_пузырька_мм", "Пузырёк"), ("bubble_mm", "Пузырёк"),
    # — ВТОРИЧНЫЕ: опущены вниз (для НЕ-упаковочных категорий это и есть выбор) —
    ("объём", "Объём"), ("объем", "Объём"), ("цвет", "Цвет"),
    ("назначение", "Назначение"), ("мощность", "Мощность"), ("вес", "Вес"),
]


def _load_font(size, bold=False):
    """Первый доступный шрифт из цепочки нужного веса; иначе PIL default (никогда не падаем)."""
    if not _HAVE_PIL:
        return None
    for path in (_FONT_BOLD if bold else _FONT_REG):
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _text_w(draw, text, font):
    """Ширина строки, устойчиво к версиям Pillow (getlength → textbbox → грубая оценка)."""
    if font is None:
        return len(text) * 6
    try:
        return draw.textlength(text, font=font)
    except Exception:
        pass
    try:
        b = draw.textbbox((0, 0), text, font=font)
        return b[2] - b[0]
    except Exception:
        return len(text) * (getattr(font, "size", 12) * 0.5)


def _fit_text(draw, text, font, max_w):
    """Обрезает строку многоточием, если не влезает в max_w (защита сетки от переполнения)."""
    text = " ".join(str(text).split())
    if _text_w(draw, text, font) <= max_w:
        return text
    ell = "…"
    while text and _text_w(draw, text + ell, font) > max_w:
        text = text[:-1]
    return (text + ell) if text else ell


def _wrap(draw, text, font, max_w, max_lines=2):
    """Жадный перенос строки в ≤max_lines под ширину max_w; остаток — многоточием в последней строке.

    Чинит «5-слойный гоф…»: продающий факт не режем в огрызок, а переносим на 2 строки целиком.
    """
    words = " ".join(str(text).split()).split(" ")
    if not words or words == [""]:
        return [""]
    lines, cur, idx = [], "", 0
    while idx < len(words) and len(lines) < max_lines:
        w = words[idx]
        trial = (cur + " " + w).strip()
        if not cur or _text_w(draw, trial, font) <= max_w:
            cur, idx = trial, idx + 1
        else:
            lines.append(cur)
            cur = ""
    if cur and len(lines) < max_lines:
        lines.append(cur)
        cur = ""
    if idx < len(words):                                # остаток не влез — свернём в последнюю строку
        leftover = " ".join(words[idx:])
        base = (lines.pop() if lines else "")
        lines.append(_fit_text(draw, (base + " " + leftover).strip(), font, max_w))
    lines = [ln if _text_w(draw, ln, font) <= max_w else _fit_text(draw, ln, font, max_w) for ln in lines]
    return lines[:max_lines] if lines else [""]


def _autocrop_subject(img, white_thr=244, pad_frac=0.05):
    """Кроп по bbox предмета (не-белые пиксели) + мягкое поле. Делает товар КРУПНЫМ в кадре.

    Корень жалобы «товар мелкий»: канон-база — 4:5 с белыми полями, потому в зоне инфографики
    предмет висит крошкой. Обрезаем белые поля → предмет заполняет зону. Не нашли предмет / ошибка
    → возвращаем как есть (честно, без падения). Белый фон вокруг остатка сохраняется → слияние цело.
    """
    if not _HAVE_PIL:
        return img
    try:
        gray = img.convert("L")
        mask = gray.point(lambda p: 255 if p < white_thr else 0)   # предмет=где темнее белого порога
        bbox = mask.getbbox()
        if not bbox:
            return img
        l, t, r, b = bbox
        w, h = img.size
        pad = int(min(w, h) * pad_frac)
        l, t = max(0, l - pad), max(0, t - pad)
        r, bt = min(w, r + pad), min(h, b + pad)
        if r - l < 16 or bt - t < 16:                              # слишком мелкий bbox — не режем
            return img
        return img.crop((l, t, r, bt))
    except Exception:
        return img


def _hero_line(facts):
    """Строка-герой: что это. Из название/вид/тип/наименование; иначе пусто (не выдумываем)."""
    facts = facts or {}
    for k in ("название", "наименование", "вид", "тип", "товар", "name", "title"):
        v = facts.get(k)
        if v:
            s = " ".join(str(v).split())
            return s[:1].upper() + s[1:] if s else s
    return ""


def _specs(facts, max_n=3):
    """До max_n фактов для нижней ленты: ТОЛЬКО присутствующие ключи, без дублей подписей."""
    facts = facts or {}
    low = {str(k).strip().lower(): v for k, v in facts.items() if v not in (None, "", [])}
    out, seen = [], set()
    for key, label in _SPEC_KEYS:
        if key in low and label not in seen:
            val = " ".join(str(low[key]).split())
            if val:
                out.append((label, val))
                seen.add(label)
        if len(out) >= max_n:
            break
    return out


def _open_base(base):
    """База (путь|bytes|PIL.Image) → RGB-изображение или None (честно, без падения)."""
    if not _HAVE_PIL:
        return None
    try:
        if hasattr(base, "convert"):                 # уже PIL.Image
            return base.convert("RGB")
        if isinstance(base, (bytes, bytearray)):
            return Image.open(io.BytesIO(bytes(base))).convert("RGB")
        p = Path(str(base))
        if not p.exists():
            return None
        return Image.open(p).convert("RGB")
    except Exception:
        return None


# ── ШАБЛОНЫ КАТЕГОРИЙ (АРТ-КАНОН 2026-09-02): render() = диспетчер box|film|lean ─────────────
# Раскладка построена на «сетке воздуха»: холст 1024×1280, поле M=76 (0.074W), x∈[76,948] (0.926W),
# ширина колонки CW=872. Каждая координата Y привязывается к шагу 8px (_snap8) — ровная типографика
# без «волосков». Два веса REG/BOLD; ручной трекинг ТОЛЬКО у слово-марки и микро-подписей.
# ЗАКОНЫ: никаких окружностей/эллипсов/градиентов/теней (пустая декорация запрещена — каждый элемент
# несёт данные); текст НИКОГДА не красим (цвет только заливками/линиями ≥4px); ≤2 акцентов на кадр
# (cyan-бар-константа + ОДНА ступень цвета варианта в карриере). «×» = U+00D7.
_M = 76                                            # поле ≈7.4% ширины — воздух (арт-канон)
_X0, _X1 = _M, CANVAS_W - _M                       # 76 / 948
_CW = _X1 - _X0                                    # 872
_STAMP_X = int(CANVAS_W * 0.62)                    # 634 — левая граница колонки штампа плёнки
_HERO_MAXW = int(CANVAS_W * 0.60) - _X0            # 538 — плёночный герой не заезжает под штамп
_BIG_LABELS = {"Размер", "Габариты", "Размеры"}    # колонка-гигант (семейство размера) в паспорте короба


def _snap8(y):
    """Y к шагу 8px (воздух-сетка): ровная полка для линий/строк."""
    return int(round(float(y) / 8.0) * 8)


def _ink_or_white(fill):
    """Чернила или белый на заливке по яркости (текст чипа/плашки всегда контрастен)."""
    r, g, b = fill[:3]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return BRAND["ink"] if lum > 150 else (255, 255, 255)


def _draw_tracked(d, xy, text, font, fill, tracking):
    """Ручной трекинг строки побуквенно (слово-марка/микро-капс). Пробел не получает трекинг."""
    x, y = xy
    for ch in str(text):
        d.text((x, y), ch, font=font, fill=fill)
        x += int(_text_w(d, ch, font) + (tracking if ch != " " else 0))


def _wordmark(d, b, y=62):
    """Слово-марка вразрядку (muted, капс) — фирменный «регистрационный знак» вверху слева."""
    f = _load_font(22, bold=False)
    if f is None:
        return
    _draw_tracked(d, (_X0, y), str(b["wordmark"]).upper(), f, b["muted"], 2)


def _fit_val(d, val, ladder, max_w, max_lines=2, bold=True):
    """Выбор кегля: самый крупный из ladder, где значение влезает в ≤max_lines. → (size, font, lines)."""
    last = None
    for size in ladder:
        f = _load_font(size, bold=bold)
        if f is None:
            continue
        lines = _wrap(d, val, f, max_w, max_lines=max_lines)
        last = (size, f, lines)
        if len(lines) <= max_lines:
            return (size, f, lines)
    return last or (ladder[-1], _load_font(ladder[-1], bold=bold), [val])


def _paste_center(canvas, prod, box):
    """Вписать фото товара в прямоугольник по центру (белый фон базы сливается с канвасом)."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    if bw <= 0 or bh <= 0 or prod is None:
        return
    pw, ph = prod.size
    scale = min(bw / pw, bh / ph)
    nw, nh = max(1, int(pw * scale)), max(1, int(ph * scale))
    fitted = prod.resize((nw, nh))
    ox = x0 + (bw - nw) // 2
    oy = y0 + (bh - nh) // 2
    canvas.paste(fitted, (ox, oy))


# ── BOX-ШАБЛОН «ПОСТЕР-ПАСПОРТ» ─────────────────────────────────────────────────────────────
# Чип-ярус прав-верх (цвет = класс/слои/марка) → ГЕРОЙ жирный → cyan-бар под ним → фото →
# нижний ПАССПОРТ: размер-семейство ГИГАНТСКОЙ цифрой + единица мелко на той же базовой линии,
# остальные факты ≤2 колонок; когда чипа нет — ≤3 равных колонок. Цвет-фасет 6px под колонкой-осью.
def _macro_box(d, canvas, prod, facts, g, b):
    specs = _specs(facts)
    # ── чип-ярус (карриер варианта: заливка цветом ступени + капс-токен). Только если есть текст.
    chip_w = 0
    chip_text = g.get("token")
    if chip_text:
        fc = _load_font(22, bold=True)
        chip_w = int(_text_w(d, chip_text, fc)) + 36
        fill = tuple(g["rgb"])
        d.rectangle([_X1 - chip_w, 108, _X1, 150], fill=fill)
        d.text((_X1 - chip_w + 18, 117), chip_text, font=fc, fill=_ink_or_white(fill))
    hero_w = (_CW - chip_w - 24) if chip_w else _CW
    # ── герой: жирно/чернила, лестница 88→76→64→52, ≤2 строк, ширина без чипа.
    hero = _hero_line(facts)
    hero_bottom = 150
    if hero:
        size, f, lines = _fit_val(d, hero, (88, 76, 64, 52), hero_w, max_lines=2)
        y = 150
        for ln in lines:
            d.text((_X0, y), ln, font=f, fill=b["ink"])
            y += size
        hero_bottom = _snap8((y - size) + int(size * 0.45))
    # ── cyan-бар под героем — ВСЕГДА константа (подпись «кто»); 140×6.
    bar_y = _snap8(hero_bottom + 18)
    d.rectangle([_X0, bar_y, _X0 + 140, bar_y + 6], fill=_BAR)
    zone_top = bar_y + 30
    if not specs:
        _paste_center(canvas, prod, (_X0, zone_top, _X1, CANVAS_H - _M - 8))
        return
    # ── паспорт фактов прижат к низу: значения ВЫРОВНЕНЫ ПО БАЗОВОЙ B=1184, подписи-капс над ними.
    big = specs[0][0] in _BIG_LABELS                 # размер-семейство → ГИГАНТ-цифра + мелкая единица
    n = len(specs)
    if big:
        n_rest = n - 1
        frac0 = 0.62 if n_rest == 1 else (0.52 if n_rest == 2 else 1.0)
        fracs = [frac0] + (([(1.0 - frac0) / n_rest] * n_rest) if n_rest else [])
    else:
        fracs = [1.0 / n] * n
    xs, x = [], _X0
    for fr in fracs:                                 # (x0, w) колонок по дробям ширины
        w = int(round(_CW * fr))
        xs.append((x, w))
        x += w
    B = 1184
    cols, maxH = [], 0
    for i, (label, val) in enumerate(specs):
        cx0, cw = xs[i]
        if big and i == 0:
            number, unit = _split_val_unit(val)
            un = _load_font(20, bold=False)
            u_w = _text_w(d, unit, un) if unit else 0
            size, f, _l = _fit_val(d, number, (56, 48, 40), cw - (u_w + 10), max_lines=1)
            cap = int(size * 0.8)
            cols.append({"kind": "big", "label": label, "val": number, "unit": unit, "size": size,
                         "font": f, "unit_font": un, "unit_w": u_w, "cap": cap, "cx0": cx0, "cw": cw})
            maxH = max(maxH, cap)
        else:
            size, f, lines = _fit_val(d, val, (36, 32, 28), cw, max_lines=2)
            cap = int(size * 0.82)
            h = cap if len(lines) == 1 else cap + size + 6
            cols.append({"kind": "col", "label": label, "lines": lines, "size": size, "font": f,
                         "cap": cap, "h": h, "cx0": cx0, "cw": cw})
            maxH = max(maxH, h)
    lab_row = _snap8(B - maxH - 28)                  # базовая подписей — над самой высокой колонкой
    P = _snap8(lab_row - 44)                         # верх паспорта (hairline-разделитель)
    d.line([(_X0, P), (_X1, P)], fill=b["hairline"], width=2)
    f_lbl = _load_font(15, bold=False)
    for c in cols:
        cx = c["cx0"]
        d.text((cx, lab_row - 15), c["label"].upper(), font=f_lbl, fill=b["muted"])
        if c["kind"] == "big":
            d.text((cx, B - c["cap"]), c["val"], font=c["font"], fill=b["ink"])
            if c["unit"]:
                d.text((cx + _text_w(d, c["val"], c["font"]) + 8, B - 16), c["unit"],
                       font=c["unit_font"], fill=b["muted"])
        elif len(c["lines"]) == 1:
            d.text((cx, B - c["cap"]), c["lines"][0], font=c["font"], fill=b["ink"])
        else:
            d.text((cx, B - c["cap"] - (c["size"] + 6)), c["lines"][0], font=c["font"], fill=b["ink"])
            d.text((cx, B - c["cap"]), c["lines"][1], font=c["font"], fill=b["ink"])
    # ── фасет 6px цвета варианта под колонкой-осью (только когда чип-ярус есть).
    if chip_w:
        a = cols[0]
        if a["kind"] == "big":
            wnum = _text_w(d, a["val"], a["font"])
        else:
            wnum = _text_w(d, a["lines"][0], a["font"])
        d.rectangle([a["cx0"], B + 12, a["cx0"] + wnum, B + 18], fill=tuple(g["rgb"]))
    # ── зона фото товара между cyan-баром и паспортом.
    _paste_center(canvas, prod, (_X0, zone_top, _X1, P - 22))


# ── FILM-ШАБЛОН «ПАСПОРТ РУЛОНА» ────────────────────────────────────────────────────────────
# Слева-верх ГЕРОЙ (шириной ≤0.60W, не заезжает под штамп), справа-верх ШТАМП-ОСЬ: микро-капс
# подпись, число жирно + единица чернилами, цветное подчёрк-число 6px (= цвет ступени). Внизу —
# журнал строк «ПАРАМЕТРЫ РУЛОНА» (строка оси принудительно в топ-3): подпись слева, значение
# справа по правому краю, hairline под каждой строкой.
def _macro_film(d, canvas, prod, facts, g, b):
    # ── герой слева: лестница 54→48→42→36, lh=size×1.16, ≤3 строк, ширина ≤0.60W.
    hero = _hero_line(facts)
    hero_bottom = 108
    if hero:
        size, f, lines = _fit_val(d, hero, (54, 48, 42, 36), _HERO_MAXW, max_lines=3)
        y = 108
        lh = int(size * 1.16)
        for ln in lines:
            d.text((_X0, y), ln, font=f, fill=b["ink"])
            y += lh
        hero_bottom = _snap8((y - lh) + int(size * 0.4))
    # ── штамп-ось справа (правый край 948, верх ≈108). Карриер = цветное подчёрк-число.
    stamp = (g.get("axis_label") or "").upper()
    has_num = g.get("num") is not None
    if stamp:
        if g.get("token") == "ПРЕМИУМ" and not has_num:          # слово-штамп премиума без числа
            fs = _load_font(28, bold=True)
            d.text((_X1 - _text_w(d, "ПРЕМИУМ", fs), 120), "ПРЕМИУМ", font=fs, fill=b["ink"])
            pw = _text_w(d, "ПРЕМИУМ", fs)
            d.rectangle([_X1 - pw, 158, _X1, 164], fill=tuple(g["rgb"]))
        elif has_num:
            cap = _load_font(18, bold=False)
            d.text((_X1 - _text_w(d, stamp, cap), 100), stamp, font=cap, fill=b["muted"])
            num = _fmt_num(g["num"])
            unit = g.get("unit") or ""
            un = _load_font(20, bold=False)
            u_w = _text_w(d, unit, un) if unit else 0
            size, f, lines = _fit_val(d, num, (40, 36, 32), _CW - _HERO_MAXW - 20 - u_w, max_lines=1)
            nw = _text_w(d, num, f)
            d.text((_X1 - nw - u_w, 142), num, font=f, fill=b["ink"])
            if unit:
                d.text((_X1 - u_w, 142 + size - 20), unit, font=un, fill=b["ink"])
            d.rectangle([_X1 - nw - u_w, 142 + size + 12, _X1 - u_w, 142 + size + 18],
                        fill=tuple(g["rgb"]))
    # ── cyan-бар под героем (120×6, константа).
    bar_y = _snap8(hero_bottom + 18)
    d.rectangle([_X0, bar_y, _X0 + 120, bar_y + 6], fill=_BAR)
    # ── журнал «ПАРАМЕТРЫ РУЛОНА» снизу: строки подпись(слева)/значение(справа по 948).
    rows = _specs(facts, max_n=3)
    ak = g.get("axis_key")
    if ak and g.get("axis_label") and g.get("has_fact"):
        ax_spec = None
        for key, label in _SPEC_KEYS:
            if key == ak and (facts or {}).get(key) not in (None, "", []):
                ax_spec = (label, str((facts or {}).get(key)))
                break
        if ax_spec and not any(r[0] == ax_spec[0] for r in rows):
            rows = rows[:2] + [ax_spec] if len(rows) >= 2 else rows + [ax_spec]
            rows = rows[:3]
    if rows:
        f_hdr = _load_font(15, bold=False)
        # высота журнала: hairline+заголовок + строки (56/88)
        row_hs = []
        for label, val in rows:
            fv = _load_font(28, bold=True)
            _s, _f, lines = _fit_val(d, str(val), (28, 24, 20), int(_CW * 0.52), max_lines=2)
            row_hs.append(88 if len(lines) > 1 else 56)
        hdr_h = 46
        passport_h = 12 + hdr_h + sum(row_hs)
        P = _snap8(1216 - passport_h)
        d.line([(_X0, P), (_X1, P)], fill=b["hairline"], width=2)
        d.text((_X0, P + 12), "ПАРАМЕТРЫ РУЛОНА", font=f_hdr, fill=b["muted"])
        y = P + hdr_h
        f_lbl = _load_font(16, bold=False)
        for i, (label, val) in enumerate(rows):
            rh = row_hs[i]
            base = y + (32 if rh == 56 else 40)
            d.text((_X0, base - int(rh * 0.42)), label, font=f_lbl, fill=b["muted"])
            _s, _f, lines = _fit_val(d, str(val), (28, 24, 20), int(_CW * 0.52), max_lines=2)
            if len(lines) <= 1:
                d.text((_X1 - _text_w(d, str(val), _f), base - int(_s * 0.8)), str(val), font=_f, fill=b["ink"])
            else:
                vy = base + 6
                for ln in reversed(lines):
                    vy -= _s + 4
                    d.text((_X1 - _text_w(d, ln, _f), vy), ln, font=_f, fill=b["ink"])
            d.line([(_X0, y + rh - 2), (_X1, y + rh - 2)], fill=b["hairline"], width=2)
            y += rh
        _paste_center(canvas, prod, (_X0, bar_y + 30, _X1, P - 10))
    else:
        _paste_center(canvas, prod, (_X0, bar_y + 30, _X1, CANVAS_H - _M))


def _macro_lean(d, canvas, prod, facts, b):
    """Общий (не box/film) шаблон — монохром + cyan-бар, без цветных карриеров (закон честности)."""
    hero = _hero_line(facts)
    hero_bottom = 120
    if hero:
        size, f, lines = _fit_val(d, hero, (64, 52, 44), _CW, max_lines=2)
        y = 120
        for ln in lines:
            d.text((_X0, y), ln, font=f, fill=b["ink"])
            y += size
        hero_bottom = _snap8((y - size) + int(size * 0.4))
    d.rectangle([_X0, _snap8(hero_bottom + 18), _X0 + 120, _snap8(hero_bottom + 18) + 6], fill=_BAR)
    specs = _specs(facts)
    band_top = 1124 if specs else CANVAS_H - _M
    _paste_center(canvas, prod, (_X0, _snap8(hero_bottom + 18) + 30, _X1, band_top - 20))
    if specs:
        d.line([(_X0, band_top), (_X1, band_top)], fill=b["hairline"], width=2)
        n = len(specs)
        colw = _CW / n
        for i, (label, val) in enumerate(specs):
            cx = _X0 + i * colw
            d.text((cx, band_top + 22), label.upper(), font=_load_font(15, bold=False), fill=b["muted"])
            _s, _f, lines = _fit_val(d, val, (30, 26, 22), colw - 18, max_lines=2)
            vy = band_top + 50
            for ln in lines:
                d.text((cx, vy), ln, font=_f, fill=b["ink"])
                vy += _s + 6


def render(base, facts=None, brand=None, zoom=True):
    """Собирает PIL-кадр инфографики (без записи на диск). None → нельзя собрать (нет PIL/битая база).

    ДИСПЕТЧЕР шаблонов категорий: detect_category → 'box' → ПОСТЕР-ПАСПОРТ (чип-ярус + гигант-цифра
    размера), 'film' → ПАСПОРТ РУЛОНА (штамп-ось справа + журнал-строки), None → общий монохром.
    zoom=True → авто-кроп по предмету, чтобы товар был КРУПНЫМ (чинит «товар мелкий на кадре»).
    """
    if not _HAVE_PIL:
        return None
    prod = _open_base(base)
    if prod is None:
        return None
    if zoom:
        prod = _autocrop_subject(prod)
    b = dict(BRAND)
    if brand:
        b.update(brand)
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), b["bg"])
    d = ImageDraw.Draw(canvas)
    cat = detect_category(facts)
    g = grade_resolve(facts, cat)
    _wordmark(d, b)
    if cat == "box":
        _macro_box(d, canvas, prod, facts, g, b)
    elif cat == "film":
        _macro_film(d, canvas, prod, facts, g, b)
    else:
        _macro_lean(d, canvas, prod, facts, b)
    # Системная подпись (если явно задана) — внизу-справа. По умолчанию пусто (SOCC — внутренняя марка).
    sysmark = str(b.get("system") or "").strip()
    if sysmark:
        f_sys = _load_font(20, bold=False)
        d.text((_X1 - _text_w(d, sysmark, f_sys), CANVAS_H - 40), sysmark, font=f_sys, fill=b["muted"])
    return canvas


def compose_infographic(base, facts=None, brand=None, out_dir=None, deliver_dir=None,
                        open_it=False, tag="item", dry=True, zoom=True, require_clean=True):
    """Куёт фирменный инфографический кадр поверх УЖЕ готового фото. Всегда 0₽, 0 сети.

    base       — путь|bytes|PIL.Image готового кадра товара (ЧИСТОГО: товар на белом, без чужих
                 текстов/инфографики/водяных знаков — по умолчанию это ПРОВЕРЯЕТСЯ, см. require_clean).
    facts      — словарь фактов; на ленту идут ТОЛЬКО присутствующие (честно), ≤3.
    brand      — перекрытие BRAND (wordmark/accent/…), 1 строка на смену марки/цвета.
    out_dir    — куда писать кадр (дефолт state/forged/); deliver_dir — доп. копия «для глаз» (Desktop).
    open_it    — открыть в Просмотре (только darwin; в stdout ничего не печатаем).
    dry        — здесь НЕ про деньги (их нет): dry=True → НЕ копируем в deliver_dir/не открываем
                 (тихий предпросмотр), dry=False → доставляем оператору. Кадр пишется в out_dir всегда.
    require_clean — ЗАКОН ЧИСТОЙ БАЗЫ: True (по умолч.) → перед наложением макета база проходит гейт
                 clean_base_score (белые углы + OCR-слов мало); грязную (чужая инфографика/текст/
                 водяной знак/цветной фон) НЕ брендируем — отдаём ok=False и причину в why/clean.
                 False — осознанный байпас (арт-прогон/тест), двойную инфографику НЕ рисуем всё равно.
    Возврат: {ok, path, thumb, dry, cost_usd:0.0,
              content:{hero,specs,wordmark,accent,variant,accent_why}, clean, why}.
    """
    # ── ЦВЕТ-КАК-СМЫСЛ (арт-канон): cyan-бар — КОНСТАНТА бренда (никогда не меняется); вариант/класс
    # товара живёт ТОЛЬКО в карриере (чип короба/подчёрк-штамп плёнки), цвет которого render() выводит
    # САМ через grade_resolve(facts) — единый источник правды. Caller может явно дать brand.accent
    # (перекроет cyan-бар для особого кадра), но на цвет варианта это не влияет.
    sig = variant_signal(facts)
    eff_brand = dict(brand or {})
    eff_brand.setdefault("accent", BRAND["accent"])   # бар по умолчанию = cyan-константа (закон)
    step = resolve_accent(facts, default=BRAND["accent"])
    accent_why = ("фирменный cyan-бар, варианта нет (монохром/стандарт)" if not sig
                  else "%s → %s (%s)" % (sig.get("kind"), sig.get("label"), sig.get("key")))
    if (brand or {}).get("accent") is not None:
        accent_why = "явный brand.accent оператора (%s)" % (str(eff_brand["accent"]))
    rep = {"ok": False, "path": None, "thumb": None, "dry": bool(dry), "cost_usd": 0.0,
           "content": {"hero": _hero_line(facts), "specs": _specs(facts),
                       "wordmark": eff_brand.get("wordmark", BRAND["wordmark"]),
                       "accent": tuple(step),
                       "variant": (sig or {}).get("kind"),
                       "accent_why": accent_why},
           "clean": None, "why": ""}
    if not _HAVE_PIL:
        rep["why"] = "нет Pillow — инфографику не рисуем (честно; поставь PIL в venv фото-органа)"
        return rep
    if require_clean:
        cs = clean_base_score(base)
        rep["clean"] = cs
        if not cs["ok"]:
            rep["why"] = ("чистый-гейт базы НЕ пройден — не кладём фирменный макет на грязный кадр "
                          "(требуем товар на белом БЕЗ чужого текста/инфографики/водяных знаков): %s"
                          % cs["why"])
            return rep
    img = render(base, facts=facts, brand=eff_brand, zoom=zoom)
    if img is None:
        rep["why"] = "базовый кадр не открылся (битый/не изображение) — инфографику не куём"
        return rep

    d = Path(out_dir) if out_dir else (Path(__file__).resolve().parent / "state" / "forged")
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        rep["why"] = "не создать каталог вывода: %s" % e
        return rep
    fname = "infographic_%s_%d_%s.jpg" % (tag, int(time.time()), uuid.uuid4().hex[:8])
    path = d / fname
    try:
        img.save(path, "JPEG", quality=92)
    except Exception as e:
        rep["why"] = "не сохранить кадр: %s" % e
        return rep
    rep["ok"] = True
    rep["path"] = str(path)

    # Лёгкий thumbnail (~360px) — чтобы верифицировать макет БЕЗ чтения полного кадра (токен-эконом).
    try:
        th = img.copy()
        th.thumbnail((360, 450))
        tpath = d / ("thumb_" + fname)
        th.save(tpath, "JPEG", quality=72)
        rep["thumb"] = str(tpath)
    except Exception:
        pass

    # Доставка «для глаз» оператора — только вне dry (его преференция: видеть картинкой на компе).
    if not dry:
        dd = Path(deliver_dir) if deliver_dir else (Path.home() / "Desktop" / "ARBITER_фото")
        try:
            dd.mkdir(parents=True, exist_ok=True)
            dpath = dd / fname
            img.save(dpath, "JPEG", quality=92)
            rep["delivered"] = str(dpath)
            if open_it and sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", str(dpath)], check=False)
        except Exception as e:
            rep["deliver_why"] = "доставка не удалась: %s" % e
    return rep


# ── CLI: демо/боевой рендер (0₽, локально). Заголовки в stderr, отчёт-JSON в stdout. ──
def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="SOCC-инфографика поверх готового кадра (0₽, локально)")
    ap.add_argument("--base", help="путь к готовому фото товара (канон-белый)")
    ap.add_argument("--facts", help="JSON фактов товара")
    ap.add_argument("--out", help="каталог вывода (дефолт state/forged/)")
    ap.add_argument("--deliver-dir", help="доп. копия «для глаз» (дефолт ~/Desktop/ARBITER_фото)")
    ap.add_argument("--wordmark", help="слово-марка (перекрыть ATLAS EDGE)")
    ap.add_argument("--open", action="store_true", help="открыть в Просмотре (darwin)")
    ap.add_argument("--live", action="store_true", help="доставить оператору (иначе тихий предпросмотр)")
    ap.add_argument("--no-zoom", action="store_true", help="не кропать по предмету (оставить поля базы)")
    ap.add_argument("--no-clean-gate", action="store_true",
                    help="ОСОЗНАННЫЙ байпас чистого-гейта базы (арт-прогон на заведомо чистом кадре)")
    ap.add_argument("--demo", action="store_true", help="демо на образце короба")
    args = ap.parse_args(argv)

    facts = {}
    if args.facts:
        try:
            facts = json.loads(args.facts)
        except Exception as e:
            print("плохой --facts JSON: %s" % e, file=sys.stderr)
            return 2
    base = args.base
    if args.demo:
        base = base or str(Path.home() / "Desktop" / "ARBITER_фото" / "коробка_образец.jpg")
        facts = facts or {"вид": "Гофрокороб 4-х клапанный", "размер": "600×400×400 мм",
                          "материал": "5-слойный гофрокартон Т-24", "комплектация": "10 шт"}
    if not base:
        print("нужен --base путь_к_фото (или --demo)", file=sys.stderr)
        return 2
    brand = {"wordmark": args.wordmark} if args.wordmark else None
    print("PIL=%s base=%s фактов=%d live=%s" % (_HAVE_PIL, base, len(facts), args.live), file=sys.stderr)
    rep = compose_infographic(base, facts=facts, brand=brand, out_dir=args.out,
                              deliver_dir=args.deliver_dir, open_it=args.open,
                              tag="demo" if args.demo else "item", dry=not args.live,
                              zoom=not args.no_zoom, require_clean=not args.no_clean_gate)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(_main())

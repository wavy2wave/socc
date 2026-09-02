#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ФОТО-ИСКАТЕЛЬ (PHOTO HUNTER V1) — орган поиска чистых фото товара под карточку Маркета.

ЗАЧЕМ (слова оператора, дословный смысл): «найти фото под наши критерии, пусть проводит сам
двойные-тройные человеческие проверки. А что же на картинке? Он должен уметь отвечать без
промахов. Нам просто не нужно тратить токены постоянно — мы просто ЗНАЕМ КАК НАЙТИ:
проверяем, проверяем, проверяем — вердикт, ссылка, профит.»

ЗАЧЕМ ЭТО ДЕНЬГИ. Индекс контента карточки на 20 пунктов определяется числом фото
(натуральный эксперимент 2026-08-11: 1 фото → 69, 3 → 83, 6 → 87 при побитово одинаковых
параметрах). А единственные доступные нам кадры — донорские, с его водяным знаком: ставить
чужой знак нельзя. Нет чистых фото → нет индекса → нет выдачи → нет продаж.

ДОКТРИНА (главное решение органа): ИСКАТЬ НЕ КАРТИНКУ, А ТОВАР У ПЕРВОИСТОЧНИКА.
Подсказка оператора: любой товар с маркетплейса имеет производителя и продавцов; у производителя
обычно много студийных кадров без знака. Открытый поиск картинок — ПОСЛЕДНИЙ рубеж, не первый.
Лестница источников — в photo_sources_v1.json (реестр растёт: нашли раз → знаем навсегда).

ТРИ СТУПЕНИ ШЛЮЗА, дешёвое раньше дорогого (экономия токенов — это закон, а не пожелание):
  Ступень 1 · ЖЕЛЕЗО (0 ₽, без модели): скачалось? это картинка? ≥300×300? не дубль (pHash)?
             формат/вес/пропорции в норме? Отсеивает почти весь мусор бесплатно.
  Ступень 2 · БУКВЫ (0 ₽, локально): OCR по кадру. Нашли чужой домен/бренд/«оптом» → водяной
             знак → отбой. Работает без всякой модели, ловит главный риск.
  Ступень 3 · ЗРЕНИЕ (дорого, поэтому ТОЛЬКО на выживших): «что на картинке?» Проверяем не
             вообще, а СВЕРКОЙ С ФАКТАМИ, которые мы уже знаем из выгрузки: ширина 1.2 м,
             пузырёк 30 мм, плотность 130 г/м², рулон. Зрение говорит «мелкий пузырёк», а у нас
             30 мм → отбой. Это и есть «двойная-тройная человеческая проверка»: независимые
             вопросы + кворум + сверка с известной физикой товара.

ЧЕСТНОСТЬ (закон L3 линии): не смогли проверить → вердикт 'unknown', а НЕ 'годится'.
Неизвестность чинится повтором, ложное «годится» ставит чужой знак на живую карточку.
Кэш вердиктов на диске: одна ссылка проверяется ОДИН раз за всю жизнь органа.

ГРАНИЦА. Орган НЕ скачивает фото на наш сервер и НЕ заливает их в Маркет — он отдаёт
ПРОВЕРЕННЫЕ ССЫЛКИ и вердикт. Заливкой занимается ymarket_write. Права на снимки — вопрос
оператора: орган помечает источник и лицензионный риск, но решает человек.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "photo_sources_v1.json"
CACHE = HERE / "state" / "photo_verdicts.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")

# ── Мягкие зависимости: органу нельзя падать из-за отсутствия библиотеки ──────────
try:
    from PIL import Image
    HAVE_PIL = True
except Exception:
    Image = None
    HAVE_PIL = False


def have_tesseract():
    """Есть ли локальный OCR. Без него ступень 2 честно помечается как непройденная."""
    try:
        subprocess.run(["tesseract", "--version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def ocr_langs():
    """Какие языки реально доступны tesseract. Русского может не быть (языковой пакет отдельный).

    Просить '-l rus+eng' при отсутствии rus — значит уронить OCR на пустом месте.
    Берём пересечение желаемого и доступного, иначе молчим и пусть tesseract берёт дефолт.
    """
    try:
        r = subprocess.run(["tesseract", "--list-langs"], capture_output=True, timeout=8)
        have = {l.strip() for l in (r.stdout or b"").decode("utf-8", "ignore").splitlines()
                if l.strip() and "List of" not in l}
    except Exception:
        return None
    want = [l for l in ("rus", "eng") if l in have]
    return "+".join(want) if want else None


def _has_ollama_vision():
    """Есть ли локальная модель зрения в ollama (moondream/llava/…). Кэш в атрибуте функции."""
    if hasattr(_has_ollama_vision, "_c"):
        return _has_ollama_vision._c
    model = None
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, timeout=6)
        out = (r.stdout or b"").decode("utf-8", "ignore").lower()
        for m in ("moondream", "llava", "llama3.2-vision", "qwen2-vl", "bakllava", "minicpm-v"):
            if m in out:
                model = m
                break
    except Exception:
        model = None
    _has_ollama_vision._c = model
    return model


def auto_vision_cmd():
    """Команда зрения: явный PHOTO_VISION_CMD, иначе — самопривязка к локальному ollama.

    Смысл: если рядом лежит photo_vision_ollama.py, интерпретатор с PIL и в ollama есть модель
    зрения — орган включает ступень 3 САМ, без ручной настройки env. Это и есть «мы просто ЗНАЕМ
    КАК» — знание вшито, а не требует шаманства при каждом запуске.
    """
    env_cmd = os.getenv("PHOTO_VISION_CMD")
    if env_cmd:
        return env_cmd
    bridge = HERE / "photo_vision_ollama.py"
    if bridge.exists() and _has_ollama_vision():
        return "%s %s" % (sys.executable, bridge)
    return None


def discovery_providers():
    """Честный срез РАБОЧИХ добытчиков ссылок: что реально ходит в сеть в discover(), а не просто
    заявлено в реестре. photo_sources_v1.json → discovery_sources описывает ЛЕСТНИЦУ желаемого;
    здесь — код, который правда добывает. Мандат «искать не только на ВБ, а везде, даже на
    иноязычных сайтах» закрывает открытый поиск (open_images): он индексирует и зарубежные сайты.
    Поле сообщает лишь, что под источник ЕСТЬ КОД — сетевая достижимость с RU-egress проверяется
    в момент запроса и возвращается в результатах find().
    """
    src = load_sources()
    decl = (src.get("discovery_sources") or {})
    wired = {"wildberries": HAVE_WB, "open_images": True}
    out = {}
    for name, code in wired.items():
        d = decl.get(name) or {}
        out[name] = {"code": bool(code),
                     "rank": d.get("rank", 3 if name == "wildberries" else 5),
                     "kind": "open_search" if name == "open_images" else "other_shop"}
    return out


def capabilities():
    """Что орган РЕАЛЬНО умеет в этом окружении. Честный паспорт возможностей."""
    return {
        "download": True,                       # stdlib
        "image_probe": HAVE_PIL,                # размеры/формат/pHash
        "ocr": have_tesseract(),                # ступень 2
        "vision": bool(auto_vision_cmd()),      # ступень 3, авто-привязка к ollama или env
        "discover_wildberries": HAVE_WB,        # добытчик: запрос → ссылки (rank-3 источник)
        "discover_sources": discovery_providers(),  # какие источники «искать везде» подключены живьём
        "vision_hint": ("зрение подключается переменной PHOTO_VISION_CMD (команда: путь к файлу + "
                        "вопрос → ответ в stdout), либо привязывается САМО к локальному ollama, "
                        "если рядом лежит photo_vision_ollama.py и установлена модель зрения "
                        "(moondream/llava)."),
    }


# ── Реестр знания ────────────────────────────────────────────────────────────────
def load_sources():
    try:
        return json.loads(SOURCES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_cache():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(data):
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    except Exception:
        return False


# ── Скачивание ───────────────────────────────────────────────────────────────────
def fetch_bytes(url, timeout=25, retries=1, max_bytes=12_000_000):
    """Байты по ссылке или None. Сеть моргнула → повтор. Гигант не тянем."""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(max_bytes), (r.headers.get("Content-Type") or "").lower()
        except Exception:
            if attempt >= retries:
                return None, None
            time.sleep(1.2 * (attempt + 1))
    return None, None


# ── Ступень 1: ЖЕЛЕЗО ────────────────────────────────────────────────────────────
def phash(raw, size=8):
    """Перцептивный хеш (dHash) — сравнить КАДРЫ, а не байты. None если нет PIL."""
    if not HAVE_PIL or not raw:
        return None
    try:
        im = Image.open(io.BytesIO(raw)).convert("L").resize((size + 1, size), Image.LANCZOS)
        px = list(im.getdata())
        bits = []
        for row in range(size):
            for col in range(size):
                left = px[row * (size + 1) + col]
                right = px[row * (size + 1) + col + 1]
                bits.append("1" if left > right else "0")
        return "%016x" % int("".join(bits), 2)
    except Exception:
        return None


def hamming(a, b):
    """Расстояние между хешами. None если хоть один отсутствует."""
    if not a or not b or len(a) != len(b):
        return None
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def stage1_iron(raw, ctype, crit):
    """Железная проверка: это годная картинка? Возвращает (ok, детали)."""
    out = {"stage": "iron", "ok": False, "why": None, "width": None, "height": None,
           "bytes": len(raw) if raw else 0, "phash": None, "format": None}
    if not raw:
        out["why"] = "не скачалось"
        return False, out
    if len(raw) < crit.get("min_bytes", 8000):
        out["why"] = "файл слишком мал (%d байт) — вероятно превью или заглушка" % len(raw)
        return False, out
    if ctype and "image" not in ctype:
        out["why"] = "не изображение по Content-Type: %s" % ctype
        return False, out
    if not HAVE_PIL:
        out["why"] = "PIL недоступен — размеры не проверены"
        out["ok"] = None                      # честное «не знаю», не «годится»
        return None, out
    try:
        im = Image.open(io.BytesIO(raw))
        w, h = im.size
        out["width"], out["height"], out["format"] = w, h, (im.format or "").lower()
    except Exception as e:
        out["why"] = "не разбирается как изображение: %s" % type(e).__name__
        return False, out
    out["phash"] = phash(raw)
    if out["format"] not in crit.get("formats", []):
        out["why"] = "формат %s не в списке допустимых" % out["format"]
        return False, out
    side = min(w, h)
    if side < crit.get("min_side_px", 300):
        out["why"] = "мелкая: %dx%d, минимум стороны %d" % (w, h, crit.get("min_side_px", 300))
        return False, out
    ar = max(w, h) / max(1, min(w, h))
    if ar > crit.get("max_aspect_ratio", 2.0):
        out["why"] = "пропорции %.2f — вероятно баннер, а не товар" % ar
        return False, out
    small = side < crit.get("target_min_side_px", 1000)
    out["ok"] = True
    out["why"] = "%dx%d %s%s" % (w, h, out["format"], ", ниже целевой 1000px" if small else "")
    out["below_target"] = small
    return True, out


# ── Ступень 2: БУКВЫ (OCR против водяных знаков + ЗАКОН КОМПРОМЕТАЦИИ) ─────────────
def stage2_letters(raw, markers):
    """OCR по кадру. Нашли чужой домен/бренд/оптовый лексикон → водяной знак.

    ЗАКОН КОМПРОМЕТАЦИИ (слово оператора): кадр, на котором ВИДЕН след маркетплейса или
    продавца (домен wildberries/ozon/avito, ник магазина, «продавец: …»), использовать НЕЛЬЗЯ —
    он нас разоблачает. Такой кадр не просто «грязный», он compromise=True: рубим жёстко, отдельным
    классом от оптового знака («опт/прайс/скидка»). Читаем ТОЛЬКО пиксели — про хост знает провенанс.
    """
    out = {"stage": "letters", "ok": None, "why": None, "text": None, "hits": [],
           "domain_hits": [], "seller_hits": [], "phrase_hits": [], "compromise": False}
    if not have_tesseract():
        out["why"] = "tesseract недоступен — водяной знак по буквам НЕ проверен"
        return None, out
    # OCR ЧЕРЕЗ STDIN, не через путь к файлу. На этой машине (leptonica 1.87.0) режим
    # файла молча ломается — Leptonica «image file not found» на существующий файл, tesseract
    # отдаёт пусто → гейт СЛЕП. Поток stdin (`tesseract - stdout`) читается железно. Заодно
    # ушёл темп-файл. Нормализуем в PNG через PIL (webp/битые → предсказуемый вход).
    try:
        if HAVE_PIL:
            buf = io.BytesIO()
            Image.open(io.BytesIO(raw)).convert("RGB").save(buf, format="PNG")
            img_bytes = buf.getvalue()
        else:
            img_bytes = raw
        r = subprocess.run(["tesseract", "-", "stdout"] +
                           (["-l", ocr_langs()] if ocr_langs() else []),
                           input=img_bytes, capture_output=True, timeout=45)
        text = (r.stdout or b"").decode("utf-8", "ignore")
    except Exception as e:
        out["why"] = "OCR не выполнился: %s" % type(e).__name__
        return None, out
    low = re.sub(r"\s+", " ", text).strip().lower()
    out["text"] = low[:300]
    domain_hits = [d for d in markers.get("domains", []) if d in low]
    seller_hits = [s for s in markers.get("seller_marks", []) if s in low]
    phrase_hits = [p for p in markers.get("phrases", [])
                   if re.search(r"\b%s\b" % re.escape(p), low)]
    out["domain_hits"], out["seller_hits"], out["phrase_hits"] = domain_hits, seller_hits, phrase_hits
    out["hits"] = domain_hits + seller_hits + phrase_hits  # объединение — обратная совместимость
    out["compromise"] = bool(domain_hits or seller_hits)   # след маркетплейса/продавца = разоблачение
    if out["compromise"]:
        out["ok"] = False
        out["why"] = ("КОМПРОМЕТАЦИЯ: на кадре след маркетплейса/продавца: %s — использовать нельзя"
                      % ", ".join((domain_hits + seller_hits)[:4]))
        return False, out
    if phrase_hits:
        out["ok"] = False
        out["why"] = "оптовый водяной знак на кадре: %s" % ", ".join(phrase_hits[:4])
        return False, out
    out["ok"] = True
    out["why"] = "чужого текста не найдено (распознано %d знаков)" % len(low)
    return True, out


# ── Ступень 3: ЗРЕНИЕ (подключаемое, только на выживших) ─────────────────────────
def ask_vision(path, question, timeout=180):
    """Спросить у зрения. Провайдер — auto_vision_cmd (env или самопривязка к ollama). None → нет."""
    cmd = auto_vision_cmd()
    if not cmd:
        return None
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout,
                           env=dict(os.environ, PHOTO_PATH=str(path), PHOTO_QUESTION=question))
        ans = (r.stdout or b"").decode("utf-8", "ignore").strip()
        return ans or None
    except Exception:
        return None


def vision_questions(facts):
    """Независимые вопросы к кадру, СВЕРЯЕМЫЕ С ИЗВЕСТНОЙ ФИЗИКОЙ товара.

    Вопросы на АНГЛИЙСКОМ намеренно: локальная модель зрения (moondream) обучена на английском
    и на русские вопросы всё равно отвечает по-английски либо галлюцинирует кириллицу
    (проверено живьём 2026-08-11). Спрашиваем на её языке — получаем осмысленный ответ.

    Что модель РЕАЛЬНО умеет надёжно (проверено): опознать предмет и грубый вид (крупный/мелкий
    пузырёк). Что она НЕ умеет: читать бледный водяной знак — на «есть ли текст?» отвечает пусто
    или мусором. Поэтому зрение здесь отвечает на «ЧТО на картинке» (сверка с фактами), а чистота
    от чужого знака решается ПРОИСХОЖДЕНИЕМ (реестр источников), НЕ null-ответом зрения.
    """
    subj_en = facts.get("subject_en")
    if subj_en:
        is_ours_q = "Is this %s? Answer strictly YES or NO." % subj_en
    else:
        is_ours_q = "Is this a roll of air bubble wrap (packaging bubble film)? Answer strictly YES or NO."
    qs = [
        ("subject",
         "What product is shown in this image? Answer in one short sentence, only what is visible."),
        ("is_ours", is_ours_q),
        ("background",
         "Is the background a plain white studio background, or a scene/collage/multiple items? "
         "Answer in a few words."),
        ("overlay_text",
         "Is there any text, website address, phone number or price printed over the image? "
         "Answer strictly YES or NO, and if YES what it says."),
    ]
    if facts.get("bubble_mm"):
        qs.append(("bubble",
                   "Are the bubbles on the film small (about 10 mm) or large (about 30 mm)? "
                   "Answer 'small' or 'large'."))
    return qs


def stage3_vision(raw, facts):
    """Зрение по кадру. Возвращает СИГНАЛЫ, а не финальный вердикт чистоты.

    Различаем три исхода:
      • ok=False — зрение ПОЛОЖИТЕЛЬНО увидело плохое (не наш товар / чужой текст / не тот пузырёк).
      • ok=True  — зрение ПОЛОЖИТЕЛЬНО подтвердило наш товар. Это ещё НЕ «годится»: чистоту от
                   знака даёт происхождение, а не зрение. check_photo решает финал.
      • ok=None  — зрение молчит/не подключено: ничего не доказано (не путать с «чисто»).
    """
    out = {"stage": "vision", "ok": None, "why": None, "answers": {},
           "product_ok": None, "saw_overlay": None}
    if not auto_vision_cmd():
        out["why"] = "зрение не подключено (нет PHOTO_VISION_CMD и локального ollama) — кадр НЕ проверен"
        return None, out
    tmp = Path("/tmp/photo_hunter_vision.png")
    try:
        if HAVE_PIL:
            Image.open(io.BytesIO(raw)).convert("RGB").save(tmp)
        else:
            tmp.write_bytes(raw)
        for key, q in vision_questions(facts):
            out["answers"][key] = ask_vision(tmp, q)
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass

    a = {k: (v or "").lower() for k, v in out["answers"].items()}
    if not any(a.values()):
        out["why"] = "зрение не ответило ни на один вопрос"
        return None, out

    def _yes(s):
        return s.strip().startswith("yes") or "да" == s.strip()[:2]

    def _no(s):
        return s.strip().startswith("no") or "нет" == s.strip()[:3]

    # Опознание товара — по КЛЮЧЕВЫМ СЛОВАМ в свободном ответе, а не по YES/NO.
    # Проверено живьём: moondream устойчиво пишет «bubble wrap» в описании, но на прямой
    # вопрос ДА/НЕТ часто отвечает пусто. Ключевые слова — надёжный сигнал, YES/NO — нет.
    kw = facts.get("subject_keywords") or ["bubble wrap", "bubble film", "bubble", "пузырч", "плёнк", "плен"]
    free = " ".join(a.get(k, "") for k in ("subject", "is_ours", "background"))
    is_ours = a.get("is_ours", "")
    if any(w in free for w in kw):
        out["product_ok"] = True
    elif _no(is_ours):
        out["product_ok"] = False
    else:
        out["product_ok"] = None

    bad = []
    if out["product_ok"] is False:
        bad.append("зрение говорит: это не пузырчатая плёнка")
    # чужой текст: ТОЛЬКО положительное «yes» — это сигнал ПРОТИВ. Пустой/‘no’ ничего не доказывает
    # (модель не умеет читать бледный знак), поэтому в пользу чистоты НЕ засчитывается.
    overlay = a.get("overlay_text", "")
    out["saw_overlay"] = True if _yes(overlay) else (False if _no(overlay) else None)
    if out["saw_overlay"] is True:
        bad.append("зрение видит наложенный текст/знак: %s" % overlay[:60])
    # сверка с известной физикой пузырька
    want = facts.get("bubble_mm")
    seen = a.get("bubble", "")
    if want and seen:
        if float(want) >= 20 and "small" in seen:
            bad.append("пузырёк мелкий, а у товара %s мм" % want)
        if float(want) <= 15 and "large" in seen:
            bad.append("пузырёк крупный, а у товара %s мм" % want)

    if bad:
        out["ok"] = False
        out["why"] = "; ".join(bad)
        return False, out
    if out["product_ok"] is True:
        out["ok"] = True
        out["why"] = "зрение подтвердило товар: %s" % (out["answers"].get("subject") or "")[:110]
        return True, out
    out["why"] = "зрение ответило, но товар не подтверждён положительно"
    return None, out


# ── Главный шлюз ─────────────────────────────────────────────────────────────────
def host_is_clean(host, src):
    """Известен ли хост как ЧИСТЫЙ источник (реестр). Только это даёт право на 'good'.

    Проверено живьём 2026-08-11: ни OCR, ни локальное зрение НЕ читают бледный тайловый знак
    («ТУТ.РУ» → OCR 0 знаков, moondream пусто). Значит «знак не найден» ≠ «знака нет». Право на
    вердикт good даёт только ПРОИСХОЖДЕНИЕ — хост, помеченный чистым в реестре (производитель/
    магазин без знака). Всё прочее максимум 'unknown' (человеку на один взгляд).
    """
    clean = set()
    cats = (src.get("categories") or {})
    for c in cats.values():
        if isinstance(c, dict):
            clean.update(c.get("known_clean_shops") or [])
    for b in (src.get("brands") or {}).values():
        if isinstance(b, dict) and b.get("manufacturer_site"):
            clean.add(re.sub(r"^https?://([^/]+).*", r"\1", b["manufacturer_site"]))
    # ЗАКОН 1 (граница хоста, НЕ подстрока): «example.ru» в реестре не должен делать чистым
    # «example.ru.evil.com» или «fakeexample.ru». Совпадение — только точный хост или его поддомен.
    h = (host or "").split("@")[-1].split(":")[0].strip().lower().rstrip(".")

    def _host_match(c):
        c = (c or "").split("@")[-1].split(":")[0].strip().lower().rstrip(".")
        return bool(c) and (h == c or h.endswith("." + c))

    return any(_host_match(c) for c in clean)


# ── Чистота КАДРА: пиксельный скоринг «студийный ли снимок» (0₽, без egress) ──────
def _corner_white_frac(raw, corner=0.14, thr=236):
    """Доля почти-белых пикселей в 4 углах кадра. Товар-на-белом (студия) → близко к 1.0.

    Не «читает» знак, а МЕРЯЕТ ФОН: коллаж/сцена/инфографика с цветной подложкой заваливает
    метрику. Дополняет OCR (буквы) независимым взглядом на фон. Предметно-независимо.
    """
    if not HAVE_PIL or not raw:
        return None
    try:
        im = Image.open(io.BytesIO(raw)).convert("L")
        w, h = im.size
        cw, ch = max(1, int(w * corner)), max(1, int(h * corner))
        px = im.load()
        white = tot = 0
        for ox, oy in ((0, 0), (w - cw, 0), (0, h - ch), (w - cw, h - ch)):
            for x in range(ox, ox + cw, 3):
                for y in range(oy, oy + ch, 3):
                    tot += 1
                    if px[x, y] >= thr:
                        white += 1
        return round(white / max(1, tot), 3)
    except Exception:
        return None


def _text_density(ocr_text):
    """Число словоподобных токенов на кадре по OCR.

    Главная доказанная дыра: конкурентная инфографика ВПАЯНА в фото («60 СМ», «100 М», лозунги).
    Этих слов НЕТ в watermark_markers (не домен, не «опт») → ступень БУКВЫ их пропускает.
    Плотность ловит их КАК КЛАСС: много слов на «фото товара» = инфографика, а не студийный кадр.
    """
    if not ocr_text:
        return 0
    return len(re.findall(r"[0-9a-zA-Zа-яёА-ЯЁ]{2,}", ocr_text))


def clean_signals(raw, ocr_text, vision_out, crit):
    """Свести пиксельные признаки «чистого студийного кадра» в один честный флаг.

    НЕ создаёт вердикт 'good' (закон органа цел: чистоту от бледного знака машина не доказывает,
    право на 'good' даёт только происхождение). Задача — РАНЖИРОВАТЬ неясные: пометить кадры,
    которые ВЫГЛЯДЯТ чистыми (белый фон + мало текста + зрение не опровергло товар), чтобы
    оператор смотрел сперва на них и получал чистый пиксель под инфографику. Работает для ЛЮБОГО
    товара — все метрики предметно-независимы.
    """
    bg = _corner_white_frac(raw)
    words = _text_density(ocr_text)
    max_words = int(crit.get("clean_max_ocr_words", 6))
    min_bg = float(crit.get("clean_min_bg_white", 0.80))
    text_heavy = words > max_words
    bg_ok = (bg is not None and bg >= min_bg)
    prod_ok = bool(vision_out and vision_out.get("product_ok") is True)
    prod_denied = bool(vision_out and vision_out.get("product_ok") is False)
    candidate = bool(bg_ok and not text_heavy and not prod_denied)
    return {"bg_white_frac": bg, "ocr_words": words, "text_heavy": text_heavy,
            "bg_ok": bg_ok, "product_confirmed": prod_ok, "clean_candidate": candidate}


def check_photo(url, facts=None, donor_phashes=(), seen_phashes=(), use_cache=True, trusted=None):
    """Провести одну ссылку через три ступени. Вердикт: good | bad | unknown.

    facts — что мы ЗНАЕМ о товаре из выгрузки (ширина, пузырёк, плотность, вид).
    donor_phashes — хеши донорских кадров: совпадение значит «тот же ракурс того же товара»
                    (плюс к доверию), но НЕ отменяет проверку на водяной знак.
    seen_phashes — уже принятые кадры: близкий хеш = дубль, второй раз не берём.
    trusted — источник заведомо чистый (провенанс). None → определяем по реестру host_is_clean.
              БЕЗ доверенного источника вердикт НИКОГДА не 'good' — максимум 'unknown', потому что
              чистоту от чужого знака машина доказать не может (см. host_is_clean).
    """
    facts = facts or {}
    src = load_sources()
    crit = src.get("criteria", {})
    markers = src.get("watermark_markers", {})
    blocked = src.get("blocked_hosts", {})

    cache = load_cache() if use_cache else {}

    res = {"url": url, "verdict": "unknown", "why": None, "stages": [], "from_cache": False,
           "host": re.sub(r"^https?://([^/]+).*", r"\1", url)}

    # ЧЁРНЫЙ СПИСОК — ДО кэша: блок хоста ВСЕГДА главнее любого сохранённого вердикта. Иначе кадр,
    # закэшированный ДО добавления его хоста в blocked_hosts, молча обходил бы блок навсегда.
    for bad_host, why in blocked.items():
        if bad_host in res["host"]:
            res.update(verdict="bad", why="хост в чёрном списке (%s)" % why)
            return res

    # Ключ кэша ВЕРСИОНИРОВАН критериями/маркерами/блок-листом: ужесточили правила → старые
    # записи автоматически промахиваются и перепроверяются, а не тухнут молча под прежним вердиктом.
    try:
        ver = hashlib.sha1(json.dumps({"c": crit, "m": markers, "b": blocked},
                                      sort_keys=True, ensure_ascii=False).encode("utf-8")
                           ).hexdigest()[:8]
    except Exception:
        ver = "0"
    key = hashlib.sha1(("%s|%s" % (url, ver)).encode("utf-8")).hexdigest()[:16]
    if use_cache and key in cache:
        c = dict(cache[key])
        c["from_cache"] = True
        return c

    raw, ctype = fetch_bytes(url)
    ok1, d1 = stage1_iron(raw, ctype, crit)
    res["stages"].append(d1)
    if ok1 is False:
        res.update(verdict="bad", why=d1["why"])
        if use_cache:
            cache[key] = res
            save_cache(cache)
        return res

    ph = d1.get("phash")
    res["phash"] = ph
    for s in seen_phashes:
        h = hamming(ph, s)
        if h is not None and h <= 4:
            res.update(verdict="bad", why="дубль уже принятого кадра (hamming=%d)" % h)
            if use_cache:
                cache[key] = res
                save_cache(cache)
            return res
    res["same_as_donor"] = any((hamming(ph, s) or 99) <= 6 for s in donor_phashes)

    ok2, d2 = stage2_letters(raw, markers)
    res["stages"].append(d2)
    res["compromise"] = bool(d2.get("compromise"))  # виден след маркетплейса/продавца на кадре
    if ok2 is False:
        res.update(verdict="bad", why=d2["why"])
        if use_cache:
            cache[key] = res
            save_cache(cache)
        return res

    ok3, d3 = stage3_vision(raw, facts)
    res["stages"].append(d3)

    # Пиксельная чистота кадра: белизна фона + плотность текста + опознание зрением. НЕ меняет
    # вердикт (право на 'good' — за происхождением), но ранжирует неясные под «один взгляд».
    res["clean"] = clean_signals(raw, d2.get("text"), d3, crit)

    # Доверие к источнику: явный аргумент → иначе реестр чистых хостов.
    is_trusted = trusted if trusted is not None else host_is_clean(res["host"], src)
    res["trusted_source"] = bool(is_trusted)

    if ok3 is False:
        # зрение положительно увидело плохое (не тот товар / наложенный текст / не тот пузырёк)
        res.update(verdict="bad", why=d3["why"])
    elif is_trusted and ok3 is True and ok2 is True:
        # ЕДИНСТВЕННЫЙ путь к 'good': чистый источник (провенанс) + зрение подтвердило товар +
        # буквы ПРОВЕРЕНЫ (закон компрометации отработал). «Знак не найден» сам по себе НЕ
        # основание — машина не читает бледный знак; но след МП/продавца буквами исключён.
        res.update(verdict="good",
                   why="чистый источник + зрение подтвердило: %s" % d3["why"])
    elif is_trusted and ok3 is True and ok2 is None:
        # чистый источник и товар опознан, НО OCR недоступен → ЗАКОН КОМПРОМЕТАЦИИ не отработал:
        # след маркетплейса/продавца на пикселях машиной НЕ исключён → не 'good', человеку на взгляд.
        res.update(verdict="unknown",
                   why="источник чистый и товар опознан, но OCR недоступен — "
                       "компрометирующий текст на пикселях не исключён; нужен один взгляд человека")
    elif is_trusted and ok3 is None and ok1 is True:
        # чистый источник, но зрение не подключено/молчит: товар не подтверждён → человеку на взгляд
        res.update(verdict="unknown",
                   why="источник чистый, но зрение не подтвердило товар — нужен один взгляд человека")
    else:
        # источник НЕ доказан чистым → водяной знак не исключён машиной → никогда не 'good'
        why = ("источник не в реестре чистых — чужой водяной знак машина исключить не может; "
               "нужен чистый первоисточник или взгляд человека")
        if ok3 is True:
            why = "товар зрение подтвердило, но источник не доказан чистым: " + why
        if ok2 is None:
            # OCR не отработал → компрометирующий текст на пикселях машиной НЕ исключён
            why += "; буквы не проверены (OCR недоступен)"
        res.update(verdict="unknown", why=why)

    if use_cache:
        cache[key] = res
        save_cache(cache)
    return res


def hunt(urls, facts=None, need=5, donor_urls=()):
    """Провести пачку ссылок и набрать need годных кадров. Возвращает разбор.

    Порядок важен: ссылки подаются УЖЕ по лестнице источников (производитель первым).
    """
    donor_ph = []
    for u in donor_urls:
        raw, _ = fetch_bytes(u)
        p = phash(raw)
        if p:
            donor_ph.append(p)

    good, bad, unknown, seen = [], [], [], []
    for u in urls:
        if len(good) >= need:
            break
        r = check_photo(u, facts=facts, donor_phashes=donor_ph, seen_phashes=seen)
        if r["verdict"] == "good":
            good.append(r)
            if r.get("phash"):
                seen.append(r["phash"])
        elif r["verdict"] == "bad":
            bad.append(r)
        else:
            unknown.append(r)
    return {"good": good, "bad": bad, "unknown": unknown,
            "need": need, "got": len(good), "enough": len(good) >= need,
            "capabilities": capabilities()}


# ── ДОБЫТЧИК (DISCOVERY): запрос → прямые ссылки картинок ─────────────────────────
# Верхняя половина органа. hunt()/check_photo() ПРОВЕРЯЮТ готовые ссылки — discover() их
# ДОБЫВАЕТ токен-free (чистый HTTP к публичному поиску маркетплейса), замыкая обещание
# оператору: «сказал товар → получил прямую PNG/WEBP-ссылку под API Маркета» — и в разы
# быстрее генерации (миллисекунды против кузницы). Первый источник лестницы, доказанный
# сетево достижимым с RU-egress этой машины (2026-08-26): Wildberries — реальные карточки
# товара, студийные .webp на basket-CDN, 0₽. Он rank-3 «сторонний магазин»: кадры не
# донорские (у донора знак), но и не первоисточник — ПРАВО на них решает оператор, поэтому
# такие ссылки честно выходят вердиктом 'unknown' (хост не в реестре чистых), а НЕ 'good'.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
try:
    import wb_scout_v1 as _wb
    HAVE_WB = True
except Exception:
    _wb = None
    HAVE_WB = False

WB_BASKET_CACHE = HERE / "state" / "wb_basket_map.json"
# Затравка vol→basket, измеренная живьём 2026-08-26. Реестр монотонен (↑vol ⇒ ↑basket) и
# ДОУЧИВАЕТСЯ: неизвестный vol угадывается от ближайшего снизу и добивается пробой соседей,
# найденное кэшируется. «Нашли раз → знаем навсегда» — тот же закон, что у реестра источников.
_WB_BASKET_SEED = {"1979": 13, "3294": 20, "4748": 26, "7972": 36, "10014": 41}


def _wb_basket_cache():
    try:
        d = json.loads(WB_BASKET_CACHE.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    for k, v in _WB_BASKET_SEED.items():
        d.setdefault(k, v)
    return d


def _wb_save_basket(cache):
    try:
        WB_BASKET_CACHE.parent.mkdir(parents=True, exist_ok=True)
        WB_BASKET_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _wb_probe_webp(url, timeout=10):
    """Тонкий зонд живости кадра: читаем 16 байт (сигнатуру), не файл. True = живой webp/jpeg/png."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Referer": "https://www.wildberries.ru/"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if getattr(r, "status", 200) != 200:
                return False
            b = r.read(16)
            return b[8:12] == b"WEBP" or b[:2] == b"\xff\xd8" or b[:4] == b"\x89PNG"
    except Exception:
        return False


def _wb_resolve_basket(nm_id, probe=None, deadline=30.0):
    """vol → номер basket-хоста CDN (или None). Кэш → угадка от ближайшего снизу → пробой соседей.

    Вынесено из wb_image_urls, чтобы ОДНОЙ резолюцией пользовались и ссылки на кадры, и card.json
    (структурная карточка на том же CDN). basket дрейфует (WB добавляет хосты: vol 10014 живёт на
    basket-41). Известный vol берётся из кэша БЕЗ единого зонда; неизвестный добивается пробой
    соседей в [1,60] и фиксируется на диск. probe — инъекция зонда для оффлайн-тестов.

    deadline — жёсткий потолок резолва (сек). БЕЗ него неизвестный vol в худшем случае пробует
    60 соседей по `probe(timeout)` каждый (обычно 10с) → до 10 мин блокировки органа (висение
    «долго и мучительно» в живом цикле). С дедлайном резолв отдаёт None через deadline, а не
    жжёт десятки минут: карточка без фото честно уходит в no_pictures, цикл не стоит.
    """
    probe = probe or _wb_probe_webp
    nm = int(nm_id)
    vol, part = nm // 100000, nm // 1000
    cache = _wb_basket_cache()
    basket = cache.get(str(vol))
    if basket is not None:
        return basket
    known = sorted((int(v), b) for v, b in cache.items())
    guess = 1
    for v, b in known:
        if v <= vol:
            guess = b
        else:
            break
    tried, order = set(), []
    for d in range(0, 60):
        for cand in (guess + d, guess - d):
            if 1 <= cand <= 60 and cand not in tried:
                tried.add(cand)
                order.append(cand)
    tpl = "https://basket-%02d.wbbasket.ru/vol%d/part%d/%d/images/big/1.webp"
    t0 = time.monotonic()
    for b in order:
        if time.monotonic() - t0 > deadline:
            break
        if probe(tpl % (b, vol, part, nm)):
            cache[str(vol)] = b
            _wb_save_basket(cache)
            return b
    return None


def wb_image_urls(nm_id, pics=1, max_pics=6, probe=None):
    """Прямые ссылки на студийные .webp карточки WB по nm_id. [] если basket не нашёлся.

    Резолвим basket само-коррекцией (см. _wb_resolve_basket) и строим пути к кадрам. probe —
    инъекция зонда для оффлайн-тестов (умолч. — реальный _wb_probe_webp).
    """
    nm = int(nm_id)
    vol, part = nm // 100000, nm // 1000
    basket = _wb_resolve_basket(nm, probe=probe)
    if basket is None:
        return []
    n = max(1, min(int(pics or 1), int(max_pics)))
    return ["https://basket-%02d.wbbasket.ru/vol%d/part%d/%d/images/big/%d.webp"
            % (basket, vol, part, nm, i) for i in range(1, n + 1)]


def _wb_fetch_card(url, timeout=12):
    """Скачать card.json (structured JSON карточки). {} при любой осечке — орган не падает."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Referer": "https://www.wildberries.ru/"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read(2_000_000).decode("utf-8", "ignore"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def wb_card_info(nm_id, probe=None, fetch=None):
    """Структурная карточка WB (card.json) на том же basket-CDN — БЕЗ токена, 0₽.

    ЗАЧЕМ (лечит «размеры одни, фото иные»): текст названия в выдаче беден и врёт. card.json несёт
    imt_name (полное имя), vendor_code (артикул с зашитыми размерами: «ВПП-2-63/0.3X100М»),
    description и options/grouped_options (характеристики). ЖИВОЙ УРОК 2026-08-11: у ВПП размер
    рулона 0.3×100м лежал НЕ в options (там были габариты УПАКОВКИ 40×5×5), а в imt_name и
    vendor_code — поэтому сверка size идёт по СУММЕ текстовых полей, не по одним options.
    fetch/probe — инъекция сети для оффлайн-тестов. {} при недостижимости (орган не падает).
    """
    fetch = fetch or _wb_fetch_card
    nm = int(nm_id)
    vol, part = nm // 100000, nm // 1000
    basket = _wb_resolve_basket(nm, probe=probe)
    if basket is None:
        return {}
    d = fetch("https://basket-%02d.wbbasket.ru/vol%d/part%d/%d/info/ru/card.json"
              % (basket, vol, part, nm))
    if not isinstance(d, dict) or not d:
        return {}
    opts, seen = [], set()
    buckets = [d.get("options") or []]
    for g in (d.get("grouped_options") or []):
        if isinstance(g, dict):
            buckets.append(g.get("options") or [])
    for bucket in buckets:
        for o in bucket:
            if isinstance(o, dict):
                nmo, val = o.get("name"), o.get("value")
                if nmo and val and (nmo, val) not in seen:
                    seen.add((nmo, val))
                    opts.append((nmo, val))
    media = d.get("media") if isinstance(d.get("media"), dict) else {}
    selling = d.get("selling") if isinstance(d.get("selling"), dict) else {}
    return {"imt_name": d.get("imt_name") or "", "vendor_code": d.get("vendor_code") or "",
            "description": d.get("description") or "", "options": opts,
            "photo_count": media.get("photo_count"),
            "brand": selling.get("brand_name") or (d.get("selling") or {}).get("brand") or ""}


# ── СВЕРКА ПО ФАКТАМ: почему товар ПОДОШЁЛ (детерминированно, 0₽, объяснимо) ───────
# Лечит промах «размеры одни, а фото иные»: из запроса вынимаем ЧИСЛА-ГАБАРИТЫ (0.3, 100) и
# слова, затем ищем их в имени/артикуле/описании/характеристиках товара. Числа весят втрое:
# «плёнка» найдётся у сотни рулонов, а «0.3×100» — почти уникальный отпечаток. Никакой модели:
# правило одно и объяснимое, агент цикла дня реплеит ту же арифметику по match{}.
_SPEC_STOP = {"для", "под", "или", "the", "and", "шт", "штук"}
_SPEC_SEP = re.compile(r"[×хx*]")
_SPEC_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _norm_spec(s):
    """Нормализовать строку под сверку: нижний регистр, ё→е, NBSP→пробел, разделители ×хx*→x."""
    s = (s or "").lower().replace(" ", " ").replace("ё", "е")
    s = _SPEC_SEP.sub("x", s)
    return re.sub(r"\s+", " ", s).strip()


def _num(x):
    """Каноничная форма числа: '0,3'→'0.3', '100.0'→'100'. None если не число."""
    try:
        f = float(str(x).replace(",", "."))
    except Exception:
        return None
    return str(int(f)) if f == int(f) else ("%.3f" % f).rstrip("0").rstrip(".")


def query_specs(query):
    """Запрос → {nums, words, norm}: числа-габариты и значимые слова (стоп-слова отброшены)."""
    q = _norm_spec(query)
    nums = {n for n in (_num(m) for m in _SPEC_NUM.findall(q)) if n is not None}
    words = {w for w in re.findall(r"[a-zа-я]{3,}", q) if w not in _SPEC_STOP}
    return {"nums": nums, "words": words, "norm": q}


def match_facts(query, *texts):
    """Насколько товар (сумма texts: имя+артикул+описание+характеристики) отвечает запросу.

    Возвращает {score 0..1, nums_hit, nums_miss, words_hit, has_specs}. Если в запросе есть числа —
    вес 0.75 числа / 0.25 слова (габариты решают: «0.3×100» важнее слова «плёнка»). Нет чисел —
    чистая доля слов. Детерминированно и объяснимо: видно, какое ЧИСЛО не совпало (nums_miss).
    """
    spec = query_specs(query)
    hay = _norm_spec(" ".join(str(t) for t in texts if t))
    hay_nums = {n for n in (_num(m) for m in _SPEC_NUM.findall(hay)) if n is not None}
    nums_hit = sorted(n for n in spec["nums"] if n in hay_nums)
    nums_miss = sorted(n for n in spec["nums"] if n not in hay_nums)
    words_hit = sorted(w for w in spec["words"] if w in hay)
    word_score = (len(words_hit) / len(spec["words"])) if spec["words"] else (1.0 if spec["nums"] else 0.0)
    if spec["nums"]:
        num_score = len(nums_hit) / len(spec["nums"])
        score = 0.75 * num_score + 0.25 * word_score
    else:
        score = word_score
    return {"score": round(score, 3), "nums_hit": nums_hit, "nums_miss": nums_miss,
            "words_hit": words_hit, "has_specs": bool(spec["nums"])}


# ── ДОБЫТЧИК №2: ОТКРЫТЫЙ ПОИСК (весь веб, вкл. иноязычные сайты) ─────────────────
# Закрывает мандат оператора «искать не только на ВБ, а везде». DuckDuckGo: без ключа,
# глобальный индекс (сайты производителей, зарубежные магазины, дилеры). rank-5 «последний
# рубеж» по доктрине — самый широкий охват и самый грязный, поэтому ВСЁ уходит в тройную
# проверку hunt() и не может выйти выше 'unknown' (хост не в реестре чистых). Пиксельный
# clean_signals ранжирует именно этот поток: белый фон + мало текста = чистый пиксель наверх.
def _ddg_vqd(query, timeout=12):
    """Токен vqd для картиночного поиска DuckDuckGo. None → поиск недостижим/сменил формат."""
    try:
        url = "https://duckduckgo.com/?" + urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            html = r.read(300_000).decode("utf-8", "ignore")
        m = re.search(r'vqd=["\']?([\d-]+)', html)
        return m.group(1) if m else None
    except Exception:
        return None


def _open_image_urls(query, limit=12, timeout=15):
    """Запрос → прямые URL изображений со всего веба (вкл. иноязычные). [] если недостижимо.

    Достижимость с RU-egress — вопрос рантайма; при блокировке честно отдаёт [], а не падает.
    Возвращает провенанс: url кадра + страница-источник (для взгляда/реестра оператором).
    """
    vqd = _ddg_vqd(query, timeout=timeout)
    if not vqd:
        return []
    try:
        qs = urllib.parse.urlencode({"l": "wt-wt", "o": "json", "q": query, "vqd": vqd,
                                     "f": ",,,", "p": "1"})
        req = urllib.request.Request("https://duckduckgo.com/i.js?" + qs,
                                     headers={"User-Agent": UA, "Referer": "https://duckduckgo.com/",
                                              "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read(3_000_000).decode("utf-8", "ignore"))
    except Exception:
        return []
    out = []
    for it in (data.get("results") or [])[:limit]:
        img = it.get("image")
        if img and str(img).startswith("http"):
            out.append({"url": img, "title": (it.get("title") or "")[:120],
                        "source_page": it.get("url"),
                        "width": it.get("width"), "height": it.get("height")})
    return out


def _discover_wb(query, facts, limit_products, pics_per, city, deepen, min_score):
    """Wildberries-ветвь: выдача → сверка по фактам → (опц.) добор card.json → ссылки на кадры.

    ДВА ТАКТА (message-4 «самый точный источник для тебя»):
      такт-1 (бесплатно): ранжируем товары сверкой запроса с ИМЕНЕМ выдачи — самый на-запрос первым.
      такт-2 (deepen, дёшево): у верхних тянем card.json и ПЕРЕСЧИТЫВАЕМ сверку по артикулу+описанию+
              характеристикам (там живут габариты, которых нет в имени) + берём число кадров карточки.
    min_score отбрасывает мимо-запроса (когда в запросе есть числа-габариты); хотя бы один оставляем.
    """
    if not HAVE_WB:
        return []
    try:
        prods = _wb.scan_category(query=query, city=city, limit=limit_products) or []
    except Exception:
        prods = []
    scored = []
    for pos, p in enumerate(prods):
        nm = p.get("id") or p.get("nmId") or p.get("nm")
        if not nm:
            continue
        name = (p.get("name") or "")[:160]
        brand = p.get("brand") or ""
        scored.append({"nm": nm, "pos": pos, "name": name[:120], "full_name": name,
                       "brand": brand, "prod": p, "match": match_facts(query, name, brand)})
    scored.sort(key=lambda s: (-s["match"]["score"], s["pos"]))
    kept = [s for s in scored if s["match"]["score"] >= min_score or not s["match"]["has_specs"]]
    kept = kept or scored[:1]
    out = []
    for rank_i, s in enumerate(kept):
        nm, p, m, vendor_code = s["nm"], s["prod"], s["match"], None
        try:
            price = _wb._price_rub(p)
        except Exception:
            price = None
        n = pics_per or int(p.get("pics") or 1)
        if deepen and rank_i < 6:
            card = wb_card_info(nm)
            if card:
                vendor_code = card.get("vendor_code") or None
                m = match_facts(query, s["full_name"], s["brand"], card.get("imt_name"),
                                card.get("vendor_code"), card.get("description"),
                                " ".join("%s %s" % kv for kv in card.get("options", [])))
                if card.get("photo_count") and not pics_per:
                    n = int(card["photo_count"])
        for i, u in enumerate(wb_image_urls(nm, pics=n), 1):
            out.append({
                "url": u, "nm_id": nm, "name": s["name"], "price_rub": price,
                "marketplace": "wildberries", "source_kind": "other_shop", "rank": 3,
                "position": s["pos"], "pic_index": i,
                "confidence": m["score"], "match": m, "vendor_code": vendor_code,
                "product_url": "https://www.wildberries.ru/catalog/%s/detail.aspx" % nm,
                "license": "маркетплейс-кадр: право на использование — решение оператора",
            })
    return out


def discover(query, facts=None, limit_products=12, pics_per=1, city="msk",
             sources=("wildberries",), deepen=False, min_score=0.0):
    """Токен-free добыча ссылок-кандидатов под текстовый запрос → список провенанс-словарей.

    Дефолт-источник доказан сетево — Wildberries (rank-3): выдача → сверка по фактам → card.json.
    sources=("wildberries","open_images") добавляет открытый поиск (весь веб). НИЧЕГО не скачиваем
    целиком — строим прямые ссылки; тяжёлую тройную проверку делает hunt(). Порядок отдачи —
    по СВЕРКЕ С ЗАПРОСОМ (самый на-запрос первым), затем по лестнице источника и позиции выдачи;
    так hunt() проверяет самые точные кадры раньше и набирает need быстрее. deepen (card.json) по
    умолчанию OFF в discover() и ON в find() — примитив не ходит в сеть без спроса.
    """
    facts = facts or {}
    out, seen = [], set()
    if "wildberries" in sources:
        for c in _discover_wb(query, facts, limit_products, pics_per, city, deepen, min_score):
            if c["url"] not in seen:
                seen.add(c["url"])
                out.append(c)
    if "open_images" in sources:
        for pos, it in enumerate(_open_image_urls(query, limit=limit_products)):
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            m = match_facts(query, it.get("title", ""))
            out.append({
                "url": it["url"], "nm_id": None, "name": it.get("title", ""),
                "price_rub": None, "marketplace": "open_web",
                "source_kind": "open_search", "rank": 5, "position": pos, "pic_index": 1,
                "confidence": m["score"], "match": m, "vendor_code": None,
                "product_url": it.get("source_page"),
                "license": "открытый поиск: происхождение и право — проверка и решение оператора",
            })
    # РАНЖИР: лестница источника первым (ВБ доказан чище открытого поиска), внутри — по сверке
    # с запросом (самый точный кадр раньше), тай-брейк по позиции выдачи и номеру кадра.
    out.sort(key=lambda c: (c.get("rank", 9), -(c.get("confidence") or 0.0),
                            c.get("position", 0), c.get("pic_index", 0)))
    return out


def find(query, facts=None, need=5, limit_products=12, pics_per=1, city="msk",
         sources=("wildberries",), deepen=True, min_score=0.0):
    """ПОЛНЫЙ ОРГАН: запрос → добыча (discover) → проверка (hunt) → прямые ссылки + честный вердикт.

    sources — какие добытчики звать: ("wildberries",) по умолч., ("wildberries","open_images")
    чтобы искать ВЕЗДЕ (вкл. иноязычные сайты через открытый поиск). Замыкает обещание «сказал
    товар → получил прямую PNG/WEBP-ссылку под API Маркета». Честность цела: источник не в реестре
    чистых → 'unknown' (рабочая ссылка + один взгляд), а НЕ 'good'. clean_candidates — те же
    неясные, НО отобранные пиксельно (белый фон + мало текста + зрение не опровергло) и
    отсортированные чистотой: оператору сразу видно, из чего брать чистый пиксель под инфографику.
    deepen=True (дефолт живого органа) добирает card.json → сверка по артикулу+характеристикам →
    самый на-запрос товар первым (message-4 «самый точный источник для тебя»); в discover() OFF.
    """
    facts = facts or {}
    cands = discover(query, facts=facts, limit_products=limit_products, pics_per=pics_per,
                     city=city, sources=sources, deepen=deepen, min_score=min_score)
    by_url = {c["url"]: c for c in cands}
    res = hunt([c["url"] for c in cands], facts=facts, need=need)
    for grp in ("good", "unknown", "bad"):
        for r in res.get(grp, []):
            prov = by_url.get(r["url"])
            if prov:
                r["provenance"] = {k: prov[k] for k in
                                   ("nm_id", "name", "marketplace", "source_kind", "product_url",
                                    "license", "price_rub", "confidence", "vendor_code")
                                   if k in prov}
    res["direct_links"] = ([r["url"] for r in res.get("good", [])] +
                           [r["url"] for r in res.get("unknown", [])])[:need]
    # ЧИСТЫЕ ПИКСЕЛИ НАВЕРХ: кадры (good+unknown), где пиксельный скоринг не возразил —
    # белый фон + мало текста + зрение не опровергло. Сортировка по белизне фона: оператору
    # сразу видно, из чего брать чистый пиксель под нашу инфографику. Вердикт НЕ повышаем.
    cc = []
    for grp in ("good", "unknown"):
        for r in res.get(grp, []):
            sig = r.get("clean") or {}
            if sig.get("clean_candidate"):
                cc.append({
                    "url": r["url"], "verdict": r["verdict"],
                    "bg_white_frac": sig.get("bg_white_frac"),
                    "ocr_words": sig.get("ocr_words"),
                    "product_confirmed": sig.get("product_confirmed"),
                    "name": (r.get("provenance") or {}).get("name"),
                    "product_url": (r.get("provenance") or {}).get("product_url"),
                    "source_kind": (r.get("provenance") or {}).get("source_kind"),
                })
    cc.sort(key=lambda x: (x["bg_white_frac"] if x["bg_white_frac"] is not None else -1.0),
            reverse=True)
    res["clean_candidates"] = cc
    res["query"] = query
    res["discovered"] = len(cands)
    return res


if __name__ == "__main__":
    caps = capabilities()
    print("ФОТО-ИСКАТЕЛЬ · паспорт возможностей:")
    for k, v in caps.items():
        if k == "vision_hint":
            continue
        print("   %-22s %s" % (k, "да" if v else "НЕТ"))
    if not caps["vision"]:
        print("\n   " + caps["vision_hint"])

    argv = sys.argv[1:]
    if argv and argv[0] == "--find":
        # ЗАПРОС → ПРЯМЫЕ ССЫЛКИ. Полный орган: добыча (WB + card.json-сверка) + тройная проверка.
        want_web = "--web" in argv
        query = " ".join(a for a in argv[1:] if a != "--web").strip()
        if not query:
            print("\nиспользование: photo_hunter_v1.py --find \"ВПП плёнка 0.3x100\" [--web]")
            sys.exit(2)
        facts = {"kind": "воздушно-пузырьковая плёнка в рулоне", "bubble_mm": 30,
                 "subject_keywords": ["bubble wrap", "bubble film", "bubble", "пузырч", "плёнк", "плен"]}
        srcs = ("wildberries", "open_images") if want_web else ("wildberries",)
        # pics_per=None → берём число кадров из card.json (photo_count), а не жёсткую единицу.
        out = find(query, facts=facts, need=5, limit_products=8, pics_per=None, sources=srcs)
        print("\nЗАПРОС: %s" % query)
        print("добыто ссылок: %d · годных: %d · неясно: %d · отбито: %d"
              % (out["discovered"], len(out["good"]), len(out["unknown"]), len(out["bad"])))
        for grp, tag in (("good", "ГОДЕН"), ("unknown", "НЕЯСНО"), ("bad", "ОТБОЙ")):
            for r in out[grp]:
                prov = r.get("provenance") or {}
                nm, conf = prov.get("name", ""), prov.get("confidence")
                sfx = ""
                if nm:
                    sfx = "\n        товар: %s%s" % (
                        nm, ("  (сверка %.0f%%)" % (conf * 100)) if conf is not None else "")
                print("  [%s] %s\n        %s%s" % (tag, r["url"], r["why"], sfx))
        if out["direct_links"]:
            print("\nПРЯМЫЕ ССЫЛКИ ПОД ЗАЛИВКУ (Маркет принимает webp):")
            for u in out["direct_links"]:
                print("  " + u)
    elif argv:
        facts = {"kind": "воздушно-пузырьковая плёнка в рулоне", "bubble_mm": 30}
        out = hunt(argv, facts=facts, need=len(argv))
        print("\nгодных: %d · отбито: %d · неясно: %d"
              % (len(out["good"]), len(out["bad"]), len(out["unknown"])))
        for grp, tag in (("good", "ГОДЕН"), ("bad", "ОТБОЙ"), ("unknown", "НЕЯСНО")):
            for r in out[grp]:
                print("  [%s] %s\n        %s" % (tag, r["url"][:88], r["why"]))

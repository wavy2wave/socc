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

ЧЕСТНОСТЬ (закон органа): рисуем ТОЛЬКО факты, которые реально есть в `facts`. Никаких выдуманных
«доставка сегодня»/«гарантия качества» — если оператор не дал факт, его нет на кадре.

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


def render(base, facts=None, brand=None, zoom=True):
    """Собирает PIL-кадр инфографики (без записи на диск). None → нельзя собрать (нет PIL/битая база).

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
    M = 76                                            # поле ≈7.4% — воздух (закон инфографики)

    f_over = _load_font(24, bold=False)               # надстрочная марка
    f_lbl = _load_font(23, bold=False)                # подпись факта
    f_val = _load_font(28, bold=True)                 # значение факта (28 — запас на перенос в 2 строки)
    f_sys = _load_font(20, bold=False)                # системная подпись

    # 1) Надстрочная слово-марка (муdraщ, вразрядку пробелами — минимализм без спец-кернинга).
    over = " ".join(list(str(b["wordmark"]).upper())).replace("   ", "  ")
    d.text((M, 62), over, font=f_over, fill=b["muted"])

    # 2) Герой — что это (жирно, чернила). ФРАЗА НЕ ПРОПАДАЕТ: переносим целиком в ≤2 строки
    #    (чинит «Воздушно-пузырьковая пл…»), при длинных названиях авто-ужимаем шрифт.
    hero = _hero_line(facts)
    hero_y = 98
    hero_bottom = 150
    if hero:
        f_h, lines = None, None
        for size, f_h in ((58, _load_font(58, bold=True)),
                          (52, _load_font(52, bold=True)),
                          (46, _load_font(46, bold=True))):
            lines = _wrap(d, hero, f_h, CANVAS_W - 2 * M, max_lines=2)
            if len(lines) <= 2:
                break
        for ln in lines or []:
            d.text((M, hero_y), ln, font=f_h, fill=b["ink"])
            hero_y += int(size * 1.15)
        hero_bottom = (hero_y + 10) if (lines and len(lines) > 1) else 176
    # 3) Марка-тег (продуктовая линейка «МиниБабл»/«БаблБокс»/«Компакт») — только если факт есть.
    marka = str((facts or {}).get("марка") or "").strip()
    if marka:
        f_m = _load_font(26, bold=True)
        tag_y = hero_bottom + 18
        d.rectangle([M, tag_y, M + 8, tag_y + 26], fill=b["accent"])          # мини-планка акцента
        d.text((M + 22, tag_y + 2), marka.upper(), font=f_m, fill=b["ink"])
        hero_bottom = tag_y + 36
    # 4) Фирменная акцент-черта (подпись SOCC) — короткая толстая линия под героем.
    d.rectangle([M, hero_bottom, M + 120, hero_bottom + 5], fill=b["accent"])

    specs = _specs(facts)
    # Зона товара: между героем и лентой фактов (если фактов нет — лента не занимает место).
    band_top = 1064 if specs else CANVAS_H - M
    prod_top = hero_bottom + 34
    prod_box = (M, prod_top, CANVAS_W - M, band_top - 24)
    bw, bh = prod_box[2] - prod_box[0], prod_box[3] - prod_box[1]
    if bw > 0 and bh > 0:
        pw, ph = prod.size
        scale = min(bw / pw, bh / ph)
        nw, nh = max(1, int(pw * scale)), max(1, int(ph * scale))
        fitted = prod.resize((nw, nh))
        ox = prod_box[0] + (bw - nw) // 2
        oy = prod_box[1] + (bh - nh) // 2
        canvas.paste(fitted, (ox, oy))                # белый фон товара сливается с белым канвасом

    # 4) Нижняя лента фактов: тонкая линия + до 3 колонок «ПОДПИСЬ / значение» (значение в ≤2 строки).
    if specs:
        d.line([(M, band_top), (CANVAS_W - M, band_top)], fill=b["hairline"], width=2)
        n = len(specs)
        col_w = (CANVAS_W - 2 * M) / n
        for i, (label, val) in enumerate(specs):
            cx = M + i * col_w
            d.rectangle([cx, band_top + 34, cx + 26, band_top + 39], fill=b["accent"])   # мини-акцент
            d.text((cx, band_top + 52), label.upper(), font=f_lbl, fill=b["muted"])
            vy = band_top + 84
            for ln in _wrap(d, val, f_val, col_w - 22, max_lines=2):
                d.text((cx, vy), ln, font=f_val, fill=b["ink"])
                vy += 34

    # 5) Опциональная системная подпись внизу-справа. По умолчанию ПУСТО: SOCC — внутренняя марка,
    #    покупателю на карточке не нужна (директива оператора). Слово-марка магазина остаётся сверху.
    sysmark = str(b.get("system") or "").strip()
    if sysmark:
        sw = _text_w(d, sysmark, f_sys)
        sy = CANVAS_H - 40
        d.ellipse([CANVAS_W - M - sw - 20, sy + 6, CANVAS_W - M - sw - 8, sy + 18], fill=b["accent"])
        d.text((CANVAS_W - M - sw, sy), sysmark, font=f_sys, fill=b["muted"])
    return canvas


def compose_infographic(base, facts=None, brand=None, out_dir=None, deliver_dir=None,
                        open_it=False, tag="item", dry=True, zoom=True):
    """Куёт фирменный инфографический кадр поверх УЖЕ готового фото. Всегда 0₽, 0 сети.

    base       — путь|bytes|PIL.Image готового (лучше канон-белого) кадра товара.
    facts      — словарь фактов; на ленту идут ТОЛЬКО присутствующие (честно), ≤3.
    brand      — перекрытие BRAND (wordmark/accent/…), 1 строка на смену марки/цвета.
    out_dir    — куда писать кадр (дефолт state/forged/); deliver_dir — доп. копия «для глаз» (Desktop).
    open_it    — открыть в Просмотре (только darwin; в stdout ничего не печатаем).
    dry        — здесь НЕ про деньги (их нет): dry=True → НЕ копируем в deliver_dir/не открываем
                 (тихий предпросмотр), dry=False → доставляем оператору. Кадр пишется в out_dir всегда.
    Возврат: {ok, path, thumb, dry, cost_usd:0.0, content:{hero,specs,wordmark}, why}.
    """
    rep = {"ok": False, "path": None, "thumb": None, "dry": bool(dry), "cost_usd": 0.0,
           "content": {"hero": _hero_line(facts), "specs": _specs(facts),
                       "wordmark": (brand or {}).get("wordmark", BRAND["wordmark"])},
           "why": ""}
    if not _HAVE_PIL:
        rep["why"] = "нет Pillow — инфографику не рисуем (честно; поставь PIL в venv фото-органа)"
        return rep
    img = render(base, facts=facts, brand=brand, zoom=zoom)
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
                              zoom=not args.no_zoom)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(_main())

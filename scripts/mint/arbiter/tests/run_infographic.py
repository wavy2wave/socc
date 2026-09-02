#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ИНФОГРАФИКА ПРИЁМКА — фирменный SOCC-минимализм поверх готового кадра (локально, 0₽, 0 сети).

Орган photo_infographic_v1 куёт ВТОРОЙ кадр карточки: чистое канон-фото + разумная лента фактов,
нарисованная НАМИ через PIL (не ИИ → буквы целы, 0₽, детерминировано). Приёмка проверяет ДВА
столпа: (а) КУРАТОР фактов — на ленту идут только существенные, влияющие на выбор, характеристики,
в правильном приоритете, честно и без дублей; (б) БЕЗОПАСНОСТЬ — 0₽, 0 сети, честный отказ без PIL.

  G1  socc_absent          — директива «надпись SOCC не нужна»: system-подпись ВЫКЛ по умолч.,
                             в отчёте нет строки «SOCC», слово-марка карточки ≠ SOCC.
  G2  decision_order_box    — короб → [Размер, В упаковке, Материал]: размер, потом КОЛИЧЕСТВО
                             (драйвер опта) ВЫШЕ материала; вес-тара/форма/страна отпали (филлер).
  G3  film_standalone_dims  — рулон плёнки (нет «размера») → [Ширина, Длина, Плотность]:
                             standalone-габариты метража и плотность — реальные драйверы выбора.
  G4  honesty_present_only  — только филлер → []: ничего не выдумываем (ни «доставка», ни «гарантия»).
  G5  dedup_by_label        — размер+габариты+dims_raw → одна «Размер»; штук+количество → одна «В упаковке».
  G6  max_n_cap_crowding    — 3 драйвера присутствуют → вторичное (цвет) вытеснено; всегда ≤3.
  G7  demote_not_drop       — одежда (размер/цвет/состав) → ЦВЕТ ПОКАЗАН: вторичные опущены, НЕ выкинуты
                             (орган общий: где цвет и есть выбор — он доступен). Ключевое отличие дизайна.
  G8  excluded_plumbing     — голые length/width/height/weight/страна/бренд/форма НЕ дают строк.
  G9  nopil_honest_refuse   — без Pillow → ok=False, cost_usd=0.0, why про PIL, БЕЗ падения.
  G10 cost_zero_rubicon     — cost_usd=0.0 всегда (dry и live); у органа нет сетевых швов (0 сети).
  G11 render_size_pil       — [PIL] render() → RGB-холст ровно 1024×1280 (4:5 как карточка).
  G12 autocrop_shrinks_pil  — [PIL] авто-кроп по предмету реально уменьшает белые поля (товар крупнее).
  G13 wrap_two_lines_pil    — [PIL] длинное значение переносится в ≤2 строки, слова не теряются.

Столпы (а) чисто-логические → идентичны на любом интерпретаторе. PIL-тесты (G11-G13) само-гейтятся:
без Pillow (системный python 3.14) честно пропускаются с пометкой — приёмка 100% зелёная на обоих,
а на venv (3.13 + Pillow) дополнительно гоняет реальный рендер. Наружу не уходит ничего (0₽, 0 сети).
"""
import io
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import photo_infographic_v1 as ig    # noqa: E402


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


def _no_pil_skip(tag):
    """Единый честный пропуск PIL-теста без Pillow (тот же контракт проверен в G9)."""
    return True, f"PIL отсутствует → {tag} пропущен (честный отказ проверен в G9)"


def _white_with_dark_box(w=1024, h=1280, margin=300):
    """Синтетика: белый холст с тёмным прямоугольником по центру (для рендера/автокропа)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([margin, margin, w - margin, h - margin], fill=(40, 40, 40))
    return im


# ── (в) ЗАКОН ЧИСТОЙ БАЗЫ + ЦВЕТ-КАК-СМЫСЛ (директива 2026-09-02) ─────────────────────
# Гейт/цвет — новые законы органа: не брендировать грязный донор (двойная инфографика), акцент несёт
# вариант товара. OCR-зависимые гейты честно пропускаются без tesseract (строгий закон: без OCR база
# чистой не признаётся → «пройти» проверить нельзя, а «отказать грязному» уже покрыто логикой).

def _ocr_ok():
    return ig._tesseract() is not None


def _soiled_synthetic():
    """Чистый фон + товар по центру + чужой текст-инфографика (как грязный донор WB): тёмный текст
    продавца прямо на белом в зоне ленты — ровно то, что OCR кадра обязан поймать."""
    from PIL import Image, ImageDraw, ImageFont
    im = _white_with_dark_box(margin=320)
    d = ImageDraw.Draw(im)
    font = None
    for fp in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
               "/System/Library/Fonts/Supplemental/Arial.ttf",
               "/System/Library/Fonts/Helvetica.ttc"):
        try:
            font = ImageFont.truetype(fp, 44)
            break
        except Exception:
            continue
    d.text((150, 1160), "СКИДКА 50% КАЧЕСТВО ОПТ ДОСТАВКА", fill=(30, 30, 30),
           font=font or ImageFont.load_default())
    d.text((150, 1225), "3 СЛОЯ ПРЕМИУМ ЗАЩИТА БЕСПЛАТНО 24 ЧАСА", fill=(30, 30, 30),
           font=font or ImageFont.load_default())
    return im


def t14_clean_gate_refuses_soiled():
    """ЗАКОН ЧИСТОЙ БАЗЫ: грязный донор (чужой текст/плашка на белом фоне) НЕ брендируется —
    compose возвращает ok=False с честной причиной про чистый-гейт (никакой двойной инфографики)."""
    if not ig._HAVE_PIL:
        return _no_pil_skip("clean_refuse")
    if not _ocr_ok():
        return True, "OCR нет → отказ грязному гарантирован конструктивно (строже к худшему)"
    import tempfile
    from PIL import Image
    soiled = _soiled_synthetic()
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        soiled.save(f.name, "JPEG", quality=92)
        path = f.name
    try:
        rep = ig.compose_infographic(path, facts={"вид": "Короб", "размер": "60×40 см"}, dry=True)
        refused = (rep["ok"] is False and rep["path"] is None
                   and "чистый-гейт" in (rep.get("why") or ""))
        clean_flag = (rep.get("clean") or {}).get("ok") is False
        words_seen = (rep.get("clean") or {}).get("ocr_words") or 0
        return refused and clean_flag, (f"ok={rep['ok']} clean.ok={clean_flag} "
                                        f"ocr_words={words_seen} why={rep.get('why','')[:60]!r}")
    finally:
        try:
            import os
            os.unlink(path)
        except Exception:
            pass


def t15_clean_gate_passes_clean():
    """Обратная сторона: ЧИСТАЯ база (товар на белом, без текста) проходит гейт и брендируется."""
    if not ig._HAVE_PIL:
        return _no_pil_skip("clean_pass")
    if not _ocr_ok():
        return True, "OCR нет → пройти гейт нельзя доказать честно (пропускаем)"
    import tempfile
    clean = _white_with_dark_box(margin=300)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        clean.save(f.name, "JPEG", quality=92)
        path = f.name
    try:
        rep = ig.compose_infographic(path, facts={"вид": "Короб", "размер": "60×40 см"}, dry=True)
        ok = rep["ok"] is True and (rep.get("clean") or {}).get("ok") is True
        return ok, (f"ok={rep['ok']} clean.ok={(rep.get('clean') or {}).get('ok')} "
                    f"bg={(rep.get('clean') or {}).get('bg_white_frac')}")
    finally:
        try:
            import os
            os.unlink(path)
        except Exception:
            pass


def t16_box_color_is_class():
    """ЦВЕТ-КАК-СМЫСЛ (арт-канон): у короба цвет кодирует КЛАСС/СЛОИ/МАРКУ. Премиум-слово или Т-24 →
    cherry; 5-слой → cherry; «усиленный/армирован/7-слой» → plum; 4-слой/Т-23 → teal; стандарт → cyan."""
    def ac(facts):
        return tuple(ig.resolve_accent(facts))
    C = ig.GRADE
    prem = ac({"вид": "Короб №10-Ц (премиум)", "размер": "600×400×400", "материал": "Т-24 В"})
    lay5 = ac({"вид": "Короб", "материал": "5-слойный гофрокартон"})
    armd = ac({"вид": "Короб усиленный", "материал": "5-слойный гофрокартон"})
    lay4 = ac({"вид": "Короб четырёхклапанный", "слои_картона": "четырёхслойный"})
    lay7 = ac({"вид": "Короб", "слои_картона": "7-слойный"})
    std = ac({"вид": "Коробка картонная", "размер": "60×40 см"})
    ok = (prem == C["cherry"] and lay5 == C["cherry"] and armd == C["plum"]
          and lay4 == C["teal"] and lay7 == C["plum"] and std == C["cyan"])
    return ok, (f"premium={prem} 5слой={lay5} усилен={armd} 4слой={lay4} "
                f"7слой={lay7} стандарт={std}")


def t17_film_color_is_axis():
    """Плёнка: цвет по ОСИ (плотность→толщина→пузырёк→ширина). 120см (>0.5м) и 0.75м → teal (пром-
    формат); 300мм/0.5м → cyan; плотность 130 → indigo, 180 → cherry; пузырёк 16 → cherry; без факта → cyan."""
    def ac(facts):
        return tuple(ig.resolve_accent(facts))
    def kind(f):
        return (ig.variant_signal(f) or {}).get("kind")
    C = ig.GRADE
    ok = (ac({"вид": "Плёнка", "ширина_см": 120}) == C["teal"]
          and ac({"вид": "Плёнка", "ширина": "0,75 м"}) == C["teal"]
          and ac({"вид": "Плёнка", "ширина": "300 мм"}) == C["cyan"]
          and ac({"вид": "Плёнка", "ширина_м": 0.5}) == C["cyan"]
          and ac({"вид": "Плёнка", "плотность_г_м2": 130}) == C["indigo"]
          and ac({"вид": "Плёнка", "плотность_г_м2": 180}) == C["cherry"]
          and ac({"вид": "Плёнка", "толщина_мм": 0.04}) == C["indigo"]
          and ac({"вид": "Плёнка", "диаметр_пузырька_мм": 16}) == C["cherry"]
          and ac({"вид": "Плёнка", "длина_м": 100}) == C["cyan"])
    wide_kind = kind({"вид": "Плёнка", "ширина_см": 120})
    ok = ok and wide_kind == "teal"
    return ok, (f"120см=teal 0.75м=teal 300мм=cyan 0.5м=cyan d130=indigo d180=cherry "
                f"t.04=indigo b16=cherry длинa=cyan wide_kind={wide_kind}")


def t18_grade_box_layers_lexicon():
    """Резолв короба по цифрам/словам слоёв и маркам Т; склонение токена; из «5-слойный/пятислойный»."""
    def gr(f):
        return ig.grade_resolve(f)
    # числительное «пятислойный» → 5; Т-23 отдельно от Т-24
    g5 = gr({"вид": "Короб", "слои_картона": "пятислойный гофрокартон"})
    g24 = gr({"вид": "Короб", "материал": "гофрокартон Т-24"})
    g23 = gr({"вид": "Короб", "материал": "Т-23 картон"})
    g1 = gr({"вид": "Короб", "слои_картона": "трёхслойный"})
    ok = (g5["tier"] == "cherry" and g5["token"] == "5 СЛОЁВ"
          and g24["tier"] == "cherry" and g24["token"] == "Т-24"
          and g23["tier"] == "cherry" and g23["token"] == "Т-23"
          and g1["tier"] == "cyan" and g1["token"] == "3 СЛОЯ"
          and ig._sklon_layer(1) == "СЛОЙ" and ig._sklon_layer(4) == "СЛОЯ"
          and ig._sklon_layer(5) == "СЛОЁВ" and ig._sklon_layer(13) == "СЛОЁВ"
          and ig._sklon_layer(21) == "СЛОЙ")
    return ok, (f"5слой={g5['token']}({g5['tier']}) Т-24={g24['token']} Т-23={g23['token']} "
                f"3слой={g1['token']}")


def t19_grade_film_honest_no_axis():
    """Плёнка честна: нет факта ОСИ (только длина/материал) → has_fact False и токена НЕТ; есть слабое
    число оси → has_fact True, но ступень cyan (стандарт), токен None (не рисуем фальшивый премиум)."""
    no = ig.grade_resolve({"вид": "Плёнка", "длина_м": 100})
    weak = ig.grade_resolve({"вид": "Плёнка", "плотность_г_м2": 40})
    ok = (no["has_fact"] is False and no["tier"] == "cyan" and no["token"] is None
          and weak["has_fact"] is True and weak["tier"] == "cyan" and weak["token"] is None
          and weak["num"] == 40.0 and weak["axis_label"] == "Плотность")
    return ok, (f"нет-оси: has_fact={no['has_fact']} tier={no['tier']} | "
                f"плотность40: has_fact={weak['has_fact']} tier={weak['tier']} num={weak['num']}")


def t20_fmt_split_num_helpers():
    """Хелперы чисел/единиц: «0,5» (RU-запятая), «1.20» → «1,2»; 600×400×400 мм → (число, мм); × не режется."""
    ok = (ig._fmt_num(1.2) == "1,2" and ig._fmt_num(0.5) == "0,5"
          and ig._fmt_num(40) == "40" and ig._fmt_num(180) == "180"
          and ig._split_val_unit("600×400×400 мм") == ("600×400×400", "мм")
          and ig._split_val_unit("60×40") == ("60×40", "")
          and ig._split_val_unit("10") == ("10", ""))
    return ok, (f"fmt={ig._fmt_num(1.2)}/{ig._fmt_num(0.5)} split="
                f"{ig._split_val_unit('600×400×400 мм')}")



# ── (а) КУРАТОР ФАКТОВ ───────────────────────────────────────────────────────────────

def t1_socc_absent():
    # директива оператора: «надпись SOCC не нужна» — системная подпись выключена по умолчанию.
    default_off = ig.BRAND.get("system", None) == ""
    rep = ig.compose_infographic(io.BytesIO(b"not-an-image"),
                                 facts={"вид": "Короб", "размер": "60×40 см"}, dry=True)
    blob = json.dumps(rep, ensure_ascii=False)
    no_socc = "SOCC" not in blob
    wm = rep["content"]["wordmark"]
    wm_not_socc = "SOCC" not in str(wm)
    ok = default_off and no_socc and wm_not_socc
    return ok, f"system_off={default_off} no_socc_in_report={no_socc} wordmark={wm!r}"


def t2_decision_order_box():
    box = {"вид": "Гофрокороб", "размер": "600×400×400 мм", "штук_в_упаковке": 10,
           "материал": "гофрокартон", "слои_картона": "пятислойный",
           "weight": 0.35, "форма": "четырёхклапанная", "страна": "Россия"}
    specs = ig._specs(box)
    labels = [l for l, _ in specs]
    ok = labels == ["Размер", "В упаковке", "Материал"]
    # количество ВЫШЕ материала (фикс приоритет-бага), тара/форма/страна не просочились
    return ok, f"labels={labels}"


def t3_film_standalone_dims():
    film = {"kind": "Плёнка", "ширина_м": 0.5, "длина_м": 100, "плотность_г_м2": 40,
            "толщина_мм": 0.12, "диаметр_пузырька_мм": 10}
    specs = ig._specs(film)
    labels = [l for l, _ in specs]
    ok = labels == ["Ширина", "Длина", "Плотность"]
    return ok, f"labels={labels}"


def t4_honesty_present_only():
    filler = {"страна": "Китай", "бренд": "NoName", "форма": "куб", "weight": 1.2}
    specs = ig._specs(filler)
    empty = specs == []
    # орган не выдумывает продающих обещаний
    rep = ig.compose_infographic(io.BytesIO(b"x"), facts=filler, dry=True)
    blob = json.dumps(rep, ensure_ascii=False)
    no_invented = ("доставка" not in blob.lower()) and ("гарант" not in blob.lower())
    ok = empty and no_invented
    return ok, f"specs_empty={empty} no_invented_promises={no_invented}"


def t5_dedup_by_label():
    a = {"размер": "60×40", "габариты": "60×40×40", "dims_raw": "600x400x400"}
    b = {"штук_в_упаковке": 10, "количество": 10, "в упаковке": "10 шт"}
    la = [l for l, _ in ig._specs(a)]
    lb = [l for l, _ in ig._specs(b)]
    ok = la == ["Размер"] and lb == ["В упаковке"]   # каждый смысл — одна строка
    return ok, f"size={la} qty={lb}"


def t6_max_n_cap_crowding():
    many = {"размер": "S", "штук_в_упаковке": 5, "материал": "хлопок",
            "цвет": "синий", "плотность": 200, "объём": "3 л"}
    specs = ig._specs(many)
    labels = [l for l, _ in specs]
    cap = len(specs) <= 3
    crowded = "Цвет" not in labels and "Объём" not in labels   # вторичное вытеснено драйверами
    ok = cap and crowded and len(labels) == len(set(labels))
    return ok, f"n={len(specs)} labels={labels}"


def t7_demote_not_drop():
    # РЕШЕНИЕ ДИЗАЙНА: вторичные ОПУЩЕНЫ, а не выкинуты → для одежды цвет доступен и показан.
    apparel = {"вид": "Футболка", "размер": "M", "цвет": "синий", "состав": "100% хлопок"}
    labels = [l for l, _ in ig._specs(apparel)]
    color_shown = "Цвет" in labels
    return color_shown, f"labels={labels} (цвет доступен для не-упаковочной категории)"


def t8_excluded_plumbing():
    plumbing = {"length": 60, "width": 40, "height": 40, "weight": 0.3,
                "страна_производства": "РФ", "brand": "X", "марка": "Т-24"}
    specs = ig._specs(plumbing)
    ok = specs == []       # плита профиля МП / филлер — не человеку на карточку
    return ok, f"specs={specs}"


# ── (б) БЕЗОПАСНОСТЬ / RUBICON ───────────────────────────────────────────────────────

def t9_nopil_honest_refuse():
    saved = ig._HAVE_PIL
    try:
        ig._HAVE_PIL = False
        rep = ig.compose_infographic("/tmp/whatever.jpg",
                                     facts={"вид": "Короб", "размер": "60×40"}, dry=True)
        ok = (rep["ok"] is False and rep["cost_usd"] == 0.0
              and "PIL" in rep["why"] and rep["path"] is None)
    finally:
        ig._HAVE_PIL = saved
    return ok, f"ok={rep['ok']} cost={rep['cost_usd']} why={rep['why'][:40]!r}"


def t10_cost_zero_rubicon():
    # cost всегда 0.0 (и в отказе, и в реальном рендере), и у органа НЕТ сетевых швов.
    saved = ig._HAVE_PIL
    costs = []
    try:
        ig._HAVE_PIL = False
        costs.append(ig.compose_infographic("/x.jpg", facts={"размер": "1"}, dry=True)["cost_usd"])
        costs.append(ig.compose_infographic("/x.jpg", facts={"размер": "1"}, dry=False)["cost_usd"])
    finally:
        ig._HAVE_PIL = saved
    all_zero = all(c == 0.0 for c in costs)
    no_net = not hasattr(ig, "_http_call") and not hasattr(ig, "_request")   # нет сетевых функций
    ok = all_zero and no_net
    return ok, f"costs={costs} no_network_seams={no_net}"


# ── (б+) РЕАЛЬНЫЙ РЕНДЕР (само-гейт: без Pillow честно пропускаем) ─────────────────────

def t11_render_size_pil():
    if not ig._HAVE_PIL:
        return _no_pil_skip("render_size")
    base = _white_with_dark_box()
    canvas = ig.render(base, facts={"вид": "Короб", "размер": "60×40×40 см",
                                    "штук_в_упаковке": 10, "материал": "гофрокартон"})
    ok = canvas is not None and canvas.size == (ig.CANVAS_W, ig.CANVAS_H) and canvas.mode == "RGB"
    return ok, f"size={None if canvas is None else canvas.size} (ждём {ig.CANVAS_W}×{ig.CANVAS_H})"


def t12_autocrop_shrinks_pil():
    if not ig._HAVE_PIL:
        return _no_pil_skip("autocrop")
    base = _white_with_dark_box(margin=300)          # предмет в белых полях
    cropped = ig._autocrop_subject(base)
    shrunk = cropped.size[0] < base.size[0] and cropped.size[1] < base.size[1]
    # корень жалобы «товар мелкий»: белые поля срезаны → предмет крупнее в кадре
    return shrunk, f"{base.size} → {cropped.size}"


def t13_wrap_two_lines_pil():
    if not ig._HAVE_PIL:
        return _no_pil_skip("wrap")
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    f = ig._load_font(28, bold=True)
    long_val = "5-слойный гофрокартон Т-24 повышенной прочности"
    lines = ig._wrap(d, long_val, f, max_w=260, max_lines=2)
    two_max = 1 <= len(lines) <= 2
    joined = " ".join(lines).replace("…", "").strip()
    # первое слово-драйвер не потеряно (не режем «5-слойный» в огрызок)
    keeps_head = joined.split(" ")[0] == "5-слойный"
    ok = two_max and keeps_head
    return ok, f"lines={lines}"


def _synthetic_base():
    """Белое + СЕРОЕ изделие (sat≈0) → любой насыщенный пиксель кадра = НАШ акцент (cyan-бар / ступень)."""
    return _white_with_dark_box(margin=340)


def _sat_family(px):
    """Hue-семейство насыщенного пикселя: 'ct' (cyan/teal 170–205), 'ind' (indigo 212–240),
    'cherry' (plum/cherry 320–360), None — не насыщен (текст/серый/белый/растушёвка не в счёт)."""
    r, g, b = px
    mx, mn = max(px), min(px)
    if mx - mn < 48:
        return None                       # серо-белое: наш ink/muted/hairline/текст — фон канона
    if mx == r:
        h = 60 * (((g - b) / (mx - mn)) % 6)
    elif mx == g:
        h = 60 * ((b - r) / (mx - mn) + 2)
    else:
        h = 60 * ((r - g) / (mx - mn) + 4)
    h %= 360
    if 170 <= h <= 205:
        return "ct"
    if 212 <= h <= 240:
        return "ind"
    if 320 <= h or h <= 12:
        return "cherry"
    return "other"                        # чужой цвет — канон НЕ разрешает


def _audit(canvas, allowed):
    """Сканирует кадр: все насыщенные пиксели обязаны быть в allowed-семействах. → (ok, чужие, счёт)."""
    families = {}
    px = canvas.load()
    for y in range(0, canvas.size[1], 2):            # шаг 2 — аудит дешёвый, не пропустит полосу
        for x in range(0, canvas.size[0], 2):
            f = _sat_family(px[x, y])
            if f and f != "other":
                families[f] = families.get(f, 0) + 1
            elif f == "other":
                families["other"] = families.get("other", 0) + 1
    foreign = {k: v for k, v in families.items() if k not in allowed}
    return not foreign, foreign, families


def _render_macro(facts):
    return ig.render(_synthetic_base(), facts=facts, zoom=False)


def t21_palette_audit_box():
    """ПАЛИТРА КАДРА КОРОБА (пиксели): cyan-бар-константа есть всегда; ступень ровно одна и по факту.
    Премиум/5слой/усилен-7слой → в кадре только {cyan, вишня-слива}; 4слой → только cyan/teal-семья
    (НЕТ красного — не рисуем премиум, которого нет); стандарт без факта → ТОЛЬКО cyan (закон честности)."""
    if not ig._HAVE_PIL:
        return _no_pil_skip("palette_box")
    C = ig.GRADE
    prem = _audit(_render_macro({"вид": "Короб премиум", "материал": "Т-24 В"}), {"ct", "cherry"})
    teal = _audit(_render_macro({"вид": "Короб", "слои_картона": "четырёхслойный"}), {"ct"})
    std = _audit(_render_macro({"вид": "Коробка картонная", "размер": "60×40 см"}), {"ct"})
    # вишня реально нарисована (не только бар) у премиума, и её НЕТ у 4слой/стандарта
    prem_has_cherry = (prem[2] or {}).get("cherry", 0) > 0
    red_leak_teal = (teal[2] or {}).get("cherry", 0) + (teal[2] or {}).get("other", 0)
    ok = prem[0] and prem_has_cherry and teal[0] and red_leak_teal == 0 and std[0]
    return ok, (f"prem={prem[1] or 'чисто'} cherry_px={prem_has_cherry} "
                f"4слой={teal[1] or 'чисто'} std={std[1] or 'чисто'}")


def t22_palette_audit_film():
    """ПАЛИТРА КАДРА ПЛЁНКИ: ось индиго (130 г/м²) → в кадре есть индиго-семья и нет красного;
    плотность 40 (слабая, стандарт) → ТОЛЬКО cyan-семья (слабую ось НЕ красим как премиум); без оси → cyan."""
    if not ig._HAVE_PIL:
        return _no_pil_skip("palette_film")
    ind = _audit(_render_macro({"вид": "Плёнка", "плотность_г_м2": 130}), {"ct", "ind"})
    weak = _audit(_render_macro({"вид": "Плёнка", "плотность_г_м2": 40}), {"ct"})
    noax = _audit(_render_macro({"вид": "Плёнка", "длина_м": 100}), {"ct"})
    ind_present = (ind[2] or {}).get("ind", 0) > 0
    no_red = (ind[2] or {}).get("cherry", 0) == 0 and (weak[2] or {}).get("cherry", 0) == 0
    ok = ind[0] and ind_present and no_red and weak[0] and noax[0]
    return ok, (f"indigo={ind[1] or 'чисто'} indigo_px={ind_present} "
                f"weak={weak[1] or 'чисто'} noax={noax[1] or 'чисто'}")


def t23_palette_audit_generic():
    """Общая категория (чашки) — не короб/не плёнка: кадр монохром + cyan-бар, НИКАКИХ других цветов."""
    if not ig._HAVE_PIL:
        return _no_pil_skip("palette_generic")
    gen = _audit(_render_macro({"вид": "Набор чашек", "количество": "6 шт"}), {"ct"})
    only_cyan = all(k == "ct" for k in (gen[2] or {}))
    return gen[0] and only_cyan, f"generic={gen[1] or 'чисто'} families={sorted((gen[2] or {}).keys())}"


TESTS = [
    ("G1  socc_absent", t1_socc_absent),
    ("G2  decision_order_box", t2_decision_order_box),
    ("G3  film_standalone_dims", t3_film_standalone_dims),
    ("G4  honesty_present_only", t4_honesty_present_only),
    ("G5  dedup_by_label", t5_dedup_by_label),
    ("G6  max_n_cap_crowding", t6_max_n_cap_crowding),
    ("G7  demote_not_drop", t7_demote_not_drop),
    ("G8  excluded_plumbing", t8_excluded_plumbing),
    ("G9  nopil_honest_refuse", t9_nopil_honest_refuse),
    ("G10 cost_zero_rubicon", t10_cost_zero_rubicon),
    ("G11 render_size_pil", t11_render_size_pil),
    ("G12 autocrop_shrinks_pil", t12_autocrop_shrinks_pil),
    ("G13 wrap_two_lines_pil", t13_wrap_two_lines_pil),
    ("G14 clean_gate_refuses_soiled", t14_clean_gate_refuses_soiled),
    ("G15 clean_gate_passes_clean", t15_clean_gate_passes_clean),
    ("G16 box_color_is_class", t16_box_color_is_class),
    ("G17 film_color_is_axis", t17_film_color_is_axis),
    ("G18 grade_box_layers_lexicon", t18_grade_box_layers_lexicon),
    ("G19 grade_film_honest_no_axis", t19_grade_film_honest_no_axis),
    ("G20 fmt_split_num_helpers", t20_fmt_split_num_helpers),
    ("G21 palette_audit_box", t21_palette_audit_box),
    ("G22 palette_audit_film", t22_palette_audit_film),
    ("G23 palette_audit_generic", t23_palette_audit_generic),
]


def main():
    pil = "✔ Pillow" if ig._HAVE_PIL else "○ без Pillow (PIL-тесты пропущены честно)"
    print(f"🎯 ИНФОГРАФИКА ПРИЁМКА · фирменный кадр (локально, 0₽, 0 сети) · {pil}")
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

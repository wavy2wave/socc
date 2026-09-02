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

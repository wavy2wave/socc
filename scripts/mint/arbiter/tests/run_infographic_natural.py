#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_infographic_natural — регресс RGBA-пути «естественных краёв» (_paste_natural).

Покрывает код, которого нет в run_infographic (там RGB-белые базы): товар-вырезку ставят
БАЗОЙ на низ зоны + МЯГКАЯ КОНТАКТНАЯ ТЕНЬ. Без глаз: вся проверка программная (пиксели).

Законы, которые держит тест:
  N1 база товара стоит ровно на низу зоны (y1), товар не плавает.
  N2 под базой есть мягкая тень: min-lum 130..235 сразу под основанием (серая, не чёрная),
     и СПАД вниз (светлеет) до чистого белого — тень не «плита».
  N3 кап высоты: при огромном белом ходе вниз тень короткая (~8% роста), не 200px-полоса:
     через ~30px под базой уже чистый белый.
  N4 ширина тени не шире товара: по бокам от следа под базой бело.
  N5 разделитель/текст ниже зоны НЕ задевается: если под базой нарисована линия, тень гаснет
     ДО неё и за неё не перетекает (runway-замер).
  N6 если под базой почти нет белого хода (<5px) — тень честно НЕ рисуется (no-op), товар цел.
  N7 контейнмент: кольцо 8px по периметру холста белое (ничего не вылезло).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import photo_infographic_v1 as ig
from PIL import Image, ImageDraw

W, H = 1024, 1280
FAIL = []


def white_canvas():
    return Image.new("RGB", (W, H), (255, 255, 255))


def lum(px, x, y):
    p = px[x, y]
    return (p[0] + p[1] + p[2]) / 3.0


def min_lum(px, y, x0, x1):
    return min(lum(px, x, y) for x in range(x0, x1, 4))


def box_product(w=520, h=220):
    """Плотный RGBA-«товар»: непрозрачный тёмный прямоугольник на всю площадь (база вплотную к низу)."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], fill=(22, 92, 60, 255))
    return im


def check(name, cond, detail=""):
    if cond:
        print("  ✅ PASS %s %s" % (name, detail))
    else:
        print("  ❌ FAIL %s %s" % (name, detail))
        FAIL.append(name)


def ring_check(name, canvas):
    px = canvas.load()
    bad = []
    for y in range(H):
        for x in list(range(8)) + list(range(W - 8, W)):
            if lum(px, x, y) < 250:
                bad.append((x, y)); break
    for x in range(W):
        for y in list(range(8)) + list(range(H - 8, H)):
            if lum(px, x, y) < 250:
                bad.append((x, y)); break
    check(name + "_ring", not bad, "" if not bad else "out " + str(bad[:2]))


# ── N1..N4, N7: база + мягкая короткая тень ────────────────────────────────────────────────
cv = white_canvas()
prod = box_product()
ZONE = (200, 300, 824, 900)          # низ y1 = 900
ig._paste_center(cv, prod, ZONE)
ring_check("N7", cv)
px = cv.load()
# товар: тело до y900
body = min_lum(px, 899, 400, 620)
check("N1_body_at_base", body < 120, "min-lum@899=%d" % body)
# сразу под базой — мягкая серая тень (не чёрная, не пусто)
g = min_lum(px, 903, 300, 724)
check("N2_shadow_present", 130 <= g <= 235, "min-lum@903=%d" % g)
# спад вниз
vals = [min_lum(px, yy, 300, 724) for yy in (905, 911, 917)]
check("N2_fade_down", vals[0] < vals[1] <= vals[2] and vals[2] < 253,
      "905:%d 911:%d 917:%d" % (vals[0], vals[1], vals[2]))
# N3: кап — далеко под базой уже бело (не длинная плита)
far = min_lum(px, 935, 300, 724)
check("N3_cap_short", far == 255, "min-lum@935=%d" % far)
# N4: тень законно чуть шире следа товара (~кап nw+3%), но НЕ убегает далеко в стороны
# (товар x∈[200,824], тень ≤ ~x191..833) — за пределами тени бело
side_l = min_lum(px, 905, 150, 186)
side_r = min_lum(px, 905, 838, 874)
check("N4_no_side_bleed", side_l >= 250 and side_r >= 250,
      "L=%d R=%d" % (side_l, side_r))

# ── N5: линия ниже зоны не задевается (runway-замер) ──────────────────────────────────────
cv = white_canvas()
d = ImageDraw.Draw(cv)
d.line([(150, 932), (900, 932)], fill=(30, 30, 30), width=2)   # «разделитель паспорта» в 32px от базы
ig._paste_center(cv, box_product(), ZONE)                      # y1 = 900
px = cv.load()
# между базой и линией тень гаснет, не долетая до линии
pre_line = min_lum(px, 928, 300, 724)
on_line = min_lum(px, 932, 300, 724)
post_line = min_lum(px, 938, 300, 724)
check("N5_fade_before_line", pre_line >= 250, "min-lum@928=%d (не должно быть тени у самой линии)" % pre_line)
check("N5_line_intact", on_line < 120, "line lum@932=%d" % on_line)
check("N5_no_spill_past", post_line >= 250, "min-lum@938=%d (за линией не должно перетекать)" % post_line)

# ── N6: малый ход под базой → тень не рисуется (no-op), товар цел ─────────────────────────
cv = white_canvas()
d = ImageDraw.Draw(cv)
d.line([(150, 903), (900, 903)], fill=(30, 30, 30), width=2)   # линия в 3px от базы
ig._paste_center(cv, box_product(), ZONE)
px = cv.load()
under = min_lum(px, 902, 300, 724)
body_b = min_lum(px, 899, 300, 724)
check("N6_no_shadow_tight", under >= 250, "min-lum@902=%d (не должно быть тени)" % under)
check("N6_product_ok", body_b < 120, "body lum@899=%d" % body_b)

print("\nИТОГ: %s" % ("ВСЁ ЗЕЛЁНО" if not FAIL else "ПРОВАЛЫ: " + ",".join(FAIL)))
sys.exit(1 if FAIL else 0)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""photo_cutout_v1 — орган «ВЫРЕЗАТЬ ТОВАР»: донор-фото любого фона → ПРОДУКТ НА БЕЛОМ.

Зачем: кадр инфографики обязан показывать сам товар, а не пустое место. У донора товар часто на
цветном/грязном фоне (наш гейт require_clean не пропустил бы его как базу). Решение — отматтить предмет
ЛОКАЛЬНО (rembg/u2net, onnxruntime CPU), положить на чистый белый, отдать дальше compose_infographic
(там по-прежнему стоит гейт чистой базы: белые углы + нет чужих текстов — поэтому старые законы целы).

Честность/границы:
  • 0₽, 0 сети НА карточку: модель u2net качается ОДИН раз (176МБ) и кэшируется в ~/.rembg; дальше
    весь маттинг локальный (~0.3-0.8с CPU на фото). Карточка данных товара НЕ покидает машину.
  • Вырезаем ФОТО ТОГО ЖЕ ТОВАРА (дропшип одного SKU) — это товар, а не чужая инфографика; чужие
    тексты/лейблы на самом товаре — часть товара, их не трогаем.
  • Если фон/кадр не маттится (продукт почти весь кадр или сцена сложная) — честно говорим и не
    выдаём артефакт за товар.
  • Тяжёлая зависимость (onnxruntime + rembg, ~300МБ) — НОВАЯ для SOCC; решение оператора (см. README).

API:
  cutout(src, out_png=None)                -> {'ok','img'(RGBA),'alpha_frac','bbox','secs'}
  product_on_white(src, pad=0.06)          -> {'ok','img'(белый PIL, товар по центру),'cut',...}
  pick_best(shots, max_n=8)                -> лучший кадр-кандидат по маттингу всех (без записи)
"""
import os, io, time, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from PIL import Image
    from rembg import remove, new_session
    _HAVE = True
except Exception as _e:                       # pragma: no cover
    _HAVE = False
    _e = _e
    Image = None

_SESSION = None
_MODEL = os.environ.get("PHOTO_CUTOUT_MODEL", "u2net")
_WHITE = (255, 255, 255)
_BG_THR = 252                                  # для crop'а: «почти белый» считаем фоном


def _sess():
    global _SESSION
    if _SESSION is None:
        _SESSION = new_session(_MODEL)
    return _SESSION


def _src_image(src):
    if Image is None:
        return None
    if isinstance(src, Image.Image):
        return src.convert("RGB")
    if isinstance(src, (bytes, bytearray)):
        return Image.open(io.BytesIO(src)).convert("RGB")
    if isinstance(src, (str, os.PathLike)):
        return Image.open(str(src)).convert("RGB")
    return None


def cutout(src, out_png=None, session=None):
    """Убрать фон (rembg/u2net). Возврат: ok/alpha_frac/bbox/сек или ok=False+why."""
    t0 = time.time()
    if not _HAVE:
        return {"ok": False, "why": "no rembg (pip install 'rembg[cpu]')", "secs": time.time() - t0}
    im = _src_image(src)
    if im is None:
        return {"ok": False, "why": "unreadable src", "secs": time.time() - t0}
    try:
        cut = remove(im, session=session or _sess())
    except Exception as e:
        return {"ok": False, "why": f"rembg: {e}", "secs": time.time() - t0}
    a = cut.split()[-1]
    alpha_frac = sum(a.histogram()[64:]) / float(cut.size[0] * cut.size[1])
    mask = a.point(lambda v: 255 if v > 64 else 0)
    bbox = mask.getbbox()
    rep = {"ok": True, "img": cut, "alpha_frac": round(alpha_frac, 3), "bbox": bbox,
           "secs": round(time.time() - t0, 3)}
    if out_png:
        os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
        cut.save(out_png)
        rep["out_png"] = out_png
    return rep


def product_on_white(src, pad=0.06, session=None, out_png=None):
    """Товар на чистом белом: маттим → кладём по центру на белый холст пропорций предмета.
    Возврат: {'ok','img'(RGB белый холст),'cut','alpha_frac','secs','why'}."""
    rep = cutout(src, session=session)
    if not rep["ok"]:
        return rep
    cut, bbox = rep["img"], rep["bbox"]
    if not bbox:
        return {"ok": False, "why": "маттинг не дал предмета", "secs": rep["secs"]}
    x0, y0, x1, y1 = bbox
    pw, ph = x1 - x0, y1 - y0
    if pw < 8 or ph < 8:
        return {"ok": False, "why": "предмет слишком мал на кадре", "secs": rep["secs"]}
    pw2, ph2 = int(pw * (1 + 2 * pad)), int(ph * (1 + 2 * pad))
    white = Image.new("RGBA", (pw2, ph2), _WHITE + (255,))
    ox, oy = int(pad * pw), int(pad * ph)
    white.paste(cut.crop(bbox), (ox, oy), cut.crop(bbox).split()[-1])
    white = white.convert("RGB")
    rep["img"] = white
    rep["cut_png"] = out_png
    if out_png:
        os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
        white.save(out_png)
    return rep


def grounded_cutout(src, session=None, out_png=None):
    """Вырезка товара, «снятого на столе»: если u2net прицепил к предмету СВЕТЛУЮ подложку/стол вплоть
    до нижней кромки кадра (низ bbox упирается в рамку), честно обрезаем альфу по линии базы — нижнему
    ряду, где предмет ещё плотный, а ПОД ним начинается почти-белый фон (>=97% строки светлое).
    Убираем ТОЛЬКО фон (стол+его тень), пикселей предмета НЕ добавляем. Если предмет не упирается в низ
    или резкой светлой базы нет — возвращаем обычный cutout без изменений (no-op, безопасно для старых
    путей). Возврат как у cutout + ключ 'ground_trim' (int: строка среза | None) и 'img' — RGBA-вырезка.

    Зачем: у доноров товар часто стоит на светлом столе, и rembg сливает стол в предмет (альфа до рамки),
    что выглядит как «обрезанный низ» и плита под товаром. Наш фин-кадр ставит товар НА белый низ зоны
    со своей контактной тенью — чужая плита/стол там не нужны.
    """
    rep = cutout(src, session=session)
    if not rep["ok"] or not rep.get("img"):
        return rep
    cut, bbox = rep["img"], rep["bbox"]
    if not bbox:
        return rep
    W, H = cut.size
    x0, y0, x1, y1 = bbox
    # предмет не упирается в нижнюю кромку — стол не мог быть прицеплен; ничего не делаем
    if y1 < H - 4:
        rep["ground_trim"] = None
        return rep
    alpha = cut.split()[-1]
    rgb = cut.convert("RGB")
    px = rgb.load()
    xs = list(range(x0, x1, 2))
    n = len(xs)

    def _lum(x, y):
        p = px[x, y]
        return (p[0] + p[1] + p[2]) / 3.0

    # Строка базы = кромка «тёмный предмет НАД / светлый стол ПОД»: почти все колонки разом
    # темнеют→светлеют. У артефактов лейбла такие скачки лишь на части ширины.
    base = None
    for cand in sorted(range(y0 + 46, min(y1, H - 1) - 6, 2),
                       key=lambda y: -sum(1 for x in xs
                                          if _lum(x, y + 4) - _lum(x, y - 4) > 60
                                          and _lum(x, y - 4) < 150)):
        y = cand
        if y <= (base or 0):
            continue
        cnt = sum(1 for x in xs if _lum(x, y + 4) - _lum(x, y - 4) > 60 and _lum(x, y - 4) < 150)
        if cnt < max(8, int(n * 0.5)):
            continue
        # страховка: сразу ПОД кромкой светлый стол (а не тёмный предмет) — иначе это внутренняя кромка
        below = sum(1 for x in xs if _lum(x, min(y + 10, H - 2)) >= 185)
        if below >= max(8, int(n * 0.9)):
            base = y + 5          # срезаем через пару строк ниже перехода — уходит стол
            break
    if base is None:
        rep["ground_trim"] = None
        return rep
    # срезать альфу ниже базы (стол + его тень) — фон уходит, предмет остаётся целиком
    anew = alpha.point(lambda v: v)
    anew_px = anew.load()
    for yy in range(base + 1, H):
        for xx in range(0, W):
            anew_px[xx, yy] = 0
    clean = cut.copy()
    clean.putalpha(anew)
    rep["img"] = clean
    rep["alpha_frac"] = round(sum(anew.histogram()[64:]) / float(W * H), 3)
    rep["bbox"] = clean.split()[-1].getbbox() or bbox
    rep["ground_trim"] = base
    rep["why"] = "низ упирался в рамку: срезан светлый стол по линии базы (фон, не предмет)"
    if out_png:
        os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
        clean.save(out_png)
    return rep


def pick_best(shots, max_n=8, session=None, want=None):
    """Прогнать маттинг по кадрам-кандидатам и выбрать лучший под наш вертикальный кадр.
    Правила: продукт занимает 15..80% кадра, центр горизонтально близок к середине, края НЕ упираются
    в рамку (иначе это обрезка/сцена, а не предмет). want='big' — предпочесть большего. 0₽/0 сети.
    """
    scores = []
    for i, s in enumerate(shots[:max_n]):
        r = cutout(s, session=session)
        if not r["ok"]:
            scores.append((i, r)); continue
        bbox = r["bbox"]
        if not bbox:
            scores.append((i, {**r, "score": -1, "why": "no bbox"})); continue
        W, H = r["img"].size
        x0, y0, x1, y1 = bbox
        pw, ph = x1 - x0, y1 - y0
        af = r["alpha_frac"]
        cx = (x0 + x1) / 2.0 / W
        cxpen = abs(cx - 0.5)
        edge = int(y1 > H - 6) + int(x1 > W - 6) + int(x0 < 6)   # вплотную к краям — штраф
        hf, wf = ph / H, pw / W
        # цель: предмет вертикальный/квадратный, по центру, 40..75% высоты, без упора в края
        if 0.12 <= af <= 0.8 and 0.25 <= hf <= 0.95 and wf / max(hf, 0.01) < 1.8 and edge == 0:
            score = hf - 0.45 * cxpen - 0.35 * abs(wf / max(hf, 0.01) - 0.55) + (0.1 if 0.35 <= hf <= 0.8 else -0.3)
        else:
            score = -1
        scores.append((i, {**r, "score": round(score, 3), "cx": round(cx, 2), "hf": round(hf, 2)}))
    good = [(i, r) for i, r in scores if r.get("score", -1) > 0]
    if not good:
        return {"ok": False, "why": "ни один кадр не маттится в предмет", "shots": scores}
    if want == "big":
        good.sort(key=lambda t: -t[1]["bbox"][3])
    else:
        good.sort(key=lambda t: -t[1]["score"])
    return {"ok": True, "chosen": good[0][0], "rep": good[0][1], "all": [(i, {k: r[k] for k in
            ("score", "alpha_frac", "secs", "why") if k in r}) for i, r in scores]}


if __name__ == "__main__":
    # CLI-прогон: python3 photo_cutout_v1.py <фото> <out_white.png> [out_cut.png]
    import json
    src, outp = sys.argv[1], sys.argv[2]
    outp_cut = sys.argv[3] if len(sys.argv) > 3 else None
    rep = product_on_white(src, out_png=outp)
    if outp_cut and rep.get("cut_png") is None and rep.get("ok"):
        rep2 = cutout(src, out_png=outp_cut)
        rep["cut_secs"] = rep2.get("secs")
    print(json.dumps({k: v for k, v in rep.items() if k != "img"}, ensure_ascii=False, indent=1))
    sys.exit(0 if rep.get("ok") else 1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OZON ARTICLE V1 — системный СЕМАНТИЧЕСКИЙ артикул (артикул = ключ).

Оператор (2026-09-09): артикул виден в карточке Ozon, по нему должно быть «грубо понятно ВСЁ
о товаре», артикул — ключ библиотеки. Образцы оператора: коробки BX-389 (токен-семейство + номер).
Схема (латиница — безопасна для этикеток/выгрузок, уникальна, детерминирована, БЕЗ сетевых вызовов):

  VPP-{W}x{L}-{слои}[k]-{NN}

  • VPP       = семейство: рулон воздушно-пузырьковой плёнки (ВПП) файл-линейки.
  • {W}       = ширина в СМ целым (20..220).
  • {L}       = длина в М: целое число (5,10,50,100); единственная нецелая 1.2 → «1-2»
               (дефис как разделитель дроби; с целыми не коллизирует).
  • {слои}    = 1|2|3 — слои из имени (без слова → 1, «грубо»; двух/трёхслойн → 2/3).
  • k         = чёрная (прозрачная не помечаем — цвет по умолчанию).
  • {NN}      = «-» + 2 цифры — индекс ВНУТРИ одинаковой сигнатуры (w,l,слои,цвет), ставится
                ТОЛЬКО когда сигнатура не уникальна (семейства-«древо» до 32 карточек);
                порядок детерминирован (по исходному артикулу) → стабилен между пересборками.

Семейства (расширяемо под след. категории библиотеки):
  рулон-в-м → VPP ; пакеты-пупырка → PUP ; м-одиночное → SHT ; в-см → ROL ;
  коробки → BOX ; лента/скотч → TAP ; без-размера → RAW ; пленка-прочее → FLM

Почему БЕЗ «фраз-аффирмаций»: артикул — это ключ (уникальность/поиск/маршрут), фраза бы его
загрязнила и сломала бы уникальность. Декоративные слова не входят в ключ (при желании — имя).
"""
import re

# ── семейство по честному типу классификатора (расширяемо под каталог) ──
FAMILY = {
    "рулон-в-м": "VPP",      # воздушно-пузырьковая плёнка, рулон в метрах
    "пакеты-пупырка": "PUP",
    "м-одиночное": "SHT",
    "в-см": "ROL",
    "коробка": "BOX",
    "коробки": "BOX",
    "лента": "TAP",
    "скотч": "TAP",
    "без-размера": "RAW",
    "плёнка-прочее": "FLM",
    "пленка-прочее": "FLM",
}


def family_of(rec):
    t = (rec or {}).get("type") or ""
    return FAMILY.get(t, "RAW")


def layers_of(name):
    """Слои из имени: трёхслойн/3х/3-х слой(ная)/«в 3 слоя» → 3; двухслойн/2х/2-х слой(ная)/«2 слоя» → 2.
    Иначе 1 (грубо, по умолчанию). Словесные формы («трёх/двухслойн») и цифровые («2 слоя», «3-х слойная»)
    обе ловим — иначе код соврёт о слоях (артикул должен говорить ВСЁ о товаре)."""
    n = re.sub(r"\s+", " ", (name or "").lower()).replace("ё", "е")
    if re.search(r"трехслойн|3\s*[-х]?\s*слойн|3\s*[-х]?\s*слоя?\b|3\s*слой", n):
        return 3
    if re.search(r"двухслойн|2\s*[-х]?\s*слойн|2\s*[-х]?\s*слоя?\b|2\s*слой", n):
        return 2
    return 1


def color_k(name):
    """Чёрная → 'k' (прозрачная не помечаем)."""
    n = (name or "").lower()
    if "чёрн" in n or "черн" in n:
        return "k"
    return ""


def sig_of(rec):
    """Сигнатура (семейство, w_см, длина-токен, слои, цвет) — ключ «древа» одинаковых."""
    fam = family_of(rec)
    sz = rec.get("size") or {}
    w_m, l_m = sz.get("w_m"), sz.get("l_m")
    if not w_m:
        return (fam, None, None, None, None)
    w_cm = int(round(float(w_m) * 100))
    if l_m is None:
        l_tok = None
    elif float(l_m) == int(l_m):
        l_tok = str(int(l_m))
    else:
        l_tok = str(l_m).replace(".", "-")          # единственная 1.2 → «1-2»
    return (fam, w_cm, l_tok, layers_of(rec.get("name")), color_k(rec.get("name")))


def _encode_sig(sig):
    fam, w_cm, l_tok, layers, k = sig
    if w_cm is None:
        return fam
    return f"{fam}-{w_cm}x{l_tok}-{layers}{k}"


def build_index(records):
    """article(исходный) → системный код. Детерминировано: сигнатуры сортируем, внутри сигнатуры
    индекс по исходному артикулу (стабильно между пересборками матрицы). Пустой ввод → {}."""
    recs = [r for r in (records or []) if isinstance(r, dict)]
    by_sig = {}
    for i, r in enumerate(recs):
        by_sig.setdefault(sig_of(r), []).append((i, r))
    out = {}
    for sig, group in by_sig.items():
        group_sorted = sorted(group, key=lambda ir: str((ir[1].get("article") or "")).zfill(40))
        base = _encode_sig(sig)
        need_idx = len(group) > 1
        for j, (i, r) in enumerate(group_sorted, start=1):
            code = base if not need_idx else f"{base}-{j:02d}"
            out[r.get("article")] = code
    return out


def article_for(records, article):
    """Код по исходному артикулу; нет в индексе → честный None (не выдумываем)."""
    idx = build_index(records)
    return idx.get(str(article))


def demo(records=None, limit=10):
    """Печать образцов для оператора (0 сетевых вызовов)."""
    if records is None:
        return "demo: передай records"
    idx = build_index(records)
    lines = [f"СИСТЕМНЫЙ АРТИКУЛ · индекс {len(idx)} записей"]
    shown_sig = set()
    for r in sorted(records, key=lambda x: str(x.get("article") or "")):
        if r.get("type") != "рулон-в-м":
            continue
        sz = r.get("size") or {}
        if not sz.get("w_m"):
            continue
        sig = sig_of(r)
        if sig in shown_sig:
            continue
        shown_sig.add(sig)
        lines.append(f"  {idx.get(r.get('article')):16s} ← {r.get('article')} · {str(r.get('name'))[:64]}")
        if len([s for s in shown_sig if s[:2] == sig[:2]]) > limit:
            break
        if len([x for x in shown_sig]) >= limit:
            break
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ozon_library_v1 as LIB
    lib = LIB.load_library()
    recs = lib.get("records") or []
    idx = build_index(recs)
    codes = list(idx.values())
    print(f"записей: {len(recs)} · уник кодов: {len(set(codes))} · кодов=записей: {len(set(codes)) == len(codes)}")
    print(demo(recs, limit=16))

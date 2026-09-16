#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН КОРОБКИ · Echelon-1 · СУХОЙ МАНИФЕСТ КРУПНОЙ ПЕРЕЕЗДНОЙ (0₽, показ оператору).

Решение оператора 09.09 (AskUserQuestion): Echelon-1 = «Вся крупная переездная»;
кабинет = «Сначала сухо, потом решим» → собираю ЭШЕЛОН-1 ПОЛНОСТЬЮ СУХО (0₽, twin-гард,
манифест) под новый кабинет «OZON Express Box» (client 5838715) и ПОКАЗЫВАЮ. Живой шаг —
отдельно, после показа и слова (RUBICON).

ИСТОЧНИК карточек: слой «ИП Анна/ya new/карго/Коробка для переезда Готов Озон.xlsx»
(база ozon_korobki_base_2026-09-08.json), строки:
  • readiness = ГОТОВО
  • поштучные (в имени НЕТ «шт»)  — оператор: «важно чтобы были коробки по 1 шт»
  • длинная сторона ≥500 мм (переездные/гардеробные/пятислойные/Бизнес) — «акцент
    600×400×400, 700×500×500, 800×550×550, гардеробный»
Прайс «как есть» (решение оператора: «Цены файлов как есть»). Своё фото cdn1 100%.

КАТЕГОРИЯ/ТИП: dci в строке = 17036258 «Коробка для переезда» — МЁРТВ в живом дереве.
Ремап в живую (17027937 «Коробка для хранения», тип 95482 «коробка для хранения») — тот же
прецедент, что 203 an_exp_car в CARD_LIVE 988. Категорию подтвердил ОРГАН (живой лист),
не оператор.

⚠ ВАЖНО ПРО ОВХ (аудит этого прохода): «упаковка»-колонки всех ИП-файлов коробок —
ИИ-филлер (пачка 20×20×20×20-коробок «весит» 980 г при упаковке 133×150×130 мм; то же
значение у 600-мм короба). Поэтому:
  • РАЗМЕРЫ карточки = СОБРАННЫЙ размер из ИМЕНИ (мм, полный парс 3-4 знака) — сверен с
    дон-близнецом (№10-МК Бизнес 600×400×400 ↔ an_ex_c_26 и т.д.). Не из base.ovh.
  • ВЕС = из файла (base.ovh.weight_g, те же колонки) — ПОМЕЧЕН ⚠ НЕПРОВЕРЕН. Для живой
    карточки вес обязателен; перед живым шагом нужен честный источник веса (образец/дон-чтение)
    — это ГЕЙТ, выносим оператору.
Порядок размера как в имени = Д×Ш×В (гардероб 500×600×1000: 1000 — высота, короб высокий).

Живой шаг — НЕ здесь. Здесь: сборка to_item (5 обязательных атрибутов 85/9048/8229/23536/22232),
сухой create_product батчем ≤100, манифест json/md + заморозка items.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ozon_card_v1 as C                      # noqa: E402
import ozon_hands_write_v1 as H               # noqa: E402
import ozon_korobki_card_manifest_v1 as M     # noqa: E402  (BOX_PROFILE/REQUIRED_IDS/_tn_ved_of)

DATE = "2026-09-09"
BASE = HERE / "runtime" / "ozon_boxes" / "ozon_korobki_base_2026-09-08.json"
SRC = "ИП Анна/ya new/карго/Коробка для переезда Готов Озон.xlsx"
TARGET_CABINET = "OZON Express Box · client 5838715 (creds OZON_BOX_*, пин перед живым)"
CREATE_BATCH = 100

OUT_JSON = HERE / "runtime" / "ozon_boxes" / f"korobki_echelon1_DRY_{DATE}.json"
OUT_MD = HERE / "runtime" / "ozon_boxes" / f"korobki_echelon1_DRY_{DATE}.md"
OUT_ITEMS = HERE / "runtime" / "ozon_boxes" / f"korobki_echelon1_DRY_{DATE}.items.json"

# Полный парс мм из имени: 3 ИЛИ 4 знака на грань (не обрезаем 1000/1300 как регэксп 3 знака).
_DIM_RE = re.compile(r"(\d{3,4})\s*[×xх*]\s*(\d{3,4})\s*[×xх*]\s*(\d{3,4})")


def _name_dims(name):
    m = _DIM_RE.search(str(name))
    if not m:
        return None
    return tuple(int(g) for g in m.groups())


def _load_candidates():
    data = json.loads(BASE.read_text(encoding="utf-8"))
    out = []
    for p in data["products"]:
        if p.get("source") != SRC:
            continue
        if "ГОТОВО" not in (p.get("readiness") or []):
            continue
        name = str(p.get("name") or "")
        if "шт" in name:
            continue  # только по 1 шт (решение оператора)
        dims = _name_dims(name)
        if not dims:
            continue
        if max(dims) < 500:  # длинная сторона ≥500 → крупная переездная/гардеробная
            continue
        if not (p.get("photos") and p.get("price")):
            continue
        out.append((p, dims))
    out.sort(key=lambda x: x[0]["art"])
    return out


def _tn_ved_sig(name):
    return M._tn_ved_of(name)  # тот же сигнальный выбор, что у CARD_LIVE 988 (без изобретений)


def main():
    cands = _load_candidates()
    print(f"кандидаты Echelon-1 (поштучные, L≥500, ГОТОВО, своё фото): {len(cands)}")

    items, metas, skipped = [], [], []
    for p, dims in cands:
        art = str(p["art"])
        name = str(p["name"])
        d, w, h = dims          # порядок имени = Д×Ш×В (гардероб: 1000/1300 = высота)
        ovh = p.get("ovh") or {}
        w_raw = ovh.get("weight_g")
        tn = _tn_ved_sig(name)
        prod = {
            "offer_id": art,
            "name": name,
            "price": float(p["price"]),
            "vat": "0",
            "description_category_id": 17027937,
            "type_id": 95482,                          # «коробка для хранения» (жив; прецедент an_exp_car)
            "images": [str(x) for x in (p.get("photos") or [])][:15],
            "dimensions": {"depth": d, "width": w, "height": h,
                           "weight": int(w_raw) if w_raw else 0},
            "_profile": M.BOX_PROFILE,
            "_spec": {"_model": art, "тип": "коробка для хранения",
                      "тн_вэд": tn},
        }
        if not (w_raw and int(w_raw) > 0):
            skipped.append({"art": art, "name": name[:60], "reason": "нет честного веса в файле"})
            continue
        try:
            out = C.to_item(prod)
        except C.CardError as e:
            skipped.append({"art": art, "name": name[:60], "reason": f"CardError: {e}"})
            continue
        item, m = out["item"], out["meta"]
        if item is None:
            skipped.append({"art": art, "name": name[:60],
                            "reason": f"to_item None: {m.get('block_reason')}"})
            continue
        attrs = item.get("attributes") or []
        a_ids = {a.get("id") for a in attrs}
        if M.REQUIRED_IDS - a_ids:
            skipped.append({"art": art, "name": name[:60],
                            "reason": f"нет обяз. атрибутов: {sorted(M.REQUIRED_IDS - a_ids)}"})
            continue
        items.append(item)
        metas.append({"art": art, "name": name[:66], "price": float(p["price"]),
                      "dims_mm_assembled": list(dims), "weight_file_g": int(w_raw),
                      "weight_note": "из файла, НЕПРОВЕРЕН — гейт перед живым",
                      "type_id": 95482, "tn_ved": tn,
                      "attrs": sorted(a_ids), "images": len(item.get("images", [])),
                      "photo0": (p.get("photos") or [""])[0][:70]})

    print(f"собрано item: {len(items)} · пропущено: {len(skipped)}")
    for s in skipped:
        print("  skip:", s["art"], "—", s["reason"][:90])

    batches, dry_ok = [], True
    for i in range(0, len(items), CREATE_BATCH):
        chunk = items[i:i + CREATE_BATCH]
        r = H.create_product(chunk, dry=True, commit=False)
        st = r.get("status") if isinstance(r, dict) else None
        if st != "dry":
            dry_ok = False
            print(f"  батч {len(batches)+1} ({len(chunk)}): status={st}")
        else:
            print(f"  батч {len(batches)+1} ({len(chunk)}): dry ok")
        batches.append(len(chunk))

    price_min = min(float(p["price"]) for p, _ in cands)
    price_max = max(float(p["price"]) for p, _ in cands)
    dims_sizes = sorted({tuple(m["dims_mm_assembled"]) for m in metas})
    tn = {}
    for m in metas:
        tn[m["tn_ved"]] = tn.get(m["tn_ved"], 0) + 1

    manifest = {
        "date": DATE,
        "title": "Echelon-1 · крупная переездная поштучная · СУХО (0₽) под OZON Express Box 5838715",
        "target_cabinet": TARGET_CABINET,
        "source": SRC,
        "segment": "поштучные (по 1 шт) · длинная сторона ≥500 мм · ГОТОВО",
        "rule_operator": "акцент 600×400×400, 700×500×500, 800×550×550, гардеробный; прайс как есть",
        "category": {"description_category_id": 17027937, "type_id": 95482,
                     "why": "17036258 «Коробка для переезда» мёртв в живом дереве; ремап-прецедент an_exp_car CARD_LIVE 988 (решил ОРГАН)"},
        "candidates": len(cands),
        "items_built": len(items),
        "items_skipped": len(skipped),
        "skipped_list": skipped,
        "price": {"min": price_min, "max": price_max},
        "assembled_sizes": dims_sizes,
        "tn_ved": tn,
        "required_ids": sorted(M.REQUIRED_IDS),
        "batches": batches,
        "dry_ok": dry_ok,
        "metas": metas,
        "item_sample": items[0] if items else None,
        "ovh_audit": ("Упаковка-колонки всех ИП-файлов коробок = ИИ-филлер. РАЗМЕРЫ карточек = "
                      "собранный из имени (сверен с дон-близнецом). ВЕС из файла, помечен "
                      "НЕПРОВЕРЕН — честный источник веса нужен ДО живого шага (гейт, решает оператор)."),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    _write_md(manifest)
    OUT_ITEMS.write_text(json.dumps({"date": DATE, "target": TARGET_CABINET,
                                     "items": items, "metas": metas},
                                    ensure_ascii=False, indent=1))
    print(f"\nманифест: {OUT_JSON.name} (+md)")
    print(f"замороженные items ({len(items)}): {OUT_ITEMS.name}")
    print("\nВЕРДИКТ (сухой, 0₽):")
    print(f"  кандидатов {len(cands)} → item {len(items)} (skip {len(skipped)}), "
          f"dry-батчей {len(batches)} ok={dry_ok}, цена {price_min:.0f}–{price_max:.0f}₽")
    print("  ГЕЙТ перед живым: честный ВЕС карточки (образец/дон) + кабинет 5838715 (пин OZON_BOX_*) "
          "+ twin-скан + слово оператора (RUBICON).")
    return 0


def _write_md(m):
    L = [f"# КОРОБКИ · ЭШЕЛОН-1 · КРУПНАЯ ПЕРЕЕЗДНАЯ · СУХО 0₽ · {m['date']}",
         "",
         f"- цель: **{m['target_cabinet']}**",
         f"- источник: {m['source']}",
         f"- сегмент: {m['segment']}",
         f"- кандидатов: **{m['candidates']}** → собрано item: **{m['items_built']}** · "
         f"skip: {m['items_skipped']}",
         f"- цена (как есть): {m['price']['min']:.0f}–{m['price']['max']:.0f}₽/шт",
         f"- категория: {m['category']['description_category_id']} / тип {m['category']['type_id']}"
         f" — {m['category']['why']}",
         f"- ТН ВЭД: {m['tn_ved']} · обязательные атрибуты: {m['required_ids']}",
         f"- сухие батчи: {m['batches']} · dry_ok={m['dry_ok']}",
         "",
         "## Размеры (собранные, из имени) — сверены с дон-близнецом",
         ]
    for sz in m["assembled_sizes"]:
        L.append(f"- {sz[0]}×{sz[1]}×{sz[2]} мм")
    L.append("")
    L.append("## Карточки")
    L.append("| арт | цена | размер, мм | вес-файл ⚠ | ТН ВЭД | фото | имя |")
    L.append("|---|---|---|---|---|---|---|")
    for x in m["metas"]:
        L.append(f"| {x['art']} | {x['price']:.0f}₽ | {'×'.join(map(str, x['dims_mm_assembled']))} | "
                 f"{x['weight_file_g']} г ⚠ | {x['tn_ved']} | {x['images']} | {x['name']} |")
    if m["skipped_list"]:
        L.append("")
        L.append("## Пропущено")
        for s in m["skipped_list"]:
            L.append(f"- `{s['art']}` {s['name']} — {s['reason'][:70]}")
    L.append("")
    L.append("## ⚠ Аудит ОВХ этого прохода")
    L.append(m["ovh_audit"])
    if m.get("item_sample"):
        L.append("")
        L.append("## Пример собранного item")
        L.append("```json")
        L.append(json.dumps(m["item_sample"], ensure_ascii=False, indent=1))
        L.append("```")
    OUT_MD.write_text("\n".join(L))
    return True


if __name__ == "__main__":
    raise SystemExit(main())

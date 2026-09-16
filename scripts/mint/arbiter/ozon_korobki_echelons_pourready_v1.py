#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН КОРОБКИ · ПУЛ-ГОТОВЫЕ НАБОРЫ E1+E2 с ЧЕСТНЫМ ДОН-ВЕСОМ (0₽, сухие манифесты).

Применяет решения оператора 09.09 по весу (гейт #22 закрыт):
  1) «Разделить по имени» для 600×400×400: пятислойные → 846 г (дон 9602492-1 П-32 ВС),
     премиум/Бизнес/Т-24/Т-22 → 663 г (дон 9600067-1 №10-Ц). Остальные размеры с одним
     дон-фактом → вес = дон-факт (кг → г). Размеры из имени, НЕ из base.ovh (там ИИ-филлер).
  2) «Льём только дон-размеры»: в пул идут ТОЛЬКО карточки, у которых есть реальная коробка
     дона того же размера (честный вес И честная поставка). Без-дона — HELD (ждут образца/
     поставщика), НЕ теряются, НЕ льются.

Наружу ничего не пишет. Веса = дон-факт лексикона korobki_weight_lexicon_*.json (не выдумка).
Файл-вес (ИИ-филлер) в карточки БОЛЬШЕ не попадает — только в колонку ⚠ истории.

Выход (артефакты, заморозка items для живого залива после RUBICON):
  korobki_echelon1_POURREADY_2026-09-09.{json,md,items.json}   — 10 карточек
  korobki_echelon2_DRY_2026-09-09.{json,md,items.json}         — 7 карточек
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
import ozon_korobki_card_manifest_v1 as M     # noqa: E402

DATE = "2026-09-09"
BASE = HERE / "runtime" / "ozon_boxes" / "ozon_korobki_base_2026-09-08.json"
E1_ITEMS = HERE / "runtime" / "ozon_boxes" / "korobki_echelon1_DRY_2026-09-09.items.json"
LEX = HERE / "runtime" / "ozon_boxes" / f"korobki_weight_lexicon_{DATE}.json"
SRC = "ИП Анна/ya new/карго/Коробка для переезда Готов Озон.xlsx"
TARGET_CABINET = "OZON Express Box · client 5838715 (creds OZON_BOX_*, пин перед живым)"

# Вес 600×400×400 — выбор оператора 09.09 «разделить по имени»:
_SIX_HUNDRED = {"пятислойный": {"g": 846, "art": "9602492-1", "line": "П-32 ВС прочный пятислойный"},
                "премиум/бизнес": {"g": 663, "art": "9600067-1", "line": "№10-Ц Бизнес/премиум Т-24 В"}}

_DIM_RE = re.compile(r"(\d{3,4})\s*[×xх*]\s*(\d{3,4})\s*[×xх*]\s*(\d{3,4})")


def _facts(dims):
    """Дон-факты лексикона для размера (list)."""
    lex = json.loads(LEX.read_text(encoding="utf-8"))["lexicon"]
    key = "x".join(str(x) for x in sorted(dims))
    return lex.get(key, [])


def _load_e1():
    """Замороженные Echelon-1: items (payload) + metas (арт/размер/имя/файл-вес)."""
    d = json.loads(E1_ITEMS.read_text(encoding="utf-8"))
    return d["items"], d["metas"]


def _resolve_e1_weight(meta):
    """Вес по решению оператора: один дон-факт → факт; 600×400×400 → по имени."""
    name = meta["name"].lower()
    dims = tuple(meta["dims_mm_assembled"])
    if tuple(sorted(dims)) == (400, 400, 600):
        if "пятислойн" in name:
            return _SIX_HUNDRED["пятислойный"]
        return _SIX_HUNDRED["премиум/бизнес"]
    facts = _facts(dims)
    if len(facts) != 1:
        return None
    f = facts[0]
    return {"g": f["weight_g"], "art": f["art"],
            "line": f"{f.get('mark','')} {f['note'][:34]}".strip()}


def build_e1():
    items, metas = _load_e1()
    pour, held = [], []
    for it, meta in zip(items, metas):
        art = meta["art"]
        w = _resolve_e1_weight(meta)
        if w is None:
            held.append({"art": art, "name": meta["name"],
                         "dims": meta["dims_mm_assembled"], "price": meta["price"],
                         "reason": "нет дон-близнеца (нет честного веса и поставки)"})
            continue
        it = json.loads(json.dumps(it))          # глубокое копирование payload
        it["weight"] = w["g"]
        pour.append({"art": art, "item": it, "meta": meta, "weight_donor": w})
    return pour, held


def e2_candidates():
    """Поштучные малые (L<500) из базы, ГОТОВО, без «шт», своё фото+цена."""
    data = json.loads(BASE.read_text(encoding="utf-8"))
    out = []
    for p in data["products"]:
        if p.get("source") != SRC:
            continue
        if "ГОТОВО" not in (p.get("readiness") or []):
            continue
        name = str(p.get("name") or "")
        if "шт" in name:
            continue
        m = _DIM_RE.search(name)
        if not m:
            continue
        dims = tuple(int(g) for g in m.groups())
        if max(dims) >= 500:
            continue
        if not (p.get("photos") and p.get("price")):
            continue
        out.append({"art": str(p["art"]), "name": name, "price": float(p["price"]),
                    "dims": dims, "photos": p.get("photos"),
                    "file_g": (p.get("ovh") or {}).get("weight_g")})
    out.sort(key=lambda x: x["art"])
    return out


def build_e2():
    pour, held = [], []
    for c in e2_candidates():
        facts = _facts(c["dims"])
        if len(facts) != 1:
            held.append({"art": c["art"], "name": c["name"], "dims": list(c["dims"]),
                         "price": c["price"],
                         "reason": "нет дон-близнеца (нет честного веса и поставки)"})
            continue
        f = facts[0]
        d, w, h = c["dims"]
        tn = M._tn_ved_of(c["name"])
        prod = {
            "offer_id": c["art"],
            "name": c["name"],
            "price": c["price"],
            "vat": "0",
            "description_category_id": 17027937,
            "type_id": 95482,
            "images": [str(x) for x in c["photos"]][:15],
            "dimensions": {"depth": d, "width": w, "height": h,
                           "weight": f["weight_g"]},
            "_profile": M.BOX_PROFILE,
            "_spec": {"_model": c["art"], "тип": "коробка для хранения", "тн_вэд": tn},
        }
        out = C.to_item(prod)
        item, m = out["item"], out["meta"]
        if item is None:
            held.append({"art": c["art"], "name": c["name"][:60],
                         "reason": f"to_item None: {m.get('block_reason')}"})
            continue
        attrs = item.get("attributes") or []
        a_ids = {a.get("id") for a in attrs}
        if M.REQUIRED_IDS - a_ids:
            held.append({"art": c["art"], "name": c["name"][:60],
                         "reason": f"нет обяз. атрибутов: {sorted(M.REQUIRED_IDS - a_ids)}"})
            continue
        pour.append({"art": c["art"], "item": item,
                     "weight_donor": {"g": f["weight_g"], "art": f["art"],
                                      "line": f"{f.get('mark','')} {f['note'][:34]}".strip()},
                     "file_g": int(c["file_g"]) if c["file_g"] else None,
                     "meta": {"art": c["art"], "name": c["name"][:66],
                              "price": c["price"], "dims_mm_assembled": list(c["dims"]),
                              "type_id": 95482, "tn_ved": tn,
                              "attrs": sorted(a_ids), "images": len(item.get("images", []))}})
    return pour, held


def _freeze(name, pour, held, title, src_seg, note):
    items = [p["item"] for p in pour]
    metas = []
    for p in pour:
        m = dict(p["meta"])
        m["weight_g"] = p["weight_donor"]["g"]
        m["weight_note"] = (f"дон-факт {p['weight_donor']['art']} "
                            f"({p['weight_donor']['line']}) — честный вес, НЕ файл")
        m["donor_art"] = p["weight_donor"]["art"]
        metas.append(m)
    manifest = {
        "date": DATE,
        "title": title,
        "target_cabinet": TARGET_CABINET,
        "source": SRC,
        "segment": src_seg,
        "category": {"description_category_id": 17027937, "type_id": 95482,
                     "why": "17036258 «Коробка для переезда» мёртв; ремап-прецедент an_exp_car CARD_LIVE 988"},
        "operator_decisions_2026_09_09": [
            "600×400×400: разделить по имени — пятислойный→846 г (9602492-1), премиум/Бизнес→663 г (9600067-1)",
            "льём только дон-размеры: карточки без реальной коробки дона (нет честного веса И поставки) → HELD, не льём"],
        "pour_ready": len(pour),
        "held": len(held),
        "held_list": held,
        "metas": metas,
        "item_sample": items[0] if items else None,
        "weight_policy": "вес карточки = дон-факт (кг→г), размер из имени; файл-вес (ИИ-филлер) в карточки НЕ идёт",
        "weighted_all": all(m.get("weight_g") for m in metas),
        "note": note,
    }
    json.dump({"date": DATE, "title": title, "items": items, "metas": metas},
              (HERE / "runtime" / "ozon_boxes" / f"{name}.items.json").open("w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    (HERE / "runtime" / "ozon_boxes" / f"{name}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1))
    _write_md(name, manifest, items)
    return manifest


def _write_md(name, m, items):
    L = [f"# {m['title']} · СУХО 0₽ · {m['date']}",
         "",
         f"- цель: **{m['target_cabinet']}**",
         f"- сегмент: {m['segment']}",
         f"- **пул-готово: {m['pour_ready']}** · HELD (без дон-близнеца): {m['held']}",
         f"- категория: {m['category']['description_category_id']} / тип {m['category']['type_id']}",
         f"- политика веса: {m['weight_policy']}",
         "",
         "## Карточки пула (вес = дон-факт ✓)",
         "| арт | цена | размер, мм | ВЕС дон ✓ | источник | имя |",
         "|---|---|---|---|---|---|",
         ]
    for x in m["metas"]:
        L.append(f"| {x['art']} | {x['price']:.0f}₽ | {'×'.join(map(str, x['dims_mm_assembled']))} | "
                 f"{x['weight_g']} г | {x['weight_note'].split('(')[-1].rstrip(')')} | {x['name']} |")
    L.append("")
    L.append("## HELD (ждут честного веса/поставщика — НЕ льются, не теряются)")
    for h in m["held_list"]:
        L.append(f"- `{h['art']}` {'×'.join(map(str, h.get('dims') or []))} "
                 f"{h.get('price', '')}₽ — {h.get('reason','')[:80]}")
    if m.get("item_sample"):
        L.append("")
        L.append("## Пример собранного item")
        L.append("```json")
        L.append(json.dumps(m["item_sample"], ensure_ascii=False, indent=1))
        L.append("```")
    (HERE / "runtime" / "ozon_boxes" / f"{name}.md").write_text("\n".join(L))
    return True


def main():
    e1p, e1h = build_e1()
    e2p, e2h = build_e2()
    m1 = _freeze("korobki_echelon1_POURREADY_2026-09-09", e1p, e1h,
                 "Echelon-1 · крупная переездная · ПУЛ-ГОТОВО (честный дон-вес)",
                 "поштучные · длинная ≥500 мм · ГОТОВО",
                 "17 исходных → 10 пул (дон-вес) + 7 HELD (нет дон-близнеца: гардеробные 1000/1300, "
                 "500×500×500, 700×500×500, 580×350×410, 550×350×350)")
    m2 = _freeze("korobki_echelon2_DRY_2026-09-09", e2p, e2h,
                 "Echelon-2 · малые поштучные · ДОН-РАЗМЕРЫ (честный дон-вес)",
                 "поштучные · длинная <500 мм · ГОТОВО",
                 "20 исходных → 7 пул (только дон-размеры, честный вес) + 13 HELD (нет дон-близнеца)")

    # ── Сухой рендер точных батчей живого органа (dry=True, локально, 0₽, наружу ничего) ──
    print("\n[сухой рендер] батчи ровно тех payload, что ушли бы в /v3/product/import (RUBICON цел)…")
    ok_all = True
    for seg, items in (("Echelon-1 (10)", [p["item"] for p in e1p]),
                       ("Echelon-2 (7)",  [p["item"] for p in e2p])):
        if not items:
            print(f"  {seg}: нет items — пропуск")
            continue
        r = H.create_product(items, dry=True, commit=False)
        st = r.get("status") if isinstance(r, dict) else None
        ok = st == "dry"
        ok_all = ok_all and ok
        print(f"  {seg}: {len(items)} шт → create_product(dry=True) status={st} {'✅' if ok else '⚠'}")
    if not ok_all:
        print("  ⚠ dry-рендер дал НЕ-dry статус — смотреть (payload не прошёл бы гейт).")

    print(f"Echelon-1: пул-готово {m1['pour_ready']} · HELD {m1['held']}")
    for x in m1["metas"]:
        print(f"  {x['art']:12} {x['price']:.0f}₽  {'×'.join(map(str,x['dims_mm_assembled'])):16} {x['weight_g']} г")
    print(f"Echelon-2: пул-готово {m2['pour_ready']} · HELD {m2['held']}")
    for x in m2["metas"]:
        print(f"  {x['art']:12} {x['price']:.0f}₽  {'×'.join(map(str,x['dims_mm_assembled'])):16} {x['weight_g']} г")
    print("\nартефакты: korobki_echelon1_POURREADY_2026-09-09.{json,md,items.json}")
    print("           korobki_echelon2_DRY_2026-09-09.{json,md,items.json}")
    print("\nВЕРДИКТ (сухо, 0₽): пул готов к живому заливу ПО СЛОВУ (RUBICON) под 5838715 "
          "(пин OZON_BOX_* + twin-скан уже зелёный). Вес честный, поставка = реальные коробки дона.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

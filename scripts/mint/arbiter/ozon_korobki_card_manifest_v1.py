#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · КОРОБКИ · ЖИВОЙ МАНИФЕСТ КАРТОННОЙ ГРУППЫ (Шаг к заливу 986, RUBICON дан).

Оператор 08.09: «986 картонных сейчас, 314 на паузу» (по вопросу о ТН ВЭД/материале).
Материал известен только для 950ч3 (донор col33 «Материал»=Картон, 202 из 204 resolved)
и из ИМЕНИ (для 1700ч донор col33 ПУСТ у всех). Детерминированное правило:

    КАРТОН = (source 950ч3: донор-материал «Картон»)  ∪  (имя содержит картон-сигнал)
    ПАУЗА  = остальное resolved-ядро (текстиль/пластик по имени, или имя молчит)

Навешивает на каждую картонную строку ПРОФИЛЬ категории + _spec, чтобы карточка прошла
живой import со ВСЕМИ 5 обязательными атрибутами (85/9048/8229/23536/22232):
  • prod['_profile'] = BOX_PROFILE   (attr_constants бренд+маркировка, attr_specs модель,
                                      attr_enums тип + тн_вэд) — dvid ТОЛЬКО из живых словарей
  • prod['_spec']     = {_model: art(анти-склейка), тип: <имя типа из строки>,
                         тн_вэд: <код по сигналу имени>}
Строит items и ДЕЛАЕТ СУХОЙ create_product батчами ≤100 (0₽). Живой commit — отдельным органом.

Честно: 200≠успех; dry-манифест показывает attributes[] на предметах; нужно ПОСМОТРЕТЬ, что
каждая карточка несёт id 85/9048/8229/23536/22232, прежде чем живой шаг. Не выдумываем dvid:
тип Коробка=95482/Корзина=95481 (dvid==type_id из живого /attribute/values dict 1960),
ТН ВЭД гофр 4819100000=971398212, складной 4819200000=971398213 (dict 124412395).

Артефакт: runtime/ozon_boxes/korobki_CARD_LIVE_<DATE>.{json,md}   (манифест 982/986 + рендер)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ozon_card_v1 as C           # noqa: E402
import ozon_hands_write_v1 as H    # noqa: E402

DATE = "2026-09-09"
BASE = HERE / "runtime" / "ozon_boxes" / "ozon_korobki_base_2026-09-08.json"
DONOR_950 = "/Users/wavysexy/Downloads/ready/WIP/ИП Анна/Озон ЗАЛИТЬ/Коробки 950 шт ч3.xlsx"
OUT_JSON = HERE / "runtime" / "ozon_boxes" / f"korobki_CARD_LIVE_{DATE}.json"
OUT_MD = HERE / "runtime" / "ozon_boxes" / f"korobki_CARD_LIVE_{DATE}.md"
# Замороженные предметы для ЖИВОГО шага (живой орган льёт ровно эти payload'ы, без пересборки).
OUT_ITEMS = HERE / "runtime" / "ozon_boxes" / f"korobki_CARD_LIVE_{DATE}.items.json"

CREATE_BATCH = 100
HOUSE_BRAND = "ExpressGo"

# Картон-сигналы имени (для 1700ч, где донор-материал пуст). Порядок: гофр-сигнал отдельно ниже.
_CARD_SIG = ("картон", "самосбор", "самосборочн", "крафт", "складн", "клапан", "гофр")
# Заведомо ЖЁСТКИЙ картон по смыслу (без слова «картон»): переездные/архивные/почтовые коробки и
# Т-марки гофрокартона (Т21-Т25/Т30-Т32 — ГОСТ). Это те же сигналы, что _GOFR_SIG тянет в код
# 4819100000; если имя уже «гофр»-решил для ТН ВЭД — это картон и для членства (раньше НЕ совпадало).
_RIGID_SIG = ("переезд", "архив", "почтов", "т21", "т22", "т23", "т24", "т25",
              "т30", "т31", "т32", "т21с", "т22с", "т23с", "т24с", "т25с")
_TEXTILE_SIG = ("ткань", "текстиль", "полиэстер", "нейлон", "брезент", "тканев",
                "хлопк", "льнян", "джинс", "велюр", "рогожк")
_PLASTIC_SIG = ("пластик", "полипропилен", "пластмасс")
# 4819100000 = ящики/коробки из ГОФРИРОВАННОЙ бумаги/картона (несущие: переезд, архив, почтовые,
# гофрокороба, марки гофрокартона Т21-Т25/Т30-Т32). 4819200000 = складные из НЕгофрированной
# (тонкие самосборные/подарочные/декор-хранения). Сигнал гофра тянем из прочности/несущих слов.
_GOFR_SIG = ("гофр", "трехслой", "трёхслой", "микрогофр",
             "т21", "т22", "т23", "т24", "т25", "т30", "т31", "т32", "т-2", "т-3",
             "переезд", "архив", "почтов", "упаковоч", "клапан", "набор для переезд",
             "гофрокороб", "гофроящик", "трёхслойн", "трехслойн", "курьер", "маркетплейс")

# ── ПРОФИЛЬ: 5 обязательных атрибутов категории «Коробка для хранения» ───────────
TN_VED = {  # dict 124412395, живые dvid (09.09)
    "4819100000": 971398212,   # ящики/коробки из гофрированной бумаги/картона
    "4819200000": 971398213,   # складные из негофрированной
}
BOX_PROFILE = {
    "attr_constants": {
        "бренд":      {"id": 85,    "value": HOUSE_BRAND},
        "маркировка": {"id": 23536, "value": "false"},
    },
    "attr_specs": {
        "модель":     {"id": 9048, "from": "_model"},
    },
    "attr_enums": {
        "тип":    {"id": 8229, "values": {"коробка для хранения": 95482,
                                          "корзина для хранения": 95481}},
        "тн_вэд": {"id": 22232, "values": TN_VED},
    },
}
REQUIRED_IDS = {85, 9048, 8229, 23536, 22232}


def _load():
    data = json.loads(BASE.read_text(encoding="utf-8"))
    ready = [p for p in data["products"] if "ГОТОВО" in (p.get("readiness") or [])]
    core_sources = {"ИП Анна/Озон ЗАЛИТЬ/Коробки 1700 штук озон .xlsx",
                    "ИП Анна/Озон ЗАЛИТЬ/Коробки 950 шт ч3.xlsx"}
    core = [p for p in ready if p.get("source") in core_sources
            and str(p.get("dci")) == "17027937"
            and p.get("type") in ("Коробка для хранения", "Корзина для хранения")]
    return core


def _donor_material_950():
    """source 950ч3: прочитать col33 «Материал» (art→материал). Один проход, надёжно."""
    try:
        import openpyxl
    except Exception as e:  # pragma: no cover
        print(f"  ⚠ openpyxl недоступен: {e} — донор-материал 950 не читается")
        return {}
    wb = openpyxl.load_workbook(DONOR_950, read_only=True, data_only=True)
    ws = wb.active
    out = {}
    for r in ws.iter_rows(min_row=4, values_only=True):
        art = r[1]
        if art is None:
            continue
        key = str(art).strip().lower()
        mat = str(r[33]).strip() if len(r) > 33 and r[33] is not None else ""
        if key.startswith("введите артикул"):
            continue
        out[key] = mat
    return out


def _has(name, sigs):
    n = str(name).lower()
    return any(s in n for s in sigs)


def classify(core, donor_mat):
    """Вернуть (cardboard, paused), каждый элемент = исходная строка + разметка."""
    cardboard, paused = [], []
    for p in core:
        art = str(p["art"]).strip().lower()
        name = str(p["name"])
        tag = {"art": p["art"], "name": name, "price": p.get("price"),
               "type": p.get("type"), "source": p.get("source")}
        dm = donor_mat.get(art, "")
        # донор прямо сказал материал (950ч3)
        if dm and "картон" in dm.lower():
            tag["material_how"] = "донор-Картон"
            cardboard.append(tag)
            continue
        if dm and _has(name, _TEXTILE_SIG + _PLASTIC_SIG):
            pass  # донор не-картон → ниже по имени
        # текстиль/пластик по имени — пауза (не картон)
        if _has(name, _TEXTILE_SIG):
            tag["material_how"] = "текстиль-имя"
            paused.append(tag); continue
        if _has(name, _PLASTIC_SIG):
            tag["material_how"] = "пластик-имя"
            paused.append(tag); continue
        # картон по имени (слово «картон»/самосбор/крафт/складн/клапан/гофр)
        if _has(name, _CARD_SIG):
            tag["material_how"] = "картон-имя"
            cardboard.append(tag)
            continue
        # заведомо жёсткий картон ПО СМЫСЛУ: переездные/архивные/почтовые коробки, Т-марки
        # гофрокартона (Т23С = ГОСТ-марка гофрированного картона) — те же сигналы, что _GOFR_SIG
        # тянет в код 4819100000; фото НЕ нужно, имя уже говорит «жёсткая картонная коробка».
        if _has(name, _RIGID_SIG) or (_has(name, "упаковк") and not _has(name, "в упаковке")):
            tag["material_how"] = "жёсткий-картон-имя"
            cardboard.append(tag)
            continue
        # донор сказал что-то иное или имя молчит
        tag["material_how"] = ("донор-не-картон" if dm else "имя-молчит")
        paused.append(tag)
    return cardboard, paused


def _tn_ved_of(name):
    """Честный выбор кода по имени: гофр-сигнал/марки Т21-Т25 (это гофрокартон) → 4819100000;
    остальные «картон складной/самосборный/крафт» → 4819200000 (негофр складной)."""
    return "4819100000" if _has(name, _GOFR_SIG) else "4819200000"


def _to_prod(row, type_id):
    """row(cardboard-тег) → prod для to_item. Габариты из базовой строки мы НЕ храним в теге —
    перечитываем по art из core. Возвращает prod|None."""
    return row  # не используется напрямую — см. сборку в main


def build_items(cardboard):
    """cardboard: [{art,name,price,type,material_how}] → items c attributes[] + мета.
    Габариты/фото тянем из полной строки базы (по art)."""
    by_art = {str(c["art"]).strip().lower(): c for c in cardboard}
    # габариты и фото из исходной строки базы
    core = _load()
    full = {str(p["art"]).strip().lower(): p for p in core}
    items, metas, skipped = [], [], []
    for c in cardboard:
        key = str(c["art"]).strip().lower()
        src = full.get(key)
        if src is None:
            skipped.append({"art": c["art"], "reason": "нет в базе"})
            continue
        ovh = src.get("ovh") or {}
        dims = {}
        ok = True
        for src_k, dim_k in (("d_mm", "depth"), ("w_mm", "width"),
                             ("h_mm", "height"), ("weight_g", "weight")):
            try:
                v = float(ovh.get(src_k))
            except (TypeError, ValueError):
                ok = False; break
            if not (v > 0):
                ok = False; break
            dims[dim_k] = v
        if not ok:
            skipped.append({"art": c["art"], "reason": f"нет ОВХ {src_k}"})
            continue
        type_id = 95482 if c["type"] == "Коробка для хранения" else 95481
        tn = _tn_ved_of(c["name"])
        prod = {
            "offer_id": str(c["art"]),
            "name": str(c["name"]),
            "price": float(c["price"]),
            "vat": "0",
            "description_category_id": 17027937,
            "type_id": type_id,
            "images": [str(x) for x in (src.get("photos") or []) if x][:15],
            "dimensions": dims,
            "old_price": float(c["price"]) + 500,
            "_profile": BOX_PROFILE,
            "_spec": {"_model": str(c["art"]), "тип": str(c["type"]), "тн_вэд": tn},
        }
        try:
            out = C.to_item(prod)
        except C.CardError as e:
            skipped.append({"art": c["art"], "reason": f"CardError: {e}"})
            continue
        m = out["meta"]
        if out["item"] is None:
            skipped.append({"art": c["art"], "reason": f"to_item None: {m.get('block_reason')}"})
            continue
        attrs = out["item"].get("attributes") or []
        a_ids = {a.get("id") for a in attrs}
        miss = REQUIRED_IDS - a_ids
        if miss:
            skipped.append({"art": c["art"], "reason": f"нет обязательных атрибутов: {sorted(miss)}"})
            continue
        items.append(out["item"])
        metas.append({"art": c["art"], "name": c["name"][:70], "price": m["price"],
                      "tn_ved": tn, "type_id": type_id, "material_how": c["material_how"],
                      "attrs": sorted(a_ids), "images": len(out["item"].get("images", [])),
                      "offer_id_truncated": m.get("offer_id_truncated")})
    return items, metas, skipped


def main():
    print(f"артефакт: {BASE.name}")
    core = _load()
    print(f"resolved core (1700ч+950ч3, тип жив): {len(core)}")
    donor_mat = _donor_material_950()
    print(f"донор-материал 950ч3 прочитан: {len(donor_mat)} артов")
    cardboard, paused = classify(core, donor_mat)
    print(f"КАРТОН: {len(cardboard)}   ПАУЗА: {len(paused)}")
    how = Counter(c["material_how"] for c in cardboard)
    print("  картон по:", dict(how))
    pw = Counter(c["material_how"] for c in paused)
    print("  пауза по:", dict(pw))

    # цены картонной группы: не выше ли где-то слишком низко
    prices = sorted(float(c["price"]) for c in cardboard)
    print(f"  цена мин={prices[0]:.0f} медиана={prices[len(prices)//2]:.0f} макс={prices[-1]:.0f}")

    items, metas, skipped = build_items(cardboard)
    print(f"собрано item: {len(items)} · пропущено: {len(skipped)}")
    for s in skipped[:8]:
        print("  skip:", s["art"], "—", s["reason"][:80])
    tn_count = Counter(m["tn_ved"] for m in metas)
    print(f"ТН ВЭД в собранных: {dict(tn_count)}")

    # сухой рендер батчами
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

    manifest = {
        "date": DATE,
        "scope": "картонная группа resolved-ядра коробок (оператор: «986 картонных сейчас»)",
        "core_total": len(core),
        "cardboard": len(cardboard),
        "paused": len(paused),
        "cardboard_how": dict(how),
        "paused_how": dict(pw),
        "items_built": len(items),
        "items_skipped": len(skipped),
        "skipped_sample": skipped[:20],
        "tn_ved": dict(tn_count),
        "batches": batches,
        "dry_ok": dry_ok,
        "price_min": prices[0], "price_median": prices[len(prices)//2], "price_max": prices[-1],
        "metas_sample": metas[:5],
        "item_sample": items[0] if items else None,
        "required_ids": sorted(REQUIRED_IDS),
        "paused_list": [{"art": c["art"], "name": c["name"][:70], "price": c["price"],
                         "how": c["material_how"]} for c in paused],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    _write_md(manifest)
    OUT_ITEMS.write_text(json.dumps({"date": DATE, "items": items, "metas": metas},
                                    ensure_ascii=False, indent=1))
    print(f"\nманифест: {OUT_JSON.name} (+md)")
    print(f"замороженные items ({len(items)}): {OUT_ITEMS.name}")
    print("\nВЕРДИКТ (сухой, 0₽):")
    print(f"  картон {len(cardboard)} (пауза {len(paused)}), собрано item {len(items)}"
          f" (skip {len(skipped)}), dry-батчей {len(batches)} ok={dry_ok}")
    print("  к живому заливу: отдельный орган --commit, дозы ≤100, poll import_info, verify витрины.")
    return 0


def _write_md(m):
    L = [f"# ОЗОН КОРОБКИ · ЖИВОЙ МАНИФЕСТ КАРТОН {m['date']}",
         "",
         f"- resolved core: **{m['core_total']}** (1700ч + 950ч3)",
         f"- **КАРТОН: {m['cardboard']}** · ПАУЗА: {m['paused']}",
         f"- картон по: {m['cardboard_how']}",
         f"- пауза по: {m['paused_how']}",
         f"- собрано item: {m['items_built']} · skip: {m['items_skipped']}",
         f"- ТН ВЭД: {m['tn_ved']}",
         f"- цена: мин {m['price_min']:.0f} / мед {m['price_median']:.0f} / макс {m['price_max']:.0f}",
         f"- dry-батчи: {m['batches']} · dry_ok={m['dry_ok']}",
         "",
         "## ПАУЗА (не льём сейчас)",
         ]
    for c in m["paused_list"]:
        L.append(f"- `{c['art']}` {c['name']} · {c['price']}₽ · {c['how']}")
    L.append("")
    L.append("## Пример собранного item (attributes[] целиком)")
    it = m.get("item_sample")
    if it:
        L.append("```json")
        L.append(json.dumps(it, ensure_ascii=False, indent=1))
        L.append("```")
    OUT_MD.write_text("\n".join(L))
    return True


if __name__ == "__main__":
    raise SystemExit(main())

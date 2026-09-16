#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН КОРОБКИ · Echelon-1 · TWIN-СКАН ЦЕЛЕВОГО КАБИНЕТА 5838715 (0₽ чтение).

СУХОЙ шаг перед живым заливом Echelon-1 (оператор: «далее» → веду план сухими/read-only
шагами; слово (RUBICON) на запись не дано). Проверяет ПОД ЦЕЛЕВЫМ кабинетом:
  1) ключи OZON_BOX_* валидны (Client-Id = 5838715, НЕ старый 5473485);
  2) НИ ОДИН из 17 артов an_ex_c_* (Echelon-1, заморожен korobki_echelon1_DRY_2026-09-09)
     ещё НЕ живёт на витрине 5838715 (twin-гард: уже-живое НЕ пересоздаём);
  3) склады кабинета (источник warehouse_id для будущего set_stock — не выдумываем).

Пин в ПРОЦЕССЕ: после ensure_env() явно переназначаем OZON_CLIENT_ID/OZON_API_KEY из
OZON_BOX_* (уже заданное окружение у env-loader имеет приоритет, поэтому ставим сами).
Значения ключей НИКОГДА не печатаются — наружу только последние цифры Client-Id (не секрет,
кабинет уже назван в манифесте) и факты витрины.

Артефакт: runtime/ozon_boxes/korobki_echelon1_TWINSCAN_<DATE>.{json,md}
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))          # SOCC/scripts/mint

import ozon_hands_write_v1 as H               # noqa: E402  (read_shelf/warehouse_list)

DATE = date.today().isoformat()
ITEMS_JSON = HERE / "runtime" / "ozon_boxes" / "korobki_echelon1_DRY_2026-09-09.items.json"
OUT_JSON = HERE / "runtime" / "ozon_boxes" / f"korobki_echelon1_TWINSCAN_{DATE}.json"
OUT_MD = HERE / "runtime" / "ozon_boxes" / f"korobki_echelon1_TWINSCAN_{DATE}.md"

TARGET_TAIL = "8715"                          # 5838715 — целевой кабинет «OZON Express Box»
OLD_TAIL = "3485"                             # 5473485 — старый кабинет, НЕ пишем


def _pin_box_creds():
    """Переназначить OZON_* из OZON_BOX_* в процессе. Вернуть tail Client-Id (не секрет)."""
    import socc_mint_env_v1 as env
    env.ensure_env()
    bc = os.getenv("OZON_BOX_CLIENT_ID")
    bk = os.getenv("OZON_BOX_API_KEY")
    if not (bc and bk):
        raise RuntimeError("OZON_BOX_CLIENT_ID/OZON_BOX_API_KEY нет в env — twin-скан кабинета 5838715 невозможен")
    os.environ["OZON_CLIENT_ID"] = bc
    os.environ["OZON_API_KEY"] = bk
    return str(bc)


def main():
    tail = _pin_box_creds()
    print(f"[пин] BOX-ключи → Client-Id …{tail[-4:]} "
          + ("✅ целевой 5838715" if tail[-4:] == TARGET_TAIL else f"⚠ НЕ целевой (ожидали …{TARGET_TAIL})"))
    if tail[-4:] != TARGET_TAIL:
        print("ОТКАЗ: ключи смотрят не на целевой кабинет — не читаем чужой кабинет.")
        return 2

    items_d = json.loads(ITEMS_JSON.read_text(encoding="utf-8"))
    offer_ids = [str(i["offer_id"]) for i in items_d.get("items", [])]
    print(f"замороженных item Echelon-1: {len(offer_ids)}")

    # 2) twin-гард: читаем витрину 5838715 по 17 артам
    print("\n[twin-гард] витрина кабинета 5838715 (0₽ read_shelf)…")
    r = H.read_shelf(offer_ids)
    if not r.get("ok"):
        print("  ОТКАЗ: чтение витрины упало:", r.get("_error"))
        return 2
    cards = r.get("cards", [])
    live, not_live = [], []
    for c in cards:
        oid = str(c.get("offer_id"))
        if c.get("product_id") not in (None, 0):
            live.append({"offer_id": oid, "product_id": c.get("product_id"),
                         "visible": c.get("visible"), "moderation": c.get("moderation")})
        else:
            not_live.append(oid)
    # read_shelf может не вернуть карточку вовсе (нет товара) — это тоже «не живёт»
    found = {str(c.get("offer_id")) for c in cards}
    absent = [o for o in offer_ids if o not in found]
    print(f"  уже-жив (НЕ пересоздаём): {len(live)} · пусто/нет карточки: {len(not_live) + len(absent)}")
    if live:
        for x in live[:20]:
            print("   🔴", x)
        print("  ⚠ twin-конфликт: арты уже живут в 5838715 — живой залив этих артов ОТМЕНЯЕТСЯ (не пересоздаём).")
    else:
        print("  ✅ twin-чисто: ни один арт Echelon-1 не живёт в целевом кабинете — можно заливать (по слову).")

    # 3) склады кабинета (для будущего set_stock)
    print("\n[склады] кабинета 5838715 (0₽ /v2/warehouse/list)…")
    w = H.warehouse_list()
    whs = []
    if w.get("ok"):
        whs = [{"id": x.get("warehouse_id"), "name": x.get("name")} for x in w.get("warehouses", [])]
        print(f"  складов: {len(whs)}" + ("" if whs else " (FBS-складов нет — остатки ставить некуда)"))
        for x in whs[:20]:
            print("   •", x["id"], x["name"])
    else:
        print("  ⚠ чтение складов упало:", w.get("_error"))

    twin_clean = len(live) == 0
    manifest = {
        "date": DATE,
        "target_cabinet": "OZON Express Box · client 5838715 (creds OZON_BOX_*, пин подтверждён)",
        "client_id_tail": tail[-4:],
        "twin_clean": twin_clean,
        "already_live": live,
        "checked": len(offer_ids),
        "not_live_count": len(not_live) + len(absent),
        "warehouses": whs,
        "frozen_items": ITEMS_JSON.name,
        "verdict": ("twin-чисто под 5838715 — живой залив по слову оператора (RUBICON) "
                    "готов к исполнению; вес карточек остаётся ГЕЙТОМ (см. Echelon-1 DRY)")
                    if twin_clean else "⚠ twin-конфликт — живой залив этих артов не делать",
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    _write_md(manifest)
    print(f"\nартефакт: {OUT_JSON.name} (+md)")
    print("\n──────── ВЕРДИКТ (read-only, 0₽) ────────")
    print(f"  кабинет …{tail[-4:]} ✅ целевой · twin-чисто={twin_clean} "
          f"(уже-жив {len(live)} из {len(offer_ids)}) · складов {len(whs)}")
    print("  Живой залив Echelon-1 — ТОЛЬКО по слову (RUBICON) и после решения по ВЕСУ карточек.")
    return 0


def _write_md(m):
    L = [f"# ОЗОН КОРОБКИ · Echelon-1 · TWIN-СКАН КАБИНЕТА 5838715 · {m['date']} · 0₽",
         "",
         f"- целевой кабинет: {m['target_cabinet']}",
         f"- frozen: {m['frozen_items']}",
         f"- проверено артов: {m['checked']} · уже-жив: {len(m['already_live'])}",
         f"- **twin-чисто: {m['twin_clean']}**",
         ]
    if m["already_live"]:
        L.append("")
        L.append("## Уже живут в 5838715 (не пересоздаём)")
        for x in m["already_live"]:
            L.append(f"- 🔴 `{x['offer_id']}` product_id={x['product_id']}")
    L.append("")
    L.append("## Склады кабинета (для будущего set_stock)")
    if m["warehouses"]:
        for x in m["warehouses"]:
            L.append(f"- `{x['id']}` {x['name']}")
    else:
        L.append("- FBS-складов нет")
    L.append("")
    L.append(m["verdict"])
    OUT_MD.write_text("\n".join(L))
    return True


if __name__ == "__main__":
    raise SystemExit(main())

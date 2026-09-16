#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Приёмка GATE-PERSISTENCE (04.09, 4 правки канала, 0₽, без сети).

Правка B — score_item passthrough несёт barcode/dims_source/dims_cached/_platform_residue (провенанс
не срезается на строке категорийщика; durable воспроизводим между снимками).
Правка C — uniqueizer.platform_residue: флаг чужого МП в имени (FLAG ONLY, без «wb/вб» ложных);
zaliv _map_live_row ставит _platform_residue на строку живого скана.
Правка A — _stamp_write_meta зеркалит write-EAN (gen_ean13, единый источник) + провенанс с products
назад на строки шорт-листа: durable несёт честный barcode (не «UNKNOWN»).
Правка D — twin-gate: готовый SKU == donor_pid живой карточки goods_library → dubl_live (ФЛАГ).

Все входы — локальные фикстуры (швы), сеть и файлы канона не трогаем. Внешние чтения в twin-gate
заменяем инъекцией doc. Всё честно: поле НЕТ = не флаг, не выдумываем.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # scripts/mint/arbiter

import uniqueizer_v1 as uq                     # noqa: E402
import ymarket_role_categorist_v1 as categorist  # noqa: E402
import ymarket_runner_v1 as runner             # noqa: E402  реальный продюсер канала (0₽, без сети)
import ymarket_zaliv_source_v1 as zaliv         # noqa: E402
import ymarket_twin_gate_v1 as twin              # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    if not cond:
        print(f"  FAIL: {label}")
        sys.exit(1)
    PASS += 1
    print(f"  ok: {label}")


# ── Правка B: score_item переносит провенанс ─────────────────────────────────────────────
print("[B] score_item passthrough несёт провенанс")
item = {
    "sku": "901", "name": "Плёнка тестовая 0,3×100 м", "cost": 0,   # cost=0 → needs_data рано
    "barcode": "2991234567890", "dims_source": "physics",
    "dims_cached": True, "_platform_residue": "ozon",
    "category": "Упаковка", "slug": "streich-plenka",
}
out = categorist.score_item(item)
for k in ("barcode", "dims_source", "dims_cached", "_platform_residue"):
    ok(out.get(k) == item[k], f"score_item сохранил {k}={item[k]!r}")
ok(out["verdict"] == "needs_data", "ранний needs_data не сломал перенос провенанса")
bare = {"sku": "902", "name": "X", "cost": 0}
out2 = categorist.score_item(bare)
ok("barcode" not in out2, "нет barcode на входе → ключа нет (не выдумываем)")

# ── Правка C: платформенный флаг ─────────────────────────────────────────────────────────
print("[C] uniqueizer.platform_residue + _map_live_row флаг")
ok(uq.platform_residue("Стрейч плёнка для упаковки заказов Ozon") == "ozon", "латиница ozon")
ok(uq.platform_residue("Скотч для ОЗОН") == "озон", "кириллица ОЗОН")
ok(uq.platform_residue("Лента клейкая для Wildberries") == "wildberries", "wildberries")
ok(uq.platform_residue("Диспенсер-ручка для стрейч плёнки пластиковый") is None,
   "имя с «для» без платформы → None (не ложный флаг)")
ok(uq.platform_residue("Плёнка 500мм 23мкм 2кг") is None, "чистое имя → None")
# граница слова: хим. озон ≠ маркетплейс OZON (ложные срабатывания короткого токена)
ok(uq.platform_residue("Озоновый генератор воздуха") is None, "«Озоновый» (хим.) → None")
ok(uq.platform_residue("Плёнка озонированная антибактериальная") is None, "«озонированная» (хим.) → None")
ok(uq.platform_residue("Генератор озона промышленный") is None, "«озона» (хим.) → None")
ok(uq.platform_residue("Скотч для OZON-упаковки") == "ozon", "ozon через дефис → флаг (граница по '-' )")
# #9 (аудит): PREFIX-класс ловит склонения однозначных брендов; STRICT-озон остаётся хим.-защищённым
ok(uq.platform_residue("Лента клейкая для маркетплейсов") == "маркетплейс",
   "«маркетплейсов» (род. мн., словоформа) → флаг по началу токена")
ok(uq.platform_residue("Стрейч на алиэкспрессе") == "алиэкспресс",
   "«алиэкспрессе» (предл., словоформа) → флаг")
ok(uq.platform_residue("Плёнка для упаковки в вайлдберриз-стиле") == "вайлдберриз",
   "«вайлдберриз-» через дефис → флаг (начало токена)")
ok(uq.platform_residue("Заказы на озоне упаковываем") is None,
   "«на озоне» (сленг-склонение STRICT) → None: хим.-защита важнее редкой словоформы (документировано)")
ok(uq.platform_residue("Озоновый слой плёнки и маркетплейс") == "маркетплейс",
   "хим. «Озоновый» не мешает флагу честного «маркетплейс» рядом")
row = zaliv._map_live_row({"sku": "19946", "name": "Стрейч для Ozon 500мм",
                           "cost": 10}, "streich-plenka", 76346336)
ok(row.get("_platform_residue") == "ozon", "_map_live_row поставил флаг (Ozon)")
row2 = zaliv._map_live_row({"sku": "19946", "name": "Стрейч плёнка белая 500мм 23мкм 2кг 1сорт",
                            "cost": 10}, "streich-plenka", 76346336)
ok("_platform_residue" not in row2, "чистое имя → ключа нет (флаг только при находке)")

# ── Правка A: _stamp_write_meta зеркалит write-EAN (реальный продюсер) ──────────────────────────
print("[A] write-EAN/провенанс/флаг доходят в строки + readiness (реальный shortlist_to_prod)")
row_ok = {"sku": "5273", "name": "Гофролист Т-24 для маркетплейсов", "proposed_low": 265.0,
          "slug": "karton-i-gofrokarton", "length": 80.0, "width": 6.8, "height": 6.8,
          "weight": 0.43, "dims_source": "physics", "dims_cached": True,
          "_platform_residue": "ozon", "barcode": uq.gen_ean13("5273")}
# Строка без партнёра-продюсера (зип короче) не должна получить фантом.
sh = {"schema": "…", "agg": {"selected": 2},
      "shortlist": [dict(row_ok), {"sku": "x", "name": "Без prod", "proposed_low": 1.0}]}
products = [runner.shortlist_to_prod(row_ok)]          # РЕАЛЬНЫЙ продюсер, не фейк-форма
_own = products[0].get("barcode")
ok(_own == uq.gen_ean13("5273"), f"продюсер дал свой EAN {_own} (единый источник own_card_fields)")
ok(products[0].get("_platform_residue") == "ozon", "продюсер пронёс флаг чужой площадки")
ok("dims_source" not in products[0] and "weight" not in products[0],
   "продюсер НЕ выставляет dims/weight верхнеуровнево (их провенанс живёт на строке категорийщика)")
zaliv._stamp_write_meta(sh, products)
r0 = sh["shortlist"][0]
ok(r0.get("barcode") == _own and r0.get("barcode_source") == "own-ean13",
   "зеркало вернуло write-EAN на строку (barcode_source=own-ean13)")
ok(r0.get("dims_source") == "physics" and r0.get("dims_cached") is True,
   "провенанс габаритов НЕ потерян: живёт на строке категорийщика (Правка B), не через зеркало")
ok(r0.get("weight") == 0.43 and r0.get("_platform_residue") == "ozon", "вес/флаг на строке целы")
ok("barcode" not in sh["shortlist"][1], "строка без партнёра (зип короче) не получила фантомный barcode")

# ── Правка A (#1): stamped-строки НЕ умирают в thunk — readiness их проектирует ────────────────
print("[A1] e2e thunk: короткий_лист(реальный прод) → preflight(fake) → readiness несёт write-EAN")

def _fake_preflight(products, slug, cats=None, category_params=None):
    return {"agg": {"total": len(products), "ok": len(products), "build_error": 0,
                    "need_mapping": 0, "no_pictures": 0, "topfill": len(products),
                    "with_specs": 0, "avg_emitted": None, "min_emitted": None},
            "rows": [{"sku": p.get("sku"), "ok": True} for p in products]}

z = zaliv._xlsx_thunk(
    "cargo.xlsx", "karton-i-gofrokarton", city=None, limit=10, max_cost=700.0,
    markup_lo=None, markup_hi=None, cats={},
    shortlist_fn=lambda *a, **k: sh,          # шов: вернуть фикстуру шорт-листа (без xlsx/сети)
    to_prod_fn=runner.shortlist_to_prod,      # РЕАЛЬНЫЙ продюсер канала
    preflight_fn=_fake_preflight,             # шов: не гонять publish_card (герметично)
    load_cats_fn=lambda *a, **k: {})
ok(z["configured"] and z["ready"] == 2, "readiness живая (ready от шов-preflight)")
prov = z.get("shortlist_prov") or []
ok(len(prov) == 2, f"проекция шорт-листа в readiness: {len(prov)} строк (дыра #1 закрыта)")
ok(prov[0].get("barcode") == _own and prov[0].get("barcode_source") == "own-ean13",
   "durable/readiness видит СВОЙ write-EAN (не «UNKNOWN», не пропадает в thunk)")
ok(prov[0].get("dims_source") == "physics" and prov[0].get("_platform_residue") == "ozon",
   "провенанс/флаг в проекции (Правки B+C доехали в durable)")
ok(z.get("residue_skus") == ["5273"], f"residue_skus видит SKU с чужим МП: {z.get('residue_skus')}")
ok("⚑" in zaliv.render(z) and "чужую площадку" in zaliv.render(z),
   "render показывает ⚑-флаг оператору до момента слова")

sh_empty = {"shortlist": []}
zaliv._stamp_write_meta(sh_empty, [])
ok(sh_empty == {"shortlist": []}, "пустой шорт-лист — no-op")
z_empty = zaliv.readiness({}, shortlist_rep=sh_empty)
ok(z_empty["shortlist_prov"] == [] and z_empty["residue_skus"] == [], "пустая проекция — честный []")

# ── Правка D: twin-gate флаг vs donor_pid живых ──────────────────────────────────────────
print("[D] twin-gate: dubl_live против donor_pid goods_library")
lib_doc = {"goods": {
    "ARB-87309612": {"donor_pid": "1588731", "price": 5600, "store_slug": "atlas-express-film",
                     "article": "9605392", "name": "МиниБабл"},
    "ARB-87931769": {"donor_pid": "2050", "price": 520, "store_slug": "atlas-express-film",
                     "article": "9600155", "name": "Компакт"},
}}
live = twin.live_donor_pids(lib_doc)
ok(sorted(live) == ["1588731", "2050"], "live_donor_pids собрал donor_pid живых")
rows = [
    {"offerId": "1588731", "name": "Пузырчатка МиниБабл"},   # = живой → DUBL
    {"offerId": "999999", "name": "Стрейч новый"},            # не живой → ok
]
fl = twin.flag_rows(rows, live=live)
ok(fl[0]["dubl_live"] is True and fl[0]["dubl_evidence"][0]["offer_id"] == "ARB-87309612",
   "готовый SKU == donor_pid живой карточки → dubl_live + evidence")
ok(fl[1]["dubl_live"] is False and "dubl_evidence" not in fl[1], "неживой SKU → dubl_live=False без evidence")
# #4 (аудит): библиотеки живых НЕТ → громкий отказ, НЕ молчаливое «0 дублей» (иначе ложь «не дубль»)
try:
    twin.live_donor_pids(library_path=Path("/nonexistent/nothere_goods_library.json"))
    ok(False, "нет библиотеки живых → должен быть SystemExit (fail-loud)")
except SystemExit:
    ok(True, "нет библиотеки живых → громкий SystemExit (#4: fail-open закрыт)")

print(f"\nGATE-PERSISTENCE: {PASS} проверок, все ок (0₽, без сети).")

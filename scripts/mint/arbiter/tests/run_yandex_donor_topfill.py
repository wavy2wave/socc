#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА ЯНДЕКС — ДОНОР → ТОП-ЗАПОЛНЕНИЕ (сквозной сухой путь, 0₽, без ключа, без openpyxl).

Доказывает ровно планку оператора: «заполняя всевозможные данные, чтобы карточка была реально
охуенно заполнена → в ТОП; ни один товар с ошибкой». Ловит конкретные нарушения:
  • Если движок НЕ эмитит характеристики короба (пустая карточка) → FAIL (D6).
  • Если в карточку уйдёт донорская ЗАКУПКА как цена продажи → FAIL (D5, дропшип-убыток).
  • Если выдумает материал/слои там, где донор их не подтвердил → FAIL (D1/D2/D7, «без фейка»).
  • Если форму КОРОБКИ отправит в ENUM «форма выпуска» (семантика ПЛЁНКИ) → FAIL (D8, ловушка).
  • Если частичные габариты попадут в weightDimensions → FAIL (D5, Маркет отклонит).

ЧИСТАЯ ЛОГИКА: синтетические донор-короба (как их отдал бы read_donor) прогоняются
score_item → shortlist_to_prod → write.publish_card(dry). openpyxl/сеть НЕ трогаются →
зелено под интерпретатором регрессии 3.13. Живой прогон по реальному XLSX — отдельно, под 3.9.6.

Запуск: python3 tests/run_yandex_donor_topfill.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_role_categorist_v1 as cat     # noqa: E402
import ymarket_runner_v1 as runner           # noqa: E402
import ymarket_write_v1 as write             # noqa: E402

PASS, FAIL = [], []

# parameterId'ы подтверждённого профиля kartonnye-koroba (из живого category_parameters).
PID_NAZNACHENIE = 27143691
PID_LEN, PID_WID, PID_HEI = 23674610, 23679910, 14805336
PID_WEIGHT = 23674510
PID_MATERIAL = 17352854
PID_LAYERS = 27144213
PID_FORMA_VYPUSKA = 27141511   # ЛОВУШКА: справочник ПЛЁНКИ (лист/рулон/бобина) — коробу НЕЛЬЗЯ.


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))


def donor_box(cost=60.0, sku="CARGO-1", tip="Трехслойный", material_col="Целлюлоза",
              kolvo=None, dims=(33.0, 23.0, 23.0), weight=0.276,
              marka="Т-23 В", forma="Прямоугольная", obem=96, ruchki="Нет", desc="Прочный короб"):
    """Синтетический короб В ТОМ ВИДЕ, как его отдал бы read_donor: габариты в СМ, вес в КГ,
    _spec собран build_box_spec, описание обогащено — БЕЗ чтения файла (тест чистой логики)."""
    L, W, H = dims
    item = {
        "sku": sku, "name": f"Короб картонный {int(L*10)}х{int(W*10)}х{int(H*10)}", "cost": cost,
        "slug": "kartonnye-koroba", "category_id": 76296786,
        "pictures": ["https://cdn.example/box.jpg"], "stock_source": "donor:в наличии",
        "description": cat.enrich_description(desc, marka=marka, forma=forma, obem=obem,
                                              ruchki=ruchki, kolvo=kolvo),
        "_spec": cat.build_box_spec(length=L, width=W, height=H, weight=weight,
                                    tip_kartona=tip, material_col=material_col, kolvo=kolvo),
    }
    if L and W and H:
        item["length"], item["width"], item["height"] = L, W, H
    if weight:
        item["weight"] = weight
    return item


def emit(prod):
    """prod → dry publish_card → список эмитируемых parameterValues (истинная метрика заполнения)."""
    res = write.publish_card(prod, slug="kartonnye-koroba", dry=True, commit=False)
    cc = res.get("create_card", res)
    return res, cc, runner._emitted_param_values(cc)


print("ПРИЁМКА ЯНДЕКС — ДОНОР → ТОП-ЗАПОЛНЕНИЕ\n")

# ============================================================================
# D1 — материал выводится из КОНСТРУКЦИИ, не выдумывается
# ============================================================================
print("D1 · материал короба из «Тип картона» (конструкция), честный None на незнакомом")
check("D1: 'Трехслойный' → гофрокартон", cat.derive_material("Трехслойный") == "гофрокартон")
check("D1: 'Микрогофрокартон' → гофрокартон", cat.derive_material("Микрогофрокартон") == "гофрокартон")
check("D1: 'Хром-эрзац' → картон (не гофро)", cat.derive_material("Хром-эрзац") == "картон")
check("D1: пусто, но колонка 'Целлюлоза' → целлюлоза (запасной сигнал)",
      cat.derive_material("", "Целлюлоза") == "целлюлоза")
check("D1: незнакомая конструкция → None (не выдумываем valueId)",
      cat.derive_material("нечто", "Макулатура") is None)

# ============================================================================
# D2 — слои только из явного слова слойности
# ============================================================================
print("\nD2 · слои картона только из слова «…слойный», иначе None")
check("D2: 'Пятислойный' → значение проброшено (карта профиля резолвит)",
      cat.derive_layers("Пятислойный") == "Пятислойный")
check("D2: 'Микрогофрокартон' слоёв НЕ декларирует → None", cat.derive_layers("Микрогофрокартон") is None)
check("D2: 'Хром-эрзац' → None", cat.derive_layers("Хром-эрзац") is None)

# ============================================================================
# D3 — build_box_spec кладёт только присутствующее/подтверждённое
# ============================================================================
print("\nD3 · _spec = только реальные поля")
s = cat.build_box_spec(length=33.0, width=23.0, height=23.0, weight=0.276,
                       tip_kartona="Трехслойный", material_col="Целлюлоза", kolvo="25 шт")
check("D3: габариты+вес на месте", all(k in s for k in ("length", "width", "height", "weight")))
check("D3: материал=гофрокартон", s.get("материал") == "гофрокартон")
check("D3: слои=Трехслойный", s.get("слои_картона") == "Трехслойный")
check("D3: штук_в_упаковке=25 (из «25 шт»)", s.get("штук_в_упаковке") == 25, str(s.get("штук_в_упаковке")))
s_bare = cat.build_box_spec(length=33.0, width=23.0, height=23.0, weight=0.276,
                            tip_kartona="Микрогофрокартон")
check("D3: микрогофра → материал есть, слои отсутствуют (честно)",
      s_bare.get("материал") == "гофрокартон" and "слои_картона" not in s_bare, str(s_bare))
check("D3: нет кол-ва → ключа штук_в_упаковке нет", "штук_в_упаковке" not in s_bare)

# ============================================================================
# D4 — enrich_description: факты в описание, без выдумок; форма НЕ в ENUM
# ============================================================================
print("\nD4 · описание обогащено реальными фактами (форма/марка/объём/ручки)")
d = cat.enrich_description("База", marka="Т-23 В", forma="Прямоугольная", obem=96, ruchki="Да", kolvo=25)
check("D4: форма попала в текст описания", "Прямоугольная" in d)
check("D4: марка в описании", "Т-23 В" in d)
check("D4: объём в описании", "96" in d)
check("D4: ручки 'Да' → отметка в описании", "ручк" in d.lower())
d_no = cat.enrich_description("База", ruchki="Нет")
check("D4: ручки 'Нет' → НЕ добавляем ложных удобств", "ручк" not in d_no.lower(), d_no)
check("D4: нет фактов → описание не портится", cat.enrich_description("Только текст") == "Только текст")

# ============================================================================
# D5 — адаптер shortlist→prod: цена=ПРЕДЛОЖЕНИЕ, габариты комплектом, _spec насквозь
# ============================================================================
print("\nD5 · shortlist_to_prod — дропшип-цена и честные габариты")
row = cat.score_item(donor_box(cost=60.0), city="москва", markup_lo=5.0, markup_hi=10.0)
prod = runner.shortlist_to_prod(row)
check("D5: цена карточки = предложение ×5 (300), НЕ закупка 60", prod["price"] == 300.0, str(prod["price"]))
check("D5: weightDimensions собран из полного набора",
      isinstance(prod.get("weightDimensions"), dict)
      and prod["weightDimensions"]["length"] == 33.0)
check("D5: _spec проброшен в prod", isinstance(prod.get("_spec"), dict) and bool(prod["_spec"]))
# частичные габариты → weightDimensions НЕ собираем
row_partial = cat.score_item(donor_box(sku="P1", dims=(33.0, 23.0, 0)), city="москва")
prod_partial = runner.shortlist_to_prod(row_partial)
check("D5: частичные габариты → нет weightDimensions (Маркет отклонил бы неполный)",
      "weightDimensions" not in prod_partial)

# ============================================================================
# D6 — СКВОЗНОЙ: короб → dry publish_card → ТОП-заполнение (≥6 характеристик, 0 ошибок)
# ============================================================================
print("\nD6 · сквозной сухой залив — карточка ОХУЕННО ЗАПОЛНЕНА")
row = cat.score_item(donor_box(cost=60.0), city="москва", markup_lo=5.0, markup_hi=10.0)
prod = runner.shortlist_to_prod(row)
res, cc, pv = emit(prod)
pids = {p.get("parameterId") for p in pv}
check("D6: сборка без ошибок (ни один товар с ошибкой)", res.get("ok") and not cc.get("errors"),
      str(cc.get("errors")))
check("D6: эмитится ≥6 характеристик (ТОП-заполнение)", len(pv) >= 6, f"{len(pv)}: {pids}")
check("D6: Назначение (константа) отправлено", PID_NAZNACHENIE in pids)
check("D6: 3 габарита отправлены", {PID_LEN, PID_WID, PID_HEI} <= pids)
check("D6: вес отправлен", PID_WEIGHT in pids)
check("D6: материал (ENUM) отправлен", PID_MATERIAL in pids)
check("D6: слои (ENUM) отправлены", PID_LAYERS in pids)
# ENUM обязан нести И valueId, И value (недокументированный живой урок)
enum_items = [p for p in pv if p.get("parameterId") in (PID_MATERIAL, PID_LAYERS, PID_NAZNACHENIE)]
check("D6: каждый ENUM несёт valueId+value вместе",
      all(p.get("valueId") and p.get("value") for p in enum_items), str(enum_items))

# ============================================================================
# D7 — честность масштаба: короб без слоёв всё равно летит; пустой _spec не роняет
# ============================================================================
print("\nD7 · честность — меньше данных не значит ошибка")
row_micro = cat.score_item(donor_box(sku="MICRO", tip="Микрогофрокартон"), city="москва")
_, cc_m, pv_m = emit(runner.shortlist_to_prod(row_micro))
mp = {p.get("parameterId") for p in pv_m}
check("D7: микрогофра — материал есть, слои отсутствуют (не выдуманы)",
      PID_MATERIAL in mp and PID_LAYERS not in mp, str(mp))
check("D7: и всё равно сборка без ошибок", not cc_m.get("errors"))
# короб совсем без _spec (обратная совместимость со старым shortlist) — карточка валидна
row_bare = cat.score_item({"sku": "BARE", "name": "Короб", "cost": 50.0, "slug": "kartonnye-koroba",
                           "category_id": 76296786, "length": 30.0, "width": 20.0, "height": 20.0,
                           "weight": 0.3, "pictures": ["https://x/y.jpg"]}, city="москва")
res_b, cc_b, pv_b = emit(runner.shortlist_to_prod(row_bare))
check("D7: короб без спец-колонок — карточка собирается (обратная совместимость)",
      res_b.get("ok") and not cc_b.get("errors"))
check("D7: без _spec всё равно эмитятся габариты+вес+Назначение (≥5)", len(pv_b) >= 5, str(len(pv_b)))

# ============================================================================
# D8 — ЛОВУШКА: форма коробки НИКОГДА не уходит в ENUM «форма выпуска» (семантика плёнки)
# ============================================================================
print("\nD8 · форма коробки — в описание, НЕ в ENUM «форма выпуска» плёнки")
row = cat.score_item(donor_box(sku="TRAP", forma="Плоская"), city="москва")
prod = runner.shortlist_to_prod(row)
_, cc_t, pv_t = emit(prod)
pids_t = {p.get("parameterId") for p in pv_t}
check("D8: параметр «форма выпуска» НЕ эмитится для короба", PID_FORMA_VYPUSKA not in pids_t)
check("D8: 'форма_выпуска' не просочилась в _spec", "форма_выпуска" not in (prod.get("_spec") or {}))
check("D8: но форма ЖИВЁТ в описании (данные не потеряны)", "Плоская" in (prod.get("description") or ""))

# ============================================================================
# D9 — БРЕНД-ЭТАЖ + ОТВЯЗКА: донор-путь штампует vendor="Без бренда" (иначе NO_CARD_ERRORS)
# ============================================================================
# Живой инцидент первого RUBICON-залива (2026-08-25): 5 карточек легли с ошибкой «Заполните поле
# Бренд» — донорский shortlist_to_prod, в отличие от штатного row_to_prod, НЕ штамповал vendor.
# Тут стоим на страже: бренд-этаж + свой EAN-13 (отвязка от чужой карточки) обязаны БЫТЬ.
print("\nD9 · бренд «Без бренда» + отвязка своим EAN-13 (страж живого инцидента)")
row = cat.score_item(donor_box(cost=60.0), city="москва", markup_lo=5.0, markup_hi=10.0)
prod = runner.shortlist_to_prod(row)
check("D9: prod.vendor='Без бренда' (легальный дефолт, канал не раскрыт)",
      prod.get("vendor") == "Без бренда", str(prod.get("vendor")))
check("D9: prod.send_vendor=True (иначе to_offer бренд не отправит)", prod.get("send_vendor") is True)
check("D9: prod.unique_name=True (вторичный рычаг отвязки — уникальное имя)",
      prod.get("unique_name") is True)
bc = str(prod.get("barcode") or "")
check("D9: свой EAN-13 проставлен (13 цифр, внутренний префикс 2)",
      len(bc) == 13 and bc.isdigit() and bc[0] == "2", bc)
# КАРТОЧНЫЙ уровень (истинная метрика): to_offer РЕАЛЬНО кладёт offer.vendor — закрывает
# обязательное поле «Бренд». Ровно то, чего не хватало 5 живым карточкам (offer.vendor=None).
built = runner.card.to_offer(prod, slug="kartonnye-koroba")
offer = built["offer"] if isinstance(built, dict) and "offer" in built else built
check("D9: offer.vendor='Без бренда' уходит в offer-mappings (обязательное поле закрыто)",
      offer.get("vendor") == "Без бренда", str(offer.get("vendor")))
ob = (offer.get("barcodes") or [None])[0]
check("D9: offer.barcodes несут свой EAN-13 (склейка по штрихкоду разорвана)",
      isinstance(ob, str) and len(ob) == 13 and ob.isdigit() and ob[0] == "2", str(offer.get("barcodes")))
# Свой EAN-13 ПЕРЕКРЫВАЕТ донорский штрихкод (донорский склеил бы нас с чужой карточкой Маркета).
prod_bc = runner.shortlist_to_prod({"sku": "BC-OVR", "name": "Короб картонный 330х230х230",
                                    "proposed_low": 300.0, "slug": "kartonnye-koroba",
                                    "barcode": "4601234567893"})
check("D9: донорский штрихкод перекрыт своим EAN-13 (отвязка, а не склейка)",
      prod_bc.get("barcode") != "4601234567893" and str(prod_bc.get("barcode"))[:1] == "2",
      str(prod_bc.get("barcode")))

# ============================================================================
# ИТОГ
# ============================================================================
print("\n" + "=" * 70)
print(f"ЯНДЕКС ДОНОР→ТОП-ЗАПОЛНЕНИЕ: {len(PASS)}/{len(PASS) + len(FAIL)} зелёных")
if FAIL:
    print("КРАСНЫЕ:")
    for f in FAIL:
        print(f"  ❌ {f}")
    sys.exit(1)
print("✅ Донор → карточка охуенно заполнена (≥6 характеристик), 0 ошибок, цена предложена, "
      "материал/слои не выдуманы, форма-ловушка обойдена, бренд «Без бренда» + свой EAN-13 (отвязка)")

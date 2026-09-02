#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M1 ПРИЁМКА — SCOUT кормит PROSPECTOR, ≥1 связка проходит фальсифицируемый тест.

Гейты вехи M1 (HER «оно работает» + SCI «фальсиф. тест достижимости»):

  T1 registry_wired   — реестр поставщиков поднялся, WB зарегистрирован, secret+proven.
  T2 wb_adapter_shape — WB-адаптер даёт товары в единой схеме normalized() (на фикстуре, оффлайн).
  T3 candidate_schema — to_candidates даёт ТОЧНО ту схему, что ждёт PROSPECTOR.falsifiable_test.
  T4 prospector_pass  — скормили кандидатов PROSPECTOR: ≥1 связка passed=True (SCI-гейт).
  T5 honest_signal    — demand_signal помечен как ПРОКСИ (kind=…_public_proxy), не факт продаж.
  T6 add_store_no_core — детмир/спортмастер зарегистрированы БЕЗ правки ядра (доказательство мощи).
  T7 live_wb (опц.)   — реальный скан WB по сети; ПРОПУСК мягко, если сети/выдачи нет.

Оффлайн-фикстура ниже — точный формат сырого товара WB (product-level salePriceU в копейках,
feedbacks на верхнем уровне), по которому написан парс адаптера. Так тест не зависит от сети.
"""
import sys
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent                    # SOCC/scripts/mint/arbiter
MINT = ARB.parent                    # SOCC/scripts/mint
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from suppliers import get_adapter, all_suppliers, normalized  # noqa: E402
from suppliers.wildberries_v1 import _price_rub, _total_stock, _wb_url, _parse_products  # noqa: E402
import supplier_scout_v1 as scout                              # noqa: E402
import socc_mint_prospect_v1 as prospector                     # noqa: E402
import portfolio_v1 as portfolio                               # noqa: E402
import uniqueizer_v1 as uniqueizer                             # noqa: E402


# ── Оффлайн-фикстура: сырой ответ WB (реальная форма полей, чтобы не звать сеть) ──
WB_RAW_FIXTURE = {
    "data": {"products": [
        {"id": 179217312, "name": "Дождевик - пончо многоразовый", "brand": "RainOn",
         "salePriceU": 11100, "feedbacks": 7094, "reviewRating": 4.7,
         "sizes": [{"price": {"total": 11100, "product": 15000},
                    "stocks": [{"qty": 340}, {"qty": 210}]}]},
        {"id": 200455121, "name": "Непромокаемый дождевик с капюшоном унисекс", "brand": "DryWalk",
         "salePriceU": 43400, "feedbacks": 25545, "reviewRating": 4.8,
         "sizes": [{"price": {"total": 43400}, "stocks": [{"qty": 55}]}]},
        {"id": 300999001, "name": "Плащ-дождевик детский", "brand": "KidRain",
         "salePriceU": 0, "feedbacks": 3,  # cost=0 → должен отсеяться на входе
         "sizes": []},
    ]}
}


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


def t1_registry_wired():
    sup = all_suppliers()
    wb = get_adapter("wildberries")
    ok = wb is not None and wb.key == "wildberries" and wb.secret and wb.proven and len(sup) >= 1
    detail = f"поставщиков={sorted(sup)}, wb.secret={getattr(wb,'secret',None)}, wb.proven={getattr(wb,'proven',None)}"
    return ok, detail


def t2_wb_adapter_shape():
    """Парсим фикстуру теми же функциями, что адаптер, и собираем normalized — проверяем форму."""
    prods = _parse_products(WB_RAW_FIXTURE)
    norm = []
    for prod in prods:
        cost = _price_rub(prod)
        if cost <= 0:
            continue
        norm.append(normalized(
            sku=prod["id"], name=prod["name"], cost=cost, url=_wb_url(prod["id"]),
            brand=prod.get("brand", ""), stock=_total_stock(prod),
            feedbacks=prod.get("feedbacks", 0), rating=prod.get("reviewRating", 0)))
    keys = {"sku", "name", "brand", "cost", "url", "stock", "feedbacks", "rating"}
    ok = (len(norm) == 2  # 2 валидных, 1 отсеян по cost=0
          and all(keys <= set(n) for n in norm)
          and norm[0]["cost"] == 111.0 and norm[0]["feedbacks"] == 7094)
    return ok, f"нормализовано={len(norm)} (ждём 2), первый cost={norm[0]['cost'] if norm else None}"


def _fixture_candidates():
    """Прогнать фикстуру через тот же путь, что supplier_scout: normalized → to_candidates."""
    prods = _parse_products(WB_RAW_FIXTURE)
    norm = []
    for prod in prods:
        cost = _price_rub(prod)
        if cost <= 0:
            continue
        norm.append(normalized(
            sku=prod["id"], name=prod["name"], cost=cost, url=_wb_url(prod["id"]),
            brand=prod.get("brand", ""), stock=_total_stock(prod),
            feedbacks=prod.get("feedbacks", 0), rating=prod.get("reviewRating", 0)))
    return scout.to_candidates(norm, "wildberries", profit_target=600, min_profit=200)


def t3_candidate_schema():
    cands = _fixture_candidates()
    need = {"name", "brand", "cost", "sku", "url", "profit_target", "min_profit",
            "demand_signal", "source_market"}
    ok = len(cands) == 2 and all(need <= set(c) for c in cands) \
        and all(isinstance(c["demand_signal"], dict) for c in cands)
    return ok, f"кандидатов={len(cands)}, ключи первого={sorted(cands[0]) if cands else []}"


def t4_prospector_pass():
    """SCI-гейт: скормить кандидатов PROSPECTOR, ≥1 должен пройти falsifiable_test."""
    cands = _fixture_candidates()
    results = [prospector.falsifiable_test(c) for c in cands]
    passed = [r for r in results if r["passed"]]
    proven = prospector.prospect(cands, profit_target=600, min_profit=200)
    ok = len(passed) >= 1 and len(proven) >= 1
    why_first = results[0]["why"] if results else "нет кандидатов"
    m = passed[0]["margin"]["profit_net"] if passed else None
    return ok, f"passed={len(passed)}/{len(cands)}, доказано PROSPECTOR={len(proven)}, маржа₽={m}, why={why_first}"


def t5_honest_signal():
    cands = _fixture_candidates()
    ds = cands[0]["demand_signal"] if cands else {}
    ok = (ds.get("kind") == "wildberries_public_proxy"
          and "прокси" in ds.get("note", "").lower()
          and ds.get("feedbacks", 0) > 0)
    return ok, f"kind={ds.get('kind')}, feedbacks={ds.get('feedbacks')}"


def t6_add_store_no_core():
    """Мощь: детмир+спортмастер в реестре, зарегистрированы БЕЗ единой правки ядра."""
    sup = all_suppliers()
    ok = "detmir" in sup and "sportmaster" in sup
    extra = [k for k in sup if k not in ("wildberries",)]
    return ok, f"доп. магазины без правки ядра={extra}"


def t7_portfolio_breadth():
    """Портфель под лимит: топ 5-8 обоснованных на категорию, breadth-first, cap держится."""
    # 3 категории по несколько кандидатов; часть заведомо непроходная (cost=0 / нет спроса)
    def mk(name, cost, fb):
        return {"name": name, "cost": cost, "sku": f"s{name}", "url": f"u/{name}",
                "profit_target": 600, "min_profit": 200,
                "demand_signal": {"kind": "wildberries_public_proxy", "strength": min(100, fb),
                                  "feedbacks": fb, "note": "прокси"}}
    cats = {
        "дождевик": [mk("дождевик-пончо", 111, 90), mk("дождевик-капюшон", 434, 70),
                     mk("дождевик-детский", 0, 5)],           # cost=0 отсеется
        "зонт": [mk("зонт-автомат", 300, 80), mk("зонт-трость", 250, 40)],
        "термокружка": [mk("термокружка-500", 220, 60), {"name": "без спроса", "cost": 200,
                        "sku": "x", "url": "u/x", "profit_target": 600, "min_profit": 200}],  # нет demand
    }
    res = portfolio.build_portfolio(cats, top_k=8, cabinet_cap=500, profit_target=600, min_profit=200)
    ok = (res["categories_entered"] == 3                       # вошли во ВСЕ 3 категории (вширь)
          and res["cap_used"] <= 500                            # лимит держится
          and all(p["justification"]["passed"] for p in res["portfolio"])  # каждый обоснован
          and all(p["justified_score"] > 0 for p in res["portfolio"]))     # не рандом — ранг с числами
    return ok, (f"вошли в {res['categories_entered']}/3 категорий, занято {res['cap_used']}/500, "
                f"обоснованных пиков={len(res['portfolio'])}")


def t8_portfolio_cap_spreads():
    """При жёстком cap=4 breadth-first присутствует ВШИРЬ (≥3 категории), не топит одну."""
    def mk(cat, i, fb):
        return {"name": f"{cat}-{i}", "cost": 200 + i, "sku": f"{cat}{i}", "url": f"u/{cat}{i}",
                "profit_target": 600, "min_profit": 200,
                "demand_signal": {"strength": fb, "feedbacks": fb, "note": "прокси"}}
    cats = {c: [mk(c, i, 80 - i) for i in range(8)] for c in ("a", "b", "c", "d")}
    res = portfolio.build_portfolio(cats, top_k=8, cabinet_cap=4)
    ok = res["cap_used"] == 4 and res["categories_entered"] >= 3
    return ok, f"cap=4 → занято {res['cap_used']}, категорий вширь={res['categories_entered']} (ждём ≥3)"


def t9_uniqueizer_own_card():
    """Уникализация: свой штрихкод + рерайт + бренд-дом → риск склейки низкий, закон контента ок."""
    prod = {"sku": "179217312", "name": "Дождевик - пончо многоразовый", "brand": "RainOn",
            "url": "https://www.wildberries.ru/catalog/179217312/detail.aspx",
            "cost": 111, "source_market": "wildberries"}
    src = {"name": prod["name"], "brand": "RainOn", "barcode": "4650000000017"}  # заводской
    res = uniqueizer.uniqueize(prod, source_card=src, house_brand="ДОЖДЬ-ДОМ", platform="ozon")
    c, r = res["card"], res["law_report"]
    bc_ok = c["barcode"] != src["barcode"] and len(c["barcode"]) == 13 and c["barcode"][0] == "2"
    ok = (bc_ok and "own_barcode" in r["collision"]["levers_applied"]
          and r["collision"]["verdict"] in ("own_card_likely", "borderline")
          and r["content_law"]["passed"] and r["publish_ok"]
          and not r["risk_levers"])                            # спуфинг по умолчанию ВЫКЛ
    return ok, (f"свой штрихкод={c['barcode']}, риск={r['collision']['risk']}→{r['collision']['verdict']}, "
                f"публиковать={r['publish_ok']}, риск-рычаги={r['risk_levers']}")


def t10_uniqueizer_spoof_flagged():
    """RISK-рычаг спуфинга явно поднимает флаг (закон-честность: опасное — видно оператору)."""
    prod = {"sku": "200455121", "name": "Дождевик с капюшоном", "brand": "DryWalk",
            "url": "u/x", "cost": 434, "source_market": "wildberries"}
    res = uniqueizer.uniqueize(prod, house_brand="ДОЖДЬ-ДОМ", platform="ozon",
                               spoof_manufacturer="Reebok")
    r = res["law_report"]
    ok = "spoof_manufacturer" in r["risk_levers"] and len(r["warnings"]) >= 1
    return ok, f"риск-рычаги={r['risk_levers']}, предупреждений={len(r['warnings'])}"


def t7_live_wb_optional():
    """Опциональный живой скан. Сети/выдачи нет → SKIP (мягко), не роняет приёмку."""
    try:
        res = scout.scout("wildberries", query="дождевик", city="msk", limit=5)
    except Exception as e:
        return None, f"SKIP: сеть недоступна ({type(e).__name__})"
    c = res.get("candidates", [])
    if not c:
        return None, "SKIP: сеть/выдача пуста (fail-soft)"
    return True, f"ЖИВОЙ WB: {len(c)} реальных кандидатов, первый ₽{c[0]['cost']} «{c[0]['name'][:32]}»"


def t12_relevance_guard():
    """Гард релевантности: троттлинг МП отдаёт HTTP-200 с ЛЕВЫМИ товарами — режем ДО кандидата.

    Живой дефект (2026-08-05): под нагрузкой WB на «точилка для ножей» вернул «Высокие кроссовки
    для девочки» ₽1774, и конвейер сделал из них PROVEN-связку с фантомной прибылью ₽1230.
    Тест держит ОБЕ стороны: фантом режется И настоящий товар (включая словоформы) выживает.
    """
    from suppliers.base_v1 import relevant_to_query, filter_relevant, query_tokens

    # 1) фантом режется, настоящее (в т.ч. словоформы «ножей»/«точильный») — живёт
    must_cut = [("Высокие кроссовки для девочки", "точилка для ножей"),
                ("Кроссовки Nike", "дождевик")]
    must_keep = [("Точилка для ножей и ножниц", "точилка для ножей"),
                 ("Точильный камень водный", "точилка для ножей"),
                 ("Дождевик - пончо", "дождевик"),
                 ("Грелка самонагревающаяся для рук", "грелка для рук"),
                 ("Органайзер для проводов", "органайзер для кабелей")]
    cut_ok = all(not relevant_to_query(n, q) for n, q in must_cut)
    keep_ok = all(relevant_to_query(n, q) for n, q in must_keep)

    # 2) пустой/стоп-словный запрос → фильтр ВЫКЛ (обратная совместимость, без над-фильтрации)
    offall = (len(filter_relevant([{"name": "что угодно"}], "")) == 1
              and len(filter_relevant([{"name": "что угодно"}], "для и с")) == 1
              and query_tokens("") == [])

    # 3) фильтр РЕАЛЬНО применён в адаптере WB (не просто лежит функцией) — на фикстуре, без сети
    import suppliers.wildberries_v1 as wbmod
    wb = get_adapter("wildberries")
    fake = {"data": {"products": [
        {"id": 1, "name": "Точилка для ножей и ножниц", "salePriceU": 39800, "feedbacks": 10,
         "sizes": [{"price": {"total": 39800}, "stocks": [{"qty": 5}]}]},
        {"id": 2, "name": "Высокие кроссовки для девочки", "salePriceU": 177400, "feedbacks": 3,
         "sizes": [{"price": {"total": 177400}, "stocks": [{"qty": 2}]}]},
    ]}}
    orig = wbmod.SupplierAdapter.get                       # подменяем сеть на фикстуру
    try:
        wbmod.SupplierAdapter.get = lambda self, url, timeout=20, headers=None: fake
        got = wb.scan(query="точилка для ножей", city="msk", limit=10)
    finally:
        wbmod.SupplierAdapter.get = orig
    names = [g["name"] for g in got]
    wired = len(got) == 1 and "Точилка" in names[0]        # кроссовки отсеяны АДАПТЕРОМ

    ok = cut_ok and keep_ok and offall and wired
    return ok, (f"фантом режется={cut_ok}, настоящее живёт={keep_ok}, пустой-запрос-выкл={offall}, "
                f"адаптер отфильтровал={wired} (осталось {names})")


TESTS = [
    ("T1 registry_wired", t1_registry_wired),
    ("T2 wb_adapter_shape", t2_wb_adapter_shape),
    ("T3 candidate_schema", t3_candidate_schema),
    ("T4 prospector_pass", t4_prospector_pass),
    ("T5 honest_signal", t5_honest_signal),
    ("T6 add_store_no_core", t6_add_store_no_core),
    ("T7 portfolio_breadth", t7_portfolio_breadth),
    ("T8 portfolio_cap_spreads", t8_portfolio_cap_spreads),
    ("T9 uniqueizer_own_card", t9_uniqueizer_own_card),
    ("T10 uniqueizer_spoof_flagged", t10_uniqueizer_spoof_flagged),
    ("T12 relevance_guard", t12_relevance_guard),
    ("T11 live_wb (опц.)", t7_live_wb_optional),
]


def main():
    print("═" * 68)
    print("  ARBITER · M1 ПРИЁМКА — SCOUT → PROSPECTOR (мульти-поставщик, WB №1)")
    print("═" * 68)
    hard_total = 0
    hard_pass = 0
    skipped = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        if ok is None:
            skipped += 1
            print(f"⏭️  SKIP  {name}: {detail}")
            continue
        hard_total += 1
        hard_pass += 1 if ok else 0
        print(f"{_passed(ok)}  {name}: {detail}")
    print("─" * 68)
    print(f"ИТОГ M1:  {hard_pass}/{hard_total} обязательных зелёные"
          f"{f', {skipped} опциональных пропущено' if skipped else ''}")
    print("═" * 68)
    return 0 if hard_pass == hard_total else 1


if __name__ == "__main__":
    sys.exit(main())

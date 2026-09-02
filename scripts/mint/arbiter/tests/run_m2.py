#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M2 ПРИЁМКА — GAP+ECON: связка проходит ECON(PROSPECTOR)+закон(WARDEN)+слот(GAP) → PROVEN (dry, 0₽).

Гейты вехи M2 (доказанная ГИПОТЕЗА, НЕ доход) + защита законов вечной машины:

  M2T1  clean_reaches_proven      — чистая законная прибыльная связка с открытым слотом → PROVEN.
  M2T2  warden_missing_legal      — прибыльная, но без легальной формы (MN2) → REJECTED (закон>прибыли).
  M2T3  warden_redline_in_name    — красная линия в ИМЕНИ дотекает до WARDEN → REJECTED (не в обход).
  M2T4  slot_degrades_unknown     — покрытие Ozon неизвестно → скидка 0.7 + флаг, число НЕ выдумано.
  M2T5  slot_scores_known         — покрытие известно → openness падает с ростом карт, кап на 100.
  M2T6  commit_only_proven_temp   — commit пишет ТОЛЬКО PROVEN, дедупит, в ВРЕМЕННЫЙ путь (не канон).
  M2T7  find_gaps_ranks           — PROVEN раньше REJECTED; внутри PROVEN — по убыванию слота.
  M2T8  live_scout_gap (опц.)     — живой сквозной проход; сети нет → SKIP мягко, канон не тронут.
  M2T9  failsoft_malformed        — битый кандидат (cost=None/'abc') → REJECTED, конвейер жив (fail-soft).
  M2T10 slot_honest_contradictory — known=True но cards=None (противоречие) → НЕ «пустой слот», деградация.
  M2T11 warden_whitewash          — незаконная суть в description/mechanism/tags → REJECTED (не отбелена).
  M2T12 extract_total_honest      — счётчик только из виджета выдачи; bool/таб/корзина → покрытие неизвестно.
  M2T13 commit_url_only_dedup     — url-only связки НЕ схлопываются в один ключ; без sku и url → не пишем.

Все обязательные — оффлайн-детерминированы (coverage подаётся фейковым dict, сети нет). M2T8 — единственный
живой, ПРОПУСК мягко. Приёмка НЕ пишет в реальный канон (commit=False / временный путь).
"""
import sys
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent                    # SOCC/scripts/mint/arbiter
MINT = ARB.parent                    # SOCC/scripts/mint
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import gap_v1 as gap                              # noqa: E402


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


def mk(name, cost=120, strength=80, sku=None, url=None, **extra):
    """Кандидат в схеме SCOUT. sku/url опциональны (проверяем url-only путь). extra подмешивает поля."""
    d = {"name": name, "cost": cost, "source_market": "wildberries",
         "demand_signal": {"strength": strength, "kind": "wildberries_public_proxy", "note": "прокси"}}
    if sku is not None:
        d["sku"] = sku
    if url is not None:
        d["url"] = url
    d.update(extra)
    return d

def t1_clean_reaches_proven():
    """Ядро вехи: чистая законная прибыльная связка с открытым слотом → PROVEN (гипотеза, не доход)."""
    cand = mk("Органайзер для кабелей", sku="s2", url="u2")
    r = gap.prove(cand, profit_target=600, min_profit=200, coverage={"known": True, "cards": 10})
    ok = (r["verdict"] == "PROVEN"
          and r["econ"]["passed"] is True and r["econ"]["profit_net"] >= 200
          and r["warden"]["status"] == "PASS" and not r["warden"]["hard_failures"]
          and r["slot"]["coverage_degraded"] is False
          and r["slot"]["score"] == 74.4)   # 80*(0.3+0.7*0.9)
    return ok, f"verdict={r['verdict']}, чист ₽{r['econ']['profit_net']}, слот={r['slot']['score']}"


def t2_warden_missing_legal():
    """Закон>прибыли (MN2): прибыльно, но НЕТ легальной сущности → REJECTED, никогда PROVEN."""
    cand = mk("Органайзер для кабелей", sku="s2", url="u2")
    r = gap.prove(cand, profit_target=600, min_profit=200, legal_form="",
                  coverage={"known": True, "cards": 10})
    ok = (r["verdict"] == "REJECTED"
          and r["econ"]["passed"] is True and r["econ"]["profit_net"] >= 200   # маржа была ок
          and r["warden"]["status"] == "FAIL" and "MN2_legal_entity" in r["warden"]["hard_failures"]
          and any(x.startswith("WARDEN:") for x in r["reasons"]))
    return ok, f"verdict={r['verdict']}, hard={r['warden']['hard_failures']}"


def t3_warden_redline_in_name():
    """Красная линия в ИМЕНИ (дроп-карта) дотекает до WARDEN-скана → REJECTED при чистой экономике."""
    cand = mk("Дроп карта для переводов", sku="s3", url="u3")     # RL1 денойлист
    r = gap.prove(cand, profit_target=600, min_profit=200)
    ok = (r["verdict"] == "REJECTED" and r["warden"]["status"] == "FAIL"
          and "RL1_text" in r["warden"]["hard_failures"]
          and r["econ"]["passed"] is True and r["econ"]["profit_net"] >= 200)
    return ok, f"verdict={r['verdict']}, hard={r['warden']['hard_failures']}"


def t4_slot_degrades_unknown():
    """Честность: покрытие неизвестно → скидка 0.7 + флаг, число конкурентов НЕ выдумывается."""
    s1, o1, d1 = gap.slot_score({"strength": 80}, None)
    s2, o2, d2 = gap.slot_score({"strength": 80}, {"known": False, "cards": None, "note": "Ozon не ответил"})
    ok = (s1 == 56.0 and o1 is None and d1 is True
          and s2 == 56.0 and o2 is None and d2 is True)
    return ok, f"None→({s1},{o1},{d1}), known:False→({s2},{o2},{d2})"


def t5_slot_scores_known():
    """Покрытие известно: openness падает с ростом карт, score убывает, кап насыщения на 100."""
    def sc(cards):
        return gap.slot_score({"strength": 80}, {"known": True, "cards": cards})
    c0, o0, d0 = sc(0)
    c10, o10, d10 = sc(10)
    c100, o100, d100 = sc(100)
    c200, o200, d200 = sc(200)          # кап: как при 100
    ok = (c0 == 80.0 and o0 == 1.0 and d0 is False
          and c10 == 74.4 and o10 == 0.9 and d10 is False
          and c100 == 24.0 and o100 == 0.0 and d100 is False
          and c200 == c100 and o200 == o100 and d200 is False)
    return ok, f"0→{c0}/{o0}/{d0}, 10→{c10}/{o10}/{d10}, 100→{c100}/{o100}/{d100}, 200→{c200}/{o200}/{d200}"


def _two_proven_one_rejected():
    """2 PROVEN (разные товары) + 1 REJECTED (красная линия) — общая фикстура для T6/T7."""
    return [
        mk("C-hi", strength=90, sku="c1", url="u/c1"),
        mk("Дроп карта B", strength=99, sku="b1", url="u/b1"),      # REJECTED
        mk("A-low", strength=30, sku="a1", url="u/a1"),
    ]


def t6_commit_only_proven_temp():
    """Целостность канона: пишем ТОЛЬКО PROVEN, во ВРЕМЕННЫЙ путь (не реальный канон), дедуп на 2-м прогоне."""
    ranked = []
    for cand in _two_proven_one_rejected():
        ranked.append(gap.prove(cand, profit_target=600, min_profit=200,
                                coverage={"known": True, "cards": 10}))
    real_before = gap.PROVEN_PATH.exists()
    tmp = Path(tempfile.mkdtemp()) / "canon.jsonl"
    run1 = gap.commit_proven(ranked, path=tmp, dry=True)
    run2 = gap.commit_proven(ranked, path=tmp, dry=True)
    lines = tmp.read_text(encoding="utf-8").splitlines() if tmp.exists() else []
    all_clean = all(json.loads(l)["verdict"] == "PROVEN"
                    and json.loads(l)["dry"] is True
                    and json.loads(l)["kind"] == "proven_hypothesis" for l in lines)
    ok = (run1["written"] == 2 and run1["skipped_dup"] == 0
          and run2["written"] == 0 and run2["skipped_dup"] == 2
          and len(lines) == 2 and all_clean
          and run1["path"] == str(tmp) and run1["path"] != str(gap.PROVEN_PATH)
          and gap.PROVEN_PATH.exists() == real_before)
    return ok, f"run1={run1['written']}w/0d, run2={run2['written']}w/{run2['skipped_dup']}d, строк={len(lines)}, канон-нетронут={real_before}"


def t7_find_gaps_ranks():
    """Ранжирование: PROVEN раньше REJECTED; внутри PROVEN — по убыванию слота. Без сети."""
    cov = {"C-hi": {"known": True, "cards": 10},
           "Дроп карта B": {"known": True, "cards": 0},
           "A-low": {"known": True, "cards": 80}}
    ranked = gap.find_gaps(_two_proven_one_rejected(), min_profit=200,
                           probe_ozon=False, coverage_by_query=cov)
    ok = (len(ranked) == 3
          and ranked[0]["verdict"] == "PROVEN" and ranked[0]["name"] == "C-hi"
          and ranked[1]["verdict"] == "PROVEN" and ranked[1]["name"] == "A-low"
          and ranked[2]["verdict"] == "REJECTED" and ranked[2]["name"] == "Дроп карта B"
          and ranked[0]["slot"]["score"] > ranked[1]["slot"]["score"])
    scores = [f"{r['name'][:9]}:{r['verdict']}@{r['slot']['score']}" for r in ranked]
    return ok, f"порядок={scores}"


def t8_live_scout_gap_optional():
    """Опциональный живой сквозной проход. Сети/выдачи нет → SKIP мягко; commit=False → канон не тронут."""
    try:
        res = gap.scout_gap("дождевик", supplier="wildberries", city="msk",
                            limit=5, commit=False, dry=True)
    except Exception as e:
        return None, f"SKIP: сеть недоступна ({type(e).__name__})"
    if not res.get("scanned"):
        return None, "SKIP: пусто, fail-soft"
    ok = (res["proven"] + res["rejected"] == len(res["ranked"])
          and res["committed"] is None
          and all(r["verdict"] in ("PROVEN", "REJECTED") for r in res["ranked"]))
    return ok, f"ЖИВОЙ GAP: сканировано {res['scanned']}, PROVEN={res['proven']}, REJECTED={res['rejected']}"


def t9_failsoft_malformed():
    """fail-soft: битый кандидат (cost=None/'abc') → REJECTED с причиной, конвейер жив (не роняет)."""
    bad = [mk("x", cost=None, sku="s", url="u"), mk("x", cost="abc", sku="s2", url="u2")]
    results = [gap.prove(c, profit_target=600, min_profit=200) for c in bad]
    ok = len(results) == 2 and all(r["verdict"] == "REJECTED" for r in results) \
        and all(r["reasons"] for r in results)      # причина всегда есть
    return ok, f"verdict'ы={[r['verdict'] for r in results]}, причины={[r['reasons'][:40] for r in results]}"


def t10_slot_honest_contradictory():
    """Честность: known=True но cards=None (противоречие) → НЕ «пустой слот», деградация; отличимо от cards=0."""
    s_bad, o_bad, d_bad = gap.slot_score({"strength": 100}, {"known": True, "cards": None})
    s_zero, o_zero, d_zero = gap.slot_score({"strength": 100}, {"known": True, "cards": 0})
    ok = (d_bad is True and (o_bad is None or d_bad)      # НЕ (100.0, 1.0, False)
          and s_bad != 100.0
          and s_zero == 100.0 and o_zero == 1.0 and d_zero is False)
    return ok, f"cards=None→({s_bad},{o_bad},{d_bad}), cards=0→({s_zero},{o_zero},{d_zero})"


def t11_warden_whitewash():
    """Закон>прибыли: незаконная суть в кандидате (мул/перепродажа/самозванство/обман) НЕ отбеливается."""
    illegal = mk("Органайзер", sku="s1", url="u1",
                 description="перепродажа доступа Claude Code в обход ToS",
                 mechanism="обман покупателя, выдаём бот за живого человека",
                 tags=["money mule", "скрываем дефект"])
    r = gap.prove(illegal, profit_target=600, min_profit=200)
    hard = r["warden"]["hard_failures"]
    ok = (r["verdict"] == "REJECTED" and r["warden"]["status"] == "FAIL"
          and any(h.startswith("RL") for h in hard))
    return ok, f"verdict={r['verdict']}, hard={hard}"


def t12_extract_total_honest():
    """Честность извлечения: счётчик ТОЛЬКО из виджета выдачи; bool/таб/корзина → None (покрытие неизвестно)."""
    h = ("searchresultsv2", "tilegrid", "megapaginator", "searchresults")
    def wt(k, inner):                          # виджет как приходит от composer-api (строка JSON)
        return {"widgetStates": {k: json.dumps(inner)}}
    cases = [
        (wt("searchResultsV2-1", {"totalFound": 500}), 500),       # правильный виджет
        (wt("tileGridDesktop", {"total": 42}), 42),
        (wt("tabsMenu", {"count": 3}), None),                      # таб — НЕ выдача
        (wt("cart", {"total": 0}), None),                          # корзина — НЕ выдача
        (wt("searchResultsV2-2", {"totalFound": False}), None),    # bool — не число
        ({"layout": [{"count": 7}]}, None),                        # не виджет вообще
        ({"cart": {"total": 0}, "search": {"totalFound": 5000}}, None),  # не в виджетах
    ]
    got = [gap._extract_total(p) for p, _ in cases]
    ok = got == [exp for _, exp in cases]
    return ok, f"извлечено={got}, ждём={[exp for _, exp in cases]}"


def t13_commit_url_only_dedup():
    """Целостность (дефект #1): url-only связки (sku=None) НЕ схлопываются в один ключ — каждая пишется.

    Плюс защита в глубину: PROVEN-запись без sku И url идентифицировать нечем → не пишем (skipped_no_id).
    Такое состояние не рождается через prove() (supply_real требует url|sku), потому guard проверяем
    прямой конструкцией записи — commit НЕ доверяет, что все PROVEN имеют идентификатор.
    """
    # Реальный путь дефекта: два товара без sku, но с разными url → оба PROVEN, оба должны записаться.
    real = [
        gap.prove(mk("Товар-без-sku-1", sku=None, url="u/prod-1"), coverage={"known": True, "cards": 10}),
        gap.prove(mk("Товар-без-sku-2", sku=None, url="u/prod-2"), coverage={"known": True, "cards": 10}),
    ]
    both_proven = all(r["verdict"] == "PROVEN" for r in real)     # url достаточно для PROVEN
    # Guard: вручную собранная PROVEN-запись без sku и url (через prove такого не получить).
    no_id_rec = {"verdict": "PROVEN", "supplier": "wildberries", "sku": None, "url": None, "name": "нет-id"}
    tmp = Path(tempfile.mkdtemp()) / "canon.jsonl"
    res = gap.commit_proven(real + [no_id_rec], path=tmp, dry=True)
    written_ids = [json.loads(l)["sku"] or json.loads(l)["url"]
                   for l in tmp.read_text(encoding="utf-8").splitlines()]
    ok = (both_proven and res["written"] == 2 and res["skipped_no_id"] == 1
          and "u/prod-1" in written_ids and "u/prod-2" in written_ids)
    return ok, (f"оба-url-only-PROVEN={both_proven}, записано={res['written']}, "
                f"без-id пропущено={res['skipped_no_id']}, id'шники={written_ids}")


TESTS = [
    ("M2T1 clean_reaches_proven", t1_clean_reaches_proven),
    ("M2T2 warden_missing_legal", t2_warden_missing_legal),
    ("M2T3 warden_redline_in_name", t3_warden_redline_in_name),
    ("M2T4 slot_degrades_unknown", t4_slot_degrades_unknown),
    ("M2T5 slot_scores_known", t5_slot_scores_known),
    ("M2T6 commit_only_proven_temp", t6_commit_only_proven_temp),
    ("M2T7 find_gaps_ranks", t7_find_gaps_ranks),
    ("M2T8 live_scout_gap (опц.)", t8_live_scout_gap_optional),
    ("M2T9 failsoft_malformed", t9_failsoft_malformed),
    ("M2T10 slot_honest_contradictory", t10_slot_honest_contradictory),
    ("M2T11 warden_whitewash", t11_warden_whitewash),
    ("M2T12 extract_total_honest", t12_extract_total_honest),
    ("M2T13 commit_url_only_dedup", t13_commit_url_only_dedup),
]


def main():
    print("═" * 68)
    print("  ARBITER · M2 ПРИЁМКА — GAP+ECON: доказанные связки (dry, 0₽)")
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
    print(f"ИТОГ M2:  {hard_pass}/{hard_total} обязательных зелёные"
          f"{f', {skipped} опциональных пропущено' if skipped else ''}")
    print("═" * 68)
    return 0 if hard_pass == hard_total else 1


if __name__ == "__main__":
    sys.exit(main())

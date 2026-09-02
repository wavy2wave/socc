#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — ИСТОЧНИК ГОЛОВЫ (ymarket_head_source_v1). Сухо, 0₽, БЕЗ СЕТИ.

Проверяем ЗАКОНЫ моста wb_scout→ГОЛОВА, а не «запустилось». Сеть подменяем швом fetch_fn —
ни один тест не ходит в WB. Каждый тест ловит конкретную ложь, которую мост мог бы сказать.

  HS1  hunt_default_never_empty   — нет файла → встроенный дефолт (список охоты не бывает пустым)
  HS2  hunt_file_overrides        — валидный файл перекрывает дефолт (воля оператора)
  HS3  hunt_corrupt_falls_back    — битый/пустой/мусорный файл → дефолт, не падение (fail-soft)
  HS4  collect_dedups_by_sku      — один sku из двух запросов → один кандидат (не дубль)
  HS5  dedup_keeps_strongest      — при дубле остаётся экземпляр с бОльшим demand strength
  HS6  one_item_fails_others_ok   — один запрос кидает исключение → остальные всё равно собраны
  HS7  fetch_shapes_accepted      — fetch_fn вернул и dict{candidates}, и голый список — оба ок
  HS8  universe_cap_respected     — вход больше потолка → срез до cap, сильнейшие сохранены
  HS9  thunk_is_lazy_zero_arg     — build_source_fn даёт thunk() без аргументов; сеть НЕ тронута до вызова
  HS10 feeds_head_end_to_end      — thunk → head.plan_day: реальный шорт-лист «предложено» (стык живой)
  HS11 name_dedup_normalized      — без sku дубль по имени (ё/регистр/пробелы) схлопывается
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_head_source_v1 as src      # noqa: E402
import ymarket_role_head_v1 as head       # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


class _Hunt:
    """Контекст: временный список охоты через env YM_HEAD_HUNT_PATH."""
    def __init__(self, content=None):
        self._content = content
    def __enter__(self):
        self._save = os.environ.get("YM_HEAD_HUNT_PATH")
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "hunt.json"
        if self._content is not None:
            self.path.write_text(self._content, encoding="utf-8")
        os.environ["YM_HEAD_HUNT_PATH"] = str(self.path)
        return self
    def __exit__(self, *exc):
        if self._save is None:
            os.environ.pop("YM_HEAD_HUNT_PATH", None)
        else:
            os.environ["YM_HEAD_HUNT_PATH"] = self._save
        self._dir.cleanup()
        return False


def _cand(sku, name, cost, strength):
    """Кандидат в схеме wb_scout.to_candidates (то, что отдаёт scout()['candidates'])."""
    return {"name": name, "brand": "", "cost": float(cost), "sku": (str(sku) if sku else None),
            "url": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx",
            "profit_target": 600, "min_profit": 200, "source_market": "wildberries",
            "demand_signal": {"kind": "wb_public_proxy", "strength": strength}}


def _fetch_from(mapping):
    """Собрать фейковый fetch_fn: query → список кандидатов. Форма ответа как у wb_scout.scout."""
    def fetch(**kw):
        q = kw.get("query") or ("cat" + str(kw.get("category")))
        return {"ts": "x", "candidates": list(mapping.get(q, []))}
    return fetch


# ── тесты ──────────────────────────────────────────────────────────────────────

def hs1_hunt_default_never_empty():
    with _Hunt(None):                                   # файла нет
        h = src.load_hunt()
    ok = isinstance(h, list) and len(h) >= 1 and all(("query" in x or "category" in x) for x in h)
    return ok, f"пунктов дефолта={len(h)} (список охоты не бывает пустым)"


def hs2_hunt_file_overrides():
    with _Hunt(json.dumps([{"query": "только это"}])):
        h = src.load_hunt()
    ok = h == [{"query": "только это"}]
    return ok, f"из файла={h}"


def hs3_hunt_corrupt_falls_back():
    outs = []
    for bad in ("}{ не json", "[]", json.dumps([{"мусор": 1}, "строка", 42])):
        with _Hunt(bad):
            h = src.load_hunt()
        outs.append(len(h))
    # все три → дефолт (непустой), а не пустой/падение
    ok = all(n == len(src.DEFAULT_HUNT) for n in outs)
    return ok, f"битый/пустой/мусор → дефолт каждый раз={outs}"


def hs4_collect_dedups_by_sku():
    fetch = _fetch_from({"q1": [_cand("111", "Плёнка А", 350, 60)],
                         "q2": [_cand("111", "Плёнка А (дубль)", 350, 60)]})
    got = src.collect(hunt=[{"query": "q1"}, {"query": "q2"}], fetch_fn=fetch)
    ok = len(got) == 1 and got[0]["sku"] == "111"
    return ok, f"один sku из двух запросов → кандидатов={len(got)}"


def hs5_dedup_keeps_strongest():
    fetch = _fetch_from({"q1": [_cand("111", "Плёнка", 350, 30)],
                         "q2": [_cand("111", "Плёнка", 350, 90)]})   # сильнее
    got = src.collect(hunt=[{"query": "q1"}, {"query": "q2"}], fetch_fn=fetch)
    s = (got[0].get("demand_signal") or {}).get("strength")
    ok = len(got) == 1 and s == 90
    return ok, f"при дубле осталась сила={s} (ждём 90, сильнейший сигнал)"


def hs6_one_item_fails_others_ok():
    def fetch(**kw):
        if kw.get("query") == "boom":
            raise RuntimeError("сеть легла на этом запросе")
        return {"candidates": [_cand("222", "Живой", 400, 50)]}
    got = src.collect(hunt=[{"query": "boom"}, {"query": "ok"}], fetch_fn=fetch)
    ok = len(got) == 1 and got[0]["sku"] == "222"
    return ok, f"упавший пункт пропущен, собрано={[c['sku'] for c in got]}"


def hs7_fetch_shapes_accepted():
    # dict с 'candidates' И голый список — обе формы валидны
    def fetch(**kw):
        if kw.get("query") == "as_dict":
            return {"candidates": [_cand("1", "Ч/з dict", 350, 40)]}
        return [_cand("2", "Голым списком", 360, 40)]        # без обёртки
    got = src.collect(hunt=[{"query": "as_dict"}, {"query": "as_list"}], fetch_fn=fetch)
    skus = sorted(c["sku"] for c in got)
    ok = skus == ["1", "2"]
    return ok, f"обе формы приняты, sku={skus}"


def hs8_universe_cap_respected():
    big = [_cand(str(i), f"К{i}", 350, i) for i in range(1, 51)]     # 50 штук, strength=i
    fetch = _fetch_from({"q": big})
    got = src.collect(hunt=[{"query": "q"}], fetch_fn=fetch, universe_cap=10)
    strengths = [(c["demand_signal"]["strength"]) for c in got]
    ok = len(got) == 10 and strengths == sorted(strengths, reverse=True) and strengths[0] == 50
    return ok, f"cap=10 соблюдён, топ силы={strengths[:3]} (сильнейшие сохранены)"


def hs9_thunk_is_lazy_zero_arg():
    calls = {"n": 0}
    def fetch(**kw):
        calls["n"] += 1
        return {"candidates": [_cand("9", "Ленивый", 350, 50)]}
    thunk = src.build_source_fn(hunt=[{"query": "q"}], fetch_fn=fetch)
    before = calls["n"]                                  # сборка thunk НЕ должна ходить в сеть
    got = thunk()                                        # вызов без аргументов → тянет сеть
    ok = before == 0 and calls["n"] == 1 and len(got) == 1 and got[0]["sku"] == "9"
    return ok, f"до вызова fetch={before}, после={calls['n']} (лениво, zero-arg)"


def hs10_feeds_head_end_to_end():
    fetch = _fetch_from({"плёнка": [_cand("777", "Плёнка карбон 3D", 350, 80)]})
    thunk = src.build_source_fn(hunt=[{"query": "плёнка"}], fetch_fn=fetch)
    res = head.plan_day(head_source_fn=thunk, trend_result=None)
    ok = (res.get("ok") is True and res.get("reason") != "NO_HEAD_SOURCE"
          and len(res.get("shortlist", [])) == 1
          and res["shortlist"][0]["state"] == head.STATE_PROPOSED)
    return ok, f"стык живой: ok={res.get('ok')} шорт-лист={[s.get('name') for s in res.get('shortlist', [])]}"


def hs11_name_dedup_normalized():
    # без sku: дубль по нормализованному имени (ё→е, регистр, лишние пробелы) ДОЛЖЕН схлопнуться
    fetch = _fetch_from({"q1": [_cand(None, "Плёнка Матовая", 350, 40)],
                         "q2": [_cand(None, "плёнка  матовая", 350, 70)]})   # тот же товар, сильнее
    got = src.collect(hunt=[{"query": "q1"}, {"query": "q2"}], fetch_fn=fetch)
    ok = len(got) == 1 and got[0]["demand_signal"]["strength"] == 70
    return ok, f"осталось={len(got)} сила={got and got[0]['demand_signal']['strength']} (регистр/ё/пробелы схлопнуты)"


TESTS = [
    ("HS1  hunt_default_never_empty", hs1_hunt_default_never_empty),
    ("HS2  hunt_file_overrides", hs2_hunt_file_overrides),
    ("HS3  hunt_corrupt_falls_back", hs3_hunt_corrupt_falls_back),
    ("HS4  collect_dedups_by_sku", hs4_collect_dedups_by_sku),
    ("HS5  dedup_keeps_strongest", hs5_dedup_keeps_strongest),
    ("HS6  one_item_fails_others_ok", hs6_one_item_fails_others_ok),
    ("HS7  fetch_shapes_accepted", hs7_fetch_shapes_accepted),
    ("HS8  universe_cap_respected", hs8_universe_cap_respected),
    ("HS9  thunk_is_lazy_zero_arg", hs9_thunk_is_lazy_zero_arg),
    ("HS10 feeds_head_end_to_end", hs10_feeds_head_end_to_end),
    ("HS11 name_dedup_normalized", hs11_name_dedup_normalized),
]


def main():
    print("🎯 ПРИЁМКА · ИСТОЧНИК ГОЛОВЫ (сухо, 0₽, БЕЗ СЕТИ)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<30} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Источник честен: список охоты не пуст, файл перекрывает, битый→дефолт, дедуп по "
              "sku/имени с сильнейшим сигналом, поштучный fail-soft, потолок соблюдён, thunk ленив "
              "и zero-arg, стык с ГОЛОВОЙ живой, сеть только через шов (0₽ в тестах).")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

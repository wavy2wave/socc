#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — РЕЕСТР АРТИКУЛОВ (ymarket_registry_v1). Сухо, 0₽, без сети.

Проверяем ЗАКОНЫ канона идентификаторов, а не «запустилось». Каждый тест ловит конкретную
ложь, которую реестр мог бы сказать. Пишем ТОЛЬКО во временный стор (env YM_REGISTRY_PATH) —
канон отчётов не трогаем.

  RG1  empty_store_is_empty     — нет файла → load() чистый бланк, get/by_pid/all пусты (не падаем)
  RG2  upsert_needs_offerid     — upsert без offerId → ValueError (R1, не выдумываем ключ)
  RG3  autobuild_pid_and_url    — '9603273-1' → donor_pid+donor_url достроены сами (R6/R3)
  RG4  none_safe_merge          — частичный upsert не затирает известные поля None (R2)
  RG5  explicit_over_derived    — переданный donor_pid/url важнее выведенного (воля вызывающего)
  RG6  by_pid_reverse_index     — by_pid честно собирает ВСЕ offerId одного pid, отсортированно (R4)
  RG7  atomic_roundtrip         — record→lookup через файл: связь переживает запись/чтение
  RG8  failsoft_corrupt_file    — битый JSON → чистый бланк, спасаем articles из чужой схемы (R5)
  RG9  ozon_path_no_pid         — 'ARB-<ean>' → donor_pid=None (Ozon-путь не выдумывает карго-pid)
  RG10 resolve_cargo_from_store — сохранённый donor_pid перекрывает split-fallback (host-префикс)
  RG11 pid_from_source_url      — pid читается из донор-ссылки (R3), чужой url pid НЕ даёт (не выдумываем)
  RG12 absorb_marketsku_track   — marketSku из track (ok=True) вшит в реестр; dry (ok=False) → ничего (ШАГ2)
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

import ymarket_registry_v1 as reg     # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


class _Store:
    """Контекст: временный стор через env YM_REGISTRY_PATH (канон отчётов не трогаем)."""
    def __enter__(self):
        self._save = os.environ.get("YM_REGISTRY_PATH")
        self._dir = tempfile.TemporaryDirectory()
        os.environ["YM_REGISTRY_PATH"] = str(Path(self._dir.name) / "reg.json")
        return self

    def __exit__(self, *exc):
        if self._save is None:
            os.environ.pop("YM_REGISTRY_PATH", None)
        else:
            os.environ["YM_REGISTRY_PATH"] = self._save
        self._dir.cleanup()
        return False


def rg1_empty_store_is_empty():
    with _Store():
        doc = reg.load()
        ok = (doc["schema"] == reg.SCHEMA and reg.all_articles(doc) == {}
              and reg.get(doc, "9603273-1") is None and reg.by_pid(doc, "9603273") == [])
    return ok, f"бланк schema={doc['schema']} articles={reg.all_articles(doc)}"


def rg2_upsert_needs_offerid():
    doc = reg._blank()
    bad = 0
    for empty in ("", None):
        try:
            reg.upsert(doc, empty, marketSku="1")
        except ValueError:
            bad += 1
    return bad == 2, f"отказов на пустом offerId={bad}/2 (R1)"


def rg3_autobuild_pid_and_url():
    doc = reg._blank()
    rec = reg.upsert(doc, "9603273-1")
    ok = (rec["donor_pid"] == "9603273"
          and rec["donor_url"] == "https://sp.cargo-avto.ru/catalog/9603273/")
    return ok, f"pid={rec['donor_pid']} url={rec['donor_url']}"


def rg4_none_safe_merge():
    doc = reg._blank()
    reg.upsert(doc, "9603273-1", marketSku="101812345678", supplier="cargo-avto")
    # частичный upsert (только shopSku) НЕ должен затереть marketSku/supplier
    rec = reg.upsert(doc, "9603273-1", shopSku="SHOP-1")
    ok = (rec["marketSku"] == "101812345678" and rec["supplier"] == "cargo-avto"
          and rec["shopSku"] == "SHOP-1")
    return ok, f"marketSku={rec['marketSku']} shopSku={rec['shopSku']} supplier={rec['supplier']}"


def rg5_explicit_over_derived():
    doc = reg._blank()
    # offerId дал бы pid=9603273, но вызывающий ЗНАЕТ иное (host-префиксный offer) — воля важнее
    rec = reg.upsert(doc, "cargoavto-777", donor_pid="9603273",
                     donor_url="https://custom.example/777/")
    ok = rec["donor_pid"] == "9603273" and rec["donor_url"] == "https://custom.example/777/"
    return ok, f"pid={rec['donor_pid']} url={rec['donor_url']}"


def rg6_by_pid_reverse_index():
    doc = reg._blank()
    reg.upsert(doc, "9603273-2", donor_pid="9603273")
    reg.upsert(doc, "9603273-1", donor_pid="9603273")
    reg.upsert(doc, "9602037-1")                       # другой pid
    got = reg.by_pid(doc, "9603273")
    ok = got == ["9603273-1", "9603273-2"]             # все, отсортированно
    return ok, f"by_pid(9603273)={got} (ждём оба, sorted)"


def rg7_atomic_roundtrip():
    with _Store():
        reg.record("9603273-1", marketSku="101812345678", supplier="cargo-avto")
        rec = reg.lookup("9603273-1")
        ids = reg.lookup_by_pid("9603273")
        ok = (rec and rec["marketSku"] == "101812345678"
              and rec["donor_pid"] == "9603273" and ids == ["9603273-1"])
    return bool(ok), f"через файл: marketSku={rec and rec['marketSku']} by_pid={ids}"


def rg8_failsoft_corrupt_file():
    with _Store():
        p = Path(os.environ["YM_REGISTRY_PATH"])
        p.parent.mkdir(parents=True, exist_ok=True)
        # чужая схема, но с articles — спасаем содержимое, не роняемся (R5)
        p.write_text(json.dumps({"schema": "someone.else", "articles":
                     {"9603273-1": {"offerId": "9603273-1", "donor_pid": "9603273"}}}),
                     encoding="utf-8")
        doc = reg.load()
        rescued = reg.get(doc, "9603273-1")
        # полностью битый JSON → чистый бланк
        p.write_text("}{ не json", encoding="utf-8")
        blank = reg.load()
        ok = (doc["schema"] == reg.SCHEMA and rescued and rescued["donor_pid"] == "9603273"
              and reg.all_articles(blank) == {})
    return bool(ok), f"спасено={bool(rescued)} битый→бланк={reg.all_articles(blank) == {}}"


def rg9_ozon_path_no_pid():
    doc = reg._blank()
    rec = reg.upsert(doc, "ARB-4607012345678", marketSku="55")
    ok = rec["donor_pid"] is None and rec["donor_url"] is None and rec["marketSku"] == "55"
    return ok, f"donor_pid={rec['donor_pid']} (Ozon-путь не выдумывает карго-pid)"


def rg10_resolve_cargo_from_store():
    with _Store():
        # host-префиксный offerId: split-конвенция дала бы None, но сохранённый pid спасает
        reg.record("cargoavto-9603273", donor_pid="9603273",
                   donor_url="https://sp.cargo-avto.ru/catalog/9603273/")
        r = reg.resolve_cargo("cargoavto-9603273")
        # голый канон-offerId работает и без стора (дно-конвенция)
        r2 = reg.resolve_cargo("9602037-1")
        ok = (r and r["pid"] == "9603273" and r["url"].endswith("/9603273/")
              and r2 and r2["pid"] == "9602037")
    return bool(ok), f"из_стора={r} канон={r2}"


def rg11_pid_from_source_url():
    doc = reg._blank()
    # host-префиксный offerId (база не число) → pid НЕ из offerId, но донор-ссылка его несёт
    rec = reg.upsert(doc, "cargoavto-9603273",
                     source_url="https://sp.cargo-avto.ru/catalog/9603273/", supplier="cargo-avto")
    # чужой/не-донорский url pid НЕ даёт (не выдумываем)
    foreign = reg.donor_pid_from_url("https://example.com/product/9603273/")
    ok = (rec["donor_pid"] == "9603273"
          and rec["donor_url"] == "https://sp.cargo-avto.ru/catalog/9603273/"
          and foreign is None)
    return ok, f"pid_из_ссылки={rec['donor_pid']} чужой_url→{foreign} (ждём None)"


def rg12_absorb_marketsku_from_track():
    """ШАГ2: runner._absorb_marketsku ловит marketSku из отчёта track и вшивает в реестр.

    Ловит ту дыру, ради которой заведён реестр: marketSku (id Маркета после залива) читался
    транзитно в card_quality и терялся. Проверяем: (1) реальный rep (ok=True) → marketSku вшит;
    (2) dry rep (ok=False) → НИЧЕГО не пишем (не выдумываем id из воздуха)."""
    import ymarket_runner_v1 as runner
    with _Store():
        # реальный отчёт индекса: mapping.marketSku присвоен Маркетом
        rep_real = {"ok": True, "cards": [
            {"offerId": "9603273-1", "contentRating": 70,
             "mapping": {"marketSku": "101812345678"}},
            {"offerId": "9602037-1", "contentRating": 65, "mapping": {}},   # без marketSku — пропуск
        ]}
        n_real = runner._absorb_marketsku(rep_real)
        got = reg.lookup("9603273-1")
        skipped = reg.lookup("9602037-1")             # не должен появиться (нет marketSku)
        # dry отчёт: ok=False → абсорбция no-op (реестр остаётся как был)
        n_dry = runner._absorb_marketsku({"ok": False, "dry": True, "cards": [
            {"offerId": "ZZZ-1", "mapping": {"marketSku": "999"}}]})
        leaked = reg.lookup("ZZZ-1")
        ok = (n_real == 1 and got and got["marketSku"] == "101812345678"
              and got["donor_pid"] == "9603273"       # достроен из offerId по канону
              and skipped is None and n_dry == 0 and leaked is None)
    return ok, f"вшито_real={n_real} marketSku={got and got.get('marketSku')} dry_вшито={n_dry} утечка_dry={leaked}"


TESTS = [
    ("RG1  empty_store_is_empty", rg1_empty_store_is_empty),
    ("RG2  upsert_needs_offerid", rg2_upsert_needs_offerid),
    ("RG3  autobuild_pid_and_url", rg3_autobuild_pid_and_url),
    ("RG4  none_safe_merge", rg4_none_safe_merge),
    ("RG5  explicit_over_derived", rg5_explicit_over_derived),
    ("RG6  by_pid_reverse_index", rg6_by_pid_reverse_index),
    ("RG7  atomic_roundtrip", rg7_atomic_roundtrip),
    ("RG8  failsoft_corrupt_file", rg8_failsoft_corrupt_file),
    ("RG9  ozon_path_no_pid", rg9_ozon_path_no_pid),
    ("RG10 resolve_cargo_from_store", rg10_resolve_cargo_from_store),
    ("RG11 pid_from_source_url", rg11_pid_from_source_url),
    ("RG12 absorb_marketsku_track", rg12_absorb_marketsku_from_track),
]


def main():
    print("🎯 ПРИЁМКА · РЕЕСТР АРТИКУЛОВ (сухо, 0₽, без сети)")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<28} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    if passed == len(TESTS):
        print("✅ Реестр честен: пустой=пусто, не выдумывает ключ/pid, None-safe merge, "
              "обратный индекс полон, fail-soft, RUBICON цел (0 сети/локальная запись).")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

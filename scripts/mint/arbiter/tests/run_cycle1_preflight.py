#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — PREFLIGHT ЖИВОГО ХОДА ЦИКЛ-1 (#35). Сухо, 0₽, без сети, герметично.

Движок: run_cycle(..., dry=False) до запуска цепи спрашивает creds_present();
ключ в env НЕ найден → ранний FAIL «YANDEX_MARKET_API_KEY отсутствует», цепь НЕ стартует,
леджер НЕ пишется. Ключ есть → preflight пропускается и цепь идёт нормально.

Цепь подменена на заглушку (реальный write НЕ зовём), _sync_library и ledger_path — мок,
чтобы даже при прошедшем preflight ничего не писалось наружу и сеть не звалась.

  PH1 no_key_stops_before_chain  — creds_present=False + живой ход → FAIL-причина «YANDEX_MARKET_API_KEY»,
                                   узел-заглушка НЕ вызывался, леджер НЕ открывался
  PH2 key_present_chain_runs     — creds_present=True + живой ход → preflight пропущен, узел-заглушка
                                   выполнен, вердикт PASS (мост к реальному гейту: дальше уже цепь)
  PH3 dry_never_asks_key         — dry=True (обычный сухой прогон 0₽) preflight не трогает → цепь идёт,
                                   ключ не требуется (обратносовместимо: сухой не падал и не падает)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
for p in (str(ARB),):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_cycle1_v1 as C1        # noqa: E402
import ymarket_hands_v1 as HANDS      # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


# ── герметичная обвязка: манифест/мама — мок, леджер — в tmp, запись-хук — заглушка ──

_FAKE_PROFILE = {"slug": "ph-test", "business_id": 1, "campaign_id": 2, "warehouse_id": 3,
                 "markup": 8.0, "builder": "puzyrkovaya-plenka"}
_ORIG = {}


def _store():
    _ORIG["load_store"] = C1.load_store
    _ORIG["resolve_profile"] = C1.resolve_profile
    _ORIG["ledger_path"] = C1.ledger_path
    _ORIG["_sync_library"] = C1._sync_library
    _ORIG["creds_present"] = getattr(HANDS, "creds_present", None)
    C1.load_store = lambda slug: dict(_FAKE_PROFILE) if slug == "ph-test" else None
    C1.resolve_profile = lambda profile, all_profiles=None: (dict(profile), None)
    C1.ledger_path = lambda slug, date: Path(tempfile.mkdtemp(prefix="ph-ledger-")) / f"{slug}.jsonl"
    C1._sync_library = lambda ctx, results, hsh: {"ok": True, "note": "mock"}
    HANDS.creds_present = lambda: True   # дефолт мока — ключ «есть»


def _restore():
    for k, v in _ORIG.items():
        setattr(C1, k, v)
    if _ORIG.get("creds_present") is None:
        if hasattr(HANDS, "creds_present"):
            del HANDS.creds_present
    else:
        HANDS.creds_present = _ORIG["creds_present"]


def _run_case(key_present, dry):
    """Запуск одного прогона run_cycle с цепью-заглушкой.

    Возврат (verdict, why, ran_nodes, ledger_written) — где ledger_written = True, если
    файл-леджер РЕАЛЬНО создан (движок дошёл до `with open(lp,'a')`). Движок легитимно
    ВЫЧИСЛЯЕТ путь lp на строке 754 ещё до preflight — спай считает не вызов функции,
    а создание файла.
    """
    ran = []
    real_ledger = C1.ledger_path
    state = {"last": None}

    def spy_ledger(slug, date):
        p = Path(real_ledger(slug, date))
        state["last"] = p
        return str(p)

    C1.ledger_path = spy_ledger
    HANDS.creds_present = lambda: key_present

    def stub_node(ctx, dry=dry, commit=True):
        ran.append("STUB")
        return {"verdict": "PASS", "note": "stub", "evidence": {}}

    chain = [("STUB", stub_node, True)]
    try:
        r = C1.run_cycle("ph-test", dry=dry, commit=True, chain=chain,
                         date_str="2026-09-03")
        return r, ran, (state["last"] is not None and state["last"].exists())
    finally:
        C1.ledger_path = real_ledger


def ph1_no_key_stops_before_chain():
    r, ran, lp = _run_case(key_present=False, dry=False)
    why = r.get("why", "")
    ok = (r.get("verdict") == "FAIL" and "YANDEX_MARKET_API_KEY" in why
          and ran == [] and lp == 0)
    return ok, f"verdict={r.get('verdict')} why={why!r} ran={ran} ledger_calls={lp}"


def ph2_key_present_chain_runs():
    r, ran, lp = _run_case(key_present=True, dry=False)
    ok = (r.get("verdict") == "PASS" and ran == ["STUB"] and lp == 1)
    return ok, f"verdict={r.get('verdict')} ran={ran} ledger_calls={lp} (ключ есть → preflight пропущен)"


def ph3_dry_never_asks_key():
    # сухой прогон: preflight-ветка (if not dry) вообще не выполняется → ключ не спрашивается
    r, ran, lp = _run_case(key_present=False, dry=True)
    ok = (r.get("verdict") == "DRY_OK" and ran == ["STUB"] and lp == 1)
    return ok, f"verdict={r.get('verdict')} ran={ran} (dry даже без ключа — цепь идёт, как раньше)"


def _run():
    _store()
    try:
        tests = [("PH1 no_key_stops_before_chain", ph1_no_key_stops_before_chain),
                 ("PH2 key_present_chain_runs", ph2_key_present_chain_runs),
                 ("PH3 dry_never_asks_key", ph3_dry_never_asks_key)]
        fails = 0
        for name, fn in tests:
            try:
                ok, detail = fn()
            except Exception as e:
                ok, detail = False, f"{type(e).__name__}: {e}"
            print(f"  {_passed(ok)} {name:<28} {detail}")
            fails += 0 if ok else 1
        print(f"\nPREFLIGHT #35: {len(tests) - fails}/{len(tests)} зелёных")
        return 1 if fails else 0
    finally:
        _restore()


if __name__ == "__main__":
    raise SystemExit(_run())

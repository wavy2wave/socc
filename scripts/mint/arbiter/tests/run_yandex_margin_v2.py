#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЯНДЕКС — ПРИЁМКА «ЦЕНОВИК v2 · пол маржи с трудом выкупа L + возвраты r» (сухо, 0₽, без сети).

Бэклог органа №3: вшить L (труд выкупа на заказ) и r (доля возвратов) в ПОЛ цены и поднять
гейт маржи 5%→18% на ОЖИДАЕМОЙ прибыли. Проверяем ЗАКОНЫ (каждый можно провалить), а не «запустилось».

  Математика (ymarket_margin_v2_v1)
    MV1  parity_v1_at_zeros      — L=0,r=0,маржа=5% → пол = закупка+сборы+30 (ровно v1); v2 ⊃ v1
    MV2  labor_adds_exactly_L    — при r=0 труд L поднимает пол РОВНО на L (абсолютное условие)
    MV3  returns_monotonic       — пол строго растёт с ростом r (возвраты дороже → цена выше)
    MV4  gate18_binds_relative   — цена выше break-even, но маржа<18% → ОТКАЗ (жмёт относительное)
    MV5  honest_none_never_zero  — нет закупки/сборов → пол None, НИКОГДА 0 (ноль=«продай за копейку»)
    MV6  E_eq_minprofit_at_abs   — на абсолютном полу ожидаемая прибыль == min_profit (break-even точен)
    MV7  E_margin_eq_gate_at_rel — на относительном полу ожидаемая маржа == гейт (18% точен)
    MV8  calibrated_flag         — L,r заданы явно → calibrated=True; по умолчанию → False + метка ⚠️
    MV9  returns_1_guard         — r≥1 → пол None, decide infeasible, НЕТ деления на ноль (не падаем)
    MV10 margin_unreachable      — (1−r) ≤ маржи → пол None + «недостижима» (не выдумываем число)
    MV11 rubicon_pure_math       — модуль НЕ импортирует сеть/торговые руки, денег не двигает

  Обратная совместимость роли (ymarket_role_pricer_v1) — opt-in, умолчание НЕ трогает v1
    MV12 role_v1_default_intact  — price_decision без floor_model = прежний v1 (пол 260, без v2-полей)
    MV13 role_v2_optin_delegates — floor_model='v2' → делегат в модуль (model=v2, profit=E[π])
    MV14 batch_default_is_v1     — decide_batch без floor_model = v1 (нет ключа model → M4/БРИГАДИР целы)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
SCRIPTS = MINT.parent
for p in (str(ARB), str(MINT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_margin_v2_v1 as mv2          # noqa: E402
import ymarket_role_pricer_v1 as pricer     # noqa: E402


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


# ─────────────────────────── МАТЕМАТИКА ───────────────────────────

def mv1_parity_v1_at_zeros():
    """L=0, r=0, маржа=5% → пол = закупка(180)+сборы(50)+min_profit(30) = 260 (ровно v1)."""
    f = mv2.margin_floor_v2(180, 50, labor=0, returns_rate=0, min_margin_pct=5)
    ok = f["floor"] == 260.0 and f["binding"] == "absolute" and f["feasible"]
    return ok, f"floor={f['floor']} (v1 ждал 260) binding={f['binding']}"


def mv2_labor_adds_exactly_L():
    """При r=0 (маржа 5%, чтобы жало абсолютное условие) труд L поднимает пол РОВНО на L."""
    f0 = mv2.margin_floor_v2(180, 50, labor=0, returns_rate=0, min_margin_pct=5)
    fL = mv2.margin_floor_v2(180, 50, labor=50, returns_rate=0, min_margin_pct=5)
    delta = round(fL["floor"] - f0["floor"], 2)
    ok = delta == 50.0 and f0["binding"] == "absolute" and fL["binding"] == "absolute"
    return ok, f"Δпол={delta} при L=50 (ждём 50.0); binding {f0['binding']}/{fL['binding']}"


def mv3_returns_monotonic():
    """Пол строго растёт с ростом доли возвратов r (0 < 5% < 20%), прочее фиксировано."""
    fs = [mv2.margin_floor_v2(180, 50, labor=50, returns_rate=r)["floor"] for r in (0.0, 0.05, 0.2)]
    ok = fs[0] < fs[1] < fs[2]
    return ok, f"пол(r=0)={fs[0]} < пол(5%)={fs[1]} < пол(20%)={fs[2]}"


def mv4_gate18_binds_relative():
    """Цена 340 > break-even (E≥min_profit), но ожид. маржа 13.4% < 18% → ОТКАЗ, жмёт относительное."""
    d = mv2.decide_v2(340, 180, 50)         # L,r по умолчанию (50/5%), гейт 18%
    ok = (not d["allowed"] and d["binding"] == "relative"
          and d["e_profit"] >= mv2.MIN_PROFIT_RUB      # абсолютное условие ВЫПОЛНЕНО
          and d["e_margin_pct"] < mv2.MIN_MARGIN_PCT_V2)  # но МАРЖА не дотянула → вот причина
    return ok, f"allowed={d['allowed']} E={d['e_profit']}₽ (≥{mv2.MIN_PROFIT_RUB}) маржа={d['e_margin_pct']}% (<18)"


def mv5_honest_none_never_zero():
    """Нет закупки или сборов → пол None (не 0). decide честно отказывает с правильным basis."""
    fl_c = mv2.margin_floor_v2(None, 50)["floor"]
    fl_f = mv2.margin_floor_v2(180, None)["floor"]
    dc = mv2.decide_v2(1000, None, 50)
    df = mv2.decide_v2(1000, 500, None)
    ok = (fl_c is None and fl_f is None
          and dc["floor"] is None and dc["basis"] == "cost_only" and not dc["allowed"]
          and df["floor"] is None and df["basis"] == "no_fees" and not df["allowed"])
    return ok, f"пол(нет закуп)={fl_c} пол(нет сборов)={fl_f} basis={dc['basis']}/{df['basis']} (не 0!)"


def mv6_E_eq_minprofit_at_abs():
    """На АБСОЛЮТНОМ полу ожидаемая прибыль == min_profit (пол = точный break-even по прибыли)."""
    fl = mv2.margin_floor_v2(180, 50, labor=50, returns_rate=0.05, min_margin_pct=5)
    af = fl["absolute_floor"]
    ep = mv2.expected_profit(af, 180, 50, labor=50, returns_rate=0.05)["e_profit"]
    ok = abs(ep - mv2.MIN_PROFIT_RUB) < 0.5
    return ok, f"E[π]@абс.пол({af})={ep}₽ == min_profit {mv2.MIN_PROFIT_RUB}₽"


def mv7_E_margin_eq_gate_at_rel():
    """На ОТНОСИТЕЛЬНОМ полу ожидаемая маржа == гейт 18% (пол = точная граница маржи)."""
    fl = mv2.margin_floor_v2(180, 50)       # умолчания: L=50, r=5%, гейт 18%
    rf = fl["relative_floor"]
    em = mv2.expected_profit(rf, 180, 50)["e_margin_pct"]
    ok = abs(em - mv2.MIN_MARGIN_PCT_V2) < 0.5
    return ok, f"E-маржа@отн.пол({rf})={em}% == гейт {mv2.MIN_MARGIN_PCT_V2}%"


def mv8_calibrated_flag():
    """L,r заданы явно (замер на живом заказе) → calibrated=True без метки; по умолчанию → False + ⚠️."""
    est = mv2.decide_v2(600, 180, 50)
    cal = mv2.decide_v2(600, 180, 50, labor=40, returns_rate=0.03)
    ok = (est["calibrated"] is False and "оценка" in est["why"]
          and cal["calibrated"] is True and "оценка" not in cal["why"])
    return ok, f"умолч.calibrated={est['calibrated']}(+метка) явно={cal['calibrated']}(без метки)"


def mv9_returns_1_guard():
    """r≥1 (почти верный возврат) → пол None, decide infeasible, БЕЗ ZeroDivisionError."""
    try:
        fl = mv2.margin_floor_v2(180, 50, returns_rate=1.0)
        d = mv2.decide_v2(1000, 180, 50, returns_rate=1.0)
    except ZeroDivisionError:
        return False, "УПАЛ на делении на ноль при r=1 (защита не сработала)"
    ok = fl["floor"] is None and not fl["feasible"] and not d["allowed"] and d["basis"] == "infeasible"
    return ok, f"пол={fl['floor']} feasible={fl['feasible']} decide.basis={d['basis']} (не упал)"


def mv10_margin_unreachable():
    """(1−r) ≤ маржа/100 → маржу не взять ни за какую цену → пол None + честное «недостижима»."""
    fl = mv2.margin_floor_v2(180, 50, returns_rate=0.9, min_margin_pct=18)
    ok = fl["floor"] is None and not fl["feasible"] and "недостижима" in fl["why"]
    return ok, f"пол={fl['floor']} feasible={fl['feasible']} why…{fl['why'][:30]!r}"


def mv11_rubicon_pure_math():
    """RUBICON: модуль математики НЕ тянет сеть/торговые руки и не двигает деньги (чистая функция)."""
    src = (ARB / "ymarket_margin_v2_v1.py").read_text(encoding="utf-8")
    banned = ["urllib", "requests", "socket", "http", "trade_hands", "update_prices",
              "publish", "subprocess", "open("]
    hit = [b for b in banned if b in src]
    return not hit, f"запрещённых обращений: {hit or 'нет — пол считается, деньги не двигаются'}"


# ─────────────────────────── ОБРАТНАЯ СОВМЕСТИМОСТЬ РОЛИ ───────────────────────────

_TARIFF = {"tariffs": [{"amount": 50}]}


def mv12_role_v1_default_intact():
    """price_decision БЕЗ floor_model = чистый v1: канонич. кейс M4 (цена200/закуп180/сборы50) →
    пол 260, отказ «ниже пола», и НИ ОДНОГО поля v2 в ответе (иначе сломались бы M4/потребители)."""
    d = pricer.price_decision({"price": 200, "cost": 180}, tariff_row=_TARIFF)
    ok = (d["floor"] == 260.0 and not d["allowed"] and d["basis"] == "full"
          and "НИЖЕ пола" in d["why"]
          and "model" not in d and "e_profit" not in d and "calibrated" not in d)
    return ok, f"floor={d['floor']} allowed={d['allowed']} v2-поля-протекли={'model' in d}"


def mv13_role_v2_optin_delegates():
    """floor_model='v2' → делегат в модуль: model=v2, floor=пол v2, profit=ОЖИДАЕМАЯ прибыль."""
    d = pricer.price_decision({"price": 600, "cost": 180}, tariff_row=_TARIFF, floor_model="v2")
    ref = mv2.decide_v2(600, 180, 50)
    ok = (d.get("model") == "v2" and d["floor"] == ref["floor"]
          and d["profit"] == ref["e_profit"] and d["margin_pct"] == ref["e_margin_pct"]
          and d["allowed"] == ref["allowed"] and d["calibrated"] is False)
    return ok, f"model={d.get('model')} floor={d['floor']} profit=E[π]={d['profit']} allowed={d['allowed']}"


def mv14_batch_default_is_v1():
    """decide_batch БЕЗ floor_model = v1 (нет ключа model в решениях) — M4 и эскалация БРИГАДИРА целы."""
    prods = [{"sku": "S1", "price": 300, "cost": 180}, {"sku": "S2", "price": 1000, "cost": 500}]
    fake = lambda offers, **kw: [_TARIFF for _ in offers]
    v1 = pricer.decide_batch(prods, tariffs_fn=fake)
    v2 = pricer.decide_batch(prods, tariffs_fn=fake, floor_model="v2")
    v1_clean = all("model" not in d for d in v1["decisions"])
    v2_marked = all(d.get("model") == "v2" for d in v2["decisions"])
    return v1_clean and v2_marked, f"v1 без model={v1_clean} · v2 помечен={v2_marked}"


TESTS = [
    ("MV1  parity_v1_at_zeros", mv1_parity_v1_at_zeros),
    ("MV2  labor_adds_exactly_L", mv2_labor_adds_exactly_L),
    ("MV3  returns_monotonic", mv3_returns_monotonic),
    ("MV4  gate18_binds_relative", mv4_gate18_binds_relative),
    ("MV5  honest_none_never_zero", mv5_honest_none_never_zero),
    ("MV6  E_eq_minprofit_at_abs", mv6_E_eq_minprofit_at_abs),
    ("MV7  E_margin_eq_gate_at_rel", mv7_E_margin_eq_gate_at_rel),
    ("MV8  calibrated_flag", mv8_calibrated_flag),
    ("MV9  returns_1_guard", mv9_returns_1_guard),
    ("MV10 margin_unreachable", mv10_margin_unreachable),
    ("MV11 rubicon_pure_math", mv11_rubicon_pure_math),
    ("MV12 role_v1_default_intact", mv12_role_v1_default_intact),
    ("MV13 role_v2_optin_delegates", mv13_role_v2_optin_delegates),
    ("MV14 batch_default_is_v1", mv14_batch_default_is_v1),
]


def main():
    print("🎯 ЯНДЕКС ПРИЁМКА · ЦЕНОВИК v2 — L+r в пол маржи, гейт 18%, v2⊃v1 (сухо, 0₽)")
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
        print("✅ ЦЕНОВИК v2 честен: пол держит ожид. прибыль ≥18% с учётом труда выкупа и возвратов, "
              "вырождается в v1 при нулях, None вместо фейкового 0, r≥1 не роняет, умолчание = v1 (M4 цел)")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

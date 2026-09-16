#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — ФИЗ-БЛИЗНЕЦ НА ВИТРИНЕ (#38 · «в след раз создай без ошибки»). Сухо, 0₽, без сети:
руки ЯМ мокаются на уровне модуля (как FG-приёмка floor-guard). НИ ОДИН тест не ходит в сеть.

Ошибка 2026-09-02 (которую гард не должен повторить): один физический рулон 0.3×50 м трёхслойный
60 г/м² продавался ДВАЖДЫ — легаси 9601515-1 и новый ARB-29846713 — под разными offerId и своими
EAN. СВЕРКА (N6) видит только СВОИ манифест-sku и чужого близнеца не замечает (matrix/registry/
library — пост-фактум). Гард — ПРЕД-заливной, в СБОРКЕ (N2): сравнивает ХАРАКТЕРИСТИКИ задумки
(_spec) с живым offer-cards кампании (не имя — у донора и у нас разные стили имени, norm_key
имени и вырождался). Проверяет ТОЛЬКО создание НОВЫХ карточек; уже-живые ARB-карточки манифеста
(идемпотентный пере-сбор) не трогает — их оверлэп с легаси = факт каталога оператора, не ошибка
создания (доктрина refute_action).

  TW1  единицы_ширины_нормируются — легаси слал ширину в см (30), ARB в м (0.3): один физ-ключ
  TW2  новый_кандидат_близнец     — создаём карточку, чей рулон уже живой (легаси) → FAIL, стоп
  TW3  пере_сбор_живого_PASS      — уже-живая ARB-карточка манифеста пере-собирается → PASS
  TW4  offline_инертно            — кабинета нет в манифесте (как юнит-тесты FG) → PASS, без сети
  TW5  чтение_упало_честный_FAIL  — кабинет есть, читалка витрины упала → FAIL «не доказано»
  TW6  близнец_внутри_партии      — два новых донора одной партии = один рулон → FAIL
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
for p in (str(ARB),):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_cycle1_v1 as C1          # noqa: E402
import ymarket_film_cards_v1 as FC      # noqa: E402
from uniqueizer_v1 import gen_ean13     # noqa: E402

# pid из FILM_FACTS → _spec+описание; габариты полные → ОВХ. Рулон = ARB-29846713 (0.3×50, трёх, 60).
_PID = "9048"
_CAB = {"business_id": "216949599", "campaign_id": "149215943"}


def _donor(article, pid=_PID, cost=600.0):
    return {"pid": pid, "article": article,
            "name": "Воздушно-пузырьковая плёнка 0.3×50 м трёхслойная 60 г/м²",
            "cost": cost, "length": 50, "width": 35, "height": 50, "weight": 1.438}


def _full_ctx(profile_extra, donors):
    profile = {"slug": "tw-test", "markup": 8.0}
    profile.update(profile_extra or {})
    return {"profile": profile, "raw_donor": donors}


def _patch_photos():
    orig = FC._pub_urls_by_pid
    FC._pub_urls_by_pid = lambda: {_PID: ["https://img.example/1.jpg"]}
    return orig


def _patch_live(entries, cards, creds=True):
    """Мок ЯМ-рук на уровне модуля ymarket_hands_v1 (тот же объект, что импортит движок).
    entries — как ответ campaign_offers; cards — как offer_cards_status."""
    import ymarket_hands_v1 as h
    orig = (h.campaign_offers, h.offer_cards_status, h.creds_present)
    h.creds_present = lambda: creds
    h.campaign_offers = lambda cid, offer_ids=None, limit=50, timeout=30: {"offers": entries}
    h.offer_cards_status = lambda bid, offer_ids=None, limit=50, timeout=30: cards
    return orig


def _restore(fns, orig):
    import ymarket_hands_v1 as h
    h.campaign_offers, h.offer_cards_status, h.creds_present = orig
    FC._pub_urls_by_pid = fns


def _pv(width, length, density, слои="трехслойная", material="полиэтилен", color=None):
    """Живой offer-cards parameterValues: parameterId → поле физ-ключа (см. _TWIN_LIVE_PID)."""
    pv = [{"parameterId": 23679910, "value": width},
          {"parameterId": 51734601, "value": length},
          {"parameterId": 34439870, "value": density},
          {"parameterId": 27141751, "value": слои},
          {"parameterId": 17352854, "value": material}]
    if color is not None:
        pv.append({"parameterId": 13887626, "value": color})
    return pv


def _live_offer(oid):
    return {"offerId": oid, "status": "PUBLISHED", "available": True}


def _node_build(ctx):
    orig = _patch_photos()
    try:
        return C1.node_build(ctx, dry=True, commit=False)
    finally:
        FC._pub_urls_by_pid = orig


def _node_build_live(ctx, entries, cards, creds=True):
    orig = _patch_live(entries, cards, creds=creds)
    try:
        return _node_build(ctx)
    finally:
        _restore(FC._pub_urls_by_pid, orig)


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


# ── TW1: единицы ширины нормируются ───────────────────────────────────────────

def tw1_units_normalized():
    k_cm = C1._twin_live_key(_pv(30, 50, 60))          # легаси: ширина в см (30)
    k_m = C1._twin_live_key(_pv(0.3, 50, 60))          # ARB: ширина в м (0.3)
    ok = (k_cm == k_m == "0.3|50|60|трехслойная|полиэтилен")
    return ok, f"cm={k_cm!r} vs m={k_m!r} (один физ-ключ → тот же рулон)"


# ── TW2: новый кандидат — рулон уже живой под другим offerId ─────────────────

def tw2_new_twin_fail():
    # Живёт легаси 9601515-1 (тот же рулон). Манифест хочет СОЗДАТЬ новый ARB-* под pid 9048 —
    # его sku ещё не живёт → гард обязан остановить до залива.
    sku = "ARB-" + gen_ean13("TW-9602037")[-8:]
    ctx = _full_ctx(_CAB, [_donor("TW-9602037")])
    r = _node_build_live(ctx, [_live_offer("9601515-1")],
                         [{"offerId": "9601515-1", "parameterValues": _pv(30, 50, 60)}])
    ev = r.get("evidence") or {}
    twin = ev.get("twin") or {}
    ok = (r.get("verdict") == "FAIL" and "близнец" in r.get("note", "")
          and twin.get(sku) == ["9601515-1"])
    return ok, (f"verdict={r.get('verdict')} twin={twin} · {r.get('note', '')[:120]}"
                f"\n      (кандидат {sku} = живой 9601515-1, тот же 0.3×50×60 трёхслойная)")


# ── TW3: пере-сбор уже-живой карточки манифеста — НЕ близнец ──────────────────

def tw3_idempotent_rebuild_pass():
    # И ARB-29846713 (свой sku), и легаси-близнец 9601515-1 живут. Пере-сбор манифеста идемпотентен:
    # sku кандидата УЖЕ в live → это не «создание», оверлэп с легаси — факт каталога, НЕ ошибка гарда.
    sku = "ARB-" + gen_ean13("TW-9602037")[-8:]
    ctx = _full_ctx(_CAB, [_donor("TW-9602037")])
    cards = [{"offerId": o, "parameterValues": _pv(30, 50, 60)}
             for o in ("9601515-1", sku)]
    r = _node_build_live(ctx, [_live_offer("9601515-1"), _live_offer(sku)], cards)
    ev = r.get("evidence") or {}
    ok = r.get("verdict") == "PASS" and "twin" not in ev
    return ok, f"verdict={r.get('verdict')} (живой {sku} + легаси рядом → PASS, оверлэп оператора)"


# ── TW4: офлайн-инертность (кабинет в манифесте не задан) ─────────────────────

def tw4_offline_inert():
    # Как юнит-тесты FG (profile без business_id/campaign_id): руки НЕ мокаем — если гард попробует
    # сеть, упадёт/зависнет. Должен пройти PASS без сети (прежнее поведение N2).
    ctx = _full_ctx(None, [_donor("TW-9602037")])
    r = _node_build(ctx)
    return r.get("verdict") == "PASS", f"verdict={r.get('verdict')} (кабинета нет — дедуп инертен)"


# ── TW5: чтение витрины упало → честный FAIL, не залив вслепую ────────────────

def tw5_read_fail_honest():
    ctx = _full_ctx(_CAB, [_donor("TW-9602037")])
    import ymarket_hands_v1 as h
    orig = (h.campaign_offers, h.offer_cards_status, h.creds_present)
    h.creds_present = lambda: True
    h.campaign_offers = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("сеть моргнула"))
    h.offer_cards_status = lambda *a, **k: []
    try:
        r = _node_build(ctx)
    finally:
        h.campaign_offers, h.offer_cards_status, h.creds_present = orig
        FC._pub_urls_by_pid = FC._pub_urls_by_pid
    note = r.get("note", "")
    ok = (r.get("verdict") == "FAIL" and "дедуп-чтение" in note and "залив отменён" in note)
    return ok, f"verdict={r.get('verdict')} · {note[:130]} (не доказано «близнеца нет» → не пишем)"


# ── TW6: два новых донора одной партии = один рулон ───────────────────────────

def tw6_within_batch_fail():
    # Витрина пуста, но манифест принёс ДВЕ строки = один физический рулон (разные article → разные
    # sku, одинаковые _spec). Гард ловит пару ВНУТРИ партии до любого залива.
    ctx = _full_ctx(_CAB, [_donor("TW-9602037"), _donor("TW-9602037B")])
    r = _node_build_live(ctx, [], [])
    ev = r.get("evidence") or {}
    twin = ev.get("twin") or {}
    sku_a = "ARB-" + gen_ean13("TW-9602037")[-8:]
    sku_b = "ARB-" + gen_ean13("TW-9602037B")[-8:]
    ok = (r.get("verdict") == "FAIL"
          and set(twin.get(sku_a, [])) == {sku_b} and set(twin.get(sku_b, [])) == {sku_a})
    return ok, (f"verdict={r.get('verdict')} twin={ {k: v for k, v in twin.items()} } "
                f"(два донора = один рулон)")


# ── TW7: цвет-ВАРИАНТ против живой витрины — НЕ близнец (#38-расширение 2026-09-08) ──────────

def tw7_live_color_variant_pass():
    # Тот же размер/плотность, но живой легаси ЧЁРНЫЙ (Black bubble), кандидат ПРОЗРАЧНЫЙ (9048):
    # физ-ключ один, но цвет разводит → разные товары → залив НЕ останавливаем.
    sku = "ARB-" + gen_ean13("TW-9602037")[-8:]
    ctx = _full_ctx(_CAB, [_donor("TW-9602037")])
    r = _node_build_live(ctx, [_live_offer("9601515-1")],
                         [{"offerId": "9601515-1",
                           "parameterValues": _pv(30, 50, 60, color="чёрный")}])
    ev = r.get("evidence") or {}
    ok = r.get("verdict") == "PASS" and "twin" not in ev
    return ok, (f"verdict={r.get('verdict')} (живой 9601515-1 чёрный vs кандидат прозрачный — "
                f"цвет разводит, НЕ близнец)")

# ── TW8: цвет-ВАРИАНТ внутри партии — НЕ близнец (#38-расширение 2026-09-08) ────────────────

def tw8_within_batch_color_variant_pass():
    # Партия несёт ДВА донора одного размера/плотности: один прозрачный (9048), другой ЧЁРНЫЙ
    # (впрыснутый факт) → физ-ключ один, цвет разводит → оба уходят, НЕ «один рулон».
    black_pid = "9999"
    orig = FC.FILM_FACTS.get(black_pid)
    facts = dict(FC.FILM_FACTS[_PID])           # копия 9048 (0.3×50 трёхслойная 60г)
    facts["цвет"] = "чёрный"
    FC.FILM_FACTS[black_pid] = facts
    try:
        ctx = _full_ctx(_CAB, [_donor("TW-9602037"), _donor("TW-9602037B", pid=black_pid)])
        # фото ОБОИМ кандидатам (иначе СБОРКА честно упадёт «фото нет», а не на гарде)
        orig_photos = _patch_photos()
        FC._pub_urls_by_pid = lambda: {_PID: ["https://img.example/1.jpg"],
                                       black_pid: ["https://img.example/2.jpg"]}
        orig_live = _patch_live([], [])
        try:
            r = C1.node_build(ctx, dry=True, commit=False)
        finally:
            FC._pub_urls_by_pid = orig_photos
            _restore(None, orig_live)
        ev = r.get("evidence") or {}
        ok = r.get("verdict") == "PASS" and "twin" not in ev
        return ok, (f"verdict={r.get('verdict')} (9048 прозрачный + {black_pid} чёрный — "
                    f"цвет разводит внутри партии, НЕ близнец)")
    finally:
        if orig is None:
            FC.FILM_FACTS.pop(black_pid, None)
        else:
            FC.FILM_FACTS[black_pid] = orig


def _run():
    tests = [("TW1 единицы_ширины", tw1_units_normalized),
             ("TW2 новый_кандидат_близнец", tw2_new_twin_fail),
             ("TW3 пере_сбор_живого_PASS", tw3_idempotent_rebuild_pass),
             ("TW4 offline_инертно", tw4_offline_inert),
             ("TW5 чтение_упало_честный_FAIL", tw5_read_fail_honest),
             ("TW6 близнец_внутри_партии", tw6_within_batch_fail),
             ("TW7 жив_цвет_вариант_PASS", tw7_live_color_variant_pass),
             ("TW8 партия_цвет_вариант_PASS", tw8_within_batch_color_variant_pass)]
    fails = 0
    for name, fn in tests:
        try:
            ok, detail = fn()
        except Exception as e:                      # тест упал — это FAIL приёмки, не «ожидание»
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(f"  {_passed(ok)} {name:<26} {detail}")
        fails += 0 if ok else 1
    print(f"\nФИЗ-БЛИЗНЕЦ (#38): {len(tests) - fails}/{len(tests)} зелёных")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА ЯНДЕКС — ПОСТ-ЗАЛИВОЧНАЯ СВЕРКА СТАТУСОВ (0₽, без сети, без ключа, без openpyxl).

Кодифицирует планку оператора: «инструмент не просто заливает, а ОТСЛЕЖИВАЕТ статусы; ни один
товар не должен быть с ошибкой; быстро и надёжно как швейцарские часы». Закрывает доказанное
живьём слепое пятно: card.card_quality РОНЯЕТ errors[], поэтому track/quality_report/verify_publish
были СЛЕПЫ к вердиктам ошибок карточки. reconcile читает и cardStatus, и errors[] и честно судит.

Тесты инъектируют cards_fn (ридер offer-cards) и sleep_fn → чистая классификация без сети и без сна:
  R1 clean            — PUBLISHED без ошибок → clean/none, «свои ошибки НЕТ».
  R2 frozen           — ERROR-статус + своя ошибка → frozen/rebuild (патч молча гибнет → полный ре-билд).
  R3 store_blocked    — только «Магазин отключён» → store_blocked/operator_cabinet, НЕ наша ошибка.
  R4 orphan_mixed     — И store-вердикт, И своя ошибка → store отделён, klass=frozen (нам чинить своё).
  R5 err_item_shape   — errors[] как dict-с-message И как голая строка — оба формата подняты (не теряем).
  R6 async_vs_frozen  — два чтения: processing→clean = асинхрон-лаг (settled), frozen→frozen = ре-билд.
  R7 store_all_live   — 5 живых бренд-закрытых SKU: витрина отключена целиком, наших ошибок 0.
  R8 missing_honesty  — запрошенный, но не вернувшийся SKU честно в missing (не выдаём за clean).
  R9 dry_gate         — живой путь (cards_fn=None) в dry/no-commit ЧЕСТНО отказывает ДО сети.
  R10 read_only       — СВЕРКА не трогает НИ ОДНОЙ write-руки (RUBICON: нет commit-пути записи).
  R11 delegate        — runner.reconcile — тонкая обёртка над write.reconcile (единый мозг, без дубля).
  R12 bare_error      — *_ERRORS с ПУСТЫМ errors[] → frozen/rebuild (ловим ЛОЖНУЮ зелень, не clean).
  R13 needs_placement — NO_CARD_ADD_TO_CAMPAIGN → needs_placement/place (размещение в кампании, не ре-билд).
  R14 store_nbsp      — «Магазин\xa0ОТКЛЮЧЁН» (nbsp+регистр) всё равно опознан как блок ВИТРИНЫ, не наша ошибка.
  R15 err_nonstr      — errors[] с НЕ-строковым message → без обвала, честно сериализован (текст виден).
  R16 warnings        — warnings[] подняты отдельно и НЕ роняют чистую карточку в ошибку.
  R17 disappeared     — битый в 1-м чтении и пропавший из 2-го → carried forward (не ложное «исцеление»).
  R18 storefront_unk  — storefront_moderation_unknown: включение витрины через API не видно (кабинет).
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_write_v1 as write      # noqa: E402
import ymarket_runner_v1 as runner    # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))


def card(offer_id, status, errors=None, rating=None):
    """Синтетическая строка offer_cards_status — форма живого offerCard (offerId/cardStatus/errors)."""
    return {"offerId": offer_id, "cardStatus": status, "errors": list(errors or []),
            "contentRating": rating}


NOSLEEP = lambda _s: None   # sleep_fn заглушка: тесты не ждут реальных секунд


print("ПРИЁМКА ЯНДЕКС — ПОСТ-ЗАЛИВОЧНАЯ СВЕРКА СТАТУСОВ\n")

# ── R1 · чистая карточка ──
print("R1 · PUBLISHED без ошибок → clean/none")
rep = write.reconcile(["A"], reread=False, cards_fn=lambda ids: [card("A", "PUBLISHED")])
v = rep["verdicts"][0]
check("R1: klass=clean action=none", v["klass"] == "clean" and v["action"] == "none",
      f"{v['klass']}/{v['action']}")
check("R1: свои ошибки НЕТ (all_clean_of_our_errors)", rep["all_clean_of_our_errors"] is True)
check("R1: строгий вердикт all_verified_clean=True (виден + чист)", rep["all_verified_clean"] is True)
check("R1: в clean_skus", rep["clean_skus"] == ["A"], str(rep["clean_skus"]))

# ── R2 · заморожена (ERROR-статус + своя ошибка) → полный ре-билд ──
print("\nR2 · NO_CARD_ERRORS + своя ошибка → frozen/rebuild")
rep = write.reconcile(["B"], reread=False, cards_fn=lambda ids: [
    card("B", "NO_CARD_ERRORS", [{"message": "Не заполнено обязательное поле"}])])
v = rep["verdicts"][0]
check("R2: klass=frozen action=rebuild", v["klass"] == "frozen" and v["action"] == "rebuild",
      f"{v['klass']}/{v['action']}")
check("R2: в needs_rebuild и frozen_skus", rep["needs_rebuild"] == ["B"] and rep["frozen_skus"] == ["B"])
check("R2: наша ошибка поднята дословно",
      v["our_errors"] == ["Не заполнено обязательное поле"], str(v["our_errors"]))
check("R2: all_clean_of_our_errors=False (есть наша ошибка)", rep["all_clean_of_our_errors"] is False)

# ── R3 · только «Магазин отключён» → вина витрины, НЕ карточки ──
print("\nR3 · только «Магазин отключён» → store_blocked/operator_cabinet, наших ошибок 0")
rep = write.reconcile(["C"], reread=False, cards_fn=lambda ids: [
    card("C", "HAS_CARD_CAN_UPDATE", ["Магазин отключён по результатам проверки"])])
v = rep["verdicts"][0]
check("R3: klass=store_blocked action=operator_cabinet",
      v["klass"] == "store_blocked" and v["action"] == "operator_cabinet", f"{v['klass']}/{v['action']}")
check("R3: НАШИХ ошибок нет (store-вердикт не в our_errors)", v["our_errors"] == [], str(v["our_errors"]))
check("R3: store-вердикт отделён в store_verdicts", len(v["store_verdicts"]) == 1, str(v["store_verdicts"]))
check("R3: all_clean_of_our_errors=True (витрина ≠ наша ошибка)", rep["all_clean_of_our_errors"] is True)
check("R3: НЕ в needs_rebuild (нам нечего чинить)", rep["needs_rebuild"] == [], str(rep["needs_rebuild"]))

# ── R4 · сирота: И store-вердикт, И своя ошибка одновременно ──
print("\nR4 · store-вердикт + своя ошибка → store отделён, klass=frozen (чиним СВОЁ)")
rep = write.reconcile(["D"], reread=False, cards_fn=lambda ids: [card(
    "D", "NO_CARD_ERRORS",
    ["Магазин отключён по результатам проверки", "Не\xa0заполнено обязательное поле"])])
v = rep["verdicts"][0]
check("R4: klass=frozen (своя ошибка при ERROR-статусе важнее store-блока)", v["klass"] == "frozen",
      v["klass"])
check("R4: store_blocked флаг поднят НЕЗАВИСИМО", v["store_blocked"] is True)
check("R4: наша ошибка в our_errors, store-вердикт — в store_verdicts",
      len(v["our_errors"]) == 1 and len(v["store_verdicts"]) == 1,
      f"our={v['our_errors']} store={v['store_verdicts']}")
check("R4: в needs_rebuild (свою карточку чинить)", rep["needs_rebuild"] == ["D"])
check("R4: одновременно в store_blocked_skus", rep["store_blocked_skus"] == ["D"])

# ── R5 · форма элемента errors[]: dict-с-message И голая строка ──
print("\nR5 · errors[] как dict (message/text/value/comment/description) И как строка — не теряем ни один")
mixed = [{"message": "M1"}, {"text": "M2"}, {"value": "M3"}, {"comment": "M4"},
         {"description": "M5"}, "M6-строка", {"weird": "zz"}]
rep = write.reconcile(["E"], reread=False, cards_fn=lambda ids: [card("E", "NO_CARD_ERRORS", mixed)])
v = rep["verdicts"][0]
check("R5: подняты ВСЕ 7 вердиктов (0 потеряно)", len(v["our_errors"]) == 7, str(v["our_errors"]))
for want in ("M1", "M2", "M3", "M4", "M5", "M6-строка"):
    check(f"R5: «{want}» на месте", want in v["our_errors"], str(v["our_errors"]))
check("R5: незнакомый dict не потерян (json-fallback c 'weird')",
      any("weird" in e for e in v["our_errors"]), str(v["our_errors"]))

# ── R6 · два чтения различают асинхрон-лаг от настоящей заморозки ──
print("\nR6 · два чтения: processing→clean = асинхрон (settled), frozen→frozen = ре-билд")
_calls = {"n": 0, "slept": []}


def _staged_reader(ids):
    """1-е чтение: ASYNC в обработке, FROZ заморожена. 2-е: ASYNC осела в clean, FROZ так и заморожена."""
    _calls["n"] += 1
    if _calls["n"] == 1:
        return [card("ASYNC", "NO_CARD_PROCESSING"),
                card("FROZ", "NO_CARD_ERRORS", [{"message": "Не заполнено обязательное поле"}])]
    return [card("ASYNC", "PUBLISHED"),
            card("FROZ", "NO_CARD_ERRORS", [{"message": "Не заполнено обязательное поле"}])]


rep = write.reconcile(["ASYNC", "FROZ"], reread=True, settle_wait=90,
                      cards_fn=_staged_reader, sleep_fn=lambda s: _calls["slept"].append(s))
by = {v["offerId"]: v for v in rep["verdicts"]}
check("R6: два чтения выполнены", _calls["n"] == 2, f"n={_calls['n']}")
check("R6: пауза оседания выждана (sleep_fn(90))", _calls["slept"] == [90], str(_calls["slept"]))
check("R6: settled=True (было пере-чтение)", rep["settled"] is True)
check("R6: ASYNC осела в clean (это был лаг, НЕ заморозка)",
      by["ASYNC"]["klass"] == "clean" and by["ASYNC"].get("settled_change") is True,
      f"{by['ASYNC']['klass']} settled_change={by['ASYNC'].get('settled_change')}")
check("R6: ASYNC помнит, что был processing (was)", by["ASYNC"].get("was") == "processing",
      str(by["ASYNC"].get("was")))
check("R6: FROZ так и заморожена → в needs_rebuild, settled_change=False",
      by["FROZ"]["klass"] == "frozen" and rep["needs_rebuild"] == ["FROZ"]
      and not by["FROZ"].get("settled_change"),
      f"{by['FROZ']['klass']} rebuild={rep['needs_rebuild']}")
check("R6: ASYNC НЕ попал в ре-билд (лаг ≠ поломка)", "ASYNC" not in rep["needs_rebuild"])

# ── R7 · живой кабинет: 5 бренд-закрытых SKU, витрина отключена целиком ──
print("\nR7 · 5 живых бренд-закрытых SKU: store_blocked_all, наших ошибок 0 (зеркало кабинета)")
live = ["9601478", "9601551", "9601575", "9601591", "9600132"]
rep = write.reconcile(live, reread=False, cards_fn=lambda ids: [
    card(s, "HAS_CARD_CAN_UPDATE", ["Магазин отключён по результатам проверки"]) for s in live])
check("R7: our_error_skus пуст (ни одной НАШЕЙ ошибки)", rep["our_error_skus"] == [],
      str(rep["our_error_skus"]))
check("R7: all_clean_of_our_errors=True", rep["all_clean_of_our_errors"] is True)
check("R7: store_blocked_all=True (вся витрина отключена)", rep["store_blocked_all"] is True)
check("R7: все 5 в store_blocked_skus", set(rep["store_blocked_skus"]) == set(live),
      str(rep["store_blocked_skus"]))
check("R7: needs_rebuild пуст (чинить нам нечего — это кабинет)", rep["needs_rebuild"] == [])

# ── R8 · честность missing: запрошенный, но не вернувшийся SKU ──
print("\nR8 · запрошен SKU, которого нет в ответе → honest missing (не clean)")
rep = write.reconcile(["A", "B", "GHOST"], reread=False, cards_fn=lambda ids: [
    card("A", "PUBLISHED"), card("B", "PUBLISHED")])
check("R8: GHOST честно в missing", rep["missing"] == ["GHOST"], str(rep["missing"]))
check("R8: наших ошибок среди вернувшихся нет", rep["all_clean_of_our_errors"] is True)
check("R8: НО строгий вердикт all_verified_clean=False (не все видны)",
      rep["all_verified_clean"] is False, str(rep["all_verified_clean"]))

# ── R9 · живой путь под гейтом: dry/no-commit отказывает ДО сети ──
print("\nR9 · cards_fn=None (живой путь): dry и no-commit честно отказывают, наружу 0")
rep_dry = write.reconcile(["X"], dry=True, commit=True)      # dry → отказ
rep_nc = write.reconcile(["X"], dry=False, commit=False)     # без --commit → отказ
check("R9: dry → ok=False, в note слово 'dry'", rep_dry.get("ok") is False and "dry" in rep_dry.get("note", ""),
      str(rep_dry))
check("R9: no-commit → ok=False, note про режим", rep_nc.get("ok") is False and bool(rep_nc.get("note")),
      str(rep_nc))

# ── R10 · СВЕРКА не трогает НИ ОДНОЙ write-руки (RUBICON: нет пути записи) ──
print("\nR10 · reconcile — чистый READ: 0 обращений к write-рукам (offer-mappings/cards/campaign/delete)")
spy = {"n": 0}


def _boom(*a, **k):
    spy["n"] += 1
    raise AssertionError("СВЕРКА не имеет права звать write-руку!")


saved = (write.hands.update_offer_mappings, write.hands.update_offer_cards,
         write.hands.update_campaign_offers, write.hands.delete_offer_mappings)
try:
    write.hands.update_offer_mappings = _boom
    write.hands.update_offer_cards = _boom
    write.hands.update_campaign_offers = _boom
    write.hands.delete_offer_mappings = _boom
    rep = write.reconcile(["A"], reread=False, cards_fn=lambda ids: [card("A", "PUBLISHED")])
    check("R10: СВЕРКА успешна как READ", rep.get("ok") is True)
    check("R10: НИ ОДНОГО обращения к write-руке (RUBICON цел)", spy["n"] == 0, f"calls={spy['n']}")
finally:
    (write.hands.update_offer_mappings, write.hands.update_offer_cards,
     write.hands.update_campaign_offers, write.hands.delete_offer_mappings) = saved

# ── R11 · обёртка runner.reconcile делегирует в write.reconcile (единый мозг) ──
print("\nR11 · runner.reconcile — тонкая обёртка над write.reconcile (без дубля логики)")
rep = runner.reconcile(["A"], reread=False, cards_fn=lambda ids: [card("A", "PUBLISHED")]) \
    if "cards_fn" in runner.reconcile.__code__.co_varnames else None
if rep is None:
    # обёртка не пробрасывает cards_fn (по дизайну) — проверим делегирование через dry-гейт
    rep = runner.reconcile(["A"], dry=True, commit=True)
    check("R11: runner.reconcile делегирует (dry-гейт отдаёт note)", rep.get("ok") is False and "dry" in rep.get("note", ""),
          str(rep))
else:
    check("R11: runner.reconcile проксирует до чистого вердикта", rep.get("ok") is True and rep["clean_skus"] == ["A"],
          str(rep.get("clean_skus")))

# ── R12 · FIX-1 · ERROR-статус с ПУСТЫМ errors[] → frozen (ловим ЛОЖНУЮ зелень) ──
print("\nR12 · NO_CARD_ERRORS с ПУСТЫМ errors[] → frozen/rebuild (пустой список ≠ «чисто»)")
rep = write.reconcile(["Z"], reread=False, cards_fn=lambda ids: [card("Z", "NO_CARD_ERRORS", [])])
v = rep["verdicts"][0]
check("R12: klass=frozen action=rebuild (ERROR-статус без видимых ошибок ≠ clean)",
      v["klass"] == "frozen" and v["action"] == "rebuild", f"{v['klass']}/{v['action']}")
check("R12: в needs_rebuild и error_skus", rep["needs_rebuild"] == ["Z"] and rep["error_skus"] == ["Z"])
check("R12: НЕ ложный ✅ — all_clean_of_our_errors=False, all_verified_clean=False",
      rep["all_clean_of_our_errors"] is False and rep["all_verified_clean"] is False)
check("R12: НЕ утёк в clean_skus", rep["clean_skus"] == [], str(rep["clean_skus"]))

# ── R13 · FIX-6 · NO_CARD_ADD_TO_CAMPAIGN → needs_placement/place (разместить, не ре-билд) ──
print("\nR13 · NO_CARD_ADD_TO_CAMPAIGN → needs_placement/place (контент готов, лечится размещением)")
rep = write.reconcile(["P"], reread=False, cards_fn=lambda ids: [card("P", "NO_CARD_ADD_TO_CAMPAIGN")])
v = rep["verdicts"][0]
check("R13: klass=needs_placement action=place",
      v["klass"] == "needs_placement" and v["action"] == "place", f"{v['klass']}/{v['action']}")
check("R13: в needs_placement, НЕ в needs_rebuild",
      rep["needs_placement"] == ["P"] and rep["needs_rebuild"] == [])
check("R13: размещение ≠ НАША ошибка (all_clean_of_our_errors=True)", rep["all_clean_of_our_errors"] is True)
check("R13: но не «часы» — all_verified_clean=False (ещё не размещён)", rep["all_verified_clean"] is False)

# ── R14 · FIX-4 · store-вердикт с NBSP и в другом регистре всё равно опознан ──
print("\nR14 · «Магазин\\xa0ОТКЛЮЧЁН…» (nbsp+регистр) → store_blocked (не ложный ре-билд чистой карточки)")
rep = write.reconcile(["N"], reread=False, cards_fn=lambda ids: [
    card("N", "HAS_CARD_CAN_UPDATE", ["Магазин\xa0ОТКЛЮЧЁН по результатам проверки"])])
v = rep["verdicts"][0]
check("R14: klass=store_blocked (nbsp/регистр не спрятали блок)", v["klass"] == "store_blocked", v["klass"])
check("R14: store-вердикт НЕ утёк в our_errors", v["our_errors"] == [], str(v["our_errors"]))
check("R14: needs_rebuild пуст (чинить нам нечего)", rep["needs_rebuild"] == [])

# ── R15 · FIX-5 · errors[] с НЕ-строковым message → не падаем, сериализуем честно ──
print("\nR15 · errors[] element {'message': {...}} (не строка) → без AttributeError, текст вердикта виден")
rep = write.reconcile(["W"], reread=False, cards_fn=lambda ids: [
    card("W", "NO_CARD_ERRORS", [{"message": {"nested": "boom"}}, {"code": 500}])])
v = rep["verdicts"][0]
check("R15: сверка не упала, вернула вердикт frozen", rep.get("ok") is True and v["klass"] == "frozen",
      f"ok={rep.get('ok')} klass={v['klass']}")
check("R15: кривой message сериализован (виден 'boom'/'nested')",
      any("boom" in e or "nested" in e for e in v["our_errors"]), str(v["our_errors"]))
check("R15: второй кривой вердикт ({'code':500}) тоже поднят",
      any("500" in e or "code" in e for e in v["our_errors"]), str(v["our_errors"]))

# ── R16 · FIX-7 · warnings[] подняты отдельно, но НЕ блокируют (карточка остаётся clean) ──
print("\nR16 · warnings[] захвачены отдельно, не роняют чистую карточку в ошибку")
rep = write.reconcile(["G"], reread=False, cards_fn=lambda ids: [
    {"offerId": "G", "cardStatus": "PUBLISHED", "errors": [],
     "warnings": [{"message": "рекомендуем добавить видео"}, "мало фото"]}])
v = rep["verdicts"][0]
check("R16: карточка остаётся clean (warnings ≠ ошибка)", v["klass"] == "clean", v["klass"])
check("R16: оба warning подняты в v['warnings']",
      set(v["warnings"]) == {"рекомендуем добавить видео", "мало фото"}, str(v["warnings"]))
check("R16: all_clean_of_our_errors=True (варнинги не считаются нашей ошибкой)",
      rep["all_clean_of_our_errors"] is True)

# ── R17 · FIX-2 · битый в 1-м чтении и пропавший из 2-го → carried forward (не «исцелился») ──
print("\nR17 · frozen в 1-м чтении исчез из 2-го среза (пагинация) → disappeared, НЕ ложная зелень")
_c = {"n": 0}


def _shrinking_reader(ids):
    """1-е чтение: H1 чистая + H2 заморожена. 2-е чтение (срез/пагинация) НЕ вернуло битый H2."""
    _c["n"] += 1
    if _c["n"] == 1:
        return [card("H1", "PUBLISHED"),
                card("H2", "NO_CARD_ERRORS", [{"message": "Не заполнено обязательное поле"}])]
    return [card("H1", "PUBLISHED")]


rep = write.reconcile([], reread=True, settle_wait=90, cards_fn=_shrinking_reader, sleep_fn=NOSLEEP)
by = {v["offerId"]: v for v in rep["verdicts"]}
check("R17: H2 перенесён вперёд, не потерян", "H2" in by, str(list(by)))
check("R17: H2 помечен disappeared и в списке disappeared",
      by.get("H2", {}).get("disappeared") is True and rep["disappeared"] == ["H2"], str(rep.get("disappeared")))
check("R17: H2 в needs_rebuild, all_verified_clean=False (пропажа битого ≠ исцеление)",
      rep["needs_rebuild"] == ["H2"] and rep["all_verified_clean"] is False)

# ── R18 · FIX-3 · storefront_moderation_unknown — честный флаг «включение витрины API не видит» ──
print("\nR18 · storefront_moderation_unknown: отсутствие store-вердикта ≠ «витрина жива»")
rep_no = write.reconcile(["A"], reread=False, cards_fn=lambda ids: [card("A", "PUBLISHED")])
check("R18: без store-вердикта → unknown=True (модерация витрины через API не видна)",
      rep_no["storefront_moderation_unknown"] is True)
check("R18: есть текст-оговорка про кабинет", "кабинет" in rep_no.get("storefront_caveat", ""))
rep_blk = write.reconcile(["C"], reread=False, cards_fn=lambda ids: [
    card("C", "HAS_CARD_CAN_UPDATE", ["Магазин отключён по результатам проверки"])])
check("R18: увиден store-вердикт → unknown=False (блок известен явно)",
      rep_blk["storefront_moderation_unknown"] is False)

# ============================================================================
# ИТОГ
# ============================================================================
print("\n" + "=" * 70)
print(f"ЯНДЕКС ПОСТ-ЗАЛИВОЧНАЯ СВЕРКА: {len(PASS)}/{len(PASS) + len(FAIL)} зелёных")
if FAIL:
    print("КРАСНЫЕ:")
    for f in FAIL:
        print(f"  ❌ {f}")
    sys.exit(1)
print("✅ статусы отслеживаются, наши ошибки отделены от операторского store-блока, асинхрон-лаг "
      "отличён от заморозки, missing честен, живой путь под гейтом, RUBICON держит (0 записи)")

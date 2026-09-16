#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИЁМКА — ГЕЙТ СВЕРКИ ЦИКЛ-1 ПОСЛЕ ULTRA-АУДИТА. Сухо, 0₽, без сети, герметично.

Проверяет три подтверждённые находки аудита, исправленные в node_verify движка:

  FIX-C (verify_slice:577)  — карточка на витрине (placement PUBLISHED+available+остаток FIT), а
        offer-mappings НЕ вернул строку content. Раньше — тихий `continue` → ложный PASS + фраза
        «имя/цена/…/параметры на месте». Теперь — честный FAIL «БЕЗ контент-среза».
  FIX-E (price:578/514)     — живая цена ≠ плану задумки НЕ гейт (донор мог сменить cost) → PASS,
        но в note честный маркер «ЦЕНА ЖИВЬЁМ ≠ ПЛАН» + evidence.price_drift (переценку решает
        ЦЕНОВИК/ДЕНЬ). Плюс SETTLE≈90с: СВЕРКА спит ТОЛЬКО когда этот прогон реально писал
        живьём (dry=False И commit=True); сухие/автопилот (0₽) сна не делают.
  FIX-B (env_write_gate:877)— `--dry --commit` в CLI ВЗАИМОИСКЛЮЧАЮЩИ: argparse сам отклонит (rc 2)
        ДО запуска движка (раньше --dry был мёртв и пара уходила ЖИВЬЁМ).
  PASS-ГЕЙТ (04.09, VG6) — карточка на витрине, а её блоки СВЕРКА НЕ собрала чтением
        (audit_live UNVERIFIED, напр. спеки при недоступном offer-cards) → НЕ молча PASS:
        вердикт FAIL «блоки не собраны чтением» (закон оператора «сделай чтобы система
        законно не врала»). Это НЕ «карточка плохая» — чтение не доказало полноту; повторный
        прогон при поднявшемся чтении решает.

Фикстура повторяет живой срез СВЕРКИ (#33) той же формы, что кладёт node_verify (placement из
campaign_offers, content из offer-mappings, spec_n из offer-cards, остаток из read_stocks).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
for p in (str(ARB),):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_cycle1_v1 as C1          # noqa: E402
import ymarket_hands_v1 as H            # noqa: E402
import ymarket_trade_hands_v1 as T      # noqa: E402

SKU = "ARB-77700001"
PLAN = 4800.0
WH = 2390811
BID, CID = 216949599, 149215943


def _ctx(plan_price=PLAN):
    return {"profile": {"business_id": BID, "campaign_id": CID, "warehouse_id": WH},
            "prods": [{"sku": SKU, "price": plan_price}]}


def _full_offer(live_price=PLAN):
    """Оффер, из которого node_verify соберёт ПОЛНЫЙ content-срез (COMPLETE для audit_live)."""
    return {"offerId": SKU, "name": "Воздушно-пузырьковая плёнка 100 м × 0,75 м, двухслойная",
            "vendor": "Без бренда", "description": "Плёнка для упаковки. " * 10,
            "pictures": [f"https://img.example/{i}.jpg" for i in range(4)],
            "barcodes": ["4607000000000"],
            "weightDimensions": {"length": 50, "width": 35, "height": 50, "weight": 1.438},
            "basicPrice": {"value": live_price, "currency": "RUR"}}


def _orig():
    return {"co": H.campaign_offers, "req": H._request, "ocs": H.offer_cards_status,
            "rs": T.read_stocks, "sleep": C1.time.sleep}


def _stub(co_offers, req_result, ocs_cards, stock_rows, plan_price, dry, commit):
    """Подменяет сеть/сон и гонит node_verify. Возврат (r, sleeps). Снимок — ДО подмены."""
    saved = _orig()
    H.campaign_offers = lambda cid, offer_ids=None, limit=None: {"offers": co_offers}
    H._request = lambda method, path, body=None, params=None: req_result
    # callable ocs_cards = "поднять исключение" (fail-soft offer-cards), иначе — его возврат
    if callable(ocs_cards):
        H.offer_cards_status = ocs_cards
    else:
        H.offer_cards_status = lambda bid, offer_ids=None, limit=None: ocs_cards
    T.read_stocks = lambda bid, wh, offer_ids=None: stock_rows
    sleeps = []
    C1.time.sleep = lambda s: sleeps.append(s)
    try:
        r = C1.node_verify(_ctx(plan_price), dry=dry, commit=commit)
        return r, sleeps
    finally:
        H.campaign_offers, H._request, H.offer_cards_status = saved["co"], saved["req"], saved["ocs"]
        T.read_stocks = saved["rs"]
        C1.time.sleep = saved["sleep"]


def _placement_offer(live_price=PLAN):
    return {"offerId": SKU, "available": True, "status": "PUBLISHED",
            "basicPrice": {"value": live_price, "currency": "RUR"}}


def _mapping(content_offer):
    return {"result": {"offerMappings": [{"offer": content_offer}]}}


def _specs(n=13):
    return [{"offerId": SKU, "cardStatus": "HAS_CARD_CAN_UPDATE",
             "parameterValues": [{} for _ in range(n)]}]


def _stock_fit():
    return [{"type": "FIT", "sku": SKU, "count": 100}]


def _passed(c):
    return "✅ PASS" if c else "❌ FAIL"


def vg1_full_slice_pass():
    # ВСЕ блоки на месте, цена = план → PASS, полностью ПОДТВЕРЖДЕНЫ, дрейфа нет, сна НЕТ (dry)
    r, sleeps = _stub([_placement_offer()], _mapping(_full_offer()),
                      _specs(), _stock_fit(), PLAN, dry=True, commit=False)
    note = r.get("note", "")
    ok = (r.get("verdict") == "PASS" and "ПОДТВЕРЖДЕНЫ полностью" in note
          and "ЦЕНА ЖИВЬЁМ" not in note and sleeps == [])
    return ok, f"verdict={r.get('verdict')} sleeps={len(sleeps)} · {note[:120]}"


def vg2_no_content_honest_fail():
    # карточка на витрине (placement+остаток ок), offer-mappings вернул ПУСТО, а offer-cards
    # отвечает (каталог)! Раньше offer-cards ФАБРИКОВАЛ content из чужой spec_n → ложный PASS.
    # Теперь spec_n в content кладётся только при живой маппинг-строке → честный FAIL no_content.
    empty = {"result": {"offerMappings": []}}
    r, _ = _stub([_placement_offer()], empty, _specs(), _stock_fit(), PLAN, dry=True, commit=False)
    note = r.get("note", "")
    ok = (r.get("verdict") == "FAIL" and "БЕЗ контент-среза" in note and SKU in note)
    return ok, f"verdict={r.get('verdict')} · {note[:140]}"


def vg3_price_drift_not_fail():
    # полный срез, но живая цена (3300) ≠ план (4800): PASS + честный маркер дрейфа (НЕ гейт)
    # + evidence price_ok=False/price_plan=4800 на самой карточке.
    r, _ = _stub([_placement_offer(3300)], _mapping(_full_offer(3300)),
                 _specs(), _stock_fit(), PLAN, dry=True, commit=False)
    note = r.get("note", "")
    cont = (r.get("evidence") or {}).get(SKU, {}).get("content", {})
    ok = (r.get("verdict") == "PASS" and "ЦЕНА ЖИВЬЁМ ≠ ПЛАН" in note
          and cont.get("price_ok") is False and cont.get("price_plan") == PLAN)
    return ok, f"verdict={r.get('verdict')} content_price={cont.get('price')} plan={cont.get('price_plan')} ok={cont.get('price_ok')} · {note[:110]}"


def vg4_settle_only_live_write():
    # SETTLE: сон ТОЛЬКО когда этот прогон реально писал живьём (dry=False И commit=True).
    # dry-автопилот (0₽) сна не делает; dry=False/commit=False (фейк-путь, ничего не слали) — тоже.
    def run(dry, commit):
        return _stub([_placement_offer()], _mapping(_full_offer()),
                     _specs(), _stock_fit(), PLAN, dry=dry, commit=commit)
    _, s_dry = run(dry=True, commit=False)
    _, s_fake = run(dry=False, commit=False)
    _, s_live = run(dry=False, commit=True)
    ok = (s_dry == [] and s_fake == [] and s_live == [C1.CYCLE_SETTLE_SEC])
    return ok, (f"dry={s_dry} fake(commit=False)={s_fake} live(commit=True)="
                f"{s_live} (сеттл только после реального живого залива)")


def vg5_cli_dry_commit_mutually_exclusive():
    # Парсер (build_parser): `--dry --commit` → SystemExit 2 ДО запуска (раньше --dry был мёртв
    # и пара УХОДИЛА ЖИВЬЁМ). Поодиночке — каждый принимается, дефолт остаётся dry.
    p = C1.build_parser()
    try:
        p.parse_args(["--dry", "--commit"])
        rc_pair = None
    except SystemExit as e:
        rc_pair = e.code
    a_dry = p.parse_args(["--dry"])
    a_com = p.parse_args(["--commit"])
    a_none = p.parse_args([])
    ok = (rc_pair == 2 and a_dry.dry and not a_dry.commit
          and a_com.commit and not a_com.dry and not a_none.commit)
    return ok, (f"пара --dry --commit → rc={rc_pair}; --dry → commit={a_dry.commit}; "
                f"--commit → dry={a_com.dry}; пусто → commit={a_none.commit} (дефолт dry)")


def vg6_unverified_blocks_no_silent_pass():
    # Карточка НА витрине (PUBLISHED+available+остаток FIT) и контент ПОЛОН (имя/цена/описание/
    # фото/штрихкод/габариты), но offer-cards НЕДОСТУПЕН (сеть, fail-soft) → spec_n не собран →
    # audit_live честно: UNVERIFIED (полнота спеками не подтверждена). Раньше — тихий PASS
    # «полнота N/N». ЗАКОН PASS-ГЕЙТА (04.09, «сделай чтобы система законно не врала»):
    # UNVERIFIED-блок НЕ даёт молча PASS → вердикт FAIL «блоки не собраны чтением»; повторный
    # прогон, когда чтение поднимется, решает (это НЕ «карточка плохая»).
    def ocs_down(bid, offer_ids=None, limit=None):
        raise RuntimeError("offer-cards: сеть недоступна")

    r, sleeps = _stub([_placement_offer()], _mapping(_full_offer()),
                      ocs_down, _stock_fit(), PLAN, dry=True, commit=False)
    note = r.get("note", "")
    ev = r.get("evidence") or {}
    unk = (ev.get("unverified") or {}).get(SKU) or []
    ok = (r.get("verdict") == "FAIL" and "UNVERIFIED" in note
          and "не собраны чтением" in note and ev.get("n_unverified") == 1
          and unk == ["specs"] and sleeps == [])
    return ok, (f"verdict={r.get('verdict')} n_unverified={ev.get('n_unverified')} "
                f"unknown={unk} · {note[:150]}")


# ── КОНТРОЛЬ (N7): зелёный ценник / цена-эталон / акции (директива оператора 08.09) ──

def _ctrl_ctx():
    return {"profile": {"business_id": BID, "campaign_id": CID, "warehouse_id": WH},
            "prods": [], "results": []}


def _ctrl_stub(offers, promos, lib_goods=None, dry=True, commit=False):
    """Подменяет сеть offer-prices/promos + update_prices + библиотеку (tmp) и гонит node_control.
    Возврат (r, calls). Патч-снимок до подмены, восстановление в finally — герметично."""
    saved = {"req": H._request, "up": T.update_prices}
    calls = {"update_prices": None}

    def req(method, path, body=None, params=None, timeout=None):
        if "offer-prices" in path:
            return {"status": "OK", "result": {"offers": offers}}
        if "promos" in path:
            return {"status": "OK", "result": {"promos": promos}}
        raise AssertionError(f"неожиданный путь КОНТРОЛЯ: {path}")

    def fake_update(bid, offers_, dry=dry, commit=commit, timeout=60):
        calls["update_prices"] = offers_
        return {"status": "sent", "sent": True, "ok": True}

    H._request = req
    T.update_prices = fake_update
    tmp = tempfile.TemporaryDirectory()
    lib_file = Path(tmp.name) / "lib.json"
    lib_file.write_text(json.dumps(
        {"schema": "ymarket.goods.library.v1", "goods": lib_goods or {}}))
    os.environ["YM_LIBRARY_PATH"] = str(lib_file)
    try:
        r = C1.node_control(_ctrl_ctx(), dry=dry, commit=commit)
        return r, calls
    finally:
        H._request = saved["req"]
        T.update_prices = saved["up"]
        os.environ.pop("YM_LIBRARY_PATH", None)
        tmp.cleanup()


def _price_offer(oid, value, base=None):
    pr = {"value": value, "currencyId": "RUR"}
    if base is not None:
        pr["discountBase"] = base
    return {"offerId": oid, "price": pr}


def vg7_control_green_dry_report():
    # ЖИВОЙ offer-prices видит легаси-ценник 9601515-1 (discountBase) — зелёный ценник.
    # СУХОЙ ход: PASS + evidence.green (факт), update_prices НЕ вызывался (0₽, RUBICON цел).
    r, calls = _ctrl_stub(
        [_price_offer("9601515-1", 3390, 4900), _price_offer("ARB-77700001", 4800)],
        [{"id": "p1", "name": "Бестселлеры", "participating": False}])
    ev = r.get("evidence") or {}
    ok = (r.get("verdict") == "PASS"
          and ev.get("green", {}).get("9601515-1", {}).get("base") == 4900
          and "зелёных ценников" in r.get("note", "")
          and calls["update_prices"] is None)
    return ok, (f"verdict={r.get('verdict')} green={ev.get('green')} "
                f"update_prices вызван={calls['update_prices'] is not None} · {r.get('note', '')[:110]}")


def vg8_control_green_live_clears():
    # ЖИВОЙ ход (--commit, RUBICON): зелёный ценник СНОСИТСЯ — update_prices БЕЗ discountBase
    # (value не меняется → карантина цен нет), evidence.cleared, честно «подтвердить чтением».
    r, calls = _ctrl_stub(
        [_price_offer("9601515-1", 3390, 4900)],
        [{"id": "p1", "name": "Бестселлеры", "participating": False}],
        dry=False, commit=True)
    ev = r.get("evidence") or {}
    payload = calls["update_prices"] or []
    no_db = all("discount_base" not in o and "discountBase" not in o for o in payload)
    ok = (r.get("verdict") == "PASS" and ev.get("cleared") == ["9601515-1"]
          and len(payload) == 1 and payload[0]["sku"] == "9601515-1"
          and payload[0]["value"] == 3390 and no_db
          and "подтвердить чтением" in r.get("note", ""))
    return ok, (f"cleared={ev.get('cleared')} payload={payload} (без discountBase: {no_db}) "
                f"· {r.get('note', '')[:110]}")


def vg9_control_below_plan_and_promos():
    # Карточка библиотеки (cost=100, markup=8 → эталон 800) живьём 500₽ → клиент платит меньше
    # выгодной → evidence.below_plan (факт для ЦЕНОВИКА, не FAIL). Акция participating=true →
    # evidence.promos.participating=1 (кабинет, не API). Чистая витрина — «зелёных ценников 0».
    lib = {"ARB-77700001": {"cost": 100.0, "markup": 8.0}}
    r, _ = _ctrl_stub(
        [_price_offer("ARB-77700001", 500), _price_offer("9601515-1", 3390)],
        [{"id": "p1", "name": "Бестселлеры", "participating": True}],
        lib_goods=lib, dry=True, commit=False)
    ev = r.get("evidence") or {}
    bp = ev.get("below_plan") or {}
    ok = (r.get("verdict") == "PASS" and bp.get("ARB-77700001", {}).get("plan") == 800.0
          and ev.get("promos", {}).get("participating") == 1
          and "зелёных ценников 0" in r.get("note", "")
          and "ниже эталона" in r.get("note", ""))
    return ok, (f"below_plan={bp} promos_participating={ev.get('promos', {}).get('participating')} "
                f"· {r.get('note', '')[:130]}")


def _run():
    tests = [("VG1 full_slice_pass", vg1_full_slice_pass),
             ("VG2 no_content_honest_fail", vg2_no_content_honest_fail),
             ("VG3 price_drift_not_fail", vg3_price_drift_not_fail),
             ("VG4 settle_only_live_write", vg4_settle_only_live_write),
             ("VG5 cli_dry_commit_exclusive", vg5_cli_dry_commit_mutually_exclusive),
             ("VG6 unverified_no_silent_pass", vg6_unverified_blocks_no_silent_pass),
             ("VG7 контроль: dry отчёт", vg7_control_green_dry_report),
             ("VG8 контроль: живой снос", vg8_control_green_live_clears),
             ("VG9 контроль: эталон+акции", vg9_control_below_plan_and_promos)]
    fails = 0
    for name, fn in tests:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(f"  {_passed(ok)} {name:<28} {detail}")
        fails += 0 if ok else 1
    print(f"\nСВЕРКА-ГЕЙТ (FIX-B/C/E + PASS-ГЕЙТ 04.09 + КОНТРОЛЬ 08.09): {len(tests) - fails}/{len(tests)} зелёных")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run())

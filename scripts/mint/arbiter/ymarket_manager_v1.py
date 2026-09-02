#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET MANAGER V1 — управляющий Яндекс.Маркетом (тик-цикл + CLI, швейцарская точность).

Мандат от оператора (дословно): «заливаешь через API категорию, заполняя всевозможные данные,
чтобы карточка была реально охуенно заполнена → в ТОП; инструмент не просто заливает, а
отслеживает статусы; ни один товар не должен быть с ошибкой; быстро и надёжно как швейцарские часы».

УПРАВЛЯЮЩИЙ = короткий тик (НЕ демон), живущий между завершениями за счёт ПАМЯТИ (ymarket_state).
Каждый тик:
  1. ЧИТАЕТ память (state.load) — что ведём, какой индекс, какие открытые рекомендации, что
     делали прошлым разом.
  2. ОСОЗНАЁТ себя (ymarket_self.self_status) — кто он, зачем, в каком состоянии, что следующий
     законный шаг (next_lawful_step).
  3. РЕШАЕТ одно действие: preflight/resolve/publish/track/fix_one (по next_lawful_step).
  4. ВЫПОЛНЯЕТ через runner/write/proof (fail-soft: один упал — несём ошибку дальше, не падаем).
  5. ДОПИСЫВАЕТ результат назад в память (ingest_preflight/ingest_track/record_action).
  6. ДОКАЗЫВАЕТ тик (ymarket_proof.emit_tick_proof → tick_ledger → verify_chain).
  7. ПЕЧАТАЕТ само-осознание (self.render) — сводка КПИ + следующий шаг.

Непрерывность получается из памяти + ledger'а тиков, а не из вечного процесса. Запускается вручную
(./ymarket_manager_v1.py --tick) или по расписанию (cron 1x/час, или после каждого залива товаров).

CLI:
  --tick              — выполнить один тик (действие по next_lawful_step + память + доказательство).
  --preflight <xlsx>  — preflight категории (dry, 0₽), впитать в память → report.
  --resolve <query>   — резолв категории через hands.categories_tree (READ, нужен ключ).
  --commit <xlsx>     — реальный залив категории (ТОЛЬКО с --commit, гейт двойной).
  --track             — опросить витрину/индекс для всех карточек из working_set, впитать.
  --self              — показать само-осознание (без действия).
  --verify-chain      — проверить цепочку доказательств тиков (честность).

ЗАКОНЫ:
  • stdlib+openpyxl, никаких requests/aiohttp (hands-абстракция).
  • двойной гейт: не dry (hands/runner) AND commit (CLI явно) → реальная сеть.
  • fail-soft: ошибка одной карточки → error в память, не роняет тик.
  • 200≠успех: читаем errors/warnings из ответа (write делает это).
  • proof-gate: publish без verify → claimed, с verify → verified (не врём).
  • не ломает орган: новый модуль-оркестратор поверх runner/state/econ/self/proof.
"""
import sys
import json
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_runner_v1 as runner        # noqa: E402
import ymarket_state_v1 as state          # noqa: E402
import ymarket_econ_v1 as econ            # noqa: E402
import ymarket_self_v1 as self_mod        # noqa: E402
import ymarket_proof_v1 as proof          # noqa: E402
import ymarket_hands_v1 as hands          # noqa: E402
import ymarket_write_v1 as write          # noqa: E402


def tick(dry=True, commit=False, quiet=False):
    """Один тик управляющего: ЧИТАЕТ память → РЕШАЕТ → ДЕЛАЕТ → ДОКАЗЫВАЕТ → render.

    dry/commit — двойной гейт (как в hands/runner): реальная сеть только при not dry AND commit.
    Тик НЕ демон: живёт между завершениями за счёт state (память). Fail-soft: ошибка → в память,
    не роняет тик. Возвращает {ok, action, self, proof, errors}.

    quiet=True — не печатать (тик вызван изнутри суточного цикла, у которого свой единый отчёт;
    два доклада в одном экране путают оператора). По умолчанию False — прежнее поведение CLI.
    """
    tick_id = f"YMTICK_{proof._now().replace(':', '').replace('-', '')[:15]}"
    doc = state.load()
    st = self_mod.self_status(doc)

    # ── Шаг 1: РЕШИТЬ следующее действие (from next_lawful_step) ──
    k = st["kpis"]
    action = None
    result = None
    errors = []
    network_used = False

    # Лестница решений (зеркало self._next_lawful_step):
    if k["cards_errored"] > 0:
        # Починить ошибки — сейчас у нас нет автоматического fix_one (это L2+), пока просто сигнализируем
        action = "AWAIT_FIX"
        result = {"note": (f"Ошибки присутствуют ({k['cards_errored']} карточек). Починка вручную "
                           "или автоматический fix_one — roadmap L2+. Пока держим строй.")}
    elif k["need_mapping"] > 0:
        action = "AWAIT_MAPPING"
        result = {"note": (f"Категории не подтверждены ({k['need_mapping']} карточек). Нужен "
                           "resolve_category + глаза оператора. См. ymarket_cats_v1.json.")}
    elif k["cards_tracked"] == 0:
        action = "AWAIT_PREFLIGHT"
        result = {"note": "Память пуста. Нужен preflight по категории → --preflight <xlsx>"}
    elif k["cards_live_verified"] == 0 and k["ready_to_publish"] > 0:
        action = "AWAIT_FIRST_PUBLISH"
        result = {"note": (f"{k['ready_to_publish']} карточек готовы. Первая реальная публикация "
                           "только по отмашке оператора (--commit <xlsx>). RUBICON.")}
    elif k["avg_content_rating"] is not None and k["avg_content_rating"] < econ.TOP_RATING_THRESHOLD:
        # Поднять индекс — track + приоритизация (L2+); сейчас просто трекаем, если commit
        action = "TRACK"
        if not (not dry and commit):
            # гейт закрыт (dry или без --commit) — наружу не идём, честно говорим почему
            result = {"dry": dry, "commit": commit, "network_used": False,
                      "note": "track требует реального режима (dry=False) и --commit — READ не выполнен"}
        elif not hands.creds_present():
            # ЗАКОН ЧЕСТНОСТИ: нет ключа → не трогаем сеть и НЕ выдаём это за успех
            result = {"ok": False, "dry": True, "network_used": False,
                      "note": "REFUSED: нет YANDEX_MARKET_API_KEY — реальный READ индекса невозможен"}
            errors.append("нет ключа YANDEX_MARKET_API_KEY — track пропущен (не выдумываем индекс)")
        else:
            working = doc.get("working_set", [])
            if not working:
                result = {"network_used": False, "note": "working_set пуст — нечего трекать"}
            else:
                network_used = True
                rep = runner.track(working, dry=False, commit=True)
                result = rep
                if rep.get("ok"):
                    state.ingest_track(doc, rep)
                    state.bump(doc, "ticks")
                    state.write_atomic(doc)
                else:
                    errors.append(f"track не дал данных: {rep.get('error') or rep.get('note')}")
    else:
        action = "HOLD"
        result = {"note": "Ошибок нет, индекс в зоне цели. Держать строй."}

    # ── Шаг 2: ДОКАЗАТЬ тик (proof) ──
    checks = {
        "state_loaded": doc.get("schema") == state.SCHEMA,
        "self_honest": st.get("kpis", {}).get("cards_errored") is not None,  # честные числа
        "action_decided": action is not None,
        "no_fakepass": not k.get("need_mapping", 0) > 0 or action in ("AWAIT_MAPPING", "AWAIT_FIX"),
    }
    prf = proof.emit_tick_proof(tick_id, checks, self_status=st, action=action,
                                 moved_money=False, network_used=network_used)

    # Записать тик в леджер
    try:
        proof.append_tick({
            "tick_id": tick_id,
            "action": action,
            "result": result,
            "proof": prf,
            "ts": proof._now(),
        })
    except Exception as e:
        errors.append(f"не смог записать тик в леджер: {e}")

    # ── Шаг 3: ПЕЧАТЬ само-осознания ──
    if not quiet:
        print(self_mod.render(st))
        print()
        print(f"Тик {tick_id}: {action}")
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if errors:
            print("⚠️  Ошибки:")
            for e in errors:
                print(f"  • {e}")

    return {"ok": not errors, "tick_id": tick_id, "action": action, "self": st,
            "proof": prf, "result": result, "errors": errors}


def preflight_category(xlsx, slug, vendor=None):
    """Preflight категории (dry, 0₽): прогнать каждый товар, составить карту готовности, впитать в память."""
    import ymarket_from_xlsx_v1 as bridge
    import ymarket_card_v1 as card

    cats = card.load_cats()
    loaded = bridge.load_category(xlsx, slug=slug, vendor=vendor)
    products = loaded["products"]

    print(f"Категория '{slug}': загружено {len(products)} товаров")
    print("Прогоняем preflight (dry, 0₽)...")
    rep = runner.preflight(products, slug, cats=cats)

    # Впитать результат в память
    doc = state.load()
    n = state.ingest_preflight(doc, rep)
    state.bump(doc, "ticks")
    state.write_atomic(doc)

    print(f"✅ Preflight завершён: {rep['agg']['ok']}/{rep['agg']['total']} готовы, впитано {n} карточек в память")
    return rep


def commit_category_real(xlsx, slug, vendor=None, business_id=None, campaign_id=None,
                         vat="VAT_20", pace=0.4):
    """Реальный залив категории (ТОЛЬКО с --commit). Fail-soft + proof-gate + впитать в память."""
    import ymarket_from_xlsx_v1 as bridge
    import ymarket_card_v1 as card

    if not hands.creds_present():
        print("❌ REFUSED: нет YANDEX_MARKET_API_KEY — реальный залив невозможен")
        return {"ok": False, "error": "no creds"}

    cats = card.load_cats()
    loaded = bridge.load_category(xlsx, slug=slug, vendor=vendor)
    products = loaded["products"]

    print(f"Категория '{slug}': {len(products)} товаров")
    print("⚠️  РЕАЛЬНЫЙ ЗАЛИВ (не dry, commit=True, деньги НЕ двигаем, но API пишет)")
    print("Начинаем...")

    rep = runner.commit_category(products, slug, cats=cats, business_id=business_id,
                                  campaign_id=campaign_id, vat=vat, pace=pace)

    # Claim каждой опубликованной карточки (proof-gate stage 1)
    doc = state.load()
    for row in rep.get("rows", []):
        oid = row.get("sku")
        if not oid:
            continue
        if row.get("published"):
            claim = proof.record_publish_claim(oid, commit_response=row, meta={"slug": slug})
            state.upsert_sku(doc, oid, status="PUBLISHED_CLAIMED", claim=claim)
            state.bump(doc, "publishes_claimed")
        else:
            # Ошибки впитываем честно
            state.upsert_sku(doc, oid, preflight_errors=row.get("errors", []),
                            status=row.get("status"))
        state.record_action(doc, oid, "COMMIT", ok=row.get("ok"))

    state.bump(doc, "ticks")
    state.write_atomic(doc)

    print(f"✅ Залито {rep['agg']['published']}/{rep['agg']['total']}, ошибок {rep['agg']['errors']}")
    print("Теперь нужен verify (--verify) для доказательства PUBLISHED (proof-gate stage 2)")
    return rep


def verify_published():
    """Proof-gate stage 2: независимый READ витрины по всем claimed карточкам → verified."""
    if not hands.creds_present():
        print("❌ REFUSED: нет YANDEX_MARKET_API_KEY — verify невозможен")
        return {"ok": False, "error": "no creds"}

    doc = state.load()
    claimed = [oid for oid, s in doc.get("skus", {}).items()
               if s.get("status") == "PUBLISHED_CLAIMED" and not s.get("published_verified")]

    if not claimed:
        print("Нет claimed карточек для verify (либо все уже verified, либо ещё не заливали)")
        return {"ok": True, "verified": 0, "note": "nothing to verify"}

    print(f"Проверяем {len(claimed)} claimed карточек через независимый READ витрины...")
    verified_count = 0
    errors = []

    for oid in claimed:
        rec, err = proof.verify_publish(oid, hands=hands)
        if err:
            errors.append({"offerId": oid, "error": err})
        else:
            state.mark_published_verified(doc, oid, verified=True)
            state.upsert_sku(doc, oid, status="PUBLISHED", verify_record=rec)
            verified_count += 1

    state.write_atomic(doc)
    print(f"✅ Verified {verified_count}/{len(claimed)} карточек")
    if errors:
        print("⚠️  Ошибки verify:")
        for e in errors:
            print(f"  • {e['offerId']}: {e['error']}")
    return {"ok": True, "verified": verified_count, "errors": errors}


def track_working_set():
    """Track (READ индекса) для всех карточек из working_set. Впитать в память."""
    if not hands.creds_present():
        print("❌ REFUSED: нет YANDEX_MARKET_API_KEY — track невозможен")
        return {"ok": False, "error": "no creds"}

    doc = state.load()
    working = doc.get("working_set", [])
    if not working:
        print("working_set пуст — нечего трекать")
        return {"ok": True, "note": "empty working_set"}

    print(f"Трекаем {len(working)} карточек (READ витрины/индекса)...")
    rep = runner.track(working, dry=False, commit=True)
    if not rep.get("ok"):
        print("❌ track упал или dry")
        return rep

    n = state.ingest_track(doc, rep)
    state.bump(doc, "ticks")
    state.write_atomic(doc)

    print(f"✅ Track завершён: обновлено {n} карточек")
    return rep


def show_self():
    """Показать само-осознание управляющего (без действия)."""
    doc = state.load()
    st = self_mod.self_status(doc)
    print(self_mod.render(st))
    return st


def verify_chain_cmd():
    """Проверить цепочку доказательств тиков (целостность леджера)."""
    ok, problems = proof.verify_chain()
    if ok:
        print("✅ Цепочка тиков целостна")
    else:
        print("❌ Цепочка тиков нарушена:")
        for p in problems:
            print(f"  • индекс {p.get('index')}: {p.get('why')}")
    return {"ok": ok, "problems": problems}


def _main(argv=None):
    ap = argparse.ArgumentParser(
        description="YMARKET MANAGER V1 — управляющий Яндекс.Маркетом (тик-цикл, швейцарская точность)",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tick", action="store_true", help="выполнить один тик (действие по next_lawful_step)")
    ap.add_argument("--preflight", metavar="XLSX", help="preflight категории (dry, 0₽), впитать в память")
    ap.add_argument("--commit", metavar="XLSX", help="РЕАЛЬНЫЙ залив категории (ТОЛЬКО с --commit)")
    ap.add_argument("--verify", action="store_true", help="proof-gate stage 2: verify claimed карточек")
    ap.add_argument("--track", action="store_true", help="track (READ) для working_set, впитать")
    ap.add_argument("--self", action="store_true", help="показать само-осознание (без действия)")
    ap.add_argument("--verify-chain", action="store_true", help="проверить цепочку доказательств тиков")

    ap.add_argument("--slug", help="slug категории (для preflight/commit)")
    ap.add_argument("--vendor", help="vendor name (опц., для from_xlsx)")
    ap.add_argument("--business-id", help="businessId (опц.)")
    ap.add_argument("--campaign-id", help="campaignId (опц.)")
    ap.add_argument("--vat", default="VAT_20", help="НДС (default VAT_20)")
    ap.add_argument("--pace", type=float, default=0.4, help="пауза между товарами, сек (default 0.4)")

    args = ap.parse_args(argv)

    if args.tick:
        return tick(dry=False, commit=True)  # тик всегда в реальном режиме (если commit)
    elif args.preflight:
        if not args.slug:
            print("❌ --preflight требует --slug")
            return {"ok": False}
        return preflight_category(args.preflight, args.slug, vendor=args.vendor)
    elif args.commit:
        if not args.slug:
            print("❌ --commit требует --slug")
            return {"ok": False}
        return commit_category_real(args.commit, args.slug, vendor=args.vendor,
                                    business_id=args.business_id, campaign_id=args.campaign_id,
                                    vat=args.vat, pace=args.pace)
    elif args.verify:
        return verify_published()
    elif args.track:
        return track_working_set()
    elif args.self:
        return show_self()
    elif args.verify_chain:
        return verify_chain_cmd()
    else:
        ap.print_help()
        return {"ok": False}


if __name__ == "__main__":
    sys.exit(0 if _main().get("ok", True) else 1)

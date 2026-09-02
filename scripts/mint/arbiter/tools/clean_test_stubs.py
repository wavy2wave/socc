#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЧИСТКА КАБИНЕТА — снять 2 тестовые заглушки из каталога Яндекс.Маркета.

RUBICON: dry по умолчанию (только читает и показывает, что снял бы — 0 записи). Реальное
удаление ТОЛЬКО с --commit и ТОЛЬКО по явной отмашке оператора. Жёсткий предохранитель:
удаляем исключительно из ALLOWLIST (2 тестовые заглушки) — ничего живого руки не тронут,
даже если передать лишнее. Товар из offer-mappings исчезает НЕОБРАТИМО из каталога и всех
магазинов; поэтому после удаления сразу перечитываем каталог и подтверждаем ЧТЕНИЕМ.

Использование:
    python3 tools/clean_test_stubs.py            # dry — показать, что снял бы
    python3 tools/clean_test_stubs.py --probe     # безопасная проба контракта (удаляет НЕсуществующий id)
    /usr/bin/python3 tools/clean_test_stubs.py --commit   # реально снять (нужны requests + отмашка)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import ymarket_hands_v1 as H  # noqa: E402

# Жёсткий предохранитель: ТОЛЬКО эти offerId допустимы к удалению. Тестовый мусор
# (contentRating 23/29), подтверждён живым чтением каталога 2026-08-11. Всё, что не тут —
# руки не тронут, даже если попадёт в аргументы.
ALLOWLIST = {"TEST-AUTOCAT-1", "TEST-BARECAT-1"}

# Проба контракта: заведомо несуществующий offerId. Удаляет НОЛЬ реальных карточек, но
# заставляет API отдать настоящую форму ответа (status/result/notDeletedOfferIds) этого кабинета.
PROBE_ID = "__CONTRACT_PROBE_DOES_NOT_EXIST__"


def _catalog(bid):
    cards = H.offer_cards_status(bid, limit=100)
    rows = cards if isinstance(cards, list) else (cards.get("offerCards") if isinstance(cards, dict) else [])
    return {c.get("offerId"): c for c in rows if c.get("offerId")}


def main():
    ap = argparse.ArgumentParser(description="Снять тестовые заглушки из каталога ЯМ (dry по умолчанию)")
    ap.add_argument("--commit", action="store_true", help="реально удалить (иначе только показать)")
    ap.add_argument("--probe", action="store_true", help="безопасная проба контракта delete (0 реальных удалений)")
    args = ap.parse_args()

    H._ensure_env()
    bid = H.business_id_env()
    if not bid:
        print("НЕТ businessId — нечего чистить (проверь YANDEX_BUSINESS_ID в mint/.env)")
        return 2
    if not H.creds_present():
        print("НЕТ ключа YANDEX_MARKET_API_KEY — реальный режим недоступен")
        return 2

    catalog = _catalog(bid)
    print(f"business={bid} · в каталоге {len(catalog)} карточек")

    # Что вообще есть из целей
    present = [oid for oid in ALLOWLIST if oid in catalog]
    missing = [oid for oid in ALLOWLIST if oid not in catalog]
    print("\nЦели чистки (ALLOWLIST):")
    for oid in sorted(ALLOWLIST):
        c = catalog.get(oid)
        if c:
            m = c.get("mapping") or {}
            print(f"  • {oid}: есть — рейтинг {c.get('contentRating')}, "
                  f"кат {m.get('marketCategoryId') or c.get('marketCategoryId')} "
                  f"({m.get('marketCategoryName') or c.get('marketCategoryName')})")
        else:
            print(f"  • {oid}: уже нет в каталоге")

    if args.probe:
        print(f"\n== ПРОБА КОНТРАКТА (удаляем несуществующий {PROBE_ID} — 0 реальных удалений) ==")
        resp = H.delete_offer_mappings(bid, [PROBE_ID])
        print(json.dumps(resp, ensure_ascii=False, indent=2))
        # Контроль: каталог не изменился
        after = _catalog(bid)
        print(f"каталог после пробы: {len(after)} карточек (было {len(catalog)}) — "
              f"{'без изменений ✓' if len(after) == len(catalog) else 'ИЗМЕНИЛСЯ ✗'}")
        return 0

    if not present:
        print("\nНечего снимать — обе заглушки уже отсутствуют.")
        return 0

    if not args.commit:
        print(f"\nDRY: снял бы {present} (--commit чтобы реально удалить). "
              f"Ничего не записано.")
        return 0

    # ── LIVE (только по отмашке) ──
    to_delete = [oid for oid in present if oid in ALLOWLIST]  # предохранитель ещё раз
    if to_delete != present:
        print("ОТКАЗ: попытка удалить вне ALLOWLIST — не выполняю")
        return 3
    print(f"\n== LIVE УДАЛЕНИЕ {to_delete} ==")
    resp = H.delete_offer_mappings(bid, to_delete)
    print(json.dumps(resp, ensure_ascii=False, indent=2))
    not_deleted = ((resp.get("result") or {}).get("notDeletedOfferIds")
                   if isinstance(resp, dict) else None) or []
    # Подтверждаем ЧТЕНИЕМ, а не голым 200
    after = _catalog(bid)
    still = [oid for oid in to_delete if oid in after]
    print(f"\nпосле удаления в каталоге {len(after)} карточек (было {len(catalog)})")
    print(f"notDeletedOfferIds: {not_deleted}")
    if still:
        print(f"ВНИМАНИЕ: ещё в каталоге {still} — не удалились (см. notDeletedOfferIds)")
        return 1
    print(f"✓ снято чтением подтверждено: {to_delete} больше нет в каталоге")
    return 0


if __name__ == "__main__":
    sys.exit(main())
